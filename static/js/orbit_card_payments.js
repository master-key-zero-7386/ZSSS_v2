// =====================================================
// ファイル名: static/js/orbit_card_payments.js
// 目的: 分析タブ「支払い予定」サブタブ（クレカ別の支払い予定。カード登録は ORBIT「クレカ管理」）― 選んだ支払月に、カードごとに
//   いくら引き落とされるかの目安を出す。データは /orbit/profit-analysis/card-payments。
//   サブタブを開くたび・カードの締め日/支払日を変えたときに集計し直す（発注管理の入力が反映されるように）。
// =====================================================

(function () {
    const pane = document.getElementById("orbit-pane-card-pay");
    const tbody = document.querySelector("#card-pay-table tbody");
    if (!pane || !tbody) return;

    const payMonthSel = document.getElementById("card-pay-month");
    const payStatus = document.getElementById("card-pay-status");
    let payLoaded = false;

    const esc = (v) => (typeof orbitEscapeHtml === "function")
        ? orbitEscapeHtml(v == null ? "" : String(v))
        : String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const yen = (v) => (v == null ? "" : "¥" + Math.round(v).toLocaleString());
    const md = (iso) => (iso ? iso.slice(5).replace("-", "/") : "");
    const monthLabel = (ym) => `${ym.slice(0, 4)}年${Number(ym.slice(5))}月`;

    function payItemsHtml(items) {
        if (!items.length) return '<span class="orbit-profit-sub">この期間の仕入れはありません</span>';
        return `<table>${items.map(i => `
            <tr>
                <td>${esc(md(i.date))}</td>
                <td>${i.serial != null ? "N" + esc(i.serial) : ""}${i.archived ? '<span class="orbit-profit-sub">・履歴</span>' : ""}</td>
                <td>${esc(i.supplier || "")}</td>
                <td class="name">${esc(i.product_name || "")}</td>
                <td class="num">${i.price == null ? '<span class="orbit-text-red">金額未入力</span>' : yen(i.price)}</td>
            </tr>`).join("")}</table>`;
    }

    function payRowHtml(r, idx, isNoCard) {
        const notes = [];
        if (!r.ok) notes.push('<span class="orbit-text-red">締め日・支払日が読めません（上の表で「月末」「翌月27日」の形に）</span>');
        if (r.missing_price) notes.push(`<span class="orbit-text-red">金額未入力 ${r.missing_price}件</span>`);
        if (r.open) notes.push("締め前（まだ増えます）");
        if (r.overdue) notes.push('<span class="orbit-profit-sub">支払い済み</span>');
        if (isNoCard && r.count) notes.push("どのカードか入れてください");
        const period = r.period_start ? `${md(r.period_start)} 〜 ${md(r.period_end)}` : "";
        return `
            <tr class="card-pay-row" data-idx="${idx}">
                <td>${r.count ? "▶ " : ""}<b>${esc(r.card_name)}</b>
                    <span class="orbit-profit-sub">${isNoCard ? "" : esc(`${r.closing_day || "?"}締め・${r.payment_day || "?"}`)}</span></td>
                <td>${isNoCard ? "" : esc(md(r.pay_date))}</td>
                <td>${esc(period)}</td>
                <td class="num">${r.count || ""}</td>
                <td class="num"><b>${r.count ? yen(r.total) : ""}</b></td>
                <td>${notes.join("　")}</td>
            </tr>
            <tr class="card-pay-items" data-idx="${idx}" style="display:none;"><td colspan="6">${payItemsHtml(r.items || [])}</td></tr>`;
    }

    function renderCardPayments(d) {
        payMonthSel.innerHTML = d.months.map(m =>
            `<option value="${esc(m)}"${m === d.month ? " selected" : ""}>${esc(monthLabel(m))}</option>`).join("");
        const all = [...d.rows];
        const hasNoCard = d.no_card && d.no_card.count;
        if (hasNoCard) all.push(d.no_card);
        tbody.innerHTML =
            all.map((r, i) => payRowHtml(r, i, hasNoCard && i === all.length - 1)).join("") +
            `<tr class="card-pay-total"><td>合計（${esc(monthLabel(d.month))}の支払い）</td><td></td><td></td>
                <td class="num">${d.rows.reduce((n, r) => n + r.count, 0)}</td><td class="num">${yen(d.total)}</td>
                <td class="orbit-profit-sub">利用クレカ未入力の分は入っていません</td></tr>`;
        payStatus.innerHTML = d.unknown_cards.length
            ? `<span class="orbit-text-red">上の表に無いカード名の仕入れがあります：${d.unknown_cards.map(esc).join("、")}</span>` : "";
    }

    async function loadCardPayments() {
        payStatus.textContent = "集計中…";
        try {
            const month = payLoaded ? payMonthSel.value : "";
            const res = await fetch(`/orbit/profit-analysis/card-payments?month=${encodeURIComponent(month)}&_=${Date.now()}`);
            const json = await res.json();
            if (json.status !== "success") throw new Error(json.message || "集計に失敗しました");
            payStatus.textContent = "";
            renderCardPayments(json.data);
            payLoaded = true;
        } catch (e) {
            console.error("[card-payments]", e);
            payStatus.textContent = e.message;
        }
    }

    tbody.addEventListener("click", (e) => {
        const tr = e.target.closest("tr.card-pay-row");
        if (!tr) return;
        const items = tr.nextElementSibling;
        if (!items || !tr.querySelector("td").textContent.includes("▶")) return;
        items.style.display = items.style.display === "none" ? "" : "none";
    });
    payMonthSel?.addEventListener("change", loadCardPayments);
    document.getElementById("card-pay-refresh")?.addEventListener("click", loadCardPayments);

    // サブタブを開くたびに集計（発注管理で入れた利用クレカ・仕入れ価格を反映するため）
    document.querySelector('.st-subtab-btn[data-target="orbit-pane-card-pay"]')
        ?.addEventListener("click", loadCardPayments);
    // 上の表でカードの追加・変更・削除があったら集計し直す（orbit.js が投げる）
    document.addEventListener("orbit:credit-cards-changed", () => {
        if (payLoaded) loadCardPayments();
    });
    // ページを開いた時点で支払い予定が表示されていれば、そのまま集計
    if (pane.classList.contains("active")) loadCardPayments();
})();
