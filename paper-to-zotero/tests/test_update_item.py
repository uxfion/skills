# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/update_item.py against the fake Zotero."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import call, closed_port, config_file, load, smoke
from fake_zotero import FakeZotero

JOURNAL, CONF, NOTE, ATT, DUP1, DUP2 = "JOURNAL1", "CONFPAP1", "NOTE0001", "ATTACH01", "DUPKEY01", "DUPKEY02"
update = load("update_item")


def moves_pmid_line(it):
    """Zotero moves an Extra line it has an empty field for into that field."""
    d = it["data"]
    keep = []
    for line in (d.get("extra") or "").splitlines():
        m = re.fullmatch(r"PMID:\s*(\d+)", line)
        if m and not d.get("PMID"):
            d["PMID"] = m.group(1)
        else:
            keep.append(line)
    d["extra"] = "\n".join(keep)


def changes_type_to_conference(it):
    """Zotero's type change: a base field goes to the type's own field, a field the type lacks goes to Extra."""
    d = it["data"]
    if d["itemType"] != "conferencePaper":
        return
    if "publicationTitle" in d:
        d.setdefault("proceedingsTitle", d.pop("publicationTitle"))
    moved = [f"{f}: {d.pop(f)}" for f in ("journalAbbreviation", "volume") if f in d]
    d["extra"] = "\n".join(filter(None, [d.get("extra"), *moved]))


class UpdateItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zot = FakeZotero()
        cls.config = config_file()
        cls.tmp = Path(tempfile.mkdtemp(prefix="p2z-update-"))

    @classmethod
    def tearDownClass(cls):
        cls.zot.close()

    def setUp(self):
        z = self.zot
        z.reset()
        z.add_item(JOURNAL, version=10, itemType="journalArticle", title="A journal paper", publicationTitle="Old Journal",
                   journalAbbreviation="Old J.", volume="12", pages="1-10", date="2022", extra="",
                   citationKey="liu2022paper", creators=[{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}])
        z.add_item(CONF, version=11, itemType="conferencePaper", title="A conference paper", proceedingsTitle="Proc. Old",
                   conferenceName="OLDCONF", date="2021", citationKey="chen2021conf")
        z.add_item(NOTE, version=12, itemType="note", parentItem=JOURNAL, note="<p>a note</p>")
        z.add_item(ATT, version=13, itemType="attachment", parentItem=JOURNAL, title="Full Text PDF",
                   linkMode="imported_url", contentType="application/pdf")
        z.add_item(DUP1, version=14, itemType="journalArticle", title="Dup one", citationKey="dupkey")
        z.add_item(DUP2, version=15, itemType="journalArticle", title="Dup two", citationKey="dupkey")

    def run_(self, *argv, base_url=None, config=None):
        return call(update, *argv, "--base-url", base_url or self.zot.base_url, config=config or self.config)

    def patches(self):
        return [(p.rsplit("/", 1)[1], json.loads(body)) for _, p, _, body in self.zot.requested("PATCH")]

    def patch_file(self, obj):
        path = Path(tempfile.mkstemp(suffix=".json", dir=self.tmp)[1])
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return path

    def test_set_writes_what_differs_and_reads_it_back(self):
        r = self.run_("--key", JOURNAL, "--set", "date=2023", "--set", "DOI= 10.1109/CVPR.2023.1 ", "--set", "pages=1-10")
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual(line, {"key": JOURNAL, "code": "ok",
                                "changes": {"date": {"from": "2022", "to": "2023"}, "DOI": {"from": "", "to": "10.1109/CVPR.2023.1"}},
                                "mapped_fields": {}, "fields_to_extra": {}, "applied": ["date", "DOI"], "normalized": {},
                                "version_before": 10, "version_after": line["version_after"], "retried": False})
        self.assertGreater(line["version_after"], 10)
        self.assertEqual(r.lines[-1], {"summary": {"total": 1, "ok": 1, "skipped": 0, "failed": 0}})
        self.assertEqual(self.patches(), [(JOURNAL, {"date": "2023", "DOI": "10.1109/CVPR.2023.1"})])
        self.assertEqual(self.zot.data(JOURNAL)["DOI"], "10.1109/CVPR.2023.1")

    def test_rerun_is_skipped_unchanged(self):
        self.run_("--key", JOURNAL, "--set", "date=2023")
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["retried"]), ("skipped", "unchanged", False))
        self.assertNotIn("hint", r.lines[0])
        self.assertEqual(r.lines[-1]["summary"], {"total": 1, "ok": 0, "skipped": 1, "failed": 0})
        self.assertEqual(len(self.patches()), 1)

    def test_every_item_named_gets_the_same_set(self):
        r = self.run_("--key", JOURNAL, "--cite", "chen2021conf", "--set", "date=2024")
        self.assertEqual(r.code, 0, r)
        self.assertEqual([(o["key"], o.get("cite"), o["code"]) for o in r.lines[:2]],
                         [(JOURNAL, None, "ok"), (CONF, "chen2021conf", "ok")])
        self.assertEqual(self.patches(), [(JOURNAL, {"date": "2024"}), (CONF, {"date": "2024"})])

    def test_base_name_goes_to_the_types_own_field(self):
        r = self.run_("--key", CONF, "--set", "publicationTitle=Proc. CVPR 2023")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["mapped_fields"], {"publicationTitle": "proceedingsTitle"})
        self.assertEqual(r.lines[0]["applied"], ["proceedingsTitle"])
        self.assertEqual(self.patches(), [(CONF, {"proceedingsTitle": "Proc. CVPR 2023"})])

    def test_type_change_lists_the_fields_zotero_moves_to_extra(self):
        r = self.run_("--key", JOURNAL, "--set", "itemType=conferencePaper", "--set", "conferenceName=CVPR", "--dry-run")
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual(line["fields_to_extra"], {"journalAbbreviation": "Old J.", "volume": "12"},
                         "publicationTitle rides to proceedingsTitle; pages, date, title stay")
        self.assertEqual(line["changes"], {"itemType": {"from": "journalArticle", "to": "conferencePaper"},
                                           "conferenceName": {"from": "", "to": "CVPR"}})
        self.assertEqual(self.zot.writes(), [])

        self.zot.on_write = changes_type_to_conference
        r = self.run_("--key", JOURNAL, "--set", "itemType=conferencePaper", "--set", "conferenceName=CVPR")
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual(line["applied"], ["itemType", "conferenceName"])
        self.assertEqual(line["extra"], {"from": "", "to": "journalAbbreviation: Old J.\nvolume: 12"},
                         "an Extra Zotero changed on its own is shown")
        self.assertEqual(self.zot.data(JOURNAL)["proceedingsTitle"], "Old Journal")

    def test_type_change_keeps_a_type_field_through_its_base_field(self):
        r = self.run_("--key", CONF, "--set", "itemType=journalArticle", "--dry-run")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["fields_to_extra"], {"conferenceName": "OLDCONF"},
                         "proceedingsTitle goes to journalArticle's publicationTitle")

    def test_dry_run_plans_and_writes_nothing(self):
        r = self.run_("--key", JOURNAL, CONF, "--set", "date=2022", "--set", "publicationTitle=New", "--dry-run")
        self.assertEqual(r.code, 0, r)
        out = r.lines
        self.assertEqual(out[0], {"key": JOURNAL, "code": "ok", "changes": {"publicationTitle": {"from": "Old Journal", "to": "New"}},
                                  "mapped_fields": {}, "fields_to_extra": {}, "version": 10, "dry_run": True})
        self.assertEqual((out[1]["mapped_fields"], out[1]["dry_run"]), ({"publicationTitle": "proceedingsTitle"}, True))
        self.assertEqual(out[-1]["summary"], {"total": 2, "ok": 2, "skipped": 0, "failed": 0, "dry_run": True})
        r = self.run_("--key", JOURNAL, "--set", "date=2022", "--dry-run")
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["version"]), ("skipped", "unchanged", 10))
        self.assertEqual(self.zot.writes(), [])

    def test_patch_file_creators_numbers_and_set_wins(self):
        patch = self.patch_file({"creators": [{"creatorType": "author", "firstName": " Ada ", "lastName": "Lovelace"},
                                              {"creatorType": "editor", "name": "The Editors"}],
                                 "volume": 13, "date": "2020", "extra": "arXiv: 2205.07680\nTLDR: short"})
        r = self.run_("--key", JOURNAL, "--patch", patch, "--set", "date=2021")
        self.assertEqual(r.code, 0, r)
        creators = [{"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"},
                    {"creatorType": "editor", "name": "The Editors"}]
        self.assertEqual(self.patches(), [(JOURNAL, {"creators": creators, "volume": "13", "date": "2021",
                                                     "extra": "arXiv: 2205.07680\nTLDR: short"})])
        self.assertEqual(r.lines[0]["applied"], ["creators", "volume", "date", "extra"])
        self.assertEqual(r.lines[0]["changes"]["creators"]["from"],
                         [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}])

    def test_invalid_creators(self):
        patch = self.patch_file({"creators": [{"creatorType": "translator", "lastName": "X"},
                                              {"creatorType": "author", "first": "Y"}]})
        r = self.run_("--key", JOURNAL, "--patch", patch)
        self.assertEqual((r.code, r.lines[0]["code"], len(r.lines[0]["problems"])), (1, "invalid_creators", 2), r)
        self.assertIn("hint", r.lines[0])
        r = self.run_("--key", JOURNAL, "--patch", self.patch_file({"creators": "Ada Lovelace"}))
        self.assertEqual(r.lines[0]["code"], "invalid_creators")
        self.assertEqual(self.zot.writes(), [])

    def test_bad_input_is_one_line_before_zotero_is_asked(self):
        cases = [(("--set", "tags=a"), "refused_property"),
                 (("--patch", self.patch_file({"collections": ["ABCD1234"]})), "refused_property"),
                 (("--set", "deleted=1"), "refused_property"),
                 (("--patch", self.tmp / "missing.json"), "invalid_patch_file"),
                 (("--patch", self.patch_file("{not json")), "invalid_patch_file"),
                 (("--patch", self.patch_file([])), "invalid_patch_file"),
                 (("--patch", self.patch_file({})), "invalid_patch_file"),
                 (("--patch", self.patch_file({"title": ["a", "b"]})), "invalid_field")]
        for argv, code in cases:
            r = self.run_("--key", JOURNAL, *argv)
            self.assertEqual((r.code, len(r.lines), r.lines[0]["code"]), (1, 1, code), (argv, r))
            self.assertIn("hint", r.lines[0])
        self.assertEqual(r.lines[0]["field"], "title")
        self.assertEqual(self.zot.requests, [], "nothing was asked of Zotero")
        self.assertEqual(self.run_("--key", JOURNAL, "--set", "novalue").code, 2, "--set takes FIELD=VALUE")
        self.assertEqual(self.run_("--key", JOURNAL).code, 2, "--set or --patch is required")
        self.assertEqual(self.run_("--set", "date=2023").code, 2, "--key or --cite is required")

    def test_invalid_field_and_item_type_fail_their_own_item(self):
        r = self.run_("--key", CONF, JOURNAL, "--set", "volume=3")
        self.assertEqual(r.code, 1)
        self.assertEqual([o["code"] for o in r.lines[:2]], ["invalid_field", "ok"])
        self.assertEqual(r.lines[0]["invalid_fields"], ["volume"])
        self.assertIn("publicationTitle", r.lines[0]["valid_fields"])
        self.assertNotIn("volume", r.lines[0]["valid_fields"])
        self.assertEqual(self.patches(), [(JOURNAL, {"volume": "3"})])

        for key, argv in ((JOURNAL, ("--set", "itemType=bogus")), (NOTE, ("--set", "title=x")),
                          (ATT, ("--set", "itemType=journalArticle"))):
            r = self.run_("--key", key, *argv)
            self.assertEqual((r.code, r.lines[0]["code"]), (1, "invalid_item_type"), (key, r))
        r = self.run_("--key", ATT, "--set", "title=Accepted manuscript")
        self.assertEqual((r.code, r.lines[0]["applied"]), (0, ["title"]), "an attachment's title is a field like any other")

    def test_412_once_retries_twice_conflicts(self):
        self.zot.bump_before_write = 1
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["retried"], r.lines[0]["version_before"]), ("ok", True, 101))
        self.assertEqual(len(self.patches()), 2)

        self.setUp()
        self.zot.bump_before_write = 2
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "version_conflict"))
        self.assertIn("hint", r.lines[0])
        self.assertEqual(len(self.patches()), 2)

    def test_412_plans_again_on_what_changed_meanwhile(self):
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(date="2023")
        r = self.run_("--key", JOURNAL, "--set", "date=2023", "--set", "DOI=10.1/x")
        self.assertEqual(r.code, 0, r)
        self.assertEqual(self.patches(), [(JOURNAL, {"date": "2023", "DOI": "10.1/x"}), (JOURNAL, {"DOI": "10.1/x"})])
        self.assertEqual(r.lines[0]["changes"], {"DOI": {"from": "", "to": "10.1/x"}})

        self.setUp()
        self.zot.bump_before_write = 1
        self.zot.concurrent_edit = lambda it: it["data"].update(date="2023")
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual(r.code, 0, r)
        self.assertEqual((r.lines[0]["code"], r.lines[0]["reason"], r.lines[0]["retried"]), ("skipped", "unchanged", True))
        self.assertEqual(len(self.patches()), 1)

    def test_readback_mismatch(self):
        self.zot.ignore_writes = True
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "readback_mismatch"), r)
        self.assertEqual(r.lines[0]["mismatch"], {"date": {"sent": "2023", "now": "2022"}})
        self.assertIn("hint", r.lines[0])

    def test_values_zotero_normalized(self):
        self.zot.on_write = moves_pmid_line
        r = self.run_("--key", JOURNAL, "--patch", self.patch_file({"extra": "TLDR: a summary\nPMID: 38262200"}))
        self.assertEqual(r.code, 0, r)
        line = r.lines[0]
        self.assertEqual((line["code"], line["applied"]), ("ok", []))
        self.assertEqual(line["normalized"], {"extra": {"sent": "TLDR: a summary\nPMID: 38262200", "now": "TLDR: a summary",
                                                        "moved_to_fields": {"PMID: 38262200": "PMID"}}})
        self.assertEqual(self.zot.data(JOURNAL)["PMID"], "38262200")

        self.zot.on_write = lambda it: it["data"].update(date="2023-01-05")
        r = self.run_("--key", JOURNAL, "--set", "date=2023-1-5")
        self.assertEqual((r.code, r.lines[0]["code"]), (0, "ok"), r)
        self.assertEqual(r.lines[0]["normalized"], {"date": {"sent": "2023-1-5", "now": "2023-01-05"}})

    def test_write_denied_and_write_failed(self):
        self.zot.write_status = (403, "Write access denied")
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["detail"]), (1, "write_denied", "Write access denied"))
        self.zot.write_status = (400, "Invalid field value")
        r = self.run_("--key", JOURNAL, "--set", "date=2023")
        self.assertEqual((r.code, r.lines[0]["code"], r.lines[0]["status"]), (1, "write_failed", 400))

    def test_not_found_and_cite_resolution(self):
        r = self.run_("--key", "GONE0000", "--cite", "liu2022paper", "nobody", "dupkey", "--set", "date=2023")
        self.assertEqual(r.code, 1)
        out = r.lines
        self.assertEqual((out[0]["key"], out[0]["code"]), ("GONE0000", "not_found"))
        self.assertIn("hint", out[0])
        self.assertEqual((out[1]["key"], out[1]["cite"], out[1]["code"]), (JOURNAL, "liu2022paper", "ok"))
        self.assertEqual(out[2], {"cite": "nobody", "code": "cite_not_found", "hint": out[2]["hint"]})
        self.assertEqual((out[3]["code"], out[3]["keys"]), ("cite_ambiguous", [DUP1, DUP2]))
        self.assertEqual(out[-1]["summary"], {"total": 4, "ok": 1, "skipped": 0, "failed": 3})
        self.assertEqual(self.patches(), [(JOURNAL, {"date": "2023"})])

    def test_cannot_check(self):
        r = self.run_("--key", JOURNAL, "--set", "date=2023", base_url=f"http://127.0.0.1:{closed_port()}")
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "zotero_unreachable"))
        r = self.run_("--key", JOURNAL, "--set", "date=2023", config=config_file(key=None))
        self.assertEqual((r.code, r.lines[0]["code"]), (2, "no_key"))
        r = self.run_("--key", JOURNAL, CONF, "--set", "date=2023", config=config_file(key="wrong"))
        self.assertEqual(r.code, 2)
        self.assertEqual([o["code"] for o in r.lines[:2]], ["key_rejected", "not_run"], "the item it stopped on says why")
        self.assertEqual(r.lines[-1]["summary"]["stopped"], "key_rejected")

    def test_smoke(self):
        r = smoke("update_item", "--key", JOURNAL, "--set", "date=2023", "--dry-run", "--base-url", self.zot.base_url,
                  config=self.config)
        self.assertEqual(r.code, 0, r)
        self.assertEqual(r.lines[0]["code"], "ok")
        self.assertEqual(r.lines[-1]["summary"]["total"], 1)


class MovedToFields(unittest.TestCase):
    def test_a_pmid_line_zotero_moved_into_its_field(self):
        sent = "TLDR: a summary\nPMID: 38262200"
        after = {"extra": "TLDR: a summary", "PMID": "38262200", "title": "x"}
        self.assertEqual(update.moved_to_fields(sent, after["extra"], after), {"PMID: 38262200": "PMID"})

    def test_a_line_that_is_simply_missing_is_not_explained(self):
        self.assertEqual(update.moved_to_fields("arXiv: 2101.00001", "", {"extra": "", "title": "x"}), {})
        self.assertEqual(update.moved_to_fields("PMID: 1", "", {"extra": "", "PMID": "2"}), {}, "a different value")


if __name__ == "__main__":
    unittest.main()
