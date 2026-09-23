# paper-to-zotero — 设计 spec v9(已实现并验证;2026-09-22 冻结)

> Superseded by `20260923-paper-to-zotero-v2-spec.md`(2026-09-23:记录流、citationKey 身份、新脚本、文档按分支拆分)。

> 本 spec 已冻结:skill 已按此实现、通过真实运行、新 agent 演练与第一批整理,并于 2026-09-22 提交。当前行为以 `paper-to-zotero/` 下的 SKILL.md、references 与脚本为准;后续优化另起新日期的 spec。

**状态(2026-09-21)**:v3 经三份独立审查(需求忠实度、技术正确性、agent 可用性)+ 对照 zotero 10.0.3 源码自审;v4 起按用户原则复审并逐条决定(§7);v8 跑完全部探针(§12);v9 是通读整理后的定稿——去掉了历次改通道留下的过时引用,合并了重复段落。脚本、SKILL.md、references 已实现并验证(§8、§10)。修订历史见 §13。

## 1. 目标与边界

**目标**:用户给出题目 / 关键词 / DOI / arXiv 号 / URL → Zotero 里多出**一条带 PDF、归好类、打好标签的条目**(分类由用户点名或确认,定不下来放临时分类;标签由 agent 管理)→ 库外不留残留(residue)。用户会长期使用。

**边界**
- 只处理用户**逐一点名**的论文;列表 = 逐篇顺序执行,不做批量抓取。第一次 gate 超时(用户 5 分钟内没通过)就停下整个列表并汇报(保护用户的机构账号)。
- 只使用用户本人已有的订阅,不绕过付费墙。
- 库内检索 / 导出 / 引用属于 `zotero` skill(本 skill 只补它的缺口:按标识符查重,见 §5 的退役条件);通用浏览器自动化属于 `opencli-browser`。
- 也能处理**已有**条目:重新归类、修正与补充标签、挂 PDF——经本地写 API(U9)。整理全库是 skill 做完之后的一次任务(§8 第 5 步),按分类分批、每批先给用户看清单。
- 仓库 `uxfion/skills` 是**公开**的:skill 的文本保持通用,不出现学校名、代理、Windows 用户路径等个人事实(这些只放在 `.memory/`)。

## 2. 原则(用户的明确要求)

1. **只补缺口**:`zotero`、`opencli-usage`、`opencli-browser` 已有的不重做——它们会自己更新。本 skill 只提供它们没有的能力,以及本任务特有的上下文和提示。
2. **OpenCLI 是适配层**,适用于所有面向网页的阶段:运行时发现的适配器 → 最底层 `opencli browser`。不写死适配器名(用户习惯用 Google Scholar,这一条作为提示保留)。
   **访问阶梯(U6)**:拿不到——被拦、验证页、空结果——就**自动回落**;一次访问失败不是停下或放弃的理由。
   - 直接访问(web search / fetch / curl / wget)失败 → OpenCLI 适配器(经 `opencli-usage` 发现)。
   - **API 型适配器**(`browser: false`,本质也是直接请求)失败 → `opencli web read`(一次性,在用户的 Chrome 里带 cookie 把页面读成 Markdown)→ `opencli browser` 自己操作,看能否解决 → 解决不了就是 gate(§2.6),提醒用户介入。
   - **浏览器型适配器**(`browser: true`)失败:已经是有头浏览器,多半是被拦。适配器的标签页此时已关,所以用 `opencli browser` 在前台重开同一页——既是诊断(验证页 / 登录页 → gate;页面正常 → 是适配器坏了,自己读),也是给用户一个可以操作的标签页。
   - 缺任何信息(摘要、页码、会议名…)同理:可用的工具都可以试。
   - **这是写给 agent 的 prompt,不是脚本或决策表**:怎么回落、重试几次由 agent 判断(对正在拦你的接口反复重试只会更糟:瞬时错误重试一次,403 / 验证页直接下一级)。SKILL.md 用几句话讲清原则即可。

   OpenCLI 的优势:有头、带登录状态的真实浏览器,而且有用户值守——提醒他、给他处理时间即可。已知会拦的主机(出版商、Google Scholar)直接从 OpenCLI 这一级开始(§2.5)。
3. **中间层是 agent 的判断**:检索、选候选、修正关键词、选标签、问用户。
4. **脚本单一功能、互不依赖**,只写确定性的缺口;出问题易定位,单个可独立更新。
5. **Real navigation 按主机划界**:对出版商主机的任何请求(用户给的 URL、读摘要、拿 PDF)都在用户的 Chrome 里以读者方式进行。元数据服务(doi.org、Crossref、OpenAlex、arXiv API)直接调用。Google Scholar 这类给人看的检索页同样只经 OpenCLI(用户的 Chrome,有头浏览器)访问——agent 自己发请求最容易被判成机器人。curl 出版商主机已实测被拦(IEEE 502/202);页面内 `fetch` v1 不用、文档里不提。
6. **Gate = 用户能帮忙过、agent 自己过不去的事**:机构登录、人机验证(含 Google Scholar 的)、授权页、agent 试过仍过不去的页面错误;也包括启动 Zotero、改 Chrome 设置、Chrome 没开或 OpenCLI 扩展没连上、点了下载却弹出系统"另存为"对话框、Zotero 弹出本地 API 授权框(请用户点 Always Allow)。用户在场就是资源:遇到这类页面不关标签页、不绕开、不放弃。agent 走到门前 → **先提醒用户**(哪一页在等、要他做什么;标签页放在前台窗口;**必须用推送通知**——2026-09-22 首次真实运行时只在终端写了一句,用户在看浏览器,没看到)→ 在门前等(**5 分钟**)→ 通过后从原处继续。超时**保留标签页**并问用户。凭据永远由用户输入。
7. **Residue 可枚举**:工作目录 + 浏览器 session。工具顺手写出的文件(如 `web read` 的输出)不必回避,让它落在工作目录里、用完即删。成功后立即清理;没进库的 PDF 是交付物,不是残留。
8. **写库授权**:用户"导入 / 添加这篇"的请求就是授权("能不能帮我导入…"是礼貌的请求,同样算);让用户在候选中选择后,他的选择即授权。单纯问能力("能导入 Elsevier 的吗?")只回答。改**已有**条目(整理、删标签)先给清单、确认后写。本地写 API 的 key 用户允许永久保存(U9),缺了随时向用户申请。
9. **先设计后执行;决定性的事与用户讨论**。

## 3. 已核实的事实

### 3.1 Connector 通道(`127.0.0.1:23119/connector/*`;无需授权;源码 10.0.3 + 实测)

v9 起只用于两处:Zotero 在线探测(`/connector/ping`)和无 DOI 记录时的识别退路(`saveStandaloneAttachment`,§3.6)。其余是新建条目的后备通道事实,留作参考。

- `ping` → 200,响应头 `X-Zotero-Version`、`X-Zotero-Connector-API-Version`。
- `saveStandaloneAttachment`:正文 = PDF 字节;`X-Metadata {sessionID, title, url}`;`Content-Type: application/pdf`;`Content-Length` 必填 → 201 `{canRecognize: true}`,并**触发"自动为 PDF 检索元数据"**(2026-09-21 实测:10 秒内建出 `preprint` 父条目——arXiv 翻译器给 DOI、archiveID、arXiv 分类作自动标签、一条 "Comment: …" 笔记;文件按用户设置自动重命名)。条目落在 Zotero 窗口**当前选中**的分类,之后要用 `file_and_tag.py` 归位。
- 后备通道(新建条目):`saveItems {sessionID, uri, items:[{id,…}]}` → 201 无正文、**不返回 key**;条目落在当前选中的分类;标签只能是自动标签,且用户关闭 `automaticTags` 偏好时被静默丢弃。`saveAttachment`(`X-Metadata {sessionID, parentItemID, title, url}`;`url` 为空 → 500 且条目已建成;`Content-Type` 必须 `application/pdf`;不可写库返回 200 而非 201)。`updateSession {sessionID, target(必填,treeViewID), tags, note}` 覆盖语义、只调一次、仅读源码未实测。session gc 有 bug,不要依赖 TTL;saveItems 500 后同一 sessionID 重试 → 409,每次用新 UUID。请求头 `X-Zotero-Connector-API-Version` 带了且低于服务器版本 → 400;UA 不要伪装成浏览器。已实测 saveItems + saveAttachment 成功(`WL3IHIVX`、`8D58AIM9`)。
- 不用的接口:`import`(session 键是内部 id,无法挂附件)、`hasAttachmentResolvers` / `saveAttachmentFromResolver`(先建条目再找 OA PDF,有半成功风险)。
- connector 无 PDF 时的快照(`saveSnapshot` / `saveSingleFile`,SingleFile 打包的自包含 HTML):用户库里已有 63 个——附件 title "Snapshot"、`imported_url`、`text/html`、charset utf-8、url = 页面地址、文件名取自 URL 末段。`attach_file.py` 的 HTML 模式照此形状写(title Snapshot、text/html、utf-8),内容是浏览器里页面的 `outerHTML`(不内联 CSS / 图片,但 Zotero 会索引其文本)。

### 3.2 本地 Web API(`/api/*`;2026-09-21 读写全部实测)

**读**(无需授权、无需请求头):
- 被关闭时 403 `Local API is not enabled`(connector 照常可用)→ 开本地 API 是用户的事(gate)。
- 检索:`q=` 默认 `qmode=titleCreatorYear`(分词后 AND 的精确词匹配,一个拼写差异就漏);**按 DOI / arXiv 号查用 `qmode=fields`**(实测命中,不搜全文;`everything` 会把"参考文献里引用了它"的论文也算上);非法 qmode → 500。`zotero` skill 的 `search` 不传 qmode → 按 DOI 永远查不到(实测)。
- `/api/schema` 自带 CSL↔Zotero 映射(`csl.types`、`csl.fields`、`csl.names`)和各类型字段表(含 `baseField`);`/api/itemTypeFields?itemType=X`(非法类型 → 400;取 `field` 键,`localized` 是界面语言)。
- 多对象响应带 `Last-Modified-Version`(库版本);`since=<v>` 精确返回版本大于 v 的对象(实测)。子附件 JSON 带 `md5`、`filename`、`contentType`;`/items/:key/fulltext` 给索引文本。条目 JSON 的 `collections` 是 8 位 key;collection 记录有 `key`、`name`、`parentCollection`——落点就用这个 key。
- 每个响应带 `Zotero-Server-ID`(实例标识)。

**写**(Web API v3 语义;**没有限流**——源码注释 "no rate limits",只有授权弹框限 5 次/分钟):
- 授权:`POST /api/local/authorize {appName}`,**也要带 `Zotero-Server-ID`**(缺 → 428)→ Zotero 弹框(gate)→ Always Allow → `{key, remember: true}`,key 持久(存在 profile 的 `localAPIKeys.json`);Allow 的 key 一次性,不够用。
- 写请求头:`Zotero-API-Key`(缺 / 错 → 401)、`Zotero-Server-ID`(缺 → 428,不匹配 → 412:key 属于别的实例,重新授权)。
- `POST /items` 数组(≤50 个对象)→ 200 `{successful: {"0": {key, version, data}}, failed: {"i": {code, message}}}`;条目 JSON 直接带 `collections` 与 `tags`(`{tag, type}`,type 0 手动 / 1 自动,读回原样)。**JSON 校验与 connector 同样宽松**(`Item.fromJSON(strict: false)`):未知 itemType → 400 显式;未知字符串字段 → 进 Extra;合法但不属于该类型的字段 → 映射到基字段或进 Extra;未知非字符串字段 → 丢弃;非法 linkMode → 400。→ `check_item.py` 仍然需要。
- `PATCH /items/:key` 带 `If-Unmodified-Since-Version` → 204;版本旧 → 412 并说明"expected X, found Y"。批量更新:对象带 `key` + `version`,失败逐条报告(412),其余照常写入。
- 文件上传三步:`POST /items/:key/file`(`application/x-www-form-urlencoded`:md5、filename、filesize、mtime 毫秒;`If-None-Match: *`;**filename 里的空格必须 %20 编码——Zotero 的表单解析不把 `+` 还原成空格**,2026-09-22 真实运行时文件名因此带了 `+`,已改 `quote_via=quote`)→ `{url, uploadKey}` 或 `{exists: 1}` → POST 字节到 `url`(`/api/local/uploads/<uploadKey>`,Content-Type 为文件类型)→ 201 → `POST /items/:key/file` 表单 `upload=<uploadKey>`(再带 `If-None-Match: *`)→ 204。读回 `md5` 一致,文件在 `storage/<key>/<filename>`,已全文索引;**不**按 Zotero 设置自动重命名(文件名 = 传的 filename),**不**触发识别器。附件须是 `imported_url` / `imported_file`;库须 `filesEditable`。
- `PATCH {"deleted": 1}` 移回收站(实测)。`POST /collections [{name}]` 建分类(实测,`tmp` 就是这么建的)。
- key 的保存位置:`~/.config/zotero/local-api-key`(JSON:key、serverID;0600;环境变量 `ZOTERO_LOCAL_API_KEY` 优先)。

### 3.3 `zotero` skill 的坑(本 skill 要提示 agent)

- `enable` / `disable` 在 WSL 下找不到 Windows 侧配置(报错无副作用;个人环境事实,不进 SKILL.md);**`restart` 会执行 `pkill -f zotero`,杀掉本机所有命令行含 "zotero" 的进程——包括本 skill 的脚本——且重启不了 Windows 侧的 Zotero**。其 SKILL.md 仍引导 `enable --restart` → 本 skill 必须明确覆盖:启动 Zotero / 开本地 API 是用户的事(gate)。
- 它的文档写 `python3 …`;它的脚本只依赖标准库,`uv run` 可用。本 skill 的示例直接写 `uv run`,SKILL.md 不解释 uv(那由别的 skill 和全局指令约束)。
- `collections` 给 key、name、parent——正是落点需要的;`tags` 给 tag + numItems,不带类型;`selected-target --json` 输出约 21 KB(大半是 tags),不需要。

### 3.4 浏览器侧

- OpenCLI 只碰网页内容,碰不到浏览器外壳(扩展图标——Zotero Connector 插件本身驱动不了、扩展快捷键、`chrome://`、PDF 阅读器按钮、"另存为"原生对话框)。
- Chrome 须设为"下载 PDF 文件"(用户已设;Preferences 里 `plugins.always_open_pdf_externally=true`);否则显示 PDF 的标签页无法接入(`attach_failed … chrome-extension://`——`opencli-browser` 文档对同一报错给的是 1Password 诊断,此场景以本 skill 为准)。设置开启后:顶层 PDF 导航 → 下载;iframe 内嵌 PDF → "打开"占位框,需导航到 iframe `src`。用户若开了"每次询问保存位置",点击后会弹原生对话框,表现为"没有触发下载"(gate)。
- `opencli browser <s> wait download <窄 pattern>`(2026-09-21 实测,arXiv PDF):下载前调用 → 超时不误报;`open <PDF url>` 后调用 → 命中,返回 Windows 路径(`C:\Users\…\Downloads\x.pdf`,用 `wslpath` 转)、`mime`、`totalBytes`、`state: complete`;完成后再调一次(同 pattern、空 pattern、不匹配的 pattern)都不再命中。→ 新下载的文件由它认出,不需要目录快照。`/mnt/c` 是 9p 挂载,元数据可能短暂陈旧。
- `opencli list -f json` 有 1.3 MB → 必须过滤(过滤后约 40 行);`opencli-usage` 指向的 `smart-search` skill 本机未安装。
- 文献相关适配器(2026-09-21 实查:共 1332 条命令 / 176 个站点;以运行时发现为准,SKILL.md 不写死):
  - **API 型**(`browser: false`——opencli 进程自己调公开 API,不经过 Chrome):`arxiv`(search / paper / author / recent;paper 给分类)、`openalex`(search / work;work 给摘要、关键词)、`semanticscholar`(search / paper / citations / recommendations;paper 接受 DOI 或 arXiv 号)、`dblp`(search / paper / author / venue)、`pubmed`(search / article / related 等 9 条)、`openreview`(search / paper / reviews / venue / author)、`hf paper`(按 arXiv 号取题目 / 摘要 / 作者)。
  - **浏览器型**(`browser: true`——在用户的 Chrome 里运行):`google-scholar`(search / cite / profile)、`baidu-scholar search`、`cnki search`(cookie,海外版)、`wanfang search`。
  - **没有**的:Crossref / doi.org、任何出版商站点(IEEE / Springer / Elsevier / Wiley / ACM)、PDF 下载、`papers.cool` → DOI→CSL 仍由 `doi_to_item.py` 直接调 doi.org;出版商页面仍是 `opencli browser`。
  - `papers.cool`(用户提供的检索面;无适配器;2026-09-22 subagent 调研,curl + 后台浏览器,约 25 次请求):**全站服务端渲染**(Caddy;列表 / 搜索页 25–40 KB,单篇 14 KB;页面不发站内 XHR),无 Cloudflare / 登录 / 限流迹象,curl 直连即可。搜索 = tantivy 全文引擎:`/arxiv/search?query=<词>&show=N&skip=N`、`/venue/search?query=…`(相关性排序;精确标题第一条即命中;**不索引作者名**;结果只有 HTML)。单篇 `/arxiv/<id>`(逗号可多篇)含 `citation_title / citation_authors / citation_pdf_url` meta 与 `div.panel.paper`(`a.title-link`、`p.summary` 摘要、`p#subjects-<id>` 学科、`p#date-<id>`、`sup#pdf-stars / kimi-stars` 热度);会议页 `/venue/<id>` 另有 `citation_publisher`(如 `NeurIPS.2025 - Spotlight`)、`citation_year`。列表 `/arxiv/<cat>?date=YYYY-MM-DD&sort=1`(sort=1 按 stars)、`/venue/<NAME>.<YEAR>?group=Oral`;Atom feed `/arxiv/<cat>/feed`、`/venue/<NAME>/feed`。Kimi 中文 FAQ 解读:`POST /arxiv/kimi?paper=<id>`(只取已缓存的;`/arxiv/star` 是计数接口,脚本不要调)。**没有 DOI**;会议只收录约 2021 年后的主流 ML 会议(CVPR、ICLR、ICML、NeurIPS 2021–25、MICCAI 2024–25…),无期刊(TMI、MedIA 没有),老论文只能作为 arXiv 记录找到。对本 skill:阶段 1 粗标题定位与会议核对的第一站(直接 fetch);DOI 另取。追热点 / 查某领域最新论文是另一件事,见 §11。
    - 仓库 `bojone/papers.cool`(2026-09-22 克隆查看;无源码,只有更新日志、官方 Zotero 翻译器 `Zotero/CoolPapers.js`、Chrome 扩展 "Cool Papers Redirector")和 issue 调研(subagent,约 60 条)补充的事实:**官方 Zotero 翻译器**从 `/arxiv/*`、`/venue/*` 列表页把卡片存成 `preprint` / `conferencePaper`(title、authors、abstract、PDF 附件、`extra` = 学科或 "NeurIPS.2025 - Spotlight"),等于官方给出的 DOM 选择器(`div.items > p`、`.title-link`、`.author`、`p.summary`、`.title-pdf[data]`、`p.subjects a`、`span.date-data`);会议单篇 id 格式 `<id>@OpenReview`、`<aclid>@ACL`、`<name>@v<NN>@PMLR`、`<n>@<year>@IJCAI`;类别代数 `/arxiv/cs.CV+eess.IV-cs.CL`(实测 200,Total 281)与并集 `cs.AI,cs.CL`;**搜索页有 Atom 订阅** `/arxiv/search/feed?query=…`(实测,1.8 MB)可监控关键词;`/venue/<会名>` = 最新一届、`/venue/<会名>/feed`、`/venue/latest/feed`;`?sort=1` 按 star、时间排序、[REL] = 用卡片 `keywords` 属性做同库搜索;搜索**无标题加权、无精确匹配**(#54),arXiv 与 venue 不能混搜(#53),历史按日列表仅 2024-01 起(#67);Kimi 解读按论文缓存、中英文两次独立生成,`POST /arxiv/kimi` 是第三方从前端反推的,**脚本不要调**(作者态度:个人用途直接解析 HTML 可以,反爬只针对恶意流量,#49/#69;star / kimi / config 端点别碰);收录标准 = 有免费持续 PDF 直链的会议(ACM / IEEE / Springer 系、期刊都不收,#88);没有官方 JSON API / MCP(#8)。**已有现成 skill**:`samonysh/papers-cool-search`(issue #104;MIT;2026-09-03 更新;Codex/Claude 两用):纯标准库 `scripts/papers_cool_fetch.py` 提供 `arxiv <cat-expr> [--date --sort --show]`、`venue <V.Y>`、`search <query> [--branch arxiv|venue]`、`related arxiv/<id>` 四种模式,解析卡片为规范 JSON(title、abstract、authors、subjects、published、source_url、papers_cool_url、keywords),自带礼貌预算(单并发、3 秒间隔、每会话 ≤20 请求、show ≤ 50、不调 star/kimi/config);2026-09-22 在 WSL 用 `uv run` 实测可用(venue 搜索 3 条 MICCAI 2025 超声论文,1 次请求);小瑕疵:作者列表重复一遍(卡片里隐藏的完整作者列表被解析了两次)。全网调研(subagent,2026-09-22):**没有**专门的 papers.cool MCP server / npm / PyPI 包,OpenCLI 上游(jackwener/opencli,约 190 个 adapter)无 papers.cool 且无 issue / PR;把它当数据源之一的项目里可参考的只有 RSSHub 的 `lib/routes/papers/`(生产验证的 DOM 选择器,`query.ts` 直接读搜索 Atom feed)和 ScholAI(反例:`show=1000` 对个人站点不礼貌);已缓存的 Kimi 解读 `GET /arxiv/kimi?paper=<id>` 即可读,未缓存的不要脚本触发。
  - `opencli web read --url <url>`:`browser: true`、`strategy: cookie`。默认把 Markdown 存到 `./web-articles/` 并下载图片——留下文件没关系(用户决定),取到需要的信息后删掉;让它落在工作目录里(`--output`),就随工作目录一起清。
  - 含义:API 型适配器省掉自己写 API 调用,但被拦时和 curl 一样失败(没有有头浏览器的优势),下一级是 `opencli browser`。doi.org 的记录常无摘要 → 先用 `openalex work` / `semanticscholar paper` / `hf paper` 补摘要,补不到再开文章页(省一次出版商访问和可能的 gate)。
- 访问权过期时出版商往往不弹登录页、只显示购买页 → agent 要主动点站点的机构登录入口,那之后才是 gate。
- 前台 `sleep` 在 Claude Code 里不可用;用 `opencli browser <s> wait time N` 做间隔,整个轮询放在一次长超时的 shell 调用里(OpenCLI 单命令默认超时 60 秒、Bash 工具默认 120 秒,都要调大)。
- IEEE 全链路已实测通过(M2Trans);其他出版商未验证。

### 3.5 doi.org 内容协商(`Accept: application/vnd.citationstyles.csl+json`,实测)

| 来源 | 结果 |
|---|---|
| Crossref 期刊 | 200;`type` 是 **Crossref 词表**(`journal-article`),不是 CSL;`container-title` 为字符串;常无摘要;DOI 小写 |
| Crossref 会议(CVPR) | `proceedings-article`,有 `event` |
| LNCS 章节(MICCAI / ECCV) | `book-chapter`,`container-title` 是丛书名 |
| arXiv(DataCite,`10.48550/arXiv.<id>`) | `article`;有摘要;DOI 大写;无 `published`;**无分类** |
| mEDRA | `article-journal`(真正的 CSL 类型) |
| ISTIC / CNKI | **200 + text/html**(内容协商被忽略) |
| 不存在 | 404 html |

→ 类型映射要同时覆盖 Crossref 词表与 CSL 词表(后者取自 `/api/schema`);未知类型要显式报告;必须检查 Content-Type;DOI 比对不区分大小写。**来源关键词不在这里**:Crossref 的 `subject` 是期刊的学科分类,不是作者关键词——作者关键词来自文章页(`citation_keywords` meta、IEEE 的 `xplGlobal.document.metadata.keywords`)或 `openalex work`;arXiv 分类来自 `arxiv paper` 适配器或 arXiv API。所以 `doi_to_item.py` 不写 tags,来源关键词由 agent 在阶段 3 收集。

### 3.6 Zotero 的"自动为 PDF 检索元数据"

- 用户把 PDF 拖进 Zotero 后过一会儿自动出现的父条目,来自设置 → 常规 → **"自动为 PDF 检索元数据"**(pref `autoRecognizeFiles`;右键菜单里叫"检索 PDF 元数据"):Zotero 抽取前几页文本,找 DOI / arXiv ID / ISBN,找不到就把文本指纹发给 Zotero 的识别服务去匹配 Crossref,然后用对应的翻译器建父条目——arXiv 学科分类标签、出版商关键词就是翻译器这一步带进来的;随后按设置自动重命名文件。触发点(源码):UI 的拖放 / 添加文件,以及 connector 的 `saveStandaloneAttachment`;本地 API 上传不触发。
- 对本 skill 的正常路径没有增益:agent 在阶段 1 已经拿到 DOI / arXiv 号,`doi_to_item.py` 用的是同一来源(Crossref / DataCite),直接、key 已知、可核对;识别器慢、异步、建出的条目还得再去找,认的是 PDF 里印的那个标识符(arXiv 版 PDF 就建成 arXiv 记录,即使用户要的是正式版),失败时 PDF 以独立附件留在库里。
- 有用的两处:(1) 用户自己拖进去的 PDF 已经带识别器给的元数据 → 整理入口在其上补标签、归类;(2) **没有 DOI 记录的 PDF**(老论文、首页没 DOI):识别器的指纹匹配是 agent 没有的能力 → 退路见 §4"无 DOI 记录"。

## 4. 架构:稳定的是交付物,可替换的是工具

| # | 阶段 | 完成标准(可检查) | 工具 |
|---|---|---|---|
| 0 | 准备 | Zotero 在线(`/connector/ping`)、本地 API 可读、key 可用(否则各是一个 gate:开 Zotero / 开本地 API / 授权);工作目录已建;上次遗留已**汇报**(不擅自删,见"续跑") | `zotero` skill 的 `status`;`authorize_local_api.py`;固定工作目录 `${TMPDIR:-/tmp}/paper-to-zotero/`、固定 session 名 `p2z` |
| 1 | 锁定论文 | 标识符能解析出记录且题目与候选一致;用户请求里每个有区分度的词都对得上;没有别的结果同样吻合——否则列候选问用户 | agent 判断,按 §2.2 的阶梯:元数据 API / API 型适配器(`arxiv`、`openalex`、`semanticscholar`…)→ 浏览器型适配器(`google-scholar`,用户习惯的检索面)→ `opencli browser`。Scholar 出人机验证 = gate:适配器是一次性命令、失败时标签页已关,所以用 `opencli browser` 在前台重开该搜索页 → 提醒用户 → 等 5 分钟 → 重试 |
| 2 | 查库与落点 | 库里没有(标识符 + 题目);落点 = 一个分类 **key**:用户点名或确认过的,定不下来则临时分类(U10) | `find_in_library.py`;分类树用 `zotero` skill 的 `collections`(key、name、parent),路径 → key 由 agent 判断 |
| 3 | 起草条目与标签 | `check_item.py` 对 item.json 输出 ok;摘要已填,或适配器、文章页与 arXiv 记录都看过确实没有;tags.json 已按 `references/tagging.md` 定好:来源关键词(type 1)+ agent 的标签(type 0) | `doi_to_item.py` → agent 修订 → `check_item.py`;无 DOI / 无 CSL 记录则手写(骨架见 `check_item.py --help`)或走"无 DOI 记录"退路;摘要与来源关键词先用适配器补(§3.4、§3.5);已有标签词表 = `zotero` skill 的 `tags` |
| 4 | 拿 PDF | PDF 在工作目录里;`check_pdf.py` ok,或 agent 读了摘录判定是这篇(汇报中注明) | 开放仓库直接下;出版商:§2 的访问阶梯 + gate;认出新下载的文件:`opencli browser p2z wait download <窄 pattern>`(返回 Windows 路径 → `wslpath`),再移入工作目录 |
| 5 | 存入、归类、打标签 | `create_item.py` 输出 `item_key`,读回的 `collections` 含目标 key、`tags` 与发送的一致;`attach_file.py` 输出 `attachment_key`、`md5_ok: true` | 本地写 API(U13):`create_item.py --item item.json --collection K --tags-file tags.json`(POST,一次落到位)→ `attach_file.py --key <item_key> --pdf … --pdf-url …`(三步上传 + 读回 md5) |
| 6 | 清 residue | 工作目录不存在;`p2z` 不在 session 列表里;下载目录里没有本次运行产生的文件;清不掉的已在汇报里点名 | agent |
| 7 | 汇报 | 见 §6 | agent |

换检索工具不影响 2–7;换下载方式不影响 5;换写入通道只替换 `create_item.py` / `attach_file.py`;`file_and_tag.py` 只用于已有条目(重新归类、改标签、整理、识别退路的归位)。

**落点规则(U2 + U10)**:用户点名了分类 → agent 在 `zotero collections` 的树里定出唯一 key(歧义 / 不存在 → 列候选路径问用户)。没点名 → agent 按论文主题**建议**一个,问用户确认或改;需要问候选时把两个问题合并成一轮。**推荐不出来,或没人可问**(用户不在、批量运行中不便打断)→ 放进临时分类 **`tmp`**,汇报里提示用户之后再归类(不存在 → agent 经本地 API `POST /collections` 建一次,不写脚本)。"近期"是用户这段时间常看的文章,不是收件箱,不要当落点。落点**总是显式**传给 `create_item.py`(新建)或 `file_and_tag.py`(已有),因此不受"Zotero 当前选中"以及 gate 等待期间用户点别处的影响。

**续跑(复审 #2)**:gate 超时后用户说"继续" = 从中断的阶段重入(通常是阶段 4),不重跑阶段 0,不清工作目录和 `p2z`。操作都在用户日常使用的 Chrome 里,登录状态保存在浏览器里:标签页即使被关掉(包括 OpenCLI 对自有 session 的空闲自动关闭,时长文档未写),重开后登录仍在——保留标签页是为了让用户接着操作,不是为了保状态;只有用户不在、或他那边的登录自己超时了,才需要重新过 gate。阶段 0 遇到上次遗留:只汇报;含 PDF 的目录不擅自删(没进库的 PDF 是交付物)。

**无 DOI 记录(阶段 3 的退路)**:PDF 已拿到、但 doi.org / 适配器都给不出记录(老论文、首页没 DOI、CNKI 这类内容协商失效的)→ 把 PDF 经 connector `saveStandaloneAttachment` 送进库(先记库版本 v0)→ 等识别(`wait time 15` 后 `since=v0` 看有没有新父条目,最多等 60 秒)→ 有:读它的 JSON,agent 补摘要 / 修正,`file_and_tag.py --key` 归位、打标签(自动标签已由翻译器带上)→ 没有:把独立附件移回收站,手写 item.json 走正常的 `create_item` + `attach_file`。识别器认的是 PDF 里的标识符,arXiv 版会建成 arXiv 记录——用户要正式版时按 §6"正式版与预印本"处理。

**开放仓库按行为定义**:能向普通 HTTP 客户端直接给出 PDF 的站点(arXiv、CVF Open Access、OpenReview、PMLR…)。直接下载拿到的不是 PDF → 改走出版商分支。出版商平台上的 OA 文章仍算出版商主机。

### 退出路径表(阶段 6)

| 退出路径 | 处理 |
|---|---|
| 成功 | `attach_file.py` 读回 md5 一致之后:删工作目录(含 PDF)、关 session |
| 库里已有,**有**附件 | 没下载东西;关掉可能打开的 session;告诉用户已有条目的 key 和分类;用户要求的话可以对它重新归类 / 补标签(`file_and_tag.py`) |
| 库里已有,**无**附件 | 照常拿 PDF → `attach_file.py --key <已有条目>` → 清理 |
| 走过 gate 仍拿不到 PDF、也没有预印本(机构没订阅) | **仍然存条目**(U14):`create_item.py` 照常归类、打标签,汇报注明无 PDF 及原因;不绕付费墙、不反复试 |
| gate 超时 | **保留标签页**,汇报哪一页在等,请用户通过后说"继续"(见"续跑");处理列表时**在此停下整个列表** |
| 只建了条目、PDF 没挂上 | 条目已在库里(key 已知)→ 只重跑 `attach_file.py --key`,**不重建条目**;仍失败 → PDF 交给用户(放回下载目录并报路径),汇报条目 key |
| 建条目本身失败(`failed` 里有报错) | 本地 API 会说明原因(字段非法等)→ 改 item.json 重试;没有半成品 |
| 识别退路失败 | 独立附件移回收站;PDF 仍在工作目录 → 手写路径 |
| 清不掉的 | 在汇报里点名并给位置 |

安全条件:只删本次运行创建的东西;PDF 只在 Zotero 确认有附件后才删;对已有条目的改动(整理时)先给用户看清单再写。

## 5. 组件

```
paper-to-zotero/
├── SKILL.md
├── references/
│   ├── publishers.md             # 第一次碰出版商主机之前读
│   └── tagging.md                # 标签规范(U4 / U7 / U11):保留什么、补什么、格式;导入与整理共用
└── scripts/                      # PEP 723 + `uv run`;各自独立(不互相 import);stdout 为 UTF-8 JSON
    ├── authorize_local_api.py    # 写(一次):取本地写 API 的 key 并保存
    ├── find_in_library.py        # 读
    ├── doi_to_item.py            # 读(doi.org + Zotero schema)→ 写出 item.json
    ├── check_item.py             # 读
    ├── check_pdf.py              # 读文件(只报事实)
    ├── create_item.py            # 写(本地 API):新建条目,带落点与标签 → key
    ├── attach_file.py            # 写(本地 API):给任一条目挂 PDF 或网页快照(新建的、已有的都一样)
    └── file_and_tag.py           # 写(本地 API):已有条目的归类 + 标签(整理入口也用它)
```

不写的(探针后确定):`new_downloads`(`wait download` 已可靠)、`resolve_collection`(`zotero collections` 已给 key)、`verify_saved`(key 由 create 直接返回)、connector 版的写脚本(后备设计,§3.1)。

**通用约定**:退出码 0 = 通过;1 = 不通过,交给 agent 判断;2 = 无法检查(Zotero 不可达 / 本地 API 403 / 没有 key / key 属于别的实例,要区分)。输出含稳定的 `code`;`hint` 只在失败 / 分支时出现,用本 skill 的词汇说下一步,不复述 `references/publishers.md` 的症状表。参数以各脚本 `--help` 为准;SKILL.md 每个脚本只给一条典型调用,并注明"脚本路径相对 SKILL.md 所在目录"。与别的 skill 重叠的脚本写明**退役条件**——它们会自己更新,缺口补上了本脚本就该删。写本地 API 的脚本从同一位置读 key(见 `authorize_local_api.py`);**key 永远不进仓库、不进 SKILL.md、不进汇报**。写脚本都有 `--dry-run`(只跑预检)。

| 脚本 | 做什么 | 要点 |
|---|---|---|
| `authorize_local_api.py` | 取得并保存本地写 API 的 key(一次) | 已有 key 且 serverID 匹配 → 直接报 ok。否则 `POST /api/local/authorize`(带 `Zotero-Server-ID`)→ Zotero 弹授权框 = **gate**:调用前提醒用户点 **Always Allow**(Allow 的 key 一次性,不够用),请求会挂到用户点击(超时 5 分钟)→ key 与 serverID 存到 `~/.config/zotero/local-api-key`(0600);环境变量 `ZOTERO_LOCAL_API_KEY` 优先。429 → 授权弹框限流,等 `Retry-After`。其他写脚本缺 key → 退出码 2 + hint "先授权";412 → key 属于别的 Zotero 实例 → 重新授权 |
| `find_in_library.py --doi/--arxiv/--title` | 库里有没有这篇 | 标识符用 `qmode=fields` 再精确比对 `data.DOI` / `url` / `archiveID` / `extra` 里的 arXiv 号(不区分大小写);题目用分词检索 + Unicode 归一化比对;输出 key、题目、itemType、DOI、附件数、**分类路径**、现有标签。预印本与正式版视为同一篇的另一版本,交给 agent 问用户。**退役条件**:`zotero` skill 的 `search` 能按标识符(`qmode=fields`)查询并给出附件数与分类路径 |
| `doi_to_item.py --doi --out item.json` | DOI → item.json 草稿 | 输入容错(`doi:` 前缀、URL、尾随标点、需 URL 编码的老 DOI);检查 Content-Type(200 + HTML → `no_csl_record`);类型映射 = Crossref 词表小表 + `/api/schema` 的 `csl.types`,未知类型 → `unknown_type` 显式报告;`container-title` / `title` 字符串或列表都接受;`author.literal` → 单字段作者;JATS 摘要去标签;arXiv → `preprint` + `repository: arXiv` + `archiveID`,DOI 规范成 `10.48550/arXiv.<id>`;`issued` 可能只有年份。**不写 tags**(Crossref 的 `subject` 不是关键词,§3.5) |
| `check_item.py --item item.json` | 保存前看清会发生什么 | 对照 `/api/itemTypeFields`:未知 `itemType` → 不通过(本地 API 400);其余分三类报告——**会被映射**到基字段 / **会进 Extra**(未知字符串字段、不属于该类型的字段)/ **会被丢弃或改写**(非字符串未知字段、非法 creatorType)——本地 API 与 connector 同样宽松(§3.2);自定的最低要求:title、creators、date、DOI 或 url、出处;`--help` 给 item.json 骨架(手写分支用) |
| `check_pdf.py --item item.json --pdf x.pdf` | 报告这个 PDF 的事实 | **只报事实,不打分**:`%PDF-` 头;有无文本层 / 是否加密(`no_text_layer`);首页摘录;首页是否含 "Supplementary"。唯一的判定规则:归一化(NFKC、去标点、小写)后的题目**整串**出现在首页文本里 → ok;否则退出码 1 + 摘录,由 agent 判断。不设可调阈值。题目从 item.json 读(避免命令行引用出错)。没有文本层时的退路:agent 直接读 PDF 首页(`pdf` skill)。只依赖标准库:文本层用最朴素的 PDF 流解析(FlateDecode + 括号 / 十六进制字符串),解析不出 = `no_text_layer`,不装 pdf 库 |
| `create_item.py --item item.json --collection K --tags-file tags.json --out saved.json` | 新建条目(本地 API) | 预检:本地 API 可读、key 可用且 serverID 匹配、item.json 至少有 itemType / title、`--collection` 的 key 存在(不存在 → `code: collection_not_found`)。`POST /items` 一个对象,JSON 里带 `collections: [K]` 与完整 `tags`(`{tag, type}`)→ `successful.0.key`;`failed` 有内容 → 退出码 1,原样报告 message。读回比对 `collections` / `tags`。写出 `saved.json`(item_key、version、collection、tags)。**不重试**创建——失败时没有半成品 |
| `attach_file.py --key K --pdf x.pdf --pdf-url URL [--filename …]` | 给条目挂 PDF(新建的、已有的一样) | 预检:`%PDF-` 头、pdf-url 非空(回落 `https://doi.org/<DOI>`;存规范地址,不存 EZproxy 主机名)、`filesEditable`、父条目存在且没有同 md5 的子附件(有 → `code: already_attached`,退出码 0,不重复)。POST 子附件(`imported_url`、`contentType: application/pdf`、`filename`、`title: "PDF"`)→ 三步上传 → GET 读回 `md5` 比对 → `attachment_key`、`md5_ok`。文件名由调用方定(本地 API 不自动重命名):默认按 Zotero 默认模式 `<第一作者姓> - <年> - <题目>.pdf`(从父条目 JSON 取,截断到合理长度、去掉非法字符)。上传中断时子附件条目可能已建而无文件 → 重跑先找同 `filename` 且无 md5 的子附件复用,不再新建 |
| `file_and_tag.py --key K [--collection COLLKEY] [--tags-file tags.json]` / `--batch changes.json` | 已有条目的归类 + 标签 | 先 GET 取 `version`、现有 `collections` / `tags`,再 `PATCH`(`If-Unmodified-Since-Version`;412 → 重新 GET 再试一次)。`collections` 设为目标(= 移动;不传则不动);`tags-file` 是**完整的目标标签集**(`{tag, type}`),脚本算差异、报告 `tags_added / tags_removed`,读回比对 → `filed` / `tags_ok`。设的是目标值,重跑无副作用。`--batch`:多对象 POST,≤50 条/次,每条带 `version`,失败逐条报告,输出每条的结果;整理全库(148 条)= 3 次请求 |

**不写成脚本的**:检索与打分;路径 → 分类 key(读 `zotero collections` 即可);选标签、收集来源关键词、修正关键词(按 `references/tagging.md`,agent 判断);建 `tmp`(一条 POST);识别新下载(`wait download`);读旧条目(整理时:本地 API GET 或 `zotero` skill);访问回落与补缺失信息(§2.2 访问阶梯——prompt 讲原则,agent 判断);gate 轮询(SKILL.md 给一条典型调用;先试 `wait selector/text --timeout`,不行再轮询);清理;开放仓库的直接下载;无 DOI 记录时经 `saveStandaloneAttachment` 让 Zotero 识别(一条 curl,SKILL.md 给示例)。

### SKILL.md 大纲(按 writing-for-agents)

```
frontmatter description
# Paper to Zotero      契约两行;脚本路径相对本文件所在目录;写库授权一句;本地 API 的 key 在哪、缺了先授权
## Instruments         四个 skill 各一行(zotero、opencli-usage、opencli-browser、pdf:何时打开 + 用到的子命令名);
                       "第一次碰出版商主机前读 references/publishers.md";"选标签前读 references/tagging.md";
                       覆盖 zotero skill 的 enable/restart 建议
## Steps 0–7           每步:做什么 + Done when + 本任务特有的提示(含"无 DOI 记录"退路)
## Rules               够到页面(访问阶梯 → 已知会拦的主机从 OpenCLI 开始 → gate:定义、先提醒、前台、等 5 分钟、
                       通过的判据、超时与续跑)/ Residue(枚举、例外、退出路径表)
## Several papers      先全部锁定并一次问完(候选 + 落点);逐篇 2–7;单篇失败(拿不到 PDF、保存失败)不中断,
                       唯一的例外是 gate 超时——停下整个列表;汇总表
## Organize            第二入口(整理已有条目):读全库 → 按 tagging.md 逐条拟定标签 / 分类 →
                       变更清单(尤其删除、改名)给用户确认 → 分批写(--batch,≤50 条/次)→ 汇报
## Limits              本地 API 上传不自动重命名文件(脚本自己起名;用户可在 Zotero 里"从父条目元数据重命名");
                       识别器只能经 connector 触发;不新建分类(tmp 除外)
```

提示的写法(复审 #9、#11、#12):
- "real navigation"、访问阶梯、gate 讲的是同一件事——怎么够到网页——在 SKILL.md 里合成一块,不分三处。
- 示例命令直接写 `uv run …`,不解释 uv。个人环境事实(WSL、学校、代理)不进 SKILL.md。
- opencli 的命令每处只留一条示例,标明"典型调用,语法以 opencli-usage / opencli-browser 为准"。
- **已经明确的做法和适配器要提示**(用户要求):`google-scholar` 适配器(用户习惯的检索面);`openalex work` / `semanticscholar paper` / `hf paper` 补摘要与关键词;`arxiv paper` 取分类;`opencli web read`;`--window foreground`;`wait download` 传窄 pattern;IEEE 的已验证流程(在 publishers.md)。都写成带日期的提示,以运行时发现为准。

description(草案):
> Imports one paper into Zotero as an item with its PDF attached, filed and tagged, from a title, keywords, DOI, arXiv id, or URL; on request, organizes the existing library's tags and collections. Use when the user wants a paper added to Zotero (把论文/文献导入 Zotero) — also when they do not mention the PDF — or wants their Zotero tags/collections tidied (整理 Zotero 标签/分类). A .bib/.ris file the user already has goes through the zotero skill instead.

引导词:**gate**(动词统一为 "wait at the gate")、**residue**、**fall back**(访问阶梯)。少用否定句;唯一保留的硬护栏是 curl 出版商主机、`zotero restart`、整理时未经确认不删,都配正向目标。开头不写"指挥 / 乐器"式的说明文字(no-op),只写何时打开哪个 skill。

`references/publishers.md`:Chrome PDF 设置;OpenCLI 的边界;`attach_failed` 的诊断覆盖;gate 的几种不典型形态(Chrome 没开或 OpenCLI 扩展没连上;点了下载却弹出系统"另存为"对话框——都是用户几秒钟能解决的事,提醒他);已验证出版商(IEEE:PDF 按钮 `a[href*='stamp.jsp']` → 阅读页 iframe `stampPDF/getPDF.jsp`;摘要与关键词在 `xplGlobal.document.metadata`;登录后可能经 EZproxy 主机名)与未验证预期(Springer / Nature、ScienceDirect、Wiley);PII→DOI(Crossref `filter=alternative-id:<PII>`);唯一的一份症状表。新出版商的经验写进**汇报**的 "publisher notes",由用户决定是否收录;运行中不改 skill 仓库。

`references/tagging.md`:已草拟(2026-09-21,通用文本);用户库特有的约定(`tmp`、"近期"的含义、现有手动标签的去向)只在 `.memory/`。

## 6. 需要 agent 判断或问用户的时刻

| 时刻 | 做法 |
|---|---|
| 多个候选 / 没把握 | 列前几名(题目、作者、年份、出处)问用户 |
| 没点名分类 | 按主题建议一个,问用户(U2);与候选问题合并成一轮。推荐不出来或没人可问 → `tmp`,汇报里提示(U10) |
| 选标签 | 按 `references/tagging.md`:来源关键词(作者关键词、arXiv 分类)保留、修正明显错误的;补 method / task / modality / dataset / 常用名 / 出版物简称;优先复用库里已有的,新建的在汇报里列出 |
| 正式版与预印本 | 条目描述阶段 1 锁定的版本,默认正式版。正式版没有 DOI(NeurIPS / ICLR 等):用 arXiv DOI 起草,按落地页改 `itemType` 与会议字段,arXiv 号放 `extra`。LNCS / MICCAI / ECCV 章节默认成 `bookSection`,通常应改 `conferencePaper`。手里是 arXiv 版 PDF 而已知正式发表处 → 两个简称都打(U12) |
| 库里有同一论文的另一版本 | 视为"已有",问用户 |
| 库里已有且无附件 | 拿 PDF 挂上去(`attach_file.py`) |
| 无 DOI 记录 | 走 §4 的识别退路;识别失败则手写 |
| 购买页而非登录页 | 先点机构登录入口、在 gate 前等过;之后才谈替代 |
| Chrome / OpenCLI 扩展没连上;弹出系统"另存为"对话框;Zotero 弹本地 API 授权框 | 也是 gate:提醒用户,几秒钟的事 |
| 走过 gate 仍拿不到 PDF | 有预印本 → 用预印本并在汇报注明;没有 → 问用户:只存条目还是放弃(U3) |
| `check_pdf` 不通过 / 无法判定 | 读摘录:是这篇 → 继续并注明;不是 → 回到拿 PDF |
| 整理时要删或改已有标签 | 先列清单给用户确认,再写 |
| gate 超时 | 保留标签页,问用户 |

汇报内容:题目 / 作者 / 年份 / 出处;`item_key`、附件 key、`zotero://select/library/items/<key>`;分类路径(落在 `tmp` 时提示用户之后归类);标签(保留的来源关键词、修正的、新加的、其中新建的);替代项(预印本 PDF、凭摘录接受的 PDF、经识别退路建的条目、因无来源留空的字段、被映射 / 进 Extra / 被丢弃的字段);residue 一行;publisher notes。

## 7. 用户的决定(2026-09-21)

| # | 问题 | 决定 |
|---|---|---|
| U0 | item.json 由谁起草 | 脚本起草 + agent 修订 |
| U1 | 写入通道 | 原定 connector(插件同款);v8 起新建条目也走本地 API,见 U13 |
| U2 | 没点名分类时 | **agent 按主题建议一个分类,再问用户**;点名时直接归入 |
| U3 | 走过 gate 仍拿不到 PDF | 有预印本就用并注明,否则问用户 → **U14 修订(2026-09-22)**:机构没订阅时**不问,直接存无 PDF 的条目**并注明("即使没有PDF,还是需要保存文献到Zotero里面的"),用户之后可用 `attach_file.py` 补;识别"没订阅":购买页、无 "Access provided by"、机构登录后仍如此 → 停止尝试,小心不要绕付费墙 |
| U4 | 出版商关键词 | **保留**——它们就是论文自己的关键词(自动标签类型,与浏览器插件一致);**arXiv 学科分类也保留**;agent **修正明显错误的**——出版商自动生成的索引词(IEEE 的 `Training`、`Task analysis`…)是整理时的待删候选,用户在清单上勾选;拼写变体合并。(v4 一度提议不再入库,用户否决) |
| U5 | 人机验证、登录、页面问题(含 Google Scholar) | **都按 gate 处理**:不关、不绕开,提醒用户帮忙,等 **5 分钟**(原 3 分钟);Scholar 只经 OpenCLI 访问。取代原设计"Scholar 出验证码就换检索面,不等用户" |
| U6 | 访问失败 / 信息缺失时 | **自动回落,不停下**:直接访问 → OpenCLI 适配器;API 型适配器失败 → `opencli web read` → `opencli browser` 自己解决 → gate(提醒用户,给处理时间);浏览器型适配器失败 → 前台重开该页,被拦就提醒用户。可用的工具都可以试。**回落写成 prompt 交给 agent 判断,不写脚本去规范** |
| U7 | 每篇文献的标签 | **由 agent 管理**(用户:"现在也是野蛮生长,根本不清楚怎么个标签")。在保留的关键词之上**补充**:方法、任务、模态、数据集;论文的**常用名**(讨论时一说就知道是哪篇,题目里却没有,如 CycleGAN);**发表处的简称**(CVPR、ICML、ICLR、ACL、NeurIPS、AAAI、MICCAI、TMI、MedIA、JBHI、TIM、npj Digital Medicine、NC、Nature Medicine…)。方向:用户检索方便。规范在 `references/tagging.md`;已有的 148 条在 skill 做完后由 agent 整理一遍 |
| U8 | 落点定不下来时 | 放进临时分类,汇报里提示用户之后再归类(名字见 U10) |
| U9 | 本地写 API | **随时可用,不是负担**(用户原话);"可以完全使用本地写 API"。agent 可随时向用户申请授权;key 永久保存——位置由设计者定:`~/.config/zotero/local-api-key`(仓库外;环境变量 `ZOTERO_LOCAL_API_KEY` 优先)。由此:归类 / 标签走本地 API(取代 `updateSession`,新旧条目通用);给已有条目挂 PDF、整理全库进入 v1 |
| U10 | 临时分类 | 名字 **`tmp`**(用户确认,不用"未分类条目";已建,key `RIBA5MZJ`)。"近期"里放的是用户这段时间常看的文章,不是收件箱 |
| U11 | 标签格式 | 前缀**不用中文**:`method/`、`task/`、`modality/`、`dataset/`,值用该术语的通行写法;常用名与出版物简称不带前缀。草案 `paper-to-zotero/references/tagging.md`,待用户过目 |
| U12 | 整理入口的打包;预印本的简称 | 整理入口 = 同一 skill 的第二入口;arXiv 版且已知正式发表处 → `arXiv` 与该简称都打 |
| U14 | 机构没订阅、没有 PDF | 仍存条目(见 U3 修订);**并把文章页存成快照挂上**(用户 2026-09-22:"把网页存下来,看看网页上能不能读到一些信息并补充上",与 connector 无 PDF 时存快照的行为一致)→ `attach_pdf.py` 改名 `attach_file.py`,接受 PDF 或 .html |
| U13 | 新建条目的通道 | v6 本地 API → v7 因设计者误读"限流 5 次/分钟"改回 connector → **v8 纠正:本地 API 没有写限流**(§3.2),两条通道都实测通过,**新建条目走本地 API**:一条通道、一次授权、key 直接返回、错误显式、落点与标签随创建一次写入、无 session。代价:文件不自动重命名(脚本自己按 Zotero 默认格式起名)。设计者据探针结果修订,用户已看过 |

**按用户原则的复审(2026-09-21,15 条,用户逐条决定)**:#1–#9、#11–#15 采纳——#1 核实与写入分离(v9 里 key 由 POST 直接返回,不再需要单独的核实脚本);#2 续跑;#3 归类没成的退出路径(用户另加 U8 临时分类);#4 归类独立成脚本,用户希望借此也能整理已有文献,U9 之后经本地 API 做到了;#5 列表只在 gate 超时时停下;#6 `new_downloads.py` 先探针(P1 通过,不写);#7 `check_pdf.py` 只报事实;#8 退役条件;#9 三条规则合成"够到页面";#11 不解释 uv、个人环境事实不进 SKILL.md;#12 opencli 命令只留示例,但已明确的做法和适配器要提示;#13 阶段 6 的完成标准可检查;#14 gate 的不典型形态;#15 探针先行。**#10 不采纳**:把访问阶梯写进全局指令——那是设计 skill 时的原则,不该落到 skill 使用者头上。

设计者自定:skill 名 `paper-to-zotero`;库里已有且有附件 → 停下汇报;gate 超时 → 保留标签页并问;key 的保存位置(U9);来源关键词由 agent 在阶段 3 收集(§3.5)。

## 8. 验证计划

0. 探针 P0–P6:**已全部跑完**(2026-09-21,§12)。
1. 脚本单测(不写库、不动浏览器):每个脚本的成功与失败路径;写脚本的 `--dry-run`。
2. **真实运行一篇**——**已完成(2026-09-22)**:用户 ref.bib 里的 Liu et al. 2022 JBHI(10.1109/JBHI.2022.3142076,IEEE 付费):doi_to_item + OpenAlex 补摘要 → check_item ok → IEEE 经 EZproxy 登录(gate,用户登录)→ `xplGlobal.document.metadata` 取作者关键词 → stamp.jsp → getPDF.jsp → `wait download 9684683` 命中 → check_pdf ok(页面树)→ create_item(`4L562S9K`,医疗图像,4 个来源关键词 + `method/CNN`、`task/Super-resolution`、`modality/Ultrasound`、`JBHI`)→ attach_pdf(md5 一致)→ 清理。发现并修复一个 bug:上传表单的 filename 空格被 `urlencode` 编成 `+`,Zotero 原样保存(§3.2);删掉错名附件后用修好的脚本重挂(`B4K98DC7`)。教训:gate 提醒必须推送(§2.6)。
3. 新 agent 演练——**已完成(2026-09-22)**:subagent 只凭 SKILL.md 导入 ref.bib 里的 Lyu et al. 2023 ARU-GAN(Computers in Biology and Medicine,10.1016/j.compbiomed.2023.107316)→ 条目 `DD3XXKVS`,医疗图像,5 个作者关键词(PubMed)+ `method/GAN`、`task/Super-resolution`、`modality/Ultrasound`、`dataset/PICMUS`、`Comput Biol Med`;**无 PDF**——ScienceDirect 明示机构未订阅,无开放副本,按 U14 存条目。交付了 18 条摩擦日志,已全部改进文档:cwd 与工作目录、zotero helper 的 uv 调用、Crossref 一行钉论文、pubmed 补摘要 / 关键词 / PMID、作者关键词 ≠ MeSH / 索引词、期刊无社区缩写用 NLM 缩写、gate 靠标志识别且提醒先于一切、subagent 用 SendMessage 提醒主会话、ScienceDirect 的 Turnstile 与"未订阅"识别、无订阅走无 PDF 分支、`close` 的判据与 Downloads 检查方法、UNDICI 警告。两个 gate 事件:Turnstile 出现时 agent 没先提醒(用户先看到),购买页时按规则提醒并等到了用户的决定。
4. 收尾:README skills 列表加一行;根 AGENTS.md 不动;不自动 commit / push。
5. **整理已有条目**(skill 设计、实现完成之后):148 条 → **按分类分批**(先做一个中等大小的,如"自然图像 / Diffusion" 10 条):每批先 dry-run 出变更清单(保留 / 修正 / 删除 / 新增,按条目)给用户确认 → `file_and_tag.py --batch` 写 → 汇报。第一批是校准:用户看了实际效果再定规范细节(前缀、粒度),后面的批次才照做。

## 9. 明确不做(v1)

检索 / 打分代码;出版商专用下载器;对 `zotero` / `opencli` 命令的二次封装;清理脚本;访问回落脚本;新建分类(`tmp` 除外);`--note`;connector 版的写脚本(后备设计,§3.1;需要时再写);把独立附件重新挂到手写条目下(`parentItem` 的 PATCH 未实测,识别失败时直接移回收站走正常路径)。

## 10. 交接状态

- 本 spec 在仓库 `docs/specs/20260921-paper-to-zotero-spec.md`(未提交);实现完成后冻结(见根 `AGENTS.md`)。
- `paper-to-zotero/` 已按本 spec 实现(2026-09-22;全部未跟踪、未提交):`SKILL.md`(按 §5 大纲重写,通用文本)、`references/publishers.md`(重写)、`references/tagging.md`(待用户过目)、`scripts/` 8 个脚本(4 个 subagent 并行编写,每个都有 mock 测试和只读 live 测试;冒烟测试:`--help` 全通过,真实 DOI 走完 find → doi_to_item → check_item → check_pdf,三个写脚本 `--dry-run` 对实库通过,库版本不变)。README 已加一行。旧的 `save_with_pdf.py` 已删。
- 实现时发现、与 spec 表不同或超出的地方(参数以各脚本 `--help` 为准):`find_in_library.py` 把未经精确确认的标识符子串命中也报成 `near_match`(带 reason);`qmode=fields` 是子串匹配;本地 API 对不存在的 key 请求 `/children` 会返回 200 加别的条目的子项(脚本按 `parentItem` 过滤)。`check_pdf.py` 经页面树定位第一页(arXiv PDF 的第一页内容流在文件末尾,文件顺序不可靠),并处理 TeX 连字;仍不处理 CID 字体。`doi_to_item.py`:journalArticle 不写 publisher(与 Zotero 自带导入一致);`10.1109/TMI.2024.3375871` 在 doi.org 是 404,别拿它当示例。`create_item.py` 多了 `readback_mismatch`(条目已建,用 file_and_tag 修)、`post_incomplete`(连接中断,先查库再重建)。`attach_file.py` 用文件自身 mtime;`--dry-run` 也要 key。`file_and_tag.py` 的 tags 是完整目标集(只传新标签会删掉来源关键词);批量模式任一 key / 分类不存在则整批不写;批量 412 不重试。
- 本地写 API **已授权**(2026-09-21,Always Allow),key 在 `~/.config/zotero/local-api-key`;`tmp` 分类**已建**(key `RIBA5MZJ`)。
- 源码对照用的 clone 在本会话的 scratchpad(会被清理);重新获取:`git clone --depth 1 --branch 10.0.3 --filter=blob:none --sparse https://github.com/zotero/zotero` 后 `git sparse-checkout set chrome/content/zotero/xpcom`。关键文件:`xpcom/server/server_localAPI.js`(写协议、上传)、`server_connector.js`(`saveStandaloneAttachment` 与识别触发)、`xpcom/data/item.js`(`fromJSON` 的宽松规则)。
- 2026-09-22 真实导入的两条:`4L562S9K`(Liu 2022 JBHI,带 PDF `B4K98DC7`)、`DD3XXKVS`(Lyu 2023 CBM,无 PDF,机构未订阅)。用户 Zotero 里的测试产物:`WL3IHIVX`(Nature Medicine,带 PDF)、`8D58AIM9`(M2Trans,带 PDF)保留;**回收站**里有探针留下的 5 个对象(`Q796LX5T` 探针条目及其附件 `6GM2ALTN`;识别器测试的 `SI6I9FQ8` "Attention Is All You Need" 及其附件 `NJ4MGYBB`、笔记 `GPFLMEYT`)以及更早的 `HXI7JHLX` 和两条 `[DELETE ME]`——由用户清空回收站。探针下载的 PDF 已从下载目录删除;更早测试的 3 个 PDF(两份 Restormer、一份 M2Trans)可能还在,未经用户同意没有删除。
- 下一步:§8 第 2 步真实运行一篇(用户给论文和目标分类,在场过 gate)→ 第 3 步新 agent 演练 → 第 5 步整理全库(先一个小分类校准)。papers.cool 的适配器 / skill 待用户定(§11)。

## 11. 待用户过目 / 决定

- `paper-to-zotero/references/tagging.md`(U11)。第一批整理是校准,看了效果再改。
- **papers.cool 的进一步利用**(用户 2026-09-21:追热点、查文献、查某领域最新论文)。2026-09-22 调研后设计者的建议改为**复用现成 skill `samonysh/papers-cool-search`**(§3.4),不写适配器:它已经覆盖查文献(`search`)、查某领域最新(`arxiv cs.CV+eess.IV`)、追热点(`arxiv <cat> --date … --sort 1`,一周热点 = 5 次调用,在预算内)、相关论文(`related`),带礼貌预算,MIT,`npx skills add samonysh/papers-cool-search` 即可装;paper-to-zotero 的阶段 1 直接调用它(装了用 helper,没装就 curl 同样的 URL)。它不做的:Atom 订阅(直接 curl feed)、Kimi 解读(按作者态度不脚本化;用户在浏览器里看,或 `opencli browser` 点开)。缺口出现再向上游提 PR,不在本仓库复制一份。用户 2026-09-22 认同("没必要重造轮子"),已 `npx skills add samonysh/papers-cool-search -g` 装到 `~/.agents/skills/papers-cool-search`(Claude Code 已符号链接);paper-to-zotero 的 SKILL.md 阶段 1 已引用它。

## 12. 探针结果(2026-09-21)

| 探针 | 结果 | 对设计的影响 |
|---|---|---|
| P0 授权 | `POST /api/local/authorize` 需带 `Zotero-Server-ID`;弹框 4 秒内点 Always Allow → `{key, remember: true}`;key 存 `~/.config/zotero/local-api-key` | `authorize_local_api.py` 的形状;授权弹框 = gate |
| P1 `wait download` | 下载前不误报;`open <pdf url>` 后命中(37 秒,10 MB 经代理),返回 `C:\Users\…\2006.11239v2.pdf`;完成后同 / 空 / 错 pattern 都不再命中 | 不写 `new_downloads.py`;路径用 `wslpath` 转 |
| P2 建条目 + PATCH | POST 带 `collections`、typed `tags` → key `Q796LX5T`,版本 199→200;PATCH 带版本 → 204;旧版本 → 412 "expected 200, found 201" | 新建可一次落到位;`file_and_tag.py` 的并发规则 |
| P3 `since=` | `since=199` 恰好返回新条目 | 识别退路用它找新建的父条目 |
| P4 上传 | 授权 200 → 传字节 201 → 注册 204;读回 md5 一致;`storage/6GM2ALTN/probe.pdf` 存在;`/fulltext` 已索引;文件名保持 `probe.pdf` | `attach_file.py` 可行;脚本自己起文件名 |
| P5 批量写 | 两个对象(一个版本正确、一个故意过期)→ `successful: [0]`,`failed: {1: 412 …}`,正确的那条已写入 | 整理全库用批量写,148 条 = 3 次请求 |
| P6 识别器 | 本地 API 上传的 PDF 不触发;connector `saveStandaloneAttachment` → 201 `{canRecognize: true}`,10 秒后出现 `preprint` 条目 `SI6I9FQ8`(Attention Is All You Need,arXiv 翻译器,分类作自动标签,一条 Comment 笔记),文件自动重命名 | 无 DOI 记录时的退路成立,走 connector |
| 限流 | 源码:"no rate limits";只有授权弹框 5 次/分钟 | v7 改回 connector 的理由不成立 → v8 用本地 API 新建 |
| 字段校验 | 源码:本地 API 用 `fromJSON(strict: false)`,与 connector 同样宽松 | `check_item.py` 保留 |

所有探针对象已移入回收站;探针下载的文件已删除;`p2z` session 已关。

## 13. 修订历史

- v3:定稿待实现;三份独立审查 + 源码自审;U0–U4。
- v4:按用户原则复审 15 条,用户逐条决定;U5(gate 5 分钟、范围扩大)、U6(访问阶梯)、U7(标签由 agent 管)、U8(临时分类);探针先行。
- v5:U4 改为保留出版商关键词、U7 扩为六类标签、U9 本地写 API 进 v1(归类 / 标签走 PATCH)、U10 `tmp`。
- v6:U11 英文前缀、U12;"可以完全使用本地写 API" → 新建条目走本地 API;§3.6 识别器。
- v7:因设计者误读"限流 5 次/分钟",新建条目改回 connector。
- v8:探针 P0–P6 全部通过;纠正限流误读,新建条目改回本地 API(U13);`wait download` 可靠;脚本收敛为 8 个。
- v9:通读整理——(2026-09-22 补:实现完成,§10 记录实现时的发现)修复损坏的版本说明、重复的 §3.5 编号、历次改通道留下的 `verify_saved` / `updateSession` / treeViewID 引用;来源关键词的来源改正(Crossref `subject` 不是关键词);补"无 DOI 记录"退路与"没有 PDF 时"的退出路径;`check_item.py` 的依据改为本地 API 的 `fromJSON(strict: false)`。
