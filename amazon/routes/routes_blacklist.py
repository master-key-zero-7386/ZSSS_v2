# =====================================================
# ファイル名: amazon/routes_blacklist.py
# 目的：ASINのブラックリストを追加・削除・取得するAPI
# =====================================================

from flask import Blueprint, request, jsonify, session
import sqlite3
import os
import csv
from amazon.db import get_conn
from io import TextIOWrapper
from datetime import datetime
from werkzeug.utils import secure_filename
from datetime import datetime
import threading
from amazon.routes.routes_pricing_v2 import delete_listings_item

blacklist_bp = Blueprint("blacklist_bp", __name__)

# --- ▼ SECTION 01: country_code 正規チェック ▼ ---
def _validate_country_code(country_code: str) -> str:
    if not country_code:
        return None

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "db",
        "a_marketplaces.db"
    )

    conn = get_conn("a_marketplaces.db")

    cur = conn.cursor()
    cur.execute("SELECT LOWER(country_code) FROM marketplaces")
    valid_country_codes = [r[0] for r in cur.fetchall()]
    conn.close()

    country_code = country_code.lower()
    return country_code if country_code in valid_country_codes else None

# --- ▼ SECTION 02: ▼ ---
def _get_blacklist_db(country_code: str, target: str) -> str:

    country_code = (country_code or "").lower()

    if target == "brand":
        filename = f"a_{country_code}_blacklist_brand.db"
    elif target == "asin":
        filename = f"a_{country_code}_blacklist_asin.db"
    else:
        raise ValueError("invalid target")

    return filename 

# --- ▼ SECTION 03: CSV取り込み（ASIN / BRAND 同時） ▼ ---
@blacklist_bp.post("/blacklist/import")
def import_blacklist_csv():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "login required"}), 401

    country_code = request.form.get("country_code")
    if not country_code:
        return jsonify({"status": "error", "message": "country_code required"}), 400
    country_code = country_code.lower()

    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "message": "CSV file required"}), 400

    # --- ▼ CSVリージョンチェック ▼ ---
    filename = secure_filename(file.filename)

    if not filename[:2].upper() == country_code.upper():
        return jsonify({
            "status": "error",
            "message": f"リージョンとファイル名が一致しません（リージョン={country_code.upper()}, ファイル={filename})"
        }), 400

    # CSV読み込み（Excel想定）
    stream = TextIOWrapper(file.stream, encoding="utf-8-sig")
    reader = csv.DictReader(stream)  
    rows = list(reader)
    if len(rows) <= 1:
        return jsonify({"status": "error", "message": "CSV is empty"}), 400

    asin_rows  = []
    brand_rows = []

    # --- CSV解析（A列で振り分け） ---
    for row in rows:
        if not row:
            continue

        type_col = (row.get("type") or "").replace("\u3000", "").strip().upper()
        value_col = (row.get("ASIN/BrandName") or "").strip()
        note_col  = (row.get("note") or "").strip()

        if not value_col:
            continue

        if type_col == "ASIN":
            asin_rows.append({"asin": value_col, "note": note_col})   # ←変換なし
        elif type_col == "BRAND":
            brand_rows.append({"brand": value_col, "note": note_col}) # ←変換なし

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    db_dir = os.path.join(base_dir, "db", "blacklist")
    os.makedirs(db_dir, exist_ok=True)

    result = {
        "asin":  {"before": 0, "import": 0, "after": 0},
        "brand": {"before": 0, "import": 0, "after": 0},
    }

    # --- ASIN DB ---
    if asin_rows:

        asin_db = f"a_{country_code}_blacklist_asin.db"

        conn = get_conn(asin_db) 

        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM blacklist_asin WHERE user_id = %s", (user_id,))

        result["asin"]["before"] = cur.fetchone()[0]

        now_utc = datetime.utcnow().isoformat()

        try:
            for r in asin_rows:
                cur.execute("""
                    INSERT INTO blacklist_asin (user_id, asin, note, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(user_id, asin)
                    DO UPDATE SET
                        note = excluded.note
                """, (user_id, r["asin"], r["note"], now_utc))
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": "ASIN upsert failed", "detail": str(e)}), 500

        cur.execute("SELECT COUNT(*) FROM blacklist_asin WHERE user_id = %s", (user_id,))
        result["asin"]["after"] = cur.fetchone()[0]
        result["asin"]["import"] = result["asin"]["after"] - result["asin"]["before"]
        conn.close()

    # --- BRAND DB ---
    if brand_rows:

        brand_db = f"a_{country_code}_blacklist_brand.db"

        conn = get_conn(brand_db) 

        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM blacklist_brand WHERE user_id = %s", (user_id,))

        result["brand"]["before"] = cur.fetchone()[0]

        now_utc = datetime.utcnow().isoformat()

        try:
            for r in brand_rows:
                cur.execute("""
                    INSERT INTO blacklist_brand (user_id, brand, note, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(user_id, brand)
                    DO UPDATE SET note = excluded.note
                """, (user_id, r["brand"], r["note"], now_utc))
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": "BRAND upsert failed", "detail": str(e)}), 500

        cur.execute("SELECT COUNT(*) FROM blacklist_brand WHERE user_id = %s", (user_id,))
        result["brand"]["after"] = cur.fetchone()[0]
        result["brand"]["import"] = result["brand"]["after"] - result["brand"]["before"]
        conn.close()

    threading.Thread(
        target=apply_blacklist_update,
        args=(user_id, country_code),
        daemon=True
    ).start()


    return jsonify({
        "status": "success",
        "country_code": country_code,
        "asin": result["asin"],
        "brand": result["brand"],
    })

# --- ▼ SECTION 04: API：Brand一覧取得（UI用） ▼ ---
@blacklist_bp.get("/blacklist/brand/<country_code>")
def get_blacklist_brand(country_code):

    user_id = session.get("user_id")
    country_code = (country_code or "").lower()

    if not user_id or not country_code:
        return jsonify({"status": "error", "message": "invalid user or country_code"}), 400

    db_name = _get_blacklist_db(country_code, "brand")

    conn = get_conn(db_name) 

    cur = conn.cursor()  

    try:
        cur.execute("""
            SELECT
                id,
                brand,
                note,
                created_at
            FROM blacklist_brand
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))

        rows = [
            {
                "id": r["id"],  
                "brand": r["brand"],
                "note": r["note"],
                "created_at": r["created_at"]
            }
            for r in cur.fetchall()
        ]

    finally:
        conn.close()

    return jsonify({
        "status": "success",
        "country_code": country_code,
        "count": len(rows),
        "rows": rows
    })

# --- ▼ SECTION 05: API：ASIN一覧取得（UI用） ▼ ---
@blacklist_bp.get("/blacklist/asin/<country_code>")
def get_blacklist(country_code):
    user_id = session.get("user_id")
    country_code = (country_code or "").lower()

    if not user_id or not country_code:
        return jsonify({"status": "error", "message": "invalid user or country_code"}), 400

    db_name = _get_blacklist_db(country_code, "asin")

    conn = get_conn(db_name) 

    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                id,
                asin,
                note,
                created_at
            FROM blacklist_asin
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))

        rows = [
            {
                "id": r["id"], 
                "asin": r["asin"],
                "note": r["note"],
                "created_at": r["created_at"]
            }
            for r in cur.fetchall()
        ]

    finally:
        conn.close()

    return jsonify({
        "status": "success",
        "country_code": country_code,
        "count": len(rows),
        "rows": rows
    })

# --- ▼ SECTION 06: Blacklist更新API ▼ ---
@blacklist_bp.post("/blacklist/update")
def update_blacklist():
    data = request.get_json()

    user_id = session.get("user_id")
    country_code = (data.get("country_code") or "").lower()
    main = data.get("main")
    note = data.get("note")

    if not user_id or not country_code or not main:
        return jsonify({"status": "error"}), 400

    # brand or asin判定（簡易）
    main = (main or "").strip()
    target = (data.get("target") or "").lower()

    if target == "asin":
        table = "blacklist_asin"
        key = "asin"
        db_name = _get_blacklist_db(country_code, "asin")

    elif target == "brand":
        table = "blacklist_brand"
        key = "brand"
        db_name = _get_blacklist_db(country_code, "brand")

    else:
        return jsonify({"status": "error", "message": "invalid target"}), 400

    conn = get_conn(db_name)

    cur = conn.cursor()

    try:
        cur.execute(f"""
            UPDATE {table}
            SET {key} = %s, note = %s  
            WHERE id = %s AND user_id = %s
        """, (main, note, data.get("id"), user_id))

        conn.commit()
        print("ROWCOUNT:", cur.rowcount)  # // チェック完了後削除
        cur.execute(f"SELECT {key} FROM {table} WHERE id = %s", (data.get("id"),))
        print("AFTER UPDATE:", cur.fetchone())

    except Exception as e:
        if "UNIQUE" in str(e) or "duplicate key" in str(e):
            if table == "blacklist_asin":
                msg = "同じASINが既に存在しています"
            else:
                msg = "同じブランドが既に存在しています"

            return jsonify({
                "status": "error",
                "message": msg
            }), 400
        raise

    finally:
        conn.close()

    threading.Thread(
        target=apply_blacklist_update,
        args=(user_id, country_code),
        daemon=True
    ).start()

    return jsonify({"status": "ok"})

# --- ▼ SECTION 07: Blacklist削除API ▼ ---
@blacklist_bp.post("/blacklist/delete")
def delete_blacklist():
    data = request.get_json()

    user_id = session.get("user_id")
    country_code = (data.get("country_code") or "").lower()
    row_id = data.get("id")

    if not user_id or not country_code or not row_id:
        return jsonify({"status": "error"}), 400

    # brand / asin 判定
    # ※どっちでも id で削除できるからDBだけ分岐
    db_name_asin = _get_blacklist_db(country_code, "asin")
    db_name_brand = _get_blacklist_db(country_code, "brand")

    conn = get_conn(db_name_asin) 
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM blacklist_asin
        WHERE id = %s AND user_id = %s
    """, (row_id, user_id))
    conn.commit()
    conn.close()

    conn = get_conn(db_name_brand) 
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM blacklist_brand
        WHERE id = %s AND user_id = %s
    """, (row_id, user_id))
    conn.commit()
    conn.close()

    threading.Thread(
        target=apply_blacklist_update,
        args=(user_id, country_code),
        daemon=True
    ).start()

    return jsonify({"status": "ok"})

# --- ▼ SECTION 08: BlacklistCSV出力 ▼ ---
@blacklist_bp.get("/blacklist/export/<country_code>")
def export_blacklist(country_code):

    user_id = session.get("user_id")
    country_code = (country_code or "").lower()

    if not user_id or not country_code:
        return "error", 400

    db_asin = _get_blacklist_db(country_code, "asin")
    db_brand = _get_blacklist_db(country_code, "brand")

    import csv
    from io import StringIO
    from flask import Response

    output = StringIO()
    output.write('\ufeff')  
    writer = csv.writer(output)

    # ヘッダー
    writer.writerow(["type", "ASIN/BrandName", "note"])

    # --- BRAND ---
    conn = get_conn(db_brand) 
    
    cur = conn.cursor()

    cur.execute("""
        SELECT brand, note FROM blacklist_brand
        WHERE user_id = %s
    """, (user_id,))

    for r in cur.fetchall():
        writer.writerow(["BRAND", r["brand"], r["note"]])

    conn.close()

    # --- ASIN ---
    conn = get_conn(db_asin) 
    
    cur = conn.cursor()

    cur.execute("""
        SELECT asin, note FROM blacklist_asin
        WHERE user_id = %s
    """, (user_id,))

    for r in cur.fetchall():
        writer.writerow(["ASIN", r["asin"], r["note"]])

    conn.close()

    output.seek(0)

    filename = f"{country_code}_blacklist_output.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment;filename={filename}"
        }
    )

# --- ▼ SECTION 09: ASIN/Brand単体追加  ▼ ---
@blacklist_bp.post("/blacklist/add")
def add_blacklist():
    from datetime import datetime

    data = request.get_json()

    user_id = session.get("user_id")
    country_code = (data.get("country_code") or "").lower()
    main = (data.get("main") or "").strip()
    note = data.get("note")
    target = (data.get("target") or "").lower()  # ←ここ重要

    if not user_id or not country_code or not main or not target:
        return jsonify({"status": "error"}), 400

    # --- ▼ UIタブと完全一致 ▼ ---
    if target == "asin":
        table = "blacklist_asin"
        key = "asin"
        db_name = _get_blacklist_db(country_code, "asin")
    elif target == "brand":
        table = "blacklist_brand"
        key = "brand"
        db_name = _get_blacklist_db(country_code, "brand")
    else:
        return jsonify({"status": "error", "message": "invalid target"}), 400

    conn = get_conn(db_name) 
    cur = conn.cursor()

    try:
        cur.execute(f"""
            INSERT INTO {table} (user_id, {key}, note, created_at)
            VALUES (%s, %s, %s, %s)
        """, (user_id, main, note, datetime.utcnow().isoformat()))

        conn.commit()

    except Exception as e:
        if "UNIQUE" in str(e) or "duplicate key" in str(e):
            return jsonify({
                "status": "error",
                "message": "既に存在しています"
            }), 400
        raise

    finally:
        conn.close()

    threading.Thread(
        target=apply_blacklist_update,
        args=(user_id, country_code),
        daemon=True
    ).start()

    return jsonify({"status": "ok"})

# --- ▼ SECTION 10: ブラックリスト即時反映 ▼ ---
def apply_blacklist_update(user_id, country_code):

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "db",
        f"a_{country_code}_listed_items.db"
    )

    conn = sqlite3.connect(db_path, timeout=10) # 一旦保留
    conn.execute("PRAGMA journal_mode=WAL;") # 一旦保留
    conn.row_factory = sqlite3.Row # 一旦保留
    cur = conn.cursor()

    # --- ブランドブラック取得 ---
    brand_db = _get_blacklist_db(country_code, "brand")
    brand_ng_list = []

    # if os.path.exists(brand_db):
    conn_b = get_conn(brand_db)
    cur_b = conn_b.cursor()
    cur_b.execute("SELECT brand FROM blacklist_brand WHERE user_id = %s", (user_id,))
    brand_ng_list = [r[0].strip().lower() for r in cur_b.fetchall()]
    conn_b.close()

    # --- ASINブラック取得 ---
    asin_db = _get_blacklist_db(country_code, "asin")
    asin_ng_list = []

    # if os.path.exists(asin_db):
    conn_a = get_conn(asin_db) 
    cur_a = conn_a.cursor()
    cur_a.execute("SELECT asin FROM blacklist_asin WHERE user_id = %s", (user_id,))
    asin_ng_list = [r[0] for r in cur_a.fetchall()]
    conn_a.close()

    # --- 全件取得 ---
    cur.execute("SELECT * FROM listed_items WHERE user_id = %s", (user_id,))
    rows = cur.fetchall()

    for row in rows:

        asin = row["asin"]

        # --- ASINチェック ---
        asin_ng = asin in asin_ng_list

        # --- ブランドチェック ---
        brand_list = []

        if "home_brand" in row.keys() and row["home_brand"]:
            brand_list.append(row["home_brand"].strip().lower())

        if "region_brand" in row.keys() and row["region_brand"]:
            brand_list.append(row["region_brand"].strip().lower())

        brand_ng = any(
            ng == b
            for b in brand_list
            for ng in brand_ng_list
        )

        if asin_ng or brand_ng:

            # --- INACTIVE ---
            cur.execute("""
                UPDATE listed_items
                SET information_status = 'INACTIVE'
                WHERE id = %s
            """, (row["id"],))

            if row["status"] == "listed":
                print(f"[BLACKLIST DELETE] ASIN:{asin}")  # // チェック完了後削除
                delete_listings_item(
                    user_id=user_id,
                    country_code=country_code,
                    marketplace_id=row["region_marketplace_id"],
                    seller_sku=row["sku"]
                )

        else:
            # --- ACTIVEに戻す（ここ追加） ---
            cur.execute("""
                UPDATE listed_items
                SET information_status = 'ACTIVE'
                WHERE id = %s
            """, (row["id"],))            

    conn.commit()
    conn.close()
 
