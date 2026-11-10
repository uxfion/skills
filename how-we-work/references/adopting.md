# Adopting these rules in a project

Read this when the user asks for a project to adopt how-we-work, and when `hww.py sync` exits 2 with `unclosed_block` or `several_blocks` in a project that should already have the block. A project adopts only on the user's word naming it; a project that does not carry the block is left as it is.

## What must hold

- **Every rule the project had is accounted for.** Its old rules sit in several places (an `AGENTS.md` or `CLAUDE.md`, convention documents, memory, a README). Each one ends in exactly one place, and the user sees the accounting before any old text goes:

  | The old rule | Where it goes |
  |---|---|
  | The common block or a reference now says it | Dropped from the project |
  | A fact of this project (its task, data, hosts, paths, dated cases) | A fact one kind of work needs: that kind's convention file, under `## This project only` (each reference says what its file holds). Hosts: the servers file. The rest: the project's `AGENTS.md`, outside the block, or the document that already holds such facts |
  | A rule for one kind of work that only this project needs | `docs/conventions/<kind>.md` under `## This project only`, with the reason it is this project's alone |
  | A rule that looks general and that the common rules do not have | `docs/conventions/<kind>.md` under `## To promote` (a rule for every task: the project's `AGENTS.md`, outside the block, marked the same way), and an issue in the skills repository, named at the entry's end as `(issue: <its file name>)` |
  | The user's global instructions, or one of their skills, already say it | Dropped from the project, with what says it named |
  | Overtaken by something the user said later | Dropped, with the later statement named in the accounting |

  The same sorting covers the project's convention documents and its memory entries. An entry that is partly covered is split: the covered part goes, the rest stays. Nothing is removed from the project's files or memory before the user's yes; after it, the agent doing the adoption removes what the accounting marked: what git tracks, in git; what it does not (memory entries, a rules file outside git), into `archive/<YYYYMMDD>/` with its line in `INDEX.md`, as the layout reference says.

  The accounting is a table of this shape, one row per old rule, kept in the project where its other records are (its issue or decision on adopting). "Weakened" is checked as well as "lost": a rule that survives in fewer words than it needs counts as changed.
- **The project differs where it says so.** Where the project keeps a practice that departs from the common block, its own text says which rule and why; the project's text wins.
- **Only the sync writes the block.** Place the marker pair, empty, where the block is to stand (usually after the file's title and its opening lines about the project), then run the sync:

  ```markdown
  <!-- how-we-work:begin -->
  <!-- how-we-work:end -->
  ```

- **Directories stay where they are.** The layout reference is the default for a new project. An existing project keeps its directories and file names until the user decides otherwise. Where its things are is said once each: every place the common block names (the to-do list, decisions, issues, specs, unattended runs, the direction, what others said, the servers file, the convention files), in its `AGENTS.md` outside the block, since the block is read in every session; everything else in its README's map, with the reason for each difference in `docs/conventions/layout.md`. Ask once whether new things take the default names from now on.
- **A project without a rules file**, whose rules sit in memory and in the openings of its documents, gets an `AGENTS.md` written from nothing: a title, two or three lines saying what the project is, the empty pair, then its own part. A rules file in a subdirectory is accounted for like the rest; whether it stays is the user's.
- **A harness-specific rules file** (a `CLAUDE.md` that holds the project's rules) is the user's to keep or to turn into `AGENTS.md`; ask.

The layout reference has the default map and what happens to a file that is replaced; the records reference has the convention file's two headings and the record files a project may lack (they are set up when first needed, not at adoption).

## What the user sees

Before anything in the project changes: the accounting, in brief (how many rules dropped as covered, how many kept as the project's own, how many to promote, and every row that is a judgement of yours and not an obvious match), and the project's `AGENTS.md` as it would read. After their yes: make the changes, run the sync, and say what was done. Done when: each row of the accounting names the place its rule now stands in, and that place holds it in words that still say all of it; a second `hww.py sync` prints `current`; each entry under `## To promote` ends in `(issue: …)` or `(judged …: stays)`; and one read of the project's `AGENTS.md` from its first line to its last finds no rule stated both inside the block and outside it, and no path the project does not have.

## Damaged markers

When the sync exits 2 with `unclosed_block` or `several_blocks` in an adopted project, look at the markers on the lines it names: one missing, a second pair, a marker quoted in the project's own text. Restore one pair around what is left of the block (the sync replaces everything between the two), reword a quoted marker so that it no longer matches, and run the sync again. Text that someone wrote inside the block by hand does not stop the sync: the next run replaces it without a word, so when you see such text, move it to the project's own part first. Say what you found.
