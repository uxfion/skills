# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/p2zlib/verify.py: the verdict's pass paths and vetoes, kinds, HTML snapshots, the evidence.

pdftotext / pdfinfo are shell stubs on PATH that print sidecar files (<file>.txt with form feeds between pages,
<file>.pages with the page count), so the verdicts do not depend on the poppler installed here. One test runs the
real pdftotext on a generated PDF when it is installed."""
import contextlib
import hashlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import fake_pdf, make_pdf, poppler_stubs
from p2zlib import cli, verify

REAL_PDFTOTEXT = shutil.which("pdftotext") if shutil.which("pdfinfo") else None
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
DOI = "10.1109/JBHI.2022.3142076"
PAPER_PAGE = (f"{TITLE}\nWei Liu, Jing Zhang, and Ming Chen\nAbstract\nWe study cardiac image segmentation.\n"
              f"DOI: {DOI}")
COVER = ("Downloaded from the institutional repository on 2024-01-01\n"
         "This is a post-print of an Accepted manuscript.\nCitation: Liu et al. (2022)")

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verify_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = poppler_stubs(self.tmp / "bin")
        self.use_path(str(self.bin))

    def use_path(self, path):
        patcher = mock.patch.dict(os.environ, {"PATH": path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def item(self, **extra):
        return {"itemType": "journalArticle", "title": TITLE, "DOI": DOI,
                "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}], **extra}

    def pdf(self, name, pages, page_count=None, data=None):
        return fake_pdf(self.tmp / name, pages, page_count, data)

    def record(self, item=None, **extra):
        return {"item": self.item() if item is None else item, **extra}

    def check(self, *pages, item=None, file_name="r.pdf", page_count=None, kind=None, **extra):
        """One record against one PDF with these pages -> check()'s result."""
        f = self.pdf(file_name, list(pages), page_count)
        return verify.check(f, self.record(item, **extra), kind)


class Verdict(Base):
    def test_title_on_page_one_with_evidence(self):
        res = self.check(PAPER_PAGE, "Introduction ...", page_count=9)
        self.assertEqual(set(res), {"code", "evidence", "md5", "kind"})
        self.assertEqual((res["code"], res["kind"]), ("ok", "published"))
        ev = res["evidence"]
        self.assertEqual((ev["extractor"], ev["page_count"], ev["pages_scanned"], ev["title_page"]),
                         ("pdftotext", 9, 2, 1))
        self.assertEqual((ev["doi_found"], ev["first_author_found"], ev["first_author_in_byline"]), (True, True, True))
        self.assertEqual((ev["kind"], ev["arxiv_stamp"], ev["matched_title"]), ("published", None, TITLE))
        self.assertNotIn("file_version", ev)
        self.assertEqual(res["md5"], hashlib.md5((self.tmp / "r.pdf").read_bytes()).hexdigest())

    def test_cover_sheet_then_title(self):
        res = self.check(COVER, PAPER_PAGE)
        self.assertEqual(res["code"], "ok_on_page_2")
        self.assertTrue(res["evidence"]["cover_page_suspected"])
        self.assertIsNotNone(res["evidence"]["excerpt_title_page"])

    def test_title_on_page_three_is_a_collection(self):
        res = self.check("Proceedings front matter", "Table of contents", PAPER_PAGE)
        self.assertEqual(res["code"], "ok_on_page_3")
        self.assertTrue(res["evidence"]["collection_suspected"])

    def test_long_file_with_title_on_page_two(self):
        res = self.check("Program of the workshop", PAPER_PAGE, page_count=120)
        self.assertEqual(res["code"], "ok_on_page_2")
        self.assertTrue(res["evidence"]["collection_suspected"])

    def test_title_absent_fails_with_evidence(self):
        res = self.check("A different paper about lungs\nSomeone Else\nAbstract ...")
        self.assertEqual(res["code"], "title_not_found")
        self.assertNotIn(res["code"], verify.PASS_CODES)
        self.assertIn("claim.py --accept", verify.HINTS["title_not_found"])
        self.assertEqual(res["evidence"]["doi_found"], False)

    def test_doi_and_author_null_when_item_lacks_them(self):
        res = self.check(PAPER_PAGE, item={"itemType": "journalArticle", "title": TITLE})
        self.assertIsNone(res["evidence"]["doi_found"])
        self.assertIsNone(res["evidence"]["first_author_found"])

    def test_not_a_pdf_and_missing_file(self):
        (self.tmp / "html.pdf").write_text("<html><title>Login</title></html>", encoding="utf-8")
        res = verify.check(self.tmp / "html.pdf", self.record())
        self.assertEqual(res["code"], "not_a_pdf")
        self.assertEqual(res["evidence"]["excerpt"], "<html><title>Login</title></html>")
        with self.assertRaises(cli.Stop) as caught:
            verify.check(self.tmp / "missing.pdf", self.record())
        stop = caught.exception
        self.assertEqual((stop.code, stop.exit, stop.extra["file"]), ("file_not_found", cli.ACT,
                                                                      str(self.tmp / "missing.pdf")))
        self.assertIsNone(verify.extract(self.tmp / "missing.pdf"))

    def test_no_text_layer(self):
        f = self.pdf("scan.pdf", None)  # no sidecar: the stub fails like pdftotext on a broken file
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(verify.check(f, self.record())["code"], "no_text_layer")
        self.assertIn("pdftotext scan.pdf: exit 1", err.getvalue())
        self.assertEqual(self.check("   ")["code"], "no_text_layer")

    def test_short_title_cannot_judge(self):
        res = self.check("GAN\nIan Goodfellow", item={"itemType": "journalArticle", "title": "GAN"})
        self.assertEqual(res["code"], "cannot_judge")

    def test_title_markup_is_dropped(self):
        res = self.check(PAPER_PAGE, item=self.item(title="Progressive <i>Deep</i> Learning for Cardiac Image "
                                                          "Segmentation"))
        self.assertEqual(res["code"], "ok")


class PathB(Base):
    def test_words_with_ligature_and_line_end_hyphen_and_byline_author(self):
        page = ("Progressive Deep Learn-\ning, revisited, for Cardiac Im-\nage Segmen-\ntation\nWei Liu, Jing Zhang\n"
                "Abstract ...")
        res = self.check(page, item=self.item(DOI=None))
        self.assertEqual(res["code"], "ok_by_words")
        self.assertEqual(res["evidence"]["title_words"]["share"], 1.0)
        self.assertTrue(res["evidence"]["first_author_in_byline"])
        self.assertEqual(res["evidence"]["matched_title"], TITLE)

    def test_words_with_doi(self):
        page = f"PROGRESSIVE DEEP-LEARNING (PDL) FOR\nCARDIAC IMAGE\nSEGMENTATION?\nM. Chen\n{DOI}"
        self.assertEqual(self.check(page, item=self.item(creators=[]))["code"], "ok_by_words")

    def test_words_alone_are_not_enough(self):
        page = "Progressive deep learning for the cardiac image segmentation: a survey of others\nSomeone Else"
        self.assertEqual(self.check(page, item=self.item(DOI=None))["code"], "title_not_found")

    def test_below_threshold_fails_even_with_doi(self):
        res = self.check(f"Cardiac Imaging\nWei Liu\n{DOI}")
        self.assertEqual(res["code"], "title_not_found")
        self.assertLess(res["evidence"]["title_words"]["share"], 0.8)

    def test_words_on_later_pages_count(self):
        res = self.check("Wei Liu, Jing Zhang", "Progressive deep learning, again, for cardiac image segmentation",
                         item=self.item(DOI=None))
        self.assertEqual(res["code"], "ok_by_words")

    def test_author_cited_later_is_no_corroboration(self):
        filler = "Background text. " * 120  # pushes the citation past the byline window
        page = (f"Progressive deep learning, again, for cardiac image segmentation\nSomeone Else\n{filler}"
                "as shown by Liu et al. [3]")
        res = self.check(page, item=self.item(DOI=None))
        self.assertEqual(res["code"], "title_not_found")
        self.assertEqual((res["evidence"]["first_author_found"], res["evidence"]["first_author_in_byline"]),
                         (True, False))

    def test_alt_titles_from_the_record_and_to_judge(self):
        page = "A Gentle Introduction to Conformal Prediction\nA. Angelopoulos"
        alt = "A Gentle Introduction to Conformal Prediction"
        item = self.item(title="Conformal Prediction: A Gentle Introduction", DOI=None, creators=[])
        res = self.check(page, item=item, alt_titles=[alt])
        self.assertEqual((res["code"], res["evidence"]["matched_title"]), ("ok", alt))
        self.assertEqual(self.check(page, item=item, alt_titles=alt)["code"], "ok", "one alt title as a string")
        ex = verify.extract(self.tmp / "r.pdf")
        self.assertEqual(verify.judge(ex, item["title"])[0], "title_not_found")
        self.assertEqual(verify.judge(ex, item["title"], alt_titles=[alt])[0], "ok")


class HeadMarkers(Base):
    def test_correction_notice_passes_a_but_fails(self):
        res = self.check(f"Correction to: {TITLE}\nThe author name was misspelled.\n{DOI}")
        self.assertEqual(res["code"], "erratum_suspected")
        self.assertEqual(res["evidence"]["erratum_marker"], "correction")

    def test_author_correction_and_erratum_forms(self):
        for head in ("Author Correction:", "Erratum", "RETRACTION NOTICE", "Publisher's Correction - "):
            self.assertEqual(self.check(f"{head}\n{TITLE}\nWei Liu")["code"], "erratum_suspected", head)

    def test_title_with_correction_is_not_an_erratum(self):
        title = "Self-Correction with Large Language Models"
        res = self.check(f"Correction\n{title}\nWei Liu", item=self.item(title=title, DOI=None))
        self.assertEqual(res["code"], "ok")

    def test_mentions_are_not_headings(self):
        for head in ("Correction-based learning is popular", "Corrections of motion artefacts in MRI"):
            self.assertEqual(self.check(f"{head}\n{PAPER_PAGE}")["code"], "ok", head)

    def test_supplement_and_its_file_name(self):
        page = f"Supplementary Material\n{TITLE}\nWei Liu"
        res = self.check(page)
        self.assertEqual((res["code"], res["evidence"]["supplement_marker"]),
                         ("supplement_suspected", "supplementary material"))
        self.assertTrue(res["evidence"]["supplementary"])
        res = self.check(page, file_name="r.supplement.pdf")
        self.assertEqual((res["code"], res["kind"], res["evidence"]["kind"]), ("ok", "supplement", "supplement"))
        self.assertEqual(self.check(page, kind="supplement")["code"], "ok", "a given kind counts the same")

    def test_margin_supplemental_content_is_no_supplement(self):
        self.assertEqual(self.check(f"Supplemental content\n{PAPER_PAGE}")["code"], "ok")


class DoiMismatch(Base):
    def test_other_doi_printed(self):
        res = self.check(f"{TITLE}\nWei Liu\nDOI: 10.1016/j.media.2020.101234")
        self.assertEqual((res["code"], res["evidence"]["doi_mismatch"]), ("doi_mismatch", True))
        self.assertEqual(res["evidence"]["dois_on_page_1"], ["10.1016/j.media.2020.101234"])

    def test_only_for_published_files(self):
        page = f"{TITLE}\nWei Liu\nDOI: 10.48550/arXiv.2201.00001"
        res = self.check(page, file_name="r.accepted.pdf")
        self.assertEqual((res["code"], res["kind"], res["evidence"]["doi_mismatch"]), ("ok", "accepted", None))
        self.assertEqual(self.check(page, file_name="r.preprint.pdf")["code"], "ok")
        self.assertEqual(self.check(page, kind="accepted")["code"], "ok")

    def test_matches_despite_case_line_break_or_other_dois(self):
        self.assertEqual(self.check(f"{TITLE}\nWei Liu\ndoi: 10.1109/jbhi.2022.\n3142076\nSee also 10.1000/xyz123")
                         ["code"], "ok")

    def test_no_doi_printed_or_none_in_item(self):
        self.assertEqual(self.check(f"{TITLE}\nWei Liu")["code"], "ok")
        self.assertEqual(self.check(f"{TITLE}\n10.1000/other", item=self.item(DOI=None))["code"], "ok")


class Kinds(Base):
    STAMPED = f"arXiv:2201.00001v2 [cs.CV] 3 Jan 2022\n{TITLE}\nWei Liu\nDOI: 10.48550/arXiv.2201.00001"

    def test_the_arxiv_stamp_is_evidence_not_a_kind(self):
        res = self.check(self.STAMPED)
        self.assertEqual((res["code"], res["kind"], res["evidence"]["arxiv_stamp"]),
                         ("ok", "published", "arXiv:2201.00001v2 [cs.CV]"))  # the arXiv DOI on it is no doi_mismatch
        self.assertEqual(self.check(self.STAMPED, file_name="r.accepted.pdf")["kind"], "accepted")
        self.assertEqual(self.check(self.STAMPED, kind="unknown")["kind"], "published", "unknown is no kind given")

    def test_pdf_dates_and_page_two(self):
        f = self.pdf("r.pdf", [PAPER_PAGE, "Introduction and more"], 9)
        f.with_name("r.pdf.dates").write_text("CreationDate:   2023-10-09T18:57:41+08\nModDate:        2023-10-10T09:00:00Z\n")
        ev = verify.check(f, self.record())["evidence"]
        self.assertEqual((ev["pdf_dates"], ev["excerpt_page_2"], ev["page_count"]),
                         ({"created": "2023-10-09T18:57:41+08", "modified": "2023-10-10T09:00:00Z"}, "Introduction and more", 9))

    def test_kind_of_names(self):
        for name, kind in (("s.pdf", "published"), ("s.accepted.pdf", "accepted"), ("s.preprint.pdf", "preprint"),
                           ("s.supplement.pdf", "supplement"), ("s.html", "snapshot"), ("s.htm", "snapshot"),
                           ("S.PDF", "published"), ("getPDF.jsp", "published")):
            self.assertEqual(verify.kind_of(self.tmp / name), kind, name)
        self.assertEqual(verify.kind_of("s.pdf", "accepted"), "accepted")
        with self.assertRaises(ValueError):
            verify.kind_of("s.pdf", "version_of_record")


class Html(Base):
    def snapshot(self, html, name="r.html", item=None):
        (self.tmp / name).write_text(html, encoding="utf-8")
        return verify.check(self.tmp / name, self.record(item))

    def test_article_page(self):
        res = self.snapshot(f"<html><head><title>{TITLE} | IEEE</title>"
                            f"<meta name='citation_doi' content='{DOI}'></head>"
                            "<body><h1>Abstract</h1><p>We study segmentation.</p></body></html>")
        self.assertEqual((res["code"], res["kind"]), ("ok", "snapshot"))
        self.assertEqual((res["evidence"]["extractor"], res["evidence"]["html_title"]), ("html", f"{TITLE} | IEEE"))

    def test_entities_are_unescaped(self):
        title = "Segmentation & Registration: A Survey"
        res = self.snapshot("<html><title>Segmentation &amp; Registration: A Survey</title></html>",
                            item=self.item(title=title, DOI=None))
        self.assertEqual(res["code"], "ok")

    def test_title_only_in_a_script_does_not_count(self):
        res = self.snapshot(f"<html><title>Sign in</title><script>var t='{TITLE}'</script>"
                            "<body>Please sign in</body></html>")
        self.assertEqual(res["code"], "title_not_found")

    def test_proxy_error_page(self):
        res = self.snapshot("<html><title>Host Needed</title><body>The host is not configured.</body></html>")
        self.assertEqual(res["code"], "not_the_article")
        self.assertEqual(res["evidence"]["denial_marker"], "host needed")

    def test_access_and_robot_pages(self):
        for body in ("Access denied", "Just a moment...", "Your institution does not subscribe to this content"):
            res = self.snapshot(f"<html><title>Journal</title><body>{body}</body></html>")
            self.assertEqual(res["code"], "not_the_article", body)

    def test_denial_page_that_has_the_title_passes(self):
        res = self.snapshot(f"<html><title>{TITLE}</title><body>You do not have access. Abstract ...</body></html>")
        self.assertEqual(res["code"], "ok")

    def test_empty_page(self):
        self.assertEqual(self.snapshot("<html><head></head><body></body></html>")["code"], "not_the_article")

    def test_meta_doi_mismatch(self):
        res = self.snapshot(f"<html><title>{TITLE}</title><meta name='citation_doi' content='10.1000/other'></html>")
        self.assertEqual(res["code"], "ok", "a snapshot is no published file: the DOI rule does not apply")
        self.assertEqual(res["evidence"]["dois_on_page_1"], ["10.1000/other"])

    def test_html_without_poppler(self):
        self.use_path(str(self.tmp / "nowhere"))
        res = self.snapshot(f"<html><title>{TITLE}</title></html>")
        self.assertEqual(res["code"], "ok", "a snapshot needs no pdftotext")


class Records(Base):
    def test_subject(self):
        rec = {"item": {"title": TITLE, "DOI": DOI, "creators": [
            {"creatorType": "editor", "lastName": "Ed"}, {"creatorType": "author", "name": "World Health Organization"}]},
            "alt_titles": "Another Title"}
        self.assertEqual(verify.subject(rec), {"title": TITLE, "alt_titles": ["Another Title"], "doi": DOI,
                                               "surname": "Organization"})
        rec = {"item": {"title": TITLE, "DOI": 7, "creators": [{"creatorType": "editor", "lastName": "Ed"}]},
               "alt_titles": ["", 3, "Alt"]}
        self.assertEqual(verify.subject(rec), {"title": TITLE, "alt_titles": ["Alt"], "doi": None, "surname": "Ed"})
        self.assertEqual(verify.subject({}), {"title": "", "alt_titles": [], "doi": None, "surname": None})

    def test_cache_reads_a_file_once_for_several_records(self):
        f = self.pdf("dl.pdf", [PAPER_PAGE])
        other = self.record(self.item(title="Another Paper About Lungs Entirely"))
        cache = {}
        with mock.patch.object(verify, "pdftotext_pages", wraps=verify.pdftotext_pages) as pages:
            codes = [verify.check(f, rec, cache=cache)["code"] for rec in (self.record(), other)]
        self.assertEqual((codes, pages.call_count), (["ok", "title_not_found"], 1))
        self.assertEqual(list(cache), [str(f.absolute())])
        with self.assertRaises(cli.Stop):
            verify.check(self.tmp / "gone.pdf", self.record(), cache=cache)
        self.assertIsNone(cache[str((self.tmp / "gone.pdf").absolute())])

    def test_summary_fields(self):
        res = self.check(PAPER_PAGE)
        self.assertEqual(verify.summary_fields(res["code"], res["evidence"]),
                         {"title_page": 1, "page_count": 1, "kind": "published", "cover_page_suspected": False,
                          "collection_suspected": False})
        res = self.check("Cardiac Imaging\nWei Liu")
        self.assertIn("title_words", verify.summary_fields(res["code"], res["evidence"]))
        res = self.check(f"Erratum\n{TITLE}")
        self.assertEqual(verify.summary_fields(res["code"], res["evidence"])["erratum_marker"], "erratum")


class Poppler(Base):
    def test_no_pdftotext_cannot_check(self):
        f = self.pdf("r.pdf", [PAPER_PAGE])
        self.use_path(str(self.tmp / "nowhere"))
        for fn in (lambda: verify.require_pdftotext(), lambda: verify.extract(f),
                   lambda: verify.check(f, self.record())):
            with self.assertRaises(cli.Stop) as caught:
                fn()
            stop = caught.exception
            self.assertEqual((stop.code, stop.exit), ("no_pdftotext", cli.CANNOT))
            self.assertIn("install.md", stop.hint)

    @unittest.skipUnless(REAL_PDFTOTEXT, "poppler-utils not installed")
    def test_real_pdftotext(self):
        self.use_path(os.path.dirname(REAL_PDFTOTEXT))
        (self.tmp / "real.pdf").write_bytes(make_pdf(["A cover sheet", PAPER_PAGE, "Introduction"]))
        res = verify.check(self.tmp / "real.pdf", self.record())
        self.assertEqual((res["code"], res["evidence"]["page_count"], res["evidence"]["pages_scanned"]),
                         ("ok_on_page_2", 3, 3))


if __name__ == "__main__":
    unittest.main()
