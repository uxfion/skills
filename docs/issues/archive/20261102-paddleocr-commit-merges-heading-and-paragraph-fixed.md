# paddleocr：`doc.py commit` 把标题和下面的段落并成一块，事后拆不开

> 已修（2026-11-04）。原因和下面"现场"里 subagent 的推断不一样：
> - **真正的原因**：commit 比较改动时先把空行都去掉，agent 写的空行从来不算分块的地方。在 T-CACE 包的副本上复现了三种情形：
>   - agent 插进去的「标题、空一行、段落」被记成一个标题块；
>   - 改一块的同时在旁边加一段，新加的段并进了那一块；
>   - 把一块拆成标题和段落，`## …` 作为字面文字留在正文块里。
> - `content_of()` 不是原因。"nothing to commit" 是因为 Markdown 看起来本来就已经分开，改不出差别。
> - **改了**（`scripts/doc.py`）：
>   - 插入的内容按空行切成几块，每块按自己的第一行定类型（标题、表格、公式、正文），修改理由跟着它上面那一段；
>   - 改一块以后段落变多了，commit 拒收：脚本分不清原来那一块该留哪一段。拒收提示里写明先单独 commit 这一块，再把新段落前后加空行插进去、commit 第二次；
>   - 只看"段落变多"。模型给出的块里本来就有空行的（267 篇的解析里，算法块 1465 个中有 611 个）照常能改。
> - **用户选了拒收**（方案 A）。另外比较过：
>   - 按相似度猜：让脚本判断不确定的事，违反设计原则 §1；
>   - 保持原样：记录里块的类型悄悄出错；
>   - Markdown 里每块加编号标记：每个读包的 agent 都要多读几百行；
>   - 按 Markdown 语法定归属：只解决一半；
>   - 逐词对齐：太重，拆分时仍分不清。
>
>   用户：「那看一看有没有更好更优雅的做法呢？我只是问一嘴，如果没有的话，那就A就可以了」。
> - **没采纳**下面"在 settle.md 里补一句提醒"：根子修好了，就不需要提醒。settle.md 只把"拒收时把它点名的东西放回去"改成"照它说的做"，因为这次的拒收要的不是放回去。
> - 测试：`tests/test_doc.py` 两条，在旧代码上都失败。一条测插入的标题和段落成为两块；一条测改一块又加一段会被拒收，以及带空行的算法块照常能改。

- 来源：paper-read 实测（2026-11-02）。读论文的 subagent 精读 T-CACE（`xiaoTCACETimeConditionedAutoregressive2026`，Published-IEEE 的包）时顺手整理包，在回报里报出这个问题。没有用户原话。
- 状态：已修，见开头。

## 现场

subagent 按 `paddleocr/references/settle.md` §1 整理第 1 页：把 "1. INTRODUCTION" 改成 "I. INTRODUCTION"，新建了一个标题块；在标题和下面的段落之间放了一行 `<!-- fixed: … -->`，标题和段落之间没有空一行。

1. **并成一块**：`doc.py commit` 把新标题和下面的段落记成了同一个 `paragraph_title` 块。
2. **拆不开**：subagent 想把这一块拆回标题加段落，再 commit，输出是 "nothing to commit"。subagent 的判断：这一块的文字里含 `\n\n`，`content_of()` 对 `paragraph_title` 只去掉开头的 `#`，把整段原样返回，所以 commit 看不出有改动（`paddleocr/scripts/doc.py:964`）。这是 subagent 的推断，还没核对。
3. **绕过的办法**：先 commit 一次，把这一块删到只剩标题；再 commit 一次，把段落作为新块插进去。多花了两次 commit。

回报原文存在会话的临时目录里（T-CACE 的 `report.md`，*Package* 一节），会话结束后不保留，要点都抄在上面了。

## 为什么要紧

- settle.md 写着 "A paragraph of your own (blank lines around it) becomes a new block; a line added without a blank line joins the paragraph it touches"。照这句话，`fixed` 注释行只是没空行，就把标题和正文粘成了一块。这个后果 settle.md 没有提醒，整理的 agent 很容易踩到。
- 粘成一块以后，正常的编辑拆不开，只能靠删了再插这种绕法。下一个踩到的 agent 不一定想得到。

## 待查

- 先复现：在一个测试包里照第 1 步做一遍，确认是否真是 `content_of()` 的原因。
- 再定修法：是 commit 时把含空行的标题块拆开或拒绝，还是在 settle.md 里补一句提醒，按设计原则判断。
