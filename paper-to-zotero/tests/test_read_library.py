# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/read_library.py against a minimal local-API mock (http.server)."""

import http.server
import json
import subprocess
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_library.py"
LIB = "/api/users/0"


def make_library():
    items = {}
    for i in range(250):
        key = f"K{i:07d}"
        items[key] = {"key": key, "version": i + 1, "data": {
            "key": key, "version": i + 1, "itemType": "journalArticle", "title": f"Paper number {i}",
            "citationKey": f"auth{i}", "collections": ["C1AAAAAA"] if i % 5 == 0 else [], "tags": []}}
    items["K0000001"]["data"]["citationKey"] = "dupkey"
    items["K0000002"]["data"]["citationKey"] = "dupkey"
    items["ATT00001"] = {"key": "ATT00001", "version": 300, "data": {
        "key": "ATT00001", "version": 300, "itemType": "attachment", "parentItem": "K0000000",
        "title": "PDF", "contentType": "application/pdf", "md5": "abc"}}
    items["NOTE0001"] = {"key": "NOTE0001", "version": 301, "data": {
        "key": "NOTE0001", "version": 301, "itemType": "note", "parentItem": "K0000000", "note": "<p>hi</p>"}}
    collections = [
        {"key": "C1AAAAAA", "version": 1, "data": {"key": "C1AAAAAA", "version": 1, "name": "医疗图像", "parentCollection": False}},
        {"key": "C2AAAAAA", "version": 2, "data": {"key": "C2AAAAAA", "version": 2, "name": "超声挑战赛", "parentCollection": "C1AAAAAA"}},
        {"key": "C3AAAAAA", "version": 3, "data": {"key": "C3AAAAAA", "version": 3, "name": "Agent", "parentCollection": False}},
        {"key": "C4AAAAAA", "version": 4, "data": {"key": "C4AAAAAA", "version": 4, "name": "Old", "parentCollection": False, "deleted": True}},
        {"key": "C5AAAAAA", "version": 5, "data": {"key": "C5AAAAAA", "version": 5, "name": "Orphan of Old", "parentCollection": "C4AAAAAA"}},
    ]
    tags = [
        {"tag": "CVPR", "meta": {"type": 0, "numItems": 4}},
        {"tag": "Deep learning", "meta": {"type": 1, "numItems": 6}},
        {"tag": "rare", "meta": {"type": 0, "numItems": 1}},
    ]
    return items, collections, tags


class Handler(http.server.BaseHTTPRequestHandler):
    items, collections, tags = make_library()
    requests = []
    disabled = False

    def log_message(self, *a):
        pass

    def send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def paginate(self, rows, query):
        start = int(query.get("start", ["0"])[0])
        limit = int(query.get("limit", ["25"])[0])
        page = rows[start:start + limit]
        headers = {"Total-Results": str(len(rows))}
        if start + limit < len(rows):
            headers["Link"] = f'<{self.path}&start={start + limit}>; rel="next"'
        self.send_json(page, headers=headers)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        Handler.requests.append((path, {k: v[0] for k, v in query.items()}))
        if Handler.disabled:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Local API is not enabled")
            return
        if path == "/api/schema":
            return self.send_json({"version": 44, "itemTypes": [{"itemType": "journalArticle"}]})
        if path == f"{LIB}/collections":
            return self.paginate(self.collections, query)
        if path == f"{LIB}/tags":
            return self.paginate(self.tags, query)
        m_item = path.startswith(f"{LIB}/items/") and path.split("/")
        if m_item and len(m_item) == 7 and m_item[6] == "children":
            key = m_item[5]
            # The real local API answers a missing key with the whole library.
            rows = [it for it in self.items.values() if it["data"].get("parentItem") == key] if key in self.items else list(self.items.values())
            return self.paginate(rows, query)
        if m_item and len(m_item) == 6 and m_item[5] != "top":
            it = self.items.get(m_item[5])
            return self.send_json(it) if it else self.send_json("Not found", 404)
        top = path.endswith("/top")
        coll = None
        if path.startswith(f"{LIB}/collections/"):
            coll = path.split("/")[5]
        rows = list(self.items.values())
        if coll:
            rows = [it for it in rows if coll in (it["data"].get("collections") or [])]
        if "itemKey" in query:
            wanted = query["itemKey"][0].split(",")
            # Emulate the local API: the children of a requested key come along.
            rows = [it for it in rows if it["key"] in wanted or it["data"].get("parentItem") in wanted]
        if top:
            rows = [it for it in rows if not it["data"].get("parentItem")]
        if "since" in query:
            rows = [it for it in rows if it["version"] > int(query["since"][0])]
        if "q" in query:
            q = query["q"][0].casefold()
            mode = query.get("qmode", ["titleCreatorYear"])[0]
            def hay(it):
                d = it["data"]
                keys = d.keys() if mode == "everything" else (("title", "DOI", "url") if mode == "fields" else ("title",))
                return [str(d[k]) for k in keys if isinstance(d.get(k), str)]
            rows = [it for it in rows if any(q in h.casefold() for h in hay(it))]
        return self.paginate(rows, query)


class ReadLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Handler.requests.clear()
        Handler.disabled = False

    def run_script(self, *args, base=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args],
                              capture_output=True, text=True)

    def lines(self, proc):
        return [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]

    def test_items_paginates_by_100(self):
        proc = self.run_script("items")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = self.lines(proc)
        self.assertEqual(len(rows), 250)
        self.assertEqual(rows[0]["key"], "K0000000")
        self.assertEqual(rows[0]["version"], 1)
        self.assertTrue(all("parentItem" not in r for r in rows))
        pages = [q for p, q in Handler.requests if p == f"{LIB}/items/top"]
        self.assertEqual([(q["start"], q["limit"]) for q in pages], [("0", "100"), ("100", "100"), ("200", "100")])

    def test_limit_caps_total_and_requests(self):
        proc = self.run_script("items", "--limit", "150")
        self.assertEqual(len(self.lines(proc)), 150)
        pages = [q for p, q in Handler.requests if p == f"{LIB}/items/top"]
        self.assertEqual([(q["start"], q["limit"]) for q in pages], [("0", "100"), ("100", "50")])

    def test_all_includes_children(self):
        rows = self.lines(self.run_script("items", "--all"))
        self.assertEqual(len(rows), 252)
        self.assertIn("ATT00001", {r["key"] for r in rows})

    def test_collection_filter(self):
        rows = self.lines(self.run_script("items", "--collection", "C1AAAAAA"))
        self.assertEqual(len(rows), 50)
        self.assertTrue(Handler.requests[0][0].startswith(f"{LIB}/collections/C1AAAAAA/items"))

    def test_keys_are_filtered_to_the_request(self):
        proc = self.run_script("items", "--key", "K0000000", "--key", "K0000007", "--key", "NOPE1234")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual([r["key"] for r in self.lines(proc)], ["K0000000", "K0000007"])
        self.assertIn("NOPE1234", proc.stderr)

    def test_q_and_since(self):
        rows = self.lines(self.run_script("items", "--q", "number 24"))
        self.assertEqual({r["key"] for r in rows}, {"K0000024", "K0000240", "K0000241", "K0000242", "K0000243",
                                                     "K0000244", "K0000245", "K0000246", "K0000247", "K0000248", "K0000249"})
        rows = self.lines(self.run_script("items", "--since", "248"))
        self.assertEqual([r["key"] for r in rows], ["K0000248", "K0000249"])

    def test_cite_resolution(self):
        proc = self.run_script("items", "--cite", "auth7")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([r["key"] for r in self.lines(proc)], ["K0000007"])
        self.assertEqual(Handler.requests[0][1], {"q": "auth7", "qmode": "everything", "limit": "50"})
        self.assertFalse(any(p == f"{LIB}/items/top" for p, _ in Handler.requests), "no fallback scan when the search hits")

        proc = self.run_script("items", "--cite", "nobody")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.lines(proc)[0]["code"], "cite_not_found")
        self.assertTrue(any(p == f"{LIB}/items/top" for p, _ in Handler.requests), "fallback scan ran")

        proc = self.run_script("items", "--cite", "dupkey")
        self.assertEqual(proc.returncode, 1)
        out = self.lines(proc)[0]
        self.assertEqual(out["code"], "cite_ambiguous")
        self.assertEqual(out["keys"], ["K0000001", "K0000002"])

    def test_item_and_children(self):
        proc = self.run_script("item", "K0000003")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.lines(proc)[0]["title"], "Paper number 3")
        proc = self.run_script("item", "NOPE1234")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.lines(proc)[0]["code"], "not_found")
        rows = self.lines(self.run_script("children", "K0000000"))
        self.assertEqual({r["key"] for r in rows}, {"ATT00001", "NOTE0001"})
        self.assertEqual(self.lines(self.run_script("children", "NOPE1234")), [], "whole-library quirk filtered out")

    def test_collections_and_tree(self):
        rows = self.lines(self.run_script("collections"))
        self.assertEqual(len(rows), 5)
        self.assertNotIn("path", rows[0])
        rows = self.lines(self.run_script("collections", "--tree"))
        self.assertEqual([r["path"] for r in rows], ["Agent", "医疗图像", "医疗图像/超声挑战赛"])
        self.assertEqual(rows[2]["parentCollection"], "C1AAAAAA")

    def test_tags_min_count(self):
        rows = self.lines(self.run_script("tags"))
        self.assertEqual(rows[0], {"tag": "CVPR", "type": 0, "count": 4})
        rows = self.lines(self.run_script("tags", "--min-count", "3"))
        self.assertEqual([r["tag"] for r in rows], ["CVPR", "Deep learning"])

    def test_schema_once(self):
        proc = self.run_script("schema")
        rows = self.lines(proc)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], 44)

    def test_unreachable_and_disabled(self):
        proc = self.run_script("items", base="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.lines(proc)[0]["code"], "zotero_unreachable")
        Handler.disabled = True
        proc = self.run_script("tags")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(self.lines(proc)[0]["code"], "local_api_disabled")


if __name__ == "__main__":
    unittest.main()
