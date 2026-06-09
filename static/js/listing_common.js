// =====================================================
// ファイル名: static/js/listing_common.js
// 共通機能（pre / all 共通のDOM・操作系）
// =====================================================

// === 二重読み込み防止ガード ===
if (window.__listingCommonLoaded) {

} else {
    window.__listingCommonLoaded = true;

    // ↓↓↓ ここから下に、今まで listing_common.js に書いてた処理を全部入れる ↓↓↓

    const style = document.createElement("style");
    style.textContent = `

table.dataTable td:last-child {
    position: relative;
}
    
.listing-action-wrap {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    gap: 8px;
}

.trash-icon {
    font-size: 18px;   /* ← 好きなサイズに */
}
    
`;

document.head.appendChild(style);

// --- ▼ SECTION 01: 最新取得ボタン生成（pre / all 共通） ▼ ---
window.attachRefreshButtons = function (tableSelector) {

    const currentTab = tableSelector.includes("all") ? "all" : "pre";
    const country_code = document.getElementById("globalRegion")?.value;

    if (!country_code) return;

    document.querySelectorAll(`${tableSelector} tbody tr`).forEach(row => {

        if (row.querySelector(".dataTables_empty")) return;

        const asinCell = row.querySelector("strong.asin-cell");
        const asin = asinCell ? asinCell.textContent.trim() : "";

        let actionCell = row.querySelector("td:last-child");
        if (!actionCell) {
            actionCell = document.createElement("td");
            row.appendChild(actionCell);
        }

        let wrap = actionCell.querySelector(".listing-action-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "listing-action-wrap";
            actionCell.appendChild(wrap);
        }

        if (wrap.querySelector(".refresh-now-btn")) return;

        const refreshBtn = document.createElement("button");
        refreshBtn.className = "btn-blue refresh-now-btn";
        refreshBtn.textContent = "最新取得";

        refreshBtn.addEventListener("click", async () => {

            refreshBtn.disabled = true;
            refreshBtn.textContent = "取得中...";

            try {

                await fetch("/run_refresh_now", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        asin: asin,
                        country_code: country_code
                    })
                });

                if (currentTab === "all") {

                    const table = $("#alllistingtable").DataTable();

                    sessionStorage.setItem("all_current_page", table.page());

                    window.loadalllisting(country_code);

                } else {

                    const table = $("#prelistingtable").DataTable();
                    sessionStorage.setItem("pre_current_page", table.page());

                    window.loadprelisting(country_code);
                }

            } catch (e) {

                alert("最新取得失敗");

            } finally {

                refreshBtn.disabled = false;
                refreshBtn.textContent = "最新取得";
            }
        });

        wrap.prepend(refreshBtn);
    });
};

// --- ▼ SECTION 02: 登録ボタン生成（pre / all 共通） ▼ ---
window.attachRegisterButtons = function (tableSelector) {
    const currentTab = tableSelector.includes("all") ? "all" : "pre";
    const country_code = document.getElementById("globalRegion")?.value;
    // プルダウン未選択時は処理しない
    if (!country_code) return;

    document.querySelectorAll(`${tableSelector} tbody tr`).forEach(row => {
        if (row.querySelector(".dataTables_empty")) return;
        const asinCell = row.querySelector("strong.asin-cell");
        const asin = asinCell ? asinCell.textContent.trim().toLowerCase() : "(asin不明)";

        let actionCell = row.querySelector("td:last-child");
        if (!actionCell) {
            actionCell = document.createElement("td");
            row.appendChild(actionCell);
        }
        
        // これを追加（ラッパー作成）
        let wrap = actionCell.querySelector(".listing-action-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "listing-action-wrap";
            actionCell.appendChild(wrap);
        }        

        if (wrap.querySelector(".register-btn")) return;

        const registerBtn = document.createElement("button");
        registerBtn.className = "btn-blue register-btn";
        registerBtn.textContent = "LIST";


        registerBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/listing/move_to_all", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ asin, country_code, status: currentTab })
                });
                const data = await res.json();
                const status = (data.status || "").toString().trim().toLowerCase();

                if (status === "ok" || status === "success") {
                    window.showToast("登録完了", "success");

                    if (currentTab === "pre") {
                        const table = $(tableSelector).DataTable();
                        table.row($(registerBtn).closest("tr")).remove().draw(false);
                    } else {
                        window.loadalllisting(country_code, document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all'); 
                    }
                } else {
                    console.warn("move_to_all failed:", data);
                    window.showToast("登録に失敗しました", "error");
                }
            } catch (err) {
                console.error("register error:", err);
                window.showToast("通信エラーが発生しました", "error");
            }
        });

        wrap.appendChild(registerBtn); 
    });

};

// --- ▼ SECTION 03: ごみ箱ボタン生成（pre / all 共通） ▼ ---
window.attachDeleteButtons = function (tableSelector) {
    const currentTab = tableSelector.includes("all") ? "all" : "pre";
    const country_code = document.getElementById("globalRegion")?.value;
    if (!country_code) return;

    document.querySelectorAll(`${tableSelector} tbody tr`).forEach(row => {
        if (row.querySelector(".dataTables_empty")) return;

        const asinCell = row.querySelector("strong.asin-cell");
        const asin = asinCell ? asinCell.textContent.trim() : "(asin不明)";
        const skuCell = row.querySelector(".sku-cell");
        const sku = skuCell ? skuCell.textContent.trim() : "";

        let actionCell = row.querySelector("td:last-child");
        if (!actionCell) {
            actionCell = document.createElement("td");
            row.appendChild(actionCell);
        }

        // ★ register と同じ wrap を必ず使う
        let wrap = actionCell.querySelector(".listing-action-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "listing-action-wrap";
            actionCell.appendChild(wrap);
        }

        // ★ 存在チェックは wrap 基準
        if (wrap.querySelector(".delete-btn")) return;

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "delete-btn";
        deleteBtn.innerHTML = '<i class="fa-solid fa-trash-can trash-icon"></i>';
        deleteBtn.style.cssText = "border:none;background:transparent;cursor:pointer;";

        deleteBtn.addEventListener("click", async () => {
            try {
                const res = await fetch("/listing/delete_item", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ asin, sku, country_code, status: currentTab })
                });
                const data = await res.json();

                if (data.status === "success" || data.status === "ok") {
                    const table = $(tableSelector).DataTable();
                    table.row($(deleteBtn).closest("tr")).remove().draw(false);
                    window.showToast("削除しました", "success");
                } else {
                    window.showToast("削除に失敗しました", "error");
                }
            } catch (err) {
                console.error("delete error:", err);
                window.showToast("通信エラーが発生しました", "error");
            }
        });

        // ★ 位置調整は一切せず wrap に追加
        wrap.appendChild(deleteBtn);
    });
};

// --- ▼ SECTION 04: 全選択 / 全解除（行チェックボックス） ▼ ---
window.setupRowSelectionHandlers = function () {
    const pairs = [
        { toggle: "#toggleAllRows", selector: ".row-select" },
        { toggle: "#toggleAllRowsAll", selector: ".row-select" }
    ];

    pairs.forEach(({ toggle, selector }) => {
        $(document).on("change", toggle, function () {
            const checked = $(this).is(":checked");
            $(selector).prop("checked", checked);
        });
        $(document).on("change", selector, function () {
            const total = $(`${selector}`).length;
            const checkedCount = $(`${selector}:checked`).length;
            $(toggle).prop("checked", total === checkedCount);
        });
    });
};

// --- ▼ SECTION 05: 共通ハンドラ初期化 ▼ ---
window.initCommonHandlers = function () {
    window.setupRowSelectionHandlers();
};

// --- ▼ SECTION 06: 情報取得状態 編集UI制御（pre / all 共通） ▼ ---
$(document).on("click", ".edit-btn", function () {
    // const cell = $(this).closest("td");
    const cell = $(this).closest(".listing-strategy-summary, .listing-strategy-edit").parent();

    cell.find(".listing-strategy-summary").hide();
    cell.find(".listing-strategy-edit").show();
});

// --- ▼ SECTION 07: 編集取消（表示を戻す） ▼ ---
$(document).on("click", ".cancel-edit-btn", function () {
    const cell = $(this).closest("td");
    cell.find(".listing-strategy-edit").hide();
    cell.find(".listing-strategy-summary").show();             
});

// --- ▼ SECTION 08: ALL 出品戦略 保存処理（ALL専用） ▼ ---
$(document).on("click", ".save-edit-btn", async function () {

    const $cell = $(this).closest("td");
    const $row  = $(this).closest("tr");

    const asin   = $row.find(".asin-cell").text().trim();
    const country_code = $("#globalRegion").val();
    if (!asin || !country_code) return;

    // --- 入力値取得 ---
    const overridePrice = $cell.find(".edit-sale-price").val();
    const qty           = $cell.find(".edit-qty").val();
    const sellout       = $cell.find(".edit-sellout").is(":checked");
    const ht            = $cell.find(".edit-ht").val();

    // --- 送信用データ ---
    const payload = {
        asin,
        country_code,
        override_price: overridePrice === "" ? null : overridePrice,
        strategy_quantity: qty === "" ? 0 : Number(qty),
        strategy_sellout: sellout ? 1 : 0,
        strategy_handling_time: ht === "" || Number(ht) <= 0 ? 7 : Number(ht),
    };

    try {
        const res = await fetch("/listing/update_strategy", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (data.status !== "success") {
            window.showToast("保存に失敗しました", "error");
            return;
        }

        // --- 表示更新（即時反映） ---
        $cell.find(".disp-sale-price").text(
            payload.override_price !== null ? payload.override_price : "ー"
        );
        $cell.find(".disp-ht").text(`${payload.strategy_handling_time}日`);

        // 編集UIを閉じる（ALL仕様）
        $cell.find(".listing-strategy-edit").hide();
        $cell.find(".listing-strategy-summary").show();

        window.showToast("出品戦略を保存しました", "success");

    } catch (e) {
        console.error("[update_strategy]", e);
        window.showToast("通信エラーが発生しました", "error");
    }
});


document.addEventListener("DOMContentLoaded", () => {

    // --- ▼ SECTION 09: サイドバークリックで pre / all を切り替え ▼
    document.querySelectorAll(".sidebar-btn").forEach(btn => {
        btn.addEventListener("click", () => {

            const target = btn.getAttribute("data-target");
            const country_code = document.getElementById("globalRegion")?.value;

            if (!country_code) return;

            // ▼ ここ追加（状態リセット）
            document.querySelectorAll(".row-select").forEach(cb => cb.checked = false);
            const toggle = document.getElementById("toggleAllRows");
            if (toggle) toggle.checked = false;

            const runPre = document.getElementById("bulkActionRunPre");
            const runAll = document.getElementById("bulkActionRunAll");
            if (runPre) runPre.disabled = true;
            if (runAll) runAll.disabled = true;
            // ▲ ここまで

            if (target === "prelisting") {
                window.loadprelisting(country_code, document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all');
            } else if (target === "listing") {
                window.loadalllisting(country_code, document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all');
            }
        });
    });


    // === ▼ 09-01: 検索ワードクリア（Pre） ▼ ===
    const presearchInput = document.getElementById("preListingSearchInput");

    // === ▼ 09-02: 検索ワードクリア（ALL） ▼ ===
    const allsearchInput = document.getElementById("allListingSearchInput");    

    // === ▼ 09-03: Pre 検索実行 ▼ ===
    const preSearchBtn = document.getElementById("preListingSearchBtn");

    if (preSearchBtn) {
        preSearchBtn.addEventListener("click", function () {

            const keyword = document.getElementById("preListingSearchInput").value.trim();
            const detail = document.getElementById("preListingDetailSearch").checked;
            const country_code = document.getElementById("globalRegion")?.value;
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';

            if (!keyword) {
                
                window.loadprelisting(country_code, infoStatus);

                return;
            }

            window.searchPreListing(keyword, detail, country_code, infoStatus); 

        });
    }

    // === ▼ 09-04: ALL 検索実行 ▼ ===
    const allSearchBtn = document.getElementById("allListingSearchBtn");

    if (allSearchBtn) {
        allSearchBtn.addEventListener("click", function () {

            const keyword = document.getElementById("allListingSearchInput").value.trim();
            const detail = document.getElementById("allListingDetailSearch").checked;
            const country_code = document.getElementById("globalRegion")?.value;
            const infoStatus = document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all';
            

            if (!keyword) {
                window.loadalllisting(country_code, infoStatus);
                return;
            }

            window.searchAllListing(keyword, detail, country_code, infoStatus);

        });
    }    

    // === ▼ 09-04A: Pre 検索クリアボタン ▼ ===
    const preSearchClear = document.getElementById("preListingSearchClear");

    if (presearchInput && preSearchClear) {

        presearchInput.addEventListener("input", function () {

            preSearchClear.style.display = this.value ? "block" : "none";

        });

        preSearchClear.addEventListener("click", function () {

            presearchInput.value = "";
            preSearchClear.style.display = "none";
            presearchInput.focus();

        });

    } 
    
    // === ▼ 09-04B: ALL 検索クリアボタン ▼ ===
    const allSearchClear = document.getElementById("allListingSearchClear");

    if (allsearchInput && allSearchClear) {

        allsearchInput.addEventListener("input", function () {

            allSearchClear.style.display = this.value ? "block" : "none";

        });

        allSearchClear.addEventListener("click", function () {

            allsearchInput.value = "";
            allSearchClear.style.display = "none";
            allsearchInput.focus();

        });

    }    

    // === ▼ 09-05: Pre Enter検索 ▼ ===
    if (presearchInput) {
        presearchInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                preSearchBtn.click();
            }
        });
    }

    // === ▼ 09-06: ALL Enter検索 ▼ ===
    if (allsearchInput) {
        allsearchInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                allSearchBtn.click();
            }
        });
    }   
    
    // === ▼ 09-07: Pre DB検索 ▼ ===
    window.searchPreListing = function(keyword, detail, country_code) {
        const sort = document.getElementById("preListingSort")?.value;

        const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';

        fetch(`/listing/search_listing?mode=pre&keyword=${encodeURIComponent(keyword)}&detail=${detail}&country_code=${country_code}&sort=${sort}&info_status=${infoStatus}`)
        .then(res => res.json())
        .then(data => {

            const table = $.fn.dataTable.isDataTable('#prelistingtable')
                ? $('#prelistingtable').DataTable()
                : null;          

            if (!table) return;

            table.clear();
            table.rows.add(data);
            table.draw();

        });
    };

    // === ▼ 09-08: ALL DB検索 ▼ ===
    window.searchAllListing = function(keyword, detail, country_code) {

        const sort = document.getElementById("allListingSort")?.value;

        const infoStatus = document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all';
        
        fetch(`/listing/search_listing?mode=all&keyword=${encodeURIComponent(keyword)}&detail=${detail}&country_code=${country_code}&sort=${sort}&info_status=${infoStatus}`)
        .then(res => res.json())
        .then(data => {

            const table = $('#alllistingtable').DataTable();

            table.clear();
            table.rows.add(data);
            table.draw();

        });

    };    

    // === ▼ SECTION 10: チェックで実行ボタン有効化 ▼
    document.addEventListener("change", function(e){

        if (e.target.id === "toggleAllRows") {

            const table = e.target.closest("table");

            const checked = e.target.checked;

            table.querySelectorAll(".row-select").forEach(cb=>{
                cb.checked = checked;
            });
        }

        if(
            !e.target.classList.contains("row-select") &&
            e.target.id !== "toggleAllRows"
        ) return;

        const table = e.target.closest("table");

        const hasChecked = table.querySelectorAll(".row-select:checked").length > 0;

        const runPre = document.getElementById("bulkActionRunPre");
        const runAll = document.getElementById("bulkActionRunAll");

        if(runPre) runPre.disabled = !hasChecked;
        if(runAll) runAll.disabled = !hasChecked;

    });

    // --- ▼ SECTION 11: Pre 一括操作 実行 ▼
    document.getElementById("bulkActionRunPre").addEventListener("click", async function () {

        const action = document.getElementById("bulkActionSelectPre").value;

        if (!action) {
            alert("操作を選択してください");
            return;
        }

        const selected = [];

        document.querySelectorAll("#prelistingtable .row-select:checked").forEach(cb => {
            selected.push(cb.dataset.asin);
        });

        if (selected.length === 0) {
            alert("選択されていません");
            return;
        }

        if (action === "move_to_all") {

            const country_code = document.getElementById("globalRegion")?.value;

            fetch("/listing/bulk_move_to_all", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    asins: selected,
                    country_code: country_code
                })
            })
            .then(res => res.json())
            .then(data => {

                if (country_code) {
                    window.loadprelisting(country_code);
                }
                window.showToast("登録完了", "success"); 
            });
        }

        if (action === "brand_check") {

            const country_code = document.getElementById("globalRegion")?.value;

            // --- ▼ Checking 表示 ▼ ---
            selected.forEach(asin => {

                const row = document.querySelector(`#prelistingtable .row-select[data-asin="${CSS.escape(asin)}"]`)?.closest("tr");
                if (!row) return;

                const resultEl = row.querySelector(".bg-result");
                if (!resultEl) return;

                resultEl.innerText = "Checking...";
                resultEl.style.color = "#999";

            });

            const res = await fetch("/amazon/brand_gate_check", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    asins: selected,
                    country_code: country_code
                })
            });

            const data = await res.json();

            data.forEach(r => {

                const cb = document.querySelector(`#prelistingtable .row-select[data-asin="${CSS.escape(r.asin)}"]`);
                const row = cb ? cb.closest("tr") : null; 

                if (!row) return;

                const resultEl = row.querySelector(".bg-result");
                if (!resultEl) return;

                resultEl.innerText = r.status || "-";

                if (r.status === "OK") {
                    resultEl.style.color = "#28a745";
                } else if (r.status === "APPROVAL") {
                    resultEl.style.color = "#fd7e14";
                } else if (r.status) {
                    resultEl.style.color = "#dc3545";
                } else {
                    resultEl.style.color = "#999";
                }

            });            

            return;
        }        
        
        if (action === "delete") {

            const country_code = document.getElementById("globalRegion")?.value;

            // --- ▼ 削除確認 ---
            if (!confirm(`${selected.length}件削除します。実行しますか？`)) {
                return;
            }

            await fetch("/listing/bulk_delete_items", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    items: selected.map(asin => {
                        const el = document.querySelector(`#prelistingtable .row-select[data-asin="${CSS.escape(asin)}"]`);
                        if (!el) return null;

                        const row = el.closest("tr");

                        const sku = row.querySelector(".sku-cell")?.textContent.trim();
                        
                        return {
                            sku: sku,
                            country_code: country_code
                        };

                    }).filter(x => x !== null),
                    status: "pre"
                })
            });
 
            const table = $('#prelistingtable').DataTable();

            document.querySelectorAll("#prelistingtable .row-select:checked").forEach(cb => {
                table.row($(cb).closest("tr")).remove();
            });

            table.draw();            

            if (country_code) {
                window.loadprelisting(country_code);
            }
            window.showToast("削除完了", "success");
        }   

    });    

    // --- ▼ SECTION 12: ALL 一括操作 実行 ▼ ---
    document.getElementById("bulkActionRunAll").addEventListener("click", async function () {

        const action = document.getElementById("bulkActionSelectAll").value;

        if (action === "brand_check") {

            const country_code = document.getElementById("globalRegion")?.value;

            const asins = [];

            document.querySelectorAll("#alllistingtable .row-select:checked").forEach(cb => {
                const row = cb.closest("tr");
                const asin = row.querySelector("strong.asin-cell")?.textContent.trim();
                if (asin) asins.push(asin);
            });

            // --- ▼ Checking 表示 ▼ ---
            asins.forEach(asin => {

                const row = document.querySelector(`#alllistingtable .row-select[data-asin="${CSS.escape(asin)}"]`)?.closest("tr");
                if (!row) return;

                const resultEl = row.querySelector(".bg-result");
                if (!resultEl) return;

                resultEl.innerText = "Checking...";
                resultEl.style.color = "#999";

            });

            const res = await fetch("/amazon/brand_gate_check", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    asins: asins,
                    country_code: country_code
                })
            });

            const data = await res.json();

            data.forEach(r => {

                const cb = document.querySelector(`#alllistingtable .row-select[data-asin="${CSS.escape(r.asin)}"]`);
                const row = cb ? cb.closest("tr") : null;

                if (!row) return;

                const resultEl = row.querySelector(".bg-result");
                if (!resultEl) return;

                resultEl.innerText = r.status || "-";

                if (r.status === "OK") {
                    resultEl.style.color = "#28a745";
                } else if (r.status === "APPROVAL") {
                    resultEl.style.color = "#fd7e14";
                } else if (r.status) {
                    resultEl.style.color = "#dc3545";
                } else {
                    resultEl.style.color = "#999";
                }

            });

            return;
        }

        if (!action) {
            alert("操作を選択してください");
            return;
        }

        if (action !== "delete") return;

        const country_code = document.getElementById("globalRegion")?.value;

        const items = [];

        document.querySelectorAll("#alllistingtable .row-select:checked").forEach(cb => {

            const row = cb.closest("tr");

            const asin = row.querySelector("strong.asin-cell")?.textContent.trim();
            const sku  = row.querySelector(".sku-cell")?.textContent.trim();

            items.push({
                asin,
                sku,
                country_code,
                status: "listed"
            });

        });

        if (items.length === 0) {
            alert("選択されていません");
            return;
        }

        // --- ▼ 削除確認 ---
        if (!confirm(`${items.length}件削除します。実行しますか？`)) {
            return;
        }        

        await fetch("/listing/bulk_delete_items", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ items, status: "listed" })
        });

        const table = $('#alllistingtable').DataTable();   
        const currentPage = table.page();                  

        if (country_code) {
            window.loadalllisting(country_code, document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all');
        }
        window.showToast("削除完了", "success");
    });

});

// --- ▼ SECTION 13: Listing共通：ASINセルクリックコピー ▼ --- 
document.addEventListener("click", function (e) {

    const cell = e.target.closest(".asin-cell"); // ここを修正
    if (!cell) return; // ここを修正

    const asin = cell.textContent.trim(); // ここを修正
    if (!asin) return;

    // --- ▼ クリップボード処理（HTTP / HTTPS 両対応）▼ ---
    if (navigator.clipboard && navigator.clipboard.writeText) { 
        navigator.clipboard.writeText(asin).then(() => {
            if (window.showCopyNotification) {
                window.showCopyNotification("コピーしました", cell);
            }
        }).catch(err => {
            console.error("コピー失敗:", err);
        });
    } else { // ここを追加
        const tmp = document.createElement("textarea"); 
        tmp.value = asin; // ここを追加
        document.body.appendChild(tmp);
        tmp.select(); // ここを追加
        document.execCommand("copy"); 
        document.body.removeChild(tmp); 

        if (window.showCopyNotification) {
            window.showCopyNotification("コピーしました", cell);
        }
    }

});
        // === 通知表示処理（右上フェードアウト） ===
        window.showCopyNotification = function (message, targetEl) {
            const rect = targetEl.getBoundingClientRect();

            const notif = document.createElement("div");
            notif.textContent = message;
            notif.style.position = "absolute";
            notif.style.left = (rect.left + window.scrollX) + "px";
            notif.style.top = (rect.top + window.scrollY - 28) + "px";
            notif.style.background = "rgba(23, 162, 184, 0.95)";
            notif.style.color = "#fff";
            notif.style.padding = "4px 8px";
            notif.style.borderRadius = "4px";
            notif.style.fontSize = "12px";
            notif.style.pointerEvents = "none";
            notif.style.opacity = "1";
            notif.style.transition = "opacity 1.5s ease";
            notif.style.zIndex = "9999";

            document.body.appendChild(notif);

            setTimeout(() => {
                notif.style.opacity = "0";
                setTimeout(() => notif.remove(), 800);
            }, 600);
        };

// --- ▼ SECTION 14: 行単位オーバーレイ（listing専用・初期定義） ▼ ---
function showRowOverlay(table, asin) {
    const row = table
        .rows()
        .nodes()
        .toArray()
        .find(tr => {
            const cell = tr.querySelector(".asin-cell");
            return cell && cell.dataset.asin === asin;
        });

    if (!row) return;

    const firstCell = row.querySelector("td");
    if (!firstCell) return;

    if (firstCell.querySelector(".row-overlay")) return;

    firstCell.style.position = "relative";

    const overlay = document.createElement("div");
    overlay.className = "row-overlay";
    overlay.innerHTML = `<div class="win-spinner"></div>`;

    firstCell.appendChild(overlay);
}

function hideRowOverlay(table, asin) {
    const row = table
        .rows()
        .nodes()
        .toArray()
        .find(tr => {
            const cell = tr.querySelector(".asin-cell");
            return cell && cell.dataset.asin === asin;
        });

    if (!row) return;

    const firstCell = row.querySelector("td");
    if (!firstCell) return;

    const overlay = firstCell.querySelector(".row-overlay");
    if (overlay) overlay.remove();
}
}
