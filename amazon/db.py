# ==========================================
# ファイル名: amazon/db.py
# 目的: ZSSSのDB基盤モジュール（PostgreSQL専用）
#       - PostgreSQL接続の共通化（get_conn）
#       - marketplaceマスタ情報の取得
#       - user_id / country_code / marketplace_id から
#         SP-API接続情報を取得するための専用モジュール
# ==========================================

import os
import atexit
import psycopg2
from psycopg2 import pool as _pg_pool
from pathlib import Path
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

PG_HOST = os.environ.get("PG_HOST")
PG_PORT = os.environ.get("PG_PORT")
PG_USER = os.environ.get("PG_USER")
PG_PASSWORD = os.environ.get("PG_PASSWORD")
PG_DATABASE = os.environ.get("PG_DATABASE")

# --- ▼ SECTION 01: PostgreSQL接続プール ▼ ---
# get_conn()がリクエスト/バックグラウンドループのたびに毎回新規TCP接続していたのを
# プール化。Flaskはthreaded=True、バックグラウンドスレッドも複数同時稼働するため
# スレッドセーフなThreadedConnectionPoolを使用。
_POOL = _pg_pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=20,
    host=PG_HOST,
    port=PG_PORT,
    user=PG_USER,
    password=PG_PASSWORD,
    dbname=PG_DATABASE,
    client_encoding="UTF8",
    cursor_factory=RealDictCursor,
)

atexit.register(_POOL.closeall)

# --- ▼ SECTION 01-1: プール貸出用ラッパー ▼ ---
# 呼び出し側は今まで通り conn.cursor() / conn.commit() / conn.close() を呼ぶだけでよい。
# close() だけをプール返却に差し替え、それ以外は__getattr__で本物のconnectionへ委譲する。
class _PooledConnection:
    def __init__(self, conn):
        self._conn = conn
        self._returned = False

    def close(self):
        if self._returned:
            return
        self._returned = True

        try:
            # --- 借用中に例外でcommit/rollbackされないまま返却されるのを防ぐ ---
            if not self._conn.closed:
                self._conn.rollback()
            _POOL.putconn(self._conn)
        except Exception:
            try:
                _POOL.putconn(self._conn, close=True)
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __del__(self):
        # --- close()し忘れ（例外パスなど）でもGC時にプールへ返却されるようにする保険 ---
        try:
            self.close()
        except Exception:
            pass

# --- ▼ SECTION 02: 共通接続入口 ▼ ---
# db_name はテーブル/DB識別用の引数として過去のSQLite分割DB構成から残っているが、
# PostgreSQLは単一DBに統一しているため接続先の決定には使用しない。
def get_conn(db_name):
    return _PooledConnection(_POOL.getconn())

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
