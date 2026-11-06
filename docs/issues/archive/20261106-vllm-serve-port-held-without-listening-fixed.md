# vllm-serve：端口被占但没人监听时，`up` 报成启动失败

> **已解决（2026-11-06）**：`up` 判断端口的办法改成和 vLLM 一样去绑定它（带 SO_REUSEADDR，同 uvicorn）。有程序在监听，照旧报 `port_busy`、提示 `ss -ltnp`；没人监听却绑不上，也报 `port_busy`，`detail` 说"in use, though nothing listens on it"，提示用 `ss -tanp` 查本机、WSL 镜像网络下到 Windows 那边 `netstat -ano` 查，等它放开，或者给 profile 换个端口（`~/.config/vllm-serve/profiles/` 里写一个 `extends` 的）。测试加了一条：只绑定不监听的端口，`up` 得 `port_busy`，不是 `server_failed`。

- 来源：主 agent，2026-11-06，vllm-serve 改 Unix 约定的 subagent 在本机实测时碰到。用户没有提。

## 经过

- **跑的什么。** `serve.py up paddleocr-vl`（端口 8118）。
- **看到什么。** vLLM 起来后报 "Address already in use" 退出，`up` 报 `server_failed`。8118 上没有程序在监听：本机 WSL 用的是镜像网络，Windows 一侧的 `wetype_update.exe`（微信输入法的更新程序）有一条往外的连接，本地端口正好是 8118；8119 也一样。
- **为什么不顺。** `up` 原来靠"连一下端口"判断有没有人占着，没人应答就当空闲，于是起了 vLLM，等它绑定失败才知道，报的是 `server_failed`，叫 agent 去翻日志；该报的是 `port_busy`，并告诉它怎么查、怎么绕开。paddleocr 平时解析就用 8118，碰上这种情况会退回原生、慢十几倍，而原因被说成了"服务起不来"。
- **实测怎么绕过的。** 用一个 `extends` 的 profile 把端口换成 8128。
