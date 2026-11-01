# paper-to-zotero: the check cannot judge a one-word title, even with the DOI on page 1

> 已解决（2026-10-31）：spec `docs/specs/20261031-paper-skills-script-agent-division-spec.md` §3.1。核对拿不准的文件不再当错文件，写 `file` 交接给这篇的 paper agent，看前两页后答复；这里提的“加 DOI 规则”方向没有采纳。第一期验收实测的 Mask R-CNN 就走的这条路。


Logged 2026-10-30, while saving the baseline for the split (spec `20261030-paper-to-zotero-split-spec.md` §10 step 0). After the split this belongs to paper-fetch's `verify`.

**What was run.** `p2z.py fetch --pass 2` on `he2020mask` (Mask R-CNN, IEEE TPAMI, DOI `10.1109/TPAMI.2018.2844175`). The publisher route downloaded IEEE's own PDF through the institution's proxy.

**What was seen.** The claim went to `unverified/` with `check: cannot_judge`. `check_pdf --file` showed why: `title_words {"share": 1.0, "found": 1, "total": 1}`, `title_page: null`, `matched_title: null`, while page 1 carried `dois_on_page_1: ["10.1109/tpami.2018.2844175"]` (`doi_mismatch: false`), `first_author_found: true` and `first_author_in_byline: true`. Page 1 reads "IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 42, NO. 2 … Mask R-CNN … Kaiming He".

**Why it hurts.** The right file, from the publisher, waits for the agent to read it and `claim --accept` it, and the report lists it among the files the agent accepted. A title of one or two words ("Mask R-CNN", "U-Net", "YOLO9000") is common in this library's field.

**Direction.** When the title alone is too short to judge, let the DOI printed on page 1 matching the record's DOI, with the first author in the byline, settle it as `ok`; a DOI on page 1 is stronger evidence than title words anyway.

**Superseded direction (2026-10-30).** Adding a DOI-and-author rule to the check is a matcher for an uncertain branch; the user set the opposite: a file the check cannot judge goes to a subagent, the script only detects it. The redesign is tracked in `20261030-paper-fetch-script-agent-division.md`.
