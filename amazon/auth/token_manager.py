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

def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:

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
        return data["access_token"]
    else:
        raise Exception(f"Access token request failed: {response.text}")
