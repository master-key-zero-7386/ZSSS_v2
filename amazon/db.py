# ==========================================
# ファイル名: amazon/db.py
# 目的: ZSSSのDB基盤モジュール（PostgreSQL専用）
#       - PostgreSQL接続の共通化（get_conn）
#       - marketplaceマスタ情報の取得
#       - user_id / country_code / marketplace_id から
#         SP-API接続情報を取得するための専用モジュール
# ==========================================

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

PG_HOST = os.environ.get("PG_HOST")
PG_PORT = os.environ.get("PG_PORT")
PG_USER = os.environ.get("PG_USER")
PG_PASSWORD = os.environ.get("PG_PASSWORD")
PG_DATABASE = os.environ.get("PG_DATABASE")

# --- ▼ SECTION 01: PostgreSQL接続 ▼ ---
def _get_postgres_conn():
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DATABASE,
        client_encoding="UTF8",
        cursor_factory=RealDictCursor,
    )

    return conn

# --- ▼ SECTION 02: 共通接続入口 ▼ ---
# db_name はテーブル/DB識別用の引数として過去のSQLite分割DB構成から残っているが、
# PostgreSQLは単一DBに統一しているため接続先の決定には使用しない。
def get_conn(db_name):
    return _get_postgres_conn()

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

    return row 

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

    return row

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

    # --- ▼ DEBUG: LWA確認 ▼ ---
    if not row:
        raise ValueError("LWA credentials not found in master DB")

    # columns = [desc[0] for desc in cur.description] 
    # row_dict = dict(zip(columns, row))

    return {
        "client_id": row["client_id"],
        "client_secret": row["client_secret"],
    }
