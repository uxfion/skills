---
name: paper-read
description: Keeps one paper note per Zotero library paper — what the paper says, question by question, each fact with its source, and what it offers our work — and each project's paper index of the decisions it based on papers. Use when a task needs what a library paper says (查论文里怎么说的、精读、读论文) or what it offers a project (启发、借鉴), when the user wants a paper read or its note written (论文笔记), when a project decides something from a paper (论文索引), or when notes across papers are wanted (主题笔记).
---

# Paper read

Any task, in any project, that needs what a library paper says gets it fast from the paper's **paper note**, with sources to check it against the PDF, instead of reading the paper again. Two things hold this knowledge:

- **The paper note**, in Zotero under the paper's item, one per paper: what the paper says, judgements about it, and what it offers work like ours (Q9) (references/note-format.md).
- **The project's paper index**, in the project: one line per decision the project based on a paper, pointing at the note's question and the project's own reasoning (references/notes.md).

**The subject decides where a sentence goes.** About the paper, or what it offers work like ours → the note, whether or not a project needs it. A project's own choices and details → that project.

| operation | where |
|---|---|
| Look something up in a paper | *Look it up* below |
| Read a paper through into its note | *Read a paper* below |
| How a note is written | [references/note-format.md](references/note-format.md) |
| A project uses a paper: checking, the paper index | [references/notes.md](references/notes.md), *A project uses a paper*, *The project's paper index* |
| Correct a note | references/notes.md, *Corrections* |
| A topic note across papers (主题笔记) | references/notes.md, *Topic notes* |
| The library's older notes | references/notes.md, *Older notes* |

**Calling.** Start every shell call with this statement, filled in with this file's absolute directory, then the commands: `set -o pipefail; export PATH="<this directory>/scripts:<this directory>/../paper-to-zotero/scripts:<this directory>/../paddleocr/scripts:$PATH";` — `pr.py <word> …`, paper-to-zotero's `p2z.py` and paddleocr's `ocr.py` are then found from anywhere in the call, your working directory stays where it is, and a failure anywhere in a pipe sets the call's exit code. `pr.py -h` lists the words; `pr.py <word> -h` is each one's reference: what it reads, its options, its lines, its exit codes. stdout is data; stderr stays empty when everything is done, so keep it: on exit 2 its last line is `{code, hint}`, saying why nothing could go on (Zotero not running, say).

**Zotero is the one home** of a paper's note and structured package. Take them out whenever a task needs them, into a **scratch directory**: a new subdirectory of the session's scratchpad (else of `${TMPDIR:-/tmp}`), one per change, never in a project. Delete it once Zotero holds the result and no question for the user still rests on it. A file that did not reach Zotero is the user's: hand it over with its full path.

**Language by reader.** Notes and indexes are Chinese, for the user (note-format.md, *Language*); what you tell a subagent is English.

## Every change to a note

A read-through, a looked-up answer written back, a check mark, a correction: each one changes the paper's one note, in four steps.

1. **Take**: `pr.py take <citation key> -o <scratch>/`, which puts the note file, its PDF, the package and the paper's other notes there (`pr.py take -h`).
   - `no_such_title`: the PDF the note was read in is no longer in the library under that title. If one of its `titles` is the same file renamed, take again with `--title` that title and name it in the 读的版本 paragraph; nothing needs reading again. Otherwise it goes to the user.
   - any other code but `ok` (`no_package`, `two_notes`, or paper-to-zotero's own line, `step` naming its command): follow its `hint`.
   - `better_pdf`: the library holds a better version than the one the note was read in. A lookup reads on in the note's version, consulting the better one when the question needs it (*Additional sources*); a read-through moves the note onto it (*Read a paper*).
2. **Edit** the note file by note-format.md, *Changing a note*.
3. **Check**: `pr.py check <note>` (`--full` after a read-through) prints `complete`, and `pr.py quotes <note>` exits 0. `missing_numbers` lists questions lost since the take: put them back.
4. **Put**: `pr.py put <note>`, run by you alone, since it writes Zotero. Its `code` is note put's:
   - `version_conflict`, `same_title`: the paper's note changed, or was created, in Zotero meanwhile. Take it into a new scratch directory (a take into this one keeps the file there), carry this change over, check and put again.
   - any other code but `ok` and `skipped`: follow its `hint`.
   - `unmatched` lists the figures and tables left unlinked: look each one up in the PDF, then follow its `hint`.

Done when both checks pass, `pr.py put` answers `ok` or `skipped`, and every `unmatched` entry has been looked up.

## Look it up

1. Take the note (`pr.py take --bare …`) and see whether it answers the question. If it does, that is your answer; a fact a decision or a manuscript will rest on is checked first (references/notes.md, *A project uses a paper*).
2. If not, or not enough: read the parts of the package that bear on it, by the paddleocr skill's *3. Read and report*, and check against the PDF the numbers you use and any spot still marked open or unresolved; settling the whole package is a read-through's work. Follow other versions or supplementary material when the question calls for them (*Additional sources*).
3. Write back what is about the paper or what it offers work like ours (*The subject decides where a sentence goes*), under the question it belongs to, by *Every change to a note*. A note whose only gaps in `check --full` are Q9, Q3 **核心机制** and Q6 **更好的验证** gets the lines of those items this question needs. With nothing to write back, put nothing and delete the scratch directory.

Done when the answer rests on the note or the paper's text, and what belongs in the note is in Zotero.

## Additional sources

The primary PDF gives the default page numbers and automatic figure links. To answer a question, follow the paper's references to another version or supplement, and use other relevant attachments as needed. The reader does these lookups during a read-through; outside one, you do them. Follow references/reading.md, *Additional sources*, and cite each file by references/note-format.md, *Evidence*.

If a needed source is missing, you obtain it through paper-fetch and continue the lookup or resume the reader with the source and its original brief. Keep a question as 要看别处 only with the source still needed and what prevents checking it; material already in hand is used now. Any library write follows paper-to-zotero's authorization rules.

## Read a paper

**Whether to read a paper through is yours to judge.** Read through a paper that matters to the project: one its decisions will lean on, or one close to its problem. A paper from a strong journal or conference weighs more. For the rest, look up what you need. Papers are read when a task needs them, never in bulk at import. A note `pr.py check --full` already finds `complete` is not read again: look up what it lacks. Nor is a note whose only gaps in `check --full` are Q9, Q3 **核心机制** and Q6 **更好的验证**, a note from before Q9: a lookup fills the lines its question needs (*Look it up*, step 3), a read-through all of them. A better version in the library (`better_pdf`) is the exception: reading the paper through on it is how the note moves there.

1. **Take** (*Every change to a note*, step 1). With `better_pdf`, take again into a new scratch directory with `--title <better_pdf>`: `previous` then holds the version the note was read in, for the reader to compare (reading.md, *Moving to another version*).
2. **Send the reader** (*Handoffs*). A subagent running this flow is its own reader: it reads by references/reading.md, then goes on from step 3 with its own findings, and keeps what would be `report.md` in its reply.
3. **Check what comes back**, against the files:
   - the checks of *Every change to a note*, step 3, with `--full`;
   - a package that had open findings: `ocr.py findings <package>` exits 0;
   - `git status` in the project shows nothing the reader left; remove what it did;
   - a move to a better version: `pr.py check` prints the new PDF as `version`, and the report's version section lists every difference between the two and what it became.

   What fails goes back to the same reader with the output as printed: Claude Code `SendMessage`. If it cannot be resumed, send a new reader with the same brief, the note file as it stands, that output and the first reader's reply.
4. **Save the reader's reply** as `<scratch>/report.md`, then act on it:
   - the PDF is not this paper: stop; it goes to the user;
   - a settled package: `p2z.py package put <package>`, which trashes the package it replaces (a derived copy: no question for the user);
   - a library error it names, such as a common name the paper goes by without its `aka/` tag: read the item, and if the error is real, fix it by paper-to-zotero's rules and list it in your report. Deleting or merging items waits for the user;
   - questions marked 要看别处: check what source is missing and obtain it when needed for the task (*Additional sources*); resume the reader with what you obtain. Report what remains blocked;
   - the reader could not finish: supply what it says is missing and send it back, or take it to the user.
5. **Check and put** (*Every change to a note*, steps 3 and 4): step 4 may have changed the note.
6. **Questions for the user** (*Handoffs*, the user's row; older notes: references/notes.md, *Older notes*) wait for the batch's end and go out in one message. It names each paper read without the project's open problems: once the user names them, Q9 is filled against them (*Look it up*, step 3).

Done when *Every change to a note* is done with `pr.py check --full`, and every item of `report.md` is acted on or waits in the user's message.

## Handoffs

The scripts settle what is certain and stop where judgement starts; the table lists those stops and who takes them.

**The reader** is a background subagent on the session's own model (Claude Code: no `model`; Codex: its default), one per paper, up to 5 at once. Send it with every `<…>` filled in: each skill's directory as an absolute path, the rest from `pr.py take`'s line:

```text
You are paper-read's reader. <paper-read> is <this skill's directory>. Start every shell call with: `set -o pipefail; export PATH="<paper-read>/scripts:<paper-to-zotero>/scripts:<paddleocr>/scripts:$PATH";` Your brief: <paper-read>/references/reading.md; the note format: <paper-read>/references/note-format.md. The paper: <title> · <first author> · <year> · <venue> · <DOI> · aka: <its aka/ names, or none>. Scratch: <scratch>. Note: <note>. PDF: <input>. Package: <package or none>. Older notes: <old_notes or none>.
[Open findings: <open_findings>. <paddleocr> is <the paddleocr skill's directory>: settle by <paddleocr>/references/settle.md and <paddleocr>/references/papers.md, with ocr.py.]
[Previous version: <its PDF title>; PDF <previous.input>; package <previous.package>. This read moves the note onto the PDF above.]
Papers with notes: <citation key · title, one a line>. [Compare with: <the notes the open problems bear on>.]
[Our open problems (<project>): <each in one or two lines: the problem; why it stands; what is missing; what has been tried, or none; where it is stated>.]
[Important: <why: the project will rely on it, reproduce it, or compare against it>. Look for later work.]
```

- **Papers with notes**: `p2z.py search --all-fields 论文笔记 | jq -r '"\(.citationKey) · \(.title)"'`.
- **Open problems** are the ones blocking the project now, quoted as the project's records or the task at hand state them (what the user said, the results in view), each naming where it is stated. What has been tried lets Q9 build on it. A part the source leaves unsaid reads "not stated"; "none" means the source says nothing was tried. With no source, leave the line out: Q9 rests on the paper alone.
- **Important** sends the reader to the web for later work, so one important reader runs at a time: readers in parallel would query the same citation services as one person.

| stop | taker | brief | what comes back, recorded by |
|---|---|---|---|
| a paper to read through (*Read a paper*, step 2) | the reader | references/reading.md | the note file, edited in place; the package, by `ocr.py commit`; its report, in its reply, which you save as `report.md`. You put the note and the package into Zotero |
| `no_package` | you, with the paddleocr skill | the line's `hint`; paddleocr's SKILL.md | the parse, by `p2z.py package put`; then `pr.py take` again |
| a quotation `pr.py quotes` cannot find, outside a read-through | you | references/note-format.md, *Evidence* | the quotation compared with the page image, marked （已核对 …） |
| `two_notes`, `no_such_title` with no renamed file, a PDF that is not the paper, older notes to trash, deleting or merging items | the user, in the batch's one message | — | their answer, carried out by you |

## Sibling skills

Each is installed on its own, beside this one; look for its `SKILL.md` when the operation starts.

| operation | needs | missing → |
|---|---|---|
| every operation | paper-to-zotero (`../paper-to-zotero/`): takes the note, the package and the PDF out of Zotero and puts them back | stop; tell the user to install it |
| a PDF without a structured package; settling a package; links to figures and tables | paddleocr (`../paddleocr/`) | read the PDF alone; figures and tables go unlinked; tell the user the skill to install |
| checking quotations | poppler's `pdftotext`, which `pr.py quotes` runs | it stops with `no_pdftotext`: tell the user to install poppler; the note is put once the check passes |
| a paper not yet in the library | paper-to-zotero's import, which needs paper-fetch | import it first, as paper-to-zotero's own table says |
