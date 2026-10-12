# paper-to-zotero — 设计 spec v3（2026-10-12 定稿，实现中：第一轮已完成）

> 前身 `20260923-paper-to-zotero-v2-spec.md`（v2）在 v3 实现完成后加一行 `Superseded by`。v2 的记录与流约定（§3）、脚本通用约定（§4.2）、测试方式（§4.3）继续有效，本 spec 只写**改什么、为什么改**。来源是两份 issue 的统一分诊：`docs/issues/20261009-paper-to-zotero-batch-import.md`（下称 B#，37 条）与 `docs/issues/20260923-paper-to-zotero-v2-first-use.md`（下称 F#，17 条）；每条的去向见 §9。仓库公开：不写学校、代理域名、个人路径；本地事实只进 §6 的配置文件。

## 1. 为什么要 v3：证据

v2 在 2026-10-09/10 被用在一个研究项目上：166 篇 + 235 篇两批入库，另有约 35 篇出版社全文的批量补取，用户在线协助了一部分。脚本链本身扛住了，但 54 条问题里的大头追到下面五个根因：

| 痛点 | 根因 |
|---|---|
| 两批共约 90 篇报 `title_not_found`，全靠读第 1 页人工接收（B#1，F#13）；错文件（勘误、另一篇论文、"Host Needed" 快照）反而照样挂上（B#13 B#32 B#37） | **R1 身份核对又严又松**：自带抽取器不处理字体编码映射，连字、小型大写、部分 ACL/arXiv 字体出乱码；规则是"整条标题作为子串出现"，全有或全无；核对是 agent 记得跑的一步，不是写库前的条件 |
| 用户前半段在、后半段不在，后半段的门禁没人处理（B#21）；用户正在登录的标签页被脚本切走（B#26）；用户替 agent 点了下载，agent 仍在门禁上空等（B#34）；同一篇下载两遍、Downloads 越积越多（B#7 B#27） | **R2 取全文按论文顺序组织，下载检测绑在 agent 自己的点击上**：流程没有按"谁能完成这一步"分段；浏览器只有一个，却没有"谁在用"的规则 |
| 等一个永远过不去的页面（代理 "Host Needed"、会前 403、站点封禁），或把它当"没有 PDF 链接"立刻换路线、顶掉用户的登录页（B#22 B#23 B#26 B#35）；加了新办法后把所有失败整体重跑（B#36） | **R3 门禁只有一类，失败不分类**：用户能过的和谁都过不去的混在一起；不记试过什么，也不区分"这条路线不行"和"这篇在这个站点就是取不到" |
| arXiv 草稿改成会议 / 期刊正式版全靠手工逐篇查（B#4 B#19 B#24）；建完条目才发现版本不对，citation key 停在旧值（B#31） | **R4 正式版与会议出处没有可脚本化的来源**，而且版本在建条目之后才定 |
| 每篇要补跑 `file_and_tag`、按附件标题分组多次调用、记录状态被读回混淆、重复条目进库（B#2 B#3 B#28 F#1 F#4 F#5） | **R5 记录与脚本的接口缺口**：多分类、逐条附件标题、读回字段、写前查重 |

## 2. 顶层定案

1. **记录仍是论文元数据的唯一接口**（v2 §2.6）。取全文另有三样东西，都在工作目录、都按"一个写者或只追加"设计：`<slug>.pdf` / `<slug>.html` 文件本身（取到了）、`fetch.jsonl`（试过什么、结果如何）、`downloads.jsonl`（下载目录里看到了什么）。理由见 §3.6。
2. **同一时刻只有一个 agent 碰浏览器**：通常是主会话；整批交给一个子 agent 时就是它，它的提醒经 `SendMessage` 交给主会话。其余子 agent 不用 `opencli browser`、`opencli web read`、浏览器型适配器、Google Scholar。这就是"全局暂停"的实现：门禁出现时不会有第二个操作者。
3. **路线选择是 agent 的判断，写在 prompt 里**（用户 2026-09-21 的回落原则）。脚本只做"一条路线套到一组记录上"，按确定的标记分类结果；认不准的页面返回 `unknown_page`，交 agent 判断。不写自动串路线的驱动（参考代码 `fetch_batch.py` 不采纳）。
4. **身份核对是写库前的条件**：`attach_file.py` 不挂核对没过、agent 也没写明接收理由的文件（与 F#1"查重是写库前的条件"同一教训）。
5. **门禁等待保持 5 分钟**（用户 2026-09-21 定的规则）。B#26 的损失来自误判和超时后同一标签页被导航，与时长无关；修法是门禁分类（§3.3）、挂起后不碰门禁标签页（§3.4）。
6. **回收站**：用户 2026-10-12 选 F#10 的 (b)——加 `trash_item.py`，只做"移进回收站"，可撤回；先列清单，用户确认后执行。`attach_file.py --replace`（B#14 原方向）不做：错文件由核对挡住，被取代的附件走回收站。
7. **NeurIPS DOI**：NeurIPS 2022–2025 的 `10.52202/…` 是 Crossref 登记、出版方为 NeurIPS 基金会的正式 DOI，但 doi.org 跳到纸质论文集的付费销售页（2026-10-12 用 DPO 验证）。按 09-23 的暂行规则处理，同 CVPR：`DOI` 填它，`url` 放 proceedings.neurips.cc 论文页，arXiv 号进 Extra。标识放哪儿的总原则（F#17）仍待用户详谈，本 spec 不改。
8. **脚本约定不变**：PEP 723、只用标准库（`pdftotext` / `pdfinfo` 是 PATH 上可选的外部程序，经 subprocess 调用）、脚本互不 import（需要另一个脚本的能力就 subprocess 调它）、稳定 `code`、退出 0/1/2、key 不进仓库不进输出。运行环境是 POSIX（Linux / WSL / macOS），`fcntl` 可用。
9. **可移植**：skill 也在别的 harness 里用。常驻下载监控是用户要的（B#34「后台下载监控程序要持续的」），能挂后台的 harness 就挂；但正确性不依赖它——`fetch_file` 自己在每篇之前、每次导航之后、每次等待中都扫描（§3.6）。
10. **不做**：自动串路线的驱动、调度框架、TSV 状态表；Google Scholar 的节流脚本（靠 §3.5 的规则）；引用数（B#18 的引用数回落顺序属于找文献，不在本 skill 范围，也不存进 Zotero）。

## 3. 流程

### 3.1 三段（batch.md）

用户在开头在、后面不在，所以需要用户的部分尽早开始，元数据工作与之并行：

| 段 | 谁 | 做什么 |
|---|---|---|
| 0 分流（几分钟） | 主会话 | `doi_to_item` 起草、`find_in_library` 查库、`fulltext_links` 列候选全文链接与开放获取状态（这几个脚本写记录，所以在子 agent 开始改记录之前跑完）；每篇分成"库里已有 / HTTP 能取 / 要浏览器 / 版本待定"；要问用户的一次问完（v2 规则）；需要浏览器且配置了机构（§6）时，**先请用户登录一次机构认证**（Ctrl+N 普通窗口），趁用户在把最常见的门禁过掉 |
| 1 浏览器段（用户在线） | 持有浏览器的 agent；子 agent 并行 | 浏览器：`fetch_file` 按出版社分组跑路线，先做版本已定的；`claim_downloads --watch` 常驻（能挂后台时）。子 agent：确认预印本的正式版（§4.5）、起草条目、摘要、标签，`fetch_file --via http` 取开放文件；版本定下的记录随时加进浏览器队列 |
| 2 无人值守 | agent | `check_pdf` → `create_item` → `attach_file` → 读回 → `report.py`（含"未取到"清单）；"未取到"的记录写 `blocker`，等用户事后逐条定 |

单篇是一篇的批次：三段收成 SKILL.md 的步骤，用同一批工具。

### 3.2 路线（以正式版为目标）

1. **正式版的开放副本能直接 HTTP 取**：会议论文集（NeurIPS、ICLR、PMLR、ACL Anthology、CVF、MICCAI）、对 curl 开放的开放获取出版社 → `fetch_file --via http`，不进浏览器。
2. **浏览器**：开放获取期刊走 PMC（PMC 对 curl 返回 JS 验证页，B#5；出版社主机会被 Zotero Connector 转到机构代理而落到 "Host Needed"，B#22）；订阅出版社走 `--via page`。已有结论的主机跳过（§3.4）。
3. **机构检索系统 → 聚合库**（有配置时，§6）：`fulltext_links` 的 `discovery` 来源给出链接，`fetch_file --via page --start link:discovery`；聚合库阅读器用 `--via viewer`。检索系统没收录时，agent 可以直接在聚合库里按题名检索，拿到文档页后 `--start url:<URL>`（B#9）。
4. **替代版本**：接受稿、PMC 作者稿、机构库副本、arXiv。附件标题写明版本（§4.3 `file_version`）。
5. **纯文本快照**：`fetch_file --via snapshot`。

各出版社的首选路线写在 publishers.md（§7），是起点不是封闭清单。

### 3.3 页面分类

`fetch_file.py` 在每次导航后读 `state`（URL、标题）并按标记表分类。识别看**主机名与正文**，不只看标题（参考代码的标题关键词 `认证|登录|授权` 太宽）。标记表是活的，随出版社知识扩充；认不准就是 `unknown_page`。

| 类 | 标记 | 结果码 | 处理 |
|---|---|---|---|
| 用户能过 | 标题"请稍候… / Just a moment… / Are you a robot?"；`input[name=cf-turnstile-response]`、`#captcha-box`；页面离开起始主机、落到配置里的机构认证主机或通用登录路径（`/idp/`、`/cas/login`、`shibboleth`、`/saml`）上；有密码输入框；Chrome / 扩展连不上 | `gate` | 流停下；agent 先提醒用户（推送；持有浏览器的是子 agent 时经 `SendMessage`），再 `fetch_file --wait-gate` |
| 要先点机构登录 | 只有 "Purchase / Get access"、没有机构访问标志，也没有"未订阅"横幅（v2 的规则：点了机构登录入口之后的登录页才是门禁） | `needs_login` | 流停下；agent 点该站的机构登录入口（判断），之后多半就是 `gate` |
| 过不去 | 正文 "Host Needed"、代理主机上的 404 → `proxy_unconfigured`；"Sorry, you have been blocked" → `site_blocked`；机构标志 + "does not subscribe" 横幅 → `no_access`；OpenReview `/pdf` 返回 403 → `not_public` | 见左 | **每个主机第一次出现时就提醒用户**是什么（B#26「两类都要在动作之前先告诉用户」、B#35），不等；该主机按 §3.4 跳过 |
| 认不准 | 以上都不是，也找不到 PDF 链接 | `unknown_page` | 流停下，附 URL、标题、正文开头；agent 判断（是门禁就按门禁处理） |

提醒的文案写明在哪儿操作（B#26）：验证码 / 人机验证就在当前标签页点；**登录按 Ctrl+N 开普通窗口**，不要用自动化窗口——登录状态整个 Chrome 共享。

### 3.4 等待、挂起、一轮即止

- **等待**：`fetch_file --wait-gate` 每 15 秒只读一次 `state`（不导航；读本身也让 opencli 的标签租约保持活跃），每 2 秒扫一次下载目录。返回 `passed`（重跑同一条命令，已完成的跳过）、`taken`（这一篇的文件已被认领）或 `timeout`（5 分钟）。
- **挂起**：超时后 agent 在 `sites.json` 记 `{"<sso-host>": {"state": "gate_pending", "session": "p2z"}}`，**门禁标签页留着、不再导航**：之后的 `fetch_file` 调用带 `--keepalive p2z`，每处理一篇读一次该会话的 `state`（保持租约——opencli 自有会话的标签页闲置超时会被回收，2026-10-12 核实——也看它是否已通过；这是脚本做的，不靠 agent 记得），直到用户说好了或运行结束才关；`--wait-gate` 超时时在输出里提示带上 `--keepalive`。其余工作换一个会话名、开在后台窗口（`--session p2z-2 --window background`，不抢用户的焦点）。之后流里再落到同一登录主机的记录直接记 `gate_pending`、不停、不等，所以只有不经这道登录的站点继续推进。其他站点做完后，对挂起的主机再试一次（再提醒一次）；仍不过 → `gate_timeout`。用户说"继续 / 登好了"随时恢复。
- **两级失败**（B#36）：
  - **路线级**——这条路不通，别的路线照走：`no_pdf_link`、`not_pdf`、`wrong_file`、`unknown_page`（agent 判断后）；同一（路线, 起点）组合不再重试。
  - **结论级**——这篇在这个主机上就是取不到：`no_access`、`proxy_unconfigured`、`not_public`、`site_blocked`、`gate_timeout`。记录有结论级失败后，`fetch_file` 对它**一律跳过，除非 `--retry CODE` 点名该类**——新办法只对它能解决的那一类失败重试一次（B#36 补充「你这都重复几次了」）。
  - `gate`、`gate_pending`、`needs_login`、`taken` 不算失败，也不记为试过；`error`（工具或网络的偶发错误）同一组合第二次出现即算路线级失败（v2"偶发错误重试一次"）。
- **主机结论**：`fetch_file` 先用 doi.org 的跳转（HTTP HEAD，不碰出版社）得到目标主机；`fetch.jsonl` 里该主机已有 `site_blocked` / `proxy_unconfigured` 的，对新记录也跳过（记 `skipped_host`），本轮不再向它发请求（B#35「停止对该站点的一切请求」）。
- **"未取到"清单**：`report.py` 从**记录**出发（没有文件、没有附件、库里也没有 PDF 的每一篇），再并上 `fetch.jsonl` 的尝试：每行原因、试过的路线、可选下一步（换开放副本 / 用户手动下载 / 快照 / 放弃 / 会后补挂）。没试过的也在清单里，原因"未尝试"。agent 在第 2 段末把清单写进各记录的 `blocker`——"这篇卡住了"只此一处。

### 3.5 限额按机器合计（B#5 B#18 B#25 B#35）

- **脚本**：所有发外部请求的脚本（`doi_to_item`、`fulltext_links`、`venue_index`、`fetch_file` 的 http 路线与对 medRxiv / bioRxiv 的页面请求）按主机共享调用间隔：`~/.cache/paper-to-zotero/pace/<host>`，`fcntl` 锁 + 上次调用时间，多个进程、多个子 agent 自动排队。429 → 写 `<host>.blocked`（`Retry-After`，OpenAlex 预算耗尽则到 UTC 零点），本机所有脚本在此之前跳过这个来源并在输出里注明；`ready.py` 列出仍在生效的。
- **agent**：Google Scholar 只由持有浏览器的 agent 用，合计每分钟至多一次。medRxiv / bioRxiv 每篇之间留足间隔、优先 API 与 Europe PMC，出现封禁页立即停止对该主机的一切请求。
- **OpenAlex key** 从 `~/.config/openalex/api_key`（600）读，只在脚本里作为 `api_key` 参数发送，不进环境变量，日志不打印带 key 的 URL；优先按 DOI 单篇查询（带 key 不扣费）。

### 3.6 工作目录与并发

```
<work>/                 必须在本地 Linux 文件系统上（scratchpad / /tmp），不能在 /mnt/c：追加写与 link 的语义要可靠
├── .started
├── sites.json          只有 agent 写：用户的声明（"no_subscription"）与挂起（{"state":"gate_pending","session":…}）
├── fetch.jsonl         追加，一行一次 write()：{slug, via, start, url, host, session, code, version, at, note}；可多进程（子 agent 的 http 路线）
├── downloads.jsonl     追加：{file, md5, status: claimed|stray|unmatched|ambiguous|unverified|not_pdf, slug?, why?, source?, at}
├── stray/              同一篇的重复副本（不删，随工作目录清掉）
├── unverified/         本轮路线取到、核对不过的文件，附来源链接（不挂，留给人看）
├── scratch/
└── records/
    ├── <slug>.json
    ├── <slug>.pdf | <slug>.html     取到的文件；谁先以独占方式创建谁算数
    └── …
```

- **为什么取全文不写记录**：浏览器段里子 agent 正在读改写记录（起草 item、标签），v2 的脚本写记录是"整份替换"、没有锁；取全文若也写记录，会互相覆盖。所以取全文只产生文件和追加日志；`sites.json` 只有 agent 写，脚本只读。
- **认领**：文件先写到 `records/.<slug>.<rand>.tmp`，再 `os.link` 到 `<slug>.pdf`（目标已存在则失败 → 这份进 `stray/`）。来源在下载目录（Windows 盘）时先复制到 `records/` 再 link，成功后才删源文件；源文件已不在（另一个扫描者先拿走了）就什么也不做。
- **扫描的时机**：`fetch_file` 在每篇开始前、每次导航之后、每次等待中都调一次 `claim_downloads --once`；能挂后台时另有 `--watch` 常驻。认领是原子的，几个扫描者同时跑也安全，所以不需要 pid 文件之类的协调。
- **`file` 与 `file_version` 的默认值**：记录没有 `file` 时，`check_pdf`、`attach_file` 依次取记录旁的 `<slug>.pdf`、`<slug>.html`；没有 `file_version` 时取 `fetch.jsonl` 里这一篇成功那一行的 `version`，再没有就是 `published`。
- **接收核对不过的文件**：agent 读过第 1 页决定接收 `unverified/` 里的某份时，把它移成 `records/<slug>.pdf`（同样独占创建），并在记录写 `pdf_accepted`（§4.4）。
- **收尾**：关闭本轮开过的所有会话（`fetch.jsonl` 与 `sites.json` 里出现过的会话名）；停掉 `--watch`；`claim_downloads --sweep`。有 `blocker` 的记录或 `unverified/` 非空时，工作目录留着，直到用户逐条定完（v2"含 blocker 不删"、"没进库的 PDF 交给用户"）。

## 4. 脚本

### 4.1 新脚本

```
fetch_file.py --via http|page|viewer|snapshot [--start doi|url|link:<source>|url:<URL>] [--session p2z] [--window foreground|background]
              [--keepalive SESSION]… [--retry CODE]… [记录路径…]
fetch_file.py --wait-gate --session S --record PATH [--timeout 300]
  候选      还没有 <slug>.pdf（snapshot：.html）的记录；found / readback 已有 PDF 附件的跳过（skipped: library_has_pdf），
            除非记录写了 need_file: true（如库里只有预印本、用户要正式版）；有结论级失败的跳过，除非 --retry 点名（§3.4）；
            该（via, start）组合已有路线级失败的跳过
  起点      doi = https://doi.org/<DOI>（先 HEAD 得到目标主机，§3.4）；url = item.url；link:<source> = 记录 links 里该来源的链接；
            url:<URL> = 给定地址（只用于单条记录）
  http      GET 起点（不经浏览器，按主机节流）；%PDF → 核对 → 认领；否则 not_pdf
  page      open 起点 → 读 state 分类（§3.3）→
            · 起点本身是 PDF：按 Chrome 的 PDF 设置分三种（publishers.md）——设为下载（用户机器上的设置，常见情形）→ opencli
              `wait download`（Chrome 的下载接口）接上，再退回扫描下载目录；内置查看器且标签页可附着 → document.contentType 是 PDF
              就在页内 fetch(location.href) 取字节；`attach_failed … chrome-extension://` → 查看器开着，按 publishers.md 当门禁请用户改设置；
            · 文章页：取 citation_pdf_url 或 "Download PDF" 链接；当前主机是该链接主机的代理形式（主机名把点换成连字符再接代理后缀，
              或匹配配置的 institution.proxy）时只取路径、在当前源上请求（B#22），否则原样请求；页内 fetch(credentials: include)，
              content-type 是 PDF → base64 分块带出 → 核对 → 认领；
            · 被拒（403、HTML、跨源跳转引起的 TypeError）→ 像点击一样在标签页里打开该链接，按上一条"起点本身是 PDF"处理（B#34）；
            · 仍没有 → no_pdf_link 或按页面分类给结论级码
  viewer    当前页或同源 iframe 里的 pdf.js：PDFViewerApplication.pdfDocument.getData() → base64 分块（聚合库阅读器，B#10）
  snapshot  open 起点 → 读 state，标题与记录题名核对通过才把 outerHTML 存成 <slug>.html（B#13）；否则 wrong_file
  核对      每个取到的文件先过 check_pdf.py --match（§4.2）；本条路线触发的下载核对不过 → 移到 unverified/<slug>-<via>.pdf，
            记来源链接，code wrong_file（B#27 再现）；扫描时看到的其他未通过 / 有歧义的文件，在本条摘要的 near_misses 里列给 agent
  流规则    gate / needs_login / unknown_page → 本条停下，流停下（剩余记录 not_run）；门禁主机已 gate_pending → 本条 gate_pending，继续；
            本条被扫描认领 → taken
  输出      不写记录；stdout 每条一行摘要 {slug, code, via, start, host, session, url?, gate_host?, near_misses?, note}，最后 summary；
            每次尝试追加 fetch.jsonl（version 取自所用链接的 version，doi / 正式版起点为 published）
  --wait-gate  §3.4；code passed | taken | timeout
  exit      0 = 全部 ok / taken / skipped；1 = 有失败或停下；2 = 无法检查（opencli 不在、工作目录不对）

claim_downloads.py --work DIR [--downloads DIR] (--once | --watch [--interval 2] | --sweep)
  新文件    下载目录里比 .started 新、downloads.jsonl 里没出现过、没有同名 .crdownload、两次扫描大小不变、%PDF 开头
  配对      check_pdf.py --match FILE 对**全部**记录 → 恰好一条通过才算配上；多条 → ambiguous，一条也没有 → unmatched：
            都留在下载目录（可能是用户自己下的），记一笔
  去向      配上的记录还没有 <slug>.pdf、库里也没有它的 PDF → 认领（§3.6）；已有 → stray/（B#7 B#27 的重复）
  --watch   常驻；工作目录里已没有待取的记录时退出
  --sweep   收尾：比 .started 新、与本轮任一已认领 / 已挂文件 md5 相同的 → stray/；其余列出（供报告），不删
  输出      每个事件一行 JSONL（同 downloads.jsonl）；exit 0

fulltext_links.py [记录路径…] [-i] [--sources arxiv,openalex,unpaywall,europepmc,s2,discovery] [--refresh]
  每条记录 → links: [{url, source, version: published|accepted|preprint|unknown, host, needs_browser}] 与
            oa: {is_oa, oa_status, pmcid, pmid}；needs_browser 来自主机表（PMC、Europe PMC 渲染页、medRxiv / bioRxiv…，表是活的）
  来源      arXiv（记录有 arXiv 号 → PDF 链接，version preprint）、OpenAlex（带 key，/works/doi:…）、Unpaywall（需 config 的
            contact_email，没有则跳过）、Europe PMC（fullTextUrlList）、Semantic Scholar（openAccessPdf）、discovery（config 有
            institution.discovery 时；Primo 的 pnxs 接口：实现前先验证普通 HTTP 能否访问，不能则这一来源改由 fetch_file 在浏览器里取，
            契约在实现时补进本节）
  机构库链接只标 version: unknown；能否算"有开放副本"由取到并核对通过决定（B#16）
  节流 §3.5；已有 links 的记录 skipped（--refresh 重查）；这是分流阶段在记录上写字段的脚本，浏览器段开始前跑完

venue_index.py build --venue neurips|iclr|icml|pmlr|tmlr|acl|cvf|miccai --year Y   |   match --title T [--venue V] [--year Y]
  从官方列表建"会议—年份—题名—论文页—PDF 链接"，缓存在 ~/.cache/paper-to-zotero/venues/；按归一化题名匹配。
  入口（B#19 B#24 已验证）：proceedings.neurips.cc、proceedings.iclr.cc（2024 起）、ICLR / ICML / NeurIPS 的 virtual 论文页
  （早年 ICLR 等没有论文集时）、PMLR 卷页、jmlr.org/tmlr、ACL Anthology、CVF Open Access、papers.miccai.org。不抓 OpenReview（会拦）。
  按需构建：第一次用到某会议某年时建，之后读缓存

trash_item.py (--key K… | --cite C…) [--restore] [--dry-run]
  PATCH {"deleted": 1}（--restore 设 0），带版本检查；--dry-run 列出 {key, itemType, title, parent} 不写
  用途：被取代的附件（report 的"待清理附件"）、用户同意删除的重复条目——这些只在用户确认清单之后用；识别退路里没长出
  父条目的独立附件是本轮自己的残留，不用确认（v2 的做法）
  code ok | not_found | already_trashed | version_conflict
```

### 4.2 `check_pdf.py`（R1）

- **抽取**：PATH 上有 `pdftotext` 就用它（`-f 1 -l 3 -enc UTF-8`，按换页符分页），页数取自 `pdfinfo` 或现有的 `/Count`；否则用现有抽取器。`evidence.extractor` 写明用了哪个。加密文件的提前返回挪到 pdftotext 尝试之后（pdftotext 能读的加密文件照常核对）。
- **两条通过路径**：
  - A：整条归一化题名（或 `alt_titles` 中任一条）出现在某页 → `ok` / `ok_on_page_2` / `ok_on_page_3`（现状不变）；
  - B：题名中 ≥4 字母的词（连字、弯引号归一化）至少 80% 出现在前 3 页，**且** `doi_found` 或 `first_author_found` → `ok_by_words`。阈值取自参考代码 `verify()`（对 9 篇真文件全过、2 份错文件全拒）。
- **新的失败码**（都只在明确时触发，避免误伤正文）：
  - `erratum_suspected`：第 1 页**页首、题名之前**是 Correction / Erratum / Corrigendum / Retraction（"Correction to: <题名>"会让 A 通过，所以不论 A 是否通过都查），而题名本身不含这些词；
  - `supplement_suspected`：同样只看页首、题名之前的 "Supplementary Material / Information / Appendix"（正文页边的 "Supplemental content" 不算）；记录 `file_version` 是 `supplement` 时不查；
  - `doi_mismatch`：第 1 页印的 DOI 都不是这一篇的；只对 `file_version` 为 published 的记录查（接受稿、medRxiv、arXiv 版印的是它们自己的 DOI）。
- **备选题名**：记录的 `alt_titles`（例如改了题的正式版对应的 arXiv 题名，B#15）与 `--alt-title`。
- **HTML 快照**：去标签后按 A / B 核对；正文是代理或访问拒绝页（"Host Needed"、"Access denied"）→ `not_the_article`（B#13）。
- **`--match FILE 记录…`**：同一个文件对多条记录各判一次（FILE 覆盖记录的 `file`），输出每条的 code 与 `{"matched": [slug…]}`；不写记录，与 `-i` 互斥。供 `fetch_file`、`claim_downloads` 用。
- `pdf` 字段新增 `md5`（被核对文件的 md5），供 `attach_file` 的写库前条件。
- 实现时定下的细节（2026-10-12 第一轮）：
  - B 的第一作者只认第 1 页前 1500 字（署名区）——同题材论文正文里引用了该作者，词覆盖又是 100%，曾因此误过；DOI 仍认前 3 页。
  - "页首"= 第 1 页题名位置之前、至多 500 字；题名不在第 1 页时取开头 500 字。勘误 / 补充材料的词只在行首、后接冒号、行尾或 to / for / notice 等时才算标题。
  - `doi_mismatch` 另要求记录的 DOI 不在前 3 页任何地方出现（页边或脚注的别的 DOI 不误伤）；HTML 只看 citation_doi 等元数据。
  - 文件不以 .pdf 结尾且内容像 HTML 才按 HTML 核对；文件的取法顺序：`file` > `--pdf` > `<slug>.pdf` > `<slug>.html`。
  - 新增 `--file-version`（覆盖记录与 fetch.jsonl，供第二轮 fetch_file 在写 fetch.jsonl 之前核对）。
  - 回归：B#1 的误报由 ACL 2023/2024 与 CVF 的论文复现，改后全过；没有 pdftotext 时仍不过——`ready.py`（第二轮）要报出来。

### 4.3 其余脚本的改动

```
attach_file.py
  写库前条件  有记录时（流模式与新的 --record）：文件 md5 = pdf.md5 且 pdf.code ∈ {ok, ok_on_page_2, ok_on_page_3, ok_by_words}，
             或 = pdf_accepted.md5；否则 failed: not_verified（hint：先跑 check_pdf.py -i，或读第 1 页后写 pdf_accepted）
             没有记录时（v1 单条 --key --file --url）：自己用父条目的题名、DOI、第一作者调 check_pdf（subprocess，把
             {item, file} 作为记录从 stdin 送进流模式），不过则拒绝，除非 --accept "<理由>"；理由写进输出与报告。没有绕过的路
  附件标题    记录 attach_title > --title > 由 file_version 得出（published → PDF，accepted → Accepted manuscript，
             preprint → Preprint，supplement → Supplement，snapshot → Snapshot，unknown → Full text (version unknown)）（B#28 B#33）；
             单条模式加 --file-version（传给核对，也决定标题）
  --record    单条模式加 --record PATH：成功后把 attach 写回该记录（B#3）
  已有 PDF    流模式：库里那条已有 PDF（md5 不同）、记录没写 need_file: true → skipped: library_has_pdf，不挂第二份
             （2026-10-12 冒烟时发现：手上有文件就会再挂一份）
  迁移        现有流模式测试（tests/test_attach_file.py）的记录补上 pdf；进行中的 v2 工作目录要先重跑 check_pdf -i
create_item.py
  collection  字符串或列表；--collection 可重复；读回比对全部分类（B#2）
  写前查重    没有 found / saved 的记录，POST 前按 DOI、arXiv 号、归一化题名查库（F#1）：
             DOI 或 arXiv 号命中、条目 dateAdded 早于 .started → 不建，写 found，code exists（skipped）；
             命中的是本轮中断前自己建的（dateAdded 晚于 .started）→ 写 saved，code recovered；
             只有题名命中、或 near_match → 不建，code possible_duplicate（失败），由 agent 判断（预印本 / 正式版一对按 SKILL.md 问用户）；
             是同一篇 → agent 在记录写 found: {key}，再 find_in_library --readback 补全现状；不是 → 把那条的 key 写进记录的 distinct_from，重跑时不再算它
             查库用 subprocess 调 find_in_library（全部待建记录一次从 stdin 送进去），读它给的 found.matched_by 与 found.dateAdded；
             找不到 .started（stdin 来的记录，或工作目录里没有）时，标识符命中一律按 exists；记录有自己的非 arXiv DOI、却只经
             arXiv 号命中 → 那条多半是预印本，按 possible_duplicate（find_in_library 同样把它报成 near_match，§4.5）
doi_to_item.py
  副标题      CSL 有 subtitle → "标题: 副标题"（B#29）
  arXiv 分类  arXiv 号经 DataCite CSL 起草时，CSL 已带 categories：去掉 "FOS:" 重复项，记录还没有 tags 时写成 type 1 标签（B#29）；
             写法随库里已有的（Zotero arXiv 翻译器的格式）："Machine Learning (cs.LG)" → "Computer Science - Machine Learning"，
             "(stat.ML)" → "Statistics - Machine Learning"；认不出的大类保留 DataCite 原文；
             docstring 里"从不写标签"一句相应改掉
  勘误警告    题名以 Correction / Erratum / Corrigendum / Retraction 开头、页码单页或以 e / r 开头、没有作者 → warnings（B#32）
  LNCS        doi.org 的 CSL 把 container-title 压成一项（只剩丛书名）。book-chapter 且带 ISSN（现有警告处）时，再调一次（§3.5 的节流在第二轮接上）
             api.crossref.org/works/<DOI>：container-title 两项且第一项是已知丛书（LNCS、LNAI、LNBI、CCIS…）→ conferencePaper，
             proceedingsTitle = 第二项，series = 第一项（F#16）
  正式版      arXiv 标识符 → published_candidates: [{doi, venue, year, title, url, pdf_url, source, title_differs}]，来源：arXiv API 的
             journal_ref / doi（429 → OAI-PMH arXivRaw，B#18 补充）、Crossref 题名检索（排除 10.48550，归一化相似度 ≥ 0.9）、OpenAlex 该
             arXiv DOI 的 locations、venue_index match（ICLR / ICML / TMLR 等无 DOI 的会议）。不自动改 item（B#4）
  --redraft   doi_to_item.py --redraft <正式版 DOI 或 venue:<会议>:<年>> -i <记录>：在**原记录**上换成正式版的 item，保留 slug、
             citationKey、tags、collection；arXiv 号进 extra，题名不同写进 alt_titles；清掉 found、readback、checks、links——
             它们说的是预印本。之后 agent 对这条重跑 find_in_library、check_item、fulltext_links（§4.5）
find_in_library.py
  --readback  写 readback 字段，不再覆盖 found（found = 本轮开始前库里就有）；404 时删 readback、写 blocker，saved 不动；
             report、attach_file 读库内现状时优先 readback（B#3）
  found       与 readback 同形，新增 matched_by（doi | arxiv | title；near_match 仍以 code 区分）与 dateAdded，供 create_item 查重；
             记录有自己的非 arXiv DOI 而只经 arXiv 号命中 → near_match（预印本 / 正式版一对）；题名完全相同、但库里那条带着
             另一个 DOI（预印本的 10.48550、勘误）→ 同样 near_match，库里那条没有 DOI 时题名命中仍算 found；记录的 distinct_from 里的 key
             在每一级查找中都排除，排除后这一级为空就继续下一级
  near_match  未决：create_item 报 possible_duplicate、attach_file 报 unresolved_match，都不跳过也不写；agent 定为同一篇就把
             found 换成 {key}，不是就删 found、把 key 写进 distinct_from
  --md5 FILE… 文件是否已作为附件在库里：{file, md5, attachment_key, parent_key, citationKey} | null；带时间戳的出版社 PDF（IEEE 等）
              md5 必然不同，这类按题名对（publishers.md 已有）（B#27）
file_and_tag.py
  --remove-collection K（可重复）；批量文件的 remove_collection；批量条目可用 "cite" 代替 "key"（F#4 F#5）
report.py
  新增节     "未取到"清单（§3.4）；替代版本（file_version ≠ published）；待清理附件（本轮挂上正式版的条目下，原有的快照 / 作者稿 /
             预印本附件，给 key 与原因，供 trash_item）（B#14）；新标签按前缀分组（B#8）；citation key 与最终作者 / 年 / 题名不符的提醒
             （用户给定的键除外）（B#31）；下载目录里本轮留下、未处理的文件与 unverified/（claim_downloads --sweep）；本轮提醒过的
             过不去的主机
ready.py
  新增       pdftotext / pdfinfo: 路径 | null；config: {openalex_key, contact_email, institution: {auth_hosts, proxy, discovery,
             aggregators}} 各为 bool；仍在生效的 .blocked 主机
```

### 4.4 记录的新字段

| 字段 | 谁写 | 含义 |
|---|---|---|
| `collection` | agent | 现在可以是列表 |
| `alt_titles` | agent / `doi_to_item --redraft` | 核对时也接受的题名 |
| `published_candidates` | `doi_to_item` | 预印本可能的正式版，待 agent 确认 |
| `links`、`oa` | `fulltext_links`（分流阶段） | 候选全文链接；开放获取状态、PMCID |
| `need_file` | agent | 库里已有 PDF 仍要取（例如只有预印本、用户要正式版） |
| `file_version` | agent（可缺省，§3.6） | published / accepted / preprint / supplement / snapshot / unknown（links 与 fetch.jsonl 的 `version` 用同一套词） |
| `attach_title` | agent | 逐条附件标题 |
| `pdf.md5` | `check_pdf` | 被核对文件的 md5 |
| `pdf_accepted` | agent | `{md5, reason}`：核对没过但 agent 读过后接收 |
| `readback` | `find_in_library --readback` | 读回的库内现状；`found` 只表示本轮开始前已在库 |
| `distinct_from` | agent | `create_item` 报 `possible_duplicate` 后，agent 判定不是同一篇的库内条目 key |

### 4.5 版本确认

`doi_to_item` 给出 `published_candidates` 后，agent（分流后由子 agent 并行）逐条确认：题名、作者、年份一致；会议名与 arXiv 的评论 / journal_ref 不冲突。确认的用 `--redraft` 在原记录上换成正式版——slug 和 citationKey 不变，不会多出一条"第二篇"；预印本时期查到的 `found`（库里那条可能就是预印本）随之清掉，重跑 `find_in_library` 按正式版再查，避免把正式版 PDF 挂到库里的预印本条目上；不确定的并进"一次问完"的问题。记录的版本定下之后才进浏览器队列，所以去哪取文件、建什么类型的条目都按正式版，citation key 也在建条目时就是最终的（B#31）。

## 5. 不变的部分

v2 的身份模型（citationKey）、`--cite` 解析、流约定（§3.3）、幂等与失败隔离、`-i` 摘要、`--dry-run`、测试方式（stdlib unittest + 自带 mock）、授权规则、标签规范（活的）、"每篇论文至少有一个可解析的标识"的暂行规则、"Reaching a page"的回落阶梯（浏览器型适配器失败 → 用 `opencli browser` 重开同一页，B#20 的回落路径已在其中）。

## 6. 本地配置（不进仓库）

```json
// ~/.config/paper-to-zotero/config.json（600；字段都可缺，缺则对应能力跳过）
{
  "contact_email": "<email>",                 // Unpaywall 必填；Crossref / OpenAlex 的 mailto
  "institution": {
    "auth_hosts": ["<sso-host>"],             // 机构认证主机：落到这里 = 用户能过的门禁
    "proxy": "<proxy-domain>",                // 代理主机后缀（代理后的主机 = <主机名点换连字符>.<proxy-domain>）：其上的 "Host Needed" / 404 = proxy_unconfigured
    "discovery": {"type": "primo", "base": "https://<discovery-host>", "vid": "<vid>", "tab": "<tab>", "scope": "<scope>"},
    "aggregators": {"proquest": {"proxy_host": "www-proquest-com.<proxy-domain>", "accountid": "<accountid>"}}
  }
}
```

OpenAlex key 沿用 `~/.config/openalex/api_key`（已存在）。`contact_email` 由用户自己填——向 Unpaywall 发送邮箱要用户同意。publishers.md 只写这个格式，不写任何机构的值；机构相关的值在仓库里一律写成占位符（AGENTS.md）。缓存：`~/.cache/paper-to-zotero/{pace,venues}/`。

## 7. 文档

- **SKILL.md**：
  - 第 2 步：NeurIPS DOI 事实与写法（§2.7）；PMID 会被 Zotero 迁成独立字段，之后改字段不改 Extra（B#30）；`collection` 可多个；预印本先看 `published_candidates`、用 `--redraft`。
  - 第 3 步：改写为工具与路线（§3.2）、`fetch_file` 示例一个、核对是写库前条件、`pdf_accepted` 与 `unverified/`。
  - Gate 规则：页面四类（§3.3）、同一时刻只有一个 agent 碰浏览器、等待只读、挂起后不碰门禁标签页、提醒文案（验证在当前标签页，登录用 Ctrl+N）。
  - Rules：识别退路里移进回收站改用 `trash_item`；Residue 加"本轮所有会话"、`stray/`、`unverified/`、工作目录的保留条件（§3.6）。
  - Instruments：opencli 自有会话闲置会被回收、`bind` 不会；`browser network` 的输出先存文件再取 key（读一次就空，B#17）；适配器失败时把原始输出存进 `scratch/`，写进报告的 skill notes（B#20）。
- **batch.md**：
  - 三段（§3.1）；并行规则（§2.2、§3.5）；两级失败、一轮即止与"未取到"清单（§3.4）。
  - 下载扫描与用户协作，写清 B#34 用户原话的两层意思：用户在场时可以替 agent 点 PDF 按钮或下载，agent 会接上；但 agent 照样主动去取。
- **publishers.md** 重排：
  - 路线顺序与各出版社首选路线表。
  - Zotero Connector 自动转代理是怎么回事、如何处理（B#22）；"过不去的页面"表（Host Needed、代理 404、会前 403、封禁、未订阅）。
  - 已验证行为：
    - 会议：PMLR / NeurIPS / CVF / ICLR / ACL / MICCAI 的 PDF 取法，NeurIPS 正文与附录分开（B#6 B#24）；OpenReview 页面内用 `api2.openreview.net/notes/search?term=<题名>` 找 forum id，同一篇有 CoRR 与会议两条时按 `venue` 选（B#23）。
    - 出版社：OUP / ACM / nature.com / NEJM AI / Science / JAMA / PNAS / Cell Press / BMJ 的行为（B#37）；Nature "Article in Press" 与 `_reference.pdf` 是未编辑的接受稿（B#33）。
    - 检索系统与聚合库：检索系统的链接也可能指错文件（B#37）；聚合库可以直接按题名检索（B#9）。
    - PMC 与预印本：PMC 先 cookie 墙后验证码（已有）、对 curl 返回验证页；Europe PMC `?pdf=render` 返回 HTML（B#5）；medRxiv 封禁（B#35）。
    - Cloudflare 验证：等 ≥30 秒，同时提醒（B#12）。
  - 配置格式（§6）。
- **tagging.md**：什么算"模型名"标签——一个具名的、可被引用的模型或系统（GPT-4、Med-PaLM）；数据集用 `dataset/`；方法类概念（Scalable oversight、Temperature scaling、Semantic entropy）不做裸标签，归入相应前缀维度或不打（B#8）。
- **organize.md**：`trash_item`、`--remove-collection`；第三轮的条目（§8）。

## 8. 实现分轮

spec 一次写全，实现分三轮，每轮一个提交（或一组连贯提交），每轮结束更新本节的进度。

进度：第一轮 2026-10-12 完成（脚本、测试 285 个全过、文档；对真实库的只读冒烟通过；`trash_item` 的写入尚未对真实库跑过，第一次用时先移一条再 `--restore`）。第二轮未开始。

1. **第一轮（R1、R5 与文档）**：
   - 脚本：`check_pdf`（§4.2，先于 `attach_file` 的写库前条件）；`attach_file`（含测试迁移）；`create_item`；`doi_to_item`（副标题、arXiv 分类、勘误警告、LNCS）；`find_in_library --readback`；`file_and_tag`；`trash_item`。
   - 文档：SKILL.md 第 2 步、Rules、Instruments；publishers.md（已验证的事实部分）；tagging.md。
   - 过渡：第一轮之后、第二轮之前，取文件仍是 v2 的做法，但 `attach_file` 已要求 `pdf.md5`。所以 SKILL.md 第 3 步在第一轮就写明：文件到手后先 `check_pdf -i`，再 `attach_file`；核对不过就读第 1 页，接收则写 `pdf_accepted`。
2. **第二轮（R2、R3、R4）**：
   - 脚本：`fetch_file`；`claim_downloads`；`fulltext_links`（含 discovery 的可达性验证）；§3.5 节流；`venue_index`；`doi_to_item` 的 `published_candidates` 与 `--redraft`；`find_in_library --md5`；`report` 新增节；`ready` 的配置检查。
   - 文档：SKILL.md 第 3 步与 Gate；batch.md 三段；publishers.md 的路线表。
3. **第三轮**：F# 里整理已有条目的那几条，开工前在本 spec 补契约。
   - F#3：各子命令的行形状写进 `--help`；`read_library items --tag`；stdin 是多个缩进 JSON 时只报一次"不是 JSONL / 数组"，不逐行报错。
   - F#6：`find_in_library --dupes` 吃库内条目。
   - F#7：只读 lint，输出能直接喂给 `update_item --patch` 的 JSONL。
   - F#12：处理重复条目：先列字段对照，把被删那条独有的信息并过来，再请用户删。
   - F#14：先验证"插件改写 extra"的推断。
   - F#8：笔记上的标签，问用户。

### 8.1 测试与验证

- **单元测试**：每个新脚本一个 `tests/test_<script>.py`（v2 §4.3 方式）。
  - `fetch_file` 的浏览器部分用假的 `opencli`（PATH 上的桩脚本按场景返回 state / eval 输出），覆盖每个结果码、流停下、`gate_pending` 继续、主机结论跳过、两级失败与 `--retry`、代理源改写只在代理形式下发生。
  - `claim_downloads` 覆盖唯一配对、ambiguous、重复进 stray、跨文件系统认领、源文件被别的扫描者拿走、`.crdownload` 与大小不稳。
- **核对回归**（第一轮）：
  - 样本：两批误报里开放的 PDF（Self-Refine、Reflexion、一篇 ACL Anthology、CVF 版 StyleGAN、那篇 medRxiv、FnT 改题那篇的 arXiv 版）；一份 1 页勘误；一份页边带 "Supplemental content" 的正文；一份接受稿（印着自己的 DOI）；一对错配（A 的 PDF 对 B 的记录）。
  - 做法：下载到 scratch 实测，改前改后对比；文件不进仓库。
- **真实批次**（第二轮，用户在线，落 `tmp`）：
  - 约 10 篇，覆盖：HTTP 论文集、PMC 开放获取、订阅出版社页面内取、Chrome 直接下载（OUP 类）、代理 "Host Needed"、会前 403、一次登录门禁中用户替 agent 点下载、一篇无权限进"未取到"、一篇 ICLR 预印本经 `--redraft` 换成会议版。
  - 中途中断一次重跑；核对 `fetch.jsonl`、`downloads.jsonl`、报告与读回一致；收尾无残留、会话全关。
  - 顺带验证 Cloudflare 验证在后台窗口能否自行通过；不能则挂起期间改为前台、并在提醒里说明。
- **新 agent 演练**（v2 遗留）：只凭 SKILL.md + batch.md 跑一批，记摩擦。
- **收尾**：v2 spec 加 `Superseded by`；本 spec 冻结；两份 issue 按 §9 处理。

## 9. 条目去向

| 条目 | 去向 | 轮 |
|---|---|---|
| B#1 F#13 | §4.2 抽取与两条通过路径 | 1 |
| B#2 | §4.3 create_item collection 列表 | 1 |
| B#3 | §4.3 readback 字段；attach_file --record | 1 |
| B#4 B#19 | published_candidates、--redraft、§4.5；venue_index | 2 |
| B#5 | §3.2 路线（PMC 走浏览器）、§3.5 节流、publishers.md | 1、2 |
| B#6 B#24 | publishers.md；SKILL.md NeurIPS DOI（§2.7）；venue_index | 1、2 |
| B#7 B#27 B#34 | §3.6 认领与扫描时机、claim_downloads、fetch_file 的 wait download 与 unverified/、--sweep、find_in_library --md5 | 2 |
| B#8 | tagging.md；report 新标签分组 | 1、2 |
| B#9 B#16 | fulltext_links（discovery、Unpaywall、Europe PMC、S2）、聚合库直接检索、§6 配置 | 2 |
| B#10 B#11 B#22 | fetch_file --via viewer / page（代理源改写）；publishers.md | 2 |
| B#12 B#13 B#23 B#26 B#35 | §3.3 页面分类与提醒、§3.4 等待与挂起；check_pdf 核对 HTML；publishers.md | 1、2 |
| B#14 F#10 | trash_item；report 待清理附件；--replace 不做（§2.6） | 1、2 |
| B#15 | check_pdf alt_titles | 1 |
| B#17 | SKILL.md Instruments | 1 |
| B#18 B#25 | §3.5；arXiv OAI-PMH 回落进 published_candidates；引用数回落顺序不做（§2.10） | 2 |
| B#20 | 回落路径已在 v2"Reaching a page"（§5）；适配器原始输出存 scratch 写进 Instruments；适配器本身的问题待复现 | 1 |
| B#21 B#36 | §3.1 三段、§3.4 两级失败与"未取到"清单 | 2 |
| B#28 B#33 | file_version、attach_title；publishers.md Article in Press | 1 |
| B#29 B#32 | doi_to_item 副标题、arXiv 分类、勘误警告；check_pdf erratum / doi_mismatch | 1 |
| B#30 | SKILL.md 第 2 步 | 1 |
| B#31 | §4.5 先定版本再建条目；report key 提醒 | 2 |
| B#37 | publishers.md；末尾 attach_file 只输出 `}` 那次：不进本 spec，归档时写明"再遇到时保留完整输出" | 1 |
| F#1 F#4 F#5 F#16 | §4.3 | 1 |
| F#3 F#6 F#7 F#8 F#12 F#14 | §8 第三轮 | 3 |
| F#9 F#17 | 不进本 spec：等用户详谈；F# 归档时移到新的 issue 文件 | — |
| F#2 F#11 F#15 | 已处理（F# 原文） | — |

## 10. 修订历史

- 2026-10-12 草案：两份 issue 分诊（五个根因）；用户定回收站走 (b)、其余按设计者建议；NeurIPS DOI 按暂行规则；门禁等待保持 5 分钟（撤回讨论中提过的 15 分钟）；取全文不写记录（§3.6）。
- 2026-10-12 第一轮审查（需求忠实度、技术正确性、设计一致性三位独立审查）后修订：
  - 页面分为四类：加 `needs_login`、`unknown_page`；过不去的页面当场提醒；登录提醒改为 Ctrl+N；挂起后门禁标签页靠读 state 保活，其余工作开在后台窗口。
  - 失败分两级，`--retry` 必须点名；新加 `gate_timeout`；主机结论在导航前先查。
  - `sites.json` 只有 agent 写；扫描时机写明，常驻监控保留但正确性不依赖它（一位审查建议删掉常驻，因用户在 B#34 明确要求持续监控而不采纳）；配对对全部记录做，重复才进得了 stray。
  - 版本确认改为原地 `--redraft`；`venue_index` 提前到第二轮，加 ICML、TMLR 与 virtual 页。
  - `attach_file` 写库前条件覆盖单条模式（`--accept`），附测试迁移；`create_item` 查重区分 exists / recovered / possible_duplicate。
  - 与代码对齐：LNCS 改用 Crossref REST、arXiv 分类取自 DataCite CSL；check_pdf 的新失败码只看页首、`doi_mismatch` 只对正式版。
  - 其余：`trash_item` 去掉记录路径形式；工作目录必须在本地文件系统；引用数明确不做。
- 2026-10-12 advisor 复核后：`--redraft` 清掉预印本的 found 并重查；门禁标签页保活改由 `fetch_file --keepalive` 执行；PDF 起点按 Chrome 设置分三种、以下载为先；写明第一轮到第二轮之间的过渡做法。
