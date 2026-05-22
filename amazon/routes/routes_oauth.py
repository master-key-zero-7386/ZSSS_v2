# ==========================================
# ファイル名: amazon/routes_oauth.py
# 目的: マーケとプレイスごとのリフレッシュトーク受信
# ==========================================

import requests 
from amazon.db import get_lwa_credentials
from flask import Blueprint, request, redirect, session, url_for, jsonify
from flask_login import login_required

from amazon.adapters.amazon_adapter import build_oauth_authorize_url

amazon_oauth_bp = Blueprint("amazon_oauth", __name__)

# --- ▼ SECTION 01:  ▼ ---
@amazon_oauth_bp.route("/oauth/start")
def amazon_oauth_start():
    marketplace = request.args.get("marketplace", "SG")
    app_type = request.args.get("app_type", "house_tool")

    auth_url = build_oauth_authorize_url(marketplace, app_type)
    return redirect(auth_url)



# --- ▼ SECTION 02: OAuth callback（REGION 確認用） ▼ ---
@amazon_oauth_bp.route("/oauth/callback")
def amazon_oauth_callback():

    code  = request.args.get("code")
    state = request.args.get("state")  

    if not code or not state:
        return "missing code or state", 400

    try:
        app_type, marketplace = state.split(":")
    except ValueError:
        return "invalid state", 400

    marketplace = marketplace.upper()


    # --- ▼ REGION 用：本番 Amazon token 取得 ▼ ---
    if code.startswith("DUMMY"):
        refresh_token = "DUMMY_REGION_REFRESH_TOKEN"
    else:
        TOKEN_URL = "https://api.amazon.com/auth/o2/token"

        lwa = get_lwa_credentials(marketplace) 
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": lwa["client_id"],  
            "client_secret": lwa["client_secret"],# OAuth LWA べた書きなので後々変更修正
            "redirect_uri": "https://bluntly-umbilicate-quentin.ngrok-free.dev/amazon/oauth/callback",
        }

        res = requests.post(
            TOKEN_URL, 
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        token_data = res.json()

        refresh_token = token_data.get("refresh_token")


    # --- ▼ callback では保存しない：session に積むだけ ▼ ---
    session["oauth_result"] = {
        "app_type": app_type,        # region
        "marketplace": marketplace,  # US
        "refresh_token": refresh_token
    }

    print("DEBUG OAUTH SESSION:", session.get("oauth_result")) 

    # --- ▼ 直接 /account に戻さない ▼ ---
    return redirect(url_for("amazon_oauth.oauth_complete"))

@amazon_oauth_bp.route("/oauth/complete")
def oauth_complete():
    session["force_tab"] = "account" 
    return redirect("/amazon/#account")

@amazon_oauth_bp.route("/oauth/result")
def oauth_result():
    data = session.pop("oauth_result", None)
    if not data:
        return jsonify({"status": "ng"})

    return jsonify({
        "status": "ok",
        "app_type": data["app_type"],
        "marketplace": data["marketplace"],
        "refresh_token": data["refresh_token"]
    })


