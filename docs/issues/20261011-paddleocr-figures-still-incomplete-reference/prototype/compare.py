# /// script
# dependencies = []
# ///
"""compare.py BASE_DIR REG_DIR OUT_TSV: per figure caption, the current skill's crops against the prototype's crop.
A current crop goes with the nearest caption below sharing its columns, else the nearest above (as uncropped_figure
pairs them). Status: same (one crop each, IoU >= 0.9), or diff (to be looked at)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402


def iou(a, b):
    i = P.box_overlap(a, b)
    return i / (P.box_area(a) + P.box_area(b) - i) if i else 0.0


rows = []
for rj in sorted(Path(sys.argv[2]).glob("*.json")):
    key = rj.stem
    base = json.load(open(Path(sys.argv[1]) / key / f"{key}.json"))
    reg = json.load(open(rj))
    heights = {p["page"]: p["height"] for p in base["pages"]}
    byid = {b["id"]: b for b in base["blocks"]}
    for pno, floats in reg["floats"].items():
        pno = int(pno)
        pb = [b for b in base["blocks"] if b["page"] == pno and b["bbox"]]
        crops = [b for b in pb if b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)]
        captions = [byid[f["caption"]] for f in floats]
        reach = P.UNCROPPED_REACH * heights[pno]
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
            bbox = P.box_union([m["bbox"] for m in mine]) if mine else None
            if len(mine) == 1 and f["bbox"] and iou(bbox, f["bbox"]) >= 0.9:
                st = "same"
            elif not mine and not f["bbox"]:
                st = "both-none"
            else:
                st = "diff"
            rows.append([key, pno, c["id"], st, len(mine), round(iou(bbox, f["bbox"]), 2) if bbox and f["bbox"] else "",
                         f.get("dir") or "", " ".join(c["text"].split())[:70]])
with open(sys.argv[3], "w") as out:
    out.write("key\tpage\tcaption\tstatus\tbase_crops\tiou\tdir\ttext\n")
    for r in rows:
        out.write("\t".join(map(str, r)) + "\n")
from collections import Counter
print(Counter(r[3] for r in rows), len(rows))
