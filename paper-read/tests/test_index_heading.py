# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pr.py heading (scripts/index_heading.py), against tests/fake_p2z.py: a project paper index's heading line
from Zotero."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "index_heading.py"

ITEMS = {
    "xiaoTCACE2026": {"key": "TCACE001", "title": "T-CACE: A Time-Conditioned Autoregressive Contrast Enhancement Framework",
                      "date": "2026-03", "tags": [{"tag": "venue/JBHI"}, {"tag": "modality/MRI"}]},
    "rombachHighResolutionImageSynthesis2022": {
        "key": "LDM00001", "title": "High-Resolution Image Synthesis with Latent Diffusion Models", "date": "6/2022",
        "tags": [{"tag": "aka/Stable Diffusion"}, {"tag": "venue/CVPR"}, {"tag": "aka/LDM"}]},
    "someNotePreprint": {"key": "NOTEPRE1", "title": "A Note", "date": "", "tags": []},
}

LDM = {"cite": "rombachHighResolutionImageSynthesis2022", "code": "ok",   # by hand
       "heading": "## rombachHighResolutionImageSynthesis2022 · High-Resolution Image Synthesis with Latent Diffusion "
                  "Models · LDM / Stable Diffusion（CVPR 2022）"}
TCACE = {"cite": "xiaoTCACE2026", "code": "ok",
         "heading": "## xiaoTCACE2026 · T-CACE: A Time-Conditioned Autoregressive Contrast Enhancement Framework（JBHI 2026）"}
NOTE = {"cite": "someNotePreprint", "code": "ok", "heading": "## someNotePreprint · A Note"}
MISSING = {"item": "notInTheLibrary2020", "code": "not_found", "hint": "No item has this key or citation key."}


class IndexHeading(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="paper-read-"))
        self.lib = self.dir / "library.json"
        self.lib.write_text(json.dumps({"items": ITEMS, "notes": {}, "pdfs": {}, "packages": {}}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_it(self, *papers, stdin=None, env=None):
        env = {**os.environ, "PAPER_READ_P2Z": str(HERE / "fake_p2z.py"), "FAKE_P2Z": str(self.lib), **(env or {})}
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), *papers], input=stdin,
                              capture_output=True, text=True, timeout=120, env=env)
        return done.returncode, [json.loads(l) for l in done.stdout.splitlines()], done.stderr

    def test_headings(self):
        # a citation key or an item key, each paper once; one that is not in the library is paper-to-zotero's line
        code, lines, err = self.run_it("rombachHighResolutionImageSynthesis2022", "TCACE001", "someNotePreprint",
                                       "notInTheLibrary2020", "xiaoTCACE2026")
        self.assertEqual((code, lines), (1, [LDM, TCACE, NOTE, MISSING]))
        self.assertEqual(json.loads(err.splitlines()[-1]), {"summary": {"total": 4, "failed": 1}})
        code, lines, err = self.run_it("someNotePreprint")
        self.assertEqual((code, lines, err), (0, [NOTE], ""))

    def test_a_list(self):
        # what p2z.py search prints, by key; a failure upstream passed on as it is
        listed = [json.dumps({"key": "LDM00001", "title": "High-Resolution Image Synthesis"}),
                  json.dumps(MISSING), "xiaoTCACE2026"]
        code, lines, err = self.run_it("-", stdin="\n".join(listed) + "\n")
        self.assertEqual((code, lines), (1, [LDM, MISSING, TCACE]))
        self.assertEqual(json.loads(err.splitlines()[-1]), {"summary": {"total": 3, "failed": 1}})
        self.assertEqual(self.run_it("-", stdin=""), (0, [], ""))   # nothing to do
        code, lines, err = self.run_it("-", stdin='{"title": "no key"}\n')   # a list it cannot read
        self.assertEqual((code, lines, json.loads(err.splitlines()[-1])["code"]), (2, [], "invalid_list"))
        code, lines, err = self.run_it()   # nothing named: a usage error, never the whole library
        self.assertEqual((code, json.loads(err.splitlines()[-1])["code"]), (2, "usage"))

    def test_zotero_not_running(self):
        with socket.socket() as s:   # a port just closed, the real paper-to-zotero
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code, lines, err = self.run_it("xiaoTCACE2026", "TCACE001", env={
            "PAPER_READ_P2Z": "", "PAPER_TO_ZOTERO_BASE_URL": f"http://127.0.0.1:{port}",
            "PAPER_TO_ZOTERO_CONFIG": str(self.dir / "no-config.json"), "no_proxy": "127.0.0.1,localhost",
            "NO_PROXY": "127.0.0.1,localhost"})
        self.assertEqual((code, lines), (2, [{"item": "xiaoTCACE2026", "code": "not_run"},
                                             {"item": "TCACE001", "code": "not_run"}]))
        self.assertEqual(json.loads(err.splitlines()[-1])["code"], "zotero_unreachable")


if __name__ == "__main__":
    unittest.main()
