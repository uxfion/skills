# Auto memory 更新指南

这份文件供下一次更新 Auto memory 指令时使用。它管三个 harness 共用的同一套记忆约定：记录各自的分工、对原文的适配、用户意图和已讨论的取舍，让接手者不必重走整段对话。它是维护背景，不是每次会话都要加载的执行指令。阅读顺序：先看各 harness 的分工和更新步骤；后面依次是原则、现行适配的原文与意图、否掉的规则、来源与核对记录。下列准确文字可用于复原本次版本；迁移到新原文时按意图调整，不机械重放。

当前生效文本：Codex 用 [AGENTS.md](AGENTS.md)，Hermes 用由它生成的 [HERMES.md](HERMES.md)，Claude Code 用 [CLAUDE.md](CLAUDE.md) 的 Auto memory 一节。本指南以用户于 2026-09-19 确认的提交 `238b36a37cad7808383e7ee0b7acc5ebaa409009` 为参照；比较基准是 [Fable 5.1 Memory 摘录](references/auto-memory/fable-5.1-memory-section.md)。以后更新时应保留意图，允许具体措辞随新版改进。

## 各 harness 的分工

三个 harness 共用每个项目根下的 `.memory/`。它们的指令各不相同，这是有意为之；改动前先弄清楚为什么不同。

| Harness | 源文件 → 全局位置 | 记忆机制 | 本仓库补什么 |
| --- | --- | --- | --- |
| Claude Code | `CLAUDE.md` → `~/.claude/CLAUDE.md` | 原生 auto memory：harness 注入 Memory 提示词，会话开始时载入索引，写入时加 `modified`；默认存放在项目外的统一位置 | 只把存储切到项目的 `.memory/`，见下文“Claude Code 的存储切换” |
| Codex | `AGENTS.md` → `~/.codex/AGENTS.md` | 原生记忆有意关闭（用户认为不好用）；Auto memory 一节让它复刻 Claude Code 的自动记忆 | 相对 Fable 5.1 原文的第 1–7 项修改；Codex 在项目里启动，第一次保存时直接建 `.memory/` |
| Hermes | `HERMES.md` → `~/.hermes/skills/agent-instructions/SKILL.md`，并加入 `skills.auto_load` | 没有项目概念：消息平台上工作目录固定为家目录，一个会话里随意切换工作区；另有自带的内置记忆 | `AGENTS.md` 全文，外加一段，见下文“Hermes 的适配” |

用户在 2026-09-26 的说法：「我就是要codex原生记忆关的，因为它那个不好用，然后就去复刻 Claude Code，但是 Claude Code Auto memory是存在一个统一的位置的，没有存在项目下面……Hermes为什么要单独来呢？是因为他没有一个项目的概念」。所以，“新建 `.memory/` 前先问用户”只属于 Hermes；Claude Code 的那次询问是存储切换；Codex 不问。

## 下次更新怎么做

1. **读这份指南和三份源文件。** 本文件记录意图；`AGENTS.md`、`HERMES.md`、`CLAUDE.md` 是实际生效文字；Git 保存历史。不要把这份背景全文塞进全局提示词。
2. **获取用户指定的新原文并固定来源版本。** 新模型发布也是触发点，例如 2026-09-22 的 Opus 5.5。优先使用用户指定的提示词存档和官方文档，不去逆向已安装的 Claude Code 程序。保留旧基准供比较。
3. **做三方比较：旧原文、新原文、当前适配版。** 只围绕 Memory 章节；同时按需复核涉及的官方机制。先看上游真正改变了什么，再逐项判断本指南中的补充是否仍有必要。新版已吸收的规则不重复添加；新增功能不自动照搬到 Codex 或 Hermes。
4. **以 Claude Code 的实际机制逐项核对。** 列一张表：机制｜Claude Code 怎么做｜依据（亲见、系统提示词、文档）｜当前文字怎么覆盖｜修改意见，没有就写“无”。只补 Codex、Hermes 真正缺的，并想清楚每个 harness 为什么不同。
5. **保留仍有必要的适配和用户偏好。** 用新原文的组织与措辞表达，尽量不增加额外流程。对会改变既有行为或取舍的地方，逐点说明增加、修改、删除了什么及原因，一次一条，给用户看原文和修改建议，讨论后再改；不要把已经确认的背景全部重新问一遍。
6. **检查最终指令的执行成本。** 是否只读所需内容、及时保存、避免重复写入、只在有实际疑点时询问？是否误把原生机制写成额外义务？不要为了追求最短字数牺牲明确性，也无需专门建立测试或审计框架。
7. **完成仓库版本后再同步全局。** 重写前保留可回退的 Git 基线，不覆盖其他未提交工作；讨论期间只改仓库副本。`AGENTS.md` 定稿后重新生成 `HERMES.md`（核对办法见根 `AGENTS.md`），并复核 Hermes 那一段是否仍与前后两段衔接。最终确认后再同步全局副本：`~/.codex/AGENTS.md`；`~/.hermes/skills/agent-instructions/SKILL.md`（改 Hermes 须用户逐项同意，新会话才生效）；`CLAUDE.md` 只在它自己改动时同步。只替换 Memory 章节，不连带改动 Python、CLI 规则。更新本指南及来源索引中发生变化的事实，不追加每次编辑的流水账。

可以把下面这段交给下一次接手的模型：

> 请按 `agent-instructions/auto-memory-update.md` 更新 Auto memory 指令：Codex 的 `AGENTS.md`，以及由它生成的 Hermes 的 `HERMES.md`；Claude Code 的 `CLAUDE.md` 只在存储切换方式变化时才动。先比较存档中的旧 Memory 原文、新版原文和当前 `AGENTS.md`，再对照 Claude Code 的实际机制逐项核对，只保留仍有价值的适配与用户意图。以原文为底，保持精简、干练、优雅且执行高效；不要扩大到 Claude Code 原生记忆管理。对行为变化逐点解释并与我讨论，确认后修改，完成后再同步全局。

## 目标与原则

用户最初依据官方文档写了草稿，之后希望以 Claude Code 已调优的 Memory 提示词为底，结合官方文档和初稿中的有用内容，为 Codex 补齐自动记忆；2026-09-26 起，同一份正文也接到了 Hermes。用户看重原文已有的调优成果，因此默认保留原文；这是一项设计取向，并非已经用性能测试证明原文最优。

- **精简、干练、优雅、执行高效。** 不盲目扩大规则，不为每个假设的边界情况增加流程。执行高效包括及时记住、按需读取、避免重复写入和无谓询问，不只意味着字数少。
- **补真实缺口。** 区分模型提示词要求和 harness 已经承担的行为；缺少该机制的 harness 缺的步骤才需要补进来。判断缺什么，以 Claude Code 实际替模型做的事为参照：系统提示词、会话中的提醒与拦截、官方文档，并标明哪些亲眼见过、哪些只在文档里。官方文档描述的每项机制不都要变成提示词。
- **只补缺机制的一侧。** Claude Code 的记忆管理依靠其原生机制，`CLAUDE.md` 只负责存储切换；共用文件不意味着要向它添加同样的补偿规则。Codex 与 Hermes 共用 `AGENTS.md` 的正文，Hermes 只多一段。只对某个 harness 成立的规则，不推广到其他 harness。
- **保留意图，不固守旧措辞。** 新版已涵盖的补充应合并或移除；不因旧草稿曾写过就恢复它，也不为减少几个词而反复重写已经清楚的规则。

## 相对 Fable 5.1 原文的修改（`AGENTS.md`，Codex 与 Hermes 共用）

### 1. 存储位置与跨 harness 共享

原文指定 Claude Code 私有目录，并保证目录已存在、直接用 `Write` 工具写入。当前改为项目根下的 `.memory/`，首次保存时创建，并用通用表述说明跨 harness 共享。

替换原文首段中 `Each memory is one file…` 之前的全部文字为以下独立段落；`Each memory…` 及后面的模板保留，另起一段：

```text
You have a persistent file-based memory at `.memory/` under the project root (the main worktree for Git repositories). These files are shared across agent harnesses. Create the directory when you first save.
```

这是实际共享方式的适配。不要照搬原文的个人绝对路径、目录已创建的假设或 `Write` 工具名；Codex 使用自身提供的文件操作工具即可，无需在提示词中另教一套工具调用方法。

`the main worktree for Git repositories` 不是 Fable Memory 原文的要求，而是为了让 linked worktree 与主工作区共用记忆，意图与当时官方文档的共享行为一致。用户曾担心 worktree 说明复杂化，最终同意保留这一限定，删去 `git worktree list` 等操作细节。以后不要展开成路径发现流程；删除限定前则要考虑是否会分出多份记忆。

### 2. 显式读取索引与按需召回

原文说索引每次会话会被加载；这依赖 Claude Code harness。当前为 Codex 和 Hermes 补上启动读取、修改前与压缩后的重读和工作中按需读取。在存储位置段落与 `Each memory…` 段落之间插入：

```text
At session start, read the index `.memory/MEMORY.md` if it exists; read it again before you change it, and after compaction if it is no longer in your context. Each entry points to a file: open it when the entry bears on what you are about to do or ask.
```

第 5 项也将 `loaded into context each session` 改为 `read at the start of each session`，避免把需主动执行的步骤说成平台自动行为。不要因此要求每次任务扫描全部记忆，或每次压缩后无条件重读。如果未来 Codex 已原生完成这些步骤，应重新判断是否还需补充。

2026-09-26 调整。原句为：``At session start, read `MEMORY.md` if it exists; read it again after compaction if it has left context. Use the index to find and read relevant memory files as you work. All memory paths below are relative to that directory.`` 改了四处，依据是 Claude Code 替模型做了、而 Codex 和 Hermes 缺少的机制：

- **路径**：`that directory` 往前既可指 `.memory/`，也可指项目根。`HERMES.md` 在第一、二段之间插入 Hermes 适配后，最近的目录变成了项目根，前一句又是 Hermes 自带记忆（其文件也叫 `MEMORY.md`）。现在第一次用到时直接写 `.memory/MEMORY.md`，并点明它是索引。
- **修改前重读**：Claude Code 的 Edit/Write 工具要求先读过文件才能写，文件被别人改了也会提示；Codex、Hermes 没有这层保护。记忆由多个 harness 共用，拿旧索引整份写回，会冲掉别人刚加的条目。
- **何时打开记忆文件**：Claude Code 自动载入索引，系统提示里还预留了由 harness 挑选相关记忆的召回机制。没有这些时，“relevant … as you work” 太宽，模型读完索引就按默认做事。改为：某条与“接下来要做的事或要问的问题”有关时，打开对应文件；摘要已经说清楚的条目不必打开。
- **措辞**：原句 `if it has left context` 的 left 是“离开”，但可能被读成“剩余”，或读成 NLP 术语 left context（左侧上下文），改为 `if it is no longer in your context`。

复原历史基准 `238b36a` 时用原句。

### 3. 保存时机、独立判断与适用范围

保留初稿中有用的行为：值得长期保留的用户信息及时保存，推断稳定后保存，例行更新保持安静，明确要求记住时写入这里。用户额外强调：

- 用户提供的信息也可能错误或不合理，不能因为“请记住”就放弃判断。发现疑点时先指出问题并给出更合理的建议；用户坚持保留时，记为用户的立场，不冒充已核实事实。
- 一次纠正可能只针对本次回答或行为，不能自动上升为永久规则。明确的长期要求也不必等第二次才记。
- 同一纠正重复出现（两次及以上）应触发反思并及时记住教训，同时记录适用范围。

在四类记忆说明之后、索引段落之前插入：

```text
Save user-provided information worth retaining as soon as it is given; save inferences once settled. Distinguish lasting preferences from one-off corrections. When the same correction recurs, reflect and save the lesson with its scope. Question doubtful claims or requests and suggest a better alternative before saving; if the user insists, record their position without treating it as verified fact. Keep routine memory updates silent. When asked to remember something, save it here.
```

这不是要求每次保存都调查、询问或核验所有信息；只对有疑点的内容提出质疑。原文的 `feedback` 类型已涵盖纠正和确认，不必再发明新分类。

### 4. 修改时间与元数据

在模板的 `metadata.type` 行后增加一行，与 `type` 一样缩进两个空格：

```text
  modified: <ISO 8601 UTC time of this write>
```

在保存时机段落之后、索引段落之前插入：

```text
Set `metadata.modified` on every write to the current UTC time from `date -u +%Y-%m-%dT%H:%M:%SZ`; preserve other metadata fields.
```

这里有三个不同来源：原文提供 `metadata.type` 模板；官方文档快照说明 Claude Code harness 会写入 ISO 8601 `modified`，官方 changelog 在 2.1.214 记有 `Added an ISO modified timestamp to memory file frontmatter`，与文档所述版本一致（更早的 2.1.75 另有 `Added last-modified timestamps to memory files`，未提 frontmatter）；初稿采用 `metadata.modified`，当前保留此约定。时间戳由 harness 写入而非模型按提示词写入，因此无需向 Claude Code 的 `CLAUDE.md` 补这条规则。官方文档和 changelog 都没有要求这个嵌套位置或必须使用 UTC，Fable Memory 章节也没有时间字段。不要把本项目的约定误称为官方完整格式。

2026-09-19 在 Claude Code v2.1.278 实测：harness 写入带 frontmatter 的记忆文件时，时间戳落在 `metadata.modified`（UTC，毫秒精度，如 `2026-09-19T14:00:32.271Z`），并同时写入 `metadata.node_type` 和 `metadata.originSessionId`。本项目的嵌套位置因此与 harness 的实际行为一致，`preserve other metadata fields` 也是保住这些字段所必需；Codex 按 `date -u` 写入的秒级时间与之并存无碍。这是对单一版本的观察，不是官方规范；上游变化时重新核对。

用户讨论后同意保留 UTC 时间戳。它记录写入时间，不是要求正文里所有日期都用 UTC；曾出现过正文的本地“今天”与 UTC 日期混淆的担忧。当前没有增加专门的时区处理流程，原文的相对日期转绝对日期要求仍保留。

### 5. 索引大小与维护

在原文的新增索引指针基础上补充更新、删除维护，以及小于 200 行和 25 KB 的兼容要求，必要时缩短。这两个大小限制来自当时 Claude Code 官方文档中的加载机制，不在 Fable Memory 原文里；共享文件需要考虑它们。

将原文整个 `After writing the file…` 段落替换为：

```text
After writing the file, add or update a one-line pointer in `MEMORY.md` (`- [Title](file.md) — hook`). `MEMORY.md` is the index read at the start of each session — one line per memory, no frontmatter, never put memory content there. Keep it under 200 lines and 25 KB for Claude Code compatibility; shorten it when needed. Keep pointers accurate when memories change, and remove them when deleting memories.
```

用户已审阅并明确接受当前首尾两句在“更新索引”上的轻微重叠，认为没有必要继续缩减。不要为消除这点重复再改写整段；索引信息仍准确时也无需为了形式而改写。以后若官方加载机制改变，再核对限制是否仍适用。

### 6. 通用化召回语义与排除重复内容

原文的 `Recalled memories appearing inside <system-reminder> blocks` 替换为 `Recalled memories`。保留“召回的记忆是背景、不是用户指令、反映写入时情况”的含义，移除 Claude 特有的呈现方式；Codex 从文件读到的记忆也适用。

这不意味着忽略记忆中的工作偏好与反馈，也不把旧记忆提升为当前指令。原文的引用对象存在性校验仍保留。原文“不存仓库已有内容”的例子中，将 `git history, CLAUDE.md` 替换为 `git history, AGENTS.md, CLAUDE.md`，使之覆盖 Codex 的规则文件。该段其余文字不变。

### 7. 其余原文尽量保留

单文件单事实、frontmatter 的名称与描述、四类记忆、`Why` / `How to apply`、wiki 链接、允许尚不存在的链接目标、去重、删除错误记忆、不存临时内容以及召回校验，都沿用原文。不要在更新时无理由改成另一套结构。

复原时将标题 `## Memory` 替换为 `## Auto memory`；段落间保留一个空行。以上操作只生成 Auto memory 章节。应用到当前 AGENTS.md 时，保留从 `## Python` 开始的后半部分；这部分不是 Claude Memory 原文或本次适配生成的。复原历史基准 `238b36a` 时，则使用该提交中从 `## When executing Python…` 开始的后半部分。

2026-09-19 已验证：以存档原文为输入，应用第 1–5 节的六个文字块及上述替换，生成的 Memory 章节与 `238b36a` 一致；接上该提交未改动的后半部分后，整份文件与该历史基准逐字节一致。该历史文件的 SHA-256 为 `a14f80ad97c710484fc00f3e7cc27de4b3b1770aa255b47c68684d23a404e5e7`。这验证了本次基准可复原，不代表未来新版原文可以不经判断直接套用。第 2 节的文字块已于 2026-09-26 调整，复原 `238b36a` 时换回该节注明的原句。

## Hermes 的适配（`HERMES.md`）

Hermes 通过 `skills.auto_load` 加载的 skill 使用这份指令；载体的选择、安装方式和调研证据见 [Hermes spec](../docs/specs/20260926-hermes-agent-instructions-spec.md)。正文是 `AGENTS.md` 全文，唯一的适配是在存储位置段落（第一段）之后插入：

```text
**In Hermes**, find the project from the files a task works on: a file's project root is the nearest directory enclosing it that holds `.memory/` or, if none does, the root of its Git repository, and session start is when the task first enters that project. A task with no file in a project uses your built-in memory. If the project has no `.memory/` yet, ask the user before creating it, and use your built-in memory until they agree.
```

**用户意图。**

- 统一各 harness 的 auto memory，Hermes 是唯一还没接上的。载体选用 auto_load 的 skill，用户的概括是「类似 global instruction，但又是 skills 的形式」。
- 从原文出发，一条条加必要的条件：「先从最原始的版本开始，然后加一些必要的条件」。Auto memory 原文不动：「我不是很喜欢修改原来 instruction 中关于 auto memory 的那一部分」。
- 只写 Hermes 自己判断不了的，典型情况交给实测：「太详细了……hermes应该能自己处理的吧」。
- 有 `.memory/` 就用；没有、需要新建时，必须先问：「如果该文件夹下有 .memory 那一定是要用的。如果没有需要新建的话，一定要询问我，允许了才可以」。这条只属于 Hermes，原因见上文“各 harness 的分工”。
- 放在工作区里的仓库，用外层的 `.memory/`：「一般情况下是要用外层文件夹的 .memory，但如果没有外层文件夹，有可能使用项目的，应该是少数」。原因是 `.memory/` 在全局 git ignore 里，克隆下来的仓库永远不带它。
- 通过 ssh 在远程主机上做的项目，与本机同样处理（用户的选择）。

**为什么这样改。**

- **为什么需要这一段。** 调研 Hermes v0.21.4 发现：它在消息平台上的工作目录固定为家目录，system prompt 里没有 project、git root、worktree 这些词；它一律用绝对路径，几乎从不 `cd`；唯一跟“进入目录”挂钩的机制，即子目录 context 注入，按目录触发，也不在 git 根停下。如果按“任务所在目录”来定义项目，每个目录都可能被当成项目。这正是用户当时的担心：「会不会让Hermes认为每一个目录都是一个project啊？」
- **为什么是“最近的外层 `.memory/`，都没有才用 git 根”。** 比较过的方案有：任务所在目录、git 根优先、两种标记哪个先碰到算哪个、维护一份项目清单、用插件计算。只有这一条同时满足四点：工作区的子目录归工作区；嵌在里面的克隆归外层；只在真正没有记忆的仓库才问；不需要人维护。它也和另外两个 harness 落在同一个项目上：不在 git 里的 `.memory/`，都是当初在那个目录启动 agent 时建的。早先否掉的“向上查找”，用户后来撤回了这个限制：「不要被我之前说的拒绝了点，而错过了最优方案」。
- **为什么按文件、不按任务。** 一个任务跨几个项目时，每个文件各归各的项目，不去找同时包住所有文件的那一层。
- **为什么放在这个位置。** 最初放在文件末尾，单独一节 `## In Hermes`。用户指出：「这不应该放在或者融合在 auto memory 这个 section 吗？」现在放在第一段之后，紧挨它修改的句子：第一段的 project root、“Create the directory”，以及下一段的“At session start”。用加粗的 **In Hermes** 开头，同步时就靠它来定位；原文一字不动。
- **措辞上的考虑。** 沿用原文的 project root、session start，模型会把定义套到原句上。用“it”“that project”指代单个文件及其所属项目，避免被读成“包住所有文件的那一层”。删掉了“not from your working directory”：前半句已经给出正面做法，这半句只是把工作目录拎到模型眼前。“use your built-in memory”前后两处用同一个说法，模型会把它们当成同一个行为。

**同步。** `AGENTS.md` 一改就重新生成 `HERMES.md`，核对办法见根 `AGENTS.md`。Memory 章节每次改动后，都要复核这一段和前后两段是否还衔接：2026-09-26 的路径歧义，就是插入这一段之后才出现的。

## Claude Code 的存储切换（`CLAUDE.md`）

Claude Code 的记忆由 harness 原生管理，默认存放在项目外的统一位置。`CLAUDE.md` 的 Auto memory 一节只做一件事：第一次有东西要存、而记忆目录还不是项目根下的 `.memory/` 时，问用户一次是否切换。同意，就建 `.memory/`，把 `autoMemoryDirectory` 写进 `.claude/settings.local.json`，并按用户意愿搬迁已有记忆；拒绝，就记成一条 `project` 记忆，以后不再问。这个设置下次启动才生效，本次会话剩下的时间直接用 `.memory/`。

这一节不是从 Fable 原文改写来的，Memory 原文更新时不必动它；只有 Claude Code 的存储配置方式变了（比如 `autoMemoryDirectory` 改名），才需要复核。扩展它的规则用户曾叫停，见下表。

## 讨论过但最终没有加入的规则

这些是已作出的取舍，不能因旧草稿或历史对话里出现过就自动恢复。

| 候选规则 | 最终决定与理由 |
| --- | --- |
| 为记忆单独规定申请写权限、重试、失败报告流程 | 不写入。用户起初要求自动保存与明确请求同样处理失败，后来明确认为不应过度规定，交给 harness 的通用权限与失败处理。既不要恢复“自动记忆失败静默跳过”，也不要声称项目内路径在任何沙箱下都保证可写。 |
| `edit AGENTS.md only when asked` | 删除。记忆章节不必另设规则文件编辑政策；当前“记到这里”已表达保存目的地。删除不等于获得任意修改全局或项目规则的授权。 |
| `If you are a subagent, leave memory to the main agent`，或进一步规定子代理只读、主代理写入 | 删除。最初担心子代理忘记已教过的行为，又担心强制所有子代理加载记忆；继续细分会扩大规则。官方所述的上下文继承、主会话记忆加载和子代理独立记忆是不同问题，不可由“不自动加载”推导“禁止读取”。当前不规定所有子代理必读，也不保证子代理只读；按实际任务和 harness 行为处理。 |
| `Do not open other projects' memories, keep a separate store, or commit .memory/` | 整句删除。已有存储位置约定，且当时已核对全局 Git ignore 排除 `.memory/`，不再叠加边界句。此取舍不意味着应读取其他项目记忆或提交私有记忆；换环境时也不能假设全局 ignore 必然存在。 |
| 扩展 Claude Code 的全局记忆规则 | 用户曾明确叫停。后来恢复其原有简短迁移说明，主要依靠 Claude Code 内置机制；本指南不授权再次改写它。 |
| 让 Codex 在新建 `.memory/` 前也先问用户 | 不加（2026-09-26）。Codex 在项目里启动，复刻 Claude Code 的自动记忆；先问只属于没有项目概念的 Hermes。 |
| Hermes 只放一个指向 `~/.codex/AGENTS.md` 的指针 | 不加。用户要从原文出发，不要把原文抽象掉。 |
| 在原文上给 Hermes 加详细条件、典型情况清单或完整情况表 | 不加。「太详细了……hermes应该能自己处理的吧」；典型情况交给实测，只补 Hermes 自己判断不了的。 |
| Hermes 段落放在文件末尾单独成节，或把条件改写进原句 | 不采用。前者离它修改的句子太远；后者违背“不改原文”，而且 `AGENTS.md` 一更新就得手工合并。 |
| Hermes 以“任务所在的目录”为项目，或 git 根优先、两种标记哪个先碰到算哪个 | 不采用。前者会把每个目录都当成项目；后两者会把工作区里的克隆当成独立项目，而克隆不带 `.memory/`。 |

## 原文来源与核对记录

来源沿用用户此前指定的 `asgeirtj/system_prompts_leaks` 仓库，取自本项目已保存的下载记录，不是从正在运行的模型中提取。

- [Fable 5.1 原始提示词：固定提交](https://github.com/asgeirtj/system_prompts_leaks/blob/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code/claude-code-fable-5.1.md)。这是本次比较与复原的基准；另有 [本地完整存档](references/auto-memory/claude-code-fable-5.1.md)。
- [提示词目录：查找后续版本](https://github.com/asgeirtj/system_prompts_leaks/tree/main/Anthropic/claude-code)。目录内容会变化，下次选定新版本后记录对应提交，不以 `main` 作为可复原的版本标识。
- [Claude Code 官方 auto memory 文档](https://code.claude.com/docs/en/memory#auto-memory)。本次判断依据的是 [2026-09-18 下载的快照](references/auto-memory/claude-code-memory-docs.md)，不是假定当前网页永远不变。
- [Claude Code 官方 CHANGELOG：固定提交](https://github.com/anthropics/claude-code/blob/bf7d404e26a5fb6167d21b46c93a2bf6c22ab274/CHANGELOG.md)（2026-09-21 查阅，最新条目为 2.1.278）。核对 harness 行为时文档与 changelog 都要看；机制何时引入、如何变动以 changelog 为准，它逐版本记录变更，文档只描述当前状态。
- [用户初稿：固定提交](https://github.com/uxfion/skills/blob/67f357df6f2b60638a39b842d4e8272ab26c141e/agent-instructions/AGENTS.md)。仅在追溯设计来源时查阅，无需将整份旧稿作为更新输入，也不保留额外副本。
- Hermes 的机制以 [Hermes spec](../docs/specs/20260926-hermes-agent-instructions-spec.md) 记录的 v0.21.4 为准，包括 auto_load 的载入与刷新、网关的工作目录、子目录 context 注入。Hermes 升级后先复核这些，再判断 Hermes 那一段是否仍然需要。

提示词来自第三方存档，文件名沿用其命名；不将其称为 Anthropic 官方发布，也不以存档本身证明真实性。获取时间及 [SHA-256 清单](references/auto-memory/SHA256SUMS)见 [来源索引](references/auto-memory/README.md)。Opus 5 也曾用于交叉比较，其 Memory 章节与 Fable 5.1 的实质规则相同。

2026-09-21 在 Claude Code v2.1.278 的 Fable 5.1 会话中，由模型将自身系统提示词的 Memory 章节与 [Fable 5.1 Memory 摘录](references/auto-memory/fable-5.1-memory-section.md)逐句比对：除记忆目录路径和标题层级（`# Memory`）外文字一致。这是单一版本、单次会话的观察，只说明该基准当时与运行中的提示词相符，不改变存档的第三方性质。

2026-09-26 复核（Opus 5.5 发布后）：上游新增 [Opus 5.5 原始提示词：固定提交](https://github.com/asgeirtj/system_prompts_leaks/blob/a03321b094e65cad2ccd1f5ffb4b309537648834/Anthropic/claude-code/claude-code-opus-5.5.md)，其 Memory 章节与 Fable 5.1 摘录除记忆目录路径外逐字相同；上游 Fable 5.1 原文自 2026-09-05 起未变，与本地存档逐字节一致。官方文档的 Auto memory 一节与 09-18 快照逐字相同，[CHANGELOG 至 2.1.283](https://github.com/anthropics/claude-code/blob/7779afb12e3635f46f56ec823979d68350ae000b/CHANGELOG.md) 没有影响记忆格式或加载的变更。基准不变，未新增存档。
