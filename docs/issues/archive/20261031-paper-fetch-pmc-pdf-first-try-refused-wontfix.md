# paper-fetch: PMC's PDF refused on the bulk run's first try, fetched a minute later

> **不做（2026-11-10）。** 只在 2026-10-31 出现过一次，之后两次都没再现：上午 JAMA 那篇是另一种情况（PMC 页上没有正文 PDF）；下午专门用当初那篇（UNet++，PMC7357299）照原样取了一次，18 秒取到，核对通过。当时流程自己恢复了（页面交接 → paper agent 把同一页交回 → 取到），代价是多派一次 paper agent。被拒的响应是什么仍不知道；再出现时，被拒的文件留在 `unverified/`，页面交接的证据里也有它的标题和开头文字，paper agent 的回报会带出来，到时再记成 publishers.md 里的一条提示。

2026-10-31, phase-1 live acceptance (spec `20261031-paper-skills-script-agent-division-spec.md` §8), UNet++ (`10.1109/TMI.2019.2959609`, PMC7357299, an NIH author manuscript).

- **What was run.** `pf.py fetch --pass 1 --route accepted` on the result. The candidate was the PMC article page `https://pmc.ncbi.nlm.nih.gov/articles/PMC7357299/` (`needs_browser: true`).
- **What was seen.** fetch tried the page's one PDF link and the check refused what came back (`code: refused`, note "1 PDF links tried"); a `page` handoff followed. About a minute later the paper agent ran `fetch --start <the same article page> --version accepted --session pf-zhou2020unet`, and that run fetched `…/pdf/nihms-1600374.pdf`, which passed the check.
- **Why it matters.** A PMC copy may need a second, later request before its PDF link serves the PDF (publishers.md already notes a JavaScript verification for plain HTTP and a reCAPTCHA on the PDF link). The handoff path recovered it, at the cost of a paper agent; a paper with several PMC candidates pauses on the first.
- **Not yet known.** Whether the first response was PMC's verification page, a viewer, or something else: the refused file sat in `unverified/` and went with the live-test directory.
- **Suggested.** On the next real run, keep the refused response and look at it; then a dated hint in publishers.md's PMC bullet, worded from what it was.

## 2026-11-10 又跑到一次 PMC，没再现

JAMA Netw Open 的一篇（PMC11519755）。这次不是同一种情况：PMC 文章页上根本没有正文 PDF 的链接，只有三份补充材料；paper agent 猜的 `/pdf/` 地址回 404，`refused` 记的是这个 404，`unverified/` 里没有留下文件。"第一次被拒、过一会儿又能取"没有再现，被拒的响应是什么仍不知道。
