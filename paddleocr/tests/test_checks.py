# /// script
# requires-python = ">=3.9"
# dependencies = ["pypdfium2"]
# ///
"""Tests for scripts/checks.py: tokens, the text-layer check, its findings and the PDF text layer (no GPU needed)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import checks as C  # noqa: E402

PARAGRAPH = ("The diffusion model aligns the target image to match the style of the source domain while "
             "preserving the original spatial context of every scan in the handheld device collection.")
SECOND = ("Each annotator labelled the lesion boundaries twice on separate days so that we could measure how "
          "consistent the manual reference segmentations remained over the whole study period.")


def chars(text, x=5000.0, y=5000.0):
    """Text-layer characters [(ch, x, y)], all at one point; the default lies outside every block box."""
    return [(ch, x, y) for ch in text]


def block(i, page, label, text, **extra):
    return {"id": f"p{page}-{i}", "page": page, "label": label, "text": text, "box": [0, 0, 10, 10], **extra}


def ids(findings, code=None):
    return [f["id"] for f in findings if code in (None, f["code"])]


class Tokens(unittest.TestCase):
    def test_text_layer_hyphenation_joined(self):
        self.assertEqual(C.tokens("annota" + chr(0xFFFE) + "tions are", layer=True), ["annotations", "are"])
        self.assertEqual(C.tokens("adap-\r\ntation", layer=True), ["adaptation"])

    def test_parsed_html_and_latex_stripped(self):
        self.assertEqual(C.tokens("<td>Spine</td><td>34,248</td> $\\mathbb{E}$ ok"), ["spine", "34,248", "ok"])

    def test_ligatures_and_case(self):
        self.assertEqual(C.tokens("Ef" + chr(0xFB01) + "cient"), ["efficient"])

    def test_cjk_characters_are_tokens(self):
        self.assertEqual(C.tokens("超声图像 test"), ["超", "声", "图", "像", "test"])

    def test_single_letters_dropped(self):
        self.assertEqual(C.tokens("a x b model"), ["model"])

    def test_greek_is_math(self):
        nu, gamma = chr(0x3BD), chr(0x3B3)
        self.assertEqual(C.tokens(f"where {nu}S = 2{gamma}S and", layer=True), ["where", "2", "and"])

    def test_number_ranges_not_joined(self):
        self.assertEqual(C.tokens("ICASSP 2023-\n2023 IEEE", layer=True), ["icassp", "2023", "2023", "ieee"])
        self.assertEqual(C.tokens("[-15,5] and 34,248"), ["15", "5", "and", "34,248"])

    def test_inline_math_glued_like_a_text_layer(self):
        glued = C.tokens(C.glue_math("yields $ o_k = \\mathcal{T}_p(a_k) $, where $ H_{k+1} $ and "
                                     "$ D_{\\mathrm{KL}}(q_n \\| p_n) $ or $ \\pi_\\theta(\\cdot \\mid H_k) $"))
        self.assertEqual(glued, ["yields", "ok", "tp", "ak", "where", "hk", "1", "and", "dkl", "qn", "pn", "or", "hk"])
        self.assertEqual(C.tokens("yields ok = Tp (ak ) where Hk+1 and DKL (qn ‖pn ) or πθ (· | Hk )",
                                  layer=True), glued)

    def test_quote_reads_as_written(self):
        layer = "The Ef" + chr(0xFB01) + "cient  adap-\ntation of " + chr(0x3BD) + "S, as in Fig. 3."
        text, matches = C.token_matches(layer, layer=True)
        self.assertEqual(C.quote(text, matches, 1, len(matches)), "Efficient adaptation of νS, as in Fig. 3")
        parsed = "Spine <b>34,248</b> $\\mathbb{E}$ scans"
        text, matches = C.token_matches(parsed)
        self.assertEqual(C.quote(parsed, matches, 0, 3), parsed)


class TextLayerCheck(unittest.TestCase):
    def test_full_match(self):
        toks = C.tokens(PARAGRAPH)
        coverage, runs = C.missing_runs(toks, set(C.ngrams(toks)))
        self.assertEqual((coverage, runs), (1.0, []))

    def test_missing_run_found(self):
        toks = C.tokens(PARAGRAPH)
        kept = toks[:5] + toks[-3:]
        coverage, runs = C.missing_runs(toks, set(C.ngrams(kept)))
        self.assertLess(coverage, 0.5)
        self.assertEqual(len(runs), 1)
        start, end = runs[0]
        self.assertIn("preserving", toks[start:end])

    def test_short_gap_tolerated(self):
        toks = C.tokens(PARAGRAPH)
        parsed = list(toks)
        parsed[8] = "xyz"                      # one misread word costs three trigrams, not a finding
        self.assertEqual(C.missing_runs(toks, set(C.ngrams(parsed)))[1], [])

    def test_document_omission_and_merge_placeholder(self):
        blocks = [block(0, 1, "text", PARAGRAPH[:60]), block(1, 1, "text", "", merged_into="p1-0"),
                  block(2, 2, "text", "Short page two text that is fine and complete as it stands here.")]
        coverage, findings = C.check_document(blocks, {1: chars(PARAGRAPH), 2: chars(blocks[2]["text"])})
        self.assertEqual(ids(findings), ["missing_text@p1"])
        self.assertEqual(findings[0]["page"], 1)
        self.assertEqual(coverage[2], 1.0)

    def test_text_moved_to_neighbouring_page_counts(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 2, "text", "", merged_into="p1-0")]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH[:80]), 2: chars(PARAGRAPH[80:])})
        self.assertEqual(findings, [])

    def test_inline_math_either_way(self):
        parsed = "Given a source image $ x_s $, the forward process adds random noise to the image many times over."
        layer = "Given a source image xs, the forward process adds random noise to the image many times over."
        _, findings = C.check_document([block(0, 1, "text", parsed)], {1: chars(layer)})
        self.assertEqual(findings, [])

    def test_text_inside_figures_and_formulas_not_checked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 1, "chart", "", box=[0, 0, 100, 100]),
                  block(2, 1, "display_formula", "$$ a $$", box=[0, 200, 100, 300])]
        layer = chars(PARAGRAPH) + chars("\nTraining loss validation loss epochs 10 20 30 40 50\n", 50, 50) \
            + chars("\nL total equals lambda times the sum of 12.5 terms\n", 50, 250)
        _, findings = C.check_document(blocks, {1: layer})
        self.assertEqual(findings, [])

    def test_missing_numbers(self):
        parsed = "The proposed model reached an accuracy of 70.90 percent on the held out test set."
        layer = "The proposed model reached an accuracy of 70.99 percent on the held out test set.\n0.15\n"
        _, findings = C.check_document([block(0, 1, "text", parsed)], {1: chars(layer)})
        self.assertEqual([(f["id"], f["items"]) for f in findings], [("missing_numbers@p1", ["70.99"])])

    def test_table_column_lost(self):
        table_layer = "\nModel Dice IOU HD ASD\nUNet 0.92 0.86 16.67 3.04\nResUNet 0.82 0.71 88.03 10.94\n"
        full = "<table><tr><td>Model</td><td>Dice</td><td>IOU</td><td>HD</td><td>ASD</td></tr>" \
               "<tr><td>UNet</td><td>0.92</td><td>0.86</td><td>16.67</td><td>3.04</td></tr>" \
               "<tr><td>ResUNet</td><td>0.82</td><td>0.71</td><td>88.03</td><td>10.94</td></tr></table>"
        lost = full.replace("<td>ASD</td>", "").replace("<td>3.04</td>", "").replace("<td>10.94</td>", "")
        for text, found in ((full, []), (lost, ["table_mismatch@p1-1"])):
            blocks = [block(0, 1, "text", PARAGRAPH), block(1, 1, "table", text, box=[0, 0, 100, 100])]
            _, findings = C.check_document(blocks, {1: chars(PARAGRAPH) + chars(table_layer, 50, 50)})
            self.assertEqual(ids(findings, "table_mismatch"), found)
        self.assertEqual(findings[-1]["items"], ["asd", "3.04", "10.94"])
        self.assertEqual(findings[-1]["block"], "p1-1")

    def test_table_continued_from_the_page_before(self):
        first = "\nModel Dice IOU HD ASD\nUNet 0.92 0.86 16.67 3.04\n"
        rest = "\nResUNet 0.82 0.71 88.03 10.94\nAttUNet 0.88 0.79 20.15 4.12\n"
        whole = "<table><tr><td>Model</td><td>Dice</td><td>IOU</td><td>HD</td><td>ASD</td></tr>" \
                "<tr><td>UNet</td><td>0.92</td><td>0.86</td><td>16.67</td><td>3.04</td></tr>" \
                "<tr><td>ResUNet</td><td>0.82</td><td>0.71</td><td>88.03</td><td>10.94</td></tr>" \
                "<tr><td>AttUNet</td><td>0.88</td><td>0.79</td><td>20.15</td><td>4.12</td></tr></table>"
        cut = whole.replace("<td>20.15</td><td>4.12</td>", "<td></td>")
        for text, found in ((whole, []), (cut, ["table_mismatch@p2-0"])):
            blocks = [block(0, 1, "table", text, box=[0, 0, 100, 100]),
                      block(0, 2, "table", "", box=[0, 0, 100, 100], merged_into="p1-0")]
            _, findings = C.check_document(blocks, {1: chars(first, 50, 50), 2: chars(rest, 50, 50)})
            self.assertEqual(ids(findings), found)

    def test_image_table_flagged_unchecked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 1, "table", "<table></table>", box=[0, 0, 100, 100]),
                  block(2, 1, "table", "", box=[0, 200, 100, 300], merged_into="p1-1")]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH)})
        self.assertEqual([{k: v for k, v in f.items() if k != "detail"} for f in findings],
                         [{"id": "unchecked_table@p1-1", "code": "unchecked_table", "page": 1, "block": "p1-1",
                           "items": []}])
        self.assertTrue(findings[0]["detail"])

    def test_figure_labels_beside_a_chart_not_checked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 1, "chart", "", box=[100, 100, 200, 200])]
        ticks = chars("\n0.2 0.4 0.6 0.8 1.0 accuracy over training epochs 10 20 30\n", 150, 210)
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH) + ticks})
        self.assertEqual(findings, [])

    def test_text_block_inside_figure_zone_still_checked(self):
        caption = "Figure two shows the training loss curves of every model trained in our experiments."
        blocks = [block(0, 1, "figure_title", caption[:40], box=[100, 205, 300, 215]),
                  block(1, 1, "chart", "", box=[100, 100, 300, 200])]
        _, findings = C.check_document(blocks, {1: chars(caption, 200, 210)})
        self.assertEqual(ids(findings), ["missing_text@p1"])

    def test_block_without_a_box_counts_for_coverage(self):
        # An agent restores a missing line as a block of its own, with no box: its text closes the run.
        blocks = [block(0, 1, "text", PARAGRAPH), block("n1", 1, "text", SECOND, box=None)]
        coverage, findings = C.check_document(blocks, {1: chars(PARAGRAPH + " " + SECOND)})
        self.assertEqual((coverage, findings), ({1: 1.0}, []))

    def test_layer_text_blanks_whole_words(self):
        layer = chars("keep ") + [("c", 5, 5), ("u", 5, 5), ("t", 5000, 5000)] + chars(" word")
        self.assertEqual(C.layer_text(layer, lambda x, y: x > 2000), "keep     word")   # "cut" centres at x 1670

    def test_empty_page_and_no_text_layer(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 2, "header", "IEEE TRANSACTIONS"),
                  block(2, 3, "image", "")]
        coverage, findings = C.check_document(blocks, {1: None, 2: None, 3: None})
        self.assertIn("empty_page@p2", ids(findings))
        self.assertNotIn("empty_page@p3", ids(findings))
        self.assertIn({"id": "no_text_layer", "code": "no_text_layer", "items": ["1", "2", "3"]},
                      [{k: v for k, v in f.items() if k != "detail"} for f in findings])
        self.assertEqual(coverage, {1: None, 2: None, 3: None})

    def test_repetition(self):
        looped = "The result is shown. " + "the same phrase again " * 8
        blocks = [block(0, 1, "text", looped), block(1, 1, "table", "<td>0</td>" * 40)]
        _, findings = C.check_document(blocks, {1: None})
        self.assertEqual(ids(findings, "repetition"), ["repetition@p1-0"])
        self.assertEqual(findings[0]["items"], [])
        self.assertIn("the same phrase again", findings[0]["detail"])
        self.assertIsNone(C.repetition(PARAGRAPH))

    def test_author_line_cycling_is_a_loop(self):
        # 2026-10: a 23-author line came out as 8,857 characters, the names cycling with small changes, no exact repeat
        names = ["Lingyi Xu", "Zhen Gao", "Xiao Li", "Yuan Shen", "Guisen Li", "Li Wang", "Jicheng Lv", "Zhao Qiao"]
        looped = ", ".join(f"{n} $ ^{{{i % 3 + 1}}} $" for k in range(12) for i, n in enumerate(names[k % 2:]))
        self.assertIsNone(C.REPEAT_RE.search(looped))
        self.assertIn("word trigrams distinct", C.repetition(looped))
        authors = ", ".join(f"{n} $ ^{{{i}}} $" for i, n in enumerate(names * 2))   # every name twice: not a loop
        self.assertIsNone(C.repetition(authors + " " + PARAGRAPH))

    def test_formula_dense_paragraph_passes(self):
        # 2026-10: a text layer glues subscripts to letters ("Tp (ak )"); dropping or splitting the LaTeX left
        # missing_text and extra_text on correctly parsed paragraphs
        parsed = ("At round $ k $ the policy emits an action from its history; a tool request yields "
                  "$ o_k = \\mathcal{T}_p(a_k) = (e_k, X_k) $, where $ \\mathcal{T}_p $ returns text $ e_k $ and "
                  "images $ X_k $; and $ H_{k+1} = H_k \\oplus (a_k, o_k) $ appends them in order. An episode of "
                  "$ M $ assistant turns ends with the parsed answer.")
        layer = ("At round k the policy emits an action from its history; a tool request yields ok = Tp (ak ) = "
                 "(ek , Xk ), where Tp returns text ek and images Xk ; and Hk+1 = Hk ⊕ (ak , ok ) appends them in "
                 "order. An episode of M assistant turns ends with the parsed answer.")
        blocks = [block(0, 1, "text", parsed, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(layer, 50, 50)})
        self.assertEqual(findings, [])


class ExtraText(unittest.TestCase):
    INVENTED = " and the impact of different types of data sources on the performance of the final model."

    def test_invented_continuation_flagged(self):
        blocks = [block(0, 1, "text", PARAGRAPH + self.INVENTED, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertEqual(ids(findings), ["extra_text@p1-0"])
        self.assertEqual(findings[0]["items"], ["device collection. and the impact of different types of data sources "
                                                "on the performance of the final model"])

    def test_runs_in_one_block_are_one_finding(self):
        half = PARAGRAPH.index("preserving")
        aside = "we also discuss several unrelated topics such as cooking fresh pasta at home every evening "
        parsed = PARAGRAPH[:half] + aside + PARAGRAPH[half:] + self.INVENTED
        blocks = [block(0, 1, "text", parsed, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertEqual(ids(findings), ["extra_text@p1-0"])
        self.assertEqual(len(findings[0]["items"]), 2)
        self.assertIn("cooking fresh pasta", findings[0]["items"][0])
        self.assertTrue(findings[0]["items"][1].endswith("of the final model"))

    def test_run_quoted_with_its_math(self):
        parsed = PARAGRAPH + " We then sample $ x_t $ from the prior and refine it with twenty further denoising steps."
        blocks = [block(0, 1, "text", parsed, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertIn("We then sample $ x_t $ from the prior", findings[0]["items"][0])

    def test_text_read_from_an_image_not_flagged(self):
        blocks = [block(0, 1, "text", PARAGRAPH, box=[0, 0, 100, 100]),
                  block(1, 1, "text", "Prompt: the refractive medium is turbid and mild retinal edema is visible.",
                        box=[200, 200, 300, 300])]
        _, findings = C.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertEqual(findings, [])

    def test_foreign_script_flagged(self):
        parsed = ("Let $ u_{j,1:N_j} $年第 $ j $个signal messages, and the indexing assistant tokens "
                  "of the rollout are serialized in order.")
        layer = "Let uj,1:Nj be the j-th rollout's assistant messages, and the indexing assistant tokens of the rollout are serialized in order."
        blocks = [block(0, 1, "text", parsed, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(layer, 50, 50)})
        stray = [f for f in findings if f["code"] == "foreign_script"]
        self.assertEqual(ids(stray), ["foreign_script@p1-0"])
        self.assertEqual(len(stray[0]["items"]), 1)
        self.assertIn("年第 $ j $个signal", stray[0]["items"][0])
        _, findings = C.check_document(blocks, {1: chars(layer + " 年第个", 50, 50)})   # characters the source has
        self.assertNotIn("foreign_script", [f["code"] for f in findings])

    def test_superscript_numbers_ignored(self):
        parsed = "Chenlin Meng$^{1}$, Yutong He$^{1}$, Yang Song$^{1}$, Jiaming Song$^{1}$, Jiajun Wu$^{1}$ and Jun-Yan Zhu$^{2}$"
        layer = "Chenlin Meng1 Yutong He1 Yang Song1 Jiaming Song1 Jiajun Wu1 Jun-Yan Zhu2 Stefano Ermon"
        blocks = [block(0, 1, "text", parsed, box=[0, 0, 100, 100])]
        _, findings = C.check_document(blocks, {1: chars(layer, 50, 50)})
        self.assertEqual(findings, [])


class LineNumbers(unittest.TestCase):
    @staticmethod
    def page(first, x, lines=12, step=1):
        """A text layer of `lines` lines, each led by a number at x: first, first + step, ..."""
        out = []
        for k in range(lines):
            y = 100 + 30 * k
            out += chars(str(first + step * k), x, y) + [(" ", 0.0, 0.0)] + chars("text of the line", 500, y) + [("\n", 0.0, 0.0)]
        return out

    def stripped(self, layer):
        idx = C.line_number_chars(layer, 1200)
        return "".join(c[0] for k, c in enumerate(layer) if k not in idx).split()

    def test_margin_column_counting_up_is_stripped(self):
        for first, x in ((88, 133), (1188, 164), (54, 1100)):       # left edge, 2-4 digits; right edge
            self.assertNotIn(str(first + 3), self.stripped(self.page(first, x)), msg=(first, x))
            self.assertIn("text", self.stripped(self.page(first, x)))

    def test_other_number_columns_kept(self):
        self.assertIn("4", self.stripped(self.page(1, 600)))            # a row index mid-page, in a table
        self.assertIn("94", self.stripped(self.page(88, 133, step=2)))  # not counting up by one
        self.assertIn("91", self.stripped(self.page(88, 133, lines=6))) # too short a run


class NoLayerChecks(unittest.TestCase):
    def test_shifted_columns_leave_one_empty(self):
        grid = ("<table><tr><td>Method</td><td>Image</td><td>C</td><td>CNR</td><td>gCNR</td></tr>"
                "<tr><td>DAS</td><td>-22.042</td><td>0.784</td><td>0.929</td><td></td></tr>"
                "<tr><td>CF</td><td>-35.018</td><td>0.355</td><td>0.821</td><td></td></tr></table>")
        self.assertEqual(C.empty_columns(grid), ["gCNR"])
        _, findings = C.check_document([block(0, 3, "table", grid)], {3: None})
        empty = [f for f in findings if f["code"] == "table_empty_column"]
        self.assertEqual([(f["id"], f["page"], f["block"], f["items"]) for f in empty],
                         [("table_empty_column@p3-0", 3, "p3-0", ["gCNR"])])

    def test_full_table_and_spacer_column_pass(self):
        table = ("<table><tr><td></td><td>A</td><td>B</td></tr><tr><td></td><td>1</td><td>2</td></tr>"
                 "<tr><td></td><td>3</td><td>4</td></tr></table>")
        self.assertEqual(C.empty_columns(table), [])


class FormulaNumbers(unittest.TestCase):
    def test_formula_number_gap(self):
        blocks = [block(0, 4, "formula_number", "(18)"), block(1, 4, "formula_number", "(20)"),
                  block(2, 9, "formula_number", "(31)")]
        self.assertEqual(C.formula_number_gaps(blocks),
                         [{"id": "formula_number_gap@p4", "code": "formula_number_gap", "page": 4, "items": ["(19)"],
                           "detail": "(19) between (18) and (20), page 4-4"}])
        _, findings = C.check_document(blocks, {4: None, 9: None})
        self.assertIn("formula_number_gap@p4", ids(findings))

    def test_tag_numbers_count(self):
        blocks = [block(0, 4, "display_formula", "$$ a = b \\tag{18} $$"), block(1, 4, "formula_number", "(20)")]
        self.assertEqual([f["items"] for f in C.formula_number_gaps(blocks)], [["(19)"]])
        added = block("n1", 4, "display_formula", "$$ c = d \\tag*{(19)} $$", box=None)   # the agent writes it in
        self.assertEqual(C.formula_number_gaps(blocks[:1] + [added] + blocks[1:]), [])

    def test_gaps_merge_on_the_page_before_them(self):
        blocks = [block(0, 5, "formula_number", "(1)"), block(1, 5, "formula_number", "(3)"),
                  block(0, 6, "formula_number", "(6)"), block(1, 6, "formula_number", "(7)"),
                  block(2, 6, "formula_number", "(9)")]
        self.assertEqual([(f["id"], f["items"]) for f in C.formula_number_gaps(blocks)],
                         [("formula_number_gap@p5", ["(2)", "(4)", "(5)"]), ("formula_number_gap@p6", ["(8)"])])
        self.assertEqual(C.formula_number_gaps(blocks)[0]["detail"],
                         "(2) between (1) and (3), page 5-5; (4) (5) between (3) and (6), page 5-6")


class Findings(unittest.TestCase):
    MISSING = ("Our Ef" + chr(0xFB01) + "cient  adap-\ntation, trained on 1,024 scans (Fig. 3), outperforms every "
               "baseline we tried.")

    def test_keys_by_object(self):
        looped = "The result is shown. " + "the same phrase again " * 8
        blocks = [block(0, 1, "text", looped), block(0, 2, "header", "IEEE")]
        _, findings = C.check_document(blocks, {1: None, 2: None})
        keys = {f["id"]: sorted(f) for f in findings}
        self.assertEqual(keys, {"empty_page@p2": ["code", "detail", "id", "items", "page"],
                                "repetition@p1-0": ["block", "code", "detail", "id", "items", "page"],
                                "no_text_layer": ["code", "detail", "id", "items"]})

    def test_missing_text_quotes_the_text_layer(self):
        _, findings = C.check_document([block(0, 1, "text", PARAGRAPH)], {1: chars(PARAGRAPH + " " + self.MISSING)})
        missing = [f for f in findings if f["code"] == "missing_text"]
        self.assertEqual([(f["id"], f["items"]) for f in missing],
                         [("missing_text@p1", ["device collection. Our Efficient adaptation, trained on 1,024 scans "
                                               "(Fig. 3), outperforms every baseline we tried"])])
        self.assertEqual(ids(findings), ["missing_text@p1", "low_coverage@p1", "missing_numbers@p1"])
        self.assertEqual(findings[2]["items"], ["1,024"])

    def test_runs_on_a_page_are_one_finding(self):
        layer = PARAGRAPH + " " + self.MISSING + " " + SECOND + " " + self.MISSING.replace("Our", "Their")
        _, findings = C.check_document([block(0, 1, "text", PARAGRAPH + " " + SECOND)], {1: chars(layer)})
        missing = [f for f in findings if f["code"] == "missing_text"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(len(missing[0]["items"]), 2)
        self.assertTrue(missing[0]["items"][1].startswith("study period. Their Efficient adaptation"))

    def test_one_finding_per_id(self):
        layer = PARAGRAPH + " " + self.MISSING + " " + SECOND + " " + self.MISSING.replace("Our", "Their")
        blocks = [block(0, 1, "text", PARAGRAPH + " " + SECOND), block(1, 1, "table", "<td>0</td>" * 40),
                  block(0, 2, "formula_number", "(1)"), block(1, 2, "formula_number", "(3)"),
                  block(2, 2, "formula_number", "(5)")]
        _, findings = C.check_document(blocks, {1: chars(layer), 2: None})
        self.assertEqual(len(ids(findings)), len(set(ids(findings))))
        self.assertIn(("formula_number_gap@p2", ["(2)", "(4)"]), [(f["id"], f["items"]) for f in findings])


class PdfLayer(unittest.TestCase):
    @staticmethod
    def pdf(path):
        """A two-page PDF, 200 x 100 points: "Hello world" at (20, 70) on page 1, nothing on page 2. No xref: pdfium
        rebuilds it."""
        text = b"BT /F1 12 Tf 20 70 Td (Hello world) Tj ET"
        path.write_bytes(
            b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >> endobj\n"
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"5 0 obj << /Length " + str(len(text)).encode() + b" >> stream\n" + text + b"\nendstream endobj\n"
            b"6 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] >> endobj\n"
            b"trailer << /Root 1 0 R >>\n%%EOF\n")

    def test_characters_in_page_image_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.pdf"
            self.pdf(path)
            layer = C.pdf_layer(path, {1: (400, 200), 2: (400, 200)})
        self.assertIsNone(layer[2])
        self.assertEqual("".join(c for c, _, _ in layer[1]).strip(), "Hello world")
        _, x, y = layer[1][0]                          # "H": left at 20 pt, baseline at 70 pt from the bottom
        self.assertTrue(40 < x < 70 and 40 < y < 64, (x, y))


if __name__ == "__main__":
    unittest.main()
