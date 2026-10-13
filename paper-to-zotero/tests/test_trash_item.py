# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/trash_item.py against a minimal mock of Zotero's local API (item GET, search, PATCH with version check)."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "trash_item.py"
SERVER_ID = "MOCKSRV1"
API_KEY = "mock-key-never-printed"
LIB = "/api/users/0"
PARENT, ATT, NOTE, OLD, TRASHED, DUP1, DUP2 = "PARENT01", "ATTACH01", "NOTE0001", "OLDITEM1", "TRASHED1", "DUPKEY01", "DUPKEY02"


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_items():
    def item(key, version, meta=None, **data):
        return {"key": key, "version": version, "meta": meta or {}, "data": {"key": key, "version": version, **data}}
    return {
        PARENT: item(PARENT, 10, {"numChildren": 2}, itemType="journalArticle", title="A paper with a superseded preprint",
                     citationKey="liu2022paper"),
        ATT: item(ATT, 11, None, itemType="attachment", parentItem=PARENT, title="Preprint", linkMode="imported_url"),
        NOTE: item(NOTE, 12, None, itemType="note", parentItem=PARENT, note="<p>a note</p>"),
        OLD: item(OLD, 13, {"numChildren": 0}, itemType="webpage", title="Orphan webpage"),
        TRASHED: item(TRASHED, 14, {"numChildren": 0}, itemType="journalArticle", title="Already gone", deleted=True,
                      citationKey="gone2020"),
        DUP1: item(DUP1, 15, {"numChildren": 0}, itemType="journalArticle", title="Dup one", citationKey="dupkey"),
        DUP2: item(DUP2, 16, {"numChildren": 0}, itemType="journalArticle", title="Dup two", citationKey="dupkey"),
    }


class State:
    def __init__(self):
        self.items = make_items()
        self.patches = []             # (key, body, If-Unmodified-Since-Version)
        self.gets = []
        self.bump_before_patch = 0    # simulate this many concurrent edits (each PATCH sees a newer version)
        self.trash_meanwhile = False  # a concurrent edit that also trashes the item
        self.ignore_patch = False     # answer 204 but change nothing (-> readback_mismatch)
        self.patch_status = None
        self.search_sees_citekey = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body=None, headers=None):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        s = self.server.state
        url = urllib.parse.urlsplit(self.path)
        path, q = url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        s.gets.append(self.path)
        if path == "/api/":
            return self.send(200, {"ok": True}, {"Zotero-Server-ID": SERVER_ID})
        if path in (f"{LIB}/items", f"{LIB}/items/top"):
            rows = [it for it in s.items.values() if not it["data"].get("deleted")]
            if path.endswith("/top"):
                rows = [it for it in rows if not it["data"].get("parentItem") and it["data"]["itemType"] not in ("attachment", "note")]
            if "q" in q:
                needle = q["q"].casefold()
                fields = [k for k in ("title", "citationKey") if k != "citationKey" or s.search_sees_citekey]
                rows = [it for it in rows if any(needle in str(it["data"].get(f, "")).casefold() for f in fields)]
            start, limit = int(q.get("start", 0)), int(q.get("limit", 25))
            return self.send(200, rows[start:start + limit])
        if path.startswith(f"{LIB}/items/"):
            it = s.items.get(path.rsplit("/", 1)[1])
            return self.send(200, it) if it else self.send(404, b"Not found")
        self.send(404, b"Not found")

    def do_PATCH(self):
        s = self.server.state
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Zotero-API-Key") != API_KEY:
            return self.send(401, b"Invalid API key")
        if self.headers.get("Zotero-Server-ID") != SERVER_ID:
            return self.send(412, b"Zotero-Server-ID mismatch")
        key = self.path.rsplit("/", 1)[1]
        it = s.items.get(key)
        if not it:
            return self.send(404, b"Not found")
        body, since = json.loads(raw), self.headers.get("If-Unmodified-Since-Version")
        s.patches.append((key, body, since))
        if s.patch_status:
            return self.send(s.patch_status, b"forced failure")
        if s.bump_before_patch:
            s.bump_before_patch -= 1
            it["version"] += 1
            it["data"]["version"] = it["version"]
            if s.trash_meanwhile:
                it["data"]["deleted"] = True
        if since != str(it["version"]):
            return self.send(412, b"Item has been modified since specified version")
        if not s.ignore_patch:
            if body.get("deleted"):
                it["data"]["deleted"] = True
            else:
                it["data"].pop("deleted", None)
            it["version"] += 1
            it["data"]["version"] = it["version"]
        self.send(204)


class TrashItemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.keydir = Path(tempfile.mkdtemp(prefix="trash_item_key_"))
        cls.config = cls.keydir / "config.json"
        cls.config.write_text(json.dumps({"zotero": {"key": API_KEY, "serverID": SERVER_ID}}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state = self.server.state = State()

    def run_script(self, *argv, base_url=None, config=None):
        env = dict(os.environ, PAPER_TO_ZOTERO_CONFIG=str(config or self.config))
        cmd = [sys.executable, str(SCRIPT), *argv, "--base-url", base_url or self.base_url]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    @staticmethod
    def lines(stdout):
        return [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]

    def test_trash_writes_deleted_with_version_and_reports(self):
        r = self.run_script("--key", ATT, OLD)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[0], {"key": ATT, "itemType": "attachment", "title": "Preprint", "parent": PARENT,
                                  "parent_title": "A paper with a superseded preprint", "version": 12, "code": "ok",
                                  "retried": False})
        self.assertEqual((out[1]["code"], out[1]["children"], out[1]["parent"]), ("ok", 0, None))
        self.assertEqual(out[-1], {"summary": {"total": 2, "ok": 2, "skipped": 0, "failed": 0}})
        self.assertEqual(self.state.patches, [(ATT, {"deleted": 1}, "11"), (OLD, {"deleted": 1}, "13")])
        self.assertTrue(self.state.items[ATT]["data"]["deleted"])
        self.assertNotIn(API_KEY, r.stdout + r.stderr)

    def test_already_trashed_is_skipped_and_rerun_is_a_no_op(self):
        r = self.run_script("--key", TRASHED)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["code"], "already_trashed")
        self.assertEqual(self.lines(r.stdout)[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        self.assertEqual(self.state.patches, [])
        self.run_script("--key", OLD)
        r = self.run_script("--key", OLD)
        self.assertEqual(self.lines(r.stdout)[0]["code"], "already_trashed")
        self.assertEqual(len(self.state.patches), 1)

    def test_not_found_fails_only_its_own_line(self):
        r = self.run_script("--key", "GONE0000,", OLD)
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:2]], ["not_found", "ok"])
        self.assertIn("hint", out[0])
        self.assertEqual(out[-1]["summary"], {"total": 2, "ok": 1, "skipped": 0, "failed": 1})

    def test_restore(self):
        r = self.run_script("--key", TRASHED, "--key", OLD, "--restore")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:2]], ["ok", "not_in_trash"])
        self.assertEqual(self.state.patches, [(TRASHED, {"deleted": 0}, "14")])
        self.assertNotIn("deleted", self.state.items[TRASHED]["data"])

    def test_dry_run_lists_and_writes_nothing(self):
        r = self.run_script("--key", PARENT, ATT, NOTE, TRASHED, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[0], {"key": PARENT, "itemType": "journalArticle", "title": "A paper with a superseded preprint",
                                  "parent": None, "children": 2, "version": 10, "code": "ok", "dry_run": True})
        self.assertEqual((out[1]["parent"], out[1]["parent_title"]), (PARENT, "A paper with a superseded preprint"))
        self.assertEqual((out[2]["itemType"], out[2]["title"]), ("note", "<p>a note</p>"))
        self.assertEqual(out[3]["code"], "already_trashed")
        self.assertEqual(out[-1]["summary"], {"total": 4, "ok": 3, "skipped": 1, "failed": 0, "dry_run": True})
        self.assertEqual(self.state.patches, [])

    def test_412_once_retries_twice_conflicts(self):
        self.state.bump_before_patch = 1
        r = self.run_script("--key", OLD)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["code"], line["retried"]), ("ok", True))
        self.assertEqual([p[2] for p in self.state.patches], ["13", "14"])

        self.setUp()
        self.state.bump_before_patch = 2
        r = self.run_script("--key", OLD)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.lines(r.stdout)[0]["code"], "version_conflict")
        self.assertEqual(len(self.state.patches), 2)

    def test_412_because_someone_trashed_it_meanwhile(self):
        self.state.bump_before_patch, self.state.trash_meanwhile = 1, True
        r = self.run_script("--key", OLD)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["code"], line["retried"]), ("already_trashed", True))
        self.assertEqual(len(self.state.patches), 1)

    def test_readback_mismatch_and_write_denied(self):
        self.state.ignore_patch = True
        r = self.run_script("--key", OLD)
        self.assertEqual((r.returncode, self.lines(r.stdout)[0]["code"]), (1, "readback_mismatch"))
        self.setUp()
        self.state.patch_status = 403
        r = self.run_script("--key", OLD)
        self.assertEqual((r.returncode, self.lines(r.stdout)[0]["code"]), (1, "write_denied"))

    def test_cite_resolution(self):
        r = self.run_script("--cite", "liu2022paper", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["key"], line["cite"], line["code"]), (PARENT, "liu2022paper", "ok"))
        self.assertFalse(any("/items/top" in g for g in self.state.gets))

        self.state.search_sees_citekey = False
        self.state.gets.clear()
        r = self.run_script("--cite", "liu2022paper", "nobody", "dupkey", "--dry-run")
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual(out[0]["key"], PARENT, "found by the fallback scan")
        self.assertEqual(sum("/items/top" in g for g in self.state.gets), 1, "one shared scan for every missed cite")
        self.assertEqual(out[1], {"cite": "nobody", "code": "cite_not_found", "hint": out[1]["hint"]})
        self.assertEqual((out[2]["code"], out[2]["keys"]), ("cite_ambiguous", [DUP1, DUP2]))
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 1, "skipped": 0, "failed": 2, "dry_run": True})

    def test_key_named_twice_is_handled_once(self):
        r = self.run_script("--key", PARENT, "--cite", "liu2022paper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[-1]["summary"]["total"], 1)
        self.assertEqual(len(self.state.patches), 1)

    def test_cannot_check_and_arguments(self):
        r = self.run_script("--key", OLD, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "zotero_unreachable"))
        r = self.run_script("--key", OLD, config=Path(tempfile.mkdtemp()) / "missing.json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_key"))
        other = Path(tempfile.mkdtemp()) / "wrong.json"
        other.write_text(json.dumps({"zotero": {"key": "wrong", "serverID": SERVER_ID}}), encoding="utf-8")
        r = self.run_script("--key", OLD, PARENT, config=other)
        self.assertEqual(r.returncode, 2)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:2]], ["not_run", "not_run"])
        self.assertEqual(out[-1]["summary"]["stopped"], "key_rejected")
        self.assertEqual(self.run_script().returncode, 2)
        self.assertEqual(self.run_script("--key", "short").returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
