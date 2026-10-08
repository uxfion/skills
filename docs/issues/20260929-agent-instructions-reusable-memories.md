# agent-instructions 改进清单

用户 2026-09-29 的原话：「我的意图就是想把每个项目里经常用到的这些 memory 整理起来、维护起来，然后有必要的话写进 agent instruction 里面。这样就不用经常在项目中，去引用其他项目中比较好的一些记忆，能够统一管理且自己可以进行迭代。」

本文件的主体是把各项目反复用到的记忆收拢成主题，逐个决定要不要写进全局指令（`agent-instructions/`）。目前只收集整理，还没起草措辞（「现在只是收集和整理，并没有草拟和修改」）。

背景：09-29 读了 Claude Code 和 Codex 有对话记录的所有项目的记忆，约 100 条。同一条规则已经在几个项目里各存一份、各自改写，开始分叉：git 规则有 4 份；选项编号一处写 1234，另一处写 ABC/abc/123。全局指令现在只有 Auto memory、Python、CLI tools 三节。来源代号、状态流转和判断标准见文末"维护约定"。

## 总览

| # | 主题 | 建议 | 待你定 | 状态 |
|---|---|---|---|---|
| 1 | git：提交、推送与分支 | 上升 | — | 候选 |
| 2 | 按读者选语言 | 上升 | — | 候选 |
| 3 | 何时自己定、何时问、怎么问 | 上升 | 决定 2 | 候选 |
| 4 | 授权范围 | 上升 | — | 候选 |
| 5 | 只读检查不留写入 | 上升，改现有 Python 节 | 决定 4 | 候选 |
| 6 | 求证纪律 | 上升，先压成几句 | — | 候选 |
| 7 | 受阻时换途径、请用户协助 | 只上升通用部分 | 决定 3 | 候选 |
| 8 | 并行子 agent | 上升，措辞中性 | — | 候选 |
| 9 | 引用用户原话保持原文 | 只上升逐字引用 | 决定 7 | 候选 |
| 10 | 给别的仓库的东西先本地起草 | 上升 | — | 候选 |
| 11 | 自用项目不管许可证 | 上升，写清前提 | — | 候选 |
| 12 | 讲解方式 | 上升，写成通用句 | 决定 5 | 候选 |
| 13 | advisor 时机 | 不上升 | 决定 6 | 候选 |

## 待你决定

按对起草的影响排序；每条附我的建议。

1. **规则写进全局后，各项目里的原记忆怎么处理。** 建议：只重复全局指令的删掉，项目特有的部分留下并改短；删除按项目逐个问你。理由：Claude Code 的记忆规则本来就不存 CLAUDE.md 里已有的东西；副本留着会继续分叉。
2. **选项编号。** 建议用 ABC/abc/123：这是 09-28 的偏好，比 1234 那条（09-20）晚，而且当时你说「记住我的偏好」。`fin:plain-numbering` 随后改掉。
3. **受阻时的回退梯子（第 7 节）。** 09-21 你否决过把它放进全局。建议只上升通用的一半，OpenCLI、浏览器的具体顺序留在 skill。
4. **Python 节的一次性写法加 `--no-project`（第 5 节）。** 09-28 你说暂不改、以后提醒。建议这批一起改：现有写法在有 `pyproject.toml` 的目录里会建 `.venv`，是指令本身的缺陷。→ 已定（10-07）：单独改，只加 `--no-project`，见 [20261007-uv-python-no-project-fixed.md](20261007-uv-python-no-project-fixed.md)。
5. **讲解方式（第 12 节）。** 建议写成通用句，不写你的专业背景，公开仓库里就没有个人画像。
6. **advisor（第 13 节）。** 建议不上升：Claude Code 的系统提示已经要求动手前、卡住时、完成前调用，当初纠正的"终审太晚"已被覆盖；Codex、Hermes 没有 advisor。
7. **用户原话记录（第 9 节）。** 建议只上升"引用你的话要逐字"；"所有思路都记下来"留在想法系统里。

## 主题

每节固定顺序：要点（规则说什么，概括，不是定稿措辞）· 来源 · 为什么要写 · harness 现状 · 张力或待定 · 状态。上升的规则默认同时进 `CLAUDE.md` 和 `AGENTS.md`，例外在节内写明。

### 1. git：提交、推送与分支

- 要点：到里程碑自己 commit，一件完整的事一次；小改动留在工作区，跟下一次里程碑一起提交，也不专门问；push 和任何对外发布必须用户当轮明说，任务里说过"上 GitHub"不算；简单的个人项目直接在 main 上做。
- 来源：★`skills:commit-at-milestones`、★`skills:only-push-on-explicit-instruction`、★`wx:only-push-on-explicit-instruction`、`fin:commit-granularity`、`tmp:git-commit-milestones-push-on-request`（合并版，最全）、`skills:simple-project-main-branch`
- 为什么：3 个项目纠正 5 次以上，两个方向都有：提交太碎，该提交时不提交。
- harness 现状：Claude Code 写的是 "Commit or push only when the user asks. If on the default branch, branch first"，提交和分支两点都和用户偏好相反，不写每个新项目都会重犯。Codex、Hermes 待核实。
- 状态：候选

### 2. 按读者选语言

- 要点：对话用中文，长时间调工具后也不漂；给用户读的文件用中文；给 agent、harness 读的用英文，其中引用用户的话保持中文；改已有文件沿用它原来的语言。
- 来源：★`skills:language-by-audience`、★`wx:language-by-audience`、`tmp:communication-chinese-options`（文件语言一条）
- 为什么：两个项目纠正过；漂移发生在读完英文子 agent 报告之后。
- harness 现状：都没有。
- 状态：候选

### 3. 何时自己定、何时问、怎么问

- 要点：
  - 何时问：只在真定不了、或方向需要用户定时才问；其余自己选最好的，说明理由。反馈逐条判断采纳、改形还是不采纳，三类都报告。用户以前的否决是当时的担忧，不是硬约束：先按证据找最优，再说明它触及哪条旧担忧。别因个别事实把整体设计拉保守。
  - 怎么问：给带推荐的选项；一次只问一个，按依赖顺序；核心问题问得直白，用户表了态就照办；编号见决定 2。
- 来源：`skills:ask-only-when-undecidable`、★`skills:own-judgement-on-feedback`、★`skills:past-constraints-not-binding`、`tmp:design-boldly-not-from-single-facts`、`tmp:communication-chinese-options`（选项、一次一问、编号）、`fin:plain-numbering`
- 为什么：爱问、全盘采纳反馈、拿旧否决当约束、一次抛多个问题、绕着推自己的推荐，都被纠正过。
- harness 现状：Claude Code 的 AskUserQuestion 说明有 "only when you are blocked on a decision that is genuinely the user's to make"，部分覆盖"何时问"。选项工具只有 Claude Code 有，措辞要中性。
- 张力：`fin:design-before-execute` 要求架构改动先确认整套设计。调和：小事自己定，方向和整体设计交给用户。
- 状态：候选（待决定 2）

### 4. 授权范围

- 要点：给过的授权管到任务结束，范围内不反复问；建目录、移动已有文件、下载或 clone、系统级变更（装包、改系统配置、启停服务、cron）、删除、push 各自要授权，情况紧急也一样；问"能不能"不等于让做；同意一个点不等于开工；只做被要求的那一步（整理记忆不顺手调查，建系统不顺手跑全量内容）。
- 来源：`skills:authorization-carries-over`、`proj:confirm-project-archive-scope`、`skills:capability-question-is-not-a-request`、`fin:design-before-execute`、`fin:system-vs-content-work`、`tmp:memory-tidy-is-not-investigation`、`tmp:no-system-changes-without-consent`
- 为什么：这些纠正分布在 4 个项目。
- harness 现状：Claude Code 有 "confirm first unless durably authorized … approval in one context doesn't extend to the next"，和"授权管到任务结束"有张力；全局写一句正好定义对用户来说什么算 durably authorized。装包、改系统配置未必算"难撤销"，要单独写。
- 张力：授权管到任务结束 vs 不同动作各自确认。调和：范围内的不再问，超出范围的动作类型再问。
- 状态：候选

### 5. 只读检查不留写入

- 要点：只读任务不在任何地方留下写入，尤其是别人的源码目录；一次性 Python 在临时目录里跑，并加 `--no-project`；派子 agent 做只读任务时把这些写进提示。
- 来源：`tmp:readonly-checks-no-writes`
- 为什么：09-28 一个子 agent 只读检查时，在别人的源码目录里跑了 `uv run -`，uv 建了 `.venv` 并重写了 egg-info；实测加 `--no-project` 后不再建环境。
- harness 现状：现有 Python 节的一次性写法 `uv run -` 就有这个问题。这是唯一要改现有节的主题。
- 详情：[20261007-uv-python-no-project-fixed.md](20261007-uv-python-no-project-fixed.md)，10-07 的实测、边界条件和改动方向都在那边。
- 状态：候选（Python 写法已按决定 4 改；「只读任务不留写入」的通用规则还是候选）

### 6. 求证纪律

- 要点：一手来源优先于二手归纳，报告里的归纳结论比原始数据更容易错；两个说法矛盾先解开再下结论；对自己的建议问一句"这步能删吗"；分情况的事实别说成铁律；让用户做的界面操作先核实；用户指定了来源就用它；用户知道的配置直接问，不靠探测推断；调研按主流穷尽、先看官方。
- 来源：`asr:verify-dont-anchor-on-first-source`、`asr:apk-source-is-first-hand-gold-standard`、`wx:verify-wechat-ui-steps`、`skills:use-sources-user-names`、`tmp:ask-user-for-known-config`、`tmp:research-mainstream-first`
- 为什么：6 条来源分布在 4 个项目，每条都有具体的出错现场。
- harness 现状：都没有。
- 待定：条目多、偏思维习惯，要压成几句能照着做的话，否则违背精简。
- 状态：候选

### 7. 受阻时换途径、请用户协助

- 要点（通用部分）：访问被拦或缺信息时，先把能用的途径都试过，再说"做不到"；只有用户能过的关口（登录、验证码、授权），先通知用户、保留现场、给时间，不关页面、不绕开。
- 留在 skill 的部分：OpenCLI 适配器、web read、浏览器的具体顺序，推送通知、等 5 分钟。
- 来源：★`skills:web-access-fallback-ladder`（`tmp` 有副本）、`skills:mpu-sso-login-wait`、`skills:gate-alert-must-push`
- 为什么：09-21 至 09-22 在 paper-to-zotero 里纠正过多次：见到登录页就关、提醒没送到用户、被拦就放弃。
- harness 现状：都没有。
- 以前的决定：09-21 用户否决过把梯子放进全局（`skills:skill-design-conductor-principle` 第 9 条：梯子只设计进 skill，不落到只是用 skill 的人身上）。09-29 用户又挑了它。
- 状态：候选（待决定 3）

### 8. 并行子 agent

- 要点：互不依赖的活并行交给子 agent，最多同时 5 个；每个子 agent 的说明自包含（负责什么、不能碰什么、交回什么）；commit、写用户数据、改 spec 留在主 agent。
- 来源：★`skills:parallel-subagents`（`tmp` 有副本）
- 为什么：用户主动提的要求，并定了上限。
- harness 现状：Claude Code 有子 agent 的使用说明，没有同时数量上限；三个 harness 的子 agent 机制不同，措辞要中性。
- 状态：候选

### 9. 引用用户原话保持原文

- 要点：记录或引用用户的话（issue、spec、记忆、交接）时逐字照录，附上当时的背景；提议和用户原话不一致时明说。
- 来源：`tmp:user-thought-trail`；`skills:issue-draft-workflow` 和 `skills:language-by-audience` 里也有"原话照录"的要求
- 为什么：设计想法系统时两次偏离用户的原设想，都是回头查原话才拉回来。
- 状态：候选（待决定 7）

### 10. 给别的仓库的东西先本地起草

- 要点：要进别的仓库的 issue、文档改动，先写在当前项目，用户确认后再复制过去或在那边引用；"可以提 issue"只是允许起草。
- 来源：`tmp:draft-locally-before-other-repos`
- 为什么：纠正过一次（09-28），但写到别的仓库风险高。
- 状态：候选

### 11. 自用项目不管许可证

- 要点：自用、不公开的项目，别人的代码和文字可以直接吸收，注明出处；要公开的项目另问用户。
- 来源：★`wx:licenses-not-a-constraint`（`tmp` 那份多写了适用范围）
- 为什么：用户在两个项目里各说过一次。
- 状态：候选

### 12. 讲解方式

- 要点：用户问基础概念时，先用大白话和比方把概念本身讲清，一次一个点；实现细节等用户追问；同一个问题再问时，复用上次的讲法。
- 来源：`fin:user-financial-novice`、`tmp:user-home-network-explanations`、`wx:user-is-wx-cli-user`
- 为什么：两个项目里纠正过先讲实现、术语堆叠。
- 状态：候选（待决定 5）

### 13. advisor 时机

- 要点：先写出具体方案再请 advisor 审，需求变了重新送审；完成前的终审只是最后检查。
- 来源：★`skills:consult-advisor-on-key-decisions`、★`wx:consult-advisor-on-key-decisions`（`tmp` 也有副本）
- harness 现状：只有 Claude Code 有 advisor，它的系统提示已经要求 "Call advisor BEFORE substantive work"，卡住时、完成前也调用。如果上升，只进 `CLAUDE.md`。
- 状态：候选（建议不上升，待决定 6）

## 不上升

| 记忆 | 原因 |
|---|---|
| ★`skills:memory-save-judgment`（`tmp` 有副本） | `AGENTS.md` 的 Auto memory 段已经写了；Claude Code 的记忆由 harness 管，按设计不往 `CLAUDE.md` 补 |
| `skills:memory-dir-is-not-file-storage` | 属于 Auto memory 段，要加按 `auto-memory-update.md` 走 |
| `skills:issue-draft-workflow` | 已在本仓库根 `AGENTS.md` |
| `skills:lean-claude-md-preference`、`explicit-python-c-prohibition`、`instruction-wording-workflow`、`harness-grounded-instruction-adaptation`、`skill-design-conductor-principle`、`norms-are-living` | 讲怎么写指令和 skill，留在本仓库 |
| `tmp:hx90-host-environment`（时区陷阱、同步目录）、`skills:paper-access-environment` | 个人环境，公开仓库不能写；可以只写进本机的全局文件 |
| `wx` 的只读原则和版本号规则、`fin` 的项目边界等 | 只属于某个项目 |

## 相关：走 Auto memory 流程的两条

- 临时工作区另有一份待用户确认的草稿：Hermes 读不到网关工作目录以外项目的 `AGENTS.md`。
- 同一处还有一条用户已决定暂缓的：让 Hermes 把项目知识写进 `.memory/`。
- 两者都改 `HERMES.md` 的 Hermes 段，按 `auto-memory-update.md` 走；用户确认后各记成一个 issue 文件。

## 维护约定

- **判断标准**：所有项目、所有 harness 都成立；不写就会做错（有被纠正的记录，多个项目或多次纠正更有力）；harness 本身没有，或默认做法正好相反；不含个人信息（本仓库公开）。
- **状态**：候选 → 已定（上升 / 不上升）→ 已起草 → 已写入（记 commit）→ 原记忆已处理。
- **新发现一条可复用的记忆**：有对应主题就加进它的来源；没有就新开一节，并在总览加一行。
- **起草**：一次一处，给用户看原文和修改建议；上升的规则同时进 `CLAUDE.md` 和 `AGENTS.md`，再重新生成 `HERMES.md`；Auto memory 节按 `auto-memory-update.md`；措辞按 writing-for-agents。
- **来源代号**：记忆写成 `项目:记忆名`。`skills` 本仓库；`tmp` 用户的临时工作区；`wx` wx-cli；`fin` finance；`proj` 存放克隆仓库的目录；`asr` doubaoime-asr（记忆在旧的 Claude Code 默认记忆目录，不在 `.memory/`）。具体路径记在本仓库的 `.memory/`，不写进公开仓库。★ = 用户 09-29 挑出的 12 条。
- **harness 引文**：Claude Code 的原文引自 2026-09-29 会话的系统提示；Codex、Hermes 的默认行为未核实。
