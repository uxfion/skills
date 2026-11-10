# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/claim.py, pf.py claim, scan and downloads: a file got for a result (filed, held for the agent,
refused), a stub's, a file from elsewhere, the Downloads scan and what a run left there (pdftotext and pdfinfo are
stubs that print a file's sidecars)."""
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
        """pf.py claim FILE... <result>, the result named by its slug here."""
        *files, slug = argv
        return call(claim, "claim", *files, self.work.results / f"{slug}.json", **kwargs)

    def word(self, word, *argv):
        return call(claim, word, self.work.root, *argv)

    def test_a_file_got_for_a_result(self):
        self.work.inbox.mkdir()
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"], data=b"%PDF-1.5\n% the paper\n")
        r = self.run_(good, "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"], r.lines[0]["code"]), (0, "claimed", "paper.pdf", "ok"))
        self.assertFalse(good.exists(), "a file in the directory is consumed")
        self.assertEqual([(f["name"], f["check"]) for f in self.read("paper")["files"]], [("paper.pdf", "ok")],
                         "claim folds the result when it ends")
        # Not certain: held for the paper's agent, with a file handoff holding the evidence to read.
        unsure = fake_pdf(self.work.inbox / "b.pdf", ["Erratum\nA notice"])
        r = self.run_("--as", "accepted", unsure, "other")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["file"]), (1, "held", "other.file.pdf"))
        self.assertEqual(r.last["summary"], {"total": 1, "ok": 0, "skipped": 0, "failed": 1})
        record = json.loads((self.work.handoffs / f"{r.lines[0]['handoff']}.json").read_text())
        self.assertEqual((record["kind"], record["slug"], record["paper"]["title"]), ("file", "other", OTHER))
        self.assertTrue(any(f.endswith("excerpt.txt") for f in record["evidence"]["files"]), "evidence to read, not to paste")
        self.assertEqual(self.read("other")["outcome"], {"status": "waiting", "waiting_on": ["file"], "tried": [],
                                                         "last": {"event": "handoff", "route": None, "result": "file", "url": None}})
        # Certainly not the paper: refused, nothing handed over.
        notpdf = self.work.inbox / "c.pdf"
        notpdf.write_text("<html>a login page</html>")
        self.assertEqual(self.run_(notpdf, "other").lines[0]["result"], "refused")
        # The same content again is the file already beside the result; another file of one kind is numbered.
        again = fake_pdf(self.work.inbox / "d.pdf", [f"{TITLE}\nWei Liu"], data=b"%PDF-1.5\n% the paper\n")
        second = fake_pdf(self.work.inbox / "e.pdf", [f"{TITLE}\nWei Liu, a second copy"])
        r = call(claim, "claim", self.work.results / "paper.json", again, second)   # several files; the result first
        self.assertEqual(([e["file"] for e in r.lines], r.code, r.err), (["paper.pdf", "paper.2.pdf"], 0, ""))
        self.assertEqual([e["result"] for e in self.work.events("claim")], ["claimed", "held", "refused", "claimed", "claimed"])
        self.assertEqual([e["proposal"]["title"] for e in self.work.events("claim")][:2], ["Unknown", "Accepted"],
                         "a file the agent hands over is what it names, else not settled")
        self.assertEqual(call(claim, "claim", again).code, 2, "no result")
        self.assertEqual(self.run_(again, self.work.results / "other.json", "paper").code, 2, "two results")
        self.assertEqual(call(claim, "claim", self.work.results / "paper.json").code, 2, "no file")
        gone = self.work.inbox / "gone.pdf"
        r = self.run_(gone, "paper")
        self.assertEqual((r.code, r.lines), (1, [{"file": str(gone), "code": "file_not_found", "hint": "No such file."}]))
        kept = fake_pdf(self.work.inbox / "f.pdf", [f"{TITLE}\nWei Liu, a third copy"])
        r = self.run_(kept, "nobody")
        self.assertEqual((r.code, r.lines[0]["code"], kept.exists()), (1, "result_invalid", True), "no result: no file touched")
        r = call(claim, "claim", "-", self.work.results / "paper.json",
                 stdin=f'{{"event": "claim", "file": "f.pdf", "result": "left", "source": "{kept}"}}\n')
        self.assertEqual(r.lines[0]["file"], "paper.3.pdf", "- reads the files by `source`")

    def test_a_stubs_file_is_filed_unjudged(self):
        stub = {"slug": "stub", "request": {"given": "10.9999/html"}, "warnings": ["no_csl_record"]}
        (self.work.results / "stub.json").write_text(json.dumps(stub), encoding="utf-8")
        self.work.inbox.mkdir()
        f = fake_pdf(self.work.inbox / "s.pdf", ["A paper with no record to check against"])
        r = self.run_(f, "stub")
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
        r = self.run_(kept, "paper")
        self.assertEqual((r.code, r.lines[0]["result"], r.lines[0]["source"]), (0, "claimed", str(kept)))
        self.assertTrue(kept.is_file(), "not this run's: copied, never consumed")
        self.assertEqual(run.md5_of(self.work.results / "paper.pdf"), run.md5_of(kept))
        scan = fake_pdf(storage / "scan.pdf", ["A scanned first page"])
        self.assertEqual((self.run_(scan, "other").lines[0]["result"], scan.is_file()), ("held", True))
        # One of this run's downloads is the run's own: consumed.
        dl = fake_pdf(self.dl / "third.pdf", ["Something the user reads"])
        self.result("third", "Something the user reads")
        self.assertEqual(self.run_(dl, "third").lines[0]["result"], "claimed")
        self.assertFalse(dl.exists())

    def test_downloads_scanned_and_listed(self):
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
        r = self.word("scan")
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual([(e["file"], e["result"], e["code"]) for e in r.lines],
                         [("paper.pdf", "claimed", "ok"), ("users-own.pdf", "left", "left")])
        self.assertEqual(r.lines[1]["against"], ["other"], "paper has its file by then; held was never tried")
        self.assertEqual(json.loads((self.work.handoffs / f"{r.lines[1]['handoff']}.json").read_text())["kind"], "left",
                         "a download nobody claimed goes to an agent")
        self.assertEqual((mine.exists(), users.exists(), old.exists()), (False, True, True), "older than .started: not this run's")
        self.assertEqual(self.read("paper"), before, "the scan only appends events: pf.py sync folds")
        self.assertEqual(self.word("scan").lines, [], "a left file is not checked again against the same results")
        # Chrome's second copy of a download this run has filed: the same bytes, so nothing is left to judge
        (self.dl / "download (1).pdf").write_bytes((self.work.results / "paper.pdf").read_bytes())
        self.assertEqual((self.word("scan").lines, sorted(p.name for p in self.work.handoffs.glob("left.*.json"))),
                         ([], ["left.1.json"]), "no second handoff; the copy stays in Downloads for the sweep")
        self.assertIn("download (1).pdf", [e["file"] for e in self.word("downloads").lines], "and the sweep lists it")
        (self.dl / "download (1).pdf").unlink()
        self.result("third", "Something the user reads")
        self.tried("third")
        self.assertEqual([(e["slug"], e["result"]) for e in self.word("scan").lines], [("third", "claimed")])
        # What this run left in Downloads, with md5 and size, logged nowhere; the library is paper-to-zotero's to ask.
        left = fake_pdf(self.dl / "left.pdf", ["Unrelated"])
        log = self.work.log.read_bytes()
        r = self.word("downloads")
        self.assertEqual([(e["file"], e["source"], e["md5"], e["size"], e["why"]) for e in r.lines if e["file"].endswith(".pdf")],
                         [("left.pdf", str(left), run.md5_of(left), left.stat().st_size, "sweep")])
        self.assertEqual((r.code, r.err, self.work.log.read_bytes()), (0, "", log), "a listing: no summary, no event")
        self.assertTrue(left.exists())
        left.unlink()
        self.assertEqual(self.word("downloads").code, 0, "nothing left is no failure, as ls")

    def test_cannot_go_on(self):
        self.work.set(downloads=None)
        r = self.word("scan")
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "no_downloads"))
        self.work.started.unlink()
        for word in ("scan", "downloads"):
            r = self.word(word)
            self.assertEqual((r.code, r.lines[0]["code"], r.err), (1, "no_started", ""), "not made ready: its line")
        r = call(claim, "downloads", self.work.root / "nowhere")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_work_dir"))
        self.assertEqual(call(claim, "scan").code, 2, "the directory is named")
        self.assertEqual(call(claim, "sweep", self.work.root).code, 2, "no such command")

    def test_smoke(self):
        r = smoke("scan", self.work.root)
        self.assertEqual((r.code, r.err), (0, ""), r)
        r = smoke("watch", "-h")
        self.assertIn("until stopped", r.out.split("\n\n")[1])


if __name__ == "__main__":
    unittest.main()
