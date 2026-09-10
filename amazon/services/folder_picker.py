# ==========================================
# ファイル名: amazon/services/folder_picker.py
# 目的: 設定画面の「参照」ボタン用。アプリが動いているPC側で
#       ネイティブのフォルダ選択ダイアログを出し、選ばれた絶対パスを返す。
#
# 制約:
#   - ブラウザからは実フォルダパスが取れない（type=file はファイル内容しか渡さない）ため、
#     サーバー側でダイアログを出すしかない。よってブラウザとアプリが同じPCのときだけ有効
#     （ダイアログはアプリが動いているPCの画面に出る）。
#   - Tk はスレッド安全でないので、Flask のワーカースレッドから直接呼ばず、
#     別プロセス（自分の main スレッド）で tkinter を起動する。
# ==========================================

import os
import subprocess
import sys

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


def pick_folder_dialog(initial: str = "", timeout: int = 180) -> str:
    """フォルダ選択ダイアログを出して、選ばれた絶対パスを返す。キャンセル時は ""。
    ダイアログを出せない環境なら RuntimeError。"""
    if getattr(sys, "frozen", False):
        raise RuntimeError("この実行形態ではフォルダ選択ダイアログを開けません。パスを直接入力してください。")

    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DIALOG_SCRIPT, initial or ""],
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("フォルダ選択がタイムアウトしました。")
    except OSError as e:
        raise RuntimeError(f"フォルダ選択ダイアログを起動できませんでした: {e}")

    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(
            "フォルダ選択ダイアログを開けませんでした"
            "（アプリが動いているPCで開いているか確認してください）。"
            + (f" [{detail}]" if detail else "")
        )

    path = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return os.path.normpath(path) if path else ""
