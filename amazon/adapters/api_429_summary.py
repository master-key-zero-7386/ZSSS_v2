# ==========================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ----------------------------------------------------------
# ファイル名： amazon/adapters/api_429_summary.py
# 目的： 429発生状況の集計（Dashboard表示用・読み取り専用）
# ==========================================================

from amazon.db import get_conn
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


# --- ▼ SECTION 01: 429発生サマリー取得（本日・前日・平均間隔） ▼ ---
def get_api_429_summary(user_id: int):
    conn = get_conn("a_api_429_events.db")
    cur = conn.cursor()

    # --- 直近2日分だけ見れば「本日・前日」判定には十分（JSTとUTCの差は最大9時間） ---
    cutoff_utc = (datetime.utcnow() - timedelta(days=2)).isoformat()

    cur.execute("""
        SELECT created_at
        FROM api_429_events
        WHERE user_id = %s AND created_at >= %s
        ORDER BY created_at ASC
    """, (user_id, cutoff_utc))
    rows = cur.fetchall()
    conn.close()

    now_jst = datetime.now(JST)
    today_start_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start_jst = today_start_jst - timedelta(days=1)

    today_times = []
    yesterday_count = 0

    for r in rows:
        try:
            ts_utc = datetime.fromisoformat(r["created_at"])
            if ts_utc.tzinfo is None:
                ts_utc = ts_utc.replace(tzinfo=timezone.utc)
            ts_jst = ts_utc.astimezone(JST)
        except Exception:
            continue

        if ts_jst >= today_start_jst:
            today_times.append(ts_jst)
        elif ts_jst >= yesterday_start_jst:
            yesterday_count += 1

    today_count = len(today_times)

    avg_interval_sec = None
    if len(today_times) >= 2:
        diffs = [
            (today_times[i] - today_times[i - 1]).total_seconds()
            for i in range(1, len(today_times))
        ]
        avg_interval_sec = round(sum(diffs) / len(diffs), 1)

    last_occurred_at = today_times[-1].strftime("%Y-%m-%d %H:%M:%S") if today_times else None

    return {
        "today_count": today_count,
        "yesterday_count": yesterday_count,
        "avg_interval_sec": avg_interval_sec,
        "last_occurred_at": last_occurred_at,
    }
