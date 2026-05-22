// =====================================================
// ファイル名: static/js/shipping_rates.js
// 目的： 配送料金専用
// =====================================================

document.addEventListener("DOMContentLoaded", function () {
   
    let shippingRatesMode = "new";  
    const saveBtn = document.getElementById("save-shipping-rates");

    // --- ▼ SECTION 01: 送料設定 初期ロード（表示専用） ▼ ---
    function initShippingRatesSeed() {
        const select = document.getElementById("globalRegion");
        if (!select) {
            setTimeout(initShippingRatesSeed, 100);
            return;
        }

        const region = select.value;

        if (!region) {
            setTimeout(initShippingRatesSeed, 200);
            return;
        }

        localStorage.setItem("selectedRegion", region);

        fetch("/api/shipping-rates/load?marketplace_id=" + encodeURIComponent(region))
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    shippingRatesMode = data.mode;
                    renderShippingRowsFromDB(data.rows);
                    saveBtn.textContent = (data.mode === "new") ? "新規作成" : "保　存";
                }
            });
    }

    initShippingRatesSeed();

    const select = document.getElementById("globalRegion");
    if (select) {
        select.addEventListener("change", function () {
            initShippingRatesSeed();
        });
    }    

    // --- ▼ SECTION 02: DBから描画する唯一の関数 ▼ ---
    function renderShippingRowsFromDB(rows) {
        
        const tbody = document.getElementById("shipping-rates-body");
        if (!tbody) return;

        tbody.innerHTML = "";

        rows.forEach(r => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><input type="text" value="${r.weight_from_g}" disabled></td>
                <td><input type="text" value="${r.weight_to_g}" disabled></td>
                <td><input type="text" class="carrier-1-price" value="${r.carrier_1_price || ""}"></td>
                <td><input type="text" class="carrier-2-price" value="${r.carrier_2_price || ""}"></td>
                <td><input type="text" class="carrier-3-price" value="${r.carrier_3_price || ""}"></td>
                <td><input type="text" class="min-price" readonly tabindex="-1"></td>
                <td><input type="text" class="memo" value="${r.memo || ""}"></td>
            `;

            // --- ▼ ここを修正：Carrier入力時にカンマ除去（入口正規化） ▼ ---
            tr.querySelectorAll(
                ".carrier-1-price, .carrier-2-price, .carrier-3-price, .memo"
            ).forEach(input => {
                input.addEventListener("input", () => {
                    input.value = input.value.replace(/,/g, "");
                    recalcAllMinPrices();
                });
            });


            tbody.appendChild(tr);
        });

        resetTabOrder();

        recalcAllMinPrices();
    }

    // --- ▼ SECTION 03: 最安値自動計算（そのままでOK） ▼ ---
    document.addEventListener("input", function (e) {
        if (!e.target.classList.contains("carrier-1-price") &&
            !e.target.classList.contains("carrier-2-price") &&
            !e.target.classList.contains("carrier-3-price")) {
            return;
        }

        const row = e.target.closest("tr");
        if (!row) return;

        const prices = [];

        row.querySelectorAll(".carrier-1-price, .carrier-2-price, .carrier-3-price")
            .forEach(input => {
                const v = parseInt(input.value, 10);
                if (!isNaN(v) && v > 0) prices.push(v);
            });

        const minInput = row.querySelector(".min-price");
        minInput.value = prices.length ? Math.min(...prices) : "";
    });

    // --- ▼ SECTION 04: 最安値を全行再計算（描画後用） ▼ ---
    function recalcAllMinPrices() {
        document.querySelectorAll("#shipping-rates-body tr").forEach(row => {

            const carrierInputs = Array.from(
                row.querySelectorAll(".carrier-1-price, .carrier-2-price, .carrier-3-price")
            );

            const values = carrierInputs.map(input => {
                const v = parseInt(input.value, 10);
                return (!isNaN(v) && v > 0) ? v : null;
            });

            const validValues = values.filter(v => v !== null);
            const minPrice = validValues.length ? Math.min(...validValues) : null;

            const minInput = row.querySelector(".min-price");
            minInput.value = minPrice !== null ? minPrice : "";

            // --- ▼ ここを修正：採用キャリアの視覚強調 ▼ ---
            carrierInputs.forEach((input, idx) => {
                const td = input.closest("td");
                td.classList.remove("shipping-carrier-selected");

                if (minPrice !== null && values[idx] === minPrice) {
                    td.classList.add("shipping-carrier-selected");
                }
            });
            // --- ▲ ここを修正 ▲ ---
        });
    }

    // --- ▼ SECTION 05: Tabキー縦移動制御（キャリア列優先）▼ ---
    function resetTabOrder() {
        let tabIndex = 1;

        ["carrier-1-price", "carrier-2-price", "carrier-3-price"].forEach(className => {
            Array.from(document.querySelectorAll(`.${className}`)).forEach(input => {
                input.tabIndex = tabIndex++;
            });
        });
    }

    // --- ▼ SECTION 06: Enterキーで次行へ移動（同キャリア） ▼ ---
    document.addEventListener("keydown", function (e) {
        if (e.key !== "Enter") return;

        const input = e.target;
        if (!input.classList.contains("carrier-1-price") &&
            !input.classList.contains("carrier-2-price") &&
            !input.classList.contains("carrier-3-price") &&
            !input.classList.contains("memo"))  {
            return;
        }

        e.preventDefault();

        const td = input.closest("td");
        const tr = input.closest("tr");
        if (!td || !tr) return;

        const colIndex = td.cellIndex;
        const nextRow = e.shiftKey ? tr.previousElementSibling : tr.nextElementSibling;
        if (!nextRow) return;

        const nextInput = nextRow.cells[colIndex]?.querySelector("input");
        if (nextInput) {
            nextInput.focus();
            nextInput.select();
        }
    });

    // --- ▼ SECTION 07: 送料設定 保存処理 ▼ ---
    document.getElementById("save-shipping-rates")?.addEventListener("click", async function () {

        const region = document.getElementById("globalRegion")?.value;
        if (!region) {
            alert("リージョンが選択されていません");
            return;
        }

        if (shippingRatesMode === "new") {

            const res = await fetch("/api/shipping-rates/copy-source-list");
            const copySourceData = await res.json();

            const copyOptionsHtml = copySourceData.marketplace_ids
                .filter(row => row.country_code !== region.toUpperCase())
                .map(row => `
                    <option value="${row.country_code}">
                        ${row.country_code} を利用
                    </option>
                `)
                .join("");

            const result = await showConfirmModal({
                contentHtml: `
                    <h3>送料設定の新規作成</h3>
                    <p>このマーケットプレイスの送料表を新規作成します。</p>
                    <p>既存マーケットの送料表をコピーする場合は選択してください。</p>

                    <select id="copy-source-marketplace">
                        <option value="">空で新規作成</option>
                        ${copyOptionsHtml}
                    </select>

                    <div class="ui-confirm-actions">
                        <button
                            class="ui-confirm-btn ui-confirm-btn-cancel"
                            data-confirm="cancel">
                            キャンセル
                        </button>

                        <button
                            class="ui-confirm-btn ui-confirm-btn-primary"
                            data-confirm="create">
                            作成する
                        </button>
                    </div>
                `
            });

            if (result !== "create") return;

            fetch("/api/shipping-rates/init", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    marketplace_id: region,
                    copy_from_marketplace_id: document.getElementById("copy-source-marketplace")?.value || ""
                }) 
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    document.dispatchEvent(
                        new CustomEvent("zsss:regionChanged", { detail: { region } })
                    );
                }
            });

            return;
        }

        const rows = [];

        document.querySelectorAll("#shipping-rates-body tr").forEach(tr => {
            const tds = tr.querySelectorAll("td");
            if (tds.length < 7) return;

            const weight_from_g = parseInt(tds[0].querySelector("input")?.value, 10);
            const weight_to_g   = parseInt(tds[1].querySelector("input")?.value, 10);

            const carrier_1_price = parseInt(tds[2].querySelector("input")?.value || "0", 10);
            const carrier_2_price = parseInt(tds[3].querySelector("input")?.value || "0", 10);
            const carrier_3_price = parseInt(tds[4].querySelector("input")?.value || "0", 10);

            const memo = tds[6].querySelector("input")?.value || "";

            rows.push({
                weight_from_g,
                weight_to_g,
                carrier_1_price,
                carrier_2_price,
                carrier_3_price,
                memo
            });
        });

        // --- ▼ 未設定重量帯チェック（警告のみ） ▼ ---
        const emptyRows = rows.filter(r =>
            (!r.carrier_1_price || r.carrier_1_price <= 0) &&
            (!r.carrier_2_price || r.carrier_2_price <= 0) &&
            (!r.carrier_3_price || r.carrier_3_price <= 0)
        );

        if (emptyRows.length > 0) {

            const result = await showConfirmModal({
                contentHtml: `
                    <h3>送料未設定の警告</h3>

                    <p>
                        送料が未設定の重量帯が
                        <strong>${emptyRows.length}</strong> 行あります。
                    </p>
                    <p>このまま保存しますか？</p>

                    <div class="ui-confirm-actions">
                        <button
                            class="ui-confirm-btn ui-confirm-btn-cancel"
                            data-confirm="cancel">
                            キャンセル
                        </button>

                        <button
                            class="ui-confirm-btn ui-confirm-btn-primary"
                            data-confirm="save">
                            保存する
                        </button>
                    </div>
                `
            });

            if (result !== "save") return;
        }
        

        fetch("/api/shipping-rates/save", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                marketplace_id: region,
                rows: rows
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                showToast("保存しました");
            } else {
                showToast("保存に失敗しました");
            }
        })
        .catch(() => {
            showToast("通信エラーが発生しました");
        });
    });

    // --- ▼ SECTION 08: リージョン変更時：送料設定を再ロード ▼ ---
    document.addEventListener("zsss:regionChanged", function (e) {
        const region = e.detail?.region;
        if (!region) return;

        fetch("/api/shipping-rates/load?marketplace_id=" + encodeURIComponent(region))
            .then(r => r.json())
            .then(data => {
                if (data.status !== "success") return;

                shippingRatesMode = data.mode;
                renderShippingRowsFromDB(data.rows);
                saveBtn.textContent = (data.mode === "new") ? "新規作成" : "保　存";
            });
    });

}) // "DOMContentLoaded" 終了



