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

from amazon.db import get_conn

# DBフォルダ
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db")


def get_conn_old(db_name: str): # 未使用関数 削除保留
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

    conn = sqlite3.connect(db_path, timeout=30)  # 未使用コード（get_conn_old） / DB移行対象外
    conn.row_factory = sqlite3.Row

    return conn

# カラム名定義
ACCOUNT_MASTER_COLUMNS = {
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
    "scan_limit": "INTEGER NOT NULL",         # FIRST用：1巡回あたりの最大処理件数
    "updated_at": "TEXT",                     

        # --- ▼ TTL 項目別 上限件数（新規追加） ▼ ---
    "ttl_limit_home_pricing": "INTEGER",      # TTL：HOME価格情報の上限件数
    "ttl_limit_region_pricing": "INTEGER",    # TTL：REGION価格情報の上限件数
    "ttl_limit_home_catalog": "INTEGER",      # TTL：HOME商品情報の上限件数
    "ttl_limit_region_catalog": "INTEGER",    # TTL：REGION商品情報の上限件数
    "ttl_sleep_sec": "REAL",                  # TTL SleepTIME（旧・共通値。後方互換のため残置）

        # --- ▼ API種別ごとのsleep秒数（新規追加。旧ttl_sleep_secから分割） ▼ ---
    "ttl_sleep_sec_catalog": "REAL",           # TTL：HOME/REGION catalog専用sleep
    "ttl_sleep_sec_pricing": "REAL",           # TTL：HOME/REGION pricing専用sleep
    "ttl_cycle_sleep_sec": "REAL",             # TTL：ttl_loop.py サイクル間sleep（旧ハードコード）
    "first_asin_sleep_sec": "REAL",            # FIRST：ASIN間の追加sleep（旧ハードコード）
    "api_block_sec": "REAL",                   # 429検知後のブロック秒数（旧ハードコード）

        # --- ▼ REGIONCHECK専用の巡回設定（新規追加。旧interval_min/scan_limitはfirst_loop専用に） ▼ ---
    "regioncheck_interval_min": "REAL",        # REGIONCHECK：巡回間隔（分）。未設定時はinterval_minを流用
    "regioncheck_scan_limit": "INTEGER",       # REGIONCHECK：1巡回あたりの最大処理件数。未設定時はscan_limitを流用
}


BLACKLIST_ASIN_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "asin": "TEXT NOT NULL",
    "note": "TEXT",
    "created_at": "TEXT"
}

BLACKLIST_BRAND_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "brand": "TEXT NOT NULL",
    "note": "TEXT",
    "created_at": "TEXT"
}

# --- ▼ 他社ツール出品済みASIN（重複出品防止・一時運用） ---
EXTERNAL_LISTED_ASIN_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "asin": "TEXT NOT NULL",
    "note": "TEXT",
    "created_at": "TEXT"
}

# --- ▼ 低閲覧数ASIN削除候補（Business Reportセッション数分析） ---
REPORT_CANDIDATE_ASIN_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "asin": "TEXT NOT NULL",
    "sessions": "INTEGER",
    "period_days": "INTEGER",
    "checked_at": "TEXT"
}

# # --- BlackList 管理者用カラム ---
# BLACKLIST_BRAND_COLUMNS = {
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

# --- ▼ SECTION : 429ブロック状態（複数プロセス共有用） ▼ ---
API_BLOCK_STATE_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "endpoint": "TEXT NOT NULL",
    "blocked_until": "TEXT NOT NULL",
}

# --- ▼ SECTION：429発生ログ（Dashboard表示用・新規追加） ---
API_429_EVENTS_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "endpoint": "TEXT NOT NULL",
    "created_at": "TEXT NOT NULL",
}

# --- ▼ SECTION ： Bland Gate用 ▼ ---
BRAND_GATE_RESULT_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER",
    "region_marketplace_id": "TEXT",
    "brand": "TEXT NOT NULL",
    "asin": "TEXT",            # brandが実質空("-"/空欄/UNKNOWN)の商品はASIN単位でキャッシュする
    "status": "TEXT",          # OK / NG
    "reason": "TEXT",          # エラー内容
    "updated_at": "TEXT"
}

CATALOG_CACHE_COLUMNS = {
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

    # --- 在庫0 手動一時停止用 ---
    "override_stock_zero": "INTEGER",               # 在庫0 手動出品停止（ON中はTTL対象外・出品を取り下げたまま維持）

    # --- 在庫数情報 ---

    # --- Pricing情報 ---
    # --- 価格・関税（編集UI用） ---
    "home_price": "REAL",                           # HOME仕入価格
    "region_price": "REAL",                         # REGION価格
    "raw_min_price": "REAL",                        # 最安競合価格
    "override_price": "REAL",                       # 出品価格 手動変更用 
    "final_price": "REAL",                          # 最終出品価格
    "profit_rate": "REAL",                          # 利益率
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
    "inactive_reason": "TEXT DEFAULT ''",           # INACTIVE理由

    "created_at": "TEXT",                           # 登録TIME
    "updated_at": "TEXT",                           # 更新TIME

        # --- TTL専用日時 ---
    "h_catalog_ttl_at": "TEXT",                     # TTL更新TIME home catalog
    "r_catalog_ttl_at": "TEXT",                     # TTL更新TIME region catalog

    "h_pricing_ttl_at": "TEXT",                     # TTL更新TIME home Pricing
    "r_pricing_ttl_at": "TEXT",                     # TTL更新TIME region Pricing
}

# # 未使用 --- ▼ listed brand master（出品実績ブランド） ---
# LISTED_BRAND_MASTER_COLUMNS = {
#     "id": "SERIAL PRIMARY KEY",
#     "user_id": "INTEGER NOT NULL",
#     "country_code": "TEXT NOT NULL",
#     "brand": "TEXT",
#     "manufacturer": "TEXT",
#     "created_at": "TEXT"
# }

# LWA client_id/client_secret管理DB ---
LWA_CREDENTIALS_LOG_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "client_id": "TEXT NOT NULL",
    "client_secret": "TEXT NOT NULL",
    "updated_at": "TEXT"
}

MARKETPLACES_COLUMNS = {
    # --- a_account_master.dbからコピー 
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
    "id": "SERIAL PRIMARY KEY",
    "country_code": "TEXT",
    "seller_id": "TEXT UNIQUE",
    "note": "TEXT"
}

MARKETPLACES_MASTER_COLUMNS = {
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

    # order-idの先頭桁（カンマ区切り。例: AU="2,5"）→ このマーケットの注文かどうかを判別するために使用（ORBIT）
    "order_id_prefixes": "TEXT",

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

# --- ▼ lethal_weapon_preset（Pre-Listing：絞込み条件の規定登録） ---
LETHAL_WEAPON_PRESET_COLUMNS = {
    "user_id": "INTEGER NOT NULL",
    "filters_json": "TEXT",
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
    "max_longest_side_cm": "REAL",         # EMS上限：最長辺（配送先国別）
    "max_length_plus_girth_cm": "REAL",    # EMS上限：最長辺＋胴回り合計（配送先国別）
    "updated_at": "TEXT"
}

# --- ▼ shipping_override_master（別途送料誤判定 セラー除外設定） ---
SHIPPING_OVERRIDE_MASTER_COLUMNS = {
    "marketplace_id": "TEXT NOT NULL",
    "seller_id": "TEXT NOT NULL",
    "seller_name": "TEXT",    
    "shipping_amount": "REAL",
    "remarks": "TEXT",    
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

# --- ▼ ttl_cycle_log（TTL 1サイクルごとの稼働記録：ダッシュボード表示用） ---
# leg は現状 'home_pricing' のみ書き込むが、将来 region_pricing / home_catalog /
# region_catalog へ拡張できるよう汎用列にしてある。
TTL_CYCLE_LOG_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "leg": "TEXT NOT NULL",              # 'home_pricing' 等
    "started_at": "TEXT NOT NULL",       # UTC ISO
    "finished_at": "TEXT",              # UTC ISO
    "backlog_count": "INTEGER",         # サイクル開始時点の期限切れ総数（LIMIT前）
    "target_count": "INTEGER",          # LIMIT で実際に取得した件数
    "dispatched_count": "INTEGER",      # 実際に更新関数を呼んだ件数
    "error_count": "INTEGER",           # 例外が出た件数
    "oldest_before": "TEXT",            # サイクル前 MIN(h_pricing_ttl_at)
    "oldest_after": "TEXT",             # サイクル後 MIN(h_pricing_ttl_at)
}

# --- ▲ Pricing Setting設定　SECTION ▲ ---

# --- ▼  SECTION : shipping rates（送料テーブル） ---
SHIPPING_RATES_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "marketplace_id": "TEXT NOT NULL",
    "weight_from_g": "INTEGER NOT NULL",
    "weight_to_g": "INTEGER NOT NULL",
    "carrier_1_price": "INTEGER DEFAULT 0",
    "carrier_2_price": "INTEGER DEFAULT 0",
    "carrier_3_price": "INTEGER DEFAULT 0",
    "fixed_shipping_price": "INTEGER",    # 固定送料
    
    "memo": "TEXT",    # 送料を特殊な設定をした場合などのメモ用

    "created_at": "TEXT",
    "updated_at": "TEXT"
}

# --- ▼ SECTION : carrier_remote_area_codes（DHL/FedEx 遠隔地郵便番号マスタ） ---
CARRIER_REMOTE_AREA_COLUMNS = {
    "id":           "SERIAL PRIMARY KEY",
    "carrier":      "TEXT NOT NULL",        # 'DHL' / 'FEDEX'
    "country_code": "TEXT NOT NULL",        # 2文字ISOコード（AU/CA/US等・手入力）
    "postal_from":  "TEXT NOT NULL",
    "postal_to":    "TEXT NOT NULL",
    "imported_at":  "TEXT",                 # 取り込み日（YYYY-MM-DD）
    "created_at":   "TEXT",
}

# --- ▼ SECTION : ORBIT（注文管理）注文明細テーブル ---
ORBIT_ORDERS_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",

    # --- Amazon注文レポート由来（CSVインポートでそのまま取込） ---
    "order_id": "TEXT",
    "order_item_id": "TEXT NOT NULL",       # 明細単位で一意・重複判定キー
    "purchase_date": "TEXT",
    "payments_date": "TEXT",
    "reporting_date": "TEXT",
    "promise_date": "TEXT",
    "days_past_promise": "TEXT",
    "buyer_email": "TEXT",
    "buyer_name": "TEXT",
    "buyer_phone_number": "TEXT",
    "sku": "TEXT",
    "product_name": "TEXT",
    "quantity_purchased": "INTEGER",
    "quantity_shipped": "INTEGER",
    "quantity_to_ship": "INTEGER",
    "ship_service_level": "TEXT",
    "recipient_name": "TEXT",
    "ship_address_1": "TEXT",
    "ship_address_2": "TEXT",
    "ship_address_3": "TEXT",
    "ship_city": "TEXT",
    "ship_state": "TEXT",
    "ship_postal_code": "TEXT",
    "ship_country": "TEXT",
    "is_business_order": "TEXT",
    "purchase_order_number": "TEXT",
    "price_designation": "TEXT",
    "is_transparency": "TEXT",
    "verge_of_cancellation": "TEXT",
    "verge_of_late_shipment": "TEXT",
    "signature_confirmation_recommended": "TEXT",
    "buyer_identification_number": "TEXT",
    "buyer_identification_type": "TEXT",
    "order_currency": "TEXT",              # 注文レポートのcurrency列（決済通貨。マーケットにより変動）
    "item_price": "REAL",                  # 注文レポートのitem-price列（販売価格。出荷前でも取得可能）
    "shipping_price": "REAL",              # 注文レポートのshipping-price列（買い手負担送料）

    # --- ORBIT側で手入力（再インポートで上書きされない） ---
    "jan_code": "TEXT",
    "purchase_price": "REAL",              # 仕入れ価格

    # --- 出荷前の概算利益用（SP-API手数料見積り。取得ボタンで都度キャッシュ） ---
    "fee_estimate_amount": "REAL",
    "fee_estimate_currency": "TEXT",
    "fee_estimate_fetched_at": "TEXT",

    # --- 発送代行会社シートへの貼り付け前チェック用の手修正（再インポートで上書きされない）。
    #     セットされていればAmazon注文レポート由来の値より優先して表示・CSV出力する。 ---
    "product_name_override": "TEXT",       # 70字制限・パイプ文字"|"禁止のため手修正（自動修正はしない）
    "recipient_name_override": "TEXT",     # DHL/Fedex用のフルネーム化（自動修正はしない）
    "ship_address_1_override": "TEXT",     # 40字制限の振り分け調整（自動修正はしない）
    "ship_address_2_override": "TEXT",
    "ship_address_3_override": "TEXT",
    "buyer_phone_number_override": "TEXT", # 国番号自動除去で直り切らない場合の手修正
    "buyer_phone_extension_override": "TEXT", # 内線番号(US "ext. 12345"表記)自動分離で直り切らない場合の手修正
    "ship_state_override": "TEXT",         # 州の正式表記自動変換で直り切らない場合の手修正

    # --- 寸法・重量の手入力（listed_items・catalog_cache 両方に無い場合の最終手段） ---
    "manual_length_cm": "REAL",
    "manual_width_cm": "REAL",
    "manual_height_cm": "REAL",
    "manual_weight_kg": "REAL",

    # --- 発送代行会社とのやり取り用（手入力） ---
    "agent_serial_no": "INTEGER",          # 代行会社の管理連番（Nから始まる連番。先頭行だけ入力すれば以降は自動採番）
    "request_date": "TEXT",                # 依頼日
    "shipping_type": "TEXT",               # 発送種別（暫定：手入力）
    "tracking_number": "TEXT",             # 発送会社トラッキング番号（暫定：手入力。将来自動反映を想定）
    "remarks": "TEXT",                     # 備考1＝通常の通知内容（発送代行会社への連絡事項）
    "remarks_2": "TEXT",                   # 備考2＝仕入商品の追跡番号＋到着予定日（運送会社選択＋番号。v1はフリーテキスト）
    "remarks_3": "TEXT",                   # 備考3＝他国出荷時のGST/BAT番号等（Amazon徴収済みの場合に発送時通知）
    # ZSSS_RAW書き出し時は remarks/remarks_2/remarks_3 を空でないものだけ半角スペースで連結して1列(remarks)にする

    # --- 仕入れ管理（手入力） ---
    "supplier": "TEXT",                    # 仕入先（Amazon/楽天/Yahoo!など）
    "supplier_order_number": "TEXT",       # 仕入先での注文番号
    "supplier_shop_name": "TEXT",          # モール内のショップ名（楽天/Yahoo!等）
    "procurement_date": "TEXT",            # 仕入日（実際に仕入先へ発注した日）
    "arrival_date": "TEXT",                # 到着予定日
    "procurement_credit_card": "TEXT",     # 仕入れに使ったクレジットカード（orbit_credit_cards.card_name を選択。締め支払い集計は後日）
    "shipped_completed": "INTEGER",        # 出荷完了フラグ（仕入れ管理のボタンで手動ON/OFF。押し間違えても解除可能）

    # --- 発注管理タブのチェック欄（手入力。ZSSS_RAW・代行会社へは連携しない） ---
    "invoice_saved": "INTEGER",            # インボイス（領収書）DL・保管済みフラグ。トグル式（再押しで解除）
    "points": "REAL",                      # 獲得ポイント（目安の数値を入力するだけ。計算・連携なし）
    "purchased": "INTEGER",                # 仕入確認フラグ。トグル式（日付非連動、キャンセル時に解除可能）。未仕入れ行の視認用
    # ※「出荷通知したか」は shipped_completed（既存）で兼ねる（発注管理タブでは「出荷通知」ラベルで表示）

    # --- 発送代行への通知状況 ---
    "notified_at": "TEXT",

    # --- 発送代行会社からの読み戻し（依頼書シートJ〜U列・緑項目。Google Sheets API経由で取込） ---
    "agent_tracking_number": "TEXT",       # G列 海外向けトラッキング
    "agent_thankyou_letter": "TEXT",       # J列「出荷に関する通知」＝代行会社→セラーへの連絡内容（列名は互換のため据え置き）
    "agent_option_content": "TEXT",        # K列 オプション内容
    "agent_option_fee": "TEXT",            # L列 オプション料計
    "agent_non_deliverable_weight": "TEXT",# M列 配送不可重量
    "agent_shipping_weight": "TEXT",       # N列 発送重量
    "agent_weight_recorded_date": "TEXT",  # O列 発送重量記入日（日付が入れば出荷済み）
    "agent_confirmed_weight": "TEXT",      # P列 確定重量
    "agent_deadline": "TEXT",              # Q列 期限
    "agent_status": "TEXT",                # R列 状況
    "agent_shipping_fee": "TEXT",          # S列 送料
    "agent_shipping_fee_total": "TEXT",    # T列 送料合計
    "agent_delivery_area": "TEXT",         # U列 配送エリア
    "agent_synced_at": "TEXT",             # 最終取込日時

    "created_at": "TEXT",
    "updated_at": "TEXT",
}

# --- ▼ SECTION : 仕入れ履歴（ORBIT: 買い手履歴へのアーカイブ時に、orbit_ordersの行を退避する専用
#     テーブル。orbit_buyer_historyは住所チェック用の名簿に留める設計のため、仕入額・仕入先・
#     トラッキング番号・代行会社とのやり取り等ZSSS側の全データはこちらに残す
#     （領収書発行・経理・返品対応時に仕入額等を参照する用途）。列構成はorbit_ordersと同一。 ---
ORBIT_PROCUREMENT_HISTORY_COLUMNS = dict(ORBIT_ORDERS_COLUMNS)
ORBIT_PROCUREMENT_HISTORY_COLUMNS["archived_at"] = "TEXT"  # orbit_ordersからの退避日時

# --- ▼ SECTION : クレジットカードマスタ（ORBIT: 仕入れ利用カードの選択肢＋締め日/支払日） ---
#     発注管理「仕入れ情報 → 利用クレカ」のプルダウン候補になる。締め支払いの集計は後日追加予定で、
#     締め日・支払日は「月末」「翌月27日」等の表記ゆれを許すフリーテキストで持つ（集計搭載時にパースする想定）。
ORBIT_CREDIT_CARDS_COLUMNS = {
    "id":          "SERIAL PRIMARY KEY",
    "user_id":     "INTEGER NOT NULL",
    "card_name":   "TEXT NOT NULL",         # プルダウンに出す名前（例: JCB / Amex）
    "closing_day": "TEXT",                  # 締め日（例: 月末 / 15日 / 20日）
    "payment_day": "TEXT",                  # 支払日（例: 翌月10日 / 翌月27日）
    "sort_order":  "INTEGER DEFAULT 0",     # プルダウン・一覧の表示順
    "created_at":  "TEXT",
    "updated_at":  "TEXT",
}

# --- ▼ SECTION : 決済トランザクション明細（ORBIT: 実利益計算用。セラーセントラル「支払い」→
#     「トランザクション」画面からのCSVダウンロード。1行=1注文の集計済みデータで、
#     「合計」列に既にAmazon手数料等を差し引いた後の入金額が入っている） ---
# 返金・後日調整などで同じorder-idに複数回データが来ても、上書きせず全部残せば読み取り時のSUMで
# 正しく合算できるようにする。
ORBIT_SETTLEMENT_LINES_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "order_id": "TEXT NOT NULL",
    "transaction_date": "TEXT",         # 日付
    "transaction_status": "TEXT",       # トランザクションステータス（留保中／支払い実行済み等）
    "transaction_type": "TEXT",         # トランザクションの種類
    "product_price": "REAL",            # 商品価格合計
    "promotion_discount": "REAL",       # プロモーション割引合計
    "amazon_fee": "REAL",               # Amazon手数料
    "other_amount": "REAL",             # その他
    "total_amount": "REAL",             # 合計（＝入金額。手数料等差引後）
    "currency": "TEXT",                 # 「合計 (CAD)」等ヘッダーから取得
    "imported_at": "TEXT",
}

# --- ▼ SECTION : 買い手購入履歴アーカイブ（ORBIT: 決済確定＋出荷完了の注文をorbit_ordersから退避）。
#     Amazon注文レポートの生データ（IMPORT_COLUMNS）＋N番（agent_serial_no）だけを保持する。
#     過去の購入価格・送料・利益等ZSSS側の計算結果は持たない＝「この住所は過去に買ったことがあるか」
#     だけをチェックするための台帳。過去のスプレッドシート「FBMバイヤー履歴」のCSVインポート分
#     （archived_at=NULL, source='sheet_import'）と、今後のアーカイブ分（source='archived'）の
#     両方をここに集約する。 ---
ORBIT_BUYER_HISTORY_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "order_id": "TEXT",
    "order_item_id": "TEXT NOT NULL",
    "purchase_date": "TEXT",
    "payments_date": "TEXT",
    "reporting_date": "TEXT",
    "promise_date": "TEXT",
    "days_past_promise": "TEXT",
    "buyer_email": "TEXT",
    "buyer_name": "TEXT",
    "buyer_phone_number": "TEXT",
    "sku": "TEXT",
    "product_name": "TEXT",
    "quantity_purchased": "INTEGER",
    "quantity_shipped": "INTEGER",
    "quantity_to_ship": "INTEGER",
    "ship_service_level": "TEXT",
    "recipient_name": "TEXT",
    "ship_address_1": "TEXT",
    "ship_address_2": "TEXT",
    "ship_address_3": "TEXT",
    "ship_city": "TEXT",
    "ship_state": "TEXT",
    "ship_postal_code": "TEXT",
    "ship_country": "TEXT",
    "is_business_order": "TEXT",
    "purchase_order_number": "TEXT",
    "price_designation": "TEXT",
    "is_transparency": "TEXT",
    "verge_of_cancellation": "TEXT",
    "verge_of_late_shipment": "TEXT",
    "signature_confirmation_recommended": "TEXT",
    "buyer_identification_number": "TEXT",
    "buyer_identification_type": "TEXT",
    "order_currency": "TEXT",
    "item_price": "REAL",
    "shipping_price": "REAL",

    "agent_serial_no": "INTEGER",  # N番（発送代行会社の管理連番）

    "asin": "TEXT",          # SKUに埋め込まれたASINをインポート/アーカイブ時に解決して保存（ASINカウント用）

    "buyer_key": "TEXT",      # 住所正規化キー（郵便番号+住所1）。買い手照合用
    "archived_at": "TEXT",    # orbit_ordersからの移動日時（sheet_importはNULL。ただしagent_serial_noは
                               # スプレッドシート側の"N-No"列があればsheet_importでも取り込まれる）
    "source": "TEXT",         # 'archived' | 'sheet_import'
    "created_at": "TEXT",
}

# --- ▼ SECTION : 返品・セキュリティメモ（ORBIT: 買い手＝住所単位で返品・キャンセル理由等を記録。
#     Amazonにバイヤーブラックリスト機能が無いための自衛策）。注文がorbit_orders/orbit_buyer_history
#     どちらにアーカイブ済みでも、buyer_keyさえ分かれば追記できる。 ---
ORBIT_BUYER_SECURITY_NOTES_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "buyer_key": "TEXT NOT NULL",
    "recipient_name": "TEXT",      # 表示用スナップショット
    "ship_address_1": "TEXT",      # 表示用スナップショット
    "ship_postal_code": "TEXT",    # 表示用スナップショット
    "order_id": "TEXT",
    "order_item_id": "TEXT",
    "note": "TEXT NOT NULL",
    "created_at": "TEXT",
}

# --- ▼ SECTION : Google OAuthトークン（ORBIT: 発送代行会社シートの読み戻し用） ---
GOOGLE_OAUTH_TOKENS_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "access_token": "TEXT",
    "refresh_token": "TEXT",
    "expires_at": "TEXT",          # access_tokenの有効期限（ISO日時）
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

# --- ▼ SECTION : 依頼書スプレッドシート設定（ORBIT: URLが変わっても画面から変更できるように） ---
ORBIT_DISPATCH_SHEET_SETTINGS_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "user_id": "INTEGER NOT NULL",
    "spreadsheet_url": "TEXT",     # 依頼書スプレッドシートのURL（ブラウザからそのまま貼り付け）
    "sheet_name": "TEXT",          # シート名（例: 【発送確認用】依頼書）
    # ORBIT → 自分の管理スプレッドシートへの書き出し先（ZSSS_RAWタブ）。読み戻し用(spreadsheet_url/sheet_name)とは別。
    "raw_spreadsheet_url": "TEXT", # 書き出し先スプレッドシートのURL（代行会社とIMPORTRANGE連携済みの自分のシート）
    "raw_sheet_name": "TEXT",      # 書き出し先タブ名（既定: ZSSS_RAW）
    # ZSSS_RAWタブの内容(A〜BEの57列)を、代行会社シートの中のタブへ直接ミラー書き込みする先。
    # IMPORTRANGE（頻繁に「内部エラー」になる）を廃止して置き換えるための設定。空なら書き込まない。
    "raw_mirror_spreadsheet_url": "TEXT",  # ミラー先スプレッドシートのURL（代行会社ファイル）
    "raw_mirror_sheet_name": "TEXT",       # そのタブ名（例: ujihara2）。毎回まるごと上書き
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

# --- ▼ SECTION : user_login_account（ユーザーアカウント管理テーブル） ---
USER_LOGIN_ACCOUNTS_COLUMNS = {
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

def get_existing_columns(conn, table_name):
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))

        return [row["column_name"].lower() for row in cur.fetchall()]

    except Exception:
        return []

def migrate_table(conn, table_name, schema_dict):
    existing = get_existing_columns(conn, table_name)
    cur = conn.cursor()

    if not existing:
        cols_def = ", ".join([f"{col} {dtype}" for col, dtype in schema_dict.items()])

        cur.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({cols_def})")
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
    elif base.endswith("_external_listed_asin.db"):
        migrate_table(conn, "external_listed_asin", EXTERNAL_LISTED_ASIN_COLUMNS)
    elif base.endswith("_report_candidate_asin.db"):
        migrate_table(conn, "report_candidate_asin", REPORT_CANDIDATE_ASIN_COLUMNS)
    elif base.endswith("_marketplaces.db"):
        migrate_table(conn, "marketplaces", MARKETPLACES_COLUMNS)
    elif base.endswith("_account_master.db"):
        migrate_table(conn, "account_master", ACCOUNT_MASTER_COLUMNS)
    elif base.endswith("_pricing_settings.db"):
        migrate_table(conn, "shipping_config", SHIPPING_CONFIG_COLUMNS)
        migrate_table(conn, "offer_filter_rules", OFFER_FILTER_RULES_COLUMNS)
        migrate_table(conn, "pricing_master_rules", PRICING_MASTER_RULES_COLUMNS)
        migrate_table(conn, "ttl_state", TTL_STATE_COLUMNS)
        migrate_table(conn, "ttl_cycle_log", TTL_CYCLE_LOG_COLUMNS)
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
    elif base.endswith("_carrier_remote_area.db"):
        migrate_table(conn, "carrier_remote_area_codes", CARRIER_REMOTE_AREA_COLUMNS)
        cur = conn.cursor()
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_carrier_remote_area_lookup "
            "ON carrier_remote_area_codes(carrier, country_code)"
        )
        conn.commit()
    # elif base.endswith("_brand_master.db"):
    #     migrate_table(conn, "brand_master", BRAND_MASTER_COLUMNS)  
    elif base.endswith("_brand_gate_result.db"):
        migrate_table(conn, "brand_gate_result", BRAND_GATE_RESULT_COLUMNS)
    elif base.endswith("_admin_settings.db"):
        migrate_table(conn, "admin_settings", ADMIN_SETTINGS_COLUMNS)
    elif base.endswith("_api_block_state.db"):
        migrate_table(conn, "api_block_state", API_BLOCK_STATE_COLUMNS)
    elif base.endswith("_api_429_events.db"):
        migrate_table(conn, "api_429_events", API_429_EVENTS_COLUMNS)
    elif base.endswith("_shipping_override_master.db"):
        migrate_table(conn, "shipping_override_master", SHIPPING_OVERRIDE_MASTER_COLUMNS)    
    elif base.endswith("_lwa_credentials_log.db"):
        migrate_table(conn, "lwa_credentials_log", LWA_CREDENTIALS_LOG_COLUMNS)
    elif base.endswith("_lethal_weapon_preset.db"):
        migrate_table(conn, "lethal_weapon_preset", LETHAL_WEAPON_PRESET_COLUMNS)
    elif base.endswith("_orbit_orders.db"):
        migrate_table(conn, "orbit_orders", ORBIT_ORDERS_COLUMNS)
    elif base.endswith("_orbit_settlement_lines.db"):
        migrate_table(conn, "orbit_settlement_lines", ORBIT_SETTLEMENT_LINES_COLUMNS)
    elif base.endswith("_orbit_buyer_history.db"):
        migrate_table(conn, "orbit_buyer_history", ORBIT_BUYER_HISTORY_COLUMNS)
    elif base.endswith("_orbit_credit_cards.db"):
        migrate_table(conn, "orbit_credit_cards", ORBIT_CREDIT_CARDS_COLUMNS)
    elif base.endswith("_orbit_procurement_history.db"):
        migrate_table(conn, "orbit_procurement_history", ORBIT_PROCUREMENT_HISTORY_COLUMNS)
    elif base.endswith("_orbit_buyer_security_notes.db"):
        migrate_table(conn, "orbit_buyer_security_notes", ORBIT_BUYER_SECURITY_NOTES_COLUMNS)
    elif base.endswith("_google_oauth_tokens.db"):
        migrate_table(conn, "google_oauth_tokens", GOOGLE_OAUTH_TOKENS_COLUMNS)
    elif base.endswith("_orbit_dispatch_sheet_settings.db"):
        migrate_table(conn, "orbit_dispatch_sheet_settings", ORBIT_DISPATCH_SHEET_SETTINGS_COLUMNS)


    conn.close()
    # print(f"[OK] migrated: {db_name}")

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
    country_codes = [row["country_code"].lower() for row in cur.fetchall()]
    conn.close()

    # その country_code だけ listed_items.db を更新
    for country_code in country_codes:
        db_name = f"a_{country_code}_listed_items.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ listed_items テーブルが存在するか確認
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

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_h_catalog_ttl_at "
                "ON listed_items(h_catalog_ttl_at)"
            )

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_r_catalog_ttl_at "
                "ON listed_items(r_catalog_ttl_at)"
            )

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_h_pricing_ttl_at "
                "ON listed_items(h_pricing_ttl_at)"
            )

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_r_pricing_ttl_at "
                "ON listed_items(r_pricing_ttl_at)"
            )

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_listed_items_user_market_status "
                "ON listed_items(user_id, region_marketplace_id, status)"
            )

            # ★追加: 一覧取得のメインクエリ（_get_listing_by_status / search_listing）は
            #        WHERE LOWER(li.status) = %s で比較しているため、上のプレーンな
            #        status列インデックスは使われず、件数が多いと毎回シーケンシャルスキャンに
            #        なっていた。LOWER(status)に対応したインデックスを別途用意する。
            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_listed_items_user_market_status_lower "
                "ON listed_items(user_id, region_marketplace_id, (LOWER(status)))"
            )

            cur2.execute(
                "CREATE INDEX IF NOT EXISTS idx_listed_items_region_brand_lower "
                "ON listed_items(region_marketplace_id, status, (LOWER(TRIM(region_brand))))"
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

    # --- a_orbit_orders.db ---
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbit_orders_unique "
        "ON orbit_orders(user_id, order_item_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_orders_sku "
        "ON orbit_orders(user_id, sku)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_settlement_lines.db ---
    conn = get_conn("a_orbit_settlement_lines.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbit_settlement_lines_unique "
        "ON orbit_settlement_lines(user_id, order_id, transaction_date, total_amount)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_settlement_lines_order "
        "ON orbit_settlement_lines(user_id, order_id)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_buyer_history.db ---
    conn = get_conn("a_orbit_buyer_history.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbit_buyer_history_unique "
        "ON orbit_buyer_history(user_id, order_item_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_buyer_history_buyer_key "
        "ON orbit_buyer_history(user_id, buyer_key)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_buyer_history_asin "
        "ON orbit_buyer_history(user_id, asin)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_procurement_history.db ---
    conn = get_conn("a_orbit_procurement_history.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbit_procurement_history_unique "
        "ON orbit_procurement_history(user_id, order_item_id)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_buyer_security_notes.db ---
    conn = get_conn("a_orbit_buyer_security_notes.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_buyer_security_notes_buyer_key "
        "ON orbit_buyer_security_notes(user_id, buyer_key)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_credit_cards.db ---
    conn = get_conn("a_orbit_credit_cards.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_orbit_credit_cards_user "
        "ON orbit_credit_cards(user_id, sort_order, id)"
    )
    conn.commit()
    conn.close()

    # --- a_google_oauth_tokens.db ---
    conn = get_conn("a_google_oauth_tokens.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_google_oauth_tokens_unique "
        "ON google_oauth_tokens(user_id)"
    )
    conn.commit()
    conn.close()

    # --- a_orbit_dispatch_sheet_settings.db ---
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orbit_dispatch_sheet_settings_unique "
        "ON orbit_dispatch_sheet_settings(user_id)"
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
    # --- listing一覧のWHERE region_marketplace_id=%sが全表スキャンになっていたため追加 ---
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_cache_region_mp "
        "ON catalog_cache(region_marketplace_id)"
    )
    conn.commit()
    conn.close()

    # --- a_pricing_cache.db ---
    # ★修正: (asin, home_marketplace_id) だけだと同一ASINを複数REGIONへ
    #        出品した場合に1行しか持てず、REGION側のデータが上書きされて
    #        消える不具合があったため、region_marketplace_id を複合キーに追加
    conn = get_conn("a_pricing_cache.db")
    cur = conn.cursor()
    cur.execute(
        "DROP INDEX IF EXISTS idx_pricing_cache_unique"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_cache_unique_v2 "
        "ON pricing_cache(asin, home_marketplace_id, region_marketplace_id)"
    )
    # --- 複合UNIQUEはregion_marketplace_idが末尾のため単独WHERE検索に使えない → 単独索引を追加 ---
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_pricing_cache_region_mp "
        "ON pricing_cache(region_marketplace_id)"
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
        cur2.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'blacklist_asin'
        """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_blacklist_user_asin_unique "
                "ON blacklist_asin(user_id, region_marketplace_id, asin)"
            )

        conn2.commit()
        conn2.close()

    # --- blacklist_brand UNIQUE（country_code 正） ---
    for country_code in country_codes:
        db_name = f"a_{country_code}_blacklist_brand.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ blacklist_brand テーブル存在確認
        cur2.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'blacklist_brand'
        """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_blacklist_user_brand_unique "
                "ON blacklist_brand(user_id, region_marketplace_id, brand)"
            )

        conn2.commit()
        conn2.close()

    # --- external_listed_asin UNIQUE（country_code 正） ---
    for country_code in country_codes:
        db_name = f"a_{country_code}_external_listed_asin.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ external_listed_asin テーブル存在確認
        cur2.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'external_listed_asin'
        """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_external_listed_user_asin_unique "
                "ON external_listed_asin(user_id, region_marketplace_id, asin)"
            )

        conn2.commit()
        conn2.close()

    # --- report_candidate_asin UNIQUE（country_code 正） ---
    for country_code in country_codes:
        db_name = f"a_{country_code}_report_candidate_asin.db"
        conn2 = get_conn(db_name)
        cur2 = conn2.cursor()

        # ★ report_candidate_asin テーブル存在確認
        cur2.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'report_candidate_asin'
        """)

        exists = cur2.fetchone()

        if exists:
            cur2.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_report_candidate_user_asin_unique "
                "ON report_candidate_asin(user_id, region_marketplace_id, asin)"
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

    # --- brandが実質空("-"/空欄/UNKNOWN)の商品はASIN単位でキャッシュするため、brandをNULL許容化 ---
    cur.execute("ALTER TABLE brand_gate_result ALTER COLUMN brand DROP NOT NULL")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_brand_gate_asin_unique "
        "ON brand_gate_result(user_id, region_marketplace_id, asin)"
    )

    conn.commit()
    conn.close()

    # --- a_shipping_override_master.db ---
    conn = get_conn("a_shipping_override_master.db")
    cur = conn.cursor()
    cur.execute(
        "ALTER TABLE shipping_override_master ALTER COLUMN shipping_amount DROP NOT NULL"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shipping_override_master_unique "
        "ON shipping_override_master(marketplace_id, seller_id, shipping_amount)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shipping_override_master_seller_only "
        "ON shipping_override_master(marketplace_id, seller_id) WHERE shipping_amount IS NULL"
    )
    conn.commit()
    conn.close()

    # --- a_pricing_settings.db ---
    conn = get_conn("a_pricing_settings.db")
    cur = conn.cursor()

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_shipping_config_unique "
        "ON shipping_config(user_id, country_code)"
    )

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_offer_filter_rules_unique "
        "ON offer_filter_rules(user_id, country_code)"
    )

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_master_rules_unique "
        "ON pricing_master_rules(user_id, country_code)"
    )

    conn.commit()
    conn.close()

    # --- a_api_block_state.db ---
    conn = get_conn("a_api_block_state.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_block_state_unique "
        "ON api_block_state(user_id, endpoint)"
    )
    conn.commit()
    conn.close()

    # --- a_lethal_weapon_preset.db ---
    conn = get_conn("a_lethal_weapon_preset.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lethal_weapon_preset_unique "
        "ON lethal_weapon_preset(user_id)"
    )
    conn.commit()
    conn.close()

    # --- a_api_429_events.db ---
    conn = get_conn("a_api_429_events.db")
    cur = conn.cursor()
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_429_events_created_at "
        "ON api_429_events(created_at)"
    )
    conn.commit()
    conn.close()

# --- メイン処理 ---
def main():

    # PostgreSQL用マスタDB
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
        "a_shipping_override_master.db",
        "a_lwa_credentials_log.db",
        "a_admin_settings.db",
        "a_api_block_state.db",
        "a_lethal_weapon_preset.db",
        "a_api_429_events.db",
        "a_carrier_remote_area.db",
        "a_orbit_orders.db",
        "a_orbit_settlement_lines.db",
        "a_orbit_buyer_history.db",
        "a_orbit_procurement_history.db",
        "a_orbit_buyer_security_notes.db",
        "a_google_oauth_tokens.db",
        "a_orbit_dispatch_sheet_settings.db",
        "a_orbit_credit_cards.db",
    ]

    # 固定DB migrate
    for db_file in base_dbs:
        migrate_db(db_file)

    # marketplaces から country_code を取得
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country_code FROM marketplaces")
    country_codes = [row["country_code"].lower() for row in cur.fetchall()]
    conn.close()

    # country_code ごとの migrate
    for country_code in country_codes:

        migrate_db(f"a_{country_code}_listed_items.db")
        migrate_db(f"a_{country_code}_blacklist_asin.db")
        migrate_db(f"a_{country_code}_blacklist_brand.db")
        migrate_db(f"a_{country_code}_external_listed_asin.db")
        migrate_db(f"a_{country_code}_report_candidate_asin.db")

    # INDEX
    add_unique_indexes()

    # 初期データ
    ensure_fx_settings_initialized()
    ensure_order_id_prefixes_seeded()

# --- ▼ ORBIT: order-id先頭桁の初期値投入（未設定のマーケットにのみ設定・既存の手動編集は上書きしない） ---
def ensure_order_id_prefixes_seeded():
    known_prefixes = {
        "US": "1",
        "AU": "2,5",
        "CA": "7",
    }

    conn = get_conn("a_marketplaces_master.db")
    cur = conn.cursor()

    for country_code, prefixes in known_prefixes.items():
        cur.execute("""
            UPDATE marketplaces_master
            SET order_id_prefixes = %s
            WHERE country_code = %s
            AND (order_id_prefixes IS NULL OR order_id_prefixes = '')
        """, (prefixes, country_code))

    conn.commit()
    conn.close()

# --- ▼ FX 初期設定挿入 ---
def ensure_fx_settings_initialized():
    conn = get_conn("a_fx.db")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM fx_settings")
    count = cur.fetchone()["count"]

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




