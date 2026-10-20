# paper-to-zotero v3：第一次真实批量（2026-10-18）

> 已处理：6 条都有了去向（2026-10-18），修复见提交 `f35880b`、`976bd1d`；IEEE 一项单独成为 `docs/issues/archive/20261018-paper-to-zotero-ieee-pdf-link-fixed.md`（2026-10-20 已解决）。

v3 导入部分（`b6a3ce9`）的验收批量，共 7 篇：用户点名 2 篇，agent 另挑 5 篇（用户后来说都保留）。这里记录使用中发现的问题，事后一起整理。

## 1. 链路第 3 步（学校检索系统）被静默跳过

- 来源：使用 · 2026-10-18
- 现场：两篇论文（CBM、Nature Machine Intelligence）在出版社页面显示学校未订阅。第 1、2 遍都只走了开放副本、出版社、接受稿、预印本四条路，检索系统那一步没有走。agent 准备进最后一遍时，用户问：「出版商学校无订阅，但是你有通过链路再去学校的检索系统里查一下吗」，接着补充：「学校检索系统应该是在链路里的，你看一下，之前应该提到过而且应该是失效的」。
- 痛点：上次批量里，出版社无权限的 4 篇有 3 篇是经检索系统在 ProQuest 拿到的；这一步一跳过，论文就直接滑向"无法获取"，还要用户来发现。
- 为什么：
  - SKILL.md 第 3 步写的是"配置里有 `institution.discovery` 才走"。10-13 迁移配置时只迁了代理域名，10-09 批量里用过的 Primo 地址没有迁进来，于是条件一直不成立。
  - publishers.md 写了"没有地址就问用户一次"，但这句只在处理页面时才读到。`ready.py` 报告了 `discovery: false`，agent 开头只把它说成"可选"，没有当成缺口。
  - 跳过的路线不留痕迹：`fetch.jsonl` 只记走过的尝试，报告的"无法获取"一节看起来像是每条路都试过了。
  - 第 3 步是链路里唯一没有脚本的一步，全靠 agent 手工，照着命令往下跑时最容易被落下。
  - 10-13 统一配置时（spec §5.3 只写了迁两个 key 文件），10-09 批量用过的 Primo 地址存在另一个项目的临时脚本里，没有带过来。
  - agent 自己在消息里把检索地址说成"可选，没有就跳过"，与 B#9 的经验相反。
- 用户追问：「为什么会疏忽，原因是什么，是skills的设计问题吗？」
- 方向（待用户定）：
  - A：第 0 步发现没有检索地址，就在第一条消息里问用户；第 3 条路没有地址时说出来，不再静默跳过。
  - B：第 3 条路没走或没查到，也在 `fetch.jsonl` 记一行，报告里能看出来。
  - C：给第 3 条路配脚本（B#9 的 `discover.py` 方向）：按题名查检索系统，列出 PDF 链接和所在数据库；查不到再交给 agent 手工。
- 用户：「可以」（A、B、C 都做），并说「这些比较简单的问题可以直接改吧，不用spec这种复杂的流程吧，记得使用Writing for agents」。
- 已处理（2026-10-18）：A `ready.py` 的 `config.ask_user`，SKILL.md 第 0 步要求第一条消息就问；B、C `fetch.py --via discovery`：按题名搜 Primo，对上同名记录（arXiv 记录排后），打开它的 "Get PDF"，经学校代理进 ProQuest 阅读器取字节；没有同名记录记 `not_in_discovery`，没配地址记 `no_discovery`，有记录没文件就停给 agent。实测 RAD-DINO（NMI 2025）经 ProQuest 取到 PDF，AMIFound 记为 `not_in_discovery`。
- 补充（side agent 提醒，用户转来）：经学校代理批量取全文可能触发下载上限、暂停学校账号。已处理：`fetch.py` 对经学校的全文请求统一留 15 秒间隔（`PACE["institution"]`），publishers.md 写明大批量前先告诉用户。
- 状态：已处理

## 2. citation key 里带 `^`

- 来源：使用 · 2026-10-18
- 现场：Harness^2 建条目后，Zotero 生成的 citation key 是 `xuHarness^2RecursiveAgent2026`。
- 痛点：`^` 在 TeX 里是上标符号，`\cite{xuHarness^2RecursiveAgent2026}` 很可能报错；BibTeX 导出后要用户自己改。
- 方向：`create_item` 读回 citation key 后检查有没有 TeX 特殊字符（`^ _ & % $ # { } ~ \`），有就提出一个去掉这些字符的 key，交给 agent 和用户决定。
- 已处理（2026-10-18）：`create_item.py` 的输出带上 Zotero 生成的 `citationKey`，有特殊字符时给出 `citation_key_hint`；SKILL.md 第 4 步写明问用户后用 `update_item.py` 改。用户同意后，Harness^2 已改为 `xuHarness2RecursiveAgent2026`。
- 状态：已处理

## 3. 批量中途加一篇：用户下载的文件对不上任何记录，之后也不再回头认

- 来源：使用 · 2026-10-18
- 现场：最后一遍时，用户自己下载了一篇感兴趣的论文（HarnessIR，arXiv），说「另外我有一篇比较感兴趣的，你帮我入库」。监控当时把它记为 `left`（对不上任何记录）。agent 给它建了记录之后，监控按"文件名 + md5 只记一次"的规则不再重新核对它，只好手工复制进 `inbox/` 再走 `claim --file`。
- 痛点：用户在批量中途加论文是很自然的事，现在要靠 agent 绕路。
- 方向：新建记录后，`claim --scan` 对之前 `left` 的文件再核对一次（只核对新记录）；或者 SKILL.md 写明"用户下载了不在清单里的论文 → 起草记录 → `claim --scan --retry-left`"。
- 已处理（2026-10-18）：`left` 记录写下当时核对过的记录（`against`），之后只拿新起草的记录再核对一次；batch.md 写明做法。
- 状态：已处理

## 4. 最后一遍的等待借用了门禁等待

- 来源：使用 · 2026-10-18
- 现场：最后一遍逐篇在前台打开时，agent 要等的是"文件到了，或者用户说跳过"。`fetch --wait` 是按门禁设计的：页面网址或标题一变就算通过，超时会记一条 `gate_timeout`。agent 只好传一个永远不会出现的 `--until` 文字，让页面变化不结束等待；用户说"跳过"后再手动停掉等待。
- 方向：给 `--wait` 加一个只等文件的模式（比如 `--for file`），超时不记 `gate_timeout`；SKILL.md 写明最后一遍用它。
- 已处理（2026-10-18）：`fetch.py --wait --for file`：不读页面，只等文件，超时不记日志；SKILL.md 最后一遍改用它，用户说"跳过"就停掉等待、记 `skipped_by_user`。
- 状态：已处理

## 6. 论文自己给模型起的名字没有打成标签

- 来源：用户反馈 · 2026-10-18
- 现场：EchoWDiff（MedIA 2026，`NNJT5DHQ`，2026-10-06 入库）的标签里没有 `EchoWDiff`，而它的摘要写着 "we propose EchoWDiff"。这次批量里 Harness^2、AMIFound、HarnessIR、MFR-Net、PromptIR 都打了。用户原话：「EchoWDiff为什么没有相关的标签，就是EchoWDiff，常用的称呼这篇文章的名字，就像Harness^2，AMIFound，HarnessIR 一样」。
- 为什么：tagging.md 写的是"Common name only when the community actually uses one"、"a model or system people cite by that name"。新论文还看不出"社区用不用"，这句话让 agent 倾向于不打；规则本意其实是"论文自己给模型起的名字"。
- 方向：
  - tagging.md 改成"论文自己给模型、系统或框架起的名字（摘要里的 'we propose X'）就打成裸标签；论文没用过的名字不造"。
  - 第二步的体检（`lint_items`）加一项：摘要里有 "we propose/present/introduce X" 而没有对应裸标签的条目。
- 已处理：给 `NNJT5DHQ` 补了 `EchoWDiff`（以及 `task/Dehazing`）；tagging.md 改为"论文自己给模型起的名字，每篇都读摘要找"（2026-10-18）；`lint_items.py` 的 `name_not_tagged` 列出摘要里有名字、却没有对应标签的条目（真实库里 71 处，收紧规则后待复查）。
- 状态：已处理

## 5. 其他观察

- 快照来自经代理的页面：Zotero Connector 把 `doi.org` 自动转到学校代理，所以快照是代理页面。用户已登录，核对通过，附件 URL 仍是原站。SKILL.md 说"快照取不经代理的页面"，与实际不符，要改写成"取到的页面必须核对通过"。已处理：SKILL.md 和 `fetch.py` 说明已改。
- IEEE 页面没有 `citation_pdf_url`：已移出，单独成为 `docs/issues/archive/20261018-paper-to-zotero-ieee-pdf-link-fixed.md`。
- arXiv API 在查正式版候选时返回 503（Harness^2、Restormer 两篇），候选只来自 Crossref。Restormer 和 PromptIR 仍然找到了正式版。
- 同一篇 Harness^2 来了两份：页面内请求取到一份，Chrome 又下载了一份，第二份按设计进了 `stray/`。
- Semantic Scholar 不带 key 时返回 429，本次不再使用。
- 状态：已处理 → 只是记录；唯一要做的 IEEE 一项已单独成 issue
