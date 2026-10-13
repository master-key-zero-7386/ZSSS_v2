# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/services/orbit_ship_check_service.py
# 目的: ORBIT 送料検証（出品時の想定送料・請求重量と、発送代行会社の実績を突き合わせて大きな外れを拾う）
#   ① 想定送料とのズレ  : 想定送料(全部込み) vs 代行 送料合計(T列・全部込み)
#   ② キャリアによる差  : 代行 送料(S列・運賃のみ) vs 実重量で送料表を引いた他キャリアの最安
#   ③ 請求重量のズレ    : 想定請求重量 vs 代行の確定重量(P列)／未確定なら発送重量(N列)
#   - 細かいズレはキャリア選択の都合で必ず出るので、設定の基準を超えたものだけ警告にする
#   - 同梱（同梱先指定・オプションに「同梱」）とキャンセルは対象外（1件あたりの送料が歪むため）
#   - 代行シートの重量はグラム（TEXT）、ZSSS側の請求重量は kg
#   - S列は送料表の値そのまま（燃油等は乗らない）ことを実データで確認済み → ②は送料表の生値どうしで比べる
# ==========================================================

import re
from datetime import datetime

from amazon.db import get_conn
from amazon.core.price_calculator import find_shipping_rate_row

CANCEL_SHIPPING_TYPE = "キャンセル"

DEFAULT_SETTINGS = {
    "fee_diff_yen": 1500.0,     # ① 実際 − 想定 が 1,500円以上
    "fee_diff_pct": 30.0,       #    かつ 30%以上
    "carrier_diff_yen": 1000.0, # ② 実際の運賃 − 他キャリア最安 が 1,000円以上
    "weight_ratio": 1.5,        # ③ 実重量 ÷ 想定 が 1.5倍以上
    "weight_diff_kg": 1.0,      #    かつ 差が 1kg以上
}
SETTING_KEYS = list(DEFAULT_SETTINGS.keys())


# --- ▼ SECTION 01: 基準（設定）の取得・保存 ▼ ---
def get_ship_check_settings(user_id: int) -> dict:
    conn = get_conn("a_orbit_ship_check_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {', '.join(SETTING_KEYS)} FROM orbit_ship_check_settings WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    settings = dict(DEFAULT_SETTINGS)
    if row:
        for k in SETTING_KEYS:
            if row.get(k) is not None:
                settings[k] = float(row[k])
    return settings


def save_ship_check_settings(user_id: int, data: dict) -> dict:
    values = {}
    for k in SETTING_KEYS:
        try:
            v = float(data.get(k))
        except (TypeError, ValueError):
            v = DEFAULT_SETTINGS[k]
        values[k] = v if v >= 0 else DEFAULT_SETTINGS[k]

    cols = ", ".join(SETTING_KEYS)
    placeholders = ", ".join(["%s"] * len(SETTING_KEYS))
    updates = ", ".join(f"{k} = EXCLUDED.{k}" for k in SETTING_KEYS)
    conn = get_conn("a_orbit_ship_check_settings.db")
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            INSERT INTO orbit_ship_check_settings (user_id, {cols}, updated_at)
            VALUES (%s, {placeholders}, %s)
            ON CONFLICT (user_id) DO UPDATE SET {updates}, updated_at = EXCLUDED.updated_at
            """,
            (user_id, *[values[k] for k in SETTING_KEYS], datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return values


# --- ▼ SECTION 02: 小さな変換 ▼ ---
def _num(value):
    """"¥4,180" / "2000" / 4180.0 → float。読めなければ None。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_carrier(shipping_type):
    """発送種別（"FedEx_DDP_…" / "DHL_DAP…" / "EMS"）→ "DHL" / "FedEx" / "EMS"。不明は None。"""
    head = (shipping_type or "").strip().split("_")[0].strip().upper()
    if head.startswith("DHL"):
        return "DHL"
    if head.startswith("FEDEX"):
        return "FedEx"
    if head.startswith("EMS"):
        return "EMS"
    return None


def carrier_prices(rate_row, names) -> dict:
    """送料表1行 → {キャリア名: 運賃}。0・空欄と「その他」は除く（同名が2列あれば安い方）。"""
    prices = {}
    if not rate_row:
        return prices
    for i in range(3):
        name = names[i] if i < len(names) else None
        price = _num(rate_row.get(f"carrier_{i + 1}_price"))
        if not name or name == "その他" or not price or price <= 0:
            continue
        if name not in prices or price < prices[name]:
            prices[name] = price
    return prices


def estimated_carrier(weight_kg, rate_rows, names):
    """出品時の送料計算で採用されるキャリア（固定送料なら「固定」）。"""
    if not weight_kg:
        return None
    row = find_shipping_rate_row(int(round(float(weight_kg) * 1000)), rate_rows)
    if not row:
        return None
    fixed = _num(row.get("fixed_shipping_price"))
    if fixed and fixed > 0:
        return "固定"
    prices = carrier_prices(row, names)
    if not prices:
        return None
    return min(prices, key=prices.get)


def bundled_serials(rows) -> set:
    """同梱グループに入っているN番（親として指定された番号＋指定した側）。"""
    parents = {r.get("bundle_parent_no") for r in rows if r.get("bundle_parent_no")}
    children = {r.get("agent_serial_no") for r in rows if r.get("bundle_parent_no")}
    return {s for s in (parents | children) if s}


def _fmt_yen(v):
    return f"¥{int(round(v)):,}"


# --- ▼ SECTION 03: 1注文分の判定 ▼ ---
def compute_ship_check(row, *, rate_rows, names, settings, bundle_serials=frozenset()) -> dict:
    """row は orbit_orders（または orbit_procurement_history）の行に計算値が載ったもの。"""
    qty = int(_num(row.get("quantity_purchased")) or 1)
    est_is_snapshot = bool(row.get("est_snapshot_at"))
    if est_is_snapshot:
        est_fee = _num(row.get("est_shipping_fee"))
        est_weight = _num(row.get("est_billable_weight_kg"))
        est_carrier = row.get("est_carrier")
    else:
        est_fee = _num(row.get("predicted_shipping_fee"))
        est_weight = _num(row.get("billable_weight_kg"))
        est_carrier = row.get("est_carrier_live")

    confirmed_g = _num(row.get("agent_confirmed_weight"))
    shipping_g = _num(row.get("agent_shipping_weight"))
    actual_g = confirmed_g or shipping_g
    actual_weight = actual_g / 1000.0 if actual_g else None
    # 出荷前は代行シートの送料欄が 0 のことがある → 実績なしとして扱う
    fee_base = _num(row.get("agent_shipping_fee")) or None
    fee_total = _num(row.get("agent_shipping_fee_total")) or None
    actual_carrier = normalize_carrier(row.get("shipping_type"))
    prices_at_actual = carrier_prices(find_shipping_rate_row(int(actual_g), rate_rows), names) if actual_g else {}
    carrier_inferred = False
    if not actual_carrier and fee_base:
        # 発送種別が空欄でも、運賃（S列＝送料表の値そのまま）と一致するキャリアが1つだけならそれと推定する
        matches = [n for n, p in prices_at_actual.items() if abs(p - fee_base) < 0.5]
        if len(matches) == 1:
            actual_carrier, carrier_inferred = matches[0], True

    res = {
        "qty": qty,
        "est_fee": est_fee, "est_weight_kg": est_weight, "est_carrier": est_carrier,
        "est_is_snapshot": est_is_snapshot,
        "actual_carrier": actual_carrier, "actual_carrier_inferred": carrier_inferred,
        "actual_weight_kg": actual_weight,
        "weight_confirmed": bool(confirmed_g),
        "actual_fee_base": fee_base, "actual_fee_total": fee_total,
        "excluded": None,
        "fee_diff": None, "fee_diff_pct": None, "fee_warn": False, "fee_under": False,
        "carrier_best": None, "carrier_best_price": None, "carrier_diff": None, "carrier_warn": False,
        "carrier_table": {},
        "weight_diff_kg": None, "weight_ratio": None, "weight_warn": False, "weight_under": False,
        "tips": [],
    }

    if (row.get("shipping_type") or "").strip() == CANCEL_SHIPPING_TYPE:
        res["excluded"] = "キャンセル"
        return res
    serial = row.get("agent_serial_no")
    if (serial and serial in bundle_serials) or row.get("bundle_parent_no") \
            or "同梱" in (row.get("agent_option_content") or ""):
        res["excluded"] = "同梱"
        return res

    # ① 想定送料（全部込み）vs 送料合計
    if est_fee and fee_total is not None:
        diff = fee_total - est_fee
        pct = diff / est_fee * 100
        res["fee_diff"], res["fee_diff_pct"] = diff, pct
        if diff >= settings["fee_diff_yen"] and pct >= settings["fee_diff_pct"]:
            res["fee_warn"] = True
            res["tips"].append(f"送料: 想定{_fmt_yen(est_fee)} → 実際{_fmt_yen(fee_total)}（+{_fmt_yen(diff)} / +{pct:.0f}%）")
        elif -diff >= settings["fee_diff_yen"] and -pct >= settings["fee_diff_pct"]:
            res["fee_under"] = True

    # ② 実重量で送料表を引き、実際のキャリアの運賃と他キャリアの最安を比べる
    if actual_g:
        prices = prices_at_actual
        res["carrier_table"] = prices
        others = {n: p for n, p in prices.items() if n != actual_carrier}
        actual_cost = fee_base if fee_base is not None else prices.get(actual_carrier)
        if others and actual_cost is not None:
            best = min(others, key=others.get)
            res["carrier_best"], res["carrier_best_price"] = best, others[best]
            diff = actual_cost - others[best]
            res["carrier_diff"] = diff
            if diff >= settings["carrier_diff_yen"]:
                res["carrier_warn"] = True
                used = actual_carrier or "実際"
                res["tips"].append(f"キャリア: {best}なら{_fmt_yen(others[best])}（{used} {_fmt_yen(actual_cost)}、+{_fmt_yen(diff)}）")

    # ③ 請求重量（数量2以上は1個分と比べられないので対象外）
    if est_weight and actual_weight and qty == 1:
        diff = actual_weight - est_weight
        ratio = actual_weight / est_weight
        res["weight_diff_kg"], res["weight_ratio"] = diff, ratio
        if ratio >= settings["weight_ratio"] and diff >= settings["weight_diff_kg"]:
            res["weight_warn"] = True
            res["tips"].append(f"重量: 想定{est_weight:g}kg → 実際{actual_weight:g}kg（×{ratio:.1f}）")
        elif est_weight / actual_weight >= settings["weight_ratio"] and -diff >= settings["weight_diff_kg"]:
            res["weight_under"] = True

    return res


# --- ▼ SECTION 04: 発注管理の行へ判定結果を載せる（_apply_calc_to_rows から呼ぶ） ▼ ---
def apply_ship_checks(user_id: int, rows: list, *, rate_cache: dict, names_cache: dict, settings=None):
    """rate_cache / names_cache は {marketplace_id: ...}。足りない分はここで読む。"""
    from amazon.core.price_calculator import get_shipping_rate, get_carrier_names

    settings = settings or get_ship_check_settings(user_id)
    bundles = bundled_serials(rows)
    for row in rows:
        mp = row.get("marketplace_id")
        if mp and mp not in rate_cache:
            rate_cache[mp] = get_shipping_rate(user_id, mp)
        if mp and mp not in names_cache:
            names_cache[mp] = get_carrier_names(user_id, mp)
        check = compute_ship_check(
            row,
            rate_rows=rate_cache.get(mp) or [],
            names=names_cache.get(mp) or [],
            settings=settings,
            bundle_serials=bundles,
        )
        row["ship_check"] = check
        # 発注管理の赤字・太字用（値＝ツールチップ文言）
        tips = check["tips"]
        row["ship_warn_fee"] = next((t for t in tips if t.startswith("送料")), None) if check["fee_warn"] else None
        row["ship_warn_carrier"] = next((t for t in tips if t.startswith("キャリア")), None) if check["carrier_warn"] else None
        row["ship_warn_weight"] = next((t for t in tips if t.startswith("重量")), None) if check["weight_warn"] else None
    return rows


# --- ▼ SECTION 05: 送料検証タブの一覧（発注管理の注文＋アーカイブ済みの仕入れ履歴） ▼ ---
_LIST_KEYS = [
    "order_item_id", "order_id", "agent_serial_no", "asin", "sku", "product_name",
    "marketplace_country", "ship_country", "shipping_type", "purchase_date",
    "agent_weight_recorded_date", "profit_rate_pct",
]


def list_ship_checks(user_id: int) -> dict:
    # 循環import回避（orbit_order_service がこのモジュールを import している）
    from amazon.services.orbit_order_service import list_orders_with_calc, list_procurement_history_with_calc

    rows = list_orders_with_calc(user_id) + list_procurement_history_with_calc(user_id)
    out = []
    for r in rows:
        check = r.get("ship_check")
        if not check:
            continue
        # 代行会社の実績（送料か重量）が何も無い行は検証できないので出さない
        if check["actual_fee_total"] is None and check["actual_weight_kg"] is None:
            continue
        item = {k: r.get(k) for k in _LIST_KEYS}
        item["archived"] = bool(r.get("archived_at"))
        item.update(check)
        out.append(item)

    out.sort(key=lambda x: (x.get("agent_serial_no") or 0), reverse=True)
    return {"rows": out, "settings": get_ship_check_settings(user_id)}
