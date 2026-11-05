# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fields_from_results.py against the fake Zotero: paper-fetch's own result fixtures drafted, the
empty fields of their library items listed and handed to update_item --batch."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
from fake_zotero import SCHEMA, FakeZotero

FIXTURES = Path(__file__).resolve().parents[2] / "paper-fetch" / "tests" / "fixtures" / "results"
fields_from_results, update_item = load("fields_from_results"), load("update_item")
LIU, SHINN, DUP1 = "LIUITEM1", "SHINNIT1", "DUPKEY01"
# The fake's item types, with the CSL tables of Zotero's schema that drafting reads.
CSL_SCHEMA = {**SCHEMA, "csl": {
    "types": {"article-journal": ["journalArticle"], "paper-conference": ["conferencePaper"], "article": ["preprint"]},
    "fields": {"text": {"title": ["title"], "container-title": ["publicationTitle"], "volume": ["volume"],
                        "issue": ["issue"], "page": ["pages"], "DOI": ["DOI"], "URL": ["url"], "ISSN": ["ISSN"],
                        "abstract": ["abstractNote"], "publisher": ["publisher"], "source": ["libraryCatalog"],
                        "PMID": ["PMID"]},
               "date": {"issued": "date", "accessed": "accessDate"}},
    "names": {"author": "author", "editor": "editor"}}}


class FieldsFromResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.schema = CSL_SCHEMA
        tmp = tempfile.TemporaryDirectory(prefix="p2z-fields-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        shutil.copytree(FIXTURES, self.tmp / "results")
        self.results = self.tmp / "results"
        self.creators = [{"creatorType": "author", "lastName": "Liu", "firstName": "H."}]
        z.add_item(LIU, itemType="journalArticle", title="Progressive residual learning", creators=self.creators,
                   volume="99", extra="Original: kept", citationKey="liu2022jbhi")
        z.add_item(SHINN, itemType="journalArticle", title="Reflexion", citationKey="shinn2023reflexion")

    def test_empty_fields_filled_through_update(self):
        liu, shinn = self.results / "liu2022jbhi.json", self.results / "shinn2023reflexion.json"
        r = smoke("fill", liu, shinn, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.err), (0, ""), r)
        # Expected from the fixtures' CSL by Zotero's tables (container-title -> publicationTitle, page -> pages, issued
        # -> date) and draft's url rule (https://doi.org/<DOI>); issue and ISSN have no field in the fake's
        # journalArticle. Liu's title, volume, creators and extra are the library's; Shinn's draft is a conferencePaper,
        # whose proceedingsTitle is a journalArticle's publicationTitle through their base field.
        liu_set = {"abstractNote": "Ultrasound.", "publicationTitle": "IEEE Journal of Biomedical and Health Informatics",
                   "pages": "4593-4604", "date": "2022-09", "DOI": "10.1109/JBHI.2022.3142076",
                   "url": "https://doi.org/10.1109/JBHI.2022.3142076"}
        shinn_set = {"abstractNote": "Reflexion.", "publicationTitle": "Advances in Neural Information Processing Systems 36",
                     "pages": "8634-8652", "date": "2023", "DOI": "10.52202/075280-0377",
                     "url": "https://doi.org/10.52202/075280-0377"}
        self.assertEqual([{k: v for k, v in ln.items() if k != "warnings"} for ln in r.lines],
                         [{"key": LIU, "set": liu_set, "from": str(liu)}, {"key": SHINN, "set": shinn_set, "from": str(shinn)}],
                         "stdout is the change list; draft's warnings ride along as a note")
        self.assertEqual(self.zot.writes(), [], "listing writes nothing")

        r = call(update_item, "-", "--base-url", self.zot.base_url, config=self.config, stdin=r.out)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(ln["key"], ln["code"]) for ln in r.lines], [(LIU, "ok"), (SHINN, "ok")])
        liu_now = self.zot.data(LIU)
        self.assertEqual({f: liu_now.get(f) for f in liu_set}, liu_set)
        self.assertEqual((liu_now["title"], liu_now["volume"], liu_now["extra"], liu_now["creators"]),
                         ("Progressive residual learning", "99", "Original: kept", self.creators), "never overwritten")
        self.assertEqual(self.zot.data(SHINN)["publicationTitle"], shinn_set["publicationTitle"])
        self.assertNotIn("extra", self.zot.data(SHINN), "the draft's arXiv line in extra is not listed")

        batch = self.tmp / "fields.jsonl"
        r = call(fields_from_results, "-", "-o", batch, "--base-url", self.zot.base_url, stdin=f"{liu}\n{shinn}\n")
        self.assertEqual((r.code, r.out, r.err, batch.read_text(encoding="utf-8")), (0, "", "", ""),
                         "nothing left to fill: no line")

    def test_results_that_name_no_single_item(self):
        self.zot.data(SHINN)["citationKey"] = "other"
        self.zot.add_item(DUP1, itemType="journalArticle", title="One", citationKey="liu2022jbhi")
        r = call(fields_from_results, *sorted(self.results.glob("*.json")), "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.out), (1, ""), r)
        problems = r.err_lines[:-1]
        self.assertEqual([(ln.get("slug"), ln["code"]) for ln in problems],
                         [("109999html", "result_invalid"), ("liu2022jbhi", "ambiguous"),
                          ("shinn2023reflexion", "not_found")])
        self.assertEqual(sorted(problems[1]["keys"]), sorted([LIU, DUP1]))
        self.assertEqual(r.last["summary"], {"total": 3, "failed": 3})


if __name__ == "__main__":
    unittest.main()
