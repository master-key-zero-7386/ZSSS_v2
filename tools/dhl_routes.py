from flask import Blueprint, request, jsonify, Response
from utils.dhl_remote_parser import expand_postal_tokens

dhl_bp = Blueprint("dhl_bp", __name__)

@dhl_bp.route("/remote_expand", methods=["POST"])
def remote_expand():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    codes = expand_postal_tokens(text)
    return jsonify({"codes": codes})

@dhl_bp.route("/remote_export", methods=["POST"])
def remote_export():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    codes = expand_postal_tokens(text)
    csv_body = "\n".join(codes) + ("\n" if codes else "")
    return Response(
        csv_body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=dhl_remote_codes.csv"},
    )

