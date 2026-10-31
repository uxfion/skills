# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/serve.py: profiles, the vLLM command and environment, idle and load tracking, and the server
life cycle against a stand-in vllm and hf (no GPU needed)."""
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "serve.py"
spec = importlib.util.spec_from_file_location("serve", SCRIPT)
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

# A stand-in for `vllm serve MODEL ... --served-model-name NAME --port P --host H`: records its arguments and
# environment, writes FAKE_LOG_SECONDS of start-up lines (or goes quiet for FAKE_QUIET_SECONDS, or fails like vLLM
# on a busy GPU when FAKE_FAIL is set), then answers /health, /v1/models and a /metrics page with two
# data-parallel engines, each running FAKE_RUNNING requests. With FAKE_STOP_SECONDS it takes that long to stop.
FAKE_VLLM = r'''#!/usr/bin/env python3
import json, os, signal, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
args = sys.argv[1:]
last = lambda flag: [args[i + 1] for i, a in enumerate(args) if a == flag][-1]
name, port = last("--served-model-name"), int(last("--port"))
open(os.environ["FAKE_RECORD"], "w").write(json.dumps({"args": args, "env": dict(os.environ)}))
if os.environ.get("FAKE_STOP_SECONDS"):
    signal.signal(signal.SIGTERM, lambda *_: (time.sleep(float(os.environ["FAKE_STOP_SECONDS"])), os._exit(0)))
for _ in range(int(float(os.environ.get("FAKE_LOG_SECONDS", 0)) * 4)):
    print("Loading safetensors checkpoint shards ...", flush=True); time.sleep(0.25)
time.sleep(float(os.environ.get("FAKE_QUIET_SECONDS", 0)))
if os.environ.get("FAKE_FAIL"):
    print("ValueError: Free memory on device cuda:0 (2.1/31.4 GiB) on startup is less than desired GPU memory utilization")
    for i in range(30): print(f'  File "vllm/engine/core.py", line {i}, in run_engine_core')
    print("RuntimeError: Engine core initialization failed. See root cause above."); sys.exit(1)
R = os.environ.get("FAKE_RUNNING", "0")
METRICS = f"""# HELP vllm:num_requests_running x
vllm:num_requests_running{{engine="0",model_name="m"}} {R}
vllm:num_requests_running{{engine="1",model_name="m"}} {R}
vllm:num_requests_waiting{{engine="0",model_name="m"}} 0.0
vllm:kv_cache_usage_perc{{engine="0",model_name="m"}} 0.25
vllm:kv_cache_usage_perc{{engine="1",model_name="m"}} 0.5
vllm:request_success_total{{engine="0",finished_reason="stop",model_name="m"}} 3.0
vllm:prompt_tokens_total{{engine="0",model_name="m"}} 1000.0
vllm:generation_tokens_total{{engine="0",model_name="m"}} 500.0
"""
PAGES = {"/health": "", "/metrics": METRICS, "/v1/models": json.dumps({"data": [{"id": name}]})}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path in PAGES else 404); self.end_headers()
        self.wfile.write(PAGES.get(self.path, "").encode())
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
'''

# A stand-in for `hf download MODEL`: records its pid and environment, prints FAKE_HF_SECONDS of progress, then
# puts the model's main revision into HF_HUB_CACHE.
FAKE_HF = r'''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
open(os.environ["FAKE_HF_RECORD"], "w").write(json.dumps({"pid": os.getpid(), "env": dict(os.environ)}))
for i in range(int(float(os.environ.get("FAKE_HF_SECONDS", 0)) * 4)):
    print(f"Fetching 4 files: {i}%", file=sys.stderr, flush=True); time.sleep(0.25)
repo, commit = Path(os.environ["HF_HUB_CACHE"]) / f"models--{sys.argv[2].replace('/', '--')}", "a" * 40
(repo / "snapshots" / commit).mkdir(parents=True)
(repo / "snapshots" / commit / "config.json").write_text("{}")
(repo / "refs").mkdir()
(repo / "refs" / "main").write_text(commit)
print(repo / "snapshots" / commit)
'''


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def not_http(port):
    """A program on the port that answers every connection with a line that is not HTTP."""
    server = socket.create_server(("127.0.0.1", port))
    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                conn.sendall(b"SSH-2.0-OpenSSH_9.6\r\n")
    threading.Thread(target=serve, daemon=True).start()
    try:
        yield
    finally:
        server.shutdown(socket.SHUT_RDWR)                  # wakes the accept() above, which close() alone does not
        server.close()


def wait_for(check, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if check():
            return True
        time.sleep(0.2)
    return False


class Env:
    """Temporarily set environment variables."""

    def __init__(self, **values):
        self.values, self.old = values, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.old[k] = os.environ.get(k)
            os.environ[k] = v

    def __exit__(self, *_):
        for k, v in self.old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)


class Pieces(unittest.TestCase):
    def test_profiles_extend_and_validate(self):
        with tempfile.TemporaryDirectory() as d, Env(XDG_CONFIG_HOME=d):
            local = Path(d) / "vllm-serve" / "profiles"
            local.mkdir(parents=True)
            shipped = Path(d) / "skill"
            shipped.mkdir()
            (shipped / "m.toml").write_text('model = "Org/M"\nport = 8000\nidle_minutes = 30\n'
                                            'args = ["--max-num-seqs", "256"]\nenv = { A = "1", B = "1" }\n')
            (local / "m.toml").write_text('extends = "m"\nidle_minutes = 120\nargs = ["--max-num-seqs", "16"]\n'
                                          'env = { B = "2" }\n')
            (local / "loop.toml").write_text('extends = "loop2"\n')
            (local / "loop2.toml").write_text('extends = "loop"\n')
            (local / "old.toml").write_text('model = "Org/M"\nport = 8001\ngpu_memory_utilization = 0.2\n')
            (local / "never.toml").write_text('model = "Org/M"\nport = 8002\nidle_minutes = 0\n')   # 10-30's "never stops"
            (local / "broken.toml").write_text('model = "Org/M\n')
            with mock.patch.object(S, "SKILL_PROFILES", shipped):
                p = S.load_profile("m")
                self.assertEqual((p["model"], p["port"], p["idle_minutes"]), ("Org/M", 8000, 120))
                self.assertEqual(p["args"], ["--max-num-seqs", "256", "--max-num-seqs", "16"])
                self.assertEqual(S.arg_value(p["args"], "--max-num-seqs"), "16")   # the deployment's value wins
                self.assertEqual(p["env"], {"A": "1", "B": "2"})
                for name, words in (("loop", "circle"), ("old", "--gpu-memory-utilization"), ("none", "no none.toml"),
                                    ("never", "above 0"), ("broken", "not valid TOML")):
                    with self.assertRaises(S.Failure) as e:
                        S.load_profile(name)
                    self.assertIn(words, e.exception.detail)

    def test_command_and_address(self):
        profile = {"model": "Org/Model", "port": 8118, "args": ["--trust-remote-code", "--host", "0.0.0.0"], "env": {"X": 1}}
        args = S.launch_args(profile, ["--host=10.0.0.5", "--max_num_seqs", "8"])
        self.assertEqual(args[0], "Org/Model")
        self.assertEqual(args[-4:], ["--served-model-name", "Org/Model", "--port", "8118"])   # no --host added
        self.assertEqual((S.arg_value(args, "--host"), S.arg_value(args, "--max-num-seqs")), ("10.0.0.5", "8"))
        self.assertEqual(S.launch_args({**profile, "args": []})[-2:], ["--host", "127.0.0.1"])
        self.assertEqual([S.url(h, 8118) for h in ("0.0.0.0", "::", None, "10.0.0.5", "::1")],
                         ["http://127.0.0.1:8118/v1"] * 3 + ["http://10.0.0.5:8118/v1", "http://[::1]:8118/v1"])

    def test_environment(self):
        profile = {"env": {"X": 1}}
        with tempfile.TemporaryDirectory() as d:
            toolkit = Path(d) / "cuda" / "lib64"
            toolkit.mkdir(parents=True)
            (toolkit / "libcudart.so.12").write_bytes(b"")
            env = S.server_env({"CUDA_MODULE_LOADING": "EAGER", "LD_LIBRARY_PATH": f"{toolkit}:/usr/lib/wsl/lib",
                                "VLLM_USE_FLASHINFER_SAMPLER": "1"}, profile, offline=True)
        self.assertNotIn("CUDA_MODULE_LOADING", env)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/lib/wsl/lib")
        self.assertEqual((env["VLLM_WSL2_ENABLE_PIN_MEMORY"], env["VLLM_USE_FLASHINFER_SAMPLER"]), ("1", "1"))  # caller's value kept
        self.assertEqual((env["CUDA_DEVICE_ORDER"], env["HF_HUB_OFFLINE"], env["X"]), ("PCI_BUS_ID", "1", "1"))
        self.assertEqual(S.server_env({}, profile, offline=False)["VLLM_USE_FLASHINFER_SAMPLER"], "0")
        self.assertEqual(S.server_env({"X": "2"}, profile, offline=False)["X"], "1")   # the profile's env wins
        bare = S.server_env({"CUDA_HOME": "/usr/local/cuda", "CUDA_LIB_PATH": "/usr/local/cuda/lib64"}, profile, False)
        self.assertEqual((bare.get("CUDA_HOME"), bare.get("CUDA_LIB_PATH")), (None, None))   # a CUDA 12 environment

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
        with tempfile.TemporaryDirectory() as d, Env(XDG_STATE_HOME=str(Path(d) / "state")):
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

    def test_foreign_cuda_in_maps(self):
        env = Path("/opt/uv/tools/vllm")
        maps = (f"7f00-7f01 r-xp 0 08:01 1 {env}/lib/python3.13/site-packages/nvidia/cu13/lib/libcudart.so.13\n"
                "7f02-7f03 r-xp 0 08:01 2 /usr/local/cuda-12.8/targets/x86_64-linux/lib/libcublas.so.12.8.4.1\n"
                "7f04-7f05 r-xp 0 08:01 3 /usr/lib/wsl/lib/libcuda.so.1\n"
                "7f06-7f07 rw-p 0 00:00 0 \n"
                "7f08-7f09 r-xp 0 08:01 4 /usr/lib/x86_64-linux-gnu/libc.so.6\n")
        self.assertEqual(S.foreign_cuda(maps, env), {"/usr/local/cuda-12.8/targets/x86_64-linux/lib/libcublas.so.12.8.4.1"})

    def test_hub_cache_by_revision(self):
        commit, other = "a" * 40, "b" * 40
        with tempfile.TemporaryDirectory() as d, Env(HF_HUB_CACHE=d):
            repo = Path(d) / "models--Org--Model"
            self.assertFalse(S.hub_cached("Org/Model"))
            (repo / "snapshots" / commit).mkdir(parents=True)
            (repo / "snapshots" / commit / "config.json").write_text("{}")
            self.assertTrue(S.hub_cached("Org/Model", commit))          # `hf download --revision <hash>`: no refs/main
            self.assertFalse(S.hub_cached("Org/Model"))                 # offline `main` needs refs/main
            self.assertFalse(S.hub_cached("Org/Model", other))
            (repo / "refs").mkdir()
            (repo / "refs" / "main").write_text(commit)
            self.assertTrue(S.hub_cached("Org/Model"))

    def test_health_probe_never_crashes(self):
        port = free_port()
        self.assertFalse(S.healthy("127.0.0.1", port))                  # nothing listens
        with not_http(port):
            self.assertFalse(S.healthy("127.0.0.1", port))              # something that is not HTTP
            self.assertTrue(S.listening("127.0.0.1", port))

    def test_idle_and_load(self):
        text = ('# HELP vllm:num_requests_running x\nvllm:num_requests_running{engine="0"} 2.0\n'
                'vllm:num_requests_running{engine="1"} 1.0\nvllm:kv_cache_usage_perc{engine="0"} 0.3\n'
                'vllm:kv_cache_usage_perc{engine="1"} 0.7\nvllm:request_success_total{finished_reason="stop"} 40.0\n'
                'vllm:prefix_cache_queries_total{engine="0"} 100.0\nvllm:prefix_cache_hits_total{engine="0"} 25.0\n'
                'vllm:generation_tokens_total{engine="0"} 600.0\nvllm:generation_tokens_total{engine="1"} 400.0\n')
        m = S.parse_metrics(text)
        load = S.Load()
        first = load.update(0, m)
        self.assertEqual((first["running"], first["kv_cache_usage"], first["prefix_cache_hit_rate"]), (3, 0.7, 0.25))
        self.assertNotIn("generation_tokens_per_s", first)
        later = S.parse_metrics(text.replace("600.0", "1600.0"))
        self.assertEqual(load.update(10, later)["generation_tokens_per_s"], 100.0)
        idle = S.Idle(0)
        quiet = S.parse_metrics('vllm:num_requests_running 0\nvllm:request_success_total{a="b"} 5.0\n')
        self.assertEqual(idle.update(30, quiet, 0), 0)                # first reading of the finished count: activity
        self.assertEqual(idle.update(60, quiet, 0), 30)
        self.assertEqual(idle.update(90, m, 0), 0)                    # requests running
        self.assertEqual(idle.update(150, None, 0), 60)               # metrics unreadable: no news
        self.assertEqual(idle.update(180, None, 175), 0)              # an `up` touched it


class LifeCycle(unittest.TestCase):
    """up, status, down and the idle stop through serve.py's command line, with the stand-ins on a free port, behind
    a proxy that does not exist (serve.py reaches its servers past any proxy)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.tmp.name)
        (root / "config" / "vllm-serve" / "profiles").mkdir(parents=True)
        (root / "model").mkdir()
        self.port = free_port()
        self.write_profile("fake", idle_minutes=10)
        for name, text in (("vllm", FAKE_VLLM), ("hf", FAKE_HF)):
            (root / name).write_text(text.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
            (root / name).chmod(0o755)
        self.record = root / "record.json"
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"),
                        VLLM_SERVE_VLLM=str(root / "vllm"), FAKE_RECORD=str(self.record), VLLM_SERVE_TICK="0.5",
                        HF_HUB_CACHE=str(root / "hub"), FAKE_HF_RECORD=str(root / "hf.json"),
                        CUDA_MODULE_LOADING="EAGER", http_proxy="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9")
        for k in ("CUDA_VISIBLE_DEVICES", "no_proxy", "NO_PROXY", "HF_HUB_OFFLINE"):
            self.env.pop(k, None)

    def tearDown(self):
        self.run_serve("down", "--all")
        self.tmp.cleanup()

    def write_profile(self, name, idle_minutes, args='"--trust-remote-code"', model=None, port=None, env=""):
        (self.root / "config" / "vllm-serve" / "profiles" / f"{name}.toml").write_text(
            f'model = "{model or self.root / "model"}"\nport = {port or self.port}\nidle_minutes = {idle_minutes}\n'
            f'args = [{args}]\nenv = {{ {env} }}\n')

    def run_serve(self, *args, **env):
        out = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                             env={**self.env, **env}, timeout=120)
        self.stderr = out.stderr
        return [json.loads(line) for line in out.stdout.splitlines()], out.returncode

    def start_up(self, profile="fake", **env):
        return subprocess.Popen([sys.executable, str(SCRIPT), "up", profile], stdout=subprocess.PIPE, text=True,
                                stderr=subprocess.DEVNULL, env={**self.env, **env})

    def status(self, profile="fake"):
        lines, _ = self.run_serve("status")
        return next(s for s in lines if s["profile"] == profile)

    def phase(self, profile="fake"):
        return self.status(profile).get("phase")

    def test_up_reuse_status_down(self):
        (first,), code = self.run_serve("up", "fake", "--", "--seed", "0", CUDA_VISIBLE_DEVICES="4,5", FAKE_RUNNING="1")
        self.assertEqual((code, first["started"], first["url"]), (0, True, f"http://127.0.0.1:{self.port}/v1"))
        self.assertNotIn("host", first)
        recorded = json.loads(self.record.read_text())
        self.assertNotIn("CUDA_MODULE_LOADING", recorded["env"])
        self.assertEqual(recorded["env"]["CUDA_VISIBLE_DEVICES"], "4,5")
        self.assertEqual(recorded["args"][2:5], ["--trust-remote-code", "--seed", "0"])     # serve MODEL, then these
        (same,), _ = self.run_serve("up", "fake", "--", "--seed", "0", CUDA_VISIBLE_DEVICES="4,5")
        self.assertEqual((same["started"], "differs" in same), (False, False))
        (other,), _ = self.run_serve("up", "fake")         # a plain caller: the running server, and how it differs
        self.assertEqual(other["differs"]["cuda_visible_devices"], "4,5")
        self.assertIn("--seed", other["differs"]["args"])
        time.sleep(1.5)                                    # a few supervisor ticks
        status, _ = self.run_serve("status")
        mine = next(s for s in status if s["profile"] == "fake")
        self.assertEqual((mine["phase"], mine["gpus"], mine["load"]["running"], mine["load"]["kv_cache_usage"]),
                         ("running", "4,5", 2, 0.5))
        self.assertTrue(mine["owner"])
        (stopped,), _ = self.run_serve("down", "fake")
        self.assertTrue(stopped["stopped"])
        self.assertFalse(S.healthy("127.0.0.1", self.port))
        self.assertEqual(self.phase(), "stopped")

    def test_lan_host(self):
        self.write_profile("fake", 10, '"--host", "0.0.0.0"')
        (first,), _ = self.run_serve("up", "fake")
        self.assertEqual((first["url"], first["host"]), (f"http://127.0.0.1:{self.port}/v1", "0.0.0.0"))
        self.assertEqual(S.arg_value(json.loads(self.record.read_text())["args"], "--host"), "0.0.0.0")

    def test_concurrent_ups_share_one_server(self):
        procs = [self.start_up(FAKE_LOG_SECONDS="1") for _ in range(3)]
        started = [json.loads(p.communicate(timeout=120)[0])["started"] for p in procs]
        self.assertEqual(sorted(started), [False, False, True])

    def test_a_start_is_waited_for_until_its_limit(self):
        (slow,), code = self.run_serve("up", "fake", FAKE_QUIET_SECONDS="4")    # quiet, but within the limit
        self.assertEqual((code, slow["started"]), (0, True))
        self.run_serve("down", "fake")
        t = time.time()
        (err,), code = self.run_serve("up", "fake", FAKE_QUIET_SECONDS="120", VLLM_SERVE_START_LIMIT="3")
        self.assertEqual((code, err["error"]), (2, "server_failed"))
        self.assertIn("has not answered", err["detail"])
        self.assertLess(time.time() - t, 30)

    def test_down_while_up_waits(self):
        waiting = self.start_up(FAKE_QUIET_SECONDS="120")
        self.assertTrue(wait_for(lambda: self.phase() == "starting"))
        t = time.time()
        (stopped,), _ = self.run_serve("down", "fake")
        self.assertTrue(stopped["stopped"])
        self.assertLess(time.time() - t, 15)
        err = json.loads(waiting.communicate(timeout=30)[0])
        self.assertEqual(err["error"], "server_failed")
        self.assertIn("exited while starting", err["detail"])
        self.assertIn("SIGTERM", err["detail"])                # the log's end says why

    def test_a_second_up_takes_over_from_a_killed_one(self):
        first = self.start_up(FAKE_QUIET_SECONDS="3")
        self.assertTrue(wait_for(lambda: self.phase() == "starting"))
        first.kill()
        first.communicate()
        (second,), code = self.run_serve("up", "fake")
        self.assertEqual((code, second["started"]), (0, False))

    def test_stale_state_is_not_a_server(self):
        state = self.root / "state" / "vllm-serve"
        state.mkdir(parents=True)
        (state / "fake.json").write_text(json.dumps({"pid": os.getpid(), "phase": "running", "port": self.port,
                                                     "host": "127.0.0.1", "model": "x"}))   # a live, reused pid
        (state / "fake.run").write_text("")
        stale = self.status()
        self.assertEqual((stale["phase"], stale["last"]["failed"]), ("stopped", True))
        self.assertIn("without a record", stale["last"]["ended"])
        (first,), code = self.run_serve("up", "fake")
        self.assertEqual((code, first["started"]), (0, True))

    def test_changed_profile_gets_the_running_server(self):
        self.run_serve("up", "fake")
        self.write_profile("fake", 10, model="Other/Model", port=free_port())
        (got,), code = self.run_serve("up", "fake")
        self.assertEqual((code, got["url"], got["model"]), (0, f"http://127.0.0.1:{self.port}/v1", str(self.root / "model")))
        self.assertEqual((got["differs"]["model"], got["differs"]["port"]), (str(self.root / "model"), self.port))

    def test_port_busy(self):
        with not_http(self.port):                          # another program, not even HTTP
            (err,), code = self.run_serve("up", "fake")
        self.assertEqual((code, err["error"]), (2, "port_busy"))
        self.assertIn("another program", err["detail"])
        self.write_profile("other", 10)                    # another profile on the same port, still loading
        loading = self.start_up("other", FAKE_QUIET_SECONDS="120")
        self.assertTrue(wait_for(lambda: self.phase("other") == "starting"))
        (err,), code = self.run_serve("up", "fake")
        self.assertEqual((code, err["error"]), (2, "port_busy"))
        self.assertIn("profile other", err["detail"])
        self.run_serve("down", "other")
        loading.communicate(timeout=30)

    def test_failure_points_at_the_log(self):
        (err,), code = self.run_serve("up", "fake", FAKE_FAIL="1")
        self.assertEqual((code, err["error"]), (2, "server_failed"))
        self.assertIn("exited while starting", err["detail"])
        self.assertIn("Engine core initialization failed", err["detail"])
        log = self.root / "state" / "vllm-serve" / "fake.log"
        self.assertIn(str(log), err["detail"])
        self.assertIn("references/install.md", err["detail"])           # the log's last line points at the guide
        self.assertIn("Free memory on device", log.read_text())    # the cause, above the tail: the agent reads it
        last = self.status()["last"]
        self.assertEqual((last["failed"], last["ended"]), (True, "vLLM exited with 1"))
        (again,), code = self.run_serve("up", "fake")                   # the next start keeps the failed log, says so
        self.assertEqual((code, again["started"]), (0, True))
        self.assertIn("the last start of fake failed (vLLM exited with 1", self.stderr)
        self.assertIn("Free memory on device", log.with_name("fake.prev.log").read_text())
        self.run_serve("down", "fake")
        self.assertEqual(self.status()["last"], {**self.status()["last"], "failed": False})   # stopped by down: no failure

    def test_download_is_part_of_the_start(self):
        self.write_profile("fake", 10, model="Org/M", env=f'HF_HUB_CACHE = "{self.root / "profile-hub"}"')
        waiting = self.start_up(FAKE_HF_SECONDS="120")
        self.assertTrue(wait_for(lambda: self.phase() == "downloading"))
        (stopped,), _ = self.run_serve("down", "fake")
        self.assertTrue(stopped["stopped"])
        err = json.loads(waiting.communicate(timeout=30)[0])
        self.assertIn("exited while downloading", err["detail"])
        self.assertIn("Fetching 4 files", (self.root / "state" / "vllm-serve" / "fake.log").read_text())
        hf = json.loads((self.root / "hf.json").read_text())["pid"]
        self.assertTrue(wait_for(lambda: not Path(f"/proc/{hf}").exists()))      # no orphan downloading on
        (first,), code = self.run_serve("up", "fake", FAKE_HF_SECONDS="4", VLLM_SERVE_START_LIMIT="2")
        self.assertEqual((code, first["started"]), (0, True))           # the download is not part of the limit
        self.assertEqual(json.loads((self.root / "hf.json").read_text())["env"]["HF_HUB_CACHE"], str(self.root / "profile-hub"))
        self.assertEqual(json.loads(self.record.read_text())["env"]["HF_HUB_OFFLINE"], "1")   # found in the profile's cache

    def test_idle_server_stops(self):
        self.write_profile("fake", idle_minutes=0.05)      # 3 s
        self.run_serve("up", "fake")
        self.assertTrue(wait_for(lambda: not S.healthy("127.0.0.1", self.port)))
        self.assertTrue(wait_for(lambda: self.phase() == "stopped"))

    def test_up_during_an_idle_stop_starts_afresh(self):
        self.write_profile("fake", idle_minutes=0.05)
        self.run_serve("up", "fake", FAKE_STOP_SECONDS="3")
        self.assertTrue(wait_for(lambda: self.phase() == "stopping"))
        (again,), code = self.run_serve("up", "fake")      # never handed the stopping server
        self.assertEqual((code, again["started"]), (0, True))

    def test_up_during_a_down_starts_afresh(self):
        self.run_serve("up", "fake", FAKE_STOP_SECONDS="3")
        stopping = subprocess.Popen([sys.executable, str(SCRIPT), "down", "fake"], stdout=subprocess.PIPE, text=True, env=self.env)
        self.assertTrue(wait_for(lambda: self.phase() == "stopping"))
        (again,), code = self.run_serve("up", "fake")      # never handed the server being stopped
        self.assertEqual((code, again["started"]), (0, True))
        self.assertTrue(json.loads(stopping.communicate(timeout=60)[0])["stopped"])

    def test_another_logins_server(self):
        self.run_serve("up", "fake")
        def kill(pid, sig):
            raise PermissionError(1, "Operation not permitted")
        with Env(XDG_CONFIG_HOME=self.env["XDG_CONFIG_HOME"], XDG_STATE_HOME=self.env["XDG_STATE_HOME"]), \
                mock.patch.object(S.os, "kill", side_effect=kill):
            with self.assertRaises(S.Failure) as e:
                S.down("fake")
        self.assertEqual(e.exception.code, "not_permitted")
        self.assertIn("min idle", e.exception.detail)

    def test_unknown_profile(self):
        for command in ("up", "down"):
            (err,), code = self.run_serve(command, "nope")
            self.assertEqual((code, err["error"]), (2, "unknown_profile"))


if __name__ == "__main__":
    unittest.main()
