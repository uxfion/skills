# /// script
# dependencies = ["pypdfium2"]
# ///
"""twofig.py SET BASE_DIR PDF_DIR REG_DIR OUT_TSV: written AFTER grading the new papers (post hoc).
One crop should serve one caption. Flags a figure caption whose crop also serves another figure:
  inside: another caption block lies inside the crop, or the PDF text layer inside the crop has a line starting
          "Figure N" / "Fig. N" / "Table N" (a caption the VL model swallowed into the image);
  beside: another caption sits beside this one, on the same side of the crop (two side-by-side figures, one crop)."""
import json, re, sys
from pathlib import Path
import pypdfium2 as pdfium

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

CAP = re.compile(r"(?m)^\s*(extended\s+data\s+|supplementary\s+)?(figure|fig\.|table)\s*[A-Z]?\d+\s*[.:|]", re.I)
TAB = re.compile(r"\s*(extended\s+data\s+|supplementary\s+)?(table|tab\.)\s*[A-Z]?\d+", re.I)
sset, base, pdfs, regs, outp = sys.argv[1], *map(Path, sys.argv[2:5]), sys.argv[5]
cols = lambda a, b: min(a[2], b[2]) > max(a[0], b[0])
def inside(c, r):
    w, h = c[2] - c[0], c[3] - c[1]
    ix, iy = min(c[2], r[2]) - max(c[0], r[0]), min(c[3], r[3]) - max(c[1], r[1])
    return w > 0 and h > 0 and ix > 0 and iy > 0 and ix * iy >= 0.5 * w * h
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
        reach = P.UNCROPPED_REACH * H
        pb = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"]]
        crops = [b for b in pb if b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)]
        caps = [b for b in pb if P.is_caption(b) or (b["label"] == "figure_title" and TAB.match(b.get("text") or ""))]
        page = pdf[pno - 1]
        pw, ph = page.get_size()
        s = pw / W
        tp = page.get_textpage()
        bad = {}
        for cr in crops:
            r = cr["bbox"]
            why = []
            if any(inside(c["bbox"], r) for c in caps):
                why.append("inside")
            else:
                txt = tp.get_text_bounded(left=r[0] * s, bottom=ph - r[3] * s, right=r[2] * s, top=ph - r[1] * s)
                if CAP.search(txt or ""):
                    why.append("inside")
            below = [c for c in caps if cols(r, c["bbox"]) and 0 <= c["bbox"][1] - r[3] <= reach]
            above = [c for c in caps if cols(r, c["bbox"]) and 0 <= r[1] - c["bbox"][3] <= reach]
            row = lambda cs: any(min(a["bbox"][3], b["bbox"][3]) > max(a["bbox"][1], b["bbox"][1]) and not cols(a["bbox"], b["bbox"])
                                 for a in cs for b in cs if a is not b)
            if row(below) or (not below and row(above)):
                why.append("beside")
            if why:
                bad[cr["id"]] = why
        captions = [byid[f["caption"]] for f in floats]
        owner = {}
        for cr in crops:
            x1, y1, x2, y2 = cr["bbox"]
            cs = [c for c in captions if cols(cr["bbox"], c["bbox"])]
            bl = [c for c in cs if y1 < c["bbox"][1] and y2 <= c["bbox"][3] and c["bbox"][1] - y2 <= reach]
            ab = [c for c in cs if c["bbox"][1] <= y1 and c["bbox"][3] < y2 and y1 - c["bbox"][3] <= reach]
            if bl or ab:
                c = min(bl, key=lambda c: c["bbox"][1]) if bl else max(ab, key=lambda c: c["bbox"][3])
                owner.setdefault(c["id"], []).append(cr)
        for f in floats:
            why = sorted({w for cr in owner.get(f["caption"], []) for w in bad.get(cr["id"], [])})
            rows.append([sset, k, pno, f["caption"], ",".join(why)])
with open(outp, "w") as o:
    o.write("set\tkey\tpage\tcaption\ttwofig\n")
    for r in rows:
        o.write("\t".join(map(str, r)) + "\n")
print(sset, len(rows), "captions,", sum(1 for r in rows if r[4]), "flagged")
