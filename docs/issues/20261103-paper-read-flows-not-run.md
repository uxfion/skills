# paper-read：实现了、还没在实际中跑过的流程

- 来源：用户 · 2026-11-03，准备关论文笔记那张 issue 时：
  - 「快速复用这个先不用管吧，我觉得后面在实际的项目中用起来了，如果有什么问题的话，我会让项目中的 Agent 开张issue到这边来的」
  - 「但是读起来快不快倒无所谓，因为毕竟主要是给 Agent 看的，我自己只是大致扫一下」
  - 「你其他哪些流程如果还没跑过，要不要你先挪出来，然后把这张issue给关掉？」
  - 「你先把没有做的东西分离出去，因为我怕到时候这张关了以后，有一些必要的信息给丢失了」
- 状态：open。从论文笔记那张 issue（[archive/20261028-paper-to-zotero-paper-notes-fixed.md](archive/20261028-paper-to-zotero-paper-notes-fixed.md)）分离出来。设计见 spec [20261102-paper-read-notes-spec.md](../specs/20261102-paper-read-notes-spec.md)，现在的做法以 `paper-read/` 里的 skill 为准。
- 参考资料（`20261103-paper-read-flows-not-run-reference/`，git 不跟踪）：
  - 关闭前的设计原则审阅 `principles-review-20261103.md`；
  - 引文比对的盲测记录 `check-quotes-heldout.md`；
  - 4 个项目的现状调研 `project-*.md` 和项目路径 `paths.md`（第 4 条要用）。
- 用法：项目里第一次用到下面哪一条，就顺手核对一遍：跑通的打勾，记下日期和现场；碰到问题按 AGENTS.md 另开 issue，这里写一句指过去。全部跑过就关。

## 已经实际跑过的（2026-11-02 到 11-03）

- 整篇精读 T-CACE：读论文的 subagent 用 31.9 分钟、29.5 万 token、94 次工具调用。笔记 19 问、31 条引文，包整理完，存进 Zotero。
- 查一处 VDSR：新建只含一问的笔记（`--bare`），存进 Zotero。
- 改一条已有笔记再存回：修 T-CACE 标题里的公式，走了一遍取出 → 改 → 检查 → 存。
- `version_conflict` 之后重新取出再存（在一条测试笔记上）。
- 项目索引的标题行由 `index_heading.py` 生成，给用户看过样例，没写进任何项目。
- 读论文时修库里的问题：主 agent 给 T-CACE 补了 `aka/T-CACE`。

## 2026-11-05、11-06 又跑过的（2026-11-09 对照运行记录核对）

这三次都没更新本 issue，11-09 补记。运行记录：本仓库上一个会话的主对话和 subagent 记录，以及颈动脉三维重建项目 11-06 的会话记录。

- **11-05 全流程测试**：新导入 3 篇（SonoWorld、UIV-US、FSCG），各派一个 subagent 自己当读论文的 subagent 跑完整个流程。取出都是 `ok`，包导入时就有了。
- **11-06 批量精读 16 篇**：UNSB 先试读一篇，取回逐字对比、标注框逐个看过；再分 8 篇、5 篇两轮并行。下面三项因此算跑过：
  - 同时派几个读论文的 subagent：第一轮 8 个，是用户那次说的「最多8个subagent」；SKILL.md 写的是最多 5 个。
  - 要问用户的事攒成一条消息：旧笔记要不要进回收站（11 篇上 23 条）、用户自己的两篇读不读。旧笔记那一问用户还没答。
  - 读论文的 subagent 报库里的问题，主 agent 核实后改：补了 9 个 `aka/`、`dataset/`、`venue/` 标签；MINIM"缺摘要"一说核实是过时的，没改。
  - 16 篇取出都是 `ok`：没碰上 `no_package`、`two_notes`、`better_pdf`；主 agent 没有退回过读论文的 subagent（MINIM 两处表名漏了前缀，主 agent 自己改了再存）。
- **11-06 颈动脉三维重建项目里第一次真用**：项目的 agent 新导入 5 篇高斯泼溅论文，自己当读论文的 subagent 写了 5 条笔记，`check --full` 都是 `complete`，存进了 Zotero。
  - `prepare_note`（现在的 `pr.py take`）对 5 篇都报 `no_package`。它没按提示去解析，直接读 PDF。理由是用户在那个项目里说过「训练不要用本机上面的 GPU」，它把这句套到了解析上，判断"没有 GPU 可用"。其实 paddleocr 可以用 vllm-serve 在远程服务器上起模型。结果：5 篇没有结构化包，笔记里的图表没有链接，以后查这 5 篇也没有包可读。这算第 5 条"没装 paddleocr，只读 PDF"跑过，不算 `no_package` 跑过。
  - 项目里没有建论文索引：它把 5 条笔记的 key 列进了自己的调研文档。

## 还没跑过的

1. **更正**（spec §3.5）：改笔记里一条事实，留更正标记；本项目依据它的决定当场重判；别的项目在汇报里告诉用户。
2. **换版本**（issue 已定 51，spec §12 第 14 条）：
   - 库里进了比笔记那份更好的 PDF 时，`pr.py take` 报 `better_pdf`；用 `--title` 取新版，`previous` 带出旧版的 PDF 和包；
   - 读论文的 subagent 按 reading.md *Moving to another version* 逐段对比两份包，处理每一处差别，回报里列出。
   - 要看的：两份包的 Markdown 结构差得大时，逐段对比会不会满是噪音；"新版删去了这段"的标记写得顺不顺；正文的「读的版本」一段改对没有（这是唯一的一处，元数据区的 `pdf:` 2026-11-04 去掉了，见下面「已定 49 改了」）。
   - 2026-11-04 出处链接实测时跑过取和存这两头（CycleGAN 的一条测试笔记，从 arXiv v7 换到 Published-CVF）：`--title` 取新版、`previous` 带出旧版；改「读的版本」后 `put_note` 存，链接全部换成新 PDF 的 key、新 PDF 上建了框，旧 PDF 上的框留着。读论文的 subagent 逐段对比两份包这一段没跑。
   - 2026-11-09 查过：库里 24 条论文笔记逐条 `pr.py take`，`better_pdf` 都是空的，没有现成的场合。
3. **主题笔记**（spec §3.6）：一条都没建过。
   - 要先在 Zotero 里建"主题笔记"分类。
   - 原验证清单里有一项还没做：p2z `note put` 写 `related` 以后，论文条目那一侧的"相关"里能不能看到这条主题笔记。
4. **项目论文索引在真项目里落地**（spec §3.4、§5；各项目的现状见参考资料 `project-*.md`）：
   - 第一个索引可以是 ceus 的：它考虑过 T-CACE 能不能作 B-only 方案（spec §2 的例子）。
   - T-CACE 的旧笔记"精读要点 2026-09-23"（key `4I8PKU67`）里"现在可用 / 未来可用"两节是某个项目（看起来是 ceus）的结论。这两节搬进那个项目的索引或文档以后，问用户能不能把旧笔记移进回收站。用户 2026-11-03 同意先留着。
5. **几条分支**（同时派几个、问题攒成一条、报库里的问题，11-06 已跑过，见上）：
   - `two_notes`（一篇论文有两条"论文笔记"）；
   - `no_package`：用 paddleocr 解析、`p2z.py package put`、再 `pr.py take`（11-06 项目里碰上过，但没解析，见上）；
   - 没装 paddleocr，只读 PDF（11-06 项目里实际走了这条，见上）；
   - 读论文的 subagent 没过检查，退回同一个 subagent（Claude Code `SendMessage`），或者接不上时另派一个。
6. **按问题查阅其他版本和补充材料**（2026-11-09 加的 SKILL.md *Additional sources*，见 [archive/20261106-paper-read-elsewhere-in-library-fixed.md](archive/20261106-paper-read-elsewhere-in-library-fixed.md)）。分两半，各自核对：
   - **主 agent 单独查一处**（精读以外）：主 agent 自己用 `p2z.py package take <paper> --title "<附件标题>"` 取另一个附件来查，笔记的主要版本不变。
   - **读论文的 subagent 精读时查**：要看它会不会该查的时候真去查（CycleGAN 那类，正式版指向 arXiv 版的附录），而且主 agent 的说明里不提示。
   - 两半都要看：补充事实注明各自的文件和位置，其他附件的图表写成显式页链接，`pr.py put` 不会把它们误链到主要 PDF；`pr.py quotes` 报的其他附件引文，有没有对照那份 PDF 核对后标上「已核对」；库里没有的资料，由主 agent 经 paper-fetch 取来。

## 已定 49 改了（2026-11-04）

已定 49 原来是"读的是哪份 PDF，元数据区和正文各记一份"。元数据区里自己加的字段存不进 Zotero，用户选了不去修存储、而是不再往元数据区记：「第一个问题，你根据我们的设计原则想一下，我感觉还是会选 A，就是去掉在笔记里面存它的原数据。因为本身我的笔记里面已经提到了主动提取。」

- 现在只在正文的「读的版本」一段记，`pr.py take`（当时的 `prepare_note`）本来就只读这一段；新建的笔记不再写 `pdf:`。
- p2z `note put` 遇到 Zotero 存不下的字段直接拒绝（`bad_front_matter`，列出字段），不再悄悄丢掉。
- p2z 那张 issue 随之关闭：[archive/20261102-paper-to-zotero-note-front-matter-fields-fixed.md](archive/20261102-paper-to-zotero-note-front-matter-fields-fixed.md)。

## 关闭前审阅剩下的（2026-11-03；小问题 2026-11-04 处理）

用户 11-03：「重要的你可以审一下，但是那种不重要的，我觉得没必要逐一细节去过」。重要的 9 条改了（spec §12 第 15 项）。

13 条小问题（参考资料 `principles-review-20261103.md` 第 11–23 条），用户 11-04：「你也是一样，按照我们的设计原则过一下，看是否符合，如果符合我们的设计原则的话，你就修了它」。逐条对照设计原则过了：

- **修了**：
  - 11：版本顺序改为指向 `read_library pdf --help`。
  - 12：加了测试，`prepare_note` 写出的骨架要等于 note-format.md 的骨架，`check_note` 的 Q5、Q6 固定项要等于文档的清单。
  - 13：`[等 Q5] → Q5.1` 答完写成 `[已答] → Q5.1`。
  - 14：上网规矩补上手工操作，只有用户能过的关卡交回主 agent。
  - 15：另派新的读论文 subagent 时，带上没过的检查输出和上一位的回报。
  - 16：两处用词。
  - 17：回报的 package 一节只要 open 和 `unresolved`。
  - 18：随已定 49 一起去掉了 `pdf:`。
  - 19：重跑 `prepare_note` 用同样的参数。
  - 20：后两处，check_note 帮助里的文件名、index_heading 的排序说明；前一处（`--package` 没有 `.md` 时不报）之前已修。
  - 21：其他 `failed` 和 index_heading 找不到时，照 p2z 那一行的 `hint` 做。
  - 22：`fake_p2z` 写明照抄的是 p2z `2788f2b` 的输出。
- **没修**：23（可选）。真 Zotero 去掉结尾换行这件事，`note_md.to_note` 已经处理，真编辑器也核对过；再让假 Zotero 也这样，测试抓不到更多问题，按「少而强的测试」不做。

还留着的：

- **要用户定的一条**（审阅第 9 条）："读的版本"现在只记 PDF 的标题，标题会被整理改掉。如果同时记下附件 key，改名以后 `pr.py take` 能按 key 找回同一份 PDF。这要改已定 49。
  - 2026-11-04 设计出处链接时查到的两条事实（[source-links spec](../specs/20261104-paper-read-source-links-spec.md) §4.3，那份设计不碰这件事）：出处链接存进 Zotero 后，每个链接里都带着 PDF 的附件 key；`p2z.py pdf`（当时的 `read_library pdf --cite`）已经列出每份 PDF 的 `attachment` 和现在的标题，按 key 找回不用给 p2z 加新路径。
  - 2026-11-09 补：`pr.py take` 对改了名的 PDF 现在报 `no_such_title`，带出库里各份 PDF 的标题，由主 agent 判断是不是同一份改了名（SKILL.md *Every change to a note* 第 1 步）。还缺的：找回后谁改「读的版本」那一行；包按 PDF 标题挂，PDF 不经 p2z 改名时包会找不到。
- **引文比对的规范形式修过 bug 以后，在新论文上再盲测一次**：原来那两篇已经用过，修完以后的重跑只算回归检查。

## 相关的 issue（各自开着，不在这里做）

- paddleocr 的两张（2026-11-04 已修，在 `archive/`）：`20261102-paddleocr-download-stamp-false-findings-fixed.md`、`20261102-paddleocr-commit-merges-heading-and-paragraph-fixed.md`。
- 笔记的呈现：`20261103-paper-read-note-images.md`（暂停）、`20261103-paper-read-note-expression.md`、`20261103-paper-read-note-two-depths.md`；出处链接那张 2026-11-04 做完，在 `archive/20261103-paper-read-source-links-fixed.md`。
