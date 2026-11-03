# paper-read：论文笔记里放图片

- 来源：用户 · 2026-11-03。看过 T-CACE 的笔记之后：「初步看还行，但是我有一个问题：能不能往笔记里面引用图片![]()，这样有图去表达，或者有图去看，效果会更直观一点」；又补：「不，你先要去调查一下，笔记里的 HTML 能不能存图片，也就是能不能引用图片（引用外部的图片，或者用哪里的图片），以及具体是怎么存放的。如果能带上图片，我感觉表达会好很多」。
- 状态：open，**暂停**（2026-11-03）。用户：「那就先这样吧。但是我感觉要不先不要做图片了，因为如果你再去插入主图的话，那和结构化包里面的数据就重复了」。
  - 主图在结构化包里已经有一份，再嵌进笔记，同一张图就存了两份，违背"一样东西只放一处"。
  - 以后想在笔记里一点就看到图，不重复的办法是下面的方案 B：出处带 `zotero://open-pdf` 链接，跳到图所在的页。
  - 下面的调查和实测结果留着，重新考虑时直接用。

## 调查结果（读的是 Zotero 源码，2026-11-03）

**Zotero 笔记里的图片怎么存。** 编辑器插进笔记的图片，存成笔记下面的一个附件，类型是"内嵌图片"（`embedded_image`）。文件放在 Zotero 存储目录的 `storage/<附件 key>/image.png`，和 PDF 一样随文件同步。笔记的 HTML 里只写 `<img data-attachment-key="<附件 key>" width=… height=…>`，不存图片数据。
- 出处：`zotero/zotero` `chrome/content/zotero/xpcom/attachments.js` `importEmbeddedImage`；`zotero/note-editor` `src/core/schema/nodes.js` 的 `image` 节点。
- 现在库里一张这样的图都没有（2026-11-03 查全部 2832 个条目）。

**HTML 里能写哪几种图片。** 编辑器认 `<img>` 的 `src` 和 `data-attachment-key` 两种写法。用户打开一条笔记时，只有 `src`、没有附件 key 的图片，会被自动导入成上面那种内嵌图片附件：
- `src` 是 `data:` 图片（图片数据直接写在 HTML 里）：直接导入，导入后 HTML 里的 `src` 删掉，换成附件 key。
- `src` 是 http(s) 外部链接：Zotero 去下载，下载成功才导入；只认 jpg、png 这几种格式，gif、svg、webp 等不导入。
- 本机文件路径不行：导入走的是网络请求。
- 自动导入只在用户打开笔记时发生；同步或重新载入时不做，只读时也不做；一次超过 25 张就跳过。
- 出处：`note-editor` `src/core/plugins/image.js`（`appendTransaction`、`isUnsupported`）、`src/core/editor-core.js`（打开时 `triggerImagesImport`）、`src/core/commands.js`（`attachImportedImage`）；`zotero` `xpcom/editorInstance.js` 的 `importImages` 和 `_importImage`。

**p2z 能做到哪一步。** p2z 走 Zotero 的本地接口写库。
- 本地接口能建附件，但上传文件只允许普通导入的附件；对内嵌图片附件会拒绝："Cannot upload files for non-imported attachments"（`zotero` `xpcom/server/server_localAPI.js` `handleFileWrite`）。所以 p2z 没法像编辑器那样直接建内嵌图片。
- 读取没有限制：`GET /items/<key>/file` 对内嵌图片同样可用，所以取笔记时能把图片下载下来。
- p2z 的笔记转换现在把 `<img>` 原样留成 HTML，`zotero://` 链接能完整往返（`p2zlib/note_md.py`）。

**两个限制。**
- **笔记长度**：Zotero 服务器对单条笔记的上限是 50 万字符（`zotero/dataserver` `model/Notes.inc.php` `$MAX_NOTE_LENGTH`），超过就同步不了（客户端报 `sync.error.noteTooLong`）。`data:` 图片在用户打开笔记之前，数据一直写在 HTML 里。T-CACE 包里的图每张 0.27–1.9 MB，转成 base64 还要再大三分之一，原图塞一张就可能超。
- **agent 读笔记的成本**：用户打开之前，取出的笔记里是一整段 base64，agent 每读一次都要吃进去。

**图从哪来。** 结构化包里每张图都已经裁好、整理时核对过：`imgs/<figure id>.png`，比如 T-CACE 的方法总览图 Fig. 2 是 `p4-2.png`。不用另外截图。

## 实测（2026-11-03，Zotero 10.0.7，装着 Better Notes）

用户先指出：上面这些都是读源码推的，没有试过；"Zotero 的接口不支持"和"p2z 没写"要分开。于是上网查了官方文档，又在 T-CACE 下建了测试笔记逐一试：

| 方式 | 结果 |
|---|---|
| 1. `<img src>` 写外部网址（用户图床上的 P4-2） | Zotero 把图**下载**下来，存成内嵌图片附件；HTML 里**保留网址**，再加上附件标记。下了**两次**：笔记建好时一次（HUELVEHG，没被引用，成了孤儿附件），用户打开时又一次（S3ANIHZD）。另外还要先把图传到图床上。 |
| 2. `data:` 图片（包里的 p4-2 压成 JPEG，82 KB，base64 约 11 万字符） | 笔记建好后约 1 秒内**自动**转成内嵌图片附件，HTML 里只剩 `<img alt width height data-attachment-key>`，不到 200 字符。没人打开也会转（测试 4），论文没开标签页也会转（测试 5，建在 VDSR 下）。转换后的样子和用户在 Zotero 里右键"插入 → 图片"插进去的本地图**完全一样**。 |
| 3. 直接用本地接口给内嵌图片附件上传文件 | 回 **400 "Cannot upload files for non-imported attachments"**。官方文档也写明本地接口只接受 `imported_file`、`imported_url` 的上传。是 **Zotero 本地接口本身的限制**，不是 p2z 没写。 |
| 读取内嵌图片 | `GET /items/<附件 key>/file` 回 302，指向 `file:///C:/Users/<user>/Zotero/storage/<key>/image.jpg`，p2z 取笔记时能拿到图片文件。 |

- 三条测试笔记用户都打开看过：图都正常显示。
- 是谁在笔记建好时触发了转换（Zotero 本身还是 Better Notes）没查。不管是谁，存完以后读回一次就知道转没转。
- 方式 2 的副作用：转换太快时，`note put` 读回会报 `readback_mismatch`（测试 3），因为笔记已经被 Zotero 改过。p2z 读回时要把"图片被转成附件"算作正常。
- 参考来源：[Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)、[Web API 文件上传](https://www.zotero.org/support/dev/web_api/v3/file_upload)、论坛 [127547](https://forums.zotero.org/discussion/127547/note-embedded-image-export-via-api-received-html)、[103344](https://forums.zotero.org/discussion/comment/103344/)、[388334](https://forums.zotero.org/discussion/comment/388334/)。

## 网上和插件（2026-11-03，用户：「你去网上搜一下，就没有人提出比较好的方案来吗？顺便去看一看zotero的插件」）

- **现成方案：没找到更好的。**
  - 几个 Zotero MCP 服务器（zotero-mcp-local-write、zotero-mcp-server-write、zotero-api-mcp）都只写文字笔记，没有一个支持往笔记里放图。
  - 论坛里 Zotero 官方的老说法：`<img src>` 写网址"可能可行"，其他办法不受支持。
- **Better Notes**：
  - 导入 Markdown 时，会把相对路径的本地图片导入成内嵌图片附件，用的就是 Zotero 自己的插图办法（`src/utils/convert.ts` L937-988，见参考资料 `20261103-paper-read-note-images-reference/better-notes.md` §4）。
  - 但它只能在 Zotero 内部用，没有对外接口。唯一的外部入口是文件夹双向同步，之前已经否掉了：要 Zotero 在前台、每篇笔记要用户手设、文件会被改写、冲突时弹窗（同一份参考资料 §5）。
- **Better Notes 自己怎么插图**（用户问：「我想知道 better notes 里面是怎么做的，就是像我们测试2里面内嵌到HTML，然后让它自己去转换吗？」）：**不是**。
  - 它是 Zotero 插件，代码跑在 Zotero 内部。Markdown 转成笔记时，每张图（`data:`、网址、本地文件三种都认）先自己读成图片数据，直接调 `Zotero.Attachments.importEmbeddedImage({blob, parentItemID: 笔记})` 建好内嵌图片附件。
  - 然后在 `<img>` 上写 `data-attachment-key`，删掉 `src`，最后才存笔记。笔记从头到尾不带图片数据，不靠编辑器事后转换。
  - 出处：`windingwind/zotero-better-notes` `src/utils/convert.ts` `processM2NRehypeImageNodes`（L937-988）、`src/utils/note.ts` `importImageToNote`（L432 起）。
  - 我们在 Zotero 外面，本地接口又不让上传这类附件，所以照搬不了。要做到和它一样，只能在 Zotero 里执行代码（debug-bridge），或者走它的文件夹同步。
- **debug-bridge**（Better BibTeX 作者做的，现在放在 `retorquere/zotero-better-bibtex` 仓库里）：
  - 能经本地 HTTP 在 Zotero 里执行任意 JavaScript，于是可以直接调 Zotero 的插图函数 `Zotero.Attachments.importEmbeddedImage`。这是最原生的写法。
  - 代价：要装插件；开了一个能执行任意代码的本地口子（有密码，仍有安全风险）；skill 要依赖这个插件。
- **Zotero 同步代码**专门有一条报错 `sync.error.noteEmbeddedImage`：笔记里带着 `<img src="data:image…` 而且超长时报（`zotero/zotero` `xpcom/sync/syncRunner.js`）。说明官方知道有人这么写，也说明超长的风险是真的。压缩图片、只放几张，就在 50 万字符以内；何况实测 1 秒内就转换了。
- **没查清的**：测试里 1 秒内的自动转换，是 Zotero 本身还是 Better Notes 触发的。在 Better Notes 源码里没找到直接调用导入的地方。如果是 Better Notes，不装它时要等笔记被打开才转换；在那之前图照样显示，只是笔记先大一些。要确定的话，可以请用户临时禁用 Better Notes 再测一次。

## 点链接跳到图

挪到了 [20261103-paper-read-source-links.md](20261103-paper-read-source-links.md)：实测可行，而且能从结构化包自动生成。

## 可选的做法（没拍板）

- **A. 在笔记里内嵌图片**：笔记 Markdown 里写 `![Fig. 2 方法总览](imgs/p4-2.png)`；p2z 存的时候把图压缩（比如 JPEG、宽约 1000 像素），转成 `data:` 写进 HTML；用户第一次在 Zotero 里打开这条笔记时，编辑器把它变成正式的内嵌图片附件。取笔记时，p2z 把图片（不论是 `data:` 还是已经导入的附件）存成文件，Markdown 里还是 `![](…)`，agent 读不到 base64。
  - 要做：p2z 笔记往返支持图片，加测试；paper-read 规定放哪些图，比如 Q3 的方法总览图、支撑主要结论的图。
  - 风险：用户打开之前就同步，图大了会超 50 万字符的上限，所以要压缩、只放关键的几张。先要实测一次：经 API 写进去的 `data:` 图片，打开时确实会被导入。
  - 可以实测的一个办法：存进去后，立刻用 `zotero://select/library/items/<笔记 key>` 让 Zotero 选中这条笔记。选中时右侧会打开编辑器，按源码这就会触发导入；成立的话，`data:` 在笔记里只停留几秒，超长和 base64 的问题都小得多。
- **B. 链接到 PDF 那一页**：出处后面加一个链接，比如 `zotero://open-pdf/library/items/<PDF 的 key>?page=4`，点一下在 Zotero 里打开 PDF，跳到图所在的页。不占存储，没有长度问题，现在就能做，但图不显示在笔记里。spec §11 原来把这件事放到了以后。
- **C. 两样都做**：关键的几张图用 A 嵌进笔记，其余图表的出处都用 B 链到页面。
