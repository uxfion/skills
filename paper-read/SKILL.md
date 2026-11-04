---
name: paper-read
description: Keeps one paper note per Zotero library paper — what the paper says, question by question, each fact with its source — and each project's paper index of the decisions it based on papers. Use when a task needs what a library paper says (查论文里怎么说的、精读、读论文), when the user wants a paper read or its note written (论文笔记), when a project decides something from a paper (论文索引), or when notes across papers are wanted (主题笔记).
---

# Paper read

Any task, in any project, that needs what a library paper says gets it fast from the paper's **paper note**, with sources to check it against the PDF, instead of reading the paper again. Two things hold this knowledge:

- **The paper note**, in Zotero under the paper's item: the paper alone, what it says and judgements about it (references/note-format.md). There is one per paper, and it grows and gets corrected as tasks use it. No note is final, and none is taken on trust for a decision.
- **The project's paper index**, in the project: one line per decision the project based on a paper, pointing at the note's question and the project's own reasoning (references/notes.md).

**The subject decides where a sentence goes.** About the paper → the note, whether or not a project needs it. About a project → that project.

| operation | where |
|---|---|
| Look something up in a paper | *Look it up* below |
| Read a paper through into its note | *Read a paper* below |
| How a note is written | [references/note-format.md](references/note-format.md) |
| A project uses a paper: checking, the paper index | [references/notes.md](references/notes.md), *A project uses a paper*, *The project's paper index* |
| Correct a note | references/notes.md, *Corrections* |
| A topic note across papers (主题笔记) | references/notes.md, *Topic notes* |
| The library's older notes | references/notes.md, *Older notes* |

Script paths are relative to this file's directory: `cd` there at the start of every shell call. paper-to-zotero runs as `uv run ../paper-to-zotero/scripts/p2z.py <command>`. Each script's `--help` is the reference for its output and codes.

**Zotero is the one home** of a paper's note and structured package. Take them out whenever a task needs them, into a **scratch directory**: a new subdirectory of the session's scratchpad (else of `${TMPDIR:-/tmp}`), one per change, never in a project. Delete it once Zotero holds the result and no question for the user still rests on it. A file that did not reach Zotero is the user's: hand it over with its full path.

**Language by reader.** Notes and indexes are the user's to read, in Chinese (note-format.md, *Language*). These instructions and what you tell a subagent are English.

## Every change to a note

A read-through, a looked-up answer written back, a check mark, a correction: each one changes the paper's one note, in four steps.

1. **Take**: `uv run scripts/prepare_note.py --cite <citation key> -o <scratch> [--bare] [--title <PDF title>]`. It gives the note file (a new one from the skeleton when the paper has none; `--bare` starts it without the eight questions), the PDF the note was read in (`--title` takes another, note-format.md, *读的版本*), the package, and the paper's other notes.
   - `no_package`: the PDF has not been parsed. Parse it with the paddleocr skill, `p2z.py structured put` the result, then run `prepare_note` again with the same arguments, into the same directory. Without paddleocr, read the PDF alone and tell the user the skill to install.
   - `two_notes`: the paper has two notes titled 论文笔记. Which to keep is the user's call.
   - `failed` with `no_such_title`: the PDF the note was read in is no longer in the library under that title. One of its `titles` that is the same file renamed: run again with `--title` it, and name it in the 读的版本 paragraph; nothing needs reading again. None: it goes to the user.
   - `failed` with any other code (a citation key that names no item, Zotero not running): `detail` holds paper-to-zotero's own line; follow its `hint`.
   - `better_pdf`: the library holds a better version than the one the note was read in (by the order `p2z.py read_library pdf --help` gives). A lookup reads on in the note's version; a read-through moves the note onto the better one (*Read a paper*).
2. **Edit** the note file by note-format.md, *Changing a note*.
3. **Check**: `uv run scripts/check_note.py <note>` (`--full` after a read-through) prints `complete`, and `uv run scripts/check_quotes.py <note> --pdf <PDF> --package <package>` (no package: without `--package`) prints `pass`. `missing_numbers` lists questions lost since the take: put them back.
4. **Put**: `p2z.py note put <note> -i`.
   - `version_conflict`: the note changed in Zotero meanwhile. Take it into a new scratch directory, carry this change over, check and put again. Taking into the old directory would overwrite the change.
   - `same_title`: another session created the paper's note meanwhile. Take that one, merge this change in, put again.

Done when both checks pass and `note put` answers `ok`, or `skipped` (Zotero already holds this note).

## Look it up

1. Take the note (`prepare_note.py … --bare`) and see whether it answers the question. If it does, that is your answer; a fact a decision or a manuscript will rest on is checked first (references/notes.md, *A project uses a paper*).
2. If not, or not enough: read the parts of the package that bear on it, by the paddleocr skill's *3. Read and report*, and check the numbers you use against the PDF. A spot still marked open or unresolved is checked against the PDF; settling the whole package is a read-through's work.
3. Write it back when it is about the paper, or when another project reading this paper would want it too. It goes under the question it belongs to, by *Every change to a note*. What only your project needs stays in your project; with nothing to write back, put nothing and delete the scratch directory.

Done when the answer rests on the note or the paper's text, and what belongs in the note is in Zotero.

## Read a paper

**Whether to read a paper through is yours to judge.** Read through a paper that matters to the project: one its decisions will lean on, or one close to its problem. A paper from a strong journal or conference weighs more. For the rest, look up what you need. Papers are read when a task needs them, never in bulk at import. A note `check_note --full` already finds `complete` is not read again: look up what it lacks. A better version in the library (`better_pdf`) is the exception: reading the paper through on it is how the note moves there.

1. **Take** (*Every change to a note*, step 1). `open_findings` in the output counts the package's unsettled spots: the reader settles them as it reads. With `better_pdf`, take again into a new scratch directory with `--title <better_pdf>`: `previous` then holds the version the note was read in, for the reader to compare; when it has no PDF or package, its `code` says why, and the reader moves the note without that comparison (reading.md, *Moving to another version*).
2. **Send the reader** (*Handoffs*). Several papers: one reader each, up to 5 at once.
3. **Check what comes back**, against the files:
   - the checks of *Every change to a note*, step 3, with `--full`;
   - a package that had open findings: `uv run ../paddleocr/scripts/doc.py show <package>` prints `no open findings`;
   - `git status` in the project shows nothing the reader left; remove what it did;
   - a move to a better version: `check_note` prints the new PDF as `version`, and the report's version section lists every difference between the two and what it became.

   What fails goes back to the same reader with the output as printed: Claude Code `SendMessage`. If it cannot be resumed, send a new reader with the same brief, the note file as it stands, that output and the first reader's reply.
4. **Save the reader's reply** as `<scratch>/report.md`, then act on it:
   - the PDF is not this paper: stop; it goes to the user;
   - a settled package: `p2z.py structured put <package>`;
   - a library error it names, such as a common name the paper goes by without its `aka/` tag: read the item, and if the error is real, fix it by paper-to-zotero's rules and list it in your report. Deleting or merging items waits for the user;
   - questions marked 要看别处: they stay open until the user asks;
   - answers to a project's questions: write back what *Look it up* step 3 says belongs in the note;
   - the reader could not finish: supply what it says is missing and send it back, or take it to the user.
5. **Check and put** (*Every change to a note*, steps 3 and 4): step 4 may have changed the note.
6. **Questions for the user** — two notes, a PDF that is not the paper, the paper's older notes to trash (references/notes.md, *Older notes*) — wait for the batch's end and go out in one message.

Done when *Every change to a note* is done with `check_note --full`, and every item of `report.md` is acted on or waits in the user's message.

## Handoffs

The scripts settle what is certain and stop where judgement starts; the table lists those stops and who takes them.

**The reader** is a background subagent on the session's own model (Claude Code: no `model`; Codex: its default), one per paper, up to 5 at once. It reads the paper, writes the note file and settles the package; Zotero is written only by you. Send it with:

```text
You are paper-read's reader. <paper-read> is <this skill's directory>. Your brief: <paper-read>/references/reading.md; the note format: <paper-read>/references/note-format.md. The paper: <title> · <first author> · <year> · <venue> · <DOI> · aka: <its aka/ names, or none>. Scratch: <scratch>. Note: <note>. PDF: <pdf>. Package: <package or none>. Older notes: <paths or none>.
[Open findings: <counts by code>. <paddleocr> is <the paddleocr skill's directory>: settle by <paddleocr>/references/settle.md and <paddleocr>/references/papers.md, with uv run <paddleocr>/scripts/doc.py.]
[Previous version: <its PDF title>; PDF <pdf>; package <package>. This read moves the note onto the PDF above.]
[A project's questions: <the bare questions, without the project's background>.]
```

| stop | taker | brief | what comes back, recorded by |
|---|---|---|---|
| a paper to read through (*Read a paper*, step 2) | the reader | references/reading.md | the note file, edited in place; the package, by `doc.py commit`; its report, in its reply, which you save as `report.md`. You put the note and the package into Zotero |
| `no_package` | you, with the paddleocr skill | paddleocr's SKILL.md | the parse, by `structured put`; then `prepare_note` again |
| a quotation `check_quotes` cannot find, outside a read-through | you | references/note-format.md, *Evidence* | the quotation compared with the page image, marked （已核对 …） |
| `two_notes`, a PDF that is not the paper, older notes to trash, deleting or merging items | the user, in the batch's one message | — | their answer, carried out by you |

## Sibling skills

Each is installed on its own, beside this one; look for its `SKILL.md` when the operation starts.

| operation | needs | missing → |
|---|---|---|
| every operation | paper-to-zotero (`../paper-to-zotero/`): takes the note, the package and the PDF out of Zotero and puts them back | stop; tell the user to install it |
| a PDF without a structured package; settling a package | paddleocr (`../paddleocr/`) | read the PDF alone; tell the user the skill to install |
| checking quotations | poppler's `pdftotext`, which `check_quotes.py` runs | `check_quotes` says `unreadable`: tell the user to install poppler; the note is put once the check passes |
| a paper not yet in the library | paper-to-zotero's import, which needs paper-fetch | import it first, as paper-to-zotero's own table says |
