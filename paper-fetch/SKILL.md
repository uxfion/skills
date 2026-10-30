---
name: paper-fetch
description: Finds out which paper is meant and gets its full text — DOI or arXiv id, normalized CSL metadata, preprint and published versions, then a PDF checked against the paper and labelled with its version, by open copies, the publisher through the institution's login, the library's discovery system or the user's browser. Use when a paper has to be pinned down from a title, list or link, its metadata or versions looked up, or its PDF fetched (找论文 PDF、下载全文、查 DOI 和正式版), or files someone has labelled by version; paper-to-zotero calls it when importing.
---

# Paper fetch

From "a paper" to a file of it you can trust: which paper it is, what is known about it, which versions exist, and its PDF, checked against the paper and labelled with the version it is. Everything that touches the web is here; Zotero is paper-to-zotero's. Script paths are relative to this file's directory: `cd` there at the start of every shell call. `uv run scripts/pf.py --help` lists every script; each script's `--help` is the reference for its flags, codes and output.

| operation | where |
|---|---|
| Identify a paper (a title, a link, an id) | *Identify a paper* below |
| Get its file | *Ready*, then *Get the file: the chain* below |
| Label files someone already has (a library's PDFs, the user's own) | *Label files you already have* below |
| Many papers, in passes | references/batch.md, before *Ready* |
| A page only the user can pass | references/gate.md |
| Identify only, no file | references/identify.md |

**The directory.** A run lives in one directory, `<dir>`: the caller's (an import: `<scratch>/paper-to-zotero/fetch/`), else `<scratch>/paper-fetch/` — `<scratch>` is the session's scratchpad, else `${TMPDIR:-/tmp}`. Each paper is one result file, `<dir>/results/<slug>.json`, with its file beside it; a caller reads `results/` and nothing else (`scripts/pflib/run.py` documents the format). The slug is the caller's (a citation key) or `<surname><year><first title word>`.

**The user helps; the work is yours.** The run is the same whether or not the user is watching: you fetch every paper yourself. The user may log in, pass a CAPTCHA or click a download at any moment, and that only speeds things up — the watcher files their downloads. Say early what you can foresee needing them for ("3 of these need the institutional login — if you can, log in now: Ctrl+N, a normal window"). Only the last pass waits for them.

## Instruments

- `opencli-usage` skill — web access: discover adapters at run time (`opencli list <query>`: JSON, paged with `--offset`). Seen in 2026-09: API-type `arxiv`, `openalex`, `semanticscholar` (429 without a key — one 429 means skip it), `pubmed` (abstract, author keywords, PMID), `dblp`, `openreview`, `hf paper`; browser-type `google-scholar`, `cnki`, `wanfang`. Behind a proxy every call prints a harmless `UNDICI-EHPA` warning on stderr: send stderr to `<dir>/scratch/opencli.log`.
- `opencli-browser` skill — the user's real, logged-in Chrome: `browser <command> --session pf` with `open / state / find / get / click / wait / eval / tab / close`, `web read --url`. Windows open in the background (`--window background`), so the user's focus stays theirs; the last pass opens them in the foreground for the user.
- `pdf` skill — reading a page of a file the check refused or could not read.
- `papers-cool-search` skill — papers.cool search and venue listings as JSON, one request at a time.

Read [references/publishers.md](references/publishers.md) whenever a publisher page is yours to work (`fetch` stopped on it, a discovery system, a click), and [references/install.md](references/install.md) when `ready` reports something missing.

## Identify a paper

Treat the user's words as a draft: typos, partial titles and loose keywords are normal, so reformulate and search again before concluding anything. Search along the ladder in *Reaching a page*: metadata APIs and API-type adapters first, `google-scholar` and other browser-type adapters next, `opencli browser` last. A journal or conference title is usually pinned in one Crossref call (`uv run scripts/pf.py identify --search "<title>" --author <surname>`). An arXiv-style title: papers.cool is a fast first stop (`uv run <papers-cool-search dir>/scripts/papers_cool_fetch.py search "<3-6 title words>" --show 5`); its search has no title weighting, carries no DOI and does not index authors, so confirm the title yourself. Several plausible candidates, or none you would stake the result on: show the top few (title, authors, year, venue) and let the user choose.

```bash
uv run scripts/pf.py identify <DOI | arXiv id | paper page> [--slug <citation key>] -o <dir>
```

`identify` writes the result: the paper's CSL metadata (from doi.org, or the page's `citation_*` tags), its ids and, for a preprint, its versions — `versions.published`, the published versions the authors declared to arXiv or Crossref's title search found. The published version comes first unless the user asked for the preprint: confirm a candidate against arXiv's comment ("Accepted at ICLR 2024", in `versions.preprint.comment`) and its title; none, but the comment or the paper names a venue → papers.cool's venue search or the venue's own listing finds the paper's page. Confirmed → `identify --redraft <DOI | page url> <result>`. When a caller decides the version (paper-to-zotero does), its rule wins and you redraft on its word. `versions.incomplete` names sources that did not answer: identify the same id again later. A stub (`no_csl_record`, `page_unreachable`, `no_citation_meta`): the paper has no metadata to check a file against; its files are filed as `cannot_judge`.

Abstract, author keywords and PMID, when a caller wants them and the CSL lacks them: `openalex work` / `pubmed search` + `pubmed article <pmid> --full-abstract` (journal articles) / `semanticscholar paper` / `hf paper`, before opening the article page; the page for what only it has.

Done when every paper is pinned by a DOI, an arXiv id or its page, every distinguishing word of the request matches it, no other result fits equally well, and its result is written (the version settled where the caller asked for one).

## Ready

```bash
uv run scripts/pf.py ready --dir <dir>
uv run scripts/pf.py claim --dir <dir> --watch                    # in the background, the whole run
```

`ready` checks poppler and OpenCLI, prepares `<dir>` (`results/`, `links/`, `inbox/`, `stray/`, `unverified/`, `scratch/`, the `.started` marker, `run.json` with the Downloads folder and the browser session) and prints `downloads_dir`. Act on what it reports: `config.ask_user` (the library's discovery search page: ask for it in your first message and add it to the config); `no_pdftotext`, OpenCLI issues: references/install.md, the user's to install on their word, an old daemon → `opencli daemon restart`; `resumed: true` — an earlier run left `<dir>`: carry on from its results; `leftovers` are reported, never deleted: a PDF that never reached the user belongs to them.

The **watcher** files every new PDF in Downloads that matches exactly one paper `fetch` was asked for and that has no file yet — your downloads and the user's alike. Start it as a background process that lives as long as the run. Where the harness can stream a command's lines to you as events (Claude Code: the Monitor tool), also follow the log, re-armed whenever it expires:

```bash
tail -n 0 -F <dir>/fetch.jsonl | grep --line-buffered -E '"result": "(claimed|left)"'
```

`claimed`: that paper has its file — drop whatever you were doing for it. `left`: a new file matched no paper, or several — look at it. An event never interrupts a running command, so whatever waits looks for the file itself. The watcher only appends events: `settle.py` folds them into the results (`fetch`, `claim` and `wait` fold what they touched when they end).

Done when `ready` reports `ok` and the watcher runs.

## Get the file: the chain

The **chain** is the order of routes to a paper's full text; one walk down it is a **pass**, and a paper's pass stops at the first route that yields a file:

1. `open` — an open copy of the published version (the paper's links, then those of unknown version);
2. `publisher` — the publisher's page through the institution's login, in the `pf` session;
3. `discovery` — the library's discovery system, its own full-text links (skipped while `institution.discovery` is unset: ask the user for it);
4. `accepted` — the accepted manuscript;
5. `preprint` — the preprint, last.

```bash
uv run scripts/pf.py fulltext_links <dir>/results/*.json      # where copies may be had
uv run scripts/pf.py fetch --pass N <dir>/results/*.json
```

One command walks the whole pass: each route over every paper still without a file, then the next. On a page it takes whatever PDF the page offers — the declared PDF, an embedded viewer, a "PDF" link and the reading page behind it — and every file goes through the check, so a wrong guess costs nothing. An alternate version counts as obtained: its file name carries the version it was wanted as (`<slug>.accepted.pdf`, `<slug>.preprint.pdf`); what it actually is goes into its label.

**Scripts first, then a browser agent, then the user.** `fetch` never judges a page. When it stops (`{"code": "stopped", "slug", "route", "why", "gate", "url", "title"}`), the tab stays on that page. If the paper's file has arrived meanwhile (`results/<slug>.*` or a `claimed` event), rerun the command; a stop with `gate: true` is in front of the user already: references/gate.md. Any other page needs looking and clicking — a sign-in that the institution's single sign-on can pass is one of those: give each stop to its own **browser agent**, a background subagent on a cheap model (Claude Code: `model: "sonnet"`; Codex: `luna`), while you keep your model and stay with the user; without subagents, be the browser agent yourself. Its brief:

- the stop line, the paper (title, DOI, the version wanted) and the session `pf`; first read references/publishers.md and references/gate.md, and *Agents you send* below;
- read the page through `opencli browser <command> --session pf` (`state`, `find`, `get`, `eval`; a screenshot only to confirm what those say), and click with `click --role … --name …` or a ref from the `state` just read (refs go stale);
- follow the paper to its file: a site's sign-in and the institution's choice in its login dialog, a cookie banner, the record's full-text link, the PDF or download button (Chrome downloads it, the watcher files it);
- come back with one of: the file arrived, with its version and what shows it — the host's word first (the page's label for the version, the link taken), then the file's (page 1); a gate brought to the front (the page, what the user must do there); a conclusion with its evidence.

By its answer: the file arrived → rerun the command. A gate → references/gate.md; once the user has passed it, tell the same browser agent to go on, since its try is not over. A conclusion → record it — `pf.py fetch --pass N --verdict <word> <result>` (the words are in `fetch --help`: `no_access`, `no_pdf`, `gate_timeout`, …) — then rerun the same command: it skips what this pass has done and goes on. A copy you found elsewhere yourself (a PMC page, a repository) is one more candidate: `pf.py fetch --pass N --start <url> [--version accepted] <result>`. Purchase pages are never a route.

**Every file goes through `claim`**, whoever got it: it checks the file against the paper and files it beside the result (`results/<slug>[.version].pdf`) or moves it to `<dir>/unverified/`. `pf.py check_pdf <result> [--file F]` shows the verdict and its evidence. A file there that you believe is the paper after all: read its first page (`pdf` skill), then `pf.py claim --dir <dir> --accept <file> --slug <slug> --reason "…"` (`--version accepted|preprint|…` when its name does not say) files it, and the result says `check: accepted` with your reason.

**Every file gets its label** in the pass that got it, while the host's word on it is fresh: the attachment title it will be known by, `pf.py claim --dir <dir> --label Accepted-arXiv-v3 --why "v3's comment: Accepted at CVPR 2024" --slug <slug>` (`--by subagent | browser_agent` when someone else settled it). Read references/attachment-titles.md (the scheme, the versions, the evidence) before the first one.
- A browser agent's file: the version it reported from the page.
- Every other file: the `to_label` lines `fetch` ends a pass with, one per file without a label (a snapshot needs none). Each holds the host's word recorded at download — the page's words around the title, its metadata, the link taken, arXiv's comment on the version — then the file's word. Label a line yourself when the two leave no doubt about the version and the source; every line with doubt left goes to a cheap-model subagent, which reads the line and looks at pages 1 and 2 as images (both images of every file: say so as its done-condition).
- A file neither settles: a subagent of its own looks again at the page it came from, while that page is at hand — at most 10 at once, one per site, briefed with *Agents you send*.
- Still undecided: no label; the result says `Unknown-<Source>`. The file is kept all the same.

**Three passes at most.** Every pass is the same chain and may ask the user at a gate. Between passes the caller takes what is in hand (paper-to-zotero saves); the next pass comes later, when a login, a rate limit or a flaky site may have recovered. The **last pass needs the user**:
1. Finish everything else first. Then report to the user — in the conversation and with a push notification — which papers remain, what each pass met and what each needs. While they are away, the run waits; these papers resume when the user says "继续".
2. With the user there, `fetch --pass 3 --window foreground`: pages open where the user sees them. At each paper it stops on, tell the user which paper this is, what the earlier passes met and what they could do (log in, click the PDF button); have the browser agent work the page meanwhile, and wait with `pf.py wait <result> --file-only` in the background — it ends when the file arrives. The user says 跳过 → stop the wait, `--verdict skipped_by_user`, rerun, and the next paper opens.
3. A paper still without a file gets a snapshot of its article page: `pf.py fetch --pass 3 --route snapshot <result>`. The page that arrives is checked like any file, so a login page never becomes the snapshot.

Done when every result has a file that passed the check (or that you accepted) and its label, or its last pass is in `fetch.jsonl` and its snapshot is filed — and `settle.py --dir <dir>` shows each result's `outcome`.

## Label files you already have

A library's PDFs to rename by version, or files the user dragged in: the check and the label are the same as for a fetched file, but the file's own word comes first (references/attachment-titles.md, *A file already in the library*).

1. `identify` the paper by its DOI or arXiv id, into a directory of its own (`-o <scratch>/paper-fetch/label`).
2. `pf.py claim --dir <dir> --file <path> --slug <slug>`: a file outside `<dir>` is copied, never moved, so a PDF in Zotero's storage stays where it is. Then `claim --label … --why …` as above.

The result's `files[].label` is what the caller writes back (paper-to-zotero renames the attachment).

## Residue

```bash
uv run scripts/pf.py claim --dir <dir> --sweep
```

**Residue** is `<dir>` (results, files, `inbox/`, `stray/`, `unverified/`, `fetch.jsonl`, `scratch/`), the `pf` session, the watcher, and anything in Downloads newer than `.started`. Stop the watcher. `--sweep` lists the files this run left in Downloads with their md5: delete those this run downloaded that have reached their destination (a caller asks its own store: paper-to-zotero's `find_in_library --file`), and name the rest in the report (a file the user downloaded for themselves is theirs). Then close the session (`opencli browser close --session pf`). `<dir>` goes when its files have reached the caller; standalone, the files are the deliverable: leave them where the user asked, else in `<dir>`, and give the full path. Delete only what this run created; a wait for the user is a pause, not an exit.

Done when Downloads holds no file of this run, the session is closed, and every file left anywhere is named with its location.

## Rules

### Reaching a page

Fall back instead of stopping: a blocked request, a verification page or an empty result is a reason to take the next rung.

1. Direct access — metadata APIs (doi.org, Crossref, OpenAlex, arXiv), web fetch.
2. OpenCLI adapters, discovered at run time. An API-type adapter (`browser: false`) is still a direct request and fails the same way when blocked; when it does, `opencli web read --url …` reads the page inside the user's Chrome with their cookies, and `opencli browser` lets you work the page yourself.
3. A browser-type adapter (`browser: true`) that fails was already in the real browser, so it was most likely blocked: open the same page in the `pf` session and look — a verification or login page is a gate; a normal page means the adapter broke, so read it yourself. Keep the adapter's raw output in `<dir>/scratch/` for the skill notes.

Retry a transient error once; a 403 or a verification page goes straight to the next rung. Publisher hosts and Google Scholar start at rung 2; Google Scholar at most once a minute. A host that answers 429 is left alone until its Retry-After, else an hour (the scripts keep that in `<dir>/pace.json`). Files a tool writes on the way go into `<dir>` and leave with it.

### Agents you send

Every agent works the web as the user: their IP, their Chrome, their institution's login, so every site sees one person. A site that sees a crowd blocks the user, or the institution. Each brief you write for an agent that touches a site (a browser agent, a label check, a check for a rename) carries these four lines:
- work by hand, one request at a time; a script or loop over a site, and a browser-type OpenCLI adapter (`Browser: yes`) in a loop, are out;
- one agent per site at a time, several seconds between its requests; agents on different sites run side by side, at most 10;
- the first bot check, 403, 429 or Cloudflare page ends the work on that site for this run: stop there and report it;
- do the work yourself, without agents of your own.
An agent that reads only local files (`to_label` lines, a file on disk) needs none of them.

### Report

Say per paper what was got and how (route, label, check), what was not and why (each pass's tries, the stop), the gates hit, the hosts left alone, the sources a 429 stopped — and **skill notes**: anything this skill lacked, got wrong or made you work around (a site that behaved unlike publishers.md says), for the user to decide whether to change it. Inside an import, these go into paper-to-zotero's report.
