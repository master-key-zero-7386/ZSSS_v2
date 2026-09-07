// ============================================================
// ファイル名: static/js/dashboard_sales_trend.js
// 目的: Dashboard「売上トレンド」サブタブ ― マーケット別の日次販売個数を折れ線で表示する。
//   Y軸＝販売個数。ツールチップに「販売個数 ／ 総額（現地通貨） ／ 概算利益率（母数併記）」を出す。
//   データは /orbit/sales-trend（list_orders_with_calc を通す＝全注文を再計算するため数秒かかる）。
//   自動ロードはせず「更新」ボタンでのみ集計する。集計後に期間ボタンを変えると新しい期間で再集計する。
// ============================================================

(function () {
  "use strict";

  const PERIOD_WRAP_ID = "salesTrendPeriod";
  const CANVAS_ID = "salesTrendChart";
  const STATUS_ID = "salesTrendStatus";
  const REFRESH_ID = "salesTrendRefresh";

  // 主要マーケットは固定色。未定義のコードはフォールバックパレットを順に割り当てる。
  const MARKET_COLORS = {
    JP: "#e5484d", AU: "#4a90e2", US: "#2fb344", CA: "#f7931a",
    SG: "#8e5cd9", UK: "#e8590c", GB: "#e8590c", DE: "#0ca678",
    "不明": "#adb5bd",
  };
  const FALLBACK_COLORS = [
    "#4a90e2", "#2fb344", "#f7931a", "#8e5cd9",
    "#e5484d", "#0ca678", "#e8590c", "#845ef7",
  ];

  let chart = null;
  let loading = false;
  let loadedDays = null;

  function colorForMarket(market, i) {
    return MARKET_COLORS[market] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];
  }

  function fmtAmount(value, currency) {
    if (value == null) return "-";
    if (currency && /^[A-Z]{3}$/.test(currency)) {
      try {
        return new Intl.NumberFormat("ja-JP", {
          style: "currency", currency: currency, maximumFractionDigits: 0,
        }).format(value);
      } catch (e) { /* 未知の通貨コードは下の素の数値表記へ */ }
    }
    const n = new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 0 }).format(value);
    return currency ? currency + " " + n : n;
  }

  function setStatus(text) {
    const el = document.getElementById(STATUS_ID);
    if (el) el.textContent = text || "";
  }

  function buildDatasets(data) {
    const thinPoints = data.dates.length > 120;
    return data.series.map(function (s, i) {
      const color = colorForMarket(s.market, i);
      return {
        label: s.market,
        data: s.counts,
        borderColor: color,
        backgroundColor: color,
        tension: 0.25,
        borderWidth: 2,
        pointRadius: thinPoints ? 0 : 2,
        pointHoverRadius: 4,
        // ツールチップ用の追加データ（Chart.js は未知プロパティを無視するのでそのまま持たせる）
        _amounts: s.amounts,
        _currency: s.currency,
        _amountMissing: s.amount_missing,
        _profitRate: s.profit_rate_pct,
        _profitCnt: s.profit_cnt,
        _lineCnt: s.line_cnt,
      };
    });
  }

  function tooltipLabel(ctx) {
    const ds = ctx.dataset;
    const i = ctx.dataIndex;
    const parts = [ds.label + ": " + ctx.parsed.y + "個"];

    const amount = ds._amounts ? ds._amounts[i] : null;
    const missing = ds._amountMissing ? ds._amountMissing[i] : 0;
    let amountText = "総額 " + fmtAmount(amount, ds._currency);
    if (missing) amountText += "（item_price未取得 " + missing + "件）";
    parts.push(amountText);

    const rate = ds._profitRate ? ds._profitRate[i] : null;
    const pcnt = ds._profitCnt ? ds._profitCnt[i] : 0;
    const lcnt = ds._lineCnt ? ds._lineCnt[i] : 0;
    if (rate == null || pcnt === 0) {
      parts.push("概算利益率 —");
    } else {
      parts.push("概算利益率 " + rate + "%（利益算出 " + pcnt + "/" + lcnt + "件）");
    }
    return parts;
  }

  function render(data) {
    const canvas = document.getElementById(CANVAS_ID);
    if (!canvas || !window.Chart) return;

    const datasets = buildDatasets(data);

    if (chart) {
      chart.data.labels = data.dates;
      chart.data.datasets = datasets;
      chart.update();
      return;
    }

    chart = new window.Chart(canvas.getContext("2d"), {
      type: "line",
      data: { labels: data.dates, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          tooltip: { callbacks: { label: tooltipLabel } },
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: "販売個数" },
            ticks: { precision: 0 },
          },
          x: {
            ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
          },
        },
      },
    });
  }

  function setRefreshDisabled(disabled) {
    const btn = document.getElementById(REFRESH_ID);
    if (btn) btn.disabled = disabled;
  }

  function load(days) {
    if (loading) return;
    loading = true;
    setRefreshDisabled(true);
    setStatus("集計中…（全注文を再計算するため数秒かかることがあります）");
    fetch("/orbit/sales-trend?days=" + days)
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (!json || json.status !== "success") {
          setStatus((json && json.message) || "取得に失敗しました");
          return;
        }
        loadedDays = days;
        const d = json.data;
        if (!d.series.length) {
          setStatus("対象期間に注文がありません（" + d.start + " 〜 " + d.end + "）");
        } else {
          setStatus(d.start + " 〜 " + d.end + "　販売個数 合計 " + d.total_qty + "個");
        }
        render(d);
      })
      .catch(function () { setStatus("取得に失敗しました（通信エラー）"); })
      .finally(function () { loading = false; setRefreshDisabled(false); });
  }

  function activeDays() {
    const wrap = document.getElementById(PERIOD_WRAP_ID);
    const btn = wrap && wrap.querySelector(".stp-btn.active");
    return btn ? (parseInt(btn.getAttribute("data-days"), 10) || 30) : 30;
  }

  function init() {
    const wrap = document.getElementById(PERIOD_WRAP_ID);
    if (!wrap) return; // Dashboard 以外のページ

    // 期間ボタン：選択を切り替えるだけ。すでに一度集計済みなら新しい期間で再集計する
    // （未集計なら「更新」を押すまで通信しない）。
    wrap.addEventListener("click", function (e) {
      const btn = e.target.closest(".stp-btn");
      if (!btn) return;
      wrap.querySelectorAll(".stp-btn").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      const days = parseInt(btn.getAttribute("data-days"), 10) || 30;
      if (loadedDays !== null && days !== loadedDays) load(days);
    });

    const refresh = document.getElementById(REFRESH_ID);
    if (refresh) {
      refresh.addEventListener("click", function () { load(activeDays()); });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
