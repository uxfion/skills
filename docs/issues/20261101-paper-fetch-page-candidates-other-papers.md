# paper-fetch：页面上“像 PDF 的链接”挨个试，会经学校代理下载别的论文

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
- 方向：讨论中，见下（没拍板）。
- 状态：open，用户 2026-11-01 说先推迟：「这个问题先推迟吧，先把split这边的收尾」。大批量导入 Elsevier 论文之前，先把它定下来。

## 讨论（2026-11-01，没拍板）

- 第 3 类链接对 IEEE 很重要：IEEE 页面不声明 `citation_pdf_url`，它的 PDF 按钮（`stamp.jsp`，文字 "PDF"）就属于这一类，2026-11-01 的 SAM 就是这样由脚本自动拿到的。要是只留前两类，IEEE 每篇都要派 paper agent。
- 我提的方向：
  - 第 3 类链接只在“链接地址里带着这页自己的文章号”时才由脚本去请求。例：IEEE `/document/10378323` → `stamp.jsp?arnumber=10378323`；ScienceDirect `/pii/S1361841524002056` → 这篇自己的 PDF 链接也带这个 PII；Springer、Wiley、ACM 的地址里带 DOI。
  - 其余链接作为证据写进 `page` 交接，交给看得见页面的 paper agent 挑：拿不准就交给 agent，不靠多试。
  - 采用前先在几家出版商的真实页面上试。
