# /// script
# dependencies = ["pypdfium2", "numpy", "pillow", "scipy"]
# ///
"""region_images.py PARSE_JSON IMAGE_DIR OUT_JSON: the frozen prototype on a parse of page images (screenshots):
I/O only — page images come from the input files instead of a PDF render, and there is no text layer. Rules untouched."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import region as R  # noqa: E402

doc = json.load(open(sys.argv[1]))
files = sorted(p for p in Path(sys.argv[2]).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
role, why, body_styles = R.classify(doc, None)
whole = R.load_whole(Path(sys.argv[1]).stem)
res, orph = {}, {}
for pno, (w, h) in sizes.items():
    pblocks = [b for b in doc["blocks"] if b["page"] == pno and b["bbox"] and b["label"] != "figure"]
    if not any(role.get(b["id"]) == "caption" for b in pblocks):
        continue
    img = np.asarray(Image.open(files[pno - 1]).convert("RGB").resize((w, h)))
    res[pno], orph[pno] = R.page_floats(pblocks, role, (w, h), img, None, whole.get(pno), lambda b: False)
json.dump({"floats": res, "orphans": orph, "role": role, "why": why}, open(sys.argv[3], "w"))
