# -*- coding: utf-8 -*-
# ==========================================
# 2026-09-09 の N番一括振り直し事故 専用の復元スクリプト（1回限り）
#
# 事故: set_serial が orbit_orders 全89件の agent_serial_no を
#       updated_at=2026-09-08T23:32:09.604861 で一括上書き（N5130始まり→N5149始まりにズレ＋並び回転）。
#
# 正解: 管理シート「自分用管理シート」書出タブの (注文明細ID → 旧N番)。
#       本スクリプトに88... 89件そのまま埋め込み済み。ユーザーが貼ったシート内容から起こし、
#       運用DBの現状（diagnose 出力）と突き合わせて
#         - 89件が過不足なく一致
#         - アンカー 167134004653321 → N5130
#         - 復元後のN番 5130..5218 が全ユニーク（重複なし）
#       を確認済み。
#
# 使い方（運用PCの venv）:
#   dry-run（DB変更なし。差分だけ表示＋before CSV出力）:
#     C:\zsss\python_env\venv\Scripts\python.exe C:\zsss\zsss_web\restore_nban_20260909.py
#   実行（1トランザクションでUPDATE。失敗時は全ロールバック）:
#     C:\zsss\python_env\venv\Scripts\python.exe C:\zsss\zsss_web\restore_nban_20260909.py --apply
#
#   user_id を変える場合: --user N（既定 1）
# ==========================================

import csv
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from amazon.db import get_conn

# 注文明細ID(order_item_id) -> 正しいN番(agent_serial_no)
MAPPING = {
    "167134004653321": 5130, "167159218611081": 5131, "167160526919161": 5132,
    "167205164700321": 5133, "167205164700361": 5134, "167234312056681": 5135,
    "167246233857441": 5136, "15605778691565": 5137, "15606218425645": 5138,
    "167253331528401": 5139, "167269052737881": 5140, "167303799909561": 5141,
    "167318921007321": 5142, "15609133163165": 5143, "15613250781925": 5144,
    "167376159175721": 5145, "15614762680965": 5146, "15614785033325": 5147,
    "15623289956485": 5148, "167490561063041": 5149, "15627820963445": 5150,
    "167539251828561": 5151, "15635928525925": 5152, "15638776103325": 5153,
    "15638776103365": 5154, "15638725271925": 5155, "15641644112965": 5156,
    "167769610906081": 5157, "15643572728645": 5158, "167806690306161": 5159,
    "15645687928565": 5160, "15647741001205": 5161, "15649028085765": 5162,
    "15648233981525": 5163, "167889578123321": 5164, "15654414900285": 5165,
    "15655835534845": 5166, "15656261254085": 5167, "15656749977045": 5168,
    "15657018190925": 5169, "168036654983281": 5170, "15670033693485": 5171,
    "15675523541685": 5172, "15676238504605": 5173, "168195501366841": 5174,
    "15678747629365": 5175, "168250495559841": 5176, "15691534418085": 5177,
    "15693255858645": 5178, "168316892208441": 5179, "168332331045921": 5180,
    "15698057148845": 5181, "168377086364601": 5182, "15702390168885": 5183,
    "15703267835125": 5184, "168390012808601": 5185, "15709194717045": 5186,
    "15743155976125": 5187, "15747118537045": 5188, "15750214380725": 5189,
    "168666052873481": 5190, "168687040560961": 5191, "168692190886241": 5192,
    "15753621146925": 5193, "15755491994405": 5194, "168726491672361": 5195,
    "168744695673241": 5196, "15757183187085": 5197, "15759731846765": 5198,
    "168832338712121": 5199, "168902828103241": 5200, "168908232941201": 5201,
    "15773277518925": 5202, "168942107049201": 5203, "15785630896805": 5204,
    "169008072576721": 5205, "15793053597405": 5206, "15794550948045": 5207,
    "15796901537645": 5208, "15797061861605": 5209, "169158798476001": 5210,
    "169169101563881": 5211, "169170164207961": 5212, "169198182313521": 5213,
    "15799518998885": 5214, "15801205541645": 5215, "15801464600125": 5216,
    "15801766075125": 5217, "15802240397045": 5218,
}

ANCHOR_ITEM = "167134004653321"
ANCHOR_SERIAL = 5130


def die(msg):
    print("\n!! 中断:", msg)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    user_id = 1
    if "--user" in args:
        user_id = int(args[args.index("--user") + 1])

    print(f"=== N番復元 2026-09-09  user_id={user_id}  mode={'APPLY' if apply else 'DRY-RUN'} ===\n")

    # --- 埋め込みマッピングの自己検査 ---
    if len(MAPPING) != 89:
        die(f"MAPPING 件数が89でない: {len(MAPPING)}")
    serials = sorted(MAPPING.values())
    if serials != list(range(5130, 5219)):
        die(f"MAPPING のN番が 5130..5218 の連番でない: {serials[:5]}...{serials[-5:]}")
    if MAPPING.get(ANCHOR_ITEM) != ANCHOR_SERIAL:
        die(f"アンカー不一致: {ANCHOR_ITEM} -> {MAPPING.get(ANCHOR_ITEM)} (期待 {ANCHOR_SERIAL})")

    conn = get_conn("a_orbit_orders.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT id, order_item_id, agent_serial_no, order_id, purchase_date, "
        "LEFT(COALESCE(product_name,''),40) AS product_name "
        "FROM orbit_orders WHERE user_id=%s",
        (user_id,),
    )
    db = {r["order_item_id"]: r for r in cur.fetchall()}
    print(f"DBの注文明細: {len(db)} 件 / マッピング: {len(MAPPING)} 件")

    # --- DBとマッピングが過不足なく一致するか ---
    only_db = sorted(set(db) - set(MAPPING))
    only_map = sorted(set(MAPPING) - set(db))
    if only_db:
        print(f"\nDBにあるがマッピングに無い（{len(only_db)}件）:")
        for i in only_db:
            r = db[i]
            print(f"  現N{r['agent_serial_no']}  {r['order_id']}  item={i}  {r['purchase_date']}  {r['product_name']}")
    if only_map:
        print(f"\nマッピングにあるがDBに無い（{len(only_map)}件）: {only_map}")
    if only_db or only_map:
        conn.close()
        die("DBとマッピングの注文明細IDが一致しません。手動確認が必要です。")

    # --- 差分 ---
    changes = []  # (id, item, cur_serial, new_serial, row)
    for item, new_s in MAPPING.items():
        r = db[item]
        if r["agent_serial_no"] != new_s:
            changes.append((r["id"], item, r["agent_serial_no"], new_s, r))

    # 復元後のN番が全ユニークか
    after = {item: db[item]["agent_serial_no"] for item in db}
    for item, new_s in MAPPING.items():
        after[item] = new_s
    if len(set(after.values())) != len(after):
        from collections import Counter
        dup = [n for n, c in Counter(after.values()).items() if c > 1]
        conn.close()
        die(f"復元するとN番が重複します: {dup}")

    print(f"\n変更なし: {len(db) - len(changes)} 件 / 復元する: {len(changes)} 件\n")
    print("--- 現N番 → 正N番 ---")
    for _id, item, cS, nS, r in sorted(changes, key=lambda x: x[3]):
        print(f"  N{cS} → N{nS}   {r['order_id']}  item={item}  {r['purchase_date']}  {r['product_name']}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    before_csv = f"nban_before_{stamp}.csv"
    with open(before_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "order_item_id", "order_id", "current_serial", "restore_to", "purchase_date", "product_name"])
        for _id, item, cS, nS, r in changes:
            w.writerow([_id, item, r["order_id"], cS, nS, r["purchase_date"], r["product_name"]])
    print(f"\n変更前の該当行を {before_csv} に保存しました。")

    if not apply:
        print("\nDRY-RUN のためDBは変更していません。内容を確認して問題なければ --apply を付けて再実行してください。")
        conn.close()
        return

    now = datetime.utcnow().isoformat()
    try:
        for _id, item, _cS, nS, _r in changes:
            cur.execute(
                "UPDATE orbit_orders SET agent_serial_no=%s, updated_at=%s WHERE id=%s AND user_id=%s",
                (nS, now, _id, user_id),
            )
        # コミット前に最終検証
        cur.execute(
            "SELECT agent_serial_no, COUNT(*) c FROM orbit_orders WHERE user_id=%s "
            "GROUP BY agent_serial_no HAVING COUNT(*) > 1",
            (user_id,),
        )
        post_dup = cur.fetchall()
        if post_dup:
            conn.rollback()
            die(f"UPDATE後にN番重複を検出したためロールバックしました: {[dict(x) for x in post_dup]}")
        cur.execute(
            "SELECT agent_serial_no FROM orbit_orders WHERE user_id=%s AND order_item_id=%s",
            (user_id, ANCHOR_ITEM),
        )
        got = cur.fetchone()["agent_serial_no"]
        if got != ANCHOR_SERIAL:
            conn.rollback()
            die(f"UPDATE後のアンカーが {got}（期待 {ANCHOR_SERIAL}）。ロールバックしました。")

        conn.commit()
        print(f"\n完了: {len(changes)} 件のN番を復元しました（アンカー N{ANCHOR_SERIAL} 確認済み）。")
    except SystemExit:
        raise
    except Exception as e:
        conn.rollback()
        print(f"\nエラーのため全ロールバックしました: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
