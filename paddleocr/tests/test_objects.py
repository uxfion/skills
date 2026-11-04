# /// script
# requires-python = ">=3.9"
# dependencies = ["numpy", "opencv-python-headless", "pypdfium2", "reportlab"]
# ///
"""Tests for `doc.py objects`: the figures and tables a note links to, placed in the PDF.

The PDF is made here with reportlab: page 1 has a crop box offset from the media box, page 2 is rotated. The record's
boxes are where poppler finds the words inside the crop box (`pdftotext -bbox -cropbox`, the page as PaddleOCR saw it),
and the rects expected are where poppler finds them in the media box, which starts at the origin of the PDF's user
space (`pdftotext -bbox`): two readings that never pass through doc.py."""
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import doc as D  # noqa: E402

MEDIA_H, SCALE = 792, 2.0
CROP = (9, 18, 603, 774)
WORDS = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>')


def make_pdf(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=(612, MEDIA_H))
    c.setCropBox(CROP)
    c.setFont("Helvetica", 10)
    for x, y, text in [(100, 700, "LEFTPANEL"), (300, 700, "RIGHTPANEL"), (100, 680, "Fig. 1. Two panels."),
                       (100, 600, "TABLE II"), (100, 500, "Table 7 shows that it works.")]:
        c.drawString(x, y, text)
    c.showPage()
    c.setPageRotation(90)
    c.drawString(100, 700, "TABLE III")
    c.showPage()
    c.save()


def words(pdf, *flags):
    """{word: (x1, y1, x2, y2)} on page 1, in points from the top left of the box poppler reads by (y down)."""
    out = subprocess.run(["pdftotext", "-bbox", *flags, "-f", "1", "-l", "1", str(pdf), "-"], capture_output=True,
                         text=True, check=True).stdout
    return {m.group(5): tuple(float(v) for v in m.group(1, 2, 3, 4)) for m in WORDS.finditer(out)}


def union(*boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


@unittest.skipUnless(shutil.which("pdftotext"), "needs poppler's pdftotext")
class Objects(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="objects-"))
        self.pdf = self.dir / "paper.pdf"
        make_pdf(self.pdf)
        crop, media = words(self.pdf, "-cropbox"), words(self.pdf)
        px = lambda *names: [round(v * SCALE) for v in union(*(crop[n] for n in names))]  # noqa: E731
        # expected: the media box's reading, y turned up
        self.rect = lambda *names: (lambda b: [b[0], MEDIA_H - b[3], b[2], MEDIA_H - b[1]])(union(*(media[n] for n in names)))
        block = lambda i, label, box, text: {"id": i, "label": label, "box": box, "text": text}  # noqa: E731
        fig = lambda i, caption, number, box: {"id": i, "image": f"imgs/{i}.png", "caption": caption, "number": number,  # noqa: E731
                                               "members": [], "inside": [],
                                               "changes": [{"by": "auto:figures", "box": box}]}
        size = [round((CROP[2] - CROP[0]) * SCALE), round((CROP[3] - CROP[1]) * SCALE)]
        self.record = {
            "format": D.FORMAT,
            "source": {"kind": "pdf", "path": str(self.pdf), "sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
                       "page_count": 2, "pages": [1, 2]},
            "run": {"options": {}},
            "pages": [{"page": 1, "image_size": size, "scale": SCALE}, {"page": 2, "image_size": size[::-1], "scale": SCALE}],
            "blocks": [
                block("p1-3", "figure_title", px("Fig.", "1.", "Two", "panels."), "Fig. 1. Two panels."),
                block("p1-4", "figure_title", px("TABLE", "II"), "TABLE II"),
                block("p1-5", "text", [200, 990, 700, 1010], "Table 7 shows that it works."),
                block("p1-7", "figure_title", [200, 1200, 600, 1220], "Supplementary Fig. 3. More."),
                block("p1-9", "figure_title", [200, 1300, 600, 1320], "Fig. 4. Once."),
                block("p1-10", "text", [200, 1400, 600, 1420], "Table V. Results."),
                block("p2-1", "figure_title", [200, 100, 300, 120], "TABLE III"),
                block("p2-3", "figure_title", [200, 400, 600, 420], "Fig. 4. Again."),
                block("p2-4", "figure_title", [200, 500, 600, 520], "TABLE V (continued)"),
            ],
            "figures": [fig("p1-1", "p1-3", "Fig. 1", px("LEFTPANEL")), fig("p1-2", "p1-3", "Fig. 1", px("RIGHTPANEL")),
                        fig("p1-6", "p1-7", "Supplementary Fig. 3", [200, 1100, 600, 1190]),
                        fig("p1-8", "p1-9", "Fig. 4", [200, 1230, 600, 1290]),
                        fig("p2-2", "p2-3", "Fig. 4", [200, 200, 600, 390])],
            "findings": [], "checks": {},
        }
        self.folder = self.dir / "paper"
        self.folder.mkdir()
        (self.folder / "paper.json").write_text(json.dumps(self.record), encoding="utf-8")
        (self.folder / "paper.md").write_text("an edit that commit would refuse\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def objects(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = D.main(["objects", str(self.folder), "--source", str(self.pdf)])
        self.assertEqual(code, 0, err.getvalue())
        return {o["id"]: o for o in map(json.loads, out.getvalue().splitlines())}

    def test_keys(self):
        got = {i: (o["kind"], o["key"], o["number"]) for i, o in self.objects().items()}
        self.assertEqual(got, {
            "p1-1": ("figure", "fig:1", "Fig. 1"),            # its two pieces are one object
            "p1-4": ("table", "table:II", "TABLE II"),        # "Table 7 shows ..." is running text, no caption
            "p1-6": ("figure", "fig:S3", "Supplementary Fig. 3"),
            "p1-8": ("figure", None, "Fig. 4"), "p2-2": ("figure", None, "Fig. 4"),            # two captions say Fig. 4
            "p1-10": ("table", None, "Table V"), "p2-4": ("table", None, "TABLE V"),        # and two say Table V
            "p2-1": ("table", "table:III", "TABLE III"),
        })

    def test_rects_in_the_pdfs_user_space(self):
        got = self.objects()
        for ident, names in (("p1-1", ("LEFTPANEL", "RIGHTPANEL")), ("p1-4", ("TABLE", "II"))):
            want = self.rect(*names)
            for g, w in zip(got[ident]["rect"], want):
                self.assertAlmostEqual(g, w, delta=0.6, msg=f"{ident}: {got[ident]['rect']} != {want}")
            self.assertAlmostEqual(got[ident]["top"], (CROP[3] - want[3]), delta=0.6)
            self.assertEqual(got[ident]["page_label"], "1")
        self.assertEqual((got["p2-1"]["rect"], got["p2-1"]["top"]), (None, None))   # page 2 is rotated

    def test_reads_only(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.objects()
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
