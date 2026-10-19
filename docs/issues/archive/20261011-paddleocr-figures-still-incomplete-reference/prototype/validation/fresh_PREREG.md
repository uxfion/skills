# Fresh batch for the implemented figure check: fixed before parsing and grading (2026-10-19)

- Code: paddleocr at commit 1d15f2d (figcheck.py and parse.py checksums in prereg.sha256). No change to
  the checks, thresholds or second opinion until this batch is graded and counted.
- Papers: 24 unused papers from the research corpus (chosen.tsv, seed 20261019, stratified by venue guess), parsed fresh;
  4 of them also as page images rendered at 150 dpi (no text layer: the scan path).
- Grading: as stage 4. One page image per figure caption with the current crops (red) and the caption (blue), no
  warnings shown, ids shuffled, GRADER.md, two hidden controls per batch; captions whose figure sits on the page before
  are graded on that page. I audit a random sample of the passed figures.
- Severity: SEVERE.md (same file as stage 4, severe.sha256).
- Bar: every severe error reported. Each miss is looked at, logged in the issue, and then either a general check or a
  stated limit. Also reported: minor errors reported, good figures passed, how two_figures, the cross-page split and
  second-opinion rules 7-8 fired.
