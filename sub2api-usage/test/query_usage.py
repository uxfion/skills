# /// script
# dependencies = [
#   "httpx",
#   "python-dotenv",
# ]
# ///

import os
from dotenv import load_dotenv
import httpx

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

BASE_URL = os.environ["SUB2API_URL"].rstrip("/")
ADMIN_KEY = os.environ["SUB2API_ADMIN_KEY"]

HEADERS = {"x-api-key": ADMIN_KEY}
USER_ID = 1


def get_user_keys(client: httpx.Client) -> list[dict]:
    resp = client.get(f"{BASE_URL}/api/v1/admin/users/{USER_ID}/api-keys", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()["data"]["items"]


def get_keys_usage(client: httpx.Client, key_ids: list[int]) -> dict:
    resp = client.post(
        f"{BASE_URL}/api/v1/admin/dashboard/api-keys-usage",
        headers=HEADERS,
        json={"api_key_ids": key_ids},
    )
    resp.raise_for_status()
    # 返回格式: {"data": {"stats": {"<id>": {api_key_id, today_actual_cost, total_actual_cost}}}}
    return resp.json()["data"]["stats"]


def main():
    with httpx.Client(timeout=30) as client:
        print(f"查询用户 ID={USER_ID} 下的所有 API Key...\n")
        keys = get_user_keys(client)

        if not keys:
            print("该用户下没有 API Key。")
            return

        key_ids = [k["id"] for k in keys]
        id_to_key = {k["id"]: k for k in keys}

        print(f"共找到 {len(keys)} 个 Key，正在查询用量...\n")
        stats = get_keys_usage(client, key_ids)

        def fmt_usage(used, limit):
            if limit > 0:
                pct = used / limit * 100
                return f"{used:.2f}/{limit:.2f}({pct:.2f}%)"
            return f"{used:.2f}/无限制"

        col = "{:<6} {:<12} {:<28} {:<28}"
        header = col.format("ID", "名称", "日用量/日限(占比)", "周用量/周限(占比)")
        print(header)
        print("-" * len(header))

        total_today = 0.0
        total_all   = 0.0

        for kid in key_ids:
            k     = id_to_key[kid]
            name  = (k.get("name") or "(未命名)")[:12]
            s     = stats.get(str(kid), {})
            total_today += s.get("today_actual_cost", 0)
            total_all   += s.get("total_actual_cost",  0)

            print(col.format(
                kid, name,
                fmt_usage(k.get("usage_1d") or 0, k.get("rate_limit_1d") or 0),
                fmt_usage(k.get("usage_7d") or 0, k.get("rate_limit_7d") or 0),
            ))

        print("-" * len(header))
        print(f"\n今日总花费: ${total_today:.4f}  |  累计总花费: ${total_all:.4f}")


if __name__ == "__main__":
    main()
