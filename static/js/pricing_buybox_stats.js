// ==========================================
// ファイル名: static/js/pricing_buybox_stats.js
// 目的: Pricing 設定「カート取得状況」― LIVE の出品のうち自分がカートを取っている割合（国全体・
//   カテゴリ別手数料率の対象・商品タイプごと）と、日ごとの推移。国は上部の #globalRegion（ALL は不可）。
//   データは /pricing/buybox_stats（今の数字はその場で集計するので数秒かかる）。
//   集計・記録は amazon/services/buybox_stats_service.py
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
  const section = document.getElementById("buybox-stats-section");
  if (!section) return;

  const msgEl = document.getElementById("buybox-stats-msg");
  let country = "";

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (v == null ? "" : Number(v).toLocaleString());
  const pct = (v) => (v == null ? "—" : v + "%");
  const setMsg = (text, color) => { msgEl.textContent = text || ""; msgEl.style.color = color || "#555"; };

  function nowRow(label, s) {
    return `
      <tr>
        <td><b>${esc(label)}</b></td>
        <td style="text-align:right;">${num(s.live_count)}</td>
        <td style="text-align:right;"><b>${pct(s.buybox_rate)}</b></td>
        <td style="text-align:right;">${num(s.buybox_mine)}</td>
        <td style="text-align:right;">${num(s.buybox_other)}</td>
        <td style="text-align:right;">${pct(s.lowest_rate)}</td>
        <td style="text-align:right;">${num(s.cheaper_other)}</td>
        <td style="text-align:right;">${pct(s.fresh_rate)}</td>
      </tr>`;
  }

  function render(d) {
    document.querySelector("#buybox-stats-now tbody").innerHTML =
      nowRow("全体", d.all) +
      (d.target_types.length ? nowRow("対象（カテゴリ別手数料率の表）", d.target) : "");

    const hist = d.history || [];
    document.querySelector("#buybox-stats-history tbody").innerHTML = hist.length
      ? hist.map(h => `
          <tr>
            <td>${esc(h.date)}</td>
            <td style="text-align:right;"><b>${pct(h.all.buybox_rate)}</b></td>
            <td style="text-align:right;">${pct(h.all.lowest_rate)}</td>
            <td style="text-align:right;"><b>${pct(h.target.buybox_rate)}</b></td>
            <td style="text-align:right;">${pct(h.target.lowest_rate)}</td>
            <td style="text-align:right;">${num(h.target.live_count)}</td>
            <td style="text-align:center;">${h.category_fee_enabled ? '<span style="color:#c62828; font-weight:700;">ON</span>' : "OFF"}</td>
          </tr>`).join("")
      : `<tr><td colspan="7" style="color:#777;">まだ記録がありません（毎日1回、自動で記録されます）</td></tr>`;

    const targets = new Set(d.target_types || []);
    document.querySelector("#buybox-stats-types tbody").innerHTML = (d.by_type || []).map(r => `
      <tr${targets.has(r.product_type) ? ' style="background:#fff8e1;"' : ""}>
        <td>${esc(r.product_type)}</td>
        <td style="text-align:right;">${num(r.live_count)}</td>
        <td style="text-align:right;"><b>${pct(r.buybox_rate)}</b></td>
        <td style="text-align:right;">${pct(r.lowest_rate)}</td>
        <td style="text-align:right;">${num(r.cheaper_other)}</td>
      </tr>`).join("");
  }

  function clear() {
    section.querySelectorAll("tbody").forEach(tb => { tb.innerHTML = ""; });
  }

  async function load(countryCode) {
    country = (countryCode || document.getElementById("globalRegion")?.value || "").toUpperCase();
    clear();
    if (!country || country === "ALL") {
      setMsg("上で国を選ぶと出ます");
      return;
    }
    setMsg(`${country} を集計中…`);
    try {
      const res = await fetch(`/pricing/buybox_stats?country_code=${encodeURIComponent(country)}&_=${Date.now()}`);
      const json = await res.json();
      if (json.status !== "success") throw new Error(json.message || "集計に失敗しました");
      render(json.data);
      setMsg(`対象の国：${country}`);
    } catch (e) {
      console.error("[buybox_stats] load", e);
      setMsg(e.message, "#c62828");
    }
  }

  document.getElementById("buybox-stats-refresh").addEventListener("click", () => load(country));
  document.addEventListener("zsss:regionChanged", (e) => load(e.detail?.country_code));
  // カテゴリ別手数料率の表を保存したら「対象」が変わるので出し直す
  document.addEventListener("zsss:categoryFeeSaved", () => load(country));
  load();
});
