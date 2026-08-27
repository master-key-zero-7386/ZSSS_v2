# -*- coding: utf-8 -*-
# 仕入価格(home_price)がなぜ更新されないか調査用の使い捨てスクリプト
# 使い方（実機で）:
#   python check_home_pricing.py B00WV06KGA
#   ※ ASINを省略すると marketplaces 設定だけ表示

import os
import sys

from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    dbname=os.getenv("PG_DATABASE"),
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

asin = sys.argv[1].strip().upper() if len(sys.argv) > 1 else None

print("=" * 70)
print("[1] marketplaces 設定（HOME Pricing のゲート）")
print("=" * 70)
cur.execute("""
    SELECT user_id, country_code, home_flag,
           enable_home_pricing, h_pricing_ttl_days,
           enable_region_pricing, r_pricing_ttl_days
    FROM marketplaces
    ORDER BY user_id, home_flag DESC, country_code
""")
for r in cur.fetchall():
    print(f"  user={r['user_id']} {r['country_code']:<3} home_flag={r['home_flag']} "
          f"| enable_home_pricing={r['enable_home_pricing']} "
          f"h_pricing_ttl_days={r['h_pricing_ttl_days']} "
          f"| enable_region_pricing={r['enable_region_pricing']} "
          f"r_pricing_ttl_days={r['r_pricing_ttl_days']}")
print("  → CA行の enable_home_pricing が 0 なら背景では仕入価格を一切更新していない")

print()
print("=" * 70)
print("[2] bg_scan_settings（1サイクルの処理上限・NULLは無制限=危険）")
print("=" * 70)
cur.execute("SELECT * FROM bg_scan_settings WHERE id = 1")
row = cur.fetchone()
if row:
    for k in ("ttl_limit_home_pricing", "ttl_limit_region_pricing",
              "ttl_limit_home_catalog", "ttl_limit_region_catalog",
              "ttl_cycle_sleep_sec", "ttl_sleep_sec_pricing"):
        print(f"  {k} = {row.get(k)}")
else:
    print("  bg_scan_settings に id=1 の行が無い")

if asin:
    print()
    print("=" * 70)
    print(f"[3] pricing_cache（{asin} の仕入価格を実際にAPI取得した時刻）")
    print("=" * 70)
    cur.execute("""
        SELECT asin, home_marketplace_id, region_marketplace_id,
               home_updated_at, h_pricing_ttl_at,
               r_pricing_ttl_at, updated_at
        FROM pricing_cache
        WHERE asin = %s
    """, (asin,))
    rows = cur.fetchall()
    if not rows:
        print("  該当なし")
    for r in rows:
        print(f"  home_updated_at   = {r['home_updated_at']}   ← ¥10,980 を取得した時刻")
        print(f"  h_pricing_ttl_at  = {r['h_pricing_ttl_at']}   ← 次回再取得の起点")
        print(f"  region_mp={r['region_marketplace_id']} home_mp={r['home_marketplace_id']}")

    print()
    print("=" * 70)
    print(f"[4] listed_items（{asin} の各行の状態）")
    print("=" * 70)
    cur.execute("""
        SELECT user_id, region_marketplace_id, status, information_status,
               inactive_reason, home_price, min_price, max_price, final_price,
               ttl_stop_status, override_price, override_stock_zero,
               h_pricing_ttl_at, r_pricing_ttl_at, updated_at
        FROM listed_items
        WHERE asin = %s
    """, (asin,))
    rows = cur.fetchall()
    if not rows:
        print("  該当なし")
    for r in rows:
        print(f"  user={r['user_id']} region_mp={r['region_marketplace_id']} "
              f"status={r['status']} info={r['information_status']} reason={r['inactive_reason']}")
        print(f"    home_price={r['home_price']} min={r['min_price']} max={r['max_price']} final={r['final_price']}")
        print(f"    ttl_stop_status={r['ttl_stop_status']} override_price={r['override_price']} "
              f"override_stock_zero={r['override_stock_zero']}")
        print(f"    h_pricing_ttl_at={r['h_pricing_ttl_at']}  updated_at={r['updated_at']}")
        if r['ttl_stop_status'] in ('1', 1) or r['override_price'] is not None or r['override_stock_zero'] is not None:
            print("    ★この行はTTL対象から除外される条件を持っている")

conn.close()
print()
print("done")
