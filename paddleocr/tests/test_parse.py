# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Tests for scripts/parse.py: page ranges, tokens, the text-layer check, input resolution and the start-up path (no GPU needed)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "parse.py"
spec = importlib.util.spec_from_file_location("parse", SCRIPT)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

PARAGRAPH = ("The diffusion model aligns the target image to match the style of the source domain while "
             "preserving the original spatial context of every scan in the handheld device collection.")


def chars(text, x=5000.0, y=5000.0):
    """Text-layer characters [(ch, x, y)], all at one point; the default lies outside every block box."""
    return [(ch, x, y) for ch in text]


def block(i, page, label, text):
    return {"id": i, "page": page, "label": label, "text": text, "bbox": [0, 0, 10, 10]}


class PageRanges(unittest.TestCase):
    def test_all_pages_by_default(self):
        self.assertEqual(P.parse_pages(None, 3), [1, 2, 3])

    def test_ranges_lists_and_open_end(self):
        self.assertEqual(P.parse_pages("1-3,8", 10), [1, 2, 3, 8])
        self.assertEqual(P.parse_pages("9-", 11), [9, 10, 11])
        self.assertEqual(P.parse_pages("2,2,1", 5), [1, 2])

    def test_clipped_to_page_count(self):
        self.assertEqual(P.parse_pages("4-99", 5), [4, 5])

    def test_bad_ranges(self):
        for bad in ("0", "3-1", "a", "1-2-3", "7"):
            with self.assertRaises(ValueError, msg=bad):
                P.parse_pages(bad, 5)

    def test_format_pages(self):
        self.assertEqual(P.format_pages([1, 2, 3, 8]), "1-3,8")
        self.assertEqual(P.format_pages([5]), "5")
        self.assertEqual(P.format_pages([1, 3, 4]), "1,3-4")

    def test_natural_order(self):
        names = ["p10.png", "p2.png", "p1.png"]
        self.assertEqual(sorted(names, key=P.natural_key), ["p1.png", "p2.png", "p10.png"])


class Tokens(unittest.TestCase):
    def test_text_layer_hyphenation_joined(self):
        self.assertEqual(P.tokens("annota" + chr(0xFFFE) + "tions are", layer=True), ["annotations", "are"])
        self.assertEqual(P.tokens("adap-\r\ntation", layer=True), ["adaptation"])

    def test_parsed_html_and_latex_stripped(self):
        self.assertEqual(P.tokens("<td>Spine</td><td>34,248</td> $\\mathbb{E}$ ok"), ["spine", "34,248", "ok"])

    def test_ligatures_and_case(self):
        self.assertEqual(P.tokens("Ef" + chr(0xFB01) + "cient"), ["efficient"])

    def test_cjk_characters_are_tokens(self):
        self.assertEqual(P.tokens("超声图像 test"), ["超", "声", "图", "像", "test"])

    def test_single_letters_dropped(self):
        self.assertEqual(P.tokens("a x b model"), ["model"])

    def test_greek_is_math(self):
        nu, gamma = chr(0x3BD), chr(0x3B3)
        self.assertEqual(P.tokens(f"where {nu}S = 2{gamma}S and", layer=True), ["where", "2", "and"])

    def test_number_ranges_not_joined(self):
        self.assertEqual(P.tokens("ICASSP 2023-\n2023 IEEE", layer=True), ["icassp", "2023", "2023", "ieee"])
        self.assertEqual(P.tokens("[-15,5] and 34,248"), ["15", "5", "and", "34,248"])

    def test_inline_math_glued_like_a_text_layer(self):
        glued = P.tokens(P.glue_math("yields $ o_k = \\mathcal{T}_p(a_k) $, where $ H_{k+1} $ and "
                                     "$ D_{\\mathrm{KL}}(q_n \\| p_n) $ or $ \\pi_\\theta(\\cdot \\mid H_k) $"))
        self.assertEqual(glued, ["yields", "ok", "tp", "ak", "where", "hk", "1", "and", "dkl", "qn", "pn", "or", "hk"])
        self.assertEqual(P.tokens("yields ok = Tp (ak ) where Hk+1 and DKL (qn ‖pn ) or πθ (· | Hk )",
                                  layer=True), glued)


class TextLayerCheck(unittest.TestCase):
    def test_full_match(self):
        toks = P.tokens(PARAGRAPH)
        coverage, runs = P.missing_runs(toks, set(P.ngrams(toks)))
        self.assertEqual((coverage, runs), (1.0, []))

    def test_missing_run_found(self):
        toks = P.tokens(PARAGRAPH)
        kept = toks[:5] + toks[-3:]
        coverage, runs = P.missing_runs(toks, set(P.ngrams(kept)))
        self.assertLess(coverage, 0.5)
        self.assertEqual(len(runs), 1)
        start, end = runs[0]
        self.assertIn("preserving", toks[start:end])

    def test_short_gap_tolerated(self):
        toks = P.tokens(PARAGRAPH)
        parsed = list(toks)
        parsed[8] = "xyz"                      # one misread word costs three trigrams, not a warning
        self.assertEqual(P.missing_runs(toks, set(P.ngrams(parsed)))[1], [])

    def test_document_omission_and_merge_placeholder(self):
        blocks = [block(0, 1, "text", PARAGRAPH[:60]), dict(block(1, 1, "text", ""), merged_into=0),
                  block(2, 2, "text", "Short page two text that is fine and complete as it stands here.")]
        pages, warnings = P.check_document(blocks, {1: chars(PARAGRAPH), 2: chars(blocks[2]["text"])})
        self.assertEqual([w["code"] for w in warnings], ["missing_text"])
        self.assertEqual(warnings[0]["page"], 1)
        self.assertEqual(pages[1]["coverage"], 1.0)

    def test_text_moved_to_neighbouring_page_counts(self):
        blocks = [block(0, 1, "text", PARAGRAPH), dict(block(1, 2, "text", ""), merged_into=0)]
        _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH[:80]), 2: chars(PARAGRAPH[80:])})
        self.assertEqual(warnings, [])

    def test_inline_math_either_way(self):
        parsed = "Given a source image $ x_s $, the forward process adds random noise to the image many times over."
        layer = "Given a source image xs, the forward process adds random noise to the image many times over."
        _, warnings = P.check_document([block(0, 1, "text", parsed)], {1: chars(layer)})
        self.assertEqual(warnings, [])

    def test_text_inside_figures_and_formulas_not_checked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), dict(block(1, 1, "chart", ""), bbox=[0, 0, 100, 100]),
                  dict(block(2, 1, "display_formula", "$$ a $$"), bbox=[0, 200, 100, 300])]
        layer = chars(PARAGRAPH) + chars("\nTraining loss validation loss epochs 10 20 30 40 50\n", 50, 50) \
            + chars("\nL total equals lambda times the sum of 12.5 terms\n", 50, 250)
        _, warnings = P.check_document(blocks, {1: layer})
        self.assertEqual(warnings, [])

    def test_missing_numbers(self):
        parsed = "The proposed model reached an accuracy of 70.90 percent on the held out test set."
        layer = "The proposed model reached an accuracy of 70.99 percent on the held out test set.\n0.15\n"
        _, warnings = P.check_document([block(0, 1, "text", parsed)], {1: chars(layer)})
        self.assertEqual([(w["code"], w["detail"]) for w in warnings], [("missing_numbers", "70.99")])

    def test_table_column_lost(self):
        table_layer = "\nModel Dice IOU HD ASD\nUNet 0.92 0.86 16.67 3.04\nResUNet 0.82 0.71 88.03 10.94\n"
        full = "<table><tr><td>Model</td><td>Dice</td><td>IOU</td><td>HD</td><td>ASD</td></tr>" \
               "<tr><td>UNet</td><td>0.92</td><td>0.86</td><td>16.67</td><td>3.04</td></tr>" \
               "<tr><td>ResUNet</td><td>0.82</td><td>0.71</td><td>88.03</td><td>10.94</td></tr></table>"
        lost = full.replace("<td>ASD</td>", "").replace("<td>3.04</td>", "").replace("<td>10.94</td>", "")
        for text, codes in ((full, []), (lost, ["table_mismatch"])):
            blocks = [block(0, 1, "text", PARAGRAPH), dict(block(1, 1, "table", text), bbox=[0, 0, 100, 100])]
            _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH) + chars(table_layer, 50, 50)})
            self.assertEqual([w["code"] for w in warnings if w["code"] == "table_mismatch"], codes)
        self.assertIn("asd 3.04 10.94", warnings[-1]["detail"])

    def test_image_table_flagged_unchecked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), dict(block(1, 1, "table", "<table></table>"), bbox=[0, 0, 100, 100]),
                  dict(block(2, 1, "table", ""), bbox=[0, 200, 100, 300], merged_into=1)]
        _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH)})
        self.assertEqual(warnings, [{"code": "unchecked_table", "page": 1, "block": 1}])

    def test_figure_labels_beside_a_chart_not_checked(self):
        blocks = [block(0, 1, "text", PARAGRAPH), dict(block(1, 1, "chart", ""), bbox=[100, 100, 200, 200])]
        ticks = chars("\n0.2 0.4 0.6 0.8 1.0 accuracy over training epochs 10 20 30\n", 150, 210)
        _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH) + ticks})
        self.assertEqual(warnings, [])

    def test_text_block_inside_figure_zone_still_checked(self):
        caption = "Figure two shows the training loss curves of every model trained in our experiments."
        blocks = [dict(block(0, 1, "figure_title", caption[:40]), bbox=[100, 205, 300, 215]),
                  dict(block(1, 1, "chart", ""), bbox=[100, 100, 300, 200])]
        _, warnings = P.check_document(blocks, {1: chars(caption, 200, 210)})
        self.assertEqual([w["code"] for w in warnings], ["missing_text"])

    def test_layer_text_blanks_whole_words(self):
        layer = chars("keep ") + [("c", 5, 5), ("u", 5, 5), ("t", 5000, 5000)] + chars(" word")
        self.assertEqual(P.layer_text(layer, lambda x, y: x > 2000), "keep     word")   # "cut" centres at x 1670

    def test_empty_page_and_no_text_layer(self):
        blocks = [block(0, 1, "text", PARAGRAPH), block(1, 2, "header", "IEEE TRANSACTIONS"),
                  block(2, 3, "image", "")]
        _, warnings = P.check_document(blocks, {1: None, 2: None, 3: None})
        codes = [(w["code"], w.get("page"), w.get("pages")) for w in warnings]
        self.assertIn(("empty_page", 2, None), codes)
        self.assertNotIn(("empty_page", 3, None), codes)
        self.assertIn(("no_text_layer", None, [1, 2, 3]), codes)

    def test_repetition(self):
        looped = "The result is shown. " + "the same phrase again " * 8
        blocks = [block(0, 1, "text", looped), block(1, 1, "table", "<td>0</td>" * 40)]
        _, warnings = P.check_document(blocks, {1: None})
        self.assertEqual([(w["code"], w["block"]) for w in warnings if w["code"] == "repetition"], [("repetition", 0)])
        self.assertIsNone(P.repetition(PARAGRAPH))

    def test_author_line_cycling_is_a_loop(self):
        # 2026-10: a 23-author line came out as 8,857 characters, the names cycling with small changes, no exact repeat
        names = ["Lingyi Xu", "Zhen Gao", "Xiao Li", "Yuan Shen", "Guisen Li", "Li Wang", "Jicheng Lv", "Zhao Qiao"]
        looped = ", ".join(f"{n} $ ^{{{i % 3 + 1}}} $" for k in range(12) for i, n in enumerate(names[k % 2:]))
        self.assertIsNone(P.REPEAT_RE.search(looped))
        self.assertIn("word trigrams distinct", P.repetition(looped))
        authors = ", ".join(f"{n} $ ^{{{i}}} $" for i, n in enumerate(names * 2))   # every name twice: not a loop
        self.assertIsNone(P.repetition(authors + " " + PARAGRAPH))

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
        blocks = [dict(block(0, 1, "text", parsed), bbox=[0, 0, 100, 100])]
        _, warnings = P.check_document(blocks, {1: chars(layer, 50, 50)})
        self.assertEqual(warnings, [])


class ExtraText(unittest.TestCase):
    def test_invented_continuation_flagged(self):
        invented = " and the impact of different types of data sources on the performance of the final model."
        blocks = [dict(block(0, 1, "text", PARAGRAPH + invented), bbox=[0, 0, 100, 100])]
        _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertEqual([w["code"] for w in warnings], ["extra_text"])
        self.assertIn("performance of the final model", warnings[0]["detail"])

    def test_text_read_from_an_image_not_flagged(self):
        blocks = [dict(block(0, 1, "text", PARAGRAPH), bbox=[0, 0, 100, 100]),
                  dict(block(1, 1, "text", "Prompt: the refractive medium is turbid and mild retinal edema is visible."),
                       bbox=[200, 200, 300, 300])]
        _, warnings = P.check_document(blocks, {1: chars(PARAGRAPH, 50, 50)})
        self.assertEqual(warnings, [])

    def test_foreign_script_flagged(self):
        parsed = ("Let $ u_{j,1:N_j} $年第 $ j $个signal messages, and the indexing assistant tokens "
                  "of the rollout are serialized in order.")
        layer = "Let uj,1:Nj be the j-th rollout's assistant messages, and the indexing assistant tokens of the rollout are serialized in order."
        blocks = [dict(block(0, 1, "text", parsed), bbox=[0, 0, 100, 100])]
        _, warnings = P.check_document(blocks, {1: chars(layer, 50, 50)})
        stray = [w for w in warnings if w["code"] == "foreign_script"]
        self.assertEqual(len(stray), 1)
        self.assertIn("年第 $ j $个signal", stray[0]["detail"])
        _, warnings = P.check_document(blocks, {1: chars(layer + " 年第个", 50, 50)})   # characters the source has
        self.assertNotIn("foreign_script", [w["code"] for w in warnings])

    def test_superscript_numbers_ignored(self):
        parsed = "Chenlin Meng$^{1}$, Yutong He$^{1}$, Yang Song$^{1}$, Jiaming Song$^{1}$, Jiajun Wu$^{1}$ and Jun-Yan Zhu$^{2}$"
        layer = "Chenlin Meng1 Yutong He1 Yang Song1 Jiaming Song1 Jiajun Wu1 Jun-Yan Zhu2 Stefano Ermon"
        blocks = [dict(block(0, 1, "text", parsed), bbox=[0, 0, 100, 100])]
        _, warnings = P.check_document(blocks, {1: chars(layer, 50, 50)})
        self.assertEqual(warnings, [])


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
        idx = P.line_number_chars(layer, 1200)
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
        self.assertEqual(P.empty_columns(grid), ["gCNR"])
        _, warnings = P.check_document([dict(block(0, 3, "table", grid), bbox=[0, 0, 10, 10])], {3: None})
        self.assertIn({"code": "table_empty_column", "page": 3, "block": 0, "detail": "gCNR"}, warnings)

    def test_full_table_and_spacer_column_pass(self):
        table = ("<table><tr><td></td><td>A</td><td>B</td></tr><tr><td></td><td>1</td><td>2</td></tr>"
                 "<tr><td></td><td>3</td><td>4</td></tr></table>")
        self.assertEqual(P.empty_columns(table), [])

    def test_formula_number_gap(self):
        blocks = [block(0, 4, "formula_number", "(18)"), block(1, 4, "formula_number", "(20)"),
                  block(2, 9, "formula_number", "(31)")]
        self.assertEqual(P.formula_number_gaps(blocks),
                         [{"code": "formula_number_gap", "page": 4, "detail": "(19) between (18) and (20), page 4-4"}])


class FormulaNumbers(unittest.TestCase):
    @staticmethod
    def b(label, bbox, content=""):
        return SimpleNamespace(label=label, bbox=bbox, content=content)

    def test_number_follows_its_formula_and_lead_in_goes_first(self):
        lead = self.b("text", [90, 707, 440, 730], "which can be written as")
        formula = self.b("display_formula", [266, 741, 432, 765], "$$ g = 1 - o $$")
        number = self.b("formula_number", [567, 743, 602, 764], "(19)")
        after = self.b("text", [91, 776, 602, 863], "Notice that")
        md, js = P.attach_formula_numbers([formula, lead, number, after])
        self.assertEqual(js, [lead, formula, number, after])
        self.assertEqual(md, js)

    def test_two_numbers_on_one_formula(self):
        formula = self.b("display_formula", [804, 858, 972, 908], "$$ a \\\\ b $$")
        n22 = self.b("formula_number", [1107, 855, 1143, 877], "(22)")
        n23 = self.b("formula_number", [1107, 883, 1142, 904], "(23)")
        md, js = P.attach_formula_numbers([formula, n22, n23])
        self.assertEqual(js, [formula, n22, n23])
        self.assertEqual([x.content for x in md], ["$$ a \\\\ b $$", "(22), (23)"])
        self.assertEqual(n22.content, "(22)")

    def test_number_without_a_formula_stays(self):
        text = self.b("text", [0, 0, 100, 20], "see")
        lone = self.b("formula_number", [500, 300, 530, 320], "(4)")
        self.assertEqual(P.attach_formula_numbers([text, lone]), ([text, lone], [text, lone]))


class Inputs(unittest.TestCase):
    def test_not_found(self):
        self.assertEqual(P.resolve_input("/no/such/file.pdf", None)["error"], "not_found")

    def test_unsupported_file_and_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            txt = Path(d) / "notes.txt"
            txt.write_text("x")
            self.assertEqual(P.resolve_input(str(txt), None)["error"], "unsupported_input")
            empty = Path(d) / "empty"
            empty.mkdir()
            self.assertEqual(P.resolve_input(str(empty), None)["error"], "unsupported_input")

    def test_image_directory_is_one_document(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("page10.png", "page2.png", "page1.jpg", "readme.md"):
                (Path(d) / name).write_bytes(b"")
            doc = P.resolve_input(d, "2-3")
            self.assertEqual(doc["kind"], "images")
            self.assertEqual([f.name for f in doc["files"]], ["page1.jpg", "page2.png", "page10.png"])
            self.assertEqual((doc["page_count"], doc["pages"]), (3, [2, 3]))
            self.assertEqual(P.resolve_input(d, "5")["error"], "bad_pages")


class LibraryPath(unittest.TestCase):
    def test_toolkit_directories_are_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            toolkit, other = Path(d) / "cuda-12.8" / "lib64", Path(d) / "wsl"
            toolkit.mkdir(parents=True)
            other.mkdir()
            (toolkit / "libcudart.so.12.8.90").write_bytes(b"")
            (other / "libcuda.so.1").write_bytes(b"")
            self.assertEqual(P.without_cuda_toolkit(f"{toolkit}:{other}::{toolkit}"), f"{other}:")
            self.assertIsNone(P.without_cuda_toolkit(f"{toolkit}:{toolkit}:"))
            self.assertEqual(P.without_cuda_toolkit(f"{other}:/no/such/dir"), f"{other}:/no/such/dir")


class Backend(unittest.TestCase):
    def test_choice(self):
        serve = "/skills/vllm-serve/scripts/serve.py"
        self.assertEqual(P.choose_backend("auto", None, serve)[0], "vllm")
        self.assertEqual(P.choose_backend("auto", None, None)[0], "native")
        self.assertEqual(P.choose_backend("native", None, serve)[0], "native")
        self.assertEqual(P.choose_backend("vllm", None, serve)[0], "vllm")
        self.assertEqual(P.choose_backend("auto", "http://127.0.0.1:8118/v1", None)[0], "server")

    def test_served_model_name_read_from_the_server(self):
        # 2026-10: a server started as `vllm serve PaddlePaddle/PaddleOCR-VL-1.6` answered 404 to the client's
        # default name PaddleOCR-VL-1.6-0.9B; --vl-server now passes the name the server lists
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Models(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/v1/models" else 404)
                self.end_headers()
                self.wfile.write(json.dumps({"data": [{"id": "PaddlePaddle/PaddleOCR-VL-1.6"}]}).encode())

            def log_message(self, *a):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Models)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/v1"
            self.assertEqual(P.served_models(url), ["PaddlePaddle/PaddleOCR-VL-1.6"])
            self.assertEqual(P.served_models(url + "x"), None)
        finally:
            server.shutdown()

    def test_vllm_serve_found(self):
        old = os.environ.pop("VLLM_SERVE", None)
        try:
            beside = SCRIPT.resolve().parents[2] / "vllm-serve" / "scripts" / "serve.py"
            self.assertEqual(P.find_serve(), str(beside) if beside.exists() else None)
            os.environ["VLLM_SERVE"] = "/somewhere/serve.py"
            self.assertEqual(P.find_serve(), "/somewhere/serve.py")
        finally:
            os.environ.pop("VLLM_SERVE", None)
            if old is not None:
                os.environ["VLLM_SERVE"] = old


class Recheck(unittest.TestCase):
    def test_parse_checked_by_older_rules_is_checked_again(self):
        looped = ", ".join(["Lingyi Xu", "Zhen Gao", "Xiao Li", "Yuan Shen"] * 12)
        with tempfile.TemporaryDirectory() as d:
            page = Path(d) / "p1.png"
            page.write_bytes(b"")
            doc = P.resolve_input(str(page), None)
            doc.update(sha="x", fresh=True)
            args = SimpleNamespace(output=d)
            _, md, js = P.out_paths(doc, args)
            js.parent.mkdir(parents=True)
            md.write_text("fixed by hand")
            stored = {"source": {}, "parser": {"format": P.FORMAT, "options": {}, "figures": {"version": P.FIGURES}},
                      "pages": [{"page": 1, "coverage": None, "width": 100, "height": 100}],
                      "blocks": [block(0, 1, "text", looped)], "warnings": [{"code": "no_text_layer", "pages": [1]}]}
            js.write_text(json.dumps(stored))
            summary = P.process(doc, args, {})
            self.assertTrue(summary["rechecked"])
            self.assertEqual([w["code"] for w in summary["warnings"]], ["repetition", "no_text_layer"])
            again = json.loads(js.read_text())
            self.assertEqual((again["parser"]["check"], again["warnings"]), (P.CHECK, summary["warnings"]))
            self.assertEqual(md.read_text(), "fixed by hand")
            self.assertNotIn("rechecked", P.process(doc, args, {}))


RUNNING = "We compare the methods on every dataset of the study and report the mean and spread of each metric. " * 4


def fb(i, label, bbox, text="", page=1):
    """A block on a Letter page rendered at scale 2 (1224 x 1584 pixels: a row is about 12)."""
    return {"id": i, "page": page, "label": label, "text": text, "bbox": bbox}


def grouped(blocks, layout=None, charts=False):
    return [g["members"] for g in P.group_page(blocks, layout, 1584, charts)]


class FigureGroups(unittest.TestCase):
    def test_caption_kinds(self):
        self.assertTrue(P.is_caption(fb(0, "figure_title", None, "Fig. 3: B-mode images")))
        self.assertTrue(P.is_caption(fb(0, "figure_title", None, "**Extended Data Fig. 1 | Prompts")))
        self.assertTrue(P.is_caption(fb(0, "text", None, "Fig. 3. Results on the test set")))
        self.assertTrue(P.is_caption(fb(0, "vision_footnote", None, "Figure 12: Samples")))
        self.assertFalse(P.is_caption(fb(0, "text", None, "Fig. 3 shows that the method converges")))
        self.assertTrue(P.is_panel(fb(0, "figure_title", None, "(b)")))
        self.assertTrue(P.is_subtitle(fb(0, "figure_title", None, "prompt: a photo of a cat")))
        self.assertTrue(P.is_blocker(fb(0, "text", None, RUNNING)))
        self.assertFalse(P.is_blocker(fb(0, "text", None, "x [mm]")))

    def test_layout_box_joins_its_panels_and_the_room_between(self):
        blocks = [fb(1, "image", [100, 100, 400, 300]), fb(2, "chart", [700, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 330, 1100, 360], "Fig. 2. Overview")]
        whole = [{"label": "image", "bbox": [95, 95, 1105, 310]}]
        (g,) = P.group_page(blocks, whole, 1584)
        self.assertEqual((g["members"], g["bbox"], g["by"]), ([1, 2], [95, 95, 1105, 310], "layout"))

    def test_layout_box_over_a_caption_is_dropped(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "figure_title", [100, 310, 1100, 340], "Fig. 1. One"),
                  fb(3, "image", [100, 360, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Fig. 2. Two")]
        self.assertEqual(grouped(blocks, [{"label": "image", "bbox": [90, 90, 1110, 610]}]), [])

    def test_layout_box_over_two_figures_side_by_side_is_dropped(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "figure_title", [100, 310, 580, 340], "Fig. 1. Left"),
                  fb(3, "image", [640, 100, 1120, 300]), fb(4, "figure_title", [640, 310, 1120, 340], "Fig. 2. Right")]
        self.assertEqual(grouped(blocks, [{"label": "image", "bbox": [90, 90, 1130, 305]}]), [])

    def test_caption_joins_the_panels_above_it_across_a_two_column_caption(self):
        # Nature: a full-width figure whose caption runs on in the right column, labelled text
        blocks = [fb(1, "chart", [100, 100, 580, 300]), fb(2, "chart", [640, 100, 1120, 300]),
                  fb(3, "chart", [100, 320, 580, 520]), fb(4, "chart", [640, 320, 1120, 520]),
                  fb(5, "figure_title", [100, 540, 580, 700], "Fig. 2 | Results."), fb(6, "text", [640, 541, 1120, 700], RUNNING)]
        self.assertEqual(grouped(blocks), [[1, 2, 3, 4]])
        self.assertEqual(grouped(blocks[:5]), [[1, 3]])

    def test_short_centred_caption_takes_the_whole_grid_above_it(self):
        # 2026-10: an appendix figure of 2 x 2 plots over "Figure 11. PubMedQA experimental results.", which lies under
        # less than half of every panel
        blocks = [fb(1, "chart", [129, 142, 564, 346]), fb(2, "chart", [622, 142, 1058, 346]),
                  fb(3, "figure_title", [165, 366, 532, 387], "(a) Accuracy versus the average time per question"),
                  fb(4, "chart", [118, 396, 574, 611]), fb(5, "chart", [603, 395, 967, 615]),
                  fb(6, "figure_title", [432, 672, 760, 693], "Figure 11. PubMedQA experimental results."),
                  fb(7, "text", [118, 720, 1060, 900], RUNNING)]
        self.assertEqual(grouped(blocks), [[1, 2, 4, 5]])

    def test_captions_side_by_side_keep_their_figures_apart(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [100, 320, 580, 520]),
                  fb(3, "figure_title", [100, 540, 580, 570], "Fig. 1. Left"),
                  fb(4, "image", [640, 100, 1120, 300]), fb(5, "image", [640, 320, 1120, 520]),
                  fb(6, "figure_title", [640, 540, 1120, 570], "Fig. 2. Right")]
        self.assertEqual(grouped(blocks), [[1, 2], [4, 5]])

    def test_a_row_of_panels_shares_the_caption_under_it(self):
        # 2026-10, TMI: Fig. 4 a row across the page, its caption under the left half only; the right-hand panels
        # went on to Fig. 6's caption in the right column
        blocks = [fb(1, "chart", [98, 104, 181, 418]), fb(2, "chart", [191, 102, 647, 418]), fb(3, "chart", [657, 103, 1121, 416]),
                  fb(4, "figure_title", [92, 442, 594, 464], "Fig. 4. Visual comparison"),
                  fb(5, "chart", [631, 516, 881, 698]), fb(6, "chart", [880, 517, 1120, 697]),
                  fb(7, "figure_title", [616, 1103, 1131, 1305], "Fig. 6. Assessment")]
        self.assertEqual(grouped(blocks), [[1, 2, 3], [5, 6]])

    def test_blocker_between_keeps_a_unit_out(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "paragraph_title", [100, 320, 600, 350], "IV. Results"),
                  fb(3, "image", [100, 370, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Fig. 4. Maps")]
        self.assertEqual(grouped(blocks), [])

    def test_union_over_running_text_is_not_a_figure(self):
        blocks = [fb(1, "image", [100, 100, 500, 300]), fb(2, "text", [600, 100, 1100, 300], RUNNING),
                  fb(3, "image", [100, 320, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Fig. 5. Maps")]
        self.assertEqual(grouped(blocks), [])

    def test_each_unit_goes_to_its_nearest_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "figure_title", [100, 310, 1100, 340], "Fig. 1. One"),
                  fb(3, "image", [100, 360, 1100, 500]), fb(4, "image", [100, 510, 1100, 650]),
                  fb(5, "figure_title", [100, 660, 1100, 690], "Fig. 2. Two")]
        self.assertEqual(grouped(blocks), [[3, 4]])

    def test_body_text_naming_a_figure_is_not_its_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "text", [100, 310, 1100, 340], "Fig. 3 shows the maps"),
                  fb(3, "image", [100, 360, 1100, 600])]
        self.assertEqual(grouped(blocks), [])

    def test_letters_and_titles_beside_the_figure_widen_it(self):
        blocks = [fb(1, "figure_title", [100, 85, 115, 98], "a"), fb(2, "image", [100, 100, 580, 300]),
                  fb(3, "image", [640, 100, 1120, 300]), fb(4, "figure_title", [640, 305, 900, 320], "(b) Ours"),
                  fb(5, "figure_title", [100, 340, 1120, 370], "Fig. 6. Samples")]
        (g,) = P.group_page(blocks, None, 1584)
        self.assertEqual((g["members"], g["panels"], g["bbox"]), ([2, 3], [1], [100, 85, 1120, 320]))

    def test_second_half_of_a_two_column_caption_stays_out_of_the_crop(self):
        # 2026-10, Nature: the caption's right half, labelled figure_title, was taken for a title inside the figure,
        # and widening the crop to it took in the whole caption
        blocks = [fb(1, "figure_title", [100, 85, 115, 98], "a"), fb(2, "image", [100, 100, 580, 500]),
                  fb(3, "image", [640, 100, 1120, 500]),
                  fb(4, "figure_title", [100, 505, 580, 640], "Fig. 1 | Overview. a, The system."),
                  fb(5, "figure_title", [640, 505, 1120, 620], "training source and are shown in three scenarios.")]
        for layout in ([{"label": "image", "bbox": [95, 95, 1125, 500]}], None):
            (g,) = P.group_page(blocks, layout, 1584)
            self.assertEqual((g["members"], g["panels"], g["bbox"][3]), ([2, 3], [1], 500))

    def test_table_caption_above_a_figure_stays_out_of_its_crop(self):
        # 2026-10: "Table 2. ..." under a table and right above a figure, labelled figure_title, was taken for a title
        # inside the figure
        blocks = [fb(1, "table", [111, 123, 1085, 322], "<table></table>"),
                  fb(2, "figure_title", [106, 343, 1087, 388], "Table 2. Best performance achieved by each system."),
                  fb(3, "chart", [154, 408, 440, 586]), fb(4, "chart", [452, 409, 737, 586]),
                  fb(5, "figure_title", [104, 600, 1084, 640], "Figure 2. Boxplots of total accuracy.")]
        self.assertTrue(P.is_table_caption(blocks[1]) and P.is_table_caption(fb(0, "figure_title", None, "TABLE IV")))
        (g,) = P.group_page(blocks, None, 1584)
        self.assertEqual((g["members"], g["bbox"]), ([3, 4], [154, 408, 737, 586]))

    def test_charts_turned_into_tables_stay_out(self):
        blocks = [fb(1, "chart", [100, 100, 580, 300]), fb(2, "chart", [640, 100, 1120, 300]),
                  fb(3, "figure_title", [100, 310, 1120, 340], "Fig. 7. Curves")]
        self.assertEqual(grouped(blocks), [[1, 2]])
        self.assertEqual(grouped(blocks, charts=True), [])

    def test_record_says_why_the_layout_model_was_not_used(self):
        state = {"layout": None, "layout_error": "Exception: No available model hosting platforms detected."}
        two = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1120, 300])]
        one = [fb(1, "image", [100, 100, 580, 300])]
        _, _, figures = P.group_figures(two, "", {1: (1224, 1584)}, lambda page: None, Path("."), False, state)
        self.assertEqual(figures, {"version": P.FIGURES, "layout_model": None, "layout_error": state["layout_error"]})
        _, _, figures = P.group_figures(one, "", {1: (1224, 1584)}, lambda page: None, Path("."), False, state)
        self.assertEqual(figures, {"version": P.FIGURES, "layout_model": None})

    def test_caption_without_a_crop_is_flagged(self):
        # 2026-10: sample outputs drawn as figures are read as text; their captions come with no crop
        heights = {1: 1584, 2: 1584, 3: 1584}
        blocks = [fb(1, "image", [100, 100, 1100, 400]), fb(2, "figure_title", [100, 410, 1100, 440], "Figure 1: Overview."),
                  fb(3, "algorithm", [100, 500, 1100, 900], "So we want to find the greatest value ..."),
                  fb(4, "figure_title", [100, 910, 1100, 940], "Figure 2: Revision model example 1."),
                  fb(5, "figure_title", [100, 1000, 1100, 1030], "Figure 3: Caption set above its figure."),
                  fb(6, "chart", [100, 1040, 1100, 1400]),
                  fb(7, "image", [100, 100, 1100, 1450], page=2),
                  fb(8, "text", [100, 90, 1100, 200], "Extended Data Fig. 4 | The figure on the page before.", page=3)]
        self.assertEqual([(w["page"], w["block"]) for w in P.uncropped_figures(blocks, heights)], [(1, 4)])

    def test_markdown_takes_the_whole_figure(self):
        md = ("<!-- page 2 -->\n\nText before.\n\na\n\n![](imgs/p02_a.jpg)\n\nb\n\n![](imgs/p02_b.jpg)\n\n"
              "(c) Ours\n\n![](imgs/p02_c.jpg)\n\nFig. 2. Samples.\n\na\n")
        members = [{"image": "imgs/p02_a.jpg"}, {"image": "imgs/p02_b.jpg"}, {"image": "imgs/p02_c.jpg"}]
        letters = [{"text": "a"}, {"text": "b"}]
        out = P.regroup_markdown(md, [({"image": "imgs/p02_figure_box_1_2_3_4.jpg"}, members, letters)])
        self.assertEqual(out, "<!-- page 2 -->\n\nText before.\n\n![](imgs/p02_figure_box_1_2_3_4.jpg)\n\n"
                              "(c) Ours\n\nFig. 2. Samples.\n\na\n")


class Regroup(unittest.TestCase):
    def test_parse_from_before_grouping_is_grouped_once(self):
        saved = P.save_crop, P.page_image
        P.save_crop = lambda image, bbox, path: None
        P.page_image = lambda doc, page, size, pdf=None: None
        try:
            with tempfile.TemporaryDirectory() as d:
                page = Path(d) / "p1.png"
                page.write_bytes(b"")
                doc = P.resolve_input(str(page), None)
                doc.update(sha="x", fresh=True)
                args = SimpleNamespace(output=d)
                _, md, js = P.out_paths(doc, args)
                js.parent.mkdir(parents=True)
                md.write_text("<!-- page 1 -->\n\n<!-- from page image: fixed -->\nIntro.\n\n![](imgs/p01_a.jpg)\n\n"
                              "![](imgs/p01_b.jpg)\n\nFig. 1. Two panels.\n")
                blocks = [dict(fb(0, "text", [100, 40, 1100, 80], "Intro.")),
                          dict(fb(1, "image", [100, 100, 580, 300]), image="imgs/p01_a.jpg"),
                          dict(fb(2, "image", [640, 100, 1120, 300]), image="imgs/p01_b.jpg"),
                          fb(3, "figure_title", [100, 310, 1120, 340], "Fig. 1. Two panels.")]
                stored = {"source": {}, "parser": {"format": P.FORMAT, "check": P.CHECK, "options": {}},
                          "pages": [{"page": 1, "coverage": None, "width": 1224, "height": 1584}],
                          "blocks": blocks, "warnings": []}
                js.write_text(json.dumps(stored))
                summary = P.process(doc, args, {"layout": None})
                self.assertTrue(summary["regrouped"])
                self.assertNotIn("rechecked", summary)
                again = json.loads(js.read_text())
                fig = again["blocks"][1]
                self.assertEqual((fig["label"], fig["by"], fig["bbox"]), ("figure", "caption", [100, 100, 1120, 300]))
                self.assertEqual([b.get("merged_into") for b in again["blocks"]], [None, None, 4, 4, None])
                self.assertEqual(again["parser"]["figures"], {"version": P.FIGURES, "layout_model": None})
                self.assertEqual(md.read_text(), "<!-- page 1 -->\n\n<!-- from page image: fixed -->\nIntro.\n\n"
                                                 f"![]({fig['image']})\n\nFig. 1. Two panels.\n")
                self.assertNotIn("regrouped", P.process(doc, args, {"layout": None}))
        finally:
            P.save_crop, P.page_image = saved


class StartUp(unittest.TestCase):
    def test_missing_tool_environment(self):
        env = dict(os.environ, PADDLEOCR_PYTHON="/no/such/python")
        out = subprocess.run([sys.executable, str(SCRIPT), "x.pdf", "-o", "out"], capture_output=True, text=True, env=env)
        if out.returncode == 0 or '"paddleocr_missing"' not in out.stdout:
            try:
                import paddleocr  # noqa: F401 - running inside the tool environment itself
                self.skipTest("paddleocr importable here")
            except ImportError:
                pass
        self.assertEqual(out.returncode, 2)
        self.assertEqual(json.loads(out.stdout)["error"], "paddleocr_missing")


if __name__ == "__main__":
    unittest.main()
