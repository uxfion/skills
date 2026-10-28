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
state = json.load(open(state_path)) if os.path.exists(state_path) else {"current": None, "b64": None}
argv = sys.argv[1:]  # browser <command> [args...] --session p2z [--window W]
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
if cmd == "open":
    url = args[2]
    dl = scen.get("downloads", {}).get(url)
    if dl:  # Chrome downloads it; the tab keeps its document
        open(os.path.join(dl["dir"], dl["name"]), "wb").write(base64.b64decode(dl["bytes"]))
        out({"url": url})
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
if "p2z:find" in js:
    out({"href": href, "title": page.get("title", ""), "doc": state.get("doc", 0), "viewer": bool(page.get("viewer")),
         "meta": page.get("meta", {}), "candidates": [u if isinstance(u, dict) else {"url": u, "why": "stub"} for u in page.get("pdf", [])]})
if "p2z:fetch" in js:
    url = json.loads(re.search(r"fetch\((\"[^\"]*\")", js).group(1))
    ans = scen.get("fetch", {}).get(url)
    if ans:
        state["b64"] = ans
        out({"status": 200, "ct": "application/pdf", "pdf": True, "b64len": len(ans)})
    out({"status": 403, "ct": "text/html", "pdf": False, "b64len": 0})
if "p2z:chunk" in js:
    a, b = map(int, re.search(r"slice\((\d+),(\d+)\)", js).groups())
    out(state["b64"][a:b] if state["b64"] else None)
if "p2z:clear" in js:
    state["b64"] = None
    out(True)
if "p2z:viewer-data" in js:
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
                    "PAPER_TO_ZOTERO_INSTITUTION_GAP": "0", "PAPER_TO_ZOTERO_CLICK_WAIT": "3", "PAPER_TO_ZOTERO_DOWNLOAD_WAIT": "3",
                    "PAPER_TO_ZOTERO_DISCOVERY_WAIT": "0", "ARXIV_API_URL": f"{self.base}/arxiv/api/query"}
        self.server.arxiv_asked.clear()
        self.scene({})

    def scene(self, scenario):
        self.scenario.write_text(json.dumps(scenario))

    def record(self, slug, title=TITLE, doi="10.1000/x.1", links=(), **fields):
        item = {"itemType": "journalArticle", "title": title, **({"DOI": doi} if doi else {}),
                "creators": [{"creatorType": "author", "lastName": "Liu", "firstName": "Wei"}]}
        rec = run.Record(self.work.records / f"{slug}.json", {"item": item, **fields})
        run.stamp(rec, "links", {"items": list(links)})  # as prepare writes them
        rec.save()
        return str(rec.path)

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
        nav = "Journals Books Help Search My account " * 40  # a page's start is its navigation
        self.scene({"pages": {"https://doi.org/10.1000/b.2": {"href": "https://pub.example/b", "pdf": ["https://pub.example/b.pdf"],
                                                              "text": f"{nav}\nEarly Access\n{OTHER}\nWei Liu\nVolume: PP"}},
                    "fetch": {"https://pub.example/b.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        recs = [self.record("a", links=[self.link("/paper.pdf"), self.link("/landing", "accepted")]),
                self.record("b", OTHER, "10.1000/b.2"),
                self.record("e", doi=None, links=[self.link("/wrong.pdf", "preprint"), self.link("/paper.pdf", "preprint")])]
        code, lines, err = self.fetch("--pass", "1", *recs)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.files(), ["a.pdf", "b.pdf", "e.preprint.pdf"], "each candidate's version goes along")
        self.assertEqual(self.events("try"), [("a", "open", "ok"), ("b", "publisher", "ok"), ("e", "preprint", "wrong_file"),
                                              ("e", "preprint", "ok")])
        self.assertEqual((lines[-1]["summary"]["with_file"], [x["code"] for x in lines if x.get("route") == "discovery" and "event" not in x]),
                         (3, ["no_discovery"]))
        self.assertEqual(self.fetch("--pass", "1", *recs)[0], 0)
        self.assertEqual(len(self.work.events("try")), 4, "nothing is tried twice")
        # what each file is proposed as: the route's version and the site's name, never the link's label
        self.assertEqual([(e["slug"], e["route"], e["proposal"]["title"]) for e in self.work.events("claim") if e["result"] == "claimed"],
                         [("a", "open", "Unknown"), ("b", "publisher", "Published"), ("e", "preprint", "Preprint")])
        b = next(e for e in self.work.events("claim") if e["slug"] == "b")
        self.assertEqual((b["evidence"]["url"], b["evidence"]["link"]["url"], b["evidence"]["page"]["href"], b["evidence"]["file"]["excerpt"]),
                         ("https://pub.example/b.pdf", "https://pub.example/b.pdf", "https://pub.example/b", f"{OTHER}\nWei Liu"))
        words = b["evidence"]["page"]["words"]
        self.assertTrue(words.endswith(f"Early Access {OTHER} Wei Liu Volume: PP"), "the page's words around the title")
        self.assertLess(len(words), 1600, words)
        labels = [x for x in lines if x.get("code") == "to_label"]
        self.assertEqual([(x["slug"], x["proposal"], x["route"]) for x in labels],
                         [("a", "Unknown", "open"), ("b", "Published", "publisher"), ("e", "Preprint", "preprint")])
        self.assertIn("Early Access", labels[1]["words"], "the host's word on the line")
        self.assertEqual(lines[-1]["summary"]["to_label"], 3)
        rec = run.read(recs[0])
        rec["label"] = {"title": "Published-Example", "by": "agent", "why": "the publisher's page"}
        rec.save()
        self.assertEqual([x["slug"] for x in self.fetch("--pass", "1", *recs)[1] if x.get("code") == "to_label"], ["b", "e"])

    def test_an_arxiv_link_is_fetched_at_its_latest_version(self):
        known = "https://arxiv.org/pdf/2303.11366v2"
        self.scene({"pages": {u: {"viewer": b64(pdf(f"{TITLE}\nWei Liu\narXiv:{u[22:]} [cs.AI]"))}
                              for u in ("https://arxiv.org/pdf/2201.00001v4", known)}})
        arxiv = lambda aid: {"url": f"https://arxiv.org/pdf/{aid}", "source": "arxiv", "version": "preprint", "needs_browser": True}  # noqa: E731
        asked = self.record("asked", doi=None, links=[arxiv("2201.00001")])
        rec = run.Record(self.work.records / "known.json", {"item": {"itemType": "preprint", "title": TITLE, "archiveID": "arXiv:2303.11366",
                                                                      "creators": [{"creatorType": "author", "lastName": "Liu"}]}})
        run.stamp(rec, "links", {"items": [arxiv("2303.11366")]})
        run.stamp(rec, "published_candidates", {"items": [], "arxiv_version": "v2", "comment": "Preprint. Under review."})  # prepare's answer
        rec.save()
        code, lines, err = self.fetch("--pass", "1", "--route", "preprint", asked, str(rec.path))
        self.assertEqual(code, 0, err + json.dumps(lines))
        self.assertEqual(len(self.server.arxiv_asked), 1, "one request for the ids prepare did not answer")
        self.assertIn("id_list=2201.00001&", self.server.arxiv_asked[0])
        self.assertEqual([(e["slug"], e["url"]) for e in self.work.events("try")],
                         [("asked", "https://arxiv.org/pdf/2201.00001v4"), ("known", known)])
        self.assertEqual([(x["slug"], x["proposal"], x["stamp"], x["page"], x["words"]) for x in lines if x.get("code") == "to_label"],
                         [("asked", "Preprint-arXiv-v4", "arXiv:2201.00001v4 [cs.AI]", "https://arxiv.org/abs/2201.00001v4",
                           "Comments: Accepted at CVPR 2025"),
                          ("known", "Preprint-arXiv-v2", "arXiv:2303.11366v2 [cs.AI]", "https://arxiv.org/abs/2303.11366v2",
                           "Comments: Preprint. Under review.")], "arXiv's word on the version: its comment")

    def test_a_page_the_browser_cannot_pass_stops_until_the_agent_decides(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/x", "title": "Sign in"}}})
        rec = self.record("x", links=[self.link("/wrong.pdf", "preprint")])
        code, lines, _ = self.fetch("--pass", "1", rec)
        stop = next(x for x in lines if x.get("code") == "stopped")
        self.assertEqual((code, stop["why"], stop["url"]), (1, "no_pdf_link", "https://pub.example/x"))
        self.assertEqual((self.events("try"), self.events("stop")), ([], [("x", "publisher", "no_pdf_link")]), "a stop is no try")
        self.env["PAPER_TO_ZOTERO_DOWNLOAD_WAIT"] = "30"
        began = time.monotonic()
        self.assertEqual(self.fetch("--pass", "1", rec)[0], 1, "the page is asked again on a rerun")
        self.assertLess(time.monotonic() - began, 15, "the tab's own page opened again is a new document, not a download")
        self.assertEqual(self.fetch("--pass", "1", "--verdict", "no_access", rec)[0], 0)
        self.assertEqual(self.fetch("--pass", "1", rec)[0], 0)
        self.assertEqual(self.events("try"), [("x", "publisher", "no_access"), ("x", "preprint", "wrong_file")])
        other = self.record("y", OTHER, "10.1000/y.2")
        self.assertEqual(self.fetch("--pass", "1", "--route", "publisher", "--verdict", "gate_timeout", other)[0], 0)
        self.assertEqual(self.fetch("--pass", "1", "--route", "publisher", other)[0], 0, "the route is closed for it")
        code, lines, _ = self.fetch("--pass", "2", "--verdict", "no_access", rec)
        self.assertEqual((code, lines[0]["code"]), (1, "nothing_stopped"))

    def test_a_pdf_link_that_opens_a_gate_stops_in_front_of_the_user(self):
        # ScienceDirect: the article page is fine, its PDF link lands on another host's "Are you a robot?"
        gate = "https://pdf.pub-assets.example/main.pdf?sig=1"
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"href": "https://pub.example/x", "pdf": ["https://pub.example/x/pdfft"]},
                              "https://pub.example/x/pdfft": {"href": gate, "title": "请稍候…", "text": "Are you a robot?"}}})
        rec = self.record("x")
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", rec)
        stop = next((x for x in lines if x.get("code") == "stopped"), None)
        self.assertEqual((code, stop and stop["why"], stop and stop["gate"], stop and stop["url"]), (1, "gate", True, gate),
                         err + json.dumps(lines))
        state = json.loads((self.tmp / "state.json").read_text())
        self.assertEqual(state["current"], "https://pub.example/x/pdfft", "the PDF link, not the article page, opens in front")

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
        recs = [self.record("c", c, "10.1000/c.3"), self.record("f", f, "10.1000/f.4"), self.record("g", g, "10.1109/g.5"),
                self.record("d", d, "10.1000/d.6")]
        code, lines, err = self.fetch("--pass", "1", "--route", "publisher", *recs)
        self.assertEqual(code, 0, err + json.dumps(lines))
        self.assertEqual(self.files(), ["c.pdf", "d.pdf", "f.pdf", "g.pdf"])
        # c and d came through Downloads, whose claim saw no page: fetch adds how they came
        came = {s: run.arrived(self.work, s, run.md5_of(self.work.records / f"{s}.pdf")) for s in ("c", "d")}
        self.assertEqual([(s, e["route"], e["evidence"]["url"], e["evidence"].get("page", {}).get("href"))
                          for s, e in came.items()],
                         [("c", "publisher", "https://pub.example/c.pdf", "https://pub.example/c"),
                          ("d", "publisher", "https://doi.org/10.1000/d.6", None)])
        self.assertEqual([e["slug"] for e in self.work.events("arrival")], ["c", "d"])
        self.assertEqual(came["c"]["evidence"]["file"]["excerpt"], f"{c}\nWei Liu", "the file's evidence kept")
        self.assertEqual({x["slug"]: x["route"] for x in lines if x.get("code") == "to_label"},
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
        self.scene({"pages": {search(OTHER): {"anchors": [], "text": "Sign in to get complete results and to request items"}}})
        code, lines, _ = self.fetch("--pass", "2", "--route", "discovery", self.record("q", OTHER, doi=None))
        self.assertEqual((code, self.events("stop")[-1][2]), (1, "sign_in"), "a guest's partial results prove nothing")

    def test_a_snapshot_and_a_start_page(self):
        self.scene({"pages": {"https://doi.org/10.1000/x.1": {"html": f"<html><title>{TITLE}</title><h1>{TITLE}</h1>Wei Liu</html>"},
                              "https://pmc.example/1": {"pdf": ["https://pmc.example/1.pdf"]}},
                    "fetch": {"https://pmc.example/1.pdf": b64(pdf(f"{OTHER}\nWei Liu"))}})
        self.assertEqual(self.fetch("--pass", "3", "--route", "snapshot", self.record("s"))[0], 0)
        self.assertEqual(self.fetch("--pass", "1", "--start", "https://pmc.example/1", "--version", "accepted",
                                    self.record("t", OTHER, "10.1000/t.9"))[0], 0)
        self.assertEqual(self.files(), ["s.html", "t.accepted.pdf"])
        self.assertEqual(self.events("try")[-1], ("t", "start", "ok"), "a start page is never a route's try")
        self.assertEqual([e["proposal"]["title"] for e in self.work.events("claim")], ["Snapshot", "Accepted"],
                         "a start page's version is the one the agent named")
        lines = self.fetch("--pass", "3", "--route", "snapshot", self.record("s"))[1]
        self.assertNotIn("s", [x["slug"] for x in lines if x.get("code") == "to_label"], "a snapshot needs no label")

    def test_wait(self):
        self.scene({"pages": {"https://gate.example/login": {"title": "Sign in", "text": "Sign in"}}})
        subprocess.run(["opencli", "browser", "open", "https://gate.example/login", "--session", "p2z"], env=self.env, capture_output=True)
        rec = self.record("w")
        code, lines, _ = self.run_("wait", rec, "--timeout", "1")
        self.assertEqual((code, lines[0]["code"]), (1, "timeout"))
        self.assertEqual(self.run_("wait", rec, "--until", "Sign in")[1][0]["code"], "passed")
        (self.work.records / "w.pdf").write_bytes(pdf(TITLE))
        self.assertEqual(self.run_("wait", rec, "--file-only")[1][0]["code"], "arrived")
        self.assertEqual(self.work.events(), [], "waiting records nothing")


if __name__ == "__main__":
    unittest.main()
