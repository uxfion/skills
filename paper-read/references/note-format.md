# The paper note

Read all of it before writing in a note, whether you read the paper through or add one answer.

A paper has one **paper note**: a child note of its item in Zotero whose first line is 论文笔记. It holds what the paper says, each fact with its source (*Evidence*); judgements about the paper, marked as judgements; and, in Q9, what the paper offers work like ours, which any project can use. What a project decided, and what serves one project only (its trade-offs, implementation details), goes to that project (references/notes.md). Every task that reads the paper may add to the note or correct it (*Changing a note*).

The note records results (what the paper says, what you judged, what you found) and keeps what the search turned up, whatever its length: ideas not taken further and why, leads ruled out and why, the sources searched and when.

## The skeleton

A note started for a read-through, as `pr.py take` writes it:

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

## Q9 有什么启发？ [待答]
```

A note started for one looked-up answer (`--bare`) holds the title and the 读的版本 paragraph; you add that one question, numbered under the trunk question (one of the nine) it belongs to, `### Q3.1`, without that trunk heading. A later read-through adds the trunk around it, and its number stays.

- **The summary**, the first paragraph under the title: one sentence on what the paper does. Written last, from the answers already there; read first.
- **读的版本**, the second paragraph: the title of the note's primary PDF. A new note is read in the library's best PDF, and later reads keep it as the primary; when the library gains a better version, a read-through moves the note onto it (reading.md, *Moving to another version*). A source without a version named refers to this PDF, with pages counted from 1 as the package's `<!-- page N -->` does. Other versions and supplementary material are read when a question needs them (*Evidence*).

## The nine questions

1. 这篇论文要解决什么问题，为什么重要？这是哪类论文？ The kind: a new method, a dataset, theory, an application study, or another.
2. 之前的工作怎么做，缺在哪里？ Note the works worth reading next.
3. 论文如何解决这个问题？ The intuition and the reasons; one concrete example walked from input through processing to output; the core formulas. Walk the method overview figure and say which passage of the text each module in it is. Then one fixed item, opening with its bold word:
   - **核心机制**: the key step, why it works (the authors' reasoning and the ablation that shows it), and what it depends on, in the field's own terms.
4. 创新点是什么？ What the paper claims to contribute; what is new against the closest earlier work; whether it is new in concept or only in implementation or data.
5. 做了哪些实验？ Each experiment as what it asks → how → what came out. How the comparisons were set up: against whom and why, on what data and metrics, under the same settings or not. Then five fixed items, each opening with its bold word:
   - **数据和划分**
   - **对比方法**
   - **指标**
   - **主要数字**, with the table they come from
   - **代码和数据**: public or not

   Each table and figure that carries a main conclusion gets its own sub-question: what it asks → how it was obtained (data, settings, how many runs, error bars) → the numbers and what they show. Check the numbers against the PDF; a table the package marks `unchecked_table` always. Other tables and figures get one line: what they show, and which table they agree with.
6. 结论站得住吗？ Six fixed items, each opening with its bold word:
   - **证据和范围**: whether each claim has evidence, and whether its scope is overstated;
   - **提升从哪来**: the ablations; whether the baselines were tuned with the same care; more data or compute;
   - **统计**: how many runs, what the error bars are, whether the gaps exceed the noise;
   - **前后矛盾**: where the text and the tables or figures disagree;
   - **假设和局限**: those the paper states, and those it plainly should have; then where it would fail: on what data or in what setting, as concretely as the paper allows;
   - **更好的验证**: the experiment you would run to prove or refute its main claim, beyond what the paper did, and the result that would refute it.

   Then the domain checklist below, keeping the points that apply.
7. 有什么可以进一步探索的点？
8. 总结一下论文的主要内容 A descriptive summary the authors would agree with, built only from the answers above, with one sentence on why the paper matters.
9. 有什么启发？ What the paper offers work like ours. It starts from the paper itself (its mechanism, its assumptions, where it would fail, what it left unexplored) and is read against the open problems the reader's brief names, when it names any. It opens with a paragraph naming that work and its open problems in words, since the note outlives the brief; with none given, the paragraph says so and the items rest on the paper alone. Then six fixed items, each opening with its bold word:
   - **可借鉴**: practices worth borrowing (method parts, experiment designs, evaluation, ways of arguing) and datasets, code or weights to use; each as a method interface: what it does | when it applies | what it costs | what its result depends on | what it needs in our setting, enough to judge (licences are out of scope);
   - **可吸取的**: the paper's experience and its flaws: what to take from them, what to avoid in our own work;
   - **前沿概念**: one line each: what it is, where it comes from;
   - **和别的论文的联系**: library papers with notes that this paper cites, and those the brief names: same mechanism, contrary result, generalisation or a possible combination, each resting on what the linked note says;
   - **思路与灵感**: direction-level inspiration, from the paper itself or for the open problems: a new way to see a problem, a direction worth taking; it need not be testable yet;
   - **头脑风暴**: at most three ideas, possibly none, each in four labelled parts: **想法** (the open problem it targets, or the limit of this paper it answers), **依据** (where in the paper, plus your inference), **怎么验证** (the smallest experiment, the baseline to beat, the result that would show it wrong), **可能败在哪**. An idea a linked note already holds says which note and what this one adds. Then **没展开的想法**: the other ideas of value, one line each: the idea, where in the paper it comes from, why it was not taken further; an idea another item or a linked note already holds is left out.

   Q9 is judgement and inference as much as fact: mark each as *Evidence* says. A later read against another project's open problems adds its paragraph and entries beside the earlier ones, each entry naming the problem it serves. A lookup writes only the Q9 items its question needs, under `## Q9 有什么启发？ [已答]`; the others wait for a read-through.

In a read-through, a fixed item the paper says nothing about keeps its bold word, followed by 论文没有说明; one that does not apply, or a Q9 item with nothing worth keeping, keeps its bold word and says so and why.

## The tree

The headings are the question tree, which Zotero's Better Notes outline shows as one.

- A question is a heading: its number, the question, its state in brackets: `## Q3 论文如何解决这个问题？ [已答]`. The trunk questions are `##`; a question one of them raises is `###` (`### Q3.1 推理时也要输入肿瘤 mask 吗？`); one level further is `####`. The answer is written under its heading.
- **States**: 待答 (not yet), 进行中 (being answered), 已答, 论文没有说明 (the relevant text does not say; never guessed), 要看别处 (the answer needs a source not yet consulted: name it, why it is needed, and what prevents the lookup; another version or supplement already available is read now when it bears on the question), 等 Qn (waits for another answer, asked again under it: `### Q3.2 对比方法也给了 mask 吗？ [等 Q5] → Q5.1`; once Q5.1 is answered, `[已答] → Q5.1`).
- A heading without a number is a section and has no state.
- A heading is plain text in Zotero: it shows no math, and TeX in it does not come back as a heading. Write a symbol there in Unicode (ŷᵢ, fθ) and the formula in the answer.
- A blank line before every block you write: Better Notes cuts its outline by them. Taken from Zotero, a block nested in a list item or a quote sits right under the line before it, and a table's rule reads `| --- |`: the same note.
- **A question keeps its number** once written: a project's index points at it. A new question takes the next free number under its parent; one that turns out to be wrongly asked keeps its number and heading, and its answer says why it was wrong.

## Evidence

- **The source** says where in the paper a fact is: a section, a figure, a table, an algorithm, an equation, with the page when it helps: (Sec. III-A), (Table III, p.11). An answer about the paper's whole idea, or a fact that cannot be pinned to one place, carries none.
- **Other versions and supplementary material** can answer a question without changing the primary PDF. Name the attachment and the section, figure or table, with that file's page number, beside each fact drawn from it. Link to that attachment's page when it is in Zotero, for example `[Preprint-arXiv-v7 · Sec. 7.2, p.15](zotero://open-pdf/library/items/ABCDEFGH?page=15)`. Material not yet in the library names its document and URL. Check what it actually says: an earlier version's setting is not automatically the published version's setting; distinguish differences and leave uncertain applicability explicit.
- **A quotation** is the sentence an answer rests on, copied verbatim in English, one line, unbroken, with any double quotes inside it as they are and its source after it; then a line holding only `>`; then its Chinese rendering. Formulas as `$x_{NC}$`, with no space inside the dollars:

  ```markdown
  > "Given a non-contrast liver MRI scan $x_{NC}$ and its corresponding tumor mask $x_{TM}$, our model simultaneously synthesizes three clinically relevant phases" (Sec. III-A, p.3)
  >
  > 给定平扫肝脏 MRI 和对应的肿瘤 mask，模型同时合成临床上相关的三个时相
  ```

  `pr.py quotes` searches the primary PDF and its package. It cannot verify a quotation against another attachment: compare that quotation with its own PDF, then mark it （已核对 <attachment title and location> · <date>）. The mark records a completed comparison. The text layer holds no LaTeX: of the sentences an answer could rest on, quote one in plain words. A line reported `unparsed` is rewritten in the quotation form. Any other reported quotation (often a table cell, a figure label or a formula the text layer garbles) is compared with its source page image, corrected if need be, and marked as checked; where the package misread the words, the quotation takes the PDF's words and that spot is settled in the package (`ocr.py commit`).
- **An inference** is marked （推断）; knowledge from outside the paper （论文外）; what the paper does not say is written as 论文没有说明.
- **Judgements about the paper** (Q6, Q7, Q9) are written as judgements, with what they rest on. "Not stated" is a fact and is written plainly; "possibly unfair" is a judgement and says why. Falling short of SOTA, closed code and honestly stated limits are not failures in themselves.

**Marks**, in the text (never a heading) after the fact they concern:

- `（已核对 <source> · <date>）`: someone compared this fact with its cited source. One per fact, the latest only; a table checked cell by cell takes one, after the sentence that presents it.
- `（更正 <date>：原写"…"，按 <evidence and its source> 改）`: what was there before a correction, and why it changed. It stays.
- `（<new PDF title> 删去了这段，原见 <previous PDF title> <source>）`: a later version dropped what this sentence rests on. It stays.

## Clickable figures and tables

`pr.py put` turns an unlinked figure or table in one of these forms into a box link in the primary PDF. These automatic links live in Zotero only; the file you edit keeps their plain text. For another attachment, write its figure or table name inside an explicit page link, such as `[Supplement · Fig. S2, p.4](zotero://open-pdf/library/items/ABCDEFGH?page=4)`; that link stays in the working note and through take/put, so it keeps the right PDF. For a source not yet in Zotero, use a link to its document and name the page.

- Linked: `Fig. 9`, `Fig.9`, `Figure 9`, `Fig. 2(b)` (the link is `Fig. 2`), `Table III`, `Supplementary Fig. 3`, `Extended Data Table 1`.
- Not linked: `p.11`, `Sec. III-A`, `Eq. (3)`, `图 4`, and any name in a heading: `### Q5.1 Table III 说明什么？`.

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
