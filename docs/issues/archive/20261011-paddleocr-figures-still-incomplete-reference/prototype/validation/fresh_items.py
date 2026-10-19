"""items.py OUT_DIR PDF_DIR SHOTS_DIR GRADE_DIR: one grading image per figure caption of the fresh batch, blind to the
checks: the caption's page with every crop (red) and the caption (blue). A caption at the top of a page whose page
before ends in crops no caption takes is shown with that page to its left. Writes GRADE_DIR/items.tsv: id, key, page,
caption id, two_page, caption text. Runs in the paddleocr tool env."""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P
sys.modules["parse"] = P
import figcheck as F
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

out, pdfs, shots, grade = map(Path, sys.argv[1:5])
(grade / "img").mkdir(parents=True, exist_ok=True)
rng, taken, rows = random.Random(), set(), []

def render(k, page, size, src):
    if src.is_dir():
        files = sorted([f for f in src.iterdir() if f.suffix.lower() in (".jpg", ".png")], key=lambda f: P.natural_key(f.name))
        return Image.open(files[page - 1]).convert("RGB").resize(size)
    pg = pdfium.PdfDocument(str(src))[page - 1]
    img = pg.render(scale=size[0] / pg.get_size()[0]).to_pil().convert("RGB")
    return img if img.size == size else img.resize(size)

def boxes(img, blocks, page):
    d = ImageDraw.Draw(img)
    for b in blocks:
        if b["page"] == page and F.is_crop(b):
            x1, y1, x2, y2 = b["bbox"]
            d.rectangle([x1 - 6, y1 - 6, x2 + 6, y2 + 6], outline=(230, 0, 0), width=4)
    return img

for jp in sorted(out.glob("*/*.json")):
    k = jp.stem
    rec = json.loads(jp.read_text())
    src = shots / k if (shots / k).is_dir() else pdfs / f"{k}.pdf"
    sizes = {p["page"]: (p["width"], p["height"]) for p in rec["pages"]}
    blocks = [b for b in rec["blocks"] if b["bbox"]]
    loose_end = {}
    for page, (w, h) in sizes.items():
        pb = [b for b in blocks if b["page"] == page]
        mine, loose = F.owners(pb, [b for b in pb if F.is_figure_caption(b)], h)
        loose_end[page] = any(cr["bbox"][3] > h / 2 for cr in loose)
    for page, (w, h) in sorted(sizes.items()):
        pb = [b for b in blocks if b["page"] == page]
        caps = [b for b in pb if F.is_figure_caption(b)]
        if not caps:
            continue
        mine, _ = F.owners(pb, caps, h)
        base = boxes(render(k, page, (w, h), src), blocks, page)
        for c in caps:
            two = c["id"] not in mine and c["bbox"][1] < h / 3 and loose_end.get(page - 1, False)
            im = base.copy()
            x1, y1, x2, y2 = c["bbox"]
            ImageDraw.Draw(im).rectangle([x1 - 4, y1 - 4, x2 + 4, y2 + 4], outline=(0, 70, 255), width=5)
            if two:
                left = boxes(render(k, page - 1, sizes[page - 1], src), blocks, page - 1)
                both = Image.new("RGB", (left.width + im.width + 20, max(left.height, im.height)), (120, 120, 120))
                both.paste(left, (0, 0)); both.paste(im, (left.width + 20, 0))
                im = both
                im.thumbnail((2400, 1600))
            else:
                im.thumbnail((1250, 1600))
            while (iid := "".join(rng.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(5))) in taken:
                pass
            taken.add(iid)
            im.save(grade / "img" / f"{iid}.jpg", quality=88)
            rows.append([iid, k, page, c["id"], int(two), " ".join(c["text"].split())[:90]])
with open(grade / "items.tsv", "w") as f:
    for r in rows:
        f.write("\t".join(map(str, r)) + "\n")
print(len(rows), "items,", sum(r[4] for r in rows), "two-page")
