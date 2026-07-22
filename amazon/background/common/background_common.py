# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/background/common/background_common.py
# 目的:#   background（FIRST / TTL）region判定処理用ファイル
# ==========================================================

import time
from amazon.db import get_conn


# --- ▼ SECTION 01: APIノック ASIN間 間隔制御（TTL / FIRST 共通） ▼ ---
def api_request_sleep():
    sec = get_ttl_sleep_sec()
    time.sleep(sec)  # ← 将来UIで変更可能にする

# --- ▼ SECTION 02: TTL Sleep ▼ ---
def get_ttl_sleep_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["ttl_sleep_sec"] is not None:
        return float(row["ttl_sleep_sec"])

    return 0.2  # fallback

# --- ▼ SECTION 03: FIRST 巡回設定（first_loop / first_regioncheck 共通） ▼ ---
def get_first_scan_settings():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT interval_min, scan_limit FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    interval_min = float(row["interval_min"]) if row and row["interval_min"] is not None else (1.0 / 60)
    scan_limit = int(row["scan_limit"]) if row and row["scan_limit"] is not None else 20

    return {
        "interval_sec": interval_min * 60,
        "scan_limit": scan_limit,
    }
