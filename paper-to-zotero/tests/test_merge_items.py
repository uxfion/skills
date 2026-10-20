# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/merge_items.py against the fake Zotero."""
import json
import unittest

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero, LIB

merge = load("merge_items")
KEEP, DROP = "KEEPKEY1", "DROPKEY1"


class MergeItems(unittest.TestCase):
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
        z.add_collection("COLLTMP1", "tmp")
        z.add_collection("COLLREAL", "Medical")
        z.add_collection("COLLOTHR", "Recent")
        z.add_item(KEEP, version=10, itemType="conferencePaper", title="The paper", citationKey="liu2022paper",
                   pages="1-9", extra="arXiv: 2101.00001", collections=["COLLREAL"], tags=[{"tag": "task/Segmentation"}])
        z.add_item(DROP, version=11, itemType="journalArticle", title="The Paper", abstractNote="An abstract.",
                   publicationTitle="Proceedings of X", pages="1-9", ISSN="1234-5678", extra="arXiv: 2101.00001\nPMID: 7",
                   collections=["COLLTMP1", "COLLOTHR"], tags=[{"tag": "task/Segmentation"}, {"tag": "FooNet"}],
                   citationKey="liu2022journal")
        z.add_item("KPDF0001", version=12, itemType="attachment", parentItem=KEEP, contentType="application/pdf", md5="same")
        z.add_item("DPDF0001", version=13, itemType="attachment", parentItem=DROP, contentType="application/pdf", md5="same")
        z.add_item("DPDF0002", version=14, itemType="attachment", parentItem=DROP, contentType="application/pdf", md5="new")
        z.add_item("DNOTE001", version=15, itemType="note", parentItem=DROP, note="<p>a note</p>")
        z.add_item("DSNAP001", version=16, itemType="attachment", parentItem=DROP, contentType="text/html", title="Snapshot")
        z.add_item("DGONE001", version=17, itemType="note", parentItem=DROP, note="<p>trashed</p>", deleted=True)

    def run_(self, *argv, base_url=None, config=None):
        return call(merge, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def test_the_plan(self):
        r = self.run_("--keep", KEEP, "--drop", DROP, "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(len(r.out.splitlines()), 1, "one compact object")
        out = r.lines[0]
        self.assertEqual((out["code"], out["dry_run"]), ("ok", True))
        self.assertNotIn("hint", out)
        self.assertEqual(out["keep"], {"key": KEEP, "title": "The paper", "citationKey": "liu2022paper"})
        self.assertEqual(out["fields"]["fill"], {"abstractNote": "An abstract.", "proceedingsTitle": "Proceedings of X",
                                                 "extra": "arXiv: 2101.00001\nPMID: 7"},
                         "base fields match across types; extra takes the missing lines")
        self.assertEqual(list(out["fields"]["conflicts"]), ["title", "citationKey"])
        self.assertEqual(out["fields"]["not_carried"], ["ISSN"], "no ISSN field on a conference paper")
        self.assertEqual(out["collections"]["after"], ["COLLREAL", "COLLOTHR"], "tmp left out")
        self.assertEqual(out["tags"]["added"], ["FooNet"])
        self.assertEqual([m["key"] for m in out["move"]], ["DPDF0002", "DNOTE001"], "a trashed child is left out")
        self.assertEqual({m["key"] for m in out["left_with_drop"]}, {"DPDF0001", "DSNAP001"})
        self.assertIn(f"trash_item.py --key {DROP} --dry-run", out["next"])
        self.assertEqual(self.zot.writes(), [], "a dry run writes nothing")

    def test_dry_run_needs_no_key(self):
        r = self.run_("--keep", KEEP, "--drop", DROP, "--dry-run", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)

    def test_the_merge_writes_and_reads_back(self):
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual(r.code, 0, r)
        out = r.lines[0]
        self.assertEqual((out["code"], out["retried"]), ("ok", False))
        self.assertNotIn("dry_run", out)
        keep = self.zot.data(KEEP)
        self.assertEqual((keep["abstractNote"], keep["proceedingsTitle"]), ("An abstract.", "Proceedings of X"))
        self.assertEqual(keep["collections"], ["COLLREAL", "COLLOTHR"])
        self.assertEqual([t["tag"] for t in keep["tags"]], ["task/Segmentation", "FooNet"])
        self.assertEqual(out["version"], self.zot.items[KEEP]["version"])
        for key, parent in (("DPDF0002", KEEP), ("DNOTE001", KEEP), ("DSNAP001", DROP), ("DPDF0001", DROP), ("DGONE001", DROP)):
            self.assertEqual(self.zot.data(key)["parentItem"], parent, key)
        self.assertEqual([k for k, _ in self.patches()], [KEEP, "DPDF0002", "DNOTE001"])
        self.assertIn(DROP, self.zot.items, "nothing is deleted")
        self.assertNotIn("deleted", self.zot.data(DROP))

    def test_nothing_to_merge_is_a_skip(self):
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual(r.code, 0, r)
        self.zot.requests.clear()
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "nothing_to_merge"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(self.zot.writes(), [])

    def test_cite_resolution_with_the_fallback_scan(self):
        r = self.run_("--keep", "liu2022paper", "--drop", DROP, "--dry-run")
        self.assertEqual((r.code, r.lines[0]["keep"]["key"]), (0, KEEP), r)
        self.assertEqual(self.zot.requested("GET", f"{LIB}/items/top"), [], "the search hit; no scan")

        self.zot.search_sees_citekey = False
        self.zot.requests.clear()
        r = self.run_("--keep", "liu2022paper", "--drop", "liu2022journal", "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["keep"]["key"], r.lines[0]["drop"]["key"]), (KEEP, DROP), "found by the scan")
        self.assertTrue(self.zot.requested("GET", f"{LIB}/items/top"))

        r = self.run_("--keep", "nobody2099", "--drop", DROP)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["cite"]), (1, "cite_not_found", "nobody2099"))
        self.zot.data(DROP)["citationKey"] = "liu2022paper"
        r = self.run_("--keep", "liu2022paper", "--drop", "DPDF0002")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["keys"]), (1, "cite_ambiguous", [KEEP, DROP]))

    def test_412_once_plans_again_on_the_fresh_item(self):
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(abstractNote="Someone else's abstract.")
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual(r.code, 0, r)
        out = r.lines[0]
        self.assertEqual((out["code"], out["retried"]), ("ok", True))
        first, second = [body for key, body in self.patches() if key == KEEP]
        self.assertEqual(first["abstractNote"], "An abstract.")
        self.assertNotIn("abstractNote", second, "planned again on the item as it now is")
        self.assertNotIn("abstractNote", out["fields"]["fill"])
        self.assertIn("abstractNote", out["fields"]["conflicts"])
        self.assertEqual(self.zot.data(KEEP)["abstractNote"], "Someone else's abstract.")
        self.assertEqual(self.zot.data(KEEP)["proceedingsTitle"], "Proceedings of X")

    def test_412_twice_is_a_version_conflict(self):
        self.zot.bump_before_write = 2
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["key"]), ("version_conflict", KEEP))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(len(self.patches()), 2)

    def test_write_denied_and_readback_mismatch(self):
        self.zot.write_status = (403, "Write access denied")
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"], r.lines[0]["key"]),
                         (1, "write_denied", "Write access denied", KEEP))
        self.setUp()
        self.zot.ignore_writes = True
        r = self.run_("--keep", KEEP, "--drop", DROP)
        out = r.lines[0]
        self.assertEqual((r.code, out["code"]), (1, "readback_mismatch"))
        self.assertEqual(out["unmoved"], ["DPDF0002", "DNOTE001"])
        self.assertIn("abstractNote", out["wrong"])
        self.assertIn("hint", out)

    def test_refusals(self):
        for keep, drop, code in ((KEEP, KEEP, "same_item"), (KEEP, "DPDF0002", "not_top_level"),
                                 (KEEP, "NOSUCHK1", "not_found")):
            r = self.run_("--keep", keep, "--drop", drop)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code), r)
            self.assertIn("hint", r.lines[0])
        self.zot.data(DROP)["deleted"] = True
        r = self.run_("--keep", KEEP, "--drop", DROP)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["key"]), (1, "trashed", DROP))
        self.assertEqual(self.zot.writes(), [])

    def test_cannot_check_and_arguments(self):
        r = self.run_("--keep", KEEP, "--drop", DROP, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("--keep", KEEP, "--drop", DROP, config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        self.assertEqual(self.zot.writes(), [])
        r = self.run_("--keep", KEEP, "--drop", DROP, config=config_file(key="wrong"))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "key_rejected"))
        self.zot.disabled = True
        r = self.run_("--keep", KEEP, "--drop", DROP, "--dry-run")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "local_api_disabled"))
        self.assertEqual(self.run_("--keep", KEEP).code, 2)

    def test_smoke(self):
        r = smoke("merge_items", "--keep", KEEP, "--drop", DROP, "--dry-run", "--base-url", self.zot.base_url,
                  config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((len(r.out.splitlines()), r.lines[0]["code"]), (1, "ok"))


if __name__ == "__main__":
    unittest.main()
