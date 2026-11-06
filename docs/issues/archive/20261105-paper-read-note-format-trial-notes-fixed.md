# paper-read：笔记格式上，读论文 agent 拿不准的几处

> **已解决（2026-11-06）**：1. 空行：没改转换代码。列表项里嵌的块紧贴上一行、表格分隔写成 `| --- |`，是 p2z 拆分 spec（20261030）§5 定下的转换结果，笔记内容不变，`pr.py check --full` 照样 `complete`；note-format.md 那条改成"你写的每个块前空一行"，并说明取回来的笔记长这样、是同一条笔记。改代码要动 100 个样例里的 18 个，得另起 spec。2. 公式多的句子：*Evidence* 写明文字层没有 LaTeX，挑纯文字的句子引。3. `package_only`：和找不到的引文一样先对 PDF；包读错了就引 PDF、把包里那处 `ocr.py commit` 改掉。4. 整张表逐格核对过：标一个（已核对），放在介绍这张表的那句后面；Markdown 表格放进 Zotero 能保留（一行表头的原样回来，别的保留为 HTML）；问题标题里的 Fig./Table 不会被加链接（标题行本来就跳过，例子写进"不加链接"那条，测试照它查）；`package put` 会把被替换的旧包放进回收站，SKILL.md 第 4 步写明（派生的副本，不用问用户）。另修：`put` 读 `ocr.py objects` 出错那行改从标准输出读（paddleocr 改了约定后的位置），有测试。

- 来源：2026-11-05 全流程试用，三个读论文 agent 报告。第 1 条是 SonoWorld 的 agent 把笔记放进 Zotero 后再取出来比对得到的，其余几条都是 agent 拿不准的地方。用户没有提。
- 状态：open。

## 经过

1. **列表项下面嵌着的引文，空行在 Zotero 里来回一趟就丢了。** note put 再 note take 回来，列表项和嵌在它下面的引文之间的空行没了，`|---|` 也变成了 `| --- |`；表格本身保留了下来。note-format.md 要求"每个块前空一行"，在这种位置做不到。要么格式里写明不要把引文嵌在列表里，要么让转换保留这个空行（p2z 的 `note_md`）。
2. **公式多的句子不适合当引文。** 引文里的 LaTeX 写法（如 `\gamma`）和 PDF 文字层（γ）对不上，`check_quotes` 就找不到；MICCAI 那篇的 agent 只好换成一句纯文字的。note-format.md 可以提醒一句。
3. **`package_only` 不一定是引文错了。** SonoWorld 的一条引文只在包里对得上，原因是结构化包本身多了个 "the"，引文又是从包里抄的。note-format.md 可以写明：遇到 `package_only`，先对一下 PDF。
4. **拿不准、文档没说的几处：**
   - 整张表逐格核对过，`（已核对 …）` 该标在哪；
   - Markdown 表格能不能在 note put 后保留下来（这次能）；
   - 问题标题里写 Fig. 或 Table 会不会干扰 `put_note` 加链接；
   - package put 把旧包放进回收站，SKILL.md 没提，只有 `p2z.py package put -h` 里写了。

## 待看

逐条决定：哪些写进 note-format.md 或 SKILL.md，哪些改转换代码。
