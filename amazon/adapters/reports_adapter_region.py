# ======================================================
# Copyright (c) 2026 ZSSS
# All Rights Reserved.
# ------------------------------------------------------
# ファイル名: amazon/adapters/reports_adapter_region.py
# 目的: SP-API Reports API（GET_SALES_AND_TRAFFIC_REPORT）で
#      REGION側ASINごとのセッション数（閲覧数）を取得する
# ======================================================

import gzip
import io
import json
import time

import requests

from amazon.adapters.amazon_adapter import AmazonAdapter

REPORT_TYPE = "GET_SALES_AND_TRAFFIC_REPORT"

# --- SECTION 01: レポート作成〜完了待ち〜ダウンロードまで一括実行 ---
def fetch_sales_and_traffic_sessions(
    user_id,
    country_code,
    marketplace_id,
    start_date,
    end_date,
    poll_interval_sec=15,
    timeout_sec=600,
):
    """
    指定期間のASINごとの閲覧セッション数を取得する。
    戻り値: [{"asin": "...", "sessions": 12}, ...]
    """
    adapter = AmazonAdapter(user_id, country_code=country_code, marketplace_id=marketplace_id)

    report_id = _create_report(adapter, marketplace_id, start_date, end_date)
    report_document_id = _wait_for_report(adapter, report_id, poll_interval_sec, timeout_sec)
    report_body = _download_report_document(adapter, report_document_id)

    rows = []
    for item in report_body.get("salesAndTrafficByAsin", []):
        asin = item.get("childAsin") or item.get("parentAsin")
        if not asin:
            continue
        sessions = (item.get("trafficByAsin") or {}).get("sessions", 0)
        rows.append({"asin": asin, "sessions": int(sessions or 0)})

    return rows

# --- SECTION 02: レポートリクエスト作成 ---
def _create_report(adapter, marketplace_id, start_date, end_date):
    body = {
        "reportType": REPORT_TYPE,
        "marketplaceIds": [marketplace_id],
        "dataStartTime": start_date,
        "dataEndTime": end_date,
        "reportOptions": {
            "dateGranularity": "TOTAL",
            "asinGranularity": "CHILD",
        },
    }

    res = adapter.real_signed_request(
        "POST",
        "/reports/2021-06-30/reports",
        json=body,
    )

    report_id = res.get("reportId")
    if not report_id:
        raise RuntimeError(f"レポート作成に失敗しました: {res}")

    return report_id

# --- SECTION 03: レポート完了までポーリング ---
def _wait_for_report(adapter, report_id, poll_interval_sec, timeout_sec):
    elapsed = 0

    while elapsed <= timeout_sec:
        res = adapter.real_signed_request(
            "GET",
            f"/reports/2021-06-30/reports/{report_id}",
        )

        status = res.get("processingStatus")

        if status == "DONE":
            report_document_id = res.get("reportDocumentId")
            if not report_document_id:
                raise RuntimeError(f"レポート完了しましたがreportDocumentIdがありません: {res}")
            return report_document_id

        if status in ("FATAL", "CANCELLED"):
            raise RuntimeError(f"レポート生成が失敗しました（status={status}）: {res}")

        time.sleep(poll_interval_sec)
        elapsed += poll_interval_sec

    raise TimeoutError(f"レポート生成がタイムアウトしました（report_id={report_id}）")

# --- SECTION 04: レポート本体ダウンロード（S3署名URL・SP-API署名不要） ---
def _download_report_document(adapter, report_document_id):
    res = adapter.real_signed_request(
        "GET",
        f"/reports/2021-06-30/documents/{report_document_id}",
    )

    url = res.get("url")
    if not url:
        raise RuntimeError(f"レポートドキュメントURLが取得できません: {res}")

    compression = res.get("compressionAlgorithm")

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    raw = resp.content
    if compression == "GZIP":
        raw = gzip.decompress(raw)

    return json.loads(raw.decode("utf-8"))
