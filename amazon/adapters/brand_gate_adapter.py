# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/adapters/brand_gate_adapter.py
# 目的： ブランドゲートチェック
# ==========================================================

from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.db import get_conn
from flask import request, jsonify, session

# --- ▼ SECTION 01: Brand Gate（ブランドゲートチェック） ▼ ---
class BrandGateAdapter:

    def __init__(self, user_id, country_code, marketplace_id):
        self.user_id = user_id
        self.country_code = country_code
        self.marketplace_id = marketplace_id

    def check(self, asin):
        asin = (asin or "").strip().upper()
        if not asin:
            return {
                "asin": "",
                "status": "NG",
                "note": "ASIN empty"
            }

        path = "/listings/2021-08-01/restrictions"

        adapter = AmazonAdapter(
            user_id=self.user_id,
            country_code=self.country_code,
            marketplace_id=self.marketplace_id
        )

        params = {
            "asin": asin,
            "marketplaceIds": self.marketplace_id,
            "conditionType": "new_new",
            "sellerId": adapter.seller_id
        }

        res = adapter.real_signed_request(
            method="GET",
            endpoint=path,
            params=params
        )

        result = {
            "asin": asin,
            "status": None,
            "note": ""
        }

        restrictions = (res or {}).get("restrictions") or []

        if not restrictions:
            result["status"] = "OK"
        else:
            needs_approval = False
            hard_block = False

            for r in restrictions:
                reasons = r.get("reasons") or []
                for x in reasons:
                    blob = f"{x.get('reasonCode','')} {x.get('message','')}".upper()

                    if "APPROVAL" in blob:
                        needs_approval = True

                    if any(k in blob for k in ["NOT", "RESTRICTED", "BLOCK"]):
                        hard_block = True

            if hard_block:
                result["status"] = "NG"
            elif needs_approval:
                result["status"] = "APPROVAL"

        return result

# --- ▼ SECTION 02: extract_brand （ブランド抽出） ▼ ---
def extract_brand_logic():

    data = request.get_json() or {}
    asins = data.get("asins") or []
    country_code = (data.get("country_code") or "").upper()
    user_id = session.get("user_id")

    conn = get_conn("a_marketplaces.db")

    cur = conn.cursor()
    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id=%s AND UPPER(country_code)=UPPER(%s)
        LIMIT 1
    """, (user_id, country_code))
    r = cur.fetchone()
    conn.close()

    marketplace_id = r[0] if r else None

    adapter = AmazonAdapter(user_id, country_code, marketplace_id)

    result = []

    for asin in asins:
        try:
            path = f"/catalog/2022-04-01/items/{asin}"

            params = {
                "marketplaceIds": marketplace_id,
                "includedData": "summaries,attributes"
            }

            catalog = adapter.real_signed_request(
                method="GET",
                endpoint=path,
                params=params
            ) or {}

            brand = ""

            summaries = catalog.get("summaries") or []
            if summaries and summaries[0].get("brand"):
                brand = summaries[0]["brand"]

            result.append({"asin": asin, "brand": brand})

        except Exception:
            result.append({"asin": asin, "brand": ""})

    return jsonify(result)



        
          