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
from amazon.db import get_conn, DB_MODE

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

            for listed_db in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):  

                conn = get_conn(listed_db)

                if DB_MODE == "sqlite": 
                    conn.execute("PRAGMA journal_mode=WAL") 
                    conn.row_factory = sqlite3.Row 

                try:
                    cur = conn.cursor()

                    if DB_MODE == "sqlite": 
                        cur.execute("""
                            SELECT name
                            FROM sqlite_master
                            WHERE type='table' AND name='listed_items'
                        """)

                    elif DB_MODE == "postgres": 
                        cur.execute("""
                            SELECT table_name
                            FROM information_schema.tables
                            WHERE table_name = 'listed_items'
                        """)

                    if not cur.fetchone(): continue

                    cur.execute("""
                        SELECT user_id, asin, home_marketplace_id, region_marketplace_id
                        FROM listed_items
                        WHERE first_try_count > 0
                        AND ttl_stop_status IS NULL
                        GROUP BY user_id, asin, home_marketplace_id, region_marketplace_id, created_at
                        ORDER BY created_at ASC
                        LIMIT %s
                    """, (MAX_FIRST_PER_CYCLE,))
                    rows = cur.fetchall()

                    columns = [desc[0] for desc in cur.description]

                    for r in rows:
                        row_dict = r

                        targets.append({
                            "db": listed_db,
                            "user_id": row_dict["user_id"],
                            "asin": row_dict["asin"],
                            "home_marketplace_id": row_dict["home_marketplace_id"],
                            "region_marketplace_id": row_dict["region_marketplace_id"],                          
                        })
                finally:
                    conn.close()

            if not targets:
                time.sleep(FIRST_LOOP_SLEEP_SEC)
                continue

            # 更新カウント集計用　Print消す場合はセットで削除 ▼▼▼ ----
            for idx, t in enumerate(targets, start=1): 
                print(f"[FIRST PROGRESS] {idx}/{len(targets)} ASIN:{t['asin']}")  # // チェック完了後削除
            # --- ▲▲▲ ここまでセット削除 ▲▲▲ ---   

            # 上記集計カウントのため↑↑↑ Print消すときは for t in targets: ↓にもどす
            # for t in targets: 

                try:
                    conn_mkt = get_conn("a_marketplaces.db") 
                    cur_mkt = conn_mkt.cursor() 

                    cur_mkt.execute("""
                        SELECT country_code
                        FROM marketplaces
                        WHERE marketplace_id = %s
                        LIMIT 1
                    """, (t["home_marketplace_id"],)) 

                    row_home = cur_mkt.fetchone() 

                    cur_mkt.execute("""
                        SELECT country_code
                        FROM marketplaces
                        WHERE marketplace_id = %s
                        LIMIT 1
                    """, (t["region_marketplace_id"],)) 

                    row_region = cur_mkt.fetchone() 

                    conn_mkt.close() 

                    cc_home = row_home["country_code"] if row_home else None 
                    cc_region = row_region["country_code"] if row_region else None                    

                    # --- ▼ SECTION  firstで取得・updateする項目 ▼ ---
                    t0 = time.time()  # // チェック完了後削除

                    update_home_catalog(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)

                    print(f"[FIRST TIME][CATALOG] {t['asin']} {time.time()-t0:.3f}s")  # // チェック完了後削除

                    t1 = time.time()  # // チェック完了後削除

                    update_home_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)

                    print(f"[FIRST TIME][HOME_PRICING] {t['asin']} {time.time()-t1:.3f}s")  # // チェック完了後削除

                    t2 = time.time()  # // チェック完了後削除

                    # 解除中# === ▼ firstでregion_pricingを１回は取得するためのコード ▼ ===
                    # update_region_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_region)  

                    # 未使用 update_listing_price(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)

                    update_listing_price(user_id=t["user_id"], asin=t["asin"], country_code=cc_region) 
                    api_request_sleep()         
                    # --- ▲ SECTION  firstで取得・updateする項目 ▲ ---

                    # --- ★ SUCCESS判定：pricing_cacheにrawが入っていれば即0 ---
                    conn_success = get_conn(cache_db)
                    try:
                        cur_success = conn_success.cursor()
                        cur_success.execute("""
                            SELECT home_offers_json
                            FROM pricing_cache
                            WHERE asin = %s 
                        """, (t["asin"],))
                        row_success = cur_success.fetchone()

                        if row_success and row_success["home_offers_json"] is not None:
                            conn_listed = get_conn(t["db"]) 
                            try:
                                cur_listed = conn_listed.cursor()
                                cur_listed.execute("""
                                    UPDATE listed_items
                                    SET first_try_count = 0
                                    WHERE user_id = %s AND asin = %s
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

                conn3 = get_conn(t["db"])  
                try:
                    cur3 = conn3.cursor()
                    cur3.execute("""
                        UPDATE listed_items
                        SET first_try_count =
                            CASE
                                WHEN first_try_count > 0 THEN first_try_count - 1
                                ELSE 0
                            END
                        WHERE user_id = %s AND asin = %s
                    """, (t["user_id"], t["asin"]))
                    conn3.commit()
                finally:
                    conn3.close()

            time.sleep(FIRST_LOOP_SLEEP_SEC)



