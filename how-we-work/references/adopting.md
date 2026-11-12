# Adopting these rules in a project

Read this when the user asks for a project to adopt how-we-work, and when `hww.py sync` exits 2 with `unclosed_block` or `several_blocks` in a project that should already have the block. A project adopts only on the user's word naming it; a project that does not carry the block is left as it is.

The project's own session carries the adoption out. How much there is to do follows from the project's state:

| The project | What adoption is |
|---|---|
| New: no rules of its own yet, little or nothing built | *A new project*: the block goes in, and that is all |
| Under way: it has rules, records and a layout of its own | *A project under way*: its old rules are sorted, the user sees the result, the block goes in; a move the user has decided follows in the same go |
| Under way, and it cannot stop for that: its history, memory or rules are heavy, or urgent work is waiting | *Adopting first, sorting later*: the block goes in at once, the old is sorted piece by piece |

## A new project

Write `AGENTS.md`: a title, two or three lines saying what the project is, the marker pair (*Only the sync writes the block*, below), then run the sync. Its directories and records follow the layout reference's default map, each set up when first needed. Done when a second `hww.py sync` prints `current`.

## A project under way

Read `common.md` and every reference first: each of the project's old rules is judged against them.

### What must hold

- **Every rule the project had is accounted for.** Its old rules sit in several places (an `AGENTS.md` or `CLAUDE.md`, convention documents, memory, a README). Each one ends in exactly one place, and the user sees the accounting before any old text goes:

  | The old rule | Where it goes |
  |---|---|
  | The common block or a reference now says it | Dropped from the project |
  | A fact of this project (its task, data, hosts, paths, dated cases) | A fact one kind of work needs: that kind's convention file, under `## This project only` (each reference says what its file holds). Hosts: the servers file. The rest: the project's `AGENTS.md`, outside the block, or the document that already holds such facts |
  | A rule for one kind of work that only this project needs | `docs/conventions/<kind>.md` under `## This project only`, with the reason it is this project's alone |
  | A rule that looks general and that the common rules do not have | `docs/conventions/<kind>.md` under `## To promote` (a rule for every task: the project's `AGENTS.md`, outside the block, marked the same way), and an issue in the skills repository, named at the entry's end as `(issue: <its file name>)` |
  | The user's global instructions, or one of their skills, already say it | Dropped from the project, with what says it named |
  | Overtaken by something the user said later | Dropped, with the later statement named in the accounting |

  The same sorting covers the project's convention documents and its memory entries. An entry that is partly covered is split: the covered part goes, the rest stays. Nothing is removed from the project's files or memory before the user's yes; after it, the agent removes what the accounting marked: what git tracks, in git; what it does not (memory entries, a rules file outside git), into `archive/<YYYYMMDD>/` with its line in `INDEX.md`, as the layout reference says.

  The accounting is a table of this shape, one row per old rule, kept in the project where its other records are (its issue or decision on adopting). "Weakened" is checked as well as "lost": a rule that survives in fewer words than it needs counts as changed.
- **The project differs where it says so.** Where the project keeps a practice that departs from the common block, its own text says which rule and why; the project's text wins.
- **Only the sync writes the block.** Place the marker pair, empty, where the block is to stand (usually after the file's title and its opening lines about the project), then run the sync:

  ```markdown
  <!-- how-we-work:begin -->
  <!-- how-we-work:end -->
  ```

- **Directories stay where they are.** The layout reference is the default for a new project. An existing project keeps its directories and file names until the user decides otherwise. Where its things are is said once each: every place the common block names (the to-do list, decisions, issues, specs, unattended runs, the direction, what others said, the servers file, the convention files), in its `AGENTS.md` outside the block, since the block is read in every session; everything else in its README's map, with the reason for each difference in `docs/conventions/layout.md`. Ask once whether new things take the default names from now on.
- **A project without a rules file**, whose rules sit in memory and in the openings of its documents, gets an `AGENTS.md` as a new project does, then its own part. A rules file in a subdirectory is accounted for like the rest; whether it stays is the user's.
- **A harness-specific rules file** (a `CLAUDE.md` that holds the project's rules) is the user's to keep or to turn into `AGENTS.md`; ask.

The layout reference has the default map and what happens to a file that is replaced; the records reference has the convention file's two headings and the record files a project may lack (they are set up when first needed, not at adoption).

### What the user sees

Before anything in the project changes: the accounting, in brief (how many rules dropped as covered, how many kept as the project's own, how many to promote, and every row that is a judgement of yours and not an obvious match), and the project's `AGENTS.md` as it would read. After their yes: make the changes, run the sync, check (*Acceptance*, below), and say what was done.

### With a move

A move of documents or directories happens when the user has decided one, on a map of before and after (the layout reference has how a map changes). It comes after the rules: they go in first, so that everything from that commit on is done by them, the move included. What holds for it:

- **Git is the way back.** Start from a committed tree, the project's pending work committed first as its own commit; one commit closes the rules, one the move.
- **What runs keeps running.** Before the move, search for what code, configs and reports read by path; after it, the project's tests and entry points run as they did before, and a search for the old paths finds only history. What a running job or another session in the project reads stays put until that job is over.
- **History stays as written.** A document that is no longer current gets its dated line at the top (the records reference) and keeps its content and its place.

### Adopting first, sorting later

A few projects cannot stop for the sorting. There the block goes in at once: the marker pair, the sync, and one line above the project's old rules saying that they are not yet sorted and that, where they and the block disagree, the block holds for new work. From that commit on new work follows the block and new files take the default places. The old rules, memory and layout are then sorted piece by piece as the work allows, each piece as above (its accounting, the user's yes, the removal), with what remains as a row of the to-do list. *Acceptance* comes when that row closes.

## Prepared in the skills repository first

For a project under way the user usually has the adoption prepared in a session of the skills repository, then starts the project's session from what it left. That repository is where these rules were designed: its session has the thinking behind them (the design principles, why each rule is there), which a project's session lacks. So the preparing session contributes what takes that thinking, and the project's session what takes the project in front of it. The preparing session reads the project and writes nothing into it. It delivers two things, sized to the project:

- **The decisions that shape the result, settled with the user**, each shown as the result it leads to: for a move, the map before and after.
- **One short entry file** for the project's agent: the goal, those decisions with the user's words, the calls that turn on a principle (how a kind of the project's old rules is to be judged, where the result should depart from the default and why), and the traps that agent would not find by itself.

The rest is the project session's, done better on the spot: the accounting row by row, the paths and links a move touches, the questions that only one step needs, asked when the work reaches it. The preparing session looks at the project as far as its two products need, and a finding enters the entry file when the project's agent would go wrong without it.

## Acceptance

The agent that adopted checks the result before it reports, by looking and running, with these as the points:

- Each row of the accounting names the place its rule now stands in, and that place holds it in words that still say all of it.
- A second `hww.py sync` prints `current`; each entry under `## To promote` ends in `(issue: …)` or `(judged …: stays)`.
- One read of the project's `AGENTS.md` from its first line to its last finds no rule stated both inside the block and outside it, and no path the project does not have.
- The project's training servers are in its servers file, as the user now names them.
- After a move: *What runs keeps running*.

Then the user gets a brief: what changed, where the project's things now are, what waits for them. When the user has a second session check the adoption, that session reads only, and checks these same points.

## Damaged markers

When the sync exits 2 with `unclosed_block` or `several_blocks` in an adopted project, look at the markers on the lines it names: one missing, a second pair, a marker quoted in the project's own text. Restore one pair around what is left of the block (the sync replaces everything between the two), reword a quoted marker so that it no longer matches, and run the sync again. Text that someone wrote inside the block by hand does not stop the sync: the next run replaces it without a word, so when you see such text, move it to the project's own part first. Say what you found.
