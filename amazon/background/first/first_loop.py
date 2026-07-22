## =====================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/background/first/first_loop.py
# 目的: first専用loop API起点
# =======================================================

import os
import time
import datetime
from datetime import timezone, timedelta
from amazon.db import get_conn

from amazon.routes.routes_catalog_v2 import update_home_catalog
from amazon.routes.routes_pricing_v2 import (update_home_pricing, update_region_pricing)
from amazon.background.common.background_common import get_ttl_sleep_sec, get_first_scan_settings
from amazon.routes.routes_pricing_v2 import update_listing_price


# --- ▼ SECTION 01: first loop 基本設定 ▼
def run_first_loop(app, db_dir):
    with app.app_context():
        ASIN_SLEEP_SEC = 1.0           # ASIN間Sleep時間
        JST = timezone(timedelta(hours=9))
        loop_count = 0  # LOOPカウント処理（生存確認用）

        while True:
            # === ★loop動作確認用（API関係なし） ===
            loop_count += 1
            print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [FIRST][CYCLE_START] cycle={loop_count}", flush=True)
            # =======================================

            # --- ▼ 追加: サイクル全体を保護。ここで捕まえないとDB接続エラー等1回で
            #     スレッドが完全に停止し、Flask本体は生きたままfirstだけ二度と動かなくなる ▼ ---
            try:
                # ★修正: 管理画面「FIRST Cycle Settings」の設定値をサイクルごとに反映する
                #        （固定値だと大量バックログ時に間隔を空けて負荷を下げる手段が無かった）
                scan_settings = get_first_scan_settings()
                MAX_FIRST_PER_CYCLE = scan_settings["scan_limit"]      # 件数制御
                FIRST_LOOP_SLEEP_SEC = scan_settings["interval_sec"]   # cycle間のSleep時間

                targets = []

                for listed_db in ["listed_items"]:

                    conn = get_conn(listed_db)

                    try:
                        cur = conn.cursor()

                        cur.execute("""
                            SELECT table_name
                            FROM information_schema.tables
                            WHERE table_name = 'listed_items'
                        """)

                        if not cur.fetchone(): continue

                        cur.execute("""
                            SELECT user_id, asin, home_marketplace_id, region_marketplace_id
                            FROM listed_items
                            WHERE first_try_count > 0
                            AND ttl_stop_status IS NULL
                            GROUP BY user_id, asin, home_marketplace_id, region_marketplace_id, created_at
                            ORDER BY created_at ASC
                            LIMIT %s
                        """, (MAX_FIRST_PER_CYCLE,))
                        rows = cur.fetchall()

                        columns = [desc[0] for desc in cur.description]

                        for r in rows:
                            row_dict = r

                            targets.append({
                                "db": listed_db,
                                "user_id": row_dict["user_id"],
                                "asin": row_dict["asin"],
                                "home_marketplace_id": row_dict["home_marketplace_id"],
                                "region_marketplace_id": row_dict["region_marketplace_id"],
                            })
                    finally:
                        conn.close()

                if not targets:
                    time.sleep(FIRST_LOOP_SLEEP_SEC)
                    continue

                # --- ASIN間Sleep秒数はサイクル中変わらないため、ASINごとにDB再取得せず1回だけ取得 ---
                api_sleep_sec = get_ttl_sleep_sec()

                _run_first_cycle(app, targets, api_sleep_sec, ASIN_SLEEP_SEC)

                time.sleep(FIRST_LOOP_SLEEP_SEC)

            except Exception:
                import traceback
                print("### FIRST LOOP ERROR ###", flush=True)
                traceback.print_exc()
                app.logger.error("### FIRST LOOP ERROR ###", exc_info=True)

                # ★追加：エラー内容をファイルにも記録（CMDのログが流れて消えても後から確認できるように）
                try:
                    os.makedirs(os.path.join(db_dir, "logs"), exist_ok=True)
                    log_path = os.path.join(db_dir, "logs", "first_error.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n[{datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}] ERROR\n")
                        f.write(traceback.format_exc())
                        f.write("\n")
                except Exception:
                    pass

                # --- サイクル全体が失敗した場合も、ループ自体は継続させる ---
                time.sleep(5)


# --- ▼ SECTION 02: 1サイクル分のASIN処理（例外は1件ごとに隔離） ▼ ---
def _run_first_cycle(app, targets, api_sleep_sec, ASIN_SLEEP_SEC):
    for t in targets:
        try:
            conn_mkt = get_conn("a_marketplaces.db")
            cur_mkt = conn_mkt.cursor()

            cur_mkt.execute("""
                SELECT country_code
                FROM marketplaces
                WHERE marketplace_id = %s
                LIMIT 1
            """, (t["home_marketplace_id"],))

            row_home = cur_mkt.fetchone()

            cur_mkt.execute("""
                SELECT country_code
                FROM marketplaces
                WHERE marketplace_id = %s
                LIMIT 1
            """, (t["region_marketplace_id"],))

            row_region = cur_mkt.fetchone()

            conn_mkt.close()

            cc_home = row_home["country_code"] if row_home else None
            cc_region = row_region["country_code"] if row_region else None

            # --- ▼ SECTION  firstで取得・updateする項目 ▼ ---


            update_home_catalog(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)



            update_home_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_home)



            # 責務〇〇に移動の為解除中 # === ▼ firstでregion_pricingを１回は取得するためのコード ▼ ===
            # update_region_pricing(user_id=t["user_id"], asin=t["asin"], country_code=cc_region)


            update_listing_price(user_id=t["user_id"], asin=t["asin"], country_code=cc_region)
            time.sleep(api_sleep_sec)
            # --- ▲ SECTION  firstで取得・updateする項目 ▲ ---

            # --- ★ SUCCESS判定：このリスティング自身のHOMEカタログ・価格が
            #     実際に書き込まれていれば即0（pricing_cacheはASIN単位の共有キャッシュで
            #     他ユーザー/他出品の取得結果が入っているだけの場合があり、
            #     このリスティング自身の取得成否の判定には使えないため使用しない） ---
            conn_success = get_conn(t["db"])
            try:
                cur_success = conn_success.cursor()
                cur_success.execute("""
                    SELECT home_title, home_price
                    FROM listed_items
                    WHERE user_id = %s AND asin = %s
                """, (t["user_id"], t["asin"]))
                row_success = cur_success.fetchone()

                if row_success and (row_success["home_title"] or "").strip() and row_success["home_price"] is not None:
                    cur_success.execute("""
                        UPDATE listed_items
                        SET first_try_count = 0
                        WHERE user_id = %s AND asin = %s
                    """, (t["user_id"], t["asin"]))
                    conn_success.commit()

                    time.sleep(ASIN_SLEEP_SEC)
                    continue
            finally:
                conn_success.close()

            time.sleep(ASIN_SLEEP_SEC)

        # except Exception:
        except Exception as e:
            app.logger.error(
                "### FIRST ERROR ### asin=%s user_id=%s",
                t["asin"], t["user_id"], exc_info=True
            )
        #--------------------------

        conn3 = get_conn(t["db"])
        try:
            cur3 = conn3.cursor()
            cur3.execute("""
                UPDATE listed_items
                SET first_try_count =
                    CASE
                        WHEN first_try_count > 0 THEN first_try_count - 1
                        ELSE 0
                    END
                WHERE user_id = %s AND asin = %s
            """, (t["user_id"], t["asin"]))
            conn3.commit()
        finally:
            conn3.close()

