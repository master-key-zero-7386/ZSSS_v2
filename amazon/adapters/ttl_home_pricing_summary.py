# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名: amazon/adapters/ttl_home_pricing_summary.py
# 目的: HOME Pricing TTL の稼働状況サマリー（Dashboard表示用・読み取り専用）
#   フェーズ1: listed_items + marketplaces からカバー率・鮮度分布をライブ集計
#   フェーズ2: ttl_cycle_log から実スループット・詰まり（ぐるぐる）検知
# ==========================================================

from datetime import datetime
from amazon.db import get_conn


def _age_hours(dt):
    """tz-naive UTC の datetime → 現在との差(時間)。None は None。"""
    if dt is None:
        return None
    try:
        return round((datetime.utcnow() - dt).total_seconds() / 3600.0, 1)
    except Exception:
        return None


def _iso(dt):
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


# --- ▼ SECTION 01: フェーズ1 ライブ集計（国別） ▼ ---
def _live_by_country():
    conn = get_conn("listed_items")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                mp.country_code                              AS country,
                mp.h_pricing_ttl_days                        AS ttl_days,
                COUNT(*)                                     AS total,
                COUNT(*) FILTER (WHERE li.h_pricing_ttl_at IS NULL) AS never_cnt,
                COUNT(*) FILTER (
                    WHERE li.h_pricing_ttl_at IS NOT NULL
                      AND CAST(li.h_pricing_ttl_at AS timestamp) >=
                          ((NOW() AT TIME ZONE 'UTC') - (mp.h_pricing_ttl_days * INTERVAL '1 day'))
                )                                            AS fresh_cnt,
                COUNT(*) FILTER (
                    WHERE li.h_pricing_ttl_at IS NOT NULL
                      AND CAST(li.h_pricing_ttl_at AS timestamp) <
                          ((NOW() AT TIME ZONE 'UTC') - (mp.h_pricing_ttl_days * INTERVAL '1 day'))
                )                                            AS overdue_cnt,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour'
                )                                            AS upd_1h,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour'
                )                                            AS upd_24h,
                MIN(CAST(li.h_pricing_ttl_at AS timestamp))  AS oldest,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour'
                )                                            AS b_lt1h,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) <  (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour'
                      AND CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '6 hour'
                )                                            AS b_1_6h,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) <  (NOW() AT TIME ZONE 'UTC') - INTERVAL '6 hour'
                      AND CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour'
                )                                            AS b_6_24h,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) <  (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour'
                      AND CAST(li.h_pricing_ttl_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '3 day'
                )                                            AS b_1_3d,
                COUNT(*) FILTER (
                    WHERE CAST(li.h_pricing_ttl_at AS timestamp) <  (NOW() AT TIME ZONE 'UTC') - INTERVAL '3 day'
                )                                            AS b_gt3d
            FROM listed_items li
            INNER JOIN marketplaces mp
                ON li.user_id = mp.user_id
                AND li.region_marketplace_id = mp.marketplace_id
            WHERE mp.enable_home_pricing = 1
              AND (li.ttl_stop_status IS NULL OR li.ttl_stop_status = '0')
              AND li.override_price IS NULL
              AND li.override_stock_zero IS NULL
            GROUP BY mp.country_code, mp.h_pricing_ttl_days
            ORDER BY mp.country_code
        """)
        return cur.fetchall()
    finally:
        conn.close()


def _row_to_country_dict(r):
    total = r["total"] or 0
    fresh = r["fresh_cnt"] or 0
    return {
        "country": r["country"],
        "ttl_days": float(r["ttl_days"]) if r["ttl_days"] is not None else None,
        "total": total,
        "fresh": fresh,
        "overdue": r["overdue_cnt"] or 0,
        "never": r["never_cnt"] or 0,
        "coverage_pct": round(fresh * 100.0 / total, 1) if total else None,
        "oldest_at": _iso(r["oldest"]),
        "oldest_age_hours": _age_hours(r["oldest"]),
        "updated_1h": r["upd_1h"] or 0,
        "updated_24h": r["upd_24h"] or 0,
        "buckets": {
            "lt1h": r["b_lt1h"] or 0,
            "h1_6": r["b_1_6h"] or 0,
            "h6_24": r["b_6_24h"] or 0,
            "d1_3": r["b_1_3d"] or 0,
            "gt3d": r["b_gt3d"] or 0,
            "never": r["never_cnt"] or 0,
        },
    }


# --- ▼ SECTION 02: フェーズ2 サイクルログ集計 ▼ ---
def _cycle_stats():
    conn = get_conn("a_pricing_settings.db")
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT started_at, finished_at, backlog_count, target_count,
                   dispatched_count, error_count, oldest_before, oldest_after
            FROM ttl_cycle_log
            WHERE leg = 'home_pricing'
            ORDER BY id DESC
            LIMIT 1
        """)
        last = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE CAST(started_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour')  AS cycles_1h,
                COUNT(*) FILTER (WHERE CAST(started_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour') AS cycles_24h,
                COALESCE(SUM(dispatched_count) FILTER (WHERE CAST(started_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '1 hour'), 0)  AS disp_1h,
                COALESCE(SUM(dispatched_count) FILTER (WHERE CAST(started_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour'), 0) AS disp_24h,
                COALESCE(SUM(error_count)      FILTER (WHERE CAST(started_at AS timestamp) >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '24 hour'), 0) AS err_24h
            FROM ttl_cycle_log
            WHERE leg = 'home_pricing'
        """)
        win = cur.fetchone()

        cur.execute("""
            SELECT started_at, dispatched_count, oldest_before, oldest_after
            FROM ttl_cycle_log
            WHERE leg = 'home_pricing'
            ORDER BY id DESC
            LIMIT 5
        """)
        recent = cur.fetchall()
    finally:
        conn.close()

    # --- 詰まり（ぐるぐる）判定: 直近5サイクルのうち、実処理があったのに
    #     最古(oldest)が前進していないサイクルが3つ以上なら stuck ---
    stalled = 0
    considered = 0
    for r in recent:
        if (r["dispatched_count"] or 0) <= 0:
            continue
        considered += 1
        ob, oa = r["oldest_before"], r["oldest_after"]
        advanced = (ob is not None and oa is not None and str(oa) > str(ob))
        if not advanced:
            stalled += 1
    stuck = considered >= 3 and stalled >= 3

    last_d = None
    if last:
        last_d = {
            "started_at": last["started_at"],
            "finished_at": last["finished_at"],
            "backlog_count": last["backlog_count"],
            "target_count": last["target_count"],
            "dispatched_count": last["dispatched_count"],
            "error_count": last["error_count"],
            "oldest_before": last["oldest_before"],
            "oldest_after": last["oldest_after"],
        }

    return {
        "last": last_d,
        "cycles_1h": (win["cycles_1h"] if win else 0) or 0,
        "cycles_24h": (win["cycles_24h"] if win else 0) or 0,
        "dispatched_1h": int(win["disp_1h"]) if win and win["disp_1h"] is not None else 0,
        "dispatched_24h": int(win["disp_24h"]) if win and win["disp_24h"] is not None else 0,
        "errors_24h": int(win["err_24h"]) if win and win["err_24h"] is not None else 0,
        "stuck": stuck,
        "recent": [
            {
                "started_at": r["started_at"],
                "dispatched_count": r["dispatched_count"],
                "oldest_before": r["oldest_before"],
                "oldest_after": r["oldest_after"],
            }
            for r in recent
        ],
    }


# --- ▼ SECTION 03: 設定値エコー ▼ ---
def _config_echo():
    try:
        conn = get_conn("a_bg_scan_settings.db")
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT ttl_limit_home_pricing, ttl_sleep_sec_pricing, ttl_cycle_sleep_sec
                FROM bg_scan_settings WHERE id = 1
            """)
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return {}
        return {
            "ttl_limit_home_pricing": row["ttl_limit_home_pricing"],
            "ttl_sleep_sec_pricing": row["ttl_sleep_sec_pricing"],
            "ttl_cycle_sleep_sec": row["ttl_cycle_sleep_sec"],
        }
    except Exception:
        return {}


# --- ▼ SECTION 04: 公開関数 ▼ ---
def get_ttl_home_pricing_summary(user_id: int = None) -> dict:
    by_country_rows = _live_by_country()
    by_country = [_row_to_country_dict(r) for r in by_country_rows]

    total = sum(c["total"] for c in by_country)
    fresh = sum(c["fresh"] for c in by_country)
    overdue = sum(c["overdue"] for c in by_country)
    never = sum(c["never"] for c in by_country)
    upd_1h = sum(c["updated_1h"] for c in by_country)
    upd_24h = sum(c["updated_24h"] for c in by_country)

    buckets = {"lt1h": 0, "h1_6": 0, "h6_24": 0, "d1_3": 0, "gt3d": 0, "never": 0}
    for c in by_country:
        for k in buckets:
            buckets[k] += c["buckets"][k]

    oldest_candidates = [c["oldest_at"] for c in by_country if c["oldest_at"]]
    oldest_at = min(oldest_candidates) if oldest_candidates else None
    oldest_age_hours = None
    if oldest_at:
        try:
            oldest_age_hours = round(
                (datetime.utcnow() - datetime.fromisoformat(oldest_at)).total_seconds() / 3600.0, 1
            )
        except Exception:
            oldest_age_hours = None

    cycle = _cycle_stats()

    # --- 全ASIN1巡の推定時間: 実スループット(24h dispatched) を優先、無ければ upd_24h ---
    rate_per_day = cycle["dispatched_24h"] or upd_24h or 0
    est_full_sweep_hours = round(total / (rate_per_day / 24.0), 1) if rate_per_day else None

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "config": _config_echo(),
        "overall": {
            "total": total,
            "fresh": fresh,
            "overdue": overdue,
            "never": never,
            "coverage_pct": round(fresh * 100.0 / total, 1) if total else None,
            "oldest_at": oldest_at,
            "oldest_age_hours": oldest_age_hours,
            "updated_1h": upd_1h,
            "updated_24h": upd_24h,
            "est_full_sweep_hours": est_full_sweep_hours,
            "buckets": buckets,
        },
        "by_country": by_country,
        "cycle": cycle,
    }
