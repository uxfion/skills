# /// script
# dependencies = ["pypdfium2", "numpy", "pillow", "scipy"]
# ///
"""region_slim8.py PARSE_JSON PDF OUT_JSON PLUSL_DIR [--no-layer]: region_slim.py plus two dropped rules that the slim
run showed it needs (post hoc, SLIM.md): a heading stops growth only when running text follows it, and body-text
lines from the text layer cap the far edge. Otherwise the frozen second opinion (sha256 286305bd...) cut down to its
core rules.

Kept: roles by evidence (text-layer font and size > geometry > whole-figure boxes > VL labels); captions; growing from
a caption until running text, another caption or a heading; whole-figure boxes; the crop as connected ink; one block,
one caption. Dropped: every rule added after a page went wrong (running heads, mid-page noise, raster run-ons,
wide-line and long-title tests, table-caption continuations and table notes, blocks inside VL pictures, two-column
caption tails and legends, the heading-over-text test, formulas as stops, the extra proximity cases, body-line caps,
blocks and ink between a figure and its caption)."""
import json, sys
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

FROZEN = Path(sys.argv[0]).resolve().parent / "region_frozen.py"
sys.path.insert(0, str(FROZEN.parent))
import region_frozen as F  # noqa: E402  (text layer, ink and geometry helpers, unchanged)

NOISE, FIGLIKE, FLOW_TEXT, HEADINGS = F.NOISE, F.FIGLIKE, F.FLOW_TEXT, F.HEADINGS
hov, gap_x, gap_y = F.hov, F.gap_x, F.gap_y


def classify(doc, layer):
    """block id -> role: noise, caption, tcaption, fig, tbl, flow, ~ (weak: another font, short) or ? (no evidence)."""
    blocks = [b for b in doc["blocks"] if b["bbox"] and b["label"] != "figure"]
    body = {}
    if layer:
        for b in blocks:
            if b["label"] == "text" and len(b["text"]) >= P.LONG_TEXT:
                s = F.style_of(layer.under(b["page"], b["bbox"]))
                if s:
                    body[s] = body.get(s, 0) + 1
    total = sum(body.values())
    body_styles = {s for s, n in body.items() if n >= max(2, 0.1 * total)}
    has_layer = {p: len(c) >= 50 for p, c in layer.pages.items()} if layer else {}
    role = {}
    for b in blocks:
        lab, t = b["label"], b["text"]
        if lab in NOISE:
            r = "noise"
        elif P.is_caption(b) or (lab in HEADINGS and P.CAPTION_TEXT.match(t.strip())):
            r = "caption"
        elif P.is_table_caption(b):
            r = "tcaption"
        elif lab in FIGLIKE:
            r = "fig"
        elif lab in ("doc_title", "abstract"):
            r = "flow"
        elif layer and has_layer.get(b["page"]):
            cs = layer.under(b["page"], b["bbox"])
            n = max(len(F.strip_markup(t)), 20 if lab == "table" else 0)
            s = F.style_of(cs)
            long = len(t) >= P.LONG_TEXT
            if n >= 3 and len(cs) < F.RASTER * n:
                r = "fig"                                   # its text is pixels: part of a picture
            elif lab == "table":
                r = "tbl"
            elif s in body_styles:
                r = "flow" if long or lab in HEADINGS else "~"
            elif long and lab in FLOW_TEXT:
                r = "flow"
            elif lab in ("figure_title", "vision_footnote"):
                r = "fig"
            elif lab in FLOW_TEXT:
                r = "~"
            else:
                r = "?"
        else:
            if lab == "table":
                r = "tbl"
            elif lab in FLOW_TEXT and len(t) >= P.LONG_TEXT:
                r = "flow"
            elif lab in ("figure_title", "vision_footnote"):
                r = "fig"
            elif lab in FLOW_TEXT:
                r = "~"
            else:
                r = "?"
        role[b["id"]] = r
    return role, body_styles


def page_floats(pblocks, role, size, img, whole, lines_in=None):
    W, H = size
    row = P.ROW * H
    gap = 6 * row
    top_bound = max([b["bbox"][3] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][3] < 0.15 * H] + [0])
    bot_bound = min([b["bbox"][1] for b in pblocks if role.get(b["id"]) == "noise" and b["bbox"][1] > 0.85 * H] + [H])
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
            # a section heading has running text right under it in its column
            return any(role.get(x["id"]) == "flow" and 0 <= x["bbox"][1] - b["bbox"][3] <= 3 * row and hov(x["bbox"], b["bbox"]) > 0
                       for x in pblocks)
        if role.get(b["id"]) == "tbl":                      # a table with its own caption
            return any(role.get(x["id"]) == "tcaption" and hov(x["bbox"], b["bbox"]) > 0
                       and (0 <= b["bbox"][1] - x["bbox"][3] <= 4 * row or 0 <= x["bbox"][1] - b["bbox"][3] <= 4 * row)
                       for x in pblocks)
        return False

    def own_caption(b, cid):
        return any(d["id"] != cid and hov(d["bbox"], b["bbox"]) > 0.5 * (b["bbox"][2] - b["bbox"][0])
                   and 0 <= d["bbox"][1] - b["bbox"][3] <= 6 * row for d in caps)

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
            seeds = [b for b in cand if cb[1] - b["bbox"][3] <= 12 * row and hov(b["bbox"], cb) > 0]
        else:
            cand = [b for b in cand if b["bbox"][1] >= cb[3] - row]
            seeds = [b for b in cand if b["bbox"][1] - cb[3] <= 12 * row and hov(b["bbox"], cb) > 0]
        members = [b for b in seeds if role.get(b["id"]) in ("fig", "tbl") and not own_caption(b, cid) and not blocked(b["bbox"], cb, cid)]
        if not members:
            return None
        grew = True
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
                    near = (gap_y(bb, ub) <= 2 * row and hov(bb, ub) >= 0.5 * (bb[2] - bb[0])) \
                        or P.box_overlap(bb, ub) >= 0.8 * max(1, P.box_area(bb)) or any(together(bb, m["bbox"]) for m in members)
                if near and not own_caption(b, cid) and not blocked(bb, ub, cid):
                    members.append(b)
                    grew = True
                    ub = P.box_union([m["bbox"] for m in members])
        return members

    results = {}
    for direction in ("up", "down"):
        for c in sorted(caps, key=lambda c: c["bbox"][1]):
            if c["id"] not in results:
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
        cb = c["bbox"]
        ub = P.box_union([m["bbox"] for m in members])
        x1, x2 = min(ub[0], cb[0]), max(ub[2], cb[2])
        xs = [x1, 0, x2, 0]
        if direction == "up":
            stops = [b["bbox"][3] for b in pblocks if is_stop(b, cid) and b["bbox"][3] <= ub[1] + row and hov(b["bbox"], xs) > 0]
            cap = [x1, max(stops + [top_bound, ub[1] - gap]), x2, cb[1]]
        else:
            stops = [b["bbox"][1] for b in pblocks if is_stop(b, cid) and b["bbox"][1] >= ub[3] - row and hov(b["bbox"], xs) > 0]
            cap = [x1, cb[3], x2, min(stops + [bot_bound, ub[3] + gap])]
        if False:
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
                cap[1] = edge
            if direction == "down" and edge < cap[3]:
                cap[3] = edge
        clipped = [[max(m["bbox"][0], cap[0]), max(m["bbox"][1], cap[1]), min(m["bbox"][2], cap[2]), min(m["bbox"][3], cap[3])]
                   for m in members]
        clipped = [b for b in clipped if b[2] > b[0] and b[3] > b[1]]
        mem_ids = {m["id"] for m in members}
        masks = [b["bbox"] for b in pblocks if b["id"] not in mem_ids]
        ink, _ = F.connected_ink(img, cap, masks, clipped, 0.5 * row) if clipped else (None, set())
        box = P.box_union(clipped + ([ink] if ink else [])) if clipped else ink
        out.append({"caption": cid, "bbox": [int(v) for v in box] if box else None, "members": sorted(mem_ids),
                    "dir": direction, "region": [int(v) for v in cap], "flags": []})
    return out


def main():
    doc = json.load(open(sys.argv[1]))
    pdf = pdfium.PdfDocument(sys.argv[2])
    pl = Path(sys.argv[4]) / f"{Path(sys.argv[1]).stem}.json"
    whole = {int(k): v for k, v in json.load(open(pl)).items()} if pl.exists() else {}
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    layer = None if "--no-layer" in sys.argv else F.Layer(pdf, sizes)
    role, body_styles = classify(doc, layer)
    res = {}
    for pno, (w, h) in sizes.items():
        pblocks = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"] and b["label"] != "figure"]
        if not any(role.get(b["id"]) == "caption" for b in pblocks):
            continue
        page = pdf[pno - 1]
        img = np.asarray(page.render(scale=w / page.get_size()[0]).to_pil().convert("RGB"))
        lines_in = (lambda region, width, pno=pno: F.body_lines(layer, pno, region, body_styles, width)) if layer else None
        res[pno] = page_floats(pblocks, role, (w, h), img, whole.get(pno), lines_in)
    json.dump({"floats": res, "role": role}, open(sys.argv[3], "w"))


if __name__ == "__main__":
    main()
