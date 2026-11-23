> 已解决（2026-11-23）：脚本改了两处（rev 2026-11-23.1）。登记写不进清单时，`sync` 单独输出一行 `not_registered`，带清单文件的路径、原因和后果；`-n` 试运行时的提示改成「文件里的块不是最新的，这次什么都没写」。文字只加了一句：`SKILL.md` 的 *The sync* 一节说明同步会把项目路径记进清单。「记 issue 是项目之外唯一的写入」那句没改，用户：「configure 下去配置本身就无所谓啊……是我们这个 HWW 系统的一部分，我怎么感觉你这里有一点牵强或者强制了……感觉过度了」；`adopting.md` 的验收也没加。临时目录里跑同步会被登记进清单不算毛病：脚本留了环境变量 `HOW_WE_WORK_CONFIG` 把清单指到别处，测试就这么用。

# how-we-work：`sync` 登记项目写不进配置时没有任何提示，而且这一步写在规则文字里找不到

- **来源 · 日期**：skills 仓库的会话，在用户让记两个新接入的项目时发现 · 2026-11-17。
- **涉及的文字**：`how-we-work/scripts/hww.py` 的 `register()`（第 318 行）和 `main` 里对它的调用（第 393–394 行）；`how-we-work/SKILL.md` 的 *An issue in the skills repository* 一节最后一句；`references/adopting.md`、`common.md`（都没提登记）。

## 背景

`hww.py sync` 在项目里真跑时，把项目路径写进 `~/.config/how-we-work/config.json` 的 `projects`。skills 仓库的会话发布之后"逐个同步清单上的项目"、做对账时读的就是这张清单（`references/maintaining.md` *Reconciling the projects*）。清单是接入的记录：接入时 `sync` 自动登记，是个好设计，用户看了之后也这么说。

2026-11-17，用户说他把 `us-enhancement-demo` 和 `Hub/network` 两个项目接入了 hww，让记一下，并问要不要维护接入表。

## 用户原话

- 2026-11-17，让记接入时：「记一下 我把……接入进hww，我感觉你最好维护一个接入表，这样是不是会更方便？」
- 同一天，我说明我在 `us-enhancement-demo` 里跑了 `sync`、清单多了一行之后：「我以前不知道是有~/.config/how-we-work/config.json 你这次动了什么东西吗」
- 同一天，听完说明：「所以现在的变动是接入的时候就会记录是吗，还是你时候去修改的，我觉得这个设计挺好，接入就会记录config」
- 同一天：「要不要提一个issue」

## 现场

- 清单（`~/.config/how-we-work/config.json`）11-12 08:29 创建，当时 4 项。
- `us-enhancement-demo`：它自己的会话 2026-11-16 14:42（+0800）提交了接入（提交 `40ea3d1`，改了 `AGENTS.md` 和 `README.md` 里的一行），区块是 `rev 2026-11-14.1`，当前。可 2026-11-17 13:45 读清单时，它不在上面。
- `network`：它自己的会话 2026-11-17 13:45（北京时间）提交了接入（提交 `fd14b66`），清单文件的修改时间与这次提交同一分钟，它自己登记了。
- 在 `us-enhancement-demo` 里先跑 `hww.py sync -n`，输出 `{"code": "ok", "file": "AGENTS.md", "block": "current"}`；再真跑，输出多了 `"registered": true`，清单变成 6 项，项目目录里 `git status` 干净。
- 为什么它接入时没登记，查不出来。`register()` 遇到 `OSError` 或 `ValueError` 返回 `False`，调用处只在返回 `True` 时才输出 `registered`。所以"这个项目已经在清单上"和"写失败了"的输出一模一样，都是没有这个字段，接入的会话和用户都看不出来。
- 登记这一步在规则文字里没有：`hww.py -h` 的说明里有，`common.md`、`adopting.md`、`SKILL.md` 的 *The sync* 一节都没有。`SKILL.md` 的 *An issue in the skills repository* 还写着「Logging the issue, that line of the config included, is the one thing a project's session writes outside its project」，而 `sync` 的登记也是项目之外的写入，每个项目每次接入都会做。用户事先不知道有这个文件。

## 为什么要紧

- 漏登记的项目会被发布后的同步和对账静默跳过，直到有人碰巧对一遍清单；`us-enhancement-demo` 就是这样差点漏掉的。
- 用户事先不知道 `sync` 会写 `~/.config`；这和 `AGENTS.md`「Write only inside this project」的例外只列了提 issue 一项，不一致。

## 方向（没拍板）

1. `register()` 写失败时，`sync` 输出一个明确的字段，如 `"registered": "failed"`，带 hint 说是哪个文件写不了；新登记（`true`）、已在清单上（不输出）两种情况不变。这样接入的会话能当场看见并告诉用户。
2. 规则文字里补一句：`sync` 会把项目登记进 `~/.config/how-we-work/config.json`，这是它在项目之外唯一的写入；放在 `SKILL.md` 的 *The sync* 一节，并改正 *An issue in the skills repository* 里"唯一"的说法。是否也写进 `adopting.md` 的验收（"这个项目在清单上"），待定。
3. 漏登记的原因是推测：区块手工复制过去没跑 `sync`，或者那次的环境写不了 `~/.config`（沙箱）。没有证据，修改不依赖它。

改 `SKILL.md` 和 `adopting.md` 的文字是规则文字的改动，要先问用户；改脚本的输出字段属于代码，由 skills 仓库的会话直接做。

## 同一个命令的另一个毛病（2026-11-23 并进来）

2026-11-18 对照 OpenAI 官方建议的那次调研复现过：在临时目录里放一个旧的块，跑 `hww.py sync -n`，输出里同时有 `block: updated`、`dry_run: true` 和提示「The block changed: read it again from the file」，而 `AGENTS.md` 前后的 SHA-256 相同，什么都没写。试运行时这句提示和磁盘上的状态不符。测试没拦住，因为试运行的用例把 `hint` 去掉了再比。经过在已归档的 `docs/issues/archive/20261118-how-we-work-codex-configuration-wontfix.md` 和它的参考材料 `hww-review.md` 里。改法：`-n` 时不带这句提示，或者换成「会变」的说法；和登记失败的输出一起改。没拍板。

## 状态

已解决（2026-11-23，决定 D20261123-11）。
