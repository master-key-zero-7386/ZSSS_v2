# ==========================================
# ファイル名: amazon/background/buybox/buybox_loop.py
# 目的: カート取得状況（自分がカートを取っている割合）を1日1回、国ごと・商品タイプごとに記録する常駐ループ
# ==========================================
#
# 1時間ごとに「今日（日本時間）の記録がまだ無い国」があるかを見て、あればその国だけ集計して残す。
# Amazon には問い合わせない（TTL で取ってある pricing_cache を読むだけ）。中身は
# amazon/services/buybox_stats_service.py。失敗しても次の回にやり直すだけで、他の処理は止めない。

import time
import traceback

from amazon.services.buybox_stats_service import run_daily_snapshot_if_needed

BUYBOX_LOOP_START_DELAY_SEC = 300.0  # 起動直後は TTL・first の立ち上がりを優先して少し待つ
BUYBOX_LOOP_SLEEP_SEC = 3600.0       # 1時間ごとに記録の要否を判定


# --- ▼ SECTION 01: エントリポイント ▼ ---
def run_buybox_loop(app):
    time.sleep(BUYBOX_LOOP_START_DELAY_SEC)
    while True:
        try:
            done = run_daily_snapshot_if_needed()
            if done:
                print(f"[BUYBOX] daily stats recorded: {done} country(s)")
        except Exception:
            print("[BUYBOX] daily stats ERROR")
            traceback.print_exc()
        time.sleep(BUYBOX_LOOP_SLEEP_SEC)
