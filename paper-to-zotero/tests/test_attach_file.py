# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/attach_file.py against the fake Zotero (the upload itself: test_zotero_attach.py); pdftotext and
pdfinfo are stubs that print a file's sidecars."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from helpers import call, config_file, fake_pdf, load, poppler_stubs, smoke
from fake_zotero import FakeZotero

from p2zlib import run

attach = load("attach_file")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
PARENT = "PARENT01"


class AttachFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file(institution={"proxy": "proxy.example.edu"})

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        self.zot.add_item(PARENT, itemType="journalArticle", title=TITLE, creators=[{"creatorType": "author", "lastName": "Liu"}],
                          date="2022")
        self.work = run.Work(tempfile.mkdtemp(prefix="p2z-attach-"))
        self.work.records.mkdir()
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{poppler_stubs(self.work.scratch / 'bin')}:{os.environ['PATH']}"}))
        self.rec = self.work.records / "liu.json"
        self.rec.write_text(json.dumps({"item": {"title": TITLE, "url": "https://www-publisher-org.proxy.example.edu/a/1",
                                                 "creators": [{"lastName": "Liu"}]},
                                        "saved": {"key": PARENT, "version": 1, "citationKey": None, "created_at": "x"}}))

    def run_(self, *argv):
        return call(attach, *argv, "--base-url", self.zot.base_url, config=self.config)

    def attachments(self):
        return [it["data"] for it in self.zot.items.values() if it["data"].get("parentItem") == PARENT]

    def test_attaches_the_checked_file_once(self):
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"]), (0, "skipped", "no_file_yet"))
        fake_pdf(self.work.records / "liu.preprint.pdf", [f"{TITLE}\nWei Liu"])
        r = self.run_(self.rec, "--dry-run")
        self.assertEqual((r.lines[0]["code"], self.attachments()), ("ok", []))
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["title"]), (0, "ok", "Unknown"), "no label, no site known")
        block = run.read(self.rec)["attach"]
        self.assertEqual((block["url"], block["title"]), ("https://www.publisher.org/a/1", "Unknown"), "the proxy is taken off")
        [att] = self.attachments()
        self.assertEqual((att["md5"], att["url"]), (block["md5"], "https://www.publisher.org/a/1"))
        self.zot.requests.clear()
        self.assertEqual(self.run_(self.rec).lines[0]["reason"], "attached")
        self.assertEqual([p for _, p, _, _ in self.zot.requests], ["/api/"], "only the server check: the record says it is attached")
        rec = run.read(self.rec)
        rec.pop("attach")
        rec["label"] = {"title": "Preprint-arXiv-v2", "by": "agent", "why": "the arXiv stamp"}
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.lines[0]["reason"], r.lines[0]["title"], r.lines[0]["suggested_title"]),
                         ("already_attached", "Unknown", "Preprint-arXiv-v2"), "the item's child holds it: no upload, no rename")
        self.assertEqual((len(self.attachments()), run.read(self.rec)["attach"]["existing"]), (1, True))
        self.assertEqual(self.run_(self.rec).lines[0]["reason"], "attached", "an attachment the item had is never renamed here")

    def test_unsettled_is_attached_as_unknown_then_renamed_once_labelled(self):
        f = fake_pdf(self.work.scratch / "in.pdf", [f"{TITLE}\nWei Liu"])
        shutil.copy(f"{f}.txt", self.work.records / "liu.pdf.txt")
        shutil.copy(f.with_name("in.pdf.pages"), self.work.records / "liu.pdf.pages")
        with mock.patch.dict(os.environ, {"PAPER_TO_ZOTERO_CONFIG": str(self.config)}):  # the proxy comes off first
            run.claim(self.work, f, "liu", came={"route": "publisher", "url": "https://ieeexplore-ieee-org.proxy.example.edu/stamp/x.pdf"})
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["title"]), (0, "Unknown-IEEE"), "archived although its version is not settled")
        rec = run.read(self.rec)
        rec["label"] = {"title": "Accepted IEEE", "by": "agent", "why": "typo"}
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "bad_label"))
        rec["label"] = {"title": "Published-IEEE-in_press", "by": "browser_agent", "why": "Early Access banner"}
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["renamed"]),
                         (0, "ok", {"from": "Unknown-IEEE", "to": "Published-IEEE-in_press"}), "this run's own attachment")
        self.assertEqual([a["title"] for a in self.attachments()], ["Published-IEEE-in_press"])
        self.assertEqual(self.run_(self.rec).lines[0]["reason"], "attached")

    def test_a_file_that_fails_the_check_waits_for_the_agent(self):
        wrong = fake_pdf(self.work.records / "liu.pdf", ["Erratum\nA notice about another paper"])
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["verdict"]), (1, "not_verified", "erratum_suspected"))
        self.assertEqual(self.attachments(), [])
        moved = self.work.scratch / "liu.pdf"
        shutil.move(wrong, moved)
        shutil.move(f"{wrong}.txt", f"{moved}.txt")
        run.accept(self.work, moved, "liu", "page 1 is a cover the check cannot read")
        self.assertEqual(self.run_(self.rec).lines[0]["code"], "ok", "accepted by the agent: attached unchecked")

    def test_no_item_yet(self):
        fake_pdf(self.work.records / "liu.pdf", [f"{TITLE}\nWei Liu"])
        rec = run.read(self.rec)
        rec["saved"] = {"pending": True, "at": "x"}
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_item_key"))

    def test_smoke(self):
        r = smoke("attach_file", self.rec, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["reason"]), (0, "no_file_yet"), r)


if __name__ == "__main__":
    unittest.main()
