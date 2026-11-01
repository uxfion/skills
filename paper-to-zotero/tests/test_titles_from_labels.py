# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/titles_from_labels.py against the fake Zotero: paper-fetch's own result fixtures, their files
found by md5, the lines it lists handed to update_item --batch."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
from fake_zotero import FakeZotero

FIXTURES = Path(__file__).resolve().parents[2] / "paper-fetch" / "tests" / "fixtures" / "results"
titles_from_labels, update_item = load("titles_from_labels"), load("update_item")
LIU, LIU_PDF, LIU_PKG, SHINN, SHINN_PRE, STUB, STUB_PDF = (
    "LIUITEM1", "LIUPDF01", "LIUPKG01", "SHINNIT1", "SHINNPRE", "STUBITEM", "STUBPDF1")
# The md5s the fixtures list (paper-fetch's test_contract proves they are its files' bytes).
MD5 = {"liu": "bb2157e6a8e843bba55f7ad472f794b4", "shinn_pre": "5355ac1f3d70289b8265988d63d1d8b8",
       "shinn_supp": "a20b9103c2c26f5fa03eb71d5ba0e56c", "stub": "8b125ef0973bf22a0ebe0224552a2557"}


class TitlesFromLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        tmp = tempfile.TemporaryDirectory(prefix="p2z-titles-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.fetch = self.tmp / "fetch"
        shutil.copytree(FIXTURES, self.fetch / "results")
        pdf = {"itemType": "attachment", "linkMode": "imported_url", "contentType": "application/pdf"}
        z.add_item(LIU, itemType="journalArticle", title="Progressive Residual Learning", citationKey="liu2022jbhi")
        z.add_item(LIU_PDF, parentItem=LIU, title="Full Text PDF", md5=MD5["liu"], filename="Liu - 2022.pdf", **pdf)
        pkg = "liu2022jbhi.Full Text PDF.zip"   # a structured package: a zip under its PDF's title, <cite>.<title>.zip
        z.add_item(LIU_PKG, itemType="attachment", parentItem=LIU, title="Full Text PDF", linkMode="imported_file",
                   contentType="application/zip", filename=pkg)
        z.files[LIU_PKG] = z.store_file(LIU_PKG, pkg, b"PK zip")
        z.add_item(SHINN, itemType="conferencePaper", title="Reflexion", citationKey="shinn2023reflexion")
        z.add_item(SHINN_PRE, parentItem=SHINN, title="Accepted-arXiv-v4", md5=MD5["shinn_pre"], **pdf)
        z.add_item(STUB, itemType="journalArticle", title="Some HTML paper")
        z.add_item(STUB_PDF, parentItem=STUB, title="Full Text PDF", md5=MD5["stub"], **pdf)

    def test_labels_become_titles_through_update_item(self):
        batch = self.tmp / "titles.jsonl"
        r = smoke("titles_from_labels", self.fetch, "-o", batch, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines, [
            {"slug": "109999html", "file": "109999html.pdf", "code": "skipped", "reason": "unlabelled"},
            {"slug": "liu2022jbhi", "file": "liu2022jbhi.pdf", "code": "retitle", "key": LIU_PDF, "from": "Full Text PDF",
             "to": "Published-IEEE"},
            {"slug": "shinn2023reflexion", "file": "shinn2023reflexion.preprint.pdf", "code": "skipped", "reason": "titled",
             "key": SHINN_PRE, "title": "Accepted-arXiv-v4"},
            {"slug": "shinn2023reflexion", "file": "shinn2023reflexion.supplement.pdf", "code": "not_in_library",
             "md5": MD5["shinn_supp"]},
            {"summary": {"total": 4, "ok": 2, "skipped": 2, "failed": 0, "batch": str(batch), "lines": 1}}])
        self.assertEqual([json.loads(ln) for ln in batch.read_text(encoding="utf-8").splitlines()],
                         [{"key": LIU_PDF, "set": {"title": "Published-IEEE"}, "from": "Full Text PDF",
                           "why": "the volume and issue", "by": "judge", "citationKey": "liu2022jbhi"}])
        self.assertEqual(self.zot.writes(), [], "listing writes nothing")

        r = call(update_item, "--batch", batch, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["changes"]),
                         (LIU_PDF, {"title": {"from": "Full Text PDF", "to": "Published-IEEE"}}))
        self.assertEqual(r.lines[0]["packages"], [{"key": LIU_PKG, "from": "liu2022jbhi.Full Text PDF.zip",
                                                   "to": "liu2022jbhi.Published-IEEE.zip"}])
        self.assertEqual(self.zot.data(LIU_PDF)["title"], "Published-IEEE")
        self.assertEqual((self.zot.data(LIU_PKG)["title"], self.zot.data(LIU_PKG)["filename"]),
                         ("Published-IEEE", "liu2022jbhi.Published-IEEE.zip"), "the package goes along with its PDF")
        self.assertEqual(self.zot.data(STUB_PDF)["title"], "Full Text PDF", "a placeholder label is never written")

        r = call(titles_from_labels, self.fetch, "-o", batch, "--base-url", self.zot.base_url)
        self.assertEqual((r.lines[1]["code"], r.lines[1]["reason"], r.lines[-1]["summary"]["lines"]), ("skipped", "titled", 0))
        self.assertEqual(batch.read_text(encoding="utf-8"), "")

    def test_a_bad_result_or_none(self):
        (self.fetch / "results" / "broken.json").write_text("{", encoding="utf-8")
        r = call(titles_from_labels, self.fetch, "-o", self.tmp / "t.jsonl", "--base-url", self.zot.base_url)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(ln.get("slug"), ln.get("code")) for ln in r.lines[:2]],
                         [("109999html", "skipped"), ("broken", "result_invalid")])
        self.assertEqual(r.lines[-1]["summary"]["failed"], 1)
        r = call(titles_from_labels, self.tmp / "nothing", "-o", self.tmp / "t.jsonl", "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.lines[0]["code"], len(r.lines)), (1, "no_results", 1), r)
        self.assertEqual(call(titles_from_labels, self.fetch, "--base-url", self.zot.base_url).code, 2, "-o is required")


if __name__ == "__main__":
    unittest.main()
