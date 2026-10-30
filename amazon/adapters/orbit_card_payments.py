# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/orbit_card_payments.py
# 目的: ORBIT「利益分析」― クレカごとの支払い予定。選んだ支払月に、どのカードからいくら引き落とされるかを、
#   発注管理の「利用クレカ」「仕入日」「仕入れ価格」とクレカ管理の「締め日」「支払日」から集計する。読み取り専用。
#   - 締め日は「月末」「末日」「15日」、支払日は「翌月27日」「翌々月1日」「当月末」の形を読む
#   - 支払月 P・支払日が「k か月後」のカードは、P−k 月の締め日までの1か月分（前の締め日の翌日〜）が対象
#   - 仕入日で振り分けるので、カード会社の売上日（発送時に決済されるお店など）とずれると、締め日の近くは
#     翌月分に回ることがある（目安として使う）
#   - 対象は orbit_orders ＋ アーカイブ済み（orbit_procurement_history）
# ==========================================================

import calendar
import re
from datetime import date, timedelta

from amazon.db import get_conn

NO_CARD = "（利用クレカ未入力）"


def _last_day(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _add_months(y: int, m: int, k: int):
    n = y * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


def _day_in(y: int, m: int, day) -> date:
    """day=None は月末。月の日数より大きい日は月末にそろえる"""
    last = _last_day(y, m)
    return date(y, m, last if day is None else min(day, last))


def _parse_closing(text):
    """締め日 → (読めたか, 日。None=月末)"""
    t = (text or "").strip()
    if not t:
        return False, None
    if "末" in t:
        return True, None
    m = re.search(r"(\d+)", t)
    return (True, int(m.group(1))) if m else (False, None)


def _parse_payment(text):
    """支払日 → (読めたか, 何か月後, 日。None=月末)"""
    t = (text or "").strip()
    if not t:
        return False, 0, None
    if "翌々月" in t:
        months = 2
    elif "翌月" in t:
        months = 1
    elif "当月" in t:
        months = 0
    else:
        months = 1  # 「27日」だけなら翌月とみなす
    if "末" in t.replace("翌々月", "").replace("翌月", "").replace("当月", ""):
        return True, months, None
    m = re.search(r"(\d+)", t)
    return (True, months, int(m.group(1))) if m else (False, 0, None)


def card_schedule(card: dict, pay_year: int, pay_month: int) -> dict:
    """支払月のカードの締め期間・支払日。読めなければ ok=False"""
    ok_c, closing_day = _parse_closing(card.get("closing_day"))
    ok_p, months, pay_day = _parse_payment(card.get("payment_day"))
    if not (ok_c and ok_p):
        return {"ok": False}
    cy, cm = _add_months(pay_year, pay_month, -months)
    py, pm = _add_months(cy, cm, -1)
    period_end = _day_in(cy, cm, closing_day)
    period_start = _day_in(py, pm, closing_day) + timedelta(days=1)
    return {
        "ok": True,
        "period_start": period_start,
        "period_end": period_end,
        "pay_date": _day_in(pay_year, pay_month, pay_day),
    }


def _to_date(text):
    m = re.match(r"\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _load_cards(user_id: int) -> list:
    conn = get_conn("a_orbit_credit_cards.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT card_name, closing_day, payment_day FROM orbit_credit_cards "
        "WHERE user_id = %s ORDER BY sort_order, id",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_purchases(user_id: int) -> list:
    cols = ("agent_serial_no, order_id, product_name, supplier, procurement_date, "
            "purchase_price, procurement_credit_card")
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    out = []
    for table, archived in (("orbit_orders", False), ("orbit_procurement_history", True)):
        cur.execute(
            f"SELECT {cols} FROM {table} WHERE user_id = %s "
            "AND procurement_date IS NOT NULL AND procurement_date <> ''",
            (user_id,),
        )
        for r in cur.fetchall():
            d = dict(r)
            d["archived"] = archived
            out.append(d)
    conn.close()
    return out


def _default_month(cards: list, today: date):
    """まだ引き落とされていない支払日がある一番早い月"""
    for k in range(0, 3):
        y, m = _add_months(today.year, today.month, k)
        for c in cards:
            s = card_schedule(c, y, m)
            if s["ok"] and s["pay_date"] >= today:
                return y, m
    return today.year, today.month


def get_card_payments(user_id: int, month=None, today=None) -> dict:
    """month="YYYY-MM"（支払月）。省略時はまだ支払いの来ていない一番早い月"""
    today = today or date.today()
    cards = _load_cards(user_id)
    if month and re.match(r"^\d{4}-\d{1,2}$", month):
        y, m = (int(x) for x in month.split("-"))
    else:
        y, m = _default_month(cards, today)

    purchases = []
    for p in _load_purchases(user_id):
        p["date"] = _to_date(p.get("procurement_date"))
        purchases.append(p)

    def item(p):
        return {
            "date": p["date"].isoformat() if p["date"] else p.get("procurement_date"),
            "serial": p.get("agent_serial_no"),
            "order_id": p.get("order_id"),
            "product_name": p.get("product_name"),
            "supplier": p.get("supplier"),
            "price": p.get("purchase_price"),
            "archived": p["archived"],
        }

    rows = []
    span_start = span_end = None
    for c in cards:
        name = c["card_name"]
        s = card_schedule(c, y, m)
        row = {
            "card_name": name,
            "closing_day": c.get("closing_day"),
            "payment_day": c.get("payment_day"),
            "ok": s["ok"],
            "count": 0, "total": 0, "missing_price": 0, "items": [],
        }
        if s["ok"]:
            row.update(period_start=s["period_start"].isoformat(), period_end=s["period_end"].isoformat(),
                       pay_date=s["pay_date"].isoformat(), overdue=s["pay_date"] < today,
                       open=s["period_end"] >= today)
            span_start = min(span_start or s["period_start"], s["period_start"])
            span_end = max(span_end or s["period_end"], s["period_end"])
            for p in purchases:
                if (p.get("procurement_credit_card") or "") != name or not p["date"]:
                    continue
                if not (s["period_start"] <= p["date"] <= s["period_end"]):
                    continue
                row["items"].append(item(p))
                row["count"] += 1
                if p.get("purchase_price") is None:
                    row["missing_price"] += 1
                else:
                    row["total"] += float(p["purchase_price"])
        row["items"].sort(key=lambda i: (i["date"] or "", i["serial"] or 0))
        rows.append(row)

    # 利用クレカが空の仕入れ（どのカードの期間にも入りうる範囲＝表示中の全期間で数える）
    no_card = {"card_name": NO_CARD, "ok": True, "count": 0, "total": 0, "missing_price": 0, "items": []}
    if span_start:
        no_card.update(period_start=span_start.isoformat(), period_end=span_end.isoformat())
        for p in purchases:
            if (p.get("procurement_credit_card") or "").strip() or not p["date"]:
                continue
            if span_start <= p["date"] <= span_end:
                no_card["items"].append(item(p))
                no_card["count"] += 1
                if p.get("purchase_price") is None:
                    no_card["missing_price"] += 1
                else:
                    no_card["total"] += float(p["purchase_price"])
        no_card["items"].sort(key=lambda i: (i["date"] or "", i["serial"] or 0))

    # 登録されていないカード名（クレカ管理で名前を変えた・消した等）
    known = {c["card_name"] for c in cards}
    unknown = sorted({(p.get("procurement_credit_card") or "").strip() for p in purchases}
                     - known - {""})

    # 支払月の選択肢：仕入れのある最初の月の翌月 〜 今月の3か月先
    dates = [p["date"] for p in purchases if p["date"]]
    first = min(dates) if dates else today
    months = []
    yy, mm = _add_months(first.year, first.month, 1)
    ey, em = _add_months(today.year, today.month, 3)
    while (yy, mm) <= (ey, em):
        months.append(f"{yy:04d}-{mm:02d}")
        yy, mm = _add_months(yy, mm, 1)

    return {
        "month": f"{y:04d}-{m:02d}",
        "months": months,
        "today": today.isoformat(),
        "rows": rows,
        "no_card": no_card,
        "total": sum(r["total"] for r in rows),
        "unknown_cards": unknown,
    }
