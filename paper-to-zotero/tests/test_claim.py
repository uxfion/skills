# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/claim.py: filing a fetched file, scanning Downloads, the sweep. check_pdf.py runs for real with
pdftotext / pdfinfo stubbed: the stub prints a PDF's bytes after its 9-byte header, so a test PDF is
b"%PDF-1.4\\n" + the text pdftotext would give."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claim.py"
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
OTHER = "A Completely Different Paper About Lung Nodules"


def pdf(text):
    return b"%PDF-1.4\n" + text.encode("utf-8")


def closed_port_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


class ClaimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="claim_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"
        (self.work / "records").mkdir(parents=True)
        (self.work / ".started").touch()
        past = time.time() - 600
        os.utime(self.work / ".started", (past, past))
        self.dl = self.tmp / "Downloads"
        self.dl.mkdir()
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "pdftotext").write_text('#!/bin/sh\nexec tail -c +10 "$7"\n')
        (self.bin / "pdfinfo").write_text("#!/bin/sh\necho 'Pages: 1'\n")
        for n in ("pdftotext", "pdfinfo"):
            (self.bin / n).chmod(0o755)
        self.record("paper", TITLE)
        self.record("other", OTHER)

    def record(self, slug, title, **extra):
        rec = {"slug": slug, "item": {"itemType": "journalArticle", "title": title,
                                      "creators": [{"creatorType": "author", "lastName": "Liu", "firstName": "Wei"}]},
               **extra}
        (self.work / "records" / f"{slug}.json").write_text(json.dumps(rec))

    def run_script(self, *argv):
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        return subprocess.run([sys.executable, str(SCRIPT), "--work", str(self.work), *argv], capture_output=True,
                              text=True, env=env)

    def lines(self, text):
        return [json.loads(ln) for ln in text.splitlines() if ln.startswith("{")]

    def log(self):
        path = self.work / "fetch.jsonl"
        return [json.loads(ln) for ln in path.read_text().splitlines()] if path.exists() else []

    def inbox(self, name, data):
        (self.work / "inbox").mkdir(exist_ok=True)
        f = self.work / "inbox" / name
        f.write_bytes(data)
        return f

    def download(self, name, data, age=0):
        f = self.dl / name
        f.write_bytes(data)
        if age:
            t = time.time() - age
            os.utime(f, (t, t))
        return f

    # --- --file ---------------------------------------------------------------------

    def test_a_fetched_file_is_checked_and_filed(self):
        src = self.inbox("paper.page.pdf", pdf(f"{TITLE}\nWei Liu"))
        r = self.run_script("--file", str(src), "--slug", "paper", "--source", "https://pub.example/a.pdf", "--via", "page")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        line = self.lines(r.stdout)[0]
        self.assertEqual({k: line[k] for k in ("event", "file", "slug", "result", "version", "code", "source")},
                         {"event": "claim", "file": "paper.pdf", "slug": "paper", "result": "claimed", "version": "published",
                          "code": "ok", "source": "https://pub.example/a.pdf"})
        self.assertEqual((self.work / "records" / "paper.pdf").read_bytes(), pdf(f"{TITLE}\nWei Liu"))
        self.assertFalse(src.exists(), "the inbox copy is consumed")
        self.assertEqual(self.log(), [line])
        self.assertEqual([p.name for p in (self.work / "records").iterdir() if p.name.endswith(".tmp")], [])

    def test_version_names_the_file(self):
        src = self.inbox("paper.http.pdf", pdf(f"{TITLE}\nWei Liu"))
        r = self.run_script("--file", str(src), "--slug", "paper", "--version", "preprint")
        self.assertEqual(self.lines(r.stdout)[0]["file"], "paper.preprint.pdf")
        html = self.inbox("other.snapshot.html", f"<html><title>{OTHER}</title><body>Abstract</body></html>".encode())
        r = self.run_script("--file", str(html), "--slug", "other", "--version", "snapshot")
        self.assertEqual((r.returncode, self.lines(r.stdout)[0]["file"]), (0, "other.html"))
        self.assertTrue((self.work / "records" / "other.html").is_file())

    def test_a_failing_file_goes_to_unverified(self):
        src = self.inbox("paper.page.pdf", pdf(f"{OTHER}\nSomeone Else"))
        r = self.run_script("--file", str(src), "--slug", "paper", "--via", "page", "--source", "https://x.example/p.pdf")
        self.assertEqual(r.returncode, 1)
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["result"], line["file"], line["code"], line["source"]),
                         ("unverified", "paper.page.pdf", "title_not_found", "https://x.example/p.pdf"))
        self.assertTrue((self.work / "unverified" / "paper.page.pdf").is_file())
        self.assertFalse((self.work / "records" / "paper.pdf").exists())

    def test_a_second_copy_goes_to_stray(self):
        (self.work / "records" / "paper.pdf").write_bytes(pdf(TITLE))
        src = self.inbox("paper.http.pdf", pdf(f"{TITLE}\nWei Liu"))
        r = self.run_script("--file", str(src), "--slug", "paper")
        self.assertEqual((r.returncode, self.lines(r.stdout)[0]["result"]), (1, "stray"))
        self.assertTrue((self.work / "stray" / "paper.pdf").is_file())
        self.assertEqual((self.work / "records" / "paper.pdf").read_bytes(), pdf(TITLE), "the first one stays")

    def test_file_errors(self):
        r = self.run_script("--file", str(self.tmp / "missing.pdf"), "--slug", "paper")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "file_not_found"))
        src = self.inbox("x.pdf", pdf(TITLE))
        r = self.run_script("--file", str(src), "--slug", "nobody")
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_record"))
        self.assertEqual(self.run_script("--file", str(src)).returncode, 2, "--file needs --slug")

    # --- --scan ---------------------------------------------------------------------

    def test_scan_files_one_match_and_leaves_the_rest(self):
        mine = self.download("liu2022.pdf", pdf(f"{TITLE}\nWei Liu"))
        foreign = self.download("invoice.pdf", pdf("Invoice number 42\nTotal due"))
        old = self.download("old.pdf", pdf(f"{OTHER}\nWei Liu"), age=3600)
        partial = self.download("big.pdf.crdownload", pdf(OTHER))
        r = self.run_script("--scan", "--downloads", str(self.dl))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        events = {e.get("slug") or e["file"]: e for e in self.lines(r.stdout)}
        self.assertEqual((events["paper"]["result"], events["paper"]["file"]), ("claimed", "paper.pdf"))
        self.assertEqual((events["invoice.pdf"]["result"], events["invoice.pdf"]["why"]), ("left", "unmatched"))
        self.assertTrue((self.work / "records" / "paper.pdf").is_file())
        self.assertFalse(mine.exists(), "a claimed download leaves Downloads")
        self.assertTrue(foreign.exists() and old.exists() and partial.exists(), "the rest is not touched")
        r = self.run_script("--scan", "--downloads", str(self.dl))
        self.assertEqual(self.lines(r.stdout), [], "a file logged as left is not checked again")

    def test_a_file_left_before_its_record_existed_is_claimed_once_the_record_is_drafted(self):
        third = "Harnessing Foundation Models for Universal Image Restoration"
        f = self.download("2610.10133v2.pdf", pdf(f"{third}\nWei Liu"))
        first = self.lines(self.run_script("--scan", "--downloads", str(self.dl)).stdout)[0]
        self.assertEqual((first["result"], sorted(first["against"])), ("left", ["other", "paper"]))
        self.record("kong", third)
        line = self.lines(self.run_script("--scan", "--downloads", str(self.dl)).stdout)[0]
        self.assertEqual((line["result"], line["slug"]), ("claimed", "kong"))
        self.assertFalse(f.exists())

    def test_scan_duplicate_goes_to_stray_and_stamp_makes_a_preprint(self):
        (self.work / "records" / "paper.pdf").write_bytes(pdf(TITLE))
        self.download("again.pdf", pdf(f"{TITLE}\nWei Liu"))
        self.download("arxiv.pdf", pdf(f"arXiv:2201.00001v2 [cs.CV] 3 Jan 2022\n{OTHER}\nWei Liu"))
        r = self.run_script("--scan", "--downloads", str(self.dl))
        events = {e["slug"]: e for e in self.lines(r.stdout)}
        self.assertEqual(events["paper"]["result"], "stray")
        self.assertTrue((self.work / "stray" / "paper.pdf").is_file())
        self.assertEqual((events["other"]["result"], events["other"]["file"], events["other"]["version"]),
                         ("claimed", "other.preprint.pdf", "preprint"))

    def test_scan_skips_records_whose_library_item_has_a_pdf_and_reports_ambiguity(self):
        self.record("paper", TITLE, found={"key": "K1", "attachments": [
            {"contentType": "application/pdf", "linkMode": "imported_url"}]})
        f = self.download("x.pdf", pdf(f"{TITLE}\nWei Liu"))
        r = self.run_script("--scan", "--downloads", str(self.dl))
        self.assertEqual((self.lines(r.stdout)[0]["result"], self.lines(r.stdout)[0]["why"]), ("left", "unmatched"))
        self.assertTrue(f.exists())
        self.record("twin", OTHER)
        g = self.download("y.pdf", pdf(f"{OTHER}\nWei Liu"))
        lines = {ln["file"]: ln for ln in self.lines(self.run_script("--scan", "--downloads", str(self.dl)).stdout)}
        self.assertEqual((lines["y.pdf"]["why"], sorted(lines["y.pdf"]["matched"])), ("ambiguous", ["other", "twin"]))
        self.assertEqual(lines["x.pdf"]["against"], ["twin"], "a left file is checked only against the new record")
        self.assertTrue(g.exists())

    def test_sweep_lists_what_is_left(self):
        self.download("leftover.pdf", pdf("whatever"))
        r = self.run_script("--sweep", "--downloads", str(self.dl), "--base-url", closed_port_url())
        line = self.lines(r.stdout)[0]
        self.assertEqual((line["result"], line["why"], line["file"]), ("left", "sweep", "leftover.pdf"))
        self.assertEqual(self.log()[-1]["file"], "leftover.pdf")

    def test_cannot_check(self):
        os.remove(self.work / ".started")
        r = self.run_script("--scan", "--downloads", str(self.dl))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_started"))
        r = self.run_script("--scan", "--downloads", str(self.tmp / "nowhere"))
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_downloads"))
        r = subprocess.run([sys.executable, str(SCRIPT), "--work", str(self.tmp / "nowork"), "--scan", "--downloads",
                            str(self.dl)], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["code"]), (2, "no_work_dir"))


if __name__ == "__main__":
    unittest.main()
