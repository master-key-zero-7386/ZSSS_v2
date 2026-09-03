# ==========================================================
# ファイル名： backfill_buyer_history_asin.py
# 目的： 買い手履歴（orbit_buyer_history）の既存行に asin を後埋めする
#        1回限りのメンテ用スクリプト。asin 列追加前にインポート済みの
#        旧データが対象。
#
# 使い方：
#   python backfill_buyer_history_asin.py --dry-run   # 件数だけ確認（更新しない）
#   python backfill_buyer_history_asin.py             # 実際に UPDATE する
#
# 解決ロジックは orbit_order_service._resolve_asin と共通：
#   listed_items の SKU→ASIN 対応 → 無ければ SKU からの抽出（他社ツール別の
#   命名規則パターン）。どちらでも特定できない行は asin=NULL のまま残す。
# ==========================================================

import sys

from amazon.db import get_conn
from amazon.services.orbit_order_service import (
    _load_listed_items_asin_map,
    _resolve_asin,
)


def main(dry_run=False):
    conn = get_conn("a_orbit_buyer_history.db")  # postgresモードではdb_name指定は無視され、単一DBに接続される
    cur = conn.cursor()

    cur.execute(
        "SELECT id, user_id, sku FROM orbit_buyer_history "
        "WHERE asin IS NULL AND sku IS NOT NULL"
    )
    rows = cur.fetchall()

    asin_maps = {}  # user_id -> {sku: asin}（listed_items突き合わせ用。ユーザー単位で1回だけ読む）
    resolved = 0
    unresolved = 0

    for row in rows:
        user_id = row["user_id"]
        if user_id not in asin_maps:
            asin_maps[user_id] = _load_listed_items_asin_map(user_id)

        asin = _resolve_asin(row["sku"], asin_maps[user_id])
        if not asin:
            unresolved += 1
            continue

        resolved += 1
        if not dry_run:
            cur.execute(
                "UPDATE orbit_buyer_history SET asin = %s WHERE id = %s",
                (asin, row["id"]),
            )

    if not dry_run:
        conn.commit()
    conn.close()

    tail = "  [DRY-RUN 変更なし]" if dry_run else "  -> UPDATE済み"
    print(
        f"[DONE] 対象(asin NULL & sku あり): {len(rows)}  "
        f"解決: {resolved}  未解決(SKUから特定不可): {unresolved}{tail}"
    )


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
