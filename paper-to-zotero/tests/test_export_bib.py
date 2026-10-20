# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/export_bib.py against the fake Zotero: where the keys come from, chunking, order, citation-key trouble."""
import json
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, load, smoke
from p2zlib import run
from fake_zotero import FakeZotero, LIB

export = load("export_bib")


def entries(text):
    return [line.split("{", 1)[1].rstrip(",") for line in text.splitlines() if line.startswith("@")]


class ExportBib(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_collection("COLLROOT", "root")
        z.add_collection("COLLSUB1", "sub1", "COLLROOT")
        z.add_collection("COLLSUB2", "sub2", "COLLSUB1")
        z.add_collection("COLLGONE", "gone", "COLLROOT", deleted=True)
        z.add_collection("COLLUNDR", "under gone", "COLLGONE")
        z.add_collection("COLLELSE", "else")
        for key, cite, title, colls in (("KEY00001", "zhou2021handheld", "Handheld", ["COLLROOT"]),
                                        ("KEY00002", "liu2022progressive", "Progressive", ["COLLROOT", "COLLSUB1"]),
                                        ("KEY00003", "Abel2019first", "First", ["COLLSUB1"]),
                                        ("KEY00004", "", "No key yet", ["COLLSUB2"]),
                                        ("KEY00005", "dup2020twice", "Twice a", ["COLLSUB2"]),
                                        ("KEY00006", "dup2020twice", "Twice b", ["COLLSUB2"]),
                                        ("KEY00007", "lonely2018", "Lonely", []),
                                        ("KEY00008", "smith_2020", "TeX trouble", ["COLLSUB2"]),
                                        ("KEY00009", "gone2020", "In a trashed collection", ["COLLGONE", "COLLUNDR"])):
            z.add_item(key, itemType="journalArticle", title=title, citationKey=cite, collections=colls)
        z.add_item("ATTA0001", itemType="attachment", parentItem="KEY00001", title="PDF")
        z.add_item("NOTE0001", itemType="note", note="<p>standalone</p>", collections=["COLLELSE"])
        self.tmp = Path(tempfile.mkdtemp(prefix="export-bib-"))

    def run_(self, *argv, base_url=None, stdin=""):
        return call(export, *argv, "--base-url", base_url or self.zot.base_url, stdin=stdin)

    def summary(self, r):
        return r.err_lines[-1]["summary"]

    def record(self, name, rec):
        path = self.tmp / f"{name}.json"
        path.write_text(rec if isinstance(rec, str) else json.dumps(rec, indent=2), encoding="utf-8")
        return path

    def test_collection_top_level_only_and_ordered(self):
        r = self.run_("--collection", "COLLROOT")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(entries(r.out), ["liu2022progressive", "zhou2021handheld"])
        self.assertTrue(r.out.endswith("}\n"))
        self.assertNotIn("\n\n\n", r.out)
        self.assertEqual(len(r.err_lines), 1)
        self.assertEqual(self.summary(r), {"count": 2, "collections": ["COLLROOT"]})

    def test_a_standalone_note_is_skipped_not_a_problem(self):
        r = self.run_("--collection", "COLLELSE")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(entries(r.out), [])
        self.assertEqual(self.summary(r)["standalone"], [{"key": "NOTE0001", "itemType": "note"}])

    def test_recursive_walks_live_subcollections_and_reports_cite_trouble(self):
        r = self.run_("--collection", "COLLROOT", "--recursive")
        self.assertEqual(r.code, 1, r)
        # ordered case-insensitively by BibTeX key; KEY00002 appears once although it sits in two collections;
        # KEY00009 sits only in a trashed collection and one under it
        self.assertEqual(entries(r.out), ["Abel2019first", "dup2020twice", "dup2020twice", "KEY00004",
                                          "liu2022progressive", "smith_2020", "zhou2021handheld"])
        s = self.summary(r)
        self.assertEqual((s["count"], s["collections"]), (7, ["COLLROOT", "COLLSUB1", "COLLSUB2"]))
        self.assertEqual(s["missing"], ["KEY00004"])
        self.assertEqual(s["duplicates"], [{"citationKey": "dup2020twice", "keys": ["KEY00005", "KEY00006"]}])
        self.assertEqual(s["tex"], [{"key": "KEY00008", "citationKey": "smith_2020", "suggested": "smith2020"}])
        self.assertIn("hint", s)

    def test_collection_not_found_unknown_trashed_or_under_the_trash(self):
        for key in ("ZZZZZZZZ", "COLLGONE", "COLLUNDR"):
            r = self.run_("--collection", key)
            self.assertEqual((r.code, r.out), (1, ""), key)
            line = r.err_lines[-1]
            self.assertEqual((line["code"], line["collection"]), ("collection_not_found", key))
            self.assertIn("hint", line)

    def test_keys_cites_and_not_found(self):
        r = self.run_("--key", "KEY00007,ZZZZZZZZ", "--key", "KEY00001", "--cite", "liu2022progressive", "--key", "KEY00007")
        self.assertEqual(r.code, 1, r)
        self.assertEqual(entries(r.out), ["liu2022progressive", "lonely2018", "zhou2021handheld"])
        s = self.summary(r)
        self.assertEqual((s["count"], s["not_found"]), (3, ["ZZZZZZZZ"]))
        self.assertNotIn("missing", s)

    def test_cite_unresolved_is_listed_not_fatal(self):
        self.zot.search_sees_citekey = False
        r = self.run_("--cite", "nobody2099", "--cite", "dup2020twice,lonely2018")
        self.assertEqual(r.code, 1)
        self.assertEqual(entries(r.out), ["lonely2018"], "found by the fallback scan")
        scans = [q for _, _, q, _ in self.zot.requested("GET", f"{LIB}/items/top") if "itemKey" not in q]
        self.assertEqual(len(scans), 1, "one shared scan for both missed cites")
        unresolved = self.summary(r)["unresolved"]
        self.assertEqual([(u["cite"], u["code"]) for u in unresolved],
                         [("nobody2099", "cite_not_found"), ("dup2020twice", "cite_ambiguous")])
        self.assertEqual(unresolved[1]["keys"], ["KEY00005", "KEY00006"])

    def test_chunks_of_50(self):
        for i in range(120):
            self.zot.add_item(f"BULK{i:04d}", itemType="journalArticle", title=f"Bulk {i}", citationKey=f"bulk{i:04d}",
                              collections=["COLLELSE"])
        r = self.run_("--collection", "COLLELSE")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.summary(r)["count"], 120)
        calls = [q for _, _, q, _ in self.zot.requested("GET", f"{LIB}/items/top") if q.get("format") == "bibtex"]
        self.assertEqual([len(q["itemKey"].split(",")) for q in calls], [50, 50, 20])
        self.assertTrue(all(q["limit"] == "100" for q in calls))
        self.assertEqual(entries(r.out), sorted(entries(r.out), key=str.lower))
        self.assertEqual(len(entries(r.out)), 120)

    def test_records_and_out(self):
        found = lambda key: {"key": key, "code": "found", "from": run.fingerprint(run.inputs(run.Record("x", {}), "found"))}  # noqa: E731
        paths = [self.record("a", {"saved": {"key": "KEY00001"}}),
                 self.record("b", {"found": found("KEY00003")}),
                 self.record("c", {"item": {"title": "not in the library"}}),
                 self.record("d", {"saved": {"pending": True}, "found": found("KEY00007")}),
                 self.record("e", {"found": {"key": "KEY00005", "code": "found"}})]
        out_file = self.tmp / "ref.bib"
        r = self.run_(*paths, "--out", out_file)
        self.assertEqual(r.code, 1, r)
        self.assertEqual(r.out, "")
        self.assertEqual(entries(out_file.read_text(encoding="utf-8")), ["Abel2019first", "lonely2018", "zhou2021handheld"])
        s = self.summary(r)
        self.assertEqual(s["no_item_key"], ["c", "e"], "a found an older run left, without `from`, is not trusted")
        self.assertEqual((s["count"], s["out"]), (3, str(out_file)))

        r = self.run_(paths[0], paths[1])
        self.assertEqual(r.code, 0, r)
        self.assertEqual(entries(r.out), ["Abel2019first", "zhou2021handheld"])

    def test_a_bad_record_is_listed_and_the_rest_exported(self):
        good = self.record("good", {"saved": {"key": "KEY00001"}})
        for bad in (self.record("broken", "{not json"), self.record("list", [{"saved": {"key": "KEY00001"}}]),
                    self.tmp / "missing.json"):
            r = self.run_(good, bad)
            self.assertEqual((r.code, entries(r.out)), (1, ["zhou2021handheld"]), bad)
            self.assertEqual([(i["path"], i["code"]) for i in self.summary(r)["invalid"]], [(str(bad), "record_invalid")])

    def test_empty_collection_is_no_records(self):
        self.zot.add_collection("COLLNONE", "empty")
        r = self.run_("--collection", "COLLNONE")
        self.assertEqual((r.code, r.out, r.err_lines[-1]["code"]), (1, "", "no_records"))

    def test_arguments(self):
        self.assertEqual(self.run_(stdin='{"saved": {"key": "KEY00001"}}').code, 2, "records come as paths, not on stdin")
        self.assertEqual(self.run_("--recursive").code, 2)
        self.assertEqual(self.run_("--collection", "short").code, 2)
        self.assertEqual(self.run_("--key", "short").code, 2)

    def test_cannot_check(self):
        r = self.run_("--key", "KEY00001", base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.out, r.err_lines[-1]["code"]), (2, "", "zotero_unreachable"))
        self.zot.disabled = True
        r = self.run_("--collection", "COLLROOT")
        self.assertEqual((r.code, r.err_lines[-1]["code"]), (2, "local_api_disabled"))

    def test_smoke(self):
        r = smoke("export_bib", "--collection", "COLLROOT", "--base-url", self.zot.base_url)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(entries(r.out), ["liu2022progressive", "zhou2021handheld"])
        self.assertEqual(r.err_lines[-1]["summary"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
