# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_pdf.py: the v1 single mode, the record stream, and the evidence from tiny generated PDFs."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_pdf.py"
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
COVER = ("Downloaded from the institutional repository on 2024-01-01\n"
         "This is a post-print of an Accepted manuscript.\nCitation: Liu et al. (2022)")
PAPER_PAGE = (f"{TITLE}\nWei Liu, Jing Zhang, and Ming Chen\nAbstract\nWe study cardiac image segmentation.\n"
              "DOI: 10.1109/JBHI.2022.3142076")


def pdf_string(line):
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages, count=None):
    """A minimal PDF, one uncompressed content stream per page, with a proper page tree and /Count."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {count if count is not None else len(pages)} >>".encode())
    for i, page in enumerate(pages):
        content_num = 4 + 2 * i
        shown = "".join(f"({pdf_string(line)}) Tj T* " for line in page.split("\n"))
        content = f"BT /F1 12 Tf 14 TL 72 720 Td {shown}ET".encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_num} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for num, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def run(*argv, stdin=None, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True, text=True, cwd=cwd)


def lines(stream):
    return [json.loads(line) for line in stream.splitlines() if line.startswith("{")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check_pdf_test_"))

    def item(self, **extra):
        return {"itemType": "journalArticle", "title": TITLE, "DOI": "10.1109/JBHI.2022.3142076",
                "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}], **extra}

    def record(self, slug, pdf_bytes, file_name=None, item=None, **extra):
        """Write <slug>.pdf and <slug>.json into the temp dir; return the record path."""
        if pdf_bytes is not None:
            (self.tmp / (file_name or f"{slug}.pdf")).write_bytes(pdf_bytes)
        rec = {"slug": slug, "item": self.item() if item is None else item, **extra}
        if pdf_bytes is not None or file_name:
            rec["file"] = file_name or f"{slug}.pdf"
        path = self.tmp / f"{slug}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path


class SingleMode(Base):
    def test_ok_with_evidence(self):
        pdf = self.tmp / "p.pdf"
        pdf.write_bytes(make_pdf([PAPER_PAGE, "Second page text"]))
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        r = run("--item", str(item), "--pdf", str(pdf))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "ok")
        for field in ("pdf", "size_bytes", "pdf_version", "text_chars", "first_page", "title", "supplementary", "excerpt"):
            self.assertIn(field, out)
        self.assertEqual(out["first_page"], "page_tree")
        ev = out["evidence"]
        self.assertEqual((ev["title_page"], ev["page_count"], ev["pages_scanned"]), (1, 2, 2))
        self.assertTrue(ev["doi_found"])
        self.assertTrue(ev["first_author_found"])
        self.assertFalse(ev["cover_page_suspected"])

    def test_title_not_found_keeps_v1_fields(self):
        pdf = self.tmp / "p.pdf"
        pdf.write_bytes(make_pdf(["Something else entirely, an unrelated paper"]))
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        r = run("--item", str(item), "--pdf", str(pdf))
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "title_not_found")
        self.assertIn("hint", out)
        self.assertIsNone(out["evidence"]["title_page"])

    def test_not_pdf_and_missing(self):
        bad = self.tmp / "bad.pdf"
        bad.write_bytes(b"<html><body>no</body></html>")
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        r = run("--item", str(item), "--pdf", str(bad))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "not_pdf"))
        r = run("--item", str(item), "--pdf", str(self.tmp / "none.pdf"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "file_not_found"))

    def test_single_mode_argument_errors(self):
        self.assertEqual(run("--item", "x.json").returncode, 2)
        self.assertEqual(run("--item", "x.json", "--pdf", "y.pdf", "rec.json").returncode, 2)


class StreamMode(Base):
    def test_title_on_page_one(self):
        path = self.record("a", make_pdf([PAPER_PAGE, "page two"]))
        r = run(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = lines(r.stdout)[0]
        self.assertEqual(rec["pdf"]["code"], "ok")
        self.assertEqual(rec["pdf"]["evidence"]["title_page"], 1)
        self.assertTrue(rec["pdf"]["checked_at"].endswith("Z"))
        summary = lines(r.stderr)[-1]["summary"]
        self.assertEqual(summary, {"total": 1, "ok": 1, "skipped": 0, "failed": 0})
        self.assertEqual(lines(r.stderr)[0]["code"], "ok")
        self.assertNotIn("pdf", json.loads(path.read_text()))  # no -i: the file is untouched

    def test_cover_page_then_title(self):
        path = self.record("b", make_pdf([COVER, PAPER_PAGE, "page three"]))
        r = run(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        pdf = lines(r.stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "ok_on_page_2")
        ev = pdf["evidence"]
        self.assertEqual(ev["title_page"], 2)
        self.assertTrue(ev["cover_page_suspected"])
        self.assertFalse(ev["collection_suspected"])
        self.assertIn("Downloaded from", ev["excerpt"])
        self.assertIn(TITLE.split(":")[0], ev["excerpt_title_page"])
        self.assertTrue(ev["doi_found"])
        self.assertTrue(ev["first_author_found"])

    def test_title_on_page_three_is_a_collection(self):
        path = self.record("c", make_pdf(["Proceedings front matter", "Table of contents", PAPER_PAGE, "x"]))
        r = run(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        pdf = lines(r.stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "ok_on_page_3")
        self.assertTrue(pdf["evidence"]["collection_suspected"])
        self.assertFalse(pdf["evidence"]["cover_page_suspected"])  # no cover phrases on page 1

    def test_long_file_with_title_on_page_two(self):
        path = self.record("d", make_pdf([COVER, PAPER_PAGE], count=120))
        pdf = lines(run(str(path)).stdout)[0]["pdf"]
        self.assertEqual(pdf["evidence"]["page_count"], 120)
        self.assertTrue(pdf["evidence"]["collection_suspected"])

    def test_title_absent_writes_evidence_and_fails(self):
        path = self.record("e", make_pdf(["An unrelated paper by Smith", "more"]))
        r = run("-i", str(path))
        self.assertEqual(r.returncode, 1)
        out = lines(r.stdout)
        self.assertEqual(out[0]["code"], "title_not_found")
        self.assertIn("hint", out[0])
        self.assertEqual(out[-1]["summary"], {"total": 1, "ok": 0, "skipped": 0, "failed": 1})
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rec["pdf"]["code"], "title_not_found")  # the evidence is the point: it is written
        ev = rec["pdf"]["evidence"]
        self.assertIsNone(ev["title_page"])
        self.assertFalse(ev["doi_found"])
        self.assertFalse(ev["first_author_found"])
        self.assertIsNone(ev["excerpt_title_page"])

    def test_doi_and_author_null_when_item_lacks_them(self):
        item = {"itemType": "journalArticle", "title": TITLE}
        path = self.record("f", make_pdf([PAPER_PAGE]), item=item)
        ev = lines(run(str(path)).stdout)[0]["pdf"]["evidence"]
        self.assertIsNone(ev["doi_found"])
        self.assertIsNone(ev["first_author_found"])

    def test_no_file_not_a_pdf_and_missing_file(self):
        p1 = self.record("g", None)
        p2 = self.record("h", b"<html><body>a web page</body></html>", file_name="h.pdf")
        p3 = self.record("k", None, file_name="gone.pdf")
        r = run("-i", str(p1), str(p2), str(p3))
        self.assertEqual(r.returncode, 1)
        out = lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:3]], ["no_file", "not_a_pdf", "file_not_found"])
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 0, "skipped": 0, "failed": 3})
        self.assertNotIn("pdf", json.loads(p1.read_text()))  # nothing to record
        rec2 = json.loads(p2.read_text())
        self.assertEqual(rec2["pdf"]["code"], "not_a_pdf")
        self.assertEqual(rec2["pdf"]["evidence"]["pages_scanned"], 0)
        self.assertNotIn("pdf", json.loads(p3.read_text()))

    def test_no_text_layer(self):
        # A page whose content stream uses an unsupported filter: nothing decodable.
        pdf = make_pdf([PAPER_PAGE]).replace(b"<< /Length", b"<< /Filter /LZWDecode /Length")
        path = self.record("m", pdf)
        r = run(str(path))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(lines(r.stdout)[0]["pdf"]["code"], "no_text_layer")

    def test_in_place_preserves_unknown_fields_and_formats(self):
        path = self.record("n", make_pdf([PAPER_PAGE]), custom={"nested": [1, 2]}, note="保留")
        r = run("-i", str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        raw = path.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("}\n"))
        self.assertIn('\n  "custom": {', raw)  # indent=2
        self.assertIn("保留", raw)              # ensure_ascii=False
        rec = json.loads(raw)
        self.assertEqual(rec["custom"], {"nested": [1, 2]})
        self.assertEqual(rec["pdf"]["code"], "ok")
        self.assertEqual(lines(r.stdout)[0]["slug"], "n")
        self.assertNotIn('"evidence"', r.stdout)  # -i: summary lines only, never the full records
        self.assertEqual(lines(r.stdout)[-1]["summary"]["ok"], 1)
        self.assertFalse(list(self.tmp.glob(".*.tmp")))  # temp file cleaned up

    def test_rerun_overwrites_pdf_section(self):
        path = self.record("o", make_pdf([PAPER_PAGE]), pdf={"code": "stale", "evidence": {}, "checked_at": "x"})
        run("-i", str(path))
        self.assertEqual(json.loads(path.read_text())["pdf"]["code"], "ok")

    def test_stdin_forms_and_pdf_fallback(self):
        pdf = self.tmp / "shared.pdf"
        pdf.write_bytes(make_pdf([PAPER_PAGE]))
        recs = [{"slug": "s1", "item": self.item()}, {"slug": "s2", "item": self.item(), "file": "shared.pdf"}]
        # JSONL, with --pdf as the fallback for s1 and the record's own file (relative to cwd) for s2
        jsonl = "\n".join(json.dumps(x) for x in recs) + "\n"
        r = run("--pdf", str(pdf), stdin=jsonl, cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x["pdf"]["code"] for x in lines(r.stdout)], ["ok", "ok"])
        # a JSON array
        r = run("--pdf", str(pdf), stdin=json.dumps(recs), cwd=str(self.tmp))
        self.assertEqual([x["slug"] for x in lines(r.stdout)], ["s1", "s2"])
        # a single pretty-printed object
        r = run("--pdf", str(pdf), stdin=json.dumps(recs[0], indent=2), cwd=str(self.tmp))
        self.assertEqual(len(lines(r.stdout)), 1)
        self.assertEqual(lines(r.stderr)[-1]["summary"]["total"], 1)

    def test_empty_stdin_and_in_place_with_stdin(self):
        r = run(stdin="")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "no_records"))
        r = run("-i", stdin="{}")
        self.assertEqual(r.returncode, 2)  # argument error
        r = run(stdin="not json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "input_invalid"))

    def test_slug_falls_back_to_file_stem(self):
        path = self.tmp / "fromstem.json"
        (self.tmp / "fromstem.pdf").write_bytes(make_pdf([PAPER_PAGE]))
        path.write_text(json.dumps({"item": self.item(), "file": "fromstem.pdf"}), encoding="utf-8")
        r = run("-i", str(path))
        self.assertEqual(lines(r.stdout)[0]["slug"], "fromstem")

    def test_short_title_cannot_judge(self):
        path = self.record("q", make_pdf(["Short"]), item={"itemType": "journalArticle", "title": "Short"})
        r = run(str(path))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(lines(r.stdout)[0]["pdf"]["code"], "cannot_judge")


if __name__ == "__main__":
    unittest.main(verbosity=1)
