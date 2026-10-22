# Attachment titles: which version a file is, and where it came from

Read this before settling the first label of an import run (SKILL.md, step 3), and before renaming attachments in the library (organize.md, *Attachment titles*) or briefing a subagent for either. An item may hold several files of one paper side by side, and its attachment titles are the only place that says which is which: `read_library pdf`, the report and the next import all read them back.

## The scheme

`<Version>-<Source>-<detail>`: `Preprint-arXiv-v7`, `Accepted-CVF`, `Published-Elsevier-in_press`, `Preprint-OpenReview-ICLR_2027_submission`, `Supplement-Nature-source_data`, `Unknown`.

- Fields are separated by `-`. Inside a field, spaces and hyphens become `_` (`Europe_PMC`, `T_CAIREM`, `author_page`); other punctuation drops out.
- The version word is capitalized, exactly as below; the source keeps its own spelling (`arXiv`, `IEEE`, `eScholarship`).
- Detail comes only after a source: with the source unknown, the title is the version word alone (`Unknown`, `Published`).

**Version** (after NISO RP-8-2026; the definition decides, never a label someone else wrote):

| Version | What the file is | Examples |
|---|---|---|
| `Published` | the publisher's final form: the journal's, the proceedings', the final OpenReview version of an ICLR or TMLR paper. Typeset but not yet in an issue: add `in_press` | `Published-RSNA`, `Published-OpenReview-ICLR_2023`, `Published-Elsevier-in_press` |
| `Accepted` | the reviewed, accepted text, not in the publisher's final form: a PMC author manuscript, the CVF / ECVA / MICCAI open-access copy, an arXiv version that says it was accepted, an unedited early-online version | `Accepted-CVF`, `Accepted-arXiv-v3`, `Accepted-IEEE-in_press`, `Accepted-Europe_PMC` |
| `Preprint` | made public before acceptance: an arXiv preprint, an OpenReview submission. A preprint item's own PDF too | `Preprint-arXiv-v7`, `Preprint-OpenReview-ICLR_2027_submission` |
| `Unknown` | still undecided after looking; the file is attached all the same | `Unknown`, `Unknown-ResearchGate` |
| `Supplement` | supplementary material, not a version of the paper | `Supplement-Nature`, `Supplement-Nature-source_data` |
| `Snapshot` | a saved web page, not a version of the paper | `Snapshot-Elsevier` |

**Source**: the site the file was actually downloaded from, by a short brand name: arXiv, OpenReview, CVF, ECVA, MICCAI, NeurIPS, PMLR, ICLR, ACL, AAAI, JMLR, IEEE, Elsevier, Springer, Nature, ACM, Wiley, RSNA, BMJ, NEJM, Science, MDPI, JMIR, OUP, PMC, Europe_PMC, HAL, eScholarship, ResearchGate, Research_Square, EasyChair, author_page. A proxied address counts as the publisher's own (`ieeexplore-ieee-org.<proxy-domain>` is IEEE).

**Detail**, only where it tells files apart:
- `vN`: the preprint server's version. Always for arXiv, whose unversioned address follows the authors' updates.
- `in_press`: a version that will be replaced once the paper is in its issue (IEEE Early Access, Elsevier Article in Press, Nature Article in Press, Wiley Early View, ACM Just Accepted).
- the OpenReview status as OpenReview gives it: `ICLR_2023` for the final version, `ICLR_2027_submission` for a submission.
- `source_data` and the like: several supplements from one source.
- `abstract_booklet_p66`: one paper inside a collection.

Both lists are starting sets: name a new site or case on the same pattern, and say so in the report. `scripts/p2zlib/paper.py` (`SOURCES`) maps sites to names for the scripts' proposals.

## Several files of one paper

- Different sources stand side by side: CycleGAN's `Preprint-arXiv-v7` and `Accepted-CVF`, and later `Published-IEEE`.
- One source keeps one file of the paper, the best and newest: the higher version first (Published, Accepted, Preprint, Unknown), then final over `in_press`, then the larger `vN`, then the later added. `Preprint-arXiv-v1` gives way to `Preprint-arXiv-v3`; `Accepted-Nature-in_press` to `Published-Nature`. A file without a `vN` beside one with a `vN`, alike otherwise, gives way to neither: both stay until its version is known. Supplements: one per source and detail. Snapshots: one per source; a snapshot that stood in for a missing PDF goes once a PDF of the paper is attached.
- What gives way is listed for cleaning (the report's 待清理附件, lint's `superseded` and `label_clash`) and goes to the trash only on the user's word.
- `read_library pdf` lists the files in that order; take the row of the version the task wants.

## Evidence

The scripts record facts and propose; the version is yours to settle.

- **The proposal** in a claim event (and a `to_label` line) comes from the route and the site alone: a file from arXiv, bioRxiv or medRxiv → Preprint, whichever route reached it; otherwise `publisher` → Published, `accepted` → Accepted, `preprint` → Preprint, everything else Unknown; the source from the download url's site, `vN` from an arXiv url. It is a starting point and is often wrong: an arXiv copy of the final text is Accepted, an Early Access PDF from the publisher route may be the unedited manuscript.
- **What settles it**, strongest first:
  - the same bytes (md5) as a file whose version is known;
  - the hosting site's own word on the file: the label beside the PDF button, the link text clicked ("View Open Manuscript"), a conference's open-access page, a repository's file label, the page's volume and issue (none yet: in press);
  - page 1 and 2: a banner ("This is the author's version which has not been fully edited"), a conference header ("Published as a conference paper at ICLR 2023", "Under review"), the journal's running head with volume and pages, arXiv's stamp (`arXiv:<id>vN [cs.CV] <date>`: the source and vN, not the stage);
  - the file's own dates (`pdf_dates`) against submission, acceptance and publication.
- **Says nothing**: Unpaywall's and OpenAlex's version fields (2 of 16 matched the file, 2026-10), and the titles Zotero writes from them ("Submitted Version", "Accepted Version", "Full Text PDF", "已提交版本").
- Markers seen on particular publishers' pages and files are dated hints in [publishers.md](publishers.md), *Versions on the page and on the file*; the page in front of you wins over them.
