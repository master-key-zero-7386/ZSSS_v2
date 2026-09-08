# -*- coding: utf-8 -*-
# ==========================================
# N番（agent_serial_no）一括振り直し事故の復元:
#   「管理シート（ZSSS_RAW 等）」に書き出し済みの (注文明細ID → 旧N番) を正として
#   orbit_orders.agent_serial_no を書き戻す。
#
# 前提: 事故後にまだ「管理シートへ書出」をしていない（＝シートは事故前の対応を保持）。
#
# 使い方（運用PCの venv で）:
#   1) 管理シートの該当タブを「ファイル → ダウンロード → CSV」で保存（例 sheet.csv）
#   2) まず dry-run（DBは一切変更しない。差分だけ表示）:
#        ..\python_env\venv\Scripts\python.exe restore_agent_serial_from_sheet.py sheet.csv
#   3) 差分を確認して問題なければ実行:
#        ..\python_env\venv\Scripts\python.exe restore_agent_serial_from_sheet.py sheet.csv --apply
#
#   user_id を変えるとき:  restore_agent_serial_from_sheet.py sheet.csv --user 1 [--apply]
#
# 安全策:
#   - 既定は dry-run。--apply を付けたときだけ UPDATE する。
#   - 旧N番が複数の注文明細IDに重複していたら中断（並びが壊れたシートを取り込まないため）。
#   - 1トランザクションで全UPDATE。1件でも失敗したら全ロールバック。
#   - 実行前後の該当行を before/after CSV に書き出す。
# ==========================================

import csv
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from amazon.db import get_conn

# シート見出しは「注文明細ID ／ order_item_id」「N番 ／ agent_serial_no」の形（_raw_header_label）。
# 表記ゆれに備えて部分一致で列を探す。
ITEM_ID_HINTS = ("order_item_id", "注文明細id", "明細id", "order-item-id")
SERIAL_HINTS = ("agent_serial_no", "n番", "n-no", "n_no")


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("　", "")


def _find_col(fieldnames, hints):
    for i, fn in enumerate(fieldnames):
        n = _norm(fn)
        if any(h in n for h in hints):
            return i
    return None


def _parse_serial(v):
    v = (v or "").strip()
    if not v:
        return None
    # "N5153" のような接頭辞付きも許容
    digits = "".join(ch for ch in v if ch.isdigit())
    return int(digits) if digits else None


def load_sheet_mapping(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        # 先頭にタイトル行や空行が入ることがあるので、見出しらしい行を探す
        rows = list(csv.reader(f))
    header_idx = None
    item_col = serial_col = None
    for idx, row in enumerate(rows[:20]):
        ic = _find_col(row, ITEM_ID_HINTS)
        sc = _find_col(row, SERIAL_HINTS)
        if ic is not None and sc is not None:
            header_idx, item_col, serial_col = idx, ic, sc
            break
    if header_idx is None:
        sys.exit("エラー: シートCSVから「注文明細ID」列と「N番」列の見出しを特定できませんでした。")

    print(f"見出し行: {header_idx + 1}行目 / 注文明細ID列={item_col + 1} / N番列={serial_col + 1}")

    mapping = {}
    dupe_item = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(item_col, serial_col):
            continue
        item_id = (row[item_col] or "").strip()
        serial = _parse_serial(row[serial_col])
        if not item_id or serial is None:
            continue
        if item_id in mapping and mapping[item_id] != serial:
            dupe_item.append(item_id)
        mapping[item_id] = serial

    if dupe_item:
        print(f"注意: シート内で同じ注文明細IDに複数のN番: {dupe_item[:10]}")
    return mapping


def main():
    args = [a for a in sys.argv[1:]]
    if not args or args[0].startswith("-"):
        sys.exit("使い方: restore_agent_serial_from_sheet.py <sheet.csv> [--user N] [--apply]")
    sheet_path = args[0]
    apply = "--apply" in args
    user_id = 1
    if "--user" in args:
        user_id = int(args[args.index("--user") + 1])

    print(f"=== 復元 user_id={user_id}  mode={'APPLY' if apply else 'DRY-RUN'} ===\n")

    sheet_map = load_sheet_mapping(sheet_path)
    print(f"シートから読めた (注文明細ID→旧N番): {len(sheet_map)} 件\n")

    # 旧N番の重複チェック（別々の明細が同じ旧N番を指す＝並びが壊れている）
    seen = {}
    collisions = []
    for item_id, serial in sheet_map.items():
        if serial in seen:
            collisions.append((serial, seen[serial], item_id))
        else:
            seen[serial] = item_id
    if collisions:
        print("!! 旧N番が重複しています。シートの並びが壊れている可能性があるため中断します:")
        for s, a, b in collisions[:20]:
            print(f"   N{s}: {a} と {b}")
        sys.exit(1)

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, order_item_id, order_id, agent_serial_no, purchase_date, "
        "LEFT(COALESCE(product_name,''),40) AS product_name "
        "FROM orbit_orders WHERE user_id=%s",
        (user_id,),
    )
    db_rows = {r["order_item_id"]: r for r in cur.fetchall()}
    print(f"DBの注文明細: {len(db_rows)} 件\n")

    changes = []       # (order_item_id, old_db_serial, new_serial, row)
    same = 0
    not_in_db = []
    for item_id, new_serial in sheet_map.items():
        r = db_rows.get(item_id)
        if not r:
            not_in_db.append(item_id)
            continue
        if r["agent_serial_no"] == new_serial:
            same += 1
        else:
            changes.append((item_id, r["agent_serial_no"], new_serial, r))

    in_db_not_in_sheet = [iid for iid in db_rows if iid not in sheet_map]

    print(f"--- 変更なし: {same} 件 ---")
    print(f"--- 復元する（現N番 → 旧N番）: {len(changes)} 件 ---")
    for item_id, cur_s, new_s, r in sorted(changes, key=lambda x: (x[2] is None, x[2])):
        print(f"  N{cur_s} → N{new_s}   {r['order_id']}  item={item_id}  "
              f"{r['purchase_date']}  {r['product_name']}")

    if not_in_db:
        print(f"\n--- シートにあるがDBに無い注文明細ID: {len(not_in_db)} 件 ---")
        for iid in not_in_db[:30]:
            print(f"  {iid}")

    if in_db_not_in_sheet:
        print(f"\n--- DBにあるがシートに無い（＝前回書出以降の新規注文。要手動採番）: {len(in_db_not_in_sheet)} 件 ---")
        for iid in in_db_not_in_sheet:
            r = db_rows[iid]
            print(f"  現N{r['agent_serial_no']}  {r['order_id']}  item={iid}  "
                  f"{r['purchase_date']}  {r['product_name']}")

    # 復元後にDB内でN番が重複しないか（新規行の現N番と衝突しないか）を事前チェック
    final_serial_by_item = {}
    for iid, r in db_rows.items():
        final_serial_by_item[iid] = r["agent_serial_no"]
    for item_id, _cur_s, new_s, _r in changes:
        final_serial_by_item[item_id] = new_s
    rev = {}
    dup_after = []
    for iid, s in final_serial_by_item.items():
        if s is None:
            continue
        if s in rev:
            dup_after.append((s, rev[s], iid))
        else:
            rev[s] = iid
    if dup_after:
        print(f"\n!! 復元するとN番が重複します（{len(dup_after)} 件）。"
              f"新規注文の現N番と旧N番がぶつかっています。--apply する前に対処が必要です:")
        for s, a, b in dup_after[:20]:
            print(f"   N{s}: {a} と {b}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"restore_plan_{stamp}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["order_item_id", "order_id", "current_serial", "restore_to_serial", "purchase_date", "product_name"])
        for item_id, cur_s, new_s, r in changes:
            w.writerow([item_id, r["order_id"], cur_s, new_s, r["purchase_date"], r["product_name"]])
    print(f"\n変更計画を restore_plan_{stamp}.csv に保存しました。")

    if not apply:
        print("\nDRY-RUN のためDBは変更していません。問題なければ --apply を付けて再実行してください。")
        conn.close()
        return

    if dup_after:
        print("\nN番重複が解消されていないため中断します（--apply を実行しません）。")
        conn.close()
        return

    now = datetime.utcnow().isoformat()
    try:
        for item_id, _cur_s, new_s, _r in changes:
            cur.execute(
                "UPDATE orbit_orders SET agent_serial_no=%s, updated_at=%s "
                "WHERE user_id=%s AND order_item_id=%s",
                (new_s, now, user_id, item_id),
            )
        conn.commit()
        print(f"\n完了: {len(changes)} 件のN番を復元しました。")
    except Exception as e:
        conn.rollback()
        print(f"\nエラーのため全ロールバックしました: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
