# =====================================================
# ファイル名: zsss_web/api_check/a_api_scan_allcheck.py
# 目的:実運用ファイルではない　raw情報取得チェック用PY
#   Catalog Items API を1回だけ直叩きして
#   SP-APIのRAW(JSON)をそのままUIに返す（画像含む）
#   既存ZSSSロジックに一切影響させない
# =====================================================

import json
from flask import Blueprint, request, Response, session, jsonify
from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.db import get_conn

api_raw_check_bp = Blueprint(
    "api_raw_check_bp",
    __name__,
    url_prefix="/admin/api_raw_check"
)

@api_raw_check_bp.route("/catalog", methods=["GET"])
def api_raw_catalog_check():
    # 管理者チェック
    if not session.get("is_admin"):
        return jsonify({"status": "error", "message": "権限なし"}), 403

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "login required"}), 401

    asin = (request.args.get("asin") or "").strip().upper()
    ui_country_code = (request.args.get("country_code") or request.args.get("region") or "").strip().upper()

    if not asin or not ui_country_code:
        return {"status": "error", "message": "asin / region required"}, 400

    # ★ UIで選んだregionから marketplace_id を取得
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id = %s
          AND UPPER(country_code) = UPPER(%s)
        LIMIT 1
    """, (user_id, ui_country_code))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"marketplace not found: {ui_country_code}"}, 400

    marketplace_id = row["marketplace_id"]

    # ★ 現在ログイン中の管理者のuser_id + marketplace_idでAdapter生成
    #    （marketplace_idはAmazonAdapterのコンストラクタで必須のため、先に解決してから渡す）
    adapter = AmazonAdapter(user_id=user_id, marketplace_id=marketplace_id)

    # ★ Catalog Items API を1回だけ叩く（画像含む）
    endpoint = f"/catalog/2022-04-01/items/{asin}"
    params = {
        "marketplaceIds": [marketplace_id],
        "includedData": "attributes,images,summaries"
    }

    raw = adapter.real_signed_request(
        method="GET",
        endpoint=endpoint,
        params=params,
    )

    return Response(
        json.dumps(raw, ensure_ascii=False, indent=2),
        mimetype="application/json"
    )
