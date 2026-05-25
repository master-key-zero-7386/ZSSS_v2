# ==========================================
# ファイル名: zsss_web/dump_schema.py
# 目的:# スキーマ確認用スクリプト
# ==========================================
import sys
import os
import sqlite3


def dump_schema(db_path: str) -> None:
    print("=" * 60)
    print(f"DB: {db_path}")
    if not os.path.exists(db_path):
        print("  !! ファイルが見つかりません")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # テーブル一覧
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row["name"] for row in cur.fetchall()]

    if not tables:
        print("  (テーブルがありません)")
        conn.close()
        return

    for table in tables:
        print(f"\n[Table] {table}")
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        for col in cols:
            # cid, name, type だけ見ればOK
            print(f"  {col['cid']:2d} | {col['name']} | {col['type']}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python dump_schema.py <db1> <db2> ...")
        sys.exit(1)

    for path in sys.argv[1:]:
        dump_schema(path)
