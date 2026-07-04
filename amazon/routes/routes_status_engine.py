# ===========================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# -------------------------------------------
# ファイル名: amazon\routes\routes_status_engine.py
# 目的: infomation_status判定のみを処理
# ===========================================


def evaluate_status(brand_ng_flag, final_price, max_price, raw_min_price, rules):
    inactive_reason = None

    if brand_ng_flag:
        return "INACTIVE", "BLACKLIST"

    if final_price is None or final_price == 0:
        return "INACTIVE", "NO_PRICE"

    if max_price and final_price and float(final_price) > float(max_price):
        return "INACTIVE", "SETTING_MAX_PRICE"

    if rules.get("max_competitor_price_ratio") and raw_min_price:
        if float(final_price) > float(raw_min_price) * (1 + float(rules["max_competitor_price_ratio"]) / 100):
            return "INACTIVE", "COMPETITOR_RATIO"

    return "ACTIVE", None