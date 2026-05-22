# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/catalog_rules_adapter.py
# 目的: HOME 寸法。重量情報の補正　送料算定に必要
# ======================================================
import math

class CatalogRulesAdapter:

    # --- ▼ SECTION 01: 初期化（rules受け取り専用） ▼ ---
    def __init__(self, rules: dict | None = None):
        """
        rules:
            pricing_rules テーブル等から取得した
            寸法・重量補正ルール（そのまま受け取る）
        """
        self.rules = rules or {}

    # --- ▼ SECTION 02: HOME 寸法・重量 補正処理 ▼ ---
    def apply_home_dimension_weight_rules(self, normalized_catalog: dict):
        """
        Catalog フェーズでは補正・算定は一切行わない。
        normalized_catalog をそのまま返す。
        """

        return normalized_catalog



