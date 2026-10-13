# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fetch.py. The browser is a stub `opencli` on PATH that plays a scenario (pages by URL, in-page
fetch answers by URL, links that download, pdf.js viewers) and keeps its tab state in a file; plain HTTP is a local
http.server. claim.py and check_pdf.py run for real, with pdftotext stubbed to print a PDF's bytes after its 9-byte
header (a test PDF is b"%PDF-1.4\\n" + its text)."""
import base64
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch.py"
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
OTHER = "A Completely Different Paper About Lung Nodules"


def pdf(text):
    return b"%PDF-1.4\n" + text.encode("utf-8")


def b64(data):
    return base64.b64encode(data).decode()


OPENCLI_STUB = r'''#!PYTHON
import base64, json, os, re, sys
scen = json.load(open(os.environ["STUB_SCENARIO"]))
state_path = os.environ["STUB_STATE"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {"current": None, "mark": None, "b64": None}
args = [a for a in sys.argv[1:] if a not in ("--window", "background")]
with open(os.environ["STUB_STATE"] + ".calls", "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
def out(value):
    print(value if isinstance(value, str) else json.dumps(value))
    save()
    sys.exit(0)
cmd = args[2]
if cmd == "open":
    url = args[3]
    dl = scen.get("downloads", {}).get(url)
    if dl:  # Chrome downloads it; the tab keeps its document (and the mark)
        open(os.path.join(dl["dir"], dl["name"]), "wb").write(base64.b64decode(dl["bytes"]))
        out({"url": url})
    if url not in scen.get("pages", {}):
        print("Error: navigation failed", file=sys.stderr)
        sys.exit(1)
    state["current"], state["mark"] = url, None
    out({"url": url})
js = args[3]
page = scen.get("pages", {}).get(state["current"]) or {}
if "p2z:info" in js:
    out({"href": page.get("href", state["current"]), "title": page.get("title", ""), "pdf": page.get("pdf"),
         "mark": state["mark"]})
if "p2z:mark" in js:
    state["mark"] = re.search(r"__p2z_mark='([^']*)'", js).group(1)
    out(state["current"] or "")
if "p2z:fetch" in js:
    url = json.loads(re.search(r"fetch\((\"[^\"]*\")", js).group(1))
    ans = scen.get("fetch", {}).get(url, {"status": 403, "ct": "text/html"})
    if ans.get("bytes"):
        state["b64"] = ans["bytes"]
        out({"status": 200, "ct": "application/pdf", "pdf": True, "b64len": len(ans["bytes"])})
    out({"status": ans["status"], "ct": ans["ct"], "pdf": False, "b64len": 0})
if "p2z:chunk" in js:
    a, b = map(int, re.search(r"slice\((\d+),(\d+)\)", js).groups())
    out(state["b64"][a:b] if state["b64"] else "null")
if "p2z:clear" in js:
    state["b64"] = None
    out("true")
if "p2z:html" in js:
    data = base64.b64encode(page.get("html", "").encode()).decode()
    state["b64"] = data
    out({"size": len(data), "b64len": len(data), "href": page.get("href", state["current"])})
if "p2z:viewer-ready" in js:
    out({"app": bool(page.get("viewer")), "ready": bool(page.get("viewer"))})
if "p2z:viewer-data" in js:
    state["b64"] = page.get("viewer")
    out({"pdf": True, "b64len": len(page["viewer"])} if page.get("viewer") else {"pdf": False})
print("stub: unknown call " + json.dumps(args), file=sys.stderr)
sys.exit(1)
'''


class Http(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/paper.pdf":
            body, ctype = pdf(f"{TITLE}\nWei Liu"), "application/pdf"
        elif path == "/wrong.pdf":
            body, ctype = pdf(f"{OTHER}\nSomeone Else"), "application/pdf"
        elif path == "/landing":
            body, ctype = b"<html>a landing page</html>", "text/html"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)


class FetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Http)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fetch_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"
        (self.work / "records").mkdir(parents=True)
        (self.work / ".started").touch()
        past = time.time() - 600
        os.utime(self.work / ".started", (past, past))
        self.dl = self.tmp / "Downloads"
        self.dl.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "pdftotext").write_text('#!/bin/sh\nexec tail -c +10 "$7"\n')
        (self.bin / "pdfinfo").write_text("#!/bin/sh\necho 'Pages: 1'\n")
        (self.bin / "opencli").write_text(OPENCLI_STUB.replace("PYTHON", sys.executable))
        for n in ("pdftotext", "pdfinfo", "opencli"):
            (self.bin / n).chmod(0o755)
        self.scenario = self.tmp / "scenario.json"
        self.state = self.tmp / "state.json"
        self.config = self.tmp / "config.json"
        self.config.write_text(json.dumps({"institution": {"proxy": "proxy.example.edu"}}))
        self.scene({})

    def scene(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def record(self, slug, title=TITLE, doi="10.1000/x.1", **extra):
        item = {"itemType": "journalArticle", "title": title, "DOI": doi,
                "creators": [{"creatorType": "author", "lastName": "Liu", "firstName": "Wei"}]}
        path = self.work / "records" / f"{slug}.json"
        path.write_text(json.dumps({"slug": slug, "item": item, **extra}))
        return path

    def run_script(self, *argv, path=None):
        env = dict(os.environ, PATH=path or f"{self.bin}{os.pathsep}{os.environ['PATH']}", STUB_SCENARIO=str(self.scenario),
                   STUB_STATE=str(self.state), PAPER_TO_ZOTERO_CONFIG=str(self.config),
                   PAPER_TO_ZOTERO_DOWNLOAD_WAIT="2", PAPER_TO_ZOTERO_VIEWER_WAIT="1")
        env = {k: v for k, v in env.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
        return subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, env=env, timeout=120)

    def lines(self, text):
        return [json.loads(ln) for ln in text.splitlines() if ln.startswith("{")]

    def tries(self):
        path = self.work / "fetch.jsonl"
        return [e for e in map(json.loads, path.read_text().splitlines()) if e["event"] == "try"] if path.exists() else []

    # --- page --------------------------------------------------------------------------

    def test_page_fetches_the_declared_pdf_inside_the_page(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/article/1", "title": TITLE,
                                                               "pdf": "/article/1.pdf"}},
                    "fetch": {"https://pub.example/article/1.pdf": {"bytes": b64(pdf(f"{TITLE}\nWei Liu"))}}})
        p = self.record("paper")
        r = self.run_script("--via", "page", "--pass", "1", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.work / "records" / "paper.pdf").is_file())
        t = self.tries()[-1]
        self.assertEqual((t["slug"], t["pass"], t["via"], t["url"], t["result"]),
                         ("paper", 1, "page", "https://pub.example/article/1.pdf", "ok"))
        calls = [json.loads(ln) for ln in Path(str(self.state) + ".calls").read_text().splitlines()]
        self.assertIn(["browser", "p2z", "open", "https://doi.org/10.1000/x.1", "--window", "background"], calls)
        r = self.run_script("--via", "page", "--pass", "1", str(p))
        self.assertEqual(self.lines(r.stdout)[0]["reason"], "has_file")

    def test_proxied_page_requests_the_path_on_its_own_origin(self):
        proxied = "https://www-pub-example.proxy.example.edu"
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": f"{proxied}/article/1", "title": TITLE,
                                                               "pdf": "https://www.pub.example/article/1.pdf"}},
                    "fetch": {f"{proxied}/article/1.pdf": {"bytes": b64(pdf(f"{TITLE}\nWei Liu"))}}})
        r = self.run_script("--via", "page", str(self.record("paper")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.tries()[-1]["url"], "https://www.pub.example/article/1.pdf", "logged as the canonical link")

    def test_refused_request_then_the_opened_link_downloads(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/a", "title": TITLE,
                                                               "pdf": "https://pub.example/a.pdf"}},
                    "downloads": {"https://pub.example/a.pdf": {"dir": str(self.dl), "name": "a.pdf",
                                                                 "bytes": b64(pdf(f"{TITLE}\nWei Liu"))}}})
        r = self.run_script("--via", "page", "--downloads", str(self.dl), str(self.record("paper")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.work / "records" / "paper.pdf").is_file())
        self.assertEqual(self.tries()[-1]["result"], "ok")
        self.assertFalse((self.dl / "a.pdf").exists())

    def test_refused_then_a_pdfjs_viewer(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://agg.example/doc", "title": TITLE,
                                                               "pdf": "https://agg.example/doc/pdf"},
                              "https://agg.example/doc/pdf": {"title": "viewer", "viewer": b64(pdf(f"{TITLE}\nWei Liu"))}}})
        r = self.run_script("--via", "page", str(self.record("paper")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.tries()[-1]["note"], "read from the pdf.js viewer")
        self.assertTrue((self.work / "records" / "paper.pdf").is_file())

    def test_a_page_without_a_pdf_link_stops_the_run_until_the_agent_decides(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://sso.example.edu/login", "title": "Sign in"},
                              "https://doi.org/10.1000/y.2": {"href": "https://pub.example/b", "title": OTHER,
                                                               "pdf": "https://pub.example/b.pdf"}},
                    "fetch": {"https://pub.example/b.pdf": {"bytes": b64(pdf(f"{OTHER}\nWei Liu"))}}})
        paths = [self.record("paper"), self.record("other", OTHER, "10.1000/y.2")]
        r = self.run_script("--via", "page", *map(str, paths))
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)[-1]
        self.assertEqual((out["code"], out["slug"], out["why"], out["url"], out["title"]),
                         ("stopped", "paper", "no_pdf_link", "https://sso.example.edu/login", "Sign in"))
        self.assertFalse((self.work / "records" / "other.pdf").exists(), "the run stops at the first record")
        r = self.run_script("--via", "page", *map(str, paths))
        self.assertEqual(self.lines(r.stdout)[-1]["slug"], "paper", "a stopped record is tried again on rerun")
        r = self.run_script("--via", "page", "--verdict", "gate_timeout", str(paths[0]))
        self.assertEqual((r.returncode, self.tries()[-1]["result"], self.tries()[-1]["by"]), (0, "gate_timeout", "agent"))
        r = self.run_script("--via", "page", *map(str, paths))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.lines(r.stdout)[0]["reason"], "tried", "the agent's verdict counts as tried")
        self.assertTrue((self.work / "records" / "other.pdf").is_file())
        r = self.run_script("--via", "page", "--pass", "2", str(paths[0]))
        self.assertEqual(self.lines(r.stdout)[-1]["code"], "stopped", "a new pass tries it again")

    def test_refused_and_no_viewer_stops(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/a", "title": TITLE,
                                                               "pdf": "https://pub.example/a.pdf"},
                              "https://pub.example/a.pdf": {"title": "Purchase this article"}}})
        r = self.run_script("--via", "page", str(self.record("paper")))
        out = self.lines(r.stdout)[-1]
        self.assertEqual((r.returncode, out["why"], out["title"]), (1, "refused", "Purchase this article"))

    def test_request_url_rules(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("fetch", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        p = "proxy.example.edu"
        self.assertEqual(mod.request_url("https://ieeexplore.ieee.org/x.pdf", "https://ieeexplore-ieee-org.proxy.example.edu/doc", p),
                         "https://ieeexplore-ieee-org.proxy.example.edu/x.pdf")
        self.assertEqual(mod.request_url("https://www.my-site.org/x.pdf", "https://www-my--site-org.proxy.example.edu/a", p),
                         "https://www-my--site-org.proxy.example.edu/x.pdf")
        self.assertEqual(mod.request_url("http://proceedings.mlr.press/v1/a.pdf", "https://proceedings.mlr.press/v1/a.html", p),
                         "https://proceedings.mlr.press/v1/a.pdf", "plain http on an https page: same path on the page's origin")
        self.assertEqual(mod.request_url("https://downloads.hindawi.com/x.pdf", "https://www.hindawi.com/a", p),
                         "https://downloads.hindawi.com/x.pdf", "a real cross-host link stays")
        self.assertEqual(mod.request_url("/x.pdf", "https://pub.example/a", None), "https://pub.example/x.pdf")

    # --- http / snapshot / viewer --------------------------------------------------------

    def test_http_goes_through_the_links_of_one_version(self):
        links = [{"url": f"{self.base}/landing", "source": "openalex", "version": "published", "needs_browser": None},
                 {"url": f"{self.base}/wrong.pdf", "source": "openalex", "version": "published", "needs_browser": None},
                 {"url": "https://pmc.example/x", "source": "europepmc", "version": "published", "needs_browser": True},
                 {"url": f"{self.base}/paper.pdf", "source": "openalex", "version": "published", "needs_browser": None},
                 {"url": f"{self.base}/paper.pdf?pre", "source": "arxiv", "version": "preprint", "needs_browser": False}]
        p = self.record("paper", links=links)
        q = self.record("other", OTHER, "10.1000/y.2", links=[])
        r = self.run_script("--via", "http", str(p), str(q))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([(t["slug"], t["result"]) for t in self.tries()],
                         [("paper", "not_pdf"), ("paper", "wrong_file"), ("paper", "ok"), ("other", "no_link")])
        self.assertTrue((self.work / "records" / "paper.pdf").is_file(), "the preprint link was never needed")
        self.assertTrue((self.work / "unverified" / "paper.http.pdf").is_file())
        r = self.run_script("--via", "http", str(q))
        self.assertEqual(self.lines(r.stdout)[0]["reason"], "tried")
        r = self.run_script("--via", "http", "--version", "preprint", str(self.record("pre", links=links)))
        self.assertTrue((self.work / "records" / "pre.preprint.pdf").is_file(), "a preprint link files a preprint")

    def test_snapshot_of_the_article_page(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {
            "href": "https://pub.example/article/1", "title": TITLE,
            "html": f"<html><head><title>{TITLE}</title></head><body>Abstract. Keywords.</body></html>"}}})
        r = self.run_script("--via", "snapshot", "--pass", "3", str(self.record("paper")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.work / "records" / "paper.html").is_file())
        self.assertEqual((self.tries()[-1]["result"], self.tries()[-1]["url"]), ("ok", "https://pub.example/article/1"))

    def test_viewer_in_the_current_tab(self):
        self.scene({"pages": {"https://agg.example/doc": {"title": "ProQuest", "viewer": b64(pdf(f"{TITLE}\nWei Liu"))}}})
        self.state.write_text(json.dumps({"current": "https://agg.example/doc", "mark": None, "b64": None}))
        r = self.run_script("--via", "viewer", str(self.record("paper")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.work / "records" / "paper.pdf").is_file())

    def test_cannot_run(self):
        other = self.tmp / "elsewhere" / "records"
        other.mkdir(parents=True)
        (other / "z.json").write_text(json.dumps({"slug": "z", "item": {"title": "t"}}))
        r = self.run_script("--via", "http", str(self.record("paper")), str(other / "z.json"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "mixed_work_dirs"))
        empty = self.tmp / "empty"
        empty.mkdir()
        r = self.run_script("--via", "page", str(self.record("paper")), path=str(empty))
        self.assertEqual((r.returncode, json.loads(r.stdout.splitlines()[-1])["code"]), (2, "no_opencli"))
        self.assertEqual(self.run_script("--via", "viewer", str(self.record("a")), str(self.record("b"))).returncode, 2)


if __name__ == "__main__":
    unittest.main()
