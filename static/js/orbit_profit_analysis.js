// =====================================================
// ファイル名: static/js/orbit_profit_analysis.js
// 目的: ORBIT「利益分析」サブタブ ― 期間内の注文ごとの利益内訳（販売額・返金・手数料・仕入・送料）と
//   予測送料 vs 実際の送料のズレを一覧にする。見出しクリックで並べ替え（既定は送料差の大きい順）。
//   決済レポート（実績）の取得・手動アップロードもこのサブタブで行う。
//   データは /orbit/profit-analysis（全注文を再計算するため数秒かかる）。
//   サブタブを初めて開いたときだけ自動で集計し、以後は期間の変更か「更新」ボタンで集計する。
//   期間の選び方（直近N日／月／日付指定）は売上トレンドと同じ。
// =====================================================

(function () {
    const pane = document.getElementById("orbit-pane-profit");
    if (!pane) return;

    let rows = [];
    let loaded = false;
    let loading = false;
    let period = { type: "days", days: 30 };
    let sortKey = "ship_diff";
    let sortDesc = true;
    let weightPct = 15; // ズレの目安：実重量が予測よりこの%以上重ければ重量列を赤字（DBに保存）

    const esc = (v) => (typeof orbitEscapeHtml === "function")
        ? orbitEscapeHtml(v == null ? "" : String(v))
        : String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const yen = (v) => (v == null ? "" : "¥" + Math.round(v).toLocaleString());
    const signedYen = (v) => (v == null ? "" : (v > 0 ? "+" : v < 0 ? "−" : "") + "¥" + Math.abs(Math.round(v)).toLocaleString());
    const pct = (v) => (v == null ? "" : (Math.round(v * 10) / 10).toLocaleString() + "%");
    const toast = (msg, type) => window.showToast ? window.showToast(msg, type) : alert(msg);

    // --- ▼ SECTION 01: 期間指定（売上トレンドと同じ選び方） ▼ ---
    function periodQuery(p) {
        if (p.type === "month") return "month=" + encodeURIComponent(p.month);
        if (p.type === "range") return "start=" + encodeURIComponent(p.start) + "&end=" + encodeURIComponent(p.end);
        return "days=" + p.days;
    }

    function markPeriod() {
        pane.querySelectorAll("#profitPeriod .stp-btn").forEach(b => {
            b.classList.toggle("active", period.type === "days" && parseInt(b.dataset.days, 10) === period.days);
        });
        const month = document.getElementById("profitMonth");
        if (period.type !== "month") month.value = "";
        month.classList.toggle("active", period.type === "month");
        ["profitStart", "profitEnd"].forEach(id => {
            document.getElementById(id).classList.toggle("active", period.type === "range");
        });
    }

    (function fillMonthOptions() {
        const sel = document.getElementById("profitMonth");
        const now = new Date(Date.now() + 9 * 3600 * 1000); // UTC → JST
        let y = now.getUTCFullYear();
        let m = now.getUTCMonth() + 1;
        for (let i = 0; i < 12; i++) {
            const opt = document.createElement("option");
            opt.value = `${y}-${m < 10 ? "0" : ""}${m}`;
            opt.textContent = `${y}年${m}月${i === 0 ? "（今月）" : ""}`;
            sel.appendChild(opt);
            m -= 1;
            if (m === 0) { m = 12; y -= 1; }
        }
    })();

    document.getElementById("profitPeriod").addEventListener("click", (e) => {
        const btn = e.target.closest(".stp-btn");
        if (!btn) return;
        period = { type: "days", days: parseInt(btn.dataset.days, 10) || 30 };
        markPeriod();
        load();
    });
    document.getElementById("profitMonth").addEventListener("change", (e) => {
        if (!e.target.value) return;
        period = { type: "month", month: e.target.value };
        markPeriod();
        load();
    });
    document.getElementById("profitRangeApply").addEventListener("click", () => {
        const start = document.getElementById("profitStart").value;
        const end = document.getElementById("profitEnd").value;
        if (!start || !end) {
            setStatus("日付指定は開始日と終了日の両方を選んでください");
            return;
        }
        period = { type: "range", start, end };
        markPeriod();
        load();
    });
    document.getElementById("profitRefresh").addEventListener("click", load);

    // サブタブを初めて開いたときだけ自動で1回集計
    document.querySelector('.st-subtab-btn[data-target="orbit-pane-profit"]')?.addEventListener("click", () => {
        if (!loaded) load();
    });

    // --- ▼ SECTION 02: 読み込み ▼ ---
    function setStatus(text) {
        const el = document.getElementById("profit-status");
        if (el) el.textContent = text || "";
    }

    async function load() {
        if (loading) return;
        loading = true;
        const btn = document.getElementById("profitRefresh");
        btn.disabled = true;
        setStatus("集計中…（全注文を再計算するため数秒かかることがあります）");
        try {
            const res = await fetch("/orbit/profit-analysis?" + periodQuery(period));
            const json = await res.json();
            if (json.status !== "success") throw new Error(json.message || "集計に失敗しました");
            rows = (json.data.rows || []).map(addShipDetail);
            if (json.data.weight_pct != null) {
                weightPct = json.data.weight_pct;
                document.getElementById("profit-weight-pct").value = weightPct;
            }
            loaded = true;
            buildMarketOptions();
            render();
            setStatus(`${json.data.start} 〜 ${json.data.end}（日本時間）　${rows.length}件`);
        } catch (e) {
            console.error("[profit-analysis]", e);
            setStatus("集計に失敗しました");
            toast("利益分析の集計に失敗しました", "error");
        } finally {
            loading = false;
            btn.disabled = false;
        }
    }

    ["profit-filter-market", "profit-filter-kind"].forEach(id =>
        document.getElementById(id).addEventListener("change", render));

    // ズレの目安：変えたらその場で描き直し、DBにも保存（次回・外から開いても同じ値）
    document.getElementById("profit-weight-pct").addEventListener("change", async (e) => {
        const v = parseFloat(e.target.value);
        if (!(v >= 0)) { e.target.value = weightPct; return; }
        weightPct = v;
        render();
        try {
            const res = await fetch("/orbit/profit-analysis/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ weight_pct: v }),
            });
            const json = await res.json();
            if (json.status !== "success") throw new Error();
        } catch (err) {
            console.error("[profit-analysis/settings]", err);
            toast("ズレの目安を保存できませんでした", "error");
        }
    });

    // 並べ替え用の値（キャリア＝「予測→実際」の文字、重量＝実際÷予測）。数量2以上は合計重量なので比べない
    function addShipDetail(r) {
        r.carrier_label = (r.est_carrier || r.actual_carrier) ? `${r.est_carrier || "?"}→${r.actual_carrier || "?"}` : null;
        r.weight_ratio = (Number(r.qty) === 1 && r.est_weight_kg && r.actual_weight_kg) ? r.actual_weight_kg / r.est_weight_kg : null;
        return r;
    }

    function buildMarketOptions() {
        const sel = document.getElementById("profit-filter-market");
        const cur = sel.value;
        const markets = [...new Set(rows.map(r => r.market))].sort();
        sel.innerHTML = `<option value="">国：すべて</option>` +
            markets.map(m => `<option value="${esc(m)}"${m === cur ? " selected" : ""}>${esc(m)}</option>`).join("");
    }

    function filteredRows() {
        const market = document.getElementById("profit-filter-market").value;
        const kind = document.getElementById("profit-filter-kind").value;
        return rows.filter(r => {
            if (market && r.market !== market) return false;
            if (kind === "ship_over") return r.ship_warn;
            if (kind === "ship_diff") return r.ship_diff != null;
            if (kind === "loss") return r.profit_jpy != null && r.profit_jpy < 0;
            if (kind === "no_profit") return r.profit_jpy == null;
            return true;
        });
    }

    // --- ▼ SECTION 03: 描画 ▼ ---
    // 手数料・仕入・送料のうち、販売額に占める割合が一番大きいもの
    function heaviest(r) {
        const c = { fee: r.fee_pct, purchase: r.purchase_pct, ship: r.ship_pct };
        let best = null;
        Object.keys(c).forEach(k => { if (c[k] != null && (best === null || c[k] > c[best])) best = k; });
        return best;
    }

    const estMark = (flag) => (flag ? '<span class="orbit-profit-sub">（概算）</span>' : "");
    const shipDiffCls = (r) => r.ship_warn ? "num orbit-ship-warn" : r.ship_under ? "num orbit-ship-under" : "num";

    // キャリア：予測 → 実際（違えば実際を赤字）。実際に使ったより安いキャリアがあれば下に小さく出す
    function carrierCell(r) {
        if (!r.carrier_label) return "";
        const differ = r.est_carrier && r.actual_carrier && r.est_carrier !== r.actual_carrier;
        const actual = r.actual_carrier
            ? `<span class="${differ ? "orbit-text-red" : ""}">${esc(r.actual_carrier)}</span>` +
              (r.actual_carrier_inferred ? '<span class="orbit-profit-sub">（推定）</span>' : "")
            : "?";
        const cheaper = (r.carrier_best && r.carrier_diff > 0)
            ? `<br><span class="orbit-profit-sub">${esc(r.carrier_best)}なら ${yen(r.carrier_best_price)}</span>` : "";
        return `${esc(r.est_carrier || "?")} → ${actual}${cheaper}`;
    }

    // 重量（請求重量kg）：予測 → 実際。実際が予測より「ズレの目安」%以上重ければ赤字
    function weightCell(r) {
        if (r.est_weight_kg == null && r.actual_weight_kg == null) return "";
        const kg = (v) => (v == null ? "?" : String(Math.round(v * 100) / 100));
        const heavy = r.weight_ratio != null && r.weight_ratio >= 1 + weightPct / 100;
        const qtyNote = Number(r.qty) > 1 ? `<br><span class="orbit-profit-sub">（${esc(r.qty)}個の合計）</span>` : "";
        return `${kg(r.est_weight_kg)} → <span class="${heavy ? "orbit-text-red" : ""}">${kg(r.actual_weight_kg)}kg</span>${qtyNote}`;
    }

    const COLUMNS = [
        { key: "date", label: "注文日", cell: r => esc(r.date) },
        { key: "serial", label: "N番", cell: r => r.serial != null ? `N${esc(r.serial)}` : "" },
        { key: "market", label: "国", cell: r => esc(r.market) + (r.archived ? '<span class="orbit-profit-sub">・履歴</span>' : "") },
        { key: "asin", label: "ASIN", cell: r => r.asin
            ? `<span class="profit-asin" style="color:#007bff;text-decoration:underline;cursor:pointer;" title="クリックでコピー">${esc(r.asin)}</span>` : "" },
        { key: "product_name", label: "商品名", cls: () => "profit-name", cell: r => esc(r.product_name || "") },
        { key: "qty", label: "数量", cls: () => "num", cell: r => esc(r.qty) },
        { key: "sale_jpy", label: "販売額", cls: () => "num", cell: r => yen(r.sale_jpy) },
        { key: "refund_jpy", label: "返金", cls: r => "num" + (r.refund_jpy ? " orbit-text-red" : ""), cell: r => yen(r.refund_jpy) },
        { key: "fee_jpy", label: "手数料", cls: r => "num" + (heaviest(r) === "fee" ? " profit-heavy" : ""),
          cell: r => r.fee_jpy == null ? "" : `${yen(r.fee_jpy)} <span class="orbit-profit-sub">${pct(r.fee_pct)}</span>${estMark(r.fee_is_estimate)}` },
        { key: "purchase_jpy", label: "仕入", cls: r => "num" + (heaviest(r) === "purchase" ? " profit-heavy" : ""),
          cell: r => r.purchase_jpy == null ? "未入力" : `${yen(r.purchase_jpy)} <span class="orbit-profit-sub">${pct(r.purchase_pct)}</span>` },
        { key: "ship_jpy", label: "送料（利益計算）", cls: r => "num" + (heaviest(r) === "ship" ? " profit-heavy" : ""),
          cell: r => r.ship_jpy == null ? "" : `${yen(r.ship_jpy)} <span class="orbit-profit-sub">${pct(r.ship_pct)}</span>` +
            (r.ship_is_bundle ? '<span class="orbit-profit-sub">（同梱按分）</span>' : estMark(r.ship_is_estimate)) },
        { key: "carrier_label", label: "キャリア", cell: carrierCell },
        { key: "weight_ratio", label: "重量", cls: () => "num", cell: weightCell },
        { key: "est_ship", label: "予測送料", cls: () => "num", cell: r => yen(r.est_ship) },
        { key: "actual_ship", label: "実際の送料", cls: () => "num", cell: r => yen(r.actual_ship) },
        { key: "ship_diff", label: "送料差", cls: shipDiffCls,
          cell: r => r.ship_excluded ? `<span class="orbit-profit-sub">対象外（${esc(r.ship_excluded)}）</span>`
            : r.ship_diff == null ? "" : `${signedYen(r.ship_diff)}（${r.ship_diff_pct > 0 ? "+" : ""}${Math.round(r.ship_diff_pct)}%）` },
        { key: "profit_jpy", label: "利益", cls: r => "num" + (r.profit_jpy != null && r.profit_jpy < 0 ? " orbit-text-red" : ""),
          cell: r => r.profit_jpy == null ? "" : yen(r.profit_jpy) + estMark(r.profit_is_estimate) },
        { key: "profit_rate", label: "利益率", cls: r => "num" + (r.profit_rate != null && r.profit_rate < 0 ? " orbit-text-red" : ""),
          cell: r => pct(r.profit_rate) },
    ];

    function sortRows(list) {
        const dir = sortDesc ? -1 : 1;
        return list.slice().sort((a, b) => {
            const va = a[sortKey], vb = b[sortKey];
            const na = va == null || va === "", nb = vb == null || vb === "";
            if (na && nb) return 0;
            if (na) return 1;  // 空欄は並び順に関係なく常に下
            if (nb) return -1;
            if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
            return String(va).localeCompare(String(vb), "ja") * dir;
        });
    }

    function render() {
        const list = sortRows(filteredRows());
        const table = document.getElementById("profit-table");
        table.querySelector("thead tr").innerHTML = COLUMNS.map(c =>
            `<th data-key="${c.key}" class="${c.key === sortKey ? "sorted" : ""}">${c.label}${c.key === sortKey ? (sortDesc ? " ▼" : " ▲") : ""}</th>`).join("");
        table.querySelector("tbody").innerHTML = list.length
            ? list.map(r => `<tr${r.tips.length ? ` title="${esc(r.tips.join("\n"))}"` : ""}>` +
                COLUMNS.map(c => `<td class="${c.cls ? c.cls(r) : ""}">${c.cell(r)}</td>`).join("") + "</tr>").join("")
            : `<tr><td colspan="${COLUMNS.length}" style="text-align:center; color:#888;">該当する注文はありません</td></tr>`;
        renderSummary(list);
    }

    // 絞り込み後の合計
    function renderSummary(list) {
        const box = document.getElementById("profit-summary");
        const withProfit = list.filter(r => r.profit_jpy != null);
        const profit = withProfit.reduce((a, r) => a + r.profit_jpy, 0);
        const sale = withProfit.reduce((a, r) => a + (r.sale_jpy || 0), 0);
        const estN = withProfit.filter(r => r.profit_is_estimate).length;
        const lossN = withProfit.filter(r => r.profit_jpy < 0).length;
        const diffs = list.filter(r => r.ship_diff != null && !r.ship_excluded);
        const over = diffs.filter(r => r.ship_diff > 0).reduce((a, r) => a + r.ship_diff, 0);
        const under = diffs.filter(r => r.ship_diff < 0).reduce((a, r) => a + r.ship_diff, 0);
        const warnN = list.filter(r => r.ship_warn).length;
        box.innerHTML =
            `${list.length}件　利益 ${yen(profit)}（利益率 ${sale ? pct(profit / sale * 100) : "-"}・算出 ${withProfit.length}件／うち概算 ${estN}件）` +
            `　赤字 ${lossN}件` +
            `　送料差：予測より高くついた分 ${signedYen(over)}／安く済んだ分 ${signedYen(under)}（実績 ${diffs.length}件・基準超え ${warnN}件）`;
    }

    // 見出しクリックで並べ替え（同じ見出しをもう一度押すと逆順）。数値は大きい順から始める
    document.querySelector("#profit-table thead").addEventListener("click", (e) => {
        const th = e.target.closest("th[data-key]");
        if (!th) return;
        const key = th.dataset.key;
        if (key === sortKey) {
            sortDesc = !sortDesc;
        } else {
            sortKey = key;
            sortDesc = !["date", "serial", "market", "asin", "product_name", "carrier_label"].includes(key) || key === "date";
        }
        render();
    });

    document.querySelector("#profit-table tbody").addEventListener("click", (e) => {
        const el = e.target.closest(".profit-asin");
        if (!el) return;
        const asin = el.textContent.trim();
        const done = () => window.showCopyNotification?.("コピーしました", el);
        // 外部から http で開くと navigator.clipboard が無いので execCommand で代替
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(asin).then(done).catch(err => console.error("コピー失敗:", err));
        } else {
            const tmp = document.createElement("textarea");
            tmp.value = asin;
            document.body.appendChild(tmp);
            tmp.select();
            document.execCommand("copy");
            document.body.removeChild(tmp);
            done();
        }
    });

    // --- ▼ SECTION 04: 決済レポートの取得（SP-API）・手動アップロード ▼ ---
    // API取得は裏で1分に1件ずつ進むので、取得中は数秒ごとに進み具合を見に行き、終わったら集計し直す。
    const fetchBtn = document.getElementById("settlement-fetch-btn");
    const fetchStatusEl = document.getElementById("settlement-fetch-status");
    let pollTimer = null;

    function resultSummary(results) {
        const ok = results.filter(r => r.status === "ok").length;
        const errors = results.filter(r => r.status !== "ok");
        let text = `取り込み ${ok}件`;
        if (errors.length) text += `・エラー ${errors.length}件`;
        return { text, errors, ok };
    }

    function errorDetail(errors) {
        return errors.map(e => `${e.file ? e.file + " " : ""}${e.settlement_id || ""} ${e.start_date || ""}〜${e.end_date || ""}：${e.message}`).join("\n");
    }

    // notify=true：取得中を見届けた時だけ、終わったらトーストを出して集計し直す
    // （開き直した時に、前回終わった取得の通知が毎回出ないようにする）
    async function pollFetchStatus(notify) {
        clearTimeout(pollTimer);
        let json;
        try {
            const res = await fetch("/orbit/settlements/fetch/status");
            json = await res.json();
            if (json.status !== "success") throw new Error();
        } catch (e) {
            console.error("[settlements/fetch/status]", e);
            fetchBtn.disabled = false;
            return;
        }
        if (json.running) {
            fetchBtn.disabled = true;
            fetchStatusEl.textContent = json.total != null
                ? `${json.message}（${json.done}/${json.total}件・1分に1件）` : json.message;
            pollTimer = setTimeout(() => pollFetchStatus(true), 5000);
            return;
        }
        fetchBtn.disabled = false;
        if (!json.started_at) return; // まだ一度も取得していない
        const { text, errors } = resultSummary(json.results || []);
        const finished = (json.finished_at || "").slice(0, 16).replace("T", " ");
        fetchStatusEl.textContent = json.failed ? json.message
            : (json.total === 0 ? "新しい決済レポートはありません" : `${text}（${finished} UTC）`);
        fetchStatusEl.title = errorDetail(errors);
        if (!notify) return;
        if (json.failed) toast(json.message, "error");
        else toast(json.total === 0 ? "新しい決済レポートはありません" : text, errors.length ? "error" : "success");
        if (loaded) load();
    }

    fetchBtn?.addEventListener("click", async () => {
        fetchBtn.disabled = true;
        try {
            const res = await fetch("/orbit/settlements/fetch", { method: "POST" });
            const json = await res.json();
            if (json.status !== "success") throw new Error(json.message || "取得を始められませんでした");
            fetchStatusEl.textContent = "決済レポートの一覧を取得中";
            pollTimer = setTimeout(() => pollFetchStatus(true), 2000);
        } catch (e) {
            toast(e.message, "error");
            fetchBtn.disabled = false;
        }
    });

    // 画面を開き直したときに取得中なら進み具合を出す
    if (fetchBtn) pollFetchStatus(false);

    const fileInput = document.getElementById("settlement-file-input");
    const fileName = document.getElementById("settlement-file-name");
    fileName?.addEventListener("click", () => fileInput?.click());
    fileInput?.addEventListener("change", () => {
        const names = [...fileInput.files].map(f => f.name);
        fileName.value = names.length > 1 ? `${names.length}ファイル（${names[0]} ほか）` : (names[0] || "");
    });

    document.getElementById("settlement-upload-btn")?.addEventListener("click", async () => {
        if (!fileInput?.files?.length) {
            toast("ファイルを選択してください", "error");
            return;
        }
        const formData = new FormData();
        [...fileInput.files].forEach(f => formData.append("files", f));
        try {
            const res = await fetch("/orbit/settlements/upload", { method: "POST", body: formData });
            const json = await res.json();
            if (json.status !== "success") throw new Error(json.message || "取り込みに失敗しました");
            const { text, errors } = resultSummary(json.results || []);
            if (errors.length) {
                toast(`${text}（エラーの内容は横の文字にマウスを乗せると見られます）`, "error");
                fetchStatusEl.textContent = text;
                fetchStatusEl.title = errorDetail(errors);
            } else {
                toast(text, "success");
            }
            fileInput.value = "";
            fileName.value = "";
            if (loaded) load();
        } catch (e) {
            console.error("[settlements/upload]", e);
            toast(e.message, "error");
        }
    });
})();
