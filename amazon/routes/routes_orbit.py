# ==========================================
# ファイル名: amazon/routes/routes_orbit.py
# 目的: ORBIT（注文管理）Blueprint
# ==========================================

from flask import Blueprint, request, jsonify, session, Response, redirect

from amazon.services.orbit_order_service import (
    parse_order_report,
    upsert_orders,
    list_orders_with_calc,
    update_manual_fields,
    set_agent_serial_no,
    export_notify_csv,
    sync_dispatch_sheet_status,
    MANUAL_FIELDS,
)
from amazon.services.google_sheets_service import (
    build_authorization_url,
    exchange_code_for_tokens,
    save_tokens,
    is_connected,
    get_dispatch_sheet_settings,
    save_dispatch_sheet_settings,
)

orbit_bp = Blueprint("orbit_bp", __name__, url_prefix="/orbit")


# --- ▼ SECTION 01: 注文レポートCSVインポート ▼ ---
@orbit_bp.route("/import", methods=["POST"])
def import_orders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "message": "ファイルがありません"}), 400

    text = file.read().decode("utf-8-sig", errors="replace")

    try:
        rows = parse_order_report(text)
    except Exception as e:
        return jsonify({"status": "error", "message": f"CSV解析に失敗しました: {e}"}), 400

    count = upsert_orders(user_id, rows)

    return jsonify({"status": "success", "imported": count})


# --- ▼ SECTION 02: 注文一覧取得（サイズ・重量・予測送料つき） ▼ ---
@orbit_bp.route("/orders", methods=["GET"])
def get_orders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    rows = list_orders_with_calc(user_id)
    return jsonify({"status": "success", "rows": rows})


# --- ▼ SECTION 03: 手入力項目の更新（JAN・仕入価格・依頼日・発送種別・トラッキング・備考） ▼ ---
@orbit_bp.route("/orders/update", methods=["POST"])
def update_order():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    if not order_item_id:
        return jsonify({"status": "error"}), 400

    fields = {}
    for key in MANUAL_FIELDS:
        if key not in data:
            continue
        value = data.get(key)
        if key == "purchase_price":
            value = float(value) if value not in (None, "") else None
        fields[key] = value

    update_manual_fields(user_id, order_item_id, fields)

    return jsonify({"status": "success"})


# --- ▼ SECTION 03-2: 代行会社連番の設定（先頭を入れると以降は自動連番） ▼ ---
@orbit_bp.route("/orders/set_serial", methods=["POST"])
def set_serial():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    start_value = data.get("start_value")

    if not order_item_id or start_value in (None, ""):
        return jsonify({"status": "error"}), 400

    try:
        start_value = int(start_value)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "開始番号は数値で入力してください"}), 400

    count = set_agent_serial_no(user_id, order_item_id, start_value)
    return jsonify({"status": "success", "updated": count})


# --- ▼ SECTION 04: 発送代行への通知用CSV出力 ▼ ---
@orbit_bp.route("/export", methods=["GET"])
def export_orders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    csv_text = export_notify_csv(user_id)

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orbit_export.csv"},
    )


# --- ▼ SECTION 05: Google OAuth連携（依頼書シート読み戻し用） ▼ ---
@orbit_bp.route("/google_oauth/status", methods=["GET"])
def google_oauth_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    return jsonify({"status": "success", "connected": is_connected(user_id)})


@orbit_bp.route("/google_oauth/start", methods=["GET"])
def google_oauth_start():
    if not session.get("user_id"):
        return jsonify({"status": "error"}), 401

    return redirect(build_authorization_url())


@orbit_bp.route("/google_oauth/callback", methods=["GET"])
def google_oauth_callback():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    error = request.args.get("error")
    if error:
        return f"Google連携に失敗しました: {error}", 400

    code = request.args.get("code")
    if not code:
        return "認可コードがありません", 400

    token_data = exchange_code_for_tokens(code)
    save_tokens(user_id, token_data)

    return redirect("/amazon/#orbit")




# --- ▼ SECTION 08: 依頼書スプレッドシート設定（URLが変わっても画面から変更可能に） ▼ ---
@orbit_bp.route("/dispatch_sheet_settings", methods=["GET"])
def get_dispatch_sheet_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    settings = get_dispatch_sheet_settings(user_id)
    return jsonify({"status": "success", **settings})


@orbit_bp.route("/dispatch_sheet_settings", methods=["POST"])
def save_dispatch_sheet_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    spreadsheet_url = (data.get("spreadsheet_url") or "").strip()
    sheet_name = (data.get("sheet_name") or "").strip()

    if not spreadsheet_url or not sheet_name:
        return jsonify({"status": "error", "message": "スプレッドシートURLとシート名の両方が必要です"}), 400

    save_dispatch_sheet_settings(user_id, spreadsheet_url, sheet_name)
    return jsonify({"status": "success"})


# --- ▼ SECTION 09: 代行会社シートの読み戻し（N番号で突き合わせてorbit_ordersに反映） ▼ ---
@orbit_bp.route("/dispatch_sheet_sync", methods=["POST"])
def dispatch_sheet_sync():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = sync_dispatch_sheet_status(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})
