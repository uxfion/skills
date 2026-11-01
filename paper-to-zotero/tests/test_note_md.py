# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Tests for p2zlib/note_md.py and scripts/note_md.py: every fixture note read to its expected Markdown, written back
to the same note in the editor's model, and read again to the same Markdown; the front matter; the writer's fixes;
the command line.

The fixtures (tests/fixtures/note_md/<set>.html and .md, cases under `<!-- name -->` lines): `blind` (64 notes an
agent wrote from the editor's schema), `edges` (28 hand-made), `better-notes` (Better Notes v3.3.3's test note),
`notes` (whole paper notes: editor-saved, imported, plain, edited by the user)."""
import re
import tempfile
import unittest
from pathlib import Path

from helpers import SCRIPTS, smoke  # noqa: F401  (puts scripts/ on sys.path)
from p2zlib import note_md as N

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "note_md"


def cases(path):
    parts = re.split(r"^<!-- (.+?) -->\n", path.read_text(encoding="utf-8"), flags=re.M)
    return {parts[i]: parts[i + 1].strip("\n") + "\n" for i in range(1, len(parts), 2)}


class Fixtures(unittest.TestCase):
    def test_every_note_reads_writes_back_and_reads_again(self):
        total = 0
        for html_file in sorted(FIXTURES.glob("*.html")):
            notes, expected = cases(html_file), cases(html_file.with_suffix(".md"))
            self.assertEqual(notes.keys(), expected.keys(), html_file.name)
            for name, html in notes.items():
                with self.subTest(set=html_file.stem, case=name):
                    md = N.to_md(html)
                    self.assertEqual(md, expected[name])                       # the expected Markdown
                    back = N.to_note(md)[0]
                    self.assertTrue(N.same(html, back), "the note changed")    # guarantee 1, in the editor's model
                    self.assertEqual(N.to_md(back), md)                        # guarantee 2: stable
                    total += 1
        self.assertEqual(total, 100)

    def test_fallbacks_are_the_blocks_markdown_cannot_say(self):
        kept = {}
        for html_file in sorted(FIXTURES.glob("*.html")):
            for name, html in cases(html_file).items():
                fb = []
                N.to_md(html, fallbacks=fb)
                if fb:
                    kept[name] = [tag for _, tag in fb]
        self.assertEqual(kept, {
            "code block with bold inside": ["pre"],
            "table with a list and display math in cells": ["table"],
            "merged and coloured cells": ["table"],
            "header column instead of header row": ["table"],
            "indented paragraphs and heading with marks": ["p", "p", "h3"],
            "aligned paragraphs and headings": ["h2", "p", "p", "p"],
            "direction and id attributes": ["p", "p", "h3", "ul"],
            "attribute blocks inside quote and list": ["p", "p"],
            "realistic paper note, mixed": ["p"],
            "table without header": ["table"],
            "better notes v3.3.3 test fixture": ["table"],
            "Better Notes import": ["ul"],
            "plain HTML, never saved": ["table"],
            "edited by the user": ["p"],
        })


class Model(unittest.TestCase):
    def test_what_the_editor_loads_alike_is_the_same(self):
        same = N.same
        self.assertTrue(same('<p><a href="u" rel="noopener">x</a></p>', '<p><a href="u">x</a></p>'))
        self.assertTrue(same("<ul><li><p>x</p></li></ul>", "<ul>\n<li>\nx\n</li>\n</ul>"))
        self.assertTrue(same("<p><b>x</b> <i>y</i></p>", "<p><strong>x</strong> <em>y</em></p>"))
        self.assertTrue(same("<p><strong><em>x</em></strong></p>", "<p><em><strong>x</strong></em></p>"))
        self.assertTrue(same("<p>a \n  b </p>", "<p>a b</p>"))
        self.assertTrue(same('<p><img alt="" width="1" src="s"></p>', '<p><img src="s" alt="" width="1"></p>'))
        self.assertTrue(same("<table><thead><tr><th>a</th></tr></thead></table>", "<table><tr><th><p>a</p></th></tr></table>"))
        self.assertTrue(same("<pre>a \xa0b</pre>", "<pre>a  b</pre>"))     # the editor's double space in code
        self.assertTrue(same("<p><strong><code>x</code></strong></p>", "<p><code>x</code></p>"))   # code excludes marks

    def test_what_differs_is_not(self):
        same = N.same
        self.assertFalse(same("<pre><strong>x</strong></pre>", "<pre>x</pre>"))     # bold lost in a code block
        self.assertFalse(same("<table><tr><th>a</th></tr></table>", "<table><tr><td>a</td></tr></table>"))
        self.assertFalse(same("<p>a\xa0b</p>", "<p>a b</p>"))
        self.assertFalse(same('<p style="text-align: center">x</p>', "<p>x</p>"))
        self.assertFalse(same("<p>x</p>", "<p>x</p><p>y</p>"))


class FrontMatter(unittest.TestCase):
    def test_wrapper_goes_to_the_front_matter_and_comes_back(self):
        html = '<div data-schema-version="9" data-citation-items="%5B%5D"><p>x</p></div>'
        md = N.to_md(html, {"key": "NOTE0001", "version": 12, "parent": "doe2024x", "x-own": "kept"})
        self.assertEqual(md, "---\nkey: NOTE0001\nversion: 12\nparent: doe2024x\nx-own: kept\nschema: 9\n"
                             "citation-items: %5B%5D\n---\nx\n")
        back, meta = N.to_note(md)
        self.assertEqual(back, '<div data-schema-version="9" data-citation-items="%5B%5D"><p>x</p>\n</div>')
        self.assertEqual(meta, {"key": "NOTE0001", "version": "12", "parent": "doe2024x", "x-own": "kept"})

    def test_no_wrapper_no_front_matter(self):
        self.assertEqual(N.to_md("<p>x</p>"), "x\n")
        self.assertEqual(N.to_note("x\n"), ("<p>x</p>\n", {}))
        self.assertEqual(N.to_md('<div data-schema-version="9"><p></p></div>'), "---\nschema: 9\n---\n")

    def test_lists_and_set_meta(self):
        md = N.to_md("<p>x</p>", {"collections": ["AAAA1111", "BBBB2222"], "related": []})
        self.assertEqual(md, "---\ncollections: AAAA1111,BBBB2222\nrelated:\n---\nx\n")
        self.assertEqual(N.split_meta(md)[0], {"collections": "AAAA1111,BBBB2222", "related": ""})
        moved = N.set_meta(md, {"key": "NOTE0001", "version": 3, "related": None})
        self.assertEqual(moved, "---\nkey: NOTE0001\nversion: 3\ncollections: AAAA1111,BBBB2222\n---\nx\n")

    def test_malformed_front_matter_is_an_error(self):
        for md in ("---\nkey NOTE0001\n---\nx", "---\nkey: a\n", "---"):
            with self.subTest(md=md), self.assertRaises(ValueError):
                N.split_meta(md)
        self.assertEqual(N.split_meta("x\n---\n"), ({}, "x\n---\n"))


class Writer(unittest.TestCase):
    def test_links_as_written(self):
        html = N.render("[a](https://zh.wikipedia.org/wiki/均值) [b](file:///D:/x.pdf) [c](<https://e.com/a b>)")
        self.assertIn('href="https://zh.wikipedia.org/wiki/均值"', html)
        self.assertIn('href="file:///D:/x.pdf"', html)
        self.assertIn('href="https://e.com/a b"', html)

    def test_math_and_code(self):
        self.assertEqual(N.render("- a\n  $$\n  x^2\n  $$\n"),
                         '<ul>\n<li>a<pre class="math">$$\nx^2\n$$</pre>\n</li>\n</ul>\n')
        self.assertEqual(N.render("> $$\n> a\n> $$\n"), '<blockquote>\n<pre class="math">$$\na\n$$</pre>\n</blockquote>\n')
        self.assertEqual(N.render("$x$ and $$y$$"),
                         '<p><span class="math">$x$</span> and <span class="math">$$y$$</span></p>\n')
        self.assertEqual(N.to_md(N.render("$x$ and $$y$$")), "$x$ and $$y$$\n")
        self.assertEqual(N.render("```py\na < b\n```\n"), "<pre>a &lt; b</pre>\n")

    def test_dollars(self):
        for md in ("成本 $5 和 $10 美元", "训练约 $4.6M，推理 $0.01/次"):
            self.assertNotIn("math", N.render(md), md)
        self.assertIn("math", N.render("3$\\times$3 卷积"))
        # the editor's headings hold no math: the TeX stays text, and reads back as written
        self.assertEqual(N.render("## 为什么 $O(n^2)$ 不可行"), "<h2>为什么 $O(n^2)$ 不可行</h2>\n")
        self.assertEqual(N.to_md("<h2>为什么 $O(n^2)$ 不可行</h2>"), "## 为什么 $O(n^2)$ 不可行\n")
        html = '<h2>a <span class="math">$x$</span></h2>'  # not the editor's, still kept
        self.assertTrue(N.same(N.to_note(N.to_md(html))[0], html))

    def test_minimal_escapes(self):
        md = N.to_md("<p>C:\\temp\\x snake_case a - b 4 * 5 [已答] 1. x</p>")
        self.assertEqual(md, "C:\\temp\\x snake_case a - b 4 * 5 [已答] 1. x\n")
        self.assertEqual(N.to_md("<p>1. x</p><p>- y</p><p>[1]: z</p>"), "1\\. x\n\n\\- y\n\n\\[1]: z\n")


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="note-md-"))
        (self.dir / "a.html").write_text('<div data-schema-version="9"><p>a <strong>b</strong></p></div>', encoding="utf-8")
        (self.dir / "b.html").write_text('<p style="text-align: center">c</p>', encoding="utf-8")

    def test_files_into_a_directory_and_back(self):
        r = smoke("note_md", "-t", "md", self.dir / "a.html", self.dir / "b.html", "-o", f"{self.dir}/md/")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((self.dir / "md/a.md").read_text(encoding="utf-8"), "---\nschema: 9\n---\na **b**\n")
        self.assertIn("b.html: block 1: <p> kept as HTML", r.err)
        r = smoke("note_md", "-t", "note", self.dir / "md/a.md")
        self.assertEqual((r.code, r.out), (0, '<div data-schema-version="9"><p>a <strong>b</strong></p>\n</div>\n'))

    def test_usage_errors(self):
        (self.dir / "taken.md").write_text("x", encoding="utf-8")
        for argv in (["-t", "md", self.dir / "a.html", self.dir / "b.html"],          # two inputs, stdout
                     ["-t", "md", self.dir / "a.html", "-o", self.dir / "taken.md"],  # over an existing file
                     ["-t", "md", "-o", f"{self.dir}/out/"],                            # stdin into a directory
                     ["-t", "html", self.dir / "a.html"]):
            with self.subTest(argv=argv):
                self.assertEqual(smoke("note_md", *argv).code, 2)

    def test_an_input_that_fails_is_exit_1(self):
        (self.dir / "bad.md").write_text("---\nnot a key line\n---\nx\n", encoding="utf-8")
        r = smoke("note_md", "-t", "note", self.dir / "bad.md")
        self.assertEqual(r.code, 1)
        self.assertIn("front matter line 2", r.err)


if __name__ == "__main__":
    unittest.main()
