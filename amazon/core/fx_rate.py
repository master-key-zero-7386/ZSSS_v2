# ==========================================
# ファイル名: amazon/core/fx_rate/py
# 目的: FXレート取得
# ==========================================

import sqlite3
from amazon.db_migrate import DB_DIR


# --- ▼ SECTION 01: FX取得（HOME → REGION） ▼ ---
def get_exchange_rate(base_currency: str, target_currency: str):

    conn = sqlite3.connect(f"{DB_DIR}/a_fx.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT rate
        FROM fx_rates
        WHERE base_currency = ?
        AND target_currency = ?
        LIMIT 1
    """, (base_currency, target_currency))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return float(row["rate"])
