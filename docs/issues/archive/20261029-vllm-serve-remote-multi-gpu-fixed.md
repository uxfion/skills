# vllm-serve：在共享的多卡远程服务器上部署大模型（Qwen3.8-27B，两台主机）

> **已解决（2026-10-31），归档。** 17 条按 [20261030](../../specs/20261030-vllm-serve-shared-machines-spec.md) 和 [20261031](../../specs/20261031-vllm-serve-principles-rework-spec.md) 两份 spec 进了 vllm-serve skill；两台主机都实测过，结果在 20261031 spec 第 7 节。主机 A 之后被别人预约，用户已清理；新机器照 shared-machines.md 部署。参考目录关闭时核对过：只在那里的事实有三条还用得上，写进了用到它们的文档（数据并行时 `--max-num-seqs` 按副本计、`hf cache prune` 会删钉住的版本、torch 在 `/tmp` 的残留）；其余都已过时，目录已删。

2026-10-29 至 10-30，另一个项目在两台多人共用的 GPU 服务器（8× H200；2× RTX PRO 6000）上把 Qwen3.8-27B 部署成自用后端，vllm-serve 当时直接用不了，那边写了一套补救。用户（2026-10-30）：「另外我是希望将你这几次的经验或者教训或者部署的思路，优化给uxfion/skills ……这样，之后就可以参考这个vllm skills快速部署了，而不用再另外适配了。……具体差异化的东西可以放项目的文档里，但通用的东西，就放到skills中，这样谁上来都能快速用。」

| # | 问题 | 落到哪里 |
|---|---|---|
| 1 | 显存检查只看第一张卡 | 删掉 serve.py 的预检，由 vLLM 按每张卡自己查（install.md 排障） |
| 2 | 两个启动期限太短；权重盘慢时加载很慢 | serve.py 不设等待期限，只给 vLLM 加载 30 分钟上限；install.md 的静默阶段 |
| 3 | CUDA 构建要按驱动选；Blackwell 上没有 FA3 | install.md |
| 4 | 所有文件都要放进用户指定的目录 | shared-machines.md：用户的共享目录就是那台机器上所有项目的家目录 |
| 5 | 只监听 127.0.0.1，局域网的客户端连不上 | profile 里写 `--host`；shared-machines.md |
| 6 | 选卡、和别人共用 GPU、数据并行还是张量并行 | shared-machines.md、tuning.md |
| 7 | 混合模型单卡启动失败（`max_num_seqs` 超过 Mamba 缓存块数） | qwen38-27b profile、install.md、tuning.md |
| 8 | 并发太高时 KV cache 占满，吞吐反而下降 | tuning.md |
| 9 | 显存估算：每张卡要多大、能跑几个会话 | tuning.md |
| 10 | 权重下载不认 revision；下载 CDN 不通；没有校验 | serve.py 按版本下载；install.md |
| 11 | uv 环境不能搬；PyPI 很慢时怎么办 | install.md |
| 12 | FlashInfer 预编译 kernel 缺失，首次启动要现编 | install.md |
| 13 | MTP 投机解码：菜谱里的版本说明已过时 | tuning.md、qwen38-27b profile |
| 14 | `status` 看不到负载和速度 | serve.py |
| 15 | 调用方不传采样参数时用的是什么 | tuning.md |
| 16 | 新增 profile：qwen38-27b | profiles/ |
| 17 | 共享服务器不给 root：只能用个人用户部署和管理 | shared-machines.md |
