# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/serve.py: profiles, the vLLM command and environment, idle tracking, and the server life
cycle against a stand-in vllm (no GPU needed)."""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "serve.py"
spec = importlib.util.spec_from_file_location("serve", SCRIPT)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

# A stand-in for `vllm serve MODEL --served-model-name NAME --host H --port P ...`: answers /v1/models and
# /metrics, and records its arguments and environment.
FAKE_VLLM = r'''#!/usr/bin/env python3
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
name, port = args[args.index("--served-model-name") + 1], int(args[args.index("--port") + 1])
open(os.environ["FAKE_RECORD"], "w").write(json.dumps({"args": args, "env": dict(os.environ)}))
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (json.dumps({"data": [{"id": name}]}) if self.path == "/v1/models"
                else "vllm:num_requests_running{model_name=\"m\"} 0.0\nvllm:request_success_total{finished_reason=\"stop\"} 3.0\n")
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Pieces(unittest.TestCase):
    def test_request_counts(self):
        text = ('# HELP vllm:num_requests_running x\nvllm:num_requests_running{model_name="m"} 2.0\n'
                'vllm:num_requests_waiting{model_name="m"} 1.0\n'
                'vllm:request_success_total{finished_reason="stop",model_name="m"} 40.0\n'
                'vllm:request_success_total{finished_reason="length",model_name="m"} 2.0\n'
                'vllm:num_requests_running_total_bogus 9\n')
        self.assertEqual(S.request_counts(text), (3.0, 42.0))

    def test_idle_clock(self):
        idle = S.Idle(0)
        self.assertEqual(idle.update(30, 0, 5, 0), 0)        # first reading of the finished count: activity
        self.assertEqual(idle.update(60, 0, 5, 0), 30)
        self.assertEqual(idle.update(90, 1, 5, 0), 0)        # a request running
        self.assertEqual(idle.update(120, 0, 6, 0), 0)       # one finished
        self.assertEqual(idle.update(150, None, None, 0), 30)  # metrics unreadable: no news
        self.assertEqual(idle.update(180, 0, 6, 175), 0)     # an `up` touched it

    def test_command_and_environment(self):
        profile = {"model": "Org/Model", "port": 8118, "gpu_memory_utilization": 0.5, "args": ["--trust-remote-code"],
                   "env": {"X": 1}}
        cmd = S.vllm_command("/v/bin/vllm", profile)
        self.assertEqual(cmd[:4], ["/v/bin/vllm", "serve", "Org/Model", "--served-model-name"])
        self.assertIn("--trust-remote-code", cmd)
        self.assertEqual(cmd[cmd.index("--port") + 1], "8118")
        with tempfile.TemporaryDirectory() as d:
            toolkit = Path(d) / "cuda" / "lib64"
            toolkit.mkdir(parents=True)
            (toolkit / "libcudart.so.12").write_bytes(b"")
            env = S.server_env({"CUDA_MODULE_LOADING": "EAGER", "LD_LIBRARY_PATH": f"{toolkit}:/usr/lib/wsl/lib",
                                "VLLM_USE_FLASHINFER_SAMPLER": "1"}, profile, offline=True)
        self.assertNotIn("CUDA_MODULE_LOADING", env)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/lib/wsl/lib")
        self.assertEqual((env["VLLM_WSL2_ENABLE_PIN_MEMORY"], env["VLLM_USE_FLASHINFER_SAMPLER"]), ("1", "1"))  # caller's value kept
        self.assertEqual(S.server_env({}, profile, offline=False)["VLLM_USE_FLASHINFER_SAMPLER"], "0")
        self.assertEqual((env["HF_HUB_OFFLINE"], env["X"]), ("1", "1"))

    def test_own_cuda_toolkit_wins(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "vllm"
            for cu in ("cu12", "cu13"):
                (root / "lib" / "python3.13" / "site-packages" / "nvidia" / cu / "bin").mkdir(parents=True)
                (root / "lib" / "python3.13" / "site-packages" / "nvidia" / cu / "bin" / "nvcc").write_bytes(b"")
            (root / "bin").mkdir()
            (root / "bin" / "vllm").write_bytes(b"")
            cuda = S.own_cuda(str(root / "bin" / "vllm"))
            self.assertEqual(cuda.name, "cu13")
            env = S.server_env({"CUDA_HOME": "/usr/local/cuda-12.8", "PATH": "/usr/local/cuda-12.8/bin:/usr/bin"},
                               {"env": {}}, offline=False, cuda=cuda, venv_bin=root / "bin")
            self.assertEqual((env["CUDA_HOME"], env["CUDA_PATH"], env["CUDA_LIB_PATH"]), (str(cuda), str(cuda), str(cuda / "lib")))
            self.assertTrue(env["PATH"].startswith(f"{cuda / 'bin'}:{root / 'bin'}:"))
            self.assertIsNone(S.own_cuda(str(Path(d) / "elsewhere" / "bin" / "vllm")))
            self.assertEqual(env["LD_LIBRARY_PATH"].split(":")[0], str(cuda / "lib"))

    def test_unversioned_names_point_into_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("XDG_STATE_HOME")
            os.environ["XDG_STATE_HOME"] = str(Path(d) / "state")
            try:
                lib = Path(d) / "cu13" / "lib"
                lib.mkdir(parents=True)
                for name in ("libcublas.so.13", "libcublasLt.so.13", "libnvrtc.alt.so.13"):
                    (lib / name).write_bytes(b"")
                links = S.unversioned_links(lib.parent)
                self.assertEqual((links / "libcublas.so").resolve(), (lib / "libcublas.so.13").resolve())
                self.assertTrue((links / "libnvrtc.alt.so").is_symlink())
                S.unversioned_links(lib.parent)                      # again: existing links kept
                env = S.server_env({"LD_LIBRARY_PATH": "/usr/lib/wsl/lib"}, {"env": {}}, False, lib.parent, None, links)
                self.assertEqual(env["LD_LIBRARY_PATH"], f"{links}:{lib}:/usr/lib/wsl/lib")
            finally:
                os.environ.pop("XDG_STATE_HOME") if old is None else os.environ.__setitem__("XDG_STATE_HOME", old)

    def test_foreign_cuda_in_maps(self):
        env = Path("/opt/uv/tools/vllm")
        maps = (f"7f00-7f01 r-xp 0 08:01 1 {env}/lib/python3.13/site-packages/nvidia/cu13/lib/libcudart.so.13\n"
                "7f02-7f03 r-xp 0 08:01 2 /usr/local/cuda-12.8/targets/x86_64-linux/lib/libcublas.so.12.8.4.1\n"
                "7f04-7f05 r-xp 0 08:01 3 /usr/lib/wsl/lib/libcuda.so.1\n"
                "7f06-7f07 rw-p 0 00:00 0 \n"
                "7f08-7f09 r-xp 0 08:01 4 /usr/lib/x86_64-linux-gnu/libc.so.6\n")
        self.assertEqual(S.foreign_cuda(maps, env), {"/usr/local/cuda-12.8/targets/x86_64-linux/lib/libcublas.so.12.8.4.1"})

    def test_hub_cache_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("HF_HUB_CACHE")
            os.environ["HF_HUB_CACHE"] = d
            try:
                self.assertFalse(S.hub_cached("Org/Model"))
                snap = Path(d) / "models--Org--Model" / "snapshots" / "abc"
                snap.mkdir(parents=True)
                (snap / "config.json").write_text("{}")
                self.assertTrue(S.hub_cached("Org/Model"))
            finally:
                os.environ.pop("HF_HUB_CACHE") if old is None else os.environ.__setitem__("HF_HUB_CACHE", old)


class LifeCycle(unittest.TestCase):
    """up / up again / status / idle stop / down, with the stand-in vllm on a free port."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "config" / "vllm-serve" / "profiles").mkdir(parents=True)
        (root / "model").mkdir()
        self.port = free_port()
        self.profile = root / "config" / "vllm-serve" / "profiles" / "fake.toml"
        self.write_profile(idle_minutes=10)
        fake = root / "vllm"
        fake.write_text(FAKE_VLLM.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
        fake.chmod(0o755)
        self.record = root / "record.json"
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"),
                        VLLM_SERVE_VLLM=str(fake), FAKE_RECORD=str(self.record), VLLM_SERVE_TICK="0.5",
                        CUDA_MODULE_LOADING="EAGER")

    def tearDown(self):
        self.run_serve("down", "--all")
        self.tmp.cleanup()

    def write_profile(self, idle_minutes):
        self.profile.write_text(f'model = "{Path(self.tmp.name) / "model"}"\nport = {self.port}\n'
                                f'gpu_memory_utilization = 0.0\nidle_minutes = {idle_minutes}\nargs = ["--trust-remote-code"]\n')

    def run_serve(self, *args):
        out = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=self.env, timeout=120)
        return [json.loads(line) for line in out.stdout.splitlines()], out.returncode

    def test_up_reuse_down(self):
        (first,), code = self.run_serve("up", "fake")
        self.assertEqual((code, first["started"], first["url"]), (0, True, f"http://127.0.0.1:{self.port}/v1"))
        recorded = json.loads(self.record.read_text())
        self.assertNotIn("CUDA_MODULE_LOADING", recorded["env"])
        self.assertIn("--trust-remote-code", recorded["args"])
        (again,), _ = self.run_serve("up", "fake")
        self.assertFalse(again["started"])
        status, _ = self.run_serve("status")
        self.assertTrue([s for s in status if s["profile"] == "fake"][0]["running"])
        (stopped,), _ = self.run_serve("down", "fake")
        self.assertTrue(stopped["stopped"])
        self.assertIsNone(S.answers({"port": self.port, "model": "x"}))

    def test_concurrent_ups_share_one_server(self):
        procs = [subprocess.Popen([sys.executable, str(SCRIPT), "up", "fake"], stdout=subprocess.PIPE, text=True, env=self.env)
                 for _ in range(3)]
        started = [json.loads(p.communicate(timeout=120)[0])["started"] for p in procs]
        self.assertEqual(sorted(started), [False, False, True])

    def test_idle_server_stops(self):
        self.write_profile(idle_minutes=0.05)          # 3 s
        self.run_serve("up", "fake")
        deadline = time.time() + 30
        while time.time() < deadline and S.answers({"port": self.port, "model": "x"}) is not None:
            time.sleep(0.5)
        self.assertIsNone(S.answers({"port": self.port, "model": "x"}))

    def test_other_model_on_the_port(self):
        self.run_serve("up", "fake")
        self.profile.write_text(self.profile.read_text().replace(f'model = "{Path(self.tmp.name) / "model"}"', 'model = "Other/Model"'))
        (err,), code = self.run_serve("up", "fake")
        self.assertEqual((code, err["error"]), (2, "port_busy"))

    def test_unknown_profile(self):
        (err,), code = self.run_serve("up", "nope")
        self.assertEqual((code, err["error"]), (2, "unknown_profile"))


if __name__ == "__main__":
    unittest.main()
