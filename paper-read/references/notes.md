# Notes in use

What happens around a paper note once it exists: a project builds on it and records why, a correction changes it, topic notes tie papers together, and the library's older notes are folded in. Every change to a note goes through SKILL.md, *Every change to a note*.

## A project uses a paper

- **Check what you build on.** Before a fact from a note goes into a project's decision or a manuscript, compare it with the PDF and mark it in the note （已核对 <source> · <date>）, then put the note back. A fact already marked needs no second check.
- **Name papers by citation key.** A project's documents and index name a library paper by its Zotero citation key, so a search finds every mention. A manuscript's `\cite{…}` keeps the keys of its own `.bib`.
- **The project's own reasoning stays in the project**: what the paper means for the project, how it helps, implementation details. It lives in the project's documents, organized by topic as they already are, never in a file per paper. The index points at it.
- **A newer correction**: reading a note, a correction dated after a decision your project based on that fact sends you back to judge that decision again and rewrite its index line.

Done when every fact the project builds on is marked as checked in the note, and every decision has its line in the index.

## The project's paper index

One file per project: `research/paper-index.md`, or the project's own paper index if it has one. Chinese, since the user reads it when looking back. A heading per paper the project used, one line per decision under it:

```markdown
## xiaoTCACETimeConditionedAutoregressive2026 · T-CACE: A Time-Conditioned Autoregressive … Diagnosis（JBHI 2026）
- 没采用作 B-only 方案：方法的输入要有肿瘤 mask（论文笔记 Q3、Q6），本项目只有 B 超 · research/23_…/README.md · 2026-11-02
- 借鉴期相 token + 连续时间编码的双条件写法（论文笔记 Q3） · research/… · 2026-11-02
```

- **The heading** is `citation key · title · common names（venue year）`, printed by `uv run scripts/index_heading.py --cite <citation key>…` from the item's `aka/` and `venue/` tags; paste it as printed. A citation key it cannot resolve prints paper-to-zotero's own line instead: follow its `hint`. Most papers have no common name; one the field does call by a name but that prints without it is missing its `aka/` tag: add the tag by paper-to-zotero's references/tagging.md, *Common name*, and print again.
- **A line** is `decision: the point it rests on (论文笔记 Qn) · the document and section holding the reasoning · date`. A reason that fits in the line needs no document.
- Record what was used and what was weighed and turned down, each with its reason. When the project changes a decision, rewrite its line: git keeps the history.
- Write only your own project's index. Which projects used a paper: search their indexes for its citation key.

## Corrections

A correction is a change to a note like any other, with its correction mark. It may undercut decisions projects based on the old text:

- your own project's: judge them again now and rewrite their lines;
- other projects': leave them. Name in your report to the user the paper, the question and what changed; those projects see the date when they next read the note.

## Topic notes

A topic note gathers what several papers say on one topic. It is a standalone Zotero note, one per topic, in the collection 主题笔记, which holds topic notes only and which a tidy of the library leaves alone. It is related both ways to every paper it covers:

```markdown
---
collections: <key of 主题笔记>
related: <citation key>,<citation key>
---
# <the topic>
```

Its form is open; three things hold:

1. It is written around the questions the topic has to answer.
2. Every sentence names the paper note it comes from: citation key and Qn. A point no paper note holds yet goes into that paper's note first.
3. It holds the points; the sources and details stay in the paper notes.

## Older notes

A paper may carry notes from before this skill, the user's or earlier agents'. `prepare_note.py` takes them into `<scratch>/notes/` and leaves them in Zotero as they are.

- They are leads: what they say about the paper enters the paper note once found in the paper. Their structure, order and wording are no model.
- What they say about a manuscript or a project goes to that project: your own project's into its index or documents; another project's into your report to the user.
- After a read-through, ask the user whether to move them to the trash, in the run's one message of questions. The user's own notes and highlights are never touched.
