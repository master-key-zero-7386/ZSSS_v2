// =====================================================
// ファイル名: static/js/admin/admin_tools.js
// 目的:管理者用ツール類
// =====================================================

// --- ▼ SECTION 01: 初期読込（全部まとめる） ▼ ---
document.addEventListener("DOMContentLoaded", () => {
    fetch("/admin/get_bg_scan_settings")
        .then(res => res.json())
        .then(data => {
            console.log("TTL:", data.ttl_sleep_sec);
            if (data.status !== "ok") return;

            document.getElementById("bg_scan_interval_min").value = data.interval_min;
            document.getElementById("bg_scan_limit").value        = data.scan_limit;
            document.getElementById("ttl_sleep_sec").value        = data.ttl_sleep_sec ?? 0.2;
        });

  // --- ▼ SECTION 02: ▼ First 巡回設定 保存（時間 + LIMIT） ▼ ---
  document.getElementById("save_bg_scan_interval")?.addEventListener("click", () => {

    // ① 巡回間隔（分）
    const intervalEl = document.getElementById("bg_scan_interval_min");
    const intervalVal = Number(intervalEl.value);

    if (!intervalVal || intervalVal <= 0) {
      alert("巡回間隔は 0.1 以上を入力してください");
      return;
    }

    // ② 巡回件数 LIMIT
    const limitEl = document.getElementById("bg_scan_limit");
    const limitVal = Number(limitEl.value);

    if (!limitVal || limitVal <= 0) {
      alert("巡回件数は 1 以上を入力してください");
      return;
    }

    // ③ 保存API呼び出し
    fetch("/admin/save_bg_scan_settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        interval_min: intervalVal,
        scan_limit: limitVal
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          showToast("FIRST Cycle 保存完了", "success")
        } else {
          showToast("保存失敗", "error")
        }
      })
      .catch(() => {
        document.getElementById("bg_scan_interval_msg").textContent = "通信エラー";
      });
  });

  // --- ▼ SECTION 03: TTL 保存 ▼ ---
  document.getElementById("save_ttl_settings")?.addEventListener("click", () => {

    const ttlEl = document.getElementById("ttl_sleep_sec");
    const ttlVal = Number(ttlEl.value);

    if (ttlVal < 0) {
      alert("TTL Sleep は 0 以上");
      return;
    }

    fetch("/admin/save_bg_scan_settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        ttl_sleep_sec: ttlVal
      })
    })
    .then(res => res.json())
    .then(data => {
      if (data.status === "ok") {
        showToast("TTL TIME 保存完了", "success")
      } else {
        showToast("保存失敗", "error")
      }
    });
  });

  // --- ▼ SECTION 04: RAWチェックツール ▼ ---
  document.getElementById("raw_check_btn")?.addEventListener("click", async () => {

      const asin = document.getElementById("raw_asin").value.trim();
      if (!asin) return;

      const region = document.getElementById("globalRegion")?.value;
      if (!region) return;

      try {
          const res = await fetch(`/admin/debug/get_raw_by_asin?asin=${asin}&country_code=${region}`);
          const data = await res.json();

          // TTL ID
          const ttlRes = await fetch(`/admin/debug/get_ttl_state?country_code=${region}`);
          const ttlData = await ttlRes.json();
          document.getElementById("ttl_last_id").textContent = ttlData.last_id ?? "";

          document.getElementById("raw-id").textContent =
            "listed_id: " + (data.id_listed ?? "なし") +
            " / catalog_id: " + (data.id_catalog ?? "なし") +
            " / pricing_id: " + (data.id_pricing ?? "なし");

          document.getElementById("raw_home_catalog").textContent =
              JSON.stringify(data.home_catalog, null, 2);

          document.getElementById("raw_region_catalog").textContent =
              JSON.stringify(data.region_catalog, null, 2);

          document.getElementById("raw_home_pricing").textContent =
              JSON.stringify(data.home_pricing, null, 2);

          document.getElementById("raw_region_pricing").textContent =
              JSON.stringify(data.region_pricing, null, 2);

      } catch (e) {
          console.error("RAWチェックエラー", e);
      }
  });

}); //DOMC 終了




