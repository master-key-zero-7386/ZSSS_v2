# ==========================================
# ファイル名: amazon/services/orbit_order_service.py
# 目的: ORBIT（注文管理）注文明細のCSV取込・一覧算定・出力
# ==========================================

import csv
import io
import json
import math
import re
import unicodedata
from datetime import datetime
from decimal import Decimal

import requests

from amazon.db import get_conn
from amazon.db_migrate import ORBIT_ORDERS_COLUMNS
from amazon.core.price_calculator import calculate_shipping_result, get_shipping_rate, get_pricing_master_rule
from amazon.core.fx_rate import get_exchange_rate
from amazon.services.google_sheets_service import (
    fetch_dispatch_sheet_preview,
    fetch_sheet_range,
    get_raw_sheet_settings,
    update_sheet_values,
    batch_update_sheet_values,
    _extract_spreadsheet_id,
)
from amazon.services.orbit_settlement_service import get_order_settlement_summary
from amazon.adapters.catalog_normalized_adapter import NormalizedCatalogAdapter

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


# --- ▼ SECTION 01-1: 発送代行会社への貼り付け前チェック（発注管理画面）用の補正・判定 ▼ ---
# 代行会社シートへの貼り付け時に手作業で直していた項目を自動判定・自動補正する。
# 電話番号の国番号除去・州の正式表記化は貼り付け用CSV出力にもそのまま反映する（代行会社側の制約のため）。
# それ以外（商品名・宛名・住所）は自動修正できないため、画面上でハイライトして人の目でのチェックを促す。
PHONE_COUNTRY_CODE_PATTERN = re.compile(r"^\+\d{1,3}[\s-]*")


def _clean_phone_number(value):
    if not value:
        return value
    return PHONE_COUNTRY_CODE_PATTERN.sub("", value).strip()


# US注文で稀に "602-671-6610 ext. 52861" のように内線番号が付いてくるため、
# 代行会社シートでは電話番号本体と内線番号を別セルに分けて渡す。
PHONE_EXTENSION_PATTERN = re.compile(r"\s*ext\.?\s*(\d+)\s*$", re.IGNORECASE)


def _split_phone_extension(value):
    if not value:
        return value, None
    m = PHONE_EXTENSION_PATTERN.search(value)
    if not m:
        return value, None
    return value[:m.start()].strip(), m.group(1)


# 代行会社シートの寸法・重量欄（AV〜AY）向けの丸めルール。
# 寸法: 10cm未満は10cmに、10cm以上は5cm単位で切り上げる。
# 重量: 丸めた寸法から出す容積重量と実重量の大きい方を、整数kgに切り上げる（最低1kg）。
AGENT_VOLUMETRIC_DIVISOR = 5000


def _agent_round_dim_cm(cm):
    if not cm:
        return None
    if cm < 10:
        return 10.0
    return math.ceil(cm / 5) * 5.0


def _agent_estimated_shipping_weight_kg(length_cm, width_cm, height_cm, actual_weight_kg):
    if not (length_cm and width_cm and height_cm):
        return None
    volumetric_weight_kg = (length_cm * width_cm * height_cm) / AGENT_VOLUMETRIC_DIVISOR
    heaviest = max(actual_weight_kg or 0, volumetric_weight_kg)
    return math.ceil(heaviest) if heaviest > 0 else None


# USPS州略称 → 正式名称（代行会社シートは略称ではなく正式表記が必要）
US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia", "PR": "Puerto Rico", "VI": "Virgin Islands", "GU": "Guam",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}


def _expand_us_state(state, country):
    if not state or (country or "").strip().upper() != "US":
        return state
    return US_STATE_NAMES.get(state.strip().upper(), state)


# --- ▼ SECTION 01-3: 買い手照合キー（買い手購入履歴アーカイブ・返品セキュリティメモの突き合わせ用） ▼ ---
# 氏名は同姓同名・改名がありうるため使わない。住所（郵便番号＋住所1）だけで照合する
# （全角/半角の表記ゆれはNFKC正規化・空白除去・大文字化で吸収する）。
def _normalize_buyer_key(ship_postal_code, ship_address_1):
    def _norm(value):
        if not value:
            return ""
        value = unicodedata.normalize("NFKC", str(value))
        value = re.sub(r"\s+", "", value)
        return value.strip().upper()

    postal = _norm(ship_postal_code)
    address = _norm(ship_address_1)
    if not postal and not address:
        return None
    return f"{postal}|{address}"


def _effective(value, override):
    return override if override not in (None, "") else value


# 手修正が必要な項目（商品名・宛名・住所1〜3）は、Amazon注文レポートの再取込で
# 元の値に上書きされないよう別カラム(*_override)に保存し、あれば優先して使う。
OVERRIDE_FIELD_MAP = {
    "product_name": "product_name_override",
    "recipient_name": "recipient_name_override",
    "ship_address_1": "ship_address_1_override",
    "ship_address_2": "ship_address_2_override",
    "ship_address_3": "ship_address_3_override",
}


def _apply_dispatch_checks(row):
    # 商品名・宛名・住所1〜3：自動修正は一切行わない。人が入力したoverrideがあればそれを表示・出力する。
    for base_field, override_field in OVERRIDE_FIELD_MAP.items():
        row[f"{base_field}_effective"] = _effective(row.get(base_field), row.get(override_field))

    # 電話番号・州：自動修正してよいのはこの2項目のみ。自動修正結果もoverrideがあればそちらを優先する
    # （自動判定で直し切れなかった場合や、誤りに手で気付いた場合に上書きできるように）。
    phone_auto = _clean_phone_number(row.get("buyer_phone_number"))
    phone_auto, extension_auto = _split_phone_extension(phone_auto)
    row["buyer_phone_number_effective"] = _effective(phone_auto, row.get("buyer_phone_number_override"))
    row["buyer_phone_extension_effective"] = _effective(extension_auto, row.get("buyer_phone_extension_override"))

    state_auto = _expand_us_state(row.get("ship_state"), row.get("ship_country"))
    row["ship_state_effective"] = _effective(state_auto, row.get("ship_state_override"))

    product_name = row.get("product_name_effective") or ""
    recipient_name = (row.get("recipient_name_effective") or "").strip()
    address_1 = row.get("ship_address_1_effective") or ""
    address_2 = row.get("ship_address_2_effective") or ""
    address_3 = row.get("ship_address_3_effective") or ""
    phone_effective = row.get("buyer_phone_number_effective") or ""
    state_effective = (row.get("ship_state_effective") or "").strip()

    # ハイライトは「まだ条件を満たしていないか」で判定する。修正（自動 or 手動）が済んで
    # 条件を満たせば、次の表示更新時に自動でハイライトが消える。
    row["flag_phone_country_code"] = bool(PHONE_COUNTRY_CODE_PATTERN.match(phone_effective))
    row["flag_product_name"] = bool(product_name) and (len(product_name) > 70 or "|" in product_name)
    row["flag_recipient_name"] = bool(recipient_name) and (" " not in recipient_name and "　" not in recipient_name)
    row["flag_address1_length"] = len(address_1) > 40
    row["flag_address2_length"] = len(address_2) > 40
    row["flag_address3_length"] = len(address_3) > 40
    row["flag_state_expanded"] = (
        (row.get("ship_country") or "").strip().upper() == "US"
        and len(state_effective) == 2
        and state_effective.isalpha()
    )
    row["flag_postal_code_missing"] = not row.get("ship_postal_code")

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
    # 出荷前でも取れる販売価格系（拡張版の注文レポートにのみ入っている場合がある。無ければ空欄のまま）
    "currency": "order_currency",
    "item-price": "item_price",
    "shipping-price": "shipping_price",
}

IMPORT_COLUMNS = list(dict.fromkeys(COLUMN_MAP.values()))
INTEGER_FIELDS = {"quantity_purchased", "quantity_shipped", "quantity_to_ship"}
FLOAT_FIELDS = {"item_price", "shipping_price"}

# Amazonの注文レポートは通貨コードにISO 4217と異なる独自表記を使うことがある
# （例: カナダドルが"CDN"。fx_ratesテーブルはISOコード("CAD"等)で管理しているため変換する）。
CURRENCY_ALIASES = {"CDN": "CAD"}

# 発送代行会社「依頼書」シートの実列順に合わせる（貼り付けでズレないように）
# 左：依頼書シートと同じ並び（手入力）／中：ZSSS算定・その他ORBIT列（依頼書シートには無い）／右：セラーセントラルCSV由来（元の並びのまま）
# 末尾：依頼書シートAT〜AY列（配送先電話番号・内線・想定発送重量・寸法。ship-countryのさらに右）
EXPORT_COLUMNS = (
    ["agent_serial_no", "request_date", "jan_code", "shipping_type",
     "quantity_purchased", "tracking_number", "invoice_price_jpy", "remarks"]
    + ["asin", "length_cm", "width_cm", "height_cm",
       "billable_weight_kg", "predicted_shipping_fee", "notified_at"]
    + IMPORT_COLUMNS
    + ["buyer_phone_number_effective", "buyer_phone_extension_effective",
       "agent_shipping_weight_kg", "agent_length_cm", "agent_width_cm", "agent_height_cm"]
)

# 桁数の多い/先頭0がありうる数字文字列の列（Excelが数値と誤認識すると指数表記化・先頭0欠落するため
# export_notify_csv側で="123"形式にして文字列として固定する対象）
NUMERIC_TEXT_EXPORT_COLUMNS = {
    "jan_code", "tracking_number", "order_item_id",
    "buyer_phone_number", "buyer_phone_number_effective", "buyer_phone_extension_effective",
    "buyer_identification_number",
}

# --- ZSSS_RAW シート専用の列セット ---
# A〜BE（=EXPORT_COLUMNS の57列）はCSV書き出し（発送代行へ出力）と共通で、内容は固定。
# BF以降は「まだ ZSSS_RAW に出していない項目を全部」並べたもの。利用者が実データを見ながら、
# 代行会社向けに必要な列の取捨選択・並べ替えを決めるための当面のレビュー用。列は
#   ① orbit_orders のうち EXPORT_COLUMNS に無いDB列（スキーマ順、id/user_id 除く）
#   ② list_orders_with_calc が計算で足す派生キー（入金予定額・実利益・各フラグ等。初出順）
# の順で、実際の行データから動的に組み立てる（列の取りこぼしを防ぐため）。
_RAW_SHEET_EXTRA_COLUMNS = [
    c for c in ORBIT_ORDERS_COLUMNS
    if c not in set(EXPORT_COLUMNS) and c not in ("id", "user_id")
]


def _raw_sheet_columns_for(orders) -> list:
    """EXPORT_COLUMNS → 未出力DB列 → 計算派生キー の順に、実データのキーを全部拾って列順を作る。"""
    cols = list(EXPORT_COLUMNS)
    seen = set(cols) | {"id", "user_id"}
    for c in _RAW_SHEET_EXTRA_COLUMNS:
        if c not in seen:
            cols.append(c)
            seen.add(c)
    for r in orders:
        for k in r.keys():
            if k not in seen:
                cols.append(k)
                seen.add(k)
    return cols


# --- ▼ SECTION 02: CSV/TSV解析（Amazon注文レポート形式） ▼ ---
def _normalize_header_cell(value: str) -> str:
    # スプレッドシートを手動整形したCSVでは、折り返し表示の列見出し
    # （例:"ship-\nservice-level"）がセル内改行を含んだままエクスポートされることがある。
    # 改行・空白を除去して"ship-service-level"のような通常の列名と一致させる。
    return re.sub(r"\s+", "", value) if value else value


def parse_order_report(text: str) -> list:
    if text.startswith("﻿"):
        text = text[1:]

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,")
    except csv.Error:
        dialect = csv.excel_tab  # Amazon標準レポートはタブ区切り

    reader = csv.reader(io.StringIO(text), dialect=dialect)

    # 標準のAmazon注文レポートは1行目がヘッダーだが、スプレッドシートを手動整形した
    # CSV（買い手履歴の旧データ取込用など）はタイトル行・空行が先頭に入っていることがある。
    # そのため「order-item-id列を含む行」を実ヘッダーとして検出する（先頭固定にしない）。
    header = None
    for raw_row in reader:
        normalized = [_normalize_header_cell(c) for c in raw_row]
        if "order-item-id" in normalized:
            header = normalized
            break

    if header is None:
        return []

    rows = []
    for raw_row in reader:
        raw = dict(zip(header, raw_row))
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

            if dst_col in FLOAT_FIELDS and value is not None:
                try:
                    value = float(value)
                except ValueError:
                    value = None

            if dst_col == "order_currency" and value is not None:
                value = CURRENCY_ALIASES.get(value.upper(), value.upper())

            row[dst_col] = value

        # "N-No"はAmazon注文レポートには存在しない列で、買い手履歴の旧データを
        # スプレッドシートから取り込む際にのみ付与される（発送代行の管理連番=N番）。
        # 値は"N4000"のように接頭辞付きなので_parse_agent_serial_noで数字部分だけ取り出す
        # （代行会社シート読み戻し処理と同じ変換ルール）。IMPORT_COLUMNSには含めない
        # （通常の受注インポート・エクスポート列構成に影響させないため）。
        row["agent_serial_no"] = _parse_agent_serial_no(raw.get("N-No"))

        # 「2020,-,-,-,...」のような年区切り用の装飾行を除外する
        # （order-item-idは常に数字のみのため、数字以外はデータ行とみなさない）。
        order_item_id = row.get("order_item_id")
        if order_item_id and order_item_id.isdigit():
            rows.append(row)

    return rows


# --- ▼ SECTION 03: 取込（UPSERT・手入力列は上書きしない） ▼ ---
# Amazon注文レポートは、購入からある程度日数が経つと買い手の電話番号などのPII列が
# 空欄で返ってくることがある。空欄での再取込で既存の正常値を消してしまわないよう、
# 新しい値がある列だけ更新し、空欄で来た列は既存値を残す（COALESCE）。
# 行ごと削除してからの再取込は新規INSERTになりこの保護の対象外になるため、
# 意図的な「削除して取り込み直す」リセット操作は従来どおり新しいレポートの内容で確定する。
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
    update_clause = ", ".join([f"{c}=COALESCE(EXCLUDED.{c}, orbit_orders.{c})" for c in update_cols])

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


# --- ▼ SECTION 03-3: 買い手購入履歴アーカイブへの取込（スプレッドシート「FBMバイヤー履歴」の
#     一括インポート専用。orbit_ordersと違い、既存行の上書きはしない＝過去にインポート済みなら
#     スキップするだけの単純なINSERT。列構成はAmazon注文レポートと同一のためparse_order_report()を
#     そのまま再利用できる） ▼ ---
def import_buyer_history_csv(user_id: int, rows: list) -> int:
    if not rows:
        return 0

    conn = get_conn("a_orbit_buyer_history.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    insert_cols = ["user_id"] + IMPORT_COLUMNS + ["agent_serial_no", "buyer_key", "source", "created_at"]
    col_list = ", ".join(insert_cols)
    placeholders = ", ".join(["%s"] * len(insert_cols))

    sql = f"""
        INSERT INTO orbit_buyer_history ({col_list})
        VALUES ({placeholders})
        ON CONFLICT (user_id, order_item_id) DO NOTHING
    """

    imported = 0
    for row in rows:
        buyer_key = _normalize_buyer_key(row.get("ship_postal_code"), row.get("ship_address_1"))
        values = [user_id] + [row.get(c) for c in IMPORT_COLUMNS] + [row.get("agent_serial_no"), buyer_key, "sheet_import", now]
        cur.execute(sql, values)
        imported += cur.rowcount

    conn.commit()
    conn.close()

    return imported


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


def _load_marketplace_country_map() -> dict:
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()
    cur.execute("SELECT marketplace_id, country_code FROM marketplaces_master WHERE marketplace_id IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    return {r["marketplace_id"]: r["country_code"] for r in rows}


# --- ▼ SECTION 04-2b: 実利益算定（決済レポートの入金額 − 仕入価格 − 送料） ▼ ---
# 送料は「代行会社確定値(agent_shipping_fee_total)」を最優先で使う。発送完了前でまだ確定値が無い間は、
# ZSSSの予測送料(predicted_shipping_fee)で代用する（list_orders_with_calc側で既にFuel Surcharge・
# Shipping Fee・Packaging Costを加味した全部込みの値になっているので、ここでは再加算しない）。
def _parse_agent_fee_text(value):
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _apply_settlement_profit(row, *, settlement_summary, fx_cache, settlement_weight=1.0):
    # 決済トランザクションはorder_id単位（1注文にorder_item_idが複数=複数商品あっても1行）なので、
    # そのまま各order_item_id行に適用すると同じ入金額が商品ごとに丸ごと重複してしまう。
    # 販売価格(item_price)の比率（無ければ商品数で均等割り）で按分した額を使う。
    settlement = settlement_summary.get(row.get("order_id"))
    row["net_proceeds"] = settlement.get("net_proceeds") * settlement_weight if settlement else None
    row["sale_price"] = settlement.get("sale_price") * settlement_weight if settlement else None
    row["fees_total"] = settlement.get("fees_total") * settlement_weight if settlement else None
    row["settlement_currency"] = settlement.get("currency") if settlement else None
    row["deposit_date"] = settlement.get("deposit_date") if settlement else None
    row["settlement_is_split"] = bool(settlement and settlement_weight != 1.0)

    # 出荷完了前は代行会社シートの送料セルが空欄または0のままのことが多く、それを確定額として
    # 採用すると送料0円で利益が過大に出てしまう。「発送重量記入日」（=出荷済みの目印）が入っていて、
    # かつ確定送料が正の値のときだけ確定額として採用する。
    is_shipped = bool(row.get("agent_weight_recorded_date"))
    agent_fee = _parse_agent_fee_text(row.get("agent_shipping_fee_total")) if is_shipped else None
    if agent_fee is not None and agent_fee > 0:
        row["shipping_cost_used"] = agent_fee
        row["shipping_cost_is_estimate"] = False
    else:
        predicted = row.get("predicted_shipping_fee")
        if predicted is not None:
            row["shipping_cost_used"] = predicted
            row["shipping_cost_is_estimate"] = True
        else:
            row["shipping_cost_used"] = None
            row["shipping_cost_is_estimate"] = None

    # 入金額は「決済トランザクション実績」を最優先、無ければ「販売価格−手数料見積り」の概算で代用する
    # （手数料見積りは仕入れ判断のためのSP-API getMyFeesEstimate。出荷完了前でも取得できる）。
    if row["net_proceeds"] is not None:
        net_used = row["net_proceeds"]
        net_used_currency = row.get("settlement_currency")
        net_is_estimate = False
    elif row.get("fee_estimate_amount") is not None and row.get("item_price") is not None:
        net_used = (row.get("item_price") or 0) + (row.get("shipping_price") or 0) - row["fee_estimate_amount"]
        net_used_currency = row.get("order_currency") or row.get("fee_estimate_currency")
        net_is_estimate = True
    else:
        net_used = None
        net_used_currency = None
        net_is_estimate = None

    row["net_proceeds_used"] = net_used
    row["net_proceeds_used_currency"] = net_used_currency
    row["net_proceeds_used_jpy"] = None
    row["net_proceeds_is_estimate"] = net_is_estimate
    row["profit_jpy"] = None
    row["profit_is_estimate"] = None
    row["profit_rate_pct"] = None

    # 販売額（手数料差引前の総額）。代行会社への「インボイス価格（円）」は仕入原価ではなく
    # 販売額を基準に算出する必要があるため（仕入原価そのままだとアンダーバリュー扱いになる）、
    # 円換算した販売額の97%を目安のインボイス価格とする（為替変動を見込んで少し安めに設定）。
    if row["sale_price"] is not None:
        gross_used = row["sale_price"]
        gross_used_currency = row.get("settlement_currency")
    elif row.get("item_price") is not None:
        gross_used = (row.get("item_price") or 0) + (row.get("shipping_price") or 0)
        gross_used_currency = row.get("order_currency")
    else:
        gross_used = None
        gross_used_currency = None

    row["sale_price_used"] = gross_used
    row["sale_price_used_currency"] = gross_used_currency
    row["sale_price_used_jpy"] = None
    row["invoice_price_jpy"] = None

    if gross_used is not None:
        if gross_used_currency == "JPY":
            gross_used_jpy = gross_used
        else:
            if gross_used_currency not in fx_cache:
                fx_cache[gross_used_currency] = get_exchange_rate("JPY", gross_used_currency) if gross_used_currency else None
            rate = fx_cache[gross_used_currency]
            gross_used_jpy = gross_used * rate if rate else None
        if gross_used_jpy is not None:
            row["sale_price_used_jpy"] = gross_used_jpy
            row["invoice_price_jpy"] = round(gross_used_jpy * 0.97)

    if net_used is None:
        return

    if net_used_currency == "JPY":
        net_used_jpy = net_used
    else:
        # get_exchange_rate(base, target) は「target通貨1単位あたりのbase通貨額」を返す
        # （routes_pricing_v2.py:903 と同じ呼び方: get_exchange_rate("JPY", 現地通貨) → 現地通貨1単位あたりの円）。
        if net_used_currency not in fx_cache:
            fx_cache[net_used_currency] = get_exchange_rate("JPY", net_used_currency) if net_used_currency else None
        rate = fx_cache[net_used_currency]
        net_used_jpy = net_used * rate if rate else None

    if net_used_jpy is None:
        return

    # 入金額(円)は仕入価格・送料が未確定でも表示できるが、利益(円)は両方揃わないと出せない
    row["net_proceeds_used_jpy"] = net_used_jpy
    if row["shipping_cost_used"] is None or row.get("purchase_price") is None:
        return

    row["profit_jpy"] = net_used_jpy - row["purchase_price"] - row["shipping_cost_used"]
    row["profit_is_estimate"] = bool(net_is_estimate or row["shipping_cost_is_estimate"])
    if net_used_jpy:
        row["profit_rate_pct"] = row["profit_jpy"] / net_used_jpy * 100


# --- ▼ SECTION 04-3: 寸法・重量フォールバック② catalog_cache（ASIN・出品削除後も残る生キャッシュ） ▼ ---
def _fetch_catalog_cache_dims(asin: str):
    if not asin:
        return None

    conn = get_conn("a_catalog_cache.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT home_raw_json FROM catalog_cache
        WHERE asin = %s AND home_raw_json IS NOT NULL
        ORDER BY home_updated_at DESC NULLS LAST
        LIMIT 1
    """, (asin,))
    row = cur.fetchone()
    conn.close()

    if not row or not row.get("home_raw_json"):
        return None

    try:
        raw = json.loads(row["home_raw_json"])
    except (ValueError, TypeError):
        return None

    normalized = NormalizedCatalogAdapter(None)._normalize_dimensions_weight(raw)
    if not (normalized.get("length_cm") and normalized.get("width_cm") and normalized.get("height_cm")):
        return None

    return normalized


# --- ▼ SECTION 04-4: 寸法・重量フォールバック③ その場でHOME APIを叩いて取得（listed_items登録元を問わない） ▼ ---
def fetch_and_cache_catalog_for_asin(user_id: int, asin: str) -> dict:
    if not asin:
        raise ValueError("ASINが必要です")

    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT marketplace_id, country_code FROM marketplaces WHERE user_id = %s AND home_flag = 1 LIMIT 1",
        (user_id,),
    )
    home_row = cur.fetchone()
    conn.close()

    if not home_row:
        raise RuntimeError("HOMEマーケットプレイスが設定されていません")

    # 遅延importで循環参照を避ける（routes_catalog_v2.py等が本モジュールを直接importしないため実際は問題ないが、
    # SP-API系アダプタは重いので必要な時だけ読み込む）
    from amazon.adapters.amazon_adapter import AmazonAdapter
    from amazon.adapters.catalog_adapter_home import CatalogAdapterHome

    base = AmazonAdapter(
        user_id=user_id,
        country_code=home_row["country_code"],
        marketplace_id=home_row["marketplace_id"],
    )
    adapter = CatalogAdapterHome(parent_adapter=base)
    result = adapter.get_full_catalog_item(asin)
    raw = result.get("raw") if isinstance(result, dict) else None

    errors = raw.get("errors") if isinstance(raw, dict) else None
    if errors:
        raise RuntimeError(f"HOME側でASINが見つかりませんでした: {errors}")

    normalized = NormalizedCatalogAdapter(None)._normalize_dimensions_weight(raw)
    if not (normalized.get("length_cm") and normalized.get("width_cm") and normalized.get("height_cm")):
        raise RuntimeError("HOME側に寸法情報がありませんでした")

    # 既存adapter群は「更新専用」でINSERTしないため、ここで自前でcatalog_cacheへ保存する
    now = datetime.utcnow().isoformat()
    home_marketplace_id = home_row["marketplace_id"]
    raw_json = json.dumps(raw, ensure_ascii=False)

    conn = get_conn("a_catalog_cache.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM catalog_cache WHERE asin = %s AND home_marketplace_id = %s",
        (asin, home_marketplace_id),
    )
    existing = cur.fetchone()

    if existing:
        cur.execute("""
            UPDATE catalog_cache
            SET home_raw_json = %s, home_updated_at = %s, updated_at = %s
            WHERE asin = %s AND home_marketplace_id = %s
        """, (raw_json, now, now, asin, home_marketplace_id))
    else:
        cur.execute("""
            INSERT INTO catalog_cache (asin, home_marketplace_id, home_raw_json, home_updated_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (asin, home_marketplace_id, raw_json, now, now))

    conn.commit()
    conn.close()

    return normalized


# --- ▼ SECTION 04-5: 出荷前の概算利益用（SP-API手数料見積り。getMyFeesEstimateをREGION側で叩く） ▼ ---
# 注文が入った時点で最初に取り込む基本形式の注文レポートにはitem-price(販売価格)が無いため、
# 無ければ先にSP-APIのOrders API(getOrderItems)で該当注文明細の販売価格を取得してキャッシュしてから、
# Amazonの想定手数料(参照手数料等)を取得する。item_price + shipping_price − 手数料見積り を概算入金額とする。
def fetch_and_cache_fee_estimate(user_id: int, order_item_id: str) -> dict:
    if not order_item_id:
        raise ValueError("order_item_idが必要です")

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT o.order_id, o.sku, o.item_price, o.shipping_price, o.order_currency, l.asin
        FROM orbit_orders o
        LEFT JOIN listed_items l ON l.user_id = o.user_id AND l.sku = o.sku
        WHERE o.user_id = %s AND o.order_item_id = %s
        """,
        (user_id, order_item_id),
    )
    order_row = cur.fetchone()
    conn.close()

    if not order_row:
        raise RuntimeError("注文が見つかりませんでした")

    # listed_itemsに登録が無い商品は、一覧表示と同じくSKUから直接ASINを抽出するフォールバックを使う
    if not order_row.get("asin"):
        order_row["asin"] = _extract_asin_from_sku(order_row.get("sku"))
    if not order_row.get("asin"):
        raise RuntimeError("ASINが特定できないため手数料見積りを取得できません")

    prefix_map = _load_order_id_prefix_map()
    marketplace_id = _resolve_row_marketplace_id(order_row.get("order_id"), prefix_map)
    if not marketplace_id:
        raise RuntimeError("マーケットプレイスを特定できませんでした")

    country_map = _load_marketplace_country_map()
    country_code = country_map.get(marketplace_id)
    if not country_code:
        raise RuntimeError("マーケットプレイスの国コードが見つかりませんでした")

    from amazon.adapters.amazon_adapter import AmazonAdapter

    base = AmazonAdapter(
        user_id=user_id,
        country_code=country_code,
        marketplace_id=marketplace_id,
    )

    item_price = order_row.get("item_price")
    shipping_price = order_row.get("shipping_price")
    currency = order_row.get("order_currency")

    if not item_price:
        order_items_raw = base.real_signed_request(
            method="GET",
            endpoint=f"/orders/v0/orders/{order_row['order_id']}/orderItems",
            host=base.host,
        )
        errors = order_items_raw.get("errors") if isinstance(order_items_raw, dict) else None
        if errors:
            raise RuntimeError(f"注文の販売価格取得に失敗しました: {errors}")

        items = ((order_items_raw.get("payload") or {}).get("OrderItems")) or []
        matched = next((it for it in items if it.get("OrderItemId") == order_item_id), None)
        item_price_obj = (matched or {}).get("ItemPrice")
        if not matched or not item_price_obj:
            raise RuntimeError("Amazon側にまだ販売価格が確定していません（注文直後は反映まで時間がかかる場合があります）")

        item_price = float(item_price_obj["Amount"])
        shipping_price = float((matched.get("ShippingPrice") or {}).get("Amount") or 0)
        currency = item_price_obj.get("CurrencyCode") or currency

        now = datetime.utcnow().isoformat()
        conn = get_conn("a_orbit_orders.db")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE orbit_orders
            SET item_price = %s, shipping_price = %s, order_currency = %s, updated_at = %s
            WHERE user_id = %s AND order_item_id = %s
            """,
            (item_price, shipping_price, currency, now, user_id, order_item_id),
        )
        conn.commit()
        conn.close()

    currency = currency or "USD"

    raw = base.real_signed_request(
        method="POST",
        endpoint=f"/products/fees/v0/items/{order_row['asin']}/feesEstimate",
        host=base.host,
        json={
            "FeesEstimateRequest": {
                "MarketplaceId": marketplace_id,
                "IsAmazonFulfilled": False,  # 代行会社経由の自社発送のためFBAではない
                "PriceToEstimateFees": {
                    "ListingPrice": {"CurrencyCode": currency, "Amount": item_price},
                    "Shipping": {"CurrencyCode": currency, "Amount": shipping_price or 0},
                },
                "Identifier": order_item_id,
            }
        },
    )

    errors = raw.get("errors") if isinstance(raw, dict) else None
    if errors:
        raise RuntimeError(f"手数料見積りの取得に失敗しました: {errors}")

    result = (raw.get("payload") or {}).get("FeesEstimateResult") or {}
    status = result.get("Status")
    if status and status != "Success":
        error = result.get("Error") or {}
        raise RuntimeError(f"手数料見積りの取得に失敗しました: {error.get('Message') or status}")

    total_fees = ((result.get("FeesEstimate") or {}).get("TotalFeesEstimate")) or {}
    fee_amount = total_fees.get("Amount")
    fee_currency = total_fees.get("CurrencyCode") or currency

    if fee_amount is None:
        raise RuntimeError("手数料見積りの結果を取得できませんでした")

    now = datetime.utcnow().isoformat()
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orbit_orders
        SET fee_estimate_amount = %s, fee_estimate_currency = %s, fee_estimate_fetched_at = %s
        WHERE user_id = %s AND order_item_id = %s
        """,
        (fee_amount, fee_currency, now, user_id, order_item_id),
    )
    conn.commit()
    conn.close()

    return {"fee_estimate_amount": fee_amount, "fee_estimate_currency": fee_currency}


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
    marketplace_country_map = _load_marketplace_country_map()
    pricing_rule_cache = {}

    for row in rows:
        row["billable_weight_kg"] = None
        row["predicted_shipping_fee"] = None
        row["dims_source"] = "listed_items" if (row.get("length_cm") and row.get("width_cm") and row.get("height_cm")) else None

        # 販売マーケット（＝セラーセントラルのドメイン判定に使う。ship-countryは発送先であって
        # 販売マーケットではないため使えない）。order-id先頭桁 → marketplace_id → country_code。
        _row_marketplace_id = _resolve_row_marketplace_id(row.get("order_id"), prefix_map)
        row["marketplace_id"] = _row_marketplace_id
        row["marketplace_country"] = marketplace_country_map.get(_row_marketplace_id)

        _apply_dispatch_checks(row)

        # listed_itemsとの突き合わせが取れない場合は、SKUから直接ASINを抽出（表示用フォールバック）
        if not row.get("asin"):
            row["asin"] = _extract_asin_from_sku(row.get("sku"))

        # --- 寸法・重量の3段フォールバック ---
        # ① listed_items（SKU突き合わせ、既存） → ② catalog_cache（ASIN、出品削除後も残る） → ③ 手入力
        if not row["dims_source"]:
            cached = _fetch_catalog_cache_dims(row.get("asin"))
            if cached:
                row["length_cm"] = cached["length_cm"]
                row["width_cm"] = cached["width_cm"]
                row["height_cm"] = cached["height_cm"]
                row["actual_weight_kg"] = cached.get("actual_weight_kg") or row.get("actual_weight_kg")
                row["dims_source"] = "catalog_cache"

        if not row["dims_source"] and row.get("manual_length_cm") and row.get("manual_width_cm") and row.get("manual_height_cm"):
            row["length_cm"] = row["manual_length_cm"]
            row["width_cm"] = row["manual_width_cm"]
            row["height_cm"] = row["manual_height_cm"]
            row["actual_weight_kg"] = row.get("manual_weight_kg") or row.get("actual_weight_kg")
            row["dims_source"] = "manual"

        # --- 発送代行会社シートの寸法・重量欄（AV〜AY）向け丸め値 ---
        # ZSSS自身の請求重量・予測送料（billable_weight_kg・predicted_shipping_fee）とは別に、
        # 代行会社の梱包基準（10cm未満切り上げ・5cm単位切り上げ・整数kg切り上げ）で算出する。
        row["agent_length_cm"] = _agent_round_dim_cm(row.get("length_cm"))
        row["agent_width_cm"] = _agent_round_dim_cm(row.get("width_cm"))
        row["agent_height_cm"] = _agent_round_dim_cm(row.get("height_cm"))
        row["agent_shipping_weight_kg"] = _agent_estimated_shipping_weight_kg(
            row["agent_length_cm"], row["agent_width_cm"], row["agent_height_cm"], row.get("actual_weight_kg"),
        )

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
        base_shipping_fee = calc["shipping_fee"]

        # 予測送料は「仕入れ段階の目安」として使われるため、運賃表の生値のままではなく
        # 燃油サーチャージ・発送外注費・梱包費（pricing_master_rulesの国別設定）を乗せた
        # 全部込みの見積りにする（仕入れ管理の送料(円)概算と同じ内訳・同じ値にする）。
        country_code = marketplace_country_map.get(marketplace_id)
        if base_shipping_fee is not None and country_code:
            if marketplace_id not in pricing_rule_cache:
                pricing_rule_cache[marketplace_id] = get_pricing_master_rule(user_id=user_id, country_code=country_code)
            rule = pricing_rule_cache[marketplace_id]
            fuel_rate = float(rule.get("fuel_surcharge_rate") or 0) / 100
            outsource = float(rule.get("shipping_outsource_cost") or 0)
            packing = float(rule.get("extra_cost") or 0)
            row["predicted_shipping_fee"] = base_shipping_fee * (1 + fuel_rate) + outsource + packing
        else:
            row["predicted_shipping_fee"] = base_shipping_fee

    # --- 実利益（決済レポートの入金額 − 仕入価格 − 送料）。dims/marketplace_idが解決できなかった行にも
    #     予測送料無しで代行会社確定送料だけは反映したいため、上のループとは別パスで全行に適用する。 ---
    settlement_summary = get_order_settlement_summary(user_id)
    fx_cache = {}

    # 決済トランザクションはorder_id単位のため、1注文に商品が複数(=order_item_idが複数)あると
    # 同じ入金額が重複適用されてしまう。販売価格(item_price)の比率で按分する重みを先に計算する
    # （item_priceが全商品分揃わない場合は商品数で均等割り）。
    order_id_groups = {}
    for row in rows:
        order_id_groups.setdefault(row.get("order_id"), []).append(row)

    settlement_weights = {}
    for order_id, group in order_id_groups.items():
        if len(group) <= 1:
            for row in group:
                settlement_weights[row["order_item_id"]] = 1.0
            continue
        prices = [row.get("item_price") for row in group]
        if all(p is not None for p in prices) and sum(prices) > 0:
            total = sum(prices)
            for row, price in zip(group, prices):
                settlement_weights[row["order_item_id"]] = price / total
        else:
            equal_weight = 1.0 / len(group)
            for row in group:
                settlement_weights[row["order_item_id"]] = equal_weight

    for row in rows:
        _apply_settlement_profit(
            row,
            settlement_summary=settlement_summary,
            fx_cache=fx_cache,
            settlement_weight=settlement_weights.get(row["order_item_id"], 1.0),
        )

    # --- リピーター判定・返品セキュリティメモの反映（買い手＝住所キーで突き合わせ） ---
    buyer_history_counts = _load_buyer_history_counts(user_id)
    buyer_security_notes = _load_buyer_security_notes(user_id)
    for row in rows:
        buyer_key = _normalize_buyer_key(row.get("ship_postal_code"), row.get("ship_address_1"))
        row["repeat_buyer_count"] = buyer_history_counts.get(buyer_key, 0) if buyer_key else 0
        row["security_notes"] = buyer_security_notes.get(buyer_key, []) if buyer_key else []

    return rows


# --- ▼ SECTION 05-3: リピーター件数・返品セキュリティメモの一括取得（買い手キー単位） ▼ ---
# list_orders_with_calc()の中で行ごとにクエリを投げないよう、既存のsettlement_summary一括取得
# （SECTION 04-2b付近）と同じ考え方で、ユーザー全体を1クエリずつまとめて取得する。
def _load_buyer_history_counts(user_id: int) -> dict:
    conn = get_conn("a_orbit_buyer_history.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT buyer_key, COUNT(*) AS cnt
        FROM orbit_buyer_history
        WHERE user_id = %s AND buyer_key IS NOT NULL
        GROUP BY buyer_key
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {r["buyer_key"]: r["cnt"] for r in rows}


def _load_buyer_security_notes(user_id: int) -> dict:
    conn = get_conn("a_orbit_buyer_security_notes.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT buyer_key, note, created_at
        FROM orbit_buyer_security_notes
        WHERE user_id = %s
        ORDER BY created_at ASC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()

    # 発注管理タブの「バイヤーメモ」セクションで本文＋日時を表示するため dict のリストで返す
    # （従来は本文文字列のみ。⚠要注意バッジ側も .note を参照するよう更新済み）。
    notes_by_key = {}
    for r in rows:
        notes_by_key.setdefault(r["buyer_key"], []).append(
            {"note": r["note"], "created_at": r["created_at"]}
        )
    return notes_by_key


# --- ▼ SECTION 05-1b: 買い手履歴タブの一覧表示（過去に買ったことがあるかどうかのチェック専用） ▼ ---
def list_buyer_history(user_id: int) -> list:
    conn = get_conn("a_orbit_buyer_history.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT order_item_id, order_id, agent_serial_no, purchase_date,
               buyer_name, recipient_name, ship_address_1, ship_city, ship_state,
               ship_postal_code, ship_country, sku, product_name, quantity_purchased,
               source, archived_at, created_at
        FROM orbit_buyer_history
        WHERE user_id = %s
        ORDER BY agent_serial_no ASC NULLS LAST, id DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_security_notes(user_id: int) -> list:
    conn = get_conn("a_orbit_buyer_security_notes.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, buyer_key, recipient_name, ship_address_1, ship_postal_code,
               order_id, order_item_id, note, created_at
        FROM orbit_buyer_security_notes
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# --- ▼ SECTION 05-2: 販売額・手数料見積り結果の機体間受け渡し（ATLAS(AU)⇔ZSSS(CA/US)は別々のDBのため） ▼ ---
# AU注文の販売価格・手数料見積りはAUアカウントの認証情報を持つATLAS側でしか取得できない。
# 基本の注文データ自体は通常の注文レポートCSV取込で双方に入れられるので、ここではATLAS側だけで
# 取得できた項目（item_price・shipping_price・order_currency・fee_estimate_*）だけを受け渡す。
FEE_DATA_COLUMNS = [
    "order_item_id", "item_price", "shipping_price", "order_currency",
    "fee_estimate_amount", "fee_estimate_currency", "fee_estimate_fetched_at",
]


def export_fee_data_csv(user_id: int) -> str:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {", ".join(FEE_DATA_COLUMNS)}
        FROM orbit_orders
        WHERE user_id = %s AND (item_price IS NOT NULL OR fee_estimate_amount IS NOT NULL)
        ORDER BY id
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    output.write('﻿')  # UTF-8 BOM（無いとExcelがShift-JIS扱いして日本語が文字化けする）
    writer = csv.writer(output)
    writer.writerow(FEE_DATA_COLUMNS)
    for r in rows:
        writer.writerow([r.get(c) for c in FEE_DATA_COLUMNS])
    return output.getvalue()


def parse_fee_data_csv(text: str) -> list:
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        if not raw.get("order_item_id"):
            continue
        row = {"order_item_id": raw["order_item_id"].strip()}
        for c in ("item_price", "shipping_price", "fee_estimate_amount"):
            value = raw.get(c)
            row[c] = float(value) if value not in (None, "") else None
        for c in ("order_currency", "fee_estimate_currency", "fee_estimate_fetched_at"):
            value = raw.get(c)
            row[c] = value.strip() if value else None
        rows.append(row)
    return rows


def import_fee_data(user_id: int, rows: list) -> int:
    if not rows:
        return 0

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    updated = 0
    for row in rows:
        cur.execute(
            """
            UPDATE orbit_orders
            SET item_price = %s, shipping_price = %s, order_currency = %s,
                fee_estimate_amount = %s, fee_estimate_currency = %s, fee_estimate_fetched_at = %s,
                updated_at = %s
            WHERE user_id = %s AND order_item_id = %s
            """,
            (
                row.get("item_price"), row.get("shipping_price"), row.get("order_currency"),
                row.get("fee_estimate_amount"), row.get("fee_estimate_currency"), row.get("fee_estimate_fetched_at"),
                now, user_id, row["order_item_id"],
            ),
        )
        updated += cur.rowcount

    conn.commit()
    conn.close()
    return updated


# --- ▼ SECTION 06: JAN・仕入価格の手入力更新 ▼ ---
MANUAL_FIELDS = [
    "jan_code", "purchase_price",
    "request_date", "shipping_type", "tracking_number", "remarks", "remarks_2", "remarks_3",
    "supplier", "supplier_order_number", "supplier_shop_name", "procurement_date", "arrival_date",
    "shipped_completed",
    "invoice_saved", "points", "purchased",
    "manual_length_cm", "manual_width_cm", "manual_height_cm", "manual_weight_kg",
    "product_name_override", "recipient_name_override",
    "ship_address_1_override", "ship_address_2_override", "ship_address_3_override",
    "buyer_phone_number_override", "buyer_phone_extension_override", "ship_state_override",
]

NUMERIC_MANUAL_FIELDS = {
    "purchase_price", "points",
    "manual_length_cm", "manual_width_cm", "manual_height_cm", "manual_weight_kg",
}

# 備考は 1/2/3 に分割入力。ZSSS_RAW へは空でないものだけ半角スペースで連結して1列(remarks)にする。
REMARKS_FIELDS = ["remarks", "remarks_2", "remarks_3"]


def _combine_remarks(row) -> str:
    parts = [str(row.get(f)).strip() for f in REMARKS_FIELDS if row.get(f) not in (None, "")]
    return " ".join(p for p in parts if p)


def update_manual_fields(user_id: int, order_item_id: str, fields: dict):
    allowed = {k: v for k, v in fields.items() if k in MANUAL_FIELDS}
    if not allowed:
        return

    # 依頼日(発注管理)は「仕入れした時点で代行会社へ依頼する」運用のため、仕入日(仕入れ管理)を
    # 入力した時点でそのまま反映する（JANと同じく仕入れ管理側が発生源で、発注管理側は読取専用）。
    if "procurement_date" in allowed:
        allowed["request_date"] = allowed["procurement_date"]

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


# --- ▼ SECTION 06-1: 注文の削除（行ごと／全件リセット） ▼ ---
def delete_order(user_id: int, order_item_id: str) -> int:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM orbit_orders WHERE user_id = %s AND order_item_id = %s",
        (user_id, order_item_id),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


def delete_all_orders(user_id: int) -> int:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM orbit_orders WHERE user_id = %s", (user_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


# --- ▼ SECTION 06-1b: アーカイブ候補の検出・実行（決済確定＋出荷完了の注文をFBMバイヤー履歴へ移動） ▼ ---
# 「決済確定」はorbit_settlement_linesに実績行があるかどうかで判定する。時間ベースの自動実行はせず、
# 半自動（候補を確認してからボタンで実行）にする：セラーセントラルの決済レポートをいつ・どの期間分
# 取り込むかで、事実上のアーカイブ対象期間をユーザー側でコントロールできるようにするため。
def list_archive_candidates(user_id: int) -> list:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT order_item_id, order_id, sku, product_name, recipient_name, purchase_date
        FROM orbit_orders
        WHERE user_id = %s AND shipped_completed = 1
        """,
        (user_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    settlement_summary = get_order_settlement_summary(user_id)
    return [r for r in rows if r.get("order_id") in settlement_summary]


# アーカイブは注文明細の「移動」であって削除ではない。ただしorbit_buyer_historyが持つのは
# Amazon注文レポートの生データ（IMPORT_COLUMNS）＋N番（agent_serial_no）だけ＝過去の購入価格・
# 送料・利益等ZSSS側の計算結果は引き継がない（「この住所は過去に買ったことがあるか」だけを
# チェックするための台帳のため）。仕入額・トラッキング番号・代行会社とのやり取り等の全データは
# 別途orbit_procurement_historyへ全列そのまま退避する（領収書発行・経理・返品対応時の参照用）。
_BUYER_HISTORY_ARCHIVE_COLUMNS = IMPORT_COLUMNS + ["agent_serial_no"]
_PROCUREMENT_HISTORY_COLUMNS = [c for c in ORBIT_ORDERS_COLUMNS if c != "id"]


def archive_orders(user_id: int, order_item_ids: list) -> int:
    if not order_item_ids:
        return 0

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cols_sql = ", ".join(["order_item_id"] + [c for c in _PROCUREMENT_HISTORY_COLUMNS if c != "order_item_id"])
    cur.execute(
        f"SELECT {cols_sql} FROM orbit_orders WHERE user_id = %s AND order_item_id = ANY(%s)",
        (user_id, order_item_ids),
    )
    rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        conn.close()
        return 0

    now = datetime.utcnow().isoformat()

    buyer_history_insert_cols = ["user_id"] + _BUYER_HISTORY_ARCHIVE_COLUMNS + ["buyer_key", "source", "archived_at", "created_at"]
    buyer_history_col_list = ", ".join(buyer_history_insert_cols)
    buyer_history_placeholders = ", ".join(["%s"] * len(buyer_history_insert_cols))
    buyer_history_sql = f"""
        INSERT INTO orbit_buyer_history ({buyer_history_col_list})
        VALUES ({buyer_history_placeholders})
        ON CONFLICT (user_id, order_item_id) DO NOTHING
    """

    procurement_insert_cols = _PROCUREMENT_HISTORY_COLUMNS + ["archived_at"]
    procurement_col_list = ", ".join(procurement_insert_cols)
    procurement_placeholders = ", ".join(["%s"] * len(procurement_insert_cols))
    procurement_sql = f"""
        INSERT INTO orbit_procurement_history ({procurement_col_list})
        VALUES ({procurement_placeholders})
        ON CONFLICT (user_id, order_item_id) DO NOTHING
    """

    for row in rows:
        buyer_key = _normalize_buyer_key(row.get("ship_postal_code"), row.get("ship_address_1"))
        buyer_history_values = [user_id] + [row.get(c) for c in _BUYER_HISTORY_ARCHIVE_COLUMNS] + [buyer_key, "archived", now, now]
        cur.execute(buyer_history_sql, buyer_history_values)

        procurement_values = [row.get(c) for c in _PROCUREMENT_HISTORY_COLUMNS] + [now]
        cur.execute(procurement_sql, procurement_values)

    archived_ids = [r["order_item_id"] for r in rows]
    cur.execute(
        "DELETE FROM orbit_orders WHERE user_id = %s AND order_item_id = ANY(%s)",
        (user_id, archived_ids),
    )
    archived = cur.rowcount

    conn.commit()
    conn.close()

    return archived


# --- ▼ SECTION 06-1c: 返品・セキュリティメモの追加（買い手＝住所単位） ▼ ---
# 注文明細（order_item_id）がorbit_orders・orbit_buyer_historyのどちらにあっても追記できる
# （アーカイブ後、何ヶ月経ってから返品が来ても記録できるようにするため）。
def add_security_note(user_id: int, order_item_id: str, note: str) -> bool:
    note = (note or "").strip()
    if not order_item_id or not note:
        return False

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT order_id, recipient_name, ship_address_1, ship_postal_code "
        "FROM orbit_orders WHERE user_id = %s AND order_item_id = %s",
        (user_id, order_item_id),
    )
    source_row = cur.fetchone()
    conn.close()

    if not source_row:
        conn = get_conn("a_orbit_buyer_history.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT order_id, recipient_name, ship_address_1, ship_postal_code "
            "FROM orbit_buyer_history WHERE user_id = %s AND order_item_id = %s",
            (user_id, order_item_id),
        )
        source_row = cur.fetchone()
        conn.close()

    if not source_row:
        return False

    buyer_key = _normalize_buyer_key(source_row.get("ship_postal_code"), source_row.get("ship_address_1"))
    if not buyer_key:
        return False

    now = datetime.utcnow().isoformat()
    conn = get_conn("a_orbit_buyer_security_notes.db")
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orbit_buyer_security_notes
            (user_id, buyer_key, recipient_name, ship_address_1, ship_postal_code,
             order_id, order_item_id, note, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id, buyer_key, source_row.get("recipient_name"), source_row.get("ship_address_1"),
            source_row.get("ship_postal_code"), source_row.get("order_id"), order_item_id,
            note, now,
        ),
    )
    conn.commit()
    conn.close()
    return True


# --- ▼ SECTION 06-2: 代行会社連番（Nから始まる連番）の設定 ▼ ---
# 対象行に開始番号を設定し、以降は指定された並び順で連番を振り直す。
# ordered_ids（画面側で現在表示・ソートされている順）が渡されればそれを使い、
# 無ければ既定の「システムに取り込まれた順（id昇順）」を使う
# （受注日順だと、AU分を後から取り込んだ時に既存の連番の途中へ割り込んでしまうため）。
def set_agent_serial_no(user_id: int, order_item_id: str, start_value: int, ordered_ids: list = None) -> int:
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()

    if not ordered_ids:
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
    output.write('﻿')  # UTF-8 BOM（無いとExcelがShift-JIS扱いして日本語が文字化けする）
    writer = csv.writer(output)
    writer.writerow(EXPORT_COLUMNS)

    # 電話番号(国番号除去)・州(正式表記)は自動補正、商品名・宛名・住所1〜3は手修正(*_override)された
    # 値があればそちらを優先。いずれも代行会社シート側の制約のため、貼り付け用CSVにも反映する。
    export_value_overrides = {
        "buyer_phone_number": "buyer_phone_number_effective",
        "ship_state": "ship_state_effective",
        "product_name": "product_name_effective",
        "recipient_name": "recipient_name_effective",
        "ship_address_1": "ship_address_1_effective",
        "ship_address_2": "ship_address_2_effective",
        "ship_address_3": "ship_address_3_effective",
    }

    # JANコード・電話番号・order-item-idなど桁数の多い/先頭0ありの数字文字列は、Excelが数値と誤認識すると
    # 指数表記(1.23E+12)になったり先頭0が消えたりする。="123"形式にして文字列として固定する。
    for r in rows:
        row_values = []
        for c in EXPORT_COLUMNS:
            value = r.get(export_value_overrides.get(c, c))
            text = "" if value is None else str(value)
            if c in NUMERIC_TEXT_EXPORT_COLUMNS and text.isdigit():
                text = f'="{text}"'
            row_values.append(text)
        writer.writerow(row_values)

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


# --- ▼ SECTION 07-2: 管理シート（書き出し先タブ）への書き出し ▼ ---
# 手動CSVコピペの置き換え。ORBITが持っている項目を EXPORT_COLUMNS の並びで、利用者が設定した
# スプレッドシート／タブへ書く（URL・タブ名とも必須。タブは事前に作成しておく前提）。
# 書き出し先タブ → 利用者の本番タブへはシート内の数式で転記する運用。
#
# 【N番 upsert 方式】以前は「毎回全消し＋全貼り直し」だったが、出荷通知が終わるまでは
# 仕入れ内容・代行会社への連絡内容が頻繁に変わるため、その都度反映しつつ、通知済みの行は
# 確定として固定したい。そこで：
#   1. ZSSS_RAW のA列(N番)を読み、N番→行番号 の対応表を作る
#   2. 書き出し対象 = shipped_completed=0（出荷通知まだ）かつ N番あり の注文
#      - 同じN番の行があれば その行の A〜(最終列) だけ全項目上書き
#      - なければ 既存データの最終行の下に追加
#   3. shipped_completed=1（出荷通知済み）はどの書き込み範囲にも入れない → 既存行は凍結
#      （通知解除で 0 に戻れば次回また上書き対象になる）
#   4. N番なし（採番ミス）はスキップ。ORBITから消えた／アーカイブ済みのN番の行は放置。
# ※ export_notify_csv と違い notified_at は更新しない（CSV出力＝送信済みの目印を壊さないため）。
_RAW_VALUE_OVERRIDES = {
    "buyer_phone_number": "buyer_phone_number_effective",
    "ship_state": "ship_state_effective",
    "product_name": "product_name_effective",
    "recipient_name": "recipient_name_effective",
    "ship_address_1": "ship_address_1_effective",
    "ship_address_2": "ship_address_2_effective",
    "ship_address_3": "ship_address_3_effective",
}


# ZSSS_RAW に出す数値は「本物の数値」で書き込む（文字列にすると代行会社シート側で
# 書式(0"kg" 等)が効かず、SUM等の計算もできなくなるため）。丸め方は利用者指定：
#   ・円の列        → 整数（切り上げ）        例) 17074
#   ・サイズ/現地通貨等 → 小数第2位（切り上げ）  例) 10.05, 11.5（"11.50"表示はシートの書式で）
# 「切り上げ」は正の値を上へ。負の利益(profit_jpy 等)は +∞方向＝ゼロ方向へ丸まるが許容。
# ※ JAN・追跡番号・電話番号など（NUMERIC_TEXT_EXPORT_COLUMNS）は数値化しない（指数表記・
#   先頭0落ち防止）。これらは元々DB上TEXTなのでここには来ないが、保険としてガードする。
_RAW_JPY_INT_KEYS = frozenset({
    "invoice_price_jpy", "predicted_shipping_fee",
    "net_proceeds_used_jpy", "sale_price_used_jpy",
    "profit_jpy", "shipping_cost_used", "purchase_price",
})
_RAW_CEIL_EPS = 1e-6  # 10.05 が浮動小数誤差で 10.06 に繰り上がるのを防ぐ吸収幅


def _raw_number(value, col):
    """float/Decimal を丸めて数値(int/float)で返す。NaN は空文字。"""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return str(value)
    if x != x:  # NaN
        return ""
    if col in _RAW_JPY_INT_KEYS:
        return math.ceil(x - _RAW_CEIL_EPS)
    return math.ceil(x * 100 - _RAW_CEIL_EPS) / 100


def _raw_cell(r, col):
    """1セルぶんの値。数値は数値型、フラグは真偽型、それ以外は文字列で返す。"""
    # remarks は 備考1/2/3 の連結値を出す（発注管理タブでは分割入力、ZSSS_RAW では1列）。
    if col == "remarks":
        return _combine_remarks(r)
    # N番はDB上は数字のみ保持だが、代行会社シート/マスターシートの慣習は "N5187" の接頭辞付き
    # （数値誤認防止のテキストキー）。ZSSS_RAW へ吐き出すときに "N" を付ける。未採番は空のまま。
    if col == "agent_serial_no":
        value = r.get("agent_serial_no")
        return "" if value in (None, "") else f"N{value}"
    value = r.get(_RAW_VALUE_OVERRIDES.get(col, col))
    if value is None or value == [] or value == {}:
        return ""
    if col in NUMERIC_TEXT_EXPORT_COLUMNS:
        return str(value)  # 桁数の多い数字の羅列は文字列のまま
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (float, Decimal)):
        return _raw_number(value, col)
    return str(value)


def _raw_sheet_row(r, columns) -> list:
    """注文1件を columns の並びで1行ぶんの文字列リストにする（Noneは空文字）。"""
    return [_raw_cell(r, c) for c in columns]


def _a1_col(n: int) -> str:
    """1始まりの列番号をA1記法の列名に（1→A, 26→Z, 27→AA, 57→BE）。"""
    name = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


def push_orders_to_raw_sheet(user_id: int) -> dict:
    settings = get_raw_sheet_settings(user_id)
    if not settings["spreadsheet_url"]:
        raise RuntimeError("書き出し先スプレッドシートのURLが未設定です（発注管理タブの設定欄で保存してください）")
    if not (settings["sheet_name"] or "").strip():
        raise RuntimeError("書き込み先のタブ名が未設定です（発注管理タブの設定欄で保存してください）")

    spreadsheet_id = _extract_spreadsheet_id(settings["spreadsheet_url"])
    sheet_name = settings["sheet_name"].strip()

    # A1記法ではシート名をシングルクォートで囲む（スペースや記号入りでも解釈できるように。
    # 名前に含まれる ' は '' にエスケープする）。安全な名前を囲んでも無害。
    quoted = "'" + sheet_name.replace("'", "''") + "'"

    orders = list_orders_with_calc(user_id)
    columns = _raw_sheet_columns_for(orders)
    last_col = _a1_col(len(columns))

    # --- 既存シートの A列(N番) を軽量取得して N番→行番号(1始まり) の対応表を作る ---
    # 末尾の空行はAPI側で落ちるので len(existing) が「最後にデータのある行」。
    try:
        existing = fetch_sheet_range(user_id, spreadsheet_id, f"{quoted}!A:A")
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status == 404:
            raise RuntimeError("スプレッドシートが見つかりません。書き出し先URLを確認してください。")
        raise RuntimeError(
            f"書き出し先タブ「{sheet_name}」を読めませんでした。"
            f"タブ名が正しいか、そのタブが存在するか確認してください。"
        )
    # A列が「N5187」「5187」のように"シリアルそのもの"の行だけを対象にする。
    # ヘッダー上に足した説明行（例「最終更新 2026/9/3」）や列位置メモ（"56" "57" 等）を
    # 誤ってシリアル扱いしないよう、Nプレフィックス任意＋3桁以上の数字のみ許可する
    # （実際のN番は4桁の 5xxx 台。1〜2桁のメモ数字は弾く）。
    row_by_serial = {}
    for i, cells in enumerate(existing):
        raw = str((cells[0] if cells else "") or "").strip()
        if not re.fullmatch(r"[Nn]?\s*\d{3,}", raw):
            continue
        serial = _parse_agent_serial_no(raw)
        if serial is not None and serial not in row_by_serial:
            row_by_serial[serial] = i + 1

    updates = []   # batch_update_sheet_values 用: [{"range": ..., "values": [row]}]
    appends = []   # 末尾追加ぶんの行データ
    header = list(columns)
    if not existing:
        header_row, next_row = 1, 2
    else:
        next_row = len(existing) + 1
        # 見出し行はデータ行の1つ上（ヘッダーの上に説明行を足していても崩れない）。
        # データがまだ無ければ、既存の最終行（＝見出しらしき行）を見出し行とみなす。
        header_row = (min(row_by_serial.values()) - 1) if row_by_serial else len(existing)
    if header_row >= 1:
        # 毎回 columns で見出しを貼り直す（列を増やしたぶんヘッダーも合わせる）。
        updates.append({"range": f"{quoted}!A{header_row}:{last_col}{header_row}", "values": [header]})

    n_update = n_append = skip_notified = skip_no_serial = 0
    for r in orders:
        if int(r.get("shipped_completed") or 0) == 1:
            skip_notified += 1
            continue
        serial = _parse_agent_serial_no(r.get("agent_serial_no"))
        if serial is None:
            skip_no_serial += 1
            continue
        line = _raw_sheet_row(r, columns)
        rownum = row_by_serial.get(serial)
        if rownum:
            updates.append({"range": f"{quoted}!A{rownum}:{last_col}{rownum}", "values": [line]})
            n_update += 1
        else:
            appends.append(line)
            n_append += 1

    if updates:
        batch_update_sheet_values(user_id, spreadsheet_id, updates)
    if appends:
        end_row = next_row + len(appends) - 1
        update_sheet_values(user_id, spreadsheet_id, f"{quoted}!A{next_row}:{last_col}{end_row}", appends)

    return {
        "updated": n_update,
        "appended": n_append,
        "skipped_notified": skip_notified,
        "skipped_no_serial": skip_no_serial,
        "columns": len(columns),
        "sheet_name": sheet_name,
    }


# --- ▼ SECTION 08: 代行会社シートからの読み戻し（N番号でorbit_ordersと突き合わせる） ▼ ---
# 依頼書シートの列位置（0始まり）。A=SLCN管理No(0), B=依頼日(1), ... U=配送エリア(20)。
DISPATCH_COLUMN_INDEX = {
    "agent_tracking_number": 6,         # G列
    "agent_thankyou_letter": 9,         # J列
    "agent_option_content": 10,         # K列
    "agent_option_fee": 11,             # L列
    "agent_non_deliverable_weight": 12, # M列
    "agent_shipping_weight": 13,        # N列
    "agent_weight_recorded_date": 14,   # O列（日付が入れば出荷済み）
    "agent_confirmed_weight": 15,       # P列
    "agent_deadline": 16,               # Q列
    "agent_status": 17,                 # R列
    "agent_shipping_fee": 18,           # S列
    "agent_shipping_fee_total": 19,     # T列
    "agent_delivery_area": 20,          # U列
}


def _parse_agent_serial_no(value):
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


def sync_dispatch_sheet_status(user_id: int) -> dict:
    preview = fetch_dispatch_sheet_preview(user_id)
    sheet_rows = preview.get("rows", [])

    sheet_by_serial = {}
    for row in sheet_rows:
        serial = _parse_agent_serial_no(row[0] if row else None)
        if serial is not None:
            sheet_by_serial[serial] = row

    if not sheet_by_serial:
        return {"matched": 0, "updated": 0}

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT order_item_id, agent_serial_no FROM orbit_orders WHERE user_id = %s AND agent_serial_no IS NOT NULL",
        (user_id,),
    )
    orbit_rows = cur.fetchall()

    now = datetime.utcnow().isoformat()
    matched = 0

    for orbit_row in orbit_rows:
        sheet_row = sheet_by_serial.get(orbit_row["agent_serial_no"])
        if not sheet_row:
            continue

        matched += 1

        set_parts = []
        values = []
        for field, idx in DISPATCH_COLUMN_INDEX.items():
            set_parts.append(f"{field} = %s")
            values.append(sheet_row[idx] if len(sheet_row) > idx and sheet_row[idx] else None)

        set_parts.append("agent_synced_at = %s")
        set_parts.append("updated_at = %s")
        values.extend([now, now, user_id, orbit_row["order_item_id"]])

        cur.execute(
            f"UPDATE orbit_orders SET {', '.join(set_parts)} WHERE user_id = %s AND order_item_id = %s",
            values,
        )

    conn.commit()
    conn.close()

    return {"matched": matched, "updated": matched}
