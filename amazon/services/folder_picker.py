# ==========================================
# ファイル名: amazon/services/folder_picker.py
# 目的: 設定画面の「参照」ボタン用のフォルダ選択サポート。
#   - list_subdirs / make_dir : ブラウザ内フォルダブラウザ（どの端末からでも使える）。
#     アプリが動いているPCのフォルダ階層をJSONで返す／新規フォルダを作る。
#   - pick_folder_dialog : ネイティブのフォルダ選択ダイアログ（アプリと同じPCで開いている時だけ有効。旧方式）。
# ==========================================

import os
import string
import subprocess
import sys
import threading

# ダイアログは一度に1つだけ。2個目以降は待たせず即エラーにして、
# Flask のワーカースレッドが「開きっぱなしのダイアログ待ち」で溜まらないようにする。
_DIALOG_LOCK = threading.Lock()

_DIALOG_SCRIPT = r"""
import sys
try:
    import tkinter as tk
    from tkinter import filedialog
    initial = sys.argv[1] if len(sys.argv) > 1 else ""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    kw = {"title": "フォルダを選択"}
    if initial and __import__("os").path.isdir(initial):
        kw["initialdir"] = initial
    path = filedialog.askdirectory(**kw)
    root.destroy()
    sys.stdout.buffer.write((path or "").encode("utf-8"))
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
"""


def pick_folder_dialog(initial: str = "", timeout: int = 60) -> str:
    """フォルダ選択ダイアログを出して、選ばれた絶対パスを返す。キャンセル時は ""。
    ダイアログを出せない環境・既に別のダイアログが開いている・時間切れなら RuntimeError。

    ダイアログはアプリが動いているPCの画面に出る。別端末から開いている場合は出ないので、
    timeout 内に誰も操作しなければ RuntimeError（パスは手入力してもらう）。"""
    if getattr(sys, "frozen", False):
        raise RuntimeError("この実行形態ではフォルダ選択ダイアログを開けません。パスを直接入力してください。")

    if not _DIALOG_LOCK.acquire(blocking=False):
        raise RuntimeError("フォルダ選択ダイアログが既に開いています。運用PCの画面で操作するか閉じてください。")

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DIALOG_SCRIPT, initial or ""],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "フォルダ選択がタイムアウトしました"
            "（ダイアログは運用PCの画面に出ます。別端末から開いている場合はパスを直接入力してください）。"
        )
    except OSError as e:
        raise RuntimeError(f"フォルダ選択ダイアログを起動できませんでした: {e}")
    finally:
        _DIALOG_LOCK.release()

    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(
            "フォルダ選択ダイアログを開けませんでした"
            "（アプリが動いているPCで開いているか確認してください）。"
            + (f" [{detail}]" if detail else "")
        )

    path = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return os.path.normpath(path) if path else ""


# --- ▼ ブラウザ内フォルダブラウザ（どの端末からでも使える） ▼ ---
# アプリが動いているPCのフォルダ階層を返す。login_required 相当のルートからのみ呼ぶ想定
# （社内ツール・ログイン必須のため、ファイルシステム構造の露出は許容）。ディレクトリのみ・
# ファイル内容は一切返さない。

def _win_drives():
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(root):
            drives.append(root)
    return drives


def list_subdirs(path: str) -> dict:
    """path 直下のサブフォルダ一覧を返す。path が空ならドライブ一覧。"""
    raw = (path or "").strip()
    if not raw:
        return {"path": "", "parent": None, "is_drives": True, "dirs": _win_drives()}

    abspath = os.path.abspath(raw)
    if not os.path.isdir(abspath):
        raise RuntimeError(f"フォルダが見つかりません: {abspath}")

    dirs = []
    try:
        for name in os.listdir(abspath):
            full = os.path.join(abspath, name)
            try:
                if os.path.isdir(full):
                    dirs.append(name)
            except OSError:
                pass
    except PermissionError:
        raise RuntimeError(f"アクセスできません: {abspath}")
    dirs.sort(key=str.lower)

    parent = os.path.dirname(abspath.rstrip("/\\"))
    # ドライブ直下（C:\ / C:）の親はドライブ一覧（空文字）へ
    if not parent or parent == abspath or (len(parent) == 2 and parent[1] == ":"):
        parent = ""
    return {"path": abspath, "parent": parent, "is_drives": False, "dirs": dirs}


_BAD_NAME_CHARS = set(r'\/:*?"<>|')


def make_dir(parent: str, name: str) -> str:
    """parent の中に name フォルダを作って絶対パスを返す。"""
    parent = os.path.abspath((parent or "").strip())
    name = (name or "").strip()
    if not os.path.isdir(parent):
        raise RuntimeError(f"作成先フォルダが見つかりません: {parent}")
    if not name or any(c in _BAD_NAME_CHARS for c in name):
        raise RuntimeError("フォルダ名に使えない文字が含まれています")
    target = os.path.join(parent, name)
    os.makedirs(target, exist_ok=True)
    return target
