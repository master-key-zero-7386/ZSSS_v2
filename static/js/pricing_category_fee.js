// ==========================================
// ファイル名: static/js/pricing_category_fee.js
// 目的: Pricing 設定「カテゴリ別手数料率」― 商品タイプごとの手数料率・最低利益率の表と、国ごとの ON/OFF。
//   国は上部の #globalRegion（ALL のときは使えない）。保存は「この表を保存」だけで、上の Save とは別。
//   試算は表の今の内容で計算する（保存しなくてよい・値段も DB も変えない）。
//   「決済の実績」は利益分析の参考表と同じ集計（amazon/adapters/orbit_category_fee.py）で、表を書き換えても変わらない。
//   値段の計算への適用は amazon/core/category_fee.py
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
  const section = document.getElementById("category-fee-section");
  if (!section) return;

  const tbody = document.querySelector("#category-fee-rules tbody");
  const enabledEl = document.getElementById("category-fee-enabled");
  const msgEl = document.getElementById("category-fee-msg");
  const countryEl = document.getElementById("category-fee-country");
  const simSummaryEl = document.getElementById("category-fee-sim-summary");
  let country = "";
  let actuals = {}; // 決済の実績 {商品タイプ: {median, min, max, count}}

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (msg, type) => window.showToast ? window.showToast(msg, type) : alert(msg);
  const setMsg = (text, color) => { msgEl.textContent = text || ""; msgEl.style.color = color || "#555"; };

  function actualHtml(productType) {
    const a = actuals[(productType || "").trim().toUpperCase()];
    if (!a) return '<span style="color:#aaa;">—</span>';
    const range = a.min === a.max ? "" : `（${a.min}〜${a.max}%）`;
    return `<b>${esc(a.median)}%</b> <span style="color:#777;">${a.count}件${range}</span>`;
  }

  function rowHtml(r) {
    return `
      <tr>
        <td><input type="text" class="input cf-type" value="${esc(r.product_type)}" style="width:320px;"></td>
        <td><input type="number" class="input cf-fee" step="0.01" value="${esc(r.fee_rate)}" style="width:90px;"></td>
        <td><input type="number" class="input cf-min" step="0.01" value="${esc(r.min_profit_rate)}" style="width:90px;"></td>
        <td class="cf-actual" style="text-align:right;">${actualHtml(r.product_type)}</td>
        <td class="cf-live" style="text-align:right;"></td>
        <td class="cf-floor" style="text-align:right;"></td>
        <td class="cf-change" style="text-align:right;"></td>
        <td><button type="button" class="btn-blue cf-del">削除</button></td>
      </tr>`;
  }

  function readRows() {
    return [...tbody.querySelectorAll("tr")].map(tr => ({
      product_type: tr.querySelector(".cf-type").value.trim().toUpperCase(),
      fee_rate: tr.querySelector(".cf-fee").value,
      min_profit_rate: tr.querySelector(".cf-min").value,
    })).filter(r => r.product_type);
  }

  function render(data) {
    actuals = data.actuals || {};
    enabledEl.checked = !!data.enabled;
    tbody.innerHTML = (data.rows || []).map(rowHtml).join("");
    simSummaryEl.textContent = "";
  }

  function setDisabled(disabled) {
    section.querySelectorAll("input, button").forEach(el => { el.disabled = disabled; });
  }

  async function load(countryCode) {
    country = (countryCode || document.getElementById("globalRegion")?.value || "").toUpperCase();
    countryEl.textContent = country ? `（対象の国：${country}）` : "";
    tbody.innerHTML = "";
    if (!country || country === "ALL") {
      setDisabled(true);
      setMsg("上で国を選ぶと使えます");
      return;
    }
    setDisabled(false);
    setMsg("");
    try {
      const res = await fetch(`/pricing/category_fee?country_code=${encodeURIComponent(country)}&_=${Date.now()}`);
      const json = await res.json();
      if (json.status !== "success") throw new Error(json.message || "読み込みに失敗しました");
      render(json.data);
    } catch (e) {
      console.error("[category_fee] load", e);
      setMsg(e.message, "#c62828");
    }
  }

  document.getElementById("category-fee-add").addEventListener("click", () => {
    tbody.insertAdjacentHTML("beforeend", rowHtml({ product_type: "", fee_rate: "", min_profit_rate: "" }));
  });

  // 商品タイプを書き換えたら、その商品タイプの実績に出し直す
  tbody.addEventListener("input", (e) => {
    if (!e.target.classList.contains("cf-type")) return;
    e.target.closest("tr").querySelector(".cf-actual").innerHTML = actualHtml(e.target.value);
  });

  tbody.addEventListener("click", (e) => {
    if (e.target.classList.contains("cf-del")) e.target.closest("tr").remove();
  });

  document.getElementById("category-fee-save").addEventListener("click", async () => {
    if (!country || country === "ALL") return;
    const enabled = enabledEl.checked;
    if (enabled && !confirm(`${country} でカテゴリ別手数料率を ON にします。表の商品タイプの出品は、次の TTL から値段が変わります。よろしいですか？`)) return;
    try {
      const res = await fetch("/pricing/category_fee", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_code: country, enabled, rows: readRows() }),
      });
      const json = await res.json();
      if (json.status !== "success") throw new Error(json.message || "保存に失敗しました");
      render(json.data);
      document.dispatchEvent(new CustomEvent("zsss:categoryFeeSaved", { detail: { country_code: country } }));
      toast(`${country} のカテゴリ別手数料率を保存しました（${json.data.enabled ? "ON" : "OFF"}）`, "success");
    } catch (e) {
      console.error("[category_fee] save", e);
      toast(e.message, "error");
    }
  });

  document.getElementById("category-fee-simulate").addEventListener("click", async () => {
    if (!country || country === "ALL") return;
    setMsg("試算中…");
    try {
      const res = await fetch("/pricing/category_fee/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country_code: country, rows: readRows() }),
      });
      const json = await res.json();
      if (json.status !== "success") throw new Error(json.message || "試算に失敗しました");
      const d = json.data;
      const byType = Object.fromEntries((d.rows || []).map(r => [r.product_type, r]));
      tbody.querySelectorAll("tr").forEach(tr => {
        const r = byType[tr.querySelector(".cf-type").value.trim().toUpperCase()];
        tr.querySelector(".cf-live").textContent = r ? r.live.toLocaleString() : "";
        tr.querySelector(".cf-floor").textContent = r ? r.at_floor.toLocaleString() : "";
        const c = r ? r.change_pct : null;
        tr.querySelector(".cf-change").textContent = c == null ? "" : (c > 0 ? "+" : "") + c + "%";
      });
      simSummaryEl.textContent =
        `LIVE ${d.live_total.toLocaleString()}件のうち、対象 ${d.affected.toLocaleString()}件（最低価格で出品中 ${d.affected_at_floor.toLocaleString()}件）。` +
        `今の設定：Amazon Fee ${d.base_fee_rate}%・Min Profit Margin ${d.base_min_profit_rate}%。` +
        `最低価格で出品中の商品は、ほぼ「最低価格の変化」の分だけ値段が変わります。`;
      setMsg("");
    } catch (e) {
      console.error("[category_fee] simulate", e);
      setMsg(e.message, "#c62828");
    }
  });

  document.addEventListener("zsss:regionChanged", (e) => load(e.detail?.country_code));
  load();
});
