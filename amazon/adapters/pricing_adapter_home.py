# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/pricing_adapter_home.py
# API　HOME（基準国 価格情報取得）
# ======================================================

from __future__ import annotations
import json
import sqlite3
import os
from datetime import datetime, timedelta
from amazon.db import get_conn  

# --- ▼ Amazon Retail Seller ID（DB取得） ▼ ---
def get_retail_seller_ids():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_file = os.path.join(base_dir, "db", "a_marketplaces_master.db")

    conn = get_conn("a_marketplaces_master.db")

    try:
        cur = conn.cursor()
        cur.execute("SELECT seller_id FROM amazon_retail_sellers")
        rows = cur.fetchall()
        return [r[0] for r in rows if r[0]]
    finally:
        conn.close()

class PricingAdapterHome:
    # --- ▼ SECTION 01: AmazonAdapterから認証関連情報の受け取り ▼ ---
    def __init__(self, parent_adapter): 

        # ------------------------------
        # ① 型チェック（AmazonAdapterであること）
        # ------------------------------
        from amazon.adapters.amazon_adapter import AmazonAdapter
        if not isinstance(parent_adapter, AmazonAdapter):
            raise TypeError("parent_adapter must be an instance of AmazonAdapter")

        # ------------------------------
        # ② 必須属性チェック（AmazonAdapter由来のみ）
        # ------------------------------
        required_attrs = [
            "user_id",
            "country_code",
            "marketplace_id",
            "credentials",
            "refresh_token",
            "host",
            "locale"
        ]

        for attr in required_attrs:
            if getattr(parent_adapter, attr, None) is None:
                raise ValueError(f"Missing required attribute in parent_adapter: {attr}")

        # ------------------------------
        # ③ 代入
        # ------------------------------
        self.parent = parent_adapter
        self.user_id = parent_adapter.user_id
        self.country_code = parent_adapter.country_code
        self.marketplace_id = parent_adapter.marketplace_id
        self.credentials = parent_adapter.credentials
        self.refresh_token = parent_adapter.refresh_token
        self.host = parent_adapter.host
        self.locale = parent_adapter.locale

    # --- ▼ SECTION 02: Pricing API 生取得（AmazonAdapter 経由） ▼ ---
    def _fetch_pricing_raw(self, asin: str) -> dict:
        if not asin or not isinstance(asin, str):
            raise ValueError("ASIN is required and must be a non-empty string")

        asin = asin.strip().upper()

        if not self.marketplace_id:
            raise ValueError("marketplace_id is missing")

        path = f"/products/pricing/v0/items/{asin}/offers"
        params = {
            "MarketplaceId": self.marketplace_id,
            "ItemCondition": "New",
        }

        raw = self.parent.real_signed_request(
            method="GET",
            endpoint=path,
            host=self.host,
            params=params,
        )

        if not isinstance(raw, dict):
            raise TypeError("Invalid response from Pricing API")

        return raw

    # --- ▼ SECTION 03: 外部公開メソッド（現行契約） ▼ ---
    def get_full_pricing_item(self, asin: str) -> dict:
        raw = self._fetch_pricing_raw(asin)

        # --- ▼ エラー時は保存しない ▼ ---
        if isinstance(raw, dict) and raw.get("errors"):
            return {
                "asin": asin,
                "raw": raw,
                "source": "api_error",
            }

        # === ▼ UI表示用 offersカウント（HOME） ▼ ===
        RETAIL_SELLER_IDS = get_retail_seller_ids()
        offers = raw.get("payload", {}).get("Offers", [])

        amazon_count = 0
        fba_count = 0
        fbm_count = 0

        for o in offers:
            seller_id = o.get("SellerId")
            is_fba = o.get("IsFulfilledByAmazon", False)

            # Amazon本体（RETAIL）
            if seller_id and seller_id in RETAIL_SELLER_IDS:
                amazon_count += 1

            # FBA
            elif is_fba:
                fba_count += 1

            # FBM
            else:
                fbm_count += 1   

        self._save_pricing_cache(
            asin=asin,
            home_offers_json=json.dumps(raw, ensure_ascii=False),
        )

        return {
            "asin": asin,
            "raw": raw,
            "source": "api",
        }

    # --- ▼ SECTION 04: pricing_cache 読み込み ▼ ---
    def _get_cached_pricing(self, asin: str,):

        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        db_file = os.path.join(base_dir, "db", "a_pricing_cache.db")

        conn = get_conn("a_pricing_cache.db")

        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    home_offers_json,
                    home_updated_at 
                FROM pricing_cache
                WHERE asin = %s
                    AND home_marketplace_id = %s
                LIMIT 1
            """, (asin, self.marketplace_id))

            row = cur.fetchone()

            if not row or not row[0]:
                return None

            if not row[1]:
                return None    

            updated_at = datetime.fromisoformat(row[1])        

            data = json.loads(row[0])

            RETAIL_SELLER_IDS = get_retail_seller_ids()
            offers = data.get("payload", {}).get("Offers", [])

            amazon_count = 0
            fba_count = 0
            fbm_count = 0

            for o in offers:
                seller_id = o.get("SellerId")
                is_fba = o.get("IsFulfilledByAmazon", False)

                if seller_id and seller_id in RETAIL_SELLER_IDS:
                    amazon_count += 1
                elif is_fba:
                    fba_count += 1
                else:
                    fbm_count += 1

            data["offer_counts"] = {
                "amazon": amazon_count,
                "fba": fba_count,
                "fbm": fbm_count
            }

            return data
            
        finally:
            conn.close()

    # --- ▼ SECTION 05: pricing_cache 初期書込み（既存レコードがあるためUPDATE仕様） ▼ ---
    def _save_pricing_cache(self, asin: str, home_offers_json: str):
        # print("[PRICING HOME]SAVE CACHE CALLED", asin)
        # --- ▼ errors 検知（DB操作より前）▼ ---
        try:
            payload = json.loads(home_offers_json)
        except Exception:
            payload = {}

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_file = os.path.join(base_dir, "db", "a_pricing_cache.db")

        conn = get_conn("a_pricing_cache.db")

        now_utc = datetime.utcnow().isoformat()

        try:
            cur = conn.cursor()

            # --- 既存データ取得 ---
            cur.execute("""
                SELECT home_offers_json
                FROM pricing_cache
                WHERE asin = %s
                AND home_marketplace_id = %s
            """, (asin, self.marketplace_id))

            row = cur.fetchone()

            # --- 変更がある場合のみUPDATE ---
            old = json.dumps(json.loads(row[0]), sort_keys=True, ensure_ascii=False) if (row and row[0]) else None
            new = json.dumps(json.loads(home_offers_json), sort_keys=True, ensure_ascii=False) if home_offers_json else None  

            # --- データ変更がある場合のみ更新 ---
            if row:
                if old != new:
                    cur.execute("""
                        UPDATE pricing_cache
                        SET
                            home_offers_json = %s,
                            home_updated_at  = %s,
                            updated_at       = %s,
                            h_pricing_ttl_at = %s
                        WHERE
                            asin = %s
                            AND home_marketplace_id = %s
                    """, (
                        home_offers_json, now_utc, now_utc, now_utc, asin, self.marketplace_id)) 
                else:
                    cur.execute("""
                        UPDATE pricing_cache
                        SET
                            h_pricing_ttl_at = %s
                        WHERE
                            asin = %s
                            AND home_marketplace_id = %s
                    """, (
                        now_utc, asin, self.marketplace_id)) 

                conn.commit()

        finally:
            conn.close()
