# /// script
# requires-python = ">=3.11"
# dependencies = ["reportlab"]
# ///
"""Tests for scripts/check_quotes.py: every quotation in a note is found in the paper, or marked as checked by eye."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_quotes.py"

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

# line, result, checked: by hand, from the page and the package above
EXPECTED = [
    (3, "ok", False),             # across the hyphenated line break, cut with …
    (7, "ok", False),             # double quotes inside, brackets inside the source
    (8, "not_found", False),      # 2841 is not 28.41
    (9, "package_only", False),   # only in the package, inside an HTML table
    (10, "not_found", False),     # only in an <!-- --> comment of the package
    (11, "too_short", False),
    (12, "too_short", False),     # the piece after … is too short
    (13, "not_found", True),      # compared with the page by eye
    (14, "unparsed", False),      # words after the closing quote
    (15, "ok", False),            # curly quotes
    (16, "ok", False),            # between a "<" and a ">" of the text
]


def run(*args):
    done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, timeout=120)
    return done.returncode, (json.loads(done.stdout) if done.stdout.strip() else None), done.stderr


class CheckQuotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix="paper-read-"))
        cls.pdf = cls.dir / "paper.pdf"
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
        code, out, err = run(self.note, "--pdf", self.pdf, "--package", self.package)
        self.assertEqual((code, out["code"]), (1, "open"), err)
        self.assertEqual([(q["line"], q["result"], q["checked"]) for q in out["quotes"]], EXPECTED)
        self.assertEqual(out["counts"], {"ok": 4, "not_found": 3, "package_only": 1, "too_short": 2, "unparsed": 1})

    def test_found_or_checked_passes(self):
        lines = NOTE.split("\n")
        passing = self.dir / "passing.note.md"
        passing.write_text("\n".join(lines[i - 1] for i in (1, 3, 4, 5, 7, 13)), encoding="utf-8")
        code, out, err = run(passing, "--pdf", self.pdf)
        self.assertEqual((code, out["code"], out["counts"]), (0, "pass", {"ok": 2, "not_found": 1}), err)

    def test_an_unreadable_pdf(self):
        code, out, _ = run(self.note, "--pdf", self.dir / "gone.pdf")
        self.assertEqual((code, out["code"]), (2, "unreadable"))
        empty = self.dir / "empty"
        empty.mkdir()
        code, out, _ = run(self.note, "--pdf", self.pdf, "--package", empty)  # a package folder without its .md
        self.assertEqual((code, out["code"]), (2, "unreadable"))


if __name__ == "__main__":
    unittest.main()
