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
