# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/file_and_tag.py against the fake Zotero."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero, LIB

CA, CB, CC, CX, TRASHC = "COLLAAAA", "COLLBBBB", "COLLCCCC", "COLLXXXX", "COLLTRSH"
I1, I2, I3, ATT, DUP1, DUP2 = "ITEM0001", "ITEM0002", "ITEM0003", "ATTACH01", "DUPKEY01", "DUPKEY02"
file_and_tag = load("file_and_tag")


class FileAndTag(unittest.TestCase):
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
        z.add_item(I1, version=10, itemType="journalArticle", title="CycleGAN", citationKey="zhu2017unpaired",
                   collections=[CA, CB, CC], tags=[{"tag": "GAN", "type": 0}])
        z.add_item(I2, version=20, itemType="journalArticle", title="StyleGAN", citationKey="karras2019style",
                   collections=[CA])
        z.add_item(I3, version=30, itemType="journalArticle", title="DDPM", citationKey="ho2020denoising")
        z.add_item(ATT, version=40, itemType="attachment", parentItem=I1, title="PDF")
        z.add_item(DUP1, version=50, itemType="journalArticle", title="Dup one", citationKey="dupkey")
        z.add_item(DUP2, version=51, itemType="journalArticle", title="Dup two", citationKey="dupkey")
        for key, name in ((CA, "CC作业"), (CB, "自然图像"), (CC, "tmp"), (CX, "new")):
            z.add_collection(key, name)
        z.add_collection(TRASHC, "old", deleted=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="file-and-tag-"))

    def run_(self, *argv, base_url=None, config=None, stdin=""):
        return call(file_and_tag, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config,
                    stdin=stdin)

    def file(self, content, name="changes.jsonl"):
        """A change list (name *.jsonl: a JSON line per entry), a tag list file (*.json), or the text given."""
        path = self.tmp / name
        if isinstance(content, str):
            text = content
        elif name.endswith(".jsonl"):
            text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in content)
        else:
            text = json.dumps(content, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
        return path

    def posts(self):
        return [json.loads(body) for _, _, _, body in self.zot.requested("POST", f"{LIB}/items")]

    def colls(self, key):
        return self.zot.data(key)["collections"]

    def tags(self, key):
        return self.zot.data(key)["tags"]

    # ---- the items named after a change option ----------------------------------------------------------------

    def test_remove_collection_keeps_the_others(self):
        r = self.run_(I1, "--remove-collection", CA)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual(r.lines, [{"key": I1, "code": "ok", "title": "CycleGAN",
                                    "collection": {"from": [{"key": CA, "path": "CC作业"}, {"key": CB, "path": "自然图像"},
                                                            {"key": CC, "path": "tmp"}],
                                                   "to": [{"key": CB, "path": "自然图像"}, {"key": CC, "path": "tmp"}]},
                                    "version": r.lines[0]["version"]}], "each collection with its path, for the reader")
        self.assertGreater(r.lines[0]["version"], 10)
        self.assertEqual(self.colls(I1), [CB, CC])
        self.assertEqual(self.posts(), [[{"key": I1, "version": 10, "collections": [CB, CC]}]])
        self.assertEqual(self.zot.requested("PATCH"), [])

    def test_add_and_remove_combine_by_path_or_name_and_rerun_is_a_no_op(self):
        argv = ("zhu2017unpaired", "--add-collection", "new", "--remove-collection", "CC作业", "--remove-collection", CC)
        r = self.run_(*argv)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["cite"]), (I1, "zhu2017unpaired"))
        self.assertEqual(self.colls(I1), [CB, CX])
        r = self.run_(*argv)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "unchanged"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(len(self.zot.requested("GET", f"{LIB}/collections")), 2, "the tree is read once a run")

    def test_several_items_take_the_same_change_in_one_post(self):
        tags = self.file(["diffusion"], "tags.json")
        r = self.run_(I2, "-", "zhu2017unpaired", "--add-tags-file", tags, "--add-tag", "x", "--add-collection", CX,
                      stdin=json.dumps({"key": I3, "title": "DDPM"}) + "\n" + I1 + "\n")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([line["key"] for line in r.lines], [I2, I3, I1], "the cite naming I1 again is handled once")
        [objects] = self.posts()
        self.assertEqual([o["key"] for o in objects], [I2, I3, I1])
        self.assertEqual(self.tags(I1), [{"tag": "GAN", "type": 0}, {"tag": "diffusion", "type": 0}, {"tag": "x", "type": 0}])
        self.assertEqual(self.colls(I3), [CX])

    def test_remove_a_collection_the_item_is_not_in(self):
        r = self.run_(I2, "--remove-collection", CB, "-n")
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "unchanged"))
        self.assertEqual(self.zot.writes(), [])

    def test_set_and_add_semantics(self):
        tags = self.file(["diffusion", {"tag": "auto", "type": 1}], "tags.json")
        r = self.run_(I3, "--set-collection", CB, "--set-tags-file", tags)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["tags_added"], [{"tag": "diffusion", "type": 0}, {"tag": "auto", "type": 1}])
        self.assertNotIn("tags_removed", r.lines[0])
        self.assertEqual(self.colls(I3), [CB])
        self.assertEqual(self.tags(I3), [{"tag": "diffusion", "type": 0}, {"tag": "auto", "type": 1}])
        self.assertEqual(self.run_(I3, "--add-collection", CC).code, 0)
        self.assertEqual(self.colls(I3), [CB, CC])
        self.assertEqual(self.run_(I3, "--set-collection", "none").code, 0)
        self.assertEqual(self.colls(I3), [])
        r = self.run_(self.file([{"key": I2, "collection": None, "add_tags": ["x"]},
                                 {"key": I3, "collection": [CA, "自然图像"]}]))
        self.assertEqual(r.code, 0, r)
        self.assertEqual((self.colls(I2), self.tags(I2)), ([], [{"tag": "x", "type": 0}]))
        self.assertEqual(self.colls(I3), [CA, CB])

    def test_tags_are_the_complete_set_and_a_repeated_tag_keeps_the_last(self):
        r = self.run_(self.file([{"key": I1, "tags": ["CVPR", {"tag": "CVPR", "type": 1}]},
                                 {"key": I2, "title": "StyleGAN", "add_tags": ["x"]}]))
        self.assertEqual(r.code, 0, r)
        self.assertIn("'CVPR' given twice", r.err, "a warning that bears on the result")
        self.assertIn("'title'", r.err, "an unknown field is named on stderr, not refused")
        self.assertEqual(self.tags(I1), [{"tag": "CVPR", "type": 1}])
        self.assertEqual((r.lines[0]["tags_added"], r.lines[0]["tags_removed"]),
                         ([{"tag": "CVPR", "type": 1}], [{"tag": "GAN", "type": 0}]))

    def test_remove_tags_by_name_keeps_the_others(self):
        self.zot.data(I1)["tags"] = [{"tag": "GAN", "type": 0}, {"tag": "Deep learning, theory", "type": 1},
                                     {"tag": "to read", "type": 0}]
        r = self.run_(I1, I2, "--remove-tag", "Deep learning, theory", "--remove-tag", "to read", "--remove-tag", "absent")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["tags_removed"], [{"tag": "Deep learning, theory", "type": 1}, {"tag": "to read", "type": 0}],
                         "each value is one name, its comma kept; the type does not matter")
        self.assertNotIn("tags_added", r.lines[0])
        self.assertEqual(self.tags(I1), [{"tag": "GAN", "type": 0}])
        self.assertEqual((r.lines[1]["key"], r.lines[1]["code"], r.lines[1]["reason"]), (I2, "skipped", "unchanged"))
        self.assertEqual(self.posts(), [[{"key": I1, "version": 10, "tags": [{"tag": "GAN", "type": 0}]}]])

        r = self.run_("-", stdin="\n".join(json.dumps(e) for e in [
            {"cite": "zhu2017unpaired", "add_tags": ["CVPR"], "remove_tags": "GAN"},
            {"key": I2, "remove_tags": [], "add_collection": CX}]))
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["tags_added"], r.lines[0]["tags_removed"]),
                         ([{"tag": "CVPR", "type": 0}], [{"tag": "GAN", "type": 0}]))
        self.assertEqual((self.tags(I1), self.colls(I2), self.tags(I2)), ([{"tag": "CVPR", "type": 0}], [CA, CX], []))

        self.zot.on_write = lambda it: it["data"].update(tags=[{"tag": "CVPR", "type": 0}])
        r = self.run_(I1, "--remove-tag", "CVPR")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["now"]), (1, "readback_mismatch", {"tags": [{"tag": "CVPR", "type": 0}]}))

    # ---- checks before anything is written -----------------------------------------------------------------------

    def test_not_a_parent_and_not_found_write_nothing(self):
        r = self.run_(ATT, I2, "--remove-collection", CA)
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["code"], r.lines[0]["parentItem"]), (ATT, "not_a_parent", I1))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(r.lines[1], {"key": I2, "code": "not_run"})
        r = self.run_("NOPE1234", I2, "nobody2000", "dupkey", "--add-collection", CB)
        self.assertEqual([(line.get("key") or line.get("item"), line["code"]) for line in r.lines],
                         [("NOPE1234", "not_found"), (I2, "not_run"), ("nobody2000", "not_found"), ("dupkey", "ambiguous")])
        self.assertEqual(r.lines[3]["keys"], [DUP1, DUP2])
        self.assertEqual(r.last["summary"], {"total": 4, "ok": 0, "skipped": 0, "failed": 4})
        self.assertEqual(self.zot.writes(), [])
        failed, skip = {"item": "nope", "code": "not_found"}, {"slug": "s", "code": "skipped", "reason": "r"}
        r = self.run_("-", "--add-tag", "read", stdin=f"{json.dumps(failed)}\n{json.dumps(skip)}\n{I2}\n")
        self.assertEqual((r.code, r.lines[:2], r.lines[2]["code"], r.last["summary"]["failed"]), (1, [failed, skip], "ok", 1),
                         "upstream's lines are passed on, not names of this command's: the rest are written")
        self.assertEqual(self.tags(I2), [{"tag": "read", "type": 0}])
        r = self.run_(ATT, "--add-tag", "read")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.tags(ATT), [{"tag": "read", "type": 0}], "tags are fine on an attachment")

    def test_collection_not_found_ambiguous_or_in_the_trash(self):
        self.zot.add_collection("COLLDDDD", "tmp", CB)        # a second "tmp", under 自然图像
        r = self.run_(I3, I2, "--add-collection", "old", "--add-collection", CB)
        self.assertEqual(r.code, 1)
        self.assertEqual([(line["code"], line["collection"]) for line in r.lines], [("collection_not_found", "old")] * 2,
                         "a collection in the trash is no destination")
        r = self.run_(I3, "--add-collection", "tmp")
        self.assertEqual((r.lines[0]["code"], {c["path"] for c in r.lines[0]["candidates"]}),
                         ("ambiguous", {"tmp", "自然图像/tmp"}))
        self.assertEqual(self.run_(I3, "--add-collection", "自然图像/tmp").code, 0)
        self.assertEqual(self.colls(I3), ["COLLDDDD"])

    def test_change_lists_name_items_by_key_or_cite(self):
        r = self.run_(self.file([{"cite": "zhu2017unpaired", "remove_collection": CA},
                                 {"cite": "karras2019style", "tags": ["GAN"]},
                                 {"key": I3, "add_collection": CB}]), "-n")
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual(r.lines[0], {"key": I1, "cite": "zhu2017unpaired", "code": "ok", "title": "CycleGAN",
                                      "collection": {"from": [{"key": CA, "path": "CC作业"}, {"key": CB, "path": "自然图像"},
                                                              {"key": CC, "path": "tmp"}],
                                                     "to": [{"key": CB, "path": "自然图像"}, {"key": CC, "path": "tmp"}]},
                                      "version": 10, "dry_run": True}, "the preview names collections as the write does")
        self.assertEqual([(line["key"], line.get("cite")) for line in r.lines[1:]], [(I2, "karras2019style"), (I3, None)])
        self.assertEqual(self.zot.writes(), [])

    # ---- invalid_changes, item_line: nothing asked of Zotero, exit 2 ------------------------------------------------

    def test_malformed_change_lists(self):
        for entries in ([{"key": I1, "cite": "zhu2017unpaired", "add_collection": CB}],     # both
                        [{"add_collection": CB}],                                          # neither
                        [{"cite": "", "add_collection": CB}],
                        [{"key": "short", "add_collection": CB}],
                        [{"key": I1}],                                                     # no change
                        [{"key": I1, "collection": CB, "remove_collection": CA}],          # replace and edit
                        [{"key": I1, "tags": [], "add_tags": ["x"]}],
                        [{"key": I1, "remove_collection": {"x": 1}}],
                        [{"key": I1, "add_collection": CA, "remove_collection": [CA]}],
                        [{"key": I1, "tags": [{"tag": "x", "type": 2}]}],
                        [{"key": I1, "tags": "GAN"}],
                        [{"key": I1, "tags": ["x"], "remove_tags": ["GAN"]}],
                        [{"key": I1, "add_tags": ["GAN"], "remove_tags": "GAN"}],
                        [{"key": I1, "remove_tags": [{"tag": "GAN"}]}],
                        [{"key": I1, "remove_tags": ["GAN", " "]}],
                        ["ITEM0001"],
                        [[{"key": I1, "tags": []}]],                                       # a line that is not an object
                        "[{"):                                                             # not JSON
            r = self.run_(self.file(entries))
            self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "invalid_changes"), entries)
            self.assertTrue(r.last["detail"] and r.last["hint"], entries)
        r = self.run_(self.tmp / "missing.jsonl")
        self.assertEqual((r.code, r.last["code"]), (2, "invalid_changes"))
        r = self.run_(self.file([]))
        self.assertEqual((r.code, r.out, r.err), (0, "", ""), "an empty change list is nothing to change")
        r = self.run_("-", stdin=json.dumps({"key": I1, "itemType": "journalArticle", "title": "CycleGAN"}))
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "item_line"), "an item line is not a change")
        self.assertEqual(self.zot.requests, [])

    def test_detail_names_every_bad_entry(self):
        r = self.run_(self.file([{"key": I1, "add_collection": CB},
                                 {"cite": "x", "collection": 5},
                                 {"key": I2, "tags": [{"tag": "t", "type": 3}]}]))
        detail = r.last["detail"]
        self.assertEqual(len(detail), 2, detail)
        self.assertRegex(detail[0], r"changes\.jsonl line 2 \(cite x\): collection")
        self.assertRegex(detail[1], rf"changes\.jsonl line 3 \(key {I2}\): tags")

    def test_two_entries_for_one_item(self):
        for entries in ([{"cite": "zhu2017unpaired", "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}],
                        [{"key": I1, "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}]):
            r = self.run_(self.file(entries))
            self.assertEqual((r.code, r.last["code"]), (2, "invalid_changes"), entries)
            self.assertIn(I1, r.last["detail"][0])
        r = self.run_(self.file([{"key": I2, "add_tags": ["x"]}, {"cite": "karras2019style", "add_tags": ["x"]}]))
        self.assertEqual((r.code, len(r.lines)), (0, 1), "the same change twice is one")
        self.assertEqual(self.zot.writes()[0][0], "POST")

    def test_malformed_options(self):
        tags = self.file(["x"], "tags.json")
        for argv in (("--set-collection", CA, "--remove-collection", CB),
                     ("--add-collection", CA, "--remove-collection", CA),
                     ("--set-tags-file", self.tmp / "missing.json"),
                     ("--set-tags-file", self.file("[1, ", "broken.json")),
                     ("--add-tags-file", self.file([{"tag": "x", "type": 2}], "type2.json")),
                     ("--set-tags-file", tags, "--add-tags-file", tags),
                     ("--add-tag", "x", "--remove-tag", "x"),
                     ()):                                           # no option: I1 read as a change list file
            r = self.run_(I1, *argv)
            self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "invalid_changes"), argv)
        self.assertEqual(self.zot.requests, [])
        r = self.run_("--add-collection", CB)
        self.assertEqual((r.code, r.last["code"]), (2, "usage"))

    # ---- the write and Zotero's reply ------------------------------------------------------------------------------

    def test_a_stale_version_is_read_again_and_planned_again_once(self):
        changes = self.file([{"key": I2, "add_tags": ["x"]}, {"key": I3, "add_tags": ["x"]}])
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(tags=[{"tag": "y", "type": 0}])
        r = self.run_(changes)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual([(line["code"], line.get("retried")) for line in r.lines], [("ok", True), ("ok", None)])
        self.assertEqual({t["tag"] for t in self.zot.data(I2)["tags"]}, {"x", "y"}, "planned on the edited item")
        self.assertEqual(len(self.zot.requested("POST")), 2)

    def test_a_version_that_keeps_changing_fails_its_item_only(self):
        changes = self.file([{"key": I2, "add_tags": ["x"]}])
        self.zot.bump_before_write = 2
        r = self.run_(changes)
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["status"], r.lines[0]["retried"]), ("version_conflict", 412, True))
        self.assertIn("hint", r.lines[0])
        r = self.run_(changes)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)

    def test_write_denied(self):
        self.zot.write_status = (403, "Write access denied")
        r = self.run_(I2, I3, "--add-collection", CB)
        self.assertEqual(r.code, 1)
        self.assertEqual([(line["code"], line["detail"]) for line in r.lines], [("write_denied", "Write access denied")] * 2)
        self.assertTrue(all("hint" in line for line in r.lines))

    def test_readback_mismatch(self):
        self.zot.on_write = lambda it: it["data"].update(tags=[])
        r = self.run_(I2, "--add-tag", "x")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["now"]), (1, "readback_mismatch", {"tags": []}))
        self.assertEqual(r.lines[0]["version"], self.zot.items[I2]["version"], "the version Zotero now has")
        self.assertIn("hint", r.lines[0])

    def test_a_reply_without_the_data_is_checked_by_reading_the_item(self):
        self.zot.thin_post_reply = True
        r = self.run_(I2, "--add-collection", CB)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        self.assertEqual(r.lines[0]["version"], self.zot.items[I2]["version"])

    def test_cannot_check(self):
        argv = (I1, "zhu2017unpaired", "--add-collection", CB)
        r = self.run_(*argv, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines, r.last["code"]),
                         (2, [{"item": I1, "code": "not_run"}, {"item": "zhu2017unpaired", "code": "not_run"}],
                          "zotero_unreachable"))
        r = self.run_(*argv, "-n", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "skipped"), "a dry run writes nothing, so it needs no key")
        r = self.run_(*argv, config=config_file(key=None))
        self.assertEqual((r.code, r.last["code"]), (2, "no_key"))
        self.zot.disabled = True
        r = self.run_(*argv)
        self.assertEqual((r.code, r.last["code"]), (2, "local_api_disabled"))

    def test_through_the_entry(self):
        r = smoke("tag", self.file([{"cite": "zhu2017unpaired", "add_collection": "new"}]), "-n",
                  "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["code"], r.lines[0]["dry_run"]), (I1, "ok", True))


if __name__ == "__main__":
    unittest.main()
