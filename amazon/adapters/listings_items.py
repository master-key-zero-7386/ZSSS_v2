# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/listings_items.py
# 目的: Amazon 正式listing用
# ======================================================

from amazon.adapters.amazon_adapter import AmazonAdapter
import json
from datetime import datetime, timezone, timedelta
from amazon.utils.brand_gate_store import save_brand_gate_result
import sqlite3, os
from amazon.db import get_conn

JST = timezone(timedelta(hours=9))

# --- SECTION 00: logテキスト出力 ---
LOG_DIR = "logs"  # 保存先フォルダ名(必要に応じて変更してな)

def write_log(message: str):
    """ログをコンソールに表示しつつ、日付ごとのtxtファイルにも追記する"""
    print(message, flush=True)

    os.makedirs(LOG_DIR, exist_ok=True)
    today_str = (datetime.utcnow() + timedelta(hours=9)).strftime('%Y%m%d')
    log_path = os.path.join(LOG_DIR, f"listing_log_{today_str}.txt")

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message + "\n")

# --- SECTION 01: Listings Items API（From：FIRST / ALL listing） ---
def put_listings_item(user_id, country_code, marketplace_id, seller_sku, asin, price, quantity, handling_time):
    adapter = AmazonAdapter(user_id, country_code=None, marketplace_id=marketplace_id)

    body = {
        "productType": "PRODUCT",
        "requirements": "LISTING_OFFER_ONLY",

        "attributes": {

            "merchant_suggested_asin": [
                {
                    "value": asin,
                    "marketplace_id": marketplace_id  
                }
            ],

            "condition_type": [
                {
                    "value": "new_new",
                    "marketplace_id": marketplace_id 
                }
            ],

            "purchasable_offer": [
                {
                    "marketplace_id": marketplace_id,   
                    "currency": adapter.account["currency"],  
                    # "audience": "ALL",  

                    "our_price": [
                        {
                            "schedule": [
                                {
                                    "value_with_tax": float(price) 
                                }
                            ]
                        }
                    ]
                }
            ],


            "fulfillment_availability": [
                {
                    "fulfillment_channel_code": "DEFAULT",
                    "quantity": int(quantity),
                    "lead_time_to_ship_max_days": int(handling_time)
                }
            ]
        }
    }
    
    # --- 出品APIチェック用 ---
    print(
    f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [[LIST {country_code}]] UserID:{user_id} ASIN:{asin} PRICE:{price} QTY:{quantity} HT:{handling_time} SKU:{seller_sku} ",
    flush=True)  
    write_log(
        f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [[LIST {country_code}]] UserID:{user_id} ASIN:{asin} PRICE:{price} QTY:{quantity} HT:{handling_time} SKU:{seller_sku} "
    )      
    # --- 出品APIチェック用 ---ここまで 削除しない

    response = adapter.real_signed_request(
        "PUT",
        f"/listings/2021-08-01/items/{adapter.account['account_seller_id']}/{seller_sku}",

        params={
            "marketplaceIds": [marketplace_id],
        },
        json=body
    )

    # --- ▼ BrandGate保存（出品API直後） ▼ ---
    try:
        errors = response.get("errors") if isinstance(response, dict) else None
        status = "NG" if errors else "OK"

        # --- brand取得（listed_itemsから） ---
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_file = os.path.join(base_dir, "db", f"a_{country_code.lower()}_listed_items.db")

        conn_li = get_conn(f"a_{country_code.lower()}_listed_items.db")

        cur_li = conn_li.cursor()

        cur_li.execute("""
            SELECT region_brand
            FROM listed_items
            WHERE asin = %s
            AND user_id = %s
            LIMIT 1
        """, (asin, user_id))

        row_li = cur_li.fetchone()
        conn_li.close()

        brand = row_li["region_brand"] if row_li and row_li["region_brand"] else "UNKNOWN"

        # save_brand_gate_result(
        #     user_id=user_id,
        #     marketplace_id=marketplace_id,
        #     brand=brand,
        #     status=status,
        #     reason=str(errors) if errors else None
        # )

    except Exception as e:
        print("BrandGate save error:", e)

    return response 

# --- SECTION 02: Delete Items API（From：ALL listing専用）SKU個別Delete ---
def delete_listings_item(user_id, country_code, marketplace_id, seller_sku):

    adapter = AmazonAdapter(user_id, country_code=country_code, marketplace_id=marketplace_id)

    # --- 削除APIチェック用 ---
    print(
    f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [[DELETE {country_code}]] ID:{user_id} MP:{marketplace_id} SKU:{seller_sku}", flush=True)
    # --- 削除APIチェック用 ---ここまで 削除しない

    response = adapter.real_signed_request(
        "DELETE",
        f"/listings/2021-08-01/items/{adapter.account['account_seller_id']}/{seller_sku}?marketplaceIds={marketplace_id}"
    )

    return response

# --- SECTION 03: Delete Items API（From：Bulk Delete）：Inventory Feed ---
def delete_listings_feed(user_id, country_code, marketplace_id, sku_list):

    adapter = AmazonAdapter(user_id, country_code=country_code, marketplace_id=marketplace_id)

    # --- 削除Feedチェック用 ---
    print(
        f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [[DELETE FEED {country_code}]] ID:{user_id} MP:{marketplace_id} SELLER:{adapter.account['account_seller_id']} COUNT:{len(sku_list)} SKU:{sku_list}", flush=True)
    # --- 削除Feedチェック用 ---ここまで 削除しない

    # --- ▼ Feed Document 作成 ▼ ---
    doc = adapter.real_signed_request(
        "POST",
        "/feeds/2021-06-30/documents",
        json={
            "contentType": "application/json"
        }
    )
    print("FEED_DOC_RESPONSE:", doc, flush=True)   # 一括処理確認ログ削除NG

    doc_data = doc
    feed_document_id = doc_data.get("feedDocumentId")
    upload_url = doc_data.get("url")


    # --- ▼ Feed Body 作成 ▼ ---
    messages = []
    msg_id = 1

    for sku in sku_list:

        # --- ▼ SKU正規化 ▼ ---
        if isinstance(sku, list):
            sku = sku[0]
        if isinstance(sku, str) and sku.startswith("["):
            sku = sku.strip("[]'\"")        

        messages.append({
            "messageId": msg_id,
            "operationType": "DELETE",
            "sku": sku
        })

        msg_id += 1


    feed_body = {
        "header": {
            "sellerId": adapter.account["account_seller_id"],
            "version": "2.0",
            "issueLocale": "en_US"
        },
        "messages": messages
    }

    # --- ▼ Feed Upload ▼ ---
    import requests

    requests.put(
        upload_url,
        data=json.dumps(feed_body),
        headers={
            "Content-Type": "application/json"
        }
    )


    # --- ▼ Feed Submit ▼ ---
    feed_submit = adapter.real_signed_request(
        "POST",
        "/feeds/2021-06-30/feeds",
        json={
            "feedType": "JSON_LISTINGS_FEED",
            "marketplaceIds": [marketplace_id],
            "inputFeedDocumentId": feed_document_id
        }
    )

    feed_id = feed_submit.get("feedId")

    print("FEED ID:", feed_id, flush=True)  # 一括処理確認ログ削除NG

    import time
    time.sleep(5)

    feed_status = adapter.real_signed_request(
        "GET",
        f"/feeds/2021-06-30/feeds/{feed_id}"
    )

    return feed_submit

