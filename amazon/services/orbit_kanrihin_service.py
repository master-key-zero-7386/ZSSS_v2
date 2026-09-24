# ==========================================
# ファイル名: amazon/services/orbit_kanrihin_service.py
# 目的: ORBIT「管理品」サブタブ ― 代行会社シートの管理品タブ（発送不可品）を読み取り、
#       行ごとの確認状態（未確認＝新規追加の目安）・N番リンク（後から突き止めた注文との
#       紐付け）をZSSS側で管理する
# ==========================================

from datetime import datetime

from amazon.db import get_conn
from amazon.services.google_sheets_service import fetch_kanrihin_sheet_rows
from amazon.services.orbit_order_service import _extract_asin_from_sku

_ORDER_SUMMARY_COLS = ["sku", "product_name", "supplier_order_number", "supplier_shop_name", "purchase_price"]


def _get_annotations(user_id: int) -> dict:
    """{management_no: {"confirmed": bool, "linked_agent_serial_no": int|None,
    "processed": bool, "used_order_item_id": str|None}}"""
    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT management_no, confirmed_at, linked_agent_serial_no, processed_at, used_order_item_id "
        "FROM orbit_kanrihin_confirmed WHERE user_id = %s",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        r["management_no"]: {
            "confirmed": r["confirmed_at"] is not None,
            "linked_agent_serial_no": r["linked_agent_serial_no"],
            "processed": r["processed_at"] is not None,
            "used_order_item_id": r["used_order_item_id"],
        }
        for r in rows
    }


def _bulk_find_order_summaries(user_id: int, serial_nos: list) -> dict:
    """{agent_serial_no: {asin, product_name, supplier_order_number, supplier_shop_name,
    purchase_price, archived}}。現行のorbit_ordersに無ければアーカイブ済み
    (orbit_procurement_history)も見る（返品・キャンセルは出荷完了扱いにならないことも多いが、
    時間が経ってから他の経路でアーカイブされているケースも保険で見る）。"""
    serial_nos = sorted({s for s in serial_nos if s is not None})
    if not serial_nos:
        return {}

    found = {}

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cols_sql = ", ".join([f"o.{c}" for c in _ORDER_SUMMARY_COLS])
    cur.execute(
        f"""
        SELECT o.agent_serial_no, {cols_sql}, l.asin AS listed_asin
        FROM orbit_orders o
        LEFT JOIN listed_items l ON l.user_id = o.user_id AND l.sku = o.sku
        WHERE o.user_id = %s AND o.agent_serial_no = ANY(%s)
        """,
        (user_id, serial_nos),
    )
    for r in cur.fetchall():
        found[r["agent_serial_no"]] = {
            "asin": r["listed_asin"] or _extract_asin_from_sku(r["sku"]),
            "product_name": r["product_name"],
            "supplier_order_number": r["supplier_order_number"],
            "supplier_shop_name": r["supplier_shop_name"],
            "purchase_price": r["purchase_price"],
            "archived": False,
        }
    conn.close()

    remaining = [s for s in serial_nos if s not in found]
    if remaining:
        conn = get_conn("a_orbit_procurement_history.db")
        cur = conn.cursor()
        cols_sql = ", ".join(_ORDER_SUMMARY_COLS)
        cur.execute(
            f"""
            SELECT agent_serial_no, {cols_sql}
            FROM orbit_procurement_history
            WHERE user_id = %s AND agent_serial_no = ANY(%s)
            """,
            (user_id, remaining),
        )
        for r in cur.fetchall():
            found[r["agent_serial_no"]] = {
                "asin": _extract_asin_from_sku(r["sku"]),
                "product_name": r["product_name"],
                "supplier_order_number": r["supplier_order_number"],
                "supplier_shop_name": r["supplier_shop_name"],
                "purchase_price": r["purchase_price"],
                "archived": True,
            }
        conn.close()

    return found


def _bulk_find_serials_by_order_item(user_id: int, order_item_ids: list) -> dict:
    """{order_item_id: agent_serial_no}。「管理品から出荷」で使った出荷先注文のN番表示用
    （出荷後にアーカイブされていれば履歴側から引く）。"""
    order_item_ids = sorted({o for o in order_item_ids if o})
    found = {}
    for db_name, table in (
        ("a_orbit_orders.db", "orbit_orders"),
        ("a_orbit_procurement_history.db", "orbit_procurement_history"),
    ):
        remaining = [o for o in order_item_ids if o not in found]
        if not remaining:
            break
        conn = get_conn(db_name)
        cur = conn.cursor()
        cur.execute(
            f"SELECT order_item_id, agent_serial_no FROM {table} "
            f"WHERE user_id = %s AND order_item_id = ANY(%s)",
            (user_id, remaining),
        )
        for r in cur.fetchall():
            found.setdefault(r["order_item_id"], r["agent_serial_no"])
        conn.close()
    return found


def list_kanrihin_items(user_id: int) -> dict:
    sheet_data = fetch_kanrihin_sheet_rows(user_id)
    annotations = _get_annotations(user_id)

    linked_serials = [a["linked_agent_serial_no"] for a in annotations.values() if a["linked_agent_serial_no"]]
    order_summaries = _bulk_find_order_summaries(user_id, linked_serials)
    used_serials = _bulk_find_serials_by_order_item(
        user_id, [a["used_order_item_id"] for a in annotations.values() if a["used_order_item_id"]]
    )

    items = []
    unconfirmed_count = 0
    for row in sheet_data["rows"]:
        management_no = row[0] if row else ""
        if not management_no:
            continue
        anno = annotations.get(management_no) or {
            "confirmed": False, "linked_agent_serial_no": None, "processed": False, "used_order_item_id": None,
        }
        if not anno["confirmed"]:
            unconfirmed_count += 1

        linked_serial = anno["linked_agent_serial_no"]
        items.append({
            "management_no": management_no,
            "cells": row,
            "confirmed": anno["confirmed"],
            "linked_agent_serial_no": linked_serial,
            "linked_order_info": order_summaries.get(linked_serial) if linked_serial else None,
            "processed": anno["processed"],
            "used_order_item_id": anno["used_order_item_id"],
            "used_agent_serial_no": used_serials.get(anno["used_order_item_id"]),
        })

    return {
        "header": sheet_data["header"],
        "items": items,
        "unconfirmed_count": unconfirmed_count,
    }


def confirm_kanrihin_items(user_id: int, management_nos: list):
    management_nos = [m for m in (management_nos or []) if m]
    if not management_nos:
        return

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    for management_no in management_nos:
        cur.execute("""
            INSERT INTO orbit_kanrihin_confirmed (user_id, management_no, confirmed_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, management_no) DO UPDATE SET confirmed_at = EXCLUDED.confirmed_at
        """, (user_id, management_no, now))
    conn.commit()
    conn.close()


def release_kanrihin_item(user_id: int, management_no: str):
    """確認済みボタンの再押しで解除（未確認に戻す）。N番リンクは消さないよう、行自体は
    DELETEせずconfirmed_atだけNULLに戻す。"""
    if not management_no:
        return

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE orbit_kanrihin_confirmed SET confirmed_at = NULL WHERE user_id = %s AND management_no = %s",
        (user_id, management_no),
    )
    conn.commit()
    conn.close()


def save_kanrihin_link(user_id: int, management_no: str, agent_serial_no) -> dict:
    """管理品の行に、後から突き止めたN番を手動でリンクする。空/Noneならリンク解除。
    戻り値はその場でUIに表示するための注文情報（見つからなければNone）。"""
    if not management_no:
        raise ValueError("management_noが必要です")

    serial_no = None
    if agent_serial_no not in (None, ""):
        try:
            serial_no = int(agent_serial_no)
        except (TypeError, ValueError):
            raise ValueError("N番は数字で入力してください")

    # N番を入れたら自動で確認済にする（未確認の警告を消す）。N番を消しても確認済は戻さない
    # （入力ミスを直すたびに警告が復活しないように）。既に確認済なら元の確認日時を保つ。
    confirmed_at = datetime.utcnow().isoformat() if serial_no is not None else None

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orbit_kanrihin_confirmed (user_id, management_no, linked_agent_serial_no, confirmed_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, management_no) DO UPDATE SET
            linked_agent_serial_no = EXCLUDED.linked_agent_serial_no,
            confirmed_at = COALESCE(orbit_kanrihin_confirmed.confirmed_at, EXCLUDED.confirmed_at)
    """, (user_id, management_no, serial_no, confirmed_at))
    conn.commit()
    conn.close()

    if serial_no is None:
        return None
    return _bulk_find_order_summaries(user_id, [serial_no]).get(serial_no)


# --- ▼ 処理済（保管在庫が無くなった印）の手動ON/OFF ▼ ---
def set_kanrihin_processed(user_id: int, management_no: str, processed: bool):
    """管理品タブの「処理済」ボタン用。OFFに戻したときは「管理品から出荷」で使われた注文との
    紐付けも外す（在庫が残っている扱いに戻り、再び出荷ボタンの候補になる）。"""
    if not management_no:
        raise ValueError("management_noが必要です")

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orbit_kanrihin_confirmed (user_id, management_no, processed_at, used_order_item_id)
        VALUES (%s, %s, %s, NULL)
        ON CONFLICT (user_id, management_no) DO UPDATE SET
            processed_at = EXCLUDED.processed_at,
            used_order_item_id = NULL
    """, (user_id, management_no, datetime.utcnow().isoformat() if processed else None))
    conn.commit()
    conn.close()


# --- ▼ 「管理品から出荷」（発注管理の仕入れ情報）▼ ---
# 対象はスプレッドシート運用からORBITへ移行した後（N5130以降）にN番リンクした管理品のみ。
KANRIHIN_MIN_SERIAL_NO = 5130

# 元のN番（管理品になった注文）から出荷先注文へ移植する仕入情報
_KANRIHIN_COPY_FIELDS = [
    "supplier", "supplier_order_number", "supplier_shop_name", "purchase_price", "jan_code", "arrival_date",
]


def _load_unprocessed_with_asin(user_id: int) -> list:
    """未処理（在庫あり）の管理品を N番の古い順で、ASIN付きで返す。
    [{management_no, linked_agent_serial_no, asin}]"""
    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT management_no, linked_agent_serial_no
        FROM orbit_kanrihin_confirmed
        WHERE user_id = %s AND processed_at IS NULL AND linked_agent_serial_no >= %s
        ORDER BY linked_agent_serial_no ASC, management_no ASC
    """, (user_id, KANRIHIN_MIN_SERIAL_NO))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    summaries = _bulk_find_order_summaries(user_id, [r["linked_agent_serial_no"] for r in rows])
    for r in rows:
        r["asin"] = (summaries.get(r["linked_agent_serial_no"]) or {}).get("asin")
    return [r for r in rows if r["asin"]]


def load_kanrihin_stock(user_id: int) -> dict:
    """発注管理の一覧表示用。
    {"available": {asin: 未処理の管理品数}, "used": {order_item_id: management_no},
     "source_serials": {管理品になった元のN番}}（元の注文自身には出荷ボタンを出さないため）"""
    available = {}
    source_serials = set()
    for r in _load_unprocessed_with_asin(user_id):
        available[r["asin"]] = available.get(r["asin"], 0) + 1
        source_serials.add(r["linked_agent_serial_no"])

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT management_no, used_order_item_id FROM orbit_kanrihin_confirmed "
        "WHERE user_id = %s AND used_order_item_id IS NOT NULL",
        (user_id,),
    )
    used = {r["used_order_item_id"]: r["management_no"] for r in cur.fetchall()}
    conn.close()

    return {"available": available, "used": used, "source_serials": source_serials}


def _fetch_source_procurement(user_id: int, serial_no: int):
    """元のN番の仕入情報（移植元）。現行注文に無ければアーカイブ済み履歴も見る。"""
    cols_sql = ", ".join(_KANRIHIN_COPY_FIELDS)
    for db_name, table in (
        ("a_orbit_orders.db", "orbit_orders"),
        ("a_orbit_procurement_history.db", "orbit_procurement_history"),
    ):
        conn = get_conn(db_name)
        cur = conn.cursor()
        cur.execute(
            f"SELECT {cols_sql} FROM {table} WHERE user_id = %s AND agent_serial_no = %s LIMIT 1",
            (user_id, serial_no),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return dict(row)
    return None


def _override_price_countries(user_id: int, asin: str) -> list:
    """そのASINを手入力価格(override_price)で出品しているZSSS内のマーケット（country_code）一覧。"""
    conn = get_conn("listed_items")
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT m.country_code AS country_code
        FROM listed_items li
        JOIN marketplaces m
          ON m.user_id = li.user_id
         AND m.marketplace_id = li.region_marketplace_id
        WHERE li.user_id = %s AND li.asin = %s AND li.override_price IS NOT NULL
    """, (user_id, asin))
    countries = [r["country_code"] for r in cur.fetchall() if r["country_code"]]
    conn.close()
    return sorted(countries)


def _clear_override_price_all_markets(user_id: int, asin: str, skip_refresh_country: str = None) -> list:
    """全マーケットの手入力価格をOFFにする。OFF＝override_price NULL なのでTTL対象に自動復帰する。
    ALL-Listingの手入力OFFと同じく、その場で update_home_pricing → update_region_pricing で
    取り直して通常計算に戻す（skip_refresh_country は直後に仕入済の再出品で同じ処理が走る国）。"""
    countries = _override_price_countries(user_id, asin)
    if not countries:
        return []

    conn = get_conn("listed_items")
    cur = conn.cursor()
    cur.execute("""
        UPDATE listed_items
        SET override_price = NULL, updated_at = %s
        WHERE user_id = %s AND asin = %s AND override_price IS NOT NULL
    """, (datetime.utcnow().isoformat(), user_id, asin))
    conn.commit()
    conn.close()

    # 循環importを避けるため関数内import（relist_after_purchaseと同じ扱い）
    from amazon.routes.routes_pricing_v2 import update_home_pricing, update_region_pricing

    for country_code in countries:
        if skip_refresh_country and country_code.upper() == skip_refresh_country.upper():
            continue
        try:
            update_home_pricing(user_id=user_id, asin=asin, country_code=country_code)
            update_region_pricing(user_id=user_id, asin=asin, country_code=country_code)
        except Exception:
            import traceback
            print(f"[kanrihin] override OFF recalculation ERROR ({country_code} {asin})")
            traceback.print_exc()

    return countries


def ship_from_kanrihin(user_id: int, order_item_id: str) -> dict:
    """発注管理「管理品から出荷」。
    1. 同ASINの未処理管理品のうちN番最古を選ぶ
    2. 元N番の仕入情報（仕入先・注文番号・ショップ名・仕入価格・JAN・到着予定日）を移植
    3. その管理品を処理済にし、この注文に紐付ける
    4. 同ASINの管理品が残っていなければ全マーケットの手入力価格をOFF（TTL復帰）
    5. 仕入済をON（0→1のときだけ通常どおり再出品）
    6. 管理品が残っていて他マーケットも手入力出品中なら警告用に国を返す"""
    from amazon.services.orbit_order_service import (
        update_manual_fields, order_flag_is_set, relist_after_purchase,
    )

    # --- 出荷先注文の ASIN・販売マーケット ---
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT o.sku, o.agent_serial_no, l.asin, m.country_code
        FROM orbit_orders o
        LEFT JOIN listed_items l ON l.user_id = o.user_id AND l.sku = o.sku
        LEFT JOIN marketplaces m ON m.user_id = l.user_id AND m.marketplace_id = l.region_marketplace_id
        WHERE o.user_id = %s AND o.order_item_id = %s
        LIMIT 1
    """, (user_id, order_item_id))
    order = cur.fetchone()
    conn.close()
    if not order:
        raise ValueError("注文が見つかりません")

    asin = order["asin"] or _extract_asin_from_sku(order["sku"])
    if not asin:
        raise ValueError("ASINが特定できません")
    order_country = order["country_code"]

    # --- 1. 管理品の選択（N番の古い順） ---
    # 管理品になった元の注文自身は出荷先にならない
    candidates = [
        r for r in _load_unprocessed_with_asin(user_id)
        if r["asin"] == asin and r["linked_agent_serial_no"] != order["agent_serial_no"]
    ]
    if not candidates:
        raise ValueError("このASINの未処理の管理品がありません")
    picked = candidates[0]

    # --- 2. 仕入情報の移植（元が空の項目は上書きしない） ---
    source = _fetch_source_procurement(user_id, picked["linked_agent_serial_no"])
    if not source:
        raise ValueError(f"移植元 N{picked['linked_agent_serial_no']} の注文が見つかりません")
    copy_fields = {k: source[k] for k in _KANRIHIN_COPY_FIELDS if source.get(k) not in (None, "")}
    if copy_fields:
        update_manual_fields(user_id, order_item_id, copy_fields)

    # --- 3. 処理済＋この注文に紐付け ---
    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("""
        UPDATE orbit_kanrihin_confirmed
        SET processed_at = %s, used_order_item_id = %s
        WHERE user_id = %s AND management_no = %s
    """, (datetime.utcnow().isoformat(), order_item_id, user_id, picked["management_no"]))
    conn.commit()
    conn.close()

    remaining = len(candidates) - 1
    will_relist = not order_flag_is_set(user_id, order_item_id, "purchased")

    # --- 4. 在庫ゼロなら全マーケットの手入力価格をOFF ---
    cleared_countries = []
    if remaining == 0:
        cleared_countries = _clear_override_price_all_markets(
            user_id, asin, skip_refresh_country=order_country if will_relist else None,
        )

    # --- 5. 仕入済ON（確認ダイアログ無し。在庫が残っていれば手入力価格のまま再出品される） ---
    restock_result = None
    if will_relist:
        update_manual_fields(user_id, order_item_id, {"purchased": 1})
        try:
            restock_result = relist_after_purchase(user_id, order_item_id)
        except Exception:
            import traceback
            print("[kanrihin] relist_after_purchase ERROR")
            traceback.print_exc()

    # --- 6. 在庫が残っている場合、他マーケットの手入力出品を警告 ---
    other_override_countries = []
    if remaining > 0:
        other_override_countries = [
            c for c in _override_price_countries(user_id, asin)
            if not order_country or c.upper() != order_country.upper()
        ]

    return {
        "management_no": picked["management_no"],
        "source_serial_no": picked["linked_agent_serial_no"],
        "asin": asin,
        "remaining": remaining,
        "cleared_countries": cleared_countries,
        "other_override_countries": other_override_countries,
        "restock": restock_result,
    }
