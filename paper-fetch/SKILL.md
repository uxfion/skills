---
name: paper-fetch
description: Finds out which paper is meant and gets its full text — DOI or arXiv id, normalized CSL metadata, preprint and published versions, then a PDF checked against the paper and labelled with its version, by open copies, the publisher through the institution's login, the library's discovery system or the user's browser. Use when a paper has to be pinned down from a title, list or link, its metadata or versions looked up, or its PDF fetched (找论文 PDF、下载全文、查 DOI 和正式版), or files someone has labelled by version; paper-to-zotero calls it when importing.
---

# Paper fetch

From "a paper" to a file of it you can trust: which paper it is, what is known about it, which versions exist, and its PDF, checked against the paper and labelled with the version it is. Everything that touches the web is here; Zotero is paper-to-zotero's. Script paths are relative to this file's directory: `cd` there at the start of every shell call. `uv run scripts/pf.py --help` lists every script; each script's `--help` is the reference for its flags, codes and output.

**Scripts do the certain steps; agents do the rest.** A script goes as far as it can be certain — a request, a check, a file filed — and where it cannot (a page it gets no PDF from, a file it cannot be sure of, a version to settle) it writes a **handoff** and goes on with the other papers. An agent reads the handoff's evidence and acts: it hands the page back to the script (`fetch --start`), or answers with `pf.py answer`; the script's next run carries on from there.

| operation | where |
|---|---|
| Identify a paper (a title, a link, an id) | *Identify a paper* below |
| Get its file | *Ready*, then *Get the file: the chain* below |
| Who takes a handoff, how to answer it, the agents' briefs | *Handoffs* below |
| Label files someone already has (a library's PDFs, the user's own) | *Label files you already have* below |
| Many papers, in passes | references/batch.md, before *Ready* |
| A page only the user can pass | references/gate.md |
| Identify only, no file | references/identify.md |

**The directory.** A run lives in one directory, `<dir>`: the caller's (an import: `<scratch>/paper-to-zotero/fetch/`), else `<scratch>/paper-fetch/` — `<scratch>` is the session's scratchpad, else `${TMPDIR:-/tmp}`. Each paper is one result file, `<dir>/results/<slug>.json`, with its files beside it; a caller reads `results/` and nothing else (`scripts/pflib/run.py` documents the format). The slug is the caller's citation key in file-safe form (the key itself is kept in `cite`), or `<surname><year><first title word>`. What waits for an agent is a record in `<dir>/handoffs/`.

**The user helps; the work is yours.** The run is the same whether or not the user is watching: you and your agents fetch every paper. The user may log in, pass a CAPTCHA or click a download at any moment, and that only speeds things up — the watcher files their downloads. Say early what you can foresee needing them for ("3 of these need the institutional login — if you can, log in now: Ctrl+N, a normal window"). Only the last pass is planned around them; before it, a gate waits for them about ten minutes and sees for itself when they are through, without reloading the page (references/gate.md).

## Skills and tools it relies on

Each skill is installed on its own, beside this one (`../<name>/`); paper-to-zotero calls this skill when it imports, and nothing here needs it.

| what | for | missing → |
|---|---|---|
| `opencli-usage` skill, OpenCLI 2.x | web access: discover adapters at run time (`opencli list <query>`: JSON, paged with `--offset`). Seen in 2026-09: API-type `arxiv`, `openalex`, `semanticscholar` (429 without a key — one 429 means skip it), `pubmed`, `dblp`, `openreview`, `hf paper`; browser-type `google-scholar`, `cnki`, `wanfang`. Behind a proxy every call prints a harmless `UNDICI-EHPA` warning on stderr: send stderr to `<dir>/scratch/opencli.log` | `ready` reports it: references/install.md, the user's to install |
| `opencli-browser` skill | the user's real, logged-in Chrome: `browser <command> --session <name>` with `open / state / find / get / click / wait / eval / tab / close`, `web read --url`. The bulk run's session is `pf`; each paper agent has its own, `pf-<slug>`; every session shares Chrome's login. Windows open in the background (`--window background`), so the user's focus stays theirs; the last pass opens them in the foreground | the browser routes and every gate wait: references/install.md |
| poppler-utils (`pdftotext`, `pdfinfo`, `pdftoppm`) | checking every file against the paper; pages 1–2 of a handed-over file as images | nothing can be filed (`no_pdftotext`); without `pdftoppm` a handoff carries text only: references/install.md |
| `pdf` skill | reading pages of a file in a handoff | render the pages yourself (`pdftoppm`) |
| `papers-cool-search` skill | papers.cool search and venue listings as JSON, one request at a time | arXiv-style titles go up the other rungs of *Reaching a page* |

Read [references/publishers.md](references/publishers.md) whenever a publisher page is yours to work (a `page` handoff, a discovery system, a click), and [references/install.md](references/install.md) when `ready` reports something missing.

## Identify a paper

Treat the user's words as a draft: typos, partial titles and loose keywords are normal, so reformulate and search again before concluding anything. Search along the ladder in *Reaching a page*: metadata APIs and API-type adapters first, `google-scholar` and other browser-type adapters next, `opencli browser` last. A journal or conference title is usually pinned in one Crossref call (`uv run scripts/pf.py identify --search "<title>" --author <surname>`: Crossref's top five with authors and similarity, unfiltered). An arXiv-style title: papers.cool is a fast first stop (`uv run <papers-cool-search dir>/scripts/papers_cool_fetch.py search "<3-6 title words>" --show 5`); its search has no title weighting, carries no DOI and does not index authors, so confirm the title yourself. Several plausible candidates, or none you would stake the result on: show the top few (title, authors, year, venue) and let the user choose.

```bash
uv run scripts/pf.py identify <DOI | arXiv id | paper page> [--slug <citation key>] [--wanted accepted|preprint] -o <dir>
```

`identify` writes the result: the paper's CSL metadata (from doi.org, or the page's `citation_*` tags, with the abstract, PMID and PMCID that OpenAlex and Europe PMC have where the record lacks them), its ids, the version the caller wants (`wanted`, default published) and, for a preprint, its versions — `versions.published`, the published versions the authors declared to arXiv or Crossref's title search found. The published version comes first unless the user asked for the preprint: confirm a candidate against arXiv's comment ("Accepted at ICLR 2024", in `versions.preprint.comment`) and its title; none, but the comment or the paper names a venue → papers.cool's venue search or the venue's own listing finds the paper's page. Confirmed → `identify --redraft <DOI | page url> <result>`. When a caller decides the version (paper-to-zotero does), its rule wins and you redraft on its word. `versions.incomplete` and `enrichment.incomplete` name sources that did not answer: identify the same id again later. A page that refuses plain HTTP (`page_unreachable`): a browser agent saves its HTML into `<dir>/scratch/`, then `identify --redraft <page url> <result> --html <file>`. A stub (`no_csl_record`, `no_citation_meta`, an unreachable page not redrafted): the paper has no metadata to check a file against; its files are filed as `cannot_judge`. identify writes no author keywords.

Done when every paper is pinned by a DOI, an arXiv id or its page, every distinguishing word of the request matches it, no other result fits equally well, and its result is written (the version settled where the caller asked for one).

## Ready

```bash
uv run scripts/pf.py ready --dir <dir>
uv run scripts/pf.py claim --dir <dir> --watch                    # in the background, the whole run
```

`ready` checks poppler and OpenCLI, prepares `<dir>` (`results/`, `links/`, `handoffs/`, `inbox/`, `unverified/`, `scratch/`, the `.started` marker, `run.json` with the Downloads folder and the browser session) and prints `downloads_dir`. Act on what it reports: `config.ask_user` (the library's discovery search page: ask for it in your first message), `discovery_template` (the config's `institution.discovery` must be a search URL with `{title}` where the title goes: write it so, telling the user first); `no_pdftotext`, OpenCLI issues: references/install.md, the user's to install on their word, an old daemon → `opencli daemon restart`; `resumed: true` — an earlier run left `<dir>`: carry on from its results and `pf.py todo --dir <dir>`; `leftovers` are reported, never deleted: a PDF that never reached the user belongs to them.

The **watcher** files every new PDF in Downloads that passes the check for exactly one paper `fetch` was asked for and that is not yet satisfied — the agents' downloads and the user's alike. Start it as a background process that lives as long as the run; where none can be kept, `fetch` and `wait` scan Downloads themselves. Where the harness can stream a command's lines to you as events (Claude Code: the Monitor tool), also follow the log, re-armed whenever it expires:

```bash
tail -n 0 -F <dir>/fetch.jsonl | grep --line-buffered -E '"result": "(claimed|left)"'
```

`claimed`: that paper has its file — tell its paper agent, if it has one. `left`: a new file matched none of the waiting papers, or several; it stays in Downloads with a `left` handoff for a judge. While no paper waits, a new file is not looked at: it is the user's own. An event never interrupts a running command, so whatever waits looks for the file itself. The watcher only appends events: `pf.py settle` folds them into the results (`fetch`, `claim`, `answer` and `wait` fold what they touched when they end).

Done when `ready` reports `ok` and the watcher runs.

## Handoffs

```bash
uv run scripts/pf.py todo --dir <dir> [--slug <slug>] [--kind <kind>]         # what is open; exit 1 while anything is
uv run scripts/pf.py answer <dir>/handoffs/<id>.json <answer> --reason "<what it rests on>" --by <paper_agent|judge|agent|user>
```

A handoff record (`<dir>/handoffs/<id>.json`, id `<slug>.<n>`, or `<kind>.<n>` without a paper) holds what to judge (`kind`), who takes it (`taker`), the paper (title, DOI, wanted version), the evidence — the short facts in the record, the long texts and the page images as the files `evidence.files` lists — and the answers it takes. A script prints at most one short line per handoff, never the evidence; `todo` lists them all. `answer` records the answer, logs what it did (a file filed, a label, a try) and folds the paper's result; `answer --help` says what each answer does. A handoff also closes by itself once what it waited for has happened: a confirmed file filed for its paper (`page`, `file`), a label on its file or the file withdrawn (`label`), its download filed (`left`).

| kind | written when | taker | answers |
|---|---|---|---|
| `page` | `fetch` got no PDF from a page — a sign-in, a challenge, no PDF link, its files refused, no record in the discovery search (`code`: `no_pdf_link`, `refused`, `no_record`, `error`); the bulk run's tab stays on that page | the paper's agent | none once it got past the page: `fetch --start <url> --session pf-<slug>` hands the page back, and the file that comes closes the handoff. Else a verdict: `no_access`, `no_pdf`, `not_public`, `proxy_unconfigured`, `skipped_by_user` — the paper goes on to its next route; `blocked`, `gate_timeout` — it waits on this route until the next pass |
| `file` | the check could not be sure a file is the paper (a short title, no text layer, the title only past page 1, an erratum-like first page); the file is held in `unverified/` | the paper's agent; a judge when labelling files you already have | `accept` (filed; `--label <Title> --why "…"` with it, since the same look settles the version; `--version` when the file's name does not say its kind) · `refuse` (not the paper: it goes on) · `unknown` (filed unconfirmed: the paper goes on, and a confirmed file replaces it) |
| `label` | a filed file has no label (the fold asks, whichever command filed it) | a judge, in batches; the paper's agent for a file it fetched itself | `label --label <Title> --why "<what shows it>"` (references/attachment-titles.md) · `unknown` (`Unknown-<Source>`) |
| `left` | the watcher found a download that matched no waiting paper, or several | a judge | `claim --slug <slug>` (it is that paper's) · `not_ours` |
| `browser_down` | OpenCLI could not reach Chrome (`BROWSER_CONNECT`) | you | `resolved`, after `opencli doctor` (and `opencli daemon restart` when it says so), else the user opening Chrome |

Identify writes no records; its lines are taken like this:
- `needs_pinning`: you (*Identify a paper*); a title only a browser search finds goes to a browser agent.
- A preprint's `versions.published`, a `--search` list: a judge confirms one against the title, the first author and arXiv's comment, and you redraft on its word.
- `page_unreachable`, or a warning that needs the article page (an erratum-like title): a browser agent opens the page — it saves the HTML for `--redraft --html`, or says what the page shows.

A browser agent is briefed like a paper agent, with its one task instead of handoffs.

### The paper agent

One background subagent per paper that has an open `page` or `file` handoff (Claude Code: `model: "sonnet"`; Codex: `luna`), at most five at once, the rest queued. It keeps its paper for the whole run: later passes go back to the same agent (`SendMessage`). Without subagents, be the paper agent yourself, one paper at a time. Fill in its brief:

```text
You are the paper agent for one paper, for the whole run: "<title>" (DOI <doi | none>), the version wanted: <wanted>.
Its result: <dir>/results/<slug>.json. Its open handoffs: <the records' paths, from pf.py todo --dir <dir> --slug <slug>>.
This is pass <N>. Your browser session is pf-<slug>: `opencli browser <command> --session pf-<slug>`; it shares
Chrome's login with every other session. Scripts: `cd <paper-fetch's directory>` in every shell call, then
`uv run scripts/pf.py <command>`. First read there SKILL.md's *Handoffs*, references/publishers.md,
references/gate.md and references/attachment-titles.md.

Your goal: the paper's file of the wanted version filed and labelled, or each of its handoffs answered with what you
found. Read each record and the evidence files it lists, then:
- page: open its url in your session and work the page toward the paper's PDF. Read it with state, find, get or eval
  (a screenshot only to confirm what those say); click with --role/--name, or a ref from the state just read. Go where
  the page leads: a cookie banner, the site's institutional sign-in and the institution's entry in its login dialog,
  the record's full-text link, the PDF button. A link that opens a tab outside your session: open its address in
  yours. At an address that gives the PDF, or a page that offers it, hand it back:
  `pf.py fetch --pass <N> --session pf-<slug> --start <url> [--version accepted|preprint] <result>` fetches, checks
  and files it. A file Chrome downloaded at your click that does not show in the result's files after a minute:
  `pf.py claim --dir <dir> --file <its path in Downloads> --slug <slug>`. Nothing to get: answer the verdict.
- file: is it this paper (page 1: title, authors, DOI), and which version? Pages 1 and 2 are in the record, as text
  and images. Answer accept with its label, refuse, or unknown.
- label, of a file you fetched: label it from what its page showed.
Every answer: `pf.py answer <record> <answer> --reason "<what it rests on>" --by paper_agent`.
A page only the user can pass is a gate: references/gate.md, *The paper agent at a gate*.
<the lines of SKILL.md's *Agents you send*, pasted>

Done when `pf.py todo --dir <dir> --slug <slug>` exits 0, or you answered blocked or gate_timeout. Report one line:
what you did, the answers you gave, the label of the file filed.
```

### The judge

A background subagent on the paper agent's model that reads only local files, so it needs none of the web lines: about twenty handoffs each, at most five at once. Its brief: the records' paths; read references/attachment-titles.md first; look at pages 1 and 2 of every file as images beside their text — every record about a PDF lists them in `evidence.files` — and make both images of every file the done-condition, since a judge left to choose reads the text layer alone; a `left` record: compare the file's page 1 with the results it was checked against (`evidence.against`); answer each with `pf.py answer … --by judge`, writing only under `<dir>/scratch/judge/`, no git; report one line per handoff.

## Get the file: the chain

The **chain** is the order of routes to a paper's full text; one walk down it is a **pass**, and a paper's pass stops at the first route that yields a file it is satisfied with:

1. `open` — an open copy of the published version (the paper's links, then those of unknown version);
2. `publisher` — the publisher's page through the institution's login;
3. `discovery` — the library's discovery system, its own full-text links (skipped while `institution.discovery` is unset or holds no `{title}`);
4. `accepted` — the accepted manuscript;
5. `preprint` — the preprint, last.

```bash
uv run scripts/pf.py fulltext_links <dir>/results/*.json      # where copies may be had
uv run scripts/pf.py fetch --pass N <dir>/results/*.json
```

One command walks the whole pass: each route over every paper still without a file, then the next. On a page it takes whatever PDF the page offers — the declared PDF, an embedded viewer, a "PDF" link and the reading page behind it, the next one when a file is refused — and every file goes through the check, so a wrong guess costs nothing. A file's name carries the version it was wanted as (`<slug>.accepted.pdf`, `<slug>.preprint.pdf`; a second file of one kind `<slug>.2.pdf`); what it actually is goes into its label. A paper is satisfied by a file labelled the wanted version, or by one not labelled yet; once its label says less (an accepted manuscript, a preprint, `Unknown`), the next run of the pass takes the paper on down the chain, and every version stays in `files`, side by side.

**A pass is a loop between the script and the agents:**
1. `fetch --pass N <dir>/results/*.json`. Exit 0: nothing open, the pass is done. Exit 1: handoffs are open — its summary counts them by kind.
2. `pf.py todo --dir <dir>`. A `browser_down` first: yours, since no page can be worked without the browser. Then each paper with an open `page` or `file` handoff to its paper agent. Once they have reported, `todo` again: the `label` and `left` handoffs still open go to judges in batches (*Handoffs*) — a paper agent labels and hands over what it fetched itself, so a judge sent earlier would do its work twice.
3. Each agent answers with `pf.py answer` and reports one line. A paper agent at a gate sends you one line: references/gate.md, *The main conversation at a gate*.
4. Step 1's command again: it skips what this pass has done, takes each answered paper on from where its answer leaves it — the next route, or held on its route until the next pass — and writes new handoffs if any come.
A copy you or an agent found elsewhere (a PMC page, a repository) is one more candidate for its paper agent: `fetch --pass N --session pf-<slug> --start <url> [--version accepted] <result>`. Purchase pages are never a route.

**Every file goes through the check**, whoever got it: `claim` checks it against the paper and files it beside the result, moves it to `<dir>/unverified/` when it is certainly not the paper, or holds it there with a `file` handoff when it cannot be sure. A file an agent downloaded itself: `pf.py claim --dir <dir> --file <path> --slug <slug>`. `pf.py check_pdf <result> [--file F]` shows the verdict and its evidence.

**Every file gets its label**: the attachment title it will be known by (references/attachment-titles.md: the scheme, the versions, the evidence). A paper agent labels what it fetched while the page is fresh: with `accept --label` on a `file` handoff, or by answering its paper's `label` handoff. Every other file waits in a `label` handoff for a judge, whose record holds the host's word recorded at download — the page's words around the title, its metadata, the link taken, arXiv's comment on the version — then the file's: its arXiv stamp, its dates, pages 1 and 2. Still undecided → `unknown`: `Unknown-<Source>`; the file is kept all the same, and since it is not the wanted version the paper goes on looking for that.

**Three passes at most.** Every pass is the same loop and may meet a gate. Between passes the caller takes what is in hand (paper-to-zotero saves); the next pass comes later, when a login, a rate limit or a flaky site may have recovered, and its handoffs go back to the papers' own agents. The **last pass needs the user**:
1. Finish everything else first. Then report to the user — in the conversation and with a push notification — which papers remain, what each pass met and what each needs. While they are away, the run waits; these papers resume when the user says "继续".
2. With the user there, `fetch --pass 3 --window foreground`, and the paper agents open their pages with `--window foreground`: pages open where the user sees them. For each paper still open, tell the user which paper this is, what the earlier passes met and what they could do (log in, click the PDF button); its paper agent works the page meanwhile, and `pf.py wait <result> --file-only` in the background ends when the file arrives. The user says 跳过 → stop the wait; the paper agent answers its `page` handoff `skipped_by_user`, and the next paper goes on.
3. A paper still without a file gets a snapshot of its article page: `pf.py fetch --pass 3 --route snapshot <result>`. The page that arrives is checked like any file, so a login page never becomes the snapshot.

Done when every result has a file that passed the check (or that an agent accepted) and its label, or its last pass is over and its snapshot is filed — `pf.py settle --dir <dir>` shows each result's `outcome`, and `pf.py todo --dir <dir>` exits 0.

## Label files you already have

A library's PDFs to rename by version, or files the user dragged in: the check and the label are the same as for a fetched file, but the file's own word comes first (references/attachment-titles.md, *A file already in the library*).

1. `identify` every paper by its DOI or arXiv id, in one call into one directory (`printf '<id>\t<key>\n' … | uv run scripts/pf.py identify -o <scratch>/paper-fetch/label`): arXiv's comments come in one request per hundred ids, and every request keeps the machine's pace.
2. `pf.py claim --dir <dir> --file <path> --slug <slug>` for each file: a file outside `<dir>` is copied, never moved, so a PDF in Zotero's storage stays where it is; two files of one paper sit side by side, numbered. Each filed file gets a `label` handoff, a file the check cannot be sure of a `file` handoff.
3. Judges answer both kinds (*The judge*), about twenty files each; a `file` handoff with `accept --label …` or `refuse`, so one look settles both questions.

The result's `files[]` — each with its md5 and label — is what the caller writes back (paper-to-zotero renames the attachment holding that md5).

Done when `pf.py todo --dir <dir>` exits 0 — every file labelled, or `Unknown-<Source>` with what was looked at named — and the directory is deleted once the caller has the labels.

## Residue

```bash
uv run scripts/pf.py claim --dir <dir> --sweep
```

**Residue** is `<dir>` (results, files, `handoffs/`, `inbox/`, `unverified/`, `fetch.jsonl`, `scratch/`), the browser sessions (`pf` and every `pf-<slug>`), the watcher, and anything in Downloads newer than `.started`. Stop the watcher. `--sweep` lists the files this run left in Downloads with their md5: delete those this run downloaded that have reached their destination (a caller asks its own store: paper-to-zotero's `find_in_library --file`), and name the rest in the report (a file the user downloaded for themselves is theirs). Then close every session (`opencli browser close --session <name>`). `<dir>` goes when its files have reached the caller; standalone, the files are the deliverable: leave them where the user asked, else in `<dir>`, and give the full path. Delete only what this run created; a wait for the user is a pause, not an exit.

Done when Downloads holds no file of this run, every session's close has answered "tab lease released", and every file left anywhere is named with its location.

## Rules

### Reaching a page

Fall back instead of stopping: a blocked request, a verification page or an empty result is a reason to take the next rung.

1. Direct access — metadata APIs (doi.org, Crossref, OpenAlex, arXiv), web fetch.
2. OpenCLI adapters, discovered at run time. An API-type adapter (`browser: false`) is still a direct request and fails the same way when blocked; when it does, `opencli web read --url …` reads the page inside the user's Chrome with their cookies, and `opencli browser` lets you work the page yourself.
3. A browser-type adapter (`browser: true`) that fails was already in the real browser, so it was most likely blocked: open the same page in a session and look — a verification or login page is a gate; a normal page means the adapter broke, so read it yourself. Keep the adapter's raw output in `<dir>/scratch/` for the skill notes.

Retry a transient error once; a 403 or a verification page goes straight to the next rung. Publisher hosts and Google Scholar start at rung 2; Google Scholar at most once a minute. A host that answers 429 is left alone until its Retry-After, else an hour (the scripts keep that in the machine's pace file, `~/.cache/paper-fetch/pace.json` or `$PAPER_FETCH_PACE`). Files a tool writes on the way, and one-off code, go into `<dir>/scratch/` and leave with it.

### Agents you send

Every agent works the web as the user: their IP, their Chrome, their institution's login, so every site sees one person. A site that sees a crowd blocks the user, or the institution. Each brief you write for an agent that touches a site (a paper agent, a browser agent) carries these lines:
- work by hand, one request at a time, several seconds apart; a script or loop over a site, and a browser-type OpenCLI adapter (`Browser: yes`) in a loop, are out;
- at most five agents on the web at once;
- a page only the user can pass is a gate (references/gate.md); the first other block — a bot check, 403, 429, a Cloudflare block page — ends your work on that site for this run: answer the page handoff `blocked` with what you saw, and report it; the paper waits on its route, and you move to no other route for it;
- do the work yourself, without agents of your own; write only through `pf.py` commands and under `<dir>/scratch/`; no git.

### Report

Say per paper what was got and how (route, label, check), what was not and why (each pass's tries, the outcome's `last`), the gates hit, the blocks (site, paper), the sources a 429 stopped — and **skill notes**: anything this skill lacked, got wrong or made you work around (a site that behaved unlike publishers.md says), for the user to decide whether to change it. Inside an import, these go into paper-to-zotero's report.
