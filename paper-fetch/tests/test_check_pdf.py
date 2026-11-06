# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pf.py check (scripts/check_pdf.py), the read-only viewer of verify's verdict (the rule itself: test_verify.py)."""
import os
import tempfile
import unittest
from unittest import mock

from helpers import call, fake_pdf, load, poppler_stubs, result_file, smoke

from pflib import run

check_pdf = load("check_pdf")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"


class CheckPdf(unittest.TestCase):
    def setUp(self):
        self.work = run.Work(tempfile.mkdtemp(prefix="pf-checkpdf-"))
        self.bin = poppler_stubs(self.work.scratch / "bin")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}"}))
        self.rec = result_file(self.work.root, "liu", csl={"title": TITLE, "author": [{"family": "Liu"}]})

    def test_the_verdict_on_the_results_file_and_nothing_written(self):
        r = call(check_pdf, self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.last["summary"]["failed"]), (1, "no_file", 1))
        fake_pdf(self.work.results / "liu.preprint.pdf", [f"{TITLE}\nWei Liu"])
        before = self.rec.read_text()
        r = call(check_pdf, self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["kind"], r.err), (0, "ok", "preprint", ""), r)
        self.assertEqual(r.lines[0]["evidence"]["title_page"], 1)
        self.assertNotIn("hint", r.lines[0])
        other = fake_pdf(self.work.scratch / "other.pdf", ["Another Paper Entirely\nAda Roe"])
        for argv in ((other, self.rec), (self.rec, other)):   # the .json is the result, wherever it stands
            r = call(check_pdf, *argv)
            self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["file"]), (1, "title_not_found", str(other)))
            self.assertIn("pf.py answer", r.lines[0]["hint"])
        r = call(check_pdf, other, self.work.scratch / "gone.pdf", self.rec)
        self.assertEqual([line["code"] for line in r.lines], ["title_not_found", "file_not_found"])
        self.assertEqual(self.rec.read_text(), before)
        self.assertEqual(call(check_pdf, self.rec, self.rec, other).code, 2, "files go with one result")
        self.assertEqual(call(check_pdf).code, 2, "nothing named")
        r = call(check_pdf, "-", stdin=f'{{"slug": "liu", "code": "ok", "path": "{self.rec}"}}\n')
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), "- reads the results' paths from JSON lines")
        with mock.patch.dict(os.environ, {"PATH": str(self.work.scratch / "empty")}):
            r = call(check_pdf, self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.last["code"]), (2, "not_run", "no_pdftotext"))

    def test_smoke(self):
        r = smoke("check", "-h")
        self.assertEqual(r.code, 0, r)
        self.assertIn("ok_by_words", r.out, "-h carries verify's rule")


if __name__ == "__main__":
    unittest.main()
