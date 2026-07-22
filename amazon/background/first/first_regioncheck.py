## =====================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/background/first/first_regioncheck.py
# 目的: first_loopによるHOME取得後のREGION未取得チェック専用
# =======================================================

import os
import time
import datetime
from datetime import timezone, timedelta
from amazon.db import get_conn

from amazon.background.common.background_common import api_request_sleep, get_first_scan_settings

from amazon.routes.routes_catalog_v2 import update_region_catalog
from amazon.routes.routes_pricing_v2 import update_region_pricing


# --- ▼ SECTION 01: region check loop 基本設定 ▼
def run_first_regioncheck(app, db_dir):

    ASIN_SLEEP_SEC = 1.0
    JST = timezone(timedelta(hours=9))
    loop_count = 0  # LOOPカウント処理（生存確認用）

    while True:

        # === ★loop動作確認用（API関係なし） ===
        loop_count += 1
        print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [REGIONCHECK][CYCLE_START] cycle={loop_count}", flush=True)
        # =======================================

        # --- ▼ 追加: サイクル全体を保護。ここで捕まえないとDB接続エラー等1回で
        #     スレッドが完全に停止し、Flask本体は生きたままregioncheckだけ二度と動かなくなる ▼ ---
        try:
            with app.app_context():

                # ★修正: 管理画面「FIRST Cycle Settings」の設定値をサイクルごとに反映する
                #        （first_loopと同じ設定を共有。固定値だと負荷を下げる手段が無かった）
                scan_settings = get_first_scan_settings()
                MAX_REGIONCHECK_PER_CYCLE = scan_settings["scan_limit"]
                REGIONCHECK_LOOP_SLEEP_SEC = scan_settings["interval_sec"]

                targets = []

                for listed_db in ["listed_items"]:

                    conn = get_conn(listed_db)

                    try:

                        cur = conn.cursor()
                        cur.execute("""
                            SELECT user_id, asin, region_marketplace_id
                            FROM listed_items
                            WHERE first_try_count = 0
                            AND status = 'pre'
                            AND ttl_stop_status IS NULL
                            GROUP BY user_id, asin, region_marketplace_id, created_at
                            ORDER BY created_at ASC
                            LIMIT %s
                        """, (MAX_REGIONCHECK_PER_CYCLE,))

                        rows = cur.fetchall()

                        for r in rows:

                            targets.append({
                                "db": listed_db,
                                "user_id": r["user_id"],
                                "asin": r["asin"],
                                "region_marketplace_id": r["region_marketplace_id"],
                            })

                    finally:

                        conn.close()

                _run_regioncheck_cycle(app, targets)

            time.sleep(REGIONCHECK_LOOP_SLEEP_SEC)

        except Exception:
            import traceback
            print("### REGIONCHECK LOOP ERROR ###", flush=True)
            traceback.print_exc()
            app.logger.error("### REGIONCHECK LOOP ERROR ###", exc_info=True)

            # ★追加：エラー内容をファイルにも記録（CMDのログが流れて消えても後から確認できるように）
            try:
                os.makedirs(os.path.join(db_dir, "logs"), exist_ok=True)
                log_path = os.path.join(db_dir, "logs", "regioncheck_error.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}] ERROR\n")
                    f.write(traceback.format_exc())
                    f.write("\n")
            except Exception:
                pass

            # --- サイクル全体が失敗した場合も、ループ自体は継続させる ---
            time.sleep(5)


# --- ▼ SECTION 02: 1サイクル分のASIN処理（例外は1件ごとに隔離） ▼ ---
def _run_regioncheck_cycle(app, targets):
    for t in targets:

        try:

            conn_mkt = get_conn("a_marketplaces.db")
            cur_mkt = conn_mkt.cursor()

            cur_mkt.execute("""
                SELECT country_code
                FROM marketplaces
                WHERE marketplace_id = %s
                LIMIT 1
            """, (t["region_marketplace_id"],))

            row_region = cur_mkt.fetchone()

            if not row_region:
                continue

            cc_region = row_region["country_code"]

            update_region_catalog(
                user_id=t["user_id"],
                asin=t["asin"],
                country_code=cc_region
            )

            update_region_pricing(
                user_id=t["user_id"],
                asin=t["asin"],
                country_code=cc_region
            )

            conn_c = get_conn("a_catalog_cache.db")
            cur_c = conn_c.cursor()

            cur_c.execute("""
                SELECT region_raw_json
                FROM catalog_cache
                WHERE asin = %s
                AND region_marketplace_id = %s
            """, (
                t["asin"],
                t["region_marketplace_id"]
            ))

            row_catalog = cur_c.fetchone()

            conn_p = get_conn("a_pricing_cache.db")
            cur_p = conn_p.cursor()

            cur_p.execute("""
                SELECT region_offers_json
                FROM pricing_cache
                WHERE asin = %s
                AND region_marketplace_id = %s
            """, (
                t["asin"],
                t["region_marketplace_id"]
            ))

            row_pricing = cur_p.fetchone()

            has_catalog = bool(
                row_catalog and row_catalog["region_raw_json"]
            )

            has_pricing = bool(
                row_pricing and row_pricing["region_offers_json"]
            )

            new_first_try_count = -1

            if has_catalog != has_pricing:
                new_first_try_count = -2

            elif has_catalog and has_pricing:
                new_first_try_count = -3

            conn_listed = get_conn(t["db"])
            cur_listed = conn_listed.cursor()

            cur_listed.execute("""
                UPDATE listed_items
                SET first_try_count = %s
                WHERE user_id = %s
                AND asin = %s
            """, (
                new_first_try_count,
                t["user_id"],
                t["asin"]
            ))

            conn_listed.commit()
            conn_listed.close()

            conn_p.close()
            conn_c.close()

            conn_mkt.close()

        except Exception as e:
            app.logger.error(
                "### REGIONCHECK ERROR ### asin=%s user_id=%s",
                t["asin"], t["user_id"], exc_info=True
            )
