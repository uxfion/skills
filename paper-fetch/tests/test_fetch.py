# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/fetch.py and scripts/wait.py. The browser is a stub `opencli` on PATH that plays a scenario
(pages by URL with their PDF candidates, in-page fetch answers, links that download, pdf.js viewers, result links) and
keeps its tab in a file; plain HTTP is a local http.server; pdftotext is stubbed to print a PDF's bytes after its
9-byte header (a test PDF is b"%PDF-1.4\\n" + its text). The papers are result files as identify writes them, with
links as fulltext_links writes them."""
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
from unittest import mock

from helpers import call, load, result_file, smoke

from pflib import run

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
answer = load("answer")
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
state = json.load(open(state_path)) if os.path.exists(state_path) else {"current": None, "b64": None}
argv = sys.argv[1:]  # browser <command> [args...] --session pf [--window W]
at = argv.index("--session")
del argv[at:at + 2]
args = [a for a in argv if a not in ("--window", "background", "foreground")]
def out(value):
    print(json.dumps({"ok": True, "data": value}))
    json.dump(state, open(state_path, "w"))
    sys.exit(0)
def fail(code, message):
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
    sys.exit(1)
cmd = args[1]
if cmd == "close":
    out(True)
if cmd == "open":
    url = args[2]
    dl = scen.get("downloads", {}).get(url)
    if dl:  # Chrome downloads it; the tab keeps its document
        open(os.path.join(dl["dir"], dl["name"]), "wb").write(base64.b64decode(dl["bytes"]))
        out({"url": url})
    url = scen.get("redirects", {}).get(url, url)  # a page that now sends the browser on (a login passed elsewhere)
    if url not in scen.get("pages", {}):
        fail("navigation_failed", "navigation failed")
    state["current"], state["doc"] = url, state.get("doc", 0) + 1  # a new document, as performance.timeOrigin shows
    out({"url": url})
page = scen.get("pages", {}).get(state["current"]) or {}
href = page.get("href", state["current"]) or ""
if cmd == "get":
    out({"url": href, "title": page.get("title", ""), "html": page.get("html", "")}[args[2]])
if cmd == "extract":
    out({"url": href, "title": page.get("title", ""), "content": page.get("text", "")})
if cmd == "find":
    css = args[args.index("--css") + 1]
    entries = ([{"tag": "a", "text": a["text"], "attrs": {"href": a["href"]}} for a in page.get("anchors", [])] if css == "a[href]" else
               [{"tag": "button", "text": c, "attrs": {}} for c in page.get("controls", [])] if css == "a,button,[role=button]" else [])
    if not entries:
        fail("selector_not_found", f"CSS selector {css} matched 0 elements")
    out({"entries": entries, "matches_n": len(entries)})
if cmd == "wait" and args[2] == "text":
    if args[3] in page.get("text", ""):
        out(f"Text {args[3]!r} appeared")
    fail("UNKNOWN", f"Text not found: {args[3]}")
js = args[2]
if js == "performance.timeOrigin":
    out(state.get("doc", 0))
if "pf:find" in js:
    out({"href": href, "title": page.get("title", ""), "doc": state.get("doc", 0), "viewer": bool(page.get("viewer")),
         "meta": page.get("meta", {}), "candidates": [u if isinstance(u, dict) else {"url": u, "why": "stub"} for u in page.get("pdf", [])]})
if "pf:fetch" in js:
    url = json.loads(re.search(r"fetch\((\"[^\"]*\")", js).group(1))
    ans = scen.get("fetch", {}).get(url)
    if ans:
        state["b64"] = ans
        out({"status": 200, "ct": "application/pdf", "pdf": True, "b64len": len(ans)})
    out({"status": 403, "ct": "text/html", "pdf": False, "b64len": 0})
if "pf:chunk" in js:
    a, b = map(int, re.search(r"slice\((\d+),(\d+)\)", js).groups())
    out(state["b64"][a:b] if state["b64"] else None)
if "pf:clear" in js:
    state["b64"] = None
    out(True)
if "pf:viewer-data" in js:
    state["b64"] = page.get("viewer")
    out({"pdf": True, "b64len": len(page["viewer"])} if page.get("viewer") else {"pdf": False})
fail("stub", "unknown call " + json.dumps(args))
'''


class Http(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/arxiv/api/query"):  # arXiv's API, for the ids asked: the latest version is v4
            self.server.arxiv_asked.append(self.path)
            ids = self.path.split("id_list=", 1)[1].split("&", 1)[0].replace("%2C", ",").split(",")
            entries = "".join(f"<entry><id>http://arxiv.org/abs/{i}v4</id><arxiv:comment>Accepted at CVPR 2025</arxiv:comment></entry>"
                              for i in ids)
            body = f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">{entries}</feed>'.encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
            return
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
        cls.server.arxiv_asked = []
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pf-fetch-"))
        self.work = run.Work(self.tmp / "work")
        self.work.results.mkdir(parents=True)
        self.work.started.touch()
        os.utime(self.work.started, (time.time() - 600,) * 2)
        self.dl = self.tmp / "Downloads"
        self.dl.mkdir()
        self.work.set(downloads=str(self.dl), session="pf")
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
                    "STUB_STATE": str(self.tmp / "state.json"), "PAPER_FETCH_CONFIG": str(self.config),
                    "PAPER_FETCH_INSTITUTION_GAP": "0", "PAPER_FETCH_PACE": str(self.tmp / "pace.json"), "PAPER_FETCH_CLICK_WAIT": "3", "PAPER_FETCH_DOWNLOAD_WAIT": "3",
                    "PAPER_FETCH_DISCOVERY_WAIT": "0", "ARXIV_API_URL": f"{self.base}/arxiv/api/query"}
        self.server.arxiv_asked.clear()
        self.scene({})

    def scene(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def result(self, slug, title=TITLE, doi="10.1000/x.1", links=(), **fields):
        """A result file and its links (None: none found yet); fields go into the result as they are."""
        csl = {"type": "article-journal", "title": title, "author": [{"family": "Liu", "given": "Wei"}],
               **({"DOI": doi} if doi else {})}
        path = result_file(self.work.root, slug, csl=csl, **fields)
        if links is not None:
            run.write_links(run.read(path), {"items": list(links)})  # as fulltext_links writes them
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
        return sorted(p.name for p in self.work.results.iterdir() if not p.name.endswith(".json"))

    def handoffs(self, kind=None):
        """The handoff records written, in the log's order (one kind's only, given)."""
        recs = [json.loads((self.work.handoffs / f"{e['id']}.json").read_text()) for e in self.work.events("handoff")]
        return [r for r in recs if not kind or r["kind"] == kind]

    def answer(self, record, word, *argv):
        return call(answer, self.work.handoffs / f"{record['id']}.json", word, *argv, env=self.env)

    def test_one_pass_walks_the_routes_in_order(self):
        nav = "Journals Books Help Search My account " * 40  # a page's start is its navigation
        self.scene({"pages": {"https://doi.org/10.1000/b.2": {"href": "https://pub.example/b", "pdf": ["https://pub.example/b.pdf"],
                                                              "text": f"{nav}\nEarly Access\n{OTHER}\nWei Liu\nVolume: PP"}},
                    "fetch": {"https://pub.example/b.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        recs = [self.result("a", links=[self.link("/paper.pdf"), self.link("/landing", "accepted")]),
                self.result("b", OTHER, "10.1000/b.2"),
                self.result("e", doi=None, links=[self.link("/wrong.pdf", "preprint"), self.link("/paper.pdf", "preprint")])]
        code, lines, err = self.fetch("--pass", "1", *recs)
        self.assertEqual(code, 1, err + json.dumps(lines))
        self.assertEqual(self.files(), ["a.pdf", "b.pdf"], "each candidate's version goes along")
        self.assertEqual(self.events("try"), [("a", "open", "ok"), ("b", "publisher", "ok"), ("e", "preprint", "held")],
                         "a file the check cannot be sure of is held for the paper's agent, and the paper waits")
        self.assertEqual([(h["slug"], h["kind"]) for h in self.handoffs()], [("e", "file"), ("a", "label"), ("b", "label")])
        self.assertEqual(lines[-1]["summary"]["handoffs"], {"file": 1, "label": 2})
        self.assertIn("no_discovery", [x.get("code") for x in lines])
        self.assertEqual(self.fetch("--pass", "1", *recs)[0], 1)
        self.assertEqual((len(self.work.events("try")), len(self.handoffs())), (3, 3), "nothing is tried or handed over twice")
        # what each file is proposed as: the route's version and the site's name, never the link's label
        self.assertEqual([(e["slug"], e["route"], e["proposal"]["title"]) for e in self.work.events("claim") if e["result"] == "claimed"],
                         [("a", "open", "Unknown"), ("b", "publisher", "Published")])
        b = next(e for e in self.work.events("claim") if e["slug"] == "b")
        self.assertEqual((b["evidence"]["url"], b["evidence"]["link"]["url"], b["evidence"]["page"]["href"], b["evidence"]["file"]["excerpt"]),
                         ("https://pub.example/b.pdf", "https://pub.example/b.pdf", "https://pub.example/b", f"{OTHER}\nWei Liu"))
        labels = self.handoffs("label")
        self.assertEqual([(h["slug"], h["evidence"]["proposal"], h["route"]) for h in labels],
                         [("a", "Unknown", "open"), ("b", "Published", "publisher")])
        words = labels[1]["evidence"]["page"]["words"]
        self.assertTrue(words.endswith(f"Early Access {OTHER} Wei Liu Volume: PP"), "the page's words around the title")
        self.assertLess(len(words), 1600, words)
        # The agent refuses the held file: the paper goes on to its next candidate.
        [held] = self.handoffs("file")
        self.assertEqual(self.answer(held, "refuse", "--reason", "page 1 is another paper").code, 0)
        code, lines, err = self.fetch("--pass", "1", *recs)
        self.assertEqual(self.events("try")[-1], ("e", "preprint", "ok"), err)
        folded = run.read(recs[2])
        self.assertEqual((folded["outcome"]["status"], [f["name"] for f in folded["files"]], folded["files"][0]["label"]["title"]),
                         ("got", ["e.preprint.pdf"], "Unknown"), "the pass folds what it did into the results")
        run.label(self.work, "a", "Published-Example", "the publisher's page")
        self.assertEqual(sorted(h["slug"] for h in run.open_handoffs(self.work) if h["kind"] == "label"), ["b", "e"])

    def test_an_arxiv_link_is_fetched_at_its_latest_version(self):
        known = "https://arxiv.org/pdf/2303.11366v2"
        self.scene({"pages": {u: {"viewer": b64(pdf(f"{TITLE}\nWei Liu\narXiv:{u[22:]} [cs.AI]"))}
                              for u in ("https://arxiv.org/pdf/2201.00001v4", known)}})
        arxiv = lambda aid: {"url": f"https://arxiv.org/pdf/{aid}", "source": "arxiv", "version": "preprint", "needs_browser": True}  # noqa: E731
        asked = self.result("asked", doi=None, links=[arxiv("2201.00001")])
        own = {"ids": {"arxiv": "2303.11366", "doi": "10.48550/arXiv.2303.11366"}, "latest": "v2",
               "comment": "Preprint. Under review."}  # identify's answer
        known_rec = self.result("known", doi=None, links=[arxiv("2303.11366")], record_of="preprint", ids=own["ids"],
                                versions={"preprint": own, "published": [], "incomplete": []})
        code, lines, err = self.fetch("--pass", "1", "--route", "preprint", asked, known_rec)
        self.assertEqual(code, 1, err + json.dumps(lines))
        self.assertEqual(len(self.server.arxiv_asked), 1, "one request for the ids identify did not answer")
        self.assertIn("id_list=2201.00001&", self.server.arxiv_asked[0])
        self.assertEqual([(e["slug"], e["url"]) for e in self.work.events("try")],
                         [("asked", "https://arxiv.org/pdf/2201.00001v4"), ("known", known)])
        self.assertEqual([(h["slug"], h["evidence"]["proposal"], h["evidence"]["file"]["arxiv_stamp"], h["evidence"]["page"]["href"],
                           h["evidence"]["page"]["words"]) for h in self.handoffs("label")],
                         [("asked", "Preprint-arXiv-v4", "arXiv:2201.00001v4 [cs.AI]", "https://arxiv.org/abs/2201.00001v4",
                           "Comments: Accepted at CVPR 2025"),
                          ("known", "Preprint-arXiv-v2", "arXiv:2303.11366v2 [cs.AI]", "https://arxiv.org/abs/2303.11366v2",
                           "Comments: Preprint. Under review.")], "arXiv's word on the version: its comment")

    def test_a_page_fetch_cannot_pass_goes_to_the_papers_agent(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/x", "title": "Sign in"},
                              "https://doi.org/10.1000/y.2": {"href": "https://pub.example/y", "pdf": ["https://pub.example/y.pdf"]}},
                    "fetch": {"https://pub.example/y.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        x, y = self.result("x", links=None), self.result("y", OTHER, "10.1000/y.2", links=None)
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", x, y)
        [page] = self.handoffs("page")
        self.assertEqual((code, page["slug"], page["code"], page["taker"], page["evidence"]["page"]["title"]),
                         (1, "x", "no_pdf_link", "paper_agent", "Sign in"), "no title decides it is a gate: the agent looks")
        self.assertEqual(self.files(), ["y.pdf"], "the walk went on with the others")
        self.assertEqual(self.events("try"), [("y", "publisher", "ok")], "a handoff is no try")
        self.assertEqual(run.read(x)["outcome"]["waiting_on"], ["page"])
        # The bulk rerun leaves x to its agent; the agent's own run asks the page again, under the same handoff.
        self.fetch("--pass", "1", "--route", "publisher", x, y)
        self.assertEqual((len(self.handoffs("page")), self.events("try")), (1, [("y", "publisher", "ok")]))
        lines = self.fetch("--pass", "1", "--route", "publisher", "--session", "pf-x", x)[1]
        self.assertEqual([x_["handoff"] for x_ in lines if x_.get("kind") == "page"], [page["id"]])
        # A block holds the paper on its route this pass; a verdict lets it go on.
        r = self.answer(page, "blocked", "--reason", "a bot check on the publisher")
        self.assertEqual((r.code, self.events("try")[-1]), (0, ("x", "publisher", "blocked")), r)
        self.assertTrue(run.held_on_route(self.work, "x", 1))
        self.assertEqual(self.fetch("--pass", "1", x)[1][-1]["summary"]["satisfied"], 0)
        self.assertEqual([t for t in self.events("try") if t[0] == "x"], [("x", "publisher", "blocked")], "held this pass")
        self.fetch("--pass", "2", "--route", "publisher", x)
        [_, again] = self.handoffs("page")
        self.assertEqual(self.answer(again, "no_access", "--reason", "purchase only").code, 0)
        self.assertEqual(self.events("try")[-1], ("x", "publisher", "no_access"))

    def test_a_pdf_link_that_lands_on_a_challenge(self):
        # ScienceDirect: the article page is fine, its PDF link lands on another host's "Are you a robot?"
        gate = "https://pdf.pub-assets.example/main.pdf?sig=1"
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/x", "pdf": ["https://pub.example/x/pdfft"]},
                              "https://pub.example/x/pdfft": {"href": gate, "title": "请稍候…", "text": "Are you a robot?"}}})
        rec = self.result("x", links=None)
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", rec)
        [page] = self.handoffs("page")
        self.assertEqual((code, page["code"], page["evidence"]["page"]["href"], page["evidence"]["page"]["title"]),
                         (1, "refused", gate, "请稍候…"), err + json.dumps(lines))
        self.assertTrue(any(f.endswith("page_words.txt") for f in page["evidence"]["files"]), "the page's text, to read")
        self.assertEqual(lines[0]["code"], "not_prepared", "no links yet: only the page routes try it")
        self.assertEqual(run.read(rec)["outcome"]["status"], "waiting", "a handoff is folded too")
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertEqual(state["current"], "https://pub.example/x/pdfft", "the tab stays where the link led, for the agent")

    def test_the_page_ladder(self):
        c, f, g = "Cardiac Segmentation With Diffusion Models", "Lung Nodule Detection in Low Dose CT", "Retinal Vessel Segmentation Using Transformers"
        d = "Brain Tumor Grading From Whole Slide Images"
        proxied = "https://ieeexplore-ieee-org.proxy.example.edu"
        self.scene({"pages": {
            # refused inside the page, then the opened link downloads: this command files it (no watcher runs)
            "https://doi.org/10.1000/c.3": {"href": "https://pub.example/c", "pdf": ["https://pub.example/c.pdf"]},
            # refused, then the opened link shows a pdf.js viewer
            "https://doi.org/10.1000/f.4": {"href": "https://pub.example/f", "pdf": ["https://pub.example/f.pdf"]},
            "https://pub.example/f.pdf": {"viewer": b64(pdf(f"{f}\nWei Liu"))},
            # refused, then the opened link is an HTML reading page whose own candidate is the PDF (IEEE's stamp.jsp)
            "https://doi.org/10.1109/g.5": {"href": f"{proxied}/document/5", "pdf": ["https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=5"],
                                            "text": f"Early Access Article\n{g}\nPublisher: IEEE"},
            f"{proxied}/stamp/stamp.jsp?arnumber=5": {"pdf": [f"{proxied}/stampPDF/getPDF.jsp?arnumber=5"]}},
            # the DOI's own link downloads: the tab stays where it was, and the file is waited for
            "downloads": {"https://pub.example/c.pdf": {"dir": str(self.dl), "name": "c.pdf", "bytes": b64(pdf(f"{c}\nWei Liu"))},
                          "https://doi.org/10.1000/d.6": {"dir": str(self.dl), "name": "d.pdf", "bytes": b64(pdf(f"{d}\nWei Liu"))}},
            "fetch": {f"{proxied}/stampPDF/getPDF.jsp?arnumber=5": b64(pdf(f"{g}\nWei Liu"))}})
        recs = [self.result("c", c, "10.1000/c.3"), self.result("f", f, "10.1000/f.4"), self.result("g", g, "10.1109/g.5"),
                self.result("d", d, "10.1000/d.6")]
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", *recs)
        self.assertEqual(code, 1, err + json.dumps(lines))
        self.assertEqual(self.files(), ["c.pdf", "d.pdf", "f.pdf", "g.pdf"])
        self.assertEqual(lines[-1]["summary"], {"results": 4, "satisfied": 4, "handoffs": {"label": 4}, "routes": ["publisher"]})
        # c and d came through Downloads, whose claim saw no page: fetch adds how they came
        came = {s: run.arrived(self.work, s, run.md5_of(self.work.results / f"{s}.pdf")) for s in ("c", "d")}
        self.assertEqual([(s, e["route"], e["evidence"]["url"], e["evidence"].get("page", {}).get("href"))
                          for s, e in came.items()],
                         [("c", "publisher", "https://pub.example/c.pdf", "https://pub.example/c"),
                          ("d", "publisher", "https://doi.org/10.1000/d.6", None)])
        self.assertEqual([e["slug"] for e in self.work.events("arrival")], ["c", "d"])
        self.assertEqual(came["c"]["evidence"]["file"]["excerpt"], f"{c}\nWei Liu", "the file's evidence kept")
        self.assertEqual({h["slug"]: h["route"] for h in self.handoffs("label")},
                         {"c": "publisher", "d": "publisher", "f": "publisher", "g": "publisher"})
        g_claim = next(e for e in self.work.events("claim") if e["slug"] == "g")
        self.assertEqual((g_claim["proposal"]["title"], g_claim["evidence"]["url"], g_claim["evidence"]["page"]["href"],
                          g_claim["evidence"]["page"]["words"]),
                         ("Published-IEEE", "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=5",
                          "https://ieeexplore.ieee.org/document/5", f"Early Access Article {g} Publisher: IEEE"),
                         "the proxy taken off before the site is named; the article page speaks, not the reading page")
        request_url = load("fetch").request_url
        self.assertEqual(request_url("https://ieeexplore.ieee.org/x.pdf", f"{proxied}/d/1", "proxy.example.edu"), f"{proxied}/x.pdf")
        self.assertEqual(request_url("http://pub.example/x.pdf", "https://pub.example/a", None), "https://pub.example/x.pdf")

    def test_the_discovery_route(self):
        self.config.write_text(json.dumps({"institution": {"discovery": "https://disc.example/search?vid=X&query={title}"}}))
        search = lambda t: "https://disc.example/search?vid=X&query=" + t.replace(" ", "+")  # noqa: E731
        record_page = "https://disc.example/full?docid=1"
        self.scene({"pages": {search(TITLE): {"anchors": [{"text": TITLE, "href": "https://disc.example/full?docid=arxiv_1"},
                                                          {"text": TITLE.upper(), "href": record_page}, {"text": "Other", "href": "x"}]},
                              "https://disc.example/full?docid=arxiv_1": {}, record_page: {"pdf": ["https://agg.example/doc/pdf"]},
                              search(OTHER): {"anchors": [], "text": "Sign in to get complete results and to request items"}},
                    "fetch": {"https://agg.example/doc/pdf": b64(pdf(f"{TITLE}\nWei Liu"))}})
        code, lines, err = self.fetch("--pass", "1", "--route", "discovery", self.result("p", doi=None), self.result("q", OTHER, doi=None))
        self.assertEqual(self.events("try"), [("p", "discovery", "ok")], "arXiv's record last")
        [page] = self.handoffs("page")
        self.assertEqual((code, page["slug"], page["code"]), (1, "q", "no_record"), err)
        words = next(f for f in page["evidence"]["files"] if f.endswith("page_words.txt"))
        self.assertIn("Sign in to get complete results", Path(words).read_text(),
                      "no wording decides the guest view: the agent reads the page and signs in")
        self.config.write_text(json.dumps({"institution": {"discovery": "https://disc.example/search?vid=X&query=old"}}))
        lines = self.fetch("--pass", "2", "--route", "discovery", self.result("p2", OTHER, doi=None))[1]
        self.assertIn("no_discovery", [x.get("code") for x in lines], "a search URL without {title}: ready.py says how to write it")

    def test_a_snapshot_and_a_start_page(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"html": f"<html><title>{TITLE}</title><h1>{TITLE}</h1>Wei Liu</html>"},
                              "https://pmc.example/1": {"pdf": ["https://pmc.example/1.pdf"]}},
                    "fetch": {"https://pmc.example/1.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        self.assertEqual(self.fetch("--pass", "3", "--route", "snapshot", self.result("s"))[0], 0)
        self.assertEqual(self.fetch("--pass", "1", "--start", "https://pmc.example/1", "--version", "accepted",
                                    self.result("t", OTHER, "10.1000/t.9"))[0], 1, "its label is open: the agent's next step")
        self.assertEqual(self.files(), ["s.html", "t.accepted.pdf"])
        self.assertEqual(self.events("try")[-1], ("t", "start", "ok"), "a start page is never a route's try")
        self.assertEqual([e["proposal"]["title"] for e in self.work.events("claim")], ["Snapshot", "Accepted"],
                         "a start page's version is the one the agent named")
        self.assertEqual([h["slug"] for h in self.handoffs("label")], ["t"], "a snapshot needs no label")

    def test_wait(self):
        self.scene({"pages": {"https://gate.example/login": {"title": "Sign in", "text": "Sign in"}}})
        subprocess.run(["opencli", "browser", "open", "https://gate.example/login", "--session", "pf"], env=self.env, capture_output=True)
        rec = self.result("w")
        code, lines, _ = self.run_("wait", rec, "--timeout", "1")
        self.assertEqual((code, lines[0]["code"]), (1, "timeout"))
        self.assertEqual(self.run_("wait", rec, "--until", "Sign in")[1][0]["code"], "passed")
        (self.work.results / "w.pdf").write_bytes(pdf(TITLE))
        self.assertEqual(self.run_("wait", rec, "--file-only")[1][0]["code"], "arrived")
        self.assertEqual([(e["event"], e["kind"]) for e in self.work.events()], [("handoff", "label")],
                         "waiting records nothing; the fold asks the new file's label")
        self.assertEqual(run.read(rec)["outcome"]["status"], "got", "the result is folded when the wait ends")
        # the paper's agent passed the page fetch handed over on the paper's first candidate (no try yet, only its
        # pass event and the handoff): Chrome downloads it, and the wait files it
        gated = self.result("v", OTHER, "10.1000/v.7")
        self.work.append({"event": "pass", "pass": 1, "slug": "v"})
        run.handoff(self.work, "page", run.read(gated), pass_=1, route="publisher", url="https://doi.org/10.1000/v.7")
        (self.dl / "fulltext.pdf").write_bytes(pdf(f"{OTHER}\nWei Liu"))
        wait = load("wait")
        with mock.patch.object(wait, "STEP", 0.2):
            r = call(wait, gated, "--file-only", "--timeout", "5", env=self.env)
        self.assertEqual((r.code, r.lines[0]["code"], self.files()), (0, "arrived", ["v.pdf", "w.pdf"]), r)

    def test_a_gate_passed_from_another_window(self):
        pages = {"https://gate.example/login": {"title": "Sign in"}, "https://pub.example/a": {"title": "An article"}}
        self.scene({"pages": pages})
        subprocess.run(["opencli", "browser", "open", "https://gate.example/login", "--session", "pf"], env=self.env, capture_output=True)
        self.scene({"pages": pages, "redirects": {"https://gate.example/login": "https://pub.example/a"}})  # signed in elsewhere
        wait = load("wait")
        with mock.patch.object(wait, "STEP", 0.2), mock.patch.object(wait, "PROBE", 0.0):
            r = call(wait, self.result("w"), "--timeout", "5", env=self.env)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["seen"], r.lines[0]["title"]), (0, "passed", "fresh", "An article"),
                         "the gate's tab never changed: a fresh look at its address saw the login")

    def test_smoke(self):
        for name, first in (("fetch", "Walk one pass of the chain"), ("wait", "Wait at a gate")):
            r = smoke(name, "--help")
            self.assertEqual(r.code, 0, r)
            self.assertIn(first, r.out)


if __name__ == "__main__":
    unittest.main()
