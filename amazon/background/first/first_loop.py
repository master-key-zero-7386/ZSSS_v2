## =====================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/background/first/first_loop.py
# 目的: first専用loop API起点
# =======================================================

import os
import time
import sqlite3
import datetime
from datetime import timezone, timedelta

from amazon.background.common.background_common import list_listed_dbs
from amazon.routes.routes_catalog_v2 import update_home_catalog
from amazon.routes.routes_pricing_v2 import (update_home_pricing, update_region_pricing)
from amazon.background.common.background_common import api_request_sleep 
from amazon.routes.routes_pricing_v2 import update_listing_price


# --- ▼ SECTION 01: first loop 基本設定 ▼
def run_first_loop(app, db_dir):
    with app.app_context(): 
        cache_db = os.path.join(db_dir, "a_pricing_cache.db")

        # === ▼ 以下はfirst動作制御設定値 将来UI操作に変更する  ▼ ===
        MAX_FIRST_PER_CYCLE = 20       # 件数制御
        FIRST_LOOP_SLEEP_SEC = 1.0     # cycle間のSleep時間（0.0でもOK）
        ASIN_SLEEP_SEC = 1.0           # ASIN間Sleep時間
        # === ▲ ここまで  ▲ ===

        while True:
            targets = []

            for listed_db in list_listed_dbs(db_dir):
                conn = sqlite3.connect(listed_db, timeout=30)
                conn.execute("PRAGMA journal_mode=WAL")  
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listed_items'")
                    if not cur.fetchone(): continue

                    cur.execute("""
                        SELECT user_id, asin, home_marketplace_id, region_marketplace_id
                        FROM listed_items
                        WHERE first_try_count > 0
                        AND ttl_stop_status IS NULL
                        GROUP BY user_id, asin
                        ORDER BY created_at ASC
                        LIMIT ?
                    """, (MAX_FIRST_PER_CYCLE,))
                    rows = cur.fetchall()

                    for r in rows:
                        targets.append({
                            "db": listed_db,
                            "user_id": r["user_id"],
                            "asin": r["asin"],
                            "home_marketplace_id": r["home_marketplace_id"],
                            "region_marketplace_id": r["region_marketplace_id"],                            
                        })
                finally:
                    conn.close()

            if not targets:
                time.sleep(FIRST_LOOP_SLEEP_SEC)
                continue

            for t in targets:
                try:
                    fname = os.path.basename(t["db"])
                    cc_home = fname.split("_")[1].upper()
                    cc_region = cc_home                

                    # --- ▼ SECTION  firstで取得・updateする項目 ▼ ---
                    update_home_catalog(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)

                    update_home_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)

                    # === ▼ firstでregion_pricingを１回は取得するためのコード ▼ ===
                    update_region_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_region)                  
                    # === ▲ ここまで ▼ === コメントアウト可

                    update_listing_price(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)
                    api_request_sleep()         
                    # --- ▲ SECTION  firstで取得・updateする項目 ▲ ---

                    # --- ★ SUCCESS判定：pricing_cacheにrawが入っていれば即0 ---
                    conn_success = sqlite3.connect(cache_db)
                    try:
                        cur_success = conn_success.cursor()
                        cur_success.execute("""
                            SELECT home_offers_json
                            FROM pricing_cache
                            WHERE asin = ? 
                        """, (t["asin"],))
                        row_success = cur_success.fetchone()

                        if row_success and row_success[0] is not None:
                            conn_listed = sqlite3.connect(t["db"])
                            try:
                                cur_listed = conn_listed.cursor()
                                cur_listed.execute("""
                                    UPDATE listed_items
                                    SET first_try_count = 0
                                    WHERE user_id = ? AND asin = ?
                                """, (t["user_id"], t["asin"]))
                                conn_listed.commit()
                            finally:
                                conn_listed.close()

                            time.sleep(ASIN_SLEEP_SEC)
                            continue
                    finally:
                        conn_success.close()

                    time.sleep(ASIN_SLEEP_SEC)

                # except Exception:
                except Exception as e:
                    import traceback
                    print("### FIRST ERROR ###")
                    print(e)
                    traceback.print_exc()
                #--------------------------

                conn3 = sqlite3.connect(t["db"])
                try:
                    cur3 = conn3.cursor()
                    cur3.execute("""
                        UPDATE listed_items
                        SET first_try_count =
                            CASE
                                WHEN first_try_count > 0 THEN first_try_count - 1
                                ELSE 0
                            END
                        WHERE user_id = ? AND asin = ?
                    """, (t["user_id"], t["asin"]))
                    conn3.commit()
                finally:
                    conn3.close()

            time.sleep(FIRST_LOOP_SLEEP_SEC)



