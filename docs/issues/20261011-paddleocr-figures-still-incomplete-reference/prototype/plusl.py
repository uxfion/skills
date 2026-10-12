"""plusl.py BASE_DIR PDF_DIR OUT_DIR: PP-DocLayout_plus-L boxes (PP-StructureV3 settings) on every page that has a
figure caption or a figure block, rendered as the pipeline renders. Runs in the paddleocr tool env."""
import json, re, sys
from pathlib import Path
import pypdfium2 as pdfium
from paddlex import create_model
from paddlex.inference.pipelines import load_pipeline_config
from paddlex.inference.utils.pdf_rendering import render_pdf_page_to_numpy

base, pdfs, out = map(Path, sys.argv[1:4])
out.mkdir(exist_ok=True)
cfg = load_pipeline_config("PP-StructureV3")["SubModules"]["LayoutDetection"]
params = {k: cfg[k] for k in ("threshold", "layout_nms", "layout_unclip_ratio", "layout_merge_bboxes_mode") if cfg.get(k) is not None}
model = create_model(model_name=cfg["model_name"])
cap = re.compile(r"\s*(\*\*)?\s*(extended\s+data\s+|supplementary\s+)?(fig\.?|figure)\s*[A-Z]?\d", re.I)
for jp in sorted(base.glob("*/*.json")):
    k = jp.stem
    if k != jp.parent.name or (out / f"{k}.json").exists():
        continue
    rec = json.loads(jp.read_text())
    imgdir = pdfs / k
    if imgdir.is_dir():
        import numpy as np
        from PIL import Image
        files = sorted(p for p in imgdir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    else:
        pdf = pdfium.PdfDocument(str(pdfs / f"{k}.pdf"))
        pdf.init_forms()
    res_all = {}
    for info in rec["pages"]:
        pb = [b for b in rec["blocks"] if b["page"] == info["page"]]
        if not any(b["label"] in ("image", "chart") or cap.match(b["text"] or "") for b in pb):
            continue
        if imgdir.is_dir():   # the pipeline's own page image of an image input is the image, as BGR
            img = np.asarray(Image.open(files[info["page"] - 1]).convert("RGB").resize((info["width"], info["height"])))[:, :, ::-1].copy()
        else:
            img = render_pdf_page_to_numpy(pdf[info["page"] - 1], page_index=info["page"])
        res = next(iter(model.predict(img, batch_size=1, **params)))
        res_all[info["page"]] = [{"label": b["label"], "bbox": [float(v) for v in b["coordinate"]]} for b in res.json["res"]["boxes"]]
    (out / f"{k}.json").write_text(json.dumps(res_all))
    print(k, len(res_all), flush=True)
