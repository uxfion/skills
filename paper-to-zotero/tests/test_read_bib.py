# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/read_bib.py: .bib entries -> the `identifier<TAB>citation key` lines paper-fetch's identify takes."""
import tempfile
import unittest
from pathlib import Path

from helpers import call, load, smoke

read_bib = load("read_bib")

BIB = """\
@comment{this is ignored}
@string{ieee = "IEEE"}
@article{liuJBHI2022,
  title = {Progressive {Residual} Learning},
  author = {Liu, Heng},
  doi = {https://doi.org/10.1109/JBHI.2022.3142076},
  year = 2022
}
@misc{ho2020ddpm,
  title = "Denoising Diffusion Probabilistic Models",
  eprint = {2006.11239},
  archivePrefix = {arXiv},
  primaryClass = {cs.LG}
}
@inproceedings{he2016resnet,
  Title = {Deep Residual Learning for Image Recognition},
  booktitle = {CVPR},
  URL = {https://arxiv.org/abs/1512.03385v1}
}
@book{knuth1984,
  title = {The {TeX}book: A {Nested {Brace}} Title},
  publisher = ieee # " Press",
  note = "quoted with {braces, and} a comma"
}
"""
LINES = ["10.1109/jbhi.2022.3142076\tliuJBHI2022", "arXiv:2006.11239\tho2020ddpm", "arXiv:1512.03385v1\the2016resnet",
         "title:The TeXbook: A Nested Brace Title\tknuth1984"]


class ReadBib(unittest.TestCase):
    def test_entries_become_identify_lines(self):
        bib = Path(tempfile.mkdtemp(prefix="p2z-bib-")) / "refs.bib"
        bib.write_text(BIB, encoding="utf-8")
        r = call(read_bib, bib)
        self.assertEqual((r.code, r.out.splitlines()), (0, LINES), r)
        self.assertIn("4 entries, 1 without a DOI or arXiv id", r.err)
        self.assertEqual(call(read_bib, stdin=BIB).out.splitlines(), LINES, "stdin when no file is named")

    def test_unreadable_or_empty(self):
        r = call(read_bib, "/no/such.bib", stdin="")
        self.assertEqual((r.code, r.out), (1, ""), r)
        self.assertEqual(call(read_bib, stdin="no entries here").code, 1)

    def test_smoke(self):
        bib = Path(tempfile.mkdtemp(prefix="p2z-bib-")) / "refs.bib"
        bib.write_text(BIB, encoding="utf-8")
        r = smoke("read_bib", bib)
        self.assertEqual((r.code, r.out.splitlines()), (0, LINES), r)


if __name__ == "__main__":
    unittest.main()
