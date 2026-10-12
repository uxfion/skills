# /// script
# dependencies = ["pypdfium2", "numpy", "pillow", "scipy"]
# ///
"""region.py PARSE_JSON PDF OUT_JSON [--no-layer]: prototype of caption-anchored float regions.

Each figure caption anchors a float: the rectangle between the caption and the nearest piece of the page's running
flow (body text, section headings, other captions, page furniture) in the caption's columns. Every block inside it,
whatever its label, belongs to the figure; the crop is the ink inside the float. Blocks are told apart by evidence:
the PDF text layer (raster text has no characters; figure text uses other fonts) and, without a text layer, by
geometry alone (--no-layer simulates scans and screenshots)."""
import ctypes, json, re, sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import ndimage
import pypdfium2 as pdfium
import pypdfium2.raw as raw

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402  (caption regexes and helpers of the current skill)

NOISE = {"header", "footer", "number", "header_image", "footer_image", "aside_text"}
FIGLIKE = {"image", "chart", "seal"}
FLOW_TEXT = {"text", "reference", "reference_content", "footnote", "algorithm", "content", "abstract"}
HEADINGS = {"paragraph_title", "doc_title"}
FORMULA = {"display_formula", "formula", "formula_number"}
INK = 235            # a pixel darker than this in any channel is ink
RASTER = 0.25        # text-layer characters under a block below this share of its text: the text is pixels


def strip_markup(t):
    return re.sub(r"\$[^$]*\$|<[^>]+>|\\[A-Za-z]+|[\s{}^_]", "", t)


class Layer:
    """Text-layer characters of one PDF in page-image pixels: (x, y, size_pt, font)."""

    def __init__(self, pdf, sizes):
        self.pages = {}
        buf = ctypes.create_string_buffer(256)
        flags = ctypes.c_int()
        for pno, (w, h) in sizes.items():
            page = pdf[pno - 1]
            tp = page.get_textpage()
            W, H = page.get_size()
            sx = w / W
            out = []
            for i in range(tp.count_chars()):
                if raw.FPDFText_GetUnicode(tp, i) <= 32:
                    continue
                l, b, r, t = tp.get_charbox(i)
                raw.FPDFText_GetFontInfo(tp, i, buf, 256, ctypes.byref(flags))
                m = raw.FS_MATRIX()
                raw.FPDFText_GetMatrix(tp, i, ctypes.byref(m))
                size = raw.FPDFText_GetFontSize(tp, i) * (m.c * m.c + m.d * m.d) ** 0.5
                out.append(((l + r) / 2 * sx, (H - (t + b) / 2) * sx, round(size * 2) / 2,
                            buf.value.decode("latin-1", "replace").split("+")[-1]))
            self.pages[pno] = out

    def under(self, pno, box):
        return [c for c in self.pages[pno] if box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]]


def style_of(chars):
    if not chars:
        return None
    return Counter((c[2], c[3]) for c in chars).most_common(1)[0][0]


def classify(doc, layer):
    sizes_of = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    """block id -> role: noise, caption, tcaption, fig (figure content), flow, or ? (no evidence either way)."""
    blocks = [b for b in doc["blocks"] if b["bbox"] and b["label"] != "figure"]
    role, why = {}, {}
    body = Counter()
    if layer:
        for b in blocks:
            if b["label"] == "text" and len(b["text"]) >= P.LONG_TEXT:
                s = style_of(layer.under(b["page"], b["bbox"]))
                if s:
                    body[s] += 1
    body_styles = {s for s, n in body.items() if n >= max(2, 0.1 * sum(body.values()))}
    body_sizes = {s[0] for s in body_styles}
    body_fonts = {s[1] for s in body_styles}
    has_layer = {p: len(c) >= 50 for p, c in layer.pages.items()} if layer else {}
    # the text area of each page, from its long running text; columns from where those blocks start and end
    area, edges = {}, {}
    for pno in sizes_of:
        longs = [b["bbox"] for b in blocks if b["page"] == pno and b["label"] in FLOW_TEXT and len(b["text"]) >= P.LONG_TEXT]
        if longs:
            area[pno] = (min(x[0] for x in longs), max(x[2] for x in longs))
            edges[pno] = [(x[0], x[2]) for x in longs]
    seen = Counter()
    for b in blocks:
        seen[(re.sub(r"\d+", "#", b["text"].strip().lower())[:40], round(b["bbox"][1] / 25))] += 1
    for b in blocks:
        lab, t = b["label"], b["text"]
        H = sizes_of[b["page"]][1]
        cy = (b["bbox"][1] + b["bbox"][3]) / 2
        outer = not any(x is not b and x["page"] == b["page"] and x["label"] not in NOISE
                        and (x["bbox"][3] <= b["bbox"][1] if cy < H / 2 else x["bbox"][1] >= b["bbox"][3]) for x in blocks)
        if t.strip() and len(t) < 150 and seen[(re.sub(r"\d+", "#", t.strip().lower())[:40], round(b["bbox"][1] / 25))] >= 3 \
                and not (0.2 * H < cy < 0.8 * H) and outer:
            role[b["id"]], why[b["id"]] = "noise", "running-head"
            continue
        cx = (b["bbox"][0] + b["bbox"][2]) / 2
        in_area = b["page"] not in area or area[b["page"]][0] - 2 * P.ROW * H <= cx <= area[b["page"]][1] + 2 * P.ROW * H
        mid_page = 0.12 * H < (b["bbox"][1] + b["bbox"][3]) / 2 < 0.88 * H
        if lab in NOISE and not ((lab == "aside_text" and in_area and mid_page) or (lab in ("header", "footer") and mid_page)):
            role[b["id"]] = "noise"
        elif P.is_caption(b) or (lab in HEADINGS and P.CAPTION_TEXT.match(t.strip())):
            role[b["id"]] = "caption"
        elif P.is_table_caption(b):
            role[b["id"]] = "tcaption"
        elif lab in FIGLIKE:
            role[b["id"]] = "fig"
        elif lab in ("doc_title", "abstract"):
            role[b["id"]] = "flow"
        else:
            role[b["id"]] = None
        if role[b["id"]] is not None:
            continue
        # text-like blocks (text, headings, figure_title, vision_footnote, table, formulas ...)
        if layer and has_layer.get(b["page"]):
            cs = layer.under(b["page"], b["bbox"])
            n = len(strip_markup(t))
            if lab == "table":
                n = max(n, 20)
            # (a paragraph the model ran on across a column break carries more text than its box: few characters
            # in the body style are still running text)
            s0 = style_of(cs)
            if n >= 3 and len(cs) < RASTER * n and not (s0 and s0 in body_styles and len(cs) >= 20):
                role[b["id"]], why[b["id"]] = "fig", "raster"
                continue
            if lab == "table":
                role[b["id"]], why[b["id"]] = "tbl", "table"
                continue
            s = style_of(cs)
            if s and (s in body_styles or (s[1] in body_fonts and s[0] in body_sizes)):
                wide = any(b["bbox"][2] - b["bbox"][0] >= 0.8 * (x2 - x1) for x1, x2 in edges.get(b["page"], []))
                if len(t) >= 100 or wide or lab in HEADINGS:
                    role[b["id"]], why[b["id"]] = "flow", "body-font"
                else:
                    role[b["id"]], why[b["id"]] = "~", "body-font-short"
                continue
            if s and lab in FLOW_TEXT | {"table"} | FORMULA and len(t) >= P.LONG_TEXT:
                role[b["id"]], why[b["id"]] = "flow", "long"
                continue
            if s and lab in ("figure_title", "vision_footnote"):
                role[b["id"]], why[b["id"]] = "fig", "other-font"
                continue
            if s and lab in FLOW_TEXT:
                role[b["id"]], why[b["id"]] = "~", "other-font"
                continue
            if lab in HEADINGS or lab == "table" or lab in FORMULA:
                role[b["id"]], why[b["id"]] = "?", "heading/table/formula"
                continue
            role[b["id"]], why[b["id"]] = "?", "no-chars"
        else:
            row = P.ROW * H
            justified = lab in FLOW_TEXT and b["bbox"][3] - b["bbox"][1] >= 2.5 * row and any(
                abs(b["bbox"][0] - x1) <= 1.5 * row and abs(b["bbox"][2] - x2) <= 1.5 * row for x1, x2 in edges.get(b["page"], []))
            if lab == "table":
                role[b["id"]] = "tbl"
            elif lab in FLOW_TEXT and (len(t) >= P.LONG_TEXT or justified):
                role[b["id"]] = "flow"
            elif lab in ("figure_title", "vision_footnote") and len(t) >= 250:
                role[b["id"]], why[b["id"]] = "flow", "long-title"     # a caption whose number the model misread
            elif lab in ("figure_title", "vision_footnote"):
                role[b["id"]] = "fig"
            elif lab in FLOW_TEXT:
                role[b["id"]] = "~"
            else:
                role[b["id"]] = "?"
    # A table's caption runs on in the lines right under "TABLE I"; a table with its caption above or below is a
    # table, and the notes right under it are its own
    for pno in sizes_of:
        pb = sorted([b for b in blocks if b["page"] == pno], key=lambda b: b["bbox"][1])
        H = sizes_of[pno][1]; row = P.ROW * H
        for c in [b for b in pb if role[b["id"]] == "tcaption"]:
            last = c["bbox"]
            for b in pb:
                if role[b["id"]] in ("fig", "~", "?") and b["label"] != "table" and 0 <= b["bbox"][1] - last[3] <= 1.5 * row \
                        and hov(b["bbox"], last) > 0:
                    role[b["id"]], why[b["id"]] = "tcaption", "table-caption-cont"
                    last = b["bbox"]
        caps = [b for b in pb if role[b["id"]] == "tcaption"]
        for t in [b for b in pb if b["label"] == "table" and role[b["id"]] in ("tbl", "fig")]:
            if any(hov(c["bbox"], t["bbox"]) > 0 and (0 <= t["bbox"][1] - c["bbox"][3] <= 6 * row or 0 <= c["bbox"][1] - t["bbox"][3] <= 6 * row)
                   for c in caps):
                role[t["id"]], why[t["id"]] = "flow", "captioned-table"
                last = t["bbox"]
                for b in pb:
                    if role[b["id"]] in ("fig", "~", "?") and b["label"] != "table" and 0 <= b["bbox"][1] - last[3] <= 1.5 * row \
                            and hov(b["bbox"], last) > 0.5 * (b["bbox"][2] - b["bbox"][0]):
                        role[b["id"]], why[b["id"]] = "flow", "table-note"
                        last = b["bbox"]
    # Blocks inside a picture the VL model drew: figure content, unless they run on from the page's flow outside
    # every picture (a paragraph the picture box overreaches). Fonts alone cannot tell a vector figure set in the
    # body font from the body.
    for pno in sizes_of:
        pb = [b for b in blocks if b["page"] == pno]
        pics = [b["bbox"] for b in pb if b["label"] in FIGLIKE]
        if not pics:
            continue
        H = sizes_of[pno][1]
        inside = {b["id"] for b in pb if role[b["id"]] in ("flow", "?", "tbl", "~")
                  and any(P.box_overlap(b["bbox"], q) >= 0.8 * max(1, P.box_area(b["bbox"])) for q in pics)}
        anchors = [b for b in pb if role[b["id"]] == "flow" and b["id"] not in inside]
        grew = True
        while grew:
            grew = False
            for b in pb:
                if b["id"] in inside and any(abs(b["bbox"][1] - a["bbox"][3]) <= 2 * P.ROW * H or abs(a["bbox"][1] - b["bbox"][3]) <= 2 * P.ROW * H
                                             for a in anchors if hov(a["bbox"], b["bbox"]) > 0.5 * (b["bbox"][2] - b["bbox"][0])):
                    inside.discard(b["id"]); anchors.append(b); grew = True
        for i in inside:
            role[i], why[i] = "fig", "in-picture"
    return role, why, body_styles


def body_lines(layer, pno, box, body_styles, width):
    """Text-layer lines in the body style inside box running most of `width`: running text, not figure text."""
    if not layer or not body_styles:
        return []
    cs = [c for c in layer.under(pno, box) if (c[2], c[3]) in body_styles]
    lines = []
    for c in sorted(cs, key=lambda c: c[1]):
        if lines and abs(c[1] - lines[-1][0]) <= 0.4 * c[2] * 2:
            lines[-1][1].append(c)
        else:
            lines.append([c[1], [c]])
    out, prev = [], None
    for y, ch in lines:
        xs = [c[0] for c in ch]
        full = max(xs) - min(xs) >= 0.85 * width and len(ch) >= 30
        last_line = prev is not None and prev[0] and y - prev[1] <= 3 * ch[0][2] and len(ch) >= 3
        if full or last_line:
            out.append((y - ch[0][2], y + ch[0][2]))
        prev = (full, y)
    return out


def hov(a, b):
    return min(a[2], b[2]) - max(a[0], b[0])


def vov(a, b):
    return min(a[3], b[3]) - max(a[1], b[1])


def gap_y(a, b):
    return max(0, a[1] - b[3], b[1] - a[3])


def gap_x(a, b):
    return max(0, a[0] - b[2], b[0] - a[2])


def ink_mask(img, box, masks):
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    h, w = img.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None, (x1, y1)
    sub = (img[y1:y2, x1:x2] < INK).any(axis=2)
    for m in masks:
        mx1, my1, mx2, my2 = [int(round(v)) for v in m]
        sub[max(0, my1 - y1):max(0, my2 - y1), max(0, mx1 - x1):max(0, mx2 - x1)] = False
    return sub, (x1, y1)


def connected_ink(img, cap, masks, seeds, reach):
    """Bounding box of the ink inside cap connected (within `reach` pixels) to the seed boxes, and whether that ink
    runs into the cap's edge (cut by the flow) rather than ending in white space."""
    sub, (ox, oy) = ink_mask(img, cap, masks)
    if sub is None or not sub.any():
        return None, set()
    r = max(1, int(reach))
    grown = ndimage.binary_dilation(sub, structure=np.ones((2 * r + 1, 2 * r + 1), bool))
    lab, n = ndimage.label(grown)
    keep = set()
    for s in seeds:
        x1, y1, x2, y2 = [int(round(v)) for v in s]
        x1, y1 = max(0, x1 - ox), max(0, y1 - oy)
        x2, y2 = min(sub.shape[1], x2 - ox), min(sub.shape[0], y2 - oy)
        if x2 > x1 and y2 > y1:
            keep |= set(np.unique(lab[y1:y2, x1:x2]).tolist()) - {0}
    if not keep:
        return None, set()
    m = np.isin(lab, list(keep)) & sub
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return None, set()
    box = [ox + int(xs.min()), oy + int(ys.min()), ox + int(xs.max()) + 1, oy + int(ys.max()) + 1]
    edges = set()
    if ys.min() <= 1: edges.add("top")
    if ys.max() >= sub.shape[0] - 2: edges.add("bottom")
    if xs.min() <= 1: edges.add("left")
    if xs.max() >= sub.shape[1] - 2: edges.add("right")
    return box, edges


def page_floats(pblocks, role, size, img, lines_in=None, whole=None, body_font=lambda b: False):
    W, H = size
    row = P.ROW * H
    gap = 6 * row
    content = [b for b in pblocks if role.get(b["id"]) != "noise"]
    if not content:
        return [], []
    L, R = min(b["bbox"][0] for b in content), max(b["bbox"][2] for b in content)
    top_bound = max([b["bbox"][3] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][3] < 0.15 * H] + [0])
    bot_bound = min([b["bbox"][1] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][1] > 0.85 * H] + [H])
    caps = [b for b in pblocks if role.get(b["id"]) == "caption"]
    tails = {}
    for c in caps:
        # the right half of a caption set in two columns
        # (running text in the other column may start on the caption's line too, but it does not end with it)
        tails[c["id"]] = [b for b in pblocks if b is not c and role.get(b["id"]) not in ("caption", "noise")
                          and (role.get(b["id"]) != "flow" or (not body_font(b) and abs(b["bbox"][3] - c["bbox"][3]) <= 4 * row))
                          and b["label"] in ("text", "figure_title", "vision_footnote")
                          and abs(b["bbox"][1] - c["bbox"][1]) <= row and b["bbox"][0] >= c["bbox"][2] - row]
    for c in caps:
        # the legend paragraph right under a caption's title line, from the same left edge
        last = c["bbox"]
        for b in sorted(pblocks, key=lambda b: b["bbox"][1]):
            if b is c or role.get(b["id"]) in ("caption", "noise", "flow", "tcaption") or b in tails[c["id"]]:
                continue
            if b["label"] in ("text", "vision_footnote", "figure_title") and 0 <= b["bbox"][1] - last[3] + row <= 2 * row \
                    and abs(b["bbox"][0] - c["bbox"][0]) <= 2 * row:
                tails[c["id"]].append(b)
                last = b["bbox"]
    tail_ids = {t["id"] for ts in tails.values() for t in ts}
    cbox = {c["id"]: P.box_union([c["bbox"]] + [t["bbox"] for t in tails[c["id"]]]) for c in caps}
    claimed = {}
    # whole-figure boxes of a layout model that draws them (PP-DocLayout_plus-L): blocks inside one are one figure,
    # whatever white space parts them, unless the box spans a caption or running text
    pics = []
    for f in whole or []:
        if f["label"] not in ("image", "chart"):
            continue
        if any(role.get(x["id"]) in ("flow", "caption", "tcaption") and P.box_overlap(f["bbox"], x["bbox"]) > P.SWALLOW * P.box_area(x["bbox"])
               for x in pblocks):
            continue
        pics.append(f["bbox"])

    def together(a, b):
        return any(P.box_overlap(q, a) >= P.COVER * max(1, P.box_area(a)) and P.box_overlap(q, b) >= P.COVER * max(1, P.box_area(b))
                   for q in pics)

    def is_stop(b, cid):
        if role.get(b["id"]) in ("flow", "caption", "tcaption", "noise") and b["id"] not in tail_ids:
            return b["id"] != cid
        if b["id"] in claimed and claimed[b["id"]] != cid:
            return True
        if b["label"] in HEADINGS and role.get(b["id"]) == "?":
            # a section heading has running text right under it in its column
            return any(role.get(x["id"]) == "flow" and 0 <= x["bbox"][1] - b["bbox"][3] <= 3 * row and hov(x["bbox"], b["bbox"]) > 0
                       for x in pblocks)
        if b["label"] in FORMULA and role.get(b["id"]) == "?":
            return True
        if role.get(b["id"]) == "tbl":
            return any(role.get(x["id"]) == "tcaption" and hov(x["bbox"], b["bbox"]) > 0
                       and (0 <= b["bbox"][1] - x["bbox"][3] <= 4 * row or 0 <= x["bbox"][1] - b["bbox"][3] <= 4 * row)
                       for x in pblocks)
        return False

    def own_caption(b, cid):
        """Another caption right under (or over) b: b is that figure's."""
        return any(d["id"] != cid and hov(d["bbox"], b["bbox"]) > 0.5 * (b["bbox"][2] - b["bbox"][0])
                   and (0 <= d["bbox"][1] - b["bbox"][3] <= 6 * row) for d in caps)

    def blocked(b, box, cid):
        """A stopper between b and box (vertically between them, across both)."""
        lo, hi = (b, box) if b[3] <= box[1] else (box, b)
        if lo[3] > hi[1]:
            return False
        return any(is_stop(x, cid) and x["bbox"][1] >= lo[3] - row and x["bbox"][3] <= hi[1] + row
                   and hov(x["bbox"], b) > 0 and hov(x["bbox"], box) > 0 for x in pblocks)

    def grow(c, direction):
        cid, cb = c["id"], cbox[c["id"]]
        cand = [b for b in pblocks if role.get(b["id"]) in ("fig", "?", "tbl", "~") and b["id"] not in tail_ids
                and not is_stop(b, cid)]
        if direction == "up":
            cand = [b for b in cand if b["bbox"][3] <= cb[1] + row
                    or ((b["bbox"][1] + b["bbox"][3]) / 2 < cb[1] and b["bbox"][3] <= cb[1] + 3 * row)]
            seeds = [b for b in cand if cb[1] - b["bbox"][3] <= 12 * row and hov(b["bbox"], cb) > 0]
        else:
            cand = [b for b in cand if b["bbox"][1] >= cb[3] - row
                    or ((b["bbox"][1] + b["bbox"][3]) / 2 > cb[3] and b["bbox"][1] >= cb[3] - 3 * row)]
            seeds = [b for b in cand if b["bbox"][1] - cb[3] <= 12 * row and hov(b["bbox"], cb) > 0]
        seeds = [b for b in seeds if role.get(b["id"]) in ("fig", "tbl") and not own_caption(b, cid) and not blocked(b["bbox"], cb, cid)]
        if not any(role.get(b["id"]) in ("fig", "tbl") for b in seeds) and not seeds:
            return None
        members = list(seeds)
        grew = True
        while grew:
            grew = False
            ub = P.box_union([m["bbox"] for m in members])
            for b in cand:
                if b in members:
                    continue
                bb = b["bbox"]
                strong = role.get(b["id"]) in ("fig", "tbl")
                if strong:
                    # above or below the figure so far (further when squarely under it); beside a member in one row
                    # with it (tops and bottoms aligned); or in one whole-figure box with a member
                    near = (gap_y(bb, ub) <= gap and hov(bb, ub) > 0) \
                        or (gap_y(bb, ub) <= 10 * row and hov(bb, ub) >= 0.5 * min(bb[2] - bb[0], ub[2] - ub[0])) \
                        or any(gap_x(bb, m["bbox"]) <= gap and abs(bb[1] - m["bbox"][1]) <= 2 * row and abs(bb[3] - m["bbox"][3]) <= 2 * row
                               for m in members) \
                        or any(together(bb, m["bbox"]) for m in members if role.get(m["id"]) in ("fig", "tbl"))
                else:
                    # weak evidence (another font, no evidence): only right against the figure, or inside its box
                    near = (gap_y(bb, ub) <= 2 * row and hov(bb, ub) >= 0.5 * (bb[2] - bb[0])) \
                        or P.box_overlap(bb, ub) >= 0.8 * max(1, P.box_area(bb)) \
                        or any(together(bb, m["bbox"]) for m in members if role.get(m["id"]) in ("fig", "tbl"))
                if near and not own_caption(b, cid) and not blocked(bb, ub, cid):
                    members.append(b)
                    grew = True
                    ub = P.box_union([m["bbox"] for m in members])
        if not any(role.get(b["id"]) in ("fig", "tbl") for b in members):
            return None
        return members

    results = {}
    for direction in ("up", "down"):
        for c in sorted(caps, key=lambda c: c["bbox"][1]):
            if c["id"] in results:
                continue
            members = grow(c, direction)
            if members:
                results[c["id"]] = (direction, members)
                for m in members:
                    claimed[m["id"]] = c["id"]
    out = []
    for c in caps:
        cid = c["id"]
        if cid not in results:
            out.append({"caption": cid, "bbox": None, "members": [], "dir": None, "flags": []})
            continue
        direction, members = results[cid]
        cb = cbox[cid]
        ub = P.box_union([m["bbox"] for m in members])
        x1, x2 = min(ub[0], cb[0]), max(ub[2], cb[2])
        xs = [x1, 0, x2, 0]
        if direction == "up":
            stops = [b["bbox"][3] for b in pblocks if is_stop(b, cid) and b["bbox"][3] <= ub[1] + row and hov(b["bbox"], xs) > 0]
            cap = [x1, max(stops + [top_bound, ub[1] - gap]), x2, cb[1]]
        else:
            stops = [b["bbox"][1] for b in pblocks if is_stop(b, cid) and b["bbox"][1] >= ub[3] - row and hov(b["bbox"], xs) > 0]
            cap = [x1, cb[3], x2, min(stops + [bot_bound, ub[3] + gap])]
        flags = []
        if lines_in:
            # running text a picture box overreaches: body lines at the far edge cap the float
            flows = [b["bbox"][2] - b["bbox"][0] for b in pblocks if role.get(b["id"]) == "flow"]
            width = sorted(flows)[len(flows) // 2] if flows else x2 - x1
            far = [x1, min(cap[1], ub[1]), x2, cap[3]] if direction == "up" else [x1, cap[1], x2, max(cap[3], ub[3])]
            lines = sorted(lines_in(far, min(width, x2 - x1)), reverse=direction != "up")
            edge = far[1] if direction == "up" else far[3]
            for i, (y1, y2) in enumerate(lines):
                reach = 0.12 * H if i == 0 else 3 * row
                if direction == "up" and y1 <= edge + reach:
                    edge = max(edge, y2)
                elif direction == "down" and y2 >= edge - reach:
                    edge = min(edge, y1)
                else:
                    break
            if direction == "up" and edge > cap[1]:
                cap[1] = edge; flags.append("body_lines_cut")
            if direction == "down" and edge < cap[3]:
                cap[3] = edge; flags.append("body_lines_cut")
        # blocks between the figure and its caption, not running text: the figure's (sub-captions under panels)
        band = [x1, ub[3] - row, x2, cb[1] + row] if direction == "up" else [x1, cb[3] - row, x2, ub[1] + row]
        for b in pblocks:
            if b not in members and b["id"] not in tail_ids and b["id"] != cid and role.get(b["id"]) in ("fig", "~", "?", "tbl") \
                    and not is_stop(b, cid) and P.box_overlap(b["bbox"], band) >= 0.8 * max(1, P.box_area(b["bbox"])):
                members.append(b)
                claimed[b["id"]] = cid
        clipped = [[max(m["bbox"][0], cap[0]), max(m["bbox"][1], cap[1]), min(m["bbox"][2], cap[2]), min(m["bbox"][3], cap[3])]
                   for m in members]
        clipped = [b for b in clipped if b[2] > b[0] and b[3] > b[1]]
        mem_ids = {m["id"] for m in members}
        masks = [b["bbox"] for b in pblocks if b["id"] not in mem_ids]
        ink, edges = connected_ink(img, cap, masks, clipped, 0.5 * row) if img is not None and clipped else (None, set())
        # nothing but the figure sits between it and its caption: the ink there is the figure's too
        band = [x1, ub[3], x2, cb[1]] if direction == "up" else [x1, cb[3], x2, ub[1]]
        extra = None
        if img is not None and band[3] - band[1] > 2:
            sub, (ox, oy) = ink_mask(img, band, masks)
            if sub is not None and sub.any():
                ys, xs_ = np.nonzero(sub)
                extra = [ox + int(xs_.min()), oy + int(ys.min()), ox + int(xs_.max()) + 1, oy + int(ys.max()) + 1]
        box = P.box_union(clipped + ([ink] if ink else []) + ([extra] if extra else [])) if clipped else ink
        if not box:
            out.append({"caption": cid, "bbox": None, "members": [], "dir": None, "flags": ["empty"]})
            continue
        # checks: ink running into the flow at the float's far edge; a block the crop cuts through
        far_edge = "top" if direction == "up" else "bottom"
        if far_edge in edges and (cap[1] > top_bound + 2 if direction == "up" else cap[3] < bot_bound - 2):
            flags.append("ink_cut_by_flow")
        for b in pblocks:
            if b["id"] in mem_ids or role.get(b["id"]) == "noise" or b["id"] == cid or b["id"] in tail_ids:
                continue
            o = P.box_overlap(b["bbox"], box) / max(1, P.box_area(b["bbox"]))
            if 0.1 < o < 0.9:
                flags.append(f"cuts:{b['id']}")
        out.append({"caption": cid, "bbox": [int(v) for v in box], "members": sorted(mem_ids), "dir": direction,
                    "region": [int(v) for v in cap], "flags": flags})
    orphans = [b["id"] for b in pblocks if role.get(b["id"]) == "fig" and b["id"] not in claimed and b["id"] not in tail_ids
               and b["label"] not in FIGLIKE]
    return out, orphans


def load_whole(key):
    f = Path(__file__).parent.parent / "plusl" / f"{key}.json"
    return {int(k): v for k, v in json.load(open(f)).items()} if f.exists() and "--no-plusl" not in sys.argv else {}


def main():
    doc = json.load(open(sys.argv[1]))
    no_layer = "--no-layer" in sys.argv
    pdf = pdfium.PdfDocument(sys.argv[2])
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    layer = None if no_layer else Layer(pdf, sizes)
    role, why, body_styles = classify(doc, layer)
    whole = load_whole(Path(sys.argv[1]).stem)
    res, orph = {}, {}
    for pno, (w, h) in sizes.items():
        pblocks = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"] and b["label"] != "figure"]
        if not any(role.get(b["id"]) == "caption" for b in pblocks):
            continue
        page = pdf[pno - 1]
        img = np.asarray(page.render(scale=w / page.get_size()[0]).to_pil().convert("RGB"))
        lines_in = (lambda region, width, pno=pno: body_lines(layer, pno, region, body_styles, width)) if layer else None
        res[pno], orph[pno] = page_floats(pblocks, role, (w, h), img, lines_in, whole.get(pno),
                                          lambda b: why.get(b["id"]) == "body-font")
    json.dump({"floats": res, "orphans": orph, "role": role, "why": why}, open(sys.argv[3], "w"))


if __name__ == "__main__":
    main()
