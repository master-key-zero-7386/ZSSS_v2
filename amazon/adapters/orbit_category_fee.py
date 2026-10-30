# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/orbit_category_fee.py
# 目的: ORBIT「利益分析」― カテゴリ（商品タイプ）ごとの実際の販売手数料率を、決済レポートから集計する。
#   値段の計算（price_calculator）には一切使わない、あとで手数料率を見直すときの参考用。読み取り専用。
#   - 対象は決済レポートの注文（Order）の明細だけ。返金の明細は混ぜない
#   - 手数料率＝販売手数料（Commission）÷ 商品代金（Principal＋お客様負担の送料。税金は除く）
#   - 成約料（VariableClosingFee）など割合でない手数料は「その他手数料」として1件あたりの平均で別に出す
#   - 決済のSKU → listed_items のASIN → その環境の catalog_cache の商品タイプ の順につなぐ。
#     注文管理（orbit_orders）は使わないので、ZSSS でも ATLAS でも同じように動く
#     （AU のカタログは ATLAS にしか無いので、AU の正しい数字は ATLAS で見る）
# ==========================================================

import json
import statistics

from amazon.db import get_conn
from amazon.services.orbit_order_service import _load_listed_items_asin_map, _resolve_asin

# 決済の通貨 → 国・マーケットプレイスID（商品タイプはこの国の分を優先して使う）
CURRENCY_MARKET = {
    "CAD": ("CA", "A2EUQ1WTGCTBG2"),
    "USD": ("US", "ATVPDKIKX0DER"),
    "AUD": ("AU", "A39IBJ37TRP1C6"),
    "SGD": ("SG", "A19VAU5U5O7RUS"),
}
UNKNOWN_TYPE = "（不明）"


def _load_order_items(user_id: int) -> dict:
    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT order_item_id, sku, currency, amount_type, amount_description, amount, posted_date
        FROM orbit_settlement_items
        WHERE user_id = %s AND transaction_type = 'Order' AND order_item_id IS NOT NULL
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()

    items = {}
    for r in rows:
        it = items.setdefault(r["order_item_id"], {
            "sku": r["sku"], "currency": r["currency"], "base": 0.0, "commission": 0.0,
            "other_fee": 0.0, "other_names": set(), "posted_date": None,
        })
        amount = r["amount"] or 0.0
        desc = r["amount_description"] or ""
        if r["amount_type"] == "ItemPrice" and "Tax" not in desc:
            it["base"] += amount
        elif r["amount_type"] == "ItemFees":
            if desc == "Commission":
                it["commission"] -= amount
            else:
                it["other_fee"] -= amount
                it["other_names"].add(desc)
        if r["posted_date"] and (not it["posted_date"] or r["posted_date"] > it["posted_date"]):
            it["posted_date"] = r["posted_date"]
    return items


def _load_product_types(asins) -> dict:
    """{asin: {marketplace_id: 商品タイプ, None: どこかの国の商品タイプ}}（REGION を優先、無ければ HOME）"""
    if not asins:
        return {}
    conn = get_conn("a_catalog_cache.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT asin, region_raw_json, home_raw_json FROM catalog_cache WHERE asin = ANY(%s)",
        (list(asins),),
    )
    rows = cur.fetchall()
    conn.close()

    out = {}
    for r in rows:
        d = out.setdefault(r["asin"], {})
        for text in (r["region_raw_json"], r["home_raw_json"]):
            if not text:
                continue
            try:
                types = json.loads(text).get("productTypes") or []
            except (TypeError, ValueError, AttributeError):
                continue
            for t in types:
                pt = t.get("productType")
                if not pt:
                    continue
                d.setdefault(t.get("marketplaceId"), pt)
                d.setdefault(None, pt)
    return out


def _stats(rates):
    return {
        "median": round(statistics.median(rates), 1),
        "min": round(min(rates), 1),
        "max": round(max(rates), 1),
    }


def get_category_fee_rates(user_id: int) -> dict:
    items = _load_order_items(user_id)
    asin_map = _load_listed_items_asin_map(user_id)
    for it in items.values():
        it["asin"] = _resolve_asin(it["sku"], asin_map)
    types = _load_product_types({it["asin"] for it in items.values() if it["asin"]})

    groups = {}   # (国, 商品タイプ) -> 集計
    markets = {}  # 国 -> 国全体の集計
    for it in items.values():
        if it["base"] <= 0:
            continue
        market, mp_id = CURRENCY_MARKET.get(it["currency"], (it["currency"] or "?", None))
        t = types.get(it["asin"]) or {}
        ptype = t.get(mp_id) or t.get(None) or UNKNOWN_TYPE
        rate = it["commission"] / it["base"] * 100

        for key, bucket in (((market, ptype), groups), (market, markets)):
            g = bucket.setdefault(key, {
                "rates": [], "other_fee": 0.0, "other_count": 0, "other_names": set(),
                "asins": [], "last_date": None, "currency": it["currency"],
            })
            g["rates"].append(rate)
            if it["other_fee"]:
                g["other_fee"] += it["other_fee"]
                g["other_count"] += 1
                g["other_names"] |= it["other_names"]
            if it["asin"] and it["asin"] not in g["asins"]:
                g["asins"].append(it["asin"])
            if it["posted_date"] and (not g["last_date"] or it["posted_date"] > g["last_date"]):
                g["last_date"] = it["posted_date"]

    def _row(g):
        return {
            "count": len(g["rates"]),
            **_stats(g["rates"]),
            "currency": g["currency"],
            # 割合でない手数料（成約料など）は、その手数料が付いた注文だけの1件あたり平均
            "other_fee_avg": round(g["other_fee"] / g["other_count"], 2) if g["other_count"] else None,
            "other_count": g["other_count"],
            "other_names": sorted(g["other_names"]),
            "asins": g["asins"][:5],
            "last_date": g["last_date"],
        }

    rows = [
        {"market": m, "product_type": pt, **_row(g)}
        for (m, pt), g in groups.items()
    ]
    rows.sort(key=lambda r: (r["market"], r["product_type"] == UNKNOWN_TYPE, -r["count"], r["product_type"]))
    totals = [{"market": m, **_row(g)} for m, g in sorted(markets.items())]
    return {"rows": rows, "totals": totals}
