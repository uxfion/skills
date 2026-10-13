# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fulltext_links.py: OpenAlex and Europe PMC on one http.server (OPENALEX_BASE_URL,
EUROPEPMC_BASE_URL); each test gets its own config file."""
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fulltext_links.py"
KEY = "sk-TEST-openalex-SECRET-0042"
PUB_PDF = "https://www.publisher.example/articles/nat-1.pdf"


def loc(url_pdf=None, landing=None, version=None, is_oa=True, stype="journal"):
    return {"is_oa": is_oa, "pdf_url": url_pdf, "landing_page_url": landing, "version": version,
            "source": {"type": stype, "display_name": "x"}}


OPENALEX = {
    "10.1000/nat.1": {
        "best_oa_location": loc(PUB_PDF, "https://doi.org/10.1000/nat.1", "publishedVersion"),
        "locations": [
            loc(PUB_PDF, "https://doi.org/10.1000/nat.1", "publishedVersion"),
            loc(None, "https://pubmed.ncbi.nlm.nih.gov/456", "publishedVersion", is_oa=False, stype="repository"),
            loc("https://arxiv.org/pdf/2212.00001", "http://arxiv.org/abs/2212.00001", "submittedVersion", stype="repository"),
            loc("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/nat.pdf", "https://www.ncbi.nlm.nih.gov/pmc/articles/123",
                "submittedVersion", stype="repository"),
            loc(None, "https://doi.org/10.5281/zenodo.1", None, stype="repository"),
        ]},
    "10.1000/jno.2": {"best_oa_location": loc(None, "https://doi.org/10.1000/jno.2", "publishedVersion"),
                      "locations": [loc(None, "https://doi.org/10.1000/jno.2", "publishedVersion")]},
    "10.1000/am.3": {"locations": []},
    "10.48550/arxiv.2006.11239": {
        "best_oa_location": loc("https://arxiv.org/pdf/2006.11239", "http://arxiv.org/abs/2006.11239", "submittedVersion",
                                stype="repository"),
        "locations": [loc("https://arxiv.org/pdf/2006.11239v2", None, "submittedVersion", stype="repository")]},
    "10.1000/closed.5": {"locations": [loc(None, "https://doi.org/10.1000/closed.5", "publishedVersion", is_oa=False)]},
    "10.1000/acc.6": {"locations": [loc("https://repo.example.edu/acc.pdf", None, "acceptedVersion", stype="journal")]},
}


def epmc(doi, **kw):
    base = {"id": "456", "source": "MED", "doi": doi, "pmid": "456", "isOpenAccess": "N", "inPMC": "N",
            "authMan": "N", "epmcAuthMan": "N", "nihAuthMan": "N", "fullTextUrlList": {"fullTextUrl": []}}
    return {**base, **kw}


def ftu(code, style, site, url):
    return {"availabilityCode": code, "documentStyle": style, "site": site, "url": url}


EUROPEPMC = {
    "10.1000/nat.1": epmc("10.1000/nat.1", pmcid="PMC123", inPMC="Y", fullTextUrlList={"fullTextUrl": [
        ftu("S", "doi", "DOI", "https://doi.org/10.1000/nat.1"),
        ftu("OA", "html", "Europe_PMC", "https://europepmc.org/articles/PMC123"),
        ftu("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC123?pdf=render")]}),
    "10.1000/jno.2": epmc("10.1000/jno.2", pmcid="PMC777", inPMC="Y", fullTextUrlList={"fullTextUrl": [
        ftu("F", "doi", "DOI", "https://doi.org/10.1000/jno.2")]}),
    "10.1000/am.3": epmc("10.1000/am.3", pmcid="PMC333", inPMC="Y", authMan="Y", fullTextUrlList={"fullTextUrl": [
        ftu("OA", "pdf", "Europe_PMC", "https://europepmc.org/articles/PMC333?pdf=render"),
        ftu("OA", "html", "Unpaywall", "https://hal.example.org/hal-333")]}),
    "10.1000/ppr.7": epmc("10.1000/ppr.7", source="PPR", fullTextUrlList={"fullTextUrl": [
        ftu("OA", "doi", "DOI", "https://doi.org/10.1000/ppr.7")]}),
}


class Handler(http.server.BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *a):
        pass

    def send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(url.path)
        query = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
        Handler.requests.append((path, query))
        if path.startswith("/openalex/works/doi:"):
            doi = path[len("/openalex/works/doi:"):].lower()
            if doi == "10.1000/limit":
                return self.send(429, {"error": "slow down"})
            if doi in ("10.1000/err", "10.1000/allfail"):
                return self.send(500, b"boom", "text/plain")
            return self.send(200, OPENALEX[doi]) if doi in OPENALEX else self.send(404, {"error": "not found"})
        if path == "/epmc/europepmc/webservices/rest/search":
            doi = query.get("query", "")[len('DOI:"'):-1].lower()
            if doi == "10.1000/allfail":
                return self.send(500, b"boom", "text/plain")
            hits = [EUROPEPMC[doi]] if doi in EUROPEPMC else []
            return self.send(200, {"hitCount": len(hits), "resultList": {"result": hits}})
        self.send(404, {"error": "no route"})


class FulltextLinksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
        cls.env = {**env, "no_proxy": "127.0.0.1,localhost", "OPENALEX_BASE_URL": cls.base + "/openalex",
                   "EUROPEPMC_BASE_URL": cls.base + "/epmc"}
        spec = importlib.util.spec_from_file_location("fulltext_links", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.records = self.tmp / "records"
        self.records.mkdir()
        self.config = self.tmp / "config.json"
        self.write_config({"openalex_key": KEY})
        Handler.requests.clear()

    def write_config(self, cfg):
        self.config.write_text(json.dumps(cfg))

    def record(self, slug, doi=None, **fields):
        item = {"itemType": "journalArticle", "title": f"Title of {slug}"}
        if doi:
            item["DOI"] = doi
        item.update(fields.pop("item", {}))
        path = self.records / f"{slug}.json"
        path.write_text(json.dumps({"slug": slug, "item": item, **fields}, indent=2))
        return path

    def run_script(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True,
                              env={**self.env, "PAPER_TO_ZOTERO_CONFIG": str(self.config)})

    def lines(self, text):
        return [json.loads(ln) for ln in text.splitlines() if ln.startswith("{")]

    def summaries(self, proc):
        rows = self.lines(proc.stdout)
        return {r["slug"]: r for r in rows if "slug" in r}, rows[-1]["summary"]

    def read(self, path):
        return json.loads(Path(path).read_text())

    def hits(self, prefix):
        return [r for r in Handler.requests if r[0].startswith(prefix)]

    def test_full_record_dedupe_versions_and_order(self):
        path = self.record("nat", "10.1000/nat.1", item={"extra": "arXiv: 2212.00001"})
        proc = self.run_script("-i", str(path))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        links = self.read(path)["links"]
        self.assertEqual([(l["url"], l["source"], l["version"], l["needs_browser"]) for l in links], [
            (PUB_PDF, "openalex", "published", None),
            ("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/nat.pdf", "openalex", "published", True),
            ("https://europepmc.org/articles/PMC123?pdf=render", "europepmc", "published", True),
            ("https://arxiv.org/pdf/2212.00001", "arxiv", "preprint", False),
            ("https://doi.org/10.5281/zenodo.1", "openalex", "unknown", None)],
            "PMC copies take Europe PMC's verdict; an arXiv copy is a preprint; a repository location is unknown")
        rows, summary = self.summaries(proc)
        self.assertEqual(rows["nat"]["sources"], {"arxiv": "ok", "openalex": "ok", "europepmc": "ok"})
        self.assertEqual(rows["nat"]["first"], {"version": "published", "needs_browser": None, "host": "www.publisher.example"})
        self.assertEqual(summary, {"total": 1, "ok": 1, "skipped": 0, "failed": 0})

    def test_key_sent_as_parameter_never_printed(self):
        path = self.record("nat", "10.1000/nat.1")
        proc = self.run_script("-i", "--sources", "openalex", str(path))
        self.assertEqual(self.hits("/openalex/")[0][1], {"api_key": KEY})
        self.assertNotIn(KEY, proc.stdout + proc.stderr)
        self.write_config({})
        Handler.requests.clear()
        proc = self.run_script("-i", "--refresh", "--sources", "openalex", str(path))
        self.assertEqual(self.hits("/openalex/")[0][1], {}, "no key: unkeyed, and nothing else is sent")
        self.assertEqual(self.summaries(proc)[1]["openalex_key"], False)

    def test_closed_paper_and_accepted_label(self):
        closed = self.record("closed", "10.1000/closed.5")
        acc = self.record("acc", "10.1000/acc.6")
        self.run_script("-i", "--sources", "openalex", str(closed), str(acc))
        self.assertEqual(self.read(closed)["links"], [], "answered with nothing open: links [] is written")
        self.assertEqual([(l["version"], l["url"]) for l in self.read(acc)["links"]],
                         [("accepted", "https://repo.example.edu/acc.pdf")])

    def test_europepmc_versions_and_pmc_page(self):
        paths = [self.record(s, d) for s, d in (("jno", "10.1000/jno.2"), ("am", "10.1000/am.3"), ("ppr", "10.1000/ppr.7"))]
        self.run_script("-i", "--sources", "europepmc", *map(str, paths))
        jno, am, ppr = (self.read(p)["links"] for p in paths)
        self.assertEqual([(l["url"], l["version"]) for l in jno], [
            ("https://doi.org/10.1000/jno.2", "published"), ("https://pmc.ncbi.nlm.nih.gov/articles/PMC777/", "published")],
            "in PMC without a PMC link: its article page is added")
        self.assertEqual([(l["url"], l["version"]) for l in am], [
            ("https://europepmc.org/articles/PMC333?pdf=render", "accepted"),
            ("https://pmc.ncbi.nlm.nih.gov/articles/PMC333/", "accepted"),
            ("https://hal.example.org/hal-333", "unknown")])
        self.assertEqual([(l["url"], l["version"]) for l in ppr], [("https://doi.org/10.1000/ppr.7", "preprint")])

    def test_arxiv_record(self):
        path = self.record("ddpm", "10.48550/arXiv.2006.11239", item={"itemType": "preprint"})
        proc = self.run_script("-i", str(path))
        self.assertEqual([(l["url"], l["version"]) for l in self.read(path)["links"]],
                         [("https://arxiv.org/pdf/2006.11239", "preprint")], "arXiv URLs of every spelling are one link")
        self.assertEqual(self.summaries(proc)[0]["ddpm"]["sources"], {"arxiv": "ok", "openalex": "ok", "europepmc": "no_identifier"})
        Handler.requests.clear()
        self.run_script("-i", "--refresh", "--sources", "arxiv", str(path))
        self.assertEqual(Handler.requests, [], "the arXiv link needs no request")

    def test_identifiers(self):
        ids = self.mod.identifiers
        self.assertEqual(ids({"item": {"DOI": "https://doi.org/10.1000/X", "extra": "arXiv: 2101.00001"}}),
                         {"doi": "10.1000/X", "arxiv": "2101.00001"})
        self.assertEqual(ids({"item": {"archiveID": "arXiv:2101.00002v3"}}), {"doi": None, "arxiv": "2101.00002"})
        self.assertEqual(ids({"item": {"url": "https://arxiv.org/abs/2101.00003"}}), {"doi": None, "arxiv": "2101.00003"})
        self.assertEqual(ids({"id": "10.48550/arXiv.2101.00004", "item": {}}),
                         {"doi": "10.48550/arXiv.2101.00004", "arxiv": "2101.00004"})
        self.assertEqual(ids({"item": {"extra": "DOI: 10.5555/abc"}}), {"doi": "10.5555/abc", "arxiv": None})

    def test_needs_browser_and_proxy(self):
        fin = self.mod.finalize
        raw = self.mod.raw_link
        links = fin([raw("https://www-publisher-example.proxy.example.edu/a.pdf", "openalex", "published"),
                     raw("https://export.arxiv.org/abs/2101.00001v2", "openalex"),
                     raw("https://jamanetwork.com/x.pdf", "openalex", "published"),
                     raw("https://www.new.example/y.pdf", "openalex", "published")], None, None, "proxy.example.edu")
        self.assertEqual([(l["url"], l["needs_browser"]) for l in links], [
            ("https://www.new.example/y.pdf", None), ("https://www-publisher-example.proxy.example.edu/a.pdf", True),
            ("https://jamanetwork.com/x.pdf", True), ("https://arxiv.org/pdf/2101.00001", False)])

    def test_dedupe_keeps_the_more_specific_version(self):
        raw = self.mod.raw_link
        links = self.mod.finalize([raw("https://site.example/u.pdf", "europepmc", repository=True),
                                   raw("http://SITE.example/u.pdf/", "openalex", "published"),
                                   raw("not a url", "openalex", "published")], None, None, None)
        self.assertEqual([(l["url"], l["source"], l["version"]) for l in links],
                         [("https://site.example/u.pdf", "openalex", "published")])

    def test_skip_when_links_exist_and_refresh_a_subset(self):
        path = self.record("nat", "10.1000/nat.1", links=[
            {"url": "https://old.example/epmc.pdf", "source": "europepmc", "version": "unknown", "needs_browser": None},
            {"url": "https://old.example/oa.pdf", "source": "openalex", "version": "published", "needs_browser": None}])
        rows, _ = self.summaries(self.run_script("-i", str(path)))
        self.assertEqual((rows["nat"]["code"], rows["nat"]["reason"]), ("skipped", "has_links"))
        self.assertEqual(Handler.requests, [])
        self.run_script("-i", "--refresh", "--sources", "europepmc", str(path))
        urls = [l["url"] for l in self.read(path)["links"]]
        self.assertIn("https://old.example/oa.pdf", urls, "openalex did not run: its old link stays")
        self.assertNotIn("https://old.example/epmc.pdf", urls, "europepmc answered: its own links are replaced")

    def test_stdin_stream_and_unchanged_files(self):
        rec = {"slug": "s", "item": {"DOI": "10.1000/jno.2"}}
        proc = self.run_script("--sources", "europepmc", stdin=json.dumps(rec))
        self.assertEqual(self.lines(proc.stdout)[0]["links"][0]["url"], "https://doi.org/10.1000/jno.2")
        self.assertEqual(self.lines(proc.stderr)[-1]["summary"]["ok"], 1)
        path = self.record("skip", "10.1000/jno.2", links=[])
        before = path.stat().st_mtime_ns
        self.run_script("-i", str(path))
        self.assertEqual(path.stat().st_mtime_ns, before, "a skipped record is not rewritten")
        self.assertEqual(self.run_script("-i").returncode, 2, "-i needs record paths")

    def test_failures_and_exit_codes(self):
        paths = [self.record("noid"), self.record("allfail", "10.1000/allfail"), self.record("ok", "10.1000/jno.2")]
        bad = self.records / "bad.json"
        bad.write_text("[1, 2]")
        proc = self.run_script("-i", "--sources", "openalex,europepmc", *map(str, paths), str(bad))
        self.assertEqual(proc.returncode, 1)
        rows, summary = self.summaries(proc)
        self.assertEqual(rows["noid"]["code"], "no_identifier")
        self.assertEqual((rows["allfail"]["code"], rows["allfail"]["sources"]),
                         ("no_answer", {"openalex": "http_500", "europepmc": "http_500"}))
        self.assertNotIn("links", self.read(paths[1]), "no answer: nothing written, a rerun tries again")
        self.assertEqual(rows["bad"]["code"], "invalid_record")
        self.assertEqual(summary, {"total": 4, "ok": 1, "skipped": 0, "failed": 3})
        self.config.write_text("{not json")
        proc = self.run_script("-i", str(paths[2]))
        self.assertEqual((proc.returncode, json.loads(proc.stderr.strip().splitlines()[-1])["code"]), (1, "bad_config"))

    def test_a_429_stops_the_host_for_the_run(self):
        paths = [self.record("a", "10.1000/limit"), self.record("b", "10.1000/nat.1")]
        proc = self.run_script("-i", "--sources", "openalex,europepmc", *map(str, paths))
        rows, summary = self.summaries(proc)
        self.assertEqual(len(self.hits("/openalex/")), 1, "after the 429 OpenAlex is not asked again")
        self.assertEqual(rows["a"]["sources"]["openalex"], "source_blocked")
        self.assertEqual(rows["b"]["sources"], {"openalex": "source_blocked", "europepmc": "ok"})
        self.assertEqual(summary["stopped"], ["api.openalex.org"])


if __name__ == "__main__":
    unittest.main()
