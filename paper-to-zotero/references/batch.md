# Several papers

Read before step 0 when the request covers two or more papers — a list, a .bib, a search result, "these three". One paper is a batch of one; nothing here contradicts the steps, it only says how they run over many records at once.

## The records are the state

Every paper is one file, `<work>/records/<slug>.json`, and every script is a filter over records: paths in (glob them), the updated record out, `-i` to write it back in place. What a record holds says how far its paper got — `item` drafted, `published_candidates` listed, `found` in the library before this run, `links` listed, `pdf` checked, `saved` created, `attach` uploaded, `blocker` waiting on someone. Files are not record fields: a paper's file is `records/<slug>.pdf` (or `.accepted.pdf`, `.preprint.pdf`, `.html` for a snapshot) — its name carries its version — and every fetching attempt is a line in `<work>/fetch.jsonl`. So the scripts that fetch never write records, and subagents editing records never collide with them.

Every script skips what is already done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again. With `-i` the scripts print one summary line per record — read those, not the files.

A .bib or .ris the user has is a list source, not something to import as is: `p2z.py doi_to_item --bib ref.bib --out-dir <work>/records` takes each entry's DOI (else arXiv id, else title) as the identifier and its citation key as the slug and `citationKey`, so the created items carry the keys the manuscript cites.

## The run

**1. Triage** (main conversation, minutes):

```bash
uv run scripts/p2z.py doi_to_item --ids ids.txt --out-dir <work>/records       # `id<TAB>citation key` per line
uv run scripts/p2z.py prepare <work>/records/*.json
```

Settle the versions now, before anything is created (step 2 of SKILL.md): each arXiv record's `published_candidates`, checked against its arXiv comment; papers.cool's venue search for the rest, one request at a time; `--redraft` the ones you confirm, write `keep_preprint` for the rest, then `prepare` again: its `decide` lists say what is still open. Put every question in one message (below). And say early what you foresee needing the user for ("8 of these go through the institutional login — if you can, log in now: Ctrl+N, a normal window") and how long the institutional routes will take: `fetch` spaces full-text requests through the institution 15 s apart (references/publishers.md, *Pacing*).

**2. First pass.** With the watcher of step 0 running, `p2z.py fetch --pass 1 <work>/records/*.json` walks the chain (SKILL.md step 3) over the records that have no file, a route at a time across all of them: the open published copies, the publisher pages (a publisher at a time), the discovery system, accepted manuscripts, preprints. When a browser route stops, the page is yours (SKILL.md step 3): look, act, record a conclusion with `--verdict`, and rerun the same command.

**3. Save what is in hand:** `p2z.py save <work>/records/*.json`. Every paper gets its item now, with or without a file; run it again after each pass.

**4. Second pass:** the same chain with `--pass 2` for the records still without a file. Time has passed since the first: a login, a rate limit or a flaky site may have recovered.

**5. Last pass, with the user** (SKILL.md step 3): one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere"), then `--pass 3` with the user there, the browser routes one paper at a time in the foreground; snapshots for what still has no file.

**6.** Report and clear residue (SKILL.md steps 5–6; `p2z.py claim --sweep` lists what is left in Downloads).

## Ask once, then run

Pin all papers first (step 1 for each), then put every question in one message: candidates to choose between, preprint-or-published pairs, published versions you could not confirm, destinations for papers the user did not place. Scope the user has already set — destination, version preference, what may be renamed or removed — holds for the whole run; ask again only about a paper it does not cover. Nobody to ask → the published version, `tmp`, and say so in the report.

## What runs in parallel

The scripts that call outside services in bulk (`prepare`, `fetch`'s open routes) run in the main conversation, one at a time: each paces its own requests and stops a service that answers 429, which only works while there is one caller. Subagents (at most five) take the judgment work beside it — tags, abstracts, checking published-version candidates on papers.cool — one request at a time per service. The browser has one driver, the main conversation: one gate at a time waits on the user, and a login passed once serves every paper behind it. Google Scholar only from the browser driver, at most once a minute across the run. A subagent that has to reach the user does so with `SendMessage` to the main conversation, the only one on the user's screen.

## The user in the loop

In a batch the user often acts on a paper you have not reached yet — a PDF button, a download, a login; the watcher files what they download whenever it lands, and `fetch` skips that paper when its turn comes. A second copy of one paper goes to `<work>/stray/`; a file that matches no paper or several stays in Downloads untouched, since it may be the user's own. A paper the user downloads that is not in the run, and then asks you to add: draft its record (steps 1–2); the watcher checks the file again against the new record and files it.

## Report

One report for the whole run (SKILL.md step 5): the counts come from the read-back, and the per-paper details are the ones that matter — substitutions, sources named, gates hit — with the skill notes at the end.
