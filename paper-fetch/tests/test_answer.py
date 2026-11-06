# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for pf.py answer and pf.py todo: each kind of handoff answered, what an answer does to the paper
(filed, refused, unconfirmed then replaced, labelled, held on its route, a download claimed), the refusals, and the
version a paper is satisfied by (pdftotext and pdfinfo are stubs that print a file's sidecars)."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import call, fake_pdf, load, poppler_stubs, result_file, smoke
from pflib import run

answer, todo, claim = load("answer"), load("todo"), load("claim")
TITLE = "Progressive Deep Learning for Cardiac Image Segmentation"
OTHER = "A Completely Different Paper About Lung Nodules"


class Answer(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp(prefix="pf-answer-"))
        self.work = run.Work(root / "fetch")
        self.work.results.mkdir(parents=True)
        self.work.inbox.mkdir()
        self.work.started.touch()
        os.utime(self.work.started, (time.time() - 600,) * 2)
        self.dl = root / "Downloads"
        self.dl.mkdir()
        self.work.set(downloads=str(self.dl))
        bin_ = poppler_stubs(root / "bin")
        self.enterContext(mock.patch.dict(os.environ, {"PATH": f"{bin_}:{os.environ['PATH']}"}))
        for slug, title in (("paper", TITLE), ("other", OTHER)):
            result_file(self.work.root, slug, csl={"title": title, "author": [{"family": "Liu"}]})

    def res(self, slug):
        return run.read(self.work.results / f"{slug}.json")

    def claim(self, path, slug):
        return call(claim, "claim", path, self.work.results / f"{slug}.json")

    def held(self, slug, name, text):
        r = self.claim(fake_pdf(self.work.inbox / name, [text]), slug)
        self.assertEqual(r.lines[0]["result"], "held", r)
        return self.work.handoffs / f"{r.lines[0]['handoff']}.json"

    def answer(self, handoff, word, *argv):
        return call(answer, handoff, word, *argv)

    def todo(self, *argv):
        return call(todo, self.work.root, *argv)

    def test_a_held_file_accepted_refused_or_unknown(self):
        handoff = self.held("paper", "scan.pdf", "A scanned first page")
        listed = self.todo()
        self.assertEqual((listed.code, [(x["id"], x["kind"]) for x in listed.lines]), (1, [("paper.1", "file")]))
        self.assertEqual(listed.last, {"summary": {"open": 1, "kinds": {"file": 1}, "papers": ["paper"]}})
        r = self.answer(handoff, "accept", "--reason", "page 1 is the paper, a scan", "--label", "Published-IEEE",
                        "--why", "page 1: vol. 12 no. 3", "--by", "paper_agent")
        self.assertEqual((r.code, [(e["event"], e["code"]) for e in r.lines]),
                         (0, [("accept", "claimed"), ("label", "ok"), ("answer", "ok")]), r)
        [f] = self.res("paper")["files"]
        self.assertEqual((f["name"], f["check"], f["label"]["title"], f["accepted_reason"]),
                         ("paper.pdf", "accepted", "Published-IEEE", "page 1 is the paper, a scan"))
        self.assertTrue(run.satisfied(self.work, self.res("paper")))
        self.assertEqual((self.todo().code, self.todo().err), (0, ""))
        self.assertEqual(self.answer(handoff, "refuse").lines[0]["code"], "not_open")
        # refuse: not the paper; the paper goes on, the file stays where the check put it
        handoff = self.held("other", "notice.pdf", "Erratum\nA notice")
        self.assertEqual(self.answer(handoff, "refuse", "--reason", "a correction notice").code, 0)
        self.assertEqual(self.res("other")["outcome"]["status"], "not_got")
        self.assertTrue((self.work.unverified / "other.file.pdf").is_file())
        # unknown: filed unconfirmed, never satisfying the paper; a confirmed file later replaces it
        handoff = self.held("other", "maybe.pdf", "Lung Nodules, a poster")
        self.answer(handoff, "unknown", "--reason", "page 1 is a poster with the same words")
        [f] = self.res("other")["files"]
        self.assertEqual((f["check"], run.satisfied(self.work, self.res("other"))), ("unconfirmed", False))
        good = fake_pdf(self.work.inbox / "good.pdf", [f"{OTHER}\nWei Liu"])
        self.claim(good, "other")
        self.assertEqual([(f["name"], f["check"]) for f in self.res("other")["files"]], [("other.pdf", "ok")])
        self.assertEqual([e["event"] for e in self.work.events() if e["event"] == "withdraw"], ["withdraw"])

    def test_the_files_set_aside_are_in_the_result(self):
        """Every file of a paper left in unverified/ is in its result's set_aside, with why: the result is all a
        caller reads, so a library file refused while labelling files in hand still reaches it."""
        self.assertNotIn("set_aside", self.res("other"), "absent when there is none")
        # refused by the check: a file from outside the directory (a library's) is copied in, its original kept
        outside = Path(tempfile.mkdtemp(prefix="pf-zotero-storage-")) / "Liu - 2022.pdf"
        outside.write_text("<html>a login page</html>")
        r = self.claim(outside, "other")
        refused = r.lines[0]
        self.assertEqual((refused["result"], outside.is_file()), ("refused", True), r)
        # held: its file handoff open; then one answered refuse
        held = self.held("other", "scan.pdf", "A scanned first page")
        notice = self.held("other", "notice.pdf", "Erratum\nA notice")
        self.answer(notice, "refuse", "--reason", "a correction notice")
        # accepted: filed, so not set aside
        self.answer(self.held("paper", "a.pdf", "A scanned first page"), "accept", "--reason", "page 1 is the paper")
        # withdrawn: an unconfirmed file moved back when a confirmed one was filed
        self.answer(self.held("paper", "b.pdf", "Lung Nodules, a poster"), "unknown", "--reason", "cannot tell")
        self.claim(fake_pdf(self.work.inbox / "good.pdf", [f"{TITLE}\nWei Liu"]), "paper")

        def aside(slug):
            return [(x["why"], x.get("code"), x["md5"], (self.work.unverified / x["name"]).is_file())
                    for x in self.res(slug).get("set_aside") or []]

        handoff = lambda path: json.loads(Path(path).read_text())  # noqa: E731
        self.assertEqual(aside("other"), [("refused", refused["code"], refused["md5"], True),
                                          ("held", handoff(held)["code"], handoff(held)["md5"], True),
                                          ("refused", handoff(notice)["code"], handoff(notice)["md5"], True)])
        [withdrawn] = [e for e in self.work.events("withdraw")]
        self.assertEqual([x[0] for x in aside("paper")], ["withdrawn"], "the accepted file is among files, not here")
        self.assertEqual((aside("paper")[0][2], self.res("paper")["set_aside"][0]["name"]),
                         (withdrawn["md5"], withdrawn["file"]))
        self.assertNotIn(aside("paper")[0][2], [f["md5"] for f in self.res("paper")["files"]])

    def test_labels_decide_whether_the_paper_goes_on(self):
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"])
        self.claim(good, "paper")
        self.assertTrue(run.satisfied(self.work, self.res("paper")), "an unlabelled file holds the paper")
        f = self.work.results / "paper.pdf"
        label = lambda: run.handoff(self.work, "label", self.res("paper"), file=f, md5=run.md5_of(f))  # noqa: E731
        h = label()
        r = self.answer(self.work.handoffs / f"{h['id']}.json", "label", "--label", "Accepted-arXiv-v2", "--why", "v2's comment")
        self.assertEqual(r.code, 0, r)
        self.assertFalse(run.satisfied(self.work, self.res("paper")), "an accepted manuscript: the paper goes on (decision A)")
        second = fake_pdf(self.work.inbox / "b.pdf", [f"{TITLE}\nWei Liu, the journal's"])
        self.claim(second, "paper")
        g = self.work.results / "paper.2.pdf"
        h = run.handoff(self.work, "label", self.res("paper"), file=g, md5=run.md5_of(g))
        self.answer(self.work.handoffs / f"{h['id']}.json", "label", "--label", "Published-IEEE", "--why", "vol. 12")
        res = self.res("paper")
        self.assertEqual((run.satisfied(self.work, res), run.paper_file(self.work, res).name), (True, "paper.2.pdf"))
        self.assertEqual([x["label"]["title"] for x in res["files"]], ["Accepted-arXiv-v2", "Published-IEEE"],
                         "both versions kept, side by side")
        # unknown: Unknown-<Source>, which is not the wanted version either
        h = run.handoff(self.work, "label", self.res("other"), file=g, md5="nope")
        self.assertEqual(self.answer(self.work.handoffs / f"{h['id']}.json", "label", "--label", "Final", "--why", "x").lines[0]["code"],
                         "bad_label")
        self.assertEqual(self.answer(self.work.handoffs / f"{h['id']}.json", "label").lines[0]["code"], "no_label")

    def test_a_page_a_download_and_the_browser(self):
        page = run.handoff(self.work, "page", self.res("paper"), pass_=1, route="publisher", url="https://doi.org/10.1/x")
        r = self.answer(self.work.handoffs / f"{page['id']}.json", "blocked", "--reason", "a bot check on the publisher")
        self.assertEqual(([(e["event"], e["code"]) for e in r.lines], r.lines[0]["result"]),
                         ([("try", "blocked"), ("answer", "ok")], "blocked"))
        self.assertTrue(run.held_on_route(self.work, "paper", 1), "a block holds the paper on its route this pass")
        self.assertEqual(self.todo("--slug", "paper").code, 0, "answered blocked, nothing of the paper's is open: its "
                                                               "agent's done-when holds")
        self.assertEqual(self.res("paper")["outcome"]["last"]["result"], "blocked", "why it was not got stays")
        page = run.handoff(self.work, "page", self.res("other"), pass_=1, route="publisher", url="https://doi.org/10.1/y")
        self.assertEqual(self.answer(self.work.handoffs / f"{page['id']}.json", "no_pdf_here").lines[0]["code"], "bad_answer")
        self.assertFalse(run.held_on_route(self.work, "other", 1))
        # a download nobody claimed, which the judge says is the other paper's
        dl = fake_pdf(self.dl / "fulltext.pdf", [f"{OTHER}\nWei Liu"])
        left = run.handoff(self.work, "left", file=dl, md5=run.md5_of(dl), note="unmatched")
        r = self.answer(self.work.handoffs / f"{left['id']}.json", "claim", "--slug", "other", "--reason", "its page 1")
        self.assertEqual((r.code, r.lines[0]["file"], dl.exists()), (0, "other.pdf", False), r)
        down = run.handoff(self.work, "browser_down", note="BROWSER_CONNECT: no extension")
        self.assertEqual(self.answer(self.work.handoffs / f"{down['id']}.json", "resolved").code, 0)
        self.assertEqual([(x["slug"], x["kind"]) for x in self.todo().lines], [("other", "label")],
                         "what is left: the label of the file the download became")
        r = self.answer(self.work.handoffs / "nope.1.json", "resolved")
        self.assertEqual((r.code, r.lines[0]["code"]), (1, "no_such_handoff"))
        self.assertEqual(call(todo, self.work.root.parent / "elsewhere").lines[0]["code"], "no_work_dir")

    def test_a_slug_given_as_the_citation_key(self):
        """identify names a result by its key's file-safe form; todo and answer take the key as it was given."""
        result_file(self.work.root, "He_2016_ResNet", csl={"title": TITLE, "author": [{"family": "He"}]})
        page = run.handoff(self.work, "page", self.res("He_2016_ResNet"), pass_=1, route="publisher",
                           url="https://doi.org/10.1/z")
        r = self.todo("--slug", "He:2016:ResNet")
        self.assertEqual((r.code, [x["id"] for x in r.lines]), (1, [page["id"]]))
        dl = fake_pdf(self.dl / "resnet.pdf", [f"{TITLE}\nKaiming He"])
        left = run.handoff(self.work, "left", file=dl, md5=run.md5_of(dl), note="unmatched")
        r = self.answer(self.work.handoffs / f"{left['id']}.json", "claim", "--slug", "He:2016:ResNet", "--reason", "its page 1")
        self.assertEqual((r.code, r.lines[0]["slug"], r.lines[0]["file"]), (0, "He_2016_ResNet", "He_2016_ResNet.pdf"), r)

    def test_todo_lists_by_kind(self):
        """todo lists the open handoffs by kind, in the order the loop takes them up, oldest first within a kind. Who
        takes a kind is SKILL.md's: the record, the log and todo hold only the fields pflib/run.py documents."""
        label = run.handoff(self.work, "label", self.res("paper"), md5="0" * 32)
        page = run.handoff(self.work, "page", self.res("other"), pass_=1, route="publisher", url="https://doi.org/10.1/y",
                           code="no_pdf_link")
        left = run.handoff(self.work, "left", file=self.dl / "fulltext.pdf", md5="1" * 32, note="unmatched")
        down = run.handoff(self.work, "browser_down", note="BROWSER_CONNECT: no extension")
        again = run.handoff(self.work, "page", self.res("other"), pass_=1, route="start", url="https://pub.example/y")
        listed = self.todo()
        self.assertEqual([(x["kind"], x["id"]) for x in listed.lines],
                         [("browser_down", down["id"]), ("page", page["id"]), ("page", again["id"]),
                          ("label", label["id"]), ("left", left["id"])])
        self.assertEqual(listed.last["summary"]["kinds"], {"label": 1, "page": 2, "left": 1, "browser_down": 1})
        self.assertEqual([x["id"] for x in self.todo("--kind", "page").lines], [page["id"], again["id"]])
        documented = {"record": {"id", "kind", "slug", "pass", "route", "url", "file", "md5", "code", "note", "paper",
                                 "evidence", "answers", "at"},
                      "event": {"event", "id", "slug", "kind", "md5", "route", "url", "path", "at"},
                      "todo": {"id", "slug", "kind", "route", "url", "path"}}
        self.assertEqual({"record": set().union(*(json.loads(Path(e["path"]).read_text()) for e in self.work.events("handoff"))),
                          "event": set().union(*self.work.events("handoff")),
                          "todo": set().union(*listed.lines)}, documented)

    def test_smoke(self):
        for name, first in (("answer", "Answer a handoff"), ("todo", "The open handoffs of a run")):
            r = smoke(name, "-h")
            self.assertEqual(r.code, 0, r)
            self.assertIn(first, r.out)


if __name__ == "__main__":
    unittest.main()
