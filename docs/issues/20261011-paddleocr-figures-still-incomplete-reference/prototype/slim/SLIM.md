# Slim second opinion: settings fixed before the first run (2026-10-19)

Question: can the second opinion keep only its core rules and still catch what only it catches?

- region_slim.py = frozen region.py (sha256 286305bd...) with every case-driven rule removed; the docstring lists
  what is kept and dropped. One added simplification: the three proximity cases for strong blocks become one
  (within 6 rows on both axes). Headings always stop growth (core rule as written in the report).
- Run once over all 115 graded papers, text-layer mode and no-layer mode. No change to the script after the run;
  any later variant is reported as post hoc.
- Measured with the same grades, severity overrides, signals (table, cut) and two-figure check as stage 4;
  only the second-opinion edge signal changes. Configuration: recommended (1 row + table + cut + two).
- Adopt the slim version if, in text-layer mode, it loses at most 2 of the 139 severe errors and sends at most
  120 good figures to the agent (frozen B: 139/139, 108). Otherwise report which dropped rules the misses need,
  without tuning on these grades.
