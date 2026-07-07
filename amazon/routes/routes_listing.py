# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon\routes\routes_listing.py
# 目的: Listing（Pre/ALL）管理API
#      - ASINとSKUの登録・削除
#      - HOME/regionのカタログ情報をSP-APIで取得してDBへ反映
#      - Pre Listing / ALL Listing の一覧データを返す
# ==========================================================

from flask import Blueprint, request, jsonify, current_app, session

import os
import re
import json
import sqlite3
import traceback
import time
from datetime import datetime

from amazon.db import get_conn
from amazon.adapters import (AmazonAdapter, CatalogAdapterHome, CatalogAdapterRegion)
from amazon.adapters.catalog_image_extractor import CatalogImageExtractor
from amazon.adapters.pricing_adapter_home import PricingAdapterHome
from amazon.adapters.pricing_adapter_region import PricingAdapterRegion
from amazon.core.price_calculator import (calculate_shipping_result, get_shipping_rate, get_shipping_config)
from amazon.services.listing_submit_service import submit_listing_service
from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.services.listing_submit_service import delete_listing_item
from amazon.services.listing_submit_service import bulk_delete_listing_item
from amazon.services.blacklist_service import is_blacklisted, is_blacklisted_brand
from amazon.adapters.pricing_adapter_home import get_retail_seller_ids
from amazon.adapters.pricing_normalized_adapter import NormalizedPricingAdapter 
from amazon.core.price_calculator import get_pricing_master_rule
from amazon.adapters.pricing_rules_adapter import PricingRulesAdapter
from amazon.routes.routes_pricing_v2 import _get_offer_filter_rules


listing_bp = Blueprint("listing_bp", __name__)

# --- ▼ SECTION 01: HOME専用：ブランド・タイトル・価格・寸法更新処理 ▼ ---
def update_home_info(asin: str, user_id: int, home_data: dict, country_code: str):

    """
    HOME専用：
    globalRegion（= region）で指定された listed_items DB に HOME 情報を書く。
    ※ もう home_flag は一切参照しない！！
    """

    db_name = f"a_{country_code.lower()}_listed_items.db" 

    try:
        conn = get_conn("listed_items")
    except FileNotFoundError:
        print(f"[WARN] target listed_items DB not found") 
        return False    

    try:
        # --- 値取り出し ---
        home_title  = (home_data.get("home_title") or "").strip() if home_data else ""
        home_brand  = (home_data.get("home_brand") or "").strip() if home_data else ""
        length_cm   = home_data.get("length_cm")
        width_cm    = home_data.get("width_cm")
        height_cm   = home_data.get("height_cm")
        actual_wt   = home_data.get("actual_weight_kg")
        vol_wt      = home_data.get("volumetric_weight_kg")
        bill_wt     = home_data.get("billable_weight_kg")

        cur = conn.cursor()

        res = cur.execute("""
            UPDATE listed_items
               SET
                   home_title          = COALESCE(%s, home_title),
                   home_brand          = COALESCE(%s, home_brand),
                   length_cm           = COALESCE(%s, length_cm),
                   width_cm            = COALESCE(%s, width_cm),
                   height_cm           = COALESCE(%s, height_cm),
                   actual_weight_kg    = COALESCE(%s, actual_weight_kg),
                   volumetric_weight_kg= COALESCE(%s, volumetric_weight_kg),
                   billable_weight_kg  = COALESCE(%s, billable_weight_kg)
             WHERE asin = %s AND user_id = %s
        """, (home_title, home_brand,
              length_cm, width_cm, height_cm,
              actual_wt, vol_wt, bill_wt, asin, user_id))

        conn.commit()
        conn.close()

        print(f"[OK] HOME info updated for {asin}")
        return True

    except Exception as e:
        print(f"[ERR] HOME info update failed for {asin}: {e}")
        return False

# --- ▼ SECTION 02: region専用：ブランド・メーカー更新処理 ▼ ---
def update_region_info(asin: str, user_id: int, catalog_data: dict, country_code: str):
    """
    REGION専用：
    globalRegion（= region）で指定された listed_items DB に 情報を書く。
    """

    db_name = f"a_{country_code.lower()}_listed_items.db" 

    try:
        conn = get_conn("listed_items")
    except FileNotFoundError:
        print(f"[WARN] target listed_items DB not found")
        return False
        
    try:
        # --- region 用値取り出し ---
        region_brand        = (catalog_data.get("brand") or "").strip() if catalog_data else "" 
        region_manufacturer = (catalog_data.get("manufacturer") or "").strip() if catalog_data else ""  
        image_url           = (catalog_data.get("image_url") or "").strip() if catalog_data else ""  

        cur = conn.cursor()

        res = cur.execute("""
            UPDATE listed_items
               SET
                   region_brand        = COALESCE(%s, region_brand),
                   region_manufacturer = COALESCE(%s, region_manufacturer),
                   image_url           = COALESCE(%s, image_url)
             WHERE asin = %s AND user_id = %s
        """, 
        (
            region_brand,
            region_manufacturer,
            image_url,
            asin,
            user_id
        ))
            
        conn.commit()
        conn.close()

        print(f"[OK] REGION info updated for {asin}")
        return True

    except Exception as e:
        print(f"[ERR] REGION info update failed for {asin}: {e}") 
        return False

# --- ▼ SECTION 03: チェックセクション ▼ ---
@listing_bp.post("/listing/add")
def add_listing():
    try:
        data = request.get_json(force=True, silent=True) or {}
        items  = data.get("items") or []
        country_code = (data.get("country_code") or "").strip()
        user_id = session.get("user_id")

        if not items:
            return jsonify({"status": "error", "message": "No items provided"}), 400

        # --- 新DB：a_marketplaces.db から region を検証 ---
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__))) 
        db_market = os.path.join(base_dir, "db", "a_marketplaces.db")  

        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()

        cur.execute("SELECT country_code FROM marketplaces WHERE user_id = %s", (user_id,))
        valid_country_codes = [str(r[0]).strip().lower() for r in cur.fetchall()]
        conn.close()

        if country_code.lower() not in valid_country_codes:
            return jsonify({"status": "error", "message": f"Invalid country_code: {country_code}"}), 400

        # DBファイル名を決定
        conn = get_conn("listed_items")
        cur = conn.cursor()

        ok = []
        listed = []
        blacklist = []
        errors = []

        for item in items:
            asin = re.sub(r"[^A-Z0-9]", "", (item.get("asin") or "").strip().upper())
            sku = re.sub(r"[^\w\-]", "", (item.get("sku") or "").strip())
            if not asin or not sku:
                errors.append({"asin": asin, "sku": sku, "reason": "ASIN or SKU missing"})
                continue

            # 重複チェックはASINだけ
            cur.execute("SELECT 1 FROM listed_items WHERE asin=%s AND user_id=%s", (asin, user_id)) 
            row = cur.fetchone()

            if row:
                listed.append({"asin": asin, "sku": sku})
                continue

            now_utc = datetime.utcnow().isoformat()

            # 登録（catalog 情報のみ・価格は扱わない）
            cur.execute(
                """
                INSERT INTO listed_items 
                    (user_id, asin, sku, home_title, home_brand, image_url, region_brand, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, asin, sku, "", "", "", "", "pre", now_utc, now_utc)
            )
            ok.append({"asin": asin, "sku": sku})

        conn.commit()

        # Pre-Listing 一覧を取得（価格は含めない）
        cur.execute("""
            SELECT asin, sku, home_title, home_brand, image_url, region_brand, region_manufacturer
            FROM listed_items
            WHERE status='pre' AND user_id=%s
        """, (user_id,))
        pre_items = [{
            "asin": r[0],
            "sku": r[1],
            "home_title": r[2] or "",
            "home_brand": r[3] or "",
            "image_url": r[4] or "",
            "region_brand": r[5] or "",
            "region_manufacturer": r[6] or "",
        } for r in cur.fetchall()]
        
        return jsonify({
            "status": "success",
            "ok": ok,
            "listed": listed,
            "blacklist": blacklist,
            "errors": errors,
            "pre": pre_items
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 04: 共通 Shipping補正・設定 + Fee算定処理 ▼ ---
def _build_listing_row_with_shipping(
    row, user_id, marketplace_id, country_code, timezone, 
    black_asin_set=None, black_brand_set=None, 
    RETAIL_SELLER_IDS=None, 
    SHIPPING_CONFIG=None, 
    SHIPPING_RATE_ROWS=None,
    PRICING_CACHE_ROWS=None,
    CATALOG_CACHE_ROWS=None, 
    MARKETPLACE_HOST=None, 
    HOME_MARKETPLACE_HOST=None, 
    OFFER_FILTER_RULES=None, 
    PRICING_MASTER_RULES=None, 
    ACCOUNT_SELLER_ID=None, 
    BRAND_GATE_MAP=None, 
    SHIPPING_OVERRIDE_SET=None,
    P_min=None, P_max=None):

    # --- shipping_config取得 ---
    padding_cm = SHIPPING_CONFIG["padding_cm"] if SHIPPING_CONFIG else 0
    pack_ratio = SHIPPING_CONFIG["pack_ratio"] if SHIPPING_CONFIG else 1.0
    volum_div  = SHIPPING_CONFIG["volumetric_divisor"] if SHIPPING_CONFIG else 5000 

    # --- normalized ---
    normalized = {
        "length_cm": row["length_cm"],
        "width_cm": row["width_cm"],
        "height_cm": row["height_cm"],
        "actual_weight_kg": row["actual_weight_kg"],
    }

    shipping_config = {
        "volumetric_divisor": volum_div,
        "padding_cm": padding_cm,
        "pack_ratio": pack_ratio,
    }

    shipping_result = calculate_shipping_result(  
        normalized,
        shipping_config,
        user_id,
        marketplace_id,
        SHIPPING_RATE_ROWS
    )

    calc_result = shipping_result["calc_result"]  

    billable_weight = shipping_result["billable_weight"]  

    shipping_fee = shipping_result["shipping_fee"]    

    # --- Black ASIN Brand用 ---
    is_black_asin = (
        row["asin"].strip().lower() in black_asin_set
    )

    is_black_brand = (
        (row.get("home_brand") or "").strip().lower() in black_brand_set
        or
        (row.get("region_brand") or "").strip().lower() in black_brand_set
    )

    cache_row = PRICING_CACHE_ROWS.get(row["asin"])

    catalog_row = CATALOG_CACHE_ROWS.get(row["asin"])

    home_rank = None
    home_rank_title = None

    region_rank = None
    region_rank_title = None

    if catalog_row:

        # --- HOME --- # ここを修正

        home_data = json.loads(
            catalog_row["home_raw_json"] or "{}"
        )

        sales_ranks = home_data.get("salesRanks") or []

        try:

            cls = sales_ranks[0]["classificationRanks"]

            if cls:
                home_rank = cls[0].get("rank")
                home_rank_title = cls[0].get("title")

        except Exception:
            pass

        # --- REGION --- # ここを修正

        region_data = json.loads(
            catalog_row["region_raw_json"] or "{}"
        )

        sales_ranks = region_data.get("salesRanks") or []

        try:

            cls = sales_ranks[0]["classificationRanks"]

            if cls:
                region_rank = cls[0].get("rank")
                region_rank_title = cls[0].get("title")

        except Exception:
            pass        

    if cache_row and cache_row["home_offers_json"]:
        home_data = json.loads(cache_row["home_offers_json"])
    else:
        home_data = {"payload": {}}

    home_offers = (home_data.get("payload") or {}).get("Offers", [])

    if cache_row and cache_row["region_offers_json"]:  
        data = json.loads(cache_row["region_offers_json"])
        
        offer_count = (data.get("payload") or {}).get("Summary", {}).get("TotalOfferCount", 0)
    else:
        offer_count = 0
        data = {"payload": {}}

    home_amazon = 0
    home_fba = 0
    home_fbm = 0
    region_amazon = 0
    region_fba = 0
    region_fbm = 0

    offers = (data.get("payload") or {}).get("Offers", [])

    for o in home_offers:
        seller_id = o.get("SellerId")
        is_fba = o.get("IsFulfilledByAmazon", False)

        if seller_id and seller_id in RETAIL_SELLER_IDS:
            home_amazon += 1
        elif is_fba:
            home_fba += 1
        else:
            home_fbm += 1

    for o in offers:
        seller_id = o.get("SellerId")
        is_fba = o.get("IsFulfilledByAmazon", False)

        if seller_id and seller_id in RETAIL_SELLER_IDS:
            region_amazon += 1
        elif is_fba:
            region_fba += 1
        else:
            region_fbm += 1

    # --- host取得 ---
    marketplace_host = MARKETPLACE_HOST 
    home_marketplace_host = HOME_MARKETPLACE_HOST 

    # --- ▼ BrandGate取得 ▼ ---
    brand = str(row["region_brand"] or "").strip().lower()

    bg_row = BRAND_GATE_MAP.get(brand) if brand else None

    brand_gate_status = bg_row["status"] if bg_row else None
    brand_gate_reason = bg_row["reason"] if bg_row else None

    # --- ▼ HOME送料取得 ▼ ---
    home_shipping_amount = 0

    try:
        normalizer_home = NormalizedPricingAdapter(parent_adapter=None) 

        normalized_home = normalizer_home.normalize_home_offers(
            home_data
        )

        rules_home = OFFER_FILTER_RULES 

        pricing_rules_adapter_home = PricingRulesAdapter(rules_home, retail_seller_ids=RETAIL_SELLER_IDS)

        result_home = pricing_rules_adapter_home.select_home_cost_offer(
            normalized_home
        )

        selected_home = result_home.get("selected") if result_home else None

        if selected_home:
            home_shipping_amount = float(
                selected_home.get("shipping_amount") or 0
            )

    except Exception:
        home_shipping_amount = 0
        
    # --- ▼ REGION競合送料取得 ▼ ---
    region_shipping_amount = 0

    try:
        normalized_region = NormalizedPricingAdapter.normalize_region_offers(
            None,
            data
        )

        rules = dict(PRICING_MASTER_RULES or {}) 

        # --- 自分ID取得 ---
        my_seller_id = ACCOUNT_SELLER_ID

        rules["my_seller_id"] = my_seller_id  

        pricing_rules_adapter = PricingRulesAdapter(rules, marketplace_id=marketplace_id, shipping_override_set=SHIPPING_OVERRIDE_SET, retail_seller_ids=RETAIL_SELLER_IDS)

        result_offer = pricing_rules_adapter.select_region_price_offer(normalized_region        )

        selected_offer = result_offer.get("selected") if result_offer else None

        if selected_offer:
            region_shipping_amount = float(
                selected_offer.get("shipping_amount") or 0
            )

    except Exception:
        region_shipping_amount = 0 
    
    return {
        "asin": row["asin"],
        "sku": row["sku"],
        "home_title": row["home_title"],
        "home_brand": row["home_brand"],
        "image_url": row["image_url"],
        "length_cm": row["length_cm"],
        "width_cm": row["width_cm"],
        "height_cm": row["height_cm"],
        "actual_weight_kg": row["actual_weight_kg"],

        "actual_weight_kg_corrected": calc_result["actual_weight_kg_corrected"],
        "volumetric_weight_kg": calc_result["volumetric_weight_kg"],
        "billable_weight_kg": billable_weight,
        "shipping_fee": shipping_fee,

        "home_price": row["home_price"],
        "home_shipping_amount": home_shipping_amount,
        "region_price": row["region_price"], 
        "region_shipping_amount": region_shipping_amount,
        
        "final_price": row["final_price"],
        "profit_rate": row["profit_rate"],
        "min_price": row["min_price"], 
        "max_price": row["max_price"],
        "raw_min_price": row["raw_min_price"],
        "region_brand": row["region_brand"],
        "region_manufacturer": row["region_manufacturer"],
        "information_status": row["information_status"],
        "inactive_reason": row["inactive_reason"],
        "listing_status": row["listing_status"],

        "updated_at": row["updated_at"],
        "created_at": row["created_at"],   
        "home_timezone": timezone,   

        "is_black_asin": is_black_asin,
        "is_black_brand": is_black_brand,
        "offer_counts": {
            "home_amazon": home_amazon,
            "home_fba": home_fba,
            "home_fbm": home_fbm,        
            "region_amazon": region_amazon,
            "region_fba": region_fba,
            "region_fbm": region_fbm,
        },

        "home_marketplace_host": home_marketplace_host,
        "marketplace_host": marketplace_host,   

        "home_country_code": row["home_country_code"],
        "region_country_code": row["region_country_code"],        

        "brand_gate_status": brand_gate_status,
        "brand_gate_reason": brand_gate_reason, 

        "home_rank": home_rank,  
        "home_rank_title": home_rank_title, 
        "region_rank": region_rank, 
        "region_rank_title": region_rank_title,          
    }
    
# --- ▼ SECTION 05: 共通 Listing取得処理（status別） ▼ ---
def _get_listing_by_status(user_id, country_code, status_value, sort="created_desc", info_status="all", page=1, limit=100, keyword="", reason="all"):
    # --- marketplace_id + timezone取得 ---
    conn_mid = get_conn("a_marketplaces.db")
    cur_mid = conn_mid.cursor()

    cur_mid.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id = %s
        AND LOWER(country_code) = %s
        LIMIT 1
    """, (user_id, country_code))
    row_mid = cur_mid.fetchone()

    cur_mid.execute("""
        SELECT timezone, country_code
        FROM marketplaces
        WHERE user_id = %s
        AND home_flag = 1
        LIMIT 1
    """, (user_id,))
    row_tz = cur_mid.fetchone()

    HOME_COUNTRY = row_tz["country_code"] if row_tz else None

    conn_mid.close()

    if not row_mid:
        return None, 0, "marketplace_id not found"

    marketplace_id = row_mid["marketplace_id"]

    timezone = row_tz["timezone"] if row_tz else "UTC"

    db_name = f"a_{country_code.lower()}_listed_items.db"

    try:
        conn = get_conn("listed_items") 
    except FileNotFoundError:
        return None, 0, "DB not found: listed_items" 

    cur = conn.cursor() 

    offset = (page - 1) * limit  

    # 標準ソート登録日順       
    order_by = "created_at DESC"

    # ソート種類       
    if sort == "created_asc":               # 登録日
        order_by = "created_at ASC"
    elif sort == "updated_asc":             # 更新日
        order_by = "updated_at ASC"
    elif sort == "updated_desc":
        order_by = "updated_at DESC"    
    elif sort == "brand_asc":               # ブランド名
        order_by = "home_brand ASC"
    elif sort == "brand_desc":
        order_by = "home_brand DESC"        
    elif sort == "price_asc":               # 価格
        order_by = "final_price ASC"
    elif sort == "price_desc":
        order_by = "final_price DESC"
    elif sort == "weight_asc":              # 請求重量
        order_by = "billable_weight_kg ASC"
    elif sort == "weight_desc":
        order_by = "billable_weight_kg DESC"   

    if info_status == "INACTIVE" and sort == "created_desc":
        order_by = """
            CASE
                WHEN inactive_reason = 'BLACKLIST' THEN 1
                WHEN inactive_reason = 'COMPETITOR_RATIO' THEN 2
                WHEN inactive_reason = 'NO_PRICE' THEN 3
                WHEN inactive_reason = 'Setting MAX_PRICE' THEN 4
                WHEN inactive_reason = 'NO_CATALOG' THEN 5
                WHEN inactive_reason = 'HOME_NOT_FOUND' THEN 6
                WHEN inactive_reason = 'HOME_PRICE_NOT_FOUND' THEN 7
                WHEN inactive_reason = 'HOME_NO_OFFERS' THEN 8
                WHEN inactive_reason IS NULL OR inactive_reason = '' THEN 9                
                WHEN inactive_reason IS NULL OR inactive_reason = '' THEN 6
                ELSE 99
            END,
            created_at DESC
        """       

    # --- フィルタ条件 ---
    query_filter = " AND region_marketplace_id = %s"
    params_base = [status_value, user_id, marketplace_id]

    if sort == "brandgate_ok":
        query_filter += """
            AND LOWER(region_brand) IN (
                SELECT LOWER(brand)
                FROM brand_gate_result
                WHERE user_id = %s
                AND region_marketplace_id = %s
                AND status = 'OK'
            )
        """
        params_base.extend([user_id, marketplace_id])    

    if sort == "brandgate_approval":
        query_filter += """
            AND LOWER(region_brand) IN (
                SELECT LOWER(brand)
                FROM brand_gate_result
                WHERE user_id = %s
                AND region_marketplace_id = %s
                AND status = 'APPROVAL'
            )
        """
        params_base.extend([user_id, marketplace_id])

    if sort == "brandgate_ng":
        query_filter += """
            AND LOWER(region_brand) IN (
                SELECT LOWER(brand)
                FROM brand_gate_result
                WHERE user_id = %s
                AND region_marketplace_id = %s
                AND status = 'NG'
            )
        """
        params_base.extend([user_id, marketplace_id])     

    if sort == "brandgate_unknown":
        query_filter += """
            AND LOWER(region_brand) NOT IN (
                SELECT LOWER(brand)
                FROM brand_gate_result
                WHERE user_id = %s
                AND region_marketplace_id = %s
            )
        """
        params_base.extend([user_id, marketplace_id])

    elif info_status != "all":
        query_filter += " AND information_status = %s" 
        params_base.append(info_status)

    # --- INACTIVE理由での絞り込み ---
    if reason and reason != "all":
        query_filter += " AND inactive_reason = %s"
        params_base.append(reason)

    if keyword:
        query_filter += """
            AND (
                asin ILIKE %s
                OR sku ILIKE %s
                OR home_title ILIKE %s
                OR home_brand ILIKE %s
                OR home_manufacturer ILIKE %s
                OR region_brand ILIKE %s
                OR region_manufacturer ILIKE %s
            )
        """
        params_base.extend([
            f"%{keyword}%",
            f"%{keyword}%",
            f"%{keyword}%",
            f"%{keyword}%",
            f"%{keyword}%",
            f"%{keyword}%",    
            f"%{keyword}%"
        ])

    # --- データ取得 ---
    params_data = params_base + [limit, offset]

    cur.execute(f"""
        SELECT 
            asin, sku,
            home_marketplace_id,  
            hm.country_code AS home_country_code,
            rm.country_code AS region_country_code,
            COALESCE(home_title, '') AS home_title,
            COALESCE(home_brand, '') AS home_brand,
            COALESCE(image_url, '') AS image_url,
            length_cm,
            width_cm,
            height_cm,
            actual_weight_kg, 
            volumetric_weight_kg,
            billable_weight_kg,
            COALESCE(home_price, NULL) AS home_price,
            COALESCE(region_price, NULL) AS region_price,
            COALESCE(final_price, NULL) AS final_price,
            COALESCE(profit_rate, NULL) AS profit_rate,
            COALESCE(min_price, NULL) AS min_price,
            COALESCE(max_price, NULL) AS max_price, 
            COALESCE(raw_min_price, NULL) AS raw_min_price,
            COALESCE(region_brand, '') AS region_brand,
            COALESCE(region_manufacturer, '') AS region_manufacturer,
            COALESCE(information_status, '') AS information_status,
            COALESCE(listing_status, '') AS listing_status,
            COALESCE(inactive_reason, '') AS inactive_reason,
            li.updated_at,
            li.created_at
        FROM listed_items li

        LEFT JOIN marketplaces_master hm
            ON li.home_marketplace_id = hm.marketplace_id

        LEFT JOIN marketplaces_master rm
            ON li.region_marketplace_id = rm.marketplace_id
        WHERE LOWER(li.status) = %s
        AND li.user_id = %s
        {query_filter}
        ORDER BY {order_by}
        LIMIT %s OFFSET %s
    """, params_data)

    rows = cur.fetchall()

    # --- 件数取得 ---
    cur.execute(f"""
        SELECT COUNT(*) AS count
        FROM listed_items
        WHERE LOWER(status) = %s
        AND user_id = %s
        {query_filter}
    """, params_base)

    total_count = cur.fetchone()["count"]

    conn.close()

    result = []

    black_asin_set = set() 
    black_brand_set = set()  

    conn_bl = get_conn("a_all_blacklist_asin.db")
    cur_bl = conn_bl.cursor()         

    cur_bl.execute("""
        SELECT asin
        FROM blacklist_asin
        WHERE user_id = %s
        AND region_marketplace_id = %s
    """, (user_id, marketplace_id)) 

    black_asin_set = {
        str(r["asin"]).strip().lower()
        for r in cur_bl.fetchall()
    }

    conn_bl.close()
    
    conn_brand = get_conn(f"a_{country_code}_blacklist_brand.db") 
    cur_brand = conn_brand.cursor()  

    cur_brand.execute("""  
        SELECT brand
        FROM blacklist_brand
        WHERE user_id = %s
        AND region_marketplace_id = %s
    """, (user_id, marketplace_id))

    black_brand_set = {  
        str(r["brand"]).strip().lower()
        for r in cur_brand.fetchall()
    }

    conn_brand.close()     

    RETAIL_SELLER_IDS = get_retail_seller_ids()

    SHIPPING_CONFIG = get_shipping_config(user_id) 

    SHIPPING_RATE_ROWS = get_shipping_rate(user_id, marketplace_id)

    conn_cache = get_conn("a_pricing_cache.db")
    cur_cache = conn_cache.cursor()

    cur_cache.execute("""
        SELECT
            asin,
            home_offers_json,
            region_offers_json
        FROM pricing_cache
        WHERE region_marketplace_id = %s
    """, (marketplace_id,))

    PRICING_CACHE_ROWS = {
        r["asin"]: r
        for r in cur_cache.fetchall()
    }

    conn_cat = get_conn("a_catalog_cache.db")
    cur_cat = conn_cat.cursor()

    cur_cat.execute("""
        SELECT
            asin,
            home_raw_json,
            region_raw_json
        FROM catalog_cache
        WHERE region_marketplace_id = %s
    """, (marketplace_id,))

    CATALOG_CACHE_ROWS = {
        r["asin"]: r
        for r in cur_cat.fetchall()
    }

    conn_cat.close()

    conn_mst = get_conn("a_marketplaces_master.db")
    cur_mst = conn_mst.cursor()

    cur_mst.execute("""
        SELECT host
        FROM marketplaces_master
        WHERE marketplace_id = %s
        LIMIT 1
    """, (marketplace_id,))

    row_region = cur_mst.fetchone()

    row_home = None

    if rows:
        cur_mst.execute("""
            SELECT host
            FROM marketplaces_master
            WHERE marketplace_id = %s
            LIMIT 1
        """, (rows[0]["home_marketplace_id"],)) 

        row_home = cur_mst.fetchone() 

    conn_mst.close()

    MARKETPLACE_HOST = row_region["host"] if row_region else None
    HOME_MARKETPLACE_HOST = row_home["host"] if row_home else None

    OFFER_FILTER_RULES = _get_offer_filter_rules(user_id, "ALL")

    OFFER_FILTER_RULES["home_country"] = HOME_COUNTRY

    PRICING_MASTER_RULES = get_pricing_master_rule(user_id=user_id, country_code=country_code) 

    conn_acc = get_conn("a_account_master.db")

    cur_acc = conn_acc.cursor()

    cur_acc.execute("""
        SELECT account_seller_id
        FROM account_master
        WHERE user_id = %s
        AND country_code = %s
        LIMIT 1
    """, (user_id, country_code))

    acc = cur_acc.fetchone()

    conn_acc.close()

    ACCOUNT_SELLER_ID = acc["account_seller_id"] if acc else None    

    conn_bg = get_conn("a_brand_gate_result.db")
    cur_bg = conn_bg.cursor()

    cur_bg.execute("""
        SELECT brand, status, reason
        FROM brand_gate_result
        WHERE user_id = %s
        AND region_marketplace_id = %s
    """, (user_id, marketplace_id))

    BRAND_GATE_MAP = {
        str(r["brand"]).strip().lower(): r
        for r in cur_bg.fetchall()
    }

    conn_bg.close()    

    conn_ps = get_conn("a_pricing_settings.db")
    cur_ps = conn_ps.cursor()

    cur_ps.execute("""
        SELECT seller_id, shipping_amount
        FROM shipping_override_master
        WHERE marketplace_id = %s
    """, (marketplace_id,))

    SHIPPING_OVERRIDE_SET = {
        (r["seller_id"], float(r["shipping_amount"]))
        for r in cur_ps.fetchall()
    }

    conn_ps.close()

    for row in rows:
        result.append(
            _build_listing_row_with_shipping(
                row,
                user_id,
                marketplace_id,
                country_code,
                timezone,
                black_asin_set,
                black_brand_set,
                RETAIL_SELLER_IDS=RETAIL_SELLER_IDS,
                SHIPPING_CONFIG=SHIPPING_CONFIG,
                SHIPPING_RATE_ROWS=SHIPPING_RATE_ROWS,
                PRICING_CACHE_ROWS=PRICING_CACHE_ROWS,
                CATALOG_CACHE_ROWS=CATALOG_CACHE_ROWS,
                MARKETPLACE_HOST=MARKETPLACE_HOST,
                HOME_MARKETPLACE_HOST=HOME_MARKETPLACE_HOST,
                OFFER_FILTER_RULES=OFFER_FILTER_RULES,
                PRICING_MASTER_RULES=PRICING_MASTER_RULES,
                ACCOUNT_SELLER_ID=ACCOUNT_SELLER_ID,
                BRAND_GATE_MAP=BRAND_GATE_MAP,
                SHIPPING_OVERRIDE_SET=SHIPPING_OVERRIDE_SET
            )
        )
        
    return result, total_count, None

# --- ▼ SECTION 06: Pre Listing 取得処理 ▼ ---
@listing_bp.route("/get_prelisting", methods=["GET"])
def get_prelisting():
    try:
        keyword = (request.args.get("keyword") or "").strip().lower()
        keyword = re.sub(r"[ 　]+", "", keyword)   # スペース削除
        keyword = re.sub(r"[^a-z0-9ぁ-んァ-ン一-龥]", "", keyword)  # 記号削除

        country_code = (request.args.get("country_code") or "").strip().lower()
        user_id = request.args.get("user_id") or session.get("user_id")

        if not country_code:
            return jsonify({"status": "error", "message": "country_code is required"}), 400

        sort = request.args.get("sort") or "created_desc"

        info_status = request.args.get("info_status") or "all"
        reason = request.args.get("reason") or "all"

        page = int(request.args.get("page") or 1)
        keyword = request.args.get("keyword") or ""
        rows, total_count, err = _get_listing_by_status(user_id, country_code, "pre", sort, info_status, page=page, keyword=keyword, reason=reason)

        if err:
            return jsonify({"status": "error", "message": err}), 400

        return jsonify({"status": "success", "pre": rows, "total_count": total_count})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 07: Pre → ALL 移動処理 ▼ ---
@listing_bp.route("/get_alllisting", methods=["GET"])
def get_alllisting():
    try:
        country_code = (request.args.get("country_code") or "").strip().lower()
        user_id = request.args.get("user_id") or session.get("user_id")

        if not country_code:
            return jsonify({"status": "error", "message": "country_code is required"}), 400

        sort = request.args.get("sort") or "created_desc" 

        info_status = request.args.get("info_status") or "all"
        reason = request.args.get("reason") or "all"

        page = int(request.args.get("page") or 1)
        keyword = request.args.get("keyword") or ""
        rows, total_count, err = _get_listing_by_status(user_id, country_code, "listed", sort, info_status, page=page, keyword=keyword, reason=reason)
        
        if err:
            return jsonify({"status": "error", "message": err}), 400

        return jsonify({"status": "success", "all": rows, "total_count": total_count})
        

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 08: Listing DB検索（Pre / All 共通） ▼ ---
@listing_bp.route("/search_listing", methods=["GET"])
def search_listing():

    try:
        country_code = (request.args.get("country_code") or "").strip().lower()
        user_id = request.args.get("user_id") or session.get("user_id")

        mode = request.args.get("mode")
        keyword = (request.args.get("keyword") or "").strip()
        detail = request.args.get("detail") == "true"

        sort = request.args.get("sort") or "created_desc"  

        # 標準ソート登録日順       
        order_by = "created_at DESC"

        # ソート種類       
        if sort == "created_asc":               # 登録日
            order_by = "created_at ASC"
        elif sort == "brand_asc":               # ブランド名
            order_by = "region_brand ASC"
        elif sort == "brand_desc":
            order_by = "region_brand DESC"        
        elif sort == "price_asc":               # 価格
            order_by = "final_price ASC"
        elif sort == "price_desc":
            order_by = "final_price DESC"
        elif sort == "weight_asc":              # 請求重量
            order_by = "billable_weight_kg ASC"
        elif sort == "weight_desc":
            order_by = "billable_weight_kg DESC"            

        status_value = "pre" if mode == "pre" else "listed"
        
        db_name = f"a_{country_code}_listed_items.db" 

        try:
            conn = get_conn(db_name) 
        except FileNotFoundError:
            return jsonify({"status": "error", "message": f"DB not found: {db_name}"}), 500 

        cur = conn.cursor()


        if detail:

            info_status = request.args.get("info_status") or "all"

            query_filter = ""
            params = [
                user_id,
                status_value,
                f"%{keyword}%",
                f"%{keyword}%",
                f"%{keyword}%",
                f"%{keyword}%",
                f"%{keyword}%",
                f"%{keyword}%",
                f"%{keyword}%"
            ]

            if info_status != "all":
                query_filter = " AND information_status = %s"
                params.append(info_status)

            reason = request.args.get("reason") or "all"
            if reason != "all":
                query_filter += " AND inactive_reason = %s"
                params.append(reason)

            cur.execute(f"""
                SELECT li.*,
                    hm.country_code AS home_country_code,
                    rm.country_code AS region_country_code
                FROM listed_items li
                LEFT JOIN marketplaces_master hm
                    ON li.home_marketplace_id = hm.marketplace_id
                LEFT JOIN marketplaces_master rm
                    ON li.region_marketplace_id = rm.marketplace_id
                WHERE li.user_id = %s
                AND LOWER(li.status) = %s
                AND (
                    LOWER(li.asin) LIKE LOWER(%s)
                    OR LOWER(li.sku) LIKE LOWER(%s)
                    OR LOWER(li.home_title) LIKE LOWER(%s)
                    OR LOWER(li.home_brand) LIKE LOWER(%s)
                    OR LOWER(li.region_title) LIKE LOWER(%s)
                    OR LOWER(li.region_brand) LIKE LOWER(%s)
                    OR LOWER(li.region_manufacturer) LIKE LOWER(%s)
                )
                {query_filter}
                ORDER BY li.created_at DESC
                LIMIT 200
            """, params)            

        else:

            info_status = request.args.get("info_status") or "all"

            query_filter = ""
            params = [
                user_id,
                status_value,
                f"%{keyword}%"
            ]

            if info_status != "all":
                query_filter = " AND information_status = %s"
                params.append(info_status)

            reason = request.args.get("reason") or "all"
            if reason != "all":
                query_filter += " AND inactive_reason = %s"
                params.append(reason)

            cur.execute(f"""
                SELECT li.*,
                    hm.country_code AS home_country_code,
                    rm.country_code AS region_country_code
                FROM listed_items li
                LEFT JOIN marketplaces_master hm
                    ON li.home_marketplace_id = hm.marketplace_id
                LEFT JOIN marketplaces_master rm
                    ON li.region_marketplace_id = rm.marketplace_id
                WHERE li.user_id = %s
                AND LOWER(li.status) = %s
                AND li.asin LIKE %s
                {query_filter}
                ORDER BY li.created_at DESC
                LIMIT 200
            """, params)

        rows = cur.fetchall()
        conn.close()

        conn_m = get_conn("a_marketplaces.db") 
        cur_m = conn_m.cursor() 

        cur_m.execute("""
            SELECT marketplace_id
            FROM marketplaces
            WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
            LIMIT 1
        """, (user_id, country_code))
        r = cur_m.fetchone()
        marketplace_id = r["marketplace_id"] if r else None 

        cur_m.execute("""
            SELECT timezone
            FROM marketplaces
            WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
            LIMIT 1
        """, (user_id, country_code))
        r_tz = cur_m.fetchone()
        timezone = r_tz["timezone"] if r_tz else "UTC"

        cur_m.execute("""
            SELECT timezone, country_code
            FROM marketplaces
            WHERE user_id = %s
            AND home_flag = 1
            LIMIT 1
        """, (user_id,))
        row_tz_home = cur_m.fetchone()

        HOME_COUNTRY = row_tz_home["country_code"] if row_tz_home else None
        
        conn_m.close()

        black_asin_set = set()
        black_brand_set = set()

        conn_bl = get_conn("a_all_blacklist_asin.db")
        cur_bl = conn_bl.cursor()

        cur_bl.execute("""
            SELECT asin
            FROM blacklist_asin
            WHERE user_id = %s
            AND region_marketplace_id = %s
        """, (user_id, marketplace_id))

        black_asin_set = {
            str(r["asin"]).strip().lower()
            for r in cur_bl.fetchall()
        }

        conn_bl.close()

        conn_brand = get_conn(f"a_{country_code}_blacklist_brand.db")
        cur_brand = conn_brand.cursor()

        cur_brand.execute("""
            SELECT brand
            FROM blacklist_brand
            WHERE user_id = %s
            AND region_marketplace_id = %s
        """, (user_id, marketplace_id))

        black_brand_set = {
            str(r["brand"]).strip().lower()
            for r in cur_brand.fetchall()
        }

        conn_brand.close()

        RETAIL_SELLER_IDS = get_retail_seller_ids()

        SHIPPING_CONFIG = get_shipping_config(user_id) 
        
        SHIPPING_RATE_ROWS = get_shipping_rate(user_id, marketplace_id)        

        conn_cache = get_conn("a_pricing_cache.db")
        cur_cache = conn_cache.cursor()

        cur_cache.execute("""
            SELECT
                asin,
                home_offers_json,
                region_offers_json
            FROM pricing_cache
            WHERE region_marketplace_id = %s
        """, (marketplace_id,))

        PRICING_CACHE_ROWS = {
            r["asin"]: r
            for r in cur_cache.fetchall()
        }

        conn_cat = get_conn("a_catalog_cache.db")
        cur_cat = conn_cat.cursor()

        cur_cat.execute("""
            SELECT
                asin,
                home_raw_json,
                region_raw_json
            FROM catalog_cache
            WHERE region_marketplace_id = %s
        """, (marketplace_id,))

        CATALOG_CACHE_ROWS = {
            r["asin"]: r
            for r in cur_cat.fetchall()
        }

        conn_cat.close()

        conn_cache.close()

        conn_mst = get_conn("a_marketplaces_master.db")
        cur_mst = conn_mst.cursor()

        cur_mst.execute("""
            SELECT host
            FROM marketplaces_master
            WHERE marketplace_id = %s
            LIMIT 1
        """, (marketplace_id,))

        row_region = cur_mst.fetchone()

        row_home = None

        if rows:
            cur_mst.execute("""
                SELECT host
                FROM marketplaces_master
                WHERE marketplace_id = %s
                LIMIT 1
            """, (rows[0]["home_marketplace_id"],))

            row_home = cur_mst.fetchone()

        conn_mst.close()

        MARKETPLACE_HOST = row_region["host"] if row_region else None
        HOME_MARKETPLACE_HOST = row_home["host"] if row_home else None

        OFFER_FILTER_RULES = _get_offer_filter_rules(user_id, "ALL")
        OFFER_FILTER_RULES["home_country"] = HOME_COUNTRY

        PRICING_MASTER_RULES = get_pricing_master_rule(user_id=user_id, country_code=country_code) 

        conn_acc = get_conn("a_account_master.db")
        cur_acc = conn_acc.cursor()

        cur_acc.execute("""
            SELECT account_seller_id
            FROM account_master
            WHERE user_id = %s
            AND country_code = %s
            LIMIT 1
        """, (user_id, country_code))

        acc = cur_acc.fetchone()

        conn_acc.close()

        ACCOUNT_SELLER_ID = acc["account_seller_id"] if acc else None

        conn_bg = get_conn("a_brand_gate_result.db")
        cur_bg = conn_bg.cursor()

        cur_bg.execute("""
            SELECT brand, status, reason
            FROM brand_gate_result
            WHERE user_id = %s
            AND region_marketplace_id = %s
        """, (user_id, marketplace_id))

        BRAND_GATE_MAP = {
            str(r["brand"]).strip().lower(): r
            for r in cur_bg.fetchall()
        }

        conn_bg.close()

        result = []
        for row in rows:
            result.append(
                _build_listing_row_with_shipping(
                    row,
                    user_id,
                    marketplace_id,
                    country_code,
                    timezone,
                    black_asin_set,
                    black_brand_set,
                    RETAIL_SELLER_IDS=RETAIL_SELLER_IDS,
                    SHIPPING_CONFIG=SHIPPING_CONFIG,
                    SHIPPING_RATE_ROWS=SHIPPING_RATE_ROWS,
                    PRICING_CACHE_ROWS=PRICING_CACHE_ROWS,
                    CATALOG_CACHE_ROWS=CATALOG_CACHE_ROWS,
                    MARKETPLACE_HOST=MARKETPLACE_HOST,
                    HOME_MARKETPLACE_HOST=HOME_MARKETPLACE_HOST,
                    OFFER_FILTER_RULES=OFFER_FILTER_RULES,
                    PRICING_MASTER_RULES=PRICING_MASTER_RULES,
                    ACCOUNT_SELLER_ID=ACCOUNT_SELLER_ID,
                    BRAND_GATE_MAP=BRAND_GATE_MAP
                )
            )

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 09: UI表示用（APIは叩かない / DB参照＋画像補完のみ） ▼ ---
@listing_bp.post("/fetch_item_info")
def fetch_item_info():
    data = request.get_json(force=True)

    asin   = (data.get("asin") or "").strip().upper()
    country_code = (data.get("country_code") or "").strip().lower()

    if not asin or not country_code:
        return jsonify({"status": "error", "message": "asin and country_code required"}), 400

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "not logged in"}), 401

    # --- region 正当性チェック（user_id ベース） ---
    conn_market = get_conn("a_marketplaces.db")
    cur_market = conn_market.cursor()
    cur_market.execute(
        "SELECT country_code FROM marketplaces WHERE user_id = %s", (user_id,)
    )
    valid_country_codes = [str(r[0]).strip().lower() for r in cur_market.fetchall()]
    conn_market.close()

    if country_code not in valid_country_codes:
        return jsonify({
            "status": "error",
            "message": f"Invalid country_code: {country_code}"
        }), 400

    # --- listed_items DB 読み込み ---
    db_name = f"a_{country_code}_listed_items.db"  

    try:
        conn = get_conn(db_name) 
    except FileNotFoundError:
        return jsonify({"status": "error", "message": f"DB not found: {db_name}"}), 500

    cur = conn.cursor() 

    cur.execute("""
        SELECT
            home_brand,
            home_title,
            length_cm,
            width_cm,
            height_cm,
            actual_weight_kg
        FROM listed_items
        WHERE asin = %s AND user_id = %s
    """, (asin, user_id))
    row = cur.fetchone()
    conn.close()

    ui_home_brand = ""
    ui_home_title = ""
    ui_length_cm = None
    ui_width_cm = None
    ui_height_cm = None
    ui_actual_weight_kg = None

    if row:
        (
            ui_home_brand,
            ui_home_title,
            ui_length_cm,
            ui_width_cm,
            ui_height_cm,
            ui_actual_weight_kg,
        ) = row

    # --- REGION 画像補完（catalog とは別ルート） ---
    extractor = CatalogImageExtractor(
        user_id=user_id,
        country_code=country_code.upper()
    )
    region_image_url = extractor.get_image_url(asin) or ""

    # --- REGION 情報更新（画像のみ） ---
    region_data = {
        "image_url": region_image_url,
    }

    update_region_info(
        asin=asin,
        user_id=user_id,
        catalog_data=region_data,
        country_code=country_code
    )

    # --- UI 返却 ---
    return jsonify({
        "status": "ok",
        "asin": asin,
        "home_brand": ui_home_brand,
        "home_title": ui_home_title,
        "image_url": region_image_url,
        "length_cm": ui_length_cm,
        "width_cm": ui_width_cm,
        "height_cm": ui_height_cm,
        "actual_weight_kg": ui_actual_weight_kg,
    })

# --- ▼ SECTION 10: Delete Listing DBリストから削除処理 ▼ ---
@listing_bp.route("/delete_item", methods=["POST"])
def delete_item():
    """Pre/ALL Listing から ASIN単体削除 + cache同期削除（ユーザー別処理版）"""

    data = request.get_json()

    asin = data.get("asin")
    sku  = data.get("sku")

    # --- list対応 ---
    if isinstance(sku, list):
        sku = sku[0]

    # --- 文字列 ['SKU'] 対応 ---
    if isinstance(sku, str) and sku.startswith("["):
        sku = sku.strip("[]'\"")

    asin = (asin or "").strip()
    sku  = (sku or "").strip()
    
    country_code = (data.get("country_code") or "").strip().lower() 
    user_id = session.get("user_id")     

    # status判定（pre / all）
    status = "listed" if (data.get("status") or "").lower() == "all" else "pre"

    # --- Amazon削除API（ALLのみ） ---
    if status == "listed":

        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT marketplace_id
            FROM marketplaces
            WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
        """, (user_id, country_code))

        row = cur.fetchone()
        conn.close()

        if row and sku:

            marketplace_id = row["marketplace_id"]

            delete_listing_item(
                user_id=user_id,
                country_code=country_code,
                marketplace_id=marketplace_id,
                seller_sku=sku
            )
            
    try:
        # ============================================================
        # ★ listed_items 削除処理（ユーザーID条件を追加） 
        # ============================================================
        db_name = f"a_{country_code}_listed_items.db"

        try:
            conn = get_conn(db_name) 
        except FileNotFoundError:
            return jsonify({"status": "error", "message": f"database not found: {db_name}"}), 500

        cur = conn.cursor()         

        if sku:
            cur.execute("""
                DELETE FROM listed_items
                WHERE asin=%s AND sku=%s AND user_id=%s      
            """, (asin, sku, user_id))
        else:
            cur.execute("""
                DELETE FROM listed_items
                WHERE asin=%s AND user_id=%s     
            """, (asin, user_id))

        deleted_main = cur.rowcount
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "asin": asin,
            "sku": sku
        })

    except Exception as e:
        print("[ERR] delete_item failed:", e)
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 11: Bulk Delete（From：ALL / Pre 一括削除） ▼ ---
@listing_bp.route("/bulk_delete_items", methods=["POST"])
def bulk_delete_items():

    data = request.get_json()
    items = data.get("items") or []
    status = data.get("status")

    user_id = session.get("user_id")

    if not items:
        return jsonify({"status": "success", "results": []}) 

    country_code = (items[0].get("country_code") or "").strip().lower()    

    db_name = f"a_{country_code}_listed_items.db" 

    try:
        conn = get_conn(db_name)  
    except FileNotFoundError:
        return jsonify({"status": "error", "message": f"database not found: {db_name}"}), 500  

    cur = conn.cursor()  

    for item in items:
        sku = (item.get("sku") or "").strip()

        if not sku:
            continue

        cur.execute("""
            UPDATE listed_items
            SET deleting_flag = 1
            WHERE sku = %s
        """, (sku,))

    conn.commit()
    conn.close()  

    results = []

    if not items:
        return jsonify({"status": "success", "results": results})

    # --- country_codeごとに sku_list をまとめる ---
    country_sku_map = {}
    for item in items:
        country_code = (item.get("country_code") or "").strip().lower()
        sku = item.get("sku")

        # --- list対応 ---
        if isinstance(sku, list):
            sku = sku[0]

        # --- 文字列 ['SKU'] 対応 ---
        if isinstance(sku, str) and sku.startswith("["):
            sku = sku.strip("[]'\"")

        sku = (sku or "").strip()

        if country_code not in country_sku_map:
            country_sku_map[country_code] = []

        country_sku_map[country_code].append(sku)

    # --- Bulk処理（Feed + DB削除） ---
    for country_code, sku_list in country_sku_map.items():

        # marketplace_id取得
        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT marketplace_id
            FROM marketplaces
            WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
        """, (user_id, country_code))
        row = cur.fetchone()
        conn.close()

        if not row:
            continue
        marketplace_id = row["marketplace_id"]

        # --- API削除（Bulk Feed） ---
        if str(status).lower() == "listed":
            feed_response = bulk_delete_listing_item(
                user_id=user_id,
                country_code=country_code,
                marketplace_id=marketplace_id,
                sku_list=sku_list
            )
            print("BULK FEED RESPONSE:", feed_response, flush=True)


            if isinstance(feed_response, dict):
                print("FEED ID:", feed_response.get("feedId"), flush=True)  # 一括処理確認ログ削除NG

        # --- DB削除・cache削除（単体Deleteと同じ処理） ---
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_file = os.path.join(base_dir, "db", f"a_{country_code}_listed_items.db")

        db_name = f"a_{country_code}_listed_items.db"

        try:
            conn = get_conn(db_name) 
        except FileNotFoundError:
            continue 

        cur = conn.cursor() 

        for sku in sku_list:
            try:
                if sku:
                    cur.execute("""
                        DELETE FROM listed_items
                        WHERE sku=%s AND user_id=%s
                    """, (sku, user_id))
                else:
                    cur.execute("""
                        DELETE FROM listed_items
                        WHERE user_id=%s
                    """, (user_id,))

                print(f"[DB DELETE COMPLETE] SKU: {sku}", flush=True)
                results.append({
                    "sku": sku,
                    "status": "ok"
                })

            except Exception as e:
                print(f"[DB DELETE ERROR] SKU: {sku} → {e}", flush=True)
                results.append({
                    "sku": sku,
                    "status": "error",
                    "message": str(e)
                })

        conn.commit()
        conn.close()   

    return jsonify({
        "status": "success",
        "results": results
    })

# --- ▼ SECTION 12: Pre → ALL 移動処理 ▼ ---
@listing_bp.route("/move_to_all", methods=["POST"])
def move_to_all():
    """Pre-Listing の ASIN を ALL（出品済）へ移動"""

    try:
        data = request.get_json()
        asin = (data.get("asin") or "").strip().upper()
        country_code = (data.get("country_code") or "").strip()   
        user_id = session.get("user_id")  

        conn_m = get_conn("a_marketplaces.db") 
        cur_m = conn_m.cursor()  

        cur_m.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
        LIMIT 1
        """, (user_id, country_code))

        r = cur_m.fetchone()
        marketplace_id = r["marketplace_id"] if r else None

        conn_m.close()      

        if not asin:
            return jsonify({"status": "error", "message": "ASINが指定されていません"})

        # リトライ付きでロック回避
        max_retry = 5
        for attempt in range(max_retry):
            try:
                conn = get_conn(f"a_{country_code}_listed_items.db") 
                cur = conn.cursor()                  

                # --- ▼ 出品用データ取得 ▼ ---
                cur.execute("""
                    SELECT 
                        sku,
                        final_price,
                        strategy_quantity,
                        strategy_handling_time
                    FROM listed_items
                    WHERE asin=%s AND user_id=%s
                """, (asin, user_id))

                row = cur.fetchone()

                if not row:
                    conn.close()
                    return jsonify({"status": "error", "message": "listing data not found"})

                seller_sku = row["sku"]
                price = row["final_price"] 
                strategy_quantity = row["strategy_quantity"] 
                strategy_handling_time = row["strategy_handling_time"]               

                # --- ▼ quantity決定 ▼ ---
                strategy_quantity = int(strategy_quantity or 0)

                if strategy_quantity >= 1:
                    quantity = strategy_quantity
                else:
                    quantity = 1           # 出品在庫数量

                # --- ▼ handling_time決定 ▼ ---
                rules = get_pricing_master_rule( 
                    user_id=user_id,    
                    country_code=country_code 
                )    

                if rules and rules.get("default_handling_time") and int(rules["default_handling_time"]) >= 1: 
                    handling_time = int(rules["default_handling_time"])                     
                else:
                    handling_time = strategy_handling_time
                    

                now_utc = datetime.utcnow().isoformat()  

                # ★ ステータス更新（価格は一切触らない）
                cur.execute("""
                    UPDATE listed_items
                    SET 
                        status = 'listed',
                        updated_at = %s
                    WHERE asin=%s AND status='pre' AND user_id=%s
                """, (now_utc, asin, user_id))

                if cur.rowcount == 0:
                    conn.close()
                    return jsonify({"status": "error", "message": "該当ASINが見つかりません"})

                conn.commit()

                # --- ▼ Amazon出品 ▼ ---
                # --- ▼ brand取得（catalog_cache） ▼ ---
                base = AmazonAdapter(
                    user_id=user_id,
                    country_code=country_code,
                    marketplace_id=marketplace_id
                )
                adapter = CatalogAdapterRegion(parent_adapter=base)

                cache = adapter._get_cached_catalog(asin)

                brand = "UNKNOWN"

                if cache and cache.get("region_raw_json"):
                    try:
                        data = json.loads(cache["region_raw_json"])
                        brand_list = data.get("attributes", {}).get("brand", [])
                        if brand_list and isinstance(brand_list, list):
                            brand = brand_list[0].get("value") or "UNKNOWN"
                    except:
                        pass

                submit_listing_service(
                    user_id,  
                    country_code,
                    marketplace_id,
                    seller_sku,
                    asin,
                    price,
                    quantity,
                    handling_time,
                    brand
                )

                conn.close()

                return jsonify({
                    "status": "success",
                    "asin": asin
                })

            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    time.sleep(0.5)
                    continue
                raise e

        return jsonify({"status": "error", "message": "DBロックが解除されませんでした"})

    except Exception as e:
        import traceback
        print("move_to_all error:", traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 13: Bulk PRE → ALL ▼ ---
@listing_bp.route("/bulk_move_to_all", methods=["POST"])
def bulk_move_to_all():

    data = request.get_json()

    asins = data.get("asins", [])
    country_code = data.get("country_code")
    user_id = session.get("user_id")

    # --- ▼ marketplace_id取得 ▼ --- 
    conn_mid = get_conn("a_marketplaces.db") 
    cur_mid = conn_mid.cursor() 

    cur_mid.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id = %s
        AND LOWER(country_code) = %s
        LIMIT 1
    """, (user_id, country_code.lower())) 

    row_mid = cur_mid.fetchone() 
    conn_mid.close() 

    if not row_mid: 
        return jsonify({"status": "error", "message": "marketplace_id not found"}) 

    marketplace_id = row_mid["marketplace_id"]     

    db_name = f"a_{country_code}_listed_items.db"

    try:
        conn = get_conn(db_name)
    except FileNotFoundError:
        return jsonify({"status": "error", "message": f"database not found: {db_name}"}), 500

    cur = conn.cursor()   

    for asin in asins:

        print(f"[BULK MOVE] ASIN:{asin}", flush=True)  # 一括処理確認ログ削除NG

        # --- ▼ 出品用データ取得 ▼ --- 
        # --- ▼ 出品用データ取得 ▼ --- 
        cur.execute("""
            SELECT
                sku,
                final_price,
                strategy_quantity,
                strategy_handling_time
            FROM listed_items
            WHERE asin=%s AND user_id=%s
        """, (asin, user_id))

        row = cur.fetchone()

        if not row:
            continue

        seller_sku = row["sku"] 
        price = row["final_price"] 
        strategy_quantity = row["strategy_quantity"] 
        strategy_handling_time = row["strategy_handling_time"] 

        # --- ▼ quantity決定 ▼ ---
        strategy_quantity = int(strategy_quantity or 0) 

        if strategy_quantity >= 1: 
            quantity = strategy_quantity
        else: 
            quantity = 1 

        # --- ▼ handling_time決定 ▼ --- 
        rules = get_pricing_master_rule( 
            user_id=user_id,    
            country_code=country_code 
        )  

        if rules and rules.get("default_handling_time") and int(rules["default_handling_time"]) >= 1: 
            handling_time = int(rules["default_handling_time"]) 
        else:
            handling_time = strategy_handling_time

        now_utc = datetime.utcnow().isoformat() 

        cur.execute("""
            UPDATE listed_items
            SET
                status='listed',
                updated_at=%s
            WHERE asin=%s AND status='pre' AND user_id=%s
        """, (now_utc, asin, user_id))  

        if cur.rowcount == 0: 
            continue 

    conn.commit()

    # --- ▼ brand取得（catalog_cache） ▼ --- 
    base = AmazonAdapter( 
        user_id=user_id, 
        country_code=country_code, 
        marketplace_id=marketplace_id 
    ) 

    adapter = CatalogAdapterRegion(parent_adapter=base) 

    cache = adapter._get_cached_catalog(asin) 

    brand = "UNKNOWN" 

    if cache and cache.get("region_raw_json"): 
        try: 
            data = json.loads(cache["region_raw_json"]) 
            brand_list = data.get("attributes", {}).get("brand", []) 

            if brand_list and isinstance(brand_list, list): 
                brand = brand_list[0].get("value") or "UNKNOWN" 

        except: 
            pass 

    print(f"[BULK SUBMIT] ASIN:{asin}", flush=True)  # 一括処理確認ログ削除NG
        
    submit_listing_service( 
        user_id, 
        country_code, 
        marketplace_id, 
        seller_sku, 
        asin, 
        price, 
        quantity, 
        handling_time, 
        brand 
    ) 

    conn.close()

    return jsonify({"status": "success"})

# --- ▼ SECTION 14 ALL 出品戦略 保存処理 ▼ ---
@listing_bp.route("/update_strategy", methods=["POST"])
def update_strategy():
    """
    ALL Listing：出品戦略（価格・在庫・売り切り・HT）保存
    """
    try:
        data = request.get_json() or {}

        asin   = (data.get("asin") or "").strip()
        country_code = (data.get("country_code") or "").strip()
        user_id = session.get("user_id")   # ★ SaaS必須

        if not asin or not country_code or not user_id:
            return jsonify({"status": "error", "message": "missing parameter"})

        # --- 正規化 ---
        override_price = data.get("override_price")
        if override_price in ("", None):
            override_price = None
        else:
            override_price = float(override_price)

        strategy_quantity = data.get("strategy_quantity")
        strategy_quantity = int(strategy_quantity) if str(strategy_quantity).isdigit() else 0

        strategy_sellout = 1 if data.get("strategy_sellout") else 0

        strategy_handling_time = data.get("strategy_handling_time")
        strategy_handling_time = int(strategy_handling_time) if str(strategy_handling_time).isdigit() and int(strategy_handling_time) > 0 else 7

        db_name = f"a_{country_code}_listed_items.db"

        try:
            conn = get_conn(db_name)  
        except FileNotFoundError:
            return jsonify({"status": "error", "message": f"DB not found: {db_name}"}), 500  

        cur = conn.cursor() 

        now_utc = datetime.utcnow().isoformat()
        # --- 更新 ---
        cur.execute("""
            UPDATE listed_items
            SET
                override_price = %s,
                strategy_quantity = %s,
                strategy_sellout = %s,
                strategy_handling_time = %s,
                updated_at = %s
            WHERE asin = %s AND user_id = %s
        """, (
            override_price,
            strategy_quantity,
            strategy_sellout,
            strategy_handling_time,
            now_utc,
            asin,
            user_id
        ))

        conn.commit()
        conn.close()

        return jsonify({"status": "success"})

    except Exception as e:
        import traceback
        print("[update_strategy ERROR]")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

__all__ = ["update_brand_title_in_listed_items"]


