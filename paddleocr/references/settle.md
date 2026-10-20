# Settling a parse

This brief is for settling one document that the paddleocr skill has parsed: check every open finding and every figure note against the source, fix the Markdown or give a verdict, record it, and report back. The agent that sent you reads the result and builds its answer on it. A wrong fix costs that answer; confirming a false alarm costs nothing.

Your prompt names the document's folder and its source: a PDF, or the page images. It may also name figures to settle, by page and caption, and, for a paper, the path of `papers.md`: read that too, it adds what papers get wrong.

The folder holds:

- `<stem>.md`: the text, page by page, with `<!-- page N -->` before each page. This is what you edit.
- `<stem>.json`: the record. `doc.py` writes it; leave it to `doc.py`.
- `imgs/`: the figures, named by figure id.

You are the only one writing to this folder.

## Tools

`doc.py` below is `uv run <skill>/scripts/doc.py`, where `<skill>` is the folder above the one holding this brief.

- `doc.py show <folder>`: the open findings, one per line: status, id, page, what it saw.
- `doc.py show <folder> <finding id>`: the finding in full, the block it concerns with its text, the text layer under it (the `pdftotext` command for that region), and a page image with the block boxed. For a `figure_check`: the crops and the second opinion as boxes, and an overlay image.
- `doc.py show <folder> p<N>`: every block of page N with its id, label, box and first words, and a page image with the block ids drawn on it.
- `doc.py show <folder> p<N> --box X1 Y1 X2 Y2 --dpi 400`: that region of the page as an image, for small print and figure edges.

Boxes are in source units: PDF points for a PDF, as `pdftotext -x -y -W -H` takes them; pixels for image input.

- **A PDF** has two sources for a page: its text layer (`pdftotext -layout -f N -l N <pdf> -`, or the region `show` gives), and its image (the page images `show` writes). Trust the text layer for characters and the image for layout.
- **Image input** is its own only source: view the image, cropped and enlarged where the print is small.

## Recording

1. **Edit `<stem>.md`** with your editing tool, at the block's own place. Rewrite text freely inside a block: a word, a table cell, a whole table, a paragraph. Put `<!-- fixed: <what changed, from which source> -->` on the line above each block you edit.
   - A paragraph of your own (blank lines around it) becomes a new block; a line added without a blank line joins the paragraph it touches.
   - An edit across several blocks, such as two paragraphs put in the right order, keeps the text in the first block and deletes the others.
   - A rebuilt table stays HTML. Use `rowspan`/`colspan` for multi-level headers, and an empty cell to head a column that has no heading.
   - Leave the first line, the `<!-- page N -->` lines and the `<!-- figure … -->` / `<!-- end figure … -->` lines as they are: they tie the Markdown to the record, and commit refuses edits to them.
2. **Give a verdict** where there is nothing to fix: change the note's `open` to `ok` (the parse is right, or the finding is a false alarm) or to `unresolved` (the parse is wrong and cannot be fixed), and put your reason after the colon in place of what was there: `<!-- ok missing_numbers@p11: tick labels of the Figure 3 axes -->`. A finding you fix needs no verdict: once fixed it goes away.
3. **Commit:** `doc.py commit <folder>`. It records each edit as a change of its block, each verdict with its reason, runs the checks again and rewrites the Markdown. It prints what it recorded and which findings went, came or reopened. A finding still there after your fix means the fix missed: look again. Commit after each page you work through.

When commit refuses, it says why; put back what it names and commit again.

## 1. Text findings

Settle every open finding except `figure_check` (§2). Each one ends fixed, `ok`, or `unresolved`.

The codes, by remedy:

- **Lost or misread.** The text layer has it and the parse does not: restore it from the text layer.
  - `table_mismatch`: the table lost cells, often a whole column, and the remaining values can sit under the wrong headers (2026-10: five of the twenty text tables in six test papers). Rebuild it from `pdftotext -layout` over its region, check it against the page image, and replace the table.
  - `missing_numbers`: numbers the parse lacks or misread.
  - `missing_text`: runs of words the parse lacks, quoted in the note as the text layer has them: a dropped line or paragraph end, or a misread that breaks the words around it. False alarms: the labels and legends of a figure, a watermark, a download stamp, a formula the text layer garbles but the parse holds as LaTeX.
  - `low_coverage`: the page as a whole matched poorly. The cause is a garbled text layer (odd font encodings) or a page dense with formulas. Compare a paragraph of the page image with the Markdown.
- **Invented.** The parse has text the source lacks: delete it, or replace the block from the text layer or the image.
  - `extra_text`: words the text layer lacks, typically the model finishing a sentence cut off at the page or column end. False alarm: a sentence that continues at the top of the next column.
  - `foreign_script`: CJK, kana or Hangul characters mixed into text that lacks them. The words around them are often garbled too, so rebuild the passage from the text layer.
  - `repetition`: one phrase looped dozens of times, or a block cycling through the same words. Keep one pass, checked against the source.
- **Misplaced.**
  - `table_empty_column`: a headed column is empty in every row and the values have slid one column over; often a figure grid read as a table. Realign the values from the source.
  - `formula_number_gap`: equation numbers are missing from a run. Find those equations on the page image, where the numbers show even when the text layer garbles them, and add each as `\tag*{(n)}` at the end of its formula, inside the `$$`.
- **Unchecked.** There is nothing to check against.
  - `unchecked_table`: a table embedded as an image. Compare its values with the page image, cell by cell.
  - `no_text_layer`: scans and images. Look first at the last block of every page, where the model invents the rest of a sentence cut at the page end; then at small print (names, affiliations, superscripts); then at every table, cell by cell.
  - `empty_page`: confirm from the image that the page is blank or purely graphic.
- `stale_edit`: an earlier edit no longer fits the block's text, after the document was processed again. Redo the edit if it is still needed; else give the verdict `ok`.

Done when `doc.py show <folder>` lists no open finding but `figure_check` ones.

## 2. Figures

Settle every `figure_check` finding and every figure your prompt names. The reasons a figure was flagged:

- `no_crop`: the figure was read as text or a table, or missed. False alarms: a list of figure captions, a sentence opening with "Figure 2."
- `split`: the figure is in several images.
- `two_figures`: one image holds two figures.
- `table`: a table was drawn into the figure.
- `edge_cut`: an edge runs through text or lines.
- `second_opinion`: the extent found from the caption outwards differs from the image's.

For each:

1. `doc.py show <folder> <finding id>` and open its overlay: the caption in blue, each image on the page numbered in its own colour, the second opinion as a green dashed box. Judge the numbered images first, on their own: does one image hold the whole figure, and nothing but it (no other figure, table or body text)? Then weigh the reasons and the second opinion. For `edge_cut`, view that edge enlarged (`show p<N> --box … --dpi 400`): the overlay is too small to show a line of text sliced in half. The second opinion is a candidate and can be the wrong one, taking in a table or a note under the figure.
2. Whole and clean: verdict `ok`, with what you checked.
3. Otherwise cut it anew: `doc.py figure <folder> <figure id> --box X1 Y1 X2 Y2 --why "<what was wrong>"`, starting from the second opinion's box when it looks right. It prints the new image's path: view it, and cut again until it holds the whole figure and no caption or body text. A figure can be wider than its caption or sit beside it. The image blocks inside the box become part of this figure, so for a figure split into several images, cut any one of them to the whole box and the others go with it. The finding goes once the figure is cut.
4. A figure the parse read as text or missed (`no_crop`): `doc.py figure <folder> --page N --box … --why …` makes it, and the text the model read from it stays. When that text already says everything and its colours and layout add nothing, verdict `ok` instead.

An image that is no content of the document, such as a logo or a stray icon: delete its image line in the Markdown to hide it.

Look at every figure on a page you open: a flagged figure often has an unflagged neighbour with the same fault.

Done when every `figure_check` finding is gone or has a verdict, and every named figure has been seen whole.

## 3. Beyond the findings

The checks see only what a text layer can prove; these slip past them (2026-10, six papers):

- **A paragraph that ends early with an invented closing.** The block's box is far taller than its text needs; `missing_text` and `missing_numbers` on the same page are the trace.
- **Text joined in the wrong order across columns.** Every word is present, so no check fires; look for a sentence that breaks off and continues with an unrelated one.
- **A garbled first line at the top of a page or column**, numbers included.
- **Digit and letter confusions** (1↔I, l↔I, 0↔O) in names, acronyms and identifiers. Once found, search the whole document for the same token.
- **A real word in place of another** ("faintest" for "fairest"), which no coverage check notices.
- **Line-break hyphens kept or invented** in compound names ("Duck-DuckGo").
- **Header cells merged** in a table whose values are right.
- **Inline math garbled** in pseudo-code and tables.
- **A long line cut by your reading tool** is not a truncated paragraph: check its length or its tail before calling it cut.

On every page, compare the last block and the first line of each column with the text layer (or, without one, the image), and fix what you find the same way, with a `fixed` note. Where a page has a finding, read that page whole.

Done when every page's last block and column starts have been compared; the report says how many pages that was.

## 4. Report

Commit a last time, then reply with these five parts, one line per item, so that the agent that sent you can carry them into its own report:

- **fixed**: page, block or finding id, what changed.
- **verdicts**: finding id, `ok` or `unresolved`, the reason.
- **figures**: cut anew (figure id, what was wrong), kept (figure id), made (figure id).
- **read**: the pages compared in §3, and what you found there.
- **open**: anything you could not settle, and why; the last commit's output when it is not empty.
