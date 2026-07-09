# ==========================================
# ファイル名: amazon/admin_settings.py
# 目的: 管理者設定
# ==========================================

from amazon.db import get_conn

DB_NAME = "a_admin_settings.db"

def _get_conn(base_dir):
    return get_conn(DB_NAME)


def save_admin_setting(base_dir, key, value):
    conn = _get_conn(base_dir)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO admin_settings (key, value)
        VALUES (%s, %s)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()


def get_admin_setting(base_dir, key, default=None):
    conn = _get_conn(base_dir)
    cur = conn.cursor()
    cur.execute("SELECT value FROM admin_settings WHERE key = %s", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default

