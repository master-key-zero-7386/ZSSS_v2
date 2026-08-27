# -*- coding: utf-8 -*-
# update_home_pricing の「API取得後〜home_price書込前」を、キャッシュ済み
# 生レスポンスに対して再現し、例外が出る箇所を特定する使い捨てスクリプト。
#   python debug_home_select.py B00WV06KGA
import os
import sys
import json
import traceback

from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()

asin = (sys.argv[1] if len(sys.argv) > 1 else "B00WV06KGA").strip().upper()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"), port=os.getenv("PG_PORT"),
    user=os.getenv("PG_USER"), password=os.getenv("PG_PASSWORD"),
    dbname=os.getenv("PG_DATABASE"),
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# --- 1. キャッシュ済み生レスポンス ---
cur.execute("""
    SELECT home_offers_json, home_updated_at, home_marketplace_id
    FROM pricing_cache WHERE asin = %s AND home_offers_json IS NOT NULL
    LIMIT 1
""", (asin,))
pc = cur.fetchone()
if not pc:
    print("pricing_cache に home_offers_json が無い")
    sys.exit(1)

raw = json.loads(pc["home_offers_json"])
print(f"home_updated_at = {pc['home_updated_at']}")
offers = raw.get("payload", {}).get("Offers", [])
print(f"errors = {raw.get('errors')}")
print(f"Offers 件数 = {len(offers)}")
print("-" * 60)

# --- 2. offer_filter_rules(ALL) ---
cur.execute("""
    SELECT * FROM offer_filter_rules
    WHERE user_id = 1 AND UPPER(country_code) = 'ALL' LIMIT 1
""")
rules = dict(cur.fetchone() or {})
print("rules =", rules)
print("-" * 60)

# --- 3. 実コードで normalize → select を実行 ---
try:
    from amazon.adapters.pricing_normalized_adapter import NormalizedPricingAdapter
    from amazon.adapters.pricing_rules_adapter import PricingRulesAdapter

    normalizer = NormalizedPricingAdapter(parent_adapter=None)
    normalized = normalizer.normalize_home_offers(raw)
    print(f"normalize OK: {len(normalized)} offers")
    for i, o in enumerate(normalized):
        print(f"  [{i}] price={o['price_amount']} ship={o['shipping_amount']} "
              f"seller={o['seller_id']} buybox={o['is_buybox_winner']} "
              f"rating%={o['rating_percent']} ratingN={o['rating_count']} "
              f"handling_d={o['handling_time_days']} future={o['is_future_offer']} "
              f"ships_from={o['ships_from_country']}")

    print("-" * 60)
    adapter_rules = PricingRulesAdapter(rules)
    result_select = adapter_rules.select_home_cost_offer(normalized)
    print("select OK:", json.dumps(result_select, ensure_ascii=False, default=str, indent=2))

    sel = result_select.get("selected") if result_select else None
    if sel:
        price = float(sel.get("price_amount") or 0)
        ship = float(sel.get("shipping_amount") or 0)
        pts = float(sel.get("points_amount") or 0)
        hp = price + ship
        if rules.get("consider_points") == 1:
            hp -= pts
        print(f"\n=> 本来 home_price に書かれる値 = {hp}")
    else:
        print("\n=> selected が None（全offerがフィルタ落ち or offer0件）")
        print("   → update_home_pricing は home_price=None / HOME_NO_OFFERS で INACTIVE 化するはず")

except Exception:
    print("\n★ここで例外 ↓↓↓")
    traceback.print_exc()

conn.close()
