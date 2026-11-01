# paddleocr：按交接标准改它的几处交接

- 来源 · 日期：2026-11-01，交接标准的审查（issue `20261101-skills-handoff-standard.md`，spec `docs/specs/20261101-skills-handoff-standard-spec.md`）。用户把那次的范围定为只改 paper-fetch 和 paper-to-zotero（「A」），其余 skill 记下来以后改：「其他 skills 里面相关的，你要记个todo或issue，到时候去优化」。
- 条目编号指那张 issue 参考资料文件夹里的 `audit.md`（PO-1 到 PO-9）。paddleocr 的 settle brief 是审查里最好的样板（PO-4）：brief 本身是一个文件，按路径交给 subagent，subagent 是那个文件夹唯一的写入者，用 `doc.py commit` 记下，每一节有完成条件，回报分五部分。交接标准的"brief 按读者拆成两半"就是照它来的。
- 状态：open。等交接标准在 paper-fetch、paper-to-zotero 落地、spec 定稿后再改；由维护 paddleocr 的会话来做。

## 要改的

1. **settle brief 的小缺口（PO-4）**：没写 Codex 用什么模型（paper-fetch、vllm-serve 写了 `luna`）；settle.md:5 说派发时"也可以点名要处理的图"，SKILL.md:51–54 列派发要给什么时漏了这一项；没有"只派一层、不碰 git"。
2. **安装要不要等用户点头（PO-3，和 vllm-serve 的 VS-5 相反）**：paddleocr 的 install.md:12 说先等用户同意，vllm-serve 说直接装。用户的规矩是用 uv 装的 Python 包不用批准，支持 vllm-serve 那边。两张 issue 一起统一。
3. **回报之后还有没处理的问题（PO-6）**：subagent 回报后，`doc.py show` 仍列出没处理的问题时，主 agent 该退回同一个 subagent，还是自己处理，没写。
4. **结构化包谁来整理（PO-7）**：paper-read 的 *Look it up* 会整理（经 paddleocr 第 2、3 步），而通读一篇的 *Read a paper* 不整理；p2z SKILL.md:63 要求"有了确定的结论就 `structured put`"，*Read a paper* 没提。和 paper-read 的设计一起定（paper-notes issue）。
5. **改 `conventions.py` 归谁定（PO-8）**：那是改 skill 的代码，按仓库规矩要用户定；"在回报里说"到了主 agent 那里，没有一步把它转给用户。
6. **整体对一遍标准**：
   - brief 按读者拆成两半；
   - 必写产物和完成条件；
   - 每份 brief 都带那一小段规矩；
   - Claude Code 和 Codex 的模型都写上；
   - 角色写明是主 agent、subagent 还是用户。
