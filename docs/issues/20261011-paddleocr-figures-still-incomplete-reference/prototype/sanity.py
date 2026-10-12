# /// script
# dependencies = []
# ///
"""sanity.py BASE_DIR REG_DIR: automatic checks on the prototype's crops — two crops on a page overlapping (a false
merge), a crop covering another figure's caption or running text (swallowed), and the flags the prototype raised."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P  # noqa: E402

over, swallow, flags, orphans = [], [], Counter(), []
for rj in sorted(Path(sys.argv[2]).glob("*.json")):
    k = rj.stem
    base = json.load(open(Path(sys.argv[1]) / k / f"{k}.json"))
    reg = json.load(open(rj))
    byid = {b["id"]: b for b in base["blocks"]}
    for pno, floats in reg["floats"].items():
        crops = [f for f in floats if f["bbox"]]
        for i, a in enumerate(crops):
            for b in crops[i + 1:]:
                o = P.box_overlap(a["bbox"], b["bbox"])
                if o > 0.05 * min(P.box_area(a["bbox"]), P.box_area(b["bbox"])):
                    over.append((k, pno, a["caption"], b["caption"]))
            for f in a.get("flags", []):
                flags[f.split(":")[0]] += 1
            for b in base["blocks"]:
                if b["page"] != int(pno) or not b["bbox"] or b["id"] in a["members"]:
                    continue
                role = reg["role"].get(str(b["id"]))
                if (role == "caption" and b["id"] != a["caption"]) or role == "flow":
                    o = P.box_overlap(a["bbox"], b["bbox"]) / max(1, P.box_area(b["bbox"]))
                    if o > 0.3:
                        swallow.append((k, pno, a["caption"], b["id"], b["label"], round(o, 2), b["text"][:50]))
        for o in reg.get("orphans", {}).get(pno, []):
            orphans.append((k, pno, o, byid[o]["label"], byid[o]["text"][:40]))
print("overlapping crops:", len(over)); [print(" ", x) for x in over]
print("crops covering a caption or running text:", len(swallow)); [print(" ", x) for x in swallow]
print("flags:", dict(flags))
print("orphan figure-like blocks:", len(orphans)); [print(" ", x) for x in orphans[:40]]
