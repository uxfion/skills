# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/read_library.py (p2z.py items, search, children, pdf, collections, tags, schema) against the fake Zotero."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, load, smoke
from fake_zotero import FakeZotero, LIB

from p2zlib import zotero

read = load("read_library")
STORAGE = Path(tempfile.mkdtemp(prefix="zotero-storage-"))
PUBLISHED = STORAGE / "ATT00002" / "Smith et al. - 2024 - Paper.pdf"     # on disk; ATT00003's file is not
PUBLISHED.parent.mkdir()
PUBLISHED.write_bytes(b"%PDF-1.7")


class ReadLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        for i in range(30):
            z.add_item(f"K{i:07d}", version=i + 1, itemType="journalArticle", title=f"Paper number {i}",
                       citationKey=f"auth{i}", collections=["C1AAAAAA"] if i % 5 == 0 else ["C2AAAAAA"] if i == 7 else [],
                       tags=[{"tag": "a"}, {"tag": "b"}] if i < 3 else [{"tag": "a"}] if i < 6 else [])
        z.data("K0000001")["citationKey"] = z.data("K0000002")["citationKey"] = "dupkey"
        z.add_item("ATT00001", version=300, itemType="attachment", parentItem="K0000000", title="PDF",
                   contentType="application/pdf", md5="abc")
        z.add_item("NOTE0001", version=301, itemType="note", parentItem="K0000000", note="<p>speckle</p>")
        z.add_item("ANNO0001", version=306, itemType="annotation", parentItem="ATT00001", annotationComment="look")
        # K0000004: a title outside the scheme first, a preprint, then the published version; K0000005: only a snapshot.
        z.add_item("ATT00005", version=305, itemType="attachment", parentItem="K0000004", title="Full Text PDF",
                   contentType="application/pdf", linkMode="imported_file", dateAdded="2025-12-01T00:00:00Z", md5="old")
        z.add_item("ATT00003", version=302, itemType="attachment", parentItem="K0000004", title="Preprint-arXiv-v3",
                   contentType="application/pdf", linkMode="imported_file", dateAdded="2026-01-01T00:00:00Z", md5="pre")
        z.add_item("ATT00002", version=303, itemType="attachment", parentItem="K0000004", title="Published-IEEE-in_press",
                   contentType="application/pdf", linkMode="imported_file", dateAdded="2026-02-01T00:00:00Z", md5="pub")
        z.add_item("ATT00004", version=304, itemType="attachment", parentItem="K0000005", title="Snapshot",
                   contentType="text/html", linkMode="imported_url")
        z.files["ATT00002"] = PUBLISHED
        z.add_collection("C1AAAAAA", "医疗图像", version=1)
        z.add_collection("C2AAAAAA", "超声挑战赛", "C1AAAAAA", version=2)
        z.add_collection("C3AAAAAA", "超声挑战赛", version=3)     # the same name at the top level
        z.add_collection("C4AAAAAA", "Old", deleted=True, version=4)
        z.add_collection("C5AAAAAA", "Orphan of Old", "C4AAAAAA", version=5)
        z.tag_meta = [{"tag": "CVPR", "meta": {"type": 0, "numItems": 4}},
                      {"tag": "Deep learning", "meta": {"type": 1, "numItems": 6}},
                      {"tag": "rare", "meta": {"type": 0, "numItems": 1}}]

    def run_(self, command, *argv, base=None, stdin=""):
        return call(read, command, *argv, "--base-url", base or self.zot.base_url, stdin=stdin)

    def gets(self, path):
        return [q for _, _, q, _ in self.zot.requested("GET", path)]

    def keys(self, r):
        return [row.get("key") for row in r.lines]

    def test_items_picked_by_filters_in_one_request(self):
        r = self.run_("items", "--collection", "医疗图像")
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual(self.keys(r), [f"K{i:07d}" for i in range(0, 30, 5)])
        self.assertNotIn("data", r.lines[0])
        self.assertNotIn("limit", self.gets(f"{LIB}/collections/C1AAAAAA/items/top")[0], "a listing comes whole")
        self.assertEqual(self.keys(self.run_("items", "--collection", "医疗图像", "-r"))[-1], "K0000007",
                         "-r: the collection under it too")
        self.assertEqual(self.keys(self.run_("items", "--tag", "a", "--tag", "b")), ["K0000000", "K0000001", "K0000002"],
                         "a repeated --tag: each")
        self.assertEqual(self.keys(self.run_("items", "--since-version", "28")), ["K0000028", "K0000029"])
        self.assertIn("ATT00001", self.keys(self.run_("items", "--collection", "C1AAAAAA", "-a")) +
                      self.keys(self.run_("items", "-a", "--since-version", "299")), "-a: children too")

        r = self.run_("items")
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "usage"), "nothing named: not the whole library")
        r = self.run_("items", "--collection", "超声挑战赛")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "ambiguous"))
        self.assertEqual({c["path"] for c in r.lines[0]["candidates"]}, {"超声挑战赛", "医疗图像/超声挑战赛"})

    def test_items_named_by_key_cite_or_stdin(self):
        r = self.run_("items", "K0000003", "auth7", "ATT00001", "auth7", "NOPE1234", "dupkey")
        self.assertEqual(r.code, 1, r)
        self.assertEqual([(row.get("key") or row.get("item"), row.get("code")) for row in r.lines],
                         [("K0000003", None), ("K0000007", None), ("ATT00001", None), ("NOPE1234", "not_found"),
                          ("dupkey", "ambiguous")], "an attachment by its key; an item named twice once")
        self.assertEqual(r.lines[-1]["keys"], ["K0000001", "K0000002"])
        self.assertEqual(r.last, {"summary": {"total": 6, "failed": 2}})

        stdin = "\n".join([json.dumps({"key": "K0000009", "title": "x"}), json.dumps({"cite": "auth8"}), "auth10", ""])
        r = self.run_("items", "-", "--collection", "医疗图像", stdin=stdin)
        self.assertEqual((r.code, self.keys(r)), (0, ["K0000010"]), "named items pass the filters or print nothing")
        r = self.run_("items", "-", stdin='{"tag": "a"}\n')
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "invalid_list"))
        failed, skip = {"item": "nope", "code": "not_found", "hint": "h"}, {"slug": "s", "code": "skipped", "reason": "r"}
        r = self.run_("items", "-", stdin="\n".join(map(json.dumps, [failed, skip, {"key": "K0000003"}])))
        self.assertEqual((r.code, r.lines[:2], self.keys(r)[2:]), (1, [failed, skip], ["K0000003"]),
                         "upstream's skip and failure are passed on as they are; the failure is not done")
        self.assertEqual(r.last, {"summary": {"total": 3, "failed": 1}})

    def test_search(self):
        r = self.run_("search", "number", "24")
        self.assertEqual((r.code, self.keys(r)), (0, ["K0000024"]), "the words make one query")
        self.assertEqual(self.keys(self.run_("search", "auth13")), ["K0000013"], "the citation key, by default")
        self.assertEqual(self.keys(self.run_("search", "--all-fields", "speckle")), ["K0000000"], "a note's hit: its parent")
        self.assertEqual(self.keys(self.run_("search", "--all-fields", "speckle", "-a")), ["NOTE0001"])
        self.assertEqual(self.keys(self.run_("search", "Paper", "--collection", "医疗图像", "-r", "--tag", "a")),
                         ["K0000000", "K0000005"], "the filters keep the hits that pass")
        r = self.run_("search", "Paper", "--collection", "超声挑战赛")
        self.assertEqual((r.code, [row["code"] for row in r.lines]), (1, ["ambiguous"]))
        r = self.run_("search", "nothing-like-it")
        self.assertEqual((r.code, r.out, r.err), (1, "", ""), "no hit is exit 1, as grep")

    def test_children(self):
        self.assertEqual(set(self.keys(self.run_("children", "auth0"))), {"ATT00001", "NOTE0001"})
        self.assertEqual(self.keys(self.run_("children", "ATT00001")), ["ANNO0001"], "an attachment: its annotations")
        r = self.run_("children", "NOPE1234")
        self.assertEqual((r.code, r.lines), (1, [{"item": "NOPE1234", "code": "not_found", "hint": zotero.HINT_NOT_FOUND}]))
        self.assertEqual(self.run_("children").code, 2)

    def test_collections_tags_schema(self):
        rows = self.run_("collections").lines
        self.assertEqual([row["path"] for row in rows], ["医疗图像", "医疗图像/超声挑战赛", "超声挑战赛"])
        self.assertEqual(rows[1]["parentCollection"], "C1AAAAAA")
        self.assertEqual(len(self.run_("collections", "-a").lines), 5, "-a: the trash's too")
        self.assertEqual(self.run_("tags").lines[0], {"tag": "CVPR", "type": 0, "count": 4})
        self.assertEqual([row["tag"] for row in self.run_("tags", "--min-count", "3").lines], ["CVPR", "Deep learning"])
        rows = self.run_("schema").lines
        self.assertEqual((len(rows), rows[0]["version"]), (1, 44))

    def test_pdf(self):
        r = self.run_("pdf", "auth4")
        self.assertEqual((r.code, r.err), (0, ""), r)
        self.assertEqual([(row["attachment"], row["version"], row["source"], row["detail"], row["standard"], row["md5"],
                           row["exists"]) for row in r.lines],
                         [("ATT00002", "published", "IEEE", ["in_press"], True, "pub", True),
                          ("ATT00003", "preprint", "arXiv", ["v3"], True, "pre", False),
                          ("ATT00005", "unknown", None, [], False, "old", False)], "a title outside the scheme: unknown")
        self.assertEqual((r.lines[0]["path"], r.lines[0]["citationKey"]), (str(PUBLISHED), "auth4"))
        self.assertIsNone(r.lines[1]["path"])

        r = self.run_("pdf", "K0000005", "ATT00002")
        self.assertEqual([(row["code"], row.get("attachments") or row.get("parentItem")) for row in r.lines],
                         [("no_pdf", ["text/html"]), ("not_a_parent", "K0000004")])
        self.assertEqual((r.code, r.last), (1, {"summary": {"total": 2, "failed": 2}}))

    def test_local_path(self):
        self.assertEqual(zotero.local_path("file:///home/me/Zotero/storage/AB12CD34/a%20b.pdf"),
                         "/home/me/Zotero/storage/AB12CD34/a b.pdf")
        win = zotero.local_path("file:///C:/Users/me/Zotero/storage/AB12CD34/a%20b.pdf")
        self.assertEqual(win, "/mnt/c/Users/me/Zotero/storage/AB12CD34/a b.pdf" if shutil.which("wslpath")
                         else "C:/Users/me/Zotero/storage/AB12CD34/a b.pdf")

    def test_cannot_read(self):
        r = self.run_("pdf", "auth4", "auth5", base=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines, r.last["code"]), (2, [{"item": "auth4", "code": "not_run"},
                                                                 {"item": "auth5", "code": "not_run"}], "zotero_unreachable"))
        self.zot.disabled = True
        r = self.run_("tags")
        self.assertEqual((r.code, r.out, r.last["code"]), (2, "", "local_api_disabled"))

    def test_through_the_entry(self):
        r = smoke("search", "--base-url", self.zot.base_url, "auth13")
        self.assertEqual((r.code, [row["key"] for row in r.lines], r.err), (0, ["K0000013"], ""), r)
        r = smoke("pdf", "-h")
        self.assertEqual(r.code, 0)
        self.assertTrue(r.out.startswith("usage: p2z.py pdf "), r.out[:80])


if __name__ == "__main__":
    unittest.main()
