# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/pricing_rules_adapter.py
# 目的: HOME Price（仕入側） / region Price（販売側）判定条件
# ======================================================
from amazon.db import get_conn
from amazon.db_migrate import DB_DIR

# --- Amazon公式IDリスト ---
AMAZON_OFFICIAL_IDS = {
    "AN1VRQENFRJN5",   # JP JP
    "A2K69GP4EI3XWZ",  # AU AU
}


class PricingRulesAdapter:

    # --- ▼ SECTION 01: 初期化（将来の拡張用） ▼ ---
    def __init__(self, rules: dict | None = None):
        """
        rules: pricing_rules（DB）から取得した条件。
        ※ 現時点では未使用（暫定：最安値のみ）
        """
        self.rules = rules or {}  

    # --- ▼ SECTION 02: HOME 原価確定（フィルタ＋最安決定） ▼ ---
    def select_home_cost_offer(self, normalized_offers: list[dict]):

        if not normalized_offers:
            return None

        # --- 最低在庫数（新品offer数） ---if not filtered:
        min_stock_qty = self.rules.get("min_stock_qty")
        if min_stock_qty:
            total_offers = len(normalized_offers)
            if total_offers < int(min_stock_qty):
                return None

        filtered = []                

        # --- HOME国取得（a_marketplaces.db） ---
        conn = get_conn("a_marketplaces.db")

        cur = conn.cursor()
        cur.execute("""
            SELECT country_code
            FROM marketplaces
            WHERE user_id = %s
            AND home_flag = 1
            LIMIT 1
        """, (self.rules.get("user_id"),))
        row = cur.fetchone()
        conn.close()

        home_country = row[0] if row else None

        for offer in normalized_offers:
            # ここに条件判定を順番に追加していく    

            seller_id = offer.get("seller_id")

            # --- Amazon直売は評価率・数は無条件通過 ---
            seller_id = offer.get("seller_id")
            is_amazon = seller_id in AMAZON_OFFICIAL_IDS 

            # --- 予約商品除外 ---
            if self.rules.get("exclude_future_offer") == 1:
                if offer.get("is_future_offer"):
                    continue

            # --- 海外出荷除外 ---
            if self.rules.get("exclude_non_home_ship") == 1:
                ships_from_country = offer.get("ships_from_country")
                # HOMEのcountryは rules から渡されていないので
                # parent_adapter.country_code を使う前提
                # home_country = self.rules.get("country_code")

                if ships_from_country and home_country:
                    if ships_from_country != home_country:
                        continue

            # --- 最低評価率 ---
            min_rating_percent = self.rules.get("min_rating_percent")
            if min_rating_percent and not is_amazon:
                rating = offer.get("rating_percent")
                if rating is None or float(rating) < float(min_rating_percent):
                    continue

            # --- 最低評価数 ---
            min_rating_count = self.rules.get("min_rating_count")
            if min_rating_count and not is_amazon:
                rating_count = offer.get("rating_count")
                if rating_count is None or int(rating_count) < int(min_rating_count):
                    continue                    

            # --- 最大出荷日数 ---
            max_handling_days = self.rules.get("max_handling_days")
            handling_days = offer.get("handling_time_days")

            seller_id = offer.get("seller_id")
            is_amazon = seller_id in AMAZON_OFFICIAL_IDS 

            if handling_days is not None:

                # Amazonは48時間以内（2日）
                if is_amazon:
                    if float(handling_days) > 2:
                        continue

                # 通常セラー
                elif max_handling_days:
                    if float(handling_days) > float(max_handling_days):
                        continue

            # --- BuyBox限定 ---
            if self.rules.get("exclude_non_buybox") == 1:
                if not offer.get("is_buybox_winner"):
                    continue                    
            filtered.append(offer)


        if not filtered:      
            return None

        # 最安選定（暫定：price_amountのみ）
        min_offer = None
        min_total = None

        for offer in filtered:
            price = offer.get("price_amount")
            shipping = offer.get("shipping_amount") or 0
            points = offer.get("points_amount") or 0

            if price is None:
                continue

            total = float(price) + float(shipping)

            # --- ポイント加味 ---
            if self.rules.get("consider_points") == 1:
                total = total - float(points)

            if min_total is None or total < min_total:
                min_total = total
                min_offer = offer
       
        return {
            "selected": min_offer,
            "filtered": filtered,
            "filtered_count": len(filtered),
            "total_count": len(normalized_offers),
        }        

    # --- ▼ SECTION 03: REGION 価格基準決定（暫定＋最低評価率） ▼ ---
    def select_region_price_offer(self, normalized_offers: list[dict]):
        if not normalized_offers:
            return None

        filtered = []

        for offer in normalized_offers:
            # --- 自分除外（ここ追加） ---
            if offer.get("seller_id") == self.rules.get("my_seller_id"):
                continue

            # --- 最低評価率 ---
            min_rating_percent = self.rules.get("pricing_competitor_min_rating_percent")
            if min_rating_percent:
                rating = offer.get("rating_percent")
                if rating is None or float(rating) < float(min_rating_percent):
                    continue

            # --- 最低評価数 ---
            min_rating_count = self.rules.get("pricing_competitor_min_rating_count") 
            if min_rating_count:
                rating_count = offer.get("rating_count")
                if rating_count is None or int(rating_count) < int(min_rating_count):
                    continue

            filtered.append(offer)

        if not filtered:
            return None

        # --- 最安値選定 ---
        min_offer = None
        min_total = None

        for offer in filtered:
            price = offer.get("price_amount")
            shipping = offer.get("shipping_amount") or 0

            if price is None:
                continue

            total = float(price) + float(shipping)

            if min_total is None or total < min_total:
                min_total = total
                min_offer = offer

        return {
            "selected": min_offer,
            "filtered": filtered,
            "filtered_count": len(filtered),
            "total_count": len(normalized_offers),
        }


