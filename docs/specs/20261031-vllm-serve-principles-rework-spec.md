# vllm-serve：按 design principles 返工（2026-10-31）

> 来源：[20261029-vllm-serve-remote-multi-gpu.md](../issues/20261029-vllm-serve-remote-multi-gpu.md) 的“按 design-principles 自查”一节。用户：「在你问我问题之前，你先全局地看一下那个 design principle……因为我觉得你之前是没有按照我这个思路来的」。依据 [docs/design-principles.md](../design-principles.md)（`56bd02a`，加上本次补进 §3 的一句）。
> 取代 [20261030-vllm-serve-shared-machines-spec.md](20261030-vllm-serve-shared-machines-spec.md) 的以下几处，其余照旧：3.3（启动等待）；3.4 的下载时机（下载挪进守护进程）；3.5 的 `idle_minutes = 0` 一条，以及末尾“评审后补上的几处根因”中的三处（`--api-key` 时带密钥、启动前试绑端口、“第一条错误行”）；`up` 判断端口上是谁的做法（3.1、3.2）。

## 1. 为什么返工

10-30 版的分工方向对，但有几处没守住原则：

- **为想象出来的问题预造了机制**（§3 “General and simple, never patched”）。
- **脚本替 agent 下了判断**（§1 “The boundary is the script's certainty”）：日志 10 分钟没动，就认定卡死，停掉服务。
- **交接没写进流程**（§1 “Handoffs are part of the flow”）。

本稿写好后做了两个独立评审：一个看低级错误和技术正确性，一个看原则和设计。两边最重的发现落在同一处，就是“谁在跑、归谁”这套机制：

- `up` 在整个等待期间都拿着锁，所以不计时以后，`down` 停不下一次卡住的启动；
- 状态文件里的 pid 被系统复用时，会把别的进程当成我们的服务；
- 对一个已在运行的服务，探测用的是 profile 里的端口和模型名，而不是状态里记下的；
- 下载权重时，既看不到进度，也停不下来。

第 3 节从根上重新切分了这一块。两份评审逐条怎么处理的，见第 6 节。

## 2. 用户已定

- **启动时怎么等：方案 A**，不设计时，等到服务应答或进程退出为止。用户：「A 但是有一些必要的你还是要考虑的，不要过度防御性，你懂我意思吧。有一些基本上都会遇到的，或者本身就该考虑的，你就应该考虑进去。」
- **design principles 补两句**：§3 基本的不漏，想象的不防，用户：「A」；§1 一个工作项一个 subagent 只适用于一次铺开很多项的 skill，为自己的任务调用 skill 的 agent 自己把任务带到底，用户：「适用范围可以补一下」。都已写进 `docs/design-principles.md`。
- **spec 定稿，实现前先压缩上下文。** 用户：「适用范围可以补一下，在实现前要compact」。
- **就绪和归属：方案 A**，就绪看 `/health`，归属看自己的记录。用户：「A」。
- **一个部署由谁带到底：不另设机制**，被叫到的那个 agent 照 skill 自己做。用户：「我一般用这些 skills 都是主动用的嘛，而且都是交给 Agent 去操作的。比方说，我在 PaddleOCR 里面需要用 VLLM server，它就自己去调用啊。在其他项目中……我也会在其他的 Agent 里面说明，根据我们的 skills，去部署远程服务器上的一个 VLLM」。
- **vLLM 加载那段设 30 分钟上限，下载不计（实现中定，改了上面“不计时”的一部分）。** 起因是一个旁路 agent 的提醒：启动不计时、空闲计时又从第一次应答才开始，卡住的启动没人看着就会一直占着卡，共享服务器上就是同事的卡。我先提了“没人等就停”（等着的 `up` 拿一把锁，每 30 秒打一行进度来探测 ssh 断线），用户：「但问题是，你现在的这个方案是不是把问题考虑复杂了？还是说用以前等一定的时间比较合适？」改提“只给占卡的 vLLM 加载设一个宽裕的上限”，用户：「按30分钟来吧」。它和删掉的 10 分钟计时不同：不看日志动没动、不替 agent 判断卡没卡，只按实测最慢的阶段留足余量。
- **出了问题，让后来的 agent 知道去查：方案 A（实现中定）。** 用户：「另外是不是可以提示一下，在日志里，如果出现问题的话，可以让 Agent 去查。跟我讨论一下」。三条一起做：日志最后一行写明怎么结束的，失败时附上 install.md 的完整路径；新启动前把旧日志留作 `<profile>.prev.log`；上一次失败时，下一次 `up` 先打印一行告知，`status` 也报出上一次怎么结束的。用户：「A」。
- **实现前后各过一遍**，查低级错误和原则、设计上的问题。用户：「你最后再全部过一遍，看有没有问题，特别是一些低级错误，或者是原则上设计上的问题」。

## 3. 设计

### 3.1 一次启动整个交给守护进程

`up` 起一个守护进程。下载权重（需要时）和启动 vLLM 都由这个守护进程做，输出全部写进 `<profile>.log`。

状态文件记着这次启动所处的阶段，有三个值：`downloading`、`starting`、`running`。

**守护进程活着，等于它拿着 `<profile>.run` 这把锁。**

- 它从启动到退出一直拿着这把锁，进程一死，内核就会把锁放掉。所以，判断“活着”看的是这把锁拿不拿得到，不看 pid：状态文件留了下来、pid 被别的进程复用，都不会被误认作我们的服务。
- 第二个守护进程拿不到这把锁，就直接退出。
- 这把锁的文件描述符不能传给子进程。`Popen` 默认 `close_fds=True` 就够了，只是不要传 `pass_fds`。
- 下载用的 `hf` 和 vLLM 一样：自成一个会话（`start_new_session`），并且随守护进程一起死（`PR_SET_PDEATHSIG`）。否则下载时 `down`，会留下一个孤儿进程，接着往根目录里下载。

**空闲计时从服务第一次应答 `/health` 时开始。**

- 加载慢的服务，不会在加载过程中被当成空闲停掉。

**这样，原来散在 `up` 里的几件事都变成同一件事：**

- 下载看不到进度：现在下载的进度也在日志里，`status` 能看出它正在下载。
- 下载停不下来：现在 `down` 能停掉任何阶段，正在下载的也一样。
- `download_failed` 不再单列：下载失败就是这次启动失败，日志里有 hf 自己的报错。
- 原来把下载放在 `up` 里、排在启动之前，是为了“不占启动期限”。现在没有期限了，这个理由也就没了。

### 3.2 `up`：短暂拿锁做决定，在锁外等

状态目录里只有一把决定锁 `decide.lock`，所有 profile 共用，取代原来每个 profile 一把的 `.lock`。

- 不同 profile 的启动决定，也就排成了先后，“同端口上另一个 profile 有没有活着的服务”这一查因此是确定的事实。
- 每次决定只拿几秒，跨 profile 排队几乎没有代价。

这把锁只管两件很短的事，从不在锁里等待：

- **决定要不要起服务。**
  - 已有活着的守护进程，就用它。
  - 没有的话，先查两件确定的事：
    - 同一端口上，另一个 profile 有没有活着的服务。有，就报 `port_busy` 并点出它的名字。
    - 端口上有没有别的东西应答。只要连得上，不管它回的是 HTTP 还是别的，都报 `port_busy`。
  - 两件都没有，就起守护进程，等到下面两种结果之一出现（只需几秒，结果是确定的），然后放开锁：
    - 它拿到了运行锁、写好了状态；
    - 它已经退出，比如一导入就崩了。这种情况直接报 `server_failed`，不会挂住。
- **交出服务。**
  - 先确认守护进程不在停止的过程中，再 `touch`。
  - 拿到锁时，如果运行锁已经放开，或者状态显示正在停止，就回到“决定要不要起服务”那一步。
  - 守护进程决定空闲自停时，也在这把锁里决定，所以不会把正在停的服务交出去。

在锁外，`up` 一直等，直到状态里记下的地址上 `/health` 返回 200，或者守护进程退出（运行锁被放开），不计时。

- **守护进程退出时**，报 `server_failed`：写明它是在哪个阶段退出的，附日志路径和最后 20 行。
- **启动时的那行提示里写出日志路径**：`[vllm-serve] starting <profile> …; log: <路径>`。

**判断就绪的探测**

- 只有返回 200 才算就绪。
- 连不上、超时、回的不是 HTTP，都算“还没好”，不会让 `serve.py` 崩溃。

**返回给调用方的内容**

- 对一个已在运行的服务，返回的 `url`、`model`，以及所有探测用的端口和地址，都取自状态文件，不取当前的 profile。
- profile 改过（模型、端口、参数）或换了卡，就附上 `differs`。

### 3.3 `down` 与 `status`

**`down`**

- 有活着的守护进程，就在决定锁里给它发 SIGTERM、把状态标成 `stopping`（只拿一瞬间，见第 7 节），然后在锁外等它退出。守护进程先停 vLLM（或下载），再退出。正在等的 `up` 看到它退出，就报 `server_failed`。
- `down` 等运行锁被放开，最多等 90 s。
- 停不了别的登录的进程时，报 `not_permitted`。

**`status`**

- 显示：阶段、启动者、卡、负载、日志路径。
- 地址取自状态文件。

### 3.4 其余机制的去留

去留按“基本的不漏，想象的不防”来定：

| 机制 | 去留 | 理由 |
| --- | --- | --- |
| `extends` | 留 | 遇到过：项目为两台主机各复制了一份 profile |
| `up -- <参数>` | 留 | 遇到过：换卡时用 sed 改 profile |
| 从参数里读 `--host`、`--revision` | 留 | 遇到过（issue 第 5、10 条） |
| 按版本下载、判断是否已缓存 | 留 | 遇到过（第 10 条） |
| `status` 显示负载 | 留 | 遇到过（第 14 条） |
| `differs` | 留，补上模型和端口 | 遇到过：profile 改过后，`up` 不提示 |
| `not_permitted` | 留 | 遇到过（第 17 条） |
| profile 里出现未知的键就报错 | 留 | 本该考虑：格式改了以后，旧键会被悄悄忽略 |
| `idle_minutes` 必须大于 0 | 新增，与上一条同理 | 本该考虑：10-30 版里 0 表示“不自停”，删掉这个含义以后，旧写法必须报错，不能悄悄变成“马上停” |
| profile 的 env 优先于调用方的环境变量 | 留 | 从 10-09 起就是这样（`server_env` 最后才套上 profile 的 env）；10-30 曾经反过来，后来又改回来了 |
| 访问本机的服务不走代理 | 留 | 本该考虑：本机就设着代理 |
| `CUDA_DEVICE_ORDER=PCI_BUS_ID` | 留 | 本该考虑：文档让 agent 按 `nvidia-smi` 的编号选卡 |
| 调用方带来的 `CUDA_HOME`、`CUDA_PATH`，在没有自带工具包的环境里去掉 | 留 | 本该考虑：是“一个环境一份 CUDA”这条既有规则的一部分 |
| 把 `CUDA_LIB_PATH` 指向环境自己的 CUDA runtime | 删 | 想象的：10-30 版本来只打算在主机 A 报出 `foreign_cuda` 时才加 |
| 调大 `VLLM_ENGINE_READY_TIMEOUT_S` | 留 | 遇到过（第 2 条） |
| `VLLM_USE_FLASHINFER_SAMPLER=0` | 先实测再定 | 去掉它是“引擎自带、一个开关”的大众优化；但“收益小”从没量过（第 5 节第 3 步） |
| 10 分钟计时 | 删 | 替 agent 判断“卡死”（§1）；慢启动、静默很久的阶段都确实遇到过 |
| vLLM 加载 30 分钟上限，下载不计 | 新增（实现中定，见第 2 节） | 本该考虑：没人看着时，卡住的启动会一直占着共享的卡；实测最慢的阶段是 27B 首次启动现编 kernel 约 6 分钟、从快满的盘读权重 7–8 分钟 |
| 日志末行写怎么结束的、保留上一份日志、下一次 `up` 和 `status` 报出上次失败 | 新增（实现中定，见第 2 节） | 本该考虑：没人看着时失败了，后来的 agent 要能知道，证据也要留着 |
| “第一条错误行” | 删 | 用正则替 agent 挑原因，是个匹配器（§1）；“原因在日志末尾之上”的问题，靠 agent 读日志来解决 |
| 在 `/v1/models` 里核对模型名 | 删 | 归属由运行锁和状态文件判断 |
| `--api-key` 时带上密钥 | 删 | 改用 `/health` 后自然不需要 |
| 启动前试绑端口 | 删 | 由“端口上连得上就报 `port_busy`”和“同端口的另一个 profile”两项取代：这两项是确定的，试绑反而会和正在加载、还没开始监听的 vLLM 撞上 |
| `idle_minutes = 0` 表示不自停 | 删 | 想长开写一个大数就行，这个特殊值是多余的 |
| `::1` 被换成 127.0.0.1 | 改 | 低级错误：只有 `0.0.0.0`、`::` 和没写时才换成 127.0.0.1；IPv6 地址放进 URL 时加方括号 |

### 3.5 交接写进 SKILL.md

SKILL.md 不再复述 `--help` 里的字段和错误码含义，只写碰到时该怎么做。具体错误的处理只放在 install.md 的排障里，SKILL.md 只指过去。

| 停下的地方 | 谁接手 | 看什么、做什么 | 接着运行 |
| --- | --- | --- | --- |
| `server_failed` | 调用方 agent | 在下一次 `up` 之前读日志：重新启动会覆盖它。日志长就派一个后台 sonnet subagent，brief 给它日志路径和 install.md 的排障一节，让它带回原因那几行和对应的条目。然后按 install.md 改：改 profile、换卡、装缺的东西、等卡空出来，或者 `down` 掉我们自己空闲的服务 | `up` |
| 后台的 `up` 迟迟不返回 | 调用方 | `status` 看阶段，日志看还有没有进展：下载在不在动、在哪一步；再对照 install.md 的 “Timings” 和其中关于静默阶段的提示，以及 `nvidia-smi` 的显存是不是还在涨 | 判断卡住了就 `down`，正在等的 `up` 会返回 `server_failed` |
| `port_busy` | 调用方查清事实，只有要停别人在用的服务，或者端口上是用户自己手动起的服务时，才问用户 | `detail` 点出的 profile 用 `status` 看是否空闲；别的程序用 `ss -ltnp`、`ps -o user= -p <pid>` 查 | 自己的两个 profile 撞了端口，就给部署 profile 一个自己的端口，然后 `up` |
| `not_permitted` | 那个登录，或者用户 | `detail` 写明属于谁 | 由那个登录 `down`，或者等它空闲自停；root 所有的文件由用户 `chown`，之后 `up` |
| `vllm_missing` | 调用方 | install.md；告诉用户一声即可，不用等点头 | 装好后 `up` |
| `unknown_profile` | 调用方 | 照 `detail` 改 profile：名字写错、未知的键、`extends` 循环、缺 `model` 或 `port`、`idle_minutes` 不大于 0 | `up` |
| `differs`（随成功一起返回） | 调用方 | 运行中的模型、端口、参数和卡 | 照用即可；要让改动生效，等 `status` 显示空闲后 `down`，再 `up` |
| `foreign_cuda`（随成功一起返回） | 调用方，再报给用户 | install.md 里讲 `foreign_cuda` 的那一条 | 修好后 `down`，再 `up`；返回里不再有 `foreign_cuda` 才算好 |
| `status` 里某个 profile 一行报错 | 调用方 | 同 `unknown_profile` | `status` |
| 上一次启动没人看着时失败了（`up` 打印 “the last start … failed”，或 `status` 的 `last` 里 `failed` 为 true） | 调用方 | 读那份日志，同 `server_failed` | 改好再 `up` |
| 在共享机器上选卡 | 调用方 | shared-machines.md | 要保留就写进部署 profile 的 env，只用一次就放在调用方的环境里，然后 `up` |

### 3.6 其他文档

- **install.md**
  - 装 vLLM 前告诉用户一声就行，不用等点头：它是 uv 包。
  - 排障部分：
    - 删掉“10 分钟没写日志”那一条。
    - 改写成关于静默阶段的提示，只写确实遇到过的：首次启动没装预编译 kernel 时，FlashInfer 要下载、编译好几分钟；`CUDA_MODULE_LOADING=EAGER` 曾让引擎停在 “Initializing a V1 LLM engine” 好几分钟。
    - 加上 “Address already in use” 一条，下载失败那几条也并进来。
  - “What serve.py sets” 表：调大 `VLLM_ENGINE_READY_TIMEOUT_S` 的理由改成“`up` 等服务自己应答或退出”。
  - “Weights” 一节：下载的进度在日志里。
- **shared-machines.md**
  - 例子里用户服务器上的真实目录换成占位符。
  - 删掉和 SKILL.md 重复的“本次启动和 profile 的分工”。
  - `idle_minutes = 0` 改成“写一个足够大的数”。
  - “部署 profile 要和被继承的同名，否则要有自己的端口”只留理由：撞了端口时，`up` 会点名报出。
  - 下载一步改成：大模型的第一次 `up` 放到后台跑，进度看日志。
- **paddleocr/SKILL.md**：`parse.py` 在前台调用 `up`，而且不设超时。
  - 加交接：停在 “[paddleocr] asking vllm-serve …” 好几分钟时，读 vllm-serve 的日志（`serve.py status` 会告诉你在哪），判断卡住了就 `serve.py down paddleocr-vl`，这次解析会转去原生后端。
  - 手动起的 PaddleOCR-VL 占着 8118 时报 `port_busy`，这时改用 `--vl-server <url>`。
  - 改掉“30–60 s 启动”那句。
- **serve.py 的注释和 `--help`**
  - `MACHINE_ENV` 的注释只指向 install.md 的那张表，不再复述。
  - docstring 里的“日志在增长就等”“第一条错误行”“0：不自停”`download_failed` 都改掉。
- **issue**：引用的用户原话里，服务器上的真实目录也换成占位符，和 skill 文件一致。
- **不改**：tuning.md 和两个 profile。

### 3.7 不做

- **“一个部署交给一个 subagent”的机制**：见第 2 节。
- **把 503 当成失败**（只有设了 `VLLM_KEEP_ALIVE_ON_ENGINE_DEATH=1` 才会一直 503）：这是想象出来的问题。

## 4. 文件

- `vllm-serve/scripts/serve.py`、`vllm-serve/tests/test_serve.py`
- `vllm-serve/SKILL.md`、`vllm-serve/references/install.md`、`vllm-serve/references/shared-machines.md`
- `paddleocr/SKILL.md`
- `docs/specs/20261030-vllm-serve-shared-machines-spec.md`：顶上加一行，写明被取代的部分
- issue：记下进展，原话里的目录换成占位符
- `docs/design-principles.md`：本次补的那一句单独提交，它不属于 vllm-serve 返工的范围

## 5. 验证

1. **测试**。全部在设了失效代理的环境里跑；替身 vllm 要有真正的 `/health`。
   - 改写现有测试：
     - 慢启动的测试：去掉“停住即失败”那一半；
     - 端口被占的测试：分成三种情况：别的程序连得上、同端口的另一个 profile、profile 改过以后得到 `differs`；
     - 所有用到 `answers()` 的地方。
   - 新增测试：
     - `up` 在等待时执行 `down`，几秒内返回，`up` 报 `server_failed`；
     - 第一个 `up` 中途被杀，第二个 `up` 接着等到服务起来；
     - 状态文件过时（守护进程已死、pid 被复用）时，不当作在运行；
     - 服务运行期间 profile 的端口和模型改了，`up` 返回运行中的那个，并附 `differs`；
     - `idle_minutes = 0` 被拒；
     - 另一个 profile 还在加载、就占着同一端口时，报 `port_busy` 并点名；
     - 端口上回的不是 HTTP 时，报 `port_busy`，`serve.py` 不崩溃；
     - 下载阶段可以被 `down` 停掉，日志里有下载的输出（用一个替身 hf）。
2. **本机实测**：先用旧的 `serve.py` 执行 `down --all`。旧代码起的服务不拿运行锁，新代码会把它当成别人的服务，报 `port_busy`。2026-10-31 查过，本机此时没有在跑的服务。然后用新的 `serve.py`（本机 vLLM 0.31）对 `paddleocr-vl` 做一遍 `up`、paddleocr 解析、`status`、`down`；再做一次“`up` 在后台、中途 `down`”。
3. **FlashInfer 采样器**：在一个新根目录里装 0.32.0 加预编译 kernel（包都在 uv 缓存里），对 `paddleocr-vl` 发带 temperature、top_p、top_k 的请求，比较打开和关闭采样器：能不能用、快多少。小模型上采样所占的比例比 27B 大，量出来的是收益的上限。能用且有收益，就从默认设置里去掉这一条，本机 0.31 怎么处理（升级，或在本机的 profile 里关掉）交给用户定；没有收益就保留，把量到的数写成理由。
4. **最后全部过一遍**：
   - 我从头读一遍所有改过的文件；
   - 再派两个只读评审：一个看低级错误和技术正确性，一个看原则和设计；
   - 再派一个没看过对话的 agent，照新的交接表走一遍“远程部署”和“paddleocr 调用时服务卡住”两个场景。
5. **SKILL.md 的改动**（vllm-serve 和 paddleocr 两份）：按 design-principles §4，逐条给用户看原文和修改建议。
6. **两台服务器实测**：仍等用户决定是否放行，即 10-30 spec 第 6 节第 3、4 条，其中包括数据并行时 `/metrics` 是否覆盖所有副本。

## 6. 两份评审的处理

两份独立评审是 2026-10-31 在实现前做的：一份看低级错误和技术正确性，14 条；一份看原则和设计，15 条。很多条两边重复。

**采纳。**

- 锁和等待：两边都把它列为第 1 条，见 3.1–3.3。
- 过时的状态和被复用的 pid：改用运行锁，见 3.1。
- 探测取状态里的地址，返回运行中的模型，见 3.2。
- 同端口的另一个 profile，以及端口上连得上的别的程序，见 3.2。
- 回的不是 HTTP 时不会崩溃，见 3.2。
- `idle_minutes = 0` 被拒，四处文字一起改，见 3.4、3.6。
- 测试清单，见第 5 节。
- 交接表补全，并写清读日志的 subagent 的 brief 和它带回什么，见 3.5。
- paddleocr 这个调用方，见 3.6。
- 文件头里被取代部分的数目和清单，见文件头。
- 去留表里的几条理由原本写错了，见 3.4。
- 显存不够只放在 install.md 一处讲，见 3.5。
- `port_busy` 的事实由 agent 自己查，见 3.5。
- 选卡那一行和“这一次启动”的说法一致，见 3.5。
- 注释和 `--help` 是第二处家，见 3.6。
- issue 里的目录也换成占位符，见 3.6。
- design-principles 那一句单独提交，见第 4 节。
- 在新交接表上做一次新 agent 视角的走查，见第 5 节。
- `::1`，见 3.4。
- design-principles §1 补一句适用范围（评审的建议）：用户同意，已写进。

**换一种方式采纳。**

- 守护进程活着的判断：评审建议用 `/proc/<pid>/cmdline` 或进程的启动时间；这里改用运行锁，由内核负责放锁，最确定。
- 重试会覆盖日志：评审建议日志改成追加写，或保留上一份；这里只在交接里写“下一次 `up` 之前先读日志”，不加新机制。
- 下载卡住没有出路：评审建议给下载单独设一条路；这里把下载挪进守护进程，让它和启动成为同一件事。
- FlashInfer 采样器：评审建议直接去掉这条默认设置；这里先实测再定。

**没采纳。**

- 永远 503 的情况：想象出来的问题，见 3.7。
- 把 “profile 的 env 优先” 交给用户定：这不是新决定，从 10-09 起就是这样，10-30 只是短暂地反过来过。

## 7. 实现记录

2026-10-31。

**实现时定下、和上文不同的几处**

- `down` 也拿决定锁，但只在锁里读状态、发 SIGTERM、标上 `stopping`（几毫秒），等守护进程退出在锁外。3.3 原写“不需要拿锁”；不拿的话，新守护进程刚拿到运行锁、还没写状态的那一瞬间，`down` 会读到上一个守护进程留下的 pid。启动守护进程的 `up` 要等新状态写好才放锁，所以经过这把锁的 `down` 读不到旧 pid。`down` 只等它发了信号的那个守护进程退出：期间另一个 `up` 起了新的，不算没停。
- 任何一条退出的路（`down`、vLLM 自己退出、空闲自停），守护进程都先在决定锁里标上 `stopping`，再停子进程：停的过程中不会有 `up` 拿到它。`up` 碰到 `stopping` 就等它走完再起新的；`server_failed` 里写的仍是被停之前的阶段。
- 停子进程时等整个进程组退干净（先 SIGTERM，30 s 后 SIGKILL），之后才放开运行锁：下一次启动不会撞上还没释放的显存或端口。
- 判断“活着”：只读打开 `<profile>.run`，试拿共享锁（`LOCK_SH|LOCK_NB`），拿不到就是活着。守护进程拿排他锁时重试 2 秒，避开别人探测的那一瞬间；2 秒还拿不到，说明另一个守护进程在跑，就退出。
- 对运行中的服务，`down` 和 `status` 只看状态文件，不读 profile：profile 改坏了也停得掉、看得到。`down --all` 和 `status` 覆盖 profile 名加上正在跑的名字，`down --all` 碰到一个报错接着停后面的；`down` 一个既不在跑、也没有 profile 的名字，报 `unknown_profile`。
- `status` 用 `phase` 取代 `running`：`stopped`、`downloading`、`starting`、`running`、`stopping`。
- 下载用的 `hf` 和判断是否已缓存，都用调用方环境加上 profile 的 env，和 vLLM 一致：profile 里写了镜像或别的缓存目录，下载和离线启动都跟着走。
- 状态文件先写临时文件再改名；profile 不是合法 TOML 时报 `unknown_profile`，不再让 `status` 整个崩掉。
- 一个根目录只归一个登录：别的登录在那里得到 `not_permitted`，写明属主；换人用 `chown` 交接（shared-machines.md 原写“共用根目录的登录共用状态”，文件是 644，本来就不成立）。
- shared-machines.md 第 4 步：skill 只装在本机，服务器上的是 serve.py 的一份副本，经 ssh 调用；更新副本前，先等 `status` 显示空闲，用旧副本 `down --all`，因为新版认不出旧版起的服务。起因是一个旁路 agent 的提醒，用户补充：「一般我不会在训练公共服务器上去安装 skills，我都是通过本机的 Agent（比如 Claude Code 或其他 harness）去调用我自己本机上安装的 skills，然后让它通过 SSH 去操作」。

**验证**

- 测试：25 个，全部通过，约 85 s；加载上限和“上一次怎么结束”都有测试，包括下载时间不计入上限、过时的状态文件算作“死前没留记录”。
- 本机实测（vLLM 0.31，RTX 5090 D）：`up paddleocr-vl` 130 s 起来（其中 CUDA graph 捕获 76 s，比 Timings 原写的 25–50 s 长，已补进 install.md）；paddleocr 解析一页有标题、正文和表格的 PDF，backend `vllm-server`，`checks: ok`，内容逐字对；`status` 显示 `running` 和负载；`down` 2 s。后台 `up`、启动中途 `down`：`down` 32 s 返回（vLLM 在捕获 CUDA graph 时不理 SIGTERM，30 s 后被 SIGKILL），等着的 `up` 返回 `server_failed`，日志最后一行是 `[vllm-serve] SIGTERM (serve.py down, or the system): stopping`，没有残留进程，显存回到启动前。旧代码的 `down --all` 没跑：动手前查过，本机没有在跑的服务。
- FlashInfer 采样器（第 5 节第 3 步）：新根目录装 0.32.0 加 `vllm download-kernels`（安装 1.5 min，kernel 11 min，其中 jit-cache 要现下），`paddleocr-vl`，每轮 512 个请求、128 并发、每个固定生成 512 token，带 temperature 0.8、top_p 0.9、top_k 50。打开采样器能用（日志 “Using FlashInfer for top-p & top-k sampling.”），预热后 5 轮 45–54k token/s，中位数 51k；关闭 5 轮 53.6–54.9k，中位数 54k。没有收益，保留 `VLLM_USE_FLASHINFER_SAMPLER=0`，量到的数写进 install.md 当理由；本机 0.31 不用动。
- 最后一遍：我自己通读；两份只读评审（技术正确性 11 条加文档、测试几处；原则和设计 9 条）；一个没看过对话的 agent 照 SKILL.md 稿子走“远程部署”和“paddleocr 等服务卡住”两个场景（10 条）。采纳的已改：`down` 不标 `stopping`（两份评审都提了）、profile 写坏会让 `status` 崩、停子进程不等进程组、判断缓存不看 profile 的 env、被杀的 `up` 之后误报失败、`down --all` 遇错就停、锁里复查空闲的超时缩到 2 s、第二个 SIGTERM、符号链接竞争、`server_failed` 和 `port_busy` 的交接写法（远程日志经 ssh、子 agent 的模型名、可直接复用对方的服务）、“判断卡住”的标准、显存不够时别停别人在用的部署、已有根目录直接用、Verify 的 `up` 等选好卡再做、paddleocr 卡住后要查原因。没采纳：多个登录共用一个根目录（改成写明一个根目录归一个登录）、超长部署的选卡提醒、把要问用户的决定攒到一起问（和“一次只问一个”冲突）。
- 实现中又定了两条，见第 2 节：vLLM 加载 30 分钟上限；出了问题让后来的 agent 知道去查。代码、测试、install.md 和 shared-machines.md 已改，两份 SKILL.md 的稿子同步改了。
