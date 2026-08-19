from datetime import date

from flask import Blueprint, request, jsonify, Response

from amazon.db import get_conn
from utils.remote_area_parser import parse_paste, is_in_range, expand_range

remote_area_bp = Blueprint("remote_area_bp", __name__)

CARRIERS = ("DHL", "FEDEX")


def _normalize_carrier(carrier: str) -> str:
    return (carrier or "").strip().upper()


# --- ▼ 登録済み国一覧（キャリアごと。取り込み日・件数つき） ---
@remote_area_bp.route("/countries", methods=["GET"])
def list_countries():
    carrier = _normalize_carrier(request.args.get("carrier"))
    if carrier not in CARRIERS:
        return jsonify({"error": "carrier must be DHL or FEDEX"}), 400

    conn = get_conn("a_carrier_remote_area.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT country_code, MAX(imported_at) AS imported_at, COUNT(*) AS row_count
        FROM carrier_remote_area_codes
        WHERE carrier = %s
        GROUP BY country_code
        ORDER BY country_code
    """, (carrier,))
    rows = cur.fetchall()
    conn.close()

    return jsonify({"countries": [dict(r) for r in rows]})


# --- ▼ 取り込み（既に同一キャリア・国のデータがあれば拒否） ---
@remote_area_bp.route("/import", methods=["POST"])
def import_codes():
    data = request.get_json(silent=True) or {}
    carrier = _normalize_carrier(data.get("carrier"))
    country_code = (data.get("country_code") or "").strip().upper()
    text = data.get("text", "")

    if carrier not in CARRIERS:
        return jsonify({"error": "carrier must be DHL or FEDEX"}), 400
    if not country_code:
        return jsonify({"error": "country_code is required"}), 400

    pairs = parse_paste(text)
    if not pairs:
        return jsonify({"error": "有効な行が見つかりませんでした"}), 400

    conn = get_conn("a_carrier_remote_area.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS cnt FROM carrier_remote_area_codes
        WHERE carrier = %s AND country_code = %s
    """, (carrier, country_code))
    existing = cur.fetchone()["cnt"]

    if existing:
        conn.close()
        return jsonify({
            "error": "exists",
            "message": f"{carrier} / {country_code} のデータは既に存在します。先にリセットしてください。"
        }), 409

    today = date.today().isoformat()
    cur.executemany("""
        INSERT INTO carrier_remote_area_codes
            (carrier, country_code, postal_from, postal_to, imported_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, [
        (carrier, country_code, pf, pt, today, today)
        for pf, pt in pairs
    ])
    conn.commit()
    conn.close()

    return jsonify({"imported": len(pairs), "imported_at": today})


# --- ▼ リセット（キャリア＋国指定で削除） ---
@remote_area_bp.route("/reset", methods=["POST"])
def reset_codes():
    data = request.get_json(silent=True) or {}
    carrier = _normalize_carrier(data.get("carrier"))
    country_code = (data.get("country_code") or "").strip().upper()

    if carrier not in CARRIERS:
        return jsonify({"error": "carrier must be DHL or FEDEX"}), 400
    if not country_code:
        return jsonify({"error": "country_code is required"}), 400

    conn = get_conn("a_carrier_remote_area.db")
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM carrier_remote_area_codes
        WHERE carrier = %s AND country_code = %s
    """, (carrier, country_code))
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    return jsonify({"deleted": deleted})


# --- ▼ 郵便番号単体判定（DHL/FedEx 両方まとめてチェック） ---
@remote_area_bp.route("/check", methods=["POST"])
def check_postal():
    data = request.get_json(silent=True) or {}
    country_code = (data.get("country_code") or "").strip().upper()
    postal_code = (data.get("postal_code") or "").strip()

    if not country_code or not postal_code:
        return jsonify({"error": "country_code and postal_code are required"}), 400

    conn = get_conn("a_carrier_remote_area.db")
    cur = conn.cursor()

    result = {}
    for carrier in CARRIERS:
        cur.execute("""
            SELECT postal_from, postal_to FROM carrier_remote_area_codes
            WHERE carrier = %s AND country_code = %s
        """, (carrier, country_code))
        rows = cur.fetchall()

        matched = None
        for r in rows:
            if is_in_range(postal_code, r["postal_from"], r["postal_to"]):
                matched = {"postal_from": r["postal_from"], "postal_to": r["postal_to"]}
                break

        result[carrier] = {
            "remote": matched is not None,
            "matched_range": matched,
            "checked_rows": len(rows),
        }

    conn.close()
    return jsonify(result)


# --- ▼ CSV出力（キャリア＋国指定） ---
@remote_area_bp.route("/export", methods=["GET"])
def export_csv():
    carrier = _normalize_carrier(request.args.get("carrier"))
    country_code = (request.args.get("country_code") or "").strip().upper()

    if carrier not in CARRIERS:
        return jsonify({"error": "carrier must be DHL or FEDEX"}), 400
    if not country_code:
        return jsonify({"error": "country_code is required"}), 400

    conn = get_conn("a_carrier_remote_area.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT postal_from, postal_to FROM carrier_remote_area_codes
        WHERE carrier = %s AND country_code = %s
    """, (carrier, country_code))
    rows = cur.fetchall()
    conn.close()

    codes: set[str] = set()
    for r in rows:
        codes.update(expand_range(r["postal_from"], r["postal_to"]))

    csv_body = "\n".join(sorted(codes)) + ("\n" if codes else "")

    filename = f"{carrier}_{country_code}_remote_area.csv"
    return Response(
        csv_body,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
