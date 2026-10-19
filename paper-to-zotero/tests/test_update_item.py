# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/update_item.py: how a read-back Extra is judged when Zotero moved some of its lines into fields."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_item.py"


def module():
    spec = importlib.util.spec_from_file_location("update_item", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MovedToFields(unittest.TestCase):
    def test_a_pmid_line_zotero_moved_into_its_field(self):
        mod = module()
        sent = "TLDR: a summary\nPMID: 38262200"
        after = {"extra": "TLDR: a summary", "PMID": "38262200", "title": "x"}
        self.assertEqual(mod.moved_to_fields(sent, after["extra"], after), {"PMID: 38262200": "PMID"})

    def test_a_line_that_is_simply_missing_is_not_explained(self):
        mod = module()
        self.assertEqual(mod.moved_to_fields("arXiv: 2101.00001", "", {"extra": "", "title": "x"}), {})
        self.assertEqual(mod.moved_to_fields("PMID: 1", "", {"extra": "", "PMID": "2"}), {}, "a different value")


if __name__ == "__main__":
    unittest.main()
