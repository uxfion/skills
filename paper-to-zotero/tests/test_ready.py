# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/ready.py against the fake Zotero: the facts, the work directory, the key and its dialog."""
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from helpers import call, config_file, load, poppler_stubs, smoke
from fake_zotero import API_KEY, SERVER_ID, FakeZotero

from p2zlib import run

ready = load("ready")


class Ready(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_collection("AAAAAAAA", "自然图像")
        z.add_collection("BBBBBBBB", "Diffusion", "AAAAAAAA")
        z.add_collection("EEEEEEEE", "Old", deleted=True)
        z.add_collection("FFFFFFFF", "Under old", "EEEEEEEE")
        self.tmp = Path(tempfile.mkdtemp(prefix="p2z-ready-"))
        self.work, self.dl = run.Work(self.tmp / "work"), self.tmp / "dl"
        self.dl.mkdir()
        self.config = config_file(self.tmp, openalex_key="sk-SECRET-openalex", institution={"proxy": "proxy.example.edu"})
        self.config.chmod(0o600)
        bin_ = poppler_stubs(self.tmp / "bin")
        self.env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(self.tmp), "PAPER_TO_ZOTERO_DOWNLOADS": ""}

    def run_(self, *argv, env=None):
        return call(ready, "--work", self.work.root, "--base-url", self.zot.base_url, *argv, config=self.config,
                    env={**self.env, **(env or {})})

    def test_ready_and_the_work_directory(self):
        r = self.run_("--downloads", self.dl)
        self.assertEqual(r.code, 0, r)
        out = r.lines[0]
        self.assertEqual((out["code"], out["key"], out["downloads_dir"], out["resumed"]),
                         ("ok", {"present": True, "server_match": True}, str(self.dl), False))
        self.assertEqual(out["config"]["institution"], {"proxy": True, "discovery": False})
        self.assertIn("ask_user", out["config"])
        self.assertNotIn("sk-SECRET", r.out, "presence only, never a value")
        self.assertEqual([c["path"] for c in out["collections"]], ["自然图像", "自然图像/Diffusion"], "trashed ones left out")
        self.assertEqual(self.work.settings(), {"downloads": str(self.dl), "session": "p2z"})
        # A resumed run: the marker stays, the leftovers are listed, an older version's records named.
        os.utime(self.work.started, (time.time() - 600,) * 2)
        started = self.work.started.stat().st_mtime
        (self.work.records / "old.json").write_text(json.dumps({"item": {"title": "x"}, "found": {"code": "found", "key": "K"}}))
        (self.work.records / "old.pdf").write_bytes(b"%PDF-")
        out = self.run_("--downloads", self.dl).lines[0]
        self.assertEqual((out["resumed"], self.work.started.stat().st_mtime), (True, started))
        self.assertEqual([x["path"] for x in out["leftovers"]], ["records/old.json", "records/old.pdf"])
        self.assertEqual(out["old_format"], [{"slug": "old", "blocks": ["found"]}])
        self.assertEqual(self.run_(env={"PAPER_TO_ZOTERO_DOWNLOADS": str(self.tmp / "nowhere")}).lines[0]["downloads_dir"], None)
        self.config.chmod(0o644)
        self.assertIn("warning", self.run_().lines[0]["config"])

    def test_the_key_and_its_dialog(self):
        self.config.write_text(json.dumps({"openalex_key": "x"}))
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_key"))
        self.zot.authorize_replies = [(429, {"Retry-After": "1"}, {}), (200, {}, {"key": API_KEY, "remember": True})]
        r = self.run_("--authorize")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["key"]["present"]), (0, "ok", True), r)
        saved = json.loads(self.config.read_text())
        self.assertEqual((saved["zotero"]["serverID"], saved["openalex_key"]), (SERVER_ID, "x"), "the rest of the config kept")
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.config.write_text(json.dumps({"zotero": {"key": API_KEY, "serverID": "ANOTHER1"}}))
        self.assertEqual(self.run_().lines[0]["code"], "server_mismatch")
        for replies, code in (([(403, {}, {"denied": True})], "authorize_denied"),
                              ([(200, {}, {"key": "single", "remember": False})], "authorize_single_use"),
                              ([("sleep", 3)], "authorize_timeout")):
            self.zot.authorize_replies = replies
            r = self.run_("--authorize", "--timeout", "1")
            self.assertEqual((r.code, r.lines[0]["code"]), (1, code))
        self.assertEqual(json.loads(self.config.read_text())["zotero"]["serverID"], "ANOTHER1", "nothing saved")

    def test_cannot_check(self):
        r = self.run_(env={"PATH": "/nonexistent"})
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_pdftotext"))
        self.zot.disabled = True
        self.assertEqual(self.run_().lines[0]["code"], "local_api_disabled")
        self.zot.disabled = False
        self.config.write_text("{broken")
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "config_unreadable"))

    def test_smoke(self):
        r = smoke("ready", "--work", self.work.root, "--base-url", self.zot.base_url, "--downloads", self.dl,
                  config=self.config, env=self.env)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
