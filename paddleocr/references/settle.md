# Settling a parse

This brief is for settling one document that the paddleocr skill has parsed. Check every warning and every figure note against the source, fix the Markdown, and report back. The agent that sent you reads the result and builds its answer on it. A wrong fix costs that answer; confirming a false alarm costs nothing.

Your prompt names the document's folder and its source: a PDF, or the page images. The folder holds:

- `<stem>.md`: the text, page by page, with `<!-- page N -->` before each page.
- `<stem>.json`: every block with its `page`, `label` and `bbox` (in page-image pixels; see `pages[].width` / `height`), and the parse's `warnings`.
- `imgs/`: the figure crops.
- `checks/`: the figure overlays.

The prompt may also name figures to settle, by page and caption.

You are the only one writing to this Markdown. Leave the JSON as parsed.

## Sources

- **A PDF** has two sources for a page:
  - its text layer: `pdftotext -layout -f <N> -l <N> <pdf> -`. A warning's `region` goes in as `-x -y -W -H`, in points.
  - its image: `pdftoppm -f <N> -l <N> -r 100 -png <pdf> <prefix>`, which you view. Tables and small print need `-r 300`. A region crop at `-r 300` takes the points × 300/72, since pdftoppm counts in pixels.
- **Image input** is its own source: view the input image, cropped and enlarged where the print is small.

## 1. Text warnings

Settle every warning in the JSON's `warnings` except `figure_check` (step 2). Settling one means one of three things: you fixed it, you found it a false alarm, or it is a gap you cannot close.

Fix `<stem>.md` at its page, and put an HTML comment on the line before each fixed block: `<!-- from text layer: what changed -->` or `<!-- from page image: … -->`. A rebuilt table stays HTML. Use `rowspan`/`colspan` for multi-level headers, and an empty cell to head a column that has no heading.

The warnings, by remedy:

- **Lost or misread.** The text layer has it and the parse does not; restore it from the text layer.
  - `table_mismatch`: the table lost cells, often a whole column, and the remaining values can sit under the wrong headers (2026-10: five of the twenty text tables in six test papers). Rebuild it from `pdftotext -layout` over the warning's `region`, check it against the page image, and replace the table.
  - `missing_numbers`: numbers the parse lacks or misread.
  - `missing_text`: a run of words, sampled in `detail`: a dropped line, or author affiliations read as icons. False alarms: the labels and legends of a complex figure, a watermark, a download stamp.
  - `low_coverage`: the page as a whole matched poorly. The cause is a garbled text layer (odd font encodings) or a page dense with formulas. Compare a paragraph of the page image with the Markdown.
- **Invented.** The parse has text the source lacks. Delete it, or replace the block from the text layer or the image.
  - `extra_text`: words the text layer lacks, typically the model finishing a sentence that is cut off at the page end.
  - `foreign_script`: CJK, kana or Hangul characters mixed into the text that the text layer lacks (2026-10: 「年第」 and 「个」 inside an English sentence with inline math); `detail` quotes each spot. The words around them are often garbled too, so rebuild the passage from the text layer.
  - `repetition`: one phrase looped dozens of times, or a block cycling through the same words (2026-10: a 23-name author line run on to 8,857 characters). Keep one pass, checked against the source.
- **Misplaced.**
  - `table_empty_column`: a headed column is empty in every row and the values have slid one column over; often a figure grid read as a table. Realign the values from the source.
  - `formula_number_gap`: equation numbers are missing from a run. Find those equations on the page image, where the numbers show even when the text layer drops them. Add each number as `\tag*{(n)}` to its formula.
- **Unchecked.** There is nothing to check against.
  - `unchecked_table`: a table embedded as an image. Compare its values with the page image, cell by cell.
  - `no_text_layer`: scans and images. Look first at the last block of every page, where the model invents the rest of a sentence cut at the page end. Then look at small print (author lines, affiliations, superscripts), then at every table, cell by cell.
  - `empty_page`: confirm from the image that the page is blank or purely graphic.

A block in the JSON with a `merged_into` id lost nothing: its content moved into that earlier block. Examples: a paragraph continued across a column, a table continued on the next page, a panel or panel letter moved into its whole `figure`. Text inside figures is not transcribed and is not checked.

Done when every warning is settled.

## 2. Figures

Settle every figure that has a note in the Markdown, and every figure your prompt names. A note looks like `<!-- figure_check: <reasons> [p<page>#<caption id> checks/….jpg] -->`. The figure's warning in the JSON carries the same reasons, its crops with their boxes, and the second opinion's box. The reasons:

- `no_crop`: the figure was read as text or a table, or missed. False alarms: a list of figure captions, a sentence opening with "Figure 2.".
- `split`: the figure is in several crops.
- `two_figures`: one crop holds two figures.
- `table`: a table was drawn into the figure.
- `edge_cut`: an edge runs through text or lines.
- `second_opinion`: the extent found from the caption outwards differs from the crop's.

For each figure:

1. Open its overlay (`checks/…jpg`). It shows the page with the caption in blue, every crop numbered in its own colour, and the second opinion as a green dashed box. Judge the numbered crops first, on their own: does one crop hold the whole figure, and nothing but it — no other figure, table or body text? Then weigh the reasons and the second opinion.
   - A figure spread over several crops still needs one crop of its own, even when each piece is a whole panel.
   - For `edge_cut`, view that edge in the crop itself, enlarged. The overlay is too small to show a line of text sliced in half.
2. Whole and clean: keep it. Open the note with `figure kept:`.
3. Otherwise cut a crop (below). Start from the warning's `second_opinion` box (in pixels, like the JSON boxes) when it looks right, else from the JSON boxes. Then open the note with `from page image: figure cropped by hand;`. The second opinion is a candidate: view its crop before you use it.
4. A `no_crop` figure whose text the Markdown already holds, where colours and layout add nothing: open the note with `figure kept: the text is in the Markdown;`.

Each new opening takes the place of `figure_check:`. Change nothing else in the note: its bracket is how a later check finds it. When a named figure has no note, put `<!-- from page image: figure cropped by hand -->` above its new crop.

To cut a crop:

1. Crop the PDF page at the parse's `crop_dpi` (in the JSON's `parser`; 144 when absent). JSON boxes are in 144 dpi pixels, so multiply each by k = crop_dpi/144: `pdftoppm -f <N> -l <N> -r <crop_dpi> -x <x1·k> -y <y1·k> -W <width·k> -H <height·k> -singlefile -png <pdf> <folder>/imgs/p<NN>_fig<number>_cut`. For image input, crop the input image at the JSON box itself.
2. For the starting box, use what the model made of the figure: the incomplete crop, or the table or text blocks right above its caption.
3. View the crop and move its edges until it holds the whole figure and no caption or body text. The figure can be wider than its caption or sit beside it.
4. Put its `![](imgs/…png)` line in place of the lines of every crop it now covers, or right before the caption when there was none. Put the figure's note above it. Keep the blocks the model read from the figure: their text is the figure's words.

Done when every note is settled, or left open with its reason in your report, and every named figure has been seen whole.

## 3. Report

Reply with these four parts, one line per item, so that the agent that sent you can carry them into its own report:

- **fixed**: page, warning code, what changed.
- **false alarms**: page, warning code, why.
- **open**: what you could not settle, and why.
- **figures**: recropped (`p<page>#<id>`, what was wrong), kept (`p<page>#<id>`), kept as text (`p<page>#<id>`).
