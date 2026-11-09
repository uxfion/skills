# Papers

What a parse of a paper holds beyond any document, and what goes wrong in papers in particular.

## Reading a paper

- **Figures carry their number**, as the caption writes it ("Figure 3", "Extended Data Fig. 2", "Supplementary Fig. 1", "图 3"), in the alt text and the marker: `![Fig. 3](imgs/p6-4.png)`, `<!-- figure p6-4 (Fig. 3) -->`. Search for the number to find the image; the caption follows the figure as a block of text. A figure with no number has no caption the parse could pair: a full-page figure whose caption opens the next page, or a caption style the conventions miss (below).
- **Equation numbers** the model read outside their formula are joined to it by position.
- **Two-column pages** can be read in the wrong order where a paragraph crosses the column break. A sentence that stops mid-phrase and goes on with something unrelated is the sign; the source decides.
- **Line numbers** of a manuscript under review are left out of the checks.
- **Supplementary material** is often a separate PDF: parse it as its own document.

## Settling a paper

What the six papers of the 2026-10 test got wrong, beyond the generic misreads in `settle.md`:

- **Model and dataset names with digits.** "DeepSeek-RI" for DeepSeek-R1, "O1.AI" for 01.AI, "CULs" for CUIs. The same name usually recurs: search the whole document once you find one.
- **Equation numbers.** A text layer can encode the brackets as other glyphs, `ð5Þ` for (5), so search the text layer for the digit alone. The model can write full-width brackets, `\tag*{（5）}`: change them to `(5)`. A `formula_number_gap` whose number shows on the page image is a missing `\tag*{(n)}`, not an unnumbered equation.
- **Author lines.** Affiliation marks, ORCID and e-mail icons come out as Greek letters or stray symbols; superscript affiliation numbers fuse with names.
- **Algorithm boxes** read as tables, with the pseudo-code's inline math garbled.
- **References** lose or alter digits in years, volumes and arXiv ids.

False alarms that are common in papers: verdict `ok`, saying which.

- Reference numbers printed with leading zeros (01–09) in the text layer.
- arXiv ids and DOIs broken across lines (`2107.` / `03134`).
- Superscripts fused to the word before them in the text layer: "Composera" for Composer + footnote a, "o11" for o1 + reference 1.
- Formulas the text layer garbles that the parse holds as LaTeX.
- Figure labels in a font the text layer encodes as a cipher ("horsh ydoxh" for "elope value").

A false alarm can sit next to a real misread in the same finding: `missing_numbers "2502 01"` held a split arXiv id and the "O1.AI" misread. Check every item of a finding.

## A caption style the conventions miss

The processing knows how papers write figure and table captions, panel letters and equation numbers (`scripts/ocrlib/conventions.py`); a paper that writes its captions another way (another word, another punctuation) gets the generic processing, complete but without figure numbers. Its captions get no figure number and its figures no `figure_check`, though the captions are plain to see. Say so in your report, with an example caption: once its pattern is in `conventions.py`, `ocr.py render` on the parse gives that paper and every later one its figure numbers and checks.
