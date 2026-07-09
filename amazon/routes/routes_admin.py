# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon\routes\routes_admin.py
# 目的: 管理者用PY
# ======================================================

from flask import Blueprint, request, jsonify, session
import os
from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.admin_settings import save_admin_setting
from flask import current_app
from amazon.db import get_conn
from datetime import datetime
from amazon.core.fx_rate import get_exchange_rate
from amazon.routes.routes_pricing_v2 import update_home_pricing
from amazon.routes.routes_pricing_v2 import update_region_pricing
from amazon.db_migrate import DB_DIR
from amazon.adapters.pricing_adapter_home import PricingAdapterHome, get_retail_seller_ids
from amazon.adapters.pricing_normalized_adapter import NormalizedPricingAdapter
from amazon.routes.routes_pricing_v2 import _get_offer_filter_rules
from amazon.adapters.pricing_rules_adapter import PricingRulesAdapter
from amazon.adapters.pricing_adapter_region import PricingAdapterRegion
from amazon.core.pricing_strategy import decide_listing_price
from amazon.core.price_calculator import (calculate_listing_price, calculate_shipping_result, get_shipping_rate, get_shipping_config, get_pricing_master_rule)
from amazon.constants import BASE_DIR
import json

admin_market_bp = Blueprint("admin_market", __name__) #管理者タブ
admin_api_bp = Blueprint("admin_api", __name__) #管理者2タブ

# ▼▼▼ 管理者タブⅠ ▼▼▼
# --- ▼ SECTIONⅠ 01: 管理者：Marketplace Master 保存（UPDATE） ▼ ---
@admin_api_bp.route("/marketplace_master/update", methods=["POST"])
def update_marketplace_master():
    try:
        now_utc = datetime.utcnow().isoformat()
        # 管理者チェック
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}

        # ★ 主キー（変更不可・WHERE条件）
        marketplace_id = (data.get("marketplace_id") or "").strip()
        if not marketplace_id:
            return jsonify({"status": "error", "message": "marketplace_id 必須"}), 400

        # DB 接続
        conn = get_conn("a_marketplaces_master.db") 
        cur = conn.cursor()

        # UPDATE（marketplace_id を主キーにする）
        cur.execute("""
            UPDATE marketplaces_master
            SET
                country_code = %s,
                display_name = %s,
                currency = %s,
                weight_unit = %s,
                dimension_unit = %s,

                locale = %s,
                override_exchange_rate = %s,
                timezone = %s,
                tax_mode = %s,                

                host = %s,
                spapi_host = %s,

                client_id = %s,
                client_secret = %s,
                access_key = %s,
                secret_key = %s,
                updated_at = %s

            WHERE marketplace_id = %s
        """, (
            data.get("country_code"),
            data.get("display_name"),
            data.get("currency"),
            data.get("weight_unit"),
            data.get("dimension_unit"),

            data.get("locale"),
            data.get("override_exchange_rate"),
            data.get("timezone"),
            data.get("tax_mode"),     

            data.get("host"),
            data.get("spapi_host"),                   

            data.get("client_id"),
            data.get("client_secret"),
            data.get("access_key"),
            data.get("secret_key"),
            now_utc,
            marketplace_id
        ))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback
        traceback.print_exc()  
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 02: 管理者：LWA Credentials 一括更新 ▼ ---
@admin_api_bp.route("/marketplace_master/update_credentials_all", methods=["POST"])
def update_credentials_all():
    try:
        # 管理者チェック
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}
        client_id = (data.get("client_id") or "").strip()
        client_secret = (data.get("client_secret") or "").strip()

        if not client_id or not client_secret:
            return jsonify({"status": "error", "message": "client_id / client_secret 必須"}), 400

        now_utc = datetime.utcnow().isoformat()

        # ① marketplaces_master の全行を一括UPDATE
        conn1 = get_conn("a_marketplaces_master.db")
        cur1 = conn1.cursor()
        cur1.execute("""
            UPDATE marketplaces_master
            SET client_id = %s, client_secret = %s, updated_at = %s
        """, (client_id, client_secret, now_utc))
        conn1.commit()
        conn1.close()

        # ② lwa_credentials_log を1行だけ管理(あれば上書き、無ければ作成)
        conn2 = get_conn("a_lwa_credentials_log.db")
        cur2 = conn2.cursor()

        cur2.execute("SELECT id FROM lwa_credentials_log LIMIT 1")
        existing = cur2.fetchone()

        if existing:
            cur2.execute("""
                UPDATE lwa_credentials_log
                SET client_id = %s, client_secret = %s, updated_at = %s
            """, (client_id, client_secret, now_utc))
        else:
            cur2.execute("""
                INSERT INTO lwa_credentials_log (client_id, client_secret, updated_at)
                VALUES (%s, %s, %s)
            """, (client_id, client_secret, now_utc))

        conn2.commit()
        conn2.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            conn1.rollback()
            conn1.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 03: 管理者：Marketplace Master 新規追加（INSERT） ▼ ---
@admin_api_bp.route("/marketplace_master/insert", methods=["POST"])
def insert_marketplace_master():
    try:
        # 管理者チェック
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}

        # 必須チェック（最低限）
        required = [
            "country_code", "display_name", "marketplace_id",
            "currency", "weight_unit", "dimension_unit",
            "locale","override_exchange_rate", 
            "timezone", "tax_mode",
            "host", "spapi_host"
        ]
        for k in required:
            if not data.get(k):
                return jsonify({"status": "error", "message": f"{k} 必須"}), 400

        # DB 接続
        conn = get_conn("a_marketplaces_master.db") 

        cur = conn.cursor()

        now_utc = datetime.utcnow().isoformat()

        # INSERT
        cur.execute("""
            INSERT INTO marketplaces_master (
                country_code,
                display_name,
                marketplace_id,
                currency,
                weight_unit,
                dimension_unit,

                locale,
                override_exchange_rate,
                timezone,
                tax_mode,

                host,
                spapi_host,                

                client_id,
                client_secret,
                access_key,
                secret_key,

                created_at,
                updated_at

            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data["country_code"],
            data["display_name"],
            data["marketplace_id"],
            data["currency"],
            data["weight_unit"],
            data["dimension_unit"],

            data["locale"],
            data["override_exchange_rate"],
            data["timezone"],
            data["tax_mode"],            

            data["host"],
            data["spapi_host"],

            data.get("client_id"),
            data.get("client_secret"),
            data.get("access_key"),
            data.get("secret_key"),
            now_utc,
            now_utc
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "ok",
            "marketplace_id": data["marketplace_id"]
        })

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 04: 管理者：Marketplace Master 削除（DELETE） ▼ ---
@admin_api_bp.route("/marketplace_master/delete", methods=["POST"])
def delete_marketplace_master():
    try:
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}
        marketplace_id = (data.get("marketplace_id") or "").strip()
        if not marketplace_id:
            return jsonify({"status": "error", "message": "marketplace_id 必須"}), 400

        conn = get_conn("a_marketplaces_master.db") 
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM marketplaces_master WHERE marketplace_id = %s",
            (marketplace_id,)
        )

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 05: 管理者：Amazon Retail 保存（UPDATE） ▼ ---
@admin_api_bp.route("/amazon_retail/update", methods=["POST"])
def update_amazon_retail():
    try:
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}

        # ★ 主キー（変更不可・WHERE条件）
        seller_id = (data.get("seller_id") or "").strip()
        if not seller_id:
            return jsonify({"status": "error", "message": "seller_id 必須"}), 400

        # DB 接続
        conn = get_conn("a_marketplaces_master.db") 
        cur = conn.cursor()

        # UPDATE
        cur.execute("""
            UPDATE amazon_retail_sellers
            SET
                country_code = %s,
                note = %s
            WHERE seller_id = %s
        """, (
            data.get("country_code"),
            data.get("note"),
            seller_id
        ))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 06: 管理者：Amazon Retail 新規追加（INSERT） ▼ ---
@admin_api_bp.route("/amazon_retail/insert", methods=["POST"])
def insert_amazon_retail():
    try:
        # 管理者チェック
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}

        # 必須チェック（最低限）
        required = [
            "country_code", "seller_id"
        ]
        for k in required:
            if not data.get(k):
                return jsonify({"status": "error", "message": f"{k} 必須"}), 400

        # DB 接続
        conn = get_conn("a_marketplaces_master.db") 
        cur = conn.cursor()

        now_utc = datetime.utcnow().isoformat()

        # INSERT
        cur.execute("""
            INSERT INTO amazon_retail_sellers (
                country_code,
                seller_id,
                note
            ) VALUES (%s, %s, %s)
        """, (
            data["country_code"],
            data["seller_id"],
            data.get("note")
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "ok",
            "seller_id": data["seller_id"]
        })

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTIONⅠ 07: 管理者：Amazon Retail 削除（DELETE） ▼ ---
@admin_api_bp.route("/amazon_retail/delete", methods=["POST"])
def delete_amazon_retail():
    try:
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json(force=True) or {}
        seller_id = (data.get("seller_id") or "").strip()
        if not seller_id:
            return jsonify({"status": "error", "message": "seller_id 必須"}), 400

        conn = get_conn("a_marketplaces_master.db") 
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM amazon_retail_sellers WHERE seller_id = %s",
            (seller_id,)
        )

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "message": str(e)}), 500


# ▼▼▼ 管理者タブⅡ ▼▼▼
# --- ▼ SECTIONⅡ 01: 管理者：巡回設定 保存（時間 + LIMIT） ▼ ---
@admin_api_bp.route("/save_bg_scan_settings", methods=["POST"])
def save_bg_scan_settings():
    data = request.get_json() or {}

    interval_min  = data.get("interval_min")
    scan_limit    = data.get("scan_limit")
    ttl_sleep_sec = data.get("ttl_sleep_sec")

    ttl_limit_home_pricing    = data.get("ttl_limit_home_pricing")
    ttl_limit_region_pricing  = data.get("ttl_limit_region_pricing")
    ttl_limit_home_catalog    = data.get("ttl_limit_home_catalog")
    ttl_limit_region_catalog  = data.get("ttl_limit_region_catalog")

    try:
        conn = get_conn("a_bg_scan_settings.db")
        cur = conn.cursor()

        from datetime import datetime
        now = datetime.now().isoformat()

        # --- ▼ id=1の行が無ければ、先に空の行を作る ▼ ---
        cur.execute("""
            INSERT INTO bg_scan_settings (id, interval_min, scan_limit, updated_at)
            SELECT 1, 10, 20, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM bg_scan_settings WHERE id = 1
            )
        """, (now,))

        if interval_min is not None and scan_limit is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET interval_min = %s, scan_limit = %s, updated_at = %s
                WHERE id = 1
            """, (float(interval_min), int(scan_limit), now))

        if ttl_sleep_sec is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET ttl_sleep_sec = %s, updated_at = %s
                WHERE id = 1
            """, (float(ttl_sleep_sec), now))
            
        # ▼ TTL項目別 上限件数を保存
        if ttl_limit_home_pricing is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET ttl_limit_home_pricing = %s, updated_at = %s
                WHERE id = 1
            """, (int(ttl_limit_home_pricing), now))

        if ttl_limit_region_pricing is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET ttl_limit_region_pricing = %s, updated_at = %s
                WHERE id = 1
            """, (int(ttl_limit_region_pricing), now))

        if ttl_limit_home_catalog is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET ttl_limit_home_catalog = %s, updated_at = %s
                WHERE id = 1
            """, (int(ttl_limit_home_catalog), now))

        if ttl_limit_region_catalog is not None:
            cur.execute("""
                UPDATE bg_scan_settings
                SET ttl_limit_region_catalog = %s, updated_at = %s
                WHERE id = 1
            """, (int(ttl_limit_region_catalog), now))            

        conn.commit()
        conn.close()

    except Exception as e:
        return jsonify({"status": "ng", "error": str(e)}), 500

    return jsonify({"status": "ok"})

# --- ▼ SECTIONⅡ 02: 管理者：巡回設定 取得 ▼ ---
@admin_api_bp.route("/get_bg_scan_settings", methods=["GET"])
def get_bg_scan_settings():
    try:
        conn = get_conn("a_bg_scan_settings.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT interval_min, scan_limit, ttl_sleep_sec,
                ttl_limit_home_pricing, ttl_limit_region_pricing,
                ttl_limit_home_catalog, ttl_limit_region_catalog
            FROM bg_scan_settings
            WHERE id = 1
        """)
        row = cur.fetchone()
        conn.close()

        if not row:
            return jsonify({"status": "ng"}), 404

        return jsonify({
            "status": "ok",
            "interval_min": row["interval_min"],
            "scan_limit": row["scan_limit"],
            "ttl_sleep_sec": row["ttl_sleep_sec"],
            "ttl_limit_home_pricing": row["ttl_limit_home_pricing"],
            "ttl_limit_region_pricing": row["ttl_limit_region_pricing"],
            "ttl_limit_home_catalog": row["ttl_limit_home_catalog"],
            "ttl_limit_region_catalog": row["ttl_limit_region_catalog"],            
        })

    except Exception as e:
        return jsonify({"status": "ng", "error": str(e)}), 500

# --- ▼ SECTIONⅡ 03: RAW取得（管理者） ▼ ---
@admin_api_bp.route("/debug/get_raw_by_asin", methods=["GET"])
def get_raw_by_asin():
    try:
        asin = request.args.get("asin")
        country_code = (request.args.get("country_code") or "").lower()
        user_id = request.args.get("user_id") or session.get("user_id")

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        # --- listed_items ID検索用---
        conn_l = get_conn(f"a_{country_code}_listed_items.db") 
        cur_l = conn_l.cursor()

        cur_l.execute("""
            SELECT id
            FROM listed_items
            WHERE asin = %s
            LIMIT 1
        """, (asin,))

        row_l = cur_l.fetchone()
        conn_l.close()

        # --- pricing_cache ID検索用 ---
        conn_p = get_conn("a_pricing_cache.db") 
        cur_p = conn_p.cursor()

        cur_p.execute("""
            SELECT id, home_offers_json, region_offers_json
            FROM pricing_cache
            WHERE asin = %s
            LIMIT 1
        """, (asin,))
        row_p = cur_p.fetchone()
        conn_p.close()

        def safe_json_load(val):
            try:
                return json.loads(val) if val else {}
            except:
                return {}

        home_pricing = safe_json_load(row_p["home_offers_json"]) if row_p else {}
        region_pricing = safe_json_load(row_p["region_offers_json"]) if row_p else {}       

        # --- catalog_cache ID検索用 ---
        conn_c = get_conn("a_catalog_cache.db")
        cur_c = conn_c.cursor()

        cur_c.execute("""
            SELECT id, home_raw_json, region_raw_json
            FROM catalog_cache
            WHERE asin = %s
            LIMIT 1
        """, (asin,))
        row_c = cur_c.fetchone()
        conn_c.close()

        def safe_json_load(val):
            try:
                return json.loads(val) if val else {}
            except:
                return {}

        home_catalog = safe_json_load(row_c["home_raw_json"]) if row_c else {}
        region_catalog = safe_json_load(row_c["region_raw_json"]) if row_c else {}

        return jsonify({
            "id_listed": row_l["id"] if row_l else None,  
            "id_pricing": row_p["id"] if row_p else None,
            "id_catalog": row_c["id"] if row_c else None,
            "home_catalog": home_catalog,
            "region_catalog": region_catalog,
            "home_pricing": home_pricing,
            "region_pricing": region_pricing
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500        

# --- ▼ SECTIONⅡ 04: TTL進行状態 ID管理（管理者） ▼ ---
# --- TTL ID取得 ▼ ---
@admin_api_bp.route("/debug/get_ttl_state", methods=["GET"])
def get_ttl_state():
    try:
        country_code = (request.args.get("country_code") or "").lower()

        conn = get_conn("a_pricing_settings.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT last_id
            FROM ttl_state
            WHERE user_id = %s 
            AND country_code = %s
        """, (session.get("user_id"), country_code.upper()))

        row = cur.fetchone()
        conn.close()

        return jsonify({
            "last_id": row["last_id"] if row else None
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- ▼ SECTIONⅢ 01: 管理者：API チェックツール用 ▼ ---
@admin_api_bp.route("/api_check", methods=["POST"])
def api_check():
    try:
        if not session.get("is_admin"):
            return jsonify({"status": "error", "message": "権限なし"}), 403

        data = request.get_json()
        asin = (data.get("asin") or "").strip().upper()
        country_code = (data.get("country_code") or "").strip().upper()

        if not asin or not country_code:
            return jsonify({"status": "error", "message": "asin / country_code 必須"}), 400

        user_id = session["user_id"]

        # ==========================================================
        # ★ HOME/REGION ロジックを完全スキップさせる設定
        #   → AmazonAdapter を一切変更せず、テストツールだけ安全に動かす
        # ==========================================================
        if country_code == "JP":
            region_arg = None      # JP は HOME → AmazonAdapter の HOME 処理へ
        else:
            region_arg = country_code    # SG / US などはそのまま REGION として扱う

        # AmazonAdapter 生成（本番コードへの影響なし）
        amazon = AmazonAdapter(user_id=user_id, region=region_arg)

        # ==========================================================
        # ★ Catalog API 生データ取得
        # ==========================================================
        response = amazon.real_signed_request(
            method="GET",
            endpoint=f"/catalog/2022-04-01/items/{asin}",
            params={
                "marketplaceIds": amazon.marketplace_id,
                "includedData": ["attributes", "images", "summaries"]
            }
        )

        return jsonify({
            "status": "ok",
            "asin": asin,
            "country_code": country_code,
            "raw": response
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTIONⅢ 02: Marketplace プルダウン取得 ▼ ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "db", "a_marketplaces.db")

@admin_market_bp.route("/get_marketplaces", methods=["GET"])
def get_marketplaces():
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()

    cur.execute("SELECT country_code, display_name FROM marketplaces ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    return jsonify({
        "status": "success",
        "data": [
            {"country_code": r["country_code"], "display_name": r["display_name"]}
            for r in rows
        ]
    })

# ▼▼▼ Pricing設定Ⅲ UI Priceチェック機能Ⅲ ▼▼▼
# --- ▼ SECTIONⅢ 01: HOME Pricing Debug 実行（From：pricing_debug.html） ▼ ---
@admin_api_bp.route("/run_home_pricing_debug", methods=["POST"])
def run_home_pricing_debug():

    data = request.get_json()
    asin = data.get("asin")

    if not asin:
        return jsonify({"status": "error", "message": "ASIN required"})

    user_id = session.get("user_id") 

    conn_home = get_conn("a_marketplaces.db")
    try:
        cur_home = conn_home.cursor()
        cur_home.execute("""
            SELECT country_code
            FROM marketplaces
            WHERE user_id = %s
              AND home_flag = 1
            LIMIT 1
        """, (user_id,))
        home_row = cur_home.fetchone()
    finally:
        conn_home.close()

    if not home_row:
        return jsonify({"status": "error", "message": "HOME marketplace not set"})

    country_code = home_row["country_code"]   

    conn_mid = get_conn("a_marketplaces_master.db")
    try:        
        cur_mid = conn_mid.cursor()
        cur_mid.execute("""
            SELECT marketplace_id
            FROM marketplaces_master
            WHERE UPPER(country_code)=UPPER(%s)
            LIMIT 1
        """, (country_code,))
        row_mid = cur_mid.fetchone()
    finally:
        conn_mid.close()

    if not row_mid:
        return jsonify({"status": "error", "message": "HOME marketplace_id not found"})

    home_marketplace_id = row_mid["marketplace_id"]    

    # === HOME Pricing raw 取得（API） ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=home_marketplace_id,
    )

    adapter = PricingAdapterHome(parent_adapter=base)
    result_api = adapter.get_full_pricing_item(asin)
    raw = result_api.get("raw")

    # === NORMALIZE ===
    normalizer = NormalizedPricingAdapter(parent_adapter=adapter)
    normalized = normalizer.normalize_home_offers(raw)

    # === 条件取得 ===
    rules = _get_offer_filter_rules(user_id, "ALL")

    adapter_rules = PricingRulesAdapter(rules)
    result_select = adapter_rules.select_home_cost_offer(normalized)

    if result_select and result_select.get("selected"):

        result_select["selected"]["total_price"] = (
            float(result_select["selected"].get("price_amount") or 0)
            + float(result_select["selected"].get("shipping_amount") or 0)
            - float(result_select["selected"].get("points_amount") or 0)
            if rules.get("consider_points") == 1 else
            float(result_select["selected"].get("price_amount") or 0)
            + float(result_select["selected"].get("shipping_amount") or 0)
        )  # ここを修正 

    return jsonify({
        "status": "ok",
        "offers": raw.get("payload", {}).get("Offers", []),
        "debug": result_select,
        "self_seller_id": base.seller_id,
        "amazon_seller_ids": get_retail_seller_ids(),
    })

# --- ▼ SECTIONⅢ 02: REGION Pricing Debug（HOME構造に合わせた純デバッグ） ▼ ---
@admin_api_bp.route("/run_region_pricing_debug", methods=["POST"])
def run_region_pricing_debug():

    data = request.get_json()
    asin = data.get("asin")
    home_price = float(data.get("home_price", 0))
    country_code = data.get("country_code")

    if not asin or not country_code:
        return jsonify({"status": "error", "message": "ASIN / country_code required"})

    user_id = session.get("user_id")

    # --- marketplace_id 取得 ---
    conn_mid = get_conn("a_marketplaces_master.db")
    try:
        cur_mid = conn_mid.cursor()
        cur_mid.execute("""
            SELECT marketplace_id, tax_mode
            FROM marketplaces_master
            WHERE UPPER(country_code)=UPPER(%s)
            LIMIT 1
        """, (country_code,))
        row_mid = cur_mid.fetchone()

        tax_mode = row_mid["tax_mode"]

    finally:
        conn_mid.close()

    if not row_mid:
        return jsonify({"status": "error", "message": "marketplace_id not found"})

    region_marketplace_id = row_mid["marketplace_id"]

    # === API取得 ===
    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=region_marketplace_id,
    )

    adapter = PricingAdapterRegion(parent_adapter=base)
    result_api = adapter.get_full_pricing_item(asin)
    raw = result_api.get("raw")

    # === NORMALIZE ===
    normalizer = NormalizedPricingAdapter(parent_adapter=adapter)
    normalized = normalizer.normalize_region_offers(raw)

    # === ルール取得 ===
    rules = get_pricing_master_rule(user_id=user_id, country_code=country_code)

    conn_ps = get_conn("a_pricing_settings.db") 
    cur_ps = conn_ps.cursor()

    cur_ps.execute("""
        SELECT seller_id, shipping_amount
        FROM shipping_override_master
        WHERE marketplace_id = %s
    """, (region_marketplace_id,))

    SHIPPING_OVERRIDE_SET = {
        (r["seller_id"], float(r["shipping_amount"]))
        for r in cur_ps.fetchall()
    }

    conn_ps.close()

    adapter_rules = PricingRulesAdapter(
        rules,
        marketplace_id=region_marketplace_id, 
        shipping_override_set=SHIPPING_OVERRIDE_SET
    )

    result_select = adapter_rules.select_region_price_offer(normalized)    

    if not result_select:
        result_select = {"selected": None}
    if "selected" not in result_select:
        result_select["selected"] = None

    discount_rate = rules.get("discount_rate") or 0

    # --- ▼ 送料算定（正規ルート簡易版）▼ ---
    # === ① listed_items から寸法取得 ===
    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT length_cm, width_cm, height_cm, actual_weight_kg
        FROM listed_items
        WHERE user_id=%s AND asin=%s
        LIMIT 1
    """, (user_id, asin))
    row_dim = cur.fetchone()
    conn.close()

    # === ② shipping_config取得 ===
    cfg = get_shipping_config(user_id) 

    SHIPPING_RATE_ROWS = get_shipping_rate(user_id, region_marketplace_id)    

    padding_cm = cfg["padding_cm"] if cfg else 0
    pack_ratio = cfg["pack_ratio"] if cfg else 1.0
    volum_div = cfg["volumetric_divisor"] if cfg else 5000

    normalized_dim = {
        "length_cm": row_dim["length_cm"] if row_dim else 0,
        "width_cm": row_dim["width_cm"] if row_dim else 0,
        "height_cm": row_dim["height_cm"] if row_dim else 0,
        "actual_weight_kg": row_dim["actual_weight_kg"] if row_dim else 0,
    }

    shipping_config = {
        "volumetric_divisor": volum_div,
        "padding_cm": padding_cm,
        "pack_ratio": pack_ratio,
    }

    # === ③ 請求重量算定 ===
    shipping_result = calculate_shipping_result(  
        normalized_dim,
        shipping_config,
        user_id,
        region_marketplace_id,
        SHIPPING_RATE_ROWS
    )

    weight_result = shipping_result["calc_result"]  

    billable_weight = shipping_result["billable_weight"]  

    shipping_fee = shipping_result["shipping_fee"]    

    # === HOME通貨取得 ===
    conn_home = get_conn("a_marketplaces.db")
    cur_home = conn_home.cursor()

    cur_home.execute("""
    SELECT currency
    FROM marketplaces
    WHERE user_id = %s
    AND home_flag = 1
    LIMIT 1
    """, (user_id,))

    home_row = cur_home.fetchone()
    conn_home.close()

    home_currency = home_row["currency"]

    # === REGION通貨取得 ===
    conn_mid = get_conn("a_marketplaces_master.db")
    cur_mid = conn_mid.cursor()

    cur_mid.execute("""
    SELECT currency
    FROM marketplaces_master
    WHERE marketplace_id = %s
    LIMIT 1
    """, (region_marketplace_id,))

    row_mid = cur_mid.fetchone()
    conn_mid.close()

    currency = row_mid["currency"]    

    # === ⑤ FX取得 ===
    exchange_rate = get_exchange_rate(home_currency, currency)

    # === ⑥ 純計算（price_calculator）===
    if home_price is None:
        P_min = None
        P_max = None
        calc_result = None
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

        # === 根拠計算式 ===    
        bd = calc_result["breakdown"]

        if tax_mode == "FOB":
            bd["cif_formula"] = (
                f'{bd["home_price"]} = '
                f'{bd["home_price"]}'
            )

        elif tax_mode == "CIF":
            bd["cif_formula"] = (
                f'{bd["cif_cost"]} = '
                f'{bd["home_price"]} + '
                f'{bd["intl_shipping"]}'
            )

        elif tax_mode == "CIF_EX":
            bd["cif_formula"] = (
                f'{bd["pre_cost"]} = '
                f'{bd["home_price"]} + '
                f'{bd["intl_shipping"]} + '
                f'{bd["packing"]} + '
                f'{bd["outsource"]}'
            )

        if tax_mode == "FOB":
            duty_base = bd["home_price"]

        elif tax_mode == "CIF":
            duty_base = bd["cif_cost"]

        elif tax_mode == "CIF_EX":
            duty_base = bd["pre_cost"]

        bd["duty_formula"] = (
            f'{bd["duty"]} = '
            f'{duty_base} × {bd["customs_duty_rate"] * 100:.2f}%'
        )

        bd["total_cost_formula"] = (
            f'{calc_result["total_cost"]} = '
            f'{bd["pre_cost"]} + '
            f'{bd["duty"]}'
        ) 

        denom_min = 1 - (bd["amazon_fee_rate"] * (1 + bd["gst_rate"])) - bd["gst_rate"] - bd["profit_min_rate"] - bd["remittance_rate"]
        bd["pmin_formula"] = (
            f'{calc_result["P_min"]} = '
            f'{calc_result["total_cost"]} / {denom_min:.4f}'
        )

        denom_max = 1 - (bd["amazon_fee_rate"] * (1 + bd["gst_rate"])) - bd["gst_rate"] - bd["profit_max_rate"] - bd["remittance_rate"]
        bd["pmax_formula"] = (
            f'{calc_result["P_max"]} = '
            f'{calc_result["total_cost"]} / {denom_max:.4f}'
        )

        bd["denom_formula"] = (
            f'{denom_min:.4f} = '
            f'1 - ({bd["amazon_fee_rate"]:.4f} × (1 + {bd["gst_rate"]:.4f})) '
            f'- {bd["gst_rate"]:.4f} '
            f'- {bd["profit_min_rate"]:.4f} '
            f'- {bd["remittance_rate"]:.4f}'
        )

        bd["denom_explain"] = "1 - (AmazonFee × (1 + GST)) - GST - Profit - Remittance"

        bd["denom_max_formula"] = (
            f'{denom_max:.4f} = '
            f'1 - ({bd["amazon_fee_rate"]:.4f} × (1 + {bd["gst_rate"]:.4f})) '
            f'- {bd["gst_rate"]:.4f} '
            f'- {bd["profit_max_rate"]:.4f} '
            f'- {bd["remittance_rate"]:.4f}'
        )    

        P_min = calc_result["P_min"]
        P_max = calc_result["P_max"]

        # --- ▼ 競合価格利益率計算（Pricing Debug用） ▼ ---
        # competitor_price = result_select.get("selected", {}).get("price_amount") if result_select else None
        selected = result_select.get("selected") if result_select else None

        if not selected:
            competitor_price = None
        else:
            price = float(selected.get("price_amount") or 0)
            shipping = float(selected.get("shipping_amount") or 0)
            points = float(selected.get("points_amount") or 0)

            competitor_price = price + shipping

            if result_select.get("rules", {}).get("consider_points") == 1:
                competitor_price -= points    

        competitor_price = None
        if selected:
            price = float(selected.get("price_amount") or 0)
            shipping = float(selected.get("shipping_amount") or 0)
            points = float(selected.get("points_amount") or 0)

            competitor_price = price + shipping

            if result_select.get("rules", {}).get("consider_points") == 1:
                competitor_price -= points    

        profit_rate_at_competitor = None

        if competitor_price:
            comp = float(competitor_price)

            r = bd["amazon_fee_rate"]
            g = bd["gst_rate"]
            rem = bd["remittance_rate"]
            total_cost = calc_result["total_cost"] / exchange_rate

            profit = comp * (1 - r - rem) - (comp * g) - total_cost

            if comp > 0:
                profit_rate_at_competitor = profit / comp

        calc_result["profit_rate_at_competitor"] = profit_rate_at_competitor

        # === strategy ===
        if P_min is None:
            final_price = None
        else:

            final_price = decide_listing_price(
                P_min=P_min,
                P_max=P_max,
                competitor_price=competitor_price,
                competitor_api_enabled=True,
                discount_rate=discount_rate,
            )    

        if calc_result:
            calc_result["final_price"] = final_price

        if selected:
            result_select["selected"]["effective_price"] = competitor_price
            
        return jsonify({
            "status": "ok",
            "offers": raw.get("payload", {}).get("Offers", []),
            "debug": result_select,
            "pricing_result": calc_result,
            "final_price": final_price,
            "self_seller_id": base.seller_id,
            "amazon_seller_ids": get_retail_seller_ids(),
        })




