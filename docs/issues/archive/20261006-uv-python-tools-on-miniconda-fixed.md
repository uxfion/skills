# uv-python：本机的 uv tool 都装在 miniconda 的解释器上

> 2026-10-06 记录 · 状态：fixed（10-08）。原是 [20261006-paddleocr-setup-fixed.md](20261006-paddleocr-setup-fixed.md) 第 9 节的一条，10-07 拆出来单独成 issue。
>
> 去向（10-08）：根因在 `~/.config/uv/uv.toml` 里修了（`python-preference = "only-managed"`，见最后一节），以后新建的工具和环境都不会再用 miniconda。五个已装工具先不重建：只要 miniconda 不删、base 的 Python 不升到 3.13，它们就照常能用，出问题时再按本文的实测步骤重建。用户：「我感觉可以变成 fixed，因为已经配置好了，暂时还不会遇到问题。除非是把miniconda给删了，而且如果真遇到了，到时候再重建好了，不应该是一直未完成的状态。」uv-python skill 里也不加 conda 的说明（用户：「不用」）。

本机所有 uv tool（hf、markitdown、mineru、pdfplumber、paddleocr）的解释器都来自 miniconda。如果升级或删除 miniconda，这些工具都可能失效。可以考虑改用 `uv python` 管理的解释器重装（`--python-preference only-managed`）。

- 10-07 复查：`uv tool list --show-python` 显示五个工具仍然都是 CPython 3.12.9。
- 方向（推断，未定）：uv-python skill 里 `uv tool install <tool>` 的例子可以加 `--managed-python`（`uv tool install --help`：「Require use of uv-managed Python versions」），以后新装的工具就不会落在 miniconda 上；已装的要重装才会换解释器。

## 10-08 查明原因：conda base 自动激活，uv 把它当作当前环境

- 本机其实装了一批 uv 管理的 Python（3.9 到 3.13，含 3.12.15），uv 也不是因为找不到才用 miniconda。`~/.bashrc` 里的 conda init 块会自动激活 base（`conda config --show auto_activate_base` 为 `True`），所以每个 shell 都设好了 `CONDA_PREFIX=~/miniconda3`。uv 找解释器时会先看已激活的环境，这一步排在 uv 自己管理的 Python 前面：`uv python find -v` 输出「Found `cpython-3.12.9…` at `~/miniconda3/bin/python` (conda prefix)」。
- 对照：去掉 `CONDA_PREFIX` 等变量后，`uv python find` 选中的是 uv 管理的 3.13；`uv python find --managed-python` 也是这个结果。
- 影响不只 uv tool：全局指令里的 one-off 写法（`… | uv run --no-project -`）没有依赖时直接用这个解释器跑，`sys.executable` 是 `~/miniconda3/bin/python`。conda base 的包也能导入：`import requests` 能导入，来自 `~/miniconda3/lib/python3.12/site-packages`；加上 `UV_MANAGED_PYTHON=1` 再跑就是 `ModuleNotFoundError`。所以脚本漏写了依赖也能在本机跑通，换一台机器才会出错。
- 工具环境的 `bin/python` 是指向 `~/miniconda3/bin/python` 的软链接。如果删掉 miniconda，或者 base 的 Python 升到 3.13，这五个工具都会失效。
- 重装不用记原来的安装参数：每个工具目录里的 `uv-receipt.toml` 记着依赖、extras 和 find-links（paddleocr 的 cu129 源也在里面），`python = "3.12"` 也在。`uv tool upgrade` 支持 `--python` 和 `--managed-python`，可以按这份记录重建环境。
- 10-08 实测（临时 `UV_TOOL_DIR` 里装的 pdfplumber，先把 pillow 降到 12.2.0）：
  - `uv tool upgrade pdfplumber --python 3.12 --managed-python`：解释器换成 uv 管理的 3.12，依赖也一起升到最新（pillow 12.2.0 → 12.3.0）。
  - 先 `uv pip freeze` 出现有版本，再 `uv tool install --reinstall --python 3.12 --managed-python pdfplumber -c freeze.txt`：解释器换了，版本原样不动。但这批约束会写进 receipt 的 `constraints`，之后 `uv tool upgrade` 不会再升级（提示 pinned）；不带 `-c` 再 `--reinstall` 一次，约束就清掉了。
  - 解析失败时（约束冲突），原环境原样保留。
  - 五个真实环境的 freeze 都只有 `name==version` 行，没有 URL 或本地路径，所以都可以用作约束文件。
- 可选的修法：(a) 在 uv 的用户配置里要求只用 uv 管理的 Python，全局生效，不动 conda；(b) 关掉 conda base 的自动激活（`auto_activate_base false`），要用 conda 时再手动 activate；(c) 只在 skill 里给 `uv tool install` 加 `--managed-python`，这样管不到 one-off。已装的工具不管选哪种都要重建一次，指定 3.12 可以继续用缓存里的 cp312 wheel。

## 10-08 已改全局配置，五个工具还没重建

用户：「我觉得应该需要配置一下全局设置，不然的话每次都要带--managed-python」。选了 (a)：新建 `~/.config/uv/uv.toml`（之前没有这个文件），只写一行 `python-preference = "only-managed"`，再加一句注释说明原因。

- 生效确认：`uv python find -v` 先报 conda prefix 的 3.12.9，但跳过了，选中 uv 管理的 3.13.16；one-off 的 `sys.base_prefix` 也变成 uv 管理的 3.13.16，`import requests` 报 `ModuleNotFoundError`。已装的工具照常能跑。
- 临时目录里实测的副作用：
  - 已有项目里基于 miniconda 建的 `.venv`，下次 `uv run` 时会被删掉，用 uv 管理的 Python 重建（输出 `Removed virtual environment at: .venv`）。在 `/root` 下搜到 5 层深，只有一个项目受影响；Windows 那边建的 `.venv` 不受影响。
  - 已装的工具不会自己迁移：`uv tool upgrade <tool>` 不带 `--python` 时输出「Nothing to upgrade」，解释器还是 miniconda。所以重建还得做，只是不用再加 `--managed-python`。
  - 新装的工具不指定版本时，用的是 uv 管理的最新版 3.13。重建现有工具时仍要写 `--python 3.12`，这样才能用上缓存里的 cp312 wheel。
- 还没做的：按上面的实测结果重建五个工具，hf、markitdown、pdfplumber 用 `upgrade` 顺便升级，paddleocr、mineru 用 freeze 加 `-c` 保持版本不变；另外，uv-python skill 要不要提一句「conda base 激活时 uv 会优先用它」，这个还没定。用户 10-08：「暂时不用重建，之后再说」。
- 配置管不到的情况（10-08 实测）：用 `--python ~/miniconda3/bin/python3.12` 这种路径明确指定解释器时，仍然用 miniconda；加了 `--no-config` 时，又回到 conda prefix。
