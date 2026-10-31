# paper-to-zotero 拆成三个 skill：paper-fetch、paper-to-zotero、paper-read（设计）

> **草稿第二版**（2026-10-30）。第一版过了三份审阅：是否忠于决定、技术对不对、新 agent 能不能照着做。这一版按审阅改过，advisor 审过一轮，给用户看过以后又自审了一轮（§14 记了改了什么）。实现过程中如有修正，直接改本文。
> 来源：
> - [20261029-paper-to-zotero-split.md](../issues/20261029-paper-to-zotero-split.md)：拆分、交接、笔记的格式和转换，已定 1 到 23；
> - [20261028-paper-to-zotero-paper-notes.md](../issues/20261028-paper-to-zotero-paper-notes.md)：论文笔记的读法和格式，拆分后归 paper-read。
>
> 依据放在两张 issue 旁边的参考资料文件夹里，git 不跟踪。关 issue 时文件夹会删掉，要点已经写进本文，实现时不必回去翻。拆分这张的文件夹里有：
> - `inventory.md`：commit `ae09458` 时各部分代码的去向；
> - `reselect-blind.md`、`blind-eval/triage.md`、`blind/notes.md`：读回器的盲测、失败分类、编辑器 schema 的事实；
> - `markdown-tools.md`、`pandoc-retest.md`、`passthrough-tools.md`：Markdown 工具的选型；
> - `metadata-and-pdf-comparison.md`：元数据和找 PDF，我们的做法和 Zotero 自带的比较；
> - `zotero-external-interfaces.md`、`better-notes-external.md`：Zotero 和 Better Notes 从外面能怎么用。
>
> 论文笔记那张的文件夹里有 `zotero-notes-storage.md`、`better-notes.md`、`note-roundtrip-test.md`。
>
> 文中的行数都是估计，不是要求。

## 0. 一句话

p2z 现在同时在做五件事：查库写库、认论文、取全文、读论文、跑一次导入。拆开以后是三个 skill：
- **paper-fetch**：从"一篇论文"到"手上有核对过的 PDF"；
- **paper-to-zotero**：只管 Zotero 里的东西；
- **paper-read**：从 PDF 到论文笔记。

三者只靠临时目录里的文件交接，各自能单独用，也能在一次导入里接起来。笔记在 Zotero 外面是一份带 front matter 的 Markdown，由 p2z 的 `note_md` 在 Markdown 和笔记 HTML 之间来回转换，不丢内容。

**这次只拆，不改行为**：同样的输入，拆分后建出的条目、附件标题、标签和拆分前一样，例外列在 §11。元数据上该补的改进放进 §13，以后单独做。

## 1. 为什么拆

用户的原话在 issue 开头。要点：
- p2z 的 SKILL.md 有 3.3 万字符，references 有 6.6 万字符，脚本约 8.7k 行。其中约 2 万字符讲的是认论文、取全文和上网规则。
- 13 张 issue 里有 6 张出在取全文这边，这一块变得最快。
- 这违背了 `skill-design-conductor-principle` 的"Orchestrate, don't absorb"。

记录文件里每一块本来就只由一个脚本写，所以拆分的缝早就在数据里。

## 2. 三个 skill 各管什么

| skill | 管什么 | 交出什么 | 不做什么 |
|---|---|---|---|
| **paper-fetch**（新） | 认出是哪篇论文；查元数据（CSL）和有哪些版本；找全文并下载，路子包括开放获取、出版商、学校登录、用户的浏览器、验证页；核对 PDF 是不是这篇、是哪个版本，给出版本标签。上网的一切规则都归它 | 每篇一个结果文件，加上 PDF（§3.3） | 不碰 Zotero |
| **paper-to-zotero** | Zotero 里的一切：查库；建条目（CSL 按 Zotero schema 的对照表转成条目）；挂附件、分类、标签；改字段、合并、删除、整理；导出 bib；存取笔记；存取结构化包。导入时由它编排 paper-fetch 和 paddleocr | Zotero 里的条目、附件、笔记、结构化包；从 Zotero 取出的文件 | 不上网 |
| **paper-read**（新） | 从 PDF 到论文笔记：经 p2z 取 PDF 和结构化包，缺包时调 paddleocr；派用 opus 的 subagent 按问题树读；定笔记的格式和改笔记的规则（问题清单、问题树、"用在哪里"、"待重看"、主题笔记） | 笔记文件，交给 p2z 存 | 不直接调 Zotero 的接口，不上网找论文 |
| paddleocr（已有，不改） | 把 PDF 解析成结构化包 | 结构化包 | |

**边界**（已定 4）：
- **PDF 相关的判断归 paper-fetch**：核对 PDF、判断版本、附件标题的规则、去代理前缀，都归它。p2z 直接拿它给的标签当附件标题。库里的 PDF，或者用户自己拖进来的 PDF，要定标签时也交给 paper-fetch（§4.1）。
- **条目用哪个版本，归 p2z**：预印本和正式版都有时，选哪个作为条目，由 p2z 决定。
- **笔记**：存取归 p2z，内容和格式归 paper-read。
- **结构化包**：存取归 p2z，解析归 paddleocr，谁发现缺包谁去调。
- **不归这三个的**：按主题找论文，交给 papers-cool-search 或 Google Scholar。
- **paper-read 的外援**：要补充材料时交给 paper-fetch，要看代码仓库时用 `gh`。
- **先导入再读**：库里没有的 PDF 要先导入，因为笔记的家在 Zotero。

## 3. skill 之间怎么交接

### 3.1 临时目录（已定 11）

**临时目录**（英文 scratch directory）：当前会话有 scratchpad 就用 scratchpad，没有就用 `${TMPDIR:-/tmp}`，下文写作 `<scratch>`。文档和代码里一律这么叫，并给出路径；不单说"工作目录"，也不说"它自己的目录"。

| 场合 | 路径 |
|---|---|
| 一次导入 | `<scratch>/paper-to-zotero/`。其中 `fetch/` 给 paper-fetch，`records/` 放 p2z 的记录 |
| 单用 paper-fetch | `<scratch>/paper-fetch/` |
| 读论文 | 结构化包取到 `<scratch>/<cite>.<附件标题>/`，笔记文件放在它旁边 |

- **用完就清。**例外是下到了却没能进 Zotero 的 PDF：先报告给用户，不直接删。
- **单用 paper-fetch 时，PDF 就是交付物**：用户说了放哪里就放哪里；没说，就留在临时目录，在汇报里给出完整路径，不自动清。
- **最后留下来的**只有 Zotero 里的东西：条目、PDF、结构化包、笔记。项目里只留项目自己的决定。

### 3.2 一次导入怎么走（例子）

用户说"把 U-Net 那篇导入 Zotero，放进 diffusion 分类"：

1. **准备**：p2z 的 `ready` 检查 Zotero，建 `<scratch>/paper-to-zotero/`；paper-fetch 的 `ready` 检查 OpenCLI、Downloads、poppler，建 `fetch/`。
2. **认论文**：agent 按 paper-fetch 的"认一篇论文"，把题目落到编号 arXiv 1505.04597，再跑 `identify`。它写出 `fetch/results/<slug>.json`，里面有编号、CSL 和版本：除了预印本，还有 MICCAI 2015 的正式版，DOI 是 `10.1007/978-3-319-24574-4_28`。这一步不下载。
3. **选版本**：agent 看结果文件的 `versions`，按 p2z 的规则选：正式版优先，留预印本要写明理由。规则写在 p2z 的 `references/import.md`，用的数据来自 paper-fetch 的结果文件。这里选正式版，于是跑 `identify --redraft <DOI> fetch/results/<slug>.json`，原地把这份结果文件换成正式版的 CSL。预印本的编号、题目、摘要、作者留在 `versions.preprint`，题目也进 `alt_titles`。
4. **建记录**：p2z 的 `draft_item` 读这份结果文件，建 `records/<slug>.json`，按 CSL 生成条目；接着 `prepare` 查库、预览。版本在建记录之前就选好了，所以条目只生成一次。如果留的是预印本，agent 在记录里写上 `keep_preprint` 和理由。
5. **取全文**：条目在库里还没有 PDF，agent 就把这份结果文件交给 paper-fetch，走现在第 3 步的那条链：
   - `fulltext_links` 列出能去的地方；
   - `fetch` 一轮一轮地试；
   - `claim` 核对下到的文件；
   - 需要时 `wait` 等用户过验证页。

   过程都追加进 `fetch/fetch.jsonl`。这几个命令每次结束时，都会把过程汇总进结果文件的 `files` 和 `outcome`。后台监视器后来才收到的文件，要再跑一次 `settle` 才会汇总进去。下到的文件标签是 `Published-Springer`。
6. **建条目、挂附件**：p2z 的 `save` 建条目、挂 PDF、归类、打标签，这些都记进 p2z 自己的记录。
7. **结构化**：缺结构化包，就调 paddleocr 解析，再用 `structured put` 存回 Zotero。
8. **汇报，清掉临时目录。**

读论文只在用户要求时才做，由 paper-read 负责，最后经 `note.py put` 存进 Zotero。

**交接是双向的**：取哪个版本的全文，取决于选了哪个版本。选的规则归 p2z，选的依据是 paper-fetch 结果文件里的 `versions`。选择只有一条路到达 paper-fetch：agent 带着选定的编号去跑 `identify --redraft`，再把那份结果文件交给取全文的脚本。paper-fetch 从不读 p2z 的记录，p2z 也从不写 paper-fetch 的文件。

### 3.3 paper-fetch 的结果文件

**目录布局**：`<dir>` 是 `<scratch>/paper-fetch/`；导入时，是 p2z 用 `-o` 传入的 `<scratch>/paper-to-zotero/fetch/`。
```
<dir>/results/<slug>.json      结果文件，每篇一个
<dir>/results/<slug>.pdf       文件放在结果文件旁边，按要的版本命名，和现在一样：
                               <slug>.pdf  .accepted.pdf  .preprint.pdf  .supplement.pdf  .html
<dir>/links/<slug>.json        全文链接清单（fulltext_links 写）
<dir>/fetch.jsonl              过程记录，一行一个事件，只追加
<dir>/pace.json  run.json  .started  inbox/  stray/  unverified/  scratch/
```
p2z 只读 `results/` 下的结果文件和文件。其余都是 paper-fetch 自己的过程文件。

**slug**：调用者可以用 `--slug` 指定。比如 p2z 知道引用键时，就传 .bib 里的键或用户给的键。不指定时，paper-fetch 按现在的规则起名。结果文件里记下 `slug_given: true/false`。

下面是第 3 步重认之后的样子：`request` 还是最初给的 arXiv 号，CSL 已经换成正式版的。
```jsonc
{
  "slug": "ronneberger2015unet",
  "slug_given": false,
  "request": {"given": "1505.04597"},                 // 让它认的是什么：编号或网址
  "record_of": "published",                          // 这份 CSL 描述的是哪个版本：preprint | published
  "ids": {"doi": "10.1007/978-3-319-24574-4_28", "arxiv": null, "pmid": null, "pmcid": null},
  "csl": { … },                                      // 规范过的 CSL，见下
  "alt_titles": ["…"],                               // 论文还用过的题目
  "versions": {
    "preprint":  {"ids": {"arxiv": "1505.04597"}, "latest": "v1", "comment": "conditionally accepted at MICCAI 2015",
                  "title": "…", "abstract": "…", "author": [ … ]},
    "published": [{"ids": {"doi": "…"}, "venue": "MICCAI", "year": 2015, "title": "…", "title_differs": false,
                   "type": "paper-conference", "sources": ["arxiv", "crossref"]}],
    "incomplete": []                                 // 没有应答的来源
  },
  "files": [{
    "name": "ronneberger2015unet.pdf", "md5": "…", "kind": "published",
    "label": {"title": "Published-Springer", "version": "published", "source": "Springer", "detail": [], "by": "agent", "why": "…"},
    "check": "ok",                                   // ok | accepted（另带 accepted_reason）| cannot_judge
    "url": "https://link.springer.com/…",            // 已去掉代理前缀
    "evidence": {"page": {…}, "link": {…}, "file": {…}}
  }],
  "outcome": {"status": "got", "tried": ["link.springer.com"], "stop": null},   // got | not_got | waiting
  "warnings": ["…"],
  "settled_at": "2026-10-30T12:00:00+08:00"          // 最后一次汇总的时间
}
```

**CSL 要先规范，这件事归 paper-fetch。**对 Crossref 的 DOI，doi.org 给的 CSL 用的是 Crossref 的词，而 Zotero schema 的对照表按 CSL 的词来查。DataCite（arXiv）和 mEDRA 给的本来就是 CSL 的词，不用动。要做的是：
- **类型**改成 CSL 的词：`journal-article` 改成 `article-journal`，`proceedings-article` 改成 `paper-conference`，`book-chapter` 改成 `chapter`，`posted-content` 改成 `article`。
- **Crossref 独有的键**改成 CSL 的键：`event` 改成 `event-title`，`publisher-location` 改成 `publisher-place`，`short-container-title` 改成 `container-title-short`。
- **补日期**：`issued` 缺失时，依次用 `published`、`published-online`、`published-print`、`created` 补上，并写一条提醒。
- **清理**：合并副标题，去掉 JATS 标记，保留 DataCite 的 `version`。
- **勘误提醒**：在规范之前算好，因为要用到 `article-number`。
- **LNCS 这类论文集**写成 `paper-conference`：`container-title` 写卷名，`collection-title` 写丛书名，丛书信息用 Crossref 查到的。
- **找到了就写进 CSL**：摘要写进 `abstract`，作者关键词写进 `keyword`，PMID 写进 `PMID`。
- **`source`** 直接写成 Zotero `libraryCatalog` 的样子：`DOI.org (Crossref)`、`DOI.org (Datacite)`，网页来的写网页的主机名。schema 的对照表里 `source` 本来就对 `libraryCatalog`，所以 p2z 不用为它写代码。（实现时改的：原稿是只写机构名，由 p2z 拼成 `DOI.org (<source>)`。）
- **只留 CSL 的变量**：CSL 1.0.2 的文本、日期、姓名变量，加上按名字带着的 `categories`。Crossref 记录里的参考文献列表、入库日期、得分、链接、对象形式的许可证都不要，结果文件小了几十倍。老的 `build_item` 本来也只按对照表取 CSL 的键，所以不影响条目。
- **CSL 里没有的**，按名字原样带着，比如 arXiv 的分类 `categories`。
- **网页上的 `citation_*` 元数据**也转成 CSL。现在是直接拼进 Zotero 条目的，这一段要新写。

**谁写结果文件**：只有前台命令写它。
- **`identify`**：写 `files` 和 `outcome` 以外的所有字段。用 `--redraft` 重认时保留 `files`，因为那是已经拿到的文件，标签说明了各自是哪个版本。认不出来时，比如没有 DOI 的论文，也写一份只有 `request` 和 `warnings`、没有 `csl` 的占位结果文件，code 照报。这样后面还能把文件交给它核对（§4.2）。占位结果文件可以被同一个 slug 的新请求覆盖，不报 `slug_taken`，因为换个编号或网址再认一次是正常的。收到题目（`needs_pinning`）时什么都不写。
- **汇总**：读 `fetch.jsonl`，把这篇的事件汇总成 `files` 和 `outcome`，原地写回，记下 `settled_at`。`fetch`、`claim`、`wait` 每次结束时都对自己碰过的那几篇做一次；`settle` 单独做这一件事，用在后台监视器后来收到文件之后。汇总每次都从整个 `fetch.jsonl` 重算，所以谁最后写都一样，不会丢更新。

后台的 Downloads 监视器只往 `fetch.jsonl` 追加事件、把文件放进 `results/`，从不写结果文件。agent 定标签也是一个事件，用 `claim --dir <dir> --label <标题> --why <理由> --slug <slug>`。没定标签的文件，由汇总给出 `Unknown-<Source>`。

**`claim` 只吃掉自己的文件**：`claim --file` 现在会把交给它的文件移走或删掉。拆分后，只有 paper-fetch 自己目录里的文件和本轮 Downloads 里的新文件才这样处理；别处的文件一律先复制，原件不动。否则把 Zotero 存储目录里的 PDF 交给它定标签时，原件会被删掉（`run.place` 在复制后 `unlink` 原文件）。

**`files[].check` 有三个值**：
- `ok`：核对通过；
- `accepted`：核对没过，但 agent 看过后接收了，`accepted_reason` 写明理由；
- `cannot_judge`：没有可对照的题目，比如没有 DOI 的论文，见 §4.2。

**`outcome`** 供 p2z 汇报用：拿到了（`got`）、没拿到（`not_got`）、在等用户（`waiting`，比如等学校登录），以及试过哪些站、停在哪里。细节留在 `fetch.jsonl`。

### 3.4 p2z 的记录

记录在 `<scratch>/paper-to-zotero/records/<slug>.json`，一篇一个，和结果文件用同一个 slug。由 p2z 新写的 `draft_item` 建立，字段如下：
- **`fetched`**：结果文件的绝对路径。
- **`item`**：用 CSL 按 schema 对照表加上规则生成，agent 可以改。版本在建记录之前就选定了，平常只生成一次。建了记录以后才改主意换版本时，先 `identify --redraft`，再 `draft_item --redraft` 重新生成。`item` 变了，`prepare` 的块就会过期，重新查库、重新预览。
- **`citationKey`**：结果文件的 `slug_given` 为真时取 slug，否则留空，交给 Zotero 和 Better BibTeX 生成。
- **agent 的字段**照旧：`tags`、`collection`、`distinct_from`、`same_as`、`keep_preprint`、`blocker`。
- **块**照旧：`checks`、`found`、`near_matches`、`saved`、`attach`。（实现时改的：`attach` 改成列表，结果文件里每挂一个文件记一项，带上 `kind`。一篇论文可以同时有正文和补充材料两个文件，原来的单个对象装不下。）
- **`warnings`**：只留建条目时的提醒，比如类型没对上、作者存成了 contributor、DOI 放进了 extra、有字段被丢掉。元数据本身的提醒，比如疑似勘误，留在结果文件里。

**移出记录、归 paper-fetch 的**：
- `id`，改成结果文件的 `request`；
- `alt_titles`；
- `label`；
- `published_candidates`，改成 `versions`；
- `links`；
- 记录旁边的文件。

**条目已经有 PDF 的，就不交给 paper-fetch 取全文。**Downloads 监视器只对照这样的结果：`fetch` 被要过它的文件（`fetch.jsonl` 里有它的 `pass`、`try` 或 `stop` 事件），而它还没有文件。它不再读 Zotero 的 `found`。（实现时改的：原稿只认 `try`，但 `fetch` 在一条路试完才记 `try`，试第一条路时下载的文件、第一条路就停在验证页的论文都对不上；现在 `fetch` 每一遍开始时给要取的论文各记一个 `pass` 事件。）

### 3.5 笔记文件

一条笔记在 Zotero 外面就是一份 Markdown，格式见 §5.1。只有这一个文件，没有 sidecar。
- **paper-read 新写的笔记**：放在结构化包旁边，叫 `<scratch>/<cite>.<附件标题>.note.md`，同论文笔记那张 issue 的已定 29。
- **`note.py take` 取出的笔记**：叫 `<cite>.<笔记 key>.note.md`；独立笔记没有 cite，叫 `<笔记 key>.note.md`。
- 文件名只为了好认。`put` 认的是 front matter，不看文件名。

## 4. 各 skill 的内容

### 4.1 paper-fetch

**脚本**放在 `paper-fetch/scripts/`，库放在 `pflib/`：

| 脚本 | 来自 | 做什么 |
|---|---|---|
| `pf.py` | 拷 `p2z.py` 的调度部分 | `pf.py <命令>` 运行 `scripts/<命令>.py` |
| `identify.py` | 从 `doi_to_item` 拆出 | 认论文，写结果文件，下面细说 |
| `fulltext_links.py` | 整个搬过来 | 列出能去的地方，写进 `links/` |
| `fetch.py` | 整个搬过来 | 一轮一轮地试 |
| `claim.py` | 拆，去掉查库的部分 | 核对、归位、接收、定标签（新加 `--label`）、监视 Downloads；`--sweep` 只列出遗留文件和 md5。只吃掉自己目录和本轮 Downloads 里的文件，别处的先复制（§3.3） |
| `wait.py` | 整个搬过来 | 等验证页 |
| `check_pdf.py` | 整个搬过来 | 看一份文件的核对结果 |
| `settle.py` | 新写 | 把事件汇总进结果文件；`fetch`、`claim`、`wait` 结束时也做同样的汇总 |
| `ready.py` | 拆 | 检查 OpenCLI、Downloads、poppler，建 `<dir>`（`--dir`，各个文件夹、`.started`、`run.json`）。浏览器会话和监视器照旧不在这里查 |

`pflib/` 里有三部分：
- **整个搬过来的**：`browser`、`verify`、`web`；
- **从 `p2zlib` 拆过来的**：`run`（放文件、claim、accept、arrival、Scanner）、`paper`（文件种类、来源、proposal、勘误和补充材料的规则）、`config`（`openalex_key`、`institution`）；
- **拷过来的**：`cli`，以及 §8 列的共用代码。

**`identify.py` 的命令行**：
```
identify.py [编号或网址…] [--slug S] [-o DIR]            # 也可以从 stdin 读，一行一篇："编号[<TAB>slug]"
identify.py --redraft <编号或网址> RESULT                 # 原地换成选定的版本
identify.py --search "<题目>" [--author 姓]               # 只列出候选，不写文件
```
- **输入**：DOI、arXiv 号或网址。网址不是 doi.org、arxiv.org 的，就当论文页读它的 `citation_*`；读不到就写占位结果。只有题目时，agent 先按 SKILL.md 的"认一篇论文"，用 OpenCLI 的适配器找到编号。`--search` 是其中一条路：用 Crossref 按题目查，原来在 `lint_items --crossref` 里。
- **预印本的版本**在 `identify` 里一并查好（原来是 `prepare` 单独一步）。有来源没应答时记在 `versions.incomplete`，同一个编号再跑一次 `identify` 会重新问，其余照旧跳过。
- **输出**：stdout 每篇一行 `{slug, code, path, …}`，最后一行是 `{"summary"}`。code 有：
  - `ok`；
  - `skipped`：同一个 slug 已经有结果文件，而且 `request` 一样；
  - `slug_taken`：slug 已经被别的请求占用，这时不写；
  - `needs_pinning`：收到的是题目（`title:` 开头），要 agent 先找到编号；
  - 现有的几种：`no_csl_record`、`page_unreachable`、`no_citation_meta`、`source_blocked`、`not_published`、`same_doi`。
- **退出码**按 §6。

**要改的**：
- 凡是读 Zotero 条目字段的地方，比如 `item.title`、`item.DOI`、`item.url`、`creators[].lastName`，都改成读结果文件的 `ids` 和 `csl`。涉及 `verify.subject`、`fetch.landing`、`fulltext_links`、`preprint_id`、生成 slug 的规则。
- `first_surname` 另写一个读 CSL 作者的版本。
- 预印本那条回退路线，从 `versions.preprint.ids` 取。
- 认论文不再需要 Zotero。现在 `doi_to_item` 一开头就读 Zotero 的 schema，拆分后 schema 只在 p2z 里用。

**给库里的文件定标签**，比如整理附件标题，或者用户拖进来的 PDF：
1. agent 先用条目的编号跑 `identify`；
2. 用 `claim --file <PDF> <slug>` 核对，再用 `claim --label` 定标签。交进去的是 Zotero 存储目录里的路径，`claim` 只复制，不动原件。

p2z 读结果文件里的 `files[].label`，用它改附件标题。

**参考文件**：
- `publishers.md`；
- `attachment-titles.md` 里"命名规则"和"证据"两节，标签怎么写由它定；
- `install.md` 里 poppler、OpenCLI、配置的部分；
- 新建 `identify.md`：只认论文、不取全文；
- 新建 `batch.md`：取全文的那几轮、用户在环里的部分、并行的规则；
- 新建 `gate.md`：验证页。

**SKILL.md** 开头是操作目录（已定 6）：
- 认一篇论文；
- 取全文：那条链，连同 Reaching a page、Agents you send；
- 给一批文件定标签；
- 只认论文，指向 `identify.md`；
- 批量多轮，指向 `batch.md`；
- 验证页，指向 `gate.md`。

内容来自现在 SKILL.md 的这些部分：
- "Pin the paper"；
- "Get the file: the chain"；
- "Reaching a page"、"Gate"、"Agents you send"；
- Instruments 里的 opencli、pdf、papers-cool-search；
- "The user helps; the work is yours"；
- "Draft the record"里查正式版、摘要、PMID、关键词的部分；
- "Ready"和"Clear residue"里属于它的那一半。

**测试**不只是搬家，要改写：
- 现在的测试数据是 p2z 的记录（带 `item`），要改成结果文件；
- 整个搬过来的：`fake_web`、`test_check_pdf`、`test_fetch`、`test_fulltext_links`、`test_verify`、`test_web`、`test_fake_web`；
- 从 `test_doi_to_item`、`test_claim`、`test_lint_items`、`test_p2z`、`test_p2zlib`、`test_ready`、`test_report`、`test_run` 里，取属于它的部分改写；
- `helpers.py`、`run_all.py` 两边各带一份。paper-fetch 那份 `helpers.py` 去掉对 `fake_zotero` 的引用。

### 4.2 paper-to-zotero

**留下的**：`attach_file`、`check_item`、`create_item`、`export_bib`、`file_and_tag`、`find_in_library`、`make_collection`、`merge_items`、`read_library`、`structured`、`trash_item`、`update_item`，以及 `p2zlib/zotero`。

**新写或重写的**：

| 脚本 | 做什么 |
|---|---|
| `draft_item.py RESULT… [-o records/] [--redraft]` | 读结果文件建记录（§3.4），取代 `doi_to_item` 里建条目的部分 |
| `read_bib.py BIB` | 读 .bib，每个条目输出一行 `编号<TAB>引用键`，可以直接用管道交给 `identify`。没有 DOI 和 arXiv 号的条目，输出 `title:<题目><TAB>引用键`，`identify` 收到时报 `needs_pinning`，由 agent 按 paper-fetch 的"认一篇论文"先找到编号 |
| `note_md.py`、`note.py` | 见 §5 |

**`draft_item` 怎么生成条目**：`build_item` 本来就在查 schema 的对照表。要写成代码留下来的，只是对照表管不到的这些规则：
- 结果文件的 `record_of` 是 `preprint` 时，类型定为 `preprint`。只看这一条，不看有没有 arXiv 号，不然正式版的条目会被改成预印本。
- `journalArticle` 去掉 `publisher`。
- 预印本条目的 `url`、`repository`、`archiveID` 照 arXiv 写；正式版条目的 `url` 用 `https://doi.org/<DOI>`。
- 类型没有 DOI 字段时，把 DOI 写进 `extra`。
- `libraryCatalog` 照现在写成 `DOI.org (<source>)`。
- 日期格式、作者转换、arXiv 分类转标签。
- 选了正式版时，从 `versions.preprint` 里补四样：DOI 记录没有摘要时，用预印本的摘要；网页元数据缺作者时，用预印本的作者；`extra` 里加一行 `arXiv: <编号>`；arXiv 分类照旧转成自动标签（`csl.categories`，没有就用 `versions.preprint.categories`，老流程里预印本时打的标签重认后也留着）。这些现在在 `doi_to_item --redraft` 里。

实现时要用真库的 `read_library schema` 核对一下：规范 CSL 时用到的键，Zotero 的对照表里都有对应吗？2026-10-30 核对过（schema 版本 44）：`event-title` 对 `meetingName`/`conferenceName`，`publisher-place` 对 `place`，`collection-title` 对 `seriesTitle`/`series`，`source` 对 `libraryCatalog`，都在；`container-title-short` 不在，表里对 `journalAbbreviation` 用的是 Zotero 自己的名字。老代码也从没写过期刊缩写，所以拆分前后一致；以后补期刊缩写（§13）时，在 `draft_item` 里把它对到 `journalAbbreviation`。另外 DataCite 的 `version` 在表里对 `versionNumber`，老代码有意不写它，`draft_item` 照旧跳过。

**从拆分的脚本里拿过来的部分**：
- **`find_in_library --file <PDF>…`**：按 md5 查遗留文件在不在库里，原来在 `claim --sweep` 里。
- **`lint_items`**：只留查库的检查。
  - 按题目找 DOI，交给 paper-fetch 的 `identify --search`；
  - 不再自己读 PDF 摘录，要判断文件时按 §4.1 交给 paper-fetch；
  - 代理网址只按通用的代理写法来认。学校的代理域名是 paper-fetch 的配置，p2z 不读。审阅时核对过，本机配置的代理也符合通用写法。
- **`ready`**：Zotero、写入 key、授权、分类树；建 `<scratch>/paper-to-zotero/`。（实现时改的：给了 `--dir` 才建目录，整理文库用不着；配置里还留着搬走的两项时，`config.moved` 列出来。）
- **`report`**：库里的部分，加上结果文件里的 `files[].check` 和 `outcome`。（实现时改的："残留"和"停下与门禁"两节去掉，前者是 paper-fetch 清理时的事，后者已在 `outcome.stop` 里，由"无法获取"一节列出。）
- **`p2z.py`**：
  - `prepare` 是 `find_in_library` 加 `check_item`；
  - `save` 照旧是 `create_item` 加 `attach_file`；
  - 判断"要 agent 定什么"时，读结果文件里的 `versions`。

**`attach_file` 变简单**：
- 结果文件没有 `outcome`，就报 `unsettled`，什么都不挂。没汇总过的结果文件里没有 `files`，不报错的话，会悄悄一个文件都不挂。p2z 不读 `fetch.jsonl`，所以看不出汇总之后又来了新文件，这一点靠 paper-fetch 的流程保证：后台收到文件后，取全文那一步以 `settle` 结束；
- 挂 `fetched` 那份结果文件里 `check` 为 `ok` 或 `accepted` 的每个文件，补充材料也照现在一样挂；
- 挂之前核对文件的 md5 和 `files[].md5` 一致；
- 标题用 `files[].label.title`，再按命名规则检查一遍；
- 附件的网址照现在用条目的 `url`，没有就用 DOI 链接；
- 不再自己核对 PDF，也不再去代理前缀。

**没有 DOI 的论文**：paper-fetch 取到文件，标成 `cannot_judge`。p2z 照现在经 connector 的 `saveStandaloneAttachment` 存，让 Zotero 的识别器建条目。已定 18 说"只走本地 API"，那是针对桥接插件说的；这是现有的一处例外，保留。

**附件标题的写法**两边都要用：paper-fetch 写；p2z 解析、排序、判断哪个被取代。这段写法和来源站点表放在同一个文件里，两边各带一份，以 paper-fetch 为准（§8）。

**参考文件**：
- `organize.md`：
  - 改附件标题的第 2 到 4 步，改成"按 §4.1 交给 paper-fetch 定标签"；
  - 按题目查 Crossref，改成交给 paper-fetch；
  - 写明整理文库时不动"主题笔记"这个分类（论文笔记那张 issue 的已定 16）；
  - 笔记一节改成 take/put。
- `tagging.md`、`no-doi-record.md`；
- `attachment-titles.md` 里"一篇论文的几个文件"那一节，再加一段指向 paper-fetch 命名规则的说明；
- `install.md` 里 Zotero 和 `zotero` 配置的部分；
- `batch.md` 里记录、保存、汇报、一次问完的部分；
- 新建 `references/import.md`：一次导入怎么编排 paper-fetch 和 paddleocr（已定 6），步骤就是 §3.2。

**SKILL.md** 开头是操作目录，有五项：
- 导入，指向 `import.md`；
- 整理；
- 导出 bib；
- 存取笔记；
- 存取结构化包。

保留"Identity"、"Authorization"、"Save and attach"、"Read back and report"，以及"Clear residue"和"Limits"里属于它的那一半。（实现时改的：导入的全部步骤，包括建条目挂附件、读回汇报、清理残留，都放进 `import.md`，SKILL.md 只留各项操作都用得上的：操作目录、Identity、Authorization、Read back（写过的都从库里读回）、临时目录、读库里的论文、Limits。这几步只属于导入，留在 SKILL.md 会把一条流程切成两处，读导入的 agent 要来回翻。）

**测试**：
- 留下的 14 个，加上从拆分的那些测试里取属于它的部分；
- `test_attach_file` 和 `test_zotero_attach` 去掉对 `verify` 的依赖；
- 新写 `test_draft_item` 和 `test_note_md`（§5.6）；
- `fake_zotero` 留在这边。

### 4.3 paper-read（先只搭框架）

按已定 14，这一轮只搭框架。读法本身还在论文笔记那张 issue 里讨论。

- **SKILL.md**：开头是操作目录，包括读一篇论文、写主题笔记、在笔记里记"用在哪里"、更正笔记。每一项指向参考文件；还没定的标"待定"，写明去论文笔记那张 issue 看。
- **读一篇论文**：
  1. 用 p2z 的 `structured take` 取结构化包和 PDF。缺包就调 paddleocr，再 `structured put`。
  2. 核对 PDF 的标题和引用键。
  3. 派一个用 opus 的 subagent，按问题树写笔记文件（论文笔记那张 issue 的已定 19 到 29）。
  4. 读完的标准：树上不再有"待答""进行中""等 Qn"，开头那一句话也写好了。
  5. 达到标准后，用 `note.py put` 存进 Zotero。
- **"树上还有没答完的节点就不存"，这条检查归 paper-read**，在交给 p2z 之前做，p2z 不认识问题树。论文笔记那张 issue 的已定 29 原来写的是"p2z 就不存"，已经跟着改了。
- **从 p2z 搬来的**：SKILL.md "Reading a library paper"里讲怎么读结构化包的部分。`structured take/put` 的命令说明留在 p2z。

## 5. 笔记：格式和转换

### 5.1 一条笔记在 Zotero 外面的样子

```markdown
---
key: NOTE1234
version: 13567
parent: ronneberger2015unet
schema: 9
citation-items: %5B%7B%22uris%22…
---
# 论文笔记

一句话概括……

## Q1 这篇论文试图解决什么问题？ [已答]
……
```

**front matter 的格式是写死的，不是 YAML**：
- 第一行正好是 `---`，接着每行一个 `键: 值`，值取到行尾为止，最后一行是 `---`。
- 第一行不是 `---`，就是没有 front matter。
- 正文里的分隔线一律写 `***`，不写 `---`，免得和 front matter、setext 标题混淆。

**认得的键**：

| 键 | 意思 | 谁用 |
|---|---|---|
| `key` | Zotero 笔记的 key；新笔记没有 | `note.py` |
| `version` | 取出时的版本；put 时对不上就拒绝写 | `note.py` |
| `parent` | 挂在哪篇论文下，写引用键；独立笔记没有 | `note.py` |
| `collections` | 独立笔记放进哪些分类，写分类 key，逗号分隔 | `note.py` |
| `related` | 独立笔记和哪些论文互设"相关"，写引用键，逗号分隔 | `note.py` |
| `schema` | 最外层 div 的 `data-schema-version` | `note_md` |
| `citation-items` | 最外层 div 的 `data-citation-items`，原样保留，排在最后 | `note_md` |

- 不认得的键原样保留。
- front matter 只在 `note_md` 一处读写（已定 23）。`note.py` 只拿到、交出一个字典。
- `citation-items` 不能丢。去掉它的话，某个条目一删，笔记里对应的引文就会变成 `()`。

### 5.2 子集表：哪些写成 Markdown

写入和读回只认这一张表。表外的一律原样当 HTML 保留，CommonMark 本来就允许这样（HTML 块和行内 HTML）。

| 元素 | Markdown | 笔记 HTML | 条件 |
|---|---|---|---|
| 标题 | `#` 到 `######` | `<h1>`…`<h6>` | 不带属性 |
| 段落 | 段落 | `<p>` | 不带属性 |
| 列表，可嵌套 | `- `、`1. `，子列表缩进 | `<ul>`、`<ol start>`、`<li>` | `ol` 只带 `start`，其余都不带属性 |
| 待办 | `- [ ] 文字`、`- [x] 文字` | `<li>[ ] 文字</li>` | Better Notes 也这样存 |
| 引用 | `> ` | `<blockquote>` | 不带属性 |
| 代码块 | 围栏代码 | `<pre>` | `<pre>` 里只有文字，没有加粗、链接之类的子元素 |
| 分隔线 | `***` | `<hr>` | |
| 表格 | GFM 表格 | `<table>` | 只有第一行是 `<th>`，单元格里只有行内内容，不带属性 |
| 显示公式 | `$$…$$` | `<pre class="math">$$…$$</pre>` | |
| 加粗、斜体、行内代码 | `**`、`*`、`` ` `` | `<strong>`、`<em>`、`<code>` | |
| 链接，包括 `zotero://` | `[文字](地址)` | `<a href>`，编辑器保存时会加上 `rel` | 除 `rel` 外不带别的属性 |
| 行内公式 | `$…$` | `<span class="math">$…$</span>` | 除 `class` 外不带属性；不在标题里 |
| 硬换行 | 行尾 `\` | `<br>` | 不在段落、标题、单元格的开头或结尾 |

**表外的**：
- 颜色、背景色、下划线、删除线、上下标；
- 引文、批注高亮、图片；
- 不满足上表条件的元素，比如带缩进、对齐、`dir`、`id` 的块；
- 其他一切。

**agent 写笔记时要知道的两点**：
- 原样写的 HTML 块，前后各空一行。
- 行内代码不要放进链接或加粗里。编辑器的代码标记排斥其他标记，保存时会把链接或加粗丢掉。

### 5.3 `note_md`：转换

**放在哪里**：转换代码在 `p2zlib/note_md.py`，命令行入口是 `scripts/note_md.py`。v2 spec §4.2 规定脚本之间不互相 import，所以 `note.py` 和 `note_md.py` 都去 import 这个库模块。

**函数**：
- `to_md(html, meta={}) -> md`；
- `to_note(md) -> (html, meta)`；
- `set_meta(md, meta) -> md`：只改 front matter，供 `note.py put -i` 写回 key 和 version。

**写入**（`to_note`）用 markdown-it-py，开 `html=True`，加上表格、`dollarmath`、`mdit-py-cjk-friendly`。做了五处修正：
1. 公式渲染成编辑器用的 `span.math` 和 `pre.math`；段落中间的 `$$…$$` 也当行内公式。
2. 代码块渲染成 `<pre>`，不套 `<code>`，结尾不多出换行。
3. 链接地址原样写，不转码，也不拒绝 `file:`。否则中文地址、带空格的地址、本地文件链接都会被改掉。
4. `dollarmath` 的 bug（mdit-py-plugins 0.6.1 在列表或引用里写多行 `$$` 时，把容器的前缀混进公式）：比较后选了自己写块级公式规则，替换插件的那条，读行的方式和代码块一样。公式是两个 `$$` 之间的全部内容，换行原样保留。没给插件打补丁；报给上游算对外发布，要等用户发话。
5. 公式只认该是公式的：`dollarmath` 开 `allow_space=False`，`$` 要紧贴公式，"$5 and $10" 这样的金额不算公式，数字可以紧挨着（3$\times$3）。标题里的 `$…$` 留作文字：编辑器的标题不收公式（note-editor 的 `nodes.js`），收进去会被它从公式处劈成标题加一段（真编辑器核对时看到的）。读回时标题里的 `$` 不加反斜杠。

写入前先把 front matter 剥下来：`schema` 和 `citation-items` 用来重建最外层 div，其余的键作为 `meta` 返回。两个都没有就不套 div，这样没有外层 div 的笔记读出再写回也不变；编辑器下次保存时自己会套上。

**编辑器模型**（已定 21，纯 Python）是"同一条笔记"的定义，自检、`note.py put` 判断"没改"、测试都用它，只有一份：
- 块：标签、属性（不分先后；链接的 `rel` 不算），以及子块或段落内容。`<li>`、引用、单元格里散着的行内内容算一段；它们和整篇笔记是空的时候，算有一个空段落（编辑器会补一个）。
- 段落内容是一串**文字段**，每段带着它的标记集合。这就是编辑器（ProseMirror）的存法：标记是集合，不是嵌套，所以 `<strong><em>` 和 `<em><strong>` 相同，被加粗切开的链接也相同。相邻同标记的文字段合并。
- 空白照编辑器载入时的方式合并：连续空白算一个空格，段首、`<br>` 后和段尾的空格去掉，不换行空格单独算。
- 几条编辑器的事实：`<b>`、`<i>` 就是 `<strong>`、`<em>`；代码标记排斥其他标记；硬换行上的标记看不见，不算；`<pre>` 里的空白原样算，编辑器保存时把两个空格写成的 ` &nbsp;` 算两个空格，开头那个换行（浏览器会丢）不算。
- 公式、图片、引文、批注高亮这些行内节点，带着自己的属性和内容。

**读回**（`to_md`）：
1. 剥下最外层 div，它的属性进 front matter。
2. 用标准库 `html.parser` 解析，Better Notes 导入的 `<input type="checkbox">` 换成 `[ ] `、`[x] `，再建成上面的模型。
3. **从模型写 Markdown**，不从原 HTML 写。编辑器载入后一样的两份 HTML 模型相同，写出的 Markdown 也相同，所以"稳定"是由构造保证的。
4. 每块自检：写出的 Markdown 用 `to_note` 渲染回去，模型必须和原块一样。段落和标题先试 `*` 表示斜体，再试 `_`，再试把标记写成 HTML 标签，都不行才留成 HTML。单元格里的段落放进一个单列表格里检。列表、引用、表格、代码块在顶层整块再检一次，不行就整块留成 HTML。所以退回 HTML 的范围尽量小：一处加粗写不成，只这一段用标签。
5. 顶层块之间空一行；列表项和引用里，段落后面能直接跟的块（标题、代码块、公式、引用、分隔线、能打断段落的列表）不空行。

只比文字不够，下面两种情况文字都一样，模型都抓得住：
- 带加粗的 `<pre>` 写成围栏代码，加粗没了；
- 表头列的 `<th>` 变成 `<td>`。

**说清楚它是什么**：这个模型是一个很小的编辑器模型，只有上面几条。它和讨论时没选的方案 B 属于同一类：B 是第一次选型时 237 行的仿编辑器程序，没选它，是因为它只是近似，编辑器一改它就得跟着改。这里只留几条规则，是被上面两个漏洞逼出来的：只比文字抓不住它们。保证 1 有多可靠，就看这几条规则有多准。规则出错时有两种后果：
- 规则太松，会把真丢了的东西放过去；
- 规则太严，只会让某块多退回一次 HTML，内容不丢。

所以拿不准时宁可严。比如 `<strike>`、`<del>` 和 `<s>` 是否同一个标记没有核实，就分开算；Better Notes 列表上的 `class` 编辑器大概会丢，也照样算，那块就留成 HTML。编辑器改了，要改的也只是这几条。

**写 Markdown 时就照做的通用规则**，不靠自检兜底：
- 不满足 §5.2 条件的元素，一律留成 HTML。
- 两个相邻的同类列表，后一个换分隔符：`-` 换成 `*`，`.` 换成 `)`。不然拼回去会并成一个。
- 标记在硬换行处断开时，在换行前收住，下一行再开。
- 连续空格和不换行空格：正文里写成 `&nbsp;`；行内代码里写成不换行空格字符本身，因为实体在代码里不会被解码；代码块里写成普通空格。
- 起始号不是 1 的有序子列表，前面空一行，不然它会并进上一段。

**退回成 HTML 的块也要写对**：
- 类型 6 的 HTML 块（`<p …>`、`<ul>`、`<blockquote>`、`<table>` 等）遇到空行就结束，所以退回的 HTML 里不能有空行：文字里含换行的空白合并成一个换行，`<pre>` 文字里会造成空行的换行写成 `&#10;`。
- 退回的 HTML 照原来的写，属性照原来的顺序。
- 顶层退回的块也按模型再验一次。验不过就报错（写到 stderr，退出码 1），这种情况不应该发生。

**转义**照 CommonMark 规范，只在会被读错的位置加反斜杠：
- **行首**，包括列表项、引用、表格单元格的开头：
  - `#`；
  - `>`；
  - 后面跟空格的 `-`、`+`、`*`；
  - 后面跟空格的 `数字.`、`数字)`；
  - 分隔线、setext 下划线、代码围栏；
  - `[x]:` 这样的链接定义；
  - 缩进四格；
  - 会开始 HTML 块的 `<`；
  - 下一行像表格分隔线时，行首的 `|`。
- **标题末尾的 `#`**。
- **行内**：
  - 按左右侧规则可能成对的 `*`、`_`；
  - `` ` ``；
  - 能组成链接的 `[`、`]`，即后面紧跟 `(`、`[`、`:` 时；
  - 图片的 `![`；
  - 可能被当成标签或自动链接的 `<`；
  - 可能组成实体的 `&`；
  - 可能开始公式的 `$`（标题里不读公式，不转义）；
  - ASCII 标点前的 `\`，以及行尾的 `\`（它会变成硬换行）。
- **表格和链接里**：
  - 表格单元格里的 `|`；
  - 链接标题里的 `"`；
  - 链接地址里有空格或不配对的括号时，用 `<…>` 包起来。

其他地方一律不加，比如 `C:\temp`、`snake_case`、句中的 `-`，以及标题末尾的 `[已答]`：它后面没有 `(`，组不成链接。漏掉的转义会被自检抓住，最坏的结果是那一块退回成 HTML，内容不会丢。

**三条保证**：
1. **不丢内容**：任何笔记读成 Markdown 再写回，在编辑器的模型里内容和结构都不变。
2. **稳定**：同一条笔记读两次，结果一样。
3. **能写成 Markdown 的都写成 Markdown**：子集表里的元素能精确写成 Markdown 的，就写成 Markdown；写不精确的，那一处或那一块用 HTML。反斜杠只出现在上面列的位置。

**依赖**：
- `note.py`、`note_md.py`、`test_note_md.py`，以及在进程里 load 了 `note.py` 的测试（如 `test_note.py`）的 PEP 723 块里，钉死三个版本：`markdown-it-py==3.0.0`、`mdit-py-plugins==0.6.1`、`mdit-py-cjk-friendly==0.3.0`。这是盲测时实际跑的组合；cjk-friendly 要求 markdown-it-py 低于 4。
- 依赖由 uv 取，不往仓库里拷代码。
- `p2z.py` 和 `run_all.py` 现在用 `sys.executable` 起脚本，装不上这些依赖，要改成 `uv run --script <脚本>`（§6）。

**大小**：原型 `mdit_subset.py` 有 186 行，其中代码 138 行。加上自检、规范化、转义重写、代码块和硬换行，估计 300 行上下。

### 5.4 `note_md.py` 的命令行（已定 22、23）

```
note_md.py -t md|note [输入…] [-o 输出]
```
- **`-t/--to`**：`md` 是笔记转 Markdown，`note` 是 Markdown 转笔记。必须给，不猜。
- **输入**：不给路径，或者给 `-`，就读 stdin；也可以给一个或多个路径。
- **输出**：
  - 不给 `-o`：写到 stdout。这时只能有一个输入，给了多个算用法错误。
  - `-o 文件`：只能有一个输入，写进这个文件。
  - `-o 目录`：已经存在的目录，或者以 `/` 结尾的路径，算作目录，不存在就建。每个输入换掉最后一个扩展名后写进去，比如 `x.html` 写成 `目录/x.md`，`x.md` 写成 `目录/x.html`。
  - stdin 配目录、输出重名、要覆盖已有文件，都算用法错误。（`note.py take` 不一样，见 §5.5。）
- **stderr**：平时什么都不写。有块被自检退回成 HTML 时，每块写一行，写明是哪个文件、第几块、什么元素。
- **退出码**：0 成功；1 有输入读不了或转不了，其余照转；2 用法错误。
- 一律 UTF-8，换行用 `\n`。

例子：
```sh
uv run scripts/note_md.py -t md note.html
uv run scripts/note_md.py -t md note.html -o note.md
cat note.html | uv run scripts/note_md.py -t md > note.md
uv run scripts/note_md.py -t note notes/*.md -o out/
```

### 5.5 `note.py`：在 Zotero 和笔记文件之间搬

现在的 `note.py` 用 `--file`/`--text` 加 `--marker`，自带的转换只认一层列表。这次整个换掉：

```
note.py take (--cite C | --key K | --note N) [--title T] [-o 输出]
note.py put  [输入…] [--dry-run] [-i]
note.py list [--cite C | --key K | --collection K] [--q 文字]
```

- **`take`**：
  - 取一个条目下的子笔记；加 `--title T` 只取第一行是 T 的那条。原来的 `--marker` 改名为 `--title`，因为它认的就是笔记的第一行，也就是 Zotero 显示的标题。
  - `--note N` 按 key 取一条，独立笔记也能取。
  - 每条笔记用 `to_md` 转成带 front matter 的 Markdown。front matter 里有 key、version，以及 parent，或者 collections 和 related。
  - 一条写到 stdout 或 `-o 文件`；多条写进 `-o 目录`，文件名按 §3.5。取到多条却没给 `-o 目录`，算用法错误，stderr 列出各条的 key 和标题。
  - 目标文件已经存在、而且它的 front matter 里是同一个 `key` 时，直接覆盖。`put` 报 `version_conflict` 以后，重新 take 到同一个目录，本来就是正常的做法。key 不同的同名文件，算用法错误。
- **`put`**：
  - 从路径或 stdin 读，用 `to_note` 转换。
  - 有 `key` 就更新，带上 `version`。Zotero 里的版本和它不一样时，报 `version_conflict`，不写。front matter 里写了的 `parent`、`collections`、`related` 也一并同步，`related` 两边都改。Zotero 里已经是同一条笔记（按 §5.3 的模型）就报 `unchanged`，不写，版本不动。
  - 没有 `key` 就新建：有 `parent` 就建子笔记；否则按 `collections` 建独立笔记，并按 `related` 和论文互设"相关"。
  - 写完读回核对。
  - `-i` 用 `set_meta` 把新的 key 和 version 写回文件的 front matter，下次还能接着 put。
  - `--dry-run` 只给出要写的 HTML 和写到哪里，不写库。
  - stdout 按 §6 每条一行，字段有 file、code、key、version、action（created、updated、unchanged），最后一行是 summary。code 沿用现在 `note.py` 的那些，比如 `version_conflict`、`write_denied`、`readback_mismatch`、`cite_not_found`、`cite_ambiguous`。
- **`list`**：
  - 每条笔记输出一行 JSONL，字段有 key、parent 的引用键、标题、version、修改日期、collections。
  - `--q` 搜正文，用 `qmode=everything`。2026-10-30 在 Zotero 10 上核对过：`everything` 和 `fields` 都搜得到笔记正文，默认的 `titleCreatorYear` 连笔记标题都搜不到。

动词沿用 `structured` 的 take/put。`organize.md` 里用到 `note --marker` 的地方，都改成 take/put。

### 5.6 测试和验证

- **样例拷进仓库**，放在 `paper-to-zotero/tests/fixtures/note_md/`，每组一个 `.html` 和一个 `.md`，各个样例用 `<!-- 名字 -->` 隔开，共 100 个：
  - `blind`：盲测的 64 个，来自 `blind/`；
  - `edges`：调过的 28 个，来自 `pandoc-retest/corpus/edges.editor.html`。其中 3 个不是编辑器真正保存的样子，已经改对："nbsp / double space"、"code block"、"embedded image"；
  - `better-notes`：Better Notes v3.3.3 的测试笔记；
  - `notes`：7 条整篇的论文笔记（编辑器存过的、Better Notes 导入的、纯 HTML、没存过的、用户改过的，以及测试笔记那一对 `rt-sent.html`、`rt-after-edit.html`）。里面提到用户研究项目的地方换成了中性的字样。
- **期望的 Markdown** 按类别核对后接受，不是拿输出直接覆盖：和盲测时写的期望比，差别只有这几类，都接受了：分隔线写 `***`；转义偏保守（`\*\*\*`、每个反引号都转义、文字段末尾的 `\`）；交叠的加粗斜体改用 `_` 表示斜体；标记在硬换行前收住；中文地址、`file:` 地址、带空格的地址直接写成 Markdown 链接；行内代码里的不换行空格写成字符本身；列表项里能紧跟段落的块不空行；单行的公式写在一行。
- **`tests/test_note_md.py`**：纯 Python。每个样例都要：读成期望的 Markdown；写回以后按模型和原样相同（保证 1）；再读一次得到同样的 Markdown（保证 2）。另外检查哪些块退回了 HTML（14 个样例里有，都是 Markdown 说不了的：带属性的块、合并或着色的单元格、没有表头行的表格、带加粗的代码块、Better Notes 的任务列表）、front matter、写入的修正和命令行。`tests/test_note.py` 用假 Zotero 测 take、put、list。
- **哪些不算盲测**：这些样例都看过了，是开发和回归用的。以后另派一个 agent，不看代码，按编辑器 schema 写一批新样例，只跑一次，那一批才算检验，之后也并进回归样例。
- **保证 1 怎么验**：
  - 开发时原想用参考文件夹 `passthrough/blind/judge/` 里那个 Node 裁判量一下，但它的 `node_modules` 已经没有了，重装是装非 Python 的东西，要用户同意，所以这次没用。
  - 用真编辑器核对（issue 的待验证 2、第 73 条）：2026-10-30 做完。79 个样例拼成一条笔记，用户在 Zotero 里改过以后取回比对：差别都是用户的改动或编辑器自己的规范化（样式重写、链接加 `rel`、标记的先后、合并着色单元格的背景色拷到文字上），没有转换器丢的；存回来的那版读出写回不变。它暴露了一条编辑器规则：标题不收公式，写入因此加了修正 5。送进去和存回来的两版在参考文件夹的 `realeditor/`。

## 6. 命令行约定（三个 skill 通用）

沿用 p2z v2 spec（`docs/specs/20260923-paper-to-zotero-v2-spec.md`）已定 5 和 §3.3 的 Unix 方式：
- 脚本是过滤器：给了路径就读路径，没给就读 stdin；结果写到 stdout；诊断只写到 stderr。
- `-i` 写回原文件，这时 stdout 改成每条一行摘要，最后一行是 summary。
- 退出码：0 表示全部成功或跳过；1 表示有失败；2 表示无法检查或用法错误。
- 用管道代替循环。

这次新加的约定：
- **`-o/--out`** 只表示输出写到哪里，文件或目录都行，规则同 §5.4。`structured take --to DIR` 改成 `-o`。`doi_to_item --out-dir` 随它拆进 `identify` 和 `draft_item`，也改成 `-o`。
- **`-t/--to`** 只表示格式。
- **`fetch` 是例外**：它的 stdout 是给 agent 实时看的过程，不受"`-i` 改成摘要"那条约束。
- **调度脚本和测试入口**（`p2z.py`、`pf.py`、`run_all.py`）用 `uv run --script <脚本>` 起脚本，这样每个脚本的 PEP 723 依赖都能装上。
- **跨 skill 调用**写成相对于 skill 目录的路径。比如 p2z 的文档里写 `uv run ../paper-fetch/scripts/pf.py identify …`。
- **新脚本要设可执行位**：这个仓库关了 `core.fileMode`，要用 `git update-index --chmod=+x`。脚本开头是 `#!/usr/bin/env -S uv run --script` 加 PEP 723 块，见根目录 AGENTS.md。

## 7. 配置（已定 13）

- **p2z**：`~/.config/paper-to-zotero/config.json`，只剩 `zotero`，也就是写入 key 和 serverID。
- **paper-fetch**：新建 `~/.config/paper-fetch/config.json`，放 `openalex_key` 和 `institution`（学校的代理、发现系统）。
- **paper-read**：不需要配置。
- **怎么搬**：
  - §10 第 2 步，把这两项拷进 paper-fetch 的配置文件，让它能真跑；
  - 第 3 步，再从 p2z 的配置文件里删掉；
  - 这是用户本机的文件，每次动之前先跟用户说；
  - 改完以后，更新记忆 `paper-access-environment.md` 里关于配置位置的那句。
- 仓库里只写占位符，真值放在本机配置里。

## 8. skill 之间的调用和共用代码（已定 7、8）

- **按操作检查兄弟 skill 在不在**：在自己目录旁边找，比如 `../paper-fetch/SKILL.md`。只在要用它的操作开始时查：导入要查 paper-fetch，缺结构化包时要查 paddleocr，整理文库不用查。找不到就停下，说出要加载的 skill 的名字。
- **交接只靠文件**：拿不到就停下，不猜。
- **调用处写明对方的名字**。
- **小的共用代码各带一份，不做共享库**：文件头写明从哪里拷来、哪个提交。先例是 mattpocock 的 `pr`，它的 CREDITS.md 写着 "a hard dependency would break standalone installs"。

**两边各带一份的代码**（来自 `inventory.md` §3）：

| 代码 | 现在在 | 说明 |
|---|---|---|
| 输出行、状态码、参数、记录循环 | `p2zlib/cli.py` | paper-fetch 那份去掉 `add_base_url`、`main_items` 和 targets |
| 读配置文件 | `config.py` 的 `path`、`read`、`section`、`text` | 各读各的文件 |
| `now_iso`、`atomic_write`、`md5_of`、`records_of`、`due`/`stamp`/`fingerprint` | `run.py` | |
| 编号：`ARXIV_ID`、`DOI_FORM`、`normalize_doi`、`normalize_arxiv`<br>题目：`norm_title`、`title_similarity`<br>`file_format`、`host_of` | `paper.py` | `host_of` 现在有两个版本，`paper.py` 一个、`web.py` 一个，只留一个 |
| 附件标题的写法：`VERSIONS`、`TITLE_RE`、`title_field`、`label_title`、`parse_title`，以及来源站点表 `SOURCES` | `paper.py` | 单独放进 `titles.py`，两边内容一样，以 paper-fetch 为准 |
| 识别通用的代理网址写法 | `web.py` 的 `OTHER_PROXIES` 一带 | 只给 p2z 的 `lint_items` 用，不读配置 |
| `tests/helpers.py`、`tests/run_all.py`、调度脚本 | | |

- **防止两份 `titles.py` 越走越远**：p2z 加一个测试。旁边装了 paper-fetch 时，比较两份 `titles.py` 是否一样，不一样就失败；没装就跳过。
- **断开 import**：
  - `run.py` 在模块开头就 import 了 `verify` 和 `web`，拆的时候要断开；
  - `web.py` 和 `zotero.py` 都在用的时候才 import `run.atomic_write`，改成各自 import 自己那份。

## 9. 复用：每个部件比较后的结论（已定 17）

| 部件 | 结论 | 依据 |
|---|---|---|
| 元数据 | 留我们的。摘要、PubMed 号、正式发表版、写库前预览，都比 Zotero 的 translator 好。Zotero 做得更好的几处见 §13，以后搬进 paper-fetch | `metadata-and-pdf-comparison.md` |
| 找 PDF | 留我们的链。Zotero 的"查找可用 PDF"只找开放获取的版本，不核对文件，16 次里版本标错 14 次 | 同上 |
| CSL 转条目 | 用 Zotero schema 里的对照表，复用 Zotero 的数据，不写死对照表 | 已定 12 |
| 建条目 | 走本地 API，不走 connector 导入，因为 connector 会动用户的窗口，也没有预览。没有 DOI 的论文是例外，见 §4.2 | 已定 12 |
| 桥接插件 | 不装 | 已定 18 |
| 笔记转换 | 自己写，用 markdown-it-py。13 个读回器在同一套盲测样例上重比过，子集读回器加兜底最好 | `reselect-blind.md` |
| Better Notes | 借它的识别规则和测试样例，不搬代码，因为它的转换写在 TS 的语法树上 | 已定 20 |
| 结构化 | paddleocr，不改 | |

## 10. 改造步骤

**先复制、后删除**：paper-fetch 先从 p2z 拷出它要的代码，等 p2z 改完，再从 p2z 里删掉。中间 p2z 一直能用。每一步测试全过就提交一次。

0. **开工前存基线**：用现在的流程对 §11 的三篇跑一遍，到 `--dry-run` 为止，把认出的元数据、要建的条目、下到的文件的标签存下来，作为拆分前后对比的基线。改任何代码之前做，免得基线已经受了改动的影响。（2026-10-30 已做：存在拆分 issue 参考资料文件夹的 `baseline/` 里，不放临时目录，因为实现要跨好几次会话。`baseline/README.md` 写了三篇的输入、当时的选择、结果和 md5；标签那部分可以离线重放：拆分后用 `claim --file` 核对这几份 PDF，结果要和当时的 claim 事件一致。）
1. **笔记**（在 p2z 内部做，和拆分无关，可以先做）：
   - 写 `p2zlib/note_md.py`、`scripts/note_md.py` 和新的 `note.py`；
   - `p2z.py` 和 `run_all.py` 改用 `uv run --script`；
   - 拷入样例，写 `test_note_md`；
   - 按 §5.6 验证；
   - 把 `organize.md` 的笔记一节改成 take/put。
2. **paper-fetch**：
   - 建 `paper-fetch/`，下面有 `SKILL.md`、`references/`、`scripts/`、`pflib/`、`tests/`；
   - 拷入共用代码（§8），注明出处；
   - 拷入整个搬的文件；从 `doi_to_item` 拆出 `identify`；从 `claim`、`ready`、`run`、`paper`、`config` 里拆出属于它的部分；新写 `settle`，并让 `fetch`、`claim`、`wait` 结束时做同样的汇总；`claim` 改成只吃掉自己的文件；
   - 改成读 `ids` 和 `csl`，写结果文件，规范 CSL；
   - 写 SKILL.md 和参考文件（§4.1）；
   - 先跟用户说，再把两项配置拷进它的配置文件；
   - 改写测试，全部通过。
3. **p2z**：
   - 写 `draft_item`、`read_bib`、`find_in_library --file`；
   - `prepare`、`save` 改成读结果文件，`attach_file` 改成核对 md5；
   - 改 `lint_items`、`ready`、`report` 里属于 p2z 的那一半，统一 `-o`；
   - 删掉已经搬走的代码和测试；先跟用户说，再删掉配置里搬走的两项；
   - 写 `references/import.md`，改其他参考文件，重写 SKILL.md；
   - 测试全部通过。

   （2026-10-30 已做，`a5440e0` 到第 3、4 步的文档提交。核对过：`draft_item` 对三篇基线论文生成的条目和基线逐字段一致，SENet 的预印本和 CVPR 正式版两种都对上；在假 Zotero 上用基线的三份 PDF 跑 `attach_file`，附件标题和 md5 和基线一致。配置里搬走的两项按用户的话，等用户用过新版再提醒删。）
4. **改说法**：搬过去的和留下来的代码、文档里，"work directory"都改成"scratch directory"，并写明路径。现在 SKILL.md 和 17 个脚本里有这个说法。（2026-10-30 随第 3 步一起做完：p2z 剩下的脚本、两边的文档里都改成 `<scratch>/paper-to-zotero` 或 paper-fetch 的 `<dir>`。）
5. **paper-read**：按 §4.3 搭框架。
6. **收尾**：
   - 更新 README 的 skill 列表（根目录 AGENTS.md 的规定）；
   - 更新记忆 `paper-access-environment`、`paper-to-zotero-skill-status`；
   - 推送到 GitHub、从 GitHub 重装，都等用户发话。

## 11. 验证

- **测试**：每个 skill 自己的 `run_all.py` 全部通过。
- **笔记**：按 §5.6。
- **导入全程**：在真库的 `tmp` 分类里做，先 `--dry-run`，再真写，做完移进回收站。挑三篇：
  - 一篇有正式版的 arXiv 预印本，要选正式版；
  - 一篇要走学校登录的出版商论文；
  - 一条带引用键的 .bib 条目。

  条目字段、附件标题、标签，要和 §10 第 0 步存下的基线一致。
- **整理**：在现有分类上只读地跑 `lint_items`、`read_library`、`export_bib`，结果要和拆分前一致。只有两处例外：`lint_items` 不再给 Crossref 候选，也不再给 PDF 摘录，这两样改由 paper-fetch 做。
- **笔记的实测**：读一篇用户指定的论文，用 `note.py put` 存成笔记，在 Zotero 里看过以后再 take 回来，要和存进去的一致。同时核对论文笔记那张 issue 列的几项：
  - 独立笔记的 `related`，在论文条目那一侧看得到；
  - `zotero://open-pdf/…?page=N` 链接没被改写；
  - 结构化包里带着页码。
- **审阅**：实现完，用 code-review 对照本 spec 审一遍，再提交。

## 12. 要接受的代价，以及不做的事

**代价**（已定 10）：
- paper-read 还要管"记录项目用了这篇论文"，这一点靠描述写清；
- 常驻上下文里的 skill 描述从一段变成三段；
- 库里没有的 PDF，要先导入才能读；
- 选正式版时要多跑一次 `identify`，多一次网络请求；
- 共用的小代码两边各带一份，要靠测试防止两份越走越远。

**不做**：
- 不装桥接插件；
- skill 里不用 Node；
- 不做 Markdown 双向同步，Better Notes 的同步不适合给 agent 用；
- 不做同时修改的合并：版本对不上就拒绝写，重新取；
- 论文笔记的读法细节，本文只搭框架。

## 13. 留到以后的事

- **元数据的改进**（见 `metadata-and-pdf-comparison.md`）：把 Zotero 做得更好的几处搬进 paper-fetch，包括 arXiv 的完整日期、期刊缩写、会议地点、论文集 ISBN、LNCS 卷号、作者关键词；另外把 Zotero 处理 ScienceDirect、PMC、MDPI 的办法写进 `publishers.md`。拆完以后单独做，不和拆分混在一起，免得没法对比拆分前后的结果。
- **论文笔记那张 issue 还没定的**：
  - 防止发散：哪些子问题可以加到树上，树最多几层；
  - 读论文的 subagent 能不能再派 subagent；
  - 什么时候生成笔记；
  - 怎么对照 PDF 核对；
  - 重新生成时，怎么不冲掉追问和"用在哪里"；
  - 库里现有的 182 条笔记怎么处理。
- **文库整理**（见记忆 `zotero-library-todo`）：
  - 7 条 LNCS 条目；
  - 68 条只有年份的 arXiv 日期；
  - 把测试笔记 `JXD7NQZI` 移进回收站。

## 14. 自审改了什么（2026-10-30）

用户让我自己再审一遍，找低级错误和顶层设计上不优雅的地方。

**低级错误**：
1. **会删掉库里的 PDF**：`claim --file` 会把交给它的文件移走或删掉。原来写的"给库里的文件定标签"直接把 Zotero 存储目录里的路径交给它，原件会被删掉。现在规定：只有 paper-fetch 自己目录里的文件和本轮 Downloads 里的新文件才这样处理，别处的一律先复制（§3.3）。
2. **p2z 读了 paper-fetch 的过程文件**：`attach_file` 要读 `fetch.jsonl` 才能判断"汇总之后又来了新文件"，和"p2z 只读 `results/`"矛盾。现在 p2z 只看有没有 `outcome`（§4.2）。
3. **监视器的条件没法成立**：它要看的 `outcome` 只有汇总时才写，平时没有。现在改成看 `fetch.jsonl` 里的事件（§3.4）。
4. **没有 DOI 的论文接不上**：`identify` 认不出来时不写结果文件，后面的文件就没地方挂。现在认不出来也写一份最小的结果文件（§3.3）。
5. **对比没有基线**：§11 要求"和拆分前一致"，但第 3 步删掉旧代码以后就没得比了。现在改任何代码之前先存基线（§10 第 0 步）。
6. **小处**：
   - 结果文件的例子没说明这是重认以后的样子；
   - `take` 取到多条却没给目录时怎么办，没写；
   - `-o 目录` 不存在时怎么办，没写；
   - "只包着一段的 `<p>`"漏了"`<li>` 里"。

**顶层设计**：
1. **选版本挪到建记录之前**：原来是先建记录、查库，选了正式版再重认、再重建条目、再查一次库，一个版本选择要跑五个命令。选版本只需要 paper-fetch 结果里的 `versions`，规则仍归 p2z，所以挪到建记录之前，条目只生成一次。`draft_item --redraft` 只留给"建了记录以后才改主意"（§3.2、§3.4）。
2. **`settle` 不再是一个容易忘的步骤**：原来 `settle` 是单独一步，忘了跑就一个文件都不挂。现在 `fetch`、`claim`、`wait` 结束时自己汇总，`settle` 只在后台监视器后来收到文件时用（§3.3）。

**看过、保留的**：
- 两种笔记文件名：paper-read 新写的用包名，take 出来的用 key。前者是论文笔记那张 issue 已定 29 定的，文件名也不影响 put。
- `titles.py` 两边各带一份，再加防漂移的测试。这是 skill 各自能单独装的代价（已定 8）。
- 两个 `ready`：各查各的依赖，和"按操作检查兄弟 skill"一致。

**再通读一遍时又改的**（同日）：
- 基线挪到第 0 步，在改任何代码之前存；
- 认不出来的占位结果文件可以被同一个 slug 覆盖，收到题目时不写占位文件，不然换个编号再认会报 `slug_taken`；
- 第 2 步写明汇总和"`claim` 只吃掉自己的文件"这两处改动。
