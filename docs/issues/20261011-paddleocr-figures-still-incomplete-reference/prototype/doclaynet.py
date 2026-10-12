# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["torch", "torchvision", "transformers>=4.45,<5", "timm", "pillow", "pypdfium2", "scipy"]
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# torchvision = { index = "pytorch-cpu" }
# ///
"""doclaynet.py MODEL OUT_DIR KEY:PAGE[,PAGE] ...: boxes of a DocLayNet-trained detector (HF transformers) on PDF pages
rendered at the parse's page size, as OUT_DIR/<model>/<key>.json {page: [{label, score, bbox}]}."""
import json, sys
from pathlib import Path
import pypdfium2 as pdfium
import torch
from transformers import AutoImageProcessor, AutoModelForObjectDetection

W = Path(__file__).resolve().parent.parent
model_id, out = sys.argv[1], Path(sys.argv[2]) / sys.argv[1].replace("/", "__")
out.mkdir(parents=True, exist_ok=True)
proc = AutoImageProcessor.from_pretrained(model_id)
if "cmarkea" in model_id:
    from transformers import DetrForSegmentation
    model = DetrForSegmentation.from_pretrained(model_id).eval()
else:
    model = AutoModelForObjectDetection.from_pretrained(model_id).eval()
labels = model.config.id2label
for arg in sys.argv[3:]:
    key, pages = arg.split(":")
    doc = json.load(open(W / "base" / key / f"{key}.json"))
    sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}
    pdf = pdfium.PdfDocument(str(W / "pdf" / f"{key}.pdf"))
    res = json.load(open(out / f"{key}.json")) if (out / f"{key}.json").exists() else {}
    for p in map(int, pages.split(",")):
        w, h = sizes[p]
        page = pdf[p - 1]
        img = page.render(scale=w / page.get_size()[0]).to_pil().convert("RGB")
        inputs = proc(images=img, return_tensors="pt")
        with torch.no_grad():
            o = model(**inputs)
        r = proc.post_process_object_detection(o, threshold=0.3, target_sizes=[(img.height, img.width)])[0]
        res[str(p)] = [{"label": labels[int(l)], "score": round(float(s), 3), "bbox": [round(float(v)) for v in b]}
                       for s, l, b in zip(r["scores"], r["labels"], r["boxes"])]
        print(key, p, sum(1 for x in res[str(p)] if x["label"] in ("Picture", "picture")), "pictures", flush=True)
    json.dump(res, open(out / f"{key}.json", "w"))
