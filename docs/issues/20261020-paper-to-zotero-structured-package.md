# paper-to-zotero：Zotero 里每篇 PDF 一份结构化包，任何项目都能直接取来读

- 来源：用户 · 2026-10-19 提出，2026-10-20 立项
- 前置：[20261020-paper-to-zotero-top-down-restructure-fixed.md](archive/20261020-paper-to-zotero-top-down-restructure-fixed.md)，2026-10-20 已关闭，这张可以开始设计。
- 暂缓（2026-10-20）：用户「这边先暂缓一下，先去解决那个issue，解决完后你再重新恢复现在的现场」，先解决 [20261020-paper-to-zotero-pdf-version-by-title-fixed.md](archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)。那张 issue 2026-10-27 解决（库里附件都按版本改了名，`read_library pdf` 排第一的就是正式版），这张同日恢复。
- 状态：open。设计已定、已实现（`5d3df60`）。2026-10-28 全库 832 份 PDF 都挂上了结构化包，待推送、重装 skill 后关闭。除这张 issue 外一切只读：不改代码、不写 Zotero、不动各项目；这张 issue 随时记录讨论中得到的事实、用户的补充和方向。"已定"是用户拍板的；"10-28 重新设计"当天定稿，按这张 issue 直接实现，不写 spec。

## 目标

Zotero 里每篇论文的 PDF 都有一份结构化版本（paddleocr 的 md + json + 图），任何项目里的 agent 都能按条目取来直接读，不用再读 PDF，也不用每个项目各解析、各核对一遍。

用户原话：

- 2026-10-19：「现在遇到的问题是，我是分别存在不同的项目下的。你可以去看一下diffusion，jbhi-revision，ceus，hc_deduction，我现在这些结构化的内容都是散落在项目里的，如果对于一个全新的项目来说，agent想去阅读全文或者看主图，又需要结构化一遍，如果把pdf结构化的内容打包成zip添加到附件中，这样会不会更方便。」
- 2026-10-20：「我们现在问题的出发点是，我希望 zotero 里面的 PDF 有一个结构化的版本，这样 Agent 可以快速去查阅，而不用读 PDF。因为 Agent 在读取 PDF 的过程中，可能会存在或多或少的问题。」

## 现场（2026-10-19 盘点，外部项目只读）

| 项目 | 解析稿 | 格式 |
|---|---|---|
| hc_deduction | 267 篇，约 500 MB | 旧版 paddleocr。按 citation key 建目录，自建 `INDEX.md` 和解析队列，不入 git；都早于图核对 |
| diffusion | 28 篇，29 MB | 旧版 paddleocr。按 citation key 建目录，有自己的 README 规则、每篇一个 `meta.json`（Zotero key、标题、PDF 路径）、一个建索引的脚本 |
| ceus | 89 篇，225 MB | paddleocr 之前的自制格式（`full_text.md`、原 PDF、整页图），按"作者_年份"命名；76 个 DOI 里只有 9 个在 Zotero |
| jbhi-revision | 没有解析稿 | — |

- hc_deduction 和 diffusion 之间没有重复的论文，所以"同一篇解析两次"的成本还没真正花出去。已经在重复的是基础设施：每个项目各自发明一套目录、索引和元数据，两个项目里都有一张"citation key → Zotero key → PDF 路径"的对照表。
- **为什么值得存**：Zotero 自带的全文索引来自它内置的 PDF worker，是纯文本，最多 100 页，没有 LaTeX 和表格。实际对比 Self-RAG 的 Table 2：Zotero 的文本里列头被打乱，数字粘在一起（`40.739.979.7`），下标丢失（`Llama27B`）；解析稿里是带合并单元格的 HTML 表格。

## 已定

1. **PDF 是唯一的权威，结构化包只是从它派生出来、方便 agent 阅读的副本**（2026-10-19）。用户原话：「zip作为唯一正本怎么可能，唯一的权威肯定是pdf，结构化的压缩包仅是为了agent查阅快速阅读方便。」
   - 推论：包和当前的 PDF 对不上、丢了、或看着可疑，就从 PDF 重新解析；引用的数字照样回 PDF 核对，paddleocr 本来就这么要求。
2. **paddleocr 保持通用，不知道 Zotero**（2026-10-20）。用户原话：「Paddleocr应该坚持它原本的目的，不要被论文结构化这个任务带偏，应该保持通用。」`references/zotero.md` 已删（`e31713f`）。
3. **这个流程由 paper-to-zotero 负责**，由它调用 paddleocr（2026-10-20 与用户确认）。设想的走法，以在新项目里读 Restormer 为例：
   1. 按 citation key 找到条目里的结构化包。包里 json 记的源 PDF 哈希和条目当前的 PDF 一致，就解压到项目里直接读。
   2. 没有包，或者 PDF 已经换了（比如预印本换成了正式版）：`read_library.py pdf` 拿到 PDF → paddleocr 解析（这次要读就顺便核对）→ 打包挂回 Zotero。
   3. 在项目里核对、改了内容：重新打包挂回。

4. **多个版本都可以结构化**（2026-10-20）。用户原话：「如果有多个版本，你想打开哪个就打开哪个，结构化也可以全部结构化。」区分版本靠保存时的规范命名，见 [20261020-paper-to-zotero-pdf-version-by-title-fixed.md](archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)。
5. **包里放图片**（2026-10-28）。用户原话：「zip里我是希望放图片的，存储完全没有负担，而且你拿到压缩包就能看到，没必要再做一步。」
6. **包和 PDF 同名，不在前面加条目的 citation key**（2026-10-28）。用户原话：「结构化包命名和pdf名称一样就行了吧，有必要还在前面加一个条目吗？」
7. **从全局重新设计**（2026-10-28）。用户原话：「之前那个结构化包设计的不是很好，你重新设计一遍，从全局的角度」。
8. **解析出的文件夹只放临时文件夹，项目里不放**（2026-10-28）。用户原话：「我不太理解你为什么要在项目里面新建项目，因为这些结构化保存的目录，都应该是在临时文件夹下的。我结构化完成后，就会打包成 ZIP，然后添加到 Zotero 里面。以后其他的 Agent 或者其他地方要用的话，也是取这个 ZIP，解压到临时文件夹下，然后再操作。这样的话，就是随用随取，只要解压一下就好了。」又：「我这个项目下面也不应该放这种结构化的文档呀。我这个是 skills 文件夹。所以之前那个想法完全是不对的。」
9. **PDF 进库时就生成，库里现有的 PDF 全部补上**（2026-10-28）。用户原话：「PDF 进库时就生成。」现有的库先说「优先用那个版本，因为现在库里文件有点多」，我问指哪种之后改成：「算了，PDF库里面的PDF都结构化吧，不要搞那么复杂」。

已有的地基：

- paddleocr 产出一个完整的文件夹 `<stem>/`：`<stem>.md`、`<stem>.json`、`imgs/`；
- json 里 `source.sha256` 记着源 PDF 的哈希；
- 重新解析或升级时，之前的修改会带过去；
- `read_library.py pdf --cite/--key` 能给出条目 PDF 在本机的路径，正式版排在前面（`26e9bc9`，2026-10-20 实测通过）。

## 查到的 Zotero 事实（2026-10-19，Zotero 10.0.3 的文档和源码；"推断"指读源码得出、没有实测）

- **全文索引**：`text/*`（含 `.md`）、PDF、EPUB 会被索引，`application/zip` 不会。条目已经能通过 PDF 的索引搜到，再挂一份 `.md`，在"所有内容"模式下搜索大多只是多出重复命中（推断）。
- **`/fulltext`**：只对 PDF、HTML、EPUB 有效；`.md` 和 `.zip` 附件要通过 `/items/<key>/file` 读，它会 302 跳转到 `file://` 路径。
- **存储目录**：手动放进 `storage/<KEY>/` 的额外文件和子目录不能稳定同步。Zotero 官方说过不支持同步附件里的子目录（commit 76ae5d9）。zotero-mineru 插件把配图放在子目录里，正好踩到这个问题。
- **同步**：
  - 走 WebDAV 时，每个附件本来就会被打包成 `<KEY>.zip` 上传，挂一个 zip 只是外面再包一层（推断）；
  - 本地 API 上传的上限是 4 GB；文档里没找到 WebDAV 的单文件上限；
  - 用户的文件同步走自己 NAS 上的 WebDAV，2026-10-19 时 Zotero 数据约 4.9 GB。
- **替换附件文件**：
  - Zotero 10 的本地 API 能上传和替换附件文件，但要写入 key（`POST /api/local/authorize`）和 `Zotero-Server-ID` 头；
  - 读源码看，替换之后可能不会把文件标记为待上传，也就不一定传到 WebDAV（推断，没实测）；
  - zotero-docling 的做法更稳：新挂一个附件，再把旧的移进回收站（回收站 30 天内可以恢复）。
- **zip 附件**：不进索引，在 Zotero 里点开会用系统默认程序打开，默认不会被自动改名。
- **先例**：
  - MinerU、docling 一类插件都是直接挂 `.md`，图片或者不管、或者用 base64 嵌进 md、或者放进子目录；
  - 有一个插件把 md、json、图片分别挂成多个附件；
  - 没找到把解析结果打成一个 zip 挂上去的先例；
  - zotero-mcp（54yyyu）有 `attachment_priority`，会优先读用户挂的 Markdown。
- Zotero 8 到 10 都没有内置 AI 或 Markdown 功能；官方有一个语义搜索分支，还没发布。

## 2026-10-20 实测：新格式的包有多大

改版后图片改成 300 dpi 的 PNG。10-19 估的"每篇约 2 MB、全库约 1.5 GB"是按旧版 JPG 算的，已经不准。用草稿目录里143 篇新格式的解析稿，按 zip 压缩后计算：

| 内容 | 中位数 | 范围 |
|---|---|---|
| 整包（md + json + imgs） | 约 3.2 MB | 0.2–34 MB |
| 只有 md + json | 约 61 KB | 26–134 KB |

- 体积几乎全是图片，PNG 本身已经压缩过，打成 zip 也省不了多少。
- 按 800 篇算，整包约 2.6 GB，只放 md + json 约 50 MB。
- **图片可以从 PDF 重新裁**：`doc.py render <folder> --source <pdf>` 只要拿到 PDF，就会按 json 里每张图的框重新裁出 `imgs/`（`paddleocr/scripts/doc.py` 的 `build` → `write_images`）。所以"包里只放 md + json，图片取用时在本地从 PDF 裁"是一个可选方案，没有讨论过。
- **重裁实测**（2026-10-20，上面 143 篇里抽 6 篇，11–44 页）：拷贝一份、删掉 `imgs/`，跑 `doc.py render`（源 PDF 在记录的路径上），每篇 3.5–6 秒；`.md` 和全部图片与原来逐字节一致。

## 2026-10-20 查到的另外两件事（只读）

- **paddleocr 的命名**（读 `parse.py` 的 `resolve_input` 和 `process`）：文件夹名、md 和 json 的文件名都取输入文件名的 stem。输入是软链接时，stem 取软链自己的名字，`source.path` 记真实文件（`resolve()`），sha256 按内容算。所以给它一个 `<citation key>.pdf` 软链接，指向 Zotero 存储里的 PDF，解析出来就是 `<citation key>/`。
- **库里一个条目有几个 PDF**（只读统计）：785 个条目有 PDF，768 个一份，17 个两份：
  - 10 个是同一篇的不同版本（正式版加预印本、接收稿或投稿版）；
  - 2 个是正文加补充材料；
  - 5 个看标题分不出（两份都叫 "Full Text PDF"，或 "PDF" 加 "全文" 之类），可能是重复下载。
  - `read_library pdf` 的排序靠附件标题认版本（`paper.py` 的 `TITLE_PREFIXES`），认不出的 PDF 一律当正式版。那 10 对版本里有 3 对两份都被当成正式版，因为标题是 "Author manuscript (eScholarship, UCSF)"、"Related preprint v1 — …"、"已提交版本"（Zotero 中文界面下的 Submitted Version）。加上那 5 个，共 8 个条目的"排第一的 PDF"是并列的；并列时按添加时间排，跟版本无关。用户 10-20 定：这是 paper-to-zotero 本身的问题，单独一张 issue：[20261020-paper-to-zotero-pdf-version-by-title-fixed.md](archive/20261020-paper-to-zotero-pdf-version-by-title-fixed.md)。

## 10-28 重新设计（当天定稿）

10-20 用户问的两件事：「因为现在前置的 issue 已经解决了，要做结构化这个事情，但是你需要先跟我讲一下结构化后的文件夹结构」，「然后如果有多个PDF，应该如何解决呢？」。

这一版取代之前的三版（10-19 的倾向、10-20 和 10-27 的提议）：
- 图片放进包里（已定 5）；
- 包名去掉 citation key（已定 6）；
- 不再"排第一的那份叫 `<key>/`"，一律按附件标题命名。排第一的会变：条目原来只有预印本，后来存进了正式版，前者的名字就得跟着改；按标题命名就不用改。

10-19 倾向里沿用的一条：只挂 zip，不另挂 `.md`。

**一句话**：Zotero 里每份 PDF 旁边都有一个同名的 zip，装着 paddleocr 对这份 PDF 的完整解析（md、json、imgs）。p2z 在 PDF 进库时做出它；任何项目按 citation key 取出来就能读；读的时候核对改好的内容写回 Zotero，下一个读的人直接用。

**Zotero 里**

- **同名**：zip 和它的 PDF 在同一个条目下，标题相同（都是 `Published-OUP`），文件名也相同，只是扩展名不同（`attach` 默认的"<作者> - <年份> - <标题>"）。找 zip 按"同条目、同标题、类型是 zip"，不看文件名，用户在 Zotero 里改文件名也不影响。
- **内容**：zip 里是 paddleocr 的输出文件夹原样：`<标题>/` 下是 `<标题>.md`、`<标题>.json`、`imgs/`。
- **跟着 PDF 走**：PDF 改标题，zip 跟着改；PDF 进回收站（被同来源的新版本替代、去重），zip 一起进；合并条目时，zip 跟着它的 PDF 搬（`merge_items` 现在只搬 PDF）。
- **哪些有**：每份 PDF 都有，补充材料也有；网页快照没有，因为 paddleocr 不收 HTML。
- **不算版本**：读附件版本的地方（`read_library pdf`、`find_in_library`、lint，report 里"同一来源只留一份"）只看 PDF 和快照，zip 不当作一个版本。

**取用：解压到临时文件夹**（已定 8）

```
<临时文件夹>/                       ← agent 自己的草稿目录，用完即删
└── <citation key>/                 ← 同时读几篇时把它们分开
    └── Published-OUP/              ← zip 解压出来
        ├── Published-OUP.md
        ├── Published-OUP.json
        └── imgs/
```

- **项目里不放任何东西**：Zotero 是结构化包唯一存放的地方，每次用都从 zip 解压，只要几秒。10-28 上一稿在项目里建了 `zotero-papers/` 长期保留，用户问这是做什么用的。它只是省掉下次解压，不值得，而且会过期、会被 Synology 同步，已去掉。
- **citation key 这一层**：Zotero 里条目本身就是容器，zip 不用带 citation key；临时文件夹里一次可能解压好几篇，靠 `<citation key>/` 这一层分开。
- **PDF**：取的命令同时打印 PDF 在本机的路径，核对数字时用。paddleocr 用输入文件的 stem 给输出命名，这个名字由临时文件夹里一个叫 `<标题>.pdf` 的软链接提供（读 `parse.py`：stem 取软链接自己的名字，`source.path` 记真实文件，哈希按内容算）。
- **解压时的命名**：文件夹、md、json 一律按 PDF 当前的标题命名（paddleocr 要求三者同名，见 `doc.py` 的 `paths`）。如果标题在打包之后改过，解压时顺手改名。

**四个时刻**

1. **进库**：p2z 导入的第 4 步（存进 Zotero）之后，这一批新 PDF 在一次 paddleocr 调用里解析完，打包挂上。
   - 解析是 paddleocr 的脚本在 GPU 上跑，一次调用处理一整批，不派子代理。子代理只用来核对（用户 10-28 问：「结构化是不是每个条目派出一个 subagent sonnet去做的？」）。
   - 不做核对。paddleocr 的规则本来就是：批量解析、留着以后用的，第一次被读时再核对。
   - 没有 GPU 或解析失败，都不挡导入：PDF 照样存档，报告列出还没有 zip 的，以后补。
2. **读**：一条 p2z 命令按 citation key 把 zip 解压到临时文件夹，并打印 PDF 在本机的路径。可以指定版本标题，默认用 `read_library pdf` 排第一的那份。解压完直接读，不再让 paddleocr 检查是否最新。用户 10-28：「这个多余的检查步骤有必要吗？我感觉没必要吧。一般放在库里面的都是最新的，如果有问题，重新去结构化。」
   - 要读的地方还标着待核对：按 paddleocr 的第 2 步，交给一个 sonnet 子代理核对；
   - 发现解析有问题：对这份 PDF 重新结构化；
   - 没有 zip（比如在没有 GPU 的机器上导入的）：当场结构化；
   - 要 `--figure-text`、`--charts` 这类额外内容：另外解析，不写回。
3. **写回**：文件夹和 Zotero 里那份不一样了（核对时改过，或重新结构化过），就打包挂回，替下旧的。
   - **打包可复现**：条目按名字排序、时间戳固定，内容相同的文件夹打出来的 zip 逐字节相同。于是 md5 相同就说明没改，什么也不写。
   - **取出时记一笔**：解压时在文件夹旁边写一个隐藏小文件，记下取出的那个 zip 的 md5（没有 zip 就记"无"）。写回前比对 Zotero 里现在那份：还是它就替换；如果被别处先写回过，就停下，交给 agent 对照两边的修改记录合并。
   - **怎么替下旧的**：先实测本地 API 原地替换文件后 WebDAV 会不会同步（10-19 读源码推断可能不会）。会就原地替换，不涉及回收站；不会就新挂一个，旧的进回收站。
4. **体检**：lint 列出没有 zip 的 PDF、没有 PDF 的 zip、哈希和 PDF 对不上的 zip，交给第 1 步的流程补。

**paddleocr 更新以后能不能替换**（用户 10-28 问：「如果后面我们的结构化提取更新了，是否能做到替换？」）：能。
- **怎么知道旧了**：json 里记着记录格式（`format`）和处理代码的版本（`run.versions`），和当前的 paddleocr 一比就知道。
- **怎么更新**，分 paddleocr 自己的三种情况：
  - 处理或检查的代码改了（最常见）：从存着的模型输出重新处理，不用 GPU，核对过的修改都保留（`rendered: true`）；
  - 换了模型，要重新识别：`--force` 重新解析，要用 GPU；核对过的修改按块和文字搬到新结果上，搬不过去的标成 `stale_edit`，等核对；
  - 记录格式改了（`FORMAT`）：旧的挪到一边，整篇重新解析，之前的核对不会带过来（paddleocr 现在就是这样）。
- **什么时候换**：paddleocr 更新后跑一次整库更新：一条命令只读每个 zip 里的 json，列出旧的，批量更新后写回。取用时不检查。

**现有的库**（2026-10-28 只读统计）：
- 832 份 PDF，分属 815 个条目；其中 17 个条目有两份以上，都已按规范命名。
- 共 17,640 页，中位数 16 页，最长 171 页。
- 按每页 0.5–1 秒算，用同一个"进库"流程补一遍要 GPU 2.5–5 小时，可以后台跑。
- 按 10-20 实测的中位数 3.2 MB 算，库里多出约 2.7 GB。

**各项目里的旧解析稿**（hc_deduction、diffusion）：不搬也不改。以后在那个项目里读论文时改从 Zotero 取，旧目录怎么处理由用户定。

**改动范围（粗）**：
- p2z 新增一个脚本，负责放好、写回、补全；
- `attach_file` 允许上传 zip；
- 读附件的地方把 zip 认作 PDF 的结构化包，不当版本；
- `trash_item`、`update_item`、`merge_items` 让 zip 跟着 PDF；
- lint 加上面"体检"的三项；
- SKILL.md 改"读库里的论文"那一段，导入流程加一步；
- paddleocr 不改。

## 设计已定、直接实现（2026-10-28）

上面"10-28 重新设计"连同已定 8、9 就是定稿。用户：「这东西有必要写spec吗？直接用issue去结构化不就好了。而且这又不是优化我们的skills，就只是一个任务啊。只不过后面你在存pdf或者读的时候，相应需要增加一步，包括如果发现是没有的，或者有问题的。」核对照 paddleocr 原有的规则：「不是所有的都会派subagent只有拿不准在核对的时候才会派。」做的过程中碰到缺陷，另提 issue，解决后再回来：「如果你有遇到什么缺陷或者问题的话，你可以提issue，然后去解决，再回到我们结构化的这个任务中。」

实现（p2z 的 `structured.py`，加上几处小改动）和设计不同或补充的地方：
- **哪个 zip 算结构化包**：标题等于同条目某份 PDF 标题的 zip。不能凡是 zip 都算：Nature 的源数据就是 zip 补充材料（`Supplement-Nature-source_data`），现有测试抓到了这个冲突。
- **临时文件夹的布局**：`take` 在临时文件夹里放 `<cite>.<标题>.pdf`（指向 Zotero 存储的软链接，也就是 paddleocr 的输入）、`<cite>.<标题>.zotero.json`（这份来自哪个条目、哪份 PDF、取出的是哪个 zip；`put` 读它），有包就解压成 `<cite>.<标题>/`。用平铺的 `<cite>.<标题>`，是因为 paddleocr 一次调用只有一个 `-o`，全库一批解析时，名字得互不相同。zip 里面仍是 `<标题>/<标题>.md` 等。
- **读**：`take` 解压完直接读，不检查。没有包（`package: null`），或解析坏到没法就地修，就用 paddleocr 解析那个软链接，再 `put`。
- **写回**：`put` 打包可复现，内容没变就跳过。替换时新挂一个，读回确认后，旧的进回收站，不逐次问（写在 `structured.py` 的说明里）。原地替换文件那项实测没做，先用这个已知可行的办法。
- **跟着 PDF 走**：`trash_item` 把 PDF 移进回收站时，它的包一起进；`merge_items` 搬 PDF 时，它的包一起搬。PDF 改标题时包不跟着改，也没加 lint 检查：包对不上标题，读的时候就当没有，重新做。
- **SKILL.md**：新加"Reading a library paper"一节；第 4 步存好 PDF 之后，接着给这批 PDF 做包。organize.md 加"Structured packages"一节，写补全库和 paddleocr 更新后的整库更新。
- **补全结果**（2026-10-28）：先试 5 份，再在后台补 827 份，每批 100 份，用 vLLM 约 1 秒一页，共约 3 小时。第一轮挂上 774 份。没挂上的 53 份里：51 份是写回时 Zotero 一度没响应（用户正在 Zotero 里批量重命名文件），2 份是改名后，`take` 先前做的软链接指向旧文件名，解析失败。重跑一遍补齐，`take --missing` 再查全库为 0。832 份里 52 份没有待核对的标记；其余共 5674 处待核对，第一次被读时再核对。
- **文件名里的中文**：另见 [20261028-paper-to-zotero-english-filenames.md](20261028-paper-to-zotero-english-filenames.md)。
