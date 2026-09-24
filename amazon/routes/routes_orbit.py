# ==========================================
# ファイル名: amazon/routes/routes_orbit.py
# 目的: ORBIT（注文管理）Blueprint
# ==========================================

from datetime import datetime

from flask import Blueprint, request, jsonify, session, Response, redirect

from amazon.services.orbit_order_service import (
    parse_order_report,
    upsert_orders,
    list_orders_with_calc,
    recompute_order_group,
    update_manual_fields,
    delete_order,
    delete_all_orders,
    relist_after_purchase,
    order_flag_is_set,
    fetch_and_cache_catalog_for_asin,
    fetch_and_cache_fee_estimate,
    export_fee_data_csv,
    parse_fee_data_csv,
    import_fee_data,
    set_agent_serial_no,
    assign_missing_agent_serial_no,
    has_duplicate_agent_serial_no,
    export_notify_csv,
    push_orders_to_raw_sheet,
    sync_dispatch_sheet_status,
    import_buyer_history_csv,
    export_buyer_history_csv,
    list_archive_candidates,
    archive_orders,
    add_security_note,
    update_security_note,
    list_buyer_history,
    get_asin_shipping_history,
    list_security_notes,
    list_credit_cards,
    add_credit_card,
    update_credit_card,
    delete_credit_card,
    list_jp_holidays,
    list_agent_closures,
    add_agent_closure,
    delete_agent_closure,
    MANUAL_FIELDS,
    NUMERIC_MANUAL_FIELDS,
)
from amazon.services.orbit_settlement_service import (
    parse_settlement_report,
    import_settlement_lines,
)
from amazon.adapters.orbit_sales_trend import get_sales_trend
from amazon.core.fx_rate import get_exchange_rate
from amazon.services.google_sheets_service import (
    build_authorization_url,
    exchange_code_for_tokens,
    save_tokens,
    has_working_connection,
    get_dispatch_sheet_settings,
    save_dispatch_sheet_settings,
    get_raw_sheet_settings,
    save_raw_sheet_settings,
    get_receipt_settings,
    save_receipt_settings,
    get_request_form_url,
    save_request_form_url,
    fetch_deposit_balance,
    get_kanrihin_sheet_name,
    save_kanrihin_sheet_name,
)
from amazon.services.orbit_receipt_import_service import run_receipt_import, inbox_status
from amazon.services.orbit_kanrihin_service import (
    list_kanrihin_items,
    confirm_kanrihin_items,
    release_kanrihin_item,
    save_kanrihin_link,
    set_kanrihin_processed,
    ship_from_kanrihin,
)

orbit_bp = Blueprint("orbit_bp", __name__, url_prefix="/orbit")


# --- ▼ N番重複ガード ▼ ---
# N番(agent_serial_no)に重複がある間は、N番で行を突き合わせる処理（シート書出/取込・CSV出力・
# アーカイブ等）や在庫連動処理が壊れるため実行させない。画面側でもブロックしているが、直接APIを
# 叩かれても止まるようサーバー側でも弾く。
# 除外（重複中でも常に許可）: N番を1行だけ直す set_serial / 未採番採番 autonumber / 全件削除 delete_all。
def block_if_serial_dup(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id and has_duplicate_agent_serial_no(user_id):
            return jsonify({
                "status": "error",
                "message": "N番号に重複があるため実行できません。赤字のN番を修正してください。",
            }), 409
        return fn(*args, **kwargs)

    return wrapper


# --- ▼ SECTION 01: 注文レポートCSVインポート ▼ ---
@orbit_bp.route("/import", methods=["POST"])
@block_if_serial_dup
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


# --- ▼ SECTION 01-2: 決済レポート(Settlement Report)インポート（実利益算定用） ▼ ---
@orbit_bp.route("/settlements/import", methods=["POST"])
@block_if_serial_dup
def import_settlements():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "message": "ファイルがありません"}), 400

    text = file.read().decode("utf-8-sig", errors="replace")

    try:
        rows = parse_settlement_report(text)
    except Exception as e:
        return jsonify({"status": "error", "message": f"CSV解析に失敗しました: {e}"}), 400

    count = import_settlement_lines(user_id, rows)

    return jsonify({"status": "success", "imported": count})


# --- ▼ SECTION 02: 注文一覧取得（サイズ・重量・予測送料つき） ▼ ---
@orbit_bp.route("/orders", methods=["GET"])
def get_orders():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    # 1行でも計算で例外が出ると 500(HTML) を返し、フロントが「読み込めなかった」トースト＋
    # 空画面になっていた。JSONでエラーを返し、原因をログに残す。
    try:
        rows = list_orders_with_calc(user_id)
    except Exception:
        import traceback
        print("[orbit/orders] list_orders_with_calc ERROR")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "注文一覧の集計でエラーが発生しました"}), 500

    return jsonify({"status": "success", "rows": rows})


# --- ▼ SECTION 02-1b: 1注文だけの再計算（寸法/手数料取得・領収書取込・メモ追加後、画面側が
#     全件リロードせずその行だけ更新するために使う。同一order_idの他商品も一緒に返す
#     ＝決済按分の計算に必要なため） ▼ ---
@orbit_bp.route("/orders/recompute_group", methods=["GET"])
def recompute_order_group_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    order_id = (request.args.get("order_id") or "").strip()
    if not order_id:
        return jsonify({"status": "error", "message": "order_idが必要です"}), 400

    try:
        rows = recompute_order_group(user_id, order_id)
    except Exception:
        import traceback
        print("[orbit/orders/recompute_group] ERROR")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "再計算でエラーが発生しました"}), 500

    return jsonify({"status": "success", "rows": rows})


# --- ▼ SECTION 02-2: 売上トレンド（Dashboard「売上トレンド」サブタブ用・読み取り専用） ▼ ---
# マーケット別の日次販売個数（折れ線）＋ツールチップ用の総額（現地通貨）・概算利益率を返す。
# 集計は注文一覧と同じ list_orders_with_calc を通すため、期間が長いと数秒かかることがある。
@orbit_bp.route("/sales-trend", methods=["GET"])
def sales_trend():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        days = 30

    try:
        data = get_sales_trend(user_id, days)
    except Exception:
        import traceback
        print("[orbit/sales-trend] get_sales_trend ERROR")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "売上トレンドの集計でエラーが発生しました"}), 500

    return jsonify({"status": "success", "data": data})


# --- ▼ SECTION 03: 手入力項目の更新（JAN・仕入価格・依頼日・発送種別・トラッキング・備考） ▼ ---
@orbit_bp.route("/orders/update", methods=["POST"])
@block_if_serial_dup
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
        if key in NUMERIC_MANUAL_FIELDS:
            value = float(value) if value not in (None, "") else None
        fields[key] = value

    # --- ▼ 「仕入済」チェックを 0→1 にした瞬間だけ再出品する ▼ ---
    #     売れた時点では在庫0のまま（自動再出品しない）。実際にJPで仕入れた人間が
    #     「仕入済」を押した＝JP在庫を自分の目で確認済み、というのを再出品のゲートに
    #     する（在庫の少ない商品の売り越し防止）。もう売りたくない場合はブラック
    #     リスト or List削除で対応する運用。1→0（チェック解除）では何もしない。
    restock_on_purchase = (
        fields.get("purchased") in (1, "1", True)
        and not order_flag_is_set(user_id, order_item_id, "purchased")
    )

    update_manual_fields(user_id, order_item_id, fields)

    restock_result = None
    if restock_on_purchase:
        try:
            restock_result = relist_after_purchase(user_id, order_item_id)
        except Exception:
            import traceback
            print("[orbit/orders/update] relist_after_purchase ERROR")
            traceback.print_exc()

    return jsonify({"status": "success", "restock": restock_result})


# --- ▼ SECTION 03-1: 注文の削除（行ごと／全件リセット） ▼ ---
@orbit_bp.route("/orders/delete", methods=["POST"])
@block_if_serial_dup
def delete_order_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    if not order_item_id:
        return jsonify({"status": "error"}), 400

    deleted = delete_order(user_id, order_item_id)
    return jsonify({"status": "success", "deleted": deleted})


@orbit_bp.route("/orders/delete_all", methods=["POST"])
def delete_all_orders_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    if data.get("confirm") != "DELETE":
        return jsonify({"status": "error", "message": "確認コードが一致しません"}), 400

    deleted = delete_all_orders(user_id)
    return jsonify({"status": "success", "deleted": deleted})


# --- ▼ SECTION 03-1a: 買い手購入履歴アーカイブ ▼ ---
@orbit_bp.route("/buyer_history/import", methods=["POST"])
@block_if_serial_dup
def import_buyer_history_route():
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

    count = import_buyer_history_csv(user_id, rows)

    return jsonify({"status": "success", "imported": count})


# 既存の買い手履歴UPLOADでそのまま取り込み直せる形式のCSVバックアップ（buyer_historyのみ）。
@orbit_bp.route("/buyer_history/export", methods=["GET"])
@block_if_serial_dup
def export_buyer_history_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    csv_text = export_buyer_history_csv(user_id)
    filename = f"buyer_history_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@orbit_bp.route("/buyer_history/list", methods=["GET"])
def list_buyer_history_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    rows = list_buyer_history(user_id)
    return jsonify({"status": "success", "rows": rows})


@orbit_bp.route("/asin_shipping_history", methods=["GET"])
def asin_shipping_history_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    asin = (request.args.get("asin") or "").strip().upper()
    if not asin:
        return jsonify({"status": "error", "message": "asin required"}), 400

    rows = get_asin_shipping_history(user_id, asin)
    return jsonify({"status": "success", "rows": rows})


@orbit_bp.route("/security_notes/list", methods=["GET"])
def list_security_notes_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    rows = list_security_notes(user_id)
    return jsonify({"status": "success", "rows": rows})


# --- ▼ SECTION 02-3: クレジットカードマスタ（仕入れ利用カードの選択肢＋締め日/支払日） ▼ ---
@orbit_bp.route("/credit_cards", methods=["GET"])
def list_credit_cards_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    return jsonify({"status": "success", "cards": list_credit_cards(user_id)})


@orbit_bp.route("/credit_cards/insert", methods=["POST"])
def insert_credit_card_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    data = request.get_json(silent=True) or {}
    card_name = (data.get("card_name") or "").strip()
    if not card_name:
        return jsonify({"status": "error", "message": "カード名を入力してください"}), 400
    new_id = add_credit_card(
        user_id, card_name,
        (data.get("closing_day") or "").strip(),
        (data.get("payment_day") or "").strip(),
    )
    return jsonify({"status": "success", "id": new_id})


@orbit_bp.route("/credit_cards/update", methods=["POST"])
def update_credit_card_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    data = request.get_json(silent=True) or {}
    card_id = data.get("id")
    card_name = (data.get("card_name") or "").strip()
    if not card_id or not card_name:
        return jsonify({"status": "error", "message": "idとカード名が必要です"}), 400
    update_credit_card(
        user_id, card_id, card_name,
        (data.get("closing_day") or "").strip(),
        (data.get("payment_day") or "").strip(),
    )
    return jsonify({"status": "success"})


@orbit_bp.route("/credit_cards/delete", methods=["POST"])
def delete_credit_card_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    data = request.get_json(silent=True) or {}
    card_id = data.get("id")
    if not card_id:
        return jsonify({"status": "error", "message": "idが必要です"}), 400
    delete_credit_card(user_id, card_id)
    return jsonify({"status": "success"})


# --- ▼ SECTION 02-4: 休日設定（日本の祝日 ＋ 発送代行会社の長期休業） ▼ ---
# フロント（orbit.js）が到着予定日・出荷期日の休業日色付けに使う。
@orbit_bp.route("/holidays", methods=["GET"])
def list_holidays_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    # 過去分まで返しても意味が薄いので、少し前（前年頭）以降だけ渡す
    from datetime import date
    from_date = f"{date.today().year - 1}-01-01"

    return jsonify({
        "status": "success",
        "jp_holidays": list_jp_holidays(from_date),
        "closures": list_agent_closures(user_id),
    })


@orbit_bp.route("/agent_closures/insert", methods=["POST"])
def insert_agent_closure_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    data = request.get_json(silent=True) or {}
    start_date = (data.get("start_date") or "").strip()
    end_date = (data.get("end_date") or "").strip()
    if not start_date:
        return jsonify({"status": "error", "message": "開始日を入力してください"}), 400
    try:
        new_id = add_agent_closure(user_id, start_date, end_date, data.get("label") or "")
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "success", "id": new_id})


@orbit_bp.route("/agent_closures/delete", methods=["POST"])
def delete_agent_closure_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401
    data = request.get_json(silent=True) or {}
    closure_id = data.get("id")
    if not closure_id:
        return jsonify({"status": "error", "message": "idが必要です"}), 400
    delete_agent_closure(user_id, closure_id)
    return jsonify({"status": "success"})


@orbit_bp.route("/archive/candidates", methods=["GET"])
def archive_candidates_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    rows = list_archive_candidates(user_id)
    return jsonify({"status": "success", "rows": rows})


@orbit_bp.route("/archive/run", methods=["POST"])
@block_if_serial_dup
def archive_run_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_ids = data.get("order_item_ids")
    if not order_item_ids or not isinstance(order_item_ids, list):
        return jsonify({"status": "error", "message": "order_item_idsが必要です"}), 400

    archived = archive_orders(user_id, order_item_ids)
    return jsonify({"status": "success", "archived": archived})


# --- ▼ SECTION 03-1a-2: 返品・セキュリティメモ ▼ ---
@orbit_bp.route("/security_notes/add", methods=["POST"])
@block_if_serial_dup
def add_security_note_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    note = data.get("note")
    if not order_item_id or not note:
        return jsonify({"status": "error", "message": "order_item_idとnoteが必要です"}), 400

    added = add_security_note(user_id, order_item_id, note)
    if not added:
        return jsonify({"status": "error", "message": "対象の注文が見つかりませんでした"}), 404

    return jsonify({"status": "success"})


@orbit_bp.route("/security_notes/update", methods=["POST"])
@block_if_serial_dup
def update_security_note_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    note_id = data.get("note_id")
    note = data.get("note")
    if not note_id or not note:
        return jsonify({"status": "error", "message": "note_idとnoteが必要です"}), 400

    updated = update_security_note(user_id, note_id, note)
    if not updated:
        return jsonify({"status": "error", "message": "対象のメモが見つかりませんでした"}), 404

    return jsonify({"status": "success"})


# --- ▼ SECTION 03-1b: 寸法・重量が無いASINをその場でHOME APIから取得 ▼ ---
@orbit_bp.route("/orders/fetch_catalog", methods=["POST"])
@block_if_serial_dup
def fetch_catalog_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    asin = data.get("asin")
    if not asin:
        return jsonify({"status": "error", "message": "ASINが必要です"}), 400

    try:
        dims = fetch_and_cache_catalog_for_asin(user_id, asin)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **dims})


# --- ▼ SECTION 03-1c: 出荷前の概算利益用（SP-API手数料見積りをその場で取得） ▼ ---
@orbit_bp.route("/orders/fetch_fee_estimate", methods=["POST"])
@block_if_serial_dup
def fetch_fee_estimate_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    if not order_item_id:
        return jsonify({"status": "error", "message": "order_item_idが必要です"}), 400

    try:
        estimate = fetch_and_cache_fee_estimate(user_id, order_item_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **estimate})


# --- ▼ SECTION 03-2: 代行会社連番の設定（先頭を入れると以降は自動連番） ▼ ---
# N番セルの編集＝その1行だけ変更。連番の一括振り直しは廃止（他の行には触らない）。
# 重複ガードは付けない（重複を直す唯一の手段のため、重複中でも常に実行できる必要がある）。
@orbit_bp.route("/orders/set_serial", methods=["POST"])
def set_serial():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    value = data.get("start_value")

    if not order_item_id or value in (None, ""):
        return jsonify({"status": "error"}), 400

    try:
        value = int(value)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "N番は数値で入力してください"}), 400

    count = set_agent_serial_no(user_id, order_item_id, value)
    return jsonify({"status": "success", "updated": count})


# --- ▼ SECTION 03-3: 未採番の一括採番（取込順で既存の続きから連番） ▼ ---
@orbit_bp.route("/orders/autonumber", methods=["POST"])
def autonumber_serial():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    count = assign_missing_agent_serial_no(user_id)
    return jsonify({"status": "success", "updated": count})


# --- ▼ SECTION 04: 発送代行への通知用CSV出力 ▼ ---
@orbit_bp.route("/export", methods=["GET"])
@block_if_serial_dup
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


# --- ▼ SECTION 04-2: 販売額・手数料見積り結果の機体間受け渡し（ATLAS(AU)⇔ZSSS(CA/US)） ▼ ---
@orbit_bp.route("/fee_data/export", methods=["GET"])
@block_if_serial_dup
def export_fee_data():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    csv_text = export_fee_data_csv(user_id)

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orbit_fee_data.csv"},
    )


@orbit_bp.route("/fee_data/import", methods=["POST"])
@block_if_serial_dup
def import_fee_data_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    file = request.files.get("file")
    if not file:
        return jsonify({"status": "error", "message": "ファイルがありません"}), 400

    text = file.read().decode("utf-8-sig", errors="replace")

    try:
        rows = parse_fee_data_csv(text)
    except Exception as e:
        return jsonify({"status": "error", "message": f"CSV解析に失敗しました: {e}"}), 400

    count = import_fee_data(user_id, rows)

    return jsonify({"status": "success", "imported": count})


# --- ▼ SECTION 05: Google OAuth連携（依頼書シート読み戻し用） ▼ ---
@orbit_bp.route("/google_oauth/status", methods=["GET"])
def google_oauth_status():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    # 行の有無だけでなく実際にトークンを更新できるかまで確認する（失効時は自動で行が消え、再連携ボタンが出る）
    return jsonify({"status": "success", "connected": has_working_connection(user_id)})


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
@block_if_serial_dup
def dispatch_sheet_sync():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = sync_dispatch_sheet_status(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


# --- ▼ SECTION 10: 書き出し先（ZSSS_RAWタブ）設定 ▼ ---
@orbit_bp.route("/raw_sheet_settings", methods=["GET"])
def get_raw_sheet_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    settings = get_raw_sheet_settings(user_id)
    return jsonify({"status": "success", **settings})


@orbit_bp.route("/raw_sheet_settings", methods=["POST"])
def save_raw_sheet_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    spreadsheet_url = (data.get("spreadsheet_url") or "").strip()
    sheet_name = (data.get("sheet_name") or "").strip()
    mirror_spreadsheet_url = (data.get("mirror_spreadsheet_url") or "").strip()
    mirror_sheet_name = (data.get("mirror_sheet_name") or "").strip()

    if not spreadsheet_url:
        return jsonify({"status": "error", "message": "スプレッドシートURLが必要です"}), 400
    if not sheet_name:
        return jsonify({"status": "error", "message": "書き込み先のタブ名が必要です"}), 400
    # ミラーはURL・タブ名の両方セットで有効。片方だけはミス防止のためエラー。
    if bool(mirror_spreadsheet_url) != bool(mirror_sheet_name):
        return jsonify({"status": "error", "message": "ミラー先はURLとタブ名の両方を入力してください（不要なら両方空に）"}), 400

    save_raw_sheet_settings(user_id, spreadsheet_url, sheet_name, mirror_spreadsheet_url, mirror_sheet_name)
    return jsonify({"status": "success"})


# --- ▼ SECTION 11: 自分の管理シート（ZSSS_RAWタブ）へ書き出し ▼ ---
@orbit_bp.route("/raw_sheet_push", methods=["POST"])
@block_if_serial_dup
def raw_sheet_push():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = push_orders_to_raw_sheet(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


# --- ▼ SECTION 12: 代行会社デポジット残高（依頼書シートA1） ▼ ---
@orbit_bp.route("/deposit_balance", methods=["GET"])
def deposit_balance():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = fetch_deposit_balance(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


# --- ▼ SECTION 12-2: 為替レート（集計パネルの円換算表示用。JPY建て1単位あたりの円） ▼ ---
@orbit_bp.route("/fx_rates", methods=["GET"])
def fx_rates():
    if not session.get("user_id"):
        return jsonify({"status": "error"}), 401

    currencies = [c.strip().upper() for c in (request.args.get("currencies") or "").split(",") if c.strip()]
    rates = {}
    for ccy in currencies:
        if ccy == "JPY":
            rates[ccy] = 1.0
            continue
        rate = get_exchange_rate("JPY", ccy)
        if rate is not None:
            rates[ccy] = rate

    return jsonify({"status": "success", "rates": rates})


# --- ▼ SECTION 13: 領収書PDF取込（発注管理・領収書列「一括読込」） ▼ ---
@orbit_bp.route("/receipt_settings", methods=["GET"])
def get_receipt_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    return jsonify({"status": "success", **get_receipt_settings(user_id)})


@orbit_bp.route("/receipt_settings", methods=["POST"])
def save_receipt_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    inbox_dir = (data.get("inbox_dir") or "").strip()
    store_dir = (data.get("store_dir") or "").strip()

    save_receipt_settings(user_id, inbox_dir, store_dir)
    return jsonify({"status": "success"})


# --- ▼ SECTION 13-2: 依頼フォームURL（発注管理・トランザクション欄横の「依頼フォーム」ボタン） ▼ ---
@orbit_bp.route("/request_form_url", methods=["GET"])
def get_request_form_url_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    return jsonify({"status": "success", "request_form_url": get_request_form_url(user_id)})


@orbit_bp.route("/request_form_url", methods=["POST"])
def save_request_form_url_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    request_form_url = (data.get("request_form_url") or "").strip()

    save_request_form_url(user_id, request_form_url)
    return jsonify({"status": "success"})


@orbit_bp.route("/receipt_inbox_status", methods=["GET"])
def receipt_inbox_status_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = inbox_status(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


@orbit_bp.route("/receipt_import", methods=["POST"])
@block_if_serial_dup
def receipt_import_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = run_receipt_import(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


# --- ▼ SECTION 14: 管理品タブ設定（タブ名。URLは依頼書シート設定を使い回す） ▼ ---
@orbit_bp.route("/kanrihin_settings", methods=["GET"])
def get_kanrihin_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    return jsonify({"status": "success", "sheet_name": get_kanrihin_sheet_name(user_id)})


@orbit_bp.route("/kanrihin_settings", methods=["POST"])
def save_kanrihin_settings_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    sheet_name = (data.get("sheet_name") or "").strip()
    save_kanrihin_sheet_name(user_id, sheet_name)
    return jsonify({"status": "success"})


# --- ▼ SECTION 15: 管理品一覧（代行会社シート「管理品」タブの読み戻し＋確認状態） ▼ ---
@orbit_bp.route("/kanrihin_items", methods=["GET"])
def kanrihin_items_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    try:
        result = list_kanrihin_items(user_id)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", **result})


@orbit_bp.route("/kanrihin_confirm", methods=["POST"])
def kanrihin_confirm_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}

    # 確認済みボタンの再押しで解除（未確認に戻す）。単発の管理No.のみ対応。
    if data.get("confirmed") is False:
        management_no = (data.get("management_no") or "").strip()
        release_kanrihin_item(user_id, management_no)
        return jsonify({"status": "success"})

    management_nos = data.get("management_nos") or []
    confirm_kanrihin_items(user_id, management_nos)
    return jsonify({"status": "success"})


# --- ▼ SECTION 16: 管理品の行にN番を手動リンク（JAN不明品を後から突き止めた注文と紐付け） ▼ ---
@orbit_bp.route("/kanrihin_link", methods=["POST"])
def kanrihin_link_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    management_no = (data.get("management_no") or "").strip()
    agent_serial_no = data.get("agent_serial_no")

    try:
        order_info = save_kanrihin_link(user_id, management_no, agent_serial_no)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "order_info": order_info})


# --- ▼ SECTION 17: 管理品の「処理済」（保管在庫が無くなった印）手動ON/OFF ▼ ---
@orbit_bp.route("/kanrihin_processed", methods=["POST"])
def kanrihin_processed_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    management_no = (data.get("management_no") or "").strip()

    try:
        set_kanrihin_processed(user_id, management_no, bool(data.get("processed")))
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    return jsonify({"status": "success"})


# --- ▼ SECTION 18: 発注管理「管理品から出荷」（元N番の仕入情報を移植→処理済→在庫ゼロなら
#     全マーケットの手入力価格OFF→仕入済ON） ▼ ---
@orbit_bp.route("/orders/ship_from_kanrihin", methods=["POST"])
@block_if_serial_dup
def ship_from_kanrihin_route():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error"}), 401

    data = request.get_json(silent=True) or {}
    order_item_id = data.get("order_item_id")
    if not order_item_id:
        return jsonify({"status": "error", "message": "order_item_idが必要です"}), 400

    try:
        result = ship_from_kanrihin(user_id, order_item_id)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception:
        import traceback
        print("[orbit/orders/ship_from_kanrihin] ERROR")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "管理品から出荷の処理でエラーが発生しました"}), 500

    return jsonify({"status": "success", **result})
