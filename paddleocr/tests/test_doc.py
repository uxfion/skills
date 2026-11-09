# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2"]
# ///
"""Tests for scripts/doc.py: changes folded onto the models' output, the Markdown made from a record, edits to it
committed back, verdicts kept, edits carried over to a new parse (no GPU).

fixtures/synthetic.raw.json is a made-up record as the models give it (pages 1-3 and 5 of 5: a formula with its
number and a lead-in line, a paragraph continued across columns, a two-panel figure with its caption, a table
continued over a page with an image inside it, a lone image, page furniture); fixtures/synthetic.json and .md are
what processing makes of it. `uv run tests/test_doc.py --engine` runs again in the paddleocr tool environment and
adds the tests that need PaddleOCR: processing the raw record gives exactly those two files, and the Markdown rules
give what PaddleOCR's own do."""
import contextlib
import copy
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))
if "--engine" in sys.argv:
    sys.argv.remove("--engine")
    import parse  # noqa: E402
    parse.ensure_tool_env(__file__)
import doc as D  # noqa: E402

ENGINE = importlib.util.find_spec("paddlex") is not None
PROCESSED = json.loads((FIXTURES / "synthetic.json").read_text(encoding="utf-8"))


def record(findings=()):
    r = copy.deepcopy(PROCESSED)
    r["findings"] = [dict(f) for f in findings]
    return r


def finding(ident, items=(), status="open", **extra):
    code, _, obj = ident.partition("@")
    f = {"id": ident, "code": code, "items": list(items), "detail": "", "status": status, **extra}
    if obj.startswith("p"):
        f["page"] = D.page_of(obj)
        if "-" in obj:
            f["block"] = obj
    return f


def changes(r, ident):
    return [c for c in next(b for b in r["blocks"] if b["id"] == ident).get("changes", []) if c["by"] == "agent"]


class Fold(unittest.TestCase):
    def test_changes_apply_in_order(self):
        b = {"id": "p1-1", "label": "text", "text": "DeepSeek-RI is fast", "changes": [
            {"by": "agent", "was": "RI", "now": "R1"}, {"by": "agent", "was": "fast", "now": "quick"}]}
        self.assertEqual(D.fold(b)["text"], "DeepSeek-R1 is quick")

    def test_an_edit_whose_text_is_gone_is_stale(self):
        b = {"id": "p1-1", "label": "text", "text": "a b", "changes": [{"by": "agent", "was": "c", "now": "d"}]}
        s = D.fold(b)
        self.assertEqual((s["text"], len(s["stale"])), ("a b", 1))

    def test_the_raw_text_stays(self):
        r = record()
        before = next(b["text"] for b in r["blocks"] if b["id"] == "p1-11")
        D.commit(r, D.render_text(r)[0].replace("after the formula", "following the formula"))
        b = next(b for b in r["blocks"] if b["id"] == "p1-11")
        self.assertEqual(b["text"], before)
        self.assertIn("following", D.fold(b)["text"])


class EditOf(unittest.TestCase):
    def test_whole_words_inside_markup(self):
        for old, new, was in (("OpenAI-o1 and DeepSeek-RI demonstrate", "OpenAI-o1 and DeepSeek-R1 demonstrate", "DeepSeek-RI"),
                              ("<td>A</td><td>0.91</td><td>0.5</td>", "<td>A</td><td>0.92</td><td>0.5</td>", "0.91")):
            w, n = D.edit_of(old, new)
            self.assertIn(was, w)
            self.assertEqual(old.replace(w, n), new)

    def test_was_occurs_once(self):
        for old, new in (("a b a b", "a b a c"), ("x x x", "x y x"), ("abc", "xbc"), ("same", "same more")):
            w, n = D.edit_of(old, new)
            self.assertEqual(old.count(w), 1)
            self.assertEqual(old.replace(w, n), new)


class Markdown(unittest.TestCase):
    def setUp(self):
        self.text, self.pieces = D.render_text(record())

    def test_matches_the_fixture(self):
        self.assertEqual(self.text, (FIXTURES / "synthetic.md").read_text(encoding="utf-8"))

    def test_manifest_and_pages(self):
        first = self.text.split("\n", 1)[0]
        self.assertTrue(first.startswith("<!-- paddleocr render=6 source=synthetic.pdf "))
        self.assertIn("pages=1-3,5/5", first)
        self.assertEqual([p["text"] for p in self.pieces if p["kind"] == "page"],
                         ["<!-- page 1 -->", "<!-- page 2 -->", "<!-- page 3 -->", "<!-- page 5 -->"])

    def test_page_furniture_stays_out(self):
        self.assertNotIn("Journal of Examples", self.text)
        self.assertNotIn("Synthetic Journal 2026", self.text)

    def test_formula_number_and_lead_in(self):
        i = self.text.index("where E is energy:")
        self.assertLess(i, self.text.index("\\tag*{(1)}"))

    def test_footnote_last_on_its_page(self):
        page1 = self.text.split("<!-- page 2 -->")[0]
        self.assertTrue(page1.rstrip().endswith("* Corresponding author."))

    def test_figure_markers_hold_its_text(self):
        part = self.text.split("<!-- figure p2-2 (Fig. 1) -->")[1].split("<!-- end figure p2-2 -->")[0]
        self.assertIn("![Fig. 1](imgs/p2-2.png)", part)
        self.assertIn("Accuracy over time", part)
        self.assertNotIn("Fig. 1 |", part)                  # the caption follows the figure

    def test_lone_image_without_markers(self):
        self.assertIn("![](imgs/p5-5.png)", self.text)
        self.assertNotIn("<!-- figure p5-5", self.text)

    def test_table_continued_and_its_image(self):
        self.assertIn("<td>B</td><td>0.87</td>", self.text.split("<!-- page 3 -->")[0])
        self.assertIn("<!-- table p2-9 continues on page 3 -->", self.text)
        self.assertIn('<img alt="Image" src="imgs/p3-1-1.png"/>', self.text)

    def test_notes(self):
        r = record([finding("missing_text@p1", ["the right column ends here"]),
                    finding("table_mismatch@p2-9", ["0.95"], "unresolved", why="illegible", seen=["0.95"]),
                    finding("extra_text@p1-11", ["invented"], "ok", why="it is there", seen=["invented"]),
                    finding("figure_check@p2-6", ["split"], detail="split: 2 crops",
                            crops=[{"n": 1, "figure": "p2-2", "box": [0, 0, 1, 1], "page": 2}])])
        text = D.render_text(r)[0]
        page1 = text.split("<!-- page 1 -->\n\n")[1]
        self.assertTrue(page1.startswith("<!-- open missing_text@p1: the right column ends here -->"))
        self.assertLess(text.index("<!-- unresolved table_mismatch@p2-9: illegible -->"), text.index("<table>"))
        self.assertNotIn("extra_text@p1-11", text)
        self.assertLess(text.index("<!-- open figure_check@p2-6: split: 2 crops -->"), text.index("<!-- figure p2-2"))
        self.assertIn("open=2 unresolved=1", text.split("\n", 1)[0])

    def test_inline_math_hugs_its_dollars_from_layout_5(self):
        r = record()
        given = "Scan $ x_{NC} $ and mask $ x_{TM} $ at \\$5, with $$ E $$ as written."
        next(b for b in r["blocks"] if b["id"] == "p1-11")["text"] = given
        text = D.render_text(r)[0]
        self.assertIn("Scan $x_{NC}$ and mask $x_{TM}$ at \\$5, with $$ E $$ as written.", text)
        self.assertIn(given, D.render_text(r, 4)[0])          # an earlier layout writes it as PaddleOCR gives it
        self.assertEqual(D.commit(r, text), [])                  # read back unedited: nothing to record
        D.commit(r, text.replace("and mask", "and the mask"))
        self.assertEqual([(c["was"], c["now"]) for c in changes(r, "p1-11")], [("mask", "the mask")])
        self.assertIn("Scan $x_{NC}$ and the mask $x_{TM}$", D.render_text(r)[0])

    def test_tight_math_keeps_the_words_between_from_layout_6(self):
        r = record()
        given = "Map $x$ and returns $ \\hat{y} $; then $y$ and $ z $ cost $5 and $10."
        next(b for b in r["blocks"] if b["id"] == "p1-11")["text"] = given
        self.assertIn("Map $x$ and returns $\\hat{y}$; then $y$ and $z$ cost $5 and $10.", D.render_text(r)[0])
        old = D.render_text(r, 5)[0]                              # layout 5 paired a closing dollar with an opening one
        self.assertIn("$x$and returns$", old)
        self.assertEqual(D.commit(r, old), [])                    # and a file in it still reads back as unedited


class PageOrder(unittest.TestCase):
    @staticmethod
    def b(i, label, box, text=""):
        return {"id": f"p1-{i}", "page": 1, "label": label, "box": box, "text": text, "level": None}

    def test_number_follows_its_formula_and_lead_in_goes_first(self):
        lead = self.b(0, "text", [90, 707, 440, 730], "which can be written as")
        formula = self.b(1, "display_formula", [266, 741, 432, 765], "$$ g = 1 - o $$")
        number = self.b(2, "formula_number", [567, 743, 602, 764], "(19)")
        after = self.b(3, "text", [91, 776, 602, 863], "Notice that")
        order, numbers = D.page_order([formula, lead, number, after])
        self.assertEqual([x["id"] for x in order], ["p1-0", "p1-1", "p1-2", "p1-3"])
        self.assertEqual([n["id"] for n in numbers["p1-1"]], ["p1-2"])

    def test_two_numbers_on_one_formula(self):
        formula = self.b(0, "display_formula", [804, 858, 972, 908], "$$ a \\\\ b $$")
        n22 = self.b(1, "formula_number", [1107, 855, 1143, 877], "(22)")
        n23 = self.b(2, "formula_number", [1107, 883, 1142, 904], "(23)")
        order, numbers = D.page_order([formula, n22, n23])
        self.assertEqual([n["text"] for n in numbers["p1-0"]], ["(22)", "(23)"])

    def test_number_without_a_formula_stays(self):
        text = self.b(0, "text", [0, 0, 100, 20], "see")
        lone = self.b(1, "formula_number", [500, 300, 530, 320], "(4)")
        self.assertEqual(D.page_order([text, lone]), ([text, lone], {}))

    def test_format_pages(self):
        self.assertEqual(D.format_pages([1, 2, 3, 8]), "1-3,8")
        self.assertEqual(D.format_pages([5]), "5")
        self.assertEqual(D.format_pages([1, 3, 4]), "1,3-4")


class Commit(unittest.TestCase):
    def edit(self, r, old, new):
        text = D.render_text(r)[0]
        self.assertIn(old, text)
        return D.commit(r, text.replace(old, new, 1))

    def test_word_fix_with_reason(self):
        r = record()
        self.edit(r, "Second paragraph after", "<!-- fixed: the text layer says following -->\nSecond paragraph following")
        self.assertEqual([(c["was"], c["now"], c["why"]) for c in changes(r, "p1-11")],
                         [("after", "following", "the text layer says following")])
        self.assertIn("<!-- fixed: the text layer says following -->\n\nSecond paragraph following", D.render_text(r)[0])

    def test_verdicts(self):
        r = record([finding("missing_text@p1", ["the right column ends here"]), finding("table_mismatch@p2-9", ["0.95"])])
        text = D.render_text(r)[0]
        text = text.replace("<!-- open missing_text@p1: the right column ends here -->", "<!-- ok missing_text@p1: a figure label -->")
        text = text.replace("<!-- open table_mismatch@p2-9: 0.95 -->", "<!-- unresolved table_mismatch@p2-9: the cell is illegible -->")
        D.commit(r, text)
        got = {f["id"]: (f["status"], f.get("why"), f.get("seen")) for f in r["findings"]}
        self.assertEqual(got, {"missing_text@p1": ("ok", "a figure label", ["the right column ends here"]),
                               "table_mismatch@p2-9": ("unresolved", "the cell is illegible", ["0.95"])})

    def test_table_cell(self):
        r = record()
        self.edit(r, "<td>0.91</td>", "<td>0.92</td>")
        self.assertEqual([(c["was"], c["now"]) for c in changes(r, "p2-9")], [("0.91", "0.92")])

    def test_formula_keeps_its_number(self):
        r = record()
        self.edit(r, "E = m c^{2}", "E = m c^{3}")
        self.assertEqual([(c["was"], c["now"]) for c in changes(r, "p1-7")], [("2", "3")])
        self.assertEqual(changes(r, "p1-9"), [])
        self.assertIn("E = m c^{3}   \\tag*{(1)}$$", D.render_text(r)[0])

    def test_heading_level(self):
        r = record()
        self.edit(r, "## 2 Results", "### 2 Results")
        self.assertEqual(changes(r, "p2-7")[0]["level"], 2)
        self.assertIn("\n### 2 Results\n", D.render_text(r)[0])

    def test_a_heading_made_plain_text_is_body_text(self):
        # 2026-11, CycleGAN: the end of a sentence read as a heading ("important problem for future work.")
        r = record()
        self.edit(r, "## 2 Results", "<!-- fixed: running text, not a heading -->\n2 Results")
        self.assertEqual([(c.get("label"), c["why"]) for c in changes(r, "p2-7")], [("text", "running text, not a heading")])
        text = D.render_text(r)[0]
        self.assertIn("\n2 Results\n", text)
        self.assertNotIn("## 2 Results", text)
        self.assertEqual(D.commit(r, text), [])

    def test_edit_across_blocks_goes_to_the_first(self):
        r = record()
        self.edit(r, "Ann Author, Bob Writer\n\n## Abstract", "Ann Author, Bob Writer. Abstract")
        self.assertTrue(any(c.get("deleted") for c in changes(r, "p1-3")))
        self.assertIn("We test a parser", D.fold(next(b for b in r["blocks"] if b["id"] == "p1-2"))["text"])

    def test_new_paragraph_is_a_block(self):
        r = record()
        self.edit(r, "Text after the table with a reference [1].\n", "Text after the table with a reference [1].\n\nA dropped line.\n")
        added = [b for b in r["blocks"] if b["id"] == "p3-n1"]
        self.assertEqual((added[0]["text"], added[0]["added"]["after"]), ("A dropped line.", "p3-2"))
        self.assertIn("[1].\n\nA dropped line.", D.render_text(r)[0])

    def test_a_heading_and_its_paragraph_are_two_blocks(self):
        # 2026-11, T-CACE: a heading added with its first paragraph came out as one heading block holding both
        r = record()
        self.edit(r, "Text after the table with a reference [1].\n", "Text after the table with a reference [1].\n\n"
                  "<!-- fixed: from the page image -->\n## 3 Discussion\n\nA dropped paragraph.\n")
        added = [(b["id"], b["label"], b["text"], b["added"]["why"]) for b in r["blocks"] if b.get("added")]
        self.assertEqual(added, [("p3-n1", "paragraph_title", "3 Discussion", "from the page image"),
                                 ("p3-n2", "text", "A dropped paragraph.", "")])

    def test_an_edit_that_adds_a_paragraph_is_refused(self):
        with self.assertRaises(D.Stop) as refused:
            self.edit(record(), "reference [1].\n", "reference [2].\n\nA dropped paragraph.\n")
        self.assertEqual(refused.exception.code, "edit_refused")
        # blank lines a block already holds are its own: 611 of 1465 algorithm blocks in 267 parses (2026-11)
        r = record()
        algorithm = next(b for b in r["blocks"] if b["id"] == "p3-5")
        algorithm["text"] = "Algorithm 1 Search\n\n1: for each node do\n2:   expand it\n"
        self.edit(r, "for each node", "for every node")
        self.assertEqual([(c["was"], c["now"]) for c in changes(r, "p3-5")], [("each", "every")])

    def test_text_against_an_image_line_is_never_lost(self):
        # a caption typed right under a figure's image line, no blank line between: commit dropped it (2026-11)
        r = record()
        self.edit(r, "![](imgs/p5-5.png)\n", "![](imgs/p5-5.png)\nFig. 2. A caption the parse lost.\n")
        self.assertEqual([(b["id"], b["text"], b["added"]["after"]) for b in r["blocks"] if b.get("added")],
                         [("p5-n1", "Fig. 2. A caption the parse lost.", "p5-5")])
        self.assertIn("![](imgs/p5-5.png)\n\nFig. 2. A caption the parse lost.\n\nA figure without", D.render_text(r)[0])
        with self.assertRaises(D.Stop) as refused:                     # text in the image line's place
            self.edit(record(), "![](imgs/p5-5.png)\n", "Fig. 2. A caption the parse lost.\n")
        self.assertEqual(refused.exception.code, "edit_refused")

    def test_a_paragraph_after_a_figure_stays_after_it(self):
        # 2026-11, USRMamba p.11 and CycleGAN p.7: captions restored under their figures came out at the page's top
        r = record()
        self.edit(r, "<!-- end figure p2-2 -->\n", "<!-- end figure p2-2 -->\n\nA paragraph after the figure.\n")
        self.assertEqual([b["added"]["after"] for b in r["blocks"] if b.get("added")], ["p2-2"])
        self.assertIn("<!-- end figure p2-2 -->\n\nA paragraph after the figure.\n\nFig. 1 |", D.render_text(r)[0])
        D.set_figure(r, None, 3, [50, 360, 560, 740], "")              # a figure without blocks, placed by its box
        D.refine_figures(r)
        self.edit(r, "![](imgs/p3-cut1.png)\n", "![](imgs/p3-cut1.png)\n\nFig. 3. Restored from the text layer.\n")
        self.assertIn("![](imgs/p3-cut1.png)\n\nFig. 3. Restored from the text layer.\n\n", D.render_text(r)[0])
        self.assertEqual(D.commit(r, D.render_text(r)[0]), [])

    def test_a_line_without_a_blank_joins_its_paragraph(self):
        r = record()
        self.edit(r, "reference [1].\n", "reference [1].\nAnd its second line.\n")
        self.assertIn("And its second line.", D.fold(next(b for b in r["blocks"] if b["id"] == "p3-2"))["text"])

    def test_edits_in_neighbouring_paragraphs_stay_apart(self):
        r = record()
        text = D.render_text(r)[0].replace("cites Fig. 1", "cites Figure 1").replace("* Corresponding author.", "* Corresponding author: Ann.")
        D.commit(r, text.replace("Second paragraph after", "<!-- fixed: from the text layer -->\nSecond paragraph after"))
        self.assertEqual([(c["was"], c["now"], c["why"]) for c in changes(r, "p1-11")], [("Fig.", "Figure", "from the text layer")])
        self.assertEqual([(c["was"], c["now"]) for c in changes(r, "p1-10")], [("author.", "author: Ann.")])

    def test_reasons_inside_a_block_are_kept(self):
        r = record()
        text = D.render_text(r)[0]
        text = text.replace("Algorithm 1 Search\n1: for each node do", "Algorithm 1 Search\n<!-- fixed: from the image -->\n1: for every node do")
        D.commit(r, text)
        self.assertEqual(changes(r, "p3-5")[0]["why"], "from the image")

    def test_deleted_block(self):
        r = record()
        self.edit(r, "Accuracy over time\n\n", "")
        self.assertTrue(changes(r, "p2-5")[0]["deleted"])
        self.assertNotIn("Accuracy over time", D.render_text(r)[0])

    def test_deleted_image_line_hides_the_figure(self):
        r = record()
        self.edit(r, "![Fig. 1](imgs/p2-2.png)\n\n", "")
        fig = next(f for f in r["figures"] if f["id"] == "p2-2")
        self.assertTrue(D.fold_figure(fig)["hidden"])
        self.assertNotIn("imgs/p2-2.png", D.render_text(r)[0])

    def test_markers_are_protected(self):
        # an image line as a paragraph of its own: 2026-11, USRMamba, where it became a text block
        for old, new in (("<!-- page 3 -->", "<!-- page 4 -->"), ("<!-- end figure p2-2 -->\n", ""),
                         ("A figure without", "![x](imgs/mine.png)\nA figure without"),
                         ("reference [1].\n", "reference [1].\n\n![Fig. 2](imgs/p3-n1.png)\n")):
            with self.assertRaises(D.Stop) as refused:
                self.edit(record(), old, new)
            self.assertEqual(refused.exception.code, "edit_refused")

    def test_unedited_commits_nothing(self):
        r = record()
        self.assertEqual(D.commit(r, D.render_text(r)[0]), [])
        self.assertEqual(r, record())

    def test_commit_then_regenerate_is_stable(self):
        r = record()
        self.edit(r, "cites Fig. 1", "<!-- fixed: typo -->\ncites Figure 1")
        text = D.render_text(r)[0]
        self.assertEqual(D.commit(r, text), [])


class Verdicts(unittest.TestCase):
    def test_kept_while_covered_reopened_when_more(self):
        r = record([finding("missing_numbers@p3", ["12", "13"], "ok", why="axis ticks", seen=["12", "13"])])
        moves = D.merge_findings(r, [finding("missing_numbers@p3", ["12"])])
        self.assertEqual((r["findings"][0]["status"], r["findings"][0]["why"]), ("ok", "axis ticks"))
        moves = D.merge_findings(r, [finding("missing_numbers@p3", ["12", "99"])])
        self.assertEqual((r["findings"][0]["status"], moves["reopened"]), ("open", ["missing_numbers@p3"]))

    def test_a_shorter_run_is_covered(self):
        self.assertTrue(D.covered(["the right column"], ["the right column ends here"]))

    def test_gone_and_new(self):
        r = record([finding("missing_text@p1", ["a"])])
        moves = D.merge_findings(r, [finding("missing_text@p3", ["b"])])
        self.assertEqual((moves["gone"], moves["new"]), (["missing_text@p1"], ["missing_text@p3"]))

    def test_without_the_source_findings_stay(self):
        r = record([finding("missing_text@p1", ["a"])])
        D.check(r, None, Path("."))
        self.assertEqual([f["id"] for f in r["findings"]], ["missing_text@p1"])

    def test_a_renamed_source_is_found_beside_the_folder(self):
        """Zotero renamed the PDF after the parse (2026-11-06: "Kim 等 - 2024 …" became "Kim et al. - 2024 …"):
        the copy package take puts beside the folder is the source, when its bytes are the record's."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "paper.pdf").write_bytes(b"%PDF-1.4 the parsed bytes")
            r = {"source": {"kind": "pdf", "file": "paper.pdf", "path": str(tmp / "gone" / "old name.pdf"),
                            "sha256": D.sha256_of([tmp / "paper.pdf"])}}
            self.assertEqual(D.source_of(r, folder=tmp / "paper")["path"], tmp / "paper.pdf")
            self.assertIsNone(D.source_of(r), "no folder: nothing to look beside")
            (tmp / "paper.pdf").write_bytes(b"%PDF-1.4 other bytes")
            self.assertIsNone(D.source_of(r, folder=tmp / "paper"), "other bytes: not the source")


class Migrate(unittest.TestCase):
    def test_edits_follow_their_text(self):
        old = record()
        D.commit(old, D.render_text(old)[0].replace("after the formula", "following the formula"))
        old["findings"] = [finding("missing_text@p1", ["x"], "ok", why="label", seen=["x"])]
        new = json.loads((FIXTURES / "synthetic.raw.json").read_text(encoding="utf-8"))
        # the new parse numbers the page differently: the paragraph is block 12 now
        b = next(b for b in new["blocks"] if b["id"] == "p1-11")
        b["id"] = "p1-12"
        self.assertEqual(D.migrate(old, new), 1)
        self.assertEqual(next(b for b in new["blocks"] if b["id"] == "p1-12")["changes"][0]["now"], "following")
        self.assertEqual([f["id"] for f in new["findings"]], ["missing_text@p1"])


    def test_a_recut_figure_finds_its_panels_under_new_ids(self):
        old = record()
        D.set_figure(old, "p2-2", None, [40, 40, 570, 270], "the panel letters were outside")
        D.refine_figures(old)
        new = json.loads((FIXTURES / "synthetic.raw.json").read_text(encoding="utf-8"))
        for b in new["blocks"]:                        # the new parse numbers page 2's panels differently
            b["id"] = {"p2-2": "p2-12", "p2-4": "p2-14"}.get(b["id"], b["id"])
        D.migrate(old, new)
        D.refine_figures(new)
        page2 = [f for f in D.figures_view(new) if f["page"] == 2]
        self.assertEqual([(f["id"], f["members"]) for f in page2], [("p2-2", ["p2-12", "p2-14"])])


class Figures(unittest.TestCase):
    def test_new_figure_on_a_page(self):
        r = record()
        ident = D.set_figure(r, None, 3, [50, 260, 560, 350], "the parse read it as text")
        self.assertEqual(ident, "p3-cut1")
        fig = next(f for f in r["figures"] if f["id"] == ident)
        self.assertEqual(D.fold_figure(fig)["box"], [100, 520, 1120, 700])

    def test_a_figure_cut_over_text_alone_has_its_image_line(self):
        # 2026-11, USRMamba p.9: figures cut from a crop of four held the model's labels but no image block
        r = record()
        ident = D.set_figure(r, None, 5, [45, 80, 565, 155], "a legend and a list drawn as text")
        D.refine_figures(r)
        text = D.render_text(r)[0]
        part = text.split(f"<!-- figure {ident} -->")[1].split(f"<!-- end figure {ident} -->")[0]
        self.assertIn(f"![](imgs/{ident}.png)", part)
        self.assertIn("Arrow indicates", part)
        self.assertIn("1 Intro", part)
        # a Markdown written in layout 3 had no image line there: edited and committed, the figure stays shown
        old = D.render_text(r, 3)[0]
        self.assertNotIn(f"imgs/{ident}.png", old)
        edited = old.replace("A page after a gap", "A page after the gap")
        hidden = copy.deepcopy(r)                                  # read as layout 4, the missing line is a deletion
        D.commit(hidden, edited.replace("render=3 ", "render=4 "))
        self.assertTrue(D.fold_figure(next(f for f in hidden["figures"] if f["id"] == ident))["hidden"])
        D.commit(r, edited)
        self.assertFalse(D.fold_figure(next(f for f in r["figures"] if f["id"] == ident))["hidden"])
        self.assertIn(f"![](imgs/{ident}.png)", D.render_text(r)[0])

    def test_new_blocks_and_new_figures_never_share_an_id(self):
        # 2026-11, CycleGAN p.7: a figure cut on the page and the caption restored for it were both p7-n1
        r = record()
        r["figures"].append({"id": "p3-n1", "image": "imgs/p3-n1.png",       # a figure cut before figures had their own ids
                             "changes": [{"by": "agent", "box": [100, 720, 1120, 780], "members": []}]})
        D.commit(r, D.render_text(r)[0].replace("reference [1].\n", "reference [1].\n\nA dropped line.\n"))
        self.assertEqual([b["id"] for b in r["blocks"] if b.get("added")], ["p3-n2"])
        self.assertEqual(D.set_figure(r, None, 3, [50, 360, 560, 380], ""), "p3-cut1")

    def test_recut_takes_the_panels_inside(self):
        r = record()
        D.set_figure(r, "p5-5", None, [40, 220, 310, 410], "")
        self.assertEqual(D.fold_figure(next(f for f in r["figures"] if f["id"] == "p5-5"))["members"], ["p5-5"])


class Lock(unittest.TestCase):
    def test_one_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            with D.locked(Path(tmp)):
                with self.assertRaises(D.Stop) as held:
                    with D.locked(Path(tmp)):
                        pass
                self.assertEqual((held.exception.code, held.exception.exit), ("locked", 2))
            with D.locked(Path(tmp)):
                pass


class Commands(unittest.TestCase):
    """The words on a parse folder, as ocr.py runs them: their lines, exit codes and what they leave on disk. The
    fixture record's source path is empty: it has no source, unless a test gives it a blank PDF."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.folder = self.dir / "paper"
        self.folder.mkdir()
        (self.folder / "paper.json").write_text(json.dumps(record()), encoding="utf-8")
        shutil.copy(FIXTURES / "synthetic.md", self.folder / "paper.md")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_word(self, *argv):
        """-> (exit code, stdout, stderr)"""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = D.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def files(self):
        return {p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}

    def edit_markdown(self, old, new):
        md = self.folder / "paper.md"
        md.write_text(md.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

    def with_source(self):
        """A blank five-page Letter PDF as the record's source."""
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument.new()
        for _ in range(5):
            pdf.new_page(612, 792)
        path = self.dir / "paper.pdf"
        pdf.save(str(path))
        r = json.loads((self.folder / "paper.json").read_text(encoding="utf-8"))
        r["source"].update(path=str(path), sha256=D.sha256_of([path]))
        (self.folder / "paper.json").write_text(json.dumps(r), encoding="utf-8")

    def test_findings_and_show_read_only_and_warn_of_uncommitted_edits(self):
        r = record([finding("missing_text@p1", ["the right column ends here"]),
                    finding("table_mismatch@p2-9", ["0.95"], "unresolved", why="illegible"),
                    finding("no_text_layer", status="ok", why="a scan")])
        (self.folder / "paper.json").write_text(json.dumps(r), encoding="utf-8")
        self.edit_markdown("after the formula", "following the formula")
        before = self.files()
        code, out, err = self.run_word("findings", str(self.folder))
        self.assertEqual(code, 1, err)
        self.assertEqual([json.loads(line) for line in out.splitlines()], [
            {"id": "missing_text@p1", "status": "open", "page": 1, "note": "the right column ends here"},
            {"id": "table_mismatch@p2-9", "status": "unresolved", "page": 2, "note": "illegible"}])
        self.assertIn("not committed", err)
        self.assertEqual(json.loads(err.splitlines()[-1]),
                         {"summary": {"total": 3, "open": 1, "unresolved": 1, "ok": 1}})
        code, out, _ = self.run_word("findings", "-a", str(self.folder))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.splitlines()[-1]), {"id": "no_text_layer", "status": "ok", "page": None,
                                                            "note": "a scan"})
        code, out, err = self.run_word("show", str(self.folder), "p3")
        self.assertEqual(code, 0, err)
        self.assertIn("p3-5", out)
        self.assertIn("not committed", err)
        self.assertEqual(self.files(), before)            # nothing recorded, the Markdown untouched

    def test_findings_pass_with_only_verdicts_or_no_findings(self):
        for found in ([finding("no_text_layer", status="ok", why="a scan"),
                       finding("table_mismatch@p2-9", ["0.95"], "unresolved", why="illegible")], []):
            with self.subTest(findings=found):
                (self.folder / "paper.json").write_text(json.dumps(record(found)), encoding="utf-8")
                code, out, err = self.run_word("findings", str(self.folder))
                self.assertEqual((code, err), (0, ""))
                self.assertEqual([json.loads(line) for line in out.splitlines()],
                                 [{"id": "table_mismatch@p2-9", "status": "unresolved", "page": 2,
                                   "note": "illegible"}] if found else [])
                code, out, err = self.run_word("findings", "-a", str(self.folder))
                self.assertEqual((code, err, len(out.splitlines())), (0, "", len(found)))

    def test_usage_errors_name_the_way(self):
        code, _, err = self.run_word("show", str(self.folder))
        self.assertEqual((code, json.loads(err.splitlines()[-1])["code"]), (2, "usage"))
        self.assertIn(f"findings {self.folder}", json.loads(err.splitlines()[-1])["hint"])
        code, _, err = self.run_word("cut", str(self.folder), "p3", "--box", "50", "260", "560", "350")
        self.assertEqual((code, json.loads(err.splitlines()[-1])["hint"]), (2, "Write the box as one value: --box 50,260,560,350."))

    def test_commit_records_then_has_nothing_to_commit(self):
        self.edit_markdown("after the formula", "following the formula")
        code, out, err = self.run_word("commit", str(self.folder))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"folder": str(self.folder.resolve()), "code": "ok",
                                           "recorded": ["p1-11: 'after' -> 'following'"]})
        code, out, err = self.run_word("commit", str(self.folder))
        self.assertEqual((code, json.loads(out)["code"], json.loads(out)["reason"]), (0, "skipped", "nothing_to_commit"))

    def test_a_folders_problem_is_its_own_line(self):
        self.edit_markdown("<!-- page 3 -->", "<!-- page 4 -->")
        before = self.files()
        code, out, err = self.run_word("commit", str(self.folder))
        line = json.loads(out)
        self.assertEqual((code, err, line["folder"], line["code"]), (1, "", str(self.folder.resolve()), "edit_refused"))
        self.assertIn("<!-- page 3 -->", line["detail"])
        self.assertEqual(self.files(), before)
        code, out, _ = self.run_word("findings", str(self.dir / "gone"))
        self.assertEqual((code, json.loads(out)["code"]), (1, "file_not_found"))

    def test_cut_a_new_figure_on_a_page_with_a_box_in_one_value(self):
        self.with_source()
        code, out, err = self.run_word("cut", str(self.folder), "p3", "--box", "50,260,560,350", "--reason", "read as text")
        self.assertEqual(code, 0, err)
        line = json.loads(out)
        self.assertEqual((line["code"], line["figure"], Path(line["image"]).is_file()), ("ok", "p3-cut1", True))
        r = json.loads((self.folder / "paper.json").read_text(encoding="utf-8"))
        fig = next(f for f in r["figures"] if f["id"] == "p3-cut1")
        self.assertEqual((D.fold_figure(fig)["box"], fig["changes"][-1]["why"]), ([100, 520, 1120, 700], "read as text"))
        code, out, _ = self.run_word("cut", str(self.folder), "p3-2", "--box", "50,260,560,350")
        self.assertEqual((code, json.loads(out)["code"]), (1, "not_found"))
        self.assertIn("cut DIR p3 --box", json.loads(out)["hint"])

    def test_a_named_caption_gives_its_figure_its_number(self):
        """2026-11, CycleGAN p.7: Figure 7 and Figure 8 above one caption, Figure 8's. Cut apart, both were paired with
        it; the agent restores Figure 7's caption from the text layer and names it."""
        self.with_source()
        self.edit_markdown("A chart of accuracy.\n", "A chart of accuracy.\n\nFig. 2. The chart alone.\n")
        code, out, err = self.run_word("commit", str(self.folder))
        self.assertEqual((code, json.loads(out)["recorded"]), (0, ["p2-n1: new text after p2-6"]), err)
        self.run_word("cut", str(self.folder), "p2-2", "--box", "50,60,280,250")
        code, out, err = self.run_word("cut", str(self.folder), "p2", "--box", "310,60,560,250")
        line = json.loads(out)
        self.assertEqual((code, line["figure"], line["caption"], line["number"]), (0, "p2-cut1", "p2-6", "Fig. 1"), err)
        code, out, err = self.run_word("cut", str(self.folder), "p2-cut1", "--caption", "p2-n1")
        line = json.loads(out)
        self.assertEqual((code, line["caption"], line["number"]), (0, "p2-n1", "Fig. 2"), err)
        code, out, err = self.run_word("objects", str(self.folder))
        self.assertEqual({o["id"]: o["key"] for o in map(json.loads, out.splitlines()) if o["kind"] == "figure"},
                         {"p2-2": "fig:1", "p2-cut1": "fig:2", "p5-5": None}, err)
        text = (self.folder / "paper.md").read_text(encoding="utf-8")
        self.assertIn("![Fig. 1](imgs/p2-2.png)", text)
        self.assertIn("![Fig. 2](imgs/p2-cut1.png)", text)
        code, out, _ = self.run_word("cut", str(self.folder), "p2-cut1", "--caption", "p2-n9")
        self.assertEqual((code, json.loads(out)["code"]), (1, "not_found"))
        code, _, err = self.run_word("cut", str(self.folder), "p2-cut1")
        self.assertEqual((code, json.loads(err.splitlines()[-1])["code"]), (2, "usage"))

    def test_findings_say_when_older_code_made_them(self):
        """2026-11, M2Trans: a package checked by checks 5 showed missing_numbers that the checks of then made and
        those of now do not; they vanished at the first cut."""
        r = record([finding("missing_numbers@p1", ["21,202"])])
        r["run"]["versions"] = {**D.versions(), "checks": D.checks.VERSION - 1}
        (self.folder / "paper.json").write_text(json.dumps(r), encoding="utf-8")
        code, _, err = self.run_word("findings", str(self.folder))
        self.assertEqual(code, 1)
        self.assertIn(f"checks {D.checks.VERSION - 1}, now {D.checks.VERSION}", err)
        self.assertIn(f"render {self.folder.resolve()}", err)
        r["run"]["versions"] = D.versions()
        (self.folder / "paper.json").write_text(json.dumps(r), encoding="utf-8")
        self.assertNotIn("older code", self.run_word("findings", str(self.folder))[2])


@unittest.skipUnless(ENGINE, "needs the paddleocr tool environment: uv run tests/test_doc.py --engine")
class Engine(unittest.TestCase):
    def test_processing_gives_the_fixtures(self):
        r = json.loads((FIXTURES / "synthetic.raw.json").read_text(encoding="utf-8"))
        D.process(r)
        D.check(r, None, Path("."))
        r["run"]["versions"] = PROCESSED["run"]["versions"]
        self.assertEqual(json.loads(json.dumps(r)), PROCESSED)
        self.assertEqual(D.render_text(r)[0], (FIXTURES / "synthetic.md").read_text(encoding="utf-8"))

    def test_markdown_rules_are_paddleocrs(self):
        from paddlex.inference.common.result.converter.markdown_converter import MarkdownConverter
        from paddlex.inference.common.result.converter.markdown_format_funcs import (
            build_handle_funcs_dict, format_chart2html_table, format_image_plain, simplify_table)
        from paddlex.inference.pipelines.paddleocr_vl.result import PaddleOCRVLBlock
        image = lambda b: format_image_plain(b, show_ocr_content=False)
        handlers = build_handle_funcs_dict(text_func=lambda b: b.content, image_func=image, chart_func=image,
                                           table_func=lambda b: simplify_table("\n" + b.content),
                                           formula_func=lambda b: b.content, seal_func=image)
        for label in D.IGNORED:
            handlers.pop(label, None)
        texts = ["Plain text\nwith a line break\n\nand a paragraph.", "1.2 Methods.", "IV. Results", "（一）总则",
                 "Abstract We test.", "References\n[1] A.", "<html><body><table><tr><td>1</td></tr></table></body></html>",
                 " $$ x^2 $$ ", "Algorithm 1\n1: do\n", "1 Intro\n2 Methods-\nmore", "a|b\n1|2"]
        for label in sorted(set(handlers) - {"image", "chart", "seal", "header_image", "footer_image"}):
            for t in texts:
                for level in (None, 2):
                    blk = PaddleOCRVLBlock(label=label, bbox=[0, 0, 1, 1], content=t)
                    if level is not None:
                        blk.title_level = level
                    mine = D.format_block({"label": label, "text": t, "level": level}, {})
                    self.assertEqual(mine, handlers[label](blk), (label, t, level))
        self.assertEqual(D.format_block({"label": "chart", "text": "a|b\n1|2", "level": None}, {"charts": True}),
                         format_chart2html_table(PaddleOCRVLBlock(label="chart", bbox=[0, 0, 1, 1], content="a|b\n1|2")))
        # a page without figures: PaddleOCR's own join of the same blocks in the same order
        for page in (1, 3):
            view = [b for b in D.blocks_view(PROCESSED) if b["page"] == page]
            order, numbers = D.page_order(view)
            blocks = []
            for b in order:
                if "merged_into" in b:
                    continue
                blk = PaddleOCRVLBlock(label=b["label"], bbox=b["box"], content=b["text"])
                if b["level"] is not None:
                    blk.title_level = b["level"]
                blocks.append(blk)
            theirs = MarkdownConverter.convert(blocks, handle_funcs_dict=handlers, show_formula_number=True)["markdown_texts"]
            import re
            theirs = re.sub(r"\n{3,}", "\n\n", theirs).strip()
            ours = D.render_text(PROCESSED)[0].split(f"<!-- page {page} -->\n\n")[1].split("\n\n<!-- page ")[0]
            ours = "\n\n".join(x for x in ours.split("\n\n") if not x.startswith("<!-- table "))
            self.assertEqual(ours, theirs, page)


if __name__ == "__main__":
    unittest.main()
