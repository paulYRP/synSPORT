(function () {
  const data = window.SYN_SPORT_DASHBOARD || {};

  const metricMetadata = [
    {
      group: "Utility",
      metric: "Accuracy",
      expected_range: "0 to 1",
      preferred_direction: "Higher is better",
      interpretation: "Prediction accuracy obtained when training on synthetic data and testing against real labels.",
    },
    {
      group: "Utility",
      metric: "F1-score",
      expected_range: "0 to 1",
      preferred_direction: "Higher is better",
      interpretation: "Balance between precision and recall. Useful when classes are uneven.",
    },
    {
      group: "Utility",
      metric: "AUROC",
      expected_range: "0 to 1",
      preferred_direction: "Higher is better",
      interpretation: "Class-separation quality for binary or compatible classification tasks. It is blank when the task does not produce a valid binary AUROC.",
    },
    {
      group: "Utility",
      metric: "AUPRC",
      expected_range: "0 to 1",
      preferred_direction: "Higher is better",
      interpretation: "Precision-recall area. It is blank when the target structure does not support this score.",
    },
    {
      group: "Feature dependence",
      metric: "PearsonCorrDiff",
      expected_range: "0 upward",
      preferred_direction: "Lower is better",
      interpretation: "Average difference between real and synthetic numerical correlations.",
    },
    {
      group: "Feature dependence",
      metric: "UncertaintyCoeffDiff",
      expected_range: "0 upward",
      preferred_direction: "Lower is better",
      interpretation: "Average difference between real and synthetic categorical association patterns.",
    },
    {
      group: "Feature dependence",
      metric: "CorrelationRatioDiff",
      expected_range: "0 upward",
      preferred_direction: "Lower is better",
      interpretation: "Difference in mixed categorical-to-numerical dependence.",
    },
    {
      group: "Statistical similarity",
      metric: "Wasserstein",
      expected_range: "0 upward",
      preferred_direction: "Lower is better",
      interpretation: "Distribution distance. Values close to zero indicate closer real and synthetic marginal distributions.",
    },
    {
      group: "Statistical similarity",
      metric: "JSD",
      expected_range: "0 to 1",
      preferred_direction: "Lower is better",
      interpretation: "Jensen-Shannon distance between feature distributions. Zero means identical distributions.",
    },
    {
      group: "Privacy",
      metric: "MIA_Accuracy",
      expected_range: "0 to 1",
      preferred_direction: "Lower is safer",
      interpretation: "Membership-inference attack accuracy. Lower values indicate weaker ability to identify training records.",
    },
    {
      group: "Uncertainty",
      metric: "std",
      expected_range: "0 upward",
      preferred_direction: "Lower is more stable",
      interpretation: "Variation across repeated runs. It appears when more than one run is available.",
    },
    {
      group: "Statistical test",
      metric: "p",
      expected_range: "0 to 1",
      preferred_direction: "Context dependent",
      interpretation: "P-values appear when enough repeated runs exist to estimate them.",
    },
  ];

  function qs(selector, root = document) {
    return root.querySelector(selector);
  }

  function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function hasValue(value) {
    return value !== null && value !== undefined && String(value).trim() !== "";
  }

  function html(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function numberLike(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric);
  }

  function formatValue(value) {
    if (!hasValue(value)) return "";
    if (numberLike(value)) {
      const numeric = Number(value);
      if (Math.abs(numeric) >= 1000) return numeric.toLocaleString();
      return numeric.toFixed(4).replace(/\.?0+$/, "");
    }
    return String(value);
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(Number(bytes))) return "";
    const value = Number(bytes);
    if (value < 1024) return `${value} B`;
    if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 ** 2).toFixed(1)} MB`;
  }

  function projectHref(path) {
    if (!hasValue(path)) return "#";
    return `../../${String(path).replace(/\\/g, "/")}`;
  }

  function setText(id, value) {
    const node = qs(`#${id}`);
    if (node) node.textContent = value;
  }

  function cleanRows(rows) {
    return (rows || []).filter((row) => {
      if (!row || typeof row !== "object") return false;
      if (Object.prototype.hasOwnProperty.call(row, "value") && !hasValue(row.value)) return false;
      const identity = new Set(["dataset", "model", "metric", "baseline_group", "group", "scenario"]);
      return Object.entries(row).some(([key, value]) => !identity.has(key) && hasValue(value))
        || Object.values(row).some(hasValue);
    });
  }

  function tableColumns(rows) {
    const keys = [];
    rows.forEach((row) => {
      Object.keys(row).forEach((key) => {
        if (!keys.includes(key)) keys.push(key);
      });
    });
    return keys.filter((key) => rows.some((row) => hasValue(row[key])));
  }

  function renderTable(id, rows) {
    const node = qs(`#${id}`);
    if (!node) return;
    const clean = cleanRows(rows);
    if (!clean.length) {
      node.innerHTML = '<div class="empty-state">No output found for this section yet.</div>';
      return;
    }
    const columns = tableColumns(clean);
    if (!columns.length) {
      node.innerHTML = '<div class="empty-state">No populated columns found.</div>';
      return;
    }
    const header = columns.map((column) => `<th>${html(column)}</th>`).join("");
    const body = clean.map((row) => {
      const cells = columns.map((column) => `<td>${html(formatValue(row[column]))}</td>`).join("");
      return `<tr>${cells}</tr>`;
    }).join("");
    node.innerHTML = `<div class="table-wrap"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function renderKeyValueTable(id, value) {
    const rows = Object.entries(value || {}).map(([key, entry]) => ({ setting: key, value: entry }));
    renderTable(id, rows);
  }

  function renderFiles(id, files, limit = 80) {
    const node = qs(`#${id}`);
    if (!node) return;
    const visibleFiles = (files || []).filter((file) => file && file.path).slice(0, limit);
    if (!visibleFiles.length) {
      node.innerHTML = '<div class="empty-state">No files found yet.</div>';
      return;
    }
    node.innerHTML = `<div class="file-list">${visibleFiles.map((file) => {
      const meta = [
        hasValue(file.rows) ? `${file.rows} rows` : "",
        hasValue(file.size) ? formatBytes(file.size) : "",
        file.path || "",
      ].filter(Boolean).join(" | ");
      return `
        <div class="file-row">
          <div>
            <a href="${html(projectHref(file.path))}" target="_blank" rel="noreferrer">${html(file.name || file.path)}</a>
            <small>${html(meta)}</small>
          </div>
          <span class="pill">${html((file.name || "").split(".").pop() || "file")}</span>
        </div>`;
    }).join("")}</div>`;
  }

  function renderDataPreview() {
    const rows = data.data_preview || [];
    if (rows.length) {
      renderTable("dataPreview", rows);
      return;
    }
    renderFiles("dataPreview", data.data_files || [], 20);
  }

  function renderStats() {
    const counts = data.counts || {};
    const summaryRows = data.metrics_summary || [];
    const accuracyRows = summaryRows.filter((row) => row.metric === "Accuracy" && hasValue(row.mean));
    const bestAccuracy = accuracyRows.length
      ? Math.max(...accuracyRows.map((row) => Number(row.mean)).filter(Number.isFinite))
      : null;
    const baseStats = [
      ["Model files", counts.model_files || 0, "Detected under models/"],
      ["Result files", counts.result_files || 0, "Detected under the selected results folder"],
      ["Synthetic sessions", counts.synthetic_session_files || 0, "Saved session CSV files"],
      ["Best accuracy", bestAccuracy === null ? "n/a" : formatValue(bestAccuracy), "Highest Accuracy in metrics_summary.csv"],
    ];
    const syntheticStats = [
      ["Metric rows", counts.metrics_summary_rows || 0, "Rows in metrics_summary.csv"],
      ["Simulation rows", counts.simulation_rows || 0, "Rows in metrics_timeline.csv"],
      ["Log files", counts.log_files || 0, "Detected under logs/"],
      ["Data files", counts.data_files || 0, "Detected under data/"],
    ];
    qs("#overviewStats").innerHTML = baseStats.map(statCard).join("");
    qs("#syntheticStats").innerHTML = syntheticStats.map(statCard).join("");
  }

  function statCard([label, value, note]) {
    return `
      <article class="stat-card">
        <div class="stat-label">${html(label)}</div>
        <div class="stat-value">${html(value)}</div>
        <div class="stat-note">${html(note)}</div>
      </article>`;
  }

  function renderLogs() {
    renderFiles("logFiles", data.logs || [], 50);
    const latest = data.latest_log || {};
    setText("latestLogPill", latest.name || "no log found");
    const tail = qs("#latestLogTail");
    if (tail) tail.textContent = (data.latest_log_tail || []).join("\n") || "No log preview available.";
  }

  function renderMedia() {
    const visuals = data.simulation_visuals || [];
    const images = visuals.filter((item) => /\.(png|jpg|jpeg|svg)$/i.test(item.name || ""));
    const videos = visuals.filter((item) => /\.(gif|mp4|webm)$/i.test(item.name || ""));
    renderMediaGroup("simulationImages", images, "image");
    renderMediaGroup("simulationVideo", videos, "video");
  }

  function renderMediaGroup(id, files, mode) {
    const node = qs(`#${id}`);
    if (!node) return;
    if (!files.length) {
      node.innerHTML = '<div class="empty-state">No media generated yet.</div>';
      return;
    }
    node.innerHTML = files.map((file) => {
      const src = html(projectHref(file.path));
      const name = html(file.name || file.path);
      const isVideo = mode === "video" && /\.(mp4|webm)$/i.test(file.name || "");
      return `
        <figure class="media-item">
          ${isVideo ? `<video controls src="${src}"></video>` : `<img src="${src}" alt="${name}">`}
          <figcaption><a href="${src}" target="_blank" rel="noreferrer">${name}</a></figcaption>
        </figure>`;
    }).join("");
  }

  function renderCharts() {
    drawLineChart("chartAccuracy", data.simulation_timeline || [], "Accuracy");
    drawLineChart("chartF1", data.simulation_timeline || [], "F1-score");
    drawLineChart("chartJsd", data.simulation_timeline || [], "JSD");
    drawLineChart("chartWasserstein", data.simulation_timeline || [], "Wasserstein");
  }

  function drawLineChart(id, rows, metric) {
    const node = qs(`#${id}`);
    if (!node) return;
    const points = (rows || [])
      .filter((row) => hasValue(row.step) && hasValue(row[metric]) && numberLike(row[metric]))
      .map((row) => ({
        x: Number(row.step),
        y: Number(row[metric]),
        model: row.model || "",
      }));
    if (!points.length) {
      node.innerHTML = '<div class="empty-state">No simulation values found.</div>';
      return;
    }

    const width = 640;
    const height = 260;
    const pad = 42;
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y), 0);
    const maxY = Math.max(...points.map((point) => point.y), 1);
    const scaleX = (value) => pad + ((value - minX) / Math.max(maxX - minX, 1)) * (width - pad * 2);
    const scaleY = (value) => height - pad - ((value - minY) / Math.max(maxY - minY, 0.0001)) * (height - pad * 2);
    const grouped = points.reduce((acc, point) => {
      acc[point.model] = acc[point.model] || [];
      acc[point.model].push(point);
      return acc;
    }, {});
    const lines = Object.values(grouped).map((group) => {
      const sorted = group.sort((a, b) => a.x - b.x);
      const path = sorted.map((point, index) => `${index ? "L" : "M"} ${scaleX(point.x).toFixed(2)} ${scaleY(point.y).toFixed(2)}`).join(" ");
      const dots = sorted.map((point) => `<circle class="point" cx="${scaleX(point.x).toFixed(2)}" cy="${scaleY(point.y).toFixed(2)}" r="4"><title>${html(point.model)} step ${point.x}: ${formatValue(point.y)}</title></circle>`).join("");
      return `<path class="line" d="${path}"></path>${dots}`;
    }).join("");
    node.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${html(metric)} simulation chart">
        <line class="axis-line" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#666"></line>
        <line class="axis-line" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" stroke="#666"></line>
        <text class="axis" x="${pad}" y="${height - 12}">step ${formatValue(minX)}</text>
        <text class="axis" x="${width - pad - 48}" y="${height - 12}">step ${formatValue(maxX)}</text>
        <text class="axis" x="8" y="${pad + 4}">${formatValue(maxY)}</text>
        <text class="axis" x="8" y="${height - pad + 4}">${formatValue(minY)}</text>
        ${lines}
      </svg>`;
  }

  function wireTabs(selector, targetPrefix, attr) {
    qsa(selector).forEach((button) => {
      button.addEventListener("click", () => {
        const value = button.dataset[attr];
        const group = button.parentElement;
        qsa(".tab", group).forEach((tab) => tab.classList.remove("active"));
        button.classList.add("active");
        qsa(`[id^="${targetPrefix}-"]`).forEach((panel) => panel.classList.remove("active"));
        const panel = qs(`#${targetPrefix}-${value}`);
        if (panel) panel.classList.add("active");
      });
    });
  }

  function wireNavigation() {
    qsa("[data-section]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.section;
        qsa("[data-section]").forEach((nav) => nav.classList.remove("active"));
        qsa(".page-section").forEach((section) => section.classList.remove("active"));
        button.classList.add("active");
        const section = qs(`#${id}`);
        if (section) section.classList.add("active");
      });
    });

    const toggle = qs("#sidebarToggle");
    if (toggle) {
      toggle.addEventListener("click", () => qs("#appShell").classList.toggle("sidebar-collapsed"));
    }

    wireTabs(".main-tabs .tab", "tab", "tab");
    wireTabs("[data-metric-tab]", "metric", "metricTab");
    wireTabs("[data-simulation-tab]", "simulation", "simulationTab");
  }

  function renderAll() {
    renderStats();
    renderKeyValueTable("configTable", data.config || {});
    renderDataPreview();
    renderFiles("sessionFiles", data.synthetic_sessions || [], 20);
    renderFiles("resultFilesCompact", data.result_files || [], 12);
    renderFiles("resultFiles", data.result_files || [], 120);
    renderFiles("modelFiles", data.model_files || [], 120);
    renderFiles("simulationFiles", data.simulation_files || [], 120);
    renderLogs();
    renderTable("metricsSummary", data.metrics_summary || []);
    renderTable("baselineMetrics", data.real_baselines || []);
    renderTable("featureDependence", data.feature_dependence || []);
    renderTable("statisticalSimilarity", data.statistical_similarity || []);
    renderTable("privacyMetrics", data.privacy || []);
    renderTable("utilityMetrics", data.utility || []);
    renderTable("metricMetadata", metricMetadata);
    renderTable("simulationSummary", data.simulation_summary || []);
    renderTable("simulationTimeline", data.simulation_timeline || []);
    renderCharts();
    renderMedia();
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireNavigation();
    renderAll();
  });
}());
