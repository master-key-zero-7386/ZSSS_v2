# =====================================================
# ファイル名: amazon/pricing_calc.py
# 目的: Pricing の最終算定（今は最小：HOME最安だけ）
#   ※DB更新・API取得はしない
# =====================================================

from __future__ import annotations
from typing import Any, Dict, Optional

def calc_home_pricing(selected_offer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    今は暫定：selected_offer から home_price を作るだけ
    将来：手数料/利益/関税/送料などを合成する中心になる
    """
    if not selected_offer:
        return {"home_price": None}

    item = selected_offer.get("price_amount")
    ship = selected_offer.get("shipping_amount") or 0

    try:
        if item is None:
            return {"home_price": None}
        home_price = float(item) + float(ship)
        return {"home_price": home_price}
    except Exception:
        return {"home_price": None}



