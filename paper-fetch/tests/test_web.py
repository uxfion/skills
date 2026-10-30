# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pflib.web: requests and their pacing (in one process, and across processes through pace.json), and
what paper pages declare. Every request goes to a local server; "localhost" and "127.0.0.1" name it as two hosts."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from helpers import SCRIPTS, closed_port

from pflib import web


class Site:
    """A local web server: routes {path: (status, headers, body) or handler -> that}; requests are recorded."""

    def __init__(self):
        site = self
        self.routes, self.asked = {}, []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.asked.append((self.headers.get("Host"), self.path, dict(self.headers)))
                route = site.routes.get(self.path.split("?", 1)[0], (404, {}, b"not here"))
                status, headers, body = route(self) if callable(route) else route
                if status is None:   # the handler wrote the reply itself
                    return
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_address[1]
        self.base, self.other = f"http://127.0.0.1:{port}", f"http://localhost:{port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def paths(self):
        return [p for _, p, _ in self.asked]


def echo(handler):
    return 200, {"Content-Type": "application/json"}, json.dumps(dict(handler.headers)).encode()


def garbage(handler):
    handler.wfile.write(b"garbage\r\n\r\n")
    return None, None, None


class Get(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = Site()
        s = cls.site
        s.routes.update({
            "/echo": echo,
            "/page": (200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>page</html>"),
            "/big": (200, {}, b"x" * 10000),
            "/hop": (302, {"Location": s.other + "/page"}, b""),
            "/self": (302, {"Location": s.base + "/page"}, b""),
            "/hop429": (302, {"Location": s.other + "/429"}, b""),
            "/429": (429, {"Retry-After": "7"}, b"slow down"),
            "/gone": (302, {"Location": s.other + "/missing"}, b""),
            "/garbage": garbage,
        })

    @classmethod
    def tearDownClass(cls):
        cls.site.close()

    def setUp(self):
        self.site.asked.clear()
        self.pacer = web.Pacer()
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.enterContext(mock.patch.dict(web.GAPS, {"t.example": 0, "localhost": 0, "127.0.0.1": 0}))

    def get(self, path, **kwargs):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            out = web.get(self.site.base + path, host=kwargs.pop("host", "t.example"), pacer=self.pacer, **kwargs)
        self.err = err.getvalue()
        return out

    def test_the_user_agent_and_headers_go_out_and_a_caller_can_replace_them(self):
        _, _, body, _ = self.get("/echo", headers={"Accept": "application/json"})
        sent = json.loads(body)
        self.assertEqual((sent["User-Agent"], sent["Accept"]), (web.USER_AGENT, "application/json"))
        _, _, body, _ = self.get("/echo", headers={"User-Agent": web.BROWSER_UA})
        self.assertEqual(json.loads(body)["User-Agent"], web.BROWSER_UA)

    def test_an_error_status_is_returned_with_the_url_that_gave_it(self):
        status, headers, body, final = self.get("/gone")
        self.assertEqual((status, final, body), (404, self.site.other + "/missing", b"not here"))

    def test_the_log_line_leaves_out_the_query(self):
        status, _, _, final = self.get("/echo", params={"api_key": "SECRET", "q": "x"})
        self.assertEqual(status, 200)
        self.assertIn("api_key=SECRET", final)
        self.assertIn("/echo -> 200", self.err)
        self.assertNotIn("SECRET", self.err)

    def test_max_bytes_caps_the_body(self):
        self.assertEqual(len(self.get("/big", max_bytes=100)[2]), 100)
        self.assertEqual(len(self.get("/big")[2]), 10000)

    def test_a_redirect_to_another_host_is_paced_under_that_host(self):
        web.GAPS["localhost"] = 0.3
        self.pacer.wait("localhost")
        start = time.monotonic()
        status, _, body, final = self.get("/hop")
        self.assertGreaterEqual(time.monotonic() - start, 0.25)
        self.assertEqual((status, body, final), (200, b"<html>page</html>", self.site.other + "/page"))
        self.assertEqual(set(self.pacer.last), {"t.example", "localhost"})

    def test_a_redirect_on_the_same_host_is_one_request_to_pace(self):
        web.GAPS["t.example"] = 0.5
        start = time.monotonic()
        self.assertEqual(self.get("/self")[0], 200)
        self.assertLess(time.monotonic() - start, 0.4)
        self.assertEqual(self.site.paths(), ["/self", "/page"])

    def test_a_429_stops_the_host_that_answered_and_it_is_not_asked_again(self):
        with self.assertRaises(web.Blocked) as caught:
            self.get("/hop429")
        self.assertEqual((caught.exception.host, caught.exception.retry_after), ("localhost", 7.0))
        self.assertEqual(self.pacer.stopped, {"localhost": 7.0})
        with self.assertRaises(web.Blocked):
            self.get("/hop429")
        self.assertEqual(self.site.paths().count("/429"), 1, "the stopped host is not asked")
        self.assertEqual(self.get("/page")[0], 200, "the first host is not stopped")
        self.pacer.stop("t.example")
        with self.assertRaises(web.Blocked):
            self.get("/page")
        self.assertEqual(self.site.paths().count("/page"), 1)

    def test_network_failures_raise_oserror(self):
        with self.assertRaises(OSError):
            web.get(f"http://127.0.0.1:{closed_port()}/x", pacer=self.pacer)
        with self.assertRaises(OSError):
            self.get("/garbage")

    def test_a_work_directory_pacer_records_the_request_and_the_429(self):
        work = Path(tempfile.mkdtemp(prefix="pf-web-"))
        self.pacer = web.Pacer(work)
        self.get("/page")
        with self.assertRaises(web.Blocked) as caught:
            self.get("/hop429")
        self.assertAlmostEqual(caught.exception.until, time.time() + 7, delta=2)
        state = json.loads((work / "pace.json").read_text())
        self.assertEqual(set(state["last"]), {"t.example", "localhost"})
        self.assertEqual(state["stopped"]["localhost"]["retry_after"], 7.0)
        self.assertEqual(caught.exception.fields()["host"], "localhost")
        self.assertRegex(caught.exception.fields()["until"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_a_page_read_through_get(self):
        page = '<meta http-equiv="Content-Type" content="text/html"><meta name="citation_title" content="超声图像分割">'
        self.site.routes["/zh"] = (200, {"Content-Type": "text/html; charset=GBK"}, page.encode("gbk"))
        status, headers, body, final = self.get("/zh")
        self.assertEqual(web.page_meta(body, final, headers)["title"], "超声图像分割")


class Pacing(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="pf-pace-"))
        self.enterContext(mock.patch.dict(web.GAPS, {"h": 0.3}))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def state(self):
        return json.loads((self.work / "pace.json").read_text())

    def test_in_process_the_gap_holds_and_a_stop_lasts(self):
        pacer = web.Pacer()
        pacer.wait("h")
        start = time.monotonic()
        pacer.wait("h")
        self.assertGreaterEqual(time.monotonic() - start, 0.28)
        pacer.stop("h", 0.01)
        time.sleep(0.05)
        with self.assertRaises(web.Blocked) as caught:
            pacer.wait("h")
        self.assertEqual((caught.exception.retry_after, caught.exception.until), (0.01, None))
        self.assertFalse((self.work / "pace.json").exists())

    def test_a_second_pacer_on_the_work_directory_waits(self):
        a, b = web.Pacer(self.work), web.Pacer(self.work)
        a.wait("h")
        start = time.monotonic()
        b.wait("h")
        self.assertGreaterEqual(time.monotonic() - start, 0.28)
        start = time.monotonic()
        b.wait("other")
        self.assertLess(time.monotonic() - start, 0.1, "another host has its own gap")
        self.assertEqual(set(self.state()["last"]), {"h", "other"})
        self.assertEqual((set(a.last), set(b.last)), ({"h"}, {"h", "other"}), "the file as of each one's last wait")

    def test_a_429_seen_by_one_stops_the_other_and_keeps_retry_after(self):
        a, b = web.Pacer(self.work), web.Pacer(self.work)
        self.assertEqual(a.stop("h", 30.0)[0], 30.0)
        with self.assertRaises(web.Blocked) as caught:
            b.wait("h")
        self.assertEqual(caught.exception.retry_after, 30.0)
        self.assertAlmostEqual(caught.exception.until, time.time() + 30, delta=2)
        self.assertEqual(b.stopped, {"h": 30.0})
        with self.assertRaises(web.Blocked):
            web.Pacer(self.work).wait("h")   # a rerun of the script
        b.wait("other")

    def test_without_retry_after_the_stop_lasts_STOP(self):
        web.Pacer(self.work).stop("h")
        with self.assertRaises(web.Blocked) as caught:
            web.Pacer(self.work).wait("h")
        self.assertIsNone(caught.exception.retry_after)
        self.assertAlmostEqual(caught.exception.until, time.time() + web.STOP, delta=2)

    def test_a_stop_ends(self):
        a, b = web.Pacer(self.work), web.Pacer(self.work)
        a.stop("h", 0.2)
        time.sleep(0.3)
        b.wait("h")
        self.assertNotIn("h", self.state()["stopped"])

    def test_a_429_met_while_waiting_stops_the_waiter(self):
        a, b, c = web.Pacer(self.work), web.Pacer(self.work), web.Pacer(self.work)
        a.wait("h")
        threading.Timer(0.1, c.stop, ("h", 9.0)).start()
        with self.assertRaises(web.Blocked) as caught:
            b.wait("h")
        self.assertEqual(caught.exception.retry_after, 9.0)

    def test_an_unreadable_pace_file_starts_afresh(self):
        (self.work / "pace.json").write_text("{not json")
        web.Pacer(self.work).wait("h")
        self.assertIn("h", self.state()["last"])

    def test_the_institution_gap(self):
        self.assertEqual(web.gap(web.INSTITUTION), 15.0)
        with mock.patch.dict("os.environ", {"PAPER_FETCH_INSTITUTION_GAP": "2.5"}):
            self.assertEqual(web.gap("institution"), 2.5)
        self.assertEqual(web.gap("www.medrxiv.org"), 10.0)
        self.assertEqual(web.gap("unknown.example"), web.DEFAULT_GAP)

    def test_an_object_with_a_root_names_the_work_directory(self):
        class Work:
            root = self.work
        web.Pacer(Work()).wait("h")
        self.assertIn("h", self.state()["last"])
        with self.assertRaises(ValueError):
            with web.Pacer().state():
                pass


COUNT = """
import sys
sys.path.insert(0, sys.argv[1])
from pflib import web
pacer = web.Pacer(sys.argv[2])
for _ in range(int(sys.argv[3])):
    with pacer.state() as state:
        state["n"] = state.get("n", 0) + 1
"""

SPACED = """
import sys, time
sys.path.insert(0, sys.argv[1])
from pflib import web
web.GAPS["h"] = float(sys.argv[3])
pacer = web.Pacer(sys.argv[2])
for _ in range(3):
    pacer.wait("h")
    print(time.time(), flush=True)
"""


class Lock(unittest.TestCase):
    """Two processes on one pace.json (the work directory is under $TMPDIR: point it at /mnt/c to try drvfs)."""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="pf-lock-")

    def children(self, code, *argv):
        procs = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), self.work, *map(str, argv)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outs = [p.communicate(timeout=120) for p in procs]
        for p, (_, err) in zip(procs, outs):
            self.assertEqual(p.returncode, 0, err)
        return [out for out, _ in outs]

    def test_two_processes_do_not_lose_updates(self):
        self.children(COUNT, 200)
        self.assertEqual(json.loads((Path(self.work) / "pace.json").read_text())["n"], 400)

    def test_two_processes_keep_the_gap_between_them(self):
        times = sorted(float(t) for out in self.children(SPACED, 0.3) for t in out.split())
        self.assertEqual(len(times), 6)
        self.assertGreaterEqual(min(b - a for a, b in zip(times, times[1:])), 0.15, times)
        self.assertGreaterEqual(times[-1] - times[0], 5 * 0.3 - 0.1)


SPRINGER = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>Ultrasound Segmentation with Foundation Models | SpringerLink</title>
<meta name="citation_title" content="Ultrasound Segmentation with
     Foundation Models">
<meta name="citation_publisher" content="Springer Nature Switzerland">
<meta name="citation_inbook_title" content="Medical Image Computing and Computer Assisted Intervention – MICCAI 2023">
<meta name="citation_conference_title" content="International Conference on Medical Image Computing and Computer-Assisted Intervention">
<meta name="citation_publication_date" content="2023/10/01">
<meta name="citation_firstpage" content="45"><meta name="citation_lastpage" content="55">
<meta name="citation_doi" content="10.1007/978-3-031-43987-2_5">
<meta name="citation_isbn" content="978-3-031-43987-2">
<meta name="citation_pdf_url" content="https://link.springer.com/content/pdf/10.1007/978-3-031-43987-2_5.pdf">
<meta name="citation_author" content="Wang, Li">
<meta name="citation_author_institution" content="Fudan University">
<meta name="citation_author" content="Zhang, Wei">
<meta name="citation_author" content="M&uuml;ller, Anna">
<meta name="citation_keywords" content="Ultrasound; Segmentation; Foundation model">
<meta property="og:description" content="Foundation models promise...">
<meta name="dc.identifier" content="doi:10.1007/978-3-031-43987-2_5">
</head><body><p>…</p></body></html>"""

IEEE = """<!DOCTYPE html><html><head>
<meta property="og:title" content="Deep Residual Learning for Image Recognition">
<meta property="og:description" content="Deeper neural networks are more difficult to train.">
<meta name="Description" content="IEEE Xplore, delivering full text access">
<meta name="Keywords" content="Training,Degradation, Complexity theory">
<meta property="og:site_name" content="IEEE Xplore">
<script>xplGlobal.document.metadata={"title":"Deep Residual Learning","doi":"10.1109/CVPR.2016.90"};</script>
</head><body><div id="LayoutWrapper"></div></body></html>"""

ARXIV = """<html><head>
<meta name="citation_title" content="Attention Is All You Need" />
<meta name="citation_author" content="Vaswani, Ashish" />
<meta name="citation_author" content="Shazeer, Noam" />
<meta name="citation_date" content="2017/06/12" />
<meta name="citation_online_date" content="2023/08/02" />
<meta name="citation_pdf_url" content="http://arxiv.org/pdf/1706.03762" />
<meta name="citation_arxiv_id" content="1706.03762" />
<meta name="citation_abstract" content="The dominant sequence transduction models are based on complex recurrent networks." />
</head><body></body></html>"""

NEURIPS = """<html><head>
<meta name="citation_title" content="Denoising Diffusion Probabilistic Models">
<meta name="citation_author" content="Ho, Jonathan">
<meta name="citation_author" content="Jain, Ajay">
<meta name="citation_journal_title" content="Advances in Neural Information Processing Systems">
<meta name="citation_volume" content="33">
<meta name="citation_firstpage" content="6840"><meta name="citation_lastpage" content="6851">
<meta name="citation_pdf_url" content="/paper_files/paper/2020/file/4c5bcfec8584af0d967f1ab10179ca4b-Paper.pdf">
<meta name="citation_publication_date" content="2020">
</head></html>"""
NEURIPS_URL = "https://proceedings.neurips.cc/paper_files/paper/2020/hash/4c5bcfec8584af0d967f1ab10179ca4b-Abstract.html"


class PageMeta(unittest.TestCase):
    def test_a_springer_chapter(self):
        m = web.page_meta(SPRINGER.encode(), "https://link.springer.com/chapter/10.1007/978-3-031-43987-2_5")
        self.assertEqual(m["title"], "Ultrasound Segmentation with Foundation Models")
        self.assertEqual(m["authors"], [{"lastName": "Wang", "firstName": "Li"}, {"lastName": "Zhang", "firstName": "Wei"},
                                        {"lastName": "Müller", "firstName": "Anna"}])
        self.assertEqual((m["venue"], m["venue_kind"]),
                         ("International Conference on Medical Image Computing and Computer-Assisted Intervention", "conference"))
        self.assertEqual(m["meta"]["citation_inbook_title"], ["Medical Image Computing and Computer Assisted Intervention – MICCAI 2023"])
        self.assertEqual((m["date"], m["pages"], m["doi"], m["isbn"]), ("2023-10-01", "45-55", "10.1007/978-3-031-43987-2_5",
                                                                        "978-3-031-43987-2"))
        self.assertEqual(m["publisher"], "Springer Nature Switzerland")
        self.assertEqual(m["pdf_url"], "https://link.springer.com/content/pdf/10.1007/978-3-031-43987-2_5.pdf")
        self.assertEqual(m["keywords"], ["Ultrasound", "Segmentation", "Foundation model"])
        self.assertEqual(m["abstract"], "Foundation models promise...")

    def test_an_ieee_page_has_open_graph_only(self):
        m = web.page_meta(IEEE, "https://ieeexplore.ieee.org/document/7780459")
        self.assertEqual(m["title"], "Deep Residual Learning for Image Recognition")
        self.assertEqual(m["abstract"], "Deeper neural networks are more difficult to train.")
        self.assertEqual(m["keywords"], ["Training", "Degradation", "Complexity theory"])
        self.assertEqual((m["authors"], m["doi"], m["pdf_url"], m["venue"], m["date"]), ([], None, None, None, None))
        self.assertNotIn("citation_title", m["meta"])
        self.assertEqual(m["meta"]["og:site_name"], ["IEEE Xplore"])

    def test_an_arxiv_page(self):
        m = web.page_meta(ARXIV, "https://arxiv.org/abs/1706.03762")
        self.assertEqual((m["title"], m["date"], m["pdf_url"]), ("Attention Is All You Need", "2017-06-12",
                                                                 "http://arxiv.org/pdf/1706.03762"))
        self.assertEqual([a["lastName"] for a in m["authors"]], ["Vaswani", "Shazeer"])
        self.assertEqual((m["venue"], m["venue_kind"], m["doi"]), (None, None, None))
        self.assertTrue(m["abstract"].startswith("The dominant"))
        self.assertEqual(m["meta"]["citation_arxiv_id"], ["1706.03762"])

    def test_a_neurips_page_names_its_proceedings_as_a_journal_and_links_its_pdf_relatively(self):
        m = web.page_meta(NEURIPS, NEURIPS_URL)
        self.assertEqual((m["venue"], m["venue_kind"]), ("Advances in Neural Information Processing Systems", "conference"))
        self.assertEqual(m["pdf_url"], "https://proceedings.neurips.cc/paper_files/paper/2020/file/"
                                       "4c5bcfec8584af0d967f1ab10179ca4b-Paper.pdf")
        self.assertEqual((m["volume"], m["pages"], m["date"]), ("33", "6840-6851", "2020"))

    def test_a_journal_page_with_dublin_core_and_a_pdf_alternate(self):
        page = """<html><head><base href="/journal/v2/">
        <meta name="DC.Title" content="A study"><meta name="DC.Creator" content="Roe, Richard">
        <meta name="DC.Creator" content="王小明"><meta name="DC.Identifier" content="ISSN 1234-5678">
        <meta name="DC.Identifier" content="info:doi/10.5555/ABC.1"><meta name="DC.Publisher" content="Society">
        <meta name="citation_journal_title" content="Journal of Tests"><meta name="DC.Date" content="2021-03">
        <meta name="citation_firstpage" content="7">
        <link rel="alternate" type="application/pdf; charset=binary" href="a.pdf">
        <link rel="alternate" type="application/rss+xml" href="feed.xml"></head></html>"""
        m = web.page_meta(page, "https://journal.example.org/article/1")
        self.assertEqual((m["title"], m["doi"], m["publisher"], m["date"], m["pages"]),
                         ("A study", "10.5555/abc.1", "Society", "2021-03", "7"))
        self.assertEqual(m["authors"], [{"lastName": "Roe", "firstName": "Richard"}, {"name": "王小明"}])
        self.assertEqual((m["venue"], m["venue_kind"]), ("Journal of Tests", "journal"))
        self.assertEqual(m["pdf_url"], "https://journal.example.org/journal/v2/a.pdf")

    def test_a_page_without_meta(self):
        m = web.page_meta(b"<html><head><title>Hi</title></head><body><p>x</p></body></html>", "https://x.org/")
        self.assertEqual(m, {"title": None, "authors": [], "date": None, "doi": None, "venue": None, "venue_kind": None,
                             "publisher": None, "volume": None, "issue": None, "pages": None, "issn": None,
                             "isbn": None, "pdf_url": None, "keywords": [], "abstract": None, "meta": {}})
        self.assertEqual(web.page_meta(b"", "https://x.org/")["meta"], {})

    def test_broken_html_gives_what_it_can(self):
        page = (b"<html><head><meta name=citation_title content=Broken&amp;Fine>"
                b"<meta name='citation_authors' content='Doe, J.; Roe, R.'>"
                b"<meta name=\"citation_pdf_url\" content=\"javascript:void(0)\">"
                b"</head><body><div><p>unclosed <b>tags <<< & \xff\xfe <a href=x>"
                b"<meta name=\"citation_pdf_url\" content=\"../files/paper.pdf\">"
                b"<meta name=\"citation_doi\" content=\"https://doi.org/10.1234/XYZ\"> <!-- unterminated <meta name=x content=y>")
        m = web.page_meta(page, "https://site.example/papers/p1")
        self.assertEqual(m["title"], "Broken&Fine")
        self.assertEqual(m["authors"], [{"lastName": "Doe", "firstName": "J."}, {"lastName": "Roe", "firstName": "R."}])
        self.assertEqual((m["doi"], m["pdf_url"]), ("10.1234/xyz", "https://site.example/files/paper.pdf"))
        self.assertNotIn("x", m["meta"], "a tag inside a comment is not read")
        for junk in (b"<!DOCTYPE", b"<![CDATA[x", b"<meta", b"\x00\x01<<>>", "<méta>".encode("utf-16")):
            web.page_meta(junk, "https://x.org/")

    def test_the_charset_comes_from_the_reply_then_the_page(self):
        title = "基于深度学习的超声图像分割"
        page = f'<meta http-equiv="Content-Type" content="text/html; charset=gb2312"><meta name="citation_title" content="{title}">'
        self.assertEqual(web.page_meta(page.encode("gb18030"), "https://x.cn/")["title"], title)
        plain = f'<meta name="citation_title" content="{title}">'
        self.assertEqual(web.page_meta(plain.encode("gbk"), "https://x.cn/", {"content-type": "text/html; charset=gbk"})["title"], title)
        self.assertEqual(web.page_meta(plain.encode(), "https://x.cn/", {"Content-Type": "text/html; charset=x-nope"})["title"], title)
        self.assertEqual(web.page_meta(b"\xef\xbb\xbf" + plain.encode(), "https://x.cn/")["title"], title)


if __name__ == "__main__":
    unittest.main()
