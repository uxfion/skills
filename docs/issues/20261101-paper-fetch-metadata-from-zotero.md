# paper-fetch：把 Zotero 做得更好的几处搬过来——元数据字段和找 PDF 的做法

- 来源 · 日期：拆分 issue（`archive/20261029-paper-to-zotero-split-fixed.md`）第 34 条 · 2026-11-01 记录。2026-10-29 只读对照了 Zotero 10.0.6 的翻译器和“Find Available PDF”，结论在拆分 spec `docs/specs/20261030-paper-to-zotero-split-spec.md` §9、§13。
- 为什么记在这里：2026-11-01 拆分结案，比较报告随参考文件夹删掉，还要做的活和做法挪到这里。
- 为什么要紧：几处字段 Zotero 填得出、我们填不出；有一条错误（LNCS 丛书名当论文集名）lint 查不出来。
- 状态：open，还没排期。spec §13 定的是拆完以后单独做，不和拆分混在一起，免得没法对比拆分前后的结果。
- 不在这里的：库里受影响的条目列在记忆 `zotero-library-todo`；作者关键词已经在重新分工第二期做了（`identify.py` 的 `author_keywords`）。

## 要做的

1. **期刊缩写、会议地点、论文集 ISBN、LNCS 卷号**：CSL 记录没有时，从 Crossref 的 work 取。
   - 比较时：Zotero 直接导入的 25 篇期刊文章里 13 篇有缩写，我们的 265 篇里 12 篇有。Zotero 的 Unixref 翻译器从 `abbrev_title` 填缩写。
   - 现状：doi.org 给出 `short-container-title`、`publisher-location` 时，`identify.py` 会映射；章节的 Crossref work 已经由 `proceedings_from_crossref` 取过一次，可以顺手读这几个字段。
2. **arXiv 预印本的完整日期**：取第一版的 `published`，来自 `versions_of_preprint` 已经在调的 arXiv API，代替 DataCite 只有年份的 `Issued`。
   - 比较时：我们的 78 条预印本里 68 条只有年份；Zotero 走 arXiv id 时用 `updated`，是最新一版的日期。
3. **章节的会议名**：章节的 Crossref `custom_metadata` 带会议全名（例："International Conference on Medical Image Computing and Computer-Assisted Intervention"），读进 `conferenceName`。Zotero 的翻译器不读这个字段，我们现在也不读。spec §13 没列这一条，是我提的，没拍板。
4. **lint 加一条 `proceedingsTitle == series`**（spec §13 没列，我提的，没拍板）：2026-10-07 到 10-10 建的 7 条 LNCS 条目把丛书名 "Lecture Notes in Computer Science" 写成了论文集名，现在的 lint 查不出来。加了规则再修这 7 条。
5. **Zotero 找 PDF 时的做法，写进 `publishers.md` 的出处**（`github.com/zotero/zotero`，tag 10.0.6）：
   - 验证页：`chrome/content/zotero/xpcom/browserRequest.js#L29-70` 有一张固定的主机表：ScienceDirect 的验证码（交给用户过，#L643 "Awaiting user captcha clearance"）、PMC 和 MDPI 的 proof-of-work、WorldCat 的 Turnstile。遇到 403 或者回来的不是 PDF 时才用（`attachments.js#L1205-1214`、#L2223）。
   - 节奏：每个域名间隔 1 秒，一个域名连续失败 5 次就放弃（`attachments.js#L1513-1514`、#L1688）。
   - `publishers.md` 现在没有 MDPI 这一条。
