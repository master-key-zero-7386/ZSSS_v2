# ==========================================
# ファイル名: amazon\core\pricing_strategy.py
# 目的: 純レンジ戦略ロジック（価格決定のみ）
# ==========================================

# --- ▼ SECTION 01: pricing_master_rules 取得 ▼ ---
def decide_listing_price(*, P_min: float, P_max: float, competitor_price: float | None, competitor_api_enabled: bool, discount_rate: float = 0,):
    """
    最終出品価格（base_price）を決定する。

    ・競合なし（API OFF 含む） → P_max
        他社がいないのにわざわざ安く売る必要はないので、最大利益価格で出す。
    ・競合あり → 競合価格 ×（1 − 値下げ率）に沿う。ただし P_min より下げない。
        P_max では止めない。他社が高いのにこちらだけ極端に安いと、Amazon に
        「Potential low-pricing error」で出品を止められるため（2026-11-18 AU 本で発生）。
        高くなりすぎた場合は呼び出し側の絶対上限（max_listing_price_limit）・
        COMPETITOR_RATIO の INACTIVE 判定で止める。

    ※ 利益保証は price_calculator 側責務
    ※ 心理価格はこの層では行わない
    ※ 出品可否判定は行わない
    """

    # --- 型統一 ---
    if P_min is None:
        return None

    P_min = float(P_min)
    P_max = float(P_max) if P_max is not None else P_min

    # --- 競合なし（API OFF 含む）→ 最大利益価格 ---
    if not competitor_api_enabled or competitor_price is None:
        return round(max(P_max, P_min), 2)

    # --- 競合に沿う（P_min が下限、上は P_max で止めない） ---
    comp_price = float(competitor_price) * (1 - discount_rate / 100)

    return round(max(comp_price, P_min), 2)
