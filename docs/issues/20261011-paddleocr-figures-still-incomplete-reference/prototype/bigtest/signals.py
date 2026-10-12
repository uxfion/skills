# /// script
# dependencies = ["pypdfium2", "numpy", "scipy", "pillow"]
# ///
"""signals.py SET BASE_DIR PDF_DIR REG_DIR OUT_TSV: two more checks per figure caption, written down before the new
papers were graded.
  table: a table caption with no table block near it sits on this figure's crop (the VL model drew the table and the
         figure as one image: the same caption-and-content pairing the skill checks for figures, applied to tables).
  cut_*: per side of this figure's crop, how many ink components cross the crop edge (ink inside the crop that goes
         on past the edge): a crop edge should run through white space, not through a title or a label."""
import json, re, sys
from pathlib import Path
import numpy as np
from scipy import ndimage
import pypdfium2 as pdfium

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

TABLE = re.compile(r"\s*(\*\*)?\s*(extended\s+data\s+|supplementary\s+)?(table|tab\.)\s*[A-Z]?\d+[.:|]?", re.I)
sset, base, pdfs, regs, outp = sys.argv[1], *map(Path, sys.argv[2:5]), sys.argv[5]

def is_table_caption(b):
    t = (b.get("text") or "").strip()
    m = TABLE.match(t)
    if not m:
        return False
    return b["label"] in ("figure_title", "table_title") or (b["label"] in ("text", "vision_footnote") and m.group(0).rstrip()[-1:] in ".:|")

def cols(a, b):
    return min(a[2], b[2]) > max(a[0], b[0])

rows = []
for rj in sorted(regs.glob("*.json")):
    k = rj.stem
    if not (base / k / f"{k}.json").exists() or not (pdfs / f"{k}.pdf").exists():
        continue
    doc = json.load(open(base / k / f"{k}.json"))
    reg = json.load(open(rj))
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    byid = {b["id"]: b for b in doc["blocks"]}
    pdf = pdfium.PdfDocument(str(pdfs / f"{k}.pdf"))
    for pno, floats in reg["floats"].items():
        pno = int(pno)
        W, H = sizes[pno]
        row, reach = P.ROW * H, P.UNCROPPED_REACH * H
        pb = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"]]
        crops = [b for b in pb if b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)]
        tables = [b for b in pb if b["label"] == "table"]
        near = lambda c, x: cols(c["bbox"], x["bbox"]) and (0 <= x["bbox"][1] - c["bbox"][3] <= reach or 0 <= c["bbox"][1] - x["bbox"][3] <= reach)
        swallowed = set()
        for tc in (b for b in pb if is_table_caption(b)):
            if not any(near(tc, t) for t in tables):
                swallowed |= {cr["id"] for cr in crops if near(tc, cr)}
        captions = [byid[f["caption"]] for f in floats]
        owner = {}
        for cr in crops:
            x1, y1, x2, y2 = cr["bbox"]
            cs = [c for c in captions if cols(cr["bbox"], c["bbox"])]
            below = [c for c in cs if y1 < c["bbox"][1] and y2 <= c["bbox"][3] and c["bbox"][1] - y2 <= reach]
            above = [c for c in cs if c["bbox"][1] <= y1 and c["bbox"][3] < y2 and y1 - c["bbox"][3] <= reach]
            if below or above:
                c = min(below, key=lambda c: c["bbox"][1]) if below else max(above, key=lambda c: c["bbox"][3])
                owner.setdefault(c["id"], []).append(cr)
        ink = None
        for f in floats:
            mine = owner.get(f["caption"], [])
            cut = [0, 0, 0, 0]
            if mine:
                if ink is None:
                    page = pdf[pno - 1]
                    img = np.asarray(page.render(scale=W / page.get_size()[0]).to_pil().convert("RGB"))[:H, :W]
                    ink = img.min(axis=2) < 235
                for cr in mine:
                    x1, y1, x2, y2 = map(int, cr["bbox"])
                    m = max(4, int(0.6 * row))
                    X1, Y1, X2, Y2 = max(0, x1 - m), max(0, y1 - m), min(ink.shape[1], x2 + m), min(ink.shape[0], y2 + m)
                    lab, n = ndimage.label(ink[Y1:Y2, X1:X2], structure=np.ones((3, 3)))
                    ox1, oy1, ox2, oy2 = x1 - X1, y1 - Y1, x2 - X1, y2 - Y1
                    inside = set(np.unique(lab[oy1:oy2, ox1:ox2])) - {0}
                    for i, out in enumerate((lab[:max(0, oy1 - 2), ox1:ox2], lab[oy2 + 2:, ox1:ox2], lab[oy1:oy2, :max(0, ox1 - 2)], lab[oy1:oy2, ox2 + 2:])):
                        cut[i] += len((set(np.unique(out)) - {0}) & inside)
            rows.append([sset, k, pno, f["caption"], int(any(cr["id"] in swallowed for cr in mine)), *cut])
with open(outp, "w") as o:
    o.write("set\tkey\tpage\tcaption\ttable\tcut_top\tcut_bottom\tcut_left\tcut_right\n")
    for r in rows:
        o.write("\t".join(map(str, r)) + "\n")
print(sset, len(rows), "captions,", sum(r[4] for r in rows), "table flags")
