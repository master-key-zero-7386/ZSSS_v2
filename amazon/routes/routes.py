# ==============================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------
# ファイル名: amazon\routes\routes.py
# 目的: アカウント設定とマーケットプレイス管理のAPI
# ==============================================

import os
import sys
import csv
import json
import math
import re
import shutil
import codecs
import pandas as pd
import subprocess
import traceback
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect, url_for, jsonify, send_file, make_response, session)
from werkzeug.utils import secure_filename
from send2trash import send2trash
from amazon.constants import BASE_DIR, UPLOAD_FOLDER
from amazon.adapters import AmazonAdapter
from amazon.db import get_conn
from amazon.spapi_client import real_signed_request
from amazon.auth.token_manager import get_access_token
from sp_api.api import Products
from pathlib import Path
from auth.routes_auth import login_required
from amazon.adapters.brand_gate_adapter import BrandGateAdapter
from amazon.utils.brand_gate_store import save_brand_gate_result

DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

TRASH_DIR = os.path.join(BASE_DIR, "tool_trash") 
os.makedirs(TRASH_DIR, exist_ok=True)

amazon_bp = Blueprint("amazon", __name__, url_prefix="/amazon", template_folder="../templates")

# --- ▼ SECTION 01: マーケットプレイスプルダウン（DB display_name取得） 既存箇所修正 ▼ ---
@amazon_bp.route("/get_enabled_country_codes")
@login_required # ログイン情報判定制限
def get_enabled_country_codes():
    try:
        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT
                country_code,
                display_name,
                marketplace_id,
                host,
                spapi_host
            FROM marketplaces
            ORDER BY country_code ASC
        """)  # この行を修正
        rows = cur.fetchall()
        conn.close()

        regions = [
            {
                "code": r[0],
                "name": r[1],              
                "display_name": r[1],      
                "marketplace_id": r[2],    
                "host": r[3],              
                "spapi_host": r[4],        
            }
            for r in rows
        ]

        return jsonify({"status": "success", "regions": regions})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 02: マーケットプレイス一覧取得 ---  
@amazon_bp.route("/get_marketplaces_master", methods=["GET"])        
@login_required                                                      
def get_marketplaces_master():                                                                       
    conn = get_conn("a_marketplaces_master.db")                      
    cur = conn.cursor()                                              

    cur.execute("""                                                  
        SELECT
            id,
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
            spapi_host            
        FROM marketplaces_master
        ORDER BY id
    """)                                                             

    rows = cur.fetchall()                                            
    conn.close()                                                     

    return jsonify([
        {
            "id": r["id"],
            "country_code": r["country_code"],
            "display_name": r["display_name"],
            "marketplace_id": r["marketplace_id"],
            "currency": r["currency"],
            "weight_unit": r["weight_unit"],
            "dimension_unit": r["dimension_unit"],

            "locale": r["locale"],
            "override_exchange_rate": r["override_exchange_rate"],            
            "timezone": r["timezone"],
            "tax_mode": r["tax_mode"],

            "host": r["host"],
            "spapi_host": r["spapi_host"],
        }
        for r in rows
    ])

# --- ▼ SECTION 03: マーケットプレイス一覧取得（MarketplaceDB版） ---
@amazon_bp.route("/get_marketplaces", methods=["GET"])
@login_required # ログイン情報判定制限
def get_marketplaces():
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT
            country_code,
            display_name,
            marketplace_id,
            currency,
            weight_unit,
            dimension_unit,
            host,
            spapi_host,
            locale,
            timezone,
            override_exchange_rate
        FROM marketplaces
        ORDER BY id
    """)

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "country_code": r["country_code"],
            "display_name": r["display_name"],
            "marketplace_id": r["marketplace_id"],
            "currency": r["currency"],
            "weight_unit": r["weight_unit"],
            "dimension_unit": r["dimension_unit"],
            "host": r["host"],
            "spapi_host": r["spapi_host"],
            "locale": r["locale"],
            "timezone": r["timezone"],
            "override_exchange_rate": r["override_exchange_rate"]
        }
        for r in rows
    ])

# --- ▼ SECTION 04: トップ画面 ---
@amazon_bp.route("/")
@login_required # ログイン情報判定制限
def index():
    country_code = request.args.get("country_code", "home").lower()
    tab = request.args.get("tab", "top")

    # last_used を空の dict として渡す（テンプレート用）
    last_used = {}

    # --- ▼ LWA認証情報の期限チェック（adminのみ） ---
    lwa_days_remaining = None
    is_admin = session.get("is_admin", False)

    if is_admin:
        conn = get_conn("a_lwa_credentials_log.db")
        cur = conn.cursor()
        cur.execute("SELECT updated_at FROM lwa_credentials_log LIMIT 1")
        row = cur.fetchone()
        conn.close()

        if row and row["updated_at"]:
            last_updated = datetime.fromisoformat(row["updated_at"])
            days_passed = (datetime.utcnow() - last_updated).days
            lwa_days_remaining = 180 - days_passed

    return render_template(
        "index.html",
        country_code=country_code,
        tab=tab,
        last_used=last_used,
        is_admin=is_admin,
        lwa_days_remaining=lwa_days_remaining
    )

# --- ▼ SECTION 05: Brand Gate Check ▼ ---
@amazon_bp.route("/brand_gate_check", methods=["POST"])
@login_required
def brand_gate_check():

    try:
        data = request.get_json() or {}
        asins = data.get("asins") or []
        country_code = (data.get("country_code") or "").upper()

        user_id = session.get("user_id")

        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT marketplace_id
            FROM marketplaces
            WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
            LIMIT 1
        """, (user_id, country_code))
        r = cur.fetchone()
        conn.close()

        marketplace_id = r["marketplace_id"] if r else None

        result = []

        adapter = BrandGateAdapter(user_id, country_code, marketplace_id)

        for asin in asins:

            # result.append(adapter.check(asin))

            check_result = adapter.check(asin)

            result.append(check_result)

            conn_li = get_conn(f"a_{country_code.lower()}_listed_items.db")

            cur_li = conn_li.cursor()

            cur_li.execute("""
                SELECT region_brand
                FROM listed_items
                WHERE asin = %s
                AND user_id = %s
                LIMIT 1
            """, (asin, user_id))

            row_li = cur_li.fetchone()

            conn_li.close()

            brand = row_li["region_brand"] if row_li and row_li["region_brand"] else "UNKNOWN"

            save_brand_gate_result(
                user_id=user_id,
                marketplace_id=marketplace_id,
                brand=brand,
                status=check_result["status"],
                reason=check_result.get("note"),
                asin=asin
            )

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- ▼ SECTION 05-2: 型番チェックCSV（その他ツール） ▼ ---
# Pre-Listingの商品をブランド名で絞り、保存済みcatalog（home_raw_json）から
# 型番・部品番号・箇条書きの説明を抜き出してCSVで返す。APIは呼ばない。
# ★catalogの「voltage」欄は世界共通データで実物と違うことがあるので使わない。
#   電圧は日本語の説明文の中の言葉（100V／単相など）だけを拾う。
MAKITA_CA_SEARCH_URL = "https://www.makita.ca/index2new.php?event=searchv2&listlang=English&searchkeyword="
MAKITA_CA_WAIT_SEC = 1.0   # サイトに迷惑をかけないよう、1件ごとに間をあける


def _check_makita_ca(model: str) -> str:
    """マキタカナダで型番を検索した結果を返す。
    型番がピッタリ合うと工具ページへ転送される／無いと「No results for」が出る。
    ★「載ってる」＝カナダ版(120V)がある、という意味でしかない。
      日本で仕入れる物が100V版のこともあるので、OKの判定ではない（NGのふるい落とし用）。"""
    import time
    import requests
    try:
        r = requests.get(MAKITA_CA_SEARCH_URL + requests.utils.quote(model), timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            result = f"確認失敗({r.status_code})"
        elif "event=tool" in r.url:
            result = "載ってる"
        elif "No results for" in r.text:
            result = "載ってない"
        else:
            result = "似た型番あり（要確認）"
    except Exception:
        result = "確認失敗"
    time.sleep(MAKITA_CA_WAIT_SEC)
    return result

_VOLT_RE = re.compile(r"(?:AC|DC)?\s?\d{1,3}(?:\.\d)?\s?(?:V|ボルト)(?![A-Za-z])|単相|三相", re.I)


def _attr_values(attrs: dict, key: str) -> list:
    return [str(x.get("value")).strip() for x in (attrs.get(key) or [])
            if isinstance(x, dict) and x.get("value") not in (None, "")]


def _extract_voltage_words(text: str) -> str:
    import unicodedata
    text = unicodedata.normalize("NFKC", text or "")
    found = []
    for m in _VOLT_RE.findall(text):
        w = re.sub(r"\s+", "", m).upper().replace("ボルト", "V")
        if w not in found:
            found.append(w)
    return " / ".join(found)


@amazon_bp.route("/model_number_csv", methods=["GET"])
@login_required
def model_number_csv():
    import io
    user_id = session.get("user_id")
    brand = (request.args.get("brand") or "").strip()
    country_code = (request.args.get("country_code") or "").strip().upper()
    check_makita = request.args.get("check_makita") == "1"
    # 対象：pre＝Pre-Listingだけ／listed＝ALL-Listing（出品済み）だけ／both＝両方
    scope = (request.args.get("scope") or "pre").lower()
    statuses = {"pre": ["pre"], "listed": ["listed"], "both": ["pre", "listed"]}.get(scope, ["pre"])

    if not brand:
        return jsonify({"status": "error", "message": "ブランド名を入れてください"}), 400

    conn = get_conn("a_marketplaces.db")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT marketplace_id
            FROM marketplaces
            WHERE user_id = %s AND UPPER(country_code) = %s
            LIMIT 1
        """, (user_id, country_code))
        r = cur.fetchone()
    finally:
        conn.close()

    if not r:
        return jsonify({"status": "error", "message": "マーケットプレイスが見つかりません"}), 400
    region_marketplace_id = r["marketplace_id"]

    like = f"%{brand}%"
    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT li.asin, li.status, li.home_title, li.home_brand, li.region_brand, cc.home_raw_json
            FROM listed_items li
            LEFT JOIN catalog_cache cc
              ON cc.asin = li.asin AND cc.home_marketplace_id = li.home_marketplace_id
            WHERE li.user_id = %s
              AND li.status = ANY(%s)
              AND li.region_marketplace_id = %s
              AND (li.home_brand ILIKE %s OR li.region_brand ILIKE %s)
            ORDER BY li.status DESC, li.home_brand, li.asin
        """, (user_id, statuses, region_marketplace_id, like, like))
        rows = cur.fetchall()
    finally:
        conn.close()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ASIN", "Pre/ALL", "ブランド", "商品タイトル", "型番", "部品番号",
                "説明文の電圧の言葉", "箇条書きの説明", "マキタカナダ検索リンク", "マキタカナダ結果", "状態"])

    makita_cache = {}   # 同じ型番は1回だけ見に行く

    for row in rows:
        asin = row["asin"]
        brand_name = row["home_brand"] or row["region_brand"] or ""
        title = row["home_title"] or ""
        model = part = bullets = volt = link = ""
        state = "OK"

        raw = row["home_raw_json"]
        if not raw:
            state = "未取得"
        else:
            try:
                j = raw if isinstance(raw, dict) else json.loads(raw)
            except Exception:
                j = {}
                state = "未取得"
            summ = (j.get("summaries") or [{}])[0] or {}
            attrs = j.get("attributes") or {}
            title = title or summ.get("itemName") or ""
            model = (summ.get("modelNumber") or next(iter(_attr_values(attrs, "model_number")), "")).strip()
            part = (summ.get("partNumber") or next(iter(_attr_values(attrs, "part_number")), "")).strip()
            bullet_list = _attr_values(attrs, "bullet_point")
            desc_list = _attr_values(attrs, "product_description")
            bullets = " / ".join(bullet_list)
            volt = _extract_voltage_words(" ".join([title] + bullet_list + desc_list))
            if state == "OK" and not model:
                state = "型番なし"

        is_makita = re.search(r"makita|マキタ", brand_name, re.I)
        mk_result = ""
        if is_makita and model:
            link = MAKITA_CA_SEARCH_URL + model
            if check_makita:
                key = model.upper()
                if key not in makita_cache:
                    makita_cache[key] = _check_makita_ca(model)
                mk_result = makita_cache[key]

        where = "ALL" if row["status"] == "listed" else "Pre"
        w.writerow([asin, where, brand_name, title, model, part, volt, bullets, link, mk_result, state])

    safe_brand = re.sub(r"[^A-Za-z0-9_-]", "_", brand)[:30] or "brand"
    scope_label = {"pre": "Pre", "listed": "ALL", "both": "PreALL"}.get(scope, "Pre")
    filename = f"{country_code}_model_number_{scope_label}_{safe_brand}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    resp = make_response("﻿" + out.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp

# --- ▼ SECTION 06: Brand Gate Brand ▼ ---
@amazon_bp.route("/extract_brand", methods=["POST"])
def extract_brand():
    from amazon.adapters.brand_gate import extract_brand_logic
    return extract_brand_logic()

# --- ▼ SECTION 07: 管理者用：marketplaces_master 編集ページ ---
@amazon_bp.route("/admin/marketplace_master", methods=["GET"])
@login_required # ログイン情報判定制限
def admin_marketplace_master():
    # 後で admin 判定（role=admin）を入れる
    return render_template("admin/marketplace_master.html")


