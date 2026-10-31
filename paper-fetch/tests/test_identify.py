# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/identify.py: result files from identifiers and pages, the CSL's normalization, a preprint's
versions, --redraft and --search, against the fake web (doi.org, Crossref, arXiv's API, venue pages)."""
import json
import tempfile
import unittest
from unittest import mock

from fake_web import FakeWeb
from helpers import call, closed_port, load, smoke
from pflib import run, web

identify = load("identify")

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



class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = FakeWeb()

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        w = self.web
        w.reset()
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
        self.work = run.Work(tempfile.mkdtemp(prefix="pf-identify-"))
        self.enterContext(mock.patch.dict(web.GAPS, {h: 0 for h in ("doi.org", "api.crossref.org", "export.arxiv.org", "127.0.0.1")}))

    def run_(self, *argv, stdin="", env=None):
        return call(identify, *argv, env={**self.web.env(), **(env or {})}, stdin=stdin)

    def ident(self, *ids, stdin=""):
        return self.run_(*ids, "-o", self.work.root, stdin=stdin)

    def path(self, slug):
        return self.work.results / f"{slug}.json"

    def res(self, slug):
        return json.loads(self.path(slug).read_text(encoding="utf-8"))

    def requested(self, prefix):
        return [r.path for r in self.web.requested("GET", prefix)]


class Identifying(Base):
    def test_identifiers_become_results_and_a_rerun_keeps_them(self):
        r = self.ident(stdin=f"# comment\n{JBHI}\tliu2022jbhi\n\n{CVPR}\narXiv:{DDPM}v2\n10.9999/twin\n")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["id"], o["code"], o["slug"], o["record_of"]) for o in r.lines[:-1]],
                         [(JBHI, "ok", "liu2022jbhi", "published"), (CVPR, "ok", "he2016deep", "published"),
                          (f"arXiv:{DDPM}v2", "ok", "ho2020denoising", "preprint"),
                          ("10.9999/twin", "ok", "liu2022progressive", "published")])
        liu = self.res("liu2022jbhi")
        self.assertEqual((liu["slug"], liu["slug_given"], liu["request"], liu["record_of"]),
                         ("liu2022jbhi", True, {"given": JBHI}, "published"))
        self.assertEqual(liu["ids"], {"doi": JBHI, "arxiv": None, "pmid": None, "pmcid": None})
        self.assertEqual({k: liu["csl"][k] for k in ("type", "source", "abstract", "container-title")},
                         {"type": "article-journal", "source": "DOI.org (Crossref)", "abstract": "Ultrasound.",
                          "container-title": "IEEE Journal of Biomedical and Health Informatics"})
        self.assertEqual(liu["versions"], {"published": [], "incomplete": []})
        self.assertNotIn("files", liu, "files and outcome are the fold's")
        self.assertEqual(self.res("he2016deep")["csl"]["type"], "paper-conference")
        ho = self.res("ho2020denoising")
        self.assertEqual((ho["ids"]["arxiv"], ho["ids"]["doi"], ho["csl"]["type"], ho["csl"]["source"]),
                         (DDPM, "10.48550/arXiv." + DDPM, "article", "DOI.org (Datacite)"))
        self.assertEqual(ho["versions"]["preprint"]["ids"], {"arxiv": DDPM, "doi": "10.48550/arXiv." + DDPM})
        self.web.requests.clear()
        r = self.ident("doi:" + JBHI.lower(), DDPM, "10.9999/missing")
        self.assertEqual([(o["code"], o.get("reason"), o.get("slug")) for o in r.lines[:-1]],
                         [("skipped", "exists", "liu2022jbhi"), ("skipped", "exists", "ho2020denoising"),
                          ("not_found", None, None)])
        self.assertEqual(self.requested("/doi/*"), ["/doi/10.9999/missing"])

    def test_slugs(self):
        self.assertEqual(self.ident(JBHI, "--slug", "mine").lines[0]["slug"], "mine")
        r = self.ident("10.9999/twin", "--slug", "mine")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "slug_taken"))
        r = self.ident("10.9999/twin", JBHI)
        self.assertEqual([(o["code"], o.get("slug")) for o in r.lines[:-1]],
                         [("ok", "liu2022progressive"), ("skipped", "mine")])
        self.assertEqual([o["reason"] for o in self.ident(stdin=f"{JBHI}\n{JBHI}\n").lines[:2]], ["exists", "duplicate"])
        # A key brought later (a .bib after a bare id): the result takes it while nothing was fetched under the old name.
        self.assertEqual(self.ident(CVPR).lines[0]["slug"], "he2016deep")
        r = self.ident(stdin=f"{CVPR}\the2016resnet\n")
        self.assertEqual((r.lines[0]["code"], r.lines[0]["slug"], r.lines[0]["renamed_from"]), ("ok", "he2016resnet", "he2016deep"))
        self.assertEqual((self.res("he2016resnet")["slug_given"], self.path("he2016deep").exists()), (True, False))
        self.work.append({"event": "pass", "pass": 1, "slug": "he2016resnet"})
        r = self.ident(stdin=f"{CVPR}\thekaiming2016\n")
        self.assertEqual((r.lines[0]["reason"], r.lines[0]["slug"], r.lines[0]["slug_not_applied"]),
                         ("exists", "he2016resnet", "hekaiming2016"), "the result has its key already: the other one is reported, not applied")
        self.work.append({"event": "pass", "pass": 1, "slug": "liu2022progressive"})  # 10.9999/twin, fetched for
        r = self.ident(stdin="10.9999/twin\tliutwin\n")
        self.assertEqual((r.lines[0]["slug"], r.lines[0]["slug_not_applied"]), ("liu2022progressive", "liutwin"),
                         "fetching began under the old name: the key is reported, the name stays")

    def test_failures_stubs_and_titles(self):
        self.web.route("/doi/10.9999/broken", "upstream", status=503)
        r = self.ident(stdin="10.9999/missing\n10.9999/html\nnot-an-id\n10.9999/broken\ntitle: Some Paper\n")
        self.assertEqual(r.code, 1, r)
        self.assertEqual([o["code"] for o in r.lines[:-1]],
                         ["not_found", "no_csl_record", "no_identifier", "doi_org_error", "needs_pinning"])
        stub = r.lines[1]
        self.assertTrue(stub["stub"])
        self.assertEqual(self.res(stub["slug"]), {"slug": stub["slug"], "slug_given": False,
                                                  "request": {"given": "10.9999/html"}, "warnings": ["no_csl_record"]})
        self.assertEqual(sorted(p.name for p in self.work.results.iterdir()), [stub["slug"] + ".json"])
        self.web.doi("10.9999/html", CSL["10.9999/twin"])
        r = self.ident("10.9999/html")
        self.assertEqual((r.lines[0]["code"], r.lines[0]["slug"]), ("ok", stub["slug"]), "a stub is identified again in place")

    def test_cannot_go_on(self):
        self.web.rate_limit("/doi/10.1109/JBHI*", retry_after=120)
        r = self.ident(JBHI, CVPR)
        self.assertEqual((r.code, [o["code"] for o in r.lines[:-1]], r.lines[-1]["summary"]["stopped"]),
                         (2, ["source_blocked", "not_run"], "source_blocked"))
        self.assertEqual(self.ident(CVPR).lines[0]["code"], "source_blocked", "the stop holds for the directory's next run")
        (self.work.root / "pace.json").unlink()
        r = self.run_(CVPR, "-o", self.work.root, env={"DOI_BASE_URL": f"http://127.0.0.1:{closed_port()}"})
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "doi_org_unreachable"))
        for argv in (["--slug", "x", JBHI, CVPR], ["--author", "Liu"], [JBHI, "--search", "x"]):
            self.assertEqual(self.run_(*argv).code, 2, argv)

    def test_normalization(self):
        self.web.doi("10.9999/crossref-keys", {"type": "proceedings-article", "source": "Crossref", "title": "Crossref Keys",
                                               "author": [{"family": "Doe", "given": "Jo"}], "event": {"name": "Conf"},
                                               "publisher-location": "Cham", "short-container-title": ["J. Ab."],
                                               "published-online": {"date-parts": [[2021, 5, 3]]}, "DOI": "10.9999/crossref-keys",
                                               "reference": [{"key": "ref1"}], "score": 1, "abstract": "x"})
        r = self.ident("10.1001/jama.2023.4855", "arXiv:2105.05537", "10.1001/jama.erratum", "10.1001/jama.notice",
                       "10.1007/978-3-319-24574-4_28", "10.1007/other-series", "10.1007/crossref-down", "10.9999/crossref-keys")
        self.assertEqual(r.code, 0, r)
        jama, swin, erratum, notice, unet, other, down, keys = (self.res(o["slug"]) for o in r.lines[:-1])
        self.assertEqual(jama["csl"]["title"], "Randomized Trials vs Real-world Evidence: How Can Both Inform Decision-making?")
        self.assertNotIn("subtitle", jama["csl"])
        self.assertEqual(swin["csl"]["categories"][0], "Image and Video Processing (eess.IV)", "categories pass by name")
        self.assertIn("no authors; single page '804'", " ".join(erratum["warnings"]))
        self.assertIn("title starts with 'Author Correction'", " ".join(notice["warnings"]))
        self.assertFalse(any("erratum" in w for w in jama["warnings"]))
        self.assertEqual({k: unet["csl"].get(k) for k in ("type", "container-title", "collection-title", "publisher-place")},
                         {"type": "paper-conference", "container-title": "Medical Image Computing and Computer-Assisted "
                          "Intervention – MICCAI 2015", "collection-title": "Lecture Notes in Computer Science",
                          "publisher-place": "Cham"})
        self.assertEqual((other["csl"]["type"], down["csl"]["type"]), ("chapter", "chapter"))
        self.assertTrue(any('"A Volume of Some Book Series"' in w for w in other["warnings"]))
        self.assertTrue(any("Crossref lookup failed: HTTP 500" in w for w in down["warnings"]))
        self.assertEqual(len(self.requested("/crossref/works/*")), 3, "one Crossref call per chapter with an ISSN, none for articles")
        csl = keys["csl"]
        self.assertEqual({k: csl.get(k) for k in ("type", "event-title", "publisher-place", "container-title-short", "issued")},
                         {"type": "paper-conference", "event-title": None, "publisher-place": "Cham",
                          "container-title-short": ["J. Ab."], "issued": {"date-parts": [[2021, 5, 3]]}})
        self.assertNotIn("reference", csl)
        self.assertNotIn("score", csl)
        self.assertIn("date taken from 'published-online' (no usable 'issued')", keys["warnings"])

    def test_smoke(self):
        r = smoke("identify", CVPR, "-o", self.work.root, env=self.web.env())
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


class Versions(Base):
    def test_published_versions_of_preprints(self):
        r = self.ident(REFLEXION, "2105.05537", CVPR)
        self.assertEqual([o.get("versions") for o in r.lines[:-1]], [1, 1, None])
        reflexion = self.res("shinn2023reflexion")["versions"]
        self.assertEqual((reflexion["preprint"]["latest"], reflexion["preprint"]["comment"], reflexion["incomplete"]),
                         ("v4", "v4 contains a few additional experiments", []))
        self.assertEqual(reflexion["published"], [{
            "ids": {"doi": NEURIPS}, "venue": "Advances in Neural Information Processing Systems 36", "year": 2023,
            "title": "Reflexion: language agents with verbal reinforcement learning", "title_differs": False,
            "type": "paper-conference", "sources": ["crossref"]}], "posted-content, arXiv's own DOI and a dissimilar title are left out")
        self.assertEqual(self.res("cao2021swin")["versions"]["published"], [{
            "ids": {"doi": "10.1007/978-3-031-25066-8_9"}, "venue": "Computer Vision – ECCV 2022 Workshops", "year": 2023,
            "title": "Swin-Unet: Unet-Like Pure Transformer for Medical Image Segmentation", "title_differs": False,
            "type": "chapter", "sources": ["arxiv", "crossref"], "journal_ref": "ECCV 2022 Workshops"}],
            "the DOI arXiv declares, completed from Crossref")

    def test_sources_that_do_not_answer_are_asked_again(self):
        self.web.route("/arxiv/api/query", "busy", status=503, times=1)
        r = self.ident(REFLEXION)
        self.assertEqual(r.lines[0]["incomplete"], ["arxiv"])
        r = self.ident(REFLEXION)
        self.assertEqual((r.lines[0]["code"], r.lines[0].get("incomplete")), ("ok", None), "asked again, now complete")
        self.assertEqual(self.ident(REFLEXION).lines[0]["reason"], "exists")

    def test_a_redraft_is_never_undone(self):
        self.web.route("/arxiv/api/query", "busy", status=503, times=1)
        self.ident(REFLEXION)
        path = self.path("shinn2023reflexion")
        self.assertEqual(self.run_("--redraft", NEURIPS, path).lines[0]["code"], "ok")
        self.assertEqual(self.res("shinn2023reflexion")["versions"]["incomplete"], ["arxiv"])
        self.assertEqual(self.ident(REFLEXION).lines[0]["reason"], "exists", "its version is chosen: not asked again")
        self.assertEqual(self.res("shinn2023reflexion")["record_of"], "published")


class Redraft(Base):
    def test_by_doi(self):
        self.web.doi(NEURIPS, {k: v for k, v in CSL[NEURIPS].items() if k != "abstract"})
        self.ident(REFLEXION)
        path = self.path("shinn2023reflexion")
        res = run.read(path)
        res.update(alt_titles=["An Earlier Title"], files=[{"name": "x.preprint.pdf"}], outcome={"status": "got"})
        res.save()
        r = self.run_("--redraft", NEURIPS, path)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        res = self.res("shinn2023reflexion")
        self.assertEqual((res["record_of"], res["ids"]["doi"], res["ids"]["arxiv"], res["csl"]["type"]),
                         ("published", NEURIPS, None, "paper-conference"))
        self.assertEqual(res["versions"]["preprint"]["ids"]["arxiv"], REFLEXION)
        self.assertEqual(res["versions"]["preprint"]["abstract"], "Reflexion.")
        self.assertEqual(res["versions"]["preprint"]["categories"], ["Artificial Intelligence (cs.AI)"],
                         "the preprint's arXiv categories stay for the item's tags")
        self.assertEqual((res["files"], res["outcome"]), ([{"name": "x.preprint.pdf"}], {"status": "got"}), "files got stay")
        self.assertIn("the published record has no abstract; the preprint's is in versions.preprint", res["warnings"])
        self.assertTrue(any("sales page" in w for w in res["warnings"]))
        self.assertEqual(res["alt_titles"], ["An Earlier Title"], "the same title up to case: nothing added")
        self.assertEqual(res["request"], {"given": REFLEXION, "redraft": NEURIPS})
        self.assertEqual(self.run_("--redraft", "doi:" + NEURIPS, path).lines[0]["reason"], "same_doi")
        self.run_("--redraft", "https://doi.org/10.1234/journal-version", path)
        self.assertEqual(self.res("shinn2023reflexion")["alt_titles"],
                         ["An Earlier Title", "Reflexion: language agents with verbal reinforcement learning"])
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
        self.ident(REFLEXION)
        path = self.path("shinn2023reflexion")
        r = self.run_("--redraft", neurips, path)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        csl = self.res("shinn2023reflexion")["csl"]
        self.assertEqual({k: csl.get(k) for k in ("type", "container-title", "page", "issued", "URL", "source", "author")},
                         {"type": "paper-conference", "container-title": "Advances in Neural Information Processing Systems",
                          "page": "8634-8652", "issued": {"date-parts": [[2023, 12, 15]]}, "URL": neurips,
                          "source": "127.0.0.1", "author": [{"family": "Shinn", "given": "Noah"},
                                                            {"family": "Cassano", "given": "Federico"}]})
        for url, code in ((self.web.page("/paper/bare", "Just a page"), "no_citation_meta"),
                          (self.web.url("/paper/missing"), "page_unreachable")):
            r = self.run_("--redraft", url, path)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code), url)

    def test_a_page_identified_directly(self):
        page = self.web.page("/paper/tmlr", "", meta={
            "citation_title": "A Journal Paper on Agents", "citation_author": "Ada Lovelace",
            "citation_journal_title": "Transactions on Machine Learning Research", "citation_publication_date": "2024"})
        r = self.ident(page)
        self.assertEqual((r.code, r.lines[0]["slug"], r.lines[0]["record_of"]), (0, "lovelace2024journal", "published"), r)
        res = self.res("lovelace2024journal")
        self.assertEqual((res["csl"]["type"], res["ids"]["doi"]), ("article-journal", None))
        r = self.ident(self.web.page("/paper/bare", "Just a page"))
        self.assertEqual((r.lines[0]["code"], r.lines[0]["stub"]), ("no_citation_meta", True))


class Search(Base):
    def test_title_search(self):
        r = self.run_("--search", "Reflexion: Language Agents with Verbal Reinforcement Learning", "--author", "Shinn")
        self.assertEqual(r.code, 0, r)
        self.assertIn(NEURIPS, [o["doi"] for o in r.lines[:-1]])
        self.assertEqual(r.lines[-1]["summary"]["query"], "Reflexion: Language Agents with Verbal Reinforcement Learning")


if __name__ == "__main__":
    unittest.main()
