# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/merge_items.py against a mock of Zotero's local API (items, children, collections, schema,
PATCH with a version check)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge_items.py"
LIB = "/api/users/0"
SERVER_ID = "MOCKSRV1"
SCHEMA = {"itemTypes": [
    {"itemType": "conferencePaper", "fields": [{"field": f} for f in ("title", "abstractNote", "pages", "extra", "DOI",
                                                                       "citationKey", "url")]
     + [{"field": "proceedingsTitle", "baseField": "publicationTitle"}]},
    {"itemType": "journalArticle", "fields": [{"field": f} for f in ("title", "abstractNote", "publicationTitle", "pages",
                                                                      "extra", "DOI", "citationKey", "ISSN")]}]}


def item(key, version, **data):
    return {"key": key, "version": version, "data": {"key": key, "version": version, **data}}


def library():
    return {
        "KEEPKEY1": item("KEEPKEY1", 10, itemType="conferencePaper", title="The paper", citationKey="liu2022paper",
                         pages="1-9", extra="arXiv: 2101.00001", collections=["COLLREAL"], tags=[{"tag": "task/Segmentation"}]),
        "DROPKEY1": item("DROPKEY1", 11, itemType="journalArticle", title="The Paper", abstractNote="An abstract.",
                         publicationTitle="Proceedings of X", pages="1-9", ISSN="1234-5678",
                         extra="arXiv: 2101.00001\nPMID: 7", collections=["COLLTMP1", "COLLOTHR"],
                         tags=[{"tag": "task/Segmentation"}, {"tag": "FooNet"}]),
        "KPDF0001": item("KPDF0001", 12, itemType="attachment", parentItem="KEEPKEY1", contentType="application/pdf", md5="same"),
        "DPDF0001": item("DPDF0001", 13, itemType="attachment", parentItem="DROPKEY1", contentType="application/pdf", md5="same"),
        "DPDF0002": item("DPDF0002", 14, itemType="attachment", parentItem="DROPKEY1", contentType="application/pdf", md5="new"),
        "DNOTE001": item("DNOTE001", 15, itemType="note", parentItem="DROPKEY1", note="<p>a note</p>"),
        "DSNAP001": item("DSNAP001", 16, itemType="attachment", parentItem="DROPKEY1", contentType="text/html", title="Snapshot"),
    }


COLLECTIONS = [{"key": "COLLTMP1", "data": {"name": "tmp"}}, {"key": "COLLREAL", "data": {"name": "Medical"}},
               {"key": "COLLOTHR", "data": {"name": "Recent"}}]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, status, body=None, headers=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        s = self.server.state
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/":
            return self.send(200, {}, {"Zotero-Server-ID": SERVER_ID})
        if path == "/api/schema":
            return self.send(200, SCHEMA)
        if path == f"{LIB}/collections":
            return self.send(200, COLLECTIONS)
        parts = path[len(LIB) + 1:].split("/")
        if parts[0] == "items" and len(parts) == 2:
            return self.send(200, s.items[parts[1]]) if parts[1] in s.items else self.send(404, {})
        if parts[0] == "items" and len(parts) == 3 and parts[2] == "children":
            return self.send(200, [v for v in s.items.values() if v["data"].get("parentItem") == parts[1]])
        if path == f"{LIB}/items":
            return self.send(200, list(s.items.values()))
        self.send(404, {})

    def do_PATCH(self):
        s = self.server.state
        key = self.path.rsplit("/", 1)[1]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Zotero-API-Key") != "k" or int(self.headers["If-Unmodified-Since-Version"]) != s.items[key]["version"]:
            return self.send(412, {})
        s.patches.append((key, body))
        it = s.items[key]
        it["data"].update(body)
        it["version"] = it["data"]["version"] = it["version"] + 100
        self.send(204)


class State:
    def __init__(self):
        self.items, self.patches = library(), []


class MergeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.tmp.name) / "config.json"
        cls.config.write_text(json.dumps({"zotero": {"key": "k", "serverID": SERVER_ID}}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        self.server.state = State()

    def run_merge(self, *argv):
        env = dict(os.environ, PAPER_TO_ZOTERO_CONFIG=str(self.config))
        r = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, *argv], capture_output=True, text=True, env=env)
        return r.returncode, json.loads(r.stdout)

    def test_the_plan(self):
        code, out = self.run_merge("--keep", "KEEPKEY1", "--drop", "DROPKEY1", "--dry-run")
        self.assertEqual((code, out["code"], out["dry_run"]), (0, "ok", True))
        self.assertEqual(out["fields"]["fill"], {"abstractNote": "An abstract.", "proceedingsTitle": "Proceedings of X",
                                                 "extra": "arXiv: 2101.00001\nPMID: 7"},
                         "base fields match across types; extra takes the missing lines")
        self.assertEqual(list(out["fields"]["conflicts"]), ["title"])
        self.assertEqual(out["fields"]["not_carried"], ["ISSN"], "no ISSN field on a conference paper")
        self.assertEqual(out["collections"]["after"], ["COLLREAL", "COLLOTHR"], "tmp left out")
        self.assertEqual(out["tags"]["added"], ["FooNet"])
        self.assertEqual([m["key"] for m in out["move"]], ["DPDF0002", "DNOTE001"])
        self.assertEqual({m["key"] for m in out["left_with_drop"]}, {"DPDF0001", "DSNAP001"})
        self.assertIn("trash_item.py --key DROPKEY1 --dry-run", out["next"])
        self.assertEqual(self.server.state.patches, [], "a dry run writes nothing")

    def test_the_merge_writes_and_reads_back(self):
        code, out = self.run_merge("--keep", "KEEPKEY1", "--drop", "DROPKEY1")
        self.assertEqual((code, out["code"]), (0, "ok"), out)
        items = self.server.state.items
        self.assertEqual(items["KEEPKEY1"]["data"]["abstractNote"], "An abstract.")
        self.assertEqual(items["DPDF0002"]["data"]["parentItem"], "KEEPKEY1")
        self.assertEqual(items["DNOTE001"]["data"]["parentItem"], "KEEPKEY1")
        self.assertEqual(items["DSNAP001"]["data"]["parentItem"], "DROPKEY1")
        self.assertIn("DROPKEY1", items, "nothing is deleted")

    def test_refusals(self):
        self.assertEqual(self.run_merge("--keep", "KEEPKEY1", "--drop", "KEEPKEY1")[1]["code"], "same_item")
        self.assertEqual(self.run_merge("--keep", "KEEPKEY1", "--drop", "DPDF0002")[1]["code"], "not_top_level")
        self.assertEqual(self.run_merge("--keep", "KEEPKEY1", "--drop", "NOSUCHK1")[1]["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
