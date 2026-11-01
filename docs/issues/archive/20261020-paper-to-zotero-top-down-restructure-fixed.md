# paper-to-zotero：代码一路复制、各自走样，需要从顶层重新设计

> 已解决（2026-10-20）：按 [重构 spec](../../specs/20261020-paper-to-zotero-restructure-spec.md) 分三期实现——`8b77e53`（共享库和整理脚本）、`85f6eff`（导入流水线）、`d889001`（按路线取全文）——代码审查的修正 `907a4a5`，真实页面测试后的修正 `4c791dc`，已推送并从 GitHub 重装。结果：脚本约 12k 行减到 7.8k 行；22 个脚本都导入 `scripts/p2zlib/`，互不导入；测试共用一个假 Zotero（`tests/fake_zotero.py`）。余下的一处另记为 [跨域 iframe](20261020-paper-to-zotero-cross-origin-frames-fixed.md)。

- 来源：用户 · 2026-10-20
- 现场：讨论最初的需求时（Zotero 里每篇 PDF 有一份结构化版本，任何项目的 agent 都能直接取来读），先盘点了两个 skill 的结构。paddleocr 是新重写的，5 个文件，分工清楚。paper-to-zotero 有 21 个脚本，约 12k 行，测试约 6.9k 行。用 ast 把每个脚本的顶层函数、类、常量取出来，按名字跨文件比对（同名、出现在 ≥2 个脚本里的算一组，按规范化后的语法树判断写法是否相同），结果是：

  | 类别 | 例子（出现的脚本数 / 写法数） | 行数 |
  |---|---|---|
  | 访问 Zotero | `Api`（12 / 8）、`LocalApi`（2 / 2）、`resolve_cite`（7 / 6）、`load_key`（8 / 3）、`check_common`（8 / 3）、`live_server_id`（8 / 3）、`get_json` / `get_list` / `get_item`、`config_path`、`DEFAULT_BASE_URL`（16 / 1）、`LIB`、`KEY_RE`、`CHILD_TYPES` | 约 1270 |
  | 记录的读写流水线 | `load_records`（7 / 4）、`read_json_records`、`write_results`（6 / 5）、`write_record`、`save_record`、`Outcome`、`emit`（14 / 7）、`slug_of`、`STEM_FILES`；单条与流式两种模式的骨架（`run_single` / `run_stream`）在 5–6 个脚本里各写一遍，另约 350 行 | 约 740 |
  | 命令行骨架 | `Stop`（16 / 5）、`log`（17 / 3）、`text`（10 / 2）、`now_iso`（8 / 2） | 约 160 |
  | 领域小规则 | `identifiers` / `ARXIV_ID`、`normalize_tags`、`check_creators`、`retry_after`、各自的 `USER_AGENT` 和限速间隔 | 约 290 |
  | 测试 | 假 Zotero 服务 `Handler`（15 / 15）、`FakeZotero`（3 / 3）、`Base`、`State`、`ITEMS`、`SCHEMA`、`COLLECTIONS` | 约 1260 |

  `main`、`parse_args`、`run` 这类各脚本本来就该不同的不算在内。这是 v1 到 v3、再到整理工具，一路拿旧脚本当模板复制出来的。
  - 更正（2026-10-20）：原来这里写"查过 v3 spec，没有'每个脚本必须自成一体'的决定"，不对。v1 spec §2（用户的明确要求）第 4 条是"脚本单一功能、互不依赖"；v2 spec §4.2 写明"脚本互不 import（重复的 Api / Stop / load_key 允许）"，§4.3 写明测试"不共享 fixture"；v3 spec §5.2 沿用"脚本之间只通过子进程调用，不互相 import"。重构 spec 的 §0 说明了为什么改。
- 痛点：同一段逻辑有好几种写法，修一处、别处还是旧的；加新功能又要再复制一遍。接下来要做的"结构化包存进 Zotero、任何项目取用、核对后写回"由 paper-to-zotero 负责（2026-10-20 与用户确认），要上传附件、移进回收站、按 citation key 查条目，正好落在这些重复最多的地方。用户原话：「你之前说的paper-to-zotero问题需要优化，需要做得比较优雅，可复用。需要全面设计一下，从顶层设计优化，而不是像现在这样修修补补，内容重复，这个应该单独拉一张issue出来优化，作为前置条件。」
- 方向：先写 spec，评审通过再动手，不在现有脚本上逐个打补丁。
  - 从整个 skill 的职责出发重新划分：访问 Zotero、记录流水线、命令行骨架、领域规则各有一个归属，做成共享模块，供各脚本导入（同目录导入，和 paddleocr 的脚本一样）；
  - 脚本仍可单独运行（shebang、`p2z.py`），对外的命令、参数和输出形状尽量不变；
  - 测试共用一个假 Zotero；
  - SKILL.md（200 行）和 references 一并梳理；
  - 新的结构化包流程要能直接复用这些模块。
  - paper-to-zotero 其余未关闭的 issue（IEEE PDF 链接、投稿稿件分类）在同一份 spec 里一起分拣。
- 设计：[20261020-paper-to-zotero-restructure-spec.md](../../specs/20261020-paper-to-zotero-restructure-spec.md)（定稿，2026-10-20）；四份审查报告的结论都写进了 spec（原文已删，最后在提交 `4c791dc`）。
- 前置于：[20261020-paper-to-zotero-structured-package-fixed.md](20261020-paper-to-zotero-structured-package-fixed.md)（Zotero 结构化包流程），这张关闭后才开始做。
- 状态：fixed
