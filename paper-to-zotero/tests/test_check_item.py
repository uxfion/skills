# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_item.py against the fake Zotero's schema."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

check = load("check_item")
FIELDS = {
    "journalArticle": [{"field": f} for f in ("title", "abstractNote", "publicationTitle", "volume", "date", "DOI", "url", "extra")],
    "conferencePaper": [{"field": "title"}, {"field": "abstractNote"}, {"field": "proceedingsTitle", "baseField": "publicationTitle"},
                        {"field": "conferenceName"}, {"field": "date"}, {"field": "DOI"}, {"field": "url"}, {"field": "publisher"},
                        {"field": "extra"}],
}
CREATORS = [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}]
SCHEMA = {"version": 44, "itemTypes": [{"itemType": t, "fields": f, "creatorTypes": CREATORS} for t, f in FIELDS.items()]}
OK_ITEM = {"itemType": "journalArticle", "title": "A Paper", "creators": [{"creatorType": "author", "firstName": "A", "lastName": "B"}],
           "date": "2024", "DOI": "10.1/x", "publicationTitle": "J"}
MAPPED_ITEM = {"itemType": "conferencePaper", "title": "A Talk", "creators": [{"creatorType": "author", "name": "C"}],
               "date": "2024", "DOI": "10.1/y", "publicationTitle": "Proc"}
UNKNOWN_ITEM = {"itemType": "journalArticl", "title": "Typo"}


class CheckItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        self.zot.schema = json.loads(json.dumps(SCHEMA))
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-check-"))
        self.work.records.mkdir()

    def record(self, slug, data):
        path = self.work.records / f"{slug}.json"
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def run_(self, *argv, base_url=None):
        return call(check, *argv, "--base-url", base_url or self.zot.base_url)

    def test_each_record_gets_checks_with_its_inputs(self):
        paths = [self.record("a", {"item": OK_ITEM, "note_to_self": "keep me"}), self.record("b", {"item": MAPPED_ITEM}),
                 self.record("c", {"item": UNKNOWN_ITEM}), self.record("d", {"tags": []})]
        r = self.run_(*paths)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(o["slug"], o["code"]) for o in r.lines[:4]],
                         [("a", "ok"), ("b", "needs_attention"), ("c", "unknown_item_type"), ("d", "no_item")])
        self.assertEqual((r.lines[0]["reason"], r.lines[0]["itemType"]), ("absent", "journalArticle"))
        self.assertEqual(r.lines[1]["mapped"], [{"from": "publicationTitle", "to": "proceedingsTitle"}])
        self.assertIn("hint", r.lines[1])
        self.assertEqual(r.lines[2]["suggestions"], ["journalArticle"])
        self.assertEqual(r.lines[-1], {"summary": {"total": 4, "ok": 1, "skipped": 0, "failed": 3}})
        a = run.read(paths[0])
        self.assertEqual((a["note_to_self"], a["checks"]["code"], a["checks"]["missing_minimum"]), ("keep me", "ok", []))
        self.assertIsNone(run.due(a, "checks"))
        self.assertNotIn("checks", run.read(paths[3]), "a record without an item gets nothing written")

    def test_a_rerun_skips_what_is_done_and_redoes_what_changed(self):
        a, b = self.record("a", {"item": OK_ITEM}), self.record("b", {"item": MAPPED_ITEM})
        self.run_(a, b)
        self.zot.requests.clear()
        r = self.run_(a, b)
        self.assertEqual([(o["code"], o.get("reason"), o.get("checks")) for o in r.lines[:2]],
                         [("skipped", "done", "ok"), ("skipped", "done", "needs_attention")])
        self.assertEqual(r.code, 0, "a done block is not the agent's to act on again")
        self.assertEqual(self.zot.requests, [], "nothing asked of Zotero")
        rec = run.read(b)
        rec["item"]["proceedingsTitle"] = rec["item"].pop("publicationTitle")
        rec.save()
        r = self.run_(b)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("ok", "stale"))

    def test_the_schema_is_read_once_a_run(self):
        self.run_(self.record("a", {"item": OK_ITEM}))
        self.assertTrue((self.work.scratch / "schema.json").is_file())
        self.zot.requests.clear()
        self.run_(self.record("b", {"item": MAPPED_ITEM}))
        self.assertEqual(self.zot.requested("GET", "/api/schema"), [])

    def test_a_bad_file_does_not_stop_the_others(self):
        bad = self.record("bad", "{not json")
        r = self.run_(bad, self.record("good", {"item": OK_ITEM}))
        self.assertEqual([(o["slug"], o["code"]) for o in r.lines[:2]], [("bad", "record_invalid"), ("good", "ok")])
        self.assertEqual(bad.read_text(), "{not json")

    def test_help_has_the_skeleton_and_cannot_check(self):
        r = self.run_("--help")
        self.assertEqual(r.code, 0)
        self.assertIn('"itemType": "journalArticle"', r.out)
        a = self.record("a", {"item": OK_ITEM})
        r = self.run_(a, self.record("b", {"item": OK_ITEM}), base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, [o["code"] for o in r.lines[:2]]), (2, ["zotero_unreachable", "not_run"]))
        self.zot.disabled = True
        self.assertEqual(self.run_(a).lines[0]["code"], "local_api_disabled")
        self.assertEqual(self.run_().lines[0]["code"], "no_records")

    def test_smoke(self):
        r = smoke("check_item", self.record("a", {"item": OK_ITEM}), "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
