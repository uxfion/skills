# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_pdf.py: the v1 single mode, the record stream, --match, HTML snapshots, and the evidence
from tiny generated PDFs. pdftotext / pdfinfo are stubbed by shell scripts on PATH; by default PATH has neither."""
import hashlib
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


def make_pdf(pages, count=None, encrypt=False):
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
    encrypt_entry = " /Encrypt << /Filter /Standard /V 1 >>" if encrypt else ""
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R{encrypt_entry} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


EMPTY_BIN = tempfile.mkdtemp(prefix="check_pdf_nobin_")  # a PATH without pdftotext: the builtin extractor


def run(*argv, stdin=None, cwd=None, path=EMPTY_BIN):
    env = {**os.environ, "PATH": path}
    return subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True, text=True, cwd=cwd,
                          env=env)


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


PDFTOTEXT_STUB = """#!/bin/sh
# check_pdf calls: pdftotext -f 1 -l 3 -enc UTF-8 FILE -  -> print FILE.txt (missing: fail like a broken file)
printf '%s\\n' "$*" > "$7.args"
exec /bin/cat "$7.txt"
"""
PDFINFO_STUB = """#!/bin/sh
[ -f "$1.pages" ] || exit 1
printf 'Producer:       stub\\nPages:          '
exec /bin/cat "$1.pages"
"""


class Pdftotext(Base):
    """pdftotext and pdfinfo as stubs that print sidecar files: deterministic, whatever poppler is installed."""

    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("pdftotext", PDFTOTEXT_STUB), ("pdfinfo", PDFINFO_STUB)):
            (self.bin / name).write_text(body, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        self.textonly = self.tmp / "bin2"  # pdftotext without pdfinfo
        self.textonly.mkdir()
        (self.textonly / "pdftotext").write_text(PDFTOTEXT_STUB, encoding="utf-8")
        (self.textonly / "pdftotext").chmod(0o755)

    def sidecar(self, pdf_name, pages, page_count=None):
        (self.tmp / f"{pdf_name}.txt").write_text("\f".join(pages) + "\f", encoding="utf-8")
        if page_count is not None:
            (self.tmp / f"{pdf_name}.pages").write_text(f"{page_count}\n", encoding="utf-8")

    def test_pages_split_at_form_feeds_and_count_from_pdfinfo(self):
        path = self.record("p", make_pdf(["builtin text that lacks the title"]))
        self.sidecar("p.pdf", ["Repository cover sheet", PAPER_PAGE, "page three"], page_count=12)
        r = run(str(path), path=str(self.bin))
        self.assertEqual(r.returncode, 0, r.stderr)
        pdf = lines(r.stdout)[0]["pdf"]
        ev = pdf["evidence"]
        self.assertEqual(pdf["code"], "ok_on_page_2")
        self.assertEqual((ev["extractor"], ev["pdftotext"], ev["page_source"]), ("pdftotext", "ok", "pdftotext"))
        self.assertEqual((ev["pages_scanned"], ev["page_count"], ev["title_page"]), (3, 12, 2))
        args = (self.tmp / "p.pdf.args").read_text(encoding="utf-8").split()
        self.assertEqual(args[:6], ["-f", "1", "-l", "3", "-enc", "UTF-8"])
        self.assertEqual(args[-1], "-")

    def test_count_from_page_tree_without_pdfinfo(self):
        path = self.record("q", make_pdf(["x"], count=9))
        self.sidecar("q.pdf", [PAPER_PAGE])
        ev = lines(run(str(path), path=str(self.textonly)).stdout)[0]["pdf"]["evidence"]
        self.assertEqual((ev["extractor"], ev["page_count"]), ("pdftotext", 9))

    def test_failure_and_empty_output_fall_back_to_builtin(self):
        path = self.record("r", make_pdf([PAPER_PAGE]))  # no sidecar: the stub exits non-zero
        pdf = lines(run(str(path), path=str(self.bin)).stdout)[0]["pdf"]
        self.assertEqual((pdf["code"], pdf["evidence"]["extractor"], pdf["evidence"]["pdftotext"]),
                         ("ok", "builtin", "failed"))
        self.sidecar("r.pdf", ["", ""])  # only form feeds: a scanned file
        pdf = lines(run(str(path), path=str(self.bin)).stdout)[0]["pdf"]
        self.assertEqual((pdf["code"], pdf["evidence"]["extractor"], pdf["evidence"]["pdftotext"]),
                         ("ok", "builtin", "empty"))

    def test_absent_is_builtin(self):
        path = self.record("s", make_pdf([PAPER_PAGE]))
        ev = lines(run(str(path)).stdout)[0]["pdf"]["evidence"]
        self.assertEqual((ev["extractor"], ev["pdftotext"], ev["page_source"]), ("builtin", "absent", "page_tree"))

    def test_small_caps_and_ligatures(self):
        # "S ELF -R EFINE" and the fi ligature: rule A compares letters and digits only, after NFKC.
        item = self.item(title="Self-Refine: Iterative Refinement with Self-Feedback")
        path = self.record("t", make_pdf(["x"]), item=item)
        self.sidecar("t.pdf", ["S ELF -R EFINE : Iterative Reﬁnement with Self-Feedback\nWei Liu"])
        self.assertEqual(lines(run(str(path), path=str(self.bin)).stdout)[0]["pdf"]["code"], "ok")

    def test_encrypted_file_that_pdftotext_reads(self):
        data = make_pdf([PAPER_PAGE], encrypt=True)
        path = self.record("u", data)
        self.sidecar("u.pdf", [PAPER_PAGE])
        pdf = lines(run(str(path), path=str(self.bin)).stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "ok")
        self.assertTrue(pdf["evidence"]["encrypted"])
        # without pdftotext: no text (stream mode), `encrypted` in single mode
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "no_text_layer")
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        r = run("--item", str(item), "--pdf", str(self.tmp / "u.pdf"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "encrypted"))
        r = run("--item", str(item), "--pdf", str(self.tmp / "u.pdf"), path=str(self.bin))
        out = json.loads(r.stdout)
        self.assertEqual((r.returncode, out["code"], out["first_page"]), (0, "ok", "pdftotext"))

    def test_words_with_ligature_and_line_end_hyphen(self):
        item = self.item(title="Efficient Fine Tuning of Large Language Models")
        path = self.record("v", make_pdf(["x"]), item=item)
        self.sidecar("v.pdf", ["Eﬃcient ﬁne-tuning for large lan-\nguage models\nWei Liu"])
        pdf = lines(run(str(path), path=str(self.bin)).stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "ok_by_words")
        self.assertEqual(pdf["evidence"]["title_words"]["share"], 1.0)


class PathB(Base):
    """ok_by_words: >= 80% of the title's words of 4+ letters in pages 1-3, plus the DOI or the first author."""

    GARBLED = PAPER_PAGE.replace("Deep Learning", "Deep Lerning")  # 5 of 6 words: 83%

    def test_words_with_doi(self):
        item = self.item(creators=[])
        path = self.record("a", make_pdf([self.GARBLED]), item=item)
        r = run(str(path))
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = lines(r.stdout)[0]
        self.assertEqual(rec["pdf"]["code"], "ok_by_words")
        ev = rec["pdf"]["evidence"]
        self.assertEqual(ev["title_words"], {"share": 0.83, "found": 5, "total": 6, "missing": ["learning"]})
        self.assertIsNone(ev["title_page"])
        self.assertEqual(ev["matched_title"], TITLE)
        self.assertEqual(lines(r.stderr)[0]["title_words"], 0.83)

    def test_words_with_first_author_only(self):
        page = self.GARBLED.replace("DOI: 10.1109/JBHI.2022.3142076", "")
        path = self.record("b", make_pdf([page]))
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "ok_by_words")

    def test_words_alone_are_not_enough(self):
        page = "Progressive Deep Lerning for Cardiac Image Segmentation\nby somebody else"
        path = self.record("c", make_pdf([page]))
        pdf = lines(run(str(path)).stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "title_not_found")
        self.assertEqual(pdf["evidence"]["title_words"]["share"], 0.83)
        self.assertFalse(pdf["evidence"]["doi_found"])
        self.assertFalse(pdf["evidence"]["first_author_found"])

    def test_below_threshold_fails_even_with_doi(self):
        page = PAPER_PAGE.replace("Progressive Deep Learning", "Progresive Deep Lerning")  # 4 of 6
        path = self.record("d", make_pdf([page]))
        pdf = lines(run(str(path)).stdout)[0]["pdf"]
        self.assertEqual((pdf["code"], pdf["evidence"]["title_words"]["share"]), ("title_not_found", 0.67))

    def test_words_on_later_pages_count(self):
        pages = ["Progressive Deep\nWei Liu", "Lerning for Cardiac Image", "Segmentation"]
        path = self.record("e", make_pdf(pages))
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "ok_by_words")

    def test_author_cited_later_is_no_corroboration(self):
        # another paper on the same topic: the title's words, and "Liu et al." in its introduction
        intro = "We build on prior work. " * 70
        pages = [f"Deep Learning for Progressive Cardiac Image Segmentation Revisited\nJ. Smith\n{intro}"
                 "as in Liu et al. (2022)", "more"]
        path = self.record("f", make_pdf(pages))
        pdf = lines(run(str(path)).stdout)[0]["pdf"]
        self.assertEqual(pdf["code"], "title_not_found")
        ev = pdf["evidence"]
        self.assertEqual((ev["title_words"]["share"], ev["first_author_found"], ev["first_author_in_byline"]),
                         (1.0, True, False))


class AltTitles(Base):
    PUBLISHED = "Conformal Prediction: A Gentle Introduction"
    PREPRINT = "A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification"

    def item_(self):
        return self.item(title=self.PUBLISHED, DOI="10.1561/2200000101")

    def page(self):
        return f"{self.PREPRINT}\nWei Liu and Jing Zhang\narXiv:2107.07511v6"

    def test_record_alt_titles(self):
        path = self.record("a", make_pdf([self.page()]), item=self.item_(), alt_titles=[self.PREPRINT],
                           file_version="preprint")
        ev = lines(run(str(path)).stdout)[0]["pdf"]["evidence"]
        self.assertEqual((ev["title_page"], ev["matched_title"]), (1, self.PREPRINT))

    def test_cli_alt_title_and_single_mode(self):
        path = self.record("b", make_pdf([self.page()]), item=self.item(title="Something Else Entirely Here"))
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "title_not_found")
        self.assertEqual(lines(run("--alt-title", self.PREPRINT, str(path)).stdout)[0]["pdf"]["code"], "ok")
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item(title="Something Else Entirely Here")), encoding="utf-8")
        r = run("--item", str(item), "--pdf", str(self.tmp / "b.pdf"), "--alt-title", self.PREPRINT)
        self.assertEqual(json.loads(r.stdout)["code"], "ok")

    def test_retitled_paper_passes_by_words(self):
        # all words of the published title occur in the preprint's, and the first author is there
        path = self.record("c", make_pdf([self.page()]), item=self.item_())
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "ok_by_words")


class BadFiles(Base):
    def code(self, pages, **extra):
        path = self.record("x", make_pdf(pages), **extra)
        r = run(str(path))
        return lines(r.stdout)[0]["pdf"], lines(r.stderr)[0], r.returncode

    def test_correction_notice_passes_a_but_fails(self):
        page = (f"Journal of Cardiac Imaging (2023) 12:34\nhttps://doi.org/10.1109/JBHI.2023.9999999\nCORRECTION\n"
                f"Correction to: {TITLE}\nWei Liu, Jing Zhang\nThe original article contained an error in Fig. 2.")
        pdf, line, rc = self.code([page])
        self.assertEqual((pdf["code"], rc), ("erratum_suspected", 1))
        self.assertEqual(pdf["evidence"]["title_page"], 1)
        self.assertEqual(pdf["evidence"]["erratum_marker"], "correction")
        self.assertEqual(line["erratum_marker"], "correction")
        self.assertIn("hint", line)

    def test_author_correction_and_erratum_forms(self):
        for head in (f"Author Correction: {TITLE}", f'Erratum to "{TITLE}"', f"Retraction Note: {TITLE}",
                     f"Corrigendum\n{TITLE}"):
            pdf, _, _ = self.code([head + "\nWei Liu\nDOI: 10.1109/JBHI.2022.3142076"])
            self.assertEqual(pdf["code"], "erratum_suspected", head)

    def test_erratum_without_the_title(self):
        pdf, _, _ = self.code(["ERRATUM\nIn the article by Liu et al., an author name was misspelled."])
        self.assertEqual(pdf["code"], "erratum_suspected")

    def test_title_with_correction_is_not_an_erratum(self):
        title = "Motion Correction for Cardiac Image Segmentation"
        page = f"Research Article\n{title}\nWei Liu\nDOI: 10.1109/JBHI.2022.3142076"
        pdf, _, _ = self.code([page], item=self.item(title=title))
        self.assertEqual(pdf["code"], "ok")
        pdf, _, _ = self.code([f"Correction\n{title}\nWei Liu"], item=self.item(title=title))
        self.assertEqual(pdf["code"], "ok")  # the record's own title has the word: not checked

    def test_mentions_are_not_headings(self):
        # an unrelated paper starting "Correction of ...", and "correction" later on the page
        pdf, _, _ = self.code(["Correction of motion artifacts in MRI\nby Smith\nWe apply a correction: see below"])
        self.assertEqual(pdf["code"], "title_not_found")
        pdf, _, _ = self.code([f"{TITLE}\nWei Liu\nCorrection: a typo was fixed on 2023-01-01"])
        self.assertEqual(pdf["code"], "ok")  # after the title: not the head

    def test_supplement(self):
        pdf, line, _ = self.code([f"Supplementary Information for\n{TITLE}\nWei Liu"])
        self.assertEqual((pdf["code"], pdf["evidence"]["supplement_marker"]), ("supplement_suspected",
                                                                                "supplementary information"))
        self.assertEqual(line["supplement_marker"], "supplementary information")
        pdf, _, _ = self.code(["SUPPLEMENTARY APPENDIX\nThis appendix has been provided by the authors.\n"
                               f"Supplement to: Liu W, et al. {TITLE}. N Engl J Med 2022"])
        self.assertEqual(pdf["code"], "supplement_suspected")
        pdf, _, _ = self.code([f"Supplementary Material\n{TITLE}"], file_version="supplement")
        self.assertEqual(pdf["code"], "ok")

    def test_margin_supplemental_content_is_no_supplement(self):
        page = (f"Original Investigation\nSupplemental content\nAuthor affiliations are listed at the end.\n{TITLE}\n"
                "Wei Liu\nSupplemental Material is available online.")
        pdf, _, _ = self.code([page])
        self.assertEqual(pdf["code"], "ok")
        self.assertIsNone(pdf["evidence"]["supplement_marker"])

    def test_doi_mismatch(self):
        page = f"{TITLE}\nWei Liu\nhttps://doi.org/10.1016/j.media.2021.102000."
        pdf, line, _ = self.code([page])
        self.assertEqual(pdf["code"], "doi_mismatch")
        self.assertEqual(pdf["evidence"]["dois_on_page_1"], ["10.1016/j.media.2021.102000"])
        self.assertTrue(pdf["evidence"]["doi_mismatch"])
        self.assertEqual(line["dois_on_page_1"], ["10.1016/j.media.2021.102000"])

    def test_doi_mismatch_only_for_published(self):
        page = f"{TITLE}\nWei Liu\ndoi: 10.1101/2023.01.01.23280000"
        for fv in ("accepted", "preprint"):
            pdf, _, _ = self.code([page], file_version=fv)
            self.assertEqual((pdf["code"], pdf["evidence"]["doi_mismatch"], pdf["evidence"]["file_version"]),
                             ("ok", None, fv))

    def test_doi_matches_despite_case_line_break_or_other_dois(self):
        pdf, _, _ = self.code([f"{TITLE}\nWei Liu\nDOI 10.1109/jbhi.\n2022.3142076\ncites 10.1000/xyz123"])
        self.assertEqual((pdf["code"], pdf["evidence"]["doi_mismatch"]), ("ok", False))
        # the item's DOI on page 2 only: another DOI on page 1 is not enough
        pdf, _, _ = self.code([f"{TITLE}\nWei Liu\nSee 10.1000/xyz123", "DOI: 10.1109/JBHI.2022.3142076"])
        self.assertEqual(pdf["code"], "ok")

    def test_no_doi_printed_or_none_in_item(self):
        pdf, _, _ = self.code([f"{TITLE}\nWei Liu"])
        self.assertEqual((pdf["code"], pdf["evidence"]["doi_mismatch"]), ("ok", False))
        pdf, _, _ = self.code([f"{TITLE}\nWei Liu\n10.1000/xyz123"], item=self.item(DOI=""))
        self.assertEqual((pdf["code"], pdf["evidence"]["doi_mismatch"]), ("ok", None))

    def test_single_mode_keeps_its_codes(self):
        pdf = self.tmp / "p.pdf"
        pdf.write_bytes(make_pdf([f"Correction to: {TITLE}\nWei Liu"]))
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        out = json.loads(run("--item", str(item), "--pdf", str(pdf)).stdout)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["evidence"]["erratum_marker"], "correction")


SNAPSHOT = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{title} | Journal of Cardiac Imaging</title>
<meta name="citation_title" content="{title}"><meta name="citation_doi" content="{doi}">
<script>var t = "{other}"; if (a < b) {{ x(); }}</script><style>h1 {{ color: red }}</style></head>
<body><nav>Home Journals Corrections</nav><h1>{title}</h1><p>Wei Liu, Jing Zhang</p>
<p>Abstract: We study cardiac image segmentation &amp; more.</p></body></html>"""


class Html(Base):
    def snapshot(self, name, body, item=None, **extra):
        (self.tmp / name).write_text(body, encoding="utf-8")
        path = self.tmp / f"{Path(name).stem}.json"
        path.write_text(json.dumps({"item": item or self.item(), "file": name, **extra}), encoding="utf-8")
        r = run(str(path))
        return lines(r.stdout)[0]["pdf"], r

    def test_article_page(self):
        pdf, r = self.snapshot("a.html", SNAPSHOT.format(title=TITLE, doi="10.1109/JBHI.2022.3142076", other="x"))
        self.assertEqual((pdf["code"], r.returncode), ("ok", 0))
        ev = pdf["evidence"]
        self.assertEqual((ev["extractor"], ev["page_source"], ev["title_page"]), ("html", "html", 1))
        self.assertEqual(ev["html_title"], f"{TITLE} | Journal of Cardiac Imaging")
        self.assertEqual(ev["dois_on_page_1"], ["10.1109/jbhi.2022.3142076"])
        self.assertIsNone(ev["erratum_marker"])  # "Corrections" in the menu is not the head
        self.assertNotIn("var t", ev["excerpt"])
        self.assertIn("segmentation & more", ev["excerpt"])

    def test_entities_are_unescaped(self):
        title = "Réseaux de neurones pour la segmentation cardiaque"
        body = "<html><head><title>R&eacute;seaux de neurones pour la segmentation cardiaque</title></head></html>"
        (self.tmp / "e.html").write_text(body, encoding="utf-8")
        path = self.tmp / "e.json"
        path.write_text(json.dumps({"item": self.item(title=title), "file": "e.html"}), encoding="utf-8")
        self.assertEqual(lines(run(str(path)).stdout)[0]["pdf"]["code"], "ok")

    def test_title_only_in_a_script_does_not_count(self):
        body = SNAPSHOT.format(title="Another Paper on Kidney Ultrasound", doi="10.1000/k1", other=TITLE)
        pdf, _ = self.snapshot("b.htm", body, item=self.item(DOI=""))
        self.assertEqual(pdf["code"], "title_not_found")

    def test_proxy_error_page(self):
        body = ("<html><head><title>Host Needed</title></head><body><h1>Host Needed</h1>"
                "<p>The host is not configured for this proxy.</p></body></html>")
        pdf, r = self.snapshot("c.html", body)
        self.assertEqual((pdf["code"], pdf["evidence"]["denial_marker"], r.returncode),
                         ("not_the_article", "host needed", 1))
        self.assertEqual(lines(r.stderr)[0]["denial_marker"], "host needed")

    def test_denial_page_that_has_the_title_passes(self):
        body = SNAPSHOT.format(title=TITLE, doi="10.1109/JBHI.2022.3142076", other="x").replace(
            "<p>Wei Liu", "<p>Access denied: purchase this article. Wei Liu")
        pdf, _ = self.snapshot("d.html", body)
        self.assertEqual(pdf["code"], "ok")

    def test_empty_page_and_erratum_title(self):
        pdf, _ = self.snapshot("f.html", "<html><head><script>app()</script></head><body></body></html>")
        self.assertEqual(pdf["code"], "not_the_article")
        pdf, _ = self.snapshot("g.html", SNAPSHOT.format(title=f"Correction to: {TITLE}", doi="10.1000/c1", other="x"))
        self.assertEqual(pdf["code"], "erratum_suspected")

    def test_meta_doi_mismatch(self):
        pdf, _ = self.snapshot("h.html", SNAPSHOT.format(title=TITLE, doi="10.1000/other.1", other="x"))
        self.assertEqual(pdf["code"], "doi_mismatch")

    def test_html_in_a_pdf_name_or_plain_text_is_not_a_pdf(self):
        pdf, _ = self.snapshot("i.pdf", SNAPSHOT.format(title=TITLE, doi="10.1109/JBHI.2022.3142076", other="x"))
        self.assertEqual(pdf["code"], "not_a_pdf")
        pdf, _ = self.snapshot("j.html", f"just text, {TITLE}")
        self.assertEqual(pdf["code"], "not_a_pdf")


class Match(Base):
    def setUp(self):
        super().setUp()
        self.a = self.record("liu2022", make_pdf([PAPER_PAGE]))
        other = self.item(title="Kidney Ultrasound Segmentation with Transformers", DOI="10.1000/k1",
                          creators=[{"creatorType": "author", "lastName": "Smith"}])
        self.b = self.record("smith2023", make_pdf(["Kidney Ultrasound Segmentation with Transformers\nJ. Smith"]),
                             item=other)

    def test_one_file_against_records(self):
        before = (self.a.read_text(), self.b.read_text())
        pdf = self.tmp / "liu2022.pdf"
        r = run("--match", str(pdf), str(self.a), str(self.b))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = lines(r.stdout)
        self.assertEqual([(o["slug"], o["code"]) for o in out[:2]], [("liu2022", "ok"), ("smith2023", "doi_mismatch")])
        self.assertEqual(out[2], {"matched": ["liu2022"], "file": str(pdf),
                                  "md5": hashlib.md5(pdf.read_bytes()).hexdigest()})
        self.assertEqual((self.a.read_text(), self.b.read_text()), before)  # never writes records

    def test_file_overrides_record_file_and_none_matched(self):
        stray = self.tmp / "download.pdf"
        stray.write_bytes(make_pdf(["A third paper about lungs"]))
        r = run("--match", str(stray), str(self.a), str(self.b))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(lines(r.stdout)[-1]["matched"], [])

    def test_stdin_records_and_two_matches(self):
        recs = [{"slug": "one", "item": self.item()}, {"slug": "two", "item": self.item()}]
        r = run("--match", str(self.tmp / "liu2022.pdf"), stdin=json.dumps(recs))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(lines(r.stdout)[-1]["matched"], ["one", "two"])

    def test_cannot_check(self):
        r = run("--match", str(self.tmp / "missing.pdf"), str(self.a))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "file_not_found"))
        bad = self.tmp / "bad.json"
        bad.write_text("[1, 2", encoding="utf-8")
        r = run("--match", str(self.tmp / "liu2022.pdf"), str(bad))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "record_invalid"))
        r = run("--match", str(self.tmp / "liu2022.pdf"), stdin="")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_records"))

    def test_argument_errors(self):
        pdf = str(self.tmp / "liu2022.pdf")
        self.assertEqual(run("--match", pdf, "-i", str(self.a)).returncode, 2)
        self.assertEqual(run("--match", pdf, "--pdf", pdf, str(self.a)).returncode, 2)
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        self.assertEqual(run("--match", pdf, "--item", str(item), "--pdf", pdf).returncode, 2)

    def test_file_version_override(self):
        page = f"{TITLE}\nWei Liu\ndoi: 10.1101/2023.01.01.23280000"
        f = self.tmp / "medrxiv.pdf"
        f.write_bytes(make_pdf([page]))
        self.assertEqual(lines(run("--match", str(f), str(self.a)).stdout)[0]["code"], "doi_mismatch")
        r = run("--match", str(f), "--file-version", "preprint", str(self.a))
        self.assertEqual((r.returncode, lines(r.stdout)[-1]["matched"]), (0, ["liu2022"]))


class Defaults(Base):
    """file: `file` > --pdf > <stem>.pdf > <stem>.html; file_version: record > fetch.jsonl > published; md5."""

    def bare(self, stem, folder=None, **extra):
        folder = folder or self.tmp
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stem}.json"
        path.write_text(json.dumps({"slug": stem, "item": self.item(), **extra}), encoding="utf-8")
        return path

    def test_md5_of_the_checked_file(self):
        data = make_pdf([PAPER_PAGE])
        path = self.record("m", data)
        run("-i", str(path))
        self.assertEqual(json.loads(path.read_text())["pdf"]["md5"], hashlib.md5(data).hexdigest())

    def test_stem_pdf_then_stem_html(self):
        path = self.bare("k")
        (self.tmp / "k.html").write_text(SNAPSHOT.format(title=TITLE, doi="10.1109/JBHI.2022.3142076", other="x"),
                                         encoding="utf-8")
        r = run(str(path))
        self.assertEqual(lines(r.stderr)[0]["file"], str(self.tmp / "k.html"))
        self.assertEqual(lines(r.stdout)[0]["pdf"]["evidence"]["extractor"], "html")
        (self.tmp / "k.pdf").write_bytes(make_pdf([PAPER_PAGE]))
        r = run(str(path))
        self.assertEqual(lines(r.stderr)[0]["file"], str(self.tmp / "k.pdf"))

    def test_explicit_file_and_pdf_flag_win(self):
        path = self.bare("w", file="sub/paper.pdf")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "paper.pdf").write_bytes(make_pdf([PAPER_PAGE]))
        (self.tmp / "w.pdf").write_bytes(make_pdf(["the sibling"]))
        self.assertEqual(lines(run(str(path)).stderr)[0]["file"], str(self.tmp / "sub" / "paper.pdf"))
        path = self.bare("w2")
        (self.tmp / "w2.pdf").write_bytes(make_pdf(["the sibling"]))
        flag = self.tmp / "flag.pdf"
        flag.write_bytes(make_pdf([PAPER_PAGE]))
        self.assertEqual(lines(run("--pdf", str(flag), str(path)).stderr)[0]["file"], str(flag))

    def test_file_version_from_fetch_log(self):
        work = self.tmp / "work"
        records = work / "records"
        path = self.bare("fv", folder=records)
        (records / "fv.pdf").write_bytes(make_pdf([f"{TITLE}\nWei Liu\ndoi: 10.1101/2023.01.01.23280000"]))
        ev = lambda *a: lines(run(*a, str(path)).stdout)[0]["pdf"]  # noqa: E731
        self.assertEqual((ev()["code"], ev()["evidence"]["file_version"]), ("doi_mismatch", "published"))
        log_lines = [{"slug": "fv", "code": "ok", "version": "accepted"},
                     {"slug": "fv", "code": "no_pdf_link", "version": "published"},
                     {"slug": "other", "code": "ok", "version": "published"}]
        (work / "fetch.jsonl").write_text("\n".join(json.dumps(x) for x in log_lines) + "\n{torn line\n",
                                          encoding="utf-8")
        self.assertEqual((ev()["code"], ev()["evidence"]["file_version"]), ("ok", "accepted"))
        with open(work / "fetch.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"slug": "fv", "code": "ok", "version": "submitted"}) + "\n")
        self.assertEqual(ev()["evidence"]["file_version"], "submitted")  # the last ok line
        self.assertEqual(ev("--file-version", "published")["code"], "doi_mismatch")
        rec = json.loads(path.read_text())
        rec["file_version"] = "supplement"
        path.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(ev()["evidence"]["file_version"], "supplement")  # the record's own wins over the log


if __name__ == "__main__":
    unittest.main(verbosity=1)
