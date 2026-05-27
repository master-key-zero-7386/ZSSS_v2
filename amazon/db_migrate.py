# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/db_migrate.py
# 目的: DB接続と設定操作の統一モジュール
# ==========================================================

import os
import sqlite3
import glob

from amazon.db import get_conn, DB_MODE 

# DBフォルダ
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db")


def get_conn_old(db_name: str):
    """指定DBへ接続（DB生成は db_migrate.py のみで行う）"""

    # --- ▼ ここで保存先を決める（今回は blacklist のみ） ---
    if "_blacklist_" in db_name:
        db_path = os.path.join(DB_DIR, "blacklist", db_name)
    elif "_seller_list" in db_name:
        db_path = os.path.join(DB_DIR, "sellerlist", db_name)

    else:
        db_path = os.path.join(DB_DIR, db_name)

    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path, timeout=30) # 一旦保留
    conn.row_factory = sqlite3.Row

    return conn


ACCOUNT_MASTER_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "home_flag": "INTEGER DEFAULT 0",
    "country_code": "TEXT NOT NULL",
    "account_seller_id": "TEXT",
    "refresh_token": "TEXT",
    "status": "TEXT DEFAULT 'active'",
    "created_at": "TEXT",
    "updated_at": "TEXT"
}


API_USAGE_LOGS_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "marketplace_id": "TEXT NOT NULL",
    "endpoint": "TEXT NOT NULL",
    "created_at": "TEXT",
}

# --- ▼ background scan settings（管理者用・全体巡回制御） ---
BG_SCAN_SETTINGS_COLUMNS = {
    "id": "INTEGER PRIMARY KEY",              # 常に1レコード前提（id=1）
    "interval_min": "REAL NOT NULL",          # 巡回間隔（分・小数可）
    "scan_limit": "INTEGER NOT NULL",         # 1巡回あたりの最大処理件数
    "updated_at": "TEXT",                     
    "ttl_sleep_sec": "REAL",                  # TTL SleepTIME
}


BLACKLIST_ASIN_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "asin": "TEXT NOT NULL",
    "note": "TEXT",
    "created_at": "TEXT"
}

BLACKLIST_BRAND_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "brand": "TEXT NOT NULL",
    "note": "TEXT",
    "created_at": "TEXT"
}

# # --- BlackList 管理者用カラム ---
# BLACKLIST_BRAND_COLUMNS = {
#     # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
#     "id": "SERIAL PRIMARY KEY",
#     "user_id": "INTEGER",
#     "Brand": "TEXT NOT NULL",
#     "Rank": "TEXT",
#     "note": "TEXT",
#     "JapanBrand": "TEXT",
#     "timestamp": "TEXT"
# }

# --- ▼ SECTION : admin settings（管理者設定） ▼ ---
ADMIN_SETTINGS_COLUMNS = {
    "key": "TEXT PRIMARY KEY",
    "value": "TEXT"
}

# --- ▼ SECTION ： Bland Gate用 ▼ ---
BRAND_GATE_RESULT_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "brand": "TEXT NOT NULL",
    "status": "TEXT",          # OK / NG
    "reason": "TEXT",          # エラー内容
    "updated_at": "TEXT"
}

CATALOG_CACHE_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    # "user_id": "INTEGER NOT NULL",
    "asin": "TEXT NOT NULL",
    # "sku": "TEXT NOT NULL",
    "home_marketplace_id": "TEXT",
    "region_marketplace_id": "TEXT",       
    "home_raw_json": "TEXT",      
    "region_raw_json": "TEXT",

    "h_catalog_ttl_at": "TEXT",                     # TTL HOME catalog 巡回記録
    "r_catalog_ttl_at": "TEXT",                     # TTL REFION catalog 巡回記録 

    "home_updated_at": "TEXT",      
    "region_updated_at": "TEXT", 
    "updated_at": "TEXT"
}     

# --- ▼ SECTION : fx_settings（通貨更新設定） ---
FX_SETTINGS_COLUMNS = {
    "provider_name": "TEXT",
    "update_interval_hours": "INTEGER",
    "last_updated_at": "TEXT"
}

# --- ▼ SECTION : fx_rates（為替レート保存） ---
FX_RATES_COLUMNS = {
    "base_currency": "TEXT",
    "target_currency": "TEXT",
    "rate": "REAL",
    "updated_at": "TEXT"
}

PRICING_CACHE_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    # "user_id": "INTEGER NOT NULL",
    "asin": "TEXT NOT NULL",
    # "sku": "TEXT NOT NULL", 
    "home_marketplace_id": "TEXT",
    "region_marketplace_id": "TEXT", 
    "home_offers_json": "TEXT",     
    "region_offers_json": "TEXT",

    "h_pricing_ttl_at": "TEXT",                     # TTL HOME Pricing 巡回記録 
    "r_pricing_ttl_at": "TEXT",                     # TTL REFDGION Pricing 巡回記録 

    "home_updated_at": "TEXT",      
    "region_updated_at": "TEXT", 
    "updated_at": "TEXT"
}


LISTED_ITEMS_COLUMNS = {
    # --- 基本情報 ---
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",      # ID
    "id": "SERIAL PRIMARY KEY",                     # ID
    "user_id": "INTEGER",                           # ユーザ識別ID
    "status": "TEXT NOT NULL DEFAULT 'pre'",        # Pre/ALL Status
    "information_status": "TEXT DEFAULT ''",        # 情報取得状況 Status
    "asin": "TEXT NOT NULL",                        # ASIN
    "sku": "TEXT",                                  # SKU
    "home_marketplace_id": "TEXT",                  # HOMEマーケットプレイスID    
    "region_marketplace_id": "TEXT",                # REGIONマーケットプレイスID
    "image_url": "TEXT",                            # 商品画像URL

    # --- API Stop 404専用 ---
    "api_stop_asin": "INTEGER DEFAULT 0",           # API異常時停止フラグ

    # --- TTL動作定用 （巡回用） ---
    "first_try_count": "INTEGER DEFAULT 10",        # firstチャレンジ回数設定値   
    "ttl_stop_status": "TEXT",                      # TTL更新強制停止

    # --- HOME Catarog情報 ---
    # --- Catarog基本情報 ---
    "home_title": "TEXT",                           # HOME商品タイトル

    "home_brand": "TEXT",                           # HOMEブランド
    "home_manufacturer": "TEXT",                    # HOMEメーカー

    # --- 寸法・重量 ---
    "length_cm": "REAL",                            # HOME寸法
    "width_cm": "REAL",                             # HOME寸法
    "height_cm": "REAL",                            # HOME寸法
    "actual_weight_kg": "REAL",                     # HOME重量　実重量　
    "volumetric_weight_kg": "REAL",                 # HOME重量　容積重量
    "billable_weight_kg": "REAL",                   # HOME重量　請求重量

    # --- 送料（手動変更用） ---
    "override_weight_class": "INTEGER",             # 送料区分 手動変更用 

    # --- 在庫数情報 ---

    # --- Pricing情報 ---
    # --- 価格・関税（編集UI用） ---
    "home_price": "REAL",                           # HOME仕入価格
    "region_price": "REAL",                         # REGION価格
    "override_price": "REAL",                       # 出品価格 手動変更用 
    "final_price": "REAL",                          # 最終出品価格
    "min_price": "REAL",                            # 最低出品価格（計算結果）
    "max_price": "REAL",                            # 最高出品価格（計算結果）   
    "override_tariff_rate": "REAL",                 # 関税率 手動変更用

    # --- REGION Catarog情報 ---
    "region_title": "TEXT",                         # REGION商品タイトル  
    "region_brand": "TEXT",                         # REGIONブランド ブラックリストに必要
    "region_manufacturer": "TEXT",                  # REGIONメーカー ブラックリストに必要

    # --- 出品戦略（ALL専用） ---
    "strategy_quantity": "INTEGER DEFAULT 1",       # 手動在庫数
    "strategy_sellout": "INTEGER DEFAULT 0",        # 売り切り（0/1） 出品価格手動時に利用する在庫数
    "strategy_handling_time": "INTEGER DEFAULT 6",  # 手動Handling Time（日）

    # --- ステータス関連 ---
    "listing_status": "TEXT DEFAULT ''",            # 出品状態 Status
    "deleting_flag": "INTEGER DEFAULT 0",           # 削除状態フラグ：対TTL用

    "created_at": "TEXT",                           # 登録TIME
    "updated_at": "TEXT",                           # 更新TIME

}

# # 未使用 --- ▼ listed brand master（出品実績ブランド） ---
# LISTED_BRAND_MASTER_COLUMNS = {
#     # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
#     "id": "SERIAL PRIMARY KEY",
#     "user_id": "INTEGER NOT NULL",
#     "country_code": "TEXT NOT NULL",
#     "brand": "TEXT",
#     "manufacturer": "TEXT",
#     "created_at": "TEXT"
# }

MARKETPLACES_COLUMNS = {
    # --- a_account_master.dbからコピー 
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "home_flag": "INTEGER",
    "country_code": "TEXT NOT NULL",
    "account_seller_id": "TEXT",
    "refresh_token": "TEXT",

    # --- a_marketplaces_master.dbからコピー 
    "display_name": "TEXT",
    "marketplace_id": "TEXT",
    "access_key": "TEXT",       
    "secret_key": "TEXT",   

    "currency": "TEXT",
    "weight_unit": "TEXT",
    "dimension_unit": "TEXT",
    "host": "TEXT",
    "spapi_host": "TEXT",
    "locale": "TEXT",
    "timezone": "TEXT",    
    "override_exchange_rate": "REAL",

    # --- ▼ API ON/OFF 設定（HOME / REGION） ▼ ---
    "enable_home_catalog":   "INTEGER DEFAULT 0",   
    "enable_home_pricing":   "INTEGER DEFAULT 0",   
    "enable_region_catalog": "INTEGER DEFAULT 0",   
    "enable_region_pricing": "INTEGER DEFAULT 0",   

    # --- ▼ TTL（日）設定（巡回制御用） ▼ ---
    "h_catalog_ttl_days":   "REAL DEFAULT 90",   # HOME Catalog TTL（日）
    "h_pricing_ttl_days":   "REAL DEFAULT 90",   # HOME Pricing TTL（日）
    "r_catalog_ttl_days":   "REAL DEFAULT 90",   # REGION Catalog TTL（日）
    "r_pricing_ttl_days":   "REAL DEFAULT 90",   # REGION Pricing TTL（日）

    "created_at": "TEXT",
    "updated_at": "TEXT"
}

# --- ▼ SECTION : MARKETPLACES　MASTER（管理） ---
# --- ▼ amazon_retail_sellers（Amazon直売 sellerId 管理） ---
AMAZON_RETAIL_SELLERS_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "country_code": "TEXT",
    "seller_id": "TEXT UNIQUE",
    "note": "TEXT"
}

MARKETPLACES_MASTER_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY", 
    "country_code": "TEXT NOT NULL",
    "display_name": "TEXT",
    "marketplace_id": "TEXT",
    "currency": "TEXT",
    "weight_unit": "TEXT",
    "dimension_unit": "TEXT",

    "locale": "TEXT",
    "override_exchange_rate": "REAL",
    "timezone": "TEXT",    
    "tax_mode": "TEXT",     

    "host": "TEXT",
    "spapi_host": "TEXT",    

    "client_id": "TEXT",        
    "client_secret": "TEXT",    
    "access_key": "TEXT",       
    "secret_key": "TEXT",  
    "application_id": "TEXT",  

    "created_at": "TEXT",
    "updated_at": "TEXT"
}


# --- ▼ SECTION ： Pricing Setting設定 ▼ ---
# --- ▼ offer_filter_rules（仕入側：条件フィルタ設定） ---
OFFER_FILTER_RULES_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "country_code": "TEXT NOT NULL",
    "min_rating_percent": "REAL DEFAULT 90.0",
    "min_rating_count": "INTEGER DEFAULT 5",
    "max_handling_days": "INTEGER DEFAULT 6",
    "min_stock_qty": "INTEGER DEFAULT 0",
    "exclude_non_home_ship": "INTEGER DEFAULT 1",
    "exclude_future_offer": "INTEGER DEFAULT 1",
    "consider_points": "INTEGER DEFAULT 1",
    "exclude_non_buybox": "INTEGER DEFAULT 0",
    "created_at": "TEXT",
    "updated_at": "TEXT"
}

# --- ▼ shipping_config（仕入側：梱包補正設定） ---
SHIPPING_CONFIG_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "country_code": "TEXT NOT NULL",
    "padding_cm": "REAL",
    "pack_ratio": "REAL",
    "volumetric_divisor": "REAL",
    "updated_at": "TEXT"  
}

# --- ▼ pricing_master_rules（販売側：出品価格算出ルール） ---
PRICING_MASTER_RULES_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "country_code": "TEXT NOT NULL",

    # --- 競合フィルタ（販売側） ---
    "pricing_competitor_min_rating_percent": "REAL DEFAULT 0",   # 競合セラー評価率
    "pricing_competitor_min_rating_count": "INTEGER DEFAULT 0",  # 競合セラー評価数

    # --- 出品制限 ---
    "max_competitor_price_ratio": "REAL",   # 競合セラー価格乖離制限: 1.20 = 120%
    "max_listing_price_limit": "REAL",      # 絶対価格上限
    "discount_rate": "REAL",                # 競合価格からの割引率

    # --- 各種率補正設定 ---
    "min_profit_rate": "REAL",              # 最低利益率
    "max_profit_rate": "REAL",              # 最高利益率
    "amazon_fee_rate": "REAL",              # amazon手数料率
    "customs_duty_rate": "REAL",            # 関税率
    "gst_rate": "REAL DEFAULT 0",           # GST / VAT       
    "oversea_remittance_fee_rate": "REAL",  # 海外送金手数料率


    # --- 固定費 ---
    "shipping_outsource_cost": "REAL",      # 代行手数料+梱包資材料
    "extra_cost": "REAL",                   # その他経費    
    "fuel_surcharge_rate": "REAL",          # サーチャージ率 送料にのみ加算

    # --- その他 ---
    "default_handling_time": "INTEGER",     # ハンドリングタイム

    "created_at": "TEXT",
    "updated_at": "TEXT"
}

# --- ▼ ttl_state（TTL進行管理） ---
TTL_STATE_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "country_code": "TEXT NOT NULL",
    "last_id": "INTEGER",
}

# --- ▲ Pricing Setting設定　SECTION ▲ ---

# --- ▼  SECTION : shipping rates（送料テーブル） ---
SHIPPING_RATES_COLUMNS = {
    # "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "marketplace_id": "TEXT NOT NULL",
    "weight_from_g": "INTEGER NOT NULL",
    "weight_to_g": "INTEGER NOT NULL",
    "carrier_1_price": "INTEGER DEFAULT 0",
    "carrier_2_price": "INTEGER DEFAULT 0",
    "carrier_3_price": "INTEGER DEFAULT 0",

    "memo": "TEXT",    # 送料を特殊な設定をした場合などのメモ用

    "created_at": "TEXT",
    "updated_at": "TEXT"
}

# --- ▼ SECTION : user_login_account（ユーザーアカウント管理テーブル） ---
USER_LOGIN_ACCOUNTS_COLUMNS = {

    # "id":                   "INTEGER PRIMARY KEY AUTOINCREMENT",    # ユーザーID（全DB共通キー）
    "id":                   "SERIAL PRIMARY KEY",                   # ユーザーID（全DB共通キー）
    "email":                "TEXT NOT NULL",                        # ログイン用メール
    "password_hash":        "TEXT NOT NULL",                        # パスワードハッシュ
    "user_display_name":    "TEXT",                                 # 表示名
    "role":                 "TEXT NOT NULL DEFAULT 'user'",         # 権限区分
    "status":               "TEXT DEFAULT 'active'",                # ユーザー稼働状態（TTL判定参照 最上位ロック）
    "plan":                 "TEXT",                                 # 契約プラン
    "enabled_country_codes":"TEXT",                                 # 利用可能リージョン
    "home_country_code":    "TEXT",                                 # HOMEリージョン
    "last_login_at":        "TEXT",                                 # 最終ログイン日時
    "last_ip":              "TEXT",                                 # 最終ログインIP
    "two_factor_secret":    "TEXT",                                 # 二段階認証用
    "reset_token":          "TEXT",                                 # パスワードリセットトークン
    "reset_token_expire":   "TEXT",                                 # リセット有効期限
    "created_at":           "TEXT",                                 # 作成日時
    "updated_at":           "TEXT"                                  # 更新日時
}

# def get_existing_columns(conn, table_name):
#     cur = conn.cursor()
#     try:
#         cur.execute(f"PRAGMA table_info({table_name})")
#         return [row[1].lower() for row in cur.fetchall()]  # 小文字化して返す
#     except sqlite3.OperationalError:
#         return []

def get_existing_columns(conn, table_name):
    cur = conn.cursor()

    try:

        if DB_MODE == "sqlite":  # ここを修正
            cur.execute(f"PRAGMA table_info({table_name})")
            return [row[1].lower() for row in cur.fetchall()]

        elif DB_MODE == "postgres":  # ここを修正
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (table_name,))

            return [row[0].lower() for row in cur.fetchall()]

    except Exception:
        return []

def migrate_table(conn, table_name, schema_dict):
    existing = get_existing_columns(conn, table_name)
    cur = conn.cursor()

    if not existing:
        cols_def = ", ".join([f"{col} {dtype}" for col, dtype in schema_dict.items()])

        # # --- UNIQUE 制約 ---
        if table_name == "shipping_config":
            cols_def += ", UNIQUE(user_id, country_code)"

        if table_name == "offer_filter_rules":
            cols_def += ", UNIQUE(user_id, country_code)"

        if table_name == "pricing_master_rules":
            cols_def += ", UNIQUE(user_id, country_code)"


        cur.execute(f"CREATE TABLE {table_name} ({cols_def})")
        print(f"[CREATE] {table_name}")
        
    else:
        for col, dtype in schema_dict.items():
            if col.lower() not in existing:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {dtype}")
                print(f"[ALTER] {table_name}: add {col}")

    conn.commit()

def migrate_db(db_name):
    conn = get_conn(db_name)
    base = os.path.basename(db_name)

    if base.endswith("_listed_items.db"):
        migrate_table(conn, "listed_items", LISTED_ITEMS_COLUMNS)
    elif base.endswith("_blacklist_asin.db"):
        migrate_table(conn, "blacklist_asin", BLACKLIST_ASIN_COLUMNS)
    elif base.endswith("_blacklist_brand.db"):
        migrate_table(conn, "blacklist_brand", BLACKLIST_BRAND_COLUMNS)
    elif base.endswith("_marketplaces.db"):
        migrate_table(conn, "marketplaces", MARKETPLACES_COLUMNS)
    elif base.endswith("_account_master.db"):
        migrate_table(conn, "account_master", ACCOUNT_MASTER_COLUMNS)
    elif base.endswith("_pricing_settings.db"):
        migrate_table(conn, "shipping_config", SHIPPING_CONFIG_COLUMNS)
        migrate_table(conn, "offer_filter_rules", OFFER_FILTER_RULES_COLUMNS)
        migrate_table(conn, "pricing_master_rules", PRICING_MASTER_RULES_COLUMNS)
        migrate_table(conn, "ttl_state", TTL_STATE_COLUMNS) 
    elif base.endswith("_pricing_cache.db"):
        migrate_table(conn, "pricing_cache", PRICING_CACHE_COLUMNS)
    elif base.endswith("_marketplaces_master.db"):
        migrate_table(conn, "marketplaces_master", MARKETPLACES_MASTER_COLUMNS)
        migrate_table(conn, "amazon_retail_sellers", AMAZON_RETAIL_SELLERS_COLUMNS)
    elif base.endswith("_user_login_accounts.db"):
        migrate_table(conn, "user_login_accounts", USER_LOGIN_ACCOUNTS_COLUMNS)
    elif base.endswith("_catalog_cache.db"):
        migrate_table(conn, "catalog_cache", CATALOG_CACHE_COLUMNS)
    elif base.endswith("_api_usage.db"):
        migrate_table(conn, "api_usage_logs", API_USAGE_LOGS_COLUMNS)
    elif base.endswith("_shipping_rates.db"):
        migrate_table(conn, "shipping_rates", SHIPPING_RATES_COLUMNS)
    elif base.endswith("_bg_scan_settings.db"):
        migrate_table(conn, "bg_scan_settings", BG_SCAN_SETTINGS_COLUMNS)
    elif base.endswith("_fx.db"):
        migrate_table(conn, "fx_settings", FX_SETTINGS_COLUMNS)
        migrate_table(conn, "fx_rates", FX_RATES_COLUMNS) 
    # elif base.endswith("_brand_master.db"):
    #     migrate_table(conn, "brand_master", BRAND_MASTER_COLUMNS)  
    elif base.endswith("_brand_gate_result.db"):
        migrate_table(conn, "brand_gate_result", BRAND_GATE_RESULT_COLUMNS)
    elif base.endswith("_admin_settings.db"):
        migrate_table(conn, "admin_settings", ADMIN_SETTINGS_COLUMNS)                   


    conn.close()
    print(f"[OK] migrated: {db_name}")

def add_unique_indexes():  # UNIQUE制約
    # --- a_account_master.db ---
    conn = get_conn("a_account_master.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_account_user_country_code_unique "
        "ON account_master(user_id, country_code)"
    )
    # ② HOME は1ユーザー1件（←ここを追加）
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_one_home_per_user "
        "ON account_master(user_id) "
        "WHERE home_flag = 1"
    )
    conn.commit()
    conn.close()

    # --- a_marketplaces.db ---
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_market_user_country_code_unique "
        "ON marketplaces(user_id, country_code)"
    )
    conn.commit()
    conn.close()

    # --- a_user_login_accounts.db ---
    conn = get_conn("a_user_login_accounts.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_email_unique "
        "ON user_login_accounts(email)"
    )
    conn.commit()
    conn.close()

    # a_marketplaces.db から実在する country_code を取得（DB主導）
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_code FROM marketplaces")
    country_codes = [row[0].lower() for row in cur.fetchall()]
    conn.close()

    # その country_code だけ listed_items.db を更新
    for country_code in country_codes:
        db_name = f"a_{country_code}_listed_items.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ listed_items テーブルが存在するか確認
        if DB_MODE == "sqlite":  # ここを修正
            cur2.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='listed_items'
            """)

        elif DB_MODE == "postgres":
            cur2.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = 'listed_items'
            """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_listed_items_user_asin_region "
                "ON listed_items(user_id, asin, region_marketplace_id)"
            )

        conn2.commit()
        conn2.close()

    # --- a_shipping_rates.db ---
    conn = get_conn("a_shipping_rates.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shipping_rates_unique "
        "ON shipping_rates(user_id, marketplace_id, weight_from_g, weight_to_g)"
    )
    conn.commit()
    conn.close()

    # --- a_catalog_cache.db ---
    conn = get_conn("a_catalog_cache.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_catalog_cache_unique "
        "ON catalog_cache(asin, home_marketplace_id)"
    )
    conn.commit()
    conn.close()

    # --- a_pricing_cache.db ---
    conn = get_conn("a_pricing_cache.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_cache_unique "
        "ON pricing_cache(asin, home_marketplace_id)"
    )
    conn.commit()
    conn.close()

    # --- a_fx.db ---
    conn = get_conn("a_fx.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_fx_rates_unique "
        "ON fx_rates(base_currency, target_currency)"
    )
    conn.commit()
    conn.close()

    # --- blacklist_asin UNIQUE（country_code 正） ---
    for country_code in country_codes:
        db_name = f"a_{country_code}_blacklist_asin.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ blacklist_asin テーブル存在確認
        if DB_MODE == "sqlite": 
            cur2.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='blacklist_asin'
            """)

        elif DB_MODE == "postgres": 
            cur2.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = 'blacklist_asin'
            """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_blacklist_user_asin_unique "
                "ON blacklist_asin(user_id, asin)"
            )

        conn2.commit()
        conn2.close()

    # --- blacklist_brand UNIQUE（country_code 正） ---
    for country_code in country_codes:
        db_name = f"a_{country_code}_blacklist_brand.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ blacklist_brand テーブル存在確認
        if DB_MODE == "sqlite":
            cur2.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='blacklist_brand'
            """)

        elif DB_MODE == "postgres": 
            cur2.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = 'blacklist_brand'
            """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_blacklist_user_brand_unique "
                "ON blacklist_brand(user_id, brand)"
            )

        conn2.commit()
        conn2.close()        

    # --- a_brand_gate_result.db ---
    conn = get_conn("a_brand_gate_result.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_brand_gate_unique "
        "ON brand_gate_result(user_id, region_marketplace_id, brand)"
    )
    conn.commit()
    conn.close()



def add_indexes_listed_items():
    import sqlite3, os

    for file in os.listdir(DB_DIR):
        if file.endswith("_listed_items.db"):
            path = os.path.join(DB_DIR, file)
            conn = sqlite3.connect(path) # 一旦保留
            cur = conn.cursor()

            # ←ここに追加
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='listed_items'")
            if not cur.fetchone():
                conn.close()
                continue

            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_status ON listed_items(user_id, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_asin ON listed_items(asin)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sku ON listed_items(sku)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_home_brand ON listed_items(home_brand)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_region_brand ON listed_items(region_brand)")

            conn.commit()
            conn.close()

# --- メイン処理 ---
def main():
    os.makedirs(DB_DIR, exist_ok=True)

    # 固定DB（国に依存しない）
    base_dbs = [
        "a_marketplaces_master.db",
        "a_marketplaces.db",
        "a_account_master.db",
        "a_pricing_settings.db",
        "a_pricing_cache.db",
        "a_user_login_accounts.db",
        "a_catalog_cache.db",
        "a_api_usage.db",  
        "a_shipping_rates.db", 
        "a_bg_scan_settings.db",
        "a_fx.db",
        # "a_brand_master.db",  
        "a_brand_gate_result.db",
    ]

    for db_file in base_dbs:
        db_path = os.path.join(DB_DIR, db_file)
        if not os.path.exists(db_path):
            open(db_path, "w").close()
        migrate_db(db_file)

    # ② marketplaces から存在する country_code を取得
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_code FROM marketplaces")
    country_codes = [row[0].lower() for row in cur.fetchall()]
    conn.close()

    # ③ country_code ごとのDBを migrate（ここで listed_items テーブルが作られる）
    for country_code in country_codes:
        # listed_items（ここが重要）
        db_name = f"a_{country_code}_listed_items.db"
        db_path = os.path.join(DB_DIR, db_name)
        if not os.path.exists(db_path):
            open(db_path, "w").close()
        migrate_db(db_name)

        # blacklist_asin
        db_name = f"a_{country_code}_blacklist_asin.db"
        db_path = os.path.join(DB_DIR, "blacklist", db_name)
        if not os.path.exists(db_path):
            open(db_path, "w").close()
        migrate_db(db_name)

        # blacklist_brand
        db_name = f"a_{country_code}_blacklist_brand.db"
        db_path = os.path.join(DB_DIR, "blacklist", db_name)
        if not os.path.exists(db_path):
            open(db_path, "w").close()
        migrate_db(db_name)
        
    # ④ 全テーブル作成が終わってから UNIQUE INDEX を付与
    add_unique_indexes()

    add_indexes_listed_items() 

    ensure_fx_settings_initialized()

# --- ▼ FX 初期設定挿入 ---
def ensure_fx_settings_initialized():
    conn = get_conn("a_fx.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM fx_settings")
    count = cur.fetchone()[0]

    if count == 0:
        cur.execute("""
            INSERT INTO fx_settings (provider_name, update_interval_hours, last_updated_at)
            VALUES (%s, %s, %s)
        """, ("exchangerate_host", 24, None))         
        print("[INIT] fx_settings inserted")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()

# --- API shipping rates（送料マスタ） ---
def migrate_shipping_rates():
    conn = get_conn("a_shipping_rates.db")
    migrate_table(conn, "shipping_rates", SHIPPING_RATES_COLUMNS)
    conn.close()
    print("[OK] migrated: a_shipping_rates.db")




