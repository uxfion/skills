"""What tests/check_conventions.py needs from vllm-serve: its help environment and four runtime cases against the
stand-in vllm (the check's docstring says what each must show)."""
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

from fakes import free_port, install

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "serve.py"
# Every -h runs here: config, state and vllm under /dev/null, where no directory can be made (by root neither), so a
# -h that reads any of them fails at once.
HELP_ENV = {"XDG_CONFIG_HOME": "/dev/null/config", "XDG_STATE_HOME": "/dev/null/state",
            "VLLM_SERVE_VLLM": "/dev/null/vllm"}
ENV = {}   # the environment the cases run in, kept for written()


def serve(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env={**os.environ, **ENV}, timeout=300)


@contextlib.contextmanager
def env(tmp):
    """The stand-in vllm; profiles on an empty local model directory: q1, w1-w3 and n1 each on a free port of its
    own, r000-r499 only files, never started."""
    install(tmp)
    (tmp / "model").mkdir()
    profiles = tmp / "config" / "vllm-serve" / "profiles"
    profiles.mkdir(parents=True)
    ports = set()
    while len(ports) < 5:
        ports.add(free_port())
    for name, port in zip(("q1", "w1", "w2", "w3", "n1"), sorted(ports)):
        (profiles / f"{name}.toml").write_text(f'model = "{tmp / "model"}"\nport = {port}\n')
    for i in range(500):
        (profiles / f"r{i:03d}.toml").write_text(f'model = "{tmp / "model"}"\nport = 1\n')
    ENV.clear()
    ENV.update(XDG_CONFIG_HOME=str(tmp / "config"), XDG_STATE_HOME=str(tmp / "state"),
               VLLM_SERVE_VLLM=str(tmp / "vllm"), FAKE_RECORD=str(tmp / "record.json"), VLLM_SERVE_TICK="0.5",
               no_proxy="127.0.0.1,localhost", NO_PROXY="127.0.0.1,localhost")   # a set http_proxy skips the fake
    try:
        yield dict(ENV)
    finally:
        serve("down", "-a")   # the stand-in servers left their session: stopped here, or they stay


def quiet(tmp):
    return {"run": "serve.py up q1 >/dev/null 2>&1; serve.py up q1", "lines": 1}


def reader(tmp):
    return {"run": "serve.py status"}


def writer(tmp):
    def written():
        lines = [json.loads(line) for line in serve("status", "w1", "w2", "w3").stdout.splitlines()]
        return len(lines) == 3 and all(line["phase"] == "stopped" for line in lines)

    return {"run": "for p in w1 w2 w3; do serve.py up $p >/dev/null 2>&1; done; "
                   "serve.py status w1 w2 w3 | serve.py down -", "written": written}


def no_service(tmp):
    return {"run": f"VLLM_SERVE_VLLM={tmp / 'no-vllm'} serve.py up n1", "code": "vllm_missing"}
