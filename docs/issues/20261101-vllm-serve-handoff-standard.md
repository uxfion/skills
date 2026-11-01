# vllm-serve：按交接标准改它的几处交接

- 来源 · 日期：2026-11-01，交接标准的审查（issue `20261101-skills-handoff-standard.md`，spec `docs/specs/20261101-skills-handoff-standard-spec.md`）。用户把那次的范围定为只改 paper-fetch 和 paper-to-zotero（「A」），其余 skill 记下来以后改：「其他 skills 里面相关的，你要记个todo或issue，到时候去优化」。
- 条目编号指那张 issue 参考资料文件夹里的 `audit.md`（VS-1 到 VS-10）。整体上 vllm-serve 写得好：脚本的每种输出都写明了对应的动作，要用户定的事也都标了（VS-2、VS-9）。
- 状态：open。等交接标准在 paper-fetch、paper-to-zotero 落地、spec 定稿后再改，因为标准本身可能还会调整；由维护 vllm-serve 的会话来做。

## 要改的

1. **读长日志的 subagent（VS-3）**：缺完成条件、写入范围、"只派一层"，也没说找不到出错的那一行时交回什么；"长日志"多长算长没写。按标准：主 agent 的一半写明用哪个模型、交回什么；subagent 的一半写明产物、完成条件和那一小段固定规矩。
2. **安装要不要等用户点头（VS-5）**：vllm-serve 的 install.md:11 说直接装，paddleocr 的 install.md:12 说先等用户同意，两边都是几个 GB 的 uv 工具安装。用户的规矩是用 uv 装的 Python 包不用批准、非 Python 的要批准，支持 vllm-serve 这边。和 paddleocr 那张 issue 一起统一。
3. **整体对一遍标准**：
   - brief 按读者拆成两半；
   - 必写产物和完成条件；
   - 每份 brief 都带那一小段规矩；
   - Claude Code 和 Codex 的模型都写上；
   - 角色写明是主 agent、subagent 还是用户。
