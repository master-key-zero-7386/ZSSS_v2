# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/services/blacklist_service.py
# 目的: ブラックリスト判定
# ==========================================================

import os
from amazon.db import get_conn


# --- ▼ SECTION 01: ブラックリスト判定（From：CSV / TTL 共通） ▼ ---
def is_blacklisted(asin, user_id, country_code, marketplace_id, db_dir):
    blacklist_dir = os.path.join(db_dir, "blacklist")  
    all_db = os.path.join(blacklist_dir, "a_all_blacklist_asin.db")  

    # --- allチェック ---
    if os.path.exists(all_db):  
        conn = get_conn("a_all_blacklist_asin.db")
        cur = conn.cursor()  
        cur.execute(
            "SELECT 1 FROM blacklist_asin WHERE asin = %s AND user_id = %s AND region_marketplace_id = %s",
            (asin, user_id, marketplace_id)
        )
        hit = cur.fetchone()  
        conn.close()  

        if hit:  
            return True  

    # --- countryチェック ---  # ←ここを修正（外に出す）
    country_db = os.path.join(
        blacklist_dir,
        f"a_{country_code.lower()}_blacklist_asin.db"
    )  

    if os.path.exists(country_db):  
        conn = get_conn(f"a_{country_code.lower()}_blacklist_asin.db")
        cur = conn.cursor()  
        cur.execute(
            "SELECT 1 FROM blacklist_asin WHERE asin = %s AND user_id = %s AND region_marketplace_id = %s",
            (asin, user_id, marketplace_id) 
        )
        hit = cur.fetchone()  
        conn.close()  

        if hit:  
            return True  

    return False

# --- ▼ SECTION 02: ブラックリスト理由取得（From：CSV / check） ▼ ---
def get_blacklist_reason(asin, user_id, country_code, marketplace_id, db_dir):

    blacklist_dir = os.path.join(db_dir, "blacklist")

    reasons = []

    # # --- allチェック 未搭載のためコメントアウト ---
    # all_db = os.path.join(blacklist_dir, "a_all_blacklist_asin.db")
    # if os.path.exists(all_db):
    #     conn = get_conn("a_all_blacklist_asin.db")
    #     cur = conn.cursor()
    #     cur.execute(
    #         """
    #         SELECT 1
    #         FROM blacklist_asin
    #         WHERE asin = %s
    #         AND user_id = %s
    #         AND region_marketplace_id = %s
    #         """,
    #         (asin, user_id, marketplace_id)
    #     )   
    #     if cur.fetchone():
    #         reasons.append("All Blacklist")
    #     conn.close()

    # --- countryチェック ---
    country_db = os.path.join(
        blacklist_dir,
        f"a_{country_code.lower()}_blacklist_asin.db"
    )
    if os.path.exists(country_db):
        conn = get_conn(f"a_{country_code.lower()}_blacklist_asin.db")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1
            FROM blacklist_asin
            WHERE asin = %s
            AND user_id = %s
            AND region_marketplace_id = %s
            """,
            (asin, user_id, marketplace_id)
        )     
        if cur.fetchone():
            reasons.append(f"{country_code.upper()} Blacklist")
        conn.close()

    if reasons:
        return " / ".join(reasons)

    return None

# --- ▼ SECTION 03: ブラックリスト判定（Brand）（From：CSV / TTL 共通） ▼ ---
def is_blacklisted_brand(brand, user_id, country_code, marketplace_id, db_dir):
    brand = (brand or "").strip()

    if not brand:
        return False

    blacklist_dir = os.path.join(db_dir, "blacklist")
    all_db = os.path.join(blacklist_dir, "a_all_blacklist_brand.db")

    # --- allチェック ---
    conn = get_conn("a_all_blacklist_brand.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM blacklist_brand WHERE LOWER(brand) = LOWER(%s) AND user_id = %s AND region_marketplace_id = %s", 
        (brand, user_id, marketplace_id)
    )
    hit = cur.fetchone()
    conn.close()

    if hit:
        return True

    # --- countryチェック ---
    country_db = os.path.join(
        blacklist_dir,
        f"a_{country_code.lower()}_blacklist_brand.db"
    )

    # if os.path.exists(country_db):
    conn = get_conn(f"a_{country_code.lower()}_blacklist_brand.db") 
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM blacklist_brand WHERE LOWER(brand) = LOWER(%s) AND user_id = %s AND region_marketplace_id = %s",
        (brand, user_id, marketplace_id)
    )
    hit = cur.fetchone()
    conn.close()

    if hit:
        return True

    return False