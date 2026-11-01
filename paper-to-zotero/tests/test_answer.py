# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/answer.py and what prepare leaves open (p2z.py's decisions): a same_paper handoff answered by a
judge and by the user, the decision read from the handoff alone, several items with one DOI, a paper still to tag,
accepted checks and warnings — against the fake Zotero."""
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

    def tagged(self, slug, tags=("method/ResNet",)):
        self.work.tags.mkdir(exist_ok=True)
        (self.work.tags / f"{slug}.json").write_text(json.dumps(list(tags)), encoding="utf-8")

    def test_a_judge_answers_into_the_handoff_and_the_record_is_left_alone(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        handoff = line["handoff"]
        self.assertNotIn("taker", json.loads(Path(handoff).read_text()), "who takes it is SKILL.md's to say")
        self.assertEqual(p2z.decisions(run.read(path)), [{"same_paper": handoff, "waiting_on": "judge"},
                                                         {"tags": str(self.work.root / "tags" / "b.json")}])
        before = path.read_bytes()
        r = self.answer(handoff, "distinct", "--key", E, "--reason", "a journal extension", "--by", "judge")
        self.assertEqual((r.code, r.lines[0]["open"]), (0, [C]))
        r = self.answer(handoff, "same", "--key", C, "--reason", "same title, year and venue", "--by", "judge")
        self.assertEqual((r.code, r.lines[0]["open"]), (0, []))
        self.assertEqual(path.read_bytes(), before, "answer writes the handoff, never the record")
        self.assertEqual([(a["key"], a["answer"], a["by"]) for a in json.loads(Path(handoff).read_text())["answered"]],
                         [(E, "distinct", "judge"), (C, "same", "judge")], "every answer kept in the handoff")
        r = call(find, path, "--base-url", self.zot.base_url)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["key"], r.lines[0]["matched_by"], r.lines[0]["reason"]),
                         ("found", C, "same_paper", "stale"), "the item answered same, read from the handoff")
        rec = run.read(path)
        self.assertEqual((run.item_key(rec), p2z.decisions(rec)), (C, []), "found in the library: nothing to tag")
        self.assertEqual(self.answer(handoff, "distinct").lines[0]["code"], "not_open")

    def test_distinct_drops_the_candidates_without_a_key_every_open_one(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        self.assertEqual(self.answer(line["handoff"], "distinct", "--by", "judge").lines[0]["keys"], [C, E])
        r = call(find, path, "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"]), (0, "not_found", "stale"))
        self.assertEqual(run.read(path)["near_matches"], [], "the candidates answered distinct are left out")

    def test_pair_and_unknown_wait_for_the_user(self):
        path, line = self.prepared("b", {"item": {"title": TITLE}})
        handoff = line["handoff"]
        self.tagged("b")
        self.answer(handoff, "pair", "--key", C, "--by", "judge")
        self.assertEqual(p2z.decisions(run.read(path))[0]["waiting_on"], "judge", "E is still the judge's")
        self.answer(handoff, "unknown", "--key", E, "--by", "judge")
        self.assertEqual(p2z.decisions(run.read(path)), [{"same_paper": handoff, "waiting_on": "user"}])
        self.answer(handoff, "distinct", "--key", C, "--key", E, "--by", "user")
        self.assertEqual(p2z.decisions(run.read(path)), [], "the user's word after the judge's pair stands")
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

    def test_several_items_with_the_doi_are_handed_off_and_settled(self):
        doi = "10.1000/twice.1"
        for key in (X, Y):
            self.zot.add_item(key, itemType="journalArticle", title="Twice", DOI=doi)
        path, line = self.prepared("t", {"item": {"title": "Twice", "DOI": doi}, "warnings": ["a type guessed"]})
        rec = run.read(path)
        self.assertIsNone(run.item_key(rec), "files never go to one of two duplicates by chance")
        candidates = json.loads(Path(line["handoff"]).read_text())["candidates"]
        self.assertEqual((line["code"], [(c["key"], c["matched_by"]) for c in candidates]), ("near_match", [(X, "doi"), (Y, "doi")]),
                         "both carry the paper's DOI: which is the paper's is the handoff's question")
        rec["checks"] = {"code": "needs_attention", "mapped": [{"from": "publicationTitle", "to": "proceedingsTitle"}],
                         "to_extra": [], "dropped_or_rewritten": [], "missing_minimum": ["date"], "incomplete": ["schema"]}
        rec["accepted"] = ["a type guessed"]
        self.assertEqual(p2z.decisions(rec), [{"same_paper": line["handoff"], "waiting_on": "judge"},
                                              {"tags": str(self.work.root / "tags" / "t.json")},
                                              {"checks": ["mapped:publicationTitle", "missing_minimum:date"]},
                                              {"unanswered": ["schema"]}])
        self.answer(line["handoff"], "same", "--key", Y, "--reason", "the fuller item: abstract and PDF", "--by", "judge")
        path, line = self.prepared("t", json.loads(path.read_text()))
        self.assertEqual((line["code"], line["key"], line["matched_by"]), ("found", Y, "same_paper"))
        rec = run.read(path)
        self.assertEqual(run.item_key(rec), Y, "the files go to the item answered same")
        self.assertEqual(p2z.decisions(rec), [{"warnings": ["a type guessed"]}], "in the library: nothing to tag")
        rec["accepted"] = ["a type guessed"]
        self.assertEqual(p2z.decisions(rec), [])


if __name__ == "__main__":
    unittest.main()
