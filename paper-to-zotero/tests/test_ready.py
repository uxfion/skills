# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/ready.py against the fake Zotero: the facts, an import's directory, the key and its dialog."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
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
        self.work = run.Work(self.tmp / "paper-to-zotero")
        self.config = config_file(self.tmp, openalex_key="sk-SECRET-openalex", institution={"proxy": "proxy.example.edu"})
        self.config.chmod(0o600)

    def run_(self, *argv):
        return call(ready, "--base-url", self.zot.base_url, *argv, config=self.config, env={"HOME": str(self.tmp)})

    def test_ready_and_an_imports_directory(self):
        r = self.run_()
        self.assertEqual(r.code, 0, r)
        out = r.lines[0]
        self.assertEqual((out["code"], out["key"]), ("ok", {"present": True, "server_match": True}))
        self.assertEqual(out["config"]["moved"], ["openalex_key", "institution"], "paper-fetch's now")
        self.assertNotIn("sk-SECRET", r.out, "presence only, never a value")
        self.assertEqual([c["path"] for c in out["collections"]], ["自然图像", "自然图像/Diffusion"], "trashed ones left out")
        self.assertFalse(self.work.root.exists(), "no directory without --dir: organizing needs none")
        out = self.run_("--dir", self.work.root).lines[0]
        self.assertEqual((out["dir"], out["leftovers"]), (str(self.work.root), []))
        self.assertTrue(self.work.records.is_dir() and self.work.scratch.is_dir())
        (self.work.records / "old.json").write_text(json.dumps({"item": {"title": "x"}, "found": {"code": "found", "key": "K"}}))
        (self.work.root / "fetch").mkdir()
        out = self.run_("--dir", self.work.root).lines[0]
        self.assertEqual([x["path"] for x in out["leftovers"]], ["fetch", "records/old.json"])
        self.assertEqual(out["old_format"], [{"slug": "old", "blocks": ["found"]}])
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
        self.zot.disabled = True
        self.assertEqual(self.run_().lines[0]["code"], "local_api_disabled")
        self.zot.disabled = False
        self.config.write_text("{broken")
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "config_unreadable"))

    def test_smoke(self):
        r = smoke("ready", "--dir", self.work.root, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
