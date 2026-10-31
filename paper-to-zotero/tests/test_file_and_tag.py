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

    def run_(self, *argv, base_url=None, config=None):
        return call(file_and_tag, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def file(self, content, name="changes.jsonl"):
        """A batch (name *.jsonl: a JSON line per entry), a tag list file (*.json), or the text given."""
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

    # ---- one item, or several with the same change: the batch way --------------------------------------------

    def test_remove_collection_keeps_the_others(self):
        r = self.run_("--key", I1, "--remove-collection", CA)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0], {"key": I1, "code": "ok", "title": "CycleGAN",
                                      "collection": {"from": [CA, CB, CC], "to": [CB, CC]}, "version": r.lines[0]["version"]})
        self.assertGreater(r.lines[0]["version"], 10)
        self.assertEqual(r.lines[-1], {"summary": {"total": 1, "ok": 1, "skipped": 0, "failed": 0}})
        self.assertEqual(self.colls(I1), [CB, CC])
        self.assertEqual(self.posts(), [[{"key": I1, "version": 10, "collections": [CB, CC]}]])
        self.assertEqual(self.zot.requested("PATCH"), [])
        self.assertEqual(self.zot.requested("GET", f"{LIB}/collections"), [], "a removed collection is not looked up")

    def test_add_and_remove_combine_and_rerun_is_a_no_op(self):
        argv = ("--cite", "zhu2017unpaired", "--add-collection", CX, "--remove-collection", CA, "--remove-collection", CC)
        r = self.run_(*argv)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["cite"]), (I1, "zhu2017unpaired"))
        self.assertEqual(self.colls(I1), [CB, CX])
        r = self.run_(*argv)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "unchanged"))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(r.lines[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        self.assertEqual(len(self.posts()), 1)

    def test_several_items_take_the_same_change_in_one_post(self):
        tags = self.file(["diffusion"], "tags.json")
        r = self.run_("--key", I2, f"{I3},{I1}", "--cite", "zhu2017unpaired", "--add-tags-file", tags,
                      "--add-collection", CX)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([line["key"] for line in r.lines[:-1]], [I2, I3, I1], "the cite naming I1 again is handled once")
        self.assertEqual(r.lines[-1]["summary"]["total"], 3)
        [objects] = self.posts()
        self.assertEqual([o["key"] for o in objects], [I2, I3, I1])
        self.assertEqual(self.tags(I1), [{"tag": "GAN", "type": 0}, {"tag": "diffusion", "type": 0}])
        self.assertEqual(self.colls(I3), [CX])

    def test_remove_a_collection_the_item_is_not_in(self):
        r = self.run_("--key", I2, "--remove-collection", "NOSUCH01", "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "unchanged"))
        self.assertEqual(r.lines[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0, "dry_run": True})
        self.assertEqual(self.zot.writes(), [])

    def test_absolute_and_add_semantics(self):
        tags = self.file(["diffusion", {"tag": "auto", "type": 1}], "tags.json")
        r = self.run_("--key", I3, "--collection", CB, "--tags-file", tags)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["tags_added"], [{"tag": "diffusion", "type": 0}, {"tag": "auto", "type": 1}])
        self.assertNotIn("tags_removed", r.lines[0])
        self.assertEqual(self.colls(I3), [CB])
        self.assertEqual(self.tags(I3), [{"tag": "diffusion", "type": 0}, {"tag": "auto", "type": 1}])
        self.assertEqual(self.run_("--key", I3, "--add-collection", CC).code, 0)
        self.assertEqual(self.colls(I3), [CB, CC])
        self.assertEqual(self.run_("--key", I3, "--collection", "none").code, 0)
        self.assertEqual(self.colls(I3), [])
        r = self.run_("--batch", self.file([{"key": I2, "collection": None, "add_tags": ["x"]},
                                            {"key": I3, "collection": [CA, CB]}]))
        self.assertEqual(r.code, 0, r)
        self.assertEqual((self.colls(I2), self.tags(I2)), ([], [{"tag": "x", "type": 0}]))
        self.assertEqual(self.colls(I3), [CA, CB])

    def test_tags_are_the_complete_set_and_a_repeated_tag_keeps_the_last(self):
        r = self.run_("--batch", self.file([{"key": I1, "tags": ["CVPR", {"tag": "CVPR", "type": 1}]},
                                            {"key": I2, "title": "StyleGAN", "add_tags": ["x"]}]))
        self.assertEqual(r.code, 0, r)
        self.assertIn("'CVPR' given twice", r.err)
        self.assertIn("'title'", r.err, "an unknown field is named on stderr, not refused")
        self.assertEqual(self.tags(I1), [{"tag": "CVPR", "type": 1}])
        self.assertEqual((r.lines[0]["tags_added"], r.lines[0]["tags_removed"]),
                         ([{"tag": "CVPR", "type": 1}], [{"tag": "GAN", "type": 0}]))

    def test_remove_tags_by_name_keeps_the_others(self):
        self.zot.data(I1)["tags"] = [{"tag": "GAN", "type": 0}, {"tag": "Deep learning, theory", "type": 1},
                                     {"tag": "to read", "type": 0}]
        r = self.run_("--key", I1, I2, "--remove-tags", "Deep learning, theory", "--remove-tags", "to read", "absent")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["tags_removed"], [{"tag": "Deep learning, theory", "type": 1}, {"tag": "to read", "type": 0}],
                         "each value is one name, its comma kept; the type does not matter")
        self.assertNotIn("tags_added", r.lines[0])
        self.assertEqual(self.tags(I1), [{"tag": "GAN", "type": 0}])
        self.assertEqual((r.lines[1]["key"], r.lines[1]["code"], r.lines[1]["reason"]), (I2, "skipped", "unchanged"))
        self.assertEqual(self.posts(), [[{"key": I1, "version": 10, "tags": [{"tag": "GAN", "type": 0}]}]])

        r = self.run_("--batch", self.file([{"cite": "zhu2017unpaired", "add_tags": ["CVPR"], "remove_tags": "GAN"},
                                            {"key": I2, "remove_tags": [], "add_collection": CX}]))
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["tags_added"], r.lines[0]["tags_removed"]),
                         ([{"tag": "CVPR", "type": 0}], [{"tag": "GAN", "type": 0}]))
        self.assertEqual((self.tags(I1), self.colls(I2), self.tags(I2)), ([{"tag": "CVPR", "type": 0}], [CA, CX], []))

        self.zot.on_write = lambda it: it["data"].update(tags=[{"tag": "CVPR", "type": 0}])
        r = self.run_("--key", I1, "--remove-tags", "CVPR")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["now"]), (1, "readback_mismatch", {"tags": [{"tag": "CVPR", "type": 0}]}))

    # ---- checks before anything is written -----------------------------------------------------------------------

    def test_not_a_parent_and_not_found_write_nothing(self):
        r = self.run_("--key", ATT, I2, "--remove-collection", CA)
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["code"], r.lines[0]["parent"]), (ATT, "not_a_parent", I1))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(r.lines[1], {"key": I2, "code": "not_run"})
        r = self.run_("--key", "NOPE1234", I2, "--add-collection", CB)
        self.assertEqual([line["code"] for line in r.lines[:2]], ["not_found", "not_run"])
        self.assertEqual(r.lines[-1]["summary"], {"total": 2, "ok": 0, "skipped": 0, "failed": 2})
        self.assertEqual(self.zot.writes(), [])
        r = self.run_("--key", ATT, "--add-tags-file", self.file(["read"], "tags.json"))
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.tags(ATT), [{"tag": "read", "type": 0}], "tags are fine on an attachment")

    def test_collection_not_found_or_in_the_trash(self):
        r = self.run_("--key", I3, I2, "--add-collection", TRASHC, "NOSUCH01", CB)
        self.assertEqual(r.code, 1)
        self.assertEqual(r.lines[0]["collections"], [TRASHC, "NOSUCH01"])
        self.assertEqual([line["code"] for line in r.lines[:2]], ["collection_not_found"] * 2)
        self.assertEqual(self.zot.writes(), [])
        self.assertEqual(len(self.zot.requested("GET", f"{LIB}/collections")), 1, "the tree is read once")

    def test_cite_failures_write_nothing(self):
        r = self.run_("--batch", self.file([{"key": I2, "add_collection": CB},
                                            {"cite": "nobody2000", "add_collection": CB},
                                            {"cite": "dupkey", "add_collection": CB}]))
        self.assertEqual(r.code, 1)
        out = r.lines
        self.assertEqual(out[0], {"key": I2, "code": "not_run"})
        self.assertEqual((out[1]["cite"], out[1]["code"]), ("nobody2000", "cite_not_found"))
        self.assertEqual((out[2]["code"], out[2]["keys"]), ("cite_ambiguous", [DUP1, DUP2]))
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 0, "skipped": 0, "failed": 3})
        r = self.run_("--cite", "dupkey", "--add-collection", CB)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "cite_ambiguous"))
        self.assertEqual(self.zot.writes(), [])

    def test_batch_cites_by_search_or_one_fallback_scan(self):
        r = self.run_("--batch", self.file([{"cite": "zhu2017unpaired", "remove_collection": CA},
                                            {"cite": "karras2019style", "tags": ["GAN"]},
                                            {"key": I3, "add_collection": CB}]))
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(line["key"], line.get("cite"), line["code"]) for line in r.lines[:3]],
                         [(I1, "zhu2017unpaired", "ok"), (I2, "karras2019style", "ok"), (I3, None, "ok")])
        self.assertEqual(self.colls(I1), [CB, CC])
        self.assertEqual(self.tags(I2), [{"tag": "GAN", "type": 0}])
        self.assertEqual(self.zot.requested("GET", f"{LIB}/items/top"), [], "the search found every cite")

        self.setUp()
        self.zot.search_sees_citekey = False
        r = self.run_("--batch", self.file([{"cite": "zhu2017unpaired", "remove_collection": CA},
                                            {"cite": "ho2020denoising", "add_collection": CB}]), "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0], {"key": I1, "cite": "zhu2017unpaired", "code": "ok", "title": "CycleGAN",
                                      "collection": {"from": [CA, CB, CC], "to": [CB, CC]}, "version": 10, "dry_run": True})
        self.assertEqual((r.lines[1]["key"], r.lines[1]["collection"]), (I3, {"from": [], "to": [CB]}))
        self.assertEqual(r.lines[-1]["summary"], {"total": 2, "ok": 2, "skipped": 0, "failed": 0, "dry_run": True})
        self.assertEqual(len(self.zot.requested("GET", f"{LIB}/items/top")), 1, "one scan for every missed cite")
        self.assertEqual(self.zot.writes(), [])

    # ---- invalid_changes: one line, nothing asked of Zotero --------------------------------------------------------

    def test_malformed_batch_entries(self):
        for entries in ([{"key": I1, "cite": "zhu2017unpaired", "add_collection": CB}],     # both
                        [{"add_collection": CB}],                                          # neither
                        [{"cite": "", "add_collection": CB}],
                        [{"key": "short", "add_collection": CB}],
                        [{"key": I1}],                                                     # no change
                        [{"key": I1, "collection": CB, "remove_collection": CA}],          # replace and edit
                        [{"key": I1, "tags": [], "add_tags": ["x"]}],
                        [{"key": I1, "remove_collection": {"x": 1}}],
                        [{"key": I1, "add_collection": CA, "remove_collection": [CA]}],
                        [{"key": I1, "collection": "bad"}],
                        [{"key": I1, "tags": [{"tag": "x", "type": 2}]}],
                        [{"key": I1, "tags": "GAN"}],
                        [{"key": I1, "tags": ["x"], "remove_tags": ["GAN"]}],
                        [{"key": I1, "add_tags": ["GAN"], "remove_tags": "GAN"}],
                        [{"key": I1, "remove_tags": [{"tag": "GAN"}]}],
                        [{"key": I1, "remove_tags": ["GAN", " "]}],
                        ["ITEM0001"],
                        [],
                        [[{"key": I1, "tags": []}]],                                       # a line that is not an object
                        "[{"):                                                             # not JSON
            r = self.run_("--batch", self.file(entries))
            self.assertEqual((r.code, r.lines[0]["code"], len(r.lines)), (1, "invalid_changes", 1), entries)
            self.assertTrue(r.lines[0]["detail"] and r.lines[0]["hint"], entries)
        r = self.run_("--batch", self.tmp / "missing.json")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "invalid_changes"))
        self.assertEqual(self.zot.requests, [])

    def test_detail_names_every_bad_entry(self):
        r = self.run_("--batch", self.file([{"key": I1, "add_collection": CB},
                                            {"cite": "x", "collection": "bad"},
                                            {"key": I2, "tags": [{"tag": "t", "type": 3}]}]))
        detail = r.lines[0]["detail"]
        self.assertEqual(len(detail), 2, detail)
        self.assertTrue(detail[0].startswith("line 2 (cite x): collection"), detail)
        self.assertTrue(detail[1].startswith(f"line 3 (key {I2}): tags"), detail)

    def test_two_entries_for_one_item(self):
        for entries in ([{"cite": "zhu2017unpaired", "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}],
                        [{"key": I1, "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}]):
            r = self.run_("--batch", self.file(entries))
            self.assertEqual((r.code, r.lines[0]["code"]), (1, "invalid_changes"), entries)
            self.assertIn(I1, r.lines[0]["detail"][0])
        r = self.run_("--batch", self.file([{"key": I2, "add_tags": ["x"]}, {"cite": "karras2019style", "add_tags": ["x"]}]))
        self.assertEqual((r.code, r.lines[-1]["summary"]["total"]), (0, 1), "the same change twice is one")
        self.assertEqual(self.zot.writes()[0][0], "POST")

    def test_malformed_flags(self):
        tags = self.file(["x"], "tags.json")
        for argv in (("--collection", CA, "--remove-collection", CB),
                     ("--add-collection", CA, "--remove-collection", CA),
                     ("--remove-collection", "bad"),
                     ("--collection", "bad"),
                     ("--tags-file", self.tmp / "missing.json"),
                     ("--tags-file", self.file("[1, ", "broken.json")),
                     ("--add-tags-file", self.file([{"tag": "x", "type": 2}], "type2.json")),
                     ("--tags-file", tags, "--add-tags-file", tags),
                     ()):
            r = self.run_("--key", I1, *argv)
            self.assertEqual((r.code, r.lines[0]["code"], len(r.lines)), (1, "invalid_changes", 1), argv)
        self.assertEqual(self.zot.requests, [])

    def test_usage_errors(self):
        batch = self.file([{"key": I1, "add_collection": CB}])
        self.assertEqual(self.run_("--batch", batch, "--remove-collection", CB).code, 2)
        self.assertEqual(self.run_("--batch", batch, "--remove-tags", "GAN").code, 2)
        self.assertEqual(self.run_("--batch", batch, "--key", I1).code, 2)
        self.assertEqual(self.run_("--add-collection", CB).code, 2)
        self.assertEqual(self.run_("--key", "short", "--add-collection", CB).code, 2)

    # ---- the write and Zotero's reply ------------------------------------------------------------------------------

    def test_a_stale_version_is_read_again_and_planned_again_once(self):
        changes = self.file([{"key": I2, "add_tags": ["x"]}, {"key": I3, "add_tags": ["x"]}])
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(tags=[{"tag": "y", "type": 0}])
        r = self.run_("--batch", changes)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(line["code"], line.get("retried")) for line in r.lines[:2]], [("ok", True), ("ok", None)])
        self.assertEqual({t["tag"] for t in self.zot.data(I2)["tags"]}, {"x", "y"}, "planned on the edited item")
        self.assertEqual(len(self.zot.requested("POST")), 2)

    def test_a_version_that_keeps_changing_fails_its_item_only(self):
        changes = self.file([{"key": I2, "add_tags": ["x"]}])
        self.zot.bump_before_write = 2
        r = self.run_("--batch", changes)
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["status"], r.lines[0]["retried"]), ("version_conflict", 412, True))
        self.assertIn("hint", r.lines[0])
        r = self.run_("--batch", changes)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)

    def test_write_denied(self):
        self.zot.write_status = (403, "Write access denied")
        r = self.run_("--key", I2, I3, "--add-collection", CB)
        self.assertEqual(r.code, 1)
        self.assertEqual([(line["code"], line["detail"]) for line in r.lines[:2]], [("write_denied", "Write access denied")] * 2)
        self.assertTrue(all("hint" in line for line in r.lines[:2]))

    def test_readback_mismatch(self):
        self.zot.on_write = lambda it: it["data"].update(tags=[])
        r = self.run_("--key", I2, "--add-tags-file", self.file(["x"], "tags.json"))
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["now"]), (1, "readback_mismatch", {"tags": []}))
        self.assertEqual(r.lines[0]["version"], self.zot.items[I2]["version"], "the version Zotero now has")
        self.assertIn("hint", r.lines[0])

    def test_a_reply_without_the_data_is_checked_by_reading_the_item(self):
        self.zot.thin_post_reply = True
        r = self.run_("--key", I2, "--add-collection", CB)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        self.assertEqual(r.lines[0]["version"], self.zot.items[I2]["version"])
        self.assertEqual(len(self.zot.requested("GET", f"{LIB}/items/{I2}")), 1)

    def test_cannot_check(self):
        argv = ("--key", I1, "--add-collection", CB)
        r = self.run_(*argv, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_(*argv, "--dry-run", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "skipped"), "a dry run writes nothing, so it needs no key")
        r = self.run_(*argv, config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        self.zot.disabled = True
        r = self.run_(*argv)
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "local_api_disabled"))

    def test_smoke(self):
        r = smoke("file_and_tag", "--batch", self.file([{"cite": "zhu2017unpaired", "add_collection": CX}]), "--dry-run",
                  "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["key"], r.lines[0]["code"]), (I1, "ok"))
        self.assertEqual(r.lines[-1]["summary"]["dry_run"], True)


if __name__ == "__main__":
    unittest.main()
