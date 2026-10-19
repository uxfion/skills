# paper-to-zotero：IEEE 页面不声明 PDF 链接，取全文每次都要停

从 `docs/issues/archive/20261018-paper-to-zotero-v3-first-batch-fixed.md` 的第 5 条单独拎出（2026-10-18）。

- 来源：使用 · 2026-10-18
- 现场：第一次 v3 真实批量里，TMI 那篇经学校登录打开 IEEE Xplore 文章页后，`fetch.py --via page` 以 `no_pdf_link` 停下：IEEE 页面没有 `citation_pdf_url`。agent 按 publishers.md 手动打开 `stamp.jsp?arnumber=<n>`，读出 iframe 里的 `stampPDF/getPDF.jsp?…`，再打开它，Chrome 下载后由监控认领，核对通过。
- 痛点：IEEE（TMI、TPAMI、CVPR/ICCV 的正式版等）很常见，每篇都要 agent 停下来手动做同样的几步。
- 方向：页面没有 `citation_pdf_url` 时，`fetch.py` 也读页面自己的"PDF"按钮链接（IEEE 是 `a[href*=stamp]`），再走现有的"像点击一样打开、取阅读器或等下载"那条路。做法要通用（读页面上的 PDF 按钮），不为 IEEE 写死。
- 状态：open
