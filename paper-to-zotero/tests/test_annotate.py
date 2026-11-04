# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/annotate.py against the fake Zotero: rectangle annotations on a PDF, made once."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
from fake_zotero import FakeZotero

annotate = load("annotate")
PDF = "PDFKEY01"
BOX = {"comment": "paper-read · Fig. 9", "color": "#2ea8e5", "tag": "paper-read", "page": 11, "page_label": "11",
       "rect": [48.0, 407.0, 284.5, 595.0], "top": 197.0}
TABLE = {**BOX, "comment": "paper-read · Table III", "rect": [280.5, 719.5, 317.5, 728.5], "top": 63.5}


class Annotate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()
        cls.dir = Path(tempfile.mkdtemp(prefix="p2z-annotate-"))

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_item("PAPER001", itemType="journalArticle", title="T-CACE")
        z.add_item(PDF, itemType="attachment", parentItem="PAPER001", contentType="application/pdf", title="Published-IEEE")

    def run_(self, *entries, extra=(), pdf=PDF):
        batch = self.dir / "batch.jsonl"
        batch.write_text("\n".join(e if isinstance(e, str) else json.dumps(e, ensure_ascii=False) for e in entries),
                         encoding="utf-8")
        return call(annotate, pdf, "--batch", batch, *extra, "--base-url", self.zot.base_url, config=self.config)

    def stored(self):
        return [it["data"] for it in self.zot.items.values() if it["data"].get("itemType") == "annotation"]

    def test_created_as_zotero_stores_a_rectangle(self):
        r = self.run_(BOX)
        self.assertEqual(r.code, 0, r)
        [a] = self.stored()
        self.assertEqual(r.lines[0], {"comment": BOX["comment"], "code": "created", "key": a["key"]})
        self.assertEqual({k: a[k] for k in ("parentItem", "annotationType", "annotationColor", "annotationComment",
                                             "annotationPageLabel", "annotationSortIndex", "tags")},
                         {"parentItem": PDF, "annotationType": "image", "annotationColor": "#2ea8e5",
                          "annotationComment": "paper-read · Fig. 9", "annotationPageLabel": "11",
                          "annotationSortIndex": "00010|000000|00197", "tags": [{"tag": "paper-read"}]})
        self.assertEqual(json.loads(a["annotationPosition"]), {"pageIndex": 10, "rects": [[48.0, 407.0, 284.5, 595.0]]})

    def test_a_rerun_keeps_what_is_there(self):
        first = self.run_(BOX, TABLE).lines
        again = self.run_(TABLE, BOX)
        self.assertEqual(again.code, 0, again)
        self.assertEqual([(l["code"], l["key"]) for l in again.lines[:2]],
                         [("kept", first[1]["key"]), ("kept", first[0]["key"])])
        self.assertEqual(len(self.stored()), 2)

    def test_found_by_tag_and_first_line_the_oldest_of_two(self):
        z = self.zot
        mine = {"itemType": "annotation", "parentItem": PDF, "annotationType": "image"}
        z.add_item("NEWER001", **mine, annotationComment="paper-read · Fig. 9", tags=[{"tag": "paper-read"}],
                   dateAdded="2026-11-05T10:00:00Z")
        z.add_item("OLDER001", **mine, annotationComment="paper-read · Fig. 9\nthe user's words below",
                   tags=[{"tag": "paper-read"}, {"tag": "mine"}], dateAdded="2026-11-04T10:00:00Z")
        z.add_item("USERS001", **mine, annotationComment="paper-read · Table III", dateAdded="2026-11-01T10:00:00Z")
        r = self.run_(BOX, TABLE)
        self.assertEqual([(l["code"], l["key"] if l["code"] == "kept" else None) for l in r.lines[:2]],
                         [("kept", "OLDER001"), ("created", None)])   # the user's own, untagged, is not one of ours
        self.assertEqual(len(self.stored()), 4)
        self.assertEqual([w for w in z.writes() if w[0] != "POST"], [])   # nothing changed or deleted

    def test_a_tag_that_does_not_stick_is_a_readback_mismatch(self):
        self.zot.on_write = lambda it: it["data"].update(tags=[])
        r = self.run_(BOX)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "readback_mismatch"), r)
        self.assertIn("hint", r.lines[0])

    def test_dry_run_and_a_bad_batch_write_nothing(self):
        r = self.run_(BOX, extra=("--dry-run",))
        self.assertEqual((r.code, r.lines[0]), (0, {"comment": BOX["comment"], "code": "created", "key": None,
                                                    "dry_run": True}))
        r = self.run_(BOX, {**TABLE, "rect": [1, 2, 0, 4]}, "{not json")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "invalid_batch"), r)
        self.assertEqual(len(r.lines[0]["detail"]), 2)
        self.assertEqual(self.zot.writes(), [])

    def test_only_on_a_pdf(self):
        self.zot.add_item("NOTE0001", itemType="note", parentItem="PAPER001", note="<p>x</p>")
        r = self.run_(BOX, pdf="NOTE0001")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "not_a_pdf"), r)

    def test_runs_as_its_own_process(self):
        batch = self.dir / "smoke.jsonl"
        batch.write_text(json.dumps(BOX), encoding="utf-8")
        r = smoke("annotate", PDF, "--batch", batch, "--dry-run", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "created"), r)


if __name__ == "__main__":
    unittest.main()
