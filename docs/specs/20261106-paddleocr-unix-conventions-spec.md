# paddleocr 对接 Unix 约定

- 日期：2026-11-05。来源：[Unix 约定 issue（已归档）](../issues/archive/20261104-skills-unix-conventions-fixed.md)。状态：已冻结（2026-11-09）。用户于 2026-11-06 同意了 §3 补的几处（issue 第 14 条）和实施计划；实施及收尾已完成，实施时的更正记在本 spec。
- 约定只有一个出处：`docs/design-principles.md` §3 *The Unix/Linux philosophy*。这份只写 paddleocr 自己的：入口和短词、东西怎么指定、要跟着改的地方。样板是 p2z（`paper-to-zotero/scripts/p2z.py`、`p2zlib/cli.py`），需要的部分拷过来。
- 范围：一遍约定整理。解析流程、检查、settle 的做法、输出里的信息都不变；变的是输出的样子（第 5 节）和一处行为：`show` 不再顺手记改动（§3 要求，见第 10 节）。记录的格式和版本号（`FORMAT`、`REFINE`、各模块的 `VERSION`）不动，库里已有的结构化包照旧算最新，不会被重新处理。
- 落地顺序：第一批 vllm-serve 和 paper-fetch，第二批 paddleocr 和 paper-read。跨 skill 的改动各有一个归属（第 6 节）。

## 1. 改完是什么样

每次调用开头单独一句，列出 paddleocr 自己和它用到的 vllm-serve（卡住时要用它的 `serve.py`）：

```
set -o pipefail; export PATH="<paddleocr>/scripts:<paddleocr>/../vllm-serve/scripts:$PATH";
```

下面按 [`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 的次数排（真项目 / 本仓库）。"现在"一栏都要先 `cd` 到 skill 目录。

```
# 解析（parse，26 / 372）
现在  uv run scripts/parse.py paper.pdf -o /abs/out
改后  ocr.py parse paper.pdf -o /abs/out/
现在  uv run scripts/parse.py a.pdf b.pdf scans/ -o out/ --pages 1-8 --force
改后  ocr.py parse -f --pages 1-8 a.pdf b.pdf scans/ -o out/

# 库里缺结构化包的 PDF（p2z 的 import.md 第 5 步、organize.md 的 Structured packages）
现在  p2z.py package take K1 K2 --missing -o D/      再把打出的 input 一个个抄给 parse.py
改后  p2z.py package take K1 K2 --missing -o D/ | ocr.py parse -o D/ -

# 还开着的 finding（doc show，1 / 9；settle 和 paper-read 的完成条件）
现在  uv run scripts/doc.py show out/paper           # 打 "no open findings" 或定宽的几列
改后  ocr.py findings out/paper                     # 一行一个 JSON；完成条件：退出 0

# 看一处（finding、块、图、页）和截一块
现在  uv run scripts/doc.py show out/paper missing_text@p3
      uv run scripts/doc.py show out/paper p4 --box 72 100 300 400 --dpi 400
改后  ocr.py show out/paper missing_text@p3
      ocr.py show out/paper p4 --box 72,100,300,400 --dpi 400

# 记下改动、重切图、重新处理（doc，40；doc render，3）
现在  uv run scripts/doc.py commit out/paper
      uv run scripts/doc.py figure out/paper p6-4 --box 50 80 550 400 --why "cut off the legend"
      uv run scripts/doc.py figure out/paper --page 6 --box 50 80 550 400 --why "read as text"
      uv run scripts/doc.py render out/paper
改后  ocr.py commit out/paper
      ocr.py cut out/paper p6-4 --box 50,80,550,400 --reason "cut off the legend"
      ocr.py cut out/paper p6 --box 50,80,550,400 --reason "read as text"
      ocr.py render out/paper

# 图表在 PDF 里的位置（doc objects，8；paper-read 的 put_note 在代码里调，那边改）
现在  uv run --quiet <paddleocr>/scripts/doc.py objects <包> --source <pdf>
改后  uv run --quiet <paddleocr>/scripts/ocr.py objects <包> --source <pdf>
```

## 2. 短词表

入口 `scripts/ocr.py`。不叫 `paddleocr.py`：`parse.py` 在 paddleocr 的 uv tool 环境里跑时，`scripts/` 排在 `sys.path` 最前，同名文件会挡住它要导入的 `paddleocr` 包。`ocr` 全系统不重名（`p2z.py`、`pf.py`、`serve.py`，paper-read 取 `pr.py`）；tool 环境里也没有叫 `ocr`、`ocrlib` 的顶层模块（2026-11-05 查过 site-packages）。入口照 `p2z.py` 写：一张短词表，经 `uv run --quiet --script` 执行对应脚本，用环境变量 `OCR_PROG` 把用户敲的命令名传给脚本，用法行里写 `ocr.py <短词>`。`ocr.py -h` 列出短词，各附一句作用；表外的词退出 2，打出这张表。

| 短词 | 脚本 | 做什么 | 词性 |
|---|---|---|---|
| `parse` | parse.py | 用模型解析 PDF 或页面图片（要 GPU） | 动词 |
| `findings` | doc.py findings（新，原 `show DIR` 不带第二个参数） | 列出开着的和判为 unresolved 的 finding，`-a` 连判为 ok 的 | 名词，列东西 |
| `show` | doc.py show | 看一个 finding、块、图或页：文字、它下面的文字层、页面图；`--box` 截一块 | 动词 |
| `commit` | doc.py commit | 把 Markdown 里的改动和判定记进记录，重新检查，重写 Markdown | 动词 |
| `cut` | doc.py cut（原 `figure`） | 按给的框重切一张图，或在某页新切一张 | 动词 |
| `render` | doc.py render | 用现在的代码把模型的原始输出重新处理、检查，不用 GPU | 动词 |
| `objects` | doc.py objects | 列出图和表在 PDF 里的位置，给论文笔记做链接 | 名词，列东西 |

- doc.py 的子命令名改成和短词一样（`figure` → `cut`，加 `findings`），表里每个词就是脚本自己的命令。
- `cut` 不叫 `figure`：`figure` 是名词，读起来像"列出图"；文档里本来就说"cut it anew""cut figures"。不叫 `crop`：`show --box` 截的也叫 crop，容易混。
- `findings` 单列：一个词只有一种输出，列表是 JSON 行，`show` 是给人读的文本。
- **不是命令的**：`checks.py`、`conventions.py`、`figures.py` 是 doc.py 导入的模块，挪进 `scripts/ocrlib/`（照 `p2zlib/`、`pflib/`，paper-read 的 `sources.py` 也挪进 `prlib/`）。约定检查要求 `scripts/*.py` 除入口外都有短词、带 uv 开头、可执行，模块留在原处过不了。
- [`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 里算到 paddleocr 名下、上表没有的：`doc`（40，全在本仓库）是 `doc.py` 后面没跟子命令的命令行：[`usage.py`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 按路径数，读、改这个文件的命令（`sed`、`git diff`）和 `--help` 都落在这里，`--help` 换成 `ocr.py -h`；`doc paddleocr`（4）、`checks`（6）、`conventions`（4）、`figures`（8）同样是本仓库开发时按路径碰到的文件，不是调用；`figcheck`（22）是 `figures.py` 以前的名字，脚本早已没有，只剩 `__pycache__`。

## 3. 东西怎么指定

- **`parse` 后面写文档**：PDF、图片，或一个装页面图片的目录。只收文件，所以后面写的都是路径；不存在的那一篇报 `file_not_found`（原 `not_found`），其余照做；目录也算文件。后面什么都没写：用法错误，退出 2。
- **`parse -`** 读路径清单：一行一个路径；一行是我们自己的 JSON 时取指明文件的那个字段，这里是 `input`。parse 自己打的行带 `input`，p2z `package take` 成功的行也带（那边本来就注明 "paddleocr's input"）。上游报失败的 JSON 行（`code` 既不是 `ok` 也不是 `skipped`，又没有 `input`，如 `package take` 的 `no_pdf`、`not_found`）原样转到标准输出，算没做成（退出 1，汇总里记一笔）；没有 `input` 而 `code` 是 `skipped` 的行也原样转出，算跳过；没有 `input`、`code` 是 `ok` 或没有 `code` 的 JSON 行：`invalid_list`，退出 2，什么都不解析（同 p2z）。所以第 1 节的管道中间不用过滤。这是原则 §3 的规矩（用户 2026-11-06 同意）。读到空清单：没有要做的事，退出 0，模型不加载。`-` 在 `ensure_tool_env` 返回之后才读：它换到 tool 环境时会带着同一个标准输入重新执行自己，先读了，换过去的那个进程就只读到空清单，什么都不解析就退出 0；tool 不在（`paddleocr_missing`，不换环境）时就地读：空清单退出 0，否则每篇一行 `not_run`，退出 2。`parse -h` 写明 `-` 读的是路径清单。
- **doc.py 的六个词后面写一个解析目录** `<outdir>/<stem>`，是路径。这些词不读 `-`：没有一次要处理一串目录的用法，settle 一篇一个 subagent。
- **`show` 的第二个参数**：finding id（`missing_text@p3`）、块 id（`p4-12`）、图 id（`p6-4`、`p6-n1`）或页（`p4`），在记录里查，查法照旧。不写第二个参数是用法错误，hint 指 `ocr.py findings DIR`（今天的 `show DIR` 列 finding，改后归 `findings`）。**`cut` 的第二个参数**：图 id 是重切那张；`p<N>` 是在第 N 页新切一张（替掉 `--page N`）；写了一个不是图的块（`p6-12`）报 `not_found`，hint 是"那页新切一张：`ocr.py cut DIR p6 --box …`"。两者都不像路径（不含 `/`），不会被当文件。
- **`--source FILE` 留作选项**：见第 10 节。

## 4. 选项

[`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 只按命令计数，没有 paddleocr 各选项的次数；下表按代码列出全部选项（[`inventory.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 的那几列，加上 `show` 的 `--box`、`--dpi`）。

| 现在 | 改后 | 说明 |
|---|---|---|
| parse `-o, --output OUTDIR`（必填） | `-o, --output DIR/`（必填） | 产物是目录，帮助和文档都写成 `DIR/`；写的值都当目录，没有就建（同 p2z `package take -o`）。必填照 §3（产物是几个文件的命令） |
| parse `--pages RANGES` | 不变 | 字母表里没有合适的字母 |
| parse `--force` | `-f, --force` | 表里的 `-f` |
| parse `--charts`、`--figure-text`、`--photo` | 不变 | |
| parse `--backend auto\|vllm\|native` | 不变 | |
| parse `--vl-server URL` | 不变 | |
| doc 各词 `--source FILE` | 不变 | 见第 10 节 |
| show `--box X1 Y1 X2 Y2` | `--box X1,Y1,X2,Y2` | 一个选项只带一个值；逗号分隔，和 `--pages 1-3,8` 一个写法。brief 和开着的 issue 都教的是四个数分开写：照旧写（`--box 72 100 300 400`）是用法错误，hint 打出逗号写法。负数开头的值 argparse 不收（`--box -5,10,…` 报缺值），`-h` 写明坐标从 0 起、超出页边的框会被截到页内，用不着负数 |
| show `--dpi N` | 不变 | |
| figure `--box X1 Y1 X2 Y2`（必填） | cut `--box X1,Y1,X2,Y2`（必填） | 同上 |
| figure `--page N` | 去掉 | 改成第二个参数 `p<N>` |
| figure `--why WHY` | cut `--reason TEXT` | p2z 和 paper-fetch 的 `answer` 里"为什么这么做"都叫 `--reason`；paper-fetch 的 `--why` 是另一个意思（`--label` 的依据）。记录里的字段照旧叫 `why` |
| — | findings `-a, --all` | 连判为 ok 的一起列（平时略去的） |

不加 `-n`、`-q`、`-v`：没有命令需要。所有词：选项和后面写的东西可以交错（`parse_intermixed_args`，doc.py 先由入口定好子命令再各自解析），长选项可写唯一前缀。

## 5. 输出和退出码

退出码一条规矩（p2z 样板第 9 节）：退出 1 是命令处理的那样东西本身有问题（不在、不是该有的那种、格式旧了、它的改动被拒），写在那样东西自己的行里；处理几样东西的命令再在标准错误最后打汇总，只处理一样的不打。退出 2 是这次调用、或往下做要靠的东西有问题（用法、选项的值、服务、锁、读不了的清单），标准错误最后一行 `{code, hint, …}`（用法错误是 `{code: usage, detail, hint: "See <命令> -h."}`，拷 p2z 的 `cli.Parser`；去掉的 `--page`、`--why` 不另加提示）。标准输出被下游关掉后不再打印、照常做完、退出码不变（拷 `cli.write`、`cli.emit`）。做事的命令每行都带 `code`；列东西的行（`findings`、`objects`）不带。

- **`parse`**：
  - 标准输出照旧一篇一行，加 `folder`（`<outdir>/<stem>`，其余各词后面写的就是它；和 p2z `package take` 行里的 `folder` 同名同义）和 `code`：`ok`、`skipped`（`reason: up_to_date`，原 `skipped: "up_to_date"`）、`file_not_found`、`unsupported_input`、`bad_pages`、`parse_failed`、`not_run`；出错的行带 `hint`。`error`、`skipped` 两个字段并进 `code`：退出 2 时每篇要记 `not_run`，状态得有一个统一的字段，p2z 的行用的就是 `code`。`rendered: true`、`archived`、`edits_carried` 和其余字段照旧。
  - 重跑时先记下 Markdown 里的改动、重新处理时 finding 有进有出，现在写在标准错误（`parse.py:498,504` 的 `report`），改成放进这一行：`recorded`（每条改动一句，文字照旧）、`gone`、`new`、`reopened`。
  - 标准错误只留进度（`[paddleocr] … page N done`、加载模型、问 vllm-serve）和影响结果的警告（退回原生的原因、第二个版面模型没加载）。全部 `skipped` 的重跑，标准错误是空的。
  - 有一篇没做成（含从 `-` 原样转出的上游失败行）：退出 1，标准错误最后一行 `{"summary": {total, ok, skipped, failed}}`。
  - 做不下去：`paddleocr_missing`、`vl_server_failed`、`vl_server_unreachable` 从标准输出挪到标准错误最后一行，退出 2；每篇在标准输出记一行 `{input, code: not_run}`。
- **`commit`、`render`、`cut`**：现在是几行散文（"p3-12: 'teh' -> 'the'"、"findings gone: …"、"rendered <路径>"、"figure p6-4: <路径> — view it"）。§3 "stdout is data"：改成一行 JSON，说的是处理的那个目录：`{folder, code: ok, recorded: [原来的那几句], gone, new, reopened}`；没东西可记是 `code: skipped, reason: nothing_to_commit`；`cut` 加 `figure`、`image`；`render` 的行就是 `parse` 那一行（`rendered: true`）。改动的说法原样放进 `recorded`，文字不重写。
- **`findings`**：一行一个 JSON `{id, status, page, note}`，列的就是现在不带参数的 `show` 列的（开着的和判为 unresolved 的），`-a` 再加判为 ok 的；`page` 对整篇文档是 `null`；`note` 对开着的是 Markdown 里那条注释的文字，对判过的是理由，不再截到 110 字。有 `open` 项退出 1，标准错误最后一行 `{summary: {total, open, unresolved, ok}}`；全部已有判定（包括 `unresolved`）或列表为空退出 0。只读：不记改动、不加锁。完成条件从"打出 `no open findings`"改成"`ocr.py findings <folder>` 退出 0"（半路死掉的一次运行，标准输出也是空的）。
- **`show`**：产物是给人读的文本，照旧。只读（不再先 commit、不加锁，像 `objects`）；Markdown 里有没 commit 的改动时，标准错误打一句警告（`ocr.py commit DIR` 记下它们），退出 0。图片照旧写到 `$TMPDIR/paddleocr-show/<stem>-<hash>/`，`show -h` 写明。
- **`objects`**：输出照旧。
- **doc.py 各词处理的目录有问题，退出 1**（只处理一个目录，不打汇总）：目录不在 `{folder, code: file_not_found}`；目录里没有记录或读不了 `no_record`；旧格式 `old_format`（提示重新解析）；commit 拒收的 Markdown 改动 `edit_refused`（标记被改、图片行被改、段落拆不开，什么都没记；`detail` 说哪里、`hint` 说怎么改，文字取现在的提示；`render`、`cut` 先 commit 时同样）；记录里的源文件路径不在了 `source_not_found`（提示 `--source`）、那里换了一份 `source_mismatch`（这两条说的是这个目录的记录，没给 `--source` 时）；`objects` 的记录是从图片解析的 `not_a_pdf`（原 `refused` 退出 1，同 p2z `annotate`）；`show` 查不到第二个参数（或那页没解析）`not_found`，`cut` 找不到那张图、那页没解析、或写的块不是图 `not_found`（第 3 节）。这一行在标准输出；`show` 的标准输出是文本，它的这一行写在标准错误（第 10 节）。
- **doc.py 各词退出 2**：`locked`（另一个进程在写，提示等它结束）、`bad_box`（框在页外或太小）；`--source` 给的文件不在（`file_not_found`）或不是记录里那份（`source_mismatch`）：是这次调用给错了材料，同 paper-fetch `redraft --html`；`render` 还有 `paddleocr_missing`。用法错误里有两条说参数长什么样的 hint：`show DIR` 不写第二个参数（指 `ocr.py findings DIR`），`--box` 照旧写四个数（打出逗号写法）。原来是 `refused: …`、`error: …` 两种散文，退出 1 或 2 混着。

## 6. 要跟着改的

**paddleocr 自己**

- 新 `scripts/ocr.py`（git 里 100755）。`scripts/ocrlib/`：从 p2z 拷 `cli.py` 里用得上的（退出码常量、`write`、`emit`、`Parser`、`prog`、`parser`、`parse`、`paths`、`subcommand`、`summarize`），加上挪进来的 `checks.py`、`conventions.py`、`figures.py`；头上注明拷自哪个提交。挪进去以后 `checks.py:36` 的 `import conventions`、`figures.py:38` 的 `import conventions as C` 是同级裸导入，在包里找不到，改成相对导入（`from . import conventions`）。
- `parse.py`：第 1 行加 `--quiet`；6–72 行的说明改成 man 页（`ocr.py parse`，去掉 `doc.py`、`checks.py`、`figures.py`、`uv run parse.py` 这些字样：约定检查会扫到）；94、138 行注释和说明；149–151 行 `paddleocr_missing` 改到标准错误；224–225、236 行 `vl_server_*` 改到标准错误；287 行 `not_found` → `file_not_found`；498、504、516–518 行 `report` 并进那一行；535–548 行选项（`nargs="*"`、`-f`、`-`）；551–573 行 `main`（`code`、`folder`、`not_run`、汇总、防断管；`-` 在 `ensure_tool_env` 之后读，见第 3 节）。`-h` 照旧在 `ensure_tool_env` 之前返回，没装 tool 也能看。
- `parse.py` 调 vllm-serve 的那一段（`serve_up`，203–213 行，和 232 行读它结果的地方；`foreign_cuda` 转到 parse 自己的标准错误）归 vllm-serve 那一遍，它先落地，按它的约定：`up` 退出 0 或 1 是标准输出一行（失败时带 `code`：`unknown_profile`、`port_busy`、`server_failed`），退出 2 是标准错误最后一行 `{code, hint}`（`vllm_missing`、`not_permitted`、`usage`）。paddleocr 这一遍保留它改好的样子，不再动。
- `doc.py:156-165` 的 `source_of` 要修：记录里源文件路径为空（`tests/fixtures/synthetic.json` 就是）时，`Path("")` 成了当前目录 `.`，它存在，`sha256_of` 去读一个目录就抛 `IsADirectoryError`，`show`、`commit` 带着 traceback 退出 1（审阅时在副本上复现过）。路径为空、又没给 `--source`，就当没有源文件。
- `doc.py`：第 1 行加 `--quiet`；6–44 行的说明拆到各词的 man 页（目录里有什么 → `ocr.py -h` 和 `parse -h`；改 Markdown 的规矩 → `commit -h`；框的单位、图片写到哪 → `show -h`、`cut -h`）；61–64 行导入改 `ocrlib`；1421 行提示里的 "`show DIR p<page>` … `--page N`" → `ocr.py show DIR p<page>`、`ocr.py cut DIR p<page>`；1487–1552 行 `main`（子命令改名、`findings`、`cut` 的第二个参数、`--box` 一个值、`--why` → `--reason`、`show` 只读、各错误码和两条带专门 hint 的用法错误）；1533 行 `--page` 那条拒绝去掉。`render -h` 照旧在 `ensure_engine` 之前返回。
- `ocrlib/figures.py` 第 9 行 "parse.py's crops" 改说法（约定检查会扫到）。
- `SKILL.md`：第 10 行换成 *Calling* 一段（照 p2z SKILL.md 第 10 行：PATH 那一句、`ocr.py -h` 列短词、`<词> -h` 是各自的说明、标准错误别丢）；19 行；28 行（`serve.py` 经 PATH 找到，`VLLM_SERVE` 那半句留在 install.md）；38 行 "without `error`" → `code` 是 `ok` 或 `skipped`；40 行；42 行 `--force` → `-f`；62 行 `show` → `findings`；64 行 → "`ocr.py findings <outdir>/<stem>` 退出 0"；75、81 行 `doc.py show` → `ocr.py show`；报告一步加一句：任务结束时删掉自己 `show` 过的那几篇在 `$TMPDIR/paddleocr-show/` 下的文件夹。
- `references/settle.md`：10、11 行；17 行照旧自己定位（`<skill>` 是放这份 brief 的目录的上一级），句子换成 "Start every shell call with `set -o pipefail; export PATH="<skill>/scripts:<skill>/../vllm-serve/scripts:$PATH";`"；19 行 → `ocr.py findings <folder>`；20–22 行 `show`、`--box` 逗号写法，加一句图片写在 `$TMPDIR/paddleocr-show/<stem>-<hash>/`、报告前删掉；37、39 行 `commit`；65 行完成条件 → `ocr.py findings <folder>` 退出 0，`open` 的只剩 `figure_check`；80 行；82 行 `figure … --box X1 Y1 X2 Y2 --why …` → `cut … --box X1,Y1,X2,Y2 --reason …`；83 行 `--page N` → `cut <folder> p<N>`。
- `references/papers.md`：3、36 行 `scripts/conventions.py` → `scripts/ocrlib/conventions.py`，36 行 `doc.py render` → `ocr.py render`。
- `references/install.md`：3、44、58 行 `parse.py` → `ocr.py parse`；33 行 → `ocr.py parse <a PDF> --pages 1 -o <scratch dir>/`；70 行 `VLLM_SERVE` 指 vllm-serve 的入口。29 行检查 tool 环境的 `uv run --no-project --python …` 不是我们的脚本，不动。
- 测试：`test_parse.py` 17–20 行路径不变，165–175 行改成断言标准错误最后一行 `paddleocr_missing`、标准输出 `not_run`；`test_checks.py:12`、`test_figures.py:17-18` 的导入改 `ocrlib`；`test_objects.py` 107 行 `D.main(["objects", …])` 不变；新 `tests/conventions_fixture.py`（第 7 节）。
- 改完文档要变短：SKILL.md 90 行 + references 225 行，说明搬进 `-h`；脚本多出的只能是 man 页和拷来的共用部分。文档里没有 `cd`、`uv run scripts/`、`2>/dev/null`。

**paddleocr 这一遍改的别的 skill 的文件**

- `paper-to-zotero/SKILL.md:10`：*Calling* 那句 PATH 加 `<this directory>/../paddleocr/scripts`，不然下面的管道在 p2z 的调用里找不到 `ocr.py`（第 46 行派 judge 的那句不用加，judge 不解析）。paper-fetch 在第一批也改这同一句，paddleocr 在第二批，接着它改好的样子加。
- `paper-to-zotero/SKILL.md:73`（"`-o <scratch>`""`--force`" → `ocr.py parse <input> -o <scratch>/`、`-f`）、`references/import.md:108`、`references/organize.md:26`：解析那一步写成第 1 节的管道。
- `paper-to-zotero/scripts/structured.py:141`（`package take -h` 的 "No package (`package: null`): run the paddleocr skill's parse on the link with -o DIR"）、`:192`（`not_taken`）、`:197`（`not_parsed`）、`:210`（`source_mismatch`）的 hint：写成 `ocr.py parse <input> -o DIR/`。只看 `-h` 干活的 agent，这是它找到 paddleocr 的唯一指引。
- `vllm-serve/profiles/paddleocr-vl.toml:1`（"client: paddleocr parse.py"）、`vllm-serve/references/install.md:76`（"paddleocr's `parse.py`"）→ `ocr.py parse`。
- `README.md:39` 的例子 `paddleocr/scripts/doc.py --help` → `paddleocr/scripts/ocr.py -h`。

**别人那一遍改的**

- paper-read 的文件（`put_note.py`、`sources.py`、测试、SKILL.md、reading.md 里调 paddleocr 的地方）归 paper-read 的 spec；它和 paddleocr 同在第二批，paddleocr 先落地，它用这里的词：入口 `<paddleocr>/scripts/ocr.py`；`objects <包> --source <pdf>` 参数不变，非 0 照旧记 `objects_failed`；完成条件 "`ocr.py findings <包>` 退出 0"；`ocr.py commit`、`ocr.py show`；派 reader 时它要整理包的话，PATH 那一句里有 `<paddleocr>/scripts`。
- `tests/check_conventions.py`：落地时主 agent 把 paddleocr 从 `NOT_YET` 拿掉。
- `.memory/paddleocr-skill-status.md:27` 和 `MEMORY.md:47` 的 `doc.py objects`：实现后主 agent 更新。
- 不改：已冻结的 spec；开着的 issue 里的 `doc.py`，用到时再改（同 p2z 那次）。

## 7. 约定检查和验收

**约定检查**（照 issue「铺开到其余 skill 时」第 7 步，接口见 `tests/check_conventions.py` 的说明和 `paper-to-zotero/tests/conventions_fixture.py`）。新 `paddleocr/tests/conventions_fixture.py`，只用标准库，不要 GPU、不要 tool 环境、不要源文件：

- `HELP_ENV = {"PADDLEOCR_PYTHON": "/no/such/python"}`：哪个词的 `-h` 若走到了换 tool 环境那一步，就退出 2，帮助那一节就红。
- `REMOVED = {"--page": (), "--why": ()}`；没有 `SELECTS`。
- `env(tmp)`：上下文管理器。在 `tmp` 下用 `tests/fixtures/synthetic.json` 和 `.md` 造两个解析目录（记录里源文件路径为空，靠第 6 节 `source_of` 的修正当作没有源文件）：`small`，Markdown 里改一个词（同 `test_doc.py` 的 "after the formula" → "following the formula"）；`big`，往记录里写约 200 条判为 `unresolved` 的 finding（fixture 本身一条没有），id 按 `code@块` 不重，每条判定理由 `why` 约 500 字，`findings` 的输出过 64 KiB（检查会量），Markdown 原样（正文的哈希对得上，不出警告）。yield `{"TMPDIR": tmp}`，`show` 之类的东西都落在 `tmp` 里；没有服务要起，`finally` 里无事可做。
- `quiet`：`{"run": "ocr.py commit <tmp>/small", "lines": 1}` → 退出 0，标准错误空。（核实过：commit 经过的 `check`、`merge_findings` 和三个模块都不往标准错误写东西；审阅时在源文件路径缺失的副本上 commit 也是退出 0、标准错误空。）
- `reader`：`{"run": "ocr.py findings <tmp>/big"}`，检查接上 `| head -1` → 退出 0，标准错误空。
- `writer`：一句话说明为什么没有——"边做边打的写命令只有 parse，它离不开 paddleocr 的 tool 环境，放进这里在别的机器上就永远失败不了；doc.py 的写命令写完才打一行。parse 被截断后照常做完，由 tests/test_parse.py 的单元测试管"。那条单元测试：把处理一篇的函数换成假的，标准输出接一个已经关掉的管道，断言每篇都处理了、退出码照常。
- `no_service`：`{"run": "PADDLEOCR_PYTHON=/no/such/python ocr.py parse <tmp>/x.pdf -o <tmp>/out/", "code": "paddleocr_missing"}` → 退出 2（标准输出一行 `{input, code: not_run}`）。paddleocr 要的"服务"是 tool 环境，不是一个端口。

静态和帮助两节不用为 paddleocr 另写：短词表对上 `parse`、`doc` 两个脚本；七个词的 `-h` 不要 tool 环境、不要 GPU 都能打（`parse -h`、`render -h` 在切换环境之前就返回）。

**要更新的测试**：第 6 节列的几处；`test_doc.py` 加命令行一层：`show`、`findings` 不记改动且有警告、`findings -a`、`cut` 的 `p<N>` 和逗号框、目录不在和 `edit_refused` 都是那个目录的一行、退出 1、源文件路径为空当没有源文件；`test_parse.py` 加 `-` 读路径和 JSON 行（含上游失败行原样转出）、空清单退出 0 不加载模型、`-` 在换环境之后才读、`file_not_found`、上面的防断管。验收：paddleocr（含 tool 环境里的 `test_doc.py --engine`）和 paper-read 的测试全过，约定检查全过。

**实现之前在真解析上先看**（只列出，没做）：

1. 库里一个已有的结构化包：`ocr.py parse` 对它打 `skipped`，证明模块挪位置、版本号没变，全库的包不会被重新处理。
2. 一篇短 PDF 经 vllm-serve 解析：一行 `code: ok`，标准错误只有进度；再跑一次：`skipped`，标准错误空。跳过的路上也要在 tool 环境里 `import paddleocr`（`parse.py:143`）；install.md 记过 WSL 上 Paddle 会打 `No ccache found` 这类话，要量这一步写不写标准错误。写的话，判断"在不在 tool 环境里"改用 `importlib.util.find_spec("paddleocr")`，不真导入。
3. `ocr.py parse a.pdf b.pdf -o D/ | head -1`：两篇都解析完，退出 0。
4. 同一个包上，改前 `doc.py objects` 和改后 `ocr.py objects` 的输出逐字节一样；`findings`、`show <块>`、`show p<N> --box …`、`commit`、`cut <图>`、`cut p<N>` 各走一遍，和改前 `doc.py` 的结果一样（输出的样子除外）。
5. `p2z.py package take <一篇缺包的条目> <一个不存在的引用键> --missing -o D/ | ocr.py parse -o D/ -`：缺包的那篇解析了，`not_found` 那行原样出来，退出 1。只读 Zotero，不做 `package put`。
6. `--vl-server http://127.0.0.1:<现找的空闲端口>/v1`：退出 2，`vl_server_unreachable` 在标准错误最后一行。

## 8. 开着的 issue

- `20261104-paddleocr-pdftotext-region-offset-crop-box`：**留到以后**。是 `show` 打印的 pdftotext 命令和框从哪个角量的行为问题，不是命令写法。这次只把 "PDF points (as pdftotext -x -y -W -H takes them)" 那句原样搬进 `show -h`、`cut -h`，修的时候在那里改准。
- `20261105-paddleocr-checks-miss-word-misreads`：**留到以后**。是检查的本事（逐页单词对比、拒答句式），要按原则 §3 *Heuristics validated blind* 单独做。
- `20261105-paddleocr-settle-workflow-gaps`：**第 2 条这次做**，因为 §3 要求：读的命令不写东西，commit 的日志也不是 `show` 的数据 → `show`、`findings` 只读，有没记的改动时警告。**第 3 条这次只做说明**：`show -h` 和 settle.md 写明图片在 `$TMPDIR/paddleocr-show/`、由用了 `show` 的那方在结束时删；`show -o` 留在 issue 里以后再定。第 1、4 条是 settle.md 的说法，第 5 条归 p2z 的 `package put`，**留到以后**。issue 带着第 1、3（`-o`）、4、5 条继续开着。

## 9. 待定

没有。三处原先和 §3 字面对不上的（`parse -o` 必填、只处理一样东西的命令退出 1 不打汇总、`-` 把上游的跳过和失败行原样转出），用户 2026-11-06 同意写进了 §3。

## 10. 偏离和理由

- **`show` 退出 1 的那一行写在标准错误**：它的标准输出是给人读的文本，一行 JSON 夹在里面接不上；p2z 产物是文档的命令（`export`、`convert`）也把每样东西的问题写在标准错误（主 agent 已同意）。
- **`--source FILE` 留作选项**：命令处理的是解析目录；源文件只在它挪了地方、记录里的路径失效时才写，角色不同，像 p2z 的 `merge --into`。
- **`show` 的图片不经 `-o`**：照旧写临时目录，`-h` 写明，`-o` 留给 issue（第 8 节）。
- **范围外的一处行为**：`show` 改成只读（第 8 节），今天它会先 commit。

## 11. 实施时的改正（2026-11-06）

- 在 worktree 里改，合进 main 是 `70bbad1`。`parse.py` 里调 vllm-serve 的那段（`serve_up`、`load_backend`）一行没动；`vl_server_*` 的错误在 `main` 里转成标准错误那一行。
- 从 p2z 拷的是 `Lines`（parse 的汇总是 `{total, ok, skipped, failed}`），不是 `summarize`；拷来的 `paths(values, field)` 按 `input` 读 `-`，上游的跳过、失败行原样转出。
- 解析几篇时某个目录被锁：只算那一篇 `locked`，退出 1，不让整个命令退出 2。
- 发现码表放在 `findings -h`，`parse -h` 指过去。`findings` 碰到没提交的 Markdown 改动也在标准错误上警告一行（第 7 节测试要的）。
- organize.md 那段保留"一次约一百篇"：先 `p2z.py package take --missing -o <dir>/ > <dir>/taken.jsonl`，再 `sed -n '1,100p' … | ocr.py parse -o <dir>/ -`。
- 顺手修：`show --box` 框整个落在页外报 `bad_box`；`--source` 指向目录算 `source_mismatch`；记录里"bring it back with the figure command"改成 `ocr.py cut`。
- 行数：代码 3,398 → 3,924（入口 66、`ocrlib/cli.py` 219，`doc.py` +229，其中约 100 行是 man 页）；文档 315 → 310 行。
- GPU 实测（2026-11-06，8128 端口）全过，`objects` 新旧输出逐字节相同。第 1 节"库里已有的结构化包照旧算最新"不对：888 个包里 881 个的检查版本是 5，现在的代码（改造前也一样）是 6，下次解析会不用 GPU 重处理一遍（12 页约 4 秒），结果和旧代码重处理的逐字相同。这是更早那次升级检查版本带来的，不是这次改造。
- 解析加载模型时，PaddleX 往标准错误打四行例行日志（"Creating model …"、"Model files already exist …"），改造前就有，不合 §3：另记 issue。

## 收尾时的已定调整（2026-11-07 决定，2026-11-09 完成）

用户选择 `findings` 有 `open` 时退出 1：实际调用都把它当完成关卡，退出码可直接表达结果。列出的记录、`-a`、只读行为不变；paddleocr 和 paper-read 的最终完成条件统一为退出 0。整理包中途仍允许图片项未完成，这时退出 1，下一步继续处理图片。测试分别覆盖未完成、已有判定、空列表及断管；未改其他检测规则。
