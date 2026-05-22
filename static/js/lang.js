// =====================================================
// ファイル名: static/js/lang.js
// 目的： 言語辞書
// =====================================================

// --- ▼ SECTION 01: 翻訳辞書 ▼ ---
window.LANG = {
    ja: {
        // --- Pricing 価格条件設定 ---
        // === 仕入先設定 ===

        // === 梱包設定 ===

        // === 競合設定 ===
        max_price_limit: "出品価格",
        max_price_stop: "以上の場合は出品しない",      
        competitor_ratio: "競合より",
        competitor_ratio_stop: "%以上高い場合は出品しない",  
        discount_from: "競合価格から",
        discount_label: "安く出品",  

        // === 価格改定設定 ===

    },

    en: {

        // --- Pricing Setting ---
        // === 仕入先設定 ===

        // === 梱包設定 ===

        // === 競合設定 ===
        max_price_limit: "Listing price",
        max_price_stop: "Do not list above",
        competitor_ratio: "Compared to competitor",
        competitor_ratio_stop: "% higher → do not list",
        discount_from: "Below competitor price",
        discount_label: "discount",

        //Listing Price Calculation Settings

    }

};
// --- ▼ SECTION 02: 切替え ▼ ---
window.applyLang = function(lang){

    document.querySelectorAll("[data-i18n]").forEach(el => {

        const key = el.dataset.i18n

        if (LANG[lang] && LANG[lang][key]) {
            el.textContent = LANG[lang][key]
        }

    })

}

document.addEventListener("DOMContentLoaded", function(){

    const savedLang = localStorage.getItem("lang") || "ja"
    applyLang(savedLang)

    const langSelect = document.getElementById("lang_switch")

    if (langSelect){

        langSelect.value = savedLang

        langSelect.addEventListener("change", function(){

            const lang = this.value
            localStorage.setItem("lang", lang)
            applyLang(lang)

        })
    }

})







