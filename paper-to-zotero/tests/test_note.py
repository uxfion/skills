# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/note.py: the Markdown conversion and the create / update / unchanged flows against a fake local API."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "note.py"
SERVER_ID = "test-server-id"
LIB = "/api/users/0"


def load_module():
    spec = importlib.util.spec_from_file_location("note_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeZotero:
    """Items with children; search by q; paged /items/top; POST creates, PATCH checks the version."""

    def __init__(self, items):
        self.items = copy.deepcopy(items)  # key -> {"version", "data"}
        self.calls = []
        self.next_key = 1
        self.fail_patch_once = False

    def row(self, key):
        it = self.items[key]
        return {"key": key, "version": it["version"], "data": {"key": key, "version": it["version"], **it["data"]}}

    def page(self, keys, query):
        limit, start = int(query.get("limit", ["25"])[0]), int(query.get("start", ["0"])[0])
        return [self.row(k) for k in keys[start:start + limit]]

    def handle(self, method, path, query, body, headers):
        if path == "/api/":
            return 200, {"Zotero-Server-ID": SERVER_ID}, {"ok": True}
        if method == "GET" and path == f"{LIB}/items":
            q = query.get("q", [""])[0]
            keys = [k for k, it in self.items.items() if q and q.lower() in json.dumps(it["data"]).lower()]
            return 200, {}, self.page(keys, query)
        if method == "GET" and path == f"{LIB}/items/top":
            keys = [k for k, it in self.items.items() if not it["data"].get("parentItem")]
            return 200, {}, self.page(keys, query)
        if method == "GET" and path.endswith("/children"):
            parent = path.rsplit("/", 2)[1]
            keys = [k for k, it in self.items.items() if it["data"].get("parentItem") == parent]
            return 200, {}, self.page(keys, query)
        if method == "GET" and path.startswith(f"{LIB}/items/"):
            key = path.rsplit("/", 1)[1]
            return (200, {}, self.row(key)) if key in self.items else (404, {}, b"Not found")
        if headers.get("Zotero-API-Key") != "test-key" or headers.get("Zotero-Server-ID") != SERVER_ID:
            return 401, {}, b"Invalid API key"
        if method == "POST" and path == f"{LIB}/items":
            obj = json.loads(body)[0]
            key = f"NOTE{self.next_key:04d}"
            self.next_key += 1
            self.items[key] = {"version": 100 + self.next_key, "data": obj}
            return 200, {}, {"successful": {"0": self.row(key)}, "success": {"0": key}, "unchanged": {}, "failed": {}}
        if method == "PATCH" and path.startswith(f"{LIB}/items/"):
            key = path.rsplit("/", 1)[1]
            it = self.items[key]
            if self.fail_patch_once:
                self.fail_patch_once = False
                it["version"] += 1
                return 412, {}, b"item has been modified since specified version"
            if headers.get("If-Unmodified-Since-Version") != str(it["version"]):
                return 412, {}, b"item has been modified since specified version"
            it["data"].update(json.loads(body))
            it["version"] += 1
            return 204, {}, b""
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

    def do_PATCH(self):
        self._serve("PATCH")


class TestMarkdown(unittest.TestCase):
    mod = load_module()

    def test_blocks_and_inline(self):
        md = "# Title\n\nFirst **bold** and *em* with [a link](https://x.y/?a=1&b=2).\nsecond line\n\n- one\n- two <b>\n  continued\n\n## Sub\npara"
        self.assertEqual(self.mod.to_html(md),
                         "<h1>Title</h1>\n"
                         "<p>First <strong>bold</strong> and <em>em</em> with <a href=\"https://x.y/?a=1&amp;b=2\">a link</a>.\nsecond line</p>\n"
                         "<ul>\n<li>one</li>\n<li>two &lt;b&gt; continued</li>\n</ul>\n"
                         "<h2>Sub</h2>\n<p>para</p>")

    def test_everything_else_is_escaped(self):
        self.assertEqual(self.mod.to_html("a & b < c > d \"q\""), "<p>a &amp; b &lt; c &gt; d \"q\"</p>")
        self.assertEqual(self.mod.to_html("  \n\n"), "")

    def test_list_after_paragraph_and_star_bullets(self):
        self.assertEqual(self.mod.to_html("p\n* x\n* y"), "<p>p</p>\n<ul>\n<li>x</li>\n<li>y</li>\n</ul>")

    def test_marker_detection(self):
        f = self.mod.marker_of
        self.assertEqual(f("<p>p2z: v</p>\n<p>x</p>"), "p2z: v")
        self.assertEqual(f('<div data-schema-version="9">\n<p><em>p2z: v</em></p><p>x</p></div>'), "p2z: v")
        self.assertEqual(f("<h1>p2z: v</h1>"), "p2z: v")
        self.assertEqual(f("<p>a &amp; b</p>"), "a & b")
        self.assertIsNone(f(""))
        self.assertIsNone(f("<ul><li>x</li></ul>"))


ITEMS = {
    "ITEM0001": {"version": 10, "data": {"itemType": "journalArticle", "title": "Paper one", "citationKey": "one2020paper"}},
    "ITEM0002": {"version": 11, "data": {"itemType": "journalArticle", "title": "Paper two", "citationKey": "dup2021key"}},
    "ITEM0003": {"version": 12, "data": {"itemType": "journalArticle", "title": "Paper three", "citationKey": "dup2021key"}},
    "ATTA0001": {"version": 13, "data": {"itemType": "attachment", "parentItem": "ITEM0001", "title": "PDF"}},
    "NOTE0001": {"version": 14, "data": {"itemType": "note", "parentItem": "ITEM0001", "note": "<p>p2z: old</p>\n<p>stale</p>"}},
    "NOTE0002": {"version": 15, "data": {"itemType": "note", "parentItem": "ITEM0001", "note": "<p>other</p>"}},
}


class TestFlows(unittest.TestCase):
    def setUp(self):
        self.fake = FakeZotero(ITEMS)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.fake = self.fake
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_script(self, *args):
        env = dict(os.environ, ZOTERO_LOCAL_API_KEY="test-key")
        p = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, *args], capture_output=True, text=True, env=env)
        return p.returncode, json.loads(p.stdout), p.stderr

    def writes(self):
        return [c for c in self.fake.calls if c["method"] in ("POST", "PATCH")]

    def test_created_with_marker(self):
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "# Read\\n- a\\n- b", "--marker", "p2z: reading")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["action"], "created")
        self.assertEqual(out["item_key"], "ITEM0001")
        self.assertTrue(out["note_key"].startswith("NOTE"))
        post = self.writes()[0]
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["body"], [{"itemType": "note", "parentItem": "ITEM0001",
                                         "note": "<p>p2z: reading</p>\n<h1>Read</h1>\n<ul>\n<li>a</li>\n<li>b</li>\n</ul>"}])
        self.assertEqual(self.fake.items[out["note_key"]]["data"]["note"], post["body"][0]["note"])

    def test_updated_by_marker_with_version_header(self):
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["action"], "updated")
        self.assertEqual(out["note_key"], "NOTE0001")
        patch = self.writes()[0]
        self.assertEqual(patch["method"], "PATCH")
        self.assertEqual(patch["path"], f"{LIB}/items/NOTE0001")
        self.assertEqual(patch["headers"]["if-unmodified-since-version"], "14")
        self.assertEqual(patch["body"], {"note": "<p>p2z: old</p>\n<p>fresh</p>"})
        self.assertEqual(self.fake.items["NOTE0001"]["data"]["note"], "<p>p2z: old</p>\n<p>fresh</p>")
        self.assertFalse(out["retried"])

    def test_unchanged(self):
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "stale", "--marker", "p2z: old")
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "unchanged")
        self.assertEqual(out["note_key"], "NOTE0001")
        self.assertEqual(self.writes(), [])

    def test_412_retry_then_unchanged_or_updated(self):
        self.fake.fail_patch_once = True
        rc, out, err = self.run_script("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["action"], "updated")
        self.assertTrue(out["retried"])
        patches = [c for c in self.writes() if c["method"] == "PATCH"]
        self.assertEqual([p["headers"]["if-unmodified-since-version"] for p in patches], ["14", "15"])

    def test_without_marker_always_creates(self):
        for _ in (1, 2):
            rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "x")
            self.assertEqual(out["action"], "created")
        self.assertEqual(len(self.writes()), 2)
        self.assertEqual(self.writes()[0]["body"][0]["note"], "<p>x</p>")

    def test_marker_ambiguous(self):
        self.fake.items["NOTE0003"] = {"version": 16, "data": {"itemType": "note", "parentItem": "ITEM0001", "note": "<p>p2z: old</p>"}}
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "x", "--marker", "p2z: old")
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "marker_ambiguous")
        self.assertEqual(out["note_keys"], ["NOTE0001", "NOTE0003"])

    def test_dry_run(self):
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(out["action"], "updated")
        self.assertTrue(out["dry_run"])
        self.assertEqual(out["html"], "<p>p2z: old</p>\n<p>fresh</p>")
        self.assertEqual(self.writes(), [])

    def test_file_input_and_not_a_parent(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("**bold**\n")
        rc, out, _ = self.run_script("--key", "ATTA0001", "--file", f.name)
        self.assertEqual(out["code"], "not_a_parent")
        rc, out, _ = self.run_script("--key", "ZZZZZZZZ", "--file", f.name)
        self.assertEqual(out["code"], "item_not_found")
        rc, out, _ = self.run_script("--key", "ITEM0002", "--file", f.name)
        self.assertEqual(out["action"], "created")
        self.assertEqual(self.writes()[0]["body"][0]["note"], "<p><strong>bold</strong></p>")
        os.unlink(f.name)

    def test_empty_note(self):
        rc, out, _ = self.run_script("--key", "ITEM0001", "--text", "   ")
        self.assertEqual(out["code"], "empty_note")

    def test_cite_resolves_via_search(self):
        rc, out, _ = self.run_script("--cite", "one2020paper", "--text", "x", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["item_key"], "ITEM0001")
        self.assertEqual([c["query"].get("qmode") for c in self.fake.calls if c["path"] == f"{LIB}/items"], [["everything"]])
        self.assertNotIn(f"{LIB}/items/top", [c["path"] for c in self.fake.calls])

    def test_cite_falls_back_to_scan(self):
        # the search misses (the fake searches the JSON text; hide the key from it by a q that does not match)
        self.fake.items["ITEM0004"] = {"version": 20, "data": {"itemType": "journalArticle", "title": "Four", "citationKey": "four2024"}}
        orig = self.fake.handle

        def blind_search(method, path, query, body, headers):
            if path == f"{LIB}/items":
                return 200, {}, []
            return orig(method, path, query, body, headers)
        self.fake.handle = blind_search
        rc, out, err = self.run_script("--cite", "four2024", "--text", "x", "--dry-run")
        self.assertEqual(out["item_key"], "ITEM0004")
        self.assertIn("fallback", err)

    def test_cite_not_found_and_ambiguous(self):
        rc, out, _ = self.run_script("--cite", "nobody2099", "--text", "x")
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "cite_not_found")
        rc, out, _ = self.run_script("--cite", "dup2021key", "--text", "x")
        self.assertEqual(rc, 1)
        self.assertEqual(out["code"], "cite_ambiguous")
        self.assertEqual(sorted(out["keys"]), ["ITEM0002", "ITEM0003"])
        self.assertEqual(self.writes(), [])

    def test_key_never_printed(self):
        rc, out, err = self.run_script("--key", "ITEM0001", "--text", "x")
        self.assertNotIn("test-key", json.dumps(out) + err)


if __name__ == "__main__":
    unittest.main()
