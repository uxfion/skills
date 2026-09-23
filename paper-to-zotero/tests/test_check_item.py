# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/check_item.py against a minimal local-API mock (itemTypes, itemTypeFields, itemTypeCreatorTypes, schema)."""

import http.server
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_item.py"

FIELDS = {
    "journalArticle": [{"field": f} for f in ("title", "abstractNote", "publicationTitle", "volume", "date", "DOI", "url", "extra")],
    "conferencePaper": [{"field": "title"}, {"field": "abstractNote"}, {"field": "proceedingsTitle", "baseField": "publicationTitle"},
                        {"field": "conferenceName"}, {"field": "date"}, {"field": "DOI"}, {"field": "url"}, {"field": "publisher"},
                        {"field": "extra"}],
}
CREATORS = [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}]
SCHEMA = {"version": 44, "itemTypes": [{"itemType": t, "fields": f, "creatorTypes": CREATORS} for t, f in FIELDS.items()]}

OK_ITEM = {"itemType": "journalArticle", "title": "A Paper", "creators": [{"creatorType": "author", "firstName": "A", "lastName": "B"}],
           "date": "2024", "DOI": "10.1/x", "publicationTitle": "J"}
MAPPED_ITEM = {"itemType": "conferencePaper", "title": "A Talk", "creators": [{"creatorType": "author", "name": "C"}],
               "date": "2024", "DOI": "10.1/y", "publicationTitle": "Proc"}
UNKNOWN_ITEM = {"itemType": "journalArticl", "title": "Typo"}


class Handler(http.server.BaseHTTPRequestHandler):
    disabled = False

    def log_message(self, *a):
        pass

    def send_json(self, obj, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        if Handler.disabled:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Local API is not enabled")
            return
        if url.path == "/api/itemTypes":
            return self.send_json([{"itemType": t, "localized": t} for t in FIELDS])
        if url.path == "/api/itemTypeFields":
            return self.send_json(FIELDS.get(q["itemType"][0], []))
        if url.path == "/api/itemTypeCreatorTypes":
            return self.send_json([{"creatorType": c["creatorType"]} for c in CREATORS])
        if url.path == "/api/schema":
            return self.send_json(SCHEMA)
        self.send_json("Not found", 404)


class CheckItemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Handler.disabled = False
        self.tmp = Path(tempfile.mkdtemp())

    def run_script(self, *args, stdin=None, base=None):
        return subprocess.run([sys.executable, str(SCRIPT), "--base-url", base or self.base, *args],
                              input=stdin, capture_output=True, text=True)

    def lines(self, text):
        return [json.loads(ln) for ln in text.splitlines() if ln.strip()]

    def write(self, name, obj):
        path = self.tmp / name
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def test_v1_item_mode(self):
        proc = self.run_script("--item", str(self.write("ok.json", OK_ITEM)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["code"], "ok")
        self.assertEqual(report["missing_minimum"], [])
        proc = self.run_script("--item", str(self.write("mapped.json", MAPPED_ITEM)))
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        self.assertEqual(report["code"], "needs_attention")
        self.assertEqual(report["mapped"], [{"from": "publicationTitle", "to": "proceedingsTitle"}])
        proc = self.run_script("--item", str(self.write("unknown.json", UNKNOWN_ITEM)))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "unknown_item_type")
        proc = self.run_script("--item", str(self.tmp / "nope.json"))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "item_unreadable")

    def test_item_excludes_stream_flags(self):
        proc = self.run_script("--item", str(self.write("ok.json", OK_ITEM)), "-i")
        self.assertEqual(proc.returncode, 2)
        proc = self.run_script("-i")
        self.assertEqual(proc.returncode, 2)

    def test_stream_paths_to_stdout(self):
        p1 = self.write("a.json", {"slug": "a", "item": OK_ITEM})
        p2 = self.write("b.json", {"slug": "b", "item": MAPPED_ITEM})
        p3 = self.write("c.json", {"slug": "c", "id": "10.1/z"})
        proc = self.run_script(str(p1), str(p2), str(p3))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual([r["checks"]["code"] for r in rows], ["ok", "needs_attention", "no_item"])
        self.assertEqual(rows[0]["item"], OK_ITEM, "record returned whole")
        self.assertTrue(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rows[0]["checks"]["checked_at"]))
        self.assertEqual(self.lines(proc.stderr)[-1], {"summary": {"total": 3, "ok": 1, "skipped": 0, "failed": 2}})
        self.assertEqual(json.loads(p1.read_text()), {"slug": "a", "item": OK_ITEM}, "files untouched without -i")

    def test_stream_in_place_and_rerun(self):
        p1 = self.write("a.json", {"slug": "a", "item": OK_ITEM, "note_to_self": "keep me"})
        p2 = self.write("b.json", {"slug": "b", "item": MAPPED_ITEM})
        proc = self.run_script("-i", str(p1), str(p2))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        rows = self.lines(proc.stdout)
        self.assertEqual(rows[0], {"slug": "a", "code": "ok", "itemType": "journalArticle"})
        self.assertEqual(rows[1]["code"], "needs_attention")
        self.assertEqual(rows[1]["mapped"], [{"from": "publicationTitle", "to": "proceedingsTitle"}])
        self.assertEqual(rows[2], {"summary": {"total": 2, "ok": 1, "skipped": 0, "failed": 1}})
        self.assertEqual(proc.stderr.strip(), "", "stderr quiet in -i mode")
        text = p1.read_text()
        rec = json.loads(text)
        self.assertEqual(rec["note_to_self"], "keep me")
        self.assertEqual(rec["checks"]["code"], "ok")
        self.assertTrue(text.endswith("\n") and text.startswith("{\n  "), "indent=2 with trailing newline")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["a.json", "b.json"], "no temp files left")

        first = rec["checks"]["checked_at"]
        proc = self.run_script("-i", str(p1))
        self.assertEqual(proc.returncode, 0)
        rec2 = json.loads(p1.read_text())
        self.assertEqual(rec2["checks"]["code"], "ok", "re-checked, not skipped")
        self.assertGreaterEqual(rec2["checks"]["checked_at"], first)

    def test_stdin_forms(self):
        proc = self.run_script(stdin=json.dumps({"slug": "one", "item": OK_ITEM}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.lines(proc.stdout)[0]["checks"]["code"], "ok")
        proc = self.run_script(stdin=json.dumps([{"slug": "one", "item": OK_ITEM}, {"slug": "two", "item": OK_ITEM}]))
        self.assertEqual(len(self.lines(proc.stdout)), 2)
        proc = self.run_script(stdin="\n".join(json.dumps({"slug": s, "item": OK_ITEM}) for s in "abc") + "\n")
        self.assertEqual([r["slug"] for r in self.lines(proc.stdout)], ["a", "b", "c"])
        proc = self.run_script(stdin="")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["code"], "no_records")

    def test_bad_file_does_not_stop_the_others(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json")
        good = self.write("good.json", {"slug": "good", "item": OK_ITEM})
        proc = self.run_script("-i", str(bad), str(good))
        self.assertEqual(proc.returncode, 1)
        rows = self.lines(proc.stdout)
        self.assertEqual((rows[0]["slug"], rows[0]["code"]), ("bad", "invalid_json"))
        self.assertEqual(rows[1]["code"], "ok")
        self.assertEqual(rows[2]["summary"], {"total": 2, "ok": 1, "skipped": 0, "failed": 1})
        self.assertEqual(bad.read_text(), "{not json", "unreadable input never written back")

    def test_cannot_check(self):
        proc = self.run_script("--item", str(self.write("ok.json", OK_ITEM)), base="http://127.0.0.1:9")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "zotero_unreachable")
        Handler.disabled = True
        proc = self.run_script(stdin=json.dumps({"slug": "one", "item": OK_ITEM}))
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "local_api_disabled")


if __name__ == "__main__":
    unittest.main()
