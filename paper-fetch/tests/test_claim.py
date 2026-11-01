# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/claim.py: a file got for a result (filed, held for the agent, refused), a stub's, a file from
elsewhere, the Downloads scan and the sweep (pdftotext and pdfinfo are stubs that print a file's sidecars)."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, fake_pdf, load, poppler_stubs, result_file, smoke
from pflib import run

claim = load("claim")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
OTHER = "A Completely Different Paper About Lung Nodules"


class Claim(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp(prefix="pf-claim-"))
        self.work = run.Work(root / "fetch")
        self.work.results.mkdir(parents=True)
        self.work.started.touch()
        os.utime(self.work.started, (time.time() - 600,) * 2)
        self.dl = root / "Downloads"
        self.dl.mkdir()
        self.work.set(downloads=str(self.dl))
        bin_ = poppler_stubs(root / "bin")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_}:{os.environ['PATH']}"}))
        self.result("paper", TITLE)
        self.result("other", OTHER)

    def result(self, slug, title):
        return result_file(self.work.root, slug, csl={"title": title, "author": [{"family": "Liu"}]})

    def read(self, slug):
        return json.loads((self.work.results / f"{slug}.json").read_text(encoding="utf-8"))

    def tried(self, slug):
        self.work.append({"event": "try", "pass": 1, "slug": slug, "route": "open", "result": "no_pdf"})

    def run_(self, *argv, **kwargs):
        return call(claim, "--dir", self.work.root, *argv, **kwargs)

    def test_a_file_got_for_a_result(self):
        self.work.inbox.mkdir()
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"], data=b"%PDF-1.5\n% the paper\n")
        r = self.run_("--file", good, "--slug", "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"], r.lines[0]["code"]), (0, "claimed", "paper.pdf", "ok"))
        self.assertFalse(good.exists(), "a file in the directory is consumed")
        self.assertEqual([(f["name"], f["check"]) for f in self.read("paper")["files"]], [("paper.pdf", "ok")],
                         "--file folds the result when it ends")
        # Not certain: held for the paper's agent, with a file handoff holding the evidence to read.
        unsure = fake_pdf(self.work.inbox / "b.pdf", ["Erratum\nA notice"])
        r = self.run_("--file", unsure, "--slug", "other", "--version", "accepted")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"]), (1, "held", "other.file.pdf"))
        record = json.loads((self.work.handoffs / f"{r.lines[0]['handoff']}.json").read_text())
        self.assertEqual((record["kind"], record["taker"], record["slug"], record["paper"]["title"]),
                         ("file", "paper_agent", "other", OTHER))
        self.assertTrue(any(f.endswith("excerpt.txt") for f in record["evidence"]["files"]), "evidence to read, not to paste")
        self.assertEqual(self.read("other")["outcome"], {"status": "waiting", "waiting_on": ["file"], "tried": [],
                                                         "last": {"event": "handoff", "route": None, "result": "file", "url": None}})
        # Certainly not the paper: refused, nothing handed over.
        notpdf = self.work.inbox / "c.pdf"
        notpdf.write_text("<html>a login page</html>")
        self.assertEqual(self.run_("--file", notpdf, "--slug", "other").lines[0]["result"], "refused")
        # The same content again is the file already beside the result; another file of one kind is numbered.
        again = fake_pdf(self.work.inbox / "d.pdf", [f"{TITLE}\nWei Liu"], data=b"%PDF-1.5\n% the paper\n")
        self.assertEqual(self.run_("--file", again, "--slug", "paper").lines[0]["file"], "paper.pdf")
        second = fake_pdf(self.work.inbox / "e.pdf", [f"{TITLE}\nWei Liu, a second copy"])
        self.assertEqual(self.run_("--file", second, "--slug", "paper").lines[0]["file"], "paper.2.pdf")
        self.assertEqual([e["result"] for e in self.work.events("claim")], ["claimed", "held", "refused", "claimed", "claimed"])
        self.assertEqual([e["proposal"]["title"] for e in self.work.events("claim")][:2], ["Unknown", "Accepted"],
                         "a file the agent hands over is what it names, else not settled")
        self.assertEqual(self.run_("--file", again, "--scan").code, 2, "--file goes alone")
        self.assertEqual(self.run_("--file", again).code, 2, "--file names its result")

    def test_a_stubs_file_is_filed_unjudged(self):
        stub = {"slug": "stub", "request": {"given": "10.9999/html"}, "warnings": ["no_csl_record"]}
        (self.work.results / "stub.json").write_text(json.dumps(stub), encoding="utf-8")
        self.work.inbox.mkdir()
        f = fake_pdf(self.work.inbox / "s.pdf", ["A paper with no record to check against"])
        r = self.run_("--file", f, "--slug", "stub")
        self.assertEqual((r.lines[0]["result"], r.lines[0]["code"]), ("claimed", "cannot_judge"))
        self.assertEqual([x["check"] for x in self.read("stub")["files"]], ["cannot_judge"])

    def test_a_held_file_accepted_keeps_how_it_came(self):
        self.work.inbox.mkdir()
        scan = fake_pdf(self.work.inbox / "s.pdf", ["A scanned first page the check cannot read"])
        came = {"route": "publisher", "url": "https://ieeexplore.ieee.org/stamp/x.pdf", "page": {"title": "Xplore"}}
        self.assertEqual(run.claim(self.work, scan, "paper", came=came)["result"], "held")
        event = run.accept(self.work, self.work.unverified / "paper.file.pdf", "paper", "the title page is a scan")
        self.assertEqual((event["route"], event["proposal"]["title"], event["evidence"]["page"]),
                         ("publisher", "Published-IEEE", {"title": "Xplore"}))

    def test_a_file_from_elsewhere_is_copied_and_left_in_place(self):
        # A PDF in Zotero's storage, handed over to be checked and labelled: the library keeps its own file.
        storage = Path(tempfile.mkdtemp(prefix="pf-zotero-storage-"))
        kept = fake_pdf(storage / "Liu - 2022 - Progressive.pdf", [f"{TITLE}\nWei Liu"])
        r = self.run_("--file", kept, "--slug", "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["source"]), (0, "claimed", str(kept)))
        self.assertTrue(kept.is_file(), "not this run's: copied, never consumed")
        self.assertEqual(run.md5_of(self.work.results / "paper.pdf"), run.md5_of(kept))
        scan = fake_pdf(storage / "scan.pdf", ["A scanned first page"])
        self.assertEqual((self.run_("--file", scan, "--slug", "other").lines[0]["result"], scan.is_file()), ("held", True))
        # One of this run's downloads is the run's own: consumed.
        dl = fake_pdf(self.dl / "third.pdf", ["Something the user reads"])
        self.result("third", "Something the user reads")
        self.assertEqual(self.run_("--file", dl, "--slug", "third").lines[0]["result"], "claimed")
        self.assertFalse(dl.exists())

    def test_downloads_scan_and_sweep(self):
        # Results a download may be for: those a route was tried for. `held` is the same paper, but nothing was tried
        # for it (its file came another way, or it is not being fetched): no download is checked against it.
        self.result("held", TITLE)
        self.tried("paper")
        self.tried("other")
        mine = fake_pdf(self.dl / "download.pdf", [f"{TITLE}\nWei Liu"])
        users = fake_pdf(self.dl / "users-own.pdf", ["Something the user reads"])
        old = fake_pdf(self.dl / "old.pdf", [f"{OTHER}\nWei Liu"])
        os.utime(old, (time.time() - 3600,) * 2)
        before = self.read("paper")
        r = self.run_("--scan")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(e["file"], e["result"]) for e in r.lines], [("paper.pdf", "claimed"), ("users-own.pdf", "left")])
        self.assertEqual(r.lines[1]["against"], ["other"], "paper has its file by then; held was never tried")
        self.assertEqual(json.loads((self.work.handoffs / f"{r.lines[1]['handoff']}.json").read_text())["kind"], "left",
                         "a download nobody claimed goes to an agent")
        self.assertEqual((mine.exists(), users.exists(), old.exists()), (False, True, True), "older than .started: not this run's")
        self.assertEqual(self.read("paper"), before, "the scan only appends events: settle.py folds")
        self.assertEqual(self.run_("--scan").lines, [], "a left file is not checked again against the same results")
        self.result("third", "Something the user reads")
        self.tried("third")
        self.assertEqual([(e["slug"], e["result"]) for e in self.run_("--scan").lines], [("third", "claimed")])
        # The sweep: what this run left in Downloads, with md5 and size; the library is paper-to-zotero's to ask.
        left = fake_pdf(self.dl / "left.pdf", ["Unrelated"])
        r = self.run_("--sweep")
        self.assertEqual([(e["file"], e["source"], e["md5"], e["size"], e["why"]) for e in r.lines[:-1] if e["file"].endswith(".pdf")],
                         [("left.pdf", str(left), run.md5_of(left), left.stat().st_size, "sweep")])
        self.assertEqual(r.lines[-1]["summary"]["left"], len(r.lines) - 1, "a summary, also when nothing is left")
        self.assertTrue(left.exists())

    def test_cannot_go_on(self):
        self.work.set(downloads=None)
        self.assertEqual(self.run_("--scan").lines[0]["code"], "no_downloads")
        self.work.started.unlink()
        r = self.run_("--scan", "--downloads", self.dl)
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_started"))
        r = call(claim, "--dir", self.work.root / "nowhere", "--scan")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_work_dir"))
        self.assertEqual(self.run_().code, 2, "a mode is required")

    def test_help_is_the_docstring(self):
        r = call(claim, "--help")
        self.assertEqual(r.code, 0)
        self.assertIn(claim.__doc__.strip().splitlines()[0], r.out)
        self.assertIn("find_in_library --file", r.out)

    def test_smoke(self):
        self.assertEqual(smoke("claim", "--dir", self.work.root, "--scan").code, 0)


if __name__ == "__main__":
    unittest.main()
