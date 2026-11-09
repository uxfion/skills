# paper-fetch：MICCAI 论文页的识别交接不完整，补 DOI 后原页不参与找全文

2026-11-09 已修复：[locate](../../../paper-fetch/scripts/fulltext_links.py)在补 DOI 后仍保留原始论文页作为候选，原始请求纳入缓存输入；[识别说明](../../../paper-fetch/SKILL.md)和实际提示明确由主 agent 处理没有标准元标签的正常论文页。PDF 链接归属判断沿用既有交接。

- 来源：2026-11-05 全流程试用，导入 agent 用 MICCAI 2026 论文页导入 *Towards Unified Image–Video Modeling Across B-Mode and Contrast-Enhanced Ultrasound for Multi-task Analysis*。用户没有提。
- 状态：fixed。原始参考资料中仍用于排查学校登录的事实已移入[试用记录](../20261105-paper-fetch-trial-import-web-notes.md)，其余事实记录在本 issue；参考资料文件夹已清理。

## 经过

1. **`identify` 只得到一个空壳。** 用户给的是 `https://papers.miccai.org/miccai-2026/1076-Paper1246.html`。这个页面有 og:title、作者 meta 和一段 BibTeX，但没有 `citation_*` 标签，`identify` 判为 `no_citation_meta`，只给了一个空壳，summary 算 failed、exit 1。页面自己写着 "SpringerLink (DOI): Not yet available"。agent 改用 `identify --search` 按标题在 Crossref 找到 DOI（10.1007/978-3-032-38059-3_60），再 `--redraft`，这才成了。SKILL.md 只说空壳留着，没提可以按标题搜 DOI 再 redraft。另外，空壳的文件名是从网址生成的（`papersmiccaiorgmiccai20261076paper1246html`），redraft 以后也没变（agent 的说法）。
2. **原始论文页没进链接清单。** 当时 agent 说 redraft 后原页从 result 里丢了。2026-11-09 核实：网址仍在 `request.given` 中，真正遗漏发生在找全文时。`locate` 的 `page` 只读 CSL 的 URL；补 DOI 后这个 URL 是 DOI 地址，被排除为论文页，故报 `page: no_identifier`。`request.given` 只在没有任何标识的空壳分支作为候选加入，补到 DOI 后就不再使用。
3. **页面上的 PDF 链接 fetch 没取。** handoff 2（已核实）：agent 用 `fetch --start` 打开论文页，结果 `no_pdf_link`；证据里留着没试的链接，"Main Paper (Open Access Version): …/miccai-2026/paper/1246_paper.pdf"。原因是这个地址里没有 fetch 认得出的论文标记：页面自己的标识是 `1076-Paper1246`，PDF 地址里只有 `1246_paper`。agent 再用 `--start` 直接给 PDF 地址，才拿到，check 通过，首页水印写着 "identical to the accepted version"。

## 为什么不顺

MICCAI 是用户方向里最常见的会议之一。原始论文页已知却没有进入全文候选，agent 需要自己补回；识别阶段遇到 `no_citation_meta` 时，说明又没有明确谁接手。与此同时，页面链接交给 agent 判断归属本来就是现有流程，不应因为这一步需要 agent 就新增匹配规则。

## 2026-11-09 复核

- 当前[官方论文页](https://papers.miccai.org/miccai-2026/1076-Paper1246.html)仍有明确的开放获取 PDF 链接、标题、作者和 BibTeX，DOI 仍显示尚未提供。直接读取当前 HTML 后，用现有 `from_page` 解析，复现 `no_citation_meta`；页面没有 `citation_*` 标签。
- `identify.py` 的 `redraft` 合并保留 `request.given`。对临时结果做离线模拟，确认补 DOI 后原网址仍在，`locate.identifiers()` 的 `page` 却为空；改变原网址也不会改变现有 `links_inputs()` 缓存输入。
- 原始第 2 个 handoff 已完整保留 PDF URL 和 “Main Paper (Open Access Version)” 上下文。当前 `fetch.py`、`web-agent.md` 和 `test_fetch.py` 都明确支持 agent 判断未尝试链接，再通过 `fetch --start <PDF URL>` 交回。这是正式入口，不是缺少 MICCAI 下载能力。
- 原始结果实际已取得并保存 `Accepted-MICCAI` 文件；保存的首页水印和当前官网都指明它是接受稿。结果要求 `wanted=published`，因此继续寻找 Springer 正式版符合现有要求。
- 空壳的 slug 在 redraft 后不变属于原地更新：文件和 handoff 引用保持稳定。当前已有显式 `--slug` 的处理，不为这里增加自动改名。
- 当前命令是 `pf.py search`；原记录中的 `identify --search` 是历史用法。

## 已定方案（2026-11-09）

主 agent 提出只修以下两处，用户回复「可以」。

1. **补齐已有来源的使用。** 复用现有 `request / unknown` 候选，把已保存的原始论文页纳入全文候选，即使结果已经有 DOI；仍由现有流程核对文件及版本。原页也进入链接缓存输入，候选已知时的来源状态应计入已有 `sources` 汇总。
2. **补齐识别接管。** 页面正常可读、却没有标准元标签时，由 agent 从页面确认标题、作者和已有标识；有 DOI 直接 redraft，没有则用已有 `search <title> --author <surname>`，确认候选后 redraft。找不到可信标识时，仍保留空壳进入已有的 PDF 识别流程。当前仅保存同页 HTML 再解析，不能补上页面本来没有的标签。

取舍：不新增 MICCAI/BibTeX 专用解析、PDF 地址匹配或自动改名；现有 PDF 链接交接继续使用。仅把 `page` 回退到原网址不足以解决：`src_page()` 只抽取 PDF 元标签，仍不会把这里的普通 PDF 锚点交进候选。通用保留原页更直接。

## 验证

- 本地模拟服务往返：空壳的原页成为候选；通过真实 redraft 命令补 DOI 后，原页仍在 `request / unknown` 候选中，slug 保持稳定。
- 原页变化使链接缓存失效；原页未变复用缓存；dry-run 不更新缓存。远端元数据来源均返回 503 时，已知原页仍可用，未回答的来源仍记录为 `incomplete`。
- DOI 和 arXiv 原始地址复用已有标识来源，不额外添加原页候选。
- 全文链接的 14 项测试、识别／获取／跨技能结果格式的既有回归，以及仓库约定检查通过。独立复核未发现阻塞项。未向 Zotero 写入或重新导入真实论文。
