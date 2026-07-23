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
# ★変更: catalog/pricingで実際のAmazon側レート制限が違う（catalogの方が緩い）ため、
#        kindで使うsleep秒数を切り替えられるようにした。両方叩く箇所（first_regioncheck等）は
#        より厳しいpricing側の値を使うことで安全側に倒す。
def api_request_sleep(kind: str = "pricing"):
    if kind == "catalog":
        sec = get_ttl_sleep_sec_catalog()
    else:
        sec = get_ttl_sleep_sec_pricing()
    time.sleep(sec)

# --- ▼ SECTION 02: TTL Sleep（旧・共通値。後方互換のため残置） ▼ ---
def get_ttl_sleep_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["ttl_sleep_sec"] is not None:
        return float(row["ttl_sleep_sec"])

    return 0.2  # fallback

# --- ▼ SECTION 02-1: API種別ごとのTTL Sleep（新規） ▼ ---
def get_ttl_sleep_sec_catalog():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_sleep_sec_catalog, ttl_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["ttl_sleep_sec_catalog"] is not None:
        return float(row["ttl_sleep_sec_catalog"])
    if row and row["ttl_sleep_sec"] is not None:
        return float(row["ttl_sleep_sec"])

    return 0.2  # fallback

def get_ttl_sleep_sec_pricing():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_sleep_sec_pricing, ttl_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["ttl_sleep_sec_pricing"] is not None:
        return float(row["ttl_sleep_sec_pricing"])
    if row and row["ttl_sleep_sec"] is not None:
        return float(row["ttl_sleep_sec"])

    return 0.2  # fallback

# --- ▼ SECTION 02-2: TTLサイクル間sleep（旧ttl_loop.pyハードコード） ▼ ---
def get_ttl_cycle_sleep_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT ttl_cycle_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["ttl_cycle_sleep_sec"] is not None:
        return float(row["ttl_cycle_sleep_sec"])

    return 3.0  # fallback（旧ハードコード値と同じ）

# --- ▼ SECTION 02-3: FIRST ASIN間sleep（旧first_loop.pyハードコード） ▼ ---
def get_first_asin_sleep_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT first_asin_sleep_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["first_asin_sleep_sec"] is not None:
        return float(row["first_asin_sleep_sec"])

    return 1.0  # fallback（旧ハードコード値と同じ）

# --- ▼ SECTION 02-4: 429ブロック秒数（旧guard_429.pyハードコード） ▼ ---
def get_api_block_sec():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("SELECT api_block_sec FROM bg_scan_settings WHERE id=1")
    row = cur.fetchone()

    conn.close()

    if row and row["api_block_sec"] is not None:
        return float(row["api_block_sec"])

    return 8.0  # fallback（旧ハードコード値と同じ）

# --- ▼ SECTION 03: FIRST 巡回設定（first_loop専用） ▼ ---
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

# --- ▼ SECTION 03-1: REGIONCHECK 巡回設定（新規・first_loopから分離） ▼ ---
# ★変更: 従来first_loopと同じinterval_min/scan_limitを共有しており、片方だけ
#        調整できなかった。regioncheck専用の値が未設定ならinterval_min/scan_limit
#        （＝旧来の共有動作）にフォールバックするので、既存挙動は変わらない。
def get_regioncheck_scan_settings():
    conn = get_conn("a_bg_scan_settings.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT interval_min, scan_limit,
            regioncheck_interval_min, regioncheck_scan_limit
        FROM bg_scan_settings WHERE id=1
    """)
    row = cur.fetchone()

    conn.close()

    if row and row["regioncheck_interval_min"] is not None:
        interval_min = float(row["regioncheck_interval_min"])
    elif row and row["interval_min"] is not None:
        interval_min = float(row["interval_min"])
    else:
        interval_min = 1.0 / 60

    if row and row["regioncheck_scan_limit"] is not None:
        scan_limit = int(row["regioncheck_scan_limit"])
    elif row and row["scan_limit"] is not None:
        scan_limit = int(row["scan_limit"])
    else:
        scan_limit = 20

    return {
        "interval_sec": interval_min * 60,
        "scan_limit": scan_limit,
    }
