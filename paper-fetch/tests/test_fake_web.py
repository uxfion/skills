# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Self-test of tests/fake_web.py: each service answers in the shape the scripts parse, and the route hooks work."""
import json
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from fake_web import CSL_TYPES, FakeWeb, full_text_url, location, pdf_bytes

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
CSL = CSL_TYPES[0]


def get(url, accept=None, timeout=10):
    """(status, headers, body, final URL), redirects followed; an HTTP error status is returned like any other."""
    req = urllib.request.Request(url, headers={"Accept": accept} if accept else {})
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read(), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read(), url


def query(url, **params):
    return url + "?" + urllib.parse.urlencode(params)


class Tags(HTMLParser):
    """meta name -> [content], the (text, href) of each link, the iframe srcs."""

    def __init__(self, text):
        super().__init__()
        self.meta, self.links, self.frames, self._href = {}, [], [], None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name"):
            self.meta.setdefault(a["name"], []).append(a.get("content"))
        elif tag == "a":
            self._href = a.get("href")
        elif tag == "iframe":
            self.frames.append(a.get("src"))

    def handle_data(self, data):
        if self._href:
            self.links.append((data, self._href))
            self._href = None


class FakeWebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = FakeWeb()
        cls.env = cls.web.env()

    @classmethod
    def tearDownClass(cls):
        cls.web.close()

    def setUp(self):
        self.web.reset()

    # ---- services ---------------------------------------------------------------------------------------------------

    def test_doi_org_negotiates_csl_and_redirects_browsers(self):
        w, base = self.web, self.env["DOI_BASE_URL"]
        w.doi("10.1109/CVPR.2016.90", {"type": "paper-conference", "title": "Deep Residual Learning", "source": "Crossref"},
              landing="/pub/resnet")
        w.doi("10.48550/arXiv.2006.11239", {"type": "article", "title": "Denoising Diffusion Probabilistic Models"})
        w.doi("10.9999/html", landing="/pub/resnet")
        w.page("/pub/resnet", "Deep Residual Learning")
        status, headers, body, final = get(base + "/10.1109/cvpr.2016.90", CSL)
        self.assertEqual((status, headers["Content-Type"], json.loads(body)["title"]), (200, CSL, "Deep Residual Learning"))
        self.assertIn("/crossref/v1/works/", final, "a Crossref DOI's CSL comes from Crossref")
        self.assertIn("datacite", get(base + "/10.48550/arXiv.2006.11239", CSL)[3], "any other from DataCite")
        status, headers, _, final = get(base + "/10.1109/CVPR.2016.90", "application/pdf,*/*")
        self.assertEqual((status, final), (200, w.url("/pub/resnet")), "a browser's Accept lands on the page")
        self.assertIn("text/html", headers["Content-Type"])
        status, headers, _, final = get(base + "/10.9999/html", CSL)
        self.assertEqual((status, final), (200, w.url("/pub/resnet")), "no CSL: the landing page, as doi.org does")
        self.assertEqual(get(base + "/10.9999/missing", CSL)[0], 404)

    def test_crossref_work_and_search(self):
        w, base = self.web, self.env["CROSSREF_BASE_URL"]
        w.crossref("10.1007/978-3-319-24574-4_28", title="U-Net: Convolutional Networks for Biomedical Image Segmentation",
                   container_title=["Lecture Notes in Computer Science", "MICCAI 2015"], type="book-chapter")
        w.crossref("10.52202/075280-0377", {"type": "proceedings-article", "issued": {"date-parts": [[2023]]},
                                            "title": ["Reflexion: language agents with verbal reinforcement learning"]})
        status, _, body, _ = get(base + "/works/10.1007/978-3-319-24574-4_28")
        data = json.loads(body)
        self.assertEqual((status, data["status"], data["message-type"]), (200, "ok", "work"))
        self.assertEqual(data["message"]["container-title"], ["Lecture Notes in Computer Science", "MICCAI 2015"])
        self.assertEqual(data["message"]["title"], ["U-Net: Convolutional Networks for Biomedical Image Segmentation"])
        self.assertEqual(get(base + "/works/10.1000/none")[0], 404)
        status, _, body, _ = get(query(base + "/works", **{"query.bibliographic": "Reflexion: Language Agents",
                                                          "query.author": "Shinn", "rows": 3}))
        self.assertEqual([i["DOI"] for i in json.loads(body)["message"]["items"]], ["10.52202/075280-0377"])
        body = get(query(base + "/works", **{"query.bibliographic": "zzz nothing"}))[2]
        self.assertEqual(json.loads(body)["message"]["items"], [])

    def test_arxiv_atom_api(self):
        w, api = self.web, self.env["ARXIV_API_URL"]
        w.arxiv("2303.11366", "Reflexion: Language Agents", version=4, comment="v4 contains a few additional experiments")
        w.arxiv("2105.05537", "Swin-Unet: Unet-like Pure Transformer", journal_ref="ECCV 2022 Workshops",
                doi="10.1007/978-3-031-25066-8_9", authors=["Hu Cao"])
        status, headers, body, _ = get(query(api, id_list="2303.11366,2105.05537v1,9999.99999", max_results=3))
        self.assertEqual(status, 200)
        self.assertIn("atom+xml", headers["Content-Type"])
        entries = ET.fromstring(body).findall("a:entry", ATOM)
        self.assertEqual([e.findtext("a:id", "", ATOM) for e in entries],
                         ["http://arxiv.org/abs/2303.11366v4", "http://arxiv.org/abs/2105.05537v1"])
        self.assertEqual(entries[0].findtext("arxiv:comment", None, ATOM), "v4 contains a few additional experiments")
        self.assertIsNone(entries[0].findtext("arxiv:doi", None, ATOM))
        self.assertEqual((entries[1].findtext("arxiv:doi", None, ATOM), entries[1].findtext("arxiv:journal_ref", None, ATOM)),
                         ("10.1007/978-3-031-25066-8_9", "ECCV 2022 Workshops"))
        entries = ET.fromstring(get(query(api, search_query='ti:"Swin Unet" AND au:Cao'))[2]).findall("a:entry", ATOM)
        self.assertEqual([e.findtext("a:title", "", ATOM) for e in entries], ["Swin-Unet: Unet-like Pure Transformer"])

    def test_openalex_work(self):
        w, base = self.web, self.env["OPENALEX_BASE_URL"]
        w.openalex("10.1000/nat.1", [
            location(None, "https://pubmed.example/456", "publishedVersion", is_oa=False, source_type="repository"),
            location("https://pub.example/nat.pdf", "https://doi.org/10.1000/nat.1", "publishedVersion"),
            location("https://arxiv.org/pdf/2212.00001", None, "submittedVersion", source_type="repository")])
        status, _, body, _ = get(query(base + "/works/doi:10.1000/NAT.1", api_key="k"))
        work = json.loads(body)
        self.assertEqual((status, work["doi"]), (200, "https://doi.org/10.1000/nat.1"))
        self.assertEqual(work["best_oa_location"]["pdf_url"], "https://pub.example/nat.pdf", "the first open location")
        self.assertEqual([(l["version"], l["source"]["type"], l["is_oa"]) for l in work["locations"]],
                         [("publishedVersion", "repository", False), ("publishedVersion", "journal", True),
                          ("submittedVersion", "repository", True)])
        self.assertEqual(get(base + "/works/doi:10.1000/none")[0], 404)

    def test_europepmc_search(self):
        w, base = self.web, self.env["EUROPEPMC_BASE_URL"]
        w.europepmc("10.1000/am.3", [full_text_url("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC333?pdf=render")],
                    pmcid="PMC333", authMan="Y")
        w.europepmc("10.1000/ppr.7", source="PPR")
        search = base + "/europepmc/webservices/rest/search"
        body = get(query(search, query='DOI:"10.1000/AM.3"', resultType="core", format="json", pageSize="5"))[2]
        data = json.loads(body)
        hit = data["resultList"]["result"][0]
        self.assertEqual((data["hitCount"], hit["doi"], hit["source"], hit["inPMC"], hit["pmcid"], hit["authMan"]),
                         (1, "10.1000/am.3", "MED", "Y", "PMC333", "Y"))
        entry = hit["fullTextUrlList"]["fullTextUrl"][0]
        self.assertEqual((entry["availabilityCode"], entry["documentStyle"], entry["site"]), ("OA", "pdf", "Europe_PMC"))
        hit = json.loads(get(query(search, query='DOI:"10.1000/ppr.7"'))[2])["resultList"]["result"][0]
        self.assertEqual((hit["source"], hit["inPMC"]), ("PPR", "N"))
        self.assertNotIn("fullTextUrlList", hit)
        self.assertEqual(json.loads(get(query(search, query='DOI:"10.1/none"'))[2])["resultList"]["result"], [])

    def test_pages_pdfs_and_gates(self):
        w = self.web
        url = w.page("/pub/a", "Deep Nets", links=[("PDF", "/pub/stamp?arnumber=1")], iframe="/pub/a.pdf",
                     meta={"citation_title": "Deep Nets", "citation_author": ["Liu, Wei", "Roe, Ann"],
                           "citation_pdf_url": "/pub/a.pdf", "dc.identifier": "doi:10.1000/x.1"})
        pdf_url = w.pdf("/pub/a.pdf", "Deep Nets\nWei Liu")
        status, headers, body, _ = get(url, "text/html")
        tags = Tags(body.decode())
        self.assertEqual((status, tags.meta["citation_author"], tags.meta["dc.identifier"]),
                         (200, ["Liu, Wei", "Roe, Ann"], ["doi:10.1000/x.1"]))
        self.assertEqual((tags.links, tags.frames), ([("PDF", "/pub/stamp?arnumber=1")], ["/pub/a.pdf"]))
        status, headers, body, _ = get(pdf_url)
        self.assertEqual((status, headers["Content-Type"], body), (200, "application/pdf", pdf_bytes("Deep Nets\nWei Liu")))
        status, _, body, _ = get(w.gate("/sso/login"))
        self.assertEqual((status, Tags(body.decode()).meta), (200, {}), "a login page: no citation meta")
        self.assertIn(b'type="password"', body)
        status, headers, _, _ = get(w.gate("/cf", "challenge"))
        self.assertEqual((status, headers["cf-mitigated"]), (403, "challenge"))

    def test_env_points_every_script_variable_here(self):
        env = self.env
        self.assertEqual(set(env), {"DOI_BASE_URL", "CROSSREF_BASE_URL", "ARXIV_API_URL", "OPENALEX_BASE_URL",
                                    "EUROPEPMC_BASE_URL", "no_proxy"})
        self.assertTrue(all(v.startswith(self.web.base_url + "/") for k, v in env.items() if k != "no_proxy"))
        self.assertIn("127.0.0.1", env["no_proxy"])

    # ---- routes and the log -----------------------------------------------------------------------------------------

    def test_request_log(self):
        w = self.web
        w.route("/echo", lambda r: (201, {"X-Seen": r.headers.get("x-test", "")}, {"method": r.method}))
        req = urllib.request.Request(w.url("/echo?a=1&b="), data=b'{"x": 1}', headers={"X-Test": "yes"})
        with OPENER.open(req, timeout=10) as resp:
            self.assertEqual((resp.status, resp.headers["X-Seen"], json.loads(resp.read())), (201, "yes", {"method": "POST"}))
        get(w.url("/doi/10.1000/a%3Bb"))
        (r,) = w.requested("POST", "/echo")
        self.assertEqual((r.method, r.path, r.query, r.headers["x-test"], r.body),
                         ("POST", "/echo", {"a": "1", "b": ""}, "yes", b'{"x": 1}'))
        self.assertEqual([r.path for r in w.requested("GET", "/doi/*")], ["/doi/10.1000/a;b"], "the path is unquoted")
        self.assertEqual(len(w.requests), 2)
        w.reset()
        self.assertEqual(w.requests, [], "reset forgets the log")
        self.assertEqual(get(w.url("/echo"))[0], 404, "and the routes")

    def test_the_route_registered_last_answers_first_and_none_passes_on(self):
        w = self.web
        w.route("/x", "below")
        w.route("/x*", lambda r: "above" if r.query.get("top") else None)
        w.route("/boom", lambda r: 1 / 0)
        self.assertEqual(get(w.url("/x?top=1"))[2], b"above")
        self.assertEqual(get(w.url("/x"))[2], b"below")
        status, _, body, _ = get(w.url("/boom"))
        self.assertEqual(status, 500)
        self.assertIn(b"ZeroDivisionError", body, "a broken callable answers its traceback")
        self.assertEqual(get(w.url("/nothing"))[0], 404)

    def test_429_with_retry_after(self):
        w, base = self.web, self.env["CROSSREF_BASE_URL"]
        w.crossref("10.1000/a", title="A Paper")
        w.rate_limit("/crossref/works*", retry_after=120, times=1)
        status, headers, _, _ = get(base + "/works/10.1000/a")
        self.assertEqual((status, headers["Retry-After"]), (429, "120"))
        self.assertEqual(get(base + "/works/10.1000/a")[0], 200, "times=1: the next request reaches Crossref")
        w.rate_limit("/doi/*", retry_after="Wed, 21 Oct 2026 07:28:00 GMT")
        status, headers, _, _ = get(self.env["DOI_BASE_URL"] + "/10.1000/a", CSL)
        self.assertEqual((status, headers["Retry-After"]), (429, "Wed, 21 Oct 2026 07:28:00 GMT"))

    def test_fail_the_first_n_times(self):
        w = self.web
        url = w.pdf("/flaky.pdf", "x")
        w.route("/flaky.pdf", "busy", status=503, times=2)
        self.assertEqual([get(url)[0] for _ in range(3)], [503, 503, 200])
        w.openalex("10.1000/b")
        w.route("/openalex/*", status=500, times=1)
        self.assertEqual([get(self.env["OPENALEX_BASE_URL"] + "/works/doi:10.1000/b")[0] for _ in range(2)], [500, 200],
                         "on top of a service too")

    def test_redirect(self):
        w = self.web
        w.page("/pub/b", "B")
        w.redirect("/go", "/pub/b")
        w.redirect("/away", "https://elsewhere.example/x", status=301)
        status, _, body, final = get(w.url("/go"))
        self.assertEqual((status, final), (200, w.url("/pub/b")))
        self.assertEqual([r.path for r in w.requests], ["/go", "/pub/b"])
        req = urllib.request.Request(w.url("/away"))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            opener.open(req, timeout=10)
        self.assertEqual((caught.exception.code, caught.exception.headers["Location"]), (301, "https://elsewhere.example/x"))

    def test_delay(self):
        w = self.web
        url = w.pdf("/slow.pdf", "x", delay=0.3)
        start = time.monotonic()
        self.assertEqual(get(url)[0], 200)
        self.assertGreaterEqual(time.monotonic() - start, 0.3)
        w.route("/slow.pdf", None, delay=0.5)
        with self.assertRaises((TimeoutError, urllib.error.URLError)):
            get(url, timeout=0.2)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


if __name__ == "__main__":
    unittest.main()
