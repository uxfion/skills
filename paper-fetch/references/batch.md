# Several papers

Read before *Ready* when the request covers two or more papers — a list, a .bib, a search result, "these three". One paper is a batch of one; nothing here contradicts SKILL.md, it only says how the operations run over many results at once.

## The results are the state

Every paper is one file, `<dir>/results/<slug>.json`, and every script takes result paths (glob them). What a result holds says how far its paper got: `csl` identified, `versions` listed, `files` and `outcome` folded from `fetch.jsonl`. The files sit beside it (`<slug>.pdf`, `.accepted.pdf`, `.preprint.pdf`, `.html`: the name carries the version it was wanted as), and every attempt is a line in `<dir>/fetch.jsonl`. Only `identify` and the fold write a result; the watcher and you append events, so nothing collides.

Every script skips what is done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again. The scripts print one line per result — read those, not the files.

## The run

**1. Identify** (minutes):

```bash
printf '%s\n' <ids...> | uv run scripts/pf.py identify -o <dir>      # or `id<TAB>slug` lines: a citation key as the slug
uv run scripts/pf.py fulltext_links <dir>/results/*.json
```

A `needs_pinning` line is a title: pin it (SKILL.md, *Identify a paper*) and identify its id. A preprint's `versions.published` is the caller's to choose from; once chosen, `identify --redraft` that result before fetching, so the chain looks for the version wanted. Say early what you foresee needing the user for ("8 of these go through the institutional login — if you can, log in now: Ctrl+N, a normal window") and how long the institutional routes will take: `fetch` spaces full-text requests through the institution 15 s apart (references/publishers.md, *Pacing*).

**2. First pass.** With the watcher running, `pf.py fetch --pass 1 <dir>/results/*.json` walks the chain (SKILL.md, *Get the file*) over the results without a file, a route at a time across all of them: the open published copies, the publisher pages (a publisher at a time), the discovery system, accepted manuscripts, preprints. When a browser route stops, the page is yours: look, act, record a conclusion with `--verdict`, and rerun the same command. Label each file in the pass that got it.

**3. Between passes** the caller takes what is in hand (paper-to-zotero saves the items and attaches the files then). Time passes before the next pass: a login, a rate limit or a flaky site may have recovered.

**4. Second pass:** the same chain with `--pass 2` for the results still without a file.

**5. Last pass, with the user** (SKILL.md, *Get the file*): one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere"), then `--pass 3` with the user there, the browser routes one paper at a time in the foreground; snapshots for what still has no file.

**6.** `pf.py settle --dir <dir>` once more, then clear the residue (SKILL.md, *Residue*).

## What runs in parallel

The scripts that call outside services in bulk (`identify`, `fulltext_links`, `fetch`'s open routes) run in the main conversation, one at a time: each paces its own requests and stops a service that answers 429, which only works while there is one caller. Subagents (at most five) take the judgment work beside it — checking published-version candidates on papers.cool, labelling files from their `to_label` lines — one request at a time per service. The browser has one driver, the main conversation: one gate at a time waits on the user, and a login passed once serves every paper behind it. Google Scholar only from the browser driver, at most once a minute across the run. A subagent that has to reach the user does so with `SendMessage` to the main conversation, the only one on the user's screen.

## The user in the loop

In a batch the user often acts on a paper you have not reached yet — a PDF button, a download, a login; the watcher files what they download whenever it lands (for any paper a route was tried for), and `fetch` skips that paper when its turn comes. A second copy of one paper goes to `<dir>/stray/`; a file that matches no paper or several stays in Downloads untouched, since it may be the user's own. A paper the user downloads that is not in the run, and then asks you to add: identify it, then `claim.py --file` the download.
