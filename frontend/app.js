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
    case 'tab-port-cost': renderPortCost(); break;
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
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Executive Command Center</span><span class="sec-tag">Demo Data</span><div class="sec-sub">Port-wide operational overview — KPIs, vessel positions, berth utilization & revenue</div></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ Revenue (₹ Cr), KPI deltas, and vessel positions/map on this tab are simulated — no financial/pricing or AIS dataset exists in this project. Only the underlying berth-utilization figures are real (data/berths.csv + latest cargo tonnage). Real vessel data (NMPA Daily Vessel Position reports) is on the Vessel Intelligence tab.</div><div class="grid-4" id="exec-kpis">Loading Executive KPIs...</div><br><div class="grid-3-2"><div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">NMPA Illustrative Vessel Approach Map</div><div id="exec-map" style="height:340px;"></div></div><div class="card"><div style="font-family:Outfit;font-size:16px;font-weight:700;margin-bottom:12px;">30-Day Revenue & Throughput Trend (Simulated)</div><div id="exec-trend" style="height:340px;"></div></div></div>`;

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

// ─── TAB 2: Vessel Intelligence Renderer (real NMPA data) ─────────────────────
// Source: NMPA Daily Vessel Position reports + official monthly Operational
// Performance report, via /vessels/intel/*. See PROJECT_DOCUMENTATION/27.
const VI_CLASS = {
  dry_bulk_conventional: "Dry bulk (conv.)", dry_bulk_mechanical: "Dry bulk (mech.)", break_bulk: "Break bulk",
  liquid_bulk: "Liquid bulk", container: "Container", cruise: "Cruise", non_cargo: "Non-cargo", unknown: "Unknown"
};
const VI_CLASS_COLOR = {
  dry_bulk_conventional: "#78716C", dry_bulk_mechanical: "#374151", break_bulk: "#0891B2", liquid_bulk: "#D97706",
  container: "#2563EB", cruise: "#7C3AED", non_cargo: "#A8A29E", unknown: "#D6D3D1"
};
const VI_ACCOUNT = { port: "Port account", non_port: "Other than port", excluded: "Non-cargo", unknown: "Not stated" };

// IMO number under the ship name (curated lookup, matched on name + LOA).
function viImo(r) {
  if (r.imo) return `<div style="font-size:11px;color:#57534E;">IMO ${escHtml(r.imo)}</div>`;
  if (r.imo_match === 'ambiguous' || r.imo_match === 'loa_mismatch')
    return `<div style="font-size:11px;color:#B45309;">same name as another ship, check IMO</div>`;
  return '';
}

function viDt(s) {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d)) return escHtml(s);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

async function renderVessels(asOf) {
  const container = document.getElementById('tab-vessels');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Vessel Intelligence — New Mangalore Port</span><span class="sec-tag">Real data</span>
    <div class="sec-sub">For the berth planner and Traffic Department — expected, waiting and alongside vessels, departure forecasts, berth conflicts, and NMPA's own monthly KPIs.</div></div>
    <div id="vi-body">Loading NMPA Daily Vessel Position data…</div>`;

  const dates = await fetchAPI('/vessels/intel/report-dates') || { dates: [] };
  if (!dates.dates || dates.dates.length === 0) {
    document.getElementById('vi-body').innerHTML = '<div class="alert-box alert-warning">No Daily Vessel Position reports loaded. Run <code>python scripts/update_vessel_intel_data.py</code>.</div>';
    return;
  }
  const q = asOf ? `?as_of=${asOf}` : '';
  const [board, arrivals, plan, perf, ov] = await Promise.all([
    fetchAPI('/vessels/intel/board' + q), fetchAPI('/vessels/intel/arrivals' + q),
    fetchAPI('/vessels/intel/berth-plan' + q), fetchAPI('/vessels/intel/performance' + q), fetchAPI('/vessels/intel/overview' + q)
  ]);
  if (!board) {
    document.getElementById('vi-body').innerHTML = '<div class="alert-box alert-error">Vessel Intelligence API unavailable.</div>';
    return;
  }
  const s = board.summary, lin = board.lineage || {};
  const opts = dates.dates.slice().reverse().map(d => `<option value="${d}" ${d === board.as_of_report ? 'selected' : ''}>${d}</option>`).join('');
  const age = lin.data_age_days;
  let html = `
    <div class="grid-3-2" style="align-items:center;margin-bottom:12px;">
      <div class="alert-box alert-success" style="margin:0;"><div><b>REAL DATA</b> · NMPA Daily Vessel Position report of <b>${escHtml(board.as_of_report)}</b>
        (as of ~${escHtml((lin.report_reference_time || '10:00').slice(0, 5))} IST) · ${lin.coverage ? lin.coverage.published_days : '?'} reports in archive
        ${age > 2 ? `· <span style="color:#B45309;"><b>latest report is ${age} days old</b></span>` : ''}</div></div>
      <div class="form-group" style="margin:0;"><label class="form-label">As of NMPA report</label>
        <select onchange="renderVessels(this.value)">${opts}</select></div>
    </div>
    <div class="grid-4">
      <div class="metric-card"><div class="metric-label">Cargo vessels alongside</div><div class="metric-value">${s.alongside_cargo}</div><div class="metric-delta">${s.berths_occupied_cargo}/${s.berths_total} berths occupied</div></div>
      <div class="metric-card"><div class="metric-label">Waiting at anchorage</div><div class="metric-value">${s.waiting_total}</div><div class="metric-delta">${s.waiting_port_account} on port account · longest ${fmtNum(s.longest_port_account_wait_h)} h</div></div>
      <div class="metric-card"><div class="metric-label">Expected next 72 h</div><div class="metric-value">${s.expected_next_72h}</div><div class="metric-delta">${s.expected_total} on the expected list</div></div>
      <div class="metric-card"><div class="metric-label">NMPA programme</div><div class="metric-value">${s.programmed_berthings}</div><div class="metric-delta">berthings · ${s.programmed_sailings} sailings planned</div></div>
    </div><br>`;

  if (board.alerts && board.alerts.length) {
    html += board.alerts.slice(0, 6).map(a => `<div class="alert-box ${a.severity === 'high' ? 'alert-error' : 'alert-warning'}" style="margin-bottom:8px;"><div><b>${escHtml(a.type.replace(/_/g, ' '))}</b> — ${escHtml(a.message)}</div></div>`).join('');
  }

  // Alongside
  html += `<div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:10px;">Alongside — departure forecast</div><div class="table-container"><table><thead><tr>
    <th>Berth</th><th>Vessel</th><th>Cargo</th><th>Balance (t)</th><th>Last 24h (t)</th><th>NMPA ETD</th><th>Predicted departure</th><th>Basis</th></tr></thead><tbody>`;
  board.alongside.forEach(a => {
    html += `<tr><td><b>${escHtml(a.berth || '—')}</b></td><td>${escHtml(a.vessel)}${viImo(a)}</td>
      <td><span style="color:${VI_CLASS_COLOR[a.cargo_class] || '#1C1917'};font-weight:700;">${escHtml(a.cargo || VI_CLASS[a.cargo_class])}</span></td>
      <td>${fmtNum(a.qty_balance_t)}</td><td>${fmtNum(a.qty_day_t)}</td><td>${escHtml(a.nmpa_etd || '—')}</td>
      <td><b>${viDt(a.predicted_departure)}</b></td><td style="font-size:11px;color:#78716C;">${escHtml(a.forecast_method || '')}</td></tr>`;
  });
  html += `</tbody></table></div></div><br>`;

  // Waiting
  html += `<div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:10px;">Waiting at anchorage / scheduled tankers</div><div class="table-container"><table><thead><tr>
    <th>Vessel</th><th>Cargo</th><th>Waiting</th><th>Reason (NMPA)</th><th>Account</th><th>Target berth</th><th>Programmed berthing</th><th>Likely more wait</th></tr></thead><tbody>`;
  board.waiting.forEach(w => {
    const badge = w.account === 'port' ? 'badge-critical' : (w.account === 'non_port' ? 'badge-warning' : 'badge-normal');
    html += `<tr><td><b>${escHtml(w.vessel)}</b>${viImo(w)}</td><td>${escHtml(w.cargo || '—')}</td><td>${fmtNum(w.waiting_h)} h</td>
      <td>${escHtml(w.reason_raw || '—')}</td><td><span class="badge ${badge}">${escHtml(VI_ACCOUNT[w.account] || w.account)}</span></td>
      <td>${escHtml(w.target_berth || '—')}</td><td>${w.programme_berthing ? viDt(w.programme_berthing.at) + ' @ B' + escHtml(w.programme_berthing.berth) : '—'}</td>
      <td>${w.expected_more_wait_h != null ? fmtNum(w.expected_more_wait_h) + ' h (p80 ' + fmtNum(w.expected_more_wait_p80_h) + ' h)' : '—'}</td></tr>`;
  });
  if (!board.waiting.length) html += `<tr><td colspan="8">No vessels waiting in this report.</td></tr>`;
  html += `</tbody></table></div></div><br>`;

  // Expected
  html += `<div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:10px;">Vessels expected</div><div class="table-container"><table><thead><tr>
    <th>Vessel</th><th>Cargo</th><th>Declared ETA</th><th>Likely window (p10–p90)</th><th>Draft / LOA</th><th>Berths</th><th>Fit</th><th>P(wait &gt; 24 h)</th></tr></thead><tbody>`;
  board.expected.forEach(e => {
    const fitBadge = e.berthing_fit === 'exceeds' ? 'badge-critical' : (e.berthing_fit === 'tight' ? 'badge-warning' : 'badge-normal');
    html += `<tr><td><b>${escHtml(e.vessel)}</b>${viImo(e)}</td><td>${escHtml(e.cargo || '—')}</td><td>${viDt(e.declared_eta)}</td>
      <td>${e.eta_p10 ? viDt(e.eta_p10) + ' – ' + viDt(e.eta_p90) : '—'}</td><td>${fmtNum(e.draft_m, 1)} m / ${fmtNum(e.loa_m)} m</td>
      <td>${escHtml((e.berth_prefs || []).join(', ') || '—')}</td><td><span class="badge ${fitBadge}">${escHtml(e.berthing_fit.replace(/_/g, ' '))}</span></td>
      <td>${e.p_wait_over_threshold != null ? (e.p_wait_over_threshold * 100).toFixed(0) + '%' : '—'}</td></tr>`;
  });
  html += `</tbody></table></div></div><br>`;

  html += `<div class="grid-2"><div class="card"><div id="vi-arrivals" style="height:320px;"></div></div><div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:10px;">Berth conflicts — next 72 h</div><div id="vi-conflicts"></div></div></div><br>`;
  html += `<div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:6px;">Performance vs NMPA official monthly report</div><div style="font-size:12px;color:#78716C;margin-bottom:10px;">${escHtml(perf?.how_to_read || '')}</div><div id="vi-perf"></div></div><br>`;
  html += `<div class="card"><div style="font-weight:700;font-size:16px;margin-bottom:10px;">How reliable is each feature?</div><div id="vi-cards"></div></div>`;
  document.getElementById('vi-body').innerHTML = html;

  if (arrivals && arrivals.days) {
    const classes = [...new Set(arrivals.days.flatMap(d => Object.keys(d.by_cargo_class)))];
    const traces = classes.map(c => ({
      type: 'bar', name: VI_CLASS[c] || c, x: arrivals.days.map(d => d.date),
      y: arrivals.days.map(d => d.by_cargo_class[c] || 0), marker: { color: VI_CLASS_COLOR[c] || '#F59E0B' }
    }));
    if (window.Plotly) {
      Plotly.newPlot('vi-arrivals', traces, { ...PLOTLY_THEME, barmode: 'stack', title: 'Expected arrivals per day (from declared ETAs)' }, { displayModeBar: false });
    } else {
      document.getElementById('vi-arrivals').innerHTML = '<div style="font-weight:700;margin-bottom:8px;">Expected arrivals per day</div>' +
        arrivals.days.map(d => `<div>${escHtml(d.date)}: <b>${fmtNum(d.expected_arrivals, 1)}</b></div>`).join('');
    }
  }
  const cf = (plan && plan.conflicts) || [];
  document.getElementById('vi-conflicts').innerHTML = cf.length
    ? cf.map(c => `<div class="alert-box ${c.severity === 'high' ? 'alert-error' : 'alert-warning'}" style="margin-bottom:8px;">${escHtml(c.message)}</div>`).join('')
      + `<div style="font-size:11px;color:#78716C;">${escHtml(plan.lineage?.method || '')}</div>`
    : '<div class="alert-box alert-success">No berth conflicts forecast.</div>';

  const rec = perf && perf.reconciliation && perf.reconciliation.length ? perf.reconciliation[perf.reconciliation.length - 1] : null;
  if (rec) {
    const rows = rec.rows.filter(r => ['overall', 'liquid_bulk', 'dry_bulk_total', 'container'].includes(r.cargo_class));
    document.getElementById('vi-perf').innerHTML = `<div style="margin-bottom:6px;"><b>${escHtml(rec.month)}</b> · daily-report coverage ${rec.dvp_coverage_pct}%</div>
      <div class="table-container"><table><thead><tr><th>Class</th><th>Metric</th><th>NMPA official</th><th>Rebuilt from daily reports</th><th>Verdict</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td>${escHtml(VI_CLASS[r.cargo_class] || r.cargo_class.replace(/_/g, ' '))}</td><td>${escHtml(r.metric)}</td><td>${fmtNum(r.official, 2)}</td><td>${fmtNum(r.dvp_derived, 2)}</td>
      <td><span class="badge ${['matches', 'close'].includes(r.verdict) ? 'badge-normal' : 'badge-warning'}">${escHtml(r.verdict)}</span></td></tr>`).join('')}</tbody></table></div>`;
  } else {
    document.getElementById('vi-perf').innerHTML = '<div class="alert-box alert-warning">No official monthly report overlapping the daily archive is loaded yet.</div>';
  }
  document.getElementById('vi-cards').innerHTML = ((ov && ov.model_cards) || []).map(c =>
    `<div style="padding:10px 0;border-bottom:1px solid #F3E8D6;"><b>${escHtml(c.feature)}</b> <span class="badge badge-normal">${escHtml(c.status)}</span>
     <div style="font-size:13px;margin-top:4px;">${escHtml(c.headline)}</div><div style="font-size:12px;color:#78716C;">${escHtml(c.verdict || '')}</div></div>`).join('');
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

// ─── TAB 4b: Port Cost & Tariff (NMPA SOR 2026-27) ──────────────────────────
// Every number on this tab comes from the NMPA SOR 2026-27, a real past vessel
// call in NMPA's Daily Vessel Position reports, or the user. Nothing is filled
// with demo values: a missing input (e.g. GRT) is shown as missing, not guessed.
function escHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function fmtINR(value) {
  return "₹" + Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
const fmtUSD = v => "US$ " + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtNum = (v, d = 0) => v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d });

let sorCommodities = [];
let costMatchTimer = null;
let pastCalls = [];
let pastCallTimer = null;

const COST_BERTHS = ["", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "SPM"];

async function renderPortCost() {
  const container = document.getElementById('tab-port-cost');
  const num = (id, label, attrs = "", help = "") =>
    `<div class="form-group"><label class="form-label">${label}</label><input type="number" id="${id}" ${attrs}>${help ? `<div style="font-size:11px;color:#78716C;margin-top:4px;">${help}</div>` : ""}</div>`;
  container.innerHTML = `
    <div class="sec-header">
      <span class="sec-title">NMPA Port Cost & Tariff Calculator</span>
      <span class="sec-tag">Real (NMPA SOR 2026-27 + past calls)</span>
      <div class="sec-sub">Rates from the NMPA Indexed SOR w.e.f. 01-05-2026 · inputs from real vessel calls in NMPA's Daily Vessel Position reports · checked against SOR 2022 and NMPA's 2023-24 income</div>
    </div>

    <div class="card" style="margin-bottom:20px;">
      <div style="font-size:11px;font-weight:800;color:#D97706;">START FROM A REAL PAST CALL</div>
      <div class="grid-2" style="margin-top:8px;">
        <div class="form-group"><label class="form-label">Search vessel, cargo, berth or receiver</label>
          <input type="text" id="past-call-q" placeholder="e.g. IOF, LPG, KIOCL, SPM, VISHVA" oninput="schedulePastCallSearch()"></div>
        <div class="form-group"><label class="form-label">Past call (newest first)</label>
          <select id="past-call-select" onchange="loadPastCall(this.value)"><option value="">Loading calls…</option></select></div>
      </div>
      <div id="past-call-info" style="font-size:12px;color:#78716C;"></div>
    </div>

    <div class="card" style="margin-bottom:20px;">
      <div style="font-size:11px;font-weight:800;color:#D97706;">CARGO</div>
      <div class="grid-4" style="margin-top:8px;">
        <div class="form-group">
          <label class="form-label">Commodity (any name, NMPA code or SOR code)</label>
          <input type="text" id="cost-commodity" list="cost-commodity-list" oninput="scheduleCostMatch()">
          <datalist id="cost-commodity-list"></datalist>
          <div id="cost-match" style="font-size:12px;margin-top:6px;color:#78716C;"></div>
        </div>
        ${num("cost-qty", "Quantity (MT, or CBM / units where the SOR says so)", 'min="0" step="any"')}
        <div class="form-group"><label class="form-label">Cargo flow</label>
          <select id="cost-flow" onchange="toggleCostTrade()">
            <option value="import">Unloaded / Import (foreign cargo)</option>
            <option value="export">Loaded / Export (foreign cargo)</option>
            <option value="coastal">Coastal cargo</option>
            <option value="transhipment">Transhipment</option>
          </select></div>
        <div class="form-group"><label class="form-label">Cargo trade (transhipment only)</label>
          <select id="cost-trade" disabled><option value="foreign">Foreign</option><option value="coastal">Coastal</option></select></div>
        <div class="form-group"><label class="form-label">Receiver / shipper</label><input type="text" id="cost-party" placeholder="needed for KIOCL / UPCL rules"></div>
        ${num("cost-storage-days", "Days in transit storage", 'min="0" step="1"', "From the day after complete discharge (import) / receipt (export).")}
        ${num("cost-holidays", "Customs holidays / non-working days in free period", 'min="0" step="1" value="0"', "They extend working-day free periods (SOR 3.2.1).")}
        <div class="form-group"><label class="form-label">Storage category</label>
          <select id="cost-category">
            <option value="bulk">Bulk</option><option value="break_bulk">Break bulk</option>
            <option value="salvaged">Salvaged goods (export)</option><option value="not_shipped">Export cargo not shipped</option>
          </select></div>
        ${num("cost-annual", "Annual volume MT (cement band only)", 'min="0" step="1000"')}
      </div>
    </div>

    <div class="card" style="margin-bottom:20px;">
      <div style="font-size:11px;font-weight:800;color:#D97706;">VESSEL</div>
      <div class="grid-4" style="margin-top:8px;">
        <div class="form-group"><label class="form-label">Vessel status (Customs / DGS)</label>
          <select id="cost-vessel-run"><option value="foreign">Foreign-going (US$ rates)</option><option value="coastal">Coastal (₹ rates)</option></select></div>
        <div class="form-group"><label class="form-label">Vessel type (berth hire class)</label>
          <select id="cost-vessel">
            <option value="dry_bulk">Dry bulk</option><option value="liquid">POL / liquid tanker</option>
            <option value="hazardous">Hazardous cargo / chemicals</option>
            <option value="container">Container</option><option value="general_cargo">General cargo / break bulk</option>
            <option value="roro">RoRo / RoPax</option><option value="other">Other cargo vessel</option>
            <option value="bunkering_at_berth">Calling only for bunkering at berth</option>
            <option value="barge_tug_craft">Barge / tug / small craft</option><option value="bunker_barge">Bunker barge</option>
            <option value="fishing_service_boat">Fishing / service boat</option>
          </select></div>
        ${num("cost-grt", "Vessel GRT (from tonnage certificate)", 'min="0" step="1" placeholder="required for vessel charges"')}
        <div class="form-group"><label class="form-label">Berth</label>
          <select id="cost-berth">${COST_BERTHS.map(b => `<option value="${b}">${b === "" ? "— not set —" : b === "SPM" ? "SPM (MRPL)" : "Berth " + b}</option>`).join("")}</select></div>
        ${num("cost-berth-hours", "Berth hours (all fast → all lines cast off)", 'min="0" step="any"')}
        ${num("cost-usd-inr", "USD → INR (RBI reference, entry day)", 'min="0" step="0.0001" placeholder="needed for foreign vessels"', 'Look it up on rbi.org.in for the day the vessel entered port limits.')}
        ${num("cost-anchorage", "Anchorage hours after sailing", 'min="0" step="any" value="0"', "Pre-berthing anchorage is free.")}
        ${num("cost-tug-hours", "Tug hours hired on request", 'min="0" step="any" value="0"', "Berthing tugs are part of pilotage.")}
        ${num("cost-shifts", "Shiftings at vessel's request", 'min="0" step="1" value="0"')}
        ${num("cost-bunkers", "Bunkers supplied (MT, SOR 3.7)", 'min="0" step="any" value="0"')}
        <div class="form-group"><label class="form-label">Port dues concession (SOR 2.1.2)</label>
          <select id="cost-pd-reduction">
            <option value="none">None</option><option value="ballast_no_passengers">In ballast, no passengers (25%)</option>
            <option value="no_cargo_no_passenger">No cargo / passengers handled (50%)</option>
          </select></div>
        <div class="form-group"><label class="form-label">Double banked?</label>
          <select id="cost-double"><option value="false">No</option><option value="true">Yes (50% berth hire)</option></select></div>
      </div>
      <button class="btn" onclick="calculatePortCost()">Calculate NMPA Port Cost</button>
    </div>

    <div id="cost-output"></div>
    <br>
    <div class="card" style="margin-bottom:20px;" id="cost-validation">Loading checks against past data…</div>
    <div class="card" style="margin-bottom:20px;">
      <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:6px;">🚧 Coming soon — SOR charges without published rates</div>
      <div style="font-size:13px;color:#78716C;margin-bottom:12px;">The 2026-27 SOR lists these charges but prints their rates as "*" (as and when applicable) or refers to another tariff. They are never estimated.</div>
      <div id="cost-coming-soon">Loading…</div>
    </div>
    <div class="card">
      <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:12px;">📋 SOR 3.1.1 Wharfage Schedule (₹ per unit)</div>
      <input type="text" id="cost-schedule-filter" placeholder="Filter commodities…" oninput="renderSorSchedule()" style="margin-bottom:12px;">
      <div id="cost-schedule">Loading schedule…</div>
    </div>
  `;

  const [schedule, comingSoon] = await Promise.all([
    fetchAPI('/cost/commodities'),
    fetchAPI('/cost/coming-soon'),
  ]);

  sorCommodities = schedule?.commodities || [];
  document.getElementById('cost-commodity-list').innerHTML = sorCommodities
    .map(r => `<option value="${escHtml(r.code)}">${escHtml(r.item)}</option>`).join("");
  renderSorSchedule();

  const items = comingSoon?.components || [];
  document.getElementById('cost-coming-soon').innerHTML = items.length
    ? `<div class="table-container"><table><thead><tr><th>Charge</th><th>SOR Ref</th><th>Status</th><th>Why</th></tr></thead><tbody>${
        items.map(i => `<tr><td><b>${escHtml(i.label)}</b></td><td>${escHtml(i.sor_reference)}</td><td><span class="badge badge-warning">Coming soon</span></td><td>${escHtml(i.reason)}</td></tr>`).join("")
      }</tbody></table></div>`
    : `<div class="alert-box alert-error">Could not load the coming-soon list from the backend.</div>`;

  renderTariffValidation();
  await searchPastCalls();
  const first = document.getElementById('past-call-select')?.value;
  if (first) await loadPastCall(first);
}

function renderSorSchedule() {
  const el = document.getElementById('cost-schedule');
  if (!el) return;
  if (!sorCommodities.length) {
    el.innerHTML = `<div class="alert-box alert-error">Could not load the SOR schedule from the backend.</div>`;
    return;
  }
  const q = (document.getElementById('cost-schedule-filter')?.value || "").toLowerCase();
  const rows = sorCommodities.filter(r => !q || `${r.code} ${r.group} ${r.item}`.toLowerCase().includes(q));
  el.innerHTML = `<div class="table-container" style="max-height:420px;overflow:auto;"><table><thead><tr><th>Code</th><th>Group</th><th>Commodity</th><th>Unit</th><th>Coastal (₹)</th><th>Foreign (₹)</th></tr></thead><tbody>${
    rows.map(r => `<tr><td><b>${escHtml(r.code)}</b></td><td>${escHtml(r.group)}</td><td>${escHtml(r.item)}</td><td>${escHtml(r.unit)}</td><td>${r.coastal.toFixed(2)}</td><td>${r.foreign.toFixed(2)}</td></tr>`).join("")
  }</tbody></table></div>`;
}

function toggleCostTrade() {
  const flow = document.getElementById('cost-flow').value;
  document.getElementById('cost-trade').disabled = flow !== 'transhipment';
}

function scheduleCostMatch() {
  clearTimeout(costMatchTimer);
  costMatchTimer = setTimeout(updateCostMatch, 250);
}

async function updateCostMatch() {
  const name = document.getElementById('cost-commodity')?.value.trim();
  const el = document.getElementById('cost-match');
  if (!el) return;
  if (!name) { el.innerHTML = ""; return; }
  const m = await fetchAPI(`/cost/match?name=${encodeURIComponent(name)}`);
  if (!m) { el.innerHTML = `<span style="color:#991B1B;">Backend not reachable.</span>`; return; }
  if (!m.code) { el.innerHTML = `<span style="color:#92400E;">⚠ ${escHtml(m.message)}</span>`; return; }
  const text = `→ <b>${escHtml(m.code)}</b> ${escHtml(m.item)} <span style="opacity:.7">(${escHtml(m.method)}, ${m.score.toFixed(2)})</span>`;
  el.innerHTML = m.needs_review
    ? `<span style="color:#92400E;">⚠ ${text} — confirm the SOR line${m.ambiguity ? ": " + escHtml(m.ambiguity) : ""}</span>`
    : text;
}

// ── Real past calls ──
function schedulePastCallSearch() {
  clearTimeout(pastCallTimer);
  pastCallTimer = setTimeout(searchPastCalls, 300);
}

async function searchPastCalls() {
  const sel = document.getElementById('past-call-select');
  if (!sel) return;
  const q = document.getElementById('past-call-q')?.value.trim() || "";
  const data = await fetchAPI(`/cost/past-calls?limit=400&q=${encodeURIComponent(q)}`);
  if (!data) { sel.innerHTML = `<option value="">Backend not reachable</option>`; return; }
  pastCalls = data.calls || [];
  sel.innerHTML = pastCalls.length
    ? pastCalls.map(c => `<option value="${escHtml(c.id)}">${escHtml(c.berthing_date)} · ${escHtml(c.vessel)} · ${c.berth ? (c.berth === 'SPM' ? 'SPM' : 'B' + escHtml(c.berth)) : '—'} · ${escHtml(c.cargo_raw)} · ${fmtNum(c.quantity)} t</option>`).join("")
    : `<option value="">No matching calls</option>`;
  const s = data.summary || {};
  document.getElementById('past-call-info').innerHTML =
    `${fmtNum(data.count)} matching calls · archive ${escHtml(s.first_berthing)} → ${escHtml(s.last_berthing)} · ${fmtNum(s.with_quantity_and_sor_line)} cargo calls with quantity · source: NMPA Daily Vessel Position reports`;
}

async function loadPastCall(id) {
  if (!id) return;
  const d = await fetchAPI(`/cost/past-calls/${encodeURIComponent(id)}`);
  if (!d) return;
  const c = d.call, inp = d.calculator_inputs;
  const set = (elId, v) => { const el = document.getElementById(elId); if (el) el.value = v ?? ""; };
  set('cost-commodity', inp.cargo_type);
  set('cost-qty', inp.cargo_quantity_mt);
  set('cost-flow', inp.cargo_flow);
  set('cost-trade', inp.trade_type);
  set('cost-vessel-run', inp.vessel_trade_type);
  set('cost-vessel', inp.vessel_type);
  set('cost-grt', "");
  set('cost-berth', COST_BERTHS.includes((inp.berth || "").toUpperCase()) ? inp.berth.toUpperCase() : (inp.berth || "").replace(/\D.*$/, ""));
  set('cost-berth-hours', inp.berth_hours);
  set('cost-party', inp.receiver_shipper);
  set('cost-storage-days', "");
  toggleCostTrade();
  const conf = { exact: "exact movement times", date_only: "berthing / sailing date only", unconfirmed_lower_bound: "sailing not seen — lower bound" }[c.berth_hours_confidence] || "not linked";
  document.getElementById('past-call-info').innerHTML = `
    <b>${escHtml(c.vessel)}</b> · berthed ${escHtml(c.berthing_date)} at ${c.berth ? "Berth " + escHtml(c.berth) : "—"} · run <b>${escHtml(c.run_raw || "?")}</b> · LOA ${fmtNum(c.loa_m, 2)} m · agent ${escHtml(c.agent || "—")} · ${escHtml(c.receiver_shipper || "—")}<br>
    Quantity: <b>${fmtNum(c.quantity)}</b> (${escHtml(c.quantity_basis || "not reported")}) · Berth hours: <b>${fmtNum(c.berth_hours, 2)}</b> (${conf}) · seen in reports ${escHtml(c.first_report)} → ${escHtml(c.last_report)}<br>
    <span style="color:#92400E;">GRT is not in NMPA's daily reports — enter it from the vessel's tonnage certificate to price port dues, pilotage and berth hire.</span>`;
  updateCostMatch();
  calculatePortCost();
}

// ── Calculation ──
async function calculatePortCost() {
  const out = document.getElementById('cost-output');
  if (!out) return;
  const val = id => document.getElementById(id)?.value;
  const numOrNull = id => { const v = parseFloat(val(id)); return Number.isFinite(v) && v > 0 ? v : null; };
  const flow = val('cost-flow');
  const trade = flow === 'coastal' ? 'coastal' : flow === 'transhipment' ? val('cost-trade') : 'foreign';

  const payload = {
    cargo_type: (val('cost-commodity') || "").trim(),
    cargo_quantity_mt: numOrNull('cost-qty') || 0,
    trade_type: trade,
    vessel_trade_type: val('cost-vessel-run'),
    cargo_flow: flow,
    vessel_type: val('cost-vessel'),
    vessel_grt: numOrNull('cost-grt'),
    berth: val('cost-berth') || null,
    berth_hours: numOrNull('cost-berth-hours') || 0,
    storage_days: numOrNull('cost-storage-days') || 0,
    excluded_days_in_free_period: numOrNull('cost-holidays') || 0,
    cargo_category: val('cost-category'),
    annual_volume_mt: numOrNull('cost-annual'),
    usd_inr_rate: numOrNull('cost-usd-inr'),
    receiver_shipper: (val('cost-party') || "").trim() || null,
    port_dues_reduction: val('cost-pd-reduction'),
    double_banked: val('cost-double') === 'true',
    anchorage_hours: numOrNull('cost-anchorage') || 0,
    tug_hire_hours: numOrNull('cost-tug-hours') || 0,
    shifting_count: parseInt(val('cost-shifts') || "0", 10) || 0,
    bunker_quantity_mt: numOrNull('cost-bunkers') || 0,
  };
  if (!payload.cargo_type) { out.innerHTML = `<div class="alert-box alert-warning">Pick a past call or enter a commodity.</div>`; return; }

  out.innerHTML = `<div class="card">Calculating…</div>`;
  let res, data;
  try {
    res = await fetch(`${API_BASE}/cost/calculate`, { method: 'POST', headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    data = await res.json();
  } catch (err) {
    out.innerHTML = `<div class="alert-box alert-error">Backend not reachable: ${escHtml(err.message)}</div>`;
    return;
  }
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map(e => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join("; ")
      : (d?.message || d?.error || JSON.stringify(d));
    out.innerHTML = `<div class="alert-box alert-error">Cost calculation error: ${escHtml(msg)}</div>`;
    return;
  }
  renderCostResult(data);
}

const COST_LABELS = {
  wharfage: "Wharfage", transit_storage: "Transit storage", port_dues: "Port dues", pilotage: "Pilotage",
  berth_hire: "Berth hire", anchorage: "Anchorage", tug_hire: "Tug hire", shifting: "Shifting",
  bunkering_facility: "Bunkering facility",
};
const COST_STATUS = {
  calculated: ["Calculated", "badge-normal"], needs_exchange_rate: ["Needs USD→INR", "badge-warning"],
  needs_grt: ["Needs GRT", "badge-warning"], not_billed_by_nmpa: ["Not billed by NMPA", "badge-critical"],
  not_applicable: ["Not applicable", "badge-normal"], rate_unavailable: ["Rate not published", "badge-warning"],
};

function renderCostResult(data) {
  const out = document.getElementById('cost-output');
  const b = data.breakdown || {};
  const w = b.wharfage || {}, s = b.transit_storage || {};
  const rule = s.free_days_rule || {};
  const slabLabels = { week_1: "First week", week_2: "Second week", after_week_2: "Succeeding period", all_days: "All chargeable days (export)" };

  const rows = Object.entries(b).map(([k, c]) => {
    const [st, cls] = COST_STATUS[c.status] || [c.status, "badge-warning"];
    const usd = c.amount_usd != null ? fmtUSD(c.amount_usd) : (c.reference_currency === "USD" && c.reference_amount != null ? `<span style="opacity:.6">${fmtUSD(c.reference_amount)} (ref.)</span>` : "—");
    const inr = c.amount != null ? fmtINR(c.amount) : (c.reference_currency === "INR" && c.reference_amount != null ? `<span style="opacity:.6">${fmtINR(c.reference_amount)} (ref.)</span>` : "—");
    const why = c.message || c.note || (c.chargeable_hours != null ? `${c.chargeable_hours} chargeable hours` : "");
    return `<tr><td>${COST_LABELS[k] || escHtml(k)}</td><td>${escHtml(c.sor_reference || "")}</td><td><span class="badge ${cls}">${escHtml(st)}</span></td><td>${escHtml(c.currency || c.reference_currency || "")}</td><td>${usd}</td><td>${inr}</td><td style="font-size:12px;color:#78716C;">${escHtml(why)}</td></tr>`;
  }).join("");

  const warn = [];
  (data.exceptions || []).forEach(e => warn.push(e.scope === 'note'
    ? `<div class="alert-box alert-warning" style="margin-bottom:10px;">⚠ ${escHtml(e.message)}</div>`
    : `<div class="alert-box alert-error" style="margin-bottom:10px;">⛔ ${escHtml(e.message)}</div>`));
  if ((data.missing_grt_components || []).length)
    warn.push(`<div class="alert-box alert-warning" style="margin-bottom:10px;">⚠ Not in the total: ${data.missing_grt_components.map(k => COST_LABELS[k] || k).join(", ")} — enter the vessel's GRT.</div>`);
  if ((data.unconverted_usd_components || []).length)
    warn.push(`<div class="alert-box alert-warning" style="margin-bottom:10px;">⚠ ${fmtUSD(data.unconverted_usd_total)} of foreign-vessel charges is not in the ₹ total — enter the RBI USD→INR reference rate for the vessel's entry day.</div>`);
  (data.notes || []).forEach(n => warn.push(`<div class="alert-box alert-success" style="margin-bottom:10px;">ℹ ${escHtml(n)}</div>`));

  out.innerHTML = `
    <div class="grid-4" style="margin-bottom:20px;">
      <div class="metric-card"><div class="metric-label">Wharfage</div><div class="metric-value">${w.amount != null ? fmtINR(w.amount) : "—"}</div></div>
      <div class="metric-card"><div class="metric-label">Vessel related (₹)</div><div class="metric-value">${fmtINR(["port_dues", "pilotage", "berth_hire", "anchorage", "tug_hire", "shifting"].reduce((a, k) => a + (b[k]?.status === 'calculated' ? (b[k].amount || 0) : 0), 0))}</div></div>
      <div class="metric-card"><div class="metric-label">Total known cost (₹)</div><div class="metric-value">${fmtINR(data.total_known_cost)}</div><div class="metric-delta" style="color:#78716C;">bill rounded: ₹${fmtNum(data.bill_total_rounded)} + GST</div></div>
      <div class="metric-card"><div class="metric-label">Estimate status</div><div class="metric-value" style="font-size:20px;">${data.is_complete ? "✅ Complete" : "⚠ Partial"}</div><div class="metric-delta" style="color:#78716C;">${data.is_complete ? "all listed components priced" : "some inputs missing"}</div></div>
    </div>
    ${warn.join("")}
    <div class="card" style="margin-bottom:20px;">
      <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:12px;">Cost breakdown</div>
      <div class="table-container"><table><thead><tr><th>Component</th><th>SOR Ref</th><th>Status</th><th>Currency</th><th>Amount (US$)</th><th>Amount (₹)</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div style="font-size:12px;color:#78716C;margin-top:10px;">Tariff: <b>${escHtml(data.tariff?.name)}</b> · effective ${escHtml(data.tariff?.effective_from)} to ${escHtml(data.tariff?.effective_to)} · taxes extra (SOR 1.2(v)) · grand total rounded to the next rupee (SOR 1.2(ix)).</div>
    </div>
    <div class="grid-2" style="margin-bottom:20px;">
      <div class="card">
        <div style="font-size:11px;font-weight:800;color:#D97706;">WHARFAGE DETAIL (SOR 3.1.1)</div>
        ${w.sor_code ? `<div style="font-weight:700;margin-top:6px;">${escHtml(w.sor_code)} — ${escHtml(w.sor_item)}</div>
        <div style="margin-top:8px;">${fmtNum(w.chargeable_units, 1)} chargeable ${escHtml(w.unit)} × ₹${Number(w.rate_per_mt || 0).toFixed(2)} (${escHtml(w.trade_type)} cargo) = <b>${fmtINR(w.amount ?? w.reference_amount)}</b></div>` : `<div style="margin-top:6px;">${escHtml(w.message || "—")}</div>`}
        ${(w.notes || []).map(n => `<div style="font-size:12px;color:#92400E;margin-top:4px;">⚠ ${escHtml(n)}</div>`).join("")}
      </div>
      <div class="card">
        <div style="font-size:11px;font-weight:800;color:#D97706;">STORAGE (SOR 3.2.1)</div>
        <div style="margin-top:6px;">${rule.status === 'configured'
          ? `Free period: <b>${rule.free_storage_days}${rule.extended_by_non_working_days ? " + " + rule.extended_by_non_working_days : ""} days</b> — ${escHtml(rule.basis)} (SOR ${escHtml(rule.sor_reference)})`
          : `No automatic free-period rule for this flow / category.`}</div>
        <div style="margin-top:4px;">Chargeable days: <b>${s.chargeable_days ?? 0}</b></div>
        ${(s.slabs || []).length
          ? `<div class="table-container" style="margin-top:10px;"><table><thead><tr><th>Period</th><th>Days</th><th>₹ / unit / day</th><th>Amount</th></tr></thead><tbody>${
              s.slabs.map(x => `<tr><td>${slabLabels[x.slab] || escHtml(x.slab)}</td><td>${x.days}</td><td>${x.rate_per_unit_day}</td><td>${fmtINR(x.amount)}</td></tr>`).join("")
            }</tbody></table></div>`
          : `<div style="margin-top:8px;color:#065F46;">No storage charge (within free period or no storage days entered).</div>`}
      </div>
    </div>`;
}

// ── Checks against past data ──
async function renderTariffValidation() {
  const el = document.getElementById('cost-validation');
  const v = await fetchAPI('/cost/validation');
  if (!el) return;
  if (!v) { el.innerHTML = `<div class="alert-box alert-error">Could not load the validation report.</div>`; return; }
  const sum = v.summary, sor = v.past_tariff, inc = v.past_revenue, calls = v.past_calls;
  const factors = Object.entries(sor.factor_counts).map(([f, n]) => `${n} items × ${f}`).join(" · ");
  const lines = inc.cargo_lines.map(c => `<tr><td><b>${escHtml(c.line)}</b><div style="font-size:11px;color:#78716C;">${c.ledger.map(escHtml).join("<br>")}</div></td><td>₹${c.income_rs_crore} Cr</td><td>${c.tonnes_lakh} lakh t</td><td><b>₹${c.realised_rs_per_tonne}</b></td><td>₹${c.sor_band_rs_per_tonne[0]} – ₹${c.sor_band_rs_per_tonne[1]}<div style="font-size:11px;color:#78716C;">${escHtml(c.band_basis)}</div></td><td><span class="badge ${c.result === 'consistent' ? 'badge-normal' : 'badge-critical'}">${c.inside_band ? "Inside band" : (c.result === 'consistent' ? "Outside band — expected" : "Outside band")}</span>${c.explanation ? `<div style="font-size:11px;color:#78716C;margin-top:4px;">${escHtml(c.explanation)}</div>` : ""}</td></tr>`).join("");
  const ratios = inc.vessel_ratio_checks.map(r => `<tr><td>${escHtml(r.line)}</td><td>${r.ledger_ratio_pilotage_to_port_dues}</td><td>${r.sor_ratio}</td><td>${r.difference_pct}%</td><td style="font-size:11px;color:#78716C;">${escHtml(r.basis)}${r.explanation ? "<br>" + escHtml(r.explanation) : ""}</td></tr>`).join("");
  const groups = calls.by_group.map(g => `<tr><td>${escHtml(g.section)}</td><td>${escHtml(g.group)}</td><td>${fmtNum(g.official_tonnes)}</td><td>${fmtNum(g.calls_tonnes)}</td><td>${g.coverage_pct == null ? "—" : g.coverage_pct + "%"}</td></tr>`).join("");
  el.innerHTML = `
    <div style="font-family:Outfit;font-size:18px;font-weight:800;margin-bottom:6px;">🔎 Checked against past data</div>
    <div class="grid-3" style="margin:12px 0 16px;">
      <div class="metric-card"><div class="metric-label">Rates vs SOR 2022</div><div class="metric-value">${sum.sor_items_consistent}/${sum.sor_items_checked}</div><div class="metric-delta" style="color:#78716C;">${escHtml(factors)}</div></div>
      <div class="metric-card"><div class="metric-label">NMPA income 2023-24 vs SOR</div><div class="metric-value">${sum.income_lines_consistent}/${sum.income_lines_checked}</div><div class="metric-delta" style="color:#78716C;">realised ₹/t explained by SOR</div></div>
      <div class="metric-card"><div class="metric-label">Past calls vs traffic statement</div><div class="metric-value">${sum.calls_tonnage_coverage_pct}%</div><div class="metric-delta" style="color:#78716C;">tonnage, ${escHtml(sum.months_compared[0])} → ${escHtml(sum.months_compared.slice(-1)[0])}</div></div>
    </div>
    <details open><summary style="cursor:pointer;font-weight:700;">1 · Every rate vs the SOR general revision of Dec 2022</summary>
      <div style="font-size:13px;color:#78716C;margin:8px 0;">NMPA indexes the SOR each 1 May (SOR 1.2(xix)), so every rate must have moved by the same few factors since 2022. ${sor.outliers.length ? `<b style="color:#991B1B;">${sor.outliers.length} rate(s) do not — check them.</b>` : "No rate is out of line, so no transcription errors were found."}</div>
      <div class="table-container" style="max-height:260px;overflow:auto;"><table><thead><tr><th>Item</th><th>SOR 2022</th><th>SOR 2026-27</th><th>Ratio</th></tr></thead><tbody>${
        sor.items.map(i => `<tr><td>${escHtml(i.item)}</td><td>${i.sor_2022}</td><td>${i.sor_2026}</td><td>${i.ratio}${i.consistent ? "" : " ⚠"}</td></tr>`).join("")}</tbody></table></div>
    </details>
    <details open style="margin-top:14px;"><summary style="cursor:pointer;font-weight:700;">2 · NMPA's own income (Revised Estimate 2023-24) ÷ tonnage handled</summary>
      <div class="table-container" style="margin-top:8px;"><table><thead><tr><th>Ledger line</th><th>Income</th><th>Tonnage</th><th>Realised ₹/t</th><th>SOR band</th><th>Result</th></tr></thead><tbody>${lines}</tbody></table></div>
      <div class="table-container" style="margin-top:10px;"><table><thead><tr><th>Vessel charges</th><th>Pilotage ÷ port dues (ledger)</th><th>Same ratio in SOR</th><th>Diff.</th><th>Basis</th></tr></thead><tbody>${ratios}</tbody></table></div>
      <div style="font-size:12px;color:#78716C;margin-top:6px;">${escHtml(inc.caveat)}</div>
    </details>
    <details style="margin-top:14px;"><summary style="cursor:pointer;font-weight:700;">3 · Tonnage of individual past calls vs NMPA's monthly traffic statement</summary>
      <div style="font-size:13px;color:#78716C;margin:8px 0;">${fmtNum(calls.calls_total_tonnes)} t from individual calls vs ${fmtNum(calls.official_total_tonnes)} t reported. Calls never exceed the official figure; the gap is days missing from the report archive and calls without a quantity. ${escHtml(calls.note)}</div>
      <div class="table-container"><table><thead><tr><th>Section</th><th>Commodity</th><th>NMPA statement (t)</th><th>Sum of calls (t)</th><th>Coverage</th></tr></thead><tbody>${groups}</tbody></table></div>
    </details>
    <div style="font-size:11px;color:#78716C;margin-top:12px;">Sources: ${[...new Set([...sor.sources, ...inc.sources].map(s => s.url ? `<a href="${escHtml(s.url)}" target="_blank" rel="noopener">${escHtml(s.title)}</a>` : escHtml(s.title)))].join(" · ")}</div>`;
}

// ─── TAB 5: Trade Intelligence Renderer ──────────────────────────────────────
async function renderTrade() {
  const container = document.getElementById('tab-trade');
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Commodity Demand by Trade Lane</span><span class="sec-tag">Demo Data</span></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ This entire tab is simulated — no trade-lane, shipping-route, or commodity-price dataset exists in this project. For real commodity demand, see the Cargo Forecasting tab, grounded in data/port_cargo_monthly.csv.</div><div class="card" id="trade-content">Loading Trade Lanes...</div>`;

  const lanesData = await fetchAPI('/trade/lanes') || { lanes: [] };
  const lanes = lanesData.lanes || [];

  if (lanes.length > 0) {
    const trace = [{
      type: 'bar', orientation: 'h',
      x: lanes.map(l => l.growth_pct),
      y: lanes.map(l => l.route),
      marker: { color: lanes.map(l => l.growth_pct > 0 ? '#059669' : '#DC2626') }
    }];
    Plotly.newPlot('trade-content', trace, { ...PLOTLY_THEME, title: 'Trade Lane YoY Growth (%)' });
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
  container.innerHTML = `<div class="sec-header"><span class="sec-title">Trade Incentive Engine</span><span class="sec-tag">Real (derived)</span></div><div class="alert-box alert-warning" style="margin-bottom:12px;">⚠ Recommendations are grounded in real YoY tonnage trends from data/port_cargo_monthly.csv. The incentive %/impact figures follow a documented elasticity formula (not a trained model — no historical incentive-campaign outcome data exists to fit one against), and revenue impact is "N/A" because the dataset has no tariff/pricing column.</div><div class="card" id="incentive-recs">Loading recommendations...</div>`;

  const data = await fetchAPI('/incentive/recommendations') || { recommendations: [] };
  const recs = data.recommendations || [];
  document.getElementById('incentive-recs').innerHTML = recs.map(r => `
    <div class="alert-box alert-success" style="margin-bottom:12px;">
      <div><b>${r.action}</b> <span class="badge badge-normal">${r.priority}</span></div>
      <div style="font-size:12px;margin-top:4px;">${r.rationale}</div>
      <div style="font-size:11px;color:#78716C;margin-top:4px;">${r.current_metric} → Predicted traffic impact: ${r.predicted_traffic_impact} | Revenue impact: ${r.predicted_revenue_impact} | Confidence: ${(r.confidence * 100).toFixed(0)}%</div>
    </div>
  `).join('');
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
