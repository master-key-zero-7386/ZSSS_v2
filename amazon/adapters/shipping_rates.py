# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/shipping_rates.py
# 目的: UI上の送料表表示・shipping_rates.db保存管理
# ======================================================

from amazon.db import get_conn
from datetime import datetime

# --- ▼ SECTION 01: 重量帯定義（仮・固定ルール） ▼ ---
def generate_weight_ranges(max_g=30000):
    """
    0-1000g: 100g刻み
    1001g以上: 1000g刻み
    """
    ranges = []

    # --- 最初だけ特別 ---
    ranges.append((0, 100))

    # --- 101〜1000 ---
    start = 101
    while start <= 1000:
        end = min(start + 99, 1000)
        ranges.append((start, end))
        start = end + 1

    # --- 1001以上（500g刻みの例） ---
    start = 1001
    while start <= max_g:
        end = min(start + 499, max_g)
        ranges.append((start, end))
        start = end + 1

    return ranges

# --- ▼ SECTION 02: 初期送料枠を作成（未入力=0） ▼ ---
def seed_shipping_rates(user_id: int, marketplace_id: str, copy_from_marketplace_id: str = None):
    """
    shipping_rates に重量帯の空行を作成する
    ※ INSERT OR IGNORE 前提（UNIQUEに守られる）
    """
    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()

    # --- ▼ コピー元ありの場合 ▼ ---
    if copy_from_marketplace_id:

        cur.execute("""
            INSERT OR IGNORE INTO shipping_rates
            (
                user_id,
                marketplace_id,
                weight_from_g,
                weight_to_g,
                carrier_1_price,
                carrier_2_price,
                carrier_3_price,
                memo
            )
            SELECT
                user_id,
                ?,
                weight_from_g,
                weight_to_g,
                carrier_1_price,
                carrier_2_price,
                carrier_3_price,
                memo
            FROM shipping_rates
            WHERE user_id = ?
            AND marketplace_id = ?
        """, (
            marketplace_id,
            user_id,
            copy_from_marketplace_id
        ))

        conn.commit()
        conn.close()
        return

    for start_g, end_g in generate_weight_ranges():
        cur.execute("""
            INSERT OR IGNORE INTO shipping_rates
            (
                user_id,
                marketplace_id,
                weight_from_g,
                weight_to_g,
                carrier_1_price,
                carrier_2_price,
                carrier_3_price
            )
            VALUES (?, ?, ?, ?, 0, 0, 0)
        """, (user_id, marketplace_id, start_g, end_g))

    conn.commit()
    conn.close()

# --- ▼ SECTION 03: 送料設定の有効チェック ▼ ---
def has_valid_shipping_rates(user_id: int, marketplace_id: str) -> bool:
    """
    指定 user / marketplace に有効な送料設定が存在するかを判定する
    条件：
    - carrier_1_price / carrier_2_price / carrier_3_price のいずれかが
      1件でも > 0 のレコードが存在すれば OK
    """
    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM shipping_rates
        WHERE user_id = ?
          AND marketplace_id = ?
          AND (
              carrier_1_price > 0
              OR carrier_2_price > 0
              OR carrier_3_price > 0
          )
        LIMIT 1
    """, (user_id, marketplace_id))

    row = cur.fetchone()
    conn.close()

    return row is not None

# --- ▼ SECTION 04: 送料設定 一括更新 ▼ ---
def update_shipping_rates_bulk(user_id: int, marketplace_id: str, rows: list[dict]):
    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()

    # ★ marketplace_id を DB 形式に統一（重要）
    marketplace_id = (marketplace_id or "").upper()

    for row in rows:
        # ★ 数値を必ず int に揃える
        wf = int(row.get("weight_from_g"))
        wt = int(row.get("weight_to_g"))

        c1 = int(row.get("carrier_1_price") or 0)
        c2 = int(row.get("carrier_2_price") or 0)
        c3 = int(row.get("carrier_3_price") or 0)

        memo = row.get("memo") or ""

        now_utc = datetime.utcnow().isoformat()

        cur.execute(
            """
            UPDATE shipping_rates
            SET
                carrier_1_price = ?,
                carrier_2_price = ?,
                carrier_3_price = ?,
                memo = ?,
                updated_at = ?
            WHERE
                user_id = ?
                AND marketplace_id = ?
                AND weight_from_g = ?
                AND weight_to_g = ?
            """,
            (c1, c2, c3, memo, now_utc, user_id, marketplace_id, wf, wt)
        )

    conn.commit()
    conn.close()


