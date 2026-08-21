// =====================================================
// ファイル名: static/main.js　
// 目的: ZSSS Web Tool 全体の共通UI・状態管理・タブ制御
// =====================================================


// --- ▼ SECTION 00: 現在Region取得 共通関数（ここを修正） ---
window.getCurrentRegion = function () {
    const el = document.getElementById("globalRegion"); 
    const val = el && el.value; 

    return val || localStorage.getItem("sellingRegion");
};

// --- ▼ SECTION 01: 旧仕様互換（未定義関数の安全退避） ▼ ---
window.loadprelisting = window.loadprelisting || function() {};
window.loadalllisting = window.loadalllisting || function() {};


// --- ▼ SECTION 02: マーケットプレイス共有状態（全タブ共通） ▼ ---
window.marketplaceInfo = {};       
window.activeMarketplace = null;

// --- ▼ SECTION 03: 表示用ユーティリティ関数 ▼ ---
let dataDir = ""; // 現在は未使用（旧仕様の名残の可能性あり）
const fmtJPY = (v) => (v == null ? "-" : Math.round(v).toLocaleString("ja-JP")); // 日本円フォーマット
const fmtPrice = (v) => (v == null ? "-" : Number(v).toFixed(2)); // 価格フォーマット（小数2桁）

// --- ▼ SECTION 04: ボタン状態制御（現時点では未実装） ▼ ---
function updateStoreButtonState() {
}

// --- ▼ SECTION 05: URLパラメータ取得ユーティリティ ▼ ---
function getParam(name) {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get(name);
}

// --- ▼ SECTION 06: 現在選択中リージョン取得（全タブ共通） ▼ ---
window.getCurrentCountryCode = function () {
    const el = document.getElementById("globalRegion");
    // 未選択時は null を返す（USフォールバック禁止）
    return (el && el.value ? el.value.toUpperCase() : null);
};

// --- ▼ SECTION 07: ACCOUNT Region 表示同期（表示専用） ▼ ---
function syncAccountRegionTitle() {
    if (window.location.pathname.includes("/account")) return; 
    const regionTitleEl = document.getElementById("country_code-title");
    if (!regionTitleEl) return;
    if (!window.activeMarketplace) return;

    regionTitleEl.textContent =
        window.activeMarketplace.display_name || "";
}

// --- ▼ SECTION 08: selectedRegion の事前復元（state基盤） ▼ ---
const restoredRegion =
    localStorage.getItem("sellingRegion") || null;

// --- ▼ SECTION 09: enabled regions 読み込み ▼ ---
window.ZSSS_ENABLED_COUNTRY_CODES = JSON.parse(

    document.getElementById("enabled-country-codes")?.textContent || "[]" 
).map(r => r.toUpperCase());

// --- ▼ SECTION 10:  ▼ ---
window.addEventListener("DOMContentLoaded", () => {

    // ★ Amazon配下でない #account 直打ちは正規ルートへ戻す
    if (
        location.hash === "#account" &&
        !location.pathname.startsWith("/amazon")
    ) {
        location.replace("/amazon/#account");
        return;
    }

    // === ▼ SECTION 10-01 : 管理者判定・GlobalRegion 初期化 ▼ ===

    // 管理者タブ制御
    const isAdmin =
        window.ZSSS_IS_ADMIN === true ||
        window.ZSSS_IS_ADMIN === "true";

    if (!isAdmin) {
        const adminTab = document.querySelector("[data-tab='admin-marketplace']");
        if (adminTab) adminTab.style.display = "none";
    }

    // ページ種別判定（先に確定）
    const path = window.location.pathname;
    const isAccountPage = path.includes("/amazon/account");

    // グローバルリージョン生成
    const globalRegionEl = document.getElementById("globalRegion");
    if (globalRegionEl) {

        fetch("/amazon/get_marketplaces_master")
            .then(res => res.json())
            .then(markets => {

                if (!Array.isArray(markets)) {
                    console.error("[ERR] load marketplaces: unexpected response", markets);
                    window.showToast?.("マーケットプレイス一覧の取得に失敗しました。再読み込みしてください", "error");
                    return;
                }

                globalRegionEl.innerHTML = "";
                const enabled = window.ZSSS_ENABLED_COUNTRY_CODES || [];
                const enabledLower = enabled.map(r => r.toLowerCase());

                // 復元元（優先順）
                const restoredCountryCode =
                    localStorage.getItem("sellingCountryCode") || null;

                markets.forEach(m => {
                    const countryCodeLower = (m.country_code || "").toLowerCase();
                    const countryCodeUpper = (m.country_code || "").toUpperCase();

                    const isEnabled =
                        enabled.includes("ALL") || enabled.includes(countryCodeUpper);

                    const opt = document.createElement("option");
                    opt.value = countryCodeLower;
                    opt.textContent = m.display_name;

                    if (!isEnabled) {
                        opt.disabled = true;
                        opt.style.color = "#999";
                        opt.textContent += "（未契約）";
                    }

                    // 復元対象のみ選択
                    if (restoredCountryCode && restoredCountryCode === countryCodeLower) {
                        opt.selected = true;
                    }

                    globalRegionEl.appendChild(opt);
                    window.marketplaceInfo[countryCodeLower] = m;
                });

                // change は account 以外でのみ発火
                if (globalRegionEl.value) {
                    // ★ 常に activeMarketplace は確定させる
                    window.activeMarketplace =
                        window.marketplaceInfo[globalRegionEl.value];

                    console.log("SAVE COUNTRY", globalRegionEl.value); // チェック完了後削除    

                    // ★ 初期選択時も保存
                    localStorage.setItem(
                        "sellingCountryCode",
                        globalRegionEl.value
                    );    
                                        
                    syncAccountRegionTitle();

                    // ★ account 以外でのみイベント発火
                    if (!isAccountPage) {
                        document.dispatchEvent(
                            new CustomEvent("zsss:regionChanged", {
                                detail: { country_code: globalRegionEl.value }
                            })
                        );
                    }
                }

                // 手動変更
                globalRegionEl.addEventListener("change", (e) => {
                    const v = e.target.value;
                    window.activeMarketplace = window.marketplaceInfo[v];
                    localStorage.setItem("sellingCountryCode", v);

                    document.dispatchEvent(
                        new CustomEvent("zsss:regionChanged", { detail: { country_code: v } })
                    );
                });

            })
            .catch(err => {
                console.error("[ERR] load marketplaces:", err);
                window.showToast?.("マーケットプレイス一覧の取得に失敗しました。再読み込みしてください", "error");
            });
    }

    // === ▼ SECTION 10-02: グローバル初期化（account以外） ▼ ===   
    if (!isAccountPage) {

        const sellerEl = document.getElementById("seller_id");
        const manualSellerEl = document.getElementById("manual_seller_id");

        if (sellerEl) sellerEl.addEventListener("change", updateStoreButtonState);
        if (manualSellerEl) manualSellerEl.addEventListener("input", updateStoreButtonState);

        updateStoreButtonState();

        let activeTab = document.querySelector('.sidebar-btn.active')?.getAttribute('data-target');

        if (!activeTab) {
            activeTab = "prelisting";
            const preBtn = document.querySelector('.sidebar-btn[data-target="prelisting"]');
            if (preBtn) preBtn.classList.add("active");
        }

        const countryCodeRaw = document.getElementById("globalRegion")?.value;
        const countryCode = countryCodeRaw ? countryCodeRaw.toLowerCase() : null;
        
        if (globalRegionEl) {
            globalRegionEl.addEventListener("change", () => {
                updateOutputFolderDisplay(globalRegionEl.value);
            });
        }

        // ✅ 存在チェック付き関数（重複排除）
        function updateOutputFolderDisplay(countryCode) {
            if (!countryCode || !dataDir) return;
            const fullPath = dataDir + "\\" + countryCode.toLowerCase();
            const outEl = document.getElementById("output_folder");
            if (outEl) outEl.value = fullPath;
        }

        const tabs = document.querySelectorAll('.tab');
        const contents = document.querySelectorAll('.tab-content, .subtab-content');
        const targetTab = getParam("tab");
        const hasTabContent = contents.length > 0; 
        const activeTabElement = document.querySelector('.tab.active');
        const activeTabId = activeTabElement?.getAttribute('data-tab');

        if (activeTabId?.toLowerCase() === "pricing") {
            if (typeof populateRegionSelector === "function" && window.location.pathname.includes("/pricing")) {
                populateRegionSelector().then(() => loadShippingConfig());
            }
        }    

        if (activeTabId === "admin-marketplace" && typeof initMarketplaceMaster === "function") {
            initMarketplaceMaster();
        }        


        const btn = document.getElementById('openStoreBtn');

        if (btn) {
            } 

        // ▼ SECTION : その他ツール サブタブ切替（Brand Gate / 遠隔地郵便番号管理）
        document.querySelectorAll(".st-subtab-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                // ★ 同じ .main-container（または .subtab-content）内のサブタブ同士だけを切替対象にする
                //   （その他ツール／管理者／Pricingなど、複数のサブタブ群が同じページに存在するため、
                //    documentクリック全体を対象にすると別グループのactive状態まで消してしまう）
                const scope = btn.closest(".main-container, .subtab-content") || document;
                scope.querySelectorAll(".st-subtab-btn").forEach(b => b.classList.remove("active"));
                scope.querySelectorAll(".st-subtab-pane").forEach(p => p.classList.remove("active"));
                btn.classList.add("active");
                const pane = document.getElementById(btn.getAttribute("data-target"));
                if (!pane) return;
                pane.classList.add("active");

                // ★ DataTablesは非表示コンテナ内で初期化されると列幅が崩れるため、
                //   サブタブ表示時に再計算させる（destroy/再初期化はしない安全な方法）
                if (window.jQuery && window.jQuery.fn && window.jQuery.fn.DataTable) {
                    pane.querySelectorAll("table").forEach(tableEl => {
                        if (window.jQuery.fn.DataTable.isDataTable(tableEl)) {
                            window.jQuery(tableEl).DataTable().columns.adjust().draw(false);
                        }
                    });
                }
            });
        });

        // ▼ SECTION : 遠隔地郵便番号管理
        async function raRefreshCountryList() {
            const datalist = document.getElementById("raCountryList");
            if (!datalist) return;

            const codes = new Set();
            for (const carrier of ["DHL", "FEDEX"]) {
                try {
                    const resp = await fetch(`/tools/remote_area/countries?carrier=${carrier}`);
                    if (!resp.ok) continue;
                    const result = await resp.json();
                    (result.countries || []).forEach(c => codes.add(c.country_code));
                } catch (e) {
                    console.error("remote_area countries error:", e);
                }
            }

            datalist.innerHTML = "";
            [...codes].sort().forEach(code => {
                const opt = document.createElement("option");
                opt.value = code;
                datalist.appendChild(opt);
            });
        }

        async function raImport() {
            const carrier = document.getElementById("raImportCarrier")?.value;
            const country = (document.getElementById("raImportCountry")?.value || "").trim().toUpperCase();
            const text = document.getElementById("raImportText")?.value || "";
            const statusEl = document.getElementById("raImportStatus");
            if (!statusEl) return;

            if (!country) {
                statusEl.textContent = "国コードを入力してください。";
                statusEl.style.color = "red";
                return;
            }

            try {
                const resp = await fetch("/tools/remote_area/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ carrier, country_code: country, text })
                });
                const result = await resp.json();

                if (!resp.ok) {
                    statusEl.textContent = result.message || result.error || "取り込みに失敗しました。";
                    statusEl.style.color = "red";
                    return;
                }

                statusEl.textContent = `${carrier} / ${country}：${result.imported}件を取り込みました（${result.imported_at}）`;
                statusEl.style.color = "green";
                raRefreshCountryList();
            } catch (e) {
                console.error("remote_area import error:", e);
                statusEl.textContent = "取り込みに失敗しました。";
                statusEl.style.color = "red";
            }
        }

        function raImportClear() {
            const country = document.getElementById("raImportCountry");
            const text = document.getElementById("raImportText");
            const statusEl = document.getElementById("raImportStatus");
            if (country) country.value = "";
            if (text) text.value = "";
            if (statusEl) statusEl.textContent = "";
        }

        async function raLoadCountryTable() {
            const carrier = document.getElementById("raResetCarrier")?.value;
            const tbody = document.querySelector("#raCountryTable tbody");
            if (!tbody) return;

            tbody.innerHTML = "";

            try {
                const resp = await fetch(`/tools/remote_area/countries?carrier=${carrier}`);
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const result = await resp.json();

                (result.countries || []).forEach(c => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${c.country_code}</td>
                        <td>${c.row_count.toLocaleString()}</td>
                        <td>${c.imported_at || ""}</td>
                        <td><button class="btn-blue ra-reset-btn" data-country="${c.country_code}">リセット</button></td>
                    `;
                    tbody.appendChild(tr);
                });

                tbody.querySelectorAll(".ra-reset-btn").forEach(btn => {
                    btn.addEventListener("click", async () => {
                        const country = btn.getAttribute("data-country");
                        if (!confirm(`${carrier} / ${country} のデータを削除します。よろしいですか？`)) return;

                        const resp = await fetch("/tools/remote_area/reset", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ carrier, country_code: country })
                        });
                        if (!resp.ok) {
                            alert("リセットに失敗しました。");
                            return;
                        }
                        raLoadCountryTable();
                        raRefreshCountryList();
                    });
                });
            } catch (e) {
                console.error("remote_area countries error:", e);
            }
        }

        async function raCheckPostal() {
            const country = (document.getElementById("raCheckCountry")?.value || "").trim().toUpperCase();
            const postal = (document.getElementById("raCheckPostal")?.value || "").trim();
            const resultEl = document.getElementById("raCheckResult");
            if (!resultEl) return;

            if (!country || !postal) {
                resultEl.textContent = "国コードと郵便番号を入力してください。";
                return;
            }

            try {
                const resp = await fetch("/tools/remote_area/check", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ country_code: country, postal_code: postal })
                });
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const result = await resp.json();

                const rows = ["DHL", "FEDEX"].map(carrier => {
                    const r = result[carrier];
                    if (!r) return "";
                    const cls = r.remote ? "status-block" : "status-open";
                    const label = r.remote ? "遠隔地（該当あり）" : "対象外";
                    const range = r.matched_range ? `（${r.matched_range.postal_from} - ${r.matched_range.postal_to}）` : "";
                    return `<div><b>${carrier}</b>: <span class="${cls}">${label}</span> ${range}</div>`;
                });

                resultEl.innerHTML = rows.join("");
            } catch (e) {
                console.error("remote_area check error:", e);
                resultEl.textContent = "判定に失敗しました。";
            }
        }

        async function raExportCsv() {
            const carrier = document.getElementById("raExportCarrier")?.value;
            const country = (document.getElementById("raExportCountry")?.value || "").trim().toUpperCase();
            if (!country) {
                alert("国コードを入力してください。");
                return;
            }

            try {
                const resp = await fetch(`/tools/remote_area/export?carrier=${carrier}&country_code=${country}`);
                if (!resp.ok) throw new Error("HTTP " + resp.status);

                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `${carrier}_${country}_remote_area.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
            } catch (e) {
                console.error("remote_area export error:", e);
                alert("CSVのダウンロードに失敗しました。");
            }
        }

        document.getElementById("raImportBtn")?.addEventListener("click", raImport);
        document.getElementById("raImportClearBtn")?.addEventListener("click", raImportClear);
        document.getElementById("raResetLoadBtn")?.addEventListener("click", raLoadCountryTable);
        document.getElementById("raCheckBtn")?.addEventListener("click", raCheckPostal);
        document.getElementById("raExportBtn")?.addEventListener("click", raExportCsv);

        if (document.getElementById("st-remotearea")) {
            raRefreshCountryList();
        }

        // ▼ SECTION : 上部タブ切替（唯一の正規ルート）
        let accountInitialized = false;

        function showView(tabName) {
            const tabs = document.querySelectorAll('.tab');
            const contents = document.querySelectorAll('.tab-content, .subtab-content');

            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));

            const activeTab = document.querySelector(`[data-tab="${tabName}"]`);
            const activeContent = document.getElementById(tabName);

            if (activeTab) activeTab.classList.add('active');
            if (activeContent) activeContent.classList.add('active');

            if (typeof window.updateScrollButtons === "function") {
                window.updateScrollButtons();
            }

            // ★ account 表示時：Region Country ＋ SELLING 情報を同期
            if (tabName === "account") {
                const region = document.getElementById("globalRegion")?.value;
                if (!region) return;

                fetch(`/account/get_account_master?region=${encodeURIComponent(region)}`)
                    .then(async res => {
                        const sellerEl = document.getElementById("region_seller_id");
                        const tokenEl  = document.getElementById("region_refresh_token");

                        // ★ 未登録国（404等）の場合は必ずリセット＋編集可
                        if (!res.ok) {
                            if (sellerEl) {
                                sellerEl.value = "";
                                sellerEl.disabled = false;
                            }
                            if (tokenEl) {
                                tokenEl.value = "";
                                tokenEl.disabled = false;
                            }
                            return null;
                        }

                        return res.json();
                    })
                    .then(data => {
                        if (!data || data.status !== "success") return;

                        const sellerEl = document.getElementById("region_seller_id");
                        const tokenEl  = document.getElementById("region_refresh_token");

                        const seller = data.account?.account_seller_id || "";
                        const token  = data.account?.refresh_token || "";

                        if (sellerEl) sellerEl.value = seller;
                        if (tokenEl)  tokenEl.value  = token;

                        // ★ 連携済みならロック、未連携なら編集可
                        if (sellerEl && tokenEl) {
                            const locked = !!token;
                            sellerEl.disabled = locked;
                            tokenEl.disabled  = locked;
                        }
                    });
            }

            if (tabName === "admin-marketplace" && typeof initMarketplaceMaster === "function") {
                initMarketplaceMaster();
            }

            if (tabName === "orbit" && typeof window.initOrbit === "function") {
                window.initOrbit();
            }

        }

        if (!location.hash) {
            showView("top");
        } else {
            showView(location.hash.replace("#",""));
        }            

        window.scrollTo({ top: 0, left: 0, behavior: "instant" });

        // タブクリック時：hash と表示を同期
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                if (!tab.hasAttribute("data-tab")) return;  

                const tabName = tab.getAttribute('data-tab');
                if (!tabName) return;

                location.hash = tabName;
                showView(tabName);
            });
        });
                    
    } else {
        //  （現時点では処理なし）
    }

    // === ▼ SECTION 10-03 : サイドバー切替・初期表示 ▼ ===
    function activateSidebar(targetId) {

            // if (window._activating) return;  // ここを追加
            // window._activating = true;

        document.querySelectorAll(".sidebar-btn").forEach(b => b.classList.remove("active"));
        const btn = document.querySelector(`.sidebar-btn[data-target="${targetId}"]`);
        if (btn) btn.classList.add("active");

        document.querySelectorAll(".subtab-content").forEach(pane => {
            pane.hidden = true;
            pane.classList.remove("active");
        });

        const targetPane = document.querySelector(
            `[id="${targetId}"], [id="${targetId.charAt(0).toUpperCase() + targetId.slice(1)}"]`
        );
 
        if (targetId === "top") {
            const all = document.getElementById("alllisting");
            const pre = document.getElementById("prelisting");

            if (all) all.classList.remove("active");
            if (pre) pre.classList.remove("active");

            return;
        }        

        if (!targetPane) {
            window._activating = false;
            return;
        }

        targetPane.hidden = false;
        targetPane.classList.add("active");

        const region = getCurrentRegion();  

        console.log("REGION IN ACTIVATE >>>", region);

        if (!region) {
            window._activating = false;
            return;
        }   
        
        if (targetId !== "alllisting") return;
        
        if (targetId === "alllisting" && typeof loadalllisting === "function") {
            const regionNow = getCurrentRegion();  // ←ここを追加
            loadalllisting(regionNow, document.querySelector('input[name="allInfoStatus"]:checked')?.value || 'all');  // ここを修正
        }

        if (targetId === "pricing" && typeof loadShippingConfigV2 === "function") {
            const pricingEl = document.getElementById("pricing");
            if (!pricingEl) return;

            const saveBtn = document.getElementById("savePricingBtn");
            const inputs = pricingEl.querySelectorAll("input, select, textarea");

            if (saveBtn) {
                saveBtn.disabled = true;
                inputs.forEach(el => {
                    el.addEventListener("input", () => {
                        saveBtn.disabled = false;
                    });
                });
                saveBtn.addEventListener("click", saveShippingConfigV2);
            }

            loadShippingConfigV2(region);
        }

        window._activating = false;
    }

    // --- ▼ SECTION 10-04: GlobalRegion変更時 再描画 ▼ ---
    document.getElementById("globalRegion")?.addEventListener("change", function () {

        localStorage.setItem("sellingRegion", this.value);

        const region = getCurrentRegion();

        // ALLはここでは絶対に再ロードしない

        if (document.getElementById("prelisting")?.classList.contains("active")) {
            loadprelisting(region, document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all');
        }

        if (document.getElementById("pricing")?.classList.contains("active")) {
            loadShippingConfigV2(region);
        }

    });


    // // --- ▼ SECTION 10-05: 初回ロード ▼ ---
    // document.addEventListener("DOMContentLoaded", function () {

    //     const region = getCurrentRegion();

    //     // ALLはここではロードしない

    //     if (document.getElementById("prelisting")?.classList.contains("active")) {
    //         loadprelisting(region, document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all');
    //     }

    // });


    // --- ▼ SECTION 10-06: タブ切替時 再読み込み ▼ ---
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener("shown.bs.tab", function () {

            const region = getCurrentRegion();

            if (document.getElementById("prelisting")?.classList.contains("active")) {
                loadprelisting(region, document.querySelector('input[name="preInfoStatus"]:checked')?.value || 'all');
            }

            if (document.getElementById("alllisting")?.classList.contains("active")) {
                loadalllisting(region); // ここを修正
            }

        });
    });

    // --- ▼ SECTION 10-07: サイドバークリック ---
    document.querySelectorAll(".sidebar-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetId = (btn.getAttribute("data-target") || "").toLowerCase();
            location.hash = targetId;
            activateSidebar(targetId);
        });
    });

    // 初期表示：hash 優先（#account 対応）
    (() => {

        if (window._initialized) return;   
        window._initialized = true;        

        const hashTab = location.hash?.replace("#", "");

        if (hashTab) {
            activateSidebar(hashTab);
            return;
        }

        const activeBtn = document.querySelector(".sidebar-btn.active");
        const targetId = activeBtn
            ? (activeBtn.getAttribute("data-target") || "").toLowerCase()
            : "prelisting";

        activateSidebar(targetId);
    })();


    // === ▼ SECTION 10-08: サイドバー折りたたみ制御 ▼ ===
    const collapseHandle = document.getElementById("sidebar-collapse");
    if (collapseHandle) {
        collapseHandle.addEventListener("click", () => {
            const sidebar = document.getElementById("sidebar");
            sidebar.classList.toggle("collapsed");
            const isCollapsed = sidebar.classList.contains("collapsed");

            // ＜ と ＞ を切替
            collapseHandle.textContent = isCollapsed ? "＞" : "＜";

            // サイドバーが固定表示(position:fixed)になったため、畳んだ時はメインパネル側の余白も詰める
            const topLayout = document.querySelector(".top-layout");
            if (topLayout) topLayout.classList.toggle("sidebar-collapsed", isCollapsed);
        });
    }

    // === ▼ SECTION 10-09: ログアウト処理 ▼ ===
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", async () => {
            await fetch("/auth/logout", { method: "POST" });
            window.location.href = "/auth/login";
        });
    }

    // === ▼ SECTION 10-10: 三本メニュー（将来のマニュアル導線専用・一時温存） ▼ === 
    (function initManualMenu() {

        const btn  = document.getElementById('menu-btn'); 
        const menu = document.getElementById('user-dropdown');

        if (!btn || !menu) return;

        // メニュー開閉
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.hidden = !menu.hidden;
            btn.setAttribute('aria-expanded', String(!menu.hidden));
        });

        // 画面クリックで閉じる
        document.addEventListener('click', () => {
            menu.hidden = true;
        });

        // メニュー内クリック処理（マニュアル専用）
        menu.addEventListener('click', (e) => {
            e.stopPropagation();
            const a = e.target.closest('.menuitem');
            if (!a) return;

            const act = a.dataset.action;

            if (act === 'open-manual') {
                // TODO: マニュアル公開後にURLを設定する
                // 例：
                // window.open("https://docs.zsss.example/manual", "_blank");
            }

            // ※ アカウント遷移・ログアウト用途では使用しない
            menu.hidden = true;
        });

        // ESCキーで閉じる
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                menu.hidden = true;
            }
        });

    })();

    // === ▼ SECTION 10-11: 共通UI：トースト通知 ▼ === 
    window.showToast = function (message, type = "info") {
        let container = document.getElementById("toast-container");
        if (!container) {
            container = document.createElement("div");
            container.id = "toast-container";
            container.style.position = "fixed";
            container.style.bottom = "20px";
            container.style.right = "20px";
            container.style.zIndex = "9999";
            document.body.appendChild(container);
        }

        const toast = document.createElement("div");
        toast.style.color = "#fff";
        toast.style.padding = "10px 16px";
        toast.style.borderRadius = "6px";
        toast.style.marginTop = "8px";
        toast.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";

        toast.style.transition = "opacity .3s ease";

        if (type === "success") toast.style.background = "#28a745";
        else if (type === "error") toast.style.background = "#dc3545";
        else if (type === "warning") toast.style.background = "#ffc107";
        else toast.style.background = "#333";

        toast.textContent = message;
        container.appendChild(toast);

        requestAnimationFrame(() => toast.style.opacity = "1");
        setTimeout(() => {
            toast.style.opacity = "0";
            setTimeout(() => toast.remove(), 300);
        }, 2500);
    };    

    // === ▼ SECTION 10-12: 共通UI：Scroll Top Button ↑ ▼ ===
    // タブ切替（.tab-content.active の付け替え）や絞り込みAJAX再描画では
    // ネイティブのscrollイベントが発火しないため、判定は都度アクティブなタブを
    // 再取得する関数にまとめ、tab切替後(showView)とDataTable再描画後(drawCallback)
    // からも呼べるようにする。
    const topBtn = document.getElementById("scrollTopBtn");
    const bottomBtn = document.getElementById("scrollBottomBtn");

    window.updateScrollButtons = function(){
        const scrollArea = document.querySelector(".tab-content.active");
        if (!topBtn || !bottomBtn || !scrollArea) return;

        topBtn.style.display = scrollArea.scrollTop > 50 ? "block" : "none";

        bottomBtn.style.display =
            scrollArea.scrollTop < scrollArea.scrollHeight - scrollArea.clientHeight - 50
                ? "block"
                : "none";
    };

    // scrollイベントはバブリングしないため、キャプチャフェーズでdocumentに
    // 仕掛けることで、現在アクティブなタブ内のスクロールを個別バインドなしで拾う
    document.addEventListener("scroll", window.updateScrollButtons, true);

    if (topBtn) {
        topBtn.onclick = () => document.querySelector(".tab-content.active")
            ?.scrollTo({top:0, behavior:"smooth"});
    }
    if (bottomBtn) {
        bottomBtn.onclick = () => {
            const scrollArea = document.querySelector(".tab-content.active");
            scrollArea?.scrollTo({top:scrollArea.scrollHeight, behavior:"smooth"});
        };
    }

    window.updateScrollButtons();
}); // window.addEventListener("DOMContentLoaded" の終了    
