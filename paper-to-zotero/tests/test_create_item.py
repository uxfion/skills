# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/create_item.py against the fake Zotero: creating, the look before the POST, a cut-off run, and
what stops a record or the run."""
import json
import tempfile
import unittest

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

create = load("create_item")
COLL, COLL2 = "COLL0001", "COLL0002"
DOI = "10.1109/JBHI.2022.3142076"


class CreateItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot, cls.config = FakeZotero(), config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        self.zot.add_collection(COLL, "Inbox")
        self.zot.add_collection(COLL2, "Methods")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-create-"))
        self.work.records.mkdir()

    def record(self, slug, title=None, **extra):
        path = self.work.records / f"{slug}.json"
        rec = {"item": {"itemType": "journalArticle", "title": title or f"Paper {slug}", "creators": [{"creatorType": "author",
               "firstName": "Wei", "lastName": "Liu"}]}, "tags": ["method/diffusion"], "collection": COLL, **extra}
        path.write_text(json.dumps(rec), encoding="utf-8")
        return path

    def run_(self, *argv, base_url=None):
        return call(create, *argv, "--base-url", base_url or self.zot.base_url, config=self.config)

    def posts(self):
        return [r for r in self.zot.requested("POST", "/api/users/0/items")]

    def test_creates_filed_tagged_and_keyed(self):
        a = self.record("a", collection=[COLL, COLL2], citationKey="liu_2022")
        b = self.record("b", tags=[{"tag": "auto", "type": 1}])
        r = self.run_(a, b)
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual((line["code"], line["collection"], line["citationKey"], line["citation_key_hint"]["suggested"]),
                         ("ok", [COLL, COLL2], "liu_2022", "liu2022"))
        rec = run.read(a)
        data = self.zot.data(rec["saved"]["key"])
        self.assertEqual((data["collections"], data["tags"], data["citationKey"]), ([COLL, COLL2], [{"tag": "method/diffusion", "type": 0}], "liu_2022"))
        self.assertEqual(set(rec["saved"]), {"key", "version", "citationKey", "created_at"})
        self.assertEqual((rec["found"]["code"], rec["near_matches"]), ("not_found", []), "the look before the POST is recorded")
        self.assertEqual(len(self.posts()), 2)
        r = self.run_(a, b)
        self.assertEqual([(o["code"], o["reason"]) for o in r.lines[:2]], [("skipped", "saved")] * 2)
        self.assertEqual(len(self.posts()), 2, "nothing posted twice")
        # A thin POST reply: the item is read back.
        self.zot.thin_post_reply = True
        self.assertEqual(self.run_(self.record("c")).lines[0]["code"], "ok")
        # Zotero drops a tag on the way: created, but not as sent.
        self.zot.thin_post_reply = False
        self.zot.on_write = lambda it: it["data"].update(tags=[])
        r = self.run_(self.record("d"))
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["wrong"]), (1, "readback_mismatch", {"tags": True}))
        self.assertIn("key", run.read(self.work.records / "d.json")["saved"])

    def test_the_library_has_it(self):
        self.zot.add_item("HAVE0001", itemType="journalArticle", title="Old Title", DOI=DOI)
        self.zot.add_item("LIKE0001", itemType="journalArticle", title="Paper near")
        r = self.run_(self.record("doi", item={"itemType": "journalArticle", "title": "x", "DOI": DOI}), self.record("near"))
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(o["code"], o.get("reason"), o.get("key")) for o in r.lines[:2]],
                         [("skipped", "exists", "HAVE0001"), ("possible_duplicate", None, None)])
        self.assertEqual(r.lines[1]["near_matches"][0]["key"], "LIKE0001")
        self.assertEqual(self.posts(), [])
        near = run.read(self.work.records / "near.json")
        near["distinct_from"] = ["LIKE0001"]
        near.save()
        self.assertEqual(self.run_(near.path).lines[0]["code"], "ok", "another paper: created")

    def test_a_cut_off_run_is_safe_to_rerun(self):
        pending = {"saved": {"pending": True, "at": "2026-10-20T00:00:00Z"}}
        self.zot.add_item("MADE0001", itemType="journalArticle", title="Paper made", DOI=DOI, citationKey="liu2022")
        made = self.record("made", item={"itemType": "journalArticle", "title": "Paper made", "DOI": DOI}, **pending)
        lost = self.record("lost", **pending)
        r = self.run_(made, lost)
        self.assertEqual([(o["code"], o["key"]) for o in r.lines[:2]][0], ("ok", "MADE0001"))
        self.assertTrue(r.lines[0]["recovered"])
        self.assertEqual(run.read(made)["saved"]["created_at"], "2026-10-20T00:00:00Z")
        self.assertEqual(len(self.posts()), 1, "only the item the cut-off POST did not create")
        self.assertEqual(run.read(lost)["saved"]["key"], r.lines[1]["key"])

    def test_what_stops_a_record_or_the_run(self):
        r = self.run_(self.record("nocoll", collection=None), self.record("gone", collection="GONE0001"),
                      self.record("tags", tags=[{"tag": ""}]), self.record("child", item={"itemType": "note", "title": "x"}))
        self.assertEqual([o["code"] for o in r.lines[:4]], ["no_collection", "collection_not_found", "invalid_tags", "item_invalid"])
        self.assertEqual(self.posts(), [])
        self.zot.write_status = (400, "Invalid field")
        r = self.run_(self.record("refused"))
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "write_failed"))
        self.assertNotIn("saved", run.read(self.work.records / "refused.json"), "nothing created: no pending mark")
        self.zot.write_status = None
        dry, posts = self.record("dry"), len(self.posts())
        r = self.run_(dry, "--dry-run")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[-1]["summary"]["dry_run"]), (0, "ok", True))
        self.assertEqual((len(self.posts()), "saved" in run.read(dry)), (posts, False))
        bad = self.work.records / "bad.json"
        bad.write_text("[1]")
        r = self.run_(dry, bad)
        self.assertEqual((r.code, r.lines[-1]["summary"]["not_run"]), (1, 1), "a file that is not a record: nothing written")
        r = self.run_(dry, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))

    def test_smoke(self):
        r = smoke("create_item", self.record("s"), "--dry-run", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
