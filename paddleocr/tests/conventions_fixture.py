"""What tests/check_conventions.py needs from paddleocr: its help environment, the names it dropped, and the runtime
cases on parse folders made from the fixture record (the check's docstring says what each must show). No GPU, no tool
environment and no source: the record's source path is empty, which the words take as no source."""
import contextlib
import json
import shutil
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Every -h runs here: a word whose -h went on to the paddleocr tool environment would exit 2.
HELP_ENV = {"PADDLEOCR_PYTHON": "/no/such/python"}
# Options dropped in the conversion, so none comes back: {name: the words still allowed it}.
REMOVED = {"--page": (), "--why": ()}


def folder(tmp, name, record):
    """A parse folder <tmp>/<name> holding `record` and the fixture's Markdown."""
    path = tmp / name
    path.mkdir()
    (path / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")
    shutil.copy(FIXTURES / "synthetic.md", path / f"{name}.md")
    return path


@contextlib.contextmanager
def env(tmp):
    """small: one word edited in its Markdown. big: 200 unresolved findings, each with a 500-character verdict;
    its Markdown as generated, so no edit is pending."""
    record = json.loads((FIXTURES / "synthetic.json").read_text(encoding="utf-8"))
    small = folder(tmp, "small", record)
    md = small / "small.md"
    md.write_text(md.read_text(encoding="utf-8").replace("after the formula", "following the formula"), encoding="utf-8")
    codes = ("missing_text", "missing_numbers", "extra_text", "foreign_script", "table_mismatch")
    places = [(code, b["id"]) for code in codes for b in record["blocks"]][:200]      # code@block: no id twice
    record["findings"] = [{"id": f"{code}@{block}", "code": code, "page": int(block[1:].split("-")[0]), "block": block,
                           "items": [], "detail": "", "status": "unresolved", "why": f"{i:03d} " + "w" * 496}
                          for i, (code, block) in enumerate(places)]
    folder(tmp, "big", record)
    yield {"TMPDIR": str(tmp)}   # show's images, were any made, stay in tmp


def quiet(tmp):
    return {"run": f"ocr.py commit {tmp}/small", "lines": 1}


def reader(tmp):
    return {"run": f"ocr.py findings {tmp}/big"}


writer = ("The one write command that prints as it goes is parse, which needs paddleocr's tool environment, so here, on "
          "another machine, it could never fail; the words on a parse folder print their one line after writing. "
          "parse cut off by a closed pipe still parses every document: tests/test_parse.py, Run.")


def no_service(tmp):
    return {"run": f"PADDLEOCR_PYTHON=/no/such/python ocr.py parse {tmp}/x.pdf -o {tmp}/out/", "code": "paddleocr_missing"}
