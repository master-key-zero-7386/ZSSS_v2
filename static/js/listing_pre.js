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
    // if (!document.getElementById("prelistingtable")) {

    $("#prelisting").append(
        '<table id="prelistingtable" class="display zsss-listing-table"><thead></thead><tbody></tbody></table>' 
    );

    // --- ▼ SECTION 04: Pre info_status変更時 再読み込み ▼ ---
    document.querySelectorAll('input[name="preInfoStatus"]').forEach(radio => {
        radio.addEventListener("change", () => {

            const region = document.getElementById("globalRegion")?.value;
            if (!region) return;

            loadprelisting(region);
        });
    });    

    // --- ▼ SECTION 05: DataTable 再生成 ---
    const preTable = $("#prelistingtable").DataTable({  

        serverSide: true,
        processing: true,

        ajax: function(dt, callback) {
            console.log("DT KEYWORD:", dt.search.value); // チェック完了後削除

            const sort = document.getElementById("preListingSort")?.value;
            const infoStatus = document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all';
            const keyword = document.querySelector('#preListingSearchInput')?.value || '';
            // console.log("INPUT VALUE:", keyword); 
            const page = Math.floor((dt.start || 0) / (dt.length || 100)) + 1;  

            fetch(`/listing/get_prelisting?user_id=${ZSSS_USER_ID}&country_code=${country_code}&sort=${sort}&info_status=${infoStatus}&page=${page}&keyword=${encodeURIComponent(keyword)}`)
            .then(res => res.json())
            .then(json => {
                callback({
                    data: json.pre,
                    recordsTotal: json.total_count,
                    recordsFiltered: json.total_count
                });
            });
        },        

        pagingType: "simple_numbers", 
        deferRender: false,
        stateSave: false,  
        // data: data,
        autoWidth: false,
        paging: true,
        pageLength: 100,
        lengthChange: false,
        searching: true,
        info: true,
        scrollX: false,
        dom: '<"top"i p>rt<"bottom"i p>',
        language: {
            infoEmpty: "0 件中 0 から 0 件を表示",
            paginate: { previous: "前へ", next: "次へ" },
        },
        infoCallback: function(settings, start, end, max, total, pre) {
            return `全 ${total} 件中 ${start} から ${end} 件を表示`; 
        },
        order: [],
        orderClasses: false,
        stripeClasses: ["zsss-odd", "zsss-even"],
        columns: [
            {
                data: null,
                title: '<input type="checkbox" id="toggleAllRows"> 商品情報',
                className: "col-info",
                orderable: false,
                defaultContent: "",
                render: function (_d, _t, row) {

                    // console.log(row);  // チェック完了後削除

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
                                            ">HOME</button>
                                        </a><a href="${region_host}/dp/${asin}" target="_blank" style="text-decoration:none;">
                                            <button style="
                                                padding:2px 8px;
                                                font-size:14px;
                                                border:1px solid #62c0f7;
                                                border-radius:4px;
                                                background:#62c0f7;
                                                color:#fff;
                                                cursor:pointer;
                                            ">REGION</button>
                                        </a>
                                        <span class="brand-gate">
                                            ${
                                                row.brand_gate_status === "OK" ? "🟢" :
                                                row.brand_gate_status === "NG" ? "🔴" :
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
                                
                                <!-- SKU -->
                                <div class="sku-cell"
                                    style="font-size:13px; color:#555; margin-top:2px;"> 
                                    ${row.sku || ""}
                                </div>

                                <div class="brand-cell">
                                    ${
                                        row.is_black_brand
                                            ? `<span style="color:red !important; font-weight:bold; font-size:18px;">${row.home_brand || ""}</span>`
                                            : (row.home_brand || "")
                                    }
                                </div>
                            </div>
                        </div>
                    `;
                },
            },
            
            {
                data: null,
                data: "image_url",                      
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
                                ：<span class="disp-status"><b>${statusLabel}</b></span>
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
                                <span style="display:inline-block; width:90px;">競合最安値</span>
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
                        </div>
                    `;
                }
            },

            { title: "ユーザー変更設定", data: "misc", defaultContent: "", orderable: false },
            
            {
                title: "セラー情報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {

                    if (!row.offer_counts) return "";

                    return `
                        <div style="display:flex; gap:25px; font-size:14px;">
                            <div>
                                <div style="font-weight:600; color:#f0bc80; font-size:18px;">HOME</div>
                                <div style="color:#f15106; font-size:16px;"><span style="display:inline-block; width:40px;">Ama</span>：${row.offer_counts.home_amazon ?? 0}</div>
                                <div style="color:#f0bc80; font-size:16px;"><span style="display:inline-block; width:40px;">FBA</span>：${row.offer_counts.home_fba ?? 0}</div>
                                <div style="color:#f0bc80; font-size:16px;"><span style="display:inline-block; width:40px;">FBM</span>：${row.offer_counts.home_fbm ?? 0}</div>
                            </div>

                            <div>
                                <div style="font-weight:600; color:#7162f7; font-size:18px;">REGION</div>
                                <div style="color:#1c0cfa; font-size:16px;"><span style="display:inline-block; width:40px;">Ama</span>：${row.offer_counts.region_amazon ?? 0}</div>
                                <div style="color:#7162f7; font-size:16px;"><span style="display:inline-block; width:40px;">FBA</span>：${row.offer_counts.region_fba ?? 0}</div>
                                <div style="color:#7162f7; font-size:16px;"><span style="display:inline-block; width:40px;">FBM</span>：${row.offer_counts.region_fbm ?? 0}</div>
                            </div>
                        </div>
                    `;
                }
            },

            { 
                title: "重量・送料情報",
                data: null,
                orderable: false,
                render: function (_data, _type, row) {
                    const len = row.length_cm != null ? parseFloat(row.length_cm).toFixed(3) : "--";
                    const wid = row.width_cm != null ? parseFloat(row.width_cm).toFixed(3) : "--";
                    const hei = row.height_cm != null ? parseFloat(row.height_cm).toFixed(3) : "--";
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
                title: "更新情報",
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
            window.attachRegisterButtons("#prelistingtable");
            window.attachDeleteButtons("#prelistingtable");
        }
    });

    // Pre⇒ALLへの登録作業が確認できたら削除してOK　↑↑↑ここまで

    const hasRealRows = $("#prelistingtable").DataTable().rows().count() > 0; 
    if (hasRealRows) {
        $("#prelistingtable").off("click", ".register-btn");
        $("#prelistingtable").off("click", ".delete-btn");
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