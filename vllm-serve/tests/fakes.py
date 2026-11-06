"""Stand-ins for vllm and hf, and a free port: what test_serve.py and conventions_fixture.py start serve.py's servers
with (no GPU needed)."""
import socket
import sys
from pathlib import Path

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


def install(root: Path) -> None:
    """root/vllm and root/hf, executable, run by this Python."""
    for name, text in (("vllm", FAKE_VLLM), ("hf", FAKE_HF)):
        (root / name).write_text(text.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
        (root / name).chmod(0o755)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
