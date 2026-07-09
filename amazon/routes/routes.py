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


