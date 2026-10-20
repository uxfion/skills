# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/report.py: the rows read live from the fake Zotero, the sections from the records and fetch.jsonl."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

report = load("report")


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_collection("AAAAAAAA", "自然图像")
        z.add_collection("BBBBBBBB", "Diffusion", "AAAAAAAA")
        z.add_item("ITEM0001", itemType="journalArticle", title="A Paper", date="2022-03", citationKey="liu2022paper",
                   collections=["BBBBBBBB"], tags=[{"tag": "method/BrandNew", "type": 0}, {"tag": "method/Diffusion", "type": 0}])
        z.add_item("ATTPDF01", itemType="attachment", parentItem="ITEM0001", title="PDF", contentType="application/pdf", md5="m1")
        z.add_item("SNAP0001", itemType="attachment", parentItem="ITEM0001", title="Snapshot", contentType="text/html",
                   linkMode="imported_url")
        z.add_item("TWICE001", itemType="attachment", parentItem="ITEM0001", title="Full Text PDF", contentType="application/pdf", md5="m1")
        z.add_item("OTHER001", itemType="journalArticle", title="Other", tags=[{"tag": "method/Diffusion", "type": 0}])
        z.add_item("PRE00001", itemType="preprint", title="Kept Preprint", date="2023", citationKey="kim2023kept")
        z.add_item("ATTPRE01", itemType="attachment", parentItem="PRE00001", title="Preprint (arXiv)", contentType="application/pdf")
        self.work = run.Work(Path(tempfile.mkdtemp(prefix="p2z-report-")))
        self.work.records.mkdir()
        self.work.unverified.mkdir()
        self.dl = self.work.root / "Downloads"
        self.dl.mkdir()

    def record(self, slug, **rec):
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps({"item": {"title": slug.title()}, **rec}))
        return path

    def run_(self, *argv, base_url=None):
        return call(report, *argv, *sorted(self.work.records.glob("*.json")), "--base-url", base_url or self.zot.base_url)

    def test_rows_and_sections(self):
        self.record("liu", citationKey="liu2022", saved={"key": "ITEM0001", "version": 1, "citationKey": "liu2022paper", "created_at": "x"},
                    attach={"attachment": "ATTPDF01", "md5": "m1", "kind": "published", "title": "PDF"})
        self.record("kim", saved={"key": "PRE00001"}, keep_preprint="the user wants the preprint",
                    attach={"attachment": "ATTPRE01", "md5": "m2", "kind": "preprint", "title": "Preprint (arXiv)"})
        self.record("lost", blocker="the last pass with the user")
        (self.work.records / "lost.html").write_text("<html></html>")
        (self.work.unverified / "lost.file.pdf").write_bytes(b"%PDF")
        left = self.dl / "invoice.pdf"
        left.write_bytes(b"%PDF")
        for e in ({"event": "try", "slug": "lost", "pass": 1, "route": "open", "url": "https://repo.example/x", "result": "wrong_file"},
                  {"event": "stop", "slug": "lost", "pass": 1, "route": "publisher", "url": "https://doi.org/10.1/a",
                   "page": "https://pub.example/a", "why": "no_pdf_link"},
                  {"event": "try", "slug": "lost", "pass": 1, "route": "publisher", "url": "https://doi.org/10.1/a",
                   "result": "no_access", "by": "agent"},
                  {"event": "claim", "file": "invoice.pdf", "result": "left", "why": "unmatched", "source": str(left)},
                  {"event": "accept", "slug": "kim", "file": "kim.preprint.pdf", "reason": "a scan", "md5": "m2"}):
            self.work.append(e)
        r = self.run_("--json")
        self.assertEqual(r.code, 0, r)
        out = json.loads(r.out)
        rows = {row["slug"]: row for row in out["rows"]}
        self.assertEqual((rows["liu"]["citationKey"], rows["liu"]["cite_mismatch"], rows["liu"]["collections"], rows["liu"]["year"],
                          rows["liu"]["file"]), ("liu2022paper", True, ["自然图像/Diffusion"], "2022", "PDF"), "the library as it is now")
        self.assertEqual((rows["kim"]["file"], rows["lost"]["item_key"], rows["lost"]["file"]), ("PDF", None, None))
        self.assertEqual(out["summary"], {"total": 3, "in_library": 2, "with_pdf": 2, "with_snapshot": 0, "missing": 1, "blocked": 1})
        s = out["sections"]
        self.assertEqual(s["not_obtained"], [{"slug": "lost", "snapshot": True, "passes": {"1": [
            "open repo.example: wrong_file", "publisher doi.org: verdict no_access"]}}])
        self.assertEqual([(a["slug"], a["kind"]) for a in s["alternate_versions"]], [("kim", "preprint")])
        self.assertEqual(s["preprint_kept"], [{"slug": "kim", "reason": "the user wants the preprint"}])
        self.assertEqual(s["accepted"], [{"slug": "kim", "file": "kim.preprint.pdf", "reason": "a scan"}])
        self.assertEqual([(c["key"], c["reason"].split(" ")[0]) for c in s["attachments_to_clean"]], [("TWICE001", "the"), ("SNAP0001", "snapshot")])
        self.assertEqual(s["new_tags"], [{"tag": "method/BrandNew", "items": ["liu2022paper"]}])
        self.assertEqual([x["file"] for x in s["leftovers"]], ["Downloads/invoice.pdf", "unverified/lost.file.pdf"])
        self.assertEqual([(x["slug"], x["verdict"]) for x in s["stops"]], [("lost", "no_access")])
        md = self.run_().out
        for heading in ("| citationKey |", "liu2022paper (record: liu2022)", "### 无法获取", "### 待清理附件", "trash_item.py --dry-run --key TWICE001 SNAP0001"):
            self.assertIn(heading, md)

    def test_cannot_read(self):
        r = call(report)
        self.assertEqual((r.code, r.err_lines[0]["code"]), (1, "no_records"))
        self.record("x")
        r = self.run_(base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.err_lines[0]["code"], r.out), (2, "zotero_unreachable", ""))

    def test_smoke(self):
        r = smoke("report", self.record("x"), "--base-url", self.zot.base_url)
        self.assertEqual(r.code, 0, r)
        self.assertIn("**Summary**", r.out)


if __name__ == "__main__":
    unittest.main()
