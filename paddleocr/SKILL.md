---
name: paddleocr
description: Parses a PDF or page images (papers and other documents, scans, screenshots) into Markdown with PaddleOCR-VL on the local GPU — formulas as LaTeX, tables as HTML, figures as images. Use when a document has to be read in full, quoted, or mined for its tables and formulas (读全文、PDF/截图/扫描件转 Markdown 或结构化), instead of reading it as page images.
---

# PaddleOCR

From a PDF or page images to text an agent can read whole and trust: `<stem>.md`, the document page by page in reading order, generated from `<stem>.json`, its record of what the models gave and of every change made since, with who made it and why. The model reads pixels, so scans, screenshots and tables embedded as images come out as text too; figures stay images.

**Calling.** Start every shell call with this statement, filled in with this file's absolute directory: `set -o pipefail; export PATH="<this directory>/scripts:<this directory>/../vllm-serve/scripts:$PATH";` — `ocr.py` and vllm-serve's `serve.py` are then found from any directory, and a failure anywhere in a pipe sets the call's exit code. `ocr.py -h` lists the words; `ocr.py <word> -h` is each one's reference: options, lines, exit codes (`parse -h` the folder layout, `findings -h` the finding codes). stdout is data (`show`'s is text to read); stderr holds progress and warnings, so keep it: on exit 2 its last line `{code, hint}` says why nothing could go on. `ocr.py parse` needs the `paddleocr` uv tool on an NVIDIA GPU; `paddleocr_missing`, a `vl_server_*` code, a crash at start-up, a hang of the native backend, or no `pdftotext` / `pdftoppm` → [references/install.md](references/install.md).

A paper (a journal or conference article, a preprint, a thesis chapter) → also [references/papers.md](references/papers.md): how papers number figures, tables and equations, and what goes wrong in them.

## Steps

### 1. Parse

```bash
ocr.py parse <document.pdf> [more inputs ...] -o <outdir>/
```

Give all the documents in one call: the models load once per call. The first run downloads about 2 GB of models into `~/.paddlex/official_models/`. Run anything beyond a few pages in the background and wait for it to exit.

- `<outdir>`, an absolute path: where the user wants it, else your scratch or work directory — never this skill's directory or the folder another program keeps the source in.
- Only part of a long document is needed: `--pages 3-12`. Photographed or skewed pages: `--photo`.

The backend, named in each line's `backend`, sets the speed (`parse -h`). The vllm-serve skill's server, when not yet running, takes one to two minutes to start (more on its first start after a vLLM install, and for the model's first download); it is shared and stops by itself ten minutes after its last use, so leave it running. A run that goes native says why on stderr: for a batch, pass that reason on to the user, and when vllm-serve or vLLM is missing, add that it would parse ten to twenty times faster ([references/install.md](references/install.md)).

A parse the VL server holds up — stderr quiet for minutes after `[paddleocr] asking vllm-serve …`, `[vllm-serve] the last start … failed`, or `port_busy` in the reason — → [references/install.md](references/install.md), *When the server holds a parse up*.

Done when every input has its line with `code` `ok` or `skipped`. Parsing a document again keeps the edits made to it, under `-f` too (`parse -h`).

### 2. Settle

The parse line's `open` lists its open findings: places where the checks against the source suspect the parse lost, garbled or invented something, or cut a figure wrong (`findings -h`). Settling checks each against the source, fixes the Markdown or gives a verdict, and records that with `ocr.py commit`.

That is routine work, so hand each document to a background subagent on a cheap model that can view images (Claude Code `model: "sonnet"`, Codex `luna`). Give it:

- the absolute path of [references/settle.md](references/settle.md), its brief;
- the document's folder, `<outdir>/<stem>`;
- its source: the PDF, or the image input;
- for a paper, the absolute path of [references/papers.md](references/papers.md);
- figures your task rests on that no finding flags, by page and caption.

One subagent per document, which is then the only writer of its folder; at most five run at once unless the user sets another limit.

- A document with no open findings needs no subagent.
- In a batch parsed for later use, leave the findings open: each document is settled when a task first reads it.
- Without subagents, follow the brief yourself.
- Findings still open after the report go back to the same subagent with `ocr.py findings`' lines as printed (Claude Code `SendMessage`); if it cannot be resumed, a new subagent gets the same brief, the folder as it stands, those lines and the first report.

Done when every document you will read has its subagent's report back and `ocr.py findings <outdir>/<stem>` exits 0.

### 3. Read and report

Read `<stem>.md`: all of it when the task is the document, the sections that matter when it is one question.

- `<!-- page N -->` precedes each page; cite pages by it.
- Formulas are LaTeX, numbered as `\tag*{(n)}`. Tables are HTML; a table continued over pages is one table, at its first page, followed by `<!-- table <id> continues on page N -->`: a value from its lower rows may sit on that later page, so confirm it in the text layer of both pages before citing a page.
- A figure is its image, `![…](imgs/<figure id>.png)`, alt text the figure number when a caption gives one. Text the model read inside the figure (titles, axis labels, panel headings) stays where the model put it, between `<!-- figure <id> … -->` and `<!-- end figure <id> -->`: headings there belong to the figure, not to the document's sections. A data table in place of a chart (`--charts`) holds values read off the plot: verify them against the image.
- `<!-- fixed: … -->` marks a settled edit and its reason; `<!-- unresolved <id>: … -->` an error known and left: take that spot from the source. `<!-- open <id>: … -->` was never checked: check that spot against the source before relying on it.
- Running heads, page numbers and page footers live only in the record. Footnotes come at the end of their page; margin notes, such as an arXiv stamp, stay in the text.
- `ocr.py show <folder> <block id or pN>`: a block's or page's text, its box in source units (PDF points), the text layer under it, and a page image.

The checks see only what a text layer can prove, so a settled parse is not yet a verified one. Done when two things hold:

- every number, equation (with its number) and table cell your answer rests on has been confirmed in the source and is cited by page;
- every figure the answer rests on has been seen whole, in its image or on the page image.

Then delete the folders `ocr.py show` wrote for your documents under `$TMPDIR/paddleocr-show/`, and report:

- the Markdown and record paths;
- the parse line's `min_coverage`, or that the pages had no text layer;
- the settle report: the fixes, the figures recut or kept, the verdicts, and anything left unresolved;
- what you took from figure images rather than text;
- a caption style the settle report says the conventions miss, with its example caption: for the user to take to this skill as an issue (the conventions are its code, changed in its repository, not in an installed copy).
