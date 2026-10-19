# paper-to-zotero — 设计 spec v3（2026-10-13，待审）

> 本版从 v2（`cba872b`）出发重新设计。上一次按 issue 逐条修改的尝试（2026-10-12）已经放弃，代码保存在本地分支 `p2z-v3-attempt1`；其中经过验证的做法，按本设计挑选采用。

## 1. 为什么重新设计

两份 issue 合计 54 条：`docs/issues/20260923-paper-to-zotero-v2-first-use.md`（17 条，下文记作 F#）和 `docs/issues/archive/20261009-paper-to-zotero-batch-import-fixed.md`（37 条，下文记作 B#）。

v2 处理单篇论文顺手，批量时的问题主要有：
- PDF 核对误报约 90 次，同时又有错文件进了库；
- 重复建条目；
- 需要用户的步骤散落在整个过程里；
- 下载重复，或者已经下载了却没检测到；
- 拿不到的论文反复循环；
- 预印本没有先换成正式版。

上一次尝试逐条修补，规模翻了一倍，越改越乱。这次从整体出发重新设计。

## 2. 设计思路

1. **每篇论文一份档案**（`records/<slug>.json`），从头跟到尾：认准 → 查库 → 拿 PDF → 核对 → 存进 Zotero → 报告。中途断了，重跑同一条命令就接着做。
2. **脚本只做机械活**：下载、核对、建条目、挂附件。看页面、判断情况、决定去哪儿取，都由 agent 来做。脚本拿不到的交给 agent，agent 卡住了就问用户。
3. **用户是辅助**，作用是加快进度、过人机验证、登录。
   - agent 的跑法不看用户在不在。
   - 用户随时可以插手（点下载、登录），后台的下载监控会接上。
   - agent 能预见需要用户帮忙的，提前在对话里说。
4. **拿不到就不硬耗**：每篇的取全文链路最多走三遍，最后一遍请用户在场；还拿不到，就报告"无法获取"，并存一份网页快照。
5. **复用，不重造**：
   - 网页访问交给 opencli（`opencli-usage`、`opencli-browser` 两个 skill），找论文可以用 `papers-cool-search`。
   - 同一件事只有一处实现：查库一处、核对一处、文件归位一处。

## 3. 一个例子

用户说："把 Reflexion、一篇 Elsevier 期刊论文、一篇 IEEE TMI 论文加进 Zotero。"

1. **开工（几分钟）**
   - agent 认准三篇。Reflexion 给的是 arXiv 号，脚本查出它发表在 NeurIPS 2023。
   - 查库：三篇都不在库里。
   - 列出每篇能从哪儿拿全文：Reflexion 有 NeurIPS 论文集的免费 PDF；Elsevier 那篇在某个机构库有一份副本；TMI 那篇要经学校登录才能拿。
   - 问题一次问完：Reflexion 用哪个版本，三篇放进哪个分类。用户没回，就按默认走（正式版、放进 `tmp`）。
   - 顺带提醒："TMI 那篇要经学校登录，方便的话现在登一下（Ctrl+N 开一个普通窗口）。"
2. **第 1 遍**
   - Reflexion：直接下载 → 核对 → 归档。
   - TMI：在文章页里取到 PDF → 核对 → 归档。
   - Elsevier：试机构库（只有题目，没有 PDF）→ 经学校去出版社（显示"本校未订阅"）→ 作者接受稿（没有）→ arXiv（没有）。这一遍没拿到。
3. **建条目、挂附件**：三条都建好，Elsevier 那条暂时没有附件。
4. **第 2 遍**：Elsevier 那篇再自己走一遍，还是没有。
5. **最后一遍，请用户在场**：在对话里说明并推送"还剩 1 篇，各处都没找到"，等用户来。用户在场时一起再走一遍；还是没有 → 存出版社文章页的快照，报告"无法获取"。
6. **读回、报告、清理。**
7. **以后的项目再碰到这篇**：库里只有快照，就再走同样的三遍；拿到 PDF 就挂上，旧快照请用户确认后移进回收站。

## 4. 流程

### 4.1 步骤

保留 v2 的编号，单篇就是只有一篇的批量。

| 步 | 做什么 | 本版变化 |
|---|---|---|
| 0 准备 | `ready.py`：Zotero、key、下载目录、工作目录 | 必须装 pdftotext；读统一配置 |
| 1 认准 | agent 按回落阶梯检索 | 不变 |
| 2 起草 | `doi_to_item` → `find_in_library` → `check_item`；整理条目、标签、分类 | arXiv 论文给出正式版候选，确认后在原记录上改成正式版；补副标题、arXiv 分类、LNCS |
| 3 拿文件 | 取全文链路（§4.2） | 全部重写 |
| 4 存库 | `check_pdf` → `create_item` → `attach_file` | 建条目前自己查重；只挂核对过的文件；附件标题写明版本 |
| 5 读回、报告 | `find_in_library --readback` → `report` | 读回刷新原来那块；报告加几张清单 |
| 6 清理 | 工作目录、浏览器会话、本次下载 | 新增收件、`stray/`、`unverified/` 三个目录；收尾扫一遍下载目录 |

### 4.2 取全文链路

**一遍的顺序**（拿到就停）：
1. 正式版的开放副本（`fulltext_links` 列出的 published 链接，包括 PMC）；
2. 经学校登录，去出版社的文章页；
3. 图书馆检索系统或数据库（配置里有才走，由 agent 在浏览器里操作，做法写在 publishers.md）；
4. 作者接受稿；
5. 预印本（arXiv 等）。

**每条路怎么取**：脚本先用通用办法；不行，就交给 agent。
- 链接是直接可下载的：`fetch --via http`。
- 文章页：`fetch --via page`，打开页面，取页面里写明的 PDF 链接（`citation_pdf_url`），在页面里请求，请求带着登录状态。被拒，就直接打开这个链接，由 Chrome 下载，或者从阅读器里取出字节。还拿不到，就停在这一页，交给 agent。
- agent 自己看页面，按 publishers.md 里各出版社的说明操作，比如点按钮、进阅读器取字节、去检索系统查。卡住了就问用户。
- 各出版社的门道写成给 agent 看的文字，不写成代码。网站改了，agent 照着页面应变，事后在报告的 skill 备注里提出来，再更新文档。

**结果怎么算**：
- 每篇都试。"未订阅"只是这一篇在这条路上的结果，不影响同一网站的其他论文。
- 拿到替代版本（接受稿、预印本）也算拿到：附件标题写明版本，报告里列在"替代版本"下。

**重试**：
- 同一篇最多走三遍。每一遍走法都一样，不按第几遍换做法；任何一遍遇到门禁都可以请用户帮忙。
- 下一遍要等整批走完这一遍再开始，中间先建条目、挂上已拿到的文件。这样网络、验证页这类临时问题有时间自己恢复。
- **最后一遍必须用户在场**。在那之前，其他论文先全部收尾。然后在对话里汇报，同时推送：还剩哪几篇、前几遍试过什么、各卡在哪里。用户说可以，再开始走：需要浏览器的路线逐篇在前台窗口打开，每停在一篇，就告诉用户这是哪篇、可以怎么帮，agent 同时自己操作；文件到了，或者用户说"跳过"，就开下一篇。用户暂时不在，这几篇就标成"等你在场做最后一遍"，报告照常先出；用户说"继续"时接着做。
- 最后一遍还没拿到：存出版社文章页的快照，也就是页面的 HTML，并且要核对过；挂成快照，报告列进"无法获取"，写明每一遍走了哪些路、结果如何。快照取不经代理的页面（`doi.org` 跳到的出版社原站），因为经代理的页面在未订阅时会跳到登录页，存下来核对不过。

### 4.3 门禁和用户帮忙

**门禁**：用户能过、agent 过不去的页面，比如机构登录、人机验证、cookie 墙。
- 先推送提醒，在对话里说清是哪一页、要用户做什么，然后最多等 5 分钟（`fetch --wait`）。
- 等待期间每 10 秒看一次页面和这篇的文件，不在这个标签页里换页。文件到了（用户另外下好了）、页面过了、或者用户说登好了，都结束等待。因为文件到了而结束的等待，不算这一遍等过这个门禁。登录请用户按 Ctrl+N 开普通窗口去登，登录状态整个 Chrome 共享。
- 同一个门禁在一遍里只等一次。没过的话，这一遍里其他要过同一门禁的论文不再等，直接试各自的下一条路。
- 门禁标签页留着不动，后面的站点开新标签页继续。
- 自动化窗口在后台打开，不抢用户的焦点；最后一遍在前台打开，给用户看。

**过不去的页面**：代理返回的 "Host Needed" 或 404、网站的封禁页。
- 当场告诉用户是什么情况。
- 本次运行里 agent 不再访问那个站。这一点由 agent 自己记住，不写标记文件。

**提前说**：列完全文链接后，agent 能看出哪些论文要经学校登录，先在对话里说一句"这批有 N 篇要经学校登录，方便的话现在先登一下"。

**用户插手**：用户在 Chrome 里点下载、登录都可以。`claim --watch` 从第 0 步起一直在认领下载目录，用户下载的文件核对后归位，agent 就不再去取那篇：`fetch` 每处理一篇前、等待中都重新看文件到了没有；agent 手动操作页面时，每一步前也先看；支持事件推送的环境（Claude Code 的 Monitor）还盯着 `fetch.jsonl`，一归位就通知 agent。用户帮忙只是加快进度，agent 照样主动去取。

### 4.4 批量

顺序：
1. 分流：主会话起草全部论文、拿到正式版候选、查库、列出全文链接；问题一次问完；提前说明哪些地方可能要用户帮忙。
2. 第 1 遍。
3. 核对 → 建条目 → 挂附件。
4. 第 2 遍。
5. 最后一遍（用户在场）。
6. 快照。
7. 读回 → 报告 → 清理。

- 取文件不写记录，只落下文件和日志 `fetch.jsonl`，所以和并行改记录的子 agent 不会互相覆盖。
- 子 agent（最多 5 个）只做判断：选标签、确认正式版候选（用 papers.cool 逐篇查）、补摘要（每个来源一次只发一个请求）。
- 批量调外部接口的脚本只在主会话跑；Google Scholar 也只在主会话用，每分钟最多一次。
- 遇到 429：在本次运行里停用那个来源，并在报告里写明。

### 4.5 下个项目再碰到同一篇

Zotero 本身就是记录：
- 条目已有 PDF（包括预印本）：跳过。
- 只有快照：照常走取全文链路。拿到后挂上 PDF，旧快照列进"待清理附件"，用户确认后由 `trash_item` 移进回收站。

### 4.6 整理已有条目

第二步才实现，见 §8。

**做法**：
1. 体检：`lint_items`，只读。
2. agent 根据体检结果拟一份修改清单，合并的几对要列出字段对照。
3. 用户确认后执行：
   - 改字段：`update_item`；
   - 合并重复：`merge_items` 只合并信息，不删除；
   - 移进回收站：`trash_item`。
4. 读回核实。

## 5. 结构

### 5.1 文档

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 步骤 0–6；门禁、回落阶梯、残留等规则。按 `writing-for-agents` 写 |
| `references/batch.md` | 批量的顺序、重试、最后一遍、子 agent 分工、日志、报告 |
| `references/publishers.md` | 各出版社取 PDF 的门道；页面判断（登录、未订阅、Host Needed、封禁、购买页先点机构登录）；检索系统和聚合库的做法；opencli 实测行为 |
| `references/organize.md` | 整理：回收站、移出分类、重复条目怎么处理、体检和合并（第二步） |
| `references/tagging.md` | 补充"什么算模型名" |
| `references/install.md`（新） | poppler-utils（系统包，用户同意后安装）、Zotero 本地 API 授权、OpenAlex key、配置文件格式 |

### 5.2 脚本

| 脚本 | 做什么 | 状态 |
|---|---|---|
| `ready` | 准备与检查 | 改 |
| `doi_to_item` | 标识符或论文页 → 条目草稿；正式版候选；原地改成正式版 | 改 |
| `find_in_library` | 查库、读回、按 md5 查文件 | 改 |
| `check_item` | 写库前预览字段 | 不变 |
| `check_pdf` | 核对文件就是这篇（PDF 或 HTML） | 改 |
| `create_item` | 建条目（先查重） | 改 |
| `attach_file` | 挂附件（只挂核对过的） | 改 |
| `fulltext_links` | 列出全文链接 | 新 |
| `fetch` | 取字节：http / page / viewer / snapshot | 新 |
| `claim` | 文件归位的唯一入口：脚本取到的、下载目录里的 | 新 |
| `trash_item` | 移进回收站、恢复 | 新 |
| `report` | 报告 | 改 |
| `file_and_tag` | 改分类和标签 | 改 |
| `read_library` | 读库 | 改 |
| `update_item` | 改字段 | 第二步改 |
| `make_collection`、`note`、`export_bib`、`p2z` | — | 不变 |
| `lint_items` | 体检（只读） | 第二步新增 |
| `merge_items` | 合并重复（只合并信息） | 第二步新增 |

脚本约定沿用 v2：
- 每个脚本都是过滤器：读记录路径或 stdin，输出 JSONL，加 `-i` 时就地写回；
- PEP 723 头部，只用标准库；
- 脚本之间只通过子进程调用，不互相 import；
- 返回码统一：0 通过，1 未通过，2 无法检查。

### 5.3 配置

只有一个文件：`~/.config/paper-to-zotero/config.json`，权限 600，放在仓库外。

```json
{
  "zotero": {"key": "…", "serverID": "…"},
  "openalex_key": "…",
  "institution": {"proxy": "<proxy-domain>", "discovery": "<discovery-url>"}
}
```

- 每一项都是可选的；缺了哪项，对应的能力就跳过，并且说明原因。
- 所有脚本只读这一个文件，唯一的环境变量是 `PAPER_TO_ZOTERO_CONFIG`（文件路径，测试用）。
- `ready.py --authorize` 拿到的 key 写进这个文件。`ready.py` 只报告每一项有没有，不打印值。
- 迁移：把现有的两个 key 文件复制进来，这是一次性的本地操作。旧文件要等新版装好、用户同意后再删。

### 5.4 工作目录

| 路径 | 内容 |
|---|---|
| `records/<slug>.json` | 记录 |
| `records/<slug>.pdf`、`<slug>.accepted.pdf`、`<slug>.preprint.pdf`、`<slug>.html` | 归位后的文件；版本写在文件名里，不写进记录 |
| `inbox/` | 脚本刚取到、还没核对的字节 |
| `stray/` | 同一篇的第二份 |
| `unverified/` | 脚本取到但核对没过的文件 |
| `fetch.jsonl` | 只追加的日志。`{event: "try", slug, pass, via, url, result, at}` 记每次尝试；`{event: "claim", file, slug, result: claimed / stray / unverified / left, version, source, at}` 记认领 |
| `scratch/`、`.started` | 一次性代码；本次运行的起点标记 |

### 5.5 记录

在 v2 的字段（`slug`、`item`、`citationKey`、`tags`、`collection`、`found`、`checks`、`saved`、`file`、`pdf`、`attach`、`blocker`）之外新增：

- `published_candidates`：正式版候选，`[{doi?, venue, year, title, url?, source}]`。
- `links`：全文链接，`[{url, source, version, needs_browser}]`。
- `alt_titles`：备选题名，比如 arXiv 版的题名。
- `distinct_from`：agent 判定"不是同一篇"的条目 key。
- `pdf_accepted`：`{reason}`，agent 读过第 1 页后接收了一个核对没过的文件。

## 6. 各脚本要点

**ready**
- PATH 上没有 `pdftotext` 或 `pdfinfo`：退出码 2，结果 `no_pdftotext`，提示照 install.md 安装。
- 报告配置里各项有没有；配置文件权限过宽时给出警告。
- 其余同 v2。

**doi_to_item**
- 副标题：拼成"标题: 副标题"，标题里已经有就不拼。
- arXiv 分类取自 DataCite 的元数据，作为 type 1 标签，写法同 Zotero 的 arXiv 转换器（也就是库里现有的写法），去掉 `FOS:` 开头的项。
- LNCS：带 ISSN 的书章节，查一次 Crossref REST。`container-title` 有两项、且第一项是已知丛书时，改成会议论文：`proceedingsTitle` 取第二项，`series` 取第一项。
- 勘误警告：
  - 题名含 Correction、Erratum、Retraction 等词；
  - 或者没有作者、页码只有一页、而且这一页不是文章号。
- `published_candidates`（只对 arXiv 记录）：
  - 来源一：arXiv API 的 journal_ref 和 doi，每次最多 100 个 id；
  - 来源二：Crossref 题名检索，相似度 ≥0.9，排除 `10.48550` 前缀和 posted-content 类型。
  - 不改动条目本身。
- `--redraft <DOI | 论文页链接> -i 记录`：在原记录上改成正式版。
  - 保留 slug、citationKey、tags、collection；arXiv 号写进 `extra`；旧题名和新的不同时，放进 `alt_titles`。
  - 清掉 `found`、`checks`、`links`、`published_candidates`、`pdf`。
  - 记录已有 `saved` 时拒绝执行。
  - 给链接时：用普通 HTTP 读页面上的 `citation_*` 元数据。有 `citation_conference_title` 就是会议论文，有 `citation_journal_title` 就是期刊论文（所以 TMLR 按期刊处理）。页面被拦时，由 agent 按它看到的内容填写。
- 节流：同一个进程内，对每个主机保持最小请求间隔；遇到 429，本次运行停用这个来源。

**find_in_library**
- 依次按 DOI、arXiv 号、题名查找。
  - DOI 或 arXiv 号对上：算已在库。
  - 以下三种算"近似"：只有题名对上；预印本对正式版（记录有自己的非 arXiv DOI，库里那条只能靠 arXiv 号对上）；题名相同但 DOI 不同。
  - 每一级查找都排除 `distinct_from` 里的 key。
- `found` 里带附件信息（contentType、linkMode、md5、title），据此判断有没有 PDF。
- `--readback`：刷新存着这个 key 的那一块。本次新建的条目刷新 `saved`，原来就有的刷新 `found`；从不把 `saved` 改写成 `found`。
- `--md5 文件…`：判断这些文件是不是已经作为附件在库里。

**check_pdf**
- 用 `pdftotext -f 1 -l 3` 抽前 3 页文字，用 `pdfinfo` 取页数；删掉自带的文本读取。
- 通过：
  - `ok`：整条题名出现在前 3 页里；
  - `ok_by_words`：题名里 4 个字母以上的词，80% 以上出现在前 3 页，并且前 3 页里有这篇的 DOI，或者第 1 页前 1,500 个字符里有第一作者。
- 不通过：
  - `title_not_found`；
  - `erratum_suspected`、`supplement_suspected`：只看出现在标题位置的标记；记录的题名本身含这个词时不算；
  - `doi_mismatch`：第 1 页印着别的 DOI，前 3 页没有这篇的 DOI，而且文件是正式版；
  - `not_a_pdf`、`no_text_layer`；
  - `not_the_article`：HTML 但不是文章页，比如拒绝访问页。
- 其他输入和输出：
  - 读 `alt_titles`；
  - 文件版本从文件名读；
  - `evidence.arxiv_stamp` 标出页边有没有 arXiv 戳记，供 `claim` 判断版本。
- HTML 快照：比对 `<title>`、meta 和可见正文。
- `--match 文件 记录…`：拿一个文件逐条对照多条记录，输出每条的结果和 `{matched: […]}`；不写记录。
- 写入记录：`pdf: {code, evidence, md5, checked_at}`。

**create_item**
- `collection` 可以是字符串或列表，`--collection` 可以重复。
- POST 之前，把待建的记录交给 `find_in_library`（子进程）查一遍：
  - 已在库：写入 `found`，不建（后面附件挂到那一条上）；
  - 近似：返回 `possible_duplicate`，不建，由 agent 决定——是同一篇就把 `found` 设成那条的 key，不是就把那条的 key 加进 `distinct_from`。

**attach_file**
- 挂附件的前提，二者满足其一，否则返回 `not_verified`：
  - 记录里 `pdf` 是通过码，且 md5 和文件一致；
  - 或者有 `pdf_accepted`。
- 单条模式 `--key --file`：拿 Zotero 里那个条目的题名和 DOI 核对这个文件；`--accept "<理由>"` 可以放行。
- 附件标题按文件版本写：
  - 正式版：v2 的默认标题；
  - 接受稿：`Accepted manuscript`；
  - 预印本：`Preprint (arXiv)`；
  - 快照：`Snapshot`。
- md5 相同的文件不重复挂（同 v2）。条目要不要文件，由 agent 在第 2 步决定，不设额外开关。

**fulltext_links**
- 来源：
  - OpenAlex：`/works/doi:…`，带配置里的 key；key 不打印，日志里的网址去掉查询串；
  - Europe PMC：有 PMCID 就给 PMC 页，版本以 Europe PMC 的判定为准；
  - arXiv：`https://arxiv.org/pdf/<id>`。
- 写入 `links`，按正式版、接受稿、预印本的顺序排；每条标明 `needs_browser`。
- 某个来源失败不影响整条记录；遇到 429，本次运行停用这个来源。

**fetch**
- 只把字节交给 `claim`：先写到 `inbox/`，再调用 `claim --file`。
- 不写记录，每次尝试记一行 `fetch.jsonl`，带上 `--pass N`。
- 不判断页面是门禁、未订阅还是没有 PDF。
- 四种来源：
  - `--via http [--version V] 记录…`：逐条试记录里这个版本、不需要浏览器的链接，一条一条往下走。
  - `--via page [--start <url>] 记录…`：逐篇在会话 `p2z`（后台窗口）里打开文章页，默认是 `https://doi.org/<DOI>`，然后：
    - 取 `citation_pdf_url`（单条时也可以用 `--link` 指定），在页面里带凭据请求。当前主机在 `institution.proxy` 下时，按路径在当前主机上请求。
    - 被拒（403、返回 HTML、跨域跳转报错）：在标签页里直接打开这个链接。Chrome 下载了，就扫下载目录认领；显示阅读器，就从阅读器取字节。
    - 没有 PDF 链接，或者还是没拿到：停在这一篇，输出 `{slug, url, title, why: no_pdf_link | refused | not_pdf}`，标签页保持原样，退出码 1。
    - 跳过两种记录：已经有文件的；`fetch.jsonl` 里已有本遍（同一 `--pass`、同一 `--via`）尝试记录的。所以停下之后，agent 处理完那一篇，原样重跑同一条命令即可接着往下走。http 方式同样跳过这两种。
  - `--via viewer --slug S`：从当前标签页的 pdf.js 阅读器取出文档字节。
  - `--via snapshot`：取文章页的 HTML，存为 `<slug>.html`。
  - `--wait`（单条，门禁处）：每 10 秒读一次当前标签页和这篇的文件，不导航；文件到了 → `arrived`，页面出现 `--until` 的文字、或者没给 `--until` 时网址或标题变了 → `passed`，超过 `--timeout`（默认 300 秒）→ `gate_timeout`，记为这一遍这条路的尝试。
  - 每处理一篇前、页面路线停下前，都重新看这篇的文件（给了 `--downloads` 时先扫一次下载目录）；中途到了就跳过这篇。
  - `--window foreground`：最后一遍在前台打开页面；默认后台。

**claim**
- `--file F --slug S --version V --source URL`（脚本取到的字节）：
  - 用 `check_pdf` 对照这条记录；
  - 通过：先写临时文件，再用 `os.link` 链到 `records/<slug>[.<version>].pdf`（快照是 `records/<slug>.html`）；目标已经存在，就移进 `stray/`；
  - 不通过：移进 `unverified/`，日志里记下来源。
- `--scan`（扫一次下载目录）：
  - 只看 `.started` 之后出现、已经下载完的 PDF 或 HTML；
  - 用 `check_pdf --match` 对照还没有文件的记录，恰好对上一条就认领；版本看 arXiv 戳记，有就是 preprint，否则 published；
  - 版本判断错了（比如机构库里的接受稿被当成了 published），改文件名即可，文件名就是状态；
  - 对上多条或一条都没对上，原地不动，只记一次日志；
  - 是已归位论文的第二份，移进 `stray/`。
- `--watch`：反复执行 `--scan`。
- `--sweep`：收尾时列出本次运行后仍留在下载目录里的文件，并用 `find_in_library --md5` 标出哪些已经在库里。

**trash_item**
- 用法：`--key / --cite …`，加 `--dry-run` 或 `--restore`。
- 过程：读取条目 → 带版本号 PATCH `deleted` → 读回核实。
- 只在用户确认清单之后使用；本次运行自己产生的残留除外。

**report**
- 读回后的表格，再加几节：
  - 无法获取：从最后一遍之后仍没有文件的记录出发，再从 `fetch.jsonl` 取出它们每一遍走了哪些路、结果如何；一次都没试过的记录也会列出；
  - 替代版本；
  - 待清理附件：本次挂上正式版 PDF 的条目里，仍留着的快照、预印本或重复文件；
  - 新标签：按前缀分组；
  - 下载目录和 `unverified/` 里的残留；
  - 碰到过的门禁。

**file_and_tag**：
- 单条和批量都支持 `remove_collection`；
- 批量文件里可以用 `cite` 指定条目；
- dry-run 和真写的输出用同一个键。

**read_library**：`--help` 写明每个子命令每一行的形状；`items` 加 `--tag` 过滤。

**第二步**
- `lint_items`（只读）：按分类或 key 列出每个条目的问题，输出的 JSONL 可以直接交给 `update_item --patch`。问题包括：
  - `duplicate_of`：库里别处有同 DOI、同 arXiv 号或同题名的条目；
  - `unfiled_webpage`：没归类的网页条目；
  - `multiple_pdfs`：一条挂了几份 PDF；
  - `date_unparseable`：日期解析不了；
  - `abbreviation_misplaced`：期刊全称和缩写放错了位置；
  - `missing_doi`：缺 DOI（Crossref 能查到时附上候选）；
  - `missing_abstract`：缺摘要；
  - `no_identifier`：没有任何能定位这篇论文的标识。
  - `name_not_tagged`：摘要里给出的模型或系统名（"we propose X"），没有对应标签（2026-10-18 补）。
- `merge_items --keep K --drop K2 [--dry-run]`：
  - 列出两条的字段对照；
  - 保留条目里空着的字段，用被并条目的值补上；冲突只列出来，不覆盖；
  - 分类取并集，去掉 `tmp`；标签取并集；
  - 被并条目独有的 PDF（按 md5 判断）和笔记，改挂到保留条目下；
  - 不删除任何东西。
- `update_item`：
  - 先验证 F#14 的推断（是不是插件在写入后又改了 `extra`）。2026-10-18 验证：不是插件，是 Zotero 自己把 Extra 里 `PMID: n` 这类行迁进同名字段；读回时把这种情况报为 `moved_to_fields`，算成功。
  - `deleted` 的拒绝提示改为指向 `trash_item`。

## 7. 决定

**已定**：
- 2026-09-21 至 23（v1、v2）：
  - 门禁先推送提醒，再等 5 分钟；
  - 访问按回落阶梯；
  - 没有 PDF 也入库；
  - 标签由 agent 管，规则是活的；
  - 用 citation key 指代论文；
  - 本地写 API 可以随意使用。
- 2026-10-12：
  - 回收站用 `trash_item`，用户确认后执行；
  - NeurIPS 的 `10.52202` DOI 填进 DOI 字段；
  - 仓库里的机构信息一律用占位符；
  - 只在用户说"推送"时推送。
- 2026-10-13：
  - 必须装 pdftotext，写进 install.md；
  - papers.cool 可以批量用，一次只发一个请求；
  - 统一配置文件；
  - 每篇都试；
  - 链路最多走三遍，arXiv 算拿到，但排在最后；
  - 跑法不看用户在不在，用户随时可以插手；
  - 最后一遍必须用户在场；
  - 同一门禁在一遍里只等一次；
  - 整批走完一遍再开始下一遍；
  - 能预见要用户帮忙的，提前说；
  - 脚本先用通用办法，拿不到交给 agent，卡住了问用户；
  - 整理工具写进本 spec，等导入部分用真实批量测通之后再做。

**暂行**：标识怎么放仍按 v2 的规则（F#15）：有 DOI 填 DOI；没有 DOI 的会议，`url` 填官方页；有预印本就在 `extra` 里写 `arXiv: <id>`。

**等用户**：
- F#8：笔记上要不要打标签；
- F#9：稿件引用文献的分类结构；
- F#17：标识放在哪个字段的原则。

## 8. 实现顺序与验收

**第一步：导入部分**
1. 配置文件与 `ready`；
2. `check_pdf`；
3. `find_in_library`、`create_item`、`attach_file`；
4. `doi_to_item`；
5. `fulltext_links`；
6. `fetch`、`claim`；
7. `trash_item`；
8. `report`、`file_and_tag`、`read_library`；
9. 文档。

每个脚本配测试：标准库 unittest 加 mock 服务；WSL 下用关闭端口的辅助函数代替 `127.0.0.1:9`。

**第一步验收**：
- 全部测试通过；`p2z.py --help` 列出全部脚本。
- 对真实库做只读冒烟测试。
- 真实批量：约 10 篇导入 `tmp`。开始前先告诉用户，并且用户在线。要覆盖以下情况：
  - 开放副本；
  - 经学校登录取文件；
  - 未订阅（走满三遍后存快照）；
  - 有正式版的 arXiv 论文；
  - 用户手动点下载；
  - `trash_item` 第一次真实使用：先 dry-run，移一条进回收站，再恢复。

**第二步：整理工具**：`lint_items`、`merge_items`、`update_item`（F#14）、organize.md；各配测试；用一个分类做只读体检验证。

**每一步都是**：spec 审过再写代码；到里程碑就提交；推送前扫一遍提交里的机构信息，等用户说"推送"再推。

## 9. issue 去向

| 条目 | 去向 |
|---|---|
| B#1 | check_pdf：pdftotext，两条通过路径 |
| B#2 | create_item 支持多分类 |
| B#3 | 读回刷新原来那块；单条要回写记录时，用 `-i <记录>` |
| B#4 | 正式版候选 + `--redraft` |
| B#5 | publishers.md（开放获取期刊走 PMC、OpenReview 和 DBLP 被拦、Europe PMC 的 render 链接、Turnstile） |
| B#6 | PDF 链接一律从页面读；publishers.md |
| B#7 | claim：第二份进 stray，晚到的下载也认领 |
| B#8 | tagging.md |
| B#9 | 链路第 3 步；publishers.md 写检索系统和 ProQuest 的做法；配置里的 discovery |
| B#10 | fetch `--via viewer` |
| B#11 | fetch `--via page` |
| B#12 | publishers.md：Turnstile 先提醒，等它自己过 |
| B#13 | check_pdf 核对 HTML；publishers.md：Host Needed |
| B#14 | trash_item；报告的待清理附件 |
| B#15 | `alt_titles` |
| B#16 | fulltext_links：OpenAlex（含 Unpaywall 的数据）、Europe PMC；机构库链接取回来要核对过才算 |
| B#17 | publishers.md：network 的输出先存成文件 |
| B#18 | §4.4 的分工 |
| B#19 | 正式版候选 + papers.cool 补查，不建会议索引 |
| B#20 | SKILL / publishers.md：适配器失败就改用浏览器，保存适配器的原始输出 |
| B#21 | §4.3、§4.4：一种跑法，提前说 |
| B#22 | fetch 在代理下改主机；publishers.md：Zotero Connector 的代理关联，开放获取期刊走 PMC |
| B#23 | publishers.md：OpenReview 会前返回 403 = 尚未公开 → 改用预印本 |
| B#24 | `--redraft` 读论文页；publishers.md：各会议 PDF 的取法 |
| B#25 | 配置里的 `openalex_key`；fulltext_links |
| B#26 | §4.3 门禁：Ctrl+N 登录、脚本停在页面上不跳走、门禁标签页保留 |
| B#27 | claim：每次尝试后扫描，`--watch` 常驻；`--sweep`；`find --md5` |
| B#28 | 附件标题按版本写 |
| B#29 | 副标题、arXiv 分类 |
| B#30 | SKILL 第 2 步：PMID 会被迁成独立字段 |
| B#31 | 正式版在建条目之前定下 |
| B#32 | doi_to_item 勘误警告；check_pdf 拦勘误、DOI 不符；取到的文件一律核对 |
| B#33 | publishers.md：Article in Press 算接受稿；附件标题 |
| B#34 | claim `--watch`；文档写明用户帮忙只是加速 |
| B#35 | publishers.md；遇到封禁页，本次不再访问该站并告诉用户 |
| B#36 | 最多三遍；报告的无法获取清单 |
| B#37 | publishers.md |
| F#1 | create_item 建前查重 |
| F#2、F#11 | 已处理（v2） |
| F#3 | read_library 的 `--help`；file_and_tag 输出统一 |
| F#4、F#5 | file_and_tag |
| F#6、F#7 | lint_items（第二步） |
| F#8、F#9、F#17 | 等用户 |
| F#10 | trash_item |
| F#12 | merge_items（第二步）；organize.md |
| F#13 | check_pdf 用 pdftotext |
| F#14 | update_item（第二步，先验证） |
| F#15 | 暂行规则不变；lint_items 检查 |
| F#16 | doi_to_item：LNCS |

## 10. 修订

- 2026-10-13：建立。
- 2026-10-18（第二步）：`lint_items` 一次读全库（只读），加 `name_not_tagged`；`merge_items` 按 `/api/schema` 的字段和基础字段对应；F#14 的原因是 Zotero 的 Extra 迁移。
- 2026-10-18：用户补充（"我实际上已经帮你下载了，但是你还没找到pdf……就一直卡在那"；"最后确认那一遍的话，你汇报，然后依次帮我在浏览器打开"）：门禁等待改由 `fetch --wait` 做，文件到了也结束；`fetch` 每篇前重查文件；Monitor 盯日志；最后一遍逐篇在前台打开（`--window foreground`）。
