# =====================================================
# ファイル名: zsss_web/api_check/a_api_scan_allcheck.py
# 目的:実運用ファイルではない　raw情報取得チェック用PY
#   Catalog Items API を1回だけ直叩きして
#   SP-APIのRAW(JSON)をそのままUIに返す（画像含む）
#   既存ZSSSロジックに一切影響させない
# =====================================================

import json
from flask import Blueprint, request, Response
from amazon.adapters.amazon_adapter import AmazonAdapter
from amazon.db import get_conn

api_raw_check_bp = Blueprint(
    "api_raw_check_bp",
    __name__,
    url_prefix="/admin/api_raw_check"
)

@api_raw_check_bp.route("/catalog", methods=["GET"])
def api_raw_catalog_check():
    asin = (request.args.get("asin") or "").strip().upper()
    ui_country_code = (request.args.get("region") or "").strip().upper()

    if not asin or not ui_country_code:
        return {"status": "error", "message": "asin / region required"}, 400

    # ★ HOME固定でAdapter生成（既存ZSSS無影響）
    adapter = AmazonAdapter(user_id=1)

    # ★ UIで選んだregionから marketplace_id だけ取得
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT marketplace_id
        FROM marketplaces
        WHERE user_id = %s
          AND UPPER(country_code) = UPPER(%s)
        LIMIT 1
    """, (1, ui_country_code))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"marketplace not found: {ui_country_code}"}, 400

    marketplace_id = row["marketplace_id"]

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
