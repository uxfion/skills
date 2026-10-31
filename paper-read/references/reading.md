# Reading a paper into its note

What the reader — the subagent *Read a paper* sends — is told, and what its note looks like. Brief it with this file whole, the paths of the PDF, the package and the note file, and any questions a project brought (bare questions, no project background). It has only the paper, so what it writes is the paper's alone.

The method is a first version, still being designed (the paper-notes design, decisions 19–29, kept with the skills' sources). 待定 there: the question list itself, whether every paper gets a note when first read or the library in a batch, how answers are checked against the PDF, and how a note is regenerated without losing its added questions and *用在哪里*.

## The note

One Markdown file, `<scratch>/<cite>.<title>.note.md`, written as the reading goes and handed back as it is: in Zotero it is the note. A new one starts as:

```markdown
---
parent: <citation key>
---
# 论文笔记

[待答]

## Q1 这篇论文试图解决什么问题？ [待答]

## Q2 有哪些相关研究？ [待答]

## Q3 论文如何解决这个问题？ [待答]

## Q4 论文做了哪些实验？ [待答]

## Q5 有什么可以进一步探索的点？ [待答]

## Q6 总结一下论文的主要内容 [待答]

## 用在哪里
```

The paragraph under the title is the **one-sentence summary**: asked last, since it rests on every answer, and shown first, since it is what a later reader reads first. *用在哪里* belongs to the projects (references/notes.md); the reader leaves it as it is.

## The tree

The note's headings are the question tree: one place for the tree, the answers and their states, which Zotero's Better Notes outline shows as a tree.
- A question is a heading: number, question, state — `## Q3 论文如何解决这个问题？ [已答]`; its answer is written under it. The six trunk questions are `##`, a question one of them raises `###` (`### Q3.1 推理时也要真值 mask 吗？`), one level further `####`.
- **States**, in these words: 待答 (not yet), 进行中 (being answered), 已答, 论文没有说明 (the paper does not say: written as such, never guessed), 要看别处 (the code, the supplement — these are the open questions; no separate list), 等 Qn (waits for another answer: `### Q3.2 对比方法也给了 mask 吗？ [等 Q4] → Q4.1`, asked again as Q4.1 under that answer).
- A blank line before every block (Better Notes cuts its outline by them).
- A formula in a heading stays as TeX text (Zotero's headings hold no math): keep formulas in the answers.

## How to read

1. Check the paper: the PDF's title is the one in the brief. Then read the whole paper — every question may use any part of it, the figures, tables and appendix included. Where the package and the PDF differ, the PDF is right.
2. Answer the trunk in order, Q1 to Q6, one at a time: before each, list the headings — that is the tree — and take the next question that can be answered now. Write the answer into the file and set its state before starting the next.
3. **Grow the tree as you go.** An answer raises questions about the paper ("the input includes a tumour mask" → "is the true mask needed at inference too?"): one whose evidence is in the paper now is asked now, under the question it belongs to; one that depends on an answer still open waits there (等 Qn). Nothing is listed ahead of time.
4. **After each answer, look back**: which questions it settled, which it raised, and whether it overturns an earlier answer — then set that one back to 进行中 and correct it.
5. A project's questions go under the trunk question they belong to, like your own.
6. **Last, the summaries.** Q6 and the one-sentence summary come only from the answers already written: a fact they need that no answer holds means that answer is short — go back and complete it.
7. Then reread any part and correct what you wrote.

An answer is **done** when someone who has not read the paper could use it without asking anything: every fact carries the version and page it comes from, a sentence the answer rests on is quoted verbatim with a Chinese line under it, an inference is marked as one, and what the paper does not say is written as 论文没有说明. No first person, and nothing about any project. Chinese prose, terms, names and numbers in English.

Hand the file back when no heading is 待答, 进行中 or 等 Qn and the summary is written (`check_note.py` says `complete`).
