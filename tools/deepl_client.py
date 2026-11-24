import os

import requests

# DeepL API（文書管理の定型文を日本語へ翻訳する用）。
# キーは各PCの .env の DEEPL_API_KEY（gitには入らないので、運用PC・ATLASそれぞれに手で入れる）。
# 無料版のキーは末尾が ":fx" で、無料版専用のURLへ送る必要がある。

_FREE_URL = "https://api-free.deepl.com/v2/translate"
_PRO_URL = "https://api.deepl.com/v2/translate"
_TIMEOUT_SEC = 20


class DeepLError(Exception):
    """画面にそのまま出せる日本語のメッセージを持つ例外。"""


def translate_to_japanese(text: str) -> str:
    if not (text or "").strip():
        return ""

    key = (os.getenv("DEEPL_API_KEY") or "").strip()
    if not key:
        raise DeepLError("DEEPL_API_KEY が .env にありません（追加後はアプリの再起動が必要です）。")

    url = _FREE_URL if key.endswith(":fx") else _PRO_URL
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"DeepL-Auth-Key {key}"},
            data={"text": text, "target_lang": "JA", "preserve_formatting": "1"},
            timeout=_TIMEOUT_SEC,
        )
    except requests.RequestException as e:
        raise DeepLError(f"DeepLに接続できませんでした：{e}")

    if resp.status_code == 403:
        raise DeepLError("DeepLのAPIキーが正しくありません（.env の DEEPL_API_KEY を確認してください）。")
    if resp.status_code == 456:
        raise DeepLError("DeepLの今月の無料枠（50万文字）を使い切りました。")
    if resp.status_code == 429:
        raise DeepLError("DeepLへの送信が多すぎます。少し待ってから「翻訳し直す」を押してください。")
    if resp.status_code != 200:
        raise DeepLError(f"DeepLの翻訳に失敗しました（HTTP {resp.status_code}）。")

    try:
        return "".join(t.get("text", "") for t in resp.json().get("translations", []))
    except ValueError:
        raise DeepLError("DeepLから想定外の応答が返りました。")
