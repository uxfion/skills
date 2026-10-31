# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/answer.py and what prepare leaves open (p2z.py's decisions): a same_paper handoff answered by a
judge and by the user, several items with one DOI, accepted checks and warnings — against the fake Zotero."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, load
from fake_zotero import FakeZotero

from p2zlib import run

find, answer, p2z = load("find_in_library"), load("answer"), load("p2z")
C, E, X, Y = "CCCCCCC1", "EEEEEEE1", "XXXXXXX1", "YYYYYYY1"
TITLE = "Deep Residual Learning for Image Recognition"


class Answer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        self.zot.add_item(C, itemType="conferencePaper", title=TITLE, date="2016")
        self.zot.add_item(E, itemType="journalArticle", title=f"{TITLE}: Extended", date="2017")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-answer-"))
        self.work.records.mkdir()

    def prepared(self, slug, data):
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        r = call(find, path, "--base-url", self.zot.base_url)
        return path, r.lines[0]

    def answer(self, handoff, *argv):
        return call(answer, handoff, *argv)

    def test_a_judge_answers_and_the_record_settles(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        handoff = line["handoff"]
        self.assertEqual(p2z.decisions(run.read(path)), [{"same_paper": handoff, "waiting_on": "judge"}])
        r = self.answer(handoff, "distinct", "--key", E, "--reason", "a journal extension", "--by", "judge")
        self.assertEqual((r.code, r.lines[0]["open"]), (0, [C]))
        r = self.answer(handoff, "same", "--key", C, "--reason", "same title, year and venue", "--by", "judge")
        self.assertEqual((r.code, r.lines[0]["open"], run.read(path)["same_as"]), (0, [], C))
        self.assertEqual([(a["key"], a["answer"], a["by"]) for a in json.loads(Path(handoff).read_text())["answered"]],
                         [(E, "distinct", "judge"), (C, "same", "judge")], "every answer kept in the handoff")
        r = call(find, path, "--base-url", self.zot.base_url)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["key"], r.lines[0]["matched_by"]), ("found", C, "same_as"))
        self.assertEqual(p2z.decisions(run.read(path)), [])
        self.assertEqual(self.answer(handoff, "distinct").lines[0]["code"], "not_open")

    def test_distinct_without_a_key_settles_every_open_candidate(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        self.assertEqual(self.answer(line["handoff"], "distinct", "--by", "judge").lines[0]["keys"], [C, E])
        r = call(find, path, "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "not_found"))

    def test_pair_and_unknown_wait_for_the_user(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        handoff = line["handoff"]
        self.answer(handoff, "pair", "--key", C, "--by", "judge")
        self.assertEqual(p2z.decisions(run.read(path))[0]["waiting_on"], "judge", "E is still the judge's")
        self.answer(handoff, "unknown", "--key", E, "--by", "judge")
        self.assertEqual(p2z.decisions(run.read(path)), [{"same_paper": handoff, "waiting_on": "user"}])
        self.answer(handoff, "distinct", "--key", C, "--key", E, "--by", "user")
        self.assertEqual(p2z.decisions(run.read(path)), [])
        self.zot.add_item(X, itemType="journalArticle", title=f"{TITLE} Revisited", date="2026")
        path, line = self.prepared("b", json.loads(path.read_text()))
        self.assertEqual(line["near_matches"], [{"key": X, "title": f"{TITLE} Revisited", "similarity": 0.9}])  # 2·39/(39+48) normalised characters
        self.assertNotEqual(line["handoff"], handoff, "a new candidate: a new handoff, with only what is open")

    def test_refusals(self):
        _, line = self.prepared("b", {"item": {"title": TITLE}})
        cases = [(("maybe",), "bad_answer"), (("same",), "one_key"), (("same", "--key", f"{C},{E}"), "one_key"),
                 (("pair",), "no_key"), (("distinct", "--key", "NOPE0001"), "no_such_key")]
        for argv, code in cases:
            r = self.answer(line["handoff"], *argv)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code), argv)
        self.assertEqual(self.answer(self.work.root / "nope.json", "same").lines[0]["code"], "no_such_handoff")

    def test_several_items_with_the_doi_and_accepted_flags(self):
        doi = "10.1000/twice.1"
        for key in (X, Y):
            self.zot.add_item(key, itemType="journalArticle", title="Twice", DOI=doi)
        path, line = self.prepared("t", {"item": {"title": "Twice", "DOI": doi}, "warnings": ["a type guessed"]})
        rec = run.read(path)
        self.assertIsNone(run.item_key(rec), "files never go to one of two duplicates by chance")
        rec["checks"] = {"code": "needs_attention", "mapped": [{"from": "publicationTitle", "to": "proceedingsTitle"}],
                         "to_extra": [], "dropped_or_rewritten": [], "missing_minimum": ["date"]}
        self.assertEqual(p2z.decisions(rec), [{"duplicates": [X, Y]},
                                              {"checks": ["mapped:publicationTitle", "missing_minimum:date"]},
                                              {"warnings": ["a type guessed"]}])
        rec["accepted"] = ["mapped:publicationTitle", "missing_minimum:date", "a type guessed"]
        rec["same_as"] = Y
        self.assertEqual(p2z.decisions(rec), [])


if __name__ == "__main__":
    unittest.main()
