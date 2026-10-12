# /// script
# dependencies = ["pypdfium2", "pillow"]
# ///
"""items.py SET BASE_DIR PDF_DIR REG_DIR OUT_DIR: one grading image per figure caption, blind to the second opinion:
the caption's page with every crop the current skill made on it (red) and the caption (blue). Appends one row per
caption to OUT_DIR/items.tsv: id, set, key, page, caption id, caption text. Ids are random so a grader sees no
paper names or order."""
import json, random, sys
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

sset, base, pdfs, regs, out = sys.argv[1], *map(Path, sys.argv[2:6])
(out / "img").mkdir(parents=True, exist_ok=True)
taken = {l.split("\t")[0] for l in open(out / "items.tsv")} if (out / "items.tsv").exists() else set()
rng = random.Random()
rows = []
for rj in sorted(regs.glob("*.json")):
    k = rj.stem
    if not (pdfs / f"{k}.pdf").exists():
        continue
    doc = json.load(open(base / k / f"{k}.json"))
    reg = json.load(open(rj))
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    byid = {b["id"]: b for b in doc["blocks"]}
    pdf = pdfium.PdfDocument(str(pdfs / f"{k}.pdf"))
    for pno, floats in sorted(reg["floats"].items(), key=lambda kv: int(kv[0])):
        pno = int(pno)
        w, h = sizes[pno]
        page = pdf[pno - 1]
        img = page.render(scale=w / page.get_size()[0]).to_pil().convert("RGB")
        if img.size != (w, h):
            img = img.resize((w, h))
        d = ImageDraw.Draw(img)
        for b in doc["blocks"]:
            if b["page"] == pno and b["bbox"] and (b["label"] == "figure" or (b["label"] in ("image", "chart") and "merged_into" not in b)):
                x1, y1, x2, y2 = b["bbox"]
                d.rectangle([x1 - 6, y1 - 6, x2 + 6, y2 + 6], outline=(230, 0, 0), width=4)
        for f in floats:
            cap = byid[f["caption"]]
            im = img.copy()
            x1, y1, x2, y2 = cap["bbox"]
            ImageDraw.Draw(im).rectangle([x1 - 4, y1 - 4, x2 + 4, y2 + 4], outline=(0, 70, 255), width=5)
            im.thumbnail((1250, 1600))
            while True:
                iid = "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(5))
                if iid not in taken:
                    break
            taken.add(iid)
            im.save(out / "img" / f"{iid}.jpg", quality=88)
            rows.append([iid, sset, k, pno, cap["id"], " ".join(cap["text"].split())[:90]])
with open(out / "items.tsv", "a") as f:
    for r in rows:
        f.write("\t".join(map(str, r)) + "\n")
print(sset, len(rows), "items")
