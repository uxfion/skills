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
import copy
import importlib.util
import json
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
        self.assertTrue(first.startswith("<!-- paddleocr render=3 source=synthetic.pdf "))
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

    def test_a_line_without_a_blank_joins_its_paragraph(self):
        r = record()
        self.edit(r, "reference [1].\n", "reference [1].\nAnd its second line.\n")
        self.assertIn("And its second line.", D.fold(next(b for b in r["blocks"] if b["id"] == "p3-2"))["text"])

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
        for old, new in (("<!-- page 3 -->", "<!-- page 4 -->"), ("<!-- end figure p2-2 -->\n", ""),
                         ("A figure without", "![x](imgs/mine.png)\nA figure without")):
            with self.assertRaises(D.Refused):
                self.edit(record(), old, new)

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


class Figures(unittest.TestCase):
    def test_new_figure_on_a_page(self):
        r = record()
        ident = D.set_figure(r, None, 3, [50, 260, 560, 350], "the parse read it as text")
        self.assertEqual(ident, "p3-n1")
        fig = next(f for f in r["figures"] if f["id"] == ident)
        self.assertEqual(D.fold_figure(fig)["box"], [100, 520, 1120, 700])

    def test_recut_takes_the_panels_inside(self):
        r = record()
        D.set_figure(r, "p5-5", None, [40, 220, 310, 410], "")
        self.assertEqual(D.fold_figure(next(f for f in r["figures"] if f["id"] == "p5-5"))["members"], ["p5-5"])


class Lock(unittest.TestCase):
    def test_one_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            with D.locked(Path(tmp)):
                with self.assertRaises(D.Refused):
                    with D.locked(Path(tmp)):
                        pass
            with D.locked(Path(tmp)):
                pass


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
