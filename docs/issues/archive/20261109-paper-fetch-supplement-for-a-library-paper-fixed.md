# paper-fetch、paper-to-zotero：给库里已有的论文补一份补充材料，没有现成的流程

> **已解决（2026-11-10）。** 第二次（Nature）走通的做法写成了流程：paper-to-zotero 的 `references/import.md`，*One more file for a paper the library has*；paper-fetch 的 SKILL.md 补了 `--as supplement` 的用法，paper-read 的 *Additional sources* 指到这一节，publishers.md 加了 Nature、RSNA 补充材料和 Cloudflare 的带日期提示。补充材料的结构化包不在挂上时做，第一次读它时再做（用户 2026-11-10 同意）。
>
> **没做的，和原因：**
> - **`Supplement-Springer` 的建议不改代码。** 用 `--start` 直接给链接时，脚本手里只有文件的地址（`static-content.springer.com`），没有文章页，认不出是 Nature；标签本来就由 agent 在 label 这一步确认，所以写成 publishers.md 里的提示，不往脚本里加按网址猜的规则。
> - **附件文件名和正文相同**：存在不同文件夹里不冲突，附件标题能分清。
> - **关卡的 3 处**（下面第 4、5、6 条）：是所有关卡共有的，挪到 [20261105-paper-fetch-trial-import-web-notes.md](../20261105-paper-fetch-trial-import-web-notes.md) 等真跑时核实。
> - **Pseudo-CEUS 的 RSNA 补充材料还没取到**，卡在 Cloudflare 人机验证，等用户过；这是那篇论文的事，不是流程的缺口。

- 来源：2026-11-09 精读那一轮。Pseudo-CEUS（`chenPseudoContrastEnhanced2025`，Radiology: AI 2025，条目 VZ5ETN8K）的读论文的 subagent 有 5 问卡在 RSNA 的补充材料上（Appendix S1–S5、Figure S1–S2、Table S1），按 paper-read 的 *Additional sources*，由主 agent 经 paper-fetch 取来。主 agent 派了一个 subagent 照两个 skill 去取，下面是它的回报。用户没有提。
- 状态：已解决。原记：这次没取到：RSNA 的文章页挡着 Cloudflare 人机验证，等用户。接着做的步骤在运行记录里（参考资料 `../20261109-paper-read-reading-for-project-insight-reference/run-log.md`，git 不跟踪）。

## 文档没说怎么做的地方（subagent 逐条报的，括号里是它的做法）

1. 两个 SKILL.md 都没有"给已有条目加补充材料"的流程。import.md 第 3 步说"从提供它的那一步接着做"，但没有哪一步提供补充材料。（先 `pf.py identify`，再 `p2z.py draft`、`prepare` 拿到 `found.key`；打算不走 `save`，直接 `p2z.py attach`，因为不用新建条目。它读了代码：`attach` 只在结果没有 `outcome` 时才以 `library_has_pdf` 跳过，所以取到的补充材料应该能挂上。）
2. `fetch --start`、`claim`、`answer` 都有 `--as supplement`，但没有文档讲怎么用。`fetch` 会取页面声明的 PDF，那是正文，补充材料的链接只能手工找。（打算手工找到链接，交给 `--start … --as supplement`。）
3. publishers.md 没有 RSNA 的条目：没写它的 Turnstile 验证，也没写补充材料的链接在哪。"Cloudflare 检查一般 10–15 秒自己过"这条，在 RSNA（这次）和 OpenReview（同日导入 SDEdit 正式版时）都不成立，前台后台都过不去。（当关卡处理。）
4. gate.md 第 1 步"拿到前台"只给了 `open --window foreground`，会重新加载页面；直接调 `windows.update` 被拒（`managed_resource_conflict`）。（只重新加载了一次。）
5. `pf.py wait` 超时的提示让去回答论文的 `page` handoff `gate_timeout`，还说这是"登录页，重新看一眼"；可手工打开的页面没有 handoff，gate.md 又说人机验证不要重开。（没重开，把关卡写进记录的 `blocker`。）
6. gate.md 默认 subagent 用 `SendMessage` 发的提醒会到用户面前；实际上它只排进主 agent 的下一轮。（在回报第一行再说一遍，请主 agent 发推送提醒。）
7. 补充材料 PDF 要不要做结构化包，文档没说。

## 待看

- 设计一条"给已有论文补一份文件（补充材料、另一个版本）"的流程，写进 import.md 或 organize.md：怎么找到文件、怎么取、怎么挂、要不要解析。同日的另一张 issue（补版本时 `create` 先要分类）是同一类问题，已先修好：[archive/20261109-paper-to-zotero-create-asks-collection-before-exists-fixed.md](20261109-paper-to-zotero-create-asks-collection-before-exists-fixed.md)。
- publishers.md 补 RSNA，改 Cloudflare 那条说法（加日期）。
- gate.md：subagent 的关卡提醒怎么及时到用户面前。

## 第二次：ALADYNOULLI 的 Nature 补充材料（同日，取到了）

照第一次摸出的做法走通了，没有碰上验证：`pf.py identify` → `p2z.py draft`、`prepare`（按 DOI 找到已有条目）→ `pf.py fetch --start <补充材料链接> --as supplement` → 回答 label handoff → `p2z.py attach`（不走 `save`），挂成 Supplement-Nature（8JD7ZLN6，48 页）。又看到三处：

- 补充材料的链接在 nature.com 文章页的 Supplementary information 一节，文件放在 `static-content.springer.com/esm/…`。publishers.md 只在 SpringerLink 下提到 `/esm/`。
- 脚本建议的标签是 `Supplement-Springer`：titles.py 把 `springer.com` 认成 Springer。按 attachment-titles.md 的例子应是 `Supplement-Nature`，subagent 手工改了。以后 Nature 的补充材料都会被这样建议，`static-content.springer.com` 要按文章所在的网站认。
- `attach` 用 Zotero 的默认文件名，和正文 PDF 同名（存在不同的文件夹里，不冲突，但按文件名列出来分不清）。
