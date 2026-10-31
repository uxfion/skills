# paper-to-zotero：IEEE 连续取 PDF 后返回 Akamai 限流页，会被当成"没有 PDF"

> 已解决（2026-10-31）：spec `docs/specs/20261031-paper-skills-script-agent-division-spec.md` §3.3、§10。这里担心的“限流页被记成没有 PDF、转去下一条路”不会再发生：脚本找不到 PDF 时写 `page` 交接，paper agent 看到限流页答 `blocked`，这篇停在原路线，下一遍再试。观察到的现象写进 paper-fetch 的 `references/publishers.md`（IEEE Xplore 一节），作为带日期的提示。触发的确切次数没测。


- 来源：2026-10-21，调研附件版本时（[20261020-paper-to-zotero-pdf-version-by-title-fixed.md](archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)），一个 sonnet 探查 agent 在用户的 Chrome 里连续打开 IEEE Xplore 的 PDF 时遇到。用户没有说过这件事；下面的观察来自那个 agent 的报告（结论在那张 issue 的"IEEE 探查"一条）。
- 状态：已解决（2026-10-31）

## 现场

- 现在的取法和 `references/publishers.md` 写的一样：在页面里请求 `stamp.jsp`，读出里面 `iframe` 的 `src`（`stampPDF/getPDF.jsp?…`），再请求这个地址，拿到 `application/pdf`。
- 大约连续取了 10 次之后，`stamp.jsp` 返回的不再是带 iframe 的页面，而是一张带 `<APM_DO_NOT_TOUCH>` 标记的 Akamai 页面。一分钟后重试，又正常了。
- 另外，直接用 `curl` 访问 Xplore 得到 HTTP 202 和空内容（反爬），所以文章页里嵌的元数据只能在浏览器里读。

## 为什么要处理

- `fetch` 在 stamp.jsp 里找不到 iframe 时，会按"这一页没有 PDF"处理。这张 Akamai 页面是限流，等一会儿就会好，结果却会被记成没有 PDF，这篇论文就转去下一条路了（推断，没在 `fetch` 的实际运行里复现过）。
- 批量导入时，IEEE 论文多（库里缺正式版的就有 82 个是 IEEE），最容易连续触发。
- publishers.md 第 61 行列了 arXiv、OpenReview、DBLP 的限流，但没有 IEEE。

## 待查

- 触发的确切次数和时间窗口，等多久能恢复。
- 在 `fetch` 里复现一次，确认它现在给出的是什么结论。
