# ==========================================
# ファイル名: amazon/db.py
# 目的: ZSSSのDB基盤モジュール
#       - SQLite接続の共通化（get_conn）
#       - marketplaceマスタ情報の取得
#       - user_id / country_code / marketplace_id から
#         SP-API接続情報を取得するための専用モジュール
# ==========================================

import os
import sqlite3
from pathlib import Path

# --- DBディレクトリの決定 ---
# 優先順位:
# 1. 環境変数 ZSSS_DB_DIR が指定されていればそれを使用
# 2. なければ zsss_web/db をデフォルトとする

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  
DATA_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DATA_DIR, exist_ok=True)

# --- ▼ SECTION 01:  ▼ ---
def get_conn(db_name):
    """指定されたDBに接続（なければ新規作成）"""
    # db_path = os.path.join(DATA_DIR, db_name)

    if "_blacklist_" in db_name:
        db_path = os.path.join(DATA_DIR, "blacklist", db_name) 
    elif "_seller_list" in db_name:
        db_path = os.path.join(DATA_DIR, "sellerlist", db_name) 
    else:
        db_path = os.path.join(DATA_DIR, db_name)    
    
    conn = sqlite3.connect(db_path, timeout=10) # 一旦保留
    conn.row_factory = sqlite3.Row
    return conn

# --- ▼ SECTION 02:アカウント情報取得（user_id + country_code + marketplaces 参照） ▼ ---
def get_account_info(country_code: str, user_id: str | None = None) -> dict:
    if not user_id:
        raise ValueError("user_id が指定されていません。")

    # country_code は絶対に HOME ではなく US/AU/JP/SG の実リージョン
    country_code = (country_code or "")

    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT
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
            override_exchange_rate,
            access_key,
            secret_key,
            created_at,
            updated_at
        FROM marketplaces
        WHERE country_code = ? AND user_id = ?
        LIMIT 1
    """, (country_code, user_id))

    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(
            f"marketplaces に user_id={user_id}, country_code={country_code} のレコードが見つかりません。"
        )

    return {key: row[key] for key in row.keys()}

# --- ▼ SECTION 03:  ▼ ---
def get_account_info_by_marketplace_id(marketplace_id: str, user_id: int) -> dict:
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM marketplaces
        WHERE marketplace_id = ? AND user_id = ?
        LIMIT 1
    """, (marketplace_id, user_id))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(
            f"marketplaces に user_id={user_id}, marketplace_id={marketplace_id} のレコードが見つかりません。"
        )

    return {key: row[key] for key in row.keys()}

# --- ▼ SECTION 04: LWA認証情報取得（master） ▼ ---
def get_lwa_credentials(country_code: str):
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT client_id, client_secret
        FROM marketplaces_master
        WHERE country_code = ?
        LIMIT 1
    """, (country_code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError("LWA credentials not found in master DB")

    return {
        "client_id": row["client_id"],
        "client_secret": row["client_secret"],
    }
