# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/read_library.py against the fake Zotero."""
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
        for i in range(250):
            z.add_item(f"K{i:07d}", version=i + 1, itemType="journalArticle", title=f"Paper number {i}",
                       citationKey=f"auth{i}", collections=["C1AAAAAA"] if i % 5 == 0 else [])
        z.data("K0000001")["citationKey"] = z.data("K0000002")["citationKey"] = "dupkey"
        z.add_item("ATT00001", version=300, itemType="attachment", parentItem="K0000000", title="PDF",
                   contentType="application/pdf", md5="abc")
        z.add_item("NOTE0001", version=301, itemType="note", parentItem="K0000000", note="<p>hi</p>")
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
        z.add_collection("C3AAAAAA", "Agent", version=3)
        z.add_collection("C4AAAAAA", "Old", deleted=True, version=4)
        z.add_collection("C5AAAAAA", "Orphan of Old", "C4AAAAAA", version=5)
        z.tag_meta = [{"tag": "CVPR", "meta": {"type": 0, "numItems": 4}},
                      {"tag": "Deep learning", "meta": {"type": 1, "numItems": 6}},
                      {"tag": "rare", "meta": {"type": 0, "numItems": 1}}]

    def run_(self, *argv, base=None):
        return call(read, "--base-url", base or self.zot.base_url, *argv)

    def gets(self, path):
        return [q for _, _, q, _ in self.zot.requested("GET", path)]

    def test_items_paginates_by_100(self):
        r = self.run_("items")
        self.assertEqual(r.code, 0, r)
        rows = r.lines
        self.assertEqual(len(rows), 250)
        self.assertEqual((rows[0]["key"], rows[0]["version"]), ("K0000000", 1))
        self.assertNotIn("data", rows[0])
        self.assertTrue(all("parentItem" not in row for row in rows))
        self.assertEqual([(q["start"], q["limit"]) for q in self.gets(f"{LIB}/items/top")],
                         [("0", "100"), ("100", "100"), ("200", "100")])

    def test_limit_caps_total_and_requests(self):
        self.assertEqual(len(self.run_("items", "--limit", "150").lines), 150)
        self.assertEqual([(q["start"], q["limit"]) for q in self.gets(f"{LIB}/items/top")], [("0", "100"), ("100", "50")])

    def test_all_includes_children(self):
        rows = self.run_("items", "--all").lines
        self.assertEqual(len(rows), 256)
        self.assertIn("ATT00001", {row["key"] for row in rows})

    def test_top_is_gone(self):
        self.assertEqual(self.run_("items", "--top").code, 2, "--top was the default all along")

    def test_tag_filter_is_passed_to_zotero(self):
        self.run_("items", "--tag", "venue/CVPR")
        self.assertEqual(self.gets(f"{LIB}/items/top")[0].get("tag"), "venue/CVPR")

    def test_collection_filter(self):
        rows = self.run_("items", "--collection", "C1AAAAAA").lines
        self.assertEqual(len(rows), 50)
        self.assertTrue(self.gets(f"{LIB}/collections/C1AAAAAA/items/top"))

    def test_keys_are_filtered_to_the_request(self):
        r = self.run_("items", "--key", "K0000000", "--key", "K0000007,NOPE1234")
        self.assertEqual(r.code, 1, "a key that names no item is the agent's to look at")
        self.assertEqual((r.lines[0]["key"], r.lines[0]["code"]), ("NOPE1234", "not_found"))
        self.assertEqual([row["key"] for row in r.lines[1:]], ["K0000000", "K0000007"], "children of a requested key left out")

    def test_q_and_since(self):
        rows = self.run_("items", "--q", "number 24").lines
        self.assertEqual({row["key"] for row in rows}, {"K0000024", "K0000124", "K0000224"} | {f"K000024{i}" for i in range(10)},
                         "every word, anywhere in the field, as Zotero's quick search")
        rows = self.run_("items", "--since", "248").lines
        self.assertEqual([row["key"] for row in rows], ["K0000248", "K0000249"])

    def test_cite_resolution(self):
        r = self.run_("items", "--cite", "auth7")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([row["key"] for row in r.lines], ["K0000007"])
        first = self.gets(f"{LIB}/items")[0]
        self.assertEqual((first["q"], first["qmode"]), ("auth7", "everything"))
        self.assertEqual(self.gets(f"{LIB}/items/top"), [], "no fallback scan when the search hits")

        r = self.run_("items", "--cite", "nobody")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "cite_not_found"))
        self.assertTrue(self.gets(f"{LIB}/items/top"), "the fallback scan ran")

        r = self.run_("items", "--cite", "dupkey")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["keys"]), (1, "cite_ambiguous", ["K0000001", "K0000002"]))

    def test_children_by_key_or_cite(self):
        rows = self.run_("children", "--key", "K0000000").lines
        self.assertEqual({row["key"] for row in rows}, {"ATT00001", "NOTE0001"})
        self.assertEqual({row["key"] for row in self.run_("children", "--cite", "auth0").lines}, {"ATT00001", "NOTE0001"})
        r = self.run_("children", "--key", "NOPE1234")
        self.assertEqual((r.code, [(o["key"], o["code"]) for o in r.lines]), (1, [("NOPE1234", "not_found")]),
                         "not the whole library the local API answers an unknown key with")
        self.assertEqual(self.run_("item", "K0000003").code, 2, "`item` is `items --key`")
        self.assertEqual(self.run_("children").code, 2)

    def test_collections_and_tree(self):
        rows = self.run_("collections").lines
        self.assertEqual(len(rows), 5)
        self.assertNotIn("path", rows[0])
        rows = self.run_("collections", "--tree").lines
        self.assertEqual([row["path"] for row in rows], ["Agent", "医疗图像", "医疗图像/超声挑战赛"])
        self.assertEqual(rows[2]["parentCollection"], "C1AAAAAA")

    def test_tags_min_count(self):
        self.assertEqual(self.run_("tags").lines[0], {"tag": "CVPR", "type": 0, "count": 4})
        self.assertEqual([row["tag"] for row in self.run_("tags", "--min-count", "3").lines], ["CVPR", "Deep learning"])

    def test_schema_once(self):
        rows = self.run_("schema").lines
        self.assertEqual((len(rows), rows[0]["version"]), (1, 44))

    def test_pdf_by_version_with_path_and_md5(self):
        r = self.run_("pdf", "--cite", "auth4")
        self.assertEqual(r.code, 0, r)
        rows = r.lines
        self.assertEqual([(row["attachment"], row["version"], row["source"], row["detail"], row["standard"], row["md5"], row["exists"])
                          for row in rows],
                         [("ATT00002", "published", "IEEE", ["in_press"], True, "pub", True),
                          ("ATT00003", "preprint", "arXiv", ["v3"], True, "pre", False),
                          ("ATT00005", "unknown", None, [], False, "old", False)], "a title outside the scheme: unknown")
        self.assertEqual((rows[0]["path"], rows[0]["citationKey"], rows[0]["title"]), (str(PUBLISHED), "auth4", "Paper number 4"))
        self.assertIsNone(rows[1]["path"])

    def test_pdf_without_one(self):
        r = self.run_("pdf", "--key", "K0000005")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["attachments"]), (1, "no_pdf", ["text/html"]))
        self.assertEqual(self.run_("pdf").code, 2, "pdf needs --key or --cite")

    def test_local_path(self):
        self.assertEqual(zotero.local_path("file:///home/me/Zotero/storage/AB12CD34/a%20b.pdf"),
                         "/home/me/Zotero/storage/AB12CD34/a b.pdf")
        win = zotero.local_path("file:///C:/Users/me/Zotero/storage/AB12CD34/a%20b.pdf")
        self.assertEqual(win, "/mnt/c/Users/me/Zotero/storage/AB12CD34/a b.pdf" if shutil.which("wslpath")
                         else "C:/Users/me/Zotero/storage/AB12CD34/a b.pdf")

    def test_unreachable_and_disabled(self):
        r = self.run_("items", base=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        self.zot.disabled = True
        r = self.run_("tags")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "local_api_disabled"))

    def test_smoke(self):
        r = smoke("read_library", "--base-url", self.zot.base_url, "items", "--limit", "2")
        self.assertEqual((r.code, len(r.lines)), (0, 2), r)


if __name__ == "__main__":
    unittest.main()
