# ========================================
# ファイル名: files_check_2.py
# 目的: region が「2文字国コード」として使われている可能性のある行を抽出
# ========================================

import sqlite3
import os

DB_PATH = r"C:\zsss_web\db\a_marketplaces.db"  # 必要ならパスだけ調整

if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"DB not found: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== PRAGMA table_info(marketplaces) ===")
cur.execute("PRAGMA table_info(marketplaces);")
rows = cur.fetchall()

for r in rows:
    # (cid, name, type, notnull, dflt_value, pk)
    print(r)

conn.close()
print("=== END ===")