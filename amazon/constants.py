# =====================================================
# ファイル名: amazon/constants.py
# 目的：ZSSSで使用する共通パス（設定ファイル・アップロード先）を一括管理
# =====================================================

import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GPT_KEY_PATH = os.path.join(BASE_DIR, "gpt_key", "gpt_key.txt")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
