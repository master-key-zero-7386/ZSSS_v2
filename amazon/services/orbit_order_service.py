# ==========================================
# ファイル名: amazon/services/orbit_order_service.py
# 目的: ORBIT（注文管理）注文明細のCSV取込・一覧算定・出力
# ==========================================

import csv
import io
import re
from datetime import datetime

from amazon.db import get_conn
from amazon.core.price_calculator import calculate_shipping_result, get_shipping_rate

# SKUに埋め込まれたASIN（10桁英数字）を抽出するフォールバック用
# 例: "Z_CA_B0GP95SH1F_20260511_NEW001" / "NEW_S_AU_B013S7YU3Y_20240512"
# ※ "_" は正規表現の \w に含まれるため \b では区切れない。"_" 区切りで分割して各断片を照合する。
ASIN_IN_SKU_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def _extract_asin_from_sku(sku):
    if not sku:
        return None

    for part in sku.upper().split("_"):
        if ASIN_IN_SKU_PATTERN.match(part):
            return part
    return None

# --- ▼ SECTION 01: Amazon注文レポート列 → DB列 対応表 ▼ ---
COLUMN_MAP = {
    "order-id": "order_id",
    "order-item-id": "order_item_id",
    "purchase-date": "purchase_date",
    "payments-date": "payments_date",
    "reporting-date": "reporting_date",
    "promise-date": "promise_date",
    "days-past-promise": "days_past_promise",
    "buyer-email": "buyer_email",
    "buyer-name": "buyer_name",
    "buyer-phone-number": "buyer_phone_number",
    "sku": "sku",
    "product-name": "product_name",
    "quantity-purchased": "quantity_purchased",
    "quantity-shipped": "quantity_shipped",
    "quantity-to-ship": "quantity_to_ship",
    "ship-service-level": "ship_service_level",
    "recipient-name": "recipient_name",
    "ship-address-1": "ship_address_1",
    "ship-address-2": "ship_address_2",
    "ship-address-3": "ship_address_3",
    "ship-city": "ship_city",
    "ship-state": "ship_state",
    "ship-postal-code": "ship_postal_code",
    "ship-country": "ship_country",
    "is-business-order": "is_business_order",
    "purchase-order-number": "purchase_order_number",
    "price-designation": "price_designation",
    "is-transparency": "is_transparency",
    "verge-of-cancellation": "verge_of_cancellation",
    "verge-of-lateShipment": "verge_of_late_shipment",
    "signature-confirmation-recommended": "signature_confirmation_recommended",
    "buyer-identification-number": "buyer_identification_number",
    "buyer-identification-type": "buyer_identification_type",
}

IMPORT_COLUMNS = list(dict.fromkeys(COLUMN_MAP.values()))
INTEGER_FIELDS = {"quantity_purchased", "quantity_shipped", "quantity_to_ship"}

# 発送代行会社「依頼書」シートの実列順に合わせる（貼り付けでズレないように）
# 左：依頼書シートと同じ並び（手入力）／中：ZSSS算定・その他ORBIT列（依頼書シートには無い）／右：セラーセントラルCSV由来（元の並びのまま）
EXPORT_COLUMNS = (
    ["agent_serial_no", "request_date", "jan_code", "shipping_type",
     "quantity_purchased", "tracking_number", "purchase_price", "remarks"]
    + ["asin", "length_cm", "width_cm", "height_cm",
       "billable_weight_kg", "predicted_shipping_fee", "notified_at"]
    + IMPORT_COLUMNS
)


# --- ▼ SECTION 02: CSV/TSV解析（Amazon注文レポート形式） ▼ ---
def parse_order_report(text: str) -> list:
    if text.startswith("﻿"):
        text = text[1:]

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
    except csv.Error:
        dialect = csv.excel_tab  # Amazon標準レポートはタブ区切り

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    rows = []
    for raw in reader:
        row = {}
        for src_col, dst_col in COLUMN_MAP.items():
            value = raw.get(src_col)
            if value is not None:
                value = value.strip()
            if value == "":
                value = None

            if dst_col in INTEGER_FIELDS and value is not None:
                try:
                    value = int(value)
                except ValueError:
                    value = None

            row[dst_col] = value

        if row.get("order_item_id"):
            rows.append(row)

    return rows


# --- ▼ SECTION 03: 取込（UPSERT・手入力列は上書きしない） ▼ ---
def upsert_orders(user_id: int, rows: list) -> int:
    if not rows:
        return 0

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    insert_cols = ["user_id"] + IMPORT_COLUMNS + ["created_at", "updated_at"]
    update_cols = [c for c in IMPORT_COLUMNS if c != "order_item_id"]

    col_list = ", ".join(insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))
    update_clause = ", ".join([f"{c}=EXCLUDED.{c}" for c in update_cols])

    sql = f"""
        INSERT INTO orbit_orders ({col_list})
        VALUES ({placeholders})
        ON CONFLICT (user_id, order_item_id) DO UPDATE SET
            {update_clause},
            updated_at = EXCLUDED.updated_at
    """

    for row in rows:
        values = [user_id] + [row.get(c) for c in IMPORT_COLUMNS] + [now, now]
        cur.execute(sql, values)

    conn.commit()
    conn.close()

    return len(rows)


# --- ▼ SECTION 04: 送料算定条件の取得 ▼ ---
def _get_shipping_config(user_id: int) -> dict:
    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT padding_cm, pack_ratio, volumetric_divisor "
        "FROM shipping_config WHERE user_id=%s AND country_code='ALL'",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"padding_cm": 0, "pack_ratio": 0, "volumetric_divisor": 5000}
    return dict(row)


# --- ▼ SECTION 04-2: order-id先頭桁 → マーケット判別 ▼ ---
# ship-countryは「発送先」であって「販売マーケット（通貨圏）」ではない
# （例: USマーケットの注文がAU向けに発送されることもある）ため、送料表・為替のキーには使えない。
# 代わりにorder-idの先頭桁でマーケットを判別する。対応表はmarketplaces_master.order_id_prefixes
# （カンマ区切り。例: AU="2,5"）で管理し、新しいマーケット追加時もコード変更なしで対応できるようにする。
def _load_order_id_prefix_map() -> dict:
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT marketplace_id, order_id_prefixes FROM marketplaces_master "
        "WHERE order_id_prefixes IS NOT NULL AND order_id_prefixes <> ''"
    )
    rows = cur.fetchall()
    conn.close()

    prefix_map = {}
    for row in rows:
        for prefix in row["order_id_prefixes"].split(","):
            prefix = prefix.strip()
            if prefix:
                prefix_map[prefix] = row["marketplace_id"]

    return prefix_map


def _resolve_row_marketplace_id(order_id: str, prefix_map: dict):
    if not order_id:
        return None
    return prefix_map.get(order_id[0])


# --- ▼ SECTION 05: 注文一覧取得（ASIN・サイズ・重量・予測送料つき） ▼ ---
def list_orders_with_calc(user_id: int) -> list:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.*,
               l.asin, l.length_cm, l.width_cm, l.height_cm,
               l.actual_weight_kg, l.override_weight_class
        FROM orbit_orders o
        LEFT JOIN listed_items l
          ON l.user_id = o.user_id AND l.sku = o.sku
        WHERE o.user_id = %s
        ORDER BY o.purchase_date ASC NULLS LAST, o.id ASC
        """,
        (user_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    shipping_config = _get_shipping_config(user_id)
    prefix_map = _load_order_id_prefix_map()
    rate_cache = {}

    for row in rows:
        row["billable_weight_kg"] = None
        row["predicted_shipping_fee"] = None

        # listed_itemsとの突き合わせが取れない場合は、SKUから直接ASINを抽出（表示のみのフォールバック。寸法・重量は突き合わせが必要）
        if not row.get("asin"):
            row["asin"] = _extract_asin_from_sku(row.get("sku"))

        marketplace_id = _resolve_row_marketplace_id(row.get("order_id"), prefix_map)
        if not marketplace_id:
            continue

        if not (row.get("length_cm") and row.get("width_cm") and row.get("height_cm")):
            continue

        if marketplace_id not in rate_cache:
            rate_cache[marketplace_id] = get_shipping_rate(user_id, marketplace_id)

        normalized = {
            "length_cm": row["length_cm"],
            "width_cm": row["width_cm"],
            "height_cm": row["height_cm"],
            "actual_weight_kg": row.get("actual_weight_kg"),
        }

        calc = calculate_shipping_result(
            normalized,
            shipping_config,
            user_id,
            marketplace_id,
            rate_cache[marketplace_id],
            override_weight_g=row.get("override_weight_class"),
        )

        row["billable_weight_kg"] = calc["billable_weight"]
        row["predicted_shipping_fee"] = calc["shipping_fee"]

    return rows


# --- ▼ SECTION 06: JAN・仕入価格の手入力更新 ▼ ---
MANUAL_FIELDS = [
    "jan_code", "purchase_price",
    "request_date", "shipping_type", "tracking_number", "remarks",
    "supplier", "supplier_order_number", "supplier_shop_name", "arrival_date",
]


def update_manual_fields(user_id: int, order_item_id: str, fields: dict):
    allowed = {k: v for k, v in fields.items() if k in MANUAL_FIELDS}
    if not allowed:
        return

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    set_clause = ", ".join([f"{k} = %s" for k in allowed])
    values = list(allowed.values()) + [now, user_id, order_item_id]

    cur.execute(
        f"""
        UPDATE orbit_orders
        SET {set_clause}, updated_at = %s
        WHERE user_id = %s AND order_item_id = %s
        """,
        values,
    )

    conn.commit()
    conn.close()


# --- ▼ SECTION 06-2: 代行会社連番（Nから始まる連番）の設定 ▼ ---
# 対象行に開始番号を設定し、以降は「システムに取り込まれた順（id昇順）」で連番を振り直す。
# 受注日順にすると、AU分を後から取り込んだ時に既存の連番の途中へ割り込んでしまうため、
# 常に末尾に追加される取込順を基準にする（代行会社シートが「常に一番下に追加」の運用のため）。
def set_agent_serial_no(user_id: int, order_item_id: str, start_value: int) -> int:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT order_item_id
        FROM orbit_orders
        WHERE user_id = %s
        ORDER BY id ASC
        """,
        (user_id,),
    )
    ordered_ids = [r["order_item_id"] for r in cur.fetchall()]

    if order_item_id not in ordered_ids:
        conn.close()
        return 0

    start_index = ordered_ids.index(order_item_id)
    now = datetime.utcnow().isoformat()

    serial = int(start_value)
    updated = 0
    for oid in ordered_ids[start_index:]:
        cur.execute(
            "UPDATE orbit_orders SET agent_serial_no = %s, updated_at = %s WHERE user_id = %s AND order_item_id = %s",
            (serial, now, user_id, oid),
        )
        serial += 1
        updated += 1

    conn.commit()
    conn.close()
    return updated


# --- ▼ SECTION 07: 発送代行への通知用CSV出力 ▼ ---
def export_notify_csv(user_id: int, order_item_ids=None) -> str:
    rows = list_orders_with_calc(user_id)

    if order_item_ids:
        wanted = set(order_item_ids)
        rows = [r for r in rows if r["order_item_id"] in wanted]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(EXPORT_COLUMNS)

    for r in rows:
        writer.writerow([r.get(c) if r.get(c) is not None else "" for c in EXPORT_COLUMNS])

    ids = [r["order_item_id"] for r in rows]
    if ids:
        conn = get_conn("a_orbit_orders.db")
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            "UPDATE orbit_orders SET notified_at = %s WHERE user_id = %s AND order_item_id = ANY(%s)",
            (now, user_id, ids),
        )
        conn.commit()
        conn.close()

    return output.getvalue()
