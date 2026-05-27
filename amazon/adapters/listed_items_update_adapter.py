# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/listed_items_update_adapter.py
# 目的: catalog / pricing / shipping で算定・正規化された結果を
#   　　listed_items テーブルへ反映する UPDATE 専用アダプタ
#   　（API取得・算定ロジックは一切持たない）
# ======================================================

import sqlite3
from amazon.db import get_conn 
import os
from datetime import datetime, timedelta


class ListedItemsUpdate:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir  # DB_DIR

    # --- ▼ SECTION 01: listed_items書き込み（catalog HOME）  ▼ ---
    def update_home_from_catalog_normalized(self, listed_db: str, user_id: int, asin: str, marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db) 
        if DB_MODE == "sqlite":
            conn.execute("PRAGMA journal_mode=WAL") # 一旦保留

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
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
            if not cur.fetchone():
                return

            # --- ▼ DEBUG: status確認（UPDATE前）▼ ---
            cur.execute("""
                SELECT information_status
                FROM listed_items
                WHERE user_id=%s AND asin=%s
            """, (user_id, asin))
            row_debug = cur.fetchone()

            # --- UPDATE（HOME + 寸法・重量） ---
            cur.execute("""
                UPDATE listed_items
                SET
                    home_title = %s,
                    home_brand = %s,
                    home_manufacturer = %s,
                    image_url = %s,
                    length_cm = %s,
                    width_cm = %s,
                    height_cm = %s,
                    actual_weight_kg = %s,
                    volumetric_weight_kg = %s,
                    billable_weight_kg = %s,
                    updated_at = %s
                WHERE
                    user_id = %s
                    AND asin = %s
            """, (
                normalized.get("home_title"),
                normalized.get("home_brand"),
                normalized.get("home_manufacturer"),
                normalized.get("image_url"), 
                normalized.get("length_cm"),
                normalized.get("width_cm"),
                normalized.get("height_cm"),
                normalized.get("actual_weight_kg"),
                normalized.get("volumetric_weight_kg"),
                normalized.get("billable_weight_kg"),
                now_utc,
                user_id,
                asin,
            ))
            conn.commit()

        finally:
            conn.close()

    # --- ▼ SECTION 02: listed_items書き込み（catalog REGION）  ▼ ---
    def update_region_from_catalog_normalized(self, listed_db: str, user_id: int, asin: str, region: str, region_marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db)
        conn.execute("PRAGMA journal_mode=WAL") # 一旦保留

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
            cur.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name='listed_items'
            """)
            if not cur.fetchone():
                return

            # --- UPDATE（REGION / catalog 情報のみ） ---
            cur.execute("""
                UPDATE listed_items
                SET
                    region_title = COALESCE(?, region_title),
                    region_brand = COALESCE(?, region_brand),
                    region_manufacturer = COALESCE(?, region_manufacturer),
                    updated_at = ?
                WHERE
                    user_id = ?
                    AND asin = ?
            """, (
                normalized.get("region_title"),
                normalized.get("region_brand"),
                normalized.get("region_manufacturer"),
                now_utc,
                user_id,
                asin,
            ))

            conn.commit()

            return True
        finally:
            conn.close()

    # --- ▼ SECTION 03: listed_items書き込み（PRICING HOME） ▼ ---
    def update_home_from_pricing_normalized(self, listed_db: str, user_id: int, asin: str, marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db)
        conn.execute("PRAGMA journal_mode=WAL") #一旦保留       

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
            cur.execute("""
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name='listed_items'
            """)
            if not cur.fetchone():
                return

            # --- 旧価格取得 ---
            cur.execute("""
                SELECT id, home_price, information_status
                FROM listed_items
                WHERE user_id = ?
                AND asin = ?
                LIMIT 1
            """, (user_id, asin))
            row_old = cur.fetchone()
            old_id = row_old[0] if row_old else None 
            old_price = row_old[1] if row_old else None
            old_status = row_old[2] if row_old else None

            # --- 新価格 ---
            new_price = normalized.get("home_price") 

            print(f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [[PRICE CHECK]] ID:{old_id} ASIN:{asin} old:{old_price} new:{new_price} status:{old_status}")  # // チェック完了後削除 可

            # # --- TTL更新判定 ---
            # ttl_value = now_utc if old_price != new_price else None 

            # --- UPDATE ---
            cur.execute("""
                UPDATE listed_items
                SET
                    home_price = ?,
                    updated_at = ?
                WHERE
                    user_id = ?
                    AND asin = ?
            """, (
                new_price,
                now_utc,
                user_id,
                asin,
            ))

            conn.commit()
        finally:
            conn.close()

    # --- ▼ SECTION 04: listed_items書き込み（PRICING REGION） ▼ ---  
    def update_region_from_pricing_normalized(self, listed_db: str, user_id: int, asin: str, region_marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db) 
        conn.execute("PRAGMA journal_mode=WAL") #一旦保留       

        try:
            cur = conn.cursor()  
            now_utc = datetime.utcnow().isoformat()

            # --- UPDATE（REGION / PRICING price のみ） ---  
            cur.execute("""  
                UPDATE listed_items
                SET
                    region_price = ?,  
                    final_price = ?, 
                    updated_at = ?
                WHERE
                    user_id = ?
                    AND asin = ?
            """, (
                normalized.get("region_price"),  
                normalized.get("final_price"), 
                now_utc,
                user_id,  
                asin,  
            ))    

            conn.commit()  
            return True  
        finally:
            conn.close()  

