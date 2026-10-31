---
name: paper-read
description: Reads papers in the Zotero library into their paper notes — a tree of questions answered from the PDF and its structured package, one note per paper — and keeps those notes, where a paper is used, topic notes across papers, corrections. Use when a task needs what a library paper says (查论文里怎么说的、精读、读论文), when the user wants a paper read or its note written (论文笔记), when a project records using a paper, or when notes across papers are wanted (主题笔记).
---

# Paper read

From a paper in the Zotero library to its **paper note**: what the paper says, answered question by question from its own text, kept as one note under the paper's item so that every later task and project reads it instead of the paper. Storing is paper-to-zotero's (`note take/put`, `structured take/put`); parsing a PDF is the paddleocr skill's; a paper not yet in the library is imported first (paper-to-zotero), since a note's home is its item. Script paths are relative to this file's directory; the sibling skills run as `uv run ../paper-to-zotero/scripts/p2z.py <command>` — `cd` here at the start of every shell call.

| operation | where |
|---|---|
| Look something up in a paper | *Look it up* below |
| Read a paper through into its note | *Read a paper* below, then [references/reading.md](references/reading.md) |
| Record that a project uses a paper (用在哪里) | [references/notes.md](references/notes.md), *Used in* |
| A topic note across papers (主题笔记) | references/notes.md, *Topic notes* |
| Correct or extend a note | references/notes.md, *Corrections* |
| The library's older notes | references/notes.md, *The library's older notes* (待定) |

**The subject decides where a sentence goes.** A sentence about the paper — what it says, what that implies, what it could be used for, what direction it suggests — goes into the paper note, whether or not any project needs it. A sentence about a project — what it decided, measured or changed — goes into the project, pointing at the note (citation key, which question, the page). One home per piece of knowledge: elsewhere it is pointed at, never copied.

**Language by reader.** A note is the user's to read: Chinese prose, with terms, method and metric names and numbers kept in English; a quoted sentence verbatim in English with a Chinese line under it. These instructions, and what you tell a subagent, are English.

**Files** live in the scratch directory (`<scratch>`: the session's scratchpad, else `${TMPDIR:-/tmp}`), never in a project: a paper's package unzips to `<scratch>/<cite>.<title>/` and its note file sits beside it, `<scratch>/<cite>.<title>.note.md`. They go once the note is in Zotero.

Before the first operation: `../paper-to-zotero/SKILL.md` must be there (and `../paddleocr/SKILL.md` when a package is missing); no such file → stop and tell the user which skill to install.

## Look it up

1. The paper's note first: `uv run ../paper-to-zotero/scripts/p2z.py note take --cite <citation key> --title 论文笔记 -o <scratch>/`. What it answers, from the paper's text with its page, is your answer.
2. Not there, or not enough: the paper's package (`p2z.py structured take --cite <citation key> -o <scratch>`, paper-to-zotero's *Reading a library paper*), read by the paddleocr skill's steps 2 and 3; every number you cite checked against the PDF, the authority.
3. What you learned that is about the paper goes back into its note as a question under the one it belongs to (references/reading.md, *The tree*), then `p2z.py note put` it; no note yet → the paper's note starts with this question (*Read a paper* writes the rest later).

Done when your answer rests on the note or the paper's text with its pages, and what you added is in the note.

## Read a paper

1. **Take the files.** `p2z.py structured take --cite <citation key> -o <scratch>` gives the package and the PDF (`package: null` → the paddleocr skill parses it, then `structured put`). The paper's note, if it has one: `p2z.py note take --cite <citation key> --title 论文笔记 -o <scratch>/`, renamed to `<scratch>/<cite>.<title>.note.md` — a paper has one note, which this read continues. Otherwise the note file starts from the skeleton in references/reading.md, with the front matter `parent: <citation key>`.
2. **Check the paper.** The PDF's title and the citation key name the same paper; else stop and say so.
3. **Send the reader**: one subagent on the strongest model (Claude Code: `model: "opus"`), briefed per references/reading.md with the paths of the PDF, the package and the note file, and the questions a project brought, as bare questions without the project's background. It reads the whole paper first, then answers the questions in order, writing each answer into the note file before the next.
4. **Check it is read through:** `uv run scripts/check_note.py <note file>` — `open` lists the nodes still 待答, 进行中 or 等 Qn and whether the one-sentence summary is written; send them back to the same reader.
5. **Store it:** `p2z.py note put <note file> -i`. A `version_conflict` means the note changed in Zotero meanwhile: take it again and carry the new answers over.

Done when `check_note` says `complete` and `note put` has written the note (`ok`, or `unchanged`).
