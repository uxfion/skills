# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/report.py: the rows read live from the fake Zotero, the sections from the records and their results."""
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
        # ITEM0001: this run attached Published-IEEE; the item had a snapshot standing in for it, the same file under
        # an old title, an in-press copy from the same site, and a preprint from another site, which stays.
        att = lambda key, title, ctype="application/pdf", **kw: z.add_item(  # noqa: E731
            key, itemType="attachment", parentItem="ITEM0001", title=title, contentType=ctype, linkMode="imported_url", **kw)
        att("ATTPDF01", "Published-IEEE", md5="m1", dateAdded="2026-03-01")
        att("SNAP0001", "Snapshot-IEEE", "text/html", dateAdded="2025-01-01")
        att("TWICE001", "Full Text PDF", md5="m1", dateAdded="2025-02-01")
        att("PRESS001", "Accepted-IEEE-in_press", md5="m3", dateAdded="2025-03-01")
        att("ARXIV001", "Preprint-arXiv-v2", md5="m4", dateAdded="2025-04-01")
        z.add_item("OTHER001", itemType="journalArticle", title="Other", tags=[{"tag": "method/Diffusion", "type": 0}])
        z.add_item("PRE00001", itemType="preprint", title="Kept Preprint", date="2023", citationKey="kim2023kept")
        z.add_item("ATTPRE01", itemType="attachment", parentItem="PRE00001", title="Preprint-arXiv-v1", contentType="application/pdf")
        z.add_item("UNSURE01", itemType="journalArticle", title="Unsure", date="2024", citationKey="roe2024unsure")
        z.add_item("ATTUNK01", itemType="attachment", parentItem="UNSURE01", title="Unknown-Elsevier", contentType="application/pdf")
        z.add_item("HAD00001", itemType="journalArticle", title="Had It", date="2021", citationKey="doe2021had")
        z.add_item("ATTOLD01", itemType="attachment", parentItem="HAD00001", title="PDF", contentType="application/pdf", md5="m9")
        self.work = run.Work(Path(tempfile.mkdtemp(prefix="p2z-report-")))
        self.work.records.mkdir()
        self.results = self.work.root / "fetch" / "results"
        self.results.mkdir(parents=True)

    def record(self, slug, files=(), outcome=None, **rec):
        """A record and its result: files [(name, md5, kind, label title, check, accepted_reason?)]."""
        res = self.results / f"{slug}.json"
        res.write_text(json.dumps({"slug": slug, "outcome": outcome or {"status": "got", "tried": [], "stop": None}, "files": [
            {"name": f[0], "md5": f[1], "kind": f[2], "label": {"title": f[3]}, "check": f[4],
             **({"accepted_reason": f[5]} if len(f) > 5 else {})} for f in files]}))
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps({"fetched": str(res), "item": {"title": slug.title()}, **rec}))
        return path

    def run_(self, *argv, base_url=None):
        return call(report, *argv, *sorted(self.work.records.glob("*.json")), "--base-url", base_url or self.zot.base_url)

    def test_rows_and_sections(self):
        self.record("liu", [("liu.pdf", "m1", "published", "Published-IEEE", "ok")], citationKey="liu2022",
                    saved={"key": "ITEM0001", "version": 1, "citationKey": "liu2022paper", "created_at": "x"},
                    attach=[{"attachment": "ATTPDF01", "md5": "m1", "title": "Published-IEEE", "kind": "published"}])
        self.record("kim", [("kim.preprint.pdf", "m2", "preprint", "Preprint-arXiv-v1", "accepted", "a scan")],
                    saved={"key": "PRE00001"}, keep_preprint="the user wants the preprint",
                    attach=[{"attachment": "ATTPRE01", "md5": "m2", "title": "Preprint-arXiv-v1", "kind": "preprint"}])
        self.record("roe", [("roe.pdf", "m5", "published", "Unknown-Elsevier", "ok")], saved={"key": "UNSURE01"},
                    attach=[{"attachment": "ATTUNK01", "md5": "m5", "title": "Unknown-Elsevier", "kind": "published"}])
        doe = run.read(self.record("doe", [("doe.pdf", "m9", "published", "Published-Springer", "ok")],
                                   attach=[{"attachment": "ATTOLD01", "md5": "m9", "title": "PDF", "kind": "published", "existing": True}]))
        run.stamp(doe, "found", {"code": "found", "key": "HAD00001"})  # the item was in the library: it had this file
        doe.save()
        stop = {"route": "publisher", "why": "no_pdf_link", "url": "https://pub.example/a"}
        self.record("lost", [("lost.html", "m7", "snapshot", "Snapshot-Example", "ok")], blocker="the last pass with the user",
                    outcome={"status": "not_got", "tried": ["repo.example", "pub.example"], "stop": stop})
        r = self.run_("--json")
        self.assertEqual(r.code, 0, r)
        out = json.loads(r.out)
        rows = {row["slug"]: row for row in out["rows"]}
        self.assertEqual((rows["liu"]["citationKey"], rows["liu"]["cite_mismatch"], rows["liu"]["collections"], rows["liu"]["year"],
                          rows["liu"]["file"]), ("liu2022paper", True, ["自然图像/Diffusion"], "2022", "PDF"), "the library as it is now")
        self.assertEqual(rows["liu"]["attachments"], ["Published-IEEE", "Accepted-IEEE-in_press", "Preprint-arXiv-v2", "Full Text PDF",
                                                      "Snapshot-IEEE"], "best first")
        self.assertEqual((rows["kim"]["file"], rows["roe"]["file"], rows["lost"]["key"], rows["lost"]["file"]), ("PDF", "PDF", None, None))
        self.assertEqual(out["summary"], {"total": 5, "in_library": 4, "with_pdf": 4, "with_snapshot": 0, "missing": 1, "blocked": 1})
        s = out["sections"]
        self.assertEqual(s["not_obtained"], [{"slug": "lost", "status": "not_got", "tried": ["repo.example", "pub.example"],
                                              "stop": stop, "snapshot": True}])
        self.assertEqual([(a["slug"], a["title"]) for a in s["alternate_versions"]], [("kim", "Preprint-arXiv-v1")])
        self.assertEqual([(a["slug"], a["title"]) for a in s["unknown_versions"]], [("roe", "Unknown-Elsevier")])
        self.assertEqual(s["preprint_kept"], [{"slug": "kim", "reason": "the user wants the preprint"}])
        self.assertEqual(s["accepted"], [{"slug": "kim", "file": "kim.preprint.pdf", "reason": "a scan"}])
        self.assertEqual(sorted((c["attachment"], c["reason"].split(" ")[0]) for c in s["attachments_to_clean"]),
                         [("PRESS001", "'Accepted-IEEE-in_press',"), ("SNAP0001", "snapshot"), ("TWICE001", "the")],
                         "the arXiv preprint, another source, stays")
        self.assertEqual(s["renames"], [{"slug": "doe", "attachment": "ATTOLD01", "title": "PDF", "suggested": "Published-Springer"}])
        self.assertEqual(s["new_tags"], [{"tag": "method/BrandNew", "items": ["liu2022paper"]}])
        self.assertFalse({"leftovers", "stops"} & set(s), "what the fetching left behind is paper-fetch's")
        md = self.run_().out
        for heading in ("| citationKey |", "liu2022paper (record: liu2022)", "### 无法获取", "not_got | repo.example, pub.example | "
                        "publisher no_pdf_link https://pub.example/a", "### 待清理附件", "### 版本未定",
                        "### 建议改名", "trash_item.py --dry-run --key ", "Published-IEEE; Accepted-IEEE-in_press"):
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
