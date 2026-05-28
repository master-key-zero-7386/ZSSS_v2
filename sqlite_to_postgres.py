# ==========================================================
# ファイル名： sqlite_to_postgres.py
# 目的： SQLデータ移行用　一時使用　後に削除
# ==========================================================

import os
import sqlite3
import psycopg2

from amazon.db import get_conn


# --- ▼ SECTION 01: DB PATH ▼ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SQLITE_DB_DIR = os.path.join(BASE_DIR, "db")

# --- ▼ SECTION 02: SQLite接続 ▼ ---
def get_sqlite_conn(db_name):

    if "_blacklist_" in db_name:
        db_path = os.path.join(SQLITE_DB_DIR, "blacklist", db_name)
    else:
        db_path = os.path.join(SQLITE_DB_DIR, db_name)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn
    
# --- ▼ SECTION 03: PostgreSQL接続 ▼ ---
def get_postgres_conn(db_name):

    return get_conn(db_name)

# --- ▼ SECTION 04: 移行対象DB ▼ ---
TARGET_DBS = [
    "a_marketplaces_master.db",
    "a_marketplaces.db",
    "a_account_master.db",
    "a_account_settings.db",
    "a_pricing_settings.db",
    "a_pricing_cache.db",
    "a_user_login_accounts.db",
    "a_catalog_cache.db",
    "a_api_usage.db",
    "a_shipping_rates.db",
    "a_bg_scan_settings.db",
    "a_fx.db",
    "a_brand_gate_result.db",

    "a_brand_master.db",
    "a_catalog_settings.db",

    "a_au_listed_items.db",
    "a_ca_listed_items.db",
    "a_jp_listed_items.db",
    "a_sg_listed_items.db",
    "a_us_listed_items.db",

    "a_all_blacklist_asin.db",
    "a_all_blacklist_brand.db",
    "a_au_blacklist_asin.db",
    "a_au_blacklist_brand.db",
    "a_ca_blacklist_asin.db",
    "a_ca_blacklist_brand.db",
    "a_jp_blacklist_asin.db",
    "a_jp_blacklist_brand.db",
    "a_sg_blacklist_asin.db",
    "a_sg_blacklist_brand.db",
    "a_us_blacklist_asin.db",
    "a_us_blacklist_brand.db",
]

# --- ▼ SECTION 05: SQLiteテーブル取得 ▼ ---
def get_sqlite_tables(conn):

    cur = conn.cursor()

    cur.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name
    """)

    return [row["name"] for row in cur.fetchall()]

# --- ▼ SECTION 06: SQLiteデータ取得 ▼ ---
def fetch_all_rows(sqlite_conn, table_name):

    cur = sqlite_conn.cursor()

    cur.execute(f"SELECT * FROM {table_name}")

    return cur.fetchall()

# --- ▼ SECTION 07: PostgreSQL INSERT ▼ ---
def insert_rows(pg_conn, table_name, rows):

    if not rows:
        return

    columns = rows[0].keys()

    columns = list(columns)

    if table_name == "user_login_accounts":

        if "enabled_regions" in columns:
            columns.remove("enabled_regions")

        if "home_region" in columns:
            columns.remove("home_region")

    col_str = ", ".join(columns)
    placeholder = ", ".join(["%s"] * len(columns))

    sql = f"""
        INSERT INTO {table_name} ({col_str})
        VALUES ({placeholder})
        ON CONFLICT DO NOTHING 
    """

    cur = pg_conn.cursor()

    print(f"[INSERT] {table_name} rows={len(rows)}") # チェック完了後削除

    for row in rows:
        values = [row[col] for col in columns]
        cur.execute(sql, values)

    pg_conn.commit()

# --- ▼ SECTION 08: DB移行 ▼ ---
def migrate_one_db(db_name):

    print(f"[START] {db_name}")

    sqlite_conn = get_sqlite_conn(db_name)
    pg_conn = get_postgres_conn(db_name)

    tables = get_sqlite_tables(sqlite_conn)

    for table_name in tables:
        if table_name.startswith("sqlite_"):
            continue

        rows = fetch_all_rows(sqlite_conn, table_name)

        insert_rows(pg_conn, table_name, rows)

        print(f"[OK] {table_name} : {len(rows)} rows")

    sqlite_conn.close()
    pg_conn.close()

# --- ▼ SECTION 09: MAIN ▼ ---
def main():

    for db_name in TARGET_DBS:
        migrate_one_db(db_name)

    print("[DONE] SQLite → PostgreSQL")


if __name__ == "__main__":
    main()