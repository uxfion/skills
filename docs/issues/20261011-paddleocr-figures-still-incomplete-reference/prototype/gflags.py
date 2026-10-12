# /// script
# dependencies = []
# ///
"""gflags.py BASE_DIR REG_DIR OUT_TSV: option G — keep the current crops, flag a figure as possibly incomplete when
  uncropped  its caption has no crop (the existing uncropped_figure),
  split      its caption has two crops or more,
  edge:<s>   the second opinion (the prototype's float) and the current crop disagree on side s by more than two
             text rows (s = top/bottom/left/right, + = the second opinion reaches further, - = it stops sooner).
One row per figure caption, with the current and second-opinion boxes for grading."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

ROWS = float(sys.argv[4]) if len(sys.argv) > 4 else 2
rows = []
for rj in sorted(Path(sys.argv[2]).glob("*.json")):
    k = rj.stem
    base = json.load(open(Path(sys.argv[1]) / k / f"{k}.json"))
    reg = json.load(open(rj))
    heights = {p["page"]: p["height"] for p in base["pages"]}
    byid = {b["id"]: b for b in base["blocks"]}
    for pno, floats in reg["floats"].items():
        pno = int(pno)
        H = heights[pno]
        row = P.ROW * H
        pb = [b for b in base["blocks"] if b["page"] == pno and b["bbox"]]
        crops = [b for b in pb if b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)]
        captions = [byid[f["caption"]] for f in floats]
        reach = P.UNCROPPED_REACH * H
        owner = {}
        for cr in crops:
            x1, y1, x2, y2 = cr["bbox"]
            cols = [c for c in captions if min(x2, c["bbox"][2]) > max(x1, c["bbox"][0])]
            below = [c for c in cols if y1 < c["bbox"][1] and y2 <= c["bbox"][3] and c["bbox"][1] - y2 <= reach]
            above = [c for c in cols if c["bbox"][1] <= y1 and c["bbox"][3] < y2 and y1 - c["bbox"][3] <= reach]
            if below or above:
                c = min(below, key=lambda c: c["bbox"][1]) if below else max(above, key=lambda c: c["bbox"][3])
                owner.setdefault(c["id"], []).append(cr)
        for f in floats:
            c = byid[f["caption"]]
            mine = owner.get(c["id"], [])
            cur = P.box_union([m["bbox"] for m in mine]) if mine else None
            flags = []
            if not mine:
                flags.append("uncropped")
            if len(mine) >= 2:
                flags.append("split")
            if cur and f["bbox"]:
                s = f["bbox"]
                for name, d in (("top", cur[1] - s[1]), ("bottom", s[3] - cur[3]), ("left", cur[0] - s[0]), ("right", s[2] - cur[2])):
                    if abs(d) > ROWS * row:
                        flags.append(f"edge:{name}{'+' if d > 0 else '-'}")
            rows.append([k, pno, c["id"], ",".join(flags), cur or "", f["bbox"] or "", " ".join(c["text"].split())[:60]])
with open(sys.argv[3], "w") as out:
    out.write("key\tpage\tcaption\tflags\tcurrent\tsecond\ttext\n")
    for r in rows:
        out.write("\t".join(map(str, r)) + "\n")
print(len(rows), "captions,", sum(1 for r in rows if r[3]), "flagged")
