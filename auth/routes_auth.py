# ==========================================
# ファイル名: auth/routes_auth.py
# 目的: 認証関連ルートのBlueprint
# ==========================================
from flask import Blueprint
from flask import render_template
from flask import request, jsonify, session, redirect, url_for
from functools import wraps

auth_bp = Blueprint("auth_bp", __name__)

# === ▼ login_required（全ルートで共通利用）▼ ===
def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth_bp.login_page"))
        return func(*args, **kwargs)
    return decorated_view
# === ▲ login_required（ここまで）▲ ===

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if "user_id" in session:
        return redirect("/amazon/")
    return render_template("auth/login.html")

# === ▼ ログイン処理（a_user_login_accounts.db 使用） ▼ ===
@auth_bp.route("/login", methods=["POST"])
def login_auth():
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"status": "error", "message": "メールまたはパスワードが未入力です"}), 400

    from amazon.db import get_conn
    conn = get_conn("a_user_login_accounts.db")
    cur = conn.cursor()

    # is_admin → role に修正済み
    cur.execute(
        "SELECT id, email, password_hash, role, enabled_regions, user_display_name FROM user_login_accounts WHERE email = %s",
        (email,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "error", "message": "メールまたはパスワードが違います"}), 401

    # パスワード照合
    import hashlib
    hashed = hashlib.sha256(password.encode()).hexdigest()

    if hashed != row["password_hash"]:
        return jsonify({"status": "error", "message": "メールまたはパスワードが違います"}), 401

    # --- ログイン成功 ---
    session["user_id"] = row["id"]
    session["is_admin"] = (row["role"] == "admin")
    session["enabled_regions"] = (row["enabled_regions"] or "").split(",")
    session["user_display_name"] = row["user_display_name"]

    return jsonify({"status": "ok"})

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})   

# --- ユーザー権限を返すAPI（初期ロードで使用） ---
@auth_bp.route("/get_user_role", methods=["GET"])
def get_user_role():
    return jsonify({
        "status": "ok",
        "is_admin": session.get("is_admin", False),
        "enabled_regions": session.get("enabled_regions", []),
        "user_id": session.get("user_id")
    })

