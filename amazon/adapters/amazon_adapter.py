# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon\adapter\amazon_adapter.py
# Amazon SP-API 共通通信アダプター
#   - DBからリージョン別アカウント情報を取得
#   - 共通認証（LWA / AWS署名）を生成
#   - 各専用アダプター（Catalog, Pricingなど）を統括
# ==========================================================

import requests
import os
import json
from amazon.auth.token_manager import get_access_token
from amazon.db import get_account_info, get_conn
from amazon.adapters.base_adapter import BaseMarketplaceAdapter as BaseAdapter
from amazon.spapi_client import real_signed_request 
from flask import session
from amazon.db import get_account_info_by_marketplace_id
from datetime import datetime



class AmazonAdapter:
    # --- ▼ SECTION 01: ▼ ---
    def __init__(self, user_id: int, country_code: str | None = None, marketplace_id: str | None = None,):
        self.user_id = user_id
        self.country_code = country_code     
        self.marketplace_id = marketplace_id 

        if marketplace_id is None:
            raise ValueError("marketplace_id required")

        self.account = get_account_info_by_marketplace_id(self.marketplace_id, self.user_id)
        self.host = self.account.get("host")
        self.refresh_token = self.account.get("refresh_token")
        self.locale = self.account.get("locale", "en_US")
        self.credentials = {
            "refresh_token": self.account.get("refresh_token"),
            "lwa_app_id": self.account.get("lwa_app_id"),
            "lwa_client_secret": self.account.get("lwa_client_secret")
        }
        self.seller_id = self.account.get("account_seller_id") 

    # --- ▼ SECTION 02: 抽象クラス要件：ダミー実装 ▼ ---
    def update_price(self, product_id: str, price: float, currency: str, country_code: str, **kwargs):
        """BaseMarketplaceAdapterの抽象メソッド実装（未使用）"""
        raise NotImplementedError("update_price() is not implemented in AmazonAdapter")

    # --- ▼ SECTION 03: 共通リクエスト送信処理（DB内のAWS/LWA情報を利用） ▼ ---
    def real_signed_request(self, method: str, endpoint: str, host: str = None, params: dict = None, json: dict = None):
        """SP-API共通通信"""

        # --- ▼ APIカウンター（SP-API実行直前）▼ ---
        record_api_usage(              
            self.user_id,
            self.marketplace_id,
            endpoint
        )

        if not hasattr(self, "account") or self.account is None:
            from amazon.db import get_account_info
            self.account = get_account_info(self.country_code, self.user_id)

        acct = self.account or {}

        from amazon.db import get_lwa_credentials
        lwa = get_lwa_credentials((acct.get("country_code") or self.country_code).upper())        

        client_id = lwa.get("client_id") or "" 
        client_secret = lwa.get("client_secret") or ""

        refresh_token = acct.get("refresh_token") or ""
        host_to_use = acct.get("spapi_host") or acct.get("host") or self.host

        return real_signed_request(
            method=method,
            path=endpoint,
            json=json,           
            params=params or {},
            user_id=self.user_id,
            host=host_to_use,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )

    # --- ▼ SECTION 04: Catalog API 統合呼び出し ▼ ---
    def get_item_info(self, asin: str):
        """CatalogAdapterを通じて商品情報を取得"""
        return self.catalog.get_item_info(asin)

    # --- ▼ SECTION 05:  共通ユーティリティ ▼ ---
    def to_dict(self):
        """デバッグ用：現在の接続情報を辞書で返す"""
        return {
            "region": self.region,
            "host": self.host,
            "marketplace_id": self.marketplace_id,
            "locale": self.locale,
            "has_credentials": all(bool(v) for v in self.credentials.values()),
        }


# --- ▼ SECTION 06: API使用ログ記録（SP-APIカウンター）ファイル分離時にはこのセクションを移動 ▼ ---
def record_api_usage(user_id, marketplace_id, endpoint):
    """
    SP-API使用ログを1件記録する
    ※ 失敗してもAPI本体は止めない
    """
    conn = None

    now_utc = datetime.utcnow().isoformat()

    try:
        conn = get_conn("a_api_usage.db")
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO api_usage_logs (user_id, marketplace_id, endpoint, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, marketplace_id, endpoint, now_utc)
        )
        conn.commit()
    except Exception:
        # カウンター失敗でもAPI本体は止めない（事故防止）
        pass
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    from amazon.adapters.amazon_adapter import AmazonAdapter
    adapter = AmazonAdapter(country_code="JP")
    print(">>> JP marketplace_id =", adapter.marketplace_id)

# --- ▼ SECTION 07: Amazon OAuth 認可URL生成（HouseTool / Public 共通） ▼ ---
def build_oauth_authorize_url(
    marketplace: str,
    app_type: str = "house_tool"
) -> str:

    marketplace = marketplace.upper()

    # --- ▼ master DB から取得 ▼ ---
    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT application_id, host FROM marketplaces_master WHERE UPPER(country_code)=UPPER(%s)",
        (marketplace,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Master config not found for {marketplace}")

    application_id = row["application_id"] 
    host = row["host"] 

    # --- ▼ /ap/oa 使用 ▼ ---
    host_without_scheme = host.replace("https://", "").replace("http://", "")
    seller_host = host_without_scheme.replace("www.", "sellercentral.")
    base_url = f"https://{seller_host}/apps/authorize/consent"

    # --- ▼ redirect_uri を現在の環境から動的生成 ▼ ---
    from flask import request
    redirect_uri = request.url_root.rstrip("/") + "/amazon/oauth/callback"

    from urllib.parse import urlencode

    params = {
        "application_id": application_id,
        "redirect_uri": redirect_uri,
        "state": f"{app_type}:{marketplace}",
    }

    final_url = base_url + "?" + urlencode(params)

    return final_url



