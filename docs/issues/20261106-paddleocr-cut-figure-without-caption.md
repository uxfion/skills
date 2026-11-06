# paddleocr：`ocr.py cut` 新切出的图配不上自己的标题，编号还和新文字块撞

- 来源：2026-11-06 读论文（CycleGAN，`zhuUnpairedImagetoImageTranslation2017`），reader 报告，主 agent 核对了 `pr.py put` 的结果。用户没有提。
- 状态：open。

## 经过

- **跑的什么。** 包里 `p7-0` 一块裁切同时框住了 Figure 7、它的标题和 Figure 8。reader 把 `p7-0` 缩到 Figure 8，再用 `ocr.py cut <folder> p7 --box 51.5,69,545,251` 切出 Figure 7，得到新图 `p7-n1`。
- **看到什么。**
  - 新图被配上了 `p7-1`，那是 Figure 8 的标题，所以 `p7-n1` 的 alt 是 "Figure 8"；`commit` 拒绝改 alt（`edit_refused`）。结果包里有两张 "Figure 8"，没有 Figure 7。
  - reader 照文字层补回 Figure 7 的标题，成了一个没有框的文字块，编号也是 `p7-n1`，和新图同号，排到第 7 页最前。
  - 另一处：模型把正文 "important problem for future work." 读成了标题（`p8-4`），Markdown 里改不回正文，只能把它并进上一页的段落。
- **为什么不顺。** `ocr.py objects` 碰到两个同号标题，`key` 为 null，Figure 7 和 Figure 8 都可能链不上：这次笔记里的 Figure 7 就留成了普通文字（`pr.py put` 的 `unmatched`，why `not_in_package`）。重切合并的图是 settle 的常规操作，碰上一次就错一张图。

## 待看

`cut` 切新图时怎么认标题：让它带上标题块（如 `--caption <block id>`），或者按位置找最近的、还没配图的标题；新文字块和新图的编号分开。标题改正文的事一起看。

## 又碰到一次（同日，USRMamba，`wangUSRMambaAdaptiveRoutingGuided2026`，IEEE 录用版）

- **切开合在一起的图，Markdown 里没有图片行。** 第 9 页一块裁切框住了 Fig. 6–9，reader 用 `cut` 切成四张（`p9-n1`、`p9-n2`、`p9-n3`、`p9-7`），新框里都没有图像块，于是 Markdown 里四张图都没有 `![…]` 行。手动加一行，`commit` 把它记成了文字块，还占了图的编号 `p9-n1`。
- **图区域里的标题没被解析出来。** 第 11 页 Fig. 11、Fig. 12 的标题在模型给的图像区域里，解析时丢了。reader 照文字层补回成文字，没有框；`objects` 里 Fig. 11（`p11-n1`）没有 key，Fig. 12（`p11-n2`）和 `p11-2` 一起算成了 `fig:13`，所以笔记里 Fig. 13 的框把 Fig. 12 也框了进去。改 alt 被拒（`edit_refused`）。
- **挪段落等于删了再加。** 把两段挪到 Table X 后面，`commit` 记成删除加新块，这两块就没了框。

三件和上面是一回事：`cut` 和新块都没有办法说"这是哪张图、哪段标题"。修的时候一起设计：`cut` 产生的图要有图片行、能指定标题；新文字块和新图的编号分开；图区域里的标题文字要能落成那张图的标题。
