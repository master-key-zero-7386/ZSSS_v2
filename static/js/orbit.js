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
// 依頼日・JAN・発送種別・トラッキング・仕入価格・備考など「依頼書シート」形式の列は
// 統合画面（CA/US/AU全市場をまとめる場所）側の担当なので、ここには置かない。
// N番号のみ、取込直後にこの画面で採番したいという運用のため例外的にここで入力する
// （連番は列見出しクリックでの並び替え・↕での手動移動を含む「今の画面の表示順」を基準に振られる）。
const ORBIT_COLUMNS = [
    { key: "delete", label: "", deleteButton: true },

    // --- 買い手照合（住所ベース。過去の購入履歴・返品セキュリティメモとの突き合わせ結果） ---
    { key: "repeat_badge", label: "回", repeatBadge: true },
    { key: "security_badge", label: "⚠要注意", securityBadge: true },

    // --- N番号（発送代行会社の管理連番。↕で並び替えてから先頭行に開始番号を入れると、
    //     以降の行(画面の表示順)に自動で連番が振られる） ---
    { key: "move", label: "↕", moveButtons: true },
    { key: "agent_serial_no", label: "N番号", editable: "number", isSerial: true },

    // --- ZSSS算定（listed_items→catalog_cache→手入力 の順で自動取得。取れない場合のみ下の手入力欄を使う） ---
    { key: "asin", label: "ASIN", copyClass: "asin-cell" },
    { key: "dims_source", label: "寸法取得元" },
    { key: "fetch_catalog", label: "", fetchCatalogButton: true },
    { key: "length_cm", label: "長さ(cm)" },
    { key: "width_cm", label: "幅(cm)" },
    { key: "height_cm", label: "高さ(cm)" },
    { key: "actual_weight_kg", label: "実重量(kg)" },
    { key: "billable_weight_kg", label: "請求重量(kg)" },
    { key: "predicted_shipping_fee", label: "送料" },
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

// --- ▼ SECTION 00-1a: 仕入先の選択肢（発注管理・仕入れ管理で共用） ▼ ---
const SUPPLIER_OPTIONS = [
    "-", "Amazon", "Rakuten", "Rakuten2", "Qoo10",
    "marunishi", "marunishi2", "marunishi3",
    "ﾔﾏﾀﾞｳｪﾌﾞｺﾑ", "PayPay", "Yahoo", "au",
];

// --- ▼ SECTION 00-1b: 発注管理（＝唯一の作業タブ）列定義 ▼ ---
// アコーディオン行：1注文＝主行1行（±で展開）。展開すると下に「注文者情報／仕入れ情報／…」が段組みで開く。
// 横に伸びない。取込後の確認・チェック・仕入入力・代行会社連絡をこの1タブで完結させる。
//
// 主行↔展開部の振り分け・順番は下記 DISPATCH_PRIMARY_KEYS / DISPATCH_DETAIL_SECTIONS を編集するだけで変えられる。
// 各キーのセルの見た目（編集可否・トグル・色付け等）は DISPATCH_COLUMNS のレジストリで定義。
const DISPATCH_COLUMNS = [
    { key: "agent_serial_no", label: "N番", highlight: true },  // 受注一覧タブで採番
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell", marketColor: true },  // クリックでコピー＋マーケット色
    { key: "promise_date", label: "出荷期日", dateOnly: true, deadline: true },
    { key: "issue_summary", label: "⚠", issueSummary: true },
    { key: "security_badge", label: "要注意", securityBadge: true },
    { key: "security_note_add", label: "📝", securityNoteButton: true },
    { key: "ship_country", label: "国" },
    { key: "quantity_purchased", label: "数量", qtyWarn: true },  // 2以上で色（発注数量チェック）
    { key: "product_name_effective", label: "商品名", checkFlagKey: "flag_product_name", editable: "text", saveField: "product_name_override", mid: true },
    { key: "shipping_type", label: "発送種別", editable: "text", datalist: "orbit-dl-shipping-type" },  // 過去入力値をプルダウン候補に。新規も自由入力可
    { key: "agent_tracking_number", label: "トラッキング", copyClass: "orbit-orderid-cell" },  // 通知すべき番号（代行会社読み戻し）
    { key: "agent_weight_recorded_date", label: "代行出荷日", redUntilShipped: true },  // 代行会社がいつ出荷したか
    { key: "shipped_completed", label: "出荷通知", shippedToggle: true },  // 自分がAmazon側へ出荷通知＝完了（グレーアウト）
    { key: "purchased", label: "仕入確認", flagToggle: true, flagOnLabel: "仕入済", flagOffLabel: "未仕入" },
    { key: "invoice_saved", label: "領収書", flagToggle: true, flagOnLabel: "保存済", flagOffLabel: "未保存" },
    { key: "remarks", label: "備考1", editable: "text", mid: true },
    { key: "remarks_2", label: "備考2", editable: "text", mid: true },
    { key: "remarks_3", label: "備考3", editable: "text", mid: true },

    // 展開部
    { key: "recipient_name_effective", label: "宛名", checkFlagKey: "flag_recipient_name", editable: "text", saveField: "recipient_name_override" },
    { key: "buyer_phone_number_effective", label: "電話番号", checkFlagKey: "flag_phone_country_code", editable: "text", saveField: "buyer_phone_number_override" },
    { key: "buyer_phone_extension_effective", label: "内線", editable: "text", saveField: "buyer_phone_extension_override" },
    { key: "ship_address_1_effective", label: "住所1", checkFlagKey: "flag_address1_length", editable: "text", saveField: "ship_address_1_override", mid: true },
    { key: "ship_address_2_effective", label: "住所2", checkFlagKey: "flag_address2_length", editable: "text", saveField: "ship_address_2_override", mid: true },
    { key: "ship_address_3_effective", label: "住所3", checkFlagKey: "flag_address3_length", editable: "text", saveField: "ship_address_3_override", mid: true },
    { key: "ship_state_effective", label: "州", checkFlagKey: "flag_state_expanded", editable: "text", saveField: "ship_state_override" },
    { key: "ship_postal_code", label: "郵便番号", checkFlagKey: "flag_postal_code_missing" },

    { key: "supplier", label: "仕入先", editable: "select", options: SUPPLIER_OPTIONS },
    { key: "supplier_order_number", label: "仕入注文番号", editable: "text" },
    { key: "supplier_shop_name", label: "ショップ名", editable: "text" },
    { key: "supplier_link", label: "リンク", computed: true },
    { key: "procurement_date", label: "仕入日", editable: "text" },
    { key: "request_date", label: "依頼日" },  // 仕入日を入れると自動反映
    { key: "arrival_date", label: "到着予定", editable: "text" },
    { key: "purchase_price", label: "仕入価格(円)", editable: "number" },
    { key: "invoice_price_jpy", label: "インボイス価格(円)" },  // 販売額の97%。自動算定のみ
    { key: "points", label: "ポイント", editable: "number" },
    { key: "jan_code", label: "JAN", editable: "text" },
    { key: "asin", label: "ASIN", copyClass: "asin-cell" },

    { key: "agent_thankyou_letter", label: "サンクスレター内容" },
    { key: "agent_option_content", label: "オプション内容" },
    { key: "agent_option_fee", label: "オプション料計" },
    { key: "agent_non_deliverable_weight", label: "配送不可重量" },
    { key: "agent_shipping_weight", label: "発送重量" },
    { key: "agent_confirmed_weight", label: "確定重量" },
    { key: "agent_deadline", label: "期限" },
    { key: "agent_status", label: "状況" },
    { key: "agent_shipping_fee", label: "送料" },
    { key: "agent_shipping_fee_total", label: "送料合計" },
    { key: "agent_delivery_area", label: "配送エリア" },
    { key: "agent_synced_at", label: "読戻し日時" },

    { key: "agent_shipping_weight_kg", label: "想定重量(kg)" },
    { key: "agent_length_cm", label: "長さ" },
    { key: "agent_width_cm", label: "幅" },
    { key: "agent_height_cm", label: "高さ" },

    { key: "fetch_fee_estimate", label: "手数料見積り", fetchFeeEstimateButton: true },
    { key: "sale_price_used", label: "販売額", profitHighlight: true, saleAmountCell: true, currencyKey: "sale_price_used_currency", splitFlagKey: "settlement_is_split" },
    { key: "net_proceeds_used", label: "入金額(現地)", profitHighlight: true, saleAmountCell: true, currencyKey: "net_proceeds_used_currency", estimateFlagKey: "net_proceeds_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "net_proceeds_used_jpy", label: "入金額(円)", profitHighlight: true, estimateFlagKey: "net_proceeds_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "shipping_cost_used", label: "送料(円)", profitHighlight: true, estimateFlagKey: "shipping_cost_is_estimate" },
    { key: "profit_jpy", label: "利益(円)", profitHighlight: true, estimateFlagKey: "profit_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "profit_rate_pct", label: "利益率(%)", profitHighlight: true, percentCell: true },

    { key: "order_item_id", label: "order-item-id", copyClass: "orbit-orderid-cell" },
    { key: "purchase_date", label: "注文日", dateOnly: true },
];

const DISPATCH_COL_DEFS = Object.fromEntries(DISPATCH_COLUMNS.map(c => [c.key, c]));
const dispatchCol = (key) => DISPATCH_COL_DEFS[key] || { key, label: key };

// 主行に出す列（左から順）。「これ主行に上げて」「順番入れ替え」はこの配列を編集するだけ。
const DISPATCH_PRIMARY_KEYS = [
    "agent_serial_no", "order_id", "promise_date",
    "issue_summary", "security_badge", "security_note_add",
    "ship_country", "quantity_purchased", "product_name_effective", "shipping_type",
    "agent_tracking_number", "agent_weight_recorded_date",
    "shipped_completed", "purchased", "invoice_saved",
    "remarks", "remarks_2", "remarks_3",
];

// 展開部のセクション（ラベル＋列キー）。振り分け・順番はここを編集。
// key はセクション見出しの色分け用（CSS: .orbit-acc-sec-<key>）。
const DISPATCH_DETAIL_SECTIONS = [
    { key: "memo", label: "バイヤーメモ", custom: "buyerMemo" },
    { key: "buyer", label: "注文者情報", keys: [
        "recipient_name_effective", "buyer_phone_number_effective", "buyer_phone_extension_effective",
        "ship_address_1_effective", "ship_address_2_effective", "ship_address_3_effective",
        "ship_state_effective", "ship_postal_code",
    ] },
    { key: "proc", label: "仕入れ情報", keys: [
        "supplier", "supplier_order_number", "supplier_shop_name", "supplier_link",
        "procurement_date", "request_date", "arrival_date",
        "purchase_price", "invoice_price_jpy", "points", "jan_code", "asin",
    ] },
    { key: "agent", label: "代行会社", keys: [
        "agent_thankyou_letter", "agent_option_content", "agent_option_fee", "agent_non_deliverable_weight",
        "agent_shipping_weight", "agent_confirmed_weight", "agent_deadline", "agent_status",
        "agent_shipping_fee", "agent_shipping_fee_total", "agent_delivery_area", "agent_synced_at",
    ] },
    { key: "dims", label: "サイズ・重量", keys: ["agent_shipping_weight_kg", "agent_length_cm", "agent_width_cm", "agent_height_cm"] },
    { key: "profit", label: "利益", keys: [
        "fetch_fee_estimate", "sale_price_used", "net_proceeds_used", "net_proceeds_used_jpy",
        "shipping_cost_used", "profit_jpy", "profit_rate_pct",
    ] },
    { key: "ref", label: "参照", keys: ["order_item_id", "purchase_date"] },
];

// --- ▼ SECTION 00-2: 仕入れ管理 列定義 ▼ ---
// SUPPLIER_OPTIONS は SECTION 00-1a で定義済み（発注管理と共用）。

const PROCUREMENT_COLUMNS = [
    // --- 出荷完了フラグ（押し間違えてもボタンをもう一度押せば解除できる。行全体がグレーアウトされる） ---
    { key: "shipped_completed", label: "出荷完了", shippedToggle: true },

    // --- 仕入れ・出荷時に頻繁にチェックする項目（発注管理側のN番号と対応づけて左端に配置） ---
    { key: "agent_serial_no", label: "N番号", highlight: true },  // 発注管理タブで入力（読取専用）
    { key: "asin", label: "ASIN", copyClass: "asin-cell", highlight: true },
    { key: "procurement_date", label: "仕入日", editable: "text", highlight: true },
    { key: "arrival_date", label: "到着予定日", editable: "text", highlight: true },

    { key: "promise_date", label: "出荷期日", dateOnly: true, deadline: true },
    { key: "purchase_date", label: "注文日", dateOnly: true },

    // --- 発注管理で代行会社シートを取り込むと入る項目（出荷に必要な情報を1画面で確認できるようここにも表示） ---
    { key: "remarks", label: "備考1(通常通知)" },
    { key: "remarks_2", label: "備考2(仕入追跡)" },
    { key: "remarks_3", label: "備考3(GST/BAT)" },
    { key: "agent_tracking_number", label: "トラッキング(海外向け)", copyClass: "orbit-orderid-cell" },
    { key: "agent_weight_recorded_date", label: "発送重量記入日", redUntilShipped: true },
    { key: "agent_confirmed_weight", label: "確定重量" },
    { key: "agent_shipping_fee_total", label: "送料合計" },

    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell", marketColor: true },
    { key: "order_item_id", label: "order-item-id" },
    // JANをグループの先頭にしてトグルボタンを表示（JAN自体はgroupHeadなので折りたたんでも隠れない）。
    // 折りたたみ対象は商品名〜国まで（仕入先以降の入力欄は常に表示する）
    { key: "jan_code", label: "JAN", editable: "text", group: "procShrink", groupHead: true },
    { key: "product_name", label: "商品名", group: "procShrink" },
    { key: "quantity_purchased", label: "数量", group: "procShrink" },
    { key: "ship_country", label: "国", group: "procShrink" },

    { key: "supplier", label: "仕入先", editable: "select", options: SUPPLIER_OPTIONS },
    { key: "supplier_order_number", label: "注文番号", editable: "text" },
    { key: "supplier_shop_name", label: "ショップ名", editable: "text" },
    { key: "supplier_link", label: "注文リンク", computed: true },
    { key: "purchase_price", label: "仕入価格(円)", editable: "number" },

    // --- 実利益。入金額は「決済トランザクション実績」＞「手数料見積り概算」の順で採用、送料は
    //     「代行会社確定額」＞「ZSSS予測概算」の順で採用（円換算、いずれか概算のときは(概算)と表示） ---
    { key: "fetch_fee_estimate", label: "", fetchFeeEstimateButton: true },
    { key: "sale_price_used", label: "販売額(現地通貨)", profitHighlight: true, saleAmountCell: true, currencyKey: "sale_price_used_currency", splitFlagKey: "settlement_is_split" },
    { key: "net_proceeds_used", label: "入金額(現地通貨)", profitHighlight: true, saleAmountCell: true, currencyKey: "net_proceeds_used_currency", estimateFlagKey: "net_proceeds_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "net_proceeds_used_jpy", label: "入金額(円)", profitHighlight: true, estimateFlagKey: "net_proceeds_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "shipping_cost_used", label: "送料(円)", profitHighlight: true, estimateFlagKey: "shipping_cost_is_estimate" },
    { key: "profit_jpy", label: "利益(円)", profitHighlight: true, estimateFlagKey: "profit_is_estimate", splitFlagKey: "settlement_is_split" },
    { key: "profit_rate_pct", label: "利益率(%)", profitHighlight: true, percentCell: true },
];

// --- ▼ SECTION 00-3: 買い手履歴タブ 列定義 ▼ ---
// 買い手購入履歴はAmazon注文レポートの生データ＋N番だけの一覧（過去に買ったことがあるかの確認用）。
const BUYER_HISTORY_COLUMNS = [
    { key: "agent_serial_no", label: "N番" },
    { key: "purchase_date", label: "購入日", dateOnly: true },
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "buyer_name", label: "buyer-name" },
    { key: "recipient_name", label: "recipient-name" },
    { key: "ship_address_1", label: "住所1" },
    { key: "ship_city", label: "市区町村" },
    { key: "ship_state", label: "州" },
    { key: "ship_postal_code", label: "郵便番号" },
    { key: "ship_country", label: "国" },
    { key: "sku", label: "sku" },
    { key: "product_name", label: "product-name" },
    { key: "quantity_purchased", label: "数量" },
    { key: "source", label: "区分" },
    { key: "archived_at", label: "アーカイブ日時" },
];

// 返品・セキュリティメモ一覧（発注管理タブの「📝メモ追加」で登録した内容の確認用）
const SECURITY_NOTES_COLUMNS = [
    { key: "created_at", label: "登録日時" },
    { key: "recipient_name", label: "recipient-name" },
    { key: "ship_address_1", label: "住所1" },
    { key: "ship_postal_code", label: "郵便番号" },
    { key: "order_id", label: "order-id", copyClass: "orbit-orderid-cell" },
    { key: "order_item_id", label: "order-item-id" },
    { key: "note", label: "メモ", wide: true },
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

// order-idの先頭桁でマーケットプレイスを判定して色分け（旧スプレッドシートと同じ基準）。
// 1→US(白) ／ 7→CA(薄いオレンジ) ／ 2・5→AU(水色)。出荷完了行のグレーアウトが優先される。
function getOrderMarketColorClass(orderId) {
    const s = String(orderId ?? "").trim();
    if (/^1/.test(s)) return "orbit-market-us";
    if (/^7/.test(s)) return "orbit-market-ca";
    if (/^[25]/.test(s)) return "orbit-market-au";
    return "";
}

const JPY_ROUNDED_KEYS = ["net_proceeds_used_jpy", "shipping_cost_used", "profit_jpy", "predicted_shipping_fee"];

// 見積り(概算)・1注文複数商品の按分(按分)の目印。決済実績が確定していれば両方falseになる想定
function estimateSuffix(col, r) {
    if (col.estimateFlagKey && r[col.estimateFlagKey]) return " (概算)";
    if (col.splitFlagKey && r[col.splitFlagKey]) return " (按分)";
    return "";
}

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
        let extraHeadClass = [
            (col.group && !col.groupHead) ? `orbit-group-${col.group}` : "",
            col.highlight ? "orbit-check-highlight" : "",
            col.profitHighlight ? "orbit-profit-highlight" : "",
            col.deadline ? "orbit-deadline-col" : "",
        ].filter(Boolean).join(" ");
        if (col.key === "agent_serial_no") extraHeadClass = `${extraHeadClass} orbit-serial-cell`.trim();
        const groupClass = extraHeadClass ? ` ${extraHeadClass}` : "";
        const toggleBtn = col.groupHead
            ? `<button type="button" class="orbit-group-toggle-btn" data-group="${col.group}" title="折りたたみ/展開">${collapsedGroups.has(col.group) ? "▸" : "▾"}</button> `
            : "";

        // 手数料見積り列のヘッダーには、表示中の未取得行だけをまとめて取得する一括ボタンを出す
        if (col.fetchFeeEstimateButton) {
            return `<th class="${groupClass.trim()}"><button type="button" class="orbit-fetch-fee-all-btn btn-blue" title="表示中の未取得（「手数料取得」）行だけをまとめて取得します">一括取得</button></th>`;
        }

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

function renderTableRows(tbody, columns, rows, { grayShipped } = {}) {
    tbody.innerHTML = "";

    rows.forEach(r => {
        const tr = document.createElement("tr");
        tr.dataset.orderItemId = r.order_item_id;
        // キャンセル注文（発送種別＝キャンセル）は仕入れ時の誤発注防止のため全タブで行を緑にする。
        // 出荷完了を押したら、他の完了行と同じくグレーアウトへ切り替える。
        const isCancelOrder = (r.shipping_type || "").trim() === "キャンセル";
        if (r.shipped_completed && (grayShipped || isCancelOrder)) {
            tr.classList.add("orbit-row-shipped");
        } else if (isCancelOrder) {
            tr.classList.add("orbit-row-cancel");
        } else if (!r.purchased && !r.shipped_completed) {
            // 仕入確認が未チェックの行を薄黄色に（仕入れ忘れ防止。キャンセル緑・出荷完了グレーが優先）
            tr.classList.add("orbit-row-unpurchased");
        }

        tr.innerHTML = columns.map(col => {
            let cellClass = col.deadline ? `orbit-deadline-col ${getDeadlineColorClass(r[col.key])}`.trim() : "";
            if (col.group && !col.groupHead) cellClass = `${cellClass} orbit-group-${col.group}`.trim();
            if (col.checkFlagKey && r[col.checkFlagKey]) cellClass = `${cellClass} orbit-issue-flag`.trim();
            if (col.highlight) cellClass = `${cellClass} orbit-check-highlight`.trim();
            if (col.profitHighlight) cellClass = `${cellClass} orbit-profit-highlight`.trim();
            if (col.redUntilShipped && r[col.key] && !r.shipped_completed) cellClass = `${cellClass} orbit-text-red`.trim();
            if (col.key === "agent_serial_no") cellClass = `${cellClass} orbit-serial-cell`.trim();
            if (col.marketColor) cellClass = `${cellClass} ${getOrderMarketColorClass(r[col.key])}`.trim();
            if (col.qtyWarn && Number(r[col.key]) >= 2) cellClass = `${cellClass} orbit-qty-warn`.trim();

            if (col.shippedToggle) {
                const done = !!r[col.key];
                return `<td class="${cellClass}" style="text-align:center;"><button type="button" class="orbit-shipped-toggle-btn ${done ? "btn-red" : "btn-blue"}" data-order-item-id="${r.order_item_id}" data-shipped="${done ? 1 : 0}">${done ? "解除" : "出荷完了"}</button></td>`;
            }

            if (col.flagToggle) {
                const on = !!r[col.key];
                return `<td class="${cellClass}" style="text-align:center;"><button type="button" class="orbit-flag-toggle-btn ${on ? "is-on" : "is-off"}" data-order-item-id="${r.order_item_id}" data-field="${col.key}" data-value="${on ? 1 : 0}">${on ? (col.flagOnLabel || "ON") : (col.flagOffLabel || "OFF")}</button></td>`;
            }

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
                const fetched = r.fee_estimate_amount != null;
                const label = fetched ? "手数料再取得" : "手数料取得";
                return `<td><button type="button" class="orbit-fetch-fee-btn btn-blue" data-order-item-id="${r.order_item_id}"${fetched ? ' data-fee-fetched="1"' : ''}>${label}</button></td>`;
            }

            if (col.percentCell) {
                if (r[col.key] == null) return `<td class="${cellClass}"></td>`;
                const negClass = r[col.key] < 0 ? " orbit-text-red" : "";
                return `<td class="${cellClass}${negClass}">${(Math.round(r[col.key] * 10) / 10).toLocaleString()}%</td>`;
            }

            if (col.issueSummary) {
                const active = DISPATCH_ISSUE_FLAGS.filter(f => r[f.key]);
                if (!active.length) return "<td></td>";
                return `<td class="orbit-issue-flag" style="text-align:center;" title="${active.map(f => f.label).join(" / ")}">⚠</td>`;
            }

            if (col.repeatBadge) {
                const count = r.repeat_buyer_count || 0;
                // 初回（履歴0〜1件）は表示しない。2件以上一致したときだけリピーターとして数字を出す。
                if (count < 2) return "<td></td>";
                return `<td class="orbit-repeat-flag" style="text-align:center;" title="過去${count}回購入しています">${count}</td>`;
            }

            if (col.securityBadge) {
                const notes = r.security_notes || [];
                if (!notes.length) return "<td></td>";
                return `<td class="orbit-security-flag" style="text-align:center;" title="${notes.map(n => n.note).join(" / ")}">⚠要注意</td>`;
            }

            if (col.securityNoteButton) {
                return `<td><button type="button" class="orbit-security-note-btn" data-order-item-id="${r.order_item_id}">📝メモ追加</button></td>`;
            }

            if (col.blank) return "<td></td>";

            if (col.saleAmountCell) {
                if (r[col.key] == null) return `<td class="${cellClass}"></td>`;
                const amount = Math.round(r[col.key] * 100) / 100;
                const currency = r[col.currencyKey] || "";
                return `<td class="${cellClass}">${amount.toLocaleString()} ${currency}${estimateSuffix(col, r)}</td>`;
            }

            if (col.estimateFlagKey || col.splitFlagKey) {
                const suffix = r[col.key] != null ? estimateSuffix(col, r) : "";
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
                const inputClass = col.wide ? "orbit-manual orbit-manual-wide"
                    : col.mid ? "orbit-manual orbit-manual-mid"
                    : "orbit-manual";
                return `<td class="${cellClass}"><input type="${col.editable}" class="${inputClass}" data-field="${col.saveField || col.key}" value="${value}" title="${value}"></td>`;
            }

            return `<td class="${cellClass}">${fmtValue(col, r[col.key])}</td>`;
        }).join("");

        tbody.appendChild(tr);
    });
}

// ===== 発注管理タブ：アコーディオン行レンダラ =====
// 1注文＝主行1行（±で展開）＋ 隠し詳細行（段組み）。横に伸びない。
// セルの見た目ロジックは renderTableRows と重複するが、詳細部は <td> ではなく label+value の
// インライン要素で描くため専用に持つ（他タブのレンダラには影響させない）。
function dispCellClass(col, r) {
    let c = col.deadline ? `orbit-deadline-col ${getDeadlineColorClass(r[col.key])}`.trim() : "";
    if (col.checkFlagKey && r[col.checkFlagKey]) c += " orbit-issue-flag";
    if (col.highlight) c += " orbit-check-highlight";
    if (col.profitHighlight) c += " orbit-profit-highlight";
    if (col.redUntilShipped && r[col.key] && !r.shipped_completed) c += " orbit-text-red";
    if (col.key === "agent_serial_no") c += " orbit-serial-cell";
    if (col.marketColor) c += " " + getOrderMarketColorClass(r[col.key]);
    if (col.qtyWarn && Number(r[col.key]) >= 2) c += " orbit-qty-warn";
    return c.trim();
}

function dispCellInner(col, r) {
    if (col.issueSummary) {
        const active = DISPATCH_ISSUE_FLAGS.filter(f => r[f.key]);
        return active.length ? `<span class="orbit-issue-flag" title="${active.map(f => f.label).join(" / ")}">⚠</span>` : "";
    }
    if (col.securityBadge) {
        const notes = r.security_notes || [];
        return notes.length ? `<span class="orbit-security-flag" title="${notes.map(n => n.note).join(" / ")}">⚠要注意</span>` : "";
    }
    if (col.securityNoteButton) {
        return `<button type="button" class="orbit-security-note-btn" data-order-item-id="${r.order_item_id}">📝</button>`;
    }
    if (col.shippedToggle) {
        const done = !!r[col.key];
        return `<button type="button" class="orbit-shipped-toggle-btn ${done ? "btn-red" : "btn-blue"}" data-order-item-id="${r.order_item_id}" data-shipped="${done ? 1 : 0}">${done ? "解除" : (col.label || "出荷完了")}</button>`;
    }
    if (col.flagToggle) {
        const on = !!r[col.key];
        return `<button type="button" class="orbit-flag-toggle-btn ${on ? "is-on" : "is-off"}" data-order-item-id="${r.order_item_id}" data-field="${col.key}" data-value="${on ? 1 : 0}">${on ? (col.flagOnLabel || "ON") : (col.flagOffLabel || "OFF")}</button>`;
    }
    if (col.key === "supplier_link") {
        const link = buildSupplierLink(r.supplier, r.supplier_order_number);
        return link ? `<a href="${link}" target="_blank" rel="noopener">開く</a>` : "";
    }
    if (col.fetchFeeEstimateButton) {
        if (r.net_proceeds != null || !r.asin) return "";
        const fetched = r.fee_estimate_amount != null;
        return `<button type="button" class="orbit-fetch-fee-btn btn-blue" data-order-item-id="${r.order_item_id}"${fetched ? ' data-fee-fetched="1"' : ""}>${fetched ? "手数料再取得" : "手数料取得"}</button>`;
    }
    if (col.percentCell) {
        if (r[col.key] == null) return "";
        const neg = r[col.key] < 0 ? ' class="orbit-text-red"' : "";
        return `<span${neg}>${(Math.round(r[col.key] * 10) / 10).toLocaleString()}%</span>`;
    }
    if (col.saleAmountCell) {
        if (r[col.key] == null) return "";
        const amount = Math.round(r[col.key] * 100) / 100;
        const currency = r[col.currencyKey] || "";
        return `${amount.toLocaleString()} ${currency}${estimateSuffix(col, r)}`;
    }
    if (col.estimateFlagKey || col.splitFlagKey) {
        const suffix = r[col.key] != null ? estimateSuffix(col, r) : "";
        return `${fmtValue(col, r[col.key])}${suffix}`;
    }
    if (col.copyClass && !col.editable) {
        return `<span class="${col.copyClass}" style="color:#007bff;text-decoration:underline;cursor:pointer;" title="クリックでコピー">${fmtValue(col, r[col.key])}</span>`;
    }
    if (col.editable === "select") {
        const current = r[col.key] ?? "";
        const options = col.options.map(o => `<option value="${o}"${o === current ? " selected" : ""}>${o}</option>`).join("");
        return `<select class="orbit-manual" data-field="${col.key}">${options}</select>`;
    }
    if (col.editable) {
        const value = r[col.key] ?? "";
        const cls = col.wide ? "orbit-manual orbit-manual-wide" : col.mid ? "orbit-manual orbit-manual-mid" : "orbit-manual";
        const listAttr = col.datalist ? ` list="${col.datalist}"` : "";
        return `<input type="${col.editable}" class="${cls}"${listAttr} data-field="${col.saveField || col.key}" value="${value}" title="${value}">`;
    }
    return fmtValue(col, r[col.key]);
}

function orbitEscapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
}

// 展開部「バイヤーメモ」：リピーター購入回数＋返品/セキュリティメモ全文（住所キーで突き合わせ済み）。
function renderBuyerMemoBlock(r) {
    const count = r.repeat_buyer_count || 0;
    const notes = r.security_notes || [];

    const repeatHtml = count >= 2
        ? `<span class="orbit-memo-repeat is-repeat" title="過去${count}回購入しています">リピーター ${count}回</span>`
        : `<span class="orbit-memo-repeat">初回</span>`;

    const notesHtml = notes.length
        ? `<ul class="orbit-memo-list">` + notes.map(n => {
            const d = (n.created_at || "").slice(0, 10);
            return `<li><span class="orbit-memo-date">${orbitEscapeHtml(d)}</span> ${orbitEscapeHtml(n.note)}</li>`;
        }).join("") + `</ul>`
        : `<span class="orbit-memo-none">メモなし</span>`;

    return `${repeatHtml}${notesHtml}` +
        `<button type="button" class="orbit-security-note-btn orbit-memo-add-btn" data-order-item-id="${r.order_item_id}">📝メモ追加</button>`;
}

function renderDispatchAccordion(tbody, rows, expandedSet) {
    if (!tbody) return;
    const primaryCols = DISPATCH_PRIMARY_KEYS.map(dispatchCol);
    const colspan = primaryCols.length + 1;  // ＋トグル列

    const html = rows.map(r => {
        const oid = r.order_item_id;
        const isCancel = (r.shipping_type || "").trim() === "キャンセル";
        let rowCls = "orbit-acc-main";
        if (r.shipped_completed) rowCls += " orbit-row-shipped";
        else if (isCancel) rowCls += " orbit-row-cancel";
        else if (!r.purchased) rowCls += " orbit-row-unpurchased";

        const open = expandedSet.has(oid);

        const mainCells = primaryCols.map(col =>
            `<td class="${dispCellClass(col, r)}">${dispCellInner(col, r)}</td>`
        ).join("");

        const detailBody = DISPATCH_DETAIL_SECTIONS.map(sec => {
            const body = sec.custom === "buyerMemo"
                ? renderBuyerMemoBlock(r)
                : (sec.keys || []).map(dispatchCol).map(col => `
                    <span class="orbit-acc-field ${dispCellClass(col, r)}">
                        <span class="orbit-acc-field-label">${col.label}</span>
                        <span class="orbit-acc-field-value">${dispCellInner(col, r)}</span>
                    </span>`).join("");
            const hasNotes = sec.custom === "buyerMemo" && (r.security_notes || []).length ? " has-notes" : "";
            return `
                <div class="orbit-acc-section orbit-acc-sec-${sec.key || "x"}${hasNotes}">
                    <span class="orbit-acc-section-label">${sec.label}</span>
                    ${body}
                </div>`;
        }).join("");

        return `
            <tr class="${rowCls}" data-order-item-id="${oid}">
                <td class="orbit-acc-toggle-cell"><button type="button" class="orbit-acc-toggle" data-order-item-id="${oid}" title="展開/縮小">${open ? "−" : "＋"}</button></td>
                ${mainCells}
            </tr>
            <tr class="orbit-acc-detail" data-order-item-id="${oid}"${open ? "" : " hidden"}>
                <td class="orbit-acc-detail-cell" colspan="${colspan}">${detailBody}</td>
            </tr>`;
    }).join("");

    tbody.innerHTML = html;
}

function saveManualField(orderItemId, field, value, onDone) {
    const payload = { order_item_id: orderItemId };
    payload[field] = (field === "purchase_price" || field === "points")
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

    // 買い手履歴タブ（買い手購入履歴一覧・返品セキュリティメモ一覧。早期returnより前に取得しておく）
    const buyerHistoryTable = document.getElementById("orbit-buyer-history-table");
    const buyerHistoryThead = buyerHistoryTable?.querySelector("thead tr");
    const buyerHistoryTbody = buyerHistoryTable?.querySelector("tbody");

    const securityNotesTable = document.getElementById("orbit-security-notes-table");
    const securityNotesThead = securityNotesTable?.querySelector("thead tr");
    const securityNotesTbody = securityNotesTable?.querySelector("tbody");

    // 買い手購入履歴テーブルは列見出しクリックで並び替えできる（初期表示はN番の昇順）
    let buyerHistoryRowsCache = [];
    let buyerHistorySortState = { key: "agent_serial_no", dir: "asc" };

    function renderBuyerHistoryTable() {
        const rows = buyerHistorySortState
            ? sortRowsByKey(buyerHistoryRowsCache, buyerHistorySortState.key, buyerHistorySortState.dir)
            : buyerHistoryRowsCache;
        renderTableRows(buyerHistoryTbody, BUYER_HISTORY_COLUMNS, rows);
    }

    function onBuyerHistorySort(key) {
        if (buyerHistorySortState && buyerHistorySortState.key === key) {
            buyerHistorySortState = { key, dir: buyerHistorySortState.dir === "asc" ? "desc" : "asc" };
        } else {
            buyerHistorySortState = { key, dir: "asc" };
        }
        if (buyerHistoryThead) renderTableHeader(buyerHistoryThead, BUYER_HISTORY_COLUMNS, { sortable: true, onSort: onBuyerHistorySort, sortState: buyerHistorySortState });
        renderBuyerHistoryTable();
    }

    function loadBuyerHistory() {
        if (!buyerHistoryTbody) return;
        fetch("/orbit/buyer_history/list")
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    buyerHistoryRowsCache = data.rows;
                    renderBuyerHistoryTable();
                } else {
                    window.showToast?.("買い手購入履歴の取得に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/buyer_history/list error:", err);
                window.showToast?.("買い手購入履歴の取得に失敗しました", "error");
            });
    }

    function loadSecurityNotes() {
        if (!securityNotesTbody) return;
        fetch("/orbit/security_notes/list")
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    renderTableRows(securityNotesTbody, SECURITY_NOTES_COLUMNS, data.rows);
                } else {
                    window.showToast?.("返品・セキュリティメモの取得に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/security_notes/list error:", err);
                window.showToast?.("返品・セキュリティメモの取得に失敗しました", "error");
            });
    }

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

    // 受注一覧／発注管理テーブルの状態（並び順キャッシュ・ソート状態）は、早期returnの前に宣言しておく。
    // （2回目以降のinitOrbit()は下の早期returnで抜けるため、ここより後ろで let 宣言すると
    //   loadOrders() の .then が未初期化の変数（TDZ）に触れて ReferenceError となり、
    //   .catch に落ちて「注文一覧の取得に失敗しました」トーストが毎回出てしまう。買い手履歴側と同じ理由。）
    // どちらも初期表示はN番号の昇順（全チェック・出荷チェックの基準がN番号のため）。列見出しクリック等で解除できる。
    let ordersRowsCache = [];
    let ordersSortState = { key: "agent_serial_no", dir: "asc" }; // { key, dir }
    let dispatchRowsCache = [];
    let dispatchSortState = { key: "agent_serial_no", dir: "asc" }; // { key, dir }

    if (tbody.dataset.orbitInitialized === "true") {
        loadOrders();
        loadBuyerHistory();
        loadSecurityNotes();
        return;
    }
    tbody.dataset.orbitInitialized = "true";

    // データ再読込でtbody.innerHTMLを差し替えると、テーブルを囲むtable-wrapperの
    // 横スクロール位置がブラウザによって勝手にリセットされることがあるため、明示的に保持する。
    function renderPreservingScroll(tbodyEl, columns, rows, opts) {
        if (!tbodyEl) return;
        const wrapper = tbodyEl.closest(".table-wrapper");
        const scrollLeft = wrapper ? wrapper.scrollLeft : 0;
        renderTableRows(tbodyEl, columns, rows, opts);
        if (wrapper) wrapper.scrollLeft = scrollLeft;
    }

    // 受注一覧テーブルは列見出しクリックでの並び替え・↕での手動移動ができる
    // （N番号の連番はこの「今の画面の表示順」を基準に振られる）
    // ※ ordersRowsCache / ordersSortState の宣言は早期returnより前へ移動済み（上部参照）

    function renderOrdersTable() {
        const rows = ordersSortState
            ? sortRowsByKey(ordersRowsCache, ordersSortState.key, ordersSortState.dir)
            : ordersRowsCache;
        renderPreservingScroll(tbody, ORBIT_COLUMNS, rows);
    }

    function onOrdersSort(key) {
        if (ordersSortState && ordersSortState.key === key) {
            ordersSortState = { key, dir: ordersSortState.dir === "asc" ? "desc" : "asc" };
        } else {
            ordersSortState = { key, dir: "asc" };
        }
        renderTableHeader(thead, ORBIT_COLUMNS, { sortable: true, onSort: onOrdersSort, sortState: ordersSortState });
        renderOrdersTable();
    }

    function getOrdersOrderedIds() {
        const rows = ordersSortState
            ? sortRowsByKey(ordersRowsCache, ordersSortState.key, ordersSortState.dir)
            : ordersRowsCache;
        return rows.map(r => r.order_item_id);
    }

    // 行を1つ上/下へ手動で移動する（列ソート中の場合は解除して、移動後の並びをそのまま正とする）
    function moveOrderRow(orderItemId, direction) {
        const idx = ordersRowsCache.findIndex(r => r.order_item_id === orderItemId);
        if (idx < 0) return;

        const swapIdx = direction === "up" ? idx - 1 : idx + 1;
        if (swapIdx < 0 || swapIdx >= ordersRowsCache.length) return;

        if (ordersSortState) {
            ordersSortState = null;
            renderTableHeader(thead, ORBIT_COLUMNS, { sortable: true, onSort: onOrdersSort, sortState: ordersSortState });
        }

        [ordersRowsCache[idx], ordersRowsCache[swapIdx]] = [ordersRowsCache[swapIdx], ordersRowsCache[idx]];
        renderOrdersTable();
    }

    // 発注管理テーブル＝アコーディオン行（1注文＝主行＋±展開）。列見出しクリックで並び替え可（主行の列）。
    // ※ dispatchRowsCache / dispatchSortState の宣言は早期returnより前へ移動済み（上部参照）

    // 展開中の注文（order_item_id）。localStorage に保存して再訪でも維持。
    const dispatchExpanded = new Set(
        (() => { try { return JSON.parse(localStorage.getItem("orbitDispatchExpanded") || "[]"); } catch { return []; } })()
    );
    function persistDispatchExpanded() {
        try { localStorage.setItem("orbitDispatchExpanded", JSON.stringify([...dispatchExpanded])); } catch { /* ignore */ }
    }

    // 主行ヘッダー用の列定義（先頭に±トグル列を足す）
    const dispatchHeaderCols = [{ key: "__acc", label: "", blank: true }, ...DISPATCH_PRIMARY_KEYS.map(dispatchCol)];

    // 発送種別の入力候補を、これまでに入力された値から都度更新（datalist）。
    function refreshShippingTypeDatalist() {
        const dl = document.getElementById("orbit-dl-shipping-type");
        if (!dl) return;
        const vals = [...new Set(dispatchRowsCache.map(r => (r.shipping_type || "").trim()).filter(Boolean))].sort();
        dl.innerHTML = vals.map(v => `<option value="${orbitEscapeHtml(v)}"></option>`).join("");
    }

    function renderDispatchTable() {
        const rows = dispatchSortState
            ? sortRowsByKey(dispatchRowsCache, dispatchSortState.key, dispatchSortState.dir)
            : dispatchRowsCache;
        const wrapper = dispatchTbody?.closest(".table-wrapper");
        const scrollLeft = wrapper ? wrapper.scrollLeft : 0;
        refreshShippingTypeDatalist();
        renderDispatchAccordion(dispatchTbody, rows, dispatchExpanded);
        if (wrapper) wrapper.scrollLeft = scrollLeft;
    }

    function onDispatchSort(key) {
        if (dispatchSortState && dispatchSortState.key === key) {
            dispatchSortState = { key, dir: dispatchSortState.dir === "asc" ? "desc" : "asc" };
        } else {
            dispatchSortState = { key, dir: "asc" };
        }
        if (dispatchThead) renderTableHeader(dispatchThead, dispatchHeaderCols, { sortable: true, onSort: onDispatchSort, sortState: dispatchSortState });
        renderDispatchTable();
    }

    function loadOrders() {
        fetch("/orbit/orders")
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    ordersRowsCache = data.rows;
                    renderOrdersTable();
                    // 発注管理・仕入れ管理は出荷チェックを常にN番号で行うため、N番号の昇順で表示する
                    // （N番号未設定の行は末尾。受注一覧での並び替えとは独立）
                    const serialOrderedRows = sortRowsByKey(data.rows, "agent_serial_no", "asc");
                    renderPreservingScroll(procTbody, PROCUREMENT_COLUMNS, serialOrderedRows, { grayShipped: true });
                    dispatchRowsCache = serialOrderedRows;
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

    renderTableHeader(thead, ORBIT_COLUMNS, { sortable: true, onSort: onOrdersSort, sortState: ordersSortState });
    if (procThead) renderTableHeader(procThead, PROCUREMENT_COLUMNS);
    if (dispatchThead) renderTableHeader(dispatchThead, dispatchHeaderCols, { sortable: true, onSort: onDispatchSort, sortState: dispatchSortState });
    if (buyerHistoryThead) renderTableHeader(buyerHistoryThead, BUYER_HISTORY_COLUMNS, { sortable: true, onSort: onBuyerHistorySort, sortState: buyerHistorySortState });
    if (securityNotesThead) renderTableHeader(securityNotesThead, SECURITY_NOTES_COLUMNS);

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

    // --- ▼ SECTION 01-1d: 買い手購入履歴アーカイブへの一括インポート（過去分の一度きりの取込） ▼ ---
    const orbitBuyerHistoryFileInput = document.getElementById("orbitBuyerHistoryFileInput");
    const orbitBuyerHistoryFileName = document.getElementById("orbitBuyerHistoryFileName");
    const orbitBuyerHistoryUploadBtn = document.getElementById("orbitBuyerHistoryUploadBtn");

    orbitBuyerHistoryFileName?.addEventListener("click", () => {
        orbitBuyerHistoryFileInput?.click();
    });

    orbitBuyerHistoryFileInput?.addEventListener("change", (e) => {
        const fileName = e.target.files.length ? e.target.files[0].name : "";
        if (orbitBuyerHistoryFileName) orbitBuyerHistoryFileName.value = fileName;
    });

    orbitBuyerHistoryUploadBtn?.addEventListener("click", () => {
        if (!orbitBuyerHistoryFileInput?.files?.length) {
            window.showToast?.("ファイルを選択してください", "error");
            return;
        }

        const formData = new FormData();
        formData.append("file", orbitBuyerHistoryFileInput.files[0]);

        fetch("/orbit/buyer_history/import", { method: "POST", body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.imported}件インポートしました`, "success");
                    orbitBuyerHistoryFileInput.value = "";
                    if (orbitBuyerHistoryFileName) orbitBuyerHistoryFileName.value = "";
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "インポートに失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/buyer_history/import error:", err);
                window.showToast?.("インポートに失敗しました", "error");
            });
    });

    document.getElementById("orbit-refresh-btn")?.addEventListener("click", loadOrders);
    document.getElementById("orbit-dispatch-refresh-btn")?.addEventListener("click", loadOrders);
    document.getElementById("orbit-buyer-history-refresh-btn")?.addEventListener("click", () => {
        loadBuyerHistory();
        loadSecurityNotes();
    });

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

    // --- ▼ SECTION 01-2c: 仕入れ管理／発注管理：出荷前の概算利益用に手数料見積りを取得 ▼ ---
    const fetchFeeHandler = (e) => {
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
    };
    procTbody?.addEventListener("click", fetchFeeHandler);
    dispatchTbody?.addEventListener("click", fetchFeeHandler);

    // --- ▼ SECTION 01-2c-2: 手数料見積りの一括取得（仕入れ管理・発注管理の手数料列ヘッダーのボタン） ▼ ---
    //     表示中の「手数料取得」ボタンを1件ずつ順番に叩く（SP-APIのレート制限対策で直列実行）。
    const fetchFeeAllHandler = (e) => {
        const btn = e.target.closest(".orbit-fetch-fee-all-btn");
        if (!btn) return;

        // クリックされたヘッダーと同じテーブルの tbody を対象にする（仕入れ管理・発注管理の両対応）。
        const ownTbody = btn.closest("table")?.querySelector("tbody");

        // 未取得分（「手数料取得」）のみ対象。既に取得済み（「手数料再取得」）の行はスキップする。
        const rowBtns = Array.from(ownTbody?.querySelectorAll(".orbit-fetch-fee-btn") || [])
            .filter(b => !b.dataset.feeFetched);
        const ids = rowBtns.map(b => b.dataset.orderItemId).filter(Boolean);
        if (!ids.length) {
            window.showToast?.("未取得の行がありません", "error");
            return;
        }
        if (!confirm(`表示中の未取得${ids.length}件の手数料見積りをまとめて取得します。よろしいですか？`)) return;

        const originalLabel = btn.textContent;
        btn.disabled = true;
        rowBtns.forEach(b => { b.disabled = true; });

        let ok = 0;
        let ng = 0;

        const runNext = (i) => {
            if (i >= ids.length) {
                btn.disabled = false;
                btn.textContent = originalLabel;
                window.showToast?.(`手数料一括取得：成功${ok}件 / 失敗${ng}件`, ng ? "error" : "success");
                loadOrders();
                return;
            }
            btn.textContent = `取得中... ${i + 1}/${ids.length}`;
            fetch("/orbit/orders/fetch_fee_estimate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ order_item_id: ids[i] }),
            })
                .then(res => res.json())
                .then(data => { if (data.status === "success") ok++; else ng++; })
                .catch(err => {
                    console.error("orbit/orders/fetch_fee_estimate (bulk) error:", err);
                    ng++;
                })
                .finally(() => runNext(i + 1));
        };

        runNext(0);
    };
    procThead?.addEventListener("click", fetchFeeAllHandler);
    dispatchThead?.addEventListener("click", fetchFeeAllHandler);

    // --- ▼ SECTION 01-2d: 出荷完了フラグの切り替え（仕入れ管理・発注管理共通。再押しで解除） ▼ ---
    const shippedToggleHandler = (e) => {
        const btn = e.target.closest(".orbit-shipped-toggle-btn");
        if (!btn) return;

        const orderItemId = btn.dataset.orderItemId;
        if (!orderItemId) return;
        const next = btn.dataset.shipped === "1" ? 0 : 1;

        btn.disabled = true;

        fetch("/orbit/orders/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_id: orderItemId, shipped_completed: next }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "更新に失敗しました", "error");
                    btn.disabled = false;
                }
            })
            .catch(err => {
                console.error("orbit/orders/update (shipped_completed) error:", err);
                window.showToast?.("更新に失敗しました", "error");
                btn.disabled = false;
            });
    };
    procTbody?.addEventListener("click", shippedToggleHandler);
    dispatchTbody?.addEventListener("click", shippedToggleHandler);

    // --- ▼ SECTION 01-2e: 発注管理タブのチェック系トグル（仕入確認 purchased / 領収書 invoice_saved。再押しで解除） ▼ ---
    const flagToggleHandler = (e) => {
        const btn = e.target.closest(".orbit-flag-toggle-btn");
        if (!btn) return;

        const orderItemId = btn.dataset.orderItemId;
        const field = btn.dataset.field;
        if (!orderItemId || !field) return;
        const next = btn.dataset.value === "1" ? 0 : 1;

        btn.disabled = true;

        fetch("/orbit/orders/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_id: orderItemId, [field]: next }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    loadOrders();
                } else {
                    window.showToast?.(data.message || "更新に失敗しました", "error");
                    btn.disabled = false;
                }
            })
            .catch(err => {
                console.error("orbit/orders/update (flag toggle) error:", err);
                window.showToast?.("更新に失敗しました", "error");
                btn.disabled = false;
            });
    };
    procTbody?.addEventListener("click", flagToggleHandler);
    dispatchTbody?.addEventListener("click", flagToggleHandler);

    // --- ▼ SECTION 01-2f: 発注管理アコーディオン行の ± 展開/縮小 ▼ ---
    dispatchTbody?.addEventListener("click", (e) => {
        const btn = e.target.closest(".orbit-acc-toggle");
        if (!btn) return;
        const oid = btn.dataset.orderItemId;
        if (!oid) return;

        const detailRow = dispatchTbody.querySelector(`tr.orbit-acc-detail[data-order-item-id="${CSS.escape(oid)}"]`);
        if (dispatchExpanded.has(oid)) {
            dispatchExpanded.delete(oid);
            if (detailRow) detailRow.hidden = true;
            btn.textContent = "＋";
        } else {
            dispatchExpanded.add(oid);
            if (detailRow) detailRow.hidden = false;
            btn.textContent = "−";
        }
        persistDispatchExpanded();
    });

    // 全部展開 / 全部畳む
    document.getElementById("orbit-dispatch-expand-all-btn")?.addEventListener("click", () => {
        dispatchRowsCache.forEach(r => dispatchExpanded.add(r.order_item_id));
        persistDispatchExpanded();
        renderDispatchTable();
    });
    document.getElementById("orbit-dispatch-collapse-all-btn")?.addEventListener("click", () => {
        dispatchExpanded.clear();
        persistDispatchExpanded();
        renderDispatchTable();
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

    // --- ▼ SECTION 01-3b: 買い手購入履歴アーカイブへの移動（半自動：候補確認→実行）。
    //     対象＝出荷完了 かつ 決済レポートで入金額・手数料が確定した注文。移動後もデータは消えず
    //     orbit_buyer_historyへ引き継がれる（元に戻せないのは注文明細そのものだけで、
    //     返品・セキュリティのメモはアーカイブ後でも別途追加できる）。 ▼ ---
    let archiveCandidateIds = [];

    document.getElementById("orbit-archive-check-btn")?.addEventListener("click", () => {
        fetch("/orbit/archive/candidates")
            .then(res => res.json())
            .then(data => {
                if (data.status !== "success") {
                    window.showToast?.(data.message || "確認に失敗しました", "error");
                    return;
                }
                archiveCandidateIds = data.rows.map(r => r.order_item_id);
                const summary = document.getElementById("orbit-archive-summary");
                if (summary) {
                    summary.textContent = archiveCandidateIds.length
                        ? `アーカイブ対象: ${archiveCandidateIds.length}件（出荷完了＋決済確定済み）`
                        : "アーカイブ対象はありません";
                }
            })
            .catch(err => {
                console.error("orbit/archive/candidates error:", err);
                window.showToast?.("確認に失敗しました", "error");
            });
    });

    document.getElementById("orbit-archive-run-btn")?.addEventListener("click", () => {
        if (!archiveCandidateIds.length) {
            window.showToast?.("先に「アーカイブ対象を確認」を押してください", "error");
            return;
        }
        if (!confirm(`${archiveCandidateIds.length}件を買い手購入履歴へアーカイブします。よろしいですか？`)) return;

        fetch("/orbit/archive/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_ids: archiveCandidateIds }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.(`${data.archived}件アーカイブしました`, "success");
                    archiveCandidateIds = [];
                    const summary = document.getElementById("orbit-archive-summary");
                    if (summary) summary.textContent = "";
                    loadOrders();
                    loadBuyerHistory();
                } else {
                    window.showToast?.(data.message || "アーカイブに失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/archive/run error:", err);
                window.showToast?.("アーカイブに失敗しました", "error");
            });
    });

    // --- ▼ SECTION 01-3c: 返品・セキュリティメモの追加（発注管理タブ。アーカイブ後の注文でも追加可能） ▼ ---
    dispatchTbody?.addEventListener("click", (e) => {
        const btn = e.target.closest(".orbit-security-note-btn");
        if (!btn) return;

        const orderItemId = btn.dataset.orderItemId;
        if (!orderItemId) return;

        const note = prompt("返品・キャンセル理由等のメモを入力してください（この買い手の住所に記録されます）");
        if (!note || !note.trim()) return;

        fetch("/orbit/security_notes/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order_item_id: orderItemId, note: note.trim() }),
        })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    window.showToast?.("メモを追加しました", "success");
                    loadOrders();
                    loadSecurityNotes();
                } else {
                    window.showToast?.(data.message || "追加に失敗しました", "error");
                }
            })
            .catch(err => {
                console.error("orbit/security_notes/add error:", err);
                window.showToast?.("追加に失敗しました", "error");
            });
    });

    // --- ▼ SECTION 02: 発送代行への出力 ▼ ---
    document.getElementById("orbit-export-btn")?.addEventListener("click", () => {
        window.location.href = "/orbit/export";
    });

    // --- ▼ SECTION 02-1b: Google連携状態の表示（連携/再連携ボタンは常に表示） ▼ ---
    const googleConnectLink = document.getElementById("orbit-google-connect-link");
    const googleConnectStatus = document.getElementById("orbit-google-connect-status");

    fetch("/orbit/google_oauth/status")
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") return;
            // 連携済みでも「Google再連携」として常に出す（スコープ変更・トークン失効時に押せる導線が必要なため）
            if (googleConnectLink) {
                googleConnectLink.textContent = data.connected ? "Google再連携" : "Googleアカウントを連携する";
                googleConnectLink.style.display = "inline-block";
            }
            if (googleConnectStatus) googleConnectStatus.textContent = data.connected ? "Google連携済み" : "未連携";
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
    attachSaveHandlers(tbody, { onSaved: loadOrders, getOrderedIds: getOrdersOrderedIds });
    if (procTbody) attachSaveHandlers(procTbody, { onSaved: loadOrders });
    if (dispatchTbody) attachSaveHandlers(dispatchTbody, { onSaved: loadOrders });

    // --- ▼ 受注一覧: 行ごとの上下移動 ▼ ---
    tbody.addEventListener("click", (e) => {
        const upBtn = e.target.closest(".orbit-move-up-btn");
        const downBtn = e.target.closest(".orbit-move-down-btn");
        const btn = upBtn || downBtn;
        if (!btn) return;

        moveOrderRow(btn.dataset.orderItemId, upBtn ? "up" : "down");
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

    // --- ▼ SECTION 04-2: ZSSS_RAWタブへの書き出し（手動コピペの置き換え） ▼ ---
    const rawSheetUrlInput = document.getElementById("orbit-raw-sheet-url");
    const rawSheetNameInput = document.getElementById("orbit-raw-sheet-name");
    const rawSheetSettingsSaveBtn = document.getElementById("orbit-raw-sheet-settings-save-btn");
    const rawPushBtn = document.getElementById("orbit-raw-push-btn");
    const rawPushStatus = document.getElementById("orbit-raw-push-status");

    fetch("/orbit/raw_sheet_settings")
        .then(res => res.json())
        .then(data => {
            if (data.status !== "success") return;
            if (rawSheetUrlInput) rawSheetUrlInput.value = data.spreadsheet_url || "";
            if (rawSheetNameInput) rawSheetNameInput.value = data.sheet_name || "";
        })
        .catch(err => console.error("raw_sheet_settings load error:", err));

    rawSheetSettingsSaveBtn?.addEventListener("click", () => {
        fetch("/orbit/raw_sheet_settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                spreadsheet_url: rawSheetUrlInput?.value || "",
                sheet_name: rawSheetNameInput?.value || "",
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
                console.error("raw_sheet_settings save error:", err);
                window.showToast?.("保存に失敗しました", "error");
            });
    });

    rawPushBtn?.addEventListener("click", () => {
        if (rawPushStatus) rawPushStatus.textContent = "書き込み中...";
        rawPushBtn.disabled = true;

        fetch("/orbit/raw_sheet_push", { method: "POST" })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    if (rawPushStatus) rawPushStatus.textContent = `${data.rows}行 × ${data.columns}列 を ${data.sheet_name} に書き込みました`;
                } else {
                    if (rawPushStatus) rawPushStatus.textContent = data.message || "書き込みに失敗しました";
                }
            })
            .catch(err => {
                console.error("raw_sheet_push error:", err);
                if (rawPushStatus) rawPushStatus.textContent = "書き込みに失敗しました";
            })
            .finally(() => { rawPushBtn.disabled = false; });
    });

    loadOrders();
    loadBuyerHistory();
    loadSecurityNotes();
};
