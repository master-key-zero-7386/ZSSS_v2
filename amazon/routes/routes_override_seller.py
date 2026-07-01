# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon\routes\routes_override_seller.py
# 目的: 別途送料誤判定セラー管理
# ==========================================================

from flask import Blueprint, request, jsonify
from amazon.db import get_conn

# --- Blueprint ---
override_seller_bp = Blueprint("override_seller", __name__)


# --- ▼ SECTION 01 : 一覧取得 ▼ ---
@override_seller_bp.route("/list", methods=["POST"])
def get_override_seller_list():

    data = request.get_json() or {}
    country_code = data.get("country_code")

    print("【OVERRIDE_LIST】", data, country_code)  # チェック完了後削除

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces_master
        WHERE LOWER(country_code)=LOWER(%s)
        LIMIT 1
    """, (country_code,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Marketplaceが見つかりません"}), 400

    marketplace_id = row["marketplace_id"]
    conn.close()

    conn = get_conn("a_shipping_override_master.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM shipping_override_master
        WHERE marketplace_id=%s
        ORDER BY seller_name
    """, (marketplace_id,))

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({"data": rows})


# --- ▼ SECTION 02 : 新規追加 ▼ ---
@override_seller_bp.route("/insert", methods=["POST"])
def insert_override_seller():

    data = request.get_json() or {}

    country_code = data.get("country_code")
    seller_id = (data.get("seller_id") or "").strip()
    seller_name = (data.get("seller_name") or "").strip()
    shipping_amount = data.get("shipping_amount")
    remarks = (data.get("remarks") or "").strip()

    if not seller_id:
        return jsonify({"status": "error", "message": "Seller IDを入力してください"}), 400

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces_master
        WHERE LOWER(country_code)=LOWER(%s)
        LIMIT 1
    """, (country_code,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Marketplaceが見つかりません"}), 400

    marketplace_id = row["marketplace_id"]
    conn.close()

    conn = get_conn("a_shipping_override_master.db")
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO shipping_override_master
        (marketplace_id, seller_id, seller_name, shipping_amount, remarks)
        VALUES (%s,%s,%s,%s,%s)
    """, (
        marketplace_id,
        seller_id,
        seller_name,
        shipping_amount,
        remarks
    ))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# --- ▼ SECTION 03 : 更新 ▼ ---
@override_seller_bp.route("/update", methods=["POST"])
def update_override_seller():

    data = request.get_json() or {}

    country_code = data.get("country_code")
    seller_id = data.get("seller_id")
    seller_name = data.get("seller_name")
    shipping_amount = data.get("shipping_amount")
    remarks = data.get("remarks")

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces_master
        WHERE LOWER(country_code)=LOWER(%s)
        LIMIT 1
    """, (country_code,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Marketplaceが見つかりません"}), 400

    marketplace_id = row["marketplace_id"]
    conn.close()

    conn = get_conn("a_shipping_override_master.db")
    cur = conn.cursor()

    cur.execute("""
        UPDATE shipping_override_master
        SET seller_name=%s,
            shipping_amount=%s,
            remarks=%s
        WHERE marketplace_id=%s
        AND seller_id=%s
    """, (
        seller_name,
        shipping_amount,
        remarks,
        marketplace_id,
        seller_id
    ))

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# --- ▼ SECTION 04 : 削除 ▼ ---
@override_seller_bp.route("/delete", methods=["POST"])
def delete_override_seller():

    data = request.get_json() or {}

    country_code = data.get("country_code")
    seller_id = data.get("seller_id")

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces_master
        WHERE LOWER(country_code)=LOWER(%s)
        LIMIT 1
    """, (country_code,))

    row = cur.fetchone()

    if not row:
        return jsonify({"status":"error","message":"marketplace not found"}), 400

    marketplace_id = row["marketplace_id"]

    conn = get_conn("a_shipping_override_master.db")
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM shipping_override_master
        WHERE marketplace_id=%s
        AND seller_id=%s
    """, (
        marketplace_id,
        seller_id
    ))

    conn.commit()
    conn.close()

    return jsonify({"status":"ok"})