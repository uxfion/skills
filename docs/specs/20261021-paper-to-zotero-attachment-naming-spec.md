# paper-to-zotero：附件按版本规范命名

> **定稿**（2026-10-21）：advisor 审过两轮，按用户意见改过两处，又自审了两轮（§10 记了改了什么）。用户让我自审没问题就开始实现。实现过程中如有修正，直接改本文。
> **已实现，已冻结**（2026-10-21 起；2026-10-27 推送到 `edac142`，同日按 §5 完成一次性改名）：实现时改了几处，正文已改，§12 记了改了什么、为什么。
> 来源：[20261020-paper-to-zotero-pdf-version-by-title-fixed.md](../issues/archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)。设计过程、用户原话和调研的结论都在那张 issue 里。
> 文中的数量都是 2026-10-21 全库试命名（只读）的结果。

## 0. 目的和范围

**问题**：
- 一个条目可以挂好几份 PDF，库里却没有地方写明哪份是哪个版本。
- 现在 p2z 读的时候按标题猜：认不出的一律当正式版，并列时按添加时间排。
- 全库 802 份 PDF 里，标题叫 "PDF" 的 470 份，底下什么版本都有：53 份其实是预印本，15 份是 CVF 开放版，5 份是投稿审稿版。
- 有 8 个条目的两份 PDF 分不出先后，其中 7 个排第一的不是正式版。

**根源**：
- 取得文件的那一刻，文件是哪个版本、从哪来的，信息都在手里，只是没按统一的规范记下来。
- 标题由好几方各写各的：p2z 的几次运行、Zotero、Connector，还有手工起的。

**原则**（贯穿全文）：
1. **存档第一**：p2z 的目标是拿到全文 PDF 存进库里。版本只是附加信息，定不了就标 `Unknown`，绝不因此不挂文件（用户 2026-10-21）。
2. **在信息最全的那一刻定**：版本在出版方页面上、下载时、claim 初查时定；事后只剩文件本身（用户 2026-10-21）。
3. **只定义，不写死识别方法**：规范只定版本的定义和名字。"在某家出版方凭什么认"不写进代码，由 agent 判断；出版方的标识只当带日期的线索（用户 2026-10-21）。
4. **脚本记事实，agent 下判断**：脚本只收集和原样记录证据，不解读页面文字。判断由 agent 做，把握不大的交给后台 sonnet subagent。
5. **对外访问守规矩**：不多发请求，能复用的复用；派出去的 agent 守 §6。
6. **改库要用户点头**：改已有附件的标题、把附件移进回收站，都先列清单，等用户确认。例外和回收站规则一样：这一轮自己刚挂上的附件，同一轮里可以直接改标题。

**这次做什么**：
1. 附件标题规范（§1）。
2. 取文件时记下证据、当场判定版本（§2、§3）。
3. 读取时只认规范标题（§4）。
4. lint 找出不合规范的标题；现有的库一次性改名（§5）。
5. 派出去的 subagent 守访问节奏（§6）。

**这次不做**：
- 自动发现"某篇出了新版本"的机制。这次只把 `vN`、`in_press` 两个标记留好（§7）。
- 结构化包的文件夹命名。回到 [20261020-paper-to-zotero-structured-package.md](../issues/20261020-paper-to-zotero-structured-package.md) 再定，会从本规范的标题派生。
- 文件名不变，仍是 Zotero 的"作者 - 年份 - 标题"。
- PDF 被替换、进回收站时，它的结构化包怎么处理，也回结构化包那张 issue 再定。

## 1. 命名规范

**附件标题 = `<Version>-<Source>-<detail>`**
- 字段之间用 `-`；一个字段里的空格和名字自带的 `-` 都换成 `_`。
- 版本词首字母大写；来源保持原写法（`arXiv`、`IEEE`）。
- `detail` 可选，可以有几段（各用 `-` 隔开），但只能跟在 `Source` 后面。来源不知道时只写版本词，这样按位置解析不会把 detail 当成来源。
  - in-press 文件来自出版方，来源总能从 DOI 推出来，所以 `in_press` 不会因为这条丢掉。

| Version | 定义（按 NISO RP-8-2026） | 例子 |
|---|---|---|
| `Published` | 出版方定稿的那份：期刊出版社版、会议论文集版、OpenReview 上 ICLR/TMLR 的终稿、水印写着"与 IEEE Xplore 上的版本相同"的 CVF 开放版（CVPR、ICCV 到 2018 年）。排了版、还没进卷期的也算，加 `in_press` | `Published-RSNA`、`Published-OpenReview-ICLR_2023`、`Published-CVF`、`Published-Elsevier-in_press` |
| `Accepted` | 审稿通过的文字，但不是出版方定稿的那份：PMC 作者稿、水印写着"与接收版相同"的 CVF 开放版（2019 年起）、MICCAI 和 ECVA 开放版、arXiv 上写明已接收的版本、未编辑的在线优先稿 | `Accepted-CVF`、`Accepted-arXiv-v3`、`Accepted-IEEE-in_press`、`Accepted-Europe_PMC` |
| `Preprint` | 作者自己发布、没写明已接收的版本：接收前的（arXiv 预印本、OpenReview 投稿版），或接收后自行扩充修改、也没写明接收的（CycleGAN 2020 年的 arXiv v7，ICCV 2017 正文加附录）。预印本条目自己的 PDF 也这样写 | `Preprint-arXiv-v7`、`Preprint-OpenReview-ICLR_2027_submission` |
| `Unknown` | 看过证据仍定不了的，或保存时还没定下来的。文件照样挂上 | `Unknown`、`Unknown-ResearchGate` |
| `Supplement` | 补充材料（不是论文本身的版本） | `Supplement-Nature`、`Supplement-Nature-source_data` |
| `Snapshot` | 网页快照（不是论文本身的版本） | `Snapshot-Elsevier` |

**Source**：
- 文件实际从哪个网站下载的，用出版方或会议的简短名称。
- 起始模板：arXiv、OpenReview、CVF、ECVA、MICCAI、NeurIPS、PMLR、ICLR、ACL、AAAI、JMLR、IEEE、Elsevier、Springer、Nature、ACM、Wiley、RSNA、BMJ、NEJM、Science、MDPI、JMIR、OUP、PMC、Europe_PMC、HAL、eScholarship、ResearchGate、Research_Square、EasyChair、author_page。

**detail**：只在需要区分时写。起始模板：
- `vN`：预印本服务器的版本号。arXiv 一律写，因为不带版本号的地址会随作者更新而变。
- `in_press`：还没进最终卷期、以后会被换掉的版本。IEEE Early Access、Elsevier Article in Press、Nature Article in Press、Wiley Early View、ACM Just Accepted 都用这一个词。
- `ICLR_2023`：OpenReview 上的会议终稿；`ICLR_2027_submission`：投稿版。照抄 OpenReview 给的状态，从 OpenReview 取的文件一律写（TMLR 没有年份，写 `TMLR`）。
- `source_data` 一类：同一来源有多份补充材料时区分。
- `abstract_booklet_p66`：合集里的一篇。

**两份清单都是模板，不是封闭的清单**（用户 2026-10-21：「现在列举的是一个template，而不是固定库」）：
- 遇到新网站、新情况，agent 按上面的规则自己加，并在报告里说明；
- 代码里网站到来源名的对照表只是起点，查不到时由 agent 给名字。

**并存与替换**：
- **论文本身的版本**（Published、Accepted、Preprint、Unknown）：
  - 不同来源的并存，例如 CycleGAN 的 `Preprint-arXiv-v7`、`Accepted-CVF`，以后补上的 `Published-IEEE`。
  - 同一来源只留最好、最新的一份。比较顺序：先比版本高低，再看有没有 `in_press`（不带的胜出），再比 `vN`（大的胜出），都一样就留后加的。例子：`Preprint-arXiv-v1` 让位给 `Preprint-arXiv-v3`；`Accepted-Nature-in_press` 让位给 `Published-Nature`。
  - 只有一份写了 `vN`、其余都一样时，不判定谁让位，两份都留着：没写的那份版本号不知道，可能更新，也可能更旧。
- **补充材料**：detail 不同的并存；同一来源、detail 相同的，新的取代旧的。
- **快照**：每个来源一份，新的取代旧的。找不到 PDF 时挂上去顶替的快照，等论文的 PDF 到了，照旧列进"待清理附件"（沿用现在的行为）。
- 被取代的那份列进报告的"待清理附件"，用户确认后进回收站。
- 列出来时的顺序：Published、Accepted、Preprint、Unknown；同一级里，不带 `in_press` 的在前，`vN` 大的在前，再按添加时间。补充材料和快照另列。

## 2. 版本在取得文件的那一刻定

**那一刻记下什么**（脚本原样记录，不解读）：
- **取文件的路线**：open、publisher、discovery、accepted、preprint，以及当时想要的是哪个版本。这本身就是事实：从出版方的 DOI 落地页拿到的 PDF，和从 arXiv 拿到的，来处不一样。
- **实际下载地址和网站**，以及它对应的来源名（查不到就留空）。经学校代理的地址（`ieeexplore-ieee-org.<proxy>`）先用 `web.unproxy` 还原，再对照来源名。
- **页面**，在页面上取到文件时记：页面自己声明的元数据、页面上标题附近的文字（标签、日期、卷期都在那里）、PDF 是从哪个链接点出来的、链接文字和它周围的文字（"View Open Manuscript"、"Download PDF" 之类）。离开页面就拿不到了。arXiv 的文件，它的"页面"就是 arXiv 对这个版本的留言和期刊信息，查 vN 的那次请求里本来就有。
- **文件**：前两页的文字摘录、PDF 自带的日期、arXiv 页边戳。
- **arXiv 版本号**：
  - 预印本的记录在 prepare 找正式版时已经查过 arXiv API，返回里本来就带最新版本号，那时记进记录；
  - 其余的 arXiv 候选（比如期刊条目的 arXiv 副本）没经过那一步，由 fetch 在这一遍里用一次批量请求（`id_list`，按 `web.py` 现有的 3 秒节奏）查出；
  - fetch 下载带 `vN` 的地址。

**提议**：
- 脚本按路线和网站给一个默认版本：
  - arXiv、bioRxiv、medRxiv 的文件是 Preprint，不管走的哪条路线（预印本条目自己的 DOI 会把 publisher 路线带到 arXiv）；
  - 其余网站：publisher 路线是 Published；accepted 路线是 Accepted；preprint 路线是 Preprint；open 路线是 Unknown。
  - `fulltext_links` 给链接标的版本有一部分来自 OpenAlex，下面已经说了不能当证据，所以只用来排候选的先后，不用作默认版本。
- 这个默认只是起点，可能不对。例如从 arXiv 拿到的终稿副本，按路线默认是 Preprint，其实是 Accepted。所以默认版本必须经过下面的确认。
- 脚本不靠关键词去猜"这是不是 in press、是不是接收稿"。

**确认**：
- **浏览器 agent**：第 3 步每个停下的页面由一个浏览器 agent 处理。它把文件取到手时，连同版本和依据一起报回：页面上看到的标签、点的哪个链接、首页写了什么。它就在页面上，是信息最全的时候。
- **其余文件**：每一遍取文件结束时，fetch 列出这一遍拿到的文件，一份一行：默认版本、来源、链接文字、页面标签、首页开头几行。
  - agent 当场看这张表定下 `label`。文件多时，可以把整张表交给一个 sonnet subagent，它只读本地证据。
  - 看表定不了的，每份派一个 sonnet subagent，趁页面还能打开时去看。最多 10 个并行，同一网站同一时间只派一个，守 §6。
- **仍定不了**：写 `Unknown`（来源知道就带上），文件照样挂上。

**判断时可以用的证据**：
- 第 1、2 页要当图片看，不能只读文字层：版本标记常常是图片，或在文字层读不到的位置（CVF、MICCAI 的水印，Elsevier 灰色的 ARTICLE IN PRESS 横条）。模板文字会误导（elsarticle 在接收稿上也印 "Preprint submitted to <期刊>"）。附件网址也不能当证据：网址是 CVF 的文件，可能根本没有 CVF 水印。
- 最可靠的通用证据有三样：
  - 和已知版本逐字节相同（2026-10 的核对靠它定了 9 份）；
  - 文件日期落在投稿、接收、上线之间的哪一段；
  - 托管网站自己对这份文件的说明：会议开放版页面、机构库的文件标注、出版方页面上的版本标签。
- 不能当证据的：Unpaywall 和 OpenAlex 的版本字段（16 条里只有 2 条对得上）；Zotero 自动起的"已提交版本""全文""Full Text PDF"。
- 2026-10 探查到的各出版方标识，写进 `references/publishers.md` 当带日期的线索，例如"2026-10 见到：IEEE 作者版首页有 'has not been fully edited' 横幅"。线索和眼前的页面对不上时，以页面为准。

## 3. 导入流程的改动

- **prepare**（`doi_to_item`）：把 arXiv API 已经返回的最新版本号记进记录。
- **fetch**：
  - 记下实际下载地址；
  - 在页面上取到文件时，带回 §2 的页面证据（`p2zlib/browser.py`）；
  - arXiv 下载带 `vN` 的地址；
  - 每一遍结束时输出待确认表。
  - 链接上的版本（`fulltext_links`）仍然只用来决定先试哪个候选。
- **claim**：
  - 把 §2 的证据和默认版本写进这份文件的 claim 事件（`fetch.jsonl`）：`route`、`proposal: {title, version, source, detail}`、`evidence: {url, page, link, file}`。不写进记录（§12）；
  - 工作目录里的文件名后缀（`<slug>.accepted.pdf` 之类）照旧，表示"想要的版本"；`label` 表示"实际是什么"。
  - `verify.kind_of` 现在"有 arXiv 页边戳就算预印本"的规则，改成只把页边戳记进证据，不再单独定版本，免得两套机制并存。
- **`label`** 是记录里一个归 agent 管的字段，和 `same_as`、`distinct_from`、`keep_preprint` 一样，不另加命令：`{title, by: agent | subagent | browser_agent, why}`。
- **第 3 步的完成条件**改为：每个记录都有文件**和它的 `label`**（或者已经明确写成 `Unknown`）。`save` 在这之后跑。
- **save / attach**：
  - 有 `label` 就用它的标题；没有就以 `Unknown-<Source>` 挂上（网页快照是 `Snapshot-<Source>`），并在报告里列出。存档不等版本。
  - 这一轮挂上的 `Unknown`，同一轮里定下版本后可以直接改标题（原则 6 的例外）。这样 `Unknown` 只是这一轮里的过渡状态，不会每一份都变成要用户确认的改名。
  - 文件已经挂在条目上（md5 相同），但标题不合规范时，不顺手改名。把它列进报告的"建议改名"，归 §5 的流程，等用户确认。
- **report**：
  - 表里显示每份附件的标题；
  - "待清理附件"按 §1 的替换规则列出；
  - 另列出本次的 `Unknown` 和"建议改名"。

## 4. 读取时

- `kind_of_attachment` 改为解析规范标题：按 `-` 切开，第一段是版本词，第二段是来源，其余是 detail。
- 不合规范的标题，版本记为 `unknown`，并标 `standard: false`，不再按旧标题去猜。现有库改名以后，这类只剩新进来的非 p2z 附件，比如用户自己用 Connector 存的。
- `read_library pdf` 的每一行加上 `version`、`source`、`detail`、`standard`，按 §1 的顺序排。agent 想读哪个版本就取哪一行，SKILL.md 那一句随之改写。
- 第 2 步判断"库里已有什么"：
  - 只有 Preprint/Accepted 的条目，就知道正式版还缺；
  - **版本未知的 PDF 仍然算"条目已有 PDF"**（`run.py` 里判断是否已有论文 PDF 的那一处）。第 2 步照常停下，只告诉 agent 这份的版本没核实过；请求里点名要某个版本时，agent 才去看。
  - 否则改名前的约 800 个条目，以及以后用 Connector 存的每一份，都会被当成没有 PDF，又去取一遍。

## 5. 整理和一次性改名

- **lint** 新增两个检查，只看 PDF 和 HTML 快照，不看笔记、链接以及以后结构化包的 zip：
  - `nonstandard_title`：标题不合规范的附件，带上判断用的证据：附件 url 和网站、条目 DOI、首页开头几行。不带提议名，名字由 agent 定（原则 3、4）。合规范但没写来源、而附件 url 的网站有名字的快照（比如只写 `Snapshot` 的 ScienceDirect 快照），也列出来；
  - `label_clash`：同一条目里两份附件标题相同，多半是重复。例如 4 个条目各有两份 ScienceDirect 快照。
  - `superseded`：同一来源里按 §1 该让位的那份，例如 `Preprint-arXiv-v1` 旁边有 `Preprint-arXiv-v3`。原来的 `multiple_pdfs` 去掉了：多个版本并存是本规范的本意（§12）。
- **organize.md 加一节"附件改名"**：
  1. lint 列出不合规范的附件和证据；
  2. 脚本只定有十足把握的：网页快照、和已定文件逐字节相同的、文字层里由来源方原话写明了版本和来源的（比如 IEEE 下载戳加横幅或卷期页眉）。用这类规则前先抽几份看过；
  3. 其余的分批交给 sonnet subagent，每批约二十份：arXiv 编译的文件读文字和 arXiv 留言，其他文件看第 1、2 页的图片，提出新标题和决定它的那个标记；只读本地文件；
  4. 看文件定不了、要去出版方核对的，按网站分，每个网站一个、放慢；
  4. 仍定不了的写 `Unknown`；
  5. 整理成一张"旧标题 → 新标题"清单给用户；
  6. 用户确认后，用 `update_item` 改标题。这一步只走本地 API，不访问任何网站；改完回读核对。
- **现有的库**：
  - 顺序：读取端的改动一上线，lint 会把几乎所有附件标成不合规范，紧接着就做一次性改名。中间这段的提示是预期内的。
  - 规模：约 802 份 PDF 加 96 份快照。全库试命名时，约 30 份要多看一眼，19 份推断不出来源（这些只写版本词）。
  - 这次的调研结果（`rename-dryrun.json`、`doubtful-resolved.json`、`publisher-check-*.json`）可以直接用作第一轮的依据，不用再去访问网站。
  - 4 个条目各有两份 ScienceDirect 快照，列给用户，确认后删掉重复的。
  - 已知可以换成正式版的 9 个条目：4 个 ACM、3 个 npj、chenReasoningEraSurvey2026、guoMulticenterStudyAdaptability2024。列给用户，同意后走导入流程去取，守 §6。

## 6. 派出去的 subagent 守访问节奏

- 起因：2026-10-21 的调研里，一个 agent 在用户的 Chrome 里循环打开 dblp.org，详见 [20261021-paper-to-zotero-request-pacing-fixed.md](../issues/archive/20261021-paper-to-zotero-request-pacing-fixed.md)。所有 agent 用的都是用户的 IP、Chrome 和学校登录，网站看来就是同一个人。
- 脚本自己的请求已有 `p2zlib/web.py` 的按网站限速（`GAPS`），这一条照旧。
- SKILL.md 里每一份给 subagent 的说明（第 3 步的浏览器 agent、§2 和 §5 的核对 agent）都写进这几条：
  - 不对网站写循环，也不批量扫描。`Browser: yes` 的 OpenCLI adapter 绝不放进循环；
  - 同一网站同一时间只有一个 agent，两次请求之间至少隔几秒；
  - 碰到第一个机器人验证、403、429 或 Cloudflare 页就停，这一轮不再碰这个网站，也不绕过去；
  - 不准再派下级 agent。
- 并行按网站分：不同网站可以并行，最多 10 个；同一网站只能一个接一个。只读本地文件的 subagent 不受网站限制。

## 7. 为以后的版本升级留的标记

- 带 `in_press` 的、只有 Preprint/Accepted/Unknown 的条目，是以后检查"有没有更新版本"的对象。
- 现在先不自动检查。调研里看到的可能线索：
  - Crossref 后来补上的卷期页码；
  - OpenReview 的 venue 字段；
  - arXiv 每个版本各自的 comment；
  - 出版方页面上的 in-press 标记。
- 等以后按 §6 的规矩重做调研再定，另写 spec。

## 8. 已知限制

- Zotero 双击条目时打开哪一份，完全不看标题：先 PDF，再附件 url 等于条目 url 的，再按添加时间（Zotero 源码 `item.js`）。规范标题改变不了这一点。agent 按 `read_library pdf` 的顺序取，用户想看哪份自己点。
- 以后用户自己用 Connector 存的附件，标题仍是 Zotero 给的，下次 lint 时列出来改名。

## 9. 验证

- **测试**：几个端到端的测试就够。
  - 从 arXiv 取一篇：记录里有 `vN`，附件标题是确认后的 `Preprint-arXiv-vN` 或 `Accepted-arXiv-vN`；
  - 一份没人确认的文件：照样挂上，标题是 `Unknown-<Source>`，报告里列出；
  - 同一来源来了新文件：旧的进"待清理附件"；
  - `read_library pdf` 能解析规范标题、排序正确；不合规范的给出 `standard: false`，仍算"条目已有 PDF"；
  - lint 列出 `nonstandard_title`（带证据）和 `label_clash`。
- **真实库**：
  - 先只读跑一遍 lint，对照 2026-10-21 的试命名结果；
  - 改名清单给用户确认后再写；
  - 写完回读核对。

## 10. 自审改了什么（2026-10-21）

用户要我按原则再审一遍，"避免这种低级的、原则上的问题"。改了这些：
- **"这次做什么"里写着"保存时判定版本"**，和原则 2 矛盾，改成"取文件时"。
- **脚本按"线索和证据是否一致"判断有没有把握**：这要靠关键词去解读页面和文件，等于把出版方的识别方法写死（违反原则 3）。改为：脚本只按路线给默认版本，每一遍结束时由 agent 看一张表来确认。默认版本可能错，所以一律要确认，确认不了的标 `Unknown`。
- **"和已知版本的哈希比对"写在下载时的证据里**：下载那一刻没有可比的已知版本。挪到判断用的证据里，那是 subagent 核对时的工具。
- **lint 带"提议名"**：提议名要靠关键词规则才能给出（违反原则 3、4），改成只带证据，名字由 agent 定。
- **同一来源替换的规则会误伤**：`Supplement-Nature` 和 `Published-Nature` 同一来源，按原写法会互相取代。改为只在论文本身的版本之间按"最好、最新"比；补充材料按 detail 比，快照每个来源一份。
- **arXiv 版本号要每篇多发一次请求**：prepare 本来就查过 arXiv API，返回里有最新版本号，改为那时记下，不另发请求（原则 5）。
- **文件已经挂着、标题不合规范时**：原稿没说怎么办。改为不顺手改名，列进"建议改名"等用户确认（原则 6）。
- **lint 的范围**没写：限定为 PDF 和快照，不碰笔记和以后结构化包的 zip。
- 补了 §8 已知限制：Zotero 双击打开哪份不受标题影响。
- 最后一遍自审：补上"顶替 PDF 的快照，在 PDF 到了以后列进待清理"（现有行为，原稿的快照规则没覆盖到）；注明被替换的 PDF 的结构化包回结构化包那张 issue 定。
- **advisor 第二轮**又指出四处，已改：
  - 第 3 步没写"版本确认完才 save"，agent 先跑 `save` 就会全挂成 `Unknown`，之后每份改名都要用户确认。改为第 3 步的完成条件包括 `label`；这一轮挂上的附件，同一轮里可以直接改标题。
  - prepare 查 arXiv 只覆盖预印本的记录，补了 fetch 的批量兜底。
  - open 路线的默认版本原来用了含 OpenAlex 成分的链接版本，和"OpenAlex 不能当证据"自相矛盾，改为只看网站。
  - 补了三处小规则：经学校代理的地址先还原再对照来源名；替换规则遇到完全相同时留后加的；`verify.kind_of` 的页边戳规则并入证据。

## 11. 要改的文件（大致）

- `scripts/p2zlib/paper.py`：
  - 版本词；
  - 标题的生成和解析；
  - 来源名的规范化；
  - 网站到来源名的起始对照表（可扩充）；
  - 排序和替换规则。
- `scripts/doi_to_item.py`：记下 arXiv 最新版本号。
- `scripts/fetch.py`、`scripts/p2zlib/browser.py`：
  - 记下实际下载地址和页面证据；
  - arXiv 带 `vN`，prepare 没查到的用一次批量请求补上；
  - 每一遍结束时输出待确认表。
- `scripts/p2zlib/verify.py`、`scripts/p2zlib/run.py`：claim 写 `label_proposal`；记录的 `label` 字段；`kind_of` 的页边戳规则并入证据；第 3 步完成条件含 `label`。
- `scripts/p2zlib/zotero.py`、`scripts/attach_file.py`：按 `label` 写标题，没有就写 `Unknown-<Source>`；这一轮挂上的可以按后定的 `label` 改名，别的已挂附件不改。
- `scripts/read_library.py`、`scripts/report.py`、`scripts/lint_items.py`、`p2zlib/run.py` 的"已有 PDF"判断：§3–§5。
- `SKILL.md`：
  - 第 3 步：当场确认版本；浏览器 agent 报回版本和依据；
  - 第 4 步：没定的以 `Unknown` 挂上；
  - subagent 的派发规矩；
  - 改写 `read_library` 那一句。
- `references/attachment-titles.md`（新）：命名规范、版本定义、证据，导入和改名两处共用。
- `references/organize.md`：改名一节。
- `references/publishers.md`：2026-10 的探查线索，带日期。
- 测试：按 §9。

## 12. 实现时的修正（2026-10-21）

- **证据和默认版本写进 claim 事件，不写进记录的 `label_proposal`**：后台的 watcher 进程也会调 claim，它写记录时 agent 可能正在写 `label`，会互相覆盖。`fetch.jsonl` 只追加，没有这个问题，也合 run.py 原来"文件的事实在 fetch.jsonl"的设计。记录里只有 agent 写的 `label`。fetch 一遍跑完输出的 `to_label` 行就从这些事件里取。
- **lint 去掉 `multiple_pdfs`，加 `superseded`**：多份 PDF 并存是规范的本意，再报它就是噪音；该清理的是同一来源里让位的那份。替换规则只看合规范、写了来源的标题，免得改名前把两份旧标题的 PDF 误判成一份取代另一份。
- **`nonstandard_title` 也列"合规范但没写来源"的快照**：库里约 96 份快照的标题就是 `Snapshot`，按语法是合规范的，不这样就进不了改名清单。只在附件 url 的网站有名字时才列，而且只看快照：快照的 url 就是它存下的网页；PDF 的 url 多半抄的是条目的，说明不了从哪下载，改名时故意不写来源的 PDF 不该每次都被列出来。
- **没有 `label` 的网页快照挂成 `Snapshot-<Source>`**：快照是什么，看字节就知道，不需要确认。
- **读回附件时**：每份附件的 `version`（小写）、`source`、`detail`、`standard` 来自标题；`kind` 仍只表示工作目录里文件名带的"想要的版本"。回收站里的附件不再算。
- **arXiv 版本号的请求挪到 `web.arxiv_entries`**，prepare 和 fetch 共用一份。fetch 只在第一次碰到不带 vN 的 arXiv 链接时，为这一遍所有缺版本号的 arXiv 链接发一次请求。
- **`SITE_VERSIONS`（arXiv、bioRxiv、medRxiv → Preprint）** 放在 `paper.py`，open 路线的默认版本和 `fulltext_links` 的链接版本共用。
- **测试**：全部 27 个测试文件通过；新增的覆盖 §9 列的五条。fetch 的测试里 arXiv API 指向本地假服务，不碰真网站。
- **缺 `vN` 的不判定让位**（2026-10-22，用户同意）：原来缺 `vN` 当 v0，一份取不到版本号的 arXiv 文件会自动让位给有版本号的，可它可能更新。"缺一方就按添加时间比"排不出一致的先后（会绕成一圈），所以改成不判定、两份都留。列出顺序不变：没写版本号的排在有版本号的后面。
- **全面复查后又改了三处**（2026-10-22，用户让我全部过一遍）：
  - 预印本服务器的文件，不管走哪条路线都默认 Preprint。原来 publisher 路线一律默认 Published，可预印本条目自己的 DOI（`10.48550/arXiv.…`）会把 publisher 路线带到 arXiv，库里约 110 个预印本条目都会被默认成 `Published-arXiv`。从不带版本号的 arXiv 地址取到的文件，也补上 arXiv 当时给的最新 vN。
  - Chrome 在 fetch 打开的链接上直接下载、再由 watcher 从 Downloads 认领的文件，原来丢了 fetch 手上的路线、地址、页面和链接文字。PMC、OUP、ACM 都是这样下载的。现在 fetch 补一条 `arrival` 事件记下这些。
  - agent 用 `claim --accept` 收下被检查拒掉的文件时，沿用那份文件先前 claim 事件里的路线和证据，不再从零开始。
  - 复查这三处时又发现并改了：网页快照一律默认 `Snapshot`（不跟着网站成了 Preprint），快照的地址不改写成 arXiv PDF 地址；待确认表只列 PDF；watcher 的 claim 事件和 fetch 的 arrival 事件合起来读，不会互相盖掉。
- **逐份看图核对示例后的修正**（2026-10-27，用户要我对照每份文件第 1、2 页确认新标题，并提醒标记可能在图片里）：渲染 16 份示例文件的第 1、2 页逐份看过，又看了 11 个年份的 CVF 水印和 3 份 MICCAI 水印。
  - CVF 开放版按水印定版本：CVPR 2016 到 2018 写"与 IEEE Xplore 上的版本相同"，页上还有论文集页码，算 Published；2019 年起写"与接收版相同"，算 Accepted。原来一律算 Accepted，CycleGAN 的 CVF 版因此改成 `Published-CVF`。
  - chung 的 Radiology 版首页印着 "Radiology 2022; 000:1–8"，卷号还是 000，是进卷期前的在线版，应为 `Published-RSNA-in_press`。试命名时漏了：这行字在首页约第 800 个字符处，原来的摘录只有 300（lint）和 600（claim）个字符。摘录改成首页 1500 个字符、第 2 页 600 个字符。
  - Preprint 的定义放宽：作者自己发布、没写明已接收的版本，包括接收后自行扩充修改的（CycleGAN 的 arXiv v7）。写明已接收的仍算 Accepted（kim 的 arXiv v3 印着 "Published as a conference paper at ICLR 2024"）。
  - 一份附件网址是 CVF、首页却没有 CVF 水印的文件（mao2017least），说明网址不能当证据。
  - 改名流程：每份文件都要看第 1、2 页的图片，不只看文字摘录。
- **脚本有十足把握的才由脚本定，其余交给 sonnet subagent**（2026-10-27，用户重申的原则）：改名流程原来写成每份文件都由 subagent 看图，改为先用脚本定确定无疑的（全库约 97 份快照、6 份重复文件、IEEE 下载的大部分），其余按类交给 subagent。导入时也一样：证据确定无疑的待确认行，agent 自己定；有疑问的才交给 subagent。
- **OpenReview 的文件一律带状态**（2026-10-27，用户让我考虑，我定的）：原文"照抄 OpenReview 给的状态"没说是否一律写，10-21 的试命名也没带，约 45 个条目受影响。定为一律写：同一个 OpenReview 地址会先后给投稿版、修订版和终稿，OpenReview 上又有许多会议，状态说明这是哪一份；规则一律化，agent 也不用每次判断要不要写。状态从首页读（ICLR、TMLR 的页眉，NeurIPS、ICML 首页的脚注），读不到再看 OpenReview 的 venue 字段。
- **证据按"来源方的话、文件的话"统一组织**（2026-10-27，用户：导入时网页信息更全，应先看网页；给库里文件改名时手里只有 PDF）：
  - 导入时先看来源方的话：fetch 取文件时，记下页面上标题附近的文字（标签、日期、卷期，不只是 PDF 按钮旁的字）；arXiv 文件记下该版本的留言和期刊信息，不管字节是怎么取到的。待确认行先列来源方的话，再列文件的话。
  - 库里已有的文件先看文件的话：网站显示的是今天的状态，只有确认它给的就是同一份文件，才能拿来定名。改名流程去网站核对那一步写明了这一点。
- **一次性改名时的修正**（2026-10-27，按 §5 给 922 个附件改名的过程中发现）：
  - CVF 上 ECCV 2018、ACCV 的副本，水印写"作者制作的版本，内容与 LNCS 版相同"，按定义算 Accepted。attachment-titles.md 里 CycleGAN 的例子跟着改成 `Published-CVF`，与上面按水印定版本的规则一致。
  - arXiv 的某一版，留言写明已接收，即使文件首页还印着 NeurIPS 模板默认的 "Preprint." 也算 Accepted。给 subagent 的说明起初写成"两者矛盾时以文件为准"，判错了 2 份，已纠正。
  - subagent 不会自己去看图：说明里写"要看图"不够，要把"每份文件的两页图片都看过"写成完成条件。organize.md 和 SKILL.md 已补上。
  - 来源列表补上这次见到的名字（PNAS、PLOS、IOP、SPIE、Thieme、BMC、Frontiers、Lirias、ProQuest、EBSCO 等），`SOURCES` 也补了对应的网站。从数据库（ProQuest、EBSCO）下载的文件，来源写数据库，不写排版的出版社。
  - HAL 只把存档文件标成"作者提供的文件"，分不出接收稿和投稿稿；Pure 系的机构库（如 Edge Hill）会写明 "Accepted author manuscript"。都写进了 publishers.md。
