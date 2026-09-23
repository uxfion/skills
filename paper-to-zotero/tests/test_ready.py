# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/ready.py against a minimal mock of Zotero's local API.

Run: uv run tests/test_ready.py
"""
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ready.py"
SERVER_ID = "SRV-TEST-1"
SECRET = "SECRET-KEY-DO-NOT-PRINT"


def row(key, name, parent=False, deleted=False):
    data = {"key": key, "version": 0, "name": name, "parentCollection": parent, "relations": {}}
    if deleted:
        data["deleted"] = True
    return {"key": key, "version": 0, "data": data}


TREE = [
    row("AAAAAAAA", "自然图像"),
    row("BBBBBBBB", "Diffusion", "AAAAAAAA"),
    row("CCCCCCCC", "Latent", "BBBBBBBB"),
    row("DDDDDDDD", "tmp"),
    row("EEEEEEEE", "Old", deleted=True),
    row("FFFFFFFF", "Gone child", "EEEEEEEE", deleted=True),
]


class MockZotero:
    """Answers /api/ (with a server id), /api/users/0/collections (paged) and scripted /api/local/authorize replies."""

    def __init__(self, server_id=SERVER_ID, collections=None, api_status=200, authorize=None):
        self.server_id, self.collections, self.api_status = server_id, collections if collections is not None else TREE, api_status
        self.authorize = list(authorize or [])
        self.requests = []
        mock_self = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, body=b"", headers=None):
                try:
                    self.send_response(status)
                    for k, v in (headers or {}).items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                url = urlsplit(self.path)
                mock_self.requests.append(("GET", self.path, dict(self.headers)))
                if url.path == "/api/":
                    if mock_self.api_status == 200:
                        self.reply(200, b"{}", {"Zotero-Server-ID": mock_self.server_id, "Zotero-API-Version": "3"})
                    else:
                        self.reply(mock_self.api_status, b"Local API is not enabled")
                    return
                if url.path == "/api/users/0/collections":
                    q = parse_qs(url.query)
                    start, limit = int(q.get("start", ["0"])[0]), int(q.get("limit", ["100"])[0])
                    page = mock_self.collections[start:start + limit]
                    self.reply(200, json.dumps(page).encode(), {"Total-Results": str(len(mock_self.collections))})
                    return
                self.reply(404, b"not found")

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                headers = {k.lower(): v for k, v in self.headers.items()}  # urllib sends "Zotero-server-id"
                mock_self.requests.append(("POST", self.path, headers, body))
                if self.path != "/api/local/authorize" or not mock_self.authorize:
                    self.reply(404, b"not found")
                    return
                step = mock_self.authorize.pop(0)
                if step[0] == "sleep":
                    time.sleep(step[1])
                    self.reply(200, b"{}")
                    return
                status, headers, payload = step
                self.reply(status, json.dumps(payload).encode(), headers)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.base_url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ReadyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p2z-ready-"))
        self.downloads = self.tmp / "dl"
        self.downloads.mkdir()
        self.key_file = self.tmp / "keys" / "local-api-key"
        self.work = self.tmp / "work"
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, **kw):
        self.server = MockZotero(**kw)
        return self.server

    def write_key(self, server_id=SERVER_ID):
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_text(json.dumps({"key": SECRET, "serverID": server_id}))

    def run_ready(self, *args, base_url=None, env_extra=None, downloads=True):
        env = {k: v for k, v in os.environ.items() if k not in ("ZOTERO_LOCAL_API_KEY", "PAPER_TO_ZOTERO_DOWNLOADS")}
        env["HOME"] = str(self.tmp)
        env.update(env_extra or {})
        argv = [sys.executable, str(SCRIPT), "--base-url", base_url or self.server.base_url,
                "--key-file", str(self.key_file), "--work", str(self.work), *args]
        if downloads:
            argv += ["--downloads", str(self.downloads)]
        done = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=60)
        self.assertNotIn(SECRET, done.stdout + done.stderr, "the key leaked into the output")
        try:
            out = json.loads(done.stdout)
        except ValueError:
            self.fail(f"stdout is not one JSON object:\n{done.stdout}\n--- stderr:\n{done.stderr}")
        return done.returncode, out, done.stderr

    # --- the happy path -------------------------------------------------------------------------

    def test_ok_with_key(self):
        self.start()
        self.write_key()
        rc, out, _ = self.run_ready("--session", "mine")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["zotero"], {"reachable": True, "base_url": self.server.base_url})
        self.assertEqual(out["key"], {"present": True, "server_match": True, "key_file": str(self.key_file)})
        self.assertEqual(out["downloads_dir"], str(self.downloads))
        self.assertEqual(set(out["opencli"]), {"found", "path"})
        self.assertEqual(out["work_dir"], str(self.work))
        self.assertEqual(out["records_dir"], str(self.work / "records"))
        self.assertEqual(out["session"], "mine")
        self.assertFalse(out["resumed"])
        self.assertEqual(out["leftovers"], [])
        self.assertNotIn("hint", out)
        self.assertTrue((self.work / "records").is_dir())
        self.assertTrue((self.work / "scratch").is_dir())
        self.assertTrue((self.work / ".started").is_file())
        self.assertEqual(out["started"][:4], time.strftime("%Y"))

    def test_env_key_counts_as_present_with_unknown_match(self):
        self.start()
        rc, out, _ = self.run_ready(env_extra={"ZOTERO_LOCAL_API_KEY": SECRET})
        self.assertEqual(rc, 0)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["key"]["present"], True)
        self.assertIsNone(out["key"]["server_match"])

    def test_default_session_is_p2z(self):
        self.start()
        self.write_key()
        _, out, _ = self.run_ready()
        self.assertEqual(out["session"], "p2z")

    # --- key problems ---------------------------------------------------------------------------

    def test_no_key_without_authorize(self):
        self.start()
        rc, out, _ = self.run_ready()
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "no_key")
        self.assertEqual(out["key"], {"present": False, "server_match": None, "key_file": str(self.key_file)})
        self.assertIn("Always Allow", out["hint"])
        self.assertIn("--authorize", out["hint"])
        self.assertIn("collections", out, "the facts are still reported so the agent can plan")
        self.assertTrue((self.work / ".started").is_file())
        self.assertFalse(self.key_file.exists())

    def test_unreadable_key_file_is_absent(self):
        self.start()
        self.key_file.parent.mkdir(parents=True)
        self.key_file.write_text("not json")
        rc, out, _ = self.run_ready()
        self.assertEqual((rc, out["code"]), (1, "no_key"))
        self.assertFalse(out["key"]["present"])

    def test_server_mismatch(self):
        self.start()
        self.write_key("SRV-OTHER")
        rc, out, _ = self.run_ready()
        self.assertEqual(rc, 2)
        self.assertEqual(out["code"], "server_mismatch")
        self.assertIn("--authorize", out["hint"])
        self.assertFalse(self.work.exists(), "cannot-check stops before touching the work dir")

    # --- --authorize ----------------------------------------------------------------------------

    def test_authorize_saves_key_with_mode_0600_and_waits_on_429(self):
        self.start(authorize=[(429, {"Retry-After": "1"}, {}), (200, {}, {"key": SECRET, "remember": True})])
        rc, out, err = self.run_ready("--authorize", "--timeout", "20")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["key"], {"present": True, "server_match": True, "key_file": str(self.key_file)})
        self.assertIn("waited_s", out)
        saved = json.loads(self.key_file.read_text())
        self.assertEqual(saved["key"], SECRET)
        self.assertEqual(saved["serverID"], SERVER_ID)
        self.assertTrue(saved["remember"])
        self.assertEqual(stat.S_IMODE(self.key_file.stat().st_mode), 0o600)
        posts = [r for r in self.server.requests if r[0] == "POST"]
        self.assertEqual(len(posts), 2, "429 is retried after Retry-After")
        self.assertEqual(posts[0][2].get("zotero-server-id"), SERVER_ID)
        self.assertEqual(json.loads(posts[0][3]), {"appName": "paper-to-zotero"})
        self.assertIn("rate limited", err)

    def test_authorize_replaces_a_mismatched_key(self):
        self.start(authorize=[(200, {}, {"key": SECRET, "remember": True})])
        self.write_key("SRV-OTHER")
        rc, out, _ = self.run_ready("--authorize")
        self.assertEqual((rc, out["code"]), (0, "ok"))
        self.assertEqual(json.loads(self.key_file.read_text())["serverID"], SERVER_ID)

    def test_authorize_is_skipped_when_a_key_is_usable(self):
        self.start(authorize=[(200, {}, {"key": "OTHER", "remember": True})])
        self.write_key()
        rc, out, _ = self.run_ready("--authorize")
        self.assertEqual((rc, out["code"]), (0, "ok"))
        self.assertEqual([r for r in self.server.requests if r[0] == "POST"], [])
        self.assertEqual(json.loads(self.key_file.read_text())["key"], SECRET)

    def test_authorize_denied(self):
        self.start(authorize=[(403, {}, {"denied": True})])
        rc, out, _ = self.run_ready("--authorize")
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "authorize_denied")
        self.assertFalse(self.key_file.exists())
        self.assertIn("collections", out)

    def test_authorize_single_use_key_is_not_saved(self):
        self.start(authorize=[(200, {}, {"key": SECRET, "remember": False})])
        rc, out, _ = self.run_ready("--authorize")
        self.assertEqual((rc, out["code"]), (1, "authorize_single_use"))
        self.assertIn("Always Allow", out["hint"])
        self.assertFalse(self.key_file.exists())

    def test_authorize_timeout(self):
        self.start(authorize=[("sleep", 3)])
        rc, out, _ = self.run_ready("--authorize", "--timeout", "1")
        self.assertEqual((rc, out["code"]), (1, "authorize_timeout"))
        self.assertIn("waited_s", out)
        self.assertFalse(self.key_file.exists())

    # --- cannot check ---------------------------------------------------------------------------

    def test_zotero_unreachable(self):
        self.write_key()
        rc, out, _ = self.run_ready(base_url=f"http://127.0.0.1:{free_port()}")
        self.assertEqual((rc, out["code"]), (2, "zotero_unreachable"))
        self.assertIn("hint", out)

    def test_local_api_disabled(self):
        self.start(api_status=403)
        self.write_key()
        rc, out, _ = self.run_ready()
        self.assertEqual((rc, out["code"]), (2, "local_api_disabled"))

    # --- work directory -------------------------------------------------------------------------

    def test_leftovers_listing(self):
        self.start()
        self.write_key()
        records = self.work / "records"
        records.mkdir(parents=True)
        (records / "liu2022progressive.json").write_text("{}")
        (records / "liu2022progressive.pdf").write_bytes(b"%PDF-1.4 fake")
        (records / "page.html").write_text("<html></html>")
        sites = '{"ieeexplore.ieee.org": "gate_pending"}'
        (self.work / "sites.json").write_text(sites)
        (self.work / "notes.txt").write_text("hello")
        stray = self.work / "stray"
        (stray / "deep").mkdir(parents=True)
        (stray / "deep" / "a.bin").write_bytes(b"12345")
        (stray / "b.bin").write_bytes(b"12")
        scratch = self.work / "scratch"
        scratch.mkdir()
        (scratch / "junk.py").write_text("print()")
        rc, out, _ = self.run_ready()
        self.assertEqual((rc, out["code"]), (0, "ok"))
        self.assertEqual(out["leftovers"], [
            {"path": "notes.txt", "bytes": 5, "kind": "other"},
            {"path": "records/liu2022progressive.json", "bytes": 2, "kind": "json"},
            {"path": "records/liu2022progressive.pdf", "bytes": 13, "kind": "pdf"},
            {"path": "records/page.html", "bytes": 13, "kind": "html"},
            {"path": "sites.json", "bytes": len(sites), "kind": "json"},
            {"path": "stray", "bytes": 7, "kind": "dir"},
        ])
        self.assertTrue((scratch / "junk.py").exists(), "nothing is ever deleted")
        self.assertTrue((records / "liu2022progressive.pdf").exists())

    def test_resumed_run_keeps_started(self):
        self.start()
        self.write_key()
        rc, first, _ = self.run_ready()
        self.assertEqual(rc, 0)
        marker = self.work / ".started"
        old = marker.stat().st_mtime
        os.utime(marker, (old - 600, old - 600))  # pretend the first run was ten minutes ago
        rc, second, _ = self.run_ready()
        self.assertEqual(rc, 0)
        self.assertTrue(second["resumed"])
        self.assertEqual(marker.stat().st_mtime, old - 600, ".started is left alone")
        self.assertNotEqual(second["started"], first["started"])
        self.assertLess(second["started"], first["started"])

    # --- collections ----------------------------------------------------------------------------

    def test_collection_paths_skip_trashed_and_sort_by_path(self):
        self.start()
        self.write_key()
        _, out, _ = self.run_ready()
        self.assertEqual(out["collections"], [
            {"key": "DDDDDDDD", "name": "tmp", "parent": None, "path": "tmp"},
            {"key": "AAAAAAAA", "name": "自然图像", "parent": None, "path": "自然图像"},
            {"key": "BBBBBBBB", "name": "Diffusion", "parent": "AAAAAAAA", "path": "自然图像/Diffusion"},
            {"key": "CCCCCCCC", "name": "Latent", "parent": "BBBBBBBB", "path": "自然图像/Diffusion/Latent"},
        ])

    def test_collections_are_paged(self):
        many = [row(f"K{i:07d}", f"c{i:03d}") for i in range(230)]
        self.start(collections=many)
        self.write_key()
        _, out, _ = self.run_ready()
        self.assertEqual(len(out["collections"]), 230)
        pages = [r[1] for r in self.server.requests if r[1].startswith("/api/users/0/collections")]
        self.assertEqual(len(pages), 3)
        self.assertIn("start=200", pages[2])
        self.assertTrue(all("limit=100" in p for p in pages))


class DownloadsResolutionTest(unittest.TestCase):
    """resolve_downloads() in-process: flag, env and ~/Downloads only; never shells out here."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ready", SCRIPT)
        cls.ready = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ready)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p2z-dl-"))
        env = {k: v for k, v in os.environ.items() if k != "PAPER_TO_ZOTERO_DOWNLOADS"}
        env["HOME"] = str(self.tmp)
        patches = [mock.patch.dict(os.environ, env, clear=True),
                   mock.patch.object(self.ready, "log", lambda msg: None),
                   mock.patch.object(self.ready, "is_wsl", return_value=False),
                   mock.patch.object(self.ready, "command_output", side_effect=AssertionError("shelled out"))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_flag_wins_over_env(self):
        a, b = self.tmp / "a", self.tmp / "b"
        a.mkdir()
        b.mkdir()
        os.environ["PAPER_TO_ZOTERO_DOWNLOADS"] = str(b)
        self.assertEqual(self.ready.resolve_downloads(str(a)), str(a))

    def test_flag_pointing_nowhere_is_null(self):
        self.assertIsNone(self.ready.resolve_downloads(str(self.tmp / "missing")))

    def test_env(self):
        b = self.tmp / "b"
        b.mkdir()
        os.environ["PAPER_TO_ZOTERO_DOWNLOADS"] = str(b)
        self.assertEqual(self.ready.resolve_downloads(None), str(b))

    def test_env_pointing_nowhere_is_null(self):
        os.environ["PAPER_TO_ZOTERO_DOWNLOADS"] = str(self.tmp / "missing")
        self.assertIsNone(self.ready.resolve_downloads(None))

    def test_home_downloads(self):
        with mock.patch.object(self.ready, "command_output", return_value=None):
            self.assertIsNone(self.ready.resolve_downloads(None))
            (self.tmp / "Downloads").mkdir()
            self.assertEqual(self.ready.resolve_downloads(None), str(self.tmp / "Downloads"))

    def test_xdg_answering_home_is_ignored(self):
        (self.tmp / "Downloads").mkdir()
        with mock.patch.object(self.ready, "command_output", return_value=str(self.tmp)):
            self.assertEqual(self.ready.resolve_downloads(None), str(self.tmp / "Downloads"))

    def test_xdg_answer_is_used(self):
        xdg = self.tmp / "Téléchargements"
        xdg.mkdir()
        with mock.patch.object(self.ready, "command_output", return_value=str(xdg)):
            self.assertEqual(self.ready.resolve_downloads(None), str(xdg))


if __name__ == "__main__":
    unittest.main()
