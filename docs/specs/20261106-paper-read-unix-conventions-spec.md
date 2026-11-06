# paper-read 对接 Unix 约定

- 日期：2026-11-05。来源：[docs/issues/20261104-skills-unix-conventions.md](../issues/20261104-skills-unix-conventions.md)。
- 状态：已定（2026-11-06）：用户同意了 §3 补的几处（issue 第 14 条）和实施计划；实施中，这期间可以改正。三轮审阅（忠于需求、技术、好不好用）和主 agent 的决定已改进来。
- 约定只有一个出处：`docs/design-principles.md` §3 *The Unix/Linux philosophy*。这份只写 paper-read 自己的：入口和短词、东西怎么指定、要跟着改的地方。样板是 p2z（`paper-to-zotero/scripts/p2z.py`、`p2zlib/cli.py`、`tests/conventions_fixture.py`）。
- 范围：一遍约定整理。流程、交接、输出的内容都不动，动的是怎么调用、选项、报错写在哪、退出码，和 §3 要求的提示。
- 落地：第二批，和 paddleocr 一起。paper-read 的文件全由这份 spec 改，调 paddleocr 的地方也是，用 paddleocr 已定的写法（入口 `ocr.py`）；paddleocr 不碰 paper-read 的文件。

## 1. 改完是什么样

用得最多的几种（`usage.md`，2026-11-04：`prepare_note` 47 次、`put_note` 44、`check_quotes` 24、`check_note` 22、`index_heading` 6，全在本仓库，真项目 0 次）。下面 `<名>` 是 `take` 起的文件名主干，`<引用键>.<PDF 的附件标题>`，如 `xiaoTCACE2026.Published-IEEE`。

改一条笔记的四步：

```
# 现在：每次先 cd 到 paper-read
cd <paper-read>
uv run scripts/prepare_note.py --cite xiaoTCACE2026 -o <scratch>
uv run scripts/check_note.py <scratch>/<名>.note.md --full
uv run scripts/check_quotes.py <scratch>/<名>.note.md --pdf <scratch>/<名>.pdf --package <scratch>/<名>
uv run scripts/put_note.py <scratch>/<名>.note.md

# 改后：开头那一句单独成句，当前目录留在项目里；列出 paper-read 自己，和它的文档里出现命令的 skill
set -o pipefail; export PATH="<paper-read>/scripts:<paper-read>/../paper-to-zotero/scripts:<paper-read>/../paddleocr/scripts:$PATH";
pr.py take xiaoTCACE2026 -o <scratch>/
pr.py check --full <scratch>/<名>.note.md
pr.py quotes <scratch>/<名>.note.md
pr.py put <scratch>/<名>.note.md
```

查一处（*Look it up*）、项目论文索引的标题行：

```
# 现在
uv run scripts/prepare_note.py --cite xiaoTCACE2026 -o <scratch> --bare
uv run scripts/index_heading.py --cite xiaoTCACE2026 heDeepResidualLearning2016
# 改后
pr.py take --bare xiaoTCACE2026 -o <scratch>/
pr.py heading xiaoTCACE2026 heDeepResidualLearning2016 | jq -r 'select(.code=="ok").heading'
p2z.py search T-CACE | pr.py heading -
```

还没有结构化包（`take` 答 `no_package`），以及 paper-read 文档里调别的 skill 的几处：

```
# 现在：SKILL.md 只说"用 paddleocr 解析，package put，再跑 prepare_note"，怎么接要 agent 自己拼
uv run ../paper-to-zotero/scripts/p2z.py package put <scratch>/<名>
uv run ../paddleocr/scripts/doc.py show <scratch>/<名>
# 改后（同一句 PATH）：no_package 那一行的 hint 就是前三步
pr.py take xiaoTCACE2026 -o <scratch>/ | ocr.py parse -o <scratch>/ -
p2z.py package put <scratch>/<名>
pr.py take xiaoTCACE2026 -o <scratch>/
ocr.py findings <scratch>/<名>
```

## 2. 短词表

入口 `scripts/pr.py`：paper-read 的首字母，照 `p2z.py`、`pf.py` 的取法，全系统不重名（POSIX 有个 `pr` 命令，但 PATH 上的名字是 `pr.py`，撞不上）。`pr.py -h` 列出短词，表外的词退出 2 并列出全部。入口里一张表 `WORDS = {短词: (脚本, 一句作用)}`，脚本文件不改名；入口经 `uv run --quiet --script` 执行脚本，执行前设 `PR_PROG=pr.py <短词>`，脚本的用法行用它（拷 p2z 的 `P2Z_PROG`）。

| 短词 | 脚本 | 做什么 | 写在后面的 | 为什么用这个词 |
|---|---|---|---|---|
| `take` | prepare_note | 把一篇论文的笔记、PDF、结构化包取进 scratch 目录（改笔记第 1 步） | 一篇论文（`-` 读清单，只能一篇） | 和 p2z 的 `note take`、`package take` 同一个词，也是 SKILL.md 第 1 步的名字 |
| `check` | check_note | 按 note-format 查笔记的问题树（第 3 步） | 一个笔记文件 | 和 p2z 的 `check`（按 schema 查草稿）同类 |
| `quotes` | check_quotes | 列出笔记里每条引文，各在 PDF 或包里找没找到（第 3 步） | 一个笔记文件 | 名词：它列出每条引文和它的状态，有一条没过就退出 1；换成 `verify`，和 `check` 分不出哪个查什么 |
| `put` | put_note | 给图表加链接、存回 Zotero（第 4 步） | 一个笔记文件 | 和 `note put` 同一个词，也是第 4 步的名字 |
| `heading` | index_heading | 每篇论文在项目论文索引里的标题行 | 论文…（`-` 读清单） | 名词：打出的是一行行标题；`index` 会读成"建索引" |

`sources.py` 不是命令，是三个脚本共用的模块：挪到 `scripts/prlib/sources.py`，和从 p2z 拷来的 `prlib/cli.py` 放在一起。约定检查要求 `scripts/` 下每个 `.py` 都有短词、带 uv 开头和可执行位。

## 3. 东西怎么指定

- **论文**（`take`、`heading`）：全 skill 一条规矩，照 p2z 认条目：引用键或条目 key 都行，由 `p2z.py items` 解析（2026-11-05 实测：写条目 key 和写引用键，`items` 打出同一行）。正好一条就用它，没有是 `not_found`，几条是 `ambiguous`（列出 `keys`），退出 1。笔记和索引里照旧写引用键。`heading -` 一定要认 key：p2z 打出的行用 `key` 指条目；`take` 跟着同一条，不另立一条只认引用键的（第 9 节）。
  - `take` 一次只取一篇（一次改动一个 scratch 目录）。它先 `p2z.py items <值>` 解析（今天放在最后取 `paper` 的那次调用挪到最前），之后 `pdf`、`package take`、`note take` 都交解析出的条目 key：条目 key 不会有歧义。笔记的 `parent:` 和输出里照旧是引用键。今天写条目 key 走不通，是因为 `prepare_note.py:125,132,174` 拿 p2z 的行去比用户敲的值；p2z 的行里 `citationKey`（`pdf`）、`cite`（`package take` 成功的行，`structured.py:176`）都是引用键，改成和解析出的引用键比。`note take` 的行不按 `key` 比（那里的 `key` 是笔记的），照旧按 code 挑（`:143`）。
  - `take -` 读清单，和 `heading` 一样：p2z 教的是 `p2z.py search … | p2z.py package take - -o D/`，agent 会照着敲 `… | pr.py take - -o D/`。清单里正好一篇就取它；几篇是 `{code: ambiguous, items: [每一行写的值], hint}`，退出 1，什么都不取；空清单什么都不做，退出 0。没写、或者写了两个值是用法错误，退出 2。
  - `heading` 写几篇都行；`-` 读**清单**：一行一个值，或者一行我们自己的 JSON（p2z 的 `search`、`items` 打出的那种），取 `key`，没有 `key` 取 `cite`（拷 p2z 的 `cli.names()`）。所以 `p2z.py search T-CACE | pr.py heading -` 中间不用挑字段。输出行的 `cite` 总是这篇的引用键，写的是 key 也一样。`-` 读到空清单什么都不做、不调 p2z，退出 0；后面什么都没写是用法错误，退出 2。
  - 上游报失败的行（`take -`、`heading -` 都是）：一行 JSON 的 `code` 不是 ok、skipped，又没有 `key`、`cite`，就原样转到标准输出，算没做（退出 1），不算进 `take` 的"正好一篇"；`code` 是 skipped 的也原样转出、算跳过，同样不算进；没有那两个字段、`code` 是 ok 或没有 `code` 的行照旧是 `invalid_list`，退出 2。这是原则 §3 的规矩（用户 2026-11-06 同意）。
- **笔记文件**（`check`、`quotes`、`put`）：只收文件，写在后面的都是路径，不当别的去查。不是文件（不存在、是目录）报 `file_not_found`，读不成 UTF-8 文字报 `file_unreadable`，照 p2z `note put`。三个都不读 `-`：它们都要笔记旁边的文件，标准输入没有"旁边"。
- **笔记旁边的东西**：笔记是 `<名>.note.md`，`take` 把其余几样放在它旁边（2026-11-05 实测）：`<名>.note.md.taken`（取出时的样子）、`<名>.pdf`、`<名>/`（结构化包）、`<名>.zotero.json`（PDF 附件的 key）。`check` 读 `.taken`，`quotes` 读 PDF 和包，`put` 读 PDF、包和 `.zotero.json`：三个命令一条规矩，都从笔记旁边找，不写在后面（第 9 节）。没有 `<名>/` 就是没有包：`quotes` 只对 PDF，`put` 照旧报 `no_package`。
- 既可能是文件、也可能是别的东西的写法：paper-read 没有（论文只是论文，笔记只是文件），§3 认路径的那条用不上。

## 4. 选项

次数：写这份 spec 时只读扫了 Claude Code 的会话记录（到 2026-11-05，含当天的全流程试用），`usage.md` 没有 paper-read 各选项的行。全在本仓库，真项目 0 次。

| 命令 | 现在 | 改后 | 次数 | 为什么 |
|---|---|---|---|---|
| take | `--cite K` | 写在后面：`take K` | 37 | 要处理的东西写在后面 |
| take | `-o, --out DIR` | `-o, --output DIR/`，必须给 | 37 | 字母表的长名是 `--output`；产物是一个目录的文件，不能写标准输出，照 §3 和 p2z `package take` |
| take | `--bare` | 照旧 | 8 | |
| take | `--title T` | 照旧 | 8 | 和 p2z `package take --title` 一个意思（PDF 的附件标题；p2z 自己的 `note take --title` 指笔记标题，是 p2z 那边的事） |
| check | `--full` | 照旧 | 29 | |
| check | `--taken FILE` | 去掉 | 0 | 只在测试里用过；`.taken` 总在笔记旁边，`take` 放的 |
| quotes | `--pdf PDF` | 去掉，读 `<名>.pdf` | 33 | 从笔记旁边找（第 3 节） |
| quotes | `--package DIR` | 去掉，读 `<名>/` | 35 | 同上 |
| heading | `--cite K…` | 写在后面：`heading K…` | 7 | 也是 paper-read 唯一一个带多个值的选项，§3 不许 |
| put | 没有选项 | | | |
| 全部 | `-h, --help` | 照旧，改成 man 页的样子 | | |

去掉的选项再被敲到，是普通的用法错误，提示照 p2z 写 `See pr.py <短词> -h.`。不加新选项：`put` 不加 `-n`，没有人要过空跑。选项和写在后面的东西可以交错写、长选项可写唯一的前缀、`--` 结束选项：拷 p2z 的 `parse_intermixed_args`。

## 5. 输出和退出码

一条规矩，和 pilot spec 第 9 节、p2z 的代码一样：

- **退出 1**：命令要处理的那样东西有问题（不在、不是该有的那种、格式旧、改它被拒），写在那样东西自己的那一行，在标准输出。处理好几样的命令（`heading`）再在标准错误最后打一行汇总；只处理一样的（`take`、`check`、`quotes`、`put`）不打。
- **退出 2**：调用本身或它要靠的东西有问题（用法、选项的值不对、服务不应、读不了的清单），标准错误最后一行 `{code, hint, …}`。用法错误是 `{code: usage, detail, hint}`（拷 p2z 的 `Parser`）；p2z 做不下去（Zotero 没开、本地 API 关着）时原样转出 p2z 那一行，加上 `step`（哪个 p2z 命令）；没装 pdftotext 也在这一类。
- **提示**，照 p2z：ok、skipped 和各命令的回答（`check` 的 `complete`、`open`，`quotes` 的 `pass`、`open`）以外，每个 code 都带一句 `hint`。SKILL.md 讲到这些 code 时指向 `hint`，不再复述。
- 标准输出照旧：`take`、`check`、`quotes`、`put` 各打一个 JSON 对象，`heading` 每篇一行；每一行都带 `code`（今天已经都带）。字段不变，下表列的除外。
- 下游关掉管道：拷 p2z 的 `write`、`emit`，不再打印、不报错，照常做完，退出码照实。

| 命令 | 现在 | 改后 |
|---|---|---|
| take | p2z 的任何失败都包成 `{code: failed, step, detail: [p2z 的行], stderr}`，在标准输出，退出 1；`no_package`、`two_notes` 没有 `hint`；成功的行里 scratch 里那个 PDF 链接叫 `pdf` | p2z 做不下去：退出 2，标准输出空，标准错误最后一行是 p2z 的 `{code, hint}` 加 `step`。p2z 对这篇论文的回答直接提上来：`code` 就是 p2z 的（`not_found`、`ambiguous`、`no_such_title`、`no_pdf`、`not_on_disk`），带 p2z 的 `hint` 和它别的字段（`keys`、`titles` 等），加 `step` 和 `version`（笔记记的读的版本），退出 1；`failed`、`detail`、`stderr` 不再有。`no_package` 带 `hint`，写好路径：`ocr.py parse <input> -o <scratch>/`，再 `p2z.py package put <scratch>/<名>`，再跑一次 `take`（试用里 agent 走偏的就是这一步）。`two_notes` 带一句 `hint`：留哪条由用户定。PDF 链接改叫 `input`，`pdf` 去掉（同一个路径两个名字）；`previous` 里的 `pdf` 也改叫 `input`。名字照 p2z `package take`，`ok` 和 `no_package` 的行都有它，所以 `pr.py take … \| ocr.py parse -o <scratch>/ -` 读得到 |
| check | 读不了笔记：`{code: unreadable, path, detail}`，退出 2 | `{file, code: file_not_found \| file_unreadable, hint}`，标准输出，退出 1。`complete` 0、`open` 1 不变，都不带 `hint` |
| quotes | 读不了笔记或 PDF、包里没有 `.md`、没装 pdftotext，都是 `unreadable`，退出 2 | 笔记、旁边的 PDF、包：`{file, code: file_not_found \| file_unreadable, path, hint}`，`file` 是笔记，`path` 是出问题的那一份，标准输出，退出 1。没装 pdftotext 改叫 `no_pdftotext`（同 `put` 的 `no_paddleocr`），退出 2、在标准错误最后一行。`pass` 0、`open` 1 不变 |
| put | 读不了笔记：`{code: failed, detail}`，退出 1；`annotate` 失败一律算进 `unmatched` 的 `annotate_failed`，接着 `note put`；`note put` 做不下去：`code` 是 p2z 的，退出 1；`unmatched` 各条只有 `why` | 读不了笔记：`{file, code: file_not_found \| file_unreadable, hint}`，标准输出，退出 1。p2z 做不下去：`annotate`（`put_note.py:122`，先跑）退出 2 时整个命令就停，不跑 `note put`、笔记文件不动；`note put`（`:188`）退出 2 也一样；都是退出 2，标准错误最后一行那个 p2z 命令的 `{code, hint}` 加 `step`，已建的批注下次 `put` 会找回。`code` 不是 ok、skipped 时，行里提上 `note put` 的 `hint`。`unmatched` 每条按 `why` 带一句 `hint`。"links could not be taken off" 那句警告照旧在标准错误。`ok`、`skipped` 0，其余 1 不变 |
| heading | 解析不出的写成 `{cite, code, hint}`（把 p2z 的 `item` 改了名）；p2z 做不下去时 `{code: failed, detail}` 在标准输出，退出 2 | 解析不出的原样是 p2z 那一行 `{item, code: not_found \| ambiguous, keys?, hint}`：写的可能是 key，叫 `cite` 不对；退出 1 时标准错误最后一行 `{"summary": {total, failed}}`（新加）。p2z 做不下去：每篇一行 `{item, code: not_run}`，标准错误最后一行 p2z 的 `{code, hint}`，退出 2 |

## 6. 要跟着改的

别的 skill 里没有调 paper-read 脚本的地方：在仓库里 grep `prepare_note|check_note|check_quotes|index_heading|put_note|paper-read/scripts`，`docs/` 和 `paper-read/` 以外只有提到 paper-read 名字的 `paper-to-zotero/SKILL.md:8,27,71,82`、`references/organize.md:7` 和 `tests/test_annotate.py` 里的批注文字，都不用改。下面全在 paper-read 里。

**SKILL.md**

- 25：`cd` 和 `uv run ../paper-to-zotero/scripts/p2z.py` 那句 → *Calling* 一段，照 p2z SKILL.md 第 10 行：PATH 那一句（paper-read、paper-to-zotero、paddleocr 三个 `scripts/`：paper-read 自己，和它的文档里出现命令的两个），`pr.py -h` 列短词、`pr.py <短词> -h` 是参考，标准错误留着。
- 35：`uv run scripts/prepare_note.py --cite <citation key> -o <scratch> [--bare] [--title <PDF title>]` → `pr.py take <citation key> -o <scratch>/ [--bare] [--title <PDF title>]`。
- 36：`no_package` 的做法 → 跟着那一行的 `hint`（第 1 节前三步）；103 的 "then `prepare_note` again" → `take`。
- 37：`two_notes` → 跟着它的 `hint`。
- 38、39："`failed` with `no_such_title`"、"`failed` with any other code" → `no_such_title`、p2z 的其他 code（`step` 说是哪个 p2z 命令），跟着它的 `hint`；"Zotero not running" 那半句移走：Zotero 没开时退出 2，原因在标准错误最后一行。
- 42：→ `pr.py check <note>`（`--full`）、`pr.py quotes <note>`，删 "(no package: without `--package`)"。
- 43、50、52：`put_note` → `pr.py put`；46 的 "Zotero not running … the `{code, hint}` its stderr ended with" → 退出 2、标准错误最后一行。47–50 `unmatched` 各种 `why` 的做法 → 跟着每条的 `hint`，只留"每条都要在 PDF 里看过"这一句。
- 56：`prepare_note.py … --bare` → `pr.py take --bare …`。64、72、85：`check_note --full`、`check_note` → `pr.py check --full`、`pr.py check`。
- 70：`uv run ../paddleocr/scripts/doc.py show <package>` prints `no open findings` → `ocr.py findings <package>` prints no line with status `open`。
- 93–98 派 reader 的模板：加一句 "Start every shell call with: `set -o pipefail; export PATH="<paper-read>/scripts:<paper-to-zotero>/scripts:<paddleocr>/scripts:$PATH";`"，主 agent 填好绝对路径（pilot spec 1.7）；94 的 `PDF: <pdf>`、96 的 `PDF <pdf>` 从 `take` 那一行的 `input`、`previous.input` 填；95 的 `with uv run <paddleocr>/scripts/doc.py` → `with ocr.py`。
- 102：`doc.py commit` → `ocr.py commit`。
- 104、115：`check_quotes` → `pr.py quotes`；115 的 `unreadable` → `no_pdftotext`。
- 40、77 和 36、103 里的 `p2z.py pdf -h`、`p2z.py package put` 已是新写法，有了 PATH 那句就能跑，不改。

**references/**

- note-format.md 7、11：`prepare_note.py`、`put_note.py` → `pr.py take`、`pr.py put`；70：`check_note.py --full` → `pr.py check --full`；95：`check_quotes.py` → `pr.py quotes`。
- notes.md 24：`uv run scripts/index_heading.py --cite <citation key>…` → `pr.py heading <citation key>… | jq -r 'select(.code=="ok").heading'`（解析不出的那一行没有 `heading`），"A citation key it cannot resolve prints paper-to-zotero's own line" 不变；56：`prepare_note.py` → `pr.py take`。
- reading.md 12、14：输入里加上"每次 shell 调用开头的那一句"，14 的 "how to run its `doc.py`" 随之去掉；`<paper-read>` 照旧用来指文档路径（如 73 的 tagging.md）。39、54：`doc.py commit` → `ocr.py commit`。61：`uv run <paper-read>/scripts/check_note.py <note> --full` → `pr.py check --full <note>`；62：`check_quotes.py <note> --pdf … --package …` 和括号里那句 → `pr.py quotes <note>`。63：`doc.py show <package folder>` prints `no open findings` → `ocr.py findings <package folder>` prints no line with status `open`。72：`doc.py show` → `ocr.py findings`。

**脚本**

- 新 `scripts/pr.py`（入口，git 里 100755）。新 `scripts/prlib/cli.py`：从 `paper-to-zotero/scripts/p2zlib/cli.py` 拷 `OK/ACT/CANNOT`、`Stop`、`write`、`emit`、`Parser`、`prog`（`PR_PROG`）、`parser`、`parse`、`stdin_lines` 和 `names()` 读清单的那段（主 agent 先在 p2z 里改好上游失败行的读法，再拷）、`document()` 读文件的那段，文件头写来源和提交号（原则 §3 *Small, independent, pure-Python scripts*）；再加 paper-read 自己的一个小函数：按路径跑兄弟 skill 的入口，返回它的行、退出码，退出 2 时取标准错误最后一行。它替掉今天的三份：`prepare_note.py:66–82`、`index_heading.py:33–49`、`put_note.py:56–74`。
- `scripts/sources.py` → `scripts/prlib/sources.py`；导入跟着改：`prepare_note.py:47–48`、`check_quotes.py:43–44`、`put_note.py:46–47`；它的说明 2–3 行的 `put_note.py`、`prepare_note.py`、`check_quotes.py` → `pr.py put`、`pr.py take`、`pr.py quotes`，7 行的 `doc.py objects` → `ocr.py objects`。
- 五个脚本：第 1 行加 `--quiet`；用法行（各自第 8 行）→ `pr.py <短词> …`；帮助里的脚本名（`prepare_note.py:14,18`、`check_note.py:6`、`check_quotes.py:6`、`put_note.py:13,19,27,172`）→ 短词（`doc.py objects` → `ocr.py objects`），说明里的 `--taken`（`check_note.py:21`）→ "`.taken` beside the note"；帮助补上退出码和例子；选项照第 4 节（`prepare_note.py:151–154`、`check_note.py:127`、`check_quotes.py:127–128`、`index_heading.py:69`）；输出照第 5 节（`check_note.py:135–136`、`check_quotes.py:131–132,141–142`、`index_heading.py:74–75,85`、`prepare_note.py:160–163,176–178`、`put_note.py:180–182,186–187,194`）。
- `take`：先解析，`prepare_note.py:93–104` 的 `paper_of` 挪到最前，之后的 p2z 调用（`:124` `pdf`、`:131,172` `package take`、`:142` `note take`）交条目 key；`:125`、`:132`、`:174` 改和解析出的引用键比；`-` 读清单；失败行提上 p2z 的那一行（`:143–144`、`:175–178`）；`no_package`、`two_notes` 加 `hint`；`pdf` 改叫 `input`（`:134,136,204`）。
- `put`：`annotate` 退出 2 就停（`:122` 之后），不写链接、不跑 `:188` 的 `note put`；`unmatched` 各条按 `why` 加 `hint`（`:21–29` 的说明是它们的出处）；行里提上 `note put` 的 `hint`（`:194`）。

**调 p2z 的地方**：p2z 那边已是新写法，命令不变；照旧按路径经 uv 跑 p2z 的入口（`prepare_note.py:69`、`index_heading.py:36`、`put_note.py:59`；假 p2z 没有开头那一行），`PAPER_READ_P2Z` 照旧。`prepare_note.py:94` `items`、`:124` `pdf`、`:131,172` `package take <K> -o <dir>/ [--title T]`、`:142` `note take <K> -o <dir>/`（`<K>` 改成解析出的条目 key）；`index_heading.py:72` `items <K…>`；`put_note.py:122` `annotate <PDF key> <框的文件>`、`:188` `note put <note> -i`。

**调 paddleocr 的地方**（照 paddleocr 已定的写法）：`put_note.py:51` 的 `PAPER_READ_DOC` → `PAPER_READ_OCR`，默认 `<paddleocr>/scripts/ocr.py`；`:102` 照旧是 `objects <包> --source <PDF>`，只是跑的是 `ocr.py`。文档那几处已列在上面（SKILL.md 70、95、102，reading.md 14、39、54、63、72）。

**测试**

- 新 `tests/conventions_fixture.py`（第 7 节）。
- `fake_p2z.py`：5–8 行的说明（它兼当 `PAPER_READ_OCR` 的 `objects`）；`:43,60,70,80` 给所有条目同一个 key `ITEMKEY1` → 假库里每篇有自己的 8 位 key，`items` 按 key 或引用键找，`pdf`、`package take` 打出那篇自己的 key，`note take`、`package take` 写 key 也找得到那一篇。
- `test_prepare_note.py:57–58`：`--cite CITE -o out` → `CITE -o out/`；`:72,99,127,134` 的 `pdf` → `input`；`:122–124` 断言 `failed` 和 `detail` 的 → 断言 `code: no_such_title`、`titles`、`step`；`no_package`、`two_notes` 断言带 `hint`；日志里 `package take` 收到的是条目 key（`:83,108` 的断言）；加：写条目 key 也行；`-` 读到一篇取它、两篇 `ambiguous`；p2z 做不下去时退出 2（用真 p2z 对刚关掉的端口，同第 7 节的 `no_service`）。
- `test_check_note.py:143–149`：`--taken` 去掉，测试把 `.taken` 写在旁边；加：笔记不在 → 标准输出 `{file, code: file_not_found}`，退出 1。
- `test_check_quotes.py:71,97,106,110–115`：把 `<名>.pdf`、`<名>/` 摆在笔记旁边；PDF 不在、包里没有 `.md` → 标准输出的 `file_not_found`、`file_unreadable`（`path` 指那一份），退出 1。
- `test_index_heading.py:42–45`：写在后面、`-`、解析不出的是 p2z 那一行、退出 1 的汇总在标准错误；上游失败行原样转出。
- `test_put_note.py:17–19` 和 `test_sources.py:10–13` 的导入路径 → `scripts/prlib`；`test_put_note.py:60,103` 的 `PAPER_READ_DOC` → `PAPER_READ_OCR`；加：笔记不在 → 标准输出 `file_not_found`，退出 1；`unmatched` 各条带 `hint`。

**仓库**：主 agent 落地时把 paper-read 从 `tests/check_conventions.py` 的 `NOT_YET` 拿掉；其余检查要的都在 paper-read 的 fixture 里。`README.md:27` 只讲 skill 做什么，不改。冻结的 spec、开着的 issue 里提到旧脚本名的地方不改（照 pilot：用到时再改）。

## 7. 约定检查和验收

**约定检查**（paper-read 从 `NOT_YET` 拿掉后）：

- 静态：入口和五个脚本的开头一行；入口 100755（五个脚本已是）；`WORDS` 和 `scripts/*.py` 一一对上（所以 `sources.py` 要挪）；字符串里没有脚本文件名、`uv run scripts/`、去掉的选项。
- 帮助：五个短词的 `-h` 都退出 0，用法行以 `pr.py <短词>` 开头，有退出码和例子；只用表里的字母（只有 `-h`、`-o`）；没有带多个值的选项。
- `paper-read/tests/conventions_fixture.py`，照 `paper-to-zotero/tests/conventions_fixture.py`：
  - `HELP_ENV = {"PAPER_READ_P2Z": "/nonexistent/p2z.py", "PAPER_READ_OCR": "/nonexistent/ocr.py"}`：`-h` 不调兄弟 skill，调了就会失败。
  - `REMOVED = {"--cite": (), "--out": (), "--taken": (), "--pdf": (), "--package": ()}`；没有 `--collection`，不写 `SELECTS`。
  - `env(tmp)`，上下文管理器：在 `tmp` 里写假库 `library.json`（400 篇，各有自己的 8 位 key 和引用键，标题各 300 字），交出 `PAPER_READ_P2Z`（`tests/fake_p2z.py`）、`FAKE_P2Z`（那个假库）、`PAPER_TO_ZOTERO_CONFIG`（`tmp` 里一个不存在的文件：读库不要配置，见下）和 `no_proxy`、`NO_PROXY` = `127.0.0.1,localhost`（这台机器设了 `http_proxy`，`no_service` 里的真 p2z 连的是 127.0.0.1）。假 p2z 不是服务，`finally` 里没有要停的；文件随检查的临时目录删掉。
  - `quiet(tmp)`：`{"run": "pr.py heading <第 1 篇的引用键> <第 2 篇的引用键>", "lines": 2}`。
  - `reader(tmp)`：`{"run": "printf '%s\n' <400 个引用键> | pr.py heading -"}`，完整输出约 140 KB，过 64 KiB。
  - `writer`：一句字符串："put writes one note per call and prints its one line after every write: there is nothing for head to cut"。
  - `no_service(tmp)`：现绑一个端口再放掉，`{"run": "PAPER_READ_P2Z= PAPER_TO_ZOTERO_BASE_URL=http://127.0.0.1:<那个端口> pr.py take <第 1 篇的引用键> -o <tmp>/scratch/", "code": "zotero_unreachable"}`。变量清空就落回真的 p2z。2026-11-05 实测：没有配置文件、刚关掉的端口，`p2z.py items` 0.4 秒退出 2，标准错误最后一行 `zotero_unreachable`。用真 p2z、不给假 p2z 加"挂掉"的模式：测的是 p2z 真实的报错格式，机制只要一份。

**测试**：第 6 节那些改完，`uv run paper-read/tests/run_all.py`、`uv run tests/check_conventions.py` 全过；p2z、paper-fetch 不调 paper-read，测试不受影响。

**在真库上量**（只读）：

1. 已量（2026-11-05）：`p2z.py items <条目 key>` 和 `p2z.py items <引用键>` 打出同一行。`take` 先解析就靠它。
2. 用现在的 `prepare_note.py` 取 T-CACE，存下输出和文件；实现后 `pr.py take xiaoTCACE2026`、`pr.py take <条目 key>` 各取一次，除路径和 `pdf` 改叫 `input` 外一样。
3. 同一条笔记上，现在的 `check_note --full`、`check_quotes --pdf --package` 和改后的 `pr.py check --full`、`pr.py quotes` 结果一样。
4. 已量（2026-11-05）：`prepare_note` 把 `<名>.pdf`、`<名>/`（包）、`.note.md`、`.note.md.taken`、`.zotero.json` 放在一起。从笔记旁边找就靠它。
5. 刚关掉的端口下：`pr.py take`、`pr.py heading`、没有包的笔记上的 `pr.py put` 都马上退出 2，标准错误最后一行 `zotero_unreachable`；有包的笔记上，`put` 先跑完 `ocr.py objects` 才碰 Zotero，不算"马上"，但同样退出 2、不跑 `note put`。
6. `p2z.py search T-CACE | pr.py heading -` 打出标题行；一个不存在的引用键 → p2z 的 `{item, code: not_found}`，退出 1，标准错误最后一行是汇总；`p2z.py items <不存在的> | pr.py heading -` 把那行失败原样转出，退出 1。

**实测写入**（要用户点头）：在一条测试笔记上走一遍 `take` → `check` → `quotes` → `put`。

**全流程试用**（推送、重装后）：照 2026-11-05 那次，派一个只看已装 skill 文档的 subagent 读一篇论文，用 `trial.py` 数：没有 `cd` 进 paper-read 或 p2z、没有 `uv run`、没有 `2>/dev/null`，paper-read、p2z、paddleocr 都经 PATH 调。那次试用里经 paper-read 调 p2z 新旧混用，就是这条要验的。

**行数**：文档（SKILL.md 加 `references/`，现在 392 行）要变短：`cd` 那段、`--package` 的括号、`failed` 和 `put` 里 Zotero 没开的那半句、`unmatched` 各种 `why` 的做法都去掉（后者进了 `hint`），`-h` 已写的不在文档里重写。脚本多出的只有入口、拷来的 `cli` 部分、man 页帮助和提示，三份调兄弟 skill 的小函数并成一份（pilot spec 第 9 节的口径）。文档里没有 `cd`、`uv run`、`2>/dev/null`。

## 8. 开着的 issue

都留到以后：六张讲的都是行为、笔记内容或交接，没有一张是 §3 要求的写法。

- `20261103-paper-read-flows-not-run`：讲流程在真项目里跑没跑过。第 7 节的真库验收和全流程试用顺带跑到的分支，在那里打勾。
- `20261103-paper-read-note-expression`：笔记的呈现，和命令无关。
- `20261103-paper-read-note-images`：同上，还在暂停。
- `20261103-paper-read-note-two-depths`：同上。
- `20261105-paper-read-note-format-trial-notes`：笔记格式和 p2z 的笔记转换；第 4 条问的"问题标题里的 Fig. 会不会加链接"是 `put` 的行为（`sources` 不读标题里的），不是写法。
- `20261105-paper-read-report-when-main-is-subagent`：reader 的报告存哪，是交接的事，这次不动交接。

## 9. 偏离和理由

和 §3 或样板不一样的地方：

- **`take` 也认条目 key**（扩展）：全 skill 一条认论文的规矩。`heading -` 要认 key，因为 p2z 打出的行用 `key` 指条目；`take` 只认引用键的话，同一个 skill 就有两条规矩。代价为零：今天就有的那次 `items` 调用挪到最前。
- **`check`、`quotes`、`put` 从笔记旁边找别的文件**，不写在后面：§3 说文件写在后面；这几样不是命令要处理的东西，是笔记的附件，`take` 按笔记的名字放在旁边。三个命令一条规矩（`put` 今天就这样），省掉从 `take` 的输出里抄路径，也不会拿错版本的 PDF 去对。

## 10. 待定

没有。原先和 §3 字面对不上的三处（`-o` 指目录、只处理一样东西的命令退出 1 不打汇总、`-` 把上游的跳过和失败行原样转出），用户 2026-11-06 同意写进了 §3。

## 11. 实施时的改正（2026-11-06）

- `take` 不再按引用键比对 p2z 的行：先解析出条目 key，后面每个 p2z 调用都用它，第一行就是答案；没有引用键的条目也能取。
- 从 `package take` 起，转上来的 `take` 失败行才带 `version`；`items`、`note take` 那几步在读到笔记之前，只带 `step`。
- `check` 的文件那行，读不了的是笔记旁边的 `.taken` 时带 `path`。
- `put` 多一个 `write_failed`：改写笔记文件失败时，原来的代码会落到回溯。
- `sibling()` 遇到非零退出、又一行 JSON 都没打的兄弟命令，按退出 2 算，`step_failed`，`detail` 是标准错误最后一行。
- `take -o` 取绝对路径，同 p2z `package take`。
- `take -` 读到上游失败行之后 p2z 又做不下去：那一行已经在标准输出上（它是上游的行，先于 take 自己的事打出来），`heading` 也一样。
- notes.md 那句 heading 的话改了：`jq 'select(.code=="ok")'` 会把失败行滤掉，句子写明这一点。
- 例子里的 `xiaoTCACE2026` 是简写，真引用键是 `xiaoTCACETimeConditionedAutoregressive2026`（条目 `9ZFX6QP6`）。
- 行数：代码 932 → 1203（入口 64、`prlib/cli.py` 193，三份调兄弟 skill 的代码合成一个 `sibling()`）；文档 392 → 389。
- 在 paddleocr 合进来之前，`put` 把每个图表列为 `unmatched`，why 是 `no_paddleocr`。
