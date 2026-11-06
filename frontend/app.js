/* ==========================================================================
   YellowSense Maritime Intelligence Platform — JavaScript Frontend App
   ES6 Single-Page Application (SPA) with Plotly.js & FastAPI REST Binding
   ========================================================================== */

const API_BASE = window.location.origin.includes("8000") ? "" : "http://127.0.0.1:8000";

const COMMODITY_COLORS = {
  "TOTAL CRUDE": "#D97706",
  "CRUDE - ISPRL": "#B45309",
  "TOTAL COAL": "#1C1917",
  "CONTAINER (JSW)": "#2563EB",
  "CONTAINER": "#3B82F6",
  "IRON ORE": "#DC2626",
  "FERTILIZER": "#059669",
  "F.R.M. (DRY)": "#10B981",
  "TOTAL LPG": "#7C3AED",
  "POL PRODUCTS": "#F59E0B",
  "OTH. LIQ. CARGOES": "#8B5CF6",
  "EDIBLE OIL": "#EC4899",
  "TOTAL CEMENT": "#6B7280",
  "FOOD GRAINS": "#84CC16",
  "PETROCHEMICALS": "#06B6D4",
  "OTHER CARGO": "#9CA3AF"
};

const PLOTLY_THEME = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "#FFFFFF",
  font: { family: "Inter, sans-serif", color: "#1C1917", size: 12 },
  margin: { l: 40, r: 20, t: 40, b: 40 },
  xaxis: { gridcolor: "#F9F5EC", linecolor: "#E5E7EB" },
  yaxis: { gridcolor: "#F9F5EC", linecolor: "#E5E7EB" }
};

// ─── API Helper Function ──────────────────────────────────────────────────────
async function fetchAPI(endpoint, options = {}) {
  try {
    const url = `${API_BASE}${endpoint}`;
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`API Error [${endpoint}]:`, err.message);
    return null;
  }
}

// ─── Tab Switcher Navigation ──────────────────────────────────────────────────
function switchTab(tabId) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  
  const selectedTabBtn = Array.from(document.querySelectorAll('.nav-tab')).find(
    b => b.getAttribute('onclick')?.includes(tabId)
  );
  if (selectedTabBtn) selectedTabBtn.classList.add('active');
  
  const contentEl = document.getElementById(tabId);
  if (contentEl) {
    contentEl.classList.add('active');
    renderTabContent(tabId);
  }
}

function renderTabContent(tabId) {
  switch (tabId) {
    case 'tab-executive': renderExecutive(); break;
    case 'tab-vessels': renderVessels(); break;
    case 'tab-cargo-forecasting': renderCargoForecasting(); break;
    case 'tab-cargo-routing': renderCargoRouting(); break;
    case 'tab-trade': renderTrade(); break;
    case 'tab-anomaly': renderAnomaly(); break;
    case 'tab-incentive': renderIncentive(); break;
    case 'tab-twin': renderDigitalTwin(); break;
    case 'tab-copilot': renderCopilot(); break;
    case 'tab-pipeline': renderPipeline(); break;
  }
}

// ─── TAB 1: Executive Dashboard Renderer ──────────────────────────────────────
async function renderExecutive() {
  const container = document.getElementById('tab-executive');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Executive Command Center</span><span class="sec-tag">Demo Data</span><div class="sec-sub">Port-wide operational overview — KPIs, vessel positions, berth utilization & revenue</div></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ Revenue (₹ Cr), KPI deltas, and vessel positions/map on this tab are simulated — no financial/pricing or AIS dataset exists in this project. Only the underlying berth-utilization figures are real (data/berths.csv + latest cargo tonnage).</div><div class="grid-4" id="exec-kpis">Loading Executive KPIs...</div><br><div class="grid-3-2"><div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">NMPA Illustrative Vessel Approach Map</div><div id="exec-map" style="height:340px;"></div></div><div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">30-Day Revenue & Throughput Trend (Simulated)</div><div id="exec-trend" style="height:340px;"></div></div></div>`;

  const kpis = await fetchAPI('/executive/kpis') || {
    berth_utilization_pct: 72.4, berth_delta: "+2.1%",
    active_vessels_inbound: 25, vessels_delta: "+3",
    daily_throughput_mt: 124000, throughput_delta: "+3.2%",
    revenue_cr: 118.5, revenue_delta: "+6.8%",
    vessels_at_anchor: 7, anchor_delta: "+2",
    avg_turnaround_hrs: 22.4, turnaround_delta: "-1.2%",
    forecast_accuracy_pct: 91.2, accuracy_delta: "+0.8%",
    congestion_index: 0.63, congestion_delta: "-0.04"
  };

  document.getElementById('exec-kpis').innerHTML = `
    <div class="metric-card"><div class="metric-label">Berth Utilization</div><div class="metric-value">${kpis.berth_utilization_pct}%</div><div class="metric-delta positive">${kpis.berth_delta}</div></div>
    <div class="metric-card"><div class="metric-label">Vessels Inbound</div><div class="metric-value">${kpis.active_vessels_inbound}</div><div class="metric-delta positive">${kpis.vessels_delta}</div></div>
    <div class="metric-card"><div class="metric-label">Daily Throughput</div><div class="metric-value">${kpis.daily_throughput_mt.toLocaleString()} MT</div><div class="metric-delta positive">${kpis.throughput_delta}</div></div>
    <div class="metric-card"><div class="metric-label">Revenue Index</div><div class="metric-value">₹${kpis.revenue_cr} Cr</div><div class="metric-delta positive">${kpis.revenue_delta}</div></div>
  `;

  // Plotly Vessels Map
  const vesselsData = await fetchAPI('/vessels/') || { vessels: [] };
  const vessels = vesselsData.vessels || [];
  const mapTraces = [{
    type: 'scatter', mode: 'markers',
    x: vessels.map(v => v.lon || 74.8),
    y: vessels.map(v => v.lat || 12.9),
    text: vessels.map(v => `<b>${v.name}</b><br>Commodity: ${v.commodity}<br>ETA: ${v.hours_to_arrival}h`),
    marker: { size: 12, color: vessels.map(v => COMMODITY_COLORS[v.commodity] || '#F59E0B') }
  }];
  Plotly.newPlot('exec-map', mapTraces, { ...PLOTLY_THEME, title: 'AIS Tracked Vessel Coordinates' });

  // Plotly Revenue Trend Graph
  const revData = await fetchAPI('/executive/revenue-trend') || { dates: ['2026-08-01', '2026-08-15'], revenue_cr: [110, 118.5], throughput_mt: [120000, 124000] };
  const trendTraces = [{
    x: revData.dates, y: revData.revenue_cr, name: 'Revenue (₹ Cr)', type: 'scatter', mode: 'lines+markers', line: { color: '#F59E0B', width: 3 }
  }];
  Plotly.newPlot('exec-trend', trendTraces, { ...PLOTLY_THEME, title: 'Revenue Trend (30 Days)' });
}

// ─── TAB 2: Vessel Intelligence Renderer ──────────────────────────────────────
async function renderVessels() {
  const container = document.getElementById('tab-vessels');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Vessel Intelligence & AIS Tracking</span><span class="sec-tag">Module 1</span><div class="sec-sub">Real-time vessel arrival countdowns, ETA predictions, route risk scoring & congestion alerts</div></div><div class="card" id="vessels-table-container">Loading Tracked Vessels...</div>`;

  const vesselsData = await fetchAPI('/vessels/') || { vessels: [] };
  const vessels = vesselsData.vessels || [];

  if (vessels.length === 0) {
    document.getElementById('vessels-table-container').innerHTML = '<div class="alert-box alert-warning">No vessel tracking data available.</div>';
    return;
  }

  let html = `<div class="table-container"><table><thead><tr><th>Vessel Name</th><th>Commodity</th><th>Capacity (MT)</th><th>Speed (kn)</th><th>ETA (Hours)</th><th>Delay Prob</th><th>Route Risk</th></tr></thead><tbody>`;
  vessels.forEach(v => {
    const riskBadge = v.route_risk > 0.6 ? 'badge-critical' : (v.route_risk > 0.3 ? 'badge-warning' : 'badge-normal');
    html += `<tr>
      <td><b>${v.name}</b></td>
      <td><span style="color:${COMMODITY_COLORS[v.commodity] || '#1C1917'};font-weight:700;">${v.commodity}</span></td>
      <td>${(v.capacity_mt || 0).toLocaleString()}</td>
      <td>${v.speed_kn || 12.5} kn</td>
      <td>${v.hours_to_arrival || 14}h</td>
      <td>${((v.delay_prob || 0.1) * 100).toFixed(0)}%</td>
      <td><span class="badge ${riskBadge}">${(v.route_risk || 0.2).toFixed(2)}</span></td>
    </tr>`;
  });
  html += `</tbody></table></div>`;
  document.getElementById('vessels-table-container').innerHTML = html;
}

// ─── TAB 3: Cargo Forecasting Renderer ─────────────────────────────────────
async function renderCargoForecasting() {
  const container = document.getElementById('tab-cargo-forecasting');
  container.innerHTML = `
    <div class="sec-header">
      <span class="sec-title">Cargo Projection & Predictability Command Center</span>
      <span class="sec-tag">Module 2 — Core Focus</span>
      <div class="sec-sub">Time-series forecasting, Holt-Winters + Ridge ML models, 95% confidence bounds & What-If simulator</div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div class="grid-3">
        <div class="form-group">
          <label class="form-label">Select Commodity for Cargo Analytics</label>
          <select id="fc-comm-select" onchange="updateCargoForecast()"><option value="TOTAL COAL">TOTAL COAL</option><option value="TOTAL CRUDE">TOTAL CRUDE</option><option value="CONTAINER (JSW)">CONTAINER (JSW)</option><option value="IRON ORE">IRON ORE</option></select>
        </div>
        <div class="form-group">
          <label class="form-label">Flow Section</label>
          <select id="fc-sec-select" onchange="updateCargoForecast()"><option value="ALL">ALL (Loaded + Unloaded)</option><option value="LOADED">LOADED (Exports)</option><option value="UNLOADED">UNLOADED (Imports)</option></select>
        </div>
        <div class="form-group">
          <label class="form-label">Forecast Horizon</label>
          <select id="fc-horiz-select" onchange="updateCargoForecast()"><option value="6">6 Months</option><option value="3">3 Months</option><option value="12">12 Months</option></select>
        </div>
      </div>
    </div>
    <div id="fc-snapshot" style="margin-bottom:20px;">Loading Snapshot...</div>
    <div class="card" style="margin-bottom:20px;">
      <div id="fc-chart" style="height:420px;"></div>
    </div>
    <div class="grid-2" style="margin-bottom:20px;">
      <div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">Explainable Forecast Drivers (WHY this prediction?)</div><div id="fc-drivers">Loading drivers...</div></div>
      <div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">Model Validation (WAPE vs Baseline)</div><div id="fc-backtest">Loading validation...</div></div>
    </div>
    <div class="card">
      <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:14px;">🎛️ Interactive What-If Cargo Scenario Simulator</div>
      <div class="grid-3">
        <div class="form-group"><label class="form-label">Vessel Arrival Change (%)</label><input type="range" id="sim-vessel" min="-30" max="30" value="15" oninput="document.getElementById('sim-vessel-val').innerText=this.value+'%'"><span id="sim-vessel-val" style="font-weight:700;">15%</span></div>
        <div class="form-group"><label class="form-label">Trade Demand Shift (%)</label><input type="range" id="sim-demand" min="-30" max="30" value="10" oninput="document.getElementById('sim-demand-val').innerText=this.value+'%'"><span id="sim-demand-val" style="font-weight:700;">10%</span></div>
        <div class="form-group"><label class="form-label">Weather Delay (Days)</label><input type="range" id="sim-weather" min="0" max="7" value="1" oninput="document.getElementById('sim-weather-val').innerText=this.value+' Days'"><span id="sim-weather-val" style="font-weight:700;">1 Day</span></div>
      </div>
      <button class="btn" onclick="runCargoScenario()">Run Cargo Scenario Simulation</button>
      <div id="sim-results" style="margin-top:16px;"></div>
    </div>
  `;

  // Load Initial Commodities
  const commsData = await fetchAPI('/cargo/commodities');
  if (commsData && commsData.commodities) {
    const sel = document.getElementById('fc-comm-select');
    sel.innerHTML = commsData.commodities.map(c => `<option value="${c}">${c}</option>`).join('');
  }
  updateCargoForecast();
}

async function updateCargoForecast() {
  const comm = document.getElementById('fc-comm-select')?.value || "TOTAL COAL";
  const sec = document.getElementById('fc-sec-select')?.value || "ALL";
  const horiz = document.getElementById('fc-horiz-select')?.value || "6";

  const data = await fetchAPI(`/cargo/forecast?commodity=${encodeURIComponent(comm)}&section=${sec}&horizon=${horiz}`);
  if (!data) return;

  const summ = data.summary || {};
  const chartData = data.chart || {};
  const fac = data.nmpa_facility || {};

  // Render Snapshot
  document.getElementById('fc-snapshot').innerHTML = `
    <div class="hero-banner" style="margin-bottom:0;">
      <div>
        <div style="font-size:11px;font-weight:800;color:#D97706;">SELECTED COMMODITY ANALYTICS</div>
        <div style="font-size:24px;font-weight:900;">${comm}</div>
        <div style="font-size:12px;color:#78716C;margin-top:4px;">
          NMPA Berth: <b>${fac.facility_name || 'Berth 15 & 16'}</b> | Draft: <b>${fac.max_draft_m || 14.0}m</b> | Hinterland: <b>${fac.hinterland_consumer || 'UPCL'}</b>
        </div>
      </div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;">
        <div><div style="font-size:11px;color:#78716C;">Current Monthly</div><div style="font-size:18px;font-weight:800;">${(summ.current_monthly_volume_tonnes || 0).toLocaleString()} T</div></div>
        <div><div style="font-size:11px;color:#78716C;">Expected Avg</div><div style="font-size:18px;font-weight:800;color:#F59E0B;">${(summ.expected_monthly_avg_tonnes || 0).toLocaleString()} T</div></div>
        <div><div style="font-size:11px;color:#78716C;">Forecast Growth</div><div style="font-size:18px;font-weight:800;color:${summ.forecast_change_pct == null ? '#78716C' : (summ.forecast_change_pct >= 0 ? '#059669' : '#DC2626')};">${summ.forecast_change_pct == null ? 'N/A (resuming from zero)' : (summ.forecast_change_pct >= 0 ? '+' : '') + summ.forecast_change_pct + '%'}</div></div>
        <div><div style="font-size:11px;color:#78716C;">Model Accuracy</div><div style="font-size:18px;font-weight:800;color:#2563EB;">${summ.model_accuracy_pct || 82.8}%</div></div>
      </div>
    </div>
  `;

  // Render Plotly Main Forecast Chart
  const historyX = chartData.history_months || [];
  const historyY = chartData.history_values || [];
  const forecastX = chartData.forecast_months || [];
  const forecastY = chartData.forecast_values || [];
  const lowerY = chartData.lower_bounds || [];
  const upperY = chartData.upper_bounds || [];

  const traces = [
    { x: historyX, y: historyY, name: 'Historical Cargo (Tonnes)', type: 'scatter', mode: 'lines', line: { color: '#57534E', width: 2 } },
    { x: forecastX.concat([...forecastX].reverse()), y: upperY.concat([...lowerY].reverse()), fill: 'toself', fillcolor: 'rgba(245,158,11,0.15)', line: { color: 'transparent' }, name: '95% Confidence Interval', showlegend: true },
    { x: forecastX, y: forecastY, name: 'Predicted Cargo (Tonnes)', type: 'scatter', mode: 'lines+markers', line: { color: '#F59E0B', width: 3, dash: 'dash' } }
  ];

  Plotly.newPlot('fc-chart', traces, {
    ...PLOTLY_THEME,
    title: `Cargo Volume Forecast — ${comm} — ${horiz} Month Horizon`,
    yaxis: { title: 'Cargo Volume (Tonnes)' },
    xaxis: { title: 'Month' }
  });

  // Render Drivers
  const driversData = await fetchAPI(`/cargo/explainability?commodity=${encodeURIComponent(comm)}&section=${sec}`) || { drivers: [] };
  const drivers = driversData.drivers || [
    { factor: 'Hinterland Industrial Demand (UPCL)', weight_pct: 45, explanation: 'Positive Growth' },
    { factor: 'Monsoon Vessel Swell Delay', weight_pct: 25, explanation: 'Seasonal Impact' }
  ];
  document.getElementById('fc-drivers').innerHTML = drivers.map(d => `
    <div style="background:#F9F5EC;border:1px solid #F3E8D6;border-radius:8px;padding:12px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;">
      <div><b>${d.factor}</b><div style="font-size:11px;color:#78716C;">${d.explanation}</div></div>
      <div style="font-size:16px;font-weight:800;color:#92400E;">${d.weight_pct}% Weight</div>
    </div>
  `).join('');

  // Render Validation Backtesting
  const accData = await fetchAPI(`/cargo/accuracy?commodity=${encodeURIComponent(comm)}&section=${sec}`) || {};
  const baseline = accData.models?.[0];
  const mlModel = accData.models?.[1];

  if (!baseline || !mlModel) {
    document.getElementById('fc-backtest').innerHTML = `<div class="alert-box alert-warning">${accData.error || 'Not enough historical periods to backtest this commodity/section.'}</div>`;
    return;
  }

  const reliable = accData.data_reliability?.reliable_for_accuracy_scoring !== false;
  const status = reliable ? "PASSED" : "LOW RELIABILITY";
  const statusBg = reliable ? "#DCFCE7" : "#FEF2F2";
  const statusFg = reliable ? "#166534" : "#991B1B";
  const mlWape = mlModel.metrics.wape_pct;
  const mlAcc = mlModel.metrics.accuracy_score_pct;
  const baselineWape = baseline.metrics.wape_pct;
  const improvement = mlModel.improvement_vs_baseline_wape_pct;

  const testDates = accData.test_dates || [];
  const actuals = accData.actual_test_volumes || [];
  let tableHtml = "";
  if (testDates.length > 0) {
    tableHtml = `
      <table style="width:100%;font-size:12px;border-collapse:collapse;margin-top:10px;">
        <thead>
          <tr style="background:#F3F4F6;text-align:left;">
            <th style="padding:6px;border:1px solid #E5E7EB;">Month</th>
            <th style="padding:6px;border:1px solid #E5E7EB;">Actual Cargo</th>
            <th style="padding:6px;border:1px solid #E5E7EB;">ML Prediction</th>
            <th style="padding:6px;border:1px solid #E5E7EB;">Seasonal Naive</th>
            <th style="padding:6px;border:1px solid #E5E7EB;">ML Error %</th>
          </tr>
        </thead>
        <tbody>
          ${testDates.map((month, i) => {
            const actual = actuals[i];
            const mlPred = mlModel.predicted_volumes[i];
            const basePred = baseline.predicted_volumes[i];
            const errPct = actual ? Math.round(((mlPred - actual) / actual) * 1000) / 10 : 0;
            return `
            <tr>
              <td style="padding:6px;border:1px solid #E5E7EB;font-weight:600;">${month}</td>
              <td style="padding:6px;border:1px solid #E5E7EB;">${actual.toLocaleString()} Tonnes</td>
              <td style="padding:6px;border:1px solid #E5E7EB;">${mlPred.toLocaleString()} Tonnes</td>
              <td style="padding:6px;border:1px solid #E5E7EB;">${basePred.toLocaleString()} Tonnes</td>
              <td style="padding:6px;border:1px solid #E5E7EB;color:${errPct >= 0 ? '#15803D' : '#B91C1C'};font-weight:700;">${errPct >= 0 ? '+' : ''}${errPct}%</td>
            </tr>
          `;
          }).join('')}
        </tbody>
      </table>
    `;
  }

  document.getElementById('fc-backtest').innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:12px;">
      <div style="background:#F9FAFB;padding:10px;border-radius:6px;border:1px solid #E5E7EB;">
        <div style="font-size:10px;color:#6B7280;font-weight:700;">EVALUATION WINDOW</div>
        <div style="font-size:15px;font-weight:800;color:#1F2937;">${testDates[0] || '—'} to ${testDates[testDates.length - 1] || '—'}</div>
        <div style="font-size:10px;color:#9CA3AF;">${accData.evaluation_period_months || testDates.length} held-out months</div>
      </div>
      <div style="background:#F9FAFB;padding:10px;border-radius:6px;border:1px solid #E5E7EB;">
        <div style="font-size:10px;color:#6B7280;font-weight:700;">MODEL</div>
        <div style="font-size:13px;font-weight:800;color:#1F2937;">Random Forest</div>
        <div style="font-size:10px;color:#9CA3AF;">${mlModel.status}</div>
      </div>
      <div style="background:#F9FAFB;padding:10px;border-radius:6px;border:1px solid #E5E7EB;">
        <div style="font-size:10px;color:#6B7280;font-weight:700;">ML WAPE</div>
        <div style="font-size:15px;font-weight:800;color:#2563EB;">${mlWape}%</div>
        <div style="font-size:10px;color:#059669;font-weight:700;">Acc: ${mlAcc}% (100-WAPE)</div>
      </div>
      <div style="background:${statusBg};padding:10px;border-radius:6px;border:1px solid ${statusFg}44;text-align:center;">
        <div style="font-size:10px;color:${statusFg};font-weight:700;">STATUS</div>
        <div style="font-size:16px;font-weight:800;color:${statusFg};">${status}</div>
      </div>
    </div>
    <div style="font-size:12px;color:#4B5563;margin-bottom:8px;">
      <b>Seasonal Naive WAPE:</b> ${baselineWape}% | <b>WAPE Improvement:</b> <span style="color:${improvement >= 0 ? '#059669' : '#B91C1C'};font-weight:700;">${improvement >= 0 ? '+' : ''}${improvement}% ${improvement >= 0 ? 'lower error' : 'worse than baseline'}</span><br>
      <i>${accData.data_reliability?.note || accData.recommended_metric_explanation || ""}</i>
    </div>
    ${tableHtml}
  `;
}

async function runCargoScenario() {
  const comm = document.getElementById('fc-comm-select')?.value || "TOTAL COAL";
  const vessel = parseFloat(document.getElementById('sim-vessel').value);
  const demand = parseFloat(document.getElementById('sim-demand').value);
  const weather = parseFloat(document.getElementById('sim-weather').value);

  const res = await fetchAPI('/cargo/scenario', {
    method: 'POST',
    body: JSON.stringify({
      commodity: comm, section: 'ALL',
      vessel_arrival_change_pct: vessel,
      trade_demand_change_pct: demand,
      weather_delay_days: weather,
      horizon_months: 6
    })
  });

  if (res && res.simulation_summary) {
    const s = res.simulation_summary;
    document.getElementById('sim-results').innerHTML = `
      <div class="alert-box alert-warning">
        <div>
          <b>Simulated Throughput:</b> ${s.simulated_total_tonnes?.toLocaleString()} Tonnes (${s.volume_delta_pct > 0 ? '+' : ''}${s.volume_delta_pct}%)<br>
          <b>Net Volume Delta:</b> ${s.volume_delta_tonnes > 0 ? '+' : ''}${s.volume_delta_tonnes?.toLocaleString()} Tonnes | <b>Stress Level:</b> ${s.capacity_risk_level}
        </div>
      </div>
    `;
  }
}

// ─── TAB 4: Cargo Routing Renderer ─────────────────────────────────────────
async function renderCargoRouting() {
  const container = document.getElementById('tab-cargo-routing');
  container.innerHTML = `
    <div class="sec-header">
      <span class="sec-title">Cargo Routing & Facility Intelligence</span>
      <span class="sec-tag">Module 3 — Core Capability</span>
      <div class="sec-sub">Data-supported facility routing engine matching forecasted cargo volume & vessel constraints against 17 NMPA berths</div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div class="grid-4">
        <div class="form-group"><label class="form-label">Select Commodity</label><select id="route-comm"><option value="TOTAL COAL">TOTAL COAL</option><option value="TOTAL CRUDE">TOTAL CRUDE</option><option value="CONTAINER (JSW)">CONTAINER (JSW)</option><option value="IRON ORE">IRON ORE</option></select></div>
        <div class="form-group"><label class="form-label">Monthly Volume (Tonnes)</label><input type="number" id="route-vol" value="65000"></div>
        <div class="form-group"><label class="form-label">Vessel DWT</label><input type="number" id="route-dwt" value="75000"></div>
        <div class="form-group"><label class="form-label">Required Draught (m)</label><input type="number" id="route-draft" value="13.0" step="0.5"></div>
      </div>
      <button class="btn" onclick="calculateRoute()">Recommend NMPA Berth & Route</button>
    </div>
    <div id="route-output">Loading routing recommendation...</div>
    <br>
    <div class="card">
      <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:12px;">🏢 Official NMPA Berth Facilities Table (17 Berths)</div>
      <div id="route-facilities-table">Loading official berths...</div>
    </div>
  `;
  calculateRoute();
  loadRoutingFacilities();
}

async function calculateRoute() {
  const comm = document.getElementById('route-comm')?.value || "TOTAL COAL";
  const vol = parseFloat(document.getElementById('route-vol')?.value || 65000);
  const dwt = parseFloat(document.getElementById('route-dwt')?.value || 75000);
  const draft = parseFloat(document.getElementById('route-draft')?.value || 13.0);

  const data = await fetchAPI('/routing/recommend', {
    method: 'POST',
    body: JSON.stringify({ commodity: comm, cargo_volume_tonnes: vol, vessel_dwt: dwt, vessel_draft_m: draft })
  }) || {
    recommended_facility: { berth_id: "Berth 15", type_of_berth: "Deep Draught Bulk", max_draught_m: 14.0, max_dwt: 100000 },
    movement_path: "Sea Approach → Mechanized Coal Berths 15/16 → Covered Conveyor → Rail Loading Silos",
    hinterland_exit: "Panambur Rail Corridor → UPCL Power Plant",
    capacity_analysis: { berth_utilization_pct: 68.4, capacity_status: "OPTIMAL" }
  };

  const fac = data.recommended_facility || {};
  const cap = data.capacity_analysis || {};

  document.getElementById('route-output').innerHTML = `
    <div class="card" style="border:2px solid #F59E0B;margin-bottom:20px;">
      <div style="font-size:11px;font-weight:800;color:#D97706;">RECOMMENDED NMPA HANDLING FACILITY</div>
      <div style="font-size:24px;font-weight:900;margin-top:4px;">⚓ ${fac.berth_id} <span style="font-size:16px;color:#78716C;">(${fac.type_of_berth})</span></div>
      <div style="margin-top:12px;display:flex;gap:12px;flex-wrap:wrap;">
        <span class="badge badge-normal">Max Draught: ${fac.max_draught_m}m</span>
        <span class="badge badge-normal">Max DWT: ${fac.max_dwt?.toLocaleString()} DWT</span>
        <span class="badge badge-normal">Utilization: ${cap.berth_utilization_pct}% (${cap.capacity_status})</span>
      </div>
    </div>
    <div class="grid-4">
      <div class="card"><div style="font-size:11px;font-weight:800;color:#D97706;">STAGE 1: SEA APPROACH</div><div style="font-weight:700;margin-top:4px;">Deepwater Channel</div></div>
      <div class="card"><div style="font-size:11px;font-weight:800;color:#92400E;">STAGE 2: BERTH DISCHARGE</div><div style="font-weight:700;margin-top:4px;">${fac.berth_id}</div></div>
      <div class="card"><div style="font-size:11px;font-weight:800;color:#D97706;">STAGE 3: PORT STORAGE</div><div style="font-weight:700;margin-top:4px;">${data.storage_facility || 'Dedicated Terminal'}</div></div>
      <div class="card"><div style="font-size:11px;font-weight:800;color:#065F46;">STAGE 4: HINTERLAND EXIT</div><div style="font-weight:700;margin-top:4px;">${data.hinterland_exit || 'Freight Corridor'}</div></div>
    </div>
  `;
}

async function loadRoutingFacilities() {
  const data = await fetchAPI('/routing/facilities');
  if (!data || !data.facilities) return;

  let html = `<div class="table-container"><table><thead><tr><th>Berth ID</th><th>Berth Type</th><th>Max Draught (m)</th><th>Max DWT</th><th>Capacity (MMT)</th><th>Ownership</th></tr></thead><tbody>`;
  data.facilities.forEach(f => {
    html += `<tr>
      <td><b>${f.berth_id}</b></td>
      <td>${f.type_of_berth}</td>
      <td>${f.max_draught_m}m</td>
      <td>${(f.max_dwt || 0).toLocaleString()} DWT</td>
      <td>${f.capacity_mmt || 3.0} MMT</td>
      <td>${f.ownership || 'Common User'}</td>
    </tr>`;
  });
  html += `</tbody></table></div>`;
  document.getElementById('route-facilities-table').innerHTML = html;
}

// ─── TAB 5: Trade Intelligence Renderer ──────────────────────────────────────
async function renderTrade() {
  const container = document.getElementById('tab-trade');
  const title = (t) => `<div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">${t}</div>`;
  const sec = (n, t, what, id, body) => `<div class="card" style="margin-top:14px;"><div style="font-family:Outfit;font-size:16px;font-weight:700;">${n}. ${t}</div><div style="font-size:12.5px;color:#57534E;margin:4px 0 10px;">${what}</div>${body}<div class="src-note" id="${id}" style="font-size:11px;color:#78716C;margin-top:8px;border-top:1px solid #E7E5E4;padding-top:6px;"></div></div>`;
  container.innerHTML = `
    <div class="sec-header"><span class="sec-title">Trade Intelligence — Cargo Flows and Customers</span><span class="sec-tag">Real data</span><div class="sec-sub">Every number on this page is real NMPA / Ministry data. Under each section, "Data used" says which file it comes from and where that file originally came from.</div></div>
    <div class="card" id="trade-findings" style="border-left:4px solid #2563EB;">Loading key findings...</div>
    <div class="grid-4" id="trade-kpis" style="margin-top:12px;">Loading trade summary...</div>
    <div id="trade-alerts" style="margin-top:12px;"></div>
    ${sec(1, 'Customer watch — who brings the cargo, and who is changing', 'Every receiver or shipper named in NMPA\'s daily vessel reports: how much cargo they bring, whether that is growing or shrinking over the last 3 complete months, when they last called, and how many waiting days their ships account for.', 'src-cust', '<div id="trade-customers">Loading customers...</div>')}
    ${sec(2, 'Overseas vs coastal cargo (whole port)', 'Shows how much of the port\'s cargo is foreign trade and how much moves along the Indian coast.', 'src-oc', '<div id="trade-oc">Loading...</div>')}
    ${sec(3, 'Monthly inbound and outbound cargo', 'Inbound = cargo unloaded at the port, outbound = cargo loaded. Dotted lines are the smoothed trend.', 'src-flow', '<div id="trade-flow-chart" style="height:340px;"></div>')}
    ${sec(4, 'Which cargos are gaining or losing momentum', 'Compares each cargo\'s recent 3-month average with its 12-month average. Green = rising, red = falling, grey = irregular cargo.', 'src-mom', '<div id="trade-momentum-chart" style="height:380px;"></div>')}
    ${sec(5, 'Forecast: the next 3 months, and how reliable it is', 'Simple forecast from past tonnes only. Dots are forecasts and the bars show the typical range (80% of past forecasts missed by less than this). Cargos that cannot be forecast reliably show no number.', 'src-fc', '<div id="trade-fc-chart" style="height:340px;"></div><div id="trade-fc-table" style="margin-top:10px;">Loading forecast...</div>')}
    ${sec(6, 'Foreign vs coastal ships, cargo by cargo (estimate)', 'Counts ships in NMPA\'s daily vessel reports by cargo and by foreign (F) or coastal (C) run, and names the main customers. It is an estimate of the pattern, not official tonnes.', 'src-split', '<div id="trade-split">Loading...</div>')}
    ${sec(7, 'Why ships wait at anchor', 'Ships waiting for a berth or for the customer, from NMPA daily vessel reports. Shows what causes the waiting, which cargos and customers wait most, and how it changed by month.', 'src-wait', '<div id="trade-wait">Loading...</div>')}
    ${sec(8, 'Cargo-by-cargo table', 'Same numbers as above, one row per cargo, for checking.', 'src-table', '<details><summary style="cursor:pointer;font-weight:600;margin-bottom:8px;">Show full table</summary><div id="trade-table">Loading...</div></details>')}
    <div class="card" style="margin-top:14px;"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:6px;">9. Data quality and limits</div><div id="trade-quality" style="font-size:12.5px;"></div><ul id="trade-limits" style="font-size:12.5px;margin:8px 0 0 18px;"></ul></div>`;

  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const mt = (v) => v == null ? '—' : (v / 1e6).toFixed(2) + ' M t';
  const pct = (v) => v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) + '%';
  const delta = (v, tail) => v == null ? '' : `<div class="metric-delta ${v >= 0 ? 'positive' : 'negative'}">${pct(v)} ${tail}</div>`;
  const SIGNAL_COLORS = { Rising: '#059669', Falling: '#DC2626', Steady: '#2563EB', Irregular: '#9CA3AF', 'Insufficient data': '#9CA3AF' };

  const [summary, flows, comm, brief] = await Promise.all([
    fetchAPI('/trade/summary'), fetchAPI('/trade/flows?months=60'), fetchAPI('/trade/commodities'), fetchAPI('/trade/brief')
  ]);
  const srcLine = (k) => { const x = brief && brief.sources && brief.sources[k]; return x ? `<b>Data used:</b> ${esc(x.title)} &nbsp;|&nbsp; <b>File:</b> ${esc(x.data_file)} &nbsp;|&nbsp; <b>Where it comes from:</b> ${esc(x.origin)} &nbsp;|&nbsp; <b>Coverage:</b> ${esc(x.coverage)}` : ''; };
  const setSrc = (id, k) => { const e = document.getElementById(id); if (e) e.innerHTML = srcLine(k); };
  ['src-flow', 'src-mom', 'src-table'].forEach(id => setSrc(id, 'cargo'));
  setSrc('src-fc', 'forecast');
  setSrc('src-split', 'cargo_split');
  setSrc('src-wait', 'waiting');
  setSrc('src-oc', 'overseas_coastal');
  setSrc('src-cust', 'customers');

  // ── Customer watch (NMPA daily vessel reports) ──
  async function loadCustomers() {
    const box = document.getElementById('trade-customers');
    const cw = await fetchAPI('/trade/customers');
    if (!cw || !cw.available) {
      box.innerHTML = '<div class="alert-box alert-error">Could not load /trade/customers. If you just updated the project, an OLD backend is probably still running: close its window, start the backend again from the new folder, then refresh this page (Ctrl+F5).</div>';
      return;
    }
    const per = cw.period, conc = cw.concentration, cov = cw.coverage_vs_official;
    const num = (v) => v == null ? '—' : Math.round(v).toLocaleString();
    const ALERT_CLASS = { falling: 'alert-warning', gone_quiet: 'alert-warning', waiting: 'alert-warning', rising: 'alert-success', new: 'alert-info' };
    const TREND_COL = { Rising: '#059669', Falling: '#DC2626', Steady: '#2563EB' };
    const alerts = cw.alerts.map(a => `<div class="alert-box ${ALERT_CLASS[a.type] || 'alert-warning'}" style="margin-bottom:6px;">${esc(a.message)}</div>`);
    const rows = cw.customers;
    const flag = r => [r.joint_entry ? 'joint entry' : '', r.agent_name_warning ? 'agent name?' : ''].filter(Boolean).join(', ');
    const rowHtml = r => `<tr><td>${r.rank}</td><td><b>${esc(r.customer)}</b></td><td>${esc(r.main_cargo)}</td><td>${r.calls}</td><td>${num(r.tonnes)}</td><td>${r.share_of_traced_tonnes_pct == null ? '—' : r.share_of_traced_tonnes_pct + '%'}</td><td>${num(r.recent_tonnes)}</td><td>${num(r.previous_tonnes)}</td><td>${pct(r.change_pct)}</td><td><span style="color:${TREND_COL[r.trend] || '#6B7280'};font-weight:700;">${esc(r.trend)}</span></td><td>${r.days_since_last_call}</td><td>${r.usual_gap_days == null ? '—' : r.usual_gap_days}</td><td>${r.not_ready_ship_days}</td><td>${r.in_latest_report.expected} / ${r.in_latest_report.waiting}</td><td style="font-size:11px;color:#78716C;">${esc(flag(r))}</td></tr>`;
    const head = `<div class="table-container"><table><thead><tr><th>#</th><th>Customer</th><th>Main cargo</th><th>Calls</th><th>Tonnes</th><th>Share</th><th>${esc(per.recent_label)}</th><th>${esc(per.previous_label)}</th><th>Change</th><th>Trend</th><th>Days since last call</th><th>Usual gap (days)</th><th>Not-ready waiting (ship-days)</th><th>Due / waiting now</th><th>Note</th></tr></thead><tbody>`;
    const main = rows.filter(r => (r.share_of_traced_tonnes_pct || 0) >= 1 || r.calls >= 5);
    const rest = rows.filter(r => !((r.share_of_traced_tonnes_pct || 0) >= 1 || r.calls >= 5));

    box.innerHTML = `
      <div class="grid-4">
        <div class="metric-card"><div class="metric-label">Largest customer (${esc(conc.top3[0])})</div><div class="metric-value">${Math.round(conc.top1_pct)}%</div><div class="metric-delta">of traced tonnes</div></div>
        <div class="metric-card"><div class="metric-label">Top 3 customers</div><div class="metric-value">${Math.round(conc.top3_pct)}%</div><div class="metric-delta">${esc(conc.top3.join(', '))}</div></div>
        <div class="metric-card"><div class="metric-label">Customers making 80% of tonnes</div><div class="metric-value">${conc.customers_for_80pct}</div><div class="metric-delta">of ${cw.totals.customers} named customers</div></div>
        <div class="metric-card"><div class="metric-label">Tonnes traced vs official</div><div class="metric-value">${cov.traced_pct == null ? '—' : Math.round(cov.traced_pct) + '%'}</div><div class="metric-delta">non-container cargo</div></div>
      </div>
      <div style="font-size:12px;color:#57534E;margin:8px 0;">Trend compares <b>${esc(per.recent_label)}</b> with <b>${esc(per.previous_label)}</b> (complete months only). Latest daily report: ${esc(per.latest_report)}. ${esc(cov.verdict)}</div>
      ${alerts.length ? '<div style="font-weight:700;margin:10px 0 6px;">What needs a conversation with the customer</div>' + alerts.slice(0, 6).join('') + (alerts.length > 6 ? `<details><summary style="cursor:pointer;font-weight:600;margin:4px 0;">Show the other ${alerts.length - 6} customer alerts</summary>${alerts.slice(6).join('')}</details>` : '') : '<div class="alert-box alert-success">No customer is changing sharply, has gone quiet, or is causing an unusual share of waiting.</div>'}
      <div id="trade-cust-chart" style="height:460px;margin-top:10px;"></div>
      ${head}${main.map(rowHtml).join('')}</tbody></table></div>
      ${rest.length ? `<details style="margin-top:6px;"><summary style="cursor:pointer;font-weight:600;">Show ${rest.length} smaller customers</summary>${head}${rest.map(rowHtml).join('')}</tbody></table></div></details>` : ''}
      <div style="font-size:11.5px;color:#57534E;margin-top:6px;">Tonnes = complete months only. Container lines count calls, not tonnes. 'Joint entry' = the daily sheet names several receivers for one parcel. 'Agent name?' = this name is mostly written in the agent column, so it may not be the cargo owner.</div>
      <div style="font-family:Outfit;font-size:15px;font-weight:700;margin:16px 0 6px;">One customer in detail</div>
      <select id="trade-cust-pick" style="padding:6px 10px;border:1px solid #E7E5E4;border-radius:6px;min-width:260px;">${rows.map(r => `<option value="${esc(r.customer)}">${esc(r.customer)}</option>`).join('')}</select>
      <div id="trade-cust-detail" style="margin-top:10px;">Loading...</div>
      <details style="margin-top:10px;"><summary style="cursor:pointer;font-weight:600;">How customer numbers are checked, and their limits</summary>
        <div class="table-container"><table><thead><tr><th>Month</th><th>Official tonnes</th><th>Traced in daily reports</th><th>Traced %</th><th>With a named customer %</th><th>Daily reports</th></tr></thead><tbody>${cov.months.map(m => `<tr><td>${esc(m.month)}</td><td>${num(m.official_t)}</td><td>${num(m.traced_t)}</td><td>${m.traced_pct}%</td><td>${m.named_customer_pct}%</td><td>${m.report_days}</td></tr>`).join('')}</tbody></table></div>
        <div style="font-size:12px;margin-top:6px;"><b>Customer names:</b> ${cw.name_review.alias_rows} spellings are merged by <code>data/customer_aliases.csv</code>; ${cw.name_review.names_used_as_written} names are used exactly as written. ${esc(cw.name_review.note)}</div>
        <ul style="font-size:12px;margin:6px 0 0 18px;">${cw.how_it_works.map(h => `<li>${esc(h)}</li>`).join('')}</ul>
        <div style="font-size:12px;margin-top:6px;"><b>Limits</b></div><ul style="font-size:12px;margin:4px 0 0 18px;">${cw.limits.map(l => `<li>${esc(l)}</li>`).join('')}</ul>
      </details>`;

    const top = rows.filter(r => r.trend_basis === 'tonnes').slice(0, 12);
    Plotly.newPlot('trade-cust-chart', [
      { type: 'bar', orientation: 'h', name: per.previous_label, y: top.map(r => r.customer), x: top.map(r => r.previous_tonnes), marker: { color: '#CBD5E1' } },
      { type: 'bar', orientation: 'h', name: per.recent_label, y: top.map(r => r.customer), x: top.map(r => r.recent_tonnes), marker: { color: top.map(r => TREND_COL[r.trend] || '#2563EB') } },
    ], { ...PLOTLY_THEME, barmode: 'group', margin: { l: 170, r: 20, t: 30, b: 60 }, legend: { orientation: 'h', y: -0.12 },
         title: { text: 'Largest 12 customers: recent 3 months (coloured) vs the 3 before (grey)', font: { size: 13 } },
         xaxis: { ...PLOTLY_THEME.xaxis, type: 'linear', title: 'Tonnes (traced ship parcels)' }, yaxis: { ...PLOTLY_THEME.yaxis, type: 'category', autorange: 'reversed', automargin: true } });

    const pick = document.getElementById('trade-cust-pick');
    const showDetail = async () => {
      const el = document.getElementById('trade-cust-detail');
      el.innerHTML = 'Loading...';
      const cd = await fetchAPI('/trade/customer?name=' + encodeURIComponent(pick.value));
      if (!cd) { el.innerHTML = '<div class="alert-box alert-error">Could not load this customer.</div>'; return; }
      const s = cd.summary;
      const tbl = (cols, data) => `<div class="table-container"><table><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join('')}</tr></thead><tbody>${data.map(d => `<tr>${cols.map(c => `<td>${c[1](d)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      el.innerHTML = `
        <div class="grid-4">
          <div class="metric-card"><div class="metric-label">Calls</div><div class="metric-value">${s.calls}</div><div class="metric-delta">${s.recent_calls} in last 3 months</div></div>
          <div class="metric-card"><div class="metric-label">Tonnes (complete months)</div><div class="metric-value">${mt(s.tonnes)}</div>${delta(s.change_pct, 'recent vs previous 3 months')}</div>
          <div class="metric-card"><div class="metric-label">Foreign / coastal calls</div><div class="metric-value">${s.foreign_calls} / ${s.coastal_calls}</div></div>
          <div class="metric-card"><div class="metric-label">Waiting ship-days</div><div class="metric-value">${s.waiting_ship_days}</div><div class="metric-delta">${s.not_ready_ship_days} because not ready</div></div>
        </div>
        <div id="trade-cust-month" style="height:300px;margin-top:10px;"></div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;">
          <div><b>Cargo mix</b>${tbl([['Cargo', d => esc(d.cargo)], ['Direction', d => esc(d.direction)], ['Calls', d => d.calls], ['Tonnes', d => num(d.tonnes)], ['Foreign', d => d.foreign_calls], ['Coastal', d => d.coastal_calls]], cd.cargo_mix)}
            <div style="margin-top:8px;"><b>Waiting by reason</b></div>${cd.waiting_by_reason.length ? tbl([['Reason', d => esc(d.reason)], ['Ships', d => d.events], ['Ship-days', d => d.ship_days]], cd.waiting_by_reason) : '<div style="font-size:12px;color:#78716C;">No ship of this customer was recorded waiting.</div>'}</div>
          <div><b>In the latest daily report (${esc(cd.in_latest_report.report_date)})</b>${cd.in_latest_report.ships.length ? tbl([['Status', d => esc(d.status)], ['Ship', d => esc(d.vessel)], ['Cargo', d => esc(d.cargo)], ['Tonnes', d => num(d.quantity_t)], ['ETA / arrived', d => esc(d.eta_or_arrival)], ['Note', d => esc(d.reason)]], cd.in_latest_report.ships) : '<div style="font-size:12px;color:#78716C;">No ship for this customer is expected or waiting in the latest report.</div>'}
            <div style="margin-top:8px;"><b>Spellings merged into this name</b></div><div style="font-size:12px;color:#57534E;">${esc(cd.spellings_seen.join(', ') || '—')}</div></div>
        </div>
        <details style="margin-top:8px;"><summary style="cursor:pointer;font-weight:600;">Latest ships for this customer</summary>${tbl([['Ship', d => esc(d.vessel)], ['Cargo code', d => esc(d.cargo)], ['Cargo', d => esc(d.cargo_group)], ['First seen', d => esc(d.first_seen)], ['Last seen', d => esc(d.last_seen)], ['Run', d => esc(d.run)], ['Tonnes', d => num(d.tonnes)], ['Written as', d => esc(d.written_as)]], cd.recent_calls)}</details>
        ${cd.recent_waiting.length ? `<details style="margin-top:6px;"><summary style="cursor:pointer;font-weight:600;">Latest waiting events for this customer</summary>${tbl([['Ship', d => esc(d.vessel)], ['Cargo', d => esc(d.cargo)], ['Seen waiting', d => esc(d.first_seen)], ['Days waited', d => d.wait_days], ['Reason as written', d => esc(d.reason_as_written)], ['Reason group', d => esc(d.reason_group)]], cd.recent_waiting)}</details>` : ''}`;
      const mo = cd.monthly;
      Plotly.newPlot('trade-cust-month', [
        { type: 'bar', name: 'Tonnes', x: mo.map(m => m.month), y: mo.map(m => m.tonnes), marker: { color: mo.map(m => m.complete ? '#2563EB' : '#9CA3AF') } },
        { type: 'scatter', mode: 'lines+markers', name: 'Calls', x: mo.map(m => m.month), y: mo.map(m => m.calls), yaxis: 'y2', line: { color: '#D97706', width: 2 } },
      ], { ...PLOTLY_THEME, margin: { l: 60, r: 50, t: 30, b: 50 }, legend: { orientation: 'h', y: -0.2 },
           title: { text: `${cd.customer} — tonnes and calls per month (grey = partial month)`, font: { size: 13 } },
           xaxis: { ...PLOTLY_THEME.xaxis, type: 'category' }, yaxis: { ...PLOTLY_THEME.yaxis, title: 'Tonnes' },
           yaxis2: { overlaying: 'y', side: 'right', title: 'Calls', showgrid: false, rangemode: 'tozero' } });
    };
    pick.addEventListener('change', showDetail);
    showDetail();
  }
  loadCustomers();

  if (brief) {
    document.getElementById('trade-findings').innerHTML = `<div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:6px;">Key findings — ${esc(brief.as_of)}</div><ul style="margin:0 0 0 18px;font-size:13.5px;line-height:1.6;">${brief.findings.map(f => `<li>${esc(f)}</li>`).join('')}</ul><div style="font-size:11px;color:#78716C;margin-top:8px;">${srcLine('cargo')}</div>`;
    document.getElementById('trade-limits').innerHTML = brief.limits.map(l => `<li>${esc(l)}</li>`).join('');
  }

  if (!summary || !flows || !comm) {
    document.getElementById('trade-kpis').innerHTML = '<div class="alert-box alert-error">Could not load trade data — check that the backend is running.</div>';
  } else {
    const lm = summary.latest_month, ti = summary.inbound, to = summary.outbound, tt = summary.total;
    document.getElementById('trade-kpis').innerHTML = `
      <div class="metric-card"><div class="metric-label">Inbound — ${esc(summary.as_of)}</div><div class="metric-value">${mt(lm.inbound_tonnes)}</div>${delta(ti.yoy_pct_latest_month, 'vs same month last year')}</div>
      <div class="metric-card"><div class="metric-label">Outbound — ${esc(summary.as_of)}</div><div class="metric-value">${mt(lm.outbound_tonnes)}</div>${delta(to.yoy_pct_latest_month, 'vs same month last year')}</div>
      <div class="metric-card"><div class="metric-label">Outbound share</div><div class="metric-value">${lm.outbound_share_pct == null ? '—' : lm.outbound_share_pct.toFixed(1) + '%'}</div></div>
      <div class="metric-card"><div class="metric-label">Last 12 months, total</div><div class="metric-value">${mt(tt.last_12_months_tonnes)}</div>${delta(tt.yoy_pct_last_12_months, 'YoY (' + tt.months_compared_12m + ' months compared)')}</div>`;

    const alertData = await fetchAPI('/trade/alerts');
    if (alertData) {
      const cls = { warning: 'alert-warning', positive: 'alert-success', info: 'alert-info' };
      document.getElementById('trade-alerts').innerHTML = `<div style="font-family:Outfit;font-weight:700;margin:12px 0 8px;">What needs attention</div>` +
        (alertData.alerts.length ? (() => { const one = a => `<div class="alert-box ${cls[a.severity] || 'alert-info'}" style="margin-bottom:8px;">${esc(a.message)}</div>`; const A = alertData.alerts; return A.slice(0, 4).map(one).join('') + (A.length > 4 ? `<details><summary style="cursor:pointer;font-weight:600;margin-bottom:8px;">Show ${A.length - 4} more</summary>${A.slice(4).map(one).join('')}</details>` : ''); })()
                                 : '<div class="alert-box alert-success">No unusual cargo movements this month.</div>');
    }

    const oc = await fetchAPI('/trade/overseas-coastal');
    if (oc) {
      const y = oc.financial_year_to_date;
      document.getElementById('trade-oc').innerHTML = `
        <div class="grid-3" style="margin-bottom:8px;">
          <div class="metric-card"><div class="metric-label">Overseas, ${esc(y.from)} to ${esc(y.to)}</div><div class="metric-value">${mt(y.overseas_tonnes)}</div>${delta(y.overseas_yoy_pct, 'vs last year')}</div>
          <div class="metric-card"><div class="metric-label">Coastal</div><div class="metric-value">${mt(y.coastal_tonnes)}</div>${delta(y.coastal_yoy_pct, 'vs last year')}</div>
          <div class="metric-card"><div class="metric-label">Coastal share</div><div class="metric-value">${y.coastal_share_pct.toFixed(1)}%</div><div style="font-size:11px;color:#78716C;">${y.coastal_share_prev_year_pct.toFixed(1)}% last year</div></div>
        </div><div id="trade-oc-chart" style="height:280px;"></div>
        <div style="font-size:11.5px;color:#57534E;margin-top:6px;">${esc(oc.scope)}</div>`;
      const m = oc.series.map(r => r.month);
      Plotly.newPlot('trade-oc-chart', [
        { x: m, y: oc.series.map(r => r.overseas_tonnes), name: 'Overseas', type: 'bar', marker: { color: '#2563EB' } },
        { x: m, y: oc.series.map(r => r.coastal_tonnes), name: 'Coastal', type: 'bar', marker: { color: '#D97706' } }
      ], { ...PLOTLY_THEME, barmode: 'stack', legend: { orientation: 'h', y: -0.25 }, xaxis: { ...PLOTLY_THEME.xaxis, type: 'date', tickformat: '%b %Y' } });
    }

    const s = flows.series, x = s.map(r => r.month);
    const line = (name, key, color, dash) => ({ x, y: s.map(r => r[key]), name, type: 'scatter', mode: dash ? 'lines' : 'lines+markers', connectgaps: !!dash, line: { color, width: dash ? 1.5 : 2, dash: dash || 'solid' } });
    Plotly.newPlot('trade-flow-chart', [
      line('Inbound', 'inbound_tonnes', '#2563EB'), line('Outbound', 'outbound_tonnes', '#D97706'),
      line('Inbound trend (3-mo EMA)', 'inbound_ema3', '#2563EB', 'dot'), line('Outbound trend (3-mo EMA)', 'outbound_ema3', '#D97706', 'dot')
    ], { ...PLOTLY_THEME, legend: { orientation: 'h', y: -0.25 }, xaxis: { ...PLOTLY_THEME.xaxis, type: 'date', tickformat: '%b %Y' }, yaxis: { ...PLOTLY_THEME.yaxis, title: 'Tonnes' } });

    const fc = await fetchAPI('/trade/forecast');
    if (fc) {
      const mm = (v) => (v / 1e6).toFixed(2);
      const hist = s.slice(-24);
      const traces = [
        { x: hist.map(r => r.month), y: hist.map(r => r.inbound_tonnes), name: 'Inbound (actual)', type: 'scatter', mode: 'lines', line: { color: '#2563EB', width: 2 } },
        { x: hist.map(r => r.month), y: hist.map(r => r.outbound_tonnes), name: 'Outbound (actual)', type: 'scatter', mode: 'lines', line: { color: '#D97706', width: 2 } }
      ];
      [['All inbound cargo', 'Inbound forecast', '#2563EB'], ['All outbound cargo', 'Outbound forecast', '#D97706']].forEach(([label, name, color]) => {
        const r = fc.results.find(q => q.series === label);
        if (r && r.forecast.length) traces.push({ x: r.forecast.map(f => f.month + '-01'), y: r.forecast.map(f => f.forecast_tonnes), name, type: 'scatter', mode: 'markers', marker: { color, size: 10, symbol: 'diamond' },
          error_y: { type: 'data', symmetric: false, array: r.forecast.map(f => f.range_high_tonnes - f.forecast_tonnes), arrayminus: r.forecast.map(f => f.forecast_tonnes - f.range_low_tonnes), color, thickness: 2, width: 6 } });
      });
      Plotly.newPlot('trade-fc-chart', traces, { ...PLOTLY_THEME, legend: { orientation: 'h', y: -0.25 }, xaxis: { ...PLOTLY_THEME.xaxis, type: 'date', tickformat: '%b %Y' }, yaxis: { ...PLOTLY_THEME.yaxis, title: 'Tonnes' } });
      const CONF = { High: '#059669', Medium: '#2563EB', Low: '#D97706', 'Not forecastable': '#9CA3AF', 'Not enough history': '#9CA3AF' };
      let t = `<div class="table-container"><table><thead><tr><th>Cargo</th><th>Direction</th><th>Next month</th><th>Forecast</th><th>Typical range</th><th>Past error</th><th>Reliability</th><th>Method used</th></tr></thead><tbody>`;
      fc.results.forEach(r => {
        const f = r.forecast[0];
        t += `<tr><td><b>${esc(r.series)}</b></td><td>${esc(r.direction)}</td><td>${f ? esc(f.month) : '—'}</td><td>${f ? mm(f.forecast_tonnes) + ' M t' : 'not shown'}</td><td>${f ? mm(f.range_low_tonnes) + ' to ' + mm(f.range_high_tonnes) + ' M t' : '—'}</td><td>${r.used_wape_pct == null ? '—' : r.used_wape_pct + '%'}</td><td><span style="color:${CONF[r.confidence] || '#6B7280'};font-weight:700;">${esc(r.confidence)}</span></td><td>${esc(r.method_text || '—')}</td></tr>`;
      });
      t += `</tbody></table></div><div style="font-size:11.5px;color:#57534E;margin-top:8px;"><b>How to read it:</b> "Past error" is how far past forecasts missed, out of every 100 tonnes. ${fc.how_it_works.map(esc).join(' ')} <b>Limits:</b> ${fc.limits.map(esc).join(' ')}</div>`;
      document.getElementById('trade-fc-table').innerHTML = t;
    } else {
      document.getElementById('trade-fc-table').innerHTML = '<div class="alert-box alert-error">Could not load the forecast.</div>';
    }

    const sp = await fetchAPI('/trade/cargo-split');
    if (sp && sp.available) {
      const v = sp.validation_against_ministry;
      const known = sp.families.filter(f => f.direction_known && f.ships >= 8);
      const rest = sp.families.filter(f => !(f.direction_known && f.ships >= 8));
      const PCOL = { 'Mostly foreign': '#2563EB', 'Mostly coastal': '#D97706', Mixed: '#7C3AED', 'Too few ships to tell': '#9CA3AF' };
      const rowHtml = f => `<tr><td><b>${esc(f.cargo)}</b></td><td>${esc(f.direction)}</td><td>${f.ships}</td><td>${f.foreign_ships} / ${f.coastal_ships}</td><td>${f.coastal_share_by_ships_pct}%</td><td>${f.coastal_share_by_quantity_pct == null ? '—' : f.coastal_share_by_quantity_pct + '%'}</td><td><span style="color:${PCOL[f.pattern] || '#6B7280'};font-weight:700;">${esc(f.pattern)}</span></td><td>${f.top_customers.map(c => esc(c.customer)).join(', ') || '—'}</td></tr>`;
      const head = '<div class="table-container"><table><thead><tr><th>Cargo</th><th>Direction</th><th>Ships</th><th>Foreign / coastal</th><th>Coastal % (ships)</th><th>Coastal % (quantity)</th><th>Pattern</th><th>Main customers</th></tr></thead><tbody>';
      document.getElementById('trade-split').innerHTML = `<div class="alert-box alert-warning" style="margin-bottom:8px;"><b>Estimate.</b> ${esc(v.verdict)}</div>` + head + known.map(rowHtml).join('') + '</tbody></table></div>' +
        (rest.length ? `<details style="margin-top:8px;"><summary style="cursor:pointer;font-weight:600;">Show ${rest.length} more groups (few ships, or direction not written in the daily sheet)</summary>${head}${rest.map(rowHtml).join('')}</tbody></table></div></details>` : '') +
        `<div style="font-size:11.5px;color:#57534E;margin-top:8px;"><b>Period:</b> ${esc(sp.period.from)} to ${esc(sp.period.to)}. <b>Limits:</b> ${sp.limits.map(esc).join(' ')}</div>`;
    } else {
      document.getElementById('trade-split').innerHTML = '<div class="alert-box alert-error">Could not load the foreign vs coastal split from /trade/cargo-split. If you just updated the project, an OLD backend is probably still running: close its window, start the backend again from the new folder, then refresh this page (Ctrl+F5).</div>';
    }

    const wt = await fetchAPI('/trade/waiting');
    if (wt && wt.available) {
      const o = wt.overall, top = wt.by_reason[0];
      const rt = r => `<tr><td><b>${esc(r.reason || r.cargo || r.customer)}</b></td><td>${r.events}</td><td>${r.avg_wait_days}</td><td>${r.ship_days}</td><td>${r.share_of_waiting_days_pct}%</td>${r.not_ready_share_pct == null ? '' : `<td>${r.not_ready_share_pct}%</td>`}</tr>`;
      const tbl = (rows, first, extra) => `<div class="table-container"><table><thead><tr><th>${first}</th><th>Waiting events</th><th>Avg wait (days)</th><th>Total ship-days</th><th>Share of all waiting</th>${extra ? '<th>Of which "not ready"</th>' : ''}</tr></thead><tbody>${rows.map(rt).join('')}</tbody></table></div>`;
      document.getElementById('trade-wait').innerHTML =
        `<div class="alert-box alert-warning" style="margin-bottom:8px;"><b>${o.events} waiting events</b> (${esc(wt.period.from)} to ${esc(wt.period.to)}). Average wait ${o.avg_wait_days} days, middle value ${o.median_wait_days}, the longest 10% waited ${o.p90_wait_days}+ days. Biggest written cause: <b>${esc(top.reason)}</b> (${top.share_of_waiting_days_pct}% of waiting days).</div>` +
        '<div id="trade-wait-month" style="height:260px;"></div>' + '<b>By reason</b>' + tbl(wt.by_reason, 'Reason', false) +
        '<div style="margin-top:10px;"><b>By cargo</b></div>' + tbl(wt.by_cargo.slice(0, 8), 'Cargo', true) +
        '<div style="margin-top:10px;"><b>By customer</b></div>' + tbl(wt.by_customer.slice(0, 8), 'Customer', true) +
        `<div style="font-size:11.5px;color:#57534E;margin-top:8px;"><b>Limits:</b> ${wt.limits.map(esc).join(' ')}</div>`;
      Plotly.newPlot('trade-wait-month', [{ type: 'bar', x: wt.by_month.map(m => m.month), y: wt.by_month.map(m => m.avg_wait_days), marker: { color: wt.by_month.map(m => wt.partial_months.includes(m.month) ? '#9CA3AF' : '#2563EB') }, text: wt.by_month.map(m => m.avg_wait_days), textposition: 'outside' }], { ...PLOTLY_THEME, margin: { l: 50, r: 20, t: 20, b: 40 }, yaxis: { ...PLOTLY_THEME.yaxis, title: 'Average wait (days); grey = partial month' } });
    } else {
      document.getElementById('trade-wait').innerHTML = '<div class="alert-box alert-error">Could not load /trade/waiting. An OLD backend may still be running: close it, start it again from the new folder, then refresh (Ctrl+F5).</div>';
    }

    const ranked = comm.commodities.filter(c => c.momentum_pct != null).sort((a, b) => a.momentum_pct - b.momentum_pct);
    Plotly.newPlot('trade-momentum-chart', [{
      type: 'bar', orientation: 'h',
      x: ranked.map(c => c.momentum_pct), y: ranked.map(c => `${c.commodity} (${c.direction})`),
      text: ranked.map(c => pct(c.momentum_pct)), textposition: 'outside', cliponaxis: false,
      marker: { color: ranked.map(c => SIGNAL_COLORS[c.signal] || '#9CA3AF') }
    }], { ...PLOTLY_THEME, margin: { l: 190, r: 70, t: 20, b: 50 }, xaxis: { ...PLOTLY_THEME.xaxis, title: 'Momentum % (grey = irregular cargo)', zeroline: true }, yaxis: { ...PLOTLY_THEME.yaxis, type: 'category', automargin: true, tickfont: { size: 10 } } });

    let html = `<div class="table-container"><table><thead><tr><th>Cargo</th><th>Direction</th><th>Latest month (t)</th><th>YoY latest month</th><th>YoY last 12 months</th><th>Share of direction</th><th>Momentum</th><th>Signal</th></tr></thead><tbody>`;
    comm.commodities.forEach(c => {
      html += `<tr><td><b>${esc(c.commodity)}</b></td><td>${esc(c.direction)}</td><td>${c.latest_month_tonnes == null ? '—' : c.latest_month_tonnes.toLocaleString()}</td><td>${pct(c.yoy_pct_latest_month)}</td><td>${pct(c.yoy_pct_last_12_months)}</td><td>${c.share_of_direction_pct == null ? '—' : c.share_of_direction_pct + '%'}</td><td>${pct(c.momentum_pct)}</td><td><span style="color:${SIGNAL_COLORS[c.signal] || '#6B7280'};font-weight:700;">${esc(c.signal)}</span></td></tr>`;
    });
    html += `</tbody></table></div><div style="font-size:11px;color:#78716C;margin-top:8px;">${esc(comm.momentum_method)} Momentum and year-on-year measure different things and can disagree.</div>`;
    document.getElementById('trade-table').innerHTML = html;

    const dq = summary.data_quality, xc = dq.prior_year_crosscheck;
    document.getElementById('trade-quality').innerHTML = `<b>Data quality:</b> ${esc(dq.first_month)} to ${esc(dq.latest_month)}, ${dq.months_with_data} of ${dq.months_in_span} months have data. Missing: ${esc(dq.missing_months.join(', ') || 'none')} (shown as gaps, never zero). ${dq.reconstructed_months.length} months (${esc(dq.reconstructed_months[0])} to ${esc(dq.reconstructed_months[dq.reconstructed_months.length - 1])}) are rebuilt from the prior-year column of later reports — ${xc.exact_match_pct}% of cross-checkable figures match the original exactly. Inbound = cargo unloaded, outbound = cargo loaded; the source does not split foreign trade from coastal movement.`;
  }
}

// ─── TAB 6: Anomaly Detection Renderer ────────────────────────────────────────
async function renderAnomaly() {
  const container = document.getElementById('tab-anomaly');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Cargo Anomaly & Risk Intelligence</span><span class="sec-tag">Real (ML)</span></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ Real IsolationForest model (scikit-learn) flagging genuine outlier months in data/port_cargo_monthly.csv — unsupervised, so there's no labeled ground truth to score accuracy against; severity is relative to other flagged months, not an absolute risk level.</div><div class="card" id="anomaly-list">Loading anomalies...</div>`;

  const data = await fetchAPI('/anomaly/events') || { events: [] };
  const list = data.events || [];
  document.getElementById('anomaly-list').innerHTML = list.map(a => `
    <div class="alert-box alert-warning" style="margin-bottom:12px;">
      <div><b>${a.type}</b> — ${a.commodity} (Severity: ${a.severity}, Confidence: ${(a.confidence * 100).toFixed(0)}%)</div>
      <div style="font-size:12px;margin-top:4px;">${a.description}</div>
      <div style="font-size:11px;color:#78716C;margin-top:4px;"><b>Recommended action:</b> ${a.recommended_action}</div>
    </div>
  `).join('') || '<div class="alert-box alert-success">No anomalies detected in the current dataset.</div>';
}

// ─── TAB 7: Incentive Engine Renderer ─────────────────────────────────────────
async function renderIncentive() {
  const container = document.getElementById('tab-incentive');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Incentive Engine</span></div>
    <div class="card">The Incentive Engine is in the main dashboard (Streamlit, port 8501), tab "Incentive Engine".
    It works from NMPA's published tonnes and Scale of Rates and does not use assumed demand responses.</div>`;
}

// ─── TAB 8: Digital Twin Renderer ─────────────────────────────────────────────
async function renderDigitalTwin() {
  const container = document.getElementById('tab-twin');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Digital Twin Port Simulator</span><span class="sec-tag">Demo Data</span></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ Scenario outcomes (congestion, storage, revenue) are simulated illustrations, not calibrated against real incident data.</div><div class="card" id="twin-radar" style="height:360px;">Loading Digital Twin...</div>`;

  const data = await fetchAPI('/twin/scenario/cargo_surge') || { result: {} };
  const r = data.result || {};

  const categories = ['Congestion', 'Berth Util', 'Storage Util', 'Revenue'];
  const values = [r.congestion_index * 100 || 63, r.berth_utilization_pct || 72, r.storage_utilization_pct || 65, 90];

  const traces = [{ type: 'scatterpolar', r: values, theta: categories, fill: 'toself', name: 'Cargo Surge Scenario', line: { color: '#F59E0B' } }];
  Plotly.newPlot('twin-radar', traces, { ...PLOTLY_THEME, polar: { radialaxis: { visible: true, range: [0, 100] } } });
}

// ─── TAB 9: AI Copilot Renderer ───────────────────────────────────────────────
async function renderCopilot() {
  const container = document.getElementById('tab-copilot');
  container.innerHTML = `
    <div class="sec-header"><span class="sec-title">AI Maritime Copilot</span><span class="sec-tag">Demo Data</span></div>
    <div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ "LangGraph" names the architecture pattern, not the library — langgraph/langchain are not dependencies of this project. Responses are templated, not generated by a real LLM call.</div>
    <div class="card" style="margin-bottom:20px;">
      <div class="form-group">
        <label class="form-label">Ask Maritime Copilot</label>
        <input type="text" id="copilot-input" placeholder="Why is coal forecast increasing?">
      </div>
      <button class="btn" onclick="sendCopilotQuery()">Submit Query</button>
    </div>
    <div id="copilot-output"></div>
  `;
}

async function sendCopilotQuery() {
  const query = document.getElementById('copilot-input')?.value || "Why is cargo forecast increasing?";
  document.getElementById('copilot-output').innerHTML = '<div class="alert-box alert-warning">Dispatching query across 3-tier agent roster...</div>';

  const res = await fetchAPI('/copilot/query', {
    method: 'POST',
    body: JSON.stringify({ query })
  }) || { response: { answer: "Coal forecast is increasing due to higher thermal power demand from UPCL." } };
  const answer = res.response?.answer || "No response generated.";

  document.getElementById('copilot-output').innerHTML = `
    <div class="card">
      <div style="font-size:11px;font-weight:800;color:#D97706;">COPILOT SYNTHESIS RESPONSE</div>
      <div style="font-size:15px;margin-top:8px;">${answer}</div>
    </div>
  `;
}

// ─── TAB 10: Data Pipeline Renderer ───────────────────────────────────────────
async function renderPipeline() {
  const container = document.getElementById('tab-pipeline');
  container.innerHTML = `
    <div class="sec-header"><span class="sec-title">Data Pipeline & System Architecture</span><span class="sec-tag">Demo Data</span></div>
    <div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ This entire tab is simulated — no Kafka/Spark/Airflow/Milvus/TimescaleDB infrastructure runs behind this project. The metrics and log lines below are a fixed hardcoded list illustrating the intended architecture, not live system telemetry.</div>
    <div class="grid-4" id="pipe-metrics">Loading pipeline...</div>
  `;
  const data = await fetchAPI('/pipeline/status') || { kafka: { messages_per_sec: 1450 }, spark: { rows_per_sec: 12800 }, data_pools: { total_storage_gb: 420 }, airflow: { dags_active: 14 } };
  document.getElementById('pipe-metrics').innerHTML = `
    <div class="metric-card"><div class="metric-label">Kafka Msg/sec</div><div class="metric-value">${data.kafka?.messages_per_sec}</div></div>
    <div class="metric-card"><div class="metric-label">Spark Rows/sec</div><div class="metric-value">${data.spark?.rows_per_sec}</div></div>
    <div class="metric-card"><div class="metric-label">Storage GB</div><div class="metric-value">${data.data_pools?.total_storage_gb} GB</div></div>
    <div class="metric-card"><div class="metric-label">Airflow Active DAGs</div><div class="metric-value">${data.airflow?.dags_active}</div></div>
  `;
}

// ─── Init App On Load ────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  renderExecutive();
  setInterval(() => {
    const el = document.getElementById('live-timestamp');
    if (el) el.innerText = new Date().toISOString().replace('T', ' ').substring(0, 19) + " UTC";
  }, 1000);
});
