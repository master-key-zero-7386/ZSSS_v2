// ==========================================================
// Copyright (c) 2026 ZSSS
// All Rights Reserved.
// ----------------------------------------------------------
// ファイル名: static/js/model_number.js
// 目的：その他ツール「型番チェック」：Pre-Listingの型番・説明文をCSVで出す
// =====================================================

document.addEventListener("DOMContentLoaded", () => {

    const input = document.getElementById("mnc-brand");
    const btn = document.getElementById("mnc-export-csv");
    if (!input || !btn) return;

    const run = async () => {
        const brand = input.value.trim();
        if (!brand) {
            window.showToast?.("ブランド名を入れてください", "error");
            return;
        }
        const country_code = document.getElementById("globalRegion")?.value || "";
        const checkMakita = document.getElementById("mnc-check-makita")?.checked ? "1" : "0";
        const scope = document.getElementById("mnc-scope")?.value || "pre";
        const url = `/amazon/model_number_csv?brand=${encodeURIComponent(brand)}&country_code=${encodeURIComponent(country_code)}&check_makita=${checkMakita}&scope=${encodeURIComponent(scope)}`;
        const statusEl = document.getElementById("mncStatus");

        btn.disabled = true;
        if (statusEl) statusEl.innerText = checkMakita === "1"
            ? "作成中…（マキタカナダを見に行っているので、件数が多いと数分かかります）"
            : "作成中…";
        try {
            const res = await fetch(url);
            if (!res.ok) {
                let msg = "CSVの作成に失敗しました";
                try { msg = (await res.json()).message || msg; } catch (e) {}
                window.showToast?.(msg, "error");
                return;
            }
            const blob = await res.blob();
            const cd = res.headers.get("Content-Disposition") || "";
            const m = cd.match(/filename=([^;]+)/);
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = m ? m[1].trim() : `${country_code}_model_number.csv`;
            a.click();
            URL.revokeObjectURL(a.href);
            if (statusEl) statusEl.innerText = "完了しました";
        } catch (e) {
            console.error("model_number_csv error:", e);
            window.showToast?.("通信エラーが発生しました", "error");
            if (statusEl) statusEl.innerText = "";
        } finally {
            btn.disabled = false;
        }
    };

    btn.addEventListener("click", run);
    input.addEventListener("keydown", e => { if (e.key === "Enter") run(); });
});
