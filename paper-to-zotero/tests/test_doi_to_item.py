# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/doi_to_item.py: drafting records from identifiers, a preprint's published_candidates and
--redraft, against the fake web (doi.org, Crossref, arXiv's API, venue pages) and the fake Zotero's schema."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, closed_port, load, smoke
from fake_web import FakeWeb
from fake_zotero import FakeZotero

from p2zlib import run, web

doi_to_item = load("doi_to_item")


def fields(*names, **based):
    return [{"field": n} for n in names] + [{"field": f, "baseField": b} for f, b in based.items()]


AUTHORS = [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}, {"creatorType": "contributor"}]
# The item types and CSL mappings of Zotero's schema that drafting touches, as Zotero 7 names them.
SCHEMA = {"version": 44, "itemTypes": [
    {"itemType": "journalArticle", "creatorTypes": AUTHORS,
     "fields": fields("title", "abstractNote", "publicationTitle", "publisher", "place", "date", "volume", "issue", "pages",
                      "journalAbbreviation", "DOI", "citationKey", "url", "ISSN", "libraryCatalog", "extra")},
    {"itemType": "conferencePaper", "creatorTypes": AUTHORS,
     "fields": fields("title", "abstractNote", "conferenceName", "publisher", "place", "date", "volume", "pages", "series",
                      "DOI", "ISBN", "citationKey", "url", "ISSN", "libraryCatalog", "extra",
                      proceedingsTitle="publicationTitle")},
    {"itemType": "bookSection", "creatorTypes": AUTHORS + [{"creatorType": "bookAuthor"}],
     "fields": fields("title", "abstractNote", "series", "volume", "date", "publisher", "place", "pages", "ISBN", "DOI",
                      "citationKey", "url", "ISSN", "libraryCatalog", "extra", bookTitle="publicationTitle")},
    {"itemType": "preprint", "creatorTypes": AUTHORS[:1] + AUTHORS[2:],
     "fields": fields("title", "abstractNote", "place", "date", "series", "DOI", "citationKey", "url", "libraryCatalog",
                      "extra", repository="publisher", archiveID="number")},
], "csl": {
    "types": {"article-journal": ["journalArticle"], "paper-conference": ["conferencePaper"], "article": ["preprint"],
              "chapter": ["bookSection"]},
    "fields": {"text": {"title": ["title"], "container-title": ["publicationTitle"], "volume": ["volume"], "issue": ["issue"],
                        "page": ["pages"], "DOI": ["DOI"], "URL": ["url"], "ISSN": ["ISSN"], "abstract": ["abstractNote"],
                        "publisher": ["publisher"], "event-title": ["conferenceName"], "publisher-place": ["place"]},
               "date": {"issued": "date", "accessed": "accessDate"}},
    "names": {"author": "author", "editor": "editor", "bookAuthor": "container-author", "contributor": "contributor"},
}}

JBHI, CVPR, DDPM, REFLEXION = "10.1109/JBHI.2022.3142076", "10.1109/CVPR.2016.90", "2006.11239", "2303.11366"
NEURIPS = "10.52202/075280-0377"
CSL = {
    JBHI: {"type": "journal-article", "source": "Crossref",
           "title": "Progressive Residual Learning With Memory Upgrade for Ultrasound Image Blind Super-Resolution",
           "author": [{"family": "Liu", "given": "Heng"}, {"family": "Liu", "given": "Jianyong"}],
           "issued": {"date-parts": [[2022, 9]]}, "container-title": "IEEE Journal of Biomedical and Health Informatics",
           "volume": "26", "issue": "9", "page": "4593-4604", "DOI": JBHI, "URL": "http://dx.doi.org/" + JBHI,
           "ISSN": ["2168-2194"], "abstract": "<jats:p>Ultrasound.</jats:p>"},
    CVPR: {"type": "proceedings-article", "source": "Crossref", "title": "Deep Residual Learning for Image Recognition",
           "author": [{"family": "He", "given": "Kaiming"}], "issued": {"date-parts": [[2016, 6]]},
           "container-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)",
           "event-title": "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)", "DOI": CVPR,
           "abstract": "Deeper networks."},
    "10.9999/twin": {"type": "journal-article", "source": "Crossref", "title": "Progressive Twin Paper",
                     "author": [{"family": "Liu", "given": "Wei"}], "issued": {"date-parts": [[2022]]}, "container-title": "J",
                     "DOI": "10.9999/twin", "abstract": "x"},
    "10.48550/arXiv." + DDPM: {"type": "article", "title": "Denoising Diffusion Probabilistic Models",
                               "author": [{"family": "Ho", "given": "Jonathan"}], "issued": {"date-parts": [[2020]]},
                               "DOI": "10.48550/ARXIV." + DDPM, "publisher": "arXiv", "abstract": "We present."},
    "10.1001/jama.2023.4855": {"type": "journal-article", "source": "Crossref", "title": "Randomized Trials vs Real-world Evidence",
                               "subtitle": ["How Can Both Inform Decision-making?"], "author": [{"family": "Fang", "given": "Lee"}],
                               "issued": {"date-parts": [[2023, 4]]}, "container-title": "JAMA", "page": "1645-1646",
                               "DOI": "10.1001/jama.2023.4855", "abstract": "x"},
    "10.48550/arXiv.2105.05537": {
        "type": "article", "title": "Swin-Unet: Unet-like Pure Transformer for Medical Image Segmentation",
        "author": [{"family": "Cao", "given": "Hu"}], "issued": {"date-parts": [[2021]]}, "DOI": "10.48550/ARXIV.2105.05537",
        "publisher": "arXiv", "abstract": "x",
        "categories": ["Image and Video Processing (eess.IV)", "Computer Vision and Pattern Recognition (cs.CV)",
                       "FOS: Electrical engineering, electronic engineering, information engineering",
                       "Machine Learning (stat.ML)", "Quantum Physics (quant-ph)", "Something New (zz.AB)",
                       "Computer Vision and Pattern Recognition (cs.CV)", "FOS: Computer and information sciences"]},
    "10.1001/jama.erratum": {"type": "journal-article", "source": "Crossref", "title": "Error in Author Name",
                             "issued": {"date-parts": [[2026, 9]]}, "container-title": "JAMA", "page": "804",
                             "DOI": "10.1001/jama.erratum"},
    "10.1001/jama.notice": {"type": "journal-article", "source": "Crossref", "title": "Author Correction: Diagnostics",
                            "author": [{"family": "Kim", "given": "Ana"}], "issued": {"date-parts": [[2025]]},
                            "container-title": "JAMA", "page": "1-2", "DOI": "10.1001/jama.notice", "abstract": "x"},
    "10.1007/978-3-319-24574-4_28": {
        "type": "book-chapter", "source": "Crossref", "title": "U-Net: Convolutional Networks for Biomedical Image Segmentation",
        "subtitle": [], "author": [{"family": "Ronneberger", "given": "Olaf"}], "issued": {"date-parts": [[2015]]},
        "container-title": "Lecture Notes in Computer Science", "ISSN": ["0302-9743", "1611-3349"],
        "ISBN": ["9783319245737", "9783319245744"], "page": "234-241", "publisher": "Springer International Publishing",
        "publisher-location": "Cham", "DOI": "10.1007/978-3-319-24574-4_28", "abstract": "x"},
    "10.1007/other-series": {"type": "book-chapter", "source": "Crossref", "title": "A Chapter In Some Series",
                             "author": [{"family": "Roe", "given": "Ann"}], "issued": {"date-parts": [[2020]]},
                             "container-title": "Some Book Series", "ISSN": ["1234-5678"], "page": "1-10",
                             "DOI": "10.1007/other-series", "abstract": "x"},
    "10.1007/crossref-down": {"type": "book-chapter", "source": "Crossref", "title": "A Chapter Whose Crossref Record Fails",
                              "author": [{"family": "Poe", "given": "Al"}], "issued": {"date-parts": [[2020]]},
                              "container-title": "Lecture Notes in Computer Science", "ISSN": ["0302-9743"], "page": "1-10",
                              "DOI": "10.1007/crossref-down", "abstract": "x"},
    "10.48550/arXiv." + REFLEXION: {
        "type": "article", "title": "Reflexion: Language Agents with Verbal Reinforcement Learning",
        "author": [{"family": "Shinn", "given": "Noah"}, {"family": "Cassano", "given": "Federico"}],
        "issued": {"date-parts": [[2023]]}, "DOI": "10.48550/ARXIV." + REFLEXION, "publisher": "arXiv", "abstract": "Reflexion.",
        "categories": ["Artificial Intelligence (cs.AI)"]},
    NEURIPS: {"type": "proceedings-article", "source": "Crossref",
              "title": "Reflexion: language agents with verbal reinforcement learning",
              "author": [{"family": "Shinn", "given": "Noah"}, {"family": "Cassano", "given": "Federico"}],
              "issued": {"date-parts": [[2023]]}, "container-title": "Advances in Neural Information Processing Systems 36",
              "page": "8634-8652", "DOI": NEURIPS, "URL": "https://doi.org/" + NEURIPS, "abstract": "Reflexion."},
    "10.1234/journal-version": {"type": "journal-article", "source": "Crossref", "title": "Verbal Reinforcement for Language Agents",
                                "author": [{"family": "Shinn", "given": "Noah"}], "issued": {"date-parts": [[2024, 5]]},
                                "container-title": "Journal of Agents", "page": "1-20", "DOI": "10.1234/journal-version",
                                "abstract": "Journal."},
    "10.48550/arXiv.2310.00001": {"type": "article", "title": "LabelDP-Pro: Learning with Label Differential Privacy via Projection",
                                  "author": [{"family": "Ghazi", "given": "Badih"}], "issued": {"date-parts": [[2023]]},
                                  "DOI": "10.48550/ARXIV.2310.00001", "publisher": "arXiv", "abstract": "Label DP."},
}

BIB = """\
@comment{this is ignored}
@string{ieee = "IEEE"}
@article{liuJBHI2022,
  title = {Progressive {Residual} Learning},
  author = {Liu, Heng},
  doi = {https://doi.org/10.1109/JBHI.2022.3142076},
  year = 2022
}
@misc{ho2020ddpm,
  title = "Denoising Diffusion Probabilistic Models",
  eprint = {2006.11239},
  archivePrefix = {arXiv},
  primaryClass = {cs.LG}
}
@inproceedings{he2016resnet,
  Title = {Deep Residual Learning for Image Recognition},
  booktitle = {CVPR},
  URL = {https://arxiv.org/abs/1512.03385v1}
}
@book{knuth1984,
  title = {The {TeX}book: A {Nested {Brace}} Title},
  publisher = ieee # " Press",
  note = "quoted with {braces, and} a comma"
}
"""


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web, cls.zot = FakeWeb(), FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.web.close()
        cls.zot.close()

    def setUp(self):
        w = self.web
        w.reset()
        self.zot.reset()
        self.zot.schema = SCHEMA
        for doi, csl in CSL.items():
            w.doi(doi, csl)
        w.doi("10.9999/html", None, landing="/landing")
        w.page("/landing", "A landing page")
        # Crossref's REST API: the LNCS volumes, the published versions a title search finds, and look-alikes.
        w.crossref("10.1007/978-3-319-24574-4_28", container_title=[
            "Lecture Notes in Computer Science", "Medical Image Computing and Computer-Assisted Intervention – MICCAI 2015"])
        w.crossref("10.1007/other-series", container_title=["Some Book Series", "A Volume of Some Book Series"])
        w.route("/crossref/works/10.1007/crossref-down", "upstream error", status=500)
        w.crossref(NEURIPS, type="proceedings-article", title="Reflexion: language agents with verbal reinforcement learning",
                   container_title="Advances in Neural Information Processing Systems 36", issued={"date-parts": [[2023]]})
        w.crossref("10.21203/rs.3.rs-1/v1", type="posted-content", title="Reflexion: Language Agents with Verbal Reinforcement Learning")
        w.crossref("10.48550/arXiv." + REFLEXION, type="proceedings-article", title="Reflexion: Language Agents with Verbal Reinforcement Learning")
        w.crossref("10.1109/isaics.2025.1", type="proceedings-article", title="Robust Verbal Reinforcement Learning for Language Agents",
                   container_title="ISAICS", issued={"date-parts": [[2025]]})
        w.crossref("10.1007/978-3-031-25066-8_9", type="book-chapter",
                   title="Swin-Unet: Unet-Like Pure Transformer for Medical Image Segmentation",
                   container_title=["Lecture Notes in Computer Science", "Computer Vision – ECCV 2022 Workshops"],
                   issued={"date-parts": [[2023]]})
        w.arxiv(REFLEXION, "Reflexion: Language Agents with Verbal Reinforcement Learning", version=4,
                comment="v4 contains a few additional experiments")
        w.arxiv("2105.05537", "Swin-Unet: Unet-like Pure Transformer for Medical Image Segmentation",
                journal_ref="ECCV 2022 Workshops", doi="10.1007/978-3-031-25066-8_9")
        w.arxiv("2310.00001", "LabelDP-Pro: Learning with Label Differential Privacy via Projection", comment="ICLR 2024")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-doi-"))
        self.work.records.mkdir()
        self.enterContext(mock.patch.dict(web.GAPS, {h: 0 for h in ("doi.org", "api.crossref.org", "export.arxiv.org", "127.0.0.1")}))

    def run_(self, *argv, base_url=None, env=None):
        return call(doi_to_item, *argv, "--base-url", base_url or self.zot.base_url, env={**self.web.env(), **(env or {})})

    def draft(self, *ids):
        """Draft identifiers into the work directory -> the result."""
        return self.run_(*[a for i in ids for a in ("--doi", i)], "--out-dir", self.work.records)

    def path(self, slug):
        return self.work.records / f"{slug}.json"

    def rec(self, slug):
        return json.loads(self.path(slug).read_text(encoding="utf-8"))

    def requested(self, prefix):
        return [r.path for r in self.web.requested("GET", prefix)]


class Drafting(Base):
    def test_identifiers_become_records_and_a_rerun_keeps_them(self):
        ids = self.work.root / "ids.txt"
        ids.write_text(f"# comment\n{JBHI}\tliu2022jbhi\n\n{CVPR}\narXiv:{DDPM}v2\n", encoding="utf-8")
        r = self.run_("--ids", ids, "--doi", "10.9999/twin", "--out-dir", self.work.records)
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["id"], o.get("cite"), o["code"], o["slug"]) for o in r.lines[:-1]],
                         [("10.9999/twin", None, "ok", "liu2022progressive"), (JBHI, "liu2022jbhi", "ok", "liu2022jbhi"),
                          (CVPR, None, "ok", "he2016deep"), (f"arXiv:{DDPM}v2", None, "ok", "ho2020denoising")])
        liu = self.rec("liu2022jbhi")
        self.assertEqual((liu["id"], liu["citationKey"]), (JBHI, "liu2022jbhi"))
        self.assertNotIn("slug", liu, "the file name is the slug")
        item = liu["item"]
        self.assertEqual(list(item)[:3], ["itemType", "title", "creators"])
        self.assertEqual((item["itemType"], item["DOI"], item["libraryCatalog"], item["url"], item["abstractNote"], item["creators"][0]),
                         ("journalArticle", JBHI, "DOI.org (Crossref)", "https://doi.org/" + JBHI, "Ultrasound.",
                          {"creatorType": "author", "firstName": "Heng", "lastName": "Liu"}))
        he = self.rec("he2016deep")["item"]
        self.assertEqual((he["itemType"], he["proceedingsTitle"]),
                         ("conferencePaper", "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)"))
        ho = self.rec("ho2020denoising")["item"]
        self.assertEqual((ho["itemType"], ho["archiveID"], ho["url"], ho["libraryCatalog"]),
                         ("preprint", f"arXiv:{DDPM}", f"https://arxiv.org/abs/{DDPM}v2", "DOI.org (Datacite)"))
        self.assertEqual(self.requested("/arxiv/*") + self.requested("/crossref/works"), [], "candidates are prepare's")
        # Rerun: what is there stays, even edited; a record is also known by its item's identifiers.
        liu["tags"] = [{"tag": "mine", "type": 0}]
        self.path("liu2022jbhi").write_text(json.dumps(liu), encoding="utf-8")
        self.path("byhand").write_text(json.dumps({"item": {"itemType": "journalArticle", "title": "x", "DOI": "10.1001/JAMA.2023.4855"}}))
        self.web.requests.clear()
        r = self.draft("doi:" + JBHI.lower(), "10.1001/jama.2023.4855", "10.9999/missing")
        self.assertEqual([(o["code"], o.get("reason"), o.get("slug")) for o in r.lines[:-1]],
                         [("skipped", "exists", "liu2022jbhi"), ("skipped", "exists", "byhand"), ("not_found", None, None)])
        self.assertEqual(self.rec("liu2022jbhi"), liu)
        self.assertEqual(self.requested("/doi/*"), ["/doi/10.9999/missing"])

    def test_failures_make_no_record(self):
        self.web.route("/doi/10.9999/broken", "upstream", status=503)
        r = self.draft("10.9999/missing", "10.9999/html", "not-an-id", "10.9999/broken", JBHI, "10.9999/twin", JBHI)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([o["code"] for o in r.lines[:-1]],
                         ["not_found", "no_csl_record", "no_identifier", "doi_org_error", "ok", "ok", "skipped"])
        self.assertTrue(all("hint" in o and "slug" not in o for o in r.lines[:4]))
        self.assertEqual([o.get("slug") for o in r.lines[4:7]], ["liu2022progressive", "liu2022progressive-2", "liu2022progressive"])
        self.assertEqual(r.lines[6]["reason"], "duplicate")
        self.assertEqual(sorted(p.name for p in self.work.records.iterdir()), ["liu2022progressive-2.json", "liu2022progressive.json"])
        rec = self.path("liu2022progressive")
        for argv in (["--doi", JBHI], ["--doi", JBHI, "--out-dir", self.work.records, rec], ["--redraft", NEURIPS, rec, rec],
                     ["--out-dir", self.work.records]):
            self.assertEqual(self.run_(*argv).code, 2, argv)

    def test_cannot_draft(self):
        r = self.run_("--doi", JBHI, "--doi", CVPR, "--out-dir", self.work.records, base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, [o["code"] for o in r.lines[:-1]]), (2, ["zotero_unreachable", "not_run"]))
        self.assertEqual(self.requested("/doi/*"), [], "the schema comes first")
        self.web.rate_limit("/doi/10.1109/JBHI*", retry_after=120)
        r = self.draft(JBHI, CVPR)
        self.assertEqual((r.code, [o["code"] for o in r.lines[:-1]], r.lines[-1]["summary"]["stopped"]),
                         (2, ["source_blocked", "not_run"], "source_blocked"))
        self.assertIn("until", r.lines[0])
        self.assertEqual(self.draft(CVPR).lines[0]["code"], "source_blocked", "the stop holds for the work directory's next run")
        self.assertNotIn("/doi/" + CVPR, self.requested("/doi/*"))
        (self.work.root / "pace.json").unlink()
        r = self.run_("--doi", CVPR, "--out-dir", self.work.records, env={"DOI_BASE_URL": f"http://127.0.0.1:{closed_port()}"})
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "doi_org_unreachable"))

    def test_a_bib_file(self):
        bib = self.work.root / "refs.bib"
        bib.write_text(BIB, encoding="utf-8")
        r = self.run_("--bib", bib, "--out-dir", self.work.records)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(o["id"], o["cite"], o["code"]) for o in r.lines[:-1]],
                         [(JBHI.lower(), "liuJBHI2022", "ok"), ("arXiv:2006.11239", "ho2020ddpm", "ok"),
                          ("arXiv:1512.03385v1", "he2016resnet", "not_found"),
                          ("The TeXbook: A Nested Brace Title", "knuth1984", "no_identifier")])
        self.assertEqual(sorted(p.name for p in self.work.records.iterdir()), ["ho2020ddpm.json", "liuJBHI2022.json"])

    def test_drafting_rules(self):
        self.path("shinn").write_text(json.dumps({"id": "arXiv:" + REFLEXION, "tags": [{"tag": "mine", "type": 0}]}))
        r = self.draft("10.1001/jama.2023.4855", "arXiv:2105.05537", REFLEXION, "10.1001/jama.erratum", "10.1001/jama.notice",
                       "10.1007/978-3-319-24574-4_28", "10.1007/other-series", "10.1007/crossref-down")
        self.assertEqual(r.code, 0, r)
        jama, swin, own, erratum, notice, unet, other, down = (self.rec(o["slug"]) for o in r.lines[:-1])
        self.assertEqual(jama["item"]["title"], "Randomized Trials vs Real-world Evidence: How Can Both Inform Decision-making?")
        self.assertEqual(swin["tags"], [{"tag": t, "type": 1} for t in (
            "Electrical Engineering and Systems Science - Image and Video Processing",
            "Computer Science - Computer Vision and Pattern Recognition", "Statistics - Machine Learning", "Quantum Physics",
            "Something New (zz.AB)")], "Zotero's arXiv translator's form; FOS entries and repeats dropped")
        self.assertEqual((own["tags"], r.lines[2]["slug"], own["item"]["itemType"]), ([{"tag": "mine", "type": 0}], "shinn", "preprint"),
                         "a record set up before drafting keeps its tags")
        self.assertNotIn("tags", jama)
        self.assertIn("no authors; single page '804'", " ".join(erratum["warnings"]))
        self.assertIn("title starts with 'Author Correction'", " ".join(notice["warnings"]))
        self.assertFalse(any("erratum" in w for w in jama.get("warnings", [])))
        item = unet["item"]
        self.assertEqual((item["itemType"], item["proceedingsTitle"], item["series"], item["ISBN"], item["place"]),
                         ("conferencePaper", "Medical Image Computing and Computer-Assisted Intervention – MICCAI 2015",
                          "Lecture Notes in Computer Science", "9783319245737, 9783319245744", "Cham"))
        self.assertEqual((other["item"]["itemType"], down["item"]["itemType"]), ("bookSection", "bookSection"))
        self.assertTrue(any('"A Volume of Some Book Series"' in w for w in other["warnings"]))
        self.assertTrue(any("Crossref lookup failed: HTTP 500" in w for w in down["warnings"]))
        self.assertEqual(len(self.requested("/crossref/works/*")), 3, "one Crossref call per chapter with an ISSN, none for articles")

    def test_smoke(self):
        r = smoke("doi_to_item", "--doi", CVPR, "--out-dir", self.work.records, "--base-url", self.zot.base_url, env=self.web.env())
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


class Candidates(Base):
    """A preprint record's published_candidates: what prepare runs doi_to_item for."""

    def preprint(self, aid):
        r = self.draft("arXiv:" + aid)
        self.assertEqual(r.code, 0, r)
        return self.path(r.lines[0]["slug"])

    def test_published_versions_of_preprints(self):
        reflexion, swin = self.preprint(REFLEXION), self.preprint("2105.05537")
        self.draft(CVPR)
        journal, empty = self.path("he2016deep"), self.path("empty")
        empty.write_text("{}")
        self.web.requests.clear()
        r = self.run_(reflexion, swin, journal, empty)
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(o["code"], o.get("reason"), o.get("candidates")) for o in r.lines[:4]],
                         [("ok", "absent", 1), ("ok", "absent", 1), ("skipped", "not_preprint", None), ("no_item", None, None)])
        self.assertEqual((r.lines[0]["comment"], r.lines[0]["sources"]),
                         ("v4 contains a few additional experiments", {"arxiv": "ok", "crossref": "ok"}))
        self.assertEqual(len(self.requested("/arxiv/api/query")), 1, "one arXiv call for all records")
        rec = run.read(reflexion)
        self.assertEqual(rec["published_candidates"]["items"], [{
            "doi": NEURIPS, "venue": "Advances in Neural Information Processing Systems 36", "year": 2023,
            "title": "Reflexion: language agents with verbal reinforcement learning", "url": "https://doi.org/" + NEURIPS,
            "sources": ["crossref"], "title_differs": False, "type": "proceedings-article"}],
            "posted-content, arXiv's own DOI and a dissimilar title are left out")
        self.assertEqual(rec["item"]["itemType"], "preprint", "the item is never changed")
        self.assertEqual(rec["published_candidates"]["arxiv_version"], "v4", "the latest version, for the file's title")
        self.assertEqual(run.read(swin)["published_candidates"]["items"], [{
            "doi": "10.1007/978-3-031-25066-8_9", "venue": "Computer Vision – ECCV 2022 Workshops", "year": 2023,
            "title": "Swin-Unet: Unet-Like Pure Transformer for Medical Image Segmentation",
            "url": "https://doi.org/10.1007/978-3-031-25066-8_9", "sources": ["arxiv", "crossref"], "title_differs": False,
            "type": "book-chapter", "journal_ref": "ECCV 2022 Workshops"}], "the DOI arXiv declares, completed from Crossref")
        # Done until its inputs change.
        self.web.requests.clear()
        self.assertEqual([o["reason"] for o in self.run_(reflexion, swin).lines[:2]], ["done", "done"])
        self.assertEqual(self.web.requests, [])
        rec["item"]["title"] = "Reflexion: Language Agents"
        rec.save()
        self.assertEqual(self.run_(reflexion).lines[0]["reason"], "stale")

    def test_sources_that_do_not_answer(self):
        swin, reflexion = self.preprint("2105.05537"), self.preprint(REFLEXION)
        rec = run.read(swin)
        old = {"doi": "10.1007/978-3-031-25066-8_9", "venue": "ECCV 2022 Workshops", "year": 2023, "title": None,
               "url": "https://doi.org/10.1007/978-3-031-25066-8_9", "sources": ["arxiv"], "title_differs": None,
               "journal_ref": "ECCV 2022 Workshops"}
        run.stamp(rec, "published_candidates", {"items": [old], "comment": "before"}, incomplete=["crossref"])
        rec.save()
        self.web.route("/arxiv/api/query", "busy", status=503)
        r = self.run_(swin)
        self.assertEqual((r.code, r.lines[0]["reason"], r.lines[0]["sources"]), (0, "incomplete", {"arxiv": "http_503", "crossref": "ok"}))
        block = run.read(swin)["published_candidates"]
        self.assertEqual((block["incomplete"], block["comment"]), (["arxiv"], "before"))
        self.assertEqual([(c["sources"], c["journal_ref"], c["venue"]) for c in block["items"]],
                         [(["arxiv", "crossref"], "ECCV 2022 Workshops", "Computer Vision \u2013 ECCV 2022 Workshops")],
                         "what the silent source gave before stays, completed from Crossref's answer")
        self.web.rate_limit("/crossref/works", retry_after=120)
        r = self.run_(swin, reflexion)
        self.assertEqual((r.code, [o["code"] for o in r.lines[:2]]), (1, ["no_answer", "no_answer"]))
        self.assertEqual(r.lines[1]["sources"]["crossref"], "source_blocked")
        self.assertEqual(len(self.requested("/crossref/works")), 2, "after its 429 Crossref is not asked again")
        self.assertEqual(run.read(reflexion)["published_candidates"]["incomplete"], ["arxiv", "crossref"])


class Redraft(Base):
    def preprint(self, aid=REFLEXION, **extra):
        """A drafted, prepared preprint record with the agent's fields."""
        path = self.path(self.draft("arXiv:" + aid).lines[0]["slug"])
        rec = run.read(path)
        rec.update({"citationKey": "shinn2023reflexion", "tags": [{"tag": "mine", "type": 0}], "collection": ["AAA"], **extra})
        for block in ("found", "links", "checks"):
            run.stamp(rec, block, {"code": "x"})
        rec.save()
        self.assertEqual(self.run_(path).code, 0)
        return path, run.read(path)

    def test_by_doi(self):
        self.web.doi(NEURIPS, {k: v for k, v in CSL[NEURIPS].items() if k != "abstract"})
        path, before = self.preprint(alt_titles=["An Earlier Title"])
        r = self.run_("--redraft", NEURIPS, path)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["itemType"]), (0, "ok", "conferencePaper"), r)
        rec = run.read(path)
        self.assertEqual({k: rec[k] for k in ("id", "citationKey", "tags", "collection", "links")},
                         {k: before[k] for k in ("id", "citationKey", "tags", "collection", "links")})
        self.assertEqual((rec.item["DOI"], rec.item["extra"], rec.item["abstractNote"]), (NEURIPS, f"arXiv: {REFLEXION}", "Reflexion."))
        self.assertIn("the DOI record has no abstract: the preprint's is kept", rec["warnings"])
        self.assertTrue(any("sales page" in w for w in rec["warnings"]))
        self.assertEqual(rec["alt_titles"], ["An Earlier Title"], "the same title up to case: nothing added")
        self.assertEqual([run.due(rec, b) for b in ("found", "links", "checks")], ["stale"] * 3, "the next prepare redoes them")
        self.assertEqual(self.run_(path).lines[0]["reason"], "not_preprint")
        self.assertNotIn("published_candidates", run.read(path))
        self.assertEqual(self.run_("--redraft", "doi:" + NEURIPS, path).lines[0]["reason"], "same_doi")
        self.run_("--redraft", "https://doi.org/10.1234/journal-version", path)
        self.assertEqual(run.read(path)["alt_titles"], ["An Earlier Title", "Reflexion: language agents with verbal reinforcement learning"])
        # Refused: an item already in Zotero (or being created), the preprint's own DOI, an unknown DOI.
        saved, _ = self.preprint("2310.00001", saved={"pending": True, "at": "2026-10-20T00:00:00Z"})
        self.assertEqual(self.run_("--redraft", NEURIPS, saved).lines[0]["code"], "already_saved")
        for target, code in (("10.48550/arXiv." + REFLEXION, "not_published"), ("10.9999/missing", "not_found")):
            r = self.run_("--redraft", target, path)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code), target)

    def test_by_the_papers_page(self):
        neurips = self.web.page("/paper/neurips", "Reflexion", meta={
            "citation_title": "Reflexion: Language Agents with Verbal Reinforcement Learning",
            "citation_author": ["Shinn, Noah", "Cassano, Federico"],
            "citation_journal_title": "Advances in Neural Information Processing Systems", "citation_volume": "36",
            "citation_firstpage": "8634", "citation_lastpage": "8652", "citation_publication_date": "2023/12/15",
            "citation_pdf_url": "/paper_files/1b44-Paper-Conference.pdf"})
        path, before = self.preprint()
        r = self.run_("--redraft", neurips, path)
        self.assertEqual((r.code, r.lines[0]["itemType"], r.lines[0]["url"]), (0, "conferencePaper", neurips), r)
        rec = run.read(path)
        self.assertEqual({k: rec.item.get(k) for k in ("proceedingsTitle", "pages", "date", "extra", "abstractNote")},
                         {"proceedingsTitle": "Advances in Neural Information Processing Systems", "pages": "8634-8652",
                          "date": "2023-12-15", "extra": f"arXiv: {REFLEXION}", "abstractNote": "Reflexion."})
        self.assertEqual(rec.item["creators"], [{"creatorType": "author", "firstName": "Noah", "lastName": "Shinn"},
                                                {"creatorType": "author", "firstName": "Federico", "lastName": "Cassano"}])
        self.assertEqual(rec["links"], before["links"], "the page's PDF is fulltext_links' to list")
        tmlr = self.web.page("/paper/tmlr", "", meta={
            "citation_title": "A Journal Paper on Agents", "citation_author": "Ada Lovelace",
            "citation_journal_title": "Transactions on Machine Learning Research", "citation_publication_date": "2024",
            "description": "An abstract from the description tag."})
        path, _ = self.preprint("2310.00001")
        rec = run.read(path)
        rec["item"].pop("abstractNote")
        rec.save()
        self.run_("--redraft", tmlr, path)
        item = run.read(path).item
        self.assertEqual((item["itemType"], item["publicationTitle"], item["abstractNote"]),
                         ("journalArticle", "Transactions on Machine Learning Research", "An abstract from the description tag."))
        for url, code in ((self.web.page("/paper/bare", "Just a page"), "no_citation_meta"),
                          (self.web.url("/paper/missing"), "page_unreachable")):
            r = self.run_("--redraft", url, path)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code), url)


if __name__ == "__main__":
    unittest.main()
