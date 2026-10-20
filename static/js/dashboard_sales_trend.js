// ============================================================
// ファイル名: static/js/dashboard_sales_trend.js
// 目的: Dashboard「売上トレンド」サブタブ ― マーケット別の日次販売個数を折れ線で表示する。
//   Y軸＝販売個数。ツールチップに「販売個数 ／ 総額（現地通貨） ／ 概算利益率（母数併記）」を出す。
//   表示切替ボタンで折れ線を「利益額(円) ／ 利益率(%) ／ 仕入額(円)」にも切り替えられる。
//   グラフ上に、選んだ期間の合計表（マーケット別＋合計：個数・利益額・利益率・仕入額・消費税目安）を出す。
//   データは /orbit/sales-trend（list_orders_with_calc を通す＝全注文を再計算するため数秒かかる）。
//   自動ロードはせず「更新」ボタンでのみ集計する。集計後に期間ボタンを変えると新しい期間で再集計する。
//   期間は「直近N日」ボタン／「月で選ぶ」／「日付指定（開始〜終了）」のどれか（日の区切りは日本時間）。
//   月・日付指定は選んだ時点で集計する。
// ============================================================

(function () {
  "use strict";

  const PERIOD_WRAP_ID = "salesTrendPeriod";
  const CANVAS_ID = "salesTrendChart";
  const STATUS_ID = "salesTrendStatus";
  const REFRESH_ID = "salesTrendRefresh";
  const MODE_WRAP_ID = "salesTrendMode";
  const SUMMARY_ID = "salesTrendSummary";
  const MONTH_ID = "salesTrendMonth";
  const START_ID = "salesTrendStart";
  const END_ID = "salesTrendEnd";
  const RANGE_APPLY_ID = "salesTrendRangeApply";
  const MONTH_OPTIONS = 12; // 今月を含めて過去12か月

  // 表示切替：折れ線の値・Y軸見出し・単位
  const MODES = {
    qty: { axis: "販売個数", unit: "個" },
    profit: { axis: "利益額(円)", unit: "円" },
    rate: { axis: "利益率(%)", unit: "%" },
    purchase: { axis: "仕入額(円)", unit: "円" },
  };

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
  let loadedKey = null; // 最後に集計した期間（クエリ文字列）。未集計なら null
  // 現在の期間指定: {type:"days", days} / {type:"month", month:"YYYY-MM"} / {type:"range", start, end}
  let period = { type: "days", days: 30 };
  let lastData = null;
  let mode = "qty";

  function sumArr(arr) {
    return (arr || []).reduce(function (a, v) { return a + (v || 0); }, 0);
  }

  function fmtYen(v) {
    if (v == null) return "-";
    return "¥" + new Intl.NumberFormat("ja-JP", { maximumFractionDigits: 0 }).format(Math.round(v));
  }

  function rateOf(profit, sale) {
    return sale ? Math.round(profit / sale * 1000) / 10 : null;
  }

  // モード別の日次値（1マーケット分）。利益率は日ごとに Σ利益 ÷ Σ販売額、算出できない日は null（線を切る）
  function valuesFor(s, m) {
    if (m === "profit") {
      return s.profit_jpy.map(function (v, i) { return s.profit_cnt[i] ? v : null; });
    }
    if (m === "rate") return s.profit_rate_pct;
    if (m === "purchase") return s.purchase_jpy;
    return s.counts;
  }

  function fmtValue(v, m) {
    if (v == null) return "—";
    if (m === "profit" || m === "purchase") return fmtYen(v);
    if (m === "rate") return v + "%";
    return v + "個";
  }

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
    const lineDatasets = data.series.map(function (s, i) {
      const color = colorForMarket(s.market, i);
      return {
        label: s.market,
        data: valuesFor(s, mode),
        borderColor: color,
        backgroundColor: color,
        tension: 0.25,
        borderWidth: 2,
        pointRadius: thinPoints ? 0 : 2,
        pointHoverRadius: 4,
        order: 1,
        // ツールチップ用の追加データ（Chart.js は未知プロパティを無視するのでそのまま持たせる）
        _amounts: s.amounts,
        _currency: s.currency,
        _amountMissing: s.amount_missing,
        _profitRate: s.profit_rate_pct,
        _profitCnt: s.profit_cnt,
        _lineCnt: s.line_cnt,
        _counts: s.counts,
        _profitJpy: s.profit_jpy,
        _purchaseJpy: s.purchase_jpy,
        _purchaseCnt: s.purchase_cnt,
      };
    });

    // 全マーケット合計（日別）を棒グラフで折れ線の背面に重ねる（利益率は全体の Σ利益 ÷ Σ販売額）
    const totals = data.dates.map(function (_, i) {
      const sum = function (key) {
        return data.series.reduce(function (a, s) { return a + (s[key][i] || 0); }, 0);
      };
      if (mode === "profit") return sum("profit_cnt") ? sum("profit_jpy") : null;
      if (mode === "rate") return rateOf(sum("profit_jpy"), sum("sale_jpy"));
      if (mode === "purchase") return sum("purchase_jpy");
      return sum("counts");
    });
    const totalDataset = {
      type: "bar",
      label: "合計",
      data: totals,
      backgroundColor: "rgba(140,140,140,0.16)",
      borderColor: "rgba(110,110,110,0.35)",
      borderWidth: 1,
      barPercentage: 0.5,
      categoryPercentage: 0.6,
      order: 2,
    };

    return lineDatasets.concat([totalDataset]);
  }

  function tooltipLabel(ctx) {
    const ds = ctx.dataset;
    const i = ctx.dataIndex;
    if (!ds._amounts) {
      // 合計（棒グラフ）は内訳を持たないため値のみ表示
      return ds.label + ": " + fmtValue(ctx.raw, mode);
    }
    const parts = [ds.label + ": " + ds._counts[i] + "個"];

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
      parts.push("利益額 " + fmtYen(ds._profitJpy[i]));
    }
    if (ds._purchaseCnt[i]) {
      parts.push("仕入額 " + fmtYen(ds._purchaseJpy[i]) + "（入力済 " + ds._purchaseCnt[i] + "/" + lcnt + "件）");
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
      applyAxis();
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
        font: { size: 14 },
        plugins: {
          legend: { position: "bottom", labels: { font: { size: 14 } } },
          tooltip: { titleFont: { size: 14 }, bodyFont: { size: 14 }, callbacks: { label: tooltipLabel } },
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: MODES[mode].axis, font: { size: 14 } },
            ticks: { precision: 0, font: { size: 14 } },
          },
          x: {
            ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12, font: { size: 14 } },
          },
        },
      },
    });
  }

  function applyAxis() {
    chart.options.scales.y.title.text = MODES[mode].axis;
  }

  // 期間合計表（マーケット別＋合計）
  function renderSummary(data) {
    const el = document.getElementById(SUMMARY_ID);
    if (!el) return;
    if (!data || !data.series.length) { el.innerHTML = ""; return; }

    function rowFor(label, qty, lines, profit, sale, pcnt, estProfit, estCnt, purchase, purCnt, cls) {
      const rate = rateOf(profit, sale);
      const profitText = pcnt ? fmtYen(profit) : "-";
      const estText = estCnt ? fmtYen(estProfit) + '<span class="sub">（' + estCnt + "件）</span>" : "-";
      return "<tr" + (cls ? ' class="' + cls + '"' : "") + ">" +
        "<td>" + label + "</td>" +
        '<td class="num">' + qty + "個</td>" +
        '<td class="num' + (pcnt && profit < 0 ? " neg" : "") + '">' + profitText + "</td>" +
        '<td class="num">' + estText + "</td>" +
        '<td class="num' + (rate != null && rate < 0 ? " neg" : "") + '">' + (rate == null ? "-" : rate + "%") + "</td>" +
        '<td class="num sub">' + pcnt + "/" + lines + "件</td>" +
        '<td class="num">' + (purCnt ? fmtYen(purchase) : "-") + "</td>" +
        '<td class="num">' + (purCnt ? fmtYen(purchase * 10 / 110) : "-") + "</td>" +
        '<td class="num sub">' + purCnt + "/" + lines + "件</td>" +
        "</tr>";
    }

    const t = { qty: 0, lines: 0, profit: 0, sale: 0, pcnt: 0, est: 0, estCnt: 0, purchase: 0, purCnt: 0 };
    let body = "";
    data.series.forEach(function (s) {
      const r = {
        qty: sumArr(s.counts), lines: sumArr(s.line_cnt),
        profit: sumArr(s.profit_jpy), sale: sumArr(s.sale_jpy), pcnt: sumArr(s.profit_cnt),
        est: sumArr(s.profit_est_jpy), estCnt: sumArr(s.profit_est_cnt),
        purchase: sumArr(s.purchase_jpy), purCnt: sumArr(s.purchase_cnt),
      };
      Object.keys(t).forEach(function (k) { t[k] += r[k]; });
      body += rowFor(s.market, r.qty, r.lines, r.profit, r.sale, r.pcnt, r.est, r.estCnt, r.purchase, r.purCnt, "");
    });
    if (data.series.length > 1) {
      body += rowFor("合計", t.qty, t.lines, t.profit, t.sale, t.pcnt, t.est, t.estCnt, t.purchase, t.purCnt, "total");
    }

    el.innerHTML = "<table><thead><tr>" +
      "<th>マーケット</th><th>販売個数</th><th>利益額</th><th>うち概算</th><th>利益率</th><th>利益算出</th>" +
      "<th>仕入額</th><th>消費税目安</th><th>仕入入力済</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table>";
  }

  function setRefreshDisabled(disabled) {
    const btn = document.getElementById(REFRESH_ID);
    if (btn) btn.disabled = disabled;
  }

  function periodQuery(p) {
    if (p.type === "month") return "month=" + encodeURIComponent(p.month);
    if (p.type === "range") return "start=" + encodeURIComponent(p.start) + "&end=" + encodeURIComponent(p.end);
    return "days=" + p.days;
  }

  function load(p) {
    if (loading) return;
    const key = periodQuery(p);
    loading = true;
    setRefreshDisabled(true);
    setStatus("集計中…（全注文を再計算するため数秒かかることがあります）");
    fetch("/orbit/sales-trend?" + key)
      .then(function (r) { return r.json(); })
      .then(function (json) {
        if (!json || json.status !== "success") {
          setStatus((json && json.message) || "取得に失敗しました");
          return;
        }
        loadedKey = key;
        const d = json.data;
        if (!d.series.length) {
          setStatus("対象期間に注文がありません（" + d.start + " 〜 " + d.end + "・日本時間）");
        } else {
          setStatus(d.start + " 〜 " + d.end + "（日本時間）　販売個数 合計 " + d.total_qty + "個");
        }
        lastData = d;
        renderSummary(d);
        render(d);
      })
      .catch(function () { setStatus("取得に失敗しました（通信エラー）"); })
      .finally(function () { loading = false; setRefreshDisabled(false); });
  }

  // 期間指定の見た目（どれが選ばれているか）を period に合わせる
  function markPeriod() {
    const wrap = document.getElementById(PERIOD_WRAP_ID);
    wrap.querySelectorAll(".stp-btn").forEach(function (b) {
      b.classList.toggle("active", period.type === "days" && parseInt(b.getAttribute("data-days"), 10) === period.days);
    });
    const month = document.getElementById(MONTH_ID);
    if (month) {
      if (period.type !== "month") month.value = "";
      month.classList.toggle("active", period.type === "month");
    }
    [START_ID, END_ID].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("active", period.type === "range");
    });
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  // 「月で選ぶ」の選択肢（今月から過去 MONTH_OPTIONS か月）。日本時間の今月を基準にする
  function fillMonthOptions() {
    const sel = document.getElementById(MONTH_ID);
    if (!sel) return;
    const now = new Date(Date.now() + 9 * 3600 * 1000); // UTC → JST
    let y = now.getUTCFullYear();
    let m = now.getUTCMonth() + 1;
    for (let i = 0; i < MONTH_OPTIONS; i++) {
      const opt = document.createElement("option");
      opt.value = y + "-" + pad2(m);
      opt.textContent = y + "年" + m + "月" + (i === 0 ? "（今月）" : "");
      sel.appendChild(opt);
      m -= 1;
      if (m === 0) { m = 12; y -= 1; }
    }
  }

  function init() {
    const wrap = document.getElementById(PERIOD_WRAP_ID);
    if (!wrap) return; // Dashboard 以外のページ

    // 期間ボタン：選択を切り替えるだけ。すでに一度集計済みなら新しい期間で再集計する
    // （未集計なら「更新」を押すまで通信しない）。
    wrap.addEventListener("click", function (e) {
      const btn = e.target.closest(".stp-btn");
      if (!btn) return;
      const days = parseInt(btn.getAttribute("data-days"), 10) || 30;
      period = { type: "days", days: days };
      markPeriod();
      if (loadedKey !== null && periodQuery(period) !== loadedKey) load(period);
    });

    fillMonthOptions();
    const month = document.getElementById(MONTH_ID);
    if (month) {
      month.addEventListener("change", function () {
        if (!month.value) return;
        period = { type: "month", month: month.value };
        markPeriod();
        load(period);
      });
    }

    const rangeApply = document.getElementById(RANGE_APPLY_ID);
    if (rangeApply) {
      rangeApply.addEventListener("click", function () {
        const start = document.getElementById(START_ID).value;
        const end = document.getElementById(END_ID).value;
        if (!start || !end) {
          setStatus("日付指定は開始日と終了日の両方を選んでください");
          return;
        }
        period = { type: "range", start: start, end: end };
        markPeriod();
        load(period);
      });
    }

    // 表示切替：集計済みデータを描き直すだけ（再集計しない）
    const modeWrap = document.getElementById(MODE_WRAP_ID);
    if (modeWrap) {
      modeWrap.addEventListener("click", function (e) {
        const btn = e.target.closest(".stp-btn");
        if (!btn) return;
        modeWrap.querySelectorAll(".stp-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        mode = btn.getAttribute("data-mode") || "qty";
        if (lastData) render(lastData);
      });
    }

    const refresh = document.getElementById(REFRESH_ID);
    if (refresh) {
      refresh.addEventListener("click", function () { load(period); });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
