# vllm-serve：按交接标准改它的几处交接

> 已改（2026-11-04），和 paddleocr 那张一起（[20261101-paddleocr-handoff-standard-fixed.md](20261101-paddleocr-handoff-standard-fixed.md)）。暂缓是用户 11-02 定的（下面"状态"），今天用户解除：「那我觉得完全可以按交接标准改好，然后一起去提交推送啊」。逐条按设计原则和用户定过的规矩处理：
> - **1（VS-3）采纳**：SKILL.md 的 `server_failed` 一条后面加了一段派发文字，作为读日志 subagent 的 brief，写明：
>   - 交回什么：原样的出错行和 install.md 里对上的条目；对不上写"no entry"；一行原因都找不出，写"no cause"并附日志末尾 30 行；
>   - 完成条件：日志里每个报错都在回复里有交代；
>   - 规矩：不写文件，不派 subagent，不碰 git；读不了日志就说试过什么。
>
>   没另建 brief 文件：只有一个只读的角色、几行字，交接标准本来就允许"写成段落"。也没写进 install.md 那一节，因为那一节是主 agent 和用户自己排查时读的。
>   - "长日志"多长算长，不规定：按设计原则 §4"只约束必须成立的事"，由主 agent 判断。
> - **2（VS-5）不用改**：vllm-serve 现在的写法（告诉用户、直接装）就是用户的规矩；paddleocr 那边改成了一样的。
> - **3 整体对一遍**：两边的模型、角色名早已写明；VS-10（"client"指谁）当时审查就判过"可以接受"，不改。
>   - 没加交接索引表：*When `up` says more* 已经按输出逐条写了怎么做（审查评为范例），加一张表只是第二份副本。

- 来源 · 日期：2026-11-01，交接标准的审查（issue `archive/20261101-skills-handoff-standard-fixed.md`，spec `docs/specs/20261101-skills-handoff-standard-spec.md`）。用户把那次的范围定为只改 paper-fetch 和 paper-to-zotero（「A」），其余 skill 记下来以后改：「其他 skills 里面相关的，你要记个todo或issue，到时候去优化」。
- 条目编号（VS-1 到 VS-10）指文末附的审查条目原文。整体上 vllm-serve 写得好：脚本的每种输出都写明了对应的动作，要用户定的事也都标了（VS-2、VS-9）。
- 状态：已改，见开头。原来：open。等交接标准在 paper-fetch、paper-to-zotero 落地、spec 定稿后再改，因为标准本身可能还会调整；由维护 vllm-serve 的会话来做。
  - 2026-11-02：交接标准已落地（d9bb12f），这张却暂缓。用户：「因为 vLLM serve 和 PaddleOCR 这些是外部的，如果能用的话，且不阻塞我们当前的进程，我可以暂缓」。等它碰到问题，或者挡住别的工作时再做。

## 要改的

1. **读长日志的 subagent（VS-3）**：缺完成条件、写入范围、"只派一层"，也没说找不到出错的那一行时交回什么；"长日志"多长算长没写。按标准：主 agent 的一半写明用哪个模型、交回什么；subagent 的一半写明产物、完成条件和那一小段固定规矩。
2. **安装要不要等用户点头（VS-5）**：vllm-serve 的 install.md:11 说直接装，paddleocr 的 install.md:12 说先等用户同意，两边都是几个 GB 的 uv 工具安装。用户的规矩是用 uv 装的 Python 包不用批准、非 Python 的要批准，支持 vllm-serve 这边。和 paddleocr 那张 issue 一起统一。
3. **整体对一遍标准**：
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
| VS-1 | SKILL.md:12–21; serve.py --help · A→S, S→S · a caller needs a server (an agent, or paddleocr's parse.py) | P `up <profile> [-- args]` → `{profile, url, model, started}`; per-start vs profile settings (SKILL.md:21). | Good. |
| VS-2 | SKILL.md:23–39; serve.py --help · S→A · `host`, `differs`, `foreign_cuda`, errors | P each field/code → action; `foreign_cuda` → "report it to the user and fix it per install.md". | **Model** of script→agent: every output named, each with its action and the user's calls marked. |
| VS-3 | SKILL.md:30–31; references/install.md:97–110; serve.py:702 (log line names the guide) · S→A→Sub→M→U · `server_failed`, "the last start … failed" | T background subagent, CC `sonnet`, Codex `luna`. I log path (or the ssh command), install.md's section by name. P "the lines that give the cause and the entry they match, if any". Main acts on the entry, then `up`; no entry → work from the cause lines, tell the user cause and fix as a dated hint. | **Missing**: done-when, write containment, "one level deep", what to return when no cause line is found; "a long log" has no threshold. |
| VS-4 | SKILL.md:32–37; install.md:105 · S→A→U · `port_busy`, `not_permitted`, GPU memory held | P stopping a server someone uses / started by hand is the user's call; root's file → user `chown`; others' jobs come first → other GPUs or tell the user and wait. | Good. |
| VS-5 | install.md:11 · A→U · installing vLLM | P "tell the user, and go ahead (it is a uv package)". | **Contradiction across skills** on the same kind of handoff: paddleocr/references/install.md:12 "say so to the user and wait for their go-ahead" for its multi-GB uv tool install. |
| VS-6 | SKILL.md:41 · S→A · `up` in the background not returned | P status phase, log, nvidia-smi; stuck rule; `down`; handle `server_failed`. | Good. |
| VS-7 | SKILL.md:50 · U→A · GPUs wanted back | P `down` after `status` shows idle. | Good. |
| VS-8 | SKILL.md:52–58 · A · add a model | P recipe, profile, one real request. D SKILL.md:56. | No handoff. |
| VS-9 | references/shared-machines.md:5–59 · A↔U · a shared/remote machine | P agree the root with the user (:7); root steps → user as exact commands, check after (:25); share a lightly used GPU only with the user's agreement, ask when unsure (:31); API key: the user decides (:52); idle policy: the user chooses (:54); clearing the root: the user, or you on their word (:59). D :20. | Good: every user decision named. |
| VS-10 | shared-machines.md:54 · client→S · remote client after idle stop | P `up` over ssh "run by the client or by you". | Who "the client" is (another agent? a script?) is left open; acceptable. |
