# -*- coding: utf-8 -*-
# ============================================================================
# INACTIVE なのに Amazon 側で出品が生き残っている在庫を一括で取り下げる使い捨て
# スクリプト。今回の修正(INACTIVE→出品取り下げの一本化)より前に INACTIVE 化され、
# listing_status がまだ 'REMOVED' になっていない listed 商品が対象。
#
# 実機（運用PC / ATLAS PC それぞれ）で実行すること。DBは環境ごとに独立。
#
#   python backfill_remove_inactive_offers.py --dry-run      # 対象一覧だけ表示
#   python backfill_remove_inactive_offers.py                # 実際に取り下げ
#   python backfill_remove_inactive_offers.py --limit 50     # 先頭50件だけ
#   python backfill_remove_inactive_offers.py --sleep 3      # 1件ごと3秒待つ(既定2秒)
# ============================================================================

import os
import sys
import time

from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()

DRY_RUN = "--dry-run" in sys.argv


def _arg_val(name, default):
    if name in sys.argv:
        try:
            return type(default)(sys.argv[sys.argv.index(name) + 1])
        except (IndexError, ValueError):
            pass
    return default


LIMIT = _arg_val("--limit", 0)          # 0 = 全件
SLEEP_SEC = _arg_val("--sleep", 2.0)


def fetch_targets():
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST"), port=os.getenv("PG_PORT"),
        user=os.getenv("PG_USER"), password=os.getenv("PG_PASSWORD"),
        dbname=os.getenv("PG_DATABASE"),
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sql = """
        SELECT li.user_id,
               li.asin,
               li.sku,
               li.region_marketplace_id,
               li.inactive_reason,
               mp.country_code
        FROM listed_items li
        INNER JOIN marketplaces mp
            ON li.user_id = mp.user_id
            AND li.region_marketplace_id = mp.marketplace_id
        WHERE LOWER(li.status) = 'listed'
          AND li.information_status = 'INACTIVE'
          AND COALESCE(li.listing_status, '') <> 'REMOVED'
          AND li.sku IS NOT NULL
          AND li.sku <> ''
        ORDER BY li.user_id, mp.country_code, li.asin
    """
    if LIMIT:
        sql += f"\n        LIMIT {int(LIMIT)}"
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    return rows


def _print_reason_summary(rows):
    counts = {}
    for r in rows:
        key = (r["inactive_reason"] or "(空)")
        counts[key] = counts.get(key, 0) + 1
    print("理由別の内訳（listed かつ INACTIVE かつ 未取り下げ）:")
    for reason, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {reason:<24} {n:>5} 件")
    print("-" * 70)


def main():
    rows = fetch_targets()
    print(f"対象 {len(rows)} 件"
          f"{' (DRY-RUN: 取り下げは実行しません)' if DRY_RUN else ''}")
    print("-" * 70)
    _print_reason_summary(rows)
    for r in rows:
        print(f"  user={r['user_id']} {r['country_code']:<3} asin={r['asin']} "
              f"sku={r['sku']} reason={r['inactive_reason']}")
    print("-" * 70)

    if DRY_RUN or not rows:
        return

    # AmazonAdapter が flask.session を参照するため、アプリ/リクエストコンテキスト内で回す
    from app import app
    from amazon.routes.routes_pricing_v2 import _ensure_amazon_offer_removed

    ok = 0
    with app.test_request_context():
        for i, r in enumerate(rows, 1):
            print(f"[{i}/{len(rows)}] user={r['user_id']} {r['country_code']} "
                  f"asin={r['asin']} ...", flush=True)
            try:
                _ensure_amazon_offer_removed(
                    user_id=r["user_id"],
                    asin=r["asin"],
                    country_code=r["country_code"],
                    region_marketplace_id=r["region_marketplace_id"],
                )
                ok += 1
            except Exception as e:
                print(f"    ERROR: {e}", flush=True)
            time.sleep(SLEEP_SEC)

    # 取り下げ結果は listing_status='REMOVED' で確認できる
    remaining = fetch_targets()
    print("=" * 70)
    print(f"処理呼び出し {ok}/{len(rows)} 件 / 未 'REMOVED' 残 {len(remaining)} 件")
    print("残りは delete がエラー(429等)で弾かれた分。時間をおいて再実行するか、")
    print("通常のTTL巡回でも 'REMOVED' になるまで自動再送されます。")


if __name__ == "__main__":
    main()
