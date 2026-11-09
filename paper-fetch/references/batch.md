# Several papers

How SKILL.md's operations run over many results at once — a list, a .bib, a search result, "these three"; one paper is a batch of one.

## The results are the state

Every paper is one result file (SKILL.md, *The directory*), and every script takes result paths (glob them). What a result holds says how far its paper got: `csl` identified, `versions` listed, `files` and `outcome` folded from `<dir>/fetch.jsonl`, where every attempt is a line. Only `identify` and the fold write a result; the watcher and the agents append events through `pf.py` commands, so nothing collides.

Every script skips what is done and says so (`skipped`), so the same command line is also the recovery: after an interruption, a crash or a "继续", run it again, and `pf.py todo <dir>` shows what still waits for an agent. The scripts print one line per result: follow the run's progress in those lines, and open a result file only for what a line does not carry.

## The run

**1. Identify** (minutes):

```bash
printf '%s\n' <ids...> | pf.py identify -o <dir>/ -      # or `id<TAB>citation key` lines
pf.py locate <dir>/results/*.json
```

Pin the `needs_pinning` titles and settle the preprints' published versions as SKILL.md's *Identify a paper* says, every redraft done before fetching, so the chain looks for the version wanted. When you tell the user early what you foresee needing them for (SKILL.md), add how long the institutional routes will take: `fetch` spaces full-text requests through the institution 15 s apart (references/publishers.md, *Pacing*).

**2. First pass**, with the watcher running: SKILL.md's loop (*Get the file*) until `fetch` exits 0. The walk takes a route at a time across all the papers, the publisher pages a publisher at a time.

**3. Between passes** the caller takes what is in hand (paper-to-zotero saves the items and attaches the files).

**4. Second pass:** the same loop with `--pass 2` for the results still without a file; a paper that a `blocked` or `gate_timeout` held goes on from its route, with its own paper agent.

**5. Last pass, with the user** (SKILL.md, *Get the file*): one message for all the papers that remain ("3 wait for the institutional login, 2 were found nowhere").

**6.** `pf.py sync <dir>/results/*.json` once more, then clear the residue (SKILL.md, *Residue*).

## What runs in parallel

The commands that call outside services in bulk (`identify`, `locate`, `fetch`'s walk, and the `identify` and `redraft` runs an agent's file leads to) are yours, the main agent's, one at a time: each paces its requests through the machine's pace file and stops a service that answers 429. Beside them work the agents SKILL.md's *Handoffs* sends, as many at once as it says. Each agent works alone: it stops at its own block and reports it, and its paper waits on that route. A subagent reaches the user through you, the main agent, whose conversation is the one on the user's screen (references/gate.md).

## The user in the loop

In a batch the user often acts on a paper you have not reached yet — a PDF button, a download, a login; the watcher files what they download whenever it lands, and `fetch` skips that paper when its turn comes. A paper the user downloads that is not in the run, and then asks you to add: identify it, then `pf.py claim` the download into its result; a caller takes it on from there (paper-to-zotero: `p2z.py draft`, `prepare`, `save`).
