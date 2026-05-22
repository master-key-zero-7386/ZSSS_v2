# ==========================================
# ファイル名: amazon/admin_settings.py
# 目的: 管理者設定 
# ==========================================

import os
import sqlite3

DB_NAME = "a_admin_settings.db"

def _get_conn(base_dir):
    path = os.path.join(base_dir, DB_NAME)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    return conn


def save_admin_setting(base_dir, key, value):
    conn = _get_conn(base_dir)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO admin_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def get_admin_setting(base_dir, key, default=None):
    conn = _get_conn(base_dir)
    cur = conn.cursor()
    cur.execute("SELECT value FROM admin_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

