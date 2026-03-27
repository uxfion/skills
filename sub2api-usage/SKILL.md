---
name: sub2api-usage
description: >
  Sub2API 用量查询与报告。当用户询问任何关于 sub2api 的用量、花费、token
  消耗、限额、谁用了多少钱、今天总体情况等问题时，立即使用此 skill。
  同样适用于定时巡检场景：每隔几小时生成一份与上次对比的周期报告，找出
  谁在这段时间内用量猛增、谁接近或触碰了日/周限额。
  触发关键词示例：sub2api 用量、今天用了多少、哪个 key 快到限额了、
  给我出一份用量报告、3 小时用量、token 消耗情况。
---

## 脚本位置

脚本位于本 SKILL.md 同级目录下：

```
sub2api-usage/scripts/fetch_usage.py
```

## 运行方式

使用 `uv run` 执行（脚本通过 PEP 723 内联声明依赖，无需额外安装）：

```bash
# 普通查询（只看当前）
uv run sub2api-usage/scripts/fetch_usage.py

# 周期报告（与上次快照对比，并保存本次为新快照）
uv run sub2api-usage/scripts/fetch_usage.py --report
```

脚本输出纯 JSON，从中读取数据后用自然语言回答用户。

## 环境变量

脚本按优先级加载配置：先读 `~/.openclaw/.env`（全局），再读 `sub2api-usage/.env`（技能目录，优先级更高可覆盖全局值）。需要以下变量：

| 变量 | 说明 |
|------|------|
| `SUB2API_URL` | Sub2API 服务地址 |
| `SUB2API_ADMIN_KEY` | 管理员 API Key |
| `SUB2API_USER_ID` | 要查询的用户 ID |

## 输出字段说明

### `summary`
| 字段 | 含义 |
|------|------|
| `total_today_tokens` | 今日所有 key 合计 token（含 cache） |
| `total_today_cost`   | 今日总花费（$） |
| `total_all_cost`     | 所有 key 累计总花费（$） |

### `keys[]`（每个 key）
| 字段 | 含义 |
|------|------|
| `today_tokens`  | 今日 token 用量（含 cache） |
| `today_input/output/cache` | token 细分 |
| `today_requests` | 今日请求次数 |
| `today_cost`    | 今日花费（$） |
| `total_cost`    | 累计总花费（$） |
| `usage_1d / limit_1d / pct_1d` | 日限已用 / 日限额（$） / 占比% |
| `usage_7d / limit_7d / pct_7d` | 周限已用 / 周限额（$） / 占比% |

### `delta`（仅 `--report` 模式）

delta 仅在**同日内两次运行**之间有效。跨日时 today 计数器已重置，脚本会将 `delta` 设为 `null` 并附带 `delta_note` 说明原因。

| 字段 | 含义 |
|------|------|
| `period_from/to` | 两次快照的时间戳 |
| `delta_tokens`   | 周期内新增 token |
| `delta_cost`     | 周期内新增花费（$） |
| `key_deltas[]`   | 各 key 的 delta，按用量降序排列 |

## 回答指南

### 普通用量查询
- **汇总先行**：先说今日合计 Mtoken（`total_today_tokens / 1_000_000`，保留两位小数）和花费。
- **限额预警**：`pct_1d >= 80%` 或 `pct_7d >= 80%` 时，明确标出警告，并说明剩余额度。
- **按需展开**：若用户问"谁用了多少"，列出各 key 的今日 Mtoken 和花费；若只问总量，给总量即可。
- **数字格式**：token 换算成 Mtoken（保留两位小数），花费保留两位小数但精确到分（`$1.53`）。

### 周期报告（`--report`）

#### delta 有效时（同日内两次运行）
重点展示**变化**，而非静态状态：

1. **周期摘要**：本段新增 X Mtoken、$Y，时间区间 HH:MM -> HH:MM。
2. **活跃排名**：列出本段用量 top 3 的 key（delta_tokens 最高），指出谁"猛用"。
3. **今日累计**：今日已合计 X Mtoken、$Y，各 key 当日占限额的百分比。
4. **限额告警**：接近或超出限额的 key 单独列出，注明还剩多少。
5. **安静时段**：若某 key 用量 delta 为 0，不必逐个列出，一句"其余 N 个 key 本段无活动"带过。

#### delta 无效时（快照跨日或无历史快照）
当 `delta` 为 `null` 时，说明快照来自不同日期（或不存在）。此时：

1. 简要说明原因（如"上次快照为 X 天前，跨日后 today 计数器已重置"）。
2. **直接基于今日累计数据汇报**，格式同"普通用量查询"。
3. 不要尝试解读 delta 数值，也不要输出无意义的负数。

---

> **注意**：`usage_1d` / `usage_7d` 是系统以**花费（$）**衡量的滚动窗口用量，与 `today_cost` 来源略有差异（时间窗口计算方式不同）。限额告警以 `pct_1d` / `pct_7d` 为准。
