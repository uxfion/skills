# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_pdf.py, the read-only viewer of verify's verdict (the rule itself: test_verify.py)."""
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
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_file"))
        fake_pdf(self.work.results / "liu.preprint.pdf", [f"{TITLE}\nWei Liu"])
        before = self.rec.read_text()
        r = call(check_pdf, self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["kind"]), (0, "ok", "preprint"), r)
        self.assertEqual(r.lines[0]["evidence"]["title_page"], 1)
        self.assertNotIn("hint", r.lines[0])
        other = fake_pdf(self.work.scratch / "other.pdf", ["Another Paper Entirely\nAda Roe"])
        r = call(check_pdf, self.rec, "--file", other)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["file"]), (1, "title_not_found", str(other)))
        self.assertIn("claim.py --accept", r.lines[0]["hint"])
        self.assertEqual(self.rec.read_text(), before)
        self.assertEqual(call(check_pdf, self.rec, self.rec, "--file", other).code, 2, "--file: one result")
        with mock.patch.dict(os.environ, {"PATH": str(self.work.scratch / "empty")}):
            r = call(check_pdf, self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_pdftotext"))

    def test_smoke(self):
        r = smoke("check_pdf", "--help")
        self.assertEqual(r.code, 0, r)
        self.assertIn("ok_by_words", r.out, "--help carries verify's rule")


if __name__ == "__main__":
    unittest.main()
