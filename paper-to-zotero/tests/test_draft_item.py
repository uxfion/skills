# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/draft_item.py: records drafted from paper-fetch's result files, against a schema with Zotero 7's
names (kept in the import's scratch/schema.json, as a run keeps it, so no Zotero is asked)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, load, smoke

from p2zlib import run

draft_item = load("draft_item")


def fields(*names, **based):
    return [{"field": n} for n in names] + [{"field": f, "baseField": b} for f, b in based.items()]


AUTHORS = [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]
# The item types and CSL tables of Zotero's schema that drafting touches, as Zotero 7 names them.
SCHEMA = {"version": 44, "itemTypes": [
    {"itemType": "journalArticle", "creatorTypes": AUTHORS,
     "fields": fields("title", "abstractNote", "publicationTitle", "publisher", "place", "date", "volume", "issue", "pages",
                      "language", "DOI", "citationKey", "url", "PMID", "PMCID", "ISSN", "libraryCatalog", "extra")},
    {"itemType": "conferencePaper", "creatorTypes": AUTHORS,
     "fields": fields("title", "abstractNote", "conferenceName", "publisher", "place", "date", "volume", "pages", "series",
                      "DOI", "ISBN", "citationKey", "url", "ISSN", "libraryCatalog", "extra",
                      proceedingsTitle="publicationTitle")},
    {"itemType": "preprint", "creatorTypes": AUTHORS[:1] + AUTHORS[2:],
     "fields": fields("title", "abstractNote", "place", "date", "series", "DOI", "citationKey", "url", "libraryCatalog",
                      "extra", repository="publisher", archiveID="number")},
    {"itemType": "thesis", "creatorTypes": [{"creatorType": "author", "primary": True}],
     "fields": fields("title", "abstractNote", "place", "date", "url", "libraryCatalog", "extra", university="publisher")},
], "csl": {
    "types": {"article-journal": ["journalArticle"], "paper-conference": ["conferencePaper"], "article": ["preprint"],
              "thesis": ["thesis"]},
    "fields": {"text": {"title": ["title"], "container-title": ["publicationTitle"], "volume": ["volume"], "issue": ["issue"],
                        "page": ["pages"], "DOI": ["DOI"], "URL": ["url"], "ISSN": ["ISSN"], "abstract": ["abstractNote"],
                        "publisher": ["publisher"], "event-title": ["meetingName", "conferenceName"],
                        "publisher-place": ["place"], "source": ["libraryCatalog"], "language": ["language"],
                        "version": ["versionNumber"], "collection-title": ["seriesTitle", "series"],
                        "PMID": ["PMID"], "PMCID": ["PMCID"]},
               "date": {"issued": "date", "accessed": "accessDate"}},
    "names": {"author": "author", "editor": "editor", "contributor": "contributor"},
}}

HU, SHEN = {"family": "Hu", "given": "Jie"}, {"family": "Shen", "given": "Li"}
CATEGORIES = ["Computer Vision and Pattern Recognition (cs.CV)", "FOS: Computer and information sciences",
              "Image and Video Processing (eess.IV)", "Quantum Physics (quant-ph)", "Computer Vision and Pattern Recognition (cs.CV)"]
PREPRINT = {"ids": {"arxiv": "1709.01507", "doi": "10.48550/arXiv.1709.01507"}, "title": "Squeeze-and-Excitation Networks",
            "abstract": "The central building block.", "author": [HU, SHEN], "categories": CATEGORIES, "latest": "v4"}


def result(slug, csl, record_of="published", **fields):
    ids = {"doi": csl.get("DOI"), "arxiv": None, "pmid": None, "pmcid": None}
    return {"slug": slug, "slug_given": False, "request": {"given": csl.get("DOI") or slug}, "record_of": record_of,
            "ids": ids, "csl": csl, "alt_titles": [], "versions": {"published": [], "incomplete": []}, "files": [],
            "warnings": [], **fields}


JAMA = result("jama", {"type": "article-journal", "title": "Trials", "author": [HU], "container-title": "JAMA",
                       "issued": {"date-parts": [[2023, 5, 2]]}, "DOI": "10.1001/jama.2023.4855", "ISSN": ["0098-7484", "1538-3598"],
                       "publisher": "American Medical Association", "version": "2", "language": "en",
                       "URL": "http://dx.doi.org/10.1001/jama.2023.4855", "source": "DOI.org (Crossref)"})
SENET_PREPRINT = result("senet", {"type": "article", "title": "Squeeze-and-Excitation Networks", "author": [HU, SHEN],
                                  "issued": {"date-parts": [[2017]]}, "DOI": "10.48550/arXiv.1709.01507", "publisher": "arXiv",
                                  "abstract": "The central building block.", "categories": CATEGORIES,
                                  "source": "DOI.org (Datacite)"},
                        record_of="preprint", ids={"doi": "10.48550/arXiv.1709.01507", "arxiv": "1709.01507"},
                        request={"given": "arXiv:1709.01507v2"})
SENET_CVPR = result("senet", {"type": "paper-conference", "title": "Squeeze-and-Excitation Networks", "author": [HU],
                              "container-title": "2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition",
                              "event-title": "CVPR 2018", "publisher": "IEEE", "issued": {"date-parts": [[2018, 6]]},
                              "page": "7132-7141", "DOI": "10.1109/cvpr.2018.00745", "source": "DOI.org (Crossref)"},
                    versions={"preprint": PREPRINT, "published": [], "incomplete": []},
                    request={"given": "1709.01507", "redraft": "10.1109/CVPR.2018.00745"})
THESIS = result("thesis", {"type": "thesis", "title": "A Thesis", "author": [SHEN], "publisher": "MIT",
                           "DOI": "10.9999/thesis", "issued": {"date-parts": [[2020]]}, "source": "DOI.org (Datacite)"})
PAGE = result("page", {"type": "paper-conference", "title": "From a Page", "author": [HU],
                       "container-title": "ICLR", "URL": "https://openreview.net/forum?id=x", "source": "openreview.net"})


class DraftItem(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="p2z-draft-"))
        self.results, self.records = self.root / "fetch" / "results", self.root / "records"
        self.results.mkdir(parents=True)
        (self.root / "scratch").mkdir()
        (self.root / "scratch" / "schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")

    def put(self, res, name=None):
        path = self.results / f"{name or res['slug']}.json"
        path.write_text(json.dumps(res), encoding="utf-8")
        return path

    def draft(self, *argv, stdin=""):
        return call(draft_item, *argv, "--base-url", f"http://127.0.0.1:{closed_port()}", stdin=stdin)

    def rec(self, slug):
        return json.loads((self.records / f"{slug}.json").read_text(encoding="utf-8"))

    def test_a_published_paper(self):
        r = self.draft(self.put(JAMA))
        self.assertEqual((r.code, r.lines[0]), (0, {"slug": "jama", "code": "ok", "itemType": "journalArticle", "title": "Trials"}), r)
        rec = self.rec("jama")
        self.assertEqual(rec["item"], {
            "itemType": "journalArticle", "title": "Trials", "creators": [{"creatorType": "author", "firstName": "Jie", "lastName": "Hu"}],
            "publicationTitle": "JAMA", "date": "2023-05-02", "language": "en", "DOI": "10.1001/jama.2023.4855",
            "url": "https://doi.org/10.1001/jama.2023.4855", "ISSN": "0098-7484, 1538-3598", "libraryCatalog": "DOI.org (Crossref)"},
            "no publisher in a journalArticle, no version, the DOI's link as url")
        self.assertEqual(list(rec["item"])[:3], ["itemType", "title", "creators"])
        self.assertEqual(rec["fetched"], str(self.results / "jama.json"))
        self.assertNotIn("tags", rec)
        self.assertNotIn("citationKey", rec)

    def test_an_arxiv_preprint(self):
        self.draft(self.put(SENET_PREPRINT))
        rec = self.rec("senet")
        item = rec["item"]
        self.assertEqual((item["itemType"], item["url"], item["repository"], item["archiveID"], item["DOI"], item["date"]),
                         ("preprint", "https://arxiv.org/abs/1709.01507v2", "arXiv", "arXiv:1709.01507",
                          "10.48550/arXiv.1709.01507", "2017"), "the vN the request named")
        self.assertEqual(rec["tags"], [{"tag": t, "type": 1} for t in (
            "Computer Science - Computer Vision and Pattern Recognition",
            "Electrical Engineering and Systems Science - Image and Video Processing", "Quantum Physics")],
            "Zotero's arXiv translator's names; FOS entries and repeats dropped")

    def test_a_published_version_keeps_what_the_preprint_gave(self):
        r = self.draft(self.put(SENET_CVPR))
        rec, item = self.rec("senet"), self.rec("senet")["item"]
        self.assertEqual((item["itemType"], item["proceedingsTitle"], item["conferenceName"], item["publisher"], item["url"]),
                         ("conferencePaper", "2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition", "CVPR 2018",
                          "IEEE", "https://doi.org/10.1109/cvpr.2018.00745"))
        self.assertEqual((item["abstractNote"], item["extra"], len(item["creators"])),
                         ("The central building block.", "arXiv: 1709.01507", 1), "its own authors; the preprint's abstract")
        self.assertEqual([t["tag"] for t in rec["tags"]][0], "Computer Science - Computer Vision and Pattern Recognition")
        self.assertEqual(r.lines[0]["warnings"], ["the record has no abstract: the preprint's is drafted"])
        without = {**SENET_CVPR, "csl": {k: v for k, v in SENET_CVPR["csl"].items() if k != "author"}}
        self.draft(self.put(without), "--redraft")
        self.assertEqual(len(self.rec("senet")["item"]["creators"]), 2, "no authors of its own: the preprint's")

    def test_rules_beyond_the_tables(self):
        r = self.draft(self.put(THESIS), self.put(PAGE))
        thesis, page = self.rec("thesis")["item"], self.rec("page")["item"]
        self.assertEqual((thesis["extra"], thesis["university"]), ("DOI: 10.9999/thesis", "MIT"), "no DOI field: extra")
        self.assertIn("thesis has no DOI field; DOI written to extra", r.lines[0]["warnings"])
        self.assertEqual((page["url"], page["libraryCatalog"]), ("https://openreview.net/forum?id=x", "openreview.net"))
        med = {"title": "Ultrasound", "author": [HU], "DOI": "10.9999/med", "PMID": "123", "PMCID": "PMC456"}
        self.draft(self.put(result("journal", {**med, "type": "article-journal"})),
                   self.put(result("proc", {**med, "type": "paper-conference"})))
        journal, proc = self.rec("journal")["item"], self.rec("proc")["item"]
        self.assertEqual((journal["PMID"], journal["PMCID"], journal.get("extra")), ("123", "PMC456", None),
                         "Zotero's schema 44 gives journalArticle PMID and PMCID fields")
        self.assertEqual((proc.get("PMID"), proc["extra"]), (None, "PMID: 123\nPMCID: PMC456"),
                         "no field for them: extra, where Zotero reads them")
        odd = result("odd", {"type": "song", "title": "A Song", "DOI": "10.9999/song"})
        r = self.draft(self.put(odd))
        self.assertEqual(self.rec("odd")["item"]["itemType"], "journalArticle")
        self.assertIn("not in Zotero's table", r.lines[0]["warnings"][0])

    def test_reruns_redrafts_and_what_is_refused(self):
        bib = {**JAMA, "slug": "numpy2020", "slug_given": True, "cite": "numpy2020"}
        path = self.put(bib)
        self.draft(path)
        rec = self.rec("numpy2020")
        self.assertEqual(rec["citationKey"], "numpy2020", "the key given is the citation key")
        rec.update(collection="RIBA5MZJ", tags=[{"tag": "mine", "type": 0}], citationKey="harris2020")
        rec["item"]["title"] = "Revised by the agent"
        (self.records / "numpy2020.json").write_text(json.dumps(rec), encoding="utf-8")
        r = self.draft(path)
        self.assertEqual(r.lines[0]["code"], "skipped")
        self.assertEqual(self.rec("numpy2020")["item"]["title"], "Revised by the agent")
        r = self.draft("--redraft", stdin=f"{path}\n")
        rec = self.rec("numpy2020")
        self.assertEqual((r.code, rec["item"]["title"], rec["collection"], rec["tags"], rec["citationKey"]),
                         (0, "Trials", "RIBA5MZJ", [{"tag": "mine", "type": 0}], "harris2020"), "the agent's fields stay")
        rec["saved"] = {"key": "ABCD2345"}
        (self.records / "numpy2020.json").write_text(json.dumps(rec), encoding="utf-8")
        stub = self.put({"slug": "stub", "request": {"given": "10.9999/x"}, "warnings": ["doi.org: not_found"]})
        elsewhere = self.root / "elsewhere.json"
        elsewhere.write_text(json.dumps(JAMA), encoding="utf-8")
        r = self.draft("--redraft", path, stub, elsewhere)
        self.assertEqual((r.code, [o["code"] for o in r.lines[:-1]]), (1, ["already_saved", "result_invalid", "no_records_dir"]))
        r = self.draft(elsewhere, "-o", self.root / "other")
        self.assertEqual((r.code, (self.root / "other" / "jama.json").is_file()), (0, True))

    def test_a_record_follows_its_renamed_result(self):
        old = self.put(JAMA)
        self.draft(old)
        old.unlink()  # paper-fetch's identify renamed the result to the key given later
        new = self.put({**JAMA, "slug": "jama2023trials", "slug_given": True, "renamed_from": ["jama"]})
        rec = run.read(self.records / "jama.json")
        self.assertEqual(run.result_of(rec)[1], new, "a record not yet moved still finds its result")
        r = self.draft(new)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["renamed_from"]), ("skipped", "jama"))
        self.assertEqual(((self.records / "jama.json").exists(), self.rec("jama2023trials")["fetched"]), (False, str(new)),
                         "the record is renamed and points at the result: no orphan, no second draft")

    def test_zotero_not_running(self):
        (self.root / "scratch" / "schema.json").unlink()
        r = self.draft(self.put(JAMA), self.put(THESIS))
        self.assertEqual((r.code, [o["code"] for o in r.lines[:-1]]), (2, ["zotero_unreachable", "not_run"]), r)

    def test_smoke(self):
        r = smoke("draft_item", self.put(JAMA), "--base-url", f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
