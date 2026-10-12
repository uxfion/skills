# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/attach_file.py against a minimal mock of Zotero's local API, including the 3-step file upload.

Single mode without a record runs the real scripts/check_pdf.py on the file."""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "attach_file.py"
SERVER_ID = "MOCKSRV1"
API_KEY = "mock-key-never-printed"
PARENT = "PARENT01"
PARENT2 = "PARENT02"
PARENT_TITLE = "A Paper: With Colon"
PASS_CODES = ("ok", "ok_on_page_2", "ok_on_page_3", "ok_by_words")
PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"  # no page, no text
HTML_BYTES = b"<!DOCTYPE html>\n<html><head><title>Article</title></head><body>Abstract text</body></html>\n"


def text_pdf(*lines):
    """A small valid PDF (uncompressed, with an xref table) whose one page shows `lines` in Helvetica."""
    content = (b"BT /F1 12 Tf 72 720 Td "
               + b" 0 -14 Td ".join(b"(" + line.encode("latin-1") + b") Tj" for line in lines) + b" ET")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


TITLED_PDF = text_pdf(PARENT_TITLE)
PARENT3 = "PARENT03"  # a published item with a DOI; PREPRINT_PDF is its preprint, printing the arXiv DOI
PARENT3_TITLE = "A Preprint That Became A Paper"
PREPRINT_PDF = text_pdf(PARENT3_TITLE, "doi: 10.48550/arXiv.2101.00001")


def md5(data):
    return hashlib.md5(data).hexdigest()


def variant(n):
    """A distinct PDF (its own md5) for tests that attach several files to one parent."""
    return PDF_BYTES + b"%% variant %d\n" % n

def closed_port():
    """A port nothing listens on (bound then released), so a connection is refused at once instead of timing out."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class State:
    def __init__(self):
        self.items = {
            PARENT: {"key": PARENT, "version": 5, "itemType": "journalArticle", "title": PARENT_TITLE,
                     "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"},
                                  {"creatorType": "author", "firstName": "Jing", "lastName": "Zhang"}],
                     "date": "2022-03-01"},
            PARENT2: {"key": PARENT2, "version": 2, "itemType": "conferencePaper", "title": "Second",
                      "creators": [{"creatorType": "author", "lastName": "Chen"}], "date": "2021"},
            PARENT3: {"key": PARENT3, "version": 3, "itemType": "journalArticle", "title": PARENT3_TITLE,
                      "DOI": "10.1000/pub.1", "creators": [{"creatorType": "author", "lastName": "Liu"}], "date": "2023"},
        }
        self.children = {PARENT: [], PARENT2: [], PARENT3: []}
        self.pending = {}     # attachment key -> authorized (md5, filename) awaiting the register step
        self.uploads = {}     # attachment key -> bytes received
        self.posts = []       # POST /items bodies
        self.counter = 0

    def next_key(self):
        self.counter += 1
        return f"ATTACH{self.counter:02d}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body=None, headers=None):
        data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        s = self.server.state
        if self.path == "/api/":
            return self.send(200, {"ok": True}, {"Zotero-Server-ID": SERVER_ID})
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})/children$", self.path)
        if m:
            if m.group(1) not in s.items:
                return self.send(404, b"Not found")
            kids = [c for c in s.items.values() if c.get("parentItem") == m.group(1)]
            return self.send(200, [{"key": c["key"], "version": c["version"], "data": c} for c in kids])
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})$", self.path)
        if m:
            it = s.items.get(m.group(1))
            if not it:
                return self.send(404, b"Not found")
            return self.send(200, {"key": it["key"], "version": it["version"], "data": it})
        self.send(404, b"Not found")

    def do_POST(self):
        s = self.server.state
        raw = self.body()
        if self.path.startswith("/upload/"):
            akey = self.path.split("/")[2]
            s.uploads[akey] = raw
            return self.send(201)
        if self.headers.get("Zotero-API-Key") != API_KEY:
            return self.send(401, b"Invalid API key")
        if self.path == "/api/users/0/items":
            objs = json.loads(raw)
            s.posts.append(objs)
            successful = {}
            for i, obj in enumerate(objs):
                key = s.next_key()
                data = {**obj, "key": key, "version": 1}
                s.items[key] = data
                successful[str(i)] = {"key": key, "version": 1, "data": data}
            return self.send(200, {"successful": successful, "unchanged": {}, "failed": {}})
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})/file$", self.path)
        if m:
            akey = m.group(1)
            form = dict(urllib.parse.parse_qsl(raw.decode()))
            att = s.items.get(akey)
            if not att:
                return self.send(404, b"Not found")
            if "upload" in form:  # step 3: register
                md5, filename = s.pending.pop(akey)
                if hashlib.md5(s.uploads.get(akey, b"")).hexdigest() != md5:
                    return self.send(400, b"upload does not match")
                att["md5"], att["filename"] = md5, filename
                att["version"] += 1
                return self.send(204)
            if att.get("md5") == form["md5"]:  # step 1 with the same file already there
                return self.send(200, {"exists": 1})
            s.pending[akey] = (form["md5"], form["filename"])
            base = f"http://127.0.0.1:{self.server.server_address[1]}"
            return self.send(200, {"url": f"{base}/upload/{akey}", "uploadKey": f"UK-{akey}",
                                   "contentType": "application/pdf", "prefix": "", "suffix": ""})
        self.send(404, b"Not found")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.key_file = Path(tempfile.mkdtemp(prefix="attach_key_")) / "key.json"
        cls.key_file.write_text(json.dumps({"key": API_KEY, "serverID": SERVER_ID}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state = self.server.state = State()
        # records live in <root>/records, so the fetch.jsonl looked up is <root>/fetch.jsonl, never a stray one in /tmp
        self.tmp = Path(tempfile.mkdtemp(prefix="attach_test_")) / "records"
        self.tmp.mkdir()

    def run_script(self, *argv, stdin=None, base_url=None, cwd=None, script=SCRIPT):
        env = {k: v for k, v in os.environ.items() if k != "ZOTERO_LOCAL_API_KEY"}
        cmd = [sys.executable, str(script), *argv, "--base-url", base_url or self.base_url, "--key-file", str(self.key_file)]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, cwd=cwd)

    def record(self, slug, content=PDF_BYTES, file_name=None, where=None, **extra):
        """A record with `saved.key`, `item.DOI`, a file next to it named in `file`, and a passing `pdf` for that
        file (as check_pdf.py -i leaves it); extras override or remove (None) fields."""
        where = where or self.tmp
        where.mkdir(parents=True, exist_ok=True)
        rec = {"slug": slug, "item": {"itemType": "journalArticle", "title": "A Paper", "DOI": "10.1000/xyz"},
               "saved": {"key": PARENT, "version": 5, "created_at": "2026-09-23T00:00:00Z"}}
        if content is not None:
            name = file_name or f"{slug}.pdf"
            (where / name).write_bytes(content)
            rec["file"] = name
            rec["pdf"] = {"code": "ok", "evidence": {}, "checked_at": "2026-10-12T00:00:00Z", "md5": md5(content)}
        for k, v in extra.items():
            if v is None:
                rec.pop(k, None)
            else:
                rec[k] = v
        path = where / f"{slug}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def passed(content):
        return {"code": "ok", "md5": md5(content)}

    def title_of(self, record_path):
        """The Zotero title of the attachment the record's `attach` names."""
        return self.state.items[json.loads(record_path.read_text())["attach"]["key"]]["title"]

    @staticmethod
    def lines(stream):
        return [json.loads(line) for line in stream.splitlines() if line.startswith("{")]

    def attachments_of(self, parent):
        return [it for it in self.state.items.values() if it.get("parentItem") == parent]


class SingleMode(Base):
    def test_v1_attach_then_already_attached(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(TITLED_PDF)  # check_pdf.py finds the parent's title on page 1
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "ok")
        self.assertIn(out["check_code"], PASS_CODES)
        self.assertNotIn("accepted", out)
        self.assertEqual(out["item_key"], PARENT)
        self.assertEqual(out["attachment_key"], "ATTACH01")
        self.assertTrue(out["md5_ok"])
        self.assertEqual(out["filename"], "Liu and Zhang - 2022 - A Paper With Colon.pdf")
        self.assertEqual(out["title"], "PDF")
        self.assertFalse(out["reused_attachment"])
        self.assertFalse(out["file_existed"])
        att = self.state.items["ATTACH01"]
        self.assertEqual((att["linkMode"], att["contentType"], att["title"], att["url"]),
                         ("imported_url", "application/pdf", "PDF", "https://doi.org/10.1000/xyz"))
        self.assertEqual(self.state.uploads["ATTACH01"], TITLED_PDF)
        self.assertNotIn(API_KEY, r.stdout + r.stderr)
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        self.assertEqual(r.returncode, 0, r.stdout)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "already_attached")
        self.assertEqual(set(out), {"code", "item_key", "attachment_key", "md5_ok", "filename", "title",
                                    "reused_attachment", "md5"})  # nothing written, so no check
        self.assertEqual(len(self.state.posts), 1)

    def test_v1_pre_check_failures(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(TITLED_PDF)
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://x.ezproxy.lib.edu/pdf")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "proxied_url"))
        r = self.run_script("--key", PARENT, "--file", str(self.tmp / "none.pdf"), "--url", "https://doi.org/1")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "file_not_found"))
        bad = self.tmp / "bad.pdf"
        bad.write_bytes(HTML_BYTES)
        r = self.run_script("--key", PARENT, "--file", str(bad), "--url", "https://doi.org/1")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "unsupported_file"))
        r = self.run_script("--key", "NOPE0000", "--file", str(pdf), "--url", "https://doi.org/1")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "item_not_found"))
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/1", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["dry_run"])
        self.assertIn(out["check_code"], PASS_CODES)
        self.assertEqual(self.state.posts, [])
        self.assertEqual(self.run_script("--key", PARENT, "--file", str(pdf)).returncode, 2)  # --url missing

    def test_check_refuses_then_accept(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(PDF_BYTES)  # no page, no text: check_pdf.py cannot find the title
        argv = ("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        r = self.run_script(*argv)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "not_verified")
        self.assertTrue(out["check_code"])
        self.assertNotIn(out["check_code"], PASS_CODES)
        self.assertEqual(out["md5"], md5(PDF_BYTES))
        self.assertIn("--accept", out["hint"])
        self.assertEqual((self.state.posts, self.state.uploads), ([], {}))
        r = self.run_script(*argv, "--dry-run")  # the check is a pre-check
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "not_verified"))
        refused_code = out["check_code"]
        reason = "page 1 read: title and authors match; the file has no text layer"
        r = self.run_script(*argv, "--accept", reason)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["code"], out["accepted"], out["check_code"]), ("ok", reason, refused_code))
        self.assertEqual(self.state.uploads[out["attachment_key"]], PDF_BYTES)
        self.assertEqual(self.run_script(*argv, "--accept", "  ").returncode, 2)  # a reason is required
        r = self.run_script(*argv)  # attached now: a no-op needs no check and no --accept
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (0, "already_attached"))
        self.assertEqual(len(self.state.posts), 1)

    def test_file_version_goes_to_the_check_and_the_title(self):
        pdf = self.tmp / "preprint.pdf"
        pdf.write_bytes(PREPRINT_PDF)  # the published item's title, but the preprint's own DOI on page 1
        argv = ("--key", PARENT3, "--file", str(pdf), "--url", "https://doi.org/10.1000/pub.1")
        r = self.run_script(*argv)  # judged as the published version: the DOI on page 1 is another one
        out = json.loads(r.stdout)
        self.assertEqual((r.returncode, out["code"], out["check_code"]), (1, "not_verified", "doi_mismatch"))
        r = self.run_script(*argv, "--file-version", "submitted", "--dry-run")  # the old links' word for preprint
        self.assertEqual((r.returncode, json.loads(r.stdout)["title"]), (0, "Preprint"), r.stdout + r.stderr)
        r = self.run_script(*argv, "--file-version", "preprint")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["code"], out["check_code"], out["title"]), ("ok", "ok", "Preprint"))
        self.assertEqual(self.state.items[out["attachment_key"]]["title"], "Preprint")
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/1", "--file-version", "unknown",
                            "--title", "Repository copy", "--dry-run")
        self.assertEqual(json.loads(r.stdout)["code"], "not_verified")  # another paper's title: no version helps
        self.assertEqual(self.run_script(*argv, "--file-version", " ").returncode, 2)

    def test_check_that_cannot_run_refuses(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(TITLED_PDF)
        lone = self.tmp / "lone"  # attach_file.py without check_pdf.py beside it
        lone.mkdir()
        shutil.copy(SCRIPT, lone / "attach_file.py")
        argv = ("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        r = self.run_script(*argv, script=lone / "attach_file.py")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["code"], out["check_code"]), ("not_verified", "check_failed"))
        # a check_pdf.py that exits 2 (cannot check) refuses too, whatever it printed
        (lone / "check_pdf.py").write_text(
            "import json, sys\nsys.stdin.read()\n"
            "ev = {'title_page': 2, 'doi_found': None, 'pages_scanned': 3, 'excerpt': 'x' * 500}\n"
            "print(json.dumps({'item': {}, 'pdf': {'code': 'cannot_judge', 'evidence': ev}}))\n"
            "sys.exit(2)\n", encoding="utf-8")
        r = self.run_script(*argv, script=lone / "attach_file.py")
        out = json.loads(r.stdout)
        self.assertEqual((r.returncode, out["code"], out["check_code"]), (1, "not_verified", "cannot_judge"))
        self.assertEqual(out["evidence"], {"title_page": 2, "excerpt": "x" * 300})  # a short summary
        r = self.run_script(*argv, "--accept", "read page 1", script=lone / "attach_file.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["accepted"], "read page 1")
        self.assertEqual(len(self.state.posts), 1)


class RecordFlag(Base):
    """Single mode with --record: the record supplies what the flags leave out and gets `attach` back."""

    def test_record_alone_writes_attach_back(self):
        p = self.record("rb", file=None, file_name="rb.pdf")  # no `file`: rb.pdf next to the record is the default
        r = self.run_script("--record", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["code"], out["item_key"], out["check_code"], out["record"]), ("ok", PARENT, "ok", str(p)))
        rec = json.loads(p.read_text(encoding="utf-8"))
        att = rec["attach"]
        self.assertEqual((att["key"], att["md5_ok"], att["url"], att["title"], att["file_version"]),
                         ("ATTACH01", True, "https://doi.org/10.1000/xyz", "PDF", "published"))
        self.assertEqual(att["filename"], "Liu and Zhang - 2022 - A Paper With Colon.pdf")
        self.assertEqual(self.state.uploads["ATTACH01"], PDF_BYTES)
        # again: already attached, the record still says so
        r = self.run_script("--record", str(p))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (0, "already_attached"))
        self.assertEqual(json.loads(p.read_text())["attach"]["key"], "ATTACH01")
        self.assertEqual(len(self.state.posts), 1)
        # --dry-run leaves the record alone, also when the file is already attached
        q = self.record("dry", content=variant(5))
        r = self.run_script("--record", str(q), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["dry_run"])
        self.assertNotIn("attach", json.loads(q.read_text()))
        q = self.record("dry2")  # PDF_BYTES, attached above
        r = self.run_script("--record", str(q), "--dry-run")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (0, "already_attached"))
        self.assertNotIn("attach", json.loads(q.read_text()))
        r = self.run_script("-i", "--dry-run", str(q))
        self.assertEqual(self.lines(r.stdout)[0]["reason"], "already_attached")
        self.assertNotIn("attach", json.loads(q.read_text()))
        self.assertEqual(len(self.state.posts), 1)

    def test_record_vouches_for_the_file(self):
        p = self.record("nv", pdf=None)
        r = self.run_script("--record", str(p))
        out = json.loads(r.stdout)
        self.assertEqual((r.returncode, out["code"]), (1, "not_verified"))
        self.assertIn("pdf_accepted", out["hint"])
        self.assertNotIn("attach", json.loads(p.read_text()))
        # a --file override is still held to the record's check
        other = self.tmp / "other.pdf"
        other.write_bytes(variant(1))
        q = self.record("ov")
        r = self.run_script("--record", str(q), "--file", str(other))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "not_verified"))
        self.assertEqual(self.state.posts, [])

    def test_flag_overrides_and_combinations(self):
        p = self.record("fl", saved=None, found={"key": PARENT2}, item={"title": "no doi"}, attach_title="From record")
        r = self.run_script("--record", str(p), "--key", PARENT)  # the record names PARENT2
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "record_key_mismatch"))
        r = self.run_script("--record", str(p))  # no item.url / DOI and no --url
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "no_url"))
        r = self.run_script("--record", str(p), "--key", PARENT2, "--url", "https://publisher.example/a/1",
                            "--title", "From flag")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        att = self.attachments_of(PARENT2)[0]
        self.assertEqual((att["title"], att["url"]), ("From flag", "https://publisher.example/a/1"))
        self.assertEqual(json.loads(p.read_text())["attach"]["title"], "From flag")
        v = self.record("fv", content=variant(7), file_version="accepted")
        r = self.run_script("--record", str(v), "--file-version", "preprint")  # the flag wins over the record
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        att = json.loads(v.read_text())["attach"]
        self.assertEqual((att["title"], att["file_version"]), ("Preprint", "preprint"))
        self.assertEqual(self.run_script("--file-version", "preprint", str(v)).returncode, 2)  # not in stream mode
        q = self.record("nk", saved=None)
        self.assertEqual(json.loads(self.run_script("--record", str(q)).stdout)["code"], "no_item_key")
        self.assertEqual(self.run_script("--record", str(p), "--accept", "read it").returncode, 2)
        self.assertEqual(self.run_script("--record", str(p), "-i").returncode, 2)
        self.assertEqual(self.run_script("--record", str(p), str(q)).returncode, 2)
        self.assertEqual(self.run_script("--accept", "read it", str(p)).returncode, 2)  # stream mode has pdf_accepted


class StreamMode(Base):
    def test_paths_attach_and_fill_record(self):
        p = self.record("a")
        r = self.run_script(str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.lines(r.stdout)[0]
        att = rec["attach"]
        self.assertEqual(att["key"], "ATTACH01")
        self.assertTrue(att["md5_ok"])
        self.assertEqual(att["url"], "https://doi.org/10.1000/xyz")  # from item.DOI
        self.assertEqual(att["filename"], "Liu and Zhang - 2022 - A Paper With Colon.pdf")
        self.assertTrue(att["attached_at"].endswith("Z"))
        self.assertEqual(rec["saved"]["key"], PARENT)
        self.assertEqual(self.state.uploads["ATTACH01"], PDF_BYTES)
        self.assertNotIn("attach", json.loads(p.read_text()))  # no -i
        err = self.lines(r.stderr)
        self.assertEqual(err[0]["code"], "ok")
        self.assertEqual(err[-1]["summary"], {"total": 1, "ok": 1, "skipped": 0, "failed": 0})

    def test_in_place_and_summary(self):
        p = self.record("a", custom=[1, 2])
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[0]["slug"], "a")
        self.assertEqual(out[0]["code"], "ok")
        self.assertEqual(out[0]["attachment_key"], "ATTACH01")
        self.assertEqual(out[-1], {"summary": {"total": 1, "ok": 1, "skipped": 0, "failed": 0}})
        raw = p.read_text(encoding="utf-8")
        rec = json.loads(raw)
        self.assertEqual(rec["attach"]["key"], "ATTACH01")
        self.assertEqual(rec["custom"], [1, 2])
        self.assertTrue(raw.endswith("}\n"))
        self.assertIn('\n  "attach": {', raw)
        # second run: skipped on attach.md5_ok, nothing touched
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0)
        out = self.lines(r.stdout)
        self.assertEqual(out[0]["code"], "skipped")
        self.assertEqual(out[0]["reason"], "attach.md5_ok")
        self.assertEqual(out[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        self.assertEqual(len(self.state.posts), 1)

    def test_stdin_forms_relative_to_cwd(self):
        (self.tmp / "x.pdf").write_bytes(PDF_BYTES)
        rec = {"slug": "s", "item": {"title": "t", "url": "https://publisher.example/article/1"},
               "saved": {"key": PARENT}, "file": "x.pdf", "pdf": self.passed(PDF_BYTES)}
        r = self.run_script(stdin=json.dumps(rec) + "\n", cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["attach"]["url"], "https://publisher.example/article/1")  # item.url first
        rec2 = dict(rec, slug="s2", saved={"key": PARENT2})
        r = self.run_script(stdin=json.dumps([rec2]), cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["attach"]["key"], "ATTACH02")
        r = self.run_script(stdin=json.dumps(dict(rec2, slug="s3"), indent=2), cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["slug"], "s3")
        self.assertEqual(self.lines(r.stderr)[0]["code"], "skipped")  # same md5 on PARENT2: already_attached
        r = self.run_script("-i", stdin="{}")
        self.assertEqual(r.returncode, 2)
        r = self.run_script(stdin="")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "no_records"))

    def test_missing_pieces_are_per_record(self):
        p1 = self.record("nokey", saved=None)
        p2 = self.record("nofile", content=None)
        p3 = self.record("nourl", item={"itemType": "journalArticle", "title": "no doi"})
        p4 = self.record("gone", content=None, file="missing.pdf")
        p5 = self.record("ok")
        p6 = self.record("notfound", saved={"key": "NOPE0000"})
        r = self.run_script("-i", str(p1), str(p2), str(p3), str(p4), str(p5), str(p6))
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:6]],
                         ["no_item_key", "no_file", "no_url", "file_not_found", "ok", "item_not_found"])
        self.assertTrue(all("hint" in o for o in out[:4]))
        self.assertEqual(out[-1]["summary"], {"total": 6, "ok": 1, "skipped": 0, "failed": 5})
        self.assertEqual(json.loads(p5.read_text())["attach"]["key"], "ATTACH01")
        for p in (p1, p2, p3, p4, p6):
            self.assertNotIn("attach", json.loads(p.read_text()), p.name)

    def test_found_key_and_flag_fallbacks(self):
        p = self.record("f", saved=None, found={"key": PARENT2, "version": 2},
                        item={"itemType": "journalArticle", "title": "no doi"}, content=None, pdf=self.passed(PDF_BYTES))
        pdf = self.tmp / "elsewhere.pdf"
        pdf.write_bytes(PDF_BYTES)
        r = self.run_script("-i", "--file", str(pdf), "--url", "https://doi.org/10.9/fallback", "--title", "Preprint (arXiv v2)", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = json.loads(p.read_text())
        self.assertEqual(rec["attach"]["url"], "https://doi.org/10.9/fallback")
        att = self.attachments_of(PARENT2)[0]
        self.assertEqual(att["title"], "Preprint (arXiv v2)")
        self.assertEqual(att["parentItem"], PARENT2)

    def test_already_attached_is_skipped_and_filled(self):
        self.state.items["OLDATT01"] = {"key": "OLDATT01", "version": 1, "itemType": "attachment", "parentItem": PARENT,
                                        "linkMode": "imported_url", "filename": "old name.pdf",
                                        "md5": hashlib.md5(PDF_BYTES).hexdigest()}
        p = self.record("a")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)[0]
        self.assertEqual((out["code"], out["reason"], out["attachment_key"]), ("skipped", "already_attached", "OLDATT01"))
        rec = json.loads(p.read_text())
        self.assertEqual(rec["attach"]["key"], "OLDATT01")
        self.assertTrue(rec["attach"]["md5_ok"])
        self.assertEqual(rec["attach"]["filename"], "old name.pdf")
        self.assertEqual(self.state.posts, [])

    def test_half_made_attachment_is_reused(self):
        self.state.items["HALF0001"] = {"key": "HALF0001", "version": 1, "itemType": "attachment", "parentItem": PARENT,
                                        "linkMode": "imported_url", "contentType": "application/pdf",
                                        "filename": "Liu and Zhang - 2022 - A Paper With Colon.pdf"}
        p = self.record("a")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)[0]
        self.assertEqual((out["code"], out["attachment_key"], out["reused_attachment"]), ("ok", "HALF0001", True))
        self.assertEqual(self.state.posts, [])  # no new attachment item
        self.assertEqual(self.state.uploads["HALF0001"], PDF_BYTES)
        self.assertEqual(json.loads(p.read_text())["attach"]["key"], "HALF0001")

    def test_html_snapshot(self):
        p = self.record("h", content=HTML_BYTES, file_name="page.html")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        att = self.attachments_of(PARENT)[0]
        self.assertEqual((att["contentType"], att["charset"], att["title"]), ("text/html", "utf-8", "Snapshot"))
        self.assertTrue(att["filename"].endswith(".html"))
        self.assertEqual(json.loads(p.read_text())["attach"]["filename"], att["filename"])

    def test_dry_run_writes_nothing(self):
        p = self.record("a")
        r = self.run_script("-i", "--dry-run", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)[0]
        self.assertEqual((out["code"], out["dry_run"], out["kind"]), ("ok", True, "pdf"))
        self.assertEqual(self.state.posts, [])
        self.assertNotIn("attach", json.loads(p.read_text()))
        r = self.run_script("--dry-run", str(p))
        self.assertNotIn("attach", self.lines(r.stdout)[0])

    def test_unreachable_and_argument_errors(self):
        p = self.record("a")
        r = self.run_script("-i", str(p), base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "zotero_unreachable"))
        self.assertNotIn("attach", json.loads(p.read_text()))
        self.assertEqual(self.run_script("--key", PARENT, "--file", "x", "--url", "https://a/b", str(p)).returncode, 2)
        self.assertEqual(self.run_script("--filename", "x.pdf", str(p)).returncode, 2)

    def test_readback_preferred_over_found(self):
        listed = [{"key": "OLDATT01", "contentType": "application/pdf", "linkMode": "imported_url"}]
        p1 = self.record("rb_empty", content=None, found={"key": PARENT, "attachments": listed},
                         readback={"key": PARENT, "attachments": []})  # trashed since: readback has the say
        p2 = self.record("rb_has", content=None, found={"key": PARENT, "attachments": []},
                         readback={"key": PARENT, "attachments": listed})
        p3 = self.record("found_only", content=None, found={"key": PARENT, "attachments": listed})
        r = self.run_script("-i", str(p1), str(p2), str(p3))
        out = self.lines(r.stdout)
        self.assertEqual([(o["code"], o.get("reason")) for o in out[:3]],
                         [("no_file", None), ("skipped", "library_has_attachment"), ("skipped", "library_has_attachment")])
        self.assertEqual(r.returncode, 1)


class ItemKey(Base):
    """saved.key, else found.key; a found that is only a near match is not resolved yet."""

    def test_near_match_is_unresolved(self):
        near = {"key": PARENT2, "code": "near_match", "reason": "title contains the other (preprint vs published)"}
        listed = [{"key": "OLDATT01", "contentType": "application/pdf", "linkMode": "imported_url"}]
        p_near = self.record("near", saved=None, found=near)
        p_near_held = self.record("near_held", content=None, saved=None, found=dict(near, attachments=listed))
        p_found = self.record("found", saved=None, found={"key": PARENT2, "code": "found"}, content=variant(1))
        p_plain = self.record("plain", saved=None, found={"key": PARENT2}, content=variant(2))
        p_saved = self.record("saved", found=near, content=variant(3))  # saved.key (PARENT) wins
        r = self.run_script("-i", *map(str, (p_near, p_near_held, p_found, p_plain, p_saved)))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:5]], ["unresolved_match", "unresolved_match", "ok", "ok", "ok"])
        self.assertEqual((out[0]["found_key"], out[0]["found_reason"]), (PARENT2, near["reason"]))
        self.assertIn('replace found with {"key": "PARENT02"}', out[0]["hint"])
        self.assertIn("distinct_from", out[0]["hint"])
        self.assertNotIn("attach", json.loads(p_near.read_text()))
        self.assertEqual([a["parentItem"] for a in self.attachments_of(PARENT2)], [PARENT2, PARENT2])
        self.assertEqual(json.loads(p_saved.read_text())["attach"]["key"], self.attachments_of(PARENT)[0]["key"])
        for argv in (("--record", str(p_near)), ("--record", str(p_near), "--key", PARENT2)):
            r = self.run_script(*argv)
            self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "unresolved_match"))
        self.assertEqual(len(self.state.posts), 3)


class Precondition(Base):
    """Records: only a file whose md5 a passing `pdf` or a `pdf_accepted` names is uploaded."""

    def test_not_verified(self):
        h = md5(PDF_BYTES)
        cases = {
            "no_pdf": dict(pdf=None),
            "no_md5": dict(pdf={"code": "ok", "evidence": {}, "checked_at": "2026-10-09T00:00:00Z"}),  # a v2 record
            "md5_mismatch": dict(pdf={"code": "ok", "md5": md5(variant(9))}),
            "failing_code": dict(pdf={"code": "title_not_found", "md5": h}),
            "no_reason": dict(pdf=None, pdf_accepted={"md5": h, "reason": " "}),
        }
        paths = [self.record(slug, **extra) for slug, extra in cases.items()]
        r = self.run_script("-i", *map(str, paths))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:5]], ["not_verified"] * 5)
        for o in out[:5]:
            self.assertEqual(o["md5"], h)
            self.assertTrue(o["why"])
            self.assertIn("check_pdf.py -i", o["hint"])
        self.assertEqual(out[3]["pdf_code"], "title_not_found")
        self.assertEqual(out[-1]["summary"], {"total": 5, "ok": 0, "skipped": 0, "failed": 5})
        self.assertEqual((self.state.posts, self.state.uploads), ([], {}))
        for p in paths:
            self.assertNotIn("attach", json.loads(p.read_text()), p.name)
        r = self.run_script("-i", "--dry-run", str(paths[0]))  # the precondition is a pre-check
        self.assertEqual(self.lines(r.stdout)[0]["code"], "not_verified")
        # an HTML snapshot is held to the same rule
        q = self.record("snap", content=HTML_BYTES, file_name="snap.html", pdf=None)
        r = self.run_script("-i", str(q))
        self.assertEqual(self.lines(r.stdout)[0]["code"], "not_verified")
        self.assertEqual(self.state.posts, [])

    def test_what_writes_nothing_needs_no_check(self):
        """batch.md: a paper the library already holds with a file reports skipped, checked or not."""
        listed = [{"key": "OLDATT01", "contentType": "application/pdf", "linkMode": "imported_url", "md5": "0" * 32}]
        held = self.record("held", content=None, found={"key": PARENT, "attachments": listed})  # no file, no pdf
        self.assertNotIn("pdf", json.loads(held.read_text()))
        self.state.items["OLDATT02"] = {"key": "OLDATT02", "version": 1, "itemType": "attachment", "parentItem": PARENT2,
                                        "linkMode": "imported_url", "title": "PDF", "filename": "old.pdf",
                                        "md5": md5(PDF_BYTES)}
        same = self.record("same", pdf=None, saved={"key": PARENT2})  # its file is that very attachment
        r = self.run_script("-i", str(held), str(same))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual([(o["code"], o["reason"]) for o in out[:2]],
                         [("skipped", "library_has_attachment"), ("skipped", "already_attached")])
        self.assertNotIn("attach", json.loads(held.read_text()))
        self.assertEqual(json.loads(same.read_text())["attach"]["key"], "OLDATT02")
        self.assertEqual(json.loads(self.run_script("--record", str(same)).stdout)["code"], "already_attached")
        self.assertEqual((self.state.posts, self.state.uploads), ([], {}))

    def test_a_second_pdf_needs_need_file(self):
        """The item already holds a PDF: a file in hand with another md5 is not attached unless need_file is set."""
        listed = [{"key": "OLDATT01", "contentType": "application/pdf", "linkMode": "imported_url", "md5": "0" * 32}]
        extra = self.record("extra", saved=None, found={"key": PARENT, "attachments": listed})
        wanted = self.record("wanted", content=variant(7), saved=None, need_file=True,
                             found={"key": PARENT2, "attachments": listed})
        r = self.run_script("-i", str(extra), str(wanted))
        out = self.lines(r.stdout)
        self.assertEqual((out[0]["code"], out[0]["reason"], out[0]["attachment_key"]),
                         ("skipped", "library_has_pdf", "OLDATT01"))
        self.assertIn("need_file", out[0]["hint"])
        self.assertNotIn("attach", json.loads(extra.read_text()))
        self.assertEqual(out[1]["code"], "ok", out[1])
        self.assertEqual([a["parentItem"] for a in self.attachments_of(PARENT2)], [PARENT2])
        self.assertEqual(self.attachments_of(PARENT), [])

    def test_every_pass_code(self):
        paths = [self.record(code, content=variant(n), pdf={"code": code, "md5": md5(variant(n))})
                 for n, code in enumerate(PASS_CODES)]
        r = self.run_script("-i", *map(str, paths))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual([(o["code"], o["check_code"]) for o in out[:4]], [("ok", c) for c in PASS_CODES])
        self.assertEqual(len(self.attachments_of(PARENT)), 4)

    def test_pdf_accepted(self):
        h = md5(PDF_BYTES)
        reason = "page 1 read: the title is set in a font that extracts as garbage"
        p = self.record("acc", pdf={"code": "title_not_found", "md5": h}, pdf_accepted={"md5": h.upper(), "reason": reason})
        q = self.record("acc_other", content=variant(1), pdf=None, pdf_accepted={"md5": h, "reason": reason})
        r = self.run_script("-i", str(p), str(q))
        out = self.lines(r.stdout)
        self.assertEqual((out[0]["code"], out[0]["accepted"], out[0]["check_code"]), ("ok", reason, "title_not_found"))
        self.assertEqual(out[1]["code"], "not_verified")  # accepted another file than this one
        self.assertEqual(json.loads(p.read_text())["attach"]["key"], "ATTACH01")
        self.assertEqual(r.returncode, 1)


class RecordDefaults(Base):
    """§3.6: file and file_version defaults, and the attachment title they lead to."""

    def test_default_file_slug_pdf_then_html(self):
        work = self.tmp / "work" / "records"
        a = self.record("a", file=None, where=work, content=variant(1))                       # a.pdf
        b = self.record("b", file=None, where=work, content=HTML_BYTES, file_name="b.html")    # b.html only
        (work / "c.html").write_bytes(HTML_BYTES + b"<!-- c -->")
        c = self.record("c", file=None, where=work, content=variant(3))                       # c.pdf and c.html
        d = self.record("d", where=work, content=variant(4), file_name="named.pdf")           # `file` wins
        (work / "d.pdf").write_bytes(variant(40))
        r = self.run_script("-i", *map(str, (a, b, c, d)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        uploads = {json.loads(p.read_text())["slug"]: self.state.uploads[json.loads(p.read_text())["attach"]["key"]]
                   for p in (a, b, c, d)}
        self.assertEqual(uploads, {"a": variant(1), "b": HTML_BYTES, "c": variant(3), "d": variant(4)})
        self.assertEqual(self.title_of(b), "Snapshot")
        self.assertEqual(json.loads(b.read_text())["attach"]["file_version"], "snapshot")
        # as check_pdf.py --pdf: --file comes before <slug>.pdf
        e = self.record("e", file=None, where=work, content=variant(5), saved={"key": PARENT2})
        given = self.tmp / "given.pdf"
        given.write_bytes(variant(50))
        r = self.run_script("-i", "--file", str(given), str(e))
        self.assertEqual(self.lines(r.stdout)[0]["code"], "not_verified")  # e's pdf vouches for e.pdf, not given.pdf
        r = self.run_script("-i", str(e))
        self.assertEqual(self.state.uploads[json.loads(e.read_text())["attach"]["key"]], variant(5))
        # stdin records have no <slug> default: their `file`, or --file
        rec = json.loads(a.read_text())
        rec.pop("attach")
        rec.update(slug="a", saved={"key": PARENT2})
        r = self.run_script(stdin=json.dumps(rec), cwd=str(work))
        self.assertEqual(self.lines(r.stderr)[0]["code"], "no_file")
        r = self.run_script("--file", "a.pdf", stdin=json.dumps(rec), cwd=str(work))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state.uploads[self.lines(r.stdout)[0]["attach"]["key"]], variant(1))

    def test_file_version_from_fetch_jsonl(self):
        work = self.tmp / "work"
        rows = [
            {"slug": "e", "via": "http", "code": "ok", "version": "accepted"},
            {"slug": "e", "via": "page", "code": "no_pdf_link", "version": "published"},  # not ok: ignored
            {"slug": "other", "via": "http", "code": "ok", "version": "published"},
        ]
        rows += [{"slug": "f", "code": "ok", "version": "published"}]
        lines = [json.dumps(row) for row in rows] + ["not json", json.dumps({"slug": "e", "code": "ok", "version": "submitted"}),
                                                    json.dumps({"slug": "e", "code": "ok"})]  # no version: passed over
        work.mkdir()
        (work / "fetch.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        e = self.record("e", where=work / "records", content=variant(1))                          # last ok: submitted
        f = self.record("f", where=work / "records", content=variant(2), file_version="accepted")  # the record wins
        g = self.record("g", where=work / "records", content=variant(3))                          # no line: published
        r = self.run_script("-i", str(e), str(f), str(g))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([self.title_of(p) for p in (e, f, g)], ["Preprint", "Accepted manuscript", "PDF"])
        self.assertEqual([json.loads(p.read_text())["attach"]["file_version"] for p in (e, f, g)],
                         ["preprint", "accepted", "published"])
        self.assertEqual([o["file_version"] for o in self.lines(r.stdout)[:3]], ["preprint", "accepted", "published"])

    def test_title_precedence_and_derived_titles(self):
        versions = {"pub": None, "acc": "accepted", "pre": "preprint", "sub": "submitted", "sup": "supplement",
                    "unk": "unknown", "odd": "author_version"}
        paths = {slug: self.record(slug, content=variant(n), **({"file_version": v} if v else {}))
                 for n, (slug, v) in enumerate(versions.items())}
        paths["own"] = self.record("own", content=variant(10), file_version="preprint", attach_title="Preprint (arXiv v2)")
        paths["html"] = self.record("html", content=HTML_BYTES, file_name="html.html")
        r = self.run_script("-i", *map(str, paths.values()))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({slug: self.title_of(p) for slug, p in paths.items()},
                         {"pub": "PDF", "acc": "Accepted manuscript", "pre": "Preprint", "sub": "Preprint",
                          "sup": "Supplement", "unk": "Full text (version unknown)", "odd": "Author version",
                          "own": "Preprint (arXiv v2)", "html": "Snapshot"})
        # stream mode: --title is the fallback for records without attach_title, over the derived title
        own = self.record("own2", content=variant(20), attach_title="Accepted manuscript (Article in Press)")
        plain = self.record("plain2", content=variant(21), file_version="accepted")
        r = self.run_script("-i", "--title", "Batch title", str(own), str(plain))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([self.title_of(own), self.title_of(plain)], ["Accepted manuscript (Article in Press)", "Batch title"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
