# paddleocr：一张主图被拆成很多小图

> 2026-10-07 记录 · 状态：open（修法还没定）。原是 [20261006-paddleocr-setup-fixed.md](20261006-paddleocr-setup-fixed.md) 第 9 节的一条，同日拆出来单独成 issue。

用户：「在实际用的时候，发现它会把一个主图分散得很小」。

原因出在版面检测：PP-DocLayoutV3 的 25 个类别里没有「整张图」这一级，多面板图的每个子图各出一个 `image`/`chart` 框，流水线按框裁图，所以 Markdown 里是一串小图，面板字母（a、b、c）则成了单独的 `figure_title` 块。单独跑版面模型确认过：TMI 第 7 页 Fig. 4 出了 9 个 chart 框，Fig. 6 出了 6 个，都没有包住整张图的框；把 `layout_merge_bboxes_mode` 改成 `large` 结果不变，因为它只处理互相包含的框。6 篇测试论文共 201 个图块，Nature 第 14 页的一张图被拆成 30 块，每块约占页面的 0.5%。

- 附带发现：TMI Fig. 5 的第一个面板，在流水线自己渲染的页面图上（pypdfium2，scale 2）版面模型没有检出；换成 pdftoppm 144 dpi 渲染，得分是 0.43（阈值 0.3）。这个面板在 Markdown 里直接丢了，也没有任何 warning。
- 用户追问（同日）：「你查一下，没有相关的issue吗？理论上一个大图，主图，框架图，都不应该被划分成小图」。查了 PaddleOCR 和 PaddleX 两个仓库的 issue：
  - 直接相关的只有 [PaddleOCR #18081](https://github.com/PaddlePaddle/PaddleOCR/issues/18081)（open，2026-07）：VL-1.5/1.6 把同一行并排的几张图拆成几个块，各占一行。回复的人（不是维护者）说，restructure 阶段对「同一水平行内的多图」没有做行内聚合，临时办法是拿到 JSON 后按 bbox 的 y 坐标重叠自行合并。目前没有官方修复。
  - [PaddleOCR #18215](https://github.com/PaddlePaddle/PaddleOCR/issues/18215)（open）列了 PP-DocLayoutV3 相对 V2 的一批漏检和阅读顺序问题，和上面那个漏掉的面板是同一类问题。
- 流水线有意不合并图块：`paddleocr_vl/pipeline.py` 调 `merge_blocks(..., non_merge_labels=image_labels + ["table"])`，而 chart 识别关闭时 `image_labels` 也包括 `chart`。`merge_layout_blocks` 只合并文字块。
- 这个问题不是 V3 才有的：在同样的三页上跑 PP-DocLayoutV2（VL 1.0 用的那一代），拆法几乎一样。TMI 第 7 页 V2 和 V3 都出了 18 个图块，Nature 第 14 页都是 30 个；V2 只是把 Fig. 5 的第一个面板和第二个合成了一个框（得分 0.34），所以没有漏掉它。
- 拆还是不拆，取决于图的构成。粗略统计 6 篇论文的约 73 张图：53 张是一张图，包括 LDM Fig. 3、SDEdit Fig. 2 这类单张的框架图；20 张被拆成 2 到 9 块。被拆的都是由几个分开的子图拼成的组图：一排或一格一格的面板、Nature 那种 a–f 多面板图，也包括 Nature Fig. 1 这种由 a、b、c 三个带边框的分块组成的框架图（拆成 3 块，每块本身完整）。
- 可选的修法：`parse.py` 在 Markdown 里把同一个图注上方相邻的图块合成一张图：取这些框的并集，横向扩到图注的宽度，纵向延到图注上沿，从页面图重新裁一张；JSON 保留原来的分块。横向扩到图注宽度，也能把 Fig. 5 漏掉的那个面板补回来。还没定。
