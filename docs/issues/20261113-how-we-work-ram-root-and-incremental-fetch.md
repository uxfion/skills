# how-we-work：训练服务器的根目录可以放内存盘，训练输出在跑的过程中增量取回

- 来源 · 日期：hc_deduction 项目，2026-11-13，决定 D20261113-14。和 `20261113-vllm-serve-ram-disk-root.md` 是同一件事，这张记 how-we-work 这边要改的文字。
- 涉及的文字：`references/experiments.md` *On a training server*：
  - *Where things go on the host* 默认存储根目录在磁盘上；
  - *Fetching back, checking, cleaning* 写的是「When the job ends, in this order: 1. Fetch everything ... in one go」，只在结束时取回。

## 用户的话（2026-11-13）

- 「因为本身我们训练完或者使用完都是需要删除的，那为啥不放在存储速度更快的位置」
- 「而且训练服务器一般也都不会关机。只有那种训练权重或其他很重要的，需要取回本机的文件或内容，那就得注意，但是一般来说只要取回本地了（或者定时训练一段时间把固定已经不变的内容及时取回，或者就直接定时取回，rsync不是也有增量同步么），也没什么问题，也不会关机，即使意外关机了，也是那些不重要的，或者是已经被取回的。」
- 「只要不超过/dev/shm的一半都没什么问题吧」
- 「可以，按A定，加上这两条上限」
- 「之后我们就都在/dev/shm/.tmp下干活的，数据服务器上，如果是重要的，要取回的，那就定时取回，你觉得呢，没问题的话写进文档」

## 建议改的地方

1. *Where things go on the host*：内存充足时，存储根目录可以放在内存盘（`/dev/shm/.tmp`）。两条上限：
   - 我们的总量不超过 `/dev/shm` 上限的一半；
   - 放完后可用内存仍超过总内存一半。

   不满足就退回磁盘根目录。另外，`/dev/shm` 是别人进程间通信用的地方，不能塞满。
2. *Fetching back*：训练过程中就用增量 `rsync` 定时取回要紧的输出，比如每个 checkpoint 或每 30 分钟一次；结束时照旧完整取回、核对、清理。这样服务器意外重启时，丢的只是能重建的东西或已经取回的东西。

## 现场的数

- 机械硬盘阵列上的根目录，读模型权重约 120 MB/s，vLLM 启动 18 分钟里占 7 分钟。
- 小文件读得慢：导入环境约 5 分钟。
- 那台机器内存 2 TB，`/dev/shm` 上限 1008 GB，只用了 1.1 GB。

- 第三个前提（项目里 D20261113-16）：非 root 登录时，systemd-logind 的 `RemoveIPC`（默认 yes）会在该用户最后一个会话结束时删掉他在 `/dev/shm` 的文件；用前查 `id -u` 和 `RemoveIPC`，必要时请管理员设 `RemoveIPC=no` 或开 lingering，之前用磁盘根目录。

- 状态：open
