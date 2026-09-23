# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/report.py: the Markdown table, the JSON form, and collection-name resolution against a fake local API."""
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

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "report.py"
LIB = "/api/users/0"

COLLECTIONS = [
    {"key": "COLLROOT", "name": "自然图像", "parent": None},
    {"key": "COLLSUB1", "name": "Diffusion", "parent": "COLLROOT"},
    {"key": "COLLGONE", "name": "gone", "parent": None, "deleted": True},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        self.server.calls.append(parts.path)
        if parts.path == f"{LIB}/collections":
            limit, start = int(query.get("limit", ["25"])[0]), int(query.get("start", ["0"])[0])
            rows = [{"key": c["key"], "version": 1, "data": {"key": c["key"], "name": c["name"], "parentCollection": c["parent"] or False,
                                                              **({"deleted": True} if c.get("deleted") else {})}}
                    for c in self.server.collections[start:start + limit]]
            out, status = json.dumps(rows).encode("utf-8"), 200
        else:
            out, status = b"no route", 404
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


RECORDS = [
    {"slug": "liu2022progressive", "citationKey": "liu2022progressive",
     "item": {"itemType": "journalArticle", "title": "Progressive | Residual", "date": "2022-03-01"},
     "tags": [{"tag": "a", "type": 0}], "collection": "COLLROOT",
     "found": {"key": "4L562S9K", "citationKey": "liuProgressiveResidualLearning2022", "collections": ["COLLROOT", "COLLSUB1"],
               "tags": [{"tag": "x", "type": 0}, {"tag": "y", "type": 1}, {"tag": "z", "type": 0}],
               "attachments": [{"key": "B4K98DC7", "contentType": "application/pdf", "linkMode": "imported_file", "filename": "liu.pdf"}]}},
    {"slug": "new2026thing", "item": {"itemType": "preprint", "title": "A New Thing", "date": "2026"}, "tags": [], "collection": "COLLSUB1",
     "saved": {"key": "AAAAAAAA", "version": 1}, "found": {"key": "AAAAAAAA", "citationKey": "new2026thing", "collections": ["COLLSUB1"],
                                                            "tags": [], "attachments": []},
     "attach": {"key": "BBBBBBBB", "md5_ok": True, "filename": "page.html", "url": "https://example.org/x.html"}},
    {"slug": "nokey2025paper", "item": {"itemType": "journalArticle", "title": "Not yet", "date": ""}, "tags": [{"tag": "t", "type": 0}],
     "collection": "COLLROOT"},
]
BLOCKED = {"slug": "blocked2025", "item": {"title": "Blocked", "date": "2025"}, "blocker": "IEEE gate pending since 10:02"}


class TestReport(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.collections = COLLECTIONS
        self.server.calls = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for r in RECORDS:
            (self.dir / f"{r['slug']}.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_script(self, *args, stdin=None, base=None):
        p = subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args], capture_output=True, text=True,
                           input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)
        return p.returncode, p.stdout, p.stderr

    def test_markdown_table_and_summary(self):
        rc, out, err = self.run_script(str(self.dir / "*.json"))
        self.assertEqual(rc, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], "| citationKey | title | year | item key | collection(s) | tags | file |")
        self.assertEqual(lines[1], "|---|---|---|---|---|---|---|")
        rows = {l.split(" | ")[0].lstrip("| "): l for l in lines[2:5]}
        self.assertEqual(rows["liu2022progressive"],
                         "| liu2022progressive | Progressive \\| Residual | 2022 | 4L562S9K | 自然图像; 自然图像/Diffusion | 3 | PDF |")
        self.assertEqual(rows["new2026thing"], "| new2026thing | A New Thing | 2026 | AAAAAAAA | 自然图像/Diffusion | 0 | snapshot |")
        self.assertEqual(rows["*nokey2025paper*"], "| *nokey2025paper* | Not yet | — | — | 自然图像 | 1 | — |")
        self.assertEqual(lines[-1], "**Summary**: total 3 · in library 2 · with PDF 1 · with snapshot 1 · missing 1 · blocked 0")
        self.assertIn(f"{LIB}/collections", self.server.calls)

    def test_blocker_column_appears_only_when_needed(self):
        (self.dir / "blocked.json").write_text(json.dumps(BLOCKED), encoding="utf-8")
        rc, out, err = self.run_script(str(self.dir / "blocked.json"), str(self.dir / "new2026thing.json"), "--no-resolve")
        self.assertEqual(rc, 0, err)
        lines = out.splitlines()
        self.assertTrue(lines[0].endswith("| file | blocker |"))
        self.assertEqual(lines[2], "| *blocked2025* | Blocked | 2025 | — | — | 0 | — | IEEE gate pending since 10:02 |")
        self.assertEqual(lines[3], "| new2026thing | A New Thing | 2026 | AAAAAAAA | COLLSUB1 | 0 | snapshot | — |")
        self.assertIn("missing 1 · blocked 1", lines[-1])
        self.assertEqual(self.server.calls, [])

    def test_json_from_stdin(self):
        jsonl = "\n".join(json.dumps(r, ensure_ascii=False) for r in RECORDS)
        rc, out, err = self.run_script("--json", stdin=jsonl)
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["code"], "ok")
        self.assertEqual(data["summary"], {"total": 3, "in_library": 2, "with_pdf": 1, "with_snapshot": 1, "missing": 1, "blocked": 0})
        self.assertEqual(data["rows"][0], {"slug": "liu2022progressive", "citationKey": "liu2022progressive", "title": "Progressive | Residual",
                                           "year": "2022", "item_key": "4L562S9K", "collections": ["自然图像", "自然图像/Diffusion"],
                                           "tags": 3, "file": "PDF", "blocker": None})
        self.assertEqual(data["rows"][2]["citationKey"], None)
        self.assertEqual(data["rows"][2]["item_key"], None)
        rc, out, err = self.run_script("--json", stdin=json.dumps(RECORDS))
        self.assertEqual(len(json.loads(out)["rows"]), 3)

    def test_found_citation_key_used_when_record_has_none(self):
        rec = dict(RECORDS[0])
        rec.pop("citationKey")
        rc, out, _ = self.run_script("--json", "--no-resolve", stdin=json.dumps(rec))
        self.assertEqual(json.loads(out)["rows"][0]["citationKey"], "liuProgressiveResidualLearning2022")

    def test_unreachable_api_prints_keys(self):
        rc, out, err = self.run_script(str(self.dir / "liu2022progressive.json"), base="http://127.0.0.1:1")
        self.assertEqual(rc, 0)
        self.assertIn("| COLLROOT; COLLSUB1 |", out)
        self.assertIn("printing keys", err)

    def test_no_records(self):
        rc, out, err = self.run_script(stdin="")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err.strip().splitlines()[-1])["code"], "no_records")
        rc, out, err = self.run_script(str(self.dir / "nothing-*.json"))
        self.assertEqual(json.loads(err.strip().splitlines()[-1])["code"], "record_not_found")


if __name__ == "__main__":
    unittest.main()
