# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_pdf.py: the record stream, --match, single mode, HTML snapshots and the evidence.

pdftotext / pdfinfo are shell stubs on PATH that print sidecar files (<file>.txt with form feeds between pages,
<file>.pages with the page count), so the verdicts do not depend on the poppler installed here. One test runs the
real pdftotext on a generated PDF when it is installed."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_pdf.py"
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
DOI = "10.1109/JBHI.2022.3142076"
PAPER_PAGE = (f"{TITLE}\nWei Liu, Jing Zhang, and Ming Chen\nAbstract\nWe study cardiac image segmentation.\n"
              f"DOI: {DOI}")
COVER = ("Downloaded from the institutional repository on 2024-01-01\n"
         "This is a post-print of an Accepted manuscript.\nCitation: Liu et al. (2022)")

# check_pdf calls: pdftotext -f 1 -l 3 -enc UTF-8 FILE -   (FILE is $7)
PDFTOTEXT_STUB = """#!/bin/sh
[ -f "$7.txt" ] || exit 1
exec /bin/cat "$7.txt"
"""
PDFINFO_STUB = """#!/bin/sh
[ -f "$1.pages" ] || exit 1
printf 'Producer:       stub\\nPages:          '
exec /bin/cat "$1.pages"
"""


def lines(stream):
    return [json.loads(line) for line in stream.splitlines() if line.startswith("{")]


def pdf_string(line):
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages):
    """A minimal real PDF, one uncompressed content stream per page (for the real-pdftotext test)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, page in enumerate(pages):
        shown = "".join(f"({pdf_string(line)}) Tj T* " for line in page.split("\n"))
        content = f"BT /F1 12 Tf 14 TL 72 720 Td {shown}ET".encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
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


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="check_pdf_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name, body in (("pdftotext", PDFTOTEXT_STUB), ("pdfinfo", PDFINFO_STUB)):
            (self.bin / name).write_text(body, encoding="utf-8")
            (self.bin / name).chmod(0o755)

    def run_script(self, *argv, stdin=None, path=None, cwd=None):
        env = {**os.environ, "PATH": str(self.bin) if path is None else path}
        return subprocess.run([sys.executable, str(SCRIPT), *argv], input=stdin, capture_output=True, text=True,
                              env=env, cwd=cwd)

    def item(self, **extra):
        return {"itemType": "journalArticle", "title": TITLE, "DOI": DOI,
                "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}], **extra}

    def pdf(self, name, pages, page_count=None, data=None):
        """A file that starts like a PDF, with the text the pdftotext stub will print for it."""
        f = self.tmp / name
        f.write_bytes(data if data is not None else b"%PDF-1.5\n% " + name.encode() + b"\n")
        if pages is not None:
            (self.tmp / f"{name}.txt").write_text("\f".join(pages) + "\f", encoding="utf-8")
        (self.tmp / f"{name}.pages").write_text(f"{page_count or len(pages or [1])}\n", encoding="utf-8")
        return f

    def record(self, slug, pages=None, file_name=None, item=None, page_count=None, **extra):
        """<slug>.json, plus the file beside it (<slug>.pdf unless file_name says otherwise) when pages are given."""
        if pages is not None:
            self.pdf(file_name or f"{slug}.pdf", pages, page_count)
        rec = {"slug": slug, "item": self.item() if item is None else item, **extra}
        if file_name:
            rec.setdefault("file", file_name)
        path = self.tmp / f"{slug}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def check(self, *pages, item=None, file_name=None, page_count=None, **extra):
        """Stream-check one record with -i -> (exit code, summary line, record's pdf object)."""
        path = self.record("r", list(pages), file_name=file_name, item=item, page_count=page_count, **extra)
        r = self.run_script("-i", str(path))
        out = lines(r.stdout)
        return r.returncode, out[0], json.loads(path.read_text(encoding="utf-8")).get("pdf")


class Stream(Base):
    def test_title_on_page_one_with_evidence(self):
        rc, line, pdf = self.check(PAPER_PAGE, "Introduction ...", page_count=9)
        self.assertEqual((rc, line["code"], pdf["code"]), (0, "ok", "ok"))
        ev = pdf["evidence"]
        self.assertEqual((ev["extractor"], ev["page_count"], ev["pages_scanned"], ev["title_page"]),
                         ("pdftotext", 9, 2, 1))
        self.assertEqual((ev["doi_found"], ev["first_author_found"], ev["first_author_in_byline"]), (True, True, True))
        self.assertEqual((ev["file_version"], ev["arxiv_stamp"]), ("published", None))
        self.assertEqual(pdf["md5"], hashlib.md5((self.tmp / "r.pdf").read_bytes()).hexdigest())
        self.assertIn("checked_at", pdf)

    def test_cover_sheet_then_title(self):
        rc, line, pdf = self.check(COVER, PAPER_PAGE)
        self.assertEqual((rc, line["code"]), (0, "ok_on_page_2"))
        self.assertTrue(pdf["evidence"]["cover_page_suspected"])
        self.assertIsNotNone(pdf["evidence"]["excerpt_title_page"])

    def test_title_on_page_three_is_a_collection(self):
        _, line, pdf = self.check("Proceedings front matter", "Table of contents", PAPER_PAGE)
        self.assertEqual(line["code"], "ok_on_page_3")
        self.assertTrue(pdf["evidence"]["collection_suspected"])

    def test_long_file_with_title_on_page_two(self):
        _, line, pdf = self.check("Program of the workshop", PAPER_PAGE, page_count=120)
        self.assertEqual(line["code"], "ok_on_page_2")
        self.assertTrue(pdf["evidence"]["collection_suspected"])

    def test_title_absent_fails_with_evidence(self):
        rc, line, pdf = self.check("A different paper about lungs\nSomeone Else\nAbstract ...")
        self.assertEqual((rc, line["code"], pdf["code"]), (1, "title_not_found", "title_not_found"))
        self.assertIn("hint", line)
        self.assertEqual(pdf["evidence"]["doi_found"], False)

    def test_doi_and_author_null_when_item_lacks_them(self):
        _, _, pdf = self.check(PAPER_PAGE, item={"itemType": "journalArticle", "title": TITLE})
        self.assertIsNone(pdf["evidence"]["doi_found"])
        self.assertIsNone(pdf["evidence"]["first_author_found"])

    def test_no_file_not_a_pdf_and_missing_file(self):
        p = self.record("nofile")
        r = self.run_script("-i", str(p))
        self.assertEqual((r.returncode, lines(r.stdout)[0]["code"]), (1, "no_file"))
        (self.tmp / "html.pdf").write_text("<html><title>Login</title></html>", encoding="utf-8")
        p = self.record("h", file="html.pdf")
        self.assertEqual(lines(self.run_script("-i", str(p)).stdout)[0]["code"], "not_a_pdf")
        p = self.record("gone", file="missing.pdf")
        self.assertEqual(lines(self.run_script("-i", str(p)).stdout)[0]["code"], "file_not_found")

    def test_no_text_layer(self):
        self.pdf("scan.pdf", None)  # no sidecar: the stub fails like pdftotext on a broken file
        p = self.record("scan", file="scan.pdf")
        r = self.run_script("-i", str(p))
        self.assertEqual((r.returncode, lines(r.stdout)[0]["code"]), (1, "no_text_layer"))
        rc, line, _ = self.check("   ")
        self.assertEqual(line["code"], "no_text_layer")

    def test_in_place_keeps_unknown_fields_and_rerun_overwrites(self):
        path = self.record("k", [PAPER_PAGE], extra_field={"keep": [1, 2]})
        self.run_script("-i", str(path))
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rec["extra_field"], {"keep": [1, 2]})
        first = rec["pdf"]["checked_at"]
        (self.tmp / "k.pdf.txt").write_text("nothing here\f", encoding="utf-8")
        self.run_script("-i", str(path))
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rec["pdf"]["code"], "title_not_found")
        self.assertGreaterEqual(rec["pdf"]["checked_at"], first)

    def test_stdin_forms_and_pdf_fallback(self):
        self.pdf("given.pdf", [PAPER_PAGE])
        rec = {"slug": "s", "item": self.item()}
        for raw in (json.dumps(rec), json.dumps([rec, rec]), json.dumps(rec) + "\n" + json.dumps(rec)):
            r = self.run_script("--pdf", str(self.tmp / "given.pdf"), stdin=raw)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(all(json.loads(x)["pdf"]["code"] == "ok" for x in r.stdout.splitlines()))
        r = self.run_script(stdin="")
        self.assertEqual(json.loads(r.stdout)["code"], "no_records")

    def test_slug_falls_back_to_file_stem(self):
        path = self.tmp / "stem.json"
        path.write_text(json.dumps({"item": self.item()}), encoding="utf-8")
        self.pdf("stem.pdf", [PAPER_PAGE])
        r = self.run_script("-i", str(path))
        self.assertEqual(lines(r.stdout)[0]["slug"], "stem")

    def test_short_title_cannot_judge(self):
        _, line, _ = self.check("GAN\nIan Goodfellow", item={"itemType": "journalArticle", "title": "GAN"})
        self.assertEqual(line["code"], "cannot_judge")


class PathB(Base):
    def test_words_with_ligature_and_line_end_hyphen_and_byline_author(self):
        page = ("Progressive Deep Learn-\ning, revisited, for Cardiac Im-\nage Segmen-\ntation\nWei Liu, Jing Zhang\n"
                "Abstract ...")
        _, line, pdf = self.check(page, item=self.item(DOI=None))
        self.assertEqual(line["code"], "ok_by_words")
        self.assertEqual(pdf["evidence"]["title_words"]["share"], 1.0)
        self.assertTrue(pdf["evidence"]["first_author_in_byline"])

    def test_words_with_doi(self):
        page = f"PROGRESSIVE DEEP-LEARNING (PDL) FOR\nCARDIAC IMAGE\nSEGMENTATION?\nM. Chen\n{DOI}"
        _, line, _ = self.check(page, item=self.item(creators=[]))
        self.assertEqual(line["code"], "ok_by_words")

    def test_words_alone_are_not_enough(self):
        page = "Progressive deep learning for cardiac image segmentation: a survey of others\nSomeone Else"
        page = page.replace("for cardiac", "for the cardiac")  # breaks rule A, keeps every word
        _, line, _ = self.check(page, item=self.item(DOI=None))
        self.assertEqual(line["code"], "title_not_found")

    def test_below_threshold_fails_even_with_doi(self):
        _, line, pdf = self.check(f"Cardiac Imaging\nWei Liu\n{DOI}")
        self.assertEqual(line["code"], "title_not_found")
        self.assertLess(pdf["evidence"]["title_words"]["share"], 0.8)

    def test_words_on_later_pages_count(self):
        _, line, _ = self.check("Wei Liu, Jing Zhang", "Progressive deep learning, again, for cardiac image segmentation",
                                item=self.item(DOI=None))
        self.assertEqual(line["code"], "ok_by_words")

    def test_author_cited_later_is_no_corroboration(self):
        filler = "Background text. " * 120  # pushes the citation past the byline window
        page = (f"Progressive deep learning, again, for cardiac image segmentation\nSomeone Else\n{filler}"
                "as shown by Liu et al. [3]")
        _, line, pdf = self.check(page, item=self.item(DOI=None))
        self.assertEqual(line["code"], "title_not_found")
        self.assertEqual((pdf["evidence"]["first_author_found"], pdf["evidence"]["first_author_in_byline"]),
                         (True, False))

    def test_alt_titles_from_record_and_cli(self):
        page = "A Gentle Introduction to Conformal Prediction\nA. Angelopoulos"
        item = self.item(title="Conformal Prediction: A Gentle Introduction", DOI=None, creators=[])
        _, line, pdf = self.check(page, item=item, alt_titles=["A Gentle Introduction to Conformal Prediction"])
        self.assertEqual(line["code"], "ok")
        self.assertEqual(pdf["evidence"]["matched_title"], "A Gentle Introduction to Conformal Prediction")
        path = self.record("cli", [page], item=item)
        r = self.run_script("-i", str(path), "--alt-title", "A Gentle Introduction to Conformal Prediction")
        self.assertEqual(lines(r.stdout)[0]["code"], "ok")


class HeadMarkers(Base):
    def test_correction_notice_passes_a_but_fails(self):
        rc, line, pdf = self.check(f"Correction to: {TITLE}\nThe author name was misspelled.\n{DOI}")
        self.assertEqual((rc, line["code"]), (1, "erratum_suspected"))
        self.assertEqual(pdf["evidence"]["erratum_marker"], "correction")

    def test_author_correction_and_erratum_forms(self):
        for head in ("Author Correction:", "Erratum", "RETRACTION NOTICE", "Publisher's Correction - "):
            _, line, _ = self.check(f"{head}\n{TITLE}\nWei Liu")
            self.assertEqual(line["code"], "erratum_suspected", head)

    def test_title_with_correction_is_not_an_erratum(self):
        title = "Self-Correction with Large Language Models"
        _, line, _ = self.check(f"Correction\n{title}\nWei Liu", item=self.item(title=title, DOI=None))
        self.assertEqual(line["code"], "ok")

    def test_mentions_are_not_headings(self):
        for head in ("Correction-based learning is popular", "Corrections of motion artefacts in MRI"):
            _, line, _ = self.check(f"{head}\n{PAPER_PAGE}")
            self.assertEqual(line["code"], "ok", head)

    def test_supplement_and_its_file_name(self):
        page = f"Supplementary Material\n{TITLE}\nWei Liu"
        _, line, _ = self.check(page)
        self.assertEqual(line["code"], "supplement_suspected")
        _, line, pdf = self.check(page, file_name="r.supplement.pdf")
        self.assertEqual((line["code"], pdf["evidence"]["file_version"]), ("ok", "supplement"))

    def test_margin_supplemental_content_is_no_supplement(self):
        _, line, _ = self.check(f"Supplemental content\n{PAPER_PAGE}")
        self.assertEqual(line["code"], "ok")


class DoiMismatch(Base):
    def test_other_doi_printed(self):
        _, line, pdf = self.check(f"{TITLE}\nWei Liu\nDOI: 10.1016/j.media.2020.101234")
        self.assertEqual(line["code"], "doi_mismatch")
        self.assertEqual(pdf["evidence"]["dois_on_page_1"], ["10.1016/j.media.2020.101234"])

    def test_only_for_published_files(self):
        page = f"{TITLE}\nWei Liu\nDOI: 10.48550/arXiv.2201.00001"
        _, line, pdf = self.check(page, file_name="r.accepted.pdf")
        self.assertEqual((line["code"], pdf["evidence"]["file_version"], pdf["evidence"]["doi_mismatch"]),
                         ("ok", "accepted", None))
        _, line, _ = self.check(page, file_name="r.preprint.pdf")
        self.assertEqual(line["code"], "ok")

    def test_matches_despite_case_line_break_or_other_dois(self):
        page = f"{TITLE}\nWei Liu\ndoi: 10.1109/jbhi.2022.\n3142076\nSee also 10.1000/xyz123"
        _, line, _ = self.check(page)
        self.assertEqual(line["code"], "ok")

    def test_no_doi_printed_or_none_in_item(self):
        _, line, _ = self.check(f"{TITLE}\nWei Liu")
        self.assertEqual(line["code"], "ok")
        _, line, _ = self.check(f"{TITLE}\n10.1000/other", item=self.item(DOI=None))
        self.assertEqual(line["code"], "ok")


class Versions(Base):
    def test_arxiv_stamp_makes_a_published_name_a_preprint(self):
        page = f"arXiv:2201.00001v2 [cs.CV] 3 Jan 2022\n{TITLE}\nWei Liu\nDOI: 10.48550/arXiv.2201.00001"
        _, line, pdf = self.check(page)
        self.assertEqual((line["code"], line["file_version"]), ("ok", "preprint"))
        self.assertEqual(pdf["evidence"]["arxiv_stamp"], "arXiv:2201.00001v2 [cs.CV]")
        path = self.record("o", [page])
        r = self.run_script("-i", str(path), "--file-version", "published")
        self.assertEqual(lines(r.stdout)[0]["code"], "doi_mismatch", "--file-version overrides the stamp")

    def test_stem_files_in_order_and_explicit_file_wins(self):
        self.pdf("a.preprint.pdf", ["nothing"])
        self.pdf("a.pdf", [PAPER_PAGE])
        path = self.record("a")
        r = self.run_script("-i", str(path))
        self.assertTrue(lines(r.stdout)[0]["file"].endswith("a.pdf"))
        path = self.record("a", file="a.preprint.pdf")
        r = self.run_script("-i", str(path))
        self.assertEqual(lines(r.stdout)[0]["code"], "title_not_found")
        path = self.record("b")
        self.pdf("b.accepted.pdf", [PAPER_PAGE])
        r = self.run_script("-i", str(path))
        self.assertEqual((lines(r.stdout)[0]["code"], lines(r.stdout)[0]["file_version"]), ("ok", "accepted"))


class Html(Base):
    def snapshot(self, html, name="r.html", item=None):
        (self.tmp / name).write_text(html, encoding="utf-8")
        path = self.record("r", item=item, file=name)
        r = self.run_script("-i", str(path))
        return lines(r.stdout)[0], json.loads(path.read_text(encoding="utf-8"))["pdf"]

    def test_article_page(self):
        line, pdf = self.snapshot(f"<html><head><title>{TITLE} | IEEE</title>"
                                  f"<meta name='citation_doi' content='{DOI}'></head>"
                                  "<body><h1>Abstract</h1><p>We study segmentation.</p></body></html>")
        self.assertEqual((line["code"], line["file_version"]), ("ok", "snapshot"))
        self.assertEqual(pdf["evidence"]["extractor"], "html")

    def test_entities_are_unescaped(self):
        title = "Segmentation & Registration: A Survey"
        line, _ = self.snapshot("<html><title>Segmentation &amp; Registration: A Survey</title></html>",
                                item=self.item(title=title, DOI=None))
        self.assertEqual(line["code"], "ok")

    def test_title_only_in_a_script_does_not_count(self):
        line, _ = self.snapshot(f"<html><title>Sign in</title><script>var t='{TITLE}'</script>"
                                "<body>Please sign in</body></html>")
        self.assertEqual(line["code"], "title_not_found")

    def test_proxy_error_page(self):
        line, pdf = self.snapshot("<html><title>Host Needed</title><body>The host is not configured.</body></html>")
        self.assertEqual(line["code"], "not_the_article")
        self.assertEqual(pdf["evidence"]["denial_marker"], "host needed")

    def test_denial_page_that_has_the_title_passes(self):
        line, _ = self.snapshot(f"<html><title>{TITLE}</title><body>You do not have access. Abstract ...</body></html>")
        self.assertEqual(line["code"], "ok")

    def test_empty_page(self):
        line, _ = self.snapshot("<html><head></head><body></body></html>")
        self.assertEqual(line["code"], "not_the_article")

    def test_meta_doi_mismatch(self):
        line, _ = self.snapshot(f"<html><title>{TITLE}</title><meta name='citation_doi' content='10.1000/other'>"
                                "</html>")
        self.assertEqual(line["code"], "ok", "a snapshot is no published file: the DOI rule does not apply")


class Match(Base):
    def test_one_file_against_records(self):
        recs = [self.record("x"), self.record("y", item=self.item(title="Another Paper About Lungs Entirely"))]
        f = self.pdf("dl.pdf", [PAPER_PAGE])
        r = self.run_script("--match", str(f), *map(str, recs))
        out = lines(r.stdout)
        self.assertEqual(r.returncode, 0)
        self.assertEqual([o["code"] for o in out[:2]], ["ok", "title_not_found"])
        self.assertEqual(out[-1]["matched"], ["x"])
        self.assertEqual((out[-1]["md5"], out[-1]["file_version"]), (hashlib.md5(f.read_bytes()).hexdigest(), "published"))
        self.assertNotIn("pdf", json.loads(recs[0].read_text(encoding="utf-8")), "--match never writes records")

    def test_none_matched_and_stdin_records(self):
        f = self.pdf("dl.pdf", ["Unrelated"])
        r = self.run_script("--match", str(f), str(self.record("x")))
        self.assertEqual((r.returncode, lines(r.stdout)[-1]["matched"]), (1, []))
        f = self.pdf("dl2.pdf", [PAPER_PAGE])
        rec = json.dumps({"slug": "s", "item": self.item()})
        r = self.run_script("--match", str(f), stdin=rec + "\n" + rec.replace('"s"', '"t"'))
        self.assertEqual(lines(r.stdout)[-1]["matched"], ["s", "t"])

    def test_cannot_check(self):
        r = self.run_script("--match", str(self.tmp / "missing.pdf"), str(self.record("x")))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "file_not_found"))
        f = self.pdf("dl.pdf", [PAPER_PAGE])
        r = self.run_script("--match", str(f), stdin="")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_records"))

    def test_argument_errors(self):
        f = self.pdf("dl.pdf", [PAPER_PAGE])
        self.assertEqual(self.run_script("--match", str(f), "-i", str(self.record("x"))).returncode, 2)
        self.assertEqual(self.run_script("--item", "i.json", str(self.record("x"))).returncode, 2)


class SingleAndTools(Base):
    def test_single_mode(self):
        (self.tmp / "item.json").write_text(json.dumps(self.item()), encoding="utf-8")
        f = self.pdf("p.pdf", [PAPER_PAGE])
        r = self.run_script("--item", str(self.tmp / "item.json"), "--pdf", str(f))
        out = json.loads(r.stdout)
        self.assertEqual((r.returncode, out["code"]), (0, "ok"))
        self.assertEqual(out["md5"], hashlib.md5(f.read_bytes()).hexdigest())
        f = self.pdf("q.pdf", ["Unrelated"])
        r = self.run_script("--item", str(self.tmp / "item.json"), "--pdf", str(f))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "title_not_found"))
        (self.tmp / "bad.json").write_text("[]", encoding="utf-8")
        r = self.run_script("--item", str(self.tmp / "bad.json"), "--pdf", str(f))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "item_unreadable"))

    def test_no_pdftotext_cannot_check(self):
        path = self.record("r", [PAPER_PAGE])
        empty = self.tmp / "empty"
        empty.mkdir()
        for argv in (["-i", str(path)], ["--match", str(self.tmp / "r.pdf"), str(path)]):
            r = self.run_script(*argv, path=str(empty))
            out = json.loads(r.stdout)
            self.assertEqual((r.returncode, out["code"]), (2, "no_extractor"))
            self.assertIn("install.md", out["hint"])
        self.assertNotIn("pdf", json.loads(path.read_text(encoding="utf-8")))

    @unittest.skipUnless(shutil.which("pdftotext") and shutil.which("pdfinfo"), "poppler-utils not installed")
    def test_real_pdftotext(self):
        real = os.path.dirname(shutil.which("pdftotext"))
        (self.tmp / "real.pdf").write_bytes(make_pdf(["A cover sheet", PAPER_PAGE, "Introduction"]))
        path = self.record("real", file="real.pdf")
        r = self.run_script("-i", str(path), path=real)
        line = lines(r.stdout)[0]
        self.assertEqual((line["code"], line["page_count"]), ("ok_on_page_2", 3), r.stderr)


if __name__ == "__main__":
    unittest.main()
