# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/index_heading.py, against tests/fake_p2z.py: a project paper index's heading line from Zotero."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "index_heading.py"

ITEMS = {
    "xiaoTCACE2026": {"title": "T-CACE: A Time-Conditioned Autoregressive Contrast Enhancement Framework",
                      "date": "2026-03", "tags": [{"tag": "venue/JBHI"}, {"tag": "modality/MRI"}]},
    "rombachHighResolutionImageSynthesis2022": {
        "title": "High-Resolution Image Synthesis with Latent Diffusion Models", "date": "6/2022",
        "tags": [{"tag": "aka/Stable Diffusion"}, {"tag": "venue/CVPR"}, {"tag": "aka/LDM"}]},
    "someNotePreprint": {"title": "A Note", "date": "", "tags": []},
}

EXPECTED = [  # by hand
    {"cite": "rombachHighResolutionImageSynthesis2022", "code": "ok",
     "heading": "## rombachHighResolutionImageSynthesis2022 · High-Resolution Image Synthesis with Latent Diffusion "
                "Models · LDM / Stable Diffusion（CVPR 2022）"},
    {"cite": "xiaoTCACE2026", "code": "ok",
     "heading": "## xiaoTCACE2026 · T-CACE: A Time-Conditioned Autoregressive Contrast Enhancement Framework（JBHI 2026）"},
    {"cite": "someNotePreprint", "code": "ok", "heading": "## someNotePreprint · A Note"},
    {"cite": "notInTheLibrary2020", "code": "cite_not_found"},
]


class IndexHeading(unittest.TestCase):
    def test_headings(self):
        scratch = Path(tempfile.mkdtemp(prefix="paper-read-"))
        lib = scratch / "library.json"
        lib.write_text(json.dumps({"items": ITEMS, "notes": {}, "pdfs": {}, "packages": {}}), encoding="utf-8")
        env = {**os.environ, "PAPER_READ_P2Z": str(HERE / "fake_p2z.py"), "FAKE_P2Z": str(lib)}
        done = subprocess.run([shutil.which("uv"), "run", "--quiet", "--script", str(SCRIPT), "--cite",
                               *[e["cite"] for e in EXPECTED]], capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual([json.loads(l) for l in done.stdout.splitlines()], EXPECTED)
        shutil.rmtree(scratch)


if __name__ == "__main__":
    unittest.main()
