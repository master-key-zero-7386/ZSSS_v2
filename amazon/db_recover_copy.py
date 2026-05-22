# ==========================================
# ファイル名: amazon/db_recover_copy.py
# 目的: DB破損・不整合発生時の緊急復旧用スクリプト
#       - 旧DB → 新DB へ特定テーブルのデータを安全にコピーするための手動ツール
#       - 本番処理では使用しないバックアップ専用ファイル
#       - 外部通信なし / APIアクセスなし（安全）
# ==========================================

import sqlite3
import os

# DBフォルダ
DB_DIR = r"C:\GoogleDrive\zsss_web\db"

# 旧DB（コピー元）
old_db = os.path.join(DB_DIR, "a_au_blacklist_brand.db")
# 新DB（コピー先）
new_db = os.path.join(DB_DIR, "a_au_blacklist_brand_2.db")

# --- 旧DBからデータを読み出し ---
old_conn = sqlite3.connect(old_db)
old_cur = old_conn.cursor()
old_cur.execute("SELECT id, Brand, Rank, note, JapanBrand, timestamp FROM blacklist_brand")
rows = old_cur.fetchall()
old_conn.close()

print(f"[INFO][US] {len(rows)} 件のデータを読み込みました")

# --- 新DBに書き込み ---
new_conn = sqlite3.connect(new_db)
new_cur = new_conn.cursor()

for row in rows:
    new_cur.execute("""
        INSERT INTO blacklist_brand (id, Brand, Rank, note, JapanBrand, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, row)

new_conn.commit()
new_conn.close()

print("[INFO] データ移行完了")


