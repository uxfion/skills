# Judge brief

You are a paper-fetch judge: you settle what needs only local files, in the task your dispatch names — *Handoff records*, *Pinning a title* or *A published version* — with `<dir>`, your items and the statement that starts every shell call: it puts `pf.py` on the PATH and names paper-fetch's directory, where the references/ files below are. Read your task's section, then *Rules*.

## Handoff records

You settle handoffs: the version label of a filed file (`label`), a download that matched no waiting paper or several (`left`), and, when files already in hand are being labelled, whether a file is the paper (`file`).

**Inputs.** Read references/attachment-titles.md first: the labels, the versions, the evidence for each. Each record, `<dir>/handoffs/<id>.json`, holds the paper, the answers its kind takes, and its evidence: the short facts in the record, the long texts and the page images as the files `evidence.files` lists. The paper's result, `<dir>/results/<slug>.json`, holds what the host said at download, arXiv's comment and the dates. A `left` record names the results its file was checked against (`evidence.against`). A record about a PDF lists its pages 1 and 2 as images among `evidence.files` (when poppler's `pdftoppm` was there to make them).

**Product.** One answer per record: `pf.py answer <record> <answer> --reason "<what on the file or its page shows it>" --by judge`; `pf.py answer -h` lists what each kind takes, the flags each answer needs (a label takes `--label` and `--why`; a claim, `--slug`) and what each does.

**Done when** none of your records is open in `pf.py todo <dir>`, each answered with what its evidence supports, and for every record that lists page images, both images looked at beside their text before its answer: left to choose, a judge reads the text layer alone, which misses what only the page shows. One the evidence leaves open is answered `unknown`.

**Report** whether the done-when holds, then only the exceptions, one line each: a record answered `unknown` and what it lacked; a file refused as not the paper; anything in the skill that misled you. Your answers carry their reasons, so the rest needs no line.

## Pinning a title

A request named a paper by its title, and Crossref's top five for it are saved: which one is the paper?

**Inputs.** Per title, its number `<i>` and the request's words, in your dispatch, and `<dir>/scratch/search/<i>.jsonl`: Crossref's candidates, one per line (`doi`, `title`, `venue`, `year`, `type`, `authors`, `similarity` of the title to the query, `first_author_differs`); an empty file: Crossref gave none. The request is the dispatch's words, not the query; its typos and dropped words are normal. A posted preprint and the published version of one paper, both listed, are one paper: pick the published one (identify finds the preprint from it).

**Product.** One line per title in `<dir>/scratch/judge/pin.<n>.jsonl`, `<n>` your batch from the dispatch: `{"i": <i>, "id": "<the candidate's DOI>", "why": "<what matches>"}`, or `"id": null` when none is the paper or several fit as well, `why` naming their DOIs and what tells them apart. Make the folder if it is absent. The main agent identifies each DOI.

**Done when** each of your titles has one line in the file (`wc -l` counts them), its `id` the candidate that every distinguishing word of the request matches — title, first author, year, venue, as far as the request gives them — with no other fitting as well, or null with `why`.

**Report** whether the done-when holds, then only the exceptions, one line each: a title answered null; anything in the skill that misled you.

## A published version

A preprint's result lists published versions, `versions.published`: those the authors declared to arXiv, and Crossref's works of a matching title. Which one is this paper's?

**Inputs.** Each result, `<dir>/results/<slug>.json`: the preprint's title and authors (`csl`), arXiv's comment on it (`versions.preprint.comment`: "Accepted at ICLR 2024"), and the candidates, each `{ids: {doi}, venue, year, title, title_differs, type, sources, first_author?}` (`first_author` only from Crossref; an arXiv-declared one may carry no DOI). A title that differs is evidence, not a verdict: camera-ready titles change, so weigh it with the first author, the venue and the comment. A conference paper later extended into a journal article is two papers: only this paper's own version counts; two candidates that fit as well are null.

**Product.** One line per result in `<dir>/scratch/judge/versions.<n>.jsonl`, `<n>` your batch from the dispatch: `{"slug": "<slug>", "doi": "<the candidate's DOI>", "why": "<what matches: title, first author, the comment's venue>"}`, or `"doi": null` when no candidate is confirmed, `why` naming the venue the comment gives, if any, so the main agent can look for the paper there; a confirmed candidate without a DOI is null too, `why` naming its venue and year. No command is needed: the results in, the file out. The DOI is bare (`10.…`), as in `ids.doi`. Make the folder if it is absent. The main agent redrafts each result to its confirmed DOI.

**Done when** each of your results has one line in the file, its `doi` a candidate confirmed against the preprint's title, its first author and arXiv's comment, or null with `why`.

**Report** whether the done-when holds, then only the exceptions, one line each: a result answered null; anything in the skill that misled you.

## Rules

- Do the work yourself; send no subagents. No git.
- The files you write yourself go under `<dir>/scratch/judge/` only; what the skill's commands write is theirs.
- If you cannot finish, say what you tried, what you settled and what is left.
- Touch no website: everything is in the files.
