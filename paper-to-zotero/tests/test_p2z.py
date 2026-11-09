# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/p2z.py: the dispatcher, and prepare then save over records against the fakes."""
import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, config_file, load, smoke
from fake_zotero import FakeZotero

from p2zlib import run as work_run

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
P2Z = SCRIPTS / "p2z.py"
ENTRY = load("p2z")


def run(*args, timeout=60):
    return subprocess.run([sys.executable, str(P2Z), *args], capture_output=True, text=True, timeout=timeout)


def first_doc_line(script):
    doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


class P2zTest(unittest.TestCase):
    def test_help_lists_every_word_and_every_script_has_one(self):
        done = run("-h")
        self.assertEqual((done.returncode, done.stderr), (0, ""), done.stderr)
        words = [line.split()[0] for line in done.stdout.splitlines() if line.startswith("  ") and not line.startswith("   ")
                 and not line.lstrip().startswith("p2z.py")]
        self.assertEqual(words, list(ENTRY.WORDS))
        scripts = {p.stem for p in SCRIPTS.glob("*.py") if p.name != "p2z.py"}
        self.assertEqual({s for s, _, _ in ENTRY.WORDS.values() if s}, scripts, "a word for every script, a script for every word")

    def test_no_word_or_an_unknown_one(self):
        for argv in ((), ("nope", "--flag"), ("../scripts/ready",), ("/etc/passwd",), ("ready.py",), ("",)):
            done = run(*argv)
            self.assertEqual((done.returncode, done.stdout), (2, ""), argv)
            self.assertIn("  ready", done.stderr)
            self.assertEqual(json.loads(done.stderr.splitlines()[-1])["code"], "usage", argv)

    def test_the_word_is_the_usage_line(self):
        done = run("ready", "-h")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("usage: p2z.py ready"), done.stdout[:80])
        done = run("note", "take", "-h")
        self.assertTrue(done.stdout.startswith("usage: p2z.py note take"), done.stdout[:80])
        done = run("prepare", "-h")
        self.assertTrue(done.stdout.startswith("usage: p2z.py prepare"), done.stdout[:80])

    def test_exit_code_is_propagated(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        tmp = Path(tempfile.mkdtemp(prefix="p2z-dispatch-"))
        try:
            env = dict(os.environ, HOME=str(tmp), PAPER_TO_ZOTERO_CONFIG=str(tmp / "config.json"))
            done = subprocess.run([sys.executable, str(P2Z), "ready", "--base-url", f"http://127.0.0.1:{port}",
                                   str(tmp / "paper-to-zotero")],
                                  capture_output=True, text=True, env=env, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr)
        self.assertEqual(json.loads(done.stderr.splitlines()[-1])["code"], "zotero_unreachable")

    def test_an_empty_list_on_stdin_is_nothing_to_do(self):
        """`search X | pdf -` with no hit: the pipe's status is search's 1, never a usage error downstream; and an
        empty list never widens to the whole library. No Zotero answers here: nothing may ask it."""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = dict(os.environ, PAPER_TO_ZOTERO_BASE_URL=f"http://127.0.0.1:{port}",
                   PAPER_TO_ZOTERO_CONFIG=str(Path(tempfile.mkdtemp()) / "none.json"))
        for argv in (("pdf", "-"), ("items", "-"), ("trash", "-n", "-"), ("tag", "--add-tag", "x", "-"), ("update", "-"),
                     ("lint", "-"), ("package", "names", "-"), ("package", "take", "--missing", "-o", "/tmp/x/", "-"),
                     ("export", "-"), ("prepare", "-"), ("have", "-"), ("report", "-")):
            done = subprocess.run([sys.executable, str(P2Z), *argv], input="", capture_output=True, text=True, env=env,
                                  timeout=60)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""), argv)
        done = subprocess.run([sys.executable, str(P2Z), "pdf"], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(done.returncode, 2, "nothing written after the options is still a usage error")

    def test_one_sentence_docstrings(self):
        for name in sorted(p.name for p in SCRIPTS.glob("*.py")):
            line = first_doc_line(SCRIPTS / name)
            self.assertTrue(line.endswith("."), f"{name}: first docstring line must be one sentence: {line!r}")
            self.assertLess(len(line), 140, name)


class PrepareAndSave(unittest.TestCase):
    def test_the_main_line(self):
        zot = FakeZotero()
        self.addCleanup(zot.close)
        zot.add_collection("COLL0001", "Inbox")
        zot.add_item("LIKE0001", itemType="journalArticle", title="Paper Near Something")
        zot.add_item("HAVE0001", itemType="journalArticle", title="A Paper The Library Has", DOI="10.1000/have.1")
        zot.add_item("HAVEPDF1", itemType="attachment", parentItem="HAVE0001", title="Published-Example",
                     contentType="application/pdf", linkMode="imported_url")
        work = work_run.Work(tempfile.mkdtemp(prefix="p2z-main-"))
        results = work.root / "fetch" / "results"
        results.mkdir(parents=True)
        work.records.mkdir()
        pdf = results / "new.pdf"
        pdf.write_bytes(b"%PDF-1.4 a new paper")
        unchecked = results / "extra.pdf"
        unchecked.write_bytes(b"%PDF-1.4 a file not yet checked")
        got = {"status": "got", "tried": [], "last": None}
        author = [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}]
        papers = {
            "new": ({"itemType": "journalArticle", "title": "A New Paper", "DOI": "10.1000/new.1", "date": "2024"},
                    {"record_of": "published", "outcome": got, "files": [
                        {"name": "new.pdf", "md5": work_run.md5_of(pdf), "kind": "published", "check": "ok",
                         "label": {"title": "Published-Example"}},
                        {"name": "extra.pdf", "md5": work_run.md5_of(unchecked), "kind": "supplement",
                         "check": "cannot_judge", "label": {"title": "Supplement-Example"}}]}),
            "dup": ({"itemType": "journalArticle", "title": "Paper Near Something", "date": "2024"},
                    {"record_of": "published", "outcome": {"status": "not_got", "tried": [], "last": None}, "files": []}),
            "pre": ({"itemType": "preprint", "title": "Reflexion: Language Agents with Verbal Reinforcement",
                     "archiveID": "arXiv:2303.11366", "date": "2023"},
                    {"record_of": "preprint", "versions": {"published": [{"ids": {"doi": "10.1000/pub.9"}, "venue": "NeurIPS"}],
                                                           "incomplete": []}}),
            "lib": ({"itemType": "journalArticle", "title": "A Paper The Library Has", "DOI": "10.1000/have.1", "date": "2024"},
                    {"record_of": "published"}),  # never fetched: the item has its PDF
        }
        for slug, (item, res) in papers.items():
            (results / f"{slug}.json").write_text(json.dumps({"slug": slug, **res}))
            (work.records / f"{slug}.json").write_text(json.dumps({
                "fetched": str(results / f"{slug}.json"), "item": {**item, "creators": author}, "collection": "COLL0001",
                "tags": ["method/x"], **({"citationKey": "liu_2024"} if slug == "new" else {})}))
        records = [str(work.records / f"{s}.json") for s in papers]
        env = {**os.environ, "PAPER_TO_ZOTERO_CONFIG": str(config_file())}

        def p2z(*argv):
            done = subprocess.run([sys.executable, str(P2Z), *argv, "--base-url", zot.base_url, *records], capture_output=True,
                                  text=True, env=env, timeout=120)
            self.last = json.loads(done.stderr.splitlines()[-1]) if done.stderr.strip() else None
            return done.returncode, [json.loads(line) for line in done.stdout.splitlines()]

        code, lines = p2z("prepare")
        self.assertEqual(code, 1, lines)
        by = {line["slug"]: line for line in lines}
        self.assertEqual(set(by["new"]["steps"]), {"have", "check"})
        same = by["dup"]["decide"][0]
        self.assertEqual((same["waiting_on"], [c["key"] for c in json.loads(Path(same["same_paper"]).read_text())["candidates"]]),
                         ("judge", ["LIKE0001"]), "the open candidate is a judge's, through its handoff")
        self.assertIn({"published_versions": 1}, by["pre"]["decide"], "the result lists a published version")
        self.assertIn({"tags": str(work.tags / "new.json")}, by["new"]["decide"], "a paper to create needs its tags file")
        self.assertNotIn("tags", json.dumps(by["lib"].get("decide", [])), "a paper the library holds is not tagged")
        code, again = p2z("prepare")
        self.assertTrue(all(v["code"] == "skipped" for v in again[0]["steps"].values()), again[0])
        self.assertEqual(again[0]["steps"]["have"]["reason"], "done")
        pre = work_run.read(records[2])
        pre["keep_preprint"] = "the user wants the preprint"
        pre.save()
        code, lines = p2z("save")
        by = {line["slug"]: line for line in lines}
        self.assertEqual((by["new"]["steps"]["create"]["code"], by["new"]["failed"]), ("untagged", ["create", "attach"]),
                         "no item before its curated tags, and save says so")
        self.assertEqual(by["new"]["steps"]["create"]["tags_file"], str(work.tags / "new.json"))
        self.assertIn("tags file", by["new"]["steps"]["create"]["hint"])
        work.tags.mkdir()
        for slug in ("new", "pre"):
            (work.tags / f"{slug}.json").write_text(json.dumps(["method/x", "venue/Example"]))
        writes = len(zot.writes())
        code, lines = p2z("save", "-n")
        self.assertEqual(({name: step["code"] for name, step in
                           {line["slug"]: line for line in lines}["new"]["steps"].items()}, len(zot.writes())),
                         ({"create": "ok", "attach": "ok"}, writes), "save -n on a new record: both steps would go, nothing written")
        code, lines = p2z("save")
        by = {line["slug"]: line for line in lines}
        self.assertEqual({name: step["code"] for name, step in by["new"]["steps"].items()},
                         {"create": "ok", "attach": "ok"}, lines)
        created, attached = by["new"]["steps"]["create"], by["new"]["steps"]["attach"]
        self.assertEqual(created["key"], work_run.read(records[0])["saved"]["key"])
        self.assertEqual(created["citation_key_hint"]["suggested"], "liu2024")
        self.assertEqual(attached["unchecked"], ["extra.pdf"], "an ok step can still name files left unchecked")
        self.assertEqual(attached["files"][0]["attachment"], work_run.read(records[0])["attach"][0]["attachment"])
        self.assertEqual(zot.data(work_run.read(records[0])["saved"]["key"])["tags"],
                         [{"tag": "method/x", "type": 0}, {"tag": "venue/Example", "type": 0}])
        self.assertEqual(work_run.read(records[0])["attach"][0]["title"], "Published-Example")
        self.assertEqual(by["dup"]["steps"]["create"]["code"], "possible_duplicate")
        self.assertEqual(by["dup"]["failed"], ["create"])
        self.assertEqual(by["pre"]["steps"]["attach"]["code"], "unsettled", "a result never settled attaches nothing")
        self.assertEqual((by["lib"]["steps"]["attach"]["code"], by["lib"]["steps"]["attach"]["reason"],
                          by["lib"].get("failed")), ("skipped", "library_has_pdf", None),
                         "the library's own PDF: nothing to fetch, nothing to settle")
        self.assertNotIn({"published_versions": 1}, by["pre"].get("decide", []), "keep_preprint settles it")
        self.assertEqual(self.last["summary"]["decide"], 4)
        writes = len(zot.writes())
        code, lines = p2z("save")
        again = {line["slug"]: line for line in lines}["new"]["steps"]
        self.assertEqual((again["create"]["code"], again["create"]["reason"]), ("skipped", "saved"))
        self.assertEqual((again["attach"]["code"], again["attach"]["reason"]), ("skipped", "attached"))
        self.assertEqual(again["attach"]["unchecked"], ["extra.pdf"], "skipped steps keep their other fields too")
        self.assertEqual(len(zot.writes()), writes, "a rerun adds neither an item nor an attachment")

    def test_save_keeps_the_first_creation_readback_diagnostic(self):
        zot = FakeZotero()
        self.addCleanup(zot.close)
        zot.add_collection("COLL0001", "Inbox")
        zot.on_write = lambda item: item["data"].update(tags=[])
        with tempfile.TemporaryDirectory(prefix="p2z-mismatch-") as tmp:
            work = work_run.Work(tmp)
            work.records.mkdir()
            work.tags.mkdir()
            result = work.root / "result.json"
            result.write_text(json.dumps({"record_of": "published", "files": [],
                                          "outcome": {"status": "not_got", "tried": [], "last": None}}))
            record = work.records / "mismatch.json"
            record.write_text(json.dumps({"item": {"itemType": "journalArticle", "title": "Readback Example",
                                                    "creators": [{"creatorType": "author", "lastName": "Liu"}]},
                                          "collection": "COLL0001", "fetched": str(result)}))
            (work.tags / "mismatch.json").write_text(json.dumps(["method/x"]))
            config = config_file(work.root)
            first = call(ENTRY, "save", record, "--base-url", zot.base_url, config=config)
            created = first.lines[0]["steps"]["create"]
            self.assertEqual((first.code, created["code"], created["wrong"]),
                             (1, "readback_mismatch", {"tags": True}))
            self.assertIn(created["key"], created["hint"])
            again = smoke("create", record, "--base-url", zot.base_url, config=config)
            self.assertEqual(again.lines[0]["reason"], "saved", "a rerun cannot recover the original diagnostic")

    def test_a_step_that_exits_without_a_result_still_has_an_object(self):
        with tempfile.TemporaryDirectory(prefix="p2z-no-result-") as tmp:
            record = Path(tmp) / "example.json"
            record.write_text("{}")
            stop = {"code": "step_failed", "hint": "The child could not start."}
            child = subprocess.CompletedProcess([], 2, stdout="", stderr=json.dumps(stop))
            with mock.patch.object(ENTRY.subprocess, "run", return_value=child) as child_run:
                result = call(ENTRY, "save", record)
            self.assertEqual(result.code, 2)
            self.assertEqual(result.lines[0]["steps"], {"create": {"code": "step_failed", "exit": 2}})
            self.assertEqual(result.last, stop)
            self.assertEqual(child_run.call_count, 1, "attach never runs after a step cannot go on")


if __name__ == "__main__":
    unittest.main()
