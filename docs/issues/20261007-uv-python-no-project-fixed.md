# uv-python：One-off 会往项目目录里写 `.venv` 和 `uv.lock`（缺 `--no-project`）

> 2026-10-07 记录 · 状态：fixed（10-07）。全局指令三份和 skill 已改；还没做的：另一台机器上 Hermes 的副本（`~/.hermes/skills/agent-instructions/SKILL.md`），push 后重装全局的 uv-python skill
>
> - 涉及：`uv-python/SKILL.md`；`agent-instructions/CLAUDE.md`、`AGENTS.md` 的 Python 节（再生成 `HERMES.md`），确认后同步全局副本
> - 关联：[20260929-agent-instructions-reusable-memories.md](20260929-agent-instructions-reusable-memories.md) 第 5 节「只读检查不留写入」和「待你决定」第 4 条，两边说的是同一个缺口
> - 实测环境：Linux x86_64，ext4，uv 管理的 CPython 3.14.8。手工测试用 uv 0.12.22；会话中途用户把 uv 升到了 0.12.23（「是因为我更新了，用了最新版本」），附录的复现脚本在 0.12.23 上跑。两个版本的 `uv help run` 逐字相同，下文引用的文档和源码文件也相同
> - 补测（2026-10-07，本仓库会话）：WSL2，uv 0.12.23。和上面不是同一套环境：默认解释器是 miniconda 的 Python 3.12.9，没装 3.14；缓存目录用 `UV_CACHE_DIR` 改过，不在 `~/.cache/uv`。第 6 节标「补测」的条目是在这台机器上测的
> - 来由：用户问「跟我讲一下uv-python中的--no-project问题」，梳理完后要求「整理完毕，写清楚边界条件以后，放到那边去，让那边项目维护」
> - 去向（10-07）：用户：「你是不是把这个问题想得复杂了。相关的只要加上--no-project 就可以吧」。随后：「Standalone script也要啊」。One-off 的两种写法和 Standalone 的 `uv run x.py` 都加 `--no-project`：全局指令三份（`CLAUDE.md`、`AGENTS.md`、`HERMES.md`），skill 的判断表、Standalone 和 One-Off 两节。Standalone 带 PEP 723 头时它多余但无害（A5），没写头时挡住 C2f。第 8 节第 2–4 条、`--with` 的写法、第 6 节 12、13 条都不改

## 一句话

`uv run` 只在三个条件**同时**成立时才往项目目录里写东西（`.venv`、`uv.lock`，还会把项目本身装进去）：

> **代码没有 PEP 723 头** 且 **没加 `--no-project`** 且 **从起点往上找到了 `pyproject.toml`**

起点：`uv run -` 和 `uv run python -c` 从**当前目录**开始，`uv run x.py` 从**脚本所在目录**开始，一级级往上找。

对照现在的规则：Standalone（带 PEP 723 头）已经符合设计初衷；One-off（`uv run -`）不符合，上面三个条件都可能成立。

## 1. 设计初衷

用户原话（2026-10-07）：

- 「所以我设计之初，standalone 和 one-off 都是不想留下任何东西或者改动什么东西」
- 「A 因为我希望单脚本就能运行，不会遗留下任何东西，就只要一个脚本就能用。特别是不会动项目里的任何东西。我只是测试用或者其他目的用，只要一个文件，其他的任何东西都没有变动」——「A」是选项「写进 uv 缓存（`~/.cache/uv`）不算留下东西」
- 「我想这应该是我当初设计的初衷.如果涉及到项目的东西，那肯定就是project」

由此三种模式的分工：

| 模式 | 用途 | 允许写入 |
| --- | --- | --- |
| Project | 涉及项目 | 项目里的 `.venv`、`uv.lock`，这些本来就该有 |
| Standalone | 一个文件、留着反复用，拷到哪里都能 `uv run x.py` | 只有脚本文件本身，加上 uv 缓存 |
| One-off | 代替 `python -c`，代码不落盘 | 只有 uv 缓存 |

「涉及项目」的界线是我的解读，用户认可了方向，这句措辞没有逐字确认：**要用项目的环境或代码**才算，比如 import 项目里的包、跑项目的测试；只是读项目里的文件（grep 源码、解析配置）不算，仍走 One-off。要用**别人的**项目环境时属于 Project，但会写进别人的目录，先问用户。

## 2. 现状

### 2.1 规则原文

`agent-instructions/CLAUDE.md`（`AGENTS.md`、`HERMES.md` 相同）：

```markdown
- **Project** (`pyproject.toml`) — `uv add PKG`, `uv run script.py`
- **Standalone script** (reusable, with dependencies) — declare inline dependencies (PEP 723), manually or with `uv add PKG --script x.py`, then `uv run x.py`
- **One-off code** (no file) — `echo 'CODE' | uv run -`, or heredoc `uv run - <<'PY' CODE PY`  (never `python -c`)
```

`uv-python/SKILL.md` 的判断表和 One-Off 一节：

```markdown
| Working in a directory with `pyproject.toml` | **Project** — use `uv add`, `uv run` |
| Reusable script that needs specific packages | **Standalone Script** — use PEP 723 inline metadata |
| Quick throwaway code, no file needed | **One-Off Code** — pipe to `uv run -` |

echo 'print("hello")' | uv run -
uv run - <<'PY'
<script>
PY
```

### 2.2 缺口

1. **One-off 的写法会写进项目。** `uv run -` 在项目目录或它的任何子目录里跑，都会在项目根建 `.venv`、写 `uv.lock`（第 4 节 C2）。「no file」只保证代码不落盘，不保证环境不落盘。
2. **判断表混了两个维度。** 第一行按位置分（"Working in a directory with `pyproject.toml`"），后两行按代码形态分。在别人的仓库里跑一次性代码，同时命中第一行和第三行，表里没说哪个优先；uv 的实际行为是第一行优先。
3. **Standalone 没要求一律写头。** 全局指令写的是 "reusable, with dependencies"，没依赖的脚本就容易不写头。不写头的脚本放进项目目录，会从脚本所在目录往上找到项目（C2f）。
4. **One-off 需要第三方包时没给写法。** skill 里 `--with` 的例子只有 `uv run --with <package> <script>.py`。

### 2.3 出过的事（2026-09-28）

一个子 agent 做只读检查，工作目录是一个全局安装的 hermes-agent 的源码目录，跑了 `uv run -`。uv 把那里当成项目：建了 143M 的 `.venv`，重写了 `hermes_agent.egg-info`。`.venv` 经用户同意后删了；egg-info 按同一份 `pyproject.toml` 重新生成，原文件还原不了。

用户当时的话：「为什么只读去检查，你都能新建东西的，而且是在源码下面的。不应该都是用一次性的临时的脚本吗？我难道没有教你过吗？」随后决定暂不改规则：「不用。但是这点你记一下，后面可以提醒我。」10-07 提醒后，用户要求写成本 issue。

### 2.4 为什么之前没碰到

用户问：「是不是因为没有写这个，又没带“no project”，就会找上一级的？」是的。用户平时的脚本都带 PEP 723 头（A 组），平时跑命令的目录往上也没有 `pyproject.toml`（C1），所以一直没有副作用。只有在不是自己项目、却带 `pyproject.toml` 的目录里跑不带头的代码，才会出问题，比如别人的源码、clone 下来读的仓库。

## 3. `uv run` 怎么判断

1. **代码开头有 PEP 723 头吗？** 有就按独立脚本处理，不找项目，加不加 `--no-project` 都一样（A 组）。
2. **没有头，加了 `--no-project` 吗？** 加了就不找项目（B 组）。
3. **都没有，就找项目**：从起点往上找 `pyproject.toml`（C 组）。
   - 找不到：已激活的虚拟环境、当前或上级目录里现成的 `.venv` 有就用，没有就直接用解释器。不写任何东西。
   - 找到了：**任何** `pyproject.toml` 都算，包括只有 `[tool.ruff]` 这种工具配置的。进入项目模式：建或同步项目根的 `.venv`，写 `uv.lock`，把项目本身装进去。

## 4. 全部情况（实测）

编号和附录 A 脚本的输出一一对应。除非另说明，工作目录都是项目的子目录 `sub/`，项目根在它的上一级。

### A 组：带 PEP 723 头

| 编号 | 怎么跑 | 项目目录多了 | 代码跑在哪 | 说明 |
| --- | --- | --- | --- | --- |
| A1 | stdin，头里 `dependencies = []` | 无 | `~/.cache/uv/environments-v2/<按依赖算的哈希>` | 跑完保留，依赖一样就复用 |
| A2 | 文件 `uv run s.py`，同样的头 | 无 | `environments-v2/s-<按脚本路径算的哈希>` | 跑完保留，同一路径复用；见 D |
| A3 | 头里只写 `requires-python` | 无 | `~/.cache/uv/builds-v0/.tmp*` | 跑完删除。文档要求 `dependencies` 必写，见 7.3 |
| A4 | 头 + `--with six` | 无 | `builds-v0/.tmp*` | 跑完删除 |
| A5 | 头 + `--no-project` | 无 | 和 A1 同一个环境 | `--no-project` 多余但无害 |

### B 组：没有头，加了 `--no-project`

| 编号 | 怎么跑 | 项目目录多了 | 代码跑在哪 | 说明 |
| --- | --- | --- | --- | --- |
| B1 | 不加 `--with`，附近没有 `.venv` | 无 | 直接用解释器，不建环境 | **uv 缓存里也没有任何文件变化** |
| B2 | 不加 `--with`，上级目录已有 `.venv`（没有项目） | 无 | 那个现成的 `.venv` | 不写，但代码看到的是那个环境里的包 |
| B3 | `--with six` | 无 | `builds-v0/.tmp*` | 包来自缓存环境，见第 5 节 |
| B4 | `--with six`，上级目录已有 `.venv` | 无 | `builds-v0/.tmp*` | `six` 没有装进那个现成的 `.venv` |

### C 组：没有头，也没加 `--no-project`

| 编号 | 怎么跑 | 项目目录多了 | 代码跑在哪 | 说明 |
| --- | --- | --- | --- | --- |
| C1 | 一路往上都没有 `pyproject.toml` | 无 | 解释器 | 同 B1；附近有 `.venv` 时同 B2 |
| C2 | `uv run -` | **`.venv`、`uv.lock`** | 项目的 `.venv` | 在子目录里跑，写在上一级的项目根 |
| C2t | `pyproject.toml` 里只有 `[tool.ruff]` | **`.venv`、`uv.lock`** | 项目的 `.venv` | 没有 `[project]` 也算项目，见 7.2 |
| C2p | `uv run python -c` | **`.venv`、`uv.lock`** | 项目的 `.venv` | 和 `uv run -` 一样 |
| C2f | 不带头的脚本在项目里，工作目录在项目外 | **`.venv`、`uv.lock`** | 项目的 `.venv` | 从脚本所在目录找起 |
| C2g | 不带头的脚本在项目外，工作目录在项目里 | 无 | 解释器 | 同上，和工作目录无关 |
| C3 | `--with six` | **`.venv`、`uv.lock`** | `builds-v0/.tmp*`，叠在项目环境上 | `--with` 防不住 |
| C4 | `--no-sync` | **`.venv`** | 项目的 `.venv` | 不写 lock，但照样建 `.venv` |
| C5 | `--frozen` | **`.venv`** | 没跑：没有 lock，报错退出 | 先建了 `.venv` 才报错 |
| C6 | 已经同步过的项目再跑 | 无（`uv.lock` 修改时间不变） | 项目的 `.venv` | |

### D：按路径复用的脚本环境不会删掉依赖

同一路径的脚本，头里先声明 `six` 跑一次，再把 `six` 从头里删掉重跑，`six` **还能 import**。uv 只检查已有环境够不够用，多出来的包不删。所以脚本在这台机器上能跑，不代表头里的依赖写全了，换台机器才会暴露。这和「只要一个文件就能用」直接相关。

## 5. 原理：环境放在哪

- **不加 `--with` 的 B1、C1**：直接用 uv 装的解释器（`~/.local/share/uv/python/…`），`sys.prefix` 就是解释器目录，不建环境，也不写缓存。
- **加 `--with`（A4、B3、B4、C3）**：三层，都在缓存里。下面的路径和文件名是 0.12.22 上手工观察的：

  ```text
  代码
   └─ ③ 临时环境  builds-v0/.tmpXXXX/            每次新建，跑完删除
        ├─ 解释器 → ~/.local/share/uv/python/cpython-…
        └─ _uv_ephemeral_overlay.pth → ② 缓存环境  archive-v0/<id>/      复用；environments-v2/<哈希>/ 里有软链接指向它
                                          └─ 链接 → ① 解包后的 wheel  archive-v0/<另一个 id>/   只解包一次
  ```

  ③ 只有 `pyvenv.cfg` 和一个 `.pth` 文件，Python 启动时用 `site.addsitedir` 把②的 `site-packages`（项目模式下还有项目环境）加进搜索路径。
- **PEP 723 脚本**：stdin 的环境在 `environments-v2/<按依赖算的哈希>`，文件的在 `environments-v2/s-<按脚本路径算的哈希>`，都是完整的 venv，跑完保留复用。头里只写 `requires-python` 时走 `builds-v0` 临时环境。
- **项目模式**：项目根的 `.venv`，包文件同样从缓存链接过去。所以建得快、几乎不占空间，问题只在于写在了项目目录里。
- **链接方式**：本机看到的是硬链接（`six.py` 的硬链接数是 20，好几个环境共用一份）。文档说 Linux 默认是 clone（写时复制）；源码里 clone 失败时按 Clone → Hardlink → Copy 的顺序退回；本机缓存在 ext4 上，ext4 不支持 clone。所以「退回到了硬链接」是根据文件系统和源码做的推断，没有看到 uv 选择链接方式的日志。

## 6. 边界条件

1. **起点**：stdin 和 `python -c` 从当前目录找，`x.py` 从脚本所在目录找，一直往上找到根目录。项目的任何子目录都会命中项目。
2. **什么算项目**：任何 `pyproject.toml` 都算，包括只有 `[tool.*]` 配置、没有 `[project]` 的。源码里叫 non-project workspace root，照样 lock 和同步。
3. **防不住项目模式的**：`--with`、`--no-sync`、`--frozen`。后两个不写或不更新 lock，但照样建 `.venv`。
4. **防得住的**：只有 PEP 723 头和 `--no-project`（环境变量 `UV_NO_PROJECT=1`）。两者同时用没有坏处。
5. **参数位置**：`--no-project` 必须写在 `-` 或脚本名**前面**。写在后面会被当成传给脚本的参数。
6. **`--no-project` 不等于完全隔离**：已激活的虚拟环境，或当前、上级目录里现成的 `.venv`，会被直接拿来用（B2）。不会往里写（B4：`--with` 的包没装进去），但代码看到的是那个环境里的包。
7. **PEP 723 头**：文档要求必须写 `dependencies`，空的也要写。只写 `requires-python` 时实测也按脚本处理（A3），但这是文档之外的行为，规则里不该依赖它。
8. **脚本旁边的 lock**：`uv lock --script x.py` 会在脚本旁边生成 `x.py.lock`；有了它以后，`uv run` 还会在需要时更新它。这会让 Standalone 多出第二个文件，所以 Standalone 不该跑 `uv lock --script`。这一条依据文档，没有实测。
9. **缓存**：写进 uv 缓存不算「留下东西」（用户 10-07 定的）。B1 连缓存都不写；其他不进项目模式的写法只写缓存。
10. **缓存复用的副作用**：见 D，从头里删掉的依赖不会从环境里移除。
11. **自己的项目**：同步过的再跑不改 `uv.lock`（C6）；依赖改了会重新 lock、重新同步（文档）。
12. **`--no-project` 照样读目录里的配置**（补测）：从当前目录往上找到的 `.python-version`、`pyproject.toml` 的 `[tool.uv]`、`uv.toml` 都生效，只是不进项目模式，项目目录里不多东西。
    - `.python-version` 写 `3.11` 时，用的是 3.11.17，不是默认的 3.12.9。写一个没装的 `3.8` 并设 `UV_PYTHON_DOWNLOADS=never` 时，uv 提示有可下载的托管 Python：默认设置下它会去下载，装进 `~/.local/share/uv/python`。这个目录不是缓存，按第 9 条的口径算不算「留下东西」还没定。
    - `[tool.uv]` 里 `index-url` 指向一个连不上的地址时，`--with six` 去连这个地址，失败退出。也就是说在别人的仓库里，`--with` 的包从那个仓库指定的源下载。
13. **`--no-config` 能挡住第 12 条**（补测）：加上后 `.python-version` 和 `[tool.uv]` 都不再生效，用回默认解释器和默认源。代价是用户级的配置（`~/.config/uv/uv.toml`）也一起忽略（`uv help run`：配置文件从当前目录、上级目录和用户配置目录里找）。本机没有用户级 `uv.toml`。

没有实测、只有文档或推断的：

- 已激活虚拟环境时：没有项目就用它（文档）；有项目时默认用项目的 `.venv`，加 `--active` 才用激活的（文档）
- 项目里设了 `[tool.uv] managed = false`：文档说 uv 不再自动 lock 和同步
- 在 workspace 成员目录里跑
- 第 8 条 `x.py.lock` 的生成和更新
- `--no-cache`：文档说只用本次运行的临时缓存，跑完不留
- 预览功能 centralized-project-envs 会把项目环境放进缓存、`.venv` 只是链接（默认没开）

## 7. 和文档对照

### 7.1 文档写了，和实测一致

链接中「文档」指 docs.astral.sh 上的当前版本，「源」指 uv 仓库 `0.12.23` 标签下的固定版本。CLI 参考页由 `crates/uv-cli/src/lib.rs` 里的注释生成，内容和 `uv help run` 相同。

| 结论 | 文档原文 | 出处 |
| --- | --- | --- |
| 在项目里跑会先装项目，`--no-project` 可以跳过 | "Note that if you use `uv run` in a _project_, i.e., a directory with a `pyproject.toml`, it will install the current project before running the script. If your script does not depend on the project, use the `--no-project` flag to skip this" | [文档](https://docs.astral.sh/uv/guides/scripts/#running-a-script-without-dependencies) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L79-L81) |
| `--no-project` 写在脚本名前 | "Note: the `--no-project` flag must be provided _before_ the script name." | [文档](https://docs.astral.sh/uv/guides/scripts/#running-a-script-without-dependencies) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L84) |
| 起点：脚本从所在目录，其他从当前目录 | "When running a script, the project or workspace is discovered from the script's directory. Otherwise, the project or workspace is discovered from the current working directory." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L1118-L1119) |
| stdin 也按脚本处理 | "When used with `-`, the input will be read from stdin, and treated as a Python script." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L1108-L1109) |
| 没有项目时用现成的 `.venv` 或解释器 | "When used outside a project, if a virtual environment can be found in the current directory or a parent directory, the command will be run in that environment. Otherwise, the command will be run in the environment of the discovered interpreter." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L1114-L1116) |
| 往上找；`--no-project` 关掉这一步 | "Avoid discovering the project or workspace. Instead of searching for projects in the current directory and parent directories, run in an isolated, ephemeral environment populated by the `--with` requirements." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--no-project) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3737-L3740) |
| `--no-project` 仍用现成的环境（边界 6） | "If a virtual environment is active or found in a current or parent directory, it will be used as if there was no project or workspace." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--no-project) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3742-L3743) |
| 项目模式建 `.venv`、写 `uv.lock` | "When `uv run` is invoked, it will create the project environment if it does not exist yet or ensure it is up-to-date if it exists." / "uv creates a `uv.lock` file next to the `pyproject.toml`." | [文档](https://docs.astral.sh/uv/concepts/projects/layout/#the-project-environment) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/concepts/projects/layout.md?plain=1#L42-L43)，[lock](https://github.com/astral-sh/uv/blob/0.12.23/docs/concepts/projects/layout.md?plain=1#L77) |
| 带头时不需要 `--no-project` | "When using inline script metadata, even if `uv run` is used in a _project_, the project's dependencies will be ignored. The `--no-project` flag is not required." | [文档](https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L197) |
| 带头的脚本和项目隔离 | "Scripts that declare inline metadata are automatically executed in environments isolated from the project." | [文档](https://docs.astral.sh/uv/concepts/projects/run/#running-scripts) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/concepts/projects/run.md?plain=1#L44-L45) |
| `--with` 防不住项目模式 | "When used in a project, these dependencies will be layered on top of the project environment in a separate, ephemeral environment." / "Note that if `uv run` is used in a _project_, these dependencies will be included _in addition_ to the project's dependencies. To opt-out of this behavior, use the `--no-project` flag." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--with) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3615-L3619)，[指南](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L134-L135) |
| `--no-sync` 不写 lock | "Implies `--frozen`, as the project dependencies will be ignored (i.e., the lockfile will not be updated, since the environment will not be synced regardless)." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--no-sync) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3668-L3671) |
| `--frozen` 没有 lock 就报错 | "If the lockfile is missing, uv will exit with an error." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--frozen) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3686-L3691) |
| 脚本的 lock 要手动生成，有了以后会更新 | "Unlike with projects, scripts must be explicitly locked using `uv lock`" / "Running `uv lock --script` will create a `.lock` file adjacent to the script" / "will reuse the locked dependencies, updating the lockfile if necessary." | [文档](https://docs.astral.sh/uv/guides/scripts/#locking-dependencies) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L276-L287) |
| 默认不用已激活的环境 | "Prefer the active virtual environment over the project's virtual environment." | [文档](https://docs.astral.sh/uv/reference/cli/#uv-run--active) · [源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L3655) |
| 缓存可以丢 | "The cache directory is used for data that is disposable, but is useful to be long-lived." | [文档](https://docs.astral.sh/uv/reference/storage/#cache-directory) · [源](https://github.com/astral-sh/uv/blob/0.12.23/docs/reference/storage.md?plain=1#L32) |

### 7.2 文档没写，只有实测或源码

- **只有 `[tool.*]` 的 `pyproject.toml` 也算项目（C2t）。** 文档里没找到。源码写明是有意的：既没有 `[project]` 也没有 `[tool.uv.workspace]` 时，"Otherwise it's a pyproject.toml that maybe contains dependency-groups that we want to treat like a project/workspace to handle those uniformly"（[源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-workspace/src/workspace.rs#L2205-L2261)）。
- **`--no-sync`、`--frozen` 照样建 `.venv`（C4、C5）。** 文档只说不同步、不更新 lock。
- **缓存的分层和复用方式**：`archive-v0`、`environments-v2`、`builds-v0` 三层；stdin 按依赖分环境、文件按路径分；删掉的依赖不移除（D）。
- **B1 连缓存都不写。**

### 7.3 和文档有出入的三处

1. **链接方式。** 文档：「Defaults to `clone` (also known as Copy-on-Write) on macOS and Linux, and `hardlink` on Windows.」（[文档](https://docs.astral.sh/uv/reference/cli/#uv-run--link-mode)）本机看到的是硬链接。不矛盾：源码定义了退回顺序 Clone → Hardlink → Copy（[默认值](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-fs/src/link.rs#L12-L50)，[退回顺序](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-fs/src/link.rs#L266-L280)），ext4 不支持 clone。文档只写了缓存和环境不在同一个文件系统时会「fallback to slow copy operations」（[文档](https://docs.astral.sh/uv/concepts/cache/#cache-directory)）。
2. **「ephemeral」这个词。** 文档说带头的脚本装进「an isolated, ephemeral environment」（[源](https://github.com/astral-sh/uv/blob/0.12.23/crates/uv-cli/src/lib.rs#L1106-L1108)），实测 `environments-v2` 里的环境跑完还在，下次复用。可以理解为用法上一次性、和项目隔离，实现上靠缓存复用。D 的坑就是复用带来的。
3. **`dependencies` 必写。** 文档：「The `dependencies` field must be provided even if empty.」（[源](https://github.com/astral-sh/uv/blob/0.12.23/docs/guides/scripts.md?plain=1#L214)）实测只写 `requires-python` 也按脚本处理（A3），属于文档之外的行为。

## 8. 改动方向（待定，未改）

10-07 定了：只加 `--no-project`，One-off 和 Standalone 都加，见开头「去向」。下面保留当时的讨论。

下面只是方向，不是最终措辞。措辞按本仓库改指令的流程一条一条定，由用户拍板。改的时候保留 `python -c` 的明确禁令和用户给的 `uv run - <<'PY' CODE PY` 这种紧凑写法，只在里面加 `--no-project`。

1. **One-off**：`echo 'CODE' | uv run --no-project -`，heredoc 写成 `uv run --no-project - <<'PY' CODE PY`。需要第三方包时加 `--with PKG`。这样落在 B1、B3，项目目录不写；不加 `--with` 时连缓存都不写。
2. **Standalone**：一律写 PEP 723 头，没有依赖也写 `dependencies = []`；不跑 `uv lock --script`（边界 8）。
3. **Project**：改成「代码要用某个自己项目的环境」。判断表按代码需要哪个环境来分，不按所在目录分。要用别人项目的环境时先问用户。
4. **共同原则写成一句**：Standalone 和 One-off 除了脚本文件本身和 uv 缓存，什么都不写，尤其不碰任何项目。

要改的文件：

- `uv-python/SKILL.md`：判断表、Standalone 一节、One-Off 一节；Other Commands 里的 `--with` 例子
- `agent-instructions/CLAUDE.md`、`AGENTS.md` 的 Python 节，再生成 `HERMES.md`；确认后同步全局副本

待定：

- D 的坑要不要写进 skill
- 第 6 节 12、13 条：`--no-config` 只写进 skill 的边界条件，还是也进全局写法；下载的 Python 算不算「留下东西」
- 和 [20260929-agent-instructions-reusable-memories.md](20260929-agent-instructions-reusable-memories.md) 第 5 节、决定 4 怎么合并处理。那边第 5 节已加一行指向本文件（10-07）

## 附录 A：复现脚本

保存成 `uv-run-writes.sh`，`bash uv-run-writes.sh` 运行。每种情况在一个新的临时目录里跑，退出时删掉。第一次运行要联网下载 `six`；除了临时目录，只写 uv 缓存。

```bash
#!/usr/bin/env bash
# Which `uv run` forms write into a project directory?
# Every case runs in its own fresh directory under a temp dir that is removed on exit.
# Output per case: what appeared in the project root (besides the fixture files) and where the code ran.
# Needs network on the first run (downloads `six`); besides the temp dir it writes only to uv's cache.
# Usage: bash uv-run-writes.sh   ($TMPDIR must not sit inside a project, i.e. no pyproject.toml above it)
set -u
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
CACHE=$(uv cache dir)
CODE='import sys; print(sys.prefix)'
HDR_EMPTY=$'# /// script\n# dependencies = []\n# ///'
HDR_PYONLY=$'# /// script\n# requires-python = ">=3.10"\n# ///'
PROJ_TOML=$'[project]\nname = "demo"\nversion = "0.1.0"\nrequires-python = ">=3.10"\ndependencies = []'

proj() {  # proj DIR [toml]: a project root with a sub/ directory
  mkdir -p "$1/sub"
  printf '%s\n' "${2:-$PROJ_TOML}" > "$1/pyproject.toml"
}
where() {  # classify sys.prefix
  case "$1" in
    *"/environments-v2/s-"*) echo "cache: environments-v2/s-* (kept; keyed by script path)";;
    *"/environments-v2/"*) echo "cache: environments-v2 (kept; keyed by dependencies)";;
    *"/builds-v0/"*)       echo "cache: builds-v0 temp (deleted after run)";;
    *"/.venv")             echo ".venv at ${1#$T/}";;
    "")                    echo "(did not run)";;
    *)                     echo "interpreter, no environment";;
  esac
}
row() {  # row CASE ROOT PREFIX [FIXTURE_RE]: FIXTURE_RE names files the case created on purpose
  local extra; extra=$(cd "$2" && ls -A | grep -vxE "pyproject.toml|sub|s.py${4:+|$4}" | sort | tr '\n' ' ')
  printf '%-3s project root gained: %-20s | ran in: %s\n' "$1" "${extra:-nothing}" "$(where "$3")"
}
last() { tail -n1; }  # the code's own output is the last line; uv's notices go to stderr

echo "uv $(uv --version | cut -d' ' -f2)"
echo "--- A: PEP 723 header (cwd = project/sub)"
proj "$T/a1"; p=$(cd "$T/a1/sub" && printf '%s\n%s\n' "$HDR_EMPTY" "$CODE" | uv run - 2>/dev/null | last); row A1 "$T/a1" "$p"
proj "$T/a2"; printf '%s\n%s\n' "$HDR_EMPTY" "$CODE" > "$T/a2/sub/s.py"; p=$(cd "$T/a2/sub" && uv run s.py 2>/dev/null | last); row A2 "$T/a2" "$p"
proj "$T/a3"; p=$(cd "$T/a3/sub" && printf '%s\n%s\n' "$HDR_PYONLY" "$CODE" | uv run - 2>/dev/null | last); row A3 "$T/a3" "$p"
proj "$T/a4"; p=$(cd "$T/a4/sub" && printf '%s\n%s\n' "$HDR_EMPTY" "$CODE" | uv run --with six - 2>/dev/null | last); row A4 "$T/a4" "$p"
proj "$T/a5"; p=$(cd "$T/a5/sub" && printf '%s\n%s\n' "$HDR_EMPTY" "$CODE" | uv run --no-project - 2>/dev/null | last); row A5 "$T/a5" "$p"

echo "--- B: no header, --no-project"
proj "$T/b1"; touch "$T/marker"; sleep 1
p=$(cd "$T/b1/sub" && echo "$CODE" | uv run --no-project - 2>/dev/null | last); row B1 "$T/b1" "$p"
echo "    B1 files changed in uv cache: $(find "$CACHE" -newer "$T/marker" 2>/dev/null | wc -l)"
mkdir -p "$T/b2/sub"; (cd "$T/b2" && uv venv -q .venv)
p=$(cd "$T/b2/sub" && echo "$CODE" | uv run --no-project - 2>/dev/null | last); row B2 "$T/b2" "$p" '\.venv'
proj "$T/b3"; p=$(cd "$T/b3/sub" && echo "$CODE" | uv run --no-project --with six - 2>/dev/null | last); row B3 "$T/b3" "$p"
mkdir -p "$T/b4/sub"; (cd "$T/b4" && uv venv -q .venv)
p=$(cd "$T/b4/sub" && echo "$CODE" | uv run --no-project --with six - 2>/dev/null | last); row B4 "$T/b4" "$p" '\.venv'
echo "    B4 six installed into the existing .venv: $(ls "$T"/b4/.venv/lib/python*/site-packages | grep -qx 'six.py' && echo YES || echo no)"

echo "--- C: no header, no --no-project"
mkdir -p "$T/c1"; p=$(cd "$T/c1" && echo "$CODE" | uv run - 2>/dev/null | last); row C1 "$T/c1" "$p"
proj "$T/c2"; p=$(cd "$T/c2/sub" && echo "$CODE" | uv run - 2>/dev/null | last); row C2 "$T/c2" "$p"
proj "$T/c2t" $'[tool.ruff]\nline-length = 100'; p=$(cd "$T/c2t/sub" && echo "$CODE" | uv run - 2>/dev/null | last); row C2t "$T/c2t" "$p"
proj "$T/c2p"; p=$(cd "$T/c2p/sub" && uv run python -c "$CODE" 2>/dev/null | last); row C2p "$T/c2p" "$p"
proj "$T/c2f"; echo "$CODE" > "$T/c2f/s.py"; mkdir -p "$T/out"; p=$(cd "$T/out" && uv run "$T/c2f/s.py" 2>/dev/null | last); row C2f "$T/c2f" "$p"
proj "$T/c2g"; echo "$CODE" > "$T/out/s.py"; p=$(cd "$T/c2g/sub" && uv run "$T/out/s.py" 2>/dev/null | last); row C2g "$T/c2g" "$p"
proj "$T/c3"; p=$(cd "$T/c3/sub" && echo "$CODE" | uv run --with six - 2>/dev/null | last); row C3 "$T/c3" "$p"
proj "$T/c4"; p=$(cd "$T/c4/sub" && echo "$CODE" | uv run --no-sync - 2>/dev/null | last); row C4 "$T/c4" "$p"
proj "$T/c5"; p=$(cd "$T/c5/sub" && echo "$CODE" | uv run --frozen - 2>/dev/null | last); row C5 "$T/c5" "$p"
before=$(stat -c %Y "$T/c2/uv.lock"); sleep 1
p=$(cd "$T/c2/sub" && echo "$CODE" | uv run - 2>/dev/null | last)
echo "C6  rerun in synced project: uv.lock mtime $([ "$before" = "$(stat -c %Y "$T/c2/uv.lock")" ] && echo unchanged || echo CHANGED) | ran in: $(where "$p")"

echo "--- D: script env keyed by path keeps removed dependencies"
mkdir -p "$T/d"; S="$T/d/s.py"; CHK='import importlib.util as u; print("six importable:", bool(u.find_spec("six")))'
printf '# /// script\n# dependencies = ["six"]\n# ///\n%s\n' "$CHK" > "$S"; uv run "$S" 2>/dev/null | last
printf '%s\n%s\n' "$HDR_EMPTY" "$CHK" > "$S"; echo "    after removing six from the header: $(uv run "$S" 2>/dev/null | last)"
```

uv 0.12.23 上的输出：

```text
uv 0.12.23
--- A: PEP 723 header (cwd = project/sub)
A1  project root gained: nothing              | ran in: cache: environments-v2 (kept; keyed by dependencies)
A2  project root gained: nothing              | ran in: cache: environments-v2/s-* (kept; keyed by script path)
A3  project root gained: nothing              | ran in: cache: builds-v0 temp (deleted after run)
A4  project root gained: nothing              | ran in: cache: builds-v0 temp (deleted after run)
A5  project root gained: nothing              | ran in: cache: environments-v2 (kept; keyed by dependencies)
--- B: no header, --no-project
B1  project root gained: nothing              | ran in: interpreter, no environment
    B1 files changed in uv cache: 0
B2  project root gained: nothing              | ran in: .venv at b2/.venv
B3  project root gained: nothing              | ran in: cache: builds-v0 temp (deleted after run)
B4  project root gained: nothing              | ran in: cache: builds-v0 temp (deleted after run)
    B4 six installed into the existing .venv: no
--- C: no header, no --no-project
C1  project root gained: nothing              | ran in: interpreter, no environment
C2  project root gained: uv.lock .venv        | ran in: .venv at c2/.venv
C2t project root gained: uv.lock .venv        | ran in: .venv at c2t/.venv
C2p project root gained: uv.lock .venv        | ran in: .venv at c2p/.venv
C2f project root gained: uv.lock .venv        | ran in: .venv at c2f/.venv
C2g project root gained: nothing              | ran in: interpreter, no environment
C3  project root gained: uv.lock .venv        | ran in: cache: builds-v0 temp (deleted after run)
C4  project root gained: .venv                | ran in: .venv at c4/.venv
C5  project root gained: .venv                | ran in: (did not run)
C6  rerun in synced project: uv.lock mtime unchanged | ran in: .venv at c2/.venv
--- D: script env keyed by path keeps removed dependencies
six importable: True
    after removing six from the header: six importable: True
```
