# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/ready.py: the facts, the directory, what cannot be checked. opencli and poppler are stubs on
PATH, and the Downloads folder is a temporary one, given by flag or $PAPER_FETCH_DOWNLOADS (never detected)."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from helpers import call, config_file, load, poppler_stubs, smoke
from pflib import run

ready = load("ready")

# opencli --version and opencli doctor, as 2.x answers them; $OPENCLI_STUB_VERSION gives another version
OPENCLI_STUB = """#!/bin/sh
case "$1" in
  --version) echo "${OPENCLI_STUB_VERSION:-2.1.0}" ;;
  doctor) echo '{"data": {"cliVersion": "2.1.0", "extensionConnected": true, "issues": []}}' ;;
  *) exit 1 ;;
esac
"""


class Ready(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pf-ready-"))
        self.work, self.dl = run.Work(self.tmp / "pf"), self.tmp / "dl"
        self.dl.mkdir()
        self.config = config_file(self.tmp, openalex_key="sk-SECRET-openalex", institution={"proxy": "proxy.example.edu"})
        self.config.chmod(0o600)
        self.bin = poppler_stubs(self.tmp / "bin")
        (self.bin / "opencli").write_text(OPENCLI_STUB, encoding="utf-8")
        (self.bin / "opencli").chmod(0o755)
        self.env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.tmp), "PAPER_FETCH_DOWNLOADS": str(self.dl)}

    def run_(self, *argv, env=None):
        return call(ready, "--dir", self.work.root, *argv, config=self.config, env={**self.env, **(env or {})})

    def test_ready_and_the_directory(self):
        r = self.run_()
        self.assertEqual(r.code, 0, r)
        out = r.lines[0]
        self.assertEqual((out["code"], out["downloads_dir"], out["resumed"], out["leftovers"]),
                         ("ok", str(self.dl), False, []), "a fresh directory has no leftovers")
        self.assertEqual((out["dir"], out["results_dir"], out["session"]), (str(self.work.root), str(self.work.results), "pf"))
        for name in ("results", "links", "inbox", "stray", "unverified", "scratch"):
            self.assertTrue(getattr(self.work, name).is_dir(), name)
        self.assertEqual(out["config"]["institution"], {"proxy": True, "discovery": False})
        self.assertTrue(out["config"]["openalex_key"])
        self.assertIn("ask_user", out["config"])
        self.assertNotIn("sk-SECRET", r.out, "presence only, never a value")
        self.assertEqual(out["poppler"], {"pdftotext": str(self.bin / "pdftotext"), "pdfinfo": str(self.bin / "pdfinfo")})
        self.assertEqual(out["opencli"], {"path": str(self.bin / "opencli"), "version": "2.1.0", "connected": True, "issues": []})
        self.assertEqual(self.work.settings(), {"downloads": str(self.dl), "session": "pf"})
        # A resumed run: the marker stays, the leftovers are listed and none is deleted.
        os.utime(self.work.started, (time.time() - 600,) * 2)
        started = self.work.started.stat().st_mtime
        (self.work.results / "old.json").write_text("{}")
        (self.work.unverified / "old.fetch.pdf").write_bytes(b"%PDF-")
        self.work.append({"event": "try", "slug": "old"})
        out = self.run_().lines[0]
        self.assertEqual((out["resumed"], self.work.started.stat().st_mtime), (True, started))
        self.assertEqual([x["path"] for x in out["leftovers"]], ["fetch.jsonl", "results/old.json", "unverified/old.fetch.pdf"])
        self.assertEqual(out["leftovers"][2]["bytes"], 5)
        self.assertTrue((self.work.unverified / "old.fetch.pdf").is_file())
        # Downloads: the flag over the variable; a folder that does not exist gives null.
        nowhere = {"PAPER_FETCH_DOWNLOADS": str(self.tmp / "nowhere")}
        self.assertEqual(self.run_(env=nowhere).lines[0]["downloads_dir"], None)
        self.assertEqual(self.run_("--downloads", self.dl, env=nowhere).lines[0]["downloads_dir"], str(self.dl))
        self.config.chmod(0o644)
        self.assertIn("warning", self.run_().lines[0]["config"])

    def test_opencli(self):
        out = self.run_(env={"OPENCLI_STUB_VERSION": "1.7.3"}).lines[0]["opencli"]
        self.assertEqual(out["version"], "1.7.3")
        self.assertIn("needs 2.x", out["issues"][0])
        bare = poppler_stubs(self.tmp / "bare")
        r = self.run_(env={"PATH": f"{bare}:/usr/bin:/bin"})
        self.assertEqual((r.code, r.lines[0]["opencli"]), (0, {"path": None}), "a missing opencli is a fact, not a stop")

    def test_cannot_check(self):
        r = self.run_(env={"PATH": "/nonexistent"})
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_pdftotext"))
        self.assertTrue(self.work.started.exists(), "the directory is made all the same")
        (self.tmp / "afile").write_text("")
        r = call(ready, "--dir", self.tmp / "afile" / "pf", config=self.config, env=self.env)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "dir_unwritable"))
        self.config.write_text("{broken")
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "config_unreadable"))

    def test_help(self):
        r = call(ready, "--help")
        self.assertEqual(r.code, 0)
        self.assertIn(ready.__doc__.strip().splitlines()[0], r.out)

    def test_smoke(self):
        r = smoke("ready", "--dir", self.work.root, "--downloads", self.dl, config=self.config, env=self.env)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)


if __name__ == "__main__":
    unittest.main()
