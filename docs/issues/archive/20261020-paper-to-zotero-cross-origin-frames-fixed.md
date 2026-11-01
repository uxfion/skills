# paper-to-zotero：跨域 iframe 里的 PDF 和阅读器看不到

> 已解决（2026-10-31）：spec `docs/specs/20261031-paper-skills-script-agent-division-spec.md` §3.3、§10。脚本在页面上找不到 PDF 时写 `page` 交接，由这篇的 paper agent 接手；跨域 iframe 的看法（`opencli browser frames`、`eval --frame`）写进 paper-fetch 的 `references/publishers.md`（*Reach of browser automation*），作为带日期的提示。脚本里不加 frame 的查找。


- 来源：我 · 2026-10-20，按用户的要求对照 opencli-browser skill 找能复用的地方时发现
- 现场：`fetch` 在页面上找 PDF 靠 `browser.py` 的 `FIND_JS`，只在当前页和**同源**的 iframe 里找（`VIEWER_FIND` 遍历 `contentWindow`，跨域的读不到）。一个出版商如果把 pdf.js 阅读器或 PDF 放在别的域名的 iframe 里，候选和 `viewer` 都会漏掉，`fetch` 停下报 `no_pdf_link`，只能交给 browser agent 手动处理。还没在真实页面上遇到过。
- 用户原话：「你再看一下opencli browser skill，看有没有能复用的」；原则是「能复用opencli中的就复用」。
- 可复用的现成实现：OpenCLI 2.x 的 `opencli browser frames --session <s>` 列出跨域 iframe，`eval --frame <target>` 在选中的 frame 里执行。找 PDF 时可以先列 frame，再在每个 frame 里跑同一段查找。
- 代价：每次查找多一到几次 opencli 调用，而 `find()` 在等待循环里每秒都要调。如果做，只在第一次看页面时查 frame，循环里不查。
- 方向：等真实页面上遇到这种出版商再做，到时记下是哪个站。
- 状态：已解决（2026-10-31）
