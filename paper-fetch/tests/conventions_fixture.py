"""What tests/check_conventions.py needs from paper-fetch: its help environment, the names it dropped, and four
runtime cases against the fake web (the check's docstring says what each must show). fetch drives Chrome, so it
has no runtime case."""
import contextlib
import json
import os
import socket

from fake_web import FakeWeb
from helpers import config_file, fake_pdf, poppler_stubs, result_file

SERVICES = ("DOI_BASE_URL", "CROSSREF_BASE_URL", "ARXIV_API_URL", "OPENALEX_BASE_URL", "EUROPEPMC_BASE_URL")
# Every -h runs here: no config, each service at a port nothing listens on (-h asks none of them).
HELP_ENV = {"PAPER_FETCH_CONFIG": "/nonexistent/config.json", **{name: "http://127.0.0.1:9" for name in SERVICES}}
# Long names dropped in the conversion, so none comes back: {name: the words still allowed it}.
REMOVED = {**{name: () for name in ("--dir", "--file", "--version", "--out", "--scan", "--watch", "--sweep",
                                    "--redraft", "--search")}, "--downloads": ("ready",)}

PAPERS = {"10.1000/a.1": "A First Paper on Quiet Commands", "10.1000/b.2": "A Second Paper on Quiet Commands"}
READERS, WRITERS = 60, 400
LONG = " ".join(["words that fill the first page of the paper"] * 60)


@contextlib.contextmanager
def env(tmp):
    """The fake web with two DOIs, stubs for pdftotext and pdfinfo, a config and a pace file of the test's own."""
    web = FakeWeb()
    try:
        for doi, title in PAPERS.items():
            web.doi(doi, {"type": "journal-article", "title": title, "author": [{"family": "Doe", "given": "Jane"}],
                          "container-title": "Journal of Tests", "issued": {"date-parts": [[2024]]}, "DOI": doi,
                          "source": "Crossref"})
        stubs = poppler_stubs(tmp / "bin")
        yield {**web.env(), "PAPER_FETCH_CONFIG": str(config_file(tmp)), "PAPER_FETCH_PACE": str(tmp / "pace.json"),
               "PATH": f"{stubs}:{os.environ['PATH']}", "no_proxy": "127.0.0.1,localhost",
               "NO_PROXY": "127.0.0.1,localhost"}   # a set http_proxy skips the fake
    finally:
        web.close()


def quiet(tmp):
    return {"run": f"pf.py identify -o {tmp}/q/ {' '.join(PAPERS)}", "lines": 2}


def reader(tmp):
    """Results whose files pass the check, each line long with its page-1 excerpt."""
    for i in range(READERS):
        title = f"Reading Paper Number {i} on Pipes"
        path = result_file(tmp / "r", f"reader{i}", csl={"title": title, "author": [{"family": "Doe"}]})
        fake_pdf(path.with_suffix(".pdf"), [f"{title}\nJane Doe\n{LONG}"])
    return {"run": f"pf.py check {tmp}/r/results/*.json"}


def writer(tmp):
    paths = [result_file(tmp / "w", f"writer{i:03d}" + "x" * 80) for i in range(WRITERS)]
    return {"run": f"pf.py sync {tmp}/w/results/*.json",
            "written": lambda: all("outcome" in json.loads(p.read_text(encoding="utf-8")) for p in paths)}


def no_service(tmp):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return {"run": f"DOI_BASE_URL=http://127.0.0.1:{port} pf.py identify -o {tmp}/n/ 10.1000/a.1",
            "code": "doi_org_unreachable"}
