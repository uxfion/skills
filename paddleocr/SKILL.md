---
name: paddleocr
description: Parses a paper's PDF or page images (screenshots, scans) into full-text Markdown and block JSON with PaddleOCR-VL on the local GPU — formulas as LaTeX, tables as HTML, figures as crops beside their captions — checked against the PDF text layer. Use when a paper or other document has to be read in full, quoted, or mined for its tables and formulas (读文献全文、PDF/截图/扫描件转 Markdown 或结构化), instead of reading it as page images.
---

# PaddleOCR

From a PDF or page images to text an agent can read whole: `<stem>.md`, the document page by page in reading order, and `<stem>.json`, every block with its page, label and box, both checked against the PDF's own text layer. The model reads pixels, so scans, screenshots and tables embedded as images come out as text too; figures stay images, cropped beside their captions.

Script paths are relative to this file's directory. `uv run scripts/parse.py --help` is the reference for flags, the output layout and the warning codes. The script needs the `paddleocr` uv tool on an NVIDIA GPU; `paddleocr_missing`, a `vl_server_*` error, a crash at start-up, a hang, or no `pdftotext` / `pdftoppm` → [references/install.md](references/install.md).

## Steps

### 1. Parse

```bash
uv run scripts/parse.py <paper.pdf> [more inputs ...] -o <outdir>
```

Each input is one document: a PDF, an image, or a directory of page images in filename order. Give all the papers in one call: the models load once per call. The first run downloads about 2 GB of models into `~/.paddlex/official_models/`.

Speed depends on the backend, named in each summary's `backend`. Whenever the vllm-serve skill can provide the VL model's vLLM server (that skill and its vLLM installed, room on the GPU), the call uses it, however few the pages: 30–60 s to start the server when it is not running, then 0.5–1 s a page. The server is shared and stops by itself ten minutes after its last use, so leave it be. Otherwise the call goes native at 10–15 s a page, and stderr says why; for a batch of papers, pass that reason on to the user, and when vllm-serve or vLLM is missing, add that it would parse ten to twenty times faster ([references/install.md](references/install.md)).

Run anything beyond a few pages in the background and wait for it to exit; each document's summary line reaches stdout when that document is done. Pages finish in batches, so the per-page lines on stderr (prefixed `[paddleocr]`, among Paddle's own log lines) come in bursts.

- Parses made by an earlier version of this skill: rerun with the same output directory and options. They are upgraded in place — figures regrouped, crops cut again at 300 dpi, checks rerun, figures checked, your Markdown fixes kept — without parsing again; other options, or `--force`, parse anew and overwrite the Markdown, fixes included.
- Only part of a long document is needed (a thesis chapter, a paper without its appendix): `--pages 3-12`; the output keeps the original page numbers.
- Photographed or skewed pages: `--photo`.
- Figure detail too fine for the default 300 dpi crops (small print inside a figure): `--crop-dpi 600`; on a parsed PDF it only cuts the crops again.
- A paper in Zotero, named by title, author or citation key: [references/zotero.md](references/zotero.md) finds its PDF.
- `<outdir>`, an absolute path: where the user wants it, else your scratch or work directory — never this skill's directory or the folder another program keeps the PDF in.

Done when every input has its summary line without `error`. `skipped: up_to_date` means an earlier parse with the same file and options is already there. The other flags say what a rerun has just done:

- `rechecked: true`: newer checks have re-examined the parse, and its Markdown may already carry fixes (`<!-- from … -->`) for some of the warnings.
- `regrouped: true`: figures that were split into panels have been put back together.
- `recropped: true`: the crops have been cut again at `--crop-dpi`.
- `figures_checked: true`: the figures have been checked, and step 2 settles them.

### 2. Settle

A parse comes with warnings about what it may have got wrong. The JSON's `warnings` flag text the parse may have lost, garbled or invented. A `figure_check` note in the Markdown flags a figure whose crop may be wrong. Settling means checking each against the source and fixing the Markdown.

That is routine work, so hand each document to a subagent on a smaller model that can view images (in Claude Code, `sonnet`). Give it:

- the absolute path of [references/settle.md](references/settle.md), its brief;
- the document's folder, `<outdir>/<stem>`;
- its source: the PDF, or the image input.

Each document goes to one subagent, which is then the only writer of its Markdown. Separate documents go to separate subagents, at most five running at once unless the user sets another limit.

- A document with no warnings needs no subagent.
- In a batch parsed for later use, each document is settled when a task first reads it. Until then its warnings stay in its JSON and its notes in its Markdown.
- Without subagents, follow the brief yourself.

Done when every document you will read has its subagent's report back: fixed, false alarms, open, figures.

### 3. Read and report

Read `<stem>.md`: all of it when the task is the paper, the sections that matter when it is one question.

- `<!-- page N -->` precedes each page; cite pages by it. A `<!-- from … -->` comment before a block marks a settled fix.
- Formulas are LaTeX (`display_formula` blocks in the JSON), numbered as `\tag*{(n)}`. Tables are HTML, and a table continued over pages is one table, at its first page. A `<table>` whose caption says "Fig." is a figure grid read as a table.
- Figures are `![](imgs/…)` crops, each followed by its caption. Open a crop when an answer depends on what a figure shows.
  - A figure of several panels is one crop, a `figure` block in the JSON. Each panel keeps its own crop (its block's `image`) for a closer look.
  - `--figure-text` adds the text inside figures. `--charts` turns charts into data tables, with values the model read off the plot; verify those against the crop.
  - The note before a figure says how it was settled. `figure kept:` means the crop was whole, or its text is in the Markdown. `from page image: figure cropped by hand` means it was cut anew.
  - A note still opening with `figure_check:` was left open. View the figure on the page image before relying on it.
  - A crop that lacks what its caption describes, such as a panel or labels the model read as text: send that figure to a subagent the same way, naming it by page and caption.
- Running heads, page numbers and page footers live only in the JSON (`--keep-all` keeps them in the Markdown). Footnotes and margin notes, such as the arXiv stamp, stay in the text.
- The JSON gives positions: `label`, `bbox` in page-image pixels (`pages[].width` / `height`), and heading `level`. A block with a `merged_into` id has moved into that block. The summary's `blocks` counts blocks by label.

The checks see only what a text layer can prove, so a settled parse is not yet a verified one.

Done when two things hold:

- every number, equation (with its number) and table cell your answer rests on has been confirmed in the source (the commands are under Sources in [references/settle.md](references/settle.md)), and is cited by page;
- every figure the answer rests on has been seen whole, in its crop or on the page image.

Report:

- the Markdown and JSON paths;
- the summary's `min_coverage`, or that the pages had no text layer;
- the settle report: the fixes, the figures recropped or kept, and anything left open;
- what you took from figure images rather than text.
