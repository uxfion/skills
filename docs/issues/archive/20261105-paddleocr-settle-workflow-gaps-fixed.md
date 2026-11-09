# paddleocr：settle 流程里几处没写清的行为

已解决（2026-11-09 核对后关闭）：
- 第 1–3 条已由 Unix 改造解决，见 [paddleocr Unix 约定 spec](../../specs/20261106-paddleocr-unix-conventions-spec.md)：settle.md 写明修好的 finding 不用判、commit 后自己消失；`show` 改为只读，有没记的改动时 stderr 警告；`show -h` 和 settle.md 写明图片在 `$TMPDIR/paddleocr-show/`，由用了 `show` 的一方结束时删。当时留待以后定的 `show -o` 不做：位置和清理都已写明，之后没再出过问题。
- 第 4 条不改：合并后的结果本来就对，加一句说明，agent 并不会因此少犯错。
- 第 5 条不成立：`p2z.py package put` 上传新包后会把新包的 key 写回 `<stem>.zotero.json`（`paper-to-zotero/scripts/structured.py` 的 `put_one`，2026-10-28 起就是这样）。

- 来源：2026-11-05 全流程试用，三个读论文 agent 报告。最后一条主 agent 看过 `/tmp/paddleocr-show/` 核实了。用户没有提。
- 状态：fixed（2026-11-09）。

## 经过

1. **修好一处 finding 后，`<!-- open … -->` 那行怎么办，settle.md 没写清。** 两个 agent 做法相反：
   - FSCG 的 agent 把它换成 `<!-- fixed: … -->`，`doc.py commit` 又把 open 那行放了回来，最后只好手动判 `ok`；
   - SonoWorld 的 agent 把那行留着，commit 自己就清掉了。
2. **`doc.py show <finding id>` 会把还没 commit 的 Markdown 改动记进记录**（SonoWorld 的 agent 看到输出 "p7-2: … -> …, findings gone"）。`show` 听上去是只读的，文档里也没说它会记改动。
3. **`doc.py show` 把页面图片写到 `/tmp/paddleocr-show/<stem>-<hash>/`**，不在任务的 scratch 目录里，SKILL.md 和 settle.md 都没提，也没人清理。2026-11-05 主 agent 看到那里堆着 5 个文件夹，有这次三篇里的两篇，也有更早几次运行留下的（T-CACE、Harness2 等）。
4. **补公式编号会合并块**：写 `\tag*{(10)}` 以后，commit 把编号块并进了公式块（"p15-16: deleted, its text now in p15-15"）。结果没问题，但 settle.md 可以提一句。
5. **`package put` 以后，`<stem>.zotero.json` 里还是旧包的 key**（SonoWorld 的 agent 的说法，没核实）。这次 `put_note` 用不到它；以后有人往同一个文件夹再跑一次，会不会出问题不知道。这一条属于 paper-to-zotero 的 `package put`。

## 待看

- settle.md 写明修好以后 open 那行怎么处理，以 commit 的实际行为为准。
- `show` 要么不记改动，要么文档里写明它会记。
- 图片写到调用方给的 scratch 目录下，或者文档写明位置、由谁清理。
