// =====================================================
// ファイル名: static/account_api_settings.js
// 目的：API管理用
// =====================================================

document.addEventListener("DOMContentLoaded", () => {

    // --- ▼ SECTION 01: ▼ API取得設定 保存ボタン（明示操作のみ）▼ ---
    const saveApiSettingsBtn = document.getElementById("saveApiSettingsBtn");
    if (saveApiSettingsBtn) {
        saveApiSettingsBtn.addEventListener("click", async () => {

            // const ok = await showApiConfirmModal();
            const ok = await showConfirmModal();
            if (!ok) return;

            try {
                await saveApiSettings();
                showToast("API設定を保存しました。", "success");
            } catch (e) {
                showToast("API設定の保存に失敗しました。", "error");
            }
        });
    }

    // --- ▼ SECTION 02: API ttl取得設定 保存（2段目）▼ ---
    function getTtlValue(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        const v = parseFloat(el.value);
        return isNaN(v) ? null : v;
    }    

    async function saveApiSettings() {
        const country_code = document.getElementById("globalRegion")?.value;
        if (!country_code) return;

        const payload = {
            country_code: country_code,
            enable_home_catalog:   document.getElementById("enable_home_catalog")?.checked ? 1 : 0,
            enable_home_pricing:   document.getElementById("enable_home_pricing")?.checked ? 1 : 0,
            enable_region_catalog: document.getElementById("enable_region_catalog")?.checked ? 1 : 0,
            enable_region_pricing: document.getElementById("enable_region_pricing")?.checked ? 1 : 0,

            // --- TTL（日）
            h_catalog_ttl_days: getTtlValue("h_catalog_ttl_days"),
            h_pricing_ttl_days: getTtlValue("h_pricing_ttl_days"),
            r_catalog_ttl_days: getTtlValue("r_catalog_ttl_days"),
            r_pricing_ttl_days: getTtlValue("r_pricing_ttl_days"),
        };

        const res = await fetch("/account/save_api_settings", {   
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const json = await res.json();                            
        if (json.status !== "ok") {                               
            throw new Error(json.message || "save failed");       
        }
    }

    // --- ▼ SECTION 03: API取得設定 保存ボタン制御（確認ダイアログ）▼ ---
    document.getElementById("saveApiSettingsBtn")
        ?.addEventListener("click", async () => {

            const result = await showConfirmModal({
                contentHtml: `
                    <h3>API取得設定の保存</h3>

                    <p>API取得設定を保存します。</p>
                    <ul>
                        <li>ON にした項目は、定期的に Amazon API を実行します</li>
                        <li>API 実行にはクレジットが消費されます</li>
                        <li>OFF の項目は API 実行されません</li>
                    </ul>

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

            // ★ ここでだけ保存処理を実行
            await saveApiSettings();
        });


    // --- ▼ SECTION 04: API取得設定 ON/OFF 状態をUIに反映（チェックボックス同期）▼ ---
    function syncApiStatusFromCheckbox() {
        const ids = [
            "enable_home_catalog",
            "enable_home_pricing",
            "enable_region_catalog",
            "enable_region_pricing",
        ];

        ids.forEach(id => {
            const cb = document.getElementById(id);
            if (!cb) return;

            const statusEl = cb.closest(".api-setting-block")
                            .querySelector(".api-status");
            if (!statusEl) return;

            statusEl.classList.toggle("on", cb.checked);
            statusEl.classList.toggle("off", !cb.checked);
        });
    }

    // --- ▼ SECTION 05: API取得設定 初期読込 ▼ ---
    async function loadApiSettings(country_code) {
        if (!country_code) return;
        const res = await fetch(`/account/get_api_settings?country_code=${country_code}`);
        const json = await res.json();
        if (json.status !== "ok") return;

        const s = json.settings || {};

        const targets = [
            ["enable_home_catalog",   s.enable_home_catalog],
            ["enable_home_pricing",   s.enable_home_pricing],
            ["enable_region_catalog", s.enable_region_catalog],
            ["enable_region_pricing", s.enable_region_pricing],
        ];

        targets.forEach(([id, value]) => {
            const chk = document.getElementById(id);
            if (!chk) return;

            chk.checked = (value == 1);
        });

        // --- TTL をUIに反映
        const ttlTargets = [
            ["h_catalog_ttl_days", s.h_catalog_ttl_days],
            ["h_pricing_ttl_days", s.h_pricing_ttl_days],
            ["r_catalog_ttl_days", s.r_catalog_ttl_days],
            ["r_pricing_ttl_days", s.r_pricing_ttl_days],
        ];

        ttlTargets.forEach(([id, value]) => {
            const input = document.getElementById(id);
            if (!input) return;
            if (value !== null && value !== undefined) {
                input.value = value;
            }
        });
    }

    // --- ▼ SECTION 06: API取得設定：ON/OFF 表示制御（HOME / REGION 共通） ▼ ---
    function setupApiToggle(checkboxId) {

        const chk = document.getElementById(checkboxId);
        if (!chk) return;

        const block = chk.closest('.api-setting-block');
        if (!block) return;

        const status = block.querySelector('.api-status');
        if (!status) return;

        function updateStatus() {

            status.classList.remove('on', 'off'); 
            if (chk.checked) {
                status.classList.add('on');       
            } else {
                status.classList.add('off');      
            }
        }   


        chk.addEventListener('change', updateStatus);
        updateStatus(); // 初期表示
    }

    // 対象は「今ある4つのIDだけ」
    setupApiToggle('enable_home_catalog');
    setupApiToggle('enable_home_pricing');
    setupApiToggle('enable_region_catalog');
    setupApiToggle('enable_region_pricing');

    // --- ▼ SECTION 07: region変更時にAPI設定を再読込（API設定専用）▼ ---
    document.addEventListener("zsss:regionChanged", async (e) => {
        const newRegion = e.detail.country_code;
        await loadApiSettings(newRegion); 
        syncApiStatusFromCheckbox();  
    });

    // --- ▼ SECTION 08: 初回ロード時のAPI設定読込（イベント取り逃し対策）▼ ---
    const initialRegion = document.getElementById("globalRegion")?.value;
    if (initialRegion) {
        loadApiSettings(initialRegion);
        syncApiStatusFromCheckbox();
    }


}); // "DOMContentLoaded" 終了括弧




