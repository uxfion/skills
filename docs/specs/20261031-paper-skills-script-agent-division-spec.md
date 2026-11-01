> 定稿 2026-10-31：用户的决策见 §9，三种视角的审查意见已并入（§11），advisor 已看过。实施中发现要改的，按 AGENTS.md 的规矩在实施完成前修正这份 spec。

# paper-fetch / paper-to-zotero / paper-read：脚本和 agent 重新分工

## 0. 为什么、按什么

拆分后实测经学校登录那条路时，暴露了两个问题（issue `20261030-paper-fetch-script-agent-division.md`）：
- 出版商的正版 PDF 因为题目太短“无法判断”，fetch 把它当成错文件，接着去试图书馆系统；
- 在图书馆系统的登录页停下后，没有人派浏览器 agent 去点。

五份调研（scratchpad `audit/`：文档、测试、脚本三份迁移对照，两份分工清点）证实这不是个例。三个 skill 里到处都是两类毛病：
1. **脚本越界替判断拍板：** 用正则、关键词、阈值去决定拿不准的分支；
2. **停下点没人接手：** 交接写得含糊，或者干脆没写。

另外拆分时还丢了一些东西：几处行为、一些文档内容、不少测试。

依据是 `docs/design-principles.md`。§1：脚本只做有把握的事；拿不准的停下来，带证据交出去；一件工作从脚本放手的地方起，由一个 subagent 负责到底。§3：通用、简单，从不打补丁。

2026-10-31 的实测证实了这个方向。照现行 SKILL.md 派出一个 sonnet 浏览器 agent，它自己点了 Sign in 和学校入口，单点登录直接登上，最后取到了正式版 PDF。但下载目录监视器没能把这个文件归位：题目太短，核对拿不准。

## 1. 整体思路

**三个通用机制，替换现在各处零散的停下、提示和匹配。**

1. **交接记录。** 脚本走到把握的边界，就写一条交接记录 `<dir>/handoffs/<slug>.<n>.json`，里面有：
   - `id`；
   - 要判断什么（`kind`）；
   - 谁接手（`taker`）；
   - 证据：文件路径，比如页面摘录、PDF 前两页的文字和图片、页面信息；
   - 能怎么答复。

   屏幕上只打一行短的（id、slug、kind、记录路径），主对话的上下文里不会堆满证据。`pf.py todo` 列出还没答复的交接。脚本自己接着做能做的事，有未答复交接的论文在原处暂停，重跑时脚本跳过它。这样同一个交接不会被派两次人。
2. **一条答复命令。** 任何答复都用 `pf.py answer <id> <答复> [--reason … --label … --why …]` 记下。它取代现在的 `claim --accept`、`claim --label`、`fetch --verdict`（以及它的 `--route` 规则）和 stop 事件。paper-fetch 的交接分五种：
   - `page`：拿不到 PDF 的页面；
   - `file`：拿不准的文件；
   - `label`：已归位、版本还没定的文件，取代现在的 `to_label` 行；
   - `left`：下载目录里谁也没认领的文件；
   - `browser_down`：浏览器本身出错。

   identify 给出的候选和警告只在开头出现一次，那时还没有每篇论文的流程，所以保持现在的输出行，谁接手写在 SKILL.md 的交接表里。p2z 用同一种交接记录，放在它自己的目录下（§4）。

   答复之后，重跑脚本，这篇从原处接着走。
   - **交接什么时候关：** 一份文件为这篇归位了（不管是 `fetch --start` 取到的、`claim --file` 交来的，还是监视器归位的），这篇未答复的 `page`、`file` 交接就自动记上 `got`。
   - **答复决定这篇往哪走：**
     - `blocked`、`gate_timeout`：留在原路线，下一遍再试；
     - `refuse`、`unknown` 和各种结论（`no_access`、`no_pdf` 等）：放它去下一条路线。
   - **暂停只管批量走动：** paper agent 对自己这篇跑的 `fetch --session`、`fetch --start` 不会被跳过。
3. **一篇论文一个 agent。** 脚本没走完的论文，每篇派且只派一个 sonnet paper agent。它有自己的浏览器会话（`pf-<slug>`），这篇的所有交接都归它，后面几遍也叫它接着做，不换人。同时最多 5 个，其余排队。

接手的一共四种：

| taker | 是谁 | 做什么 |
|---|---|---|
| `paper_agent` | 后台 sonnet，一篇论文一个，有自己的会话 | 这篇的 `page`、`file` 交接：打通页面后交回脚本去取；判断拿到的文件，定标签，用 `answer` 记下 |
| `judge` | 后台 sonnet，只读本地文件，成批 | 只差定标签的文件；谁也没认领的下载；identify 的候选；查库时是不是同一篇；整理时的判断 |
| `agent` | 主对话 | 派人、转告关口提醒、选版本规则、归到哪个分类，以及 subagent 答“不知道”之后的事 |
| `user` | 用户 | 输密码、过验证、拍板 |

主 agent 的循环：
1. 跑脚本，批量走完一遍；
2. 按论文派 paper agent，只差定标签的成批交给 judge；
3. 它们各自用 `answer` 记下结果，报回一行结论；
4. 主 agent 重跑脚本收尾。

## 2. 一个例子：Mask R-CNN 加另一篇，经学校登录取全文

1. `identify` 认出两篇；arXiv 一次批量查完。
2. `fetch --pass 1`：
   - Mask R-CNN 在出版商那里拿到 PDF，核对时题目太短，脚本没有把握，于是写交接 `he2020mask.1`（`kind: file`），证据是前两页的文字和图片、页 1 上的 DOI、署名。这篇在出版商这一步暂停。
   - 另一篇停在登录页，拿不到 PDF，写交接（`kind: page`），证据是网址、页面标题、试过的链接。这篇也暂停。
   - 这遍正常退出，屏幕上是两行短的交接。
3. 主 agent 给两篇各派一个 paper agent：
   - Mask R-CNN 的 agent 读证据文件，判断“是这篇，IEEE 正版”，跑 `pf.py answer he2020mask.1 accept --reason … --label Published-IEEE --why …`。
   - 另一篇的 agent 在 `pf-<slug>` 里点 Institutional Sign In 和学校入口，登上后找到 PDF 的地址，用 `fetch --start <地址> --session pf-<slug>` 交回脚本去取。证据、核对、归位都由脚本照常完成，页面上的版本标签它刚看过，接着自己定标签。碰到密码页，它把页面推到前台，通过主对话推送提醒用户，等用户过了接着点。
4. 两个 agent 各报回一行；主 agent 重跑 fetch，两篇都有了想要的版本，这遍结束。

## 3. paper-fetch（第一期）

### 3.1 核对：三种结果

| 结果 | 什么时候 | 去向 |
|---|---|---|
| 通过 | 完整题目出现在第 1 页 | 归位到 `results/` |
| 确定不是 | 不是 PDF；出版版文件页 1 印着另一篇的 DOI；HTML 页面没有正文 | 进 `unverified/`，这篇接着试下一个候选 |
| 拿不准 | 其余一切：题目太短、没有文字层、找不到题目、只在第 2 或第 3 页（引用它的论文也会把题目印在前几页）、只凭题目词重合、题目对上了但页首像勘误或补充材料 | 文件扣在 `unverified/`，写 `file` 交接，这篇在这条路线上暂停 |

- `file` 交接能答三种：
  - `accept`（可以带标签）：文件归位；
  - `refuse`：这篇接着往下走；
  - `unknown`：这篇接着走后面的路线，文件留着备用。这一遍走完还没有更确定的文件，就先用它，它的核对结果记 `unconfirmed`，p2z 照样挂上，报告里列给用户看；之后拿到确定的文件，就换成确定的那份。这符合“拿不准不卡交付”。
- 判断和定标签合成一次查看：这篇的 paper agent 读前两页（文字加图片），同时回答“是不是这篇”和“是哪个版本”。
- claim 事件记下核对的全部证据（题目词、页 1 上的 DOI、署名），证据文件从这里生成。
- stub（没有元数据可对照）照旧：文件归位，`check: cannot_judge`。对不对，交给下游认出条目的那一步（p2z 的 connector 路径）去看。
- 删掉没人用、或者只用来改个说法的匹配：`cover_page_suspected`、`collection_suspected`、`DENIAL_RE`。

### 3.2 文件按内容认，一篇可以有几个版本（决策 A）

- 文件名照旧按它被当作哪个版本取来（`<slug>[.版本].pdf`），名字已被占时加序号（`<slug>.2.pdf`），不再挪进 stray/；内容相同（md5 一样）的就是同一份。标签事件改用 md5 对应文件，不再用文件名，所以改名不会丢标签。
- 结果文件里写明想要哪个版本（`wanted`，默认是正式版，调用方另有规则时从其规则）。
- “这篇有文件了”改成：有一份标签定为想要版本的文件。版本次一级的文件不会让这条链停下：这篇在同一遍里接着走后面能给出想要版本的路线（出版商、图书馆系统）。
- 时间上是这样：文件的版本靠标签定，标签在这一遍走完时才定（paper agent 或 judge 答复）。所以走动当中，一份还没定标签的文件先算这篇已有文件；标签定下来、低于想要的版本时，这一遍的重跑里这篇接着走后面的路线。重跑会跳过已经试过的候选，开销很小。
- 标签定为 `Unknown` 的文件也算“不是想要的版本”，这篇同样接着去找想要的版本；找不到，就用它。
- 拿到想要的版本，它就是这篇的文件；先前那份作为另一个版本保留，`files` 里都列着，p2z 都挂上，标题照各自的标签。
- 所有原来按“第一个文件”判断的地方，一起改成按这个规则判断：fetch 的待办、has_file、下载等待、监视器的 wanted、`label` 交接、标签的默认文件。
- p2z 的 superseded 只在同一版本内比较（比如 arXiv 的 v2 和 v3），不跨版本，不会把接受稿当成被正式版取代而建议删掉。

### 3.3 fetch：遇到页面不停整条命令

- 一个候选停在拿不到 PDF 的页面上，就写 `page` 交接，这篇在这条路线上暂停，其余论文照走。
- 删掉 `GATE_TITLE`、`GATE_TEXT`、`SIGN_IN_CONTROL`、`SIGNED_OUT`：是不是关口、要不要点登录，由 paper agent 看了页面再定。
- 检索系统：结果里没有标题对得上的链接，也写 `page` 交接，不再记 `not_in_discovery` 关掉这条路线。检索地址改成配置里带 `{title}` 占位符的模板，代码里不写 Primo 的参数。
- 一页上的第一个 PDF 没通过核对，接着试第二、第三个候选（最多 3 个，这个数是我定的）。
- 内层阅读页（比如 IEEE 的 stamp.jsp）停下时，它的信息也留作证据，不丢。
- 浏览器本身出错是确定的事实：Browser 把 OpenCLI 的错误码交出来，扩展没连上、附着失败这类就写 `browser_down` 交接，这遍停下。taker 先是 `agent`（`opencli doctor`、`opencli daemon restart`），不行再交 `user`。
- 限速按实际请求的主机算：identify 在 doi.org 的 API 上碰到的 429，不拦浏览器去打开 doi.org 跳转后的出版商页面。
- 每次退出都把这遍拿到、版本还没定的文件写成 `label` 交接。
- `fetch.jsonl` 现在可能有七个写入者（主对话、5 个 paper agent、监视器），一条证据可能超过一次原子追加的长度，所以追加时加锁（用限速记录现成的那把锁）。
- 检索地址改成模板是配置格式的变化：`ready` 发现旧写法就报出来，让主 agent 改。
- `fetch` 加 `--session`，paper agent 用它只跑自己这篇；`fetch --start <url> --session pf-<slug>` 是 agent 把页面打通后交回脚本的方式。`wait` 也加 `--session`。
- paper agent 自己在浏览器里下载的文件，用 `claim --file <path> --slug <slug>` 交给脚本，归属明确。监视器保持现在的规则不变：一份下载只对一篇确定通过才归位，否则留在原处、记 `left`。`left` 的文件成批交给 judge，对照还在等文件的论文看。
- 碰到拦截（决策 3，不做 agent 之间的协调）：你能过的验证是关口，paper agent 推到前台，通过主对话推送提醒，最多等 5 分钟，等不到就答 `gate_timeout` 并报回，之后主 agent 再叫它接着做；其余拦截，这个 agent 这次运行不再碰这个网站，答 `blocked`。这篇在原路线上暂停，不转去别的路线，下一遍再试。

### 3.4 identify

补回迁移丢掉的：
- 重跑时保留 `slug_given`；
- bib 里原样的 citation key 记进结果的 `cite` 字段，slug 仍只当文件名。已有的结果被再次认领、又给了 key 时，也要把 `cite` 写上（现在这条路径直接返回，不写结果）；
- 某个来源这次没答，就保留它上次的答案；
- arXiv 按批查，每 100 个 id 一个请求；
- “记录里的 DOI 和请求的不同”这条警告恢复；
- Crossref 的 `event.name` 恢复成会议名；
- 恢复“页面和预印本作者数不一致”“旧条目没有 arXiv 号”这两条警告；
- 页面上非 ISO 格式的日期（“10 December 2023”）正确解析，不再读成 `10-2023`。

另外：
- `--search` 列出 Crossref 的前 5 条，带作者、相似度，第一作者对不上的标出来，不再按 0.9 过滤；从中选哪条，交给 judge 或主 agent。
- 正式版页面拒绝普通 HTTP 请求（`page_unreachable`）：交给一个 agent，用浏览器存下页面 HTML，再跑 `identify --redraft --html <文件> <页面网址> <结果>`，用 identify 现有的页面解析器填好结果里的 CSL。这样 fetch、核对、draft_item 都照常工作。
- 摘要、PMID、作者关键词：由 identify 自己按 DOI 查 OpenAlex 和 Europe PMC，和 arXiv 一样按批查（OpenAlex 一次能查多个 DOI），照常限速，补进 CSL，不再由 agent 一篇一篇手查。几个来源说法不一致时，交给 agent。审查曾建议复用 fulltext_links 已经拿到的回应，没有采纳：结果文件只由 identify 和 settle 写，这条规矩比省一次请求更要紧。
- 认论文阶段的交接，在 SKILL.md 的交接表里写明 taker：题目要靠浏览器检索才能认准的，交给浏览器 agent；预印本的正式版候选要不要认，交给 judge；勘误信号要打开文章页看的，交给浏览器 agent。

### 3.5 限速放在一处

请求间隔和 429 停止的记录，从每个工作目录各一份（`<dir>/pace.json`），改成每台机器一份（`~/.cache/paper-fetch/pace.json`）；环境变量 `PAPER_FETCH_PACE` 可以另指，测试都用它指到自己的临时文件。限速是对网站的礼貌，跟工作目录无关；批量给库里附件定标签时，即使一个文件一个目录，也共用同一套间隔。现有的文件锁照旧负责并发。

### 3.6 结果里的 `outcome`

- `waiting`：这篇有未答复的交接，不再看 stop 事件的 `gate` 字段；`waiting_on` 列出在等哪几种交接（`page`、`file`、`label`），不另开状态。
- 用的是答了 `unknown` 的文件时，状态照常是 `got`，那份文件的核对结果是 `unconfirmed`。
- 最近一次的停下或答复（原因、路线），都写进 `outcome.last`，报告里“无法获取”的原因不再因为记了结论而丢掉。
- p2z 的 attach_file 对 `waiting` 报 `no_file_yet`，带上 `waiting_on`（现成的代码），报告按在等什么分别列出。

## 4. paper-to-zotero（第二期）

- **查库。**
  - DOI 和 arXiv 号对上，才算确定是同一篇。
  - 按题目找到的条目都作为候选，按相似度排序，最多 10 条（这个数是我定的）。除了现在的标题搜索，再用去掉副标题、去掉标点的宽松检索补候选，因为 Zotero 的快速搜索要求每个词都出现，题目稍有改动的条目会搜不到。每条候选带证据：题目、年份、第一作者、DOI 或 arXiv 号、条目类型、附件标题。
  - 写 `same_paper` 交接（judge，记录放在 `<scratch>/paper-to-zotero/handoffs/`），能答四种：同一篇、不是、预印本和正式版的一对、不知道。“一对”和“不知道”都交给用户，在报告里列出来。答复用 `p2z.py answer` 记下，它写的就是 `same_as` 或 `distinct_from`，不用手改记录。
  - lint 找重复条目也用同一套候选，导入和整理对“重复”的判断不再各说各的。
- **同一个 DOI 在库里有两条：** 进 `decide`，由主 agent 选一条，或者按 organize.md 先合并（要用户同意）。
- **一个“已接受”字段：** 记录里新增 agent 字段 `accepted`，里面列字段检查的条目、draft_item 的警告。接受了的就不再每次重跑都列成待定。字段检查和警告是同一套机制，不各开一个字段。
- **draft_item 读进 identify 补进来的字段：** 作者关键词作为第 1 类标签，PMID 写进 Extra（`PMID: <n>`），摘要写进 abstractNote。
- **lint 只报有把握的事实和证据：**
  - `url_not_record` 只报“网址不是 doi.org/<DOI>”和主机名；只有网址为空时才给补丁；场馆的例外交给 agent。
  - `abbreviation_misplaced`、`looks_abbreviated` 只列值，不给补丁。
  - `name_not_tagged` 的关键词正则删掉，改为把摘要和标签交给 judge。
  - `label_clash` 比较两份文件的 md5：md5 相同就是同一份文件，确定；不同就是一个标题下有两份文件，交给 paper-fetch 定标签。
  - 交给 judge 的整理判断成批给，每个 judge 约 20 个条目（这个数是我定的）。
  - `missing_doi`、`missing_abstract`：用 identify 的 `--search` 和补全字段那一步去找，候选交给 judge 选。
- **批量写入的小脚本：**
  - 把 paper-fetch 结果里的标签批量写成库里附件的标题（拆分 spec §4.1 本来就这么定的，代码没做）；
  - 按文件批量打补丁；
  - `remove_tags`。
- **没有 DOI 的论文走 connector：** 发送、轮询、写 `saved` 由脚本做；认出来的条目对不对，交给 judge 看。
- **笔记：**
  - `note put` 收到空内容就拒绝（`empty_note`），这是迁移丢的；
  - 新建笔记前，先看同一个父条目下有没有同标题的笔记，有就报出它的 key。
- **记录跟着结果走：** paper-fetch 给结果改名时，在新结果里记 `renamed_from`；p2z 的记录按 slug 找结果，找不到就按 `renamed_from` 跟过去，不会成为孤儿记录、也不会重复起草。
- 每个 p2z 停下点在 SKILL.md 的交接表里写明 taker。

## 5. paper-read（第二期）

- 一条脚本命令准备笔记文件：已有就取出来，没有就用骨架新建，文件名按约定；同时存一份取出时的副本，供 check_note 比对。
- “PDF 是不是这篇”：这份 PDF 是 p2z 从 paper-fetch 核对过（`ok` 或 `accepted`）的结果挂上的，就算确定；其余交给 judge。题目一致不算确定，短题目尤其不能。
- check_note 补查三项：Q1–Q6 都在；对照取出时的副本，front matter 和 `## 用在哪里` 没被改。
- 查完论文之后，结构化包要存回去（`structured put`），写进两个完成条件里。
- 一个条目下有两条“论文笔记”时：交给主 agent 合并，再存回。

## 6. 文档要补回、要改的

- **每个 SKILL.md 加一张交接表：** 每种 `kind` 对应谁接手、brief 写什么、能怎么答复。
- **paper agent 的 brief 写进 SKILL.md**，每次派人照着填：
  - 它负责哪篇（题目、DOI、想要的版本），这篇的交接记录路径，它的会话名 `pf-<slug>`；
  - 怎么读页面、怎么点；
  - 打通后怎么交回脚本（`fetch --start … --session`），自己下载的文件怎么交（`claim --file`）；
  - 怎么答复（`answer`），碰到关口和拦截怎么办；
  - 设计原则 §6 的上网规矩，自己不再派 agent；
  - 报回什么：一行结论。
- **paper-fetch 的 SKILL.md 和 gate.md 按 paper agent 重写：**
  - 关口由碰到它的 paper agent 处理，不再看 fetch 的 `gate: true`；
  - batch.md 里“浏览器只有主对话一个驾驶者”那句删掉，并发改成最多 5 个 paper agent。
- **publishers.md 加 2026-10-31 实测的三条带日期提示，不写学校名：**
  - 记录页上的全文链接会在会话之外开新标签页，要用 `open` 在会话里打开；
  - Zotero Connector 会把 IEEE 的网址自动重定向到学校代理；
  - stamp.jsp 把 PDF 嵌在 iframe 里，Chrome 不会自己下载，交给 `fetch --start` 去取。
- **迁移对照找到的：**
  - 正式版页面拒绝普通 HTTP 请求时怎么办（见 §3.4）；
  - 批量给库里附件按版本改名的细则：每个 judge 约 20 个文件、要看两页图片的理由、arXiv 先批量查、共用限速；
  - 查完论文把结构化包存回去；p2z 的依赖表加上 paper-read；
  - 打标签的 subagent 最多 5 个；
  - 不能开后台进程时，靠 fetch 自己扫描下载目录；
  - 用户下载了不在这次运行里的论文：identify、claim 之后，在 p2z 里接着 draft_item、prepare、save；
  - 收尾的完成条件要看到 “tab lease released”；
  - 一次性的代码放进 `scratch/`；
  - 用户自己写的笔记不动；
  - 快照会作为附件挂上、列在“无法获取”里、标题是 `Snapshot-<Source>`；
  - 修正 5 处指针；
  - `publishers.md` 里残留的 `doi_to_item.py` 改成现在的命令。

## 7. 测试

都写在脚本的接缝上，每个测试覆盖一整个行为。

- **新流程：**
  - 一遍跑完不在第一个页面停住，写出 `page` 交接，重跑时跳过；
  - 拿不准的文件写 `file` 交接，答 `accept`、`refuse`、`unknown` 之后各走各的路；
  - 一页上第一个 PDF 失败后接着试下一个；
  - 浏览器出错时写 `browser_down`；
  - 接受稿之后接着拿到正式版，两份都列在结果里，这篇的文件是正式版（决策 A）；
  - 标签定为 `Unknown` 的文件，这篇接着找想要的版本，找不到就用它；答 `unknown` 的文件这一遍走完先用上，之后被确定的文件替换；
  - `answer` 记下各种答复；
  - 限速记录可以另指，测试互不影响。
- **补回丢掉行为的：**
  - 空笔记被拒；
  - 来源没答时保留上次的答案；
  - `slug_given` 重跑后保留；
  - 原样的 citation key；
  - arXiv 批量；
  - `--search` 带作者；
  - 两篇推导出同一个 slug 时加 `-2`；
  - LNCS 章节起草成会议论文；
  - `note put` 的其他拒绝；
  - Crossref 429 的两条路径；
  - 页面 description 里的摘要；
  - 非 ISO 日期。
- **库代码的行为，在用到它的脚本测试里补断言，不另开单元测试模块：**
  - 附件标题的生成和解析：通过 `answer … --label`；
  - 站点表：通过 fetch 的 proposal；
  - 代理主机名：通过 fetch 的 request_url；
  - 机构配置：通过 ready；
  - `fetch.jsonl` 坏行：通过 settle；
  - `pf.py` 的冒烟测试。
- p2z：查库候选交给 judge；同一 DOI 两条进 `decide`；`accepted` 字段生效。

## 8. 实施顺序和验收

分两期。第一期是 paper-fetch，带它自己的实测验收；第二期是 paper-to-zotero 和 paper-read，吸收第一期实测学到的东西。

1. **spec 定稿：** advisor 看过，用户确认。
2. **第一期，paper-fetch：**
   - 共用部分先由我在主对话里写：交接记录和 `answer`；核对的三种结果；按 md5 认文件和 `wanted`；限速放在一处；`outcome`。
   - 然后做 fetch 的流程和 identify 的补回。
   - 文档：交接表，SKILL.md、gate.md、batch.md、publishers.md，补回 §6 里属于 paper-fetch 的部分。
   - 结果文件的格式变了（`cite`、一篇几个版本的文件、`outcome` 的新状态、按 md5 记标签），所以 p2z 读这些的地方同期改好，第一期就包含：draft_item 用 `cite`；attach_file 挂上所有版本、读新的 `outcome`，核对结果是 `unconfirmed` 的文件也挂上并报出来；report；superseded 只在同一版本内比较；契约 fixture 重新生成，p2z 的契约测试照常通过。否则两遍之间一保存就会出错。
   - 测试全部通过。
   - **验收实测**，严格按 SKILL.md 当 agent 来跑：
     - Mask R-CNN 走完整一遍：出版商拿到 PDF → `file` 交接 → paper agent 判断接受 → 归位，不去图书馆系统；
     - 只跑图书馆系统那条路：`page` 交接 → paper agent 点 Sign in 和学校入口 → 打通后用 `fetch --start` 交回脚本 → 拿到 PDF；
     - 一篇开放获取只有接受稿的论文：接着走出版商，拿到正式版，两份都在（决策 A）。
3. **第二期，paper-to-zotero，然后 paper-read：**
   - 互不依赖的模块派 subagent 并行写，都写到同一套接口上，由我整合；文档、测试同上；
   - 实测：导入和保存一批论文；整理的 dry run（lint 只给证据，判断交给 judge）。

实测建的条目最后都进回收站，scratch 清理干净，不提交任何个人信息。

## 9. 已定

1. **一篇论文拿到的文件不是想要的版本时：** 2026-10-31 用户选方案 A，见 §3.2。代价是：开放获取版本不是正式版的论文，要多走几次经学校的请求，每次间隔 15 秒。另外两个方案：B 维持“第一个文件说了算”，只修 stray/ 的问题；C 只多试出版商那一步。
2. **派 subagent 以什么为单位：** 2026-10-31 用户选方案 A：脚本先批量跑一遍；之后脚本没走完的论文，每篇派且只派一个 sonnet paper agent，有自己的会话，负责这篇的全部剩余步骤，后面几遍还叫它接着做；只差定标签的成批交给 judge。同时最多 5 篇，不按出版商排队。用户原话：「A  限流不是很担心，因为我们最多同时跑的时候会有限制嘛，最多是5篇论文同时，还是最多几篇同时.我觉得，有时候机器人限制或者人机验证限制比较严，应该就最多5个同时跑就好了」。以前定的是“一个 subagent 负责一次完整的尝试”（restructure spec 2026-10-20），现在单位从一次尝试扩大到一篇论文。
3. **一个 agent 碰到拦截时，其他 agent 怎么办：** 2026-10-31 用户选不协调：每个 agent 碰到拦截就自己停下、自己报告；这篇在原路线上暂停，不转去别的路线。用户原话：「如果就因为人机验证或者限速等限制，你就直接转头去其他地方查了，那这个查询的记录不就没了吗？这条路径不就直接被你否定掉了吗？」，「我觉得现在应该用方案 3，也就是最简单的方式去实现，后面碰到问题了再说。不要从一开始就把系统做得很复杂，我感觉是没必要的」。
4. **按原则推翻的三条旧约定**（已告诉用户，用户没有异议）：
   - 摘要、PMID、作者关键词改由脚本自动补（拆分 spec §11 原来定的是 agent 手查）；
   - lint 用来找模型名的正则删掉，改交 judge（restructure spec §9 原来定的是保留）；
   - 没有 DOI 的论文走 connector 那段，改由脚本做（restructure spec §9 原来定的是不写脚本）。

## 10. issue 去向

- `20261030-paper-fetch-script-agent-division.md`：由这份 spec 解决。
- `20261030-paper-to-zotero-short-title-cannot-judge.md`：§3.1 解决。
- `20261030-paper-to-zotero-proxy-login-not-a-gate.md`：§3.3 解决，它原来提的识别密码框这个方向不采纳。
- `20261030-paper-to-zotero-cvf-link-missing.md`：CVF 写进 publishers.md，作为带日期的提示，由 agent 去找，不在 fulltext_links 里写某一家的代码。
- `20261020-paper-to-zotero-cross-origin-frames.md`、`20261021-paper-to-zotero-ieee-akamai-rate-limit.md`：停下的页面在新流程里有 paper agent 接手；第一期实测之后再看要不要关。

## 11. 审查意见怎么并入的

三种视角的审查（需求忠实度、对照代码的技术正确性、新 agent 照着跑会不会卡住，报告在 scratchpad `audit/review-*`）找到的问题，归进了几个通用机制，没有逐条加规则：

- **交接记录、`answer`、未答复就暂停：** 解决了重复派人、`--verdict` 要不要带路线、stop 事件和“停下不算一次尝试”的冲突、主对话上下文堆满证据、新 agent 不知道怎么记答复这几个问题。
- **一篇一个 paper agent，打通后用 `fetch --start` 交回脚本：** 解决了浏览器 agent 拿到的文件又被另一个没见过页面的 judge 重判、agent 下载的文件丢证据、关口归谁说不清这几个问题。
- **按 md5 认文件和 `wanted`：** 让决策 A 能在现在“一篇一个文件位”的结构上做通。
- **“不知道”这一种答复：** 补上了“判断不了时文件没有去处”的缺口。
- **限速记录可以另指：** 测试不会污染真实运行。
- **放弃的做法：** 原稿里“监视器扣下拿不准的下载”这一条放弃了。同时等好几篇时它很少成立，只等一篇时又会抓走用户自己下载的文件。现在改成 agent 用 `claim --file` 明确交出自己下载的文件，监视器维持现状。
- **stub 维持现状**，免得破坏契约测试和 connector 那条路径。
- **库代码的测试**改在脚本的接缝上补，不另开单元测试模块，和设计原则一致。
- **page_unreachable**：用 identify 现成的页面解析器读 agent 存下的 HTML。
- **补全字段**：由 identify 自己查，守住结果文件的单一写入者。
