# paddleocr：按交接标准改它的几处交接

> 已改（2026-11-04），和 vllm-serve 那张一起。暂缓是用户 11-02 定的（下面"状态"），今天用户解除：「那我觉得完全可以按交接标准改好，然后一起去提交推送啊」。逐条按设计原则和用户定过的规矩处理，没有新的决定要用户定（用户：「你这些决策我觉得不应该让我一条一条看吧，你根据我们定下的 design principle 过一遍就好了」）：
> - **1（PO-4）采纳**：
>   - SKILL.md 派整理 subagent 时写上两边的模型（Claude Code `sonnet`，Codex `luna`）；
>   - 派发清单补上"任务要用、但没有发现标出的图，按页码和图注"；
>   - settle.md 写明在包文件夹里只改 `<stem>.md`、记录和图片由 `doc.py` 写，自己做、不派 subagent、不碰 git。没写成"只能写这个文件夹"，因为 paper-read 读论文的 subagent 也照 settle.md 整理包，它还要写笔记文件；
>   - "做不完时说试过什么、定了什么、还缺什么"并进回报的 **open** 一行；"the agent that sent you" 改成 main agent。
> - **2（PO-3）采纳**：install.md 改成告诉用户、直接装（uv 工具）。依据是用户 2026-10-09 的规矩：「Python工具因为使用的是UV，你可以随便调用或者下载」。poppler 是系统软件，照旧要用户批准。
> - **3（PO-6）采纳**：回报后 `doc.py show` 还列着没处理的问题，就把输出原样发回同一个 subagent；接不上时另派一个，带上同一份 brief、文件夹现状、这份输出和上一位的回报。写法照 paper-read。
> - **4（PO-7）不用改**：论文笔记 issue 已定 46 定了，paper-read 已实现，paddleocr SKILL.md 现在的写法和它相符。
> - **5（PO-8）采纳，换了走法**：别的项目里装的 skill 是从 GitHub 装的副本，在那里改 `conventions.py` 会和仓库分叉，重装时也会被覆盖。现在由整理的 subagent 在回报里写出图注写法并附例子，主 agent 在汇报里转告用户，再到本仓库开 issue。这是用户说过的路子（[20261103-paper-read-flows-not-run.md](../20261103-paper-read-flows-not-run.md)：「我会让项目中的 Agent 开张issue到这边来的」）。papers.md 那句相应改了。
> - **6 整体对一遍**：brief 分两处（SKILL.md 的派发说明、settle.md）、产物和完成条件（settle.md 每节都有）、固定规矩、两边的模型、角色名，现在都齐了。
>   - 没加交接索引表：paddleocr 只有一种 subagent，每个停点在所在步骤里已经写明谁接手，加一张表只是第二份副本。这一条也不在本 issue 的清单里。

- 来源 · 日期：2026-11-01，交接标准的审查（issue `archive/20261101-skills-handoff-standard-fixed.md`，spec `docs/specs/20261101-skills-handoff-standard-spec.md`）。用户把那次的范围定为只改 paper-fetch 和 paper-to-zotero（「A」），其余 skill 记下来以后改：「其他 skills 里面相关的，你要记个todo或issue，到时候去优化」。
- 条目编号（PO-1 到 PO-9）指文末附的审查条目原文。paddleocr 的 settle brief 是审查里最好的样板（PO-4）：brief 本身是一个文件，按路径交给 subagent，subagent 是那个文件夹唯一的写入者，用 `doc.py commit` 记下，每一节有完成条件，回报分五部分。交接标准的"brief 按读者拆成两半"就是照它来的。
- 状态：已改，见开头。原来：open。等交接标准在 paper-fetch、paper-to-zotero 落地、spec 定稿后再改；由维护 paddleocr 的会话来做。
  - 2026-11-02：交接标准已落地（d9bb12f），这张却暂缓。用户：「因为 vLLM serve 和 PaddleOCR 这些是外部的，如果能用的话，且不阻塞我们当前的进程，我可以暂缓」。等它碰到问题，或者挡住别的工作时再做。第 4 条（结构化包谁来整理）不等，随论文笔记那张 issue 的 paper-read 设计一起定。

## 要改的

1. **settle brief 的小缺口（PO-4）**：没写 Codex 用什么模型（paper-fetch、vllm-serve 写了 `luna`）；settle.md:5 说派发时"也可以点名要处理的图"，SKILL.md:51–54 列派发要给什么时漏了这一项；没有"只派一层、不碰 git"。
2. **安装要不要等用户点头（PO-3，和 vllm-serve 的 VS-5 相反）**：paddleocr 的 install.md:12 说先等用户同意，vllm-serve 说直接装。用户的规矩是用 uv 装的 Python 包不用批准，支持 vllm-serve 那边。两张 issue 一起统一。
3. **回报之后还有没处理的问题（PO-6）**：subagent 回报后，`doc.py show` 仍列出没处理的问题时，主 agent 该退回同一个 subagent，还是自己处理，没写。
4. **结构化包谁来整理（PO-7）**：paper-read 的 *Look it up* 会整理（经 paddleocr 第 2、3 步），而通读一篇的 *Read a paper* 不整理；p2z SKILL.md:63 要求"有了确定的结论就 `structured put`"，*Read a paper* 没提。和 paper-read 的设计一起定（paper-notes issue）。
   - 2026-11-02 定了（论文笔记 issue 已定 46）：整篇精读时，由读论文的 subagent 顺手整理，照 paddleocr 的 `references/settle.md`、用 `doc.py commit` 记下，主 agent 再 `structured put`。spec `docs/specs/20261102-paper-read-notes-spec.md` §3.3、§7。paddleocr 这边要不要改，等实施 paper-read 时看。
5. **改 `conventions.py` 归谁定（PO-8）**：那是改 skill 的代码，按仓库规矩要用户定；"在回报里说"到了主 agent 那里，没有一步把它转给用户。
6. **整体对一遍标准**：
   - brief 按读者拆成两半；
   - 必写产物和完成条件；
   - 每份 brief 都带那一小段规矩；
   - Claude Code 和 Codex 的模型都写上；
   - 角色写明是主 agent、subagent 还是用户。

## 附：审查条目原文

2026-11-01 交接标准审查（只读）时记下的条目，原样搬自那张 issue 的参考资料 `audit.md`（关闭时删除）。行号指当时的文件；评判的依据是当时的 `docs/design-principles.md`。图例：

- **Dir**: S→A script to agent · A→S agent to script · M→Sub main agent to subagent · Sub→M subagent to main · A→U agent to user · U→A / U→S user to agent / to script.
- **Stated** column, what the text says about: **T** taker (model, how many) · **G** goal · **I** inputs (paths, evidence, read-first) · **R** requirements and limits · **P** product (answers allowed, files, format, location) and how it is recorded · **↻** what resumes · **D** done-when · **U** what happens when the taker cannot settle it · **B** what it reports back. `—` = not stated.
- **Gaps**: what is missing, unclear, scattered, or contradicted (between files or by the code), each with the lines it rests on.
- File references without a skill prefix are relative to that skill's directory.

| ID | Where · Dir · trigger | Stated | Gaps (cited) |
|---|---|---|---|
| PO-1 | SKILL.md:10, :22–24, :38–43; parse.py --help · S→A, A→U · parse summary / errors / native fallback | P errors → install.md; `skipped`/`rendered`/`edits_carried`/`archived`; native reason → tell the user in a batch, and that vllm-serve would be 10–20× faster. D SKILL.md:38. | Good. |
| PO-2 | SKILL.md:26–30; parse.py:203–242 · S→A, A→U · VL server holds the call | P judge as vllm-serve's SKILL says; `serve.py down paddleocr-vl` when stuck; `port_busy` → `--vl-server` if it is PaddleOCR-VL, else tell the user. | Verified: serve.py's stderr passes through (parse.py:206 pipes only stdout) and errors print as `[paddleocr] vllm-serve <code>: <detail>` (parse.py:234–238). Consistent. |
| PO-3 | references/install.md:12, :38 · A→U · install, poppler | P multi-GB install: wait for the go-ahead; poppler: the user installs or approves. | See VS-5 contradiction. |
| PO-4 | SKILL.md:45–62; references/settle.md:1–117 · M→Sub · a parse with open findings | T one subagent per document, a smaller model that can view images (CC `sonnet`), ≤5 unless the user sets another limit, sole writer of its folder (SKILL.md:49, :56). G settle every finding, read weak spots (settle.md:3). I absolute path of settle.md, folder, source, papers.md for a paper (SKILL.md:51–54). R record left to `doc.py`; marker lines untouched (settle.md:35); trust text layer for characters, image for layout. P edits + `doc.py commit`, verdicts `ok`/`unresolved`, `doc.py figure` (settle.md:31–39). D per section (settle.md:65, :89, :107). U `unresolved`; "open" in the report. B five parts, one line per item (settle.md:111–117). | **Model brief** (a reference file that is the brief, passed by path). Small gaps: Codex model unnamed (paper-fetch and vllm-serve name `luna`); settle.md:5 says the prompt "may also name figures to settle", which SKILL.md:51–54's list of what to give omits; no "one level deep" / no-git line. |
| PO-5 | settle.md:31–39; doc.py --help · Sub→S · recording | P `doc.py commit`, refusals on stderr ("put back what it names"). | Good. |
| PO-6 | SKILL.md:62 · Sub→M · report back | D main's own: report back and `doc.py show` prints `no open findings`. | **Missing**: what the main does when `show` still lists open findings after the report (send back to the same subagent? settle itself?). |
| PO-7 | SKILL.md:59; p2z import.md:109; paper-read SKILL.md:36, :43–45 · deferred A→A · a batch parsed for later use | P "settled when a task first reads it". | **Scattered**: paper-read's Look it up settles (via paddleocr steps 2–3), but paper-read's Read a paper (the most thorough first read) does not; p2z SKILL.md:63 asks for `structured put` after "a settled finding", which Read a paper never mentions. |
| PO-8 | references/papers.md:36 · Sub→M→U · a caption style the conventions miss | P say so in the report with an example caption; pattern into `scripts/conventions.py`, then `doc.py render`. | Who changes `conventions.py` (a skill code change, the user's decision per the repo's rules) is not said; "say so in your report" reaches the main, which has no step to carry it to the user. Minor. |
| PO-9 | SKILL.md:82–87 · A→caller/U · report | P paths, `min_coverage`, settle report, what came from figure images. | Good. |
