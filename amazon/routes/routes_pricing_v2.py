# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/routes_pricing_v2.py
# 目的: pricing用統括ファイル
# ==========================================================

import os
import sqlite3
import json
from datetime import datetime
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from amazon.core.fx_rate import get_exchange_rate

from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.adapters.pricing_adapter_home import PricingAdapterHome
from amazon.adapters.pricing_adapter_region import PricingAdapterRegion

from amazon.adapters.pricing_normalized_adapter import NormalizedPricingAdapter
from amazon.adapters.listed_items_update_adapter import ListedItemsUpdate
from amazon.db import get_conn
from amazon.adapters.pricing_rules_adapter import PricingRulesAdapter
from amazon.shipping_calc import shipping_calc, calc_min_shipping_fee
from amazon.core.price_calculator import calculate_listing_price
from amazon.core.pricing_strategy import decide_listing_price
from amazon.core.fx_rate import get_exchange_rate
from amazon.adapters.pricing_normalized_adapter import NormalizedPricingAdapter
from amazon.adapters.listings_items import put_listings_item
from amazon.services.listing_submit_service import delete_listings_item
from amazon.guard.guard_429 import is_blocked 
from amazon.routes.routes_blacklist import _get_blacklist_db


DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "db")
pricing_v2_bp = Blueprint("pricing_v2_bp", __name__)

# --- ▼ SECTION 01: blacklist取得（From：routes_pricing_v2.py） ▼ ---
def get_brand_blacklist(user_id, country_code):
    import sqlite3
    db_name = _get_blacklist_db(country_code, "brand")

    conn = get_conn(db_name)
    cur = conn.cursor()

    cur.execute("SELECT brand FROM blacklist_brand WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()

    conn.close()

    return [r[0] for r in rows]

def get_asin_blacklist(user_id, country_code):
    import sqlite3
    db_name = _get_blacklist_db(country_code, "asin")

    conn = get_conn(db_name)
    cur = conn.cursor()

    cur.execute("SELECT asin FROM blacklist_asin WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()

    conn.close()

    return [r[0] for r in rows]

# --- ▼ SECTION 02:HOME Pricing 正規更新 ▼ ---
def update_home_pricing(*, user_id: int, asin: str, country_code: str):
    # print(f"<<<HOME PRICING>>> {(datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')} ENTER user={user_id} asin={asin} country={country_code}")  # チェック用 削除せずコメントアウトで残す
    # ↑↑↑↑ 削除してもOK デバグPrint

    # === 02-01: HOME marketplace_id 確定（listed_items基準） ===
    db_name = f"a_{country_code.lower()}_listed_items.db"
    listed_db = db_name
    conn = get_conn(db_name)    

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT home_marketplace_id
            FROM listed_items
            WHERE user_id = ?
              AND asin = ?
            LIMIT 1
        """, (user_id, asin))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("home_marketplace_id not found in listed_items")

    home_marketplace_id = row["home_marketplace_id"]

    # === 02-02: HOME Pricing raw 取得（API） ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=home_marketplace_id,
    )
    adapter = PricingAdapterHome(parent_adapter=base)
    result = adapter.get_full_pricing_item(asin)
    raw = result.get("raw")

    # === 02-03: NORMALIZE（HOME / 暫定） ===
    normalizer = NormalizedPricingAdapter(parent_adapter=adapter)
    normalized = normalizer.normalize_home_offers(raw)

    # === 02-04: 仕入条件取得 ===
    rules = _get_offer_filter_rules(user_id, "ALL")

    # === 02-05: HOME 原価確定（フィルタ＋最安） ===
    adapter_rules = PricingRulesAdapter(rules)
    result_select = adapter_rules.select_home_cost_offer(normalized)
    min_offer = result_select.get("selected") if result_select else None

    # === 02-06: listed_items 更新（HOME / SELECTED 原価） ===
    if min_offer:
        updater = ListedItemsUpdate(base_dir=DB_DIR)

        price = float(min_offer.get("price_amount") or 0)
        shipping = float(min_offer.get("shipping_amount") or 0)
        points = float(min_offer.get("points_amount") or 0)

        home_price = price + shipping

        # --- ポイント加味 ---
        if rules.get("consider_points") == 1:
            home_price -= points

        updater.update_home_from_pricing_normalized(
            listed_db=listed_db,
            user_id=user_id,
            asin=asin,
            marketplace_id=home_marketplace_id,
            normalized={
                "home_price": home_price
            },
        )

        # 出品再開
        conn = get_conn(listed_db)
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE listed_items
                SET updated_at = ?
                WHERE user_id = ?
                AND asin = ?
            """, (
                datetime.utcnow().isoformat(),
                user_id,
                asin,
            ))
            conn.commit()
        finally:
            conn.close()

    else:
        updater = ListedItemsUpdate(base_dir=DB_DIR)

        updater.update_home_from_pricing_normalized(
            listed_db=listed_db,
            user_id=user_id,
            asin=asin,
            marketplace_id=home_marketplace_id,
            normalized={
                "home_price": None
            },
        )

        # 出品停止
        conn = get_conn(listed_db) 
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE listed_items
                SET updated_at = ?
                WHERE user_id = ?
                AND asin = ?
            """, (
                datetime.utcnow().isoformat(),
                user_id,
                asin,
            ))
            conn.commit()
        finally:
            conn.close()

    update_listing_price(
        user_id=user_id,
        asin=asin,
        country_code=country_code,
    )

    # --- ▼ TTL更新（HOME PRICING） ▼ ---
    conn = get_conn("a_pricing_cache.db") 
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE pricing_cache
            SET h_pricing_ttl_at = ?
            WHERE asin = ?
            AND home_marketplace_id = ?
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
        "debug": result_select,
        "offers": raw.get("payload", {}).get("Offers", []),
    }

# --- ▼ SECTION 03: ALL 手動最新取得（From：listing_all.js） ▼ ---
@pricing_v2_bp.route("/run_refresh_now", methods=["POST"])
def run_refresh_now():

    data = request.get_json()

    asin = data.get("asin")
    country_code = data.get("country_code")
    user_id = session.get("user_id")

    if not asin or not country_code:
        return jsonify({
            "status": "error",
            "message": "asin/country_code required"
        }), 400

    try:

        update_home_pricing(
            user_id=user_id,
            asin=asin,
            country_code=country_code,
        )

        update_region_pricing(
            user_id=user_id,
            asin=asin,
            country_code=country_code,
        )

        return jsonify({
            "status": "ok"
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# --- ▼ SECTION 04: 内部用 仕入条件取得（From：update_home_pricing） ▼ ---
def _get_offer_filter_rules(user_id: int, country_code: str):
    conn = get_conn("a_pricing_settings.db")
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM offer_filter_rules
            WHERE user_id=? AND UPPER(country_code)=UPPER(?)
            LIMIT 1
        """, (user_id, country_code))
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

# --- ▼ SECTION 05:REGION Pricing 正規更新 ▼ ---
def update_region_pricing(*, user_id: int, asin: str, country_code: str, home_price: float = 0):

    # === 05-01: REGION marketplace_id 確定（listed_items基準） ===
    db_name = f"a_{country_code.lower()}_listed_items.db"
    listed_db = db_name
    conn = get_conn(db_name)

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT region_marketplace_id
            FROM listed_items
            WHERE user_id = ?
              AND asin = ?
            LIMIT 1
        """, (user_id, asin))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise RuntimeError("region_marketplace_id not found in listed_items")

    region_marketplace_id = row["region_marketplace_id"]

    # === 05-02: REGION Pricing raw 取得（API） ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=region_marketplace_id,
    )
    adapter = PricingAdapterRegion(parent_adapter=base)
    result = adapter.get_full_pricing_item(asin)
    raw = result.get("raw")

    # === 05-03: NORMALIZE（REGION） ===
    normalizer = NormalizedPricingAdapter(parent_adapter=adapter)
    normalized = normalizer.normalize_region_offers(raw)

    # === 05-04: REGION 競合価格選択 ===
    rules = _get_pricing_master_rules(user_id, country_code)

    # --- 自分ID取得（ここ追加） ---
    conn_acc = get_conn("a_account_master.db")
    conn_acc.row_factory = sqlite3.Row
    cur_acc = conn_acc.cursor()

    cur_acc.execute("""
        SELECT account_seller_id
        FROM account_master
        WHERE user_id = ?
        AND country_code = ?
        LIMIT 1
    """, (user_id, country_code))

    acc = cur_acc.fetchone()
    conn_acc.close()

    my_seller_id = acc["account_seller_id"] if acc else None

    # --- rulesへ渡す ---
    rules["my_seller_id"] = my_seller_id    
    
    adapter_rules = PricingRulesAdapter(rules)
    result_select = adapter_rules.select_region_price_offer(normalized)
    selected = result_select.get("selected") if result_select else None
    region_price = selected.get("price_amount") if selected else None

    # === 05-05: listed_items 更新（REGION競合価格） ===
    updater = ListedItemsUpdate(base_dir=DB_DIR)

    region_shipping_amount = (
        float(selected.get("shipping_amount") or 0)
        if selected else None
    ) 

    updater.update_region_from_pricing_normalized(
        listed_db=listed_db,
        user_id=user_id,
        asin=asin,
        region_marketplace_id=region_marketplace_id,
        normalized={
            "region_price": region_price,
            "region_shipping_amount": region_shipping_amount, 
        },
    )

    update_listing_price(
        user_id=user_id,
        asin=asin,
        country_code=country_code
    )

    # --- ▼ TTL更新（REGION PRICING） ▼ ---
    conn = get_conn("a_pricing_cache.db") 

    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE pricing_cache
            SET r_pricing_ttl_at = ?
            WHERE asin = ?
            AND region_marketplace_id = ?
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
        "debug": result_select,
        "offers": raw.get("payload", {}).get("Offers", []),
    }

# --- ▼ SECTION 06: 内部用 販売条件取得（From：update_region_pricing） ▼ ---
def _get_pricing_master_rules(user_id: int, country_code: str):
        conn = get_conn("a_pricing_settings.db")
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT *
                FROM pricing_master_rules
                WHERE user_id=? AND UPPER(country_code)=UPPER(?)
                LIMIT 1
            """, (user_id, country_code))
            row = cur.fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

# --- ▼ SECTION 07 : 販売条件取得（UI用API） ▼ ---
@pricing_v2_bp.route("/pricing/get_pricing_master_rules", methods=["GET"]) 
def get_pricing_master_rules():

    user_id = request.args.get("user_id")
    country_code = request.args.get("country_code")

    data = _get_pricing_master_rules(user_id, country_code)

    return jsonify({
        "status": "success",
        "data": data
    })

# --- ▼ SECTION 08 : 販売条件更新（UI用API） ▼ ---
@pricing_v2_bp.route("/pricing/update_pricing_master_rules", methods=["POST"])
def update_pricing_master_rules():

    body = request.get_json(force=True) or {}

    user_id = body.get("user_id")
    country_code = body.get("country_code").upper() 

    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()

    # --- ▼ レコードが無ければインサート ▼ ---
    now_utc = datetime.utcnow().isoformat() 

    cur.execute("""
        INSERT INTO pricing_master_rules (user_id, country_code, created_at, updated_at)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM pricing_master_rules
            WHERE LOWER(user_id)=LOWER(?) AND UPPER(country_code)=UPPER(?)
        )
    """, (user_id, country_code, now_utc, now_utc, user_id, country_code))

    now_utc = datetime.utcnow().isoformat()   

    cur.execute("""
    UPDATE pricing_master_rules
        SET
            pricing_competitor_min_rating_percent = ?,
            pricing_competitor_min_rating_count = ?,
            max_competitor_price_ratio = ?,
            max_listing_price_limit = ?,
            discount_rate = ?,
            min_profit_rate = ?,
            max_profit_rate = ?,
            amazon_fee_rate = ?,
            gst_rate = ?,
            customs_duty_rate = ?,
            oversea_remittance_fee_rate = ?,
            fuel_surcharge_rate = ?,
            shipping_outsource_cost = ?,            
            extra_cost = ?,

            default_handling_time = ?,
            updated_at = ?
        WHERE LOWER(user_id)=LOWER(?)
        AND UPPER(country_code)=UPPER(?)
    """, (
        body.get("pricing_competitor_min_rating_percent"),
        body.get("pricing_competitor_min_rating_count"),
        body.get("max_competitor_price_ratio"),
        body.get("max_listing_price_limit"),
        body.get("discount_rate"),
        body.get("min_profit_rate"),
        body.get("max_profit_rate"),
        body.get("amazon_fee_rate"),
        body.get("gst_rate"),
        body.get("customs_duty_rate"),
        body.get("oversea_remittance_fee_rate"),
        body.get("fuel_surcharge_rate"),
        body.get("shipping_outsource_cost"),        
        body.get("extra_cost"),
        body.get("default_handling_time"),
        now_utc,
        user_id,
        country_code
    ))
    conn.commit()
    conn.close()

    data = _get_pricing_master_rules(user_id, country_code)

    return jsonify({
        "status": "success",
        "data": data
    })

# --- ▼ SECTION 09 : 競合条件取得（UI用API） ▼ ---
@pricing_v2_bp.route("/pricing/get_offer_filter_rules", methods=["GET"])
def get_offer_filter_rules():

    user_id = request.args.get("user_id")
    country_code = request.args.get("country_code")

    data = _get_offer_filter_rules(user_id, country_code)

    return jsonify({
        "status": "success",
        "data": data
    })

# --- ▼ SECTION 10 : 競合条件更新（UI用API） ▼ ---
@pricing_v2_bp.route("/pricing/update_offer_filter_rules", methods=["POST"])
def update_offer_filter_rules():

    body = request.get_json(force=True) or {}
    user_id = str(body.get("user_id") or "admin").strip()
    country_code = body.get("country_code").upper() 

    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()

    # --- ▼ レコードが無ければインサート ▼ ---
    cur.execute("""
        INSERT INTO offer_filter_rules (user_id, country_code, created_at, updated_at)
        SELECT ?, ?, datetime('now'), datetime('now')
        WHERE NOT EXISTS (
            SELECT 1 FROM offer_filter_rules
            WHERE LOWER(user_id)=LOWER(?) AND UPPER(country_code)=UPPER(?)
        )
    """, (user_id, country_code, user_id, country_code))

    now_utc = datetime.utcnow().isoformat()   

    # --- ▼ bool → int 正規化 ▼ ---
    exclude_non_home_ship = 1 if body.get("exclude_non_home_ship") else 0
    exclude_future_offer = 1 if body.get("exclude_future_offer") else 0
    consider_points = 1 if body.get("consider_points") else 0
    exclude_non_buybox = 1 if body.get("exclude_non_buybox") else 0

    cur.execute("""
        UPDATE offer_filter_rules
        SET
            min_rating_percent = ?,
            min_rating_count = ?,
            max_handling_days = ?,
            min_stock_qty = ?,
            exclude_non_home_ship = ?,
            exclude_future_offer = ?,
            consider_points = ?,  
            exclude_non_buybox = ?,
            updated_at = ?
        WHERE LOWER(user_id)=LOWER(?)
        AND UPPER(country_code)=UPPER(?)
    """, (
        body.get("min_rating_percent"),
        body.get("min_rating_count"),
        body.get("max_handling_days"),
        body.get("min_stock_qty"),
        exclude_non_home_ship,
        exclude_future_offer,
        consider_points,
        exclude_non_buybox,
        now_utc,
        user_id,
        country_code
    ))

    conn.commit()
    conn.close()

    data = _get_offer_filter_rules(user_id, country_code)

    return jsonify({
        "status": "success",
        "data": data
    })

# --- ▼ SECTION 11: Listing Price 計算（From：FIRST / TTL 共通） ▼ ---
def update_listing_price(*, user_id: int, asin: str, country_code: str):

    # === 11-01: listed_items取得 ===
    db_name = f"a_{country_code.lower()}_listed_items.db" 
    listed_db = db_name

    conn = get_conn(db_name)

    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id,
                sku,
                region_marketplace_id,
                home_price,
                length_cm,
                width_cm,
                height_cm,
                actual_weight_kg,
                status,
                strategy_quantity,
                information_status,
                home_brand,         
                region_brand        
            FROM listed_items
            WHERE user_id = ?
              AND asin = ?
            LIMIT 1
        """, (user_id, asin))
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        # raise RuntimeError("listed_items row not found")
        return 

    region_marketplace_id = row["region_marketplace_id"]
    home_price = row["home_price"]    
    if home_price is None:
        final_price = None
    else:
        home_price = float(home_price)        

    # home_price = float(home_price)

    # === 11-02: tax_mode取得 ===
    conn_mid = get_conn("a_marketplaces_master.db") 
    conn_mid.row_factory = sqlite3.Row
    cur_mid = conn_mid.cursor()

    cur_mid.execute("""
        SELECT tax_mode, currency
        FROM marketplaces_master
        WHERE marketplace_id = ?
        LIMIT 1
    """, (region_marketplace_id,))

    row_mid = cur_mid.fetchone()
    conn_mid.close()

    if not row_mid:
        raise RuntimeError("tax_mode not found")

    tax_mode = row_mid["tax_mode"]
    currency = row_mid["currency"]

    # === 11-03: HOME通貨取得 === 
    conn_home = get_conn("a_marketplaces.db")
    conn_home.row_factory = sqlite3.Row
    cur_home = conn_home.cursor()

    cur_home.execute("""
    SELECT currency
    FROM marketplaces
    WHERE user_id = ?
    AND home_flag = 1
    LIMIT 1
    """, (user_id,))

    home_row = cur_home.fetchone()
    conn_home.close()

    home_currency = home_row["currency"]

    # === 11-04: shipping_config取得 ===
    conn_cfg = get_conn("a_pricing_settings.db")
    cur_cfg = conn_cfg.cursor()

    cur_cfg.execute("""
        SELECT padding_cm, pack_ratio, volumetric_divisor
        FROM shipping_config
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (user_id,))

    cfg = cur_cfg.fetchone()
    conn_cfg.close()

    padding_cm = cfg[0] if cfg else 0
    pack_ratio = cfg[1] if cfg else 1.0
    volum_div = cfg[2] if cfg else 5000

    # === 11-05: shipping計算 ===
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

    calc_result = shipping_calc(normalized, shipping_config)
    

    billable_weight = calc_result["billable_weight_kg_rounded"]

    shipping_fee = calc_min_shipping_fee(
        billable_weight,
        user_id,
        region_marketplace_id
    )

    # === 11-06: pricing_rules取得 ===
    rules = _get_pricing_master_rules(user_id, country_code)

    # === 11-07: FX取得 ===
    exchange_rate = get_exchange_rate(home_currency, currency)

    # === 11-08: 価格計算 ===
    if home_price is None:
        P_min = None
        P_max = None
    else:
        calc_result = calculate_listing_price(
            country_code=country_code,
            exchange_rate=exchange_rate,
            home_price=home_price,
            shipping_fee=shipping_fee,
            amazon_fee_rate=rules["amazon_fee_rate"],
            min_profit_rate=rules["min_profit_rate"],
            max_profit_rate=rules["max_profit_rate"],
            gst_rate=rules["gst_rate"],
            tax_mode=tax_mode,
            customs_duty_rate=rules["customs_duty_rate"],
            oversea_remittance_fee_rate=rules["oversea_remittance_fee_rate"],
            fuel_surcharge_rate=rules["fuel_surcharge_rate"],
            shipping_outsource_cost=rules["shipping_outsource_cost"],        
            extra_cost=rules["extra_cost"],
        )

        P_min = calc_result["P_min"]
        P_max = calc_result["P_max"]

        # --- ▼ min/max 保存（ここに追加） ---
        try:
            conn_li = get_conn(f"a_{country_code.lower()}_listed_items.db")
            cur_li = conn_li.cursor()

            cur_li.execute("""
                UPDATE listed_items
                SET min_price = ?, max_price = ?
                WHERE user_id = ? AND asin = ?
            """, (P_min, P_max, user_id, asin))

            conn_li.commit()
            conn_li.close()
        except Exception:
            pass

    # === 11-08.5: 競合価格取得 ===
    selected_offer = None

    try:
        conn_cache = get_conn("a_pricing_cache.db") 
        conn_cache.row_factory = sqlite3.Row
        cur_cache = conn_cache.cursor()

        cur_cache.execute("""
            SELECT region_offers_json
            FROM pricing_cache
            WHERE asin = ?
                AND region_marketplace_id = ?
            LIMIT 1
        """, (asin, region_marketplace_id))

        row_cache = cur_cache.fetchone()

        conn_cache.close()

        if row_cache and row_cache["region_offers_json"]:

            region_offers_json = json.loads(row_cache["region_offers_json"])
            normalized = NormalizedPricingAdapter.normalize_region_offers(None, region_offers_json)           
            pricing_rules_adapter = PricingRulesAdapter(rules)
            result = pricing_rules_adapter.select_region_price_offer(normalized)

            if not result or not result.get("selected"):
                selected_offer = None
            else:
                selected_offer = result.get("selected")

                # --- ▼ 自分除外（ここ追加） ---
                try:
                    conn_acc = get_conn("a_account_master.db") 
                    conn_acc.row_factory = sqlite3.Row
                    cur_acc = conn_acc.cursor()

                    cur_acc.execute("""
                        SELECT account_seller_id
                        FROM account_master
                        WHERE user_id = ?
                        AND country_code = ?
                        LIMIT 1
                    """, (user_id, country_code))

                    acc = cur_acc.fetchone()
                    conn_acc.close()

                    my_seller_id = acc["account_seller_id"] if acc else None

                    if my_seller_id and selected_offer.get("seller_id") == my_seller_id:
                        selected_offer = None             

                except Exception:
                    selected_offer = None              

    except Exception:
        selected_offer = None

    # --- competitor price ---
    competitor_price = None

    region_price = None  

    if selected_offer:
        # region_price = selected_offer.get("price_amount")
        price_amount = float(selected_offer.get("price_amount") or 0) 
        shipping_amount = float(selected_offer.get("shipping_amount") or 0) 

        region_price = price_amount + shipping_amount  

    # === 11-09: 出品価格決定 ===
    discount_rate = rules.get("discount_rate") or 0   
    
    final_price = decide_listing_price(
        P_min=P_min,
        P_max=P_max,
        competitor_price=region_price,
        competitor_api_enabled=(region_price is not None),
        discount_rate=discount_rate,
    )

    # === 11-11: 上限価格チェック ===
    max_price = rules.get("max_listing_price_limit")

    # --- PREはAPI叩かない（←ここ追加） ---
    is_listed = (row["status"] == "listed")
    
    # --- ▼ ブラック取得 ---
    brand_ng_list = get_brand_blacklist(user_id, country_code)  
    asin_ng_list  = get_asin_blacklist(user_id, country_code)

    # --- ▼ ブランド判定 ---
    brand_list = []

    if "home_brand" in row.keys() and row["home_brand"]:
        brand_list.append(row["home_brand"])

    if "region_brand" in row.keys() and row["region_brand"]:
        brand_list.append(row["region_brand"])

    brand_ng_flag = any(
        bl.lower() in b.lower()
        for b in brand_list
        for bl in brand_ng_list
    )

    # --- ▼ ASIN判定 ---
    asin_ng_flag = asin in asin_ng_list  # ←ここ追加

    # --- ▼ 統合 ---
    brand_ng_flag = brand_ng_flag or asin_ng_flag     

    # print(f"[BLACK CHECK] ASIN:{asin} brand_ng_flag:{brand_ng_flag}")  # Blackチェック用

    # --- ▼ status判定 ---
    status_value = 'INACTIVE' if brand_ng_flag else 'ACTIVE'

    sku = row["sku"]

    if brand_ng_flag:
        status_value = 'INACTIVE'

        if is_listed and row["information_status"] != "INACTIVE":
            res = delete_listings_item(user_id=user_id, country_code=country_code, marketplace_id=region_marketplace_id, seller_sku=sku)

    elif final_price is None or final_price == 0:
        status_value = 'INACTIVE'

        if is_listed and row["information_status"] != "INACTIVE":
            res = delete_listings_item(user_id=user_id, country_code=country_code, marketplace_id=region_marketplace_id, seller_sku=sku)

    elif max_price and final_price and float(final_price) > float(max_price):
        status_value = 'INACTIVE'

        if is_listed and row["information_status"] != "INACTIVE":

            res = delete_listings_item(user_id=user_id, country_code=country_code, marketplace_id=region_marketplace_id, seller_sku=sku)

    # --- ▼ RAW最安競合との差チェック ▼ ---
    elif rules.get("max_competitor_price_ratio") and final_price:

        raw_min_price = None

        try:

            conn_acc = get_conn("a_account_master.db")
            conn_acc.row_factory = sqlite3.Row
            cur_acc = conn_acc.cursor()

            cur_acc.execute("""
                SELECT account_seller_id
                FROM account_master
                WHERE user_id = ?
                AND country_code = ?
                LIMIT 1
            """, (user_id, country_code))

            acc = cur_acc.fetchone()
            conn_acc.close()

            my_seller_id = acc["account_seller_id"] if acc else None

            for offer in normalized:

                # --- 自分除外 ---
                if my_seller_id and offer.get("seller_id") == my_seller_id:
                    continue

                price_amount = float(offer.get("price_amount") or 0)
                shipping_amount = float(offer.get("shipping_amount") or 0)

                total_price = price_amount + shipping_amount

                if total_price <= 0:
                    continue

                if raw_min_price is None or total_price < raw_min_price:
                    raw_min_price = total_price

            if raw_min_price is not None:

                max_allowed_price = raw_min_price * (
                    1 + (float(rules.get("max_competitor_price_ratio")) / 100)
                )

                if float(final_price) > float(max_allowed_price):

                    status_value = 'INACTIVE'  # ここを修正

                    if is_listed and row["information_status"] != "INACTIVE":

                        res = delete_listings_item(
                            user_id=user_id,
                            country_code=country_code,
                            marketplace_id=region_marketplace_id,
                            seller_sku=sku
                        )

        except Exception:
            pass
               
    # === 11-12: DB更新 ===
    conn = get_conn(listed_db)

    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE listed_items
            SET final_price = ?,
                information_status = ?,
                updated_at = ?
            WHERE user_id = ?
            AND asin = ?
        """, (
            final_price,
            status_value,
            datetime.utcnow().isoformat(),
            user_id,
            asin,
        ))
        conn.commit()
    finally:
        conn.close()

    # --- PREはAPI叩かない ---
    if row["status"] != "listed":
        return {
            "status": "ok",
            "final_price": final_price
        }

    # --- ▼ Status INACTIVEはAPI叩かない  ---
    if status_value == 'INACTIVE':
        return {
            "status": "inactive_skip",
            "final_price": final_price
        }

    # --- quantity決定（将来UI対応） ---
    quantity = row["strategy_quantity"]

    sku = row["sku"]

    # --- Listings API送信 ---
    # put_listings_item(  
    response = put_listings_item(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=region_marketplace_id,
        seller_sku=sku,
        asin=asin,
        price=final_price,
        quantity=quantity,
        handling_time=rules["default_handling_time"]
    )

    return {
        "status": "ok",
        "final_price": final_price
    }

# --- ▼ SECTION 11 : HOME通貨取得（UI表示用） ▼ ---
@pricing_v2_bp.route("/pricing/get_home_currency", methods=["GET"])
def get_home_currency():

    user_id = request.args.get("user_id")

    conn = get_conn("a_marketplaces.db")
    
    cur = conn.cursor()

    cur.execute("""
        SELECT currency
        FROM marketplaces
        WHERE user_id = ?
        AND home_flag = 1
        LIMIT 1
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    return jsonify({
        "currency": row["currency"] if row else ""
    })

