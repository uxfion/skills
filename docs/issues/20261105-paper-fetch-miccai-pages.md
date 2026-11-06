# paper-fetch：MICCAI 论文页（papers.miccai.org）认不出、开放获取版拿不到

- 来源：2026-11-05 全流程试用，导入 agent 用 MICCAI 2026 论文页导入 *Towards Unified Image–Video Modeling Across B-Mode and Contrast-Enhanced Ultrasound for Multi-task Analysis*。用户没有提。
- 状态：open。证据在参考资料文件夹：5 个 handoff 及其证据、`fetch.jsonl`、`result.json`。

## 经过

1. **`identify` 只得到一个空壳。** 用户给的是 `https://papers.miccai.org/miccai-2026/1076-Paper1246.html`。这个页面有 og:title、作者 meta 和一段 BibTeX，但没有 `citation_*` 标签，`identify` 判为 `no_citation_meta`，只给了一个空壳，summary 算 failed、exit 1。页面自己写着 "SpringerLink (DOI): Not yet available"。agent 改用 `identify --search` 按标题在 Crossref 找到 DOI（10.1007/978-3-032-38059-3_60），再 `--redraft`，这才成了。SKILL.md 只说空壳留着，没提可以按标题搜 DOI 再 redraft。另外，空壳的文件名是从网址生成的（`papersmiccaiorgmiccai20261076paper1246html`），redraft 以后也没变（agent 的说法）。
2. **开放获取版没进链接清单。** redraft 以后，最初给的论文页就从 result 里丢了（`fulltext_links` 报 `page: no_identifier`），open 路线一条链接都没有。publishers.md 写了 MICCAI 有开放获取版，却没有脚本去找它（agent 的说法）。
3. **页面上的 PDF 链接 fetch 没取。** handoff 2（已核实）：agent 用 `fetch --start` 打开论文页，结果 `no_pdf_link`；证据里留着没试的链接，"Main Paper (Open Access Version): …/miccai-2026/paper/1246_paper.pdf"。原因是这个地址里没有 fetch 认得出的论文标记：页面自己的标识是 `1076-Paper1246`，PDF 地址里只有 `1246_paper`。agent 再用 `--start` 直接给 PDF 地址，才拿到，check 通过，首页水印写着 "identical to the accepted version"。

## 为什么不顺

MICCAI 是用户方向里最常见的会议之一。正式版在 Springer，要走学校登录；开放获取的接受版就挂在 MICCAI 自己的网站上。这三处每一处都要 agent 自己绕路，流程才走得下去。

## 待看

- 页面里有 BibTeX，或者 `og:title` 加作者 meta 时，`identify` 能不能直接拿来，或者至少按标题去 Crossref 搜一次（搜到的仍要人或 judge 确认）。
- papers.miccai.org 的 PDF 地址形如 `miccai-<年>/paper/<号>_paper.pdf`，页面形如 `<序号>-Paper<号>.html`。这两者的对应要不要作为"本论文标记"写进 publishers.md，当作带日期的提示，交给 agent 判断，而不是写成匹配规则（原则 §1，*Knowledge stays open*）。
