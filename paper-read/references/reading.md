# Reading a paper into its note

This brief is for paper-read's **reader**: one subagent reading one paper of the Zotero library into its paper note. Read through, the note answers the eight questions and the questions that grew from them, from the paper itself. Every later task that needs this paper reads your note instead of the paper. It trusts what you wrote and checks only what it builds on.

## Inputs

Your prompt names the paper, its note file (which you edit in place), its PDF, its package (the paddleocr skill's parse of that PDF) or none, and the scratch directory they sit in; and, when they apply, the older notes, the package's open findings, a previous version and a project's questions. Read note-format.md first: it says how a note is written.

Before anything else, check that the PDF is this paper: its first page against the title and first author given. A different year or venue is normal, since the preprint and the published version differ. A different paper: stop and report.

The package is the PDF's text, page by page, with its tables and formulas. The PDF is the authority wherever the package flags a spot:

- `<!-- open … -->`: never checked;
- `<!-- unresolved … -->`: known wrong;
- `unchecked_table`: a table without a text layer.

The note may hold answers already, someone else's work: change it by note-format.md, *Changing a note*.

Older notes are leads: a fact in one enters the note once you have found it in the paper. Their structure and wording are no model.

## Reading

- Read the whole paper first, figures, tables and appendix included.
- Answer one question at a time, and write the answer into the file before starting the next. Any answer may draw on any part of the paper.
- Grow the tree as you go. An answer raises questions about the paper ("the input includes a tumour mask" → "is the mask needed at test time too?"). One whose evidence is in the paper now is asked and answered now, under the question it belongs to. One that waits on a later answer is marked 等 Qn. Each is written when it arises.
- After each answer, look back: which questions it settled, which it raised, whether it overturns an earlier answer. If it does, set that answer back to 进行中 and correct it.
- The summaries come last (note-format.md). A fact they need that no answer holds means that answer is short: complete it.
- A project's questions are answered in your report, with sources, not in the note. Whatever they lead you to find about the paper itself goes into the note like any other answer.

**Settling the package.** When your prompt names open findings, settle them as you reach them in the reading. Follow settle.md §1–3 and record with `ocr.py commit`. You check those spots against the PDF anyway, and you know what the text is saying. Where settle.md and this brief differ, this brief wins: you write the note file as well as the package folder, and of settle.md's report only what *Report* below asks for goes into yours.

## Moving to another version

When your prompt names a previous version, the note was read in that PDF, and this read moves it onto the one given. A later version can add, change and remove content. Compare the two packages paragraph by paragraph (a diff of their Markdown) and deal with every difference:

- **added**: read and answered like the rest; it grows the tree;
- **changed**: corrected, with a correction mark that cites the new version;
- **removed**: the note's sentence stays, with the removal mark (note-format.md, *Marks*).

Every source in the note then points into the new PDF: check each against it. The 读的版本 paragraph names the new PDF. A previous version that comes without its package is compared through its PDF's text (`pdftotext`); one without a PDF leaves only the new version to check every answer against.

## Product

- The note file, edited in place.
- The package folder, settled through `ocr.py commit` (when it had open findings).

Write only these, plus any drafts of yours in the scratch directory. Putting the note and the package into Zotero is the main agent's work.

## Done when

1. The PDF's first page shows the title and first author given; otherwise you stopped and reported.
2. `pr.py check --full <note>` prints `complete`.
3. `pr.py quotes <note>` exits 0, each reported quotation settled by note-format.md, *Evidence*.
4. When your prompt named open findings: `ocr.py findings <package folder>` exits 0.
5. The self-review is done: each answer split into its claims, every claim checked against the paper, what was wrong corrected; 2–4 then hold again.
6. Your reply is the report (*Report*), with every project question answered and, after a move, every difference listed.

## Report

The main agent saves your reply and reads the rest from the files and the checks, so the report holds only the items below that have something to say:

- the PDF is not this paper;
- **package**: what settle.md's report lists under **open**, and each `unresolved` verdict; the main agent checks the rest with `ocr.py findings`;
- **library**: an error in the item's tags or fields: which, where, what it should be. A word the field uses for this paper that is not among its `aka/` names is one (`<paper-read>/../paper-to-zotero/references/tagging.md`, *Common name*). The main agent fixes it;
- **version** (a move): each difference between the two versions, and what it became in the note;
- **elsewhere**: the questions marked 要看别处, and where the answer would be;
- **project questions**: each answered, with sources;
- **self-review**: each correction, one line.

## Rules

- Do the work yourself: send no subagents.
- Leave git alone.
- On the web (the paper's code repository, say): work by hand, one request at a time, seconds apart on one site. A login or check only the user can pass: leave it as it is and report it, for the main agent to bring to the user. Any other bot check, a 403 or a 429 ends your work on that site: say so in the report.
- Cannot finish: say what you tried, what is settled and what is missing, and hand back.
