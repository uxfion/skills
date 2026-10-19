# Grading figure crops

A PDF parser cuts each figure of a paper out as an image (a "crop"). You check whether it cut the right area.

Each image you grade is one page of a paper, with:
- **red boxes**: every crop the parser cut on this page. Each box is drawn about 6 px outside the real crop edge, so a red line that just touches content is fine;
- **one blue box**: the figure caption to grade.

For the figure that the blue caption describes, decide whether the crops capture it correctly.

Some images show two pages side by side: the caption (blue) opens the right-hand page and its figure fills the left-hand page. Then the red boxes on the left-hand page are the figure's crops: grade them as if they were on the caption's page.

## What counts as the figure

The figure is everything laid out as part of it:
- all panels and panel letters;
- axis labels, legends and colour bars;
- titles and headings inside the figure area (for example "Step 1: ..." over a diagram);
- text boxes, prompt and example-text panels, and arrows.

These are not part of the figure:
- running body text and section headings;
- page headers and footers;
- tables that have their own "Table" caption;
- other figures.

The caption itself does not matter: inside or outside the box are both fine.

## Verdict (pick one)

- `ok`: one red box holds the whole figure and nothing substantial besides it. Extra white margin, a hairline of the page header, or the figure's own caption inside the box are fine; mention them in the note.
- `missing`: one red box covers most of the figure, but part of it lies outside every red box, or a red edge cuts through it.
- `extra`: the red box holding the figure also holds something that is not part of the figure, such as body-text lines, a section heading, a table, or part of another figure.
- `missing+extra`: both of the above.
- `split`: the figure is covered by two or more red boxes and none of them holds all of it. Two red boxes that each hold a whole, separate figure are not a split.
- `none`: no red box covers the figure, or a red box covers only a small part of it (under about a quarter).
- `nofig`: the blue box is not a figure caption whose figure is on this page. Examples: the figure sits on another page, the box is a list of captions, a body sentence that starts with "Figure", or a table caption.
- `unsure`: you cannot decide. Give the reason in the note.

## Size

Give a size for `missing`, `extra`, `missing+extra` and `split`:
- `small`: at most one line of text or a thin strip, such as one title line or a row of tick labels;
- `large`: more than that, such as a panel, a text box, several lines, or half the figure.

For other verdicts, write `-`.

## How to look

Check all four edges of the red box closely. Look for:
- a text line just above or below the box;
- a title cut in half;
- labels on the left or right that are cut off;
- a panel or text box standing apart from the rest of the figure.

Read the text just outside each edge and ask whether it belongs to the figure or to the page's running text. Judge every image on its own.

## Output

Write a TSV file to the path you were given:
- header: `id	verdict	size	note`;
- one row per image, in batch order;
- `note`: at most 15 words saying what is missing or extra, or `-`.

If an image fails to load, retry it once. If it fails again, write `unread` as its verdict.

When finished, reply with only `done N rows`.
