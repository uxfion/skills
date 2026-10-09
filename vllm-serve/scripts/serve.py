# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Serve models on this machine's GPU through one shared vLLM installation, one server per model profile.

  serve.py up PROFILE        start the profile's server unless it already runs, wait until it answers, and
                             print {"profile", "url", "model", "started"}; concurrent calls share one server
  serve.py down PROFILE      stop it now (--all: every profile)
  serve.py status            one JSON line per profile: running, url, pid, idle_minutes, log

A server stops by itself once it has had no request for the profile's idle_minutes, so the GPU is free
for other work; `up` counts as a request. Clients speak the OpenAI API at the url, with the model name
given.

Profiles: <name>.toml in ~/.config/vllm-serve/profiles/ (XDG_CONFIG_HOME), then in profiles/ beside this
script. Keys: model (Hugging Face id or local directory), port, gpu_memory_utilization (share of the
GPU's total memory), idle_minutes (default 10), args (more `vllm serve` arguments), env.
The vllm executable: VLLM_SERVE_VLLM, else the `vllm` uv tool, else vllm on PATH.
State and logs: ~/.local/state/vllm-serve/ (XDG_STATE_HOME), <profile>.log per server.

`up` also reports "foreign_cuda": CUDA libraries a freshly started server mapped from outside vLLM's
environment, such as a system toolkit's; there should be none.

Errors, one JSON line on stdout with exit 2: unknown_profile, vllm_missing, port_busy (another program
holds the port), gpu_busy (too little free GPU memory; lists who holds it), download_failed,
server_failed (with the end of the log).
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import urllib.request
from contextlib import contextmanager
from pathlib import Path

SKILL_PROFILES = Path(__file__).resolve().parent.parent / "profiles"
STARTUP_TIMEOUT = 300    # seconds from launch until the server must answer (a model download comes before)
TICK = float(os.environ.get("VLLM_SERVE_TICK", 30))   # seconds between idle checks
# Settings every server gets (2026-10, WSL2 + RTX 50, vLLM 0.31); a profile's env overrides them. Pinned memory is
# off under WSL by default (0.28 then stopped with "UVA is not available"; 0.31 runs slower without it).
# FlashInfer's sampler compiles its kernels on first use, and the pip CUDA toolkit cannot link them (no lib64,
# no libcudart.so, no stubs/libcuda.so); vLLM samples with PyTorch instead. A profile that needs FlashInfer's
# sampler sets it to 1 and the environment gets FlashInfer's prebuilt flashinfer-jit-cache.
MACHINE_ENV = {"VLLM_WSL2_ENABLE_PIN_MEMORY": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0"}
CUDA_LIBRARY = re.compile(r"/lib(cudart|cublas|cublasLt|cudnn\w*|nvrtc|nccl|cufft|curand|cusolver|cusparse)\.so")


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


def load_profile(name: str) -> dict:
    for d in profile_dirs():
        path = d / f"{name}.toml"
        if path.is_file():
            p = tomllib.loads(path.read_text(encoding="utf-8"))
            missing = [k for k in ("model", "port", "gpu_memory_utilization") if k not in p]
            if missing:
                raise Failure("unknown_profile", f"{path} lacks {', '.join(missing)}")
            return {"name": name, "idle_minutes": 10, "args": [], "env": {}, **p, "path": str(path)}
    raise Failure("unknown_profile", f"no {name}.toml in {', '.join(map(str, profile_dirs()))}; "
                                     f"profiles: {', '.join(profile_names()) or 'none'}")


def state_dir() -> Path:
    d = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "vllm-serve"
    d.mkdir(parents=True, exist_ok=True)
    return d


def url_of(profile: dict) -> str:
    return f"http://127.0.0.1:{profile['port']}/v1"


@contextmanager
def locked(name: str):
    """The profile's lock: held by `up` from its health check until the server answers, by `down`, and by the
    supervisor while it decides to stop, so a caller never gets a server that is starting or stopping."""
    with open(state_dir() / f"{name}.lock", "w") as f:
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
    except PermissionError:
        return True


# ---------------------------------------------------------------- vLLM

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


def vllm_command(vllm: str, profile: dict) -> list[str]:
    return [vllm, "serve", str(Path(profile["model"]).expanduser()) if local_model(profile) else profile["model"],
            "--served-model-name", profile["model"], "--host", "127.0.0.1", "--port", str(profile["port"]),
            "--gpu-memory-utilization", str(profile["gpu_memory_utilization"]), *map(str, profile["args"])]


def without_cuda_toolkit(path: str) -> str | None:
    """LD_LIBRARY_PATH minus directories holding a CUDA runtime: vLLM's PyTorch brings its own, and a system
    toolkit ahead of it gets loaded beside it (2026-10). None when nothing is left."""
    kept = [d for d in path.split(":") if not (d and glob.glob(os.path.join(glob.escape(d), "libcudart.so*")))]
    return ":".join(kept) if any(kept) else None


def own_cuda(vllm: str) -> Path | None:
    """The CUDA toolkit inside vLLM's environment (site-packages/nvidia/cu13 with bin/nvcc, include, lib), the
    newest if several; None when the environment has none."""
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
            link.symlink_to(lib)
    return d


def server_env(base: dict, profile: dict, offline: bool, cuda: Path | None = None, venv_bin: Path | None = None,
               links: Path | None = None) -> dict:
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
    # Run as if the environment were activated: its own tools (ninja, which FlashInfer's kernel builds call) and
    # its CUDA compiler come first.
    env["PATH"] = ":".join([*(str(d) for d in (cuda / "bin" if cuda else None, venv_bin) if d), env.get("PATH", "")])
    if offline:
        env.setdefault("HF_HUB_OFFLINE", "1")   # the weights are in the cache: start without asking the Hub
    env.update({k: str(v) for k, v in profile["env"].items()})
    return env


def local_model(profile: dict) -> bool:
    return Path(profile["model"]).expanduser().is_dir()


def hub_cached(model: str) -> bool:
    """Whether a Hugging Face model's weights are in the local cache."""
    hub = os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"
    snapshots = Path(hub) / f"models--{model.replace('/', '--')}" / "snapshots"
    return any((s / "config.json").exists() for s in snapshots.glob("*")) if snapshots.is_dir() else False


def ensure_weights(profile: dict, vllm: str) -> None:
    """Download a Hub model before the server starts, so the download does not count against its start-up time."""
    if local_model(profile) or hub_cached(profile["model"]):
        return
    hf = Path(vllm).resolve().parent / "hf"
    cmd = [str(hf) if hf.exists() else (shutil.which("hf") or "hf"), "download", profile["model"]]
    print(f"[vllm-serve] downloading {profile['model']} ...", file=sys.stderr, flush=True)
    try:
        done = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except OSError as e:
        raise Failure("download_failed", f"cannot run {cmd[0]}: {e}") from e
    if done.returncode:
        raise Failure("download_failed", done.stderr.strip()[-2000:])


def check_gpu(profile: dict) -> None:
    """Fail with gpu_busy when the GPU lacks the free memory the profile asks for (vLLM would fail later and
    less clearly). Skipped when nvidia-smi is absent."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, check=True).stdout.split("\n")[0]
    except (OSError, subprocess.CalledProcessError):
        return
    total, free = (int(v) for v in out.split(","))
    need = profile["gpu_memory_utilization"] * total
    if free < need:
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
                              capture_output=True, text=True).stdout.strip()
        raise Failure("gpu_busy", f"{profile['name']} needs {need:.0f} MiB of {total} MiB, {free} MiB free; "
                                  f"holding GPU memory: {apps or 'not listed by nvidia-smi (WSL lists none)'}")


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


def answers(profile: dict) -> bool | None:
    """True: the profile's model answers on its port; False: something else does; None: nothing does."""
    try:
        with urllib.request.urlopen(url_of(profile) + "/models", timeout=5) as r:
            ids = [m.get("id") for m in json.load(r).get("data", [])]
        return profile["model"] in ids
    except (OSError, ValueError):
        return None


def log_tail(name: str, lines: int = 20) -> str:
    try:
        return "\n".join((state_dir() / f"{name}.log").read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


# ---------------------------------------------------------------- idle tracking

def request_counts(metrics: str) -> tuple[float, float]:
    """(requests running or waiting, requests finished so far) from vLLM's Prometheus /metrics text."""
    active = done = 0.0
    for line in metrics.splitlines():
        name = line.split("{", 1)[0].split(" ", 1)[0]
        if name in ("vllm:num_requests_running", "vllm:num_requests_waiting"):
            active += float(line.rsplit(" ", 1)[1])
        elif name == "vllm:request_success_total":
            done += float(line.rsplit(" ", 1)[1])
    return active, done


class Idle:
    """Seconds since the server last had work: a request running or waiting, a request finished, or an `up`."""

    def __init__(self, now: float):
        self.last, self.done, self.touched = now, None, 0.0

    def update(self, now: float, active: float | None, done: float | None, touched: float) -> float:
        if active or (done is not None and done != self.done) or touched > self.touched:
            self.last = now
        self.done = done if done is not None else self.done
        self.touched = max(self.touched, touched)
        return now - self.last


def touch(name: str) -> None:
    (state_dir() / f"{name}.touch").write_text(str(time.time()))


def touched(name: str) -> float:
    try:
        return (state_dir() / f"{name}.touch").stat().st_mtime
    except OSError:
        return 0.0


def metrics(profile: dict) -> tuple[float | None, float | None]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{profile['port']}/metrics", timeout=10) as r:
            return request_counts(r.read().decode())
    except (OSError, ValueError):
        return None, None


# ---------------------------------------------------------------- commands

def up(name: str) -> dict:
    profile = load_profile(name)
    with locked(name):
        state = read_state(name)
        deadline = time.time() + STARTUP_TIMEOUT
        while state and alive(state.get("pid")) and answers(profile) is None and time.time() < deadline:
            time.sleep(2)               # a server still starting: the `up` that launched it was interrupted
        found = answers(profile)
        if found:                       # supervised here, or started by hand on the profile's port
            touch(name)
            return {"profile": name, "url": url_of(profile), "model": profile["model"], "started": False}
        if found is False:
            raise Failure("port_busy", f"port {profile['port']} answers with another model; `curl {url_of(profile)}/models`")
        if state and alive(state.get("pid")):
            raise Failure("server_failed", f"{name}'s supervisor (pid {state['pid']}) runs but its server never answered; "
                                           f"`serve.py down {name}`; the log ends:\n{log_tail(name)}")
        vllm = find_vllm()
        if not vllm:
            raise Failure("vllm_missing", "no vllm executable; see references/install.md")
        ensure_weights(profile, vllm)
        check_gpu(profile)
        print(f"[vllm-serve] starting {name} ({profile['model']}) on port {profile['port']} ...", file=sys.stderr, flush=True)
        log = open(state_dir() / f"{name}.log", "wb")
        supervisor = subprocess.Popen([sys.executable, os.path.abspath(__file__), "_supervise", name],
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        log.close()
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline and supervisor.poll() is None:
            if answers(profile):
                touch(name)
                out = {"profile": name, "url": url_of(profile), "model": profile["model"], "started": True}
                if foreign := server_foreign_cuda(name, vllm):
                    out["foreign_cuda"] = foreign
                    print(f"[vllm-serve] {name}'s server loaded CUDA libraries from outside vLLM's environment: "
                          f"{', '.join(foreign)}; see references/install.md", file=sys.stderr, flush=True)
                return out
            time.sleep(2)
        how = "exited" if supervisor.poll() is not None else f"did not answer within {STARTUP_TIMEOUT} s"
        if supervisor.poll() is None:
            supervisor.terminate()
            supervisor.wait(60)
        raise Failure("server_failed", f"{name}'s server {how}; {state_dir() / (name + '.log')} ends:\n{log_tail(name)}")


def die_with_parent() -> None:
    """Runs in vLLM's process before it execs: SIGTERM it when the supervisor dies, even by SIGKILL."""
    try:
        import ctypes
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)      # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass


def stop(proc: subprocess.Popen) -> None:
    """SIGTERM vLLM's process group (it runs its engine in a child), SIGKILL whatever is left after 30 s."""
    for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(wait)
        except subprocess.TimeoutExpired:
            pass


def supervise(name: str) -> None:
    """Run the profile's vLLM server until it has been idle for idle_minutes, it exits, or `down` stops it."""
    profile = load_profile(name)
    vllm = find_vllm()
    offline = not local_model(profile) and hub_cached(profile["model"])
    cuda = own_cuda(vllm)
    env = server_env(dict(os.environ), profile, offline, cuda, Path(vllm).resolve().parent,
                     unversioned_links(cuda) if cuda else None)
    proc = subprocess.Popen(vllm_command(vllm, profile), stdin=subprocess.DEVNULL, env=env,
                            start_new_session=True, preexec_fn=die_with_parent if sys.platform == "linux" else None)
    path = state_dir() / f"{name}.json"
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    idle = Idle(time.time())
    try:
        path.write_text(json.dumps({"pid": os.getpid(), "vllm_pid": proc.pid, "port": profile["port"],
                                    "model": profile["model"], "since": time.time(), "idle_seconds": 0}))
        while proc.poll() is None:
            time.sleep(TICK)
            seconds = idle.update(time.time(), *metrics(profile), touched(name))
            state = json.loads(path.read_text())
            path.write_text(json.dumps({**state, "idle_seconds": round(seconds)}))
            if seconds >= profile["idle_minutes"] * 60:
                with locked(name):      # no `up` may hand out this server while it stops
                    if idle.update(time.time(), *metrics(profile), touched(name)) >= profile["idle_minutes"] * 60:
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
        os.kill(state["pid"], signal.SIGTERM)
        for _ in range(90):
            if not alive(state["pid"]) and answers(profile) is None:
                break
            time.sleep(1)
        return {"profile": name, "stopped": True}


def status(name: str) -> dict:
    profile = load_profile(name)
    state = read_state(name)
    running = bool(state and alive(state.get("pid")))
    out = {"profile": name, "model": profile["model"], "running": running, "url": url_of(profile)}
    if running:
        out.update(pid=state["pid"], idle_minutes=round(state.get("idle_seconds", 0) / 60, 1),
                   stops_after_minutes=profile["idle_minutes"])
    out["log"] = str(state_dir() / f"{name}.log")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("up").add_argument("profile")
    d = sub.add_parser("down")
    d.add_argument("profile", nargs="?")
    d.add_argument("--all", action="store_true")
    sub.add_parser("status")
    sub.add_parser("_supervise").add_argument("profile")
    args = p.parse_args(argv)
    try:
        if args.command == "_supervise":
            supervise(args.profile)
            return 0
        if args.command == "up":
            print(json.dumps(up(args.profile)), flush=True)
        elif args.command == "down":
            if not args.all and not args.profile:
                p.error("down needs a profile or --all")
            for name in profile_names() if args.all else [args.profile]:
                print(json.dumps(down(name)), flush=True)
        else:
            for name in profile_names():
                print(json.dumps(status(name)), flush=True)
    except Failure as e:
        print(json.dumps({"error": e.code, "detail": e.detail}), flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
