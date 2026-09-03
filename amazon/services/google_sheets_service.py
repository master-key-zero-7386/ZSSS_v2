# ==========================================
# ファイル名: amazon/services/google_sheets_service.py
# 目的: ORBIT（発注管理）が発送代行会社の「依頼書」シートを読み戻すための
#       Google OAuth（ユーザー自身のGoogleアカウント）・Sheets API連携
# ==========================================

import os
import re
import time
from datetime import datetime, timedelta

import requests

from amazon.db import get_conn

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

# Desktop app タイプのOAuthクライアントは http://localhost（任意のポート）へのリダイレクトが
# 登録不要で許可されるため、ZSSS自身のFlaskサーバーをそのままコールバック先にできる。
GOOGLE_REDIRECT_URI = "http://localhost:5001/orbit/google_oauth/callback"

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
# 依頼書シートの読み戻し（読取）に加え、ORBIT → 自分の管理シート（ZSSS_RAWタブ）への
# 書き出しも行うため読み書きスコープにする。※スコープ変更後は一度Google連携をやり直す必要がある
# （既存のrefresh_tokenは古いスコープのまま。/orbit/google_oauth/start を再実行して再同意）。
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# 依頼書スプレッドシートのURL・シート名はユーザー変更可能（orbit_dispatch_sheet_settings）。
# 未設定時のみのフォールバックとして、判明している値を初期値に使う。
DEFAULT_DISPATCH_SHEET_URL = "https://docs.google.com/spreadsheets/d/1w4lnuf9RxwKZaPHgJJ6QoRwgihgDF7WNc1W61PGWvn4/edit"
DEFAULT_DISPATCH_SHEET_NAME = "【発送確認用】依頼書"

# ORBIT → 管理シートへの書き出し先（スプレッドシートURL・タブ名）は必須。既定値は持たず、
# ユーザーが画面から明示的に設定する（未設定なら書き出しはエラーになる）。
DISPATCH_SHEET_FULL_COLUMN_RANGE = "A2:U"       # ヘッダー除く全列（絞り込んだ行範囲に対して使う）
DISPATCH_SHEET_KEY_COLUMN_RANGE = "A2:B"        # 事前スキャン用：N番号・依頼日の2列だけ（軽量）
DISPATCH_SHEET_RECENT_DAYS = 30                 # この日数より古い依頼日の行は取得しない

SPREADSHEET_ID_PATTERN = re.compile(r"/d/([a-zA-Z0-9_-]+)")


class GoogleAuthError(RuntimeError):
    """保存済みのrefresh_tokenが失効している等、再連携が必要な状態。
    ルート側は str(e) をそのままフロントに返すため、メッセージは日本語で操作案内まで含める。"""
    pass


def _parse_sheet_date(value: str):
    if not value:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def _extract_spreadsheet_id(url: str):
    if not url:
        return None
    match = SPREADSHEET_ID_PATTERN.search(url)
    return match.group(1) if match else url.strip()  # IDそのものを貼られた場合もそのまま使う


# --- ▼ SECTION 00: 依頼書シート設定の取得・保存 ▼ ---
def get_dispatch_sheet_settings(user_id: int) -> dict:
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT spreadsheet_url, sheet_name FROM orbit_dispatch_sheet_settings WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    return {
        "spreadsheet_url": (row["spreadsheet_url"] if row and row.get("spreadsheet_url") else DEFAULT_DISPATCH_SHEET_URL),
        "sheet_name": (row["sheet_name"] if row and row.get("sheet_name") else DEFAULT_DISPATCH_SHEET_NAME),
    }


def save_dispatch_sheet_settings(user_id: int, spreadsheet_url: str, sheet_name: str):
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO orbit_dispatch_sheet_settings (user_id, spreadsheet_url, sheet_name, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            spreadsheet_url = EXCLUDED.spreadsheet_url,
            sheet_name = EXCLUDED.sheet_name,
            updated_at = EXCLUDED.updated_at
    """, (user_id, spreadsheet_url, sheet_name, now, now))

    conn.commit()
    conn.close()


# --- ▼ SECTION 00-2: 書き出し先（管理シートのタブ）設定の取得・保存 ▼ ---
# 読み戻し用の依頼書シート設定と同じ1行（user_idユニーク）に相乗りで保存する。
# URL・タブ名とも既定値は持たない（未設定なら空文字を返し、画面はプレースホルダ表示のまま）。
def get_raw_sheet_settings(user_id: int) -> dict:
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT raw_spreadsheet_url, raw_sheet_name, raw_mirror_spreadsheet_url, raw_mirror_sheet_name "
        "FROM orbit_dispatch_sheet_settings WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    return {
        "spreadsheet_url": (row["raw_spreadsheet_url"] if row and row.get("raw_spreadsheet_url") else ""),
        "sheet_name": (row["raw_sheet_name"] if row and row.get("raw_sheet_name") else ""),
        # 代行会社シートへの直接ミラー書き込み先（未設定なら空＝ミラーしない）
        "mirror_spreadsheet_url": (row["raw_mirror_spreadsheet_url"] if row and row.get("raw_mirror_spreadsheet_url") else ""),
        "mirror_sheet_name": (row["raw_mirror_sheet_name"] if row and row.get("raw_mirror_sheet_name") else ""),
    }


def save_raw_sheet_settings(user_id: int, spreadsheet_url: str, sheet_name: str,
                            mirror_spreadsheet_url: str = "", mirror_sheet_name: str = ""):
    conn = get_conn("a_orbit_dispatch_sheet_settings.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO orbit_dispatch_sheet_settings
            (user_id, raw_spreadsheet_url, raw_sheet_name, raw_mirror_spreadsheet_url, raw_mirror_sheet_name, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            raw_spreadsheet_url = EXCLUDED.raw_spreadsheet_url,
            raw_sheet_name = EXCLUDED.raw_sheet_name,
            raw_mirror_spreadsheet_url = EXCLUDED.raw_mirror_spreadsheet_url,
            raw_mirror_sheet_name = EXCLUDED.raw_mirror_sheet_name,
            updated_at = EXCLUDED.updated_at
    """, (user_id, spreadsheet_url, sheet_name, mirror_spreadsheet_url, mirror_sheet_name, now, now))

    conn.commit()
    conn.close()


# --- ▼ SECTION 01: 認可URL生成 ▼ ---
def build_authorization_url(redirect_uri: str = None) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri or GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SHEETS_SCOPE,
        "access_type": "offline",   # refresh_tokenを取得するために必須
        "prompt": "consent",        # 毎回同意画面を出してrefresh_tokenを確実に取得
    }
    query = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in params.items())
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


# --- ▼ SECTION 02: 認可コード → トークン交換 ▼ ---
# redirect_uriは認可リクエスト時に使ったものと完全一致している必要がある（Googleの仕様）。
# Tailscale等で複数端末からアクセスする運用があるため、呼び出し元(ルート)でアクセス元ホストから
# 動的に組み立てたものを渡す（未指定時のみ従来のlocalhost固定にフォールバック）。
def exchange_code_for_tokens(code: str, redirect_uri: str = None) -> dict:
    resp = requests.post(GOOGLE_TOKEN_ENDPOINT, data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri or GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


# --- ▼ SECTION 03: トークン保存（refresh_tokenは初回のみ返るので、無ければ既存を保持） ▼ ---
def save_tokens(user_id: int, token_data: dict):
    conn = get_conn("a_google_oauth_tokens.db")
    cur = conn.cursor()
    now = datetime.utcnow()
    expires_at = (now + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if refresh_token:
        cur.execute("""
            INSERT INTO google_oauth_tokens (user_id, access_token, refresh_token, expires_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
        """, (user_id, access_token, refresh_token, expires_at, now.isoformat(), now.isoformat()))
    else:
        # refresh_tokenが返らなかった場合（再認可等）は既存のrefresh_tokenを保持
        cur.execute("""
            UPDATE google_oauth_tokens
            SET access_token = %s, expires_at = %s, updated_at = %s
            WHERE user_id = %s
        """, (access_token, expires_at, now.isoformat(), user_id))

    conn.commit()
    conn.close()


# 失効した（再連携が必要な）トークン行を消す。次回の連携状態チェックで「未連携」＝再連携ボタン表示に戻す。
def clear_tokens(user_id: int):
    conn = get_conn("a_google_oauth_tokens.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM google_oauth_tokens WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()


# --- ▼ SECTION 04: 有効なaccess_tokenの取得（期限切れなら自動更新） ▼ ---
def get_valid_access_token(user_id: int):
    conn = get_conn("a_google_oauth_tokens.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT access_token, refresh_token, expires_at FROM google_oauth_tokens WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row or not row.get("refresh_token"):
        return None

    expires_at = row.get("expires_at")
    if expires_at:
        try:
            still_valid = datetime.fromisoformat(expires_at) > datetime.utcnow() + timedelta(seconds=60)
        except ValueError:
            still_valid = False
    else:
        still_valid = False

    if still_valid:
        return row["access_token"]

    # --- 期限切れ：refresh_tokenで再取得 ---
    resp = requests.post(GOOGLE_TOKEN_ENDPOINT, data={
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": row["refresh_token"],
        "grant_type": "refresh_token",
    })

    if resp.status_code >= 400:
        # 4xx（invalid_grant等）は保存済みrefresh_tokenの失効。スコープ変更・同意画面のテスト期限切れ・
        # ユーザーによる取消などが原因で、リトライしても直らない。死んだ行を消して再連携へ誘導する。
        # 5xx（Google側の一時障害）は行を残し、次回リトライで回復する余地を残す。
        if resp.status_code < 500:
            clear_tokens(user_id)
        raise GoogleAuthError(
            "Google連携の有効期限が切れています。"
            "発注管理タブの「Google再連携」からGoogleアカウントを連携し直してください。"
        )

    token_data = resp.json()
    save_tokens(user_id, token_data)
    return token_data.get("access_token")


# --- ▼ SECTION 05: 接続状態の確認 ▼ ---
def is_connected(user_id: int) -> bool:
    conn = get_conn("a_google_oauth_tokens.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT refresh_token FROM google_oauth_tokens WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return bool(row and row.get("refresh_token"))


# refresh_tokenの行があるか（is_connected）だけでなく、実際にアクセストークンを更新できるかまで確認する。
# 失効していれば get_valid_access_token 側で行が消えるので、以後は is_connected も False に戻る。
def has_working_connection(user_id: int) -> bool:
    if not is_connected(user_id):
        return False
    try:
        return bool(get_valid_access_token(user_id))
    except GoogleAuthError:
        return False
    except requests.RequestException:
        # ネットワーク不調などの一時的な失敗で「未連携」に落とさない（行はまだ生きている扱い）
        return True


# --- ▼ SECTION 06: シート範囲の取得（IMPORTRANGEと同じ発想） ▼ ---
def fetch_sheet_range(user_id: int, spreadsheet_id: str, sheet_range: str,
                      value_render_option: str = None) -> list:
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise RuntimeError("Googleアカウントが未接続です（要OAuth連携）")

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{requests.utils.quote(sheet_range)}"
    # UNFORMATTED_VALUE を指定すると数値/真偽はJSONの数値・boolのまま返る（既定のFORMATTED_VALUEは
    # 全部文字列化される）。ZSSS_RAW→代行会社シートのミラーで型を保つのに使う。
    if value_render_option:
        url += f"?valueRenderOption={value_render_option}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    return resp.json().get("values", [])


def append_sheet_values(user_id: int, spreadsheet_id: str, sheet_range: str, values: list,
                        insert_data_option: str = "OVERWRITE") -> dict:
    """values.append。update と違いグリッド行数を自動拡張するので、行数上限(既定1000)を気にせず
    まるごと書ける。事前に clear した上で range=タブ名!A1 を渡せば1行目から詰めて書き込まれる。"""
    if not values:
        return {}
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise RuntimeError("Googleアカウントが未接続です（要OAuth連携）")

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{requests.utils.quote(sheet_range)}:append"
        f"?valueInputOption=RAW&insertDataOption={insert_data_option}"
    )
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"values": values},
    )
    _raise_for_sheets_write_error(resp)
    return resp.json()


# --- ▼ SECTION 06-2: シート範囲への書き込み・クリア（ZSSS_RAWタブ出力用） ▼ ---
# valueInputOption=RAW: JAN・トラッキング番号・電話番号など桁数の多い数字文字列を
# Sheetsが数値/日付/数式に勝手に変換しないよう、送った文字列をそのまま入れる。
def _raise_for_sheets_write_error(resp):
    if resp.ok:
        return

    if resp.status_code == 403:
        raise RuntimeError(
            "書き込み権限がありません。スコープ変更後の再連携が必要です"
            "（発注管理タブの『Google再連携』からやり直してください）。"
        )

    # Google APIのエラー本文（{"error":{"message":"Unable to parse range: ZSSS_RAW", ...}}）を拾って
    # 「タブ名が違う」「シートが見つからない」等を切り分けられるようにする。
    detail = ""
    try:
        detail = ((resp.json() or {}).get("error") or {}).get("message") or ""
    except ValueError:
        detail = (resp.text or "")[:300]

    if resp.status_code == 400 and "parse range" in detail.lower():
        raise RuntimeError(
            f"タブが見つかりません（{detail}）。書き出し先スプレッドシートに指定タブ名が存在するか、"
            f"URLとタブを作ったシートが一致しているか確認してください。"
        )
    if resp.status_code == 404:
        raise RuntimeError("スプレッドシートが見つかりません。書き出し先URLを確認してください。")

    raise RuntimeError(f"Sheets API エラー（HTTP {resp.status_code}）: {detail or resp.reason}")


def update_sheet_values(user_id: int, spreadsheet_id: str, sheet_range: str, values: list) -> dict:
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise RuntimeError("Googleアカウントが未接続です（要OAuth連携）")

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{requests.utils.quote(sheet_range)}?valueInputOption=RAW"
    )
    resp = requests.put(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"values": values},
    )
    _raise_for_sheets_write_error(resp)
    return resp.json()


def batch_update_sheet_values(user_id: int, spreadsheet_id: str, data: list) -> dict:
    """複数の範囲を1リクエストでまとめて書き込む（N番一致の行だけ上書きする用途）。
    data = [{"range": "'ZSSS_RAW'!A5:BE5", "values": [[...]]}, ...]。
    valueInputOption=RAW は update_sheet_values と同じ理由（数字文字列をそのまま入れる）。
    """
    if not data:
        return {}
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise RuntimeError("Googleアカウントが未接続です（要OAuth連携）")

    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        json={"valueInputOption": "RAW", "data": data},
    )
    _raise_for_sheets_write_error(resp)
    return resp.json()


def clear_sheet_values(user_id: int, spreadsheet_id: str, sheet_range: str) -> dict:
    access_token = get_valid_access_token(user_id)
    if not access_token:
        raise RuntimeError("Googleアカウントが未接続です（要OAuth連携）")

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{requests.utils.quote(sheet_range)}:clear"
    )
    resp = requests.post(url, headers={"Authorization": f"Bearer {access_token}"})
    _raise_for_sheets_write_error(resp)
    return resp.json()


# --- ▼ SECTION 07: 依頼書シートの直近分取得 ▼ ---
# シート全体（数千行）を毎回取得すると重いため、まずA・B列（N番号・依頼日）だけを軽量取得して
# 「直近30日以内の依頼日が始まる行」を特定し、そこから末尾までだけを全列で取得する。
# 通常30日あれば発送〜到着まで完了しているはず、という前提。
def _fetch_recent_dispatch_rows(user_id: int, spreadsheet_id: str, sheet_name: str, days: int = DISPATCH_SHEET_RECENT_DAYS) -> dict:
    header_rows = fetch_sheet_range(user_id, spreadsheet_id, f"{sheet_name}!A1:U1")
    header = header_rows[0] if header_rows else []

    key_rows = fetch_sheet_range(user_id, spreadsheet_id, f"{sheet_name}!{DISPATCH_SHEET_KEY_COLUMN_RANGE}")
    if not key_rows:
        return {"header": header, "rows": []}

    cutoff = datetime.utcnow() - timedelta(days=days)
    start_index = len(key_rows)  # 見つからなければ「該当なし」

    for i, row in enumerate(key_rows):
        date_str = row[1] if len(row) > 1 else None
        parsed = _parse_sheet_date(date_str)
        if parsed and parsed >= cutoff:
            start_index = i
            break

    if start_index >= len(key_rows):
        return {"header": header, "rows": []}

    start_row_number = start_index + 2  # key_rows[0] はシートの2行目に対応
    data_rows = fetch_sheet_range(user_id, spreadsheet_id, f"{sheet_name}!A{start_row_number}:U")

    # 末尾には「N番号だけ自動採番済みで依頼日(B列)が未入力」の空行が含まれることがあるため除外する
    data_rows = [row for row in data_rows if len(row) > 1 and row[1]]

    return {"header": header, "rows": data_rows}


def fetch_dispatch_sheet_preview(user_id: int) -> dict:
    settings = get_dispatch_sheet_settings(user_id)
    spreadsheet_id = _extract_spreadsheet_id(settings["spreadsheet_url"])
    return _fetch_recent_dispatch_rows(user_id, spreadsheet_id, settings["sheet_name"])
