# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for the fold of fetch.jsonl into the result files (pflib/run.py settle, scripts/settle.py), the label event,
and filing a file without consuming one that is not this run's."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, fake_pdf, load, poppler_stubs, result_file, smoke
from pflib import cli, run

settle = load("settle")
TITLE = "Deep learning for ultrasound super-resolution"


class Fold(unittest.TestCase):
    def setUp(self):
        self.work = run.Work(tempfile.mkdtemp(prefix="pf-settle-"))
        self.path = result_file(self.work.root, "doe2024deep")
        self.bin = poppler_stubs(self.work.root / "bin")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}"}))

    def result(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_nothing_yet(self):
        self.work.append({"event": "try", "pass": 1, "slug": "doe2024deep", "route": "open",
                          "url": "https://www.ncbi.nlm.nih.gov/pmc/x.pdf", "result": "no_pdf"})
        r = call(settle, self.path)
        self.assertEqual((r.code, r.lines[0]["status"], r.lines[0]["files"]), (0, "not_got", []), r)
        res = self.result()
        self.assertEqual(res["outcome"], {"status": "not_got", "tried": ["www.ncbi.nlm.nih.gov"], "stop": None})
        self.assertIn("settled_at", res)
        self.assertEqual(res["csl"]["title"], TITLE, "identify's fields stay as they were")

    def test_a_gate_in_front_of_the_user_is_waiting(self):
        self.work.append({"event": "stop", "pass": 1, "slug": "doe2024deep", "route": "publisher", "why": "gate",
                          "gate": True, "url": "https://doi.org/10.1016/j.media.2024.103100"})
        self.assertEqual(call(settle, self.path).lines[0]["status"], "waiting")
        self.work.append({"event": "try", "pass": 1, "slug": "doe2024deep", "route": "publisher",
                          "result": "gate_timeout", "by": "agent"})
        self.assertEqual(call(settle, self.path).lines[0]["status"], "not_got", "a try after the stop: not waiting")

    def test_the_file_its_check_and_label(self):
        paper = fake_pdf(self.work.root / "dl.pdf", [f"{TITLE}\nJane Doe"])
        event = run.claim(self.work, paper, "doe2024deep", source="https://www.sciencedirect.com/x.pdf",
                          came={"route": "publisher", "url": "https://www.sciencedirect.com/x.pdf"})
        self.assertEqual((event["result"], event["code"]), ("claimed", "ok"))
        res, = [r for r, _ in run.settle(self.work)]
        [f] = res["files"]
        self.assertEqual((f["name"], f["kind"], f["check"], f["label"]["title"], f["url"]),
                         ("doe2024deep.pdf", "published", "ok", "Unknown-Elsevier", "https://www.sciencedirect.com/x.pdf"))
        self.assertEqual(f["md5"], run.md5_of(self.work.results / "doe2024deep.pdf"))
        self.assertEqual(res["outcome"]["status"], "got")

        run.label(self.work, "doe2024deep", "Published-Elsevier", "the page: Volume 92, May 2024")
        res, = [r for r, _ in run.settle(self.work)]
        self.assertEqual({k: res["files"][0]["label"][k] for k in ("title", "version", "source", "by", "why")},
                         {"title": "Published-Elsevier", "version": "published", "source": "Elsevier", "by": "agent",
                          "why": "the page: Volume 92, May 2024"})
        with self.assertRaises(cli.Stop) as stop:
            run.label(self.work, "doe2024deep", "Final version", "x")
        self.assertEqual(stop.exception.code, "bad_label")

    def test_a_file_the_agent_accepted(self):
        f = fake_pdf(self.work.root / "scan.pdf", ["A scanned page with no title on it"])
        run.accept(self.work, f, "doe2024deep", "page 1 is the paper; its text layer lacks the title")
        res, = [r for r, _ in run.settle(self.work)]
        self.assertEqual((res["files"][0]["check"], res["files"][0]["accepted_reason"], res["outcome"]["status"]),
                         ("accepted", "page 1 is the paper; its text layer lacks the title", "got"))

    def test_a_supplement_alone_is_not_got(self):
        supp = fake_pdf(self.work.root / "s.pdf", [f"Supplementary Material\n{TITLE}"])
        run.accept(self.work, supp, "doe2024deep", "supplement", kind="supplement")
        res, = [r for r, _ in run.settle(self.work)]
        self.assertEqual(res["outcome"]["status"], "not_got")

    def test_a_stub_files_what_it_is_given_as_cannot_judge(self):
        stub = result_file(self.work.root, "page2024", csl=None, warnings=["no_citation_meta"])
        f = fake_pdf(self.work.root / "p.pdf", ["Some paper\nwithout a DOI"])
        event = run.claim(self.work, f, "page2024")
        self.assertEqual((event["result"], event["code"]), ("claimed", "cannot_judge"))
        res, = [r for r, _ in run.settle(self.work, [run.read(stub)])]
        self.assertEqual((res["files"][0]["check"], res["outcome"]["status"]), ("cannot_judge", "got"))

    def test_a_file_from_elsewhere_is_copied_not_consumed(self):
        outside = Path(tempfile.mkdtemp(prefix="pf-zotero-storage-"))
        kept = fake_pdf(outside / "Doe - 2024 - Deep.pdf", [f"{TITLE}\nJane Doe"])
        self.assertFalse(self.work.owns(kept))
        run.claim(self.work, kept, "doe2024deep", consume=self.work.owns(kept))
        self.assertTrue(kept.is_file(), "the library's own file stays")
        self.assertTrue((self.work.results / "doe2024deep.pdf").is_file())
        own = fake_pdf(self.work.inbox / "x.pdf", [f"{TITLE}\nJane Doe"]) if self.work.inbox.mkdir() is None else None
        self.assertTrue(self.work.owns(own))

    def test_settle_every_result_in_a_directory(self):
        result_file(self.work.root, "roe2023other", csl={"title": "Other", "DOI": "10.1/x"})
        r = call(settle, "--dir", self.work.root)
        self.assertEqual([x["slug"] for x in r.lines[:-1]], ["doe2024deep", "roe2023other"])
        r = call(settle, self.work.root / "results" / "nope.json")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "result_invalid"))

    def test_smoke(self):
        r = smoke("settle", self.path)
        self.assertEqual((r.code, r.lines[0]["status"]), (0, "not_got"), r)


if __name__ == "__main__":
    unittest.main()
