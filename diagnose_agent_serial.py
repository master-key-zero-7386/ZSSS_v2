# -*- coding: utf-8 -*-
# ==========================================
# N番（agent_serial_no）一括振り直し事故の調査用（読み取り専用）
#   - orbit_orders を一切書き換えない
#   - 運用PCの venv で実行する:  ..\python_env\venv\Scripts\python.exe diagnose_agent_serial.py
#   - .env の PG_* をそのまま使う（= 実行したマシンのDBを見る）
# 出力:
#   1) updated_at が完全一致する行のかたまり（= set_serial 1回で書き換わったバッチ）
#   2) 直近の大きいバッチの中身（N番順）
#   3) N番の健全性チェック（NULL / 重複 / 欠番）
#   4) 全注文のスナップショットを CSV に書き出し（agent_serial_snapshot_YYYYMMDD_HHMMSS.csv）
# ==========================================

import csv
import sys
from datetime import datetime

# Windowsの既定コンソール（cp932）だと商品名の一部文字で print が落ちるため、
# 出力を UTF-8 / 文字化け許容にしておく（調査目的なので表示崩れは許容）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from amazon.db import get_conn


def main(user_id: int):
    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()

    print(f"=== user_id={user_id} ===\n")

    cur.execute("SELECT COUNT(*) AS n FROM orbit_orders WHERE user_id=%s", (user_id,))
    total = cur.fetchone()["n"]
    print(f"orbit_orders 件数: {total}\n")

    # 1) updated_at が完全一致する行のかたまり（set_serial は1回の処理で全対象行に同一 updated_at を書く）
    print("--- (1) updated_at が一致する行のかたまり（多い＝一括処理の跡） ---")
    cur.execute(
        """
        SELECT updated_at, COUNT(*) AS n,
               MIN(agent_serial_no) AS min_n, MAX(agent_serial_no) AS max_n
        FROM orbit_orders
        WHERE user_id=%s AND updated_at IS NOT NULL
        GROUP BY updated_at
        HAVING COUNT(*) > 1
        ORDER BY updated_at DESC
        LIMIT 20
        """,
        (user_id,),
    )
    batches = cur.fetchall()
    if not batches:
        print("  （まとまった一括更新の跡は見つかりませんでした）")
    for b in batches:
        print(f"  {b['updated_at']}  {b['n']}件  N番 {b['min_n']}〜{b['max_n']}")
    print()

    # 2) 直近の一番大きいバッチの中身
    if batches:
        target = max(batches, key=lambda r: (r["n"], r["updated_at"]))
        print(f"--- (2) 最大バッチ {target['updated_at']}（{target['n']}件）の中身（N番順） ---")
        cur.execute(
            """
            SELECT agent_serial_no, order_id, order_item_id, purchase_date, created_at,
                   LEFT(COALESCE(product_name,''), 40) AS product_name
            FROM orbit_orders
            WHERE user_id=%s AND updated_at=%s
            ORDER BY agent_serial_no NULLS LAST, id
            """,
            (user_id, target["updated_at"]),
        )
        for r in cur.fetchall():
            print(f"  N{r['agent_serial_no']}  {r['order_id']}  item={r['order_item_id']}  "
                  f"注文日={r['purchase_date']}  {r['product_name']}")
        print()

    # 3) N番の健全性
    print("--- (3) N番の健全性 ---")
    cur.execute("SELECT COUNT(*) AS n FROM orbit_orders WHERE user_id=%s AND agent_serial_no IS NULL", (user_id,))
    print(f"  N番 NULL: {cur.fetchone()['n']}件")
    cur.execute(
        """
        SELECT agent_serial_no, COUNT(*) AS n
        FROM orbit_orders
        WHERE user_id=%s AND agent_serial_no IS NOT NULL
        GROUP BY agent_serial_no HAVING COUNT(*) > 1
        ORDER BY agent_serial_no
        """,
        (user_id,),
    )
    dups = cur.fetchall()
    print(f"  N番の重複: {len(dups)}種"
          + (f"  例: {[d['agent_serial_no'] for d in dups[:15]]}" if dups else ""))
    cur.execute(
        "SELECT MIN(agent_serial_no) AS lo, MAX(agent_serial_no) AS hi "
        "FROM orbit_orders WHERE user_id=%s AND agent_serial_no IS NOT NULL",
        (user_id,),
    )
    rng = cur.fetchone()
    if rng["lo"] is not None:
        cur.execute(
            "SELECT DISTINCT agent_serial_no FROM orbit_orders "
            "WHERE user_id=%s AND agent_serial_no IS NOT NULL",
            (user_id,),
        )
        present = {r["agent_serial_no"] for r in cur.fetchall()}
        missing = [n for n in range(rng["lo"], rng["hi"] + 1) if n not in present]
        print(f"  N番の範囲: {rng['lo']}〜{rng['hi']}  欠番: {len(missing)}個"
              + (f"  例: {missing[:20]}" if missing else ""))
    print()

    # 4) 全注文スナップショットを CSV へ
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"agent_serial_snapshot_{stamp}.csv"
    cur.execute(
        """
        SELECT id, agent_serial_no, order_id, order_item_id, purchase_date,
               created_at, updated_at, product_name
        FROM orbit_orders
        WHERE user_id=%s
        ORDER BY agent_serial_no NULLS LAST, id
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "agent_serial_no", "order_id", "order_item_id",
                    "purchase_date", "created_at", "updated_at", "product_name"])
        for r in rows:
            w.writerow([r["id"], r["agent_serial_no"], r["order_id"], r["order_item_id"],
                        r["purchase_date"], r["created_at"], r["updated_at"], r["product_name"]])
    print(f"--- (4) 全{len(rows)}件のスナップショットを書き出しました: {out}")
    print("    （このCSVは復元前の証拠として保管してください）")

    conn.close()


if __name__ == "__main__":
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    main(uid)
