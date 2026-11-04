# paper-to-zotero：笔记元数据区里自己加的字段，存进 Zotero 后就丢了

> 已修（2026-11-04），没走下面"让字段存进 Zotero"的方向：
> - 唯一要存的字段是 paper-read 的 `pdf:`，它只是正文「读的版本」的备份，`prepare_note` 从来只读正文。用户：「第一个问题，你根据我们的设计原则想一下，我感觉还是会选 A，就是去掉在笔记里面存它的原数据。因为本身我的笔记里面已经提到了主动提取。」paper-read 新建笔记不再写 `pdf:`，已定 49 随之改了（见 [20261103-paper-read-flows-not-run.md](../20261103-paper-read-flows-not-run.md)「已定 49 改了」）。
> - p2z `note put` 遇到 Zotero 存不下的字段直接拒收：报 `bad_front_matter`，列出 `fields`，什么都不写，本地文件原样留着；agent 把信息写进正文或删掉再存。另一个方案是照存、只在输出里提示丢了哪些字段。用户选了拒收：「A，按拒收来」。改在 `note.py`（白名单用 `note_md.FIRST`）、它的测试和 organize.md 的 *Notes*。
> - 参考资料文件夹里还放着拆分 issue 留下的 Node 裁判（用 Zotero 笔记编辑器自己的代码算出一条笔记会被存成什么）。用户：「但是问题是，现在笔记转换不是已经做好了吗？可以装，你验证一遍没问题，然后就删吧 C」。在临时目录 `npm ci` 后跑了它的 `validate.py`：三条检查都是 `True`（往返测试笔记：送进去的经裁判，等于实测保存去掉用户加的一项；实测保存是不动点；79 例笔记的实测保存也是不动点）；79 例笔记送进去的经裁判和实测保存比，差 5 处，全是用户当时手改的（加的两段字、改的注释行、改的标题结尾、删掉的「段一」）。和 2026-10-30 真编辑器核对的结论一致。之后文件夹连同裁判删了，临时目录里装的依赖也删了。
> - 技术审阅报告（下面"参考资料"）随这张 issue 关闭删了；它第 1 条就是本 issue，第 13 条已抄进 paddleocr 的水印 issue，其余各条的处理记在归档的论文笔记 issue 第 70 条和 paper-read spec。

- 来源 · 日期：2026-11-02，审 paper-read spec 时，技术审阅的 agent 实测发现（技术审阅报告第 1 条，关闭时已删）。用户：「元数据区，你看能不能做一个 issue，然后让p2z那边去修复一下」。
- 现场：笔记在 Zotero 外面是一份 Markdown，开头 `---` 包起来的那几行是元数据区。paper-read 想在里面记"读的是哪份 PDF"（`pdf: Published-IEEE`）。
  - `note put` 不报错，也不用这个字段：`note_md.to_note` 把 `schema`、`citation-items` 以外的键都当元数据交出去（note_md.py:401–408），`put_one` 只读 `key`、`version`、`parent`、`collections`、`related`（note.py:207–221、239–251）。
  - `put -i` 把新的 key 和 version 并进本地文件的元数据区（note_md.py:66–69，note.py:348–350），所以本地文件里 `pdf` 还在，看不出丢了。
  - 下次 `note take`，元数据区按 Zotero 里的条目重建，只有 `key`、`version`、`parent`（note.py:114–123）。
  - 实测：照 spec 的空笔记 put 再 take，差别是 `+key … +version … -pdf: Published-IEEE`。
- 为什么要紧：
  - 自己加的字段悄悄丢掉，不报错，要等下次取出才发现；
  - paper-read 要靠"读的是哪份 PDF"取同一份 PDF 核对引文。T-CACE 就有 Published-IEEE 和 Preprint-arXiv-v1 两份，不带 `--title` 的 `structured take` 会取"最好的那份"（structured.py:128–133）。以后库里来了更好的版本，取到的就变了。
- paper-read 那边的做法（论文笔记 issue，第 77 条）：元数据区和笔记正文各记一份，正文那份兜底。这里修好以后，元数据区那份才算数。
- 方向（没拍板，由维护 p2z 的会话来定）：让元数据区里自己加的字段跟着笔记存进 Zotero、取出时还原。至少要做到：存不了的字段要报出来，不能悄悄丢。存的办法要先调研：笔记 HTML 里藏一段数据，编辑器和 Better Notes 会不会改写或删掉它；或者用 Zotero 别的地方存。拿真编辑器往返试过再定。
- 状态：已修，见开头。
