# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/file_and_tag.py against a minimal mock of Zotero's local API: remove_collection, batch "cite", existing semantics."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "file_and_tag.py"
SERVER_ID = "MOCKSRV1"
API_KEY = "mock-key-never-printed"
LIB = "/api/users/0"
CA, CB, CC, CX, TRASHC = "COLLAAAA", "COLLBBBB", "COLLCCCC", "COLLXXXX", "COLLTRSH"
I1, I2, I3, ATT, DUP1, DUP2 = "ITEM0001", "ITEM0002", "ITEM0003", "ATTACH01", "DUPKEY01", "DUPKEY02"


def make_items():
    def item(key, version, **data):
        return {"key": key, "version": version, "data": {"key": key, "version": version, **data}}
    return {
        I1: item(I1, 10, itemType="journalArticle", title="CycleGAN", citationKey="zhu2017unpaired",
                 collections=[CA, CB, CC], tags=[{"tag": "GAN", "type": 0}]),
        I2: item(I2, 20, itemType="journalArticle", title="StyleGAN", citationKey="karras2019style", collections=[CA], tags=[]),
        I3: item(I3, 30, itemType="journalArticle", title="DDPM", citationKey="ho2020denoising", collections=[], tags=[]),
        ATT: item(ATT, 40, itemType="attachment", parentItem=I1, title="PDF", tags=[]),
        DUP1: item(DUP1, 50, itemType="journalArticle", title="Dup one", citationKey="dupkey", collections=[], tags=[]),
        DUP2: item(DUP2, 51, itemType="journalArticle", title="Dup two", citationKey="dupkey", collections=[], tags=[]),
    }


class State:
    def __init__(self):
        self.items = make_items()
        self.collections = {CA: {"name": "CC作业"}, CB: {"name": "自然图像"}, CC: {"name": "tmp"}, CX: {"name": "new"},
                            TRASHC: {"name": "old", "deleted": True}}
        self.patches, self.posts, self.gets = [], [], []
        self.search_sees_citekey = True


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

    def authorized(self):
        if self.headers.get("Zotero-API-Key") != API_KEY:
            self.send(401, b"Invalid API key")
            return False
        return True

    def do_GET(self):
        s = self.server.state
        url = urllib.parse.urlsplit(self.path)
        path, q = url.path, {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        s.gets.append(self.path)
        if path == "/api/":
            return self.send(200, {"ok": True}, {"Zotero-Server-ID": SERVER_ID})
        if path.startswith(f"{LIB}/collections/"):
            key = path.rsplit("/", 1)[1]
            c = s.collections.get(key)
            return self.send(200, {"key": key, "data": {"key": key, **c}}) if c else self.send(404, b"Not found")
        if path in (f"{LIB}/items", f"{LIB}/items/top"):
            rows = list(s.items.values())
            if path.endswith("/top"):
                rows = [it for it in rows if not it["data"].get("parentItem")]
            if "q" in q:
                needle = q["q"].casefold()
                fields = [f for f in ("title", "citationKey") if f != "citationKey" or s.search_sees_citekey]
                rows = [it for it in rows if any(needle in str(it["data"].get(f, "")).casefold() for f in fields)]
            start, limit = int(q.get("start", 0)), int(q.get("limit", 25))
            return self.send(200, rows[start:start + limit])
        if path.startswith(f"{LIB}/items/"):
            it = s.items.get(path.rsplit("/", 1)[1])
            return self.send(200, it) if it else self.send(404, b"Not found")
        self.send(404, b"Not found")

    def apply(self, it, patch):
        it["data"].update({k: v for k, v in patch.items() if k not in ("key", "version")})
        it["version"] += 1
        it["data"]["version"] = it["version"]

    def do_PATCH(self):
        s = self.server.state
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if not self.authorized():
            return
        it = s.items.get(self.path.rsplit("/", 1)[1])
        if not it:
            return self.send(404, b"Not found")
        s.patches.append((it["key"], body))
        if self.headers.get("If-Unmodified-Since-Version") != str(it["version"]):
            return self.send(412, b"Item has been modified since specified version")
        self.apply(it, body)
        self.send(204)

    def do_POST(self):
        s = self.server.state
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if not self.authorized():
            return
        s.posts.append(body)
        successful, failed = {}, {}
        for i, obj in enumerate(body):
            it = s.items.get(obj["key"])
            if it["version"] != obj["version"]:
                failed[str(i)] = {"code": 412, "message": "Item has been modified"}
                continue
            self.apply(it, obj)
            successful[str(i)] = {"key": it["key"], "version": it["version"], "data": it["data"]}
        self.send(200, {"successful": successful, "unchanged": {}, "failed": failed})


class FileAndTagTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.keydir = Path(tempfile.mkdtemp(prefix="file_and_tag_key_"))
        cls.config = cls.keydir / "config.json"
        cls.config.write_text(json.dumps({"zotero": {"key": API_KEY, "serverID": SERVER_ID}}), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state = self.server.state = State()
        self.tmp = Path(tempfile.mkdtemp(prefix="file_and_tag_test_"))

    def run_script(self, *argv):
        env = dict(os.environ, PAPER_TO_ZOTERO_CONFIG=str(self.config))
        cmd = [sys.executable, str(SCRIPT), *argv, "--base-url", self.base_url]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotIn(API_KEY, r.stdout + r.stderr)
        return r

    def batch(self, entries):
        path = self.tmp / "changes.json"
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def colls(self, key):
        return self.state.items[key]["data"]["collections"]

    # --- single mode: --remove-collection ---------------------------------------

    def test_remove_collection_keeps_the_others(self):
        r = self.run_script("--key", I1, "--remove-collection", CA)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["code"], out["filed"]), ("ok", True))
        self.assertEqual(out["collection"], {"from": [CA, CB, CC], "to": [CB, CC]})
        self.assertEqual(self.colls(I1), [CB, CC])
        self.assertEqual(self.state.patches, [(I1, {"collections": [CB, CC]})])
        self.assertNotIn(f"{LIB}/collections/{CA}", self.state.gets, "a removed collection is not looked up")

    def test_add_and_remove_combine_and_rerun_is_a_no_op(self):
        argv = ("--cite", "zhu2017unpaired", "--add-collection", CX, "--remove-collection", CA, "--remove-collection", CC)
        r = self.run_script(*argv)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.colls(I1), [CB, CX])
        r = self.run_script(*argv)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["unchanged"])
        self.assertEqual(len(self.state.patches), 1)

    def test_remove_a_collection_the_item_is_not_in(self):
        r = self.run_script("--key", I2, "--remove-collection", "NOSUCH01", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["unchanged"])
        self.assertEqual(self.state.patches, [])

    def test_remove_collection_argument_errors(self):
        self.assertEqual(self.run_script("--key", I1, "--collection", CA, "--remove-collection", CB).returncode, 2)
        self.assertEqual(self.run_script("--batch", "x.json", "--remove-collection", CB).returncode, 2)
        r = self.run_script("--key", I1, "--add-collection", CA, "--remove-collection", CA)
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "invalid_collection"))
        r = self.run_script("--key", I1, "--remove-collection", "bad")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "invalid_collection"))
        r = self.run_script("--key", ATT, "--remove-collection", CA)
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "not_a_parent"))
        self.assertEqual(self.state.patches, [])

    # --- batch: remove_collection and cite ----------------------------------------

    def test_batch_remove_collection_string_and_list(self):
        r = self.run_script("--batch", self.batch([
            {"key": I1, "remove_collection": [CA, CC], "add_collection": CX},
            {"key": I2, "remove_collection": CA},
        ]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["written"], out["failed"]), (2, 0))
        self.assertEqual(self.colls(I1), [CB, CX])
        self.assertEqual(self.colls(I2), [])
        self.assertEqual(len(self.state.posts), 1)

    def test_batch_cite_entries(self):
        r = self.run_script("--batch", self.batch([
            {"cite": "zhu2017unpaired", "remove_collection": CA},
            {"cite": "karras2019style", "tags": ["GAN"]},
            {"key": I3, "add_collection": CB},
        ]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([(x["key"], x.get("cite"), x["result"]) for x in out["results"]],
                         [(I1, "zhu2017unpaired", "ok"), (I2, "karras2019style", "ok"), (I3, None, "ok")])
        self.assertEqual(self.colls(I1), [CB, CC])
        self.assertEqual(self.state.items[I2]["data"]["tags"], [{"tag": "GAN", "type": 0}])
        self.assertFalse(any("/items/top" in g for g in self.state.gets), "the search found every cite")

    def test_batch_cite_fallback_scan_once_and_dry_run(self):
        self.state.search_sees_citekey = False
        r = self.run_script("--batch", self.batch([
            {"cite": "zhu2017unpaired", "remove_collection": CA},
            {"cite": "ho2020denoising", "add_collection": CB},
        ]), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([(c["key"], c["cite"]) for c in out["changes"]], [(I1, "zhu2017unpaired"), (I3, "ho2020denoising")])
        self.assertEqual(out["changes"][0]["collection"], {"from": [CA, CB, CC], "to": [CB, CC]})
        self.assertEqual(sum(g.startswith(f"{LIB}/items/top") for g in self.state.gets), 1)
        self.assertEqual((self.state.posts, self.state.patches), ([], []))

    def test_batch_cite_failures_write_nothing(self):
        r = self.run_script("--batch", self.batch([{"key": I2, "add_collection": CB},
                                                   {"cite": "nobody2000", "add_collection": CB},
                                                   {"cite": "dupkey", "add_collection": CB}]))
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertEqual(out["code"], "cite_not_found")
        self.assertEqual(out["cites_not_found"], ["nobody2000"])
        self.assertEqual(out["cites_ambiguous"], [{"cite": "dupkey", "keys": [DUP1, DUP2]}])
        r = self.run_script("--batch", self.batch([{"cite": "dupkey", "add_collection": CB}]))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "cite_ambiguous"))
        self.assertEqual(self.state.posts, [])

    def test_batch_entry_shape_errors(self):
        for entries in ([{"key": I1, "cite": "zhu2017unpaired", "add_collection": CB}],      # both
                        [{"add_collection": CB}],                                           # neither
                        [{"cite": "", "add_collection": CB}],
                        [{"key": I1, "collection": CB, "remove_collection": CA}],           # absolute + remove
                        [{"key": I1, "remove_collection": {"x": 1}}],
                        [{"key": I1, "add_collection": CA, "remove_collection": [CA]}],
                        [{"cite": "zhu2017unpaired", "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}],
                        [{"key": I1, "add_collection": CB}, {"cite": "zhu2017unpaired", "tags": []}]):  # same item twice
            r = self.run_script("--batch", self.batch(entries))
            self.assertEqual(r.returncode, 1, entries)
            self.assertIn(json.loads(r.stdout)["code"], ("invalid_batch_file", "invalid_collection"), entries)
        self.assertEqual(self.state.posts, [])

    # --- existing semantics -----------------------------------------------------------

    def test_existing_absolute_and_add_semantics(self):
        tags = self.tmp / "tags.json"
        tags.write_text(json.dumps(["diffusion", {"tag": "auto", "type": 1}]), encoding="utf-8")
        r = self.run_script("--key", I3, "--collection", CB, "--tags-file", str(tags))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.colls(I3), [CB])
        self.assertEqual(self.state.items[I3]["data"]["tags"], [{"tag": "diffusion", "type": 0}, {"tag": "auto", "type": 1}])
        r = self.run_script("--key", I3, "--add-collection", CC)
        self.assertEqual(self.colls(I3), [CB, CC])
        r = self.run_script("--key", I3, "--collection", "none")
        self.assertEqual(self.colls(I3), [])
        r = self.run_script("--key", I3, "--add-collection", TRASHC)
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (1, "collection_not_found"))
        r = self.run_script("--batch", self.batch([{"key": I2, "collection": None, "add_tags": ["x"]}]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.colls(I2), self.state.items[I2]["data"]["tags"]), ([], [{"tag": "x", "type": 0}]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
