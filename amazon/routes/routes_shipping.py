# =====================================================
# ファイル名: amazon/routes_shipping.py
# 目的：送料表作成-保存
# =====================================================

from flask import Blueprint, request, jsonify, session
from amazon.adapters.shipping_rates import update_shipping_rates_bulk
from amazon.adapters.shipping_rates import seed_shipping_rates
from amazon.db import get_conn
import sqlite3 
import os 

shipping_bp = Blueprint("shipping_bp", __name__, url_prefix="/api")

# --- ▼ SECTION 01: marketplace_code → marketplace_id 変換 ▼ ---
def resolve_marketplace_id(marketplace_code: str):
    import sqlite3
    import os

    db_path = os.path.join("db", "a_marketplaces_master.db")
    
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    # cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    # cur.execute(
    #     "SELECT * FROM marketplaces_master"
    # )

    cur.execute(
        "SELECT marketplace_id FROM marketplaces_master WHERE country_code = %s",
        (marketplace_code.upper(),)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Unknown marketplace_code: {marketplace_code}")

    return row[0]

# --- ▼ SECTION 02: 送料設定 ロード（表示専用） ▼ ---
@shipping_bp.route("/shipping-rates/load", methods=["GET"])
def load_shipping_rates():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    marketplace_code = request.args.get("marketplace_id")
    if not marketplace_code:
        return jsonify({"status": "error"}), 400

    marketplace_id = resolve_marketplace_id(marketplace_code)

    # # ① seed（何回呼ばれてもOK）
    # seed_shipping_rates(user_id, marketplace_id)

    # ② rows を取得
    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) 
        FROM shipping_rates
        WHERE user_id = ?
          AND marketplace_id = ?
    """, (user_id, marketplace_id))

    count = cur.fetchone()[0]
    mode = "edit" if count > 0 else "new"

    cur.execute("""
        SELECT
            weight_from_g,
            weight_to_g,
            carrier_1_price,
            carrier_2_price,
            carrier_3_price
        FROM shipping_rates
        WHERE user_id = ?
          AND marketplace_id = ?
        ORDER BY weight_from_g
    """, (user_id, marketplace_id))

    rows = [
        {
            "weight_from_g": r[0],
            "weight_to_g": r[1],
            "carrier_1_price": r[2],
            "carrier_2_price": r[3],
            "carrier_3_price": r[4],
        }
        for r in cur.fetchall()
    ]
    conn.close()

    return jsonify({
        "status": "success",
        "mode": mode,
        "rows": rows
    })

# --- ▼ SECTION 03: 送料設定 保存API ▼ ---
@shipping_bp.route("/shipping-rates/save", methods=["POST"])
def save_shipping_rates():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error"}), 400

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    marketplace_code = data.get("marketplace_id") 
    rows = data.get("rows")

    if not marketplace_code or not isinstance(rows, list):
        return jsonify({"status": "error"}), 400

    marketplace_id = resolve_marketplace_id(marketplace_code)

    update_shipping_rates_bulk(
        user_id=user_id,
        marketplace_id=marketplace_id,
        rows=rows
    )

    return jsonify({"status": "success"})

# --- ▼ SECTION 04: 送料設定 新規作成（seed専用） ▼ ---
@shipping_bp.route("/shipping-rates/init", methods=["POST"])
def init_shipping_rates():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    marketplace_code = data.get("marketplace_id")
    if not marketplace_code:
        return jsonify({"status": "error"}), 400

    marketplace_id = resolve_marketplace_id(marketplace_code)

    copy_from_marketplace_code = data.get("copy_from_marketplace_id", "") 
    copy_from_marketplace_id = resolve_marketplace_id(copy_from_marketplace_code) if copy_from_marketplace_code else None

    # ★ 新規作成（UNIQUE前提で安全）
    seed_shipping_rates(
        user_id,
        marketplace_id,
        copy_from_marketplace_id=copy_from_marketplace_id
    ) 

    return jsonify({"status": "success"})

# --- ▼ SECTION 05: コピー可能 marketplace 一覧取得 ▼ ---
@shipping_bp.route("/shipping-rates/copy-source-list", methods=["GET"])
def get_shipping_rate_copy_source_list():

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT marketplace_id
        FROM shipping_rates
        WHERE user_id = ?
        ORDER BY marketplace_id
    """, (user_id,))

    marketplace_rows = [r[0] for r in cur.fetchall()]

    conn.close()

    result_rows = []

    for marketplace_id in marketplace_rows:

        try:
            db_path = os.path.join("db", "a_marketplaces_master.db")

            master_conn = get_conn("a_marketplaces_master.db")

            master_cur = master_conn.cursor()

            master_cur.execute("""
                SELECT country_code
                FROM marketplaces_master
                WHERE marketplace_id = ?
            """, (marketplace_id,))

            row = master_cur.fetchone()

            master_conn.close()

            if row:
                result_rows.append({
                    "marketplace_id": marketplace_id,
                    "country_code": row[0]
                })

        except Exception:
            pass

    return jsonify({
        "status": "success",
        "marketplace_ids": result_rows
    })