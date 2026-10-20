# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/make_collection.py against the fake Zotero."""
import json
import unittest

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero, LIB

make = load("make_collection")
TREE = [("AAAAAAAA", "自然图像", None), ("BBBBBBBB", "Diffusion", "AAAAAAAA"), ("CCCCCCCC", "tmp", None),
        ("DDDDDDDD", "Diffusion", None), ("EEEEEEEE", "twice", "AAAAAAAA"), ("FFFFFFFF", "twice", "AAAAAAAA")]


class MakeCollection(unittest.TestCase):
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
        for key, name, parent in TREE:
            z.add_collection(key, name, parent)
        z.add_collection("GGGGGGGG", "gone", deleted=True)
        z.add_collection("HHHHHHHH", "under gone", "GGGGGGGG")

    def run_(self, *argv, base_url=None, config=None):
        return call(make, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def posts(self):
        return [json.loads(body) for _, _, _, body in self.zot.requested("POST")]

    def test_exists_is_skipped(self):
        r = self.run_("--name", "tmp")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines, [{"key": "CCCCCCCC", "code": "skipped", "reason": "exists", "name": "tmp", "parent": None,
                                    "path": "tmp"}])
        self.assertEqual(self.posts(), [])

    def test_exists_only_under_the_same_parent(self):
        r = self.run_("--name", "Diffusion", "--parent", "AAAAAAAA")
        self.assertEqual((r.code, r.lines[0]["key"], r.lines[0]["path"]), (0, "BBBBBBBB", "自然图像/Diffusion"))
        self.assertEqual(self.run_("--name", "Diffusion").lines[0]["key"], "DDDDDDDD")

    def test_ambiguous(self):
        r = self.run_("--name", "twice", "--parent", "AAAAAAAA")
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["keys"]), ("ambiguous", ["EEEEEEEE", "FFFFFFFF"]))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(self.posts(), [])

    def test_parent_not_found_missing_trashed_or_under_trashed(self):
        for parent in ("ZZZZZZZZ", "GGGGGGGG", "HHHHHHHH"):
            r = self.run_("--name", "x", "--parent", parent)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, "parent_not_found"), parent)
        self.assertEqual(self.posts(), [])

    def test_trashed_collection_does_not_count_as_existing(self):
        r = self.run_("--name", "gone", "--dry-run")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["dry_run"]), (0, "ok", True))

    def test_creates_under_parent_then_rerun_finds_it(self):
        r = self.run_("--name", "Mean Flow", "--parent", "AAAAAAAA")
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual({k: line[k] for k in ("key", "code", "name", "parent", "path")},
                         {"key": "NEW00001", "code": "ok", "name": "Mean Flow", "parent": "AAAAAAAA", "path": "自然图像/Mean Flow"})
        self.assertIsInstance(line["version"], int)
        self.assertEqual(self.posts(), [[{"name": "Mean Flow", "parentCollection": "AAAAAAAA"}]])
        r = self.run_("--name", "Mean Flow", "--parent", "AAAAAAAA")
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["key"]), ("skipped", "exists", "NEW00001"))
        self.assertEqual(len(self.posts()), 1)

    def test_top_level_sends_false_parent(self):
        r = self.run_("--name", "新分类")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["path"]), (0, "ok", "新分类"))
        self.assertEqual(self.posts(), [[{"name": "新分类", "parentCollection": False}]])

    def test_dry_run_posts_nothing(self):
        r = self.run_("--name", "新分类", "--parent", "AAAAAAAA", "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines, [{"key": None, "code": "ok", "name": "新分类", "parent": "AAAAAAAA", "path": "自然图像/新分类",
                                    "dry_run": True}])
        self.assertEqual(self.zot.writes(), [])

    def test_write_denied_write_failed_readback_mismatch(self):
        self.zot.write_status = (403, "Write access denied")
        r = self.run_("--name", "x")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_denied", "Write access denied"))

        self.setUp()
        self.zot.reject = lambda obj: (400, "Collection name too long")
        r = self.run_("--name", "x")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_failed", "Collection name too long"))

        self.setUp()
        create = self.zot.create

        def renamed(obj, collection=False):   # Zotero stores another name than the one sent
            row = create(obj, collection)
            row["data"]["name"] += " (1)"
            return row
        self.zot.create = renamed
        r = self.run_("--name", "x")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["key"]), (1, "readback_mismatch", "NEW00001"))
        self.assertEqual(r.lines[0]["read_back"], {"name": "x (1)", "parentCollection": False})

    def test_second_page_is_read(self):
        z = self.zot
        z.reset()
        for i in range(150):
            z.add_collection(f"C{i:07d}", f"c{i}")
        z.add_collection("TARGET01", "late", "C0000149")
        r = self.run_("--name", "late", "--parent", "C0000149")
        self.assertEqual((r.lines[0]["code"], r.lines[0]["key"], r.lines[0]["path"]), ("skipped", "TARGET01", "c149/late"))
        self.assertEqual([q["start"] for _, _, q, _ in z.requested("GET", f"{LIB}/collections")], ["0", "100"])

    def test_cannot_check_and_arguments(self):
        r = self.run_("--name", "x", base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("--name", "x", "--dry-run", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), "a dry run writes nothing, so it needs no key")
        r = self.run_("--name", "x", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        self.zot.requests.clear()
        r = self.run_("--name", "  ")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "invalid_name"))
        self.assertEqual(self.zot.requests, [], "a blank name asks Zotero nothing")
        self.assertEqual(self.run_().code, 2)
        self.assertEqual(self.run_("--name", "x", "--parent", "short").code, 2)

    def test_smoke(self):
        r = smoke("make_collection", "--name", "tmp", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["code"], o["key"]) for o in r.lines], [("skipped", "CCCCCCCC")])


if __name__ == "__main__":
    unittest.main()
