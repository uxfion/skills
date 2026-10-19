"""The figure check of parse.py: after the figures are grouped, each figure caption is checked against its crops, and
a figure whose crops do not hold up is reported as a figure_check warning, drawn in an overlay and noted in the
Markdown, for the agent to judge when a task uses it.

A check asks what must hold for a caption and its crops, not what kind of figure it is (2026-10: 115 papers, 1138
captions, graded blind: every one of 138 severe errors reported, 86% of the good figures passed):
  no_crop         no crop goes with the caption: the figure was read as text or a table, or missed
  split           two or more crops go with it, or, across a page break, the page before ends in uncaptioned pieces
  two_figures     a crop of it also holds another caption, or two captions sit side by side under one crop
  table           a table caption with no table near it sits by its crop: the table was drawn into the figure
  edge_cut        a side of its crops cuts through three or more marks (text, lines)
  second_opinion  the extent found from the caption outwards differs from its crops by more than a text row

The second opinion grows each caption's figure out from the caption until running text, another caption or a
section heading stops it, taking every block in between whatever its label; roles come from the PDF text layer
(body font and size) before geometry, whole-figure boxes and VL labels (spec 20261019, §3.2 and its appendix).

Runs in the paddleocr tool environment (numpy, cv2, pypdfium2); `parse` is the running parse.py."""
from __future__ import annotations

import ctypes
import re
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

import parse as P

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
NOTE = re.compile(r"<!-- (figure_check|figure kept|from page image)\b[^\n]*?\[(p\d+#\d+)[^\]\n]*\] -->")
CAPTION_LINE = re.compile(r"(?mi)^\s*(\*\*)?\s*(extended\s+data\s+|supplementary\s+)?(figure|fig\.|table)\s*([A-Z]?\d+)\s*(\*\*)?\s*[.:|]")
PALETTE = [(0, 0, 230), (0, 140, 255), (200, 0, 200), (150, 50, 0), (0, 160, 160), (90, 0, 140), (0, 90, 200)]  # BGR


def hov(a, b) -> float:
    return min(a[2], b[2]) - max(a[0], b[0])


def gap_y(a, b) -> float:
    return max(0, a[1] - b[3], b[1] - a[3])


def gap_x(a, b) -> float:
    return max(0, a[0] - b[2], b[0] - a[2])


def is_figure_caption(b: dict) -> bool:
    """A figure caption: is_caption, or a heading whose text is one ("Figure 2: ..." labelled paragraph_title)."""
    return bool(b["bbox"]) and (P.is_caption(b) or (b["label"] in HEADINGS and bool(P.CAPTION_TEXT.match(b["text"].strip()))))


def is_table_caption(b: dict) -> bool:
    """A table caption, held to the rule for figure captions: a text block needs punctuation after the number,
    as "Table 3 lists ..." opens running text."""
    if not b["bbox"] or not P.is_table_caption(b):
        return False
    return b["label"] in ("figure_title", "table_title") or bool(re.match(P.TABLE_CAPTION.pattern + r"\s*(\*\*)?\s*[.:|]", b["text"].strip(), re.I))


def is_crop(b: dict) -> bool:
    return bool(b["bbox"]) and (b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b))


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
        if b["label"] == "text" and len(b["text"]) >= P.LONG_TEXT and (s := style_of(under(layers.get(b["page"]), b["bbox"]))):
            body[s] += 1
    styles = {s for s, n in body.items() if n >= max(2, BODY_SHARE * sum(body.values()))}
    role = {}
    for b in blocks:
        lab, t, chars = b["label"], b["text"], layers.get(b["page"])
        long = len(t) >= P.LONG_TEXT
        if lab in NOISE:
            r = "noise"
        elif is_figure_caption(b):
            r = "caption"
        elif P.is_table_caption(b):
            r = "tcaption"
        elif lab in FIGLIKE:
            r = "fig"
        elif lab in ("doc_title", "abstract"):
            r = "flow"
        elif chars and len(chars) >= LAYER_CHARS:
            cs = under(chars, b["bbox"])
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
    pblocks: the page's blocks without grouped "figure" blocks; whole: the layout model's whole-figure boxes;
    lines_in(region, width): the body-text lines in a region, with a text layer."""
    W, H = size
    row = P.ROW * H
    gap = GAP_ROWS * row
    top_bound = max([b["bbox"][3] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][3] < MARGIN * H] + [0])
    bot_bound = min([b["bbox"][1] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][1] > (1 - MARGIN) * H] + [H])
    caps = [b for b in pblocks if role.get(b["id"]) == "caption"]
    claimed = {}
    pics = [f["bbox"] for f in whole or [] if f["label"] in ("image", "chart") and not any(
        role.get(x["id"]) in ("flow", "caption", "tcaption") and P.box_overlap(f["bbox"], x["bbox"]) > P.SWALLOW * P.box_area(x["bbox"])
        for x in pblocks)]

    def together(a, b):
        return any(P.box_overlap(q, a) >= P.COVER * max(1, P.box_area(a)) and P.box_overlap(q, b) >= P.COVER * max(1, P.box_area(b))
                   for q in pics)

    def is_stop(b, cid):
        if role.get(b["id"]) in ("flow", "caption", "tcaption", "noise"):
            return b["id"] != cid
        if b["id"] in claimed and claimed[b["id"]] != cid:
            return True
        if b["label"] in HEADINGS:
            # a section heading has running text right under it in its column; any other title is the figure's
            return any(role.get(x["id"]) == "flow" and 0 <= x["bbox"][1] - b["bbox"][3] <= HEADING_ROWS * row
                       and hov(x["bbox"], b["bbox"]) > 0 for x in pblocks)
        if role.get(b["id"]) == "tbl":                      # a table with its own caption
            return any(role.get(x["id"]) == "tcaption" and hov(x["bbox"], b["bbox"]) > 0
                       and (0 <= b["bbox"][1] - x["bbox"][3] <= TABLE_ROWS * row or 0 <= x["bbox"][1] - b["bbox"][3] <= TABLE_ROWS * row)
                       for x in pblocks)
        return False

    def own_caption(b, cid):
        return any(d["id"] != cid and hov(d["bbox"], b["bbox"]) > 0.5 * (b["bbox"][2] - b["bbox"][0])
                   and 0 <= d["bbox"][1] - b["bbox"][3] <= OWN_ROWS * row for d in caps)

    def blocked(b, box, cid):
        lo, hi = (b, box) if b[3] <= box[1] else (box, b)
        if lo[3] > hi[1]:
            return False
        return any(is_stop(x, cid) and x["bbox"][1] >= lo[3] - row and x["bbox"][3] <= hi[1] + row
                   and hov(x["bbox"], b) > 0 and hov(x["bbox"], box) > 0 for x in pblocks)

    def grow(c, direction):
        cid, cb = c["id"], c["bbox"]
        cand = [b for b in pblocks if role.get(b["id"]) in ("fig", "?", "tbl", "~") and not is_stop(b, cid)]
        if direction == "up":
            cand = [b for b in cand if b["bbox"][3] <= cb[1] + row]
            seeds = [b for b in cand if cb[1] - b["bbox"][3] <= SEED_ROWS * row and hov(b["bbox"], cb) > 0]
        else:
            cand = [b for b in cand if b["bbox"][1] >= cb[3] - row]
            seeds = [b for b in cand if b["bbox"][1] - cb[3] <= SEED_ROWS * row and hov(b["bbox"], cb) > 0]
        members = [b for b in seeds if role.get(b["id"]) in ("fig", "tbl") and not own_caption(b, cid) and not blocked(b["bbox"], cb, cid)]
        grew = bool(members)
        while grew:
            grew = False
            ub = P.box_union([m["bbox"] for m in members])
            for b in cand:
                if b in members:
                    continue
                bb = b["bbox"]
                if role.get(b["id"]) in ("fig", "tbl"):
                    near = (gap_y(bb, ub) <= gap and gap_x(bb, ub) <= gap) or any(together(bb, m["bbox"]) for m in members)
                else:
                    near = (gap_y(bb, ub) <= TOUCH_ROWS * row and hov(bb, ub) >= 0.5 * (bb[2] - bb[0])) \
                        or P.box_overlap(bb, ub) >= 0.8 * max(1, P.box_area(bb)) or any(together(bb, m["bbox"]) for m in members)
                if near and not own_caption(b, cid) and not blocked(bb, ub, cid):
                    members.append(b)
                    grew = True
                    ub = P.box_union([m["bbox"] for m in members])
        return members

    found = {}
    for direction in ("up", "down"):
        for c in sorted(caps, key=lambda c: c["bbox"][1]):
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
        cid, cb = c["id"], c["bbox"]
        ub = P.box_union([m["bbox"] for m in members])
        x1, x2 = min(ub[0], cb[0]), max(ub[2], cb[2])
        xs = [x1, 0, x2, 0]
        if direction == "up":
            stops = [b["bbox"][3] for b in pblocks if is_stop(b, cid) and b["bbox"][3] <= ub[1] + row and hov(b["bbox"], xs) > 0]
            region = [x1, max(stops + [top_bound, ub[1] - gap]), x2, cb[1]]
        else:
            stops = [b["bbox"][1] for b in pblocks if is_stop(b, cid) and b["bbox"][1] >= ub[3] - row and hov(b["bbox"], xs) > 0]
            region = [x1, cb[3], x2, min(stops + [bot_bound, ub[3] + gap])]
        if lines_in:
            # running text a picture box overreaches: body lines at the far edge cap the figure
            flows = sorted(b["bbox"][2] - b["bbox"][0] for b in pblocks if role.get(b["id"]) == "flow")
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
        clipped = [[max(m["bbox"][0], region[0]), max(m["bbox"][1], region[1]), min(m["bbox"][2], region[2]), min(m["bbox"][3], region[3])]
                   for m in members]
        clipped = [b for b in clipped if b[2] > b[0] and b[3] > b[1]]
        ids = {m["id"] for m in members}
        ink = connected_ink(img, region, [b["bbox"] for b in pblocks if b["id"] not in ids], clipped, 0.5 * row) if clipped else None
        box = P.box_union(clipped + ([ink] if ink else [])) if clipped else None
        out[cid] = [int(v) for v in box] if box else None
    return out


# ---------------------------------------------------------------- the checks

def owners(pblocks: list[dict], captions: list[dict], height: float) -> tuple[dict, list]:
    """caption id -> its crops (in block order), and the crops no caption takes: each crop goes with the nearest
    caption below it sharing its columns, else the nearest above it (captions set above figures)."""
    reach = P.UNCROPPED_REACH * height
    mine, loose = {}, []
    for cr in (b for b in pblocks if is_crop(b)):
        x1, y1, x2, y2 = cr["bbox"]
        cols = [c for c in captions if min(x2, c["bbox"][2]) > max(x1, c["bbox"][0])]
        below = [c for c in cols if y1 < c["bbox"][1] and y2 <= c["bbox"][3] and c["bbox"][1] - y2 <= reach]
        above = [c for c in cols if c["bbox"][1] <= y1 and c["bbox"][3] < y2 and y1 - c["bbox"][3] <= reach]
        if below or above:
            c = min(below, key=lambda c: c["bbox"][1]) if below else max(above, key=lambda c: c["bbox"][3])
            mine.setdefault(c["id"], []).append(cr)
        else:
            loose.append(cr)
    return mine, loose


def edge_marks(img, crops: list[dict], height: float) -> list[int]:
    """Per side (top, bottom, left, right), the ink components (8-connected) inside the crops that run on past
    the side, summed over the crops."""
    ink = (img < INK).any(axis=2)
    m = max(4, int(0.6 * P.ROW * height))
    cut = [0, 0, 0, 0]
    for cr in crops:
        x1, y1, x2, y2 = [int(v) for v in cr["bbox"]]
        X1, Y1, X2, Y2 = max(0, x1 - m), max(0, y1 - m), min(ink.shape[1], x2 + m), min(ink.shape[0], y2 + m)
        _, lab = cv2.connectedComponents(ink[Y1:Y2, X1:X2].astype(np.uint8), connectivity=8)
        ox1, oy1, ox2, oy2 = x1 - X1, y1 - Y1, x2 - X1, y2 - Y1
        inside = set(np.unique(lab[max(0, oy1):oy2, max(0, ox1):ox2]).tolist()) - {0}
        sides = (lab[:max(0, oy1 - CUT_EDGE), max(0, ox1):ox2], lab[oy2 + CUT_EDGE:, max(0, ox1):ox2],
                 lab[max(0, oy1):oy2, :max(0, ox1 - CUT_EDGE)], lab[max(0, oy1):oy2, ox2 + CUT_EDGE:])
        for i, out in enumerate(sides):
            cut[i] += len((set(np.unique(out).tolist()) - {0}) & inside)
    return cut


def two_figures(c: dict, crops: list[dict], pblocks: list[dict], height: float, text_in) -> list[str]:
    """Why a crop of caption c serves another figure too: another caption inside it, a caption line of another
    figure in its text layer (text_in(box) -> text, or None without one), two captions side by side under it."""
    reach = P.UNCROPPED_REACH * height
    caps = [b for b in pblocks if is_figure_caption(b) or is_table_caption(b)]
    own = P.figure_id(c)
    cols = lambda a, b: min(a[2], b[2]) > max(a[0], b[0])
    why = []
    for n, cr in crops:
        r = cr["bbox"]
        held = [d for d in caps if d is not c and P.box_overlap(d["bbox"], r) >= 0.5 * max(1, P.box_area(d["bbox"]))]
        if held:
            why.append(f"crop {n} holds the caption \"{held[0]['text'].strip()[:40]}\"")
        elif text_in and (text := text_in(r)):
            for m in CAPTION_LINE.finditer(text):
                kind, ident = m.group(3).lower(), (" ".join((m.group(2) or "").lower().split()), m.group(4).upper())
                if kind == "table" or ident != own:
                    why.append(f"crop {n} has the caption line \"{m.group(0).strip()}\" in it")
                    break
        below = [d for d in caps if cols(r, d["bbox"]) and 0 <= d["bbox"][1] - r[3] <= reach]
        above = [d for d in caps if cols(r, d["bbox"]) and 0 <= r[1] - d["bbox"][3] <= reach]
        pair = lambda ds: any(min(a["bbox"][3], b["bbox"][3]) > max(a["bbox"][1], b["bbox"][1]) and not cols(a["bbox"], b["bbox"])
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


def figure_warnings(blocks: list[dict], sizes: dict, layers: dict | None = None, text_in=None, image_of=None,
                    layout_of=None) -> list[dict]:
    """figure_check warnings, one per caption that fails a check, in page order.

    sizes: page -> (width, height) of the page images the boxes refer to; layers: page -> font_chars or None (no
    text layer); text_in(page, box) -> the text layer's text inside a box, or None; image_of(page) -> the page image
    (BGR) or None, without which edge_cut and the second opinion are left out; layout_of(page) -> the layout
    model's whole-figure boxes or None."""
    layers = layers or {}
    vl = [b for b in blocks if b["bbox"] and b["label"] != "figure"]
    role, styles = classify(vl, layers)
    out, prev = [], None
    for page in sorted(sizes):
        prev = prev if prev and prev["page"] == page - 1 else None
        w, h = sizes[page]
        row = P.ROW * h
        pblocks = [b for b in blocks if b["page"] == page and b["bbox"]]
        captions = [b for b in pblocks if is_figure_caption(b)]
        mine, loose = owners(pblocks, captions, h)
        numbered = {cr["id"]: n for n, cr in enumerate((b for b in pblocks if is_crop(b)), 1)}
        img = image_of(page) if image_of and captions else None
        opinion = {}
        if img is not None and captions:
            chars = layers.get(page)
            lines_in = (lambda region, width: body_lines(chars, region, styles, width)) if chars else None
            opinion = second_opinion([b for b in vl if b["page"] == page], role, (w, h), img,
                                     layout_of(page) if layout_of else None, lines_in)
        tables = [b for b in pblocks if b["label"] == "table"]
        near = lambda a, b: min(a[2], b[2]) > max(a[0], b[0]) and (0 <= b[1] - a[3] <= P.UNCROPPED_REACH * h
                                                                   or 0 <= a[1] - b[3] <= P.UNCROPPED_REACH * h)
        swallowed = {cr["id"]: t for t in pblocks if is_table_caption(t) and not any(near(t["bbox"], x["bbox"]) for x in tables)
                     for cr in pblocks if is_crop(cr) and near(t["bbox"], cr["bbox"])}
        cropped = {P.figure_id(c) for c in captions if c["id"] in mine}
        top_caption = min((c for c in captions if c["id"] not in mine and c["bbox"][1] < h / 3), key=lambda c: c["bbox"][1], default=None)
        for c in captions:
            crops = mine.get(c["id"], [])
            warn = {"code": "figure_check", "page": page, "block": c["id"], "detail": c["text"].strip()[:100], "reasons": []}
            if not crops:
                if prev and c is top_caption and len(prev["loose"]) >= 2:
                    warn["reasons"].append(f"split: the figure on page {prev['page']} is in {len(prev['loose'])} crops")
                    warn["crops"] = [{"n": prev["numbered"][cr["id"]], "page": prev["page"], "block": cr["id"], "bbox": cr["bbox"],
                                      **({"image": cr["image"]} if cr.get("image") else {})} for cr in prev["loose"]]
                elif P.figure_id(c) in cropped or (prev and c["bbox"][1] < h / 3):
                    continue
                else:
                    warn["reasons"].append("no_crop: no crop beside this caption")
                if opinion.get(c["id"]):
                    warn["second_opinion"] = opinion[c["id"]]
                out.append(warn)
                continue
            listed = [(numbered[cr["id"]], cr) for cr in crops]
            if len(crops) >= 2:
                warn["reasons"].append(f"split: {len(crops)} crops")
            if why := two_figures(c, listed, pblocks, h, text_in and (lambda box: text_in(page, box))):
                warn["reasons"].append("two_figures: " + "; ".join(why))
            if t := next((swallowed[cr["id"]] for cr in crops if cr["id"] in swallowed), None):
                warn["reasons"].append(f"table: \"{t['text'].strip()[:40]}\" has no table of its own next to it; the table is likely in the crop")
            if img is not None:
                cuts = [f"the {side} edge cuts through {n} marks"
                        for side, n in zip(("top", "bottom", "left", "right"), edge_marks(img, crops, h)) if n >= CUT_MARKS]
                if cuts:
                    warn["reasons"].append("edge_cut: " + "; ".join(cuts))
                if (s := opinion.get(c["id"])) and (sides := side_words(P.box_union([cr["bbox"] for cr in crops]), s, row)):
                    warn["reasons"].append("second_opinion: " + "; ".join(sides))
            if warn["reasons"]:
                warn["crops"] = [{"n": n, "block": cr["id"], "bbox": cr["bbox"], **({"image": cr["image"]} if cr.get("image") else {})}
                                 for n, cr in listed]
                if opinion.get(c["id"]):
                    warn["second_opinion"] = opinion[c["id"]]
                out.append(warn)
        # a page that ends in a crop no caption takes is a figure page; its caption opens the next page
        prev = {"page": page, "loose": loose, "numbered": numbered} if any(cr["bbox"][3] > h / 2 for cr in loose) else None
    return out


# ---------------------------------------------------------------- output

def marker(w: dict) -> str:
    return f"p{w['page']}#{w['block']}"


def draw_overlay(img, w: dict, pblocks: list[dict], caption: dict | None, path: Path) -> None:
    """The page with this caption (blue), every crop on the page numbered in its own colour, and the second
    opinion (green, dashed), each box drawn OFFSET pixels outside its edge so that it covers nothing."""
    out = img.copy()
    h, wd = out.shape[:2]
    grow = lambda b: (max(0, int(b[0]) - OFFSET), max(0, int(b[1]) - OFFSET), min(wd - 1, int(b[2]) + OFFSET), min(h - 1, int(b[3]) + OFFSET))
    for n, cr in enumerate((b for b in pblocks if is_crop(b)), 1):
        x1, y1, x2, y2 = grow(cr["bbox"])
        colour = PALETTE[(n - 1) % len(PALETTE)]
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 3)
        label = str(n)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.rectangle(out, (x1, y1), (x1 + tw + 8, y1 + th + 10), colour, -1)
        cv2.putText(out, label, (x1 + 4, y1 + th + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    if caption:
        x1, y1, x2, y2 = grow(caption["bbox"])
        cv2.rectangle(out, (x1, y1), (x2, y2), (230, 80, 0), 3)
    if s := w.get("second_opinion"):
        x1, y1, x2, y2 = grow([s[0] - OFFSET, s[1] - OFFSET, s[2] + OFFSET, s[3] + OFFSET])
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            length = int(np.hypot(b[0] - a[0], b[1] - a[1]))
            for t in range(0, length, 24):
                p = (int(a[0] + (b[0] - a[0]) * t / length), int(a[1] + (b[1] - a[1]) * t / length))
                q = (int(a[0] + (b[0] - a[0]) * min(length, t + 14) / length), int(a[1] + (b[1] - a[1]) * min(length, t + 14) / length))
                cv2.line(out, p, q, (0, 170, 0), 3)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes())


def squash(text: str) -> str:
    return re.sub(r"\s+|\*\*", "", text).lower()


def annotate(markdown: str, warnings: list[dict], by_id: dict) -> str:
    """`markdown` with a note before each reported figure, once: before its first crop's image line, else before its
    caption's line on its page, else after its page marker. A figure's note is known by its marker (p<page>#<caption
    id>) whatever its state; a note still open ("figure_check:") whose figure is no longer reported goes."""
    lines = markdown.split("\n")
    known, current, drop = set(), {marker(w) for w in warnings}, set()
    for i, line in enumerate(lines):
        for m in NOTE.finditer(line):
            known.add(m.group(2))
            if m.group(1) == "figure_check" and m.group(2) not in current and line.strip() == m.group(0):
                drop.add(i)
    pages, page = {}, None
    for i, line in enumerate(lines):
        if m := re.fullmatch(r"<!-- page (\d+) -->", line.strip()):
            page = int(m.group(1))
            pages[page] = [i, i]
        elif page is not None:
            pages[page][1] = i
    before = {}
    for w in warnings:
        if marker(w) in known:
            continue
        reasons = "; ".join(w["reasons"]).replace("--", "–")
        tail = f" [{marker(w)}{' ' + w['overlay'] if w.get('overlay') else ''}] -->"
        at = None
        if first := (w.get("crops") or [{}])[0].get("image"):
            at = next((i for i, line in enumerate(lines) if f"({first})" in line), None)
        if at is None and w["page"] in pages:
            lo, hi = pages[w["page"]]
            head = squash(by_id[w["block"]]["text"])[:30]
            at = next((i for i in range(lo + 1, hi + 1) if head and squash(lines[i]).startswith(head)), None)
        if at is not None:
            before.setdefault(at, []).append(f"<!-- figure_check: {reasons}{tail}")
        elif w["page"] in pages:
            caption = by_id[w["block"]]["text"].strip()[:40].replace("--", "–")
            before.setdefault(pages[w["page"]][0] + 1, []).append(f"<!-- figure_check: {reasons}; caption \"{caption}\"{tail}")
    out = []
    for i, line in enumerate(lines):
        out += before.get(i, [])
        if i not in drop:
            out.append(line)
    return "\n".join(out + before.get(len(lines), []))
