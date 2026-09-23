# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/make_collection.py against a minimal fake of the Zotero local API."""
import json
import os
import subprocess
import sys
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_collection.py"
SERVER_ID = "test-server-id"
LIB = "/api/users/0"


class FakeZotero:
    """Collections only: a paged listing, one collection by key, and the POST that creates one."""

    def __init__(self, collections):
        self.collections = list(collections)  # {key, name, parent, deleted?, version}
        self.calls = []
        self.next_key = 1

    def row(self, c):
        data = {"key": c["key"], "version": c.get("version", 1), "name": c["name"], "parentCollection": c["parent"] or False}
        if c.get("deleted"):
            data["deleted"] = True
        return {"key": c["key"], "version": c.get("version", 1), "data": data}

    def handle(self, method, path, query, body, headers):
        if path == "/api/":
            return 200, {"Zotero-Server-ID": SERVER_ID}, {"ok": True}
        if method == "GET" and path == f"{LIB}/collections":
            limit, start = int(query.get("limit", ["25"])[0]), int(query.get("start", ["0"])[0])
            return 200, {}, [self.row(c) for c in self.collections[start:start + limit]]
        if method == "GET" and path.startswith(f"{LIB}/collections/"):
            key = path.rsplit("/", 1)[1]
            for c in self.collections:
                if c["key"] == key:
                    return 200, {}, self.row(c)
            return 404, {}, b"Not found"
        if method == "POST" and path == f"{LIB}/collections":
            if headers.get("Zotero-API-Key") != "test-key" or headers.get("Zotero-Server-ID") != SERVER_ID:
                return 401, {}, b"Invalid API key"
            obj = json.loads(body)[0]
            key = f"NEW{self.next_key:05d}"
            self.next_key += 1
            self.collections.append({"key": key, "name": obj["name"], "parent": obj["parentCollection"] or None, "version": 7})
            return 200, {}, {"successful": {"0": {"key": key, "version": 7, "data": self.row(self.collections[-1])["data"]}},
                             "success": {"0": key}, "unchanged": {}, "failed": {}}
        return 404, {}, b"no route"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _serve(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        fake = self.server.fake
        fake.calls.append({"method": method, "path": parts.path, "query": query, "body": json.loads(body) if body else None,
                           "headers": {k.lower(): v for k, v in self.headers.items()}})
        status, extra, out = fake.handle(method, parts.path, query, body, self.headers)
        if not isinstance(out, bytes):
            out = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")


class Base(unittest.TestCase):
    collections = []

    def setUp(self):
        self.fake = FakeZotero(self.collections)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.fake = self.fake
        import threading
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_script(self, *args):
        env = dict(os.environ, ZOTERO_LOCAL_API_KEY="test-key")
        p = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, *args], capture_output=True, text=True, env=env)
        return p.returncode, json.loads(p.stdout), p.stderr

    def posts(self):
        return [c for c in self.fake.calls if c["method"] == "POST"]


TREE = [
    {"key": "AAAAAAAA", "name": "自然图像", "parent": None},
    {"key": "BBBBBBBB", "name": "Diffusion", "parent": "AAAAAAAA"},
    {"key": "CCCCCCCC", "name": "tmp", "parent": None},
    {"key": "DDDDDDDD", "name": "Diffusion", "parent": None},
    {"key": "EEEEEEEE", "name": "twice", "parent": "AAAAAAAA"},
    {"key": "FFFFFFFF", "name": "twice", "parent": "AAAAAAAA"},
    {"key": "GGGGGGGG", "name": "gone", "parent": None, "deleted": True},
]


class TestMakeCollection(Base):
    collections = TREE

    def test_exists_top_level(self):
        rc, out, _ = self.run_script("--name", "tmp")
        self.assertEqual(rc, 0)
        self.assertEqual(out["code"], "exists")
        self.assertEqual(out["key"], "CCCCCCCC")
        self.assertEqual(out["path"], "tmp")
        self.assertIsNone(out["parent"])
        self.assertEqual(self.posts(), [])

    def test_exists_under_parent_only_matches_that_parent(self):
        rc, out, _ = self.run_script("--name", "Diffusion", "--parent", "AAAAAAAA")
        self.assertEqual(rc, 0)
        self.assertEqual(out["code"], "exists")
        self.assertEqual(out["key"], "BBBBBBBB")
        self.assertEqual(out["path"], "自然图像/Diffusion")
        rc, out, _ = self.run_script("--name", "Diffusion")
        self.assertEqual(out["key"], "DDDDDDDD")

    def test_ambiguous(self):
        rc, out, _ = self.run_script("--name", "twice", "--parent", "AAAAAAAA")
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "ambiguous")
        self.assertEqual(out["keys"], ["EEEEEEEE", "FFFFFFFF"])
        self.assertEqual(self.posts(), [])

    def test_parent_not_found_missing_and_trashed(self):
        for parent in ("ZZZZZZZZ", "GGGGGGGG"):
            rc, out, _ = self.run_script("--name", "x", "--parent", parent)
            self.assertEqual(rc, 1, parent)
            self.assertEqual(out["code"], "parent_not_found")
        self.assertEqual(self.posts(), [])

    def test_trashed_collection_does_not_count_as_existing(self):
        rc, out, _ = self.run_script("--name", "gone", "--dry-run")
        self.assertEqual(out["code"], "ok")
        self.assertTrue(out["dry_run"])

    def test_ok_creates_under_parent(self):
        rc, out, _ = self.run_script("--name", "Mean Flow", "--parent", "AAAAAAAA")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["key"], "NEW00001")
        self.assertEqual(out["path"], "自然图像/Mean Flow")
        self.assertEqual(out["parent"], "AAAAAAAA")
        post = self.posts()[0]
        self.assertEqual(post["body"], [{"name": "Mean Flow", "parentCollection": "AAAAAAAA"}])
        self.assertEqual(post["headers"]["zotero-api-key"], "test-key")
        self.assertEqual(post["headers"]["zotero-server-id"], SERVER_ID)
        # idempotent: the second run finds it
        rc, out, _ = self.run_script("--name", "Mean Flow", "--parent", "AAAAAAAA")
        self.assertEqual(out["code"], "exists")
        self.assertEqual(out["key"], "NEW00001")
        self.assertEqual(len(self.posts()), 1)

    def test_ok_top_level_sends_false_parent(self):
        rc, out, _ = self.run_script("--name", "新分类")
        self.assertEqual(out["code"], "ok")
        self.assertEqual(self.posts()[0]["body"], [{"name": "新分类", "parentCollection": False}])
        self.assertEqual(out["path"], "新分类")

    def test_dry_run_posts_nothing(self):
        rc, out, _ = self.run_script("--name", "新分类", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(out["code"], "ok")
        self.assertTrue(out["dry_run"])
        self.assertIsNone(out["key"])
        self.assertEqual(self.posts(), [])

    def test_key_never_printed(self):
        rc, out, err = self.run_script("--name", "新分类")
        self.assertNotIn("test-key", json.dumps(out) + err)


class TestPagination(Base):
    collections = [{"key": f"C{i:07d}", "name": f"c{i}", "parent": None} for i in range(150)] + \
                  [{"key": "TARGET01", "name": "late", "parent": "C0000149"}]

    def test_second_page_is_read(self):
        rc, out, _ = self.run_script("--name", "late", "--parent", "C0000149")
        self.assertEqual(out["code"], "exists")
        self.assertEqual(out["key"], "TARGET01")
        self.assertEqual(out["path"], "c149/late")
        starts = [c["query"].get("start") for c in self.fake.calls if c["path"] == f"{LIB}/collections"]
        self.assertEqual(starts, [["0"], ["100"]])


if __name__ == "__main__":
    unittest.main()
