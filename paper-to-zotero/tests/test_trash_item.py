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

    def run_(self, *argv, base_url=None, config=None):
        return call(trash, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def test_trash_writes_deleted_with_version_and_reports(self):
        r = self.run_("--key", ATT, OLD)
        self.assertEqual(r.code, 0, r)
        out = r.lines
        self.assertEqual(out[0], {"key": ATT, "code": "ok", "itemType": "attachment", "title": "Preprint", "parent": PARENT,
                                  "parent_title": "A paper with a superseded preprint", "version": out[0]["version"],
                                  "retried": False})
        self.assertGreater(out[0]["version"], 11)
        self.assertEqual((out[1]["code"], out[1]["children"], out[1]["parent"]), ("ok", 0, None))
        self.assertEqual(out[-1], {"summary": {"total": 2, "ok": 2, "skipped": 0, "failed": 0}})
        self.assertEqual(self.patches(), [(ATT, {"deleted": 1}), (OLD, {"deleted": 1})])
        self.assertTrue(self.zot.data(ATT)["deleted"])

    def test_already_trashed_is_skipped_and_rerun_is_a_no_op(self):
        r = self.run_("--key", TRASHED)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "already_trashed"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(r.lines[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        self.assertEqual(self.patches(), [])
        self.run_("--key", OLD)
        r = self.run_("--key", OLD)
        self.assertEqual(r.lines[0]["reason"], "already_trashed")
        self.assertEqual(len(self.patches()), 1)

    def test_not_found_fails_only_its_own_line(self):
        r = self.run_("--key", "GONE0000,", OLD)
        self.assertEqual(r.code, 1)
        self.assertEqual([o["code"] for o in r.lines[:2]], ["not_found", "ok"])
        self.assertIn("hint", r.lines[0])
        self.assertEqual(r.lines[-1]["summary"], {"total": 2, "ok": 1, "skipped": 0, "failed": 1})

    def test_restore(self):
        r = self.run_("--key", TRASHED, "--key", OLD, "--restore")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["code"], o.get("reason")) for o in r.lines[:2]], [("ok", None), ("skipped", "not_in_trash")])
        self.assertEqual(self.patches(), [(TRASHED, {"deleted": 0})])
        self.assertNotIn("deleted", self.zot.data(TRASHED))

    def test_dry_run_lists_and_writes_nothing(self):
        r = self.run_("--key", PARENT, ATT, NOTE, TRASHED, "--dry-run")
        self.assertEqual(r.code, 0, r)
        out = r.lines
        self.assertEqual(out[0], {"key": PARENT, "code": "ok", "itemType": "journalArticle",
                                  "title": "A paper with a superseded preprint", "parent": None, "children": 2,
                                  "version": 10, "dry_run": True})
        self.assertEqual((out[1]["parent"], out[1]["parent_title"]), (PARENT, "A paper with a superseded preprint"))
        self.assertEqual((out[2]["itemType"], out[2]["title"]), ("note", "<p>a note</p>"))
        self.assertEqual(out[3]["reason"], "already_trashed")
        self.assertEqual(out[-1]["summary"], {"total": 4, "ok": 3, "skipped": 1, "failed": 0, "dry_run": True})
        self.assertEqual(self.zot.writes(), [])

    def test_412_once_retries_twice_conflicts(self):
        self.zot.bump_before_write = 1
        r = self.run_("--key", OLD)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["retried"]), ("ok", True))
        self.assertEqual(len(self.patches()), 2)

        self.setUp()
        self.zot.bump_before_write = 2
        r = self.run_("--key", OLD)
        self.assertEqual(r.code, 1)
        self.assertEqual(r.lines[0]["code"], "version_conflict")
        self.assertEqual(len(self.patches()), 2)

    def test_412_because_someone_trashed_it_meanwhile(self):
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(deleted=True)
        r = self.run_("--key", OLD)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["reason"], r.lines[0]["retried"]), ("already_trashed", True))
        self.assertEqual(len(self.patches()), 1)

    def test_readback_mismatch_and_write_denied(self):
        self.zot.ignore_writes = True
        r = self.run_("--key", OLD)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "readback_mismatch"))
        self.setUp()
        self.zot.write_status = (403, "Write access denied")
        r = self.run_("--key", OLD)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_denied", "Write access denied"))

    def test_cite_resolution(self):
        r = self.run_("--cite", "liu2022paper", "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["cite"], r.lines[0]["code"]), (PARENT, "liu2022paper", "ok"))
        self.assertEqual(self.zot.requested("GET", "/api/users/0/items/top"), [])

        self.zot.search_sees_citekey = False
        self.zot.requests.clear()
        r = self.run_("--cite", "liu2022paper", "nobody", "dupkey", "--dry-run")
        self.assertEqual(r.code, 1)
        out = r.lines
        self.assertEqual(out[0]["key"], PARENT, "found by the fallback scan")
        self.assertEqual(len(self.zot.requested("GET", "/api/users/0/items/top")), 1, "one shared scan for every missed cite")
        self.assertEqual(out[1], {"cite": "nobody", "code": "cite_not_found", "hint": out[1]["hint"]})
        self.assertEqual((out[2]["code"], out[2]["keys"]), ("cite_ambiguous", [DUP1, DUP2]))
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 1, "skipped": 0, "failed": 2, "dry_run": True})

    def test_key_named_twice_is_handled_once(self):
        r = self.run_("--key", PARENT, "--cite", "liu2022paper")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[-1]["summary"]["total"], 1)
        self.assertEqual(len(self.patches()), 1)

    def test_cannot_check_and_arguments(self):
        r = self.run_("--key", OLD, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("--key", OLD, config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        r = self.run_("--key", OLD, PARENT, config=config_file(key="wrong"))
        self.assertEqual(r.code, 2)
        self.assertEqual([o["code"] for o in r.lines[:2]], ["key_rejected", "not_run"], "the item it stopped on says why")
        self.assertEqual(r.lines[-1]["summary"]["stopped"], "key_rejected")
        self.assertEqual(self.run_().code, 2)
        self.assertEqual(self.run_("--key", "short").code, 2)

    def test_smoke(self):
        r = smoke("trash_item", "--key", OLD, "--dry-run", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["code"], "ok")
        self.assertEqual(r.lines[-1]["summary"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
