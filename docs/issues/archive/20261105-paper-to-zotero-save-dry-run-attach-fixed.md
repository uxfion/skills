# paper-to-zotero：`save -n` 对还没建条目的记录，attach 一律报失败

> **已解决（2026-11-06）**：`attach -n` 碰到还没有条目的记录，当它已有 `save` 先跑的 `create` 会建的那个条目：照常检查结果和文件，列出会挂上的每个文件（名字、标题），记 `ok`，不再报 `no_item_key`。真跑照旧要条目已在。像 `make -n`，后一步按前一步做成了来预览。p2z 的整套测试里加了一条：新记录上 `save -n` 两步都是 `ok`，假 Zotero 没有写入。

- 来源：2026-11-05 全流程试用，一个只看 skill 文档的导入 agent 报告，主 agent 读代码核实。用户没有提。
- 状态：open。

## 经过

- **跑的什么。** 导入 3 篇新论文时，agent 在真正 `save` 之前先跑了 `p2z.py save -n <records>`。
- **看到什么。** 每条记录都是 attach `no_item_key`，整个命令 exit 1；去掉 `-n` 正式跑，exit 0。
- **原因（读代码确认）。** `save` 依次跑 `create` 和 `attach`（`p2z.py` 的 `compound`），`-n` 原样传给两步。`create -n` 不建条目，`attach_file.py` 第 130 行起不管是不是空跑，都要条目已经存在，没有就 `cli.Stop("no_item_key")`。所以任何一条新记录，`save -n` 都会失败。
- **为什么不顺。** 按约定（原则 §3 的字母表），`-n` 是"列出会做什么，什么都不做"。现在它对新记录永远报失败、exit 1，agent 看不出正式跑会不会出问题。这次 agent 只好忽略这个失败，直接正式跑。

## 建议

空跑时，`create` 那一步本来就要建的条目，`attach` 不再报 `no_item_key`，而是逐个文件列出会挂上去的附件（标题、文件），exit 0。测试加一条：新记录上的 `save -n` exit 0，而且什么都没写进假 Zotero。
