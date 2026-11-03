# paddleocr：`doc.py commit` 把标题和下面的段落并成一块，事后拆不开

- 来源：paper-read 实测（2026-11-02）。读论文的 subagent 精读 T-CACE（`xiaoTCACETimeConditionedAutoregressive2026`，Published-IEEE 的包）时顺手整理包，在回报里报出这个问题。没有用户原话。
- 状态：open。

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
