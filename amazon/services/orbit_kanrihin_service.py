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
    """{management_no: {"confirmed": bool, "linked_agent_serial_no": int|None}}"""
    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT management_no, confirmed_at, linked_agent_serial_no "
        "FROM orbit_kanrihin_confirmed WHERE user_id = %s",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        r["management_no"]: {
            "confirmed": r["confirmed_at"] is not None,
            "linked_agent_serial_no": r["linked_agent_serial_no"],
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


def list_kanrihin_items(user_id: int) -> dict:
    sheet_data = fetch_kanrihin_sheet_rows(user_id)
    annotations = _get_annotations(user_id)

    linked_serials = [a["linked_agent_serial_no"] for a in annotations.values() if a["linked_agent_serial_no"]]
    order_summaries = _bulk_find_order_summaries(user_id, linked_serials)

    items = []
    unconfirmed_count = 0
    for row in sheet_data["rows"]:
        management_no = row[0] if row else ""
        if not management_no:
            continue
        anno = annotations.get(management_no) or {"confirmed": False, "linked_agent_serial_no": None}
        if not anno["confirmed"]:
            unconfirmed_count += 1

        linked_serial = anno["linked_agent_serial_no"]
        items.append({
            "management_no": management_no,
            "cells": row,
            "confirmed": anno["confirmed"],
            "linked_agent_serial_no": linked_serial,
            "linked_order_info": order_summaries.get(linked_serial) if linked_serial else None,
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

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orbit_kanrihin_confirmed (user_id, management_no, linked_agent_serial_no)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, management_no) DO UPDATE SET
            linked_agent_serial_no = EXCLUDED.linked_agent_serial_no
    """, (user_id, management_no, serial_no))
    conn.commit()
    conn.close()

    if serial_no is None:
        return None
    return _bulk_find_order_summaries(user_id, [serial_no]).get(serial_no)
