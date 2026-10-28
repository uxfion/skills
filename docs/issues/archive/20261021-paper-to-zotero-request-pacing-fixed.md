# paper-to-zotero：派出去的 agent 没有访问节奏的约束，循环访问会让用户被网站封

> 已解决（2026-10-27）：并入 [附件命名 spec](../../specs/20261021-paper-to-zotero-attachment-naming-spec.md) §6，实现于 `6e1ae65`，2026-10-27 推送并从 GitHub 重装。SKILL.md 的 Rules 下新增 *Agents you send*，"要做的"四条都写进去了：
> - 不对网站写循环，`Browser: yes` 的 OpenCLI adapter 不放进循环；
> - 同一网站同一时间只有一个 agent，请求之间隔几秒；不同网站可以并行，最多 10 个；
> - 碰到第一个机器人验证、403、429 或 Cloudflare 页，这一轮就不再碰这个网站；
> - 不再派下级 agent。
>
> 第 3 步的浏览器 agent，以及定标签、改名时派去核对的 agent，说明里都带这四条；只读本地文件的 agent 不受限。Unpaywall 邮箱那条不用处理：p2z 不直接调 Unpaywall，它的仓储副本经 OpenAlex 拿到。

- 来源：2026-10-21，调研附件版本时（[20261020-paper-to-zotero-pdf-version-by-title-fixed.md](20261020-paper-to-zotero-pdf-version-by-title-fixed.md)），后台同时跑了 10 个 agent。
- 状态：fixed

## 现场

- 查版本升级的 agent 写了一个 shell 循环，对库里 104 个预印本标题逐个调用 `opencli dblp search`，每次只隔 1 秒。
  - 这个 adapter 是 `Browser: yes`，会在用户自己的 Chrome 里打开 dblp.org。
  - 约 90 秒里打开了 33 次，用户看到 Chrome 一直在重复打开页面，叫停后我停掉了这个 agent。
  - 它同时还用脚本批量扫了 arXiv API、Semantic Scholar、OpenAlex、PubMed；这几个按 API 的分批限额走，节奏尚可。
- ACM/Wiley 那个探查 agent 循环访问了 10 个 Wiley 期刊页面，每次隔 9 秒；遇到 Cloudflare 403 以后还在继续用 ACM 和 Wiley。这是它自己报告的。
- 查开放网站的 agent 自己又派了几个下级 agent，其中一个反复对一个页面执行 `eval` 轮询。
- 我给这些 agent 的说明里都没有节奏要求，也没有禁止它们再派下级 agent。
- 查开放网站的 agent 事后交代：
  - 它派了 3 个 sonnet 下级 agent，分别查 CVF/ECVA/MICCAI、论文集加机构库、PMC/Europe PMC。
  - 查 PMC 的那个多次用 curl 访问以后，PMC 弹出了 reCAPTCHA。这说明已经被网站盯上过一次。
  - 它自己在规则下达前跑过几个小循环：
    - 10 份 arXiv PDF，每份隔 4 秒；
    - 两轮各 6 个 DOI，请求 Zotero 的 Unpaywall 镜像和 OpenAlex，每次隔 1 秒；
    - 5 个 OpenReview 页面，每次隔 3 秒。
- 写进说明里的邮箱 `unpaywall@example.com` 被 Unpaywall 拒绝（HTTP 422）。给 API 的联系邮箱要用真实的，或者不用这个 API。

用户原话：
- 「为什么一个subagent在重复打开」「循环」「https://dblp.org/ 的」
- 「你这种循环千万要注意小心，会被直接拉黑」
- 「这个排查一下问题，下次别再犯了，很危险，即使有头浏览器，也遭不住你这么折腾，会被封的」
- 用户认可的一条旁注：并行 agent 都用同一个网络和学校登录，网站按总量限流；派任务时要写明不准再派下级 agent，同一网站同一时间只让一个 agent 访问，而且要放慢。

## 为什么和 p2z 有关

- p2z 自己的流程也在派 agent：第 3 步每个停下来的页面派一个浏览器 agent。
- 正在设计的版本核对，打算让最多 10 个 sonnet agent 并行。
- `references/publishers.md` 第 61 行写着"并行的 subagent 共享这些限额"，但派 agent 的说明里没有节奏规则，也没禁止下级 agent，更没规定按网站分工。

## 要做的（待批量处理）

- 在 SKILL.md 给浏览器 agent 的说明，以及以后版本核对的 agent 说明里，写进这几条：
  - 不对网站写循环；
  - 同一网站同一时间只有一个 agent，放慢访问；
  - 遇到第一个机器人验证、403、429 就停下，不再碰这个网站；
  - 不准再派下级 agent。
- 并行的上限按网站来分：不同网站可以并行，同一网站只能串行。
- 用 `Browser: yes` 的 OpenCLI adapter 之前先看它的 `--help`，这类 adapter 不能放进循环。
