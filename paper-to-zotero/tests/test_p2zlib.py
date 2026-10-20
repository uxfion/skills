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
        for key, title, ctype in (("A1", "Snapshot", "text/html"), ("A2", "Preprint (arXiv)", "application/pdf"),
                                  ("A3", "Full Text PDF", "application/pdf"), ("A4", "Accepted Version", "application/pdf")):
            self.fake.add_item(key, itemType="attachment", parentItem="PARENT01", title=title, contentType=ctype,
                               linkMode="imported_url", md5=key.lower())
        self.assertEqual([(a["key"], a["kind"], a["md5"]) for a in self.zot.attachments("PARENT01")],
                         [("A3", "published", "a3"), ("A4", "accepted", "a4"), ("A2", "preprint", "a2"), ("A1", "snapshot", "a1")])

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
        self.assertEqual(paper.attachment_title("preprint", "bioRxiv"), "Preprint (bioRxiv)")
        self.assertEqual(paper.attachment_title("preprint", parent_type="preprint"), "PDF")
        self.assertEqual(paper.kind_of_attachment({"title": "arXiv Fulltext PDF", "contentType": "application/pdf"}), "preprint")
        self.assertIsNone(paper.kind_of_attachment({"title": "Link", "linkMode": "linked_url"}))

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
