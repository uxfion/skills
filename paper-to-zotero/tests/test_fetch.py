# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fetch.py and scripts/wait.py. The browser is a stub `opencli` on PATH that plays a scenario
(pages by URL with their PDF candidates, in-page fetch answers, links that download, pdf.js viewers, result links) and
keeps its tab in a file; plain HTTP is a local http.server; pdftotext is stubbed to print a PDF's bytes after its
9-byte header (a test PDF is b"%PDF-1.4\\n" + its text)."""
import base64
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from helpers import load

from p2zlib import run

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
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
args = [a for a in sys.argv[1:] if a not in ("--window", "background", "foreground")]
def out(value):
    print(value if isinstance(value, str) else json.dumps(value))
    json.dump(state, open(state_path, "w"))
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
if "p2z:find" in js:
    out({"href": page.get("href", state["current"]), "title": page.get("title", ""), "mark": state["mark"],
         "viewer": bool(page.get("viewer")), "candidates": [{"url": u, "why": "stub"} for u in page.get("pdf", [])]})
if "p2z:mark" in js:
    state["mark"] = re.search(r"__p2z_mark='([^']*)'", js).group(1)
    out(state["current"] or "")
if "p2z:fetch" in js:
    url = json.loads(re.search(r"fetch\((\"[^\"]*\")", js).group(1))
    ans = scen.get("fetch", {}).get(url)
    if ans:
        state["b64"] = ans
        out({"status": 200, "ct": "application/pdf", "pdf": True, "b64len": len(ans)})
    out({"status": 403, "ct": "text/html", "pdf": False, "b64len": 0})
if "p2z:chunk" in js:
    a, b = map(int, re.search(r"slice\((\d+),(\d+)\)", js).groups())
    out(state["b64"][a:b] if state["b64"] else "null")
if "p2z:clear" in js:
    state["b64"] = None
    out("true")
if "p2z:html" in js:
    state["b64"] = base64.b64encode(page.get("html", "").encode()).decode()
    out({"size": len(state["b64"]), "b64len": len(state["b64"]), "href": page.get("href", state["current"])})
if "p2z:viewer-data" in js:
    state["b64"] = page.get("viewer")
    out({"pdf": True, "b64len": len(page["viewer"])} if page.get("viewer") else {"pdf": False})
if "p2z:anchors" in js:
    out({"href": state["current"], "anchors": page.get("anchors", [])})
if "p2z:watch" in js:
    until = json.loads(re.search(r"const u=(null|\"[^\"]*\");", js).group(1))
    out({"href": page.get("href", state["current"]), "title": page.get("title", ""),
         "found": bool(until) and until in page.get("text", "")})
print("stub: unknown call " + json.dumps(args), file=sys.stderr)
sys.exit(1)
'''


class Http(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = {"/paper.pdf": pdf(f"{TITLE}\nWei Liu"), "/wrong.pdf": pdf(f"{OTHER}\nSomeone Else"),
                "/landing": b"<html>a landing page</html>"}.get(self.path.split("?", 1)[0])
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "application/pdf" if body and body.startswith(b"%PDF") else "text/html")
        self.end_headers()
        self.wfile.write(body or b"")


class Fetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Http)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p2z-fetch-"))
        self.work = run.Work(self.tmp / "work")
        self.work.records.mkdir(parents=True)
        self.work.started.touch()
        os.utime(self.work.started, (time.time() - 600,) * 2)
        self.dl = self.tmp / "Downloads"
        self.dl.mkdir()
        self.work.set(downloads=str(self.dl), session="p2z")
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "pdftotext").write_text('#!/bin/sh\nexec tail -c +10 "$7"\n')
        (bin_ / "pdfinfo").write_text("#!/bin/sh\necho 'Pages: 1'\n")
        (bin_ / "opencli").write_text(OPENCLI_STUB.replace("PYTHON", sys.executable))
        for n in ("pdftotext", "pdfinfo", "opencli"):
            (bin_ / n).chmod(0o755)
        self.scenario, self.config = self.tmp / "scenario.json", self.tmp / "config.json"
        self.config.write_text(json.dumps({"institution": {"proxy": "proxy.example.edu"}}))
        self.env = {**{k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")},
                    "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "STUB_SCENARIO": str(self.scenario),
                    "STUB_STATE": str(self.tmp / "state.json"), "PAPER_TO_ZOTERO_CONFIG": str(self.config),
                    "PAPER_TO_ZOTERO_INSTITUTION_GAP": "0", "PAPER_TO_ZOTERO_CLICK_WAIT": "3",
                    "PAPER_TO_ZOTERO_DISCOVERY_WAIT": "0"}
        self.scene({})

    def scene(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def record(self, slug, title=TITLE, doi="10.1000/x.1", links=()):
        item = {"itemType": "journalArticle", "title": title, **({"DOI": doi} if doi else {}),
                "creators": [{"creatorType": "author", "lastName": "Liu", "firstName": "Wei"}]}
        path = self.work.records / f"{slug}.json"
        path.write_text(json.dumps({"item": item, "links": {"items": list(links)}}))
        return str(path)

    def link(self, path, version="published"):
        return {"url": self.base + path, "source": "openalex", "version": version, "needs_browser": None}

    def run_(self, script, *argv):
        done = subprocess.run([sys.executable, str(SCRIPTS / f"{script}.py"), *argv], capture_output=True, text=True,
                              env=self.env, timeout=120)
        return done.returncode, [json.loads(ln) for ln in done.stdout.splitlines() if ln.startswith("{")], done.stderr

    def fetch(self, *argv):
        return self.run_("fetch", *argv)

    def events(self, kind):
        return [(e["slug"], e["route"], e.get("result") or e.get("why")) for e in self.work.events(kind)]

    def files(self):
        return sorted(p.name for p in self.work.records.iterdir() if not p.name.endswith(".json"))

    def test_one_pass_walks_the_routes_in_order(self):
        self.scene({"pages": {"https://doi.org/10.1000/b.2": {"href": "https://pub.example/b", "pdf": ["https://pub.example/b.pdf"]}},
                    "fetch": {"https://pub.example/b.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        recs = [self.record("a", links=[self.link("/paper.pdf"), self.link("/landing", "accepted")]),
                self.record("b", OTHER, "10.1000/b.2"),
                self.record("e", doi=None, links=[self.link("/wrong.pdf", "preprint"), self.link("/paper.pdf", "preprint")])]
        code, lines, err = self.fetch("--pass", "1", *recs)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.files(), ["a.pdf", "b.pdf", "e.preprint.pdf"], "each candidate's version goes along")
        self.assertEqual(self.events("try"), [("a", "open", "ok"), ("b", "publisher", "ok"), ("e", "preprint", "wrong_file"),
                                              ("e", "preprint", "ok")])
        self.assertEqual((lines[-1]["summary"]["with_file"], [x.get("reason") for x in lines if x.get("code") == "skipped"]),
                         (3, ["no_discovery"]))
        self.assertEqual(self.fetch("--pass", "1", *recs)[0], 0)
        self.assertEqual(len(self.work.events("try")), 4, "nothing is tried twice")

    def test_a_page_the_browser_cannot_pass_stops_until_the_agent_decides(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/x", "title": "Sign in"}}})
        rec = self.record("x", links=[self.link("/wrong.pdf", "preprint")])
        code, lines, _ = self.fetch("--pass", "1", rec)
        stop = next(x for x in lines if x.get("code") == "stopped")
        self.assertEqual((code, stop["why"], stop["url"]), (1, "no_pdf_link", "https://pub.example/x"))
        self.assertEqual((self.events("try"), self.events("stop")), ([], [("x", "publisher", "no_pdf_link")]), "a stop is no try")
        self.assertEqual(self.fetch("--pass", "1", rec)[0], 1, "the page is asked again on a rerun")
        self.assertEqual(self.fetch("--pass", "1", "--verdict", "no_access", rec)[0], 0)
        self.assertEqual(self.fetch("--pass", "1", rec)[0], 0)
        self.assertEqual(self.events("try"), [("x", "publisher", "no_access"), ("x", "preprint", "wrong_file")])
        other = self.record("y", OTHER, "10.1000/y.2")
        self.assertEqual(self.fetch("--pass", "1", "--route", "publisher", "--verdict", "gate_timeout", other)[0], 0)
        self.assertEqual(self.fetch("--pass", "1", "--route", "publisher", other)[0], 0, "the route is closed for it")
        code, lines, _ = self.fetch("--pass", "2", "--verdict", "no_access", rec)
        self.assertEqual((code, lines[0]["code"]), (1, "nothing_stopped"))

    def test_the_page_ladder(self):
        c, f, g = "Cardiac Segmentation With Diffusion Models", "Lung Nodule Detection in Low Dose CT", "Retinal Vessel Segmentation Using Transformers"
        proxied = "https://ieeexplore-ieee-org.proxy.example.edu"
        self.scene({"pages": {
            # refused inside the page, then the opened link downloads: this command files it (no watcher runs)
            "https://doi.org/10.1000/c.3": {"href": "https://pub.example/c", "pdf": ["https://pub.example/c.pdf"]},
            # refused, then the opened link shows a pdf.js viewer
            "https://doi.org/10.1000/f.4": {"href": "https://pub.example/f", "pdf": ["https://pub.example/f.pdf"]},
            "https://pub.example/f.pdf": {"viewer": b64(pdf(f"{f}\nWei Liu"))},
            # refused, then the opened link is an HTML reading page whose own candidate is the PDF (IEEE's stamp.jsp)
            "https://doi.org/10.1109/g.5": {"href": f"{proxied}/document/5", "pdf": ["https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=5"]},
            f"{proxied}/stamp/stamp.jsp?arnumber=5": {"pdf": [f"{proxied}/stampPDF/getPDF.jsp?arnumber=5"]}},
            "downloads": {"https://pub.example/c.pdf": {"dir": str(self.dl), "name": "c.pdf", "bytes": b64(pdf(f"{c}\nWei Liu"))}},
            "fetch": {f"{proxied}/stampPDF/getPDF.jsp?arnumber=5": b64(pdf(f"{g}\nWei Liu"))}})
        recs = [self.record("c", c, "10.1000/c.3"), self.record("f", f, "10.1000/f.4"), self.record("g", g, "10.1109/g.5")]
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", *recs)
        self.assertEqual(code, 0, err + json.dumps(lines))
        self.assertEqual(self.files(), ["c.pdf", "f.pdf", "g.pdf"])
        request_url = load("fetch").request_url
        self.assertEqual(request_url("https://ieeexplore.ieee.org/x.pdf", f"{proxied}/d/1", "proxy.example.edu"), f"{proxied}/x.pdf")
        self.assertEqual(request_url("http://pub.example/x.pdf", "https://pub.example/a", None), "https://pub.example/x.pdf")

    def test_the_discovery_route(self):
        self.config.write_text(json.dumps({"institution": {"discovery": "https://disc.example/search?vid=X&query=old"}}))
        search = lambda t: "https://disc.example/search?query=" + t.replace(" ", "+") + "&vid=X"  # noqa: E731
        record_page = "https://disc.example/full?docid=1"
        self.scene({"pages": {search(TITLE): {"anchors": [{"text": TITLE, "href": "https://disc.example/full?docid=arxiv_1"},
                                                          {"text": TITLE.upper(), "href": record_page}, {"text": "Other", "href": "x"}]},
                              "https://disc.example/full?docid=arxiv_1": {}, record_page: {"pdf": ["https://agg.example/doc/pdf"]},
                              search(OTHER): {"anchors": []}},
                    "fetch": {"https://agg.example/doc/pdf": b64(pdf(f"{TITLE}\nWei Liu"))}})
        code, lines, err = self.fetch("--pass", "1", "--route", "discovery", self.record("p", doi=None), self.record("q", OTHER, doi=None))
        self.assertEqual(code, 0, err + json.dumps(lines))
        self.assertEqual(self.events("try"), [("p", "discovery", "ok"), ("q", "discovery", "not_in_discovery")], "arXiv's record last")

    def test_a_snapshot_and_a_start_page(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"html": f"<html><title>{TITLE}</title><h1>{TITLE}</h1>Wei Liu</html>"},
                              "https://pmc.example/1": {"pdf": ["https://pmc.example/1.pdf"]}},
                    "fetch": {"https://pmc.example/1.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        self.assertEqual(self.fetch("--pass", "3", "--route", "snapshot", self.record("s"))[0], 0)
        self.assertEqual(self.fetch("--pass", "1", "--start", "https://pmc.example/1", "--version", "accepted",
                                    self.record("t", OTHER, "10.1000/t.9"))[0], 0)
        self.assertEqual(self.files(), ["s.html", "t.accepted.pdf"])
        self.assertEqual(self.events("try")[-1], ("t", "start", "ok"), "a start page is never a route's try")

    def test_wait(self):
        self.scene({"pages": {"https://gate.example/login": {"title": "Sign in", "text": "Sign in"}}})
        subprocess.run(["opencli", "browser", "p2z", "open", "https://gate.example/login"], env=self.env, capture_output=True)
        rec = self.record("w")
        code, lines, _ = self.run_("wait", rec, "--timeout", "1")
        self.assertEqual((code, lines[0]["code"]), (1, "timeout"))
        self.assertEqual(self.run_("wait", rec, "--until", "Sign in")[1][0]["code"], "passed")
        (self.work.records / "w.pdf").write_bytes(pdf(TITLE))
        self.assertEqual(self.run_("wait", rec, "--file-only")[1][0]["code"], "arrived")
        self.assertEqual(self.work.events(), [], "waiting records nothing")


if __name__ == "__main__":
    unittest.main()
