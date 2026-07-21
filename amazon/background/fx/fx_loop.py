# ==========================================
# ファイル名: amazon/background/fx/fx_loop.py
# 目的: 通貨更新用loop
# ==========================================

from datetime import datetime, timedelta
from amazon.db import get_conn

# --- ▼ SECTION 01: ENV LOAD ▼ ---
from dotenv import load_dotenv
import os

# fx_secret.env を読み込む
load_dotenv()

FX_API_KEY = os.getenv("FX_API_KEY")

# --- ▼ SECTION 02: FX LOOP ENTRY POINT ▼ ---
def run_fx_loop(app):
    """
    通貨更新メインループ
    """

    import time
    from datetime import timezone, timedelta

    # loop_count = 0  # LOOPカウント処理用

    # === ▼ 以下は FX 動作制御設定値（FIRSTと同系）将来UI操作に変更する ▼ ===
    FX_LOOP_SLEEP_SEC = 5.0  # ループ間待機  
    # === ▲ ここまで  ▲ ===    

    while True:  # ←ここを修正
        # loop_count += 1  # カウント処理用
        # print(f"[FX][CYCLE_START] cycle={loop_count}") # カウント処理用

        JST = timezone(timedelta(hours=9))
        # print(f"[FX][LOOP][ALIVE] {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}")

        try:

            last_updated = get_last_fx_updated_at()
            interval_hours = get_fx_update_interval_hours()
            now = datetime.utcnow()

            # 初回
            if last_updated is None:
                print("[FX] First run - update required")
                update_fx_last_updated_at()
                print("[FX] last_updated_at set")

            # 更新判定
            elif now - last_updated >= timedelta(hours=interval_hours):
                print("[FX] Interval exceeded - update required")

                # --- master から通貨一覧取得 ---
                conn = get_conn("a_marketplaces_master.db")
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT currency FROM marketplaces_master")
                base_currencies = [row["currency"] for row in cur.fetchall()] 
                conn.close()

                # --- 各通貨を基準に取得＆保存 ---
                for base_currency in base_currencies:
                    rates = fetch_fx_rates(base_currency)
                    save_fx_rates(base_currency, rates)

                update_fx_last_updated_at()
                print("[FX] last_updated_at updated")

            else:
                pass
                # print("[FX] No update needed")

        except Exception as e:
            import traceback
            print("### FX LOOP ERROR ###")
            print(e)
            traceback.print_exc()
            app.logger.error("### FX LOOP ERROR ###", exc_info=True)

        # print(f"[FX][CYCLE_END] cycle={loop_count}") # カウント処理用

        time.sleep(FX_LOOP_SLEEP_SEC)  

# --- ▼ SECTION 03: 最終更新時刻取得 ▼ ---
def get_last_fx_updated_at():
    db_name = "a_fx.db"
    conn = get_conn(db_name) 
    cur = conn.cursor()    

    cur.execute("SELECT last_updated_at FROM fx_settings LIMIT 1")
    row = cur.fetchone()

    conn.close()

    if not row or not row["last_updated_at"]:
        return None

    return datetime.fromisoformat(row["last_updated_at"])

# --- ▼ SECTION 04: 更新間隔取得 ▼ ---
def get_fx_update_interval_hours():
    db_name = "a_fx.db"
    conn = get_conn(db_name) 
    cur = conn.cursor()

    cur.execute("SELECT update_interval_hours FROM fx_settings LIMIT 1")
    row = cur.fetchone()

    conn.close()

    if not row or row["update_interval_hours"] is None:
        return 24  # デフォルト

    return int(row["update_interval_hours"])

# --- ▼ SECTION 05: 最終更新時刻更新 ▼ ---
def update_fx_last_updated_at():
    db_name = "a_fx.db"
    conn = get_conn(db_name) 
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    cur.execute("""
        UPDATE fx_settings
        SET last_updated_at = %s
    """, (now,))

    conn.commit()
    conn.close()

# --- ▼ SECTION 06: FX取得（ExchangeRate-API） ---
def fetch_fx_rates(base_currency: str, provider_name="exchangerate_api"):
    import requests

    if provider_name != "exchangerate_api":
        raise ValueError("Unsupported FX provider")

    if not FX_API_KEY:
        raise RuntimeError("FX_API_KEY not set")

    url = f"https://v6.exchangerate-api.com/v6/{FX_API_KEY}/latest/{base_currency}"

    res = requests.get(url, timeout=10)
    data = res.json()

    if data.get("result") != "success":
        raise RuntimeError("FX API response invalid")

    return data.get("conversion_rates", {})

# --- ▼ SECTION 07: FX保存処理（UPSERT） ▼ ---
def save_fx_rates(base_currency: str, rates: dict):
    conn = get_conn("a_fx.db")
    cur = conn.cursor()

    for target_currency, rate in rates.items():
        cur.execute(
            """
            INSERT INTO fx_rates (base_currency, target_currency, rate, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(base_currency, target_currency)
            DO UPDATE SET
                rate = excluded.rate,
                updated_at = excluded.updated_at
            """,
            (
                base_currency,
                target_currency,
                1 / rate,
                datetime.utcnow().isoformat()
            )
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    print(fetch_fx_rates())    