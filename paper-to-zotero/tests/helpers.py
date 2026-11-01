"""What every test file shares: loading a script, running it in this process or as a subprocess, a config, a closed
port.

    from helpers import load, call, smoke, config_file, closed_port
    trash = load("trash_item")
    r = call(trash, "--key", "ABCD1234", "--base-url", zot.base_url, config=cfg)   # r.code, r.out, r.err, r.lines

Every run checks that the fake's API key appears in neither stdout nor stderr.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))   # `from p2zlib import ...` inside the scripts, as when uv runs them
sys.path.insert(0, str(TESTS))

from fake_zotero import API_KEY, SERVER_ID  # noqa: E402

_loaded = {}


def load(name):
    """The script scripts/<name>.py as a module (once per process)."""
    if name not in _loaded:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[name] = module
    return _loaded[name]


def closed_port():
    """A port nothing listens on: bound, then released (a fixed port such as 9 can hang for seconds instead of refusing)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def config_file(directory=None, *, key=API_KEY, server_id=SERVER_ID, **fields):
    """A config file with the fake's key (key=None: none at all) and any other top-level fields; returns its path."""
    directory = Path(directory or tempfile.mkdtemp(prefix="p2z-config-"))
    config = dict(fields)
    if key is not None:
        config["zotero"] = {"key": key, "serverID": server_id}
    path = directory / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


class Result:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err

    @property
    def lines(self):
        """stdout as JSON objects, one per line."""
        return [json.loads(line) for line in self.out.splitlines() if line.strip()]

    @property
    def err_lines(self):
        return [json.loads(line) for line in self.err.splitlines() if line.startswith("{")]

    def __repr__(self):
        return f"Result(code={self.code}, out={self.out[-800:]!r}, err={self.err[-800:]!r})"


def _no_secret(result):
    assert API_KEY not in result.out + result.err, "the API key leaked into the output"
    return result


def call(module, *argv, config=None, env=None, stdin=""):
    """module.main(argv) in this process, stdout and stderr captured; a parser error (SystemExit) gives its code."""
    out, err = io.StringIO(), io.StringIO()
    environ = {**({"PAPER_TO_ZOTERO_CONFIG": str(config)} if config else {}), **(env or {})}
    with mock.patch.dict(os.environ, environ), mock.patch("sys.stdin", io.StringIO(stdin)), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    return _no_secret(Result(code, out.getvalue(), err.getvalue()))


SHEBANG = "#!/usr/bin/env -S uv run --script"
UV = shutil.which("uv")   # found once: a test may hand the script a PATH of stubs only


def smoke(name, *argv, config=None, env=None, timeout=120):
    """scripts/<name>.py as its own process, run by uv as the docs run it (after checking it opens with the uv shebang)."""
    first = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8").splitlines()[0]
    assert first == SHEBANG, f"{name}.py must open with {SHEBANG!r}, not {first!r}"
    environ = {**os.environ, **({"PAPER_TO_ZOTERO_CONFIG": str(config)} if config else {}), **(env or {})}
    done = subprocess.run([UV, "run", "--quiet", "--script", str(SCRIPTS / f"{name}.py"), *map(str, argv)], capture_output=True,
                          text=True, env=environ, timeout=timeout)
    return _no_secret(Result(done.returncode, done.stdout, done.stderr))
