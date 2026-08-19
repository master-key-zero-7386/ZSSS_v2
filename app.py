# ==========================================
# ファイル名: zsss_web/app.py
# 目的: 
# ==========================================

import sys
import os
import threading

from amazon.routes.routes import amazon_bp
from tools.remote_area_routes import remote_area_bp
from flask import Flask, render_template, jsonify, request, redirect
import json
import codecs
from amazon.csv_import import csv_import_bp
from amazon.routes.routes_listing import listing_bp
import logging
import traceback
from logging.handlers import RotatingFileHandler
from amazon.routes.routes_pricing_v2 import pricing_v2_bp
from auth.routes_auth import auth_bp
from amazon.routes.routes_account import account_bp
from amazon.routes.routes_admin import admin_api_bp
from amazon.routes.routes_admin import admin_market_bp
from amazon.routes.routes_admin import admin_api_bp, admin_market_bp

from api_check.a_api_scan_allcheck import api_raw_check_bp
import amazon.shipping_calc
from amazon.routes.routes_shipping import shipping_bp
from amazon.routes.routes_oauth import amazon_oauth_bp
from amazon.routes.routes_blacklist import blacklist_bp
from amazon.background.first.first_loop import run_first_loop
from amazon.background.first.first_regioncheck import run_first_regioncheck 
from amazon.background.ttl.ttl_loop import run_ttl_loop
from amazon.background.fx.fx_loop import run_fx_loop
from amazon.routes.routes_override_seller import override_seller_bp


# ✅ コマンド引数から実行モードを判定（デフォルトは "dev"）
mode = sys.argv[1] if len(sys.argv) > 1 else "dev"

# ✅ Flaskアプリ初期化
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config["ZSSS_MODE"] = mode       # ← 追加：どのPC(dev/zsss/atlas)かを保存しておく
app.config['MAX_FORM_MEMORY_SIZE'] = None
app.config['MAX_FORM_PARTS'] = 1000000
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["DB_DIR"] = os.path.join(BASE_DIR, "db")

app.debug = False

base_dir = os.path.abspath(os.path.dirname(__file__))

sys.path.append(os.path.dirname(__file__))  # ← zsss_web を明示的に検索パスに追加

app.secret_key = 'your-secret-key'  
app.config['UPLOAD_FOLDER'] = 'uploads'

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

# Blueprint 登録
app.register_blueprint(amazon_bp, url_prefix="/amazon")
app.register_blueprint(amazon_oauth_bp, url_prefix="/amazon")
app.register_blueprint(blacklist_bp) # 新BlackList
app.register_blueprint(remote_area_bp, url_prefix="/tools/remote_area")
app.register_blueprint(csv_import_bp, url_prefix="/csv")
app.register_blueprint(listing_bp, url_prefix="/listing")
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(account_bp, url_prefix="/account")
app.register_blueprint(override_seller_bp, url_prefix="/override_seller")
app.register_blueprint(admin_api_bp, url_prefix="/admin")
app.register_blueprint(admin_market_bp, url_prefix="/admin_market")
app.register_blueprint(api_raw_check_bp) # APIチェック用　
app.register_blueprint(shipping_bp, url_prefix="/api")
app.register_blueprint(pricing_v2_bp)


# first loop常駐起動
def start_first_runner(app):
    if getattr(app, "_first_runner_started", False):
        return

    app._first_runner_started = True
    db_dir = app.config.get("DB_DIR")

    t = threading.Thread(
        target=run_first_loop,
        args=(app, db_dir),
        daemon=True
    )
    t.start()
    print("[FIRST] runner STARTED")

# first regioncheck常駐起動
def start_first_regioncheck_runner(app):
    if getattr(app, "_first_regioncheck_runner_started", False):
        return

    app._first_regioncheck_runner_started = True
    db_dir = app.config.get("DB_DIR")

    t = threading.Thread(
        target=run_first_regioncheck,
        args=(app, db_dir),
        daemon=True
    )
    t.start()
    print("[FIRST_REGIONCHECK] runner STARTED")

# ttl loop常駐起動
def start_ttl_runner(app):
    if getattr(app, "_ttl_runner_started", False):
        return

    app._ttl_runner_started = True
    db_dir = app.config.get("DB_DIR")

    t = threading.Thread(
        target=run_ttl_loop,
        args=(app, db_dir),
        daemon=True
    )
    t.start()
    print("[TTL] runner STARTED")

# fx loop常駐起動
def start_fx_runner(app):
    if getattr(app, "_fx_runner_started", False):
        return

    app._fx_runner_started = True

    t = threading.Thread(
        target=run_fx_loop,
        args=(app,),
        daemon=True
    )
    t.start()
    print("[FX] runner STARTED")   

# ✅ 追加：すべてのHTMLテンプレートで「今のモード(dev/zsss/atlas)」を使えるようにする
@app.context_processor
def inject_zsss_mode():
    return {"zsss_mode": app.config.get("ZSSS_MODE", "dev")}


@app.route("/")
def index():

    return redirect("/amazon/#account") 

if __name__ == "__main__":
    print(">>> Flask main() start <<<")

    # --- DBマイグレーションを先に実行 ---
    from amazon import db_migrate
    db_migrate.main()

    # --- TTL・firstは起動時に1回だけ ---
    start_first_runner(app)
    start_first_regioncheck_runner(app)
    start_ttl_runner(app)
    start_fx_runner(app)

    file_handler = RotatingFileHandler(
        'app_error.log', maxBytes=1024 * 1024, backupCount=2, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.ERROR)
    app.logger.addHandler(file_handler)

    # チェック完了後削除
    for rule in app.url_map.iter_rules():
        if "override" in rule.rule:
            print(rule.endpoint, rule.rule, rule.methods)  # チェック完了後削除
            
    # --- Flaskサーバ起動（これ1回だけ！） ---
    # threaded=True: ページ初期表示時に多数のAPIをブラウザが並列で叩くため、
    # シングルスレッドのままだと1本ずつ直列処理になり待ち時間が積み上がっていた。
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False, threaded=True)






