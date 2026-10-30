# ==========================================
# ファイル名: amazon\core\category_fee.py
# 目的: カテゴリ別手数料率 ― 商品タイプ（カタログの productType）ごとに、
#       値段の計算に使う「Amazon手数料率」と「最低利益率」を置き換える。
#   - 国ごとの ON/OFF（pricing_category_fee_settings）。OFF の国と、表に無い商品タイプは
#     pricing_master_rules のまま（値段は1円も変わらない）
#   - 手数料率は pricing_master_rules.amazon_fee_rate と同じ意味（式の中で ×(1+税率) される）。
#     Amazon の手数料表の%をそのまま入れれば、決済の実績と合う（AU のおもちゃ 12%・CA 15%）
#   - 最初に画面を開いた国には、おもちゃ系の商品タイプを OFF のまま入れておく
#   - 決済の実績（参考）は amazon/adapters/orbit_category_fee.py
# ==========================================

import json
from datetime import datetime

from amazon.db import get_conn

# 決済の実績で手数料14.5〜15%だったおもちゃ系（2026年8〜10月の AU・CA）
DEFAULT_PRODUCT_TYPES = [
    "TOY_FIGURE", "FIGURINE", "TOYS_AND_GAMES", "COLLECTIBLE_CARD", "ART_CRAFT_KIT",
    "NON_RIDING_TOY_VEHICLE", "TOY_VEHICLE_SET", "PRETEND_PLAY_TOY", "TABLETOP_GAME",
]
DEFAULT_FEE_RATES = {"AU": 12.0, "CA": 15.0, "US": 15.0}
DEFAULT_MIN_PROFIT_RATE = 0.0


# --- ▼ SECTION 01: 設定の読み書き ▼ ---
def _seed_defaults(cur, user_id: int, country_code: str):
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO pricing_category_fee_settings (user_id, country_code, enabled, updated_at) "
        "VALUES (%s, %s, 0, %s) ON CONFLICT (user_id, country_code) DO NOTHING",
        (user_id, country_code, now),
    )
    fee = DEFAULT_FEE_RATES.get(country_code)
    if fee is None:
        return
    for pt in DEFAULT_PRODUCT_TYPES:
        cur.execute(
            "INSERT INTO pricing_category_fee_rules "
            "(user_id, country_code, product_type, fee_rate, min_profit_rate, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (user_id, country_code, product_type) DO NOTHING",
            (user_id, country_code, pt, fee, DEFAULT_MIN_PROFIT_RATE, now),
        )


def get_category_fee_settings(user_id: int, country_code: str, *, seed: bool = False) -> dict:
    """{enabled: bool, rows: [{product_type, fee_rate, min_profit_rate}]}。seed=True なら初回に既定を入れる"""
    country_code = (country_code or "").upper()
    conn = get_conn("a_pricing_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT enabled FROM pricing_category_fee_settings WHERE user_id = %s AND country_code = %s",
            (user_id, country_code),
        )
        row = cur.fetchone()
        if row is None and seed:
            _seed_defaults(cur, user_id, country_code)
            conn.commit()
        cur.execute(
            "SELECT product_type, fee_rate, min_profit_rate FROM pricing_category_fee_rules "
            "WHERE user_id = %s AND country_code = %s ORDER BY product_type",
            (user_id, country_code),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return {"enabled": bool(row and row["enabled"]), "rows": rows}


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def save_category_fee_settings(user_id: int, country_code: str, enabled: bool, rows: list) -> dict:
    """表を丸ごと入れ替える（画面に無い商品タイプは消える）"""
    country_code = (country_code or "").upper()
    now = datetime.utcnow().isoformat()
    clean = {}
    for r in rows or []:
        pt = (r.get("product_type") or "").strip().upper()
        if pt:
            clean[pt] = (_num(r.get("fee_rate")), _num(r.get("min_profit_rate")))

    conn = get_conn("a_pricing_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pricing_category_fee_settings (user_id, country_code, enabled, updated_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, country_code) "
            "DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = EXCLUDED.updated_at",
            (user_id, country_code, 1 if enabled else 0, now),
        )
        cur.execute(
            "DELETE FROM pricing_category_fee_rules WHERE user_id = %s AND country_code = %s",
            (user_id, country_code),
        )
        for pt, (fee, m_min) in clean.items():
            cur.execute(
                "INSERT INTO pricing_category_fee_rules "
                "(user_id, country_code, product_type, fee_rate, min_profit_rate, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, country_code, pt, fee, m_min, now),
            )
        conn.commit()
    finally:
        conn.close()
    return get_category_fee_settings(user_id, country_code)


# --- ▼ SECTION 02: 商品タイプの取得（この環境の catalog_cache。REGION を優先、無ければ HOME） ▼ ---
def _types_from_json(text, marketplace_id):
    if not text:
        return None, None
    try:
        types = json.loads(text).get("productTypes") or []
    except (TypeError, ValueError, AttributeError):
        return None, None
    exact = next((t.get("productType") for t in types if t.get("marketplaceId") == marketplace_id), None)
    first = next((t.get("productType") for t in types if t.get("productType")), None)
    return exact, first


def load_product_types(asins, marketplace_id: str) -> dict:
    """{asin: 商品タイプ}（その国の分 ＞ 他の国の分）"""
    asins = [a for a in set(asins or []) if a]
    if not asins:
        return {}
    conn = get_conn("a_catalog_cache.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT asin, region_raw_json, home_raw_json FROM catalog_cache WHERE asin = ANY(%s)",
            (asins,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    exact, fallback = {}, {}
    for r in rows:
        for text in (r["region_raw_json"], r["home_raw_json"]):
            e, f = _types_from_json(text, marketplace_id)
            if e:
                exact.setdefault(r["asin"], e)
            if f:
                fallback.setdefault(r["asin"], f)
    return {a: exact.get(a) or fallback.get(a) for a in asins if exact.get(a) or fallback.get(a)}


# --- ▼ SECTION 03: 値段の計算への適用 ▼ ---
def apply_category_fee(rules: dict, *, user_id: int, country_code: str, asin: str, marketplace_id: str) -> dict:
    """ON の国で、その ASIN の商品タイプが表にあれば、手数料率・最低利益率を置き換えた rules のコピーを返す。
    それ以外は rules をそのまま返す（OFF の間は値段の計算に何の影響も無い）"""
    if not rules or not asin:
        return rules
    # 出品の値段の計算を止めないよう、ここで失敗したら今の設定のまま計算する
    try:
        settings = get_category_fee_settings(user_id, country_code)
        if not settings["enabled"] or not settings["rows"]:
            return rules
        ptype = load_product_types([asin], marketplace_id).get(asin)
    except Exception as e:
        print(f"[category_fee] apply_category_fee skipped ({country_code} {asin}): {e}")
        return rules
    rule = next((r for r in settings["rows"] if r["product_type"] == ptype), None) if ptype else None
    if not rule:
        return rules

    out = dict(rules)
    if rule["fee_rate"] is not None:
        out["amazon_fee_rate"] = rule["fee_rate"]
    if rule["min_profit_rate"] is not None:
        out["min_profit_rate"] = rule["min_profit_rate"]
    out["category_fee_product_type"] = ptype
    return out


# --- ▼ SECTION 04: 試算（ON にしたら最低価格が何%変わるか。値段も DB も変えない） ▼ ---
# 最低価格 P_min = 総原価 ÷ 分母 ÷ 為替 なので、同じ商品なら 新P_min ÷ 旧P_min ＝ 旧分母 ÷ 新分母。
# 商品タイプごとに一律の%になる。最低価格で出品中（final_price ≒ min_price）の商品はこの%だけ値段が上がる。
def _denom(fee_rate, min_profit_rate, rules):
    r = float(fee_rate or 0) / 100
    g = float(rules.get("gst_rate") or 0) / 100
    m = float(min_profit_rate or 0) / 100
    rem = float(rules.get("oversea_remittance_fee_rate") or 0) / 100
    return 1 - (r * (1 + g)) - g - m - rem


def simulate_category_fee(user_id: int, country_code: str, marketplace_id: str, rows: list, base_rules: dict) -> dict:
    country_code = (country_code or "").upper()
    rule_map = {}
    for r in rows or []:
        pt = (r.get("product_type") or "").strip().upper()
        if pt:
            rule_map[pt] = r

    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT asin, final_price, min_price FROM listed_items "
            "WHERE user_id = %s AND region_marketplace_id = %s AND UPPER(COALESCE(listing_status, '')) = 'LIVE'",
            (user_id, marketplace_id),
        )
        items = cur.fetchall()
    finally:
        conn.close()

    types = load_product_types([i["asin"] for i in items], marketplace_id)
    old_denom = _denom(base_rules.get("amazon_fee_rate"), base_rules.get("min_profit_rate"), base_rules)

    result = {}
    for pt, r in rule_map.items():
        fee = _num(r.get("fee_rate"))
        m_min = _num(r.get("min_profit_rate"))
        new_denom = _denom(
            base_rules.get("amazon_fee_rate") if fee is None else fee,
            base_rules.get("min_profit_rate") if m_min is None else m_min,
            base_rules,
        )
        change = round((old_denom / new_denom - 1) * 100, 1) if new_denom > 0 and old_denom > 0 else None
        result[pt] = {"product_type": pt, "live": 0, "at_floor": 0, "change_pct": change}

    for i in items:
        pt = types.get(i["asin"])
        if pt not in result:
            continue
        result[pt]["live"] += 1
        try:
            fp, mp = float(i["final_price"]), float(i["min_price"])
            if mp > 0 and abs(fp - mp) <= 0.011:
                result[pt]["at_floor"] += 1
        except (TypeError, ValueError):
            pass

    rows_out = sorted(result.values(), key=lambda x: (-x["live"], x["product_type"]))
    return {
        "live_total": len(items),
        "rows": rows_out,
        "affected": sum(x["live"] for x in rows_out),
        "affected_at_floor": sum(x["at_floor"] for x in rows_out),
    }
