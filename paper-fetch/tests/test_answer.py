# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for scripts/answer.py and scripts/todo.py: each kind of handoff answered, what an answer does to the paper
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

    def held(self, slug, name, text):
        r = call(claim, "--dir", self.work.root, "--file", fake_pdf(self.work.inbox / name, [text]), "--slug", slug)
        self.assertEqual(r.lines[0]["result"], "held", r)
        return self.work.handoffs / f"{r.lines[0]['handoff']}.json"

    def answer(self, handoff, word, *argv):
        return call(answer, handoff, word, *argv)

    def todo(self, *argv):
        return call(todo, "--dir", self.work.root, *argv)

    def test_a_held_file_accepted_refused_or_unknown(self):
        handoff = self.held("paper", "scan.pdf", "A scanned first page")
        listed = self.todo()
        self.assertEqual((listed.code, [(x["id"], x["kind"], x["taker"]) for x in listed.lines[:-1]]),
                         (1, [("paper.1", "file", "paper_agent")]))
        r = self.answer(handoff, "accept", "--reason", "page 1 is the paper, a scan", "--label", "Published-IEEE",
                        "--why", "page 1: vol. 12 no. 3", "--by", "paper_agent")
        self.assertEqual((r.code, [e["event"] for e in r.lines]), (0, ["accept", "label", "answer"]), r)
        [f] = self.res("paper")["files"]
        self.assertEqual((f["name"], f["check"], f["label"]["title"], f["accepted_reason"]),
                         ("paper.pdf", "accepted", "Published-IEEE", "page 1 is the paper, a scan"))
        self.assertTrue(run.satisfied(self.work, self.res("paper")))
        self.assertEqual((self.todo().code, self.answer(handoff, "refuse").lines[0]["code"]), (0, "not_open"))
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
        call(claim, "--dir", self.work.root, "--file", good, "--slug", "other")
        self.assertEqual([(f["name"], f["check"]) for f in self.res("other")["files"]], [("other.pdf", "ok")])
        self.assertEqual([e["event"] for e in self.work.events() if e["event"] == "withdraw"], ["withdraw"])

    def test_labels_decide_whether_the_paper_goes_on(self):
        good = fake_pdf(self.work.inbox / "a.pdf", [f"{TITLE}\nWei Liu"])
        call(claim, "--dir", self.work.root, "--file", good, "--slug", "paper")
        self.assertTrue(run.satisfied(self.work, self.res("paper")), "an unlabelled file holds the paper")
        f = self.work.results / "paper.pdf"
        label = lambda: run.handoff(self.work, "label", self.res("paper"), file=f, md5=run.md5_of(f))  # noqa: E731
        h = label()
        r = self.answer(self.work.handoffs / f"{h['id']}.json", "label", "--label", "Accepted-arXiv-v2", "--why", "v2's comment")
        self.assertEqual(r.code, 0, r)
        self.assertFalse(run.satisfied(self.work, self.res("paper")), "an accepted manuscript: the paper goes on (decision A)")
        second = fake_pdf(self.work.inbox / "b.pdf", [f"{TITLE}\nWei Liu, the journal's"])
        call(claim, "--dir", self.work.root, "--file", second, "--slug", "paper")
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
        r = call(answer, page["id"], "blocked", "--dir", self.work.root, "--reason", "a bot check on the publisher")
        self.assertEqual(([e["event"] for e in r.lines], r.lines[0]["result"]), (["try", "answer"], "blocked"))
        self.assertTrue(run.held_on_route(self.work, "paper", 1), "a block holds the paper on its route this pass")
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
        self.assertEqual([(x["slug"], x["kind"]) for x in self.todo().lines[:-1]], [("other", "label")],
                         "what is left: the label of the file the download became")
        self.assertEqual(call(answer, "nope.1", "resolved", "--dir", self.work.root).lines[0]["code"], "no_such_handoff")
        self.assertEqual(call(answer, "paper.1", "resolved").code, 2, "an id needs --dir")

    def test_smoke(self):
        for name, first in (("answer", "Answer a handoff"), ("todo", "List a directory's open handoffs")):
            r = smoke(name, "--help")
            self.assertEqual(r.code, 0, r)
            self.assertIn(first, r.out)


if __name__ == "__main__":
    unittest.main()
