# paper-to-zotero：附件的版本只靠标题前缀认，8 个条目分不出哪份是论文的 PDF

- 来源：2026-10-20，讨论 [20261020-paper-to-zotero-structured-package.md](20261020-paper-to-zotero-structured-package.md) 的"多个 PDF 怎么办"时，只读统计发现。用户：「取 PDF 那个是 paper to zotero 的一个问题，你提一张 issue」
- 状态：open。方向已定，见"已定的方向"：保存时规范命名。正在调研有哪些版本。
- 经过：2026-10-20 用户说先解决这张，我没先给方案就改了代码（没提交，Zotero 没写，只跑了 dry-run）。用户叫停：「去解决这个 issue，应该是你先给我预览方案，你啥都没给我看，然后就直接去解决它」。之后两次重述方向，第二次才对。

## 现场

用 `p2zlib` 只读遍历库里所有 PDF 附件，按条目分组，用 `paper.kind_of_attachment` 认版本、`paper.kind_rank` 排序。这和 `read_library pdf`（经 `zotero.attachments`）用的是同一套逻辑。

785 个条目有 PDF，其中 17 个有两份。有 8 个条目，两份都被认成 `published`，排第一的位置并列：

| 条目 | 两份附件的标题 | 实际（看标题判断） |
|---|---|---|
| `chungDeepLearningSimulate2023`（`46GUJFLD`） | Published version (Radiology)；Author manuscript (eScholarship, UCSF) | 正式版 + 作者稿 |
| `choHybridDeepLearning2026`（`BTPFQVU5`） | Published version — Medical Physics 2026；Related preprint v1 — formal author list differs | 正式版 + 预印本 |
| `shamsolmoaliImageSynthesisAdversarial2021`（`NCZTJNVW`） | PDF；已提交版本 | 正式版 + 投稿版（推断："已提交版本"是 Zotero 中文界面下的 Submitted Version） |
| `liuPerceptionConsistencyUltrasound2023`（`7HR8LLQL`） | Full Text PDF；Full text PDF | 分不出 |
| `liEnhancingAdaptingClinic2024`（`H35M5ZN4`） | Full Text PDF；Full Text PDF | 分不出 |
| `sahariaPaletteImagetoImageDiffusion2022`（`M5C7LE2E`） | Full Text PDF；Full Text PDF | 分不出 |
| `liReviewDeepLearning2021`（`P3IP65ZL`） | PDF；全文 | 分不出 |
| `zhuUnpairedImagetoImageTranslation2017`（`VNEXSRV2`） | PDF；Full Text PDF | 分不出 |

还有一份认错了，但没有并列：`shaoGivenGatheredEvidence2026`（`35UG627E`）的 "Full Text PDF (OpenReview, ICLR 2027 submission)" 被认成 `published`，其实是投稿版。

## 机制

- `paper.kind_of_attachment` 只看标题前缀（`TITLE_PREFIXES`：preprint、submitted version、arxiv fulltext pdf、accepted manuscript、accepted version、supplement、snapshot）。不匹配的 PDF 一律算 `published`。
- `zotero.attachments` 按（版本等级，添加时间）排序。并列时谁先加进库谁排第一，跟实际版本无关。
- 标题来自好几个地方：
  - Zotero Connector 写的 "Full Text PDF"；
  - Zotero 按界面语言写的 "已提交版本"、"全文"（推断）；
  - 早期的运行或手写的标题，比如 "Author manuscript"、"Related preprint"。

## 为什么要处理

- `read_library pdf` 说"论文的 PDF 排第一"，别的技能就靠这一份去读或解析。结构化包的提议也是"默认只解析排第一的那份"。这 8 个条目上，排第一的是先加进库的那份，不一定是正式版：比如 `chungDeepLearningSimulate2023` 可能拿到作者稿。
- （推断）第 2 步判断库里已有什么（`found`）也看版本。一份被认成 `published` 的预印本，会让 agent 以为正式版已经在库里了，于是不再去取。

## 2026-10-20 再查到的（只读）

- **8 个并列的都是版本对，没有真重复。** 看了每份的第 1 页和下载来源（附件的 url）：
  - 6 个是正式版加一份 arXiv 版：cho、shamsolmoali、liuPerception、liEnhancing、saharia、zhu。其中 5 个（除 saharia）排第一的是 arXiv 版，因为它先加进库。
  - chung：eScholarship 那份内页是 "HHS Public Access Author manuscript"，是接收稿；另一份是 RSNA 正式版。接收稿先加进库，排第一。
  - liReview：HAL 那份（"全文"）抬头是 "Version of Record: …sciencedirect… Manuscript_…"，是接收稿；"PDF" 那份是 Elsevier 排版后的在线优先版。HAL 那份先加进库，排第一。
  - 所以 8 个里有 7 个现在排第一的不是正式版。
- **附件的 url 记着文件从哪下载。** Zotero Connector 和"查找可用 PDF"存的是文件地址，比如 `arxiv.org/pdf/…`。p2z 自己挂附件时存的是条目的 url（`attach_file` 的约定）。
- **OpenReview 不能当预印本服务器。** ICLR、TMLR 的正式版就在 OpenReview 上。按 url 认的话，会把 52 个 OpenReview 下载的 PDF 错认成预印本。
- **条目 url 那条排除是必要的。** `jinSearchR1TrainingLLMs2025` 唯一的 PDF 是 p2z 挂的 COLM 正式版（第 1 页 "Published as a conference paper at COLM 2025"），附件 url 是条目自己的 arXiv 摘要页。
- **只看"只放预印本的服务器"、且附件 url 不等于条目 url 时**，全库有这些变化：
  - 6 个多 PDF 条目排对；
  - 14 个期刊、会议条目唯一的 PDF 其实是 arXiv 版，原来被当成正式版，现在认成预印本。逐个看过第 1 页：12 个有 arXiv 页边戳；另外 2 个没有戳，但都是从 `arxiv.org/pdf/…` 下载的；
  - 74 个本身是预印本的条目，PDF 认成预印本，与事实一致。

## 已定的方向（用户 2026-10-20）

「我指的是一开始保存pdf的时候就应该分清楚，取好名字，因为在下载的时候，我们就清楚了它来自于哪里。规范命名，这个问题不就解决了吗？如果有多个版本，你想打开哪个就打开哪个，结构化也可以全部结构化。」

- 根源在保存的时候：下载时就知道文件是哪个版本、从哪来，当场按一套规范起名。读的时候认名字，不再猜。
- 用户确认这个理解（2026-10-20）：「这次理解的对了。这样才能从根源上解决这些问题。你在下游修修补补，改得要死，还是那一样的结果。你从上游根源上解决问题，那所有的一切都解决了吧。有哪些版本？这些都已经是覆盖全部了吗？我不太清楚，你先去调研一下。」
- 用户（2026-10-20）：「你不应该去调研我Zotero里面存的PDF都是是什么版本的吗？」我已只读盘点全库 802 份 PDF 加 96 份快照，见参考材料目录里的 `library-inventory.md`。要点：
  - 前几次运行已经自己造出现有 5 类以外的名字（"Open access version (CVF)"、"Proceedings version"、"Camera-ready"、"Author version"），也把校样、Early Access 塞进了 "Accepted manuscript"；
  - "PDF" 和 "Full Text PDF" 底下什么版本都有；
  - "版本"和"来源"是两回事。
- 下一步：调研论文有哪些版本、p2z 现有 5 类（published、accepted、preprint、supplement、snapshot）够不够。结果写进本 issue 的参考材料目录 `20261020-paper-to-zotero-pdf-version-by-title-reference/versions-research.md`，结论再浓缩进这里。之后给用户出命名规范和整理方案，用户点头后再动手。
- "读时按 url 认版本"的代码改动已还原（2026-10-20，从没提交过）。

## 调研结论（2026-10-20）

参考材料目录下有两份：`versions-research.md`（标准和 Zotero 源码），`library-inventory.md`（库里实际情况）。下面"推断"是我的判断，其余有来源。

- **标准**：NISO RP-8-2026（2026-10-05 发布，DOI 10.3789/niso-rp-8-2026，我核对过出版物页）把论文分 6 个阶段：
  - AO 作者原稿、SMUR 投稿审稿中、PMUR 公开评审中（新增）、AM 接收稿、PF 校样、VoR 正式版；
  - 更正版、增强版、撤稿都算 VoR 的后续版本号，不单列；
  - "preprint" 不是阶段，是"公开发出来了"这个属性，落在 AO、SMUR、PMUR 上；
  - COAR、OpenAIRE、Unpaywall、OpenAlex、Open Policy Finder 都更粗，最细的也只有投稿、接收、正式三档，外加"未知"（NA 或 null）。
- **p2z 的 5 类**：
  - 正式版、接收稿、预印本覆盖了 6 个阶段里的 5 个（AO、SMUR、PMUR 归预印本）；
  - 补充材料和快照不是版本，是内容的一部分和文件格式，保留；
  - 缺"校样、在线优先"（PF：排好版、还会换成终版的，如 Elsevier 的 `JID:` 校样）。库里真正的校样只有约 3 份，比如 liReview 的 "PDF"。
    - 更正（2026-10-21）：之前说"11 份"有误。其中 8 份是 npj Digital Medicine 的 "Article in Press"，首页写着 "We are providing an unedited version of this manuscript"，是未编辑的接收稿，标成接收稿是对的。
    - IEEE Early Access 那份（`maTinyUSFMCompactEfficient2026`）首页写着 "This is the author's version which has not been fully edited"，也是接收稿；
  - 缺"未知"：没证据时现在默认算正式版。
- **版本和来源是两条轴**：arXiv、OpenReview、PMC、HAL、eScholarship 上都同时放着几种版本，来源推不出版本。版本要看保存时手上的证据：首页标注、来源的元数据、会议的声明。
  - CVF、MICCAI 的开放版：会议自己说与接收稿一致，所以是接收稿；
  - arXiv 上的终稿副本：内容是接收稿（推断，按 NISO 2026 §2.3.4 注 4）。
- **Zotero 自己**（我核对过 `attachments.js` 的 `_getTitleFromVersion`）：
  - "查找可用 PDF" 按 Unpaywall 起名，接收版叫"已接受版本 / Accepted Version"，投稿版叫"已提交版本 / Submitted Version"，正式版和没标版本的都叫"全文 / Full Text"，按保存时的界面语言写死；
  - "Full Text PDF"、"Preprint PDF"、"Snapshot" 来自 Connector 和网站译者；"PDF" 是 Zotero 7 给第一个 PDF 的默认标题；
  - "按父条目重命名文件"只改文件名；
  - Zotero 双击打开哪一份完全不看标题：先 PDF，再附件 url 等于条目 url 的，再按添加时间。
- 多个版本都留着，各有清楚的名字，要哪个开哪个。
- 下面我那次"一个条目只留一份论文 PDF"的重述理解错了，作废；"读时按 url 认版本"的方案也作废。
- 现状（读代码）：
  - p2z 保存时其实知道文件来源：`attach_file` 从 `fetch.jsonl` 取 `source`，但只拿来给预印本的标题写服务器名。
  - 正式版的标题就是 "PDF"，跟 Zotero 自己的通用标题撞了，分不出来。
  - 文件名用 Zotero 的默认格式，不带版本。
  - 库里现有标题是各次运行、各个会话各写各的（"PDF (published version)"、"Published version (IEEE Xplore)"、"Published version — Medical Physics 2026"、"Author manuscript (eScholarship, UCSF)"、"Related preprint v1 — …"），加上 Zotero 和 Connector 的 "Full Text PDF"、"已提交版本"、"全文"。

## 命名方案 v2（2026-10-21 调研之后提出；方向用户已同意，书写细节待定）

用户（2026-10-21）：「可以，但是命名细节你要和我确定，大小写 - _ 之类的，我不太喜欢有空格」。
- v2 整体和三处决定都定了：
  - 用短词（Published、Accepted…）；
  - 校样并入 Published，标 `in press`；
  - 同一来源的新文件替换旧的，不同来源的并存。
- 下面表里带空格和括号的写法只是示意。具体书写（分隔符、大小写、来源名怎么写）一件一件和用户定。
- **已定（2026-10-21，用户在四种写法里选的）**：
  - 不用空格；字段之间用 `_`，一个字段里有多个词时用 `-`；
  - 版本词首字母大写，来源保留自己的写法；
  - 来源用简短的品牌名。
  - 例子：`Published_RSNA`、`Published_OpenReview_ICLR-2023`、`Published_Elsevier_in-press`、`Accepted_CVF`、`Accepted_arXiv_v3`、`Accepted_IEEE_in-press`、`Preprint_arXiv_v7`、`Preprint_OpenReview_ICLR-2027-submission`、`Supplement_Nature`、`Snapshot_Elsevier`、`Unknown`。
  - 另外三种（全小写、点号分隔、连字符加驼峰）没选。
- **已定（2026-10-21）：来源用品牌短名，不用网站全名**。
  - 来源是开放列表，新网站按同样规则加：arXiv、OpenReview、CVF、ECVA、MICCAI、NeurIPS、PMLR、ICLR、ACL、AAAI、JMLR、IEEE、Elsevier、Springer、Nature、ACM、Wiley、RSNA、BMJ、NEJM、Science、MDPI、JMIR、OUP、PMC、Europe-PMC、HAL、eScholarship、ResearchGate、Research-Square、EasyChair、author-page。
  - 补充字段的固定写法：
    - `vN`：预印本服务器的版本号；
    - `in-press`；
    - `ICLR-2023`：OpenReview 上的会议终稿；
    - `ICLR-2027-submission`：OpenReview 投稿版；
    - `source-data` 一类：同一来源有多份补充材料时；
    - `abstract-booklet-p66`：合集里的一篇。
  - 例子：`Accepted_IEEE_in-press`、`Preprint_arXiv_v7`、`Supplement_Nature_source-data`、`Published_T-CAIREM_abstract-booklet-p66`。
- 用户（2026-10-21）：「记得这些名称不是固定的，如果有新的来，你可以按照我们原有的规则，自己新加，现在列举的是一个template，而不是固定库，你应该清楚吧。」
  - 来源名和补充写法都只是模板，不是封闭的清单。新情况由 agent 按同样的规则自己加，并在报告里说明。spec 和 skill 里要写明这一点。
- 用户又问：「我怎么记得-是用在不同字段间的，_是一个字段内的」。我选项里给的是 `_` 分字段、`-` 连字段内的词，用户当时选的也是这一种。现在请用户再确认一次，确认前不往下推进。
- 我对比了两种分工：
  - `_` 在正则里算单词字符、双击会整体选中，Google 把 `-` 当空格；
  - 名字自带的 `-`（T-CAIREM、日期）在"`-` 分字段"的写法下得改写。
  - 我建议 `_` 分字段。
- 用户：「我印象中-是"分隔符"，而_是"连接符（整体）"」。
- **还没定**：用户说「不是，我还没定呢，你两种方案，左右对比给我看一下」。我把用户的印象当成决定记早了，已改回待定。另一种方案是 `-` 分隔字段、`_` 把一个字段里的词连成整体：
  - 名字自带的 `-` 一律改成 `_`：`T_CAIREM`、`Europe_PMC`、`Research_Square`、`author_page`；
  - 程序按 `-` 切字段；
  - 例子：`Published-RSNA`、`Published-OpenReview-ICLR_2023`、`Published-Elsevier-in_press`、`Accepted-CVF`、`Accepted-arXiv-v3`、`Accepted-IEEE-in_press`、`Preprint-arXiv-v7`、`Preprint-OpenReview-ICLR_2027_submission`、`Supplement-Nature-source_data`、`Snapshot-Elsevier`、`Published-T_CAIREM-abstract_booklet_p66`、`Unknown`。
- 用户要我综合评估后推荐（2026-10-21）。我改为推荐方案二（`-` 分隔字段，`_` 连接词）。理由：
  - 符号的意思和用户的直觉、正则和双击的规则都一致；
  - Zotero 自己默认的文件名 "作者 - 年份 - 标题" 也是用 `-` 隔开字段；
  - 方案一的主要优点"名字自带的 `-` 能原样保留"，在库里几乎用不上：试命名用到的来源名和补充写法里，只有 T-CAIREM 一个自带 `-`，别的多词名都是空格，两种方案都要改写；标题里也不放日期。
  - 等用户定。
- **已定（2026-10-21，用户：「可以」）：方案二**。
  - 字段之间用 `-`；一个字段里的空格和自带的 `-`，一律换成 `_`。
  - 版本词首字母大写，来源名保持原写法。
  - 例子：`Published-Elsevier-in_press`、`Accepted-IEEE-in_press`、`Accepted-Europe_PMC`、`Preprint-arXiv-v7`、`Preprint-OpenReview-ICLR_2027_submission`、`Supplement-Nature-source_data`、`Published-T_CAIREM-abstract_booklet_p66`、`Unknown`。
  - 上面所有 `_` 分字段的例子都按这条改写。
- 命名书写到此定完。下一步是写 spec 并审查，然后给用户看实施方案，等用户同意再改代码。
- spec 草稿：[20261021-paper-to-zotero-attachment-naming-spec.md](../specs/20261021-paper-to-zotero-attachment-naming-spec.md)（2026-10-21，advisor 审过一轮，已按意见改）。等用户看。
- 用户（2026-10-21）：「注意pdf version是在出版商网页或者下载pdf以及初步检查的时候就能大致确定的，不要事后再去做，事后再做就缺了很多信息了」。
  - 草稿原来把判定放到了保存时，已改成：
    - 取文件时当场记下页面证据（元数据、版本标签、链接文字）；
    - claim 初查时提议，浏览器 agent 当场报版本；
    - 每一遍结束前定完；
    - save 只兜底。
  - 现有库的改名只能事后做，所以更依赖内容和去出版方核对。
- 用户（2026-10-21）：「"只做兜底检查。没定版本的不上传" 这个不太对，我们zotero的目标肯定是获得全文的pdf并存档，如果不确定版本，但是有pdf，最后文献存档的目标是不能阻塞，如果就是应为不确定版本而丢弃了pdf，就会因小失大了，不确定就标unknown。」
  - spec 已改：版本定不了绝不挡住存档。
- 用户：「你自己在审查一遍，避免这种低级的，原则上的问题。整个处理要符合原则，合理、高效、优雅、考虑全面。」
  - spec 重写了一遍，开头列出 6 条原则：存档第一；在信息最全的那一刻定；只定义、不写死识别方法；脚本记事实、agent 下判断；对外访问守规矩；改库要用户点头。
  - 自审和 advisor 第二轮找到的问题记在 spec §10。
  - 文件通过"是不是这篇论文"的检查就挂上；没定版本的以 `Unknown-<Source>` 挂上，报告里列出，之后再细看。

**附件标题 = `<Version> (<Source>[, <detail>])`**

| Version | 定义（按 NISO RP-8-2026） | 库里的例子 → 新标题 |
|---|---|---|
| `Published` | 出版方定稿的那份：期刊出版社、会议论文集、OpenReview 上 ICLR/TMLR 的终稿 | chung 的 RSNA 版 → `Published (RSNA)`；yaoReAct → `Published (OpenReview, ICLR 2023)` |
| `Accepted` | 审完接收的文字，但不是出版方定稿的那份：PMC 作者稿、CVF/ECVA/MICCAI 开放版、arXiv 上写明接收的版本、未编辑的 in press 稿 | zhu 的 CVF 版 → `Accepted (CVF)`；kimUnpaired → `Accepted (arXiv v3)` |
| `Preprint` | 接收前公开的：arXiv 预印本、OpenReview 投稿版 | zhu 的 arXiv 版 → `Preprint (arXiv v7)`；shao → `Preprint (OpenReview, ICLR 2027 submission)` |
| `Supplement` | 补充材料 | xuLLM2026 → `Supplement (Nature)` |
| `Snapshot` | 网页快照 | liReview → `Snapshot (ScienceDirect)` |
| `Unknown` | subagent 看过、去出版商核对过也定不了 | jeong → `Unknown (author copy)` |

- **Source**：文件从哪个网站下载的，写网站的通用名（arXiv、OpenReview、IEEE Xplore、ScienceDirect、SpringerLink、Nature、PMC、CVF、HAL、author page 等）。这是开放列表，可以扩充。
- **detail** 只写区分得着的，几个固定写法：
  - arXiv 必写 `vN`，因为不带版本号的地址会变；
  - `in press`：还没进最终卷期、以后会被换掉的版本。IEEE Early Access、Elsevier Article in Press、Nature Article in Press、Wiley Early View、ACM Just Accepted 都用这一个词，例如 `Published (ScienceDirect, in press)`、`Accepted (IEEE Xplore, in press)`；
  - OpenReview 照写它给的状态，例如 `ICLR 2027 submission`；
  - 合集里的一篇写位置，例如 `abstract booklet p. 66`。
- **多个版本和升级**：
  - 不同来源的文件并存。同一个来源来了更新的文件，就替换旧的，旧的进回收站要用户确认。例如 arXiv v1 换成 v3，`in press` 换成同一网站的最终版。
  - 列出来时按 Published、Accepted、Preprint、Unknown 排；同一级里，不带 `in press` 的在前。
  - 带 `in press` 的、只有 Preprint/Accepted 的条目，是以后检查"有没有更新版本"的对象。具体怎么检查，等版本升级那部分按新规矩重做完再定。
- **怎么定版本**（流程，不按出版社写死规则）：
  - 保存时，脚本只收集证据：下载地址、页面元数据、PDF 首页文字（必要时渲染成图）、PDF 里的日期、和已知版本的哈希比对。
  - agent 按上面的定义判断；把握不大的交给后台 sonnet subagent 看文件、去出版商核对（每个网站同一时间只派一个，放慢节奏）；仍定不了就写 Unknown。
  - 各出版社观察到的标识，写进 publishers.md 当带日期的线索。
  - 最有力的通用证据有三样：
    - 和已知版本逐字节相同；
    - 文件日期落在投稿、接收、上线之间的哪一段；
    - 托管网站自己对这份文件的说明。
  - Unpaywall 和 Zotero 写的"已提交版本""全文"不能当证据。
- 文件名不变；版本只写在标题里。
- 现有的库一次性改名：
  - 证据明确的直接拟名；存疑的交给 subagent，先读本地文件，要访问网站的按每个网站一个 agent、放慢节奏；
  - 清单给用户确认后，用 `update_item` 写标题。这一步走本地 API，不访问任何网站。
- 已经找到、可以换成正式版的：
  - 4 个 ACM 条目（库里是 arXiv 版，正式版开放获取）；
  - 3 个 npj 条目（库里是 in press，最终版已出）；
  - chenReasoningEraSurvey2026；
  - guoMulticenterStudyAdaptability2024。

补充两条：
- 来源不知道时不写括号，只写 `Unknown` 或 `Published`。jeong 那份是 `Unknown`，不写 `(author copy)`。
- 预印本条目自己的 PDF 也照写，例如 `Preprint (arXiv v2)`，不再叫 "PDF"。涉及 110 个条目。

**全库试命名**（只读本地文件，结果在 `rename-dryrun.json`）：
- 898 个附件：Published 417、Preprint 212、Accepted 170、Snapshot 96、Supplement 2、Unknown 1，其中带 `in press` 的 16 个。
- 409 个的来源不是下载记录给的。这些是 p2z 以前存的文件，附件 url 抄的是条目的 url，来源只能从 DOI 和文件内容推断。
- 约 30 个要 subagent 再看：
  - 19 个推断不出来源；
  - 7 个 npj 的 in press 分不清是未编辑稿还是排了版的；
  - 3 个 arXiv 文件找不到版本号 vN；
  - 还有个别低把握的。
- 撞名 4 个：4 个条目各有两份 ScienceDirect 快照，是重复，要整理。
- 来源名称要统一写法。agent 写的 "MICCAI Open Access"、"OpenReview (TMLR)"、"ECVA open-access PDF" 改写成 MICCAI、OpenReview、ECVA。
- 版本升级怎么检查还没定：这部分调研因循环事故被叫停了。现在的方案先提供 `vN`、`in press` 这两个标记，以及"只有 Preprint/Accepted 的条目是检查对象"这一条；具体机制以后按新的访问规矩再做。

上面这一版取代下面那份草案。下面那份用的是长名称 "Published version" 等，校样还单独列了一类。

## 命名规范草案（没拍板，2026-10-21 给用户；已被上面 v2 取代）

用户：「我没太看懂你未来会定成什么？你规范一下」。下面是把所有待定点按我的建议定下后的完整草案。

**附件标题 = `<版本> (<来源>[, <补充>])`**

| 版本 | 标题开头（固定） | 什么时候用 |
|---|---|---|
| 正式版 | `Published version` | 出版社定稿：期刊、会议论文集（NeurIPS、PMLR）、OpenReview 上的 ICLR/TMLR 终稿 |
| 校样、在线优先 | `Proof` | 出版社排了版、还会换的：IEEE Early Access、Elsevier Article in Press |
| 接收稿 | `Accepted manuscript` | 审完接收的稿子，不在出版社手里定稿：PMC 作者稿、CVF/MICCAI/ECVA 开放版、arXiv 上的终稿副本 |
| 预印本 | `Preprint` | 投稿前或审稿中公开的：arXiv 的预印本、OpenReview 投稿版 |
| 补充材料 | `Supplementary material` | |
| 网页快照 | `Snapshot` | |
| 未知 | `Unknown version` | 看了证据也定不了 |

- **版本**按保存时手上的证据定：首页标注、网站的声明、元数据。不按网站推断。
- **来源**写文件从哪个网站下载的，用网站自己的名字：arXiv、OpenReview、IEEE Xplore、ScienceDirect、PMC、CVF 等。
- **补充**只写区分得着的信息：arXiv 必写版本号 vN；投稿版写 "ICLR 2027 submission"；Early Access 写明。
- 预印本条目自己的 PDF 也照写，例如 `Preprint (arXiv v2)`，不再叫 "PDF"。
- 文件名不变，用 Zotero 的格式。版本只放标题，因为"按父条目重命名文件"会把文件名改回去。
- 多个版本都留着。列出来时按"正式版、校样、接收稿、预印本、未知"排，补充材料和快照另列。
- 不合规范的标题（"PDF"、"Full Text PDF"、"全文"、"已提交版本"等）由 lint 列出；agent 拟名，用户确认后改。
- 现有库：约 802 份 PDF 加 96 份快照一次性改名，用户确认清单后写。

例子：CycleGAN（`zhuUnpairedImagetoImageTranslation2017`）
- 现在两份叫 "PDF"（其实是 arXiv v7）和 "Full Text PDF"（其实是 CVF 开放版）；
- 改名后是 `Preprint (arXiv v7)` 和 `Accepted manuscript (CVF)`；
- 一眼能看出库里还没有 IEEE Xplore 的正式版。

### 2026-10-21 按真实文件重讲

用户：「你让我定的点根本没有example，我完全不清楚你在讲什么，重新来」。我用库里 12 份真实文件，逐份列出"现在叫什么、以后叫什么"，再请用户看其中三处判断：
- arXiv 上的终稿副本叫接收稿；
- 排好版、还没定稿的单独叫 Proof；
- 看不出的写 Unknown version。

用户问：「我不太懂proof是什么东西」。我用 liReview 解释了，并改为建议：不单开 Proof，归入正式版，括号里注明 "Article in Press"，如 `Published version (ScienceDirect, Article in Press)`。理由：
- 这种文件库里只有约 3 份，内容和终版基本一样，差的是卷期页码；
- 名字里注明了，照样看得出不是终版；
- 少一类，好懂。
等用户定。

### 2026-10-21 用户对命名方案的要求

「用英文，这些名称。你自己查过我现在库里的吗？你也可以探究一下，如果库里没有预期的版本，或者存疑的，任何你有疑惑的地方，你可以根据流程去找一下相关的文章pdf，考虑实际情况，因为我记得文献相关的pdf版本都会比较混乱，你怎么去判断会是问题，当然，你在下载的时候绝大部分应该能判断出，因为pdf来源的网站应该就能判断了。我需要一个比较完善、高效、简洁、优雅、容易分辨的一个命名方案，同时为以后版本的提升或者多个版本做好准备。」

- 名称用英文。
- 方案要完善、高效、简洁、优雅、容易分辨；要为版本升级和多个版本并存做准备。
- 判断版本主要靠下载时的来源网站；存疑的、库里缺预期版本的，按流程去找真实的 PDF 来看。
- 库里现状（按粗分规则推断）：除预印本条目外，约 200 个会议、期刊条目没有正式版。其中会议 90 个只有接收稿、76 个只有预印本、36 个看不出；期刊 13 个只有接收稿、33 个只有预印本、15 个看不出。
- 三路调研在跑（只读，Zotero 不写，下载放到草稿目录）。结果写进参考材料目录：
  - `doubtful-resolved.md/json`：73 份存疑文件逐份定版本。用户补充：「你不确定的版本，也可以调用后台subagent去自己看pdf，然后再根据相关的论文获取的流程检查对应出版商，来确定。」所以读完仍不确定的，按 p2z 的获取流程去出版商页面对照后再定；
  - `source-signals.md`：各来源网站给什么版本、下载时怎么认，用真实下载验证；
  - `upgrades.md`：版本以后怎么变、怎么发现。
- 用户（2026-10-21）：「要善用后台subagent，不管是你现在测试探索也好，还是之后skills检查流程也好，如果脚本处理不好，就善于用subagent，准确率也会高很多，当然，这种用于浏览器操作、判断、检验等小任务/简单任务的subagent用sonnet模型就足够了，同时并行数量可以提高到10个。」
  - 对方案的影响：保存时脚本定不了版本的、一次性改名时存疑的，都交给后台 sonnet subagent 看文件、去出版商页面核对，最多 10 个并行。
  - 当下的分工随即调整：
    - 需要登录的出版商拆给 5 个 sonnet agent 并行，各写一份：`source-signals-ieee.md`、`-elsevier.md`、`-springer.md`、`-nature.md`、`-acm-wiley.md`；
    - 原来那路只查开放网站和 API；
    - 73 份存疑文件那路只做本地阅读，标出要去出版商核对的，之后再分给并行的 sonnet agent。
- **73 份存疑文件读完了**（`doubtful-resolved.md/json`）：Accepted 40、Published 21、Preprint 5、Unknown 7。
  - 值得定规则的情况：
    - CVF、MICCAI 的 "Open Access version" 水印是图片，`pdftotext` 看不到，要渲染首页才能认；
    - ECCV 2024 有 5 份是不带水印的 LNCS 终稿排版；
    - TMLR 和 OpenReview 上 NeurIPS 2025 的终稿算 Published；
    - PMC 上没有 NIHMS 横幅的 AMIA 论文集算 Published；
    - 作者主页上的副本：SSIM 印着 TIP 卷期但页码从 1 开始，MS-SSIM 写着 "Published in: … ©IEEE"，这两份都判为 Accepted；
    - Research Square 封面写着已有 Nature Medicine 版本，但它本身仍是 Preprint；
    - 一份 171 页的会议摘要集只为其中一篇摘要挂进来；
    - RCAN 的同一份 CVF 文件挂在两个条目上。
  - 剩 14 份要去出版商核对，分给 3 个并行的 sonnet agent，结果写进 `publisher-check-{journals,eccv-miccai,misc}.json`。
  - 期刊组 4 份（FUTURE-AI、BRIDGE、Guo、Brodeur）全是 Preprint。
    - 依据：每份都和 arXiv 最新版逐字节相同（md5），而这个版本的日期早于期刊的接收日期（Crossref）。
    - 这是一种通用、可靠的判法：先比对文件哈希，再看版本日期和接收日期的先后。
  - ECCV/MICCAI 组 6 份全是 Accepted。
    - 5 份 ECCV 和 ECVA 开放版逐字节相同，跟 arXiv 各版都不同；
    - I-SECRET 是作者从 ResearchGate 发的终稿：LNCS 排版，页码从 1 开始，没有开放版可比，中等把握。
  - 零散组 4 份：
    - gCNR：Accepted，中等把握。和 Lirias 作者版文字完全相同，创建于接收前 18 天，可能是最后一轮修改稿。
    - FSIM：Accepted，较高把握。作者主页上的 Word 稿，创建于修改之后、上线之前，参考文献里写着 "accepted"。
    - Jeong：Unknown。像是 MICCAI 2023 USenhance 挑战赛的队伍方法说明，查不到出处。
    - T-CAIREM：Published。和会议网站上的摘要集逐字节相同，是主办方出版的整本摘要集，论文只是其中一篇摘要。
  - 由此看出：
    - 判版本最有力的是两样：一是和某个已知版本逐字节相同；二是文件的日期落在投稿、接收、上线之间的哪一段。
    - 还要能表达"整本合集里的一篇"和"挑战赛方法说明"这类不是单篇论文的文件。
- **ScienceDirect 探查**（`source-signals-elsevier.md`）：
  - 文章页上的版本信号：
    - 文章页写 "In Press, Journal Pre-proof"，或 "In Press, Corrected Proof"；
    - 最终版写 "Volume N"，元数据有 `citation_volume`，没有 "In Press"；
    - 接收稿走单独的路径 `/science/article/am/pii/<PII>`（"View Open Manuscript"）。
  - 文章页已经是最终版时，库里的 PDF 仍可能是校样（liReview 就是），所以要读 PDF 自己的首页。
  - 库里的 huangStabilityenhancedCycleGAN2022 被标成正式版，其实是作者稿：标题大写、没有 Elsevier 页眉、创建日期早于上线日期。
  - PDF 地址另有一道验证，单独记了 issue：[20261021-paper-to-zotero-sciencedirect-pdf-host-captcha.md](20261021-paper-to-zotero-sciencedirect-pdf-host-captcha.md)。
- **Nature 探查**（`source-signals-nature.md`）：
  - 页面的 `dataLayer` 里有 `articleInPress` 和 `uneditedManuscript`。预览版是 `AcceleratedArticlePreview` / `true`，没有卷号和起始页，正文写着 "will be replaced automatically by the final Version of Record"。
  - PDF 首页：
    - 旧式的写 "unedited version"；
    - 新式的每页页眉都有 "Article in Press"；
    - 最终版有期刊页眉。
  - 库里 3 个 npj 的 Article in Press 条目，现在都已有最终版（页数从 24–33 页变成 10–15 页），库里那份应该换。
  - `guoMulticenterStudyAdaptability2024` 的最终版是开放获取，可以直接下载。
  - 对 p2z 本身也有影响（还没在实际运行里碰到过，先记在这里）：
    - 预览页上 `<id>.pdf` 返回的是 HTML，真正的 PDF 是 `<id>_reference.pdf`；
    - 付费文章的 PDF 链接返回 HTTP 200 加 HTML，只能靠 `%PDF-` 文件头分辨；
    - 补充材料里的 Peer Review File 和 "Author Correction: …" 更正声明，首页都带着论文标题，单凭标题会被当成论文本身。
- **Springer 探查**（`source-signals-springer.md`）：
  - MICCAI 开放版：papers.miccai.org 标着 "Main Paper (Open Access Version)"。首页没有 LNCS 页眉、© 和 DOI，页码从 1 开始。库里的 3 份和下载的完全一致。
  - Springer 的章节 PDF 没拿到：没有权限时返回 HTTP 204 空内容，机构登录没去走。所以 LNCS 正式版的首页长什么样还没验证。
  - 会议网站可能滞后：pham 那篇在 Springer 上已经出版，papers.miccai.org 仍写 "Not yet available"。不能拿会议网站判断正式版有没有。
  - 期刊没有单独的 "Online First" 标签，卷期在上线时就给了；信号是 `citation_online_date` 早于 `citation_publication_date`。
  - chenReasoningEraSurvey2026 的正式版是开放获取，可以直接下载（50 页）；库里存的是 arXiv v5（109 页），该换。
  - 更正声明是单独的 DOI（Author Correction，`dc.type=Erratum`）。
- **IEEE 探查**（`source-signals-ieee.md`）：
  - 文章页的 `xplGlobal.document.metadata` 里：`isEarlyAccess` 为 true、`volume:"PP"` 是 Early Access；最终版有真实的卷期，并且 `isEarlyAccess:false`。"Date of Publication" 是首次上线日期，不是版本信号。
  - Early Access 不一定是接收稿：
    - 作者版带横幅 "This is the author's version which has not been fully edited"，是 Accepted；
    - 排了版的那种写着 "Content is final as presented, with the exception of pagination"，是 Published（Article in Press）。
  - `maTinyUSFMCompactEfficient2026` 至今仍是 Early Access，库里那份和今天 Xplore 上下载的内容相同。
  - CVF 和 Xplore 的区别：
    - CVF 版只有首页有三行水印，写着 "identical to the accepted version"，没有版权行和下载戳；
    - Xplore 版有会议页眉、©、DOI，每页都有 "Authorized licensed use limited to: <机构>"；
    - ICCV 两版页码不同，CVPR 两版相同。
  - 会议论文没有 Early Access。"Corrections to …" 是单独的 DOI，一页，标题是 "COMMENTS AND CORRECTIONS"。
  - 限流页单独记了 issue：[20261021-paper-to-zotero-ieee-akamai-rate-limit.md](20261021-paper-to-zotero-ieee-akamai-rate-limit.md)。
- 用户（2026-10-21）：「不同的出版商，甚至不同的文章，可能都会不一样，你不要认为库里这几篇就把某个流程定死，而且出版商也有可能去更新标识之类的，你把握不是很大就交给subagent去判断」。对方案的影响：
  - 规范只定版本的定义和名称，不定"在某家出版商怎么认"。
  - 各家探查到的标识，写进 publishers.md 当带日期的线索（"2026-10 见到"），不当成识别规则。线索和页面实际对不上时，以页面为准。
  - 保存时，脚本只收集证据：页面元数据、首页文字、各个日期、和已知版本的哈希比对。由 agent 按定义判断；把握不大的交给后台 sonnet subagent 看；真定不了的写 Unknown。
- **2026-10-21 循环访问事故**：查版本升级的 agent 在用户的 Chrome 里循环打开 dblp.org（33 次，约 90 秒）。已停掉它和另一个反复轮询的下级 agent，所有浏览器会话都已关闭。经过和防范措施见 [20261021-paper-to-zotero-request-pacing.md](20261021-paper-to-zotero-request-pacing.md)。
  - 版本升级这部分调研没做完。草稿目录 `probe-upgrades/` 里有半成品：arXiv、OpenAlex、PubMed 的批量结果，以及 33 条 dblp 结果。之后按新规矩重做。
- **开放网站探查**（`source-signals.md`，270 行）：
  - arXiv：
    - 每个版本各有自己的 comment，可以按 `<id>vN` 取到。
    - `journal_ref` 和 `doi` 不能当证据：CoreDiff 投稿前的 v1 就挂着 TMI 的 DOI。
    - 用 PDF 直接提交的没有页边戳。
    - 不带 vN 的网址永远指向最新版，所以要记下 vN。
  - OpenReview：`content.venue` 直接写明状态，例如 "ICLR 2027 Conference Submission"、"Submitted to ICLR 2025"（被拒）、"ICLR 2025 Oral"、"Accepted by TMLR"。`/pdf?id=` 的内容会随修订改变。
  - CVF、ECVA、MICCAI 都是 Accepted。文件上的标记不一定有：CVF 2017–2022 年的水印是图形，ECVA 2024 什么标记都没有。
  - NeurIPS、PMLR、ICLR、ACL、JMLR 的论文集是 Published。
    - 首页的抬头只是旁证，因为 arXiv 上的终稿副本也印着同样的字；
    - ACL 的 `<id>.pdf` 会悄悄指向修订版。
  - PMC 作者稿：`ncbi_pcid=manuscript`、文件名 `nihms-*.pdf`。Europe PMC 用 `authMan=Y` 标作者稿。
  - HAL、eScholarship 的封面一律引正式出版信息，看不出版本，要看第 2 页；机构库自己页面上对文件的标注最准。
  - Unpaywall 不可靠：16 条里只有 2 条和文件对得上。所以 Zotero 写的"已提交版本""全文"不能当证据。
  - 同一个网址会先后给出不同版本：arXiv 不带 vN 的地址、OpenReview 的 `/pdf?id=`、ACL 的 `<id>.pdf`。
- ACM/Wiley 探查（`source-signals-acm-wiley.md`）：
  - 库里 4 个 ACM 条目存的都是 arXiv 预印本，ACM 上的正式版都是开放获取，可以换。
  - ACM "Just Accepted" 是作者的 Word 稿，属于 Accepted。
  - Wiley "Early View" 是排了版的 Published（还没进期）。
  - Wiley 的 Zhou 那篇没有订阅权限，拿不到。
- 库里缺正式版的条目按出版商分：IEEE 82（主要是只有 CVF 开放版的 CVPR/ICCV）、Springer 68（主要是只有会议开放版的 MICCAI）、Nature 14、Elsevier 9、ACM 6、Wiley 1。清单在 `missing-published-by-publisher.json`。

## 用户质疑方向（2026-10-20）

看完下面的方案，用户：「我感觉完全不太对，这个问题是否应该从根源上解决。在问题背后，有没有一个更深的问题，是我一直在绕着它走，却没有真正问出来的？用你自己的话重述你认为这次的目标是什么，以及试图解决的问题是什么」。

- **查到的事实**（只读）：Zotero 自己的"主附件"（本地 API 条目里的 `links.attachment`，双击条目时打开的那份）也选错了。chung、shamsolmoali、zhu（CycleGAN）、liReview 这 4 个，它选的都是先加进库的接收稿或 arXiv 版。所以问题不只在 p2z 的识别规则：库里没有任何地方写明哪份文件是"这篇论文"，Zotero 和 p2z 都在猜。
- **我的重述**（没拍板，等用户确认）：更深的问题是"一个条目里哪份文件算这篇论文，该在什么时候、由谁定下来、记在哪里"。方向是文件进库时定，不在读的时候猜：库保持每个条目只有一份论文本身的 PDF，其余明确标成补充材料或旧版本，现有 17 个一次整理。照这个方向，下面"读时按 url 认版本"的改动就不需要了。

## 方案（没拍板，2026-10-20 给用户预览；见上，方向被质疑）

- **认版本的顺序**：附件标题写了版本就按标题；没写，就看它从哪下载的。
  - 从 arXiv、bioRxiv 这类只放预印本的服务器下的，算预印本；OpenReview 除外。
  - 附件 url 跟条目 url 一样，不算数（p2z 会把条目 url 抄到附件上）。
  - 都没有，才默认正式版。
- **仍然并列时**（标题和来源都看不出），agent 打开每份第 1 页判断。`SKILL.md` 和 `read_library --help` 各加一句。
- **不做**：不为 "Author manuscript"、"已提交版本" 之类逐个加标题前缀。来源 url 是一个通用机制，前缀清单只会越加越长。
- **库里要改的两处**（要用户点头，已 dry-run）：
  - chung 的 `AAQTX26I`："Author manuscript (eScholarship, UCSF)" → "Accepted manuscript (eScholarship, UCSF)"；
  - liReview 的 `T3FHSIUF`："全文" → "Accepted manuscript (HAL)"。
  - 改完它们排在正式版后面。
- **已在工作区改了的文件**（没提交）：
  - `p2zlib/paper.py`：规则本身；
  - `p2zlib/zotero.py`：把条目 url 传进去；
  - `read_library.py`、`report.py`：调用处；
  - `SKILL.md`：一句说明；
  - 两个测试。
  - 27 个测试文件全过；真实库上 `read_library pdf` 结果和上面的预期一致。
