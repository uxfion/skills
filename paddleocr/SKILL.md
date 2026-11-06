---
name: paddleocr
description: Parses a PDF or page images (papers and other documents, scans, screenshots) into Markdown with PaddleOCR-VL on the local GPU — formulas as LaTeX, tables as HTML, figures as images. Use when a document has to be read in full, quoted, or mined for its tables and formulas (读全文、PDF/截图/扫描件转 Markdown 或结构化), instead of reading it as page images.
---

# PaddleOCR

From a PDF or page images to text an agent can read whole and trust: `<stem>.md`, the document page by page in reading order, and `<stem>.json`, its record. The record keeps what the models gave, as given, and every change made since, each with who made it and why: the processing's, then the agent's and the user's. The Markdown is generated from the record. The model reads pixels, so scans, screenshots and tables embedded as images come out as text too; figures stay images.

**Calling.** Start every shell call with this statement, filled in with this file's absolute directory: `set -o pipefail; export PATH="<this directory>/scripts:<this directory>/../vllm-serve/scripts:$PATH";` — `ocr.py` and vllm-serve's `serve.py` are then found from any directory, and a failure anywhere in a pipe sets the call's exit code. `ocr.py -h` lists the words; `ocr.py <word> -h` is each one's reference: options, lines, exit codes (`parse -h` the folder layout, `findings -h` the finding codes). stdout is data (`show`'s is text to read); stderr holds progress and warnings, so keep it: on exit 2 its last line `{code, hint}` says why nothing could go on. `ocr.py parse` needs the `paddleocr` uv tool on an NVIDIA GPU; `paddleocr_missing`, a `vl_server_*` code, a crash at start-up, a hang of the native backend, or no `pdftotext` / `pdftoppm` → [references/install.md](references/install.md).

A paper (a journal or conference article, a preprint, a thesis chapter) → also [references/papers.md](references/papers.md): how papers number figures, tables and equations, and what goes wrong in them.

## Steps

### 1. Parse

```bash
ocr.py parse <document.pdf> [more inputs ...] -o <outdir>/
```

Give all the documents in one call: the models load once per call. The first run downloads about 2 GB of models into `~/.paddlex/official_models/`.

Speed depends on the backend, named in each line's `backend`. Whenever the vllm-serve skill can provide the VL model's vLLM server (that skill and its vLLM installed, room on the GPU), the call uses it, however few the pages: starting the server when it is not running takes one to two minutes (more on its first start after a vLLM install, and for the model's first download), then 0.5–1 s a page. The server is shared and stops by itself ten minutes after its last use, so leave it be. Otherwise the call goes native at 10–15 s a page, and stderr says why; for a batch, pass that reason on to the user, and when vllm-serve or vLLM is missing, add that it would parse ten to twenty times faster ([references/install.md](references/install.md)).

When the VL server holds the call up:

- Quiet for minutes after `[paddleocr] asking vllm-serve …`: the server is starting, and the `[vllm-serve]` line below it names its log. Judge it as vllm-serve's SKILL.md says for an `up` that has not returned ("When `up` says more"), with its `serve.py`, which the *Calling* statement puts on the PATH. Judged stuck: `serve.py down paddleocr-vl`, and under `--backend auto`, the default, the call goes native. Then find the cause as that skill says for `server_failed`, before the next parse starts the server again.
- `[vllm-serve] the last start … failed` on stderr: a start failed earlier; find its cause the same way.
- `port_busy` in the reason on stderr: something else holds port 8118, a profile named there or a server started by hand, often PaddleOCR-VL's own. If `curl --noproxy '*' http://127.0.0.1:8118/v1/models` lists PaddleOCR-VL-1.6, pass `--vl-server http://127.0.0.1:8118/v1`; otherwise tell the user.

Run anything beyond a few pages in the background and wait for it to exit; each document's line reaches stdout when that document is done.

- Only part of a long document is needed: `--pages 3-12`; the output keeps the original page numbers.
- Photographed or skewed pages: `--photo`.
- `<outdir>`, an absolute path: where the user wants it, else your scratch or work directory — never this skill's directory or the folder another program keeps the source in.

Done when every input has its line with `code` `ok` or `skipped`. Running again on a parsed document is safe: it is skipped, or processed again without the GPU when this skill's code changed (`rendered: true`), the edits made to it kept; `-f` parses anew and carries the edits over (`parse -h`).

### 2. Settle

A parse comes with findings: places where the checks against the source suspect the parse lost, garbled or invented something, or cut a figure wrong. Each open finding is a note in the Markdown, `<!-- open <id>: … -->`, before its block, figure or page, and the line's `open` lists them. Settling means checking each against the source and either fixing the Markdown or giving a verdict, then recording that in the record with `ocr.py commit`.

That is routine work, so hand each document to a background subagent on a cheap model that can view images (Claude Code `model: "sonnet"`, Codex `luna`). Give it:

- the absolute path of [references/settle.md](references/settle.md), its brief;
- the document's folder, `<outdir>/<stem>`;
- its source: the PDF, or the image input;
- for a paper, the absolute path of [references/papers.md](references/papers.md);
- figures your task rests on that no finding flags, by page and caption.

Each document goes to one subagent, which is then the only writer of its folder. Separate documents go to separate subagents, at most five running at once unless the user sets another limit.

- A document with no open findings needs no subagent.
- In a batch parsed for later use, each document is settled when a task first reads it. Until then its notes stay open.
- Without subagents, follow the brief yourself.
- Findings still open after the report go back to the same subagent with `ocr.py findings`' lines as printed (Claude Code `SendMessage`); if it cannot be resumed, a new subagent gets the same brief, the folder as it stands, those lines and the first report.

Done when every document you will read has its subagent's report back and `ocr.py findings <outdir>/<stem>` prints no line with `status` `open`, and exits 0.

### 3. Read and report

Read `<stem>.md`: all of it when the task is the document, the sections that matter when it is one question.

- `<!-- page N -->` precedes each page; cite pages by it.
- Formulas are LaTeX, numbered as `\tag*{(n)}`. Tables are HTML; a table continued over pages is one table, at its first page, followed by `<!-- table <id> continues on page N -->`.
- A figure is its image, `![…](imgs/<figure id>.png)`, alt text the figure number when a caption gives one. When the model read text inside the figure (titles, axis labels, panel headings), it stays where the model put it, between `<!-- figure <id> … -->` and `<!-- end figure <id> -->`: headings there belong to the figure, not to the document's sections. Open the image when an answer depends on what a figure shows. `--figure-text` adds the text inside figures; `--charts` turns charts into data tables, with values the model read off the plot: verify those against the image.
- `<!-- fixed: … -->` marks a settled edit and its reason. `<!-- unresolved <id>: … -->` marks an error known and left: do not rely on that spot. A note still `open` was never checked: check that spot against the source before relying on it.
- Running heads, page numbers and page footers live only in the record. Footnotes come at the end of their page; margin notes, such as an arXiv stamp, stay in the text.
- Positions: `ocr.py show <folder> <block id or pN>` prints a block's or page's text with its box in source units (PDF points), the text layer under it, and a page image.

The checks see only what a text layer can prove, so a settled parse is not yet a verified one.

Done when two things hold:

- every number, equation (with its number) and table cell your answer rests on has been confirmed in the source (`ocr.py show` gives the text layer and page image), and is cited by page;
- every figure the answer rests on has been seen whole, in its image or on the page image.

Then delete the folders `ocr.py show` wrote for your documents under `$TMPDIR/paddleocr-show/`, and report:

- the Markdown and record paths;
- the parse line's `min_coverage`, or that the pages had no text layer;
- the settle report: the fixes, the figures recut or kept, the verdicts, and anything left unresolved;
- what you took from figure images rather than text;
- a caption style the settle report says the conventions miss, with its example caption: for the user to take to this skill as an issue (the conventions are its code, changed in its repository, not in an installed copy).
