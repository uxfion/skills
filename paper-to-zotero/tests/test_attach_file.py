# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/attach_file.py: a record's result files attached against the fake Zotero (the upload itself:
test_zotero_attach.py)."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

attach = load("attach_file")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
PARENT = "PARENT01"
URL = "https://www.publisher.org/a/1"


class AttachFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        self.zot.add_item(PARENT, itemType="journalArticle", title=TITLE, creators=[{"creatorType": "author", "lastName": "Liu"}],
                          date="2022")
        root = Path(tempfile.mkdtemp(prefix="p2z-attach-"))
        self.results = root / "fetch" / "results"
        self.results.mkdir(parents=True)
        (root / "records").mkdir()
        self.result = self.results / "liu.json"
        self.result.write_text(json.dumps({"slug": "liu", "record_of": "published"}))
        self.rec = root / "records" / "liu.json"
        self.rec.write_text(json.dumps({"fetched": str(self.result), "item": {"title": TITLE, "url": URL},
                                        "saved": {"key": PARENT, "version": 1, "citationKey": None, "created_at": "x"}}))

    def settle(self, *files, status="got"):
        """The result as paper-fetch's settle leaves it: files [(name, bytes, kind, label title, check)]."""
        entries = []
        for name, body, kind, title, check in files:
            (self.results / name).write_bytes(body)
            entries.append({"name": name, "md5": run.md5_of(self.results / name), "kind": kind, "check": check,
                            "label": {"title": title}})
        res = json.loads(self.result.read_text())
        res.update(files=entries, outcome={"status": status, "tried": [], "last": None})
        self.result.write_text(json.dumps(res))

    def run_(self, *argv):
        return call(attach, *argv, "--base-url", self.zot.base_url, config=self.config)

    def attachments(self):
        return sorted((it["data"]["title"], it["data"].get("url")) for it in self.zot.items.values()
                      if it["data"].get("parentItem") == PARENT)

    def test_attaches_each_settled_file_once(self):
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "unsettled"), "never settled: its files may lack one")
        self.settle(status="not_got")
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["reason"], r.lines[0]["status"]), (0, "no_file_yet", "not_got"))
        paper = ("liu.preprint.pdf", b"%PDF-1.4 the paper", "preprint", "Preprint-arXiv-v2", "ok")
        supplement = ("liu.supplement.pdf", b"%PDF-1.4 its supplement", "supplement", "Supplement-Publisher", "accepted")
        unsure = ("liu.pdf", b"%PDF-1.4 cannot tell", "published", "Unknown-Publisher", "cannot_judge")
        self.settle(paper, supplement, unsure)
        r = self.run_(self.rec, "--dry-run")
        self.assertEqual((r.lines[0]["code"], self.attachments()), ("ok", []))
        r = self.run_(self.rec)
        self.assertEqual((r.code, [(f["name"], f["code"], f["title"]) for f in r.lines[0]["files"]]),
                         (0, [("liu.preprint.pdf", "ok", "Preprint-arXiv-v2"), ("liu.supplement.pdf", "ok", "Supplement-Publisher")]),
                         "a check the agent has not passed (cannot_judge) is left out")
        self.assertEqual(r.lines[0]["unchecked"], ["liu.pdf"], "and named")
        self.assertEqual(self.attachments(), [("Preprint-arXiv-v2", URL), ("Supplement-Publisher", URL)])
        block = run.read(self.rec)["attach"]
        self.assertEqual([(a["kind"], a["title"]) for a in block], [("preprint", "Preprint-arXiv-v2"), ("supplement", "Supplement-Publisher")])
        self.zot.requests.clear()
        self.assertEqual(self.run_(self.rec).lines[0]["reason"], "attached")
        self.assertEqual([p for _, p, _, _ in self.zot.requests], ["/api/"], "only the server check: the record says so")
        self.settle(("liu.preprint.pdf", b"%PDF-1.4 the paper", "preprint", "Accepted-arXiv-v2", "ok"), supplement)
        r = self.run_(self.rec)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["files"][0]["renamed"]),
                         ("ok", {"from": "Preprint-arXiv-v2", "to": "Accepted-arXiv-v2"}), "this run's own attachment, relabelled")
        self.assertEqual(self.attachments()[0][0], "Accepted-arXiv-v2")

    def test_an_unconfirmed_file_and_a_stubs(self):
        self.settle(("liu.pdf", b"%PDF-1.4 cannot tell", "published", "Unknown-IEEE", "cannot_judge"))
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["files"], self.attachments()), (1, "unchecked", ["liu.pdf"], []))
        self.assertIn("no-doi-record.md", r.lines[0]["hint"], "a stub's file goes the connector path")
        self.settle(("liu.pdf", b"%PDF-1.4 a poster with the same words", "published", "Unknown-IEEE", "unconfirmed"))
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["unconfirmed"], self.attachments()), (0, ["liu.pdf"], [("Unknown-IEEE", URL)]),
                         "attached all the same, and named")

    def test_an_item_with_a_pdf_needs_no_result(self):
        self.zot.add_item("HADPDF01", itemType="attachment", parentItem=PARENT, title="Preprint-arXiv-v1",
                          contentType="application/pdf", linkMode="imported_url")
        rec = run.read(self.rec)
        rec.pop("saved")
        run.stamp(rec, "found", {"code": "found", "key": PARENT, "attachments": [
            {"key": "HADPDF01", "version": "preprint", "contentType": "application/pdf"}]})
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"]), (0, "skipped", "library_has_pdf"),
                         "never fetched, so never settled: the item's own PDF settles it")
        self.settle(("liu.pdf", b"%PDF-1.4 the published one", "published", "Published-IEEE", "ok"))
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), "fetched for the published version: attached beside it")

    def test_what_is_refused(self):
        self.settle(("liu.pdf", b"%PDF-1.4 x", "published", "Published-IEEE", "ok"))
        (self.results / "liu.pdf").write_bytes(b"%PDF-1.4 another download")
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"], self.attachments()), (1, "file_changed", []))
        rec = run.read(self.rec)
        rec.pop("fetched")
        rec.save()
        self.assertEqual(self.run_(self.rec).lines[0]["code"], "no_result")

    def test_a_file_the_item_has_keeps_its_title(self):
        self.settle(("liu.pdf", b"%PDF-1.4 x", "published", "Published-IEEE", "ok"))
        self.run_(self.rec)
        rec = run.read(self.rec)
        rec.pop("attach")
        rec.save()
        self.settle(("liu.pdf", b"%PDF-1.4 x", "published", "Published-IEEE-in_press", "ok"))
        r = self.run_(self.rec)
        f = r.lines[0]["files"][0]
        self.assertEqual((r.lines[0]["code"], f["reason"], f["title"], f["suggested_title"]),
                         ("skipped", "already_attached", "Published-IEEE", "Published-IEEE-in_press"), "no upload, no rename")
        self.assertTrue(run.read(self.rec)["attach"][0]["existing"])
        self.assertEqual(self.run_(self.rec).lines[0]["reason"], "attached", "an attachment the item had is never renamed here")

    def test_no_item_yet(self):
        self.settle(("liu.pdf", b"%PDF-1.4 x", "published", "Published-IEEE", "ok"))
        rec = run.read(self.rec)
        rec["saved"] = {"pending": True, "at": "x"}
        rec.save()
        r = self.run_(self.rec)
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_item_key"))

    def test_smoke(self):
        self.settle(status="waiting")
        r = smoke("attach_file", self.rec, "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["reason"], r.lines[0]["status"]), (0, "no_file_yet", "waiting"), r)


if __name__ == "__main__":
    unittest.main()
