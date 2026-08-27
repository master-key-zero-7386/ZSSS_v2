// =====================================================
// ファイル名: static/js/ttl_home_pricing_panel.js
// 目的: HOME Pricing TTL 稼働状況パネル（Dashboard）
//   /account/ttl-home-pricing-summary を取得して描画。30秒ごと自動更新。
// =====================================================

(function () {
    "use strict";

    var REFRESH_MS = 30000;
    var timer = null;

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
        });
    }

    function fmtNum(n) {
        if (n == null) return "-";
        return Number(n).toLocaleString();
    }

    function fmtLocal(iso) {
        if (!iso) return "-";
        try {
            var d = new Date(iso.indexOf("Z") >= 0 ? iso : iso + "Z");
            return d.toLocaleString();
        } catch (e) {
            return iso;
        }
    }

    function fmtAge(h) {
        if (h == null) return "-";
        if (h < 1) return Math.round(h * 60) + "分前";
        if (h < 48) return h.toFixed(1) + "時間前";
        return (h / 24).toFixed(1) + "日前";
    }

    function kpi(label, value, cls) {
        return (
            '<div class="ttlhp-kpi ' + (cls || "") + '">' +
            '<div class="k">' + esc(label) + "</div>" +
            '<div class="v">' + value + "</div>" +
            "</div>"
        );
    }

    function histogram(b) {
        var items = [
            ["<1h", b.lt1h, ""],
            ["1-6h", b.h1_6, ""],
            ["6-24h", b.h6_24, ""],
            ["1-3d", b.d1_3, "stale"],
            [">3d", b.gt3d, "dead"],
            ["未取得", b.never, "dead"],
        ];
        var max = 1;
        items.forEach(function (it) { if (it[1] > max) max = it[1]; });
        var bars = items.map(function (it) {
            var pct = Math.round((it[1] / max) * 100);
            return '<div class="bar ' + it[2] + '" style="height:' + pct + '%" title="' + esc(it[0]) + ": " + fmtNum(it[1]) + '"></div>';
        }).join("");
        var labels = items.map(function (it) {
            return "<span>" + esc(it[0]) + "<br>" + fmtNum(it[1]) + "</span>";
        }).join("");
        return '<div class="ttlhp-hist">' + bars + "</div><div class=\"ttlhp-hist-labels\">" + labels + "</div>";
    }

    function countryTable(rows) {
        if (!rows || !rows.length) return "";
        var head =
            "<thead><tr>" +
            "<th>国</th><th>TTL(日)</th><th>対象</th><th>鮮度内</th><th>期限切れ</th><th>未取得</th><th>カバー率</th><th>最古</th><th>24h更新</th>" +
            "</tr></thead>";
        var body = rows.map(function (c) {
            var cov = c.coverage_pct == null ? "-" : c.coverage_pct.toFixed(1) + "%";
            return (
                "<tr>" +
                "<td>" + esc(c.country) + "</td>" +
                "<td>" + (c.ttl_days == null ? "-" : c.ttl_days) + "</td>" +
                "<td>" + fmtNum(c.total) + "</td>" +
                "<td>" + fmtNum(c.fresh) + "</td>" +
                "<td>" + fmtNum(c.overdue) + "</td>" +
                "<td>" + fmtNum(c.never) + "</td>" +
                "<td>" + cov + "</td>" +
                "<td>" + fmtAge(c.oldest_age_hours) + "</td>" +
                "<td>" + fmtNum(c.updated_24h) + "</td>" +
                "</tr>"
            );
        }).join("");
        return '<table class="ttlhp-table">' + head + "<tbody>" + body + "</tbody></table>";
    }

    function render(data) {
        var o = data.overall || {};
        var cyc = data.cycle || {};
        var cfg = data.config || {};

        if (!o.total && !(cyc.last)) {
            return '<div style="color:#888;">まだデータがありません（TTLループ稼働後に表示されます）。</div>';
        }

        var cov = o.coverage_pct == null ? 0 : o.coverage_pct;
        var covBar =
            '<div class="ttlhp-cover-bar">' +
            '<div class="ttlhp-cover-fill" style="width:' + cov + '%"></div>' +
            '<div class="ttlhp-cover-label">カバー率 ' + cov.toFixed(1) + "% （" + fmtNum(o.fresh) + " / " + fmtNum(o.total) + "）</div>" +
            "</div>";

        var oldestCls = "";
        if (o.oldest_age_hours != null) {
            if (o.oldest_age_hours >= 72) oldestCls = "bad";
            else if (o.oldest_age_hours >= 48) oldestCls = "warn";
        }

        var kpis =
            '<div class="ttlhp-kpis">' +
            kpi("対象総数", fmtNum(o.total)) +
            kpi("期限切れ", fmtNum(o.overdue), o.overdue > 0 ? "warn" : "") +
            kpi("未取得(NULL)", fmtNum(o.never), o.never > 0 ? "warn" : "") +
            kpi("最古の待ち行", fmtAge(o.oldest_age_hours) + " <small>" + esc(fmtLocal(o.oldest_at)) + "</small>", oldestCls) +
            kpi("直近1時間の更新", fmtNum(o.updated_1h) + " <small>件</small>") +
            kpi("直近24時間の更新", fmtNum(o.updated_24h) + " <small>件</small>") +
            kpi("全ASIN1巡の推定", o.est_full_sweep_hours == null ? "-" : "約 " + o.est_full_sweep_hours + " <small>時間</small>") +
            "</div>";

        var hist = "<div style=\"margin-top:12px;\"><b>鮮度分布</b>" + histogram(o.buckets || {}) + "</div>";

        // --- サイクル（フェーズ2） ---
        var stuckBadge = cyc.stuck
            ? '<span class="ttlhp-badge stuck">⚠ 停滞（同じ行に貼り付き疑い）</span>'
            : '<span class="ttlhp-badge ok">正常（最古が前進中）</span>';

        var lastLine = "-";
        if (cyc.last) {
            var L = cyc.last;
            lastLine =
                esc(fmtLocal(L.started_at)) +
                " ｜ 対象 " + fmtNum(L.target_count) +
                " / 実行 " + fmtNum(L.dispatched_count) +
                " / エラー " + fmtNum(L.error_count) +
                " ｜ 積み残し " + fmtNum(L.backlog_count) +
                " ｜ 最古 " + esc(fmtLocal(L.oldest_before)) + " → " + esc(fmtLocal(L.oldest_after));
        }

        var cycleBlock =
            '<div style="margin-top:14px;">' +
            "<b>サイクル稼働（ttl_cycle_log）</b> &nbsp; " + stuckBadge +
            '<div style="font-size:13px; margin-top:6px;">最終サイクル： ' + lastLine + "</div>" +
            '<div class="ttlhp-kpis" style="margin-top:8px;">' +
            kpi("1時間のサイクル数", fmtNum(cyc.cycles_1h)) +
            kpi("24hのサイクル数", fmtNum(cyc.cycles_24h)) +
            kpi("実処理数 直近1h", fmtNum(cyc.dispatched_1h) + " <small>件</small>") +
            kpi("実処理数 直近24h", fmtNum(cyc.dispatched_24h) + " <small>件</small>") +
            kpi("エラー 直近24h", fmtNum(cyc.errors_24h), (cyc.errors_24h > 0 ? "warn" : "")) +
            "</div></div>";

        var cfgLine =
            '<div style="font-size:11px; color:#999; margin-top:8px;">' +
            "設定: 1サイクル上限 " + esc(cfg.ttl_limit_home_pricing == null ? "未設定(→50)" : cfg.ttl_limit_home_pricing) +
            " 件 ／ Pricing Sleep " + esc(cfg.ttl_sleep_sec_pricing == null ? "-" : cfg.ttl_sleep_sec_pricing) +
            " 秒 ／ サイクル間 " + esc(cfg.ttl_cycle_sleep_sec == null ? "-" : cfg.ttl_cycle_sleep_sec) + " 秒" +
            "</div>";

        var byCountry = "<div style=\"margin-top:14px;\"><b>国別</b>" + countryTable(data.by_country) + "</div>";

        return covBar + kpis + hist + cycleBlock + cfgLine + byCountry;
    }

    function load() {
        var body = document.getElementById("ttlhp-body");
        if (!body) return;

        fetch("/account/ttl-home-pricing-summary")
            .then(function (res) { return res.json(); })
            .then(function (res) {
                if (res.status !== "ok") {
                    body.innerHTML = '<div style="color:#c0392b;">取得エラー: ' + esc(res.message || "unknown") + "</div>";
                    return;
                }
                body.innerHTML = render(res.data || {});
                var up = document.getElementById("ttlhp-updated-at");
                if (up) up.textContent = new Date().toLocaleString();
            })
            .catch(function (err) {
                console.error("ttl-home-pricing-summary error:", err);
                body.innerHTML = '<div style="color:#c0392b;">通信エラー</div>';
            });
    }

    function init() {
        if (!document.getElementById("ttlhp-body")) return;
        load();
        if (timer) clearInterval(timer);
        timer = setInterval(load, REFRESH_MS);

        var btn = document.getElementById("ttlhpReload");
        if (btn && !btn.dataset.bound) {
            btn.addEventListener("click", load);
            btn.dataset.bound = "1";
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
