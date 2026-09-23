# paper-to-zotero — 问题草稿

使用中碰到的问题、用户随口提的痛点和建议，发生时就记，攒一批再统一整理优化（整理结果进新的 spec 或直接改 skill，条目标上去向）。每条要写到事后能还原现场：当时在做什么、跑了什么、看到了什么、为什么难受——用户原话照录、必要的背景、我查到的根因。只记事实和推断，推断标明；整理时看不懂的条目回头问用户。仓库公开：不写学校、代理域名、个人路径。

条目格式：`### N. 标题`，下列 来源（用户 / 使用 / 观察）· 日期、现场、痛点、为什么、方向（可空）、状态（open / 已处理 → 去向）。

---

### 1. 无 DOI 的手写条目跳过了查重，建出重复条目

- 来源：使用 · 2026-09-23
- 现场：v2 验证批次（用户 bib 里 6 篇）。`goodfellow2014generative` 没有 DOI：`doi_to_item.py` 返回 `invalid_identifier`，`find_in_library.py -i` 返回 `no_item`（记录里还没有 `item`）。随后我手写了 `item`，直接 `create_item.py -i` → `DEJDBSIY`（tmp）。整理 CC作业 时才发现库里早有 `9NB4JT94`：同标题，挂的 NeurIPS PDF 与新条目 MD5 相同。
- 痛点：去重只发生在 `find_in_library`；`item` 在查重之后才出现（或被改），`create_item` 不再查，重复就进了库。无 DOI、需要手写 `item` 的分支恰恰最容易漏掉这一步。
- 为什么：流水线把"查重"当成 agent 记得跑的一步，而不是写库前的不变量。
- 方向：`create_item` POST 前自己按 DOI / arXiv / 标题查一次，命中则跳过并写 `found`（幂等，agent 绕不过）；或 `find_in_library` 在记录上留下对当前 `item` 的查重戳，`create_item` 见不到戳就拒绝。倾向前者。
- 状态：open（库里的重复待用户裁定）

### 2. tagging.md 仍指向已不用的 `zotero` skill

- 来源：使用 · 2026-09-23
- 现场：整理 CC作业 读 tagging.md，"Choosing tags for one paper" 第 1 步写的是 "the `zotero` skill's `tags` command"。
- 痛点：v2 已不依赖该 skill，照做的 agent 会去找一个不该用的工具；正确的是 `read_library.py tags`。
- 为什么：v2 改文档时漏了这一处。
- 状态：已处理 → 2026-09-23 改 venue 规则时顺手改为 `read_library.py tags`

### 3. `read_library.py` 的输出形状没写

- 来源：使用 · 2026-09-23
- 现场：`read_library.py items --collection K | jq '.data | …'` 报 `Cannot iterate over null`。实际每行是条目 `data` 平铺（`key`、`version`、字段），没有 `data` 外层；而 `find_in_library.py --key` 输出 `{code, matches: [...]}`，形状又不同。`--help` 和 organize.md 都没说。
- 同类（同日整理时又碰到）：`file_and_tag.py --batch` 的 dry-run 输出把条目放在 `changes`，真写时放在 `results`；`read_library.py items` 没有 `--tag` 过滤（API 支持 `tag=`），按标签找条目只能全库拉下来再 jq。
- 痛点：写管道前得先 `head` 一行猜形状。
- 方向：`--help` 写一句每个子命令的行形状；或各脚本统一条目的形状。
- 状态：open

### 4. `file_and_tag` 不能把条目移出其中一个分类

- 来源：使用 · 2026-09-23
- 现场：用户可能要删 CC作业，先整理里面的文献。CycleGAN（`VNEXSRV2`）同时在 CC作业、自然图像、投稿文献/04 三处。只想去掉 CC作业：`collection` 只接受一个 key（替换成单一分类），`add_collection` 只能加，没有 remove。
- 痛点：清空一个分类再删掉是整理的常规动作，现在做不到。这次绕过：Zotero 删分类不删条目，所以只给其它条目加上正式归属，CC作业 原样留给用户删。
- 方向：single / batch 加 `remove_collection`；或 `collection` 接受列表。
- 再次碰到（同日）：用户在 Zotero 里合并 GAN 的重复条目后，原条目被带进了 `tmp`；要只去掉 `tmp`、保留 CC作业 和 自然图像，又只能在 scratch 写一次性脚本 PATCH `collections`。一天两次，优先级应提高。
- 状态：open

### 5. batch 文件只认 item key，不认 citation key

- 来源：使用 · 2026-09-23
- 现场：`file_and_tag.py --batch` 的每个条目必须有 8 位 `"key"`。
- 痛点：v2 的身份是 citation key（每个 `--key` 脚本都有 `--cite`），批量文件却退回到 item key，写 changes.json 时要来回查。
- 方向：条目可给 `"cite"`，解析方式同 `--cite`（查不到 / 不唯一照样报错）。
- 状态：open

### 6. 查一个分类里的重复和垃圾条目没有工具

- 来源：使用 · 2026-09-23
- 现场：为查 CC作业 的 12 篇有没有重复，只能对每个标题循环 `find_in_library.py --title`（12 次调用）。查出：GAN 重复（见 1）；两个未归类的 `webpage` 条目——CycleGAN 项目页快照（`7IA737QZ`），以及 SRCNN 的出版社页面（`LV5AVFU7`，URL 是机构代理主机加一次性 token，无附件）；CycleGAN 条目挂了两份 PDF（IEEE 版和 CVF 版，MD5 不同）。
- 痛点：整理时最该先看的"重复、孤立网页条目、一条多份 PDF"全靠手工拼。
- 方向：`find_in_library` 流模式也能吃库里的条目（`read_library.py items --collection K | find_in_library.py --dupes`），报告同 DOI / 同标题的其它条目；organize.md 的整理清单加上这三类。
- 状态：open

### 7. 字段异味只能肉眼看

- 来源：使用 · 2026-09-23
- 现场：CC作业 里 `7BTJMW24` 的 date 是 "十一月 23, 2021"（中文界面的 connector 存进来的），publicationTitle 放的是缩写 "ACM Comput. Surv."；`8PJ24U2W` date 是 "2023/1"（页面元数据，Crossref 为 2023-10-21）；`UV98FY94` 的 journalAbbreviation 放的是全称；StyleGAN、SRGAN 两条是 CVF 版，没有 DOI 和摘要，而同分类其它 CVPR 条目是 IEEE 版带 DOI。都是逐条看 JSON 看出来的。
- 痛点：12 条还能看，医疗图像 58 条就会漏。
- 方向：只读的 lint（对现有条目：日期能否解析、缩写与全称错位、缺 DOI / 摘要、同分类版本不一致），输出能直接喂给 `update_item.py --patch` 的 JSONL。
- 状态：open

### 8. 流程状态被做成了标签

- 来源：观察 · 2026-09-23
- 现场：读标签词表时看到 `投稿全文核查`（22）。核实后：它挂在 22 条**笔记**上，不在论文条目上——是 2026-09-22 另一个 harness 的稿件核查笔记的标记。tagging.md 写明阅读 / 审稿进度不是标签维度，但那条规则只讲论文条目。
- 痛点：笔记上的标签照样出现在 Zotero 标签栏里，和论文标签混在一起；`note.py` 靠 marker 识别自己的笔记，本不需要标签。
- 方向：待讨论。organize.md 的 Notes 一节说明笔记不打标签（marker 已够用），或者定一个笔记标签的前缀。
- 状态：open（该标签是否保留由用户定）

### 9. 稿件文献的分类结构不满意，但还不知道该怎么分

- 来源：用户 · 2026-09-23
- 现场：2026-09-22 另一个 harness 把用户一篇稿件的引用全部入库，自建了 `VQ-US Mixed-Supervision 投稿文献`（69 条）和 7 个编号子分类：01 最接近工作与新颖性（7）、02 数据对应与混合监督（10）、03 共享表征与网络（9）、04 比较方法与基线（12）、05 保真与评价依据（13）、06 背景与成像（13）、07 后续模型改进与前沿论文（5）。每条恰好落在一个子分类；24 条同时还在主题分类里（医疗图像、自然图像等）。
- 用户原话："其实我对之前那个 Agent VQ-US 这个，做的分类不是很满意，但我又不知道应该如何分类去做好，记一下"
- 痛点：用户说不出好的分法，只知道现在这个不对。
- 为什么（我的推断，未与用户核对）：子分类按"这篇在这份稿件的论证里扮演什么角色"来分——对一次修订有用，却是一份稿件、一个时点的视角，写成了库的结构；七个桶边界模糊（"共享表征与网络"和"比较方法与基线"常可两放），每篇只能进一个；已引用的和"候选 / 前沿新发现"混在同一棵树里；编号中文名看不出和论文本身的关系。skill 也没有"项目分类"和"主题分类"怎么分工的指引，organize.md 只说"只建用户点名的结构"，于是 agent 在项目任务里自由发挥。
- 方向：待和用户一起定（grill）。可选思路：项目分类只放"这份稿件引用的"一层（= bib），角色写进笔记或留在稿件的修订材料里；候选 / 新发现单独一层或进 tmp；主题归属靠主题分类和标签。先把"项目分类 vs 主题分类"的原则定下来，再写进 organize.md。
- 状态：open

### 10. 用户同意删除后，skill 里没有路可走

- 来源：使用 · 2026-09-23
- 现场：整理 CC作业 时提出把 3 个条目移到回收站（验证时建重复的 `DEJDBSIY`、两个孤立 `webpage` 条目），用户回"都同意"。organize.md 写的是"the trash is the user's own act — nothing here deletes"，`update_item` 拒绝 `deleted`，没有脚本可用；我在 scratch 里写了个一次性脚本（PATCH `deleted: 1`），被 Claude Code 自动模式的权限分类器以"Irreversible Deletion"拦下——实际上进回收站是可逆的。
- 痛点：v2 本想消灭一次性脚本，这里又逼出一个；而且用户明确同意了，动作仍落不了地，只能退回让用户在 Zotero 里手点。
- 为什么：设计时把"删除"整体划给用户，没区分"用户亲手删"和"用户授权 agent 移到回收站"。
- 方向：二选一，待定。(a) 保持用户亲手做，但报告里固定给出"待移入回收站"清单（条目键、标题、理由），交接清楚；(b) 加 `trash_item.py`（只设 `deleted`，带 `--restore`，dry-run 先列），命名写明可逆，权限规则可以对它单独放行。
- 状态：open（这 3 条目前待用户处理）

### 11. 出版物标签没有前缀，在标签栏里找不齐

- 来源：用户 · 2026-09-23
- 用户原话："你觉得出版物要不要也带一个什么东西/ 这样我在筛选标签的时候也能快速定位。如果没带分类前缀的话，就很难，比方说我想集中找 CVPR 的文章之类的"
- 背景：tagging.md 规定 venue 用不带前缀的缩写（`CVPR`、`TMI`、`Comput Biol Med` + `CBM`），和模型名（`CycleGAN`）、旧手工标签混在一起；库里约 40 个这样的出版物标签。刚整理完 CC作业，新增了 `TPAMI`、`TCBB`、`CSUR`、`CVPRW` 等。
- 痛点：在 Zotero 标签栏里按类过滤时，出版物没有共同前缀，无法一次列出全部出版物，也分不清哪个是出版物、哪个是模型名。
- 讨论：用户问"为什么是 venue？学术界对于这种期刊会议的一个统称是什么？"——答：CS 通称 publication venue（DBLP、Semantic Scholar 的字段名）；`source/` 与 tagging.md 的 source keywords 撞词，`pub/` 分不清 publication / publisher，`journal/`+`conf/` 要先分类。用户："就用venue"。
- 状态：已处理 → 2026-09-23 tagging.md 改为 `venue/<Abbr>`（同时写入新维度 `type/Survey`），全库 67 条、41 种出版物标签加了前缀

### 12. 提议删重复条目时没把信息差异讲清楚，用户合并后怕删错

- 来源：用户 · 2026-09-23
- 现场：整理 CC作业 时我提议把"tmp 里的 Generative Adversarial Nets（`DEJDBSIY`，我验证时重复建的）"移到回收站，只写了键和一句理由。用户在 Zotero 里用"合并条目"处理，随后问："我删除了，但是好像信息没有整理吧？我还是说我删除了那个信息全的，你帮我看一下，整理一下"。核实：合并保留的是原条目 `9NB4JT94`（有摘要、卷号），被合并掉的是 `DEJDBSIY`——没删错；但合并把 `tmp` 带到了原条目上，而重复条目独有的页码 2672-2680、`extra` 里的 arXiv 号没有带过来（Zotero 合并默认取主条目的字段）。我用 `update_item` 补了字段，又用一次性脚本把 `tmp` 去掉（见 4）。
- 痛点：用户看不出两条谁更全，只能凭印象操作，事后还得回头问；合并又悄悄带来了分类和字段的副作用。
- 为什么：提议里只有"删哪条"，没有两条的字段对照，也没有先把被删那条独有的信息并进保留的那条。本地 API 不能合并条目（合并只在客户端），skill 里也没有"处理重复"的步骤。
- 方向：organize.md 加"重复条目"一节：先列字段对照，定保留哪条，用 `update_item` 把对方独有的字段并过来，分类和标签取并集（`tmp` 除外），最后才请用户删除另一条（或在 Zotero 里合并时选保留那条）。可做成脚本：`dedupe.py --keep K --drop K2 --dry-run`，只合并信息，不删除。
- 状态：open

### 13. `check_pdf` 对 CVF 版 StyleGAN 报 title_not_found（误报）

- 来源：使用 · 2026-09-23
- 现场：CC作业 删除前核对 12 篇的 PDF（把库里条目拼成记录，`check_pdf.py -i`）。`G9D6XEKQ` 的 CVF PDF 返回 `title_not_found`、`first_author_found: false`，`excerpt` 是乱码（自定义字体编码）；同一文件 `pdftotext -l 1` 读出来标题、作者都对。
- 痛点：误报要人工再查一遍；提示里让去用 pdf skill，而机器上现成的 `pdftotext` 一步就能判。
- 方向：`check_pdf` 自带解析失败或乱码时，若 PATH 上有 `pdftotext` 就用它再判一次，并在结果里注明用了哪个提取器。
- 同次顺带：把库里条目当记录喂给 `check_item` / `check_pdf` 很好用（审计已有条目），但要自己拼记录（`item` 去掉 key/version/collections/tags、`file` 指向 storage 路径）；stdin 喂多个缩进的 JSON 对象时每一行都报一次 `invalid_json`（几百行），不如直接报"stdin 不是 JSONL / 数组"。可考虑 `read_library.py items --as-records`。
- 状态：open

### 14. `update_item` 改 `extra` 第一次报 readback_mismatch，重跑就成

- 来源：使用 · 2026-09-23（第二次复现）
- 现场：给 `UV98FY94` 的 `extra` 追加 `PMID: 38262200`（原 `extra` 只有一行 `TLDR: …`）：第一次 `update_item --patch` 返回 `readback_mismatch`、`applied: []`；原样重跑返回 `ok`（version 1254 → 1255），读回正确。v2 验证批次里给 qiu2020super 的 `extra` 加 PMID 时一模一样。
- 推断（未证实）：库里装着会写 `extra` 的插件（`TLDR:` 行就是插件写的），它在条目被修改时重写 `extra`，把我们刚写的内容盖掉，于是读回不一致；第二次它不再动（已有 TLDR）。
- 痛点：agent 看到 mismatch 不知道该信哪边；重跑能好，但原因不明。
- 方向：先验证推断（改一条带 TLDR 的条目的 `extra`，隔 1–2 秒连读两次看版本号是否被第三方 +1）；若属实，`update_item` 的读回在 mismatch 时等一下再读一次，并报告"写入后被别的程序改了（version 跳了 N）"。
- 状态：open

### 15. 没有 DOI 的论文怎么定位、给别人什么链接

- 来源：用户 · 2026-09-23
- 用户原话："那我想知道那些不发DOI链接的，我应该怎么定位到它？现在我的文献库里面的检索，给别人的链接，一般都是用什么的？"
- 背景：刚核对完 CC作业，GAN（NeurIPS 2014）没有 DOI，只有 `url`（proceedings.neurips.cc）和刚补上的 `extra: arXiv: 1406.2661`。全库统计（同日）：28 条没有 DOI——8 条是代码（computerProgram，GitHub 等，正常）；其余 20 条论文里，9 条 `url` 是 CVF Open Access（CVPR/ICCV 实际有 IEEE DOI，可补），4 条 NeurIPS、2 条 OpenReview（本来就无 DOI），4 条期刊论文没有 DOI（可疑），5 条连 `url` 都没有；只有 3 条带 arXiv 号。
- 痛点：没有 DOI 时用户不知道该靠什么找到论文、分享给别人；库里这类条目的标识参差不齐。
- 方向：定一条"每篇论文至少有一个可解析的标识"的规则写进 skill：有 DOI 用 DOI；没有就 `url` 指向官方页（NeurIPS proceedings / PMLR / OpenReview forum / ACL Anthology），并在 `extra` 写 arXiv 号（有的话）；导入时照此填，整理时作为 lint 的一项（见 7）。报告里给分享链接时按 DOI > 官方页 > arXiv 的顺序。
- 状态：open（已口头回答用户；是否对库里这 20 条做一轮补全待用户定）
