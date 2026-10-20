# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/orbit_sales_trend.py
# 目的: 売上トレンド（マーケット別 販売個数の日次推移）。Dashboard「売上トレンド」サブタブ用・読み取り専用。
#   - 折れ線の値＝販売個数（quantity_purchased の日次合計）。1マーケット＝1系列
#   - ツールチップ用に、日次×マーケットの総額（item_price 合計・現地通貨のまま）と
#     概算利益率（Σ利益(円) ÷ Σ販売額(円)）＋その母数（利益を算出できた明細数）も返す
#   - 利益額(円)・仕入額(円) の日次合計も返す（画面の期間合計表と「利益額／利益率／仕入額」表示切替用）。
#     仕入額は仕入価格(円)が入力済みの明細だけを合計する（消費税還付の目安用・注文日ベース）
#   - 利益は「うち概算」（手数料見積り・予測送料を使った分＝profit_is_estimate）も別に返す
#   - 期間は「直近N日」「月指定(YYYY-MM)」「開始日〜終了日」のどれか。日の区切りは日本時間（JST）。
#     purchase_date は UTC の ISO8601 なので +9時間して日付を決める
#   - 集計元は ORBIT（注文管理）に取込済みの orbit_orders のみ。マーケットは order_id 先頭桁から
#     判定する（list_orders_with_calc と同じロジック。判定不可は "不明"）
#   - item_price は拡張版の注文レポートにしか入らないため、空欄の明細は総額に含まれない（過小表示）。
#     amount_missing でその件数を返す
# ==========================================================

from datetime import date, datetime, timedelta, timezone

from amazon.db import get_conn
from amazon.services.orbit_order_service import list_orders_with_calc

ALLOWED_DAYS = (7, 30, 90, 180, 365)
DEFAULT_DAYS = 30
MAX_RANGE_DAYS = 366  # 日付指定の上限（1年分）
JST = timezone(timedelta(hours=9))
UNKNOWN_MARKET = "不明"
CANCELLED_SHIPPING_TYPE = "キャンセル"  # static/js/orbit.js の ORBIT_CANCEL と同じ判定基準


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
    """purchase_date(TEXT, ISO8601想定・UTC) → 日本時間の 'YYYY-MM-DD'。パースできなければ None。
    タイムゾーン表記が無い値は UTC とみなす。時刻が無い（日付だけの）値はそのままの日付を使う。"""
    if not value:
        return None
    text = str(value).strip()
    if len(text) <= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).date().isoformat()


def today_jst() -> date:
    return datetime.now(JST).date()


def resolve_range(days=None, month=None, start=None, end=None):
    """画面の期間指定 → (開始日, 終了日)。優先順位: 開始日〜終了日 ＞ 月 ＞ 直近N日。
    不正な値は直近30日に戻す。月指定は今月なら今日まで。"""
    today = today_jst()
    if start and end:
        try:
            s = date.fromisoformat(start)
            e = date.fromisoformat(end)
            if s > e:
                s, e = e, s
            if (e - s).days + 1 > MAX_RANGE_DAYS:
                s = e - timedelta(days=MAX_RANGE_DAYS - 1)
            return s, e
        except ValueError:
            pass
    if month:
        try:
            s = datetime.strptime(month, "%Y-%m").date()
            nxt = (s.replace(day=28) + timedelta(days=4)).replace(day=1)
            e = nxt - timedelta(days=1)
            if s <= today < e:
                e = today
            return s, e
        except ValueError:
            pass
    if days not in ALLOWED_DAYS:
        days = DEFAULT_DAYS
    return today - timedelta(days=days - 1), today  # 当日を含めて days 日


def get_sales_trend(user_id: int, start: date, end: date) -> dict:
    days = (end - start).days + 1

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
                "profit_est_jpy": [0.0] * days,  # うち概算（手数料見積り・予測送料を使った明細）の利益(円)
                "profit_est_cnt": [0] * days,    # うち概算の明細数
                "line_cnt": [0] * days,        # その日の明細数（母数）
                "purchase_jpy": [0.0] * days,  # 仕入額(円) 合計（仕入価格が入力済みの明細のみ）
                "purchase_cnt": [0] * days,    # 仕入価格が入力済みの明細数
                "currency": None,
            }
        return acc[market]

    for row in orders:
        # ORBIT集計パネル（月次売上・未出荷サマリ）と同じく、発送種別=キャンセルの注文は除外する
        if (row.get("shipping_type") or "").strip() == CANCELLED_SHIPPING_TYPE:
            continue

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
            if row.get("profit_is_estimate"):
                s["profit_est_jpy"][idx] += float(profit_jpy)
                s["profit_est_cnt"][idx] += 1

        purchase_price = row.get("purchase_price")
        if purchase_price is not None:
            s["purchase_jpy"][idx] += float(purchase_price)
            s["purchase_cnt"][idx] += 1

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
            "profit_jpy": [round(v) for v in s["profit_jpy"]],
            "sale_jpy": [round(v) for v in s["sale_jpy"]],
            "profit_est_jpy": [round(v) for v in s["profit_est_jpy"]],
            "profit_est_cnt": s["profit_est_cnt"],
            "purchase_jpy": [round(v) for v in s["purchase_jpy"]],
            "purchase_cnt": s["purchase_cnt"],
            "profit_cnt": s["profit_cnt"],
            "line_cnt": s["line_cnt"],
        })

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "days": days,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "dates": date_labels,
        "series": series,
        "total_qty": sum(sum(x["counts"]) for x in series),
    }
