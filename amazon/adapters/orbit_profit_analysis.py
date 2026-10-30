# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/orbit_profit_analysis.py
# 目的: ORBIT「利益分析」サブタブ ― 期間内の注文を1行ずつ、利益の内訳（販売額・手数料・仕入・送料）と
#   予測送料 vs 実際の送料のズレを並べる。読み取り専用。
#   - 集計元・期間・日の区切り（日本時間）は売上トレンドと同じ（orbit_sales_trend の関数を使う）
#   - 金額はすべて円。販売額＝注文一覧の sale_price_used_jpy、返金＝決済レポートの返金（プラスで表示）、
#     手数料＝販売額 − 入金額(円) − 返金
#   - 送料ズレは送料検証（ship_check）の判定結果をそのまま使う（同梱・キャンセルは対象外）
#   - 利益率は売上トレンドと同じ「利益 ÷ 販売額」（注文一覧の利益率は入金額基準なので少し違う）
#   - キャンセル（発送種別＝キャンセル）は除外
# ==========================================================

from amazon.adapters.orbit_sales_trend import (
    CANCELLED_SHIPPING_TYPE,
    UNKNOWN_MARKET,
    _purchase_date_key,
    load_rows_with_calc,
)
from amazon.services.orbit_ship_check_service import get_profit_weight_pct


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _pct(part, whole):
    return round(part / whole * 100, 1) if part is not None and whole else None


def get_profit_analysis(user_id: int, start, end) -> dict:
    start_key, end_key = start.isoformat(), end.isoformat()
    out = []
    for r in load_rows_with_calc(user_id):
        if (r.get("shipping_type") or "").strip() == CANCELLED_SHIPPING_TYPE:
            continue
        dkey = _purchase_date_key(r.get("purchase_date"))
        if dkey is None or not (start_key <= dkey <= end_key):
            continue

        sale = _f(r.get("sale_price_used_jpy"))
        net = _f(r.get("net_proceeds_used_jpy"))
        # 返金は決済レポートでマイナスで来る。表ではプラスの金額で出し、手数料からは除く
        refund = -_f(r.get("refund_used_jpy")) if r.get("refund_used_jpy") else None
        fee = sale - net - (refund or 0) if sale is not None and net is not None else None
        purchase = _f(r.get("purchase_price"))
        ship = _f(r.get("shipping_cost_used"))
        profit = _f(r.get("profit_jpy"))
        check = r.get("ship_check") or {}

        out.append({
            "order_item_id": r.get("order_item_id"),
            "order_id": r.get("order_id"),
            "date": dkey,
            "serial": r.get("agent_serial_no"),
            "market": (r.get("marketplace_country") or "").strip().upper() or UNKNOWN_MARKET,
            "asin": r.get("asin"),
            "product_name": r.get("product_name"),
            "qty": r.get("quantity_purchased") or 0,
            "archived": bool(r.get("archived_at")),
            "sale_jpy": sale,
            "refund_jpy": refund,
            "fee_jpy": fee,
            "fee_is_estimate": r.get("net_proceeds_is_estimate"),
            "purchase_jpy": purchase,
            "ship_jpy": ship,
            "ship_is_estimate": r.get("shipping_cost_is_estimate"),
            "ship_is_bundle": bool(r.get("shipping_cost_is_bundle")),
            "fee_pct": _pct(fee, sale),
            "purchase_pct": _pct(purchase, sale),
            "ship_pct": _pct(ship, sale),
            # 予測送料 vs 実際（送料検証と同じ値・同じ警告基準）
            "est_ship": check.get("est_fee"),
            "actual_ship": check.get("actual_fee_total"),
            "ship_diff": check.get("fee_diff"),
            "ship_diff_pct": check.get("fee_diff_pct"),
            "ship_warn": bool(check.get("fee_warn")),
            "ship_under": bool(check.get("fee_under")),
            "weight_warn": bool(check.get("weight_warn")),
            "carrier_warn": bool(check.get("carrier_warn")),
            # 送料のズレの中身（キャリア・請求重量の 予測 → 実際）
            "est_carrier": check.get("est_carrier"),
            "actual_carrier": check.get("actual_carrier"),
            "actual_carrier_inferred": bool(check.get("actual_carrier_inferred")),
            "carrier_best": check.get("carrier_best"),
            "carrier_best_price": check.get("carrier_best_price"),
            "carrier_diff": check.get("carrier_diff"),
            "est_weight_kg": check.get("est_weight_kg"),
            "actual_weight_kg": check.get("actual_weight_kg"),
            "ship_excluded": check.get("excluded"),
            "tips": check.get("tips") or [],
            "profit_jpy": profit,
            "profit_is_estimate": r.get("profit_is_estimate"),
            "profit_rate": _pct(profit, sale),
        })

    return {
        "start": start_key,
        "end": end_key,
        "rows": out,
        "weight_pct": get_profit_weight_pct(user_id),
    }
