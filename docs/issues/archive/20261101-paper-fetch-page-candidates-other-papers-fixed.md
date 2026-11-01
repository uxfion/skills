# paper-fetch：页面上“像 PDF 的链接”挨个试，会经学校代理下载别的论文

> **已修复（2026-11-01）**：实现在 `paper-fetch/scripts/fetch.py`（`own_marks`、`carries_mark`，提交 `94ac939`），SKILL.md 和 paper agent 的 brief 写明从 `evidence.links` 里挑；真实页面核对通过，见文末。

- 来源 · 日期：一个旁观的 agent 提醒 · 2026-11-01，第二期验收实测（记录在 `archive/20261030-paper-fetch-script-agent-division-fixed.md` 的“第二期验收实测”）之后。
- 背景：第二期 paper-to-zotero 的实测，导入 TransUNet（Medical Image Analysis 2024，DOI `10.1016/j.media.2024.103280`）。第 1 遍停在 ScienceDirect 文章页（经学校代理），写了 `page` 交接，paper agent 用 `fetch --start <文章页>` 把页面交回脚本。
- 现场：
  - 脚本在页面上找 PDF 候选（`pflib/browser.py` 的 `FIND_JS`），按序分三类，每页最多试 3 个（`fetch.py` 的 `PAGE_CANDIDATES`，重新分工 spec §3.3 定的，数字是我定的）：
    1. 页面声明的 PDF（`citation_pdf_url`、`link rel=alternate`）；
    2. 页面嵌的 PDF（iframe、embed）；
    3. 文字或地址像 PDF 的链接（"PDF"、"View PDF"、`.pdf`、`/pdf/`），本站的排前面。
  - 这页上第一个 “View PDF” 是推荐文章 IB-TransUNet（PII `S1319157823000411`）的。脚本经代理下载了它，核对判定不是这篇，丢掉；正是这次请求在 `pdf.sciencedirectassets.com` 上撞到 “Are you a robot?”，推送提醒用户去勾。用户勾过之后，paper agent 从页面上找到这篇自己的链接（带它的 PII `S1361841524002056`），再交回脚本取到。
- 为什么要紧：
  - 核对保证不会挂错文件，但请求已经发出去了。SKILL.md *Get the file: the chain* 说猜错不花什么代价（“a wrong guess costs nothing”），在这里不成立：每多下载一份别人的论文，就多一次经学校代理打到出版商的请求。
  - ScienceDirect 的 PDF 主机本来就会出验证页（见已关的 `archive/20261021-paper-to-zotero-sciencedirect-pdf-host-captcha-fixed.md`）。批量导入很多 Elsevier 论文时，碰到验证页、学校账号被限的风险随篇数放大。
  - 这和设计原则 §6 的上网规矩冲突：每个请求都是用户本人发的。
- 用户原话：「看一下这个，提出的问题是否有意义，你研究后和讨论？」
- 方向：已定（2026-11-01，用户选 A），见下“定下的”。
- 状态：已修复（2026-11-01）。用户先推迟（「这个问题先推迟吧，先把split这边的收尾」），拆分收尾后当天定了方向、实现、核对。

## 讨论（2026-11-01，没拍板）

- 第 3 类链接对 IEEE 很重要：IEEE 页面不声明 `citation_pdf_url`，它的 PDF 按钮（`stamp.jsp`，文字 "PDF"）就属于这一类，2026-11-01 的 SAM 就是这样由脚本自动拿到的。要是只留前两类，IEEE 每篇都要派 paper agent。
- 我提的方向：
  - 第 3 类链接只在“链接地址里带着这页自己的文章号”时才由脚本去请求。例：IEEE `/document/10378323` → `stamp.jsp?arnumber=10378323`；ScienceDirect `/pii/S1361841524002056` → 这篇自己的 PDF 链接也带这个 PII；Springer、Wiley、ACM 的地址里带 DOI。
  - 其余链接作为证据写进 `page` 交接，交给看得见页面的 paper agent 挑：拿不准就交给 agent，不靠多试。
  - 采用前先在几家出版商的真实页面上试。

## 定下的（2026-11-01）

- **用户选 A：按编号把关。** 页面声明或内嵌的 PDF（`citation_pdf_url`、`link rel=alternate`、iframe、embed）照旧由脚本请求；文字或地址像 PDF 的普通链接，只有地址里带着这篇自己的编号才由脚本请求。编号是这篇的 DOI、arXiv 号、PMCID，或者文章页自己地址里的编号（ScienceDirect 的 PII、IEEE 的文档号）。其余链接一个都不请求，作为证据写进 `page` 交接，交给 paper agent 挑。
  - 依据：两种出错代价不对等。该试的没试，只是多派一个本来就会派的 agent；不该试的试了，就是用用户的学校账号多下载一篇别人的论文，这个错误本身就是伤害。
  - 另外两个选项没选：B 普通链接一律不试（每篇 IEEE 都要派 agent，SAM 那种原来自动拿到的也要人接手）；C 维持现状、每页只试 1 个（上次多下载的那篇恰恰排在第一个）。
  - 编号具体怎么取（地址的哪一段算编号），先按已知的几家写，再在几家出版商的真实页面上各打开一次、存下页面上的链接列表来核对。打开哪几页，先列给用户看。
- **文章页地址里的编号也算（用户选 A，2026-11-01）。** 用户问这样是否合设计原则：DOI、arXiv 号、PMCID 是标识符对上，合 §1；“文章页地址的最后一段，至少 6 个字符、含数字，算这篇的编号”是我定的经验规则（6 是我定的数），出错偏安全的一边（对不上只是交给 agent），要先在真实页面上核对。用户选 A 留着（B 是只认 DOI、arXiv 号、PMCID，IEEE 和 ScienceDirect 大多要派 agent）。代码注释写明：哪家网站对不上就交给 agent，永远不往这里加某个网站的地址规则。
- **实现（2026-11-01）：** `fetch.py` 的 `own_marks`、`carries_mark`，`on_page` 只请求带编号的普通链接，其余进 `page` 交接的 `evidence.links`；SKILL.md 去掉“猜错不花什么代价”，paper agent 的 brief 写明从 `evidence.links` 里挑。测试：推荐文章排在前面的 ScienceDirect 场景、编号的取法（IEEE 文档号、arXiv 带版本号、DOI 转义、MDPI 的短编号不算）。真实页面核对还没做。
- **用户的两点和讨论**（选 A 之前）：
  - 用户原话：「但是你要知道，可能有多个，其中一个肯定是我们能取到想要的嘛。如果我们没有取到的话，它不就会自动交给subagent去自己操作嘛，是吧？还有一点，因为这是页面上推荐的相关论文，肯定和我们这篇论文也有一定关系，是不是也需要去探索呢？这就相当于做了一个寻找类似论文的操作，如果把这一步丢掉了，是不是会有点可惜？虽然我们没有去实现相关的论文，就是去找类似的论文，但是如果页面中跳出来推荐的，如果有用的，不应该大致浏览一下吗？如果是有用的话，你就存嘛.我不确定我这个想法对不对、合不合适，你自己根据情况判断一下。你要有独立思考的能力，不能全信我的话，要提出自己的观点和我讨论」
  - 多个链接：取不到确实会交给 agent，问题在取到之前的试错。每试一个错的，就是经学校代理完整下载一篇别人的 PDF；出版商一般不许批量下载，异常的下载量可能停掉整个学校的访问。A 并不只试一个：带着这篇编号的链接有几个就试几个（最多 3 个），挡住的只是对不上的。
  - 推荐的相关论文：我的看法是不放在取全文这一步做。要判断有没有用得读摘要或 PDF，每篇导入就多下载好几篇；“有用”要知道用户在做什么研究，自动存会把库塞满（用户说过「一般对于这篇论文有意义，我们才会入库」）；出版商的推荐只推自己的期刊，按引用关系（OpenAlex 的相关文献、引用和被引）或 papers-cool-search 按主题找更全。“找相似论文”值得以后单独设计，等用户想做时再说，现在不另记 issue。

## 真实页面核对（2026-11-01，用户选 A）

在用户的 Chrome 里打开 5 个真实文章页（出版商的经学校代理，PMC 不经代理），一页一次请求、手动；只读页面上的候选链接（`pflib/browser.py` 的 `FIND_JS`），用 `fetch.own_marks`、`carries_mark` 离线判断，不下载任何 PDF。没有碰到验证页。

| 页面 | 页面上的候选 | 新规则 |
|---|---|---|
| ScienceDirect，TransUNet（`10.1016/j.media.2024.103280`），文章页 `…/pii/S1361841524002056` | 3 个 "View PDF" | 这篇自己的（`/pii/S1361841524002056/pdfft…`）请求；两篇推荐文章的（`S1361841518306133`、上次误下载的 IB-TransUNet `S1319157823000411`）留给 agent |
| IEEE，Mask R-CNN（`10.1109/TPAMI.2018.2844175`），`/document/8372616` | 1 个 "PDF" 按钮 `stamp.jsp?…arnumber=8372616` | 请求（文档号对上） |
| Springer，MICCAI 2025 一章（`10.1007/978-3-032-05127-1_40`） | 页面声明的 PDF（`citation_pdf_url`） | 请求（声明的照旧，不看编号） |
| Nature，AlphaFold（`10.1038/s41586-021-03819-2`） | 声明的正文 PDF；两份补充材料（地址带 DOI）；参考文献里两份别人的 PDF（CASP14 摘要集、arXiv 0804.2488） | 正文先请求；补充材料算这篇的；参考文献里的两份留给 agent |
| PubMed Central，UNet++（`PMC7357299`） | 页面声明的 PDF `/articles/PMC7357299/pdf/…` | 请求 |

结论：5 家都按设计走。这篇自己的 PDF 都被认出来，没有一家要多派 agent；挡下来的都是别的论文（推荐文章、参考文献）。"文章页地址最后一段、至少 6 个字符、含数字"的经验规则在 ScienceDirect（PII）和 IEEE（文档号）上对得上。
