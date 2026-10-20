# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fulltext_links.py against the fake web's OpenAlex, Europe PMC and venue pages."""
import json
import tempfile
import unittest
from unittest import mock

from helpers import call, config_file, load, smoke
from fake_web import FakeWeb, full_text_url, location

from p2zlib import run, web

links = load("fulltext_links")
KEY = "sk-TEST-openalex-SECRET-0042"
PUB_PDF = "https://www.publisher.example/articles/nat-1.pdf"


class FulltextLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = FakeWeb()

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        w = self.web
        w.reset()
        w.openalex("10.1000/nat.1", [
            location(PUB_PDF, "https://doi.org/10.1000/nat.1", "publishedVersion"),
            location(None, "https://pubmed.ncbi.nlm.nih.gov/456", "publishedVersion", is_oa=False, source_type="repository"),
            location("https://arxiv.org/pdf/2212.00001", "http://arxiv.org/abs/2212.00001", "submittedVersion", source_type="repository"),
            location("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/nat.pdf", "https://www.ncbi.nlm.nih.gov/pmc/articles/123",
                     "submittedVersion", source_type="repository"),
            location(None, "https://doi.org/10.5281/zenodo.1", None, source_type="repository")])
        w.europepmc("10.1000/nat.1", [full_text_url("S", "doi", "DOI", "https://doi.org/10.1000/nat.1"),
                                      full_text_url("OA", "html", "Europe_PMC", "https://europepmc.org/articles/PMC123"),
                                      full_text_url("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC123?pdf=render")],
                    pmcid="PMC123")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-links-"))
        self.work.records.mkdir()
        self.config = config_file(self.work.root, openalex_key=KEY)
        self.enterContext(mock.patch.dict(web.GAPS, {"api.openalex.org": 0, "www.ebi.ac.uk": 0, "127.0.0.1": 0}))

    def record(self, slug, doi=None, **item):
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps({"item": {"itemType": "journalArticle", "title": f"Title of {slug}",
                                             **({"DOI": doi} if doi else {}), **item}}), encoding="utf-8")
        return path

    def run_(self, *argv, config=None):
        return call(links, *argv, config=config or self.config, env=self.web.env())

    def items(self, path):
        return [(link["url"], link["version"]) for link in run.read(path)["links"]["items"]]

    def test_every_source_one_link_per_url_by_version(self):
        path = self.record("nat", "10.1000/nat.1", extra="arXiv: 2212.00001")
        r = self.run_(path)
        self.assertEqual(r.code, 0, r)
        got = run.read(path)["links"]["items"]
        self.assertEqual([(x["url"], x["source"], x["version"], x["needs_browser"]) for x in got], [
            (PUB_PDF, "openalex", "published", None),
            ("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/nat.pdf", "openalex", "published", True),
            ("https://europepmc.org/articles/PMC123?pdf=render", "europepmc", "published", True),
            ("https://arxiv.org/pdf/2212.00001", "arxiv", "preprint", False),
            ("https://doi.org/10.5281/zenodo.1", "openalex", "unknown", None)],
            "PMC copies take Europe PMC's word; an arXiv copy is a preprint; a repository location is unknown")
        line = r.lines[0]
        self.assertEqual((line["code"], line["reason"], line["links"]), ("ok", "absent", 5))
        self.assertEqual(line["sources"], {"arxiv": "ok", "openalex": "ok", "europepmc": "ok", "page": "no_identifier"})
        self.assertEqual(line["first"], {"version": "published", "needs_browser": None, "host": "www.publisher.example"})

    def test_the_key_goes_as_a_parameter_and_is_never_printed(self):
        path = self.record("nat", "10.1000/nat.1")
        r = self.run_(path)
        self.assertEqual(self.web.requested("GET", "/openalex/*")[0].query, {"api_key": KEY})
        self.assertNotIn(KEY, r.out + r.err)
        self.web.requests.clear()
        self.run_(self.record("nat2", "10.1000/nat.1"), config=config_file())
        self.assertEqual(self.web.requested("GET", "/openalex/*")[0].query, {}, "no key: unkeyed, nothing else sent")

    def test_closed_paper_and_accepted_label(self):
        self.web.openalex("10.1000/closed.5", [location(None, "https://doi.org/10.1000/closed.5", "publishedVersion", is_oa=False)])
        self.web.openalex("10.1000/acc.6", [location("https://repo.example.edu/acc.pdf", None, "acceptedVersion")])
        closed, acc = self.record("closed", "10.1000/closed.5"), self.record("acc", "10.1000/acc.6")
        self.run_(closed, acc)
        self.assertEqual(self.items(closed), [], "answered with nothing open: an empty list, done")
        self.assertIsNone(run.due(run.read(closed), "links"))
        self.assertEqual(self.items(acc), [("https://repo.example.edu/acc.pdf", "accepted")])

    def test_europepmc_versions_and_the_pmc_page(self):
        w = self.web
        w.europepmc("10.1000/jno.2", [full_text_url("F", "doi", "DOI", "https://doi.org/10.1000/jno.2")], pmcid="PMC777")
        w.europepmc("10.1000/am.3", [full_text_url("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC333?pdf=render"),
                                     full_text_url("OA", "html", "Unpaywall", "https://hal.example.org/hal-333")],
                    pmcid="PMC333", authMan="Y")
        w.europepmc("10.1000/ppr.7", [full_text_url("OA", "doi", "DOI", "https://doi.org/10.1000/ppr.7")], source="PPR")
        jno, am, ppr = (self.record(s, d) for s, d in (("jno", "10.1000/jno.2"), ("am", "10.1000/am.3"), ("ppr", "10.1000/ppr.7")))
        self.run_(jno, am, ppr)
        self.assertEqual(self.items(jno), [("https://doi.org/10.1000/jno.2", "published"),
                                           ("https://pmc.ncbi.nlm.nih.gov/articles/PMC777/", "published")],
                         "in PMC without a PMC link: its article page is added")
        self.assertEqual(self.items(am), [("https://europepmc.org/articles/PMC333?pdf=render", "accepted"),
                                          ("https://pmc.ncbi.nlm.nih.gov/articles/PMC333/", "accepted"),
                                          ("https://hal.example.org/hal-333", "unknown")])
        self.assertEqual(self.items(ppr), [("https://doi.org/10.1000/ppr.7", "preprint")])

    def test_an_arxiv_record_needs_no_request(self):
        path = self.record("ddpm", "10.48550/arXiv.2006.11239", itemType="preprint", url="https://arxiv.org/abs/2006.11239")
        r = self.run_(path)
        self.assertEqual(self.items(path), [("https://arxiv.org/pdf/2006.11239", "preprint")])
        self.assertEqual(r.lines[0]["sources"], {"arxiv": "ok", "openalex": "no_identifier", "europepmc": "no_identifier",
                                                 "page": "no_identifier"})
        self.assertEqual(self.web.requests, [])

    def test_a_venue_page_gives_its_pdf(self):
        self.web.page("/paper/42.html", "A NeurIPS paper", meta={"citation_title": "A NeurIPS paper",
                                                                "citation_pdf_url": "/paper/42.pdf"})
        path = self.record("nips", None, itemType="conferencePaper", url=self.web.url("/paper/42.html"))
        r = self.run_(path)
        self.assertEqual(self.items(path), [(self.web.url("/paper/42.pdf"), "published")])
        self.assertEqual(r.lines[0]["sources"]["page"], "ok")
        self.web.route("/paper/43.html", "no", status=403)
        r = self.run_(self.record("shut", None, itemType="conferencePaper", url=self.web.url("/paper/43.html")))
        self.assertEqual((r.lines[0]["code"], r.lines[0]["sources"]["page"]), ("ok", "refused"), "an answer, not incomplete")

    def test_done_stale_and_incomplete(self):
        path = self.record("nat", "10.1000/nat.1")
        self.run_(path)
        self.web.requests.clear()
        r = self.run_(path)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"]), ("skipped", "done"))
        self.assertEqual(self.web.requests, [])
        rec = run.read(path)
        rec["tags"] = [{"tag": "x", "type": 0}]
        rec.save()
        self.assertEqual(self.run_(path).lines[0]["code"], "skipped", "tags are no input of links")
        self.web.route("/epmc/*", status=503)
        rec = run.read(path)
        rec["item"]["url"] = "https://doi.org/10.1000/nat.1"
        rec.save()
        r = self.run_(path)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["sources"]["europepmc"]), ("ok", "stale", "http_503"))
        rec = run.read(path)
        self.assertEqual(rec["links"]["incomplete"], ["europepmc"])
        self.assertNotIn("europepmc", {x["source"] for x in rec["links"]["items"]}, "stale: last time's links are gone")
        self.web.reset()
        self.web.openalex("10.1000/nat.1", [])
        self.web.europepmc("10.1000/nat.1", [full_text_url("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC9?pdf=render")])
        r = self.run_(path)
        self.assertEqual((r.lines[0]["reason"], self.items(path)), ("incomplete", [("https://europepmc.org/articles/PMC9?pdf=render", "published")]))
        self.assertIsNone(run.due(run.read(path), "links"))

    def test_a_source_that_does_not_answer_keeps_its_links(self):
        path = self.record("nat", "10.1000/nat.1")
        self.web.route("/openalex/*", status=500)
        self.run_(path)
        self.web.reset()
        self.web.route("/openalex/*", status=500)
        self.web.europepmc("10.1000/nat.1", [full_text_url("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC9?pdf=render")])
        self.run_(path)
        rec = run.read(path)
        self.assertEqual(rec["links"]["incomplete"], ["openalex"])
        self.assertEqual([x["source"] for x in rec["links"]["items"]], ["europepmc"])

    def test_failures_and_exit_codes(self):
        self.web.route("/openalex/works/doi:10.1000/allfail", status=500)
        self.web.route("/epmc/*", status=500)
        noid, allfail = self.record("noid"), self.record("allfail", "10.1000/allfail")
        bad = self.work.records / "bad.json"
        bad.write_text("[1, 2]")
        r = self.run_(noid, allfail, bad)
        self.assertEqual(r.code, 1)
        self.assertEqual([(o["slug"], o["code"]) for o in r.lines[:3]],
                         [("noid", "no_identifier"), ("allfail", "no_answer"), ("bad", "record_invalid")])
        self.assertEqual(run.read(allfail)["links"]["incomplete"], ["europepmc", "openalex"])
        unreadable = config_file()
        unreadable.write_text("{not json")
        r = self.run_(self.record("x", "10.1000/nat.1"), config=unreadable)
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "config_unreadable"))

    def test_a_429_stops_the_host_for_the_run(self):
        self.web.rate_limit("/openalex/works/doi:10.1000/limit")
        a, b = self.record("a", "10.1000/limit"), self.record("b", "10.1000/nat.1")
        r = self.run_(a, b)
        self.assertEqual(len(self.web.requested("GET", "/openalex/*")), 1, "after the 429 OpenAlex is not asked again")
        self.assertEqual((r.lines[0]["sources"]["openalex"], r.lines[1]["sources"]["openalex"]), ("source_blocked", "source_blocked"))
        self.web.requests.clear()
        self.run_(a)
        self.assertEqual(self.web.requested("GET", "/openalex/*"), [], "nor in the next run: pace.json keeps the stop")

    def test_needs_browser_and_one_link_per_url(self):
        raw = links.raw_link
        got = links.finalize([raw("https://www-publisher-example.proxy.example.edu/a.pdf", "openalex", "published"),
                              raw("https://export.arxiv.org/abs/2101.00001v2", "openalex"),
                              raw("https://jamanetwork.com/x.pdf", "openalex", "published"),
                              raw("https://www.new.example/y.pdf", "openalex", "published")], None, None, "proxy.example.edu")
        self.assertEqual([(x["url"], x["needs_browser"]) for x in got], [
            ("https://www.new.example/y.pdf", None), ("https://www-publisher-example.proxy.example.edu/a.pdf", True),
            ("https://jamanetwork.com/x.pdf", True), ("https://arxiv.org/pdf/2101.00001", False)])
        got = links.finalize([raw("https://site.example/u.pdf", "europepmc", repository=True),
                              raw("http://SITE.example/u.pdf/", "openalex", "published"),
                              raw("not a url", "openalex", "published")], None, None, None)
        self.assertEqual([(x["url"], x["source"], x["version"]) for x in got], [("https://site.example/u.pdf", "openalex", "published")])

    def test_smoke(self):
        r = smoke("fulltext_links", self.record("nat", "10.1000/nat.1"), config=self.config,
                  env=self.web.env())
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
