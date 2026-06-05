// =====================================================
// ファイル名: static/js/index.js
// 目的:Listing全体のエントリーポイント
// =====================================================

import { loadprelisting } from "./listing_pre.js";
import { showToast } from "./listing_common.js";
import { loadalllisting } from "./listing_all.js";

document.addEventListener("DOMContentLoaded", () => {

    // ✅ サイドバーのクリックを監視
    document.querySelectorAll(".sidebar-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const target = btn.getAttribute("data-target");

            const country_code = (document.getElementById("globalRegion")?.value || "US").trim();

            if (target === "prelisting") {
                loadprelisting(country_code);
            } else if (target === "alllisting") {
                loadalllisting(country_code); 
            }
        });
    });
});



