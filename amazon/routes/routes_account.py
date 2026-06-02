# ==========================================
# ファイル名: amazon/routes_account.py
# 目的: アカウント設定・管理者設定専用ルート
# ==========================================

import os
import sqlite3
from flask import Blueprint, jsonify, session, render_template, request
from auth.routes_auth import login_required
from amazon.constants import BASE_DIR
from amazon.db import get_conn
from amazon.adapters.api_usage_summary import get_api_usage_summary
from datetime import datetime

# --- ▼ SECTION 01: account_master + marketplaces_master → marketplaces へコピー ▼ ---
def copy_marketplace_from_master(country_code: str, user_id: str):
    country_code = (country_code or "").upper()

    # ------------------------------------------------------------
    # ① account_master（ユーザー固有情報）
    # ------------------------------------------------------------
    conn_acc = get_conn("a_account_master.db")
    cur_acc = conn_acc.cursor()

    cur_acc.execute("""
        SELECT 
            user_id,
            home_flag,
            country_code,
            account_seller_id,
            refresh_token
        FROM account_master
        WHERE user_id = %s
          AND UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
        LIMIT 1
    """, (user_id, country_code))

    row_acc = cur_acc.fetchone()
    conn_acc.close()

    if not row_acc:
        raise ValueError(f"[copy_marketplace] account_master に user_id={user_id}, country_code={country_code} がありません")

    # columns_acc = [desc[0] for desc in cur_acc.description] 
    # acc = dict(zip(columns_acc, row_acc)) 

    acc = row_acc 


    # ------------------------------------------------------------
    # ② marketplaces_master（Amazon各国プリセット情報）
    # ------------------------------------------------------------
    conn_master = get_conn("a_marketplaces_master.db")
    cur_master = conn_master.cursor()

    cur_master.execute("""
        SELECT
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

            access_key,
            secret_key
        FROM marketplaces_master
        WHERE UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
        LIMIT 1
    """, (country_code,))

    row_m = cur_master.fetchone()
    if not row_m:
        conn_master.close() 
        raise ValueError(f"[copy_marketplace] marketplaces_master に country_code={country_code} がありません") 

    master = row_m  

    conn_master.close()

    # ------------------------------------------------------------
    # ③ account + master を合成 → a_marketplaces.db へ書き込み
    # ------------------------------------------------------------
    conn_user = get_conn("a_marketplaces.db")
    cur_user = conn_user.cursor()

    # ★ ここに入れる（marketplaces 側 HOME 全解除）
    if acc["home_flag"] == 1:
        cur_user.execute("""
            UPDATE marketplaces
            SET home_flag = 0
            WHERE user_id = %s
            AND home_flag = 1
        """, (acc["user_id"],))

    now_utc = datetime.utcnow().isoformat()

    cur_user.execute("""
        INSERT INTO marketplaces (
            user_id,
            home_flag,
            country_code,
            account_seller_id,
            refresh_token,

            display_name,
            marketplace_id,
            access_key,
            secret_key,

            currency,
            weight_unit,
            dimension_unit,
            host,

            spapi_host,
            locale,
            timezone,
            override_exchange_rate,

            created_at,
            updated_at
        )
        VALUES (
            %s, %s, %s, %s, %s, 
            %s, %s, %s, %s,
            %s, %s, %s, %s, 
            %s, %s, %s, %s, 
            %s, %s
        )
        ON CONFLICT(user_id, country_code) DO UPDATE SET
            home_flag        = excluded.home_flag,
            account_seller_id = excluded.account_seller_id,
            refresh_token     = excluded.refresh_token,

            display_name   = excluded.display_name,
            marketplace_id = excluded.marketplace_id,
            access_key     = excluded.access_key,
            secret_key     = excluded.secret_key,

            currency       = excluded.currency,
            weight_unit    = excluded.weight_unit,
            dimension_unit = excluded.dimension_unit,
            host           = excluded.host,
            spapi_host     = excluded.spapi_host,
            locale         = excluded.locale,
            timezone       = excluded.timezone,
            override_exchange_rate  = excluded.override_exchange_rate,
            updated_at     = %s
    """, (
        acc["user_id"],
        acc["home_flag"],
        acc["country_code"],
        acc["account_seller_id"],
        acc["refresh_token"],

        master["display_name"],
        master["marketplace_id"],
        master["access_key"],
        master["secret_key"],

        master["currency"],
        master["weight_unit"],
        master["dimension_unit"],
        master["host"],
        master["spapi_host"],
        master["locale"],
        master["timezone"],
        master["override_exchange_rate"],
        now_utc,
        now_utc,        
        now_utc
    ))

    conn_user.commit()
    conn_user.close()

account_bp = Blueprint("account_bp", __name__)

# --- ▼ SECTION 02: マーケットプレイスマスター取得（管理者専用）  ▼ ---
@account_bp.route("/admin/get_marketplaces_master", methods=["GET"])
@login_required
def admin_get_marketplaces_master():
    if not session.get("is_admin"):
        # ★ DataTables は配列を期待する
        return jsonify({"data": []})

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM marketplaces_master ORDER BY id ASC")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({"data": rows})

# --- ▼ SECTION 03: Amazon Retail 取得（管理者専用） ▼ --- 
@account_bp.route("/admin/get_amazon_retail", methods=["GET"])
@login_required
def admin_get_amazon_retail():
    if not session.get("is_admin"):
        return jsonify({"data": []})

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM amazon_retail_sellers")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    return jsonify({"data": rows})

# --- ▼ SECTION 04: アカウント設定ページ表示 ▼ ---
@account_bp.route("/", methods=["GET"])
@login_required # ログイン情報判定制限
def account_page():
    print("account_page loaded")
    return render_template("account.html")

# --- ▼ SECTION 05: HOME 専用アカウント情報取得API ▼ --- 
@account_bp.route("/get_home_account", methods=["GET"])
@login_required
def get_home_account():
    """HOME（基準国）専用のアカウント情報取得API"""
    try:
        user_id = session.get("user_id")

        # ======================================================
        # ① HOME region を a_marketplaces.db から決定する
        # ======================================================        
        conn_mkt = get_conn("a_marketplaces.db")
        cur_mkt = conn_mkt.cursor()

        cur_mkt.execute("""
            SELECT country_code
            FROM marketplaces
            WHERE user_id = %s
              AND home_flag = 1
            LIMIT 1
        """, (user_id,)) 

        row_home = cur_mkt.fetchone()

        if not row_home:
            conn_mkt.close()
            return jsonify({
                "status": "success",
                "account": {},
                "marketplace": {}
            })

        home_country_code = row_home["country_code"]

        conn_mkt.close()

        # ======================================================
        # ② HOME のアカウント情報（すべて a_marketplaces.db から取得）
        # ======================================================
        conn_acc = get_conn("a_marketplaces.db")
        cur_acc = conn_acc.cursor()

        cur_acc.execute("""
            SELECT
                country_code,
                account_seller_id,
                refresh_token,
                marketplace_id,
                display_name,
                host,
                spapi_host,
                locale,
                currency,
                weight_unit,
                dimension_unit,
                timezone,
                override_exchange_rate
            FROM marketplaces
            WHERE user_id = %s
            AND UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
            LIMIT 1
        """, (user_id, home_country_code))

        acc = cur_acc.fetchone()

        if not acc:
            conn_acc.close()
            return jsonify({"status": "error", "message": "not found"})

        # columns_acc = [desc[0] for desc in cur_acc.description]
        # acc = dict(zip(columns_acc, acc))

        acc = acc

        conn_acc.close()

        mkt = None

        # ======================================================
        # --- acc に全情報があるので分割して返す ---
        # ======================================================

        acc_dict = acc if acc else {}

        return jsonify({
            "status": "success",
            "account": {
                "account_seller_id": acc_dict.get("account_seller_id", ""),
                "refresh_token": acc_dict.get("refresh_token", "")
            },
            "marketplace": {
                "country_code": acc_dict.get("country_code", ""),
                "display_name": acc_dict.get("display_name", ""),
                "marketplace_id": acc_dict.get("marketplace_id", ""),
                "host": acc_dict.get("host", ""),
                "spapi_host": acc_dict.get("spapi_host", ""),
                "locale": acc_dict.get("locale", ""),
                "currency": acc_dict.get("currency", ""),
                "weight_unit": acc_dict.get("weight_unit", ""),
                "dimension_unit": acc_dict.get("dimension_unit", ""),
                "timezone": acc_dict.get("timezone", ""),
                "override_exchange_rate": acc_dict.get("override_exchange_rate", "")
            }
        })

    except Exception as e:
        print("[ERR] get_home_account:", e)
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 06: region 専用アカウント情報取得API ▼ ---　
@account_bp.route("/get_account_master", methods=["GET"])
@login_required
def get_account_master():
    """ 特定 region の marketplaces.db から統合情報を返す（HOMEは扱わない） """
    try:
        country_code = (request.args.get("country_code") or request.args.get("region") or "").strip().upper()

        user_id = session.get("user_id")

        if not country_code:
            return jsonify({"status": "error", "message": "country_code required"}), 400

        # ============================================================
        # ① a_marketplaces.db（統合済みの1レコードを取得） 
        # ============================================================
        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT
                account_seller_id,
                refresh_token,
                country_code,
                display_name,
                marketplace_id,
                host,
                spapi_host,
                locale,
                currency,
                weight_unit,
                dimension_unit,
                timezone,
                override_exchange_rate
            FROM marketplaces
            WHERE user_id = %s
              AND UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
            LIMIT 1
        """, (user_id, country_code)) 

        row = cur.fetchone()

        if not row:
            conn.close()
            return jsonify({"status": "error", "message": "not found"}), 404

        # columns = [desc[0] for desc in cur.description]
        # row = dict(zip(columns, row))
        row = row 

        conn.close()

        return jsonify({
            "status": "success",
            "account": {
                "account_seller_id": row.get("account_seller_id", ""),
                "refresh_token": row.get("refresh_token", "")
            },
            "marketplace": {
                "country_code": row.get("country_code", ""),
                "display_name": row.get("display_name", ""),
                "marketplace_id": row.get("marketplace_id", ""),
                "host": row.get("host", ""),
                "spapi_host": row.get("spapi_host", ""),
                "locale": row.get("locale", ""),
                "currency": row.get("currency", ""),
                "weight_unit": row.get("weight_unit", ""),
                "dimension_unit": row.get("dimension_unit", ""),
                "timezone": row.get("timezone", ""),
                "override_exchange_rate": row.get("override_exchange_rate", "")
            }
        })

    except Exception as e:
        print("[ERR] get_account_master:", e)
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 07: アカウント保存処理（HOME / REGION 共通） ▼ ---
@account_bp.route("/save_account_master", methods=["POST"])
@login_required
def save_account_master():
    try:
        data = request.get_json() or {}
        user_id = session.get("user_id")

        # -------------------------------------------------------
        # ① 受け取り（UI から来るのはこの4つだけ）
        # -------------------------------------------------------
        country_code      = (data.get("country_code") or "").strip().upper() 
        account_seller_id = (data.get("account_seller_id") or "").strip()
        refresh_token     = (data.get("refresh_token") or "").strip()
        home_flag         = 1 if str(data.get("home_flag") or "0") == "1" else 0

        if not country_code:
            return jsonify({"status": "error", "message": "country_code required"}), 400

        # -------------------------------------------------------
        # ② account_master の seller_id / refresh_token だけ更新
        #    ※ 管理者項目（client_id 等）は触らない
        # -------------------------------------------------------
        conn_acc = get_conn("a_account_master.db")
        cur_acc = conn_acc.cursor()

        # --- ▼ 追加：HOMEは必ず1件にする（ここを修正） ---
        if home_flag == 1:
            cur_acc.execute("""
                UPDATE account_master
                SET home_flag = 0
                WHERE user_id = %s
                AND home_flag = 1
            """, (user_id,))
        # --- ▲ 追加ここまで ---

        now_utc = datetime.utcnow().isoformat()

        cur_acc.execute("""
            INSERT INTO account_master (
                user_id, country_code, home_flag,
                account_seller_id, refresh_token,
                created_at, updated_at
            )
            VALUES(%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id, country_code) DO UPDATE SET
                home_flag         = excluded.home_flag,
                account_seller_id = excluded.account_seller_id,
                refresh_token     = excluded.refresh_token,
                updated_at        = excluded.updated_at
        """, (
            user_id, country_code, home_flag,
            account_seller_id, refresh_token,
            now_utc, now_utc
        ))

        conn_acc.commit()
        conn_acc.close()

        # -------------------------------------------------------
        # ③ SECTION 1 を呼び出して、master → marketplaces に同期
        # -------------------------------------------------------
        copy_marketplace_from_master(country_code, user_id)

        # -------------------------------------------------------
        # 完了
        # -------------------------------------------------------
        return jsonify({"status": "ok", "message": f"{country_code} saved"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 08: TTL用 float 安全変換 ▼ ---
def safe_float(val, default):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

# --- ▼ SECTION 09: API取得ON/OFF サイクル保存（marketplaces専用） ▼ ---
@account_bp.route("/save_api_settings", methods=["POST"])
@login_required
def save_api_settings():
    try:
        data = request.get_json() or {}
        user_id = session.get("user_id")

        country_code = (data.get("country_code") or "").strip().upper()
        if not country_code:
            return jsonify({"status": "error", "message": "country_code required"}), 400

        enable_home_catalog   = int(data.get("enable_home_catalog", 0))
        enable_home_pricing   = int(data.get("enable_home_pricing", 0))
        enable_region_catalog = int(data.get("enable_region_catalog", 0))
        enable_region_pricing = int(data.get("enable_region_pricing", 0))

        h_catalog_ttl_days = safe_float(data.get("h_catalog_ttl_days"), 90)
        h_pricing_ttl_days = safe_float(data.get("h_pricing_ttl_days"), 90)
        r_catalog_ttl_days = safe_float(data.get("r_catalog_ttl_days"), 90)
        r_pricing_ttl_days = safe_float(data.get("r_pricing_ttl_days"), 90)        

        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()

        now_utc = datetime.utcnow().isoformat()

        cur.execute("""
            UPDATE marketplaces
            SET
                enable_home_catalog   = %s,
                enable_home_pricing   = %s,
                enable_region_catalog = %s,
                enable_region_pricing = %s,

                h_catalog_ttl_days = %s,
                h_pricing_ttl_days = %s,
                r_catalog_ttl_days = %s,
                r_pricing_ttl_days = %s,

                updated_at = %s
            WHERE user_id = %s
            AND UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
        """, (
            enable_home_catalog,
            enable_home_pricing,
            enable_region_catalog,
            enable_region_pricing,

            h_catalog_ttl_days,
            h_pricing_ttl_days,
            r_catalog_ttl_days,
            r_pricing_ttl_days,

            now_utc,
            user_id,
            country_code
        ))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 10: API取得ON/OFF サイクル取得（marketplaces専用） ▼ ---
@account_bp.route("/get_api_settings", methods=["GET"])
@login_required
def get_api_settings():
    try:
        user_id = session.get("user_id")
        country_code = (request.args.get("country_code") or "").strip().upper()

        if not country_code:
            return jsonify({"status": "error", "message": "country_code required"}), 400

        conn = get_conn("a_marketplaces.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT
                enable_home_catalog,
                enable_home_pricing,
                enable_region_catalog,
                enable_region_pricing,


                h_catalog_ttl_days, 
                h_pricing_ttl_days, 
                r_catalog_ttl_days, 
                r_pricing_ttl_days                 

            FROM marketplaces
            WHERE user_id = %s
              AND UPPER(TRIM(country_code)) = UPPER(TRIM(%s))
            LIMIT 1
        """, (user_id, country_code))

        row = cur.fetchone()

        if not row:
            conn.close()
            return jsonify({"status": "ok", "settings": {}})

        # columns = [desc[0] for desc in cur.description]
        # row = dict(zip(columns, row))

        row = row

        conn.close()

        return jsonify({
            "status": "ok",
            "settings": {
                "enable_home_catalog": row.get("enable_home_catalog", 0),
                "enable_home_pricing": row.get("enable_home_pricing", 0),
                "enable_region_catalog": row.get("enable_region_catalog", 0),
                "enable_region_pricing": row.get("enable_region_pricing", 0),

                "h_catalog_ttl_days": row.get("h_catalog_ttl_days", 0),
                "h_pricing_ttl_days": row.get("h_pricing_ttl_days", 0),
                "r_catalog_ttl_days": row.get("r_catalog_ttl_days", 0),
                "r_pricing_ttl_days": row.get("r_pricing_ttl_days", 0)
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 11: HOME フラグ切り替えAPI ▼ ---Z
@account_bp.route("/set_home_country_code", methods=["POST"])
@login_required
def set_home_country_code():
    data = request.json
    new_home = (data.get("new_home_country_code") or "").strip().upper()
    user_id = session["user_id"]

    try:
        now_utc = datetime.utcnow().isoformat()
        
        # --- a_account_master.db ---
        conn = get_conn("a_account_master.db") 
        cur = conn.cursor()

        # ▼ まず new_home のレコードが存在するか確認（ここを追加）
        cur.execute("""
            SELECT 1 FROM account_master
            WHERE user_id = %s AND country_code = %s
            LIMIT 1
        """, (user_id, new_home))
        exists = cur.fetchone()

        if not exists:
            conn.close()
            return jsonify({
                "status": "error",
                "message": "home record not found"
            }), 404


        # ▼ HOME の実在が確認できた場合のみフラグ更新（元の処理）
        cur.execute("""
            UPDATE account_master
            SET home_flag = CASE WHEN country_code = %s THEN 1 ELSE 0 END, updated_at = %s
            WHERE user_id = %s
        """, (new_home, now_utc, user_id))
        conn.commit()
        conn.close()

        # --- a_marketplaces.db (同じロジックで HOME が存在する時だけ更新)
        conn = get_conn("a_marketplaces.db") 
        cur = conn.cursor()
        cur.execute("""
            UPDATE marketplaces
            SET home_flag = CASE WHEN country_code = %s THEN 1 ELSE 0 END, updated_at = %s
            WHERE user_id = %s
        """, (new_home, now_utc, user_id))
        conn.commit()
        conn.close()

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 12: HOME HOMEプルダウン切替時 既存HOME削除API ▼ ---
@account_bp.route("/delete_home_account", methods=["POST"])
@login_required
def delete_home_account():
    try:
        user_id = session.get("user_id")

        # -----------------------------------------------------
        # ① a_account_master.db の HOME削除（既存）
        # -----------------------------------------------------
        conn = get_conn("a_account_master.db")
        cur    = conn.cursor()

        cur.execute("""
            DELETE FROM account_master
            WHERE user_id = %s
              AND home_flag = 1
        """, (user_id,))

        conn.commit()
        conn.close()

        # -----------------------------------------------------
        # ② a_marketplaces.db の HOME削除（追加）
        # -----------------------------------------------------
        conn2 = get_conn("a_marketplaces.db")
        cur2   = conn2.cursor()

        # ★ HOMEフラグ=1 のマーケットプレイスを削除
        cur2.execute("""
            DELETE FROM marketplaces
            WHERE user_id = %s
              AND home_flag = 1
        """, (user_id,))  
        conn2.commit()
        conn2.close()

        return jsonify({"status": "success", "message": "HOME account deleted"})

    except Exception as e:
        print("[ERR] delete_home_account:", e)
        return jsonify({"status": "error", "message": str(e)})

# --- ▼ SECTION 13: マーケットプレイス一覧取得（MasterDB版：HOME専用） ▼ --- 
@account_bp.route("/get_marketplaces_master", methods=["GET"])        
@login_required                                                      
def get_marketplaces_master_for_account():                                       
    from amazon.db import get_conn                                   
    conn = get_conn("a_marketplaces_master.db")                      
    cur = conn.cursor()                                              

    cur.execute("""                                                  
        SELECT
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

    rows_list = [                                              
            {
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
        ]

    return jsonify({
        "data": rows_list,
        "regions": rows_list       
    })

# --- ▼ SECTION 14: API使用量サマリー（表示用・読み取り専用） ▼ ---
@account_bp.route("/api-usage-summary", methods=["GET"])
@login_required
def api_usage_summary():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "not logged in"}), 401

    data = get_api_usage_summary(user_id)
    return jsonify({"status": "ok", "data": data})

