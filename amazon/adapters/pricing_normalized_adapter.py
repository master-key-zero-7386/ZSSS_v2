# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/pricing_normalized_adapter.py
# 目的: offers_json ⇒ normalized
# ==========================================================

class NormalizedPricingAdapter:

    # --- ▼ SECTION 01:  ▼ ---
    def _get_ci(self, d: dict, key: str):
        if not isinstance(d, dict):
            return None
        for k, v in d.items():
            if k.lower() == key.lower():
                return v
        return None

    # --- ▼ SECTION 02: AmazonAdapter を保持（HOME/REGION共通） ▼ ---
    def __init__(self, parent_adapter):
        """
        HOME / REGION 共通で使用する normalized adapter の基盤。
        """
        self.parent = parent_adapter

    # --- ▼ SECTION 03: HOME offers 正規化（条件判定用素材化） ▼ ---
    def normalize_home_offers(self, home_offers_json: dict):
        """
        HOME側 offers_json を
        条件判定に使える最小単位へ正規化する。
        ※ 条件ロジック・価格決定は一切行わない
        """
        if not home_offers_json:                         
            return []                                    

        payload = home_offers_json.get("payload") or {} 
        offers = payload.get("Offers") or []           

        if not isinstance(offers, list):                 
            return []                                    

        normalized = []                                  

        for offer in offers:                             
            if not isinstance(offer, dict):       
                continue                                 

            # --- price ---
            price_info = offer.get("ListingPrice") or {}     
            price_amount = price_info.get("Amount")          
            price_currency = price_info.get("CurrencyCode")  

            # --- seller ---
            seller_id = offer.get("SellerId")                
            is_amazon_seller = bool(seller_id == "Amazon")  

            # --- shipping / handling ---
            shipping_info = self._get_ci(offer, "ShippingTime") or {}
            maximum_hours = self._get_ci(shipping_info, "maximumHours")
            handling_time_days = float(maximum_hours) / 24 if maximum_hours else 0 
            availability_type = self._get_ci(shipping_info, "availabilityType")
            is_future_offer = bool(availability_type and availability_type != "NOW")

            shipping_price_info = offer.get("Shipping") or {} 
            shipping_amount = shipping_price_info.get("Amount") or 0   

            # --- points ---
            points_info = offer.get("Points") or {}
            points_amount = points_info.get("PointsNumber") or 0

            ships_from = self._get_ci(offer, "ShipsFrom") or {}
            ships_from_country = self._get_ci(ships_from, "Country")

            # --- buybox ---
            is_buybox_winner = bool(offer.get("IsBuyBoxWinner"))    

            # --- rating ---
            seller_feedback = offer.get("SellerFeedbackRating") or {}  
            rating_percent = seller_feedback.get("SellerPositiveFeedbackRating")  
            rating_count = seller_feedback.get("FeedbackCount")        

            normalized.append({                         
                "price_amount": price_amount, 
                "shipping_amount": shipping_amount,                           
                "price_currency": price_currency,       
                "seller_id": seller_id,                 
                "is_amazon_seller": is_amazon_seller,   
                "handling_time_days": handling_time_days,  
                "points_amount": points_amount,
                "ships_from_country": ships_from_country,
                "is_future_offer": is_future_offer,     
                "is_buybox_winner": is_buybox_winner,   
                "rating_percent": rating_percent,       
                "rating_count": rating_count,           
            })

        return normalized                                 

    # --- ▼ SECTION 04: REGION offers 正規化（条件判定用素材化） ▼ ---  
    def normalize_region_offers(self, region_offers_json: dict):  

        if not region_offers_json:  
            return []  

        payload = region_offers_json.get("payload") or {}
        offers = payload.get("Offers") or []

        if not isinstance(offers, list):  
            return []  

        normalized = []  

        for offer in offers:  
            if not isinstance(offer, dict):  
                continue

            # --- price ---
            price_info = offer.get("ListingPrice") or {}
            price_amount = price_info.get("Amount")
            price_currency = price_info.get("CurrencyCode")

            # --- shipping ---
            shipping_price_info = offer.get("Shipping") or {}
            shipping_amount = shipping_price_info.get("Amount") or 0

            # --- seller ---
            seller_id = offer.get("SellerId")

            # --- rating ---
            seller_feedback = offer.get("SellerFeedbackRating") or {}
            rating_percent = seller_feedback.get("SellerPositiveFeedbackRating")
            rating_count = seller_feedback.get("FeedbackCount")

            normalized.append({
                "price_amount": price_amount,
                "shipping_amount": shipping_amount,
                "price_currency": price_currency,
                "seller_id": seller_id,
                "rating_percent": rating_percent,
                "rating_count": rating_count,
            })

        return normalized



