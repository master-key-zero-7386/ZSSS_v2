# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/services/listing_submit_service.py
# 目的: 出品ロジック（必須チェック / 出品実行）
# ==========================================================

from amazon.adapters.listings_items import put_listings_item, delete_listings_item, delete_listings_feed
from amazon.utils.brand_gate_store import save_brand_gate_result

# --- SECTION 01: Listing Submit Service（From：FIRST / ALL listing） ---
def submit_listing_service(user_id, country_code, marketplace_id, seller_sku, asin, price, quantity, handling_time,brand,record_id=None):    

    if price is None or quantity is None or handling_time is None:
        return {"status": "ERROR", "reason": "required field missing"}

    response = put_listings_item(
        user_id,
        country_code,
        marketplace_id,
        seller_sku,
        asin,
        price,
        quantity,
        handling_time,
    )

    # === Brand出品可否記録 === 
    errors = response.get("errors") if isinstance(response, dict) else None

    status = "NG" if errors else "OK"

    save_brand_gate_result(
        user_id=user_id,
        marketplace_id=marketplace_id,
        brand=brand,
        status=status,
        reason=str(errors) if errors else None
    )

    return response

# --- SECTION 02: Listing DELETE（From：Delete / ALL listing） ---
def delete_listing_item(user_id, country_code, marketplace_id, seller_sku):
    response = delete_listings_item(
        user_id,
        country_code,
        marketplace_id,
        seller_sku
    )

    return response

# --- SECTION 03: Bulk DELETE（From：Bulk Delete / ALL listing） ---
def bulk_delete_listing_item(user_id, country_code, marketplace_id, sku_list):
    return delete_listings_feed(
        user_id,
        country_code,
        marketplace_id,
        sku_list
    )

    return response




