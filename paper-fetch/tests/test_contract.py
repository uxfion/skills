# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The result files paper-fetch hands its callers, made by its own scripts and kept as fixtures/results/: a caller
(paper-to-zotero's test_contract.py) reads them to prove it can consume what paper-fetch writes. This test makes
them again — identify, redraft, claim, accept, label and settle against the fake web — and fails when they are no
longer what is kept: then the format changed, and its callers must be checked. PF_REGEN_FIXTURES=1 writes them anew.

The kept results: liu2022jbhi (a journal article, slug given, its PDF labelled), shinn2023reflexion (an arXiv
preprint redrafted to its NeurIPS version, the preprint's file labelled, a supplement accepted), and a stub (no CSL
record, its file cannot_judge). Volatile fields (settled_at, evidence) are left out; the files are kept beside."""
import json
import os
import shutil
import unittest
from pathlib import Path

from helpers import call, fake_pdf, load, poppler_stubs
from test_identify import CSL, JBHI, NEURIPS, REFLEXION, Base

identify, claim, settle, answer = load("identify"), load("claim"), load("settle"), load("answer")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "results"
VOLATILE = ("settled_at",)


def kept(res):
    """A result as the fixture keeps it: without what changes from run to run."""
    out = {k: v for k, v in res.items() if k not in VOLATILE}
    out["files"] = [{k: v for k, v in f.items() if k != "evidence"} for f in out.get("files") or []]
    return out


class Contract(Base):
    def make(self):
        """The fixtures' results, made by paper-fetch's own scripts into self.work -> {slug: result}."""
        env = {**self.web.env(), "PATH": f"{poppler_stubs(self.work.root / 'bin')}:{os.environ['PATH']}"}
        inbox = self.work.root / "in"
        inbox.mkdir()

        def run_(module, *argv, stdin=""):
            r = call(module, *argv, env=env, stdin=stdin)
            self.assertNotEqual(r.code, 2, r)
            return r

        def label(slug, name, title, why):
            """The judge's answer to the label handoff the claim opened for a filed file."""
            md5 = run.md5_of(self.work.results / name)
            [h] = [h for h in run.open_handoffs(self.work, slug=slug) if h["kind"] == "label" and h["md5"] == md5]
            run_(answer, h["path"], "label", "--label", title, "--why", why, "--by", "judge")

        run_(identify, "-o", self.work.root, stdin=f"{JBHI}\tliu2022jbhi\n{REFLEXION}\n10.9999/html\n")
        reflexion = self.work.results / "shinn2023reflexion.json"
        run_(identify, "--redraft", NEURIPS, reflexion)
        title, author = CSL[JBHI]["title"], "Heng Liu"
        run_(claim, "--dir", self.work.root, "--file", fake_pdf(inbox / "liu.pdf", [f"{title}\n{author}"]), "--slug", "liu2022jbhi")
        label("liu2022jbhi", "liu2022jbhi.pdf", "Published-IEEE", "the volume and issue")
        pre = fake_pdf(inbox / "shinn.preprint.pdf", ["Reflexion: Language Agents with Verbal Reinforcement Learning\nNoah Shinn"])
        run_(claim, "--dir", self.work.root, "--file", pre, "--slug", "shinn2023reflexion")
        label("shinn2023reflexion", "shinn2023reflexion.preprint.pdf", "Accepted-arXiv-v4", "v4's comment")
        supp = fake_pdf(inbox / "shinn.supplement.pdf", ["Appendix A"])
        held = run_(claim, "--dir", self.work.root, "--file", supp, "--slug", "shinn2023reflexion").lines[0]
        run_(answer, self.work.handoffs / f"{held['handoff']}.json", "accept", "--reason", "the appendix", "--version",
             "supplement", "--label", "Supplement-NeurIPS", "--why", "the venue's appendix", "--by", "paper_agent")
        stub = next(p.stem for p in self.work.results.glob("*.json") if p.stem not in ("liu2022jbhi", "shinn2023reflexion"))
        run_(claim, "--dir", self.work.root, "--file", fake_pdf(inbox / "stub.pdf", ["Some paper"]), "--slug", stub)
        run_(settle, "--dir", self.work.root)
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.work.results.glob("*.json"))}

    def test_the_fixtures_are_what_paper_fetch_writes(self):
        made = {slug: kept(res) for slug, res in self.make().items()}
        self.assertEqual(sorted(made), ["109999html", "liu2022jbhi", "shinn2023reflexion"])
        self.assertEqual([(f["name"], f["check"], f["label"]["title"]) for f in made["shinn2023reflexion"]["files"]],
                         [("shinn2023reflexion.preprint.pdf", "ok", "Accepted-arXiv-v4"),
                          ("shinn2023reflexion.supplement.pdf", "accepted", "Supplement-NeurIPS")])
        self.assertEqual(made["109999html"]["files"][0]["check"], "cannot_judge")
        if os.environ.get("PF_REGEN_FIXTURES"):
            shutil.rmtree(FIXTURES, ignore_errors=True)
            FIXTURES.mkdir(parents=True)
            for slug, res in made.items():
                (FIXTURES / f"{slug}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                for f in res["files"]:
                    shutil.copy2(self.work.results / f["name"], FIXTURES / f["name"])
        have = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("*.json"))}
        self.assertEqual(made, have, "the result format changed: check its callers (paper-to-zotero's test_contract.py), "
                                     "then PF_REGEN_FIXTURES=1 writes the fixtures anew")
        for res in have.values():
            for f in res["files"]:
                self.assertEqual(run.md5_of(FIXTURES / f["name"]), f["md5"], f["name"])


from pflib import run  # noqa: E402  (after helpers put scripts/ on the path)

if __name__ == "__main__":
    unittest.main()
