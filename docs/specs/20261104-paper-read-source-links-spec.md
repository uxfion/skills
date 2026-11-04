# paper-read：笔记里的出处可以点，跳到 PDF 里的位置（设计）

> 第二版，2026-11-04：用户看过预览，定了已定 2，说 compact 之后实施。第一版过了两份审阅（忠实度和可用性、技术正确性，在 issue 的参考资料文件夹 `review-fidelity.md`、`review-technical.md`），按审阅、自查和用户的选择改过，§10 记了改了什么。来源：issue [20261103-paper-read-source-links.md](../issues/20261103-paper-read-source-links.md)（实测和已定 1）。依据：`docs/design-principles.md`。

## 0. 一句话

读论文的 agent 照旧只写出处；主 agent 把笔记存进 Zotero 之前，脚本把正文里的页码、图号、表号变成链接：图和表在 PDF 上有一个带 `paper-read` 标签的蓝色区域标注，链接跳到标注并框住，其余跳到页。取出笔记时再把链接去掉，agent 读写的始终是干净的出处。

## 1. 要什么，已经定了什么

- 用户（2026-11-03）：「你说的那个跳转能不能实现？就是我点一下，跳转到图所在的位置」；实测后：「那这样的话，本身就是和结构化包对应起来了呀。我们本身是有结构化信息的」。
- **已定 1**（用户选 A）：笔记引用到的图、表，在 PDF 上建区域标注，链接到标注（蓝框定位）；其余出处只链接到页，不建标注。标注统一一种颜色，备注写明是 paper-read 建的，和用户自己的标注分开。
- **已定 2**（2026-11-04，用户选 A：「A」）：表的框框住表的标题（"TABLE III" 那一行），不框整张表。标题自己写着编号，位置确定；框整张表要猜哪个标题配哪张表（§4.5）。图照旧框整张图。
- **已定 45**（2026-11-02）：出处能定位就标，页码或章节都行，不强制。本设计不改它：只写节号的出处没有页码可链，就不加链接（§4.1）。
- 实测过的（issue）：`zotero://open-pdf/library/items/<PDF 附件 key>?page=N` 跳到第 N 页（从 1 数），`?annotation=<标注 key>` 跳到标注并框住；区域标注能经本地接口建；p2z 的笔记转换能完整往返 `zotero://` 链接（技术审阅在 T-CACE 笔记上加了 225 个链接，离线转成 Zotero 的格式再转回来、去掉链接，和原文逐字相同）。

## 2. 例子：T-CACE 笔记里的一行，从写到点

T-CACE 笔记 Q5 里现在的一行：

```markdown
4. 消融：CTE、DTAM、时间编码各贡献多少 → 只在 MG-2021 的 Delay 合成任务上做 → 去掉任一模块分割和分类都下降（Table III, p.11；Fig. 9, p.11）。见 Q5.4。
```

1. 主 agent 检查过笔记，用 `put_note.py <笔记>` 存。它先认出 `Table III`、`p.11`、`Fig. 9`、`p.11` 四个记号。
2. 它问 paddleocr（`doc.py objects`）这个包里 Table III 和 Fig. 9 在哪：都在第 11 页；Fig. 9 给整张图的框，Table III 给 "TABLE III" 那行标题的框，都已换算成 PDF 自己的坐标。
3. 它让 p2z（`annotate`）在这份 PDF 上为两者各找一个已有的 paper-read 标注，没有就建：蓝色、标签 `paper-read`、备注 `paper-read · Table III`，拿回 key。
4. 这一行变成 `（[Table III](zotero://open-pdf/library/items/4UVJVU5R?annotation=…), [p.11](zotero://open-pdf/library/items/4UVJVU5R?page=11)；[Fig. 9](…?annotation=…), [p.11](…?page=11)）`，存进 Zotero；存完，主 agent 手里的笔记文件又是干净的。
5. 用户在 Zotero 里点 `Fig. 9`：PDF 打开，蓝框框住图 9；点 `Table III`：跳到表 III，蓝框框住它的标题；点 `p.11`：翻到第 11 页。
6. 下次 `prepare_note` 取出：链接去掉，这一行和原来逐字相同。

## 3. 谁做什么

| 谁 | 做什么 | 改动 |
|---|---|---|
| 读论文的 agent | 照旧写出处，不写链接 | note-format.md 说明哪些写法会变成链接（说明，不是规矩） |
| paddleocr | 知道图和表在 PDF 的哪里 | 新命令 `doc.py objects`（只读）：图给整张图的框，表给标题的框 |
| p2z | 知道 Zotero 怎么存标注 | 新命令 `annotate`：找到或新建区域标注，交回 key |
| paper-read | 把笔记里的记号和图表连起来，加链接、去链接 | 新脚本 `put_note.py`（加链接、存、存完去掉链接）；认记号和去链接的函数放在一个模块里，`prepare_note`、`put_note`、`check_quotes` 共用；`prepare_note` 取出时去链接；SKILL.md、note-format.md |

每样东西只有一个家：图表在 PDF 的哪里归 paddleocr，标注怎么存归 p2z，出处的文字归笔记。链接是从这三样推出来的，随时能去掉、能重新生成。

## 4. 细节

### 4.1 哪些写法变成链接

- **记号**：
  - 页：`p.N`、`p.N–M`（链到第 N 页），和 note-format.md 的写法一样，`p.` 后面不空格；`p.9、p.11` 是两个。
  - 图：`Fig. N`、`Figure N`、`Fig.N`；表：`Table N`；前面可以有 `Supplementary`、`Extended Data`。编号照论文（`3`、`III`、`S1`）。
  - 每个记号都是完整的一个：`Table I/II`、`Figs. 3–5` 这样连写时，只有写全的第一个（`Table I`、`Figs. 3`）有链接，后面单独的编号不链。note-format.md 说明一句"各写全名才各有链接"，是提示，不是规矩。T-CACE 里这种连写只有 4 处。
  - 子图：`Fig. 2(b)`、`Fig. 2b` 链的是 `Fig. 2`，面板字母留在链接外面。
  - 中文的 `图 4`、`表 III` 不认（note-format.md 本来就要求术语保留英文）。
- **在哪里认**：笔记正文的 Markdown 文字，括号里外都认（T-CACE 里常见 `Fig. 4（p.7）是…`，图写在句子里）。**不碰**：
  - 标题行（含 `# 论文笔记` 和 HTML 标题）、开头的元数据区、「读的版本」那一段。标题下面的概要是正文，照常加；
  - 引文的英文原句：范围用 `check_quotes` 现成的引文规则（挪进共用模块），它后面的出处照常加；引文下面的中文译文是正文，照常加；
  - 行内公式、代码；
  - HTML 块（用户在 Zotero 里排过版的段落，取出时留成 HTML）和已经在链接里的文字；
  - 删去标记 `（<新 PDF> 删去了这段，原见 <旧 PDF> <出处>）` 和更正标记里 `原写"…"` 的部分：它们引的是旧版本或旧文字，不是这份 PDF。
- **对不上的**进 `unmatched`，各带原因：
  - 图表：包里没有这个图表或编号不唯一、旋转页、没有包、没装 paddleocr、`doc.py objects` 出错、`annotate` 被拒。这些图表不建标注，同一处出处里的 `p.N` 照样链到页。
  - 页：页码超出 PDF 的页数，不加链接。页数用 `pdfinfo` 读（poppler，`check_quotes` 本来就要它）。
- 只写节号、没写页码的出处（如 `Sec. III-A`）不加链接，也不按节号去猜页码（拿不准）。note-format.md 写一句说明：节号后面写上页码，出处就能点。T-CACE 的 145 处括号出处里 137 处带页码。

### 4.2 链接的写法，和怎么去掉

- 写法固定为两种：
  - 页：`[<记号>](zotero://open-pdf/library/items/<PDF key>?page=<n>)`，`n` 等于记号里的第一页；
  - 图表：`[<记号>](zotero://open-pdf/library/items/<PDF key>?annotation=<标注 key>)`，只带这一个参数。
- 去掉：正好是这两种形状（Markdown 链接，或转换后留成 `<a href="…">…</a>` 的）、文字是记号的，还原成文字；页链接还要 `n` 等于记号里的第一页，`[p.6](…?page=7)` 这种不动。不按 PDF key 限定：换版本时旧链接带的是旧 PDF 的 key，也要去掉。用户自己做的链接，形状或文字对不上的都不动（样例里的 `[p. 6](…?page=6)` 带空格，不是记号）。
- `prepare_note` 取出时去掉（笔记和 `.taken` 都去）；`put_note` 每次先去掉再加，所以 agent 改了页码或图号、用户在 Zotero 里改了出处文字，下次存时链接都跟着对。
- 不经 `prepare_note`、直接 `p2z note take` 的读者会看到链接，只是多些字。

### 4.3 PDF 的 key

`structured take` 取 PDF 时，已经把附件 key 写在 `<stem>.zotero.json` 的 `attachment` 里（T-CACE 是 `4UVJVU5R`）。`put_note` 只收笔记的路径，从笔记旁边的这个文件读 key，包和 PDF 也在旁边（`<stem>/`、`<stem>.pdf`）。换版本时取出的是新 PDF，key 也就是新 PDF 的。

「读的版本」要不要也记 key、PDF 改名后能不能按 key 找回，是 flows-not-run 那张 issue 里留给用户的另一件事，本设计不碰。两份审阅给的事实记到那张 issue 里：链接里带着 key；`read_library pdf` 已经能从 key 查到现在的标题。

### 4.4 标注

- 区域标注（`annotationType: image`），颜色 `#2ea8e5`（11-03 实测用的蓝色，用户认可"蓝框定位"；库里用户自己的 28 个标注都是高亮，没有蓝色），标签 `paper-read`，备注第一行 `paper-read · Table III`。页标签用 PDF 自己的页标签（期刊 PDF 上是印的页码）。排序键 `<pageIndex，5 位>|000000|<离页顶的点数取整，5 位>`，和 11-03 实测的 `00003|000000|00132` 一样；中间一段是字符偏移，写 0，同一页里排在高亮前面。
- 有了标签，用户可以在 Zotero 的标注栏里按 `paper-read` 筛选，把这些框藏起来或只看它们。
- 一份 PDF 上，同一张图或表只有一个 paper-read 标注，笔记里多处引用共用。
- **身份**：标签 `paper-read`，加备注第一行。用户在备注下面加了字，仍认得出。
- **已有的不改**：找到就用，不管位置和包里一样不一样（可能是用户自己调过）；同一个图表有两个时用最早的那个；没有才建。这几种情况都没有人要接着处理，所以不报。
- 笔记不再引用的、旧版本 PDF 上的 paper-read 标注：留着，不删。
- 用户在 Zotero 里删掉一个 paper-read 框，笔记还引用那张图表时，下次存笔记会再建出来。想不看这些框，按 `paper-read` 标签筛掉。
- 换版本以后，链接按新 PDF 重新生成，新 PDF 上建新标注。

### 4.5 paddleocr：`doc.py objects`

```bash
uv run scripts/doc.py objects <folder> --source <PDF>
```

- **只读**：不拿文件夹锁，不提交 Markdown 里没提交的编辑（别的 `doc.py` 命令都会），`load` 以后直接用 `blocks_view`、`figures_view`。
- 每行一个 JSON：`{id, kind: figure|table, key, number, page, page_label, rect, top}`。`top` 是框的上沿离这一页顶的点数，给标注的排序键用（p2z 没有读 PDF 的库，算不出页高）。`page_label` 用 PDF 自己的页标签，读不到（pypdfium2 不给、或 PDF 没有）就用页码。
  - `key` 是归一化的编号：`<fig|table>:<前缀><编号>`，前缀是空、`S`（Supplementary）或 `ED`（Extended Data），罗马数字转成大写，比如 `fig:3`、`fig:ED2`、`table:III`。图用 `conventions.figure_id`，表补一个同样的函数。`number` 是图注原样的写法，给人看。这个格式写进 `objects` 的 `--help`，是 paddleocr 和 paper-read 之间的接口：`put_note` 把笔记里的记号按它归一（`Fig.`、`Figure`、`Figs.` 都是 `fig`），两边各管自己那一侧。
  - `rect` 是 PDF 自己的坐标（Zotero 存标注用的那种），按这一页的页面框（cropbox）换算。库里有页面原点不在 (0,0) 的 PDF（`steinUseCarotidUltrasound2008` 偏 9 pt），doc.py 自己换算时本来就加了这个偏移。旋转页不给 `rect`。
- **图**：一张图被切成几块的（同一页、同一个图注），合成一个对象，框取并集；编号在不同页、不同图注上重复的，不给 `key`。
- **表：框住表的标题**（已定 2，用户选 A）：
  - 对象是表的标题块本身（`TABLE III` 那一行），`rect` 是标题块的框，编号就写在标题里，不用和表配对。点 `Table III` 跳到标题，表就贴在它上方或下方；蓝框圈住的是标题那一行，不是整张表。
  - 标题判定用严的那条（`figures.is_table_caption`，要求正文块在编号后面有标点），不用 `conventions.is_table_caption`（会把 "Table 7 shows that…" 当成标题）。
  - 同一个表号出现在不止一个标题上（如续表的 "TABLE I (continued)"），不给 `key`，这张表只链到页。
  - 为什么不框整张表：包里有表的框，也有标题的框，但哪个标题属于哪张表要按位置去猜。第一版审阅在库里试过：按顺序配只配上 72%，有 14 页会悄悄配错；改按位置配要借图的配对逻辑、在库里试验、抽查。框标题是确定的，整块都省掉了。
  - 这样也不用改 paddleocr 的处理、不用重新处理库里的包：标题块和它的框包里本来就有。

### 4.6 p2z：`annotate`

```bash
uv run scripts/p2z.py annotate <PDF 附件 key> --batch <file> [--dry-run]
```

- 每行 `{comment, color, tag, page, page_label, rect, top}`：`page` 从 1 数，`rect` 是 PDF 自己的坐标，`top` 是离页顶的点数。p2z 换算成 Zotero 的存法（`annotationPosition` 是 JSON 字符串，`pageIndex` 从 0 数，`annotationSortIndex` 照 §4.4）。
- 先读这份 PDF 的标注（`items/<key>/children?itemType=annotation`；不带 `itemType` 不返回标注，已实测），按 `tag` 加备注第一行找。
- 输出每行 `{comment, key, code: created | kept}`。
- 通用：p2z 不知道 paper-read，备注、颜色、标签都由调用方给。

### 4.7 paper-read：`put_note.py`，存笔记那一步

```bash
uv run scripts/put_note.py <note>
```

- 一条命令做完存笔记：去掉旧链接 → 认记号 → `doc.py objects`（有包、装了 paddleocr 时）→ `p2z.py annotate` → 把链接写进笔记文件 → `p2z.py note put <note> -i` → **存完把文件里的链接再去掉**（不管 put 的结果是什么）。工作文件除了存的那一下，始终没有链接，和 `.taken` 一样干净；`-i` 写回的 key 和 version 留在文件里。
- 输出 `{code, put, links: {pages, figures, tables}, unmatched: [{line, token, why}], annotations: {created, kept}}`：`put` 是 p2z `note put` 原样的那一行，`code` 就是它的 code（`ok`、`skipped`、`version_conflict`、`same_title` 等），照 SKILL.md 现在的写法处理。
  - 加链接哪部分做不了就降一级，不挡存笔记：查不到图表位置（没有包、没装 paddleocr、`doc.py objects` 出错、旋转页）或 `annotate` 被拒，这些图表就只链到页，原因进 `unmatched`，下游的原话带在里面（原则 §1"拿不准的不挡交付"）。
  - `failed`：笔记文件本身读不了、写不了，什么都不存。存一份没加上链接的笔记会把 Zotero 里原有的链接冲掉，所以不能绕过它直接 `note put`。
- 有 `--help`，列出输出和代码。
- **SKILL.md *Every change to a note* 改动**：
  - 第 4 步：`p2z.py note put <note> -i` 换成 `uv run scripts/put_note.py <note>`。这一步写 Zotero，只有主 agent 跑，读论文的 subagent 不跑。`version_conflict`、`same_title` 的处理不变（工作文件已经是干净的，和 `.taken` 比就是这次的改动）。
  - `unmatched` 由主 agent 看，对照 PDF：
    - 笔记写错了号或页码：按 *Changing a note* 改（精读时退回读论文的 subagent），再从第 3 步走；
    - 包里没有这个图表、旋转页、没有包、没装 paddleocr：留着，它只链到页；
    - `doc.py objects` 出错、`annotate` 被拒：按带着的原话修，修好重跑；修不了就留着，在汇报里说。
  - 完成条件：`put_note` 的 code 是 `ok` 或 `skipped`，`unmatched` 每一条都看过。
- *Sibling skills* 表：paddleocr 那一行加上"没有它时，图表只链到页"。
- `prepare_note` 取出时去链接，`.taken` 也去。它的输出不用加字段：`put_note` 自己读 `.zotero.json`。

## 5. 和设计原则对一下

- **§1 脚本只做确定的事**：记号是固定写法；表只在位置上确定时才配；编号重复、旋转页、对不上的都不猜，列进 `unmatched`，由主 agent 对照 PDF 看。
- **§1 一个写入者**：链接只由 `put_note` 写，只在存的那一下出现在文件里，文字由 agent 写；已有的标注不改，用户调过的框不会被改回去。
- **§3 每样东西一个家，"Orchestrate, don't absorb"**：坐标换算在 paddleocr（它本来就会，还管 cropbox）；Zotero 的存法在 p2z；表的编号用 paddleocr 现成的严格标题规则；认记号、去链接、引文范围在 paper-read 的一个模块里。
- **§1 拿不准的不由脚本定**：表框住标题，不去猜哪个标题属于哪张表（已定 2）。
- **§3 先去掉步骤**：agent 不写链接也看不到链接；key 从取出时写下的文件读，不让人传。
- **§4 只约束必须成立的**：读论文的 agent 没有新规矩，note-format.md 只多一段说明。
- **新加的机制**：paddleocr 一个只读命令（另给 conventions 加一个表编号归一的函数），p2z 一个命令，paper-read 一个脚本和一个共用模块，都是这件事本身必需的。

## 6. 不做的

- 引文跳到所在段落（已定 1 选了 A）。
- 节号按标题找页码（拿不准）。
- 删除或修改已有的 paper-read 标注（§4.4）。用户想让脚本删掉不再引用的框，再加。
- 「读的版本」记 key、改名后找回（留在 flows-not-run，§4.3）。
- 「大致看」和「细节」分层（另一张 issue），等真读过几篇再说。

## 7. 验证

1. **测试**（各 skill 自己的，样例是合成的，库里的 PDF 不进仓库）：
   - 认记号：§4.1 每种写法，引文原句、HTML 块、两种标记不动，加了再去掉逐字还原（含 `<a href>` 形状；`Table I/II` 只链 `Table I`）。会变成链接的写法从 note-format.md 那段说明里读出来测，不在测试里另抄一份：文档和代码对不上时测试就失败（和骨架那条测试一样）；
   - `doc.py objects`：合成记录上的图（切成几块的合并、重复编号）和表的标题（正文句子 "Table 7 shows…" 不当标题、同一表号出现在两个标题上时不给 `key`）；一个页面框偏移、页上有字的 PDF，测试里用 reportlab 生成（写进测试的 PEP 723 依赖），答案用 `pdftotext -bbox` 独立读出；
   - `annotate`：坐标换算、按标签和备注第一行找到已有的（备注下面加了字也认得）、有两个时用最早的，对着假 Zotero。
2. **库里的包**：`objects` 在全部包上跑一遍，不出错；报出图和表各有多少拿到了 `key`（只是了解，不设门槛）。
3. **实测**（要用户看的三项攒成一条消息，每项写明看哪里、对的样子是什么）：
   - T-CACE 笔记加链接、存进 Zotero，请用户点一个图、一个表、一个页码，确认跳得对、框得准；取出后和存之前逐字相同。第一次建标注时顺带确认两个从没经本地接口写过的字段：标签（用户在标注栏能按 `paper-read` 筛出来），页标签（读回来是 PDF 的页标签）；
   - `steinUseCarotidUltrasound2008` 的 PDF（页面原点偏移）上建一个标注，请用户看框的位置；
   - 找一篇有两份 PDF、还没有论文笔记的论文，建一条测试笔记，用 `--title` 换到另一份 PDF，确认链接和标注都落在新 PDF 上；测完把测试笔记和它在两份 PDF 上建的标注都清理掉。
4. 之后读一篇新论文时整条流程跑一遍（顺带 check_quotes 的新论文盲测）。

**实施顺序**：从下往上：paddleocr 的 `objects`，p2z 的 `annotate`，再是 paper-read 的共用模块、`put_note` 和 `prepare_note`，最后改 SKILL.md、note-format.md。表框住标题以后，没有哪一块要等试验结果。

## 8. 完成条件

- 三个 skill 的测试全过，新测试在改之前的代码上会失败；
- §7.2 的数报给用户，§7.3 的三项用户看过、对；
- writing-for-agents 过一遍改过的文字；issue 归档（flows-not-run 里 §4.3 的两条事实 2026-11-04 已经记下）。

## 9. 要用户定的

没有挡住实施的。可以以后再说的：不再引用的 paper-read 框要不要自动删（现在不删，用户可以按标签筛掉）。

## 10. 第二版改了什么（按两份审阅）

- 表的配对：换成严的标题规则，按位置配，复用 `figures.owners` 并反转方向（技术 1、忠实度 10）。后来被已定 2（框住标题）取代，见下面以「用户问」开头的一条。
- 编号按归一化的键比；切开的图合并；重复编号不给（技术 2）。
- 坐标由 paddleocr 按 cropbox 换算，旋转页不给框（技术 4）。
- HTML 块不加链接；去链接认 `<a href>`（技术 3）。
- 删去标记、更正标记里不加链接（技术 5、忠实度 3）。
- PDF key 从 `.zotero.json` 读，`link_sources` 只收笔记路径（技术 6、忠实度 2）。
- 「读的版本」记 key 这件事退出本设计，留给用户另定（忠实度 1）。
- 标注加 `paper-read` 标签；已有的不改（所以也不用比位置）；页标签用 PDF 的（技术 7、忠实度 11）。
- `objects` 只读；没装 paddleocr 时退到页（技术 8、忠实度 12）。
- 链接写法定死，去链接不按 key 限定（技术 9）。
- 认 `Table I/II`、`Figs. 3–5`、子图、`Fig.N`，不要求写的人改写法（忠实度 9、技术 10）；引文范围用 check_quotes 的规则（技术 10）。
- 存笔记那一步：谁跑、失败怎么办、`unmatched` 谁看、冲突后的顺序（忠实度 4、6、8，技术 12）。
- 节号没页码不链，note-format 加一句说明（忠实度 5、7）。
- 认记号、去链接放进一个共用模块（忠实度 14）。
- 测试的标准答案改用独立来源，加了库里能测到 T-CACE 测不到的情况（技术 11）；数字更正（技术 13）。
- 自查（用户：「你自己过一遍，看有没有什么问题，是否根据我们的 design principle 来的」）：`link_sources` 按部分降级、只在笔记读写不了时 `failed`，失败时不存（否则会冲掉 Zotero 里的链接）；`annotate` 去掉没人接的 `differs`、`duplicate`；会变成链接的写法从 note-format.md 读出来测；写明用户删掉的框会再建。
- 最后一遍全文检查（用户：「你最后再全部过一遍所有内容，看有没有问题，特别是一些低级错误，原则上、设计上、逻辑上的问题」）：骨架第二段是概要（正文），不是"笔记标题"，照常加链接；页记号只认 `p.N`，去掉和"`p. 6` 不算记号"矛盾的 `pp. N–M`；去页链接要 `n` 等于记号的第一页；`unmatched` 的原因前后列全，出错类的怎么处理分开写；页数用 `pdfinfo` 读；归一化的键写明格式、写在哪、两边谁归一；排序键写全；表配对"偏低"改成能判断的条件；`prepare_note` 不加没人用的 `pdf_key`；几处说法改准。
- 用户问「你觉得这个方案是最优最优雅的了吗？」之后：表改成框住标题，用户选 A（已定 2），表和标题的配对、库里的配对试验、比例门槛整块去掉；连写只链写全的第一个记号，去掉"只有编号的链接"这种特殊形状。
- 用户再问「现在是最优的了吗？」之后：加链接和存合成一条命令 `put_note.py`，存完马上去掉文件里的链接。存笔记从两条命令变成一条，不会漏掉加链接而冲掉 Zotero 里的链接；工作文件始终干净，版本冲突的流程不变，`--strip` 模式不要了。
- advisor 审过以后：连写编号的链接也能去掉；排序键要的离页顶距离由 `objects` 给；测试用的 PDF 用 reportlab 生成；两个没写过的字段在第一次实测时确认；要用户看的攒成一条消息；先做图、表的配对最后做。
