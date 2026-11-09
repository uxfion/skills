#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""vllm-serve: models as OpenAI-compatible vLLM servers on this machine's GPUs, one server per model profile.

A start is one job of a supervisor process: it downloads the weights when the cache lacks them, starts vLLM and
writes all their output to the profile's log. A vLLM that has not answered 30 min after its start is stopped (the
download does not count); once it has answered, the server stops by itself after idle_minutes without a request.
The log's last line says how the start ended; the next start keeps the log as <profile>.prev.log and says so when
that start failed.

Profiles: <name>.toml in ~/.config/vllm-serve/profiles/ (XDG_CONFIG_HOME), then in the skill's profiles/; a
profile is named, never a path. Keys: model (Hugging Face id or local directory; clients use it as the model
name), port, idle_minutes (above 0, default 10), args (`vllm serve` arguments), env, extends (a profile to start
from: its keys, then this file's; args are appended, env merged; a profile may extend the one of its own name
further down the search path). Every vLLM setting is a vLLM argument. serve.py reads two of them, the last one
winning as in vLLM: --host (added as 127.0.0.1 when absent) and --revision (the weights it downloads); it adds
--served-model-name and --port.
The vllm executable: VLLM_SERVE_VLLM, else the `vllm` uv tool, else vllm on PATH.
State and logs: ~/.local/state/vllm-serve/ (XDG_STATE_HOME), <profile>.log per server.

Exit codes, every word: 0 done; 1 a profile is yours to act on: its line's code and hint say what, and down and
status end stderr with {"summary": ...}; 2 the command cannot go on (no vLLM, a state file of another login, a
usage error): stderr's last line is {code, detail, hint}.

Examples:
  serve.py up paddleocr-vl
  serve.py status | jq -c 'select(.phase == "running" and .idle_for_minutes >= 30)' | serve.py down -
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import hashlib
import http.client
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

SELF = Path(__file__).name
# word: (script, what it does). Every word runs here, in serve.py, so none has a script of its own.
WORDS = {
    "up": (None, "start a profile's server unless it runs, wait until it answers, print where it is"),
    "down": (None, "stop profiles' servers, in whatever phase"),
    "status": (None, "list the profiles: phase, url, owner, GPUs, load, idle time, last start, log"),
}
SKILL_PROFILES = Path(__file__).resolve().parent.parent / "profiles"
GUIDE = Path(__file__).resolve().parent.parent / "references" / "install.md"
KEYS = {"model", "port", "idle_minutes", "args", "env", "extends"}
TICK = float(os.environ.get("VLLM_SERVE_TICK", 30))      # seconds between idle checks
# Seconds vLLM may take from its start to its first answer before the supervisor stops it, so a start that hangs
# gives the GPUs back with nobody watching. The slowest phases met (references/install.md, Timings): a 27B model's
# first start compiling kernels, about 6 min, and its weights read from a nearly full disk, 7-8 min. The download
# before vLLM holds no GPU and does not count.
START_LIMIT = float(os.environ.get("VLLM_SERVE_START_LIMIT", 30 * 60))
# Settings every server gets, under the caller's environment and the profile's env; the reason for each is in
# references/install.md ("What serve.py sets for every server").
MACHINE_ENV = {"VLLM_WSL2_ENABLE_PIN_MEMORY": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0",
               "CUDA_DEVICE_ORDER": "PCI_BUS_ID", "VLLM_ENGINE_READY_TIMEOUT_S": "86400"}
CUDA_LIBRARY = re.compile(r"/lib(cudart|cublas|cublasLt|cudnn\w*|nvrtc|nccl|cufft|curand|cusolver|cusparse)\.so")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # this machine's servers, never via a proxy
OK, ACT, CANNOT = 0, 1, 2
FIX_PROFILE = "Name a profile that detail lists, or fix the file it names."


class Failure(Exception):
    """A problem with one profile, on that profile's line (exit 1), or one that stops the command (exit CANNOT: its
    line is stderr's last)."""

    def __init__(self, code: str, detail: str, hint: str, exit: int = ACT):
        super().__init__(detail)
        self.code, self.detail, self.hint, self.exit = code, detail, hint, exit

    def line(self, profile: str | None = None) -> dict:
        return {**({"profile": profile} if profile else {}), "code": self.code, "detail": self.detail, "hint": self.hint}


# ---------------------------------------------------------------- profiles

def profile_dirs() -> list[Path]:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return [config / "vllm-serve" / "profiles", SKILL_PROFILES]


def profile_names() -> list[str]:
    return sorted({p.stem for d in profile_dirs() if d.is_dir() for p in d.glob("*.toml")})


def profile_path(name: str, below: Path | None = None) -> Path:
    """The first <name>.toml on the search path, or the first after `below`'s directory (a profile extending the
    profile of its own name). A name is never a path: one holding "/" is no profile."""
    dirs = profile_dirs()
    if below is not None:
        later = [i for i, d in enumerate(dirs) if d.resolve() == below.parent.resolve()]
        dirs = dirs[later[0] + 1:] if later else dirs
    for d in dirs:
        if "/" not in name and (d / f"{name}.toml").is_file():
            return d / f"{name}.toml"
    raise Failure("unknown_profile", f"no {name}.toml in {', '.join(map(str, dirs))}; "
                                     f"profiles: {', '.join(profile_names()) or 'none'}", FIX_PROFILE)


def read_profile(path: Path, seen: tuple[Path, ...] = ()) -> dict:
    if path in seen:
        raise Failure("unknown_profile", f"profiles extend each other in a circle: {', '.join(map(str, seen))}", FIX_PROFILE)
    try:
        p = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise Failure("unknown_profile", f"{path} is not valid TOML: {e}", FIX_PROFILE) from None
    if unknown := sorted(set(p) - KEYS):
        raise Failure("unknown_profile", f"{path}: unknown keys {', '.join(unknown)} (keys: {', '.join(sorted(KEYS))})",
                      "Fix the file: vLLM settings go in args, e.g. --gpu-memory-utilization.")
    base = {}
    if "extends" in p:
        parent = profile_path(p["extends"], below=path if p["extends"] == path.stem else None)
        base = read_profile(parent, (*seen, path))
    return {**base, **p, "args": [*base.get("args", []), *p.get("args", [])], "env": {**base.get("env", {}), **p.get("env", {})}}


def load_profile(name: str) -> dict:
    path = profile_path(name)
    p = {"idle_minutes": 10, **read_profile(path)}
    if missing := [k for k in ("model", "port") if k not in p]:
        raise Failure("unknown_profile", f"{path} lacks {', '.join(missing)}", FIX_PROFILE)
    if not isinstance(p["idle_minutes"], (int, float)) or p["idle_minutes"] <= 0:
        raise Failure("unknown_profile", f"{path}: idle_minutes must be minutes above 0",
                      "Fix the file: a server meant to stay up takes a large number.")
    return {**p, "name": name, "path": str(path)}


# ---------------------------------------------------------------- state: who runs, decided under one lock

def state_dir() -> Path:
    d = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "vllm-serve"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path(name: str) -> Path:
    return state_dir() / f"{name}.log"


@contextmanager
def deciding():
    """The one lock, shared by every profile, for short decisions: whether to start a supervisor, handing a server
    out, and a supervisor's decision to stop when idle. Nobody holds it while waiting for a server."""
    with open(state_dir() / "decide.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def held(name: str) -> bool:
    """Whether the profile's supervisor is alive: it holds <profile>.run from its start to its exit, and the kernel
    releases the lock when it dies, so a stale state file or a reused pid never counts."""
    try:
        f = open(state_dir() / f"{name}.run", "rb")
    except FileNotFoundError:
        return False
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)     # released when f closes
        except BlockingIOError:
            return True
        return False


def read_state(name: str) -> dict | None:
    try:
        return json.loads((state_dir() / f"{name}.json").read_text())
    except (OSError, ValueError):
        return None


def write_state(name: str, state: dict) -> None:
    path = state_dir() / f"{name}.json"
    path.with_suffix(".tmp").write_text(json.dumps(state))
    os.replace(path.with_suffix(".tmp"), path)


def live(name: str) -> dict | None:
    """The state of the profile's live supervisor: {} for the moment it has none (just started, or on its way out
    with its record of how it ended written); None when no supervisor runs."""
    if not held(name):
        return None
    state = read_state(name) or {}
    return {} if state.get("phase") == "stopped" else state


def last_start(name: str) -> dict | None:
    """How the profile's last start ended, once no supervisor runs: the supervisor's own record, or, when it left
    the state of a live one behind, that it died without one."""
    try:
        state, at = read_state(name), (state_dir() / f"{name}.json").stat().st_mtime
    except OSError:
        return None
    if not state:
        return None
    if state.get("phase") == "stopped":
        ended, failed = state.get("why"), state.get("failed")
    else:
        ended, failed = "its supervisor died without a record: killed, or the machine restarted", True
    return {"ended": ended, "failed": failed, "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(at))}


def running_names() -> list[str]:
    return [p.stem for p in state_dir().glob("*.run") if held(p.stem)]


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


def launch(profile: dict, extra: list[str]) -> dict:
    """What a start of this profile from here runs: its model, port, arguments, address and the GPUs it sees."""
    args = launch_args(profile, extra)
    env = {**os.environ, **{k: str(v) for k, v in profile["env"].items()}}
    return {"model": profile["model"], "port": profile["port"], "args": args, "host": arg_value(args, "--host"),
            "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES")}


def address(host: str | None) -> str:
    """Where this machine reaches a server bound to `host`."""
    return "127.0.0.1" if host in (None, "", "0.0.0.0", "::") else host


def url(host: str | None, port: int, path: str = "/v1") -> str:
    a = address(host)
    return f"http://{f'[{a}]' if ':' in a else a}:{port}{path}"


def healthy(host: str | None, port: int) -> bool:
    """Whether vLLM answers 200 on /health (outside --api-key's guard). Nothing listening, a 503, a timeout or a
    reply that is not HTTP: not yet."""
    try:
        with LOCAL.open(url(host, port, "/health"), timeout=5) as r:
            return r.status == 200
    except (OSError, ValueError, http.client.HTTPException):
        return False


def port_taken(host: str | None, port: int) -> str | None:
    """What keeps vLLM from binding the port, asked the way vLLM binds it (SO_REUSEADDR, as uvicorn): "listens" (a
    program serves there), "held" (something has the port without listening: a connection's local end, or, under
    WSL's mirrored networking, a Windows program), or None (free)."""
    try:
        socket.create_connection((address(host), port), timeout=2).close()
        return "listens"
    except OSError:
        pass
    family, kind, proto, _, where = socket.getaddrinfo(host or "127.0.0.1", port, type=socket.SOCK_STREAM)[0]
    with socket.socket(family, kind, proto) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(where)
        except OSError:
            return "held"
    return None


# ---------------------------------------------------------------- vLLM's environment

def find_vllm() -> str | None:
    """The vllm executable: VLLM_SERVE_VLLM (None when that is no executable file), else the `vllm` uv tool, else
    vllm on PATH."""
    if named := os.environ.get("VLLM_SERVE_VLLM"):
        return named if os.path.isfile(named) and os.access(named, os.X_OK) else None
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


def unversioned_links(cuda: Path) -> Path:
    """A directory of unversioned library names pointing into the environment's toolkit (libcublas.so ->
    .../libcublas.so.13). FlashInfer's autotuner dlopens "libcublas.so"; the pip toolkit ships only versioned
    names, so the system loader cache answered with the system toolkit's cuBLAS (2026-10)."""
    d = state_dir() / "cuda-links" / hashlib.sha1(str(cuda).encode()).hexdigest()[:12]
    d.mkdir(parents=True, exist_ok=True)
    for lib in sorted((cuda / "lib").glob("lib*.so.*")):
        link = d / (lib.name.split(".so.", 1)[0] + ".so")
        if not link.is_symlink():
            try:
                link.symlink_to(lib)
            except FileExistsError:                     # another start made it a moment ago
                pass
    return d


def server_env(base: dict, profile: dict, offline: bool, cuda: Path | None = None, venv_bin: Path | None = None,
               links: Path | None = None) -> dict:
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
    # Run as if the environment were activated: its own tools (ninja, which FlashInfer's kernel builds call) and
    # its CUDA compiler come first.
    env["PATH"] = ":".join([*(str(d) for d in (cuda / "bin" if cuda else None, venv_bin) if d), env.get("PATH", "")])
    if offline:
        env.setdefault("HF_HUB_OFFLINE", "1")   # the weights are in the cache: start without asking the Hub
    env.update({k: str(v) for k, v in profile["env"].items()})
    return env


def hub_cached(model: str, revision: str | None = None, env: dict | None = None) -> bool:
    """Whether the Hugging Face cache that `env` (default: this process's) points at holds this revision of the
    model (a commit hash, a branch or tag, else main) in the form an offline vLLM loads: a branch needs its refs/
    entry, a commit hash only its snapshot."""
    env = os.environ if env is None else env
    hub = env.get("HF_HUB_CACHE") or Path(env.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    repo = Path(hub) / f"models--{model.replace('/', '--')}"
    commit = revision or "main"
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        try:
            commit = (repo / "refs" / commit).read_text().strip()
        except OSError:
            return False
    return (repo / "snapshots" / commit / "config.json").exists()


def foreign_cuda(maps: str, env_root: Path) -> set[str]:
    """CUDA libraries in a /proc/<pid>/maps text that come from outside vLLM's environment (the driver's libcuda
    is not one of them): a system toolkit leaking in."""
    found = set()
    for line in maps.splitlines():
        parts = line.split(None, 5)
        if len(parts) == 6 and CUDA_LIBRARY.search(parts[5]) and not parts[5].startswith(f"{env_root}/"):
            found.add(parts[5])
    return found


def server_foreign_cuda(state: dict, vllm: str) -> list[str]:
    """foreign_cuda over every process of a running server (vLLM's process group)."""
    env_root, found = Path(vllm).resolve().parent.parent, set()
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            if int((proc / "stat").read_text().rsplit(")", 1)[1].split()[2]) == state.get("vllm_pid"):
                found |= foreign_cuda((proc / "maps").read_text(), env_root)
        except (OSError, ValueError, IndexError):
            continue
    return sorted(found)


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


def metrics(host: str | None, port: int, timeout: float = 10) -> dict | None:
    try:
        with LOCAL.open(url(host, port, "/metrics"), timeout=timeout) as r:
            return parse_metrics(r.read().decode())
    except (OSError, ValueError, http.client.HTTPException):
        return None


# ---------------------------------------------------------------- up

def log_tail(name: str, lines: int = 20) -> str:
    try:
        return "\n".join(log_path(name).read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def failed(name: str, phase: str) -> Failure:
    return Failure("server_failed", f"{name}'s supervisor exited while {phase}; {log_path(name)} ends:\n{log_tail(name)}",
                   f"Read the log for the cause, then {GUIDE}, \"A server that does not start, or loads foreign CUDA\".")


def start_supervisor(name: str, profile: dict, extra: list[str]) -> dict:
    """Start the profile's supervisor (under the decision lock) and return its state once it holds its run lock;
    server_failed when it exits first."""
    last, previous = last_start(name), state_dir() / f"{name}.prev.log"
    if log_path(name).exists():
        os.replace(log_path(name), previous)
    (state_dir() / f"{name}.json").unlink(missing_ok=True)
    if last and last["failed"]:
        print(f"[vllm-serve] the last start of {name} failed ({last['ended']}, {last['at']}); its log: {previous}",
              file=sys.stderr, flush=True)
    print(f"[vllm-serve] starting {name} ({profile['model']}) on port {profile['port']}; log: {log_path(name)}",
          file=sys.stderr, flush=True)
    with open(log_path(name), "wb") as log:
        supervisor = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", name, "--", *extra],
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    while supervisor.poll() is None:
        if (state := read_state(name)) and state.get("pid") == supervisor.pid:
            return state
        time.sleep(0.1)
    if (state := live(name)) is not None:              # another supervisor holds the run lock: an `up` killed
        return state                                    # while it started one
    raise failed(name, "starting")


def wait_ready(name: str, state: dict, told: bool) -> dict:
    """Wait, outside the lock and with no deadline, until the server answers at the address its state names, and
    return that state; server_failed when the supervisor exits first (a failed start, or `down`)."""
    phase = state["phase"]
    while not healthy(state["host"], state["port"]):
        if not held(name):
            raise failed(name, phase)
        if not told:
            print(f"[vllm-serve] waiting for {name}, {phase}; log: {log_path(name)}", file=sys.stderr, flush=True)
            told = True
        time.sleep(2)
        if (now := read_state(name) or {}).get("pid"):  # a live state, not the record of how it ended
            state = now
        phase = phase if state["phase"] == "stopping" else state["phase"]     # the phase it was stopped in
    return state


def reply(name: str, state: dict, want: dict, started: bool, vllm: str | None) -> dict:
    out = {"profile": name, "code": "ok", "url": url(state["host"], state["port"]), "model": state["model"],
           "started": started}
    if state["host"] not in LOOPBACK:
        out["host"] = state["host"]
    if differs := {k: state.get(k) for k in ("model", "port", "args", "cuda_visible_devices") if state.get(k) != want[k]}:
        out["differs"] = differs
    if started and (foreign := server_foreign_cuda(state, vllm)):
        out["foreign_cuda"] = foreign
    return out


def up(name: str, extra: list[str]) -> dict:
    profile = load_profile(name)
    want = launch(profile, extra)
    started = told = False
    vllm = None
    while True:
        with deciding():
            state = live(name)
            if state is None:
                holder = next((n for n in running_names() if n != name and (read_state(n) or {}).get("port") == profile["port"]), None)
                if holder:
                    raise Failure("port_busy", f"port {profile['port']} is held by profile {holder}'s server",
                                  f"`{SELF} status` names it: use that profile, or `down` it once idle.")
                taken, port = port_taken(want["host"], profile["port"]), profile["port"]
                if taken == "listens":
                    raise Failure("port_busy", f"another program listens on port {port}",
                                  f"`ss -ltnp | grep :{port}` names it.")
                if taken == "held":
                    raise Failure("port_busy", f"port {port} is in use, though nothing listens on it",
                                  f"`ss -tanp | grep :{port}` names what holds it; under WSL's mirrored networking it "
                                  f"may be a Windows program (`netstat -ano | findstr :{port}` there). Wait until it "
                                  "lets go, or give the profile another port (an `extends` profile in "
                                  "~/.config/vllm-serve/profiles/).")
                if not (vllm := find_vllm()):
                    named = os.environ.get("VLLM_SERVE_VLLM")
                    raise Failure("vllm_missing", f"VLLM_SERVE_VLLM names {named}, which is not an executable file" if named else
                                  "no vllm executable", f"Install vLLM per {GUIDE}" + (", or point VLLM_SERVE_VLLM at "
                                  "its vllm, or unset it." if named else "."), exit=CANNOT)
                state, started, told = start_supervisor(name, profile, extra), True, True
        if not state or state.get("phase") == "stopping":       # on its way out: decide again once it is gone
            time.sleep(1)
            continue
        state, told = wait_ready(name, state, told), True
        with deciding():
            now = live(name)
            if now and now.get("pid") == state["pid"] and now.get("phase") != "stopping":
                touch(name)
                return reply(name, now, want, started, vllm)


# ---------------------------------------------------------------- the supervisor

def die_with_parent() -> None:
    """Runs in a child before it execs: SIGTERM it when the supervisor dies, even by SIGKILL."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)      # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def spawn(cmd: list[str], env: dict | None = None) -> subprocess.Popen:
    """A child in a process group of its own, for stop(), that dies with the supervisor."""
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, env=env, start_new_session=True,
                            preexec_fn=die_with_parent if sys.platform == "linux" else None)


def stop(proc: subprocess.Popen) -> None:
    """SIGTERM the child's process group (vLLM runs its engines in children), SIGKILL whatever is left of it after
    30 s, and return once the whole group is gone, so its GPU memory and port are free."""
    for sig, grace in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        deadline = time.time() + grace
        while time.time() < deadline:
            proc.poll()                                 # reaps the leader, which killpg would still count
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.2)


def supervise(name: str, extra: list[str]) -> int:
    """One start of the profile, from download to stop: download the weights if the cache lacks them, run vLLM
    until it has been idle for idle_minutes, it exits, `down` stops it, or it has not answered within START_LIMIT.
    How it ended is the log's last line and the state it leaves."""
    ending = {"why": "serve.py raised an error (its traceback follows)", "failed": True}

    def end(why: str, failed: bool = True) -> int:
        ending.update(why=why, failed=failed)
        return 1 if failed else 0

    def on_sigterm(*_) -> None:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)   # a second `down` does not cut the stop short
        end("stopped by SIGTERM (serve.py down, or the system)", failed=False)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_sigterm)
    lock = open(state_dir() / f"{name}.run", "a")       # held until this process exits; children never get it
    for _ in range(20):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:                         # a moment's check by held(), or another supervisor
            time.sleep(0.1)
    else:
        print(f"[vllm-serve] another supervisor runs {name}", flush=True)
        return 1
    child, state = None, {}
    try:
        profile, vllm = load_profile(name), find_vllm()
        run = launch(profile, extra)
        start_env = {**os.environ, **{k: str(v) for k, v in profile["env"].items()}}
        revision = arg_value(run["args"], "--revision")
        download = not local_model(profile) and not hub_cached(profile["model"], revision, start_env)
        state.update(pid=os.getpid(), owner=login(), since=time.time(), phase="downloading" if download else "starting",
                     idle_minutes=profile["idle_minutes"], **run)
        write_state(name, state)
        if download:
            hf = Path(vllm).resolve().parent / "hf"
            cmd = [str(hf) if hf.exists() else (shutil.which("hf") or "hf"), "download", profile["model"],
                   *(["--revision", revision] if revision else [])]
            print(f"[vllm-serve] {' '.join(cmd)}", flush=True)
            try:
                child = spawn(cmd, start_env)
            except OSError as e:
                return end(f"cannot run {cmd[0]}: {e}")
            if child.wait():
                return end(f"the download exited with {child.returncode}")
            state["phase"] = "starting"
        cuda = own_cuda(vllm)
        offline = not local_model(profile) and hub_cached(profile["model"], revision, start_env)
        env = server_env(dict(os.environ), profile, offline, cuda, Path(vllm).resolve().parent,
                         unversioned_links(cuda) if cuda else None)
        child, since = spawn([vllm, "serve", *run["args"]], env), time.time()
        state["vllm_pid"] = child.pid
        write_state(name, state)
        idle = load = None
        limit = profile["idle_minutes"] * 60
        while child.poll() is None:
            if idle is None:                            # the idle clock starts when the server first answers
                if not healthy(run["host"], run["port"]):
                    if time.time() - since > START_LIMIT:
                        return end(f"vLLM has not answered {START_LIMIT / 60:g} min after its start")
                    time.sleep(min(TICK, 2))
                    continue
                idle, load = Idle(time.time()), Load()
                state.update(phase="running", idle_seconds=0)
                write_state(name, state)
            time.sleep(TICK)
            now, m = time.time(), metrics(run["host"], run["port"])
            seconds = idle.update(now, m, touched(name))
            state.update(idle_seconds=round(seconds), **({"load": load.update(now, m)} if m else {}))
            write_state(name, state)
            if seconds >= limit:
                with deciding():                        # no `up` hands the server out once it is stopping
                    if idle.update(time.time(), metrics(run["host"], run["port"], timeout=2), touched(name)) >= limit:
                        state["phase"] = "stopping"
                        write_state(name, state)
                if state["phase"] == "stopping":
                    return end(f"idle for {profile['idle_minutes']} min", failed=False)
        return end(f"vLLM exited with {child.returncode}")
    except Failure as e:
        return end(f"{e.code}: {e.detail}")
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if state.get("phase") != "stopping" and state.get("pid"):
            with deciding():                            # from here on no `up` is handed this server
                state["phase"] = "stopping"
                write_state(name, state)
        if child:
            stop(child)
        print(f"[vllm-serve] ended: {ending['why']}" + (f"; the cause stands above, and {GUIDE} (\"A server that does not "
              f"start, or loads foreign CUDA\") lists the known ones" if ending["failed"] else ""), flush=True)
        write_state(name, {"phase": "stopped", **ending})


# ---------------------------------------------------------------- down and status

def down(name: str) -> dict:
    with deciding():
        state = live(name)
        if state is None:
            profile_path(name)                          # a name that is neither running nor a profile: unknown_profile
            return {"profile": name, "code": "skipped", "reason": "not_running"}
        if pid := state.get("pid"):
            try:
                os.kill(pid, signal.SIGTERM)
                write_state(name, {**state, "phase": "stopping"})   # no `up` is handed it from now on
            except PermissionError:
                raise Failure("not_permitted", f"{name}'s server (pid {pid}) was started by "
                                               f"{state.get('owner', 'another login')}",
                              f"That login stops it, or it stops by itself after {state.get('idle_minutes')} min idle."
                              ) from None
            except ProcessLookupError:
                pass
    for _ in range(90):                                 # until the supervisor signalled is gone, even if a new
        now = live(name)                                # `up` has started another meanwhile
        if now is None or now.get("pid") not in (None, state.get("pid")):
            return {"profile": name, "code": "ok"}
        time.sleep(1)
    return {"profile": name, "code": "still_stopping", "hint": f"`{SELF} status {name}` shows when it is gone."}


def status(name: str) -> dict:
    state = live(name)
    if state is None:
        profile = load_profile(name)
        out = {"profile": name, "phase": "stopped", "model": profile["model"],
               "url": url(launch(profile, [])["host"], profile["port"])}
        if last := last_start(name):
            out["last"] = last
    else:
        out = {"profile": name, "phase": state.get("phase", "starting")}
        if state.get("pid"):
            out.update(model=state["model"], url=url(state["host"], state["port"]), pid=state["pid"],
                       owner=state.get("owner"), gpus=state.get("cuda_visible_devices"))
            if state["host"] not in LOOPBACK:
                out["host"] = state["host"]
            if state["phase"] == "running":
                out.update(idle_for_minutes=round(state.get("idle_seconds", 0) / 60, 1),
                           stops_after_minutes=state["idle_minutes"])
            if "load" in state:
                out["load"] = state["load"]
    out["log"] = str(log_path(name))
    return out



# ---------------------------------------------------------------- the words

UP = """Start the profile's server unless it runs, wait until it answers, and print where it is.

up waits with no deadline of its own, until the server answers or its start fails; concurrent ups share one server,
and each counts as a request. What follows the profile goes to `vllm serve` as it is, for this start only, as
timeout or torchrun hand on their command's arguments (a -- right after the profile is allowed); so does the
caller's environment (CUDA_VISIBLE_DEVICES picks the GPUs), except variables the profile's env sets.

stdout, one line: {profile, code: ok, url, model, started}. Clients speak the OpenAI API at url, with model as the
model name; started says whether this up started the server. The line may add
  host          the server listens beyond this machine: clients elsewhere use the machine's address and url's port
  differs       where the running server differs from what this up asks for (model, port, args,
                cuda_visible_devices); it serves as it is
  foreign_cuda  CUDA libraries a freshly started server mapped from outside vLLM's environment; there should be none
A profile that cannot be served is one line {profile, code, detail, hint}:
  unknown_profile  no such profile, or its file is broken
  port_busy        another profile's server, or another program, holds the port
  server_failed    the supervisor exited before the server answered: the phase, the log and its last 20 lines
stderr: while a start is under way, "[vllm-serve] starting ..." or "[vllm-serve] waiting for ..." with the log's
path, and a warning when the profile's last start failed; empty when the server was running.

Exit 0 served; 1 not served, the line's code says why; 2 nothing tried, stdout empty: stderr's last line is
{code, detail, hint}, the code vllm_missing (no vllm executable), not_permitted (a state file of another login) or
usage.

Examples:
  serve.py up paddleocr-vl
  CUDA_VISIBLE_DEVICES=4,5 serve.py up qwen38-27b --data-parallel-size 2
"""

DOWN = """Stop profiles' servers now, in whatever phase, waiting up to 90 s for each to end.

A running server is shared: down cuts off whoever is using it.

stdout, one line per profile, as each ends:
  {profile, code: ok}                             stopped
  {profile, code: skipped, reason: not_running}   it was not running
  {profile, code: still_stopping, hint}           still ending after 90 s
  {profile, code: unknown_profile, detail, hint}  no such profile
  {profile, code: not_permitted, detail, hint}    a server another login started
A JSON line read through - that names no profile is passed on as it is when its code reports a skip or a failure
upstream; any other such line makes the list unreadable (invalid_list).

Exit 0 every line ok or skipped, stderr empty; an empty list read through - is nothing to do. 1 another code:
stderr's last line is {"summary": ...}. 2 a usage error, a list it cannot read (nothing done), or a state file of
another login: stderr's last line is {code, detail, hint}, and each profile left is a not_run line.

Examples:
  serve.py down paddleocr-vl
  serve.py status | jq -c 'select(.phase == "running" and .idle_for_minutes >= 30)' | serve.py down -
"""

STATUS = """List profiles, one line each: every profile configured or running, or the ones named.

stdout fields:
  profile, model, url, log
  phase                downloading, starting, running, stopping or stopped
  pid, owner, gpus     a live server: its supervisor, the login that started it, its CUDA_VISIBLE_DEVICES
  host                 the server listens beyond this machine
  idle_for_minutes     a running server: minutes since its last request; it stops at stops_after_minutes
  load                 a running server, read from its metrics every 30 s: running and waiting requests,
                       kv_cache_usage, prefix_cache_hit_rate, preemptions, prompt_tokens_per_s,
                       generation_tokens_per_s
  last                 a stopped profile: how its last start ended, {ended, failed, at}; failed: true is a failure
                       that may have gone unseen
A profile whose file is broken, or a name no profile has, is {profile, code: unknown_profile, detail, hint}.

Exit 0 all listed, also when there is none; 1 a line is unknown_profile: stderr's last line is {"summary": ...};
2 a usage error.

Examples:
  serve.py status paddleocr-vl
  serve.py status | jq -c 'select(.phase != "stopped")'
"""


def split(argv: list[str]) -> tuple[list[str], list[str]]:
    """argv cut at its first `--`: what comes before it, and what comes after, which goes to vLLM as it is. Cut
    before parsing: argparse alone takes `up p extra` as a vLLM argument and `up -- p` as the profile."""
    if "--" not in argv:
        return argv, []
    return argv[:argv.index("--")], argv[argv.index("--") + 1:]


def at_profile(argv: list[str]) -> tuple[list[str], list[str]]:
    """up's argv cut at the profile, as timeout or torchrun cut at their command: up's own options and the profile,
    then what follows it, for vLLM as it is. A -- before the profile ends up's options; one right after it is dropped."""
    for i, arg in enumerate(argv):
        if arg == "--" or not arg.startswith("-"):
            rest = argv[i + 1:] if arg == "--" else argv[i:]
            own, after = argv[:i] + rest[:1], rest[1:]
            return own, after[1:] if after[:1] == ["--"] else after
    return argv, []


def up_word(argv: list[str]) -> int:
    left, extra = at_profile(argv)
    p = parser(UP, "up", usage=f"{SELF} up [-h] PROFILE [VLLM_ARG ...]")
    p.add_argument("profile", nargs="?", metavar="PROFILE", help="a profile's name")
    args = p.parse_args(left)
    if args.profile is None:
        p.error("name a profile")
    try:
        emit(up(args.profile, extra))
        return OK
    except Failure as e:
        emit(e.line() if e.exit == CANNOT else e.line(args.profile), sys.stderr if e.exit == CANNOT else None)
        return e.exit


def down_word(argv: list[str]) -> int:
    p = parser(DOWN, "down")
    p.add_argument("profiles", nargs="*", metavar="PROFILE",
                   help="a profile's name; - reads a list from stdin: a name a line, or the JSON lines status, up "
                        "and down print, by their profile")
    p.add_argument("-a", "--all", action="store_true", help="every profile, configured or running")
    args = p.parse_intermixed_args(argv)
    if args.all and args.profiles:
        p.error("-a stops every profile: name none beside it")
    if not args.all and not args.profiles:
        p.error("name the profiles, - to read them from stdin, or -a for all")
    try:
        named = sorted({*profile_names(), *running_names()}) if args.all else names(args.profiles)
    except Failure as e:
        emit(e.line(), sys.stderr)
        return e.exit
    out = Lines()
    for name in named:
        out.put(name) if isinstance(name, dict) else out.add(name, lambda: down(name))
    return out.finish()


def status_word(argv: list[str]) -> int:
    p = parser(STATUS, "status")
    p.add_argument("profiles", nargs="*", metavar="PROFILE", help="a profile's name; none: every profile")
    args = p.parse_intermixed_args(argv)
    out = Lines()
    for name in args.profiles or sorted({*profile_names(), *running_names()}):
        out.add(name, lambda: status(name))
    return out.finish()


# ---------------------------------------------------------------- output and the command line
# write, emit, the usage error, the word listing, names() and Lines: copied from
# paper-to-zotero/scripts/p2zlib/cli.py at 8b0a0cd and cut to serve.py's use: a line is about a profile, and a
# status line, which carries no code, counts as ok.

def write(text: str) -> None:
    """Text to stdout. Once the reader has closed the pipe, stdout goes to /dev/null and the work goes on."""
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
            os.close(fd)
        except (OSError, ValueError):
            pass


def emit(obj: dict, stream=None) -> None:
    """One JSON line: to stdout (write), or to `stream`."""
    text = json.dumps(obj, ensure_ascii=False) + "\n"
    if stream is None:
        write(text)
    else:
        stream.write(text)
        stream.flush()


class Parser(argparse.ArgumentParser):
    def error(self, message, hint=None):
        """A usage error: the usage line, then {code: usage, detail, hint} as stderr's last line; exit 2."""
        self.print_usage(sys.stderr)
        emit({"code": "usage", "detail": message, "hint": hint or f"See {self.prog} -h."}, sys.stderr)
        raise SystemExit(CANNOT)


def parser(doc: str, word: str, usage: str | None = None) -> Parser:
    """A word's parser, whose -h is its man page: the doc's first line, the options, then the rest."""
    first, _, rest = doc.strip().partition("\n")
    return Parser(prog=f"{SELF} {word}", usage=usage, description=first, epilog=rest.strip(),
                  formatter_class=argparse.RawDescriptionHelpFormatter)


def listing() -> str:
    first, _, rest = __doc__.strip().partition("\n")
    width = max(map(len, WORDS)) + 2
    words = "\n".join(f"  {word:<{width}}{text}" for word, (_, text) in WORDS.items())
    return f"usage: {SELF} WORD [options] [operands]   ({SELF} WORD -h for each)\n\n{first}\n\nwords:\n{words}\n\n{rest.strip()}\n"


def names(values: list[str]) -> list:
    """The profiles named after the options, `-` read from stdin as a list: a line is a name, or one of our JSON
    lines, which names its profile by `profile`. A JSON line without it is passed on as it is (a dict) when its code
    reports a skip or a failure upstream (any code but ok); any other stops the command before anything is done."""
    out = []
    for value in values:
        if value != "-":
            out.append(value)
            continue
        for n, line in enumerate((x.strip() for x in sys.stdin.read().splitlines() if x.strip()), 1):
            if not line.startswith("{"):
                out.append(line)
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("profile"), str) and obj["profile"].strip():
                out.append(obj["profile"].strip())
            elif isinstance(obj, dict) and isinstance(obj.get("code"), str) and obj["code"] != "ok":
                out.append(obj)
            else:
                raise Failure("invalid_list", f"stdin line {n}: {line[:200]}",
                              "A list holds one profile a line: a name, or a JSON line with `profile` (what status, "
                              "up and down print). Nothing was done.", exit=CANNOT)
    return out


def not_permitted(e: PermissionError) -> Failure:
    """A file in the state directory that another login owns: the command cannot go on."""
    owner = ""
    try:
        owner = f" (owned by {Path(e.filename).owner()})" if e.filename else ""
    except (OSError, KeyError):
        pass
    return Failure("not_permitted", f"{e}{owner}", "The owner hands it over, e.g. `chown -R`.", exit=CANNOT)


class Lines:
    """The lines of a word over several profiles, printed as they come. add(name, fn) prints fn()'s line, or the
    line of the Failure it raised; after one that stops the command, that profile and every later one are not_run.
    finish() -> the exit code, after the summary (exit 1) or the stop (exit 2) on stderr."""

    def __init__(self):
        self.counts = {"total": 0, "ok": 0, "skipped": 0, "failed": 0}
        self.stopped: Failure | None = None

    def put(self, line: dict) -> None:
        code = line.get("code", "ok")
        self.counts["total"] += 1
        self.counts[code if code in ("ok", "skipped") else "failed"] += 1
        emit(line)

    def add(self, name: str, fn) -> None:
        if self.stopped is None:
            try:
                return self.put(fn())
            except PermissionError as e:
                self.stopped = not_permitted(e)
            except Failure as e:
                if e.exit != CANNOT:
                    return self.put(e.line(name))
                self.stopped = e
        self.put({"profile": name, "code": "not_run"})

    def finish(self) -> int:
        if self.stopped is not None:
            emit(self.stopped.line(), sys.stderr)
            return CANNOT
        if self.counts["failed"]:
            emit({"summary": self.counts}, sys.stderr)
            return ACT
        return OK


WORD_RUNS = {"up": up_word, "down": down_word, "status": status_word}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    word = argv[0] if argv else None
    if word == "_supervise":            # up's own call when it starts a server: serve.py _supervise PROFILE -- ARG ...
        left, extra = split(argv[1:])
        return supervise(left[0], extra)
    if word in ("-h", "--help"):
        write(listing())
        return OK
    if word not in WORDS:
        sys.stderr.write(listing())
        emit({"code": "usage", "detail": f"no word {word!r}" if word else "name a word", "hint": f"See {SELF} -h."},
             sys.stderr)
        return CANNOT
    try:
        return WORD_RUNS[word](argv[1:])
    except PermissionError as e:
        emit(not_permitted(e).line(), sys.stderr)
        return CANNOT


if __name__ == "__main__":
    sys.exit(main())
