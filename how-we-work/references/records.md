# Records: what an entry holds and how each record stays current

Read this before setting up a record file, when the format at the top of a record file leaves you unsure what an entry must hold, and before closing an issue, freezing or superseding a spec, or correcting a record that is out of date or was never true. Day to day the format at the top of each record file is enough; those headers are written from this document. Where each record lives is in the layout reference of this skill. The rules of recording that hold in every turn are in the common block in the project's `AGENTS.md` (*Words* and *Records*), and are not repeated here.

## What the records are for

A later session starts with no memory of this one, and the user comes back to a project after weeks. The records are how both learn why things are the way they are. Each entry therefore lets a reader who was not there do three things:

- **Rebuild the scene**: what was being done, in what state, what was seen. The user asked for it when issues were first kept: 「对了，在记问题的时候需要记清楚，上下文（背景）也要记一下」.
- **See whose call it was, and in what words.** The user's sentences are the only evidence of what they wanted; a paraphrase carries the agent's reading of them.
- **See how things stand now**, without replaying the history. A standing record holds what a later reader will use. A list of what was sent or finished helps nobody: 「你把它保存下来没有意义啊」.

## What holds for every record

- **The user's words stand in 「」, with their date and their scene**: what was being asked, shown or done when they said it. The common block has the rule itself (whole, beside what they led to, voice-input errors corrected, the meaning kept, nothing added). Dictation that came out scattered is put in order, within the same two limits. The session transcript remains the letter-for-letter original, which is why the record can be the readable one.
- **What is not the user's says whose it is.** An option names its source (a file, another project, "main agent 提的"); a cause you inferred is marked 推测; a proposal stays marked 没拍板 until the user agrees. Words that reached you second-hand (another project's memory, a subagent's report) are marked as relayed and stay outside 「」.
- **History is appended; current state is rewritten.** In a record that is the history (decisions, what others said, the experiment log), entries are added at the end and an old entry gains only a pointer to what later changed it. A record that shows how things stand (the to-do list, the exploration tree, an issue's status, an alignment table) is rewritten to the present. The one other change an old entry ever sees is the removal of a statement that never held (*Keeping records true*, below).
- **An id is never reused.** Read the file's last entries before taking a number: two sessions may be writing the same file.
- **A decision is written in the turn it settles**, before the work that follows from it. A problem or a passing idea is written the moment it comes up, and the main line goes on: 「注意，不要忘记你的主线程任务。我提到的这些点，你要快速记录」.
- **Each record file opens with what it takes and its entry format**, and an entry follows the header of its own file. The formats below are where a new header comes from. A project may add fields; where it changes a format, its own records file (`docs/conventions/records.md`) says why.

## The records

| Record | File | Language | Changes by |
|---|---|---|---|
| Direction | `docs/goal.md` | Chinese | rewriting, only with the user |
| Decisions | `docs/decisions/<YYYYMM>.md` | Chinese | appending |
| To-do | `docs/todo.md` | Chinese | rewriting |
| What others said | `docs/meetings.md` | Chinese | appending (what was said); rewriting (the alignment table) |
| Issues | `docs/issues/<YYYYMMDD>-<topic>.md` | Chinese | rewriting, one file per problem |
| Specs | `docs/specs/<YYYYMMDD>-<topic>-spec.md` | Chinese | rewriting until built, then frozen |
| An unattended run | `docs/goals/<YYYYMMDD>-<topic>.md` | Chinese | as the unattended reference of this skill says; its parts are there |
| The user's words behind a rule | `docs/rules-sources.md` | Chinese | appending |
| What the project adds to a reference of this skill | `docs/conventions/<name>.md` | English, quoting the user in Chinese: agents read it | rewriting |
| Exploration tree | `docs/exploration-tree.md` | Chinese | rewriting |
| Experiment log | `docs/experiment-log.md` | by the common block's rule: Chinese where the user reads it, English where only agents do; an existing log keeps its language | appending |

### Direction: `docs/goal.md`

Sections: 方向 (where the project is going and what for), 范围与约束, 完成条件, 修订记录. A statement that came from someone names its entry in the decisions or in what others said. Each revision adds one line to 修订记录: `日期 · 起因 · 改了哪一节 · 谁定的`.

It holds direction only: 「goal不应该去表达的是整个项目的目标方向，或者说实现的最终目标吗？」 Progress, open technical problems and things to do each have their own record, and the file changes only after discussion with the user, as the common block says. An agent once kept a "current position" section here and updated it unasked: 「为什么会把记录项目的方向当前进展记入 goal？当前进展是记入 goal 的吗？不太合适吧」.

### Decisions: `docs/decisions/<YYYYMM>.md`

Takes: what the user decided, what the user adopted from a recommendation, and what the main agent decided alone once another document or a later run depends on it. Small decisions inside an unattended run stay in that run's goal document.

The entry keeps the options and the thinking, not only the outcome: 「我们尽量能记录之前的选项来源内容，还有我们的想法」. An option that was turned down keeps its reason, so that it can be re-examined instead of re-proposed: 「B 只写“没采用”是不够的，拒绝的原因一样需要写清楚，以便下次复盘的时候，也能清楚当初为什么没有采用。也能查清当初拒绝的原因，如果发现不对的话，也能更好地纠正」.

Id: `D<YYYYMMDD>-<n>`, the day it settled and its number on that day, from 1. The first decision record used one running number, and the user saw where that leads: 「如果你用同一个编号，后面会增长得很快。你觉得是不是应该按照日期或者其他方式去编号？」

A decision that is overturned or refined gets a new entry, and the old one's 后来改过 names it; the old entry's text stays as it was written (a statement in it that never held is the one exception: *Keeping records true*).

```markdown
## D<YYYYMMDD>-<n> · <要决定的问题>

- **问题**：要决定什么，当时的背景。
- **选项**：每个选项一行，写明出处（哪个仓库、哪个文件，或“main agent 自己提的”）；没说出处的写“对话里没写出处”，不猜。
- **讨论**：用户怎么想（原话，放在「」里）；main agent 的建议和理由；没选的选项各自为什么没选。
- **结果**：选了什么。谁定的：用户定的 / 用户采纳了 main agent 的建议 / main agent 自己定的。
- **落在哪里**：写进了哪个文件、哪一节。
- **后来改过**：被哪一条推翻或细化；没有就写“无”。
```

An invented entry (the project, the numbers, the paths and the words in 「」 are made up):

```markdown
## D20260312-2 · 新标的 240 张田间照片，验证集按什么划分

- **问题**：新标注的 240 张照片要分出验证集。它们来自 6 个地块，同一个地块的照片光照和病斑都很像。当时在准备 `experiments/20260312-field-finetune/` 的第一轮微调。
- **选项**：
  - A. 按地块划分，一个地块的照片只在一边。main agent 自己提的。
  - B. 按照片随机划分。出自上游仓库 `repos/SomeUpstream/tools/split.py` 的默认做法。
  - C. 沿用上一批数据的验证名单，新照片全部进训练集。对话里没写出处。
- **讨论**：用户：「按地块分吧。不过这样验证集会不会太小？太小的话数字跳来跳去，也没法比」。main agent：留 1 个地块做验证，约 40 张；数字的波动先用几次重复估出来，写进实验的 README，再决定要不要多留一个地块。B 没选：同一个地块的照片落在两边，验证分数会虚高。C 没选：新照片不进验证集，就看不出模型在新数据上的表现。
- **结果**：A。谁定的：用户定的。
- **落在哪里**：`experiments/20260312-field-finetune/README.md` 的“数据”一节；名单在 `experiments/20260312-field-finetune/splits/val.txt`。
- **后来改过**：无。
```

A spec lists the decisions it settled by id and one sentence each; their content is here.

### To-do: `docs/todo.md`

Takes: what is to be done and what it waits on (a person, data, a condition), and what the user mentions in passing as something for later. It is the agent's to keep: 「觉得 todo 应该不是我去维护的，应该是你去维护的，因为做事情的是你」. The common block has it read at the start of a session; look it over again at a milestone, when finished rows are closed and shelved ones may have come due. The user hears of an item when they need to: 「有时候有些 todo 也不用每一个都列给我，你自己判断就行了，有一些需要我知道的，那你可以跟我讲一下」.

One row per item, id `B<n>`, a running number:

```markdown
| # | 日期 | 用户原话 / 来源 | 事项 | 状态 | 何时提醒 / 下一步 |
```

状态: ☐ 未开始 · ⏳ 进行中 · ✅ 完成 · ⏸ 暂缓 · ❓ 等人 · ↗ 移到别处（写明去向）. An item of the user's carries their words; one you added says where it came from.

The last column is what keeps the list alive. An item the user shelved (「先不用」, 「回头再说」, 「提醒我」) says when it comes back, and when that moment arrives you raise it; the user does not ask again. A finished row keeps one line on how it ended and where the result is. Invented rows (the project and the words in 「」 are made up):

```markdown
| B2 | 2026-03-12 | main agent：调研时发现公开数据集 FieldLeaf 可以直接用 | 下载 FieldLeaf 并登记 | ✅ 2026-03-13 已下载，登记在 `docs/datasets.md` | — |
| B4 | 2026-03-14 | 用户，问到雨天拍的那一批要不要标时：「回头再说」 | 雨天拍的 60 张照片暂不标注 | ⏸ | 晴天那批的第一轮结果出来时提：要不要补标 |
| B7 | 2026-03-20 | main agent：`docs/goal.md` 的完成条件还没写，用户说第一轮结果出来再定 | 请用户定完成条件 | ⏸ | 第一轮对比的报告交给用户时提 |
```

An open technical problem is a node of the exploration tree; the to-do row is the action that would unblock it, and each names the other.

### What others said: `docs/meetings.md`

Takes everything said about the project by someone other than the user: a supervisor, a doctor, a reviewer, a collaborator, a data provider. It is recorded however it arrives: the notes of a meeting, a chat log the user pastes, one sentence the user relays in passing. A rule that said "group-meeting notes" left a supervisor's relayed sentence unrecorded until the user asked: 「这些东西你要都要记入到meeting里面,这也相当于一次沟通了」; and of a chat log: 「其实这些东西就相当于是meeting内容」.

Two parts:

- **一、原始记录.** Appended by date, as it arrived and unedited, under a heading that says when, who, and how it reached the project, for example (invented) `### 2026-03-18 · 合作的农技员看了 12 张拿不准的照片（经用户转达）`. When the user later supplies more of the same exchange (「是因为老师说的没讲完全，我现在补充，以下是他的原话，做好会议记录」), it is added under the same heading with its date.
- **二、对齐表.** One row per point, id `M<YYYYMMDD>-<n>` from the date of the exchange. An invented row:

  ```markdown
  | 编号 | 反馈 | 我们做了什么（出处） | 状态 | 下一步 |
  |---|---|---|---|---|
  | M20260318-2 | 病斑外面发黄的一圈也要算进病斑 | 标注说明已改；已标的 120 张里重标了 80 张（`experiments/20260319-relabel-halo/`） | ◐ | 还有 40 张没重标；重标完请他再抽看 10 张 |
  ```

  状态: ✅ 已做 · ◐ 部分完成 · ⏳ 进行中 · ☐ 未开始 · ⏸ 暂缓; ⚠ marks a point that pulls against the project's goal or a recorded decision. How a point was taken (采纳 / 修改 / 不采纳) is said in 我们做了什么, and one not taken gives the reason there; a point is input to weigh, as the common block says of all feedback. The table is checked against the files when it is updated, not filled from memory. When one person's points come up again (the next meeting, the next round of comments), the table is what is reported from: for each point, what was done and where.

### Issues: `docs/issues/<YYYYMMDD>-<topic>.md`

Takes a problem met in code, tools or workflow, or a pain point the user mentions in passing. One problem per file; the date is the day it was logged; the topic starts with the part of the project it concerns. The directory holds open issues only, because closed ones beside them get in the user's way: 「现在把 fix 的 issue 也放在同一个目录下，我很容易会被干扰，而且看得不是很清楚」.

A question still being talked through is not an issue yet (「你这个乱七八糟的，还没确定下来就已经在记issue了，删了」). A problem in one of the user's skills goes to the skills repository, as the common block says; from this project you log it there and go on, and the testing and the fix happen in that repository: 「你不需要实际测试，你只需要提issue就好了」.

Fields, in this order:

```markdown
# <部分>：<一句话说出问题>

- **来源 · 日期**：谁在什么场合提出或发现的。
- **背景**：当时在做什么任务、为什么做，当时的状态（git 提交、实验目录、环境），让没在场的人也能还原现场。
- **用户原话**：放在「」里；没有就写“无”。
- **现场**：跑了什么、看到了什么，引 `文件:行号` 和汇总的数字。
- **为什么要紧**：它妨碍了什么。
- **方向**：打算怎么处理。推测的原因标“推测”；提议标“没拍板”，直到用户同意。
- **状态**：open / 处理中 / 已解决。
```

An invented issue (the project, the code, the numbers and the words in 「」 are made up):

```markdown
# 预处理：竖拍的照片被转了 90 度，掩膜没跟着转，验证集里这几张对不上

- **来源 · 日期**：main agent 看验证集的叠加图时发现 · 2026-03-22。
- **背景**：在做 `experiments/20260312-field-finetune/` 的第一轮微调（提交 `4d5e6f7`）。训练前把照片和掩膜都缩到 1024：照片由 `prep/resize.py` 处理，掩膜在标注工具导出时已经缩好。当天要出第一轮结果给用户看，所以这一轮没有改预处理。
- **用户原话**（2026-03-22，看了叠加图之后）：「这几张怎么是歪的？先记下来，别耽误今天出结果」
- **现场**：`prep/resize.py:48` 的 `resize_keep_ratio()` 按 EXIF 里的方向把竖拍的照片转正；掩膜没有 EXIF，没有跟着转。验证集 40 张里有 6 张竖拍，这 6 张的 Dice 都低于 0.1，其余 34 张平均 0.71。
- **为什么要紧**：验证集的平均分被这 6 张拉低。这一轮各组用的是同一份数据，组间比较不受影响，但报告里的绝对数字偏低。
- **方向**：缩放之前把照片和掩膜一起按 EXIF 转正；加一项检查：每对照片和掩膜的尺寸一致。训练集里多半也有竖拍的（推测，还没查）。没拍板。
- **状态**：open
```

While an issue is open:

- **Its design is discussed with everything else read-only**, and what the discussion yields goes into the issue as it comes: the user's added facts and words, a direction they set, facts you checked. 「就是针对其他内容是只读的，issue 是随时记录的嘛」
- **It is weighed before it is fixed or ranked.** An issue records what was seen; whether it is worth fixing is still open. Check what the harm actually is (does anything read the thing? how many cases?) and say which parts are worth doing: 「你修之前确定一下这个 issue 值不值得修。有时候我记得有些 issue 是不值得修的」.
- Open issues of one part are taken up together: what needs a design becomes a spec, a small one is fixed directly.

Closing:

- **Resolved means it no longer bites.** Once the root cause is handled the issue closes, even if a contingency remains; the leftover and what would trigger it go into the closing note. 「我感觉可以变成 fixed，因为已经配置好了，暂时还不会遇到问题」; an issue 「不应该是一直未完成的状态」.
- The file gains `-fixed` in its name (`-wontfix` if dropped) and a line at its top saying where it went, moves to `docs/issues/archive/`, and every link to it is repointed, links in frozen specs included.
- **Its reference folder leaves with it.** First it is checked once more, as a guard against losing something and not as material to carry over: 「过时的东西完全没必要。因为他们或多或少已经写进代码或者什么地方了，我只是怕会有遗漏，所以才给你规定这个流程。」 A fact in it that is still in use and recorded nowhere else moves to where it is used, and links into the folder are pointed at the issue or the spec. Then the folder moves to the project's git-ignored `archive/<YYYYMMDD>/`, with a line in that folder's `INDEX.md` (the layout reference has the form).

### Specs: `docs/specs/<YYYYMMDD>-<topic>-spec.md`

Takes a design: the whole of it, written before it is built. The date is the day the design settled. Small agreed fixes and tidying need none. A draft is put here too and reaches the user as a brief in the chat, never as a file left somewhere for them to open: 「我不会看的。我只会让你简述给我，你应该放在spec下的」.

It opens with:

- **状态**: 设计中 / 已定 / 实现中 / 已冻结 / 已被取代.
- **入口**: which sections to read first, and in what order after a compaction or a resumed run.
- **不用读的**: which sections are history or background.

Inside, what the user decided is told apart from what is still a proposal (没拍板), and the section of settled decisions lists ids and one sentence each.

A spec is a snapshot. While it is being built, an error in it is corrected in place. Once built it is frozen: the later edits it still takes are a repointed link and the removal of a statement that never held (*Keeping records true*). A redesign gets a new dated file, and the old one gains one line at its top, its text kept:

```markdown
> 已被 `<新文件>` 取代（YYYY-MM-DD）：<原因>
```

Current behaviour is read from the code and the rules, not from an old spec.

### The user's words behind a rule: `docs/rules-sources.md`

Takes any exchange behind a rule of the project's own that is longer than the entry's `From:` holds, for an entry in `AGENTS.md` outside the block and in `docs/conventions/` alike; the entry then names the date. A sentence or two of the user's stays in the entry's `From:` and is not copied here. The words behind the common rules are kept with this skill, not in the project. The user asked for rules and their sources to be kept apart: 「我说的话应该放在 source 里面，然后具体的 to do 和其他内容你就另外放」.

Grouped by where the rule lives. One bullet per source: the date, the scene, the words in 「」; where a decision entry holds the full exchange, its id. A rule that has no words of the user's says who proposed it and from which case. A bullet is appended when the user approves or changes a rule.

It is consulted to check where a rule came from, or how wide it was meant when its wording is in doubt; the rule text is what is followed.

### What the project adds to a reference: `docs/conventions/<name>.md`

One file per kind of work, named as the reference it adds to: `docs/conventions/experiments.md` adds to `references/experiments.md`. It holds this project's rules for that kind of work and the facts that work needs. Where an entry differs from the reference, the entry holds for this project; one that departs from a common rule on purpose says which rule and why. Agents read the file, so it is in English and quotes the user in Chinese.

The script owns the file's name and its first line under the title. `hww.py add <name>`, run in the project's root, makes the file; it refuses a name that is no reference of the skill. The sync writes the line into a file that lacks it, and lists a file named for no reference: what such a file holds moves to the kind it belongs to, to `AGENTS.md` outside the block (a rule for every task), or to the project's documents (any other fact).

Under the line, one bullet per rule or fact. The same form serves an entry in `AGENTS.md` outside the block:

```markdown
# Experiments: this project

Read `~/.agents/skills/how-we-work/references/experiments.md` first; this file adds to it, and holds for this project where the two differ.

- **<the rule, one sentence>.** From: <the date, and the user's words in 「」 or the case>.
```

An invented entry (the project and the case are made up):

```markdown
- **Photos from the two greenhouse cameras are scored apart from the field photos.** From: 2026-03-25, the comparison in `experiments/20260324-source-gap/`.
```

A file made before 2026-11-12 may carry the headings `## This project only` and `## To promote`. They may stay, below the line; nothing reads them.

### Exploration tree and experiment log

Their formats are given here; when an entry is written, and what is added to it later, is in the experiments reference of this skill.

- **`docs/exploration-tree.md`.** One root question; a legend (✅ 已完成 · 🔵 进行中 · ⏳ 条件未满足 · ⬜ 未开始 · ❌ 失败 · ⏸ 暂缓 · 🚫 规则禁止); then one table per technical problem: `节点 | 状态 | 证据 / 原因 | 兄弟方案`. A failed node stays, with the reason. A node waiting on something outside names the to-do row that would unblock it. A 选择记录 at the end takes one line per choice of next node: date, which, why, the candidates after it.
- **`docs/experiment-log.md`.** Entries newest last, each under `## <YYYY-MM-DD> · <title>`, then **Hypothesis · Set-up · Result · Conclusion · Next**, naming the experiment folders.

## Keeping records true

Two cases look alike and are handled in opposite ways. The test is whether the statement was true, or was the decision, when it was written.

- **Out of date: the text stays, and says what replaced it.** A superseded document gets one dated line at its top naming what replaces it and why (the spec line above). An entry of an appended record gets its pointer: 后来改过 in a decision entry, a dated note under a log entry or under a finding. A dated report is a snapshot and stays as written; what was learned later goes into a new report, as the reports reference says.

- **Never held: the false statement is taken out, and the correct one stands in its place.** First find what rested on it: where the statement is about data or a run, list the conclusions that passed through it before changing any text (the experiments reference, *When something turns out wrong*). A finding that turned out false, a premise that was wrong when it was written, a limit nobody set. A later session takes what the records say as true and builds on it, and the user's words when that had happened were: 「不要留下任何错误信息的记录，避免越走越远」.
  - **Where.** Every project document that says how things are, and the memory, history included: a log entry, a findings list, a decision entry, a frozen spec. Search for every place the statement is made or relied on.
  - **A report the user has seen or presented is the exception: its sentence stays, marked.** A report records what was shown on its day, and what was said from it has to stay traceable. The false sentence stays as written, with a red box beside it saying that it is wrong and linking to the report that corrects it; a box at the report's top lists the corrections; the correcting report says what it corrects. (Settled by the user, 2026-11-10.)
  - **What stands there afterwards.** The correct statement, and under it a dated line saying that an earlier statement here was wrong and what showed it. The line names what the earlier statement was about and leaves the false statement itself unwritten. An invented example, in a findings list:

    ```markdown
    - **验证集里竖拍的照片有 6 张**，都来自 3 号地块。
      - 2026-04-02 更正：这里原先写的张数是错的。统计脚本把缩略图也数了进去（`docs/issues/archive/20260322-prep-exif-rotation-fixed.md`）。
    ```
  - **What rested on it.** A decision that rested on the false statement is reopened with the user as a new entry; in the old entry the statement is replaced in the same way, and its 后来改过 names the new entry.
  - **How far the removal reaches.** The project's documents and memory as they stand in the working tree. Session transcripts stay as they are (「会话记录不要动」). Git history stays as it is too, unless the user asks for a rewrite for that one time (「仅这次可以修改git提交」).

When you find either case, say in the chat which it is and where the text was changed.
