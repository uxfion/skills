# paper-to-zotero — 设计 spec v2(2026-09-23 定稿;实现中)

> 前身 `20260921-paper-to-zotero-spec.md`(v1,已冻结)在 v2 实现完成后加一行 `Superseded by`。v1 的事实(§3)、原则(§2)、gate 规则、标签规范继续有效,本 spec 只写**改什么、为什么改**。定稿经过 2026-09-23 的 grill 会话(Q1–Q11),用户裁定顶层方向,技术细节由设计者把控。

## 1. 为什么要 v2:证据

v1 的设计单位是"一篇"。它通过了三次验证,然后在 2026-09-22 被另一个 harness 拿去做了设计之外的事:把一篇稿件的 52 个引用键 + 7 篇候选 + 10 篇 papers.cool 新发现全部入库、补 PDF、修元数据、建专题分类、写核查笔记、按原引用键导出。它用了 skill 的脚本(`check_pdf` 8 次、`attach_file` 6 次、`file_and_tag` 5 次、`find_in_library` / `create_item` 3 次、`doi_to_item` 2 次),也写了 19 个自己的脚本,其中 `library_api.py` 只有 6 个函数——`call`(带版本的 GET/POST/PATCH)、`allrows`(翻页读全库)、`patch`、`add_membership`、`create`、`zotero_from_crossref`——每一个都是我们没给、或给了但**串不起来**的东西。复盘 24 条,追查到的根因:

| 痛点 | 根因 |
|---|---|
| 续办时要重新拼进度;同一篇早期失败与后来成功并存 | **R1 设计单位是一篇**:一篇的状态散在 4–5 个文件里,几十篇时没有布局、没有批量建条目、汇报只能数日志 |
| 常规批量修改要补很多代码,补完又修自己的遗漏 | **R2 只有"新建"原语**:v1 §9 不做建分类、笔记;改字段没脚本。**R1 的另一面**:33 篇 × 三步三文件在 shell 里循环太笨,进了 Python 就直接打 API,映射就在这里漏的 |
| 库里改好了,报告仍是上一轮 | **R3 真相在 Zotero 但读不回来**:没有"给定这些条目现在各是什么状态"的一条命令 |
| 用户说下载成功,agent 不知道文件在哪;收尾不知道哪些文件是本轮的 | **R4 环境事实要 agent 自己拼**:下载目录、`wait download` 只报之后的、opencli 在不在 |
| PDF 校验失败后仍要从零诊断 | **R5 `check_pdf` 只给一个布尔** |
| 20 个脚本、heredoc 堆积 | **R6 抽象层不够好用**:脚本是"带 flag 的命令 + JSON 输出",不读 stdin、一次一篇、没有通用读——到了 33 篇它写循环,写循环就写 API 层 |
| SKILL.md 195 行三种用法挤在一起 | **R7 分支材料内联** |

## 2. 顶层定案(grill 会话,用户裁定)

1. **定位**:paper-to-zotero = Zotero 的读写层 + 批量约定。上层任务(稿件核查、追热点、审读)靠 prompt 组合它,不长成 skill。一个 skill,导入 / 整理两个入口,按分支披露。
2. **身份**:一篇论文在 Zotero 里只有一个身份——原生字段 **`citationKey`**(Zotero 8 起原生;用户装的 Better BibTeX 已给 194 条中的 192 条生成并写入该字段;BBT 8 起"所有键都是钉住的",不会被重算覆盖;本地 API 的 BibTeX 导出直接采用该字段——2026-09-23 探针验证)。用户带键来(bib、清单)就钉住用户的键;没带就交给 BBT / Zotero 生成。**skill 不发明第二套键规则**。
3. **citation key 是用户面和 agent 面的第一标识**:用户提到论文用它;所有按条目操作的脚本都接受 `--cite <key>`;汇报、表、记录以它开头,8 位 item key 退为附注。
4. **bib 是导出物**:稿件 = 一个分类,`ref.bib` = 该分类的导出,键就是 `citationKey`,随时重生成;`\cite{citationKey}`。历史键的迁移不在本轮。
5. **接口按 Unix 方式**:每篇一条 JSON 记录;脚本是过滤器(stdin / 路径读记录,stdout 一行一条,`-i` 就地写回);管道让"循环"消失。通用**读**有,通用**写**没有(写只走带预检的领域脚本——通用写就是 curl,安全边界会没掉)。
6. **状态只在工作目录**;Zotero 只放最终事实;跑完即删。
7. **并行**:锁定 / 起草 / 标签可并行;拿 PDF 串行、一个浏览器 session、一次一个 gate。
8. **对第三方 `zotero` skill 的依赖收回**:它剩下的两个读取(分类树、标签)由 `ready.py` / `read_library.py` 提供。
9. 验证用真库:从旧 bib 47 条未引用条目里挑五篇混合批次落到 `tmp`。
10. **不做**:状态机 / 调度框架;通用写;全文审读、稿件编译;全局 uv 规则不加(用户否决);历史键迁移。

## 3. 记录与流

### 3.1 工作目录

```
<work>/                       ready.py 建(默认 ${TMPDIR:-/tmp}/paper-to-zotero;SKILL.md 让 agent 传 scratchpad 下的路径)
├── .started                  运行标记(mtime);Downloads 里比它新的文件是本轮的
├── sites.json                agent 记的站点状态 {"<host>": "no_subscription"|"gate_pending"|"ok"}
├── scratch/                  agent 的一次性代码与中间输出;整个目录是 residue
└── records/
    ├── <slug>.json           每篇一条记录(§3.2)
    ├── <slug>.pdf            要挂的文件(或 <slug>.html 快照);记录的 file 字段指向它
    └── …
```

单篇 = `records/` 里只有一条。residue = `<work>` 整个目录 + `p2z` session + Downloads 里比 `.started` 新的文件;成功后删;含 `blocker` 的记录所在的目录不删;没进库的 PDF 交给用户。

### 3.2 记录(唯一的接口)

```json
{
  "slug": "liu2022progressive",
  "id": "10.1109/JBHI.2022.3142076",
  "citationKey": "liu2022progressive",
  "item": { "itemType": "journalArticle", "title": "…", "creators": [], "DOI": "…", "url": "…", "…": "…" },
  "tags": [ { "tag": "…", "type": 0 } ],
  "collection": "9EYXTC2I",
  "checks": { "code": "ok", "…": "check_item 的报告字段" },
  "found": { "key": "…", "version": 0, "citationKey": "…", "collections": [], "tags": [], "attachments": [ { "key": "…", "contentType": "…", "linkMode": "…", "filename": "…", "md5": "…" } ], "checked_at": "…" },
  "saved": { "key": "…", "version": 0, "created_at": "…" },
  "file": "liu2022progressive.pdf",
  "pdf": { "code": "ok", "evidence": {}, "checked_at": "…" },
  "attach": { "key": "…", "md5_ok": true, "filename": "…", "url": "…", "attached_at": "…" },
  "blocker": "…"
}
```

| 字段 | 谁写 | 含义 |
|---|---|---|
| `slug` | `doi_to_item`(或 agent) | 文件名与第一标识:用户给了引用键就是引用键;否则 `<第一作者姓><年><题目首个 ≥4 字母的词>` 全小写只留字母数字(`liu2022progressive`),撞了加 `-2` |
| `id` | `doi_to_item` | 用户给的标识符原样(DOI / arXiv / URL / 题目) |
| `citationKey` | `doi_to_item`(用户给了键时)/ `find_in_library --readback`(从库里读回) | 用户给的键在 `create_item` 时写进条目的 `citationKey`(钉住);没给则建好后由 BBT / Zotero 生成,读回时填入 |
| `item` | `doi_to_item`;agent 改 | Zotero 条目 data(v1 同) |
| `tags` | agent | 完整集,`type` 0 手工 / 1 自动 |
| `collection` | agent 或 `create_item --collection` 的默认 | 落点 key |
| `checks` | `check_item` | 报告 |
| `found` | `find_in_library` | 库里已有;`--readback` 时按 `saved.key` / `found.key` 刷新 |
| `saved` | `create_item` | 已入库 |
| `file` | agent / 下载 | 相对记录所在目录的文件名;`paper.pdf`、`page.html` 之类都行 |
| `pdf` | `check_pdf` | 证据 |
| `attach` | `attach_file` | 已挂上 |
| `blocker` | agent | 卡在哪一步、哪个页面、时间、缺什么 |

**item key 的来源**:`saved.key`,否则 `found.key`,都没有 → 该脚本对这条报 `no_item_key`。**url**:`item.url`,否则 `https://doi.org/<item.DOI>`。

### 3.3 流的约定(所有读记录的脚本一致)

- **输入**:位置参数是记录文件路径(可 glob);没有路径就读 stdin——JSONL(一行一条)或一个 JSON 数组或单个对象。空输入 → `code: no_records`(exit 1)。
- **输出**:默认 stdout 一行一条**完整的更新后记录**(JSONL),可以接着管到下一个脚本。
- **`-i` / `--in-place`**:把每条更新后的记录写回它来的文件(只对路径输入有效;stdin 输入 + `-i` → 参数错误);此时 stdout 改为**每条一行摘要** `{"slug", "code", …该脚本的关键字段}`,最后一行 `{"summary": {"total", "ok", "skipped", "failed"}}`——`-i` 是"安静但可读"的模式,agent 的上下文不被 50 条完整记录淹没。
- **幂等**:每个脚本自己判断"这条已经做过"并报 `skipped`(§4 逐脚本写明),重跑无副作用。
- **失败隔离**:一条失败不影响其他条;退出码 0 = 全部 ok 或 skipped,1 = 有失败(看各条的 code),2 = 无法检查(Zotero 不可达 / 本地 API 关 / 没 key / key 属别的实例)。
- **`--dry-run`**:写脚本只做预检,输出与真跑同形,不写文件也不写库。
- **v1 的单对象参数全部保留**(`--doi X --out item.json`、`--item`、`--key`、`--pdf`…),行为与输出不变;新增 `--cite KEY` 与 `--key` 等价(§3.4)。
- stderr 只放诊断;stdout 只放 JSON / JSONL(`report.py`、`export_bib.py` 例外:它们的产物就是文本)。

### 3.4 `--cite` 的解析(每个接受 `--key` 的脚本都实现,算法一致)

1. `GET /api/users/0/items?q=<cite>&qmode=everything&limit=50`,在结果里找 `data.citationKey == cite`(区分大小写)的顶层条目;
2. 没找到 → 翻页扫 `/items/top?limit=100&start=…` 比对 `data.citationKey`(库不大;实现里写明这是回退);
3. 0 条 → `code: cite_not_found`(exit 1);多条 → `cite_ambiguous`(列 keys,exit 1);1 条 → 当作 `--key` 继续。
   实现前用真库只读验证第 1 步在本地 API 上是否命中;不命中就只留第 2 步。

## 4. 脚本

```
paper-to-zotero/scripts/
├── p2z.py               分发器:p2z.py <子命令> … = 同目录 <子命令>.py;p2z.py --help 列出全部子命令与各自的一句话(取各脚本 docstring 首行)
├── ready.py             (新;并入 authorize_local_api.py,后者删除)第 0 步:环境事实 + 授权 + 工作目录 + 分类树
├── read_library.py      (新)通用读:items|item|children|collections|tags|schema → JSONL,自动翻页
├── doi_to_item.py       标识符 → 记录(流);v1 单个 --doi --out 保留
├── find_in_library.py   记录 → found(流);--readback 刷新库内事实;v1 三种查法 + --key/--cite 保留
├── check_item.py        记录 → checks(流);v1 --item 保留
├── create_item.py       记录 → saved(流,≤50 一次 POST;钉 citationKey);v1 保留
├── check_pdf.py         记录 → pdf(流;证据化);v1 保留
├── attach_file.py       记录 → attach(流);v1 保留
├── file_and_tag.py      不变 + --cite
├── update_item.py       不变 + --cite
├── make_collection.py   (新)按用户要求建分类,幂等
├── note.py              (新)子笔记新建 / 按标记更新
├── export_bib.py        (新)分类 / key / cite / 记录 → BibTeX(键 = citationKey)
└── report.py            (新)记录 → Markdown 表 + 汇总
```

### 4.1 CLI 契约(实现以此为准)

```
ready.py [--work DIR] [--session NAME] [--downloads DIR] [--authorize] [--key-file] [--base-url]
  code  ok | no_key(exit 1;hint:先告诉用户要点 Always Allow,再加 --authorize)| authorize_denied / authorize_timeout(exit 1)
        | zotero_unreachable / local_api_disabled / server_mismatch(exit 2)
  out   {code, zotero:{reachable, base_url}, key:{present, server_match, key_file}, downloads_dir, opencli:{found, path},
         work_dir, records_dir, session, started(ISO;已存在则不动,报原 mtime), leftovers:[{path, bytes, kind: pdf|html|json|dir|other}],
         collections:[{key, name, parent, path}]   ← 分类树,path 如 "自然图像/Diffusion"}
  下载目录  --downloads > env PAPER_TO_ZOTERO_DOWNLOADS > WSL(/proc/version 含 microsoft):powershell.exe -NoProfile
        "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path" → wslpath,失败则 cmd.exe
        %USERPROFILE%\Downloads > Linux:xdg-user-dir DOWNLOAD > ~/Downloads;目录不存在 → null(不算失败)
  --authorize  缺 key 时执行 v1 authorize_local_api.py 的流程(POST /api/local/authorize,Always Allow,等 5 分钟,429 等 Retry-After),存到 key-file(0600)
  建 <work>/records/、<work>/scratch/、.started

read_library.py items [--top] [--collection K] [--key K…] [--cite C…] [--q TEXT] [--since V] [--limit N]
                item KEY | children KEY | collections [--tree] | tags [--min-count N] | schema
  JSONL:每行一个对象(items / children:本地 API 的 data 加 key、version;collections --tree 加 path;tags:{tag, type, count})
  自动翻页(limit 100);--limit 限制总数;items 默认 --top;stdout 空行不输出;exit 0;2 = 无法读

doi_to_item.py [--doi ID]… [--ids FILE] [--out FILE | --out-dir DIR] [记录路径…]
  输入  --doi 可重复;--ids 每行 `标识符[<TAB>引用键]`(# 与空行跳过);也接受 stdin 每行同格式;或已有记录(补它的 item)
  单个 --doi + --out:v1 行为不变(写 item.json,输出 v1 的报告)
  流    每个标识符 → 一条记录(slug、id、citationKey(给了引用键时)、item);--out-dir 写 <slug>.json 到 DIR(已存在 → skipped: exists,不覆盖);
        否则 stdout JSONL;失败的标识符 → 记录只有 slug/id 与 code(如 no_csl_record),不中断
check_item.py [--item FILE] | [记录路径…] [-i]
  流    每条记录 → checks;code ok | issues(exit 1 若有 issues 且非 accepted 映射——沿用 v1 判定)
find_in_library.py [v1: --doi|--arxiv|--title] | [--key K | --cite C] | [记录路径…] [-i] [--readback]
  单个  --key / --cite → v1 describe() 输出(加 citationKey、附件 md5);code found | not_found
  流    每条:有 saved.key / found.key 且 --readback → 按 key 读回,刷新 found(不存在 → code missing_in_library,记录里 found 删除、
        blocker 提示);否则按 item 的 DOI / archiveID / arXiv / title 查重 → 命中写 found(code found / near_match),未命中 code not_found
        (exit 0 表示查过;missing_in_library / 无法查 → exit 1)
create_item.py [v1: --item --collection --tags-file --out] | [记录路径…] [-i] [--collection K] [--dry-run]
  流    跳过有 saved 或 found 的记录(skipped);落点 = 记录 collection,否则 --collection,都没有 → failed: no_collection;
        tags = 记录 tags(没有 → 空,stderr 警告);记录有 citationKey → 写入 item.citationKey;
        ≤50 条一次 POST(同 v1 file_and_tag --batch 的 successful/failed 处理);成功写 saved;读回比对 collections / tags / citationKey
check_pdf.py [v1: --item --pdf] | [记录路径…] [-i] [--pdf FILE]
  流    文件 = 记录 file(相对记录目录)或 --pdf;没有 → failed: no_file
  evidence  {page_count, pages_scanned(≤3), title_page(int|null), doi_found(bool|null), first_author_found(bool|null),
        cover_page_suspected, collection_suspected(title_page ≥ 3,或 page_count > 80 且 title_page > 1), excerpt(首页), excerpt_title_page}
  code  ok(title_page == 1)| ok_on_page_n(2–3,exit 0)| title_not_found | no_text_layer | not_a_pdf(exit 1)
attach_file.py [v1] | [记录路径…] [-i] [--file F] [--url U] [--title T] [--dry-run]
  流    key 按 §3.2;文件 = 记录 file / --file;url 按 §3.2;attach.md5_ok 已 true → skipped;成功写 attach;HTML 走 v1 快照逻辑
file_and_tag.py / update_item.py   不变;--key 处加 --cite(§3.4)
make_collection.py --name N [--parent K|--parent-cite? 否,只有 K] [--dry-run]
  code ok(新建)| exists | ambiguous(同父多个同名,列 keys)| parent_not_found;out {code, key, name, parent, path}
note.py (--key K | --cite C) (--file F | --text T) [--marker M] [--dry-run]
  Markdown(段落、无序列表、# 标题、**、*、链接)→ 简单 HTML;--marker 时首段固定为标记行(形式由实现探针确定:探针条目在 tmp,用完删),
  已有同标记的子笔记则更新;code ok;action created | updated | unchanged;note_key
export_bib.py (--collection K [--recursive] | --key K… | --cite C… | 记录路径…) [--out FILE]
  本地 API `format=bibtex`,翻页合并(每次 ≤100 key:GET /items?itemKey=K1,K2,…&format=bibtex);输出 BibTeX 到 stdout 或 --out;
  stderr 汇总 {count, missing_citation_key:[…], duplicate_keys:[…]};缺键或重复 → exit 1(仍输出)
report.py [记录路径…] [--json]
  stdout Markdown:表(citationKey | 题目 | 年 | 库内 key | 分类 | 标签数 | PDF / 快照 / 无 | 阻塞)+ 汇总行;--json 输出同内容的 JSON
```

### 4.2 通用约定

沿用 v1:PEP 723 + 只用标准库、`uv run`、脚本互不 import(重复的 Api / Stop / load_key 允许)、稳定 `code`、退出 0/1/2、`--key-file` / `--base-url`、key 不进仓库不进汇报。新增:§3.3 的流约定;每个脚本 docstring 首行是一句话用途(分发器读它)。

### 4.3 测试

`paper-to-zotero/tests/test_<script>.py`,stdlib `unittest`,每个测试文件自带最小 `http.server` mock(不共享 fixture、不装依赖),`uv run tests/test_x.py` 可单独跑。覆盖:流的三种输入、`-i` 的写回与摘要、幂等(skipped)、失败隔离、各 code、`--cite` 解析的三种结果、`create_item` 的 50 条分块与 citationKey 钉入、`export_bib` 的缺键 / 重复。真库只做只读与 `--dry-run`;需要写的探针只在 `tmp` 下建 `[DELETE ME]` 对象并在结束时永久删除。

## 5. 文档

```
paper-to-zotero/
├── SKILL.md              目的、instruments(opencli-usage / opencli-browser / pdf / papers-cool-search;不再列 zotero skill)、
│                         身份模型一段、单篇八步(用记录与 p2z.py 写示例)、规则、限制;≈140 行
├── references/
│   ├── batch.md          触发:两篇以上、清单、bib、检索结果。§3 的目录与记录、管道示例、先全部锁定再一次问完、授权整轮沿用、
│   │                     并行规则(§2.7)、按站点 gate 与 sites.json、恢复(--readback)、report.py、scratch/ 属 residue、"skill notes"
│   ├── organize.md       触发:整理标签 / 分类、修字段、建结构、写笔记、导出 bib。按分类分批 + dry-run + 确认(v1 Organize)、
│   │                     update_item、make_collection(只建用户要求的)、note、export_bib、read_library 的用法
│   ├── publishers.md     不变
│   └── tagging.md        不变
└── scripts/、tests/
```

description 补触发词:清单 / bib / 检索结果里的论文、按 citation key 找 / 改 / 导出。README 一行不变。

## 6. 验证

1. 全部测试通过;所有脚本 `--help`;写脚本 `--dry-run` 对真库通过;`p2z.py --help` 列全。
2. **一批五篇**(旧 bib 47 条未引用中挑):库里已有一篇、arXiv 一篇、IEEE 一篇(gate)、机构未订阅一篇(快照)、无 DOI 记录一篇(识别退路);落到 `tmp`,引用键钉入 `citationKey`;中途人为中断一次,重跑同一批命令:已入库不重建、已挂不重传;`report.py` 与 `find_in_library --readback` 一致;`export_bib.py --collection tmp` 键正确。
3. 新 agent 演练:只凭 SKILL.md + batch.md 跑一批;记摩擦。
4. 整理:`医疗图像` 第一批(20 条)走 organize.md。
5. 收尾:v1 spec 加 `Superseded by`;本 spec 冻结;README 不变。

## 7. 修订历史

- 2026-09-23 草案:根因(§1)、目录即记录、D1–D9。
- 2026-09-23 定稿:grill 会话后改为记录流 + `-i`(Q8)、`citationKey` 身份模型与 `--cite`(Q11 + 用户补充)、收回 `zotero` skill 依赖(Q4)、`export_bib` / `report` / `read_library` / `p2z` 分发器、并行规则(Q7)、全局 uv 规则不加(Q10)。
