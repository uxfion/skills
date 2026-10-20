# paper-to-zotero：从顶层重构，每样机制只有一处实现

> **定稿**（2026-10-20）：advisor 审过两轮；你看过之后让我自审，觉得没问题就提交。实现过程中如有修正，直接改本文。
> 来源：[20261020-paper-to-zotero-top-down-restructure.md](../issues/archive/20261020-paper-to-zotero-top-down-restructure-fixed.md)。
> 依据：四份只读审查（复用、简化、效率、层次），原文在 issue 的参考资料文件夹 [`20261020-paper-to-zotero-top-down-restructure-reference/`](../issues/archive/20261020-paper-to-zotero-top-down-restructure-reference/)。报告里我对着代码确认过的，文中标"已核实"。
> 文中的行数、秒数、请求数都是我的估计，不是要求。

## 0. 目的和范围

**为什么要重构**：
- paper-to-zotero 有 21 个脚本，约 11.8k 行，测试约 6.9k 行。从 v1 到 v3，再到整理工具，新脚本都是复制旧脚本改出来的，所以同一样机制有好几种写法：
  - 访问 Zotero 的 `Api` 在 12 个脚本里有 8 种写法；
  - 按 citation key 找条目的 `resolve_cite` 在 7 个脚本里有 6 种写法；
  - 测试里的假 Zotero 写了 15 遍。
- 这些写法已经开始走样，有几处已经出错（§8）。最严重的一处会把 PDF 挂到错的条目上。
- 下一步的结构化包要上传附件、移进回收站、按 citation key 找条目，正好都落在重复最多的地方。

**这次做什么**：
1. 按流程的阶段重新分工（§2），每样机制只有一个归属；
2. 这些机制做成一个共享库 `scripts/p2zlib/`（§3），每个脚本只做自己那一件事；
3. 统一脚本的输入、输出、返回码和记录的写法（§4）；
4. agent 的用法收成一条主线，每步一条命令：ready → prepare → fetch → save → report → sweep（§2）；
5. 从根上修好取全文这一段，IEEE 这类页面不再每篇停下（§6）；
6. 测试共用一个假 Zotero（§10），SKILL.md 和 references 跟着变短（§11）。

**这次不做什么**：
- 导入的步骤划分（第 0–6 步）、三遍取全文的链路、门禁规则、标签规则都不变；
- "这个文件是不是这篇论文"的判定规则不变（check_pdf 的两条通过路径和三条否决）；
- 结构化包另写 spec（§13）；
- 投稿文献的分类不动。

**推翻的旧决定**。issue 里写"查过 v3 spec，没有'每个脚本必须自成一体'的决定"，这句不对。历版 spec 都有明文：
- v1 spec §2（标题是"原则（用户的明确要求）"）第 4 条："脚本单一功能、互不依赖……出问题易定位，单个可独立更新"；
- v2 spec §4.2："脚本互不 import（重复的 Api / Stop / load_key 允许）"；§4.3："每个测试文件自带最小 mock（不共享 fixture）"；
- v3 spec §5.2："脚本之间只通过子进程调用，不互相 import"。

本稿改为：
- 所有脚本都 import 同一个共享库；
- 脚本之间仍然不互相 import；
- 原来脚本之间的子进程调用改成函数调用，只有后台监控仍是单独的进程。

当初的理由逐条对照：
- **"互不依赖"**：现在的脚本其实互相依赖，比如 create_item 起 find_in_library 子进程，fetch 起 claim，claim 又起 check_pdf。重构后脚本只依赖共享库，彼此不再依赖。
- **"出问题易定位"**：现在一个问题要在好几份副本里找。统一后每样机制只有一个地方，定位更容易。
- **"单个可独立更新"**：skill 是整个文件夹一起安装、一起更新的（`npx skills add`），从来没有只更新一个脚本的做法。
- **"单一功能"**：保留。每个脚本仍然只做一件事，也仍然能单独运行。

## 1. 一个例子

沿用 v3 spec 的例子：把 Reflexion（给的是 arXiv 号）、一篇 Elsevier 期刊论文、一篇 IEEE TMI 论文加进 Zotero。和 v3 的例子有两处不同：库里已经有那篇 Elsevier 论文的预印本；这次它的正式版在一个机构库里有开放副本，第一条路线就能拿到。

**现在 agent 要跑的命令**（省略 `uv run scripts/`）：

```
ready.py --work W
claim.py --work W --watch --downloads D              # 后台
doi_to_item.py --ids ids.txt --out-dir W/records
find_in_library.py -i W/records/*.json               # Elsevier：found.code = near_match，指向库里那条预印本
fulltext_links.py -i W/records/*.json
check_item.py -i W/records/*.json
doi_to_item.py --redraft <NeurIPS 论文页> -i W/records/shinn2023reflexion.json
find_in_library.py -i …；fulltext_links.py -i …      # redraft 已写了 links，fulltext_links 跳过，arXiv 链接丢了
fetch.py --via http --pass 1 --downloads D W/records/*.json   # Reflexion、Elsevier 拿到
fetch.py --via page --pass 1 --downloads D W/records/*.json
                                                     # TMI 停在 no_pdf_link：agent 手动开 stamp.jsp，读出 getPDF.jsp，再打开
check_pdf.py -i W/records/*.json
create_item.py -i W/records/*.json                   # Elsevier：possible_duplicate，不建条目
attach_file.py -i W/records/*.json                   # Elsevier 的 PDF 挂到了库里那条预印本上（found.key 还在）
```

**重构后**（都经 `p2z.py`，省略 `uv run scripts/`）：

```
p2z.py ready --work W                                # 下载目录、浏览器会话记进 W/run.json，后面不用再传
p2z.py claim --work W --watch                        # 后台
p2z.py doi_to_item --ids ids.txt --out-dir W/records
p2z.py prepare W/records/*.json                      # 正式版候选、查库、列链接、预览字段一次做完；汇总列出要 agent 判断的：
                                                     #   Elsevier 有近似匹配（库里那条预印本）、Reflexion 有正式版候选
p2z.py doi_to_item --redraft <NeurIPS 论文页> W/records/shinn2023reflexion.json
p2z.py prepare W/records/*.json                      # 只重算依据变了的块（Reflexion 的），其余跳过
p2z.py fetch --pass 1 W/records/*.json               # 一条命令走完一遍链路：
                                                     #   Reflexion、Elsevier 在第一条路线拿到；
                                                     #   TMI 在出版社页面上找到"PDF"按钮 → 阅读页 → 页里的 PDF
p2z.py save W/records/*.json                         # 建条目、挂附件；挂之前自己核对文件；
                                                     #   Elsevier 还没有条目，不建也不挂，汇总里提醒 agent 去定
p2z.py report --work W W/records/*.json              # 报告直接读库
p2z.py claim --work W --sweep
```

整个导入就是一条主线：ready → prepare → fetch → save → report → sweep。中间要判断的地方，汇总都会列出来。

**agent 省掉的**：
- `-i`；
- 每次都要带的 `--downloads`；
- 起草之后三条命令一起跑、改了记录再一起重跑：换成一条 `prepare`；
- 每一遍按顺序跑五条路线：换成一条 `fetch --pass N`；
- 第 4 步前单独跑的 `check_pdf -i`，以及 `create_item`、`attach_file` 两条：换成一条 `save`；
- 第 5 步报告前的 `find_in_library --readback`；
- IEEE 的手动绕路；
- redraft 之后要记得清掉哪些块。

Elsevier 那篇，agent 判断是同一篇就在记录里写 `same_as`，不是就写 `distinct_from`，再跑一次 `prepare`、`save`。

**维护的人省掉的**：比如 Zotero 返回 403 时怎么报，现在有三种判法，分散在十几个脚本里。重构后只在 `p2zlib/zotero.py` 的一个函数里，改一处，所有脚本一起生效。

## 2. 顶层切分：阶段、产物、谁来做

导入的每一段，输入什么、产出什么、谁负责：

| 阶段 | 输入 → 产物 | 谁 | 用到的共享模块 |
|---|---|---|---|
| 认准 | 用户的话 → DOI / arXiv 号 / 论文页 | agent（papers-cool、OpenCLI、Crossref） | — |
| 起草 | 标识符或论文页 → 记录：`item`、`warnings`、`published_candidates` | `doi_to_item`；agent 修改 `item` | paper、web |
| 预览 | `item` → `checks` | `check_item` | zotero（schema） |
| 查库 | 记录 → `found`（确认的）或 `near_matches` | `find_in_library`；近似的由 agent 定 | zotero、paper |
| 列链接 | 记录 → `links` | `fulltext_links` | paper、web |
| 取文件 | 路线 + 候选链接 → 字节 | `fetch`；停下的页面由 agent 处理，门禁交给用户 | browser、web、run |
| 核对、归位 | 字节 → `records/<slug>[.版本].pdf` 和一条日志 | `claim`（调用 verify）；拿不准的由 agent 接收 | verify、run |
| 入库 | 记录 → 条目 key；文件 → 附件 | `create_item`、`attach_file` | zotero、verify、paper |
| 报告 | 记录 + 库的现状 → 报告 | `report`（自己读库） | zotero、run |

**agent 用的是一条主线**，每一步一条命令，都经 `p2z.py`：

| 步 | 命令 | 做什么 |
|---|---|---|
| 0 | `ready`、`claim --watch` | 准备工作目录，后台认领下载 |
| 2 | `doi_to_item`，然后 `prepare` | 起草；再把记录里算出来的块（正式版候选、查库、链接、字段预览）补齐 |
| 3 | `fetch --pass N` | 走一遍链路 |
| 4 | `save` | 建条目、挂附件 |
| 5 | `report` | 报告 |
| 6 | `claim --sweep` | 清点残留 |

- **`prepare`** 依次跑 doi_to_item（只补正式版候选）、find_in_library、fulltext_links、check_item。它们只读库和外部服务，不写库；每个都按"算完"规则（§4.4）跳过没过期的块，所以记录改了什么，重跑这一条就够了。汇总里每条记录列出要 agent 判断的地方：
  - 近似匹配；
  - 没定下来的正式版候选：条目仍是预印本，`published_candidates` 不为空，agent 也还没写 `keep_preprint`；
  - 字段问题；
  - 没答上的来源。

  这些都从记录本身就能看出来，不需要另设标记。
- **`save`** 依次跑 create_item、attach_file。两个都会写库，但都跳过做过的，所以每一遍取完文件后都可以原样再跑一次。导入的请求本身就是写库的授权，和现在单独跑这两条一样。
- `--dry-run` 两个命令都有，会传给它们跑的每个脚本。

`p2z.py` 本来就是转调各脚本的入口，顺序由它来管。`prepare`、`save` 像转调其他命令一样，用子进程依次跑各脚本，再把它们的 JSON 行合成一份汇总。脚本之间仍不互相调用，`p2z.py` 也不 import 它们；每个脚本仍可单独跑、单独测试。

另外两个入口不经过记录：
- **整理**（lint、merge、update、file_and_tag、trash、note、make_collection、export）：直接对库里的条目操作；
- **取用**（`read_library pdf`，以及以后的结构化包）：按 citation key 找条目、找附件。

这两个入口只用 zotero、paper 两个模块，不用 run（记录和工作目录是导入专用的）。所以结构化包可以直接建在第一期的成果上（§12）。

## 3. 共享库 `scripts/p2zlib/`

### 3.1 模块

| 模块 | 管什么 | 主要内容 |
|---|---|---|
| `cli.py` | 脚本的骨架 | `Stop`；输出 JSON 行的规则；参数（记录路径、`--key/--cite`、`--base-url`）；对记录、对条目的两种循环；`main` 包装 |
| `config.py` | 唯一的配置文件 | 读（严格、宽松两种）；写 key；`institution`、`openalex_key` 等字段 |
| `zotero.py` | 和 Zotero 本地 API 打交道的一切 | 客户端：请求、分页、`file://` 跳转（换成本机能打开的路径，WSL 下转换 Windows 路径）；状态码怎么换成结果码；服务器 id、写入 key、写入头；读：条目、批量条目、子项、检索、citation key → key、分类树、标签、schema；查库：库里有没有这篇、近似的有哪些、按 md5 找文件（判定用 `paper` 的规则）；写：批量 POST、带版本号的 PATCH（412 时重读、重试一次）、建附件加三步上传、移进回收站、建分类 |
| `paper.py` | 什么是"一篇论文"，只有规则，不碰外部 | DOI、arXiv 号的解析和比较；题名的规范化和相似度；`same_paper`；文件种类表（§4.6）；条目规则：标签、作者、正式版的 url、citation key 的毛病 |
| `verify.py` | 这个文件是不是这篇论文 | 用 pdftotext、pdfinfo 抽文字；判定（规则不变，勘误、补充材料的标记取自 `paper`）；HTML 快照的核对 |
| `run.py` | 一次导入的工作目录 | 目录布局和 `run.json`；记录的读、原子写（保留文件权限）、"算完"规则（§4.4）；日志 `fetch.jsonl` 的追加和读取；按种类找文件；认领：核对（调用 verify）后按种类归位、记日志，claim 和 fetch 都调用它；扫描下载目录；后台监控在不在跑 |
| `web.py` | 对外的请求 | 统一的 HTTP 请求和 User-Agent；每个主机的请求间隔表和 429 停用（有工作目录时跨进程保持，§6.6）；`Retry-After`；从 HTML 读 `citation_*` 等元数据；代理主机的判断和还原 |
| `browser.py` | 用户的 Chrome（经 opencli） | 会话操作；在页面上找 PDF 候选链接；取字节的阶梯：页内请求 → 像点击一样打开 → 下载或阅读器（§6） |

**分层**：`paper.py` 是纯规则，不做任何 I/O，所以最容易测、哪里都能用；碰外部的各有一个模块：Zotero 是 `zotero.py`，网络是 `web.py`，浏览器是 `browser.py`，工作目录是 `run.py`，PDF 工具是 `verify.py`。它们都可以用 `paper.py`，`paper.py` 不依赖它们。

**归属规则**：只有一个脚本用的函数留在那个脚本里；两个以上脚本用的放进库。库里只放机制，不放流程；流程在脚本、`p2z.py` 和 SKILL.md 里。

**规模**（估计）：库约 2–2.5k 行，其中约一半是从 check_pdf、fetch、find_in_library 搬过来的；脚本加库合计从约 11.8k 行降到 9k 行左右；测试从约 6.9k 行降到 5k 行左右。

### 3.2 一开始就要守住的约束

这几条守不住，第一期就会弄坏现有测试：
- **库是子目录** `scripts/p2zlib/`，不是平铺在 `scripts/` 下的文件。`p2z.py` 把 `scripts/*.py` 都当成命令，`tests/test_p2z.py:37` 也这样检查；子目录不在通配范围里，两边都不用改。不能叫 `p2z/`，那会遮住 `p2z.py`。
- **`prepare`、`save` 是没有对应脚本文件的命令**：`tests/test_p2z.py:37` 断言命令列表正好等于 `scripts/*.py`，这个测试要改成"脚本命令，加上 `p2z.py` 自己的命令"。
- **导入方式**：`uv run scripts/x.py` 运行时 `scripts/` 在 `sys.path` 上，`from p2zlib import zotero` 直接可用，和 paddleocr 的同目录导入一样。有 8 个测试用 `spec_from_file_location` 载入脚本，这种方式不会把 `scripts/` 放上 `sys.path`，所以共享的载入函数要补上这一步。
- **`Stop` 只有一种签名**：`Stop(code, *, exit=1, hint=None, **extra)`，`exit` 和 `hint` 只能按名字传。现在有两种签名，照搬过来会把 hint 当成退出码。
- **原子写要保留权限修正**：现在有 4 个脚本改写记录后，文件权限变成 0600（已核实：`attach_file.py:501` 用 `mkstemp` 而没有 `chmod`）。
- **安装要带上子目录**：仓库里还没有哪个 skill 的 `scripts/` 下有子目录。第一期装一次，确认 `npx skills add` 把 `p2zlib/` 一起装上了。

### 3.3 合并时要定的分歧

同一机制的几种写法行为不一样，合并时按下表统一。细节见参考资料里的 `reuse.md`。

| 机制 | 现在 | 统一后 |
|---|---|---|
| 403 | 有的脚本见 403 就算"本地 API 没开"，有的要看正文；写入被拒报成 `write_denied`、`files_not_editable`、`library_not_editable` 三种 | 正文含 "not enabled" → `local_api_disabled`（退出 2）；其他 403 → `write_denied`（退出 1，`detail` 写原文） |
| 412 | create 见 412 一律算服务器 id 不符；其他脚本看正文 | 正文含 "server-id" → `server_mismatch`（退出 2）；其他 412 → 版本冲突，重读后重试一次，再冲突是 `version_conflict`。PATCH 和批量 POST 的更新都这样：批量里冲突的那几条重读、重新计划、再发一次 |
| 超时 | 5–120 秒不等 | 默认 120 秒；个别调用另给（ready 的授权等待、report 读分类名） |
| 分页 | 11 处各写一遍；其中两处遇到异常页面会悄悄返回半截 | 只写一处，遇到异常页面就报错 |
| citation key → key | 6 种写法；merge 那份没有"检索没命中就扫一遍全库"的退路 | 一个函数：先检索，没命中的一起扫一次全库 |
| 子项 | 有的按 `parentItem` 过滤（本地 API 对不存在的 key 会返回全库），有的不过滤 | 一律过滤、分页 |
| 分类路径 | 7 处各建一遍；分隔符有 `" / "` 和 `"/"` 两种，有的含回收站里的分类 | 只建一处；分隔符 `"/"`；不含回收站里的分类 |
| 标识符 | 6 个解析函数；find 认 `url` 里的 doi.org，lint 不认，所以两个脚本判重复的结果不一样 | 一个函数：find 的规则，加上 DOI 格式检查 |
| 题名相似度 | 3 种算法；fetch 那份只认 ASCII，中文题名永远对不上 | 一个函数 |
| 标签 | create 遇到重复就报错；file_and_tag 保留后一个 | 去重，保留后一个，给警告；类型只接受 0、1 |
| 读记录 | 两族：一族有一个坏文件就全部不做，另一族把坏文件算一条失败；后一族读不了连在一起的多行 JSON | 一个读取函数，坏文件算一条失败；会写库的脚本写之前先确认全部有效 |

## 4. 约定

### 4.1 脚本骨架

每个脚本都长这样：

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""一句话用途。

--help 的正文：读什么、写哪一块、结果码、返回码。"""
from p2zlib import cli, run

def process(rec, ctx):        # 这个脚本唯一的那件事，对一条记录
    ...
    return cli.ok(...)        # 或者 raise cli.Stop("code", hint=...)

def main(argv=None):          # 测试在进程内调用 main([...])
    return cli.main_records(__doc__, process, argv)

if __name__ == "__main__":
    raise SystemExit(main())
```

- 模块的 docstring 就是 `--help`，不再另写一份 EPILOG。现在有 4 个脚本两处各写一遍，约 120 行。
- 对条目操作的脚本用 `cli.main_items`。没有第二条代码路径：
  - 对一个条目的命令，就是只有一个目标的批量；
  - 对一篇论文的命令，就是只有一条的记录。
- 代码和注释里不再写 v1、v2、spec 节号这类历史。

### 4.2 输入

- **记录**：只接受记录文件的路径（通配由 shell 展开），算完写回原文件。
  - 不再有 `-i`；
  - 不再从 stdin 读记录，也不再把整条记录打到 stdout。这条记录流原来只供脚本之间互相调用，改成函数调用后就没人用了。
- **条目**：`--key`、`--cite` 都可以重复给，也可以用逗号分隔。凡是接受 `--key` 的地方都接受 `--cite`（现在 `read_library item` 和 `children` 只收位置参数）。

### 4.3 输出和返回码

- **stdout**：
  - 只放 JSON：每个处理对象（记录、条目、文件）一行，紧凑格式；
  - 处理多个对象的脚本，最后加一行 `{"summary": {...}}`；
  - 例外照旧：`report` 输出 Markdown，`export_bib` 输出 BibTeX，它们的 JSON 行走 stderr；
  - stderr 只放给人看的诊断。
- **每行的形状**：`{slug 或 key[, cite], code, ...}`。读出来的数据不算：read_library 每行是库里的一个对象，lint_items 每行是一个有问题的条目和它的 `problems`，都没有 `code`；read_library 也没有汇总行。
  - `code` 不是 `ok` 或 `skipped` 时才有 `hint`；
  - 跳过一律是 `code: skipped`，加一个 `reason` 词。
- **返回码**：
  - 0 = 全部完成或跳过；
  - 1 = 有对象要 agent 处理；
  - 2 = 没法检查（Zotero 没开、没有 key……）。

  "找到 / 没找到""对上 / 没对上"是结果码，不是返回码。现在 find_in_library 的单条查询"找到"反而返回 1。
- **命名**：8 位的条目 key 一律叫 `key`（不叫 `item_key`）；输入里的 citation key 叫 `cite`；库里存的值叫 `citationKey`。
- **公共结果码**只有一张表：

  | 类 | 码 |
  |---|---|
  | 环境（退出 2） | `zotero_unreachable`、`local_api_disabled`、`no_key`、`key_rejected`、`server_mismatch`、`config_unreadable`、`no_pdftotext` |
  | 输入 | `record_invalid`、`no_records`、`no_identifier` |
  | 查找 | `not_found`、`cite_not_found`、`cite_ambiguous`、`collection_not_found` |
  | 写入 | `write_denied`、`version_conflict`、`write_failed`、`readback_mismatch`、`unexpected_response` |
  | 没跑 | `not_run`：前面一个对象遇到退出 2 的情况，后面的都没处理；停在哪一个，那一行写原因，汇总的 `stopped` 也写 |

  去掉的同义词：
  - `item_not_found`；
  - `invalid_record`、`invalid_json`、`unreadable`、`input_invalid`、`record_not_found`；
  - `no_id`、`invalid_identifier`；
  - `api_error`、`bad_config`；
  - `create_failed`、`attachment_create_failed`、`patch_failed`；
  - `files_not_editable`、`library_not_editable`；
  - `invalid_collection`、`invalid_tags_file`。

  各脚本自己的码（核对结果、`near_match`、`possible_duplicate`……）照旧写在各自的 `--help` 里。实现时定下的几个：
  - file_and_tag：给的改动本身有毛病（批量文件不是 JSON 列表、条目没指明条目、分类 key 写错、标签不合规、同一分类又加又删、标签文件不存在）一律是 `invalid_changes`，`detail` 逐条列出，什么都不写；它替掉了 `invalid_collection`、`invalid_tags_file`、`invalid_batch_file`；
  - 原来表示"已经是这样"的码都成了 `skipped` 加 `reason`：make_collection 的 `exists`、merge_items 的 `nothing_to_merge`、trash_item 的 `already_trashed` / `not_in_trash`、update_item 和 file_and_tag 的 `unchanged`；
  - export_bib 的 stderr 只有一行汇总：`count` 之外，`missing`、`duplicates`、`tex`、`not_found`、`unresolved`、`no_item_key` 这几张表不为空时才出现，有一张就退出 1。
- `fetch.jsonl` 的 `event`、`result` 字段不改名，因为 SKILL.md 第 0 步的监听命令按这两个字段过滤。

### 4.4 记录：谁写哪一块，什么时候算完

**记录里的字段分两类**，各有各的写入者：
- **agent 的字段**：
  - `item`：doi_to_item 起草，agent 修改；`--redraft` 时整个换掉；
  - `tags`、`collection`、`citationKey`、`alt_titles`、`distinct_from`、`blocker`；
  - `same_as`（新）：近似匹配里的那一条就是这篇；
  - `keep_preprint`（新）：有正式版候选，但这篇就用预印本，写明理由（用户要预印本，或者候选都对不上）。`prepare` 不再为它提醒，报告照写这个理由。

  脚本只读这些字段，不改；doi_to_item 建记录时写初值。agent 的每个决定都落在自己的字段里，从不去改脚本的块。
- **脚本的块**：每块只有一个脚本写。

  | 块 | 写的脚本 | 依据 |
  |---|---|---|
  | `published_candidates` | doi_to_item | arXiv 号、题名 |
  | `checks` | check_item | `item` |
  | `found` / `near_matches` | 查库函数（`zotero.py`），由 find_in_library 调用；create_item 建条目前查重也调用它 | 标识符、题名、`same_as`、`distinct_from` |
  | `links` | fulltext_links | DOI、arXiv 号、`item.url` |
  | `saved` | create_item | — |
  | `attach` | attach_file | 文件的 md5 |

  前四块由 `prepare` 补齐，后两块由 `save` 写。

**算完的规则**：只有一条，所有块通用。
- 块里记下它依据的输入，写成 `from`（一个短哈希）。
- 有的来源没答上（超时、429），就在块里写 `incomplete: [来源]`，已经拿到的照样留着。
- 重跑时，三种情况重算，其余跳过：
  - 块不存在；
  - 块带着 `incomplete`；
  - 块的 `from` 和记录现在的输入对不上。

  重算的那一行写明原因（`reason: absent | incomplete | stale`），agent 看得出为什么又算了一遍。
- `prepare` 补的四块（`published_candidates`、`checks`、`found`/`near_matches`、`links`）没有 `from` 的（旧版本留下的），一律当作不存在：读的脚本不信它，写的脚本重算它。`saved` 和 `attach` 是写库的记录，不是算出来的，照原样可信。所以接着跑一个旧格式的工作目录时，旧 `found` 里的近似匹配不会被当成确认的；`ready.py` 发现旧格式的记录就报告出来，第 4 步之前先跑一遍 `p2z.py prepare`。
- `found` 依据的是记录，不包括库的变化：查过之后用户往库里加了同一篇，`found` 不会自己知道。这由 create_item 建条目前的那次现查兜住（本来就故意每次现查）。

这一条替掉了：
- `--refresh`、`--candidates`、`--no-candidates`、`--sources` 四个开关；
- `--redraft` 要清掉哪些块的那张清单（`REDRAFT_CLEARS`）：redraft 只换 `item`，依据它的块下次运行自然重算；
- agent "改了 DOI 就删掉 `found` 和 `links`"这类手工步骤。

两个例外：
- `saved` 不重算：它表示"这次运行建的条目"，建好就不再变；库里后来的样子由 `report` 现读。
- `attach` 按 md5：换了文件就再挂一次，同 md5 的照旧不重复挂。

**建条目中途断了**：create_item 发 POST 之前，先在记录里写下 `saved: {"pending": true}`。连接断在半路时，条目可能已经建了，也可能没建。重跑时，记录带着 `pending`，建前查重找到的那条就是这次建的，记成 `saved`；找不到就照常建。所以重跑永远安全，SKILL.md 里 `post_incomplete` 那段"先读回再建"的特别说明可以删掉。`pending` 的 `saved` 没有 `key`：读 `saved.key` 的脚本（attach_file、report）都把它当作"还没有条目"。

**其他改动**：
- **`found` 只放确认的那一条**，近似的放进 `near_matches`。agent 判断后写 `same_as: KEY`（就是这一条），或者往 `distinct_from` 里加 KEY，再跑一次 `p2z.py prepare`，由查库写出 `found`。这样，读 `found.key` 的四个脚本（attach_file、export_bib、claim、report）再也不会把近似的当成确认的（§8 第 1 条）。
- **`saved` 从建条目起就是完整的形状**：POST 的回复里本来就有 `data`。`find_in_library --readback` 这个模式去掉，报告直接读库（§5 report 一行）；也就不再有"读回把库里的 citation key 抄进记录的 `citationKey`"这回事。
- **`attach` 只有一种形状**，总带 `version`。
- **`links` 只由 fulltext_links 写**。redraft 从论文页读到的 PDF 链接，改成 fulltext_links 的一个来源 `page`：当 `item.url` 是会议自己的论文页时，读这一页声明的 `citation_pdf_url`。
- **去掉的字段**：
  - `slug`：文件名就是 slug，现在两处各认一个；
  - `file`：没有脚本写它；
  - `pdf`、`pdf_accepted`：文件的事实放在工作目录里（§4.5）；
  - 失败时写进记录的 `code`、`hint`、`detail`：起草失败就不建记录文件，重跑时会再试；
  - `checked_at`、`attached_at`：没有脚本读。
- `collection`、`distinct_from` 读的时候一律当列表处理，给字符串也接受。

### 4.5 工作目录

v3 的布局不变：`records/`、`inbox/`、`stray/`、`unverified/`、`scratch/`、`.started`、`fetch.jsonl`。v3 的原则也保留："文件的事实不写进记录"，文件名就是种类，取文件、核对、认领的经过都记在 `fetch.jsonl` 里。

新增：
- `run.json`：这次运行的设置。`ready.py` 写下下载目录和浏览器会话名，后面的脚本都从这里读，所以 `--downloads` 变成可选；后台监控启动时把自己的进程号也写进来，它在跑时 `fetch` 就不自己扫下载目录（§6.5）。
- `pace.json`：每个主机上次请求的时间，以及被 429 停用到什么时候，读写时加文件锁（§6.6）。它写得频繁，所以不和 `run.json` 放在一起。
- `fetch.jsonl` 新增一种事件 `accept`：agent 用 `claim.py --accept` 接收一个核对没过的文件时，记下它的 md5 和理由（§5 的 claim 一行）。
- `scratch/schema.json`：Zotero 的 schema，一次运行只取一次。

### 4.6 文件种类表

一个文件是哪一种（正式版、接受稿、预印本、补充材料、快照），现在在 7 个地方各定义一遍，叫法也不一样；从库里的附件标题反推有两种写法，结果还不一致。统一成 `paper.py` 里的一张表。"版本"只是其中一列：补充材料、快照不是论文的版本，以后的结构化包也不是。

| 种类 | 论文版本 | 文件名 | 附件标题 | 作为"这篇的 PDF"的排序 |
|---|---|---|---|---|
| published | 正式版 | `<slug>.pdf` | `PDF` | 1 |
| accepted | 接受稿 | `<slug>.accepted.pdf` | `Accepted manuscript` | 2 |
| preprint | 预印本 | `<slug>.preprint.pdf` | `Preprint (<服务器>)`，如 `Preprint (arXiv)`、`Preprint (bioRxiv)` | 3 |
| supplement | — | `<slug>.supplement.pdf` | `Supplementary material` | — |
| snapshot | — | `<slug>.html` | `Snapshot` | — |

链接上还可能是 `unknown`（不知道是哪个版本），它不是文件种类：取到文件时按下面的规则定下来。

- 写文件名、写附件标题、从文件名读种类、从附件标题读种类，都查这张表。表里也收录库里已有的旧标题写法，读的时候认得出来。
- **文件没有自带版本时怎么定**，只有一条规则，三种情况都用它：候选链接的版本是 `unknown`；`fetch --start` 加的候选；`claim` 从下载目录认领的、或 `--accept` 接收的文件。规则沿用现在 claim 的做法：第 1 页页边有 arXiv 戳记 → preprint，否则 → published。agent 知道版本时用 `--version` 指明，指明的优先。
- 现在所有预印本都写成 `Preprint (arXiv)`，bioRxiv、medRxiv 的也一样；改成按服务器写。
- 结构化包以后就是表里多一行（种类 package，不是论文版本，不参加 PDF 排序），不必再定义第八份。

## 5. 各脚本：留什么、去掉什么

| 脚本 | 保留 | 去掉 | 变化 |
|---|---|---|---|
| ready | 各项检查、工作目录、分类树、`--authorize` | `--session` | 写 `run.json` |
| doi_to_item | `--doi`、`--ids`、`--bib`、记录路径、`--out-dir`、`--redraft` | `--out`（单条模式）、`--candidates`、`--no-candidates`、`--refresh`、stdin | 给已有记录时不重新起草，只按"算完"规则补 `published_candidates`（`prepare` 就这样用它）；起草失败不建记录；`published_candidates` 去掉恒等于 `doi` 的 `redraft` 字段，`sources` 一律是列表；redraft 不再写 `links`；读论文页用 `web` 的元数据函数；勘误标记和 verify 共用 `paper` 里的那一份 |
| find_in_library | 记录路径 | `--readback`、`--key`、`--cite`、`--doi`、`--arxiv`、`--title`、`--md5`、`-v`、stdin | 只做一件事：给记录写 `found` / `near_matches`。读回由 report 自己读库代替；按 key 或 citation key 看一个条目，用 `read_library items --cite` 和 `children`（organize.md 跟着改）；查库、按 md5 找文件变成库函数，create_item 和 claim 直接调用 |
| check_item | 记录路径、`--help` 里的骨架 | `--item` | schema 一次运行只取一次 |
| fulltext_links | 记录路径 | `--sources`、`--refresh` | `links` 的唯一写入者；新来源 `page` |
| fetch | `--pass`、`--start`、`--verdict`、`--window` | `--via`、`--version`（只剩 `--start` 的）、`--session`、`--current`、`--wait`、`--until`、`--for`、`--timeout` | 一条命令走完一遍链路，`--route` 只走一条（§6） |
| wait（新） | — | — | 从 fetch 拆出来：等这篇的文件到，或者等页面变化；自己什么都不记，结论由 agent 用 `fetch --verdict` 记 |
| claim | `--file`、`--scan`、`--watch`、`--sweep` | `--interval`；`--source`、`--via`（fetch 改成直接调用函数） | 新增 `--accept FILE --slug S --reason R [--version V]`：接收一个核对没过的文件并归位，代替现在的四步手工操作；没给 `--version` 按 §4.6 的规则定；扫描改成有状态的（§6.5） |
| check_pdf | 判定规则 | `-i` 写 `pdf` 块、`--item`、`--pdf`、`--match`、`--file-version`、`--alt-title` | 变成只读的查看工具：`check_pdf.py <记录> [--file F]` 打印判定和证据，什么都不写；核对本身在 `verify` 里，claim 和 attach_file 直接调用 |
| create_item | 记录路径、`--dry-run` | `--item`、`--tags-file`、`--out`、`--collection` | 建前查重直接调用库函数；POST 前先记 `pending`（§4.4），中途断了重跑即可；citation key 的毛病用共享的检查 |
| attach_file | 记录路径、`--dry-run` | `--key`、`--cite`、`--file`、`--url`、`--filename`、`--title`、`--accept`、`--pdf`、`--pdf-url` | 挂之前自己核对文件（或者这个 md5 有 `accept` 事件），所以第 4 步不再单独跑 `check_pdf`；文件还没取到时报 `skipped`（`reason: no_file_yet`），不算失败，这样取文件中途每次跑 `save` 返回码仍是 0，返回码 1 只表示 agent 要处理；经代理的网址先还原再存，不再拒绝；底下用通用的 `zotero.attach` |
| report | 记录路径、`--work`、`--json` | `--no-resolve`、stdin | 每个条目在库里现在的样子（分类、标签、附件）直接读库，这次做了什么从记录读，文件的事实从 `fetch.jsonl` 读；报告因此总是来自库，不再依赖先跑读回 |
| read_library | `items`、`children`、`pdf`、`collections`、`tags`、`schema` | `item` 子命令（就是 `items --key`）、`items --top`（本来就是默认） | `children` 接受 `--key/--cite`；`pdf` 按文件种类表排序，并给出 md5 |
| file_and_tag | 全部现有用法 | — | 单条就是只有一条的批量，只剩一条写入路径；单条的输出变成批量的形状 |
| update_item、note、trash_item、make_collection | 全部现有用法 | — | 建在 `zotero` 模块上 |
| merge_items | 全部现有用法 | — | citation key 解析补上扫描全库的退路 |
| export_bib | `--collection`、`--key`、`--cite`、`--recursive`、记录路径、`--out` | stdin | citation key 的毛病（缺、重复、含 TeX 特殊字符）用共享的检查 |
| lint_items | 现有用法 | `--only` | 判重复用 `paper` 的规则，和 find_in_library 一致；加 citation key 检查；代理主机用 `web` 的判断；`collection_not_found` 返回 1 |
| p2z | 列出并转调脚本 | — | 新增 `prepare`（doi_to_item 补候选、find_in_library、fulltext_links、check_item）和 `save`（create_item、attach_file），各合成一份汇总，列出每条记录要 agent 判断的地方（§2）；SKILL.md 的命令一律经 `p2z.py`；只在 `--help` 时才解析各脚本的 docstring（现在每次转调都解析 21 个，多花约 150 ms） |

`--base-url` 以及 `*_BASE_URL`、`PAPER_TO_ZOTERO_*` 环境变量留着，供测试使用。

## 6. 取全文（第三期）

### 6.1 路线

SKILL.md 里的链路分五步，代码里却是 `--via`、`--version`、`--start` 的组合。改成按路线命名：

| 路线 | 候选链接 | 对应 SKILL.md 链路的第几步 |
|---|---|---|
| `open` | `links` 里的正式版，再加版本未知的 | 1 |
| `publisher` | `https://doi.org/<DOI>`（没有 DOI 就用 `item.url`） | 2 |
| `discovery` | 图书馆检索系统里这篇的记录页 | 3 |
| `accepted` | `links` 里的接受稿 | 4 |
| `preprint` | `links` 里的预印本 | 5 |
| `snapshot` | 文章页本身（最后一遍） | — |

**一遍就是一条命令**：`fetch.py --pass N <记录…>` 按上表的顺序走前五条路线。
- 每条路线对所有还没有文件的记录走完，再走下一条，和 batch.md 现在要求 agent 手工做的顺序一样："一条路线走完全部论文，再走下一条"。出版社那条按网站分组走。
- 一篇拿到文件，就不再走后面的路线。
- 一条路线停在一个要 agent 看的页面上（`stopped`），整条命令就停下，标签页留在那一页。agent 处理完、记下结论，重跑同一条命令；已经试过的会跳过，从停下的地方接着走。
- 没有配置检索系统时，跳过 `discovery`。
- `snapshot` 不在这个顺序里：最后一遍还没有文件的，由 agent 单独用 `--route snapshot` 取。
- `--route <路线>` 只走这一条，用在单独补一条路线的时候。
- `--start <url> [--version V]` 是给某一篇加一个候选，不再是另一种模式；没给 `--version` 按 §4.6 的规则定。
- `--verdict`、`--window foreground`（最后一遍）照旧。
- **每个候选带着自己的版本一路传到 claim**。PMC 上的作者稿因此按接受稿归档，不再当成正式版（§8 第 3 条）；版本未知的链接也终于有路线去取。
- **一个候选怎么取**：`needs_browser` 为假，先用普通 HTTP，拿到的不是 PDF 再交给浏览器；为真，直接用浏览器。
- **一次尝试记作（篇、遍、路线、候选）**。重跑时跳过本遍已经试过的候选；agent 的 `--verdict` 结束这篇在这条路线上的这一遍。
- **停下不算一次尝试**。只有候选有了结果才记一次尝试：拿到文件、失败（比如对方拒绝、拿到的不是 PDF）、或者 agent 用 `--verdict` 记下的结论。
  - 停在页面上时，日志里记一条 `stop` 事件（篇、遍、路线、候选、页面），报告据此列出停过的页面；但这个候选仍算没试过。
  - 所以门禁过了、agent 重跑时，fetch 会在同一页上重试它。
  - 不想再试，就用 `fetch --verdict <结论> <记录>` 结束它：不加别的参数时，结束的是这篇最近一次停下的那个候选，agent 不用再指明路线和网址。
  - 明确的写法也保留：`fetch --verdict <结论> --route <路线> [--start <url>] <记录…>`，不管这些候选停没停过，都把它们结束。两种场合要用它：
    - 门禁等超时后，同一门禁后面的其他论文这一遍直接走下一条路线（门禁规则）。它们还没停过，不用逐篇再停一次；
    - agent 自己打开的页面。

### 6.2 在页面上找 PDF

现在只认 `citation_pdf_url` 这一个标签，没有就停下，所以 IEEE 每篇都停。检索系统和阅读器又各有一段代码。

改成一个函数，按任何页面都可能有的信号列出候选，并排好序：
1. `citation_pdf_url`；`<link rel=alternate type=application/pdf>`；
2. `iframe`、`embed`、`object` 的 `src`；任何一层框架里的 pdf.js 阅读器；
3. 文字或 `aria-label` 写着 PDF 的链接（"PDF""Download PDF""View PDF""Get PDF""Full text PDF"），或者路径以 `.pdf` 结尾、含 `/pdf/` 一段的链接。同站的排前面，购买链接排除。

每个候选都走同一个阶梯：页内带凭据请求 → 像点击一样打开 → 下载，或者从阅读器取字节。打开后落在一个 HTML 页面上，就在那一页上再找一次，只再找这一层。

有上限：拿到一个 PDF 就停；一页上最多试排在前面的 3 个候选（3 是我定的，实测后再调）。目录页、列表页上可能有几十个"PDF"链接，经学校的每次请求要间隔 15 秒，每次打开还可能往用户的下载目录里落一个文件。

这样做是安全的：拿到的每个文件都要经过 claim 核对，把关的是核对，选择器只管找。

IEEE 就自然通了：文章页上写着"PDF"的链接是 `stamp.jsp`，它打开的是一个 HTML 阅读页；在这一页上再找一层，就找到里面 iframe 的 `getPDF.jsp`。publishers.md 里 IEEE 的手工步骤缩成一句事实。

### 6.3 检索系统

现在的 discovery 路线按 Primo 写死了选择器（`a[href*="fulldisplay"]`、"Get PDF"、`uresolver`）。改成通用的：
- 检索页地址仍然从配置读（`institution.discovery`）；
- 结果页上，文字和这篇题名相似度 ≥ 0.9 的链接就是这篇的记录页。现在其实已经按 0.9 挑结果，只是先用 Primo 的选择器圈定范围；
- 记录页上用 §6.2 的函数找 PDF 候选。

这一条要在真实的检索系统上验证（§12）。如果不通，退路是在配置里给一个结果链接的选择器，代码里仍然不写某一家。

### 6.4 门禁等待

`fetch --wait` 拆成 `wait.py`，每 10 秒看一次这篇的文件和当前页面：
- 文件到了 → `arrived`；
- 页面出现 `--until` 的文字，或者没给 `--until` 时网址、标题变了 → `passed`；
- 5 分钟到了 → `timeout`。

它自己什么都不记。超时后，agent 照常用 `fetch --verdict gate_timeout` 记下结论。现在之所以要 `--for file` 这个开关，只是因为等待会顺手记一笔 `gate_timeout`；拆开后就不需要了。

结论词（`no_access`、`no_pdf`、`gate_timeout`……）在 fetch 里只有一张表，`--verdict` 按这张表检查，`--help` 列出全部。SKILL.md 和 publishers.md 只引用它。

### 6.5 扫描下载目录

**现在的做法**：
- fetch 每处理一篇之前、等待时每一秒，都起一个 `claim.py --scan` 子进程；
- 每次扫描先把每个新文件整个算一遍 md5，再看它是不是 PDF；每个 PDF 固定睡 0.2 秒；每处理一个文件，都重新读一遍全部记录；
- 后台监控每 3 秒也做同样的事，两边还会抢着认领同一个文件。

估计一批 50 篇里，光睡眠就要几分钟。

**改成**：
- 扫描是 `run.py` 里一个有状态的函数：
  - 记住下载目录里每个文件的名字、大小、修改时间，只处理变了的；
  - 先看文件头是不是 `%PDF-`，要匹配时才算 md5；
  - 连续两次大小不变就算下载完了，不再固定睡；
  - 记录目录变了才重读记录。
- 后台监控在跑（`run.json` 里记的进程还活着）时，只有它扫，fetch 只看 `records/<slug>.*` 有没有文件；监控没跑时，fetch 在自己的进程里扫。
- 3 秒的监控间隔、10 秒的门禁轮询、5 分钟的等待都保留。WSL 下，Windows 那边写进来的文件收不到 inotify 通知，所以轮询是对的，只是每一次要便宜。

页面路线被拒后，现在先等 25 秒看有没有下载，再花最多 20 秒看阅读器。改成在同一个循环里每秒两样都看，先出结果的就算。等多久看标签页：跳到了别的页面，最多等 20 秒，等它显示阅读器或 PDF 链接；留在原处，说明 Chrome 在下载，最多等 60 秒（PMC 的 PDF 从打开到落地要 45–60 秒）。直接打开的地址让标签页留在原处时，也按下载等。

### 6.6 请求间隔

**现在的问题**：
- 4 个脚本各有一张主机间隔表，而且只在一个进程里有效。agent 每次停下后重跑 fetch，经学校的 15 秒间隔就重新计时；"遇到 429，本次运行停用这个来源"其实只停到进程结束。
- fetch 的 http 路线遇到 429 后，还会继续请求同一个主机。
- medRxiv、bioRxiv 的 10 秒间隔挂在跳转之前的主机上，实际几乎用不上。

**改成**：`web.py` 里一张主机表、一个限速器。
- 有工作目录时，每个主机的上次请求时间和停用期限记在 `<work>/pace.json`（加文件锁），每次调用都读它。所以重跑也遵守间隔，429 也跨进程有效：停到 `Retry-After` 给的时间，没给就停一小时。不停整次运行，是因为没答上的来源（`incomplete`）要在同一次运行里过后再试（§4.4）；一小时是我定的，实测后再调。
- 没有工作目录时（整理工具），只在进程内有效。
- 间隔按实际请求的主机算；各主机的间隔数值不变。

batch.md 里"批量请求外部服务的脚本只在主会话里一次跑一个"这条照旧保留（浏览器本来也只有一个驾驶者），只是代码不再靠这条规则才守得住间隔。

## 7. 调用方看到的变化

issue 里写"对外的命令、参数和输出形状尽量不变"。审查后我的判断是：这些命令的调用方只有这个 skill 的文档，以及照着文档做事的 agent；文档里从没用过的模式和开关，留着只会让脚本更长、`--help` 更难读。所以：
- 文档里用到的全部保留，个别改名的，文档同步改；
- 只有测试在用、或者谁都没用的，去掉。

逐个开关的查证见参考资料里的 `simplification.md` §7。

| 方面 | 现在 | 之后 | 为什么 |
|---|---|---|---|
| 单条模式 | 7 个脚本另有一套单条模式（`--item`、`--doi --out`、`--key --file` 等），行为和批量不一样（比如 create 的单条模式不查重） | 去掉；单条就是只有一条的记录，或只有一个目标的批量 | 文档只用批量模式；只留一条代码路径 |
| 写回 | 要加 `-i` | 总是写回 | 文档每次都加 `-i` |
| stdin、stdout 上的记录流 | 8 个脚本支持 | 去掉 | 只有脚本之间互相调用时用，现在改成函数调用了 |
| 只有测试用的开关 | 约 15 个（§5 的表） | 去掉 | 文档里没有 |
| 结果码 | 有同义词 | 一张表（§4.3） | 同一件事一个名字 |
| 返回码 | find_in_library 的单条查询"找到"返回 1 | 0、1、2 的含义所有脚本一致 | 同上 |
| 输出 | 有的缩进、有的紧凑，有的没有汇总行 | 每个对象一行紧凑 JSON，多个对象再加汇总行 | agent 只需要会读一种 |
| `found` | 近似的也写进 `found` | 只放确认的；近似的在 `near_matches`；agent 写 `same_as` 或 `distinct_from` | §8 第 1 条 |
| 分类路径 | `" / "` 和 `"/"` 两种 | `"/"` | 只要一种 |
| `--downloads` | 每次 fetch、claim 都要带 | 可选，默认读 `run.json` | 第 0 步已经知道了 |
| 入口 | SKILL.md 里直接写各脚本 | 一律经 `p2z.py <命令>`；脚本仍可直接跑 | 一条主线：ready → prepare → fetch → save → report → sweep |
| 起草之后 | find_in_library、fulltext_links、check_item 三条，记录改了再三条一起重跑；正式版候选没答全要另跑 doi_to_item | `p2z.py prepare` 一条 | 这几条总是一起跑 |
| 取全文 | 每一遍按顺序跑五条：`--via http/page/discovery` 加 `--version`；等待用 `--wait` | 每一遍一条 `fetch --pass N`，按链路顺序走；`--route` 只走一条；等待用 `wait.py` | §6 |
| 第 4 步 | `check_pdf -i` → `create_item -i` → `attach_file -i` | `p2z.py save` 一条 | attach_file 自己核对；两条总是一起跑 |
| 中途断了的建条目 | 先 `find_in_library --readback`，再决定要不要重建 | 直接重跑 `save` | create_item 先记 `pending` |
| 第 5 步 | `find_in_library --readback` → `report` | `report` 一条 | report 自己读库 |
| 看库里的一个条目 | `find_in_library --cite` 和 `read_library` 两套 | 只有 `read_library` | 一件事一个工具 |
| 手工接收文件 | 移文件、改名、跑 check_pdf、改记录，共四步 | `claim.py --accept` | 一条命令 |
| 预印本附件的标题 | 一律 `Preprint (arXiv)` | 按服务器写 | bioRxiv 的也写成 arXiv，不对 |

## 8. 审查中发现的缺陷

这些都由上面的设计从根上解决，不单独打补丁。"已核实"是我对着代码确认过的；其余来自审查报告，实现时逐条核实。

1. **近似匹配的条目会被挂上 PDF**（已核实，会弄脏库）。
   - `find_in_library.py:780` 把近似的那条也写进 `found`，带着它的 key；`attach_file.py:558` 的 `item_key_of` 只要有 `found.key` 就用，不看 `found.code`。
   - 后果：agent 漏处理一个近似匹配时，create_item 报 `possible_duplicate`、不建条目；紧接着 `attach_file -i` 就把这篇的 PDF 挂到库里那条近似的条目上。那可能是预印本，也可能是另一篇论文。
   - export_bib、claim、report 也这样读 `found.key`。
   - → §4.4：`found` 只放确认的。
   - 2026-10-20 你定了先修：`9f2423b` 在 attach_file 里不把 `near_match` 的 key 当成条目 key（加了测试）。export_bib、claim、report 的同类读法不会写库，留给重构。
2. **会议论文页 redraft 之后拿不到 arXiv 链接**（已核实）。`doi_to_item.py:1408` 从论文页写了 `links`，`fulltext_links.py:434` 见到 `links` 就跳过。于是 ICLR、PMLR 这类论文，第 5 步的预印本路线永远是 `no_link`。→ `links` 只有一个写入者，加上"算完"规则。
3. **PMC 上的作者稿被当成正式版归档**（已核实一半：`fetch.py:431,449` 页面路线把版本传成了空值）。链接的版本 fulltext_links 本来知道，取文件时丢了。→ 候选带着版本走（§6.1）。
4. **版本未知的链接没有路线会去取**（已核实：fetch `--version` 的选项里有 `unknown`，但 SKILL.md 的链路没有一步用它，claim 的版本选项里也没有 `unknown`）。→ `open` 路线包含这些链接。
5. **改写记录后文件权限变成 0600**（已核实：`attach_file.py:501`；check_pdf、create_item、fulltext_links 同样）。→ 只用一个原子写函数。
6. **`attach` 有两种形状**：`already_attached` 那种没有 `version`，report 会把预印本当成正式版。→ 只留一种形状。
7. **find_in_library 和 lint_items 判重复的结果不一致**：find 认 `url` 里的 doi.org，lint 不认。→ 一个 `same_paper`。
8. **merge_items 的 citation key 解析没有扫描全库的退路**：别的脚本能找到的 key，它报 `cite_not_found`。→ 一个解析函数。
9. **检索系统路线的题名比较只认 ASCII**，中文题名永远对不上。→ 一个相似度函数。
10. **attach_file 用写死的正则判断代理主机**，不看配置；遇到经代理的网址就拒绝，而 fetch 明明知道怎么还原。→ 用 `web` 的代理函数。
11. **限速只在一个进程里有效**，429 停用也是（§6.6）。
12. **SKILL.md 说"每个接受 `--key` 的脚本都接受 `--cite`"**，但 `read_library item` 和 `children` 不接受。→ §4.2。

## 9. 审查意见的取舍

**采纳**：§3–§8 写进去的都是。

**改形采纳**：
- 简化审查建议"块写完整了才写，不完整就不写"。改成"块里记着依据和没答上的来源"：不完整时已经拿到的链接也有用，不能整块丢掉。
- 层次审查建议"检索系统的选择器挪进配置，或者交给 OpenCLI 适配器"。改成先用"结果链接的文字和题名相似"这个通用办法，验证不通才在配置里给选择器。
- 效率、层次审查都建议做共享的限速器。采纳，但 batch.md"一次跑一个"的规则照旧保留，不放开并行。

**不采纳**：
- 把 `lint_items` 的 `name_not_tagged` 改成证据或者去掉（层次审查）：它只列出候选，判断交给 agent，正是"能检测的检测出来，拿不准的交给 agent"的做法。
- 把"没有 DOI 记录"那段 connector 调用写成 `recognize.py`（层次审查）：这条路很少走，中间还要 agent 判断。只把这段从 SKILL.md 挪进 references。
- 外部接口批量请求（Europe PMC 用 OR、Crossref 用 filter）、OpenAlex 和 Europe PMC 并发请求、长连接（效率审查）：一批 50 篇估计只省几十秒，却要多一套批量和出错处理。以后真的慢了再说。
- PDF 抽字缓存（效率审查）：改成函数调用后，一个文件只在认领和挂附件时各抽一次，每次不到 1 秒。
- 库的快照缓存、按库版本号跳过建前查重（效率审查）：会读到用户中途改过的旧数据；建前查重本来就是故意每次现查的。
- 一次 POST 建多个附件条目（效率审查）：每个文件单独建、单独上传，出错时只影响一篇。
- Crossref 请求带 `mailto` 进礼貌池（效率审查）：要在配置里多加一项个人信息，而现在并没有被限速的问题。
- 把浏览器取字节的分块从 1 MB 调大（效率审查）：先查 opencli 的传输上限，如果 1 MB 是它的限制就不动。这是实现时核实的事，不算设计。

**留到实现时核实再定**：读回改成按 `itemKey` 批量读（效率审查）。前提是 `items?itemKey=…` 会连子项一起返回，这只是代码注释里的说法，没有实测过；本地 API 有过怪行为（对不存在的 key 返回全库）。先在 Zotero 10 上实测。

## 10. 测试

- **一个假 Zotero** `tests/fake_zotero.py`，是现有 14 个假服务的路由和故障钩子的并集：
  - 存储：`key → {version, meta, data}`，以及分类、标签、schema、文件；
  - 路由：检索的 q/qmode、`itemKey`、`since`、分页（`Total-Results`、`Link`）、子项的怪行为、`file://` 跳转、三步上传、批量 POST、带版本的 PATCH、回收站；
  - 认证：401、412、403"未开启"；授权对话框的脚本化回复；
  - 命名的故障钩子："改之前先涨版本号""第一次失败""回复缺字段"等。

  外部服务的假服务（doi.org、Crossref、OpenAlex、Europe PMC、各种页面）分开写，共用同一套服务器骨架。
- **共享的辅助** `tests/helpers.py`：
  - 关闭的端口：先绑定再释放。现在有 5 个测试用 `127.0.0.1:9`，在这台 WSL 上要等 12.6 秒才超时，约 85 秒，占整套测试的 43%；
  - 跑脚本的函数：每次都检查 key 没有出现在输出里；
  - 载入脚本的函数：把 `scripts/` 放上 `sys.path`；
  - 写配置、poppler 的替身、假 PDF。
- **测哪一层**：
  - 共享的情形只在库模块的测试里测一次：citation key 的检索和扫描退路、412 重试、分页和每块 50 条、连不上、key 不外泄、写回再重跑、算完规则；
  - 各脚本的测试只测它自己那件事，在进程内调用 `main(argv)`；
  - 每个脚本另留一个子进程冒烟测试，检查 shebang、返回码和 stdout 的形状。
- **跑法**：`uv run tests/run_all.py`，各文件各一个进程，并行跑。原来逐个文件跑约 199 秒。
- **回归的标准**：现有测试的场景。除了本稿明确改掉的行为，原来测过的都要照样通过。

## 11. 文档

按 writing-for-agents 改，目标是更短、更好用。

**SKILL.md**：
- 全篇的命令一律写成 `uv run scripts/p2z.py <命令>`；每一步开头先给那一条命令；
- 第 0 步：`ready` 写下 `run.json`，后面的命令都不再带 `--downloads`；
- 第 2 步：起草之后跑 `prepare`，按它的汇总逐条判断：
  - 近似匹配写 `same_as` 或 `distinct_from`；
  - 正式版候选：确认了就 redraft，就用预印本就写 `keep_preprint`；
  - redraft、改了 `item`，都只要再跑一次 `prepare`，不用记着清哪些块；
- 第 3 步：
  - 每一遍一条 `fetch --pass N`，停下就处理那一页再重跑；链路的五条路线按名字写，说明顺序由 fetch 自己走；
  - 手工接收文件用 `claim --accept`；
  - 门禁用 `wait.py`；
  - 结论词指向 `fetch --help`，`--verdict` 结束最近一次停下的候选；
  - 去掉"这几个文件名，一字不差"那张清单；
- 第 4 步：一条 `save`；去掉单独的 `check_pdf` 和 `post_incomplete` 那段说明；
- 第 5 步：一条 `report`；
- "No DOI record"一节挪进 references。

**references**：
- publishers.md：IEEE 的手工步骤和"取字节"一节缩成事实；
- batch.md：命令跟着改；"一条路线走完全部论文再走下一条"由 fetch 自己做，这段改成一句说明；
- organize.md：看一个条目改用 `read_library items --cite` 和 `children`，命令也经 `p2z.py`；
- install.md：写明库是子目录，装好后检查。

改完通读一遍，文档和代码对不上的地方一并改掉。

## 12. 实施顺序与验收

开工前打一个本地标签 `paper-to-zotero-stable-20261020` 作为回退点（和 paddleocr 一样，不推送）。

共享库、假 Zotero 和每类脚本的样板在主会话里写，接口由它们定下；之后各脚本互不相干，由子 agent 并行搬到库上（你 2026-10-20 要求能并行的就并行）。每个子 agent 只改自己的脚本和测试，不碰共享库；库里缺什么报回来，由主会话统一加。v3 第一次尝试时，五个子 agent 各自设计、各打补丁，结果是 15.4k 行；这次接口先定死，就不会那样。

每一期改了哪些行为，对应的文档就在那一期一起改，所以每一期都可以单独推送、安装、使用。

**第一期：共享库，以及整理、读取的脚本**（不涉及记录）
1. `tests/helpers.py`、`tests/fake_zotero.py`；
2. `p2zlib/cli.py`、`config.py`、`zotero.py`、`paper.py`，以及 `web.py` 的一部分：代理判断、进程内限速（lint_items 的 Crossref 请求要用）；
3. 把这些脚本搬上去：read_library、make_collection、note、trash_item、update_item、file_and_tag、export_bib、merge_items、lint_items；
4. 文档：organize.md，以及 SKILL.md 里讲整理和读取的部分（结果码、分类路径分隔符、`read_library` 的用法）；
5. 安装一次，确认子目录装上了；对真库做只读冒烟测试。

结构化包要用的四样东西，这一期就都有了：通用的 `zotero.attach`、`resolve_cite`、移进回收站、带路径和 md5 的附件列表。`zotero.attach` 这一期还没有脚本用，第二期 attach_file 搬上去时一起验收。

**第二期：导入流程**
1. `run.py`、`verify.py`；`web.py` 补上对外请求和页面元数据；
2. 把 ready、doi_to_item、find_in_library、check_item、fulltext_links、check_pdf、claim、create_item、attach_file、report 搬上去，记录的新约定（§4.4）一起落地；`p2z.py prepare`、`save`；
3. fetch 先只搬到库上，行为不变；
4. 文档：SKILL.md 第 0、1、2、4、5、6 步，batch.md，install.md。

**第三期：取全文**
1. `browser.py`；fetch 按路线重写，一条命令走完一遍链路，加上找 PDF 的函数、`wait.py`、有状态的扫描、跨进程限速；
2. 文档：SKILL.md 第 3 步和门禁一节，publishers.md；最后通读全部文档（§11）。

**验收**：
- 全部测试通过；`p2z.py --help` 列出全部脚本。
- 真库只读冒烟：`read_library`（含 `items --cite`、`children`、`pdf`）、对一个分类跑 `lint_items` 和 `export_bib`，结果和重构前一致（本稿改掉的，比如分隔符，除外）。
- 建条目中途断开：用假 Zotero 在 POST 回复前断开连接，重跑 `save`，不重复建、记成 `saved`。
- 整理工具在 `tmp` 下试：`merge_items --dry-run`；`trash_item` 移进回收站再恢复。
- `pace.json` 的文件锁：工作目录放在 `/mnt/c` 下（drvfs）时也能用。
- 一小批真实导入：约 10 篇进 `tmp`，开始前先告诉你，你要在线。覆盖：
  - 一篇 IEEE 论文：不停下就拿到；
  - 一篇 PMC 上的作者稿：按接受稿归档；
  - 一篇从会议论文页 redraft 的：拿到 arXiv 链接；
  - 一个近似匹配：不挂错；
  - 你手动点一次下载；
  - 检索系统路线；
  - 最后一遍。
- 每期到里程碑就提交；推送等你说；推送后从 GitHub 重装。

## 13. issue 去向

| issue | 去向 |
|---|---|
| [top-down-restructure](../issues/archive/20261020-paper-to-zotero-top-down-restructure-fixed.md) | 本稿；三期做完、验收通过后关闭 |
| [ieee-pdf-link](../issues/archive/20261018-paper-to-zotero-ieee-pdf-link-fixed.md) | 并入 §6.2；验收时 IEEE 论文不停下就拿到，即可关闭 |
| [manuscript-collections](../issues/20260923-paper-to-zotero-manuscript-collections.md) | 不在范围内，不动（你说过"先这样放着不要动"）。重构不对分类结构做任何新假设，`tmp` 仍是唯一会自己建的分类 |
| [structured-package](../issues/20261020-paper-to-zotero-structured-package.md) | 下一份 spec；用到第一期的 `zotero.attach`、`resolve_cite`、回收站、附件列表，以及文件种类表里多出的一行 |

## 14. 待你定

1. ~~近似匹配误挂附件（§8 第 1 条），现在先修，还是等重构时一起修？~~ 已定（2026-10-20）：现在先修，`9f2423b`。要生效得推送并重装，推送等你说。
2. **做到哪一期，再开始结构化包？** 已定（2026-10-20）：三期都做完再开始。当时的考虑——结构化包只依赖第一期，我建议三期都做完再开始：
   - 只做到第二期，fetch 已经搬到库上，但取全文的老问题都还在：IEEE 每篇停下、PMC 作者稿的版本、重跑时限速失效；
   - 你要的是全面地从顶层重做，不是先修一半。

   另一种做法是做完第二期就开始结构化包，第三期放到后面。

## 15. 修订

- 2026-10-20：预览稿；advisor 审过一轮（补上无版本文件的规则、`found` 的写入者、`main(argv)`、`web.py` 提前到第一期、文档随各期改、找 PDF 的上限、旧格式工作目录）。§14 两件事已定：近似匹配先修（`9f2423b`），三期做完再做结构化包。
- 2026-10-20：你问"从顶层、全局的角度是否合理且优雅"。我回头看，上一稿顺着审查发现、按机制组织，把代码内部理顺了，agent 的用法却几乎没变。改了四处：
  - 取全文一遍一条命令（§6.1）；
  - 起草后的三个只读步骤由 `p2z.py prepare` 一起跑（§2）；
  - "版本表"改成"文件种类表"（§4.6）；
  - `paper.py` 只放纯规则，查库挪进 `zotero.py`，碰外部的各有一个模块（§3.1）。

  另外，后台监控的进程号并进 `run.json`。advisor 复核时补了一条规则：停在页面上不算一次尝试（§6.1）；新命令叫 `prepare`，免得和要删掉的 `--refresh` 开关混淆。
- 2026-10-20：你让我自己再过一遍。按新设计从第 0 步走到第 6 步，又改了这些：
  - `prepare` 也补正式版候选，管全部四个算出来的块；
  - 新增 agent 字段 `keep_preprint`，免得汇总一直提醒；
  - `stop` 记成一种事件，但不算尝试，`--verdict` 结束最近一次停下的候选；
  - `save` 合并建条目和挂附件；
  - report 自己读库，`find_in_library --readback` 去掉；
  - create_item 先记 `pending`，中途断了直接重跑；
  - `find_in_library --cite` 和 `read_library` 重复，去掉前者；
  - 命令一律经 `p2z.py`，整个导入是一条主线；
  - 认领函数放进 `run.py`，路径转换放进 `zotero.py`。

  advisor 收尾检查后又补了三处："没有依据就当不存在"只管 `prepare` 的四块，`pending` 状态下当作还没有条目；`--verdict` 保留指明路线的写法，门禁超时后可以一次结束同一门禁后的其他论文；文件还没到时 attach_file 报 `skipped`，不算失败。

- 2026-10-20：实现第一期时的修正（共享库和假服务先写定，各脚本由子 agent 并行搬，审查后统一修）：
  - 批量 POST 的更新也按 412 规则重读、重新计划、重试一次（§3.3）；
  - 各脚本的码：file_and_tag 的 `invalid_changes`，"已经是这样"一律 `skipped` 加 `reason`，export_bib 的 stderr 只有一行汇总（§4.3）；公共码表补上 `collection_not_found` 和 `not_run`，数据行的例外写明；
  - dry-run 什么都不写，所以不需要 key；
  - 429 的停用期限（§6.6）；
  - 第二期再做的：`paper.same_paper` 和查库函数随 find_in_library 一起搬；export_bib 的记录到条目改用 `run.item_key`（要等导入脚本写出带 `from` 的 `found`）。
- 2026-10-20：实现第二期时的修正：
  - 起草只写记录，不查正式版候选；候选由 `prepare` 在记录上补（§2 的"起草"一行，产物里的 `published_candidates` 来自 `prepare`）。起草的输出行以 `id` 开头，记录写成后才有 `slug`；起草失败不建文件。
  - doi.org 的 429 和断网是退出 2，后面的标识符 `not_run`；某个 DOI 的 5xx 只算这一条失败（`doi_org_error`）。
  - create_item 每条记录一次 POST，不再 50 条一批：每条先记 `pending` 再发，中途断了只影响那一条。
  - "找到 / 没找到"算完成，改成各脚本自己声明（`answers`），不再是全局的：update_item 等脚本里的 `not_found` 仍是失败。
  - `p2z.py prepare/save` 把 `--base-url` 经环境变量 `PAPER_TO_ZOTERO_BASE_URL` 传给各脚本（不是每个脚本都连 Zotero）；四个预备脚本都接受 `--dry-run`。
  - 扫描下载目录挪进 `run.py`，claim 和 fetch 直接调用，脚本之间不再有子进程调用。fetch 的路线不变，留给第三期。
  - 条目类型表（字段顺序、基础字段、创建者类型）只在 `zotero.types_of` 一处；服务地址的测试替换只在 `web.endpoint` 一处；"问一个服务拿到正文或原因"只在 `web.read` / `read_json` 一处。
  - 真库验收：一篇测试论文走完起草 → prepare → 取文件 → save（建条目、挂附件，重跑全部跳过）→ report → 移进回收站 → 恢复 → 再移进回收站，都对。
- 2026-10-20：实现第三期时的修正：
  - `fetch --start` 的候选记在路线 `start` 下，不算任何一条路线的尝试；`--verdict` 带 `--route` 而不带 `--start` 时结束整条路线（网址为空的尝试）。
  - 浏览器部分放进 `p2zlib/browser.py`（打开、页内脚本、取字节、在页面上找 PDF 候选），fetch 和 wait 共用。
  - 下载目录的扫描是 `run.Scanner`：两次看到同样大小才算下完，不再固定睡；`claim --scan` 只看两次，间隔半秒。
  - 测试：fetch 的 19 个测试换成 6 个场景（路线顺序、停下与结论、页面阶梯含 IEEE 式阅读页、检索系统、快照与 `--start`、门禁等待）。IEEE 和检索系统在真实页面上的验证留到下一次和你一起的真实导入。
- 2026-10-20：代码审查（规范、spec 两路）之后的修正：
  - 三处一样的"停下就 `not_run`"循环合成 `cli.Lines`；查库并写 `found` 合成 `run.look_up`；HTTP 失败归类只在 `web.read` 一处；文件种类里"是论文本身"的那几种只在 `paper.PDF_KINDS`；条目 key 在报告里也叫 `key`。
  - fetch 只信按"算完"规则成立的 `links`（旧格式、过期的不用，并提示先跑 `prepare`）；经检索系统的请求按学校的间隔；页面阶梯每试下一个候选前回到给出候选的那一页；嵌入框架只在像 PDF 时才算候选。
  - 预印本附件的标题按文件的来源（`fetch.jsonl` 里的认领事件）写服务器。
  - wait.py 保留 `--file-only`：最后一遍用户自己在那一页上操作，读页面会把用户的翻页当成"过了门禁"；监控没跑时它自己扫下载目录。
  - p2z 的汇总：一步没给某条记录输出就退出了，也算这一步失败。
  - "No DOI record" 一节挪进 references/no-doi-record.md；install.md 写明共享库是子目录。
- 2026-10-20：真实页面测试时的修正：
  - 检索系统没登录时，guest 结果不能当作"不在检索系统里"：`fetch` 看到登录提示或"Sign in"按钮就停下（`why: sign_in`）。这一页本身不是门禁；点它自己的登录、选本校入口，是 agent 的事，走到账号密码页才是门禁。
  - fetch 停下后，看页面、点页面的活交给后台 subagent，用便宜的模型（Claude Code 里是 sonnet，Codex 里是 luna；主对话换不了模型）；它自己读页面、自己点，带回四种结果之一：文件到了、一个可能通向 PDF 的地址、一个放到用户面前的门禁、一个带证据的结论。主 agent 留在用户身边，按协议记录、重跑。
  - browser.py 改用 opencli 自带的命令读页面（`get url/title/html`、`extract`、`find`、`wait text`），只留它没有的三段 JavaScript：找 PDF 候选（它的 `find` 只报几个属性，读不到 meta 的 content）、页面内带 cookie 的请求、pdf.js 阅读器里的文档。点开链接后是不是下载，改看文档标识（`performance.timeOrigin`）变没变，不再往页面里写标记：每次导航它都会变，同一地址重新打开也算新文档（只比地址的话，停下后重跑会把重新打开的同一页当成下载，白等一分钟）；下载不改变它。
  - 直接打开 PDF 地址、Chrome 当下载处理时，标签页留在原处：现在按下载等文件落地，不再马上判"页上没有 PDF"。只在标签页没跳转时才等满 60 秒（实测 PMC 要 45–60 秒），跳到别的页面时最多等 20 秒，免得每个点不通的链接都白等一分钟。opencli 的 `wait download` 只在下载完成时返回，分不出"还没开始"和"不会下载"，所以终点仍是认领。
  - 浏览器 subagent 一次只做一个 try：它跟着论文一路点到文件为止，不半路带回地址；门禁过了以后，接着叫同一个 subagent 继续。
  - OpenCLI 升到 2.x：session 改用 `--session`，结果统一是 `{ok, data}`。browser.py、测试里的假 opencli、SKILL.md 和 publishers.md 里的命令都跟着改了。`wait download` 的说明按 2.0.1 的源码重写。
