# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/claim.py: a file got for a result, an accepted one, a file from elsewhere, a label, the Downloads
scan and the sweep (pdftotext and pdfinfo are stubs that print a file's sidecars)."""
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
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"])
        r = self.run_("--file", good, "--slug", "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"], r.lines[0]["code"]), (0, "claimed", "paper.pdf", "ok"))
        self.assertFalse(good.exists(), "a file in the directory is consumed")
        self.assertEqual([(f["name"], f["check"]) for f in self.read("paper")["files"]], [("paper.pdf", "ok")],
                         "--file folds the result when it ends")
        bad = fake_pdf(self.work.inbox / "b.pdf", ["Erratum\nA notice"])
        r = self.run_("--file", bad, "--slug", "other", "--version", "accepted")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"]), (1, "unverified", "other.file.pdf"))
        self.assertEqual(self.read("other")["outcome"]["status"], "not_got")
        # The agent reads it and accepts it: filed unchecked under the kind given, md5 and reason logged.
        r = self.run_("--accept", self.work.unverified / "other.file.pdf", "--slug", "other", "--reason", "a scan", "--version", "accepted")
        self.assertEqual((r.code, r.lines[0]["event"], r.lines[0]["file"]), (0, "accept", "other.accepted.pdf"))
        self.assertFalse((self.work.unverified / "other.file.pdf").exists())
        [f] = self.read("other")["files"]
        self.assertEqual((f["name"], f["md5"], f["check"], f["accepted_reason"]),
                         ("other.accepted.pdf", r.lines[0]["md5"], "accepted", "a scan"))
        again = fake_pdf(self.work.inbox / "c.pdf", [f"{TITLE}\nWei Liu"])
        self.assertEqual(self.run_("--file", again, "--slug", "paper").lines[0]["result"], "stray", "first come, first served")
        self.assertEqual([e["result"] for e in self.work.events()], ["claimed", "unverified", "claimed", "stray"])
        self.assertEqual([e["proposal"]["title"] for e in self.work.events()], ["Unknown", "Accepted", "Accepted", "Unknown"],
                         "a file the agent hands over is what it names, else not settled")
        self.assertEqual(self.run_("--accept", again, "--slug", "paper").code, 2, "--accept needs --reason")
        self.assertEqual(self.run_("--file", again, "--scan").code, 2, "--file goes alone, or with --label")

    def test_a_stubs_file_is_accepted_where_it_is(self):
        stub = {"slug": "stub", "request": {"given": "10.9999/html"}, "warnings": ["no_csl_record"]}
        (self.work.results / "stub.json").write_text(json.dumps(stub), encoding="utf-8")
        self.work.inbox.mkdir()
        f = fake_pdf(self.work.inbox / "s.pdf", ["A paper with no record to check against"])
        self.assertEqual(self.run_("--file", f, "--slug", "stub").lines[0]["code"], "cannot_judge")
        [entry] = self.read("stub")["files"]
        r = self.run_("--accept", self.work.results / entry["name"], "--slug", "stub", "--reason", "page 1 is the paper")
        self.assertEqual((r.code, r.lines[0]["file"], r.lines[0]["result"]), (0, entry["name"], "claimed"))
        self.assertEqual([(x["name"], x["check"]) for x in self.read("stub")["files"]], [(entry["name"], "accepted")],
                         "not sent to stray/ as a second file")
        self.assertFalse(self.work.stray.exists() and any(self.work.stray.iterdir()))

    def test_an_accepted_file_keeps_how_it_came(self):
        self.work.inbox.mkdir()
        scan = fake_pdf(self.work.inbox / "s.pdf", ["A scanned first page the check cannot read"])
        came = {"route": "publisher", "url": "https://ieeexplore.ieee.org/stamp/x.pdf", "page": {"title": "Xplore"}}
        self.assertEqual(run.claim(self.work, scan, "paper", came=came)["result"], "unverified")
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
        r = self.run_("--accept", scan, "--slug", "other", "--reason", "a scan")
        self.assertEqual((r.code, r.lines[0]["file"], scan.is_file()), (0, "other.pdf", True))
        # One of this run's downloads is the run's own: consumed.
        dl = fake_pdf(self.dl / "third.pdf", ["Something the user reads"])
        self.result("third", "Something the user reads")
        self.assertEqual(self.run_("--file", dl, "--slug", "third").lines[0]["result"], "claimed")
        self.assertFalse(dl.exists())

    def test_a_label(self):
        self.work.inbox.mkdir()
        self.run_("--file", fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"]), "--slug", "paper")
        r = self.run_("--label", "Published-IEEE", "--why", "the page: Volume 12, Issue 3", "--slug", "paper")
        self.assertEqual((r.code, {k: r.lines[0][k] for k in ("event", "slug", "file", "title", "why", "by")}),
                         (0, {"event": "label", "slug": "paper", "file": "paper.pdf", "title": "Published-IEEE",
                              "why": "the page: Volume 12, Issue 3", "by": "agent"}), r)
        [f] = self.read("paper")["files"]
        self.assertEqual((f["label"]["title"], f["label"]["version"], f["label"]["by"]), ("Published-IEEE", "published", "agent"),
                         "--label folds the result")
        # A supplement is labelled by naming it (its name or its path): the default is the paper's own file.
        supp = fake_pdf(self.work.inbox / "s.pdf", [f"Supplementary Material\n{OTHER}"])
        self.run_("--accept", supp, "--slug", "other", "--reason", "the supplement", "--version", "supplement")
        r = self.run_("--label", "Supplement-IEEE", "--why", "x", "--slug", "other")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_such_file"))
        r = self.run_("--label", "Supplement-IEEE", "--why", "its first page", "--slug", "other", "--by", "browser_agent",
                      "--file", self.work.results / "other.supplement.pdf")
        self.assertEqual((r.code, r.lines[0]["file"], r.lines[0]["by"]), (0, "other.supplement.pdf", "browser_agent"))
        self.assertEqual([(f["name"], f["label"]["title"], f["label"]["by"]) for f in self.read("other")["files"]],
                         [("other.supplement.pdf", "Supplement-IEEE", "browser_agent")])
        r = self.run_("--label", "Final version", "--why", "x", "--slug", "paper")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "bad_label"))
        self.assertEqual(self.run_("--label", "Published-IEEE", "--slug", "paper").code, 2, "--label needs --why")
        self.assertEqual(len(self.work.events("label")), 2)

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
        self.assertEqual((mine.exists(), users.exists(), old.exists()), (False, True, True), "older than .started: not this run's")
        self.assertEqual(self.read("paper"), before, "the scan only appends events: settle.py folds")
        self.assertEqual(self.run_("--scan").lines, [], "a left file is not checked again against the same results")
        self.result("third", "Something the user reads")
        self.tried("third")
        self.assertEqual([(e["slug"], e["result"]) for e in self.run_("--scan").lines], [("third", "claimed")])
        # The sweep: what this run left in Downloads, with md5 and size; the library is paper-to-zotero's to ask.
        left = fake_pdf(self.dl / "left.pdf", ["Unrelated"])
        r = self.run_("--sweep")
        self.assertEqual([(e["file"], e["source"], e["md5"], e["size"], e["why"]) for e in r.lines if e["file"].endswith(".pdf")],
                         [("left.pdf", str(left), run.md5_of(left), left.stat().st_size, "sweep")])
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
