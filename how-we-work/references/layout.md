# Layout: where things live

Read this before deciding where a new file or directory goes or what it is called, before moving, replacing, archiving or deleting one, and when a project's layout is first set up. The common block in the project's `AGENTS.md` says which record takes what; this document holds the whole map and what must hold when the map changes. What an entry of each record looks like is in the records reference of this skill.

## What the layout is for

The user steers several projects and comes back to each after days or months; a later session picks the work up with no memory of this one. Both find a thing by where it is and what it is called, without opening it. Two things therefore hold everywhere:

- **One home per kind of thing.** A kind of content lives in one place, and a file lands in the home of its kind the moment it is created. Files left where they were made are what the user has to stop and ask about: 「现在各种根目录下的 MD 文件都很散落，我觉得应该是放在 docs 下面的」; 「为什么在项目根目录下会有 local API 这些东西啊？乱放啊？」
- **`README.md` holds the project's only directory map.** `AGENTS.md` holds rules, `docs/goal.md` the direction; neither repeats the map. (An existing project whose records are not in the default places names those few places in its `AGENTS.md`, outside the block: the adopting reference.) A place that is not on the map does not exist for the next reader.

## The default map

This is the default for a new project. A project whose map differs follows its own `README.md`, and gives the reason for each difference in its own layout file (`docs/conventions/layout.md`). An existing project keeps the directories and the names it has; in one project the user said so of its experiment folders: 「已经有的就不用改了，未来新的，从新在开始就执行这个命名方式」. Bringing an existing project onto this map is a change of the map (below) and waits for the user.

The last column says whether git tracks the thing. For the inside of an experiment's or a report's folder, that kind's reference has the list. The common block's guardrail on patient data stands above every "yes" in the column.

| What | Where | In git |
|---|---|---|
| Rules for agents: the common block and the project's own rules | `AGENTS.md` | yes |
| What the project is; the only directory map, with this column; the list of upstream repositories | `README.md` | yes |
| The project's direction: goal, scope and constraints, completion criteria | `docs/goal.md` | yes |
| What is to be done and what it waits on; the user's passing ideas | `docs/todo.md` | yes |
| A decision: options, the user's words, who decided, the reason | `docs/decisions/<YYYYMM>.md` | yes |
| What anyone other than the user said about the project (a supervisor, a doctor, a reviewer), and what was done about each point | `docs/meetings.md` | yes |
| A design | `docs/specs/<YYYYMMDD>-<topic>-spec.md` | yes |
| An unattended run: its goal, its record, what waits for the user | `docs/goals/<YYYYMMDD>-<topic>.md` (the unattended reference of this skill) | yes |
| A problem met in code, tools or workflow | `docs/issues/<YYYYMMDD>-<topic>.md`; closed ones in `docs/issues/archive/` | yes |
| An issue's working material: reports, drafts, prototypes, data | `docs/issues/<issue file name>-reference/`, beside the issue; when the issue closes, to `archive/<YYYYMMDD>/` (the records reference, *Issues*) | no |
| The user's words behind a rule of the project's own | `docs/rules-sources.md` | yes |
| What this project adds to a reference of this skill | `docs/conventions/<kind>.md` | yes |
| Each technical problem: the directions tried, their state, what blocks them | `docs/exploration-tree.md` | yes |
| The ledger of all experiments | `docs/experiment-log.md` | yes |
| External datasets, one met during a literature search included; the training servers | `docs/datasets.md`; `docs/servers.md` | yes |
| One line of experiments: code, configuration, README, run records | `experiments/<YYYYMMDD>-<topic>/` (the experiments reference) | see the experiments reference |
| What a line of work produces on the way, put where the user can look while the work is still moving | `preview/` inside that experiment's folder (the experiments reference) | see the experiments reference |
| A report | `reports/<YYYYMMDD>/<task>/` (the reports reference) | see the reports reference |
| A summary over a stretch of time, such as the one before a group meeting | `reports/<YYYYMMDD>/meeting-summary/`, a task folder under the day it is written (the reports reference) | as a report |
| A version of a report made for other people (Word, slides), with its template and build script | the folder of the report it was made from | as the report |
| A literature survey | `research/<YYYYMMDD>-<topic>.md` (the literature reference) | yes |
| What the project now holds true, from literature and from experiments | `research/key_findings.md` (the literature reference) | yes |
| Which of the project's decisions rest on which paper | the project's paper index, `research/paper-index.md` unless the project already has one; the paper-read skill keeps it and has its form | yes |
| The progress of a long survey, kept so that it can resume | `research/scratch/` | no |
| Papers, their parsed texts and the notes on them | the user's Zotero library, reached through the paper skills; not in the project | outside the project |
| The project's data | `data/` and the directories its README names | no; a README that describes the data, yes |
| Upstream code | `repos/<repo>/`: a full clone, kept current, read-only (the experiments reference has the rules) | no |
| Model weights | pretrained: where the upstream repository expects them; trained here: in the experiment that produced them (the experiments reference) | no |
| What was removed or replaced and git cannot bring back | `archive/<YYYYMMDD>/` with an `INDEX.md` | no |
| The agent's memory | `.memory/` | as the project's `.gitignore` has it |
| Throwaway files | the session's scratch directory | outside the project |

Where the project stands has no row, because it has no file of its own: what is unsolved goes to the exploration tree and what is to be done to the to-do list, and `docs/goal.md` holds the direction only (the records reference, *Direction*).

## Names

- **Each kind of thing has one form of name**, the one the map gives it. In a project that began with this map, a new thing takes the form the map gives its kind. In an older project whose things are named otherwise, existing names stay, and whether new ones take the default form from now on is the user's to say once (asked at adoption); until they have said, a new thing takes the form its kind already has there.
- **A dated thing is named `<YYYYMMDD>-<topic>`**: the date undivided, a hyphen between it and the topic and between the topic's words. The user, 2026-11-12: 「统一成连字符」, 「日期就不要带连字符了，不要把年月日分开」. The date is the day the thing was logged, settled or started, so that a listing sorts by time. The topic says what it is about in the words the user uses; an issue's topic starts with the part of the project it concerns. The two kinds that collect by period are named the same way: decisions, one file per month (`<YYYYMM>.md`), and reports, one folder per day (`<YYYYMMDD>/`) with a folder per task inside. Names a project already has stay as they are; this is the form of a new one.
- **A name tells what the thing is and when it was made, without opening it.** This is the user's test. They asked for dated, topic-named experiment folders (「尽量保持{日期}_{实验主题}的命名格式」) when a listing no longer showed them 「最新进度和主题（做了什么）」. The date and a topic that says what was done are what must hold. A version mark or a running number is added to a name that already says what the thing is (`overview-v2.png`).

## A new directory or kind of file

- **A new top-level directory needs content that no existing home covers.** It is a change of the map: show the user what it would hold and why no existing place takes it, and on their yes add it to the README map in the same change.
- **A folder tells what it holds.** A top-level directory, and any folder whose name and whose parent's README do not already say what is inside and how its contents are named, gets a README or an index. The test is the user's: 「不然我怎么知道你具体哪个文件夹干了什么？」
- **A new kind of record** (a file that will collect entries) states its entry format at its top before the first entry goes in, and gets a row in the README map.

## Changing the map

Moving a kind of thing, renaming a top-level directory or bringing an older project onto the default map is a design, and the user decides it. What they need to see is the map itself, before and after: 「你先理清，然后给个大致的版本，不用太详细，给我预览一下，特别是文件结构这一块，什么东西？应该放在哪？」

After a move, two things hold:

- **Every live pointer leads to the new place**: links and paths in rules, READMEs, records, scripts and memory, the links in frozen specs included. A search for the old path that comes back empty outside the snapshots below is the check.
- **Snapshots keep their text.** A dated report, a log entry and the body of a frozen spec say what was true when they were written; old paths inside them stay as written, and the README carries a table of old path → new path for whoever follows one.

## Replacing and deleting

What happens to the old thing depends on who may still need it.

- **A version the user has seen stays beside the new one**, as the common block's guardrail says. Here is what that takes. It covers what the user judges by comparing: a figure, a prompt, a run's outputs, a review or a proposal they read. The new version gets a name of its own (a version mark on the same name, `overview-v2.png` beside `overview-v1.png`; a new run folder) and the seen one is left exactly as it was. A text document under git has its history instead, and a report is a snapshot (the reports reference). The user compares versions and goes back to earlier ones, and has said so in three projects: 「之前的版本记得保存在figures对应的目录下，这样要是不满意可以恢复」; 「可以。之前跑的不能直接被覆盖。」; 「之前探索的实验也不要删掉，可以保留，后面可以回顾反思，这非常重要。」
- **What git tracks is changed or removed in git.** Its history is the old version; where a reader would look for the old text, name the commit (`git show <commit>:<path>`).
- **What git cannot bring back goes to `archive/<YYYYMMDD>/`**, the date being the day it was moved there: files outside git, large outputs, environments, clones, an issue's reference folder when the issue closes, material no longer needed. The archive is the project's recycle bin, as the user defined it: 「不能取消archive，这是存档备份的地方，要按照日期归档，这样误删的可以随时找回，需要迁移或者删除或者重构等找不回旧版本的东西都可以放在archive，按日期存档，不入库，旧的，不需要的，没有用的材料也可以放进去，就是备份和删除的仓库。」 Each dated folder has an `INDEX.md` that lets a later reader put anything back without asking. An invented example (the names, the paths and the commit are made up):

  ```markdown
  # archive/20260402：目录迁移时换下来的东西

  恢复点：提交 `1a2b3c4`（迁移之前的最后一次提交）。

  | 什么 | 原来在哪 | 为什么归档 | 怎么恢复 |
  |---|---|---|---|
  | `SomeUpstream/`（浅克隆，含虚拟环境） | `third_party/SomeUpstream/` | 换成 `repos/SomeUpstream/` 的完整克隆；代码没有本地改动 | `mv archive/20260402/SomeUpstream third_party/` |
  | `root_env/`（`pyproject.toml`、`uv.lock`） | 仓库根目录 | 每个实验改为自带环境 | 两个文件移回根目录，`uv sync` |
  | `20260312-val-split-reference/`（一张已关闭 issue 的参考材料） | `docs/issues/` | issue 已关闭，还在用的事实已写进 spec | `mv archive/20260402/20260312-val-split-reference docs/issues/` |
  ```

  An archived `AGENTS.md` or `CLAUDE.md` is renamed (`AGENTS.archived.md`) so that no harness loads it as rules.
- **The archive makes a removal reversible; the decision to remove stays where it was.** Moving something into the archive, where a reference of this skill says to (an issue's folder at closing), is not removing it. Removing what this task did not create is the user's decision, and so is emptying the archive: list what is there, say what could still be wanted and where else it can be recovered from, and wait for their word.
- **A record that is superseded or wrong stays where it is.** What happens to its text is in the records reference of this skill (*Keeping records true*).

## Temporary files

The common block's guardrail gives the core: a file that a later step or a later session needs lives in the project. The whole rule goes by who will need the file after this session.

- **Nobody will: the session's scratch directory.** Downloads on their way somewhere, staging copies, one-off scripts, intermediate output that minutes can recreate. It is cleared at milestones.
- **A resumed session, the user or a later reader will: the project**, in the home of the work it belongs to: the experiment's folder for a run's intermediate results, the issue's reference folder for the material of a design or a review, the git-ignored `research/scratch/` for the progress of a long survey. A session can end at any step, and its scratch directory ends with it: 「可能会因为5h token 的使用量限制而暂停，所以你需要 scratch 保存中间文件和进度。这样断点后也能快速恢复。这点你在记忆中记一下，我提过好多遍了。」
- **Outside the project: only when the user names that place for that task.** What the user is to look at reaches them as a path inside the project.

  Dated hints from one machine of the user's, where the project sits on a Linux side beside a Windows desktop and a synced drive; another machine has other places, and the rule above is what carries over:

  - 2026-10-26, of scratch files: 「临时文件夹也不要用windows上的」.
  - 2026-11-03, of material put in the desktop's download folder for review: 「审阅材料放download这个不是我的偏好。如果我特地指出放 Windows+downloads，那就可以做，但是默认你不要这么做」.
  - 2026-11-04, of a file put on the synced drive: 「就我强调你放 Synology，你才放。一般的话，你就放在 archive 中或者报告中啊」.
