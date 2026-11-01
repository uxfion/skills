# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/find_in_library.py: the records' found / near_matches, and --file, against the fake Zotero (the
lookup's rules are tested once, in test_p2zlib.py's Lookup)."""
import hashlib
import json
import tempfile
import unittest

from helpers import call, closed_port, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

find = load("find_in_library")
A, ATT, C, E = "AAAAAAA1", "AAAAATT1", "CCCCCCC1", "EEEEEEE1"
DOI = "10.1109/JBHI.2022.3142076"


class FindInLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_item(A, itemType="journalArticle", title="Progressive Residual Learning", DOI=DOI, citationKey="liu2022progressive")
        z.add_item(ATT, itemType="attachment", parentItem=A, title="PDF", contentType="application/pdf", md5="abc123")
        z.add_item(C, itemType="conferencePaper", title="Deep Residual Learning for Image Recognition")
        z.add_item(E, itemType="journalArticle", title="Deep Residual Learning for Image Recognition: Extended")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-find-"))
        self.work.records.mkdir()

    def record(self, slug, data):
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def run_(self, *argv, base_url=None):
        return call(find, *argv, "--base-url", base_url or self.zot.base_url)

    def test_found_near_and_not_found_go_into_the_record(self):
        paths = [self.record("a", {"item": {"DOI": DOI, "title": "x"}}),
                 self.record("b", {"item": {"title": "Deep Residual Learning for Image Recognition"}}),
                 self.record("c", {"item": {"title": "Nothing like this at all"}}),
                 self.record("d", {"tags": []})]
        r = self.run_(*paths)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(o["slug"], o["code"]) for o in r.lines[:4]],
                         [("a", "found"), ("b", "near_match"), ("c", "not_found"), ("d", "no_item")])
        self.assertEqual((r.lines[0]["key"], r.lines[0]["matched_by"], r.lines[0]["attachments"], r.lines[0]["reason"]),
                         (A, "doi", 1, "absent"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual([m["key"] for m in r.lines[1]["near_matches"]], [C, E])
        handoff = json.loads(open(r.lines[1]["handoff"], encoding="utf-8").read())
        self.assertEqual((handoff["kind"], handoff["taker"], handoff["paper"]["title"], [c["key"] for c in handoff["candidates"]]),
                         ("same_paper", "judge", "Deep Residual Learning for Image Recognition", [C, E]),
                         "the open candidates go to a judge, with the evidence in the file")
        self.assertEqual(r.lines[-1]["summary"], {"total": 4, "ok": 2, "skipped": 0, "failed": 2})
        a, b, c = (run.read(p) for p in paths[:3])
        self.assertEqual((a["found"]["code"], a["found"]["key"], a["near_matches"]), ("found", A, []))
        self.assertEqual((b["found"]["code"], [m["key"] for m in b["near_matches"]]), ("not_found", [C, E]))
        self.assertNotIn("key", b["found"], "a near match is never in found")
        self.assertEqual((c["found"]["code"], c["near_matches"]), ("not_found", []))
        self.assertEqual(run.item_key(a), A)
        self.assertIsNone(run.item_key(b))

    def test_the_agents_decision_settles_a_near_match(self):
        b = self.record("b", {"item": {"title": "Deep Residual Learning for Image Recognition"}})
        self.run_(b)
        rec = run.read(b)
        rec["same_as"] = C
        rec.save()
        r = self.run_(b)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["matched_by"], r.lines[0]["reason"]), (0, "found", "same_as", "stale"))
        self.assertEqual(run.item_key(run.read(b)), C)
        rec = run.read(b)
        rec.pop("same_as")
        rec["distinct_from"] = [C, E]
        rec.save()
        r = self.run_(b)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "not_found"))

    def test_a_rerun_skips_what_is_done_and_an_older_runs_found_is_redone(self):
        a = self.record("a", {"item": {"DOI": DOI, "title": "x"}})
        self.run_(a)
        self.zot.requests.clear()
        r = self.run_(a)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["key"]), ("skipped", "done", A))
        self.assertEqual(self.zot.requests, [])
        old = self.record("old", {"item": {"title": "Deep Residual Learning for Image Recognition"},
                                  "found": {"code": "near_match", "key": C}})
        r = self.run_(old)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("near_match", "absent"),
                         "a found without `from` is not trusted")
        self.assertNotIn("key", run.read(old)["found"])

    def test_files_by_md5(self):
        held, other = self.work.root / "held.pdf", self.work.root / "other.pdf"
        held.write_bytes(b"%PDF held")
        other.write_bytes(b"%PDF other")
        md5 = hashlib.md5(b"%PDF held").hexdigest()
        self.zot.add_item("AAAAATT2", itemType="attachment", parentItem=A, title="PDF", contentType="application/pdf", md5=md5)
        r = self.run_("--file", held, other, self.work.root / "gone.pdf")
        self.assertEqual(r.code, 1, r)
        self.assertEqual(r.lines[0], {"file": str(held), "md5": md5, "code": "found", "attachment": "AAAAATT2", "parent": A,
                                      "citationKey": "liu2022progressive", "title": "Progressive Residual Learning"})
        self.assertEqual([o["code"] for o in r.lines[1:3]], ["not_found", "unreadable"])
        self.assertEqual(self.run_("--file", other).code, 0, "not_found is an answer")
        self.assertEqual(self.run_("--file", held, base_url=f"http://127.0.0.1:{closed_port()}").code, 2)

    def test_cannot_check(self):
        a = self.record("a", {"item": {"DOI": DOI, "title": "x"}})
        r = self.run_(a, self.record("b", {"item": {"title": "y"}}), base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, [o["code"] for o in r.lines[:2]]), (2, ["zotero_unreachable", "not_run"]))
        self.assertNotIn("found", run.read(a))
        self.zot.disabled = True
        self.assertEqual(self.run_(a).lines[0]["code"], "local_api_disabled")
        self.assertEqual(self.run_().lines[0]["code"], "no_records")

    def test_smoke(self):
        r = smoke("find_in_library", self.record("a", {"item": {"DOI": DOI, "title": "x"}}), "--base-url", self.zot.base_url)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "found"), r)


if __name__ == "__main__":
    unittest.main()
