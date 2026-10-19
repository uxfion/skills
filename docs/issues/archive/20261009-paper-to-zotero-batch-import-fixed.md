# paper-to-zotero — 一次 166 篇批量导入攒下的问题

> 已处理：37 条全部由 v3 解决。设计见 `docs/specs/20261013-paper-to-zotero-v3-spec.md`（§9 对照表），实现见 `3e7a9ff` 至 `f35880b`，2026-10-18 第一次真实批量验收；之后的问题记在 `docs/issues/20261018-paper-to-zotero-v3-first-batch.md`。参考代码文件夹已删除，原样见提交 `c2db226`。

2026-10-09 一个研究项目把旧调研的文献批量入库：166 篇，归入一个父分类下的 13 个子分类；由一个子 agent 单线程完成。第 1–8 条是批量导入时遇到的；第 9–17 条是同日主会话补挂其中 17 篇出版社 PDF 时遇到的，当时用户在线协助。第 18–20 条是同日 5 个检索子 agent 并行查找新文献（约 260 条候选）时遇到的，属于文献查询方式。第 21–27 条是同日为约 235 篇新候选预取全文时遇到的（用户在线，主会话执行），包括按用户反馈调整的回落顺序。第 28–33 条是同日一个子 agent 不用浏览器、把这 235 篇入库时报告的（第 1、2、18、24 条的补充也来自这次）。第 34–37 条是次日补取出版社全文时记下的：用户提出的人机协作方式与核对要求、预印本站点封禁、不循环重试、出版社行为（第 1、22、26、27 条的再现也记于这次）。条目格式同其他 issue：来源 · 日期、现场、痛点、为什么、方向、状态。仓库公开：不写学校、代理域名、个人路径。

---

### 1. `check_pdf.py` 大量误报 `title_not_found`

- 来源：使用 · 2026-10-09
- 现场：约 45 篇报 `title_not_found`，用 `pdftotext` 逐篇核对后全是对的论文。原因有三类：小型大写标题被抽成带空格的字母（“S ELF -R EFINE”）；连字丢失（“Reflexion” 抽成 “Reexion”）；部分 ACL 论文的字体脚本自己的抽取器解不出来（第 1 页只拿到 178 个字符）。
- 痛点：每篇都要人工复核，批量导入时成了主要耗时。
- 为什么：标题匹配依赖脚本自带的文本抽取，且对空白、连字敏感。
- 方向：抽取失败或匹配失败时回落到 `pdftotext`；比较前去掉空白与连字差异（fi / fl / ffi），并允许小型大写拆开的字母重新拼合。
- 再现（同日第二批 235 篇）：46 篇报 `title_not_found`，全部由 agent 读第 1 页后接收。新增一类：ACL Anthology 的 PDF 标题在第 1 页，脚本却只读到页脚；弯引号与字体移位编码（arXiv 的部分 PDF）也会漏判。
- 再现（2026-10-10）：一篇 medRxiv 预印本又报 `title_not_found`，而题名的实词 100% 在第 1 页、DOI 也在。
- 状态：已处理（v3）→ check_pdf 改用 pdftotext，两条通过路径（整条题名；或八成题名词，加上 DOI 或第一作者）

### 2. `create_item.py` 只能放进一个分类

- 来源：使用 · 2026-10-09
- 现场：每篇要同时进父分类和一个或多个子分类，`create_item.py` 只接受一个 collection，只好建完条目再跑一遍 `file_and_tag.py --batch`。
- 方向：`--collection` 可重复，或记录里的 `collection` 接受列表。
- 再现：第二批 235 篇同样要逐条补跑 `file_and_tag.py --batch`（`add_collection`）。
- 状态：已处理（v3）→ create_item 支持多个分类（`collection` 可以是列表）

### 3. 记录状态被 read-back 混淆；单条附件不回写记录

- 来源：使用 · 2026-10-09
- 现场：`find_in_library.py --readback` 会给本次新建的条目写上 `found`，之后看记录就像“库里原本就有”；`attach_file.py` 单条模式（`--key`）上传成功后不更新任何记录，记录里的附件状态与 Zotero 不一致。
- 方向：read-back 写到单独字段（如 `readback`），不覆盖 `found`；单条模式接受 `-i <record>` 时回写 `attach`。
- 状态：已处理（v3）→ `find_in_library --readback` 刷新原来那块（`saved` 或 `found`），从不互相改写

### 4. arXiv 草稿转成会议论文全靠手工

- 来源：使用 · 2026-10-09
- 现场：从 arXiv id 起草的条目是 preprint；改成 ICLR / NeurIPS / ICML / TMLR 的正式条目（条目类型、会议名、官方页 URL、`arXiv:` 写进 Extra）全部手工；NeurIPS 论文页的哈希地址、PMLR 页、OpenReview id 都要逐篇查。还有 10 余篇的正式版换了刊物或题名（如 Nature、npj Digital Medicine、KDD 的正式版），也是人工比对出来的。
- 方向：`doi_to_item.py` 对 arXiv id 查一次 DBLP / Semantic Scholar 的正式出处，给出“建议的正式版”，由 agent 确认。
- 状态：已处理（v3）→ doi_to_item 给出正式版候选，`--redraft` 在原记录上改成正式版

### 5. 元数据接口限流与验证页

- 来源：使用 · 2026-10-09
- 现场：
  - arXiv API 约 60 次调用后返回 429；
  - OpenReview 约 45 次搜索后，curl 与 opencli 适配器都收到 `ChallengeRequiredError`；
  - DBLP 在这台机器上连不上；
  - Europe PMC 的 `?pdf=render` 返回 HTML；
  - PMC 对 curl 返回 JavaScript 验证页，浏览器里可以，但 Lancet、BMJ 的论文在 PMC 上没有 PDF；
  - 自动化 Chrome 标签页里，Cloudflare Turnstile 永远停在“验证成功，正在等待响应”（ACM、NEJM AI、OUP、Lancet、JAMA、Emerald），用户手点也不行。
- 痛点：出版社 PDF 最终只能列清单请用户在自己的浏览器下载。
- 方向：`references/publishers.md` 写明顺序：先 PMC，再出版社。批量导入加调用节流与退避。Turnstile 的处理见第 12 条：同日下午在自动化标签页重试，验证都自动通过了。所以“直接进手动下载清单”只作为用户不在场时的退路，不是常规做法。
- 状态：已处理（v3）→ publishers.md：开放获取走 PMC、Europe PMC 的 render 链接、OpenReview 与 DBLP 的限流、Turnstile

### 6. PMLR 的 PDF 链接改了

- 来源：使用 · 2026-10-09
- 现场：PMLR 论文页上的 PDF 链接现在指向 raw.githubusercontent.com 上的文件，按旧规律拼的链接不对，要从页面读出。
- 方向：publishers.md 记一笔；PDF 链接一律从页面读取。
- 状态：已处理（v3）→ PDF 链接一律从页面读（`citation_pdf_url`）；publishers.md 记了 PMLR 的新链接

### 7. Chrome 下载的重复与漏检

- 来源：使用 · 2026-10-09
- 现场：同一篇（Lightman 2024）被下载了两次；另一篇（Voyager）的下载在 OpenReview 验证页通过之后才开始，`wait download` 没有捕捉到，最后从 Downloads 里按时间找到。
- 方向：`wait download` 前后都按 `.started` 比对 Downloads；同名带 “(1)” 的重复文件在入库后清理。
- 状态：已处理（v3）→ claim：同一篇的第二份进 `stray/`，晚到的下载也认领

### 8. 新建裸标签过多，部分其实是数据集或概念

- 来源：使用 · 2026-10-09
- 现场：一次批量新建了 115 个模型名标签，其中一些应是 `dataset/…`（GSM8K、PRM800K、MultiMedQA、LongFact、MIMIC-CDM、MIRAGE），一些是概念而非名称（Scalable oversight、More Agents、Temperature scaling、Conformal risk control、Semantic entropy）。事后已由用户确认整理。
- 方向：tagging.md 写清“模型名”的判断标准；批量导入结束时列出新标签让用户过目。
- 状态：已处理（v3）→ tagging.md：裸标签只给模型或系统名，数据集用 `dataset/`；2026-10-18 改为“论文自己给模型起的名字”

---

以下第 9–17 条：补挂 17 篇出版社 PDF 时遇到的。最终结果：13 篇拿到正式版，2 篇只能挂 arXiv 预印本，2 篇学校无权限；用户没有逐篇下载。

### 9. 访问阶梯里没有“机构图书馆检索系统”这一级

- 来源：使用 · 2026-10-09
- 现场：有 4 篇在出版社页面显示无权限，Nature 走机构登录后仍无权限：TextGrad（Nature）、RAD-DINO（Nat Mach Intell）、BiomedGPT（Nat Med）、Lambe 2016（BMJ Qual Saf）。用户在学校图书馆的检索系统（Ex Libris Primo NDE）里搜标题，经聚合数据库（ProQuest、Ovid）拿到了正式版全文。检索页背后的接口 `primaws/rest/pub/pnxs` 对每条结果给出 `pnx.links.linktopdf` / `linktohtml` / `linkunpaywall`，可直接机读，不必解析页面。
- 痛点：skill 判定“无权限”太早，接下来只剩存网页快照或请用户下载。
- 为什么：访问阶梯只有出版社页面和开放获取副本两条路。机构订阅的聚合库是第三条，只有图书馆检索系统知道。
- 方向：
  - 在出版社页面判定无权限之前，加一级“机构检索系统”。
  - 检索系统地址、`vid`、代理主机放在用户本地配置里（如 `~/.config/paper-to-zotero/institution.json`），不进公开仓库。
  - 写一个 `discover.py`：按标题检索，抓 `pnxs` 响应，返回前 3 条结果的 PDF / HTML / OA 链接与数据库名（`$$G` 字段）。
  - ProQuest 本身也要作为一个检索入口写进阶梯，不只是检索系统跳转过去的落点。这次 4 篇里有 3 篇的全文最终都在 ProQuest，检索结果给的是 `proquest.com/docview/<id>/fulltextPDF` 链接；拿到 docview id 后，走机构代理打开 `fulltextPDF` 页即可取 PDF（见第 10 条）。检索系统没收录的条目，可以直接在 ProQuest 里按标题检索。机构订阅的其他聚合库（这次检索结果的分面里出现了 Journals@Ovid、EBSCOhost）同理。各库的代理地址和 `accountid` 都放进本地配置。
- 状态：已处理（v3）→ 链路第 3 步 `fetch.py --via discovery`（Primo → ProQuest），地址在配置的 `institution.discovery`，缺了 `ready.py` 提示问用户（2026-10-18）

### 10. 聚合库的 PDF 嵌在阅读器里：外层没有下载链接，新标签页不归会话

- 来源：使用 · 2026-10-09
- 现场：ProQuest 的 `fulltextPDF` 页面把 PDF 放进同源的 pdf.js iframe，外层页面没有下载链接，下载按钮在 iframe 里。在检索系统里点 “Get PDF” 会新开一个标签页，这个标签页不归当前 opencli 会话管，`wait download` 也等不到下载；`bind` 有时会绑到之前的旧标签页上。
- 可行做法：直接用 `www-proquest-com.<proxy-domain>/docview/<id>/fulltextPDF` 打开页面，等 `iframe.contentWindow.PDFViewerApplication.pdfDocument` 就绪，用 `getData()` 取出字节，再经 `eval` 以 base64 带出。这样 Downloads 里不留文件。
- 方向：把这个做法写进 publishers.md，或做成脚本（和第 11 条共用“页面内取字节”的部分）。
- 状态：已处理（v3）→ `fetch.py --via viewer` 和 discovery 路线都从 pdf.js 阅读器取字节，都在会话自己的标签页里打开

### 11. 在页面里同源 fetch 取 PDF，比点按钮、等下载更稳

- 来源：使用 · 2026-10-09
- 现场：ACM、NEJM AI、Lancet、JAMA 的做法一样：打开文章页并通过验证后，在页面里执行 `fetch('/doi/pdf/…', {credentials: 'include'})`；`content-type` 是 PDF 就把字节以 base64 带出，是 HTML 就说明无权限（Almanac、JAMA 都是这样）。这样不经过 Chrome 自带的 PDF 阅读器（那个标签页无法调试），也不往 Downloads 里留文件。
- 方向：作为第 3 步“取 PDF”的默认做法写进 SKILL.md，并做成脚本（例如 `fetch_in_page.py --session p2z --path <同源路径> --out <pdf>`）。点按钮加 `wait download` 只作为退路。
- 状态：已处理（v3）→ `fetch.py --via page`：页面内带凭据请求 `citation_pdf_url`，被拒再像点击一样打开链接

### 12. 第 5 条里的 Cloudflare 结论需要修正

- 来源：使用 · 2026-10-09
- 现场：同日下午用户在线，重试结果：ACM 文章页直接打开，没有验证；NEJM AI、Lancet、JAMA 的“请稍候…”在 10–15 秒内自动通过。上午子 agent 遇到的“永远等待响应”没有再出现。
- 为什么：原因未查明，可能和当时的会话或时段有关。可以确定的是，“遇到 Turnstile 就进手动清单”放弃得太早。
- 方向：用户在场时先在自动化标签页里重试，等待 ≥ 30 秒，同时提醒用户，必要时请用户点一下验证框；仍然循环才列进手动清单。
- 状态：已处理（v3）→ publishers.md：Turnstile 先提醒，等它自己过

### 13. 机构代理的自动跳转与 “Host Needed”；快照存成了报错页

- 来源：使用 · 2026-10-09
- 现场：
  - 用户的 Chrome 会把部分出版社主机自动转到学校的 EZproxy，`link.springer.com` 和 `jamanetwork.com` 都被转过。
  - 代理不覆盖的主机，会落到标题为 “Host Needed” 的报错页。
  - 我给一篇无权限的 JAMA 论文存网页快照时，存下的正是这个报错页，`attach_file.py` 照样上传成功了。
- 方向：
  - `attach_file.py` 对 HTML 快照也做标题核对：页面里找不到条目标题就拒绝上传，和 `check_pdf.py` 对 PDF 的做法一样。
  - publishers.md 记下：“Host Needed” 或代理登录页表示“代理不覆盖这个主机，即无机构权限”。
  - 保存快照前先读 `state`，确认标题和 URL。
- 状态：已处理（v3）→ check_pdf 核对 HTML（`not_the_article`）；publishers.md 把 “Host Needed” 列为过不去的页面

### 14. 挂错或已被取代的附件，agent 没有正当的撤回办法

- 来源：使用 · 2026-10-09
- 现场：
  - 存错的快照（第 13 条）想移进回收站，agent 侧的写操作被权限策略拦下。这也符合 skill 的规则：回收站是用户的操作。
  - 正式版挂上后，原来的网页快照和 PMC 作者稿都还留在条目下，同样只能请用户清理。
- 方向：
  - `attach_file.py` 加 `--replace <attachment key>`：只允许覆盖本次运行刚建的附件文件。
  - 报告里固定加一节“待用户清理的附件”（附件 key、原因），挂上正式版时自动列出被取代的快照和作者稿。
- 状态：已处理（v3）→ `trash_item.py`；报告的“待清理附件”

### 15. 正式版改了标题时，`check_pdf.py` 认不出 arXiv 版

- 来源：使用 · 2026-10-09
- 现场：FnT ML 正式版的标题是 “Conformal Prediction: A Gentle Introduction”，对应的 arXiv 2107.07511 标题是 “A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification”，所以挂 arXiv 版时报 `title_not_found`。
- 方向：`check_pdf.py` 同时比对 `extra` 里 arXiv id 对应的标题，或者接受 `--alt-title`。
- 状态：已处理（v3）→ 记录的 `alt_titles`，check_pdf 认备选题名

### 16. 开放获取的来源偏少

- 来源：使用 · 2026-10-09
- 现场：
  - 检索系统给出的 `linkunpaywall` 显示，Unpaywall 能找到 PMC 作者稿和机构库副本：BiomedGPT 指向 PMC，Mamede 2010 指向 Maastricht 机构库。
  - 但机构库的条目可能只有元数据，没有 PDF：Mamede 2010 那一条就是。
  - skill 目前主要依靠 OpenAlex 的 OA URL。
- 方向：
  - 开放获取查询补上 Unpaywall API（需要 `email` 参数，放在用户本地配置里）、Europe PMC 的 `fullTextUrlList`、Semantic Scholar 的 `openAccessPdf`。
  - 机构库链接要打开确认有 PDF，再算作“有开放副本”。
- 状态：已处理（v3）→ `fulltext_links.py`：OpenAlex（含 Unpaywall 的数据）、Europe PMC、arXiv；取到的文件都要核对

### 17. opencli `browser network` 的缓存读一次就空了

- 来源：使用 · 2026-10-09
- 现场：第一次调用 `browser network` 列出了检索系统的接口请求；紧接着第二次调用（为了取条目 key）返回 `count: 0`，只好重新检索一遍再取。
- 方向：在 skill 的 Instruments 一节写明：先把 `network` 的输出存成文件，再从文件里取 key 去调 `--detail`。如果确认是 opencli 的行为，再反馈给 opencli。
- 状态：已处理（v3）→ publishers.md：network 的输出先存成文件

### 18. 并行检索时，共享的限额没有统一调度

- 来源：使用 · 2026-10-09
- 现场：5 个检索子 agent 同时运行，各自按“每分钟最多一次”使用用户 Chrome 里的 Google Scholar，合计最多约每分钟 5 次，开跑后不到一小时 Google 返回按 IP 的“automated queries”封锁页，没有可点的验证码，用户也解除不了。OpenAlex 不带 key 的免费日额度按机器计算，开跑后十几分钟就被用完（HTTP 429 “Insufficient budget”，UTC 零点重置）。Semantic Scholar 与 arXiv API 也先后返回 429。
- 痛点：引用数和向前追引用依赖这些来源；一个 agent 触发限流，其余 agent 同时失去来源，而且彼此不知道。
- 为什么：skill 的节流规则是按单个调用者写的，没有考虑同一台机器上多个 agent 共用额度。
- 方向：
  - 在 skill 里写明“限额按机器合计”：Google Scholar 一次只给一个 agent 用，合计每分钟至多一次；可以用一个本地锁文件记录上次查询时间，所有 agent 先读再查。
  - OpenAlex 支持在用户本地配置里放 `api_key`；没有 key 时提示额度共享。
  - 引用数的回落顺序写进 skill：OpenAlex → Crossref `is-referenced-by-count` → Europe PMC（医学）→ 留空待补。
- 补充（入库 agent）：`export.arxiv.org` 的 API 返回 429 时，arXiv OAI-PMH（`metadataPrefix=arXivRaw`）全程可用，能拿到版本、分类和摘要，可以写成 arXiv 元数据的回落。
- 状态：已处理（v3）→ batch.md 的分工：批量调外部接口的脚本只在主会话跑，各进程自己节流，429 本次停用

### 19. 会议录用的核实缺少可脚本化的来源

- 来源：使用 · 2026-10-09
- 现场：OpenReview API 对脚本返回 403 “Challenge verification required”，DBLP 对 curl 返回 Anubis 人机检查页，两者都不能用来核实“这篇论文是否被某会议录用”。一个子 agent 改为抓取官方录用列表（ICLR、ICML、NeurIPS 的 virtual 页面，papers.nips.cc，PMLR 目录），建成约 5.7 万个标题的本地索引，再按标题匹配，效果很好。
- 痛点：没有这个索引时，会议论文的出处只能逐篇打开网页核实，或者凭记忆，后者不允许。
- 方向：skill 增加一个脚本，从官方录用列表构建并缓存“会议—年份—标题—链接”索引，在第 1 步（定位论文）和第 2 步（填会议字段）中按归一化标题匹配；ACL Anthology 与 CVF 也可以加进去。
- 状态：已处理（v3）→ 正式版候选（arXiv、Crossref）+ papers.cool 补查，不建会议索引

### 20. Google Scholar 的 opencli 适配器在检索中失效

- 来源：使用 · 2026-10-09
- 现场：一个检索子 agent 报告 `google-scholar` 适配器调用失败，改用 `opencli browser` 会话直接操作 Scholar 页面才拿到结果（之后又遇到第 18 条的封锁）。当时没有保存适配器的错误输出。
- 方向：下次失败时保存适配器的原始输出再判断是适配器问题还是页面拦截；如果是适配器问题，反馈给 opencli。skill 里把 Scholar 的回落路径（适配器 → 浏览器会话）写明。
- 状态：已处理（v3）→ SKILL.md 回落阶梯：浏览器型适配器失败，就在会话里打开同一页自己看，适配器原始输出存进 `scratch/`

---

以下第 21–25 条：为约 235 篇新候选预取全文时遇到的。做法：先按“谁能取到”分类，脚本能取的直接下载，剩下的趁用户在线一次性用浏览器取完，再交给无人值守的入库。

### 21. 需要用户在场的步骤散落在整个批量导入里

- 来源：用户反馈 · 2026-10-09
- 现场：batch.md 让入库 agent 逐条处理，出版社页面的门禁（登录、验证）出现在哪一条就停在哪一条。批量导入一跑几个小时，用户往往前半段在、后半段不在，后半段的门禁就没人处理。用户原话：「你要是把所有需要我协助的任务都放在最后，我最后可能就不在的。现在前期我还是在的，后面就放到你自己执行无人值守了」。
- 痛点：一份清单里只要有几篇需要浏览器，整个批量导入的完成时间就取决于用户什么时候回来。
- 为什么：skill 按论文顺序组织流程，没有按“谁能完成这一步”组织。
- 方向：批量模式先做一次分流，再分两段执行：
  - 分流：arXiv / PMLR / 会议论文集等开放仓库；OpenAlex `best_oa_location` / `locations[].pdf_url` 给出的开放获取 PDF（按 DOI 单篇查询）；其余需要浏览器的。
  - 第一段（无需用户）：开放的全部用 HTTP 直接下载，验证 `%PDF` 和标题。
  - 第二段（用户在线时一次做完）：需要浏览器的逐条按回落顺序取：出版社文章页同源 fetch → 机构检索系统（第 9 条）→ ProQuest 阅读器取字节（第 10 条）→ 都没有再列入快照清单。门禁用一个监视器盯住，出现就提醒用户。
  - 入库：只挂已在本地的文件，基本不再碰门禁，可以无人值守。
  - 这次的结果：235 篇里约 100 篇在第一段由脚本取到，约 80 篇是 arXiv，留给浏览器的约 50 篇。
- 状态：已处理（v3）→ SKILL.md、batch.md：一种跑法；用户随时可插手；能预见的提前说；只有最后一遍等用户

### 22. 机构代理的自动跳转来自 Zotero Connector，跳转后的地址需要单独处理

- 来源：使用 · 2026-10-09（补充第 13 条）
- 现场：
  - 第 13 条记的“Chrome 自动把出版社主机转到 EZproxy”，实际是 Zotero Connector 的代理功能：页面顶部出现 “Zotero automatically associated <host> with a previously defined proxy”。同一出版社的两篇文章，一篇被转、一篇没被转。
  - 被关联之后，代理不覆盖的主机会落到代理返回的 404 页（一篇 Science 文章）。
  - 页面里的 `citation_pdf_url` 写的是出版社原主机名。在代理后的页面里直接 fetch 这个地址是跨域请求，带不上代理的 cookie，取回来的是 HTML。
- 方向：
  - 同源 fetch 前先比对 `location.host`。不同的话，只取路径，在当前（代理后的）源上请求。
  - publishers.md 写明这个跳转的来源。代理 404 与 “Host Needed” 一样，判为“无机构权限”，转去机构检索系统，不要重试出版社页面。
- 再现（2026-10-10）：Zotero Connector 把 jamanetwork.com 也转去了机构代理，代理回 “Host Needed”；其中两篇是开放获取的 JAMA Netw Open，本来不需要代理。开放获取期刊应先走不经代理的地址或 PMC。
- 状态：已处理（v3）→ fetch 在代理页上按路径请求；publishers.md 写了 Zotero Connector 的代理关联、开放获取期刊走 PMC

### 23. 当年会议的 OpenReview 论文在公开前返回 403，不是门禁

- 来源：使用 · 2026-10-09
- 现场：在用户已登录的 Chrome 里，ICLR 2025/2026、ICML 2026、COLM 2025 的 `/pdf?id=…` 都能在页面里同源取到；NeurIPS 2026（会议还没开）的论文，`/pdf?id=…` 与 `api2.openreview.net/notes?id=…` 都返回 403。会议官网的 virtual 页面有作者和摘要。
- 方向：403 判为“尚未公开”，不当门禁等待；回落到 arXiv，没有 arXiv 就挂 virtual 页面的快照，并在报告里注明会后补挂。另外，在 OpenReview 页面里调 `api2.openreview.net/notes/search?term=<标题>` 可以按标题找 forum id（同一篇常有 CoRR 和会议两条记录，按 `venue` 选）。
- 状态：已处理（v3）→ publishers.md：OpenReview 会前 403 = 尚未公开，改用预印本

### 24. 会议论文的正式版 PDF 可以脚本取到；NeurIPS 其实有 DOI

- 来源：使用 · 2026-10-09
- 现场：
  - PMLR 的 PDF 链接在卷目录页里，指向 `raw.githubusercontent.com/mlresearch/v<卷>/main/assets/<id>/<id>.pdf`，可以直接下载。
  - NeurIPS 论文集页面 `/hash/<h>-Abstract-<track>.html` 对应的 PDF 是 `/file/<h>-Paper-<track>.pdf`。这个文件只有正文，附录在单独的 Supplemental 文件里。
  - CVF 把 `/html/` 换成 `/papers/` 即可。
  - Crossref 的标题查询会返回 NeurIPS 2022–2025 的 DOI（前缀 `10.52202`，Curran 印刷版论文集），解析到付费页面。SKILL.md 写的是“NeurIPS 不发 DOI”。
- 方向：
  - 第 3 步写明各会议正式版 PDF 的取法（可以和第 19 条的录用索引共用）。
  - 写明 NeurIPS 的 `10.52202` DOI 可以填进 `DOI` 字段，但 `url` 仍用论文集页面，附件取论文集的 PDF；需要附录时另挂 Supplemental。
- 补充（入库 agent，纯 HTTP 已验证）：`proceedings.neurips.cc`（2025 主会列表在 `/paper_files/paper/2025/vol38-main-conference`）、`proceedings.iclr.cc`（2024–2026，2023 没有）、PMLR 卷页、ACL Anthology（含 TACL 卷页）、CVF Open Access、`papers.miccai.org` 的 “Main Paper (Open Access Version)”。
- 状态：已处理（v3）→ `--redraft` 读论文页的 `citation_*`；publishers.md 写各会议 PDF 的取法；NeurIPS 的 DOI 填进 DOI 字段

### 25. opencli 的 OpenAlex 适配器不读 API key

- 来源：使用 · 2026-10-09（补充第 18 条）
- 现场：用户申请了 OpenAlex key。opencli 的 `openalex` 适配器只读环境变量 `OPENALEX_MAILTO`，没有 `api_key` 参数，只能自己用 HTTP 请求带上 key。带 key 时，按 DOI 的单篇查询不扣费（响应头 `x-ratelimit-cost-usd: 0`），日额度 1 美元；检索和列表请求扣费。
- 方向：
  - skill 的脚本从用户本地文件读 key（例如 `~/.config/openalex/api_key`，权限 600），作为 `api_key` 参数发送，日志里不打印 URL。不用环境变量，免得 `env` 之类的输出把 key 带进对话。
  - 优先用单篇查询（`/works/doi:…`），少用 search。
  - 给 opencli 提需求：适配器支持读 key。
- 状态：已处理（v3）→ 配置里的 `openalex_key`，fulltext_links 直接调 OpenAlex API

### 26. 请用户在浏览器里操作时，自动化还在占用同一个标签页

- 来源：用户反馈 · 2026-10-09
- 现场：
  - 预取全文时，我请用户登录学校检索平台，但取全文的脚本没有停。它每处理一篇就让 `p2z` 会话的标签页跳到新地址，用户在那个页面上登录，几次都被切走。用户原话：「你没等我登录学校检索平台，怎么就把tab给关掉了」「出现很多次了，直接就跳没了。是不是应为后续的检索任务把它顶掉了」。
  - 脚本停下后，用户如果仍在自动化打开的窗口里操作，页面也可能被关掉。推测是 opencli 后台进程按“标签租约”回收会话名下的标签，未核实。
- 痛点：需要用户动手的那一步（登录、验证）反复失败，用户的时间白白浪费，还以为是自己操作有问题。
- 为什么：skill 的门禁规则只写了“提醒用户、轮询等待”，没有写“等待期间不得再操作浏览器”。批量模式下，脚本或其他子 agent 仍在用同一个 Chrome。
- 方向：
  - 门禁和登录请求一律是**全局暂停**：发出提醒后，本会话和所有子 agent 都停止 `opencli browser` 操作，直到用户确认或轮询确认已通过；轮询只读 `state`，不导航。
  - 提醒里告诉用户在哪儿操作：门禁就在当前标签页里点；登录就按 Ctrl+N 新开普通窗口，不要用自动化窗口。登录状态是整个 Chrome 共享的。
  - 如果确认 opencli 会回收会话名下的标签，在 SKILL.md 的 Instruments 一节写明，并考虑给自动化窗口一个醒目的标记（例如固定的标签组名称）。
- 再现（2026-10-10，批量补取）：脚本按标题关键词识别门禁，机构代理的 “Host Needed” 页和学校统一身份认证页都不在关键词里，于是判为“没有 PDF 链接”，接着走下一条路线，把用户正要登录的页面顶掉了。用户原话：「别那么快关，我还没登录，上一个学校授权的」。本项目的临时做法：门禁关键词加上单点登录页的常见标题（Shibboleth、SSO、CAS、WebVPN、统一身份认证、登录、授权），等待时间从 5 分钟改为 15 分钟。后来读页面正文才确认，这次的 “Host Needed” 其实不是登录页：它是 Zotero Connector 把出版社主机自动转到机构代理后，代理回答“该资源未配置”，用户登录也过不去。所以要分两类：能由用户通过的门禁（登录、验证码）停下来等；“代理不覆盖此主机”这类无法通过的页面，告诉用户是什么、换下一条路线。两类都要在动作之前先告诉用户，不能默默跳过。方向补充：门禁不只看标题，也看主机名——页面离开出版社或检索系统、落到机构的认证域名上，就当作门禁；门禁出现时先停下并通知用户，不换路线。
- 状态：已处理（v3）→ SKILL.md 门禁：Ctrl+N 普通窗口登录，等待只读页面，门禁标签页保留，之后开新标签页；自动化窗口在后台

### 27. 页面内取 PDF 的路线没有检查下载目录：Chrome 已经下载了，脚本却判为失败

- 来源：用户反馈 · 2026-10-09（补充第 7、11 条）
- 现场：
  - 预取脚本按“出版社页面内同源 fetch → 机构检索系统给出的 `linktopdf`”依次尝试。某出版社（OUP）的 PDF 链接带 `Content-Disposition: attachment`，`browser open` 打开它时 Chrome 直接把文件存进了 Downloads。脚本只看页面内 fetch 的返回值（是 HTML），判为“没拿到”，接着试下一条路，于是同一篇被下载了两遍（`ocae294.pdf`、`ocae294 (1).pdf`，两份 md5 还不同，大概是下载时加了水印或时间戳）。
  - 用户原话：「你检查一下下载目录，有一个下了两遍了，你似乎没看到」「Chrome已经下载了呀，你没有检测到而已」。
  - 同时发现 Downloads 里还留着前一天和当天早些时候的 4 个 PDF，与 Zotero 附件 md5 完全相同。它们来自不经过 skill 运行的手工补挂（没有 `.started` 标记，所以第 6 步清理不到）。
- 痛点：重复下载浪费时间，还会误判“无权限”而去存网页快照；Downloads 越积越多，需要用户提醒才清理。
- 为什么：第 11 条把“页面内 fetch”定为默认做法，前提是不产生下载；但打开 PDF 链接本身就可能触发下载，这一路径没有被观察到。第 7 条的“前后比对 Downloads”只写在 `wait download` 那条路上。
- 方向：
  - 每一次导航或点击之后都比对 Downloads（相对 `.started` 的新文件，包括 `.crdownload`）。出现新的 PDF 且标题核对通过，就当作这一步成功，把文件移进工作目录，不再试后面的路线。
  - 同一篇出现带 “(1)” 的重复文件时，保留一份，其余删除（都是本次运行产生的）。
  - 提供一个清理脚本：把 Downloads 里的 PDF 与 Zotero 附件按 md5 比对，列出已在库中的文件，经用户确认后删除。不经过 skill 的手工补挂之后也可以跑。
- 再现（2026-10-10，批量补取）：加了“每条路线后比对 Downloads”之后仍有两类残留：① 页面内已取到 PDF，Chrome 稍后又存了一份同样的文件，到达时比对已经结束（md5 与已挂附件相同）；② 检索系统的链接下载到了另一篇论文（标题核对不过），脚本不收也不清。方向补充：批次结束时再扫一次 Downloads，把本次运行之后出现、与已挂附件 md5 相同的文件删掉；标题核对不过的下载移出 Downloads 并记下来源链接，那通常说明检索系统的链接指错了。
- 状态：已处理（v3）→ claim：`--watch` 从第 0 步起常驻、`--sweep` 收尾；`find_in_library --md5`

### 28. `attach_file.py` 的 `--title` 对整次调用生效

- 来源：使用 · 2026-10-09
- 现场：235 篇里 39 篇挂的是替代版本，附件标题要分别写成 “Preprint (arXiv v2)”、“Accepted manuscript (…)” 等。流模式下 `--title` 对整批记录生效，记录里不能逐条指定，只好按标题分组多次调用。
- 方向：记录里加 `attach.title`（或 `file_title`），有就用它，没有再用 `--title`。
- 状态：已处理（v3）→ attach_file：附件标题按文件版本写

### 29. `doi_to_item.py` 丢了 Crossref 的副标题，也不带 arXiv 分类

- 来源：使用 · 2026-10-09
- 现场：JAMA、ACM 等的标题只剩冒号前的部分，4 篇需要按正式版手工补全。arXiv 条目的分类要另取 arXiv 元数据，才能按 SKILL.md 写成 type 1 标签。
- 方向：Crossref 记录有 `subtitle` 时拼成 “标题: 副标题”；arXiv id 的记录顺带取分类。
- 状态：已处理（v3）→ doi_to_item：补副标题和 arXiv 分类

### 30. Zotero 把 `extra` 里的 PMID 迁成独立字段

- 来源：使用 · 2026-10-09
- 现场：按 SKILL.md 把 `PMID: <n>` 写进 `extra`，Zotero 会把它迁成独立的 `PMID` 字段。之后再改 `extra` 改不到这个字段，必须单独 `--set PMID=`。
- 方向：在第 2 步写明这一迁移；改 PMID 时用字段而不是 `extra`。
- 状态：已处理（v3）→ SKILL.md 第 2 步：PMID 会被迁成独立字段，之后用 `update_item --set PMID=` 改

### 31. citation key 在创建时就固定了

- 来源：使用 · 2026-10-09
- 现场：两条记录在建好条目后才改了作者或标题（一条原来指向勘误，一条的 arXiv 标题与正式标题不同），citation key 停在旧值，要手动重设。
- 方向：第 4 步之后、读回之前加一次 key 复核：按最终的作者、年份、标题重新生成，与条目的 key 不同就提示（用户给定的 key 除外）。
- 状态：已处理（v3）→ SKILL.md 第 2 步：正式版在建条目之前定下

### 32. 定位得到的标识符可能指向别的文件：勘误、错挂的开放获取链接

- 来源：使用 · 2026-10-09
- 现场：
  - Crossref 的书目检索把一则 1 页的作者姓名勘误排在第一，类型仍是 `journal-article`；候选清单于是带着勘误的 DOI，预取的 PDF 也是勘误。入库 agent 读第 1 页才发现，改指正文的 DOI。
  - 另一篇的 OpenAlex 开放获取链接指向一篇无关的会议论文（标题完全不同）。预取时的标题检查已经标了 CHECK，但清单仍把它当作已预取的文件交了出去。
- 痛点：标识符和文件都“看起来对”，只有读第 1 页才能发现；入库之后再改要动 DOI、key 和附件。
- 方向：
  - 第 1 步对 Crossref 结果检查标题以外的信号：页码以 `r`、`e` 开头，页数为 1，作者为空，标题含 “Correction”“Erratum”“Retraction”。
  - 任何来源的开放获取链接，下载后标题核对不过，就不算已取到，而不是留给后面的步骤判断。
- 状态：已处理（v3）→ doi_to_item 的勘误警告；check_pdf 拦勘误、补充材料、DOI 不符；所有文件都经 claim 核对

### 33. Nature 的 “Article in Press” 是未编辑的接受稿

- 来源：使用 · 2026-10-09
- 现场：npj 系期刊的 `_reference.pdf` 与 “Article in Press” 页面给的是未编辑的接受稿，不是排版后的正式版；7 篇这样挂上，附件标题写成 “Accepted manuscript (npj Digit Med article in press)”。
- 方向：写进 `references/publishers.md`：这类文件按 accepted manuscript 标注，正式版排版后再替换。另外，批量状态文件的 `attachment` 只有 `pdf`/`queued`/`failed` 三个值，表达不了“库里已有、未改动”和“挂的是替代版本”，可以加上。
- 状态：已处理（v3）→ publishers.md：Article in Press 算接受稿（`<slug>.accepted.pdf`）

### 34. 下载监控应持续运行，用户也可能替 agent 点 PDF 按钮

- 来源：用户反馈 · 2026-10-10
- 现场：批量补取时，用户在共用的 Chrome 里看到文章页的 PDF 按钮，就顺手替 agent 点了，Chrome 把文件存进 Downloads；脚本当时正停在一个人机验证页上等待，只在“自己点完之后”才比对 Downloads，没有察觉文件已经到了，继续空等。用户原话：「有时候我看到了 PDF 那个按钮，也会帮你点一下……后台下载监控程序要持续的，不要以你自己点击为准才开始监控下载目录……你一旦检测到下载了，然后内容符合，就进行下一步」。
- 痛点：用户能更快拿到的文件被晾在一边，agent 还在门禁上空等；人和 agent 都点时又容易重复下载、重复挂附件。
- 为什么：下载检测绑在 agent 自己的动作上（第 7、27 条都是“动作前后比对”），默认只有 agent 会触发下载。
- 方向：
  - 浏览器批次期间，下载监控作为独立的后台进程持续运行，不依赖 agent 的点击：Downloads 出现新的完整 PDF，就按题名（必要时加 DOI）与待取清单逐条匹配；匹配上的移入工作目录、核对、挂附件、标记完成，并通知正在处理这条的驱动流程提前结束等待（包括门禁等待）。
  - 驱动流程照常主动走各条路线（用户不在时也能完成），每处理一条前、每次等待中都查看这一条是否已被监控进程完成。
  - 人和 agent 都可能拿到同一篇：挂附件前先“认领”这一条（加锁写状态），后到的一份按重复删除；匹配不上清单的下载移出 Downloads 并记录来源。
  - 在 SKILL.md 的批量导入说明里写明这种人机协作方式：用户在场时可以替 agent 点 PDF 按钮或下载，agent 会自动接上。
- 补充（用户 2026-10-10：「下载后入库前要核对」）：
  - 监控进程只碰能认出来的文件：匹配不上清单的新 PDF 留在原处、只记一笔，因为在共用的电脑上它可能是用户自己下的；同一篇的重复副本移到工作目录的 stray 文件夹，不删除。
  - 下载到的文件在挂附件之前必须过身份核对，不能只看题名的前几个词：题名的大部分实词出现在前 3 页；第 1 页印有 DOI 时必须是这一篇的 DOI；不是补充材料、勘误或撤稿通知（与第 32 条同源：勘误和错挂的开放获取链接都“看起来对”）。核对不过的文件不挂、留给人看，并写明哪一项没过。
  - 本项目的实现：`verify()` 对已挂的 9 篇全部通过，对两份已知的错文件（1 页勘误、另一篇论文）都拒绝。
- 参考代码（项目里的临时补救，不是 skill 代码）：原在 `docs/issues/20261009-paper-to-zotero-batch-import-reference/`，v3 的 `claim.py`、`check_pdf.py`、`fetch.py` 取代了它，已删除；原样见提交 `c2db226`。
- 补充（用户 2026-10-10：「我可能帮你点pdf下载并不意味着你不作为不去点，你也要尝试去获取到pdf」）：用户帮忙只是加速，agent 照样要主动取。本次的缺口是：页面内请求 PDF 链接被拒（ACM 数字图书馆 403；nature.com、NEJM AI、Science 返回 HTML）时，脚本就判为失败，没有像人那样直接打开 PDF 链接。改为：页面内请求被拒，就在标签页里打开该链接（相当于点击），Chrome 显示 PDF 则从查看器地址取，Chrome 下载则由监控进程接上；仍不行再走机构检索系统。
- 补充（2026-10-18，审 v3 时用户重提：「我实际上已经帮你下载了，但是你还没找到pdf，就没开启监控，就一直卡在那，效率就很低」）：v3 的监控从第 0 步起就在跑，但 agent 不一定及时知道文件到了——门禁等待只看页面，手动操作页面前不看文件，`fetch` 只在开头查一次。改为：`fetch --wait` 等门禁时也看文件；`fetch` 每篇前重查；手动操作每一步前先看；Claude Code 里用 Monitor 盯 `fetch.jsonl` 的认领行。
- 状态：已处理（v3）→ claim `--watch` 常驻；fetch 每篇前重查文件；`--wait` 看到文件就结束；Monitor 盯日志（2026-10-13、10-18）

### 35. 自动化请求过多后，预印本服务器会拦截整个浏览器

- 来源：使用 · 2026-10-10
- 现场：批量补取中，脚本在用户的 Chrome 里取了一篇 medRxiv 论文（成功）；之后用户在同一浏览器里打开该论文 v2 的 PDF，页面显示 Cloudflare 的“Sorry, you have been blocked / You are unable to access www.medrxiv.org”，没有可点的验证。用户：「这篇卡住了……回头再说」。
- 痛点：拦截落在用户自己的浏览器上，不只影响 agent；用户手动访问也被挡住。
- 为什么：medRxiv、bioRxiv 前面有 Cloudflare，短时间内来自同一浏览器的程序化请求（页面内 fetch、连续打开 PDF）会触发封禁；skill 对这类站点没有节流。
- 方向：对 medRxiv、bioRxiv 这类站点限速（每篇之间留足间隔、同一会话里少量请求），优先用它们的开放 API 或 Europe PMC 等镜像取全文元数据；出现封禁页时停止对该站点的一切请求并告诉用户，不要继续重试。
- 状态：已处理（v3）→ publishers.md：medRxiv / bioRxiv 节流；封禁页列为过不去的页面，本次不再访问那个站

### 36. 实在取不到的，走完一轮就停，事后列清单由用户逐条确认

- 来源：用户反馈 · 2026-10-10
- 现场：批量补取中，有些论文各条路线都走不通（学校代理不覆盖的出版社、未订阅的期刊、尚未公开的会议论文），重试只会重复同样的失败。用户原话：「实在找不到的就不要卡在那里一直循环浪费时间了，事后报告并记录即可，之后在一条一条由用户确认」。
- 痛点：反复重试与长时间等待占住用户的浏览器和时间，换不来新结果。
- 方向：
  - 每篇每条路线最多走一轮；失败原因分类记录（无权限 / 代理不覆盖 / 尚未公开 / 被站点拦截 / 门禁超时 / 找不到记录），不自动重试同一类失败。
  - 批次结束后给出一张“未取到”清单，每行写明原因、已试过的路线和可选的下一步（换开放副本、用户手动下载、存网页快照、放弃），由用户逐条确认后再处理。
  - 能自动过的人机验证（几秒内自行通过）照常等；要用户登录的门禁先通知用户，用户不在时不长时间空等，记入清单。
- 补充（同日）：加了一条新路线后，我把所有失败的条目整体重跑了一遍，包括新路线根本帮不上的类别（代理不覆盖、尚未公开），只多取到 1 篇，被用户叫停：「还在循环？获取不到就不要再试了，你这都重复几次了？」。规则：新办法只对它能解决的那一类失败重试一次。
- 补充（用户 2026-10-18：「最后确认那一遍的话，你汇报，然后依次帮我在浏览器打开」）：v3 的最后一遍（第 3 遍）先汇报还剩哪些、试过什么，再逐篇在前台窗口打开，每篇说明可以怎么帮，agent 同时自己操作；文件到了或用户说"跳过"就开下一篇。
- 状态：已处理（v3）→ 最多三遍，最后一遍用户在场；报告的“无法获取”逐遍列出每条路

### 37. 出版社取 PDF 的行为记录（供 `references/publishers.md`）

- 来源：使用 · 2026-10-10（约 35 篇批量补取，用户的 Chrome，已登录机构检索系统）
- 现场：
  - OUP（JAMIA、JAMIA Open）：页面内请求 PDF 链接常拿到空文档或 HTML，前面有 Cloudflare“请稍候…”（几秒内自行通过）；直接打开 PDF 链接时 Chrome 会下载文件，可以拿到。
  - ACM 数字图书馆：页面内请求 PDF 返回 403；用户在页面上点 PDF 按钮可以下载。
  - nature.com（Nat Med、Nat Biomed Eng）、NEJM AI、Science：PDF 链接返回 HTML，直接打开也是网页——多为机构未订阅；Science 经代理时是 “Host Needed”。
  - jamanetwork.com：经代理是 “Host Needed”，不经代理是 403，开放获取的 JAMA Netw Open 也一样；应改走 PMC。
  - PNAS、Patterns（Cell Press）、BMJ、Nature 正刊、CHI/FAccT 的出版社页面：`citation_pdf_url` 页面内请求即可拿到。
  - 机构检索系统（Primo）给某篇 JAMIA 论文的 PDF 链接，两次都下载到另一篇 JMIR 论文——检索系统的链接也要做身份核对（第 34 条）。
  - medRxiv：页面内取到 PDF 后不久，整个浏览器被 Cloudflare 封禁（第 35 条）。
- 方向：把上面写进 `references/publishers.md`，按“页面内请求 → 直接打开链接（下载由监控接上）→ 检索系统 → 开放副本（PMC、作者稿）”排路线，并按出版社给出首选路线。
- 另记一次未查明的现象：`attach_file.py` 有一次退出码非零、最后一行只有 `}`，库里没有生成附件；原样重跑一次成功。没有保留第一次的完整输出，原因未查。
- 状态：已处理（v3）→ publishers.md
