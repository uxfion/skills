# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""p2zlib/titles.py is paper-fetch's pflib/titles.py byte for byte: the attachment titles one writes, the other reads.
Skipped when paper-fetch is not installed beside this skill."""
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
OURS, OWNER = HERE.parent / "scripts" / "p2zlib" / "titles.py", HERE.parents[1] / "paper-fetch" / "scripts" / "pflib" / "titles.py"


class Titles(unittest.TestCase):
    @unittest.skipUnless(OWNER.is_file(), "paper-fetch is not beside this skill")
    def test_the_copy_is_paper_fetchs(self):
        self.assertEqual(OURS.read_bytes(), OWNER.read_bytes(),
                         f"copy {OWNER} over {OURS}: paper-fetch owns the attachment title scheme")


if __name__ == "__main__":
    unittest.main()
