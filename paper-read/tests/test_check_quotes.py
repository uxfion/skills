# /// script
# requires-python = ">=3.11"
# dependencies = ["reportlab"]
# ///
"""Tests for pr.py quotes (scripts/check_quotes.py): every quotation in a note is found in the paper, or marked as
checked by eye. The PDF and the package sit beside the note, where pr.py take puts them."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pr.py"

PAGE = [  # one page of the paper; the first sentence breaks with a hyphen across two lines
    "The time-conditioned autoregressive model synthesises con-",
    "trast-enhanced phases from non-contrast MRI.",
    'We call this the "phase token" encoding of each image.',
    "It reaches a PSNR of 28.41 dB on the internal test set.",
    "With p < 0.05 in every comparison of the study,",   # a "<" and a ">" in the text are no HTML tags
    "the time-aware attention mask improves every phase.",
    "The margin exceeds 2 dB when x > 2.",
]

PACKAGE = """# T-CACE

The time-conditioned autoregressive model synthesises contrast-enhanced phases from non-contrast MRI.

<table><tr><td>Table 3 reports a mean Dice of 0.912 on the internal cohort.</td></tr></table>

<!-- settle: the model needs no tumour mask at test time -->
"""

NOTE = """# 论文笔记

> "The time-conditioned autoregressive model … synthesises contrast-enhanced phases from non-contrast MRI" (Sec. 3.1, p.2)
>
> 时间条件自回归模型……从平扫 MRI 生成增强各期。

> "We call this the "phase token" encoding of each image" (Eq. (3), p.2)
> "It reaches a PSNR of 2841 dB on the internal test set" (Table 2)
> "Table 3 reports a mean Dice of 0.912 on the internal cohort" (Table 3)
> "the model needs no tumour mask at test time" (Sec. 4)
> "the PSNR" (Table 2)
> "It reaches a PSNR of 28.41 dB … set" (Table 2)
> "the model needs no tumour mask at test time" (Sec. 4)（已核对 Sec. 4, p.5 · 2026-11-02）
> "a sentence about the tumour masks" and then more words
> “The time-conditioned autoregressive model synthesises contrast-enhanced phases” (p.1)
> "the time-aware attention mask improves every phase" (p.1)
"""

# Open quotations, by hand from the page and package above. PDF matches and the
# quotation marked 已核对 on line 13 are omitted from stdout.
EXPECTED = [
    (8, "not_found"),      # 2841 is not 28.41
    (9, "package_only"),   # only in the package, inside an HTML table
    (10, "not_found"),     # only in an <!-- --> comment of the package
    (11, "too_short"),
    (12, "too_short"),     # the piece after … is too short
    (14, "unparsed"),      # words after the closing quote
]


def run(*args, env=None):
    done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), "quotes", *map(str, args)],
                          capture_output=True, text=True, timeout=120, env={**os.environ, **(env or {})})
    return done.returncode, [json.loads(line) for line in done.stdout.splitlines()], done.stderr


class CheckQuotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="paper-read-"))
        cls.pdf = cls.dir / "paper.pdf"   # beside paper.note.md
        c = canvas.Canvas(str(cls.pdf))
        for i, line in enumerate(PAGE):
            c.drawString(72, 720 - 16 * i, line)
        c.showPage()
        c.save()
        cls.package = cls.dir / "paper"
        cls.package.mkdir()
        (cls.package / "paper.md").write_text(PACKAGE, encoding="utf-8")
        cls.note = cls.dir / "paper.note.md"
        cls.note.write_text(NOTE, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def test_each_kind_of_quotation(self):
        code, out, err = run(self.note)
        self.assertEqual(code, 1, err)
        self.assertEqual([(q["line"], q["result"]) for q in out], EXPECTED)
        self.assertTrue(all(set(q) == {"line", "result", "text"} for q in out))
        self.assertEqual(json.loads(err), {"summary": {"total": 11, "ok": 4, "checked": 1, "open": 6}})

    def test_found_or_checked_passes(self):
        lines = NOTE.split("\n")
        passing = self.dir / "passing.note.md"   # no package beside it: the PDF alone
        passing.write_text("\n".join(lines[i - 1] for i in (1, 3, 4, 5, 7, 13)), encoding="utf-8")
        shutil.copyfile(self.pdf, self.dir / "passing.pdf")
        code, out, err = run(passing)
        self.assertEqual((code, out, err), (0, [], ""))
        passing.write_text("# No quotations\n", encoding="utf-8")
        self.assertEqual(run(passing), (0, [], ""))

    def test_what_cannot_be_read(self):
        lone = self.dir / "lone.note.md"   # no PDF beside it
        lone.write_text(NOTE, encoding="utf-8")
        code, (out,), _ = run(lone)
        self.assertEqual((code, out["file"], out["code"], out["path"]), (1, str(lone), "file_not_found", str(self.dir / "lone.pdf")))
        self.assertIn("pr.py take", out["hint"])
        shutil.copyfile(self.pdf, self.dir / "lone.pdf")
        (self.dir / "lone").mkdir()   # a package folder without its .md
        code, (out,), _ = run(lone)
        self.assertEqual((code, out["code"], out["path"]), (1, "file_unreadable", str(self.dir / "lone")))
        code, (out,), _ = run(self.dir / "gone.note.md")
        self.assertEqual((code, out["code"]), (1, "file_not_found"))
        self.assertEqual(run(self.note, "--pdf", self.pdf)[0], 2)   # a usage error
        code, out, err = run(self.note, env={"PATH": str(Path(shutil.which("uv")).parent)})   # no pdftotext on PATH
        self.assertEqual((code, out, json.loads(err.splitlines()[-1])["code"]), (2, [], "no_pdftotext"))


if __name__ == "__main__":
    unittest.main()
