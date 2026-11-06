# paper-to-zotero：保留预印本时，import.md 没让 paper-fetch 改成"要预印本"

> **已解决（2026-11-06）**：import.md 第 2 步写明，决定保留预印本时先 `pf.py identify --wanted preprint <arXiv id> -o <imp>/fetch/`，再写 `keep_preprint`；完成条件改成"redrafted, or has `wanted: preprint` and its reason to stay"。核实了 `identify` 改了 `wanted` 却报 `skipped: exists`：改成一条规矩，结果文件写过就是 `ok`，并写出改了的 `cite`、`wanted`；`skipped: exists` 只表示文件没变。

- 来源：2026-11-05 全流程试用。导入 agent 报告：保留预印本要用 `pf.py identify --wanted preprint` 重新认一遍，这一步只写在 paper-fetch 的 batch.md 里，import.md 没有。主 agent 对照文件核实。用户没有提。
- 状态：open。

## 经过

- **文件里写的。** paper-fetch `references/batch.md` 第 20 行："A caller that keeps the preprint passes `--wanted preprint`"。p2z `references/import.md` 第 2 步只说"the preprint it is, and its record gets `keep_preprint`"，没说要告诉 paper-fetch。
- **不改会怎样。** `identify` 默认 `wanted: published`。paper-fetch 的规则是：文件的标签版本低于想要的版本时，下一遍取文件会继续往链路下面找（SKILL.md *Get the file*）。所以只有预印本的论文，拿到 arXiv 版、标成 `Preprint-…` 以后，再跑一遍还会去出版商、图书馆系统找正式版。
- **这次碰到的。** 导入 agent 按 batch.md 自己推出来，补跑了 `identify --wanted preprint`。它报告这次 `identify` 回的是 `skipped: exists`，但 `wanted` 其实已经悄悄改了，行里看不出来（这一点是 agent 的说法，没核实）。主 agent 当天导入 UltraDiff 没加这个参数，只是因为只跑了一遍取文件，才没出问题。

## 建议

import.md 第 2 步：决定保留预印本时，`pf.py identify --wanted preprint <id> -o <imp>/fetch` 再认一遍，再写 `keep_preprint`。顺带确认 `identify` 改了 `wanted` 时，它那一行有没有说出来。
