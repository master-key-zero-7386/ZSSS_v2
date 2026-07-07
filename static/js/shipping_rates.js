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
                <td><input type="text" class="fixed-shipping-price" value="${r.fixed_shipping_price || ""}"></td>                
                <td><input type="text" class="memo" value="${r.memo || ""}"></td>
            `;

            // --- ▼ ここを修正：Carrier入力時にカンマ除去（入口正規化） ▼ ---
            tr.querySelectorAll(
                ".carrier-1-price, .carrier-2-price, .carrier-3-price, .fixed-shipping-price, .memo"
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
                !e.target.classList.contains("carrier-3-price") &&
                !e.target.classList.contains("fixed-shipping-price")) {
                return;
            }

            const row = e.target.closest("tr");
            if (!row) return;

            // --- ▼ 固定送料が入力されていれば、それを優先して最安値欄に表示 ▼ ---
            const fixedInput = row.querySelector(".fixed-shipping-price");
            const fixedValue = parseInt(fixedInput?.value, 10);

            const minInput = row.querySelector(".min-price");

            if (!isNaN(fixedValue) && fixedValue > 0) {
                minInput.value = fixedValue;
                return; // Carrier1〜3の計算はスキップ
            }

            const prices = [];

            row.querySelectorAll(".carrier-1-price, .carrier-2-price, .carrier-3-price")
                .forEach(input => {
                    const v = parseInt(input.value, 10);
                    if (!isNaN(v) && v > 0) prices.push(v);
                });

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
            !input.classList.contains("fixed-shipping-price") &&
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
            if (tds.length < 8) return;

            const weight_from_g = parseInt(tds[0].querySelector("input")?.value, 10);
            const weight_to_g   = parseInt(tds[1].querySelector("input")?.value, 10);

            const carrier_1_price = parseInt(tds[2].querySelector("input")?.value || "0", 10);
            const carrier_2_price = parseInt(tds[3].querySelector("input")?.value || "0", 10);
            const carrier_3_price = parseInt(tds[4].querySelector("input")?.value || "0", 10);

            const fixedRaw = tds[6].querySelector("input")?.value;            
            const fixed_shipping_price = fixedRaw ? parseInt(fixedRaw, 10) : null;

            const memo = tds[7].querySelector("input")?.value || "";

            rows.push({
                weight_from_g,
                weight_to_g,
                carrier_1_price,
                carrier_2_price,
                carrier_3_price,
                fixed_shipping_price,
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

    // --- ▼ SECTION 09: 他マーケットの送料をCarrier列単位でコピー ▼ ---
    document.getElementById("copy-from-other-market")?.addEventListener("click", async function () {

        const region = document.getElementById("globalRegion")?.value;
        if (!region) {
            alert("リージョンが選択されていません");
            return;
        }

        // コピー元にできる（＝送料表がすでにある）マーケット一覧を取得
        const res = await fetch("/api/shipping-rates/copy-source-list");
        const copySourceData = await res.json();

        const copyOptionsHtml = copySourceData.marketplace_ids
            .filter(row => row.country_code !== region.toUpperCase())
            .map(row => `<option value="${row.country_code}">${row.country_code}</option>`)
            .join("");

        if (!copyOptionsHtml) {
            alert("コピー元にできる他のマーケットがありません");
            return;
        }

        // コピー元マーケット & コピーする列を選んでもらうポップアップ
        const result = await showConfirmModal({
            contentHtml: `
                <h3>他マーケットからコピー</h3>
                <p>コピー元のマーケットと、コピーするCarrier列を選んでください。</p>

                <div style="margin-bottom:12px;">
                    <label style="display:block; margin-bottom:4px;">コピー元マーケット</label>
                    <select id="copy-source-marketplace-existing">
                        ${copyOptionsHtml}
                    </select>
                </div>

                <div style="margin-bottom:12px;">
                    <label style="display:block; margin-bottom:6px;">コピーする列</label>
                    <label style="display:block;"><input type="checkbox" id="copy-col-carrier1" checked> Carrier 1</label>
                    <label style="display:block;"><input type="checkbox" id="copy-col-carrier2"> Carrier 2</label>
                    <label style="display:block;"><input type="checkbox" id="copy-col-carrier3"> Carrier 3</label>
                    <label style="display:block;"><input type="checkbox" id="copy-col-fixed"> 固定送料</label>
                </div>

                <p style="color:#c0392b; font-size:13px;">
                    ※ ここではまだ保存されません。内容を確認してから「保存」ボタンを押してください。
                </p>

                <div class="ui-confirm-actions">
                    <button class="ui-confirm-btn ui-confirm-btn-cancel" data-confirm="cancel">キャンセル</button>
                    <button class="ui-confirm-btn ui-confirm-btn-primary" data-confirm="copy">コピーする</button>
                </div>
            `
        });

        if (result !== "copy") return;

        const sourceCode = document.getElementById("copy-source-marketplace-existing")?.value;
        if (!sourceCode) return;

        const copyCarrier1 = document.getElementById("copy-col-carrier1")?.checked;
        const copyCarrier2 = document.getElementById("copy-col-carrier2")?.checked;
        const copyCarrier3 = document.getElementById("copy-col-carrier3")?.checked;
        const copyFixed = document.getElementById("copy-col-fixed")?.checked; 

        if (!copyCarrier1 && !copyCarrier2 && !copyCarrier3 && !copyFixed) {   // ★条件にも追加
            alert("コピーする列を1つ以上選択してください");
            return;
        }


        // コピー元マーケットの送料データを取得（既存の「読み込みAPI」を流用。保存はしない）
        const sourceRes = await fetch("/api/shipping-rates/load?marketplace_id=" + encodeURIComponent(sourceCode));
        const sourceData = await sourceRes.json();

        if (sourceData.status !== "success") {
            showToast("コピー元データの取得に失敗しました");
            return;
        }

        // 重量帯(From/To)をキーにして、コピー元の行をすぐ探せるようにする
        const sourceRowMap = new Map();
        sourceData.rows.forEach(r => {
            sourceRowMap.set(`${r.weight_from_g}_${r.weight_to_g}`, r);
        });

        // 画面上の表に、選んだ列だけ反映する（保存はまだしない）
        document.querySelectorAll("#shipping-rates-body tr").forEach(tr => {
            const tds = tr.querySelectorAll("td");
            if (tds.length < 8) return;   // ★列が増えたので7→8に変更

            const weightFrom = tds[0].querySelector("input")?.value;
            const weightTo = tds[1].querySelector("input")?.value;

            const sourceRow = sourceRowMap.get(`${weightFrom}_${weightTo}`);
            if (!sourceRow) return;

            if (copyCarrier1) tds[2].querySelector("input").value = sourceRow.carrier_1_price || "";
            if (copyCarrier2) tds[3].querySelector("input").value = sourceRow.carrier_2_price || "";
            if (copyCarrier3) tds[4].querySelector("input").value = sourceRow.carrier_3_price || "";
            if (copyFixed) tds[6].querySelector("input").value = sourceRow.fixed_shipping_price || "";
        });

        recalcAllMinPrices();

        showToast("コピーしました。内容を確認して保存してください");
    });    

    // --- ▼ SECTION 10: 送料表をCSVに書き出す ▼ ---
    document.getElementById("export-shipping-csv")?.addEventListener("click", function () {

        const region = document.getElementById("globalRegion")?.value;
        if (!region) {
            alert("リージョンが選択されていません");
            return;
        }

        // ヘッダー行
        const rows = [["From(g)", "To(g)", "Carrier1", "Carrier2", "Carrier3", "固定送料", "Memo"]];

        document.querySelectorAll("#shipping-rates-body tr").forEach(tr => {
            const tds = tr.querySelectorAll("td");
            if (tds.length < 8) return;

            rows.push([
                tds[0].querySelector("input")?.value || "",
                tds[1].querySelector("input")?.value || "",
                tds[2].querySelector("input")?.value || "",
                tds[3].querySelector("input")?.value || "",
                tds[4].querySelector("input")?.value || "",
                tds[6].querySelector("input")?.value || "",  // 固定送料
                tds[7].querySelector("input")?.value || ""   // メモ
            ]);
        });

        // カンマや改行を含んでもズレないよう、各項目を""で囲む
        const csv = rows
            .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(","))
            .join("\n");

        // \uFEFF は Excel で開いた時に文字化けしないためのおまじない
        const blob = new Blob(["\uFEFF" + csv], { type: "text/csv" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${region.toUpperCase()}_shipping_rates.csv`;
        a.click();
    });

    // --- ▼ SECTION 11: CSVから送料表を取り込む ▼ ---
    document.getElementById("import-shipping-csv-btn")?.addEventListener("click", function () {
        // 隠しファイル選択欄を代わりにクリックさせる
        document.getElementById("import-shipping-csv-input")?.click();
    });

    document.getElementById("import-shipping-csv-input")?.addEventListener("change", function (e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();

        reader.onload = function (evt) {
            const text = evt.target.result;

            // --- 簡易CSVパーサー（""で囲まれた項目にも対応） ---
            const lines = text.split(/\r?\n/).filter(l => l.trim() !== "");
            const parsedRows = lines.map(line => {
                const result = [];
                let cur = "";
                let inQuotes = false;
                for (let i = 0; i < line.length; i++) {
                    const ch = line[i];
                    if (ch === '"') {
                        if (inQuotes && line[i + 1] === '"') { cur += '"'; i++; }
                        else { inQuotes = !inQuotes; }
                    } else if (ch === "," && !inQuotes) {
                        result.push(cur); cur = "";
                    } else {
                        cur += ch;
                    }
                }
                result.push(cur);
                return result;
            });

            // 先頭行はヘッダーなので飛ばす
            const dataRows = parsedRows.slice(1);

            const csvRowMap = new Map();
            dataRows.forEach(cols => {
                const [from, to, c1, c2, c3, fixed, memo] = cols;
                csvRowMap.set(`${from}_${to}`, { c1, c2, c3, fixed, memo });
            });

            document.querySelectorAll("#shipping-rates-body tr").forEach(tr => {
                const tds = tr.querySelectorAll("td");
                if (tds.length < 8) return;

                const weightFrom = tds[0].querySelector("input")?.value;
                const weightTo = tds[1].querySelector("input")?.value;

                const csvRow = csvRowMap.get(`${weightFrom}_${weightTo}`);
                if (!csvRow) return;

                tds[2].querySelector("input").value = csvRow.c1 || "";
                tds[3].querySelector("input").value = csvRow.c2 || "";
                tds[4].querySelector("input").value = csvRow.c3 || "";
                tds[6].querySelector("input").value = csvRow.fixed || "";
                tds[7].querySelector("input").value = csvRow.memo || "";
            });

            recalcAllMinPrices();

            showToast("CSVを取り込みました。内容を確認して保存してください");

            // 同じファイルをもう一度選んでも反応するようにリセット
            e.target.value = "";
        };

        reader.readAsText(file, "UTF-8");
    });

}) // "DOMContentLoaded" 終了



