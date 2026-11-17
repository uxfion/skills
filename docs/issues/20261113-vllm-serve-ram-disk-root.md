# vllm-serve：共享服务器内存充足时，根目录放内存盘 `/dev/shm/.tmp`

- 来源 · 日期：hc_deduction 项目，2026-11-13。项目里的决定是 D20261113-14（`docs/decisions/202611.md`），写法在 `docs/servers.md`。
- 涉及的文字：`references/shared-machines.md` *First deployment* 第 1 步写的是"Agree on the place with the user: their directory on that machine (2026-10: the user keeps one per server, a `.tmp` under a path with room)"，默认根目录在硬盘上。

## 现场

- 一台 8 卡 GPU 服务器：根目录在机械硬盘阵列上（84% 满）。27B 模型启动一次约 18 分钟：
  - 读权重 426 秒，50 GB，约 120 MB/s；
  - 进入 vLLM 之前导入环境约 5 分钟，大量小文件读得慢，在根目录下对 `.local`、uv 缓存跑 `du`，20 秒都数不完；
  - 引擎初始化和热身约 4 分钟。
- 同一台机器内存 2 TB，可用约 1.67 TB；`/dev/shm` 是 tmpfs，上限 1008 GB，只用了 1.1 GB。
- 用户（2026-11-13）：「因为本身我们训练完或者使用完都是需要删除的，那为啥不放在存储速度更快的位置」；「而且训练服务器一般也都不会关机……即使意外关机了，也是那些不重要的，或者是已经被取回的」；定的是：「可以，按A定，加上这两条上限」。

## 定下的做法（项目里）

- 用完即删的东西都放 `/dev/shm/.tmp`，并把它当作这台机器的根目录（`env.sh` 里 `HOME=/dev/shm/.tmp`）：模型权重、uv 和 Python 环境、各种缓存、训练数据副本、训练输出。
- 两条上限同时满足才放：
  1. 我们的总量不超过 `/dev/shm` 上限的一半；
  2. 放完后 `free` 显示的可用内存仍超过总内存一半。

  任一条不满足，就用硬盘上的根目录。
- `/dev/shm` 也是别人进程间通信用的地方（NCCL、PyTorch 多进程），不能塞满。
- 机器重启后内存盘清空，按第 2–5 步重建：uv、vLLM、权重拷贝，权重用 sha256 核对。
- 实测（同一台机器、同一张卡，都是新环境第一次启动，各一次）：
  - 从启动命令到服务应答：硬盘根目录约 18 分钟，内存盘 2 分 15 秒；
  - 导入环境：约 5 分钟降到 8 秒；
  - 读权重：426 秒降到 10 秒；
  - 引擎初始化和热身：238 秒降到 95 秒。
- 搭内存盘时又遇到一件事：共用硬盘被别人占满，从硬盘上的 uv 缓存装内核包卡了 18 分钟；改从网上下载，103 秒装完。所以内存盘里的东西要靠下载来填，不从这块硬盘拷。用户（2026-11-13）：「这就说明硬盘速度严重拖累了，你还不如直接用uv直接下载呢」；之后又定：「很大的权重，比如模型权重这些非常大，内网其他服务器上有，那就直接内网传过去，如果是小的安装包，本省下载也很快，那就直接下载就行」。

## 建议

在第 1 步加一个分支：内存充足时（写明上面两条上限），根目录选 `/dev/shm/.tmp`；否则用硬盘上的 `.tmp`。再写清重启后要重建哪些东西。第一次照做的项目实测一次启动时间，把实测数补进这张 issue。

- 第三个前提（项目里 D20261113-16）：非 root 登录时，systemd-logind 的 `RemoveIPC`（默认 yes）会在该用户最后一个会话结束时删掉他在 `/dev/shm` 的文件；用前查 `id -u` 和 `RemoveIPC`，必要时请管理员设 `RemoveIPC=no` 或开 lingering，之前用磁盘根目录。

## 处理（2026-11-17）

- 用户（2026-11-17，看了 how-we-work issue 的优先级排序后）：「内存盘那个可以去做」。两张 issue 一起做：根目录怎么放在 vllm-serve 的共享机器参考里写一处，how-we-work 的 experiments 参考只指过去，再加上跑的过程中取回。
- 改了什么：
  - `vllm-serve/references/shared-machines.md`：*First deployment* 第 1 步加一句（内存充足时新的根目录放内存，原来商定的硬盘目录做退路）；新的一节 *A root in RAM*：三个前提（我们的总量不超过 `/dev/shm` 一半；放完后可用内存仍超过总内存一半；logind 不会删它），重启后怎么重建（从网络填，不从本机硬盘拷），那台 8 卡服务器的实测数作为带日期的提示；*Leaving the machine* 加一句：根目录在内存里时，它一直占着这台机器的内存。
  - `how-we-work/references/experiments.md` *On a training server*：*Where things go on the host* 第一条加了内存根目录和指针，大数据集放上去、输出会很大的训练开跑之前再查一次前提；*Fetching back, checking, cleaning* 开头加了跑的过程中用增量 `rsync` 取回要紧的输出，第 1 步去掉了"一次取回"（in one go）。
- main agent 自己定的几处：
  - 已经在用的硬盘根目录不自动搬，要用户发话才搬：用户的话说的是"之后"，hc 那次清空硬盘上的根目录也是等用户发了话。
  - 跑的过程中取回对硬盘上的根目录也适用：用户那句「如果是重要的，要取回的，那就定时取回」没限定内存盘，代价也小。
  - "每半小时"标成例子，写明不是用户定的数。
  - `RemoveIPC` 两条说法对照了 systemd v255 源码：`src/shared/clean-ipc.c` 会递归删掉 `/dev/shm` 下属于这个 uid 的文件和目录；`src/login/logind-user.c` 里开了 lingering、用户服务还在跑时不会走到清理那一步。查 `RemoveIPC` 的命令用 `loginctl show-session -p RemoveIPC`；hc 的 `docs/servers.md` 里写的 `loginctl show-logind` 在 systemd 255 上不存在（本机实测 `Unknown command verb 'show-logind'`）。
  - 内存盘怎么填（大文件走内网、安装包直接下载，D20261113-17）写进了共享机器参考的重建一段。
- 状态：处理中。文字已改、已提交，等发布（推送要用户发话，然后 `skills update -g`）。发布后 hc_deduction 里被盖过的条目从这边清理：`docs/conventions/experiments.md` 里内存盘那条，`docs/servers.md` 里的通用部分和那条错的命令。待办 B1。发布后关闭。
