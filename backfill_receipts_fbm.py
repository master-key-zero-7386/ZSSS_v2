# ==========================================
# ファイル名: backfill_receipts_fbm.py   ★一回限りの使い捨てスクリプト（完了後は削除してよい）
# 目的: N4837〜5129 の仕入れ領収書PDFを、Googleスプレッドシート「FBM」タブを照合表にして
#       「N{N番}_YYMMDD_注文番号_仕入先.pdf」へリネームし、保管先フォルダへ移す。
#       この期間は ZSSS(orbit_orders) にデータが無く、発注管理の「一括読込」では処理できないため。
#
#   - Phase1 のコア（注文番号抽出・命名・重複判定・コピー）を amazon.services.orbit_receipt_import_service
#     から流用。DBへの書き込みは一切しない（該当行がZSSSに無いため）。
#   - 既定は dry-run（ファイルを一切動かさず、読み取り結果と実行予定だけ表示）。--commit で実行。
#
# 使い方（運用PCで、venvのpythonから）:
#   set PY=..\python_env\venv\Scripts\python.exe
#   %PY% backfill_receipts_fbm.py --user 1 --inbox "G:\...\受信" --store "G:\...\保管先"
#   （表示を確認して問題なければ）
#   %PY% backfill_receipts_fbm.py --user 1 --inbox "G:\...\受信" --store "G:\...\保管先" --commit
# ==========================================

import argparse
import os
import re
import shutil
import sys

# リポジトリ直下に置く前提。amazon パッケージを import できるようにする。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amazon.services.google_sheets_service import (
    fetch_sheet_range,
    _extract_spreadsheet_id,
    GoogleAuthError,
)
from amazon.services.orbit_receipt_import_service import (
    extract_order_numbers,
    extract_order_numbers_from_filename,
    _yymmdd_from_filename,
    _normalize_yymmdd,
    _sanitize_supplier,
    _sha256,
    _resolve_target,
    _extract_pdf_text,
)

# FBMシート（依頼書の管理シート）。列位置はユーザー指定（2026-09-10）:
#   A(0)=SLCN管理No(N番) / BW(74)=注文ID / BX(75)=仕入先:ショップ名 / CL(89)=仕入確認("-" or "仕入")
#   ヘッダー行=8行目 / データ=10行目〜 / 日付列はヘッダー名「仕入日」で探す
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1DVsinPw-G9lVJ_4fL1btiWNUdxJoGv7iFETBNcix2N8/edit?gid=748611947"
DEFAULT_TAB = "FBM"
COL_NBAN = 0
COL_ORDER = 74   # BW
COL_SUPPLIER = 75  # BX
COL_CONFIRM = 89  # CL
CONFIRM_OK = "仕入"
HEADER_ROW_1IDX = 8   # ヘッダーは8行目
DATA_ROW_1IDX = 10    # データは10行目から


def _cell(row, i):
    return row[i].strip() if i < len(row) and row[i] is not None else ""


def _parse_nban(raw):
    """"N4835" / "4835" / "Ｎ4835" → 4835（int）。取れなければ None。"""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits) if digits else None


def load_match_index(user_id, sheet_url, tab):
    """FBMシートを {注文番号: [ {nban, supplier, date_raw} , ... ]} に。CL列=="仕入" の行だけ。"""
    sheet_id = _extract_spreadsheet_id(sheet_url)
    # ヘッダー行〜末尾まで、CL列を確実に含む幅で取得（余裕をみて EZ=156列まで）
    values = fetch_sheet_range(user_id, sheet_id, f"{tab}!A{HEADER_ROW_1IDX}:EZ")
    if not values:
        raise RuntimeError(f"シート {tab} から行を取得できませんでした。")

    header = values[0]
    try:
        col_date = header.index("仕入日")
    except ValueError:
        raise RuntimeError(
            "ヘッダー行に「仕入日」列が見つかりません。取得したヘッダー: "
            + " | ".join(f"{i}:{h}" for i, h in enumerate(header) if h)
        )

    # values[0]=ヘッダー(8行目), values[1]=9行目, values[2]=10行目(データ先頭)
    data = values[(DATA_ROW_1IDX - HEADER_ROW_1IDX):]

    index = {}
    stats = {"rows": 0, "confirmed": 0, "no_nban": 0, "no_order": 0, "entries": 0}
    samples = []
    for row in data:
        stats["rows"] += 1
        if _cell(row, COL_CONFIRM) != CONFIRM_OK:
            continue
        stats["confirmed"] += 1
        nban = _parse_nban(_cell(row, COL_NBAN))
        order_raw = _cell(row, COL_ORDER)
        supplier = _cell(row, COL_SUPPLIER)
        date_raw = _cell(row, col_date)
        if nban is None:
            stats["no_nban"] += 1
            continue
        order_nos = extract_order_numbers(order_raw)
        # Amazon形式に当てはまらない注文番号（Yahoo等）も生値のまま候補に加える
        if order_raw and order_raw not in order_nos:
            order_nos.append(order_raw)
        if not order_nos:
            stats["no_order"] += 1
            continue
        if len(samples) < 8:
            samples.append((nban, order_nos, supplier, date_raw))
        for on in order_nos:
            index.setdefault(on, []).append(
                {"nban": nban, "supplier": supplier, "date_raw": date_raw}
            )
            stats["entries"] += 1
    return index, col_date, stats, samples


def plan_files(inbox, index):
    """受信フォルダの *.pdf を1件ずつ照合し、実行プラン（コピー予定）を作る。"""
    pdfs = sorted(
        f for f in os.listdir(inbox)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(inbox, f))
    )
    plans = []   # {"src","name","targets":[filename,...],"note"} 成功
    failed = []  # {"file","reason"}
    for name in pdfs:
        src = os.path.join(inbox, name)
        candidates = extract_order_numbers_from_filename(name)
        if not candidates:
            candidates = extract_order_numbers(_extract_pdf_text(src))

        entries = []
        matched_no = None
        for on in candidates:
            if on in index:
                entries = index[on]
                matched_no = on
                break
        if not entries:
            failed.append({"file": name, "reason": "注文番号を特定できない、またはFBMシート(仕入確定分)に一致なし"})
            continue

        yymmdd = _yymmdd_from_filename(name) or _normalize_yymmdd(entries[0]["date_raw"])
        if not yymmdd:
            failed.append({"file": name, "reason": f"日付を決定できません（ファイル名／シート仕入日='{entries[0]['date_raw']}'）"})
            continue

        nbans = sorted({e["nban"] for e in entries})
        targets = []
        for nban in nbans:
            e = next((x for x in entries if x["nban"] == nban), entries[0])
            supplier = _sanitize_supplier(e["supplier"])
            targets.append(f"N{nban}_{yymmdd}_{matched_no}_{supplier}.pdf")
        plans.append({"src": src, "name": name, "matched_no": matched_no, "targets": targets})
    return pdfs, plans, failed


def set_flags_from_store(user_id, store):
    """保管先フォルダの「N{数字}_...」ファイル名からN番を集め、orbit_orders に存在する行の
    invoice_saved を立てる（DB更新のみ・ファイルは触らない）。
    バックフィルで N5130 以降の領収書もファイル化されるが invoice_saved は立たないため、その穴埋め。"""
    import re as _re
    from datetime import datetime as _dt
    from amazon.db import get_conn

    nbans = set()
    for f in os.listdir(store):
        m = _re.match(r"^N(\d+)_", f)
        if m:
            nbans.add(int(m.group(1)))
    if not nbans:
        print("[FLAGS] 保管先に「N番_...」形式のファイルがありません")
        return

    conn = get_conn("a_orbit_orders.db")
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE orbit_orders SET invoice_saved = 1, updated_at = %s "
            "WHERE user_id = %s AND agent_serial_no = ANY(%s) "
            "AND (invoice_saved IS NULL OR invoice_saved = 0)",
            (_dt.utcnow().isoformat(), user_id, sorted(nbans)),
        )
        n = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"[FLAGS] 保管先のN番 {len(nbans)}種  →  invoice_saved を立てた行: {n}")


def main():
    ap = argparse.ArgumentParser(description="FBMシート照合で N4837〜5129 の領収書PDFをリネーム保管（一回限り）")
    ap.add_argument("--user", type=int, required=True, help="Google連携済みの user_id（通常 1）")
    ap.add_argument("--inbox", help="受信フォルダ（手DLした領収書PDF）")
    ap.add_argument("--store", required=True, help="保管先フォルダ（リネーム後の移動先）")
    ap.add_argument("--sheet-url", default=DEFAULT_SHEET_URL)
    ap.add_argument("--tab", default=DEFAULT_TAB)
    ap.add_argument("--commit", action="store_true", help="指定時のみ実際にコピー＆元ファイル削除。既定は dry-run。")
    ap.add_argument("--set-flags", action="store_true",
                    help="ファイル処理はせず、保管先の「N番_...」ファイルから orbit_orders の invoice_saved を立てるだけ")
    ap.add_argument("--cleanup-inbox", action="store_true",
                    help="コピーはせず、保管先に中身一致のコピーを確認できた受信フォルダの元PDFだけ削除（失敗29件は残す）")
    args = ap.parse_args()

    if not os.path.isdir(args.store):
        sys.exit(f"保管先フォルダが見つかりません: {args.store}")

    if args.set_flags:
        print("[MODE] SET-FLAGS（DB更新のみ・ファイルは動かしません）")
        set_flags_from_store(args.user, args.store)
        return

    if not args.inbox or not os.path.isdir(args.inbox):
        sys.exit(f"受信フォルダが見つかりません: {args.inbox}")

    if args.cleanup_inbox:
        # Google連携もFBMシートも使わない。保管先の既存ファイル名（N番_日付_注文番号_...）から
        # 注文番号を拾い、受信フォルダの元PDFと SHA256 で突き合わせて、中身一致が確認できた元だけ削除する。
        print("[MODE] CLEANUP-INBOX（保管先の N番_注文番号 ファイルを基準に、中身一致の元PDFだけ削除）")
        # 保管先のファイル名は「N番_YYMMDD_注文番号_仕入先.pdf」固定形式。注文番号部分に
        # Amazon形式でないもの（Yahoo等）も入るので、位置で直接切り出す（Amazon抽出はフォールバック）。
        gen_name_re = re.compile(r"^N\d+_\d{6}_([^_]+)_")
        store_by_order = {}
        for f in os.listdir(args.store):
            if not f.lower().endswith(".pdf") or not os.path.isfile(os.path.join(args.store, f)):
                continue
            m = gen_name_re.match(f)
            if m:
                store_by_order.setdefault(m.group(1), []).append(os.path.join(args.store, f))
            for on in extract_order_numbers(f):
                store_by_order.setdefault(on, []).append(os.path.join(args.store, f))
        print(f"[STORE] 保管先PDF由来のユニーク注文番号 = {len(store_by_order)}")

        src_pdfs = sorted(
            x for x in os.listdir(args.inbox)
            if x.lower().endswith(".pdf") and os.path.isfile(os.path.join(args.inbox, x))
        )
        deleted = kept = errors = 0
        for name in src_pdfs:
            src = os.path.join(args.inbox, name)
            ons = extract_order_numbers_from_filename(name) or extract_order_numbers(_extract_pdf_text(src))
            cand_paths = []
            for on in ons:
                cand_paths += store_by_order.get(on, [])
            if not cand_paths:
                kept += 1
                print(f"   KEEP  {name}（保管先に対応ファイルなし＝未処理/失敗分）")
                continue
            try:
                src_hash = _sha256(src)
            except OSError as e:
                kept += 1
                print(f"   KEEP  {name}（読み取り不可: {e}）")
                continue
            match = False
            for fp in cand_paths:
                try:
                    if _sha256(fp) == src_hash:
                        match = True
                        break
                except OSError:
                    pass
            if not match:
                kept += 1
                print(f"   KEEP  {name}（保管先に中身一致のコピーが無い）")
                continue
            try:
                os.remove(src)
                deleted += 1
                print(f"   DEL   {name}")
            except OSError as e:
                errors += 1
                print(f"   ERROR 削除できない: {name} — {e}")
        print(f"\n[CLEANUP] 削除 {deleted} / 保持 {kept} / 削除失敗 {errors}")
        return

    print(f"[MODE] {'COMMIT（実行）' if args.commit else 'DRY-RUN（表示のみ・ファイルは動かしません）'}")
    print(f"[SHEET] {args.tab}  <- {args.sheet_url}")
    try:
        index, col_date, stats, samples = load_match_index(args.user, args.sheet_url, args.tab)
    except GoogleAuthError as e:
        sys.exit(f"[GOOGLE] {e}")

    print(f"[SHEET] 仕入日列 index={col_date}")
    print(f"[SHEET] データ行={stats['rows']}  仕入確定(CL=='仕入')={stats['confirmed']}  "
          f"N番なし={stats['no_nban']}  注文ID無し={stats['no_order']}  照合エントリ={stats['entries']}  "
          f"ユニーク注文番号={len(index)}")
    print("[SHEET] 先頭サンプル（列マッピング確認用）:")
    for nban, ons, sup, d in samples:
        print(f"   N{nban}  order={ons}  仕入先='{sup}'  仕入日='{d}'")

    pdfs, plans, failed = plan_files(args.inbox, index)
    print(f"\n[PDF] 受信フォルダ内 PDF={len(pdfs)}  照合OK={len(plans)}  失敗={len(failed)}")

    would_copy = would_skip = did_copy = did_skip = 0
    for p in plans:
        try:
            src_hash = _sha256(p["src"])
        except OSError as e:
            failed.append({"file": p["name"], "reason": f"読み取り不可: {e}"})
            continue
        wrote_any = False
        for fname in p["targets"]:
            target, action = _resolve_target(args.store, fname, src_hash)
            base = os.path.basename(target)
            if action == "skip":
                would_skip += 1
                wrote_any = True
                if args.commit:
                    did_skip += 1
                print(f"   SKIP  {p['name']}  =(既に同一)=> {base}")
                continue
            would_copy += 1
            if args.commit:
                shutil.copy2(p["src"], target)
                did_copy += 1
            print(f"   {'COPY ' if args.commit else 'PLAN '} {p['name']}  ==> {base}")
        if wrote_any and args.commit:
            try:
                os.remove(p["src"])
            except OSError as e:
                print(f"   ※元ファイルを削除できず（保管先へのコピーは完了済み）: {p['name']} — {e}")

    if failed:
        print(f"\n[FAILED] 受信フォルダに残す（要対応） {len(failed)}件:")
        for f in failed:
            print(f"   {f['file']} — {f['reason']}")

    print("\n[SUMMARY] "
          + (f"コピー {did_copy} / スキップ {did_skip} / 失敗 {len(failed)}"
             if args.commit
             else f"コピー予定 {would_copy} / スキップ予定 {would_skip} / 失敗 {len(failed)}  … --commit で実行"))


if __name__ == "__main__":
    main()
