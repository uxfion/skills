# Unattended runs

Read this when the user switches an unattended run on, before writing its goal document, before notifying them, and again, with the goal document, when a session resumes a run after a compaction or a restart. The common block (*Unattended runs*) has how a run is switched on and off and what its rules come to; this document holds the rules themselves, the reasons, the form of the goal document, what is done ahead and reported, and what is known about keeping a run alive.

## Why the user runs unattended

The user's time at the keyboard is the scarce thing; yours is not. An unattended run turns their absence, usually a night, into progress on the project: 「在我不在线的这一段时间里，你要尽可能向前推进，因为等我回来后，我希望看到结果。而不是被某个问题卡住。」 They come back to decide, not to start work: 「不要等我做了决定以后，你再去做一堆东西。你要把你能做的以及未来可能需要做的都做好了，等我在的时候，你再集中问我……甚至有些路已经走通了，只是让我确定一下就行了。」 An agent that finishes the named task and waits has wasted the night: 「不然的话，无人值守的意义在哪里呢？」

Their brakes were never about doing too much. They were about direction: pushing on without rethinking (「如果方向错误的话，你走的再多都没有用」), a side line crowding out the main one, and scale put on a base that was not settled yet.

## The rules of a run

- **The goal is the project's goal.** The main line comes first and is carried to the end the user will check. When it is done, blocked, or waiting on a training run or subagents, the run does not stop: from the project's goal, pick the next thing that you can do yourself, that does not crowd out the main line, and that helps the project most: an experiment, a path ahead explored, a coming choice of the user's worked out as compared results, an issue solved, literature, analysis, whatever serves the goal. After each stretch, look back at the direction before picking the next. A report or a commit is a milestone, not a stop.
- **At the switch,** write the run's goal document in `docs/goals/`, say back in a few lines the goal as you read it, what you will do ahead of their decisions, what waits for them and what would stop the run; ask only what they can settle on the spot; and start on what does not hang on the answer. After 10 minutes without a reply, treat the user as absent.
- **Do ahead whatever would still be a long run after the user's word; only the word itself waits.** The user decides in the morning, and what remains after their word should be quick assembly, never another long run. So what the user decides (the common block, *Who decides what*) still waits, each item prepared to within one word: the options of an open choice all run, drafts of a paper or an outward report written in the likeliest versions with their figures, the branches of a change of direction explored. What is small and can be undone you do and report afterwards, with the reason and how to undo it (*Done ahead and reported*). What the user then refuses is not done again.
- **The one stop.** Stop only when everything left hangs on a decision of the user's and doing it first would likely be wasted; before deciding that, re-read `docs/goal.md`, the to-do list and the open issues for what else serves the goal. Then the goal document says so and the user is notified on their phone, with the project and what waits. Waiting is not this stop: when only the end of a training run or another job is left, note in the goal document what is awaited and end the turn with a way back set (*Keeping the run alive*), without notifying.
- **A turn ends only with a way back.** Do not end a turn on "next I will do X": do X. End a turn only with background work that will call you back, or at the one stop, and end it with one line of state: what was just done, what comes next, what was queued for the user.
- **The record is the goal document.** After each step append what was done, decided or met, how it was handled and why, and keep its list of what waits for the user current; it is where a resumed session picks up. A conflict or an anomaly met in the run goes on that list with a proposed handling.
- **A batch that spends at scale** (the common block's guardrail) is announced in the goal document; it then runs where the resources the user gave for the round cover it and nothing it rests on is undecided, and waits for the user otherwise.
- **When the user is back,** give first a brief that needs no context (what was done, the state now, what you decided for them, what waits), then the questions, one at a time.

## The goal document

One file per run: `docs/goals/<YYYYMMDD>-<topic>.md`, in Chinese (the user may read it; a later session will). It is written at the switch and kept current until the run ends, and stays as the run's record afterwards. Its first line says whether the run is on: `状态：进行中（<开始时间>）`, and at the end `状态：已结束（<时间>；用户：「…」）`. Its parts:

| Part | What it holds |
|---|---|
| 状态 (the first line) | Whether the run is on: `进行中` with its start, or `已结束` with the time and the user's words that ended it |
| 用户的话 | What the user said for this round, whole: the task, the background, the resources, the limits |
| 目标 | The goal as you read it, tied to `docs/goal.md`: the main line and the end the user will check |
| 回来时要看到的 | What the user should find: the main result; the paths explored, each with its result, compared; the options prepared for the choices that are theirs. Where the task is exploration, this is the completion goal: the attempts this round is to make and what each should show. No metric is invented for it |
| 往前做的 | What you will do beyond the main line, in the order of its worth to the project |
| 照哪些约定做 | The references and the user's skills this round's work will follow, named: a survey names the literature reference and the paper skills, a report the reports reference. The user has had to remind agents of a skill at the start of a run (「我是怕你忘记」); naming them here answers that before it is asked |
| 等用户的 | What waits for their word, kept current through the run |
| 收尾 | What is done before the one stop, and when the user ends the run: the work committed, the to-do list and the other records brought current, what ran on a server fetched back, checked and the server cleaned, temporary files cleared |
| 记录 | One line per step, appended |

The two parts whose form matters, each with one filled row (invented):

```markdown
## 等用户的

| 事 | 准备到什么程度 | 用户说了之后要多久 |
|---|---|---|
| 两种损失选哪个作主结果 | 两种都训完、同一批病例上评过，对比表和每种 6 例的图在 `reports/20261111/loss-choice/` | 选完改一行配置、重出一张表，约 10 分钟 |

## 记录

- 01:40 · 边界损失的训练在第 3 轮发散 · 学习率减半重跑，旧的那次留着没删 · 发散发生在预热结束的那一步，像是步长问题不是损失本身 · `experiments/20261110-boundary-loss/runs/20261111-0140.json`
```

The record is for the agent that resumes, more than for the user: 「你合理规划记录好，我不会看，是 agent 看」. The brief on their return is what they read.

## At the switch

What you say back has the four parts *The rules of a run* names, a line or two each, in the chat: the goal as you read it; what you will do ahead; what waits for them; what would stop the run. This is their one chance to correct the scope before they leave; the one time it was done well, the user widened the scope within two minutes.

Your questions go as one numbered list: only what their message left open and they can settle on the spot, or what only they can open in the coming hours (a login that will expire, a permission).

With the say-back, give the user the `/goal` line to paste, whole, in a code block (*Keeping the run alive* has the line and what is known about it).

## Done ahead and reported

The common block's guardrail on installs leaves the unattended run to this document. These you do during a run and report afterwards, with the reason and how to undo it: reinstalling a tool or a skill; a small system install on this machine that one command undoes; training on any of the project's training servers, also one the user did not name for this round; trying, beside what a written rule asks for, a way you judge better, with both results kept and the rule named in the report (never in place of what the user decides or of a guardrail). Wide uninstalls, wide deletions and wide changes of configuration wait; cleaning a server of what the run itself put there is not one of them.

## Keeping the run alive

A run ends in ways the task does not show. The block's rule is that a turn ends only with something that will call the main agent back, or at the one stop. What is known about the ways a run dies, as dated hints (Claude Code, 2026-11-10; another harness may differ, and these change with versions):

| What ends it | What was seen |
|---|---|
| All work handed to subagents or a training run | The main agent is called back when a background task of its own finishes; nothing calls it back for a job on a remote server unless something local is watching it |
| The 5-hour usage limit | The session waited and resumed by itself after the reset (seen once, 2026-11-10) |
| The weekly limit, a machine restart | Nothing resumes. The state is in the goal document, so the user's 「继续」 is enough |
| `/goal` | A check after every turn that sends the agent back to work while a condition is unmet; a turn that ends with a subagent or a background command still running is judged only once they return. Only the user can set it: when the goal document is written, give them the whole line in a code block to paste, with the completion condition written in the line itself (the judging model sees the conversation, not files). First used 2026-11-10 in this form, still being tried: `/goal Unattended run; the goal document is <path>. NOT met, and work continues, unless the conversation shows (a) a message from the user that ends the run, or (b) Claude's latest message has a section "没有用户就做不下去了" that lists every remaining piece of work, the decision of the user's each hangs on, that the options for each are prepared, and that docs/goal.md, the to-do list and the open issues were re-read in this turn. Not reasons to stop: an item finished; a report or commit written; Claude says what it will do next; a question pending; subagents still running.` |

At the one stop, the message that stops carries the section the line names, with its four items: the judging model reads the conversation and nothing else.

## Notifying the user

Only at the one stop. Bark, with the settings in `~/.config/bark/config.json` (`server_url`, `device_key`): a POST of JSON to `<server_url>/push` with `device_key`, `title` (the project, and that the run stopped), `body` (what waits, in a line or two), `group` (`how-we-work`). You send it, before the message that stops.

## When the user is back

*The rules of a run* gives the order: first the brief, then the questions one at a time. The brief is in the chat, in Chinese, with the names the user uses, and says: what was done; the state now, including what is still running and until when; what you decided for them, which they may overturn; what waits. A report of the night's results, where the round calls for one, follows the reports reference.
