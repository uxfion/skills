# paper-to-zotero：`save` 只转出每一步的代码，create 和 attach 给的提示字段丢了

- 来源：2026-11-06 paper-to-zotero 文档通读，subagent 核对 `save` 时发现，主 agent 核对了代码。用户没有说过这件事。
- 状态：open。

## 看到的

`p2z.py save` 依次跑 create 和 attach，每条记录给一行 `{slug, code, decide?, failed?, steps: {word: its code}}`。`steps` 里只留每一步的 `code`（skipped 时加 reason），步骤那一行的其他字段都丢了（`p2z.py` 的 `compound()`：`steps[slug][name] = … code`）：

- create 的 `citation_key_hint`：引用键里有 TeX 特殊字符（`^`、`_`、`&` …），`\cite{}` 会坏，附建议的键；
- attach 的 `unconfirmed`、`unchecked`（附上了但没确认是这篇的文件、桩结果的 PDF）和每个文件的 `suggested_title`；
- 没做完的那一行的 `hint`。

当时 import.md 第 5 步有一条 "`citation_key_hint`: … ask the user, then `p2z.py update <key> --set citationKey=<suggested>`"。可导入时走的是 `save`，这一行永远看不到，这条指示也就永远触发不了。`unconfirmed` 能从导入报告（`p2z.py report`）补上；`unchecked` 不在报告里，和可附文件混合时连步骤码也看不出来。

2026-11-09 核实并改正文档：现有 `lint` 已能报告 `citation_key / tex_special`，不需要新问题码。import.md 改为检查新条目，并在结果文件未全部附上时单跑 `attach` 取得文件名和提示。组合命令是否保留子步骤字段仍待定。

## 为什么要紧

引用键带特殊字符的论文，导入时没人提醒，等稿件编译 `\cite{}` 出错才发现。这也和 design-principles 的 *Orchestrate, don't absorb* 相背：组合命令吞掉了下层命令的输出。

## 要定的

- `steps` 改成 `{word: 那一步的整行（去掉 slug）}`，还是只把几个字段提到 `save` 的行上；前者改的是 `save` 和 `prepare` 共同的输出形状，文档里读 `steps` 的地方要一起改。
- 或者维持子步骤输出不转发，由现有 `lint`、`attach` 补充提示；评估额外调用的成本。
