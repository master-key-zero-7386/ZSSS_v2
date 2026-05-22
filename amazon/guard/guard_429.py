# =====================================================
# ファイル名: amazon/guard/guard_429.py
# 目的：HTTPステータスコード429用ファイル
# =====================================================

from datetime import datetime, timedelta

# --- ▼ SECTION 01: 429（ID単位で個別停止） ▼ ---
# 開発用メモリブロック管理
_BLOCK_MAP = {}

def _get_block_seconds():
    # 将来UI化前提
    return 8    # 暫定的に30秒保留 将来的にUIで変更可能にする

def block(user_id: int, endpoint: str):
    seconds = _get_block_seconds()
    _BLOCK_MAP[(user_id, endpoint)] = datetime.utcnow() + timedelta(seconds=seconds)

def is_blocked(user_id: int, endpoint: str) -> bool:
    until = _BLOCK_MAP.get((user_id, endpoint))
    if not until:
        return False
    if datetime.utcnow() >= until:
        print(f"[{(datetime.utcnow() + timedelta(hours=9)).strftime('%H:%M:%S')}] [429 RELEASE] user:{user_id} endpoint:{endpoint}")  # 429 再開ログ
        del _BLOCK_MAP[(user_id, endpoint)]
        return False
    return True
