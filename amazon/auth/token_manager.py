# =====================================================
# ファイル名: amazon/auth/token_manager.py
# 目的：Amazon LWA（Login With Amazon）認証専用のトークン管理モジュール。
#      Refresh Token から Access Token を発行する処理のみを担当し、
#      SP-API 呼び出し時に他のアダプターから共通利用される。
# =====================================================

import requests
import time
from amazon.background.common.background_common import get_ttl_sleep_sec

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

_TOKEN_CACHE = {}

def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:

    cache = _TOKEN_CACHE.get(refresh_token) 

    if cache and cache["expires_at"] > time.time():
        return cache["access_token"]

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    time.sleep(get_ttl_sleep_sec())  

    response = requests.post(LWA_TOKEN_URL, data=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()

        _TOKEN_CACHE[refresh_token] = {  
            "access_token": data["access_token"],  
            "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60  
        } 

        return data["access_token"]
    else:
        raise Exception(f"Access token request failed: {response.text}")
