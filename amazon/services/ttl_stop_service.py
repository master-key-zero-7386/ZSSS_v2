# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/services/ttl_stop_service.py
# 目的: ttl_stopに関する管理とDB保存
# ==========================================================

from amazon.db import get_conn


# --- ▼ SECTION 01: BLACKLIST反映（停止処理） ▼ ---
def apply_blacklist(user_id, asin, marketplace_id, sku, reason, country_code):

    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")
    cur = conn.cursor()

    cur.execute("""
        UPDATE listed_items
        SET information_status = 'INACTIVE',
            inactive_reason = %s,
            ttl_stop_status = '1'
        WHERE user_id = %s
        AND asin = %s
        AND region_marketplace_id = %s
    """, (
        reason,
        user_id,
        asin,
        marketplace_id
    ))

    conn.commit()
    conn.close()


# --- ▼ SECTION 02: BLACK解除（復帰処理） ▼ ---
def clear_blacklist(user_id, asin, marketplace_id, country_code):

    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")
    cur = conn.cursor()

    # ★修正: 従来はブラック解除で無条件に information_status='ACTIVE' へ戻して
    #        いたため、「仕入価格(home_price)が無いのに ACTIVE」という矛盾行が
    #        発生していた（例: JP新品0件でINACTIVE化 → 後でブラック解除 → 価格が
    #        無いまま復活）。解除では ttl_stop を外すだけにして INACTIVE(理由=RECHECK)
    #        のまま据え置き、ACTIVE/INACTIVE の確定は次の Pricing/TTL 巡回
    #        （update_listing_price）に委ねる。
    cur.execute("""
        UPDATE listed_items
        SET information_status = 'INACTIVE',
            inactive_reason = 'RECHECK',
            ttl_stop_status = NULL
        WHERE user_id = %s
        AND asin = %s
        AND region_marketplace_id = %s
    """, (
        user_id,
        asin,
        marketplace_id
    ))

    conn.commit()
    conn.close()

# --- ▼ SECTION 03: DBに保存 ▼ ---
def apply_ttl_stop(user_id, asin, marketplace_id, reason, country_code, stop_flag=1):

    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")
    cur = conn.cursor()

    cur.execute("""
        UPDATE listed_items
        SET ttl_stop_status = %s,
            inactive_reason = %s
        WHERE user_id = %s
        AND asin = %s
        AND region_marketplace_id = %s
    """, (
        stop_flag,
        reason,
        user_id,
        asin,
        marketplace_id
    ))

    conn.commit()
    conn.close()



