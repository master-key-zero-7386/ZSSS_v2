# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/utils/brand_gate_store.py
# 目的： ゲート通過ブランド記録・保存
# ==========================================================


# --- ▼ SECTION 01: BrandGate保存（From：listing_submit_service） ▼ ---
def save_brand_gate_result(user_id, marketplace_id, brand, status, reason):
    import sqlite3
    from datetime import datetime
    import os

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_file = os.path.join(base_dir, "db", "a_brand_gate_result.db")

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO brand_gate_result (user_id, region_marketplace_id, brand, status, reason, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, region_marketplace_id, brand)
        DO UPDATE SET
            status=excluded.status,
            reason=excluded.reason,
            updated_at=excluded.updated_at
    """, (user_id, marketplace_id, brand, status, reason, now))

    conn.commit()
    conn.close()


        
          