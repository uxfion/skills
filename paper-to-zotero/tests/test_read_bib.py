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
        self.assertEqual((r.code, r.out.splitlines(), r.err), (0, LINES, ""), r)
        self.assertEqual(call(read_bib, "-", stdin=BIB).out.splitlines(), LINES, "- reads the .bib from stdin")
        self.assertEqual(call(read_bib, stdin=BIB).last["code"], "usage", "stdin only with -")

    def test_unreadable_or_empty(self):
        r = call(read_bib, "/no/such.bib", "-", stdin="no entries here")
        self.assertEqual((r.code, r.out), (1, ""), r)
        self.assertEqual([(ln["file"], ln["code"]) for ln in r.err_lines[:-1]],
                         [("/no/such.bib", "file_not_found"), ("-", "no_entry")])
        self.assertEqual(r.last, {"summary": {"total": 2, "failed": 2}})

    def test_through_the_entry(self):
        bib = Path(tempfile.mkdtemp(prefix="p2z-bib-")) / "refs.bib"
        bib.write_text(BIB, encoding="utf-8")
        r = smoke("ids", bib)
        self.assertEqual((r.code, r.out.splitlines(), r.err), (0, LINES, ""), r)


if __name__ == "__main__":
    unittest.main()
