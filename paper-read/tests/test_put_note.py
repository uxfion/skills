# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pr.py put (scripts/put_note.py) against tests/fake_p2z.py, which also stands in for paddleocr's
`ocr.py objects`: a note put into Zotero with its figures and tables linked, and its file left without links."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "put_note.py"
sys.path.insert(0, str(HERE.parent / "scripts"))
from prlib import sources  # noqa: E402

STEM = "xiaoTCACE2026.Published-IEEE"
URL = "zotero://open-pdf/library/items/PDFKEY01"
NOTE = """---
parent: xiaoTCACE2026
---
# 论文笔记

T-CACE 一个模型同时合成和分割（Fig. 1, p.2）。

读的版本：Published-IEEE

## Q5 做了哪些实验？ [已答]

消融（Table III, p.3；Fig. 9, p.3；Fig. 4, p.2）。Fig. 99 不在包里，Figure 9 和 Fig. 9 是同一张图。
"""
BOX = {"page_label": "3", "rect": [48.0, 407.0, 284.5, 595.0], "top": 197.0}
OBJECTS = [{"id": "p2-2", "kind": "figure", "key": "fig:1", "number": "Fig. 1", "page": 2, **BOX},
           {"id": "p3-2", "kind": "table", "key": "table:III", "number": "TABLE III", "page": 3, **BOX},
           {"id": "p3-6", "kind": "figure", "key": "fig:9", "number": "Fig. 9", "page": 3, **BOX},
           {"id": "p2-9", "kind": "figure", "key": "fig:4", "number": "Fig. 4", "page": 2, "page_label": "2",
            "rect": None, "top": None},
           {"id": "p3-8", "kind": "figure", "key": None, "number": "Fig. 5", "page": 3, **BOX}]


class PutNote(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="paper-read-put-"))
        self.lib = self.dir / "library.json"
        self.lib.write_text(json.dumps({"objects": OBJECTS}), encoding="utf-8")
        self.note = self.dir / f"{STEM}.note.md"
        self.note.write_text(NOTE, encoding="utf-8")
        (self.dir / f"{STEM}.zotero.json").write_text(json.dumps({"attachment": "PDFKEY01"}), encoding="utf-8")
        (self.dir / STEM).mkdir()
        (self.dir / f"{STEM}.pdf").write_bytes(b"%PDF-1.4\n")   # ocr.py objects reads it; the fake does not

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_it(self, note=None, **env):
        env = {**os.environ, "PAPER_READ_P2Z": str(HERE / "fake_p2z.py"), "PAPER_READ_OCR": str(HERE / "fake_p2z.py"),
               "FAKE_P2Z": str(self.lib), **env}
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), str(note or self.note)],
                              capture_output=True, text=True, timeout=120, env=env)
        return done.returncode, (json.loads(done.stdout) if done.stdout else None), done.stderr

    def put(self, n):
        """What note put was given, the n-th time."""
        return Path(f"{self.lib}.put.{n}").read_text(encoding="utf-8")

    def library(self, **fields):
        self.lib.write_text(json.dumps({**json.loads(self.lib.read_text(encoding="utf-8")), **fields}), encoding="utf-8")

    def test_linked_put_and_left_clean(self):
        code, out, err = self.run_it()
        self.assertEqual((code, out["code"]), (0, "ok"), err)
        self.assertEqual(out["links"], {"figures": 4, "tables": 1})
        self.assertEqual(out["annotations"], {"created": 3, "kept": 0})
        self.assertEqual([(u["token"], u["why"]) for u in out["unmatched"]],
                         [("Fig. 4", "rotated_page"), ("Fig. 99", "not_in_package")])
        self.assertTrue(all(u["hint"] for u in out["unmatched"]))
        put = self.put(0)
        for link in (f"[Fig. 1]({URL}?annotation=ANNOT000)", f"[Table III]({URL}?annotation=ANNOT001)",
                     f"[Fig. 9]({URL}?annotation=ANNOT002)", f"[Figure 9]({URL}?annotation=ANNOT002)",
                     "Fig. 4, p.2", "Fig. 99 "):
            self.assertIn(link, put)
        self.assertNotIn("?page=", put)   # pages stay plain text
        self.assertEqual(sources.strip(put), NOTE)
        boxes = json.loads(self.lib.read_text(encoding="utf-8"))["annotations"]
        self.assertEqual(sorted(boxes), ["paper-read · Fig. 1", "paper-read · Fig. 9", "paper-read · Table III"])
        # the file: the note as written, with the key and version note put -i wrote into it
        self.assertEqual(self.note.read_text(encoding="utf-8"), NOTE.replace("---\n", "---\nkey: NOTEKEY1\nversion: 8\n", 1))

        code, again, err = self.run_it()   # a second put finds its boxes and links alike
        self.assertEqual((code, again["annotations"]), (0, {"created": 0, "kept": 3}), err)
        self.assertEqual(sources.strip(self.put(1)), self.note.read_text(encoding="utf-8"))
        self.assertEqual(self.put(1).split("---\n", 2)[2], put.split("---\n", 2)[2])

    def test_without_package_paddleocr_or_pdf_key(self):
        shutil.rmtree(self.dir / STEM)
        code, out, err = self.run_it()
        self.assertEqual((code, out["links"]), (0, {"figures": 0, "tables": 0}), err)
        self.assertEqual({u["why"] for u in out["unmatched"]}, {"no_package"})
        (self.dir / STEM).mkdir()
        code, out, err = self.run_it(PAPER_READ_OCR=str(self.dir / "no-paddleocr" / "ocr.py"))
        self.assertEqual({u["why"] for u in out["unmatched"]}, {"no_paddleocr"}, err)
        (self.dir / f"{STEM}.zotero.json").unlink()
        self.note.write_text(NOTE, encoding="utf-8")
        code, out, err = self.run_it()
        self.assertEqual((code, out["links"], {u["why"] for u in out["unmatched"]}),
                         (0, {"figures": 0, "tables": 0}, {"no_pdf"}), err)
        self.assertEqual(self.put(2), NOTE)

    def test_a_put_refused_leaves_the_file_clean(self):
        self.library(put_code="version_conflict")
        code, out, err = self.run_it()
        self.assertEqual((code, out["code"], out["put"]["code"], out["hint"]),
                         (1, "version_conflict", "version_conflict", "as the real one says"), err)
        self.assertNotEqual(self.put(0), NOTE)
        self.assertEqual(self.note.read_text(encoding="utf-8"), NOTE)

    def test_what_stops_it(self):
        code, out, err = self.run_it(note=self.dir / "gone.note.md")
        self.assertEqual((code, out["code"], out["file"], err), (1, "file_not_found", str(self.dir / "gone.note.md"), ""))
        with socket.socket() as s:   # Zotero not running: a port just closed, the real paper-to-zotero
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code, out, err = self.run_it(PAPER_READ_P2Z="", PAPER_TO_ZOTERO_BASE_URL=f"http://127.0.0.1:{port}",
                                     PAPER_TO_ZOTERO_CONFIG=str(self.dir / "no-config.json"),
                                     no_proxy="127.0.0.1,localhost", NO_PROXY="127.0.0.1,localhost")
        last = json.loads(err.splitlines()[-1])
        self.assertEqual((code, out, last["code"], last["step"]), (2, None, "zotero_unreachable", "annotate"))
        self.assertEqual(self.note.read_text(encoding="utf-8"), NOTE)   # nothing put, the file as it was
        (self.dir / f"{STEM}.zotero.json").unlink()   # nothing to link: note put is the step that cannot go on
        code, out, err = self.run_it(PAPER_READ_P2Z="", PAPER_TO_ZOTERO_BASE_URL=f"http://127.0.0.1:{port}",
                                     PAPER_TO_ZOTERO_CONFIG=str(self.dir / "no-config.json"),
                                     no_proxy="127.0.0.1,localhost", NO_PROXY="127.0.0.1,localhost")
        last = json.loads(err.splitlines()[-1])
        self.assertEqual((code, out, last["code"], last["step"]), (2, None, "zotero_unreachable", "note put"))
        self.assertEqual(self.note.read_text(encoding="utf-8"), NOTE)

    def test_links_left_in_the_file_are_taken_off_first(self):
        self.note.write_text(NOTE.replace("Fig. 99", f"[Fig. 99]({URL}?annotation=OLDBOX01)"), encoding="utf-8")
        code, out, err = self.run_it()
        self.assertEqual(code, 0, err)
        self.assertNotIn("OLDBOX01", self.put(0))
        self.assertIn("Fig. 99", [u["token"] for u in out["unmatched"]])


if __name__ == "__main__":
    unittest.main()
