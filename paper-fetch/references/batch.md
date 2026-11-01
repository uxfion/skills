# Several papers

Read before *Ready* when the request covers two or more papers — a list, a .bib, a search result, "these three". One paper is a batch of one; nothing here contradicts SKILL.md, it only says how the operations run over many results at once.

## The results are the state

Every paper is one file, `<dir>/results/<slug>.json`, and every script takes result paths (glob them). What a result holds says how far its paper got: `csl` identified, `versions` listed, `files` and `outcome` folded from `fetch.jsonl`. The files sit beside it, named by the version each was wanted as (`<slug>.pdf`, `.accepted.pdf`, `.preprint.pdf`, `.html`; a second file of one kind `<slug>.2.pdf`); every attempt is a line in `<dir>/fetch.jsonl`; what waits for an agent is a record in `<dir>/handoffs/`. Only `identify` and the fold write a result; the watcher and the agents append events through `pf.py` commands, so nothing collides.

Every script skips what is done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again, and `pf.py todo --dir <dir>` shows what still waits for an agent. The scripts print one line per result — read those, not the files.

## The run

**1. Identify** (minutes):

```bash
printf '%s\n' <ids...> | uv run scripts/pf.py identify -o <dir>      # or `id<TAB>key` lines: a citation key, kept as given in `cite`
uv run scripts/pf.py fulltext_links <dir>/results/*.json
```

A `needs_pinning` line is a title: pin it (SKILL.md, *Identify a paper*) and identify its id. A caller that keeps the preprint passes `--wanted preprint`. A preprint's `versions.published` is the caller's to choose from (a judge checks the candidates); once chosen, `identify --redraft` that result before fetching, so the chain looks for the version wanted. Say early what you foresee needing the user for ("8 of these go through the institutional login — if you can, log in now: Ctrl+N, a normal window") and how long the institutional routes will take: `fetch` spaces full-text requests through the institution 15 s apart (references/publishers.md, *Pacing*).

**2. First pass.** With the watcher running, SKILL.md's loop (*Get the file*): `pf.py fetch --pass 1 <dir>/results/*.json`, then `pf.py todo --dir <dir>`, paper agents, then judges for what they left, then the same `fetch` again until it exits 0. The walk takes a route at a time across all the papers: the open published copies, the publisher pages (a publisher at a time), the discovery system, accepted manuscripts, preprints.

**3. Between passes** the caller takes what is in hand (paper-to-zotero saves the items and attaches the files then). Time passes before the next pass: a login, a rate limit or a flaky site may have recovered.

**4. Second pass:** the same loop with `--pass 2` for the results still without a file; a paper that a `blocked` or `gate_timeout` held goes on from its route, with its own paper agent.

**5. Last pass, with the user** (SKILL.md, *Get the file*): one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere"), then `--pass 3` with the user there, the pages in the foreground; snapshots for what still has no file.

**6.** `pf.py settle --dir <dir>` once more, then clear the residue (SKILL.md, *Residue*).

## What runs in parallel

The scripts that call outside services in bulk (`identify`, `fulltext_links`, `fetch`'s walk) run in the main conversation, one at a time: each paces its requests through the machine's pace file and stops a service that answers 429. Beside them work up to five paper agents, each with its own paper and its own browser session (`pf-<slug>`), by hand on the web, and up to five judges, which read only local files, about twenty handoffs each. Agents do not coordinate: each stops at its own block and reports it, and its paper waits on that route. Google Scholar only by hand, at most once a minute. A subagent that has to reach the user does so with `SendMessage` to `"main"`, the only conversation on the user's screen, which pushes the alert: a subagent has no push notification of its own.

## The user in the loop

In a batch the user often acts on a paper you have not reached yet — a PDF button, a download, a login; the watcher files what they download whenever it lands (for any paper `fetch` was asked for and that is not yet satisfied), and `fetch` skips that paper when its turn comes. A file that matches no waiting paper, or several, stays in Downloads untouched, since it may be the user's own; a `left` handoff asks a judge whose it is. A paper the user downloads that is not in the run, and then asks you to add: identify it, then `claim --file` the download; a caller takes it on from there (paper-to-zotero: draft_item, prepare, save).
