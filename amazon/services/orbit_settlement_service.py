# ==========================================
# ファイル名: amazon/services/orbit_settlement_service.py
# 目的: ORBIT（注文管理）決済レポート（Settlement Report フラットファイルV2）の取込・集計
#   - SP-API（GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2）で自動取得、またはセラーセントラル
#     「過去の決済情報」→「フラットファイルV2」を手動アップロード
#   - 精算番号（settlement-id）単位で丸ごと入れ替えるので、何回取り込んでも二重にならない
#   - 明細は order_item_id（order-item-code）で注文管理の商品ごとの行と直接つながる
# ==========================================

import csv
import gzip
import io
import re
import threading
import time
from datetime import datetime

import requests
from psycopg2.extras import execute_values

from amazon.db import get_conn

SETTLEMENT_REPORT_TYPE = "GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2"

# どの環境（app.py の起動引数）でどの国の決済レポートをAPIで取るか。
# AUはATLASだけで扱う（ZSSSからAUのSP-APIには絶対に触らない）。devはAPIを叩かない。
SETTLEMENT_API_COUNTRIES = {
    "zsss": ("US", "CA"),
    "atlas": ("AU",),
}

# getReportDocument は 1分に1回程度しか呼べない（burstはあるが残量が見えない）。
# 429を出すと guard_429 で同じユーザーの他のSP-API（価格更新等）まで止まるので、最初から間隔を空ける。
DOCUMENT_INTERVAL_SEC = 61
QUOTA_RETRY_WAIT_SEC = 65
QUOTA_RETRY_MAX = 3


# --- ▼ SECTION 01: 日付・数値の正規化 ▼ ---
# 国（セラーセントラルの表示言語）で書式が違う：US「2026-10-08...」、CA「08.10.2026」、手動DL「2026-10-19T07:01:21+00:00」
def _norm_date(value):
    s = (value or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _to_float(value):
    s = (value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        # ヨーロッパ式（1.234,56）で来た場合
        try:
            return float(s.replace(".", "").replace(",", "."))
        except ValueError:
            return None


# --- ▼ SECTION 02: ファイル解析（API＝縦長形式／手動DL＝横長形式の両方） ▼ ---
# 縦長（API）：1行＝1金額。amount-type / amount-description / amount
# 横長（セラーセントラル手動DL）：金額の種類ごとに列が分かれている（price-type/price-amount 等）
WIDE_AMOUNT_COLUMNS = [
    # (金額列, 種類名の列, amount_type)
    ("price-amount", "price-type", "ItemPrice"),
    ("item-related-fee-amount", "item-related-fee-type", "ItemFees"),
    ("order-fee-amount", "order-fee-type", "OrderFees"),
    ("shipment-fee-amount", "shipment-fee-type", "ShipmentFees"),
    ("promotion-amount", "promotion-type", "Promotion"),
    ("direct-payment-amount", "direct-payment-type", "DirectPayment"),
    ("misc-fee-amount", None, "MiscFees"),
    ("other-fee-amount", "other-fee-reason-description", "OtherFees"),
    ("other-amount", "other-fee-reason-description", "other-transaction"),
]


def _item_base(raw: dict) -> dict:
    return {
        "transaction_type": (raw.get("transaction-type") or "").strip() or None,
        "order_id": (raw.get("order-id") or "").strip() or None,
        "order_item_id": (raw.get("order-item-code") or "").strip() or None,
        "adjustment_id": (raw.get("adjustment-id") or "").strip() or None,
        "sku": (raw.get("sku") or "").strip() or None,
        "marketplace_name": (raw.get("marketplace-name") or "").strip() or None,
        "posted_date": _norm_date(raw.get("posted-date")),
    }


def _items_from_row(raw: dict, is_long: bool) -> list:
    if is_long:
        amount = _to_float(raw.get("amount"))
        if amount is None:
            return []
        item = _item_base(raw)
        item["amount_type"] = (raw.get("amount-type") or "").strip() or None
        item["amount_description"] = (raw.get("amount-description") or "").strip() or None
        item["amount"] = amount
        return [item]

    items = []
    for amount_col, desc_col, amount_type in WIDE_AMOUNT_COLUMNS:
        amount = _to_float(raw.get(amount_col))
        if amount is None:
            continue
        item = _item_base(raw)
        item["amount_type"] = amount_type
        desc = (raw.get(desc_col) or "").strip() if desc_col else ""
        item["amount_description"] = desc or amount_type
        item["amount"] = amount
        items.append(item)
    return items


def parse_settlement_file(text: str) -> list:
    """1ファイルに複数の精算が入っていてもよい（ATLASからの書き出しファイル）。"""
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    fieldnames = reader.fieldnames or []
    if "settlement-id" not in fieldnames:
        raise ValueError("決済レポート（フラットファイルV2）の形式ではありません（settlement-id 列がありません）")
    is_long = "amount-type" in fieldnames
    if not is_long and "price-type" not in fieldnames:
        raise ValueError("決済レポートの列の形式を判別できません")

    settlements = {}
    order = []
    for raw in reader:
        sid = (raw.get("settlement-id") or "").strip()
        if not sid:
            continue
        s = settlements.get(sid)
        if s is None:
            s = {"settlement_id": sid, "items": []}
            settlements[sid] = s
            order.append(sid)
        # 精算のまとめ行（期間・入金日・入金額だけが入っていて、取引の種類が空）
        if raw.get("settlement-start-date") and not (raw.get("transaction-type") or "").strip():
            s["start_date"] = _norm_date(raw.get("settlement-start-date"))
            s["end_date"] = _norm_date(raw.get("settlement-end-date"))
            s["deposit_date"] = _norm_date(raw.get("deposit-date"))
            s["total_amount"] = _to_float(raw.get("total-amount"))
            s["currency"] = (raw.get("currency") or "").strip() or None
            continue
        s["items"].extend(_items_from_row(raw, is_long))

    return [settlements[sid] for sid in order]


# --- ▼ SECTION 03: 保存（精算番号ごとに丸ごと入れ替え。明細の合計が入金額と合わない精算は取り込まない） ▼ ---
def _check_settlement(s: dict):
    if s.get("total_amount") is None or not s.get("currency"):
        return "精算のまとめ行（入金額・通貨）がありません"
    total = round(sum(i["amount"] for i in s["items"]), 2)
    if abs(total - s["total_amount"]) >= 0.01:
        return f"明細の合計 {total} が入金額 {s['total_amount']} と合いません"
    return None


def save_settlements(user_id: int, settlements: list, source: str, report_ids: dict = None) -> list:
    results = []
    if not settlements:
        return results

    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    for s in settlements:
        result = {
            "settlement_id": s["settlement_id"],
            "start_date": s.get("start_date"),
            "end_date": s.get("end_date"),
            "currency": s.get("currency"),
            "total_amount": s.get("total_amount"),
            "lines": len(s["items"]),
        }
        error = _check_settlement(s)
        if error:
            result["status"] = "error"
            result["message"] = error
            results.append(result)
            continue

        cur.execute("DELETE FROM orbit_settlement_items WHERE user_id = %s AND settlement_id = %s",
                    (user_id, s["settlement_id"]))
        cur.execute("DELETE FROM orbit_settlements WHERE user_id = %s AND settlement_id = %s",
                    (user_id, s["settlement_id"]))
        cur.execute(
            """
            INSERT INTO orbit_settlements
                (user_id, settlement_id, start_date, end_date, deposit_date, total_amount, currency,
                 source, report_id, imported_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, s["settlement_id"], s.get("start_date"), s.get("end_date"), s.get("deposit_date"),
             s["total_amount"], s["currency"], source, (report_ids or {}).get(s["settlement_id"]), now),
        )
        if s["items"]:
            execute_values(
                cur,
                """
                INSERT INTO orbit_settlement_items
                    (user_id, settlement_id, transaction_type, order_id, order_item_id, adjustment_id, sku,
                     marketplace_name, amount_type, amount_description, amount, currency, posted_date)
                VALUES %s
                """,
                [
                    (user_id, s["settlement_id"], i["transaction_type"], i["order_id"], i["order_item_id"],
                     i["adjustment_id"], i["sku"], i["marketplace_name"], i["amount_type"],
                     i["amount_description"], i["amount"], s["currency"], i["posted_date"])
                    for i in s["items"]
                ],
            )
        conn.commit()
        result["status"] = "ok"
        results.append(result)

    conn.close()
    return results


# --- ▼ SECTION 04: SP-APIで自動取得（バックグラウンド。1分に1件ずつダウンロード） ▼ ---
_fetch_status = {}
_fetch_lock = threading.Lock()


def get_fetch_status(user_id: int) -> dict:
    return dict(_fetch_status.get(user_id) or {"running": False})


def _api_accounts(user_id: int, countries) -> list:
    # 同じ北米アカウント（US・CA）は refresh_token が同じ＝1回の一覧取得で両方の精算が返るのでまとめる
    conn = get_conn("a_marketplaces.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT country_code, marketplace_id, refresh_token, spapi_host, host
        FROM marketplaces
        WHERE user_id = %s AND country_code = ANY(%s)
          AND refresh_token IS NOT NULL AND refresh_token <> ''
        ORDER BY country_code
        """,
        (user_id, list(countries)),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    accounts = {}
    for r in rows:
        accounts.setdefault(r["refresh_token"], r)
    return list(accounts.values())


def _imported_report_ids(user_id: int) -> set:
    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    cur.execute("SELECT report_id FROM orbit_settlements WHERE user_id = %s AND report_id IS NOT NULL", (user_id,))
    ids = {r["report_id"] for r in cur.fetchall()}
    conn.close()
    return ids


def _spapi_get(user_id: int, account: dict, path: str, params: dict = None):
    # guard_429 のブロックを避けるため user_id は渡さずに呼ぶ（429は自前で待って再試行する）。
    # API使用回数のカウンターは他のSP-APIと同じく記録する。
    from amazon.adapters.amazon_adapter import record_api_usage
    from amazon.db import get_lwa_credentials
    from amazon.spapi_client import real_signed_request

    lwa = get_lwa_credentials(account["country_code"].upper())
    record_api_usage(user_id, account["marketplace_id"], path)
    return real_signed_request(
        "GET", path, params=params or {},
        host=account.get("spapi_host") or account.get("host"), user_id=None,
        client_id=lwa.get("client_id"), client_secret=lwa.get("client_secret"),
        refresh_token=account["refresh_token"],
    )


def _is_quota_error(res: dict) -> bool:
    return any((e or {}).get("code") == "QuotaExceeded" for e in (res.get("errors") or []))


def _error_text(res: dict) -> str:
    errors = res.get("errors") or []
    if not errors:
        return "不明なエラー"
    e = errors[0] or {}
    if e.get("code") == "Unauthorized":
        return "権限がありません（アプリに「財務会計」の権限が付いているか、認証し直したか確認してください）"
    return f"{e.get('code')}: {e.get('message')}"


def _list_settlement_reports(user_id: int, account: dict) -> list:
    reports = []
    params = {"reportTypes": SETTLEMENT_REPORT_TYPE, "pageSize": 100}
    while True:
        res = _spapi_get(user_id, account, "/reports/2021-06-30/reports", params)
        if res.get("errors"):
            raise RuntimeError(_error_text(res))
        reports.extend(res.get("reports") or [])
        token = res.get("nextToken")
        if not token:
            break
        params = {"nextToken": token}
    return [r for r in reports if r.get("processingStatus") == "DONE" and r.get("reportDocumentId")]


def _download_report(user_id: int, account: dict, document_id: str) -> str:
    for _ in range(QUOTA_RETRY_MAX + 1):
        res = _spapi_get(user_id, account, f"/reports/2021-06-30/documents/{document_id}")
        if res.get("url"):
            break
        if not _is_quota_error(res):
            raise RuntimeError(_error_text(res))
        time.sleep(QUOTA_RETRY_WAIT_SEC)
    else:
        raise RuntimeError("API制限で取得できませんでした（時間をおいてもう一度押してください）")

    resp = requests.get(res["url"], timeout=60)
    resp.raise_for_status()
    raw = resp.content
    if res.get("compressionAlgorithm") == "GZIP":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _run_fetch(user_id: int, countries):
    status = _fetch_status[user_id]
    try:
        imported = _imported_report_ids(user_id)
        targets = []
        for account in _api_accounts(user_id, countries):
            for r in _list_settlement_reports(user_id, account):
                if r["reportId"] not in imported:
                    targets.append((account, r))
        targets.sort(key=lambda t: t[1].get("dataStartTime") or "")
        status["total"] = len(targets)

        for idx, (account, report) in enumerate(targets):
            if idx > 0:
                time.sleep(DOCUMENT_INTERVAL_SEC)
            status["message"] = f"{idx + 1}/{len(targets)}件目を取得中"
            try:
                text = _download_report(user_id, account, report["reportDocumentId"])
                settlements = parse_settlement_file(text)
                report_ids = {s["settlement_id"]: report["reportId"] for s in settlements}
                results = save_settlements(user_id, settlements, "api", report_ids)
            except Exception as e:
                results = [{
                    "settlement_id": None, "status": "error", "message": str(e),
                    "start_date": (report.get("dataStartTime") or "")[:10],
                    "end_date": (report.get("dataEndTime") or "")[:10],
                }]
            status["results"].extend(results)
            status["done"] = idx + 1
        status["message"] = "完了"
    except Exception as e:
        status["message"] = f"失敗：{e}"
        status["failed"] = True
    finally:
        status["running"] = False
        status["finished_at"] = datetime.utcnow().isoformat()


def start_fetch(user_id: int, zsss_mode: str) -> dict:
    countries = SETTLEMENT_API_COUNTRIES.get((zsss_mode or "").lower())
    if not countries:
        return {"started": False, "message": f"この環境（{zsss_mode}）ではAPIで決済レポートを取得しません"}
    with _fetch_lock:
        if (_fetch_status.get(user_id) or {}).get("running"):
            return {"started": False, "message": "取得中です"}
        _fetch_status[user_id] = {
            "running": True, "countries": list(countries), "total": None, "done": 0,
            "results": [], "message": "決済レポートの一覧を取得中", "failed": False,
            "started_at": datetime.utcnow().isoformat(), "finished_at": None,
        }
    threading.Thread(target=_run_fetch, args=(user_id, countries), daemon=True).start()
    return {"started": True, "countries": list(countries)}


# --- ▼ SECTION 05: 書き出し（ATLAS→ZSSS受け渡し用。縦長形式で全精算を1ファイルに） ▼ ---
EXPORT_COLUMNS = [
    "settlement-id", "settlement-start-date", "settlement-end-date", "deposit-date", "total-amount", "currency",
    "transaction-type", "order-id", "adjustment-id", "marketplace-name", "amount-type", "amount-description",
    "amount", "posted-date", "order-item-code", "sku",
]


def export_settlements_tsv(user_id: int) -> str:
    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM orbit_settlements WHERE user_id = %s ORDER BY start_date, settlement_id", (user_id,))
    headers = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM orbit_settlement_items WHERE user_id = %s ORDER BY settlement_id, id", (user_id,))
    items_by_sid = {}
    for r in cur.fetchall():
        items_by_sid.setdefault(r["settlement_id"], []).append(dict(r))
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)
    blank = {c: "" for c in EXPORT_COLUMNS}
    for h in headers:
        writer.writerow([{**blank, "settlement-id": h["settlement_id"], "settlement-start-date": h["start_date"] or "",
                          "settlement-end-date": h["end_date"] or "", "deposit-date": h["deposit_date"] or "",
                          "total-amount": h["total_amount"], "currency": h["currency"] or ""}[c] for c in EXPORT_COLUMNS])
        for i in items_by_sid.get(h["settlement_id"], []):
            writer.writerow([{**blank, "settlement-id": h["settlement_id"], "transaction-type": i["transaction_type"] or "",
                              "order-id": i["order_id"] or "", "adjustment-id": i["adjustment_id"] or "",
                              "marketplace-name": i["marketplace_name"] or "", "amount-type": i["amount_type"] or "",
                              "amount-description": i["amount_description"] or "", "amount": i["amount"],
                              "posted-date": i["posted_date"] or "", "order-item-code": i["order_item_id"] or "",
                              "sku": i["sku"] or ""}[c] for c in EXPORT_COLUMNS])
    return output.getvalue()


# --- ▼ SECTION 06: 商品ごとの集計（販売額・返金・手数料・入金額） ▼ ---
# 販売額＝注文の商品代金＋お客様負担の送料（税金は除く）。返金＝返金・Goodwill等（税金は除く）。
# 税金は「預かった税」と「Amazonが代わりに納める税」で打ち消し合うので入金額にだけ含める。
# 手数料＝それ以外全部（販売手数料・返金時に戻る手数料・返金手数料など）＝入金額−販売額−返金−税金。
def _is_tax(amount_type, description) -> bool:
    return amount_type == "ItemWithheldTax" or "Tax" in (description or "")


def get_item_settlement_summary(user_id: int) -> dict:
    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT i.order_item_id, i.transaction_type, i.amount_type, i.amount_description, i.amount,
               i.currency, s.deposit_date
        FROM orbit_settlement_items i
        JOIN orbit_settlements s ON s.user_id = i.user_id AND s.settlement_id = i.settlement_id
        WHERE i.user_id = %s AND i.order_item_id IS NOT NULL
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()

    summary = {}
    for r in rows:
        s = summary.setdefault(r["order_item_id"], {
            "currency": r["currency"], "sale_price": 0.0, "refund_total": 0.0, "tax_total": 0.0,
            "net_proceeds": 0.0, "has_order": False, "deposit_date": None,
        })
        amount = r["amount"] or 0.0
        s["net_proceeds"] += amount
        if r["transaction_type"] == "Order":
            s["has_order"] = True
        if _is_tax(r["amount_type"], r["amount_description"]):
            s["tax_total"] += amount
        elif r["amount_type"] in ("ItemPrice", "Promotion"):
            if r["transaction_type"] == "Order":
                s["sale_price"] += amount
            else:
                s["refund_total"] += amount
        if r["deposit_date"] and (not s["deposit_date"] or r["deposit_date"] > s["deposit_date"]):
            s["deposit_date"] = r["deposit_date"]

    for s in summary.values():
        s["fees_total"] = s["net_proceeds"] - s["sale_price"] - s["refund_total"] - s["tax_total"]
    return summary


# アーカイブの「決済確定」判定用：注文の入金（Order）が精算に入っている注文番号
def get_settled_order_ids(user_id: int) -> set:
    conn = get_conn("a_orbit_settlements.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT order_id FROM orbit_settlement_items "
        "WHERE user_id = %s AND transaction_type = 'Order' AND order_id IS NOT NULL",
        (user_id,),
    )
    ids = {r["order_id"] for r in cur.fetchall()}
    conn.close()
    return ids
