# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/trash_item.py against the fake Zotero."""
import json
import unittest

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero

PARENT, ATT, NOTE, OLD, TRASHED, DUP1, DUP2 = "PARENT01", "ATTACH01", "NOTE0001", "OLDITEM1", "TRASHED1", "DUPKEY01", "DUPKEY02"
trash = load("trash_item")


class TrashItem(unittest.TestCase):
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
        z.add_item(PARENT, version=10, meta={"numChildren": 2}, itemType="journalArticle",
                   title="A paper with a superseded preprint", citationKey="liu2022paper")
        z.add_item(ATT, version=11, itemType="attachment", parentItem=PARENT, title="Preprint", linkMode="imported_url")
        z.add_item(NOTE, version=12, itemType="note", parentItem=PARENT, note="<p>a note</p>")
        z.add_item(OLD, version=13, meta={"numChildren": 0}, itemType="webpage", title="Orphan webpage")
        z.add_item(TRASHED, version=14, meta={"numChildren": 0}, itemType="journalArticle", title="Already gone",
                   deleted=True, citationKey="gone2020")
        z.add_item(DUP1, version=15, itemType="journalArticle", title="Dup one", citationKey="dupkey")
        z.add_item(DUP2, version=16, itemType="journalArticle", title="Dup two", citationKey="dupkey")

    def run_(self, *argv, base_url=None, config=None, stdin=""):
        return call(trash, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config, stdin=stdin)

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def test_trash_writes_deleted_with_version_and_reports(self):
        r = self.run_(ATT, OLD)
        self.assertEqual((r.code, r.err), (0, ""), r)
        out = r.lines
        self.assertEqual(out[0], {"key": ATT, "code": "ok", "itemType": "attachment", "title": "Preprint", "parent": PARENT,
                                  "parent_title": "A paper with a superseded preprint", "version": out[0]["version"],
                                  "retried": False})
        self.assertGreater(out[0]["version"], 11)
        self.assertEqual((out[1]["code"], out[1]["children"], out[1]["parent"]), ("ok", 0, None))
        self.assertEqual(self.patches(), [(ATT, {"deleted": 1}), (OLD, {"deleted": 1})])
        self.assertTrue(self.zot.data(ATT)["deleted"])

    def test_already_trashed_is_skipped_and_rerun_is_a_no_op(self):
        r = self.run_(TRASHED)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "already_trashed"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(self.patches(), [])
        self.run_(OLD)
        self.assertEqual(self.run_(OLD).lines[0]["reason"], "already_trashed")
        self.assertEqual(len(self.patches()), 1)

    def test_names_that_are_not_one_item_fail_their_own_lines(self):
        r = self.run_("GONE0000", OLD, "nobody", "dupkey", "liu2022paper", PARENT, "-n")
        self.assertEqual(r.code, 1)
        self.assertEqual([(o.get("key") or o.get("item"), o["code"]) for o in r.lines],
                         [("GONE0000", "not_found"), (OLD, "ok"), ("nobody", "not_found"), ("dupkey", "ambiguous"),
                          (PARENT, "ok")], "an item named twice (citation key, then key) once")
        self.assertEqual((r.lines[3]["keys"], r.lines[4]["cite"]), ([DUP1, DUP2], "liu2022paper"))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(r.last, {"summary": {"total": 5, "ok": 2, "skipped": 0, "failed": 3}})

    def test_restore_and_stdin(self):
        r = self.run_("--restore", "-", stdin=json.dumps({"key": TRASHED, "title": "Already gone"}) + "\nOLDITEM1\n")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["code"], o.get("reason")) for o in r.lines], [("ok", None), ("skipped", "not_in_trash")])
        self.assertEqual(self.patches(), [(TRASHED, {"deleted": 0})])
        self.assertNotIn("deleted", self.zot.data(TRASHED))

    def test_dry_run_lists_and_writes_nothing(self):
        r = self.run_(PARENT, ATT, "-n", NOTE, TRASHED)
        self.assertEqual((r.code, r.err), (0, ""), r)
        out = r.lines
        self.assertEqual(out[0], {"key": PARENT, "code": "ok", "itemType": "journalArticle",
                                  "title": "A paper with a superseded preprint", "parent": None, "children": 2,
                                  "version": 10, "dry_run": True})
        self.assertEqual((out[1]["parent"], out[1]["parent_title"]), (PARENT, "A paper with a superseded preprint"))
        self.assertEqual((out[2]["itemType"], out[2]["title"]), ("note", "<p>a note</p>"))
        self.assertEqual(out[3]["reason"], "already_trashed", "a key finds an item in the trash too")
        self.assertEqual(self.zot.writes(), [])

    def test_412_once_retries_twice_conflicts(self):
        self.zot.bump_before_write = 1
        r = self.run_(OLD)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["retried"]), ("ok", True))
        self.assertEqual(len(self.patches()), 2)

        self.setUp()
        self.zot.bump_before_write = 2
        r = self.run_(OLD)
        self.assertEqual(r.code, 1)
        self.assertEqual(r.lines[0]["code"], "version_conflict")
        self.assertEqual(len(self.patches()), 2)

    def test_412_because_someone_trashed_it_meanwhile(self):
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(deleted=True)
        r = self.run_(OLD)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["reason"], r.lines[0]["retried"]), ("already_trashed", True))
        self.assertEqual(len(self.patches()), 1)

    def test_readback_mismatch_and_write_denied(self):
        self.zot.ignore_writes = True
        r = self.run_(OLD)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "readback_mismatch"))
        self.setUp()
        self.zot.write_status = (403, "Write access denied")
        r = self.run_(OLD)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_denied", "Write access denied"))

    def test_cannot_check_and_arguments(self):
        r = self.run_(OLD, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "zotero_unreachable"))
        r = self.run_(OLD, config=config_file(key=None))
        self.assertEqual((r.code, r.last["code"]), (2, "no_key"))
        self.zot.write_status = (401, "bad key")
        r = self.run_(OLD, PARENT)
        self.assertEqual((r.code, r.lines, r.last["code"]),
                         (2, [{"key": OLD, "code": "not_run"}, {"item": PARENT, "code": "not_run"}], "key_rejected"),
                         "the item it stopped on and the rest (not read yet): not_run; why: stderr's last line")
        self.assertEqual((self.run_().code, self.run_().last["code"]), (2, "usage"))

    def test_through_the_entry(self):
        r = smoke("trash", "-n", OLD, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.err, r.lines[0]["code"]), (0, "", "ok"), r)


if __name__ == "__main__":
    unittest.main()
