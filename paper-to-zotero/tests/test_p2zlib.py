# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for the shared library scripts/p2zlib: the cases every script shares are tested here, once."""
import json
import unittest
from unittest import mock

from helpers import call, closed_port, config_file
from fake_zotero import API_KEY, LIB, SERVER_ID, FakeZotero

from p2zlib import cli, config, paper, web, zotero


class Client(unittest.TestCase):
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

    def stop(self, fn, *args, **kwargs):
        with self.assertRaises(cli.Stop) as caught:
            fn(*args, **kwargs)
        return caught.exception

    # ---- reading ----

    def test_pages_reads_100_at_a_time_until_total_results(self):
        for i in range(230):
            self.fake.add_item(f"K{i:07d}", itemType="journalArticle", title=f"t{i}")
        rows = self.zot.pages(f"{LIB}/items/top")
        self.assertEqual(len(rows), 230)
        self.assertEqual([(q["start"], q["limit"]) for *_, q, _ in self.fake.requested("GET", f"{LIB}/items/top")],
                         [("0", "100"), ("100", "100"), ("200", "100")])
        self.fake.requests.clear()
        self.assertEqual(len(self.zot.pages(f"{LIB}/items/top", limit=120)), 120)
        self.assertEqual([q["limit"] for *_, q, _ in self.fake.requested("GET", f"{LIB}/items/top")], ["100", "20"])

    def test_a_page_that_is_not_a_list_is_an_error_not_half_a_listing(self):
        with mock.patch.object(self.zot, "_get", return_value=({"oops": 1}, {})):
            self.assertEqual(self.stop(self.zot.pages, f"{LIB}/items").code, "unexpected_response")

    def test_items_by_key_in_chunks_of_50_without_their_children(self):
        keys = [f"K{i:07d}" for i in range(120)]
        for k in keys:
            self.fake.add_item(k, itemType="journalArticle", title=k)
        self.fake.add_item("ATTACH01", itemType="attachment", parentItem=keys[0], title="PDF")
        found = self.zot.items(keys + ["MISSING1"])
        self.assertEqual(set(found), set(keys))
        self.assertEqual(len(self.fake.requested("GET", f"{LIB}/items")), 3)

    def test_children_filters_the_whole_library_answer(self):
        self.fake.add_item("PARENT01", itemType="journalArticle", title="p")
        self.fake.add_item("ATTACH01", itemType="attachment", parentItem="PARENT01", title="PDF")
        self.assertEqual([c["key"] for c in self.zot.children("PARENT01")], ["ATTACH01"])
        self.assertEqual(self.zot.children("NOPE0000"), [])

    def test_cites_search_first_then_one_shared_scan(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="One", citationKey="one2020")
        self.fake.add_item("ITEM0002", itemType="journalArticle", title="Two", citationKey="two2021")
        self.fake.add_item("DUP00001", itemType="journalArticle", title="Dup a", citationKey="dup")
        self.fake.add_item("DUP00002", itemType="journalArticle", title="Dup b", citationKey="dup")
        self.assertEqual(self.zot.resolve_cite("one2020"), "ITEM0001")
        self.assertEqual(self.fake.requested("GET", f"{LIB}/items/top"), [])
        self.fake.search_sees_citekey = False
        self.assertEqual(self.zot.resolve_cites(["one2020", "two2021", "none"]),
                         {"one2020": ["ITEM0001"], "two2021": ["ITEM0002"], "none": []})
        self.assertEqual(len(self.fake.requested("GET", f"{LIB}/items/top")), 1, "one scan for every cite the search missed")
        self.assertEqual(self.stop(self.zot.resolve_cite, "none").code, "cite_not_found")
        failure = self.stop(self.zot.resolve_cite, "dup")
        self.assertEqual((failure.code, failure.extra["keys"]), ("cite_ambiguous", ["DUP00001", "DUP00002"]))

    def test_targets_keep_the_order_and_name_an_item_once(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="One", citationKey="one2020")
        out = self.zot.targets(["ITEM0001", "OTHER001"], ["one2020", "none"])
        self.assertEqual([(k, c, f.code if f else None) for k, c, f in out],
                         [("ITEM0001", None, None), ("OTHER001", None, None), (None, "none", "cite_not_found")])

    def test_collection_tree_leaves_out_the_trash_and_what_is_under_it(self):
        self.fake.add_collection("C1AAAAAA", "医疗图像")
        self.fake.add_collection("C2AAAAAA", "超声", "C1AAAAAA")
        self.fake.add_collection("C3AAAAAA", "Old", deleted=True)
        self.fake.add_collection("C4AAAAAA", "Under old", "C3AAAAAA")
        self.fake.add_collection("C5AAAAAA", "Loop a", "C6AAAAAA")
        self.fake.add_collection("C6AAAAAA", "Loop b", "C5AAAAAA")
        tree = self.zot.collections()
        self.assertEqual({k: c["path"] for k, c in tree.items()}, {"C1AAAAAA": "医疗图像", "C2AAAAAA": "医疗图像/超声"})

    def test_attachments_rank_the_paper_first_and_carry_md5(self):
        self.fake.add_item("PARENT01", itemType="journalArticle", title="p")
        for key, title, ctype, added in (("A1", "Snapshot-IEEE", "text/html", "2024-01-01T00:00:00Z"),
                                         ("A2", "Preprint-arXiv-v2", "application/pdf", "2024-01-02T00:00:00Z"),
                                         ("A3", "Full Text PDF", "application/pdf", "2024-01-03T00:00:00Z"),
                                         ("A4", "Published-IEEE", "application/pdf", "2024-01-04T00:00:00Z")):
            self.fake.add_item(key, itemType="attachment", parentItem="PARENT01", title=title, contentType=ctype,
                               linkMode="imported_url", md5=key.lower(), dateAdded=added)
        self.assertEqual([(a["key"], a["version"], a["source"], a["standard"], a["md5"]) for a in self.zot.attachments("PARENT01")],
                         [("A4", "published", "IEEE", True, "a4"), ("A2", "preprint", "arXiv", True, "a2"),
                          ("A3", "unknown", None, False, "a3"), ("A1", "snapshot", "IEEE", True, "a1")])

    # ---- how replies become codes ----

    def test_unreachable_disabled_and_unexpected(self):
        dead = zotero.Zotero(f"http://127.0.0.1:{closed_port()}")
        failure = self.stop(dead.item, "ITEM0001")
        self.assertEqual((failure.code, failure.exit), ("zotero_unreachable", cli.CANNOT))
        self.fake.disabled = True
        failure = self.stop(self.zot.item, "ITEM0001")
        self.assertEqual((failure.code, failure.exit), ("local_api_disabled", cli.CANNOT))
        self.fake.disabled = False
        self.assertIsNone(self.zot.item("NOPE0000"))
        self.assertEqual(self.stop(self.zot.get, "/api/users/0/nothing").code, "unexpected_response")

    def test_write_headers_check_server_and_key_once(self):
        h = self.zot.write_headers(7)
        self.assertEqual((h["Zotero-Server-ID"], h["If-Unmodified-Since-Version"]), (SERVER_ID, "7"))
        self.zot.write_headers()
        self.assertEqual(len(self.fake.requested("GET", "/api/")), 1)
        with mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(config_file(key=None))}):
            self.assertEqual(self.stop(zotero.Zotero(self.fake.base_url).write_headers).code, "no_key")
        with mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(config_file(server_id="ELSEWHERE"))}):
            self.assertEqual(self.stop(zotero.Zotero(self.fake.base_url).write_headers).code, "server_mismatch")

    def test_update_retries_a_version_conflict_once(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="old")
        plans = []

        def plan(item):
            plans.append(item["version"])
            return {"title": "new"} if zotero.data(item)["title"] != "new" else None

        self.fake.bump_before_write = 1
        item, sent, retried = self.zot.update("ITEM0001", plan)
        self.assertEqual((sent, retried, self.fake.data("ITEM0001")["title"]), ({"title": "new"}, True, "new"))
        self.assertEqual(len(plans), 2, "planned again on the fresh item")
        self.fake.bump_before_write = 2
        self.fake.data("ITEM0001")["title"] = "old"
        self.assertEqual(self.stop(self.zot.update, "ITEM0001", plan).code, "version_conflict")
        self.assertEqual(self.stop(self.zot.update, "NOPE0000", plan).code, "not_found")

    def test_write_denied_and_failed_keep_zoteros_words(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="old")
        self.fake.write_status = (403, "Library is read-only")
        failure = self.stop(self.zot.update, "ITEM0001", lambda it: {"title": "x"})
        self.assertEqual((failure.code, failure.extra["detail"]), ("write_denied", "Library is read-only"))
        self.fake.write_status = (500, "boom")
        self.assertEqual(self.stop(self.zot.update, "ITEM0001", lambda it: {"title": "x"}).code, "write_failed")
        self.fake.write_status = (401, "no")
        self.assertEqual(self.stop(self.zot.update, "ITEM0001", lambda it: {"title": "x"}).exit, cli.CANNOT)

    def test_post_gives_one_result_per_object_in_order(self):
        self.fake.add_item("ITEM0001", version=5, itemType="journalArticle", title="a")
        self.fake.reject = lambda obj: (400, "bad title") if obj.get("title") == "bad" else None
        objs = [{"itemType": "note", "note": "x"}] * 3 + [{"key": "ITEM0001", "version": 4, "title": "b"},
                                                          {"key": "ITEM0001", "version": 5, "title": "a"},
                                                          {"itemType": "journalArticle", "title": "bad"}]
        results = self.zot.post(objs * 10)
        self.assertEqual(len(results), 60)
        self.assertEqual([next(iter(r)) for r in results[:6]], ["ok", "ok", "ok", "failed", "unchanged", "failed"])
        self.assertEqual(results[3]["failed"]["status"], 412)
        self.assertEqual(len(self.fake.requested("POST")), 2, "50 objects a request")
        self.fake.write_status = (500, "down")
        self.assertEqual({r["failed"]["code"] for r in self.zot.post(objs)}, {"write_failed"})

    def test_post_reads_a_stale_object_again_and_replans_it_once(self):
        self.fake.add_item("ITEM0001", version=5, itemType="journalArticle", title="a")
        self.fake.add_item("ITEM0002", version=6, itemType="journalArticle", title="b")
        objs = [{"key": "ITEM0001", "version": 4, "title": "a2"}, {"key": "ITEM0002", "version": 1, "title": "b"}]
        self.assertEqual(self.zot.post(objs)[0]["failed"]["code"], "version_conflict")
        seen = []

        def replan(i, item):
            seen.append((i, item["version"]))
            return {"key": item["key"], "version": item["version"], "title": "a2"} if i == 0 else None

        results = self.zot.post(objs, replan=replan)
        self.assertEqual(seen, [(0, 5), (1, 6)])
        self.assertEqual((results[0]["ok"]["data"]["title"], results[0]["retried"]), ("a2", True))
        self.assertEqual(results[1], {"unchanged": True, "retried": True})

    def test_trash_and_restore(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="a")
        self.assertEqual(self.zot.trash("ITEM0001")["code"], "ok")
        self.assertEqual(self.zot.trash("ITEM0001")["reason"], "already_trashed")
        self.assertEqual(self.zot.trash("ITEM0001", restore=True)["code"], "ok")
        self.assertNotIn("deleted", self.fake.data("ITEM0001"))

    def test_create_collection(self):
        key = self.zot.create_collection("tmp")
        self.assertEqual(self.fake.collections[key]["data"]["name"], "tmp")

    def test_the_key_never_reaches_the_output(self):
        self.fake.add_item("ITEM0001", itemType="journalArticle", title="a")
        self.fake.write_status = (500, "boom")
        r = call(_Probe(self.fake.base_url), config=self.cfg)   # call() itself asserts the key is absent
        self.assertEqual((r.code, r.lines[0]["code"]), (cli.ACT, "write_failed"))
        self.assertNotIn(API_KEY, r.out + r.err)


class Lookup(unittest.TestCase):
    """Zotero.lookup: is this paper in the library, and what is only like it."""
    A, ATT, B, C, D, E, F = "AAAAAAA1", "AAAAATT1", "BBBBBBB1", "CCCCCCC1", "DDDDDDD1", "EEEEEEE1", "FFFFFFF1"

    @classmethod
    def setUpClass(cls):
        cls.fake = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.fake.close()

    def setUp(self):
        z, self.zot = self.fake, zotero.Zotero(self.fake.base_url)
        z.reset()
        z.add_item(self.A, version=894, itemType="journalArticle", date="2022-09", DOI="10.1109/JBHI.2022.3142076",
                   title="Progressive Residual Learning With Memory Upgrade for Ultrasound Image Blind Super-Resolution",
                   url="https://doi.org/10.1109/JBHI.2022.3142076", citationKey="liu2022progressive", collections=["C1AAAAAA"],
                   tags=[{"tag": "JBHI", "type": 0}])
        z.add_item(self.ATT, itemType="attachment", parentItem=self.A, title="PDF", linkMode="imported_url",
                   contentType="application/pdf", filename="liu.pdf", md5="abc123")
        z.add_item(self.B, itemType="preprint", title="Denoising Diffusion Probabilistic Models", date="2020",
                   archiveID="arXiv:2006.11239", url="https://arxiv.org/abs/2006.11239v2", citationKey="ho2020denoising")
        z.add_item(self.C, itemType="conferencePaper", title="Deep Residual Learning for Image Recognition", date="2016")
        z.add_item(self.D, itemType="journalArticle", title="Something Else Entirely", date="2019")
        z.add_item(self.E, itemType="journalArticle", title="Deep Residual Learning for Image Recognition: Extended", date="2017")
        z.add_item(self.F, itemType="preprint", title="Pair Paper Title", date="2024", DOI="10.48550/arXiv.2401.00001",
                   archiveID="arXiv:2401.00001", url="https://arxiv.org/abs/2401.00001")

    def look(self, distinct_from=(), same_as=None, **item):
        found, near = self.zot.lookup(item, distinct_from=distinct_from, same_as=same_as)
        return found, [(m["key"], m["reason"]) for m in near]

    def test_a_doi_confirms_and_describes_what_the_library_holds(self):
        found, near = self.look(DOI="https://doi.org/10.1109/JBHI.2022.3142076", title="x")
        self.assertEqual((found["code"], found["key"], found["matched_by"], near), ("found", self.A, "doi", []))
        self.assertEqual((found["citationKey"], found["collections"], found["date"]), ("liu2022progressive", ["C1AAAAAA"], "2022-09"))
        self.assertEqual([(a["key"], a["version"], a["standard"], a["md5"], a["title"]) for a in found["attachments"]],
                         [(self.ATT, "unknown", False, "abc123", "PDF")])

    def test_an_arxiv_id_confirms_unless_the_item_has_its_own_doi(self):
        for item in ({"archiveID": "arXiv:2401.00001"}, {"DOI": "10.48550/arXiv.2401.00001v2"}):
            found, near = self.look(title="x", **item)
            self.assertEqual((found["code"], found["key"], found["matched_by"]), ("found", self.F, "arxiv"), item)
        found, near = self.look(itemType="journalArticle", DOI="10.1000/pub.1", title="Pair Paper Title", extra="arXiv: 2401.00001")
        self.assertEqual(found["code"], "not_found")
        self.assertEqual(near[0][0], self.F)
        self.assertTrue(near[0][1].startswith("preprint/published pair"))

    def test_a_title_never_confirms(self):
        found, near = self.look(title="Deep Residual Learning for Image Recognition")
        self.assertEqual(found["code"], "not_found")
        self.assertEqual(near, [(self.C, "same title; no identifier confirms it"),
                                (self.E, "the library title contains this title")], "the same title first")
        found, near = self.look(DOI="10.1000/pub.2", title="Pair Paper Title")
        self.assertEqual(near[0][0], self.F)
        self.assertIn("same title, another DOI", near[0][1])
        self.assertEqual(self.look(title="Nothing like this at all")[1], [])
        self.assertEqual(self.look(title="Nothing like this at all")[0]["searched"][0]["qmode"], "titleCreatorYear")

    def test_distinct_from_drops_items_at_every_step(self):
        self.assertEqual(self.look([self.A], DOI="10.1109/JBHI.2022.3142076", title="Deep Residual Learning for Image Recognition")[1][0][0],
                         self.C, "the DOI hit dropped: the title step")
        self.assertEqual(self.look([self.C], title="Deep Residual Learning for Image Recognition")[1], [(self.E, "the library title contains this title")])
        found, near = self.look([self.C, self.E], title="Deep Residual Learning for Image Recognition")
        self.assertEqual((found["code"], near), ("not_found", []))
        found, near = self.look([self.F], archiveID="arXiv:2401.00001", title="Something Else Entirely")
        self.assertEqual((found["code"], near[0][0]), ("not_found", self.D))

    def test_same_as_settles_it(self):
        found, near = self.look(same_as=self.C, title="Deep Residual Learning for Image Recognition")
        self.assertEqual((found["code"], found["key"], found["matched_by"], near), ("found", self.C, "same_as", []))
        with self.assertRaises(cli.Stop) as caught:
            self.look(same_as="NOPE0000", title="x")
        self.assertEqual(caught.exception.code, "not_found")

    def test_a_hit_on_a_child_counts_for_its_parent(self):
        self.fake.add_item("NOTE0001", itemType="note", parentItem=self.D, note="see 10.1000/only.in.a.note")
        found, near = self.look(DOI="10.1000/only.in.a.note", title="y")
        self.assertEqual(found["code"], "not_found", "the parent's own fields do not carry the DOI")
        self.assertEqual(found["searched"][0]["hits"], 1)

    def test_files_by_md5_newest_first_until_each_has_a_hit(self):
        self.fake.add_item("ATTOLD01", itemType="attachment", parentItem=self.B, md5="dup", dateAdded="2020-01-01T00:00:00Z")
        self.fake.add_item("ATTNEW01", itemType="attachment", parentItem=self.C, md5="dup", dateAdded="2026-01-01T00:00:00Z")
        self.fake.add_item("LOOSE001", itemType="attachment", md5="loose")
        out = self.zot.files_by_md5(["DUP", "loose", "abc123", "none"])
        self.assertEqual(out["dup"]["attachment"], "ATTNEW01", "the newest attachment with that md5")
        self.assertEqual((out["abc123"]["parent"], out["abc123"]["citationKey"]), (self.A, "liu2022progressive"))
        self.assertEqual((out["loose"]["parent"], out["loose"]["title"]), (None, None))
        self.assertNotIn("none", out)


class _Probe:
    """A script whose write fails: its line must not carry the key it sent."""

    def __init__(self, base):
        self.base = base

    def main(self, argv):
        return cli.run(lambda: zotero.Zotero(self.base).update("ITEM0001", lambda it: {"title": "b"}))


class Skeleton(unittest.TestCase):
    def test_stop_is_keyword_only_and_its_line_puts_code_after_the_head(self):
        with self.assertRaises(TypeError):
            cli.Stop("x", 2, "a hint")
        line = cli.Stop("x", exit=2, hint="h", detail="d").line(key="K")
        self.assertEqual(list(line), ["key", "code", "detail", "hint"])

    def test_finish_counts_and_exits(self):
        with mock.patch("sys.stdout") as out:
            self.assertEqual(cli.finish([cli.ok(), cli.skipped("unchanged")]), cli.OK)
            self.assertEqual(cli.finish([cli.ok(), {"code": "not_found"}]), cli.ACT)
            stop = cli.Stop("key_rejected", exit=cli.CANNOT)
            self.assertEqual(cli.finish([{"code": "not_run"}], stopped=stop), cli.CANNOT)
        last = json.loads(out.write.call_args_list[-2][0][0])
        self.assertEqual(last, {"summary": {"total": 1, "ok": 0, "skipped": 0, "failed": 1, "stopped": "key_rejected"}})

    def test_split_takes_repeats_and_commas(self):
        self.assertEqual(cli.split(["A,B", "C", " B "]), ["A", "B", "C"])


class Rules(unittest.TestCase):
    def test_identifiers(self):
        self.assertEqual(paper.identifiers({"DOI": "https://doi.org/10.1109/CVPR.2016.90"}), ("10.1109/cvpr.2016.90", ""))
        self.assertEqual(paper.identifiers({"url": "https://doi.org/10.1109/TMI.2024.1"}), ("10.1109/tmi.2024.1", ""))
        self.assertEqual(paper.identifiers({"DOI": "10.48550/arXiv.2303.11366"}), ("", "2303.11366"))
        self.assertEqual(paper.identifiers({"extra": "tldr\narXiv: 2303.11366v2"}), ("", "2303.11366"))
        self.assertEqual(paper.identifiers({"archiveID": "arXiv:2303.11366", "url": "https://arxiv.org/abs/9999.99999"}),
                         ("", "2303.11366"))
        self.assertEqual(paper.identifiers({"DOI": "not a doi"}), ("", ""))
        self.assertEqual(paper.doi_of({"url": "https://doi.org/10.1/x"}, url=False), "")

    def test_titles_compare_in_any_script(self):
        self.assertEqual(paper.norm_title("Deep  Residual-Learning!"), "deepresiduallearning")
        self.assertGreater(paper.title_similarity("基于深度学习的超声图像分割", "基于深度学习的超声图像分割方法"), 0.9)
        self.assertEqual(paper.title_similarity("", "x"), 0.0)

    def test_file_kinds(self):
        self.assertEqual([paper.kind_of_file(n) for n in ("a.pdf", "a.accepted.pdf", "a.preprint.pdf", "a.supplement.pdf",
                                                          "a.html", "a.txt")],
                         ["published", "accepted", "preprint", "supplement", "snapshot", None])

    def test_attachment_titles_round_trip(self):
        for version, source, detail, title in (("Preprint", "arXiv", ["v7"], "Preprint-arXiv-v7"),
                                               ("accepted", "Europe PMC", [], "Accepted-Europe_PMC"),
                                               ("Published", "T-CAIREM", ["abstract booklet p66"],
                                                "Published-T_CAIREM-abstract_booklet_p66"),
                                               ("Preprint", "OpenReview", ["ICLR 2027 submission"],
                                                "Preprint-OpenReview-ICLR_2027_submission"),
                                               ("Unknown", None, ["v2"], "Unknown")):  # detail only after a source
            self.assertEqual(paper.label_title(version, source, detail), title)
            parsed = paper.parse_title(title)
            self.assertEqual(paper.label_title(parsed["version"], parsed["source"], parsed["detail"]), title)
        self.assertEqual(paper.parse_title("Published-Elsevier-in_press"),
                         {"version": "published", "source": "Elsevier", "detail": ["in_press"]})
        for other in ("PDF", "Full Text PDF", "Preprint (arXiv)", "Accepted manuscript", "published-IEEE", "Published-",
                      "Published--IEEE", "Snapshot (Nature)"):
            self.assertIsNone(paper.parse_title(other), other)
        with self.assertRaises(ValueError):
            paper.label_title("Proof", "IEEE")

    def test_attachment_label_reads_only_the_scheme(self):
        pdf, html = "application/pdf", "text/html"
        cases = (({"title": "Accepted-CVF", "contentType": pdf}, ("accepted", "CVF", True)),
                 ({"title": "Snapshot", "contentType": html, "linkMode": "imported_url"}, ("snapshot", None, True)),
                 ({"title": "Supplement-Nature-source_data", "contentType": "application/zip"}, ("supplement", "Nature", True)),
                 ({"title": "Accepted Version", "contentType": pdf}, ("unknown", None, False)),   # Zotero's words: no evidence
                 ({"title": "arXiv Fulltext PDF", "contentType": pdf}, ("unknown", None, False)),
                 ({"title": "ScienceDirect Snapshot", "contentType": html}, ("snapshot", None, False)),
                 ({"title": "Published-IEEE", "linkMode": "linked_url"}, (None, None, None)),
                 ({"title": "data.xlsx", "contentType": "application/vnd.ms-excel"}, (None, None, None)))
        for data, want in cases:
            got = paper.attachment_label(data)
            self.assertEqual((got["version"], got["source"], got["standard"]), want, data)

    def test_proposals_go_by_the_route_and_the_site(self):
        cases = (("publisher", "https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=1", None, "Published-IEEE"),
                 ("open", "https://arxiv.org/pdf/2303.11366v4", None, "Preprint-arXiv-v4"),
                 ("open", "https://www.biorxiv.org/content/10.1101/1v2.full.pdf", None, "Preprint-bioRxiv"),
                 ("open", "https://openaccess.thecvf.com/content/x.pdf", None, "Unknown-CVF"),  # not by the link's label
                 ("accepted", "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/pdf/a.pdf", None, "Accepted-PMC"),
                 ("preprint", "https://arxiv.org/pdf/hep-th/9901001v1", None, "Preprint-arXiv-v1"),
                 ("discovery", "https://www.sciencedirect.com/science/article/pii/S1/pdfft", None, "Unknown-Elsevier"),
                 ("start", "https://repository.example.edu/a.pdf", "accepted", "Accepted"),
                 ("snapshot", "https://www.nature.com/articles/x", None, "Snapshot-Nature"),
                 (None, None, None, "Unknown"))
        for route, url, given, title in cases:
            self.assertEqual(paper.proposal(route, url, given)["title"], title, (route, url))
        self.assertEqual(paper.proposal("open", "https://arxiv.org/pdf/2303.11366v12")["detail"], ["v12"])

    def test_order_and_replacement(self):
        def att(key, title, added, ctype="application/pdf"):
            return {"key": key, "dateAdded": added, **paper.attachment_label({"title": title, "contentType": ctype})}
        atts = [att("V1", "Preprint-arXiv-v1", "2024-01-01"), att("V10", "Preprint-arXiv-v10", "2023-01-01"),
                att("CVF", "Accepted-CVF", "2024-02-01"), att("PRESS", "Accepted-Nature-in_press", "2024-03-01"),
                att("FINAL", "Published-Nature", "2024-01-15"), att("OLD", "PDF", "2020-01-01"),
                att("OLD2", "Full Text PDF", "2021-01-01"), att("S1", "Snapshot-Elsevier", "2024-01-01", "text/html"),
                att("S2", "Snapshot-Elsevier", "2024-05-01", "text/html"), att("SUP", "Supplement-Nature", "2024-01-01"),
                att("SUPD", "Supplement-Nature-source_data", "2024-01-02"), att("U", "Unknown", "2024-06-01"),
                att("NOV", "Preprint-arXiv", "2024-07-01")]  # its vN not known
        self.assertEqual([a["key"] for a in paper.ordered(atts)],
                         ["FINAL", "CVF", "PRESS", "V10", "V1", "NOV", "U", "OLD2", "OLD", "SUPD", "SUP", "S2", "S1"])
        self.assertEqual(sorted((a["key"], b["key"]) for a, b in paper.superseded(atts)),
                         [("PRESS", "FINAL"), ("S1", "S2"), ("V1", "V10")],
                         "v10 beats v1 as a number; a file without a vN beside v10 is undecided: both stay")
        published = att("PUB", "Published-arXiv", "2023-01-01")  # a higher version still decides without a vN
        self.assertIn(("V10", "PUB"), [(a["key"], b["key"]) for a, b in paper.superseded(atts + [published])])

    def test_tags_dedupe_keeping_the_last(self):
        tags, problems, warnings = paper.normalize_tags(["a", {"tag": "a", "type": 1}, {"tag": "b", "type": True}, ""])
        self.assertEqual(tags, [{"tag": "a", "type": 1}])
        self.assertEqual(len(problems), 2)
        self.assertEqual(len(warnings), 1)

    def test_cite_problems(self):
        out = paper.cite_problems({"A": {"citationKey": "x_1"}, "B": {"citationKey": "dup"}, "C": {"citationKey": "dup"},
                                   "D": {}})
        self.assertEqual(out, {"missing": ["D"], "duplicates": [{"citationKey": "dup", "keys": ["B", "C"]}],
                               "tex": [{"key": "A", "citationKey": "x_1", "suggested": "x1"}]})

    def test_creators(self):
        self.assertEqual(paper.creator_problems([{"creatorType": "author", "lastName": "Li"}], {"author"}), [])
        self.assertEqual(len(paper.creator_problems([{"creatorType": "x", "name": "Li"}, {"creatorType": "author"}],
                                                    {"author"})), 2)


class Web(unittest.TestCase):
    def test_proxy_hosts_round_trip(self):
        proxy = "proxy.example.edu"
        for host in ("ieeexplore.ieee.org", "www.sciencedirect-x.com"):
            self.assertEqual(web.original_host(web.proxied_host(host, proxy), proxy), host)
        self.assertEqual(web.unproxy("https://ieeexplore-ieee-org.proxy.example.edu/document/1?x=1", proxy),
                         "https://ieeexplore.ieee.org/document/1?x=1")
        self.assertEqual(web.unproxy("https://www.nature.com/a", proxy), "https://www.nature.com/a")
        self.assertTrue(web.is_proxy_host("ieeexplore-ieee-org.proxy.example.edu", proxy))
        self.assertTrue(web.is_proxy_host("www-x-com.ezproxy.other.edu", proxy))
        self.assertFalse(web.is_proxy_host("www.nature.com", proxy))

    def test_the_configured_proxy_is_read_from_the_config(self):
        cfg = config_file(institution={"proxy": ".Proxy.Example.EDU "})
        with mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(cfg)}):
            self.assertEqual(config.institution()["proxy"], "proxy.example.edu")
            self.assertTrue(web.is_proxy_host("a-b-org.proxy.example.edu"))

    def test_a_429_stops_the_host(self):
        pacer = web.Pacer()
        pacer.stop("api.crossref.org", 30.0)
        with self.assertRaises(web.Blocked) as caught:
            pacer.wait("api.crossref.org")
        self.assertEqual(caught.exception.retry_after, 30.0)

    def test_retry_after(self):
        self.assertEqual(web.retry_after({"Retry-After": "12"}), 12.0)
        self.assertIsNone(web.retry_after({}))


class Config(unittest.TestCase):
    def test_strict_and_lenient(self):
        bad = config_file()
        bad.write_text("{not json", encoding="utf-8")
        with mock.patch.dict("os.environ", {"PAPER_TO_ZOTERO_CONFIG": str(bad)}):
            with self.assertRaises(cli.Stop) as caught:
                config.read()
            self.assertEqual(caught.exception.code, "config_unreadable")
            self.assertEqual(config.read(strict=False), {})
            self.assertEqual(config.institution(), {"proxy": None, "discovery": None})


if __name__ == "__main__":
    unittest.main()
