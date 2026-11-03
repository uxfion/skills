# paper-read：丰富论文笔记的表达

- 来源：用户 · 2026-11-03。看过 T-CACE 的笔记之后：「另外，内嵌的流程图那些，我看后面能不能也加进去。你开一个 issue 吧，丰富笔记的表达. 插入图片、使用 CDN 上的 Mermaid、使用 CDN 上的 Tailwind 等等。因为目前来看，我感觉全是文字，一眼望过去，不是很有读的欲望」；接着又说：「Mermaid 我只是提到一嘴，后面再说。我们先解决图片的问题」。
- 状态：open，后面再说。图片先在 [20261103-paper-read-note-images.md](20261103-paper-read-note-images.md) 里解决。

## 已知的事实（2026-11-03 读 Zotero 源码时顺带看到，没深查）

- Zotero 笔记编辑器只保留它认识的节点和样式（`zotero/note-editor` `src/core/schema/nodes.js`、`marks.js`）：段落、标题、公式、代码块、引用块、分隔线、列表、图片、引文、高亮等，加上粗体、斜体、带颜色的下划线这类文字样式。没有 `<script>`，所以 CDN 上的 Mermaid、Tailwind 不能在笔记里运行。
- 流程图之类的可行做法：先在本机把 Mermaid 渲染成图片，再当图片放进笔记，走图片那张 issue 定下来的路。
- Better Notes 插件会往每个笔记编辑器里注入自己的脚本和样式（参考资料 `20261103-paper-read-note-images-reference/better-notes.md` §1），它能不能显示 Mermaid 没查。

## 以后要讨论的

- 用户想要的是"一眼望过去有读的欲望"：除了图片和流程图，编辑器现有的手段（表格、高亮、颜色、引用块、分隔线）怎么用，才能让笔记更好读。
