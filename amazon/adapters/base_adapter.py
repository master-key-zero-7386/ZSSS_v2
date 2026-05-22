# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/adapters/base_adapter.py
# 目的： 共通 API（各プラットフォームに共通するインタフェース定義）
# ==========================================================

# 共通 API（各プラットフォームに共通するインタフェース定義）
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BaseMarketplaceAdapter(ABC):
    @abstractmethod
    def update_price(
        self,
        product_id: str,
        price: float,
        currency: str,
        region: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """単品の価格を更新する。戻り値はPFごとの結果ペイロード。"""
        raise NotImplementedError

class PricingAdapter(ABC):
    @abstractmethod
    def get_item_offers(self, asin: str, region: str) -> dict:
        """
        返却形式：
        {
            "price_cart_jpy": float|None,
            "price_lowest_new_jpy": float|None,
            "price_lowest_used_jpy": float|None,
        }
        """
        raise NotImplementedError

class CatalogAdapter(ABC):
    @abstractmethod
    def get_dimensions(self, asin: str, region: str) -> Dict[str, Any]:
        """
        Catalog Items などから item/package の寸法・重量を返す。
        返却例:
        {
            "itemDimensions": {"length": float|None, "width": float|None, "height": float|None, "unit": "centimeters"},
            "packageDimensions": {"length": ..., "width": ..., "height": ..., "unit": "centimeters"},
            "itemWeight": {"value": float|None, "unit": "kilograms"},
            "packageWeight": {"value": float|None, "unit": "kilograms"},
        }
        取得失敗時は各フィールドを None にして返す（呼び出し側で制御）。
        """
        raise NotImplementedError


        