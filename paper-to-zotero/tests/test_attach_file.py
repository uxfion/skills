# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/attach_file.py against a minimal mock of Zotero's local API, including the 3-step file upload."""
import hashlib
import json
import os
import re
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
PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
HTML_BYTES = b"<!DOCTYPE html>\n<html><head><title>Article</title></head><body>Abstract text</body></html>\n"

def closed_port():
    """A port nothing listens on (bound then released), so a connection is refused at once instead of timing out."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class State:
    def __init__(self):
        self.items = {
            PARENT: {"key": PARENT, "version": 5, "itemType": "journalArticle", "title": "A Paper: With Colon",
                     "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"},
                                  {"creatorType": "author", "firstName": "Jing", "lastName": "Zhang"}],
                     "date": "2022-03-01"},
            PARENT2: {"key": PARENT2, "version": 2, "itemType": "conferencePaper", "title": "Second",
                      "creators": [{"creatorType": "author", "lastName": "Chen"}], "date": "2021"},
        }
        self.children = {PARENT: [], PARENT2: []}
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
        self.tmp = Path(tempfile.mkdtemp(prefix="attach_test_"))

    def run_script(self, *argv, stdin=None, base_url=None, cwd=None):
        env = {k: v for k, v in os.environ.items() if k != "ZOTERO_LOCAL_API_KEY"}
        cmd = [sys.executable, str(SCRIPT), *argv, "--base-url", base_url or self.base_url, "--key-file", str(self.key_file)]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, cwd=cwd)

    def record(self, slug, content=PDF_BYTES, file_name=None, **extra):
        """A record with `saved.key`, `item.DOI` and a file next to it; extras override or remove (None) fields."""
        rec = {"slug": slug, "item": {"itemType": "journalArticle", "title": "A Paper", "DOI": "10.1000/xyz"},
               "saved": {"key": PARENT, "version": 5, "created_at": "2026-09-23T00:00:00Z"}}
        if content is not None:
            name = file_name or f"{slug}.pdf"
            (self.tmp / name).write_bytes(content)
            rec["file"] = name
        for k, v in extra.items():
            if v is None:
                rec.pop(k, None)
            else:
                rec[k] = v
        path = self.tmp / f"{slug}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def lines(stream):
        return [json.loads(line) for line in stream.splitlines() if line.startswith("{")]

    def attachments_of(self, parent):
        return [it for it in self.state.items.values() if it.get("parentItem") == parent]


class SingleMode(Base):
    def test_v1_attach_then_already_attached(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(PDF_BYTES)
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "ok")
        self.assertEqual(out["item_key"], PARENT)
        self.assertEqual(out["attachment_key"], "ATTACH01")
        self.assertTrue(out["md5_ok"])
        self.assertEqual(out["filename"], "Liu and Zhang - 2022 - A Paper With Colon.pdf")
        self.assertFalse(out["reused_attachment"])
        self.assertFalse(out["file_existed"])
        att = self.state.items["ATTACH01"]
        self.assertEqual((att["linkMode"], att["contentType"], att["title"], att["url"]),
                         ("imported_url", "application/pdf", "PDF", "https://doi.org/10.1000/xyz"))
        self.assertEqual(self.state.uploads["ATTACH01"], PDF_BYTES)
        self.assertNotIn(API_KEY, r.stdout + r.stderr)
        r = self.run_script("--key", PARENT, "--file", str(pdf), "--url", "https://doi.org/10.1000/xyz")
        self.assertEqual(r.returncode, 0, r.stdout)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "already_attached")
        self.assertEqual(set(out), {"code", "item_key", "attachment_key", "md5_ok", "filename", "reused_attachment", "md5"})
        self.assertEqual(len(self.state.posts), 1)

    def test_v1_pre_check_failures(self):
        pdf = self.tmp / "paper.pdf"
        pdf.write_bytes(PDF_BYTES)
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
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["dry_run"])
        self.assertEqual(self.state.posts, [])
        self.assertEqual(self.run_script("--key", PARENT, "--file", str(pdf)).returncode, 2)  # --url missing


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
               "saved": {"key": PARENT}, "file": "x.pdf"}
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
                        item={"itemType": "journalArticle", "title": "no doi"}, content=None)
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
