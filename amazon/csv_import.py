# =====================================================
# ファイル名: amazon/csv_import.py
# 目的：CSVファイルからASIN/SKU読込み・仕分け・DB登録を行う処理
# =====================================================

# =====================================================
# csv_import.py の責務
# -----------------------------------------------------
# ・csv_import は listed_items のテーブルを作らない
# ・DB構造（CREATE / UNIQUE / INDEX）は db_migrate.py が唯一の正
# ・csv_import は既存DBを前提に、存在確認と INSERT 要求のみを行う
# ・テーブルが存在しない場合は migrate 未実行の異常として扱う
# =====================================================

import io
import os
import re
import csv
import glob
import random
import sqlite3
import traceback

from datetime import datetime, timedelta
from collections import Counter
from threading import Thread
from amazon.db import get_conn, DB_MODE

from flask import Blueprint, request, jsonify, session, current_app, Response
from werkzeug.utils import secure_filename

from amazon.services.blacklist_service import is_blacklisted, get_blacklist_reason


BASE_DIR = os.path.dirname(__file__)
db_dir = os.path.abspath(os.path.join(BASE_DIR, "../db"))


db_files = {}

csv_import_bp = Blueprint("csv_import", __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- ▼ SECTION 01: CSVアップロード ▼ ---
@csv_import_bp.route("/upload", methods=["POST"])
def upload_csv():
    try:
        if "file" not in request.files:
            return jsonify({"status": "error", "message": "ファイルが見つかりません"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"status": "error", "message": "ファイル名が空です"}), 400

        filename = secure_filename(file.filename)

        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)

        # ✅ ヘッダーチェック
        with open(save_path, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.reader(csvfile)
            headers = next(reader, None)

            if headers is None or len(headers) < 2:
                return jsonify({
                    "status": "error",
                    "message": "CSVのヘッダーが不足しています。ASIN,SKU の2列が必要です。"
                }), 400

            if headers[0].strip().upper() != "ASIN" or headers[1].strip().upper() != "SKU":
                return jsonify({
                    "status": "error",
                    "message": "CSVのフォーマットが不正です。1列目は『ASIN』、2列目は『SKU』にしてください。"
                }), 400

        return jsonify({"status": "success", "filename": filename, "path": save_path})
    except Exception as e:

        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 02: アップロードデータチェック ▼ ---
@csv_import_bp.route("/check", methods=["POST"])
def check_csv():
    try:
        # country_code と file を取得
        country_code = request.form.get("country_code")
        file = request.files.get("file")
        if not file or not country_code:
            return jsonify({"status": "error", "message": "ファイルまたはリージョンが指定されていません"}), 400

        # uploads/ に一時保存
        filename = secure_filename(file.filename)
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)

        # CSV 読み込み
        with open(save_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            asin_list = [row[0].strip() for row in reader if row]

        # DBチェック結果格納用
        ok_asins = []
        listed_asins = []
        blacklist_asins = {}

        db_dir = current_app.config.get("DB_DIR")

        for asin in asin_list:
            reason = get_blacklist_reason(asin, country_code, db_dir)

            if reason:
                blacklist_asins[asin] = reason

         # 出品可能ASIN = 全体 − ブラックリスト − 出品済み
        ok_asins = [
            asin for asin in asin_list
            if asin not in blacklist_asins ]

        # 完全削除
        os.remove(save_path)

        return jsonify({
            "status": "success",
            "total_count": len(asin_list),   # ✅ ASIN件数だけでOK
            "ok": [
                {"asin": asin, "sku": ""}   # SKUは空欄でも良いならこれで
                for asin in asin_list
                if asin not in blacklist_asins and asin not in listed_asins
            ],
            "blacklist": [
                {"asin": a, "reason": r}
                for a, r in blacklist_asins.items()
            ],
            "listed": [
                {"asin": asin, "sku": ""}   # 必要ならDBから拾って埋める
                for asin in listed_asins
            ]
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 03: Pre-Listing登録 ▼ ---
@csv_import_bp.route("/csv_import", methods=["POST"])
def import_csv():
    db_dir = current_app.config.get("DB_DIR")
    try:
        # if "file" not in request.files and request.form.get("mode", "check") == "check":
        mode = request.form.get("mode", "check") 

        if mode == "check" and "file" not in request.files:
            
            return jsonify({"status": "error", "message": "ファイルが見つかりません"}), 400

        # ▼ リージョン取得
        country_code = request.form.get("country_code", "").upper()

        # --- 利用可能リージョン取得（DB） ---
        conn_m = get_conn("a_marketplaces.db")

        cur_m = conn_m.cursor()
        cur_m.execute("SELECT DISTINCT country_code FROM marketplaces")
        valid_regions = [row["country_code"].upper() for row in cur_m.fetchall()]

        cur_m.execute("""                                
            SELECT marketplace_id                  
            FROM marketplaces                 
            WHERE LOWER(country_code) = %s     
            LIMIT 1                             
        """, (country_code.lower(),))          

        row_market = cur_m.fetchone()    
        marketplace_id = row_market["marketplace_id"] if row_market else None

        conn_m.close()

        if country_code not in valid_regions:
            return jsonify({"status": "error", "message": "選択したマーケットプレイスが違います"}), 400

        condition = request.form.get("condition", "NEW001")
        mode = request.form.get("mode", "check")

        if mode == "check":

            listed_asins = [] 
            blacklist_asins = {}   

            # ▼ CSVアップロードして仕分け
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"status": "error", "message": "ファイル名が空です"}), 400

            # ▼ ファイル名チェック（先頭2文字とcountry_code一致）
            filename = secure_filename(file.filename)
            if not filename[:2].upper() == country_code:
                return jsonify({
                    "status": "error",
                    "message": f"リージョンとファイル名が一致しません（リージョン={country_code}, ファイル={filename})"
                }), 400

            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)

            asin_list = []
            with open(save_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f, delimiter=",")
                headers = next(reader, None)

                # ✅ ヘッダーチェック
                if headers is None or len(headers) < 2:
                    return jsonify({
                        "status": "error",
                        "message": "CSVのヘッダーが不足しています。ASIN,SKU の2列が必要です。"
                    }), 400

                if headers[0].strip().upper() != "ASIN" or headers[1].strip().upper() != "SKU":
                    return jsonify({
                        "status": "error",
                        "message": "CSVのフォーマットが不正です。1列目は『ASIN』、2列目は『SKU』にしてください。"
                    }), 400

                # ▼ データ読み込み (ASIN + SKU)
                records = []
                for row in reader:
                    if row and row[0].strip():
                        asin = re.sub(r"[^A-Z0-9]", "", row[0].strip().upper())   
                        sku = re.sub(r"[^\w\-]", "", row[1].strip()) if len(row) > 1 and row[1].strip() else ""
                        records.append({"asin": asin, "sku": sku})
                        asin_list.append(asin)

                # ✅ CSVファイル内ASIN重複チェック 
                from collections import Counter
                asin_counter = Counter([r["asin"] for r in records])
                if any(count > 1 for count in asin_counter.values()):
                    return jsonify({
                        "status": "error",
                        "message": "CSVにASINの重複があります。"
                    }), 400

                # ✅ SKU重複チェック（空白は無視）
                sku_values = [r["sku"] for r in records if r["sku"]]
                sku_counter = Counter(sku_values)
                if any(count > 1 for count in sku_counter.values()):
                    return jsonify({
                        "status": "error",
                        "message": "CSVにSKUの重複があります。"
                    }), 400

            # ▼ ブラックリストチェック
            blacklist_asins = {}

            user_id = session.get("user_id")

            import time  # ここを修正
            t_black = time.time()  # // チェック完了後削除

            conn_bl = get_conn("a_all_blacklist_asin.db")  
            cur_bl = conn_bl.cursor() 

            cur_bl.execute("""  
                SELECT asin
                FROM blacklist_asin
                WHERE user_id = %s
                AND region_marketplace_id = %s
            """, (
                user_id,
                marketplace_id
            ))

            black_asin_set = { 
                str(r["asin"]).strip().upper()
                for r in cur_bl.fetchall()
            }

            conn_bl.close() 

            for rec in records:
                asin = rec["asin"]

                # if is_blacklisted(asin, user_id, country_code, marketplace_id, db_dir):
                if asin in black_asin_set: 
                    blacklist_asins[asin] = "blacklist"

            print(f"[CSV BLACK] {time.time()-t_black:.3f}s")  # // チェック完了後削除   

            # --- ▼ 既登録チェック ▼ ---
            listed_db = os.path.join(db_dir, f"a_{country_code.lower()}_listed_items.db") 

            t_listed = time.time()  # // チェック完了後削除

            if os.path.exists(listed_db):

                if DB_MODE == "sqlite":
                    conn = sqlite3.connect(listed_db, timeout=30)  # DB移行 分岐対応済（SQLite専用）
                    conn.execute("PRAGMA journal_mode=WAL")
                else:
                    conn = get_conn(f"a_{country_code.lower()}_listed_items.db")                    
                cur = conn.cursor()
                for asin in asin_list:
                    cur.execute("SELECT 1 FROM listed_items WHERE asin = %s", (asin,))
                    if cur.fetchone():
                        listed_asins.append(asin)
                conn.close()

                print(f"[CSV LISTED] {time.time()-t_listed:.3f}s")  # // チェック完了後削除

            # ▼ SKU割り振り
            today = datetime.utcnow().strftime("%Y%m%d") 
            for rec in records:
                if not rec["sku"]:
                    rec["sku"] = f"Z_{country_code}_{rec['asin']}_{today}_{condition}"

            # ▼ 出品可能ASIN（仕分け結果）
            ok_asins = [
                asin for asin in asin_list
                if asin not in blacklist_asins and asin not in listed_asins
            ]

            os.remove(save_path)
            conn.close()

            return jsonify({
                "status": "success",
                "ok": [
                    {"asin": rec["asin"], "sku": rec["sku"]}
                    for rec in records
                    if rec["asin"] in ok_asins
                ],
                "blacklist": [
                    {"asin": a, "sku": "", "reason": r}
                    for a, r in blacklist_asins.items()
                ],
                
                "listed": [
                    {"asin": asin, "sku": ""}
                    for asin in listed_asins                    
                ],   # ← 空で返す（UI崩さないため）
                "total_count": len(records),
            })

        elif mode == "commit":

            # ▼ リージョンを再取得してDBを開く（重要）
            country_code = request.form.get("country_code", "").upper()
            # --- 利用可能リージョン取得（DB） ---
            conn_m = get_conn("a_marketplaces.db")
            cur_m = conn_m.cursor()
            cur_m.execute("SELECT DISTINCT country_code FROM marketplaces")
            valid_regions = [row["country_code"].upper() for row in cur_m.fetchall()]
            conn_m.close()

            if country_code not in valid_regions:
                return jsonify({"status": "error", "message": "選択したマーケットプレイスが違います"}), 400

            listed_db = os.path.join(db_dir, f"a_{country_code.lower()}_listed_items.db")

            if DB_MODE == "sqlite":
                conn = sqlite3.connect(listed_db, timeout=30)  # DB移行 分岐対応済（SQLite専用）
                conn.execute("PRAGMA journal_mode=WAL")
            else:
                conn = get_conn(f"a_{country_code.lower()}_listed_items.db")

            cur = conn.cursor()

            # --- ▼ marketplace_id 取得 ---
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"status": "error", "message": "not logged in"}), 401

            # REGION marketplace_id（UIで選択された region）
            conn_m = get_conn("a_marketplaces.db")
            cur_m = conn_m.cursor()
            cur_m.execute("""
                SELECT marketplace_id
                FROM marketplaces
                WHERE user_id = %s AND country_code = %s
            """, (user_id, country_code))
            row = cur_m.fetchone()
            if not row:
                conn_m.close()
                return jsonify({"status": "error", "message": "region marketplace not found"}), 400
            region_marketplace_id = row["marketplace_id"]

            # HOME marketplace_id（home_flag = 1）
            cur_m.execute("""
                SELECT marketplace_id
                FROM marketplaces
                WHERE user_id = %s AND home_flag = 1
            """, (user_id,))
            row = cur_m.fetchone()
            conn_m.close()
            if not row:
                return jsonify({"status": "error", "message": "home marketplace not found"}), 400
            home_marketplace_id = row["marketplace_id"]


            # ▼ OKタブのASINとSKUを受け取る
            asins = request.form.getlist("asins[]")
            skus = request.form.getlist("skus[]")  
            today = datetime.utcnow().strftime("%Y%m%d") 

            now_utc = datetime.utcnow().isoformat()

            for asin, sku in zip(asins, skus):
                if not sku:  
                    sku = f"Z_{country_code}_{asin}_{today}_{condition}"

                # ▼ listed_items のカラム順に完全一致 
                cur.execute("""
                    INSERT INTO listed_items ( 
                        user_id,
                        asin,
                        sku,
                        home_marketplace_id,
                        region_marketplace_id,
                        image_url,

                        first_try_count,
                        ttl_stop_status,

                        home_title,
                        home_brand,
                        home_manufacturer,

                        length_cm,
                        width_cm,
                        height_cm,
                        actual_weight_kg,
                        volumetric_weight_kg,
                        billable_weight_kg,

                        override_weight_class,

                        home_price,
                        region_price,
                        override_price,
                        override_tariff_rate,

                        region_brand,
                        region_manufacturer,

                        strategy_quantity,
                        strategy_sellout,
                        strategy_handling_time,

                        status,
                        information_status,
                        listing_status,

                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,
                        10,%s,
                        %s,%s,%s,
                        %s,%s,%s,%s,%s,%s,
                        %s,
                        %s,%s,%s,%s,
                        %s,%s,
                        %s,%s,%s,
                        %s,%s,%s,
                        %s,%s
                    )
                """, (
                    session.get("user_id"),      # user_id　　　　　　　　　6
                    asin,                        # asin
                    sku,                         # sku
                    home_marketplace_id,         # home_marketplace_id
                    region_marketplace_id,       # region_marketplace_id
                    "",                          # image_url

                    #None,                       # first_try_count         2   
                    None,                        # ttl_stop_status  

                    "",                          # home_title              3
                    "",                          # home_brand
                    "",                          # home_manufacturer

                    None,                        # length_cm               6
                    None,                        # width_cm
                    None,                        # height_cm
                    None,                        # actual_weight_kg
                    None,                        # volumetric_weight_kg
                    None,                        # billable_weight_kg

                    None,                        # override_weight_class   1

                    None,                        # home_price              4
                    None,                        # region_price
                    None,                        # override_price
                    None,                        # override_tariff_rate

                    "",                          # region_brand            2
                    "",                          # region_manufacturer

                    1,                           # strategy_quantity       3
                    0,                           # strategy_sellout
                    6,                           # strategy_handling_time

                    "pre",                       # status                  3
                    "",                          # information_status                    
                    "",                          # listing_status

                    now_utc,                     # created_at              2
                    now_utc,                     # updated_at                 
                ))

                # CSV取り込み時点で cache 骨格を同時に作成
                insert_cache_record_from_csv(
                    db_dir,
                    asin,
                    home_marketplace_id,
                    region_marketplace_id,
                )              

            conn.commit()
            conn.close()

            app = current_app._get_current_object()             

            return jsonify({"status": "success", "count": len(asins)})

    except Exception as e:
        import traceback
        print("=== CSV IMPORT ERROR ===")
        traceback.print_exc()
        print("========================")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 04: CacheDB登録 ▼ ---
def insert_cache_record_from_csv(db_dir: str, asin: str, home_marketplace_id: str, region_marketplace_id: str):
    # --- catalog_cache ---
    catalog_db = os.path.join(db_dir, "a_catalog_cache.db")
    conn_c = get_conn("a_catalog_cache.db")

    cur_c = conn_c.cursor()
    
    try:
        cur_c.execute("""
            INSERT INTO catalog_cache (
                asin,
                home_marketplace_id,
                region_marketplace_id,
                h_catalog_ttl_at,
                r_catalog_ttl_at
            )
            VALUES (%s, %s, %s, %s, %s)

            ON CONFLICT (asin, home_marketplace_id)
            DO UPDATE SET
                region_marketplace_id = EXCLUDED.region_marketplace_id,
                h_catalog_ttl_at = EXCLUDED.h_catalog_ttl_at,
                r_catalog_ttl_at = EXCLUDED.r_catalog_ttl_at
        """, (
            asin,
            home_marketplace_id,
            region_marketplace_id,
            datetime.utcnow().isoformat(),
            datetime.utcnow().isoformat(), 
        ))
        conn_c.commit()
    finally:
        conn_c.close()

    # --- pricing_cache ---
    pricing_db = os.path.join(db_dir, "a_pricing_cache.db")
    conn_p = get_conn("a_pricing_cache.db")
    cur_p = conn_p.cursor()
    try:
        now = datetime.utcnow()
        offset = timedelta(seconds=random.randint(0, 300))
        cur_p.execute("""
            INSERT INTO pricing_cache (
                asin,
                home_marketplace_id,
                region_marketplace_id,
                h_pricing_ttl_at,
                r_pricing_ttl_at
            )
            VALUES (%s, %s, %s, %s, %s)

            ON CONFLICT (asin, home_marketplace_id)
            DO UPDATE SET
                region_marketplace_id = EXCLUDED.region_marketplace_id,
                h_pricing_ttl_at = EXCLUDED.h_pricing_ttl_at,
                r_pricing_ttl_at = EXCLUDED.r_pricing_ttl_at
        """, (
            asin,
            home_marketplace_id,
            region_marketplace_id,
            (now + offset).isoformat(),
            (now + offset).isoformat(),
        ))
        conn_p.commit()
    finally:
        conn_p.close()

# --- ▼ SECTION 05: CSV Export ▼ ---
@csv_import_bp.route("/export_listed_csv", methods=["GET"])
def export_listed_csv():

    db_dir = current_app.config.get("DB_DIR")

    country_code = request.args.get("country_code")
    if not country_code:
        return jsonify({"status": "error", "message": "country_code required"}), 400

    country_code = country_code.lower() 

    db_file = os.path.join(db_dir, f"a_{country_code}_listed_items.db") 

    conn = get_conn(f"a_{country_code}_listed_items.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT asin, sku, status
        FROM listed_items
    """)

    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ASIN", "SKU", "STATUS"])
    writer.writerows(rows)

    output.seek(0)

    # --- ファイル名生成 ---
    country_code = request.args.get("country_code", "XX")
    now_str = datetime.utcnow().strftime("%Y%m%d%H%M")
    filename = f"{country_code}_listed_asin_{now_str}.csv"

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

