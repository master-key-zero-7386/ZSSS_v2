# ==========================================
# ファイル名: amazon/services/orbit_settlement_service.py
# 目的: ORBIT（注文管理）決済トランザクションCSV取込・入金額集計
# ==========================================

import csv
import io
import re
from datetime import datetime

from amazon.db import get_conn

# --- ▼ SECTION 01: セラーセントラル「支払い」→「トランザクション」CSVの列名 ▼ ---
# 1行=1注文の集計済みデータ。「合計 (CAD)」のように通貨がヘッダーに埋め込まれており、
# マーケットプレイスによって列名の通貨部分が変わる（CAD/USD/AUD等）ため正規表現で拾う。
TOTAL_COLUMN_PATTERN = re.compile(r"^合計\s*\((\w+)\)$")

TEXT_COLUMN_MAP = {
    "注文番号": "order_id",
    "日付": "transaction_date",
    "トランザクションステータス": "transaction_status",
    "トランザクションの種類": "transaction_type",
}

NUMERIC_COLUMN_MAP = {
    "商品価格合計": "product_price",
    "プロモーション割引合計": "promotion_discount",
    "Amazon手数料": "amazon_fee",
    "その他": "other_amount",
}


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        cleaned = re.sub(r"[^0-9.\-]", "", value)
        if cleaned in ("", "-", "."):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None


# --- ▼ SECTION 02: CSV解析（Amazon決済トランザクション形式） ▼ ---
def parse_settlement_report(text: str) -> list:
    if text.startswith("﻿"):
        text = text[1:]

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    fieldnames = reader.fieldnames or []

    total_col = None
    currency = None
    for fn in fieldnames:
        m = TOTAL_COLUMN_PATTERN.match((fn or "").strip())
        if m:
            total_col = fn
            currency = m.group(1)
            break

    rows = []
    for raw in reader:
        row = {}
        for src_col, dst_col in TEXT_COLUMN_MAP.items():
            value = raw.get(src_col)
            row[dst_col] = value.strip() if value else None

        if not row.get("order_id"):
            continue

        for src_col, dst_col in NUMERIC_COLUMN_MAP.items():
            row[dst_col] = _to_float(raw.get(src_col))

        row["total_amount"] = _to_float(raw.get(total_col)) if total_col else None
        row["currency"] = currency

        rows.append(row)

    return rows


# --- ▼ SECTION 03: 取込（重複行はスキップ。返金・後日調整で同じorder-idに複数回来ても全部残す） ▼ ---
def import_settlement_lines(user_id: int, rows: list) -> int:
    if not rows:
        return 0

    conn = get_conn("a_orbit_settlement_lines.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    sql = """
        INSERT INTO orbit_settlement_lines
            (user_id, order_id, transaction_date, transaction_status, transaction_type,
             product_price, promotion_discount, amazon_fee, other_amount, total_amount,
             currency, imported_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, order_id, transaction_date, total_amount)
        DO NOTHING
    """

    inserted = 0
    for row in rows:
        cur.execute(sql, (
            user_id, row.get("order_id"), row.get("transaction_date"), row.get("transaction_status"),
            row.get("transaction_type"), row.get("product_price"), row.get("promotion_discount"),
            row.get("amazon_fee"), row.get("other_amount"), row.get("total_amount"),
            row.get("currency"), now,
        ))
        inserted += cur.rowcount

    conn.commit()
    conn.close()
    return inserted


# --- ▼ SECTION 04: order-id単位の集計（入金額・販売価格・手数料） ▼ ---
# total_amount(＝合計。手数料等差引後)の合計を入金額(net_proceeds)とする。同じorder-idに
# 複数トランザクション（返金・調整等）があってもSUMすれば正しい手取り額になる。
def get_order_settlement_summary(user_id: int) -> dict:
    conn = get_conn("a_orbit_settlement_lines.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT
            order_id,
            currency,
            SUM(total_amount) AS net_proceeds,
            SUM(product_price) AS sale_price,
            SUM(amazon_fee) AS fees_total,
            MAX(transaction_date) AS deposit_date
        FROM orbit_settlement_lines
        WHERE user_id = %s
        GROUP BY order_id, currency
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    return {r["order_id"]: dict(r) for r in rows}
