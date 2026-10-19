"""rules78.py FRESH: which reported figures of the fresh batch depend on second-opinion rules 7 (body lines) and 8
(headings), by running the figure check with each turned off. Runs in the paddleocr tool env."""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude/skills/paddleocr/scripts"))
import parse as P
sys.modules["parse"] = P
import figcheck as F
import pypdfium2 as pdfium
S = Path(sys.argv[1])
graded = {(r["key"], r["page"], r["caption"]): int(r["defined_tier"]) for r in csv.DictReader(open(S / "graded.tsv"), delimiter="\t")}
state, out = {}, {"full": set(), "no7": set(), "no8": set()}
orig_stop = F.second_opinion
for jp in sorted((S / "out").glob("*/*.json")):
    k = jp.stem
    if k.endswith("_scan"):
        continue
    rec = json.loads(jp.read_text())
    sizes = {p["page"]: (p["width"], p["height"]) for p in rec["pages"]}
    doc = {"kind": "pdf", "path": S / "pdf" / f"{k}.pdf", "stem": k}
    pdf = pdfium.PdfDocument(str(doc["path"])); pdf.init_forms()
    layers = {p: F.font_chars(pdf, p, s) for p, s in sizes.items()}
    imgs = {}
    image = lambda p: imgs.setdefault(p, P.page_image(doc, p, sizes[p], pdf))
    layout = lambda p: P.page_layout(state, k, p, image)
    for mode in out:
        saved = F.HEADING_ROWS, F.body_lines
        if mode == "no7":
            F.body_lines = lambda *a: []
        if mode == "no8":
            F.HEADING_ROWS = 10 ** 6           # rule 8 off: any running text below in its column makes a heading a stop
        ws = F.figure_warnings(rec["blocks"], sizes, layers, None, image, layout)
        F.HEADING_ROWS, F.body_lines = saved
        out[mode] |= {(k, str(w["page"]), str(w["block"])) for w in ws}
for mode in ("no7", "no8"):
    lost = out["full"] - out[mode]
    print(mode, "flags lost:", [(x, graded.get(x)) for x in sorted(lost)], "flags gained:", len(out[mode] - out["full"]))
