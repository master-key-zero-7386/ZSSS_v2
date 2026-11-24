import json
import re
from datetime import datetime

from flask import Blueprint, request, jsonify, Response, session

from amazon.db import get_conn

# その他ツール「文書管理」：購入者メッセージ等の定型文（カテゴリ＋タイトル＋本文）。
# 画面でコピーしてそのまま貼り付ける用途。インポート/エクスポートは引っ越し・バックアップ用のJSON。
doc_library_bp = Blueprint("doc_library_bp", __name__)

DB_NAME = "a_doc_templates.db"
EXPORT_FORMAT = "zsss_doc_templates"
EXPORT_VERSION = 1


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _err(message: str, code: int = 400):
    return jsonify({"status": "error", "message": message}), code


# --- ▼ 対象ASIN（この定型文を使う商品。発注管理の該当行からワンクリックで開ける） ---
_ASIN_SPLIT = re.compile(r"[\s,、，]+")
_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def _parse_asins(raw) -> tuple:
    """改行・カンマ・空白区切りの入力 → (大文字・重複なしのASINリスト, 形式がおかしい語のリスト)。"""
    if isinstance(raw, list):
        raw = "\n".join(str(x) for x in raw)
    asins, bad = [], []
    for token in _ASIN_SPLIT.split((raw or "").upper()):
        if not token:
            continue
        if not _ASIN_RE.match(token):
            bad.append(token)
        elif token not in asins:
            asins.append(token)
    return asins, bad


def load_asin_template_map(user_id) -> dict:
    """{ASIN: [文書id, ...]}。発注管理の一覧で「このASINに定型文があるか」を引く用。"""
    conn = get_conn(DB_NAME)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, asins FROM doc_templates
            WHERE user_id = %s AND asins IS NOT NULL AND asins <> ''
            ORDER BY title, id
        """, (user_id,))
        result = {}
        for r in cur.fetchall():
            for asin in (r["asins"] or "").split("\n"):
                if asin:
                    result.setdefault(asin, []).append(r["id"])
        return result
    finally:
        conn.close()


# --- ▼ 一覧（カテゴリ＋全文書をまとめて返す。件数は多くない想定） ---
@doc_library_bp.route("/data", methods=["GET"])
def get_data():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, sort_order FROM doc_template_categories
        WHERE user_id = %s
        ORDER BY sort_order, id
    """, (user_id,))
    categories = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT id, category_id, title, body, asins, body_translated, translated_source, updated_at
        FROM doc_templates
        WHERE user_id = %s
        ORDER BY title, id
    """, (user_id,))
    templates = []
    for r in cur.fetchall():
        t = dict(r)
        t["asins"] = [a for a in (t.get("asins") or "").split("\n") if a]
        # 翻訳が無い・本文を直した後で古い → 画面が開いた時に自動で翻訳し直す
        source = t.pop("translated_source", None)
        t["translation_stale"] = t.get("body_translated") is None \
            or (source or "") != (t.get("body") or "")
        templates.append(t)
    conn.close()

    return jsonify({"status": "ok", "categories": categories, "templates": templates})


# --- ▼ カテゴリ 追加・名前変更（id なし＝追加） ---
@doc_library_bp.route("/category/save", methods=["POST"])
def save_category():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    data = request.get_json(silent=True) or {}
    cat_id = data.get("id")
    name = (data.get("name") or "").strip()
    if not name:
        return _err("カテゴリ名を入力してください。")

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM doc_template_categories
        WHERE user_id = %s AND name = %s AND id <> %s
    """, (user_id, name, cat_id or 0))
    if cur.fetchone():
        conn.close()
        return _err(f"「{name}」というカテゴリは既にあります。")

    if cat_id:
        cur.execute("""
            UPDATE doc_template_categories SET name = %s
            WHERE id = %s AND user_id = %s
        """, (name, cat_id, user_id))
    else:
        cur.execute("""
            SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
            FROM doc_template_categories WHERE user_id = %s
        """, (user_id,))
        next_order = cur.fetchone()["next_order"]
        cur.execute("""
            INSERT INTO doc_template_categories (user_id, name, sort_order, created_at)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (user_id, name, next_order, _now()))
        cat_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "id": cat_id})


# --- ▼ カテゴリ 削除（中に文書が残っていれば拒否：うっかり全消しを防ぐ） ---
@doc_library_bp.route("/category/delete", methods=["POST"])
def delete_category():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    cat_id = (request.get_json(silent=True) or {}).get("id")

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) AS cnt FROM doc_templates
        WHERE user_id = %s AND category_id = %s
    """, (user_id, cat_id))
    if cur.fetchone()["cnt"]:
        conn.close()
        return _err("このカテゴリには文書が入っています。先に文書を削除するか、別のカテゴリへ移してください。")

    cur.execute("""
        DELETE FROM doc_template_categories WHERE id = %s AND user_id = %s
    """, (cat_id, user_id))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# --- ▼ カテゴリ 並び替え（上へ／下へ：隣のカテゴリと入れ替え） ---
@doc_library_bp.route("/category/move", methods=["POST"])
def move_category():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    data = request.get_json(silent=True) or {}
    cat_id = data.get("id")
    direction = data.get("direction")

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM doc_template_categories
        WHERE user_id = %s ORDER BY sort_order, id
    """, (user_id,))
    ids = [r["id"] for r in cur.fetchall()]

    if cat_id in ids:
        i = ids.index(cat_id)
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            # 並び順を 1,2,3… に振り直す（sort_order の重複も同時に解消）
            for order, cid in enumerate(ids, start=1):
                cur.execute("""
                    UPDATE doc_template_categories SET sort_order = %s
                    WHERE id = %s AND user_id = %s
                """, (order, cid, user_id))
            conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# --- ▼ 文書 追加・編集（id なし＝追加） ---
@doc_library_bp.route("/template/save", methods=["POST"])
def save_template():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    data = request.get_json(silent=True) or {}
    tpl_id = data.get("id")
    category_id = data.get("category_id")
    title = (data.get("title") or "").strip()
    body = data.get("body") or ""
    asins, bad_asins = _parse_asins(data.get("asins"))

    if not category_id:
        return _err("カテゴリを選んでください。")
    if not title:
        return _err("タイトルを入力してください。")
    if bad_asins:
        return _err(f"対象ASINの形式が正しくありません（英数字10桁）：{'、'.join(bad_asins[:10])}")
    asins_text = "\n".join(asins) or None

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM doc_template_categories WHERE id = %s AND user_id = %s
    """, (category_id, user_id))
    if not cur.fetchone():
        conn.close()
        return _err("カテゴリが見つかりません。画面を更新してください。")

    cur.execute("""
        SELECT id FROM doc_templates
        WHERE user_id = %s AND category_id = %s AND title = %s AND id <> %s
    """, (user_id, category_id, title, tpl_id or 0))
    if cur.fetchone():
        conn.close()
        return _err(f"同じカテゴリに「{title}」という文書が既にあります。")

    now = _now()
    if tpl_id:
        cur.execute("""
            UPDATE doc_templates
            SET category_id = %s, title = %s, body = %s, asins = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
        """, (category_id, title, body, asins_text, now, tpl_id, user_id))
    else:
        cur.execute("""
            INSERT INTO doc_templates (user_id, category_id, title, body, asins, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (user_id, category_id, title, body, asins_text, now, now))
        tpl_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "id": tpl_id})


# --- ▼ 文書 翻訳（DeepLで日本語に。結果はDBに残し、本文が変わるまで再翻訳しない） ---
@doc_library_bp.route("/template/translate", methods=["POST"])
def translate_template():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    tpl_id = (request.get_json(silent=True) or {}).get("id")

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT body FROM doc_templates WHERE id = %s AND user_id = %s
    """, (tpl_id, user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return _err("文書が見つかりません。画面を更新してください。", 404)

    # DeepLの応答待ち（数秒）の間はDB接続を持たない
    body = row["body"] or ""
    from tools.deepl_client import translate_to_japanese, DeepLError
    try:
        translated = translate_to_japanese(body)
    except DeepLError as e:
        return _err(str(e), 502)

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    # 翻訳中に本文が書き換えられていたら、古い本文の翻訳で上書きしない
    cur.execute("""
        UPDATE doc_templates
        SET body_translated = %s, translated_source = %s, translated_at = %s
        WHERE id = %s AND user_id = %s AND COALESCE(body, '') = %s
    """, (translated, body, _now(), tpl_id, user_id, body))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "body_translated": translated})


# --- ▼ 文書 削除 ---
@doc_library_bp.route("/template/delete", methods=["POST"])
def delete_template():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    tpl_id = (request.get_json(silent=True) or {}).get("id")

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM doc_templates WHERE id = %s AND user_id = %s
    """, (tpl_id, user_id))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


# --- ▼ エクスポート（全カテゴリ・全文書を1つのJSONファイルに。本文は一字一句そのまま） ---
@doc_library_bp.route("/export", methods=["GET"])
def export_json():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name FROM doc_template_categories
        WHERE user_id = %s ORDER BY sort_order, id
    """, (user_id,))
    categories = cur.fetchall()

    cur.execute("""
        SELECT category_id, title, body, asins FROM doc_templates
        WHERE user_id = %s ORDER BY title, id
    """, (user_id,))
    templates = cur.fetchall()
    conn.close()

    def _doc(t):
        return {
            "title": t["title"],
            "body": t["body"] or "",
            "asins": [a for a in (t["asins"] or "").split("\n") if a],
        }

    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": _now(),
        "categories": [
            {
                "name": c["name"],
                "documents": [_doc(t) for t in templates if t["category_id"] == c["id"]],
            }
            for c in categories
        ],
    }

    # ensure_ascii=False：メモ帳で開いても日本語がそのまま読める
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"doc_templates_{datetime.now().strftime('%Y%m%d')}.json"
    return Response(
        body,
        content_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- ▼ インポート（同じカテゴリ名＋同じタイトルは上書き、なければ追加。既存は消さない） ---
@doc_library_bp.route("/import", methods=["POST"])
def import_json():
    user_id = session.get("user_id")
    if not user_id:
        return _err("ログインしてください。", 401)

    file = request.files.get("file")
    if not file:
        return _err("ファイルを選んでください。")

    # 中身を全部チェックしてからDBに書く（途中で壊れていたら何も取り込まない）
    try:
        payload = json.loads(file.read().decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _err("ファイルが壊れているか、文書管理のエクスポートファイルではありません。何も取り込んでいません。")

    if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT \
            or not isinstance(payload.get("categories"), list):
        return _err("文書管理のエクスポートファイルではありません。何も取り込んでいません。")

    # 対象ASINの無い古いファイル（asins キーなし）は、既存文書の対象ASINを消さずに残す（asins_text=False）
    entries = []  # [(カテゴリ名, [(タイトル, 本文, asins_text), ...]), ...]
    for c in payload["categories"]:
        name = (c.get("name") or "").strip() if isinstance(c, dict) else ""
        docs = c.get("documents") if isinstance(c, dict) else None
        if not name or not isinstance(docs, list):
            return _err("ファイルの中身に不正な箇所があります（カテゴリ）。何も取り込んでいません。")
        doc_rows = []
        for d in docs:
            title = (d.get("title") or "").strip() if isinstance(d, dict) else ""
            body = d.get("body") if isinstance(d, dict) else None
            if not title or not isinstance(body, str):
                return _err(f"ファイルの中身に不正な箇所があります（カテゴリ「{name}」の文書）。何も取り込んでいません。")
            asins_text = False
            if "asins" in d:
                asins, bad = _parse_asins(d.get("asins"))
                if bad:
                    return _err(f"「{title}」の対象ASINの形式が正しくありません：{'、'.join(bad[:10])}。何も取り込んでいません。")
                asins_text = "\n".join(asins) or None
            doc_rows.append((title, body, asins_text))
        entries.append((name, doc_rows))

    conn = get_conn(DB_NAME)
    cur = conn.cursor()
    now = _now()
    added = updated = new_categories = 0

    try:
        for name, doc_rows in entries:
            cur.execute("""
                SELECT id FROM doc_template_categories WHERE user_id = %s AND name = %s
            """, (user_id, name))
            row = cur.fetchone()
            if row:
                cat_id = row["id"]
            else:
                cur.execute("""
                    SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order
                    FROM doc_template_categories WHERE user_id = %s
                """, (user_id,))
                next_order = cur.fetchone()["next_order"]
                cur.execute("""
                    INSERT INTO doc_template_categories (user_id, name, sort_order, created_at)
                    VALUES (%s, %s, %s, %s) RETURNING id
                """, (user_id, name, next_order, now))
                cat_id = cur.fetchone()["id"]
                new_categories += 1

            for title, body, asins_text in doc_rows:
                cur.execute("""
                    SELECT id FROM doc_templates
                    WHERE user_id = %s AND category_id = %s AND title = %s
                """, (user_id, cat_id, title))
                existing = cur.fetchone()
                if existing:
                    if asins_text is False:
                        cur.execute("""
                            UPDATE doc_templates SET body = %s, updated_at = %s WHERE id = %s
                        """, (body, now, existing["id"]))
                    else:
                        cur.execute("""
                            UPDATE doc_templates SET body = %s, asins = %s, updated_at = %s WHERE id = %s
                        """, (body, asins_text, now, existing["id"]))
                    updated += 1
                else:
                    cur.execute("""
                        INSERT INTO doc_templates (user_id, category_id, title, body, asins, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, cat_id, title, body, asins_text or None, now, now))
                    added += 1
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()

    return jsonify({
        "status": "ok",
        "added": added,
        "updated": updated,
        "new_categories": new_categories,
    })
