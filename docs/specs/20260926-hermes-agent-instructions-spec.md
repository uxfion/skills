# Hermes 全局指令 — 设计 spec（2026-09-26 定稿）

> 快照：记录 2026-09-26 定下的设计与理由。现行文字以 `agent-instructions/HERMES.md` 为准；同步方法见根 `AGENTS.md`。

## 1. 目标

让 Hermes Agent（Nous Research，经 Telegram 等消息平台使用）得到和 Claude Code、Codex 相同的全局指令：Auto memory、Python、CLI tools 三节，并接入跨 harness 共享的项目 `.memory/`。调研对象为 Hermes v0.21.4 的源码、本地文档和已存会话（只读）。

## 2. 载体：用 `skills.auto_load` 加载的 skill

Hermes 没有全局 `AGENTS.md`：项目 context file 按会话工作目录查找，而消息平台网关的工作目录固定为家目录，不在任何项目里。可选的常驻位置里，选 auto_load 的 skill：

- 放在 system prompt 的 stable 层，每个新会话全文载入，压缩后仍在；
- `/personality` 挤不掉它（`/personality` 会写进配置、全局取代 `agent.system_prompt`）；
- 和其他手装 skill 一样管理。

代价：改动要到新会话（Telegram 里 `/new`）才生效。

否掉的位置：`agent.system_prompt`（会被 `/personality` 全局取代）；SOUL.md（Hermes 文档说它只放人格）；按需加载的 skill（不保证加载）；插件（要写代码维护）；写进 Hermes 自带的 MEMORY/USER（有字符上限，且 Hermes 要求记忆只放事实、不放指令）；`hermes import-agent`（超出上限的部分直接丢弃）。

进 auto_load 的准入条件：每个会话第一条回复前就需要；模型自己想不到去加载；篇幅短。任务知识仍是按需加载的普通 skill。

## 3. 文件、同步与安装

- **源文件** `agent-instructions/HERMES.md`，与 `CLAUDE.md`、`AGENTS.md` 并列，按 harness 命名。不叫 `SKILL.md`：skills CLI 只认 `SKILL.md`，所以 `npx skills add --all` 不会把它装给其他 harness。Hermes 只在启动时把「工作目录到 git 根」路径上的 `HERMES.md` 当 context file，子目录渐进发现不认它，放在仓库里没有副作用。
- **内容**：
  - frontmatter：`name: agent-instructions`，`description: Global instructions, auto-loaded into every session`。触发靠 auto_load，不靠描述。Hermes 的 skill 索引仍会列出 auto_load 的 skill，并规定“部分相关就必须 `skill_view`”，而 `skill_view` 会把全文再塞进对话一次，所以描述不列具体内容，免得和日常任务对上。“auto-loaded” 与 Hermes 载入时加的标注用同一个词，模型能把两处对上。索引只显示描述的前 60 个字符。
  - `AGENTS.md` 全文原样。
  - 在 Auto memory 第一段之后插入一段以 `**In Hermes**` 开头的文字（§4）。
- **同步**：`AGENTS.md` 改了就重新生成 `HERMES.md`。核对办法：去掉 frontmatter 和那一段后，剩下的内容必须与 `AGENTS.md` 逐字节一致。
- **安装**：复制成 `~/.hermes/skills/agent-instructions/SKILL.md`，在 `skills.auto_load` 加上 `agent-instructions`，然后开新会话；用 `hermes curator pin` 固定。用复制而不用软链：仓库可能在网络盘上，网络盘断开时，新会话会丢掉整份指令。

## 4. Hermes 那一段

```markdown
**In Hermes**, find the project from the files a task works on: a file's project root is the nearest directory enclosing it that holds `.memory/` or, if none does, the root of its Git repository, and session start is when the task first enters that project. A task with no file in a project uses your built-in memory. If the project has no `.memory/` yet, ask the user before creating it, and use your built-in memory until they agree.
```

### 4.1 为什么需要这一段

Auto memory 原文默认 agent 是在某个项目里启动的，Hermes 不是：

- 消息平台上工作目录固定为家目录。system prompt 里没有 project、git root、worktree 这些词，唯一的位置信息是 `Current working directory`。
- Hermes 一律用绝对路径，几乎从不 `cd`，每次临时看路径判断自己在哪。
- Hermes 唯一跟「进入目录」挂钩的机制，是把被碰到的目录里的 `AGENTS.md`、`CLAUDE.md` 附进工具结果。它按目录触发，不在 git 根停下。

所以如果不定义，「项目」会落到任意一层目录上：把工作区的子目录当成项目，读不到工作区的 `.memory/`，还会在错误的层级问要不要新建。

### 4.2 规则的依据

- **先找外层 `.memory/`，找不到才用 git 仓库根。** `.memory/` 在全局 git ignore 里，clone 下来的仓库永远不带它。所以没有 `.memory/` 的仓库，一般是某个工作区里的克隆（临时克隆、嵌套的上游克隆、存档用的上游仓库），它的事实应该记进外层工作区。用户自己的项目在开始工作时就已经有 `.memory/`。
- **和另外两个 harness 落在同一个项目。** Claude Code、Codex 的项目是 git 仓库根，否则就是启动会话的目录。不在 git 里的 `.memory/`，都是当初在那个目录启动 agent 时建的。Hermes 没有启动目录，这条规则替它还原出来。
- **按每个文件找，不按任务找。** 一个任务跨几个项目时，各文件各归各的项目，不去找同时包住所有文件的那一层。
- **新建一定先问。** 只有「外层都没有 `.memory/`、落到 git 根」这一种情况会走到这一步。用户同意之前用 Hermes 自带记忆。
- **位置与措辞。** 这一段插在它修改的句子旁边：第一段的「project root」「Create the directory when you first save」，以及下一段开头的「At session start」。原文一字不动，因为用户不接受改写 Auto memory 原文。沿用原文的词（project root、session start），模型就会把定义套到原句上；「built-in memory」有意重复；整段只写该做什么。

### 4.3 各种情况

| 情况 | 结果 |
|---|---|
| 纯聊天；家目录、配置目录里的文件 | 没有项目，用自带记忆，不问 |
| 有 `.memory/` 的工作区，包括它的任意子目录 | 用该 `.memory/` |
| 工作区里的 git 克隆（临时克隆、嵌套的上游克隆、存档仓库目录下的仓库） | 用外层工作区的 `.memory/` |
| 外层都没有 `.memory/` 的 git 仓库（包括恰好是 git 仓库的配置目录） | 先问，同意才建；之前用自带记忆 |
| 一个任务跨多个项目 | 每个文件各自找 |
| 通过 ssh 在远程主机上的项目 | 和本机一样处理（用户确认） |
| 带工作目录的 cron | 推断会加载这个 skill（源码里只有委派子 agent、后台 fork 等跳过 context file 的 agent 不加载），但没法问用户，所以不会新建；未实测 |
| 委派的子 agent、后台记忆整理 | 不加载 auto_load 的 skill，这条规则管不到（已知局限） |

## 5. 否掉的方案

- 只放一个指向 `~/.codex/AGENTS.md` 的指针：用户要从原文出发，不要把原文抽象掉。
- 原文加一长串条件或典型情况清单，或者把完整的情况表写进 skill：太细，不符合本仓库 skill 的设计原则；交给 Hermes 自己判断，实测后再补。
- 把 Hermes 段落放在文件末尾，单独一个 `## In Hermes` 小节：离它修改的句子太远。
- 把 Hermes 条件改写进原句：违背「不改 Auto memory 原文」，而且以后 `AGENTS.md` 一更新就得手工合并。
- 「任务所在的目录就是项目」：每个目录都可能被当成项目。
- 两个标记哪个先碰到算哪个、或者 git 根优先：嵌在工作区里的克隆会被当成独立项目，而克隆本来就不带 `.memory/`。
- 维护一份项目清单、在每个项目的 `AGENTS.md` 里写提示、写插件算出项目：分别要人维护、要逐个改项目且注入不覆盖工作目录树以外的路径、要写代码。插件留作升级：实测发现文字规则常常判断错时再做。
- 早先曾否掉「向上查找」。2026-09-26 用户说明那只是当时的担忧，要求按最优方案定。本规则里的向上查找，只找已经存在的 `.memory/`。

## 6. 实测项

- 工作区子目录里的文件：Hermes 读外层的 `MEMORY.md`。
- 自带 `.memory/` 的 git 仓库：用仓库自己的 `.memory/`。
- 外层都没有 `.memory/` 的仓库：先问，不擅自新建。
- 纯聊天：不读写任何 `.memory/`。
- Hermes 会不会再对这个 skill 调 `skill_view`：源码里索引不排除 auto_load 的 skill，未实测。
- 带工作目录的 cron：是否真的加载这个 skill。
- linked worktree：未实测。worktree 建在另一个工作区里时，可能用到那个工作区的 `.memory/`，而不是主工作树的。
- Python 一节的「Never invoke `python` directly」会不会让 Hermes 不用它内置的 `execute_code` 工具，以及这是不是想要的。
- 询问会不会太频繁。如果太频繁，再补「用户拒绝过就不再问」。

## 7. 不在本 spec 内

安装到 Hermes、修改 Hermes 配置、清理 Hermes 自带记忆里和本 skill 重复的条目：都属于 Hermes 的系统改动，由用户逐项同意后进行。
