# ==========================================
# ファイル名: amazon/core/price_calculator.py
# 目的: 出品価格算定 中間計算部のみ
# ==========================================

import math
import sqlite3
from amazon.db_migrate import DB_DIR
from amazon.db import get_conn 

# --- ▼ SECTION 01: pricing_master_rules 取得 ▼ ---
def get_pricing_master_rule(*, user_id: int, country_code: str):
    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM pricing_master_rules
        WHERE user_id = ?
        AND country_code IN (?, 'ALL')
        ORDER BY country_code DESC
        LIMIT 1
    """, (user_id, country_code))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None

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
    tax_mode: str,                                         # 関税計算方式（FOB / CIF）
    customs_duty_rate: float,                              # 関税率（％）
    oversea_remittance_fee_rate: float,                    # 海外送金手数料率（％）
    fuel_surcharge_rate: float,                            # 燃油サーチャージ率（％）
    shipping_outsource_cost: float,                        # 発送外注費（通貨）           
    extra_cost: float,  ):                                 # その他経費（通貨）
       

    # --- 正規化 ---
    home_price = float(home_price or 0)                    # 仕入原価（通貨）
    shipping_fee = float(shipping_fee or 0)                # 国際送料ベース（通貨）

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

    # --- CIF原価（発送前原価） ---
    pre = home_price + intl_shipping + packing + outsource # 計算式: CIF原価 = 仕入 + 国際送料 + 梱包費 + 外注費

    # --- 関税計算 ---
    if tax_mode == "FOB":
        duty = home_price * d                              # 計算式: 関税 = 仕入原価 × 関税率（FOB方式）
    else:
        duty = pre * d                                     # 計算式: 関税 = CIF原価 × 関税率（CIF方式）

    # --- 総原価 ---
    total_cost = pre + duty                                # 計算式: 総原価 = CIF原価 + 関税

    # --- 最低利益価格 ---
    denom_min = 1 - (r * (1 + g)) - g - m_min - rem        # 計算式: 分母 = 1 - (手数料率 × (1 + 税率)) - 税率 - 最低利益率 - 送金手数料率
    # print("DENOM DEBUG:", r, g, m_min, rem)  # // チェック完了後削除

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
    # print("DENOM MAX DEBUG:", r, g, m_max, rem, denom_max)  # // チェック完了後削除

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
            "packing": packing,
            "outsource": outsource,
            "cif_cost": round(pre, 2),
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


