# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/recognize.py: a stub's PDF sent through the fake Zotero's connector, its recognizer finding a
parent item, nothing, or not done in time; an earlier run's attachment after Zotero restarted; and the refusals."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, config_file, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run

recognize = load("recognize")
PDF = b"%PDF-1.4 a paper nobody could identify"
MD5 = hashlib.md5(PDF).hexdigest()
PARENT = {"itemType": "journalArticle", "title": "Measuring What Recognizers Find", "date": "2021-03",
          "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Byron"}],
          "publicationTitle": "Journal of Tests", "DOI": "10.9999/html"}
URL = "https://doi.org/10.9999/html"  # the stub's request, a DOI, as a link


class Recognize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        self.zot.reset()
        root = Path(tempfile.mkdtemp(prefix="p2z-recognize-"))
        results = root / "fetch" / "results"
        results.mkdir(parents=True)
        (root / "records").mkdir()
        self.pdf = results / "109999html.pdf"
        self.pdf.write_bytes(PDF)
        self.result = results / "109999html.json"  # paper-fetch's stub, as its fixture 109999html.json
        self.result.write_text(json.dumps({
            "slug": "109999html", "request": {"given": "10.9999/html"}, "warnings": ["no_csl_record"],
            "files": [{"name": "109999html.pdf", "md5": MD5, "kind": "published", "check": "cannot_judge", "url": None,
                       "label": {"title": "Unknown", "version": "unknown", "source": None, "detail": [], "by": "settle"}}],
            "outcome": {"status": "got", "waiting_on": ["label"], "tried": [], "last": None}}))
        self.rec = root / "records" / "109999html.json"
        self.rec.write_text(json.dumps({"fetched": str(self.result)}))

    def tearDown(self):
        self.zot.recognizer_free.set()  # no request left waiting

    def run_(self, *argv):
        return call(recognize, self.rec, *argv, "--base-url", self.zot.base_url, config=self.config)

    def sent(self):
        return self.zot.requested("POST", "/connector/saveStandaloneAttachment")

    def asked(self):
        """The sessionIDs getRecognizedItem was asked about, in order."""
        return [json.loads(body)["sessionID"] for *_, body in self.zot.requested("POST", "/connector/getRecognizedItem")]

    def ours(self):
        [key] = [k for k, it in self.zot.items.items() if it["data"].get("md5") == MD5]
        return key, self.zot.data(key)

    def earlier_run(self, session, parent=None):
        """The library and the record as a run left them that sent the PDF and was cut off before the recognizer was done."""
        if parent:
            self.zot.add_item("OLDPAPR1", **PARENT, citationKey="byron2021measuring")
        self.zot.add_item("OLDATT01", itemType="attachment", linkMode="imported_url", contentType="application/pdf",
                          md5=MD5, dateAdded="2026-10-30T09:00:00Z", title="PDF" if parent else "Unknown",
                          **({"parentItem": "OLDPAPR1"} if parent else {}))
        rec = run.read(self.rec)
        rec["recognize"] = {"md5": MD5, "title": "Unknown", "url": URL, "sessionID": session, "at": "x", "code": "sent"}
        rec.save()

    def test_recognized_item_saved_and_the_label_restored(self):
        self.zot.selected_collection = "COLL0001"
        self.zot.recognizer = PARENT
        r = self.run_()
        self.assertEqual(r.code, 0, r)
        att, data = self.ours()
        [parent] = [k for k, it in self.zot.items.items() if it["data"].get("title") == PARENT["title"]]
        self.assertEqual((data["parentItem"], data["title"], data["url"]), (parent, "Unknown", URL),
                         "under the recognized item, titled with the label again")
        line = r.lines[0]
        self.assertEqual((line["code"], line["key"], line["attachment"], line["pdf"], line["retitled"]),
                         ("recognized", parent, att, str(self.pdf), {"from": "PDF", "to": "Unknown"}))
        self.assertEqual({k: line["item"][k] for k in (*PARENT, "collections")}, {**PARENT, "collections": ["COLL0001"]},
                         "the item's fields for the judge, and where Zotero filed it")
        rec = run.read(self.rec)
        self.assertEqual({k: v for k, v in rec["saved"].items() if k != "created_at"},
                         {"key": parent, "version": self.zot.items[parent]["version"], "citationKey": None, "via": "recognizer"})
        self.assertEqual((rec["recognize"]["code"], rec["recognize"]["attachment"], self.asked()),
                         ("recognized", att, [rec["recognize"]["sessionID"]]))
        self.assertEqual([s for s in self.zot.sessions], [rec["recognize"]["sessionID"]], "the session the PDF was sent in")
        self.assertFalse([q for _, _, q, _ in self.zot.requests if "since" in q], "only our own attachment is looked at")
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["reason"], len(self.sent())), (0, "saved", 1))

    def test_nothing_recognized_goes_to_the_trash_once(self):
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "not_recognized"), r)
        att, data = self.ours()
        self.assertEqual((r.lines[0]["attachment"], data.get("deleted"), data.get("parentItem")), (att, True, None))
        rec = run.read(self.rec)
        self.assertEqual((rec["recognize"]["code"], "saved" in rec), ("not_recognized", False))
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["reason"], len(self.sent())), (0, "not_recognized", 1), "never sent twice")

    def test_still_recognizing_then_a_rerun_waits_on_the_same_session(self):
        self.zot.recognizer = PARENT
        self.zot.recognizer_free.clear()
        r = self.run_("--wait", "0.2")
        att, data = self.ours()
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["attachment"]), (1, "recognizing", att), r)
        self.assertEqual((data.get("deleted"), data.get("parentItem"), run.read(self.rec)["recognize"]["code"]),
                         (None, None, "sent"), "nothing trashed while the recognizer works")
        self.zot.recognizer_free.set()
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"], len(self.sent())), (0, "recognized", 1), "the PDF is not sent again")
        session = run.read(self.rec)["recognize"]["sessionID"]
        self.assertEqual(self.asked(), [session, session])

    def test_after_a_restart_the_attachments_parent_decides(self):
        self.earlier_run("FORGOTTEN", parent=True)  # Zotero restarted since: it does not know the session
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["key"], r.lines[0]["retitled"], self.sent()),
                         (0, "recognized", "OLDPAPR1", {"from": "PDF", "to": "Unknown"}, []))
        self.assertEqual((run.read(self.rec)["saved"]["citationKey"], self.zot.data("OLDATT01")["title"]),
                         ("byron2021measuring", "Unknown"))
        self.setUp()
        self.earlier_run("FORGOTTEN")
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"], self.zot.data("OLDATT01").get("deleted"), self.sent()),
                         (1, "not_recognized", True, []))

    def test_in_library_dry_run_and_not_a_stub(self):
        self.earlier_run("FORGOTTEN", parent=True)
        rec = run.read(self.rec)
        del rec["recognize"]
        rec.save()
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["parent"], r.lines[0]["citationKey"], self.zot.writes()),
                         (1, "in_library", "OLDPAPR1", "byron2021measuring", []), "the paper is in Zotero: nothing sent")
        self.zot.reset()
        r = smoke("recognize", self.rec, "--dry-run", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["url"], self.zot.writes()), (0, "ok", URL, []), r)
        self.result.write_text(json.dumps({"slug": "109999html", "csl": {"title": "Known"}, "files": []}))
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"], self.sent()), (1, "not_a_stub", []))


if __name__ == "__main__":
    unittest.main()
