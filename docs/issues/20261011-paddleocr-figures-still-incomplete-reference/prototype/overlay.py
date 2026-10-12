# /// script
# dependencies = ["pypdfium2", "pillow"]
# ///
"""overlay.py PARSE_JSON PDF REGION_JSON PAGE[,PAGE] OUTDIR [TAG]: two copies of each page side by side —
left: the current skill's crops (red = merged figure, orange = single block), right: the prototype's
(red = crop, grey = float region, purple = member blocks); blue = captions on both."""
import json, sys
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

doc = json.load(open(sys.argv[1]))
src = Path(sys.argv[2])
pdf = pdfium.PdfDocument(str(src)) if src.suffix == ".pdf" else None
files = sorted(p for p in src.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")) if pdf is None else None
reg = json.load(open(sys.argv[3]))
pages = [int(p) for p in sys.argv[4].split(",")]
out = Path(sys.argv[5]); out.mkdir(parents=True, exist_ok=True)
tag = sys.argv[6] if len(sys.argv) > 6 else Path(sys.argv[1]).stem
sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
byid = {b["id"]: b for b in doc["blocks"]}
for pno in pages:
    w, h = sizes[pno]
    if pdf is not None:
        page = pdf[pno - 1]
        base = page.render(scale=w / page.get_size()[0]).to_pil().convert("RGB")
    else:
        base = Image.open(files[pno - 1]).convert("RGB").resize((w, h))
    left, right = base.copy(), base.copy()
    dl, dr = ImageDraw.Draw(left), ImageDraw.Draw(right)
    for b in doc["blocks"]:
        if b["page"] != pno or not b["bbox"]:
            continue
        if b["label"] == "figure":
            x1, y1, x2, y2 = b["bbox"]; dl.rectangle([x1 - 5, y1 - 5, x2 + 5, y2 + 5], outline=(220, 0, 0), width=4)
        elif b["label"] in ("image", "chart") and "merged_into" not in b:
            dl.rectangle(b["bbox"], outline=(255, 140, 0), width=4)
        elif b["label"] == "table":
            dl.rectangle(b["bbox"], outline=(150, 0, 200), width=2)
    for f in reg["floats"].get(str(pno), []):
        cap = byid[f["caption"]]
        for d in (dl, dr):
            d.rectangle(cap["bbox"], outline=(0, 60, 220), width=2)
        if f.get("region"):
            dr.rectangle(f["region"], outline=(150, 150, 150), width=2)
        for m in f["members"]:
            dr.rectangle(byid[m]["bbox"], outline=(150, 0, 200), width=1)
        if f["bbox"]:
            x1, y1, x2, y2 = f["bbox"]; dr.rectangle([x1 - 5, y1 - 5, x2 + 5, y2 + 5], outline=(220, 0, 0), width=4)
    sheet = Image.new("RGB", (2 * w + 20, h), "white")
    sheet.paste(left, (0, 0)); sheet.paste(right, (w + 20, 0))
    sheet.thumbnail((1400, 1400))
    sheet.save(out / f"{tag}_p{pno:02d}.png")
