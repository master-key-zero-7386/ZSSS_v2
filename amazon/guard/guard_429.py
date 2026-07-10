# =====================================================
# ファイル名: amazon/guard/guard_429.py
# 目的：HTTPステータスコード429用ファイル
# =====================================================

from datetime import datetime, timedelta
from amazon.db import get_conn

# --- ▼ SECTION 01: 429（ID単位で個別停止） ▼ ---
# DB上でブロック状態を共有する（プロセスをまたいでも429ブロックが有効になるように）
def _get_block_seconds():
    # 将来UI化前提
    return 8    # 暫定的に30秒保留 将来的にUIで変更可能にする

def block(user_id: int, endpoint: str):
    seconds = _get_block_seconds()
    until = datetime.utcnow() + timedelta(seconds=seconds)

    conn = get_conn("a_api_block_state.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO api_block_state (user_id, endpoint, blocked_until)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, endpoint)
        DO UPDATE SET blocked_until = excluded.blocked_until
    """, (user_id, endpoint, until.isoformat()))
    conn.commit()
    conn.close()

def is_blocked(user_id: int, endpoint: str) -> bool:
    conn = get_conn("a_api_block_state.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT blocked_until
        FROM api_block_state
        WHERE user_id = %s AND endpoint = %s
    """, (user_id, endpoint))
    row = cur.fetchone()

    if not row:
        conn.close()
        return False

    until = datetime.fromisoformat(row["blocked_until"])

    if datetime.utcnow() >= until:
        print(f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [429 RELEASE] user:{user_id} endpoint:{endpoint}")  # 429 再開ログ
        cur.execute("""
            DELETE FROM api_block_state
            WHERE user_id = %s AND endpoint = %s
        """, (user_id, endpoint))
        conn.commit()
        conn.close()
        return False

    conn.close()
    return True
