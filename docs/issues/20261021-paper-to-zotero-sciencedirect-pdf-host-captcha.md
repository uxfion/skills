# paper-to-zotero：ScienceDirect 的 PDF 地址另有一道 Cloudflare 验证，publishers.md 没写

- 来源：2026-10-21，调研附件版本时（[20261020-paper-to-zotero-pdf-version-by-title-fixed.md](archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)），一个 sonnet 探查 agent 按 p2z 的流程去 ScienceDirect 下载 PDF 时遇到。用户没有说过这件事；下面的观察来自那个 agent 的报告（结论在那张 issue 的"ScienceDirect 探查"一条）。
- 状态：open

## 现场

- 文章页 `sciencedirect.com/science/article/pii/<PII>` 在 Chrome 里能正常打开。
- 两条 PDF 路由都会 302 跳到 `pdf.sciencedirectassets.com`：
  - 正式版：`/pdfft?...`；
  - 接收稿：`/science/article/am/pii/<PII>`，文件是 `am.pdf`。
- 那个地址显示 Cloudflare 的 "Are you a robot?" 验证页，没有自己通过。在页面里用 `fetch` 请求 pdfft 链接，拿回来的也是这张验证页。
- `curl` 访问 `sciencedirect.com` 返回 403；只有 `doi.org` 的 302 跳转能用 `curl` 走通。
- 另外，Chrome 里打开 `doi.org` 时，被 Zotero Connector 转到了 EZproxy 登录页；直接打开 `sciencedirect.com/science/article/pii/<PII>` 则不会。

## 为什么要处理

- `references/publishers.md` 的 ScienceDirect 一节只写了文章页首次访问时的 Turnstile（"通常约 20 秒内自己通过"），没写 PDF 所在的另一个主机还有一道验证。
- 结果是：文章页已经过了验证，PDF 还是拿不到。agent 照现在的说明，会把它当成拿不到文件，而不是一道要用户通过的验证（推断）。

## 待查

- 用户在前台通过一次以后，能管多久？是否对同一个浏览器会话里的其他论文都有效？
- 这一节标着 "2026-09, partially"，这条补进去时要注明核实日期。
