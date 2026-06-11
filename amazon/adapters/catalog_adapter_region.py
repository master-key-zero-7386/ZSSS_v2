# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/catalog_adapter_region.py
# API　region（regionカタログ情報取得）
# ==========================================================

from __future__ import annotations
from typing import Dict, Any
from datetime import datetime
from amazon.db import get_conn
import json
import os
from amazon.spapi_client import real_signed_request 
import logging
import requests 

# logging.basicConfig(level=logging.DEBUG)

class CatalogAdapterRegion:
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

    # --- ▼ SECTION 02: フルカタログ取得（AmazonAdapter 経由） ▼ ---
    def fetch_catalog(self, asin: str) -> dict:

        # === ① ASINバリデーション（空・None禁止） ===
        if not asin or not isinstance(asin, str):  
            raise ValueError("ASIN is required and must be a non-empty string")  

        asin = asin.strip().upper()  

        # === ② marketplace_id の事前チェック（None禁止） ===
        if not self.marketplace_id:  
            raise ValueError("marketplace_id is missing — cannot call CatalogItems API")  

        # === API パス定義（既存コード） === 
        path = f"/catalog/2022-04-01/items/{asin}"

        # === API パラメータ（既存） === 
        params = {
            "marketplaceIds": [self.marketplace_id],
            "includedData": ",".join([
                "attributes",      # 商品属性
                "images",          # 画像一覧
                "summaries",       # 商品概要
                "salesRanks",      # ランキング
                "productTypes",    # 商品タイプ
            ])
        }

        # === ③ API 実行＋例外処理追加 ===
        try: 
            raw = self.parent.real_signed_request(  
                method="GET",
                endpoint=path,
                host=self.host,
                params=params
            )
                
        except Exception as e:  
            raise RuntimeError(f"CatalogItems API request failed: {e}")  

        # === ④ APIレスポンス型チェック === 
        if not isinstance(raw, dict):  
            raise TypeError("Invalid response type from Amazon API — expected dict")  

        # === （既存コード）raw をそのまま返す === 
        return raw 

    # --- ▼ SECTION 03: 外部公開メソッド（UI から使う） ▼ ---
    def get_full_catalog_item(self, asin: str,) -> dict:
        # === ① 生データ取得（API） ===
        raw = self.fetch_catalog(asin)

        # --- ▼ エラー時は保存しない ▼ ---
        if isinstance(raw, dict) and raw.get("errors"):
            return {
                "asin": asin,
                "raw": raw,
                "source": "api_error"
            }

        # === ② catalog_cache 保存（raw_json のみ） ===
        self._save_catalog_cache(
            asin=asin,
            region_raw_json=json.dumps(raw, ensure_ascii=False) 
        )

        # === ③ UI に返す（raw そのまま） ===
        return {
            "asin": asin,
            "raw": raw,
            "source": "api"
        }

    # --- ▼ SECTION 04: catalog_cache_region 読み込み ▼ ---
    def _get_cached_catalog(self, asin: str):
        import sqlite3, os

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_file = os.path.join(base_dir, "db", "a_catalog_cache.db")

        conn = get_conn("a_catalog_cache.db")

        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    region_raw_json,
                    region_updated_at
                FROM catalog_cache
                WHERE asin = %s
                AND region_marketplace_id = %s
                LIMIT 1
            """, ( asin, self.marketplace_id))

            row = cur.fetchone()

            if not row or not row["region_updated_at"]: 
                return None

            columns = [desc[0] for desc in cur.description] 
            return dict(row) 

        finally:
            conn.close()

    # --- ▼ SECTION 05: catalog_cache region部分の更新 ▼ ---
    def _save_catalog_cache(self, asin: str, region_raw_json: str = None):
        # print("[CATALOG REGION]SAVE CACHE CALLED", asin)

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_file = os.path.join(base_dir, "db", "a_catalog_cache.db")

        conn = get_conn("a_catalog_cache.db")

        now_utc = datetime.utcnow().isoformat()

        try:
            cur = conn.cursor()

            # --- 既存データ取得 ---
            cur.execute("""
                SELECT region_raw_json
                FROM catalog_cache
                WHERE asin = %s
                AND region_marketplace_id = %s
            """, (asin, self.marketplace_id))

            row = cur.fetchone()

            # --- 変更がある場合のみUPDATE ---
            old = json.dumps(json.loads(row["region_raw_json"]), sort_keys=True, ensure_ascii=False) if (row and row["region_raw_json"]) else None 
            new = json.dumps(json.loads(region_raw_json), sort_keys=True, ensure_ascii=False) if region_raw_json else None

            if row:
                if old != new:
                    cur.execute("""
                        UPDATE catalog_cache
                        SET
                            region_raw_json   = %s,
                            region_updated_at = %s,
                            updated_at        = %s,
                            r_catalog_ttl_at  = %s
                        WHERE
                            asin = %s
                            AND region_marketplace_id = %s
                    """, (
                        region_raw_json, now_utc, now_utc, now_utc, asin, self.marketplace_id))
                else:
                    cur.execute("""
                        UPDATE catalog_cache
                        SET
                            r_catalog_ttl_at = %s
                        WHERE
                            asin = %s
                            AND region_marketplace_id = %s
                    """, (
                        now_utc, asin, self.marketplace_id))

                # --- listed_items TTL同期 ---
                cur.execute("""
                    UPDATE listed_items
                    SET r_catalog_ttl_at = %s
                    WHERE user_id = %s
                    AND asin = %s
                    AND region_marketplace_id = %s
                """, (
                    now_utc,
                    self.user_id,
                    asin,
                    self.marketplace_id
                ))
                
                conn.commit()

        finally:
            conn.close()


