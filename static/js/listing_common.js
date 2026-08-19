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

table.dataTable td.col-action {
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

// --- ▼ SECTION 00: DataTable共通設定 ▼ ---
window.getCommonDataTableOptions = function() {

    return {

        pagingType: "simple_numbers",
        deferRender: false,
        stateSave: false,
        autoWidth: false,

        paging: true,
        pageLength: 100,
        lengthChange: false,

        searching: true,
        info: true,
        scrollX: false,

        dom: '<"top"i p>rt<"bottom"i p>',

        language: {
            info: "全 _TOTAL_ 件中 _START_ から _END_ 件を表示",
            infoEmpty: "0 件中 0 から 0 件を表示",
            paginate: {
                previous: "前へ",
                next: "次へ"
            }
        },

        drawCallback: function() {

            const api = this.api();
            const info = api.page.info();

            const current = info.page + 1;
            const total = info.pages;

            const container = $(api.table().container());
            const paginate = container.find(".dataTables_paginate");

            const start = Math.max(1, current - 10);
            const end = Math.min(total, current + 10);

            let html = '';

            // 前へ
            if (current > 1) {
                html += `<a class="paginate_button custom-prev" data-page="${current - 1}">前へ</a>`;
            } else {
                html += `<span class="paginate_button disabled">前へ</span>`;
            }

            // 1ページ
            html += `<a class="paginate_button ${current === 1 ? 'current' : ''}" data-page="1">1</a>`;

            // 前側 ...
            if (start > 2) {
                html += `<span class="ellipsis">...</span>`;
            }

            // 中央
            for (let p = start; p <= end; p++) {

                if (p === 1 || p === total) {
                    continue;
                }

                html += `
                    <a
                        class="paginate_button ${p === current ? 'current' : ''}"
                        data-page="${p}">
                        ${p}
                    </a>
                `;
            }

            // 後側 ...
            if (end < total - 1) {
                html += `<span class="ellipsis">...</span>`;
            }

            // 最終ページ
            if (total > 1) {
                html += `
                    <a
                        class="paginate_button ${current === total ? 'current' : ''}"
                        data-page="${total}">
                        ${total}
                    </a>
                `;
            }

            html += `
                <span style="margin-left:20px;">
                    Page
                    <input
                        type="number"
                        class="page-jump-input"
                        min="1"
                        max="${total}"
                        style="
                            width:50px;
                            height:36px;
                            text-align:center;">
                    <button class="page-jump-btn" style="height:36px;padding:0 10px;">
                        移動
                    </button>
                </span>
            `;

            // 次へ
            if (current < total) {
                html += `<a class="paginate_button custom-next" data-page="${current + 1}">次へ</a>`;
            } else {
                html += `<span class="paginate_button disabled">次へ</span>`;
            }

            paginate.html(html);

            paginate.off("click", "a.paginate_button");

            paginate.on("click", "a.paginate_button", function() {

                const page = parseInt($(this).data("page"));

                if (!page) {
                    return;
                }

                api.page(page - 1).draw("page");

            });

            paginate.off("click", ".page-jump-btn");

            paginate.on("click", ".page-jump-btn", function() {

                const scope = $(this).closest(".dataTables_paginate");

                const page = parseInt(
                    scope.find(".page-jump-input").val()
                );

                if (isNaN(page)) {
                    return;
                }

                if (page < 1 || page > total) {
                    return;
                }

                api.page(page - 1).draw("page");

            });

            // --- ▼ 登録総数（絞り込み無視のPre/ALL全体件数）を info 表示末尾に追加 ▼ ---
            const tableId = api.table().node().id;

            let grandTotal = null;
            let grandLabel = "";

            if (tableId === "prelistingtable") {
                grandTotal = window.preGrandTotalCount;
                grandLabel = "Pre登録総数";
            } else if (tableId === "alllistingtable") {
                grandTotal = window.allGrandTotalCount;
                grandLabel = "ALL登録総数";
            }

            if (grandTotal !== null && grandTotal !== undefined) {
                container.find(".dataTables_info").text(function(_i, text) {
                    return `${text}　（${grandLabel}：${grandTotal.toLocaleString()}）`;
                });
            }

            // --- ▼ 絞り込み・ページ切替でリストの高さが変わってもscrollイベントが
            //     発火しないため、再描画のたびにスクロールボタンの表示を再評価する ▼ ---
            if (typeof window.updateScrollButtons === "function") {
                window.updateScrollButtons();
            }

        }
    };
};

// --- ▼ 絞り込み条件を変えずにテーブルを再読み込みする操作（一括削除・一括最新取得・
//     一括登録など）の前に呼ぶと、再読み込み後も同じページに留まる ▼ ---
window.savePreListingPage = function() {
    if ($.fn.DataTable.isDataTable("#prelistingtable")) {
        sessionStorage.setItem("pre_current_page", $("#prelistingtable").DataTable().page());
    }
};
window.saveAllListingPage = function() {
    if ($.fn.DataTable.isDataTable("#alllistingtable")) {
        sessionStorage.setItem("all_current_page", $("#alllistingtable").DataTable().page());
    }
};

// --- ▼ SECTION 01: 最新取得ボタン生成（pre / all 共通） ▼ ---
window.attachRefreshButtons = function (tableSelector) {

    const currentTab = tableSelector.includes("all") ? "all" : "pre";
    const country_code = document.getElementById("globalRegion")?.value;

    if (!country_code) return;

    document.querySelectorAll(`${tableSelector} tbody tr`).forEach(row => {

        if (row.querySelector(".dataTables_empty")) return;

        const asinCell = row.querySelector("strong.asin-cell");
        const asin = asinCell ? asinCell.textContent.trim() : "";

        let actionCell = row.querySelector("td.col-action");
        if (!actionCell) {
            actionCell = document.createElement("td");
            actionCell.className = "col-action";
            row.insertBefore(actionCell, row.children[1] || null);
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

                const res = await fetch("/run_refresh_now", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        asin: asin,
                        country_code: country_code
                    })
                });

                const json = await res.json().catch(() => ({}));

                if (!res.ok || json.status === "error") {
                    console.error("run_refresh_now failed:", res.status, json.message);
                    window.showToast?.(`最新取得失敗: ${json.message || res.status}`, "error");
                    return;
                }

                if (currentTab === "all") {

                    window.saveAllListingPage();
                    window.loadalllisting(country_code);

                } else {

                    window.savePreListingPage();
                    window.loadprelisting(country_code);
                }

            } catch (e) {

                console.error("run_refresh_now error:", e);
                window.showToast?.("通信エラーが発生しました", "error");

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

        let actionCell = row.querySelector("td.col-action");
        if (!actionCell) {
            actionCell = document.createElement("td");
            actionCell.className = "col-action";
            row.insertBefore(actionCell, row.children[1] || null);
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
                        window.saveAllListingPage();
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

        let actionCell = row.querySelector("td.col-action");
        if (!actionCell) {
            actionCell = document.createElement("td");
            actionCell.className = "col-action";
            row.insertBefore(actionCell, row.children[1] || null);
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

// --- ▼ SECTION 07b: 送料区分 手動上書き ON/OFF（グレーアウト切替） ▼ ---
$(document).on("change", ".weight-override-toggle", function () {
    const $row = $(this).closest(".weight-override-row");
    const $select = $row.find(".weight-override-select");
    const $saveBtn = $row.find(".weight-override-save-btn");

    if ($(this).is(":checked")) {
        $select.prop("disabled", false).css("opacity", 1);
        $saveBtn.prop("disabled", false).css("opacity", 1);
    } else {
        $select.val("").prop("disabled", true).css("opacity", 0.4);
        $saveBtn.prop("disabled", true).css("opacity", 0.4);
        // OFFにした時点で自動計算に戻す（保存ボタンを待たない）
        saveWeightOverride($row, null);
    }
});

// --- ▼ SECTION 07c: 送料区分 手動上書き 保存処理 ▼ ---
async function saveWeightOverride($row, overrideWeightClass) {
    const asin = $row.data("asin");
    const country_code = $("#globalRegion").val();
    if (!asin || !country_code) return;

    try {
        const res = await fetch("/listing/update_shipping_override", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                asin,
                country_code,
                override_weight_class: overrideWeightClass,
            }),
        });

        const data = await res.json();
        if (data.status !== "success") {
            window.showToast("保存に失敗しました", "error");
            return;
        }

        const submitted = data.price_result && data.price_result.submitted;
        window.showToast(
            submitted
                ? "送料区分を保存し、Seller Centralへ送信しました"
                : "送料区分を保存しました（未出品/非ACTIVEのためSeller Centralへの送信は行われません）",
            "success"
        );

        // --- 請求重量・送料・出品価格が変わるため、一覧を再読込して最新値を表示 ---
        if ($.fn.DataTable.isDataTable("#alllistingtable")) {
            $("#alllistingtable").DataTable().ajax.reload(null, false);
        }

    } catch (e) {
        console.error("[update_shipping_override]", e);
        window.showToast("通信エラーが発生しました", "error");
    }
}

$(document).on("click", ".weight-override-save-btn", function () {
    const $row = $(this).closest(".weight-override-row");
    const selected = $row.find(".weight-override-select").val();

    if (!selected) {
        window.showToast("重量区分を選択してください", "error");
        return;
    }

    saveWeightOverride($row, Number(selected));
});

// --- ▼ SECTION 07d: 出品価格 手動固定 ON/OFF（グレーアウト切替） ▼ ---
$(document).on("change", ".price-override-toggle", function () {
    const $row = $(this).closest(".price-override-row");
    const $input = $row.find(".price-override-input");
    const $saveBtn = $row.find(".price-override-save-btn");

    if ($(this).is(":checked")) {
        $input.prop("disabled", false).css("opacity", 1);
        $saveBtn.prop("disabled", false).css("opacity", 1);
    } else {
        $input.val("").prop("disabled", true).css("opacity", 0.4);
        $saveBtn.prop("disabled", true).css("opacity", 0.4);
        // OFFにした時点で自動計算・TTL対象に戻す（保存ボタンを待たない）
        savePriceOverride($row, null);
    }
});

// --- ▼ SECTION 07e: 出品価格 手動固定 保存処理 ▼ ---
async function savePriceOverride($row, overridePrice) {
    const asin = $row.data("asin");
    const country_code = $("#globalRegion").val();
    if (!asin || !country_code) return;

    try {
        const res = await fetch("/listing/update_price_override", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                asin,
                country_code,
                override_price: overridePrice,
            }),
        });

        const data = await res.json();
        if (data.status !== "success") {
            window.showToast(data.message || "保存に失敗しました", "error");
            return;
        }

        const submitted = data.price_result && data.price_result.submitted;
        window.showToast(
            submitted
                ? "価格を固定し、Seller Centralへ送信しました"
                : "価格を固定しました（未出品/非ACTIVEのためSeller Centralへの送信は行われません）",
            "success"
        );

        if ($.fn.DataTable.isDataTable("#alllistingtable")) {
            $("#alllistingtable").DataTable().ajax.reload(null, false);
        }

    } catch (e) {
        console.error("[update_price_override]", e);
        window.showToast("通信エラーが発生しました", "error");
    }
}

$(document).on("click", ".price-override-save-btn", function () {
    const $row = $(this).closest(".price-override-row");
    const val = $row.find(".price-override-input").val();

    if (!val || Number(val) <= 0) {
        window.showToast("価格を入力してください", "error");
        return;
    }

    savePriceOverride($row, Number(val));
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
            const detail = document.getElementById("preListingDetailSearch")?.checked || false;
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
            const detail = document.getElementById("allListingDetailSearch")?.checked || false;
            const country_code = document.getElementById("globalRegion")?.value;
            const infoStatus = document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all';
            

            if (!keyword) {
                window.loadalllisting(country_code, infoStatus);
                return;
            }

            window.searchAllListing(keyword, detail, country_code, infoStatus);

        });
    }    

    // === ▼ 09-04C: Pre 絞込リセット ▼ ===
    const preResetBtn = document.getElementById("preFilterResetBtn");

    if (preResetBtn) {
        preResetBtn.addEventListener("click", function () {

            const input = document.getElementById("preListingSearchInput");
            if (input) input.value = "";

            const clearBtn = document.getElementById("preListingSearchClear");
            if (clearBtn) clearBtn.style.display = "none";

            const sortEl = document.getElementById("preListingSort");
            if (sortEl) sortEl.value = "created_desc";

            const brandGateEl = document.getElementById("preBrandGateFilter");
            if (brandGateEl) brandGateEl.value = "all";

            const regionSellerEl = document.getElementById("preRegionSellerFilter");
            if (regionSellerEl) regionSellerEl.value = "all";

            const excludeBooksEl = document.getElementById("preExcludeBooksFilter");
            if (excludeBooksEl) excludeBooksEl.checked = false;

            const infoAll = document.querySelector('input[name="preInfoStatus"][value="all"]');
            if (infoAll) infoAll.checked = true;

            const reasonEl = document.getElementById("preInactiveReason");
            if (reasonEl) {
                reasonEl.value = "all";
                reasonEl.disabled = true;
            }

            const brandStatusAll = document.querySelector('input[name="preBrandStatus"][value="all"]');
            if (brandStatusAll) brandStatusAll.checked = true;

            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            window.loadprelisting(region);
        });
    }

    // === ▼ 09-04E: リーサルウエポン（Pre絞込み条件の規定登録・復元） ▼ ===
    // data-lw="1" が付いた要素を汎用的に走査するため、絞込み項目が増えても
    // ここのコードは変更不要（HTML側にdata-lwを付けるだけで対象に入る）
    function collectLethalWeaponFilters() {
        const filters = {};

        document.querySelectorAll('#prelisting [data-lw]').forEach(el => {
            if (el.type === "radio") {
                if (el.checked) filters[el.name] = el.value;
            } else if (el.type === "checkbox") {
                filters[el.id] = el.checked;
            } else {
                filters[el.id] = el.value;
            }
        });

        return filters;
    }

    function applyLethalWeaponFilters(filters) {
        Object.entries(filters).forEach(([key, value]) => {
            const radios = document.querySelectorAll(`#prelisting input[type="radio"][name="${key}"]`);

            if (radios.length) {
                radios.forEach(r => { r.checked = (r.value === value); });
            } else {
                const el = document.getElementById(key);
                if (!el) return;
                if (el.type === "checkbox") {
                    el.checked = !!value;
                } else {
                    el.value = value;
                }
            }
        });

        // --- ▼ INACTIVE理由プルダウンの有効/無効を情報取得状態に合わせて同期 ▼ ---
        const reasonSelect = document.getElementById("preInactiveReason");
        if (reasonSelect) {
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value;
            reasonSelect.disabled = (infoStatus !== "INACTIVE");
        }

        const region = document.getElementById("globalRegion")?.value;
        if (!region) return;

        window.loadprelisting(region);
    }

    const lwSaveBtn = document.getElementById("lwSaveBtn");
    if (lwSaveBtn) {
        lwSaveBtn.addEventListener("click", function () {
            const originalLabel = lwSaveBtn.textContent;
            lwSaveBtn.disabled = true;

            fetch(`/listing/lethal_weapon/save?user_id=${ZSSS_USER_ID}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: ZSSS_USER_ID, filters: collectLethalWeaponFilters() })
            })
            .then(res => res.json())
            .then(json => {
                lwSaveBtn.textContent = (json.status === "success") ? "登録しました" : "登録失敗";
            })
            .catch(err => {
                console.error("lethal_weapon save error:", err);
                lwSaveBtn.textContent = "登録失敗";
            })
            .finally(() => {
                setTimeout(() => {
                    lwSaveBtn.textContent = originalLabel;
                    lwSaveBtn.disabled = false;
                }, 1500);
            });
        });
    }

    const lwApplyBtn = document.getElementById("lwApplyBtn");
    if (lwApplyBtn) {
        lwApplyBtn.addEventListener("click", function () {
            fetch(`/listing/lethal_weapon/load?user_id=${ZSSS_USER_ID}`)
            .then(res => res.json())
            .then(json => {
                if (json.status === "success") {
                    applyLethalWeaponFilters(json.filters || {});
                }
            })
            .catch(err => console.error("lethal_weapon load error:", err));
        });
    }

    // === ▼ 09-04D: ALL 絞込リセット ▼ ===
    const allResetBtn = document.getElementById("allFilterResetBtn");

    if (allResetBtn) {
        allResetBtn.addEventListener("click", function () {

            const input = document.getElementById("allListingSearchInput");
            if (input) input.value = "";

            const clearBtn = document.getElementById("allListingSearchClear");
            if (clearBtn) clearBtn.style.display = "none";

            const sortEl = document.getElementById("allListingSort");
            if (sortEl) sortEl.value = "created_desc";

            const brandGateEl = document.getElementById("allBrandGateFilter");
            if (brandGateEl) brandGateEl.value = "all";

            const regionSellerEl = document.getElementById("allRegionSellerFilter");
            if (regionSellerEl) regionSellerEl.value = "all";

            const excludeBooksEl = document.getElementById("allExcludeBooksFilter");
            if (excludeBooksEl) excludeBooksEl.checked = false;

            const weightOverrideEl = document.getElementById("allWeightOverrideFilter");
            if (weightOverrideEl) weightOverrideEl.checked = false;

            const priceOverrideEl = document.getElementById("allPriceOverrideFilter");
            if (priceOverrideEl) priceOverrideEl.checked = false;

            const infoAll = document.querySelector('input[name="allInfoStatus"][value="all"]');
            if (infoAll) infoAll.checked = true;

            const reasonEl = document.getElementById("allInactiveReason");
            if (reasonEl) {
                reasonEl.value = "all";
                reasonEl.disabled = true;
            }

            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            window.loadalllisting(region);
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

            const country_code = document.getElementById("globalRegion")?.value;
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';

            window.loadprelisting(country_code, infoStatus);
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

            const country_code = document.getElementById("globalRegion")?.value;
            const infoStatus = document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all';

            window.loadalllisting(country_code, infoStatus);
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
        const reason = document.getElementById("preInactiveReason")?.value || 'all';

        const table = $.fn.dataTable.isDataTable('#prelistingtable')
            ? $('#prelistingtable').DataTable()
            : null;

        if (!table) return;

        const btn = document.getElementById("preListingSearchBtn");
        const originalLabel = btn ? btn.textContent : null;
        if (btn) {
            btn.disabled = true;
            btn.textContent = "検索中...";
        }

        fetch(`/listing/search_listing?mode=pre&keyword=${encodeURIComponent(keyword)}&detail=${detail}&country_code=${country_code}&sort=${sort}&info_status=${infoStatus}&reason=${reason}`)
        .then(res => res.json())
        .then(data => {

            table.clear();
            table.rows.add(data);
            table.draw();

        })
        .catch(err => {
            console.error("searchPreListing error:", err);
            window.showToast?.("検索に失敗しました", "error");
        })
        .finally(() => {
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
        });
    };

    // === ▼ 09-08: ALL DB検索 ▼ ===
    window.searchAllListing = function(keyword, detail, country_code) {

        const sort = document.getElementById("allListingSort")?.value;

        const infoStatus = document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all';
        const reason = document.getElementById("allInactiveReason")?.value || 'all';

        const table = $('#alllistingtable').DataTable();

        const btn = document.getElementById("allListingSearchBtn");
        const originalLabel = btn ? btn.textContent : null;
        if (btn) {
            btn.disabled = true;
            btn.textContent = "検索中...";
        }

        fetch(`/listing/search_listing?mode=all&keyword=${encodeURIComponent(keyword)}&detail=${detail}&country_code=${country_code}&sort=${sort}&info_status=${infoStatus}&reason=${reason}`)
        .then(res => res.json())
        .then(data => {

            table.clear();
            table.rows.add(data);
            table.draw();

        })
        .catch(err => {
            console.error("searchAllListing error:", err);
            window.showToast?.("検索に失敗しました", "error");
        })
        .finally(() => {
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalLabel;
            }
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

        const preAction = document.getElementById("bulkActionSelectPre")?.value;

        // --- 「該当ASIN全一括削除」は絞り込み条件全体が対象のため、行選択の有無を問わず実行可 ---
        if (runPre) runPre.disabled = (preAction === "delete_all_filtered") ? false : !hasChecked;
        if (runAll) runAll.disabled = !hasChecked;

    });

    // --- ▼ Pre 一括操作プルダウン変更時：「該当ASIN全一括削除」選択時は行未選択でも実行可に ▼
    document.getElementById("bulkActionSelectPre")?.addEventListener("change", function () {
        const runPre = document.getElementById("bulkActionRunPre");
        if (!runPre) return;

        if (this.value === "delete_all_filtered") {
            runPre.disabled = false;
        } else {
            const hasChecked = document.querySelectorAll("#prelistingtable .row-select:checked").length > 0;
            runPre.disabled = !hasChecked;
        }
    });

    // --- ▼ 「該当ASIN全一括削除」は誤操作防止のため、何らかの絞り込みが有効な間のみ選択可にする ▼
    // 絞り込みなし（全件対象）での事故を避けるため、条件が一つも指定されていない場合は
    // プルダウンの選択肢自体をdisabledにし、実行ボタンも連動して無効化する。
    // Preタブの一覧が再描画されるたび（検索・各種フィルタ変更・絞込リセット・ページ切替等）に
    // listing_pre.js の draw イベントから呼び出される。
    window.getPreFilterState = function () {
        const brandgate = document.getElementById("preBrandGateFilter")?.value || "all";
        const brandStatus = document.querySelector('input[name="preBrandStatus"]:checked')?.value || "all";
        const regionSeller = document.getElementById("preRegionSellerFilter")?.value || "all";
        const excludeBooks = document.getElementById("preExcludeBooksFilter")?.checked || false;
        const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || "all";
        const keyword = document.querySelector('#preListingSearchInput')?.value?.trim() || "";
        const reason = document.getElementById("preInactiveReason")?.value || "all";

        const hasFilter =
            !!keyword ||
            brandgate !== "all" ||
            brandStatus !== "all" ||
            regionSeller !== "all" ||
            excludeBooks ||
            infoStatus !== "all" ||
            reason !== "all";

        return { brandgate, brandStatus, regionSeller, excludeBooks, infoStatus, keyword, reason, hasFilter };
    };

    window.updatePreDeleteAllFilteredState = function () {
        const option = document.getElementById("bulkDeleteAllFilteredOption");
        const select = document.getElementById("bulkActionSelectPre");
        if (!option || !select) return;

        const { hasFilter } = window.getPreFilterState();

        option.disabled = !hasFilter;

        if (!hasFilter && select.value === "delete_all_filtered") {
            select.value = "";
            const runPre = document.getElementById("bulkActionRunPre");
            if (runPre) runPre.disabled = true;
        }
    };

    window.updatePreDeleteAllFilteredState();

    // --- ▼ SECTION 11: Pre 一括操作 実行 ▼
    document.getElementById("bulkActionRunPre").addEventListener("click", async function () {

        const action = document.getElementById("bulkActionSelectPre").value;

        if (!action) {
            alert("操作を選択してください");
            return;
        }

        // --- ▼ 該当ASIN全一括削除（絞り込み条件に一致する全ページ分を削除） ▼ ---
        if (action === "delete_all_filtered") {

            // --- 絞り込みなし（全件対象）での誤削除を防止（選択後に絞込を解除された場合の保険） ---
            const { hasFilter } = window.getPreFilterState();
            if (!hasFilter) {
                alert("絞り込み条件を1つ以上指定してから実行してください（全件対象での削除は防止されています）");
                window.updatePreDeleteAllFilteredState();
                return;
            }

            const country_code = document.getElementById("globalRegion")?.value;
            if (!country_code) {
                alert("リージョンを選択してください");
                return;
            }

            const table = $.fn.dataTable.isDataTable('#prelistingtable')
                ? $('#prelistingtable').DataTable()
                : null;

            const totalCount = table ? table.page.info().recordsTotal : 0;

            if (!totalCount) {
                alert("削除対象がありません");
                return;
            }

            if (!confirm(`現在の絞り込み条件に一致する全 ${totalCount} 件を削除します。\nこの操作は元に戻せません。実行しますか？`)) {
                return;
            }

            if (!confirm(`最終確認：本当に全 ${totalCount} 件を削除してよろしいですか？`)) {
                return;
            }

            const brandgate = document.getElementById("preBrandGateFilter")?.value || 'all';
            const brandStatus = document.querySelector('input[name="preBrandStatus"]:checked')?.value || 'all';
            const regionSeller = document.getElementById("preRegionSellerFilter")?.value || 'all';
            const excludeBooks = document.getElementById("preExcludeBooksFilter")?.checked || false;
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';
            const keyword = document.querySelector('#preListingSearchInput')?.value || '';
            const reason = document.getElementById("preInactiveReason")?.value || 'all';

            const runBtn = document.getElementById("bulkActionRunPre");
            runBtn.disabled = true;

            try {
                const res = await fetch("/listing/bulk_delete_all_pre", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        country_code,
                        brandgate,
                        brand_status: brandStatus,
                        region_seller: regionSeller,
                        exclude_books: excludeBooks,
                        info_status: infoStatus,
                        keyword,
                        reason
                    })
                });

                const data = await res.json();

                if (data.status === "success") {
                    window.showToast(`${data.deleted_count}件削除しました`, "success");
                    window.loadprelisting(country_code);
                } else {
                    window.showToast(data.message || "削除に失敗しました", "error");
                }
            } catch (e) {
                console.error("bulk_delete_all_pre error:", e);
                window.showToast("通信エラーが発生しました", "error");
            } finally {
                runBtn.disabled = false;
            }

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

            if (!confirm(`${selected.length}件を出品対象へ登録します。実行しますか？`)) {
                return;
            }
            
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
            .then(async res => {
                const data = await res.json().catch(() => ({}));

                if (!res.ok || data.status === "error") {
                    window.showToast(`登録に失敗しました: ${data.message || res.status}`, "error");
                    return;
                }

                if (country_code) {
                    window.savePreListingPage();
                    window.loadprelisting(country_code);
                }

                if (data.blocked_asins && data.blocked_asins.length > 0) {
                    window.showToast(`${data.blocked_asins.length}件はブラックリストのためスキップされました`, "warning");
                } else {
                    window.showToast("登録完了", "success");
                }
            })
            .catch(e => {
                console.error("bulk_move_to_all error:", e);
                window.showToast("通信エラーが発生しました", "error");
            });
        }

        if (action === "refresh") {

            if (!confirm(`${selected.length}件を最新取得します。実行しますか？`)) {
                return;
            }

            const country_code = document.getElementById("globalRegion")?.value;

            const runBtn = document.getElementById("bulkActionRunPre");
            runBtn.disabled = true;

            let failedCount = 0;

            for (const asin of selected) {
                try {
                    const res = await fetch("/run_refresh_now", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ asin, country_code })
                    });

                    const json = await res.json().catch(() => ({}));

                    if (!res.ok || json.status === "error") {
                        failedCount++;
                        console.error("run_refresh_now failed:", asin, res.status, json.message);
                    }
                } catch (e) {
                    failedCount++;
                    console.warn("run_refresh_now failed:", asin, e);
                }
            }

            runBtn.disabled = false;

            if (country_code) {
                window.savePreListingPage();
                window.loadprelisting(country_code);
            }

            if (failedCount > 0) {
                window.showToast(`${failedCount}/${selected.length}件の最新取得に失敗しました`, "error");
            } else {
                window.showToast("最新取得完了", "success");
            }

            return;
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

            // --- ▼ 1件ずつ実行し、返ってきた順に即時反映 ▼ ---
            for (const asin of selected) {

                const row = document.querySelector(`#prelistingtable .row-select[data-asin="${CSS.escape(asin)}"]`)?.closest("tr");
                const resultEl = row?.querySelector(".bg-result");

                try {
                    const res = await fetch("/amazon/brand_gate_check", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            asins: [asin],
                            country_code: country_code
                        })
                    });

                    const data = await res.json();
                    const r = data && data[0] ? data[0] : {};

                    if (!resultEl) continue;

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

                } catch (e) {
                    if (resultEl) {
                        resultEl.innerText = "ERR";
                        resultEl.style.color = "#dc3545";
                    }
                }
            }

            return;
        }
        
        if (action === "delete") {

            const country_code = document.getElementById("globalRegion")?.value;

            // --- ▼ 削除確認 ---
            if (!confirm(`${selected.length}件削除します。実行しますか？`)) {
                return;
            }

            try {
                const res = await fetch("/listing/bulk_delete_items", {
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

                const data = await res.json().catch(() => ({}));
                const failed = (data.results || []).filter(r => r.status === "error");

                if (!res.ok || data.status === "error") {
                    window.showToast(`削除に失敗しました: ${data.message || res.status}`, "error");
                    return;
                }

                const table = $('#prelistingtable').DataTable();

                document.querySelectorAll("#prelistingtable .row-select:checked").forEach(cb => {
                    table.row($(cb).closest("tr")).remove();
                });

                table.draw();

                if (country_code) {
                    window.savePreListingPage();
                    window.loadprelisting(country_code);
                }

                if (failed.length > 0) {
                    window.showToast(`${failed.length}件の削除に失敗しました`, "error");
                } else {
                    window.showToast("削除完了", "success");
                }
            } catch (e) {
                console.error("bulk_delete_items error:", e);
                window.showToast("通信エラーが発生しました", "error");
            }
        }

    });

    // --- ▼ SECTION 12: ALL 一括操作 実行 ▼ ---
    document.getElementById("bulkActionRunAll").addEventListener("click", async function () {

        const action = document.getElementById("bulkActionSelectAll").value;

        if (action === "refresh") {

            const country_code = document.getElementById("globalRegion")?.value;

            const asins = [];

            document.querySelectorAll("#alllistingtable .row-select:checked").forEach(cb => {
                const row = cb.closest("tr");
                const asin = row.querySelector("strong.asin-cell")?.textContent.trim();
                if (asin) asins.push(asin);
            });

            if (asins.length === 0) {
                alert("選択されていません");
                return;
            }

            if (!confirm(`${asins.length}件を最新取得します。実行しますか？`)) {
                return;
            }

            const runBtn = document.getElementById("bulkActionRunAll");
            runBtn.disabled = true;

            let failedCount = 0;

            for (const asin of asins) {
                try {
                    const res = await fetch("/run_refresh_now", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ asin, country_code })
                    });

                    const json = await res.json().catch(() => ({}));

                    if (!res.ok || json.status === "error") {
                        failedCount++;
                        console.error("run_refresh_now failed:", asin, res.status, json.message);
                    }
                } catch (e) {
                    failedCount++;
                    console.warn("run_refresh_now failed:", asin, e);
                }
            }

            runBtn.disabled = false;

            if (country_code) {
                window.saveAllListingPage();
                window.loadalllisting(country_code);
            }

            if (failedCount > 0) {
                window.showToast(`${failedCount}/${asins.length}件の最新取得に失敗しました`, "error");
            } else {
                window.showToast("最新取得完了", "success");
            }

            return;
        }

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

            // --- ▼ 1件ずつ実行し、返ってきた順に即時反映 ▼ ---
            for (const asin of asins) {

                const row = document.querySelector(`#alllistingtable .row-select[data-asin="${CSS.escape(asin)}"]`)?.closest("tr");
                const resultEl = row?.querySelector(".bg-result");

                try {
                    const res = await fetch("/amazon/brand_gate_check", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            asins: [asin],
                            country_code: country_code
                        })
                    });

                    const data = await res.json();
                    const r = data && data[0] ? data[0] : {};

                    if (!resultEl) continue;

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

                } catch (e) {
                    if (resultEl) {
                        resultEl.innerText = "ERR";
                        resultEl.style.color = "#dc3545";
                    }
                }
            }

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

        try {
            const res = await fetch("/listing/bulk_delete_items", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ items, status: "listed" })
            });

            const data = await res.json().catch(() => ({}));
            const failed = (data.results || []).filter(r => r.status === "error");

            if (!res.ok || data.status === "error") {
                window.showToast(`削除に失敗しました: ${data.message || res.status}`, "error");
                return;
            }

            if (country_code) {
                window.saveAllListingPage();
                window.loadalllisting(country_code, document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all');
            }

            if (failed.length > 0) {
                window.showToast(`${failed.length}件の削除に失敗しました`, "error");
            } else {
                window.showToast("削除完了", "success");
            }
        } catch (e) {
            console.error("bulk_delete_items error:", e);
            window.showToast("通信エラーが発生しました", "error");
        }
    });

});

// --- ▼ SECTION 13: Listing共通：ASINセルクリックコピー ▼ --- 
document.addEventListener("click", function (e) {

    const cell = e.target.closest(".asin-cell"); 
    if (!cell) return; 

    const asin = cell.textContent.trim(); 
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
    } else { 
        const tmp = document.createElement("textarea"); 
        tmp.value = asin; 
        document.body.appendChild(tmp);
        tmp.select(); 
        document.execCommand("copy"); 
        document.body.removeChild(tmp); 

        if (window.showCopyNotification) {
            window.showCopyNotification("コピーしました", cell);
        }
    }

});

// --- ▼ SECTION 14: Brandセルクリックコピー ▼ ---
document.addEventListener("click", function (e) {

    const cell = e.target.closest(".brand-copy");
    if (!cell) return;

    const brand = cell.textContent.trim();
    if (!brand) return;

    if (navigator.clipboard && navigator.clipboard.writeText) {

        navigator.clipboard.writeText(brand).then(() => {

            if (window.showCopyNotification) {
                window.showCopyNotification("ブランドコピー", cell);
            }

        }).catch(err => {

            console.error("コピー失敗:", err);

        });

    } else {

        const tmp = document.createElement("textarea");
        tmp.value = brand;

        document.body.appendChild(tmp);
        tmp.select();

        document.execCommand("copy");

        document.body.removeChild(tmp);

        if (window.showCopyNotification) {
            window.showCopyNotification("ブランドコピー", cell);
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

// --- ▼ SECTION 15: 行単位オーバーレイ（listing専用・初期定義） ▼ ---
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
