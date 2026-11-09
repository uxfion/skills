# paper-fetch 改成 Unix 约定

- 日期：2026-11-05，草稿第二稿。来源：[Unix 约定 issue（已归档）](../issues/archive/20261104-skills-unix-conventions-fixed.md)（已定 7：`--version` 改 `--as`；已定 13：从 p2z 拷要用的代码，不另立共用层；「铺开到其余 skill 时」的 10 步）。约定只有一个出处：`docs/design-principles.md` §3 *The Unix/Linux philosophy*，这里只写 paper-fetch 自己的：短词、东西怎么指定、`-` 读什么。样板是已实现的 p2z（`p2z.py`、`p2zlib/cli.py`）。
- 状态：已冻结（2026-11-09）。用户于 2026-11-06 同意了 §3 补的几处（issue 第 14 条）和实施计划；实施及收尾已完成，实施时的更正记在本 spec。第一稿的三条待定主 agent 已定（2026-11-05，都按推荐）；四份 spec 共用的几条也是主 agent 定的（运行时检查的 fixture、退出码规则、每行带 `code`、跨 skill 改动谁来改、PATH 那一句、路径清单读 JSON 行、去掉的选项不另给提示）。这份 spec 没有待定。原先和 §3 字面对不上的三处（`-o` 指目录、只处理一样东西的命令退出 1 不打汇总、`-` 把上游的跳过和失败行原样转出），用户 2026-11-06 同意写进了 §3。
- 范围：一遍约定整理。流程、交接单、结果文件都不动；变的是怎么调用、选项、汇总放在哪、退出码、帮助。输出的字段只加不改：每行补 `code`（第 5 节），两种跳过行补 `path`（第 3 节）。另有两处小改：`downloads` 不再往 `fetch.jsonl` 记事件（第 2 节），`todo`、`answer` 的 `--slug` 修好（第 3 节）。
- 跨 skill 的改动分批落地：第一批 paper-fetch 和 vllm-serve，第二批 paddleocr 和 paper-read。paper-to-zotero 里调 paper-fetch 的每一行（文档和脚本帮助）、p2z `ready` 的改动都归这份 spec；p2z `SKILL.md` 的 PATH 那一句和 `import.md` 里解析的几行归 paddleocr，这里不碰。

## 1. 改完是什么样

每次调用开头单独一句（下面"改后"都省掉它）：`set -o pipefail; export PATH="<paper-fetch 目录>/scripts:$PATH";`。paper-fetch 不调别的 skill，所以这一句只列它自己；接到 `p2z.py` 的管道写在 p2z 的文档里，那边的 PATH 带着两个 skill。"现在"的写法都要先 `cd` 到 paper-fetch 目录。次数取自 [`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料)，全在本仓库，真项目 0 次；括号里是拆分前同一批命令记在 paper-to-zotero 名下的次数。

```
# identify，99 次。认一篇，带引用键
uv run scripts/pf.py identify 10.1109/CVPR.2016.90 --slug He:2016:ResNet -o <dir>
pf.py identify -o <dir>/ --slug He:2016:ResNet 10.1109/CVPR.2016.90
# 一份 .bib 的清单（p2z 的 import.md）：现在不写 ID 就去读标准输入，改后要写 -
p2z.py ids refs.bib | uv run ../paper-fetch/scripts/pf.py identify -o <imp>/fetch
p2z.py ids refs.bib | pf.py identify -o <imp>/fetch/ -
# 按标题在 Crossref 找；judge 定下的 DOI 一次认完（现在主 agent 一个个敲）
uv run scripts/pf.py identify --search "U-Net: Convolutional Networks for Biomedical Image Segmentation" --author Ronneberger
pf.py search U-Net: Convolutional Networks for Biomedical Image Segmentation --author Ronneberger
jq -c 'select(.id)' <dir>/scratch/judge/pin.*.jsonl | pf.py identify -o <dir>/ -
# 预印本的结果改成正式版
uv run scripts/pf.py identify --redraft 10.1007/978-3-319-24574-4_28 <dir>/results/ronneberger2015unet.json
pf.py redraft 10.1007/978-3-319-24574-4_28 <dir>/results/ronneberger2015unet.json

# fetch，87 次（196）。走一遍，以及 paper agent 把页面交回来
uv run scripts/pf.py fetch --pass 1 <dir>/results/*.json
pf.py fetch --pass 1 <dir>/results/*.json
uv run scripts/pf.py fetch --pass 2 --session pf-liu2022jbhi --start <url> --version accepted <dir>/results/liu2022jbhi.json
pf.py fetch --pass 2 --session pf-liu2022jbhi --start <url> --as accepted <dir>/results/liu2022jbhi.json

# claim，53 次（35）。后台监视进程；agent 自己下的文件；收尾时 Downloads 里剩下的（后一行在 p2z 的 import.md）
uv run scripts/pf.py claim --dir <dir> --watch
pf.py watch <dir>
uv run scripts/pf.py claim --dir <dir> --file ~/Downloads/x.pdf --slug liu2022jbhi
pf.py claim ~/Downloads/x.pdf <dir>/results/liu2022jbhi.json
uv run ../paper-fetch/scripts/pf.py claim --dir <imp>/fetch --sweep        # 再把列出的文件交给 p2z.py have
pf.py downloads <imp>/fetch | jq -r .source | p2z.py have -

# fulltext_links 18 次（30）；ready 14（p2z 的 ready 同一批改）；settle 12
uv run scripts/pf.py fulltext_links <dir>/results/*.json
pf.py locate <dir>/results/*.json
uv run scripts/pf.py ready --dir <dir>          # p2z：uv run scripts/p2z.py ready --dir <imp>
pf.py ready <dir>                               # p2z：p2z.py ready <imp>
uv run scripts/pf.py settle --dir <dir>
pf.py sync <dir>/results/*.json

# wait 11 次（12）；列命令 10；todo 9；answer 3
uv run scripts/pf.py wait <result> --session pf-<slug>
pf.py wait <result> --session pf-<slug>
uv run scripts/pf.py --help
pf.py -h
uv run scripts/pf.py todo --dir <dir> --slug liu2022jbhi
pf.py todo <dir> --slug liu2022jbhi
pf.py todo <dir> --kind label | jq -r .path               # 新能这样：派给 judge 的那批交接单
uv run scripts/pf.py answer <dir>/handoffs/liu2022jbhi.2.json accept --version accepted --reason "…" --by paper_agent
pf.py answer <dir>/handoffs/liu2022jbhi.2.json accept --as accepted --reason "…" --by paper_agent
```

p2z 的 `have -` 现在只读一行一个路径，所以中间要 `jq -r .source`；它哪天也认 paper-fetch 的行（取 `source`），这一步就省了，那是 p2z 的事。

## 2. 短词表

入口还是 `pf.py`，里面一张"短词 → 脚本"的表（p2z.py 的写法）；脚本文件不改名。两个脚本里各装着几个命令，拆成各自的短词，脚本收到短词当子命令（p2z 的 `read_library` 就是这样）。做事的用动词，列东西的用名词。"写在后面的"一栏里括号是 `-` 读的那一种。

| 短词 | 脚本 | 写在后面的（`-` 读） | 做什么；为什么用这个词 |
|---|---|---|---|
| `ready` | ready | [运行目录] | 查 poppler、OpenCLI、配置，建好运行目录 |
| `identify` | identify identify | 论文标识…（清单） | 认论文，每篇写一个结果文件 |
| `search` | identify search | 搜索词… | Crossref 按标题的前 5 条，什么都不写。原来是 `identify --search` |
| `redraft` | identify redraft | 目标 结果 | 结果改成正式版（DOI 或页面）的元数据。原来是 `identify --redraft`，那个选项带两个值 |
| `locate` | fulltext_links | 结果…（路径清单） | 查每篇的全文能在哪拿到，写进 `links/<slug>.json`。标准输出每篇一行状态和链接数，不是链接清单本身，所以用动词；`fulltext_links` 也不是一个词 |
| `watch` | claim watch | 运行目录 | 后台监视 Downloads。`-h` 开头一句：一直跑到被停掉，每次运行在后台开一个；和 `wait` 不是一回事 |
| `scan` | claim scan | 运行目录 | 同 `watch`，只看一遍。原来是 `claim --scan` |
| `fetch` | fetch | 结果…（路径清单） | 走一遍取全文的路线 |
| `claim` | claim claim | 文件… 结果（路径清单） | 文件对着论文查过，再归档。原来是 `claim --file --slug` |
| `check` | check_pdf | 结果…，或 文件… 结果（路径清单） | 只看查验的结论和证据，不写东西 |
| `wait` | wait | 结果 | 一篇论文在门页前等。`-h` 开头一句：只管这一篇，最多约十分钟；和 `watch` 不是一回事 |
| `todo` | todo | 运行目录 | 列还开着的交接单 |
| `answer` | answer | 交接单 回答 | 记下 agent 或用户的回答 |
| `sync` | settle | 结果…（路径清单） | 把 `fetch.jsonl` 里的事件对到结果的 `files` 和 `outcome` 上。原来叫 `settle`；paddleocr 里 settle 是 agent 对问题下结论，这里是机械地对齐，所以换词 |
| `downloads` | claim downloads | 运行目录 | 这次运行留在 Downloads 里的文件，各带 md5 和大小，只读。原来是 `claim --sweep`，它每个文件往 `fetch.jsonl` 记一条 `left`/`sweep` 事件；没有人读这些事件（对齐只读带 slug 的事件，监视 Downloads 时这种事件不带 `against`，什么都不改；p2z 只读结果），反倒会被跟着 `fetch.jsonl` 的 `tail -F` 当成新的 `left`。所以不再记，成了纯列东西，用名词 |

去掉的命令和顶替的：`pf.py fulltext_links` → `locate`；`pf.py check_pdf` → `check`；`pf.py settle` → `sync`；`identify --search` → `search`；`identify --redraft` → `redraft`；`claim --file F --slug S` → `claim F <结果>`；`claim --scan`、`--watch`、`--sweep` → `scan`、`watch`、`downloads`；只敲 `pf.py`（现在列出命令、退出 0）→ `pf.py -h`，只敲 `pf.py` 退出 2 并列出短词。

## 3. 东西怎么指定

- **结果**：结果文件的路径 `<dir>/results/<slug>.json`。运行目录从路径推出来（`fetch` 现在就这样），所以只给结果的命令不再要 `--dir`。几篇用 glob：`<dir>/results/*.json`；`settle --dir` 去掉，`sync` 也用 glob，和 `fetch`、`locate` 一个写法。
- **运行目录**：`ready`、`watch`、`scan`、`downloads`、`todo` 处理的就是它，写在后面。`ready` 不写时照旧是 `${TMPDIR:-/tmp}/paper-fetch`；其余四个必须写。
- **交接单**：它的文件路径，就是 `todo` 每行打出的 `path`。现在"id 加 `--dir`"那种写法去掉：文档里一次都没用过，id 形如 `he2020mask.1`，按 §3 认路径的规则说不清算不算路径。
- **一个结果加别的东西**（`claim`、`check`、`redraft`）：以 `.json` 结尾的那个是结果，另一种是要归档或要查的文件（PDF、HTML 快照），或 `redraft` 的目标（DOI、论文页网址），先后不限，写反了照样对。只能有一个结果，没有或有两个都是用法错误。`claim` 至少一个文件；`check` 只写结果时查各结果自己的文件，写了文件时只能有一个结果（现在 `--file` 也是这样）。`claim` 的结果必须写在命令行上，它的 `-` 只读要归档的文件；`check` 的 `-` 读结果。`redraft` 的 `--html 文件` 留作选项（第 9 节）。
- **论文标识**（`identify`）：DOI、doi.org 链接、arXiv 号或链接、论文页面网址。这里写的永远不会是文件，所以含 `/` 也照标识读（DOI 本来就有 `/`）。
- **`identify` 的 `-` 读清单**：一行一篇，标识后面可以跟一个 TAB 和引用键（`p2z.py ids` 打出的就是这样）；`title:…` 行照旧答 `needs_pinning`；空行和 `#` 开头的行跳过（现在就是）。一行也可以是 paper-fetch 自己的 JSON 行，取 `id`：`identify` 自己的行（重认失败的那几篇）、judge 的 `pin.<n>.jsonl`（格式改成带 `id`，第 6 节）、browser agent 写的 `<i>.browser.json`（已经带 `id`）。没有 `id` 的 JSON 行照下面「上游报失败的行」那条：报跳过或失败的原样转出，别的让整个命令退出 2（`invalid_list`），什么都不做：`"id": null` 先用 `jq -c 'select(.id)'` 筛掉；`search` 的行有意读不进来，候选要先对过标题和第一作者，提示写 "Confirm a candidate (title, first author), then `pf.py identify <doi>`"。
- **路径清单**（`fetch`、`locate`、`sync`、`check`、`claim` 的 `-`）：一行一个路径，或 paper-fetch 自己的 JSON 行，取标出这个命令所要文件的那个字段，各命令的 `-h` 写明：结果取 `path`；`claim` 要归档的文件取 `source`（`downloads` 和 `claim` 的行在这里放文件的完整路径）。`identify`、`redraft` 的行只要说的是一个结果就带 `path`：现在两种 skipped 行没有（`identify` 的 `duplicate`、`redraft` 的 `same_doi`），补上。同一个路径来两次，只算一次。
- **上游报失败的行**（`-` 读的所有清单）：一行 JSON 缺这个命令要的字段，而它的 `code` 既不是 ok 也不是 skipped，就是上游没做成的那一样：原样转到标准输出，算没做完（退出 1，汇总里算 failed），其余照做。比如 `identify` 认不出的那几行没有 `path`，接 `fetch -` 时原样过去。缺字段而 `code` 是 skipped 的行也原样转出，算跳过；缺字段、`code` 是 ok 或没有 `code` 的行，照旧 `invalid_list`，退出 2：`search` 的行带 `code: ok`、没有 `id`，喂给 `identify -` 正好落在这里；judge 的 `"id": null` 不带 `code`，也是。这是原则 §3 的规矩（用户 2026-11-06 同意）。
- **`--slug`**（`identify`、`todo`、`answer`）：都指一篇论文的结果。`identify` 把引用键换成文件安全的写法当 slug（`identify.py:708` 的 `safe_slug`：`He:2016:ResNet` → `He_2016_ResNet`），`todo`、`answer` 现在拿原样去比，`todo <dir> --slug He:2016:ResNet` 什么都找不到、退出 0，像是做完了。改成三处都先过 `safe_slug`（挪进 `pflib`）。
- **`search`**：几个词合成一个查询，引号可有可无。
- 写了 `-` 而清单是空的：零件事，退出 0。后面该写东西的命令什么都没写：用法错误，退出 2（现在 `identify` 不写 ID 会去读标准输入，在 agent 的终端里可能一直挂着；结果类命令现在报 `no_results` 退出 1）。
- "一个东西命中好几样"在 paper-fetch 用不上：路径都是确切的。"像不像路径"也用不上：每个位置要么永远是文件，要么永远不是。

## 4. 选项

字母只用 §3 表里的：`-h`、`-n`、`-o`。每个选项只带一个值。"粗数"是按 [`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 同一批会话记录数的 paper-fetch 调用里各选项出现的次数（含开发时的旧写法，只看多少）；issue 记的全系统总数：`--dir` 33、`--file` 20、`--out` 22、`--version` 4、`--dry-run` 14、`-o` 93。

| 命令 | 现在 | 改后 | 粗数 | 说明 |
|---|---|---|---|---|
| identify | `-o, --out DIR` | `-o, --output DIR/` | 34 | 输出是一目录结果文件；不写照旧 `${TMPDIR:-/tmp}/paper-fetch`，`-h` 写明（§3：产物是几个文件的命令） |
| identify | `--slug KEY` | 不变，按 `safe_slug` 用（第 3 节） | 3 | 指这篇论文的结果，和 `todo`、`answer` 的 `--slug` 一个意思 |
| identify | `--wanted V` | 不变 | 3 | |
| identify | `--search TITLE` | 短词 `search`，词写在后面 | 17 | 搜索词是写在后面的东西 |
| identify | `--author NAME` | `search` 的 `--author NAME` | 15 | |
| identify | `--redraft TARGET RESULT` | 短词 `redraft` | 16 | 一个选项带了两个值 |
| identify | `--html FILE` | `redraft` 的 `--html FILE` | 2 | |
| fulltext_links | `--dry-run` | `locate` 的 `-n, --dry-run` | 0 | |
| fetch | `--pass N`、`--route R`、`--start URL`、`--session NAME`、`--window W` | 不变 | 56、16、19、17、0 | `--start` 是一个候选地址，不是要处理的东西 |
| fetch | `--version V` | `--as V` | 4 | issue 已定 7 |
| claim | `--file F` | 写在后面 | 18 | issue 已定 5 |
| claim | `--slug S`、`--dir DIR` | 去掉：结果的路径写在后面 | 23、61 | |
| claim | `--scan`、`--watch`、`--sweep` | 短词 `scan`、`watch`、`downloads` | 3、14、17 | 四种跑法，各是一个命令 |
| claim | `--version V` | `--as V` | 1 | |
| claim | `--downloads DIR` | 去掉 | 0 | `ready` 把 Downloads 记进 `run.json`，后面都读那里；要换文件夹就 `ready <dir> --downloads DIR` 再跑一次。留着还会出现 `pf.py downloads <dir> --downloads …` |
| check_pdf | `--file F` | `check` 写在后面 | 0 | 第 3 节 |
| ready | `--dir DIR` | 写在后面 | 18 | p2z 的 `ready` 同一批改成可选的写在后面 |
| ready | `--downloads DIR` | 不变 | 0 | |
| settle | `--dir DIR` | 去掉，`sync` 用 glob | 20 | |
| todo | `--dir DIR` | 写在后面 | 62 | |
| todo | `--slug S`、`--kind K` | 不变，`--slug` 按 `safe_slug` | 18、4 | 筛选 |
| answer | `--dir DIR` | 去掉，交接单只认文件 | 0 | |
| answer | `--version V` | `--as V` | 0 | |
| answer | `--slug S` | 不变，按 `safe_slug` | 3 | |
| answer | `--reason`、`--label`、`--why`、`--by` | 不变 | 32、33、33、18 | `--reason`、`--by` 和 p2z `answer` 同义 |
| wait | `--until`、`--timeout`、`--file-only`、`--session` | 不变 | 0、0、2、1 | `--timeout` 和 p2z `ready --timeout` 同义（等几秒） |

- 选项和写在后面的东西可以交错写，长选项可以写唯一的前缀（`parse_intermixed_args`，照 p2z）；所以 `--out` 照样是 `--output`。
- 去掉的选项敲了就是普通的用法错误，提示照 p2z 写 `See <prog> -h.`，不另列旧名字。说参数长什么样的提示留着（比如 `claim` 没有结果时："name the result: <dir>/results/<slug>.json"）。

## 5. 输出和退出码

**退出码一条规矩**（样板 spec 第 9 节和 p2z 的代码）：退出 1 是命令处理的那样东西有问题（不存在、不是那种东西），写在它自己那一行，标准输出（处理几样东西的命令再在标准错误打汇总，只处理一样的不打）。退出 2 是调用本身或它要靠的东西有问题：用法错误、选项的值不对、服务不应答、锁、读不了的清单或说明文件；标准错误最后一行 `{code, hint}`。用到 paper-fetch：

- `claim` 的文件不存在：`{file, code: file_not_found}` 一行，退出 1；结果不存在或不是结果：结果那一行，退出 1，文件都不动。`redraft`、`check`、`fetch`、`locate`、`sync`、`wait` 的结果同样。
- 写反的 `redraft`：照 `.json` 认，照样做。没有 `.json`、两个 `.json`：用法错误。`--html` 的文件不存在：它是 `redraft` 要靠的材料，不是要处理的那篇，退出 2（`file_not_found`），和现在一样是 2。
- `todo`、`watch`、`scan`、`downloads` 的目录不是运行目录（没有 `results/`）或没经 `ready`（没有 `.started`）：`{dir, code: no_work_dir | no_started}` 一行，退出 1（现在 `claim` 那几种跑法是 2）。没有 Downloads 文件夹、没有 pdftotext、没有 OpenCLI 是要靠的东西没有：2。
- `answer` 的交接单不存在：`no_such_handoff` 一行，退出 1，照旧。

**共同的**（拷 p2z 的 `cli.py`，`pflib/cli.py` 跟着改）：

- 一行一个 JSON 照旧；逐条处理的命令边做边打（现在 `identify`、`locate`、`sync`、`check` 攒到最后才一起打）。
- 做事的命令每行带 `code`。缺的几种补上，只补在打出来的那一行，`fetch.jsonl` 里的事件不动（对齐结果读的是它）：`fetch` 的尝试行 `code` 取它的 `result`（ok、held、wrong_file、error），交接单的通告行 `code: handoff`；`answer` 打出的事件（answer、label 和它做的 accept、try）补 `code`，有 `result` 的取它，没有的是 `ok`；`claim`、`scan`、`watch` 的行查过文件的已经带 `code`（查验的结论），没查的 left 行补 `code: left`。`todo`、`downloads`、`search`、`check` 是列东西或只读的，不补；`search`、`check` 本来就带 `code`。
- 标准输出末尾的 `{"summary"}` 去掉。处理几样东西的命令没全做完（退出 1）时，标准错误最后一行是 `{"summary": {…}}`，字段照旧；全做完（退出 0）时标准错误为空。
- 整个命令做不下去（退出 2）：处理几样东西的命令，已做的照旧留在标准输出，没做的每样一行 `code: not_run`；只处理一样的（`redraft`、`wait`、`answer`）标准输出为空。现在的 "stopped early: …" 一行和汇总里的 `stopped` 去掉。用法错误：用法行之后最后一行 `{code: usage, detail, hint}`。
- 下游关掉管道（`| head`）后不再打印、不报错，命令照常做完，退出码照常。最要紧的是 `fetch`（一遍几分钟，写结果）和后台的 `watch`。
- 标准错误里的例行日志去掉：`pflib/web.py:272` 每个请求一行 `GET … -> 状态`。留下影响结果的警告：某个站回 429、多久以内不再问它（`web.py:153`、`161`），节奏文件读不了（`:189`），没有文件锁（`:119`），pdftotext 或 HTML 解析失败（`pflib/verify.py:198`、`201`、`291`）。几分钟的命令的进度，就是标准输出里边做边打的行。
- 帮助是 man 页：用法行用敲的名字（`pf.py claim`；入口设 `PF_PROG` 告诉脚本，照 p2z 的 `P2Z_PROG`）、做什么、选项、`-` 读什么（路径清单写明取哪个字段）、退出码、一两个例子；不连网、不读配置也能打。例子里没有 `uv run`、脚本文件名、`2>/dev/null`。
- 脚本开头一律 `#!/usr/bin/env -S uv run --quiet --script`（现在 11 个都没有 `--quiet`）。

**各命令不同的地方**

| 命令 | 0 | 1 | 2 | 和现在不同的 |
|---|---|---|---|---|
| identify | 每行 ok 或 skipped | 有别的（`needs_pinning`、空壳、`slug_taken`…）；汇总 | `doi_org_unreachable`、`source_blocked`（带 `until`）、`invalid_list` | 汇总挪走；停下时那一篇和后面的都是 `not_run` |
| search | 有候选 | 一条也没有（学 `grep`），标准错误空 | `crossref_unreachable`、`source_blocked` | 汇总里的 `query` 去掉；现在搜不到是 0。真 Crossref 上量过，没意义的标题搜出 0 条，这条路是真的（第 7 节） |
| redraft | ok 或 skipped | `not_published`、结果不存在等，行在标准输出 | 同 identify；`--html` 的文件不存在 | skipped 行补 `path` |
| locate | 都 ok 或 done | `no_identifier`、`no_answer`；汇总 | `config_unreadable` | 汇总里的 `dry_run` 随汇总去掉 |
| fetch | 这一遍没有开着的交接单 | 有开着的、浏览器坏了、有文件不是结果；汇总按类数交接单 | 没有 OpenCLI、两个目录的结果、没有 pdftotext：每个结果 `not_run` | 汇总改到标准错误；`--start` 照旧不打汇总 |
| claim | 都归档了 | 有拒掉的、留给 agent 看的、文件不存在；汇总 | 没有 pdftotext | 可以一次给几个文件 |
| scan、watch | 照常 | 目录不对（见上） | 没有 Downloads、没有 pdftotext | 目录不对现在是 2 |
| downloads | 照常（一个都没有也是 0，学 `ls`） | 目录不对 | 没有 Downloads | 汇总 `{left}` 去掉，数用 `wc -l`；不再往 `fetch.jsonl` 记事件，每行的字段照旧 |
| check | 每个文件都通过 | 有没通过的；汇总 | 没有 pdftotext | |
| wait | arrived、passed | timeout，行在标准输出 | | |
| todo | 没有开着的 | 有开着的：汇总 `{open, kinds, papers}`；目录不对 | | 流程靠它的退出码（"todo 退出 0"），照旧 |
| answer | 记下了 | 拒了，行在标准输出 | 用法错误 | |
| sync | 都对齐了 | 有文件不是结果；汇总 | | |
| ready | ok | 没准备好：`dir_unwritable`，以及 `no_pdftotext`（现在是 2） | `config_unreadable` | `no_pdftotext` 改 1：`ready` 查完了，结论是"还不能跑"，和 p2z `ready` 的 `no_key` 一类；`check`、`claim`、`fetch` 没有 pdftotext 照旧是 2 |

`fetch` 的标准输出照旧混着几种行：每次尝试、交接单的通告、跳过、`not_prepared`、`no_discovery`、`browser_down`，都是这一遍的记录。

## 6. 要跟着改的

**paper-fetch 的代码**

- `scripts/pf.py`：照 `p2z.py` 改成短词表（去掉 `prepare`、`save` 那套），开头注明拷自 p2z 的哪次提交（不再是 `95cea41`）；`-h` 列短词和退出码；未知短词、只敲 `pf.py`：退出 2。
- `scripts/pflib/cli.py`：从 `p2zlib/cli.py` 拷 `write`/`emit`（防断管）、边做边打的 `Lines` 和 `finish`、`summarize`、`run`（退出 2 写标准错误）、`Parser`（用法错误的 JSON）、`prog`/`parser(doc, sub)`/`parse`（交错写）/`subcommand`、`output`、`stdin_lines`、`paths`（加上按字段读 JSON 行、上游报失败的行原样转出、重复的只算一次）、`document`；自己写 `identify` 的清单读法，和"`.json` 是结果"的分法。`split()` 没人用，删。`main_results`/`each_result` 不写结果时改成用法错误。
- `safe_slug` 从 `identify.py:708` 挪进 `pflib`，`todo.py`、`answer.py`（经 `run.answer`）的 `--slug` 先过它。
- `identify.py`、`claim.py` 拆成子命令（`identify`/`search`/`redraft`，`claim`/`scan`/`watch`/`downloads`），其余脚本按第 4 节改选项、按第 5 节补 `code`；`identify` 的 `duplicate` 行、`redraft` 的 `same_doi` 行补 `path`；`claim.py:66`–`71` 的 sweep 不再 `work.append`。提示和帮助里的脚本文件名、`uv run scripts/`、旧选项、`settle`/`fulltext_links` 换成新写法：按约定检查的扫描（或照它的写法先 grep 一遍）逐个改，不按清单改。审阅扫出脚本文件名约 44 处，`uv run scripts/` 20 处；容易漏的例子：`pflib/run.py:4`、`19`、`26`、`55`、`69`、`619`、`759`、`870`、`894`、`947`，`claim.py:59`（"ready.py records…; or pass --downloads DIR"）、`99`，`identify.py:462`–`463`、`466`–`467`（"identify.py --redraft <url> <result> --html"），`pflib/verify.py:116`–`120`，`pflib/cli.py:57`。`web.py:272` 的请求日志删掉。11 个脚本开头加 `--quiet`。
- 不改的：结果文件里标签的 `by: "settle"`（对齐时给的默认标签，p2z 的 `titles_from_labels.py:57` 按它判断）、代码里的 `run.settle`、p2z 的 `unsettled` 代码，都是数据或内部名字，不是命令。

**paper-fetch 的文档**（逐行换成第 1、2 节的写法；文档要变短：选项的细节挪进 `-h`）

- `SKILL.md`：8（`cd`、`uv run` 那句改成 *Calling* 一段：PATH 那一句和为什么单独成句、`pf.py -h`、标准错误要留着）、42、45、50（`search … > <dir>/scratch/search/<i>.jsonl`；"exit 1: none found"）、51、52、61、62、65、73（`pf.py settle` → `pf.py sync`）、80、81、84、89、93（pin 文件带 `id`，`jq -c 'select(.id)' … \| pf.py identify -o <dir>/ -`）、94、95、102–104 和 119–120 和 131–133（三份派发模板的 "Run its commands from <paper-fetch's directory>" 换成填好绝对路径的 "Start every shell call with: `set -o pipefail; export PATH="<paper-fetch's directory>/scripts:$PATH";`"，照 p2z `SKILL.md:45`）、107、108（`todo --slug` → `todo <dir> --slug`）、124、137、150、151、157（"its summary counts them by kind" → 标准错误最后一行）、158、161、163、172、178、179、184、189、192。
- `references/`：`attachment-titles.md:41`；`batch.md:9`、16、17、20、22、30、34、38；`gate.md:20`、24；`identify.md:6`、7、11、12、14；`install.md:3`、7、31、40、41、44；`judge.md:3`（`cd` 和 `uv run` 那句换成"每次调用开头用派发给的那一句"）、11、13、21（"then a summary line with the query" 删；文件是空的就是 Crossref 一条都没给，`search` 退出 1）、23 和 25（pin 的一行改成 `{"i", "id", "why"}`，`id` 是定下的 DOI 或 null）；`publishers.md:24`、70、73、83、139；`web-agent.md:3`（同 judge.md:3）、9、12、18、20。

**paper-to-zotero 里调 paper-fetch 的**（paper-read、paddleocr、vllm-serve、README、AGENTS.md 里没有；p2z `SKILL.md:10` 只改 `pf.py <command>` 这几个字，同一行的 PATH 那一句归 paddleocr）

| 位置 | 现在 | 改后 |
|---|---|---|
| `SKILL.md:10` | paper-fetch's `pf.py <command> …` | `pf.py <word> …` |
| `references/import.md:9` | `pf.py <command>` | `pf.py <word>` |
| `import.md:12`、`13` | `p2z.py ready --dir <imp>`、`pf.py ready --dir <imp>/fetch` | `p2z.py ready <imp>`、`pf.py ready <imp>/fetch` |
| `import.md:14` | `pf.py claim --dir <imp>/fetch --watch` | `pf.py watch <imp>/fetch` |
| `import.md:30` | `pf.py identify <…> [--slug <citation key>] -o <imp>/fetch` | `… -o <imp>/fetch/` |
| `import.md:31` | `p2z.py ids refs.bib \| pf.py identify -o <imp>/fetch` | `… \| pf.py identify -o <imp>/fetch/ -` |
| `import.md:40`、`59` | `pf.py identify --redraft …`、`identify --redraft` | `pf.py redraft …` |
| `import.md:80`、`83` | `fulltext_links`、`pf.py fulltext_links …` | `locate`、`pf.py locate …` |
| `import.md:89`、`102` | `pf.py settle --dir <imp>/fetch` | `pf.py sync <imp>/fetch/results/*.json` |
| `import.md:129` | `pf.py claim --dir <imp>/fetch --sweep` … `p2z.py have <those files>` | `pf.py downloads <imp>/fetch \| jq -r .source \| p2z.py have -` |
| `references/batch.md:11` | `id<TAB>citation key` lines on `identify`'s stdin | 这样的行接管道给 `pf.py identify … -` |
| `references/organize.md:11` | `pf.py identify --search "<title>" --author <surname> > …` | `pf.py search <title> --author <surname> > …` |
| `organize.md:12` | `printf … \| pf.py identify -o <scratch>/tidy/fetch` | `… -o <scratch>/tidy/fetch/ -` |
| `organize.md:44` | `pf.py identify --search` | `pf.py search` |
| `organize.md:51` | `pf.py claim --dir <scratch>/paper-fetch/label --file <…> --slug <slug>` | `pf.py claim <…> <scratch>/paper-fetch/label/results/<slug>.json` |
| `scripts/attach_file.py:37`、`38`、`94`、`105` | `pf.py settle`、"settle the result again" | `pf.py sync` |
| `scripts/recognize.py:46`、`91` | "settle the result again" | "sync the result again (pf.py sync)" |
| `scripts/titles_from_labels.py:110` | "settle it again" | "sync it again (pf.py sync)" |
| `scripts/draft_item.py:21`、`scripts/p2z.py:77` | `identify --redraft` | `pf.py redraft` |
| `scripts/find_in_library.py:9` | paper-fetch's `claim --sweep` lists them | `pf.py downloads` lists them |
| `scripts/lint_items.py:44` | paper-fetch's `identify --search` | `pf.py search` |
| `scripts/read_bib.py:18` | `… \| pf.py identify -o <scratch>/paper-to-zotero/fetch` | `… -o <scratch>/paper-to-zotero/fetch/ -` |
| `tests/test_attach_file.py:48` | paper-fetch's settle leaves it | `pf.py sync` leaves it |

**p2z 的 `ready`**（同一批，因为 import.md 里两行并排）：目录改成可选的写在后面，`p2z.py ready [目录]`。`scripts/ready.py:6`、`10`、`26`、`124`（"Pass a writable directory with --dir" → 写在后面）、`146`；`tests/test_ready.py:53`、`58`、`93`；`tests/test_p2z.py:70`；`tests/conventions_fixture.py` 的 `REMOVED` 加 `"--dir": ()`；`references/import.md:12`。

不动：`import.md:63`、`84`，`fields_from_results.py:8`（写法没变）；`docs/specs/` 里冻结的 spec；开着的 issue 里的旧写法，用到时再改（p2z 那次的规矩）。

## 7. 约定检查和验收

**`paper-fetch/tests/conventions_fixture.py`**（`tests/check_conventions.py` 导入它；照 p2z 那份写，接口见检查的说明）

- `HELP_ENV`：`PAPER_FETCH_CONFIG=/nonexistent/config.json`，`DOI_BASE_URL`、`CROSSREF_BASE_URL`、`ARXIV_API_URL`、`OPENALEX_BASE_URL`、`EUROPEPMC_BASE_URL` 都指到 `http://127.0.0.1:9`（`-h` 不该连它们）。
- `REMOVED`：`--dir`、`--file`、`--version`、`--out`、`--scan`、`--watch`、`--sweep`、`--redraft`、`--search` 一律不许，`--downloads` 只许在 `ready`。`--slug` 不进：还在 `identify`、`todo`、`answer`。放 `--redraft` 前先 grep paper-fetch 的字符串里有没有 `p2z.py draft --redraft`（p2z 的 `draft` 留着它），有就换写法。没有 `--collection`，不写 `SELECTS`。
- `env(tmp)`：上下文管理器。起一个 `FakeWeb`（`tests/fake_web.py`，doi.org、Crossref、arXiv、OpenAlex、Europe PMC），登记两篇 DOI；在 `tmp` 下做好 `reader`、`writer` 的结果（`helpers.result_file`）和 `reader` 能通过的 PDF（`helpers.fake_pdf`，第 1 页有整个标题，文字拉长）；`yield` 的环境：`FakeWeb` 的各服务地址，`tmp` 里的测试配置（`PAPER_FETCH_CONFIG`）和节奏文件（`PAPER_FETCH_PACE`），`PATH` 前面加 `helpers.poppler_stubs` 做的 pdftotext、pdfinfo 替身，`no_proxy`、`NO_PROXY` 都是 `127.0.0.1,localhost`；`finally` 里关掉 `FakeWeb`。
- `quiet`：`{"run": "pf.py identify -o <tmp>/q/ 10.1000/a.1 10.1000/b.2", "lines": 2}`。选它是因为汇总和每个请求的 `GET` 日志都出在它身上。节奏按逻辑上的主机算（`web.py:64`：doi.org 0.5 秒、Crossref 1.0 秒、OpenAlex 0.1 秒），两篇的 doi.org 和登记机构各两次、OpenAlex 和 Europe PMC 各一次，约两秒。
- `reader`：`{"run": "pf.py check <tmp>/r/results/*.json"}`，条数够让整个输出超过 64 KiB（检查自己量）。`check` 什么都不写，是纯读的命令，全通过时退出 0。
- `writer`：`{"run": "pf.py sync <tmp>/w/results/*.json", "written": 每个结果都有 outcome}`，400 个结果，slug 拉长，让 `head -1` 关掉管道时 `sync` 还有得写。
- `no_service`：每次现找一个端口、绑上再放开，`{"run": "DOI_BASE_URL=http://127.0.0.1:<port> pf.py identify -o <tmp>/n/ 10.1000/a.1", "code": "doi_org_unreachable"}`（标准输出一行 `not_run`）。
- `fetch` 要 Chrome，不进运行时检查。去掉防断管时 `reader`、`writer` 各自变红；留着 `GET` 日志或汇总时 `quiet` 变红。

**`check_conventions.py` 那边**：主 agent 落地时把 `paper-fetch` 从 `NOT_YET` 拿掉。p2z 的 `REMOVED` 加 `"--dir": ()` 在 p2z 自己的 fixture 里，和 `ready` 一起改（第 6 节）。

**要跟着改的测试**（paper-fetch 的 `tests/`）

- `helpers.py`：`SHEBANG` 加 `--quiet`；`call()` 给拆了子命令的脚本带上短词；`smoke()` 经入口跑。
- `test_identify.py`：读标准输入的几处要写 `-`；`--search`、`--redraft` 改成 `search`、`redraft`；`-o`；汇总的 `stopped`（:257）、`query`（:516）改读标准错误；加：`-` 读空清单退出 0、什么都不写退出 2、JSON 行取 `id`、`search` 的行退出 2、`redraft` 写反照样做、`duplicate` 行带 `path`、认不出的行接 `fetch -` 原样转出并退出 1。
- `test_claim.py`：`--file`/`--slug`/`--dir` 改成写在后面；`--scan`、`--watch`、`--sweep` 改成短词；`--downloads` 那条（:151）删；"`--file` 不能和 `--scan` 一起"那几条（:79、:80）换成"没有结果、两个结果"的用法错误；`--sweep` 的汇总（:144）删，再断言 `downloads` 之后 `fetch.jsonl` 没变；目录不对（:153）改成退出 1 的那一行；加：文件不存在是那一行退出 1。
- `test_answer.py`：`claim`、`todo` 的写法；"id 加 `--dir`"（:143、:161）删；`todo` 的汇总（:177）读标准错误；加：`todo`、`answer` 的 `--slug` 写原样引用键也认得。
- `test_check_pdf.py`：`--file`（:36、:40）改成写在后面。`test_contract.py`：`claim`、`answer --as`、`settle` 改 `sync` 加 glob。`test_fetch.py`：`--version` → `--as`，汇总（:225、:298、:378）读标准错误，尝试行和通告行带 `code`。`test_fulltext_links.py`：`-n`，`dry_run` 汇总（:142）删。`test_ready.py`：目录写在后面，`no_pdftotext` 退出 1。`test_settle.py`：`--dir` 去掉。`test_web.py:120`：`GET` 日志那条删，"日志里没有密钥"那条（:121）改成标准错误为空。
- paper-read 的测试不调 paper-fetch。p2z 的测试只有 `ready` 那几处（第 6 节）；p2z 的 `test_contract` 读 paper-fetch 的结果样例，格式没变。

**验收**

- paper-fetch、p2z 的测试全过；约定检查全过（paper-fetch 不在 `NOT_YET`）。
- 在真服务上跑一遍小的（结果写在 scratch，不碰 Zotero）：一篇开放获取的论文，`ready`、`watch`、`identify`、`locate`、`fetch --pass 1`、`todo`、`sync`、`downloads`，全按新写法；做完的命令标准错误为空。
- 文档变短：`SKILL.md` 加 `references/` 现在 635 行，改完更短。脚本（现在 5,379 行，含 `pflib/`）多出的只能是 man 页的帮助，和只写一处、各命令共用的机制（拷来的 `cli.py`）。
- paper-fetch 的文档里没有 `cd`、`uv run`（papers-cool-search 那句是别的 skill 的，不算）、`2>/dev/null`。

**动手前先在真服务上量的**

1. 真跑一小遍（两三篇开放获取的）时 `pf.py fetch --pass 1 … | head -1`：每条路线照样走完，结果照样对齐，退出码不变。`fetch` 是写东西最多、跑得最久的命令。（没做）
2. 真 Crossref 上 `search` 一串没意义的词会不会一条都不给：主 agent 2026-11-05 量过，0 条。所以"搜不到退出 1"是真会发生的，假服务（只给有共同词的）和真的一样。（已做）
3. `p2z.py ids <一份带 title: 条目的真 .bib> | pf.py identify -o <dir>/ -`，带 `pipefail`：退出 1、标准错误最后一行是汇总、标准输出的行和现在一样；再拿一份没有条目的 .bib：`ids` 退出 1，`identify -` 读到空清单退出 0，整行是 1。（没做）

## 8. 开着的 issue

都是行为，不是调用方式，这次都不碰：

- `20261031-paper-fetch-pmc-pdf-first-try-refused`：PMC 第一次给的不是 PDF，是网站行为，等下次真跑留证据。
- `20261101-paper-fetch-metadata-from-zotero`：补期刊缩写、会议名、arXiv 完整日期等字段，是元数据的内容。
- `20261105-paper-fetch-arxiv-abstract-latex`：摘要里的 LaTeX 转义怎么规整，是 `identify` 的内容。
- `20261105-paper-fetch-arxiv-date-year-only`：用 arXiv 的 `published` 补日期，是 `identify` 的内容。
- [20261105-paper-fetch-miccai-pages](../issues/archive/20261105-paper-fetch-miccai-pages-fixed.md)：没有 `citation_*` 的页面、站点自己的开放获取版、PDF 地址的论文标记，是认论文和取全文的做法。这次 `search`、`redraft` 改了名，它第 1 条里"按标题搜 DOI 再 redraft"写进 SKILL.md 时用新名字，但没解决它。
- `20261105-paper-fetch-trial-import-web-notes`：学校登录这条路上的现象，等真跑核实；第 5 条（"不等的门"没有回答）是交接单的回答词，属于流程。

## 9. 偏离和理由

和 §3 或样板不一样的地方：

- **`claim`、`check`、`redraft` 按 `.json` 后缀分出结果**，不按先后，也不像 p2z `merge --into` 那样用选项点明。结果永远是 `results/<slug>.json`，要归档的永远是 PDF 或 HTML，目标永远是 DOI 或网址，所以后缀分得清；先后不限，写反了照样对，用不着为防写反另起选项。
- **`claim` 一次收几个文件，也收 `-`**：现在一次只收一个，这是扩展。按 §3，处理文件的命令后面可以写几个、`-` 读路径清单；"给手上已有的 PDF 打标签"本来就一篇几个文件，`downloads` 的行也能接过来。
- **`redraft --html 文件`、`fetch --start 网址` 留作选项**：它们是给要处理的那篇提供材料（存下的页面、一个候选地址），不是要处理的东西；p2z `update --patch 文件` 同理。
- **打出来的行补 `code`，`fetch.jsonl` 不补**：对齐结果读的是日志，日志不动最稳。`claim` 那几种行的 `code` 是查验的结论（`ok`、`doi_mismatch`…），做了什么在 `result`（claimed、refused、held、left），不是 p2z 那样 `code` 就是这一行的状态；改名要动日志和对齐的代码，超出这次的范围。
- **结果文件里标签的 `by: "settle"` 不随命令改名**：它是数据，p2z 按它判断；只改命令名和文档。
- **`todo` 列东西却在有内容时退出 1**：§3 的 1 是"有要处理的"，开着的交接单正是；流程的完成条件靠它（"todo 退出 0"），照旧。
- **`ready` 不写目录时有默认**：照旧 `${TMPDIR:-/tmp}/paper-fetch`，它不是非写不可的东西，空的 `$(…)` 也不会落到"整个库"上。
- **p2z 的 `ready` 一起改成写在后面**：样板 skill 里的改动，因为 import.md 里两行并排，一个 `--dir`、一个写在后面会让人混。

## 10. 实施时的改正（2026-11-06）

- `pflib/cli.py` 没拷 `summarize`、`finish`、`output`、`document`：paper-fetch 没有脚本用它们（§3 *General and simple*）。
- `todo` 只要 `results/` 在，不查 `.started`："给手上已有的 PDF 打标签"那条路（identify → claim → todo）不跑 `ready`。`scan`、`watch`、`downloads` 两样都查。
- `identify -o` 写什么都当目录，没有就建；产物总是目录，`-h` 写 `DIR/`。
- `ready` 用 `opencli -V` 问版本：约定检查不许 skill 的字符串里出现 `--version`，OpenCLI 认 `-V`（核过）。
- `fetch` 的汇总多一个 `failed?`：从上游原样转来的行要有地方计数。
- `tests/helpers.py` 去掉 `SHEBANG`，`smoke()` 经 `pf.py <词>` 跑。
- 行数：脚本 5,379 → 5,746（拷来的 `cli.py` 层 +114，man 页：claim +86、identify +59、fetch +32、pf.py +28、check +28）；文档 635 → 632 行，词数 15,593 → 15,423。
- 实测时看到另一个会话正用已装的旧版跑 `claim --dir … --watch`：重装新版后，这种写法就不认了。
