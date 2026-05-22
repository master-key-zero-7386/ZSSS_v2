# ==========================================
# ファイル名: amazon/core/pricing_strategy.py
# 目的: 純レンジ戦略ロジック（価格決定のみ）
# ==========================================

# --- ▼ SECTION 01: pricing_master_rules 取得 ▼ ---
def decide_listing_price(*, P_min: float, P_max: float, competitor_price: float | None, competitor_api_enabled: bool, discount_rate: float = 0,):
    """
    最終出品価格（base_price）を決定する。

    ・API OFF → P_min
    ・API ON + 競合なし → P_min
    ・競合価格あり → レンジ内で決定

    ※ 利益保証は price_calculator 側責務
    ※ 心理価格はこの層では行わない
    ※ 出品可否判定は行わない
    """

    # --- 型統一 ---
    if P_min is None:
        return None 

    P_min = float(P_min)
    P_max = float(P_max)

    if competitor_price is not None:
        competitor_price = float(competitor_price)

    # --- API OFF または 競合なし ---
    if not competitor_api_enabled or competitor_price is None:
        return P_min

    # --- 競合価格レンジ判定 ---
    if competitor_price < P_min:
        return P_min

    if competitor_price > P_max:
        competitor_price = P_max 

    # --- 最終価格（P_min基準） ---
    price = P_min  # ←ここを修正

    # --- 競合反映 ---
    comp_price = competitor_price * (1 - discount_rate / 100)

    if comp_price > price:
        price = comp_price

    # --- 上限制御 ---
    if price > P_max:
        price = P_max

    return round(price, 2)
