# Auto memory 更新指南

这份文件供下一次更新 Claude Code Memory 提示词时使用：记录我们对原文的适配、用户意图和已讨论的取舍，让接手者不必重走整段对话。它是维护背景，不是每次会话都要加载的执行指令。下列准确文字可用于复原本次版本；迁移到新原文时按意图调整，不机械重放。

当前生效文本在 [AGENTS.md](AGENTS.md)。本指南以用户于 2026-09-19 确认的提交 `238b36a37cad7808383e7ee0b7acc5ebaa409009` 为参照；比较基准是 [Fable 5.1 Memory 摘录](references/auto-memory/fable-5.1-memory-section.md)。以后更新时应保留意图，允许具体措辞随新版改进。

## 原文来源

来源沿用用户此前指定的 `asgeirtj/system_prompts_leaks` 仓库，取自本项目已保存的下载记录，不是从正在运行的模型中提取。

- [Fable 5.1 原始提示词：固定提交](https://github.com/asgeirtj/system_prompts_leaks/blob/c7b2c31df51e64784603f5740a251b445fd88c46/Anthropic/claude-code/claude-code-fable-5.1.md)。这是本次比较与复原的基准；另有 [本地完整存档](references/auto-memory/claude-code-fable-5.1.md)。
- [提示词目录：查找后续版本](https://github.com/asgeirtj/system_prompts_leaks/tree/main/Anthropic/claude-code)。目录内容会变化，下次选定新版本后记录对应提交，不以 `main` 作为可复原的版本标识。
- [Claude Code 官方 auto memory 文档](https://code.claude.com/docs/en/memory#auto-memory)。本次判断依据的是 [2026-09-18 下载的快照](references/auto-memory/claude-code-memory-docs.md)，不是假定当前网页永远不变。
- [用户初稿：固定提交](https://github.com/uxfion/skills/blob/67f357df6f2b60638a39b842d4e8272ab26c141e/agent-instructions/AGENTS.md)。仅在追溯设计来源时查阅，无需将整份旧稿作为更新输入，也不保留额外副本。

提示词来自第三方存档，文件名沿用其命名；不将其称为 Anthropic 官方发布，也不以存档本身证明真实性。获取时间及 [SHA-256 清单](references/auto-memory/SHA256SUMS)见 [来源索引](references/auto-memory/README.md)。Opus 5 也曾用于交叉比较，其 Memory 章节与 Fable 5.1 的实质规则相同。

## 目标与原则

用户最初依据官方文档写了草稿，之后希望以 Claude Code 已调优的 Memory 提示词为底，结合官方文档和初稿中的有用内容，为 Codex 补齐自动记忆。用户看重原文已有的调优成果，因此默认保留原文；这是一项设计取向，并非已经用性能测试证明原文最优。

- **精简、干练、优雅、执行高效。** 不盲目扩大规则，不为每个假设的边界情况增加流程。执行高效包括及时记住、按需读取、避免重复写入和无谓询问，不只意味着字数少。
- **补真实缺口。** 区分模型提示词要求和 harness 已经承担的行为；Codex 缺少的步骤才需要补进来。官方文档描述的每项机制不都要变成提示词。
- **只补 Codex 这一侧。** Claude Code 的记忆管理依靠其原生机制。共用文件不意味着要向 Claude Code 的全局 `CLAUDE.md` 添加同样的补偿规则。
- **保留意图，不固守旧措辞。** 新版已涵盖的补充应合并或移除；不因旧草稿曾写过就恢复它，也不为减少几个词而反复重写已经清楚的规则。

## 相对 Fable 5.1 原文的修改

### 1. 存储位置与跨 harness 共享

原文指定 Claude Code 私有目录，并保证目录已存在、直接用 `Write` 工具写入。当前改为项目根下的 `.memory/`，首次保存时创建，并用通用表述说明跨 harness 共享。

替换原文首段中 `Each memory is one file…` 之前的全部文字为以下独立段落；`Each memory…` 及后面的模板保留，另起一段：

```text
You have a persistent file-based memory at `.memory/` under the project root (the main worktree for Git repositories). These files are shared across agent harnesses. Create the directory when you first save.
```

这是实际共享方式的适配。不要照搬原文的个人绝对路径、目录已创建的假设或 `Write` 工具名；Codex 使用自身提供的文件操作工具即可，无需在提示词中另教一套工具调用方法。

`the main worktree for Git repositories` 不是 Fable Memory 原文的要求，而是为了让 linked worktree 与主工作区共用记忆，意图与当时官方文档的共享行为一致。用户曾担心 worktree 说明复杂化，最终同意保留这一限定，删去 `git worktree list` 等操作细节。以后不要展开成路径发现流程；删除限定前则要考虑是否会分出多份记忆。

### 2. 显式读取索引与按需召回

原文说索引每次会话会被加载；这依赖 Claude Code harness。当前为 Codex 补上启动读取、压缩后有条件重读和工作中按需读取。在存储位置段落与 `Each memory…` 段落之间插入：

```text
At session start, read `MEMORY.md` if it exists; read it again after compaction if it has left context. Use the index to find and read relevant memory files as you work. All memory paths below are relative to that directory.
```

第 5 项也将 `loaded into context each session` 改为 `read at the start of each session`，避免把需主动执行的步骤说成平台自动行为。不要因此要求每次任务扫描全部记忆，或每次压缩后无条件重读。如果未来 Codex 已原生完成这些步骤，应重新判断是否还需补充。

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

这里有三个不同来源：原文提供 `metadata.type` 模板；官方文档快照说明 Claude Code harness 会写入 ISO 8601 `modified`；初稿采用 `metadata.modified`，当前保留此约定。官方文档没有要求这个嵌套位置或必须使用 UTC，Fable Memory 章节也没有时间字段。不要把本项目的约定误称为官方完整格式。

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

复原时将标题 `## Memory` 替换为 `## Auto memory`；段落间保留一个空行。以上操作只生成 Auto memory 章节。要复原整份 AGENTS.md，接上已确认版本中从 `## When executing Python…` 开始的原有后半部分；这部分不是 Claude Memory 原文或本次适配生成的。

2026-09-19 已验证：以存档原文为输入，应用本指南六个文字块及上述替换，生成的 Memory 章节与 `238b36a` 一致；接上该提交未改动的后半部分后，整份文件与当前 AGENTS.md 逐字节一致。整份文件的 SHA-256 为 `a14f80ad97c710484fc00f3e7cc27de4b3b1770aa255b47c68684d23a404e5e7`。这验证了本次基准可复原，不代表未来新版原文可以不经判断直接套用。

## 讨论过但最终没有加入的规则

这些是已作出的取舍，不能因旧草稿或历史对话里出现过就自动恢复。

| 候选规则 | 最终决定与理由 |
| --- | --- |
| 为记忆单独规定申请写权限、重试、失败报告流程 | 不写入。用户起初要求自动保存与明确请求同样处理失败，后来明确认为不应过度规定，交给 harness 的通用权限与失败处理。既不要恢复“自动记忆失败静默跳过”，也不要声称项目内路径在任何沙箱下都保证可写。 |
| `edit AGENTS.md only when asked` | 删除。记忆章节不必另设规则文件编辑政策；当前“记到这里”已表达保存目的地。删除不等于获得任意修改全局或项目规则的授权。 |
| `If you are a subagent, leave memory to the main agent`，或进一步规定子代理只读、主代理写入 | 删除。最初担心子代理忘记已教过的行为，又担心强制所有子代理加载记忆；继续细分会扩大规则。官方所述的上下文继承、主会话记忆加载和子代理独立记忆是不同问题，不可由“不自动加载”推导“禁止读取”。当前不规定所有子代理必读，也不保证子代理只读；按实际任务和 harness 行为处理。 |
| `Do not open other projects' memories, keep a separate store, or commit .memory/` | 整句删除。已有存储位置约定，且当时已核对全局 Git ignore 排除 `.memory/`，不再叠加边界句。此取舍不意味着应读取其他项目记忆或提交私有记忆；换环境时也不能假设全局 ignore 必然存在。 |
| 扩展 Claude Code 的全局记忆规则 | 用户曾明确叫停。后来恢复其原有简短迁移说明，主要依靠 Claude Code 内置机制；本指南不授权再次改写它。 |

## 下次更新怎么做

1. **读这份指南和当前 AGENTS.md。** 本文件记录意图，AGENTS.md 是实际生效文字，Git 保存历史。不要把这份背景全文塞进全局提示词。
2. **获取用户指定的新原文并固定来源版本。** 优先使用用户指定的提示词存档和官方文档，不去逆向已安装的 Claude Code 程序。保留旧基准供比较。
3. **做三方比较：旧原文、新原文、当前适配版。** 只围绕 Memory 章节；同时按需复核涉及的官方机制。先看上游真正改变了什么，再逐项判断本指南中的补充是否仍有必要。新版已吸收的规则不重复添加；新增功能不自动照搬到 Codex。
4. **保留仍有必要的适配和用户偏好。** 用新原文的组织与措辞表达，尽量不增加额外流程。对会改变既有行为或取舍的地方，逐点说明增加、修改、删除了什么及原因，与用户讨论后修改；不要把已经确认的背景全部重新问一遍。
5. **检查最终指令的执行成本。** 是否只读所需内容、及时保存、避免重复写入、只在有实际疑点时询问？是否误把原生机制写成额外义务？不要为了追求最短字数牺牲明确性，也无需专门建立测试或审计框架。
6. **完成仓库版本后再同步全局。** 重写前保留可回退的 Git 基线，不覆盖其他未提交工作；讨论期间修改仓库副本，最终确认后再同步全局 `AGENTS.md` 并检查一致性。只替换 Memory 章节，不连带改动 Python、CLI 规则或 Claude Code 的 `CLAUDE.md`。更新本指南及来源索引中发生变化的事实，不追加每次编辑的流水账。

可以把下面这段交给下一次接手的模型：

> 请按 `agent-instructions/auto-memory-update.md` 更新 Codex 的 Auto memory。先比较存档中的旧 Memory 原文、新版原文和当前 AGENTS.md，只保留仍有价值的适配与用户意图。以原文为底，保持精简、干练、优雅且执行高效；不要扩大到 Claude Code 原生记忆管理。对行为变化逐点解释并与我讨论，确认后修改，完成后再同步全局。
