# Reading a paper into its note

This brief is for paper-read's **reader**: one subagent reading one paper of the Zotero library into its paper note. Read through, the note answers the nine questions and the questions that grew from them: Q1–Q8 from the paper itself, Q9 from the paper and, when your prompt names them, against our open problems. Every later task that needs this paper reads your note instead of the paper. It trusts what you wrote and checks only what it builds on.

## Inputs

Your prompt names the paper, its note file (which you edit in place), its primary PDF, its package (the paddleocr skill's parse of that PDF) or none, and the scratch directory they sit in; the library's papers that have notes; and, when they apply, the older notes, the package's open findings, a previous version, our open problems, whether the paper is important to a project, and notes to compare with. Read note-format.md first: it says how a note is written and how other sources are cited.

Before anything else, check that the PDF is this paper: its first page against the title and first author given. A different year or venue is normal, since the preprint and the published version differ. A different paper: stop and report.

The package is the PDF's text, page by page, with its tables and formulas. The PDF is the authority wherever the package flags a spot:

- `<!-- open … -->`: never checked;
- `<!-- unresolved … -->`: known wrong;
- `unchecked_table`: a table without a text layer.

The note may hold answers already, someone else's work: change it by note-format.md, *Changing a note*.

Older notes are leads: a fact in one enters the note once you have found it in the paper. Their structure and wording are no model.

## Reading

- Read the whole paper first, figures, tables and appendix included.
- Follow another version or supplementary material when the paper points there or a question needs it. The primary PDF sets the default source, not the reading boundary. Look up the relevant parts, by *Additional sources* below, and write each answer with its own source by note-format.md, *Evidence*.
- Answer one question at a time, and write the answer into the file before starting the next. Any answer may draw on any part of the paper.
- Grow the tree as you go. An answer raises questions about the paper ("the input includes a tumour mask" → "is the mask needed at test time too?"). One whose evidence is in the paper now is asked and answered now, under the question it belongs to. One that waits on a later answer is marked 等 Qn. Each is written when it arises.
- After each answer, look back: which questions it settled, which it raised, whether it overturns an earlier answer. If it does, set that answer back to 进行中 and correct it.
- The order is Q1–Q8, then Q9, then the one-sentence summary (note-format.md). A fact Q8 or the summary needs that no answer holds means that answer is short: complete it.
- Our open problems, when your prompt names them, are what Q9 is read against besides the paper itself. What they lead you to find about the paper itself goes into the note like any other answer.

**Reading deep.** This method is yours; the note gets what it finds, where note-format.md puts it.

- **Sceptical by default.** A claim holds when its evidence does; language-model reviewers lean positive.
- **Re-implement before Q6.** Walk the method step by step as the authors had to build it. The settings the paper leaves unsaid go under the question they belong to, as 论文没有说明; where the method would fail goes into Q6 **假设和局限**.
- **Code on demand.** Look at the paper's code when the brief marks the paper important, or when a key setting is missing from the paper. The note names the repository, the commit or date, and what differs from the paper, marked （论文外）.
- **Later work.** When the brief marks the paper important, find a few later papers that directly test, reproduce, contradict or improve it. Q6 **证据和范围** says whether its conclusions were overturned or revised, marked （论文外）, with the date and the sources searched.
- **Q9 from this paper first.** After Q8, start from this paper's core mechanism, its assumptions, where it would fail and what it left unexplored. Links come from the brief's papers with notes: those this paper cites, and those the brief names. When a relation rests on a linked note, read it: `p2z.py note take <citation key> -o <scratch>/linked/` takes out all of that paper's notes, and its paper note is the one whose first line is 论文笔记.
- **Brainstorm.** Diverge first, before looking at other notes' ideas: do the opposite, take an analogy from another field, go deep into one component, generalise, move to another setting. Then converge on the ideas that change something and carry a test; applying the method unchanged is not an idea. Last, set them beside the linked notes' ideas. The note gets the kept ideas and 没展开的想法 in note-format.md's form. "No bearing on our open problems" and "nothing worth keeping" are answers.

**Settling the package.** When your prompt names open findings, settle them as you reach them in the reading. Follow settle.md §1–3 and record with `ocr.py commit`. You check those spots against the PDF anyway, and you know what the text is saying. Where settle.md and this brief differ, this brief wins: you write the note file as well as the package folder, and of settle.md's report only what *Report* below asks for goes into yours.

## Additional sources

Use `p2z.py pdf <paper>` to list the item's PDFs and their attachment keys. Take the one needed with `p2z.py package take <paper> --title "<attachment title>" -o <scratch>/sources/`; its line names the PDF and package. With no package, read the PDF directly. Other supplementary formats are listed by `p2z.py children <paper>`: use a reader appropriate to the file. Check that the material is the referenced version or supplement. A missing source goes back to the main agent with the exact reference and the question it blocks, so it can be obtained and your reading resumed.

Keep the note's primary PDF while consulting other sources; `pr.py take --title` is for adopting another primary version. Cite the actual file for every added fact, and check quotations against that file. Other attachments' figure and table names use explicit page links, as note-format.md describes. When versions disagree, say which says what and whether it applies to the question. A direction to another document is a lead to check, not evidence of the answer.

## Moving to another version

When your prompt names a previous version, the note was read in that PDF, and this read moves it onto the one given. A later version can add, change and remove content. Deal with what differs between the two versions, and only that; your prompt says what the main agent found:

- **added**: read and answered like the rest; it grows the tree;
- **changed**: corrected, with a correction mark that cites the new version;
- **removed**: the note's sentence stays, with the removal mark (note-format.md, *Marks*).

A difference that touches a number, a table or a figure the note uses is checked in the new PDF. Gaps the note already had (a question not yet answered, package findings outside the changed parts) wait for a read-through, unless your prompt asks for one; the done-when then holds with `pr.py check` in place of `--full`.

Check the facts that used the old primary PDF against the new one and update their sources. Facts explicitly citing another attachment keep that source; check whether the version move changes their applicability. The 读的版本 paragraph names the new primary PDF. Without the previous PDF, report what cannot be compared rather than treating every answer as verified.

## Product

- The note file, edited in place.
- The package folder, settled through `ocr.py commit` (when it had open findings).

Write only these, plus any drafts of yours in the scratch directory. Putting the note and the package into Zotero is the main agent's work.

## Done when

1. The PDF's first page shows the title and first author given; otherwise you stopped and reported.
2. `pr.py check --full <note>` prints `complete`.
3. `pr.py quotes <note>` exits 0, each reported quotation settled by note-format.md, *Evidence*.
4. When your prompt named open findings: `ocr.py findings <package folder>` exits 0.
5. The self-review is done: each answer split into its claims, every claim checked against its cited source, what was wrong corrected; other-version and supplement facts name their own file and location; 2–4 then hold again.
6. Your reply is the report (*Report*), after a move with every difference listed.

## Report

The main agent saves your reply and reads the rest from the files and the checks, so the report holds only the items below that have something to say:

- the PDF is not this paper;
- **package**: what settle.md's report lists under **open**, and each `unresolved` verdict; the main agent checks the rest with `ocr.py findings`;
- **library**: an error in the item's tags or fields: which, where, what it should be. A word the field uses for this paper that is not among its `aka/` names is one (`<paper-read>/../paper-to-zotero/references/tagging.md`, *Common name*). The main agent fixes it;
- **version** (a move): each difference between the two versions, and what it became in the note;
- **elsewhere**: questions still marked 要看别处, the exact source needed, and why it could not be consulted; an available version or supplement needed for an answer has been checked;
- **open problems**: which ones Q9 bears on, and what a source elsewhere would still settle;
- **self-review**: each correction, one line.

## Rules

- Do the work yourself: send no subagents.
- Leave git alone.
- On the web (the paper's code repository, say): work by hand, one request at a time, seconds apart on one site. Three tries at most for any one thing — a request, a search, a click — seconds apart; after the third, leave that site and say in the report what you could not get. The count is another where the user or your dispatch names one, and a step that waits by design (a gate's wait, a download arriving) is no retry. A login or check only the user can pass: leave it as it is and report it, for the main agent to bring to the user. Any other bot check, a 403 or a 429 ends your work on that site: say so in the report.
- Cannot finish: say what you tried, what is settled and what is missing, and hand back.
