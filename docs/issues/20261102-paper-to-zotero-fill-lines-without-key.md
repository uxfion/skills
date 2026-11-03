# paper-to-zotero：fields_from_results 写出的行没有条目 key，tidy judge 按 key 去找就漏掉了

- 来源 · 日期：2026-11-02，整理 99 篇没打标签的论文时发现，见 [archive/20261102-paper-to-zotero-untagged-old-items-fixed.md](archive/20261102-paper-to-zotero-untagged-old-items-fixed.md)。
- 现场：
  - `fields_from_results -o fill.jsonl` 写的批量行是 `{"cite": …, "set": …}`，条目 key 是 null。它打印到 stdout 的行里倒是有 key。
  - tidy-judge.md 规定：`missing_abstract` 的条目在 fill.jsonl 里有对应的行就判 change，没有就判 leave。
  - judge 3 拿条目 key `YGRAUL9R` 去 fill.jsonl 里找，没找到，判成了 leave。其实 fill.jsonl 里有这篇（`boumeridjaEnhancingFetalUltrasound2025`）的摘要行。judge 1 是按引用键找的，就找到了。
  - 主 agent 合并各份结果时发现，改正了。
- 为什么要紧：能补上的摘要会悄悄漏掉。三个 judge 里只有一个出错，要靠主 agent 逐条核对才发现。
- 方向（没拍板）：`fields_from_results` 写的行同时带上 key 和 cite；或者在 tidy-judge.md 里写明按引用键对。
- 状态：open。
