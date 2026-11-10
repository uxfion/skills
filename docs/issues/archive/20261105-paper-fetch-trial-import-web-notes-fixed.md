# paper-fetch：全流程试用中，学校登录这条路上的几处现象（待下次真跑时核实）

> **已解决（2026-11-10）。** 10 条现象逐条有了结论，见「2026-11-10 下午：逐条判断」一节的表：核实后写进 publishers.md 的 3 条（Springer 机构列表里没有学校、后台窗口里输入和部分点击会失败、代理关联通常保持）；改了规则文字的 2 条（SKILL.md 交接表删掉"标签页停在那一页"，gate.md 写明切前台用标签页当前的地址）；核实后不用改的 2 条；判断不做的 3 条，各自的理由在表里。
>
> 没查的一件：切到前台后窗口有没有真的弹到最前面。用户 2026-11-10：「这个问题影响吗？我感觉不影响吧。我应该是自己切过去的，我不太记得了」。通知用户靠的是主 agent 的推送和对话里的说明，窗口弹不弹只差一次切换，不再查。
>
> 登录和人机验证本身在两次试跑里都没出现（代理和单点登录一直是通的）。以后真碰到关卡时出了问题，按现象另开 issue。

- 来源：2026-11-05 全流程试用。一个只看 skill 文档的导入 agent 在取 MICCAI 论文的 Springer 正式版时报告了这些。主 agent 只核实了能从文件里看到的部分，其余都是 agent 的说法，标了"未核实"。用户没有提。
- 状态：已解决。[MICCAI 来源页问题](20261105-paper-fetch-miccai-pages-fixed.md)于 2026-11-09 关闭时，仍需使用的原始资料事实已整理到本文件，见下方复核；登录现象的原因仍待真跑核实。

## 现象

1. **代理关联没有"粘住"**（handoff 1 和 4 核实了路线和结果，原因未核实）：第 1 遍里，doi.org 地址经 Zotero Connector 转到了学校的 EZproxy，落在 SSO 密码页；第 2 遍同一个地址没被代理，直接到了 Springer 章节页（"preview of subscription content"），PDF 被拒（handoff 5，`refused`）。publishers.md 说这种关联一旦建立就会一直保持，这次没有。
2. **Springer 的机构登录列表里没有用户的学校**（未核实）：agent 在 Springer 的 WAYF 页面搜了学校名，没搜到，只能走 EZproxy。值得作为带日期的提示写进 publishers.md，写的时候学校名换成占位符。
3. **后台窗口里点不了按钮**（未核实）：`opencli browser click` 返回 "Native input requires a visible browser page"。web-agent.md 让 agent "去点机构登录"，可后台窗口点不了，agent 只好直接打开那个链接的地址。
4. **批量会话的标签页没有停在门页**（未核实）：handoff 表说批量会话 `pf` 的标签页会停在那一页，实际上它接着去处理别的论文了。
5. **"不等的门"没有对应的答案**：agent 被要求遇到门不要等（这是试用 brief 的要求，不是 skill 的），只能答 `gate_timeout`，可这个词的意思是"等过了"。
6. **`got` 和尚未满足版本要求**（2026-11-09 已核实，符合现有语义）：结果要求 `wanted: published`，已有文件为 `Accepted-MICCAI`、`check: ok`，`outcome.status: got` 表示已有可用文件；`fetch` 仍寻找正式版。此项无需修复。
7. **arXiv 接口偶尔回 400**（未核实）：第一次 `identify` 时 arXiv 接口回 400，result 记成 `versions.incomplete`；同样的参数用 curl 手动请求是 200，重跑也正常。`identify` 那一行没写出 400 的原因。

## 2026-11-09 原始资料复核

- handoff 1、4 都标为 `pass: 1`、`route: publisher`、`code: no_pdf_link`，落点是 `<institution>` 的代理登录页，页面文字有 “Sign In”。handoff 5 标为 `pass: 2`、`route: publisher`、`code: refused`，落点是公开 Springer 章节页，页面有 “preview of subscription content” 和 “Access this chapter”。这支持第 1 项的前后落点记录，但不能确定代理关联为何变化。
- `fetch.jsonl` 记录了两次 paper agent 的 `gate_timeout` 回答，其理由都称本次试用要求不等待密码门。可核实的是 agent 留下了这种说法，不能据此推断实际等待了多久；第 5 项仍需按正式运行的要求判断。
- `result.json` 的版本要求、文件标签、文件检查和状态字段解释了第 6 项。第 2、3、4、7 项在这些资料中没有新增独立证据，保留原有“未核实”状态。

## 2026-11-09 取补充材料时又看到的关卡现象（未核实）

从补充材料那张 issue（[archive/20261109-paper-fetch-supplement-for-a-library-paper-fixed.md](20261109-paper-fetch-supplement-for-a-library-paper-fixed.md)）挪来，都是取 RSNA 补充材料的 subagent 的说法：

8. **切到前台会重新加载页面**：gate.md 第 1 步只给了 `open --window foreground`，它会重新加载；直接调 `windows.update` 被拒（`managed_resource_conflict`）。
9. **手工打开的页面超时后，提示对不上**：`pf.py wait` 超时的提示让去回答论文的 `page` handoff `gate_timeout`，还说是"登录页，重新看一眼"；可手工打开的页面没有 handoff，gate.md 又说人机验证不要重开。
10. **subagent 的关卡提醒到不了用户面前**：gate.md 默认 subagent 用 `SendMessage` 发的提醒会到用户面前，实际只排进主 agent 的下一轮。

## 2026-11-10 真跑一次的结果

用户在场，取库里三篇缺 PDF 的论文：两篇 SpringerLink 期刊（Eur Radiol 2025、IJCARS 2018）、一篇 JAMA Netw Open。两本 Springer 期刊学校都没订阅，全程没有出现密码页和人机验证，所以登录和关卡本身这次没测到。

- **第 1 条（代理关联没粘住）**：这次没出现，两篇都直接经代理打开。原因仍不明，没再现。
- **第 2 条（Springer 机构列表里没有用户的学校）**：核实了。两个 paper agent 各自搜过多种写法，都没有。已写进 publishers.md（带日期，学校名用占位符）。
- **第 3 条（后台窗口点不了按钮）**：更正。点击能用；不能用的是输入文字（`opencli browser type`）。已写进 publishers.md。
- **第 4、5、8、9、10 条**（标签页没停在门页、不等的门、切前台重载、超时提示、提醒到不了用户）：没碰到关卡，仍未核实。
- **第 7 条（arXiv 接口 400）**：这次三篇都没有 arXiv 版，没碰到。

这次新看到的问题另记在 [archive/20261110-paper-fetch-keeps-trying-where-the-page-says-no-fixed.md](20261110-paper-fetch-keeps-trying-where-the-page-says-no-fixed.md) 和 [archive/20261110-paper-fetch-trial-run-findings-fixed.md](20261110-paper-fetch-trial-run-findings-fixed.md)。

## 2026-11-10 下午：逐条判断，能核实的都核实了

用户：「要求你先读这个依据，有没有必要？或者说有哪些需要升级？有哪些是待商榷的？也不是一味地接纳。你根据我们的 design principle 来」。下面每条写依据和结论。

| # | 现象 | 依据 | 结论 |
|---|---|---|---|
| 1 | 代理关联没粘住 | 11-05 出现一次；10-31、11-10 都粘住了。走不走代理是 Zotero Connector 定的，skill 管不到 | 不改流程。publishers.md 里"一旦建立就一直保持"改成"通常保持"，附这次的日期 |
| 2 | Springer 机构列表里没有学校 | 上午两个 paper agent 各自搜过 | 已写进 publishers.md |
| 3 | 后台窗口点不了按钮 | 上午：点击成功、输入失败；下午另一个 paper agent：点击也失败了一次 | 两种都有，publishers.md 的提示照实改了 |
| 4 | 批量会话的标签页没停在门页 | 上午亲眼看到：JAMA 那篇留下页面交接后，`pf` 的标签页已经在 Springer 的页面上。脚本用同一个会话接着处理下一篇，停不住 | **SKILL.md 交接表里"the bulk run's tab stays on that page"这半句不对，要删。规则文字，等用户看过** |
| 5 | "不等的门"没有对应的答案 | 这个要求是 11-05 试用 brief 自己加的，skill 没有；正式流程里 agent 会等 | 不做 |
| 6 | `got` 和版本要求 | 11-09 已核实符合设计 | 不用改 |
| 7 | arXiv 接口偶尔回 400 | 出现一次，重跑正常；结果里已经记了哪个来源没答（`incomplete`），做法是过会儿再认一次 | 不做：不管是 400 还是别的，做法都一样，多记一个原因不改变任何行为 |
| 8 | 切到前台会重新加载页面 | 下午实测：在后台会话里打开一页、做记号，再用**同一个地址** `open --window foreground`，记号还在，没有重新加载；直接调 Chrome 的窗口方法被拒（`managed_resource_conflict`），和当时 subagent 说的一致。所以会重载的情况是：给 `open` 的地址和标签页当前所在的地址不一样（比如给了交接里的 doi.org 地址，而标签页已经跳到了验证页） | **gate.md 第 1 步的 `<url>` 写明是"标签页现在所在的地址"。规则文字，等用户看过。** 窗口有没有真的弹到前面，要用户在屏幕上看 |
| 9 | 手工打开的页面超时后，提示对不上 | 当时没有"给已有论文补一份文件"的流程，subagent 是手工打开页面的。现在流程写了，用 `fetch --start`，取不到时会自己开一个页面交接，提示就对得上 | 不做：原因已经没了 |
| 10 | subagent 的关卡提醒到不了用户面前 | 下午实测：subagent 用 `SendMessage` 发给主 agent，21 秒内到达，当时 subagent 还在干活、主 agent 也在干活。gate.md 现在写的就是"subagent 发给主 agent，主 agent 推送给用户" | 不用改 |

另外补做了上午漏掉的一步：JAMA 那篇当时在 Europe PMC 被拦后停在第一遍，主 agent 决定不跑第二遍，图书馆的发现系统就没查。下午补查，从发现记录里的 LibKey 下载按钮取到了 JAMA 排版的正式版，已挂上。做法写进了 publishers.md。

登录和人机验证本身今天仍然没有出现（代理和单点登录一直是通的），第 4、8 条之外没有别的要等关卡才能核实的了。
