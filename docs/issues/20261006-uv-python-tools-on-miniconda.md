# uv-python：本机的 uv tool 都装在 miniconda 的解释器上

> 2026-10-06 记录 · 状态：open（还没决定要不要重装）。原是 [20261006-paddleocr-setup-fixed.md](20261006-paddleocr-setup-fixed.md) 第 9 节的一条，10-07 拆出来单独成 issue。

本机所有 uv tool（hf、markitdown、mineru、pdfplumber、paddleocr）的解释器都来自 miniconda。如果升级或删除 miniconda，这些工具都可能失效。可以考虑改用 `uv python` 管理的解释器重装（`--python-preference only-managed`）。

- 10-07 复查：`uv tool list --show-python` 显示五个工具仍然都是 CPython 3.12.9。
- 方向（推断，未定）：uv-python skill 里 `uv tool install <tool>` 的例子可以加 `--managed-python`（`uv tool install --help`：「Require use of uv-managed Python versions」），以后新装的工具就不会落在 miniconda 上；已装的要重装才会换解释器。
