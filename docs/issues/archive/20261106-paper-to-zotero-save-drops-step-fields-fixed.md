# paper-to-zotero：`save` 只转出每一步的代码，create 和 attach 给的提示字段丢了

2026-11-09 已修复：[组合命令](../../../paper-to-zotero/scripts/p2z.py)保留子步骤完整结果，[导入说明](../../../paper-to-zotero/references/import.md)直接处理提示，去掉仅为找回丢失信息而增加的补查。本次修改不改变顶层状态和退出码的判定。

- 来源：2026-11-06 paper-to-zotero 文档通读，subagent 核对 `save` 时发现，主 agent 核对了代码。用户没有说过这件事。
- 状态：fixed。

## 看到的

`p2z.py save` 依次跑 create 和 attach，每条记录给一行 `{slug, code, decide?, failed?, steps: {word: its code}}`。`steps` 里只留每一步的 `code`（skipped 时加 reason），步骤那一行的其他字段都丢了（`p2z.py` 的 `compound()`：`steps[slug][name] = … code`）：

- create 的 `citation_key_hint`：引用键里有 TeX 特殊字符（`^`、`_`、`&` …），`\cite{}` 会坏，附建议的键；
- attach 的 `unconfirmed`、`unchecked`（附上了但没确认是这篇的文件、桩结果的 PDF）和每个文件的 `suggested_title`；
- 没做完的那一行的 `hint`。

当时 import.md 第 5 步有一条 "`citation_key_hint`: … ask the user, then `p2z.py update <key> --set citationKey=<suggested>`"。可导入时走的是 `save`，这一行永远看不到，这条指示也就永远触发不了。`unconfirmed` 能从导入报告（`p2z.py report`）补上；`unchecked` 不在报告里，和可附文件混合时连步骤码也看不出来。

2026-11-09 核实并改正文档：现有 `lint` 已能报告 `citation_key / tex_special`，不需要新问题码。import.md 改为检查新条目，并在结果文件未全部附上时单跑 `attach` 取得文件名和提示。组合命令是否保留子步骤字段仍待定。

## 为什么要紧

引用键带特殊字符的论文，导入时没人提醒，等稿件编译 `\cite{}` 出错才发现。这也和 design-principles 的 *Orchestrate, don't absorb* 相背：组合命令吞掉了下层命令的输出。

## 已定方案（2026-11-09）

- 用户原话：「可以，按照你建议的推进吧」。此前用户要求重新评估：「你再过一遍，方案A是否是最合适的」。
- `steps` 保留每个子步骤的完整结果对象，去掉重复的 `slug`；正常、跳过、失败使用同一种对象结构。共用实现的 `prepare` 和 `save` 一起修改。
- 导入说明直接处理每步的完整结果，成功或跳过时也读取附带字段；删除仅为补回丢失信息而增加的 `lint` 和重复 `attach`。最终报告仍读回真实库核验。
- 保留现有调度、顶层汇总和退出码；不为旧字符串结构增加兼容开关。
- 比较后放弃：另设详情字段会重复存状态；挑选字段会继续维护漏项；直接输出各子步骤行会增加同篇论文多行结果的关联；删除 `save` 会把每轮的调用和汇总交回执行 agent。

## 核实的影响

本地模拟库复现：正文已附上、另一个文件 `cannot_judge` 时，`attach` 返回 `ok` 和 `unchecked` 名单，旧 `save` 只返回两步 `ok`。首次创建的 `citation_key_hint`、写入后校验异常的 `wrong` 和 `hint` 也会丢失；重跑 `create` 因为条目已保存而直接跳过，无法恢复首次诊断。没有发现这次输出遗漏已造成真实库写坏的证据。

现有报告覆盖未确认文件和建议改名，不覆盖 `unchecked`；`lint` 可以重新发现引用键建议，但增加一次库读取。仓库内没有生产脚本解析旧 `steps` 字符串值，直接消费者是组合命令的测试和文档。

## 验证

- `test_p2z.py` 的完整导入场景验证首次引用键建议、失败提示、成功及跳过结果中的未检查文件名单，并确认 dry-run 和重跑不增加库写入。
- 模拟库的写入后校验异常验证首次 `wrong` 和 `hint` 直接出现在 `save` 中；无输出退出的子步骤仍返回对象，后续附件步骤不运行。
- 创建、附件、报告、跨技能结果格式的既有回归，以及仓库约定检查通过。未向真实 Zotero 库写入。
