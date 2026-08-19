# ==========================================
# ファイル名: amazon\core\price_calculator.py
# 目的: 出品価格算定 中間計算部のみ
# ==========================================

import math
from amazon.db import get_conn
from amazon.shipping_calc import shipping_calc, calc_min_shipping_fee

# --- ▼ SECTION 01: pricing_master_rules 取得 ▼ ---
def get_pricing_master_rule(*, user_id: int, country_code: str):
    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM pricing_master_rules
        WHERE user_id = %s
        AND country_code IN (%s, 'ALL')
        ORDER BY country_code DESC
        LIMIT 1
    """, (user_id, country_code.upper()))

    row = cur.fetchone()

    if not row:
        conn.close()
        return {}

    conn.close()

    return dict(row)

# --- ▼ SECTION 02: 出品価格算出エンジン（純計算専用） ▼ ---
def calculate_listing_price(
    *,
    country_code: str,                                     # 出品国コード（US/AU/SGなど）
    exchange_rate: float,                                  # 
    home_price: float,                                     # 仕入原価（通貨）
    shipping_fee: float,                                   # 国際送料ベース金額（通貨）請求重量にて算定
    amazon_fee_rate: float,                                # Amazon販売手数料率（％）
    min_profit_rate: float,                                # 目標利益率（販売額基準％）
    max_profit_rate: float,                                # 最大利益率（販売額基準％）  
    gst_rate: float,                                       # 消費税率（GST/VAT％）
    tax_mode: str,                                         # 関税計算方式（FOB / CIF / CIF_EX）
    customs_duty_rate: float,                              # 関税率（％）
    oversea_remittance_fee_rate: float,                    # 海外送金手数料率（％）
    fuel_surcharge_rate: float,                            # 燃油サーチャージ率（％）
    shipping_outsource_cost: float,                        # 発送外注費（通貨）           
    extra_cost: float,  ):                                 # その他経費（通貨）
       

    # --- 送料表の重量範囲外（該当行なし）は価格計算不能として扱う ---
    # shipping_fee=None を 0 円扱いすると、送料無しの誤った安値でACTIVE化してしまうため
    if shipping_fee is None:
        return {
            "P_min": None,
            "P_max": None,
            "total_cost": None,
            "breakdown": {
                "home_price": None,
                "intl_shipping": None,
                "packing": None,
                "outsource": None,
                "cif_cost": None,
                "duty": None,
                "amazon_fee_rate": None,
                "gst_rate": None,
                "profit_min_rate": None,
                "profit_max_rate": None,
                "customs_duty_rate": None,
                "remittance_rate": None,
                "fuel_rate": None,
                "exchange_rate": None,
                "denom_min": None,
                "denom_max": None,
            }
        }

    # --- 正規化 ---
    home_price = float(home_price or 0)                    # 仕入原価（通貨）
    shipping_fee = float(shipping_fee)                     # 国際送料ベース（通貨）

    r = float(amazon_fee_rate or 0) / 100                  # Amazon手数料率
    m_min = float(min_profit_rate or 0) / 100              # 目標利益率（販売額基準）
    m_max = float(max_profit_rate or 0) / 100              # 最大利益率（販売額基準）   
    g = float(gst_rate or 0) / 100                         # 消費税率（GST/VAT）
    d = float(customs_duty_rate or 0) / 100                # 関税率
    rem = float(oversea_remittance_fee_rate or 0) / 100    # 送金手数料率
    fuel = float(fuel_surcharge_rate or 0) / 100           # 燃油サーチャージ率

    outsource = float(shipping_outsource_cost or 0)        # 発送外注費
    packing = float(extra_cost or 0)                       # その他経費


    # --- 国際送料補正 ---
    intl_shipping = shipping_fee * (1 + fuel)              # 計算式: 国際送料 = 基本送料 × (1 + 燃油率)

    # --- 関税計算用CIF（正式なCIF） ---
    cif_cost = home_price + intl_shipping                  # 商品代金＋国際送料

    # --- 利益計算用原価（ZSSS独自：経費込み） ---
    pre = home_price + intl_shipping + packing + outsource # 計算式: 利益計算用原価 = 仕入 + 国際送料 + 梱包費 + 外注費

    # --- 関税計算 ---
    if tax_mode == "FOB":
        duty = home_price * d                              # FOB : 関税 = 仕入原価 × 関税率
    elif tax_mode == "CIF":
        duty = cif_cost * d                                # CIF : 関税 = (商品代金＋国際送料) × 関税率 （正式なCIF）

    elif tax_mode == "CIF_EX":                             # 正式なCIFに梱包費・発送外注費を含めた拡張方式 ▼▼ ---
        duty = pre * d                                     # CIF_EX : 関税 =（商品代金＋国際送料＋梱包費＋発送外注費）× 関税率（ZSSS独自）

    # --- 総原価 ---
    total_cost = pre + duty                                # 計算式: 総原価 = 原価 + 関税

    # --- 最低利益価格 ---
    denom_min = 1 - (r * (1 + g)) - g - m_min - rem        # 計算式: 分母 = 1 - (手数料率 × (1 + 税率)) - 税率 - 最低利益率 - 送金手数料率

    if denom_min <= 0:
        return {
            "P_min": None,
            "P_max": None,
            "total_cost": None,
            "breakdown": {
                "home_price": None,
                "intl_shipping": None,
                "packing": None,
                "outsource": None,
                "cif_cost": None,
                "duty": None,
                "amazon_fee_rate": None,
                "gst_rate": None,
                "profit_min_rate": None,
                "profit_max_rate": None,
                "customs_duty_rate": None,
                "remittance_rate": None,
                "fuel_rate": None,
                "exchange_rate": None,
                "denom_min": None,
                "denom_max": None,
            }            

        }

    P_min = total_cost / denom_min                         # 計算式: 最低利益価格 = 総原価 ÷ (1 - r - g - m_min - rem)

    # --- 最大利益価格 ---
    denom_max = 1 - (r * (1 + g)) - g - m_max - rem        # 計算式: 分母 = 1 - (手数料率 × (1 + 税率)) - 税率 - 最大利益率 - 送金手数料率

    if denom_max <= 0:
        return {
            "P_min": None,
            "P_max": None,
            "total_cost": None,
            "breakdown": {
                "home_price": None,
                "intl_shipping": None,
                "packing": None,
                "outsource": None,
                "cif_cost": None,
                "duty": None,
                "amazon_fee_rate": None,
                "gst_rate": None,
                "profit_min_rate": None,
                "profit_max_rate": None,
                "customs_duty_rate": None,
                "remittance_rate": None,
                "fuel_rate": None,
                "exchange_rate": None,
                "denom_min": None,
                "denom_max": None,
            }                       
        }

    P_max = total_cost / denom_max                         # 計算式: 最大利益価格 = 総原価 ÷ (1 - r - g - m_max - rem)

    return {
        "P_min": round(P_min / exchange_rate, 2),          # 最低利益価格
        "P_max": round(P_max / exchange_rate, 2),          # 最大利益価格
        "total_cost": round(total_cost, 2),                # 総原価
        "breakdown": {
            "home_price": home_price,
            "intl_shipping": round(intl_shipping, 2),
            "pre_cost": round(pre, 2),   
            "packing": packing,
            "outsource": outsource,
            "cif_cost": round(cif_cost, 2),
            "duty": round(duty, 2),
            "amazon_fee_rate": r,
            "gst_rate": g,
            "profit_min_rate": m_min,
            "profit_max_rate": m_max,
            "customs_duty_rate": d,
            "remittance_rate": rem,
            "fuel_rate": fuel,

            "exchange_rate": exchange_rate, 

            "denom_min": round(denom_min, 4),
            "denom_max": round(denom_max, 4),            
        }
    } 

# --- ▼ SECTION 03: Shipping共通計算（From：routes_pricing_v2.py / routes_listing.py） ▼ ---
def calculate_shipping_result(normalized, shipping_config, user_id, marketplace_id, SHIPPING_RATE_ROWS, override_weight_g=None):
    """
    override_weight_g: listed_items.override_weight_class（手動上書きの重量帯 To(g)）。
    Amazonカタログの寸法・重量が誤っていて自動算定の請求重量がズレる場合に、
    このASINだけ自動算定をスキップして指定の重量で送料帯を確定させるための値。
    """

    calc_result = shipping_calc(
        normalized,
        shipping_config
    )

    if override_weight_g:
        billable_weight = round(float(override_weight_g) / 1000.0, 3)
    else:
        billable_weight = calc_result["billable_weight_kg_rounded"]

    shipping_fee = calc_min_shipping_fee(
        billable_weight,
        user_id,
        marketplace_id,
        SHIPPING_RATE_ROWS=SHIPPING_RATE_ROWS
    )

    return {
        "calc_result": calc_result,
        "billable_weight": billable_weight,
        "shipping_fee": shipping_fee,
        "weight_override_applied": bool(override_weight_g),
    }

# --- ▼ SECTION 04: shipping_rates取得（From：routes_pricing_v2.py / routes_listing.py / routes_admin.py） ▼ ---
def get_shipping_rate(user_id, marketplace_id):

    conn_ship = get_conn("a_shipping_rates.db")
    cur_ship = conn_ship.cursor()

    cur_ship.execute("""
        SELECT
            weight_from_g,
            weight_to_g,
            carrier_1_price,
            carrier_2_price,
            carrier_3_price,
            fixed_shipping_price
        FROM shipping_rates
        WHERE user_id = %s
        AND marketplace_id = %s
    """, (user_id, marketplace_id))

    shipping_rate = cur_ship.fetchall()

    conn_ship.close()

    return shipping_rate

# --- ▼ SECTION 05: shipping_config取得（From：routes_pricing_v2.py / routes_listing.py / routes_admin.py） ▼ ---
def get_shipping_config(user_id):

    conn_cfg = get_conn("a_pricing_settings.db")
    cur_cfg = conn_cfg.cursor()

    cur_cfg.execute("""
        SELECT padding_cm, pack_ratio, volumetric_divisor
        FROM shipping_config
        WHERE user_id = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """, (user_id,))

    shipping_config = cur_cfg.fetchone()

    conn_cfg.close()

    return shipping_config

