# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/create_item.py against a minimal mock of Zotero's local API: v1 single mode and the record stream."""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_item.py"
SERVER_ID = "MOCKSRV1"
API_KEY = "mock-key-never-printed"
COLL, COLL2 = "AAAABBBB", "CCCCDDDD"

def closed_port():
    """A port nothing listens on (bound then released), so a connection is refused at once instead of timing out."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class State:
    """What the mock knows and records; reset per test."""

    def __init__(self):
        self.collections = {COLL: {"name": "tmp"}, COLL2: {"name": "医疗图像"}, "TRASHED1": {"name": "old", "deleted": True}}
        self.items = {}
        self.posts = []          # every POST /items body, in order
        self.gets = []           # every GET path
        self.counter = 0
        self.drop_collections = False   # answer with collections=[] to force readback_mismatch
        self.thin_response = False      # answer without `data` so the script must GET the item back
        self.post_status = None         # force a status on POST /items

    def next_key(self):
        self.counter += 1
        return f"ITEM{self.counter:04d}"


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

    def do_GET(self):
        s = self.server.state
        s.gets.append(self.path)
        if self.path == "/api/":
            return self.send(200, {"ok": True}, {"Zotero-Server-ID": SERVER_ID})
        m = re.match(r"^/api/users/0/collections/([A-Z0-9]{8})$", self.path)
        if m:
            c = s.collections.get(m.group(1))
            if not c:
                return self.send(404, b"Not found")
            return self.send(200, {"key": m.group(1), "data": {"key": m.group(1), **c}})
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})$", self.path)
        if m:
            it = s.items.get(m.group(1))
            if not it:
                return self.send(404, b"Not found")
            return self.send(200, {"key": it["key"], "version": it["version"], "data": it})
        self.send(404, b"Not found")

    def do_POST(self):
        s = self.server.state
        if self.path != "/api/users/0/items":
            return self.send(404, b"Not found")
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Zotero-API-Key") != API_KEY:
            return self.send(401, b"Invalid API key")
        if self.headers.get("Zotero-Server-ID") != SERVER_ID:
            return self.send(412, b"Zotero-Server-ID mismatch")
        body = json.loads(raw)
        s.posts.append(body)
        if s.post_status:
            return self.send(s.post_status, b"forced failure")
        successful, failed = {}, {}
        for i, obj in enumerate(body):
            if str(obj.get("title", "")).startswith("REJECT"):
                failed[str(i)] = {"code": 400, "message": f"mock rejects {obj['title']!r}"}
                continue
            key = s.next_key()
            data = {**obj, "key": key, "version": 1}
            if s.drop_collections:
                data["collections"] = []
            s.items[key] = data
            successful[str(i)] = {"key": key, "version": 1} if s.thin_response else {"key": key, "version": 1, "data": data}
        self.send(200, {"successful": successful, "unchanged": {}, "failed": failed})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.keydir = Path(tempfile.mkdtemp(prefix="create_item_key_"))
        cls.key_file = cls.keydir / "key.json"
        cls.key_file.write_text(json.dumps({"key": API_KEY, "serverID": SERVER_ID}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state = self.server.state = State()
        self.tmp = Path(tempfile.mkdtemp(prefix="create_item_test_"))

    def run_script(self, *argv, stdin=None, base_url=None, key_file=None):
        env = {k: v for k, v in os.environ.items() if k != "ZOTERO_LOCAL_API_KEY"}
        cmd = [sys.executable, str(SCRIPT), *argv, "--base-url", base_url or self.base_url,
               "--key-file", str(key_file or self.key_file)]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)

    @staticmethod
    def item(title="A paper about things", **extra):
        return {"itemType": "journalArticle", "title": title,
                "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}], "date": "2022", **extra}

    def record(self, slug, **extra):
        rec = {"slug": slug, "item": self.item(f"Paper {slug}"), "tags": [{"tag": "method/diffusion", "type": 0}],
               "collection": COLL}
        rec.update(extra)
        path = self.tmp / f"{slug}.json"
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def lines(stream):
        return [json.loads(line) for line in stream.splitlines() if line.startswith("{")]


class SingleMode(Base):
    def test_v1_flow_unchanged(self):
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        tags = self.tmp / "tags.json"
        tags.write_text(json.dumps(["deep learning", {"tag": "auto", "type": 1}]), encoding="utf-8")
        out = self.tmp / "saved.json"
        r = self.run_script("--item", str(item), "--collection", COLL, "--tags-file", str(tags), "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["code"], "ok")
        self.assertEqual(res["item_key"], "ITEM0001")
        self.assertTrue(res["filed"] and res["tags_ok"])
        self.assertEqual(res["collection_name"], "tmp")
        self.assertEqual(res["out"], str(out))
        saved = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(saved["item_key"], "ITEM0001")
        self.assertEqual(saved["tags"], [{"tag": "deep learning", "type": 0}, {"tag": "auto", "type": 1}])
        self.assertEqual(len(self.state.posts), 1)
        self.assertEqual(self.state.posts[0][0]["collections"], [COLL])
        self.assertNotIn(API_KEY, r.stdout + r.stderr)

    def test_v1_dry_run_and_failures(self):
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        r = self.run_script("--item", str(item), "--collection", COLL, "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(json.loads(r.stdout)["dry_run"])
        self.assertEqual(self.state.posts, [])
        r = self.run_script("--item", str(item), "--collection", "NOPE0000", "--out", str(self.tmp / "s.json"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "collection_not_found"))
        r = self.run_script("--item", str(item))
        self.assertEqual(r.returncode, 2)  # --out is required unless --dry-run
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"itemType": "attachment", "title": "x"}), encoding="utf-8")
        r = self.run_script("--item", str(bad), "--out", str(self.tmp / "s.json"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "item_invalid"))
        item.write_text(json.dumps(self.item("REJECT me")), encoding="utf-8")
        r = self.run_script("--item", str(item), "--out", str(self.tmp / "s.json"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "create_failed"))

    def test_v1_readback_mismatch(self):
        self.state.drop_collections = True
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        out = self.tmp / "saved.json"
        r = self.run_script("--item", str(item), "--collection", COLL, "--out", str(out))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "readback_mismatch"))
        self.assertTrue(out.exists())


class StreamMode(Base):
    def test_paths_stdout_records(self):
        p1, p2 = self.record("a"), self.record("b", citationKey="liu2022b")
        r = self.run_script(str(p1), str(p2))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        recs = self.lines(r.stdout)
        self.assertEqual([x["slug"] for x in recs], ["a", "b"])
        self.assertEqual(recs[0]["saved"]["key"], "ITEM0001")
        self.assertEqual(recs[1]["saved"]["key"], "ITEM0002")
        self.assertTrue(recs[0]["saved"]["created_at"].endswith("Z"))
        self.assertEqual(recs[0]["item"]["title"], "Paper a")  # the rest of the record is untouched
        self.assertNotIn("saved", json.loads(p1.read_text()))  # no -i: the files are untouched
        err = self.lines(r.stderr)
        self.assertEqual(err[-1]["summary"], {"total": 2, "ok": 2, "skipped": 0, "failed": 0})
        self.assertEqual([x["code"] for x in err[:2]], ["ok", "ok"])
        self.assertEqual(len(self.state.posts), 1)
        self.assertEqual(len(self.state.posts[0]), 2)

    def test_stdin_jsonl_array_object(self):
        recs = [{"slug": "s1", "item": self.item("S one"), "tags": [], "collection": COLL},
                {"slug": "s2", "item": self.item("S two"), "tags": ["t"], "collection": COLL}]
        r = self.run_script(stdin="\n".join(json.dumps(x) for x in recs) + "\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x["saved"]["key"] for x in self.lines(r.stdout)], ["ITEM0001", "ITEM0002"])
        r = self.run_script(stdin=json.dumps(recs))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.lines(r.stdout)), 2)
        r = self.run_script(stdin=json.dumps(recs[0], indent=2))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["slug"], "s1")
        self.assertEqual(self.lines(r.stderr)[-1]["summary"]["total"], 1)

    def test_in_place_writes_back_and_summarizes(self):
        p1 = self.record("a", extra_field={"keep": "me"}, note="中文")
        p2 = self.record("b")
        r = self.run_script("-i", str(p1), str(p2))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[0], {"slug": "a", "code": "ok", "key": "ITEM0001", "version": 1, "collection": COLL})
        self.assertEqual(out[-1], {"summary": {"total": 2, "ok": 2, "skipped": 0, "failed": 0}})
        raw = p1.read_text(encoding="utf-8")
        rec = json.loads(raw)
        self.assertEqual(rec["saved"]["key"], "ITEM0001")
        self.assertEqual(rec["extra_field"], {"keep": "me"})
        self.assertIn("中文", raw)
        self.assertTrue(raw.endswith("}\n"))
        self.assertIn('\n  "saved": {', raw)
        self.assertFalse(list(self.tmp.glob(".*.tmp")))

    def test_in_place_needs_paths_and_empty_input(self):
        r = self.run_script("-i", stdin="{}")
        self.assertEqual(r.returncode, 2)
        r = self.run_script(stdin="   \n")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "no_records"))
        self.assertEqual(self.state.gets, [])  # nothing checked before the input error
        r = self.run_script(stdin="[1, 2]")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "input_invalid"))

    def test_skips_saved_and_found(self):
        p1 = self.record("a", saved={"key": "OLD00001", "version": 3, "created_at": "2026-01-01T00:00:00Z"})
        p2 = self.record("b", found={"key": "OLD00002", "version": 9})
        p3 = self.record("c")
        r = self.run_script("-i", str(p1), str(p2), str(p3))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual(out[0], {"slug": "a", "code": "skipped", "reason": "saved", "key": "OLD00001"})
        self.assertEqual(out[1], {"slug": "b", "code": "skipped", "reason": "found", "key": "OLD00002"})
        self.assertEqual(out[2]["code"], "ok")
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 1, "skipped": 2, "failed": 0})
        self.assertEqual(len(self.state.posts[0]), 1)
        self.assertEqual(json.loads(p1.read_text())["saved"]["key"], "OLD00001")  # untouched

    def test_no_collection_and_default(self):
        p1 = self.record("a", collection=None)
        del_rec = json.loads(p1.read_text())
        del del_rec["collection"]
        p1.write_text(json.dumps(del_rec), encoding="utf-8")
        r = self.run_script("-i", str(p1))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.lines(r.stdout)[0]["code"], "no_collection")
        self.assertEqual(self.state.posts, [])
        self.assertNotIn("saved", json.loads(p1.read_text()))
        r = self.run_script("-i", "--collection", COLL2, str(p1))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state.posts[0][0]["collections"], [COLL2])
        p2 = self.record("b", collection=COLL2)
        r = self.run_script("-i", "--collection", COLL, str(p2))  # the record's own collection wins
        self.assertEqual(self.state.posts[-1][0]["collections"], [COLL2])

    def test_chunks_of_fifty(self):
        paths = [self.record(f"r{i:03d}") for i in range(120)]
        r = self.run_script("-i", *map(str, paths))
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertEqual([len(p) for p in self.state.posts], [50, 50, 20])
        self.assertEqual(self.lines(r.stdout)[-1]["summary"], {"total": 120, "ok": 120, "skipped": 0, "failed": 0})
        keys = {json.loads(p.read_text())["saved"]["key"] for p in paths}
        self.assertEqual(len(keys), 120)
        self.assertEqual(json.loads(paths[119].read_text())["saved"]["key"], "ITEM0120")  # order preserved

    def test_citation_key_pinned_and_verified(self):
        p = self.record("a", citationKey="liu2022progressive")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state.posts[0][0]["citationKey"], "liu2022progressive")
        self.assertEqual(self.state.items["ITEM0001"]["citationKey"], "liu2022progressive")
        p2 = self.record("b", item=self.item("Paper b", citationKey="old"), citationKey="new2022")
        self.run_script("-i", str(p2))
        self.assertEqual(self.state.posts[-1][0]["citationKey"], "new2022")  # the record's key wins over item's
        p3 = self.record("c")
        self.run_script("-i", str(p3))
        self.assertNotIn("citationKey", self.state.posts[-1][0])  # none given: Zotero / BBT generates one

    def test_thin_post_response_reads_item_back(self):
        self.state.thin_response = True
        p = self.record("a", citationKey="liu2022x")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("/api/users/0/items/ITEM0001", self.state.gets)

    def test_failure_isolation(self):
        p1 = self.record("a")
        p2 = self.record("b", item=self.item("REJECT this one"))
        p3 = self.record("c", collection="NOPE0000")
        p4 = self.record("d", item={"itemType": "journalArticle"})  # no title
        p5 = self.record("e", tags=[{"tag": "", "type": 0}])
        p6 = self.record("f")
        r = self.run_script("-i", str(p1), str(p2), str(p3), str(p4), str(p5), str(p6))
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual([o["code"] for o in out[:6]],
                         ["ok", "create_failed", "collection_not_found", "item_invalid", "tags_invalid", "ok"])
        self.assertEqual(out[1]["message"], "mock rejects 'REJECT this one'")
        self.assertIn("hint", out[1])
        self.assertEqual(out[-1]["summary"], {"total": 6, "ok": 2, "skipped": 0, "failed": 4})
        self.assertEqual(len(self.state.posts), 1)
        self.assertEqual(len(self.state.posts[0]), 3)  # a, b, f were posted together
        self.assertEqual(json.loads(p1.read_text())["saved"]["key"], "ITEM0001")
        self.assertEqual(json.loads(p6.read_text())["saved"]["key"], "ITEM0002")
        for p in (p2, p3, p4, p5):
            self.assertNotIn("saved", json.loads(p.read_text()), p.name)

    def test_readback_mismatch_still_records_saved(self):
        self.state.drop_collections = True
        p = self.record("a")
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 1)
        line = self.lines(r.stdout)[0]
        self.assertEqual(line["code"], "readback_mismatch")
        self.assertFalse(line["filed"])
        self.assertEqual(json.loads(p.read_text())["saved"]["key"], "ITEM0001")  # the item exists: recorded

    def test_dry_run_writes_nothing(self):
        p1, p2 = self.record("a"), self.record("b", saved={"key": "OLD00001"})
        r = self.run_script("-i", "--dry-run", str(p1), str(p2))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.lines(r.stdout)
        self.assertEqual((out[0]["code"], out[0]["dry_run"], out[0]["collection_name"]), ("ok", True, "tmp"))
        self.assertEqual(out[1]["code"], "skipped")
        self.assertEqual(out[-1]["summary"], {"total": 2, "ok": 1, "skipped": 1, "failed": 0})
        self.assertEqual(self.state.posts, [])
        self.assertNotIn("saved", json.loads(p1.read_text()))
        r = self.run_script("--dry-run", str(p1))  # without -i the records come back unchanged
        self.assertNotIn("saved", self.lines(r.stdout)[0])

    def test_whole_chunk_rejected_then_next_chunk_proceeds(self):
        # A non-200 POST fails the chunk's records only; the next chunk is still tried.
        self.state.post_status = 400
        p1 = self.record("a")
        r = self.run_script("-i", str(p1))
        self.assertEqual((r.returncode, self.lines(r.stdout)[0]["code"]), (1, "create_failed"))
        self.assertNotIn("saved", json.loads(p1.read_text()))

    def test_unreachable_and_bad_key(self):
        p = self.record("a")
        r = self.run_script("-i", str(p), base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "zotero_unreachable"))
        other = self.tmp / "otherkey.json"
        other.write_text(json.dumps({"key": "wrong", "serverID": SERVER_ID}), encoding="utf-8")
        r = self.run_script("-i", str(p), key_file=other)
        self.assertEqual(r.returncode, 2)
        out = self.lines(r.stdout)
        self.assertEqual(out[0]["code"], "key_rejected")
        self.assertEqual(out[-1]["summary"]["stopped"], "key_rejected")
        self.assertNotIn("saved", json.loads(p.read_text()))
        r = self.run_script("-i", str(p), key_file=self.tmp / "missing.json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_key"))

    def test_mode_conflicts(self):
        p = self.record("a")
        self.assertEqual(self.run_script("--item", "x.json", str(p)).returncode, 2)
        self.assertEqual(self.run_script("--out", "x.json", str(p)).returncode, 2)
        self.assertEqual(self.run_script("--tags-file", "x.json", str(p)).returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
