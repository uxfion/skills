# Attachment titles: which of a paper's files an item keeps

An item may hold several files of one paper side by side, and its attachment titles are the only place that says which is which: `read_library pdf`, the report and the next import all read them back. A title says the file's version and where it came from, `<Version>-<Source>-<detail>` (`Preprint-arXiv-v7`, `Accepted-CVF`, `Published-Elsevier-in_press`); the scheme, the versions and the evidence that settles a file's version are paper-fetch's, which labels every file (its `references/attachment-titles.md`; `scripts/p2zlib/titles.py` is its copy of the scheme). Read this before cleaning or renaming an item's files (organize.md, *Attachment titles*). A title outside the scheme (Zotero's "Full Text PDF", an older run's "Preprint (arXiv)") says nothing about the version.

## Several files of one paper

- Different sources stand side by side: CycleGAN's `Preprint-arXiv-v7` and `Published-CVF` (ICCV 2017's watermark: identical to the IEEE Xplore version), and later `Published-IEEE`.
- One source keeps one file of the paper, the best and newest: the higher version first (Published, Accepted, Preprint, Unknown), then final over `in_press`, then the larger `vN`, then the later added. `Preprint-arXiv-v1` gives way to `Preprint-arXiv-v3`; `Accepted-Nature-in_press` to `Published-Nature`. A file without a `vN` beside one with a `vN`, alike otherwise, gives way to neither: both stay until its version is known. Supplements: one per source and detail. Snapshots: one per source; a snapshot that stood in for a missing PDF goes once a PDF of the paper is attached.
- What gives way is listed for cleaning (the report's 待清理附件, lint's `superseded` and `label_clash`) and goes to the trash only on the user's word.
- `read_library pdf` lists the files in that order; take the row of the version the task wants.
