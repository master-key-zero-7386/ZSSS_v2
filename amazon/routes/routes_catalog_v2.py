# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon\routes\routes_catalog_v2.py
# 目的: catalog用統括ファイル（再設計・正テンプレ）
# ======================================================

import os
import sqlite3
from datetime import datetime
from datetime import datetime, timedelta
from amazon.db import get_conn

from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.adapters.catalog_adapter_home import CatalogAdapterHome
from amazon.adapters.catalog_adapter_region import CatalogAdapterRegion
from amazon.adapters.catalog_normalized_adapter import NormalizedCatalogAdapter
from amazon.adapters.listed_items_update_adapter import ListedItemsUpdate
from amazon.guard.guard_429 import is_blocked 
from amazon.utils.brand_gate_store import save_brand_gate_result
from amazon.core.price_calculator import shipping_calc, get_shipping_config

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "db")  

# --- ▼ SECTION 01: HOME Catalog 正規更新 ▼ ---
def update_home_catalog(*, user_id: int, asin: str, country_code: str):
    # === 01-1: HOME marketplace_id 確定 ===
    listed_db = os.path.join(DB_DIR, f"a_{country_code.lower()}_listed_items.db")
    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT home_marketplace_id
            FROM listed_items
            WHERE user_id = %s
              AND asin = %s
            LIMIT 1
        """, (user_id, asin))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("home_marketplace_id not found in listed_items")

    home_marketplace_id = row["home_marketplace_id"]

# === 01-2: HOME Catalog raw 取得（API） ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=home_marketplace_id,
    )
    adapter = CatalogAdapterHome(parent_adapter=base)
    result = adapter.get_full_catalog_item(asin)    
    raw = result.get("raw")

    # ★追加: 404 NOT_FOUND（HOME=仕入先に商品がもう存在しない）を検知
    errors = raw.get("errors") if isinstance(raw, dict) else None
    if errors and any(e.get("code") == "NOT_FOUND" for e in errors):
        conn = get_conn(f"a_{country_code.lower()}_listed_items.db")
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE listed_items
                SET information_status = 'INACTIVE',
                    inactive_reason = 'HOME_NOT_FOUND',
                    ttl_stop_status = 1,
                    updated_at = %s
                WHERE user_id = %s
                AND asin = %s
            """, (datetime.utcnow().isoformat(), user_id, asin))
            conn.commit()
        finally:
            conn.close()

        return {
            "status": "home_not_found",
            "asin": asin,
            "country_code": country_code,
        }

    # === 01-3: NORMALIZE（HOME） ===
    normalizer = NormalizedCatalogAdapter(parent_adapter=adapter)
    normalized = {
        "home_title":         normalizer._normalize_title(raw),
        "home_brand":         normalizer._normalize_brand(raw),
        "home_manufacturer":  normalizer._normalize_manufacturer(raw),
        "image_url":          normalizer._normalize_home_image_url(raw),
    }
    normalized.update(normalizer._normalize_dimensions_weight(raw))

    # --- ▼ 請求重量を「実際の送料設定」で再計算（画面表示と一致させる） ▼ ---
    if normalized.get("actual_weight_kg") is not None:
        shipping_config_row = get_shipping_config(user_id) or {}

        calc_result = shipping_calc(
            {
                "length_cm": normalized.get("length_cm"),
                "width_cm": normalized.get("width_cm"),
                "height_cm": normalized.get("height_cm"),
                "actual_weight_kg": normalized.get("actual_weight_kg"),
            },
            {
                "volumetric_divisor": shipping_config_row.get("volumetric_divisor", 5000),
                "padding_cm": shipping_config_row.get("padding_cm", 0),
                "pack_ratio": shipping_config_row.get("pack_ratio", 0),
            }
        )

        normalized["volumetric_weight_kg"] = calc_result["volumetric_weight_kg"]
        normalized["billable_weight_kg"] = calc_result["billable_weight_kg_rounded"]    

    # === 01-4: listed_items 更新（HOME） ===
    listed_db = os.path.join(DB_DIR, f"a_{country_code.lower()}_listed_items.db")
    updater = ListedItemsUpdate(base_dir=DB_DIR)
    updater.update_home_from_catalog_normalized(
        listed_db=listed_db,
        user_id=user_id,
        asin=asin,
        marketplace_id=home_marketplace_id,
        normalized=normalized,
    )

    # --- ▼ TTL更新（HOME CATALOG） ▼ ---
    cache_db = os.path.join(DB_DIR, "a_catalog_cache.db")

    conn = get_conn("a_catalog_cache.db")
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE catalog_cache
            SET h_catalog_ttl_at = %s
            WHERE asin = %s
            AND home_marketplace_id = %s
        """, (
            datetime.utcnow().isoformat(),
            asin,
            home_marketplace_id
        ))
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "asin": asin,
        "country_code": country_code,
        "source": result.get("source"),
    }

# --- ▼ SECTION 01: REGION Catalog 正規更新 ▼ ---
def update_region_catalog(*, user_id: int, asin: str, country_code: str):
    # === 01-01: REGION marketplace_id 確定 ===
    listed_db = os.path.join(DB_DIR, f"a_{country_code.lower()}_listed_items.db")

    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT region_marketplace_id
            FROM listed_items
            WHERE user_id = %s
              AND asin = %s
            LIMIT 1
        """, (user_id, asin))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("region_marketplace_id not found in listed_items")

    region_marketplace_id = row["region_marketplace_id"]

    # === 01-02: REGION Catalog raw 取得（API） ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=region_marketplace_id,
    )
    adapter = CatalogAdapterRegion(parent_adapter=base)

    result = adapter.get_full_catalog_item(asin)


    raw = result.get("raw")

    # === 01-03: NORMALIZE（REGION） ===
    normalizer = NormalizedCatalogAdapter(parent_adapter=adapter)
    normalized = {
        "region_title":         normalizer._normalize_title(raw),
        "region_brand":         normalizer._normalize_brand(raw),
        "region_manufacturer":  normalizer._normalize_manufacturer(raw),
    }
    normalized.update(normalizer._normalize_dimensions_weight(raw))


    # === 01-04: listed_items 更新（REGION） ===
    listed_db = os.path.join(DB_DIR, f"a_{country_code.lower()}_listed_items.db")
    updater = ListedItemsUpdate(base_dir=DB_DIR)
    updater.update_region_from_catalog_normalized(
        listed_db=listed_db,
        user_id=user_id,
        asin=asin,
        region=country_code.lower(),
        region_marketplace_id=region_marketplace_id,
        normalized=normalized,
    )

    # === 01-05 TTL更新（REGION CATALOG） ===
    cache_db = os.path.join(DB_DIR, "a_catalog_cache.db")
    conn = get_conn("a_catalog_cache.db")

    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE catalog_cache
            SET r_catalog_ttl_at = %s
            WHERE asin = %s
            AND region_marketplace_id = %s
        """, (
            datetime.utcnow().isoformat(),
            asin,
            region_marketplace_id
        ))
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "asin": asin,
        "country_code": country_code,
        "source": result.get("source"),
    }

