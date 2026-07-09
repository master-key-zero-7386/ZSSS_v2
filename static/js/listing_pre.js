// =====================================================
// ファイル名: static/listing_pre.js
// Pre-Listing 専用処理（初期ロード・JP情報補完など）
// =====================================================

window.loadprelisting = async function (country_code) {

    // --- ▼ SECTION 01: 二重実行防止ロック ---
    if (window.prelistingLoading) {
        return;
    }
    window.prelistingLoading = true;    

    $("#prelisting").find(".dataTables_wrapper").remove();

    // --- ▼ SECTION 02: 既存テーブルの完全初期化（DataTablesのみ破棄） ---
    if ($.fn.DataTable.isDataTable("#prelistingtable")) {
        const table = $("#prelistingtable").DataTable();
        table.destroy(true);
        $("#prelistingtable_wrapper").remove();        
    }

    // --- ▼ SECTION 03: テーブルが無い場合は生成 ---
    $("#prelistingtable").remove();

    $("#prelisting").append(
        '<table id="prelistingtable" class="display zsss-listing-table"><thead></thead><tbody></tbody></table>' 
    );

    // --- ▼ SECTION 04: Pre info_status変更時 再読み込み ▼ ---
    document.querySelectorAll('input[name="preInfoStatus"]').forEach(radio => {
        radio.addEventListener("change", () => {

            // --- ▼ INACTIVE選択時だけ理由プルダウンを有効化 ▼ ---
            const reasonSelect = document.getElementById("preInactiveReason");
            if (reasonSelect) {
                if (radio.value === "INACTIVE" && radio.checked) {
                    reasonSelect.disabled = false;
                } else {
                    reasonSelect.disabled = true;
                    reasonSelect.value = "all"; // 選択を戻す
                }
            }

            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            loadprelisting(region);
        });
    });    

    // --- ▼ SECTION 04-2: 理由プルダウン変更時も再読み込み ▼ ---
    const preReasonSelect = document.getElementById("preInactiveReason");
    if (preReasonSelect && !preReasonSelect.dataset.bound) {
        preReasonSelect.addEventListener("change", () => {
            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            loadprelisting(region);
        });
        preReasonSelect.dataset.bound = "1";
    }

    // --- ▼ SECTION 04-3: Pre 既出品/未出品 変更時 再読み込み ▼ ---
    document.querySelectorAll('input[name="preBrandStatus"]').forEach(radio => {
        radio.addEventListener("change", () => {

            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            loadprelisting(region);
        });
    });

    // --- ▼ SECTION 05: DataTable 再生成 ---
    const preTable = $("#prelistingtable").DataTable({  

        ...window.getCommonDataTableOptions(),

        serverSide: true,
        processing: true,

        ajax: function(dt, callback) {
            const sort = document.getElementById("preListingSort")?.value;
            const brandgate = document.getElementById("preBrandGateFilter")?.value || 'all';
            const brandStatus = document.querySelector('input[name="preBrandStatus"]:checked')?.value || 'all';
            const regionSeller = document.getElementById("preRegionSellerFilter")?.value || 'all';
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';
            const keyword = document.querySelector('#preListingSearchInput')?.value || '';
            const reason = document.getElementById("preInactiveReason")?.value || 'all';
            // console.log("INPUT VALUE:", keyword);
            const page = Math.floor((dt.start || 0) / (dt.length || 100)) + 1;

            fetch(`/listing/get_prelisting?user_id=${ZSSS_USER_ID}&country_code=${country_code}&sort=${sort}&brandgate=${brandgate}&brand_status=${brandStatus}&region_seller=${regionSeller}&info_status=${infoStatus}&reason=${reason}&page=${page}&keyword=${encodeURIComponent(keyword)}`)
            .then(res => res.json())
            .then(json => {
                callback({
                    data: json.pre,
                    recordsTotal: json.total_count,
                    recordsFiltered: json.total_count
                });
            });
        },     

        order: [],
        orderClasses: false,
        stripeClasses: ["zsss-odd", "zsss-even"],
        columns: [
            {
                data: null,
                title: "No.",
                className: "col-no",
                orderable: false,
                render: function (_d, _t, _row, meta) {
                    return meta.row + meta.settings._iDisplayStart + 1;
                }
            },
            
            {
                data: null,
                title: '<input type="checkbox" id="toggleAllRows"> 商品情報',
                className: "col-info",
                orderable: false,
                defaultContent: "",
                render: function (_d, _t, row) {

                    const asin = row.asin || "";
                    const checked = row.selected ? "checked" : "";
                    const home_host = row.home_marketplace_host;       
                    const region_host = row.marketplace_host;  

                    return `
                        <div class="row-toggle-wrap">
                            <input type="checkbox" class="row-select" data-asin="${asin}" ${checked}
                                style="vertical-align:middle; margin-right:8px;">
                            
                            <div class="row-container">
                                <div>
                                    <strong class="asin-cell" data-asin="${asin}"
                                        style="
                                            color:${row.is_black_asin ? 'red' : '#007bff'};
                                            font-weight:${row.is_black_asin ? 'bold' : 'normal'};
                                            font-size:${row.is_black_asin ? '16px' : '16px'};
                                            cursor:pointer;
                                            text-decoration:underline;
                                            display:inline-flex; 
                                            align-items:center;
                                            margin-bottom:4px;
                                        ">
                                        ${asin}
                                    </strong>                              

                                    <button class="bg-check-btn" data-asin="${asin}"
                                        style="
                                            margin-left:8px;
                                            padding:4px 10px;      /* ←サイズUP */
                                            font-size:12px;        /* ←サイズUP */
                                            font-weight:600;
                                            border-radius:14px;
                                            border:1px solid #007bff;
                                            background:#007bff;
                                            color:#fff;
                                            cursor:pointer;
                                            line-height:1;
                                            vertical-align:middle; /* ←ズレ防止 */
                                        ">
                                        Brand CHECK
                                    </button>

                                    <!-- SKU -->
                                    <span class="sku-cell"
                                        style="font-size:13px; color:#555; margin-left:8px;">
                                        ${row.sku || ""}
                                    </span>   

                                    <span class="bg-result" style="margin-left:6px; font-size:16px;"></span>                                    

                                    <!-- ボタン -->
                                    <div style="margin-top:4px; margin-bottom:6px;"> 
                                        <a href="${home_host}/dp/${asin}" target="_blank" style="text-decoration:none;">
                                            <button style="
                                                margin-right:6px;
                                                padding:2px 8px;
                                                font-size:14px;
                                                border:1px solid #f1c694;
                                                border-radius:4px;
                                                background:#f7f1ea;
                                                cursor:pointer;
                                            ">${row.home_country_code}</button>
                                        </a><a href="${region_host}/dp/${asin}" target="_blank" style="text-decoration:none;">
                                            <button style="
                                                padding:2px 8px;
                                                font-size:14px;
                                                border:1px solid #62c0f7;
                                                border-radius:4px;
                                                background:#62c0f7;
                                                color:#fff;
                                                cursor:pointer;
                                            ">${row.region_country_code}</button>
                                        </a>
                                        <span class="brand-listed-badge">
                                            ${
                                                row.brand_listed_before === true ?
                                                    '<span style="display:inline-block; margin-left:4px; padding:1px 6px; font-size:11px; font-weight:600; border-radius:10px; background:#28a745; color:#fff;" title="このREGIONブランドは出品実績があります">既出品</span>' :
                                                row.brand_listed_before === false ?
                                                    '<span style="display:inline-block; margin-left:4px; padding:1px 6px; font-size:11px; font-weight:600; border-radius:10px; background:#dc3545; color:#fff;" title="このREGIONブランドはまだ出品したことがありません。知財権利者からの警告リスクに注意してください">⚠ 未出品</span>' :
                                                    ''
                                            }
                                        </span>
                                        <span class="brand-gate">
                                            ${
                                                row.brand_gate_status === "OK" ? "🟢" :
                                                row.brand_gate_status === "NG" ? "🔴" :
                                                row.brand_gate_status === "APPROVAL" ? "🟡" :
                                                row.brand_gate_status === "UNKNOWN" ? "⚪" :
                                                "⚪"
                                            }
                                        </span>
                                    </div>
                                </div>
                                
                                <!-- タイトル -->
                                <div class="title-cell"
                                    title="${row.home_title || ""}"
                                    style="font-size:15px; font-weight:600; color:#000; margin-bottom:4px;"> 
                                    ${row.home_title || ""}
                                </div>
                                
                                <div style="font-size:13px; color:#666;">
                                    <span style="display:inline-block; width:70px; font-weight:bold;">Brand</span>
                                    ：${row.home_country_code}：
                                    ${
                                        row.is_black_brand
                                            ? `<span class="brand-copy" style="color:red !important; font-weight:bold;cursor:pointer;text-decoration:underline;">${row.home_brand || ""}</span>`
                                            : `<span class="brand-copy" style="color:#007bff;cursor:pointer;text-decoration:underline;">${row.home_brand || ""}</span>`                                  
                                    }

                                    &nbsp;&nbsp;

                                    ${row.region_country_code}：
                                    ${
                                        row.is_black_brand
                                            ? `<span class="brand-copy" style="color:red !important; font-weight:bold;cursor:pointer;text-decoration:underline;">${row.region_brand || ""}</span>`
                                            : `<span class="brand-copy" style="color:#007bff;cursor:pointer;text-decoration:underline;">${row.region_brand || ""}</span>`
                                    }
                                </div>

                                <div style="font-size:13px; color:#666;">
                                    <span style="display:inline-block; width:70px; font-weight:bold;">RANK</span>
                                    ：${row.home_country_code}：${row.home_rank || "-"}
                                    &nbsp;&nbsp;
                                    ${row.region_country_code}：${row.region_rank || "-"}
                                </div>

                                <!--
                                <div style="font-size:13px; color:#666;">
                                    <span style="display:inline-block; width:70px; font-weight:bold;">Category</span>
                                    ：${row.home_country_code}：${row.home_rank_title || "-"}
                                    &nbsp;&nbsp;
                                    ${row.region_country_code}：${row.region_rank_title || "-"}
                                </div>  
                                -->         

                                <div style="font-size:13px; color:#666;">
                                    <span style="display:inline-block; width:70px; font-weight:bold;">Category</span>
                                    ：${row.region_rank_title || "-"}
                                </div>      
                                
                            </div>
                        </div>
                    `;
                },
            },
            
            {
                data: null,
                title: "画像",                      
                className: "col-ops",
                orderable: false,
                defaultContent: "",
                render: function (_d, _t, row) {
                    const url = (row.image_url || "").replace(/"/g, "&quot;");

                    if (url) {
                        return `
                            <span class="image-container">
                                <img src="${url}" loading="lazy">
                            </span>
                        `;
                    } else {
                        return `
                            <span class="image-container">
                                画像読込中
                            </span>
                        `;
                    }
                },
            },

            {
                title: "出品情報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {
                    const statusLabel = row.information_status || "ー";

                    return `
                        <div class="listing-base">
                            <div>
                                <span style="display:inline-block; width:90px;">情報取得</span>
                                ：<span class="disp-status">
                                    <b style="color:${statusLabel === 'INACTIVE' ? '#e68b02' : '#3528a7'};">
                                        ${statusLabel}
                                    </b>
                                </span>
                            </div>

                            <div>       
                                <span style="display:inline-block; width:90px;">仕入価格</span>
                                ：<span class="disp-home-price">
                                    ${
                                        (() => {
                                            const shipping = Number(row.home_shipping_amount || 0);
                                            const price = Number(row.home_price || 0) - shipping;

                                            if (!price) return "ー";

                                            return shipping > 0
                                                ? `${price.toLocaleString()}（${shipping.toLocaleString()}）`
                                                : price.toLocaleString();
                                        })()
                                    }
                                </span>
                            </div>

                            <div>
                                <span style="display:inline-block; width:90px;">Min Price</span>
                                ：<span class="disp-ht">
                                    ${row.min_price ? Number(row.min_price).toLocaleString() : "ー"}
                                </span>
                            </div>         

                            <div>
                                <span style="display:inline-block; width:90px;">Max Price</span>
                                ：<span class="disp-ht">
                                    ${row.max_price ? Number(row.max_price).toLocaleString() : "ー"}
                                </span>
                            </div>  

                            <div>
                                <span style="display:inline-block; width:90px;">最安値</span>
                                ：<span class="disp-ht">
                                    ${row.raw_min_price ? Number(row.raw_min_price).toLocaleString() : "ー"}
                                </span>
                            </div>

                            <div>
                                <span style="display:inline-block; width:90px;">選択競合価格</span>
                                ：<span class="disp-ht">
                                    ${
                                        (() => {
                                            const price = Number(row.region_price || 0);
                                            const shipping = Number(row.region_shipping_amount || 0);

                                            if (!price) return "ー";

                                            return shipping > 0
                                                ? `${price.toLocaleString()}（${shipping.toLocaleString()}）`
                                                : price.toLocaleString();
                                        })()
                                    }
                                </span>
                            </div>   

                            <div>
                                <span style="display:inline-block; width:90px;">利益率</span>
                                ：<span class="disp-ht">
                                    ${
                                        row.profit_rate != null
                                            ? row.profit_rate + "%"
                                            : "ー"
                                    }
                                </span>
                            </div>
                        </div>
                    `;
                }
            },

            {
                title: "出品価格",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {
                    return `
                        <div style="display:inline-block; border-bottom:2px solid #1c0cfa;">
                            <span style="display:inline-block; width:90px; font-weight:bold;">出品価格</span>
                            ：<span class="disp-sale-price" style="
                                    font-size:25px;
                                    font-weight:bold;
                                    color:${
                                        (() => {
                                            const myPrice = Number(row.override_price ?? row.final_price);
                                            const compPrice =
                                                Number(row.region_price || 0)
                                                + Number(row.region_shipping_amount || 0);

                                            const isWin =
                                                row.region_price == null ||
                                                (myPrice <= compPrice);

                                            return isWin ? '#1c0cfa' : '#cec8c8';
                                        })()
                                    };
                                ">
                                ${
                                    row.override_price
                                        ?? (row.final_price
                                            ? Number(row.final_price).toLocaleString()
                                            : "ー")
                                }
                            </span>
                        </div>
                    `;
                }
            },
            
            {
                title: "セラー情報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {

                    if (!row.offer_counts) return "";

                    return `
                        <div style="display:flex; flex-wrap:wrap; gap:10px; font-size:14px; max-width:100%; overflow:hidden;">
                            <div>
                                <div style="font-weight:600; color:#f0bc80; font-size:18px;">HOME</div>
                                <div style="color:#f15106; font-size:16px;"><span style="display:inline-block; width:34px;">Ama</span>：${row.offer_counts.home_amazon ?? 0}</div>
                                <div style="color:#f0bc80; font-size:16px;"><span style="display:inline-block; width:34px;">FBA</span>：${row.offer_counts.home_fba ?? 0}</div>
                                <div style="color:#f0bc80; font-size:16px;"><span style="display:inline-block; width:34px;">FBM</span>：${row.offer_counts.home_fbm ?? 0}</div>
                            </div>

                            ${(() => {
                                const regionTotal =
                                    (row.offer_counts.region_amazon ?? 0) +
                                    (row.offer_counts.region_fba ?? 0) +
                                    (row.offer_counts.region_fbm ?? 0);
                                const isSingleSeller = regionTotal <= 1;
                                return `
                                    <div style="${isSingleSeller ? 'border:2px solid #dc3545; border-radius:6px; padding:2px 6px;' : ''}">
                                        <div style="font-weight:600; color:#7162f7; font-size:18px; display:flex; flex-wrap:wrap; align-items:center; gap:4px;">
                                            REGION
                                            ${isSingleSeller ? '<span style="display:inline-block; padding:1px 6px; font-size:11px; font-weight:600; border-radius:10px; background:#dc3545; color:#fff;" title="REGIONセラーが0～1人です。メーカー・権利者本人の可能性があるため要注意">⚠ 要注意</span>' : ''}
                                        </div>
                                        <div style="color:#1c0cfa; font-size:16px;"><span style="display:inline-block; width:34px;">Ama</span>：${row.offer_counts.region_amazon ?? 0}</div>
                                        <div style="color:#7162f7; font-size:16px;"><span style="display:inline-block; width:34px;">FBA</span>：${row.offer_counts.region_fba ?? 0}</div>
                                        <div style="color:#7162f7; font-size:16px;"><span style="display:inline-block; width:34px;">FBM</span>：${row.offer_counts.region_fbm ?? 0}</div>
                                    </div>
                                `;
                            })()}
                        </div>
                    `;
                }
            },

            { 
                title: "重量・送料情報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {
                    const len = row.length_cm != null ? parseFloat(row.length_cm).toFixed(1) : "--";
                    const wid = row.width_cm != null ? parseFloat(row.width_cm).toFixed(1) : "--";
                    const hei = row.height_cm != null ? parseFloat(row.height_cm).toFixed(1) : "--";
                    // --- # ここを修正：実重量は pricing 算定後の値を表示 ---
                    const act = row.actual_weight_kg_corrected != null ? parseFloat(row.actual_weight_kg_corrected).toFixed(3) : "--";
                    const vol = row.volumetric_weight_kg != null ? parseFloat(row.volumetric_weight_kg).toFixed(3) : "--";
                    const bill = row.billable_weight_kg != null ? parseFloat(row.billable_weight_kg).toFixed(3) : "--";
                    const shippingFee = row.shipping_fee != null ? Number(row.shipping_fee).toLocaleString() : "--";
                    return `
                        <div>
                            <div><span style="display:inline-block; width:90px;">サイズ</span>：${len} × ${wid} × ${hei} cm</div>
                            <div><span style="display:inline-block; width:90px;">実重量</span>：${act} kg</div>
                            <div><span style="display:inline-block; width:90px;">容積重量</span>：${vol} kg</div>
                            <div><span style="display:inline-block; width:90px;">請求重量</span>：<b>${bill} kg</b></div>
                            <div><span style="display:inline-block; width:90px;">補正前送料</span>：<b>${shippingFee}</b></div>
                        </div>

                    `;
                }
            },
 
            { 
                title: "情　報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {
                    const fmt = (utc, tz) => { 
                        if (!utc) return "-";
                        const d = new Date(utc + "Z");
                        return d.toLocaleString(undefined, { timeZone: tz });
                    };

                    return `
                        <div>
                            <div>更新：${fmt(row.updated_at, row.home_timezone)}</div>
                            <div>登録：${fmt(row.created_at, row.home_timezone)}</div>
                            ${
                                row.information_status === "INACTIVE" && row.inactive_reason
                                    ? `<div style="color:#ff9800;font-weight:bold;">理由：${row.inactive_reason}</div>`
                                    : ""
                            }
                        </div>
                    `;
                }
            },
            { title: "Action", data: null, defaultContent: "", orderable: false },
        ],
    });

    const btn = document.querySelector('#preListingSearchBtn');

    if (btn && !btn.dataset.bound) {
        btn.addEventListener('click', () => {
            $('#prelistingtable').DataTable().ajax.reload();
        });
        btn.dataset.bound = "1";
    }

    // --- ▼ SHIFT範囲選択（Pre）▼ ---
    let lastChecked = null;

    $("#prelistingtable")
        .off('click', '.row-select')
        .on('click', '.row-select', function(e) {

        const checkbox = this;
        const checkboxes = Array.from(document.querySelectorAll('#prelistingtable .row-select'));

        if (!lastChecked) {
            lastChecked = checkbox;
            return;
        }

        if (e.shiftKey) {
            const start = checkboxes.indexOf(checkbox);
            const end = checkboxes.indexOf(lastChecked);
            const [min, max] = [Math.min(start, end), Math.max(start, end)];

            for (let i = min; i <= max; i++) {
                checkboxes[i].checked = lastChecked.checked;
            }
        }

        lastChecked = checkbox;
    });

    // --- ▼ SECTION 06: DataTable 再描画時にも登録ボタンを再アタッチ
    preTable.off('draw').on('draw', function () {        
        const hasRealRows = $("#prelistingtable tbody tr").toArray().some(
            tr => !$(tr).text().includes("No data")
        );
        if (hasRealRows) {
            window.attachRefreshButtons("#prelistingtable"); 
            window.attachRegisterButtons("#prelistingtable");
            window.attachDeleteButtons("#prelistingtable");
        }
    });


    const hasRealRows = $("#prelistingtable").DataTable().rows().count() > 0; 
    if (hasRealRows) {
        $("#prelistingtable").off("click", ".register-btn");
        $("#prelistingtable").off("click", ".delete-btn");
        window.attachRefreshButtons("#prelistingtable");
        window.attachRegisterButtons("#prelistingtable");
        window.attachDeleteButtons("#prelistingtable");
    }

    setTimeout(() => {
        window.prelistingLoading = false;
    }, 0);
};

// =====================================================
// ✅ Pre専用リージョン切替監視（初回自動発火なし）
// =====================================================
window.addEventListener("load", () => {
    const sel = document.getElementById("globalRegion");
    if (!sel) return;

    // 🔹 初期ロードではAPI呼び出ししない（ユーザー操作時のみ）
    sel.addEventListener("change", (e) => {
        const activeTab = document
            .querySelector(".sidebar-btn.active")
            ?.getAttribute("data-target") || ""; 
        if (activeTab !== "prelisting") { 
            return; 
        } 

        const country_code = e.target.value;
        // プルダウン未選択時は何もしない
        if (!country_code) return;
        
        window.loadprelisting(country_code);
    });
});

document.addEventListener("DOMContentLoaded", () => {
    if (window.initCommonHandlers) {
        window.initCommonHandlers();
    }
})

// ASIN個別Brandチェック
document.addEventListener("click", function(e) {

    const btn = e.target.closest(".bg-check-btn");
    if (!btn) return;

    const asin = btn.dataset.asin;
    const resultEl = btn.parentElement.querySelector(".bg-result");
    const country_code = document.getElementById("globalRegion")?.value;

    resultEl.innerText = "Checking...";
    resultEl.style.color = "#999";

    fetch("/amazon/brand_gate_check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            asins: [asin],
            country_code: country_code
        })
    })
    .then(res => {
        return res.json();
    })
    .then(data => {
        const r = data && data[0] ? data[0] : {};
        const status = r.status || "";

        resultEl.innerText = status || "-";

        if (status === "OK") {
            resultEl.style.color = "#28a745";
        } else if (status === "APPROVAL") {
            resultEl.style.color = "#fd7e14";
        } else if (status) {
            resultEl.style.color = "#dc3545";
        } else {
            resultEl.style.color = "#999";
        }

    })
    .catch((err) => {
        resultEl.innerText = "ERR";
        resultEl.style.color = "#dc3545";
    });
});