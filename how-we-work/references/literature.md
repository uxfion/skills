# Literature

Read this before you look for what others have published (papers, models and their weights, code, datasets, the field's guidelines), and before you import a paper into the library, read one for the project, record what it gives the project, or cite one in a project document.

What holds in every kind of work is in the common block in the project's `AGENTS.md`. What only this project needs (its Zotero collection, its directions and the fields next to them, the venues that count in its field) is in the project's `docs/conventions/literature.md`.

## What the literature is for

The user builds on what others have done and wants to know it before building: 「只有了解到整个行业、整个任务别人已经做了什么以后，我们才可以继续自己的工作，吸取他们的经验，把一些想法应用起来，而不是闭门造车。」 Two failures worry them. One is work that turns out to be already done or out of date: 「我不希望我的项目做完后发现是已过时的方法」. The other is drowning: 「你需要自己有重点。不要被爆炸的信息所淹没了。」

A paper is read for what the project can use, and what it says is weighed, not taken: 「他们说的并不一定就是正确的，客观的，但是思路上可以借鉴，但是也要持保留意见，你要有自己的判断。」

## One home for each thing

| What | Its home |
|---|---|
| A paper: its item and the PDF of each version | Zotero, in the project's collection |
| Its parsed full text (the structured package) | Zotero, beside the PDF |
| What the paper says, judgements about it, what it offers work like ours | The paper note, in Zotero under the paper |
| Which of the project's decisions rest on which paper | The project's paper index, which paper-read keeps |
| A decision and its reasoning | `docs/decisions/` |
| A survey: what exists on a question, compared, for the user to decide from | A survey report in `research/`, under a dated name (the layout reference of this skill, on names) |
| What the project now holds true, from literature and from experiments | `research/key_findings.md` |
| A public dataset met on the way | The project's dataset register |
| Someone else's code | `repos/` (the experiments reference of this skill, on upstream code) |

The user settled the first three rows: 「我现在都是确定放在 Zotero 笔记里面，而不是用一个专有的项目去管所有这些东西」. So the project's own folders hold surveys, findings, the paper index and decisions; papers, their parsed texts and the notes on them are in the library, taken out and put back by the paper skills. A project that still keeps papers and notes in its own folders is in the earlier state: those copies are leads, and the library is where you look and write.

## The paper skills, and what they leave to this document

The user's paper skills carry this work. Each skill's own description says when it applies, and its `SKILL.md` governs how (the common block, *The user's skills*). The table is a map for orientation; where it and a description differ, the description is right.

| The step | The skill |
|---|---|
| Find current papers on a topic | papers-cool-search, where it is installed |
| Pin down which paper is meant, find its versions, get its PDF | paper-fetch |
| Put papers into the library; tidy the library; export BibTeX | paper-to-zotero |
| Look something up in a library paper; read one through into its paper note; record that the project decided something from it | paper-read |
| Parse a PDF into its structured package | paddleocr |

These are the skills' to govern, and this document says nothing of its own about them: logins and verification pages, how a route to a paper is tried, which version of a paper is filed, when a paper is read through and when only looked up, how a note is written and its evidence marked, what a reader subagent is sent with. Where this document and a skill seem to disagree on one of those, follow the skill and log the difference as an issue in the skills repository.

What the skills do not say is the rest of this document: where to start, how wide to look, what is worth importing, how much a paper weighs in a decision, and where the project records what it took from a paper.

**The library first.** A question about what a paper says, or about what the papers we already have say, starts in the library, through paper-read. Before importing, downloading or cloning anything, check what the user already has: the library, `repos/`, the model caches. The case: asked which datasets the project's reference papers had used, an agent started an online search. 「论文相关的 PDF，包括结构化出来的文档还有 Markdown 都有啊，你直接去zotero文献库里找就好了。你怎么去网上去找了？」

## How wide to look

Two corrections from the user pull in opposite directions. The kind of question decides which one applies.

**A question about the field is searched wide.** "Has anyone done this", "what is the state of the art", "is there a public model for it", "what should our baseline be": the search starts at the level of the whole project, not of the exact task.

- Each direction is searched at the survey level as well as at the level of the exact task, with the key words of the directions combined: 「你记得综合一下关键字，统一去查。我觉得肯定是有人做过相关的工作的，应该做得比较好」.
- The fields next to ours are listed before the search starts; the project's own file names them. For a medical-imaging project, as an example: other imaging modalities, other anatomy, the general form of the problem outside medicine, foundation models and model zoos. 「不是超声模态的也可以考虑，比方说它是在 MRI 上的，我们也可以借鉴。」
- The last five years: 「文献需要在近5年内」. Older work enters where the field still builds on it.
- Top venues and representative work first.
- The project's own choices do not narrow it: 「你在调研文献的时候，不应该被我的这个决定给局限住，你的调研还是一样查文献的。」
- Starting points for sources, to extend as the question needs: papers.cool; Google Scholar and publishers, reached the way paper-fetch reaches a page; Hugging Face (`hf`) and GitHub (`gh`) for models and code; the field's guidelines and handbooks for a question of practice (how the field's practitioners delineate, measure or grade something).

**A question about named things keeps their size.** When the user asks about particular papers (ones they sent, ones named in a meeting, "the main few"), find those first, read them deeply, and skim what surrounds them. The amount of material at hand does not set the size of the task. The case: the same question about datasets, where the agent, once in the library, treated every paper in it alike and delivered a library-wide survey where a table of the few named papers was wanted. 「也不是说查所有相关的文献，就是我们头部几个比较重要的，应该我们提到过吧？就重点参考那几篇论文」 「你要分得清主次嘛.重要的，和我们比较相关的，那就主要看；其他的，大致过一下就好」

A paper the user sends as an example of a direction is both kinds: read it, then look for its neighbours. 「也不仅仅是指我发给你这篇，你也可以去 papers cool 上或者其他地方去查一些相关的内容」

**The size follows the question.** A quick look (「查一下」) is answered in the chat, with the table of what was searched when the answer is that nothing was found. The survey file, its progress file and the imports belong to a survey the user asked for or will decide from.

**"Nothing exists" has to show its search.** The user does not believe a narrow negative: 「我觉得你文献综述查的现状还是太少了。」 「不可能一篇都没有的呀，不可能一个开源的权重都没有呀」. They were right: the first survey had searched only the exact task, and the second, across the neighbouring fields, found several sets of downloadable weights. So before a report says that no paper, model, weights, code or dataset exists for something, the search has covered the neighbouring fields and the last five years, and the answer carries what was searched: each direction, its queries, where they were run, what each found, the years, and what was left unsearched. An invented example of the form (the project, the models, the addresses and the sizes are made up):

> **结论：没有能直接用于田间茶叶病斑分割的公开权重。** 相邻领域有 3 个能下载的权重（2 个输出病斑掩膜，1 个只分叶片），可以作为迁移的起点。
>
> | 查的方向 | 查询词 | 在哪查 | 查到什么 |
> |---|---|---|---|
> | 本任务：田间拍摄的茶叶病斑分割 | `tea leaf disease lesion segmentation field images`；`tea leaf blight semantic segmentation deep learning`；`茶叶 病斑 分割` | Google Scholar、papers.cool、GitHub、Hugging Face | 方法论文 4 篇，来自 2 个课题组；权重和数据都不公开 |
> | 相邻：其他作物的叶片病斑分割 | `plant leaf lesion segmentation pretrained weights`；`crop disease segmentation benchmark` | Google Scholar、papers.cool、GitHub、Hugging Face | LeafLesionNet（苹果、葡萄）：权重可下载（文件列表 `https://example.org/leaflesionnet/files`，412 MB），仓库里有训练入口 `train.py` |
> | 相邻：实验室拍摄的植物表型分割 | `plant phenotyping leaf instance segmentation` | Google Scholar、GitHub，另查了两个表型挑战赛的页面 | PhenoSeg-B：权重可下载（文件列表 `https://example.org/phenoseg/releases`，98 MB）；只分叶片，不分病斑 |
> | 相邻：通用分割基础模型在农业图像上的微调 | `segmentation foundation model agriculture fine-tuning`；`promptable segmentation plant disease` | Google Scholar、Hugging Face | AgriSeg-ft：权重可下载（文件列表 `https://example.org/agriseg-ft/tree/main`，1.2 GB）；论文写“代码即将公开”，仓库里只有推理脚本 |
> | 相邻：无人机影像里的作物病害区域分割 | `UAV crop disease region segmentation` | Google Scholar、GitHub | 有 3 篇方法论文，都是地块级的区域，没有输出叶片级病斑的 |
>
> 时间范围：2021–2026。没查的：中文数据库、专利。

**Public means seen.** Weights, code and data count as available once you have seen the files: for weights, the file listing, recorded with its URL and size; for code a baseline is to be retrained from, the training entry point in the repository tree. A paper's "code will be released" and a README's link are leads.

**A dataset found** is entered in the project's dataset register with its link, size, licence and what it could serve. A small one is downloaded to the project's place for outside data, with a note of its source beside it (link, version, licence, date, checksum). A large one is registered and discussed with the user before any download. Where it needs a registration, an agreement or a signature, record the route: the account and the signature are the user's. One whose licence forbids redistribution is used locally only.

**A survey sent to a subagent** takes its breadth from its brief, because the subagent knows only what the brief tells it. The case: this breadth rule was written in the document the main agent had read, the survey was done by a subagent, and it came back narrow. Besides naming this document, the brief gives what the subagent cannot work out alone: the question in the user's words, the project's directions and the neighbouring fields to cover, the years, what the library already holds, and what the answer will be used to decide. The subagent hands back the papers worth keeping as identifiers; importing them is the main agent's, so that the library has one writer. Whether the subagent may send agents of its own is the common block's rule (*Subagents*).

**On the web, every agent is the user**: their address, their browser, their institution's login, so a site that sees a crowd blocks the user. Inside the paper skills their own rules apply. For any other searching, yours or a subagent's:

- One agent on a site at a time, requests made by hand and seconds apart; a script never loops over a site or sweeps it (「你这种循环千万要注意小心，会被直接拉黑」).
- Requests carry nothing personal, an email address included.
- When your own search or fetch tool is refused, that route is closed and the site is not: go on to the next route (an OpenCLI adapter where there is one, then the user's browser through opencli) before reporting failure.
- A login or a verification page that only the user can pass is left as it is and brought to the user. Any other block met in the user's browser itself (a bot check, a 403, a 429) ends the work on that site for the run and is reported. Here this document is stricter than the common block's three tries: what a site refuses or blocks is not tried again.
- What no route reaches is listed with the routes tried and settled with the user afterwards: 「实在找不到的就不要卡在那里一直循环浪费时间了，事后报告并记录即可，之后在一条一条由用户确认」.

**A survey resumes from disk.** The usage limit or the end of a session can stop a survey at any point, and what it had found has to be there afterwards. Its intermediate results and a progress file (`research/scratch/<YYYYMMDD>-<topic>/progress.md`, a folder per survey: what is done, what is in flight, what comes next) are kept in the project as the work goes; the layout reference of this skill, on temporary files, has the user's words and the reason. A survey stopped midway keeps what it has, and its top says what is missing.

**Reading shifts the direction without anyone deciding it**: 「你在查文献的过程中，读得越多，方向可能也会慢慢偏移。反正大方向是我决定的，在合理的时间点停下来和我讨论，小方向你自己决定。」 When what you have read would change the project's direction, bring it to the user at that point.

**A survey beside a main line** comes under the rule that the main line comes first on quota (the subagents reference of this skill). The case behind that rule was a literature one: literature agents running beside the main line used up the shared limit. 「你的文献任务暂缓一下，用了太多token导致限额了，影响了主任务。」

## What goes into the library

- **Screen first.** A paper goes in when the project has a use for it. The user's test for what stays out: 「那些没有用的、过时的或者一点意义都没有的文章就不用入库了」
- **What a survey found useful goes in**, not left behind as a link or as a summary of its abstract in a report: 「你调研过的有用的文献是需要保存下来的。」 A survey the user asked for therefore includes importing the useful papers it found: for those papers, the request for the survey is the request to add them that paper-to-zotero's rule on authorization asks for. The library is outside the project and is written only through paper-to-zotero, whose `SKILL.md` holds as written for everything else. Your report on the survey lists the papers that went in. A search you began on your own ends with the useful papers listed by identifier and proposed for import.
- **A paper needs no code to go in.** The bar for a baseline is higher than the bar for the library: 「我们考虑 baseline 肯定是要有代码可以复训的，但是你相关的文献没有这个限制条件可以入库zotero」
- **The collection** is the project's, named in the project's `docs/conventions/literature.md`, so every import names it. Where that file does not name one yet, ask at the first import and write the answer there.

## Reading

Whether a paper is read through or only looked up, and how, is paper-read's. What the project adds:

- **Full text is the evidence.** A conclusion drawn from an abstract is a direction to look in, and is labelled as that. A paper that a recommendation or a decision rests on has been read in full: 「对于那些重要的文献你需要看全文」.
- **Reason from the paper, not from a summary of it**: 「你应该去读原文markdown，而不是总结出来的research」. A survey report or a finding points to the paper's note and full text in the library and does not replace them. Where a synthesis and a paper note disagree, the note, checked against the PDF, is right; correct the synthesis and say what differed.

### An important paper with public code is read against its code

This applies when the project will build on the paper (a baseline to retrain and change, a method to borrow parts from) and its repository is public. 「特别重要的，然后也有GitHub仓库的，对照着看，同时做好research的笔记。」 The reason: 「因为后面我们肯定要改 baseline 或者优化我们的 baseline，然后逐渐形成方法。」 The aim is to know how they built it, not to port it: 「而是知道它的一些方法实现，然后为我们所用的，对我们完成这个任务有帮助的，可以吸收借鉴的」.

What the reading brings back, as a starting set to extend for the paper in hand:

- where each piece of the method lives in the code, by path and line: the losses and their weights, the schedules, the preprocessing, the training and inference entry points;
- the defaults and settings the paper leaves unsaid;
- every place where the paper and the code differ;
- what the release lacks: training code, weights, data, configurations;
- what we can borrow, each marked as reused as it is, re-implemented, or taken as a setting.

Clone the repository into `repos/` first (the experiments reference of this skill, on upstream code), so that the reading is of files, not of web pages: 「你如果调研的话，肯定是把这个仓库git clone克隆下来,然后再慢慢看是最方便的」. When the reading is done by paper-read's reader, its dispatch says that the project will build on this paper and why, and gives the clone's path and commit; where in the dispatch these go is paper-read's. What the code shows about the paper goes into the paper note, as paper-read's note format records a source outside the paper. What the project decides to borrow is a decision of the project's (*Recording what a paper gives the project*, below).

## How much a paper weighs

- **Strong venues carry a decision; a weak paper never carries one alone.** 「注意顶会顶刊对于计划的决策占比更大，比较小的论文不可作为单独的决策依据。」 The user's two tiers: 「应该分高质量论文：顶刊顶会一区部分二区部分高质量arxiv也算 和 低质量论文：其他小期刊会议（没有影响因子或不是主流）的论文，不能作为主导决策的依据，需要鉴别真假。」 A weak paper can still supply an idea to test.
- **A decision that leans on the literature names its support**: high-quality papers, or the project's own data. 「决策方向要有顶会顶刊论文支持或者数据支持。决策需要有记录。」
- **The venue raises the weight; it does not settle the claim.** Whether a paper's conclusions hold is judged in its paper note, where paper-read has its reader weigh them. Where a paper disagrees with what the project measured on its own data, say so and raise it; the paper's word alone does not overturn the measurement.

## Recording what a paper gives the project

The line between the paper note and the project is paper-read's, and the table under *One home for each thing* gives its two sides: what is about the paper, or about what it offers work like ours, is in the note, where every project finds it; this project's choices are in the project. In the project:

- **A decision made from a paper** is written in `docs/decisions/` (the records reference of this skill has the entry's form), naming the paper by its citation key and the place in its note the decision rests on. It also gets its line in the project's paper index, whose form is paper-read's. A paper or a method that was weighed and turned down is recorded the same way, with the reason.
- **What the project now holds true** goes into `research/key_findings.md`. Reports and specs point to the finding or to the paper note instead of deriving the conclusion again.

### A finding

`research/key_findings.md` is in Chinese (the user reads it), in sections by date, appended: `## 【YYYY-MM-DD】<what produced these findings>`. One bullet is one finding: the conclusion in bold, as a sentence that reads alone; then the numbers or the conditions it rests on; then, in parentheses, where the evidence is: a survey report and its section, an experiment's folder, a decision's number, or a paper, as its citation key and the place in its paper note. The numbering of a note's questions is paper-read's note format; the pointer uses it as it stands in the note.

When later evidence weakens or narrows a finding, its sentence stays and a dated line under it says what changed and where that is recorded. A finding that turns out never to have held is handled as the records reference of this skill says under *Keeping records true*, the one home of that rule.

An invented example (the project, the papers, the numbers and the paths are made up):

```markdown
## 【2026-03-12】文献调研：田间叶片病斑分割

- **在实验室白底照片上训练的模型，直接用到田间照片上会明显变差**：3 篇论文各自报告的跨场景 Dice 都比同场景低 20 个点以上。（`research/20260312-leaf-lesion-survey.md` §2）
- **通用分割基础模型微调后是现成的最强起点**：在 2 个公开数据集上都排第一，条件是病斑大于叶面积的约 5%。（`research/20260312-leaf-lesion-survey.md` §3）
  - 2026-04-02 加注：范围变窄。我们自己的数据里小病斑占多数，微调后的模型在小病斑上不如专用模型（`experiments/20260328-small-lesion-compare/`；`docs/decisions/202604.md` D20260402-3）。

## 【2026-04-20】读 LeafLesionNet

- **LeafLesionNet 不能原样当 baseline**：它的训练要逐像素的病种标注，我们只有病斑的二值掩膜。（zhangLeafLesionNetFieldRobust2025 · 论文笔记 Q3、Q6）
```

## Citing in project documents

- A library paper is named by its Zotero citation key, so that one search finds every mention. A paper not in the library is named by an identifier seen during this work (DOI, arXiv id or page), never by a title and venue recalled from memory.
- Each claim about a paper carries its place in the source: section, figure, table, equation, page.
- What you or a subagent inferred is marked 推断; what comes from outside the paper says so. What rests on an abstract alone is marked as a direction.
- A manuscript's `.bib` is exported from the library through paper-to-zotero, with the library's citation keys, and is corrected in the library, not in the file. What a sentence says a cited paper showed is checked against that paper's full text before the sentence enters a manuscript or a decision rests on it; how a fact from a note is checked is paper-read's. The rest of manuscript work is in the papers reference of this skill. A report carries its own reference list, its papers named as this section says.

## A survey report

A survey is asked for so that the user can decide something. Its result reaches them in the chat as findings and a proposal; the report is the file behind that, and the decision stays theirs: 「你可以派一个subagent去调研，然后给出调研报告，回头我再决定。」 It is in Chinese, and its structure follows the question it answers, not an earlier report: 「不要保持一致，根据你自己的情况和实际任务的导向来」. Every survey report opens with these lines:

> 文件性质：调研报告，供用户决定，不是决定。编写日期 YYYY-MM-DD。
>
> 用户原话：「…」（这次调研要回答的请求）
>
> 背景：当时在做什么、为什么要查。
>
> 查了什么：方向（含相邻领域）、查询词、来源、时间范围；没查的。
>
> 读法：§0 一页答案；其余各节讲什么；证据等级（全文读过 / 只看了摘要 / 只检索到）。

§0 is the answer, on one page. A report that compares options also says which option its writer leans to and why (being familiar with one is no reason), which constraints are hard and which are only effort, and what would reopen the choice.

A method the survey found better than ours is recommended or dismissed only after it was tried on our data (the experiments reference of this skill, *What a result may claim*).
