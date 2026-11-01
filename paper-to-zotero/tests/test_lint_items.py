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


def by_title(r):
    """{key: its duplicate_of by title} (an item may carry a duplicate_of by DOI beside it)."""
    return {key: p for key, line in reported(r).items() for p in line["problems"]
            if p["code"] == "duplicate_of" and p["by"] == "title"}


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
            collections=["COLL0001"], date="2021", url="https://x/a", abstractNote="x")
        add(z, B, itemType="journalArticle", title="A second record of that paper", DOI="10.1000/a",
            collections=["COLL0002"], date="2021", abstractNote="x")
        add(z, "WWWWWWWW", itemType="webpage", title="Project page", url="https://proxy.example/x")
        add(z, D, {"parsedDate": None}, itemType="conferencePaper", title="An old conference paper",
            date="十一月 23, 2021", collections=["COLL0001"])
        add(z, "CCCCCCCC", itemType="conferencePaper", title="A CVPR paper", DOI="10.1109/CVPR.2019.00453",
            abstractNote="x", date="2019", url="https://openaccess.thecvf.com/content_CVPR_2019/html/x.html")
        add(z, "NNNNNNNN", itemType="conferencePaper", title="A NeurIPS paper", DOI="10.52202/075280-3121",
            abstractNote="x", date="2023", url="http://dx.doi.org/10.52202/075280-3121")
        add(z, J, itemType="journalArticle", title="A journal paper", DOI="10.1000/j", abstractNote="x",
            publicationTitle="Comput Biol Med", journalAbbreviation="Computers in Biology and Medicine", date="2021")
        add(z, "PPPPPPPP", itemType="preprint", title="Same Title Different Version", DOI="10.48550/arXiv.2101.00001",
            abstractNote="x", date="2021")
        add(z, "QQQQQQQQ", itemType="journalArticle", title="Same title, different version", DOI="10.1000/q",
            extra="arXiv: 2101.00001", abstractNote="x", date="2021")
        add(z, K, itemType="journalArticle", title="A paper with nothing to tidy", DOI="10.1000/k", abstractNote="x",
            date="2021", url="https://doi.org/10.1000/k")
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
        att("FINAL002", "Published-IEEE", md5="f1", dateAdded="2024-06-01")
        att("ACCEPT01", "Accepted-IEEE", md5="c1")
        att("ACCEPT02", "Accepted-IEEE", md5="c2")
        r = self.run_("--key", T)
        got = [p for p in reported(r)[T]["problems"] if p["code"] in ("nonstandard_title", "label_clash", "superseded")]
        self.assertEqual(got, [
            {"code": "nonstandard_title", "why": "outside_scheme", "attachment": "OLDPDF01", "title": "Full Text PDF",
             "contentType": "application/pdf", "url": "https://ieeexplore.ieee.org/stamp/x", "host": "ieeexplore.ieee.org",
             "url_site": "IEEE", "filename": None, "md5": "o1", "doi": "10.1000/t"},
            {"code": "nonstandard_title", "why": "no_source", "attachment": "SNAP0001", "title": "Snapshot",
             "contentType": "text/html", "url": "https://www.sciencedirect.com/science/article/pii/S1",
             "host": "www.sciencedirect.com", "url_site": "Elsevier", "filename": None, "md5": None, "doi": "10.1000/t"},
            {"code": "label_clash", "title": "Published-IEEE", "attachments": ["FINAL001", "FINAL002"], "same_file": True},
            {"code": "label_clash", "title": "Snapshot-Elsevier", "attachments": ["SNAP0002", "SNAP0003"], "same_file": None},
            {"code": "label_clash", "title": "Accepted-IEEE", "attachments": ["ACCEPT01", "ACCEPT02"], "same_file": False},
            {"code": "superseded", "attachment": "ARXIV001", "title": "Preprint-arXiv-v1", "by": "ARXIV003",
             "by_title": "Preprint-arXiv-v3"}],
            "evidence and no proposed name, the proxy taken off; a link is no file; one md5 twice, two md5s, none")

    def test_the_whole_library(self):
        r = self.run_()
        self.assertEqual(r.code, 1, r)
        found, lines, summary = problems(r), reported(r), r.lines[-1]["summary"]
        self.assertEqual(found[A]["duplicate_of"], {"code": "duplicate_of", "by": "doi", "keys": [B]},
                         "a trashed copy is not a duplicate")
        self.assertEqual(by_title(r), {}, "P and Q share every title word, but their arXiv id found them; A's namesake is trashed")
        self.assertEqual((found["PPPPPPPP"]["duplicate_of"]["by"], found["PPPPPPPP"]["duplicate_of"]["keys"]),
                         ("arxiv", ["QQQQQQQQ"]))
        self.assertNotIn("superseded", found[A], "two sources side by side: no problem")
        self.assertIn("unfiled_webpage", found["WWWWWWWW"])
        self.assertEqual(set(found[D]), {"date_unparseable", "missing_doi", "missing_abstract", "no_identifier"})
        self.assertEqual(found[J]["abbreviation_misplaced"], {"code": "abbreviation_misplaced", "publicationTitle":
                         "Comput Biol Med", "journalAbbreviation": "Computers in Biology and Medicine"}, "no patch")
        self.assertEqual(found[A]["url_not_record"],
                         {"code": "url_not_record", "url": "https://x/a", "host": "x", "doi": "10.1000/A"})
        self.assertEqual(found["CCCCCCCC"]["url_not_record"],
                         {"code": "url_not_record", "url": "https://openaccess.thecvf.com/content_CVPR_2019/html/x.html",
                          "host": "openaccess.thecvf.com", "doi": "10.1109/CVPR.2019.00453"}, "a copy or not: the judge's")
        self.assertEqual(found[B]["url_not_record"], {"code": "url_not_record", "url": None, "host": None,
                         "doi": "10.1000/a", "patch": {"url": "https://doi.org/10.1000/a"}}, "an empty url is patched")
        self.assertNotIn("NNNNNNNN", found, "a dx.doi.org link is the DOI's url, a NeurIPS DOI's too")
        self.assertNotIn("url_not_record", found["PPPPPPPP"], "a preprint's url is its own")
        self.assertNotIn("TTTTTTTT", found)
        self.assertNotIn(K, found)
        self.assertEqual((lines[A]["collections"], lines[B]["collections"]), (["Medical"], ["Medical/Sub"]))
        self.assertEqual((lines[A]["citationKey"], lines[A]["itemType"], lines[A]["title"]),
                         ("aaaaaaaa", "journalArticle", "Paper about segmentation networks"))
        self.assertEqual((summary["items"], summary["with_problems"]), (10, len(found)))
        self.assertEqual((summary["by_code"]["duplicate_of"], summary["by_code"]["url_not_record"]), (4, 5),
                         "A, B by DOI and P, Q by arXiv id; url: A, B, C, J, Q")

    def test_title_candidates(self):
        z = self.zot
        add(z, "RESNETJA", itemType="journalArticle", title="Deep residual learning for image recognition",
            DOI="10.1000/r1", publicationTitle="Journal of Vision", date="2016-06", abstractNote="x",
            url="https://doi.org/10.1000/r1", creators=[{"creatorType": "author", "firstName": "Kaiming", "lastName": "He"}])
        z.add_item("RESNETPD", itemType="attachment", parentItem="RESNETJA", contentType="application/pdf", md5="r1",
                   title="Published-IEEE")
        z.add_item("RESNETZP", itemType="attachment", parentItem="RESNETJA", contentType="application/zip", md5="z1",
                   title="Published-IEEE")  # its structured package: not a file a judge compares
        add(z, "RESNETCP", itemType="conferencePaper", title="Deep Residual Learning for Image Recognition.", date="2016")
        add(z, "SEGMENT1", itemType="journalArticle", title="Deep learning for image segmentation", date="2020")
        add(z, "GANPAPER", itemType="conferencePaper", title="Generative adversarial nets", date="2014",
            creators=[{"creatorType": "author", "firstName": "Ian", "lastName": "Goodfellow"}])
        add(z, "GANPAGE1", itemType="webpage", title="Generative Adversarial Nets (Goodfellow, 2014)")
        add(z, "GANNET01", itemType="journalArticle", title="Generative adversarial network", date="2015")
        add(z, "GANNETS1", itemType="journalArticle", title="Generative Adversarial Networks", date="2019")
        found = by_title(self.run_())
        self.assertEqual(found["RESNETCP"], {"code": "duplicate_of", "by": "title", "paper": {
            "title": "Deep Residual Learning for Image Recognition.", "year": "2016", "first_author": None, "doi": None,
            "arxiv": None, "itemType": "conferencePaper", "venue": None, "attachments": []}, "candidates": [
            {"key": "RESNETJA", "title": "Deep residual learning for image recognition", "year": "2016", "first_author": "He",
             "doi": "10.1000/r1", "arxiv": None, "itemType": "journalArticle", "venue": "Journal of Vision",
             "similarity": 1.0, "attachments": ["Published-IEEE"]}]}, "case and a full stop aside, the same title")
        self.assertEqual([c["key"] for c in found["RESNETJA"]["candidates"]], ["RESNETCP"],
                         "image segmentation shares some words, not all")
        self.assertNotIn("SEGMENT1", found, "no other item holds every word of its title")
        self.assertEqual([c["key"] for c in found["GANPAGE1"]["candidates"]], ["GANPAPER"],
                         "the author and the year in a title count as the creator and the date")
        self.assertEqual([c["key"] for c in found["GANNET01"]["candidates"]], ["GANNETS1"],
                         "a word inside a longer one, as Zotero's quick search: network finds Networks")
        self.assertNotIn("GANNETS1", found, "and not the other way round")

    def test_candidates_beyond_ten_are_counted(self):
        for i in range(12):
            add(self.zot, f"ATTN{i:04d}", itemType="conferencePaper", title="Attention is all you need", date="2017")
        p = by_title(self.run_("--key", "ATTN0000"))["ATTN0000"]
        self.assertEqual((len(p["candidates"]), p["more"]), (10, 1), "11 others: 10 shown, the rest counted")
        self.assertNotIn("ATTN0000", [c["key"] for c in p["candidates"]])

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
