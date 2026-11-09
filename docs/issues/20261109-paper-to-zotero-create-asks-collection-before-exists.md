# paper-to-zotero：给库里已有的论文补一个版本，`create` 先要分类才肯认出它已在库里

- 来源：2026-11-09 精读那一轮，主 agent 派导入 subagent 给 SDEdit（`meng2022sdedit`，库里已有，只有 Preprint-arXiv-v2）补 ICLR 2022 正式版 PDF。subagent 回报，主 agent 读了代码核实。用户没有提。
- 状态：open。

## 经过

- **跑的什么。** 导入流程走到 `p2z.py save <imp>/records/meng2022sdedit.json`，其中 `create` 这一步处理这条记录。
- **看到什么。** `create` 回 `no_collection`（"Put the destination in the record's collection"）。这篇论文早在库里，这次只是补一个版本，不新建条目，也就用不上分类。subagent 把条目现有的两个分类（GPUICTEH、WQ9TZLY7）填进记录，再跑一次，`create` 才回 `skipped: exists`（按 arXiv id 认出来），条目没动。
- **原因。** `paper-to-zotero/scripts/create_item.py` 的 `process()` 先调 `payload_of()`，在那里对没有 `collection` 的记录报 `no_collection`；查库里有没有这篇的 `run.look_up()` 排在它后面。
- **为什么不顺。** 给已有论文补版本是常见操作（补正式版、补补充材料）。要填一个不会被用到的分类才能过，下一个 agent 很可能照提示去问用户"放哪个分类"，白白多问一次；或者随手填一个，记录里留下假信息。

## 待看

`create` 先查库里有没有这篇，有就 `skipped: exists`，不再检查分类；只有真要新建条目时才要分类。改完用一条没有 `collection`、库里已有的记录试一遍。
