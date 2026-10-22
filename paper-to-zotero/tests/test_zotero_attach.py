# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for Zotero.attach in scripts/p2zlib/zotero.py: one file onto one item, the three-step upload, against the fake."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import config_file
from fake_zotero import LIB, FakeZotero

from p2zlib import cli, zotero

PARENT = "PARENT01"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
HTML = b"<!DOCTYPE html>\n<html><head><title>Article</title></head><body>Abstract text</body></html>\n"
MD5 = hashlib.md5(PDF).hexdigest()
FILENAME = "Liu and Zhang - 2022 - A Paper With Colon.pdf"
URL = "https://doi.org/10.1000/xyz"


class Attach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = FakeZotero()
        cls.cfg = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()

    def setUp(self):
        self.fake.reset()
        self.zot = zotero.Zotero(self.fake.base_url)
        patcher = mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(self.cfg)})
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory(prefix="p2z-attach-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.fake.add_item(PARENT, itemType="journalArticle", title="A Paper: With Colon", date="2022-03-01",
                           creators=[{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"},
                                     {"creatorType": "author", "firstName": "Jing", "lastName": "Zhang"}])

    def file(self, name="paper.pdf", content=PDF):
        path = self.tmp / name
        path.write_bytes(content)
        return path

    def child(self, key, **fields):
        return self.fake.add_item(key, itemType="attachment", parentItem=PARENT, linkMode="imported_url",
                                  contentType="application/pdf", **fields)

    def stop(self, fn, *args, **kwargs):
        with self.assertRaises(cli.Stop) as caught:
            fn(*args, **kwargs)
        return caught.exception

    def posts(self, path=f"{LIB}/items"):
        return self.fake.requested("POST", path)

    # ---- the main line ----

    def test_a_new_attachment_is_created_uploaded_and_read_back(self):
        res = self.zot.attach(PARENT, self.file(), url=URL)
        key = res["attachment"]
        self.assertEqual(res, {"code": "ok", "attachment": key, "md5": MD5, "filename": FILENAME, "title": "Unknown",
                               "reused": False, "file_existed": False}, "no title given: the version word the bytes give")
        att = self.fake.data(key)
        self.assertEqual({f: att.get(f) for f in ("parentItem", "linkMode", "contentType", "title", "url", "md5", "filename")},
                         {"parentItem": PARENT, "linkMode": "imported_url", "contentType": "application/pdf", "title": "Unknown",
                          "url": URL, "md5": MD5, "filename": FILENAME})
        self.assertNotIn("charset", att)
        self.assertEqual(list(self.fake.uploads.values()), [PDF])
        self.assertEqual(Path(self.zot.file_path(key)).read_bytes(), PDF)
        authorize = self.posts(f"{LIB}/items/{key}/file")[0][3]
        self.assertIn(b"filename=Liu%20and%20Zhang", authorize, "spaces go as %20: Zotero keeps a '+' as it is")
        writes = len(self.fake.writes())
        again = self.zot.attach(PARENT, self.file(), title="Published-IEEE", url=URL)
        self.assertEqual(again, {"code": "skipped", "reason": "already_attached", "attachment": key, "md5": MD5,
                                 "filename": FILENAME, "title": "Unknown"}, "the title it has stays")
        self.assertEqual(len(self.fake.writes()), writes, "never uploaded twice")

    def test_a_child_holding_the_same_md5_settles_it_without_verify(self):
        self.child("OLDATT01", title="Full Text PDF", filename="old name.pdf", md5=MD5)
        verify = mock.Mock(side_effect=AssertionError("verify must not run"))
        res = self.zot.attach(PARENT, self.file(), url=URL, verify=verify)
        self.assertEqual(res, {"code": "skipped", "reason": "already_attached", "attachment": "OLDATT01", "md5": MD5,
                               "filename": "old name.pdf", "title": "Full Text PDF"})
        self.assertEqual(self.fake.writes(), [])

    def test_a_child_in_the_trash_counts_for_nothing(self):
        self.child("OLDATT01", title="PDF", filename=FILENAME, md5=MD5, deleted=True)
        self.child("HALF0001", title="PDF", filename=FILENAME, deleted=True)
        res = self.zot.attach(PARENT, self.file(), url=URL)
        self.assertEqual((res["code"], res["reused"]), ("ok", False))
        self.assertNotIn(res["attachment"], ("OLDATT01", "HALF0001"))

    def test_an_empty_child_left_by_an_interrupted_run_is_reused(self):
        self.child("OTHER001", title="PDF", filename="another name.pdf")
        self.child("HALF0001", title="Unknown-IEEE", filename=FILENAME)
        res = self.zot.attach(PARENT, self.file(), title="Published-IEEE", url=URL)
        self.assertEqual((res["code"], res["attachment"], res["reused"], res["file_existed"], res["title"]),
                         ("ok", "HALF0001", True, False, "Published-IEEE"))
        self.assertEqual(self.posts(), [], "no new attachment item")
        self.assertEqual((self.fake.data("HALF0001")["md5"], self.fake.data("HALF0001")["title"]), (MD5, "Published-IEEE"),
                         "the caller's title wins over the half-made one's")
        self.assertNotIn("md5", self.fake.data("OTHER001"))

    def test_zotero_already_having_the_file_skips_the_transfer(self):
        self.child("HALF0001", title="PDF", filename=FILENAME)
        self.fake.bump_before_write = 1   # another run finishes the upload between our look and our request
        self.fake.concurrent_edit = lambda it: it["data"].update(md5=MD5)
        res = self.zot.attach(PARENT, self.file(), url=URL)
        self.assertEqual((res["code"], res["attachment"], res["file_existed"]), ("ok", "HALF0001", True))
        self.assertEqual(self.fake.uploads, {})

    def test_an_html_snapshot_carries_its_charset(self):
        res = self.zot.attach(PARENT, self.file("page.html", HTML), url=URL)
        att = self.fake.data(res["attachment"])
        self.assertEqual((att["contentType"], att["charset"], att["title"]), ("text/html", "utf-8", "Snapshot"))
        self.assertEqual(res["filename"], "Liu and Zhang - 2022 - A Paper With Colon.html")
        gbk = '<html><head><meta charset="GBK"><title>文章</title></head><body>摘要</body></html>'.encode("gbk")
        res = self.zot.attach(PARENT, self.file("cn.htm", gbk), url=URL, filename="cn.html")
        self.assertEqual(self.fake.data(res["attachment"])["charset"], "gbk")
        self.assertEqual(zotero.file_type(b"\xef\xbb\xbf<html><meta charset=latin-1>", "a.html"), ("text/html", ".html", "utf-8"))
        self.assertEqual(zotero.file_type(b"<html>", "a.HTML"), ("text/html", ".html", "utf-8"))
        self.assertEqual(zotero.file_type(PDF, "download"), ("application/pdf", ".pdf", None))
        self.assertIsNone(zotero.file_type(b"just text", "a.html"))

    def test_only_a_pdf_or_an_html_page_is_taken(self):
        failure = self.stop(self.zot.attach, PARENT, self.file("bad.pdf", HTML), url=URL)
        self.assertEqual((failure.code, failure.extra["head"]), ("unsupported_file", "<!DOCTYPE html>\n"))
        self.assertIn("web page", failure.hint)
        self.assertEqual(self.stop(self.zot.attach, PARENT, self.file("x.html", b"\x00\x01"), url=URL).code, "unsupported_file")
        self.assertEqual(self.stop(self.zot.attach, PARENT, self.tmp / "none.pdf", url=URL).code, "file_not_found")
        self.assertEqual(self.fake.requests, [], "Zotero is not asked about a file that cannot go")

    def test_the_default_filename_follows_zoteros_pattern(self):
        name = zotero.default_filename
        self.assertEqual(name({"title": "T", "date": "2020", "creators": [{"creatorType": "editor", "lastName": "Ed"},
                                                                          {"creatorType": "contributor", "name": "Org"}]}),
                         "Ed - 2020 - T.pdf")
        self.assertEqual(name({"title": "T", "creators": [{"creatorType": "author", "lastName": n} for n in "ABC"]}, ".html"),
                         "A et al. - T.html")
        self.assertEqual(name({"creators": [{"creatorType": "author", "name": "WHO"}], "date": "May 2019"}), "WHO - 2019.pdf")
        self.assertEqual(name({}), "attachment.pdf")
        self.assertEqual(len(name({"title": "x" * 300})), 120 + len(".pdf"))
        res = self.zot.attach(PARENT, self.file(), url=URL, filename='a/b: "c".pdf')
        self.assertEqual(self.fake.data(res["attachment"])["filename"], "a b c .pdf")
        self.assertEqual(self.stop(self.zot.attach, PARENT, self.file(), url=URL, filename=":/?").code, "invalid_filename")

    def test_the_title_is_the_callers(self):
        res = self.zot.attach(PARENT, self.file("v.preprint.pdf"), title="Preprint-arXiv-v7", url=URL)
        self.assertEqual((res["title"], self.fake.data(res["attachment"])["title"]), ("Preprint-arXiv-v7", "Preprint-arXiv-v7"))
        self.assertTrue(self.zot.retitle(res["attachment"], "Accepted-arXiv-v7"))
        self.assertFalse(self.zot.retitle(res["attachment"], "Accepted-arXiv-v7"), "nothing sent when it has the title")
        self.assertEqual(self.fake.data(res["attachment"])["title"], "Accepted-arXiv-v7")

    def test_no_url_makes_a_stored_file_without_a_source(self):
        res = self.zot.attach(PARENT, self.file(), url=None)
        att = self.fake.data(res["attachment"])
        self.assertEqual((att["linkMode"], "url" in att, att["md5"]), ("imported_file", False, MD5))

    # ---- refusals and failures ----

    def test_verify_sees_the_parent_and_can_refuse(self):
        seen = []

        def verify(data):
            seen.append(data["title"])
            raise cli.Stop("not_verified", hint="not this paper")

        self.assertEqual(self.stop(self.zot.attach, PARENT, self.file(), url=URL, verify=verify).code, "not_verified")
        self.assertEqual(seen, ["A Paper: With Colon"])
        self.assertEqual(self.fake.writes(), [])
        self.assertEqual(self.stop(self.zot.attach, PARENT, self.file(), url=URL, verify=verify, dry_run=True).code,
                         "not_verified", "a dry run shows the refusal too")

    def test_dry_run_writes_nothing_and_needs_no_key(self):
        with mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(config_file(key=None))}):
            res = self.zot.attach(PARENT, self.file(), url=URL, dry_run=True)
            self.assertEqual(res, {"code": "ok", "dry_run": True, "attachment": None, "md5": MD5, "filename": FILENAME,
                                   "title": "Unknown", "reused": False, "contentType": "application/pdf",
                                   "url": URL, "size": len(PDF)})
            self.child("HALF0001", title="PDF", filename=FILENAME)
            res = self.zot.attach(PARENT, self.file(), url=URL, dry_run=True)
            self.assertEqual((res["attachment"], res["reused"]), ("HALF0001", True))
        self.assertEqual(self.fake.writes(), [])

    def test_not_found_and_not_a_parent(self):
        failure = self.stop(self.zot.attach, "NOPE0000", self.file(), url=URL)
        self.assertEqual((failure.code, failure.extra["key"]), ("not_found", "NOPE0000"))
        self.child("ATTACH01", title="PDF", filename="x.pdf")
        self.fake.add_item("NOTE0001", itemType="note", parentItem=PARENT, note="n")
        for key, item_type in (("ATTACH01", "attachment"), ("NOTE0001", "note")):
            failure = self.stop(self.zot.attach, key, self.file(), url=URL)
            self.assertEqual((failure.code, failure.extra["itemType"], failure.extra["parentItem"]),
                             ("not_a_parent", item_type, PARENT))
        self.assertEqual(self.fake.writes(), [])

    def test_403_on_the_file_step_is_write_denied_and_a_rerun_reuses_the_item(self):
        self.fake.file_step_status = {"authorize": (403, "Library does not allow file editing")}
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
        self.assertEqual((failure.code, failure.exit, failure.extra["step"], failure.extra["detail"]),
                         ("write_denied", cli.ACT, "authorize", "Library does not allow file editing"))
        key = failure.extra["attachment"]
        self.assertIn("reuses", failure.hint)
        self.assertNotIn("md5", self.fake.data(key))
        self.fake.file_step_status = {}
        res = self.zot.attach(PARENT, self.file(), url=URL)
        self.assertEqual((res["code"], res["attachment"], res["reused"]), ("ok", key, True))
        self.assertEqual(len(self.posts()), 1, "the attachment item is made once")

    def test_a_failed_step_is_write_failed_and_names_the_step(self):
        for step in ("authorize", "transfer", "register"):
            with self.subTest(step=step):
                self.fake.file_step_status = {step: (500, "boom")}
                failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
                self.assertEqual((failure.code, failure.extra["step"], failure.extra["status"], failure.extra["detail"]),
                                 ("write_failed", step, 500, "boom"))
        self.fake.file_step_status = {"authorize": (412, "If-None-Match: * set but file exists")}
        self.assertIn("already records a file", self.stop(self.zot.attach, PARENT, self.file(), url=URL).hint)
        self.fake.file_step_status = {"authorize": (200, "not json")}
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
        self.assertEqual((failure.code, failure.extra["step"]), ("unexpected_response", "authorize"))
        self.fake.file_step_status = {}
        self.fake.reject = lambda obj: (400, "bad attachment") if obj.get("itemType") == "attachment" else None
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL, filename="fresh.pdf")
        self.assertEqual((failure.code, failure.extra["step"], failure.extra["status"]), ("write_failed", "create", 400))

    def test_another_md5_read_back_is_readback_mismatch(self):
        self.fake.file_md5 = "0" * 32
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
        self.assertEqual((failure.code, failure.extra["md5_sent"], failure.extra["md5_read_back"]),
                         ("readback_mismatch", MD5, "0" * 32))
        self.fake.reset()
        self.fake.add_item(PARENT, itemType="journalArticle", title="T")
        self.fake.ignore_writes = True
        self.assertIsNone(self.stop(self.zot.attach, PARENT, self.file(), url=URL).extra["md5_read_back"])

    def test_cannot_check_replies_raise(self):
        self.fake.write_status = (401, "Invalid key")
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
        self.assertEqual((failure.code, failure.exit), ("key_rejected", cli.CANNOT))
        self.fake.write_status = None
        self.fake.file_step_status = {"register": (403, "Local API is not enabled")}
        self.assertEqual(self.stop(self.zot.attach, PARENT, self.file(), url=URL).code, "local_api_disabled")
        self.fake.disabled = True
        failure = self.stop(self.zot.attach, PARENT, self.file(), url=URL)
        self.assertEqual((failure.code, failure.exit), ("local_api_disabled", cli.CANNOT))


if __name__ == "__main__":
    unittest.main()
