# 交接标准：脚本、agent、用户之间每一处交接怎么写（设计）

> **第二版，设计已定，终审已做（§12），待用户说开始再实施**（2026-11-01）。§10 的七个问题用户都已定；实施中发现要改的，直接改本文。第一版过了三份审阅（忠于来源、对代码的说法、新 agent 能不能照着写），这一版按审阅改过，§11 记了改了什么。来源：issue [20261101-skills-handoff-standard.md](../issues/20261101-skills-handoff-standard.md)，调研在它的参考资料文件夹（`mattpocock-findings.md`、`audit.md`；下文的 PF-7、PZ-13 等编号指 `audit.md` 的条目）。依据：`docs/design-principles.md` §1、§3、§4（2026-11-01 新加的“只约束必须守住的，怎么做交给 agent”）、§5、§6，writing-for-agents skill，以及用户 2026-11-01 的方向：「现在模型能力都是比较强的，所以我们尽量要做到少约束。也不是说不约束，必要的应该约束，但在细节方面应该让 Agent 去把控」。

## 0. 一句话

数据从一个角色交到另一个角色时，必须落成文件、经命令或文件收回；brief 按读者分两处写：派发说明写在 SKILL.md，给主 agent；brief 文件单独一份，给 subagent，硬性要求两项接口（交回什么、怎么记下；完成条件），外加一小段每份都带的规矩（subagent 读不到原则），其余交给 agent 把握。

## 1. 要解决什么

审查了五个 skill 的 73 处交接（详见 issue）：

- 从脚本出发的交接普遍写得好：有交接记录，有一条命令记下答复，有接手的 subagent 能自己检查的完成条件。
- 从 agent 出发的交接普遍弱：identify 派的 judge 和浏览器 agent、识别器之后的 judge、打标签的 subagent、reader 退回重读。输入常只在主对话里，答复没有命令收回，判断结论没有落在文件上。
- 同一类交接写法各异："便宜的 subagent 判断本地文件"有五种写法。
- 主 agent 要知道的和 subagent 要知道的混在一起：有的 brief 把模型、上限写给 subagent 看，派 subagent 的主 agent 反而要去翻。
- §6 的规矩（写入文件夹、只派一层、不碰 git、完成条件）只在一处写全；恢复同一个 subagent 时说什么，哪份文档都没写；Codex 的对应写法不全。
- 11 处文档和代码、或文档之间对不上（§7）。

## 2. 从 mattpocock/skills 学到的

- **没有统一的 brief 模板。** 每个 skill 自己定格式。统一靠共用的词（角色名、动词），和固定的外壳：框架几项、可选几项、中间自由、一条必写（`.agents/writing-docs.md:15,40,42`）。
- **借来的：**
  - brief 是契约，之前的讨论只是背景（`triage/AGENT-BRIEF.md:3`）；写要的行为，不写怎么做，agent 自己做实现上的决定（同文件"Behavioral, not procedural"）；
  - 措辞越严，越限制 agent 的判断，得到的却很少（tdd 文档 :59）——和用户"少约束"的方向一致；
  - 给指针不给副本，除非接手的 agent 够不着（`code-review/SKILL.md:65`）；
  - 做不完：停下，列试过什么，点名要什么（`diagnosing-bugs:53-55`）；做了一部分：列"还剩哪些"（`wizard`）；
  - 状态在共享的存储里，不在对话里（`software-factory:23`）；输入对接手的 agent 只读；一个工单一个文件，避免并行写冲突（`to-tickets` 文档 :71）；
  - software-factory 设计一处交接时问的五个问题：什么触发、读写什么、接着触发什么、用户在哪里重新介入、怎么防止两次做同一件事（`software-factory:90`）。本方案的索引表和 brief 合起来回答这五问（§5.3）。
- **它警告的：** 接管流程的框架拿走控制权（`README.md:17`）；为填格子而填（`ADR-FORMAT.md:15`，`loop-me:18` "never a checklist"）；在每个 skill 里抄一段文字守则，占 token 又只能靠自觉（`.out-of-scope/subagent-recursion.md:7`）；让受约束的一方自己写豁免（`wayfinder` 文档 :69）。

## 3. 两个极端，和推荐的折中

| | A 只写成标准 | B 全部机制化 | **C 推荐** |
|---|---|---|---|
| 做法 | 原则规定 brief 的各项，各 skill 照着写 | 每处跨角色的交接都由脚本写一条记录，接手的 subagent 用一条命令答复；完成条件处处是 `todo` 清空 | 有数据跨角色时用机制：输入落盘，答复经命令或文件收回；brief 只硬性要求两项接口和一小段固定规矩，其余交给 agent |
| 好处 | 不用改代码 | 最统一，最不靠自觉 | 该硬的地方硬，其余放开 |
| 代价 | 靠作者自觉，会走样：审查里的五种写法就是这么来的 | 每个 skill 加代码；没有数据要传的交接也要建记录，是为想象的问题造机制（§3 原则） | 要分清哪些交接传数据；几处要改代码或流程（§6） |

C 的分界线：**有数据从一个角色交到另一个角色时，数据落成文件，答复经命令或下一步会读的文件收回**（原则 §1 "状态存在文件里"、"一个写入者"）；**怎么判断、怎么操作，交给 agent**（用户"少约束"的方向，mattpocock "写行为不写步骤"）。

**和原则的关系**
- 合：§1（按接手的那一方写：subagent、主 agent 或用户；状态在文件里；一个写入者；做不完要交回）、§3（通用简单；标准打底按任务定制；不为想象的问题造机制）、§6（brief 是契约；给指针）。
- **背离的两处**，用户都已定，已写进原则（§10 问题 3、4）：
  1. **恢复 subagent**：原则 §1 说下一轮"恢复原来的 subagent，不换新的"。本方案提议加一句：harness 不能恢复时（或恢复失败），派一个新的、给同一份 brief 和记录，因为状态都在文件里，新的也能接着做。已写进原则 §1（§10 问题 4）。
  2. **brief 的框架写进原则**：原则 §6 现在列的是"目标、要的行为、完成条件、范围外、交回什么"。本方案把它改成按读者分两处的写法，已写进原则 §6（§5.5，§10 问题 3）。

## 4. 例子：打标签的 subagent，改前改后

**改前**（PZ-9、PZ-18）：p2z 的交接表写"打标签：你，或者许多篇时交给打标签的 subagent"，brief 是 tagging.md，而那是写给主 agent 自己打标签用的。没写用什么模型、读哪些文件、写到哪里；导入时 subagent 直接改记录文件，主 agent 同时也在改这些文件。

**改后：**
1. 派发说明写在 p2z SKILL.md 的交接表和派 subagent 那一步：接手的是打标签的 subagent（Claude Code `sonnet`，Codex `luna`），最多 10 个同时，因为不上网；每个派约 20 篇；填空项是这批记录的路径和 `read_library tags` 的输出文件；交回的是每篇一个标签文件 `<imp>/tags/<slug>.json`；主 agent 怎么核对：每篇都有文件，`save --dry-run` 显示标签。
2. brief 文件是 `references/tagging-brief.md`（或者 tagging.md 加一节"给打标签的 subagent"）：目标是给每篇选精选标签（curated tags）；输入是记录（只读）、现有标签、tagging.md；产物是每篇一个标签文件，只能写 `<imp>/tags/`；完成条件是每篇都有文件、每个新标签都在文件里标为新的；回报只报例外：新出现的标签、拿不准的论文；规矩：只派一层，不碰 git，不碰网站。
3. `save` 建条目时，把记录里的自动标签和标签文件里的精选标签合起来写（要改 `create_item`）。
4. 库里已有的条目（`found`）不在这一步打标签：`save` 不新建它们，改它们的标签是改现有条目，照 SKILL.md 先给用户看 `file_and_tag --dry-run`、用户点头再写。打标签的 subagent 只给要新建的论文写标签文件。

**结果**：每样东西只有一个写入者（标签文件归 subagent，记录归主 agent），状态在文件里（中断了重来，标签还在），主 agent 读的 SKILL.md 只多一行表。这是 §6 打标签的 a 方案；另外两个方案见那里。

## 5. 标准的部分

### 5.1 brief 按读者分两处：派发说明和 brief 文件

| | 派发说明：写在 SKILL.md 的交接表和派 subagent 那一步 | brief 文件：单独一份，subagent 自己读 |
|---|---|---|
| 谁读 | 主 agent | subagent |
| 讲到什么 | 谁接（角色；Claude Code / Codex 各用什么模型；最多几个同时）；派发时的填空项；交回什么、放在哪、主 agent 怎么核对；恢复时的消息带什么 | 目标；输入（文件路径，先读什么）；**产物**（交回什么、放在哪、用哪条命令或文件记下、只能写哪个文件夹）；**完成条件**（自己能跑、可能不通过的检查）；回报（只报例外：拿不准的、挡住的、发现 skill 有问题的）；规矩（见 5.2） |

- **必写的**：两项接口，brief 文件里的"产物"和"完成条件"，它们是别的步骤要读的，对应原则的"状态存在文件里"和"完成条件要能检查"；加上 5.2 那一小段规矩，那是 subagent 读不到原则、不得不付的代价。
- 其余各项是要讲到的内容，不是必须用的小标题；用得上才写，写成段落也行。**怎么判断、怎么操作，留给接手的 agent。**
- 文件名只固定下一步要读的那几个（接口）；subagent 自己的草稿放哪、叫什么，不规定。文件名里的 `<n>` 是主 agent 派发时给每个 subagent 的批次号，写在填空项里。
- 完成条件要能不通过，而且不必加代码：judge 对自己写的改动文件跑一遍记录命令的预演（比如 `update_item --batch --dry-run`），再核对每件输入在结论文件里都有一行；没有预演的，数行数也行。

### 5.2 subagent 读不到原则，所以 brief 里要带上的

subagent 不读设计原则，原则里的默认规矩不写进 brief，它就不知道。每份 brief 文件的"规矩"里都带：
- 只派一层，自己做，不再派 subagent；不碰 git；自己直接写的文件只放在给定的文件夹（经脚本命令写的记录和日志不算）；
- 做不完：说试过什么、确定了什么、还缺什么；
- 上网的角色另带该 skill 的上网规矩，直接写在 brief 文件里（原则 §6 要求 brief 带上这些规矩）。paper-fetch 的两个上网角色（paper agent、浏览器 agent）共用一份 brief 文件，规矩只写一处，两种任务各占一节。

这几行在每个 skill 的几份 brief 里会重复一点，换来的是每份 brief 自己够用。

### 5.3 交接索引表

每个 SKILL.md 的 *Handoffs* 一节一张表，列统一为：`停点 | 谁接 | brief | 交回什么、用什么记下`（英文写作 `stop | taker | brief | what comes back, recorded by`）。这张表加上 brief，回答 software-factory 的五问：停点是"什么触发"；brief 的输入和产物是"读写什么"；"用什么记下"之后脚本接着跑，是"接着触发什么"；表里交给用户的行是"用户在哪里重新介入"；一个写入者加上脚本跳过已做的，是"怎么防止两次做同一件事"。

### 5.4 对用户的交接

- **运行中的问题**（某篇论文选哪个版本、两个条目是不是同一篇）：攒到任务的自然停顿处，一条消息问完，每个问题带证据和可选的答复；等不了的（验证码、密码）立刻推送。用户的答复用同一条命令记下，标 `--by user`。原来只有 p2z 的 batch.md 这样写，已写进原则 §1。
- **设计决定**：按原则 §5，一次问一个。
- 两者各管什么，已写进原则 §1（§5.5）。

### 5.5 写进设计原则（已写进，2026-11-01）

§1 那份"交给谁、任务、要求、产物、所需文件"的清单不动（它管所有交接，不只 brief）。§6 的第一条换成：

```
- **A subagent's brief is the contract** *(mattpocock: triage)*, written in two places by reader.
  - **The dispatch** sits in the SKILL.md's handoff table and the step that sends; the main agent reads it: the
    role that takes the work, its model on each harness, how many at once; what each dispatch fills in (the
    item, the paths of its records, the pass); what comes back and how the main agent checks it; what a resume
    message carries.
  - **The brief file** is what the subagent reads: the goal; the inputs, by path; the product (what comes back,
    where, the command or file that records it, the one folder it writes); a done-when it can run and that can
    fail; the report, of exceptions only; and the rules it cannot read anywhere else: one level deep, no git,
    what to say when it cannot finish, and for a web role the skill's web lines.
  - The product, the done-when and those rules are always there. Everything else, what is out of scope
    included, is said when it applies, and how to do the work is the subagent's.
```

§1 "What needs the user" 一条补上：

```
In a run, the user's questions are gathered into one message at the run's pause, each with its evidence and
the answers it takes, and the answer is recorded through the same command, by user; only what cannot wait, a
gate or a password, alerts at once. Design decisions follow §5.
```

## 6. 定制的部分：逐处交接怎么改

| 编号 | 现在 | 改成 | 改什么 |
|---|---|---|---|
| PF-7 identify 派的浏览器 agent | "照 paper agent 的 brief"；两种任务混在一起 | 拆成两种：①页面不能直接取（`page_unreachable`）：把 HTML 存到 `<dir>/scratch/pages/<slug>.html`，主 agent 用 `identify --redraft <url> <result> --html <file>` 记下；②只有题目、要靠浏览器搜：还没有结果，也没有 slug，产物是找到的 DOI 或页面地址，写进 `<dir>/scratch/search/<i>.browser.json`（`<i>` 是这个题目在请求里的序号，主 agent 给），主 agent 用 `identify <id>` 记下。会话用 `pf-search-<i>` 或 `pf-<slug>`。`scratch/` 由写它的一方先建 | 文档 |
| PF-5 只有题目时的 judge | `--search` 的候选只在主对话里 | 主 agent 把 `identify --search` 的输出存成 `<dir>/scratch/search/<i>.jsonl`（`<i>` 同上）；judge 每件写一行到 `<dir>/scratch/judge/pin.<n>.jsonl`（`<n>` 是批次号；选哪个、依据）；主 agent 读后跑 `identify`：批量联网的脚本留在主对话里一次跑一个（batch.md） | 文档 |
| PF-6 正式版候选的 judge | 输入是结果文件（已在盘上），但没有答复格式和记录命令 | judge 每件写一行到 `<dir>/scratch/judge/versions.<n>.jsonl`（确认哪个、依据）；主 agent 跑 `--redraft` | 文档 |
| PZ-13 识别器之后的 judge | 没有 brief，产物不明 | 主 agent 把 `recognize` 的输出存成 `<imp>/recognize/recognize.jsonl`；judge 对照 PDF 第 1 页在同一文件夹写两份：结论文件 `verdicts.<n>.jsonl`（每件一行：改 / 没问题 / 拿不准，各带理由）和改动文件 `changes.<n>.jsonl`（只放要改的，因为 `update_item --batch` 遇到空改动整份不写）；主 agent 跑 `update_item --batch` | 文档 |
| PZ-9、PZ-18 打标签的 subagent | 没有 brief；导入时直接改记录文件 | 见 §4：每篇一个标签文件（已定 a） | 文档；`create_item`（a 方案） |
| PZ-17 整理时的 judge | `unknown` 交给你看（organize.md:15 写了），但记在哪没写；怎么分、`<n>` 谁定没写 | 主 agent 把 `lint.jsonl` 分成 `lint.<n>.jsonl`；judge 在 `<scratch>/tidy/` 写结论文件 `verdicts.<n>.jsonl`（每件每个问题一行：改 / 不动 / 拿不准，各带理由）、`changes.<n>.jsonl`、`tags.<n>.jsonl`；附件标题的问题走 *Attachment titles* 那条路，不归它。判"不动"的结论不存，下次照判，报告里归成一组（§10 问题 6） | 文档 |
| PF-15、PF-18 跨轮的 paper agent | 恢复时说什么没写 | 派发说明写明恢复消息：第几轮 + `todo --slug` 列出的记录路径；用户说"跳过"，主 agent 在恢复消息里转告，由 paper agent 答 `skipped_by_user`；第 3 轮的前台窗口写进 brief 的规矩 | 文档 |
| PF-12c、PF-20 给库里文件定标签的 judge | 没指给它结果文件；被拒的库内 PDF 不报 | brief 的输入加结果文件（arXiv 的备注、日期在里面）；被拒的文件由脚本报出（`titles_from_labels` 列出没有标签的文件），不靠回报 | 文档；`titles_from_labels` 小改 |
| PR-4、PR-5 reader | 题目不在 brief 里；没有写入范围、回报、退回办法 | 放进 paper-read 的设计里，按本标准定（§8） | — |
| PZ-6 查重的 judge | 没写 skill 目录、写入范围、只派一层、完成条件；`--key` 说法错（§7） | judge 的 brief 文件带上 `cd <paper-to-zotero 目录>`、5.2 的规矩、完成条件（每个候选都有答复，`prepare` 不再列它为等 judge） | 文档 |
| PZ-24 识别器把条目放进你在 Zotero 里选中的分类 | 没告诉你 | 运行中的问题那条消息里说一句：识别出的条目会先落在你当前选中的分类，之后由 `file_and_tag` 归位 | 文档 |
| PF-3、PF-9、PF-17 paper agent 的几处小缺口 | 下载被监视器归位后主 agent 告诉 paper agent 什么没写（PF-3）；`--start` 再被拒会新开一条页面交接、"答了 blocked 就算完成"在还有别的交接时有歧义、Codex 怎么联系主 agent（PF-9 a–c）；遇到挡住的网站，paper agent 只在最后回报（PF-17） | 都并进 paper agent 的派发说明和 brief 文件：恢复消息里转告归位的文件；brief 写明 `--start` 再被拒的情况和完成条件的歧义；派发说明写明怎么联系主 agent、怎么跟进事件（Claude Code 用 `SendMessage` 和 Monitor；Codex 等用到时再确认）；挡住的网站照常在回报里说，publishers.md 那句"第一次出现就告诉用户"改成"paper agent 回报时" | 文档 |

**打标签怎么进条目（已定 a，2026-11-01）**
- **a（已定，2026-11-01）** 每篇一个标签文件 `<imp>/tags/<slug>.json`，打标签的 subagent 是唯一的写入者；`save` 建条目时连同记录里的自动标签一起写。要改 `create_item`。建条目前就能打，不改导入顺序。
- **b** subagent 写 `tags.<n>.jsonl`，加一条小命令把它并进记录的 `tags`。要加一条命令，记录仍有两个写入者（命令和主 agent）。
- **c** 条目建好后用 `file_and_tag --batch` 打标签，和整理时一样。审阅查出四个问题：建条目前没有 key 可指；`tags` 会整套替换，要改用 `add_tags`；一行出错整批不写；库里已有的条目要用户点头，导入流程里没有这一步。所以不再倾向。

**judge 判"不动"的结论怎么记住**：已定（2026-11-01，用户选 A），什么都不加，见 §10 问题 6。第一版和第二版列过的三个存法（写进 Extra、打标签、存本机文件）都比要解决的问题重，写进 Extra 还可能在导出 BibTeX 时混进稿子的参考文献。

## 7. 文档和代码对不上的地方

| 矛盾 | 处理 |
|---|---|
| reader 用 opus，原则说用会话本身的模型 | 留到 paper-read 设计 |
| `taker` 在记录里按种类写死，SKILL.md 按情况换接手的角色 | 去掉记录里的 `taker` 字段，谁接只在 SKILL.md 的表里写一处；paper agent 的 brief 写明它也答自己那篇论文的标签交接。`todo` 改为按种类列出（要改 `run.py`、`todo.py`） |
| organize.md 写 `--slug <citation key>`，paper-fetch 的 slug 是文件名安全的形式 | 改成"结果的 slug（引用键的文件名安全形式）" |
| judge 必看两页图，图要装了 `pdftoppm` 才有 | brief 写"记录里列了图就看图" |
| vllm-serve 和 paddleocr 对 uv 安装要不要等用户说法相反 | 不在本次范围（另一个会话），记下 |
| reader 核对的题目 brief 里没有 | 留到 paper-read 设计 |
| p2z `import.md` 把 `--key` 写成都可选，`answer.py` 要求 `same`、`pair`、`unknown` 必须带 | 改 `import.md` |
| p2z 记录说明对 `answer.py` 的写法；`same_as` 主 agent 和 `answer.py` 都写；`answer.py` 整份重写记录文件，主 agent 同时改记录就会丢改动 | **已定（2026-11-01，用户选 A，按原则 §5 先指出更根本的做法）**："库里哪个条目是这篇论文"的所有判断（judge、主 agent、用户）都只用 `p2z.py answer` 记在交接文件里；记录文件不再存 `same_as`、`distinct_from`，用到的脚本（`p2zlib/run.py` 三处、`p2z.py` 一处）从交接文件读；同 DOI 多个条目也写同样的交接文件，原来单独的 `duplicates` 流程去掉；`answer.py` 不再写记录文件。subagent 从此不碰主 agent 的记录文件；"把答复抄进记录"这一步省掉。说明按实际重写 |
| subagent 上限两种算法 | 按原则：上网的最多 5 个，只看本地文件的最多 10 个；两个 skill 写法统一 |
| `discovery_template` 的搜索步骤 SKILL.md 没写 | 补进 SKILL.md *Ready* |
| p2z 的 judge 定义说"只读 brief 指定的文件"，而新的完成条件要它跑记录命令的预演（会读本机 Zotero） | judge 的定义改为：只读 brief 指定的文件，可以跑记录命令的 `--dry-run` |
| paper-read 等 `unchanged`，脚本打印 `skipped` | 留到 paper-read 设计 |

## 8. 范围，和不做的

- **改：** paper-fetch、paper-to-zotero。设计原则的改动已经写进（§5.5）。
- **paper-read：** 它的设计还没定，交接放进它的设计里一起定，直接按本标准写。
- **vllm-serve、paddleocr：** 审查发现的问题记在 `audit.md`，它们是另一个会话的范围，在那边按同一标准改（用户 2026-11-01 选 A）。
- **不做：** 不加统一的交接库或模板代码（每个 skill 各自安装，原则 §3 不许共用库）；不给没有数据要传的交接建记录；不规定 brief 的小标题和篇幅。

## 9. 完成条件

- §6 每一行改完，每行能指出一处可检查的差别：新 brief 文件有产物和完成条件，填空项写在 SKILL.md，数据文件的路径写明。
- §7 每条矛盾解决，或写明留到哪里。
- **新 agent 试读**：每份新 brief 交给一个没有背景的 subagent，只给 brief 和填空项，让它写出第一步要做什么、交回什么；它要猜的地方都改掉。
- paper-fetch 的 SKILL.md 变短（审阅估计净少约 35 行）；paper-to-zotero 的略长，长在主 agent 派 subagent 的那几行（打标签、识别器之后、整理时的 judge），每处一两行。
- 两个 skill 的测试都通过；改了代码的几处（`create_item` 读标签文件；查重结论只记在交接文件里：`answer` 不再写记录、`p2zlib/run.py` 和 `p2z.py` 从交接文件读、`find_in_library` 为同 DOI 多个条目写交接文件；去掉 `taker`；`titles_from_labels` 列出没标签的文件）各有测试；改动用 writing-for-agents 过一遍。
- 改流程的地方（打标签、查重结论的新记法）用一次真实的小规模导入验证：在 `tmp` 分类里导入两三篇，事先告诉用户，结束后把测试条目移进回收站。

## 10. 要用户定的（一次问一个，按先后）

1. ~~**范围**~~：已定（2026-11-01，用户选 A）：只改 paper-fetch、paper-to-zotero；paper-read 放进它的设计里；vllm-serve、paddleocr 留给那边的会话按同一标准改。
2. ~~**机制的深度**~~：已定（2026-11-01，用户选 C）：有数据跨角色时用机制，brief 只硬性要求两项接口加一小段固定规矩，其余交给 agent。
3. ~~**写进原则的文字**~~：已定（2026-11-01，用户「可以」），§5.5 两段已写进设计原则 §6 和 §1。
4. ~~**恢复 subagent**~~：已定（2026-11-01，用户选 A）：默认恢复原来的（Claude Code 用 `SendMessage`）；恢复不了时派新的，读同一份 brief 文件和记录、先看试过什么。Codex 等用到时再确认。已写进原则 §1。
5. ~~**打标签怎么进条目**~~：已定（2026-11-01，用户选 A）：每篇一个标签文件，打标签的 subagent 是唯一的写入者，`save` 建条目时合进去（改 `create_item`）。
6. ~~**判"不动"的结论怎么记住**~~：已定（2026-11-01，用户选 A）：什么都不加，judge 每次照判，整理报告把"又一次判为不用改"的归成一组。为省几次便宜的重判造机制不划算；哪天真觉得重复得烦，再考虑只整理上次之后变动过的条目（按条目版本号）。
7. ~~**查重的结论由谁写进记录文件**~~：已定（2026-11-01，用户选 A）：都只记在交接文件里，记录文件不再存，见 §7。

## 11. 第二版改了什么（按审阅）

- brief 按读者分两处（派发说明、brief 文件）（两位审阅者都提出，审查里写得最好的 paddleocr 正是这样）；"Taker"挪到派发说明。
- 框架变轻：只有产物和完成条件必写，其余是要讲到的内容、不是小标题；回报只报例外；删掉"Resume"一项（恢复消息归派发说明）；固定的文件名只限下一步要读的。
- 补上 subagent 读不到的规矩（只派一层、不碰 git、写入文件夹、做不完怎么说），上网的规矩写进 brief 文件，不只给指针（原则 §6）。
- 判断结论落成文件：结论文件和改动文件分开（`update_item --batch` 不收空改动）；"拿不准"不再只在回报里；被拒的库内文件由脚本报出。
- 打标签改倾向 a（c 的四个问题见 §6）；判"不动"的 a 补上要改 lint、Extra 整段重写、BibTeX 导出待测。
- identify 的浏览器 agent 拆成两种任务（只有题目时没有 slug，记录命令也不同）；`scratch/` 由写它的一方建。
- 对用户的交接分清"运行中的问题"和"设计决定"（第一版把"攒成一条消息"错算到原则 §5 头上）。
- §1 的清单不再挪到 §6（它管所有交接）。
- "和原则没有背离"改为如实列出两处背离，都交用户定；删掉"Codex 的问题也就不存在了"（`SendMessage`、Monitor 的对应写法仍要补）。
- `taker` 改为只在一处写；`same_as` 两个写入者的问题，用户选了更根本的做法（判断只记在交接文件里）。
- 必写项说一致：两项接口加一小段固定规矩（第二版初稿在 §5.2 和其余几处说法不一）。
- 补上审阅指出漏掉的 PF-3、PF-9、PF-17、PZ-6、PZ-24；p2z 的 SKILL.md 改为预计略长；judge 的定义允许跑预演。
- 加入 software-factory 的五问，作为检查索引表和 brief 是否完整的依据。
- 问题的顺序改为先问机制深度，再问原则文字。
- PZ-17、PF-6 的"现在"一栏按审阅改正。

## 12. 终审改了什么（2026-11-01，实施前）

- 文件命名分清两种编号：题目在请求里的序号 `<i>`（identify 只给题目时），和 subagent 的批次号 `<n>`；原来两处都写 `<n>`，会混。浏览器搜题目的产物改名 `search/<i>.browser.json`，不和 `--search` 的输出 `search/<i>.jsonl` 撞名。
- 补齐没写目录的产物：`versions.<n>.jsonl` 在 `<dir>/scratch/judge/`；识别器的输出和 judge 的两份文件在 `<imp>/recognize/`；结论文件统一叫 `verdicts.<n>.jsonl`。
- 补上设计上的一个漏洞：库里已有的条目不在导入时打标签（改现有条目要先给用户看预演），打标签的 subagent 只给要新建的论文写标签文件。
- 整理时判"不动"不存（问题 6），所以 lint 不用改，那一行改为只改文档。
- `<n>` 由主 agent 派发时给出；"只写给定的文件夹"说清是 subagent 直接写的文件，经脚本命令写的不算。
- Codex 的写法不再自己编：派发说明只写 Claude Code 的做法（`SendMessage`、Monitor），Codex 等用到时再确认（用户：「其他的后面使用了再确定好了」）。
- 完成条件里过时的一句（`answer` 无交接文件时写 `same_as`）按问题 7 的定法改正；真实验证写明在 `tmp` 分类里做、事先告诉用户、事后清理。
- 交接表的英文列名定下来，免得两个 skill 各译各的。
- 状态、背离、§5.4、§5.5、§8 里"待定""草稿"的说法改为已定、已写进原则。
- 原则 §1 "状态存在文件里"的后半句收窄为"中断后重跑的运行能找到已做的判断"，和问题 6 不再冲突（用户选 A）。
