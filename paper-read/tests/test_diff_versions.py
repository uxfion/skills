# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pr.py diff (scripts/diff_versions.py): two versions compared section by section, and two pieces of text.
The expected lines are written by hand from the two texts."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "diff_versions.py"

# A preprint and its typeset version: other numbering and case in the headings, a formula spaced otherwise, a line
# broken elsewhere, one number changed, a section dropped and one added, a second "Training" under another heading.
OLD = """arXiv:2305.15086v3 [cs.CV] 2 Mar 2024

# A Study of Things

## I. INTRODUCTION

We study things with $ \\lambda = 0.5 $ and report
an accuracy of 91.2 on 1,067 pairs.

## II. METHOD

### A. Training

We train for 200 epochs.

## III. RESULTS

### A. Training

Loss falls <!-- open missing_text@p3: gone --> steadily.

## ACKNOWLEDGMENT

We thank nobody.
"""
NEW = """# A study of things

## 1 Introduction

We study things with $\\lambda=0.5$ and report an accuracy
of 91.2 on 1,067 pairs.

## 2 Method

### 2.1 Training

We train for 400 epochs.

## 3 Results

### 3.1 Training

Loss falls steadily.

## Data availability

On request.
"""


def run(*argv):
    done = subprocess.run(["uv", "run", "--quiet", "--script", str(SCRIPT), *map(str, argv)], capture_output=True, text=True)
    return done.returncode, [json.loads(line) for line in done.stdout.splitlines()], done.stderr


class DiffVersions(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="pr-diff-"))
        for name, text in (("old", OLD), ("new", NEW)):
            folder = self.dir / f"paper.{name}"     # a package folder holds <name>/<name>.md
            folder.mkdir()
            (folder / f"paper.{name}.md").write_text(text, encoding="utf-8")

    def test_two_versions_section_by_section(self):
        code, lines, err = run(self.dir / "paper.old", self.dir / "paper.new")
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(lines, [
            {"section": "(start)", "code": "only_old", "words": 8},                      # the margin stamp
            {"section": "I. INTRODUCTION", "new_section": "1 Introduction", "code": "same", "words": 14},
            {"section": "A. Training", "new_section": "2.1 Training", "code": "differs", "old_words": 5, "new_words": 5,
             "only_old": 1, "only_new": 1, "places": [{"old": "200", "new": "400"}]},
            {"section": "A. Training", "new_section": "3.1 Training", "code": "same", "words": 3},   # paired in order
            {"section": "ACKNOWLEDGMENT", "code": "only_old", "words": 3},
            {"section": "Data availability", "code": "only_new", "words": 2},
        ])

    def test_two_pieces_of_text_and_no_difference(self):
        a, b = self.dir / "a.txt", self.dir / "b.txt"
        a.write_text("Fig. 3. Results on the test set (n = 120).", encoding="utf-8")
        b.write_text("Figure 3: results on the\ntest set ( n=120 ).", encoding="utf-8")
        code, lines, _ = run(a, b)
        self.assertEqual((code, lines), (1, [{"section": "(start)", "code": "differs", "old_words": 9, "new_words": 9,
                                              "only_old": 1, "only_new": 1, "places": [{"old": "Fig", "new": "Figure"}]}]))
        b.write_text("FIG. 3: Results on the test set (n=120)", encoding="utf-8")
        self.assertEqual(run(a, b)[:2], (0, [{"section": "(start)", "code": "same", "words": 9}]))

    def test_every_place_and_what_cannot_be_read(self):
        a, b = self.dir / "a.txt", self.dir / "b.txt"
        a.write_text(" ".join(f"w{i} x" for i in range(12)), encoding="utf-8")
        b.write_text(" ".join(f"v{i} x" for i in range(12)), encoding="utf-8")
        self.assertEqual(len(run(a, b)[1][0]["places"]), 8, "the first eight places")
        self.assertEqual(len(run("-a", a, b)[1][0]["places"]), 12)
        (self.dir / "empty").mkdir()
        for path, why in ((self.dir / "nothing.txt", "file_not_found"), (self.dir / "empty", "no_markdown")):
            code, lines, err = run(a, path)
            self.assertEqual((code, lines, json.loads(err.splitlines()[-1])["code"]), (2, [], why))


if __name__ == "__main__":
    unittest.main()
