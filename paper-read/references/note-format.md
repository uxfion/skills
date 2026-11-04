# The paper note

What a paper note holds and how it is written. Read it before writing in a note, whether you read the paper through or add one answer.

A paper has one **paper note**: a child note of its item in Zotero whose first line is 论文笔记. It holds the paper alone: what the paper says, each fact with its **source** (where in the paper it is), and judgements about the paper, marked as judgements. A project never appears in it; what a project decided goes into that project's paper index (references/notes.md). A note is never finished or final: every task that reads the paper may add to it or correct it (*Changing a note*).

Outside Zotero the note is a Markdown file, `<scratch>/<package folder name>.note.md`, which `prepare_note.py` writes and `put_note.py` puts back into Zotero.

## The skeleton

A note started for a read-through, as `prepare_note.py` writes it:

```markdown
---
parent: <citation key>
---
# 论文笔记

[待答]

读的版本：<PDF title>

## Q1 这篇论文要解决什么问题，为什么重要？这是哪类论文？ [待答]

## Q2 之前的工作怎么做，缺在哪里？ [待答]

## Q3 论文如何解决这个问题？ [待答]

## Q4 创新点是什么？ [待答]

## Q5 做了哪些实验？ [待答]

## Q6 结论站得住吗？ [待答]

## Q7 有什么可以进一步探索的点？ [待答]

## Q8 总结一下论文的主要内容 [待答]
```

A note started for one looked-up answer (`--bare`) holds the title, the 读的版本 paragraph and that one question: no `[待答]` summary and no empty questions. The question is numbered under the trunk question (one of the eight) it belongs to, `### Q3.1`, without that trunk heading; a later read-through adds the trunk around it, and its number stays.

- **The summary**, the first paragraph under the title: one sentence on what the paper does. Written last, from the answers already there; read first.
- **读的版本**, the second paragraph: the title of the PDF the note was read in. Every page number in the note counts that PDF's pages from 1, as the package's `<!-- page N -->` does. A new note is read in the library's best PDF, and every later read uses the same one. When the library gains a better version, a read-through moves the note onto it (reading.md, *Moving to another version*).

## The eight questions

1. 这篇论文要解决什么问题，为什么重要？这是哪类论文？ The kind: a new method, a dataset, theory, an application study, or another.
2. 之前的工作怎么做，缺在哪里？ Note the works worth reading next.
3. 论文如何解决这个问题？ The intuition and the reasons; one concrete example walked from input through processing to output; the core formulas. Walk the method overview figure and say which passage of the text each module in it is.
4. 创新点是什么？ What the paper claims to contribute; what is new against the closest earlier work; whether it is new in concept or only in implementation or data.
5. 做了哪些实验？ Each experiment as what it asks → how → what came out. How the comparisons were set up: against whom and why, on what data and metrics, under the same settings or not. Then five fixed items, each opening with its bold word:
   - **数据和划分**
   - **对比方法**
   - **指标**
   - **主要数字**, with the table they come from
   - **代码和数据**: public or not

   Each table and figure that carries a main conclusion gets its own sub-question: what it asks → how it was obtained (data, settings, how many runs, error bars) → the numbers and what they show. Check the numbers against the PDF; a table the package marks `unchecked_table` always. Other tables and figures get one line: what they show, and which table they agree with.
6. 结论站得住吗？ Five fixed items, each opening with its bold word:
   - **证据和范围**: whether each claim has evidence, and whether its scope is overstated;
   - **提升从哪来**: the ablations; whether the baselines were tuned with the same care; more data or compute;
   - **统计**: how many runs, what the error bars are, whether the gaps exceed the noise;
   - **前后矛盾**: where the text and the tables or figures disagree;
   - **假设和局限**: those the paper states, and those it plainly should have.

   Then the domain checklist below, keeping the points that apply.
7. 有什么可以进一步探索的点？
8. 总结一下论文的主要内容 A descriptive summary the authors would agree with, built only from the answers above, with one sentence on why the paper matters.

A fixed item of Q5 or Q6 the paper says nothing about keeps its bold word, followed by 论文没有说明; one that does not apply says 不适用 and why. `check_note.py --full` checks that every bold word is there.

## The tree

The headings are the question tree, which Zotero's Better Notes outline shows as one.

- A question is a heading: its number, the question, its state in brackets: `## Q3 论文如何解决这个问题？ [已答]`. The trunk questions are `##`; a question one of them raises is `###` (`### Q3.1 推理时也要输入肿瘤 mask 吗？`); one level further is `####`. The answer is written under its heading.
- **States**: 待答 (not yet), 进行中 (being answered), 已答, 论文没有说明 (the paper does not say; never guessed), 要看别处 (the answer is outside the paper: the code, the supplement), 等 Qn (waits for another answer, asked again under it: `### Q3.2 对比方法也给了 mask 吗？ [等 Q5] → Q5.1`; once Q5.1 is answered, `[已答] → Q5.1`).
- A heading without a number is a section and has no state.
- A heading is plain text in Zotero: it shows no math, and TeX in it does not come back as a heading. Write a symbol there in Unicode (ŷᵢ, fθ) and the formula in the answer.
- A blank line before every block: Better Notes cuts its outline by them.
- **A question's number never changes** once written: a project's index points at it. A new question takes the next free number under its parent. A question that turns out to be wrongly asked keeps its number and heading; its answer says why it was wrong.
- Marks (below) go in the text, never in a heading.

## Evidence

- **The source** says where in the paper a fact is: a section, a figure, a table, an algorithm, an equation, with the page when it helps: (Sec. III-A), (Table III, p.11). An answer about the paper's whole idea, or a fact that cannot be pinned to one place, carries none.
- **A quotation** is the sentence an answer rests on, copied verbatim in English, one line, unbroken, with any double quotes inside it as they are and its source after it; then a line holding only `>`; then its Chinese rendering. Formulas as `$x_{NC}$`, with no space inside the dollars:

  ```markdown
  > "Given a non-contrast liver MRI scan $x_{NC}$ and its corresponding tumor mask $x_{TM}$, our model simultaneously synthesizes three clinically relevant phases" (Sec. III-A, p.3)
  >
  > 给定平扫肝脏 MRI 和对应的肿瘤 mask，模型同时合成临床上相关的三个时相
  ```

  `check_quotes.py` looks for every quotation in the PDF's text layer, then in the package. One it cannot find (a table cell, a figure label, a formula the text layer garbles) is compared with the page image, corrected if need be, and marked as checked.
- **An inference** is marked （推断）; knowledge from outside the paper （论文外）; what the paper does not say is written as 论文没有说明.
- **Judgements about the paper** (Q6, Q7) are written as judgements, with what they rest on. "Not stated" is a fact and is written plainly; "possibly unfair" is a judgement and says why. Falling short of SOTA, closed code and honestly stated limits are not failures in themselves.

**Marks**, in the text after the fact they concern:

- `（已核对 <source> · <date>）`: someone compared this fact with the PDF. One per fact, the latest only.
- `（更正 <date>：原写"…"，按 <evidence and its source> 改）`: what was there before a correction, and why it changed. It stays.
- `（<new PDF title> 删去了这段，原见 <previous PDF title> <source>）`: a later version dropped what this sentence rests on. It stays.

## Clickable figures and tables

When the note is put into Zotero, each figure and table it names in one of these forms becomes a link to a blue box on it in the PDF the note was read in, so a reader of the note sees it in one click. The links live in Zotero only: the note file you edit has none.

- Linked: `Fig. 9`, `Fig.9`, `Figure 9`, `Fig. 2(b)` (the link is `Fig. 2`), `Table III`, `Supplementary Fig. 3`, `Extended Data Table 1`.
- Not linked: `p.11`, `Sec. III-A`, `Eq. (3)`, `图 4`.

Of `Table I/II` only the first links: write each in full, `Table I, Table II`, for each to link.

## Changing a note

A note holds others' work, and a change keeps it:

- Read the whole note before changing it.
- Every change rests on the paper's text, with its source.
- What is there stays unless the paper proves it wrong; then a correction mark records what it was.
- Question numbers stay as written (*The tree*).

## Language

Chinese prose; terms, method and metric names and numbers stay in English; quotations stay in English with their Chinese line.

## Domain checklist

A starting point for Q6; add what else the paper calls for.

- **ML**: speculation presented as explanation; whether a theorem really supports the main claim; claims like "human-level".
- **Medical imaging**: how representative the cohort is; label quality; whether the split is by patient; statistical tests; the clinical setting; domain shift and pathological cases.
