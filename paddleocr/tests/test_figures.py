# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2"]
# ///
"""Tests for scripts/figures.py: figure groups, captions paired with figures, the second opinion, the checks and the
overlay (no GPU needed). Pages are Letter at scale 2: 1224 x 1584 pixels, a text row about 12."""
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import conventions as C  # noqa: E402
import figures as F  # noqa: E402

SIZE = (1224, 1584)
RUNNING = "We compare the methods on every dataset of the study and report the mean and spread of each metric. " * 4


def pid(i, page=1):
    return f"p{page}-{i}"


def fb(i, label, box, text="", page=1, **extra):
    return {"id": pid(i, page), "page": page, "label": label, "text": text, "box": box, **extra}


def figs(blocks):
    """A figure of each image and chart block not in a figure of several, as the caller makes them."""
    return [{"id": b["id"], "page": b["page"], "box": b["box"], "image": f"imgs/{b['id']}.png", "members": [b["id"]]}
            for b in blocks if b["label"] in ("image", "chart") and "figure" not in b and "merged_into" not in b]


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
    role, styles = F.classify(blocks, layers or {})
    chars = (layers or {}).get(1)
    lines_in = (lambda region, width: F.body_lines(chars, region, styles, width)) if chars else None
    return F.second_opinion(blocks, role, SIZE, img, whole, lines_in)


def warned(blocks, sizes=None, figures=None, **kw):
    """caption id -> detail of its finding."""
    found = F.figure_findings(blocks, figs(blocks) if figures is None else figures, sizes or {1: SIZE}, **kw)
    return {f["block"]: f["detail"] for f in found}


def grouped(blocks, layout=None, charts=False):
    return [g["members"] for g in F.group_page(blocks, layout, 1584, charts)]


class Module(unittest.TestCase):
    def test_parse_is_not_imported(self):
        self.assertNotIn("parse", sys.modules)


class FigureGroups(unittest.TestCase):
    def test_caption_kinds(self):
        self.assertTrue(C.is_caption(fb(0, "figure_title", None, "Fig. 3: B-mode images")))
        self.assertTrue(C.is_caption(fb(0, "figure_title", None, "**Extended Data Fig. 1 | Prompts")))
        self.assertTrue(C.is_caption(fb(0, "text", None, "Fig. 3. Results on the test set")))
        self.assertTrue(C.is_caption(fb(0, "vision_footnote", None, "Figure 12: Samples")))
        self.assertFalse(C.is_caption(fb(0, "text", None, "Fig. 3 shows that the method converges")))
        self.assertTrue(C.is_panel(fb(0, "figure_title", None, "(b)")))
        self.assertTrue(C.is_subtitle(fb(0, "figure_title", None, "prompt: a photo of a cat")))
        self.assertTrue(F.is_blocker(fb(0, "text", None, RUNNING)))
        self.assertFalse(F.is_blocker(fb(0, "text", None, "x [mm]")))

    def test_layout_box_joins_its_panels_and_the_room_between(self):
        blocks = [fb(1, "image", [100, 100, 400, 300]), fb(2, "chart", [700, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 330, 1100, 360], "Fig. 2. Overview")]
        whole = [{"label": "image", "score": 0.9, "box": [95, 95, 1105, 310]}]
        (g,) = F.group_page(blocks, whole, 1584)
        self.assertEqual((g["members"], g["box"], g["by"]), ([pid(1), pid(2)], [95, 95, 1105, 310], "layout"))

    def test_layout_box_over_a_caption_is_dropped(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "figure_title", [100, 310, 1100, 340], "Fig. 1. One"),
                  fb(3, "image", [100, 360, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Fig. 2. Two")]
        self.assertEqual(grouped(blocks, [{"label": "image", "score": 0.9, "box": [90, 90, 1110, 610]}]), [])

    def test_layout_box_over_two_figures_side_by_side_is_dropped(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "figure_title", [100, 310, 580, 340], "Fig. 1. Left"),
                  fb(3, "image", [640, 100, 1120, 300]), fb(4, "figure_title", [640, 310, 1120, 340], "Fig. 2. Right")]
        self.assertEqual(grouped(blocks, [{"label": "image", "score": 0.9, "box": [90, 90, 1130, 305]}]), [])

    def test_caption_joins_the_panels_above_it_across_a_two_column_caption(self):
        # Nature: a full-width figure whose caption runs on in the right column, labelled text
        blocks = [fb(1, "chart", [100, 100, 580, 300]), fb(2, "chart", [640, 100, 1120, 300]),
                  fb(3, "chart", [100, 320, 580, 520]), fb(4, "chart", [640, 320, 1120, 520]),
                  fb(5, "figure_title", [100, 540, 580, 700], "Fig. 2 | Results."), fb(6, "text", [640, 541, 1120, 700], RUNNING)]
        self.assertEqual(grouped(blocks), [[pid(1), pid(2), pid(3), pid(4)]])
        self.assertEqual(grouped(blocks[:5]), [[pid(1), pid(3)]])

    def test_short_centred_caption_takes_the_whole_grid_above_it(self):
        # 2026-10: an appendix figure of 2 x 2 plots over "Figure 11. PubMedQA experimental results.", which lies under
        # less than half of every panel
        blocks = [fb(1, "chart", [129, 142, 564, 346]), fb(2, "chart", [622, 142, 1058, 346]),
                  fb(3, "figure_title", [165, 366, 532, 387], "(a) Accuracy versus the average time per question"),
                  fb(4, "chart", [118, 396, 574, 611]), fb(5, "chart", [603, 395, 967, 615]),
                  fb(6, "figure_title", [432, 672, 760, 693], "Figure 11. PubMedQA experimental results."),
                  fb(7, "text", [118, 720, 1060, 900], RUNNING)]
        self.assertEqual(grouped(blocks), [[pid(1), pid(2), pid(4), pid(5)]])

    def test_captions_side_by_side_keep_their_figures_apart(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [100, 320, 580, 520]),
                  fb(3, "figure_title", [100, 540, 580, 570], "Fig. 1. Left"),
                  fb(4, "image", [640, 100, 1120, 300]), fb(5, "image", [640, 320, 1120, 520]),
                  fb(6, "figure_title", [640, 540, 1120, 570], "Fig. 2. Right")]
        self.assertEqual(grouped(blocks), [[pid(1), pid(2)], [pid(4), pid(5)]])

    def test_a_row_of_panels_shares_the_caption_under_it(self):
        # 2026-10, TMI: Fig. 4 a row across the page, its caption under the left half only; the right-hand panels
        # went on to Fig. 6's caption in the right column
        blocks = [fb(1, "chart", [98, 104, 181, 418]), fb(2, "chart", [191, 102, 647, 418]), fb(3, "chart", [657, 103, 1121, 416]),
                  fb(4, "figure_title", [92, 442, 594, 464], "Fig. 4. Visual comparison"),
                  fb(5, "chart", [631, 516, 881, 698]), fb(6, "chart", [880, 517, 1120, 697]),
                  fb(7, "figure_title", [616, 1103, 1131, 1305], "Fig. 6. Assessment")]
        self.assertEqual(grouped(blocks), [[pid(1), pid(2), pid(3)], [pid(5), pid(6)]])

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
        self.assertEqual(grouped(blocks), [[pid(3), pid(4)]])

    def test_body_text_naming_a_figure_is_not_its_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "text", [100, 310, 1100, 340], "Fig. 3 shows the maps"),
                  fb(3, "image", [100, 360, 1100, 600])]
        self.assertEqual(grouped(blocks), [])

    def test_letters_and_titles_beside_the_figure_widen_it(self):
        blocks = [fb(1, "figure_title", [100, 85, 115, 98], "a"), fb(2, "image", [100, 100, 580, 300]),
                  fb(3, "image", [640, 100, 1120, 300]), fb(4, "figure_title", [640, 305, 900, 320], "(b) Ours"),
                  fb(5, "figure_title", [100, 340, 1120, 370], "Fig. 6. Samples")]
        (g,) = F.group_page(blocks, None, 1584)
        self.assertEqual((g["members"], g["panels"], g["box"]), ([pid(2), pid(3)], [pid(1)], [100, 85, 1120, 320]))

    def test_second_half_of_a_two_column_caption_stays_out_of_the_crop(self):
        # 2026-10, Nature: the caption's right half, labelled figure_title, was taken for a title inside the figure,
        # and widening the crop to it took in the whole caption
        blocks = [fb(1, "figure_title", [100, 85, 115, 98], "a"), fb(2, "image", [100, 100, 580, 500]),
                  fb(3, "image", [640, 100, 1120, 500]),
                  fb(4, "figure_title", [100, 505, 580, 640], "Fig. 1 | Overview. a, The system."),
                  fb(5, "figure_title", [640, 505, 1120, 620], "training source and are shown in three scenarios.")]
        for layout in ([{"label": "image", "score": 0.9, "box": [95, 95, 1125, 500]}], None):
            (g,) = F.group_page(blocks, layout, 1584)
            self.assertEqual((g["members"], g["panels"], g["box"][3]), ([pid(2), pid(3)], [pid(1)], 500))

    def test_table_caption_above_a_figure_stays_out_of_its_crop(self):
        # 2026-10: "Table 2. ..." under a table and right above a figure, labelled figure_title, was taken for a title
        # inside the figure
        blocks = [fb(1, "table", [111, 123, 1085, 322], "<table></table>"),
                  fb(2, "figure_title", [106, 343, 1087, 388], "Table 2. Best performance achieved by each system."),
                  fb(3, "chart", [154, 408, 440, 586]), fb(4, "chart", [452, 409, 737, 586]),
                  fb(5, "figure_title", [104, 600, 1084, 640], "Figure 2. Boxplots of total accuracy.")]
        self.assertTrue(C.is_table_caption(blocks[1]) and C.is_table_caption(fb(0, "figure_title", None, "TABLE IV")))
        (g,) = F.group_page(blocks, None, 1584)
        self.assertEqual((g["members"], g["box"]), ([pid(3), pid(4)], [154, 408, 737, 586]))

    def test_charts_turned_into_tables_stay_out(self):
        blocks = [fb(1, "chart", [100, 100, 580, 300]), fb(2, "chart", [640, 100, 1120, 300]),
                  fb(3, "figure_title", [100, 310, 1120, 340], "Fig. 7. Curves")]
        self.assertEqual(grouped(blocks), [[pid(1), pid(2)]])
        self.assertEqual(grouped(blocks, charts=True), [])

    def test_groups_come_in_reading_order_whatever_the_ids(self):
        # ids are strings: "p1-20" sorts before "p1-9"
        blocks = [fb(9, "image", [100, 100, 580, 300]), fb(15, "image", [100, 400, 580, 600]),
                  fb(16, "image", [640, 400, 1100, 600]), fb(20, "image", [640, 100, 1100, 300]),
                  fb(21, "figure_title", [100, 310, 1100, 340], "Fig. 1. Upper"),
                  fb(22, "figure_title", [100, 610, 1100, 640], "Fig. 2. Lower")]
        self.assertEqual(grouped(blocks), [[pid(9), pid(20)], [pid(15), pid(16)]])

    def test_content_moved_elsewhere_stays_out(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1120, 300], merged_into=pid(1)),
                  fb(3, "figure_title", [100, 310, 1120, 340], "Fig. 1. Two")]
        self.assertEqual(grouped(blocks), [])


class PairCaptions(unittest.TestCase):
    def test_nearest_caption_below_else_above(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two crops."),
                  fb(4, "figure_title", [100, 700, 1100, 730], "Figure 2: Set above its figure."),
                  fb(5, "chart", [100, 740, 1100, 1000]),
                  fb(1, "image", [100, 100, 1100, 1400], page=2)]
        self.assertEqual(F.pair_captions(blocks, figs(blocks), {1: SIZE, 2: SIZE}),
                         {pid(1): pid(3), pid(2): pid(3), pid(5): pid(4)})

    def test_caption_in_another_column_is_not_its(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "figure_title", [640, 310, 1100, 340], "Figure 1: Right.")]
        self.assertEqual(F.pair_captions(blocks, figs(blocks), {1: SIZE}), {})

    def test_a_figure_of_several_blocks_takes_the_caption(self):
        blocks = [fb(1, "image", [100, 100, 580, 300], figure=pid(1)), fb(2, "image", [640, 100, 1100, 300], figure=pid(1)),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Fig. 1 | Two panels.")]
        whole = [{"id": pid(1), "page": 1, "box": [100, 100, 1100, 300], "image": "imgs/p1-1.png", "members": [pid(1), pid(2)]}]
        self.assertEqual(F.pair_captions(blocks, whole, {1: SIZE}), {pid(1): pid(3)})


class SecondOpinion(unittest.TestCase):
    def test_grows_up_to_running_text_and_takes_the_ink_against_the_figure(self):
        blocks = [fb(1, "text", [100, 100, 1100, 380], RUNNING), fb(2, "image", [100, 400, 1100, 690]),
                  fb(3, "figure_title", [100, 700, 1100, 730], "Figure 1: Overview.")]
        img = page([150, 450, 1050, 650], [150, 385, 600, 396], [150, 200, 1050, 300])   # a label right above; text
        self.assertEqual(opinion(blocks, img)[pid(3)], [100, 385, 1100, 690])

    def test_grows_down_when_nothing_is_above(self):
        blocks = [fb(1, "figure_title", [100, 100, 1100, 130], "Figure 2: Set above."), fb(2, "chart", [100, 140, 1100, 500])]
        self.assertEqual(opinion(blocks, page([200, 200, 1000, 480]))[pid(1)], [100, 140, 1100, 500])

    def test_whole_figure_box_joins_far_panels_unless_it_covers_a_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "image", [100, 420, 1100, 600]),
                  fb(3, "figure_title", [100, 610, 1100, 640], "Figure 1: Two panels far apart.")]
        img = page([150, 150, 1050, 250], [150, 450, 1050, 580])
        self.assertEqual(opinion(blocks, img)[pid(3)], [100, 420, 1100, 600])
        self.assertEqual(opinion(blocks, img, whole=[{"label": "image", "score": 0.9, "box": [90, 90, 1110, 605]}])[pid(3)],
                         [100, 100, 1100, 600])
        self.assertEqual(opinion(blocks, img, whole=[{"label": "image", "score": 0.9, "box": [90, 90, 1110, 645]}])[pid(3)],
                         [100, 420, 1100, 600])

    def test_weak_text_joins_only_when_touching(self):
        blocks = [fb(1, "text", [100, 330, 600, 345], "a short label"), fb(2, "text", [100, 360, 600, 375], "another label"),
                  fb(3, "image", [100, 380, 1100, 690]), fb(4, "figure_title", [100, 700, 1100, 730], "Figure 1: Labels.")]
        img = page([150, 400, 1050, 680])
        self.assertEqual(opinion(blocks, img)[pid(4)], [100, 330, 1100, 690])
        blocks[1]["box"] = [100, 290, 600, 305]             # three rows above the figure: not its label
        self.assertEqual(opinion(blocks, img)[pid(4)][1], 380)

    def test_a_block_goes_to_one_caption(self):
        blocks = [fb(1, "image", [100, 100, 1100, 300]), fb(2, "figure_title", [100, 310, 1100, 340], "Figure 1: Upper."),
                  fb(3, "image", [100, 350, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Figure 2: Lower.")]
        got = opinion(blocks, page([150, 150, 1050, 280], [150, 380, 1050, 580]))
        self.assertEqual((got[pid(2)], got[pid(4)]), ([100, 100, 1100, 300], [100, 350, 1100, 600]))

    def test_body_lines_in_a_picture_box_cap_the_figure(self):
        # 2026-10, AgentHospital Fig. 6: the VL model drew five lines of body text into the figure's block
        body = [fb(1, "text", [100, 1000, 1100, 1100], RUNNING), fb(2, "text", [100, 1150, 1100, 1250], RUNNING)]
        blocks = body + [fb(3, "image", [100, 100, 1100, 600]), fb(4, "figure_title", [100, 610, 1100, 640], "Figure 6: Knowledge.")]
        chars = line(1020) + line(1040) + line(1170) + line(1190) + line(110) + line(125) + line(140)
        img = page([150, 200, 1050, 580], [100, 105, 1100, 145])
        self.assertEqual(opinion(blocks, img)[pid(4)][1], 100)
        self.assertEqual(opinion(blocks, img, layers={1: chars})[pid(4)][1], 150)

    def test_a_heading_stops_only_when_running_text_follows_it(self):
        # 2026-10, wangKnowledgeGraph Fig. 4: a panel title read as a section heading cut the figure in two
        blocks = [fb(1, "image", [100, 300, 600, 560]), fb(2, "paragraph_title", [100, 570, 1100, 590], "Prompt for paths"),
                  fb(3, "image", [100, 600, 600, 890]), fb(4, "figure_title", [100, 900, 600, 930], "Figure 4: Prompts.")]
        img = page([150, 320, 550, 540], [150, 620, 550, 880])
        self.assertEqual(opinion(blocks, img)[pid(4)][1], 300)
        blocks.append(fb(5, "text", [700, 594, 1100, 700], RUNNING))
        self.assertEqual(opinion(blocks, img)[pid(4)][1], 600)

    def test_roles_from_the_text_layer(self):
        body = [fb(1, "text", [100, 1000, 1100, 1100], RUNNING), fb(2, "text", [100, 1150, 1100, 1250], RUNNING)]
        blocks = body + [fb(3, "text", [100, 100, 1100, 200], RUNNING), fb(4, "text", [100, 300, 1100, 320], "Prompt: what is shown"),
                         fb(5, "figure_title", [100, 400, 600, 420], "Step 1: read")]
        chars = line(1020, n=100) + line(1170, n=100) + line(150, n=100) + line(410, 100, 600, 12, 8.0, "Arial")
        role, _ = F.classify(blocks, {1: chars})
        self.assertEqual([role[pid(i)] for i in (1, 3, 4, 5)], ["flow", "flow", "fig", "fig"])   # block 4: text in pixels
        role, _ = F.classify(blocks, {})
        self.assertEqual([role[pid(i)] for i in (1, 3, 4, 5)], ["flow", "flow", "~", "fig"])


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
        self.assertEqual(warned(blocks, sizes), {pid(4): "no_crop: no crop beside this caption"})

    def test_title_above_and_legend_below_are_one_figure(self):
        # 2026-10, Science: "Figure 1. <title>" over the figure, "Figure 1: <legend>" under it
        blocks = [fb(1, "figure_title", [100, 100, 1100, 130], "Figure 1. Performance of diagnosis generators"),
                  fb(2, "chart", [100, 150, 1100, 600]),
                  fb(3, "figure_title", [100, 610, 1100, 700], "Figure 1: Barplot showing the accuracy."),
                  fb(4, "figure_title", [100, 800, 1100, 830], "Extended Data Fig. 1 | Drawn as text.")]
        self.assertEqual(list(warned(blocks)), [pid(4)])

    def test_split(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two crops.")]
        self.assertEqual(warned(blocks), {pid(3): "split: 2 crops"})

    def test_split_across_a_page_break(self):
        # 2026-10, Nature Medicine Extended Data Fig. 8: a grid of small images in 26 crops, its caption on the next page
        pieces = [fb(i, "image", [100 + 300 * (i % 3), 100 + 400 * (i // 3), 380 + 300 * (i % 3), 480 + 400 * (i // 3)]) for i in range(9)]
        captions = [fb(20, "text", [100, 90, 1100, 200], "Extended Data Fig. 8 | A grid.", page=2),
                    fb(21, "text", [100, 210, 1100, 300], "Extended Data Fig. 9 | Another.", page=2)]
        found = F.figure_findings(pieces + captions, figs(pieces), {1: SIZE, 2: SIZE})
        self.assertEqual([(f["block"], f["detail"]) for f in found], [(pid(20, 2), "split: the figure on page 1 is in 9 crops")])
        self.assertEqual({c["page"] for c in found[0]["crops"]}, {1})
        whole = [fb(0, "image", [100, 100, 1100, 1400])]
        self.assertEqual(F.figure_findings(whole + captions, figs(whole), {1: SIZE, 2: SIZE}), [])

    def test_two_figures_in_one_crop(self):
        crop = fb(1, "image", [100, 100, 1100, 900])
        caption = fb(3, "figure_title", [100, 910, 1100, 940], "Figure 17: Upper.")
        inside = fb(2, "figure_title", [100, 500, 1100, 530], "Figure 18: Swallowed.")
        self.assertTrue(warned([crop, inside, caption])[pid(3)].startswith("two_figures"))
        text = lambda own: (lambda page, box: f"axis\n{own}: Swallowed caption\nmore")
        self.assertTrue(warned([crop, caption], text_in=text("Figure 18"))[pid(3)].startswith("two_figures"))
        self.assertEqual(warned([crop, caption], text_in=text("Figure 17")), {})
        side = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 510, 580, 540], "Figure 1: Left."),
                fb(3, "figure_title", [640, 510, 1100, 540], "Figure 2: Right.")]
        self.assertIn("side by side", warned(side)[pid(2)])

    def test_table_drawn_into_a_figure(self):
        blocks = [fb(1, "image", [100, 100, 1100, 700]), fb(2, "figure_title", [100, 710, 1100, 740], "Figure 2: Overview."),
                  fb(3, "figure_title", [100, 760, 1100, 790], "Table 1. Results.")]
        self.assertTrue(warned(blocks)[pid(2)].startswith("table:"))
        self.assertEqual(warned(blocks + [fb(4, "table", [100, 800, 1100, 1000], "<table></table>")]), {})
        blocks[2] = fb(3, "text", [100, 760, 1100, 790], "Table 1 lists the results of every model on every dataset.")
        self.assertEqual(warned(blocks), {})

    def test_crop_edge_through_marks(self):
        blocks = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 520, 1100, 550], "Figure 1: Cut.")]
        bars = [[200 + 100 * k, 300, 210 + 100 * k, 508] for k in range(3)]   # 8 px past the edge: under a row
        self.assertEqual(warned(blocks, image_of=lambda p: page(*bars)), {pid(2): "edge_cut: the bottom edge cuts through 3 marks"})
        self.assertEqual(warned(blocks, image_of=lambda p: page(*bars[:2])), {})

    def test_second_opinion_against_the_crop(self):
        blocks = [fb(1, "text", [100, 100, 1100, 380], RUNNING), fb(2, "image", [100, 400, 1100, 690]),
                  fb(3, "figure_title", [100, 700, 1100, 730], "Figure 1: Overview.")]
        img = page([150, 450, 1050, 650], [150, 385, 600, 396])
        (found,) = F.figure_findings(blocks, figs(blocks), {1: SIZE}, image_of=lambda p: img)
        self.assertEqual(found["detail"], "second_opinion: its top edge is 1.3 rows above the crop's")
        self.assertEqual(found["second_opinion"], [100, 385, 1100, 690])
        self.assertEqual(found["crops"], [{"n": 1, "figure": pid(2), "box": [100, 400, 1100, 690], "page": 1}])

    def test_without_a_page_image_only_the_block_checks_run(self):
        blocks = [fb(1, "image", [100, 100, 1100, 500]), fb(2, "figure_title", [100, 520, 1100, 550], "Figure 1: Cut.")]
        bars = [[200 + 100 * k, 300, 210 + 100 * k, 508] for k in range(3)]   # 8 px past the edge: under a row
        self.assertEqual(warned(blocks, image_of=lambda p: None), {})
        self.assertEqual(list(warned(blocks, image_of=lambda p: page(*bars))), [pid(2)])


class Findings(unittest.TestCase):
    def test_a_finding_names_its_caption_reasons_and_crops(self):
        blocks = [fb(1, "image", [100, 100, 580, 500]), fb(2, "image", [640, 100, 1100, 500]),
                  fb(3, "figure_title", [100, 520, 1100, 550], "Figure 1: Two crops, cut.")]
        bars = [[200 + 100 * k, 300, 210 + 100 * k, 508] for k in range(3)]
        (found,) = F.figure_findings(blocks, figs(blocks), {1: SIZE}, image_of=lambda p: page(*bars))
        self.assertEqual({k: found[k] for k in ("id", "code", "page", "block", "items", "detail")},
                         {"id": "figure_check@p1-3", "code": "figure_check", "page": 1, "block": pid(3), "items": ["split", "edge_cut"],
                          "detail": "split: 2 crops; edge_cut: the bottom edge cuts through 3 marks"})
        self.assertEqual([(c["n"], c["figure"]) for c in found["crops"]], [(1, pid(1)), (2, pid(2))])

    def test_a_figure_of_several_blocks_is_one_crop(self):
        blocks = [fb(1, "image", [100, 100, 580, 300], figure=pid(1)), fb(2, "image", [640, 100, 1100, 300], figure=pid(1)),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two panels.")]
        whole = [{"id": pid(1), "page": 1, "box": [100, 100, 1100, 300], "image": "imgs/p1-1.png", "members": [pid(1), pid(2)]}]
        img = page([150, 150, 550, 280], [700, 150, 1050, 280])
        self.assertEqual(warned(blocks, figures=whole, image_of=lambda p: img), {})
        singles = [{k: v for k, v in b.items() if k != "figure"} for b in blocks]
        self.assertEqual(warned(singles, image_of=lambda p: img), {pid(3): "split: 2 crops"})

    def test_settled_figures_are_not_checked(self):
        blocks = [fb(1, "image", [100, 100, 580, 300]), fb(2, "image", [640, 100, 1100, 300]),
                  fb(3, "figure_title", [100, 310, 1100, 340], "Figure 1: Two crops."),
                  fb(4, "figure_title", [100, 800, 1100, 830], "Figure 2: Drawn as text.")]
        self.assertEqual(warned(blocks, settled={pid(2)}), {pid(4): "no_crop: no crop beside this caption"})
        self.assertEqual(list(warned(blocks, settled={pid(9)})), [pid(3), pid(4)])
        pieces = [fb(i, "image", [100 + 300 * (i % 3), 100 + 400 * (i // 3), 380 + 300 * (i % 3), 480 + 400 * (i // 3)]) for i in range(9)]
        caption = fb(20, "text", [100, 90, 1100, 200], "Extended Data Fig. 8 | A grid.", page=2)
        self.assertEqual(warned(pieces + [caption], {1: SIZE, 2: SIZE}, settled={pid(4)}), {})


class Overlay(unittest.TestCase):
    def test_png_with_numbered_crops_caption_and_second_opinion(self):
        crops = [{"id": pid(2), "page": 1, "box": [100, 400, 580, 690]}, {"id": pid(5), "page": 1, "box": [640, 400, 1100, 690]}]
        caption = fb(3, "figure_title", [100, 700, 1100, 730], "Figure 1: Overview.")
        found = {"id": "figure_check@p1-3", "second_opinion": [100, 385, 1100, 690]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "new" / "p1-3.png"
            F.draw_overlay(page(), found, crops, caption, path)
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            img = cv2.imread(str(path))
        o = F.OFFSET
        self.assertEqual(tuple(img[400 - o, 300]), F.PALETTE[0])                 # crop 1, top edge
        self.assertEqual(tuple(img[400 - o, 900]), F.PALETTE[1])                 # crop 2
        self.assertEqual(tuple(img[730 + o, 600]), (230, 80, 0))                 # the caption, bottom edge
        self.assertEqual(tuple(img[385 - 2 * o, 100 - 2 * o + 4]), (0, 170, 0))  # the second opinion, a dash at its corner


if __name__ == "__main__":
    unittest.main()
