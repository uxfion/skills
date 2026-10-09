---
name: paddleocr
description: Parses a paper's PDF or page images (screenshots, scans) into full-text Markdown and block JSON with PaddleOCR-VL on the local GPU — formulas as LaTeX, tables as HTML, figures as crops beside their captions — checked against the PDF text layer. Use when a paper or other document has to be read in full, quoted, or mined for its tables and formulas (读文献全文、PDF/截图/扫描件转 Markdown 或结构化), instead of reading it as page images.
---

# PaddleOCR

From a PDF or page images to text an agent can read whole: `<stem>.md`, the document page by page in reading order, and `<stem>.json`, every block with its page, label and box, both checked against the PDF's own text layer. The model reads pixels, so scans, screenshots and tables embedded as images come out as text too; figures stay images, cropped beside their captions.

Script paths are relative to this file's directory. `uv run scripts/parse.py --help` is the reference for flags, the output layout and the warning codes. The script needs the `paddleocr` uv tool on an NVIDIA GPU, and parses ten to twenty times faster with the vllm-serve skill beside it; `paddleocr_missing`, a `vl_server_*` error, a crash at start-up or a hang → [references/install.md](references/install.md).

## Steps

### 1. Parse

```bash
uv run scripts/parse.py <paper.pdf> [more inputs ...] -o <outdir>
```

Each input is one document: a PDF, an image, or a directory of page images in filename order. Give all the papers in one call: the models load once per call. The first run downloads about 2 GB of models into `~/.paddlex/official_models/`.

Speed depends on the backend, which each summary names in `backend`. With the vllm-serve skill installed, a call with 8 or more pages to parse, or any call while that server runs, gets the VL model's vLLM server from it (30–60 s to start when it is not running) and then takes 0.5–1 s a page; the server is shared and stops by itself ten minutes after its last use, so leave it be. Otherwise the native backend takes 10–15 s a page: for a batch of papers without vllm-serve, tell the user it would be ten to twenty times faster and point to [references/install.md](references/install.md). Pages finish in batches, so the per-page lines on stderr (prefixed `[paddleocr]`, among Paddle's own log lines) come in bursts. Run anything beyond a few pages in the background and wait for it to exit; each document's summary line reaches stdout when that document is done.

- Only part of a long document is needed (a thesis chapter, a paper without its appendix): `--pages 3-12`; the output keeps the original page numbers.
- Photographed or skewed pages: `--photo`.
- A paper in Zotero, named by title, author or citation key: [references/zotero.md](references/zotero.md) finds its PDF.
- `<outdir>`, an absolute path: where the user wants it, else your scratch or work directory — never this skill's directory or the folder another program keeps the PDF in.

Done when every input has its summary line without `error`. `skipped: up_to_date` means an earlier parse with the same file and options is already there; with `rechecked: true`, newer checks have just re-examined it, and its Markdown may already carry fixes (`<!-- from … -->`) for some of the warnings.

### 2. Check

Each summary's `warnings` mark where the parse lost, garbled or invented text. Settle every one against the source:

- **A PDF** has its page's text layer, `pdftotext -layout -f <N> -l <N> <pdf> -` (a warning's `region` goes in as `-x -y -W -H`, in points), and its image, `pdftoppm -f <N> -l <N> -r 100 -png <pdf> <prefix>`, which you view. Tables and small print need `-r 300`; a region crop there takes the points × 300/72, as pdftoppm counts pixels.
- **Image input** is its own source: the input image, cropped and enlarged where print is small.

Fix `<stem>.md` at its page, with an HTML comment on the line before each fixed block: `<!-- from text layer: what changed -->` or `<!-- from page image: … -->`. A rebuilt table stays HTML, with `rowspan`/`colspan` for multi-level headers and an empty cell heading an unheaded column. The JSON stays as parsed, and `--force` or a rerun with other options overwrites the Markdown, fixes included.

The warnings, by remedy:

- **Lost or misread** — the text layer has it, the parse does not; restore it from the text layer:
  - `table_mismatch`: the table lost cells, often a whole column, and the remaining values can sit under the wrong headers (2026-10: five of the twenty text tables in six test papers). Rebuild it from `pdftotext -layout` over the warning's `region`, check it against the page image, and replace the table.
  - `missing_numbers`: numbers the parse lacks or misread.
  - `missing_text`: a run of words, sampled in `detail` — a dropped line, author affiliations read as icons. Labels and legends of a complex figure, a watermark or a download stamp are false alarms.
  - `low_coverage`: the page as a whole matched poorly — a garbled text layer (odd font encodings) or a page dense with formulas; compare a paragraph of the page image with the Markdown.
- **Invented** — the parse has text the source lacks; delete it, or replace the block from the text layer or image:
  - `extra_text`: words the text layer lacks, typically the model finishing a sentence that is cut off at the page end.
  - `foreign_script`: CJK, kana or Hangul characters the text layer lacks, mixed into the text (2026-10: 「年第」 and 「个」 inside an English sentence with inline math); `detail` quotes each spot. The words around them are often garbled too: rebuild the passage from the text layer.
  - `repetition`: one phrase looped dozens of times, or a block cycling through the same words (2026-10: a 23-name author line run on to 8,857 characters). Keep one pass, checked against the source.
- **Misplaced**:
  - `table_empty_column`: a headed column empty in every row, the values slid one column over; often a figure grid read as a table. Realign from the source.
  - `formula_number_gap`: equation numbers missing from a run; find those equations in the source and add each as `\tag*{(n)}` to its formula.
- **Unchecked** — nothing to check against:
  - `unchecked_table`: a table embedded as an image; compare the values you will use with the page image.
  - `no_text_layer`: scans and images. Look first at the last block of every page, where the model invents the rest of a sentence cut at the page end; then at small print (author lines, affiliations, superscripts); then at every table you will use, cell by cell.
  - `empty_page`: confirm from the image that the page is blank or purely graphic.

A block in the JSON with empty `text` and a `merged_into` id lost nothing: its content moved into that earlier block (a paragraph continued across a column, a table continued on the next page). Text inside figures is not transcribed and is not checked.

Done when every warning is settled as a fix, a false alarm, or a gap you will name to the user.

### 3. Read and report

Read `<stem>.md` — all of it when the task is the paper, the sections that matter when it is one question:

- `<!-- page N -->` precedes each page; cite pages by it.
- Formulas are LaTeX (`display_formula` blocks in the JSON), numbered as `\tag*{(n)}`; tables are HTML, and a table continued over pages is one table at its first page. A `<table>` whose caption says "Fig." is a figure grid read as a table.
- Figures are `![](imgs/…)` crops followed by their captions. Open a crop when an answer depends on what a figure shows. `--figure-text` adds the text inside figures; `--charts` turns charts into data tables, with values the model read off the plot — verify them against the crop.
- Running heads, page numbers and page footers live only in the JSON (`--keep-all` keeps them in the Markdown); footnotes and margin notes, such as the arXiv stamp, stay in the text.
- The JSON gives positions: `label`, `bbox` in page-image pixels (`pages[].width` / `height`), heading `level`. The summary's `blocks` counts blocks by label.

The checks see only what a text layer can prove, so a parse without warnings is not yet a verified one. Done when every number, equation (with its number) and table cell your answer rests on has been confirmed in the text layer or the page image and is cited by page.

Report the Markdown and JSON paths, the summary's `min_coverage` (or that the pages had no text layer), the fixes you made, what you took from figure images rather than text, and any warning left open.
