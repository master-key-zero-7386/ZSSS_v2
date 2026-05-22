# =====================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/catalog_image_extractor.py
# 目的：カタログ　画像情報専用探索 PY 
# =====================================================

import json
from amazon.adapters.amazon_adapter import AmazonAdapter


class CatalogImageExtractor:
    def __init__(self, user_id: int, region: str):
        # 認証・署名のみを委譲（加工は禁止）
        self.adapter = AmazonAdapter(user_id=user_id, region=region)

    def _fetch_raw(self, asin: str) -> dict:
        path = f"/catalog/2022-04-01/items/{asin}"
        params = {
            "marketplaceIds": [self.adapter.marketplace_id],
            "includedData": "images,summaries",
            "locale": self.adapter.locale,
        }

        raw = self.adapter.real_signed_request(
            method="GET",
            endpoint=path,
            params=params,
        )

        return raw if isinstance(raw, dict) else {}

    def _pick_first_image(self, raw: dict) -> str | None:
        if not isinstance(raw, dict):
            return None

        # ① raw["images"] → さらに1段下の ["images"][*]["link"]
        blocks = raw.get("images") or []
        for block in blocks:
            imgs = block.get("images") if isinstance(block, dict) else None
            if isinstance(imgs, list):
                for img in imgs:
                    link = img.get("link") if isinstance(img, dict) else None
                    if isinstance(link, str) and link.startswith("http"):
                        return link

        # ② 念のため summaries 側
        summaries = raw.get("summaries") or []
        for s in summaries:
            imgs = s.get("images") if isinstance(s, dict) else None
            if isinstance(imgs, list):
                for img in imgs:
                    link = img.get("link") if isinstance(img, dict) else None
                    if isinstance(link, str) and link.startswith("http"):
                        return link

        return None
    def get_image_url(self, asin: str) -> str | None:
        raw = self._fetch_raw(asin)
        image_url = self._pick_first_image(raw)

        return image_url


