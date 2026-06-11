# ==========================================
# ファイル名: amazon/spapi_client.py
# 目的:SP-API 署名処理・LWAトークン取得・カタログ取得用の共通ロジックを提供
# ==========================================

# ---- 標準ライブラリ ----
from typing import Dict, Any, Optional, List
import json
import os
import time
import hmac
import hashlib
import base64
import logging
import inspect
import sys
from urllib.parse import urlencode
import os, datetime, hmac, hashlib, requests
from urllib.parse import urlencode
from amazon.auth.token_manager import get_access_token
from amazon.guard.guard_429 import block, is_blocked
from datetime import datetime, timedelta


# ---- パス解決（amazonフォルダ外の utils/ へアクセスするため必須） ----
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# ---- 外部ライブラリ（SP-API SDK）----
from sp_api.base import Marketplaces, SellingApiException
from sp_api.api import CatalogItems
from sp_api.base.marketplaces import Marketplaces as SP_MARKETPLACES

# ---- HTTP通信（Amazon審査にも問題なし / SP-API公式仕様に準拠） ----
import requests

# ---- ZSSS内部モジュール ----
from amazon.auth.token_manager import get_access_token
from amazon.db import get_account_info


# --- SECTION : SP-API レスポンス処理（JSON変換 & 生データ返却） ---
def real_signed_request(method, path, params, host, json=None, cfg=None, user_id=None,
                        client_id=None, client_secret=None, refresh_token=None,
                        aws_access_key=None, aws_secret_key=None):
                        
    # --- ▼ 429ブロック判定（ユーザー単位） ▼ ---
    if user_id and is_blocked(user_id, "spapi"):
        return {"errors": [{"code": "Blocked429", "message": "Temporarily blocked"}]}
                        
    """
    本番用：必ず SP-API に投げる（LWA取得 + SigV4署名 + GET）
    - params['marketplaceId'] を前提に、対象リージョンの LWA refresh_token を選ぶ
    - AWSアクセスキーは環境変数（AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN）から取得
    - 成功時は dict(JSON) を返す（既存シグネチャ互換）
    """
    need_mp = not (path or "").startswith("/sellers/") 
    
    # --- marketplaceIds 抽出処理（list / dict どちらでも動くように修正） ---
    if isinstance(params, dict):
        # 旧形式（dict）
        mpids = params.get("marketplaceIds") or params.get("marketplaceId") or []
    elif isinstance(params, list):
        # 新形式（list of tuples）
        mpids = [v for (k, v) in params if k == "marketplaceIds"]
    else:
        mpids = []

    # 最終 marketplace_id 決定
    if isinstance(mpids, list) and mpids:
        marketplace_id = mpids[0]
    else:
        marketplace_id = mpids

    if isinstance(params, dict):
        params.pop("marketplaceId", None)

    # marketplaceId から region キーを逆引き
    def _region_key_from_mp(mp_):
        # DBモード時（cfg=None）は marketplace_id がそのまま使われる
        if cfg is None:
            return None
        for reg, mid in (cfg.get("marketplace") or {}).items():
            val = (mid.get("marketplace_id") if isinstance(mid, dict) else mid)
            if str(mp_).strip().upper() == str(val).strip().upper():
                return reg.upper()
        return None

    region_key = _region_key_from_mp(marketplace_id)

    # --- 上位関数から認証情報が渡されていない場合 ---
    if not (client_id and client_secret and refresh_token):
        # 👇ここではもう再取得しない（再呼び出しを削除）
        raise RuntimeError("LWA資格情報が不完全です（client_id / secret / refresh_token）")

    # ③ LWA アクセストークン
    access_token = get_access_token(client_id, client_secret, refresh_token)

    # URL とベースヘッダ
    query = urlencode(params or {}, doseq=True, encoding="utf-8", errors="ignore")
    url = f"{host}{path}" + (f"?{query}" if query else "")    
    headers = {
        "accept": "application/json",
        "x-amz-access-token": access_token,
    }

    # AWS 認証情報（環境変数から）
    if cfg is None:
        cfg = {}

    aws_access_key = (
        aws_access_key or os.getenv("AWS_ACCESS_KEY_ID")
        or (cfg.get("aws") or {}).get("base_access_key_id")
    )
    aws_secret_key = (
        aws_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        or (cfg.get("aws") or {}).get("base_secret_access_key")
    )
    aws_session    = os.getenv("AWS_SESSION_TOKEN")  # 任意
    
    if not aws_access_key or not aws_secret_key:
        raise RuntimeError("AWS クレデンシャル未設定（AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY）")

    # エンドポイントから署名リージョンを推定
    if "-na." in host:
        aws_region = "us-east-1"
    elif "-eu." in host:
        aws_region = "eu-west-1"
    elif "-fe." in host: 
        aws_region = "us-west-2"
    else: 
        # 念のためデフォルトで us-west-2 にしておく
        aws_region = "us-west-2" 

    # ---- SigV4 署名（GETは空ボディ） ----
    def _hmac(key, msg): return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    now = datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    service = "execute-api"

    scheme_sep = "://"
    host_and_path = url.split(scheme_sep, 1)[-1]
    host_only = host_and_path.split("/", 1)[0]
    path_and_q = host_and_path[len(host_only):] or "/"
    path_only, qs = (path_and_q.split("?", 1) + [""])[:2]

    headers["host"] = host_only
    headers["x-amz-date"] = amz_date
    if aws_session:
        headers["x-amz-security-token"] = aws_session

    signed_headers_list = ["host", "x-amz-date"] + (["x-amz-security-token"] if aws_session else [])
    signed_headers = ";".join(signed_headers_list)
    canonical_headers = "".join(f"{h}:{headers[h]}\n" for h in signed_headers_list)
    canonical_q = "&".join(sorted(qs.split("&"))) if qs else ""
    payload_hash = hashlib.sha256(b"").hexdigest()

    canonical_request = "\n".join([
        method,
        path_only if path_only.startswith("/") else "/" + path_only,
        canonical_q,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{aws_region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    kDate = _hmac(("AWS4" + aws_secret_key).encode("utf-8"), date_stamp)
    kRegion = hmac.new(kDate, aws_region.encode("utf-8"), hashlib.sha256).digest()
    kService = hmac.new(kRegion, service.encode("utf-8"), hashlib.sha256).digest()
    kSigning = hmac.new(kService, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(kSigning, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    headers["Authorization"] = (
        f"{algorithm} Credential={aws_access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    # ---- 署名ここまで ----
    try:
        # ✅ すべてのHTTPヘッダーをUTF-8で再エンコード
        headers = {
            k: (v.encode("utf-8", "ignore").decode("utf-8", "ignore") if isinstance(v, str) else v)
            for k, v in headers.items()
        }

        # ✅ URLにスキームが付いていない場合は https:// を補う
        if not url.startswith("http"):
            url = f"https://{url}"

        # === latin-1 原因特定用 ===
        import chardet
        for k, v in headers.items():
            if isinstance(v, str):
                det = chardet.detect(v.encode(errors="ignore"))

        from urllib.parse import quote

        resp = requests.request(method, url, headers=headers, params=params, json=json, timeout=15)

        print(f"<< API RESPONSE >> status:{resp.status_code}")  # コメントアウトのみ可

    except Exception as e:
        import traceback
        traceback.print_exc()        
        print(f"[DBG][ERR] request failed (after utf8 encode): {e}", flush=True)
        return {"error": str(e)}

    # === ▼ SECTION 02: APIエラーコード管理  ▼ ---
    if resp.status_code >= 400:

        msg = ""

        try:
            data = resp.json()
            code = data.get("errors", [{}])[0].get("code")
        except Exception:
            code = None

        if resp.status_code == 400:
            msg = f"400 ASIN不正 or 存在しない ({code})"
        elif resp.status_code == 404:
            msg = f"404 ASIN存在しない ({code})"
        elif resp.status_code == 429:
            msg = "429 API制限"
        elif resp.status_code >= 500:
            msg = f"{resp.status_code} Amazonサーバーエラー"
        else:
            msg = f"{resp.status_code} 不明エラー"

        print(f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [SP-API][ERR] {msg} body={resp.text[:500]}", flush=True)

        # --- ▼ ttl_stop判定 ▼ ---
        if user_id:
            try:
                if (
                    (resp.status_code == 400 and code == "InvalidInput") or
                    (resp.status_code == 404 and code == "NOT_FOUND")
                ):
                    pass
            except Exception:
                pass 
        # --- ▲ ttl_stop判定（ここまで） ▼ ---

        if resp.status_code == 429 and user_id:
            block(user_id, "spapi")

        try:
            return resp.json()
        except Exception:
            return {"raw_text": resp.text, "status_code": resp.status_code}

    data = {}
    try:
        data = resp.json()
    except Exception as e:
        # if get_debug_mode():
        #     print(f"[SP-API][WARN] JSON parse failed: {e}")
        data = {}

    return data



