"""What tests/check_conventions.py needs from paper-read: its help environment, the names it dropped, and four runtime
cases against tests/fake_p2z.py (the check's docstring says what each must show)."""
import contextlib
import json
import socket
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Every -h runs here: the sibling skills' entries nowhere, so a -h that ran one would fail.
HELP_ENV = {"PAPER_READ_P2Z": "/nonexistent/p2z.py", "PAPER_READ_OCR": "/nonexistent/ocr.py"}
# Long names dropped in the conversion, so none comes back: {name: the words still allowed it}.
REMOVED = {"--cite": (), "--out": (), "--taken": (), "--pdf": (), "--package": ()}

CITES = [f"paper{i:03d}Study2026" for i in range(400)]


@contextlib.contextmanager
def env(tmp):
    """400 papers, each with its own key and citation key and a 300-character title, in the fake p2z's library."""
    lib = tmp / "library.json"
    items = {cite: {"key": f"K{i:07d}", "title": f"Paper {i} " + "x" * 300, "date": "2026"} for i, cite in enumerate(CITES)}
    lib.write_text(json.dumps({"items": items, "notes": {}, "pdfs": {}, "packages": {}}), encoding="utf-8")
    # The fake is no service: nothing to stop afterwards, and the files go with the check's temporary directory.
    # PAPER_TO_ZOTERO_CONFIG: reading the library needs no config. no_proxy: no_service's real p2z goes to 127.0.0.1,
    # which a set http_proxy would take.
    yield {"PAPER_READ_P2Z": str(HERE / "fake_p2z.py"), "FAKE_P2Z": str(lib),
           "PAPER_TO_ZOTERO_CONFIG": str(tmp / "no-config.json"),
           "no_proxy": "127.0.0.1,localhost", "NO_PROXY": "127.0.0.1,localhost"}


def quiet(tmp):
    return {"run": f"pr.py heading {CITES[0]} {CITES[1]}", "lines": 2}


def reader(tmp):
    return {"run": f"printf '%s\\n' {' '.join(CITES)} | pr.py heading -"}


writer = "put writes one note per call and prints its one line after every write: there is nothing for head to cut"


def no_service(tmp):
    with socket.socket() as s:   # a port just closed: nothing listens there (port 9 hangs on WSL)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return {"run": f"PAPER_READ_P2Z= PAPER_TO_ZOTERO_BASE_URL=http://127.0.0.1:{port} pr.py take {CITES[0]} "
                   f"-o {tmp}/scratch/", "code": "zotero_unreachable"}
