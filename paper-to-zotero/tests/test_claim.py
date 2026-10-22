# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/claim.py: a file got for a record, an accepted one, the Downloads scan and the sweep (pdftotext and
pdfinfo are stubs that print a file's sidecars)."""
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, config_file, fake_pdf, load, poppler_stubs, smoke
from fake_zotero import FakeZotero

from p2zlib import run

claim = load("claim")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
OTHER = "A Completely Different Paper About Lung Nodules"


class Claim(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp(prefix="p2z-claim-"))
        self.work = run.Work(root / "work")
        self.work.records.mkdir(parents=True)
        self.work.started.touch()
        os.utime(self.work.started, (time.time() - 600,) * 2)
        self.dl = root / "Downloads"
        self.dl.mkdir()
        self.work.set(downloads=str(self.dl))
        bin_ = poppler_stubs(root / "bin")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_}:{os.environ['PATH']}",
                                                       "PAPER_TO_ZOTERO_CONFIG": str(config_file())}))
        self.record("paper", TITLE)
        self.record("other", OTHER)

    def record(self, slug, title, **extra):
        (self.work.records / f"{slug}.json").write_text(json.dumps({"item": {"title": title, "creators": [{"lastName": "Liu"}]}, **extra}))

    def run_(self, *argv, **kwargs):
        return call(claim, "--work", self.work.root, *argv, **kwargs)

    def test_a_file_got_for_a_record(self):
        self.work.inbox.mkdir()
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"])
        r = self.run_("--file", good, "--slug", "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"], r.lines[0]["code"]), (0, "claimed", "paper.pdf", "ok"))
        self.assertFalse(good.exists())
        bad = fake_pdf(self.work.inbox / "b.pdf", ["Erratum\nA notice"])
        r = self.run_("--file", bad, "--slug", "other", "--version", "accepted")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"]), (1, "unverified", "other.file.pdf"))
        # The agent reads it and accepts it: filed unchecked under the kind given, md5 and reason logged.
        r = self.run_("--accept", self.work.unverified / "other.file.pdf", "--slug", "other", "--reason", "a scan", "--version", "accepted")
        self.assertEqual((r.code, r.lines[0]["event"], r.lines[0]["file"]), (0, "accept", "other.accepted.pdf"))
        self.assertEqual(run.accepted(self.work, "other", r.lines[0]["md5"])["reason"], "a scan")
        again = fake_pdf(self.work.inbox / "c.pdf", [f"{TITLE}\nWei Liu"])
        self.assertEqual(self.run_("--file", again, "--slug", "paper").lines[0]["result"], "stray", "first come, first served")
        self.assertEqual([e["result"] for e in self.work.events()], ["claimed", "unverified", "claimed", "stray"])
        self.assertEqual([e["proposal"]["title"] for e in self.work.events()], ["Unknown", "Accepted", "Accepted", "Unknown"],
                         "a file the agent hands over is what it names, else not settled")
        self.assertEqual(self.run_("--accept", again, "--slug", "paper").code, 2, "--accept needs --reason")

    def test_an_accepted_file_keeps_how_it_came(self):
        self.work.inbox.mkdir()
        scan = fake_pdf(self.work.inbox / "s.pdf", ["A scanned first page the check cannot read"])
        came = {"route": "publisher", "url": "https://ieeexplore.ieee.org/stamp/x.pdf", "page": {"title": "Xplore"}}
        self.assertEqual(run.claim(self.work, scan, "paper", came=came)["result"], "unverified")
        event = run.accept(self.work, self.work.unverified / "paper.file.pdf", "paper", "the title page is a scan")
        self.assertEqual((event["route"], event["proposal"]["title"], event["evidence"]["page"]),
                         ("publisher", "Published-IEEE", {"title": "Xplore"}))

    def test_downloads_scan_and_sweep(self):
        # Another record of the same paper whose library item has a PDF already, its version unknown (a title outside
        # the scheme): it is the paper's file all the same, so no download is checked against that record.
        held = run.Record(self.work.records / "held.json", {"item": {"title": TITLE, "creators": [{"lastName": "Liu"}]}})
        run.stamp(held, "found", {"code": "found", "key": "HELD0001", "attachments": [
            {"key": "OLDPDF01", "title": "Full Text PDF", "version": "unknown", "standard": False, "contentType": "application/pdf"}]})
        held.save()
        mine = fake_pdf(self.dl / "download.pdf", [f"{TITLE}\nWei Liu"])
        users = fake_pdf(self.dl / "users-own.pdf", ["Something the user reads"])
        old = fake_pdf(self.dl / "old.pdf", [f"{OTHER}\nWei Liu"])
        os.utime(old, (time.time() - 3600,) * 2)
        r = self.run_("--scan")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(e["file"], e["result"]) for e in r.lines], [("paper.pdf", "claimed"), ("users-own.pdf", "left")])
        self.assertEqual((mine.exists(), users.exists(), old.exists()), (False, True, True), "older than .started: not this run's")
        self.assertEqual(self.run_("--scan").lines, [], "a left file is not checked again against the same records")
        self.record("third", "Something the user reads")
        self.assertEqual([(e["slug"], e["result"]) for e in self.run_("--scan").lines], [("third", "claimed")])
        # The sweep: what is left, and whether the library has it.
        left = fake_pdf(self.dl / "left.pdf", ["Unrelated"])
        zot = FakeZotero()
        self.addCleanup(zot.close)
        zot.add_item("PARENT01", itemType="journalArticle", title="Unrelated", citationKey="roe2020")
        zot.add_item("ATTACH01", itemType="attachment", parentItem="PARENT01", contentType="application/pdf",
                     md5=hashlib.md5(left.read_bytes()).hexdigest())
        r = self.run_("--sweep", "--base-url", zot.base_url)
        self.assertEqual([(e["file"], e["in_library"], e.get("citationKey")) for e in r.lines if e["file"].endswith(".pdf")],
                         [("left.pdf", True, "roe2020")])

    def test_cannot_go_on(self):
        self.work.set(downloads=None)
        self.assertEqual(self.run_("--scan").lines[0]["code"], "no_downloads")
        self.work.started.unlink()
        r = self.run_("--scan", "--downloads", self.dl)
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_started"))
        r = call(claim, "--work", self.work.root / "nowhere", "--scan")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_work_dir"))

    def test_smoke(self):
        self.assertEqual(smoke("claim", "--work", self.work.root, "--scan").code, 0)


if __name__ == "__main__":
    unittest.main()
