#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Serve models on this machine's GPUs through one shared vLLM installation, one server per model profile.

  serve.py up PROFILE [-- ARGS]  start the profile's server unless it already runs, wait until it answers, and
                                 print {"profile", "url", "model", "started"}; concurrent calls share one server.
                                 ARGS are `vllm serve` arguments for this start only; the caller's environment
                                 reaches the server too (CUDA_VISIBLE_DEVICES picks the GPUs), except variables the
                                 profile's env sets
  serve.py down PROFILE          stop it now (--all: every profile)
  serve.py status                one JSON line per profile: running, url, owner, gpus, load, idle_for_minutes, log

A server stops by itself once it has had no request for the profile's idle_minutes, so the GPUs are free for
other work; `up` counts as a request. Clients speak the OpenAI API at the url, with the model name given.

Profiles: <name>.toml in ~/.config/vllm-serve/profiles/ (XDG_CONFIG_HOME), then in profiles/ beside this script.
Keys: model (Hugging Face id or local directory; clients use it as the model name), port, idle_minutes (default
10; 0: never stops by itself), args (`vllm serve` arguments), env, extends (a profile to start from: its keys, then this file's; args are
appended, env merged; a profile may extend the one of its own name further down the search path).
Every vLLM setting is a vLLM argument. serve.py reads two of them, the last one winning as in vLLM: --host
(added as 127.0.0.1 when absent) and --revision (the weights it downloads); it adds --served-model-name and --port.
The vllm executable: VLLM_SERVE_VLLM, else the `vllm` uv tool, else vllm on PATH.
State and logs: ~/.local/state/vllm-serve/ (XDG_STATE_HOME), <profile>.log per server.

`up` waits as long as the server's log keeps growing. Its line may also carry "host" (the server listens beyond
this machine: clients elsewhere use the machine's address), "differs" (the running server was started with other
arguments or GPUs than this `up` asks for, given as the running ones; `down` it to apply yours) and "foreign_cuda"
(CUDA libraries a freshly started server mapped from outside vLLM's environment; there should be none).

Errors, one JSON line on stdout with exit 2: unknown_profile, vllm_missing, port_busy (another model answers on
the port, or another program holds it), download_failed (hf's own output precedes it), server_failed (with the
log's first error line and its end), not_permitted (a server or file of another login).
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from contextlib import contextmanager
from pathlib import Path

SKILL_PROFILES = Path(__file__).resolve().parent.parent / "profiles"
KEYS = {"model", "port", "idle_minutes", "args", "env", "extends"}
STALL = float(os.environ.get("VLLM_SERVE_STALL", 600))   # seconds a starting server may write nothing to its log
TICK = float(os.environ.get("VLLM_SERVE_TICK", 30))      # seconds between idle checks
# Settings every server gets; a profile's env overrides them.
# - Pinned memory is off under WSL by default (2026-10, vLLM 0.28 stopped with "UVA is not available"; 0.31 runs
#   slower without it).
# - FlashInfer's sampler compiles its kernels on first use, and the pip CUDA toolkit cannot link them (no lib64, no
#   libcudart.so, no stubs/libcuda.so); vLLM samples with PyTorch instead.
# - CUDA_VISIBLE_DEVICES numbers mean nvidia-smi's numbering; CUDA's own default order is fastest first.
# - vLLM's start-up deadline (600 s, applied with data parallel) stopped a 52 GB load from a slow disk (2026-10,
#   vLLM 0.32); `up` watches the log instead.
MACHINE_ENV = {"VLLM_WSL2_ENABLE_PIN_MEMORY": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0",
               "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "VLLM_ENGINE_READY_TIMEOUT_S": "86400"}
CUDA_LIBRARY = re.compile(r"/lib(cudart|cublas|cublasLt|cudnn\w*|nvrtc|nccl|cufft|curand|cusolver|cusparse)\.so")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # this machine's servers, never via a proxy


class Failure(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code, self.detail = code, detail


# ---------------------------------------------------------------- profiles and paths

def profile_dirs() -> list[Path]:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return [config / "vllm-serve" / "profiles", SKILL_PROFILES]


def profile_names() -> list[str]:
    return sorted({p.stem for d in profile_dirs() if d.is_dir() for p in d.glob("*.toml")})


def profile_path(name: str, below: Path | None = None) -> Path:
    """The first <name>.toml on the search path, or the first after `below`'s directory (a profile extending the
    profile of its own name)."""
    dirs = profile_dirs()
    if below is not None:
        later = [i for i, d in enumerate(dirs) if d.resolve() == below.parent.resolve()]
        dirs = dirs[later[0] + 1:] if later else dirs
    for d in dirs:
        if (d / f"{name}.toml").is_file():
            return d / f"{name}.toml"
    raise Failure("unknown_profile", f"no {name}.toml in {', '.join(map(str, dirs))}; "
                                     f"profiles: {', '.join(profile_names()) or 'none'}")


def read_profile(path: Path, seen: tuple[Path, ...] = ()) -> dict:
    if path in seen:
        raise Failure("unknown_profile", f"profiles extend each other in a circle: {', '.join(map(str, seen))}")
    p = tomllib.loads(path.read_text(encoding="utf-8"))
    if unknown := sorted(set(p) - KEYS):
        raise Failure("unknown_profile", f"{path}: unknown keys {', '.join(unknown)} (keys: {', '.join(sorted(KEYS))}; "
                                         f"vLLM settings go in args, e.g. --gpu-memory-utilization)")
    base = {}
    if "extends" in p:
        parent = profile_path(p["extends"], below=path if p["extends"] == path.stem else None)
        base = read_profile(parent, (*seen, path))
    return {**base, **p, "args": [*base.get("args", []), *p.get("args", [])], "env": {**base.get("env", {}), **p.get("env", {})}}


def load_profile(name: str) -> dict:
    path = profile_path(name)
    p = read_profile(path)
    if missing := [k for k in ("model", "port") if k not in p]:
        raise Failure("unknown_profile", f"{path} lacks {', '.join(missing)}")
    return {"idle_minutes": 10, **p, "name": name, "path": str(path)}


def state_dir() -> Path:
    d = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "vllm-serve"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def locked(name: str):
    """The profile's lock: held by `up` from its health check until the server answers, by `down`, and by the
    supervisor while it decides to stop, so a caller never gets a server that is starting or stopping."""
    with open(state_dir() / f"{name}.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_state(name: str) -> dict | None:
    try:
        return json.loads((state_dir() / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:         # another login's process
        return True


def login() -> str:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return str(os.getuid())


# ---------------------------------------------------------------- the server's command and address

def arg_value(args: list[str], name: str) -> str | None:
    """The value of the last `name` flag in vLLM arguments (`--flag value` or `--flag=value`; vLLM reads
    underscores in flag names as dashes)."""
    value = None
    for i, a in enumerate(args):
        flag, eq, v = a.partition("=")
        if flag.startswith("--") and flag.replace("_", "-") == name:
            value = v if eq else (args[i + 1] if i + 1 < len(args) else None)
    return value


def local_model(profile: dict) -> bool:
    return Path(profile["model"]).expanduser().is_dir()


def launch_args(profile: dict, extra: list[str] = ()) -> list[str]:
    """Everything after `vllm serve`: the model, the profile's and this start's arguments, then serve.py's own."""
    args = [*map(str, profile["args"]), *extra]
    own = ["--served-model-name", profile["model"], "--port", str(profile["port"])]
    if arg_value(args, "--host") is None:
        own += ["--host", "127.0.0.1"]
    model = str(Path(profile["model"]).expanduser()) if local_model(profile) else profile["model"]
    return [model, *args, *own]


def address(host: str | None) -> str:
    """Where this machine reaches a server bound to `host`."""
    return "127.0.0.1" if not host or host in LOOPBACK or host in ("0.0.0.0", "::") else host


def base_url(port: int, host: str | None) -> str:
    return f"http://{address(host)}:{port}/v1"


def answers(port: int, model: str, host: str | None = None, key: str | None = None) -> bool | None:
    """True: the model answers on the port; False: another model does; None: nothing does. `key`: the server's
    --api-key, which guards /v1."""
    request = urllib.request.Request(base_url(port, host) + "/models", headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        with LOCAL.open(request, timeout=5) as r:
            ids = [m.get("id") for m in json.load(r).get("data", [])]
        return model in ids
    except (OSError, ValueError):
        return None


def port_taken(port: int, host: str | None) -> bool:
    """Whether another program holds the port where the server would bind (with SO_REUSEADDR, as vLLM binds)."""
    bind = host if host and host not in ("localhost",) else "127.0.0.1"
    with socket.socket(socket.AF_INET6 if ":" in bind else socket.AF_INET) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((bind, port))
            return False
        except OSError:
            return True


# ---------------------------------------------------------------- vLLM's environment

def find_vllm() -> str | None:
    if os.environ.get("VLLM_SERVE_VLLM"):
        return os.environ["VLLM_SERVE_VLLM"]
    try:
        tool_dir = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True, check=True).stdout.strip()
        candidate = Path(tool_dir) / "vllm" / "bin" / "vllm"
        if candidate.exists():
            return str(candidate)
    except (OSError, subprocess.CalledProcessError):
        pass
    return shutil.which("vllm")


def without_cuda_toolkit(path: str) -> str | None:
    """LD_LIBRARY_PATH minus directories holding a CUDA runtime: vLLM's PyTorch brings its own, and a system
    toolkit ahead of it gets loaded beside it (2026-10). None when nothing is left."""
    kept = [d for d in path.split(":") if not (d and glob.glob(os.path.join(glob.escape(d), "libcudart.so*")))]
    return ":".join(kept) if any(kept) else None


def own_cuda(vllm: str) -> Path | None:
    """The CUDA toolkit inside vLLM's environment (site-packages/nvidia/cu13 with bin/nvcc, include, lib), the
    newest if several; None when the environment has none (CUDA 12 builds: PyPI ships no CUDA 12 nvcc)."""
    root = Path(vllm).resolve().parent.parent
    found = sorted(root.glob("lib/python3*/site-packages/nvidia/cu[0-9]*/bin/nvcc"), key=lambda p: int(p.parent.parent.name[2:]))
    return found[-1].parent.parent if found else None


def own_cuda_runtime(vllm: str) -> Path | None:
    """The directory of the CUDA runtime (libcudart) inside vLLM's environment, the newest if several."""
    root = Path(vllm).resolve().parent.parent
    found = sorted(root.glob("lib/python3*/site-packages/nvidia/*/lib/libcudart.so.*"))
    return found[-1].parent if found else None


def unversioned_links(cuda: Path) -> Path:
    """A directory of unversioned library names pointing into the environment's toolkit (libcublas.so ->
    .../libcublas.so.13). FlashInfer's autotuner dlopens "libcublas.so"; the pip toolkit ships only versioned
    names, so the system loader cache answered with the system toolkit's cuBLAS (2026-10)."""
    d = state_dir() / "cuda-links" / hashlib.sha1(str(cuda).encode()).hexdigest()[:12]
    d.mkdir(parents=True, exist_ok=True)
    for lib in sorted((cuda / "lib").glob("lib*.so.*")):
        link = d / (lib.name.split(".so.", 1)[0] + ".so")
        if not link.is_symlink():
            link.symlink_to(lib)
    return d


def server_env(base: dict, profile: dict, offline: bool, cuda: Path | None = None, venv_bin: Path | None = None,
               links: Path | None = None, runtime: Path | None = None) -> dict:
    """The server's environment: serve.py's settings, the caller's environment (base), then the profile's env, each
    over the one before, made to use only vLLM's own CUDA. The profile wins: a deployment's GPUs must not move with
    whatever a caller's environment happens to hold."""
    env = {**MACHINE_ENV, **base}
    env.pop("CUDA_MODULE_LOADING", None)    # EAGER, which Paddle needs, stalled vLLM's engine start for minutes
    if "LD_LIBRARY_PATH" in env:
        path = without_cuda_toolkit(env.pop("LD_LIBRARY_PATH"))
        if path:
            env["LD_LIBRARY_PATH"] = path
    if cuda:
        env["LD_LIBRARY_PATH"] = ":".join(str(d) for d in (links, cuda / "lib", env.get("LD_LIBRARY_PATH")) if d)
        # Every CUDA lookup goes to the environment's own toolkit, not the system's. The system one got in through
        # CUDA_HOME (FlashInfer took its nvcc 12.8 and refused RTX 50 GPUs) and through FlashInfer's preload of
        # CUDA_LIB_PATH/libcudart.so.12, default /usr/local/cuda/... (2026-10).
        env.update(CUDA_HOME=str(cuda), CUDA_PATH=str(cuda), CUDA_LIB_PATH=str(cuda / "lib"))
    else:   # no toolkit in the environment (CUDA 12 builds): nothing points libraries at a system one
        for k in ("CUDA_HOME", "CUDA_PATH", "CUDA_LIB_PATH"):
            env.pop(k, None)
        if runtime:
            env["CUDA_LIB_PATH"] = str(runtime)
    # Run as if the environment were activated: its own tools (ninja, which FlashInfer's kernel builds call) and
    # its CUDA compiler come first.
    env["PATH"] = ":".join([*(str(d) for d in (cuda / "bin" if cuda else None, venv_bin) if d), env.get("PATH", "")])
    if offline:
        env.setdefault("HF_HUB_OFFLINE", "1")   # the weights are in the cache: start without asking the Hub
    env.update({k: str(v) for k, v in profile["env"].items()})
    return env


def hub_cached(model: str, revision: str | None = None) -> bool:
    """Whether the Hugging Face cache holds this revision of the model (a commit hash, a branch or tag, else main)
    in the form an offline vLLM loads: a branch needs its refs/ entry, a commit hash only its snapshot."""
    hub = os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    repo = Path(hub) / f"models--{model.replace('/', '--')}"
    commit = revision or "main"
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        try:
            commit = (repo / "refs" / commit).read_text().strip()
        except OSError:
            return False
    return (repo / "snapshots" / commit / "config.json").exists()


def ensure_weights(profile: dict, vllm: str, revision: str | None) -> None:
    """Download a Hub model before the server starts, so the download does not hold up its start."""
    if local_model(profile) or hub_cached(profile["model"], revision):
        return
    hf = Path(vllm).resolve().parent / "hf"
    cmd = [str(hf) if hf.exists() else (shutil.which("hf") or "hf"), "download", profile["model"],
           *(["--revision", revision] if revision else [])]
    print(f"[vllm-serve] downloading {profile['model']} {revision or ''}...", file=sys.stderr, flush=True)
    try:
        done = subprocess.run(cmd, stdout=subprocess.DEVNULL)      # its progress and errors go to our stderr
    except OSError as e:
        raise Failure("download_failed", f"cannot run {cmd[0]}: {e}") from e
    if done.returncode:
        raise Failure("download_failed", f"`{' '.join(cmd)}` exited with {done.returncode}; its output is above")


def foreign_cuda(maps: str, env_root: Path) -> set[str]:
    """CUDA libraries in a /proc/<pid>/maps text that come from outside vLLM's environment (the driver's libcuda
    is not one of them): a system toolkit leaking in."""
    found = set()
    for line in maps.splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and CUDA_LIBRARY.search(parts[5]) and not parts[5].startswith(f"{env_root}/"):
            found.add(parts[5])
    return found


def server_foreign_cuda(name: str, vllm: str) -> list[str]:
    """foreign_cuda over every process of the profile's running server (vLLM's process group)."""
    state = read_state(name) or {}
    env_root, found = Path(vllm).resolve().parent.parent, set()
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if int((proc / "stat").read_text().rsplit(")", 1)[1].split()[2]) == state.get("vllm_pid"):
                found |= foreign_cuda((proc / "maps").read_text(), env_root)
        except (OSError, ValueError, IndexError):
            continue
    return sorted(found)


def log_tail(name: str, lines: int = 20) -> str:
    try:
        return "\n".join((state_dir() / f"{name}.log").read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def failed(name: str, why: str) -> Failure:
    """server_failed with the log's first error line (vLLM's root cause sits above the tracebacks that end the log)
    and the log's end."""
    log = state_dir() / f"{name}.log"
    try:
        first = next((line.strip() for line in log.read_text(errors="replace").splitlines()
                      if re.search(r"\b[A-Z]\w*(Error|Exception): ", line)), None)
    except OSError:
        first = None
    return Failure("server_failed", f"{name}'s server {why}; first error: {first or 'none logged'}\n{log} ends:\n{log_tail(name)}")


def wait_ready(name: str, port: int, model: str, host: str | None, key: str | None, running) -> str | None:
    """Wait until the server answers: None when it does, else why not. A start may take long (52 GB of weights
    from a slow disk, kernels compiled on a first start) but keeps writing to its log; one that stops writing for
    STALL seconds is stuck."""
    log, size, changed = state_dir() / f"{name}.log", -1, time.time()
    while True:
        if answers(port, model, host, key):
            return None
        if not running():
            return "exited"
        now, grown = time.time(), log.stat().st_size if log.exists() else 0
        if grown != size:
            size, changed = grown, now
        elif now - changed > STALL:
            return f"wrote nothing to its log for {STALL / 60:.0f} min"
        time.sleep(2)


# ---------------------------------------------------------------- idle tracking and load

def parse_metrics(text: str) -> dict[str, list[float]]:
    """Every value of each series in vLLM's Prometheus /metrics text, one per label set (with data parallel, one
    per engine)."""
    out: dict[str, list[float]] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            try:
                out.setdefault(line.split("{", 1)[0].split(" ", 1)[0], []).append(float(line.rsplit(" ", 1)[1]))
            except (IndexError, ValueError):
                continue
    return out


def total(m: dict, name: str) -> float:
    return sum(m.get(name, ()))


class Idle:
    """Seconds since the server last had work: a request running or waiting, a request finished, or an `up`."""

    def __init__(self, now: float):
        self.last, self.done, self.touched = now, None, 0.0

    def update(self, now: float, m: dict | None, touched: float) -> float:
        active = m and total(m, "vllm:num_requests_running") + total(m, "vllm:num_requests_waiting")
        done = total(m, "vllm:request_success_total") if m else None
        if active or (done is not None and done != self.done) or touched > self.touched:
            self.last = now
        self.done = done if done is not None else self.done
        self.touched = max(self.touched, touched)
        return now - self.last


class Load:
    """The server's load from successive /metrics readings; token rates cover the time since the previous one."""

    def __init__(self):
        self.last: tuple[float, float, float] | None = None

    def update(self, now: float, m: dict) -> dict:
        queries, prompt, generated = (total(m, f"vllm:{k}_total") for k in ("prefix_cache_queries", "prompt_tokens", "generation_tokens"))
        out = {"running": int(total(m, "vllm:num_requests_running")), "waiting": int(total(m, "vllm:num_requests_waiting")),
               "kv_cache_usage": round(max(m.get("vllm:kv_cache_usage_perc", [0])), 3),
               "prefix_cache_hit_rate": round(total(m, "vllm:prefix_cache_hits_total") / queries, 3) if queries else None,
               "preemptions": int(total(m, "vllm:num_preemptions_total"))}
        if self.last and now > self.last[0]:
            seconds = now - self.last[0]
            out.update(prompt_tokens_per_s=round((prompt - self.last[1]) / seconds, 1),
                       generation_tokens_per_s=round((generated - self.last[2]) / seconds, 1))
        self.last = (now, prompt, generated)
        return out


def touch(name: str) -> None:
    (state_dir() / f"{name}.touch").write_text(str(time.time()))


def touched(name: str) -> float:
    try:
        return (state_dir() / f"{name}.touch").stat().st_mtime
    except OSError:
        return 0.0


def metrics(port: int, host: str | None) -> dict | None:
    try:
        with LOCAL.open(f"http://{address(host)}:{port}/metrics", timeout=10) as r:
            return parse_metrics(r.read().decode())
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- commands

def launch(profile: dict, extra: list[str]) -> dict:
    """What a start of this profile from here would run: its arguments, the GPUs it would see, its address and API
    key."""
    args = launch_args(profile, extra)
    env = {**os.environ, **{k: str(v) for k, v in profile["env"].items()}}
    return {"args": args, "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"), "host": arg_value(args, "--host"),
            "key": arg_value(args, "--api-key") or env.get("VLLM_API_KEY")}


def reply(name: str, profile: dict, host: str | None, started: bool) -> dict:
    out = {"profile": name, "url": base_url(profile["port"], host), "model": profile["model"], "started": started}
    if host not in LOOPBACK:
        out["host"] = host
    return out


def up(name: str, extra: list[str]) -> dict:
    profile = load_profile(name)
    want = launch(profile, extra)
    with locked(name):
        state = read_state(name)
        running = state if state and alive(state.get("pid")) else None
        host = running.get("host", "127.0.0.1") if running else want["host"]
        if running and answers(profile["port"], profile["model"], host, want["key"]) is None:
            # a server still starting: the `up` that launched it was interrupted
            if why := wait_ready(name, profile["port"], profile["model"], host, want["key"], lambda: alive(running["pid"])):
                raise failed(name, f"{why} (its supervisor, pid {running['pid']}, runs: `serve.py down {name}`)")
        found = answers(profile["port"], profile["model"], host, want["key"])
        if found:                       # supervised here, or started by hand on the profile's port
            touch(name)
            out = reply(name, profile, host, False)
            if running and (differs := {k: running.get(k) for k in ("args", "cuda_visible_devices") if running.get(k) != want[k]}):
                out["differs"] = differs
            return out
        if found is False:
            raise Failure("port_busy", f"port {profile['port']} answers with another model; `curl {base_url(profile['port'], host)}/models`")
        if port_taken(profile["port"], want["host"]):
            raise Failure("port_busy", f"another program holds port {profile['port']}: `ss -ltnp | grep :{profile['port']}`")
        vllm = find_vllm()
        if not vllm:
            raise Failure("vllm_missing", "no vllm executable; see references/install.md")
        ensure_weights(profile, vllm, arg_value(want["args"], "--revision"))
        print(f"[vllm-serve] starting {name} ({profile['model']}) on port {profile['port']} ...", file=sys.stderr, flush=True)
        log = open(state_dir() / f"{name}.log", "wb")
        supervisor = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", name, "--", *extra],
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        log.close()
        why = wait_ready(name, profile["port"], profile["model"], want["host"], want["key"], lambda: supervisor.poll() is None)
        if why is None:
            touch(name)
            out = reply(name, profile, want["host"], True)
            if foreign := server_foreign_cuda(name, vllm):
                out["foreign_cuda"] = foreign
                print(f"[vllm-serve] {name}'s server loaded CUDA libraries from outside vLLM's environment: "
                      f"{', '.join(foreign)}; see references/install.md", file=sys.stderr, flush=True)
            return out
        if supervisor.poll() is None:
            supervisor.terminate()
            supervisor.wait(60)
        raise failed(name, why)


def die_with_parent() -> None:
    """Runs in vLLM's process before it execs: SIGTERM it when the supervisor dies, even by SIGKILL."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)      # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def stop(proc: subprocess.Popen) -> None:
    """SIGTERM vLLM's process group (it runs its engines in children), SIGKILL whatever is left after 30 s."""
    for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(wait)
        except subprocess.TimeoutExpired:
            pass


def supervise(name: str, extra: list[str]) -> None:
    """Run the profile's vLLM server until it has been idle for idle_minutes, it exits, or `down` stops it."""
    profile = load_profile(name)
    vllm = find_vllm()
    run = launch(profile, extra)
    offline = not local_model(profile) and hub_cached(profile["model"], arg_value(run["args"], "--revision"))
    cuda = own_cuda(vllm)
    env = server_env(dict(os.environ), profile, offline, cuda, Path(vllm).resolve().parent,
                     unversioned_links(cuda) if cuda else None, None if cuda else own_cuda_runtime(vllm))
    proc = subprocess.Popen([vllm, "serve", *run["args"]], stdin=subprocess.DEVNULL, env=env,
                            start_new_session=True, preexec_fn=die_with_parent if sys.platform == "linux" else None)
    path = state_dir() / f"{name}.json"
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    idle, load = Idle(time.time()), Load()
    state = {"pid": os.getpid(), "vllm_pid": proc.pid, "port": profile["port"], "model": profile["model"],
             "owner": login(), "since": time.time(), "idle_seconds": 0, **{k: run[k] for k in ("args", "cuda_visible_devices", "host")}}
    try:
        path.write_text(json.dumps(state))
        while proc.poll() is None:
            time.sleep(TICK)
            now, m = time.time(), metrics(profile["port"], run["host"])
            seconds = idle.update(now, m, touched(name))
            state.update(idle_seconds=round(seconds), **({"load": load.update(now, m)} if m else {}))
            path.write_text(json.dumps(state))
            limit = profile["idle_minutes"] * 60
            if limit and seconds >= limit:
                with locked(name):      # no `up` may hand out this server while it stops
                    if idle.update(time.time(), metrics(profile["port"], run["host"]), touched(name)) >= limit:
                        print(f"[vllm-serve] {name} idle for {profile['idle_minutes']} min, stopping", flush=True)
                        stop(proc)
                        path.unlink(missing_ok=True)
                        return
    finally:
        stop(proc)
        path.unlink(missing_ok=True)


def down(name: str) -> dict:
    profile = load_profile(name)
    with locked(name):
        state = read_state(name)
        if not state or not alive(state.get("pid")):
            (state_dir() / f"{name}.json").unlink(missing_ok=True)
            return {"profile": name, "stopped": False}
        try:
            os.kill(state["pid"], signal.SIGTERM)
        except PermissionError:
            raise Failure("not_permitted", f"{name}'s server (pid {state['pid']}) was started by {state.get('owner', 'another login')}: "
                                           f"that login stops it, or it stops by itself once idle ({profile['idle_minutes']} min; 0: never)") from None
        for _ in range(90):
            if not alive(state["pid"]) and answers(profile["port"], profile["model"], state.get("host"), launch(profile, [])["key"]) is None:
                break
            time.sleep(1)
        return {"profile": name, "stopped": True}


def status(name: str) -> dict:
    profile = load_profile(name)
    state = read_state(name)
    running = bool(state and alive(state.get("pid")))
    host = state.get("host") if running else arg_value(launch_args(profile), "--host")
    out = {"profile": name, "model": profile["model"], "running": running, "url": base_url(profile["port"], host)}
    if running:
        out.update(pid=state["pid"], owner=state.get("owner"), gpus=state.get("cuda_visible_devices"),
                   idle_for_minutes=round(state.get("idle_seconds", 0) / 60, 1), stops_after_minutes=profile["idle_minutes"])
        if host not in LOOPBACK:
            out["host"] = host
        if "load" in state:
            out["load"] = state["load"]
    out["log"] = str(state_dir() / f"{name}.log")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("up", "_supervise"):
        s = sub.add_parser(command)
        s.add_argument("profile")
        s.add_argument("vllm_args", nargs="*", help="after --: `vllm serve` arguments for this start")
    d = sub.add_parser("down")
    d.add_argument("profile", nargs="?")
    d.add_argument("--all", action="store_true")
    sub.add_parser("status")
    args = p.parse_args(argv)
    try:
        if args.command == "_supervise":
            supervise(args.profile, args.vllm_args)
            return 0
        if args.command == "up":
            print(json.dumps(up(args.profile, args.vllm_args)), flush=True)
        elif args.command == "down":
            if not args.all and not args.profile:
                p.error("down needs a profile or --all")
            for name in profile_names() if args.all else [args.profile]:
                print(json.dumps(down(name)), flush=True)
        else:
            for name in profile_names():
                try:
                    print(json.dumps(status(name)), flush=True)
                except Failure as e:
                    print(json.dumps({"profile": name, "error": e.code, "detail": e.detail}), flush=True)
    except Failure as e:
        print(json.dumps({"error": e.code, "detail": e.detail}), flush=True)
        return 2
    except PermissionError as e:
        owner = ""
        try:
            owner = f" (owned by {Path(e.filename).owner()})" if e.filename else ""
        except (OSError, KeyError):
            pass
        print(json.dumps({"error": "not_permitted", "detail": f"{e}{owner}; the owner hands it over, e.g. `chown -R`"}), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
