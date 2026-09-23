# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/export_bib.py: key collection, chunking, ordering and the citationKey checks against a fake local API."""
import copy
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

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_bib.py"
LIB = "/api/users/0"


class FakeZotero:
    """Items (top-level unless parentItem), collections with membership, itemKey filter, and a BibTeX export in stored order."""

    def __init__(self, items, collections):
        self.items = items            # key -> data (with "collections": [...])
        self.collections = collections  # key -> {"name", "parent", "deleted"?}
        self.calls = []

    def row(self, key):
        return {"key": key, "version": 1, "data": {"key": key, **self.items[key]}}

    def page(self, keys, query):
        limit, start = int(query.get("limit", ["25"])[0]), int(query.get("start", ["0"])[0])
        return keys[start:start + limit]

    def bibtex(self, keys):
        out = ["", ""]
        for k in keys:
            d = self.items[k]
            if d.get("itemType") in ("note", "attachment"):
                continue
            cite = d.get("citationKey") or f"gen_{k.lower()}"
            out.append(f"@article{{{cite},\n\ttitle = {{{d.get('title', '')}}},\n\tkey = {{{k}}},\n}}\n")
        return "\n".join(out)

    def handle(self, method, path, query, body, headers):
        if path == "/api/":
            return 200, {"Zotero-Server-ID": "sid"}, {"ok": True}
        if path == f"{LIB}/collections":
            keys = list(self.collections)
            rows = [{"key": k, "version": 1, "data": {"key": k, "name": c["name"], "parentCollection": c["parent"] or False,
                                                       **({"deleted": True} if c.get("deleted") else {})}}
                    for k, c in self.collections.items()]
            return 200, {}, self.page(rows, query)
        if path.startswith(f"{LIB}/collections/") and path.endswith("/items/top"):
            ck = path.split("/")[5]
            keys = [k for k, d in self.items.items() if ck in d.get("collections", []) and not d.get("parentItem")]
            return 200, {}, [self.row(k) for k in self.page(keys, query)]
        if path.startswith(f"{LIB}/collections/"):
            ck = path.rsplit("/", 1)[1]
            if ck not in self.collections:
                return 404, {}, b"Not found"
            c = self.collections[ck]
            return 200, {}, {"key": ck, "version": 1, "data": {"key": ck, "name": c["name"], "parentCollection": c["parent"] or False,
                                                                **({"deleted": True} if c.get("deleted") else {})}}
        if path == f"{LIB}/items/top":
            keys = [k for k, d in self.items.items() if not d.get("parentItem")]
            if "itemKey" in query:
                wanted = set(query["itemKey"][0].split(","))
                keys = [k for k in keys if k in wanted]  # stored order, not request order
            if query.get("format") == ["bibtex"]:
                return 200, {"Content-Type": "text/plain"}, self.bibtex(self.page(keys, query)).encode("utf-8")
            return 200, {}, [self.row(k) for k in self.page(keys, query)]
        if path == f"{LIB}/items":
            q = query.get("q", [""])[0]
            keys = [k for k, d in self.items.items() if q and q in json.dumps(d)]
            return 200, {}, [self.row(k) for k in self.page(keys, query)]
        return 404, {}, b"no route"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        fake = self.server.fake
        fake.calls.append({"path": parts.path, "query": query, "url_len": len(self.path)})
        status, extra, out = fake.handle("GET", parts.path, query, b"", self.headers)
        if not isinstance(out, bytes):
            out = json.dumps(out, ensure_ascii=False).encode("utf-8")
            extra = {**extra, "Content-Type": "application/json"}
        self.send_response(status)
        for k, v in extra.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def item(cite, title, colls, **extra):
    return {"itemType": "journalArticle", "title": title, "citationKey": cite, "collections": colls, "tags": [], **extra}


ITEMS = {
    "KEY00001": item("zhou2021handheld", "Handheld", ["COLLROOT"]),
    "KEY00002": item("liu2022progressive", "Progressive", ["COLLROOT", "COLLSUB1"]),
    "KEY00003": item("Abel2019first", "First", ["COLLSUB1"]),
    "KEY00004": item("", "No key yet", ["COLLSUB2"]),
    "KEY00005": item("dup2020twice", "Twice a", ["COLLSUB2"]),
    "KEY00006": item("dup2020twice", "Twice b", ["COLLSUB2"]),
    "KEY00007": item("lonely2018", "Lonely", []),
    "NOTE0001": {"itemType": "note", "note": "<p>standalone</p>", "collections": ["COLLROOT"], "tags": []},
    "ATTA0001": {"itemType": "attachment", "parentItem": "KEY00001", "title": "PDF", "collections": [], "tags": []},
}
COLLECTIONS = {
    "COLLROOT": {"name": "root", "parent": None},
    "COLLSUB1": {"name": "sub1", "parent": "COLLROOT"},
    "COLLSUB2": {"name": "sub2", "parent": "COLLSUB1"},
    "COLLGONE": {"name": "gone", "parent": "COLLROOT", "deleted": True},
    "COLLELSE": {"name": "else", "parent": None},
}


def entries(text):
    return [line.split("{", 1)[1].rstrip(",") for line in text.splitlines() if line.startswith("@")]


class TestExportBib(unittest.TestCase):
    def setUp(self):
        self.fake = FakeZotero(copy.deepcopy(ITEMS), copy.deepcopy(COLLECTIONS))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.fake = self.fake
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_script(self, *args, stdin=None):
        p = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, *args], capture_output=True, text=True,
                           input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)
        summary = json.loads(p.stderr.strip().splitlines()[-1]) if p.stderr.strip() else None
        return p.returncode, p.stdout, summary, p.stderr

    def bibtex_calls(self):
        return [c for c in self.fake.calls if c["path"] == f"{LIB}/items/top" and c["query"].get("format") == ["bibtex"]]

    def test_collection_top_level_only_and_ordered(self):
        rc, out, summary, err = self.run_script("--collection", "COLLROOT")
        self.assertEqual(rc, 0, err)
        self.assertEqual(summary["code"], "ok")
        self.assertEqual(summary["count"], 2)
        self.assertEqual(entries(out), ["liu2022progressive", "zhou2021handheld"])
        self.assertEqual(summary["skipped"], [{"key": "NOTE0001", "reason": "standalone note"}])
        self.assertTrue(out.endswith("}\n"))
        self.assertNotIn("\n\n\n", out)

    def test_recursive_walks_live_subcollections_and_dedupes(self):
        rc, out, summary, err = self.run_script("--collection", "COLLROOT", "--recursive")
        self.assertEqual(rc, 1, err)
        self.assertEqual(summary["collections"], ["COLLROOT", "COLLSUB1", "COLLSUB2"])
        # ordered case-insensitively by BibTeX key; KEY00002 appears once although it sits in two collections
        self.assertEqual(entries(out), ["Abel2019first", "dup2020twice", "dup2020twice", "gen_key00004", "liu2022progressive", "zhou2021handheld"])
        self.assertEqual(summary["missing_citation_key"], ["KEY00004"])
        self.assertEqual(summary["duplicate_keys"], [{"citationKey": "dup2020twice", "keys": ["KEY00005", "KEY00006"]}])
        self.assertEqual(summary["problems"], ["missing_citation_key", "duplicate_keys"])
        self.assertEqual(summary["code"], "missing_citation_key")

    def test_collection_not_found_and_trashed(self):
        for ck in ("ZZZZZZZZ", "COLLGONE"):
            rc, out, summary, _ = self.run_script("--collection", ck)
            self.assertEqual(rc, 1)
            self.assertEqual(summary["code"], "collection_not_found")
            self.assertEqual(out, "")

    def test_keys_cites_and_not_found(self):
        rc, out, summary, err = self.run_script("--key", "KEY00007,ZZZZZZZZ", "--key", "KEY00001", "--cite", "liu2022progressive")
        self.assertEqual(rc, 1, err)
        self.assertEqual(entries(out), ["liu2022progressive", "lonely2018", "zhou2021handheld"])
        self.assertEqual(summary["not_found"], ["ZZZZZZZZ"])
        self.assertEqual(summary["code"], "not_found")
        self.assertEqual(summary["count"], 3)

    def test_cite_unresolved_is_isolated(self):
        rc, out, summary, err = self.run_script("--cite", "nobody2099", "--cite", "dup2020twice", "--cite", "lonely2018")
        self.assertEqual(rc, 1)
        self.assertEqual(entries(out), ["lonely2018"])
        self.assertEqual([u["code"] for u in summary["unresolved"]], ["cite_not_found", "cite_ambiguous"])
        self.assertEqual(sorted(summary["unresolved"][1]["keys"]), ["KEY00005", "KEY00006"])

    def test_chunks_of_50(self):
        for i in range(120):
            self.fake.items[f"BULK{i:04d}"] = item(f"bulk{i:04d}", f"Bulk {i}", ["COLLELSE"])
        rc, out, summary, err = self.run_script("--collection", "COLLELSE")
        self.assertEqual(rc, 0, err)
        self.assertEqual(summary["count"], 120)
        calls = self.bibtex_calls()
        sizes = [len(c["query"]["itemKey"][0].split(",")) for c in calls]
        self.assertEqual(sizes, [50, 50, 20])
        self.assertTrue(all(c["query"].get("limit") == ["100"] for c in calls))
        self.assertEqual(entries(out), sorted(entries(out), key=str.lower))
        self.assertEqual(len(entries(out)), 120)

    def test_records_from_files_stdin_and_out(self):
        d = Path(self.tmp.name)
        (d / "a.json").write_text(json.dumps({"slug": "a", "saved": {"key": "KEY00001"}}), encoding="utf-8")
        (d / "b.json").write_text(json.dumps({"slug": "b", "found": {"key": "KEY00003"}}), encoding="utf-8")
        (d / "c.json").write_text(json.dumps({"slug": "c", "item": {"title": "not in library"}}), encoding="utf-8")
        out_file = d / "ref.bib"
        rc, out, summary, err = self.run_script(str(d / "*.json"), "--out", str(out_file))
        self.assertEqual(rc, 1, err)
        self.assertEqual(out, "")
        self.assertEqual(entries(out_file.read_text(encoding="utf-8")), ["Abel2019first", "zhou2021handheld"])
        self.assertEqual(summary["no_item_key"], ["c"])
        self.assertEqual(summary["code"], "no_item_key")
        jsonl = "\n".join(json.dumps(r) for r in [{"slug": "a", "saved": {"key": "KEY00001"}}, {"slug": "b", "found": {"key": "KEY00007"}}])
        rc, out, summary, err = self.run_script(stdin=jsonl)
        self.assertEqual(rc, 0, err)
        self.assertEqual(entries(out), ["lonely2018", "zhou2021handheld"])
        rc, out, summary, err = self.run_script(stdin=json.dumps([{"slug": "a", "saved": {"key": "KEY00001"}}]))
        self.assertEqual(entries(out), ["zhou2021handheld"])
        rc, out, summary, err = self.run_script(stdin="")
        self.assertEqual(rc, 1)
        self.assertEqual(summary["code"], "no_records")

    def test_empty_collection_is_no_records(self):
        self.fake.collections["COLLNONE"] = {"name": "empty", "parent": None}
        rc, out, summary, _ = self.run_script("--collection", "COLLNONE")
        self.assertEqual(rc, 1)
        self.assertEqual(summary["code"], "no_records")
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
