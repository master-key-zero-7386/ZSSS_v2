// =====================================================
// ファイル名: static/account.js
// 目的：アカウントに関する内容
// =====================================================
document.addEventListener("DOMContentLoaded", async () => {

    // --- ▼ OAuth結果受信処理（最優先） ▼ ---
    const oauthRes = await fetch("/amazon/oauth/result");
    const oauthData = await oauthRes.json();

    if (oauthData && oauthData.status === "ok") {
        if (oauthData.app_type === "home") {
            const homeToken = document.getElementById("home_refresh_token");
            if (homeToken) homeToken.value = oauthData.refresh_token;
        }

        if (oauthData.app_type === "region") {
            const regionToken = document.getElementById("region_refresh_token");
            if (regionToken) regionToken.value = oauthData.refresh_token;
        }
    }

    // --- ▼ SECTION 01: HOMEプルダウン生成：serverからregion一覧を取得して作る ▼ ---
    const homeCountryCodeEl = document.getElementById("homeCountryCode");

    let initialAccountLoad = true;
    let isRegionEditing = false; 
    let isHomeEditing   = false;
    let suppressHomeChange = false;

    async function loadHomeAccount() {
        initialAccountLoad = false;

        try {
            const res = await fetch("/account/get_home_account");
            const data = await res.json();
            const sellerEl = document.getElementById("home_seller_id");
            const tokenEl  = document.getElementById("home_refresh_token");

            sellerEl.value = data.account?.account_seller_id || "";
            tokenEl.value  = data.account?.refresh_token || "";

            // --- ▼ HOME確定時はDBの値を表示して完全ロック ▼ ---
            if (data.marketplace && data.marketplace.country_code && !isHomeEditing) {

                // プルダウンは表示専用に差し替え
                homeCountryCodeEl.value = data.marketplace.country_code;
                homeCountryCodeEl.disabled = true;   

                homeCountryCodeEl.setAttribute("data-current", data.marketplace.country_code);

                // ★ ここが今回の本命修正
                sellerEl.disabled = true;
                tokenEl.disabled  = true;

                localStorage.removeItem("homeCountryCode");

                // ★ HOME 読み込み後に REGION も必ず同期する
                const countryCode = document.getElementById("globalRegion")?.value;
                if (countryCode) {
                    await updateAccountFields(countryCode);
                }

            } else {
                // HOME未確定時のみ編集可能
                homeCountryCodeEl.disabled = false;
                sellerEl.disabled = false;
                tokenEl.disabled  = false;
            }

        } catch (err) {
            console.error("[ACCOUNT] HOME info load failed:", err);
        }
    }

    fetch("/account/get_marketplaces_master")
        .then(res => res.json())
        .then(data => {
            if (!Array.isArray(data.regions)) return;

            homeCountryCodeEl.innerHTML = "";

            // --- ▼ 未選択 option を必ず先頭に入れる（重要） ---
            const emptyOpt = document.createElement("option");
            emptyOpt.value = "";
            emptyOpt.textContent = "— HOMEを選択 —";
            homeCountryCodeEl.appendChild(emptyOpt);

            data.regions.forEach(r => {
                const opt = document.createElement("option");
                opt.value = r.country_code;            // "JP"
                opt.textContent = r.display_name; // "Japan"
                homeCountryCodeEl.appendChild(opt);
            });

            // 明示的に未選択状態にする
            homeCountryCodeEl.value = "";

            // ★ DOM反映後に HOME確定状態を判定させる（重要）
            setTimeout(() => {
                loadHomeAccount();
            }, 0);            
        });

    // --- ▼ SECTION 02: HOME変更時（警告 → OKなら削除 → HOME再設定）▼ ---
    homeCountryCodeEl.addEventListener("change", async () => {

        if (suppressHomeChange) return; 

        const previousValue = homeCountryCodeEl.getAttribute("data-current");
        const newHome = homeCountryCodeEl.value;

        if (!newHome) return;

        // ▼ 現在HOMEが存在するか確認
        let hasHome = false;
        try {
            const res = await fetch("/account/get_home_account");
            const data = await res.json();
            hasHome = !!(data.account && Object.keys(data.account).length > 0);
        } catch (e) {
            console.error("HOME確認失敗:", e);
        }

        // ▼ HOMEが存在する場合だけ confirm を出す
        if (hasHome) {
            const ok = confirm("HOMEの設定内容が削除されます。\nよろしいですか？");
            if (!ok) {
                // ★ ここが重要：元に戻す
                suppressHomeChange = true;
                homeCountryCodeEl.value = homeCountryCodeEl.getAttribute("data-current");
                suppressHomeChange = false;
                return;
            }
        }

        // ▼ HOME UIを空にする
        document.getElementById("home_seller_id").value = "";
        document.getElementById("home_refresh_token").value = "";

        // ▼ 旧HOME削除API
        await fetch("/account/delete_home_account", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });

        // ▼ 再読み込み
        loadHomeAccount();
    });
    // --- ▼ SECTION 03: アカウント基本情報 保存（HOME / Region） ▼ ---
    const saveAccountBtn = document.getElementById("saveAccountBtn");
    if (saveAccountBtn) {
        saveAccountBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!e.isTrusted) return;

            // ▼ HOME と Region が同じ場合は保存禁止
            const newHome = (document.getElementById("homeCountryCode")?.value || "").toUpperCase();
            const countryCode = (document.getElementById("globalRegion")?.value || "").toUpperCase();

            if (newHome === countryCode) {
                if (window.showToast) {
                    window.showToast("HOME と Region が同じ国の保存利用はできません。", "error");
                }
                return;
            }

            // ▼ フィールド取得
            const homeSeller   = document.getElementById("home_seller_id")?.value || "";
            const homeToken    = document.getElementById("home_refresh_token")?.value || "";
            const regionSeller = document.getElementById("region_seller_id")?.value || "";
            const regionToken  = document.getElementById("region_refresh_token")?.value || "";

            // ▼ 保存結果フラグ
            let saveOk = false;

            // =====================================================
            // ① 保存処理（ここだけが「致命的エラー」対象）
            // =====================================================
            try {
                // HOME 保存
                const homeRes = await fetch("/account/save_account_master", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        country_code: newHome,
                        account_seller_id: homeSeller,
                        refresh_token: homeToken,
                        home_flag: 1
                    })
                });
                const homeJson = await homeRes.json();

                // REGION 保存
                const regionRes = await fetch("/account/save_account_master", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        country_code: countryCode,
                        account_seller_id: regionSeller,
                        refresh_token: regionToken,
                        home_flag: 0
                    })
                });
                const regionJson = await regionRes.json();

                saveOk =
                    (homeJson?.status === "ok" || homeJson?.status === "success") &&
                    (regionJson?.status === "ok" || regionJson?.status === "success");

                if (!saveOk) {
                    throw new Error("save response not ok");
                }

            } catch (err) {
                if (window.showToast) {
                    window.showToast("アカウント基本情報の保存に失敗しました", "error");
                }
                return; // ← 保存失敗時はここで終了
            }

            // ▼ 保存成功トースト
            if (window.showToast) {
                window.showToast("アカウント基本情報を保存しました", "success");
            }

            // =====================================================
            // ② 保存後の再読込（軽微エラー扱い）
            // =====================================================
            try {
                loadHomeAccount();
            } catch (e) {
                if (window.showToast) {
                    window.showToast("保存後の HOME 情報再取得に失敗しました", "warning");
                }
            }

            try {
                if (countryCode) {
                    loadRegionAccount(countryCode);
                }
            } catch (e) {
                // 何もしない
            }

            // --- ▼ HOME確定後はプルダウンをロック ▼ ---
            const homeCountryCodeEl = document.getElementById("homeCountryCode");
            if (homeCountryCodeEl) {
                homeCountryCodeEl.disabled = true;   // a_marketplaces.db の表示に切替後、変更不可
            }
        });
    }
    
    // --- ▼ SECTION 04: HOME / Region 連携／リセットボタン処理 ▼ ---
    window.resetAccount = function (countryCode) {

        let tokenEl = null;
        let linkBtn = null;
        let marketplace = null;
        let homeRegionEl = null;

        if (countryCode === "HOME") {
            tokenEl = document.getElementById("home_refresh_token");
            linkBtn = document.getElementById("home_link_btn");
            homeRegionEl = document.getElementById("homeCountryCode");
            marketplace = homeRegionEl?.value;
        } else {
            tokenEl = document.getElementById("region_refresh_token");
            linkBtn = document.getElementById("region_link_btn");
            marketplace = document.getElementById("globalRegion")?.value;
        }

        if (!tokenEl || !linkBtn) return;

        // ==== ▼ 連携（Amazon OAuth 開始）===
        if (!tokenEl.value) {
            if (!marketplace) return;

            window.location.href =
                `/amazon/oauth/start?marketplace=${encodeURIComponent(marketplace)}&app_type=${countryCode === "HOME" ? "home" : "region"}`;
            return;
        }

        // === ▼ リセット（UIのみ） ===
        tokenEl.value = "";
        linkBtn.textContent = "連　携";

        if (countryCode === "HOME") { // （HOME用）

            const homeSellerEl = document.getElementById("home_seller_id");
            const homeTokenEl  = document.getElementById("home_refresh_token");
            const cancelBtn    = document.getElementById("home_cancel_btn");

            if (homeSellerEl) homeSellerEl.disabled = false; 
            if (homeTokenEl)  homeTokenEl.disabled  = false;   
            if (homeRegionEl) homeRegionEl.disabled = false;
            

            linkBtn.disabled = false;  
            
            if (cancelBtn) cancelBtn.style.display = "inline-block";
        }

        if (countryCode !== "HOME") { // （region用）
            const sellerEl = document.getElementById("region_seller_id");
            const tokenEl  = document.getElementById("region_refresh_token");
            const cancelBtn = document.getElementById("region_cancel_btn");
            const linkBtn   = document.getElementById("region_link_btn");

            // 編集可能に戻す
            if (sellerEl) sellerEl.disabled = false;
            if (tokenEl)  tokenEl.disabled  = false;

            // ★ キャンセル表示
            if (cancelBtn) cancelBtn.style.display = "inline-block";

            // ★ ボタン文言を「連携」に
            if (linkBtn) linkBtn.textContent = "連　携";
        }

        // // === ▼ HOME の場合はプルダウンを未確定状態に戻す ===
        // if (countryCode === "HOME" && homeRegionEl) {

        //     homeSnapshot = {
        //         country_code: homeRegionEl.value || "",
        //         display_name: homeRegionEl.options[homeRegionEl.selectedIndex]?.textContent || ""
        //     };
        //     isHomeEditing = true;

        //     suppressHomeChange = true;

        //     const cancelBtn = document.getElementById("home_cancel_btn");
        //     if (cancelBtn) cancelBtn.style.display = "inline-block";

        //     homeRegionEl.disabled = false;
        //     homeRegionEl.innerHTML = "";

        //     const emptyOpt = document.createElement("option");
        //     emptyOpt.value = "";
        //     emptyOpt.textContent = "— HOMEを選択 —";
        //     homeRegionEl.appendChild(emptyOpt);        

        //     fetch("/account/get_marketplaces_master")
        //         .then(res => res.json())
        //         .then(data => {
        //             if (!Array.isArray(data.regions)) return;

        //             data.regions.forEach(r => {
        //                 const opt = document.createElement("option");
        //                 opt.value = r.country_code;
        //                 opt.textContent = r.display_name;
        //                 homeRegionEl.appendChild(opt);
        //             });
        //         })
        //         .finally(() => {
        //         homeRegionEl.value = "";
        //         suppressHomeChange = false;
        //         });

        //     localStorage.removeItem("homeCountryCode");
        // }

        if (window.showToast) {
            if (countryCode === "HOME") {
                window.showToast("HOMEの設定をリセットしました（未保存）", "info");
            } else {
                window.showToast(`${countryCode} のRefresh Tokenをリセットしました（未保存）`, "info");
            }
        }
    }; // # --- ▼ SECTION 04の終わり

    // --- ▼ SECTION 05: HOME 編集キャンセル ▼ ---
    window.cancelHomeEdit = function () {

        const sellerEl  = document.getElementById("home_seller_id");
        const tokenEl   = document.getElementById("home_refresh_token");
        const cancelBtn = document.getElementById("home_cancel_btn");
        const linkBtn   = document.getElementById("home_link_btn");

        // ▼ DB状態に戻す
        loadHomeAccount();

        // ▼ UIロック
        if (sellerEl) sellerEl.disabled = true;
        if (tokenEl)  tokenEl.disabled  = true;

        // ▼ ボタン状態復元
        if (linkBtn)   linkBtn.textContent = "リセット";
        if (cancelBtn) cancelBtn.style.display = "none";
    };

    // // --- ▼ SECTION 05: ▼ HOME設定変更キャンセル（UIのみ） ▼ ---
    // window.cancelHomeEdit = function () {
    //     if (!isHomeEditing || !homeSnapshot) return;

    //     const homeCountryCodeEl = document.getElementById("homeCountryCode");
    //     if (!homeCountryCodeEl) return;

    //     suppressHomeChange = true;

    //     // 元の HOME 表示に戻す
    //     homeCountryCodeEl.innerHTML = "";

    //     const opt = document.createElement("option");
    //     opt.value = homeSnapshot.country_code;
    //     opt.textContent = homeSnapshot.display_name;
    //     homeCountryCodeEl.appendChild(opt);

    //     homeCountryCodeEl.value = homeSnapshot.country_code;
    //     homeCountryCodeEl.disabled = true;

    //     suppressHomeChange = false;

    //     // 編集状態解除
    //     isHomeEditing = false;
    //     homeSnapshot = null;

    //     if (window.showToast) {
    //         window.showToast("HOME の変更をキャンセルしました", "info");
    //     }
    // };

    // // --- ▼ SECTION 06: HOME 編集キャンセル（完全復元） ▼ ===
    // window.cancelHomeEdit = function () {

    //     if (!isHomeEditing || !homeSnapshot) return;

    //     const homeCountryCodeEl = document.getElementById("homeCountryCode");
    //     const cancelBtn   = document.getElementById("home_cancel_btn");
    //     const linkBtn     = document.getElementById("home_link_btn");

    //     // --- ▼ change イベント誤爆防止 ---
    //     suppressHomeChange = true;

    //     // --- ▼ プルダウン復元 ---
    //     homeCountryCodeEl.innerHTML = "";

    //     const opt = document.createElement("option");
    //     opt.value = homeSnapshot.country_code;
    //     opt.textContent = homeSnapshot.display_name;
    //     homeCountryCodeEl.appendChild(opt);

    //     homeCountryCodeEl.value = homeSnapshot.country_code;
    //     homeCountryCodeEl.disabled = true;

    //     // --- ▼ Refresh Token は再取得（DBの状態に戻す） ---
    //     loadHomeAccount();

    //     // --- ▼ ボタン状態復元 ---
    //     if (linkBtn) linkBtn.textContent = "リセット";
    //     if (cancelBtn) cancelBtn.style.display = "none";

    //     // --- ▼ 編集状態解除 ---
    //     isHomeEditing = false;
    //     homeSnapshot = null;

    //     suppressHomeChange = false;
    // };

    // --- ▼ SECTION 06: REGION 編集キャンセル（UIのみ） ▼ ---
    window.cancelRegionEdit = function () {

        const sellerEl = document.getElementById("region_seller_id");
        const tokenEl  = document.getElementById("region_refresh_token");
        const cancelBtn = document.getElementById("region_cancel_btn");
        const linkBtn   = document.getElementById("region_link_btn");

        // ▼ 現在の REGION を取得
        const regionCode =
            (document.getElementById("globalRegion")?.value || "").toUpperCase();

        // ▼ DB 状態に戻す
        if (regionCode) {
            document.dispatchEvent(
                new CustomEvent("zsss:regionChanged", {
                    detail: { country_code: regionCode }
                })
            );
        }

        // ▼ UI をロック状態に戻す
        if (sellerEl) sellerEl.disabled = true;
        if (tokenEl)  tokenEl.disabled  = true;

        // ▼ ボタン状態復元
        if (linkBtn)   linkBtn.textContent = "リセット";
        if (cancelBtn) cancelBtn.style.display = "none";
    };

    // === ▼ 初期表示：現在選択中のリージョンを1回だけ反映 ▼ ===
    const initialCountryCode = document.getElementById("globalRegion")?.value;
    if (initialCountryCode) {
        document.dispatchEvent(
            new CustomEvent("zsss:regionChanged", {
                detail: { country_code: initialCountryCode }
            })
        );
    }

    // === ▼ zsss:regionChanged（account画面用）▼ ===
    document.addEventListener("zsss:regionChanged", async (e) => {
        const countryCode = e.detail.country_code;
        updateRegionLabels(countryCode);
        await updateMarketplaceView(countryCode);
        await updateAccountFields(countryCode);
    });

}); // "DOMContentLoaded" 終了括弧

// ▼ リフレッシュトークンの表示／非表示切替（Home / Region 共通）
window.toggleTokenVisibility = function (inputId) {
    const input = document.getElementById(inputId);
    if (!input) {
        console.warn("[ACCOUNT] toggleTokenVisibility target not found:", inputId);
        return;
    }

    input.type = (input.type === "password") ? "text" : "password";
};

// ▼ Marketplace Info（表示領域の切替）
async function updateMarketplaceView(countryCode) {

    if (!countryCode) {
        console.warn("[SKIP] updateMarketplaceView: countryCode is empty");
        return;
    }
    
    const code = (countryCode || "").toLowerCase(); 
    const match = window.marketplaceInfo?.[code];

    // Region 側ブロックの表示切替
    document.querySelectorAll(".region-detail[data-country_code]").forEach(el => {
        el.style.display = "none";
    });

    if (!match) {
        console.warn("[SKIP] marketplaceInfo not found:", code);
        return;
    }

    const target = document.querySelector(
        `.region-detail[data-country_code='${match.country_code.toLowerCase()}']`
    );
    if (target) {
        target.style.display = "block";
    }

    const regionDisplay   = document.getElementById("region_display_name");
    const regionMkt       = document.getElementById("region_marketplace_id");
    const regionHost      = document.getElementById("region_host");
    const regionSpapiHost = document.getElementById("region_spapi_host");

    if (regionDisplay)   regionDisplay.value   = match.display_name || "";
    if (regionMkt)       regionMkt.value       = match.marketplace_id || "";
    if (regionHost)      regionHost.value      = match.host || "";
    if (regionSpapiHost) regionSpapiHost.value = match.spapi_host || "";
}

// ▼ 選択リージョンの表示名を反映
function updateRegionLabels(countryCode) {
    if (!countryCode) {

        return;
    }

    if (!window.marketplaceInfo) {

        return;
    }

    const code  = countryCode.toLowerCase();
    const match = window.marketplaceInfo[code];

    if (!match) return;

    const titleEl = document.getElementById("country_code-title");

    if (!titleEl) return;

    titleEl.textContent = match.display_name || "";
    titleEl.dataset.country_code = match.country_code;

}

// ▼ リージョン別アカウント情報の再取得（サーバー返却のキー名に合わせた版）
// Marketplace 情報は updateMarketplaceView が担当するので、ここでは認証情報だけ扱う
async function updateAccountFields(countryCode) {
    try {
        const sellerEl = document.getElementById("region_seller_id");
        const tokenEl  = document.getElementById("region_refresh_token");

        const res = await fetch(`/account/get_account_master?region=${countryCode.toLowerCase()}`);

        // ★ 未登録国（404 等）なら必ずクリア＋編集可
        if (!res.ok) {
            if (sellerEl) {
                sellerEl.value = "";
                sellerEl.disabled = false;
            }
            if (tokenEl) {
                tokenEl.value = "";
                tokenEl.disabled = false;
            }
            return;
        }

        const data = await res.json();

        if (data.status !== "success") return;

        const acc = data.account || {};

        const seller       = acc.account_seller_id || "";
        const refreshToken = acc.refresh_token     || "";

        if (sellerEl) sellerEl.value = seller;
        if (tokenEl)  tokenEl.value  = refreshToken;

        // ★ 連携済みならロック、未連携なら編集可
        const locked = !!refreshToken;
        if (sellerEl) sellerEl.disabled = locked;
        if (tokenEl)  tokenEl.disabled  = locked;

    } catch (err) {
        console.error("[ACCOUNT] updateAccountFields error:", err);
    }
}







