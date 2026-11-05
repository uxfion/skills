# skills 对接 Unix 哲学：全系统约定与 p2z 样板

- 日期：2026-11-04。来源：[docs/issues/20261104-skills-unix-conventions.md](../issues/20261104-skills-unix-conventions.md)（目标、已定的决策、现状数据都在那里，这里不重复）。
- 状态：定稿（2026-11-04），等用户点头后实现。经三路审阅（忠于需求和原则、技术、换个 agent 试用）和 advisor 改过；第 8 节两个问题用户都定了；第 6 节的规则文字用户同意，已改进原则、AGENTS.md 和 README。实现时修正，实现完冻结。
- 范围：一遍约定整理。流程不动，输出的内容不动（字段照旧），不重新设计。定两件事：所有 skill 都照的**全系统约定**（第 1 节），和先做的**样板：整个 paper-to-zotero**（第 2–5 节）。
- 第 1 节只有一个出处：定稿后，其中必须遵守的规矩改写成英文并进 `docs/design-principles.md` §3 *The Unix/Linux philosophy*，做法上的放进 AGENTS.md 和各 skill 自己的文档（第 6 节）；这份 spec 和以后各 skill 的 spec 都只引用它们。其余四个 skill 在样板用过一阵后照它改，各自的 spec 只写自己的短词表、各种东西怎么指定、要跟着改的地方。用户：「设计原则尽量是统一的，因为后续我们同样会扩展到其他的skill上，如果设计原则上或者比较顶层方面不一致，到时候会非常的混乱」。
- 试用期间各 skill 之间新旧并存：p2z 用新约定，paper-fetch 等还是旧的。p2z 的文档调 paper-fetch 时经 `pf.py` 和它的 PATH，选项照 paper-fetch 现在的写。

## 0. 改完是什么样

在库里搜几篇，看它们的 PDF 在哪：

```
# 现在
cd ~/.agents/skills/paper-to-zotero
uv run scripts/p2z.py read_library items --q POCUS
uv run scripts/p2z.py read_library pdf --cite madhusoodananPOCUSNetBeamformingInclusive2026

# 改后（开头那一句的写法见 1.2）
<PATH 那一句> p2z.py search POCUS | p2z.py pdf -
```

给一篇加标签，先空跑：

```
# 现在
uv run scripts/file_and_tag.py --cite madhusoodananPOCUSNetBeamformingInclusive2026 --add-tags-file <scratch>/tags.json --dry-run
# 改后
p2z.py tag -n --add-tag method/diffusion madhusoodananPOCUSNetBeamformingInclusive2026
```

## 1. 全系统约定

### 1.1 入口和短词

- 每个 skill 一个入口，放在 `scripts/`，名字取 skill 的简称加 `.py`，全系统不重名：`p2z.py`、`pf.py`；paper-read、paddleocr 铺开时照同一规则取；vllm-serve 唯一的 `serve.py` 已经是入口加短词（`up`、`status`、`down`）。
- 入口下面是短词，一个英文单词：做事的用动词（`tag`、`merge`），列东西的用名词（`items`、`tags`，像 `git tag`）。`<入口> -h` 列出全部短词，各附一句作用。
- 入口里一张表，把每个短词对到一个脚本，必要时带上固定的子命令（`search` → `read_library.py search`）。脚本文件不改名。表外的名字：退出 2，打出全部短词。
- 一个 skill 在代码里调另一个 skill 时，按路径执行对方的入口。

### 1.2 调用

- 用的时候带 PATH：每次调用开头单独一句，后面整条管道都找得到；不 `cd` 到 skill 目录，不写 `uv run`，当前目录留在项目里。写法：`set -o pipefail; export PATH="<skill 目录的绝对路径>/scripts:$PATH";`。`pipefail` 让管道里任何一个命令的失败都带到整行的退出码上（Zotero 没开时，`search … | pdf -` 整行退出 2，而不是 0）；`export` 漏了分号会当场报错，不会只对第一个命令生效。（用户选 A）
- 两个 skill 写在同一句里：`export PATH="<p2z>/scripts:<p2z>/../paper-fetch/scripts:$PATH"`（skill 装在一起，彼此是兄弟目录）。入口名不同，不会撞。
- 脚本开头一律 `#!/usr/bin/env -S uv run --quiet --script`；入口和每个脚本在 git 里都是可执行的（`100755`）。

### 1.3 写在命令后面的东西

- 命令要处理的东西写在后面，不用选项：条目、文件、目录、记录、交接单、搜索词。
- 每个 skill 在自己的 spec 里写明它的东西怎么指定（p2z 见 2.1、2.2）。通用的只有三条：
  - 后面写的东西既可能是文件、也可能是别的（如 `export` 收条目或记录文件）时，写法像路径的（含 `/`，或以 `.json`、`.jsonl`、`.pdf`、`.bib`、`.md` 结尾）才当路径；只收文件的命令，后面写的都是路径。路径不存在，报 `file_not_found`，不当别的东西去查。"文件"包括目录。后面写的不会是文件的命令（`mkcol` 的集合路径、`search` 的搜索词）不受这条影响，含 `/` 也照它本来的意思读。
  - 写在后面的东西以 `-` 起头时，用 `--` 隔开。
  - 一个要处理的东西命中好几样时，把候选都列出来，退出 1，不做交互式选择。
- `-` 代替一个文件，内容从标准输入来。短词表里每一行写明它的 `-` 读的是哪一种：
  - **清单**：一行一样东西。一行可以是一个值，也可以是我们自己输出的一行 JSON，取其中标识那样东西的字段（每个 skill 写明是哪个；p2z 的条目是 `key`，没有 `key` 时取 `cite`）。
  - **路径清单**：一行一个路径（读记录、结果文件的命令）。
  - **文档**：整份内容（.bib、笔记正文、框的清单）。
- 不写 `-` 就不读标准输入：agent 的环境里，没接管道时标准输入可能一直开着，命令会挂住。

### 1.4 选项

- 一个字母一个意思，全系统统一：

  | 字母 | 意思 |
  |---|---|
  | `-h, --help` | 帮助 |
  | `-n, --dry-run` | 空跑：只列出会做什么 |
  | `-o, --output` | 输出到哪；不给就写标准输出（能写标准输出的命令）。给的是目录时以 `/` 结尾 |
  | `-a, --all` | 连同平时略去的 |
  | `-r, --recursive` | 连同下层 |
  | `-f, --force` | 强制（不表示"文件"） |
  | `-i` | 原地写回（像 `sed -i`） |
  | `-t, --to` | 转成哪种格式（pandoc 的写法） |

  不加 `-v`、`-q`、`-V`：没有命令需要。
- 一个长选项名在全系统只有一个意思：`--collection` 只表示"只看这个集合"（筛选），换掉集合的选项另起名（p2z：`--set-collection`）；`--version` 只表示打印程序版本，没有命令需要就不出现（paper-fetch 拿它表示论文版本的那三处，铺开时改名 `--as`）。
- 一个选项只带一个值，要多个就重复写：`--add-tag A --add-tag B`。一个选项后面能跟好几个值时，会把写在后面的东西也吞进去：`--add-collection X 8YVIJGWV` 会把 `8YVIJGWV` 当成第二个集合。
- 选项和写在后面的东西可以交错写（`tag K1 -n K2`）。长选项可以写唯一的前缀（GNU 的惯例）。
- 搜索词写在后面，几个词合成一个查询：`search speckle reduction` 和 `search "speckle reduction"` 一样。

### 1.5 输出和退出码

- 输出记录的命令：标准输出一行一个 JSON，每条记录自己的状态和提示留在那一行里（`{key, code, hint}`）。产物是文档的命令（BibTeX、Markdown、给另一个命令读的 TSV、给 `update -` 读的改动清单）把文档原样写到标准输出或 `-o`；文档里放不下的——某个条目没找到、某个文件读不了——写在标准错误的汇总里，退出 1。
- 标准错误只放读的人需要、标准输出又放不下的：跑上好几分钟的任务的进度（paddleocr 解析时的那几行），影响结果的警告（vllm-serve 的"上一次启动失败过"）。
  - 全做完了（退出 0）：不打汇总，不打例行步骤的日志。条数用 `wc -l` 数，每条的状态在它那一行里。p2z 的命令没有长任务，所以全做完时标准错误是空的。
  - 没全做完（退出 1）：最后打一行汇总。
  - 整个命令做不下去（连不上 Zotero、本地 API 没开、配置缺了）：标准错误最后一行是一个 JSON `{code, hint, …}`，退出 2。已经做完的记录照旧留在标准输出，没做的每条一行 `code: not_run`。
  - p2z 成功路上的日志（"named more than once"、"reusing" 之类）去掉，或者并进那条记录的行里。
- 退出码：0 做完；1 有要处理的（某条没找到、有歧义、要人定、有一条失败）；2 做不下去。搜东西的命令一条都没搜到是 1，学 `grep`；列表为空是 0，学 `ls`。
- 下游关掉管道（`| head`）后：不再打印，不报错；命令照常做完，退出码照常。写东西的命令不会做到一半停下。

### 1.6 帮助

- `-h` 是 man 页的样子：用法行、做什么、选项、退出码、一两个例子。用法行里的命令名是用户敲的那个（`p2z.py search`），不是脚本文件名。带子命令的，每个子命令有自己完整的帮助。
- `-h` 不连 Zotero、不读配置也能打出来。

### 1.7 SKILL.md 和 brief 里写一次的

- 带 PATH 的那一句，和它为什么单独成一句。
- 标准错误要留着：例行的东西不往那里写，出错时它说哪里出了错。例子都不带 `2>/dev/null`。
- 例子只写 `<入口> <短词> …`，不写 `cd`、`uv run`、`../<skill>/scripts/…`。
- 派 subagent 的模板里放填好绝对路径的那一句（"Start every shell call with: …"），brief 引用它，不写"from the skill's directory"。

### 1.8 约定检查

整个仓库一份（仓库根目录的 `tests/`，开发时跑，不随 skill 安装），一次查所有 skill。还没铺开的 skill 列在检查自己的名单里，铺开一个划掉一个。字母表从 `docs/design-principles.md` 里读，不在代码里另写一份。

- **静态**（只读代码）：
  - 脚本开头那一行；git 里的可执行位；
  - 字母只按 1.4 的表用；长选项不用已经去掉的名字（p2z：`--q`、`--key`/`--cite`、`--batch`、`--out`、`--tags-file`，以及当筛选以外意思用的 `--collection`）；没有一个选项带多个值；
  - 入口的短词表里每一项对得上存在的脚本，每个脚本都有短词对着；
  - 提示和帮助里不出现脚本文件名、去掉的选项。
- **运行时**（对着测试用的假 Zotero）：
  - 每个短词的 `-h` 在不连 Zotero、没有配置时退出 0，含用法行、退出码和例子，用法行是 `<入口> <短词>`；
  - 一个处理多条的命令全成功时（如 `trash -n K1 K2`），标准错误为空；
  - 输出超过管道缓冲（64 KiB 以上）的命令接 `| head -1`，标准错误为空、退出码照常；
  - 连不上 Zotero 时，标准错误最后一行是 `{code: zotero_unreachable, …}`，退出 2。

## 2. p2z 的具体规定

### 2.1 条目怎么指定

- 写的是一个值：它是哪个条目，只看 `key` 或 `citationKey` 和它完全相同的条目（全部条目，不只顶层）；正好一条就用它，没有报 `not_found`，几条（比如它是一个条目的 key，又是另一个条目的引用键）报 `ambiguous` 并列出候选，退出 1。不按长相猜是 key 还是引用键，两种都查（本机实测：快速搜索按 key 和 `citationKey` 都能精确命中；921 个条目都有引用键、没有重复）。一次查几个时成批地查，由实现定。
- 附件、笔记在 Zotero 里本身就是条目，有自己的 key：
  - 收它们的命令：`items`（读它们自己的数据）、`children`（附件下面的注释）、`trash`（清理附件）、`update`（`retitle` 打出的是附件的 key）、`tag` 的标签选项（Zotero 允许给附件打标签）、`annotate`（PDF 附件）、`note take`（笔记）。
  - 只对顶层条目有意义的命令（`merge`、`export`、`lint`、`pdf`、`package take`、`tag` 的集合选项）收到附件或笔记的 key：报 `not_a_parent`，给出它的 `parentItem`，退出 1。
- `note take` 写的 key 是笔记就取这条笔记，是条目就取它下面的笔记：按 key 查出类型就知道（本机实测笔记返回 `itemType: note` 和 `parentItem`）。

### 2.2 集合怎么指定

- 凡是指定集合的地方都认 key、`collections` 打出的路径（`自然图像/Diffusion`）和唯一的名字：选项（`--collection`、`--add-collection`、`--remove-collection`、`--set-collection`）、导入记录里的 `collection`、改动清单里的集合字段、`mkcol` 的上级。
- 写的值按 key、完整路径、名字三样去对：只对上一个集合就用它；对上几个就报 `ambiguous`，列出各自的 key 和路径，退出 1，不替人挑。本库：`自然图像/Diffusion` 只对上一个；`Diffusion` 既是顶层那个的完整路径，又是 `自然图像` 下那个的名字，所以报两条路径（用户选 A 时看过的例子就是这样）；这时顶层那个用它的 key 写。
- `--collection` 只看这一个集合本身；要连下层，加 `-r`（`items`、`search`、`lint`、`export` 都一样）。
- `mkcol 上级/新名字`：上级照上面的规则找，最后一段是新名字；只写一个名字就在顶层建；整条路径已经有了就算已有（和现在一样，不建第二个）。

### 2.3 改东西的命令（`tag`、`update`）

- 命令行上给了改动（`update` 的 `--set`、`--patch`；`tag` 的 `--add-*`、`--remove-*`、`--set-*`）：写在后面的东西和 `-` 都是条目清单，取 `key`。所以 `p2z.py search X | head -3 | p2z.py tag -n --add-tag method/diffusion -` 能直接用。
- 没给改动：写在后面的是改动清单文件，`-` 是改动清单：一行一个 JSON，用 `key` 或 `cite` 指明条目，带上要改的内容。`fill`、`retitle` 打出的正是这种行：`p2z.py fill <结果>… | p2z.py update -n -`。
- 改动清单里有一行带 `itemType` 或 `version`（那是条目行，不是改动行）：报 `item_line`，提示改动要写成选项，什么都不写，退出 1。

### 2.4 短词表

都是一个英文单词。"`-` 读"一栏按 1.3：清单、路径清单、改动清单、文档。

| 短词 | 脚本 | 写在后面的（`-` 读） | 主要选项 | 为什么用这个词 |
|---|---|---|---|---|
| `items` | read_library items | 条目…（清单） | `-a` 连附件和笔记；`--collection`、`-r`、`--tag`、`--since-version` | 不写条目也不写筛选时退出 2，提示写条目、`-` 或筛选：空变量（`items $(…)`）会把整个库带摘要倒出来 |
| `search` | read_library search（新） | 搜索词 | `--all-fields`、`--everything`；`--collection`、`-r`、`--tag`、`--since-version`；`-a` | 模式照 Zotero 界面的叫法（All Fields & Tags、Everything）；`--fields` 会读成"挑输出字段" |
| `children` | read_library children | 条目…（清单） | | |
| `pdf` | read_library pdf | 条目…（清单） | | 取路径时用 `select(.exists)`，SKILL.md 的例子这样写 |
| `collections` | read_library collections | | `-a` 连回收站里的 | 默认就是现在的 `--tree`（带 `path`）；回收站里的用 `-a` 照样列得出 |
| `tags` | read_library tags | | `--min-count N` | |
| `schema` | read_library schema | | | |
| `ready` | ready | | `--dir`、`--authorize`、`--timeout` | |
| `draft` | draft_item | 结果文件…（路径清单） | `-o DIR/`、`--redraft`、`--automatic-tags` / `--no-automatic-tags` | |
| `prepare` | 入口里（have + check） | 记录…（路径清单） | `-n` | 入口先把 `-` 读成路径，再交给两个脚本 |
| `save` | 入口里（create + attach） | 记录…（路径清单） | `-n` | 同上 |
| `have` | find_in_library | 记录或文件…（路径清单） | `-n` | "库里有没有"：记录查这篇论文，其余文件按 md5 查；读得成记录的是记录。`lookup` 会读成查元数据，`find` 会读成查文件 |
| `check` | check_item | 记录…（路径清单） | `-n` | |
| `create` | create_item | 记录…（路径清单） | `-n` | |
| `attach` | attach_file | 记录…（路径清单） | `-n` | `-h` 写明"按记录附文件"；给已有条目补 PDF 走导入 |
| `recognize` | recognize | 记录…（路径清单） | `-n`、`--wait S` | |
| `answer` | answer | 交接单 回答 | `--key K`（这条回答指向的候选条目）、`--reason`、`--by` | |
| `report` | report | 记录…（路径清单） | `--json` | |
| `ids` | read_bib | .bib 文件…（文档） | | 打出 `<DOI 或 arXiv id><TAB><引用键>`，给 paper-fetch 的 `identify` 读；`bib` 会读成导出 |
| `lint` | lint_items | 条目…（清单） | `--collection`、`-r` | |
| `update` | update_item | 见 2.3 | `--set F=V`、`--patch FILE`、`-n` | |
| `tag` | file_and_tag | 见 2.3 | `--add-tag`、`--remove-tag`、`--add-tags-file`、`--set-tags-file`、`--add-collection`、`--remove-collection`、`--set-collection`（各带一个值，可重复）、`-n` | `-h` 写明管标签和集合。"换掉"的选项都叫 `--set-*`：现在的 `--collection`（集合换成只剩这一个）和 `--tags-file`（标签换成这一组）会被当成筛选或导入时的标签文件，误删 |
| `merge` | merge_items | 要并掉的条目 | `--into 留下的条目`、`-n` | 读作"把 X 并进 Y"；留下的那条单独点出，写反了也不会把它扔进回收站（像 `mv -t`；用户选 A） |
| `trash` | trash_item | 条目…（清单） | `--restore`、`-n` | `rm` 像删除，回收站能恢复 |
| `mkcol` | make_collection | `上级/新名字`（见 2.2） | `-n` | `mkdir` 会让人带 `-p`、写文件路径 |
| `fill` | fields_from_results | 结果文件…（路径清单） | `-o`（不给就写标准输出） | 产物是改动清单（文档，1.5），接 `update -`：标准输出只有改动行，没东西可补的结果不出行，读不了的结果写在标准错误、退出 1（现在的每个结果一行状态和汇总去掉）；`fields` 会读成"列字段" |
| `retitle` | titles_from_labels | 目录 | `-o`（不给就写标准输出） | 同 `fill`；`titles` 会读成"列标题" |
| `export` | export_bib | 条目…（清单）或记录… | `--collection`、`-r`、`-o` | |
| `note` | note | `take 条目或笔记`、`put 文件…`（`-` 读文档）、`list [条目…]`、`search 词 [条目…]` | `take`：`-o DIR/`、`--title`；`put`：`-i`、`-n`；`list`、`search`：`--collection` | `search` 照样能限定在某篇论文或某个集合里 |
| `convert` | note_md | 文件…（文档） | `-t md\|note`、`-o` | `md -t md` 读着像"md 转 md" |
| `package` | structured | `take 条目…`、`put 目录…`、`names [条目…]` | `take`：`--title` / `--every` / `--missing`、`-o DIR/`；`put`：`-n` | 文档和 `pdf` 的字段都叫 package；`-h` 写明"PDF 的解析包" |
| `annotate` | annotate | PDF 附件、框的清单文件（`-` 读文档） | `-n` | |

## 3. 读库内部的减法

不改用法，只删用不着的代码。依据 `existing-tools.md`，本机 Zotero 10.0.7 上验证过：

- 读库的列表一次请求拿全部：本地 API 不带 `limit` 就返回全部（实测 921 条，`Total-Results` 也是 921）。`--limit` 去掉，要前几条用 `| head`（`head` 只是截断打印，请求还是一次）。共用的 `pages()` 还有别的用处（按 50 个 key 一组取条目、按 md5 找到就停），这些不在本节里动。
- 去掉"扫全库"那一步：快速搜索按 `citationKey` 精确命中。删之前先对一遍：拿库里每个引用键，走和命令一样的编码（`+` 编成 `%2B`）搜一次，全都命中自己那一条再删。
- PDF 路径从 `/file/view/url` 取（实测直接给 `file://` 地址，不存在的 key 是 404），Windows 路径照旧经 `wslpath` 转。
- 去掉 `children` 防"不认识的 key 返回整个库"的过滤：实测不存在的 key 和附件的 key 都返回空列表。
- `pdf` 找不到磁盘上的文件时，标准错误里多打的那一行去掉：每行已经带 `exists: false`。
- Better BibTeX 和 pyzotero 的命令行不换进来：前者遇到重复引用键默默取第一个，后者没有引用键寻址和 PDF 路径。

## 4. 要跟着改的

- **p2z 的共用代码**（`p2zlib/cli.py`、`zotero.py`）：2.1 的条目解析、2.2 的集合解析、2.3 的两种读法、1.3 的路径和 `-`、1.5 的输出（汇总只在退出 1 时打，整命令报错写标准错误最后一行，空跑也一样，做不完的记 `not_run`，成功路上的日志去掉）、管道关掉后照常做完（所有脚本的 `__main__` 和入口都套上同一层：接住 BrokenPipeError，把标准输出接到 `/dev/null`，往下做）、选项交错写（`parse_intermixed_args`；带子命令的脚本由入口定好子命令，按子命令单独解析；`--base-url` 挂到每个子命令上）、一个选项一个值。25 个脚本里 22 个走这里。
- **p2z 的入口** `p2z.py`：短词表；`-h` 列短词，作用那一句取自表；`prepare`、`save` 各自的帮助；`-` 读成路径再交给两个脚本；执行脚本前设一个环境变量告诉它用户敲的命令名，`cli.parser` 用它当用法行里的名字。
- **p2z 的脚本**：各自的选项按 1.4 和 2.4 改；`fill`、`retitle` 不给 `-o` 时写标准输出，标准输出只放改动行；条目解析的报错代码 `cite_not_found`、`cite_ambiguous` 改成 `not_found`、`ambiguous`（paper-read `index_heading.py` 的说明、p2z 的提示里提到它们的地方跟着改）；帮助按 1.6 改，带子命令的把模块说明拆到各子命令；所有提示（约 96 处 hint）和帮助里的例子换成新写法；`answer.py` 补上可执行位。
- **p2z 的文档**：SKILL.md 和 `references/` 里所有调用；1.7 那几条写进 SKILL.md；四份 brief（`same-paper-judge.md`、`recognizer-judge.md`、`tidy-judge.md`、`tagging.md`）的调用写法和派发模板。
- **paper-read**：`prepare_note`、`index_heading`、`put_note` 调 p2z 的地方改成新短词；整命令报错从标准错误最后一行读 `code` 和 `hint`（SKILL.md 第 39、46 行那两处跟着改）；`put_note` 跑 paddleocr 的 `doc.py` 时照旧经 uv；测试替身 `fake_p2z` 跟着改（它兼当 `PAPER_READ_DOC`，没有开头那一行）；SKILL.md 里提到 p2z 命令的几处（如第 40 行的 `read_library pdf --help`）。paper-read 自己的命令不动。
- **paper-fetch**：SKILL.md 第 192 行、`scripts/claim.py` 第 20 行的帮助和 `tests/test_claim.py` 第 161 行里的 `find_in_library --file` 改成 `p2z.py have`；`references/attachment-titles.md`、`references/batch.md` 里提到 p2z 命令的地方。paper-fetch 自己的命令不动。
- **测试**：p2z 和 paper-read 的测试换成新写法：用 `lines[-1]` 取汇总的约 57 处、在标准输出里断言整命令错误码的那些、`helpers.py` 里的开头一行常量和 `smoke()`、`test_p2z.py` 里断言命令列表的那条。
- **仓库**：根目录新加 `tests/`，放 1.8 的约定检查；README 的目录说明加上它。
- **不改**：`docs/specs/` 里已冻结的旧 spec；开着的 issue 里提到旧命令的，用到时再改。

## 5. 验收

- p2z、paper-read、paper-fetch 的测试全过；约定检查全过（只查 p2z，其余四个在名单里）。
- 本机只读实测（真库）：
  - `p2z.py search POCUS | p2z.py pdf - | jq -r 'select(.exists) | .path'` 列出那几篇的 PDF；
  - `p2z.py items --collection 自然图像/Diffusion | head -3` 取对集合；`p2z.py items --collection Diffusion` 报两条路径、退出 1；
  - `p2z.py tags | head -1` 标准错误为空、退出 0；
  - 把地址指到一个没人用的端口（`PAPER_TO_ZOTERO_BASE_URL=http://127.0.0.1:9 p2z.py tags`，不用关 Zotero）：标准输出为空，标准错误最后一行是 `zotero_unreachable`，退出 2。
- 实测写入：用户指定一篇论文，走完整的导入（`ready`、`draft`、`prepare`、`save`、`report`），再做一次 `tag -n` 和用户点头后的 `tag`。论文由用户定，写入要用户点头。
- p2z 的文档变短：SKILL.md 加 `references/` 现在 554 行，改完要更短；脚本现在 7,596 行，删掉的（翻页、扫全库、`--batch` 的另一套读法、汇总）抵得过加上的，不变长。
- p2z 的文档里没有 `cd`、`uv run`、`2>/dev/null`。
- 用一阵之后：重跑 `usage.py`，看 p2z 的调用里 `cd`、`2>/dev/null`、接 heredoc 的 Python 是否消失，新写法出错几次，用之前查 `-h` 几次；结果写进 issue，再决定铺开。

## 6. 规则文字（用户已同意，已改）

照原则 §4 的流程改：草稿经 advisor 审，原则那一节给用户看了简要版和 `git diff`，AGENTS.md 那一条给用户看了原文和修改建议，用户同意；全面复查时又改正两处（认路径的规则只管"后面可能是文件也可能是别的"的命令；AGENTS.md 只管文档或入口会运行的脚本，不管被导入的模块），用户也同意了。

- `docs/design-principles.md` §3 *The Unix/Linux philosophy*：第 1 节里必须遵守的规矩改写成英文并进来，和原有的要点合成一份：入口和短词（含"别的 skill 的代码按路径执行入口"）、带 PATH、写在后面的东西和 `-`、字母表、一个选项一个值、一个名字一个意思、输出和退出码、帮助。原文"`-f` file or force"改成只表示强制；"a closing summary goes to stderr"改成"只在没全做完时"；标准错误留给长任务的进度和影响结果的警告（paddleocr、vllm-serve 要用）。做法上的东西不进原则：约定检查放在哪、怎么跑，实现时写进 AGENTS.md；SKILL.md 和 brief 里写一次的那几句（1.7）、每个命令的 `-` 读哪一种，写在各 skill 自己的文档里。约定检查从原则里读字母表，原则里注明了"one letter per row"。
- `docs/design-principles.md` §4 *Skill text*：「examples simply use `uv run`」改成例子用入口和短词。
- `AGENTS.md`：文档或入口会运行的每个脚本（包括入口）开头加 `--quiet`；可执行位改成必须：文档经 PATH 调入口，其余脚本在同一个 PATH 上。
- `README.md` 第 39 行改成指向原则 §3，不另写一份。
- `docs/design-principles-sources.md` 记了用户这次的原话。

## 7. 和设计原则的对照

- **§3 The Unix/Linux philosophy**：写在后面的东西、`-`、标准输出只放数据、惯例的字母、man 页的帮助、以文件为本（改动清单、记录、交接单都是文件），都照它做。
- **§3 Remove a step before automating it**：`--limit` 换成 `| head`；集合认路径，省掉先查 key；`-` 认我们自己的 JSON 行，省掉中间挑字段；`--add-tag` 省掉先写一个标签文件；读库去掉翻页和扫全库。
- **§3 General and simple, never patched**：条目、集合各一条解析规则，所有命令共用；改动集中在共用代码。不为没遇到的问题加东西：不加 `-v`/`-q`/`-V`。
- **§3 Cut where it pays（每条知识一个出处）**：全系统约定只在 design-principles §3；约定检查全仓库一份，字母表从原则里读。
- **§3 A standard where cases share a shape**：只统一真的同形的部分（字母、写在后面的东西、输出通道、帮助的段落）；各命令自己的选项照旧。
- **§3 Reuse decided by comparison**：比过 Better BibTeX、pyzotero 命令行、papis、pubs；读库留在本地 API 上做减法，命令组织学 papis、pubs。
- **§3 Checks that can fail**：约定写成检查；管道那条用超过缓冲的输出，没修好就过不了。
- **§1 The boundary is the script's certainty**：条目不按长相猜，key 和引用键两种都查、只认完全相同的；集合、条目命中几样就列候选交出去。
- **§3 A redesign is measured by the skill getting shorter**：p2z 的文档要变短，脚本不变长。
- **§2 Review before building**：三路审阅改过一轮，再经 advisor 给用户。
- **偏离和理由**：
  - 列东西的短词用名词，不是动词：像 `git tag`，比硬凑动词好懂（用户同意用合适的词）。
  - `answer` 留着 `--key`：它指的是这条回答针对的候选，不是要处理的东西。
  - `merge` 留下的那条用 `--into` 点出，不写在后面：两条角色不同，写反就把该留的扔进回收站（用户选 A）。
  - 原则里"结尾的汇总写标准错误"和"成功时不出声"互相顶着，这里按"没有话就不说"解开：只在没全做完时打汇总。

## 8. 待用户定的

1. ~~PATH 那一句的写法~~：已定，`set -o pipefail; export PATH="…/scripts:$PATH";`（1.2）。
2. ~~`merge` 怎么写两个条目~~：已定，并掉的写在后面，留下的用 `--into`（2.4）。

两个问题都定了，第 6 节的规则文字也已同意。
