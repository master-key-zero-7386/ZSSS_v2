# ファイル名：zsss_web\files_check
# 目的：構造改修時に干渉するファイルを検索
# ========================================

# ========================================
# ファイル名：zsss_web\files_check
# 目的：構造改修時に干渉するファイルを検索
# ========================================

import os

project_dir = r"C:\zsss_web"

# --- 検索キーワード定義 ---
SEARCH_KEYWORDS = {
    "marketplace_id": "marketplace_id_references.txt",
    "region": "region_references.txt",  # ←ここを追加
}

results = {k: [] for k in SEARCH_KEYWORDS}

for root, dirs, files in os.walk(project_dir):
    for fname in files:
        if fname.endswith(".py"):
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        for key in SEARCH_KEYWORDS:
                            if key in line:
                                results[key].append((path, i, line.strip()))
            except Exception as e:
                print(f"[ERROR] {path}: {e}")

# --- 結果出力 ---
for key, out_name in SEARCH_KEYWORDS.items():
    output_file = os.path.join(project_dir, out_name)
    with open(output_file, "w", encoding="utf-8") as out:
        for r in results[key]:
            out.write(f"{r[0]}:{r[1]}: {r[2]}\n")
    print(f"[OK] {key} 参照箇所を {output_file} に出力しました")

