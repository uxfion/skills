# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Tests for scripts/note.py against the fake Zotero: take notes out as Markdown files, put them back (unchanged,
changed, new, conflicting), list them."""
import json
import tempfile
import unittest
from pathlib import Path

from fake_zotero import FakeZotero
from helpers import call, closed_port, config_file, load, smoke

note = load("note")
NOTE_HTML = '<div data-schema-version="9"><h1>论文笔记</h1>\n<ul>\n<li>\nQ1 问题 [已答]\n</li>\n</ul>\n</div>'
URI = "http://zotero.org/users/0/items/"


class Note(unittest.TestCase):
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
        z.add_collection("COLL0001", "主题笔记")
        z.add_item("ITEM0001", version=10, itemType="journalArticle", title="Paper one", citationKey="one2020paper")
        z.add_item("ITEM0002", version=11, itemType="journalArticle", title="Paper two", citationKey="two2021paper",
                   relations={"dc:relation": [URI + "NOTE0003"]})
        z.add_item("ATTA0001", version=12, itemType="attachment", parentItem="ITEM0001", title="PDF")
        z.add_item("NOTE0001", version=13, itemType="note", parentItem="ITEM0001", note=NOTE_HTML)
        z.add_item("NOTE0002", version=14, itemType="note", parentItem="ITEM0001", note="<p>Reading log</p><p>x</p>")
        z.add_item("NOTE0003", version=15, itemType="note", note="<h1>主题：扩散</h1><p>见两篇</p>",
                   collections=["COLL0001"], relations={"dc:relation": [URI + "ITEM0002"]})
        self.dir = Path(tempfile.mkdtemp(prefix="note-"))

    def run_(self, *argv, stdin="", config=None, base_url=None):
        return call(note, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config, stdin=stdin)

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def posts(self):
        return [json.loads(body)[0] for _, _, _, body in self.zot.requested("POST")]

    # ---- take -------------------------------------------------------------------------------------------------

    def test_take_one_note_to_stdout(self):
        r = self.run_("take", "--cite", "one2020paper", "--title", "论文笔记")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.out, "---\nkey: NOTE0001\nversion: 13\nparent: one2020paper\nschema: 9\n---\n"
                                "# 论文笔记\n\n- Q1 问题 [已答]\n")
        self.assertEqual(self.zot.writes(), [])

    def test_take_several_needs_a_directory(self):
        r = self.run_("take", "--key", "ITEM0001")
        self.assertEqual(r.code, 2)
        self.assertIn("NOTE0001  论文笔记", r.err)
        self.assertIn("NOTE0002  Reading log", r.err)
        r = self.run_("take", "--key", "ITEM0001", "-o", f"{self.dir}/notes/")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(x["key"], x["title"], Path(x["file"]).name) for x in r.lines[:2]],
                         [("NOTE0001", "论文笔记", "one2020paper.NOTE0001.note.md"),
                          ("NOTE0002", "Reading log", "one2020paper.NOTE0002.note.md")])
        self.assertTrue((self.dir / "notes/one2020paper.NOTE0002.note.md").read_text(encoding="utf-8")
                        .endswith("---\nReading log\n\nx\n"))

    def test_take_writes_over_the_same_note_only(self):
        out = self.dir / "n.md"
        self.assertEqual(self.run_("take", "--note", "NOTE0002", "-o", out).code, 0)
        self.assertEqual(self.run_("take", "--note", "NOTE0002", "-o", out).code, 0, "the same note: written over")
        r = self.run_("take", "--note", "NOTE0001", "-o", out)
        self.assertEqual(r.code, 2)
        self.assertIn("holds another note (NOTE0002)", r.err)

    def test_take_a_standalone_note(self):
        r = self.run_("take", "--note", "NOTE0003")
        self.assertEqual(r.out, "---\nkey: NOTE0003\nversion: 15\ncollections: COLL0001\nrelated: two2021paper\n---\n"
                                "# 主题：扩散\n\n见两篇\n")

    def test_take_finds_nothing(self):
        r = self.run_("take", "--cite", "one2020paper", "--title", "nope")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_notes"))
        r = self.run_("take", "--note", "ITEM0001")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "not_a_note"))
        r = self.run_("take", "--key", "ATTA0001")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "not_a_parent"))

    # ---- put --------------------------------------------------------------------------------------------------

    def taken(self, key="NOTE0001"):
        path = self.dir / f"{key}.note.md"
        self.assertEqual(self.run_("take", "--note", key, "-o", path).code, 0)
        return path

    def test_put_unchanged_writes_nothing(self):
        r = self.run_("put", self.taken())
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"]), (0, "skipped", "unchanged"), r)
        self.assertEqual(self.zot.writes(), [])

    def test_put_a_change_with_its_version(self):
        path = self.taken()
        path.write_text(path.read_text(encoding="utf-8") + "- Q2 新问题 [待答]\n", encoding="utf-8")
        r = self.run_("put", path, "-i")
        self.assertEqual((r.code, r.lines[0]["action"], r.lines[0]["key"]), (0, "updated", "NOTE0001"), r)
        [(key, body)] = self.patches()
        self.assertEqual(key, "NOTE0001")
        self.assertEqual(body["note"], '<div data-schema-version="9"><h1>论文笔记</h1>\n<ul>\n<li>Q1 问题 [已答]</li>\n'
                                       "<li>Q2 新问题 [待答]</li>\n</ul>\n</div>")
        self.assertEqual(self.zot.data("NOTE0001")["note"], body["note"])
        version = self.zot.items["NOTE0001"]["version"]
        self.assertIn(f"version: {version}\n", path.read_text(encoding="utf-8"), "-i writes the new version back")
        self.assertEqual(self.run_("put", path).lines[0]["reason"], "unchanged", "the next put follows on")

    def test_put_refuses_a_note_changed_since_the_take(self):
        path = self.taken()
        self.zot.touch(self.zot.items["NOTE0001"])
        path.write_text(path.read_text(encoding="utf-8") + "more\n", encoding="utf-8")
        r = self.run_("put", path)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["taken"]), (1, "version_conflict", "13"))
        self.assertEqual(self.zot.writes(), [])
        self.zot.bump_before_write = 1                     # changed between the read and the write
        r = self.run_("put", self.taken())
        self.assertEqual(r.lines[0]["reason"], "unchanged")
        path = self.taken()
        path.write_text(path.read_text(encoding="utf-8") + "more\n", encoding="utf-8")
        self.zot.bump_before_write = 1
        r = self.run_("put", path)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "version_conflict"))

    def test_put_a_new_child_note(self):
        path = self.dir / "new.note.md"
        path.write_text("---\nparent: one2020paper\n---\n# 新笔记\n\n**粗** $x$\n", encoding="utf-8")
        r = self.run_("put", path, "-i")
        self.assertEqual((r.code, r.lines[0]["action"]), (0, "created"), r)
        [obj] = self.posts()
        self.assertEqual(obj, {"itemType": "note", "parentItem": "ITEM0001",
                               "note": '<h1>新笔记</h1>\n<p><strong>粗</strong> <span class="math">$x$</span></p>\n'})
        key = r.lines[0]["key"]
        self.assertTrue(path.read_text(encoding="utf-8").startswith(f"---\nkey: {key}\nversion: "))

    def test_put_a_new_standalone_note_related_both_ways(self):
        r = self.run_("put", stdin="---\ncollections: COLL0001\nrelated: one2020paper,ITEM0002\n---\n# 主题\n")
        self.assertEqual((r.code, r.lines[0]["action"]), (0, "created"), r)
        key = r.lines[0]["key"]
        [obj] = self.posts()
        self.assertEqual((obj["collections"], obj["relations"]),
                         (["COLL0001"], {"dc:relation": [URI + "ITEM0001", URI + "ITEM0002"]}))
        self.assertEqual(self.zot.data("ITEM0001")["relations"], {"dc:relation": [URI + key]})
        self.assertEqual(self.zot.data("ITEM0002")["relations"]["dc:relation"], [URI + "NOTE0003", URI + key])

    def test_put_moves_a_standalone_note_between_papers(self):
        path = self.taken("NOTE0003")
        path.write_text(path.read_text(encoding="utf-8").replace("related: two2021paper", "related: one2020paper"),
                        encoding="utf-8")
        r = self.run_("put", path)
        self.assertEqual((r.code, r.lines[0]["action"]), (0, "updated"), r)
        self.assertEqual(self.zot.data("NOTE0003")["relations"], {"dc:relation": [URI + "ITEM0001"]})
        self.assertEqual(self.zot.data("ITEM0001")["relations"], {"dc:relation": [URI + "NOTE0003"]})
        self.assertEqual(self.zot.data("ITEM0002").get("relations"), {})

    def test_put_dry_run_and_bad_input(self):
        r = self.run_("put", "--dry-run", stdin="---\nparent: one2020paper\n---\nx\n")
        self.assertEqual((r.code, r.lines[0]["action"], r.lines[0]["note"]), (0, "created", "<p>x</p>\n"))
        self.assertEqual(self.zot.writes(), [])
        cases = {"---\nkey NOTE0001\n---\nx\n": "bad_front_matter", "---\nkey: NOTE0001\n---\nx\n": "no_version",
                 "---\nkey: ZZZZZZZZ\nversion: 1\n---\nx\n": "not_found", "---\nparent: nobody\n---\nx\n": "cite_not_found",
                 "---\ncollections: NOPE0000\n---\nx\n": "collection_not_found"}
        for text, code in cases.items():
            with self.subTest(code=code):
                r = self.run_("put", stdin=text)
                self.assertEqual((r.code, r.lines[0]["code"]), (1, code))
        self.assertEqual(self.run_("put", "-i", stdin="x").code, 2)
        self.assertEqual(self.zot.writes(), [])

    # ---- list -------------------------------------------------------------------------------------------------

    def test_list(self):
        r = self.run_("list", "--cite", "one2020paper")
        self.assertEqual([(x["key"], x["parent"], x["title"]) for x in r.lines[:-1]],
                         [("NOTE0001", "one2020paper", "论文笔记"), ("NOTE0002", "one2020paper", "Reading log")])
        r = self.run_("list", "--collection", "COLL0001")
        self.assertEqual([(x["key"], x["title"], x["collections"]) for x in r.lines[:-1]],
                         [("NOTE0003", "主题：扩散", ["COLL0001"])])
        r = self.run_("list", "--q", "两篇")
        self.assertEqual([x["key"] for x in r.lines[:-1]], ["NOTE0003"])
        self.assertEqual([q.get("qmode") for _, _, q, _ in self.zot.requested("GET") if q.get("q") == "两篇"], ["everything"])

    # ---- Zotero not there -------------------------------------------------------------------------------------

    def test_cannot_check(self):
        r = self.run_("put", stdin="x", base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("put", stdin="x", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))

    def test_smoke(self):
        r = smoke("note", "take", "--note", "NOTE0002", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.out), (0, "---\nkey: NOTE0002\nversion: 14\nparent: one2020paper\n---\nReading log\n\nx\n"), r)


if __name__ == "__main__":
    unittest.main()
