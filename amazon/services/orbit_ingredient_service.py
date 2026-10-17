# ==========================================
# ファイル名: amazon/services/orbit_ingredient_service.py
# 目的: ORBIT「成分台帳」サブタブ ― 代行会社へ申告する成分（電池の種類も含む）をASINごとに記録し、
#       台帳にあるASINの注文は発注管理の備考1の末尾へ成分を自動で書き足す（国を問わず）。
#       説明（発送不可など）が入っている商品は発注管理で赤字の警告を出す。
#       台帳の元データは以前スプレッドシートで管理していたので、そのシートから取り込める。
# ==========================================

import re
from datetime import datetime

from amazon.db import get_conn
from amazon.services.google_sheets_service import _extract_spreadsheet_id, fetch_sheet_range

_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
LEDGER_FIELDS = ["product_name", "genre", "jan_code", "note", "ingredients"]


# --- ▼ SECTION 01: 取込元シートの設定（依頼書シート設定と同じ1行に相乗り） ▼ ---
def get_ingredient_sheet_settings(user_id: int) -> dict:
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ingredient_sheet_url, ingredient_sheet_name FROM orbit_dispatch_sheet_settings WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
        return {
            "spreadsheet_url": (row["ingredient_sheet_url"] if row and row.get("ingredient_sheet_url") else ""),
            "sheet_name": (row["ingredient_sheet_name"] if row and row.get("ingredient_sheet_name") else ""),
        }
    finally:
        conn.close()


def save_ingredient_sheet_settings(user_id: int, spreadsheet_url: str, sheet_name: str):
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute("""
            INSERT INTO orbit_dispatch_sheet_settings (user_id, ingredient_sheet_url, ingredient_sheet_name, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                ingredient_sheet_url = EXCLUDED.ingredient_sheet_url,
                ingredient_sheet_name = EXCLUDED.ingredient_sheet_name,
                updated_at = EXCLUDED.updated_at
        """, (user_id, spreadsheet_url, sheet_name, now, now))
        conn.commit()
    finally:
        conn.close()


# --- ▼ SECTION 02: 台帳の読み込み ▼ ---
def normalize_asin(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def remarks_text(ingredients) -> str:
    """備考1へ書く形。備考1は1行の入力欄なので、シートのセル内改行は半角スペースにする。"""
    return " ".join(line.strip() for line in str(ingredients or "").splitlines() if line.strip())


def load_ingredient_map(user_id: int) -> dict:
    """{asin: {"note", "ingredients"}}（発注管理の印・警告と備考1の書き足し用）"""
    conn = get_conn("a_orbit_ingredient_ledger.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT asin, note, ingredients FROM orbit_ingredient_ledger WHERE user_id = %s",
            (user_id,),
        )
        return {r["asin"]: {"note": r["note"], "ingredients": r["ingredients"]} for r in cur.fetchall()}
    finally:
        conn.close()


def _load_shipped_counts(user_id: int) -> dict:
    """{asin: 出荷通知済みの注文数}（発注管理に残っている分＋アーカイブ済み）"""
    from amazon.services.orbit_order_service import _load_listed_items_asin_map, _resolve_asin
    listed_items_map = _load_listed_items_asin_map(user_id)
    counts = {}
    for table, db_name in (
        ("orbit_orders", "a_orbit_orders.db"),
        ("orbit_procurement_history", "a_orbit_procurement_history.db"),
    ):
        conn = get_conn(db_name)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT sku FROM {table} WHERE user_id = %s AND shipped_completed = 1", (user_id,))
            for r in cur.fetchall():
                asin = _resolve_asin(r["sku"], listed_items_map)
                if asin:
                    counts[asin] = counts.get(asin, 0) + 1
        finally:
            conn.close()
    return counts


def list_ingredient_ledger(user_id: int) -> list:
    conn = get_conn("a_orbit_ingredient_ledger.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT asin, product_name, genre, jan_code, note, ingredients, sheet_shipped, updated_at "
            "FROM orbit_ingredient_ledger WHERE user_id = %s ORDER BY id ASC",
            (user_id,),
        )
        items = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    shipped_counts = _load_shipped_counts(user_id)
    for item in items:
        item["shipped_count"] = shipped_counts.get(item["asin"], 0)
        item["sheet_shipped"] = bool(item.get("sheet_shipped"))
    return items


# --- ▼ SECTION 03: 台帳の追加・修正・削除（画面から） ▼ ---
def save_ingredient_item(user_id: int, data: dict) -> dict:
    asin = normalize_asin(data.get("asin"))
    if not _ASIN_PATTERN.match(asin):
        raise ValueError("ASINは英数字10桁で入力してください")
    values = {f: (str(data.get(f) or "").strip() or None) for f in LEDGER_FIELDS}

    conn = get_conn("a_orbit_ingredient_ledger.db")
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cols = ", ".join(LEDGER_FIELDS)
        placeholders = ", ".join(["%s"] * len(LEDGER_FIELDS))
        updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in LEDGER_FIELDS)
        cur.execute(f"""
            INSERT INTO orbit_ingredient_ledger (user_id, asin, {cols}, created_at, updated_at)
            VALUES (%s, %s, {placeholders}, %s, %s)
            ON CONFLICT (user_id, asin) DO UPDATE SET {updates}, updated_at = EXCLUDED.updated_at
        """, [user_id, asin] + [values[f] for f in LEDGER_FIELDS] + [now, now])
        conn.commit()
    finally:
        conn.close()

    return sync_ingredient_remarks(user_id, asins=[asin])


def delete_ingredient_item(user_id: int, asin: str) -> dict:
    asin = normalize_asin(asin)
    conn = get_conn("a_orbit_ingredient_ledger.db")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM orbit_ingredient_ledger WHERE user_id = %s AND asin = %s", (user_id, asin))
        conn.commit()
    finally:
        conn.close()
    # 台帳から消したASINの注文は、自動で書き足した成分を備考1から外す
    return sync_ingredient_remarks(user_id, asins=[asin])


# --- ▼ SECTION 04: シートからの取込 ▼ ---
# 見出し行（「ASIN」と書かれたセルがある行）の文字で列を探すので、列の並びが変わっても読める。
# シートにあるASINは台帳をシートの内容で上書きし、シートに無いASIN（画面で足した分）は残す。
_SHEET_HEADER_KEYS = {
    "asin": lambda h: h.upper() == "ASIN",
    "product_name": lambda h: "商品名" in h,
    "genre": lambda h: "ジャンル" in h,
    "jan_code": lambda h: "JAN" in h.upper(),
    "note": lambda h: "説明" in h,
    "ingredients": lambda h: "成分" in h,
    "sheet_shipped": lambda h: "出荷実績" in h,
}


def _quote_sheet_name(sheet_name: str) -> str:
    # 「FDA&電池関係」のように記号を含むタブ名は '...' で囲まないと範囲指定として読めない
    return "'" + sheet_name.replace("'", "''") + "'"


def import_ingredient_sheet(user_id: int) -> dict:
    settings = get_ingredient_sheet_settings(user_id)
    if not settings["spreadsheet_url"] or not settings["sheet_name"]:
        raise ValueError("取込元のスプレッドシートURLとタブ名を設定してください")
    spreadsheet_id = _extract_spreadsheet_id(settings["spreadsheet_url"])

    rows = fetch_sheet_range(user_id, spreadsheet_id, f"{_quote_sheet_name(settings['sheet_name'])}!A1:Z")

    header_index = next(
        (i for i, row in enumerate(rows[:20]) if any(str(c).strip().upper() == "ASIN" for c in row)), None
    )
    if header_index is None:
        raise ValueError("見出しに「ASIN」の列が見つかりません。タブ名を確認してください")
    header = [str(c).strip() for c in rows[header_index]]
    col_index = {}
    for key, match in _SHEET_HEADER_KEYS.items():
        idx = next((i for i, h in enumerate(header) if h and match(h)), None)
        if idx is not None:
            col_index[key] = idx
    if "ingredients" not in col_index:
        raise ValueError("見出しに「成分」の列が見つかりません")

    def cell(row, key):
        idx = col_index.get(key)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    merged = {}
    skipped = 0
    for row in rows[header_index + 1:]:
        if not any(str(c).strip() for c in row):
            continue
        asin = normalize_asin(cell(row, "asin"))
        if not _ASIN_PATTERN.match(asin):
            skipped += 1
            continue
        item = merged.setdefault(asin, {"sheet_shipped": 0})
        # 同じASINが複数行あれば、下の行の空でない値で上書きする
        for f in LEDGER_FIELDS:
            v = cell(row, f)
            if v:
                item[f] = v
        if cell(row, "sheet_shipped").upper() == "TRUE":
            item["sheet_shipped"] = 1

    conn = get_conn("a_orbit_ingredient_ledger.db")
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cols = LEDGER_FIELDS + ["sheet_shipped"]
        col_sql = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in cols)
        for asin, item in merged.items():
            cur.execute(f"""
                INSERT INTO orbit_ingredient_ledger (user_id, asin, {col_sql}, created_at, updated_at)
                VALUES (%s, %s, {placeholders}, %s, %s)
                ON CONFLICT (user_id, asin) DO UPDATE SET {updates}, updated_at = EXCLUDED.updated_at
            """, [user_id, asin] + [item.get(f) for f in cols] + [now, now])
        conn.commit()
    finally:
        conn.close()

    result = sync_ingredient_remarks(user_id)
    result.update({"imported": len(merged), "skipped": skipped})
    return result


# --- ▼ SECTION 05: 発注管理の備考1への成分の書き足し ▼ ---
# 対象は出荷通知前（shipped_completed≠1）の注文だけ。ZSSS_RAW への書き出しも出荷通知前の行だけを
# 上書きするので、それと揃える（通知済みの注文の備考1は過去の記録として触らない）。
# 書き足した文字列は ingredient_remarks_auto に控え、次回はそれを探して置換・削除する
# （同梱表記と同じ仕組み。手で書いた文には触らず、自動部分を手で書き換えて見つからない行は触らずに警告）。
def sync_ingredient_remarks(user_id: int, order_item_ids=None, asins=None, cur=None) -> dict:
    from amazon.services.orbit_order_service import (
        _load_listed_items_asin_map, _resolve_asin, _replace_bundle_remarks,
    )

    own_conn = None
    if cur is None:
        own_conn = get_conn("a_orbit_orders.db")
        cur = own_conn.cursor()
    try:
        sql = (
            "SELECT order_item_id, sku, agent_serial_no, remarks, ingredient_remarks_auto FROM orbit_orders "
            "WHERE user_id = %s AND COALESCE(shipped_completed, 0) <> 1"
        )
        params = [user_id]
        if order_item_ids is not None:
            if not order_item_ids:
                return {"updated": 0, "remarks_mismatch": []}
            sql += " AND order_item_id = ANY(%s)"
            params.append(list(order_item_ids))
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]

        ledger = load_ingredient_map(user_id)
        listed_items_map = _load_listed_items_asin_map(user_id)
        asin_filter = {normalize_asin(a) for a in asins} if asins is not None else None

        updated = 0
        mismatched = []
        now = datetime.utcnow().isoformat()
        for r in rows:
            asin = _resolve_asin(r["sku"], listed_items_map)
            if asin_filter is not None and asin not in asin_filter:
                continue
            new_auto = remarks_text((ledger.get(asin) or {}).get("ingredients"))
            old_auto = r["ingredient_remarks_auto"] or ""
            if new_auto == old_auto and (not old_auto or old_auto in (r["remarks"] or "")):
                continue
            if not old_auto and new_auto and new_auto in (r["remarks"] or ""):
                # 以前から手で同じ成分を貼ってある行は二重に書き足さず、控えだけ付ける
                cur.execute(
                    "UPDATE orbit_orders SET ingredient_remarks_auto = %s, updated_at = %s "
                    "WHERE user_id = %s AND order_item_id = %s",
                    (new_auto, now, user_id, r["order_item_id"]),
                )
                continue
            remarks, ok = _replace_bundle_remarks(r["remarks"], old_auto, new_auto)
            if not ok:
                mismatched.append(r["agent_serial_no"])
                # 備考1は触らないが、控えは新しい成分にしておく（画面で「見つからない」警告を出すため）
                cur.execute(
                    "UPDATE orbit_orders SET ingredient_remarks_auto = %s, updated_at = %s "
                    "WHERE user_id = %s AND order_item_id = %s",
                    (new_auto or None, now, user_id, r["order_item_id"]),
                )
                continue
            cur.execute(
                "UPDATE orbit_orders SET remarks = %s, ingredient_remarks_auto = %s, updated_at = %s "
                "WHERE user_id = %s AND order_item_id = %s",
                (remarks or None, new_auto or None, now, user_id, r["order_item_id"]),
            )
            updated += 1

        if own_conn is not None:
            own_conn.commit()
        return {"updated": updated, "remarks_mismatch": mismatched}
    finally:
        if own_conn is not None:
            own_conn.close()


# --- ▼ SECTION 06: 発注管理の印・警告（一覧表示用の派生キー） ▼ ---
def apply_ingredient_checks(user_id: int, rows: list):
    ledger = load_ingredient_map(user_id)
    for row in rows:
        entry = ledger.get(row.get("asin")) if row.get("asin") else None
        row["ingredient_listed"] = entry is not None
        row["ingredient_note"] = (entry or {}).get("note") or ""
        row["ingredient_text"] = remarks_text((entry or {}).get("ingredients"))
        auto = row.get("ingredient_remarks_auto")
        row["ingredient_remarks_mismatch"] = bool(auto) and auto not in (row.get("remarks") or "")
