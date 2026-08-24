// =====================================================
// ファイル名: static/js/orbit.js
// 目的: ORBIT（注文管理）画面制御
// =====================================================

// --- ▼ SECTION 00-0: order-idセルクリックコピー（Listingの.asin-cellと同じ仕組みを流用） ▼ ---
document.addEventListener("click", function (e) {
    const cell = e.target.closest(".orbit-orderid-cell");
    if (!cell) return;

    const orderId = cell.textContent.trim();
    if (!orderId) return;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(orderId).then(() => {
            window.showCopyNotification?.("コピーしました", cell);
        }).catch(err => console.error("コピー失敗:", err));
    } else {
        const tmp = document.createElement("textarea");
        tmp.value = orderId;
        document.body.appendChild(tmp);
        tmp.select();
        document.execCommand("copy");
        document.body.removeChild(tmp);
        window.showCopyNotification?.("コピーしました", cell);
    }
});

// --- ▼ SECTION 00: 表示列定義 ▼ ---
// 受注一覧＝Amazonデータの取込・管理専用（市場別）。
// N番号・依頼日・JAN・発送種別・トラッキング・仕入価格・備考など「依頼書シート」形式の列は
// 統合画面（CA/US/AU全市場をまとめる場所）側の担当なので、ここには置かない。
const ORBIT_COLUMNS = [
    { key: "delete", label: "", deleteButton: true },

    // --- ZSSS算定（listed_items→catalog_cache→手入力 の順で自動取得。取れない場合のみ下の手入力欄を使う） ---
    { key: "asin", label: "ASIN", copyClass: "asin-cell" },
    { key: "dims_source", label: "寸法取得元" },
    { key: "fetch_catalog", label: "", fetchCatalogButton: true },
    { key: "length_cm", label: "長さ(cm)" },
    { key: "width_cm", label: "幅(cm)" },
    { key: "height_cm", label: "高さ(cm)" },
    { key: "billable_weight_kg", label: "請求重量(kg)" },
    { key: "predicted_shipping_fee", label: "予測送料" },
    { key: "manual_length_cm", label: "長さ手入力(cm)", editable: "number" },
    { key: "manual_width_cm", label: "幅手入力(cm)", editable: "number" },
    { key: "manual_height_cm", label: "高さ手入力(cm)", editable: "number" },
    { key: "manual_weight_kg", label: "重量手入力(kg)", editable: "number" },

    // --- セラーセントラルCSV由来（右／元の列順のまま） ---
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell" },
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

// --- ▼ SECTION 00-1a: 代行会社シートへの貼り付け前チェック項目（発注管理・電話番号〜郵便番号） ▼ ---
// 電話番号(国番号除去)・州(正式表記化)は/orbit/ordersのAPI側（list_orders_with_calc）で自動補正され、
// 貼り付け用CSV出力にも同じ値が反映される。それ以外（商品名・宛名・住所1〜3）は自動修正しないため
// 必ず人の目で編集する。いずれも編集可能で、まだ条件を満たしていない行だけ黄色でハイライトされ、
// 修正（自動 or 手動）が完了すると次の表示更新でハイライトが消える。
const DISPATCH_ISSUE_FLAGS = [
    { key: "flag_phone_country_code", label: "電話番号(国番号が残っています)" },
    { key: "flag_product_name", label: "商品名(70字超 or ｜禁止)" },
    { key: "flag_recipient_name", label: "宛名(フルネーム要確認)" },
    { key: "flag_address1_length", label: "住所1(40字超)" },
    { key: "flag_address2_length", label: "住所2(40字超)" },
    { key: "flag_address3_length", label: "住所3(40字超)" },
    { key: "flag_state_expanded", label: "州(正式表記への変換が必要です)" },
    { key: "flag_postal_code_missing", label: "郵便番号(未入力)" },
];

// --- ▼ SECTION 00-1b: 発注管理（依頼書シート形式）列定義 ▼ ---
// CA/US/AU全市場をまとめて、発送代行会社の「依頼書」シートと同じ並びで表示・編集する。
const DISPATCH_COLUMNS = [
    { key: "issue_summary", label: "⚠", issueSummary: true },
    { key: "move", label: "↕", moveButtons: true },
    { key: "agent_serial_no", label: "N番号", editable: "number", isSerial: true },
    { key: "request_date", label: "依頼日" },  // 仕入れ管理で仕入日を入力した値を反映（読取専用）
    { key: "jan_code", label: "JAN" },  // 仕入れ管理で入力した値を反映（読取専用）
    { key: "shipping_type", label: "発送種別", editable: "text" },
    { key: "quantity_purchased", label: "数量" },
    { key: "agent_tracking_number", label: "トラッキング(海外向け)" },  // 代行会社シートから読み戻し（読取専用）
    // 代行会社シートの「インボイス価格（円）」＝仕入原価ではなく販売額基準（アンダーバリュー防止のため
    // 販売額の97%で算出、自動算定のみで手入力不可）
    { key: "invoice_price_jpy", label: "仕入価格(インボイス円)" },
    { key: "remarks", label: "備考", editable: "text" },

    // --- 代行会社シートからの読み戻し（読取専用。依頼書J〜U列） ---
    // Excelの列グループのように折りたたみ可能（先頭列にトグルボタンを表示、他は折りたたみ時に非表示）
    { key: "agent_thankyou_letter", label: "サンクスレター内容", group: "agentReadback", groupHead: true },
    { key: "agent_option_content", label: "オプション内容", group: "agentReadback" },
    { key: "agent_option_fee", label: "オプション料計", group: "agentReadback" },
    { key: "agent_non_deliverable_weight", label: "配送不可重量", group: "agentReadback" },
    { key: "agent_shipping_weight", label: "発送重量", group: "agentReadback" },
    { key: "agent_weight_recorded_date", label: "発送重量記入日(=出荷済み)", group: "agentReadback" },
    { key: "agent_confirmed_weight", label: "確定重量", group: "agentReadback" },
    { key: "agent_deadline", label: "期限", group: "agentReadback" },
    { key: "agent_status", label: "状況", group: "agentReadback" },
    { key: "agent_shipping_fee", label: "送料", group: "agentReadback" },
    { key: "agent_shipping_fee_total", label: "送料合計", group: "agentReadback" },
    { key: "agent_delivery_area", label: "配送エリア", group: "agentReadback" },
    { key: "agent_synced_at", label: "読戻し日時", group: "agentReadback" },

    // --- 参照用（読み取り専用） ---
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell" },
    { key: "order_item_id", label: "order-item-id" },

    // --- 代行会社シートへの貼り付け前チェック（黄色ハイライト＝未解消。解消されると自動で消える） ---
    // 自動修正してよいのは電話番号(国番号除去)と州(正式表記化)の2項目だけ。商品名・宛名・住所1〜3は
    // 自動修正せず必ず人の目で編集する。いずれも編集可能で、入力内容は*_overrideに保存
    // （Amazon注文レポートの再取込で上書きされない。貼り付け用CSV出力にも反映）。
    { key: "buyer_phone_number_effective", label: "電話番号", checkFlagKey: "flag_phone_country_code", editable: "text", saveField: "buyer_phone_number_override" },
    { key: "buyer_phone_extension_effective", label: "内線", editable: "text", saveField: "buyer_phone_extension_override" },
    { key: "product_name_effective", label: "商品名", checkFlagKey: "flag_product_name", editable: "text", saveField: "product_name_override", wide: true },
    { key: "recipient_name_effective", label: "宛名", checkFlagKey: "flag_recipient_name", editable: "text", saveField: "recipient_name_override", wide: true },
    { key: "ship_address_1_effective", label: "住所1", checkFlagKey: "flag_address1_length", editable: "text", saveField: "ship_address_1_override", wide: true },
    { key: "ship_address_2_effective", label: "住所2", checkFlagKey: "flag_address2_length", editable: "text", saveField: "ship_address_2_override", wide: true },
    { key: "ship_address_3_effective", label: "住所3", checkFlagKey: "flag_address3_length", editable: "text", saveField: "ship_address_3_override", wide: true },
    { key: "ship_state_effective", label: "州", checkFlagKey: "flag_state_expanded", editable: "text", saveField: "ship_state_override" },
    { key: "ship_postal_code", label: "郵便番号", checkFlagKey: "flag_postal_code_missing" },

    { key: "ship_country", label: "国" },

    // --- 依頼書シートAV〜AY列（代行会社の梱包基準で丸めた想定発送重量・寸法。読取専用の自動算定） ---
    { key: "agent_shipping_weight_kg", label: "想定発送重量(kg)" },
    { key: "agent_length_cm", label: "長さ(cm)" },
    { key: "agent_width_cm", label: "幅(cm)" },
    { key: "agent_height_cm", label: "高さ(cm)" },
];

// --- ▼ SECTION 00-2: 仕入れ管理 列定義 ▼ ---
const SUPPLIER_OPTIONS = [
    "-", "Amazon", "Rakuten", "Rakuten2", "Qoo10",
    "marunishi", "marunishi2", "marunishi3",
    "ﾔﾏﾀﾞｳｪﾌﾞｺﾑ", "PayPay", "Yahoo", "au",
];

const PROCUREMENT_COLUMNS = [
    // --- 仕入れ・出荷時に頻繁にチェックする項目（発注管理側のN番号と対応づけて左端に配置） ---
    { key: "agent_serial_no", label: "N番号", highlight: true },  // 発注管理タブで入力（読取専用）
    { key: "asin", label: "ASIN", copyClass: "asin-cell", highlight: true },
    { key: "procurement_date", label: "仕入日", editable: "text", highlight: true },
    { key: "arrival_date", label: "到着予定日", editable: "text", highlight: true },

    { key: "promise_date", label: "出荷期日", dateOnly: true, deadline: true },
    { key: "purchase_date", label: "注文日", dateOnly: true },
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "jan_code", label: "JAN", editable: "text" },
    { key: "product_name", label: "商品名" },
    { key: "quantity_purchased", label: "数量" },
    { key: "ship_country", label: "国" },

    { key: "supplier", label: "仕入先", editable: "select", options: SUPPLIER_OPTIONS },
    { key: "supplier_order_number", label: "注文番号", editable: "text" },
    { key: "supplier_shop_name", label: "ショップ名", editable: "text" },
    { key: "supplier_link", label: "注文リンク", computed: true },
    { key: "purchase_price", label: "仕入価格(円)", editable: "number" },

    // --- 実利益。入金額は「決済トランザクション実績」＞「手数料見積り概算」の順で採用、送料は
    //     「代行会社確定額」＞「ZSSS予測概算」の順で採用（円換算、いずれか概算のときは(概算)と表示） ---
    { key: "fetch_fee_estimate", label: "", fetchFeeEstimateButton: true },
    { key: "sale_price_used", label: "販売額(現地通貨)", profitHighlight: true, saleAmountCell: true, currencyKey: "sale_price_used_currency" },
    { key: "net_proceeds_used", label: "入金額(現地通貨)", profitHighlight: true, saleAmountCell: true, currencyKey: "net_proceeds_used_currency", estimateFlagKey: "net_proceeds_is_estimate" },
    { key: "net_proceeds_used_jpy", label: "入金額(円)", profitHighlight: true, estimateFlagKey: "net_proceeds_is_estimate" },
    { key: "shipping_cost_used", label: "送料(円)", profitHighlight: true, estimateFlagKey: "shipping_cost_is_estimate" },
    { key: "profit_jpy", label: "利益(円)", profitHighlight: true, estimateFlagKey: "profit_is_estimate" },
    { key: "profit_rate_pct", label: "利益率(%)", profitHighlight: true, percentCell: true },
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

const JPY_ROUNDED_KEYS = ["net_proceeds_used_jpy", "shipping_cost_used", "profit_jpy"];

function fmtValue(col, value) {
    if (value === null || value === undefined) return "";
    if (col.dateOnly && typeof value === "string") return value.slice(0, 10);
    if (col.key === "notified_at") return value ? "済" : "";
    if (JPY_ROUNDED_KEYS.includes(col.key) && typeof value === "number") return Math.round(value).toLocaleString();
    return value;
}

// --- ▼ SECTION 00-3: テーブル共通描画・保存処理 ▼ ---
// 列グループの折りたたみ／展開で幅が変わるため、対応する上部スクロールバー（あれば）の内側要素の幅を再計算する
function syncTopScrollWidth(table) {
    if (!table) return;
    const wrapper = table.closest(".table-wrapper");
    const topScroll = wrapper?.previousElementSibling;
    if (!topScroll || !topScroll.classList.contains("orbit-top-scroll")) return;
    const inner = topScroll.firstElementChild;
    if (inner) inner.style.width = `${table.scrollWidth}px`;
}

function renderTableHeader(thead, columns, { sortable, onSort, sortState } = {}) {
    // 折りたたみ可能な列グループ（Excelの列グループ相当）。現在どのグループが
    // 折りたたみ中かは <table> 要素のクラスで管理しているので、再描画時はそれを見て復元する。
    const table = thead.closest("table");
    const collapsedGroups = new Set(
        table ? columns.filter(c => c.group && table.classList.contains(`orbit-collapsed-${c.group}`)).map(c => c.group) : []
    );

    thead.innerHTML = columns.map(col => {
        const extraHeadClass = [
            (col.group && !col.groupHead) ? `orbit-group-${col.group}` : "",
            col.highlight ? "orbit-check-highlight" : "",
            col.profitHighlight ? "orbit-profit-highlight" : "",
        ].filter(Boolean).join(" ");
        const groupClass = extraHeadClass ? ` ${extraHeadClass}` : "";
        const toggleBtn = col.groupHead
            ? `<button type="button" class="orbit-group-toggle-btn" data-group="${col.group}" title="折りたたみ/展開">${collapsedGroups.has(col.group) ? "▸" : "▾"}</button> `
            : "";

        if (!sortable || col.blank || col.deleteButton || col.key === "supplier_link") {
            return `<th class="${groupClass.trim()}">${toggleBtn}${col.label}</th>`;
        }
        const arrow = sortState && sortState.key === col.key ? (sortState.dir === "asc" ? " ▲" : " ▼") : "";
        return `<th class="orbit-sortable-th${groupClass}" data-sort-key="${col.key}" style="cursor:pointer;" title="クリックで並び替え">${toggleBtn}${col.label}${arrow}</th>`;
    }).join("");

    if (sortable) {
        thead.querySelectorAll(".orbit-sortable-th").forEach(th => {
            th.addEventListener("click", () => onSort?.(th.dataset.sortKey));
        });
    }

    thead.querySelectorAll(".orbit-group-toggle-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const group = btn.dataset.group;
            if (!table || !group) return;
            const collapsed = table.classList.toggle(`orbit-collapsed-${group}`);
            btn.textContent = collapsed ? "▸" : "▾";
            syncTopScrollWidth(table);
        });
    });
}

// 行の並び替え（文字列・数値どちらも簡易比較。空値は末尾に回す）
function sortRowsByKey(rows, key, dir) {
    const sorted = [...rows].sort((a, b) => {
        const av = a[key];
        const bv = b[key];
        if (av === null || av === undefined || av === "") return 1;
        if (bv === null || bv === undefined || bv === "") return -1;
        if (av < bv) return dir === "asc" ? -1 : 1;
        if (av > bv) return dir === "asc" ? 1 : -1;
        return 0;
    });
    return sorted;
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

            if (col.deleteButton) {
                return `<td><button type="button" class="orbit-row-delete-btn btn-red" data-order-item-id="${r.order_item_id}">削除</button></td>`;
            }

            if (col.moveButtons) {
                return `<td style="white-space:nowrap;">
                    <button type="button" class="orbit-move-up-btn" data-order-item-id="${r.order_item_id}" title="上へ">▲</button>
                    <button type="button" class="orbit-move-down-btn" data-order-item-id="${r.order_item_id}" title="下へ">▼</button>
                </td>`;
            }

            if (col.fetchCatalogButton) {
                if (r.dims_source || !r.asin) return "<td></td>";
                return `<td><button type="button" class="orbit-fetch-catalog-btn btn-blue" data-asin="${r.asin}" data-order-item-id="${r.order_item_id}">API取得</button></td>`;
            }

            if (col.fetchFeeEstimateButton) {
                // 決済トランザクション実績が既にあれば手数料見積りは不要。
                // item_priceが無くても、ボタン側でAmazon注文詳細(Orders API)から自動取得する。
                if (r.net_proceeds != null || !r.asin) return "<td></td>";
                const label = r.fee_estimate_amount != null ? "手数料見積り再取得" : "手数料見積り取得";
                return `<td><button type="button" class="orbit-fetch-fee-btn btn-blue" data-order-item-id="${r.order_item_id}">${label}</button></td>`;
            }

            if (col.percentCell) {
                if (r[col.key] == null) return "<td></td>";
                return `<td>${(Math.round(r[col.key] * 10) / 10).toLocaleString()}%</td>`;
            }

            if (col.issueSummary) {
                const active = DISPATCH_ISSUE_FLAGS.filter(f => r[f.key]);
                if (!active.length) return "<td></td>";
                return `<td class="orbit-issue-flag" style="text-align:center;" title="${active.map(f => f.label).join(" / ")}">⚠</td>`;
            }

            if (col.blank) return "<td></td>";

            let cellClass = col.deadline ? getDeadlineColorClass(r[col.key]) : "";
            if (col.group && !col.groupHead) cellClass = `${cellClass} orbit-group-${col.group}`.trim();
            if (col.checkFlagKey && r[col.checkFlagKey]) cellClass = `${cellClass} orbit-issue-flag`.trim();
            if (col.highlight) cellClass = `${cellClass} orbit-check-highlight`.trim();
            if (col.profitHighlight) cellClass = `${cellClass} orbit-profit-highlight`.trim();

            if (col.saleAmountCell) {
                if (r[col.key] == null) return `<td class="${cellClass}"></td>`;
                const amount = Math.round(r[col.key] * 100) / 100;
                const currency = r[col.currencyKey] || "";
                const suffix = col.estimateFlagKey && r[col.estimateFlagKey] ? " (概算)" : "";
                return `<td class="${cellClass}">${amount.toLocaleString()} ${currency}${suffix}</td>`;
            }

            if (col.estimateFlagKey) {
                const suffix = (r[col.key] != null && r[col.estimateFlagKey]) ? " (概算)" : "";
                return `<td class="${cellClass}">${fmtValue(col, r[col.key])}${suffix}</td>`;
            }

            if (col.copyClass && !col.editable) {
                return `<td class="${cellClass}"><span class="${col.copyClass}" style="color:#007bff; text-decoration:underline; cursor:pointer;" title="クリックでコピー">${fmtValue(col, r[col.key])}</span></td>`;
            }

            if (col.editable === "select") {
                const current = r[col.key] ?? "";
                const options = col.options.map(opt =>
                    `<option value="${opt}"${opt === current ? " selected" : ""}>${opt}</option>`
                ).join("");
                return `<td class="${cellClass}"><select class="orbit-manual" data-field="${col.key}">${options}</select></td>`;
            }

            if (col.editable) {
                const value = r[col.key] ?? "";
                const inputClass = col.wide ? "orbit-manual orbit-manual-wide" : "orbit-manual";
                return `<td class="${cellClass}"><input type="${col.editable}" class="${inputClass}" data-field="${col.saveField || col.key}" value="${value}" title="${value}"></td>`;
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

function attachSaveHandlers(tbody, { onSaved, getOrderedIds } = {}) {
    const handler = (e) => {
        const target = e.target;
        if (!target.classList?.contains("orbit-manual")) return;
        if (target.tagName === "SELECT" && e.type !== "change") return;
        if (target.tagName !== "SELECT" && e.type !== "focusout") return;

        const tr = target.closest("tr");
        const orderItemId = tr?.dataset?.orderItemId;
        const field = target.dataset.field;
        if (!orderItemId || !field) return;

        // N番号：先頭行に開始番号を入れると、以降の行（今の画面の並び順）に自動で連番が振られる
        if (field === "agent_serial_no") {
            const startValue = target.value;
            if (startValue === "") return;

            const orderedIds = getOrderedIds ? getOrderedIds() : undefined;

            fetch("/orbit/orders/set_serial", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ order_item_id: orderItemId, start_value: startValue, ordered_ids: orderedIds }),
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

    // 受注一覧は行数が少ないと本体の横スクロールバーが画面下に隠れるため、上部に操作用のバーを用意して同期する
    const ordersTopScroll = document.getElementById("orbit-orders-top-scroll");
    const ordersTableWrapper = document.getElementById("orbit-orders-table-wrapper");
    const ordersTopScrollInner = ordersTopScroll?.firstElementChild;

    function syncOrdersTopScrollWidth() {
        if (ordersTopScrollInner) ordersTopScrollInner.style.width = `${table.scrollWidth}px`;
    }

    if (ordersTopScroll && ordersTableWrapper) {
        ordersTopScroll.addEventListener("scroll", () => {
            ordersTableWrapper.scrollLeft = ordersTopScroll.scrollLeft;
        });
        ordersTableWrapper.addEventListener("scroll", () => {
            ordersTopScroll.scrollLeft = ordersTableWrapper.scrollLeft;
        });
    }

    const procTable = document.getElementById("orbit-procurement-table");
    const procThead = procTable?.querySelector("thead tr");
    const procTbody = procTable?.querySelector("tbody");

    // 仕入れ管理も他タブ同様、行数が少ないと本体の横スクロールバーが画面下に隠れるため上部バーを同期する
    const procTopScroll = document.getElementById("orbit-procurement-top-scroll");
    const procTableWrapper = document.getElementById("orbit-procurement-table-wrapper");
    const procTopScrollInner = procTopScroll?.firstElementChild;

    function syncProcurementTopScrollWidth() {
        if (procTopScrollInner && procTable) procTopScrollInner.style.width = `${procTable.scrollWidth}px`;
    }

    if (procTopScroll && procTableWrapper) {
        procTopScroll.addEventListener("scroll", () => {
            procTableWrapper.scrollLeft = procTopScroll.scrollLeft;
        });
        procTableWrapper.addEventListener("scroll", () => {
            procTopScroll.scrollLeft = procTableWrapper.scrollLeft;
        });
    }

    const dispatchTable = document.getElementById("orbit-dispatch-table");
    const dispatchThead = dispatchTable?.querySelector("thead tr");
    const dispatchTbody = dispatchTable?.querySelector("tbody");

    // 発注管理も受注一覧と同様、行数が少ないと本体の横スクロールバーが画面下に隠れるため上部バーを同期する
    const dispatchTopScroll = document.getElementById("orbit-dispatch-top-scroll");
    const dispatchTableWrapper = document.getElementById("orbit-dispatch-table-wrapper");
    const dispatchTopScrollInner = dispatchTopScroll?.firstElementChild;

    function syncDispatchTopScrollWidth() {
        if (dispatchTopScrollInner && dispatchTable) dispatchTopScrollInner.style.width = `${dispatchTable.scrollWidth}px`;
    }

    if (dispatchTopScroll && dispatchTableWrapper) {
        dispatchTopScroll.addEventListener("scroll", () => {
            dispatchTableWrapper.scrollLeft = dispatchTopScroll.scrollLeft;
        });
        dispatchTableWrapper.addEventListener("scroll", () => {
            dispatchTopScroll.scrollLeft = dispatchTableWrapper.scrollLeft;
        });
    }

    // 発注管理タブは初期表示時 display:none のため、初回データ読込時点では table.scrollWidth が
    // 0になってしまう（=上部バーの幅も0で操作不能になる）。タブが実際に表示されて幅が確定した
    // タイミングで再計算できるよう、サイズ変化を監視して都度同期する。
    if (dispatchTable && window.ResizeObserver) {
        new ResizeObserver(() => syncDispatchTopScrollWidth()).observe(dispatchTable);
    }
    if (procTable && window.ResizeObserver) {
        new ResizeObserver(() => syncProcurementTopScrollWidth()).observe(procTable);
    }

    if (tbody.dataset.orbitInitialized === "true") {
        loadOrders();
        return;
    }
    tbody.dataset.orbitInitialized = "true";

    // データ再読込でtbody.innerHTMLを差し替えると、テーブルを囲むtable-wrapperの
    // 横スクロール位置がブラウザによって勝手にリセットされることがあるため、明示的に保持する。
    function renderPreservingScroll(tbodyEl, columns, rows) {
        if (!tbodyEl) return;
        const wrapper = tbodyEl.closest(".table-wrapper");
        const scrollLeft = wrapper ? wrapper.scrollLeft : 0;
        renderTableRows(tbodyEl, columns, rows);
        if (wrapper) wrapper.scrollLeft = scrollLeft;
    }

    // 発注管理テーブルは列見出しクリックで並び替えできる（N番号の連番はこの並び順を使う）
    let dispatchRowsCache = [];
    let dispatchSortState = null; // { key, dir }

    function renderDispatchTable() {
        const rows = dispatchSortState
            ? sortRowsByKey(dispatchRowsCache, dispatchSortState.key, dispatchSortState.dir)
            : dispatchRowsCache;
        renderPreservingScroll(dispatchTbody, DISPATCH_COLUMNS, rows);
    }

    function onDispatchSort(key) {
        if (dispatchSortState && dispatchSortState.key === key) {
            dispatchSortState = { key, dir: dispatchSortState.dir === "asc" ? "desc" : "asc" };
        } else {
            dispatchSortState = { key, dir: "asc" };
        }
        if (dispatchThead) renderTableHeader(dispatchThead, DISPATCH_COLUMNS, { sortable: true, onSort: onDispatchSort, sortState: dispatchSortState });
        renderDispatchTable();
    }

    function getDispatchOrderedIds() {
        return [...dispatchTbody.querySelectorAll("tr[data-order-item-id]")].map(tr => tr.dataset.orderItemId);
    }

    // 行を1つ上/下へ手動で移動する（列ソート中の場合は解除して、移動後の並びをそのまま正とする）
    function moveDispatchRow(orderItemId, direction) {
        const idx = dispatchRowsCache.findIndex(r => r.order_item_id === orderItemId);
        if (idx < 0) return;

        const swapIdx = direction === "up" ? idx - 1 : idx + 1;
        if (swapIdx < 0 || swapIdx >= dispatchRowsCache.length) return;

        if (dispatchSortState) {
            dispatchSortState = null;
            if (dispatchThead) renderTableHeader(dispatchThead, DISPATCH_COLUMNS, { sortable: true, onSort: onDispatchSort, sortState: dispatchSortState });
        }

        [dispatchRowsCache[idx], dispatchRowsCache[swapIdx]] = [dispatchRowsCache[swapIdx], dispatchRowsCache[idx]];
        renderDispatchTable();
    }

    function loadOrders() {
        fetch("/orbit/orders")
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    renderPreservingScroll(tbody, ORBIT_COLUMNS, data.rows);
                    // 発注管理は「常に末尾に追加される取込順(id昇順)」がN番号採番の基準のため、
                    // 受注一覧と違って購入日順ではなくid順を初期表示順にする
                    // （購入日順のままだと、後から取り込んだ注文の購入日が早い場合に
                    //   既存の連番より上に表示されてしまい、N番号の並びと矛盾する）。
                    // 仕入れ管理もN番号の列を持つため、発注管理と同じ並びに揃える。
                    const idOrderedRows = [...data.rows].sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
                    renderPreservingScroll(procTbody, PROCUREMENT_COLUMNS, idOrderedRows);
                    dispatchRowsCache = idOrderedRows;
                    renderDispatchTable();
                    syncOrdersTopScrollWidth();
                    syncDispatchTopScrollWidth();
                    syncProcurementTopScrollWidth();
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
    if (dispatchThead) renderTableHeader(dispatchThead, DISPATCH_COLUMNS, { sortable: true, onSort: onDispatchSort, sortState: dispatchSortState });

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

    // --- ▼ SECTION 01-1b: 決済レポートインポート（実利益算定用） ▼ ---
    const orbitSettlementFileInput = document.getElementById("orbitSettlementFileInput");
    const orbitSettlementFileName = document.getElementById("orbitSettlementFileName");
    const orbitSettlementUploadBtn = document.getElementById("orbitSettlementUploadBtn");

    orbitSettlementFileName?.addEventListener("click", () => {
        orbitSettlementFileInput?.click();
    });

    orbitSettlementFileInput?.addEventListener("change", (e) => {
        const fileName = e.target.files.length ? e.target.files[0].name : "";
        if (orbitSettlementFileName) orbitSettlementFileName.value = fileName;
    });

    orbitSettlementUploadBtn?.addEventListener("click", () => {
        if (!orbitSettlementFileInput?.files?.length) {
            window.showToast?.("ファイルを選択してください", "error");
            return;
        }

        const formData = new FormData();
        formData.append("file", orbitSettlementFileInput.files[0]);

        fetch("/orbit/settlements/import", { method: "POST", body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.imported}件インポートしました`, "success");
                    orbitSettlementFileInput.value = "";
                    if (orbitSettlementFileName) orbitSettlementFileName.value = "";
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "インポートに失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/settlements/import error:", err);
                window.showToast?.("インポートに失敗しました", "error");
            });
    });

    // --- ▼ SECTION 01-1c: 販売額・手数料見積り結果の機体間受け渡し（ATLAS(AU)⇔ZSSS(CA/US)） ▼ ---
    const orbitFeeDataFileInput = document.getElementById("orbitFeeDataFileInput");
    const orbitFeeDataFileName = document.getElementById("orbitFeeDataFileName");
    const orbitFeeDataUploadBtn = document.getElementById("orbitFeeDataUploadBtn");

    orbitFeeDataFileName?.addEventListener("click", () => {
        orbitFeeDataFileInput?.click();
    });

    orbitFeeDataFileInput?.addEventListener("change", (e) => {
        const fileName = e.target.files.length ? e.target.files[0].name : "";
        if (orbitFeeDataFileName) orbitFeeDataFileName.value = fileName;
    });

    orbitFeeDataUploadBtn?.addEventListener("click", () => {
        if (!orbitFeeDataFileInput?.files?.length) {
            window.showToast?.("ファイルを選択してください", "error");
            return;
        }

        const formData = new FormData();
        formData.append("file", orbitFeeDataFileInput.files[0]);

        fetch("/orbit/fee_data/import", { method: "POST", body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.imported}件反映しました`, "success");
                    orbitFeeDataFileInput.value = "";
                    if (orbitFeeDataFileName) orbitFeeDataFileName.value = "";
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "取り込みに失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/fee_data/import error:", err);
                window.showToast?.("取り込みに失敗しました", "error");
            });
    });

    document.getElementById("orbit-refresh-btn")?.addEventListener("click", loadOrders);
    document.getElementById("orbit-dispatch-refresh-btn")?.addEventListener("click", loadOrders);

    // --- ▼ SECTION 01-2: 行ごとの削除 ▼ ---
    tbody.addEventListener("click", (e) => {
        const btn = e.target.closest(".orbit-row-delete-btn");
        if (!btn) return;

        const orderItemId = btn.dataset.orderItemId;
        if (!orderItemId) return;
        if (!confirm(`order-item-id: ${orderItemId} を削除します。よろしいですか？`)) return;

        fetch("/orbit/orders/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_id: orderItemId }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "削除に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/orders/delete error:", err);
                window.showToast?.("削除に失敗しました", "error");
            });
    });

    // --- ▼ SECTION 01-2b: 寸法・重量が無いASINをその場でHOME APIから取得 ▼ ---
    tbody.addEventListener("click", (e) => {
        const btn = e.target.closest(".orbit-fetch-catalog-btn");
        if (!btn) return;

        const asin = btn.dataset.asin;
        if (!asin) return;

        btn.disabled = true;
        btn.textContent = "取得中...";

        fetch("/orbit/orders/fetch_catalog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ asin }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.("寸法を取得しました", "success");
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "取得に失敗しました", "error");
                    btn.disabled = false;
                    btn.textContent = "API取得";
                }
            })
            .catch(err => {
                console.error("orbit/orders/fetch_catalog error:", err);
                window.showToast?.("取得に失敗しました", "error");
                btn.disabled = false;
                btn.textContent = "API取得";
            });
    });

    // --- ▼ SECTION 01-2c: 仕入れ管理：出荷前の概算利益用に手数料見積りを取得 ▼ ---
    procTbody?.addEventListener("click", (e) => {
        const btn = e.target.closest(".orbit-fetch-fee-btn");
        if (!btn) return;

        const orderItemId = btn.dataset.orderItemId;
        if (!orderItemId) return;

        const originalLabel = btn.textContent;
        btn.disabled = true;
        btn.textContent = "取得中...";

        fetch("/orbit/orders/fetch_fee_estimate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_id: orderItemId }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.("手数料見積りを取得しました", "success");
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "取得に失敗しました", "error");
                    btn.disabled = false;
                    btn.textContent = originalLabel;
                }
            })
            .catch(err => {
                console.error("orbit/orders/fetch_fee_estimate error:", err);
                window.showToast?.("取得に失敗しました", "error");
                btn.disabled = false;
                btn.textContent = originalLabel;
            });
    });

    // --- ▼ SECTION 01-3: 全件削除（リセット） ▼ ---
    document.getElementById("orbit-delete-all-btn")?.addEventListener("click", () => {
        const typed = prompt("受注一覧の全データを削除します。元に戻せません。\n続行するには「DELETE」と入力してください。");
        if (typed !== "DELETE") return;

        fetch("/orbit/orders/delete_all", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ confirm: "DELETE" }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.deleted}件削除しました`, "success");
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "削除に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/orders/delete_all error:", err);
                window.showToast?.("削除に失敗しました", "error");
            });
    });

    // --- ▼ SECTION 02: 発送代行への出力 ▼ ---
    document.getElementById("orbit-export-btn")?.addEventListener("click", () => {
        window.location.href = "/orbit/export";
    });

    // --- ▼ SECTION 02-1b: Google連携状態の表示（未連携ならボタンを出す） ▼ ---
    const googleConnectLink = document.getElementById("orbit-google-connect-link");
    const googleConnectStatus = document.getElementById("orbit-google-connect-status");

    fetch("/orbit/google_oauth/status")
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") return;
            if (data.connected) {
                if (googleConnectStatus) googleConnectStatus.textContent = "Google連携済み";
            } else if (googleConnectLink) {
                googleConnectLink.style.display = "inline-block";
            }
        })
        .catch(err => console.error("google_oauth/status error:", err));

    // --- ▼ SECTION 02-2: 代行会社シートから読み戻し（N番号で突き合わせ） ▼ ---
    const syncBtn = document.getElementById("orbit-dispatch-sync-btn");
    const syncStatus = document.getElementById("orbit-dispatch-sync-status");

    syncBtn?.addEventListener("click", () => {
        if (syncStatus) syncStatus.textContent = "取り込み中...";

        fetch("/orbit/dispatch_sheet_sync", { method: "POST" })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    if (syncStatus) syncStatus.textContent = `${data.matched}件を反映しました`;
                    loadOrders();
                } else {
                    if (syncStatus) syncStatus.textContent = data.message || "取り込みに失敗しました";
                }
            })
            .catch(err => {
                console.error("dispatch_sheet_sync error:", err);
                if (syncStatus) syncStatus.textContent = "取り込みに失敗しました";
            });
    });

    // --- ▼ SECTION 03: 手入力項目の保存（全テーブル共通） ▼ ---
    attachSaveHandlers(tbody, { onSaved: loadOrders });
    if (procTbody) attachSaveHandlers(procTbody, { onSaved: loadOrders });
    if (dispatchTbody) attachSaveHandlers(dispatchTbody, { onSaved: loadOrders, getOrderedIds: getDispatchOrderedIds });

    // --- ▼ 発注管理: 行ごとの上下移動 ▼ ---
    dispatchTbody?.addEventListener("click", (e) => {
        const upBtn = e.target.closest(".orbit-move-up-btn");
        const downBtn = e.target.closest(".orbit-move-down-btn");
        const btn = upBtn || downBtn;
        if (!btn) return;

        moveDispatchRow(btn.dataset.orderItemId, upBtn ? "up" : "down");
    });

    // --- ▼ SECTION 04: 依頼書スプレッドシートの設定（URL・シート名） ▼ ---
    const sheetUrlInput = document.getElementById("orbit-dispatch-sheet-url");
    const sheetNameInput = document.getElementById("orbit-dispatch-sheet-name");
    const sheetSettingsSaveBtn = document.getElementById("orbit-dispatch-sheet-settings-save-btn");

    // 依頼書スプレッドシートの設定を読み込んで欄に反映
    fetch("/orbit/dispatch_sheet_settings")
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") return;
            if (sheetUrlInput) sheetUrlInput.value = data.spreadsheet_url || "";
            if (sheetNameInput) sheetNameInput.value = data.sheet_name || "";
        })
        .catch(err => console.error("dispatch_sheet_settings load error:", err));

    sheetSettingsSaveBtn?.addEventListener("click", () => {
        fetch("/orbit/dispatch_sheet_settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                spreadsheet_url: sheetUrlInput?.value || "",
                sheet_name: sheetNameInput?.value || "",
            }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.("設定を保存しました", "success");
                } else {
                    window.showToast?.(data.message || "保存に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("dispatch_sheet_settings save error:", err);
                window.showToast?.("保存に失敗しました", "error");
            });
    });

    loadOrders();
};
