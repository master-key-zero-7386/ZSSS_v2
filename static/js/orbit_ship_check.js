// =====================================================
// ファイル名: static/js/orbit_ship_check.js
// 目的: ORBIT「送料検証」サブタブ（想定送料・請求重量 vs 発送代行の実績）
//   データは /orbit/ship-check（発注管理の注文＋アーカイブ済み）。重いので「更新」ボタンで手動集計。
// =====================================================

(function () {
    const pane = document.getElementById("orbit-pane-ship-check");
    if (!pane) return;

    let shipCheckRows = [];
    let loaded = false;

    const esc = (v) => (typeof orbitEscapeHtml === "function")
        ? orbitEscapeHtml(v == null ? "" : String(v))
        : String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const yen = (v) => (v == null ? "" : "¥" + Math.round(v).toLocaleString());
    const signedYen = (v) => (v == null ? "" : (v > 0 ? "+" : v < 0 ? "−" : "") + "¥" + Math.abs(Math.round(v)).toLocaleString());
    const kg = (v) => (v == null ? "" : (Math.round(v * 100) / 100).toLocaleString() + "kg");
    const toast = (msg, type) => window.showToast ? window.showToast(msg, type) : alert(msg);

    // --- ▼ SECTION 01: 基準（設定） ▼ ---
    const SETTING_INPUTS = {
        fee_diff_yen: "shipcheck-fee-yen",
        fee_diff_pct: "shipcheck-fee-pct",
        carrier_diff_yen: "shipcheck-carrier-yen",
        weight_ratio: "shipcheck-weight-ratio",
        weight_diff_kg: "shipcheck-weight-kg",
    };

    function fillSettings(settings) {
        Object.entries(SETTING_INPUTS).forEach(([k, id]) => {
            const el = document.getElementById(id);
            if (el && settings && settings[k] != null) el.value = settings[k];
        });
    }

    document.getElementById("shipcheck-settings-save-btn")?.addEventListener("click", async () => {
        const body = {};
        Object.entries(SETTING_INPUTS).forEach(([k, id]) => { body[k] = document.getElementById(id)?.value; });
        try {
            const res = await fetch("/orbit/ship-check/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.status !== "success") throw new Error(data.message || "保存に失敗しました");
            fillSettings(data.settings);
            toast("基準を保存しました。「更新」で判定し直します", "success");
        } catch (e) {
            console.error("[ship-check/settings]", e);
            toast("基準の保存に失敗しました", "error");
        }
    });

    // --- ▼ SECTION 02: 読み込み ▼ ---
    async function loadShipCheck() {
        const status = document.getElementById("shipcheck-status");
        const btn = document.getElementById("shipcheck-refresh-btn");
        if (status) status.textContent = "集計中…（注文が多いと数秒かかります）";
        if (btn) btn.disabled = true;
        try {
            const res = await fetch("/orbit/ship-check");
            const data = await res.json();
            if (data.status !== "success") throw new Error(data.message || "集計に失敗しました");
            shipCheckRows = data.rows || [];
            fillSettings(data.settings);
            loaded = true;
            buildFilterOptions();
            render();
            if (status) status.textContent = `${shipCheckRows.length}件（代行会社の実績がある注文）`;
        } catch (e) {
            console.error("[ship-check]", e);
            if (status) status.textContent = "集計に失敗しました";
            toast("送料検証の集計に失敗しました", "error");
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    document.getElementById("shipcheck-refresh-btn")?.addEventListener("click", loadShipCheck);

    // サブタブを初めて開いたときだけ自動で1回集計（以後は「更新」ボタン）
    document.querySelector('.st-subtab-btn[data-target="orbit-pane-ship-check"]')?.addEventListener("click", () => {
        if (!loaded) loadShipCheck();
    });

    ["shipcheck-filter-warn", "shipcheck-filter-carrier", "shipcheck-filter-country", "shipcheck-filter-confirmed"]
        .forEach(id => document.getElementById(id)?.addEventListener("change", render));

    function buildFilterOptions() {
        const fill = (id, label, values) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const cur = sel.value;
            sel.innerHTML = `<option value="">${label}：すべて</option>` +
                values.map(v => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(v)}</option>`).join("");
        };
        fill("shipcheck-filter-carrier", "キャリア",
            [...new Set(shipCheckRows.map(r => r.actual_carrier || "不明"))].sort());
        fill("shipcheck-filter-country", "国",
            [...new Set(shipCheckRows.map(r => r.marketplace_country || r.ship_country || "不明"))].sort());
    }

    function filteredRows() {
        const warn = document.getElementById("shipcheck-filter-warn")?.value || "any";
        const carrier = document.getElementById("shipcheck-filter-carrier")?.value || "";
        const country = document.getElementById("shipcheck-filter-country")?.value || "";
        const confirmedOnly = !!document.getElementById("shipcheck-filter-confirmed")?.checked;
        return shipCheckRows.filter(r => {
            if (carrier && (r.actual_carrier || "不明") !== carrier) return false;
            if (country && (r.marketplace_country || r.ship_country || "不明") !== country) return false;
            if (confirmedOnly && !r.weight_confirmed) return false;
            if (warn === "any") return r.fee_warn || r.carrier_warn || r.weight_warn;
            if (warn === "fee") return r.fee_warn;
            if (warn === "carrier") return r.carrier_warn;
            if (warn === "weight") return r.weight_warn;
            return true;
        });
    }

    // --- ▼ SECTION 03: 描画 ▼ ---
    const COLUMNS = [
        { label: "N番", cell: r => r.agent_serial_no != null ? `N${esc(r.agent_serial_no)}` : "" },
        { label: "状態", cell: r => {
            if (r.excluded) return `対象外（${esc(r.excluded)}）`;
            const s = r.weight_confirmed ? "確定" : "暫定";
            return r.archived ? `${s}・履歴` : s;
        } },
        { label: "国", cell: r => esc(r.marketplace_country || r.ship_country || "") },
        { label: "ASIN", cell: r => r.asin
            ? `<span class="asin-cell" style="color:#007bff;text-decoration:underline;cursor:pointer;" title="クリックでコピー">${esc(r.asin)}</span>` +
              (r._asin_warn_count >= 2 ? ` <span class="orbit-text-red" title="この一覧でこのASINが警告になった回数">警告×${r._asin_warn_count}</span>` : "")
            : "" },
        { label: "商品名", cls: () => "shipcheck-name", cell: r => esc(r.product_name || "") },
        { label: "数量", cell: r => esc(r.qty) },
        { label: "キャリア 想定→実際", cls: r => r.carrier_warn ? "orbit-ship-warn" : "",
          cell: r => `${esc(r.est_carrier || "?")} → ${esc(r.actual_carrier || "不明")}${r.actual_carrier_inferred ? '<span title="発送種別が空欄のため、運賃が送料表と一致したキャリアを推定">（推定）</span>' : ""}` },
        { label: "想定重量", cell: r => kg(r.est_weight_kg) },
        { label: "実重量", cls: r => r.weight_warn ? "orbit-ship-warn" : r.weight_under ? "orbit-ship-under" : "",
          cell: r => kg(r.actual_weight_kg) + (r.actual_weight_kg != null && !r.weight_confirmed ? "（暫定）" : "") },
        { label: "重量差", cls: r => r.weight_warn ? "orbit-ship-warn" : r.weight_under ? "orbit-ship-under" : "",
          cell: r => r.weight_diff_kg == null ? "" : `${r.weight_diff_kg > 0 ? "+" : ""}${kg(r.weight_diff_kg)}（×${r.weight_ratio.toFixed(1)}）` },
        { label: "想定送料", cell: r => yen(r.est_fee) + (r.est_fee != null && !r.est_is_snapshot ? "*" : "") },
        { label: "送料合計", cls: r => r.fee_warn ? "orbit-ship-warn" : r.fee_under ? "orbit-ship-under" : "", cell: r => yen(r.actual_fee_total) },
        { label: "送料差", cls: r => r.fee_warn ? "orbit-ship-warn" : r.fee_under ? "orbit-ship-under" : "",
          cell: r => r.fee_diff == null ? "" : `${signedYen(r.fee_diff)}（${r.fee_diff_pct > 0 ? "+" : ""}${Math.round(r.fee_diff_pct)}%）` },
        { label: "実運賃", cell: r => yen(r.actual_fee_base) },
        { label: "他キャリア最安", cell: r => r.carrier_best ? `${esc(r.carrier_best)} ${yen(r.carrier_best_price)}` : "" },
        { label: "キャリア差", cls: r => r.carrier_warn ? "orbit-ship-warn" : "",
          cell: r => r.carrier_diff == null ? "" : signedYen(r.carrier_diff) },
        { label: "利益率", cls: r => r.profit_rate_pct != null && r.profit_rate_pct < 0 ? "orbit-text-red" : "",
          cell: r => r.profit_rate_pct == null ? "" : `${(Math.round(r.profit_rate_pct * 10) / 10).toLocaleString()}%` },
        { label: "代行出荷日", cell: r => esc(r.agent_weight_recorded_date || "") },
    ];

    function render() {
        // ASINごとの警告回数（同じ商品が何度も外れていれば重量区分・出品の見直し候補）
        const asinWarn = {};
        shipCheckRows.forEach(r => {
            if (r.asin && (r.fee_warn || r.carrier_warn || r.weight_warn)) asinWarn[r.asin] = (asinWarn[r.asin] || 0) + 1;
        });
        shipCheckRows.forEach(r => { r._asin_warn_count = asinWarn[r.asin] || 0; });

        const rows = filteredRows();
        const table = document.getElementById("shipcheck-table");
        if (!table) return;
        table.querySelector("thead tr").innerHTML = COLUMNS.map(c => `<th>${c.label}</th>`).join("");
        table.querySelector("tbody").innerHTML = rows.length
            ? rows.map(r => `<tr${r.tips && r.tips.length ? ` title="${esc(r.tips.join("\n"))}"` : ""}>` +
                COLUMNS.map(c => `<td class="${c.cls ? c.cls(r) : ""}">${c.cell(r)}</td>`).join("") + "</tr>").join("")
            : `<tr><td colspan="${COLUMNS.length}" style="text-align:center; color:#888;">該当する注文はありません</td></tr>`;

        renderSummary();
    }

    // キャリア×国ごとの平均ズレ（燃油・外注費などの補正を見直す目安）。対象外を除き、上の絞り込み（警告種別以外）に従う
    function renderSummary() {
        const box = document.getElementById("shipcheck-summary");
        if (!box) return;
        const carrier = document.getElementById("shipcheck-filter-carrier")?.value || "";
        const country = document.getElementById("shipcheck-filter-country")?.value || "";
        const confirmedOnly = !!document.getElementById("shipcheck-filter-confirmed")?.checked;
        const base = shipCheckRows.filter(r => !r.excluded
            && (!carrier || (r.actual_carrier || "不明") === carrier)
            && (!country || (r.marketplace_country || r.ship_country || "不明") === country)
            && (!confirmedOnly || r.weight_confirmed));

        const nFee = base.filter(r => r.fee_warn).length;
        const nCarrier = base.filter(r => r.carrier_warn).length;
        const nWeight = base.filter(r => r.weight_warn).length;

        const groups = {};
        base.forEach(r => {
            const key = `${r.actual_carrier || "不明"}|${r.marketplace_country || r.ship_country || "不明"}`;
            const g = groups[key] || (groups[key] = { n: 0, feeN: 0, feeSum: 0, pctSum: 0, wN: 0, wSum: 0 });
            g.n++;
            if (r.fee_diff != null) { g.feeN++; g.feeSum += r.fee_diff; g.pctSum += r.fee_diff_pct; }
            if (r.weight_diff_kg != null) { g.wN++; g.wSum += r.weight_diff_kg; }
        });
        const groupRows = Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0])).map(([key, g]) => {
            const [c, m] = key.split("|");
            return `<tr><td style="text-align:left;">${esc(c)}</td><td style="text-align:left;">${esc(m)}</td><td>${g.n}</td>` +
                `<td>${g.feeN ? signedYen(g.feeSum / g.feeN) : ""}</td>` +
                `<td>${g.feeN ? `${(g.pctSum / g.feeN) > 0 ? "+" : ""}${Math.round(g.pctSum / g.feeN)}%` : ""}</td>` +
                `<td>${g.wN ? `${(g.wSum / g.wN) > 0 ? "+" : ""}${kg(g.wSum / g.wN)}` : ""}</td></tr>`;
        }).join("");

        box.innerHTML = `
            <table>
                <tr><th>警告</th><th>件数</th></tr>
                <tr><td style="text-align:left;">①送料のズレ</td><td>${nFee}</td></tr>
                <tr><td style="text-align:left;">②キャリア差</td><td>${nCarrier}</td></tr>
                <tr><td style="text-align:left;">③重量のズレ</td><td>${nWeight}</td></tr>
                <tr><td style="text-align:left;">対象の注文</td><td>${base.length}</td></tr>
            </table>
            <table>
                <tr><th>実キャリア</th><th>国</th><th>件数</th><th>平均 送料差</th><th>平均 送料差%</th><th>平均 重量差</th></tr>
                ${groupRows || `<tr><td colspan="6" style="text-align:center; color:#888;">データなし</td></tr>`}
            </table>
            <div style="color:#888;">想定送料の「*」＝まだ保存されていない想定（今の設定で計算した値）。行にマウスを乗せると警告の内容が出ます。</div>`;
    }
})();
