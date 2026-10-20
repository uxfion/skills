"""Figures: which image blocks make up one figure (group_page), which caption goes with each figure (pair_captions),
and the figure check (figure_findings, draw_overlay).

The VL layout model boxes a multi-panel figure panel by panel; group_page puts the panels back together by the
whole-figure boxes of a second layout model and by the captions under them. The caller makes each group, and each
image block left alone, one figure: a crop, which pair_captions gives its caption and so its number.

The check starts from each figure caption and asks what must hold for it and its crops, not what kind of figure it
is (2026-10, on parse.py's crops of then: 115 papers, 1138 captions, graded blind: every one of 138 severe errors
reported, 86% of the good figures passed). A caption that fails gets a figure_check finding, for the agent to judge
when a task uses it:
  no_crop         no crop goes with the caption: the figure was read as text or a table, or missed
  split           two or more crops go with it, or, across a page break, the page before ends in uncaptioned pieces
  two_figures     a crop of it also holds another caption, or two captions sit side by side under one crop
  table           a table caption with no table near it sits by its crop: the table was drawn into the figure
  edge_cut        a side of its crops cuts through three or more marks (text, lines)
  second_opinion  the extent found from the caption outwards differs from its crops by more than a text row
A caption whose crops include a figure an agent has recropped is settled and not checked.

The second opinion grows each caption's figure out from the caption until running text, another caption or a
section heading stops it, taking every block in between whatever its label; roles come from the PDF text layer
(body font and size) before geometry, whole-figure boxes and VL labels (20261019-paddleocr-figure-checks-spec.md,
§3.2 and its appendix).

Captions, panel letters and table captions are paper conventions (conventions.py): a document that writes none gets
its figures grouped by the layout boxes alone, and no figure check. Boxes are in page-image pixels. Runs in the
paddleocr tool environment (numpy, cv2, pypdfium2)."""
from __future__ import annotations

import ctypes
import re
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

import conventions as C

VERSION = 2              # bump when figure grouping or the figure check changes, so stored parses are processed again
COVER = 0.7              # share of a figure block's area inside a layout box that makes it one of the box's members
SWALLOW = 0.2            # share of a blocker's area a figure may cover
ROW = 0.0075             # share of the page height within which blocks sit in one row (12 px on a Letter page at scale 2)
LONG_TEXT = 300          # characters: a text block this long is running text, never part of a figure
UNCROPPED_REACH = 0.4    # share of the page height within which a figure crop goes with a caption
HEADING_LABELS = {"paragraph_title", "doc_title", "abstract"}
RUNNING_LABELS = {"text", "reference", "reference_content", "footnote", "algorithm", "content"}

NOISE = {"header", "footer", "number", "header_image", "footer_image", "aside_text"}
FIGLIKE = {"image", "chart", "seal"}
FLOW_TEXT = {"text", "reference", "reference_content", "footnote", "algorithm", "content", "abstract"}
HEADINGS = {"paragraph_title", "doc_title"}
INK = 235                # a pixel darker than this in any channel is ink
RASTER = 0.25            # text-layer characters under a block below this share of its text: the text is pixels
LAYER_CHARS = 50         # a page with fewer text-layer characters has no text layer
BODY_SHARE = 0.1         # a (size, font) in this share of the long text blocks, and two or more, is body text
SEED_ROWS = 12           # a caption's figure starts from figure blocks within this many rows of it
GAP_ROWS = 6             # figure blocks this close to the figure so far join it; the farthest it reaches past them
TOUCH_ROWS = 2           # blocks without evidence join only this close
OWN_ROWS = 6             # a block with another caption this close under it is that caption's
TABLE_ROWS = 4           # a table with a table caption this close is a table, not a figure
HEADING_ROWS = 3         # a heading with running text this close under it is a section heading
FULL_LINE = 0.85         # a body-font line across this share of the column is running text ...
FULL_CHARS = 30          # ... with this many characters
FIRST_LINE = 0.12        # share of the page height within which the first running line must sit from the far edge
MARGIN = 0.12            # share of the page height: header and footer bands
CUT_MARKS = 3            # ink components a side may cut through
CUT_EDGE = 2             # pixels ink must run past a side to be cut
OFFSET = 6               # pixels between a box drawn on an overlay and its real edge
PALETTE = [(0, 0, 230), (0, 140, 255), (200, 0, 200), (150, 50, 0), (0, 160, 160), (90, 0, 140), (0, 90, 200)]  # BGR


def box_area(b) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def box_overlap(a, b) -> float:
    return box_area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def box_union(boxes) -> list:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def hov(a, b) -> float:
    return min(a[2], b[2]) - max(a[0], b[0])


def gap_y(a, b) -> float:
    return max(0, a[1] - b[3], b[1] - a[3])


def gap_x(a, b) -> float:
    return max(0, a[0] - b[2], b[0] - a[2])


def is_figure_caption(b: dict) -> bool:
    """A figure caption: is_caption, or a heading whose text is one ("Figure 2: ..." labelled paragraph_title)."""
    return bool(b["box"]) and (C.is_caption(b) or (b["label"] in HEADINGS and bool(C.CAPTION_TEXT.match(b["text"].strip()))))


def is_table_caption(b: dict) -> bool:
    """A table caption, held to the rule for figure captions: a text block needs punctuation after the number,
    as "Table 3 lists ..." opens running text."""
    if not b["box"] or not C.is_table_caption(b):
        return False
    return b["label"] in ("figure_title", "table_title") or bool(re.match(C.TABLE_CAPTION.pattern + r"\s*(\*\*)?\s*[.:|]", b["text"].strip(), re.I))


def is_blocker(b: dict) -> bool:
    """A block that parts figures: a figure or table caption, a heading, running text."""
    return (C.is_caption(b) or C.is_table_caption(b) or b["label"] in HEADING_LABELS
            or (b["label"] in RUNNING_LABELS and len(b["text"]) >= LONG_TEXT))


# ---------------------------------------------------------------- figure groups

def group_page(blocks: list[dict], layout: list[dict] | None, height: float, charts: bool = False) -> list[dict]:
    """The figures of one page that several image/chart blocks make up (the VL layout model boxes each panel):
    [{"members": [ids], "panels": [ids], "box", "by"}], members in block order. A block that stays alone is no
    group; the caller makes it a figure of its own.

    A unit is a figure block or a figure made so far. `layout` holds the boxes of a layout model that draws whole
    figures ({"label", "score", "box"}); one with two or more figure blocks inside makes them a figure ("layout")
    unless it covers a blocker or two captions sit side by side right under it (it spans two figures). Then the
    units whose nearest caption below is one and the same, with no blocker between, make a figure ("caption")
    unless together they cover a blocker. Panel letters and titles within two rows of a figure widen its box; the
    letters join it. With `charts`, charts are data tables and stay out."""
    row = ROW * height
    kinds = {"image"} if charts else {"image", "chart"}
    figs = [b for b in blocks if b["label"] in kinds and b["box"] and "merged_into" not in b]
    if len(figs) < 2:
        return []
    order = {b["id"]: i for i, b in enumerate(blocks)}
    captions = [b for b in blocks if b["box"] and C.is_caption(b)]
    # A caption set in two columns goes on to its right on the same row, in a block the VL model labels text or
    # figure_title; that block is the caption too. Another caption beside it is not.
    tails = {c["id"]: [b for b in blocks if b is not c and b["box"] and b["label"] in ("text", "figure_title", "vision_footnote")
                       and not C.is_caption(b) and abs(b["box"][1] - c["box"][1]) <= row and b["box"][0] >= c["box"][2] - row]
             for c in captions}
    spans = {c["id"]: box_union([c["box"]] + [t["box"] for t in tails[c["id"]]]) for c in captions}
    tail_ids = {t["id"] for ts in tails.values() for t in ts}
    # A caption across the middle of the text area sits under a figure as wide as the text: a short centred caption
    # speaks for every panel of a grid above it (2026-10: appendix figures of 2 x 2 plots, each panel wider than the
    # part of the caption below it). A caption within one column speaks for its own width.
    text = [b["box"] for b in blocks if b["box"] and b["label"] not in NOISE]
    left, right = min(b[0] for b in text), max(b[2] for b in text)
    for cid, span in spans.items():
        if span[0] < (left + right) / 2 - row and span[2] > (left + right) / 2 + row:
            spans[cid] = [left, span[1], right, span[3]]
    blockers = [b for b in blocks if b["box"] and (is_blocker(b) or b["id"] in tail_ids)]
    units = {b["id"]: {"members": [b["id"]], "box": b["box"], "by": None} for b in figs}
    owner = {b["id"]: b["id"] for b in figs}

    def merge(ids, box, by):
        roots = sorted({owner[i] for i in ids}, key=order.get)     # the first in block order keeps the unit
        keep = units[roots[0]]
        for r in roots[1:]:
            gone = units.pop(r)
            keep["members"] += gone["members"]
            keep["box"] = box_union([keep["box"], gone["box"]])
            keep["by"] = keep["by"] or gone["by"]
            for m in gone["members"]:
                owner[m] = roots[0]
        keep["box"] = box_union([keep["box"]] + ([box] if box else []))
        keep["by"] = keep["by"] or by

    def covers_blocker(box, spare=None):
        return any(x is not spare and box_overlap(box, x["box"]) > SWALLOW * box_area(x["box"]) for x in blockers)

    def caption_below(box):
        """The nearest caption below box speaking for half its width or more, with no blocker between."""
        best = None
        for c in captions:
            span = spans[c["id"]]
            if box[3] > c["box"][1] + row or min(box[2], span[2]) - max(box[0], span[0]) < 0.5 * (box[2] - box[0]):
                continue
            if any(x is not c and x["box"][1] >= box[3] - row and x["box"][3] <= c["box"][1] + row
                   and min(x["box"][2], box[2]) > max(x["box"][0], box[0]) for x in blockers):
                continue
            if best is None or c["box"][1] < best["box"][1]:
                best = c
        return best

    for f in layout or []:
        if f["label"] not in ("image", "chart"):
            continue
        members = [b["id"] for b in figs if box_overlap(f["box"], b["box"]) >= COVER * box_area(b["box"])]
        under = [c for c in captions if f["box"][3] - row <= c["box"][1] <= f["box"][3] + 4 * row
                 and min(c["box"][2], f["box"][2]) > max(c["box"][0], f["box"][0])]
        if len(members) >= 2 and len(under) <= 1 and not covers_blocker(f["box"]):
            merge(members, f["box"], "layout")
    found = {root: caption_below(unit["box"]) for root, unit in units.items()}
    # A row of panels (tops and bottoms aligned, side by side) shares the caption right under it: a unit that would
    # pass it for a lower caption, or find none, takes it (2026-10, TMI: a row across the page over a caption under
    # its left half; the right half went on to the next figure's caption in the right column).
    rows = []
    for root in sorted(units, key=lambda r: units[r]["box"][0]):
        x1, y1, _, y2 = units[root]["box"]
        for r in rows:
            last = units[r[-1]]["box"]
            if abs(y1 - last[1]) <= 2 * row and abs(y2 - last[3]) <= 2 * row and x1 - last[2] <= 2 * row:
                r.append(root)
                break
        else:
            rows.append([root])
    for r in rows:
        bottom = max(units[root]["box"][3] for root in r)
        under = [c for c in (found[root] for root in r) if c and c["box"][1] - bottom <= 4 * row]
        if len(r) >= 2 and under:
            c = min(under, key=lambda c: c["box"][1])
            for root in r:
                if found[root] is None or found[root]["box"][1] > c["box"][3]:
                    found[root] = c
    by_caption = {}
    for root, c in found.items():
        if c:
            by_caption.setdefault(c["id"], (c, []))[1].append(root)
    for c, roots in by_caption.values():
        if len(roots) >= 2 and not covers_blocker(box_union([units[r]["box"] for r in roots]), spare=c):
            merge(roots, None, "caption")

    figures, taken = [], set()
    for unit in units.values():
        if len(unit["members"]) < 2:
            continue
        box, panels = unit["box"], []
        x1, y1, x2, y2 = box
        reach = [x1 - 2 * row, y1 - 2 * row, x2 + 2 * row, y2 + 2 * row]
        for b in blocks:
            if b["box"] and "merged_into" not in b and b["id"] not in taken | tail_ids and (C.is_panel(b) or C.is_subtitle(b)) \
                    and box_overlap(reach, b["box"]) > 0 and not covers_blocker(wider := box_union([box, b["box"]])):
                box = wider
                if C.is_panel(b):
                    panels.append(b["id"])
        taken.update(panels)
        figures.append({"members": sorted(unit["members"], key=order.get), "panels": panels,
                        "box": [int(round(v)) for v in box], "by": unit["by"]})
    return figures


# ---------------------------------------------------------------- captions

def owners(figures: list[dict], captions: list[dict], height: float) -> tuple[dict, list]:
    """caption id -> its crops (figures of the page, in their order), and the crops no caption takes: each crop goes
    with the nearest caption below it sharing its columns, else the nearest above it (captions set above figures)."""
    reach = UNCROPPED_REACH * height
    mine, loose = {}, []
    for cr in figures:
        x1, y1, x2, y2 = cr["box"]
        cols = [c for c in captions if min(x2, c["box"][2]) > max(x1, c["box"][0])]
        below = [c for c in cols if y1 < c["box"][1] and y2 <= c["box"][3] and c["box"][1] - y2 <= reach]
        above = [c for c in cols if c["box"][1] <= y1 and c["box"][3] < y2 and y1 - c["box"][3] <= reach]
        if below or above:
            c = min(below, key=lambda c: c["box"][1]) if below else max(above, key=lambda c: c["box"][3])
            mine.setdefault(c["id"], []).append(cr)
        else:
            loose.append(cr)
    return mine, loose


def pair_captions(blocks: list[dict], figures: list[dict], sizes: dict) -> dict:
    """figure id -> the id of its caption block, by owners on each page (sizes: page -> (width, height)). The crops
    of a figure split in several all get its caption; a figure no caption takes is left out."""
    out = {}
    for page, (_, h) in sizes.items():
        captions = [b for b in blocks if b["page"] == page and is_figure_caption(b)]
        mine, _ = owners([f for f in figures if f["page"] == page], captions, h)
        out.update({cr["id"]: cid for cid, crops in mine.items() for cr in crops})
    return out


# ---------------------------------------------------------------- text layer

def font_chars(pdf, page_no: int, size: tuple) -> list[tuple]:
    """One PDF page's text-layer characters as (x, y, size_pt, font), the centre in page-image pixels, the size
    scaled by the character's matrix and rounded to half a point, the font without its subset prefix."""
    import pypdfium2.raw as raw
    page = pdf[page_no - 1]
    tp = page.get_textpage()
    left, _, _, top = page.get_cropbox()
    width_pt, height_pt = page.get_size()
    sx, sy = size[0] / width_pt, size[1] / height_pt
    name, flags, out = ctypes.create_string_buffer(256), ctypes.c_int(), []
    for i in range(tp.count_chars()):
        if raw.FPDFText_GetUnicode(tp, i) <= 32:
            continue
        l, b, r, t = tp.get_charbox(i)
        raw.FPDFText_GetFontInfo(tp, i, name, 256, ctypes.byref(flags))
        m = raw.FS_MATRIX()
        raw.FPDFText_GetMatrix(tp, i, ctypes.byref(m))
        pt = raw.FPDFText_GetFontSize(tp, i) * (m.c * m.c + m.d * m.d) ** 0.5
        out.append((((l + r) / 2 - left) * sx, (top - (t + b) / 2) * sy, round(pt * 2) / 2,
                    name.value.decode("latin-1", "replace").split("+")[-1]))
    return out


def under(chars, box) -> list[tuple]:
    return [c for c in chars or [] if box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]]


def style_of(chars) -> tuple | None:
    return Counter((c[2], c[3]) for c in chars).most_common(1)[0][0] if chars else None


def strip_markup(t: str) -> str:
    return re.sub(r"\$[^$]*\$|<[^>]+>|\\[A-Za-z]+|[\s{}^_]", "", t)


def body_lines(chars, box, body_styles, width) -> list[tuple]:
    """(top, bottom) of the text-layer lines in the body font inside box that run most of `width`, and of the
    last line of such a paragraph: running text, not figure text."""
    cs = sorted((c for c in under(chars, box) if (c[2], c[3]) in body_styles), key=lambda c: c[1])
    lines = []
    for c in cs:
        if lines and abs(c[1] - lines[-1][0]) <= 0.4 * c[2] * 2:
            lines[-1][1].append(c)
        else:
            lines.append([c[1], [c]])
    out, prev = [], None
    for y, ch in lines:
        xs = [c[0] for c in ch]
        full = max(xs) - min(xs) >= FULL_LINE * width and len(ch) >= FULL_CHARS
        last = prev is not None and prev[0] and y - prev[1] <= 3 * ch[0][2] and len(ch) >= 3
        if full or last:
            out.append((y - ch[0][2], y + ch[0][2]))
        prev = (full, y)
    return out


# ---------------------------------------------------------------- the second opinion

def classify(blocks: list[dict], layers: dict) -> tuple[dict, set]:
    """block id -> role (noise, caption, tcaption, fig, tbl, flow; ~ for weak evidence, ? for none) and the body
    styles, from the text layer (`layers`: page -> font_chars, or None) where a page has one, else from labels."""
    body = Counter()
    for b in blocks:
        if b["label"] == "text" and len(b["text"]) >= LONG_TEXT and (s := style_of(under(layers.get(b["page"]), b["box"]))):
            body[s] += 1
    styles = {s for s, n in body.items() if n >= max(2, BODY_SHARE * sum(body.values()))}
    role = {}
    for b in blocks:
        lab, t, chars = b["label"], b["text"], layers.get(b["page"])
        long = len(t) >= LONG_TEXT
        if lab in NOISE:
            r = "noise"
        elif is_figure_caption(b):
            r = "caption"
        elif C.is_table_caption(b):
            r = "tcaption"
        elif lab in FIGLIKE:
            r = "fig"
        elif lab in ("doc_title", "abstract"):
            r = "flow"
        elif chars and len(chars) >= LAYER_CHARS:
            cs = under(chars, b["box"])
            n = max(len(strip_markup(t)), 20 if lab == "table" else 0)
            s = style_of(cs)
            if n >= 3 and len(cs) < RASTER * n:
                r = "fig"                                   # its text is pixels: part of a picture
            elif lab == "table":
                r = "tbl"
            elif s in styles:
                r = "flow" if long or lab in HEADINGS else "~"
            elif long and lab in FLOW_TEXT:
                r = "flow"
            elif lab in ("figure_title", "vision_footnote"):
                r = "fig"
            else:
                r = "~" if lab in FLOW_TEXT else "?"
        elif lab == "table":
            r = "tbl"
        elif lab in FLOW_TEXT and long:
            r = "flow"
        elif lab in ("figure_title", "vision_footnote"):
            r = "fig"
        else:
            r = "~" if lab in FLOW_TEXT else "?"
        role[b["id"]] = r
    return role, styles


def connected_ink(img, region, masks, seeds, reach):
    """Bounding box of the ink inside region connected (within `reach` pixels) to the seed boxes; other blocks'
    boxes (`masks`) hold no ink."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in region]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    ink = (img[y1:y2, x1:x2] < INK).any(axis=2)
    for m in masks:
        mx1, my1, mx2, my2 = [int(round(v)) for v in m]
        ink[max(0, my1 - y1):max(0, my2 - y1), max(0, mx1 - x1):max(0, mx2 - x1)] = False
    if not ink.any():
        return None
    r = max(1, int(reach))
    grown = cv2.dilate(ink.astype(np.uint8), np.ones((2 * r + 1, 2 * r + 1), np.uint8))
    _, lab = cv2.connectedComponents(grown, connectivity=4)
    keep = set()
    for s in seeds:
        sx1, sy1 = max(0, int(round(s[0])) - x1), max(0, int(round(s[1])) - y1)
        sx2, sy2 = min(ink.shape[1], int(round(s[2])) - x1), min(ink.shape[0], int(round(s[3])) - y1)
        if sx2 > sx1 and sy2 > sy1:
            keep |= set(np.unique(lab[sy1:sy2, sx1:sx2]).tolist()) - {0}
    if not keep:
        return None
    ys, xs = np.nonzero(np.isin(lab, list(keep)) & ink)
    if len(ys) == 0:
        return None
    return [x1 + int(xs.min()), y1 + int(ys.min()), x1 + int(xs.max()) + 1, y1 + int(ys.max()) + 1]


def second_opinion(pblocks: list[dict], role: dict, size: tuple, img, whole: list | None, lines_in=None) -> dict:
    """caption id -> the box of its figure grown out from the caption (None when nothing grows), on one page.
    pblocks: the page's blocks; whole: the layout model's boxes on the page; lines_in(region, width): the body-text
    lines in a region, with a text layer."""
    W, H = size
    row = ROW * H
    gap = GAP_ROWS * row
    top_bound = max([b["box"][3] for b in pblocks if role.get(b["id"]) == "noise" and b["box"][3] < MARGIN * H] + [0])
    bot_bound = min([b["box"][1] for b in pblocks if role.get(b["id"]) == "noise" and b["box"][1] > (1 - MARGIN) * H] + [H])
    caps = [b for b in pblocks if role.get(b["id"]) == "caption"]
    claimed = {}
    pics = [f["box"] for f in whole or [] if f["label"] in ("image", "chart") and not any(
        role.get(x["id"]) in ("flow", "caption", "tcaption") and box_overlap(f["box"], x["box"]) > SWALLOW * box_area(x["box"])
        for x in pblocks)]

    def together(a, b):
        return any(box_overlap(q, a) >= COVER * max(1, box_area(a)) and box_overlap(q, b) >= COVER * max(1, box_area(b))
                   for q in pics)

    def is_stop(b, cid):
        if role.get(b["id"]) in ("flow", "caption", "tcaption", "noise"):
            return b["id"] != cid
        if b["id"] in claimed and claimed[b["id"]] != cid:
            return True
        if b["label"] in HEADINGS:
            # a section heading has running text right under it in its column; any other title is the figure's
            return any(role.get(x["id"]) == "flow" and 0 <= x["box"][1] - b["box"][3] <= HEADING_ROWS * row
                       and hov(x["box"], b["box"]) > 0 for x in pblocks)
        if role.get(b["id"]) == "tbl":                      # a table with its own caption
            return any(role.get(x["id"]) == "tcaption" and hov(x["box"], b["box"]) > 0
                       and (0 <= b["box"][1] - x["box"][3] <= TABLE_ROWS * row or 0 <= x["box"][1] - b["box"][3] <= TABLE_ROWS * row)
                       for x in pblocks)
        return False

    def own_caption(b, cid):
        return any(d["id"] != cid and hov(d["box"], b["box"]) > 0.5 * (b["box"][2] - b["box"][0])
                   and 0 <= d["box"][1] - b["box"][3] <= OWN_ROWS * row for d in caps)

    def blocked(b, box, cid):
        lo, hi = (b, box) if b[3] <= box[1] else (box, b)
        if lo[3] > hi[1]:
            return False
        return any(is_stop(x, cid) and x["box"][1] >= lo[3] - row and x["box"][3] <= hi[1] + row
                   and hov(x["box"], b) > 0 and hov(x["box"], box) > 0 for x in pblocks)

    def grow(c, direction):
        cid, cb = c["id"], c["box"]
        cand = [b for b in pblocks if role.get(b["id"]) in ("fig", "?", "tbl", "~") and not is_stop(b, cid)]
        if direction == "up":
            cand = [b for b in cand if b["box"][3] <= cb[1] + row]
            seeds = [b for b in cand if cb[1] - b["box"][3] <= SEED_ROWS * row and hov(b["box"], cb) > 0]
        else:
            cand = [b for b in cand if b["box"][1] >= cb[3] - row]
            seeds = [b for b in cand if b["box"][1] - cb[3] <= SEED_ROWS * row and hov(b["box"], cb) > 0]
        members = [b for b in seeds if role.get(b["id"]) in ("fig", "tbl") and not own_caption(b, cid) and not blocked(b["box"], cb, cid)]
        grew = bool(members)
        while grew:
            grew = False
            ub = box_union([m["box"] for m in members])
            for b in cand:
                if b in members:
                    continue
                bb = b["box"]
                if role.get(b["id"]) in ("fig", "tbl"):
                    near = (gap_y(bb, ub) <= gap and gap_x(bb, ub) <= gap) or any(together(bb, m["box"]) for m in members)
                else:
                    near = (gap_y(bb, ub) <= TOUCH_ROWS * row and hov(bb, ub) >= 0.5 * (bb[2] - bb[0])) \
                        or box_overlap(bb, ub) >= 0.8 * max(1, box_area(bb)) or any(together(bb, m["box"]) for m in members)
                if near and not own_caption(b, cid) and not blocked(bb, ub, cid):
                    members.append(b)
                    grew = True
                    ub = box_union([m["box"] for m in members])
        return members

    found = {}
    for direction in ("up", "down"):
        for c in sorted(caps, key=lambda c: c["box"][1]):
            if c["id"] not in found and (members := grow(c, direction)):
                found[c["id"]] = (direction, members)
                for m in members:
                    claimed[m["id"]] = c["id"]
    out = {}
    for c in caps:
        if c["id"] not in found:
            out[c["id"]] = None
            continue
        direction, members = found[c["id"]]
        cid, cb = c["id"], c["box"]
        ub = box_union([m["box"] for m in members])
        x1, x2 = min(ub[0], cb[0]), max(ub[2], cb[2])
        xs = [x1, 0, x2, 0]
        if direction == "up":
            stops = [b["box"][3] for b in pblocks if is_stop(b, cid) and b["box"][3] <= ub[1] + row and hov(b["box"], xs) > 0]
            region = [x1, max(stops + [top_bound, ub[1] - gap]), x2, cb[1]]
        else:
            stops = [b["box"][1] for b in pblocks if is_stop(b, cid) and b["box"][1] >= ub[3] - row and hov(b["box"], xs) > 0]
            region = [x1, cb[3], x2, min(stops + [bot_bound, ub[3] + gap])]
        if lines_in:
            # running text a picture box overreaches: body lines at the far edge cap the figure
            flows = sorted(b["box"][2] - b["box"][0] for b in pblocks if role.get(b["id"]) == "flow")
            width = flows[len(flows) // 2] if flows else x2 - x1
            far = [x1, min(region[1], ub[1]), x2, region[3]] if direction == "up" else [x1, region[1], x2, max(region[3], ub[3])]
            edge = far[1] if direction == "up" else far[3]
            for i, (y1, y2) in enumerate(sorted(lines_in(far, min(width, x2 - x1)), reverse=direction != "up")):
                reach = FIRST_LINE * H if i == 0 else 3 * row
                if direction == "up" and y1 <= edge + reach:
                    edge = max(edge, y2)
                elif direction == "down" and y2 >= edge - reach:
                    edge = min(edge, y1)
                else:
                    break
            region[1] = max(region[1], edge) if direction == "up" else region[1]
            region[3] = min(region[3], edge) if direction == "down" else region[3]
        clipped = [[max(m["box"][0], region[0]), max(m["box"][1], region[1]), min(m["box"][2], region[2]), min(m["box"][3], region[3])]
                   for m in members]
        clipped = [b for b in clipped if b[2] > b[0] and b[3] > b[1]]
        ids = {m["id"] for m in members}
        ink = connected_ink(img, region, [b["box"] for b in pblocks if b["id"] not in ids], clipped, 0.5 * row) if clipped else None
        box = box_union(clipped + ([ink] if ink else [])) if clipped else None
        out[cid] = [int(v) for v in box] if box else None
    return out


# ---------------------------------------------------------------- the checks

def edge_marks(img, crops: list[dict], height: float) -> list[int]:
    """Per side (top, bottom, left, right), the ink components (8-connected) inside the crops that run on past
    the side, summed over the crops."""
    ink = (img < INK).any(axis=2)
    m = max(4, int(0.6 * ROW * height))
    cut = [0, 0, 0, 0]
    for cr in crops:
        x1, y1, x2, y2 = [int(v) for v in cr["box"]]
        X1, Y1, X2, Y2 = max(0, x1 - m), max(0, y1 - m), min(ink.shape[1], x2 + m), min(ink.shape[0], y2 + m)
        _, lab = cv2.connectedComponents(ink[Y1:Y2, X1:X2].astype(np.uint8), connectivity=8)
        ox1, oy1, ox2, oy2 = x1 - X1, y1 - Y1, x2 - X1, y2 - Y1
        inside = set(np.unique(lab[max(0, oy1):oy2, max(0, ox1):ox2]).tolist()) - {0}
        sides = (lab[:max(0, oy1 - CUT_EDGE), max(0, ox1):ox2], lab[oy2 + CUT_EDGE:, max(0, ox1):ox2],
                 lab[max(0, oy1):oy2, :max(0, ox1 - CUT_EDGE)], lab[max(0, oy1):oy2, ox2 + CUT_EDGE:])
        for i, out in enumerate(sides):
            cut[i] += len((set(np.unique(out).tolist()) - {0}) & inside)
    return cut


def two_figures(c: dict, crops: list[tuple], pblocks: list[dict], height: float, text_in) -> list[str]:
    """Why a crop of caption c serves another figure too: another caption inside it, a caption line of another
    figure in its text layer (text_in(box) -> text, or None without one), two captions side by side under it.
    crops: (number, figure)."""
    reach = UNCROPPED_REACH * height
    caps = [b for b in pblocks if is_figure_caption(b) or is_table_caption(b)]
    own = C.figure_id(c)
    cols = lambda a, b: min(a[2], b[2]) > max(a[0], b[0])
    why = []
    for n, cr in crops:
        r = cr["box"]
        held = [d for d in caps if d is not c and box_overlap(d["box"], r) >= 0.5 * max(1, box_area(d["box"]))]
        if held:
            why.append(f"crop {n} holds the caption \"{held[0]['text'].strip()[:40]}\"")
        elif text_in and (text := text_in(r)):
            for m in C.CAPTION_LINE.finditer(text):
                kind, ident = m.group(3).lower(), (" ".join((m.group(2) or "").lower().split()), m.group(4).upper())
                if kind == "table" or ident != own:
                    why.append(f"crop {n} has the caption line \"{m.group(0).strip()}\" in it")
                    break
        below = [d for d in caps if cols(r, d["box"]) and 0 <= d["box"][1] - r[3] <= reach]
        above = [d for d in caps if cols(r, d["box"]) and 0 <= r[1] - d["box"][3] <= reach]
        pair = lambda ds: any(min(a["box"][3], b["box"][3]) > max(a["box"][1], b["box"][1]) and not cols(a["box"], b["box"])
                              for a in ds for b in ds if a is not b)
        if pair(below) or (not below and pair(above)):
            why.append(f"two captions side by side {'under' if below else 'over'} crop {n}")
    return why


def side_words(cur, s, row) -> list[str]:
    """How far the second opinion's box s sits from the crops' box cur, side by side, beyond one row."""
    out = []
    for side, d, outward in (("top", cur[1] - s[1], "above"), ("bottom", s[3] - cur[3], "below"),
                             ("left", cur[0] - s[0], "left of"), ("right", s[2] - cur[2], "right of")):
        if abs(d) / row > 1:
            inward = {"above": "below", "below": "above", "left of": "right of", "right of": "left of"}[outward]
            out.append(f"its {side} edge is {abs(d) / row:.1f} rows {outward if d > 0 else inward} the crop's")
    return out


def finding_of(page: int, c: dict, reasons: list[str], crops: list[tuple], opinion: list | None) -> dict:
    """The figure_check finding of caption c: the reason codes in items, the reasons in full in detail, its crops
    as (number, figure) and the second opinion's box."""
    out = {"id": f"figure_check@{c['id']}", "code": "figure_check", "page": page, "block": c["id"],
           "items": [r.split(":")[0] for r in reasons], "detail": "; ".join(reasons)}
    if crops:
        out["crops"] = [{"n": n, "figure": cr["id"], "box": cr["box"], "page": cr["page"]} for n, cr in crops]
    if opinion:
        out["second_opinion"] = opinion
    return out


def figure_findings(blocks: list[dict], figures: list[dict], sizes: dict, layers: dict | None = None, text_in=None,
                    image_of=None, layout_of=None, settled=frozenset()) -> list[dict]:
    """figure_check findings, one per caption that fails a check, in page order.

    blocks: the document's blocks in reading order; figures: its figures, the crops, in reading order (a page's
    crops are numbered in this order, as draw_overlay numbers them); sizes: page -> (width, height) of the page
    images the boxes refer to; layers: page -> font_chars or None (no text layer); text_in(page, box) -> the text
    layer's text inside a box, or None; image_of(page) -> the page image (BGR) or None, without which edge_cut and
    the second opinion are left out; layout_of(page) -> the layout model's boxes or None; settled: the ids of
    figures an agent has recropped, whose captions are not checked."""
    layers = layers or {}
    role, styles = classify([b for b in blocks if b["box"]], layers)
    out, prev = [], None
    for page in sorted(sizes):
        prev = prev if prev and prev["page"] == page - 1 else None
        w, h = sizes[page]
        row = ROW * h
        pblocks = [b for b in blocks if b["page"] == page and b["box"]]
        pfigures = [f for f in figures if f["page"] == page]
        captions = [b for b in pblocks if is_figure_caption(b)]
        mine, loose = owners(pfigures, captions, h)
        numbered = {cr["id"]: n for n, cr in enumerate(pfigures, 1)}
        img = image_of(page) if image_of and captions else None
        opinion = {}
        if img is not None and captions:
            chars = layers.get(page)
            lines_in = (lambda region, width: body_lines(chars, region, styles, width)) if chars else None
            opinion = second_opinion(pblocks, role, (w, h), img, layout_of(page) if layout_of else None, lines_in)
        tables = [b for b in pblocks if b["label"] == "table"]
        near = lambda a, b: min(a[2], b[2]) > max(a[0], b[0]) and (0 <= b[1] - a[3] <= UNCROPPED_REACH * h
                                                                   or 0 <= a[1] - b[3] <= UNCROPPED_REACH * h)
        swallowed = {cr["id"]: t for t in pblocks if is_table_caption(t) and not any(near(t["box"], x["box"]) for x in tables)
                     for cr in pfigures if near(t["box"], cr["box"])}
        cropped = {C.figure_id(c) for c in captions if c["id"] in mine}
        top_caption = min((c for c in captions if c["id"] not in mine and c["box"][1] < h / 3), key=lambda c: c["box"][1], default=None)
        for c in captions:
            crops = mine.get(c["id"], [])
            if not crops:
                if prev and c is top_caption and len(prev["loose"]) >= 2:
                    if any(cr["id"] in settled for cr in prev["loose"]):
                        continue                            # an agent recropped the figure on the page before
                    reasons = [f"split: the figure on page {prev['page']} is in {len(prev['loose'])} crops"]
                    listed = [(prev["numbered"][cr["id"]], cr) for cr in prev["loose"]]
                elif C.figure_id(c) in cropped or (prev and c["box"][1] < h / 3):
                    continue
                else:
                    reasons, listed = ["no_crop: no crop beside this caption"], []
                out.append(finding_of(page, c, reasons, listed, opinion.get(c["id"])))
                continue
            if any(cr["id"] in settled for cr in crops):
                continue                                    # an agent recropped this figure
            listed, reasons = [(numbered[cr["id"]], cr) for cr in crops], []
            if len(crops) >= 2:
                reasons.append(f"split: {len(crops)} crops")
            if why := two_figures(c, listed, pblocks, h, text_in and (lambda box: text_in(page, box))):
                reasons.append("two_figures: " + "; ".join(why))
            if t := next((swallowed[cr["id"]] for cr in crops if cr["id"] in swallowed), None):
                reasons.append(f"table: \"{t['text'].strip()[:40]}\" has no table of its own next to it; the table is likely in the crop")
            if img is not None:
                cuts = [f"the {side} edge cuts through {n} marks"
                        for side, n in zip(("top", "bottom", "left", "right"), edge_marks(img, crops, h)) if n >= CUT_MARKS]
                if cuts:
                    reasons.append("edge_cut: " + "; ".join(cuts))
                if (s := opinion.get(c["id"])) and (sides := side_words(box_union([cr["box"] for cr in crops]), s, row)):
                    reasons.append("second_opinion: " + "; ".join(sides))
            if reasons:
                out.append(finding_of(page, c, reasons, listed, opinion.get(c["id"])))
        # a page that ends in a crop no caption takes is a figure page; its caption opens the next page
        prev = {"page": page, "loose": loose, "numbered": numbered} if any(cr["box"][3] > h / 2 for cr in loose) else None
    return out


# ---------------------------------------------------------------- output

def draw_overlay(img, finding: dict, figures_on_page: list[dict], caption_block: dict | None, path: Path) -> None:
    """The page with the finding's caption (blue), every crop on the page numbered in its own colour, and the second
    opinion (green, dashed), each box drawn OFFSET pixels outside its edge so that it covers nothing; written as PNG.
    figures_on_page: the page's figures in the order figure_findings had them, so that the numbers are the
    finding's; caption_block: None when the caption is on another page."""
    out = img.copy()
    h, wd = out.shape[:2]
    grow = lambda b: (max(0, int(b[0]) - OFFSET), max(0, int(b[1]) - OFFSET), min(wd - 1, int(b[2]) + OFFSET), min(h - 1, int(b[3]) + OFFSET))
    for n, cr in enumerate(figures_on_page, 1):
        x1, y1, x2, y2 = grow(cr["box"])
        colour = PALETTE[(n - 1) % len(PALETTE)]
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 3)
        label = str(n)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.rectangle(out, (x1, y1), (x1 + tw + 8, y1 + th + 10), colour, -1)
        cv2.putText(out, label, (x1 + 4, y1 + th + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    if caption_block:
        x1, y1, x2, y2 = grow(caption_block["box"])
        cv2.rectangle(out, (x1, y1), (x2, y2), (230, 80, 0), 3)
    if s := finding.get("second_opinion"):
        x1, y1, x2, y2 = grow([s[0] - OFFSET, s[1] - OFFSET, s[2] + OFFSET, s[3] + OFFSET])
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            length = int(np.hypot(b[0] - a[0], b[1] - a[1]))
            for t in range(0, length, 24):
                p = (int(a[0] + (b[0] - a[0]) * t / length), int(a[1] + (b[1] - a[1]) * t / length))
                q = (int(a[0] + (b[0] - a[0]) * min(length, t + 14) / length), int(a[1] + (b[1] - a[1]) * min(length, t + 14) / length))
                cv2.line(out, p, q, (0, 170, 0), 3)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cv2.imencode(".png", out)[1].tobytes())
