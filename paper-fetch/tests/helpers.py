"""What every test file shares: loading a script, running it in this process or as a subprocess, a config, a result
file, a closed port, and PDFs without poppler (stubs on PATH that print sidecar files, or a minimal real PDF).

    from helpers import load, call, smoke, config_file, result_file, closed_port
    settle = load("settle")
    r = call(settle, result_file(tmp, "doe2024paper"), config=cfg)   # r.code, r.out, r.err, r.lines

Every run checks that no secret of a config_file (the OpenAlex key) appears in stdout or stderr. Copied from
paper-to-zotero/tests/helpers.py (commit 90cecdf) without the fake Zotero.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))   # `from pflib import ...` inside the scripts, as when uv runs them
sys.path.insert(0, str(TESTS))

_loaded, SECRETS = {}, set()
# Scripts pace through the machine's pace file: tests never touch the real one. A test that needs its own points
# PAPER_FETCH_PACE into its directory.
os.environ.setdefault("PAPER_FETCH_PACE", str(Path(tempfile.mkdtemp(prefix="pf-pace-")) / "pace.json"))


def load(name):
    """The script scripts/<name>.py as a module (once per process)."""
    if name not in _loaded:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[name] = module
    return _loaded[name]


def closed_port():
    """A port nothing listens on: bound, then released (a fixed port such as 9 can hang for seconds instead of refusing)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def config_file(directory=None, **fields):
    """A config file with these top-level fields (openalex_key, institution); returns its path."""
    directory = Path(directory or tempfile.mkdtemp(prefix="pf-config-"))
    config = dict(fields)
    if config.get("openalex_key"):
        SECRETS.add(config["openalex_key"])
    path = directory / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


class Output:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err

    @property
    def lines(self):
        """stdout as JSON objects, one per line."""
        return [json.loads(line) for line in self.out.splitlines() if line.strip()]

    @property
    def err_lines(self):
        return [json.loads(line) for line in self.err.splitlines() if line.startswith("{")]

    def __repr__(self):
        return f"Output(code={self.code}, out={self.out[-800:]!r}, err={self.err[-800:]!r})"


def _no_secret(result):
    assert not any(s in result.out + result.err for s in SECRETS), "a secret leaked into the output"
    return result


ARTICLE = {"type": "article-journal", "title": "Deep learning for ultrasound super-resolution",
           "author": [{"family": "Doe", "given": "Jane"}, {"family": "Roe", "given": "Rick"}],
           "container-title": "Medical Image Analysis", "issued": {"date-parts": [[2024, 3]]},
           "DOI": "10.1016/j.media.2024.103100", "URL": "https://doi.org/10.1016/j.media.2024.103100",
           "source": "Crossref"}


def result_file(directory, slug="doe2024deep", *, csl=ARTICLE, ids=None, **fields):
    """A result file at <directory>/results/<slug>.json (the folders made), as identify writes one; `csl` None makes a
    stub. Returns its path."""
    directory = Path(directory)
    (directory / "results").mkdir(parents=True, exist_ok=True)
    doi = (csl or {}).get("DOI")
    data = {"slug": slug, "slug_given": False, "request": {"given": doi or slug}}
    if csl is not None:
        data.update(record_of="published", ids={"doi": doi, "arxiv": None, "pmid": None, "pmcid": None, **(ids or {})},
                    csl=csl, alt_titles=[], versions={"published": [], "incomplete": []}, warnings=[])
    data.update(fields)
    path = directory / "results" / f"{slug}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def call(module, *argv, config=None, env=None, stdin=""):
    """module.main(argv) in this process, stdout and stderr captured; a parser error (SystemExit) gives its code."""
    out, err = io.StringIO(), io.StringIO()
    environ = {**({"PAPER_FETCH_CONFIG": str(config)} if config else {}), **(env or {})}
    with mock.patch.dict(os.environ, environ), mock.patch("sys.stdin", io.StringIO(stdin)), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main([str(a) for a in argv])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    return _no_secret(Output(code, out.getvalue(), err.getvalue()))


SHEBANG = "#!/usr/bin/env -S uv run --script"
UV = shutil.which("uv")   # found once: a test may hand the script a PATH of stubs only


def smoke(name, *argv, config=None, env=None, timeout=120):
    """scripts/<name>.py as its own process, run by uv as the docs run it (after checking it opens with the uv shebang)."""
    first = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8").splitlines()[0]
    assert first == SHEBANG, f"{name}.py must open with {SHEBANG!r}, not {first!r}"
    environ = {**os.environ, **({"PAPER_FETCH_CONFIG": str(config)} if config else {}), **(env or {})}
    done = subprocess.run([UV, "run", "--quiet", "--script", str(SCRIPTS / f"{name}.py"), *map(str, argv)], capture_output=True,
                          text=True, env=environ, timeout=timeout)
    return _no_secret(Output(done.returncode, done.stdout, done.stderr))


# ---- PDFs without poppler: stubs that print a file's sidecars -------------------------------------------------

# verify calls: pdftotext -f 1 -l 3 -enc UTF-8 FILE -   (FILE is $7)
PDFTOTEXT_STUB = """#!/bin/sh
[ -f "$7.txt" ] || exit 1
exec /bin/cat "$7.txt"
"""
PDFINFO_STUB = """#!/bin/sh
for f; do :; done
[ -f "$f.pages" ] || exit 1
[ -f "$f.dates" ] && /bin/cat "$f.dates"
printf 'Producer:       stub\\nPages:          '
exec /bin/cat "$f.pages"
"""


def pdf_string(line):
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages):
    """A minimal real PDF, one uncompressed content stream per page (for the real-pdftotext test)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, page in enumerate(pages):
        shown = "".join(f"({pdf_string(line)}) Tj T* " for line in page.split("\n"))
        content = f"BT /F1 12 Tf 14 TL 72 720 Td {shown}ET".encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for num, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def poppler_stubs(directory):
    """pdftotext and pdfinfo stubs in `directory` (put it on PATH): they print fake_pdf's sidecar files."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in (("pdftotext", PDFTOTEXT_STUB), ("pdfinfo", PDFINFO_STUB)):
        (directory / name).write_text(body, encoding="utf-8")
        (directory / name).chmod(0o755)
    return directory


def fake_pdf(path, pages, page_count=None, data=None):
    """A file that starts like a PDF, with the pages (form feeds between them) the pdftotext stub prints for it and
    the page count pdfinfo's stub gives; pages=None: no text layer (the stub fails as on a broken file)."""
    path = Path(path)
    path.write_bytes(data if data is not None else b"%PDF-1.5\n% " + path.name.encode() + b"\n")
    if pages is not None:
        path.with_name(f"{path.name}.txt").write_text("\f".join(pages) + "\f", encoding="utf-8")
    path.with_name(f"{path.name}.pages").write_text(f"{page_count or len(pages or [1])}\n", encoding="utf-8")
    return path
