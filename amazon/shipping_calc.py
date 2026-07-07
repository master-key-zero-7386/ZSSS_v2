# ==========================================
# ファイル名: amazon/shipping_calc.py
# 目的: カタログの事実データ（寸法・実重量）に算定条件を適用し、請求重量を算定
# 　　　算定条件・送料表の保存
# ==========================================

import time
import math
from typing import Dict, Optional
from amazon.routes.routes import amazon_bp
from flask import request, jsonify
from datetime import datetime

# --- ▼ SECTION 01: Shipping Config API（取得：最小） ▼ ---
@amazon_bp.route("/get_shipping_config", methods=["GET"])
def get_shipping_config():
    try:
        user_id = int(request.args.get("user_id"))
        # country_code  = request.args.get("country_code")

        from amazon.db import get_conn
        conn = get_conn("a_pricing_settings.db")
        cur = conn.cursor()

        cur.execute("""
            SELECT padding_cm, pack_ratio, volumetric_divisor
            FROM shipping_config
            WHERE user_id=%s
            AND (
                UPPER(country_code)=UPPER(%s)
                OR country_code='ALL'
            )
        """, (user_id, "ALL"))

        row = cur.fetchone()

        conn.close()

        if not row:
            return jsonify({
                "status": "success",
                "data": {
                    "padding_cm": 0,
                    "pack_ratio": 0,
                    "volumetric_divisor": 5000
                }
            }), 200

        return jsonify({
            "status": "success",
            "data": {
                "padding_cm": row["padding_cm"],
                "pack_ratio": row["pack_ratio"],
                "volumetric_divisor": row["volumetric_divisor"],
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 02: 内部ユーティリティ（純計算） ▼ ---
def _calc_volumetric_weight(length_cm: float, width_cm: float, height_cm: float, volumetric_divisor: float,) -> float:
    """
    容積重量算定（事実データは変更しない）
    """
    if not all([length_cm, width_cm, height_cm, volumetric_divisor]):
        return 0.0

    return (length_cm * width_cm * height_cm) / volumetric_divisor

# --- ▼ SECTION 03: 切り上げ丸め処理 ▼ ---
def _round_up_weight(weight_kg: float, round_unit_kg: float) -> float:
    """
    指定単位で切り上げ
    - 1.0kg以下：100g刻み
    - 1.0kg超  ：round_unit_kg（例: 0.5kg）
    """
    if weight_kg <= 0:
        return weight_kg

    # --- ▼ 1.0kg未満 100g刻み ▼ ---
    if weight_kg <= 1.0:
        unit = 0.1
    else:
        unit = round_unit_kg
    # --- ▲ 1.0kg以上 500g刻み ▲ ---

    if unit <= 0:
        return weight_kg

    return math.ceil(weight_kg / unit) * unit

# --- ▼ SECTION 04: Shipping 重量算定（公開API） ▼ ---
def shipping_calc(normalized: Dict, shipping_config: Dict, override: Optional[Dict] = None,) -> Dict:
    """
    純算定（DB / API / UI 非依存）
    """

    # --- ① 事実データ ---
    length_cm = float(normalized.get("length_cm") or 0.0)  
    width_cm  = float(normalized.get("width_cm") or 0.0)  
    height_cm = float(normalized.get("height_cm") or 0.0)  
    actual_weight_kg = float(normalized.get("actual_weight_kg") or 0.0) 

    # --- ② 算定条件 ---
    volumetric_divisor = float(shipping_config.get("volumetric_divisor", 5000.0))
    round_unit_kg   = 0.5
    min_billable_kg = 0.1

    # ★ 補正値（今回の本命）
    padding_cm = float(shipping_config.get("padding_cm", 0.0))
    pack_ratio_percent = float(shipping_config.get("pack_ratio", 0.0))
    pack_ratio = 1 + (pack_ratio_percent / 100) 

    # --- ③ 実重量補正（重量補正） ---
    corrected_actual_weight_kg = actual_weight_kg * pack_ratio

    # --- ④ 寸法補正（容積重量用） ---
    corrected_length_cm = length_cm + padding_cm
    corrected_width_cm  = width_cm  + padding_cm
    corrected_height_cm = height_cm + padding_cm

    # --- ⑤ 容積重量（寸法補正後） ---
    volumetric_weight_kg = _calc_volumetric_weight(
        corrected_length_cm,
        corrected_width_cm,
        corrected_height_cm,
        volumetric_divisor,
    )

    # --- ⑥ 請求重量（未丸め） ---
    billable_weight_kg = max(
        corrected_actual_weight_kg,
        volumetric_weight_kg,
        min_billable_kg,
    )

    # --- ⑦ 請求重量（丸め後） ---
    billable_weight_kg_rounded = _round_up_weight(
        billable_weight_kg,
        round_unit_kg,
    )

    return {
        # 事実
        "actual_weight_kg": round(actual_weight_kg, 3),
        "actual_weight_kg_corrected": round(corrected_actual_weight_kg, 3),

        # 容積
        "volumetric_weight_kg": round(volumetric_weight_kg, 3),

        # 請求重量
        "billable_weight_kg": round(billable_weight_kg, 3),
        "billable_weight_kg_rounded": round(billable_weight_kg_rounded, 3),
    }

# --- ▼ SECTION 05: Shipping Config API（保存：最小） ▼ ---
@amazon_bp.route("/update_shipping_config", methods=["POST"])
def update_shipping_config():
    try:
        data = request.get_json(force=True) or {}
        user_id = int(data.get("user_id"))
        # country_code  = data.get("country_code") #TopページPricing設定を国別で個別に保存する場合は戻す
        country_code = "ALL"

        padding_cm = data.get("padding_cm")
        pack_ratio = data.get("pack_ratio")
        volumetric_divisor = data.get("volumetric_divisor")

        from amazon.db import get_conn
        conn = get_conn("a_pricing_settings.db")
        cur = conn.cursor()

        now_utc = datetime.utcnow().isoformat() 

        # upsert（SQLite）
        cur.execute("""
            INSERT INTO shipping_config (user_id, country_code, padding_cm, pack_ratio, volumetric_divisor, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(user_id, country_code) DO UPDATE SET
              padding_cm=excluded.padding_cm,
              pack_ratio=excluded.pack_ratio,
              volumetric_divisor=excluded.volumetric_divisor,
              updated_at=%s
        """, (user_id, country_code, padding_cm, pack_ratio, volumetric_divisor, now_utc, now_utc))

        conn.commit()
        conn.close()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ▼ SECTION 06: Shipping 送料算定（表示用・最安） ▼ ---
def calc_min_shipping_fee(billable_weight_kg: float, user_id: int, marketplace_id: str, SHIPPING_RATE_ROWS=None) -> float | None:
    """
    請求重量(kg)から送料表を引き、送料を返す（価格計算用）
    - DB保存なし
    - 固定送料（fixed_shipping_price）が設定されていればそれを優先
    - 未設定なら carrier_1/2/3 の最安を返す（従来通り）
    """
    if not billable_weight_kg or billable_weight_kg <= 0:
        return None

    SHIPPING_RATE_ROWS = SHIPPING_RATE_ROWS or []  

    weight_g = int(round(billable_weight_kg * 1000))

    row = None 

    for r in SHIPPING_RATE_ROWS: 

        if (
            r["weight_from_g"] <= weight_g
            and
            r["weight_to_g"] >= weight_g
        ):
            row = r
            break    

    if not row:
        return None

    # --- ▼ 固定送料が設定されていれば、それを最優先で採用 ▼ ---
    fixed = row.get("fixed_shipping_price")
    if fixed is not None:
        try:
            fixed_value = float(fixed)
            if fixed_value > 0:
                return fixed_value
        except (TypeError, ValueError):
            pass  # 万一おかしな値でもここでは無視し、下の従来計算にフォールバック

    # --- ▼ 固定送料が無ければ、従来通りCarrier1〜3の最安値 ▼ ---
    prices = [
        float(row["carrier_1_price"]),
        float(row["carrier_2_price"]),
        float(row["carrier_3_price"])
    ]  

    prices = [p for p in prices if p > 0]  
    return min(prices) if prices else None
