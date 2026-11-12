# Papers

Read this before writing or changing a manuscript, one of its figures or tables, a cover letter or a response to reviewers. Read *The outward document* in the reports reference of this skill with it: the rules for every text that goes out under the user's name have their home there (it is one whole that shows the settled work, it has one voice, it stands behind itself, each limit is told once, as a limit or a next step). This document adds what is the manuscript's own.

How one project runs its paper (its journal and template, how it compiles, the order of its revision, its change log, its practice for figures, tables and letters) is in that project's `docs/conventions/papers.md`.

The paper goes out under the user's name, to a reviewer who sees the paper and nothing else. Three things follow, and they are the sections below:

- The reviewer meets one finished piece of work: *One whole, in a manuscript* and *Not defensive*.
- What the paper states is what was done, and how favourably it is told has a rule of its own: *Presenting the method* and *Facts*.
- Every change you make stays visible until the user has read it: *Red until read*.

## One whole, in a manuscript

「论文的正文中应该展示一个整体，而不是一次次实验或者revised的中间流水。」 What this asks of any outward text is in the reports reference. In a manuscript two things come with it:

- **A claim that recurs reads the same everywhere.** Abstract, introduction, contributions, method, results, captions and discussion tell one argument. When one place changes, bring the others along in the same piece of work and name them in your report. After a new table went in, the user asked 「文中其他地方也同步改了吗？」, and more places were then found.
- **It is a way of reading the paper, not a step to tick off.** When an agent turned it into "check every decision against the full text", the user corrected it: 「也不是说"每条决定都要放回全文核对"，就是要把这篇论文看成一个整体」. Every rewrite, and every option you put to the user, is written for the paper's one argument.

Sentences are plain and literal, at the level of a top venue, and tell the paper's story well: 「要说人话，一切前提要有高水准的学术写作水平和讲好故事的能力。」

## Not defensive

「你不觉得这样描述很像防御性的写作吗？就是为了怕审稿人会问什么而防御性地提前说，但是实际上在展现的时候，是不是没有必要？」 The user's reason: 「避免防御性写作，这是ai写作的很明显特征」.

The rule is a pair. The first half alone deletes explanations a reader needs; the second alone brings the hedges back.

- **A sentence whose only job is to answer a question nobody asked is left out, or replaced by the positive fact.** An invented example: "The threshold was not tuned on the test set." is defensive; "The threshold was set on the validation split." tells the reader what was done.
- **Where a reader stumbled, or the user expects one to, the text says what was done, once.** A definition, a total, a sentence saying which reference a metric uses. A co-reader could not make two counts add up, and the user had met the same as a reviewer of someone else's paper (「这样是否能避免出现数据不清楚，算出来不对的问题，因为我给其他人审稿出现过一次情况。」), so a table of the data was added. What separates such a sentence from a defensive one: a reader did stumble or the user expects one to, and the sentence states what was done instead of denying a fault.

## Presenting the method

Settled by the user on 2026-11-10: the evaluation is objective, and within that the paper presents the method at its best. A revision is there to make the paper stronger.

**Never.** Nothing is fabricated: 「不伪造，这是现实因素」. The way of evaluating is not tuned so that the method wins; a change to it is made because it judges more objectively, and is tried on a case or two before the full run: 「注意，这不是为了我们的模型好而去调整，而是更客观地去评价。」

**Yours to do.** Honest results can often be presented in more than one honest way: which of several valid variants, references or related metrics the paper reports, in which order results appear. Among presentations that are all true, write the one that favours the method most, and say in a line which you chose and what the others were. A variant is a candidate only when the method and settings the paper states produce it; one that departs from what the code or those settings do is a discrepancy (below), not a presentation. What an experiment fixed before its result existed (its criterion, its control, a tie written as a tie) is not among the things chosen here, and a metric or variant brought in after the results were seen is labelled so: the experiments reference of this skill, *What a result may claim*. A weakness is said once, lightly, as a limit or a next step; a limit no reader has asked about is not expanded on.

**Reported first, decided by the user.** A finding that is materially unfavourable to the method, and any place where what the paper states and what the code or the data actually did disagree, is put to the user before any text changes, with what each way of writing it would say. What the paper states has to be what was done; how a discrepancy is resolved is never settled by an agent on its own, in either direction. The discrepancy and the user's decision on it are recorded where the project keeps such things, and the project's records say what was actually done.

## Facts

- **Every number, table and figure in the paper can be traced** to the weights, the script and the output that produced it, through one index in the project (the project's `docs/conventions/papers.md` names where it is; where there is none yet, set one up beside the manuscript and add it to the README's map): 「我希望论文里的某一个指标，能快速在对应的文档中或者在对应的机器上找到权重和代码，并进行推理。」 A number you cannot trace is raised before it is repeated.
- **Numbers agree** between text, tables and captions, with their units, and a reader's sums come out: 「就只要数据前后对得上就行了」.
- **A metric or an analysis enters the paper after it was looked at,** as the common block asks of any result (*Look, understand, then trust*).
- **Facts about people, money, ethics and where data came from are the user's.** Author names and order, affiliations, grant numbers and their order, the ethics wording: enter what the user gives character for character, and ask for one that is missing. In one manuscript the order of the grants turned out to carry meaning.
- **Citations,** the bibliography and what a sentence says a cited paper showed follow the literature reference of this skill.

## Red until read

- **Every change to the manuscript shows as a change until the user has read it.** 「这些修改需要标红。方便我审阅。」 The user has had to ask for this repeatedly. In a LaTeX source the usual way is a revision macro (for example `\rev{…}`) that prints its content red, used from the first edit on, with a switch in the preamble that turns the colour off.
- **Red means: the user has not read this properly yet.** The review state lives in the source itself, so a commit does not wait for the review: unreviewed changes are committed as they are, red on.
- **The red comes off only when the user says they have read those changes properly.** 「大致看了一遍」 is not that. An agent heard 「我记得大致过了一遍。」, recorded the batch as reviewed and proposed removing the red; the answer was 「不要，我只是说大致看了一遍，没有具体看，所以还是先提交。」 This is the common block's rule that a leaning is recorded as a leaning.
- **A deletion leaves nothing red on the page.** Name each deletion and its place in your report, so that the user can find it.
- **A copy for someone else** is built with the colour switched off and the marks still in the source; afterwards the working state, red on, is restored: 「然后把标红的标注先取消掉，编译一版，我需要发给别人相对完整的。」
- **In an unattended run,** the versions the unattended reference asks you to prepare for a choice of the user's stand side by side, each marked red, none chosen.
- **A sentence of the manuscript that goes to the user as a question** is shown as a change: where it is, the original, the proposal, the Chinese of each, the changed words marked, the reason, then the options.

## Where the other rules are

- **A figure you drew** is looked at as a rendered image before the user sees it: the common block (*Look, understand, then trust*) and, in the reports reference of this skill, the rule that every figure is looked at. The file format of a manuscript's figures is the manuscript's own; the format rule in the reports reference is for reports.
- **A figure the user drew or accepted, redrawn:** the seen version stays beside the new one (the common block, *Guardrails*); the layout reference of this skill has the detail on replacing something the user has seen.
- **What a reviewer, a co-author or a supervisor said about the manuscript** is recorded, and followed point by point until the text answers it, as the records reference of this skill describes for what others said. Each point is weighed on its merits, like any feedback (the common block, *Who decides what*).
