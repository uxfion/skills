# vllm-serve 对接 Unix 约定

- 日期：2026-11-06（草稿 2026-11-05）。状态：已冻结（2026-11-09）。用户于 2026-11-06 同意了 §3 补的几处（issue 第 14 条）和实施计划；实施及收尾已完成，实施时的更正记在本 spec。
- 来源：[Unix 约定 issue（已归档）](../issues/archive/20261104-skills-unix-conventions-fixed.md)（「铺开到其余 skill 时」那一节的步骤）。约定只有一个出处：`docs/design-principles.md` §3 *The Unix/Linux philosophy*，这里只写 vllm-serve 自己的：短词、东西怎么指定、`-` 读什么、要跟着改的地方。样板是 paper-to-zotero（[冻结的 spec](20261104-skills-unix-conventions-spec.md)）。
- 范围：一遍约定整理。服务怎么起、怎么等、怎么共用、怎么空闲自停都不动；profile 文件、状态文件、日志、锁都不动，所以新旧两份 `serve.py` 认得对方起的服务。字段的改动都在第 5 节：`up`、`down` 每行带 `code`，报错的 `error` 改名 `code`、多一个 `hint` 说下一步。
- 落地：第 1 批，和 paper-fetch 一起；paddleocr `parse.py` 里调 vllm-serve 的那一处跟这一批一起改（第 6 节）。

## 1. 改完是什么样

用得最多的三个（[`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料)，本仓库里的调用；真项目里那 17 次 `serve` 多半是读 `serve.py` 源码和一个项目自己的部署脚本，不是命令）：`status` 40 次（26 次接了管道，多是 `| grep <profile>`、`| head -1`），`up` 29 次，`down` 26 次。

开头那一句（之后每个例子都省略）：

```
set -o pipefail; export PATH="<vllm-serve 目录>/scripts:$PATH";
```

要一个服务：

```
# 现在
cd <vllm-serve 目录> && uv run scripts/serve.py up paddleocr-vl
#   → {"profile": "paddleocr-vl", "url": "http://127.0.0.1:8118/v1", "model": "…", "started": false}
# 改后
serve.py up paddleocr-vl
#   → {"profile": "paddleocr-vl", "code": "ok", "url": "http://127.0.0.1:8118/v1", "model": "…", "started": false}
```

这一次换卡、加 vLLM 参数：

```
# 现在
CUDA_VISIBLE_DEVICES=4,5 uv run scripts/serve.py up qwen38-27b -- --data-parallel-size 2
# 改后
CUDA_VISIBLE_DEVICES=4,5 serve.py up qwen38-27b -- --data-parallel-size 2
```

看一个 profile：

```
# 现在
uv run scripts/serve.py status | grep paddleocr
# 改后
serve.py status paddleocr-vl
```

停：

```
# 现在
uv run scripts/serve.py down paddleocr-vl
uv run scripts/serve.py down --all
# 改后
serve.py down paddleocr-vl
serve.py down -a
serve.py status | jq -c 'select(.phase == "running" and .idle_for_minutes >= 30)' | serve.py down -
```

起不来时：

```
# 现在：标准输出 {"error": "port_busy", "detail": "port 8118 is held by profile x's server …"}，退出 2
# 改后：标准输出 {"profile": "paddleocr-vl", "code": "port_busy", "detail": "port 8118 is held by profile x's server",
#                 "hint": "serve.py status names it: use that profile, or down it once idle"}，退出 1
#       没有 vLLM 时：标准输出为空，标准错误最后一行 {"code": "vllm_missing", "detail": "…", "hint": "…"}，退出 2
```

共享服务器上（经 ssh，按路径跑入口，理由在第 8 节）；筛选在本机这一侧：

```
# 现在
ssh <host> '. <root>/env.sh && uv run <root>/vllm-serve/scripts/serve.py status'
# 改后
ssh <host> '. <root>/env.sh && <root>/vllm-serve/scripts/serve.py status'
ssh <host> '. <root>/env.sh && <root>/vllm-serve/scripts/serve.py status' | jq -c 'select(.phase == "running" and .idle_for_minutes >= 30)' \
  | ssh <host> '. <root>/env.sh && <root>/vllm-serve/scripts/serve.py down -'
```

## 2. 短词表

入口名留 `serve.py`（第 8 节）。

| 短词 | 做什么 | 写在后面的（`-` 读） | 选项 | 为什么用这个词 |
|---|---|---|---|---|
| `up` | 起一个 profile 的服务（已在跑就直接用），等它能应答，打一行地址 | 一个 profile；`--` 之后是这一次的 vLLM 参数 | | 照 `docker compose up`：没在跑就起，在跑就用；`start` 读着像"一定新起一个" |
| `down` | 停 profile 的服务，不管在哪个阶段，每个最多等 90 秒 | profile…（`-` 读清单） | `-a, --all` | 和 `up` 成对 |
| `status` | 列 profile：阶段、地址、谁起的、哪几张卡、负载、空闲多久、上次怎么结束、日志在哪 | [profile…]，不写就是全部 | | 列东西用名词，像 `git status` |

- 三个短词都在入口里做完，不另开脚本：表里每项的脚本一栏是 `None`，像 p2z 的 `prepare`、`save`。`WORDS` 写成模块顶层的字面量，约定检查读得到。
- 不是短词：`_supervise`，`up` 起守护进程时自己调的（第 8 节）。
- 没有去掉的命令。

## 3. 东西怎么指定

- **profile 按名字指定**（`paddleocr-vl`）：先找 `~/.config/vllm-serve/profiles/<名字>.toml`（`XDG_CONFIG_HOME` 改得了），再找 skill 的 `profiles/`。从不当路径读：这几个命令后面写的都不会是文件，§3 认路径那条不管它们，名字里带 `/` 照样是 `unknown_profile`。
- **`up`**：正好一个 profile。`--` 之后的都原样交给 `vllm serve`，只管这一次启动（和现在一样）。`--` 前面多写的东西是用法错误，提示 "vLLM arguments go after `--`"：`up X --max-model-len 8192` 现在就报"unrecognized arguments"，没说该怎么写；`up X extra` 现在会悄悄把 `extra` 当成一个 vLLM 参数。做法：解析之前先在第一个 `--` 处把命令行切成两半，左半边照常解析（选项和 profile 可以交错），右半边原样交给 vLLM。argparse 自己守不住这条（3.11–3.13 上 `up p1 extra` 和 `up p1 -- extra` 都得到 `vllm_args: ['extra']`，`up -- p1` 得到 `profile: p1`）；切开以后 `up -- p1` 左边没有 profile，是用法错误。`_supervise` 收到的本来就是 `"--", *extra`（`serve.py:506`），同一处切分也给它用。
- **`down`**：一个或几个 profile。`-` 读清单：一行一个 profile 名，或者我们自己打出的一行 JSON（`status`、`up`、`down` 的行），取 `profile` 字段。缺 `profile` 的 JSON 行照原则 §3：报失败的（`code` 既不是 `ok` 也不是 `skipped`）原样转到标准输出、算没做完、退出 1，`skipped` 的原样转出、算跳过，别的什么都不做、退出 2（`invalid_list`，照 p2z）；对 `down -` 几乎碰不到，`status`、`up`、`down` 的行都带 `profile`。`-` 读到空清单是没事可做，退出 0；后面什么都没写、也没有 `-a`，是用法错误，退出 2，空的 `$(…)` 不会停掉全部。`-a` 停配置里的和正在跑的全部，不和 profile 一起写。
- **`status`**：不写就列全部（配置里的 profile 加上正在跑的），像 `ls`（第 8 节）；写了就只列这几个。不读 `-`：要列哪几个，名字直接写在后面。
- 为什么 `down` 收 `-`、`status` 收 profile：`status` 的行带 `profile`，"把空闲的停掉"就是 `status | jq 筛 | down -`，不用另加筛选选项；`status` 接到 `grep`、`head` 上挑一个 profile 是最常见的用法，名字写在后面就省掉这一步。

## 4. 选项

[`usage.md`（历史材料，结项记录）](../issues/archive/20261104-skills-unix-conventions-fixed.md#参考资料) 不按 skill 分开数选项；issue 里 `--all` 那 7 次是几个 skill 合起来的。vllm-serve 现在的全部选项和位置参数：

| 现在 | 改后 | 说明 |
|---|---|---|
| `-h, --help` | `-h, --help` | 改成 man 页：`serve.py -h` 列短词，加上 profile 的键、状态和日志放在哪、退出码；`serve.py <短词> -h` 是那个短词的用法行、做什么、选项、输出的字段、退出码、例子。不读配置，不碰服务 |
| `down --all` | `down -a, --all` | 字母表里 `-a` 的意思（连同平时略去的）：平时只停写出来的，`-a` 连其余的一起停。`--all` 照旧能用 |
| `up PROFILE [vllm_args…]` | `up PROFILE [-- VLLM参数…]` | vLLM 参数只认 `--` 之后的 |
| `down [PROFILE]` | `down PROFILE…`、`down -` | 第 3 节 |
| `status` | `status [PROFILE…]` | 第 3 节 |

- 长选项照 GNU 惯例写唯一前缀也认（`--al`），选项和 profile 可以交错写。
- 环境变量照旧：调用方的环境（`CUDA_VISIBLE_DEVICES` 选卡）照样传给服务；`VLLM_SERVE_VLLM` 指定 vllm 可执行文件；`XDG_CONFIG_HOME`、`XDG_STATE_HOME`。
- 不加别的字母：没有命令要空跑（`down` 会停哪些，`status` 已经列出来）、要写文件（`-o`）、要安静或啰嗦（`-q`、`-v`）。

## 5. 输出和退出码

**退出的规则**（样板 spec 第 9 节和 p2z 的代码，四个 skill 一样）：退出 1 是命令处理的那样东西出了问题（这里是一个 profile：不存在、写坏了、给不出服务），写在它自己那一行里，在标准输出上；处理几样东西的命令再在标准错误最后打 `{"summary": …}`，只处理一样的不打。退出 2 是调用本身、或者命令要往下做所需的东西出了问题（用法错误、读不了的输入、没有 vLLM、状态目录不让写）：标准错误最后一行 `{code, hint}`；处理几样东西的命令（`down`），已经做完的行留在标准输出，没做的每样一行 `code: not_run`，只处理一样的（`up`）标准输出为空。

**字段的改动：**

- `up`、`down` 做事，每行带 `code`：成功是 `ok`，出了问题是问题的代码。`status` 的行是列表，照旧不带，只有写坏的 profile 那一行带。
- 报错只改一个名字：`error` → `code`。`detail` 照旧说看到了什么（谁占着端口、日志在哪和它最后 20 行、哪个登录起的），另加一行 `hint` 说下一步做什么（§3：每条记录带自己的提示，整命令报错是 `{code, hint, …}`；p2z 也是 `detail` 说情况、`hint` 说怎么办）。现在 `detail` 里已经写着下一步的那半句挪进 `hint`，不添新内容：

  | `code` | `hint` |
  |---|---|
  | `unknown_profile` | 写成 `detail` 列出的某个 profile，或照 `detail` 修好那个文件 |
  | `port_busy` | `serve.py status` 说出是谁：用那个 profile，或等它空闲后 `down` 它 |
  | `server_failed` | 读日志（`detail` 里有路径），再看 install.md 的 *A server that does not start* |
  | `not_permitted` | `down` 的行：那个登录停它，或等它空闲自停；`up` 的标准错误：文件的主人用 `chown -R` 交过来 |
  | `vllm_missing` | 照 install.md 装 vLLM（`VLLM_SERVE_VLLM` 设了时，它指的文件不对） |
  | `still_stopping` | `serve.py status <profile>` 看它什么时候没了 |
  | `invalid_list` | 照 p2z |
  | `usage` | 照 p2z：`See serve.py <短词> -h.`；`--` 前多写了东西的那一种例外，说 "vLLM arguments go after `--`"（它说的是一个参数该怎么写） |

- `down` 的 `stopped`、`phase` 两个字段换成 `code`（下面）。
- `VLLM_SERVE_VLLM` 指着一个不存在的文件时，`up` 当场报 `vllm_missing`；现在要等守护进程起来再失败，报成 `server_failed`。照上面的规则这是调用的问题；约定检查的 `no_service` 也靠它，不用依赖本机 vllm 装在哪（第 7 节）。

**几个命令都一样的：**

- 管道被下游关掉（`| head`）：不再打印，不报错，命令照常做完（`down` 照样把每个都停掉），退出码照实。从 p2z `p2zlib/cli.py` 拷 `write`、`emit`、用法错误那几行和读清单的那几行进 `serve.py`，开头注明出处和拷贝时的提交。
- 不认识的短词、用法错误：退出 2，标准错误先是用法或短词清单，最后一行 `{code: usage, detail, hint}`，和 p2z 一样（`hint` 见上表）。

**`up`**（只处理一个 profile，退出 1 时不打汇总）：

| 退出码 | 标准输出 | 标准错误 |
|---|---|---|
| 0 | 一行 `{profile, code: ok, url, model, started}`，有时加 `host`、`differs`、`foreign_cuda`（照旧） | 新起一个服务时有进度：`[vllm-serve] starting … log: …`，接上别人正在起的那个时 `[vllm-serve] waiting for … log: …`；上次启动失败过时的警告 `[vllm-serve] the last start of … failed …`。服务已在跑、直接拿来用时是空的 |
| 1 | 一行 `{profile, code, detail, hint}`：`unknown_profile`、`port_busy`、`server_failed`，都是"这个 profile 这次给不出服务" | 同上（失败前已经打出的进度） |
| 2 | 空 | 最后一行 `{code, detail, hint}`：`vllm_missing`（这台机器上没有 vLLM）；`not_permitted`（状态目录里的文件是别的登录的：`up` 不停任何服务，这个代码只来自读写所有 profile 共用的状态目录，比如那把决定锁）；用法错误 |

- 现在那一行 `foreign_cuda` 的标准错误去掉：同样的库名已经在标准输出那一行里，标准错误只放标准输出放不下的。paddleocr 的 `parse.py` 只取 `url`、`model`，由它把 `foreign_cuda` 转到自己的标准错误上（第 6 节）。
- `[vllm-serve]` 这个前缀留着：paddleocr 把这几行原样转给它的调用方，它的 SKILL.md 第 28 行靠它认出是谁的话。
- 不加新的进度行：等的时候看什么，SKILL.md 已经写了（`status`、日志、`nvidia-smi`）。

**`down`**：每个 profile 一行。

| 行 | 意思 | 现在 |
|---|---|---|
| `{profile, code: ok}` | 停了 | `{profile, stopped: true}` |
| `{profile, code: skipped, reason: not_running}` | 本来就没在跑 | `{profile, stopped: false}` |
| `{profile, code: still_stopping, hint}` | 90 秒后还在停；`status <profile>` 看它什么时候没了 | `{profile, stopped: false, phase: stopping}`，退出 0 |
| `{profile, code: unknown_profile \| not_permitted, detail, hint}` | 没有这个 profile；别的登录起的服务 | `--all` 时 `error` 行、退出 2；一个 profile 时退出 2 |

退出 0：每行都是 `ok` 或 `skipped`，标准错误为空。退出 1：有别的代码，其余照常停完，标准错误最后一行汇总。退出 2：用法错误、`invalid_list`、状态目录读不了。

**`status`**：每个 profile 一行，字段照旧。退出 0：都列出来了，一个 profile 都没有也是 0（像 `ls`），上次启动失败过（`last.failed`）也是 0，那是这一行的内容。退出 1：有一行是 `{profile, code: unknown_profile, detail, hint}`（profile 写坏了，或写出来的名字没有这个 profile），标准错误最后一行汇总；现在这种情况退出 0，容易漏看。所以有 `pipefail` 时，`status | jq … | down -` 这一整行在每个都停好之后也可能是 1，那是 `status` 在说有个 profile 文件坏了（SKILL.md 写明）。退出 2：用法错误。

## 6. 要跟着改的

**vllm-serve 自己**

| 地方 | 改成 |
|---|---|
| `scripts/serve.py:1` | 开头一行加 `--quiet`（可执行位已经有了，`100755`） |
| `scripts/serve.py:6–43` | 模块说明拆开：总的放 `serve.py -h`，各短词的进各自的 man 页（第 4 节） |
| `scripts/serve.py:84–87` 及各处 `Failure(...)`（111、117、121、123、136、138、490、558、561、564、720）、`:803` | `Failure` 多带一个 `hint`（第 5 节那张表）；`detail` 里说下一步的半句挪过去，其余的话不改 |
| `scripts/serve.py:294–304`（`find_vllm`） | `VLLM_SERVE_VLLM` 指的文件不存在或不可执行时返回 None（`vllm_missing`），提示里点出这个变量 |
| `scripts/serve.py:534–544`（`reply`） | 行里加 `code: ok`；去掉 `foreign_cuda` 那一行标准错误 |
| `scripts/serve.py:709–730`（`down`） | 返回 `code: ok`、`skipped`/`not_running`、`still_stopping`，不再有 `stopped`、`phase` |
| `scripts/serve.py:757–805` | `WORDS` 表和分派（`_supervise` 先分出去）；每个短词自己的解析器（选项交错写）；`up` 和 `_supervise` 在解析前于第一个 `--` 处切开（第 3 节）；`down` 的多个 profile、`-`、`-a`；`status` 的 profile；第 5 节的输出通道和退出码；防断管的 `write`、`emit` |
| `SKILL.md:10` | 换成 p2z 那样的 *Calling* 一段：开头那一句（填 skill 目录的绝对路径，只列 vllm-serve 自己）、`serve.py -h` 列短词、`serve.py <短词> -h` 是参考；标准输出是数据，标准错误要留着（不加 `2>/dev/null`）：起服务时的进度、上次失败的警告，退出 2 时最后一行 `{code, detail, hint}` |
| `SKILL.md:15–16、52–53` | 例子去掉 `uv run scripts/`；`status <profile>`；`down` 的几种写法，连同停掉空闲服务的那条管道 `serve.py status \| jq -c 'select(…)' \| serve.py down -`（不写出来，agent 会去猜一个 `down --idle`），并说一句：有个 profile 文件坏了时 `status` 退出 1，有 `pipefail` 的这一整行在每个都停好之后也会是 1。行尾列字段的注释删掉，字段在 `up -h`、`status -h` 里 |
| `SKILL.md:25` | "each error (`{"error", "detail"}`, exit 2)" 改成：一行带 `code`、`detail`、`hint`，退出 1；`vllm_missing`、状态目录的 `not_permitted` 在标准错误最后一行，退出 2 |
| `SKILL.md:43、45` | 第 43 行分开说 `down` 的那一行（别的登录的服务，退出 1）和 `up` 的标准错误（状态目录里别的登录的文件，退出 2）；第 45 行 "an `error` line in `status`" → 带 `code` 的那一行。第 30、38 行的 `detail` 不用改 |
| `SKILL.md:47` | `status` → `status <profile>` |
| `SKILL.md:56` | `load` 各项的说明挪进 `status -h`，这里只留"`nvidia-smi` 看其余"和"`down` 会切断正在用的人"那两句 |
| `references/shared-machines.md:16、54` | ssh 那两处去掉 `uv run`，按路径跑入口；加上停掉空闲服务的那条：两头各一次 ssh，`jq` 在本机这一侧（第 1 节最后一例）。`--all` 照旧能用，不用改 |
| `references/install.md`、`shared-machines.md`、`tuning.md` 的开头 | 这三份都点名了命令（`up`、`down`、`status`），各加一句开头那一句，只列 vllm-serve 自己（"命令照 SKILL.md *Calling* 那样跑：…"）；shared-machines.md 里它管的是 ssh 管道在本机那一侧的 `pipefail`。别的不用改：只点名 `serve.py` 和三个短词，这些都不变。SKILL.md 里读日志的 subagent 的 brief 不点名任何命令，不加 |
| `tests/test_serve.py` | 见第 7 节 |

**paddleocr 里归这份 spec 的：`parse.py` 调 vllm-serve 的那一处和它的测试**（第 1 批，和 vllm-serve 一起落地；paddleocr 的 spec 不再写这一处）

| 地方 | 改成 |
|---|---|
| `scripts/parse.py:203–213`（`serve_up`） | `["uv", "run", serve, …]` 改成 `["uv", "run", "--quiet", serve, "up", VL_PROFILE]`，照 paper-read 调 p2z 的写法。退出 0 和 1：读标准输出最后一行，看 `code`，不看有没有 `url`：`ok` 才用它的 `url`、`model`，别的代码是给不出服务；退出 2：读标准错误最后一行。标准错误一边读一边原样转给自己的标准错误（几分钟的启动进度要让 agent 看见），同时记下最后一行。`code: ok` 的行里有 `foreign_cuda` 时，在自己的标准错误上打一行 `[paddleocr] vllm-serve foreign_cuda: …`。它返回给 `parse.py` 其余代码的样子不变（成功的那一行，或 `{"error", "detail"}`：`error` 取 `code`，`detail` 取 `detail` 加 `hint`），所以 `load_backend`（231–238）不动；这几个内部的名字只在 `parse.py` 里，以后也不用改 |
| `tests/test_parse.py` | 加一条接缝测试：`VLLM_SERVE` 指一个假的 vllm-serve 入口，分别退出 0（`code: ok` 的一行，带 `foreign_cuda`）、1（`port_busy` 的一行，也带 `url`：认的是 `code`）、2（标准错误最后一行 `vllm_missing`，前面有一行进度），`serve_up` 各自返回对，进度和 `foreign_cuda` 都出现在标准错误上 |

**不归这份 spec 的**

- paddleocr 的 `SKILL.md:28`（"`serve.py`（`VLLM_SERVE`，否则 `../vllm-serve/scripts/serve.py`）… `serve.py down paddleocr-vl`"）：归 paddleocr 的 spec（第 2 批）。这一批之后它照样对：入口名和 `down <profile>` 都没变。改成经 PATH 敲时，paddleocr 的开头那一句把 `<paddleocr 目录>/../vllm-serve/scripts` 也放进 PATH，像 p2z 带上 paper-fetch。
- `profiles/paddleocr-vl.toml:1`、`references/install.md:76` 提到 `parse.py`：paddleocr 第 2 批改它的命令名时一起改，这里不动。
- `tests/check_conventions.py`：落地时主 agent 把 vllm-serve 从 `NOT_YET` 拿掉，别的不用改（只有入口一个脚本时的正则修正已经在工作区里）。
- 不改：`docs/specs/` 里冻结的旧 spec；README；AGENTS.md。

**本仓库以外**

- **共享服务器上的副本**（pro6000，2× RTX PRO 6000，`<root>/vllm-serve/`）：要用户点头才做，不是例行步骤（用户 2026-11-06 选 A：第一批验完后先只读检查、再更新）：更新要先停掉那边的服务，那台机器别人也在用。用户同意后照 shared-machines.md 第 4 步：`status` 显示空闲，用旧副本停掉它的服务，`rsync -a` 新目录，在那边跑一次 `serve.py -h`。状态文件格式没变，先停是照那一步的规矩。
- **用户另一个项目里的旧部署包装脚本**：给用户一句话，我们不动——"它按路径加载 `serve.py`、把收到的参数交给 `main()`。入口名和 `main()` 都没变，`up <profile>`、`status`、`down <profile>` 照样能用；但 `up <profile>` 后面不带 `--` 直接跟 vLLM 参数，现在是用法错误，要写成 `up <profile> -- <参数>`。里面改 `STARTUP_TIMEOUT` 的那行早已不起作用。要不要改、这个脚本还用不用，由你在那个项目里定。"

## 7. 约定检查和验收

**`vllm-serve/tests/conventions_fixture.py`**，照 `tests/check_conventions.py` 的说明和 p2z 的那一份写。假 vllm、假 hf 和找空闲端口的几行从 test_serve.py 挪进 `tests/fakes.py`（假 vllm 是一个小 HTTP 服务，应答 `/health`、`/metrics`、`/v1/models`），fixture 和 test_serve.py 都在开头从那里导入。

- `HELP_ENV`：`XDG_CONFIG_HOME`、`XDG_STATE_HOME` 指到 `/dev/null` 下面（`/dev/null/config` 之类），`VLLM_SERVE_VLLM` 也指那里。那种目录建不出来，root 也不行，所以 `-h` 一旦去读配置或状态就会当场出错。`-h` 不碰任何端口。
- `REMOVED`、`SELECTS`：没有。没去掉任何长选项，也没有 `--collection`。
- `env(tmp)`，上下文管理器：把假 vllm 写进 tmp 并设可执行；建一个空目录当所有 profile 的 `model`（本地目录，不下载）；写好下面几个用例的 profile：`q1`、`w1`–`w3`、`n1` 各占一个现找的空闲端口，`r000`–`r499` 只有文件、从不起服务。yield 的环境：`XDG_CONFIG_HOME`、`XDG_STATE_HOME` 指到 tmp 里；`VLLM_SERVE_VLLM` 指假 vllm；`FAKE_RECORD` 指 tmp 里一个文件（假 vllm 往里记参数，不设会出错）；`VLLM_SERVE_TICK=0.5`；`no_proxy`、`NO_PROXY` = `127.0.0.1,localhost`。这份环境也留在模块里，给 `written` 用。`finally` 里用这份环境跑 `serve.py down -a`：假服务是脱离会话的进程，不停就会留下来。
- `quiet`：`{"run": "serve.py up q1 >/dev/null 2>&1; serve.py up q1", "lines": 1}`。前一句把假服务起好、输出丢掉；后一句直接拿来用：退出 0，一行 `code: ok`、`started: false`，标准错误为空。
- `reader`：`{"run": "serve.py status"}`。500 份 `r…` 加上前面几个，再加 skill 自带的两份 profile（不管 `XDG_CONFIG_HOME` 指哪，`status` 总会列出 skill 的 `profiles/`，`serve.py:66、94`），每行约 150 字节，全部约 80 KB，过 64 KiB（检查自己量）。都没有坏的，退出 0。
- `writer`：`{"run": "for p in w1 w2 w3; do serve.py up $p >/dev/null 2>&1; done; serve.py status w1 w2 w3 | serve.py down -", "written": …}`，检查在后面接 `| head -1`。`written` 用模块里那份环境跑 `serve.py status w1 w2 w3`，三行都是 `phase: stopped` 才算真。
  - 为什么三个就够：只有 5 行，远不到管道缓冲，断管是靠 `down` 的等待碰上的，而这个等待是必然的。`down` 拿着那把决定锁发出停止信号，放开锁后马上看一次；守护进程要先拿到同一把锁、再停掉它的 vLLM 才退出，所以这一次总还看得见它，`down` 睡 1 秒再看。于是每两行之间至少隔 1 秒，而 `head` 读到第一行就退出，第二行写出去时管道已经关了。
  - 这条测得出毛病：`down` 要是在第二行上被断管打断，`w2`、`w3` 还在跑，`written` 就是假。
- `no_service`：`{"run": "VLLM_SERVE_VLLM=<tmp>/no-vllm serve.py up n1", "code": "vllm_missing"}`。`VLLM_SERVE_VLLM` 指一个不存在的文件（第 5 节那处小改动），所以不管本机 vllm 装在哪都一样：退出 2，标准输出为空，标准错误最后一行 `code: vllm_missing`。这里不涉及端口。

**`tests/check_conventions.py`**：落地时主 agent 把 vllm-serve 从 `NOT_YET` 拿掉。静态和帮助那几条对它本来就成立：三个短词都指 `None`，没有别的脚本；三页帮助都没有 `commands:` 段。

**test_serve.py 要改的：**

- `:311`：`start_up` 把标准错误丢掉了；退出 2 的原因现在在标准错误上，改成接住。
- `:361、373、407、413、420、487`：`err["error"]` → `err["code"]`；`up` 的 `server_failed`、`port_busy`、`unknown_profile` 退出码 2 → 1，`down nope` 也是 1。`err["detail"]` 的断言照旧（`:362、374–375、408、414、421–425、443`），这几处再各断言一下有 `hint`。
- `:340、370、441、471`：`["stopped"]` → `["code"] == "ok"`。
- 补几条，尽量并进现有的测试：`--` 的切分，`up fake extra` 和 `up fake --max-model-len 8192` 退出 2、提示里有 `--`，`up -- fake` 退出 2，`up fake -- --seed 0` 把 `--seed 0` 交给 vLLM（现有的 `:321` 已经在测）；`down a b` 和 `down -`（读 `status` 的行）、`-` 读空清单退出 0、什么都不写退出 2、没在跑的是 `skipped`；`status fake` 只出这一行、`status nope` 退出 1；不认识的短词退出 2；`VLLM_SERVE_VLLM` 指不存在的文件得 `vllm_missing`、退出 2。
- 假 vllm、假 hf、找空闲端口的几行改从 `tests/fakes.py` 导入。

**动手前先在真机器上看的**（只列出来，这次不做）：

1. 本机（RTX 5090 D，vLLM 0.31）用现在的 `serve.py`：`up paddleocr-vl` 冷启动和已在跑各一次、`status`、`down`，记下标准输出、标准错误的每一行和退出码，当"改前"的底。确认成功时标准错误只有第 5 节说的那几行。
2. pro6000：`ssh <host> '. <root>/env.sh && <root>/vllm-serve/scripts/serve.py -h'`，用现在的副本，不经 `uv run`（只读，不碰服务）。开头那一行靠 `env -S`（coreutils 8.30 起才有）和 `env.sh` 放进 PATH 的 uv；跑不起来，那边就写 `uv run --quiet <root>/vllm-serve/scripts/serve.py`。（2026-11-06 主 agent 做了：退出 0，coreutils 9.4，uv 在 PATH 上，按路径直接跑就行。）
3. 本机：在 8118 端口上放一个别的程序，跑一次 paddleocr 的解析，看现在 `port_busy` 怎么传到 paddleocr 的标准错误、怎么退回原生；改完后同样跑一次对照。

**验收：**

- vllm-serve、paddleocr 的测试和约定检查全过（vllm-serve 不在 `NOT_YET` 里）。
- 本机实测：`serve.py up paddleocr-vl` 冷启动、再一次直接拿来用（标准错误为空）、`status paddleocr-vl`、`status | serve.py down -`；`VLLM_SERVE_VLLM=/nonexistent serve.py up paddleocr-vl` 得到 `vllm_missing`、退出 2；paddleocr 解析一页走 vLLM 服务。
- 文档变短：SKILL.md 加 `references/` 现在 282 行（64 + 110 + 59 + 49），改完要更短；挪走的是字段说明，进了 `-h`。`serve.py` 多出的只有 man 页和从 p2z 拷来的输出那几十行，都只写一处。
- 文档和例子里没有 `cd`、`uv run scripts/`、`2>/dev/null`。
- pro6000 上的副本：用户点头、更新之后，`status` 认得出那边的部署 profile。

## 8. 偏离和理由

1. **入口名是 `serve.py`，不是首字母。** 它是这个 skill 名字的后半截，全系统不重名；冻结的样板 spec 1.1 定 §3 这条时就把它算作入口加短词。改成 `vs.py` 也合规，但要跟着改 paddleocr 找它的路径和测试、参考文档里点名它的地方、服务器上的副本、用户项目里按路径加载它的脚本，换来的只是名字的样子一致，`vs` 还会读成 versus。
2. **`up`、`down` 不是严格的动词。** 在 `docker compose up/down`、`vagrant up` 里它们就是动词用，agent 认得；换成 `start`/`stop` 反而读着像"一定新起一个"。
3. **在共享服务器上按路径跑入口，不写 PATH 那一句**：`ssh <host> '. <root>/env.sh && <root>/vllm-serve/scripts/serve.py …'`。那一句要解决的是一行里整条管道都找得到入口、上游失败带到退出码上；ssh 那边只跑一个命令，管道在本机这一侧（`ssh … | jq … | ssh …`），由本机那一句的 `pipefail` 管着。服务器上什么都不用改。在 ssh 里也写那一句，每次都长；让 `env.sh` 把这个目录放进 PATH，要改那台机器上所有项目共用的文件，不归这个 skill。
4. **`status` 不写 profile 就列全部。** §3 说空的 `$(…)` 不能变成"全部"，管的是非写东西不可的命令。`status` 只读，几个 profile 一眼列完，空的 `$(…)` 列出全部不伤任何东西；像 p2z 的 `tags`、`collections`。
5. **`_supervise` 是不露面的子命令。** `up` 起守护进程时自己调它（`serve.py _supervise <profile> -- …`），用户不敲：不进 `WORDS`，`-h` 不列，在查短词表之前分出去，别的不认识的词照样退出 2 并列出短词。不拆成一个脚本：约定检查会要它有一个短词，而守护进程和 `up` 共用这个模块里几乎全部代码。

## 9. 待定

没有。`down -a` 留着（字母表里就是这个意思，范围是整理不是删功能）；ssh 的写法见第 8 节第 3 条；`up` 退出 1 不打汇总，用户 2026-11-06 同意写进了 §3。

## 10. 实施时的改正（2026-11-06）

- `hint` 按出错的地方各写各的：原来写在 `detail` 后半句的"下一步怎么做"挪进 `hint`；所有 `unknown_profile` 共用一句默认的。
- paddleocr 那边 `error` 后面的 `detail`，取 vllm-serve 的 `detail` 和 `hint`，用 "; " 连起来。
- `up` 在 `--` 前面多写东西：用法错误 `unrecognized arguments: …`，提示 "vLLM arguments go after --: serve.py up PROFILE -- ARG ..."。profile 名字里有 `/`：`unknown_profile`。
- 退出 2 时，vllm-serve 的 `{code, detail, hint}` 也会出现在 paddleocr 的标准错误上，紧挨在它自己那行 `[paddleocr] vllm-serve <code>: …` 前面（标准错误边读边转），重复但无害。
- 行数：`serve.py` 809 → 1053。拷来的输出那层约 125 行，比第 7 节说的"几十行"多；man 页 75 行。文档 282 → 279 行，词数反而多了约 5%：多的是 *Calling* 一段和 `status | … | serve.py down -` 那条管道。
- 实测时碰到的环境问题：本机 8118 端口被 Windows 一侧的程序占着（WSL 镜像网络），`up` 连端口时没人应答，于是判为空闲，vLLM 绑不上，报成 `server_failed`。另记 issue。实测改用 8128。
- **`up` 改成在配置名处切开**（用户 2026-11-06 选 B，取代第 3 节 `up` 那条和第 1 节的 `--` 写法）：配置名前面是 `serve.py` 自己的选项（只有 `-h`），后面的原样交给 vLLM；配置名后面紧跟的 `--` 可写可不写，配置名前面的 `--` 结束选项。理由：`up` 是替人启动另一个程序的命令，经典 Unix 的启动器（`timeout 5 cmd -x`、`sudo cmd`、`env A=1 cmd`、`nohup cmd`）和 Python 的（`torchrun train.py --lr`、`uv run script.py --flag`）都把目标后面的参数交给目标，不用 `--`。必须写 `--` 是从原则 §3"选项和操作对象可以任意交错"推出来的，这条适合处理一批东西的命令，不适合启动器。配置名就是分界，不用猜参数归谁。用户：「理论上如果我在用 Python 的时候，我都不会这么刻意去加，是不是绕路了？」——是绕了，我先前只比了"要 `--`"和"让脚本猜"两种，漏了这一种。
