# =====================================================
# ファイル名: amazon/guard/guard_404.py
# 目的：HTTPステータスコード404用ファイル
# =====================================================

import os
import sqlite3
import time
from amazon.db_migrate import DB_DIR

# --- ▼ SECTION 01: 404（ASIN個別・恒久停止） ▼ ---
def mark_asin_api_stop(*, user_id: int, asin: str, region: str) -> None:
    """
    404 確定時に呼ばれる。
    listed_items.api_stop_asin = 1 を記録するだけ。
    判定はしない。
    """

    db_path = os.path.join(DB_DIR, f"a_{region.lower()}_listed_items.db")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE listed_items
            SET api_stop_asin = 1
            WHERE user_id = ? AND asin = ?
        """, (user_id, asin))
        conn.commit()
    finally:
        conn.close()

    print("[API_GUARD][404] api_stop_asin=1", user_id, asin, db_path)

# --- ▼ SECTION 02: 429（全体・即停止） ▼ ---
def handle_api_429(*, sleep_sec: int) -> None:
    print(f"[API_GUARD][429] global sleep {sleep_sec}s")
    time.sleep(sleep_sec)

