# ==========================================
# ファイル名: amazon/background/ttl/ttl_days.py
# 目的: アカウント設定 TTLサイクル読み込み（統合版）
# ==========================================

import os
from amazon.db import get_conn


TTL_LOG_ENABLED = os.environ.get("TTL_LOG", "1") == "1"

# --- ▼ SECTION: TTL days 取得（DB基準） ▼ ---
def get_account_ttl_days(db_dir, user_id, marketplace_id, scope, ttl_type):
    if scope not in ("home", "region"):
        return None
    if ttl_type not in ("catalog", "pricing"):
        return None

    # --- 対象カラム決定 ---
    if scope == "home" and ttl_type == "catalog":
        enable_col = "enable_home_catalog"
        days_col   = "h_catalog_ttl_days"
    elif scope == "home" and ttl_type == "pricing":
        enable_col = "enable_home_pricing"
        days_col   = "h_pricing_ttl_days"
    elif scope == "region" and ttl_type == "catalog":
        enable_col = "enable_region_catalog"
        days_col   = "r_catalog_ttl_days"
    else:  # region + pricing
        enable_col = "enable_region_pricing"
        days_col   = "r_pricing_ttl_days"


    db_name = "a_marketplaces.db" 
    conn = get_conn(db_name) 
    if DB_MODE == "sqlite":
        conn.row_factory = sqlite3.Row # 一旦保留
    cur = conn.cursor()    

    cur.execute(f"""
        SELECT
            {enable_col} AS enabled,
            {days_col}   AS ttl_days
        FROM marketplaces
        WHERE user_id = %s
          AND marketplace_id = %s 
        LIMIT 1
    """, (user_id, marketplace_id))

    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None

    columns = [desc[0] for desc in cur.description] 
    row_dict = dict(zip(columns, row))

    return {
        "enabled": row_dict["enabled"],
        "ttl_days": row_dict["ttl_days"], 
    }

