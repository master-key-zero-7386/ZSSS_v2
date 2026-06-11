# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/background/ttl/ttl_loop.py
# 目的: TTL専用loop API起点
# ==========================================================

import os
import time
import sqlite3
import datetime
from datetime import timezone, timedelta

from amazon.background.common.background_common import list_listed_dbs
from amazon.background.ttl.ttl_days import get_account_ttl_days
from amazon.routes.routes_catalog_v2 import (update_home_catalog, update_region_catalog,)
from amazon.routes.routes_pricing_v2 import (update_home_pricing, update_region_pricing,)
from amazon.background.common.background_common import api_request_sleep 
from amazon.routes.routes_pricing_v2 import update_listing_price
from amazon.db import get_conn
from amazon.guard.guard_429 import is_blocked
from amazon.db import get_conn, DB_MODE



# ★ 追加オプション：DBの最短TTLだけを見る
USE_DB_MIN_TTL = True

# --- ▼ SECTION 01:  ▼ ---
def get_api_conf(user_id, country_code, db_dir):
    db_name = "a_marketplaces.db"
    conn = get_conn(db_name)
    if DB_MODE == "sqlite":
        conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM marketplaces
            WHERE user_id = %s
            AND country_code = %s
            LIMIT 1
        """, (
            user_id,
            country_code
        ))

        row = cur.fetchone()

        if not row:
            return {}

        return dict(row)

    finally:
        conn.close()

# --- ▼ SECTION 02: TTL loop 基本設定（FIRST写経） ▼
def run_ttl_loop(app, db_dir):
    with app.app_context():
        JST = timezone(timedelta(hours=9))
        loop_count = 0 # LOOPカウント処理

        # === ▼ 以下は TTL 動作制御設定値（FIRSTと同系）将来UI操作に変更する ▼ ===
        TTL_LOOP_SLEEP_SEC = 3     # cycle間のsleep
        # === ▲ ここまで ▲ ===

        while True:
            # === ★loop動作確認用（API関係なし） ===============================================
            loop_count += 1 # LOOPカウント処理
            print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [TTL][CYCLE_START] cycle={loop_count}")
            print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [TTL][LOOP][ALIVE]")
            # =================================================================================

            try:
                load_catalog_ttl_targets(db_dir)   
                load_pricing_ttl_targets(db_dir)   

            except Exception as e:
                import traceback
                print("### TTL LOOP ERROR ###")
                print(e)
                traceback.print_exc()

            # --- ▼ TTL進行更新（last_id）▼ ---
            try:
                conn = get_conn("a_pricing_settings.db")
                cur = conn.cursor()

                cur.execute("""
                    UPDATE ttl_state
                    SET last_id = COALESCE(last_id, 0) + 200
                    WHERE user_id = %s
                """, (1,))

                conn.commit()
                conn.close()
            except Exception:
                pass

            time.sleep(TTL_LOOP_SLEEP_SEC)

# --- ▼ SECTION 03: TTL対象取得（Cacheベース / catalog） ▼ ---
def load_catalog_ttl_targets(db_dir: str):
    cache_db = os.path.join(db_dir, "a_catalog_cache.db")
    conn = get_conn(cache_db)

    if DB_MODE == "sqlite":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()

        # --- Catalog HOME ---
        tmp = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path)

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL")
                conn_li.row_factory = sqlite3.Row

            try:
                cur_li = conn_li.cursor()

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.home_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_home_catalog = 1
                    AND (
                        li.h_catalog_ttl_at IS NULL
                        OR CAST(li.h_catalog_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.h_catalog_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.h_catalog_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.h_catalog_ttl_at
                    LIMIT 5
                """)

                listed_rows = cur_li.fetchall()
                print("[HOME_CAT_SQL_ROWS]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "home_marketplace_id": lr["home_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        home_rows = tmp

        # --- Catalog REGION ---
        tmp = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path)

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL")
                conn_li.row_factory = sqlite3.Row

            try:
                cur_li = conn_li.cursor()

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.region_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_region_catalog = 1
                    AND (
                        li.r_catalog_ttl_at IS NULL
                        OR CAST(li.r_catalog_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.r_catalog_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.r_catalog_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.r_catalog_ttl_at
                    LIMIT 5
                """)

                listed_rows = cur_li.fetchall()
                print("[REGION_CAT_SQL_ROWS]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "region_marketplace_id": lr["region_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        region_rows = tmp


        # Catalog HOME ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in home_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  

            executed_count += 1 

            dispatch_ttl_execution(
                [("home", "catalog")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": record.get("home_marketplace_id"),
                    "region_marketplace_id": None,
                },
                country_code
            )

        # Catalog REGION ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in region_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  

            executed_count += 1 

            dispatch_ttl_execution(
                [("region", "catalog")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": None,
                    "region_marketplace_id": record.get("region_marketplace_id"),
                },
                country_code
            )

    finally:
        conn.close()

# --- ▼ SECTION 04: TTL対象取得（Cacheベース / pricing） ▼ ---
def load_pricing_ttl_targets(db_dir: str):
    conn = get_conn(os.path.join(db_dir, "a_pricing_cache.db"))

    if DB_MODE == "sqlite":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row 

    try:
        cur = conn.cursor()

        # --- Pricing HOME ---
        tmp = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path)

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL")
                conn_li.row_factory = sqlite3.Row

            try:
                cur_li = conn_li.cursor()

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.home_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_home_pricing = 1
                    AND (
                        li.h_pricing_ttl_at IS NULL
                        OR CAST(li.h_pricing_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.h_pricing_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.h_pricing_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.h_pricing_ttl_at
                    LIMIT 5
                """)

                listed_rows = cur_li.fetchall()
                print("[HOME_SQL_ROWS]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "home_marketplace_id": lr["home_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        home_rows = tmp

        # --- Pricing REGION ---
        tmp = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path)

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL")
                conn_li.row_factory = sqlite3.Row

            try:
                cur_li = conn_li.cursor()

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.region_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_region_pricing = 1
                    AND (
                        li.r_pricing_ttl_at IS NULL
                        OR CAST(li.r_pricing_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.r_pricing_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.r_pricing_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.r_pricing_ttl_at
                    LIMIT 5
                """)

                listed_rows = cur_li.fetchall()
                print("[REGION_SQL_ROWS]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "region_marketplace_id": lr["region_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        region_rows = tmp


        # Pricing HOME ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in home_rows:
            record = dict(r)

            checked_count += 1   

            user_id = record.get("user_id")  
            country_code = record.get("country_code") 

            executed_count += 1  

            dispatch_ttl_execution(
                [("home", "pricing")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": record.get("home_marketplace_id"),
                    "region_marketplace_id": None,
                },
                country_code
            )  

        # Pricing REGION ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in region_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  
        
            executed_count += 1          

            dispatch_ttl_execution(
                [("region", "pricing")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": None,
                    "region_marketplace_id": record.get("region_marketplace_id"),
                },
                country_code
            )              

    finally:
        conn.close()
            
# --- ▼ SECTION 05: TTL実行受け口 ▼ ---
def dispatch_ttl_execution(targets, record, country_code):
    for scope, ttl_type in targets:
        # ----API を叩いたのはなにか確認するためのPrint
        print("[[ALL:", scope, ttl_type)  # 削除不可 コメントアウトのみ
        # --------------------------------------------
        
        # --- HOME / CATALOG ---
        if scope == "home" and ttl_type == "catalog":
            update_home_catalog(
                user_id=record["user_id"],
                asin=record["asin"],
                country_code=country_code,
            )

        # --- HOME / PRICING ---
        elif scope == "home" and ttl_type == "pricing":
            
            if not record.get("home_marketplace_id"):
                continue  

            update_home_pricing(
                user_id=record["user_id"],
                asin=record["asin"],
                country_code=country_code,
            )

        # --- REGION / CATALOG ---
        elif scope == "region" and ttl_type == "catalog":
            update_region_catalog(
                user_id=record["user_id"],
                asin=record["asin"],
                country_code=country_code,
            )        

        # --- REGION / PRICING ---
        elif scope == "region" and ttl_type == "pricing":
            update_region_pricing(
                user_id=record["user_id"],
                asin=record["asin"],
                country_code=country_code,
            )

    api_request_sleep()
         
