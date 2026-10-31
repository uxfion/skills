# Several papers

Read before step 0 of [import.md](import.md) when the request covers two or more papers — a list, a .bib, a search result, "these three". One paper is a batch of one; nothing here contradicts import.md, it only says how its steps run over many papers at once. paper-fetch's own `references/batch.md` says the same for its part: read it too.

## Two files per paper, each with one writer

A paper is a result in `<imp>/fetch/results/<slug>.json`, written by paper-fetch (what the paper is, its versions, its files and their labels, how the fetching went), and a record in `<imp>/records/<slug>.json`, written by this skill and by you (the item, its destination, your decisions, what was saved and attached). What a record holds says how far its paper got in Zotero — `item` drafted, `found` in the library before this run, `checks` previewed, `saved` created, `attach` uploaded, `blocker` waiting on someone — and its result says how far the fetching got. Every script takes paths (glob them), skips what is already done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again. The scripts print one line per paper — read those, not the files.

## The run

**1. Triage** (main conversation, minutes): identify every paper (import.md step 1; a .bib through `read_bib`, a list as `id<TAB>citation key` lines on `identify`'s stdin), choose the versions (step 2), then draft and prepare (step 3): its `decide` lists say what is still open. Put every question in one message (below).

**2. First pass**: paper-fetch's chain over the results of the records that need a file (import.md step 4).

**3. Save what is in hand:** `p2z.py save <imp>/records/*.json`. Every paper gets its item now, with or without a file; run it again after each pass.

**4. Second pass**, then **save** again.

**5. Last pass, with the user**: one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere"), each record's `blocker` saying what it waits for; then paper-fetch's last pass with the user there; then **save**.

**6.** Report and clear residue (import.md steps 6–7).

## Ask once, then run

Identify all papers first, then put every question in one message: candidates to choose between, preprint-or-published pairs, published versions you could not confirm, destinations for papers the user did not place. Scope the user has already set — destination, version preference, what may be renamed or removed — holds for the whole run; ask again only about a paper it does not cover. Nobody to ask → the published version, `tmp`, and say so in the report.

## What runs in parallel

The scripts that call Zotero in bulk (`prepare`, `save`) run in the main conversation, one at a time, like paper-fetch's (its batch.md, *What runs in parallel*). Subagents take the judgment work beside them — tags, abstracts — and edit only the records' agent fields.

## Report

One report for the whole run (import.md step 6): the counts come from the read-back, and the per-paper details are the ones that matter — substitutions, sources named, gates hit — with the skill notes at the end.
