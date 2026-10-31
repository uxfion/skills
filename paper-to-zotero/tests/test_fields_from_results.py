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

    def test_empty_fields_filled_through_update_item(self):
        batch, liu, shinn = self.tmp / "fields.jsonl", self.results / "liu2022jbhi.json", self.results / "shinn2023reflexion.json"
        r = smoke("fields_from_results", liu, shinn, "-o", batch, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        # Expected from the fixtures' CSL by Zotero's tables (container-title -> publicationTitle, page -> pages, issued
        # -> date) and draft_item's url rule (https://doi.org/<DOI>); issue and ISSN have no field in the fake's
        # journalArticle. Liu's title, volume, creators and extra are the library's; Shinn's draft is a conferencePaper,
        # whose proceedingsTitle is a journalArticle's publicationTitle through their base field.
        liu_set = {"abstractNote": "Ultrasound.", "publicationTitle": "IEEE Journal of Biomedical and Health Informatics",
                   "pages": "4593-4604", "date": "2022-09", "DOI": "10.1109/JBHI.2022.3142076",
                   "url": "https://doi.org/10.1109/JBHI.2022.3142076"}
        shinn_set = {"abstractNote": "Reflexion.", "publicationTitle": "Advances in Neural Information Processing Systems 36",
                     "pages": "8634-8652", "date": "2023", "DOI": "10.52202/075280-0377",
                     "url": "https://doi.org/10.52202/075280-0377"}
        self.assertEqual([(ln["slug"], ln["cite"], ln["code"], ln["key"], sorted(ln["fields"])) for ln in r.lines[:2]],
                         [("liu2022jbhi", "liu2022jbhi", "fill", LIU, sorted(liu_set)),
                          ("shinn2023reflexion", "shinn2023reflexion", "fill", SHINN, sorted(shinn_set))])
        self.assertEqual(r.lines[-1]["summary"], {"total": 2, "ok": 2, "skipped": 0, "failed": 0, "batch": str(batch), "lines": 2})
        self.assertEqual([json.loads(ln) for ln in batch.read_text(encoding="utf-8").splitlines()],
                         [{"cite": "liu2022jbhi", "set": liu_set, "from": str(liu)},
                          {"cite": "shinn2023reflexion", "set": shinn_set, "from": str(shinn)}])
        self.assertEqual(self.zot.writes(), [], "listing writes nothing")

        r = call(update_item, "--batch", batch, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(ln["key"], ln["code"]) for ln in r.lines[:2]], [(LIU, "ok"), (SHINN, "ok")])
        liu_now = self.zot.data(LIU)
        self.assertEqual({f: liu_now.get(f) for f in liu_set}, liu_set)
        self.assertEqual((liu_now["title"], liu_now["volume"], liu_now["extra"], liu_now["creators"]),
                         ("Progressive residual learning", "99", "Original: kept", self.creators), "never overwritten")
        self.assertEqual(self.zot.data(SHINN)["publicationTitle"], shinn_set["publicationTitle"])
        self.assertNotIn("extra", self.zot.data(SHINN), "the draft's arXiv line in extra is not listed")

        r = call(fields_from_results, liu, shinn, "-o", batch, "--base-url", self.zot.base_url)
        self.assertEqual([(ln["code"], ln["reason"]) for ln in r.lines[:2]], [("skipped", "nothing_to_fill")] * 2)
        self.assertEqual(batch.read_text(encoding="utf-8"), "")

    def test_results_that_name_no_single_item(self):
        self.zot.data(SHINN)["citationKey"] = "other"
        self.zot.add_item(DUP1, itemType="journalArticle", title="One", citationKey="liu2022jbhi")
        r = call(fields_from_results, *sorted(self.results.glob("*.json")), "-o", self.tmp / "f.jsonl",
                 "--base-url", self.zot.base_url)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(ln.get("slug"), ln["code"]) for ln in r.lines[:3]],
                         [("109999html", "result_invalid"), ("liu2022jbhi", "cite_ambiguous"),
                          ("shinn2023reflexion", "cite_not_found")])
        self.assertEqual(sorted(r.lines[1]["keys"]), sorted([LIU, DUP1]))
        self.assertEqual((r.lines[-1]["summary"]["failed"], r.lines[-1]["summary"]["lines"]), (3, 0))


if __name__ == "__main__":
    unittest.main()
