# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/create_item.py against a minimal mock of Zotero's local API: v1 single mode, the record stream,
collection lists and the duplicate check before the POST (which runs the real find_in_library.py against the same mock)."""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timezone
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
        self.items = {}          # key -> item data (the library: created by POST or put there by a test)
        self.posts = []          # every POST /items body, in order
        self.gets = []           # every GET path
        self.counter = 0
        self.drop_collections = False   # answer with collections=[] to force readback_mismatch
        self.drop_collection = None     # leave this one collection off created items
        self.thin_response = False      # answer without `data` so the script must GET the item back
        self.post_status = None         # force a status on POST /items
        self.search_status = None       # force a status on item searches (find_in_library's look-up)

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

    def page(self, rows, q):
        start, limit = int(q.get("start", 0)), int(q.get("limit", 25))
        self.send(200, rows[start:start + limit], {"Total-Results": str(len(rows))})

    def do_GET(self):
        s = self.server.state
        s.gets.append(self.path)
        url = urllib.parse.urlsplit(self.path)
        path, q = url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if path == "/api/":
            return self.send(200, {"ok": True}, {"Zotero-Server-ID": SERVER_ID})
        if path == "/api/users/0/collections":
            return self.page([{"key": k, "data": {"key": k, "parentCollection": False, **c}} for k, c in s.collections.items()], q)
        m = re.match(r"^/api/users/0/collections/([A-Z0-9]{8})$", path)
        if m:
            c = s.collections.get(m.group(1))
            if not c:
                return self.send(404, b"Not found")
            return self.send(200, {"key": m.group(1), "data": {"key": m.group(1), **c}})
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})/children$", path)
        if m:
            return self.page([wrap(d) for d in s.items.values() if d.get("parentItem") == m.group(1)], q)
        m = re.match(r"^/api/users/0/items/([A-Z0-9]{8})$", path)
        if m:
            it = s.items.get(m.group(1))
            if not it:
                return self.send(404, b"Not found")
            return self.send(200, wrap(it))
        if path in ("/api/users/0/items", "/api/users/0/items/top"):
            if s.search_status:
                return self.send(s.search_status, b"forced failure")
            rows = [d for d in s.items.values() if not d.get("deleted")]
            if path.endswith("/top"):
                rows = [d for d in rows if not d.get("parentItem")]
            if "q" in q:  # like the local API: qmode fields covers identifiers, the default only title / creators / year
                needle, mode = q["q"].casefold(), q.get("qmode", "titleCreatorYear")
                keys = {"everything": None, "fields": ["title", "DOI", "archiveID", "url", "extra"]}.get(mode, ["title", "date"])
                rows = [d for d in rows if any(needle in str(v).casefold() for k, v in d.items()
                                               if isinstance(v, str) and (keys is None or k in keys))]
            return self.page([wrap(d) for d in rows], q)
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
            data = {**obj, "key": key, "version": 1, "dateAdded": now_z()}
            if s.drop_collections:
                data["collections"] = []
            if s.drop_collection:
                data["collections"] = [c for c in data["collections"] if c != s.drop_collection]
            s.items[key] = data
            successful[str(i)] = {"key": key, "version": 1} if s.thin_response else {"key": key, "version": 1, "data": data}
        self.send(200, {"successful": successful, "unchanged": {}, "failed": failed})


def now_z():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wrap(data):
    return {"key": data["key"], "version": data["version"], "data": data}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.keydir = Path(tempfile.mkdtemp(prefix="create_item_key_"))
        cls.config = cls.keydir / "config.json"
        cls.config.write_text(json.dumps({"zotero": {"key": API_KEY, "serverID": SERVER_ID}}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state = self.server.state = State()
        self.tmp = Path(tempfile.mkdtemp(prefix="create_item_test_"))  # the work dir: .started + records/
        self.recdir = self.tmp / "records"
        self.recdir.mkdir()
        self.started = self.tmp / ".started"
        self.started.touch()
        an_hour_ago = time.time() - 3600
        os.utime(self.started, (an_hour_ago, an_hour_ago))

    def run_script(self, *argv, stdin=None, base_url=None, config=None):
        env = dict(os.environ, PAPER_TO_ZOTERO_CONFIG=str(config or self.config))
        cmd = [sys.executable, str(SCRIPT), *argv, "--base-url", base_url or self.base_url]
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)

    @staticmethod
    def item(title="A paper about things", **extra):
        return {"itemType": "journalArticle", "title": title,
                "creators": [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}], "date": "2022", **extra}

    def record(self, slug, **extra):
        rec = {"slug": slug, "item": self.item(f"Paper {slug}"), "tags": [{"tag": "method/diffusion", "type": 0}],
               "collection": COLL}
        rec.update(extra)
        path = self.recdir / f"{slug}.json"
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
        self.state.items.clear()  # the same records again: an empty library, or the duplicate check would stop them
        r = self.run_script(stdin=json.dumps(recs))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.lines(r.stdout)), 2)
        self.state.items.clear()
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
        self.assertFalse(list(self.recdir.glob(".*.tmp")))

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
        other = self.tmp / "otherconfig.json"
        other.write_text(json.dumps({"zotero": {"key": "wrong", "serverID": SERVER_ID}}), encoding="utf-8")
        r = self.run_script("-i", str(p), config=other)
        self.assertEqual(r.returncode, 2)
        out = self.lines(r.stdout)
        self.assertEqual(out[0]["code"], "key_rejected")
        self.assertEqual(out[-1]["summary"]["stopped"], "key_rejected")
        self.assertNotIn("saved", json.loads(p.read_text()))
        r = self.run_script("-i", str(p), config=self.tmp / "missing.json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_key"))

    def test_mode_conflicts(self):
        p = self.record("a")
        self.assertEqual(self.run_script("--item", "x.json", str(p)).returncode, 2)
        self.assertEqual(self.run_script("--out", "x.json", str(p)).returncode, 2)
        self.assertEqual(self.run_script("--tags-file", "x.json", str(p)).returncode, 2)


class CollectionLists(Base):
    def test_record_collection_list_files_in_all(self):
        p = self.record("a", collection=[COLL, COLL2, COLL])
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state.posts[0][0]["collections"], [COLL, COLL2])
        self.assertEqual(self.lines(r.stdout)[0], {"slug": "a", "code": "ok", "key": "ITEM0001", "version": 1,
                                                   "collection": [COLL, COLL2]})

    def test_repeated_collection_option_is_the_default(self):
        p = self.record("a")
        rec = json.loads(p.read_text())
        del rec["collection"]
        p.write_text(json.dumps(rec), encoding="utf-8")
        r = self.run_script("-i", "--dry-run", "--collection", COLL, "--collection", COLL2, str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["collection"], line["collection_name"]), ([COLL, COLL2], ["tmp", "医疗图像"]))
        r = self.run_script("-i", "--collection", COLL, "--collection", COLL2, str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state.posts[0][0]["collections"], [COLL, COLL2])

    def test_readback_checks_every_collection(self):
        self.state.drop_collection = COLL2
        p = self.record("a", collection=[COLL, COLL2])
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 1)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["code"], line["filed"], line["collections_missing"]), ("readback_mismatch", False, [COLL2]))
        self.assertEqual(json.loads(p.read_text())["saved"]["key"], "ITEM0001")

    def test_collection_list_errors(self):
        p1 = self.record("a", collection=[COLL, "bad"])
        p2 = self.record("b", collection=[COLL, "NOPE0000"])
        p3 = self.record("c", collection={"key": COLL})
        r = self.run_script("-i", str(p1), str(p2), str(p3))
        self.assertEqual(r.returncode, 1)
        self.assertEqual([o["code"] for o in self.lines(r.stdout)[:3]],
                         ["collection_invalid", "collection_not_found", "collection_invalid"])
        self.assertEqual(self.state.posts, [])
        self.assertEqual(self.run_script("-i", "--collection", "bad", str(p1)).returncode, 1)

    def test_single_mode_several_collections(self):
        item = self.tmp / "item.json"
        item.write_text(json.dumps(self.item()), encoding="utf-8")
        out = self.tmp / "saved.json"
        r = self.run_script("--item", str(item), "--collection", COLL, "--collection", COLL2, "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual((res["collection"], res["collection_name"], res["filed"]), ([COLL, COLL2], ["tmp", "医疗图像"], True))
        self.assertEqual(self.state.posts[0][0]["collections"], [COLL, COLL2])
        self.assertEqual(json.loads(out.read_text())["collection"], [COLL, COLL2])
        self.assertFalse(any("q=" in g for g in self.state.gets), "single mode does not look the library up")


OLD = "2020-01-01T00:00:00Z"
TITLE_ONLY = "same title; no identifier confirms it"


class DuplicateCheck(Base):
    """The look-up runs the real find_in_library.py: an identifier hit exists, anything else is the agent's call."""

    def library(self, key, **data):
        self.state.items[key] = {"key": key, "version": 7, "itemType": "journalArticle", "collections": [], "tags": [],
                                 "dateAdded": OLD, **data}

    def test_doi_hit_exists(self):
        self.library("LIBDOI01", title="Old title of the paper", DOI="10.1000/old.1", citationKey="liu2020old")
        p = self.record("a", item=self.item("A newer title", DOI="10.1000/OLD.1"))
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual(line, {"slug": "a", "code": "exists", "key": "LIBDOI01", "matched_by": "doi",
                                "citationKey": "liu2020old"})
        self.assertEqual(self.lines(r.stdout)[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        rec = json.loads(p.read_text())
        self.assertEqual((rec["found"]["key"], rec["found"]["matched_by"]), ("LIBDOI01", "doi"))
        self.assertNotIn("saved", rec)
        self.assertEqual(self.state.posts, [])
        r = self.run_script("-i", str(p))  # re-run: the record now has found -> skipped as before
        self.assertEqual(self.lines(r.stdout)[0]["code"], "skipped")

    def test_arxiv_hit_exists_unless_the_record_has_its_own_doi(self):
        self.library("LIBARX01", itemType="preprint", title="Denoising Diffusion Probabilistic Models (preprint)",
                     archiveID="arXiv:2006.11239", url="https://arxiv.org/abs/2006.11239")
        p1 = self.record("a", item=self.item("Denoising Diffusion Probabilistic Models", extra="arXiv: 2006.11239v2"))
        p2 = self.record("b", item=self.item("Denoising Diffusion Probabilistic Models", DOI="10.5555/published.1",
                                             extra="arXiv: 2006.11239"))
        r = self.run_script("-i", str(p1), str(p2))
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual((out[0]["code"], out[0]["matched_by"]), ("exists", "arxiv"))
        self.assertEqual(out[1]["code"], "possible_duplicate", "a published record vs the library's preprint")
        self.assertEqual(out[1]["candidates"][0]["key"], "LIBARX01")
        self.assertIn("preprint", out[1]["candidates"][0]["reason"])
        self.assertNotIn("found", json.loads(p2.read_text()))
        self.assertEqual(self.state.posts, [])

    def test_item_left_by_an_interrupted_run_is_not_created_twice(self):
        p = self.record("a", item=self.item("Paper a", DOI="10.1000/fresh.1"), collection=[COLL, COLL2])
        r = self.run_script(str(p))  # created, but the record file was never updated: as if interrupted
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("saved", json.loads(p.read_text()))
        r = self.run_script("-i", str(p))
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["code"], line["key"]), ("exists", "ITEM0001"))
        self.assertEqual(json.loads(p.read_text())["found"]["key"], "ITEM0001")
        self.assertEqual(len(self.state.posts), 1, "not created twice")

    def test_title_only_hit_is_a_possible_duplicate(self):
        self.library("LIBTTL01", title="Paper a", date="2021")
        p = self.record("a", item=self.item("Paper a", DOI="10.1000/new.1"))
        before = p.read_text()
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 1)
        line = self.lines(r.stdout)[0]
        self.assertEqual(line["code"], "possible_duplicate")
        self.assertEqual(line["candidates"], [{"key": "LIBTTL01", "title": "Paper a", "reason": TITLE_ONLY}])
        self.assertIn("distinct_from", line["hint"])
        self.assertEqual(p.read_text(), before, "the record is untouched")
        self.assertEqual(self.state.posts, [])

    def test_unresolved_near_match_in_found_is_not_skipped(self):
        self.library("LIBPRE01", itemType="preprint", title="Paper a")
        near = {"code": "near_match", "key": "LIBPRE01", "version": 7, "title": "Paper a",
                "reason": "library title contains the query title"}
        pair = {"code": "near_match", "key": "LIBPRE01", "version": 7, "title": "Paper a", "matched_by": "arxiv",
                "reason": "preprint/published pair: same arXiv id, different DOI"}
        p1 = self.record("a", found=near)
        p2 = self.record("b", item=self.item("Paper b", DOI="10.5555/pub.1"), found=pair)
        before = [p1.read_text(), p2.read_text()]
        for dry in ((), ("--dry-run",)):
            r = self.run_script("-i", *dry, str(p1), str(p2))
            self.assertEqual(r.returncode, 1, dry)
            out = self.lines(r.stdout)
            self.assertEqual([o["code"] for o in out[:2]], ["possible_duplicate", "possible_duplicate"])
            self.assertEqual(out[0]["candidates"], [{"key": "LIBPRE01", "title": "Paper a",
                                                     "reason": "library title contains the query title"}])
            self.assertEqual((out[1]["candidates"][0]["matched_by"], out[1]["candidates"][0]["reason"]),
                             ("arxiv", "preprint/published pair: same arXiv id, different DOI"))
            self.assertIn("distinct_from", out[0]["hint"])
            self.assertEqual(out[-1]["summary"], {"total": 2, "ok": 0, "skipped": 0, "failed": 2})
            self.assertEqual([p1.read_text(), p2.read_text()], before, "records untouched")
            self.assertEqual(self.state.posts, [])

    def test_near_match_resolved_by_the_agent(self):
        self.library("LIBPRE01", itemType="preprint", title="Paper a")
        same = self.record("a", found={"key": "LIBPRE01"})                    # the same paper
        also = self.record("c", found={"key": "LIBPRE01", "code": "found"})
        other = self.record("b", item=self.item("Paper a"), distinct_from=["LIBPRE01"])  # a different paper
        r = self.run_script("-i", str(same), str(also), str(other))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([o["code"] for o in self.lines(r.stdout)[:3]], ["skipped", "skipped", "ok"])
        self.assertEqual([[o["title"] for o in post] for post in self.state.posts], [["Paper a"]])

    def test_same_doi_twice_in_the_library(self):
        self.library("LIBDUP01", title="Twin one", DOI="10.1000/twin.1")
        self.library("LIBDUP02", title="Twin two", DOI="10.1000/twin.1")
        p = self.record("a", item=self.item("Twin", DOI="10.1000/twin.1"))
        line = self.lines(self.run_script("-i", "--dry-run", str(p)).stdout)[0]
        self.assertEqual((line["code"], line["key"], line["duplicates"]), ("exists", "LIBDUP01", ["LIBDUP02"]))
        p = self.record("b", item=self.item("Twin", DOI="10.1000/twin.1"), distinct_from=["LIBDUP01"])
        line = self.lines(self.run_script("-i", str(p)).stdout)[0]
        self.assertEqual((line["code"], line["key"]), ("exists", "LIBDUP02"), "the other DOI hit is still a match")
        self.assertEqual(self.state.posts, [])

    def test_several_title_hits_are_all_candidates(self):
        self.library("LIBTTL01", title="Paper a")
        self.library("LIBTTL02", title="Paper a")
        r = self.run_script("-i", str(self.record("a")))
        self.assertEqual(r.returncode, 1)
        cands = self.lines(r.stdout)[0]["candidates"]
        self.assertEqual([(c["key"], c["title"]) for c in cands], [("LIBTTL01", "Paper a"), ("LIBTTL02", "Paper a")])

    def test_near_title_is_a_possible_duplicate(self):
        self.library("LIBNEAR1", title="Paper a: an extended study")
        r = self.run_script("-i", str(self.record("a")))
        self.assertEqual(r.returncode, 1)
        cand = self.lines(r.stdout)[0]["candidates"][0]
        self.assertEqual(cand["key"], "LIBNEAR1")
        self.assertIn("contains", cand["reason"])
        self.assertEqual(self.state.posts, [])

    def test_distinct_from_ignores_a_hit(self):
        self.library("LIBTTL01", title="Paper a")
        p = self.record("a", distinct_from=["LIBTTL01"])
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["code"], "ok")
        self.assertEqual(len(self.state.posts), 1)
        p2 = self.record("b", distinct_from={"x": 1})
        r = self.run_script("-i", str(p2))
        self.assertEqual(self.lines(r.stdout)[0]["code"], "distinct_from_invalid")

    def test_records_from_stdin(self):
        self.library("LIBNEW01", title="Just added", DOI="10.1000/now.1")
        rec = {"slug": "s", "item": self.item("Just added", DOI="10.1000/now.1"), "tags": [], "collection": COLL}
        r = self.run_script(stdin=json.dumps(rec))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r.stdout)[0]["found"]["key"], "LIBNEW01")
        self.assertEqual(self.lines(r.stderr)[-2]["code"], "exists")
        self.assertEqual(self.state.posts, [])

    def test_dry_run_reports_without_writing(self):
        self.library("LIBDOI01", title="Old", DOI="10.1000/old.1")
        self.library("LIBTTL01", title="Paper d")
        paths = [self.record("e", item=self.item("Old", DOI="10.1000/old.1")), self.record("d"), self.record("n")]
        before = [p.read_text() for p in paths]
        r = self.run_script("-i", "--dry-run", *map(str, paths))
        self.assertEqual(r.returncode, 1)
        out = self.lines(r.stdout)
        self.assertEqual([(o["code"], o.get("dry_run")) for o in out[:3]],
                         [("exists", None), ("possible_duplicate", None), ("ok", True)])
        self.assertEqual(out[-1]["summary"], {"total": 3, "ok": 1, "skipped": 1, "failed": 1})
        self.assertEqual([p.read_text() for p in paths], before)
        self.assertEqual(self.state.posts, [])

    def test_only_new_records_are_posted(self):
        self.library("LIBDOI01", title="Old", DOI="10.1000/old.1")
        self.library("LIBTTL01", title="Paper d")
        pe, pd, pn = (self.record("e", item=self.item("Old", DOI="10.1000/old.1")), self.record("d"), self.record("n"))
        r = self.run_script("-i", str(pe), str(pd), str(pn))
        self.assertEqual(r.returncode, 1)
        self.assertEqual([o["code"] for o in self.lines(r.stdout)[:3]], ["exists", "possible_duplicate", "ok"])
        self.assertEqual([[o["title"] for o in post] for post in self.state.posts], [["Paper n"]])

    def test_lookup_failure_stops_before_any_post(self):
        self.state.search_status = 500
        p = self.record("a")
        before = p.read_text()
        r = self.run_script("-i", str(p))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout)["code"], "lookup_failed")
        self.assertEqual(self.state.posts, [])
        self.assertEqual(p.read_text(), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
