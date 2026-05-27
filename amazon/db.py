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
import psycopg2
from pathlib import Path
from dotenv import load_dotenv


# --- DBディレクトリの決定 ---
# 優先順位:
# 1. 環境変数 ZSSS_DB_DIR が指定されていればそれを使用
# 2. なければ zsss_web/db をデフォルトとする

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  
DATA_DIR = os.path.join(BASE_DIR, "db")
os.makedirs(DATA_DIR, exist_ok=True)

load_dotenv()

DB_MODE = os.environ.get("ZSSS_DB_MODE", "sqlite").lower() 

PG_HOST = os.environ.get("PG_HOST")
PG_PORT = os.environ.get("PG_PORT")
PG_USER = os.environ.get("PG_USER")
PG_PASSWORD = os.environ.get("PG_PASSWORD")
PG_DATABASE = os.environ.get("PG_DATABASE")

# --- ▼ SECTION 01: DBパス解決 ▼ ---
def _resolve_db_path(db_name):

    if os.path.isabs(db_name): 
        return db_name

    elif "_blacklist_" in db_name:
        return os.path.join(DATA_DIR, "blacklist", db_name)

    elif "_seller_list" in db_name:
        return os.path.join(DATA_DIR, "sellerlist", db_name)

    return os.path.join(DATA_DIR, db_name)


# --- ▼ SECTION 02: SQLite接続 ▼ ---
def _get_sqlite_conn(db_path):

    conn = sqlite3.connect(db_path, timeout=10) # 一旦保留
    conn.row_factory = sqlite3.Row

    return conn

# --- ▼ SECTION 03: PostgreSQL接続（準備） ▼ ---
def _get_postgres_conn():

    print("PG_HOST =", PG_HOST)  # チェック完了後削除
    print("PG_DATABASE =", PG_DATABASE)  # チェック完了後削除

    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
        client_encoding="UTF8",
    )

    return conn 

    # raise NotImplementedError("PostgreSQL connection is not implemented yet")

# --- ▼ SECTION 04: 共通接続入口 ▼ ---
def get_conn(db_name):

    db_path = _resolve_db_path(db_name)

    if DB_MODE == "sqlite":
        return _get_sqlite_conn(db_path)

    elif DB_MODE == "postgres":
        return _get_postgres_conn()

    raise ValueError(f"unsupported DB_MODE: {DB_MODE}")

# --- ▼ SECTION 05:アカウント情報取得（user_id + country_code + marketplaces 参照） ▼ ---
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
        WHERE country_code = %s AND user_id = %s
        LIMIT 1
    """, (country_code, user_id))

    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(
            f"marketplaces に user_id={user_id}, country_code={country_code} のレコードが見つかりません。"
        )

    columns = [desc[0] for desc in cur.description] 
    return dict(zip(columns, row))

# --- ▼ SECTION 06  ▼ ---
def get_account_info_by_marketplace_id(marketplace_id: str, user_id: int) -> dict:
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM marketplaces
        WHERE marketplace_id = %s AND user_id = %s
        LIMIT 1
    """, (marketplace_id, user_id))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(
            f"marketplaces に user_id={user_id}, marketplace_id={marketplace_id} のレコードが見つかりません。"
        )

    columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))

# --- ▼ SECTION 07: LWA認証情報取得（master） ▼ ---
def get_lwa_credentials(country_code: str):
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT client_id, client_secret
        FROM marketplaces_master
        WHERE country_code = %s
        LIMIT 1
    """, (country_code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError("LWA credentials not found in master DB")

    columns = [desc[0] for desc in cur.description] 
    row_dict = dict(zip(columns, row))

    return {
        "client_id": row["client_id"],
        "client_secret": row["client_secret"],
    }
