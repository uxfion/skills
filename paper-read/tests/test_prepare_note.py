# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/prepare_note.py, against tests/fake_p2z.py: a paper's note, package and PDF taken out of Zotero."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "prepare_note.py"
CITE = "xiaoTCACE2026"
ITEM = {"title": "T-CACE: A Time-Conditioned Autoregressive Contrast Enhancement Framework", "date": "Mar 2026",
        "publicationTitle": "IEEE Journal of Biomedical and Health Informatics", "DOI": "10.1109/jbhi.2025.3599387",
        "creators": [{"firstName": "Xiaojiao", "lastName": "Xiao", "creatorType": "author"}],
        "tags": [{"tag": "venue/JBHI"}, {"tag": "aka/T-CACE"}]}
PAPER = {"title": ITEM["title"], "first_author": "Xiao", "year": "2026",
         "venue": "IEEE Journal of Biomedical and Health Informatics", "doi": "10.1109/jbhi.2025.3599387", "aka": ["T-CACE"]}
MINE = "读的版本：T-CACE (arXiv v1)\n\n## Q1 这篇论文要解决什么问题，为什么重要？这是哪类论文？ [已答]\n\n回答（Fig. 2, p.4）。"
# as Zotero holds it: with the links put_note.py added
LINKED = MINE.replace("Fig. 2, p.4", "[Fig. 2](zotero://open-pdf/library/items/PDFKEY01?annotation=ANNOT001), "
                                     "[p.4](zotero://open-pdf/library/items/PDFKEY01?page=4)")
# The skeleton note-format.md shows is the expected value: prepare_note writes it with the paper's values in.
DOC = (HERE.parent / "references" / "note-format.md").read_text(encoding="utf-8")
SKELETON = (re.search(r"^## The skeleton\n.*?```markdown\n(.*?)```", DOC, re.S | re.M).group(1)
            .replace("<citation key>", CITE).replace("<PDF title>", "T-CACE (JBHI 2026)"))
BARE = f"""---
parent: {CITE}
---
# 论文笔记

读的版本：T-CACE (JBHI 2026)
"""


class PrepareNote(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="paper-read-"))
        self.lib = self.dir / "library.json"
        self.out = self.dir / "scratch"

    def tearDown(self):
        shutil.rmtree(self.dir)

    def library(self, notes=(), packages=("T-CACE (JBHI 2026)", "T-CACE (arXiv v1)")):
        self.lib.write_text(json.dumps({
            "items": {CITE: ITEM}, "notes": {CITE: list(notes)},
            "pdfs": {CITE: ["T-CACE (JBHI 2026)", "T-CACE (arXiv v1)"]}, "packages": {CITE: list(packages)},
            "findings": [{"id": 1, "code": "watermark", "status": "open"}, {"id": 2, "code": "watermark", "status": "open"},
                         {"id": 3, "code": "unchecked_table", "status": "settled"}]}, ensure_ascii=False), encoding="utf-8")

    def run_it(self, *extra):
        env = {**os.environ, "PAPER_READ_P2Z": str(HERE / "fake_p2z.py"), "FAKE_P2Z": str(self.lib)}
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), "--cite", CITE,
                               "-o", str(self.out), *extra], capture_output=True, text=True, timeout=120, env=env)
        return done.returncode, json.loads(done.stdout), done.stderr

    def structured_takes(self):
        calls = [json.loads(l) for l in Path(f"{self.lib}.log").read_text(encoding="utf-8").splitlines()]
        return [c[2:] for c in calls if c[:2] == ["structured", "take"]]

    def test_a_note_already_there_and_a_rerun(self):
        self.library(notes=[{"key": "NOTE0001", "title": "论文笔记", "text": LINKED},
                            {"key": "NOTE0002", "title": "Comment: 12 pages", "text": "旧的。"}])
        code, out, err = self.run_it()
        stem = self.out / f"{CITE}.T-CACE (arXiv v1)"
        self.assertEqual((code, out["code"], out["created"]), (0, "ok", False), err)
        self.assertEqual((out["note"], out["taken"], out["pdf"], out["package"], out["pdf_title"]),
                         (f"{stem}.note.md", f"{stem}.note.md.taken", f"{stem}.pdf", str(stem), "T-CACE (arXiv v1)"))
        mine = f"---\nkey: NOTE0001\nparent: {CITE}\n---\n# 论文笔记\n\n{MINE}\n"   # the links taken off, in both
        self.assertEqual(Path(out["note"]).read_text(encoding="utf-8"), mine)
        self.assertEqual(Path(out["taken"]).read_text(encoding="utf-8"), mine)
        self.assertEqual(out["old_notes"], [str(self.out / "notes" / f"{CITE}.NOTE0002.note.md")])
        self.assertEqual(out["open_findings"], {"watermark": 2})
        self.assertEqual(out["paper"], PAPER)
        # read in the arXiv version while the library ranks the published one first
        self.assertEqual((out["better_pdf"], out["previous"]), ("T-CACE (JBHI 2026)", None))
        # the version the note was read in is the one taken, not the best PDF
        self.assertEqual(self.structured_takes(), [["--cite", CITE, "-o", str(self.out), "--title", "T-CACE (arXiv v1)"]])

        # a rerun in the same change keeps the working note and the note as taken
        Path(out["note"]).write_text(mine + "\n## Q2 之前的工作怎么做，缺在哪里？ [进行中]\n", encoding="utf-8")
        code, again, err = self.run_it()
        self.assertEqual((code, again["code"], again["created"], again["note"]), (0, "ok", False, out["note"]), err)
        self.assertIn("[进行中]", Path(out["note"]).read_text(encoding="utf-8"))
        self.assertEqual(Path(out["taken"]).read_text(encoding="utf-8"), mine)
        self.assertEqual(again["old_notes"], out["old_notes"])

        # moving the note to the better version: the version it was read in comes along, to compare
        self.out = self.dir / "moved"
        code, moved, err = self.run_it("--title", "T-CACE (JBHI 2026)")
        old = self.out / f"{CITE}.T-CACE (arXiv v1)"
        self.assertEqual((code, moved["pdf_title"], moved["better_pdf"]), (0, "T-CACE (JBHI 2026)", None), err)
        self.assertEqual(moved["previous"],
                         {"pdf_title": "T-CACE (arXiv v1)", "pdf": f"{old}.pdf", "package": str(old), "code": "ok"})

    def test_a_new_note(self):
        self.library()
        code, out, err = self.run_it()
        self.assertEqual((code, out["code"], out["created"], out["old_notes"]), (0, "ok", True, []), err)
        self.assertEqual((out["better_pdf"], out["previous"]), (None, None))
        self.assertEqual(Path(out["note"]).read_text(encoding="utf-8"), SKELETON)
        self.assertEqual(Path(out["taken"]).read_text(encoding="utf-8"), SKELETON)
        self.assertEqual(self.structured_takes(), [["--cite", CITE, "-o", str(self.out)]])
        self.out = self.dir / "bare"
        code, out, err = self.run_it("--bare")
        self.assertEqual((code, Path(out["note"]).read_text(encoding="utf-8")), (0, BARE), err)

    def test_where_it_stops(self):
        self.library(notes=[{"key": "NOTE0001", "title": "论文笔记", "text": MINE},
                            {"key": "NOTE0003", "title": "论文笔记", "text": "另一条。"}])
        code, out, _ = self.run_it()
        self.assertEqual((code, out), (1, {"code": "two_notes", "keys": ["NOTE0001", "NOTE0003"]}))
        # the note names a PDF the library no longer has under that title
        self.library(notes=[{"key": "NOTE0001", "title": "论文笔记", "text": MINE.replace("arXiv v1", "arXiv v2")}])
        self.out = self.dir / "retitled"
        code, out, _ = self.run_it()
        self.assertEqual((code, out["code"], out["version"]), (1, "failed", "T-CACE (arXiv v2)"))
        self.assertEqual([(l["code"], l["titles"]) for l in out["detail"]],
                         [("no_such_title", ["T-CACE (JBHI 2026)", "T-CACE (arXiv v1)"])])
        code, out, err = self.run_it("--title", "T-CACE (arXiv v1)")  # the agent names the PDF to read
        self.assertEqual((code, out["code"], out["pdf_title"], out["created"]), (0, "ok", "T-CACE (arXiv v1)", False), err)
        self.assertEqual(out["previous"], {"pdf_title": "T-CACE (arXiv v2)", "pdf": None, "package": None,
                                           "code": "no_such_title"})
        # no package yet: the note is ready all the same, for a rerun after the parse or for the PDF alone
        self.library(packages=())
        self.out = self.dir / "unparsed"
        code, out, _ = self.run_it()
        stem = self.out / f"{CITE}.T-CACE (JBHI 2026)"
        self.assertEqual((code, out["code"], out["pdf_title"], out["pdf"], out["package"], out["note"]),
                         (1, "no_package", "T-CACE (JBHI 2026)", f"{stem}.pdf", None, f"{stem}.note.md"))
        self.assertEqual(Path(out["note"]).read_text(encoding="utf-8"), SKELETON)


if __name__ == "__main__":
    unittest.main()
