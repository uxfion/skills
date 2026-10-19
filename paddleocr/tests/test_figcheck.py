# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2"]
# ///
"""Tests for scripts/figcheck.py: the second opinion, the checks, the Markdown notes, and when parse.py runs them
(no GPU needed). Pages are Letter at scale 2: 1224 x 1584 pixels, a text row about 12."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("parse", SCRIPTS / "parse.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
sys.modules["parse"] = P
sys.path.insert(0, str(SCRIPTS))
import figcheck as F  # noqa: E402

SIZE = (1224, 1584)
RUNNING = "We compare the methods on every dataset of the study and report the mean and spread of each metric. " * 4


def fb(i, label, bbox, text="", page=1, **extra):
    return {"id": i, "page": page, "label": label, "text": text, "bbox": bbox, **extra}


def page(*boxes):
    """A white page with black ink in each box."""
    img = np.full((SIZE[1], SIZE[0], 3), 255, np.uint8)
    for x1, y1, x2, y2 in boxes:
        img[y1:y2, x1:x2] = 0
    return img


def line(y, x1=100, x2=1100, n=60, size=10.0, font="Times"):
    """Text-layer characters of one line: (x, y, size, font)."""
    return [(x1 + (x2 - x1) * k / (n - 1), y, size, font) for k in range(n)]


def opinion(blocks, img, layers=None, whole=None):
    role, styles = F.classify([b for b in blocks if b["label"] != "figure"], layers or {})
    chars = (layers or {}).get(1)
    lines_in = (lambda region, width: F.body_lines(chars, region, styles, width)) if chars else None
    return F.second_opinion(blocks, role, SIZE, img, whole, lines_in)


def warned(blocks, sizes=None, **kw):
    return {w["block"]: w["reasons"] for w in F.figure_warnings(blocks, sizes or {1: SIZE}, **kw)}


class SecondOpinion(unittest.TestCase):
    def test_grows_up_to_running_text_and_takes_the_ink_against_the_figure(self):
        blocks = [fb(1, "text", [100, 100, 1100, 380], RUNNING), fb(2, "image", [100, 400, 1100, 690]),
                  fb(3, "figure_title", [100, 700, 1100, 730], "Figure 1: Overview.")]
        img = page([150, 450, 1050, 650], [150, 385, 600, 396], [150, 200, 1050, 300])   # a label right above; text
        self.assertEqual(opinion(blocks, img)[3], [100, 385, 1100, 690])

    def test_grows_down_when_nothing_is_above(self):
        blocks = [fb(1, "figure_title", [100, 100, 1100, 130], "Figure 2: Set above."), fb(2, "chart", [100, 140, 1100, 500])]
        self.assertEqual(opinion(blocks, page([200, 200, 1000, 480]))[1], [100, 140, 1100, 500])

    def test_whole_figure_box_joins_far_panels_unless_it_covers_a_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "image", [100, 420, 1100, 600]),
                  fb(3, "figure_title", [100, 610, 1100, 640], "Figure 1: Two panels far apart.")]
        img = page([150, 150, 1050, 250], [150, 450, 1050, 580])
        self.assertEqual(opinion(blocks, img)[3], [100, 420, 1100, 600])
        self.assertEqual(opinion(blocks, img, whole=[{"label": "image", "bbox": [90, 90, 1110, 605]}])[3], [100, 100, 1100, 600])
        self.assertEqual(opinion(blocks, img, whole=[{"label": "image", "bbox": [90, 90, 1110, 645]}])[3], [100, 420, 1100, 600])

    def test_weak_text_joins_only_when_touching(self):
        blocks = [fb(1, "text", [100, 330, 600, 345], "a short label"), fb(2, "text", [100, 360, 600, 375], "another label"),
                  fb(3, "image", [100, 380, 1100, 690]), fb(4, "figure_title", [100, 700, 1100, 730], "Figure 1: Labels.")]
        img = page([150, 400, 1050, 680])
        self.assertEqual(opinion(blocks, img)[4], [100, 330, 1100, 690])
        blocks[1]["bbox"] = [100, 290, 600, 305]            # three rows above the figure: not its label
        self.assertEqual(opinion(blocks, img)[4][1], 380)

    def test_a_block_goes_to_one_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "figure_title", [100, 310, 1100, 340], "Figure 1: Upper."),
                  fb(3, "image", [100, 350, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Figure 2: Lower.")]
        got = opinion(blocks, page([150, 150, 1050, 280], [150, 380, 1050, 580]))
        self.assertEqual((got[2], got[4]), ([100, 100, 1100, 300], [100, 350, 1100, 600]))

    def test_body_lines_in_a_picture_box_cap_the_figure(self):
        # 2026-10, AgentHospital Fig. 6: the VL model drew five lines of body text into the figure's block
        body = [fb(1, "text", [100, 1000, 1100, 1100], RUNNING), fb(2, "text", [100, 1150, 1100, 1250], RUNNING)]
        blocks = body + [fb(3, "image", [100, 100, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Figure 6: Knowledge.")]
        chars = line(1020) + line(1040) + line(1170) + line(1190) + line(110) + line(125) + line(140)
        img = page([150, 200, 1050, 580], [100, 105, 1100, 145])
        self.assertEqual(opinion(blocks, img)[4][1], 100)
        self.assertEqual(opinion(blocks, img, layers={1: chars})[4][1], 150)

    def test_a_heading_stops_only_when_running_text_follows_it(self):
        # 2026-10, wangKnowledgeGraph Fig. 4: a panel title read as a section heading cut the figure in two
        blocks = [fb(1, "image", [100, 300, 600, 560]), fb(2, "paragraph_title", [100, 570, 1100, 590], "Prompt for paths"),
                  fb(3, "image", [100, 600, 600, 890]), fb(4, "figure_title", [100, 900, 600, 930], "Figure 4: Prompts.")]
        img = page([150, 320, 550, 540], [150, 620, 550, 880])
        self.assertEqual(opinion(blocks, img)[4][1], 300)
        blocks.append(fb(5, "text", [700, 594, 1100, 700], RUNNING))
        self.assertEqual(opinion(blocks, img)[4][1], 600)

    def test_roles_from_the_text_layer(self):
        body = [fb(1, "text", [100, 1000, 1100, 1100], RUNNING), fb(2, "text", [100, 1150, 1100, 1250], RUNNING)]
        blocks = body + [fb(3, "text", [100, 100, 1100, 200], RUNNING), fb(4, "text", [100, 300, 1100, 320], "Prompt: what is shown"),
                         fb(5, "figure_title", [100, 400, 600, 420], "Step 1: read")]
        chars = line(1020, n=100) + line(1170, n=100) + line(150, n=100) + line(410, 100, 600, 12, 8.0, "Arial")
        role, _ = F.classify(blocks, {1: chars})
        self.assertEqual([role[i] for i in (1, 3, 4, 5)], ["flow", "flow", "fig", "fig"])   # block 4: text in pixels
        role, _ = F.classify(blocks, {})
        self.assertEqual([role[i] for i in (1, 3, 4, 5)], ["flow", "flow", "~", "fig"])


class Checks(unittest.TestCase):
    def test_caption_without_a_crop(self):
        # 2026-10: sample outputs drawn as figures are read as text; their captions come with no crop
        sizes = {1: SIZE, 2: SIZE, 3: SIZE}
        blocks = [fb(1, "image", [100, 100, 1100, 400]), fb(2, "figure_title", [100, 410, 1100, 440], "Figure 1: Overview."),
                  fb(3, "algorithm", [100, 500, 1100, 900], "So we want to find the greatest value ..."),
                  fb(4, "figure_title", [100, 910, 1100, 940], "Figure 2: Revision model example 1."),
                  fb(5, "figure_title", [100, 1000, 1100, 1030], "Figure 3: Caption set above its figure."),
                  fb(6, "chart", [100, 1040, 1100, 1400]),
                  fb(7, "image", [100, 100, 1100, 1450], page=2),
                  fb(8, "text", [100, 90, 1100, 200], "Extended Data Fig. 4 | The figure on the page before.", page=3)]
        self.assertEqual(warned(blocks, sizes), {4: ["no_crop: no crop beside this caption"]})

    def test_title_above_and_legend_below_are_one_figure(self):
        # 2026-10, Science: "Figure 1. <title>" over the figure, "Figure 1: <legend>" under it
        blocks = [fb(1, "figure_title", [100, 100, 1100, 130], "Figure 1. Performance of diagnosis generators"),
                  fb(2, "chart", [100, 150, 1100, 600]),
                  fb(3, "figure_title", [100, 610, 1100, 700], "Figure 1: Barplot showing the accuracy."),
                  fb(4, "figure_title", [100, 800, 1100, 830], "Extended Data Fig. 1 | Drawn as text.")]
        self.assertEqual(list(warned(blocks)), [4])

    def test_split(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two crops.")]
        self.assertEqual(warned(blocks), {3: ["split: 2 crops"]})

    def test_split_across_a_page_break(self):
        # 2026-10, Nature Medicine Extended Data Fig. 8: a grid of small images in 26 crops, its caption on the next page
        pieces = [fb(i, "image", [100 + 300 * (i % 3), 100 + 400 * (i // 3), 380 + 300 * (i % 3), 480 + 400 * (i // 3)]) for i in range(9)]
        captions = [fb(20, "text", [100, 90, 1100, 200], "Extended Data Fig. 8 | A grid.", page=2),
                    fb(21, "text", [100, 210, 1100, 300], "Extended Data Fig. 9 | Another.", page=2)]
        warnings = F.figure_warnings(pieces + captions, {1: SIZE, 2: SIZE})
        self.assertEqual([(w["block"], w["reasons"]) for w in warnings], [(20, ["split: the figure on page 1 is in 9 crops"])])
        self.assertEqual({c["page"] for c in warnings[0]["crops"]}, {1})
        whole = [fb(0, "image", [100, 100, 1100, 1400])]
        self.assertEqual(F.figure_warnings(whole + captions, {1: SIZE, 2: SIZE}), [])

    def test_two_figures_in_one_crop(self):
        crop = fb(1, "image", [100, 100, 1100, 900])
        caption = fb(3, "figure_title", [100, 910, 1100, 940], "Figure 17: Upper.")
        inside = fb(2, "figure_title", [100, 500, 1100, 530], "Figure 18: Swallowed.")
        self.assertIn("two_figures", warned([crop, inside, caption])[3][0])
        text = lambda own: (lambda page, box: f"axis\n{own}: Swallowed caption\nmore")
        self.assertIn("two_figures", warned([crop, caption], text_in=text("Figure 18"))[3][0])
        self.assertEqual(warned([crop, caption], text_in=text("Figure 17")), {})
        side = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 510, 580, 540], "Figure 1: Left."),
                fb(3, "figure_title", [640, 510, 1100, 540], "Figure 2: Right.")]
        self.assertIn("side by side", warned(side)[2][0])

    def test_table_drawn_into_a_figure(self):
        blocks = [fb(1, "image", [100, 100, 1100, 700]), fb(2, "figure_title", [100, 710, 1100, 740], "Figure 2: Overview."),
                  fb(3, "figure_title", [100, 760, 1100, 790], "Table 1. Results.")]
        self.assertTrue(warned(blocks)[2][0].startswith("table:"))
        self.assertEqual(warned(blocks + [fb(4, "table", [100, 800, 1100, 1000], "<table></table>")]), {})
        blocks[2] = fb(3, "text", [100, 760, 1100, 790], "Table 1 lists the results of every model on every dataset.")
        self.assertEqual(warned(blocks), {})

    def test_crop_edge_through_marks(self):
        blocks = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 520, 1100, 550], "Figure 1: Cut.")]
        bars = [[200 + 100 * k, 300, 210 + 100 * k, 508] for k in range(3)]   # 8 px past the edge: under a row
        reasons = warned(blocks, image_of=lambda p: page(*bars))[2]
        self.assertEqual(reasons, ["edge_cut: the bottom edge cuts through 3 marks"])
        self.assertEqual(warned(blocks, image_of=lambda p: page(*bars[:2])), {})

    def test_second_opinion_against_the_crop(self):
        blocks = [fb(1, "text", [100, 100, 1100, 380], RUNNING), fb(2, "image", [100, 400, 1100, 690]),
                  fb(3, "figure_title", [100, 700, 1100, 730], "Figure 1: Overview.")]
        img = page([150, 450, 1050, 650], [150, 385, 600, 396])
        warnings = F.figure_warnings(blocks, {1: SIZE}, image_of=lambda p: img)
        self.assertEqual(warnings[0]["reasons"], ["second_opinion: its top edge is 1.3 rows above the crop's"])
        self.assertEqual(warnings[0]["second_opinion"], [100, 385, 1100, 690])
        self.assertEqual(warnings[0]["crops"], [{"n": 1, "block": 2, "bbox": [100, 400, 1100, 690]}])

    def test_without_a_page_image_only_the_block_checks_run(self):
        blocks = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 520, 1100, 550], "Figure 1: Cut.")]
        bars = [[200 + 100 * k, 300, 210 + 100 * k, 508] for k in range(3)]   # 8 px past the edge: under a row
        self.assertEqual(warned(blocks, image_of=lambda p: None), {})
        self.assertEqual(list(warned(blocks, image_of=lambda p: page(*bars))), [2])


class Notes(unittest.TestCase):
    MD = ("<!-- page 1 -->\n\n![](imgs/p01_a.jpg)\n\n**Figure 1:** Overview of the method.\n\n"
          "Figure 2: Drawn as text.\n\n<!-- page 2 -->\n\nBody.\n")
    BY_ID = {3: fb(3, "figure_title", [0, 0, 1, 1], "Figure 1: Overview of the method."),
             5: fb(5, "figure_title", [0, 0, 1, 1], "Figure 2: Drawn as text."),
             7: fb(7, "figure_title", [0, 0, 1, 1], "Figure 3: Rewritten by hand.", page=2)}

    def warning(self, block, page=1, reasons=("split: 2 crops",), crops=None):
        return {"code": "figure_check", "page": page, "block": block, "reasons": list(reasons),
                "overlay": f"checks/p{page:02d}_{block}.jpg", **({"crops": crops} if crops else {})}

    def test_three_landing_places(self):
        ws = [self.warning(3, crops=[{"n": 1, "block": 2, "image": "imgs/p01_a.jpg"}]), self.warning(5, reasons=["no_crop: no crop beside this caption"]),
              self.warning(7, page=2)]
        lines = F.annotate(self.MD, ws, self.BY_ID).split("\n")
        self.assertEqual(lines[2], "<!-- figure_check: split: 2 crops [p1#3 checks/p01_3.jpg] -->")
        self.assertEqual(lines[3], "![](imgs/p01_a.jpg)")
        self.assertEqual(lines[7:9], ["<!-- figure_check: no_crop: no crop beside this caption [p1#5 checks/p01_5.jpg] -->",
                                      "Figure 2: Drawn as text."])
        self.assertEqual(lines[10:12], ["<!-- page 2 -->", "<!-- figure_check: split: 2 crops; caption \"Figure 3: Rewritten by hand.\" [p2#7 checks/p02_7.jpg] -->"])

    def test_once_per_figure_and_settled_notes_stay(self):
        ws = [self.warning(3, crops=[{"n": 1, "block": 2, "image": "imgs/p01_a.jpg"}]), self.warning(5)]
        once = F.annotate(self.MD, ws, self.BY_ID)
        self.assertEqual(F.annotate(once, ws, self.BY_ID), once)
        settled = once.replace("<!-- figure_check: split: 2 crops [p1#3", "<!-- figure kept: split: 2 crops [p1#3")
        self.assertEqual(F.annotate(settled, ws, self.BY_ID), settled)
        later = F.annotate(settled, [], self.BY_ID)                 # neither is reported any more
        self.assertIn("figure kept: split", later)
        self.assertNotIn("[p1#5", later)


def stored(d, warnings=(), parser=None, blocks=None):
    """A parse of one page image in d, stored as an earlier run left it."""
    img = Path(d) / "p1.png"
    img.write_bytes(b"")
    doc = P.resolve_input(str(img), None)
    doc.update(sha="x", fresh=True)
    args = SimpleNamespace(output=d, crop_dpi=300)
    _, md, js = P.out_paths(doc, args)
    js.parent.mkdir(parents=True)
    md.write_text("<!-- page 1 -->\n\nFigure 1: Drawn as text.\n\n<!-- from page image: fixed -->\nBody.\n")
    js.write_text(json.dumps({"source": {}, "parser": {"format": P.FORMAT, "check": P.CHECK, "options": {},
                                                       "figures": {"version": P.FIGURES, "layout_model": None}, **(parser or {})},
                              "pages": [{"page": 1, "coverage": None, "width": SIZE[0], "height": SIZE[1]}],
                              "blocks": blocks or [fb(1, "figure_title", [100, 100, 1100, 130], "Figure 1: Drawn as text."),
                                                   fb(2, "text", [100, 200, 1100, 300], "Body.")],
                              "warnings": list(warnings)}))
    return doc, args, md, js


class Runs(unittest.TestCase):
    def setUp(self):
        self.saved = P.page_image
        P.page_image = lambda doc, page, size, pdf=None: np.full((size[1], size[0], 3), 255, np.uint8)

    def tearDown(self):
        P.page_image = self.saved

    def test_stored_parse_is_checked_once(self):
        with tempfile.TemporaryDirectory() as d:
            old = {"code": "uncropped_figure", "page": 1, "block": 1, "detail": "Figure 1: Drawn as text."}
            doc, args, md, js = stored(d, [old])
            summary = P.process(doc, args, {"layout": None})
            self.assertTrue(summary["figures_checked"])
            self.assertEqual([(w["code"], w["reasons"]) for w in summary["warnings"]],
                             [("figure_check", ["no_crop: no crop beside this caption"])])
            record = json.loads(js.read_text())
            self.assertEqual(record["parser"]["figure_check"], {"version": P.FIGURE_CHECK})
            self.assertTrue((js.parent / "checks" / "p01_1.jpg").exists())
            text = md.read_text()
            self.assertEqual(text, "<!-- page 1 -->\n\n<!-- figure_check: no_crop: no crop beside this caption [p1#1 checks/p01_1.jpg] -->\n"
                                   "Figure 1: Drawn as text.\n\n<!-- from page image: fixed -->\nBody.\n")
            self.assertNotIn("figures_checked", P.process(doc, args, {"layout": None}))
            self.assertEqual(md.read_text(), text)

    def test_a_failed_check_is_tried_again(self):
        with tempfile.TemporaryDirectory() as d:
            doc, args, md, js = stored(d)
            saved = P.check_figures
            P.check_figures = lambda *a, **k: 1 / 0
            try:
                self.assertIn("ZeroDivisionError", P.process(doc, args, {"layout": None})["figures_check"])
            finally:
                P.check_figures = saved
            self.assertNotIn("figure_check", json.loads(js.read_text())["parser"])
            self.assertTrue(P.process(doc, args, {"layout": None})["figures_checked"])

    def test_text_checks_run_again_keep_the_figure_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            mine = {"code": "figure_check", "page": 1, "block": 1, "reasons": ["no_crop: no crop beside this caption"]}
            doc, args, md, js = stored(d, [mine], {"check": P.CHECK - 1, "figure_check": {"version": P.FIGURE_CHECK}})
            summary = P.process(doc, args, {"layout": None})
            self.assertTrue(summary["rechecked"])
            self.assertNotIn("figures_checked", summary)
            self.assertIn(mine, summary["warnings"])

    def test_grouping_again_checks_the_figures_again(self):
        with tempfile.TemporaryDirectory() as d:
            blocks = [fb(1, "image", [100, 100, 580, 300], image="imgs/p01_a.jpg"), fb(2, "image", [640, 100, 1100, 300], image="imgs/p01_b.jpg"),
                      fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two panels.")]
            doc, args, md, js = stored(d, parser={"figure_check": {"version": P.FIGURE_CHECK}}, blocks=blocks)
            record = json.loads(js.read_text())
            del record["parser"]["figures"]
            js.write_text(json.dumps(record))
            md.write_text("<!-- page 1 -->\n\n![](imgs/p01_a.jpg)\n\n![](imgs/p01_b.jpg)\n\nFigure 1: Two panels.\n")
            saved = P.save_crop
            P.save_crop = lambda image, bbox, path: None
            try:
                summary = P.process(doc, args, {"layout": None})
            finally:
                P.save_crop = saved
            self.assertTrue(summary["regrouped"] and summary["figures_checked"])

    def test_photo_pages_get_the_checks_that_need_no_image(self):
        with tempfile.TemporaryDirectory() as d:
            doc, args, md, js = stored(d, parser={"options": {"photo": True}})
            args.photo = True
            summary = P.process(doc, args, {"layout": None})
            self.assertTrue(summary["figures_checked"])
            self.assertEqual(json.loads(js.read_text())["parser"]["figure_check"],
                             {"version": P.FIGURE_CHECK, "skipped": ["edge_cut", "second_opinion"]})
            self.assertNotIn("overlay", summary["warnings"][0])
            self.assertIn("[p1#1] -->", md.read_text())


if __name__ == "__main__":
    unittest.main()
