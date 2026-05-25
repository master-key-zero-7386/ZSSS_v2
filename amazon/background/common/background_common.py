# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/background/common/background_common.py
# 目的:#   background（FIRST / TTL）region判定処理用ファイル
# ==========================================================

import os
import sqlite3
import time
from amazon.db import get_conn


# --- ▼ SECTION 01: 有効な listed_items DB ファイル名チェック ▼ ---
def list_listed_dbs(db_dir: str) -> list[str]:
    files = []
    valid_country_codes = get_valid_country_codes(db_dir)

    for fname in os.listdir(db_dir):
        parts = fname.split("_")
        if (
            len(parts) == 4
            and parts[0] == "a"
            and parts[2] == "listed"
            and parts[3] == "items.db"
        ):
            country_code = parts[1].upper()
            if country_code not in valid_country_codes:
                continue

            files.append(os.path.join(db_dir, fname))
    return files

# --- ▼ SECTION 02: 有効な listed_items DB country_code名チェック ▼ ---
def get_valid_country_codes(db_dir: str) -> set[str]:
    db_path = os.path.join(db_dir, "a_marketplaces.db") 
    country_codes = set()

    conn = get_conn("a_marketplaces.db")

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT country_code
            FROM marketplaces
        """)
        for row in cur.fetchall():
            country_codes.add(row[0].upper())
    finally:
        conn.close()

    return country_codes

# --- ▼ SECTION 03: APIノック ASIN間 間隔制御（TTL / FIRST 共通） ▼ ---
def api_request_sleep():
    sec = get_ttl_sleep_sec()
    time.sleep(sec)  # ← 将来UIで変更可能にする

# --- ▼ SECTION 04: TTL Sleep ▼ ---
def get_ttl_sleep_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row[0] is not None:
        return float(row[0])

    return 0.2  # fallback
