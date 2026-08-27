# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/background/ttl/ttl_loop.py
# 目的: TTL専用loop API起点
# ==========================================================

import os
import time
import datetime
from datetime import timezone, timedelta

from amazon.background.ttl.ttl_days import get_account_ttl_days
from amazon.routes.routes_catalog_v2 import (update_home_catalog, update_region_catalog,)
from amazon.routes.routes_pricing_v2 import (update_home_pricing, update_region_pricing,)
from amazon.background.common.background_common import api_request_sleep, get_ttl_cycle_sleep_sec
from amazon.routes.routes_pricing_v2 import update_listing_price
from amazon.db import get_conn
from amazon.guard.guard_429 import is_blocked



# ★ 追加オプション：DBの最短TTLだけを見る
USE_DB_MIN_TTL = True

# HOME Pricing 稼働記録（ttl_cycle_log）で残すサイクル数の上限。
# ダッシュボードの「24h」集計が常に成立するよう、実運用のサイクル間隔でも
# 数日分は残る値にしておく（テーブルは軽量なので余裕を持たせる）。
TTL_CYCLE_LOG_KEEP = 5000


# --- ▼ HOME Pricing の積み残し / 最古待ち行スナップショット（稼働記録用） ▼ ---
# load_pricing_ttl_targets の HOME Pricing 対象クエリと同じ WHERE 条件で、
#  - backlog_count : LIMIT を掛けない期限切れ総数
#  - oldest        : 対象全体（期限切れ問わず）の MIN(h_pricing_ttl_at)
# を返す。ダッシュボードで「全部回っているか」「最古が前進しているか」を見る材料。
def _home_pricing_progress_snapshot():
    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE li.h_pricing_ttl_at IS NULL
                       OR CAST(li.h_pricing_ttl_at AS timestamp) <
                            ((NOW() AT TIME ZONE 'UTC')
                             - (mp.h_pricing_ttl_days * INTERVAL '1 day'))
                ) AS backlog_count,
                MIN(CAST(li.h_pricing_ttl_at AS timestamp)) AS oldest
            FROM listed_items li
            INNER JOIN marketplaces mp
                ON li.user_id = mp.user_id
                AND li.region_marketplace_id = mp.marketplace_id
            WHERE mp.enable_home_pricing = 1
              AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
              AND li.override_price IS NULL
              AND li.override_stock_zero IS NULL
        """)
        row = cur.fetchone()
        if not row:
            return (None, None)
        backlog = row["backlog_count"]
        oldest = row["oldest"]
        oldest_iso = oldest.isoformat() if oldest is not None else None
        return (backlog, oldest_iso)
    finally:
        conn.close()


# --- ▼ HOME Pricing 1サイクル記録を ttl_cycle_log へ INSERT（失敗してもループは止めない） ▼ ---
def _write_ttl_cycle_log(started_at, finished_at, backlog_count, target_count,
                         dispatched_count, error_count, oldest_before, oldest_after):
    try:
        conn = get_conn("a_pricing_settings.db")
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ttl_cycle_log
                    (leg, started_at, finished_at, backlog_count, target_count,
                     dispatched_count, error_count, oldest_before, oldest_after)
                VALUES ('home_pricing', %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                started_at, finished_at, backlog_count, target_count,
                dispatched_count, error_count, oldest_before, oldest_after,
            ))
            # 古い行を間引く（直近 TTL_CYCLE_LOG_KEEP サイクルだけ残す）
            cur.execute("""
                DELETE FROM ttl_cycle_log
                WHERE leg = 'home_pricing'
                  AND id <= (
                      SELECT MAX(id) - %s FROM ttl_cycle_log WHERE leg = 'home_pricing'
                  )
            """, (TTL_CYCLE_LOG_KEEP,))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[TTL][cycle_log] write skipped: {e}", flush=True)

# --- ▼ SECTION 01:  ▼ ---
def get_api_conf(user_id, country_code, db_dir):
    db_name = "a_marketplaces.db"
    conn = get_conn(db_name)

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM marketplaces
            WHERE user_id = %s
            AND country_code = %s
            LIMIT 1
        """, (
            user_id,
            country_code
        ))

        row = cur.fetchone()

        if not row:
            return {}

        return dict(row)

    finally:
        conn.close()

# --- ▼ SECTION 02: TTL loop 基本設定（FIRST写経） ▼
def run_ttl_loop(app, db_dir):
    with app.app_context():
        JST = timezone(timedelta(hours=9))
        loop_count = 0 # LOOPカウント処理

        # ★修正: 従来は catalog と pricing を同じ try で囲っていたため、
        #        catalog 側が毎サイクル例外を投げる状態になると
        #        pricing（＝仕入価格 home_price の更新）がサイクルごと
        #        まるごとスキップされ、仕入価格が何日も更新されない
        #        致命的な状態になっていた。系統ごとにエラーを隔離し、
        #        片方が落ちてももう片方は必ず回るようにする。
        def _run_ttl_leg(leg_name, fn):
            try:
                fn(db_dir)
            except Exception as e:
                import traceback
                print(f"### TTL LOOP ERROR [{leg_name}] ###")
                print(e)
                traceback.print_exc()
                app.logger.error("### TTL LOOP ERROR [%s] ###", leg_name, exc_info=True)

                # ★エラー内容をファイルにも記録（CMDのログが流れて消えても後から確認できるように）
                try:
                    os.makedirs(os.path.join(db_dir, "logs"), exist_ok=True)
                    log_path = os.path.join(db_dir, "logs", "ttl_error.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n[{datetime.datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}] ERROR [{leg_name}]\n")
                        f.write(traceback.format_exc())
                        f.write("\n")
                except Exception:
                    pass

        while True:
            # === ★loop動作確認用（API関係なし） ===============================================
            loop_count += 1 # LOOPカウント処理
            print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [TTL][CYCLE_START] cycle={loop_count}")
            print(f"[{datetime.datetime.now(JST).strftime('%H:%M:%S')}] [TTL][LOOP][ALIVE]")
            # =================================================================================

            _run_ttl_leg("catalog", load_catalog_ttl_targets)
            _run_ttl_leg("pricing", load_pricing_ttl_targets)

            # --- ▼ TTL進行更新（last_id）▼ ---
            try:
                conn = get_conn("a_pricing_settings.db")
                cur = conn.cursor()

                cur.execute("""
                    UPDATE ttl_state
                    SET last_id = COALESCE(last_id, 0) + 200
                    WHERE user_id = %s
                """, (1,))

                conn.commit()
                conn.close()
            except Exception:
                pass

            # ★変更: 管理者タブⅡ ttl_cycle_sleep_sec をサイクルごとに反映（旧ハードコード3秒）
            time.sleep(get_ttl_cycle_sleep_sec())

# --- ▼ SECTION 03: TTL対象取得（Cacheベース / catalog） ▼ ---
def load_catalog_ttl_targets(db_dir: str):
    try:
        # --- Catalog HOME ---
        tmp = []

        for db_path in ["listed_items"]:
            conn_li = get_conn(db_path)

            try:
                cur_li = conn_li.cursor()

                # --- ▼ 管理画面で設定したHOME Catalog対象 上限件数を取得 ▼ ---
                conn_settings = get_conn("a_bg_scan_settings.db")
                cur_settings = conn_settings.cursor()
                cur_settings.execute("""
                    SELECT ttl_limit_home_catalog
                    FROM bg_scan_settings
                    WHERE id = 1
                """)
                settings_row = cur_settings.fetchone()
                conn_settings.close()

                # ★修正: 未設定(NULL)だと "LIMIT NULL" ＝ 無制限になり、
                #        期限切れ全件を1サイクルで一気に叩いて429スロットリング
                #        を誘発し、以降 api_error で TTL 時計が進まず何日も
                #        更新されない状態に陥る。未設定時は安全側の既定値でキャップする。
                ttl_limit_home_pricing = settings_row["ttl_limit_home_catalog"] or 50

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.home_marketplace_id,
                        li.inactive_reason,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_home_catalog = 1
                    AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
                    AND li.override_price IS NULL
                    AND li.override_stock_zero IS NULL
                    AND NOT (li.status = 'pre' AND li.first_try_count > 0)
                    AND (
                        li.h_catalog_ttl_at IS NULL
                        OR CAST(li.h_catalog_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.h_catalog_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.h_catalog_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.h_catalog_ttl_at
                    LIMIT %s
                """, (ttl_limit_home_pricing,))

                listed_rows = cur_li.fetchall()
                print("[HOME_CAT_Target count]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "home_marketplace_id": lr["home_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"],
                        "was_no_catalog": (lr["inactive_reason"] == "NO_CATALOG")
                    })

            finally:
                conn_li.close()

        home_rows = tmp

        # --- Catalog REGION ---
        tmp = []

        for db_path in ["listed_items"]:
            conn_li = get_conn(db_path)

            try:
                cur_li = conn_li.cursor()

                # --- ▼ 管理画面で設定したREGION Catalog対象 上限件数を取得 ▼ ---
                conn_settings = get_conn("a_bg_scan_settings.db")
                cur_settings = conn_settings.cursor()
                cur_settings.execute("""
                    SELECT ttl_limit_region_catalog
                    FROM bg_scan_settings
                    WHERE id = 1
                """)
                settings_row = cur_settings.fetchone()
                conn_settings.close()

                ttl_limit_home_pricing = settings_row["ttl_limit_region_catalog"] or 50  # ★NULL=無制限を回避

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.region_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_region_catalog = 1
                    AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
                    AND li.override_price IS NULL
                    AND li.override_stock_zero IS NULL
                    AND NOT (li.status = 'pre' AND li.first_try_count > 0)
                    AND (
                        li.r_catalog_ttl_at IS NULL
                        OR CAST(li.r_catalog_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.r_catalog_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.r_catalog_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.r_catalog_ttl_at
                    LIMIT %s
                """, (ttl_limit_home_pricing,))

                listed_rows = cur_li.fetchall()
                print("[REGION_CAT_Target count]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "region_marketplace_id": lr["region_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        region_rows = tmp


        # Catalog HOME ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in home_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  

            executed_count += 1 

            dispatch_ttl_execution(
                [("home", "catalog")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": record.get("home_marketplace_id"),
                    "region_marketplace_id": None,
                    "was_no_catalog": record.get("was_no_catalog"),
                },
                country_code
            )

        # Catalog REGION ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in region_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  

            executed_count += 1 

            dispatch_ttl_execution(
                [("region", "catalog")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": None,
                    "region_marketplace_id": record.get("region_marketplace_id"),
                },
                country_code
            )

    finally:
        pass

# --- ▼ SECTION 04: TTL対象取得（Cacheベース / pricing） ▼ ---
def load_pricing_ttl_targets(db_dir: str):
    try:
        # --- Pricing HOME ---
        tmp = []

        for db_path in ["listed_items"]:
            conn_li = get_conn(db_path)

            try:
                cur_li = conn_li.cursor()

                # --- ▼ 管理画面で設定したHOME Pricing対象 上限件数を取得 ▼ ---
                conn_settings = get_conn("a_bg_scan_settings.db")
                cur_settings = conn_settings.cursor()
                cur_settings.execute("""
                    SELECT ttl_limit_home_pricing
                    FROM bg_scan_settings
                    WHERE id = 1
                """)
                settings_row = cur_settings.fetchone()
                conn_settings.close()

                ttl_limit_home_pricing = settings_row["ttl_limit_home_pricing"] or 50  # ★NULL=無制限を回避

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.home_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_home_pricing = 1
                    AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
                    AND li.override_price IS NULL
                    AND li.override_stock_zero IS NULL
                    AND (
                        li.h_pricing_ttl_at IS NULL
                        OR CAST(li.h_pricing_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.h_pricing_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.h_pricing_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.h_pricing_ttl_at
                    LIMIT %s
                """, (ttl_limit_home_pricing,))

                listed_rows = cur_li.fetchall()
                print("[HOME_Pri_Target count]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "home_marketplace_id": lr["home_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        home_rows = tmp

        # --- Pricing REGION ---
        tmp = []

        for db_path in ["listed_items"]:
            conn_li = get_conn(db_path)

            try:
                cur_li = conn_li.cursor()

                # --- ▼ 管理画面で設定したREGION Pricing対象 上限件数を取得 ▼ ---
                conn_settings = get_conn("a_bg_scan_settings.db")
                cur_settings = conn_settings.cursor()
                cur_settings.execute("""
                    SELECT ttl_limit_region_pricing
                    FROM bg_scan_settings
                    WHERE id = 1
                """)
                settings_row = cur_settings.fetchone()
                conn_settings.close()

                ttl_limit_home_pricing = settings_row["ttl_limit_region_pricing"] or 50  # ★NULL=無制限を回避

                cur_li.execute("""
                    SELECT
                        li.user_id,
                        li.asin,
                        li.region_marketplace_id,
                        mp.country_code
                    FROM listed_items li
                    INNER JOIN marketplaces mp
                        ON li.user_id = mp.user_id
                        AND li.region_marketplace_id = mp.marketplace_id
                    WHERE mp.enable_region_pricing = 1
                    AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
                    AND li.override_price IS NULL
                    AND li.override_stock_zero IS NULL
                    AND NOT (li.status = 'pre' AND li.first_try_count > 0)
                    AND (
                        li.r_pricing_ttl_at IS NULL
                        OR CAST(li.r_pricing_ttl_at AS timestamp) <
                            (
                                (NOW() AT TIME ZONE 'UTC')
                                - (mp.r_pricing_ttl_days * INTERVAL '1 day')
                            )
                    )
                    ORDER BY
                        CASE
                            WHEN li.r_pricing_ttl_at IS NULL THEN 0
                            ELSE 1
                        END,
                        li.r_pricing_ttl_at
                    LIMIT %s
                """, (ttl_limit_home_pricing,))

                listed_rows = cur_li.fetchall()
                print("[REGION_Pri_Target count]", len(listed_rows), flush=True) # TTL対象数カウント

                for lr in listed_rows:

                    if not lr["user_id"] or not lr["country_code"]:
                        continue

                    tmp.append({
                        "asin": lr["asin"],
                        "region_marketplace_id": lr["region_marketplace_id"],
                        "user_id": lr["user_id"],
                        "country_code": lr["country_code"]
                    })

            finally:
                conn_li.close()

        region_rows = tmp


        # Pricing HOME ▼▼
        checked_count = 0
        executed_count = 0

        # ★追加: 稼働記録（ttl_cycle_log）用の計測 — サイクル開始スナップショット
        _cyc_started_at = datetime.datetime.utcnow().isoformat()
        _cyc_backlog, _cyc_oldest_before = _home_pricing_progress_snapshot()
        _cyc_target = len(home_rows)
        _cyc_dispatched = 0
        _cyc_errors = 0

        for r in home_rows:
            record = dict(r)

            checked_count += 1

            user_id = record.get("user_id")
            country_code = record.get("country_code")

            executed_count += 1

            _res = dispatch_ttl_execution(
                [("home", "pricing")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": record.get("home_marketplace_id"),
                    "region_marketplace_id": None,
                },
                country_code
            )
            _cyc_dispatched += 1
            if _res == "error":
                _cyc_errors += 1

        # ★追加: サイクル終了スナップショット＋記録
        _cyc_backlog_after, _cyc_oldest_after = _home_pricing_progress_snapshot()
        _write_ttl_cycle_log(
            started_at=_cyc_started_at,
            finished_at=datetime.datetime.utcnow().isoformat(),
            backlog_count=_cyc_backlog,
            target_count=_cyc_target,
            dispatched_count=_cyc_dispatched,
            error_count=_cyc_errors,
            oldest_before=_cyc_oldest_before,
            oldest_after=_cyc_oldest_after,
        )

        # Pricing REGION ▼▼
        checked_count = 0 
        executed_count = 0 

        for r in region_rows:
            record = dict(r)

            checked_count += 1 

            user_id = record.get("user_id")  
            country_code = record.get("country_code")  
        
            executed_count += 1          

            dispatch_ttl_execution(
                [("region", "pricing")],
                {
                    "user_id": user_id,
                    "asin": record.get("asin"),
                    "sku": None,
                    "home_marketplace_id": None,
                    "region_marketplace_id": record.get("region_marketplace_id"),
                },
                country_code
            )

    finally:
        pass

# --- ▼ SECTION 05: TTL実行受け口 ▼ ---
def dispatch_ttl_execution(targets, record, country_code):
    had_error = False  # ★追加: 稼働記録（ttl_cycle_log）用に成否を返す
    for scope, ttl_type in targets:
        # ----API を叩いたのはなにか確認するためのPrint
        print(f"<<< {scope.upper()} {ttl_type.upper()} >>> "
            f"{(datetime.datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')} "
            f"user={record['user_id']} "
            f"asin={record['asin']} "
            f"country={country_code}",
            flush=True
        )  # --- 削除不可 コメントアウトのみ ---

        # --- ▼ 1件（1scope）ごとにエラーを隔離。ここで捕まえないと1件のエラーで
        #        HOME/REGION Catalog/Pricingの残り全件・他3系統が丸ごと止まってしまう ▼ ---
        try:
            # --- HOME / CATALOG ---
            if scope == "home" and ttl_type == "catalog":
                catalog_result = update_home_catalog(
                    user_id=record["user_id"],
                    asin=record["asin"],
                    country_code=country_code,
                )

                # ★追加: 直前まで NO_CATALOG だった項目だけ、寸法・重量が埋まったことを
                #        即座に反映するため再判定する（REGION PRICINGのTTLを待たない）。
                #        通常のカタログ更新（NO_CATALOG以外）まで毎回この重い再計算を挟むと
                #        TTLループ全体が遅くなるため、対象を限定する。
                if (
                    record.get("was_no_catalog")
                    and isinstance(catalog_result, dict)
                    and catalog_result.get("status") == "ok"
                ):
                    update_listing_price(
                        user_id=record["user_id"],
                        asin=record["asin"],
                        country_code=country_code,
                    )

            # --- HOME / PRICING ---
            elif scope == "home" and ttl_type == "pricing":

                if not record.get("home_marketplace_id"):
                    continue

                update_home_pricing(
                    user_id=record["user_id"],
                    asin=record["asin"],
                    country_code=country_code,
                )

            # --- REGION / CATALOG ---
            elif scope == "region" and ttl_type == "catalog":
                update_region_catalog(
                    user_id=record["user_id"],
                    asin=record["asin"],
                    country_code=country_code,
                )

            # --- REGION / PRICING ---
            elif scope == "region" and ttl_type == "pricing":
                update_region_pricing(
                    user_id=record["user_id"],
                    asin=record["asin"],
                    country_code=country_code,
                )

        except Exception as e:
            had_error = True
            import traceback
            from flask import current_app
            print(f"### TTL DISPATCH ERROR ### scope={scope} ttl_type={ttl_type} "
                f"user={record['user_id']} asin={record['asin']} country={country_code}: {e}",
                flush=True)
            traceback.print_exc()
            current_app.logger.error(
                "### TTL DISPATCH ERROR ### scope=%s ttl_type=%s user=%s asin=%s country=%s",
                scope, ttl_type, record["user_id"], record["asin"], country_code,
                exc_info=True
            )

    # ★変更: catalog/pricingで実際のAmazon側レート制限が違うため、
    #        この呼び出しがどちらの種別だったかでsleep秒数を切り替える
    ttl_kind = "catalog" if any(t[1] == "catalog" for t in targets) else "pricing"
    api_request_sleep(kind=ttl_kind)

    return "error" if had_error else "ok"

