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

            print("[TTL_STEP_00]", flush=True)  # チェック完了後削除

            try:
                print("[TTL_STEP_01_BEFORE_CATALOG]", flush=True)  # チェック完了後削除
                load_catalog_ttl_targets(db_dir)   

                print("[TTL_STEP_02_AFTER_CATALOG]", flush=True)  # チェック完了後削除
                load_pricing_ttl_targets(db_dir)   
                print("[TTL_STEP_03_AFTER_PRICING]", flush=True)  # チェック完了後削除


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

        now_utc = datetime.datetime.utcnow()
        now_utc_str = now_utc.isoformat()

        # --- Catalog HOME ---
        rows = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path) 

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL") 
                conn_li.row_factory = sqlite3.Row

            try:
                cur_li = conn_li.cursor()
                cur_li.execute("""
                    SELECT
                        asin,
                        home_marketplace_id
                    FROM listed_items
                """)

                listed_rows = cur_li.fetchall()

                print(f"[CAT_LISTED_ROWS] {len(listed_rows)}", flush=True)  # チェック完了後削除

                columns_li = [desc[0] for desc in cur_li.description] 

                for lr in listed_rows:
                    rows.append({
                        "asin": lr["asin"],
                        "home_marketplace_id": lr["home_marketplace_id"]
                    })

            finally:
                conn_li.close()

        # --- ▼ CATALOG CACHE 一括取得 ▼ ---
        cur.execute("""
            SELECT
                asin,
                home_marketplace_id,
                h_catalog_ttl_at
            FROM catalog_cache
        """)

        print("[CAT_CACHE_SELECT_OK]", flush=True)  # チェック完了後削除

        rows_cache = cur.fetchall()

        print(f"[CAT_CACHE_ROWS] {len(rows_cache)}", flush=True)  # チェック完了後削除

        columns_cache = [desc[0] for desc in cur.description]

        cache_map = {}
        for rc in rows_cache:
            rc = dict(zip(columns_cache, rc))

            key = (rc["asin"], rc["home_marketplace_id"])
            cache_map[key] = rc["h_catalog_ttl_at"]

        # --- ▼ TTLで並び替え（HOME catalog）▼ ---
        tmp = []

        print(f"[CAT_ROWS] {len(rows)}", flush=True)  # チェック完了後削除

        for r in rows:
            asin = r["asin"]
            mp = r["home_marketplace_id"]

            user_id = None  
            country_code = None  

            # --- ▼ listed_items から user_id / country_code 取得 ▼ ---
            for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)): 
                conn_li = get_conn(db_path)
                if DB_MODE == "sqlite":
                    conn_li.execute("PRAGMA journal_mode=WAL")
                    conn_li.row_factory = sqlite3.Row       

                try:
                    cur_li = conn_li.cursor()  
                    cur_li.execute("""
                        SELECT 
                            user_id,
                            region_marketplace_id
                        FROM listed_items
                        WHERE asin = %s
                        AND home_marketplace_id = %s
                        LIMIT 1
                    """, (
                        asin,
                        mp
                    ))

                    row_li = cur_li.fetchone()

                    if row_li:
                        user_id = row_li["user_id"]

                        conn_mkt = get_conn("a_marketplaces.db")
                        try:
                            cur_mkt = conn_mkt.cursor()

                            cur_mkt.execute("""
                                SELECT country_code
                                FROM marketplaces
                                WHERE marketplace_id = %s
                                LIMIT 1
                            """, (row_li["region_marketplace_id"],))

                            row_mkt = cur_mkt.fetchone()

                        finally:
                            conn_mkt.close()

                        country_code = row_mkt["country_code"]
                        break

                finally:
                    conn_li.close()

            if not user_id or not country_code:
                continue  

            api_conf = get_api_conf(user_id, country_code, db_dir)  

            if not api_conf.get("enable_home_catalog"):
                continue  

            ttl = cache_map.get((asin, mp))

            ttl_days = api_conf.get("h_catalog_ttl_days")  

            # --- ▼ TTLフィルタ（期限切れのみtmp投入）▼ ---
            if ttl is not None:
                try:
                    ttl_dt = datetime.datetime.fromisoformat(ttl)

                    if ttl_dt + datetime.timedelta(days=float(ttl_days)) >= now_utc:
                        continue  

                except:
                    pass  # フォーマット不正は通す  

            tmp.append({
                "asin": asin,
                "home_marketplace_id": mp,
                "ttl": ttl,
                "user_id": user_id,  
                "country_code": country_code  
            })  

        # 並び替え（古い順）
        tmp.sort(key=lambda x: (
            x["ttl"] is not None,
            x["ttl"] or ""
        ))

        # 上位だけ使う
        home_rows = tmp[:5]  # TTL対象ASIN数の制御

        # --- Catalog REGION ---
        rows = []

        for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
            conn_li = get_conn(db_path) 

            if DB_MODE == "sqlite":
                conn_li.execute("PRAGMA journal_mode=WAL")
                conn_li.row_factory = sqlite3.Row 

            try:
                cur_li = conn_li.cursor()
                cur_li.execute("""
                    SELECT
                        asin,
                        region_marketplace_id
                    FROM listed_items
                """)

                listed_rows = cur_li.fetchall()

                columns_li = [desc[0] for desc in cur_li.description]

                for lr in listed_rows:
                    rows.append({
                        "asin": lr["asin"],
                        "region_marketplace_id": lr["region_marketplace_id"]
                    })

            finally:
                conn_li.close()

        # --- ▼ CATALOG CACHE 一括取得（REGION）▼ ---
        cur.execute("""
            SELECT
                asin,
                region_marketplace_id,
                r_catalog_ttl_at
            FROM catalog_cache
        """)

        rows_cache = cur.fetchall()

        cache_map = {}

        columns_cache = [desc[0] for desc in cur.description]

        for rc in rows_cache:
            rc = dict(zip(columns_cache, rc)) 

            key = (rc["asin"], rc["region_marketplace_id"])
            cache_map[key] = rc["r_catalog_ttl_at"]

        # --- ▼ TTLで並び替え（REGION catalog）▼ ---
        tmp = []

        for r in rows:
            asin = r["asin"]
            mp = r["region_marketplace_id"]

            user_id = None  
            country_code = None  

            # --- ▼ listed_items から user_id / country_code 取得 ▼ ---
            for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
                conn_li = get_conn(db_path) 
                if DB_MODE == "sqlite":
                    conn_li.execute("PRAGMA journal_mode=WAL")
                    conn_li.row_factory = sqlite3.Row

                try:
                    cur_li = conn_li.cursor()  
                    cur_li.execute("""
                        SELECT 
                            user_id,
                            region_marketplace_id
                        FROM listed_items
                        WHERE asin = %s
                        AND region_marketplace_id = %s
                        LIMIT 1
                    """, (
                        asin,
                        mp
                    ))

                    row_li = cur_li.fetchone()

                    if row_li:
                        user_id = row_li["user_id"]

                        conn_mkt = get_conn("a_marketplaces.db")
                        try:
                            cur_mkt = conn_mkt.cursor()

                            cur_mkt.execute("""
                                SELECT country_code
                                FROM marketplaces
                                WHERE marketplace_id = %s
                                LIMIT 1
                            """, (row_li["region_marketplace_id"],))

                            row_mkt = cur_mkt.fetchone()

                        finally:
                            conn_mkt.close()

                        country_code = row_mkt["country_code"]
                        break

                finally:
                    conn_li.close()

            if not user_id or not country_code:
                continue  

            api_conf = get_api_conf(user_id, country_code, db_dir)  

            if not api_conf.get("enable_region_catalog"):
                continue  

            ttl = cache_map.get((asin, mp))

            ttl_days = api_conf.get("r_catalog_ttl_days")  

            # --- ▼ TTLフィルタ（期限切れのみtmp投入）▼ ---
            if ttl is not None:
                try:
                    ttl_dt = datetime.datetime.fromisoformat(ttl)

                    if ttl_dt + datetime.timedelta(days=float(ttl_days)) >= now_utc:
                        continue  

                except:
                    pass  # フォーマット不正は通す  

            tmp.append({
                "asin": asin,
                "region_marketplace_id": mp,
                "ttl": ttl,
                "user_id": user_id,  
                "country_code": country_code  
            })  

        # 並び替え（古い順）
        tmp.sort(key=lambda x: (
            x["ttl"] is not None,
            x["ttl"] or ""
        ))

        # 上位だけ使う
        region_rows = tmp[:5]  # TTL対象ASIN数の制御


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
    print("[TTL_PRICING_START]", flush=True)  # チェック完了後削除

    conn = get_conn(os.path.join(db_dir, "a_pricing_cache.db"))

    if DB_MODE == "sqlite":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row 

    try:
        cur = conn.cursor()

        now_utc = datetime.datetime.utcnow()
        now_utc_str = now_utc.isoformat()

        # # --- Pricing HOME ---
        # --- ▼ PRICING CACHE 一括取得 ▼ ---
        cur.execute("""
            SELECT
                asin,
                home_marketplace_id,
                h_pricing_ttl_at
            FROM pricing_cache
            ORDER BY h_pricing_ttl_at ASC
        """)
        
        rows_cache = cur.fetchall()

        columns_cache = [desc[0] for desc in cur.description] 

        # --- ▼ TTLで並び替え（HOME PRICING）▼ ---
        tmp = []
        count = 0
       
        for rc in rows_cache:
            count += 1

            asin = rc["asin"]
            mp = rc["home_marketplace_id"]

            user_id = None  
            country_code = None  

            # --- ▼ listed_items から user_id / country_code 取得 ▼ ---
            for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
                conn_li = get_conn(db_path)
                if DB_MODE == "sqlite":
                    conn_li.execute("PRAGMA journal_mode=WAL")
                    conn_li.row_factory = sqlite3.Row

                try:
                    cur_li = conn_li.cursor()    

                    cur_li.execute("""  
                        SELECT
                            user_id,
                            region_marketplace_id
                        FROM listed_items
                        WHERE asin = %s
                        AND home_marketplace_id = %s
                        LIMIT 1
                    """, (
                        asin,
                        mp
                    ))  

                    row_li = cur_li.fetchone()

                    if row_li:
                        user_id = row_li["user_id"]

                        conn_mkt = get_conn("a_marketplaces.db")
                        try:
                            cur_mkt = conn_mkt.cursor()

                            cur_mkt.execute("""
                                SELECT country_code
                                FROM marketplaces
                                WHERE marketplace_id = %s
                                LIMIT 1
                            """, (row_li["region_marketplace_id"],))

                            row_mkt = cur_mkt.fetchone()

                        finally:
                            conn_mkt.close()

                        country_code = row_mkt["country_code"]  
                        break     
                        
                finally:
                    conn_li.close()

            if not user_id or not country_code:
                continue  

            api_conf = get_api_conf(user_id, country_code, db_dir)     

            if not api_conf.get("enable_home_pricing"):
                continue  

            ttl = rc["h_pricing_ttl_at"]

            ttl_days = api_conf.get("h_pricing_ttl_days")  

            # --- ▼ TTLフィルタ（期限切れのみtmp投入）▼ ---
            if ttl is not None: 
                try:
                    ttl_dt = datetime.datetime.fromisoformat(ttl)

                    if ttl_dt + datetime.timedelta(days=float(ttl_days)) >= now_utc:
                        continue  

                except:
                    pass  # フォーマット不正は通す  

            tmp.append({
                "asin": asin,
                "home_marketplace_id": mp,
                "ttl": ttl,
                "user_id": user_id,
                "country_code": country_code
            })  
            if len(tmp) >= 30:
                break            

        # 上位だけ使う
        home_rows = tmp[:30]  # TTL対象ASIN数の制御

        # --- Pricing REGION ---
        # --- ▼ PRICING CACHE 一括取得（REGION）▼ ---
        cur.execute("""
            SELECT
                asin,
                region_marketplace_id,
                r_pricing_ttl_at
            FROM pricing_cache
            ORDER BY r_pricing_ttl_at ASC
        """)

        rows_cache = cur.fetchall()

        columns_cache = [desc[0] for desc in cur.description] 

        tmp = []

        for rc in rows_cache:
            asin = rc["asin"]
            mp = rc["region_marketplace_id"]
            
            user_id = None  
            country_code = None  

            # --- ▼ listed_items から user_id / country_code 取得 ▼ ---
            for db_path in (["listed_items"] if DB_MODE == "postgres" else list_listed_dbs(db_dir)):
                conn_li = get_conn(db_path)
                
                if DB_MODE == "sqlite":
                    conn_li.execute("PRAGMA journal_mode=WAL")
                    conn_li.row_factory = sqlite3.Row 

                try:
                    cur_li = conn_li.cursor()  
                    cur_li.execute("""
                        SELECT 
                            user_id,
                            region_marketplace_id
                        FROM listed_items
                        WHERE asin = %s
                        AND region_marketplace_id = %s
                        LIMIT 1
                    """, (
                        asin,
                        mp
                    ))

                    row_li = cur_li.fetchone()

                    if row_li:
                        user_id = row_li["user_id"]  

                        conn_mkt = get_conn("a_marketplaces.db")
                        try:
                            cur_mkt = conn_mkt.cursor()

                            cur_mkt.execute("""
                                SELECT country_code
                                FROM marketplaces
                                WHERE marketplace_id = %s
                                LIMIT 1
                            """, (row_li["region_marketplace_id"],))

                            row_mkt = cur_mkt.fetchone()

                        finally:
                            conn_mkt.close()

                        country_code = row_mkt["country_code"]
                        break                        

                finally:
                    conn_li.close()

            if not user_id or not country_code:
                continue  

            api_conf = get_api_conf(user_id, country_code, db_dir)  

            if not api_conf.get("enable_region_pricing"):
                continue  

            ttl = rc["r_pricing_ttl_at"]

            ttl_days = api_conf.get("r_pricing_ttl_days")  

            # --- ▼ TTLフィルタ（期限切れのみtmp投入）▼ ---
            if ttl is not None:
                try:
                    ttl_dt = datetime.datetime.fromisoformat(ttl)

                    if ttl_dt + datetime.timedelta(days=float(ttl_days)) >= now_utc:
                        continue  

                except:
                    pass  # フォーマット不正は通す  

            tmp.append({
                "asin": asin,
                "region_marketplace_id": mp,
                "ttl": ttl,
                "user_id": user_id,  
                "country_code": country_code  
            })  

        # 上位だけ使う
        region_rows = tmp[:30]  # TTL対象ASIN数の制御

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
         
