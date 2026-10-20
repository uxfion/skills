---
name: paddleocr
description: Parses a document's PDF or page images (papers, reports, slides, scans, screenshots) into Markdown with PaddleOCR-VL on the local GPU — reading order, formulas as LaTeX, tables as HTML, figures as images — checked against the PDF text layer and settled by an agent. Use when a document has to be read in full, quoted, or mined for its tables and formulas (读全文、PDF/截图/扫描件转 Markdown 或结构化), instead of reading it as page images.
---

# PaddleOCR

From a PDF or page images to text an agent can read whole and trust: `<stem>.md`, the document page by page in reading order, and `<stem>.json`, its record. The record keeps what the models gave, as given, and every change made since, each with who made it and why: the processing's, then the agent's and the user's. The Markdown is generated from the record. The model reads pixels, so scans, screenshots and tables embedded as images come out as text too; figures stay images.

Script paths are relative to this file's directory. `scripts/parse.py` runs the models; `scripts/doc.py` does everything after: `render`, `show`, `commit`, `figure`. Their `--help` is the reference for flags, the folder layout and the finding codes. `parse.py` needs the `paddleocr` uv tool on an NVIDIA GPU; `paddleocr_missing`, a `vl_server_*` error, a crash at start-up, a hang, or no `pdftotext` / `pdftoppm` → [references/install.md](references/install.md).

A paper (a journal or conference article, a preprint, a thesis chapter) → also [references/papers.md](references/papers.md): how papers number figures, tables and equations, and what goes wrong in them.

## Steps

### 1. Parse

```bash
uv run scripts/parse.py <document.pdf> [more inputs ...] -o <outdir>
```

Each input is one document: a PDF, an image, or a directory of page images in filename order. Give all the documents in one call: the models load once per call. The first run downloads about 2 GB of models into `~/.paddlex/official_models/`.

Speed depends on the backend, named in each summary's `backend`. Whenever the vllm-serve skill can provide the VL model's vLLM server (that skill and its vLLM installed, room on the GPU), the call uses it, however few the pages: 30–60 s to start the server when it is not running, then 0.5–1 s a page. The server is shared and stops by itself ten minutes after its last use, so leave it be. Otherwise the call goes native at 10–15 s a page, and stderr says why; for a batch, pass that reason on to the user, and when vllm-serve or vLLM is missing, add that it would parse ten to twenty times faster ([references/install.md](references/install.md)).

Run anything beyond a few pages in the background and wait for it to exit; each document's summary line reaches stdout when that document is done.

- Only part of a long document is needed: `--pages 3-12`; the output keeps the original page numbers.
- Photographed or skewed pages: `--photo`.
- A document in Zotero, named by title, author or citation key: [references/zotero.md](references/zotero.md) finds its PDF.
- `<outdir>`, an absolute path: where the user wants it, else your scratch or work directory — never this skill's directory or the folder another program keeps the source in.

Done when every input has its summary line without `error`. Running again on a parsed document is safe:

- `skipped: up_to_date`: nothing to do.
- `rendered: true`: newer code processed and checked the stored model output again, without the GPU; the edits made to it stayed.
- `--force` parses anew; `edits_carried` counts the edits moved onto the new parse.
- `archived`: a parse by an older version of this skill was moved aside, its Markdown fixes with it, and the document parsed anew.

### 2. Settle

A parse comes with findings: places where the checks against the source suspect the parse lost, garbled or invented something, or cut a figure wrong. Each open finding is a note in the Markdown, `<!-- open <id>: … -->`, before its block, figure or page, and the summary's `open` lists them. Settling means checking each against the source and either fixing the Markdown or giving a verdict, then recording that in the record with `doc.py commit`.

That is routine work, so hand each document to a subagent on a smaller model that can view images (in Claude Code, `sonnet`). Give it:

- the absolute path of [references/settle.md](references/settle.md), its brief;
- the document's folder, `<outdir>/<stem>`;
- its source: the PDF, or the image input;
- for a paper, the absolute path of [references/papers.md](references/papers.md).

Each document goes to one subagent, which is then the only writer of its folder. Separate documents go to separate subagents, at most five running at once unless the user sets another limit.

- A document with no open findings needs no subagent.
- In a batch parsed for later use, each document is settled when a task first reads it. Until then its notes stay open.
- Without subagents, follow the brief yourself.

Done when every document you will read has its subagent's report back and `uv run scripts/doc.py show <outdir>/<stem>` prints `no open findings`.

### 3. Read and report

Read `<stem>.md`: all of it when the task is the document, the sections that matter when it is one question.

- `<!-- page N -->` precedes each page; cite pages by it.
- Formulas are LaTeX, numbered as `\tag*{(n)}`. Tables are HTML; a table continued over pages is one table, at its first page, followed by `<!-- table <id> continues on page N -->`.
- A figure is its image, `![…](imgs/<figure id>.png)`, alt text the figure number when a caption gives one. When the model read text inside the figure (titles, axis labels, panel headings), it stays where the model put it, between `<!-- figure <id> … -->` and `<!-- end figure <id> -->`: headings there belong to the figure, not to the document's sections. Open the image when an answer depends on what a figure shows. `--figure-text` adds the text inside figures; `--charts` turns charts into data tables, with values the model read off the plot: verify those against the image.
- `<!-- fixed: … -->` marks a settled edit and its reason. `<!-- unresolved <id>: … -->` marks an error known and left: do not rely on that spot. A note still `open` was never checked: check that spot against the source before relying on it.
- Running heads, page numbers and page footers live only in the record. Footnotes come at the end of their page; margin notes, such as an arXiv stamp, stay in the text.
- Positions: `uv run scripts/doc.py show <folder> <block id or pN>` prints a block's or page's text with its box in source units (PDF points), the text layer under it, and a page image.

The checks see only what a text layer can prove, so a settled parse is not yet a verified one.

Done when two things hold:

- every number, equation (with its number) and table cell your answer rests on has been confirmed in the source (`doc.py show` gives the text layer and page image), and is cited by page;
- every figure the answer rests on has been seen whole, in its image or on the page image.

Report:

- the Markdown and record paths;
- the summary's `min_coverage`, or that the pages had no text layer;
- the settle report: the fixes, the figures recut or kept, the verdicts, and anything left unresolved;
- what you took from figure images rather than text.
