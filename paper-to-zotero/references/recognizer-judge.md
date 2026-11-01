# Recognizer judge brief

You are a paper-to-zotero recognizer judge. Zotero's recognizer made an item from a paper's PDF, and its fields may be wrong or missing: you check each item against its PDF's first page. Your dispatch names your items, `<imp>`, your number `<n>` and paper-to-zotero's directory.

**Inputs.** `<imp>/recognize/recognize.jsonl`, what `p2z.py recognize` printed: for each of your items a `recognized` line with its key (`key`), its fields (`item`) and its PDF (`pdf`). The PDF's first page is the authority, read from the file (`pdftotext -f 1 -l 1 <pdf> -`, or the page as an image): title, authors, venue, year, DOI, and the item type they make. Where the recognizer matched another paper, the fields come from the page all the same: the PDF is this paper's. One of your keys with no `recognized` line, or with no PDF you can read, gets `unknown`, its why saying which.

**Product**, in `<imp>/recognize/`:
- `verdicts.<n>.jsonl`, one line per item: `{"key", "verdict": "change" | "ok" | "unknown", "why"}`, the why naming what on the page shows it. A `change` is a field the page shows that is wrong or missing — title, creators, the venue (`publicationTitle`, `proceedingsTitle` …), date, DOI, item type; capitalisation or an abbreviation alone is no change;
- `changes.<n>.jsonl`, one `update_item --batch` line per item to change: `{"key", "set": {field: value}, "why"}`, the field names as the line's `item` has them, the values as the page gives them (a date as printed there; `creators` a list of `{"creatorType", "lastName", "firstName"}`). Only items with a change go in; with none, there is no file.

**Done when** every item of yours has its verdict line, each given after reading its PDF's first page against the item's fields, and, if you wrote `changes.<n>.jsonl`, `uv run scripts/p2z.py update_item --batch <imp>/recognize/changes.<n>.jsonl --dry-run`, run from paper-to-zotero's directory, exits 0 and plans each change as you meant it.

**Report** whether the done-when holds — a dry run that cannot reach Zotero is the first line — then only the exceptions, one line each: an item answered `unknown` and what it lacked; anything in the skill that misled you.

**Rules.**
- Do the work yourself; send no subagents. No git.
- The files you write yourself go under `<imp>/recognize/` only; what the skill's commands write is theirs.
- If you cannot finish, say what you tried, what you settled and what is left.
- Touch no website: everything is in the files and in the local Zotero the skill's commands read.
