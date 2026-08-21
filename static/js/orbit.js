// =====================================================
// ファイル名: static/js/orbit.js
// 目的: ORBIT（注文管理）画面制御
// =====================================================

// --- ▼ SECTION 00: 表示列定義 ▼ ---
// 受注一覧＝Amazonデータの取込・管理専用（市場別）。
// N番号・依頼日・JAN・発送種別・トラッキング・仕入価格・備考など「依頼書シート」形式の列は
// 統合画面（CA/US/AU全市場をまとめる場所）側の担当なので、ここには置かない。
const ORBIT_COLUMNS = [
    // --- ZSSS算定（Amazonの登録情報から取得） ---
    { key: "asin", label: "ASIN" },
    { key: "length_cm", label: "長さ(cm)" },
    { key: "width_cm", label: "幅(cm)" },
    { key: "height_cm", label: "高さ(cm)" },
    { key: "billable_weight_kg", label: "請求重量(kg)" },
    { key: "predicted_shipping_fee", label: "予測送料" },

    // --- セラーセントラルCSV由来（右／元の列順のまま） ---
    { key: "order_id", label: "order-id" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "purchase_date", label: "purchase-date", dateOnly: true },
    { key: "payments_date", label: "payments-date", dateOnly: true },
    { key: "reporting_date", label: "reporting-date", dateOnly: true },
    { key: "promise_date", label: "promise-date", dateOnly: true },
    { key: "days_past_promise", label: "days-past-promise" },
    { key: "buyer_email", label: "buyer-email" },
    { key: "buyer_name", label: "buyer-name" },
    { key: "buyer_phone_number", label: "buyer-phone-number" },
    { key: "sku", label: "sku" },
    { key: "product_name", label: "product-name" },
    { key: "quantity_purchased", label: "quantity-purchased" },
    { key: "quantity_shipped", label: "quantity-shipped" },
    { key: "quantity_to_ship", label: "quantity-to-ship" },
    { key: "ship_service_level", label: "ship-service-level" },
    { key: "recipient_name", label: "recipient-name" },
    { key: "ship_address_1", label: "ship-address-1" },
    { key: "ship_address_2", label: "ship-address-2" },
    { key: "ship_address_3", label: "ship-address-3" },
    { key: "ship_city", label: "ship-city" },
    { key: "ship_state", label: "ship-state" },
    { key: "ship_postal_code", label: "ship-postal-code" },
    { key: "ship_country", label: "ship-country" },
    { key: "is_business_order", label: "is-business-order" },
    { key: "purchase_order_number", label: "purchase-order-number" },
    { key: "price_designation", label: "price-designation" },
    { key: "is_transparency", label: "is-transparency" },
    { key: "verge_of_cancellation", label: "verge-of-cancellation" },
    { key: "verge_of_late_shipment", label: "verge-of-lateShipment" },
    { key: "signature_confirmation_recommended", label: "signature-confirmation-recommended" },
    { key: "buyer_identification_number", label: "buyer-identification-number" },
    { key: "buyer_identification_type", label: "buyer-identification-type" },
];

// --- ▼ SECTION 00-1b: 発注管理（依頼書シート形式）列定義 ▼ ---
// CA/US/AU全市場をまとめて、発送代行会社の「依頼書」シートと同じ並びで表示・編集する。
const DISPATCH_COLUMNS = [
    { key: "agent_serial_no", label: "N番号", editable: "number", isSerial: true },
    { key: "request_date", label: "依頼日", editable: "text" },
    { key: "jan_code", label: "JAN" },  // 仕入れ管理で入力した値を反映（読取専用）
    { key: "shipping_type", label: "発送種別", editable: "text" },
    { key: "quantity_purchased", label: "数量" },
    { key: "tracking_number", label: "トラッキング(海外向け)" },  // 代行会社が入力する項目（読取専用）
    { key: "purchase_price_placeholder", label: "仕入価格", blank: true },
    { key: "remarks", label: "備考", editable: "text" },

    // --- 参照用（読み取り専用） ---
    { key: "order_id", label: "order-id" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "product_name", label: "商品名" },
    { key: "ship_country", label: "国" },
];

// --- ▼ SECTION 00-2: 仕入れ管理 列定義 ▼ ---
const SUPPLIER_OPTIONS = [
    "-", "Amazon", "Rakuten", "Rakuten2", "Qoo10",
    "marunishi", "marunishi2", "marunishi3",
    "ﾔﾏﾀﾞｳｪﾌﾞｺﾑ", "PayPay", "Yahoo", "au",
];

const PROCUREMENT_COLUMNS = [
    { key: "promise_date", label: "出荷期日", dateOnly: true, deadline: true },
    { key: "purchase_date", label: "注文日", dateOnly: true },
    { key: "order_id", label: "order-id" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "jan_code", label: "JAN", editable: "text" },
    { key: "product_name", label: "商品名" },
    { key: "quantity_purchased", label: "数量" },
    { key: "ship_country", label: "国" },

    { key: "supplier", label: "仕入先", editable: "select", options: SUPPLIER_OPTIONS },
    { key: "supplier_order_number", label: "注文番号", editable: "text" },
    { key: "supplier_shop_name", label: "ショップ名", editable: "text" },
    { key: "supplier_link", label: "注文リンク", computed: true },
    { key: "arrival_date", label: "到着予定日", editable: "text" },
    { key: "purchase_price", label: "仕入価格(円)", editable: "number" },
];

// 旧スプレッドシートの仕入先別リンク生成ロジックを移植
function buildSupplierLink(supplier, orderNumber) {
    if (!supplier || !orderNumber || supplier === "-") return "";
    const num = String(orderNumber);

    switch (supplier) {
        case "Amazon":
            return `https://www.amazon.co.jp/gp/your-account/order-details/ref=ppx_yo_dt_b_order_details_o00?ie=UTF8&orderID=${num.slice(0, 19)}`;
        case "Rakuten":
        case "Rakuten2":
            return `https://order.my.rakuten.co.jp/?page=myorder&act=detail_view&shop_id=${num.slice(0, 6)}&order_number=${num.slice(0, 26)}`;
        case "Qoo10":
            return `https://www.qoo10.jp/gmkt.inc/My/BuyerReceiptPop.aspx?pack_no=${num.slice(0, 10)}`;
        case "marunishi":
            return "https://ec2.d-apri.com/receipt/yahoo/login.html?cid=f-marunishi";
        case "marunishi2":
            return "https://ec2.d-apri.com/receipt/yahoo/login.html?cid=f-marunishiweb2nd";
        case "marunishi3":
            return "https://ec2.d-apri.com/receipt/yahoo/login.html?cid=f-marunishi3";
        case "ﾔﾏﾀﾞｳｪﾌﾞｺﾑ":
            return `https://www.yamada-denkiweb.com/shop/customer/historydetail.aspx?order_id=${num.slice(0, 10)}`;
        case "PayPay":
            return `https://www.qoo10.jp/gmkt.inc/My/BuyerReceiptPop.aspx?pack_no=${num.slice(0, 9)}`;
        case "Yahoo":
            return "https://odhistory.shopping.yahoo.co.jp/order-history/list?sc_i=shp_pc_top_searchBox_order_history";
        case "au":
            return `https://wowma.jp/bep/m/sucinfo?id=${num.slice(0, 9)}`;
        default:
            return "";
    }
}

// 出荷期日（promise-date）の残り日数に応じた警告クラス（3日前:青／1日前:オレンジ／当日〜超過:赤）
function getDeadlineColorClass(promiseDate) {
    if (!promiseDate) return "";

    const deadline = new Date(String(promiseDate).slice(0, 10));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    deadline.setHours(0, 0, 0, 0);

    const diffDays = Math.round((deadline - today) / 86400000);

    if (diffDays <= 0) return "orbit-deadline-red";
    if (diffDays === 1) return "orbit-deadline-orange";
    if (diffDays === 2 || diffDays === 3) return "orbit-deadline-blue";
    return "";
}

function fmtValue(col, value) {
    if (value === null || value === undefined) return "";
    if (col.dateOnly && typeof value === "string") return value.slice(0, 10);
    if (col.key === "notified_at") return value ? "済" : "";
    return value;
}

// --- ▼ SECTION 00-3: テーブル共通描画・保存処理 ▼ ---
function renderTableHeader(thead, columns) {
    thead.innerHTML = columns.map(col => `<th>${col.label}</th>`).join("");
}

function renderTableRows(tbody, columns, rows) {
    tbody.innerHTML = "";

    rows.forEach(r => {
        const tr = document.createElement("tr");
        tr.dataset.orderItemId = r.order_item_id;

        tr.innerHTML = columns.map(col => {
            if (col.key === "supplier_link") {
                const link = buildSupplierLink(r.supplier, r.supplier_order_number);
                return link ? `<td><a href="${link}" target="_blank" rel="noopener">開く</a></td>` : "<td></td>";
            }

            if (col.blank) return "<td></td>";

            const cellClass = col.deadline ? getDeadlineColorClass(r[col.key]) : "";

            if (col.editable === "select") {
                const current = r[col.key] ?? "";
                const options = col.options.map(opt =>
                    `<option value="${opt}"${opt === current ? " selected" : ""}>${opt}</option>`
                ).join("");
                return `<td class="${cellClass}"><select class="orbit-manual" data-field="${col.key}">${options}</select></td>`;
            }

            if (col.editable) {
                const value = r[col.key] ?? "";
                return `<td class="${cellClass}"><input type="${col.editable}" class="orbit-manual" data-field="${col.key}" value="${value}"></td>`;
            }

            return `<td class="${cellClass}">${fmtValue(col, r[col.key])}</td>`;
        }).join("");

        tbody.appendChild(tr);
    });
}

function saveManualField(orderItemId, field, value, onDone) {
    const payload = { order_item_id: orderItemId };
    payload[field] = (field === "purchase_price")
        ? (value ? parseFloat(value) : null)
        : (value || null);

    fetch("/orbit/orders/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    })
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") {
                window.showToast?.("保存に失敗しました", "error");
            } else if (onDone) {
                onDone();
            }
        })
        .catch(err => {
            console.error("orbit/orders/update error:", err);
            window.showToast?.("保存に失敗しました", "error");
        });
}

function attachSaveHandlers(tbody, { onSaved } = {}) {
    const handler = (e) => {
        const target = e.target;
        if (!target.classList?.contains("orbit-manual")) return;
        if (target.tagName === "SELECT" && e.type !== "change") return;
        if (target.tagName !== "SELECT" && e.type !== "focusout") return;

        const tr = target.closest("tr");
        const orderItemId = tr?.dataset?.orderItemId;
        const field = target.dataset.field;
        if (!orderItemId || !field) return;

        // N番号：先頭行に開始番号を入れると、以降の行に自動で連番が振られる
        if (field === "agent_serial_no") {
            const startValue = target.value;
            if (startValue === "") return;

            fetch("/orbit/orders/set_serial", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ order_item_id: orderItemId, start_value: startValue }),
            })
                .then(res => res.json())
                .then(data => {
                    if (data.status === "success") {
                        onSaved?.();
                    } else {
                        window.showToast?.(data.message || "連番の設定に失敗しました", "error");
                    }
                })
                .catch(err => {
                    console.error("orbit/orders/set_serial error:", err);
                    window.showToast?.("連番の設定に失敗しました", "error");
                });
            return;
        }

        saveManualField(orderItemId, field, target.value, onSaved);
    };

    tbody.addEventListener("focusout", handler);
    tbody.addEventListener("change", handler);
}

window.initOrbit = function () {
    const table = document.getElementById("orbit-orders-table");
    const thead = table?.querySelector("thead tr");
    const tbody = table?.querySelector("tbody");
    if (!tbody || !thead) return;

    const procTable = document.getElementById("orbit-procurement-table");
    const procThead = procTable?.querySelector("thead tr");
    const procTbody = procTable?.querySelector("tbody");

    const dispatchTable = document.getElementById("orbit-dispatch-table");
    const dispatchThead = dispatchTable?.querySelector("thead tr");
    const dispatchTbody = dispatchTable?.querySelector("tbody");

    if (tbody.dataset.orbitInitialized === "true") {
        loadOrders();
        return;
    }
    tbody.dataset.orbitInitialized = "true";

    function loadOrders() {
        fetch("/orbit/orders")
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    renderTableRows(tbody, ORBIT_COLUMNS, data.rows);
                    if (procTbody) renderTableRows(procTbody, PROCUREMENT_COLUMNS, data.rows);
                    if (dispatchTbody) renderTableRows(dispatchTbody, DISPATCH_COLUMNS, data.rows);
                } else {
                    window.showToast?.("注文一覧の取得に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/orders error:", err);
                window.showToast?.("注文一覧の取得に失敗しました", "error");
            });
    }

    renderTableHeader(thead, ORBIT_COLUMNS);
    if (procThead) renderTableHeader(procThead, PROCUREMENT_COLUMNS);
    if (dispatchThead) renderTableHeader(dispatchThead, DISPATCH_COLUMNS);

    // --- ▼ SECTION 01: CSVインポート（他画面と同じ file-input-wrapper 方式） ▼ ---
    const orbitFileInput = document.getElementById("orbitFileInput");
    const orbitFileName = document.getElementById("orbitFileName");
    const orbitUploadBtn = document.getElementById("orbitUploadBtn");

    // 枠をクリックしたら file input を開く
    orbitFileName?.addEventListener("click", () => {
        orbitFileInput?.click();
    });

    // ファイル選択したら枠にファイル名を表示
    orbitFileInput?.addEventListener("change", (e) => {
        const fileName = e.target.files.length ? e.target.files[0].name : "";
        if (orbitFileName) orbitFileName.value = fileName;
    });

    orbitUploadBtn?.addEventListener("click", () => {
        if (!orbitFileInput?.files?.length) {
            window.showToast?.("ファイルを選択してください", "error");
            return;
        }

        const formData = new FormData();
        formData.append("file", orbitFileInput.files[0]);

        fetch("/orbit/import", { method: "POST", body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.imported}件インポートしました`, "success");
                    orbitFileInput.value = "";
                    if (orbitFileName) orbitFileName.value = "";
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "インポートに失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/import error:", err);
                window.showToast?.("インポートに失敗しました", "error");
            });
    });

    document.getElementById("orbit-refresh-btn")?.addEventListener("click", loadOrders);
    document.getElementById("orbit-dispatch-refresh-btn")?.addEventListener("click", loadOrders);

    // --- ▼ SECTION 02: 発送代行への出力 ▼ ---
    document.getElementById("orbit-export-btn")?.addEventListener("click", () => {
        window.location.href = "/orbit/export";
    });

    // --- ▼ SECTION 03: 手入力項目の保存（全テーブル共通） ▼ ---
    attachSaveHandlers(tbody, { onSaved: loadOrders });
    if (procTbody) attachSaveHandlers(procTbody, { onSaved: loadOrders });
    if (dispatchTbody) attachSaveHandlers(dispatchTbody, { onSaved: loadOrders });

    loadOrders();
};
