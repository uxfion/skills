# paper-to-zotero：Zotero 里每篇 PDF 一份结构化包，任何项目都能直接取来读

- 来源：用户 · 2026-10-19 提出，2026-10-20 立项
- 前置：[20261020-paper-to-zotero-top-down-restructure-fixed.md](archive/20261020-paper-to-zotero-top-down-restructure-fixed.md)，2026-10-20 已关闭，这张可以开始设计。
- 状态：open。以下分成"已定"、"10-19 的倾向（没拍板）"、"待定"三部分，不要把倾向当成定论。

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

## 10-19 的倾向（没拍板）

- 每篇只挂一个 zip，不另挂 `.md`：另挂 `.md` 只换来重复的搜索结果，每次核对还要写两份。以后真用上会读 Markdown 附件的工具时，再加也不迟。
- 只放正文，补充材料不放（hc_deduction 里补充材料最大一份 66 MB）。
- 核对改了内容之后，顺手刷新：新挂一个 zip，旧的移进回收站。不刷新也不会出错，只是那份副本旧一点。我当时问"这样行吗"，用户没有回答，转去讨论包里的结构了。

## 2026-10-20 实测：新格式的包有多大

改版后图片改成 300 dpi 的 PNG。10-19 估的"每篇约 2 MB、全库约 1.5 GB"是按旧版 JPG 算的，已经不准。用草稿目录里143 篇新格式的解析稿，按 zip 压缩后计算：

| 内容 | 中位数 | 范围 |
|---|---|---|
| 整包（md + json + imgs） | 约 3.2 MB | 0.2–34 MB |
| 只有 md + json | 约 61 KB | 26–134 KB |

- 体积几乎全是图片，PNG 本身已经压缩过，打成 zip 也省不了多少。
- 按 800 篇算，整包约 2.6 GB，只放 md + json 约 50 MB。
- **图片可以从 PDF 重新裁**：`doc.py render <folder> --source <pdf>` 只要拿到 PDF，就会按 json 里每张图的框重新裁出 `imgs/`（`paddleocr/scripts/doc.py` 的 `build` → `write_images`）。所以"包里只放 md + json，图片取用时在本地从 PDF 裁"是一个可选方案，没有讨论过。

## 待定（一件一件定）

1. **包的格式和内容**：
   - 一个 zip，还是别的形式；
   - 放不放图片（见上面的实测）；
   - 只放正文，还是连补充材料一起放；
   - `attach_file.py` 目前只接受 PDF 和 HTML。
2. **什么时候刷新**：
   - 核对改了内容之后；
   - 新版 paddleocr 把旧包重新处理过（`rendered: true`）之后，要不要刷新；
   - 两个项目同时核对同一篇时，后挂的会把先挂的移进回收站，先挂的那份修改就丢了。
3. **一个条目有几个 PDF**（正式版、接收稿、预印本）：包跟哪个 PDF 走？哈希只认其中一个。
4. **命名**：Zotero 里的 PDF 文件名形如"Zamir 等 - 2022 - Restormer ….pdf"，直接解析得到的 stem 就是这个长名字。包和文件夹用 citation key 还是条目 key 命名？citation key 可能会改，条目合并后 key 也会变。
5. **在项目里解压到哪里**：一个不进 git 的缓存目录；各项目现有的对照表和 `meta.json` 由它替代。
6. **现有约 295 份旧格式解析稿**（hc_deduction、diffusion）：新版 paddleocr 会把旧格式归档、重新解析，不能直接沿用。重新解析每页约 1 秒（vLLM），核对还要再花子代理的 token。用到哪篇再处理，还是一次批量跑完？ceus 的格式不同，论文也大多不在 Zotero，10-19 的倾向是不动它。
