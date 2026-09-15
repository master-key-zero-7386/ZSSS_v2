# ==========================================
# ファイル名: amazon/services/orbit_kanrihin_service.py
# 目的: ORBIT「管理品」サブタブ ― 代行会社シートの管理品タブ（発送不可品）を読み取り、
#       行ごとの確認状態（未確認＝新規追加の目安）をZSSS側で管理する
# ==========================================

from datetime import datetime

from amazon.db import get_conn
from amazon.services.google_sheets_service import fetch_kanrihin_sheet_rows


def _get_confirmed_set() -> set:
    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    cur.execute("SELECT management_no FROM orbit_kanrihin_confirmed")
    rows = cur.fetchall()
    conn.close()
    return {r["management_no"] for r in rows}


def list_kanrihin_items(user_id: int) -> dict:
    sheet_data = fetch_kanrihin_sheet_rows(user_id)
    confirmed = _get_confirmed_set()

    items = []
    unconfirmed_count = 0
    for row in sheet_data["rows"]:
        management_no = row[0] if row else ""
        if not management_no:
            continue
        is_confirmed = management_no in confirmed
        if not is_confirmed:
            unconfirmed_count += 1
        items.append({
            "management_no": management_no,
            "cells": row,
            "confirmed": is_confirmed,
        })

    return {
        "header": sheet_data["header"],
        "items": items,
        "unconfirmed_count": unconfirmed_count,
    }


def confirm_kanrihin_items(management_nos: list):
    management_nos = [m for m in (management_nos or []) if m]
    if not management_nos:
        return

    conn = get_conn("a_orbit_kanrihin_confirmed.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    for management_no in management_nos:
        cur.execute("""
            INSERT INTO orbit_kanrihin_confirmed (management_no, confirmed_at)
            VALUES (%s, %s)
            ON CONFLICT (management_no) DO UPDATE SET confirmed_at = EXCLUDED.confirmed_at
        """, (management_no, now))
    conn.commit()
    conn.close()
