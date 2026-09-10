# ==========================================
# ファイル名: amazon/services/orbit_receipt_import_service.py
# 目的: 発注管理・領収書列の「一括読込」— 受信フォルダに置かれた仕入れ領収書PDFを
#       注文番号で orbit_orders に照合し、N番ごとに
#       「N{N番}_YYMMDD_注文番号_仕入先.pdf」へリネームして保管先フォルダへ移す。
#       照合できた行は invoice_saved を立てる。照合できないPDFは受信フォルダに残す
#       （＝残ったファイルがそのまま「読めなかった／紐付かなかった」一覧になる）。
#
# 設計メモ:
#   - 照合キーはまずファイル名。Amazonの一括DLは
#     「20260302_Tax Invoice_249-4994965-6008618.pdf」形式で注文番号が入っている。
#     ファイル名で注文番号が取れないときだけ pypdf でPDF本文を読む（フォールバック）。
#   - 日付は ①ファイル名先頭の YYYYMMDD → ②照合行の procurement_date → ③注文日 の順。
#   - 仕入先名は orbit_orders の supplier_shop_name / supplier を使う
#     （Amazon領収書のファイル名は "Tax Invoice" で店名が入らないため）。
#   - 1注文に複数商品＝複数N番のときは N番ごとに同じPDFをコピーする（案B）。
#   - 重複: 保管先に同名かつ内容(SHA256)一致ならスキップ、内容違いなら "_(1)" を付ける。
#   - 1本でもコピー（またはスキップ）できたら元ファイルは受信フォルダから削除＝移動。
# ==========================================

import hashlib
import os
import re
import shutil
from datetime import datetime

from amazon.db import get_conn
from amazon.services.google_sheets_service import get_receipt_settings

# Amazon.co.jp の注文番号（xxx-xxxxxxx-xxxxxxx）。仕入れ領収書に必ず入っている前提。
ORDER_NO_RE = re.compile(r"\d{3}-\d{7}-\d{7}")

# ファイル名に使えない文字（Windows）。仕入先名のサニタイズ用。
_ILLEGAL_FS_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')

# ファイル名先頭の日付プレフィックス（20260302 / 2026-03-02 / 260302_ など）。
# 誤検出を避けるため、日付の直後に区切り文字（空白・_・-・.）が来ることを要求する。
_DATE_PREFIX_RE = re.compile(r"^\D*((?:20)?\d{2})[-/.]?(\d{2})[-/.]?(\d{2})(?=[ _\-.])")


def _normalize_hyphens(s: str) -> str:
    # 全角・各種ダッシュを ASCII ハイフンへ寄せてから注文番号を拾う
    return re.sub(r"[‐-―−－ー]", "-", s or "")


def extract_order_numbers(text: str) -> list:
    """text 中の Amazon 注文番号を出現順・重複なしで返す。"""
    if not text:
        return []
    cleaned = _normalize_hyphens(text)
    # "249 - 767924 - 7330226" のような空白入りも拾えるよう、ハイフン周りの空白を潰す
    cleaned = re.sub(r"\s*-\s*", "-", cleaned)
    seen = []
    for m in ORDER_NO_RE.findall(cleaned):
        if m not in seen:
            seen.append(m)
    return seen


def _extract_pdf_text(path: str) -> str:
    """pypdf でPDF本文テキストを抽出。未導入・画像PDF・失敗時は "" を返す。"""
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception:
        return ""


def _yymmdd_from_filename(name: str):
    m = _DATE_PREFIX_RE.match(name or "")
    if not m:
        return None
    yy, mm, dd = m.group(1)[-2:], m.group(2), m.group(3)
    if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
        return None
    return f"{yy}{mm}{dd}"


def _normalize_yymmdd(raw):
    """'2026-03-03' / '26/3/3' / '20260303' などを 'YYMMDD' に。ダメなら None。"""
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r"^(?:20)?(\d{2})[-/.](\d{1,2})[-/.](\d{1,2})$", s) \
        or re.match(r"^(?:20)?(\d{2})(\d{2})(\d{2})$", s)
    if not m:
        return None
    yy = m.group(1)
    mm = m.group(2).zfill(2)
    dd = m.group(3).zfill(2)
    if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
        return None
    return f"{yy}{mm}{dd}"


def _sanitize_supplier(s: str) -> str:
    s = _ILLEGAL_FS_CHARS.sub("", (s or "").strip())
    s = re.sub(r"\s+", " ", s).strip()
    return s[:40] if s else "shop"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_target(store_dir: str, filename: str, src_hash: str):
    """(target_path, action) を返す。action は "write"（新規書き込み）/ "skip"（同一物が既存）。
    同名で内容違いなら "_(1)", "_(2)" ... を試す。"""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    i = 0
    while True:
        path = os.path.join(store_dir, candidate)
        if not os.path.exists(path):
            return path, "write"
        try:
            if _sha256(path) == src_hash:
                return path, "skip"
        except OSError:
            pass
        i += 1
        candidate = f"{stem}_({i}){ext}"


def _load_order_index(user_id: int):
    """orbit_orders を注文番号→行リストの辞書に。
    supplier_order_number 優先、次点 order_id。"""
    conn = get_conn("a_orbit_orders.db")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT order_item_id, order_id, supplier_order_number, agent_serial_no,
                   supplier, supplier_shop_name, procurement_date, purchase_date
            FROM orbit_orders
            WHERE user_id = %s
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    by_supplier_no = {}
    by_order_id = {}
    for r in rows:
        for key in extract_order_numbers(r.get("supplier_order_number") or ""):
            by_supplier_no.setdefault(key, []).append(r)
        for key in extract_order_numbers(r.get("order_id") or ""):
            by_order_id.setdefault(key, []).append(r)
    return by_supplier_no, by_order_id


def _set_invoice_saved(user_id: int, order_item_ids) -> int:
    ids = list(order_item_ids)
    if not ids:
        return 0
    conn = get_conn("a_orbit_orders.db")
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute(
            """
            UPDATE orbit_orders
            SET invoice_saved = 1, updated_at = %s
            WHERE user_id = %s AND order_item_id = ANY(%s)
            """,
            (now, user_id, ids),
        )
        n = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n


def run_receipt_import(user_id: int) -> dict:
    settings = get_receipt_settings(user_id)
    inbox = (settings.get("inbox_dir") or "").strip()
    store = (settings.get("store_dir") or "").strip()

    if not inbox or not store:
        raise RuntimeError(
            "受信フォルダと保管先フォルダを設定してください"
            "（発注管理 → スプレッドシート連携 ファイルパス設定）。"
        )
    if not os.path.isdir(inbox):
        raise RuntimeError(f"受信フォルダが見つかりません: {inbox}")
    if not os.path.isdir(store):
        raise RuntimeError(f"保管先フォルダが見つかりません: {store}")

    pdfs = sorted(
        f for f in os.listdir(inbox)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(inbox, f))
    )

    by_supplier_no, by_order_id = _load_order_index(user_id)

    ok = 0
    skipped = 0
    failed = []
    created = []
    matched_items = set()

    for name in pdfs:
        src = os.path.join(inbox, name)

        # ① ファイル名から注文番号 → ② 取れなければPDF本文から
        candidates = extract_order_numbers(name)
        if not candidates:
            candidates = extract_order_numbers(_extract_pdf_text(src))

        rows = []
        matched_no = None
        for no in candidates:
            rows = by_supplier_no.get(no) or by_order_id.get(no) or []
            if rows:
                matched_no = no
                break

        if not rows:
            failed.append({"file": name, "reason": "注文番号を特定できない、またはZSSSに一致なし"})
            continue

        nban_set = {r.get("agent_serial_no") for r in rows}
        if any(n is None for n in nban_set):
            failed.append({"file": name, "reason": "照合先にN番未採番の行があります"})
            continue
        nbans = sorted(nban_set)

        yymmdd = (
            _yymmdd_from_filename(name)
            or _normalize_yymmdd(rows[0].get("procurement_date"))
            or _normalize_yymmdd(rows[0].get("purchase_date"))
        )
        if not yymmdd:
            failed.append({"file": name, "reason": "日付を決定できません（ファイル名・仕入日・注文日いずれも不可）"})
            continue

        try:
            src_hash = _sha256(src)
        except OSError as e:
            failed.append({"file": name, "reason": f"読み取り不可: {e}"})
            continue

        # N番ごとに1部ずつ。仕入先名はそのN番の行のもの（無ければ先頭行）を使う。
        wrote_any = False
        errored = False
        for nban in nbans:
            row = next((r for r in rows if r.get("agent_serial_no") == nban), rows[0])
            supplier = _sanitize_supplier(row.get("supplier_shop_name") or row.get("supplier") or "")
            fname = f"N{nban}_{yymmdd}_{matched_no}_{supplier}.pdf"
            target, action = _resolve_target(store, fname, src_hash)
            if action == "skip":
                skipped += 1
                wrote_any = True  # 既に保管済み → 元ファイルは消してよい
                continue
            try:
                shutil.copy2(src, target)
                ok += 1
                wrote_any = True
                created.append(os.path.basename(target))
            except OSError as e:
                failed.append({"file": name, "reason": f"コピー失敗: {e}"})
                errored = True
                break

        if errored:
            continue

        matched_items.update(r["order_item_id"] for r in rows)

        if wrote_any:
            try:
                os.remove(src)  # 全コピー完了 → 受信フォルダから除去（＝移動）
            except OSError:
                pass

    flagged = _set_invoice_saved(user_id, matched_items)

    return {
        "processed": len(pdfs),
        "ok": ok,
        "skipped": skipped,
        "failed": failed,
        "flagged_rows": flagged,
        "created": created,
    }
