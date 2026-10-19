# /// script
# dependencies = []
# ///
"""detect.py SET BASE_DIR REG_DIR OUT_TSV: option G's raw signals per figure caption, so any threshold can be applied
later. Same logic as prototype/gflags.py (frozen), with the uncropped signal taken from the skill's own
uncropped_figure warnings (its suppressions included) and each side's disagreement kept as a signed number of text
rows (+ = the second opinion reaches further than the current crop, - = it stops sooner)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

sset, base, regs, outp = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
rows = []
for rj in sorted(regs.glob("*.json")):
    k = rj.stem
    bj = base / k / f"{k}.json"
    if not bj.exists():
        continue
    doc = json.load(open(bj))
    reg = json.load(open(rj))
    heights = {p["page"]: p["height"] for p in doc["pages"]}
    byid = {b["id"]: b for b in doc["blocks"]}
    warned = {w["block"] for w in doc["warnings"] if w["code"] == "uncropped_figure"}
    for pno, floats in reg["floats"].items():
        pno = int(pno)
        H = heights[pno]
        row = P.ROW * H
        pb = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"]]
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
            d = ["", "", "", ""]
            if cur and f["bbox"]:
                s = f["bbox"]
                d = [round(x / row, 2) for x in (cur[1] - s[1], s[3] - cur[3], cur[0] - s[0], s[2] - cur[2])]
            rows.append([sset, k, pno, c["id"], int(c["id"] in warned), len(mine), int(bool(f["bbox"])), *d])
with open(outp, "w") as out:
    out.write("set\tkey\tpage\tcaption\twarn_uncropped\tncrops\tsecond_has_box\td_top\td_bottom\td_left\td_right\n")
    for r in rows:
        out.write("\t".join(map(str, r)) + "\n")
print(sset, len(rows), "captions")
