# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""p2z consumes the result files paper-fetch writes: draft_item, attach_file, report and p2z.py's decisions run on
paper-fetch's own fixtures (its tests/fixtures/results/, which its test_contract.py proves are what it writes).
Skipped when paper-fetch is not installed beside this skill."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, config_file, load
from fake_zotero import FakeZotero
from test_draft_item import SCHEMA

from p2zlib import run

FIXTURES = Path(__file__).resolve().parents[2] / "paper-fetch" / "tests" / "fixtures" / "results"
draft_item, attach_file, report, p2z = load("draft_item"), load("attach_file"), load("report"), load("p2z")


@unittest.skipUnless(FIXTURES.is_dir(), "paper-fetch is not beside this skill")
class Contract(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="p2z-contract-"))
        self.results = self.root / "fetch" / "results"
        shutil.copytree(FIXTURES, self.results)
        (self.root / "scratch").mkdir()
        (self.root / "scratch" / "schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")

    def rec(self, slug):
        return run.read(self.root / "records" / f"{slug}.json")

    def test_drafted_saved_attached_reported(self):
        r = call(draft_item, *sorted(self.results.glob("*.json")), "--automatic-tags", "--base-url", f"http://127.0.0.1:{closed_port()}",
                 config=config_file(key=None))
        codes = {line["slug"]: line["code"] for line in r.lines[:-1]}
        self.assertEqual(codes, {"109999html": "stub", "liu2022jbhi": "ok", "shinn2023reflexion": "ok"},
                         "a stub has no metadata to draft from: its record holds the result alone, for recognize.py")
        liu, shinn = self.rec("liu2022jbhi"), self.rec("shinn2023reflexion")
        self.assertEqual((liu["item"]["itemType"], liu["item"]["DOI"], liu["citationKey"]),
                         ("journalArticle", "10.1109/JBHI.2022.3142076", "liu2022jbhi"), "a given slug is the citation key")
        self.assertEqual((shinn["item"]["itemType"], shinn["item"]["extra"], [t["tag"] for t in shinn["tags"]]),
                         ("conferencePaper", "arXiv: 2303.11366", ["Computer Science - Artificial Intelligence"]),
                         "the redrafted version keeps what the preprint gave")
        self.assertEqual(p2z.decisions(shinn), [], "a redrafted result leaves no version to choose")

        zot = FakeZotero()
        self.addCleanup(zot.close)
        for key, rec in (("LIUITEM1", liu), ("SHINNIT1", shinn)):
            zot.add_item(key, itemType=rec["item"]["itemType"], title=rec["item"]["title"])
            rec["saved"] = {"key": key}
            rec.save()
        records = [liu.path, shinn.path]
        r = call(attach_file, *records, "--base-url", zot.base_url, config=config_file())
        self.assertEqual(r.code, 0, r)
        titles = {key: sorted(it["data"]["title"] for it in zot.items.values() if it["data"].get("parentItem") == key)
                  for key in ("LIUITEM1", "SHINNIT1")}
        self.assertEqual(titles, {"LIUITEM1": ["Published-IEEE"], "SHINNIT1": ["Accepted-arXiv-v4", "Supplement-NeurIPS"]},
                         "every file the result passed, under its label: the paper's and its supplement")
        files, outcome = report.result_files(self.rec("shinn2023reflexion"))
        self.assertEqual((outcome["status"], [f["check"] for f in files]), ("got", ["ok", "accepted"]))


if __name__ == "__main__":
    unittest.main()
