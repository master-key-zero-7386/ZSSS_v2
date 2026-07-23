// =====================================================
// ファイル名: static/js/api_counter.js
// 目的： APIカウント集計
// =====================================================


// === ▼ API COUNTER：Dashboard 起動時取得 ▼ ===
window.addEventListener("DOMContentLoaded", () => {

    const wrap = document.getElementById("api-counter-detail");
    if (!wrap) return;

    fetch("/account/api-usage-summary")
        .then(res => res.json())
        .then(res => {
            if (res.status !== "ok") return;

            const data = res.data || {};
            let html = "";

            function headerRow(title) {
                return `
                <div class="api-header">
                    <span class="col-market">${title}</span>
                    <span class="col-num">Product API </span>
                    <span class="col-num">Price API </span>
                    <span class="col-num">1 Day</span>
                    <span class="col-num">1 Month</span>                    
                    <span class="col-num">Total Count </span>
                </div>`;
            }

            function dataRow(label, c, p, d, m, t) {
                return `
                <div class="api-row">
                    <span class="col-market">${label}</span>
                    <span class="col-num">${c}</span>
                    <span class="col-num">${p}</span>
                    <span class="col-num">${d}</span>
                    <span class="col-num">${m}</span>        
                    <span class="col-num">${t}</span>
                </div>`;
            }

            if (data.home) {
                html += headerRow("[HOME]");
                html += dataRow(
                    data.home.label,
                    data.home.catalog,
                    data.home.pricing,
                    data.home.day,
                    data.home.month,
                    data.home.total
                );
                html += `<div class="api-spacer"></div>`;

            }

            if (Array.isArray(data.regions)) {
                html += `<div class="api-spacer"></div>`;
                html += headerRow("[SELLING]");
                data.regions.forEach(r => {
                    html += dataRow( 
                        r.label,
                        r.catalog,
                        r.pricing,
                        r.day,
                        r.month,
                        r.total
                    );
                });
            }

            const percent = ((data.grand_total / data.credit_limit) * 100).toFixed(1);
            const remain  = data.credit_limit - data.grand_total;

            html += `
            <hr>
            
            <div class="api-total">
                Total API Calls  : ${data.grand_total} / ${data.credit_limit} (${percent}%)
                &nbsp;&nbsp;|&nbsp;&nbsp;
                Remaining :  ${remain}
            </div>
            `;

            wrap.innerHTML = html;

            const updatedEl = document.getElementById("api-counter-updated-at");
            if (updatedEl) updatedEl.textContent = new Date().toLocaleString();
        })
        .catch(err => {
            console.error("api-usage-summary error:", err);
        });

    // === ▼ 429発生状況：Dashboard起動時取得 ▼ ===
    const wrap429 = document.getElementById("api-429-detail");
    if (!wrap429) return;

    fetch("/account/api-429-summary")
        .then(res => res.json())
        .then(res => {
            if (res.status !== "ok") return;

            const d = res.data || {};
            const avg = (d.avg_interval_sec !== null && d.avg_interval_sec !== undefined)
                ? `${d.avg_interval_sec} 秒`
                : "-";
            const last = d.last_occurred_at || "-";

            wrap429.innerHTML = `
                本日: <b>${d.today_count ?? 0}</b> 件
                &nbsp;&nbsp;|&nbsp;&nbsp;
                前日: <b>${d.yesterday_count ?? 0}</b> 件
                &nbsp;&nbsp;|&nbsp;&nbsp;
                本日の平均発生間隔: ${avg}
                &nbsp;&nbsp;|&nbsp;&nbsp;
                直近発生: ${last}
            `;
        })
        .catch(err => {
            console.error("api-429-summary error:", err);
        });

});

