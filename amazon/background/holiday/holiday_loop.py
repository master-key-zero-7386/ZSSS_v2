# ==========================================
# ファイル名: amazon/background/holiday/holiday_loop.py
# 目的: 日本の祝日（内閣府CSV）を日次で取得し jp_holidays テーブルへUPSERTする常駐ループ
# ==========================================
#
# 元データ: https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv
#   - 文字コードは Shift_JIS（cp932）。UTF-8で読むと文字化けする。
#   - 1列目 "国民の祝日・休日月日"（YYYY/M/D）、2列目 "国民の祝日・休日名称"。
#   - 内閣府は概ね「翌年分まで」しか掲載しないため、放置すると再来年以降が空になる。
#     → 24時間ごとに取り直して、内閣府が先の分を追加したら自動で取り込む。
#
# ORBIT の到着予定日・出荷期日が休業日（土日祝＋長期休業）に当たるかの判定に使う。
# 取得失敗時は既存の jp_holidays をそのまま使う（業務は止めない）。

import time
import traceback
from datetime import datetime, timedelta

import requests

from amazon.db import get_conn

CAO_HOLIDAY_CSV_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"

HOLIDAY_LOOP_SLEEP_SEC = 3600.0      # ループ間待機（1時間ごとに更新要否を判定）
HOLIDAY_UPDATE_INTERVAL_HOURS = 24   # 実際の再取得間隔


# --- ▼ SECTION 01: エントリポイント ▼ ---
def run_holiday_loop(app):
    """日本の祝日CSVを定期取得して jp_holidays を最新化する。"""
    while True:
        try:
            last_updated = _get_last_updated_at()
            now = datetime.utcnow()

            if last_updated is None:
                print("[HOLIDAY] First run - fetch required")
                _refresh_holidays()
            elif now - last_updated >= timedelta(hours=HOLIDAY_UPDATE_INTERVAL_HOURS):
                print(f"[HOLIDAY] Interval exceeded ({last_updated.isoformat()}) - fetch required")
                _refresh_holidays()
            else:
                pass  # 更新不要

        except Exception as e:
            print("### HOLIDAY LOOP ERROR ###")
            print(e)
            traceback.print_exc()
            try:
                app.logger.error("### HOLIDAY LOOP ERROR ###", exc_info=True)
            except Exception:
                pass

        time.sleep(HOLIDAY_LOOP_SLEEP_SEC)


# --- ▼ SECTION 02: 最終更新時刻 ▼ ---
def _get_last_updated_at():
    conn = get_conn("a_jp_holidays.db")
    cur = conn.cursor()
    cur.execute("SELECT MAX(updated_at) AS last FROM jp_holidays")
    row = cur.fetchone()
    conn.close()

    if not row or not row["last"]:
        return None
    try:
        return datetime.fromisoformat(row["last"])
    except ValueError:
        return None


# --- ▼ SECTION 03: 取得＋UPSERT ▼ ---
def _refresh_holidays():
    rows = _fetch_cao_holidays()
    if not rows:
        print("[HOLIDAY] fetched 0 rows - skip (keep existing data)")
        return

    now_iso = datetime.utcnow().isoformat()
    conn = get_conn("a_jp_holidays.db")
    cur = conn.cursor()
    for holiday_date, name in rows:
        cur.execute(
            """
            INSERT INTO jp_holidays (holiday_date, name, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (holiday_date)
            DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at
            """,
            (holiday_date, name, now_iso),
        )
    conn.commit()
    conn.close()
    print(f"[HOLIDAY] upserted {len(rows)} holidays")


# --- ▼ SECTION 04: 内閣府CSVの取得・パース ▼ ---
def _fetch_cao_holidays():
    """内閣府の祝日CSVを取得して [(YYYY-MM-DD, 名称), ...] を返す。"""
    res = requests.get(CAO_HOLIDAY_CSV_URL, timeout=15)
    res.raise_for_status()

    # Shift_JIS（cp932）。壊れた行があっても止めないよう replace。
    text = res.content.decode("cp932", errors="replace")

    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue

        raw_date = parts[0].strip()
        name = parts[1].strip()

        # ヘッダー行（"国民の祝日・休日月日,..."）はパースに失敗するので自然に弾かれる
        iso = _to_iso_date(raw_date)
        if not iso:
            continue
        out.append((iso, name))

    return out


def _to_iso_date(s):
    """'YYYY/M/D' or 'YYYY-M-D' -> 'YYYY-MM-DD'（不正なら None）。"""
    s = (s or "").strip().replace("-", "/")
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


if __name__ == "__main__":
    for row in _fetch_cao_holidays()[:10]:
        print(row)
