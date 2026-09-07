# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/orbit_sales_trend.py
# 目的: 売上トレンド（マーケット別 販売個数の日次推移）。Dashboard「売上トレンド」サブタブ用・読み取り専用。
#   - 折れ線の値＝販売個数（quantity_purchased の日次合計）。1マーケット＝1系列
#   - ツールチップ用に、日次×マーケットの総額（item_price 合計・現地通貨のまま）と
#     概算利益率（Σ利益(円) ÷ Σ販売額(円)）＋その母数（利益を算出できた明細数）も返す
#   - 集計元は ORBIT（注文管理）に取込済みの orbit_orders のみ。マーケットは order_id 先頭桁から
#     判定する（list_orders_with_calc と同じロジック。判定不可は "不明"）
#   - item_price は拡張版の注文レポートにしか入らないため、空欄の明細は総額に含まれない（過小表示）。
#     amount_missing でその件数を返す
# ==========================================================

from datetime import datetime, timedelta

from amazon.db import get_conn
from amazon.services.orbit_order_service import list_orders_with_calc

ALLOWED_DAYS = (7, 30, 90, 180, 365)
DEFAULT_DAYS = 30
UNKNOWN_MARKET = "不明"


def _load_currency_by_country() -> dict:
    """{country_code: currency}。item_price に order_currency が無いときの表示通貨フォールバック用。"""
    conn = get_conn("a_marketplaces_master.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT country_code, currency FROM marketplaces_master WHERE country_code IS NOT NULL"
        )
        return {
            (r["country_code"] or "").strip().upper(): (r["currency"] or "").strip().upper() or None
            for r in cur.fetchall()
        }
    finally:
        conn.close()


def _purchase_date_key(value):
    """purchase_date(TEXT, ISO8601想定) → 'YYYY-MM-DD'。パースできなければ None。"""
    if not value:
        return None
    head = str(value).strip()[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return None


def get_sales_trend(user_id: int, days: int) -> dict:
    if days not in ALLOWED_DAYS:
        days = DEFAULT_DAYS

    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)  # 当日を含めて days 日
    date_labels = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    date_index = {d: i for i, d in enumerate(date_labels)}

    currency_by_country = _load_currency_by_country()

    # 注文一覧と同じ計算（寸法・予測送料・決済実績・為替）を通した行を使う。
    # profit_jpy / sale_price_used_jpy / marketplace_country はここで既に付与済み。
    orders = list_orders_with_calc(user_id)

    acc = {}

    def _slot(market):
        if market not in acc:
            acc[market] = {
                "counts": [0] * days,          # 販売個数（折れ線の値）
                "amounts": [0.0] * days,       # 総額＝item_price 合計（現地通貨）
                "amount_missing": [0] * days,  # item_price が無く総額に含められなかった明細数
                "profit_jpy": [0.0] * days,    # 利益(円) 合計（概算利益率の分子）
                "sale_jpy": [0.0] * days,      # 販売額(円) 合計（概算利益率の分母）
                "profit_cnt": [0] * days,      # 利益を算出できた明細数
                "line_cnt": [0] * days,        # その日の明細数（母数）
                "currency": None,
            }
        return acc[market]

    for row in orders:
        dkey = _purchase_date_key(row.get("purchase_date"))
        if dkey is None:
            continue
        idx = date_index.get(dkey)
        if idx is None:
            continue

        market = (row.get("marketplace_country") or "").strip().upper() or UNKNOWN_MARKET
        s = _slot(market)

        s["counts"][idx] += row.get("quantity_purchased") or 0
        s["line_cnt"][idx] += 1

        item_price = row.get("item_price")
        if item_price is not None:
            s["amounts"][idx] += float(item_price)
            if not s["currency"]:
                s["currency"] = (row.get("order_currency") or "").strip().upper() or None
        else:
            s["amount_missing"][idx] += 1

        profit_jpy = row.get("profit_jpy")
        sale_jpy = row.get("sale_price_used_jpy")
        if profit_jpy is not None and sale_jpy:
            s["profit_jpy"][idx] += float(profit_jpy)
            s["sale_jpy"][idx] += float(sale_jpy)
            s["profit_cnt"][idx] += 1

    series = []
    for market in sorted(acc.keys(), key=lambda m: (m == UNKNOWN_MARKET, m)):
        s = acc[market]
        currency = s["currency"] or currency_by_country.get(market)
        profit_rate = []
        for i in range(days):
            sj = s["sale_jpy"][i]
            profit_rate.append(round(s["profit_jpy"][i] / sj * 100, 1) if sj else None)
        series.append({
            "market": market,
            "currency": currency,
            "counts": s["counts"],
            "amounts": [round(a, 2) for a in s["amounts"]],
            "amount_missing": s["amount_missing"],
            "profit_rate_pct": profit_rate,
            "profit_cnt": s["profit_cnt"],
            "line_cnt": s["line_cnt"],
        })

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "days": days,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "dates": date_labels,
        "series": series,
        "total_qty": sum(sum(x["counts"]) for x in series),
    }
