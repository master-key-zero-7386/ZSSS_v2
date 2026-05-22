// ==========================================
// ファイル名: static/js/Pricing.js
// 目的: 仕入・出品条件設定
// ==========================================

// =============================================================
// グローバル定義（他ファイルからも呼び出し可能）
// =============================================================
window.populateRegionSelector = async function() {
  
  // ※ pricing.html 内の select は削除済み。上部の #globalRegion を使用。
  const globalRegion = document.getElementById("globalRegion");
  if (!globalRegion) {
    console.warn("[WARN] globalRegion not found.");
    return;
  }
};

// =============================================================
// DOMContentLoaded 内：Pricingページ専用初期化
// =============================================================
document.addEventListener("DOMContentLoaded", () => {
  const isPricingPage = document.getElementById("pricing") !== null;
  if (!isPricingPage) return;

  // # === ▼ SECTION 01: Shipping Config 読込処理（新・最小） ▼ ===
  window.loadShippingConfigV2 = function(region) {
    const currentRegion = "ALL";

    fetch(`/amazon/get_shipping_config?user_id=${ZSSS_USER_ID}&country_code=${currentRegion}&_=${Date.now()}`)

      .then(res => res.json())
      .then(data => {
        if (data.status !== "success" || !data.data) return;

        const cfg = data.data;
        const set = (id, val) => {
          const el = document.getElementById(id);
          if (el) el.value = val ?? "";
        };

        // 新仕様：3項目のみ
        set("pkg_padding_cm", cfg.padding_cm);
        set("pkg_weight_ratio", cfg.pack_ratio);
        set("pkg_volumetric_divisor", cfg.volumetric_divisor);
      })
      .catch(err => console.error("[ERR] loadShippingConfigV2:", err));
  };

  // # === ▼ SECTION 02: Shipping Config 保存（新・最小） ▼ ===
  window.saveShippingConfigV2 = async function() {
    const globalRegion = document.getElementById("globalRegion");
    const region = globalRegion?.value;
    // プルダウン未選択時は処理しない
    if (!region) return;

    const payload = {
      user_id: ZSSS_USER_ID,
      country_code: "ALL",
      padding_cm: parseFloat(document.getElementById("pkg_padding_cm")?.value || 0),
      pack_ratio: parseFloat(document.getElementById("pkg_weight_ratio")?.value || 0),
      volumetric_divisor: parseFloat(document.getElementById("pkg_volumetric_divisor")?.value || 5000),
    };

    const res = await fetch("/amazon/update_shipping_config", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const json = await res.json();
    if (json.status === "success") {
      loadShippingConfigV2(region);

      if (window.showToast) {
        window.showToast("梱包補正設定を保存しました", "success");
      }

    } else {
      console.error("[ERR] saveShippingConfigV2:", json.message);

      if (window.showToast) {
        window.showToast("保存に失敗しました", "error");
      }
    }
  };
 
  // ★ 最後に呼ぶ
  // loadShippingConfigV2();

  // --- ▼ SECTION 03: 仕入先条件 Offer Filter Rules 読込 ▼ ---
  window.loadOfferFilterRules = async function(region) {
    const globalRegion = document.getElementById("globalRegion");
    if (!globalRegion) {
      console.warn("[WARN] globalRegion not found yet, retrying after 100ms");
      setTimeout(() => window.loadOfferFilterRules(region), 100);
      return;
    }

    const currentRegion = "ALL";

    try {
      const res = await fetch(`/pricing/get_offer_filter_rules?user_id=${ZSSS_USER_ID}&country_code=${currentRegion}`);
      const json = await res.json();

      if (json.status !== "success" || !json.data) {
        console.warn("[WARN] offer_filter_rules load failed:", json);
        return;
      }

      const d = json.data;

      document.getElementById("min_rating_percent").value = d.min_rating_percent ?? "";
      document.getElementById("min_rating_count").value = d.min_rating_count ?? "";
      document.getElementById("max_handling_days").value = d.max_handling_days ?? "";
      document.getElementById("min_stock_qty").value = d.min_stock_qty ?? "";

      const setChecked = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.checked = !!val;
      };

      setChecked("exclude_non_home_ship", d.exclude_non_home_ship);
      setChecked("exclude_future_offer", d.exclude_future_offer);
      setChecked("consider_points", d.consider_points);
      setChecked("exclude_non_buybox", d.exclude_non_buybox);

    } catch (err) {
      console.error("[ERR] loadOfferFilterRules:", err);
    }
  };

  // --- ▼ SECTION 04: 仕入先設定 Offer Filter Rules 保存 ▼ ---
  window.updateOfferFilterRules = async function(region) {
    const payload = {
      user_id: ZSSS_USER_ID,
      country_code: "ALL",
      min_rating_percent: parseFloat(document.getElementById("min_rating_percent").value || 0),
      min_rating_count: parseInt(document.getElementById("min_rating_count").value || 0),
      max_handling_days: parseInt(document.getElementById("max_handling_days").value || 0),
      min_stock_qty: parseInt(document.getElementById("min_stock_qty").value || 0),
      exclude_non_home_ship: document.getElementById("exclude_non_home_ship").checked ? 1 : 0,
      exclude_future_offer: document.getElementById("exclude_future_offer").checked ? 1 : 0,
      consider_points: document.getElementById("consider_points").checked ? 1 : 0,
      exclude_non_buybox: document.getElementById("exclude_non_buybox")?.checked ? 1 : 0, 
    };

    try {
      const res = await fetch("/pricing/update_offer_filter_rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (data.status === "success") {
      } else {
        window.showToast("仕入先設定の更新に失敗：" + data.message, "error");
      }
    } catch (err) {
      console.error("[ERR] updateOfferFilterRules:", err);
      window.showToast("仕入先設定の更新中にエラーが発生", "error");
    }
  }

  // --- ▼ SECTION 05: 販売先条件 Pricing Master Rules 読込 ▼ ---
  window.loadPricingMasterRules = async function(countryCode) {

      if (!countryCode) return;

      try {
          const res = await fetch(`/pricing/get_pricing_master_rules?user_id=${ZSSS_USER_ID}&country_code=${countryCode}`);
          const json = await res.json();

          if (json.status !== "success" || !json.data) return;

          const d = json.data;

          document.getElementById("pricing_competitor_min_rating_percent").value = 
            d.pricing_competitor_min_rating_percent != null ? parseFloat(d.pricing_competitor_min_rating_percent).toFixed(2) : "";
          document.getElementById("pricing_competitor_min_rating_count").value   = 
            d.pricing_competitor_min_rating_count ?? "";
          document.getElementById("max_competitor_price_ratio").value = 
            d.max_competitor_price_ratio != null ? parseFloat(d.max_competitor_price_ratio).toFixed(2) : "";
          document.getElementById("max_listing_price_limit").value    = 
            d.max_listing_price_limit != null ? parseFloat(d.max_listing_price_limit).toFixed(2) : "";
          document.getElementById("discount_rate").value =
            d.discount_rate != null ? parseFloat(d.discount_rate).toFixed(2) : "";            

          document.getElementById("min_profit_rate").value = 
            d.min_profit_rate != null ? parseFloat(d.min_profit_rate).toFixed(2) : "";
          document.getElementById("max_profit_rate").value = 
            d.max_profit_rate != null ? parseFloat(d.max_profit_rate).toFixed(2) : "";
          document.getElementById("amazon_fee_rate").value = 
            d.amazon_fee_rate != null ? parseFloat(d.amazon_fee_rate).toFixed(2) : "";
          document.getElementById("oversea_remittance_fee_rate").value = 
            d.oversea_remittance_fee_rate != null ? parseFloat(d.oversea_remittance_fee_rate).toFixed(2) : "";

          document.getElementById("gst_rate").value = 
            d.gst_rate != null ? parseFloat(d.gst_rate).toFixed(2) : "";            
          document.getElementById("customs_duty_rate").value = 
            d.customs_duty_rate != null ? parseFloat(d.customs_duty_rate).toFixed(2) : "";
          document.getElementById("fuel_surcharge_rate").value = 
            d.fuel_surcharge_rate != null ? parseFloat(d.fuel_surcharge_rate).toFixed(2) : "";

          document.getElementById("shipping_outsource_cost").value = 
            d.shipping_outsource_cost != null ? parseFloat(d.shipping_outsource_cost).toFixed(2) : "";            
          document.getElementById("extra_cost").value = 
            d.extra_cost != null ? parseFloat(d.extra_cost).toFixed(2) : "";

          document.getElementById("default_handling_time").value = 
            d.default_handling_time ?? "";

      } catch (err) {
          console.error("[ERR] loadPricingMasterRules:", err);
      }
  };

  // --- ▼ SECTION 06: 販売先条件 Pricing Master Rules 保存 ▼ ---
  window.updatePricingMasterRules = async function(region) {

      const countryCode = localStorage.getItem("sellingCountryCode");
      if (!countryCode) return;

      const payload = {
          user_id: ZSSS_USER_ID,
          country_code: countryCode,

          pricing_competitor_min_rating_percent: parseFloat(document.getElementById("pricing_competitor_min_rating_percent")?.value || 0),
          pricing_competitor_min_rating_count:   parseInt(document.getElementById("pricing_competitor_min_rating_count")?.value || 0),

          max_competitor_price_ratio: parseFloat(document.getElementById("max_competitor_price_ratio")?.value || 0),
          max_listing_price_limit: parseFloat(document.getElementById("max_listing_price_limit")?.value || 0),
          discount_rate: parseFloat(document.getElementById("discount_rate")?.value || 0),

          min_profit_rate: parseFloat(document.getElementById("min_profit_rate")?.value || 0),
          max_profit_rate: parseFloat(document.getElementById("max_profit_rate")?.value || 0),
          amazon_fee_rate: parseFloat(document.getElementById("amazon_fee_rate")?.value || 0),

          gst_rate: parseFloat(document.getElementById("gst_rate")?.value || 0),  
          customs_duty_rate: parseFloat(document.getElementById("customs_duty_rate")?.value || 0),          
          oversea_remittance_fee_rate: parseFloat(document.getElementById("oversea_remittance_fee_rate")?.value || 0),
          fuel_surcharge_rate: parseFloat(document.getElementById("fuel_surcharge_rate")?.value || 0),

          shipping_outsource_cost: parseFloat(document.getElementById("shipping_outsource_cost")?.value || 0),          
          extra_cost: parseFloat(document.getElementById("extra_cost")?.value || 0),
          default_handling_time: parseInt(document.getElementById("default_handling_time")?.value || 0),
      };

      try {
          const res = await fetch("/pricing/update_pricing_master_rules", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload)
          });

          const data = await res.json();
          if (data.status !== "success") {
              window.showToast("販売側設定の保存に失敗：" + data.message, "error");
          }
      } catch (err) {
          console.error("[ERR] updatePricingMasterRules:", err);
          window.showToast("販売側設定の保存中にエラーが発生", "error");
      }
  };

  // --- ▼ SECTION 07: 通貨表示更新（UI競合設定 通貨表示用） ▼ ---
  function updateListingCurrencyUnit(countryCode) {
      if (!countryCode) return;
      if (!window.marketplaceInfo) return;

      const region = window.marketplaceInfo[countryCode];
      if (!region || !region.currency) return;

      const currency = region.currency;

      document.querySelectorAll(".listing_currency_unit").forEach(el => {
          el.textContent = currency;
      });
  }

  // --- ▼ SECTION 08: HOME通貨表示更新（UI出品価格算定 通貨表示用） ▼ ---
  async function updateHomeCurrencyUnit() {
      const res = await fetch(`/pricing/get_home_currency?user_id=${ZSSS_USER_ID}`);
      const json = await res.json();

      if (!json.currency) return;

      document.querySelectorAll(".home_currency_unit").forEach(el => {
          el.textContent = json.currency;
      });
  }

  // --- ▼ SECTION 09: 保存ボタン処理 ▼ ---  
  const saveBtn = document.getElementById("savePricingBtn");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      console.log("A");
      await updateOfferFilterRules();
      console.log("B");
      await saveShippingConfigV2();
      console.log("C");
      await updatePricingMasterRules(); 
      console.log("D");

      // --- ▼ Price Check 再計算（API再取得なし） ▼ ---
      if (lastPricingDebugData) {
        runPricingDebug();
      }      
    });
  }

  // --- ▼ SECTION 10: Region変更時 通貨更新 ▼ ---
  document.addEventListener("zsss:regionChanged", (e) => {
      const countryCode = e.detail?.country_code;
      updateListingCurrencyUnit(countryCode);
      updateHomeCurrencyUnit();  
      loadPricingMasterRules(countryCode); 
  });

  // --- ▼ SECTION 11: Pricing設定 Offer部 初期読込み ▼ ---
  const globalRegion = document.getElementById("globalRegion");
  const region = globalRegion?.value;
  loadShippingConfigV2(region);
  loadOfferFilterRules(region);
  

}); // DOM終わり括弧



