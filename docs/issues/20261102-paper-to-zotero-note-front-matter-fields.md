# paper-to-zotero：笔记元数据区里自己加的字段，存进 Zotero 后就丢了

- 来源 · 日期：2026-11-02，审 paper-read spec 时，技术审阅的 agent 实测发现（论文笔记 issue 参考资料 `spec-review-technical.md` 第 1 条）。用户：「元数据区，你看能不能做一个 issue，然后让p2z那边去修复一下」。
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
- 状态：open。
