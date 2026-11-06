"""What tests/check_conventions.py needs from paper-to-zotero: its help environment, the names it dropped, and four
runtime cases against the fake Zotero (the check's docstring says what each must show)."""
import contextlib
import socket

from fake_zotero import FakeZotero
from helpers import config_file

# Every -h runs here: no config, Zotero on a port nothing listens on.
HELP_ENV = {"PAPER_TO_ZOTERO_CONFIG": "/nonexistent/config.json", "PAPER_TO_ZOTERO_BASE_URL": "http://127.0.0.1:9"}
# Long names dropped in the conversion, so none comes back: {name: the words still allowed it}.
REMOVED = {"--q": (), "--cite": (), "--key": ("answer",), "--batch": (), "--out": (), "--tags-file": (), "--tree": (),
           "--limit": (), "--since": (), "--qmode": (), "--file": (), "--keep": (), "--drop": (), "--name": (),
           "--parent": (), "--note": (), "--title": ("package",), "--dir": ()}
# Where --collection selects, so it may appear (anywhere else it would replace: that is --set-collection).
SELECTS = {"items", "search", "lint", "export", "note list", "note search"}

KEYS = [f"K{i:07d}" for i in range(400)]
zot = None


@contextlib.contextmanager
def env(tmp):
    """400 items with long titles in the collection `big`."""
    global zot
    zot = FakeZotero()
    try:
        zot.add_collection("COLL0001", "big")
        for key in KEYS:
            zot.add_item(key, itemType="journalArticle", title=f"Paper {key} " + "x" * 300, collections=["COLL0001"])
        yield {"PAPER_TO_ZOTERO_CONFIG": str(config_file(tmp)), "PAPER_TO_ZOTERO_BASE_URL": zot.base_url,
               "no_proxy": "127.0.0.1,localhost", "NO_PROXY": "127.0.0.1,localhost"}   # a set http_proxy skips the fake
    finally:
        zot.close()


def quiet(tmp):
    return {"run": "p2z.py trash -n K0000001 K0000002", "lines": 2}


def reader(tmp):
    return {"run": "p2z.py items --collection big"}


def writer(tmp):
    return {"run": f"p2z.py update {' '.join(KEYS)} --set date=2024",
            "written": lambda: {zot.data(key).get("date") for key in KEYS} == {"2024"}}


def no_service(tmp):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return {"run": f"PAPER_TO_ZOTERO_BASE_URL=http://127.0.0.1:{port} p2z.py tags", "code": "zotero_unreachable"}
