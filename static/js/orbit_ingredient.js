// =====================================================
// ファイル名: static/js/orbit_ingredient.js
// 目的: ORBIT「成分台帳」サブタブ（代行会社へ申告する成分・電池をASINごとに記録）
//   台帳にあるASINの注文は、サーバー側で発注管理の備考1へ成分を自動で書き足す。
//   行の入力欄は変更（フォーカスが外れた時）でその行を保存する。
// =====================================================

(function () {
    const pane = document.getElementById("orbit-pane-ingredient");
    if (!pane) return;

    let items = [];
    let loaded = false;

    const esc = (v) => (typeof orbitEscapeHtml === "function")
        ? orbitEscapeHtml(v == null ? "" : String(v))
        : String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const toast = (msg, type) => window.showToast ? window.showToast(msg, type) : alert(msg);
    const table = document.getElementById("orbit-ingredient-table");
    const status = document.getElementById("orbit-ingredient-status");
    const FIELDS = ["product_name", "genre", "jan_code", "note", "ingredients"];

    async function postJson(url, body) {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
        });
        const data = await res.json().catch(() => ({}));
        if (data.status !== "success") throw new Error(data.message || "処理に失敗しました");
        return data;
    }

    // 備考1を書き換えた結果のお知らせ（自動部分が見つからない行は手で直してもらう）
    function reportSync(data, prefix) {
        const parts = [prefix];
        if (data.updated) parts.push(`備考1を${data.updated}件書き換えました`);
        toast(parts.join("。"), "success");
        const missing = (data.remarks_mismatch || []).filter(n => n != null);
        if (missing.length) {
            toast(`備考1の成分が見つからない行があります（N${missing.join("・")}）。手で直してください`, "error");
        }
    }

    // --- ▼ SECTION 01: 読み込み ▼ ---
    async function load() {
        if (status) status.textContent = "読み込み中…";
        try {
            const res = await fetch("/orbit/ingredient_ledger");
            const data = await res.json();
            if (data.status !== "success") throw new Error(data.message || "読み込みに失敗しました");
            items = data.items || [];
            const s = data.settings || {};
            const urlInput = document.getElementById("orbit-ingredient-sheet-url");
            const nameInput = document.getElementById("orbit-ingredient-sheet-name");
            if (urlInput && !urlInput.value) urlInput.value = s.spreadsheet_url || "";
            if (nameInput && !nameInput.value) nameInput.value = s.sheet_name || "";
            loaded = true;
            render();
        } catch (e) {
            console.error("[ingredient_ledger]", e);
            if (status) status.textContent = "読み込みに失敗しました";
        }
    }

    document.querySelector('.st-subtab-btn[data-target="orbit-pane-ingredient"]')?.addEventListener("click", () => {
        if (!loaded) load();
    });

    // --- ▼ SECTION 02: 描画 ▼ ---
    function render() {
        const thead = table?.querySelector("thead tr");
        const tbody = table?.querySelector("tbody");
        if (!thead || !tbody) return;

        thead.innerHTML = "<th>ASIN</th><th>商品名</th><th>ジャンル</th><th>JAN</th><th>説明</th><th>成分</th><th>出荷実績</th><th></th>";

        const q = (document.getElementById("orbit-ingredient-search")?.value || "").trim().toLowerCase();
        const visible = q
            ? items.filter(i => [i.asin, i.product_name, i.genre, i.jan_code, i.note, i.ingredients]
                .some(v => (v || "").toLowerCase().includes(q)))
            : items;

        tbody.innerHTML = visible.map(i => {
            const shipped = [];
            if (i.shipped_count) shipped.push(`${i.shipped_count}回`);
            if (i.sheet_shipped && !i.shipped_count) shipped.push("あり（シート）");
            return `<tr data-asin="${esc(i.asin)}">`
                + `<td><span class="asin-cell" style="color:#007bff;text-decoration:underline;cursor:pointer;" title="クリックでコピー">${esc(i.asin)}</span></td>`
                + `<td class="ing-col-name"><input type="text" data-field="product_name" value="${esc(i.product_name)}"></td>`
                + `<td><input type="text" data-field="genre" value="${esc(i.genre)}" style="width:90px;"></td>`
                + `<td><input type="text" data-field="jan_code" value="${esc(i.jan_code)}" style="width:120px;"></td>`
                + `<td><input type="text" data-field="note" class="ing-note-input${i.note ? " has-value" : ""}" value="${esc(i.note)}" style="width:110px;"></td>`
                + `<td class="ing-col-ingredients"><textarea data-field="ingredients">${esc(i.ingredients)}</textarea></td>`
                + `<td style="white-space:nowrap;">${shipped.join(" ") || "-"}</td>`
                + `<td><button type="button" class="orbit-ingredient-delete-btn btn-red">削除</button></td>`
                + `</tr>`;
        }).join("");

        if (status) status.textContent = q ? `${visible.length}件 / 全${items.length}件` : `${items.length}件`;
    }

    document.getElementById("orbit-ingredient-search")?.addEventListener("input", render);

    // --- ▼ SECTION 03: 行の保存・削除 ▼ ---
    function rowData(tr) {
        const data = { asin: tr.dataset.asin };
        FIELDS.forEach(f => { data[f] = tr.querySelector(`[data-field="${f}"]`)?.value || ""; });
        return data;
    }

    table?.addEventListener("change", async (e) => {
        const tr = e.target.closest("tr[data-asin]");
        if (!tr || !e.target.dataset.field) return;
        const data = rowData(tr);
        try {
            const res = await postJson("/orbit/ingredient_ledger/save", data);
            const item = items.find(i => i.asin === data.asin);
            if (item) FIELDS.forEach(f => { item[f] = data[f]; });
            e.target.classList.toggle("has-value", e.target.dataset.field === "note" && !!data.note);
            reportSync(res, `${data.asin} を保存しました`);
        } catch (err) {
            console.error("[ingredient_ledger/save]", err);
            toast(err.message, "error");
        }
    });

    table?.addEventListener("click", async (e) => {
        const btn = e.target.closest(".orbit-ingredient-delete-btn");
        if (!btn) return;
        const asin = btn.closest("tr[data-asin]")?.dataset.asin;
        if (!asin || !confirm(`${asin} を台帳から削除しますか？\n出荷通知前の注文の備考1からも、自動で書き足した成分を外します。`)) return;
        try {
            const res = await postJson("/orbit/ingredient_ledger/delete", { asin });
            items = items.filter(i => i.asin !== asin);
            render();
            reportSync(res, `${asin} を削除しました`);
        } catch (err) {
            console.error("[ingredient_ledger/delete]", err);
            toast(err.message, "error");
        }
    });

    // --- ▼ SECTION 04: 追加 ▼ ---
    document.getElementById("orbit-ingredient-add-btn")?.addEventListener("click", async () => {
        const get = (f) => document.getElementById(`orbit-ingredient-new-${f}`);
        const data = { asin: (get("asin")?.value || "").trim().toUpperCase() };
        FIELDS.forEach(f => { data[f] = get(f)?.value || ""; });
        if (!data.asin) { toast("ASINを入力してください", "error"); return; }
        if (items.some(i => i.asin === data.asin)
            && !confirm(`${data.asin} はもう台帳にあります。入力した内容で上書きしますか？`)) return;
        try {
            const res = await postJson("/orbit/ingredient_ledger/save", data);
            ["asin", ...FIELDS].forEach(f => { if (get(f)) get(f).value = ""; });
            reportSync(res, `${data.asin} を台帳に追加しました`);
            await load();
        } catch (err) {
            console.error("[ingredient_ledger/add]", err);
            toast(err.message, "error");
        }
    });

    // --- ▼ SECTION 05: 取込元シートの設定・取込 ▼ ---
    function sheetSettings() {
        return {
            spreadsheet_url: (document.getElementById("orbit-ingredient-sheet-url")?.value || "").trim(),
            sheet_name: (document.getElementById("orbit-ingredient-sheet-name")?.value || "").trim(),
        };
    }

    document.getElementById("orbit-ingredient-settings-save-btn")?.addEventListener("click", async () => {
        try {
            await postJson("/orbit/ingredient_ledger/settings", sheetSettings());
            toast("取込元の設定を保存しました", "success");
        } catch (err) {
            console.error("[ingredient_ledger/settings]", err);
            toast(err.message, "error");
        }
    });

    document.getElementById("orbit-ingredient-import-btn")?.addEventListener("click", async (e) => {
        const settings = sheetSettings();
        if (!settings.spreadsheet_url || !settings.sheet_name) {
            toast("スプレッドシートのURLとタブ名を入力してください", "error");
            return;
        }
        if (!confirm("シートを読み込みます。シートにあるASINは台帳をシートの内容で上書きします。よろしいですか？")) return;
        const btn = e.currentTarget;
        btn.disabled = true;
        if (status) status.textContent = "シートを読み込み中…";
        try {
            await postJson("/orbit/ingredient_ledger/settings", settings);
            const res = await postJson("/orbit/ingredient_ledger/import");
            const skipped = res.skipped ? `（ASINが空・不正な${res.skipped}行は読み飛ばし）` : "";
            reportSync(res, `${res.imported}件を取り込みました${skipped}`);
            await load();
        } catch (err) {
            console.error("[ingredient_ledger/import]", err);
            toast(err.message, "error");
            if (status) status.textContent = "";
        } finally {
            btn.disabled = false;
        }
    });
})();
