# /// script
# dependencies = ["pypdfium2"]
# ///
"""fontprobe.py PARSE_JSON PDF PAGE[,PAGE]: per block on the pages, the text layer's font size and font under it,
against the document's body font (the size/font carrying most characters in long text blocks)."""
import ctypes, json, sys
from collections import Counter
import pypdfium2 as pdfium
import pypdfium2.raw as raw

doc = json.load(open(sys.argv[1]))
pdf = pdfium.PdfDocument(sys.argv[2])
pages = [int(p) for p in sys.argv[3].split(",")]
sizes = {p["page"]: (p["width"], p["height"]) for p in doc["pages"]}


def chars(pno):
    page = pdf[pno - 1]
    tp = page.get_textpage()
    W, H = page.get_size()
    sx = sizes[pno][0] / W
    out = []
    buf = ctypes.create_string_buffer(256)
    flags = ctypes.c_int()
    for i in range(tp.count_chars()):
        c = raw.FPDFText_GetUnicode(tp, i)
        if c <= 32:
            continue
        l, b, r, t = tp.get_charbox(i)
        n = raw.FPDFText_GetFontInfo(tp, i, buf, 256, ctypes.byref(flags))
        name = buf.value.decode("latin-1", "replace").split("+")[-1]
        m = raw.FS_MATRIX(); raw.FPDFText_GetMatrix(tp, i, ctypes.byref(m))
        size = raw.FPDFText_GetFontSize(tp, i) * (m.c * m.c + m.d * m.d) ** 0.5
        out.append(((l + r) / 2 * sx, (H - (t + b) / 2) * sx, round(size * 2) / 2, name))
    return out


def under(cs, box):
    return [c for c in cs if box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]]


allc = {p: chars(p) for p in sizes}
body = Counter()
for b in doc["blocks"]:
    if b["label"] == "text" and len(b["text"]) >= 300 and b["bbox"]:
        for c in under(allc[b["page"]], b["bbox"]):
            body[(c[2], c[3])] += 1
print("body font:", body.most_common(3))
for p in pages:
    print(f"--- page {p}")
    for b in doc["blocks"]:
        if b["page"] != p or not b["bbox"]:
            continue
        cs = under(allc[p], b["bbox"])
        sz = Counter(c[2] for c in cs).most_common(1)
        fn = Counter(c[3] for c in cs).most_common(1)
        print(f"{b['id']:4} {b['label'][:14]:14} {str(b['bbox']):24} len{len(b['text']):5} chars{len(cs):5} "
              f"size {sz[0][0] if sz else '-':>5} font {fn[0][0][:28] if fn else '-':28} {b['text'][:40]!r}")
