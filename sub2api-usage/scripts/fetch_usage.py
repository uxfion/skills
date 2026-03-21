# /// script
# dependencies = ["httpx", "python-dotenv"]
# ///
"""
Sub2API 用量数据抓取脚本

用法:
  uv run fetch_usage.py             # 抓取当前数据，输出 JSON
  uv run fetch_usage.py --report    # 与上次快照对比，输出含 delta 的 JSON
  uv run fetch_usage.py --save      # 抓取数据，保存快照，输出 JSON

快照保存路径: 脚本同级目录的 snapshot.json
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
import httpx

# ── 环境变量加载 ──────────────────────────────────────────────
script_dir = Path(__file__).parent
# .env 与 SKILL.md 同级（scripts/ 的上一级）
skill_env = script_dir.parent / ".env"
load_dotenv(dotenv_path=skill_env if skill_env.exists() else find_dotenv())

BASE_URL = os.environ.get("SUB2API_URL", "").rstrip("/")
ADMIN_KEY = os.environ.get("SUB2API_ADMIN_KEY", "")
USER_ID   = int(os.environ.get("SUB2API_USER_ID", "1"))

SNAPSHOT_PATH = script_dir.parent / "snapshot.json"

if not BASE_URL or not ADMIN_KEY:
    print(json.dumps({"error": "缺少 SUB2API_URL 或 SUB2API_ADMIN_KEY 环境变量"}))
    sys.exit(1)

HEADERS = {"x-api-key": ADMIN_KEY}


def get_keys(client: httpx.Client) -> list[dict]:
    r = client.get(f"{BASE_URL}/api/v1/admin/users/{USER_ID}/api-keys", headers=HEADERS)
    r.raise_for_status()
    return r.json()["data"]["items"]


def get_key_today_stats(client: httpx.Client, key_id: int) -> dict:
    today = date.today().isoformat()
    r = client.get(
        f"{BASE_URL}/api/v1/admin/usage/stats",
        headers=HEADERS,
        params={"api_key_id": key_id, "start": today, "end": today},
    )
    r.raise_for_status()
    return r.json()["data"]


def get_keys_cost(client: httpx.Client, key_ids: list[int]) -> dict:
    r = client.post(
        f"{BASE_URL}/api/v1/admin/dashboard/api-keys-usage",
        headers=HEADERS,
        json={"api_key_ids": key_ids},
    )
    r.raise_for_status()
    return r.json()["data"]["stats"]  # {str(id): {today_actual_cost, total_actual_cost}}


def fetch_all(client: httpx.Client) -> dict:
    keys = get_keys(client)
    key_ids = [k["id"] for k in keys]

    # 并发感：先发批量 cost 请求，同时循环取 per-key stats
    cost_map = get_keys_cost(client, key_ids)

    key_data = []
    total_today_tokens = 0
    total_today_input  = 0
    total_today_output = 0
    total_today_cache  = 0
    total_today_cost   = 0.0
    total_all_cost     = 0.0

    for k in keys:
        kid   = k["id"]
        stats = get_key_today_stats(client, kid)
        cost  = cost_map.get(str(kid), {})

        today_tokens = stats.get("total_tokens", 0)
        today_input  = stats.get("total_input_tokens", 0)
        today_output = stats.get("total_output_tokens", 0)
        today_cache  = stats.get("total_cache_tokens", 0)
        today_cost   = cost.get("today_actual_cost", 0)
        total_cost   = cost.get("total_actual_cost",  0)

        total_today_tokens += today_tokens
        total_today_input  += today_input
        total_today_output += today_output
        total_today_cache  += today_cache
        total_today_cost   += today_cost
        total_all_cost     += total_cost

        usage_1d  = k.get("usage_1d") or 0
        limit_1d  = k.get("rate_limit_1d") or 0
        usage_7d  = k.get("usage_7d") or 0
        limit_7d  = k.get("rate_limit_7d") or 0

        key_data.append({
            "id":            kid,
            "name":          k.get("name") or f"key-{kid}",
            "status":        k.get("status", "unknown"),
            # 今日 token 细分
            "today_tokens":  today_tokens,
            "today_input":   today_input,
            "today_output":  today_output,
            "today_cache":   today_cache,
            "today_requests": stats.get("total_requests", 0),
            # 费用
            "today_cost":    round(today_cost, 6),
            "total_cost":    round(total_cost, 6),
            # 限额（单位：$）
            "usage_1d":      round(usage_1d, 4),
            "limit_1d":      limit_1d,
            "pct_1d":        round(usage_1d / limit_1d * 100, 2) if limit_1d > 0 else None,
            "usage_7d":      round(usage_7d, 4),
            "limit_7d":      limit_7d,
            "pct_7d":        round(usage_7d / limit_7d * 100, 2) if limit_7d > 0 else None,
        })

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "date": date.today().isoformat(),
        "summary": {
            "total_today_tokens":  total_today_tokens,
            "total_today_input":   total_today_input,
            "total_today_output":  total_today_output,
            "total_today_cache":   total_today_cache,
            "total_today_cost":    round(total_today_cost, 4),
            "total_all_cost":      round(total_all_cost, 4),
            "key_count":           len(key_data),
        },
        "keys": key_data,
    }


def load_snapshot() -> "dict | None":
    if SNAPSHOT_PATH.exists():
        with open(SNAPSHOT_PATH) as f:
            return json.load(f)
    return None


def save_snapshot(data: dict):
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_delta(current: dict, previous: dict) -> "dict | None":
    """计算两次快照之间的 token 和费用变化，用于周期报告。

    当快照跨日时，today_* 字段已重置，差值无意义，返回 None。
    """
    cur_date  = current.get("date")
    prev_date = previous.get("date")

    # 跨日：today 计数器已重置，delta 无法计算
    if cur_date != prev_date:
        return None

    prev_keys = {k["id"]: k for k in previous.get("keys", [])}
    deltas = []
    for k in current["keys"]:
        p = prev_keys.get(k["id"])
        if p is None:
            continue
        dt = round(k["today_tokens"] - p["today_tokens"], 0)
        dc = round(k["today_cost"]   - p["today_cost"],   6)
        deltas.append({
            "id":            k["id"],
            "name":          k["name"],
            "delta_tokens":  int(dt),
            "delta_cost":    dc,
            "pct_change_tokens": round(dt / p["today_tokens"] * 100, 1) if p["today_tokens"] > 0 else None,
        })

    # 按 delta_tokens 降序排列（用得最多的排前面）
    deltas.sort(key=lambda x: x["delta_tokens"], reverse=True)

    prev_summary = previous.get("summary", {})
    cur_summary  = current["summary"]
    return {
        "period_from":    previous.get("generated_at"),
        "period_to":      current["generated_at"],
        "delta_tokens":   cur_summary["total_today_tokens"] - prev_summary.get("total_today_tokens", 0),
        "delta_cost":     round(cur_summary["total_today_cost"] - prev_summary.get("total_today_cost", 0), 4),
        "key_deltas":     deltas,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="与上次快照对比")
    parser.add_argument("--save",   action="store_true", help="保存当前快照")
    args = parser.parse_args()

    with httpx.Client(timeout=30) as client:
        current = fetch_all(client)

    result = dict(current)

    if args.report:
        previous = load_snapshot()
        if previous:
            delta = compute_delta(current, previous)
            if delta is not None:
                result["delta"] = delta
            else:
                result["delta"] = None
                result["delta_note"] = (
                    f"快照跨日（上次 {previous.get('date')}，本次 {current['date']}），"
                    "today 计数器已重置，delta 无法计算，请以今日累计数据为准"
                )
        else:
            result["delta"] = None
            result["delta_note"] = "无历史快照，本次为首次记录"

    if args.save or args.report:
        save_snapshot(current)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
