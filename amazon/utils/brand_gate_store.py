# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/utils/brand_gate_store.py
# 目的： ゲート通過ブランド記録・保存
# ==========================================================


# --- ▼ SECTION 01: BrandGate保存（From：listing_submit_service） ▼ ---
# brandが実質空("-"/空欄/UNKNOWN)の商品は、ブランド単位でキャッシュすると
# 無関係な別商品同士でチェック結果を上書きし合ってしまうため、ASIN単位で保存する。
NO_BRAND_VALUES = ("", "-", "unknown")


def save_brand_gate_result(user_id, marketplace_id, brand, status, reason, asin=None):
    from datetime import datetime
    from amazon.db import get_conn

    conn = get_conn("a_brand_gate_result.db")
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    normalized_brand = (brand or "").strip()
    is_real_brand = normalized_brand.lower() not in NO_BRAND_VALUES

    if is_real_brand:
        cur.execute("""
            INSERT INTO brand_gate_result (user_id, region_marketplace_id, brand, status, reason, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id, region_marketplace_id, brand)
            DO UPDATE SET
                status=excluded.status,
                reason=excluded.reason,
                updated_at=excluded.updated_at
        """, (user_id, marketplace_id, normalized_brand, status, reason, now))

    elif asin:
        cur.execute("""
            INSERT INTO brand_gate_result (user_id, region_marketplace_id, brand, asin, status, reason, updated_at)
            VALUES (%s, %s, NULL, %s, %s, %s, %s)
            ON CONFLICT(user_id, region_marketplace_id, asin)
            DO UPDATE SET
                status=excluded.status,
                reason=excluded.reason,
                updated_at=excluded.updated_at
        """, (user_id, marketplace_id, asin, status, reason, now))

    conn.commit()
    conn.close()


        
          