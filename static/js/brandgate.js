// ==========================================================
// Copyright (c) 2026 ZSSS
// All Rights Reserved.
// ----------------------------------------------------------
// ファイル名: static/brandgate.js
// 目的：ブランドゲート
// =====================================================


document.addEventListener("DOMContentLoaded", () => {

    const statusEl = document.getElementById("brandgateStatus");
    const runBtn = document.getElementById("bgc-run");
    const clearBtn = document.getElementById("bgc-clear");
    const input = document.getElementById("bgc-asins");
    const tbody = document.querySelector("#bgc-table tbody");
    const exportBtn = document.getElementById("bgc-export-csv");
    let bgcAllData = [];

    runBtn?.addEventListener("click", async () => {

        if (statusEl) statusEl.innerText = "Status: Running...";

        try {

            const asins = input.value
                .split(/\n/)
                .map(v => v.trim())
                .filter(v => v);

            if (!asins.length) return;

            const country_code = document.getElementById("globalRegion")?.value || "";

            const res = await fetch("/amazon/brand_gate_check", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({ asins, country_code })
            });

            if (!res.ok) {
                if (statusEl) statusEl.innerText = "Status: Error";
                return;
            }

            const data = await res.json();

            bgcAllData = data;

            tbody.innerHTML = "";

            data.forEach(r => {
                const tr = document.createElement("tr");

                tr.innerHTML = `
                    <td>${r.asin}</td>
                    <td>${r.status || ""}</td>
                `;

                tbody.appendChild(tr);
            });

            if (statusEl) statusEl.innerText = "Status: Completed";

        } catch (e) {
            if (statusEl) statusEl.innerText = "Status: Error";
        }

    });    

    // --- クリア ---
    clearBtn?.addEventListener("click", () => {
        input.value = "";
        tbody.innerHTML = "";
    });

    // --- CSV ---
    exportBtn?.addEventListener("click", () => {

        const rows = bgcAllData.map(r => [
            r.asin,
            r.status || "",
            r.brand || ""
        ]);

        const csv = [["ASIN","Result","Brand"], ...rows]
            .map(r => r.map(v => `"${v}"`).join(","))
            .join("\n");

        const blob = new Blob(["\uFEFF" + csv], {type: "text/csv"});
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        const region = document.getElementById("globalRegion")?.value || "XX";
        a.download = `${region}_brand_gate.csv`;
        a.click();
    });

    // BrandGate Brand抽出
    document.getElementById("bgc-extract-brand")
    ?.addEventListener("click", async () => {

        const result = await showConfirmModal({
            contentHtml: `
                <h3>Brand Extraction</h3>

                <label style="display:block; margin:10px 0;">
                    <input type="checkbox" id="bgc-extract-ok-only" checked>
                    OK only
                </label>

                <div class="ui-confirm-actions">
                    <button
                        class="ui-confirm-btn ui-confirm-btn-cancel"
                        data-confirm="cancel">
                        Cancel
                    </button>

                    <button
                        class="ui-confirm-btn ui-confirm-btn-primary"
                        data-confirm="execute">
                        Execute
                    </button>
                </div>
            `
        });

        if (result !== "execute") return;

        const okOnly = document.getElementById("bgc-extract-ok-only")?.checked;

        const rows = Array.from(document.querySelectorAll("#bgc-table tbody tr"));

        const targetRows = rows.filter(tr => {
            const status = tr.children[1]?.textContent.trim();
            if (okOnly) return status === "OK" || status === "APPROVAL"; 
            return true;
        });

        const asins = targetRows.map(tr => tr.children[0]?.textContent.trim());

        const res = await fetch("/amazon/extract_brand", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                asins,
                country_code: document.getElementById("globalRegion")?.value
            })
        });

        const data = await res.json();

        data.forEach(b => {
            const t = bgcAllData.find(x => x.asin === b.asin);
            if (t) t.brand = b.brand || ""; 
        });        

        const tbodyBrand = document.querySelector("#bgc-brand-table tbody");

        tbodyBrand.innerHTML = "";

        data.forEach(r => {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${r.asin}</td>
                <td>${r.brand || ""}</td>
            `;

            tbodyBrand.appendChild(tr);
        });
    });    
});
