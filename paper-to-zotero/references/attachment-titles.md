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
| `Published` | the publisher's final form: the journal's, the proceedings', the final OpenReview version of an ICLR or TMLR paper, a CVF copy whose watermark says it is "identical to the version available on IEEE Xplore" (CVPR and ICCV up to 2018). Typeset but not yet in an issue: add `in_press` | `Published-RSNA`, `Published-OpenReview-ICLR_2023`, `Published-CVF`, `Published-Elsevier-in_press` |
| `Accepted` | the reviewed, accepted text, not in the publisher's final form: a PMC author manuscript, a CVF copy whose watermark says "identical to the accepted version" (2019 on) or calls it "the author-created version" (ECCV 2018, ACCV), the MICCAI and ECVA open-access copies, an arXiv version that says it was accepted, an unedited early-online version | `Accepted-CVF`, `Accepted-arXiv-v3`, `Accepted-IEEE-in_press`, `Accepted-Europe_PMC` |
| `Preprint` | an author's own release that does not say it was accepted: before acceptance (an arXiv preprint, an OpenReview submission), or extended or revised after it without saying so (CycleGAN's arXiv v7 of 2020, the ICCV 2017 text with an appendix). A preprint item's own PDF too | `Preprint-arXiv-v7`, `Preprint-OpenReview-ICLR_2027_submission` |
| `Unknown` | still undecided after looking; the file is attached all the same | `Unknown`, `Unknown-ResearchGate` |
| `Supplement` | supplementary material, not a version of the paper | `Supplement-Nature`, `Supplement-Nature-source_data` |
| `Snapshot` | a saved web page, not a version of the paper | `Snapshot-Elsevier` |

**Source**: the site the file was actually downloaded from, by a short brand name: arXiv, OpenReview, CVF, ECVA, MICCAI, NeurIPS, PMLR, ICLR, ACL, AAAI, JMLR, IEEE, Elsevier, Springer, Nature, BMC, ACM, Wiley, RSNA, BMJ, NEJM, Science, PNAS, PLOS, IOP, SPIE, Thieme, Frontiers, MDPI, JMIR, OUP, medRxiv, SSRN, PMC, Europe_PMC, HAL, eScholarship, Lirias, ResearchGate, Research_Square, EasyChair, ProQuest, EBSCO, author_page. A proxied address counts as the publisher's own (`ieeexplore-ieee-org.<proxy-domain>` is IEEE); a database's download (ProQuest, EBSCO) is the database's, whoever typeset the file.

**Detail**, only where it tells files apart:
- `vN`: the preprint server's version. Always for arXiv, whose unversioned address follows the authors' updates.
- `in_press`: a version that will be replaced once the paper is in its issue (IEEE Early Access, Elsevier Article in Press, Nature Article in Press, Wiley Early View, ACM Just Accepted).
- the OpenReview status, on every file from OpenReview: the venue and year (`ICLR_2023`, `NeurIPS_2025`; TMLR has no year: `TMLR`) for a final version, `ICLR_2027_submission` for a submission. One OpenReview address serves the submission, its revisions and the final version in turn, and OpenReview hosts many venues, so the status says which file this is. Page 1 gives it ("Published as a conference paper at ICLR 2023", "Under review as a conference paper at ICLR 2027", NeurIPS's and ICML's first-page footnote, "Published in Transactions on Machine Learning Research"), else OpenReview's `venue` field.
- `source_data` and the like: several supplements from one source.
- `abstract_booklet_p66`: one paper inside a collection.

Both lists are starting sets: name a new site or case on the same pattern, and say so in the report. `scripts/p2zlib/paper.py` (`SOURCES`) maps sites to names for the scripts' proposals.

## Several files of one paper

- Different sources stand side by side: CycleGAN's `Preprint-arXiv-v7` and `Published-CVF` (ICCV 2017's watermark: identical to the IEEE Xplore version), and later `Published-IEEE`.
- One source keeps one file of the paper, the best and newest: the higher version first (Published, Accepted, Preprint, Unknown), then final over `in_press`, then the larger `vN`, then the later added. `Preprint-arXiv-v1` gives way to `Preprint-arXiv-v3`; `Accepted-Nature-in_press` to `Published-Nature`. A file without a `vN` beside one with a `vN`, alike otherwise, gives way to neither: both stay until its version is known. Supplements: one per source and detail. Snapshots: one per source; a snapshot that stood in for a missing PDF goes once a PDF of the paper is attached.
- What gives way is listed for cleaning (the report's 待清理附件, lint's `superseded` and `label_clash`) and goes to the trash only on the user's word.
- `read_library pdf` lists the files in that order; take the row of the version the task wants.

## Evidence

A version is settled from two words: **the host's word** — what the site that served the file says about it: its page's labels, dates, volume and issue, the link that was taken, its metadata; for an arXiv file, arXiv's comment on that version — and **the file's word**: pages 1 and 2, its dates, its stamps. The scripts record both and propose; the version is yours to settle.

**A file being fetched: the host's word first.** At download it describes this very file, and it says most: a page labels a version before the PDF does ("Early Access", "In Press, Journal Pre-proof", "Just Accepted", "View Open Manuscript"), and arXiv's comment says what the authors did with that version ("Accepted at CVPR 2025"). A claim event records it and its `to_label` line shows it (`page`, `meta`, `words`, `link`); the file's word follows (`stamp`, `dates`, `head`) to confirm it or to settle what the page left open. The `proposal` comes from the route and the site alone (a file from arXiv, bioRxiv or medRxiv → Preprint whichever route reached it; otherwise `publisher` → Published, `accepted` → Accepted, `preprint` → Preprint, everything else Unknown; the source from the download url's site, `vN` from an arXiv url): a starting point, often wrong — an arXiv copy of the final text is Accepted, an Early Access PDF from the publisher route may be the unedited manuscript.

**A file already in the library: the file's word first.** Only the file is left, and a site seen now speaks of what it serves today: an in-press page has become the final one, an unversioned arXiv or OpenReview address serves the latest revision. A site labels a file in hand only once it is shown to serve that same file (the same bytes, or the same pages). What does not change goes along with the file: arXiv's comment on that version.

Reading the file's word:
- Look at pages 1 and 2 as images (`pdftoppm -f 1 -l 2 -r 120 -png <file> <prefix>`, or the `pdf` skill), beside their text. A mark is often an image or sits where the text layer misses it: the CVF and MICCAI watermarks, Elsevier's grey ARTICLE IN PRESS bar. A file arXiv compiled keeps its marks in its text.
- Template text misleads: elsarticle prints "Preprint submitted to <journal>" on accepted manuscripts too, and the NeurIPS template's "Preprint." line stays until the authors switch to the final option: a version whose arXiv comment says it was accepted is Accepted all the same. An attachment's url is where the item lives or the page it was saved from, not proof of the file: a file under a CVF url may carry no CVF watermark at all.

What settles a version, strongest first:
- the same bytes (md5) as a file whose version is known;
- the host's own word on this file: the label beside the PDF button, the link text taken, the page's volume and issue (none yet: in press), a conference's open-access page, a repository's file label, arXiv's comment on the version;
- the file's own marks: a banner ("This is the author's version which has not been fully edited"), a watermark (CVF's, MICCAI's), a conference header ("Published as a conference paper at ICLR 2023", "Under review"), a running head or citation line with volume and pages ("Radiology 2022; 000:1–8": no volume yet, in press), a repository's stamp ("Version of Record: …", "HHS Public Access / Author manuscript"), arXiv's stamp (`arXiv:<id>vN [cs.CV] <date>`: the source and vN, not the stage);
- the file's dates (`pdf_dates`) against submission, acceptance and publication.

Unpaywall's and OpenAlex's version fields say nothing (2 of 16 matched the file, 2026-10), nor do the titles Zotero writes from them ("Submitted Version", "Accepted Version", "Full Text PDF", "已提交版本"). The words particular publishers use are dated hints in [publishers.md](publishers.md), *Versions on the page and on the file*; the page and the file in front of you win over them.
