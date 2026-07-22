# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/listed_items_update_adapter.py
# 目的: catalog / pricing / shipping で算定・正規化された結果を
#   　　listed_items テーブルへ反映する UPDATE 専用アダプタ
#   　（API取得・算定ロジックは一切持たない）
# ======================================================

from amazon.db import get_conn
import os
from datetime import datetime, timedelta


class ListedItemsUpdate:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir  # DB_DIR

    # --- ▼ SECTION 01: listed_items書き込み（catalog HOME）  ▼ ---
    # ★注記: HOME側（仕入元＝JP）のカタログ情報はASIN単位で全リージョン共通のため、
    #        意図的にregion_marketplace_idでは絞り込まず、同一user_id+asinの
    #        全リージョン行に同じHOMEデータを反映する（broadcast）。
    def update_home_from_catalog_normalized(self, listed_db: str, user_id: int, asin: str, marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db)

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
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

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = 'listed_items'
            """)

            if not cur.fetchone():
                return

            # --- UPDATE（REGION / catalog 情報のみ） ---
            # ★修正: region_marketplace_id条件が無く、同一ASINを複数国に出品している場合、
            #        他国の行まで巻き込んで上書きしてしまっていたため追加
            cur.execute("""
                UPDATE listed_items
                SET
                    region_title = COALESCE(%s, region_title),
                    region_brand = COALESCE(%s, region_brand),
                    region_manufacturer = COALESCE(%s, region_manufacturer),
                    updated_at = %s
                WHERE
                    user_id = %s
                    AND asin = %s
                    AND region_marketplace_id = %s
            """, (
                normalized.get("region_title"),
                normalized.get("region_brand"),
                normalized.get("region_manufacturer"),
                now_utc,
                user_id,
                asin,
                region_marketplace_id,
            ))

            conn.commit()

            return True
        finally:
            conn.close()

    # --- ▼ SECTION 03: listed_items書き込み（PRICING HOME） ▼ ---
    # ★注記: HOME側（仕入元＝JP）の仕入価格はASIN単位で全リージョン共通のため、
    #        意図的にregion_marketplace_idでは絞り込まず、同一user_id+asinの
    #        全リージョン行に同じHOMEデータを反映する（broadcast）。
    def update_home_from_pricing_normalized(self, listed_db: str, user_id: int, asin: str, marketplace_id: str, normalized: dict):
        conn = get_conn(listed_db)

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- listed_items テーブル存在チェック ---
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = 'listed_items'
            """)

            if not cur.fetchone():
                return

            # --- 旧価格取得 ---
            cur.execute("""
                SELECT id, home_price, information_status
                FROM listed_items
                WHERE user_id = %s
                AND asin = %s
                LIMIT 1
            """, (user_id, asin))
            row_old = cur.fetchone()
            old_id = row_old["id"] if row_old else None
            old_price = row_old["home_price"] if row_old else None
            old_status = row_old["information_status"] if row_old else None

            # --- 新価格 ---
            new_price = normalized.get("home_price")

            # --- UPDATE ---
            cur.execute("""
                UPDATE listed_items
                SET
                    home_price = %s,
                    updated_at = %s
                WHERE
                    user_id = %s
                    AND asin = %s
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

        try:
            cur = conn.cursor()
            now_utc = datetime.utcnow().isoformat()

            # --- UPDATE（REGION / PRICING price のみ） ---
            # ★修正: region_marketplace_id条件が無く、同一ASINを複数国に出品している場合、
            #        他国の行まで巻き込んで上書きしてしまっていたため追加
            cur.execute("""
                UPDATE listed_items
                SET
                    region_price = %s,
                    final_price = %s,
                    updated_at = %s
                WHERE
                    user_id = %s
                    AND asin = %s
                    AND region_marketplace_id = %s
            """, (
                normalized.get("region_price"),
                normalized.get("final_price"),
                now_utc,
                user_id,
                asin,
                region_marketplace_id,
            ))

            conn.commit()
            return True
        finally:
            conn.close()

