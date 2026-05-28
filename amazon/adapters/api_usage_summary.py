# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/adapters/api_usage_summary.py
# 目的： API使用量チェック（表示用・読み取り専用）
# ==========================================================

from amazon.db import get_conn
from datetime import datetime, timedelta

# --- ▼ SECTION 01: API使用量サマリー取得 ▼ --
# --- ▼ API使用量サマリー取得（完成形・デバッグ入り） ▼ ---
def get_api_usage_summary(user_id: int):

    """
    a_marketplaces.db を起点に、
    a_api_usage.db の使用ログを JOIN 集計して返す
    ※ 読み取り専用（SELECTのみ）
    """

    # -------------------------------
    # 1) 契約マーケットプレイス取得
    # -------------------------------
    conn_m = get_conn("a_marketplaces.db")
    cur_m = conn_m.cursor()
    cur_m.execute(
        """
        SELECT
            marketplace_id,
            display_name,
            home_flag
        FROM marketplaces
        WHERE user_id = %s
        """,
        (user_id,)
    )
    mkt_rows = cur_m.fetchall()
    conn_m.close()

    mkt_map = {}

    for row in mkt_rows:

        marketplace_id = row["marketplace_id"]
        display_name = row["display_name"]
        home_flag = row["home_flag"]

        mkt_map[marketplace_id] = {
            "label": display_name,
            "home_flag": int(home_flag),
            "catalog": 0,
            "pricing": 0,
            "day": 0,
            "month": 0,            
            "total": 0
        }

    if not mkt_map:

        return {
            "home": {"label": "", "catalog": 0, "pricing": 0, "total": 0},
            "regions": [],
            "grand_total": 0,
            "credit_limit": 50000
        }

    # -----------------------------------
    # 2) API使用ログ取得
    # -----------------------------------
    conn_u = get_conn("a_api_usage.db")
    cur_u = conn_u.cursor()
    cur_u.execute(
        """
        SELECT
            marketplace_id,
            endpoint,
            created_at
        FROM api_usage_logs
        WHERE user_id = %s
        """,
        (user_id,)
    )
    usage_rows = cur_u.fetchall()
    conn_u.close()

    # -----------------------------------
    # 3) endpoint 判定でカウント
    # -----------------------------------
    now = datetime.utcnow()
    day_limit = now - timedelta(days=1)
    month_limit = now - timedelta(days=30)

    for marketplace_id, endpoint, created_at in usage_rows:  


        if marketplace_id not in mkt_map:
            continue

        if "/catalog/" in endpoint:
            mkt_map[marketplace_id]["catalog"] += 1
        elif "/products/pricing/" in endpoint or "/pricing/" in endpoint:
            mkt_map[marketplace_id]["pricing"] += 1

        # --- 日/月カウント ---
        try:
            ts = datetime.fromisoformat(created_at.replace("Z",""))
        except:
            ts = None

        if ts:
            if ts >= day_limit:
                mkt_map[marketplace_id]["day"] += 1
            if ts >= month_limit:
                mkt_map[marketplace_id]["month"] += 1

    # -----------------------------------
    # 4) 表示用に整形
    # -----------------------------------
    result = {
        "home": {"label": "", "catalog": 0, "pricing": 0, "day":0, "month":0, "total": 0},
        "regions": [],
        "grand_total": 0,
        "credit_limit": 50000
    }

    for marketplace_id, data in mkt_map.items():
        data["total"] = data["catalog"] + data["pricing"]
        result["grand_total"] += data["total"]

        if data["home_flag"] == 1:
            result["home"] = {
                "label": data["label"],
                "catalog": data["catalog"],
                "pricing": data["pricing"],
                "day": data["day"],
                "month": data["month"],                
                "total": data["total"]
            }
        else:
            result["regions"].append({
                "label": data["label"],
                "catalog": data["catalog"],
                "pricing": data["pricing"],
                "day": data["day"],
                "month": data["month"],                
                "total": data["total"]
            })

    return result

