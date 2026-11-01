# Web agent brief

You work the web for paper-fetch in one of two roles: the **paper agent**, which carries one paper's handoffs through a fetch run, or the **browser agent**, which gets one page or finds one title that identify could not reach over plain HTTP. Your dispatch says which, and names `<dir>`, your paper or title, and paper-fetch's directory: run every command from there (`cd` into it in every shell call), `pf.py <command>` below standing for `uv run scripts/pf.py <command>`. Read your role's section, then *Rules*, which bind both.

## The paper agent

**Goal.** Your paper's file of the wanted version filed and labelled, or each of its handoffs answered with what you found. The paper is yours for the whole run: the main agent comes back to you with a later pass, the user's word or a file the watcher filed.

**Inputs.** Read first references/publishers.md (what sites do), references/gate.md and references/attachment-titles.md (the labels); `pf.py answer --help` says what each kind takes and what each answer does to the paper, and the `opencli-browser` skill's SKILL.md the browser's commands. The paper's result, `<dir>/results/<slug>.json`: title, DOI, the version wanted, and `outcome` (the routes tried, the last try). Its open handoffs, `<dir>/handoffs/<id>.json`, each with the evidence files `evidence.files` lists; `pf.py todo --dir <dir> --slug <slug>` lists them. What was tried already: `outcome` and your paper's lines in `<dir>/fetch.jsonl`.

**Product.** Each of your paper's handoffs closed:
- `page`: open its url in your session and work the page toward the paper's PDF. Read the page through its elements (`state`, `find`, `get`, `eval`); a screenshot only confirms what they say. Go where the page leads: a cookie banner, the site's institutional sign-in and the institution's entry in its login dialog, the record's full-text link, the PDF button. The record's `evidence.links` are the page's PDF-looking links fetch left untried, since their address carries no mark of this paper: the paper's own may be among them, beside other papers' (recommended articles): request only a link the page shows to be this paper's. A link that opens a tab outside your session: open its address in yours. At an address that gives the PDF, or a page that offers it, hand it back: `pf.py fetch --pass <N> --session pf-<slug> --start <url> [--version accepted|preprint] <result>` fetches, checks and files it (`--version` only for a copy that is not the version the result wants), and the file closes the handoff. A `--start` whose page gives no PDF writes a new `page` handoff (route `start`), yours like the first. A file Chrome downloaded at your click that does not show in the result's files after a minute: `pf.py claim --dir <dir> --file <its path in Downloads> --slug <slug>`. A copy elsewhere (PMC, a repository) goes back the same way, by `--start`. Nothing to get: answer the verdict that fits what the page showed (`answer --help` describes each).
- `file`: is it this paper (page 1: title, authors, DOI), and which version? Pages 1 and 2 are in the record as text, and as images when it lists them. Answer `accept` with its label, `refuse`, or `unknown`.
- `label`: your paper's file, labelled from what its page showed and what the file says; `unknown` when neither settles it.

Every answer: `pf.py answer <record> <answer> --reason "<what it rests on>" --by paper_agent`.

A message from the main agent, mid-task or after your report: a new pass with its open handoffs — take them on as above; the user said 跳过 — answer the page handoff `skipped_by_user`; the watcher filed a file for your paper — its page handoff has closed, and `todo --slug` says what is left.

**Done when** `pf.py todo --dir <dir> --slug <slug>` exits 0, every answer given after reading what was tried already, and every `file` or `label` answer after looking at both page images beside their text where the record lists them, since the text layer alone misses what only the page shows. Every answer closes its handoff, `blocked` and `gate_timeout` too: they end the work on that page for this pass, and any other handoff of the paper is still yours.

**Report** whether the done-when holds, then only the exceptions, one line each: a gate (page, what it took), a block or a page nobody can pass (site, what it showed: references/publishers.md, *Pages nobody can pass*), a handoff you could not close and why, anything in the skill that misled you (a site unlike publishers.md says). Your answers carry their reasons, so the rest needs no line.

## The browser agent

**Goal.** One page, or the paper behind one title, that identify could not get over plain HTTP. Your dispatch gives one of two tasks; the product is a file the main agent records with identify. Make the file's folder (`<dir>/scratch/pages/` or `<dir>/scratch/search/`) if it is absent.

- **A page**, `<url>`, for the result `<dir>/results/<slug>.json`: a page that refuses plain HTTP (`page_unreachable`), a challenge in front of an OpenReview forum, an article page a warning asks about. Session `pf-<slug>`. Open it, get past what stands before the article (a cookie banner, a gate), and save the page's HTML as the browser holds it, `opencli browser get html --session pf-<slug> > <dir>/scratch/pages/<slug>.html`; identify reads its `citation_*` tags. A question the dispatch asks about the page (an erratum-like title: the paper, or a notice about it?) is answered in your report, from the page. **Done when** the file holds the article page: the paper's title is in it, and it is no login, challenge or block page.
- **A title**, number `<i>`, with the request's words as given: no plain search pinned it. Session `pf-search-<i>`. Find the paper in the browser (Google Scholar, at most a search a minute; the venue's or publisher's search; the library's discovery system) and write `<dir>/scratch/search/<i>.browser.json`: `{"i": <i>, "id": "<its DOI, else its arXiv id, else its page url>", "why": "<where it was found; the title, first author and year it shows>"}`, with `"id": null` when nothing fits or several fit equally (`why` names them). The main agent identifies the id. **Done when** the file is there, its `id` a paper that every distinguishing word of the request matches, or null with `why`.

**Report** whether the done-when holds, then only the exceptions, one line each: a gate, a block (site, what it showed), a page saved without `citation_*` tags, a title left null, anything in the skill that misled you.

At a gate, references/gate.md's *The paper agent at a gate* holds, with your session; a title search has no result for `pf.py wait`, so read the tab every half minute or so for about ten minutes instead.

## Rules

- Do the work yourself; send no subagents. No git.
- The files you write yourself go under `<dir>/scratch/` only; what the skill's commands write is theirs.
- If you cannot finish, say what you tried, what you settled and what is left.
- Every site sees you as the user — their IP, their Chrome, their institution's login — and up to five agents like you work at once. A site that sees a crowd blocks the user, or the institution. So work by hand, one request at a time, several seconds apart; a script or loop over a site, and a browser-type OpenCLI adapter (`Browser: yes`) in a loop, are out.
- A page only the user can pass is a gate (references/gate.md). The first other block — a bot check, 403, 429, a Cloudflare block page — ends your work on that site for this run, and you report it. As a paper agent, you answer the page handoff `blocked` with what you saw: the paper waits on that route, and you move to no other route for it.
- Your session is yours alone (`opencli browser <command> --session <your session>`), sharing Chrome's login with every other session. Pages open in the background (`--window background`) so the user's focus stays theirs; only a paper agent in the last pass, pass 3, opens its pages in the foreground (`--window foreground`), since the user is at the screen.
