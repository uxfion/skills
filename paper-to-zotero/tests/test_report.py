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
        elif parts.path == f"{LIB}/tags":
            start = int(query.get("start", ["0"])[0])
            rows = [{"tag": t, "meta": {"numItems": n}} for t, n in getattr(self.server, "tags", {}).items()][start:start + 100]
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
        rows = {l.split(" | ")[0].lstrip("| ").split(" (")[0]: l for l in lines[2:5]}
        self.assertEqual(rows["liu2022progressive"],
                         "| liu2022progressive (≠ library: liuProgressiveResidualLearning2022) | Progressive \\| Residual | 2022 | 4L562S9K | 自然图像; 自然图像/Diffusion | 3 | PDF |")
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
        self.assertEqual(data["rows"][0], {"slug": "liu2022progressive", "citationKey": "liu2022progressive", "library_citationKey": "liuProgressiveResidualLearning2022", "cite_mismatch": True, "title": "Progressive | Residual",
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


class TestSections(unittest.TestCase):
    """The sections, from a work directory as ready.py / fetch.py / claim.py leave it."""

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.collections, self.server.calls = COLLECTIONS, []
        self.server.tags = {"method/Diffusion": 9, "method/BrandNew": 1, "task/Denoising": 2}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name) / "work"
        (self.work / "records").mkdir(parents=True)
        (self.work / ".started").touch()
        self.dl = Path(self.tmp.name) / "Downloads"
        self.dl.mkdir()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def record(self, slug, **rec):
        (self.work / "records" / f"{slug}.json").write_text(json.dumps({"slug": slug, "item": {"title": slug}, **rec}))

    def log(self, *lines):
        with open(self.work / "fetch.jsonl", "a") as fh:
            for line in lines:
                fh.write(json.dumps(line) + "\n")

    def run_json(self, *extra):
        p = subprocess.run([sys.executable, str(SCRIPT), "--base-url", self.base, "--json", *extra,
                            str(self.work / "records" / "*.json")], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout).get("sections", {})

    def test_not_obtained_lists_every_pass_and_the_never_tried(self):
        self.record("got")
        (self.work / "records" / "got.pdf").write_bytes(b"%PDF-1.4")
        self.record("lost")
        (self.work / "records" / "lost.html").write_text("<html></html>")
        self.record("untried")
        self.log({"event": "try", "slug": "lost", "pass": 1, "via": "http", "url": "https://repo.example/x", "result": "not_pdf"},
                 {"event": "try", "slug": "lost", "pass": 1, "via": "page", "url": "https://pub.example/a",
                  "result": "stopped", "why": "no_pdf_link"},
                 {"event": "try", "slug": "lost", "pass": 1, "via": "page", "result": "no_access", "by": "agent"},
                 {"event": "try", "slug": "lost", "pass": 3, "via": "snapshot", "url": "https://pub.example/a", "result": "ok"})
        rows = {r["slug"]: r for r in self.run_json("--no-resolve")["not_obtained"]}
        self.assertEqual(set(rows), {"lost", "untried"})
        self.assertEqual(rows["lost"]["passes"], {
            "1": ["http repo.example: not_pdf", "page pub.example: stopped (no_pdf_link)", "page: verdict no_access"],
            "3": ["snapshot pub.example: ok"]})
        self.assertTrue(rows["lost"]["snapshot"])
        self.assertEqual(rows["untried"]["passes"], {})

    def test_alternate_versions_and_attachments_to_clean(self):
        self.record("pre", attach={"key": "ATT1", "md5_ok": True, "filename": "x.pdf", "title": "Preprint (arXiv)",
                                   "version": "preprint"})
        self.record("pub", attach={"key": "ATT2", "md5_ok": True, "filename": "y.pdf", "title": "PDF", "version": "published"},
                    pdf={"code": "ok", "md5": "m1"},
                    found={"key": "ITEM2", "attachments": [
                        {"key": "ATT2", "contentType": "application/pdf", "title": "PDF"},
                        {"key": "SNAP", "contentType": "text/html", "linkMode": "imported_url", "title": "Snapshot"},
                        {"key": "OLDPRE", "contentType": "application/pdf", "title": "Preprint"},
                        {"key": "TWICE", "contentType": "application/pdf", "title": "Full Text PDF", "md5": "m1"},
                        {"key": "SUPP", "contentType": "application/pdf", "title": "Supplementary material"}]})
        sections = self.run_json("--no-resolve")
        self.assertEqual(sections["alternate_versions"], [{"slug": "pre", "version": "preprint", "title": "Preprint (arXiv)",
                                                           "attachment_key": "ATT1"}])
        self.assertEqual([(r["key"], r["reason"].split(" ")[0]) for r in sections["attachments_to_clean"]],
                         [("SNAP", "snapshot"), ("OLDPRE", "preprint"), ("TWICE", "the")])

    def test_new_tags_by_prefix(self):
        self.record("a", saved={"key": "NEW1", "tags": [{"tag": "method/BrandNew", "type": 0}, {"tag": "method/Diffusion", "type": 0},
                                                        {"tag": "task/Denoising", "type": 0}, {"tag": "auto", "type": 1}]})
        self.record("b", saved={"key": "NEW2", "tags": [{"tag": "task/Denoising", "type": 0}]})
        self.assertEqual(self.run_json()["new_tags"], {"method/": [{"tag": "method/BrandNew", "items": ["a"]}],
                                                       "task/": [{"tag": "task/Denoising", "items": ["a", "b"]}]})
        self.assertNotIn("new_tags", self.run_json("--no-resolve"))

    def test_leftovers_and_stops(self):
        self.record("x")
        left = self.dl / "invoice.pdf"
        left.write_bytes(b"%PDF")
        (self.work / "unverified").mkdir()
        (self.work / "unverified" / "x.page.pdf").write_bytes(b"%PDF")
        self.log({"event": "claim", "file": "invoice.pdf", "result": "left", "why": "unmatched", "source": str(left)},
                 {"event": "claim", "file": "gone.pdf", "result": "left", "why": "unmatched", "source": str(self.dl / "gone.pdf")},
                 {"event": "claim", "file": "x.page.pdf", "slug": "x", "result": "unverified", "source": "https://pub.example/x.pdf"},
                 {"event": "try", "slug": "x", "pass": 1, "via": "page", "url": "https://sso.example.edu/login",
                  "result": "stopped", "why": "no_pdf_link"},
                 {"event": "try", "slug": "x", "pass": 1, "via": "page", "result": "gate_timeout", "by": "agent"})
        sections = self.run_json("--no-resolve")
        self.assertEqual(sections["leftovers"], {"downloads": [{"file": "invoice.pdf", "why": "unmatched", "in_library": None}],
                                                 "unverified": [{"file": "x.page.pdf", "source": "https://pub.example/x.pdf"}]})
        self.assertEqual([(s["slug"], s["why"], s["verdict"]) for s in sections["stops"]], [("x", "no_pdf_link", "gate_timeout")])
        p = subprocess.run([sys.executable, str(SCRIPT), "--no-resolve", str(self.work / "records" / "*.json")],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        for title in ("### 无法获取", "### 残留", "### 停下与门禁"):
            self.assertIn(title, p.stdout)


if __name__ == "__main__":
    unittest.main()
