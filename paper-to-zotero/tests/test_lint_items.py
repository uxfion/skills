# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/lint_items.py against a mock of Zotero's local API (paged /items and /collections)."""
import json
import socket
import subprocess
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_items.py"
LIB = "/api/users/0"


def closed_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def item(key, meta=None, **data):
    return {"key": key, "version": 1, "meta": {"parsedDate": "2021", **(meta or {})},
            "data": {"key": key, "version": 1, "collections": [], "tags": [], **data}}


ITEMS = [
    item("AAAAAAAA", itemType="journalArticle", title="Paper about segmentation networks", DOI="10.1000/A",
         collections=["COLL0001"], date="2021", url="https://x/a",
         abstractNote="In this work we propose FooNet, a network for segmentation, and we present Weight-Decomposed Low-Rank Adaptation."),
    item("BBBBBBBB", itemType="journalArticle", title="A second record of that paper", DOI="10.1000/a",
         collections=["COLL0002"], date="2021", abstractNote="x", tags=[{"tag": "FooNet"}]),
    item("WWWWWWWW", itemType="webpage", title="Project page", url="https://proxy.example/x"),
    item("DDDDDDDD", {"parsedDate": None}, itemType="conferencePaper", title="An old conference paper", date="十一月 23, 2021",
         collections=["COLL0001"]),
    item("JJJJJJJJ", itemType="journalArticle", title="A journal paper", DOI="10.1000/j", abstractNote="x",
         publicationTitle="Comput Biol Med", journalAbbreviation="Computers in Biology and Medicine", date="2021"),
    item("PPPPPPPP", itemType="preprint", title="Same Title Different Version", DOI="10.48550/arXiv.2101.00001",
         abstractNote="x", date="2021"),
    item("QQQQQQQQ", itemType="journalArticle", title="Same title, different version", DOI="10.1000/q",
         extra="arXiv: 2101.00001", abstractNote="x", date="2021"),
    item("TTTTTTTT", itemType="journalArticle", title="Paper about segmentation networks", DOI="10.1000/a", deleted=True),
    item("PDF00001", itemType="attachment", parentItem="AAAAAAAA", contentType="application/pdf", md5="m1", title="PDF"),
    item("PDF00002", itemType="attachment", parentItem="AAAAAAAA", contentType="application/pdf", md5="m2", title="PDF"),
    item("NOTE0001", itemType="note", parentItem="AAAAAAAA", note="<p>n</p>"),
]
COLLECTIONS = [{"key": "COLL0001", "data": {"name": "Medical", "parentCollection": False}},
               {"key": "COLL0002", "data": {"name": "Sub", "parentCollection": "COLL0001"}}]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        rows = {f"{LIB}/items": ITEMS, f"{LIB}/collections": COLLECTIONS}.get(url.path)
        if rows is None:
            self.send_response(404)
            self.end_headers()
            return
        start, limit = int(q.get("start", 0)), int(q.get("limit", 100))
        body = json.dumps(rows[start:start + limit]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


class LintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def run_lint(self, *argv):
        r = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, *argv], capture_output=True, text=True)
        lines = [json.loads(ln) for ln in r.stdout.splitlines() if ln.startswith("{")]
        return r.returncode, {ln["key"]: {p["code"]: p for p in ln["problems"]} for ln in lines if "key" in ln}, lines[-1]

    def test_the_whole_library(self):
        code, found, summary = self.run_lint()
        self.assertEqual(code, 1)
        self.assertEqual(found["AAAAAAAA"]["duplicate_of"], {"code": "duplicate_of", "by": "doi", "keys": ["BBBBBBBB"]},
                         "a trashed copy is not a duplicate")
        self.assertEqual(found["AAAAAAAA"]["multiple_pdfs"]["attachments"][1]["key"], "PDF00002")
        self.assertEqual(found["AAAAAAAA"]["name_not_tagged"]["name"], "FooNet")
        self.assertNotIn("name_not_tagged", found["BBBBBBBB"], "the tag is there")
        self.assertIn("unfiled_webpage", found["WWWWWWWW"])
        self.assertEqual(set(found["DDDDDDDD"]), {"date_unparseable", "missing_doi", "missing_abstract", "no_identifier"})
        self.assertEqual(found["JJJJJJJJ"]["abbreviation_misplaced"]["patch"],
                         {"publicationTitle": "Computers in Biology and Medicine", "journalAbbreviation": "Comput Biol Med"})
        self.assertEqual((found["PPPPPPPP"]["duplicate_of"]["by"], found["PPPPPPPP"]["duplicate_of"]["keys"]),
                         ("arxiv", ["QQQQQQQQ"]))
        self.assertNotIn("TTTTTTTT", found)
        self.assertEqual(summary["summary"]["items"], 7)

    def test_scope_chooses_what_is_reported_not_what_is_compared(self):
        code, found, summary = self.run_lint("--collection", "COLL0001")
        self.assertEqual(set(found), {"AAAAAAAA", "DDDDDDDD"})
        self.assertEqual(found["AAAAAAAA"]["duplicate_of"]["keys"], ["BBBBBBBB"], "found outside the collection")
        _, found, _ = self.run_lint("--collection", "COLL0001", "--recursive", "--only", "duplicate_of")
        self.assertEqual(set(found), {"AAAAAAAA", "BBBBBBBB"})
        code, found, summary = self.run_lint("--key", "JJJJJJJJ", "--only", "missing_doi")
        self.assertEqual((code, found, summary["summary"]["with_problems"]), (0, {}, 0))

    def test_cannot_check(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--base-url", f"http://127.0.0.1:{closed_port()}"], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "zotero_unreachable"))


if __name__ == "__main__":
    unittest.main()
