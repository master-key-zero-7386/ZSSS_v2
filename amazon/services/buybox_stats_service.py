# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/services/buybox_stats_service.py
# 目的: Pricing 設定「カート取得状況」― LIVE の出品のうち、自分がカート（おすすめ出品）を取っている割合を
#   国ごと・商品タイプごとに集計し、1日1回 buybox_daily_stats に残す（値段を上げすぎて売れなくなって
#   いないかの目安）。
#   - Amazon には問い合わせない。TTL で取ってある pricing_cache.region_offers_json（getItemOffers の結果）を読むだけ
#   - 割合の分母は「出品情報がある件数」。データの古さは fresh_count（7日以内に取れた件数）で見る
#   - 商品タイプは amazon/core/category_fee.py と同じ（この環境の catalog_cache）
#   - 国はこの環境で LIVE の出品がある国だけ（AU は ATLAS で集計される）
# ==========================================================

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from amazon.db import get_conn
from amazon.core.category_fee import get_category_fee_settings, load_product_types

JST = timezone(timedelta(hours=9))
FRESH_DAYS = 7
COUNT_KEYS = (
    "live_count", "with_data", "buybox_mine", "buybox_other", "buybox_none",
    "lowest_mine", "cheaper_other", "not_visible", "fresh_count",
)


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


# --- ▼ SECTION 01: 集計 ▼ ---
def _landed(offer) -> float:
    return float((offer.get("ListingPrice") or {}).get("Amount") or 0) + float((offer.get("Shipping") or {}).get("Amount") or 0)


def _classify(offers_json, my_seller_id):
    """1出品分の判定。出品情報が無ければ None"""
    if not offers_json:
        return None
    try:
        payload = json.loads(offers_json).get("payload") or {}
    except (TypeError, ValueError, AttributeError):
        return None
    offers = payload.get("Offers") or []
    mine = next((o for o in offers if o.get("SellerId") == my_seller_id), None)
    winner = next((o for o in offers if o.get("IsBuyBoxWinner")), None)

    out = {"with_data": 1}
    if winner is None:
        out["buybox_none"] = 1
    elif winner.get("SellerId") == my_seller_id:
        out["buybox_mine"] = 1
    else:
        out["buybox_other"] = 1
    if mine is None:
        out["not_visible"] = 1
    elif _landed(mine) <= min(_landed(o) for o in offers) + 0.001:
        out["lowest_mine"] = 1
    else:
        out["cheaper_other"] = 1
    return out


def _my_seller_id(user_id: int, country_code: str):
    conn = get_conn("a_account_master.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT account_seller_id FROM account_master WHERE user_id = %s AND UPPER(country_code) = UPPER(%s) "
            "AND account_seller_id IS NOT NULL AND account_seller_id <> '' LIMIT 1",
            (user_id, country_code),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    return row["account_seller_id"] if row else None


def compute_buybox_stats(user_id: int, country_code: str, marketplace_id: str) -> dict:
    """{"": 国全体の件数, 商品タイプ: 件数, ...}（件数は COUNT_KEYS）"""
    my_seller_id = _my_seller_id(user_id, country_code)

    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT asin FROM listed_items "
            "WHERE user_id = %s AND region_marketplace_id = %s AND UPPER(COALESCE(listing_status, '')) = 'LIVE'",
            (user_id, marketplace_id),
        )
        asins = [r["asin"] for r in cur.fetchall() if r["asin"]]
    finally:
        conn.close()

    # 同じ ASIN が HOME 違いで複数行あるときは、新しい方を使う
    offers = {}
    if asins:
        conn = get_conn("a_pricing_cache.db")
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT asin, region_offers_json, region_updated_at FROM pricing_cache "
                "WHERE region_marketplace_id = %s AND asin = ANY(%s)",
                (marketplace_id, asins),
            )
            for r in cur.fetchall():
                prev = offers.get(r["asin"])
                if prev is None or (r["region_updated_at"] or "") > (prev[1] or ""):
                    offers[r["asin"]] = (r["region_offers_json"], r["region_updated_at"])
        finally:
            conn.close()

    types = load_product_types(asins, marketplace_id)
    fresh_from = (datetime.utcnow() - timedelta(days=FRESH_DAYS)).isoformat()

    stats = defaultdict(lambda: dict.fromkeys(COUNT_KEYS, 0))
    for asin in asins:
        json_text, updated_at = offers.get(asin, (None, None))
        result = _classify(json_text, my_seller_id) or {}
        if result and (updated_at or "") >= fresh_from:
            result["fresh_count"] = 1
        for key in ("", types.get(asin) or "（不明）"):
            s = stats[key]
            s["live_count"] += 1
            for k, v in result.items():
                s[k] += v
    return dict(stats)


# --- ▼ SECTION 02: 日ごとの記録 ▼ ---
def _live_countries(user_id: int) -> list:
    """この環境で LIVE の出品がある国 [(country_code, marketplace_id)]"""
    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT region_marketplace_id FROM listed_items "
            "WHERE user_id = %s AND UPPER(COALESCE(listing_status, '')) = 'LIVE' AND region_marketplace_id IS NOT NULL",
            (user_id,),
        )
        mp_ids = [r["region_marketplace_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    if not mp_ids:
        return []
    conn = get_conn("a_marketplaces_master.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT country_code, marketplace_id FROM marketplaces_master WHERE marketplace_id = ANY(%s)",
            (mp_ids,),
        )
        return [(r["country_code"].upper(), r["marketplace_id"]) for r in cur.fetchall()]
    finally:
        conn.close()


def save_daily_stats(user_id: int, country_code: str, marketplace_id: str, stat_date: str = None) -> dict:
    """その日の分を集計して保存（同じ日は上書き）"""
    stat_date = stat_date or today_jst()
    stats = compute_buybox_stats(user_id, country_code, marketplace_id)
    enabled = 1 if get_category_fee_settings(user_id, country_code)["enabled"] else 0
    now = datetime.utcnow().isoformat()

    conn = get_conn("a_pricing_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM buybox_daily_stats WHERE user_id = %s AND country_code = %s AND stat_date = %s",
            (user_id, country_code, stat_date),
        )
        for ptype, s in stats.items():
            cur.execute(
                f"INSERT INTO buybox_daily_stats (user_id, country_code, stat_date, product_type, "
                f"{', '.join(COUNT_KEYS)}, category_fee_enabled, created_at) "
                f"VALUES (%s, %s, %s, %s, {', '.join(['%s'] * len(COUNT_KEYS))}, %s, %s)",
                (user_id, country_code, stat_date, ptype, *[s[k] for k in COUNT_KEYS],
                 enabled if ptype == "" else None, now),
            )
        conn.commit()
    finally:
        conn.close()
    return stats


def _users_with_listings() -> list:
    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT user_id FROM listed_items "
            "WHERE UPPER(COALESCE(listing_status, '')) = 'LIVE' AND user_id IS NOT NULL"
        )
        return [r["user_id"] for r in cur.fetchall()]
    finally:
        conn.close()


def run_daily_snapshot_if_needed():
    """今日（日本時間）の記録がまだ無い国だけ集計して残す。バックグラウンドのループから呼ぶ"""
    stat_date = today_jst()
    done = 0
    for user_id in _users_with_listings():
        conn = get_conn("a_pricing_settings.db")
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT country_code FROM buybox_daily_stats WHERE user_id = %s AND stat_date = %s",
                (user_id, stat_date),
            )
            recorded = {r["country_code"] for r in cur.fetchall()}
        finally:
            conn.close()
        for country_code, marketplace_id in _live_countries(user_id):
            if country_code in recorded:
                continue
            save_daily_stats(user_id, country_code, marketplace_id, stat_date)
            done += 1
    return done


# --- ▼ SECTION 03: 画面用 ▼ ---
def _rate(part, whole):
    return round(part / whole * 100, 1) if whole else None


def _with_rates(s: dict) -> dict:
    out = dict(s)
    out["buybox_rate"] = _rate(s["buybox_mine"], s["with_data"])
    out["lowest_rate"] = _rate(s["lowest_mine"], s["with_data"])
    out["fresh_rate"] = _rate(s["fresh_count"], s["live_count"])
    return out


def get_buybox_overview(user_id: int, country_code: str, marketplace_id: str, days: int = 60) -> dict:
    """今の数字（その場で集計）と、日ごとの推移（国全体・カテゴリ別手数料率の表の商品タイプ合計）"""
    country_code = country_code.upper()
    current = compute_buybox_stats(user_id, country_code, marketplace_id)
    target_types = [r["product_type"] for r in get_category_fee_settings(user_id, country_code)["rows"]]

    def _sum(stats_by_type, keys):
        total = dict.fromkeys(COUNT_KEYS, 0)
        for t in keys:
            s = stats_by_type.get(t)
            if s:
                for k in COUNT_KEYS:
                    total[k] += s[k] or 0
        return total

    by_type = [
        {"product_type": t, **_with_rates(s)}
        for t, s in current.items() if t
    ]
    by_type.sort(key=lambda r: (-r["live_count"], r["product_type"]))

    since = (datetime.now(JST).date() - timedelta(days=days)).isoformat()
    conn = get_conn("a_pricing_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT stat_date, product_type, {', '.join(COUNT_KEYS)}, category_fee_enabled "
            "FROM buybox_daily_stats WHERE user_id = %s AND country_code = %s AND stat_date >= %s",
            (user_id, country_code, since),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    days_map = defaultdict(dict)
    enabled_map = {}
    for r in rows:
        days_map[r["stat_date"]][r["product_type"]] = {k: r[k] for k in COUNT_KEYS}
        if r["product_type"] == "":
            enabled_map[r["stat_date"]] = r["category_fee_enabled"]

    history = []
    for d in sorted(days_map, reverse=True):
        stats_by_type = days_map[d]
        if "" not in stats_by_type:
            continue
        history.append({
            "date": d,
            "category_fee_enabled": bool(enabled_map.get(d)),
            "all": _with_rates(stats_by_type[""]),
            "target": _with_rates(_sum(stats_by_type, target_types)),
        })

    return {
        "all": _with_rates(current.get("", dict.fromkeys(COUNT_KEYS, 0))),
        "target": _with_rates(_sum(current, target_types)),
        "target_types": target_types,
        "by_type": by_type,
        "history": history,
    }
