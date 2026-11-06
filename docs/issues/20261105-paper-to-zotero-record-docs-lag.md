# paper-to-zotero：`run.py` 里记录字段的说明落后于 import.md

- 来源：2026-11-05 全流程试用，导入 agent 报告"两处说法不一样，不知道听哪个"，主 agent 对照文件核实。用户没有提。
- 状态：open。

## 经过

导入 agent 写记录时，同一个字段在两处读到了相反的说法：

| 字段 | `scripts/p2zlib/run.py` 的说明（第 15–16 行） | `references/import.md` |
|---|---|---|
| `collection` | `KEY or [KEYS]` | 第 74 行："Put the path (or paths, or keys)"。按 Unix 约定的已定第 8 条，集合认 key、路径和唯一的名字，`create` 也真的认路径（2026-11-05 主 agent 的导入写的是 `tmp`，成功） |
| `keep_preprint` | 只在"result 的 `versions.published` 有内容、却仍保留预印本"时写 | 第 2 步：没有正式版时也写，附上理由；`report` 的"保留预印本"一节，凡是写了的记录都会列出来 |

agent 最后 `collection` 填了 key，`keep_preprint` 照 import.md 写了。两处都能用，只是读的人不知道该信哪一处。

## 建议

以 import.md 和代码的实际行为为准，改 `run.py` 的说明：

- `collection`：key、路径或唯一的名字，一个或一组；
- `keep_preprint`：条目保留预印本的理由，没有正式版、或者有正式版但决定不用，两种情况都写，报告里会列出。

Unix 约定改造时，这处说明没跟着改。
