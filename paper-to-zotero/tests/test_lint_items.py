# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/lint_items.py against the fake Zotero."""
import unittest

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero, LIB

lint = load("lint_items")
A, B, D, J, K = "AAAAAAAA", "BBBBBBBB", "DDDDDDDD", "JJJJJJJJ", "KKKKKKKK"


def add(z, key, meta=None, **data):
    """A top-level item with a parsed date and a citation key, unless the test says otherwise."""
    data.setdefault("citationKey", key.lower())
    return z.add_item(key, meta={"parsedDate": "2021", **(meta or {})}, **data)


def reported(r):
    return {line["key"]: line for line in r.lines if "problems" in line}


def problems(r):
    return {key: {p["code"]: p for p in line["problems"]} for key, line in reported(r).items()}


class LintItems(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        add(z, A, itemType="journalArticle", title="Paper about segmentation networks", DOI="10.1000/A",
            collections=["COLL0001"], date="2021", url="https://x/a",
            abstractNote="In this work we propose FooNet, a network for segmentation, and we present Weight-Decomposed Low-Rank Adaptation.")
        add(z, B, itemType="journalArticle", title="A second record of that paper", DOI="10.1000/a",
            collections=["COLL0002"], date="2021", abstractNote="x", tags=[{"tag": "FooNet"}])
        add(z, "WWWWWWWW", itemType="webpage", title="Project page", url="https://proxy.example/x")
        add(z, D, {"parsedDate": None}, itemType="conferencePaper", title="An old conference paper",
            date="十一月 23, 2021", collections=["COLL0001"])
        add(z, "CCCCCCCC", itemType="conferencePaper", title="A CVPR paper", DOI="10.1109/CVPR.2019.00453",
            abstractNote="x", date="2019", url="https://openaccess.thecvf.com/content_CVPR_2019/html/x.html")
        add(z, "NNNNNNNN", itemType="conferencePaper", title="A NeurIPS paper", DOI="10.52202/075280-3121",
            abstractNote="x", date="2023", url="https://doi.org/10.52202/075280-3121")
        add(z, J, itemType="journalArticle", title="A journal paper", DOI="10.1000/j", abstractNote="x",
            publicationTitle="Comput Biol Med", journalAbbreviation="Computers in Biology and Medicine", date="2021")
        add(z, "PPPPPPPP", itemType="preprint", title="Same Title Different Version", DOI="10.48550/arXiv.2101.00001",
            abstractNote="x", date="2021")
        add(z, "QQQQQQQQ", itemType="journalArticle", title="Same title, different version", DOI="10.1000/q",
            extra="arXiv: 2101.00001", abstractNote="x", date="2021")
        add(z, K, itemType="journalArticle", title="A paper with nothing to tidy", DOI="10.1000/k", abstractNote="x",
            date="2021", url="https://pub.example/k")
        add(z, "TTTTTTTT", itemType="journalArticle", title="Paper about segmentation networks", DOI="10.1000/a",
            deleted=True)
        z.add_item("PDF00001", itemType="attachment", parentItem=A, contentType="application/pdf", md5="m1",
                   title="Published-Example", url="https://x/a")
        z.add_item("PDF00002", itemType="attachment", parentItem=A, contentType="application/pdf", md5="m2",
                   title="Preprint-arXiv-v2", url="https://arxiv.org/pdf/2101.00001v2")
        z.add_item("NOTE0001", itemType="note", parentItem=A, note="<p>n</p>")
        z.add_collection("COLL0001", "Medical")
        z.add_collection("COLL0002", "Sub", "COLL0001")
        z.add_collection("COLL0009", "Old", deleted=True)

    def run_(self, *argv, base_url=None):
        return call(lint, *argv, "--base-url", base_url or self.zot.base_url, config=self.config)

    def test_attachment_titles(self):
        z, T = self.zot, "TTTTTTT2"
        add(z, T, itemType="journalArticle", title="A paper with many files", DOI="10.1000/t", abstractNote="x",
            date="2021", url="https://pub.example/t")
        att = lambda key, title, ctype="application/pdf", **kw: z.add_item(  # noqa: E731
            key, itemType="attachment", parentItem=T, title=title, contentType=ctype, **{"linkMode": "imported_url", **kw})
        att("FINAL001", "Published-IEEE", md5="f1", dateAdded="2024-05-01")
        att("ARXIV001", "Preprint-arXiv-v1", md5="a1", dateAdded="2024-01-01")
        att("ARXIV003", "Preprint-arXiv-v3", md5="a3", dateAdded="2023-01-01")
        att("OLDPDF01", "Full Text PDF", md5="o1", url="https://ieeexplore-ieee-org.ezproxy.example.edu/stamp/x")
        att("SNAP0001", "Snapshot", "text/html", url="https://www.sciencedirect.com/science/article/pii/S1")
        att("SNAP0002", "Snapshot-Elsevier", "text/html", dateAdded="2024-01-01")
        att("SNAP0003", "Snapshot-Elsevier", "text/html", dateAdded="2024-02-01")
        att("LINK0001", "PubMed entry", "text/html", linkMode="linked_url")
        att("UNKN0001", "Unknown", md5="u1", url="https://ieeexplore.ieee.org/document/1")  # left without a source on purpose
        r = self.run_("--key", T)
        got = [p for p in reported(r)[T]["problems"] if p["code"] in ("nonstandard_title", "label_clash", "superseded")]
        self.assertEqual(got, [
            {"code": "nonstandard_title", "why": "outside_scheme", "attachment": "OLDPDF01", "title": "Full Text PDF",
             "contentType": "application/pdf", "url": "https://ieeexplore.ieee.org/stamp/x", "host": "ieeexplore.ieee.org",
             "url_site": "IEEE", "filename": None, "md5": "o1", "doi": "10.1000/t"},
            {"code": "nonstandard_title", "why": "no_source", "attachment": "SNAP0001", "title": "Snapshot",
             "contentType": "text/html", "url": "https://www.sciencedirect.com/science/article/pii/S1",
             "host": "www.sciencedirect.com", "url_site": "Elsevier", "filename": None, "md5": None, "doi": "10.1000/t"},
            {"code": "label_clash", "title": "Snapshot-Elsevier", "attachments": ["SNAP0002", "SNAP0003"]},
            {"code": "superseded", "attachment": "ARXIV001", "title": "Preprint-arXiv-v1", "by": "ARXIV003",
             "by_title": "Preprint-arXiv-v3"}], "evidence and no proposed name, the proxy taken off; a link is no file")

    def test_the_whole_library(self):
        r = self.run_()
        self.assertEqual(r.code, 1, r)
        found, lines, summary = problems(r), reported(r), r.lines[-1]["summary"]
        self.assertEqual(found[A]["duplicate_of"], {"code": "duplicate_of", "by": "doi", "keys": [B]},
                         "a trashed copy is not a duplicate")
        self.assertNotIn("superseded", found[A], "two sources side by side: no problem")
        self.assertEqual(found[A]["name_not_tagged"]["name"], "FooNet")
        self.assertNotIn("name_not_tagged", found[B], "the tag is there")
        self.assertIn("unfiled_webpage", found["WWWWWWWW"])
        self.assertEqual(set(found[D]), {"date_unparseable", "missing_doi", "missing_abstract", "no_identifier"})
        self.assertEqual(found[J]["abbreviation_misplaced"]["patch"],
                         {"publicationTitle": "Computers in Biology and Medicine", "journalAbbreviation": "Comput Biol Med"})
        self.assertEqual((found["PPPPPPPP"]["duplicate_of"]["by"], found["PPPPPPPP"]["duplicate_of"]["keys"]),
                         ("arxiv", ["QQQQQQQQ"]))
        self.assertNotIn("TTTTTTTT", found)
        self.assertEqual(found["CCCCCCCC"]["url_not_record"]["patch"], {"url": "https://doi.org/10.1109/CVPR.2019.00453"})
        self.assertNotIn("patch", found["NNNNNNNN"]["url_not_record"], "the NeurIPS page is the agent's to find")
        self.assertNotIn("url_not_record", found[A], "a publisher url is the version of record")
        self.assertNotIn("url_not_record", found.get("PPPPPPPP", {}), "a preprint's url is its own")
        self.assertNotIn(K, found)
        self.assertEqual((lines[A]["collections"], lines[B]["collections"]), (["Medical"], ["Medical/Sub"]))
        self.assertEqual((lines[A]["citationKey"], lines[A]["itemType"], lines[A]["title"]),
                         ("aaaaaaaa", "journalArticle", "Paper about segmentation networks"))
        self.assertEqual((summary["items"], summary["with_problems"]), (10, len(found)))
        self.assertEqual(summary["by_code"]["duplicate_of"], 4)

    def test_scope_chooses_what_is_reported_not_what_is_compared(self):
        found = problems(self.run_("--collection", "COLL0001"))
        self.assertEqual(set(found), {A, D})
        self.assertEqual(found[A]["duplicate_of"]["keys"], [B], "found outside the collection")
        found = problems(self.run_("--collection", "COLL0001", "--recursive"))
        self.assertEqual(set(found), {A, B, D})
        self.assertEqual(found[B]["duplicate_of"]["keys"], [A])
        r = self.run_("--key", K)
        self.assertEqual((r.code, reported(r), r.lines[-1]["summary"]),
                         (0, {}, {"items": 1, "with_problems": 0, "by_code": {}}))

    def test_key_and_cite_targets(self):
        r = self.run_("--key", f"{J},CCCCCCCC", "--cite", "aaaaaaaa")
        self.assertEqual(set(problems(r)), {J, "CCCCCCCC", A})
        self.assertEqual(r.lines[-1]["summary"]["items"], 3)
        r = self.run_("--key", "NOPE1234", K, "--cite", "nobody")
        self.assertEqual(r.code, 1, "a target that names no item is the agent's to fix")
        self.assertEqual([(ln.get("key"), ln.get("cite"), ln.get("code")) for ln in r.lines[:2]],
                         [("NOPE1234", None, "not_found"), (None, "nobody", "cite_not_found")])
        self.assertTrue(all("hint" in ln for ln in r.lines[:2]))
        self.assertEqual(r.lines[-1]["summary"], {"items": 1, "with_problems": 0, "by_code": {}})
        self.assertEqual(self.run_("--only", "missing_doi").code, 2, "--only is gone")
        self.assertEqual(self.run_("--key", "short").code, 2)

    def test_collections_in_the_trash_do_not_count(self):
        add(self.zot, "INTRASH1", itemType="journalArticle", title="Filed only in a trashed collection",
            DOI="10.1000/t1", url="https://pub.example/t1", collections=["COLL0009"])
        r = self.run_("--key", "INTRASH1")
        self.assertEqual(reported(r)["INTRASH1"]["collections"], [])
        for key in ("COLL0009", "NOPE0000"):
            r = self.run_("--collection", key)
            self.assertEqual((r.code, len(r.lines), r.lines[0]["code"], r.lines[0]["collection"]),
                             (1, 1, "collection_not_found", key))
            self.assertIn("hint", r.lines[0])

    def test_a_doi_org_url_counts_for_duplicates_not_for_the_doi_field(self):
        add(self.zot, "UUUUUUUU", itemType="journalArticle", title="The same paper, found by its url",
            url="https://doi.org/10.1000/A", abstractNote="x", date="2021")
        add(self.zot, "XXXXXXXX", itemType="journalArticle", title="A journal article carrying its arXiv DOI",
            DOI="10.48550/arXiv.2202.00002", url="https://arxiv.org/abs/2202.00002", abstractNote="x")
        found = problems(self.run_())
        self.assertEqual(found["UUUUUUUU"]["duplicate_of"], {"code": "duplicate_of", "by": "doi", "keys": [A, B]})
        self.assertEqual(found[A]["duplicate_of"]["keys"], [B, "UUUUUUUU"])
        self.assertEqual(found["UUUUUUUU"]["missing_doi"]["url"], "https://doi.org/10.1000/A", "the DOI field is empty")
        self.assertNotIn("url_not_record", found["UUUUUUUU"])
        self.assertIn("missing_doi", found["XXXXXXXX"], "an arXiv DOI is not the article's DOI")

    def test_proxies_known_by_their_form(self):
        add(self.zot, "PROXY001", itemType="journalArticle", title="Read through a library's EZproxy",
            DOI="10.1109/TMI.2024.1", abstractNote="x", url="https://ieeexplore-ieee-org.ezproxy.example.edu/document/1")
        add(self.zot, "PROXY002", itemType="journalArticle", title="Read through OCLC's hosted proxy",
            DOI="10.1016/j.x.2024.2", abstractNote="x", url="https://www-sciencedirect-com.lib.idm.oclc.org/science/article/pii/S1")
        add(self.zot, "PLAIN001", itemType="journalArticle", title="On the publisher's own site",
            DOI="10.1016/j.x.2024.3", abstractNote="x", url="https://www.proxy-science.example.com/article/3")
        found = problems(self.run_("--key", "PROXY001,PROXY002,PLAIN001"))
        self.assertEqual(found["PROXY001"]["url_not_record"]["patch"], {"url": "https://doi.org/10.1109/TMI.2024.1"})
        self.assertEqual(found["PROXY002"]["url_not_record"]["patch"], {"url": "https://doi.org/10.1016/j.x.2024.2"})
        self.assertNotIn("PLAIN001", found)

    def test_citation_keys_across_the_library(self):
        z = self.zot
        clean = {"itemType": "journalArticle", "abstractNote": "x", "date": "2021"}
        add(z, "NOCITE01", **clean, title="A paper nobody keyed yet", DOI="10.1000/n1", url="https://pub.example/n1",
            collections=["COLL0001"], citationKey="")
        add(z, "DUPCITE1", **clean, title="One paper keyed dupkey", DOI="10.1000/d1", url="https://pub.example/d1",
            collections=["COLL0001"], citationKey="dupkey")
        add(z, "DUPCITE2", **clean, title="Another paper keyed dupkey", DOI="10.1000/d2", url="https://pub.example/d2",
            citationKey="dupkey")
        add(z, "TEXCITE1", **clean, title="A paper keyed with an underscore", DOI="10.1000/t", url="https://pub.example/t",
            collections=["COLL0001"], citationKey="smith_2020")
        r = self.run_("--collection", "COLL0001")
        cites = {key: [p for p in line["problems"] if p["code"] == "citation_key"] for key, line in reported(r).items()}
        self.assertEqual(cites["NOCITE01"], [{"code": "citation_key", "problem": "missing"}])
        self.assertEqual(cites["DUPCITE1"], [{"code": "citation_key", "problem": "duplicate", "keys": ["DUPCITE2"]}],
                         "the other key is outside the scope, still found")
        self.assertEqual(cites["TEXCITE1"], [{"code": "citation_key", "problem": "tex_special", "suggested": "smith2020"}])
        self.assertNotIn("DUPCITE2", cites)
        self.assertEqual(r.lines[-1]["summary"]["by_code"]["citation_key"], 3)
        r = self.run_("--cite", "dupkey")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["keys"]), (1, "cite_ambiguous", ["DUPCITE1", "DUPCITE2"]))

    def test_the_whole_library_is_read_page_by_page(self):
        for i in range(130):
            add(self.zot, f"FILL{i:04d}", itemType="webpage", title=f"Filler page number {i}", url=f"https://x/{i}",
                collections=["COLL0002"])
        add(self.zot, "LATEDUP1", itemType="journalArticle", title="The last record in the library", DOI="10.1000/A",
            abstractNote="x", url="https://pub.example/l")
        found = problems(self.run_("--key", A))
        self.assertEqual(found[A]["duplicate_of"]["keys"], [B, "LATEDUP1"])
        self.assertEqual([(q["start"], q["limit"]) for _, _, q, _ in self.zot.requested("GET", f"{LIB}/items")],
                         [("0", "100"), ("100", "100")])

    def test_cannot_check(self):
        r = self.run_(base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, len(r.lines), r.lines[0]["code"]), (2, 1, "zotero_unreachable"))
        self.zot.disabled = True
        r = self.run_()
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "local_api_disabled"))

    def test_smoke(self):
        r = smoke("lint_items", "--base-url", self.zot.base_url, config=self.config)
        self.assertEqual(r.code, 1, r)
        self.assertEqual(r.lines[-1]["summary"]["items"], 10)
        self.assertTrue(all(set(line) == {"key", "citationKey", "title", "itemType", "collections", "problems"}
                            for line in r.lines[:-1]))


if __name__ == "__main__":
    unittest.main()
