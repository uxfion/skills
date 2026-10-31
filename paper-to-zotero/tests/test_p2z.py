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

from helpers import config_file
from fake_zotero import FakeZotero

from p2zlib import run as work_run

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
P2Z = SCRIPTS / "p2z.py"


def run(*args, timeout=60):
    return subprocess.run([sys.executable, str(P2Z), *args], capture_output=True, text=True, timeout=timeout)


def first_doc_line(script):
    doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8"))) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


class P2zTest(unittest.TestCase):
    def test_help_lists_every_script_but_itself(self):
        done = run("--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        names = [line.split()[0] for line in done.stdout.splitlines() if line.startswith("  ")]
        expected = sorted([p.stem for p in SCRIPTS.glob("*.py") if p.name != "p2z.py"] + ["prepare", "save"])
        self.assertEqual(names, expected)
        self.assertNotIn("p2z", names)
        self.assertIn(first_doc_line(SCRIPTS / "ready.py"), done.stdout)
        self.assertIn(first_doc_line(SCRIPTS / "file_and_tag.py"), done.stdout)

    def test_no_args_is_help(self):
        done = run()
        self.assertEqual(done.returncode, 0)
        self.assertIn("commands:", done.stdout)
        self.assertIn("ready", done.stdout)

    def test_unknown_command(self):
        done = run("nope", "--flag")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertIn("unknown command 'nope'", done.stderr)
        self.assertIn("  ready", done.stderr)

    def test_path_tricks_are_not_commands(self):
        for name in ("../scripts/ready", "/etc/passwd", "ready.py", ""):
            done = run(name)
            self.assertEqual(done.returncode, 2, name)
            self.assertEqual(done.stdout, "", name)

    def test_dispatch_passes_args_through(self):
        done = run("ready", "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("usage: ready.py"), done.stdout[:80])

    def test_exit_code_is_propagated(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        tmp = Path(tempfile.mkdtemp(prefix="p2z-dispatch-"))
        try:
            env = dict(os.environ, HOME=str(tmp), PAPER_TO_ZOTERO_CONFIG=str(tmp / "config.json"))
            done = subprocess.run([sys.executable, str(P2Z), "ready", "--base-url", f"http://127.0.0.1:{port}",
                                   "--dir", str(tmp / "paper-to-zotero")],
                                  capture_output=True, text=True, env=env, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('"code": "zotero_unreachable"', done.stdout)

    def test_one_sentence_docstrings(self):
        for name in ("ready.py", "p2z.py"):
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
        got = {"status": "got", "tried": [], "last": None}
        author = [{"creatorType": "author", "firstName": "Wei", "lastName": "Liu"}]
        papers = {
            "new": ({"itemType": "journalArticle", "title": "A New Paper", "DOI": "10.1000/new.1", "date": "2024"},
                    {"record_of": "published", "outcome": got, "files": [
                        {"name": "new.pdf", "md5": work_run.md5_of(pdf), "kind": "published", "check": "ok",
                         "label": {"title": "Published-Example"}}]}),
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
                "tags": ["method/x"]}))
        records = [str(work.records / f"{s}.json") for s in papers]
        env = {**os.environ, "PAPER_TO_ZOTERO_CONFIG": str(config_file())}

        def p2z(*argv):
            done = subprocess.run([sys.executable, str(P2Z), *argv, "--base-url", zot.base_url, *records], capture_output=True,
                                  text=True, env=env, timeout=120)
            return done.returncode, [json.loads(line) for line in done.stdout.splitlines()]

        code, lines = p2z("prepare")
        self.assertEqual(code, 1, lines)
        by = {line["slug"]: line for line in lines[:-1]}
        self.assertEqual(set(by["new"]["steps"]), {"find_in_library", "check_item"})
        same = by["dup"]["decide"][0]
        self.assertEqual((same["waiting_on"], [c["key"] for c in json.loads(Path(same["same_paper"]).read_text())["candidates"]]),
                         ("judge", ["LIKE0001"]), "the open candidate is a judge's, through its handoff")
        self.assertIn({"published_versions": 1}, by["pre"]["decide"], "the result lists a published version")
        code, again = p2z("prepare")
        self.assertTrue(all(v.startswith("skipped") for v in again[0]["steps"].values()), again[0])
        pre = work_run.read(records[2])
        pre["keep_preprint"] = "the user wants the preprint"
        pre.save()
        code, lines = p2z("save")
        by = {line["slug"]: line for line in lines[:-1]}
        self.assertEqual(by["new"]["steps"], {"create_item": "ok", "attach_file": "ok"}, lines)
        self.assertEqual(work_run.read(records[0])["attach"][0]["title"], "Published-Example")
        self.assertEqual(by["dup"]["steps"]["create_item"], "possible_duplicate")
        self.assertEqual(by["dup"]["failed"], ["create_item"])
        self.assertEqual(by["pre"]["steps"]["attach_file"], "unsettled", "a result never settled attaches nothing")
        self.assertEqual((by["lib"]["steps"]["attach_file"], by["lib"].get("failed")), ("skipped: library_has_pdf", None),
                         "the library's own PDF: nothing to fetch, nothing to settle")
        self.assertNotIn({"published_versions": 1}, by["pre"].get("decide", []), "keep_preprint settles it")
        self.assertEqual(lines[-1]["summary"]["decide"], 4)


if __name__ == "__main__":
    unittest.main()
