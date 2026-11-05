# Several papers

Read before step 0 of [import.md](import.md) when the request covers two or more papers — a list, a .bib, a search result, "these three". This file says how import.md's steps run over many papers at once; paper-fetch's own `references/batch.md` says the same for its part: read it too.

## A paper's files, each with one writer

A paper is a result in `<imp>/fetch/results/<slug>.json`, written by paper-fetch (what the paper is, its versions, its files and their labels, how the fetching went), and a record in `<imp>/records/<slug>.json`, written by this skill and by you (the item, its destination, your decisions, what was saved and attached). Beside them, what other takers settle has files of its own: the paper's same-paper handoffs (`<imp>/handoffs/<slug>.<n>.json`), answered only through `p2z.py answer`, and its tags file (`<imp>/tags/<slug>.json`), written only by whoever tags it. What a record holds says how far its paper got in Zotero — `item` drafted, `found` in the library before this run, `checks` previewed, `saved` created, `attach` uploaded, `blocker` waiting on someone — and its result says how far the fetching got. Every script takes paths (glob them), skips what is already done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again. The scripts print one line per paper — read those, not the files.

## The run

**1. Triage** (you, the main agent, in minutes): identify every paper (import.md step 1; a .bib through `p2z.py ids`, a list as `id<TAB>citation key` lines on `identify`'s stdin), choose the versions (step 2), then draft and prepare (step 3): its `decide` lists say what is still open. Send the same-paper judges and the tagging subagents (step 3), who work beside the passes. Put every question in one message (below).

**2. First pass**: paper-fetch's chain over the results of the records that need a file (import.md step 4).

**3. Save what is in hand:** `p2z.py save <imp>/records/*.json`. Every paper gets its item now, with or without a file, once its tags file is there (`untagged` until then); run it again after each pass.

**4. Second pass**, then **save** again.

**5. Last pass, with the user**: one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere"), each record's `blocker` saying what it waits for; then paper-fetch's last pass with the user there; then **save**.

**6.** Report and clear residue (import.md steps 6–7).

## Ask once, then run

Identify all papers first, then put every question in one message: candidates to choose between, preprint-or-published pairs, published versions you could not confirm, destinations for papers the user did not place. When a stub's PDF will go to Zotero's recognizer (no-doi-record.md), the same message tells the user that the item it makes lands first in the collection selected in their Zotero window, and moves to its own collection afterwards. Scope the user has already set (SKILL.md, *Authorization*) — destination, version preference, what may be renamed or removed — covers every paper of the run; ask again only about a paper it does not cover. Nobody to ask → the published version, `tmp`, and say so in the report.

## What runs in parallel

The scripts that call Zotero in bulk (`prepare`, `save`) are yours, the main agent's, one at a time, like paper-fetch's (its batch.md, *What runs in parallel*). Subagents take the judgement beside them, reading only local files (SKILL.md, *Handoffs*): same-paper judges answer the library candidates in their handoffs, and for many papers tagging subagents write the papers' tags files (import.md step 3); none of them writes a record.

A paper the user downloads outside the run: paper-fetch identifies and claims it (its batch.md); then `draft`, `prepare` and `save` take it in here like the rest.

## Report

One report for the whole run (import.md step 6): the counts come from the read-back, and the per-paper details are the ones that matter — substitutions, sources named, gates hit — with the skill notes at the end.
