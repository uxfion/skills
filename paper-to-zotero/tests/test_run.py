# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/p2zlib/run.py (the work directory, records, when a block is done) and cli.main_records."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from helpers import call

from p2zlib import cli, run

ITEM = {"itemType": "journalArticle", "title": "Deep Residual Learning", "DOI": "10.1109/CVPR.2016.90"}


def work_dir():
    root = Path(tempfile.mkdtemp(prefix="p2z-work-"))
    (root / "records").mkdir()
    return run.Work(root)


def record(work, slug, data):
    path = work.records / f"{slug}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class Records(unittest.TestCase):
    def test_rewriting_a_record_keeps_its_mode(self):
        work = work_dir()
        path = record(work, "he2016deep", {"item": ITEM})
        os.chmod(path, 0o644)
        rec = run.read(path)
        rec["tags"] = []
        rec.save()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, "not mkstemp's 0600")
        self.assertEqual(json.loads(path.read_text())["tags"], [])
        self.assertFalse(rec.changed())

    def test_a_file_that_is_not_a_record(self):
        work = work_dir()
        bad = work.records / "bad.json"
        bad.write_text("[1, 2]", encoding="utf-8")
        for path in (bad, work.records / "missing.json"):
            with self.assertRaises(cli.Stop) as caught:
                run.read(path)
            self.assertEqual(caught.exception.code, "record_invalid")

    def test_slug_is_the_file_name_and_lists_are_lists(self):
        work = work_dir()
        rec = run.read(record(work, "x2020y", {"distinct_from": "ABCD1234", "collection": ["C1", "C2"]}))
        self.assertEqual((rec.slug, rec.keys_of("distinct_from"), rec.keys_of("collection"), rec.keys_of("none")),
                         ("x2020y", ["ABCD1234"], ["C1", "C2"], []))


class DoneRule(unittest.TestCase):
    def rec(self, **data):
        return run.Record(Path("/w/records/s.json"), {"item": dict(ITEM), **data})

    def test_absent_fresh_stale_incomplete(self):
        rec = self.rec()
        self.assertEqual(run.due(rec, "found"), "absent")
        run.stamp(rec, "found", {"code": "not_found"})
        self.assertIsNone(run.due(rec, "found"))
        rec["item"]["DOI"] = "10.1109/CVPR.2016.91"
        self.assertEqual(run.due(rec, "found"), "stale")
        run.stamp(rec, "found", {"code": "not_found"}, incomplete=["search"])
        self.assertEqual((run.due(rec, "found"), rec["found"]["incomplete"]), ("incomplete", ["search"]))

    def test_inputs_are_what_the_block_depends_on(self):
        rec = self.rec()
        run.stamp(rec, "found", {"code": "not_found"})
        run.stamp(rec, "checks", {"code": "ok"})
        rec["tags"] = [{"tag": "x", "type": 0}]
        self.assertIsNone(run.due(rec, "found"), "tags do not change a lookup")
        self.assertIsNone(run.due(rec, "checks"))
        rec["item"]["abstractNote"] = "An abstract."
        self.assertIsNone(run.due(rec, "found"), "nor does the abstract")
        self.assertEqual(run.due(rec, "checks"), "stale", "the preview is of the whole item")
        rec["distinct_from"] = ["ABCD1234"]
        self.assertEqual(run.due(rec, "found"), "stale", "a new distinct_from is a new lookup")
        run.stamp(rec, "found", {"code": "not_found"})
        rec["same_as"] = "ABCD1234"
        self.assertEqual(run.due(rec, "found"), "stale")

    def test_a_block_without_from_is_an_older_runs(self):
        rec = self.rec(found={"code": "near_match", "key": "OTHER001"}, saved={"key": "MINE0001"}, checks={"code": "ok"})
        self.assertEqual(run.old_format(rec), ["checks", "found"])
        self.assertEqual(run.due(rec, "found"), "absent")

    def test_item_key(self):
        rec = self.rec(found={"code": "near_match", "key": "OTHER001"})
        self.assertIsNone(run.item_key(rec), "an older run's found is not trusted")
        run.stamp(rec, "found", {"code": "found", "key": "THERE001"})
        self.assertEqual(run.item_key(rec), "THERE001")
        rec["item"]["title"] = "Another title"
        self.assertIsNone(run.item_key(rec), "a stale lookup is not trusted")
        rec["saved"] = {"pending": True}
        self.assertIsNone(run.item_key(rec), "a creation in flight has no key yet")
        rec["saved"] = {"key": "MINE0001", "version": 3}
        self.assertEqual(run.item_key(rec), "MINE0001")


class WorkDirectory(unittest.TestCase):
    def test_log_settings_and_files(self):
        work = work_dir()
        work.append({"event": "claim", "slug": "a", "result": "claimed", "none": None})
        work.append({"event": "try", "slug": "a"})
        with open(work.log, "a", encoding="utf-8") as fh:
            fh.write("not json\n")
        self.assertEqual([e["event"] for e in work.events()], ["claim", "try"])
        self.assertNotIn("none", work.events("claim")[0])
        work.set(downloads="/d", session="p2z")
        work.set(watcher_pid=12, session=None)
        self.assertEqual(work.settings(), {"downloads": "/d", "watcher_pid": 12})
        self.assertIsNone(work.file_of("a"))
        (work.records / "a.preprint.pdf").write_bytes(b"%PDF-1.4")
        self.assertEqual(work.file_of("a").name, "a.preprint.pdf")
        self.assertEqual(run.Work.of(work.records / "a.json").root, work.root)


class _Records:
    """A script on main_records: stamps `checks`; a record titled "boom" makes Zotero vanish."""

    def main(self, argv):
        def process(rec, ctx):
            if rec.item.get("title") == "boom":
                raise cli.Stop("zotero_unreachable", exit=cli.CANNOT, hint="gone")
            if run.due(rec, "checks") is None:
                return cli.skipped("done")
            run.stamp(rec, "checks", {"code": "ok"})
            return cli.ok()
        return cli.main_records("A probe.\n\nIt stamps checks.", process, argv, dry_run=True)


class _Writer(_Records):
    def main(self, argv):
        return cli.main_records("A probe.", lambda rec, ctx: cli.ok(), argv, all_valid=True)


class MainRecords(unittest.TestCase):
    def test_writes_back_skips_what_is_done_and_reports_bad_files(self):
        work = work_dir()
        a = record(work, "a", {"item": ITEM})
        bad = work.records / "bad.json"
        bad.write_text("{", encoding="utf-8")
        r = call(_Records(), a, bad)
        self.assertEqual(r.code, cli.ACT, r)
        self.assertEqual([(o.get("slug"), o["code"]) for o in r.lines[:2]], [("a", "ok"), ("bad", "record_invalid")])
        self.assertIn("checks", json.loads(a.read_text()))
        r = call(_Records(), a)
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["reason"]), (cli.OK, "skipped", "done"))

    def test_dry_run_writes_nothing_and_cannot_check_stops_the_rest(self):
        work = work_dir()
        a, boom, c = (record(work, s, {"item": {**ITEM, "title": t}}) for s, t in (("a", "x"), ("b", "boom"), ("c", "y")))
        r = call(_Records(), a, "--dry-run")
        self.assertNotIn("checks", json.loads(a.read_text()))
        self.assertTrue(r.lines[-1]["summary"]["dry_run"])
        r = call(_Records(), a, boom, c)
        self.assertEqual(r.code, cli.CANNOT)
        self.assertEqual([o["code"] for o in r.lines[:3]], ["ok", "zotero_unreachable", "not_run"])
        self.assertEqual(r.lines[-1]["summary"]["stopped"], "zotero_unreachable")
        self.assertNotIn("checks", json.loads(c.read_text()))

    def test_a_library_writer_does_nothing_when_a_file_is_bad(self):
        work = work_dir()
        a = record(work, "a", {"item": ITEM})
        bad = work.records / "bad.json"
        bad.write_text("{", encoding="utf-8")
        r = call(_Writer(), a, bad)
        self.assertEqual(r.code, cli.ACT)
        self.assertEqual([o.get("slug") for o in r.lines[:-1]], ["bad"])
        self.assertEqual(r.lines[-1]["summary"]["not_run"], 1)
        self.assertEqual(call(_Writer()).lines[0]["code"], "no_records")


if __name__ == "__main__":
    unittest.main()
