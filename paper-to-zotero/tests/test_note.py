# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/note.py: the Markdown conversion, and creating, updating or leaving a note against the fake Zotero."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero

note = load("note")
OLD_HTML = "<p>p2z: old</p>\n<p>stale</p>"


class Markdown(unittest.TestCase):
    def test_blocks_and_inline(self):
        md = "# Title\n\nFirst **bold** and *em* with [a link](https://x.y/?a=1&b=2).\nsecond line\n\n- one\n- two <b>\n  continued\n\n## Sub\npara"
        self.assertEqual(note.to_html(md),
                         "<h1>Title</h1>\n"
                         "<p>First <strong>bold</strong> and <em>em</em> with <a href=\"https://x.y/?a=1&amp;b=2\">a link</a>.\nsecond line</p>\n"
                         "<ul>\n<li>one</li>\n<li>two &lt;b&gt; continued</li>\n</ul>\n"
                         "<h2>Sub</h2>\n<p>para</p>")

    def test_everything_else_is_escaped(self):
        self.assertEqual(note.to_html("a & b < c > d \"q\""), "<p>a &amp; b &lt; c &gt; d \"q\"</p>")
        self.assertEqual(note.to_html("  \n\n"), "")

    def test_list_after_paragraph_and_star_bullets(self):
        self.assertEqual(note.to_html("p\n* x\n* y"), "<p>p</p>\n<ul>\n<li>x</li>\n<li>y</li>\n</ul>")

    def test_marker_detection(self):
        f = note.marker_of
        self.assertEqual(f("<p>p2z: v</p>\n<p>x</p>"), "p2z: v")
        self.assertEqual(f('<div data-schema-version="9">\n<p><em>p2z: v</em></p><p>x</p></div>'), "p2z: v")
        self.assertEqual(f("<h1>p2z: v</h1>"), "p2z: v")
        self.assertEqual(f("<p>a &amp; b</p>"), "a & b")
        self.assertIsNone(f(""))
        self.assertIsNone(f("<ul><li>x</li></ul>"))


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
        z.add_item("ITEM0001", version=10, itemType="journalArticle", title="Paper one", citationKey="one2020paper")
        z.add_item("ITEM0002", version=11, itemType="journalArticle", title="Paper two", citationKey="dup2021key")
        z.add_item("ITEM0003", version=12, itemType="journalArticle", title="Paper three", citationKey="dup2021key")
        z.add_item("ATTA0001", version=13, itemType="attachment", parentItem="ITEM0001", title="PDF")
        z.add_item("NOTE0001", version=14, itemType="note", parentItem="ITEM0001", note=OLD_HTML)
        z.add_item("NOTE0002", version=15, itemType="note", parentItem="ITEM0001", note="<p>other</p>")

    def run_(self, *argv, base_url=None, config=None):
        return call(note, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def posts(self):
        return [json.loads(body) for _, _, _, body in self.zot.requested("POST")]

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def test_created_with_marker(self):
        r = self.run_("--key", "ITEM0001", "--text", "# Read\\n- a\\n- b", "--marker", "p2z: reading")
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual({k: line[k] for k in ("key", "code", "action", "marker", "retried")},
                         {"key": "ITEM0001", "code": "ok", "action": "created", "marker": "p2z: reading", "retried": False})
        html = "<p>p2z: reading</p>\n<h1>Read</h1>\n<ul>\n<li>a</li>\n<li>b</li>\n</ul>"
        self.assertEqual(self.posts(), [[{"itemType": "note", "parentItem": "ITEM0001", "note": html}]])
        self.assertEqual(self.zot.data(line["note_key"])["note"], html)
        self.assertEqual(r.lines[-1], {"summary": {"total": 1, "ok": 1, "skipped": 0, "failed": 0}})

    def test_updated_by_marker_with_its_version(self):
        r = self.run_("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["action"], r.lines[0]["note_key"], r.lines[0]["retried"]), ("updated", "NOTE0001", False))
        # one PATCH and no retry: the fake answers 412 to any other version than the note's 14
        self.assertEqual(self.patches(), [("NOTE0001", {"note": "<p>p2z: old</p>\n<p>fresh</p>"})])
        self.assertEqual(self.zot.data("NOTE0001")["note"], "<p>p2z: old</p>\n<p>fresh</p>")

    def test_unchanged_writes_nothing(self):
        for dry in ((), ("--dry-run",)):
            r = self.run_("--key", "ITEM0001", "--text", "stale", "--marker", "p2z: old", *dry)
            self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["note_key"]),
                             (0, "skipped", "unchanged", "NOTE0001"))
        self.assertEqual(self.zot.writes(), [])

    def test_412_retries_once(self):
        self.zot.bump_before_write = 1
        r = self.run_("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual((r.code, r.lines[0]["action"], r.lines[0]["retried"]), (0, "updated", True), r)
        self.assertEqual(len(self.patches()), 2)

        self.setUp()   # the concurrent edit wrote the very same note
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(note="<p>p2z: old</p>\n<p>fresh</p>")
        r = self.run_("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual((r.code, r.lines[0]["reason"], r.lines[0]["retried"]), (0, "unchanged", True), r)
        self.assertEqual(len(self.patches()), 1)

        self.setUp()
        self.zot.bump_before_write = 2
        r = self.run_("--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "version_conflict"))
        self.assertEqual(len(self.patches()), 2)

    def test_without_marker_always_creates(self):
        for _ in (1, 2):
            self.assertEqual(self.run_("--key", "ITEM0001", "--text", "x").lines[0]["action"], "created")
        self.assertEqual([body[0]["note"] for body in self.posts()], ["<p>x</p>", "<p>x</p>"])

    def test_marker_ambiguous(self):
        self.zot.add_item("NOTE0003", version=16, itemType="note", parentItem="ITEM0001", note="<p>p2z: old</p>")
        r = self.run_("--key", "ITEM0001", "--text", "x", "--marker", "p2z: old")
        self.assertEqual(r.code, 1)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["note_keys"]), ("marker_ambiguous", ["NOTE0001", "NOTE0003"]))
        self.assertEqual(self.zot.writes(), [])

    def test_dry_run(self):
        r = self.run_("--key", "ITEM0001", "ITEM0002", "--text", "fresh", "--marker", "p2z: old", "--dry-run")
        self.assertEqual(r.code, 0, r)
        first, second = r.lines[:2]
        self.assertEqual((first["action"], first["note_key"], first["dry_run"], first["html"]),
                         ("updated", "NOTE0001", True, "<p>p2z: old</p>\n<p>fresh</p>"))
        self.assertEqual((second["action"], second["note_key"]), ("created", None))
        self.assertEqual(r.lines[-1]["summary"], {"total": 2, "ok": 2, "skipped": 0, "failed": 0, "dry_run": True})
        self.assertEqual(self.zot.writes(), [])

    def test_every_item_named_gets_the_note(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("**bold**\n")
        r = self.run_("--key", "ITEM0002,ATTA0001", "ZZZZZZZZ", "--cite", "one2020paper", "--file", f.name)
        Path(f.name).unlink()
        self.assertEqual(r.code, 1)
        out = r.lines
        self.assertEqual([(o.get("key"), o["code"], o.get("action")) for o in out[:4]],
                         [("ITEM0002", "ok", "created"), ("ATTA0001", "not_a_parent", None), ("ZZZZZZZZ", "not_found", None),
                          ("ITEM0001", "ok", "created")])
        self.assertEqual((out[1]["itemType"], out[1]["parent"]), ("attachment", "ITEM0001"))
        self.assertEqual(out[3]["cite"], "one2020paper")
        self.assertEqual(out[-1]["summary"], {"total": 4, "ok": 2, "skipped": 0, "failed": 2})
        self.assertEqual([(body[0]["parentItem"], body[0]["note"]) for body in self.posts()],
                         [("ITEM0002", "<p><strong>bold</strong></p>"), ("ITEM0001", "<p><strong>bold</strong></p>")])

    def test_bad_input_is_one_line_and_asks_nothing(self):
        r = self.run_("--key", "ITEM0001", "ITEM0002", "--text", "   ")
        self.assertEqual((r.code, [o["code"] for o in r.lines]), (1, ["empty_note"]))
        self.assertIn("hint", r.lines[0])
        r = self.run_("--key", "ITEM0001", "--file", "/no/such/note.md")
        self.assertEqual((r.code, [o["code"] for o in r.lines]), (1, ["file_not_found"]))
        self.assertEqual(self.zot.requests, [])
        self.assertEqual(self.run_("--key", "ITEM0001", "--text", "x", "--marker", "  ").code, 2)
        self.assertEqual(self.run_("--key", "ITEM0001").code, 2, "--text or --file is required")
        self.assertEqual(self.run_("--text", "x").code, 2, "--key or --cite is required")

    def test_cite_resolution(self):
        r = self.run_("--cite", "one2020paper", "--text", "x", "--dry-run")
        self.assertEqual((r.code, r.lines[0]["key"], r.lines[0]["cite"]), (0, "ITEM0001", "one2020paper"))
        self.zot.search_sees_citekey = False
        r = self.run_("--cite", "one2020paper", "nobody2099", "dup2021key", "--text", "x")
        self.assertEqual(r.code, 1)
        out = r.lines
        self.assertEqual((out[0]["key"], out[0]["action"]), ("ITEM0001", "created"), "found by the fallback scan")
        self.assertEqual(out[1]["code"], "cite_not_found")
        self.assertEqual((out[2]["code"], out[2]["keys"]), ("cite_ambiguous", ["ITEM0002", "ITEM0003"]))
        self.assertEqual(len(self.posts()), 1)

    def test_write_denied_and_readback_mismatch(self):
        self.zot.write_status = (403, "Write access denied")
        for marker in ("p2z: new", "p2z: old"):   # creating, then updating
            r = self.run_("--key", "ITEM0001", "--text", "fresh", "--marker", marker)
            self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_denied", "Write access denied"))

        self.setUp()   # Zotero stores the note in another form than the one sent
        self.zot.on_write = lambda it: it["data"].update(note=f'<div data-schema-version="9">{it["data"]["note"]}</div>')
        r = self.run_("--key", "ITEM0001", "--text", "x")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["action"]), (1, "readback_mismatch", "created"))
        self.assertTrue(r.lines[0]["note_key"])

    def test_cannot_check(self):
        r = self.run_("--key", "ITEM0001", "--text", "x", base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("--key", "ITEM0001", "--text", "x", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        self.assertEqual(self.zot.writes(), [])

    def test_smoke(self):
        r = smoke("note", "--key", "ITEM0001", "--text", "fresh", "--marker", "p2z: old", "--dry-run",
                  "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["action"], r.lines[-1]["summary"]["total"]), ("updated", 1))


if __name__ == "__main__":
    unittest.main()
