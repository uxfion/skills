# paper-fetch：全流程试用中，学校登录这条路上的几处现象（待下次真跑时核实）

- 来源：2026-11-05 全流程试用。一个只看 skill 文档的导入 agent 在取 MICCAI 论文的 Springer 正式版时报告了这些。主 agent 只核实了能从文件里看到的部分，其余都是 agent 的说法，标了"未核实"。用户没有提。
- 状态：open。证据见 [20261105-paper-fetch-miccai-pages.md](20261105-paper-fetch-miccai-pages.md) 的参考资料文件夹（handoff 1、4、5，`fetch.jsonl`）。

## 现象

1. **代理关联没有"粘住"**（handoff 1 和 4 核实了路线和结果，原因未核实）：第 1 遍里，doi.org 地址经 Zotero Connector 转到了学校的 EZproxy，落在 SSO 密码页；第 2 遍同一个地址没被代理，直接到了 Springer 章节页（"preview of subscription content"），PDF 被拒（handoff 5，`refused`）。publishers.md 说这种关联一旦建立就会一直保持，这次没有。
2. **Springer 的机构登录列表里没有用户的学校**（未核实）：agent 在 Springer 的 WAYF 页面搜了学校名，没搜到，只能走 EZproxy。值得作为带日期的提示写进 publishers.md，写的时候学校名换成占位符。
3. **后台窗口里点不了按钮**（未核实）：`opencli browser click` 返回 "Native input requires a visible browser page"。web-agent.md 让 agent "去点机构登录"，可后台窗口点不了，agent 只好直接打开那个链接的地址。
4. **批量会话的标签页没有停在门页**（未核实）：handoff 表说批量会话 `pf` 的标签页会停在那一页，实际上它接着去处理别的论文了。
5. **"不等的门"没有对应的答案**：agent 被要求遇到门不要等（这是试用 brief 的要求，不是 skill 的），只能答 `gate_timeout`，可这个词的意思是"等过了"。
6. **settle 和 fetch 说法不一**（未核实）：同一篇，`settle` 显示 `status: got`，`fetch` 却说 unsatisfied。可能是因为挂上去的是接受版，正式版还没拿到。
7. **arXiv 接口偶尔回 400**（未核实）：第一次 `identify` 时 arXiv 接口回 400，result 记成 `versions.incomplete`；同样的参数用 curl 手动请求是 200，重跑也正常。`identify` 那一行没写出 400 的原因。

## 下一步

下次真跑一篇要走学校登录的论文时，逐条对照，核实了的拆成各自的 issue，或者并进 paper-fetch Unix 改造的 spec。
