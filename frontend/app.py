"""
YellowSense Maritime Intelligence Platform
==========================================
AI-Powered Maritime Port Intelligence & Decision Support Platform
Production-grade PoC — Warm Amber Theme, 9-Tab Horizontal Navigation
"""

import html
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import requests
from datetime import datetime, timezone
from pathlib import Path
import base64
import time
import os

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YellowSense Maritime Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Constants ────────────────────────────────────────────────────────────────
API = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo11.png"
ARCH_DIR = Path(__file__).parent.parent

COMMODITY_COLORS = {
    "Coal": "#374151", "Iron Ore": "#DC2626", "Containers": "#2563EB",
    "Crude Oil": "#7C3AED", "LNG": "#059669", "Fertilizers": "#D97706",
    "Automobiles": "#0891B2", "Agricultural": "#65A30D",
}

SEVERITY_COLORS = {"Critical": "#DC2626", "High": "#D97706", "Medium": "#2563EB", "Low": "#059669"}
SEVERITY_BG = {"Critical": "#FEF2F2", "High": "#FFFBEB", "Medium": "#EFF6FF", "Low": "#F0FDF4"}

# ─── API Helper ───────────────────────────────────────────────────────────────
# Full-width display on any Streamlit version: newer versions take width="stretch"; older ones use_container_width=True.
import inspect as _insp_w
def _fullw(fn):
    try:
        return {"width": "stretch"} if "width" in _insp_w.signature(fn).parameters else {"use_container_width": True}
    except (TypeError, ValueError):
        return {"use_container_width": True}
_W_CHART, _W_DF, _W_IMG = _fullw(st.plotly_chart), _fullw(st.dataframe), _fullw(st.image)


def api_get(path: str, params: dict = None, timeout: float = 30):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"API GET Error ({path}): {e}")
        return None

def _auth_headers() -> dict:
    """The logged-in user's token, sent with every action that changes data (pilot mode)."""
    tok = st.session_state.get("auth_token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def api_post(path: str, payload: dict = None):
    try:
        r = requests.post(headers=_auth_headers(), url=f"{API}{path}", json=payload or {}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"API POST Error ({path}): {e}")
        st.error(f"Backend API Error: {e}")
        return None

# ─── Logo Helper ──────────────────────────────────────────────────────────────
def get_logo_b64():
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# ─── Premium CSS — Cream / YellowSense Brand (Ref: Image 4) ── */
st.markdown("""
<style>
/* Using System Native Fonts */

/* ── Reset & Base ── */
html, body, [class*="css"] { font-family: system-ui, sans-serif; }
h1,h2,h3,h4,h5,h6 { font-family: system-ui, sans-serif; }

/* ── App Background — Very Pale Cream ── */
.stApp {
    background: #FCFAF5;
    color: #292524;
    min-height: 100vh;
}
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem;
    max-width: 1200px !important;
}

/* ── Hide default Streamlit chrome ── */
#MainMenu, footer, header, [data-testid="stSidebarNav"] { visibility: hidden; }
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }

/* ── Floating Header Card ── */
.ys-header {
    background: #FFFDF9;
    padding: 16px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    margin-bottom: 20px;
    border: 1px solid #F3E8D6;
}
.ys-header-left {
    display: flex;
    align-items: center;
    gap: 16px;
}
.ys-header-logo {
    height: 48px;
    width: auto;
    object-fit: contain;
}
.ys-header-title {
    font-family: system-ui, sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: #1C1917;
    letter-spacing: -0.3px;
    line-height: 1.1;
}
.ys-header-subtitle {
    font-size: 13px;
    color: #92400E;
    font-weight: 600;
}
.ys-header-right {
    display: flex;
    align-items: center;
}
.ys-live-badge {
    background: #FEF3C7;
    color: #92400E;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    border: 1px solid #FDE68A;
}

/* ── Tab Navigation Pills ── */
div.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    gap: 8px;
    border-bottom: none;
    margin-bottom: 20px;
}
div.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 20px;
    color: #78716C;
    font-family: system-ui, sans-serif;
    font-weight: 600;
    font-size: 13px;
    padding: 8px 18px;
    border: none;
    transition: all 0.2s ease;
}
div.stTabs [aria-selected="true"] {
    background: #FEF3C7 !important;
    color: #92400E !important;
    border-bottom: 2px solid #EF4444 !important;
    border-radius: 12px 12px 0 0;
    box-shadow: none !important;
}

/* ── Page Content Wrapper ── */
.ys-content {
    padding: 10px 0;
}

/* ── Section Headers ── */
.sec-title {
    font-family: system-ui, sans-serif;
    font-size: 24px;
    font-weight: 800;
    color: #1C1917;
    letter-spacing: -0.4px;
    margin: 0;
}
.sec-sub {
    font-size: 14px;
    color: #78716C;
    margin-top: 6px;
    margin-bottom: 24px;
}
.sec-tag { display: none; }

/* ── Cards / Panels ── */
.kpi-card, .panel, div[data-testid="stMetric"], .pipeline-stage, .copilot-response {
    background: #FFFFFF;
    border: 1px solid #F3E8D6;
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
}
.panel-title {
    font-family: system-ui, sans-serif;
    font-size: 16px;
    font-weight: 700;
    color: #1C1917;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #F9F5EC;
}

div[data-testid="stMetricLabel"] { font-size: 11px; font-weight: 700; color: #78716C !important; text-transform: uppercase; letter-spacing: 0.6px; }
div[data-testid="stMetricValue"] { font-family: system-ui, sans-serif; font-size: 28px; font-weight: 800; color: #1C1917 !important; }

/* ── Custom Button ── */
div.stButton > button {
    background: #EAB308 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: system-ui, sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 8px 24px !important;
    box-shadow: 0 2px 4px rgba(234,179,8,0.2) !important;
    transition: all 0.2s ease !important;
}
div.stButton > button:hover {
    background: #CA8A04 !important;
    box-shadow: 0 4px 8px rgba(202,138,4,0.3) !important;
}

/* ── Trace Steps & Logs ── */
.trace-step {
    display: flex; align-items: flex-start; gap: 14px;
    padding: 12px 16px; border-radius: 8px; margin-bottom: 8px;
    background: #FCFAF5; border: 1px solid #F3E8D6;
}
.trace-num {
    background: #EAB308; color: #FFFFFF;
    font-family: system-ui, sans-serif; font-weight: 800; font-size: 13px;
    width: 26px; height: 26px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.trace-component { font-weight: 700; font-size: 13px; color: #1C1917; }
.trace-action    { font-size: 13px; color: #44403C; }
.trace-detail    { font-size: 11px; color: #78716C; margin-top: 2px; }
.trace-ms        { font-size: 11px; color: #CA8A04; font-weight: 600; margin-left: auto; }

.log-container {
    background: #FCFAF5; border: 1px solid #F3E8D6; border-radius: 10px;
    padding: 16px; max-height: 340px; overflow-y: auto;
    font-family: 'JetBrains Mono', 'Courier New', monospace; font-size: 12px;
}
.log-row { padding: 4px 0; border-bottom: 1px solid #F9F5EC; display: flex; gap: 10px; }
.log-ts   { color: #A8A29E; min-width: 65px; }
.log-src  { color: #1C1917; font-weight: 700; min-width: 95px; }
.log-info { color: #57534E; }
.log-warn { color: #D97706; }

.stDataFrame { border: 1px solid #F3E8D6; border-radius: 8px; }
.stTextArea textarea { border: 1px solid #F3E8D6 !important; border-radius: 8px !important; background: #FFFFFF !important; }
.stTextArea textarea:focus { border-color: #EAB308 !important; box-shadow: 0 0 0 2px rgba(234,179,8,0.2) !important; }
.stSpinner > div { border-top-color: #EAB308 !important; }

/* ── Restored Missing Components ── */
.alert-card { border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; border-left: 4px solid; }
.alert-critical { background: #FEF2F2; border-color: #DC2626; }
.alert-high     { background: #FFFBEB; border-color: #D97706; }
.alert-medium   { background: #EFF6FF; border-color: #2563EB; }
.alert-low      { background: #F0FDF4; border-color: #059669; }
.alert-title    { font-family: system-ui, sans-serif; font-size: 14px; font-weight: 700; color: #1C1917; }
.alert-desc     { font-size: 12px; color: #78716C; margin-top: 5px; line-height: 1.5; }
.alert-meta     { font-size: 11px; color: #92400E; margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; }
.badge          { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
.badge-crit     { background: #FEE2E2; color: #DC2626; }
.badge-high     { background: #FEF3C7; color: #D97706; }
.badge-med      { background: #DBEAFE; color: #2563EB; }
.badge-low      { background: #DCFCE7; color: #059669; }

.rec-card { background: #FFFFFF; border: 1px solid #F3E8D6; border-radius: 12px; padding: 18px 20px; margin-bottom: 14px; border-left: 5px solid #F59E0B; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
.rec-action     { font-family: system-ui, sans-serif; font-size: 15px; font-weight: 700; color: #1C1917; }
.rec-rationale  { font-size: 12px; color: #78716C; margin-top: 5px; line-height: 1.5; }
.rec-impacts    { display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap; }
.rec-impact-pos { color: #059669; font-size: 13px; font-weight: 700; }
.rec-impact-neg { color: #DC2626; font-size: 13px; font-weight: 700; }
.rec-meta       { font-size: 11px; color: #92400E; margin-top: 8px; display: flex; gap: 14px; flex-wrap: wrap; }

.event-row { display: flex; align-items: flex-start; gap: 12px; padding: 10px 0; border-bottom: 1px solid #F3E8D6; }
.event-time { font-size: 11px; color: #78716C; min-width: 48px; font-weight: 600; }
.event-dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.event-dot-arrival  { background: #059669; }
.event-dot-alert    { background: #DC2626; }
.event-dot-departure{ background: #2563EB; }
.event-dot-forecast { background: #7C3AED; }
.event-dot-incentive{ background: #F59E0B; }
.event-dot-system   { background: #78716C; }
.event-msg  { font-size: 12.5px; color: #1C1917; line-height: 1.4; }

.opp-card { background: #FFFFFF; border: 1px solid #F3E8D6; border-left: 5px solid #F59E0B; border-radius: 12px; padding: 16px 18px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.02); }
.opp-rank        { font-family: system-ui, sans-serif; font-size: 24px; font-weight: 900; color: #F59E0B; }
.opp-commodity   { font-size: 13px; font-weight: 700; color: #92400E; }
.opp-route       { font-size: 12px; color: #57534E; margin: 3px 0; }
.opp-opportunity { font-size: 12px; color: #1C1917; line-height: 1.5; margin-top: 6px; }
.opp-metrics     { display: flex; gap: 14px; margin-top: 10px; }
.opp-revenue     { font-size: 15px; font-weight: 800; color: #059669; font-family: system-ui, sans-serif; }

.pipeline-stage-title { font-family: system-ui, sans-serif; font-size: 14px; font-weight: 700; color: #1C1917; margin-bottom: 6px; }
.pipeline-stage-sub   { font-size: 11px; color: #78716C; line-height: 1.4; }

/* Plotly Theme Updates */
.js-plotly-plot .plotly { border-radius: 10px; overflow: hidden; background: #FFFFFF; }

</style>
""", unsafe_allow_html=True)

# ─── Header ───────────────────────────────────────────────────────────────────
logo_b64 = get_logo_b64()
logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="ys-header-logo" />' if logo_b64 else ""
ts = datetime.now(timezone.utc).strftime("%d %b %Y  %H:%M UTC")

st.markdown(f"""
<div class="ys-header">
  <div class="ys-header-left">
    {logo_html}
    <div>
      <div class="ys-header-title">Maritime Intelligence Platform</div>
      <div class="ys-header-subtitle">AI-POWERED PREDICTIVE CARGO ANALYTICS & DECISION SUPPORT SYSTEM</div>
    </div>
  </div>
  <div class="ys-header-right">
    <div class="ys-live-badge">
      <div class="ys-live-dot"></div>
      LIVE DATA
    </div>
    <div class="ys-timestamp">{ts}</div>
  </div>
</div>

<div style="background: linear-gradient(135deg, #FFFDF9 0%, #FEF3C7 100%); border: 1px solid #FDE68A; border-radius: 14px; padding: 16px 24px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
  <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
    <div>
      <div style="font-size: 11px; font-weight: 800; color: #D97706; letter-spacing: 0.8px; text-transform: uppercase;">PRIMARY CORE CAPABILITY</div>
      <div style="font-size: 20px; font-weight: 800; color: #1C1917; margin-top: 2px;">Predictive Cargo Analytics — See What's Coming. Plan Ahead.</div>
      <div style="font-size: 13px; color: #78716C; margin-top: 4px; line-height: 1.4;">
        <b>Operational Flow:</b> Historical Cargo Data &rarr; ML Analysis &rarr; Cargo Forecast &rarr; Commodity & Trade Demand &rarr; Risk & Anomaly Detection &rarr; Port Planning Decisions
      </div>
    </div>
    <div style="background: #FFFFFF; border: 1px solid #F3E8D6; padding: 8px 18px; border-radius: 20px; font-size: 12px; font-weight: 700; color: #92400E; display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
      <span>⚓</span> <span>Core Capability: Cargo Volume & Arrival Forecasting</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── Plotly Theme ─────────────────────────────────────────────────────────────
PLOTLY_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#FFFFFF",
    font=dict(family="system-ui, sans-serif", color="#1C1917", size=13),
    margin=dict(l=20, r=20, t=40, b=20),
    xaxis=dict(gridcolor="#F9F5EC", linecolor="#E5E7EB", tickfont=dict(color="#1C1917", size=12), title=dict(font=dict(color="#1C1917", size=14, weight="bold"))),
    yaxis=dict(gridcolor="#F9F5EC", linecolor="#E5E7EB", tickfont=dict(color="#1C1917", size=12), title=dict(font=dict(color="#1C1917", size=14, weight="bold"))),
)
GOLD = "#F59E0B"
GOLD_DARK = "#D97706"
GOLD_LIGHT = "#FDE68A"

# ─── Tab Navigation ───────────────────────────────────────────────────────────
# ── Login (pilot mode) / demo-mode notice ──────────────────────────────────────────────────────────────────────
_mode = api_get("/auth/mode") or {}
if _mode.get("pilot_mode"):
    _who = st.session_state.get("auth_user")
    if _who:
        _l1, _l2 = st.columns([0.85, 0.15])
        _l1.markdown(f"Logged in as **{_who['full_name']}** ({_who['role']}). Actions you take are recorded under your name.")
        if _l2.button("Log out", key="auth_logout"):
            try:
                requests.post(f"{API}/auth/logout", headers=_auth_headers(), timeout=10)
            except requests.RequestException:
                pass
            st.session_state.pop("auth_token", None)
            st.session_state.pop("auth_user", None)
            st.rerun()
    else:
        with st.expander("Log in (pilot mode: recording responses, notes and scheme steps needs a login)", expanded=False):
            _u1, _u2, _u3 = st.columns([0.35, 0.35, 0.3], vertical_alignment="bottom")
            _un = _u1.text_input("Username", key="auth_un")
            _pw = _u2.text_input("Password", type="password", key="auth_pw")
            if _u3.button("Log in", key="auth_login", type="primary"):
                try:
                    _r = requests.post(f"{API}/auth/login", json={"username": _un, "password": _pw}, timeout=10)
                    if _r.ok:
                        _j = _r.json()
                        st.session_state["auth_token"] = _j["token"]
                        st.session_state["auth_user"] = {"full_name": _j["full_name"], "role": _j["role"]}
                        st.rerun()
                    else:
                        st.error(_r.json().get("detail", "Could not log in."))
                except requests.RequestException:
                    st.error("Could not reach the backend.")
elif _mode:
    st.caption("Demo mode: no users are set up, so recorded actions are not attributable to a person and are not for real "
               "decisions. For a pilot, set up users with scripts/manage_users.py.")

tabs = st.tabs([
    "Executive Dashboard",
    "\u2b50 Vessel Intelligence",
    "⭐ Cargo Forecasting",
    "\u2b50 Trade Intelligence",
    "Anomaly Detection",
    "\u2b50 Incentive Engine",
    "Digital Twin",
    "AI Maritime Copilot",
    "Data Pipeline",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — EXECUTIVE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Executive Command Center</span>
      <span class="sec-tag">Demo Data</span>
      <div class="sec-sub">Port-wide operational overview — KPIs, vessel positions, berth utilization & revenue</div>
    </div>""", unsafe_allow_html=True)
    st.caption("⚠ Revenue (₹ Cr), KPI deltas, and port events on this tab are simulated — no financial/pricing dataset exists in this project. Berth utilization below is real (data/berths.csv + latest cargo tonnage); vessel positions are the same illustrative fleet used in the Vessel Intelligence tab.")

    kpis = api_get("/executive/kpis") or {
        "berth_utilization_pct": 72.4, "berth_delta": "+2.1%",
        "active_vessels_inbound": 25, "vessels_delta": "+3",
        "daily_throughput_mt": 124000, "throughput_delta": "+3.2%",
        "revenue_cr": 118.5, "revenue_delta": "+6.8%",
        "congestion_index": 0.63, "congestion_delta": "-0.04",
        "vessels_at_anchor": 7, "anchor_delta": "+2",
        "avg_turnaround_hrs": 22.4, "turnaround_delta": "-1.2%",
        "forecast_accuracy_pct": 91.2, "accuracy_delta": "+0.8%",
    }

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Berth Utilization", f"{kpis['berth_utilization_pct']}%", kpis['berth_delta'])
        st.metric("Avg Turnaround", f"{kpis['avg_turnaround_hrs']}h", kpis['turnaround_delta'])
    with c2:
        st.metric("Vessels Inbound", str(kpis['active_vessels_inbound']), kpis['vessels_delta'])
        st.metric("Vessels at Anchor", str(kpis['vessels_at_anchor']), kpis['anchor_delta'])
    with c3:
        st.metric("Daily Throughput", f"{kpis['daily_throughput_mt']:,} MT", kpis['throughput_delta'])
        st.metric(
            "Forecast Accuracy" + (" (ML)" if kpis.get("forecast_accuracy_is_ml") else ""),
            f"{kpis['forecast_accuracy_pct']}%", kpis['accuracy_delta']
        )
    with c4:
        st.metric("Revenue Index", f"₹{kpis['revenue_cr']} Cr", kpis['revenue_delta'])
        st.metric(
            "Congestion Index" + (" (ML)" if kpis.get("congestion_index_is_ml") else ""),
            f"{kpis['congestion_index']}", kpis['congestion_delta']
        )

    st.markdown("<br>", unsafe_allow_html=True)
    col_left, col_right = st.columns([3, 2])

    with col_left:
        # NMPA Vessel Map
        vessels_data = api_get("/vessels/") or {"vessels": []}
        vessels = vessels_data.get("vessels", [])
        if vessels:
            df_v = pd.DataFrame(vessels)
            fig_map = px.scatter(
                df_v, x="lon", y="lat", size="capacity_mt",
                color="commodity", color_discrete_map=COMMODITY_COLORS,
                hover_name="name", hover_data={"commodity": True, "destination_name": True, "speed_kn": True, "delay_prob": True, "status": True},
                title="Live Vessel Positions — New Mangalore Port Authority (NMPA) Approach & Anchorages",
                labels={"lon": "Longitude (°E)", "lat": "Latitude (°N)"},
                size_max=26,
            )
            # Add NMPA Port Harbor Indicator Marker
            fig_map.add_trace(go.Scatter(
                x=[74.8100], y=[12.9200],
                mode="markers+text",
                marker=dict(size=14, color="#DC2626", symbol="star"),
                name="NMPA Port (Panambur)",
                text=["NMPA Harbor"],
                textposition="top center",
                textfont=dict(size=11, color="#DC2626", family="Arial Black")
            ))
            fig_map.update_layout(**PLOTLY_THEME, height=380, showlegend=True,
                                   legend=dict(orientation="h", y=-0.2, font=dict(size=10)))
            fig_map.update_traces(marker=dict(opacity=0.85, line=dict(width=0.5, color="white")))
            st.plotly_chart(fig_map, **_W_CHART)

        # Revenue & Throughput Trend
        trend = api_get("/executive/revenue-trend") or {"dates": [], "revenue_cr": [], "throughput_mt": []}
        if trend.get("dates"):
            fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
            fig_trend.add_trace(go.Scatter(
                x=trend["dates"], y=trend["revenue_cr"], name="Revenue (₹ Cr)",
                line=dict(color=GOLD, width=2.5), fill="tozeroy",
                fillcolor="rgba(245,158,11,0.08)"
            ), secondary_y=False)
            fig_trend.add_trace(go.Scatter(
                x=trend["dates"], y=trend["throughput_mt"], name="Throughput (MT)",
                line=dict(color="#2563EB", width=2, dash="dot")
            ), secondary_y=True)
            fig_trend.update_layout(**PLOTLY_THEME, height=260, title="30-Day Revenue & Throughput Trend",
                                     legend=dict(orientation="h", y=-0.2))
            fig_trend.update_yaxes(title_text="Revenue (₹ Cr)", secondary_y=False,
                                    gridcolor="#FEF3C7", linecolor="#FDE68A")
            fig_trend.update_yaxes(title_text="Throughput (MT)", secondary_y=True,
                                    gridcolor="rgba(0,0,0,0)", linecolor="#FDE68A")
            st.plotly_chart(fig_trend, **_W_CHART)

    with col_right:
        # Berth Status
        berths_data = api_get("/cargo/berths") or {"berths": []}
        berths = berths_data.get("berths", [])
        if berths:
            df_b = pd.DataFrame(berths)
            occupied_pct = df_b["occupied"].mean() * 100
            fig_berth = go.Figure(go.Bar(
                x=df_b["berth_id"],
                y=df_b["utilization_pct"],
                marker_color=[GOLD if o else "#E5E7EB" for o in df_b["occupied"]],
                text=df_b["commodity"].fillna("Free"),
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_berth.update_layout(**PLOTLY_THEME, height=260,
                                     title=f"Berth Occupancy — {occupied_pct:.0f}% Utilized",
                                     xaxis_title="Berth", yaxis_title="Utilization %")
            fig_berth.update_yaxes(range=[0, 115], gridcolor="#FEF3C7")
            st.plotly_chart(fig_berth, **_W_CHART)

        # Cargo by Commodity Donut
        if vessels:
            comm_counts = df_v["commodity"].value_counts().reset_index()
            comm_counts.columns = ["commodity", "count"]
            fig_donut = px.pie(
                comm_counts, names="commodity", values="count",
                color="commodity", color_discrete_map=COMMODITY_COLORS,
                title="Active Vessels by Commodity", hole=0.55,
            )
            fig_donut.update_layout(**PLOTLY_THEME, height=260,
                                     legend=dict(orientation="h", y=-0.1, font=dict(size=10)))
            fig_donut.update_traces(textposition="inside", textinfo="percent+label",
                                     textfont_size=10)
            st.plotly_chart(fig_donut, **_W_CHART)

        # Port Events
        st.markdown('<div class="panel"><div class="panel-title">Recent Port Events</div>', unsafe_allow_html=True)
        evts = api_get("/executive/events") or {"events": []}
        for e in evts.get("events", [])[:6]:
            dot_class = f"event-dot-{e.get('type', 'system')}"
            st.markdown(f"""
            <div class="event-row">
              <div class="event-time">{e['time']}</div>
              <div class="event-dot {dot_class}"></div>
              <div class="event-msg">{e['message']}</div>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — VESSEL INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Vessel Intelligence — New Mangalore Port</span>
      <span class="sec-tag">Module 1</span>
      <div class="sec-sub">For the berth planner and Traffic Department: who is expected, waiting and alongside; when berths free up;
      where queues will form; and how today compares with NMPA's own monthly performance figures.</div>
    </div>""", unsafe_allow_html=True)

    def vi_get(path, params=None, timeout=45):
        try:
            r = requests.get(f"{API}{path}", params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"API GET Error ({path}): {e}")
            return None

    VI_CLASS_LABELS = {
        "dry_bulk_conventional": "Dry bulk (conv.)", "dry_bulk_mechanical": "Dry bulk (mech.)", "break_bulk": "Break bulk",
        "liquid_bulk": "Liquid bulk", "container": "Container", "cruise": "Cruise", "non_cargo": "Non-cargo", "unknown": "Unknown",
    }
    VI_CLASS_COLORS = {
        "Dry bulk (conv.)": "#78716C", "Dry bulk (mech.)": "#374151", "Break bulk": "#0891B2", "Liquid bulk": "#D97706",
        "Container": "#2563EB", "Cruise": "#7C3AED", "Non-cargo": "#A8A29E", "Unknown": "#D6D3D1",
    }
    ACCOUNT_LABELS = {"port": "Port account", "non_port": "Other than port", "excluded": "Non-cargo", "unknown": "Not stated"}

    def fmt_dt(s):
        if not s:
            return "—"
        try:
            return datetime.fromisoformat(s).strftime("%d %b %H:%M")
        except ValueError:
            return s

    dates_meta = vi_get("/vessels/intel/report-dates") or {"dates": [], "latest": None}
    vi_dates = list(reversed(dates_meta.get("dates", [])))

    if not vi_dates:
        st.error("No Daily Vessel Position reports found. Run `python scripts/update_vessel_intel_data.py` to download and parse them.")
    else:
        top_l, top_r = st.columns([3, 1])
        with top_r:
            vi_as_of = st.selectbox("As of NMPA report", vi_dates, index=0, key="vi_as_of",
                                    help="Replay the tab exactly as it would have looked on an earlier report day.")
        board = vi_get("/vessels/intel/board", {"as_of": vi_as_of}) or {}
        lin = board.get("lineage", {})
        with top_l:
            age = lin.get("data_age_days")
            cov = lin.get("coverage", {})
            st.markdown(
                f'<div style="padding:10px 14px; background:#F0FDF4; border:1px solid #BBF7D0; border-left:4px solid #059669; border-radius:10px; font-size:12.5px;">'
                f'<b style="color:#065F46;">REAL DATA</b> · NMPA Daily Vessel Position report of <b>{vi_as_of}</b> '
                f'(as of ~{lin.get("report_reference_time", "10:00")[:5]} IST) · archive {lin.get("archive", {}).get("first")} → {lin.get("archive", {}).get("last")} '
                f'· {cov.get("published_days", 0)} reports, {cov.get("coverage_excl_sundays_pct", 0)}% of working days'
                + (f' · <span style="color:#B45309;"><b>latest report is {age} days old</b> — run scripts/update_vessel_intel_data.py</span>' if age and age > 2 else "")
                + '</div>', unsafe_allow_html=True)

        sm = board.get("summary", {})
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Alongside (cargo)", sm.get("alongside_cargo", 0), f"{sm.get('berths_occupied_cargo', 0)}/{sm.get('berths_total', 0)} berths", delta_color="off")
        m2.metric("At anchorage", sm.get("waiting_total", 0), f"{sm.get('waiting_port_account', 0)} port a/c", delta_color="off")
        m3.metric("Longest port wait", f"{sm.get('longest_port_account_wait_h', 0):.0f} h")
        m4.metric("Due in 72 h", sm.get("expected_next_72h", 0), f"{sm.get('expected_total', 0)} expected", delta_color="off")
        m5.metric("Programmed berthings", sm.get("programmed_berthings", 0), f"{sm.get('programmed_sailings', 0)} sailings", delta_color="off")
        m6.metric("Alerts", sm.get("alerts", 0))

        for a in board.get("alerts", [])[:6]:
            css = {"high": "alert-high", "medium": "alert-medium", "info": "alert-low"}.get(a["severity"], "alert-medium")
            st.markdown(f'<div class="alert-card {css}" style="padding:10px 14px; margin-bottom:8px;"><div class="alert-desc" style="margin:0; color:#1C1917;">'
                        f'<b>{a["type"].replace("_", " ").title()}</b> — {a["message"]}</div></div>', unsafe_allow_html=True)

        def vi_imo_cell(r):
            """IMO from data/reference/vessel_imo_lookup.csv (name + LOA match)."""
            if r.get("imo"):
                return r["imo"]
            return "check: same name" if r.get("imo_match") in ("ambiguous", "loa_mismatch") else "—"

        vt_board, vt_arr, vt_plan, vt_wait, vt_perf, vt_method = st.tabs([
            "Port Call Board", "Arrivals & ETA", "Berth Plan", "Waiting & Delays", "Performance vs NMPA", "Data & Method",
        ])

        # ── F1 Port Call Board ────────────────────────────────────────────
        with vt_board:
            st.markdown('<div class="panel"><div class="panel-title">Alongside — departure forecast</div>', unsafe_allow_html=True)
            al = board.get("alongside", [])
            if al:
                df_al = pd.DataFrame([{
                    "Berth": a["berth"] or "—", "Vessel": a["vessel"], "IMO": vi_imo_cell(a), "Cargo": a["cargo"] or "—",
                    "Class": VI_CLASS_LABELS.get(a["cargo_class"], a["cargo_class"]),
                    "Hours alongside": a["hours_alongside"], "Handled (t)": a["qty_handled_t"], "Balance (t)": a["qty_balance_t"],
                    "Last 24h (t)": a["qty_day_t"], "NMPA ETD": a["nmpa_etd"] or "—",
                    "NMPA programme sailing": fmt_dt(a.get("programme_sailing")),
                    "Predicted departure": fmt_dt(a["predicted_departure"]), "Forecast basis": a["forecast_method"],
                    "Receiver / shipper": a["receiver"] or "—",
                } for a in al])
                st.dataframe(df_al, **_W_DF, hide_index=True, height=min(420, 40 + 35 * len(df_al)))
                st.caption("Departure forecast = NMPA's own ETD (date) plus a time-of-day offset learned from past sailings; if no ETD is printed, "
                           "remaining balance ÷ handling rate, then the typical stay. Backtest in 'Data & Method'.")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="panel"><div class="panel-title">Waiting at anchorage / scheduled tankers</div>', unsafe_allow_html=True)
            wt = board.get("waiting", [])
            if wt:
                df_wt = pd.DataFrame([{
                    "Vessel": w["vessel"], "IMO": vi_imo_cell(w), "List": w["list"], "Cargo": w["cargo"] or "—",
                    "Class": VI_CLASS_LABELS.get(w["cargo_class"], w["cargo_class"]),
                    "Arrived": fmt_dt(w["arrival"]), "Waiting (h)": w["waiting_h"],
                    "Reason (NMPA)": w["reason_raw"] or "—", "Account": ACCOUNT_LABELS.get(w["account"], w["account"]),
                    "Target berth": w["target_berth"] or "—",
                    "Programmed berthing": (f"{fmt_dt(w['programme_berthing']['at'])} @ B{w['programme_berthing']['berth']}" if w.get("programme_berthing") else "—"),
                    "Likely more wait (h, median / p80)": (f"{w['expected_more_wait_h']:.0f} / {w['expected_more_wait_p80_h']:.0f}"
                                                           if w.get("expected_more_wait_h") is not None else "—"),
                } for w in wt])
                st.dataframe(df_wt, **_W_DF, hide_index=True)
                st.caption("Account follows NMPA's monthly report: 'Port account' = want of berth / tide; 'Other than port' = receiver or shipper "
                           "not ready, laycan, customs, legal holds. 'Likely more wait' = what past vessels that had already waited this long "
                           "for the same kind of reason went on to wait.")
            else:
                st.info("No vessels waiting in this report.")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="panel"><div class="panel-title">Vessels expected</div>', unsafe_allow_html=True)
            ex = board.get("expected", [])
            if ex:
                df_ex = pd.DataFrame([{
                    "Vessel": e["vessel"], "IMO": vi_imo_cell(e), "Cargo": e["cargo"] or "—", "Class": VI_CLASS_LABELS.get(e["cargo_class"], e["cargo_class"]),
                    "Declared ETA": fmt_dt(e["declared_eta"]),
                    "Likely window (p10–p90)": f"{fmt_dt(e['eta_p10'])} – {fmt_dt(e['eta_p90'])}" if e.get("eta_p10") else "—",
                    "Qty (t)": round(e["qty_t"]) if e.get("qty_t") else None, "Draft (m)": e["draft_m"], "LOA (m)": e["loa_m"],
                    "Preferred berths": ", ".join(e["berth_prefs"] or []) or "—",
                    "Berthing fit": e["berthing_fit"].replace("_", " "),
                    "P(wait > 24 h)": e["p_wait_over_threshold"],
                    "Programmed": (f"{fmt_dt(e['programme_berthing']['at'])} @ B{e['programme_berthing']['berth']}" if e.get("programme_berthing") else "—"),
                } for e in ex])
                st.dataframe(df_ex, **_W_DF, hide_index=True,
                             column_config={"P(wait > 24 h)": st.column_config.ProgressColumn("P(wait > 24 h)", min_value=0, max_value=1, format="%.2f")})
            st.markdown('</div>', unsafe_allow_html=True)

            prog = board.get("programme", [])
            if prog:
                with st.expander(f"NMPA berthing programme in this report ({len(prog)} movements)"):
                    st.dataframe(pd.DataFrame([{"Time": fmt_dt(p["at"]), "Event": p["event"].replace("_", " "),
                                                "Vessel": p["vessel"], "Berth": p["berth"] or "—"} for p in prog]),
                                 **_W_DF, hide_index=True)

            with st.expander("Trace a vessel — every source row behind a port call"):
                call_opts = {}
                for row in al + wt:
                    if row.get("call_id"):
                        call_opts[f"{row['vessel']} ({row['call_id']})"] = row["call_id"]
                if call_opts:
                    pick = st.selectbox("Port call", list(call_opts.keys()), key="vi_call_pick")
                    cd = vi_get(f"/vessels/intel/calls/{call_opts[pick]}") or {}
                    if cd:
                        st.json({k: cd[k] for k in ["call_id", "status", "cargo", "cargo_class", "arrival_dt", "arrival_precision",
                                                    "first_berth_dt", "first_berth_basis", "depart_dt", "depart_basis", "berths",
                                                    "wait_h", "wait_port_h", "wait_non_port_h", "wait_main_reason", "at_berth_h",
                                                    "declared_eta", "eta_error_h", "flags"] if k in cd}, expanded=False)
                        st.dataframe(pd.DataFrame(cd.get("observations", [])), **_W_DF, hide_index=True)
                        if cd.get("movements"):
                            st.dataframe(pd.DataFrame(cd["movements"]), **_W_DF, hide_index=True)

        # ── F2 Arrivals & ETA ─────────────────────────────────────────────
        with vt_arr:
            arr = vi_get("/vessels/intel/arrivals", {"as_of": vi_as_of, "days": 7}) or {}
            eta = vi_get("/vessels/intel/eta-accuracy", {"as_of": vi_as_of}) or {}
            if arr.get("days"):
                rows = []
                for d in arr["days"]:
                    for cls, v in d["by_cargo_class"].items():
                        rows.append({"Date": d["date"], "Class": VI_CLASS_LABELS.get(cls, cls), "Expected arrivals": v})
                if rows:
                    fig_arr = px.bar(pd.DataFrame(rows), x="Date", y="Expected arrivals", color="Class", color_discrete_map=VI_CLASS_COLORS,
                                     title="Expected arrivals per day (probability-weighted from declared ETAs)")
                    fig_arr.update_layout(**PLOTLY_THEME, height=320)
                    st.plotly_chart(fig_arr, **_W_CHART)
            de, ce = eta.get("declared_eta", {}), eta.get("bias_corrected_eta", {})
            if de:
                e1, e2, e3, e4 = st.columns(4)
                e1.metric("Arrivals checked", de.get("n"))
                e2.metric("Declared ETA within ±24 h", f"{de.get('within_24h_pct')}%")
                e3.metric("Median ETA error", f"{de.get('median_abs_h')} h")
                e4.metric("Expected lists that arrived", f"{eta.get('expected_lists_matched_to_an_arrival_pct')}%")
                st.info(eta.get("verdict", ""))
                hist = pd.DataFrame(eta.get("error_histogram_days", []))
                if not hist.empty:
                    hist["Arrival vs declared ETA"] = hist["days"].map(lambda d: f"{d:+d} d" if abs(d) < 5 else (">= +5 d" if d > 0 else "<= -5 d"))
                    fig_h = px.bar(hist, x="Arrival vs declared ETA", y="calls", title="How late or early ships arrive vs their declared ETA")
                    fig_h.update_traces(marker_color=GOLD)
                    fig_h.update_layout(**PLOTLY_THEME, height=280)
                    st.plotly_chart(fig_h, **_W_CHART)
                with st.expander("ETA accuracy by agent (internal — commercially sensitive)"):
                    st.dataframe(pd.DataFrame(eta.get("by_agent", [])), **_W_DF, hide_index=True)

        # ── F4 Berth Plan ────────────────────────────────────────────────
        with vt_plan:
            plan = vi_get("/vessels/intel/berth-plan", {"as_of": vi_as_of, "horizon_h": 72}) or {}
            st.caption(plan.get("lineage", {}).get("method", ""))
            gantt = []
            for b in plan.get("berths", []):
                for t in b["timeline"]:
                    if t.get("start") and t.get("end"):
                        gantt.append({"Berth": f"B{b['berth']}" if b["berth"] != "SPM" else "SPM", "Vessel": t["vessel"],
                                      "Start": t["start"], "End": t["end"],
                                      "Kind": "Alongside" if t["kind"] == "alongside" else ("Planned (NMPA programme / queue)")})
            if gantt:
                gdf = pd.DataFrame(gantt)
                order = [f"B{b}" if b != "SPM" else "SPM" for b in [x["berth"] for x in plan["berths"]]]
                fig_g = px.timeline(gdf, x_start="Start", x_end="End", y="Berth", color="Kind", text="Vessel",
                                    color_discrete_map={"Alongside": "#374151", "Planned (NMPA programme / queue)": GOLD},
                                    category_orders={"Berth": order})
                fig_g.add_vline(x=plan.get("report_time"), line_dash="dash", line_color="#DC2626")
                fig_g.update_layout(**PLOTLY_THEME, height=520, title="Berth occupancy — now and next 72 h")
                fig_g.update_xaxes(range=[pd.to_datetime(plan.get("report_time")) - pd.Timedelta(hours=24),
                                          pd.to_datetime(plan.get("report_time")) + pd.Timedelta(hours=96)])
                st.plotly_chart(fig_g, **_W_CHART)
            cf = plan.get("conflicts", [])
            if cf:
                for c in cf:
                    css = "alert-high" if c["severity"] == "high" else "alert-medium"
                    st.markdown(f'<div class="alert-card {css}" style="padding:10px 14px;"><div class="alert-desc" style="margin:0;color:#1C1917;">{c["message"]}</div></div>',
                                unsafe_allow_html=True)
            else:
                st.success("No berth conflicts forecast in the next 72 h.")
            seq = plan.get("sequenced", [])
            if seq:
                st.dataframe(pd.DataFrame([{"Vessel": s["vessel"], "Status": s["kind"], "Berth": s["berth"], "Ready": fmt_dt(s["ready"]),
                                            "Predicted start": fmt_dt(s["start"]), "Predicted wait (h)": s["predicted_wait_h"],
                                            "Service (h)": s["service_h"], "Slot basis": s["slot_basis"], "Note": s.get("note") or ""} for s in seq]),
                             **_W_DF, hide_index=True)
            ns = plan.get("not_sequenced", [])
            if ns:
                st.caption("Not placed: " + "; ".join(f"{n['vessel']} — {n['why']}" for n in ns))

        # ── F9 Waiting & Delays ──────────────────────────────────────────
        with vt_wait:
            wa = vi_get("/vessels/intel/waiting", {"as_of": vi_as_of, "months": 12}) or {}
            mon = pd.DataFrame(wa.get("monthly", []))
            if not mon.empty:
                fig_w = go.Figure()
                fig_w.add_bar(x=mon["month"], y=mon["avg_port_account_days"], name="Port account", marker_color="#DC2626")
                fig_w.add_bar(x=mon["month"], y=mon["avg_other_days"], name="Other than port account", marker_color="#F59E0B")
                fig_w.update_layout(**PLOTLY_THEME, barmode="stack", height=320,
                                    title="Average pre-berthing detention per cargo call (days) — split as in NMPA's monthly report")
                st.plotly_chart(fig_w, **_W_CHART)
            w1, w2 = st.columns(2)
            with w1:
                br = pd.DataFrame(wa.get("by_reason", []))
                if not br.empty:
                    fig_r = px.bar(br.head(8), x="vessel_days", y="reason", orientation="h", title="Vessel-days waited, by stated reason",
                                   labels={"vessel_days": "Vessel-days", "reason": ""})
                    fig_r.update_traces(marker_color=GOLD_DARK)
                    fig_r.update_layout(**PLOTLY_THEME, height=320)
                    fig_r.update_yaxes(autorange="reversed", title="")
                    st.plotly_chart(fig_r, **_W_CHART)
            with w2:
                bb = pd.DataFrame(wa.get("want_of_berth_by_berth", []))
                if not bb.empty:
                    fig_b = px.bar(bb.head(10), x="berth", y="port_account_vessel_days", title="Port-account waiting by berth (vessel-days)",
                                   labels={"berth": "Berth", "port_account_vessel_days": "Vessel-days"})
                    fig_b.update_traces(marker_color="#DC2626")
                    fig_b.update_layout(**PLOTLY_THEME, height=320)
                    fig_b.update_xaxes(type="category")
                    st.plotly_chart(fig_b, **_W_CHART)
            bc = pd.DataFrame(wa.get("by_cargo_class", []))
            if not bc.empty:
                bc["cargo_class"] = bc["cargo_class"].map(lambda c: VI_CLASS_LABELS.get(c, c))
                bc = bc.rename(columns={"cargo_class": "Cargo class", "calls": "Cargo calls", "median_wait_h": "Median wait (h)",
                                        "avg_wait_days": "Average wait (days)", "share_port_account_pct": "Port-account share of waiting (%)"})
                st.dataframe(bc, **_W_DF, hide_index=True)
            with st.expander("Other-than-port waiting by receiver / shipper (internal — commercially sensitive)"):
                st.dataframe(pd.DataFrame(wa.get("non_port_waiting_by_receiver", [])), **_W_DF, hide_index=True)

        # ── F8 Performance vs NMPA ───────────────────────────────────────
        with vt_perf:
            perf = vi_get("/vessels/intel/performance", {"as_of": vi_as_of}) or {}
            st.caption(perf.get("how_to_read", ""))
            for rec in perf.get("reconciliation", [])[-2:]:
                st.markdown(f"**{rec['month']}** — DVP coverage {rec['dvp_coverage_pct']}% of days")
                rdf = pd.DataFrame(rec["rows"])
                rdf["cargo_class"] = rdf["cargo_class"].map(lambda c: VI_CLASS_LABELS.get(c, c.replace("_", " ").title()))
                rdf = rdf.rename(columns={"cargo_class": "Class", "metric": "Metric", "official": "NMPA official",
                                          "dvp_derived": "Rebuilt from daily reports", "difference": "Difference", "verdict": "Verdict"})
                st.dataframe(rdf[["Class", "Metric", "NMPA official", "Rebuilt from daily reports", "Difference", "Verdict"]],
                             **_W_DF, hide_index=True, height=420)
            if not perf.get("reconciliation"):
                st.warning("No official monthly report overlaps the daily archive yet — download NMPA 'Operational Performance' PDFs "
                           "into nmpa_public_data/operational_performance/ (scripts/update_vessel_intel_data.py does this).")
            ds = pd.DataFrame(perf.get("dvp_series", []))
            os_ = pd.DataFrame(perf.get("official_series", []))
            if not ds.empty:
                fig_p = go.Figure()
                fig_p.add_scatter(x=ds["month"], y=ds["pre_berthing_total_days"], name="Rebuilt — total", mode="lines+markers", line=dict(color=GOLD))
                fig_p.add_scatter(x=ds["month"], y=ds["pre_berthing_port_account_days"], name="Rebuilt — port account", mode="lines+markers", line=dict(color="#DC2626"))
                if not os_.empty and "pre_berthing_total_days" in os_:
                    fig_p.add_scatter(x=os_["month"], y=os_["pre_berthing_total_days"], name="NMPA official — total", mode="markers",
                                      marker=dict(size=12, symbol="diamond", color="#1C1917"))
                if not os_.empty and "pre_berthing_port_account_days" in os_:
                    fig_p.add_scatter(x=os_["month"], y=os_["pre_berthing_port_account_days"], name="NMPA official — port account", mode="markers",
                                      marker=dict(size=12, symbol="diamond-open", color="#991B1B"))
                fig_p.update_layout(**PLOTLY_THEME, height=340, title="Average pre-berthing detention (days): rebuilt monthly vs NMPA official")
                st.plotly_chart(fig_p, **_W_CHART)
            files = perf.get("official_files", [])
            st.caption("Official reports loaded: " + (", ".join(f"{f['file']} ({f['status']})" for f in files) or "none"))

        # ── Data & Method ────────────────────────────────────────────────
        with vt_method:
            ov = vi_get("/vessels/intel/overview", {"as_of": vi_as_of}) or {}
            for card in ov.get("model_cards", []):
                st.markdown(f'<div class="rec-card"><div class="rec-action">{card["feature"]} '
                            f'<span class="badge badge-low" style="margin-left:8px;">{card["status"]}</span></div>'
                            f'<div class="rec-rationale"><b>{card["headline"]}</b><br>{card["verdict"]}</div></div>', unsafe_allow_html=True)
            bt = vi_get("/vessels/intel/departure-backtest", {"as_of": vi_as_of}) or {}
            if bt.get("all_points"):
                st.markdown("**Departure forecast backtest** (mean absolute error, hours)")
                st.dataframe(pd.DataFrame([{"Method": bt["methods"][k], "Vessel-days": v["n"], "Mean error (h)": v["mae_h"],
                                            "Within 12 h (%)": v["within_12h_pct"]} for k, v in bt["all_points"].items()]),
                             **_W_DF, hide_index=True)
                st.caption(bt.get("note", ""))
            dq = vi_get("/vessels/intel/data-quality") or {}
            if dq:
                q1, q2, q3, q4 = st.columns(4)
                q1.metric("Reports in archive", dq["archive"]["published_days"])
                q2.metric("Working-day coverage", f"{dq['archive']['coverage_excl_sundays_pct']}%")
                q3.metric("Port calls stitched", dq["port_calls"]["total"])
                q4.metric("Expected lists → arrival", f"{dq['linking']['matched_to_arrival_pct']}%")
                with st.expander("Waiting-reason → account mapping (edit data/reference/vessel_intel_reference.json)"):
                    st.dataframe(pd.DataFrame(dq.get("waiting_reason_mapping", [])), **_W_DF, hide_index=True)
                ic = dq.get("imo_coverage") or {}
                if ic:
                    with st.expander(f"Ship identity — IMO numbers for {ic['share_pct']}% of cargo calls "
                                     f"({ic['distinct_ships_with_imo']} ships; edit {ic['file']})"):
                        st.caption("NMPA's daily reports print ship names only. IMO numbers come from a curated lookup "
                                   "(each checked against public registries and the IMO check digit) and are matched on "
                                   "name + length overall, so two ships with the same name get different IMOs. "
                                   "'needs_review' = same name but the size doesn't match any looked-up ship.")
                        st.json({"by_match": ic["by_match"], "needs_review": ic["needs_review"]})
                        st.dataframe(pd.DataFrame(ic["next_to_look_up"]), **_W_DF, hide_index=True)
                with st.expander("Data-quality flags and gaps"):
                    st.json({"flags": dq["port_calls"]["flags"], "missing_working_days": dq["missing_working_days"],
                             "unclassified_cargo_texts": dq["unclassified_cargo_texts"],
                             "vessel_name_review_queue": dq["vessel_name_review_queue"], "reference_version": dq["reference_version"]})
            st.caption("Update the data: `python scripts/update_vessel_intel_data.py` (downloads new NMPA reports, parses them, "
                       "rebuilds port calls), then POST /vessels/intel/refresh or restart the API.")

    # ── Vessel Call Forecast (real ML, monthly counts — complements the per-call views above) ──
    st.markdown("---")
    st.markdown('<div class="panel"><div class="panel-title">Vessel Call Forecast (ML) — real, backtested</div>', unsafe_allow_html=True)
    st.caption("Not a per-ship ETA — no AIS data exists for that. This predicts how many vessels are expected to call per month for a commodity, from real historical patterns in data/port_cargo_monthly.csv.")

    vc_meta = api_get("/cargo/commodities") or {}
    vc_status = vc_meta.get("commodity_status", {})
    vc_current = sorted(c for c in vc_meta.get("commodities", []) if c != "ALL" and vc_status.get(c, {}).get("is_current", False))
    vc_col1, vc_col2 = st.columns([2, 1])
    with vc_col1:
        vc_commodity = st.selectbox("Commodity", ["ALL"] + vc_current, index=0, key="vessel_forecast_commodity")
    with vc_col2:
        vc_horizon = st.selectbox("Horizon", [3, 6], format_func=lambda x: f"{x} Months", index=0, key="vessel_forecast_horizon")

    vc_data = api_get("/vessels/forecast", {"horizon": vc_horizon, "commodity": vc_commodity, "section": "ALL"}) or {}
    if vc_data and "summary" in vc_data:
        vs = vc_data["summary"]
        acc_reliable = vs.get("accuracy_reliable", True)
        acc_display = "N/A" if vs.get("model_accuracy_pct") is None else f"{vs['model_accuracy_pct']:.1f}%"

        vm1, vm2, vm3, vm4 = st.columns(4)
        vm1.metric("Current Monthly Calls", f"{vs['current_monthly_vessel_calls']:.0f}")
        vm2.metric("Expected Monthly Calls", f"{vs['expected_monthly_vessel_calls']:.0f}")
        vm3.metric("Backtested Accuracy", acc_display, None if acc_reliable else "unvalidated")
        vm4.metric("Avg. Days Between Calls (ML proxy)", f"{vs['expected_days_between_calls']:.1f}d" if vs.get("expected_days_between_calls") else "—",
                   help="Arithmetic proxy = 30 / expected monthly calls. Not a measured gap — see the real measured panel below for that.")

        if not acc_reliable:
            eval_note = vc_data.get("evaluation", {}).get("reliability_note")
            st.warning(f"⚠ {eval_note or 'Accuracy not reliably measurable for this commodity — too little consistent history.'}")

        # ── Real measured spacing, from the Daily Vessel Position archive ──
        # Deliberately kept visually separate from the ML metrics above:
        # different source, different time span, can legitimately disagree.
        rcs = vc_data.get("real_call_spacing", {})
        st.markdown(
            '<div style="margin-top:14px; padding:12px 16px; background:#FFF8ED; '
            'border:1px solid #F0D9AE; border-left:4px solid #D97706; border-radius:10px;">'
            '<div style="font-size:12.5px; font-weight:800; color:#92400E; letter-spacing:0.3px;">'
            'REAL MEASURED — Daily Vessel Position archive (not the ML model above)</div>',
            unsafe_allow_html=True,
        )
        if rcs.get("status") == "measured":
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Avg. Days Between Calls (measured)", f"{rcs['avg_days_between_calls']:.2f}d")
            rc2.metric("Implied Calls / Month (measured)", f"{rcs['implied_calls_per_month']:.1f}")
            rc3.metric("Unique Calls Observed", f"{rcs['unique_call_count']}")
            st.caption(
                f"Berth(s) matched: {rcs['matched_berths']} · "
                f"{rcs['date_range'][0]} to {rcs['date_range'][1]} · {rcs['caveat']}"
            )
        elif rcs.get("status") == "unavailable":
            st.caption(f"Not available for this commodity: {rcs.get('reason', 'no reliable berth match.')}")
        elif rcs.get("status") == "insufficient_data":
            st.caption(f"Only {rcs.get('unique_call_count', 0)} berthing event(s) found for this commodity's berth(s) in the archive — too few to measure spacing.")
        st.markdown("</div>", unsafe_allow_html=True)

        # ── Real measured stay duration — a DIFFERENT source from the
        # spacing box above: spacing measures gaps between calls, this
        # measures how long each call occupied the berth. ──
        rsd = vc_data.get("real_stay_duration", {})
        st.markdown(
            '<div style="margin-top:10px; padding:12px 16px; background:#FFF8ED; '
            'border:1px solid #F0D9AE; border-left:4px solid #D97706; border-radius:10px;">'
            '<div style="font-size:12.5px; font-weight:800; color:#92400E; letter-spacing:0.3px;">'
            'REAL MEASURED — Berth occupancy / stay duration (linked from daily snapshots + movements log)</div>',
            unsafe_allow_html=True,
        )
        if rsd.get("status") == "measured":
            stats = rsd.get("exact_confidence_stats", {})
            conf = rsd.get("confidence_breakdown", {})
            if stats.get("count"):
                rd1, rd2, rd3 = st.columns(3)
                rd1.metric("Median Stay Duration", f"{stats['median_hours']:.1f}h",
                           f"{stats['median_hours'] - 37:+.1f}h vs. NMPA's own 37h standard")
                rd2.metric("Mean Stay Duration", f"{stats['mean_hours']:.1f}h")
                rd3.metric("High-Confidence Calls", f"{stats['count']} of {rsd['total_calls_observed']}")
                st.caption(
                    f"Berth(s) matched: {rsd['matched_berths']} · confidence breakdown: {conf} · {rsd['caveat']}"
                )
            else:
                st.caption(
                    f"{rsd['total_calls_observed']} call(s) found for this commodity's berth(s), but none with "
                    f"both ends pinned to a real timestamp yet (breakdown: {conf})."
                )
        elif rsd.get("status") == "unavailable":
            st.caption(f"Not available for this commodity: {rsd.get('reason', 'no reliable berth match.')}")
        elif rsd.get("status") == "insufficient_data":
            st.caption("No linked stay-duration calls found for this commodity's berth(s) in the archive.")
        st.markdown("</div>", unsafe_allow_html=True)

        series = vc_data.get("forecast_series", [])
        if series:
            fig_vc = go.Figure(go.Bar(
                x=[s["month"] for s in series], y=[s["expected_vessel_calls"] for s in series],
                marker_color=GOLD, text=[f"{s['expected_vessel_calls']:.0f}" for s in series], textposition="outside",
            ))
            fig_vc.update_layout(**PLOTLY_THEME, height=240, title=f"Expected Vessel Calls — {vc_commodity}",
                                  xaxis_title="Month", yaxis_title="Vessel Calls")
            fig_vc.update_xaxes(type="category")
            st.plotly_chart(fig_vc, **_W_CHART)
    elif vc_data and "error" in vc_data:
        st.info(f"📭 {vc_data['error']}")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CARGO FORECASTING
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Cargo Projection & Predictability Command Center</span>
      <span class="sec-tag">Module 2 — Core Focus</span>
      <div class="sec-sub">Data-Grounded ML Forecasting · Dynamic 95% Confidence Intervals · Chronological Backtesting · Forecast Drivers · What-If Simulator</div>
    </div>

    <!-- Clear Cargo-Forecasting Introduction -->
    <div style="background: #FFFDF9; border: 1px solid #F3E8D6; border-left: 5px solid #EAB308; border-radius: 12px; padding: 18px 22px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
      <div style="font-size: 18px; font-weight: 800; color: #1C1917; letter-spacing: -0.3px;">Predictive Cargo Analytics</div>
      <div style="font-size: 13.5px; color: #57534E; margin-top: 6px; line-height: 1.5; font-weight: 500;">
        "Use historical port cargo movements, commodity patterns, vessel activity and operational factors to forecast future cargo volumes and support proactive port planning."
      </div>
    </div>

    <!-- 3 Visual Capability Cards -->
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px;">
      <div style="background: #FFFFFF; border: 1px solid #F3E8D6; border-top: 4px solid #EAB308; border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
        <div style="font-size: 15px; font-weight: 800; color: #1C1917;">Cargo Volume Forecasting</div>
        <div style="font-size: 12.5px; color: #78716C; margin-top: 8px; line-height: 1.5;">
          Predict future cargo throughput using historical cargo records and ML forecasting.
        </div>
      </div>
      <div style="background: #FFFFFF; border: 1px solid #F3E8D6; border-top: 4px solid #D97706; border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
        <div style="font-size: 15px; font-weight: 800; color: #1C1917;">Commodity & Trade Demand</div>
        <div style="font-size: 12.5px; color: #78716C; margin-top: 8px; line-height: 1.5;">
          Identify commodity-level and trade-demand trends to anticipate future cargo movement.
        </div>
      </div>
      <div style="background: #FFFFFF; border: 1px solid #F3E8D6; border-top: 4px solid #DC2626; border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
        <div style="font-size: 15px; font-weight: 800; color: #1C1917;">Cargo Risk & Anomaly Detection</div>
        <div style="font-size: 12.5px; color: #78716C; margin-top: 8px; line-height: 1.5;">
          Detect unusual cargo patterns, sudden volume changes and operational risks.
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Fetch available commodities
    meta = api_get("/cargo/commodities") or {"commodities": ["ALL"], "sections": ["ALL"]}
    commodity_status = meta.get("commodity_status", {})
    all_comms = [c for c in meta.get("commodities", []) if c != "ALL"]
    # Current-data commodities first, then legacy (2021-only) ones — so the
    # default view and top of the list favor commodities with live forecasts.
    current_comms = sorted(c for c in all_comms if commodity_status.get(c, {}).get("is_current", True))
    legacy_comms = sorted(c for c in all_comms if not commodity_status.get(c, {}).get("is_current", True))
    comm_list = ["ALL"] + current_comms + legacy_comms
    sec_list = ["ALL", "LOADED", "UNLOADED"]

    def _comm_label(c):
        if c == "ALL":
            return "ALL (Port-Wide)"
        status = commodity_status.get(c)
        if status and not status["is_current"]:
            return f"{c} — ⚠ discontinued {status['last_record_month']}"
        return c

    # Filter Controls — Commodity Selector Prominent
    col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
    with col_c1:
        selected_comm = st.selectbox("Select Commodity for Cargo Analytics", comm_list, index=0, format_func=_comm_label)
        if legacy_comms:
            st.caption(f"⚠ {len(legacy_comms)} of {len(all_comms)} commodities only have data through 2021 (dataset switched to consolidated categories in 2023) — marked above.")
    with col_c2:
        selected_sec = st.selectbox("Flow Section", sec_list, format_func=lambda x: {"ALL": "ALL (Loaded & Unloaded)", "LOADED": "LOADED (Exports)", "UNLOADED": "UNLOADED (Imports)"}[x], index=0)
    with col_c3:
        horizon_m = st.selectbox("Forecast Horizon", [3, 6, 12], format_func=lambda x: f"{x} Months", index=1)

    # Fetch Forecast Payload
    fc_data = api_get("/cargo/forecast", {"horizon": horizon_m, "commodity": selected_comm, "section": selected_sec}) or {}
    
    if fc_data and "summary" in fc_data:
        summ = fc_data["summary"]
        chart_data = fc_data.get("chart", {})
        predict_lvl = summ.get("predictability_level", "MEDIUM")
        nmpa_fac = fc_data.get("nmpa_facility", {})
        accuracy_reliable = summ.get("accuracy_reliable", True)

        def _pct(val, decimals=1):
            return "N/A" if val is None else f"{val:.{decimals}f}%"

        def _signed_pct(val, decimals=1):
            return "New activity" if val is None else f"{val:+.{decimals}f}%"

        growth_val = summ.get("forecast_change_pct")

        # Predictability color styling
        pred_color = "#059669" if predict_lvl == "HIGH" else ("#D97706" if predict_lvl == "MEDIUM" else "#DC2626")
        pred_bg = "#F0FDF4" if predict_lvl == "HIGH" else ("#FFFBEB" if predict_lvl == "MEDIUM" else "#FEF2F2")

        data_currency = fc_data.get("data_currency") or {}
        if data_currency.get("is_stale"):
            st.warning(f"⚠️ **Stale/discontinued commodity label:** {data_currency.get('note', '')}")

        # Commodity Snapshot & Detailed Metrics
        comm_name = selected_comm if selected_comm != "ALL" else "All Port Commodities"
        st.markdown(f"""
        <div style="background: #FFFFFF; border: 1px solid #F3E8D6; border-left: 5px solid #059669; padding: 14px 20px; border-radius: 10px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
          <div>
            <span style="font-size: 11px; font-weight: 800; color: #059669; letter-spacing: 0.5px; text-transform: uppercase;">SELECTED COMMODITY ANALYTICS</span>
            <div style="font-size: 18px; font-weight: 800; color: #1C1917; margin-top: 2px;">{comm_name}</div>
          </div>
          <div style="display: flex; gap: 20px; font-size: 12.5px; color: #4B5563; flex-wrap: wrap;">
            <div><b>Current Volume:</b> {summ.get('current_monthly_volume_tonnes', 0):,.0f} tonnes</div>
            <div><b>Forecast Average:</b> {summ.get('expected_monthly_avg_tonnes', 0):,.0f} tonnes</div>
            <div><b>Expected Growth:</b> <span style="color: {'#059669' if (growth_val is None or growth_val >= 0) else '#DC2626'}; font-weight: 700;">{_signed_pct(growth_val)}</span></div>
            <div><b>Predictability:</b> <span style="font-weight: 700; color: {pred_color};">{predict_lvl}</span></div>
            <div><b>Forecast Accuracy:</b> <b>{_pct(summ.get('model_accuracy_pct'))}</b>{'' if accuracy_reliable else ' <span style="color:#DC2626;font-size:10px;">(unvalidated)</span>'}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # NMPA Facility Banner
        st.markdown(f"""
        <div style="background: #FFFDF9; border: 1px solid #F3E8D6; border-left: 5px solid #F59E0B; padding: 12px 18px; border-radius: 10px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <span style="font-size: 11px; font-weight: 800; color: #92400E; letter-spacing: 0.5px; text-transform: uppercase;">New Mangalore Port Authority (NMPA) Operational Mapping</span>
            <div style="font-size: 15px; font-weight: 800; color: #1C1917; margin-top: 2px;">{nmpa_fac.get('facility_name', 'General Terminal')} ({nmpa_fac.get('berths', 'All Berths')})</div>
            <div style="font-size: 12px; color: #78716C; margin-top: 2px;"><b>Hinterland Consumer:</b> {nmpa_fac.get('hinterland_consumer', 'Regional Trade')} | <b>Primary Flow:</b> {nmpa_fac.get('primary_flow', 'LOADED/UNLOADED')}</div>
          </div>
          <div style="text-align: right; background: #FEF3C7; padding: 6px 14px; border-radius: 8px; border: 1px solid #FDE68A;">
            <div style="font-size: 10px; font-weight: 700; color: #92400E;">BERTH DRAFT DEPTH</div>
            <div style="font-size: 16px; font-weight: 800; color: #78350F;">{nmpa_fac.get('max_draft_m', 13.5)} Meters</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # KPI Metric Cards
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Current Monthly Volume", f"{summ.get('current_monthly_volume_tonnes', 0):,.0f} Tonnes")
        m2.metric("Expected Monthly Avg", f"{summ.get('expected_monthly_avg_tonnes', 0):,.0f} Tonnes", _signed_pct(growth_val))
        m3.metric("Forecast Trend", summ.get("trend_signal", "Neutral"))
        m4.metric("Predictability Level", predict_lvl, delta=f"WAPE {_pct(summ.get('model_wape_pct'))}", delta_color="normal")
        m5.metric("Model Accuracy (WAPE)", _pct(summ.get('model_accuracy_pct')), "Target 85%+" if accuracy_reliable else "Unvalidated — see warning above")

        st.markdown("<br>", unsafe_allow_html=True)
        col_chart, col_side = st.columns([3, 1])

        with col_chart:
            # Main Forecast Plotly Chart with Dynamic 95% Confidence Band
            fig_fc = go.Figure()
            # Historical Cargo (Tonnes)
            fig_fc.add_trace(go.Scatter(
                x=chart_data.get("history_months", []), y=chart_data.get("history_values", []),
                name="Historical Cargo (Tonnes)", line=dict(color="#4B5563", width=2.5),
                mode="lines+markers", marker=dict(size=4)
            ))
            # 95% Dynamic Prediction Interval
            fore_m = chart_data.get("forecast_months", [])
            low_b = chart_data.get("lower_bounds", [])
            up_b = chart_data.get("upper_bounds", [])
            if fore_m and low_b and up_b:
                fig_fc.add_trace(go.Scatter(
                    x=fore_m + fore_m[::-1],
                    y=up_b + low_b[::-1],
                    fill="toself", fillcolor="rgba(245,158,11,0.12)",
                    line=dict(color="rgba(0,0,0,0)"), name="95% Dynamic Prediction Interval", showlegend=True
                ))
            # Predicted Cargo
            fig_fc.add_trace(go.Scatter(
                x=fore_m, y=chart_data.get("forecast_values", []),
                name="Predicted Cargo", line=dict(color=GOLD, width=3, dash="dash"),
                mode="lines+markers", marker=dict(size=7, color=GOLD)
            ))

            title_str = f"Cargo Volume Forecast — {selected_comm} — {horizon_m} Month Horizon"
            fig_fc.update_layout(**PLOTLY_THEME, height=400, title=title_str,
                                  xaxis_title="Month", yaxis_title="Cargo Volume (Tonnes)",
                                  legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig_fc, **_W_CHART)

        with col_side:
            # Predictability & Stats Panel
            st.markdown(f"""
            <div class="panel" style="background: {pred_bg}; border: 1px solid {pred_color};">
              <div class="panel-title" style="color: {pred_color};">Predictability Score: {predict_lvl}</div>
              <p style="font-size: 13px; color: #4B5563; margin-top: 8px;">
                {summ.get('predictability_desc', '')}
              </p>
              <hr style="margin: 12px 0; border-color: #F3E8D6;">
              <div style="font-size: 12px;">
                <div><b>Total Horizon Cargo:</b> {summ.get('total_expected_horizon_tonnes', 0):,.0f} Tonnes</div>
                <div style="margin-top: 6px;"><b>Model Error (WAPE):</b> {_pct(summ.get('model_wape_pct'), 2)}</div>
                <div style="margin-top: 6px;"><b>Target Metric:</b> Weighted Absolute % Error</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Data Quality Panel
            dq = fc_data.get("data_quality", {})
            st.markdown(f"""
            <div class="panel" style="margin-top: 14px;">
              <div class="panel-title">Data Lineage & Quality</div>
              <div style="font-size: 12px; color: #4B5563; margin-top: 8px;">
                <div><b>Dataset:</b> Actual Port Cargo Records</div>
                <div><b>Completeness:</b> {dq.get('completeness_pct', 98.4)}%</div>
                <div><b>Time Range:</b> {dq.get('historical_span', '2021-01 to 2026-07')}</div>
                <div><b>Records Analyzed:</b> {dq.get('total_records_analyzed', 0)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Forecast Drivers (Explainability) & Operational Recommendations ──
        st.markdown("---")
        col_drv, col_rec = st.columns([1, 1])

        with col_drv:
            st.markdown('<div class="panel"><div class="panel-title">Explainable Forecast Drivers (WHY this prediction?)</div>', unsafe_allow_html=True)
            st.markdown('<div style="font-size: 12px; color: #78716C; margin-bottom: 12px; font-weight: 500;"><b>Cargo Forecast Query:</b> Why is cargo volume expected to change? Key contributing operational & market drivers:</div>', unsafe_allow_html=True)
            drivers = fc_data.get("drivers", [])
            for d in drivers:
                dir_icon = "▲" if d.get("direction") == "UP" else ("▼" if d.get("direction") == "DOWN" else "●")
                dir_color = "#059669" if d.get("direction") == "UP" else ("#DC2626" if d.get("direction") == "DOWN" else "#D97706")
                st.markdown(f"""
                <div style="background: #FAFAF9; padding: 10px 14px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid {dir_color};">
                  <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 700;">
                    <span>{d['factor']}</span>
                    <span style="color: {dir_color};">{dir_icon} {d['impact']}</span>
                  </div>
                  <div style="font-size: 12px; color: #6B7280; margin-top: 4px;">{d['explanation']} (Weight: {d['weight_pct']}%)</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_rec:
            st.markdown('<div class="panel"><div class="panel-title">AI Operational Recommendations</div>', unsafe_allow_html=True)
            recs = fc_data.get("operational_recommendations", [])
            for r in recs:
                prio = r.get("priority", "MEDIUM")
                prio_color = "#DC2626" if prio == "HIGH" else ("#D97706" if prio == "MEDIUM" else "#059669")
                st.markdown(f"""
                <div style="background: #FFFDF9; border: 1px solid #F3E8D6; padding: 12px 14px; border-radius: 8px; margin-bottom: 10px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 12px; font-weight: 800; color: #1C1917;">{r.get('category', 'Operations')}</span>
                    <span style="background: {prio_color}22; color: {prio_color}; font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 12px;">{prio}</span>
                  </div>
                  <div style="font-size: 13px; font-weight: 600; color: #292524; margin-top: 4px;">{r['recommendation']}</div>
                  <div style="font-size: 12px; color: #78716C; margin-top: 4px;"><b>Action:</b> {r['action']}</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Cargo Forecast Model Validation ──
        st.markdown("---")
        st.markdown("**Cargo Forecast Model Validation (Baseline vs Primary ML Model)**")
        eval_data = api_get("/cargo/accuracy", {"commodity": selected_comm, "section": selected_sec}) or {}
        if eval_data.get("models"):
            models_list = eval_data["models"]
            col_b1, col_b2 = st.columns([3, 2])
            with col_b1:
                test_dates = eval_data.get("test_dates", [])
                actual_v = eval_data.get("actual_test_volumes", [])
                bm_v = models_list[0].get("predicted_volumes", [])
                ml_v = models_list[1].get("predicted_volumes", [])
                
                fig_comp = go.Figure()
                fig_comp.add_trace(go.Scatter(x=test_dates, y=actual_v, name="Actual Cargo Test Data", line=dict(color="#1F2937", width=3), mode="lines+markers"))
                fig_comp.add_trace(go.Scatter(x=test_dates, y=bm_v, name="Baseline Model (Seasonal Naive)", line=dict(color="#9CA3AF", width=2, dash="dot"), mode="lines"))
                fig_comp.add_trace(go.Scatter(x=test_dates, y=ml_v, name="Primary ML Cargo Forecast Model", line=dict(color=GOLD, width=2.5, dash="dash"), mode="lines+markers"))
                fig_comp.update_layout(**PLOTLY_THEME, height=320, title="Chronological Backtesting Validation on Historical Cargo Records",
                                       xaxis_title="Test Month", yaxis_title="Cargo Volume (Tonnes)", legend=dict(orientation="h", y=-0.25))
                st.plotly_chart(fig_comp, **_W_CHART)

            with col_b2:
                rows_metrics = []
                for m in models_list:
                    met = m["metrics"]
                    rows_metrics.append({
                        "Model Name": m["model_name"],
                        "Status": m["status"],
                        "WAPE %": f"{met['wape_pct']}%",
                        "MAPE %": f"{met['mape_pct']}%",
                        "MAE": f"{met['mae_tonnes']:,.0f}",
                        "RMSE": f"{met['rmse_tonnes']:,.0f}",
                        "Accuracy": f"{met['accuracy_score_pct']}%",
                    })
                st.dataframe(pd.DataFrame(rows_metrics), **_W_DF, hide_index=True)
                st.info(eval_data.get("recommended_metric_explanation", "WAPE evaluates cargo predictability cleanly without division-by-zero artifacts."))
        else:
            st.info(
                f"No backtest available for **{selected_comm} / {selected_sec}** — "
                f"{eval_data.get('error', 'insufficient historical periods (fewer than 12 months of data)')}. "
                "The forecast above is unvalidated model extrapolation, not a measured-accuracy prediction."
            )

        # ── NMPA Port Cost & Tariff Calculator ──
        # Every number here comes from the NMPA SOR 2026-27, a real past
        # vessel call in NMPA's Daily Vessel Position reports, or the user.
        # Missing inputs (e.g. GRT) are reported as missing, never guessed.
        st.markdown("---")
        st.markdown(
            '<div class="panel"><div class="panel-title">NMPA Port Cost & Tariff Calculator</div>',
            unsafe_allow_html=True
        )
        st.caption(
            "Rates: NMPA Indexed SOR w.e.f. 01-05-2026. Inputs: real vessel calls from NMPA's "
            "Daily Vessel Position reports. Checked against SOR 2022 and NMPA's 2023-24 income (see below)."
        )

        def _cost_post(payload):
            try:
                r = requests.post(f"{API}/cost/calculate", json=payload, timeout=15)
                body = r.json()
                if r.status_code != 200:
                    d = body.get("detail")
                    return None, (d.get("message") or d.get("error")) if isinstance(d, dict) else str(d)
                return body, None
            except Exception as exc:
                return None, str(exc)

        # ---- start from a real past call ----
        pc_q = st.text_input(
            "Find a real past call (vessel, cargo, berth or receiver)",
            key="cost_pc_q", placeholder="e.g. IOF, LPG, KIOCL, SPM",
        )
        pc_list = api_get("/cost/past-calls", {"q": pc_q, "limit": 400}) or {}
        pc_calls = pc_list.get("calls", [])
        pc_labels = {
            c["id"]: (
                f"{c['berthing_date']} · {c['vessel']} · "
                f"{'SPM' if c['berth'] == 'SPM' else 'B' + str(c['berth']) if c['berth'] else '—'} · "
                f"{c['cargo_raw']} · {c['quantity']:,.0f} t"
            )
            for c in pc_calls
        }
        pc_id = st.selectbox(
            "Past call (newest first)", list(pc_labels), format_func=pc_labels.get,
            key="cost_pc_id", index=0 if pc_labels else None,
        )
        pc = api_get(f"/cost/past-calls/{pc_id}") if pc_id else None
        pc_in = (pc or {}).get("calculator_inputs", {})
        if pc:
            c = pc["call"]
            st.caption(
                f"**{c['vessel']}** · berthed {c['berthing_date']} · Berth {c['berth'] or '—'} · run **{c['run_raw'] or '?'}** · "
                f"LOA {c['loa_m'] or '—'} m · {c['receiver_shipper'] or '—'} — quantity **{(c['quantity'] or 0):,.0f}** "
                f"({c['quantity_basis']}); berth hours **{c['berth_hours'] or 0:,.2f}** ({c['berth_hours_confidence']}). "
                "GRT is not in NMPA's daily reports — enter it from the tonnage certificate."
            )
        sfx = f"_{pc_id}" if pc_id else ""

        flows = ["import", "export", "coastal", "transhipment"]
        vtypes = {
            "dry_bulk": "Dry bulk", "liquid": "POL / liquid tanker", "hazardous": "Hazardous cargo / chemicals",
            "container": "Container", "general_cargo": "General cargo / break bulk", "roro": "RoRo / RoPax",
            "other": "Other cargo vessel", "bunkering_at_berth": "Calling only for bunkering at berth",
            "barge_tug_craft": "Barge / tug / small craft", "bunker_barge": "Bunker barge",
            "fishing_service_boat": "Fishing / service boat",
        }
        berths = [""] + [str(i) for i in range(1, 17)] + ["SPM"]
        pc_berth = (pc_in.get("berth") or "").upper()
        pc_berth = pc_berth if pc_berth in berths else "".join(ch for ch in pc_berth.split("(")[0] if ch.isdigit())

        cost_col1, cost_col2, cost_col3 = st.columns(3)
        with cost_col1:
            cost_cargo_type = st.text_input("Commodity (any name, NMPA code or SOR code)",
                                            value=pc_in.get("cargo_type", ""), key="cost_cargo" + sfx)
            cost_quantity = st.number_input("Quantity (MT, or CBM / units where the SOR says so)", min_value=0.0,
                                            value=pc_in.get("cargo_quantity_mt"), step=100.0, key="cost_qty" + sfx)
            cost_flow = st.selectbox("Cargo flow", flows, index=flows.index(pc_in.get("cargo_flow", "import")),
                                     format_func={"import": "Unloaded / Import (foreign cargo)",
                                                  "export": "Loaded / Export (foreign cargo)",
                                                  "coastal": "Coastal cargo", "transhipment": "Transhipment"}.get,
                                     key="cost_flow" + sfx)
            cost_trade = st.selectbox("Cargo trade (transhipment only)", ["foreign", "coastal"], format_func=str.title,
                                      key="cost_trade" + sfx, disabled=cost_flow != "transhipment")
            cost_party = st.text_input("Receiver / shipper", value=pc_in.get("receiver_shipper") or "",
                                       key="cost_party" + sfx, help="Needed for the KIOCL / UPCL rules.")
        with cost_col2:
            cost_vrun = st.selectbox("Vessel status (Customs / DGS)", ["foreign", "coastal"],
                                     index=0 if pc_in.get("vessel_trade_type", "foreign") == "foreign" else 1,
                                     format_func={"foreign": "Foreign-going (US$ rates)", "coastal": "Coastal (₹ rates)"}.get,
                                     key="cost_vrun" + sfx)
            cost_vessel_type = st.selectbox("Vessel type (berth hire class)", list(vtypes),
                                            index=list(vtypes).index(pc_in.get("vessel_type", "dry_bulk")),
                                            format_func=vtypes.get, key="cost_vtype" + sfx)
            cost_grt = st.number_input("Vessel GRT (from tonnage certificate)", min_value=0.0, value=None, step=1.0,
                                       key="cost_grt" + sfx, placeholder="required for vessel charges")
            cost_berth = st.selectbox("Berth", berths, index=berths.index(pc_berth) if pc_berth in berths else 0,
                                      format_func=lambda b: "— not set —" if not b else ("SPM (MRPL)" if b == "SPM" else f"Berth {b}"),
                                      key="cost_berth" + sfx)
            cost_berth_hours = st.number_input("Berth hours (all fast → all lines cast off)", min_value=0.0,
                                               value=pc_in.get("berth_hours"), step=1.0, key="cost_bh" + sfx)
            cost_usd_inr = st.number_input("USD → INR (RBI reference, vessel entry day)", min_value=0.0, value=None,
                                           step=0.01, format="%.4f", key="cost_usd" + sfx,
                                           placeholder="needed for foreign vessels")
        with cost_col3:
            cost_storage_days = st.number_input("Days in transit storage", min_value=0, value=0, step=1, key="cost_sd" + sfx)
            cost_holidays = st.number_input("Customs holidays / non-working days in free period", min_value=0, value=0,
                                            step=1, key="cost_hol" + sfx)
            cost_storage_category = st.selectbox("Storage category", ["bulk", "break_bulk", "salvaged", "not_shipped"],
                                                 format_func={"bulk": "Bulk", "break_bulk": "Break bulk",
                                                              "salvaged": "Salvaged goods (export)",
                                                              "not_shipped": "Export cargo not shipped"}.get,
                                                 key="cost_cat" + sfx)
            cost_anch = st.number_input("Anchorage hours after sailing", min_value=0.0, value=0.0, step=1.0, key="cost_anch" + sfx)
            cost_tug = st.number_input("Tug hours hired on request", min_value=0.0, value=0.0, step=1.0, key="cost_tug" + sfx)
            cost_shifts = st.number_input("Shiftings at vessel's request", min_value=0, value=0, step=1, key="cost_shift" + sfx)
            cost_annual_volume = st.number_input("Annual volume (MT) — cement band only", min_value=0.0, value=None,
                                                 step=10000.0, key="cost_annual" + sfx)

        if cost_cargo_type:
            cost_match = api_get("/cost/match", {"name": cost_cargo_type})
            if cost_match and cost_match.get("code"):
                match_text = f"Matched to **{cost_match['code']}** — {cost_match['item']} ({cost_match['method']})"
                if cost_match.get("needs_review"):
                    st.warning(match_text + " — confirm the SOR line. " + (cost_match.get("ambiguity") or ""))
                else:
                    st.caption(match_text)
            elif cost_match:
                st.warning(cost_match.get("message", "This entry cannot be priced by wharfage."))

        if st.button("Calculate NMPA Port Cost", type="primary", key="calculate_port_cost"):
            trade = "foreign" if cost_flow in ("import", "export") else "coastal" if cost_flow == "coastal" else cost_trade
            cost_result, cost_err = _cost_post({
                "cargo_type": cost_cargo_type,
                "cargo_quantity_mt": cost_quantity or 0,
                "trade_type": trade,
                "vessel_trade_type": cost_vrun,
                "cargo_flow": cost_flow,
                "vessel_type": cost_vessel_type,
                "vessel_grt": cost_grt or None,
                "berth": cost_berth or None,
                "berth_hours": cost_berth_hours or 0,
                "storage_days": cost_storage_days,
                "excluded_days_in_free_period": cost_holidays,
                "cargo_category": cost_storage_category,
                "annual_volume_mt": cost_annual_volume or None,
                "usd_inr_rate": cost_usd_inr or None,
                "receiver_shipper": cost_party or None,
                "anchorage_hours": cost_anch,
                "tug_hire_hours": cost_tug,
                "shifting_count": cost_shifts,
            })

            if cost_err:
                st.error(f"Cost calculation error: {cost_err}")
            elif cost_result:
                breakdown = cost_result.get("breakdown", {})
                vessel_keys = ("port_dues", "pilotage", "berth_hire", "anchorage", "tug_hire", "shifting")
                m1, m2, m3, m4 = st.columns(4)
                wh = breakdown.get("wharfage", {})
                m1.metric("Wharfage", f"₹{wh['amount']:,.2f}" if wh.get("amount") is not None else "—")
                m2.metric("Vessel related", f"₹{sum((breakdown[k].get('amount') or 0) for k in vessel_keys if breakdown.get(k, {}).get('status') == 'calculated'):,.2f}")
                m3.metric("Total known cost", f"₹{cost_result['total_known_cost']:,.2f}",
                          f"bill ₹{cost_result['bill_total_rounded']:,} + GST", delta_color="off")
                m4.metric("Estimate", "Complete" if cost_result["is_complete"] else "Partial")

                for ex in cost_result.get("exceptions", []):
                    (st.warning if ex["scope"] == "note" else st.error)(ex["message"])
                if cost_result.get("missing_grt_components"):
                    st.warning("Not in the total: " + ", ".join(cost_result["missing_grt_components"]) + " — enter the vessel's GRT.")
                if cost_result.get("unconverted_usd_components"):
                    st.warning(f"US$ {cost_result['unconverted_usd_total']:,.2f} of foreign-vessel charges is not in the ₹ "
                               "total. Enter the RBI USD→INR reference rate for the vessel's entry day.")
                for note in cost_result.get("notes", []):
                    st.info(note)

                labels = {"wharfage": "Wharfage", "transit_storage": "Transit storage", "port_dues": "Port dues",
                          "pilotage": "Pilotage", "berth_hire": "Berth hire", "anchorage": "Anchorage",
                          "tug_hire": "Tug hire", "shifting": "Shifting", "bunkering_facility": "Bunkering facility"}
                status_labels = {"calculated": "Calculated", "needs_exchange_rate": "Needs USD→INR rate",
                                 "needs_grt": "Needs GRT", "not_billed_by_nmpa": "Not billed by NMPA",
                                 "not_applicable": "Not applicable", "rate_unavailable": "Rate not published"}
                st.dataframe(pd.DataFrame([
                    {
                        "Component": labels.get(k, k),
                        "SOR Ref": comp.get("sor_reference"),
                        "Status": status_labels.get(comp.get("status"), comp.get("status")),
                        "Currency": comp.get("currency") or comp.get("reference_currency"),
                        "Amount (US$)": comp.get("amount_usd"),
                        "Amount (₹)": comp.get("amount"),
                        "Reference only": comp.get("reference_amount"),
                        "Detail": comp.get("message") or comp.get("note") or "",
                    }
                    for k, comp in breakdown.items()
                ]), **_W_DF, hide_index=True)

                if wh.get("sor_code"):
                    st.caption(f"Wharfage: SOR {wh['sor_code']} — {wh['sor_item']} | {wh['chargeable_units']:,.1f} "
                               f"chargeable {wh['unit']} × ₹{wh['rate_per_mt']:,.2f} ({wh['trade_type']} cargo)")
                storage = breakdown.get("transit_storage", {})
                rule = storage.get("free_days_rule", {})
                if rule.get("status") == "configured":
                    st.caption(f"Storage: free period **{rule['free_storage_days']}"
                               f"{' + ' + str(rule['extended_by_non_working_days']) if rule.get('extended_by_non_working_days') else ''} days** — "
                               f"{rule['basis']} (SOR {rule['sor_reference']}); chargeable days **{storage.get('chargeable_days', 0):g}**.")
                if storage.get("slabs"):
                    st.dataframe(pd.DataFrame(storage["slabs"]), **_W_DF, hide_index=True)
                st.caption(f"Tariff: **{cost_result['tariff']['name']}**, effective {cost_result['tariff']['effective_from']} "
                           f"to {cost_result['tariff']['effective_to']}. Taxes extra (SOR 1.2(v)); bill rounded up to the next rupee (SOR 1.2(ix)).")

        # ── Checked against past data ──
        validation = api_get("/cost/validation")
        if validation:
            vs = validation["summary"]
            with st.expander(
                f"🔎 Checked against past data — rates {vs['sor_items_consistent']}/{vs['sor_items_checked']} consistent "
                f"with SOR 2022 · NMPA income {vs['income_lines_consistent']}/{vs['income_lines_checked']} lines explained · "
                f"past calls cover {vs['calls_tonnage_coverage_pct']}% of reported tonnage"
            ):
                sor_chk = validation["past_tariff"]
                st.markdown("**1 · Every rate vs the SOR general revision of Dec 2022.** NMPA indexes the SOR each "
                            "1 May, so every item must move by the same few factors: "
                            + ", ".join(f"{n} items × {f}" for f, n in sor_chk["factor_counts"].items())
                            + (". No outliers." if not sor_chk["outliers"] else f". **{len(sor_chk['outliers'])} outliers — check.**"))
                st.dataframe(pd.DataFrame(sor_chk["items"]), **_W_DF, hide_index=True, height=240)
                inc = validation["past_revenue"]
                st.markdown("**2 · NMPA's own income (Revised Estimate 2023-24) ÷ tonnage handled vs the SOR band.**")
                st.dataframe(pd.DataFrame([
                    {"Line": c["line"], "Income (₹ Cr)": c["income_rs_crore"], "Tonnage (lakh t)": c["tonnes_lakh"],
                     "Realised ₹/t": c["realised_rs_per_tonne"],
                     "SOR band ₹/t": f"{c['sor_band_rs_per_tonne'][0]} – {c['sor_band_rs_per_tonne'][1]}",
                     "Result": "Inside band" if c["inside_band"] else "Outside band (expected)" if c["result"] == "consistent" else "Outside band",
                     "Why": c.get("explanation") or c["band_basis"]}
                    for c in inc["cargo_lines"]
                ]), **_W_DF, hide_index=True)
                st.dataframe(pd.DataFrame(inc["vessel_ratio_checks"]), **_W_DF, hide_index=True)
                st.caption(inc["caveat"])
                pcal = validation["past_calls"]
                st.markdown(f"**3 · Tonnage of individual past calls vs NMPA's monthly traffic statement** "
                            f"({pcal['months_compared'][0]} → {pcal['months_compared'][-1]}): "
                            f"{pcal['calls_total_tonnes']:,} t vs {pcal['official_total_tonnes']:,} t reported "
                            f"({pcal['coverage_pct']}%). Calls never exceed the official figure.")
                st.dataframe(pd.DataFrame(pcal["by_group"]), **_W_DF, hide_index=True)
                st.caption("Sources: " + " · ".join(
                    f"[{s['title']}]({s['url']})" if s.get("url") else s["title"]
                    for s in {s["title"]: s for s in sor_chk["sources"] + inc["sources"]}.values()))

        # ── Coming soon ──
        coming_soon = (api_get("/cost/coming-soon") or {}).get("components", [])
        if coming_soon:
            with st.expander("🚧 Coming soon — SOR charges without published rates"):
                st.caption("The 2026-27 SOR lists these charges but prints their rates as '*' or refers to "
                           "another tariff. They are never estimated.")
                for item in coming_soon:
                    st.markdown(f"- **{item['label']}** (SOR {item['sor_reference']}) — *Coming soon*. {item['reason']}")

        st.markdown('</div>', unsafe_allow_html=True)

        # ── Interactive What-If Cargo Scenario Simulator ──
        st.markdown("---")
        st.markdown('<div class="panel"><div class="panel-title">Interactive What-If Cargo Scenario Simulator</div>', unsafe_allow_html=True)
        st.markdown("<div style='font-size: 13px; color: #6B7280; margin-bottom: 14px;'><b>Objective:</b> How will changing operational conditions affect future cargo throughput? Simulate vessel arrival shifts, trade demand changes, and weather delays.</div>", unsafe_allow_html=True)

        sc_col1, sc_col2, sc_col3 = st.columns(3)
        with sc_col1:
            vessel_shift = st.slider("Vessel Arrival Change (%)", min_value=-50, max_value=50, value=15, step=5, help="Simulates vessel fleet arrival volume shift impacting cargo")
        with sc_col2:
            demand_shift = st.slider("Trade Demand Shift (%)", min_value=-50, max_value=50, value=10, step=5, help="Simulates macro trade demand changes")
        with sc_col3:
            weather_delay = st.slider("Weather Delay (Days)", min_value=0, max_value=7, value=1, step=1, help="Simulates port operational slowdown from monsoon/weather")

        if st.button("Run Cargo Scenario Simulation", type="primary"):
            sim_res = api_post("/cargo/scenario", {
                "commodity": selected_comm,
                "section": selected_sec,
                "vessel_arrival_change_pct": vessel_shift,
                "trade_demand_change_pct": demand_shift,
                "weather_delay_days": weather_delay,
                "horizon_months": horizon_m
            })
            if sim_res and "simulation_summary" in sim_res:
                ss = sim_res["simulation_summary"]
                r1, r2, r3 = st.columns(3)
                r1.metric("Predicted Cargo Throughput", f"{ss['simulated_total_tonnes']:,.0f} Tonnes", f"{ss['volume_delta_pct']:+.1f}% vs Base")
                r2.metric("Net Volume Delta", f"{ss['volume_delta_tonnes']:+,.0f} Tonnes")
                r3.metric("Capacity Stress Level", ss["capacity_risk_level"])

                # Plotly Chart comparing Baseline vs Simulated Scenario
                sim_series = sim_res.get("series", [])
                if sim_series:
                    months_sim = [s["month"] for s in sim_series]
                    base_sim = [s["baseline_tonnes"] for s in sim_series]
                    scen_sim = [s["simulated_tonnes"] for s in sim_series]

                    fig_sim = go.Figure()
                    fig_sim.add_trace(go.Scatter(x=months_sim, y=base_sim, name="Baseline Forecast", line=dict(color="#6B7280", width=2)))
                    fig_sim.add_trace(go.Scatter(x=months_sim, y=scen_sim, name="Simulated Scenario Forecast", line=dict(color="#EF4444" if ss['volume_delta_pct'] < 0 else GOLD, width=3, dash="dash"), mode="lines+markers"))
                    fig_sim.update_layout(**PLOTLY_THEME, height=300, title="Predicted Cargo Throughput — Baseline vs Simulated Scenario", xaxis_title="Month", yaxis_title="Cargo Volume (Tonnes)")
                    st.plotly_chart(fig_sim, **_W_CHART)

                # Advisories
                for adv in sim_res.get("simulated_operational_advisories", []):
                    st.warning(adv)

    elif fc_data and "error" in fc_data:
        flow_word = {"LOADED": "export", "UNLOADED": "import", "ALL": "loaded or unloaded"}.get(selected_sec, selected_sec.lower())
        other_section = "UNLOADED" if selected_sec == "LOADED" else ("LOADED" if selected_sec == "UNLOADED" else "ALL")
        st.info(
            f"📭 **No data for this combination:** {fc_data['error']}. "
            f"This usually means **{selected_comm}** genuinely has no recorded **{flow_word}** "
            f"activity at NMPA in the dataset — e.g. crude, LPG, fertilizer, cement, and edible "
            f"oil are import-only at this port. Try **{other_section}** or **ALL** instead."
        )
    else:
        st.error("Unable to reach the backend API — check that the FastAPI server is running.")

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TRADE INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    def _tdetail(*a_, **k_):
        """Trade Intelligence detail table: inside a closed drop-down, so each section leads with its chart."""
        with st.expander("See the details"):
            return st.dataframe(*a_, **k_)

    # Trade Intelligence. Every number here comes from NMPA / Ministry data in data/ via the /trade API.
    # Layout rule: each fact is shown in exactly one place. Sources, checks and limits live in "Data and methods".
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <style>
    .ti-head { margin: 4px 0 18px 0; }
    .ti-head h2 { font-size: 26px; font-weight: 750; color: #1C1917; margin: 0; letter-spacing: -0.01em; }
    .ti-head p { font-size: 14px; color: #57534E; margin: 4px 0 0 0; max-width: 760px; }
    .ti-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; margin: 4px 0 22px 0;
               border-top: 2px solid #1C1917; border-bottom: 1px solid #E7E5E4; }
    .ti-kpi { padding: 14px 18px 14px 0; }
    .ti-kpi + .ti-kpi { padding-left: 18px; border-left: 1px solid #E7E5E4; }
    .ti-kpi .l { font-size: 13px; color: #57534E; }
    .ti-kpi .v { font-size: 30px; font-weight: 750; color: #1C1917; line-height: 1.15; margin-top: 4px; font-variant-numeric: tabular-nums; }
    .ti-kpi .c { font-size: 13px; margin-top: 4px; color: #57534E; font-variant-numeric: tabular-nums; }
    @media (max-width: 760px) { .ti-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .ti-up { color: #0F766E !important; } .ti-down { color: #B91C1C !important; }
    .ti-h { font-size: 17px; font-weight: 700; color: #1C1917; margin: 30px 0 6px 0; line-height: 1.3; letter-spacing: -0.005em; }
    .ti-insight { font-size: 14.5px; color: #1C1917; margin: 0 0 4px 0; padding: 6px 0 6px 12px; border-left: 3px solid #1D4E89;
                  background: #F5F3EF; line-height: 1.45; max-width: 980px; }
    .ti-s { font-size: 13px; color: #78716C; margin: 0 0 8px 0; max-width: 820px; }
    .ti-list { margin: 6px 0 4px 0; padding: 0; list-style: none; border-top: 1px solid #E7E5E4; }
    .ti-list li { display: grid; grid-template-columns: 92px 1fr; gap: 12px; padding: 10px 0; border-bottom: 1px solid #E7E5E4;
                  font-size: 14px; color: #1C1917; line-height: 1.45; }
    .ti-tag { font-size: 12px; font-weight: 650; padding-left: 9px; border-left: 3px solid #94A3B8; color: #44403C; align-self: start; }
    .ti-tag.down { border-color: #B91C1C; } .ti-tag.up { border-color: #0F766E; } .ti-tag.wait { border-color: #D97706; }
    .ti-src { font-size: 12px; color: #A8A29E; margin-top: -6px; }
    .ti-item { font-size: 14px; color: #1C1917; line-height: 1.45; }
    .ti-note { font-size: 12.5px; color: #0F766E; margin-top: 2px; }
    </style>""", unsafe_allow_html=True)

    INK, MUTED, GRID = "#1C1917", "#78716C", "#F1EFEC"
    C_IN, C_OUT, C_UP, C_DOWN, C_FLAT, C_PART = "#1D4E89", "#D97706", "#0F766E", "#B91C1C", "#94A3B8", "#D6D3D1"
    STATUS_COL = {"Rising": C_UP, "Falling": C_DOWN, "Steady": C_IN, "Gone quiet": C_DOWN, "New customer": C_UP}
    CHART_CFG = {"displayModeBar": False}
    # Streamlit versions differ: newer ones take width="stretch", older ones use_container_width=True and treat any
    # unknown argument as a deprecated Plotly keyword (the yellow warning). Pick whichever this version supports.
    import inspect as _inspect
    _POP_KW = ({"width": "stretch"} if "width" in _inspect.signature(st.popover).parameters else {"use_container_width": True})
    _PLOT_KW = ({"width": "stretch", "config": CHART_CFG} if "width" in _inspect.signature(st.plotly_chart).parameters
                else {"use_container_width": True, "config": CHART_CFG})
    NICE = {"TOTAL CRUDE": "Crude oil", "TOTAL COAL": "Coal", "IRON ORE": "Iron ore", "TOTAL LPG": "LPG",
            "POL PRODUCTS": "POL products", "CONTAINER (JSW)": "Containers (JSW)", "EDIBLE OIL": "Edible oil",
            "F.R.M. (DRY)": "F.R.M. (dry)", "FERTILIZER": "Fertilizer", "FOOD GRAINS": "Food grains",
            "OTH. LIQ. CARGOES": "Other liquid cargo", "OTHER CARGO": "Other cargo", "PETROCHEMICALS": "Petrochemicals",
            "TOTAL CEMENT": "Cement", "CRUDE - ISPRL": "Crude (ISPRL)"}
    nice = lambda c: NICE.get(c, c.title())

    def _t(v):
        if v is None:
            return "—"
        return f"{v / 1e6:.2f} MMT" if abs(v) >= 1e6 else f"{v:,.0f} t"

    def _mmt(v):
        return "—" if v is None else f"{v / 1e6:.2f} MMT"

    def _chg(v, tail):
        if v is None:
            return f'<div class="c">{tail}</div>'
        cls = "ti-up" if v > 0 else "ti-down" if v < 0 else ""
        num = f"{v:+.1f}%".replace("-", "\u2212")          # typographic minus
        return f'<div class="c"><span class="{cls}">{num}</span> {tail}</div>'

    def _kpis(items):
        st.markdown('<div class="ti-kpis">' + "".join(
            f'<div class="ti-kpi"><div class="l">{lab}</div><div class="v">{val}</div>{sub}</div>' for lab, val, sub in items
        ) + "</div>", unsafe_allow_html=True)

    def _head(title, sub=None, insight=None):
        """Section header used everywhere: a plain title, the finding from the data, then how to read it."""
        st.markdown(f'<div class="ti-h">{title}</div>'
                    + (f'<div class="ti-insight">{insight}</div>' if insight else "")
                    + (f'<div class="ti-s">{sub}</div>' if sub else ""), unsafe_allow_html=True)

    def _src(text):
        st.markdown(f'<div class="ti-src">Source: {text}</div>', unsafe_allow_html=True)

    def _layout(fig, height, xaxis_title=None, yaxis_title=None, **kw):
        base = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=height,
                    font=dict(family="system-ui, sans-serif", color=INK, size=13),
                    margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                    legend=dict(orientation="h", y=1.08, x=0, title_text="", font=dict(size=12)),
                    xaxis=dict(showgrid=False, linecolor="#D6D3D1", tickfont=dict(color=MUTED),
                               title=dict(text=xaxis_title or "", font=dict(size=12, color=MUTED))),
                    yaxis=dict(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED),
                               title=dict(text=yaxis_title or "", font=dict(size=12, color=MUTED))))
        base.update(kw)
        fig.update_layout(**base)
        return fig

    def _month(m):
        return pd.Timestamp(m + "-01").strftime("%b %Y")

    def _ptxt(v, nd=1):
        """A percentage for a table cell; a dash when there is no value (instead of 'None')."""
        return "\u2014" if v is None or pd.isna(v) else f"{v:+.{nd}f}%"

    def _fmt_t(v, signed=False):
        return "\u2014" if v is None else (f"{v:+,}" if signed else f"{v:,}")

    def _m(month):
        """'2026-09' -> 'Sep 2026'."""
        try:
            return pd.Timestamp(str(month) + "-01").strftime("%b %Y")
        except Exception:
            return str(month)

    def _d(day):
        return pd.Timestamp(day).strftime("%d %b %Y").lstrip("0")

    brief = api_get("/trade/brief")
    trade_sum = api_get("/trade/summary")
    trade_flows = api_get("/trade/flows", {"months": 60})
    trade_comm = api_get("/trade/commodities")

    if not (brief and trade_sum and trade_flows and trade_comm):
        st.error("The trade data did not load. Start the backend from the project folder "
                 "(python -m uvicorn backend.app.main:app --port 8000), then refresh this page.")
    else:
        as_of = _month(trade_sum["as_of"])
        st.markdown(f"""<div class="ti-head"><h2>Trade Intelligence</h2>
          <p>Cargo and customers at New Mangalore Port, built only from NMPA and Ministry of Ports reports.
          Latest complete month: {as_of}.</p></div>""", unsafe_allow_html=True)
        fr = (api_get("/trade/freshness") or {}).get("sources", {})
        h1, h2 = st.columns([4, 1])
        if fr:
            h1.markdown(f'<div class="ti-s">Data held: NMPA statements to {_month(fr["nmpa_commodity_statements"])}, Ministry reports to '
                        f'{_month(fr["ministry_major_ports"])}, NMPA daily reports to {_d(fr["nmpa_daily_reports"])}.</div>',
                        unsafe_allow_html=True)
        try:
            _pdf = requests.get(f"{API}/trade/brief.pdf", timeout=30)
            if _pdf.ok:
                h2.download_button("Monthly brief (PDF)", _pdf.content, file_name=f"NMPA_trade_brief_{trade_sum['as_of']}.pdf",
                                   mime="application/pdf", key="ti_brief")
        except requests.RequestException:
            pass

        cargo_alerts = (api_get("/trade/alerts") or {}).get("alerts", [])
        oc = api_get("/trade/overseas-coastal")
        fc = None              # forecasts: Cargo Forecasting module
        cw = api_get("/trade/customers", timeout=30)
        wt = None              # ship waiting and delays: Vessel Intelligence module
        sp = api_get("/trade/cargo-split", timeout=30)
        cw_ok = bool(cw and cw.get("available"))

        t_over, t_cust, t_cargo, t_data = st.tabs(["Overview", "Customers", "Cargo & ports", "Data & checks"])
        t_comp = t_cargo                   # other ports shown below the cargo sections

        # ══ OVERVIEW ═══════════════════════════════════════════════════════════
        with t_over:
            lm, tin, tout, tall = trade_sum["latest_month"], trade_sum["inbound"], trade_sum["outbound"], trade_sum["total"]
            prev_label = (pd.Timestamp(trade_sum["as_of"] + "-01") - pd.DateOffset(years=1)).strftime("%b %Y")
            pct_ = lambda v: "n/a" if v is None else f"{v:+.1f}%".replace("-", "\u2212")
            tg = api_get("/trade/target")
            tg_ok = bool(tg and tg.get("available"))
            kp = [(f"Cargo handled, {as_of}", _mmt(lm["total_tonnes"]),
                   _chg(tall["yoy_pct_latest_month"], f"vs {prev_label}")
                   + f'<div class="c">in {_mmt(lm["inbound_tonnes"])} ({pct_(tin["yoy_pct_latest_month"])}), '
                     f'out {_mmt(lm["outbound_tonnes"])} ({pct_(tout["yoy_pct_latest_month"])})</div>')]
            if tg_ok:
                kp += [(f"{tg['financial_year']} so far", _mmt(tg["done_tonnes"]),
                        f'<div class="c">{tg["done_share_of_target_pct"]:.0f}% of the {tg["target_tonnes"] / 1e6:.0f} MMT target</div>'
                        + _chg(tg["growth_so_far_pct"], "on last year")),
                       ("Needed per month to hit target", _mmt(tg["needed_per_month_tonnes"]),
                        f'<div class="c">same months last year: {_mmt(tg["last_year_same_months_per_month_tonnes"])}</div>'
                        + f'<div class="c">{pct_(tg["growth_needed_on_last_year_pct"])} needed</div>')]
            kp.append(("Last 12 months", _mmt(tall["last_12_months_tonnes"]), _chg(tall["yoy_pct_last_12_months"], "vs the 12 months before")))
            _kpis(kp)
            if tg_ok:
                pa, pb_ = tg["projection_if_same_as_last_year_tonnes"], tg["projection_if_growth_continues_tonnes"]
                st.markdown(f'<div class="ti-s">Year-end outlook: if the remaining months repeat last year, about {_mmt(pa)} '
                            f'({pct_((pa / tg["target_tonnes"] - 1) * 100)} vs target); if this year\'s growth holds, about {_mmt(pb_)} '
                            f'({pct_((pb_ / tg["target_tonnes"] - 1) * 100)}). {_month(tg["latest_month"])} alone: '
                            f'{pct_(tg["latest_month_growth_pct"])} on a year earlier. Target as announced in NMPA\'s Traffic & Performance report.</div>',
                            unsafe_allow_html=True)
                with st.expander("Target: month by month, and which cargos are ahead or behind"):
                    mo = tg["monthly"]
                    xs = [_month(m["month"]) for m in mo]
                    fig = go.Figure()
                    fig.add_bar(x=xs, y=[m["last_year_tonnes"] for m in mo], name="Last year", marker_color=C_PART,
                                hovertemplate="%{x} last year: %{y:,.0f} t<extra></extra>")
                    fig.add_bar(x=xs, y=[m["this_year_tonnes"] for m in mo], name="This year", marker_color=C_IN,
                                hovertemplate="%{x}: %{y:,.0f} t<extra></extra>")
                    left = [_month(m) for m in tg["months_left"]]
                    if left:
                        fig.add_scatter(x=left, y=[tg["needed_per_month_tonnes"]] * len(left), name="Needed per month",
                                        mode="lines+markers", line=dict(color=C_OUT, width=2, dash="dash"), marker=dict(size=5),
                                        hovertemplate="needed: %{y:,.0f} t<extra></extra>")
                    _layout(fig, 260, barmode="group", hovermode="closest", yaxis_title="Tonnes")
                    st.plotly_chart(fig, **_PLOT_KW)
                    est = [m for m, b in tg["basis_by_month"].items() if b != "ministry"]
                    _src("Ministry of Ports monthly totals for New Mangalore; target from NMPA's Traffic & Performance report"
                         + (f". {', '.join(_month(m) for m in est)}: NMPA statement plus average shore handling" if est else ""))
                    gc = api_get("/trade/target-by-cargo")
                    if gc and gc.get("available"):
                        st.markdown(f'<div class="ti-s" style="margin-top:10px"><b>By cargo</b>: {_month(gc["from"])} to {_month(gc["to"])} '
                                    f'against the same months last year ({gc["total_change_tonnes"] / 1e6:+.2f} MMT in total). '
                                    '"Rest of year last year" is what each cargo handled in the remaining months last year.</div>',
                                    unsafe_allow_html=True)
                        st.dataframe(pd.DataFrame([{
                            "Cargo": nice(r["cargo"]), "Direction": r["direction"], "This year (t)": r["this_year_tonnes"],
                            "Same months last year (t)": r["same_months_last_year_tonnes"], "Change (t)": r["change_tonnes"],
                            "Change %": _ptxt(r["change_pct"]), "Rest of year last year (t)": r["rest_of_year_last_year_tonnes"]}
                            for r in gc["cargos"] if r["this_year_tonnes"] or r["same_months_last_year_tonnes"]]),
                            hide_index=True, width="stretch", column_config={
                                **{c_: st.column_config.NumberColumn(format="localized") for c_ in
                                   ("This year (t)", "Same months last year (t)", "Change (t)")},
                                "Rest of year last year (t)": st.column_config.NumberColumn(format="localized",
                                    help="What this cargo handled in the remaining months of the year, last year: its usual contribution from here on")})
                        st.markdown('<div class="ti-s">Sorted with the cargos furthest behind last year first.</div>', unsafe_allow_html=True)

            # ACTION LIST - one list of trade signals. Each item can be answered by the port team (status + note);
            # answered items leave the top of the list and are kept, with the note, under "Handled".
            items = []
            for a in cargo_alerts:
                d = a.get("yoy_pct_last_3_months")
                key = f"cargo|{a['commodity']}|{a['direction']}"
                if d is None:      # irregular cargo: keep NMPA-based message as written
                    items.append({"key": key, "rank": 4, "w": -(a.get("share_of_direction_pct") or 0), "kind": "Cargo",
                                  "tone": "info", "text": a["message"]})
                    continue
                tone = "down" if d < 0 else "up"
                items.append({"key": key, "rank": 0 if tone == "down" else 3, "w": -a["share_of_direction_pct"], "kind": "Cargo",
                              "tone": tone, "text": f"{nice(a['commodity'])} ({a['direction']}): {'down' if d < 0 else 'up'} {abs(d):.0f}% "
                                                    f"on the same 3 months last year. It is {a['share_of_direction_pct']:.1f}% of {a['direction']} cargo."})
            if cw_ok:
                for a in cw["alerts"]:
                    tone = {"waiting": "wait", "rising": "up", "new": "up"}.get(a["type"], "down")
                    items.append({"key": f"customer|{a['customer']}", "w": -(a["share_pct"] or 0),
                                  "rank": {"high": 1, "medium": 2, "info": 4}[a["severity"]] if tone != "up" else 3,
                                  "kind": "Waiting" if a["type"] == "waiting" else "Customer", "tone": tone, "text": a["message"]})
            items.sort(key=lambda x: (x["rank"], x["w"]))
            fb = (api_get("/trade/alert-feedback") or {})
            fb_items, statuses = fb.get("items", {}), fb.get("statuses", ["Open", "Looking into it", "Explained", "Not relevant"])
            done = [i for i in items if fb_items.get(i["key"], {}).get("status") in ("Explained", "Not relevant")]
            open_ = [i for i in items if i not in done]

            def _item_row(it, n):
                f_ = fb_items.get(it["key"], {})
                c1, c2, c3 = st.columns([0.11, 0.74, 0.15], vertical_alignment="center")
                c1.markdown(f'<span class="ti-tag {it["tone"]}">{it["kind"]}</span>', unsafe_allow_html=True)
                note = (f'<div class="ti-note">{html.escape(f_["status"])}: {html.escape(f_.get("note") or "no note")}'
                        f'{" (" + html.escape(f_["by"]) + ")" if f_.get("by") else ""}, {f_.get("at", "")[:10]}</div>') if f_ else ""
                c2.markdown(f'<div class="ti-item">{html.escape(it["text"])}</div>{note}', unsafe_allow_html=True)
                with c3.popover("Respond" if not f_ else "Update", **_POP_KW):
                    stt = st.radio("Status", statuses, index=statuses.index(f_.get("status", "Open")) if f_.get("status") in statuses else 0,
                                   key=f"fb_s_{n}", horizontal=False)
                    nt = st.text_area("Note (what is the reason?)", value=f_.get("note", ""), key=f"fb_n_{n}", height=80,
                                      placeholder="e.g. Plant maintenance until December")
                    who = st.text_input("Your name or team", value=f_.get("by", ""), key=f"fb_b_{n}")
                    if st.button("Save", key=f"fb_go_{n}", type="primary"):
                        try:
                            requests.post(headers=_auth_headers(), url=f"{API}/trade/alert-feedback", json={"key": it["key"], "status": stt, "note": nt, "by": who}, timeout=10)
                        except requests.RequestException:
                            st.error("Could not save. Is the backend running?")
                        st.rerun()

            _head("Action list", sub=f"Cargo: latest 3 months against the same months last year. Customers: "
                                     f"{cw['period']['recent_label'] if cw_ok else 'the latest 3 months'} against the 3 months before. "
                                     "Use Respond to record what is known; explained items move to Handled.")
            if open_:
                for n_, it in enumerate(open_[:5]):
                    _item_row(it, f"o{n_}")
                if len(open_) > 5:
                    with st.expander(f"Show {len(open_) - 5} more"):
                        for n_, it in enumerate(open_[5:]):
                            _item_row(it, f"m{n_}")
            else:
                st.markdown('<div class="ti-s">Nothing open. Every signal has a recorded response.</div>', unsafe_allow_html=True)
            if done:
                with st.expander(f"Handled ({len(done)})"):
                    for n_, it in enumerate(done):
                        _item_row(it, f"d{n_}")

            # Flow history + forecast in one chart.
            df_f = pd.DataFrame(trade_flows["series"])
            df_f["month"] = pd.to_datetime(df_f["month"])
            _head("Monthly cargo", insight=f"Inbound is {tin['signal'].lower()} and outbound is {tout['signal'].lower()} against their 12-month averages.",
                  sub="Monthly tonnes since January 2022. Dotted lines show the smoothed trend; the shaded part is rebuilt from later reports.")
            fig = go.Figure()
            for col, ema, name, colr in (("inbound_tonnes", "inbound_ema3", "Inbound", C_IN), ("outbound_tonnes", "outbound_ema3", "Outbound", C_OUT)):
                fig.add_scatter(x=df_f["month"], y=df_f[col], name=name, mode="lines", line=dict(color=colr, width=2), connectgaps=False,
                                hovertemplate=f"{name}: %{{y:,.0f}} t<extra></extra>")
                fig.add_scatter(x=df_f["month"], y=df_f[ema], name=f"{name} trend", mode="lines", showlegend=False,
                                line=dict(color=colr, width=1.2, dash="dot"), hoverinfo="skip", connectgaps=True)
            if fc:
                for label, colr in (("All inbound cargo", C_IN), ("All outbound cargo", C_OUT)):
                    r = next((q for q in fc["results"] if q["series"] == label and q["forecast"]), None)
                    if r:
                        f_ = r["forecast"]
                        fig.add_scatter(x=[pd.Timestamp(x["month"] + "-01") for x in f_], y=[x["forecast_tonnes"] for x in f_],
                                        name=f"{label.split()[1].title()} forecast ({r['confidence'].lower()} reliability)",
                                        mode="markers", marker=dict(color=colr, size=9, symbol="diamond"),
                                        error_y=dict(type="data", symmetric=False, color=colr, thickness=1.5, width=4,
                                                     array=[x["range_high_tonnes"] - x["forecast_tonnes"] for x in f_],
                                                     arrayminus=[x["forecast_tonnes"] - x["range_low_tonnes"] for x in f_]))
            der = df_f[df_f["status"] == "derived"]
            if len(der):
                for col, colr in (("inbound_tonnes", C_IN), ("outbound_tonnes", C_OUT)):
                    fig.add_scatter(x=der["month"], y=der[col], mode="markers", showlegend=col == "inbound_tonnes",
                                    name="Derived from NMPA year-to-date figures",
                                    marker=dict(symbol="circle-open", size=10, color=colr, line=dict(width=2)))
            rebuilt = df_f[df_f["status"] == "reconstructed"]["month"]
            if len(rebuilt):
                fig.add_vrect(x0=rebuilt.min(), x1=rebuilt.max(), fillcolor="#E7E5E4", opacity=0.35, line_width=0,
                              annotation_text="rebuilt from later reports", annotation_position="top left",
                              annotation_font=dict(size=11, color=MUTED))
            st.plotly_chart(_layout(fig, 380, yaxis_title="Tonnes per month"), **_PLOT_KW)
            _src("NMPA monthly commodity-wise traffic statements")

        # ══ CARGO ══════════════════════════════════════════════════════════════
        with t_cargo:
            df_c = pd.DataFrame(trade_comm["commodities"])
            df_c["Cargo"] = df_c["commodity"].map(nice)
            n_up = int((df_c["signal"] == "Rising").sum())
            n_dn = int((df_c["signal"] == "Falling").sum())
            _head("Cargo momentum", insight=f"{n_up} cargos are rising and {n_dn} are falling against their 12-month average.", sub=
                  "Each bar compares the recent 3-month trend with the 12-month trend. Grey bars are cargos that move "
                  "too rarely to judge. Seasonality is not removed.")
            with st.expander("Chart: each cargo against its 12-month average"):
                cols = st.columns(2)
                for holder, direction in zip(cols, ("inbound", "outbound")):
                    sub = df_c[(df_c["direction"] == direction) & df_c["momentum_pct"].notna()].sort_values("momentum_pct")
                    with holder:
                        st.markdown(f"**{direction.title()}**")
                        if sub.empty:
                            st.caption("Not enough data.")
                            continue
                        colors = [{"Rising": C_UP, "Falling": C_DOWN}.get(s_, C_FLAT if s_ != "Steady" else C_IN) for s_ in sub["signal"]]
                        # Scale the axis to the regular cargos; an irregular cargo's very large swing is drawn to the edge
                        # with its real value in the label, so it does not squash every other bar.
                        regular = sub.loc[sub["signal"] != "Irregular", "momentum_pct"].abs()
                        span = max(regular.max() if len(regular) else 0, 10) * 1.3
                        shown = sub["momentum_pct"].clip(-span, span)
                        fig = go.Figure(go.Bar(x=shown, y=sub["Cargo"], orientation="h", marker_color=colors,
                                               text=[f"{v:+.0f}%" for v in sub["momentum_pct"]],
                                               textposition="outside", cliponaxis=False,
                                               customdata=sub["momentum_pct"], hovertemplate="%{y}: %{customdata:+.1f}%<extra></extra>"))
                        _layout(fig, 34 * len(sub) + 60, showlegend=False, hovermode="closest")
                        fig.update_xaxes(range=[-span * 1.55, span * 1.55], zeroline=True, zerolinecolor="#A8A29E", showgrid=False, showticklabels=False)
                        fig.update_yaxes(showgrid=False)
                        st.plotly_chart(fig, **_PLOT_KW)

            tbl = pd.DataFrame({
                "Cargo": df_c["Cargo"], "Direction": df_c["direction"],
                "Share of direction": df_c["share_of_direction_pct"],
                f"{as_of} (t)": df_c["latest_month_tonnes"],
                f"{as_of} vs a year earlier": [_ptxt(v) for v in df_c["yoy_pct_latest_month"]],
                "Last 12 months vs year before": [_ptxt(v) for v in df_c["yoy_pct_last_12_months"]],
                "Trend": df_c["signal"],
            }).sort_values(["Direction", "Share of direction"], ascending=[True, False])
            _head("Cargo by commodity", sub=f"{as_of}. Inbound cargos first, then outbound, each largest first. "
                                            "Tick a cargo to open its history and seasonal pattern below.")
            def _cargo_label(c_):
                import re as _re
                t_ = _re.sub(r"^TOTAL\s+", "", str(c_).strip(), flags=_re.I)
                acr = {"LPG", "POL", "JSW", "ISPRL", "LNG", "SPM", "UPCL", "MRPL"}
                words = [w if w.strip("()-.").upper() in acr else w.lower() for w in t_.split()]
                words = [w.upper() if w.strip("()-.").upper() in acr else w for w in words]
                out_ = " ".join(words)
                return out_[:1].upper() + out_[1:]
            if {"commodity", "direction", "last_12_months_tonnes"} <= set(df_c.columns):
                _sk = df_c[["commodity", "direction", "last_12_months_tonnes"]].dropna()
                _sk = _sk[~_sk["commodity"].str.upper().isin(["TOTAL", "GRAND TOTAL"])]
                groups_ = []
                _all_t = _sk["last_12_months_tonnes"].sum() / 1e6
                for d_, root_lbl in (("inbound", "Imports (unloaded)"), ("outbound", "Exports (loaded)")):
                    g_ = _sk[_sk["direction"] == d_].sort_values("last_12_months_tonnes", ascending=False)
                    big_ = g_[(g_["last_12_months_tonnes"] / 1e6 >= 0.025 * _all_t) & ~g_["commodity"].str.upper().str.startswith("OTHER")]
                    items_ = [(_cargo_label(r_["commodity"]), r_["last_12_months_tonnes"] / 1e6) for _, r_ in big_.head(7).iterrows()]
                    rest_ = (g_["last_12_months_tonnes"].sum() - big_.head(7)["last_12_months_tonnes"].sum()) / 1e6
                    if rest_ > 0:
                        items_.append(("Other " + ("imports" if d_ == "inbound" else "exports"), rest_))
                    groups_.append((root_lbl, items_))
                # fixed layout: imports on top, exports below, each largest first, so no two flows cross
                total_ = sum(v for _, it in groups_ for _, v in it); gap_ = 0.06; space_ = 1 - gap_ * 2 - 0.01 * sum(len(it) for _, it in groups_)
                nodes_, xs_, ys_, ncol_, src_, tgt_, val_, lcol_ = [], [], [], [], [], [], [], []
                y_ = 0.01
                for gi_, (root_lbl, items_) in enumerate(groups_):
                    rgb_ = "29,78,137" if gi_ == 0 else "217,119,6"
                    gtot_ = sum(v for _, v in items_); gh_ = gtot_ / total_ * space_ + 0.01 * (len(items_) - 1)
                    nodes_.append(f"{root_lbl}: {gtot_:.1f} Mt"); xs_.append(0.001); ys_.append(y_ + gh_ / 2)
                    ncol_.append("#1D4E89" if gi_ == 0 else "#D97706"); root_i = len(nodes_) - 1
                    yy_ = y_
                    for lbl_, v_ in items_:
                        h_ = v_ / total_ * space_
                        nodes_.append(f"{lbl_}  {v_:.1f}"); xs_.append(0.999); ys_.append(yy_ + h_ / 2)
                        ncol_.append(f"rgba({rgb_},0.85)")
                        src_.append(root_i); tgt_.append(len(nodes_) - 1); val_.append(v_); lcol_.append(f"rgba({rgb_},0.28)")
                        yy_ += h_ + 0.01
                    y_ += gh_ + gap_
                _fsk = go.Figure(go.Sankey(arrangement="fixed",
                                           node=dict(label=nodes_, x=xs_, y=ys_, pad=8, thickness=18, color=ncol_, line=dict(color="white", width=0.5),
                                                     hovertemplate="%{label} million t<extra></extra>"),
                                           link=dict(source=src_, target=tgt_, value=val_, color=lcol_,
                                                     hovertemplate="%{target.label} million t<extra></extra>")))
                _fsk.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10), font=dict(size=12.5, color="#1C1917"), paper_bgcolor="white")
                st.markdown("**How cargo flows through New Mangalore** (last 12 months, million tonnes; width = tonnes; "
                            "blue = imports, orange = exports)")
                st.plotly_chart(_fsk, **_W_CHART, config={"displayModeBar": False}, key="ti_chart_sankey")
            ev_g = _tdetail(tbl, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                                key="ti_cargo_table", column_config={
                "Share of direction": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100,
                    help="This cargo's share of all inbound (or all outbound) cargo in the month"),
                f"{as_of} (t)": st.column_config.NumberColumn(format="localized"),
                "Cargo": st.column_config.TextColumn(width="medium"),
                "Trend": st.column_config.TextColumn(help="Recent 3-month trend against the 12-month trend: Rising, Falling or Steady; "
                                                          "Irregular = moves too rarely to judge."),
            })
            _src("NMPA monthly commodity-wise traffic statements")
            g_rows = list(getattr(getattr(ev_g, "selection", None), "rows", []) or [])
            g_open = False
            if g_rows and g_rows[0] < len(tbl):
                chosen_g = df_c.loc[tbl.index[g_rows[0]], "commodity"]
                g_open = True
                if st.session_state.get("ti_cargo_applied") != chosen_g:
                    st.session_state["ti_cargo_applied"] = chosen_g
                    st.session_state["ti_cargo"] = chosen_g
            with st.expander("Cargo detail: history and seasonal pattern", expanded=g_open):
                st.markdown("")
                names = sorted(df_c["commodity"].unique(), key=nice)
                if st.session_state.get("ti_cargo") not in names:
                    st.session_state["ti_cargo"] = "IRON ORE" if "IRON ORE" in names else names[0]
                pick = st.selectbox("Cargo", names,
                                    format_func=nice, key="ti_cargo", label_visibility="collapsed")
                det = api_get("/trade/commodity", {"name": pick, "months": 60})
                if det:
                    df_d = pd.DataFrame(det["series"])
                    df_d["month"] = pd.to_datetime(df_d["month"])
                    fig = go.Figure()
                    for col, name, colr in (("inbound_tonnes", "Inbound", C_IN), ("outbound_tonnes", "Outbound", C_OUT)):
                        if df_d[col].notna().any() and (df_d[col].fillna(0) > 0).any():
                            fig.add_scatter(x=df_d["month"], y=df_d[col], name=name, mode="lines+markers",
                                            line=dict(color=colr, width=2), marker=dict(size=4), connectgaps=False)
                    st.plotly_chart(_layout(fig, 300, yaxis_title="Tonnes per month"), **_PLOT_KW)
                    sz = api_get("/trade/seasonality", {"name": pick})
                    if sz:
                        for direction, x in sz["directions"].items():
                            fys = sorted(x["years"])
                            if len(fys) < 2:
                                continue
                            if x["regular"] and x["busiest_months"]:
                                txt = (f"{direction.title()}: busiest months {', '.join(x['busiest_months'])}; quietest {', '.join(x['quietest_months'])} "
                                       f"(the busiest month runs about {max(x['seasonal_index'])}% of an average month, the quietest about {min(x['seasonal_index'])}%).")
                            else:
                                txt = f"{direction.title()}: no regular seasonal pattern; this cargo moves in irregular lots."
                            st.markdown(f'<div class="ti-s" style="margin-top:8px"><b>Seasonal pattern</b>. {txt} Each line is one financial year, April to March.</div>',
                                        unsafe_allow_html=True)
                            fig = go.Figure()
                            year_cols = ["#B39DDB", "#81B29A", "#E0A458", "#7FA7D1", "#D1495B", "#2A9D8F"]   # older years, distinct
                            for k, fy in enumerate(fys):
                                last_ = fy == fys[-1]
                                colr = "#1C1917" if last_ else year_cols[(len(fys) - 1 - k - 1) % len(year_cols)]
                                fig.add_scatter(x=sz["months"], y=x["years"][fy], name=fy + (" (so far)" if last_ and fy not in x["complete_years"] else ""),
                                                mode="lines+markers", line=dict(color=colr, width=3.2 if last_ else 1.8), marker=dict(size=6 if last_ else 3),
                                                hovertemplate=f"{fy} %{{x}}: %{{y:,.0f}} t<extra></extra>")
                            st.plotly_chart(_layout(fig, 260, yaxis_title="Tonnes", hovermode="closest"), **_PLOT_KW)

            mx = api_get("/trade/cargo-mix")
            if mx and mx.get("cargos"):
                with st.expander("Cargo mix by financial year: how each cargo's share of the port has shifted"):
                    lab = {fy: fy + ("" if mx["months_held"][fy] == 12 else f" ({mx['months_held'][fy]} months)") for fy in mx["financial_years"]}
                    mdf = pd.DataFrame([{"Cargo": nice(r["cargo"]), "Direction": r["direction"],
                                         **{lab[fy]: r["share_pct"][fy] for fy in mx["financial_years"]},
                                         f"Change {mx['compare_from']} to {mx['compare_to']} (points)": r["share_change_points"]}
                                        for r in mx["cargos"]])
                    st.dataframe(mdf, hide_index=True, width="stretch", column_config={
                        **{lab[fy]: st.column_config.NumberColumn(format="%.1f%%") for fy in mx["financial_years"]},
                        f"Change {mx['compare_from']} to {mx['compare_to']} (points)": st.column_config.NumberColumn(format="%+.1f")})
                    st.markdown('<div class="ti-s">Share of all cargo handled (loaded + unloaded) in each financial year, April to March. '
                                'Port totals: ' + ", ".join(f"{fy} {mx['totals_tonnes'][fy] / 1e6:.1f} MMT" for fy in mx["financial_years"])
                                + '.</div>', unsafe_allow_html=True)

            msr = api_get("/trade/market-share")
            if msr and msr.get("available"):
                opp = [o["cargo"] for o in msr["opportunities"]]
                _head("Market share among major ports",
                      insight=(f"New Mangalore handles {msr['nmpa_share_of_all_major_ports_pct']:.1f}% of all major-port cargo "
                               f"({msr['period_label']}). Gaining share: {', '.join(msr['gaining']) or 'none'}. "
                               f"Losing share: {', '.join(msr['losing']) or 'none'}."
                               + (f" Growing at other ports but not here: {', '.join(opp)}." if opp else "")),
                      sub=f"Each cargo: New Mangalore's tonnes against all 12 major ports, {msr['period_label']}, and growth against the same "
                          f"months last year. Gaining or losing share = growing at least {msr['rules']['gap_points']:.0f} points faster or slower "
                          "than the other 11 major ports (New Mangalore is left out of its own benchmark).")
                end_ = msr["period_label"].split(" to ")[1]                  # e.g. "September 2026"
                pl = f"Apr–{msr['previous_period_label'].split(' to ')[1][:3]} {msr['previous_period_label'][-4:]}"
                tl = f"Apr–{end_[:3]} {end_[-4:]}"
                rows_ms = [r for r in msr["cargos"] if r["nmpa_tonnes"] or r["nmpa_prev_tonnes"]] + [{**msr["total"], "status": "Whole port", "note": ""}]
                num = st.column_config.NumberColumn
                # Table 1: the share - what most people need
                share_df = pd.DataFrame([{
                    "Cargo": r["cargo"], "Status": r["status"], f"Share {pl}": r["share_prev_pct"], f"Share {tl}": r["share_pct"],
                    "Change (points)": r["share_change_points"], "Note": r.get("note", "")} for r in rows_ms])
                _tdetail(share_df, hide_index=True, width="stretch", height=38 + 35 * len(share_df), column_config={
                    "Cargo": st.column_config.TextColumn(width="medium"),
                    "Status": st.column_config.TextColumn(help="Gaining share = New Mangalore grew at least 5 points faster than the other 11 major ports; "
                                                              "losing share = at least 5 points slower; otherwise in line."),
                    f"Share {pl}": num(format="%.2f%%", help="New Mangalore tonnes ÷ all major ports tonnes, last year"),
                    f"Share {tl}": num(format="%.2f%%", help="New Mangalore tonnes ÷ all major ports tonnes, this year"),
                    "Change (points)": num(format="%+.2f", help="This year's share minus last year's. 9.00% → 9.40% = +0.40 points. "
                                                                "Positive = New Mangalore grew faster than the other ports."),
                    "Note": st.column_config.TextColumn(width="large")})
                # Table 2: the tonnes behind each share, last year and this year
                with st.expander(f"The tonnes behind each share: {pl} against {tl}"):
                    tdf = pd.DataFrame([{
                        "Cargo": r["cargo"],
                        f"New Mangalore {pl} (t)": r["nmpa_prev_tonnes"], f"New Mangalore {tl} (t)": r["nmpa_tonnes"],
                        "New Mangalore growth": _ptxt(r["nmpa_growth_pct"]),
                        f"All major ports {pl} (t)": r["all_ports_prev_tonnes"], f"All major ports {tl} (t)": r["all_ports_tonnes"],
                        "Other major ports' growth": _ptxt(r.get("other_ports_growth_pct"))} for r in rows_ms])
                    st.dataframe(tdf, hide_index=True, width="stretch", height=38 + 35 * len(tdf), column_config={
                        "Cargo": st.column_config.TextColumn(width="medium"),
                        **{c: num(format="localized") for c in tdf.columns if c.endswith("(t)")},
                        "New Mangalore growth": st.column_config.TextColumn(help="(this year − last year) ÷ last year × 100"),
                        "Other major ports' growth": st.column_config.TextColumn(help="Same calculation for the other 11 major ports "
                                                                                          "(all major ports minus New Mangalore): the fair benchmark")})
                    st.markdown('<div class="ti-s">Growth = (this year − last year) ÷ last year × 100. Share = New Mangalore ÷ all major ports. '
                                'Example, crude oil: (8,868,733 − 7,888,237) ÷ 7,888,237 = +12.4%; share 8,868,733 ÷ 94,320,511 = 9.40%.</div>',
                                unsafe_allow_html=True)
                st.markdown('<div class="ti-s">Sorted by New Mangalore tonnes, largest first; the last row is the whole port. '
                            'Hover over a column title for how it is calculated.</div>', unsafe_allow_html=True)
                if len(msr["monthly_share"]) >= 3:
                    with st.expander("Share by month"):
                        st.markdown('<div class="ti-s">New Mangalore\'s share of each cargo at all 12 major ports, month by month. '
                                    'A break in a line is a month for which the Ministry\'s report does not give that cargo separately; '
                                    'lines are never drawn across a missing month. Single months jump with large shiploads: read the direction '
                                    'over several months.</div>', unsafe_allow_html=True)
                        view_ = st.radio("View", ["Main groups (every month)", "Individual cargos (no figure for March)"],
                                         horizontal=True, key="ms_view", label_visibility="collapsed")
                        if view_.startswith("Main") and msr.get("monthly_share_groups"):
                            msd = pd.DataFrame(msr["monthly_share_groups"])
                            series_ = [c for c in msd.columns if c != "month"]
                        else:
                            msd = pd.DataFrame(msr["monthly_share"])
                            series_ = [r["cargo"] for r in msr["cargos"][:6]]
                            st.markdown(f'<div class="ti-s">{html.escape(msr.get("march_note", ""))} A grey dotted line bridges a month '
                                        'the Ministry did not report separately; it is not a value.</div>', unsafe_allow_html=True)
                        from plotly.subplots import make_subplots
                        msd = msd.assign(month=pd.to_datetime(msd["month"])).sort_values("month")
                        series_ = [g_ for g_ in series_ if g_ in msd.columns and msd[g_].notna().any()]
                        ncol_ = 3 if len(series_) > 4 else 2
                        nrow_ = -(-len(series_) // ncol_)
                        def _last(g_):
                            v_ = msd[["month", g_]].dropna()
                            return (v_["month"].iloc[-1], float(v_[g_].iloc[-1])) if len(v_) else (None, None)
                        titles_ = []
                        for g_ in series_:
                            m_, v_ = _last(g_)
                            nm_ = g_.split(" (")[0] if len(g_) > 30 else g_
                            titles_.append(f"<b>{nm_}</b> \u00b7 {v_:.1f}% in {m_:%b %Y}" if v_ is not None else f"<b>{nm_}</b>")
                        fig = make_subplots(rows=nrow_, cols=ncol_, subplot_titles=titles_, shared_xaxes=True,
                                            vertical_spacing=0.16 if nrow_ > 1 else 0.1, horizontal_spacing=0.07)
                        for k_, g_ in enumerate(series_):
                            r_, c_ = k_ // ncol_ + 1, k_ % ncol_ + 1
                            # dotted bridge across months the Ministry did not report separately (not a value)
                            fig.add_scatter(x=msd["month"], y=msd[g_], mode="lines", connectgaps=True, showlegend=False, hoverinfo="skip",
                                            line=dict(color="#CBD5E1", width=1.5, dash="dot"), row=r_, col=c_)
                            fig.add_scatter(x=msd["month"], y=msd[g_], mode="lines+markers", connectgaps=False, showlegend=False,
                                            line=dict(color="#1D4E89", width=2.2), marker=dict(size=4, color="#1D4E89"),
                                            hovertemplate=f"{g_} %{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>", row=r_, col=c_)
                            avg_ = float(msd[g_].dropna().tail(12).mean())
                            fig.add_hline(y=avg_, line=dict(color="#D97706", width=1, dash="dash"), row=r_, col=c_)
                            m_, v_ = _last(g_)
                            if v_ is not None:
                                fig.add_scatter(x=[m_], y=[v_], mode="markers", showlegend=False, hoverinfo="skip",
                                                marker=dict(size=9, color="#1D4E89", line=dict(color="white", width=2)), row=r_, col=c_)
                        fig.update_layout(height=230 * nrow_ + 40, plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=45, r=15, t=40, b=20),
                                          font=dict(size=11, color="#44403C"))
                        fig.update_annotations(font_size=12.5)
                        fig.update_xaxes(type="date", dtick="M6", tickformat="%b %y", gridcolor="#F1F1F1", showline=True, linecolor="#E7E5E4")
                        fig.update_yaxes(gridcolor="#F1F1F1", ticksuffix="%", rangemode="tozero")
                        st.markdown('<div class="ti-s">Each panel: New Mangalore\'s share of that cargo at all 12 major ports (blue); orange dashes = its '
                                    'average over the last 12 months. Above the dashes = gaining share.</div>', unsafe_allow_html=True)
                        st.plotly_chart(fig, **_PLOT_KW)
                _src(msr["source"])
                pc = api_get("/trade/port-competition")
                if pc and pc.get("available"):
                    with st.expander(f"Which ports gained each cargo, {pc['from']} to {pc['to']} (Ministry annual report)"):
                        grp = st.selectbox("Cargo", list(pc["groups"].keys()), key="pc_group")
                        gd = pc["groups"][grp]
                        nm_ = gd["new_mangalore"]
                        if nm_:
                            st.markdown(
                                f'<div class="ti-insight">{grp}: all major ports changed by {gd["all_ports_change_t"] / 1e6:+.2f} MMT from '
                                f'{pc["from"]} to {pc["to"]}. Largest gains: {", ".join(gd["top_gainers"]) or "none"}. New Mangalore: '
                                f'{nm_["change_t"] / 1e6:+.2f} MMT, share {nm_["share_first_pct"]:.1f}% \u2192 {nm_["share_pct"]:.1f}%, '
                                f'number {gd["new_mangalore_rank"]} of {len(gd["ports"])} ports.</div>', unsafe_allow_html=True)
                        yrs = pc["years"]
                        st.dataframe(pd.DataFrame([{
                            "Port": ("\u25b6 " if r["port"] == "New Mangalore" else "") + r["port"],
                            **{f"{fy} (t)": r[fy] for fy in yrs},
                            f"Change {pc['from']} to {pc['to']} (t)": r["change_t"],
                            f"Share {pc['to']}": r["share_pct"]} for r in gd["ports"]]),
                            hide_index=True, width="stretch", column_config={
                                **{f"{fy} (t)": st.column_config.NumberColumn(format="localized") for fy in yrs},
                                f"Change {pc['from']} to {pc['to']} (t)": st.column_config.NumberColumn(format="localized"),
                                f"Share {pc['to']}": st.column_config.NumberColumn(format="%.1f%%")})
                        st.markdown(f'<div class="ti-s">Sorted by {pc["to"]} tonnes, largest first; \u25b6 marks New Mangalore. '
                                    f'{html.escape(pc["note"])} The annual report groups crude with POL products, and its LPG/LNG '
                                    'figures are on a different basis from the monthly reports, so compare ports within this table '
                                    'rather than with the figures above.</div>', unsafe_allow_html=True)
                        _src(pc["source"])

            if sp and sp.get("available"):
                fam = [f for f in sp["families"] if f["direction_known"] and f["ships"] >= 8]
                fam.sort(key=lambda f: f["ships"])
                most_c = max(fam, key=lambda f: f["coastal_share_by_ships_pct"]) if fam else None
                with st.expander("Foreign or coastal ships, by cargo (estimate from the daily reports)"):
                    _head("Foreign and coastal ships by cargo",
                          "Ship calls in NMPA's daily vessel reports by run (F = foreign, C = coastal). An estimate of the pattern, "
                          "not official tonnes" + (f"; {most_c['cargo'].lower()} is the most coastal ({most_c['coastal_share_by_ships_pct']:.0f}% of calls)." if most_c else "."))
                    lab = [f"{f['cargo']} ({f['direction']})" for f in fam]
                    fig = go.Figure()
                    fig.add_bar(y=lab, x=[f["foreign_ships"] for f in fam], name="Foreign", orientation="h", marker_color=C_IN,
                                customdata=[[f["coastal_share_by_quantity_pct"]] for f in fam],
                                hovertemplate="%{y}: %{x} foreign calls<extra></extra>")
                    fig.add_bar(y=lab, x=[f["coastal_ships"] for f in fam], name="Coastal", orientation="h", marker_color=C_OUT,
                                hovertemplate="%{y}: %{x} coastal calls<extra></extra>")
                    _layout(fig, 30 * len(fam) + 80, barmode="stack", hovermode="closest", xaxis_title="Ship calls")
                    fig.update_yaxes(showgrid=False, automargin=True)
                    st.plotly_chart(fig, **_PLOT_KW)
                    _src(f"NMPA daily vessel positions, {sp['period']['from']} to {sp['period']['to']}")

            ct = api_get("/trade/containers")
            if ct and ct.get("available"):
                imp, exp = ct["import"], ct["export"]
                _head("Container trade by commodity",
                      insight=f"Laden container exports {_ptxt(exp['growth_pct'], 0)} and imports {_ptxt(imp['growth_pct'], 0)}, {ct['ytd_label']}, against the same months last year.",
                      sub=
                      "Biggest changes: "
                      + "; ".join(f"{c['commodity'].lower()} {c['growth_pct']:+.0f}% ({c['change_teu']:+,} TEU)" for c in ct["biggest_changes"]) + ".")
                with st.expander("Containers by commodity: imports and exports (chart)"):
                    cc = st.columns(2)
                    for holder, side, title in ((cc[0], imp, "Imports (unloaded)"), (cc[1], exp, "Exports (loaded)")):
                        top = side["commodities"][:8][::-1]
                        with holder:
                            st.markdown(f"**{title}**: {side['laden_teu_ytd']:,} TEU")
                            fig = go.Figure()
                            fig.add_bar(y=[r["commodity"] for r in top], x=[r["teu_ytd_prev"] for r in top], orientation="h",
                                        name="Last year", marker_color=C_PART, hovertemplate="%{y} last year: %{x:,} TEU<extra></extra>")
                            fig.add_bar(y=[r["commodity"] for r in top], x=[r["teu_ytd"] for r in top], orientation="h",
                                        name="This year", marker_color=C_IN if side is imp else C_OUT,
                                        text=[("" if r["teu_growth_pct"] is None else f"{r['teu_growth_pct']:+.0f}%") for r in top],
                                        textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x:,} TEU<extra></extra>")
                            _layout(fig, 36 * len(top) + 110, barmode="group", hovermode="closest", xaxis_title="TEU",
                                    legend=dict(orientation="h", y=-0.28, x=0, title_text="", font=dict(size=12)))
                            fig.update_yaxes(showgrid=False, automargin=True)
                            fig.update_xaxes(range=[0, max(max(r["teu_ytd"], r["teu_ytd_prev"]) for r in top) * 1.22])
                            st.plotly_chart(fig, **_PLOT_KW)
                with st.expander("Laden containers per month"):
                    mt_ = pd.DataFrame(ct["monthly_laden_teu"])
                    if len(mt_) >= 6:
                        st.markdown('<div class="ti-s">Laden TEU per month, as reported in each month\'s Statement II.</div>', unsafe_allow_html=True)
                        fig = go.Figure()
                        fig.add_scatter(x=[_month(m) for m in mt_["month"]], y=mt_["import_teu"], name="Imports", mode="lines+markers",
                                        line=dict(color=C_IN, width=2), marker=dict(size=4))
                        fig.add_scatter(x=[_month(m) for m in mt_["month"]], y=mt_["export_teu"], name="Exports", mode="lines+markers",
                                        line=dict(color=C_OUT, width=2), marker=dict(size=4))
                        st.plotly_chart(_layout(fig, 240, yaxis_title="Laden TEU"), **_PLOT_KW)
                _src(ct["source"])
                cln = api_get("/trade/container-lines", timeout=30)
                if cln and cln.get("available"):
                    off = cln.get("official_monthly") or []
                    newl = [l["line_or_agent"] for l in cln["lines"] if l["status"] == "New"]
                    gone = [l["line_or_agent"] for l in cln["lines"] if l["status"].startswith("Not seen")]
                    _head("Container lines and agents",
                          insight=(f"{len(cln['lines'])} lines or agents seen calling since September 2025"
                                   + (f"; new: {', '.join(newl)}" if newl else "") + (f"; not seen for 60+ days: {', '.join(gone)}" if gone else "")
                                   + (f". NMPA's official count: {off[-1]['container_vessels']} container ships in {_month(off[-1]['month'])}." if off else ".")),
                          sub="Who calls, from the agent named in NMPA's daily reports. The reports catch about a third of container "
                              "calls, so use this list for which lines call, and NMPA's official count for how many ships.")
                    _tdetail(pd.DataFrame([{
                        "Line or agent": l["line_or_agent"], "Status": l["status"], "Ships seen": l["vessel_count"],
                        "Calls seen": l["calls"], "Boxes seen": l["boxes"], "Coastal": "\u2014" if l["coastal_share_pct"] is None else f"{l['coastal_share_pct']}%",
                        "Last seen": _d(l["last_call"]), "Ships": ", ".join(l["vessels"][:6]) + (" ..." if len(l["vessels"]) > 6 else "")}
                        for l in cln["lines"]]), hide_index=True, width="stretch", column_config={
                            "Status": st.column_config.TextColumn(width="medium"),
                            "Boxes seen": st.column_config.NumberColumn(format="localized"),
                            "Ships": st.column_config.TextColumn(width="large")})
                    st.markdown('<div class="ti-s">Sorted by calls seen, most first.</div>', unsafe_allow_html=True)
                    if off:
                        with st.expander("Container ships calling per month (NMPA official count)"):
                            fig = go.Figure(go.Bar(x=[_month(o["month"]) for o in off], y=[o["container_vessels"] for o in off],
                                                   marker_color=C_IN, text=[o["container_vessels"] for o in off], textposition="outside",
                                                   cliponaxis=False, hovertemplate="%{x}: %{y} container ships<extra></extra>"))
                            st.plotly_chart(_layout(fig, 240, showlegend=False, yaxis_title="Ships"), **_PLOT_KW)
                            _src("NMPA Traffic & Performance reports, container vessels handled")

        # ══ OTHER PORTS ═══════════════════════════════════════════════════════
        with t_comp:
            if oc:
                y = oc["financial_year_to_date"]
                _head("Overseas and coastal cargo",
                      insight=f"Coastal cargo is {y['coastal_share_pct']:.0f}% of the port's cargo, up from {y['coastal_share_prev_year_pct']:.0f}% a year earlier.",
                      sub=
                      f"{_month(y['from'])} to {_month(y['to'])}. Overseas {_t(y['overseas_tonnes'])} ({y['overseas_yoy_pct']:+.1f}%), coastal {_t(y['coastal_tonnes'])} "
                      f"({y['coastal_yoy_pct']:+.1f}%). Whole port only; the source does not split this by cargo.")
                with st.expander("Overseas and coastal tonnes by month"):
                    df_oc = pd.DataFrame(oc["series"])
                    fig = go.Figure()
                    fig.add_bar(x=[_month(m) for m in df_oc["month"]], y=df_oc["overseas_tonnes"], name="Overseas", marker_color=C_IN)
                    fig.add_bar(x=[_month(m) for m in df_oc["month"]], y=df_oc["coastal_tonnes"], name="Coastal", marker_color=C_OUT)
                    st.plotly_chart(_layout(fig, 280, barmode="stack", yaxis_title="Tonnes"), **_PLOT_KW)
                _src("Ministry of Ports, Shipping and Waterways, Cargo handled at Major Ports (advance estimates)")

            bm = api_get("/trade/benchmark")
            if bm and bm.get("available"):
                ports = sorted(bm["ports"], key=lambda x: x["ytd_growth_pct"])
                h = bm["home"]
                rank_word = {1: "1st", 2: "2nd", 3: "3rd"}.get(h["rank_by_growth"], f"{h['rank_by_growth']}th")
                _head("Major-port comparison",
                      insight=f"New Mangalore grew {_ptxt(h['ytd_growth_pct'])}, {rank_word} of 12 major ports for growth; all major ports grew {_ptxt(bm['all_ports_ytd_growth_pct'])}.",
                      sub=
                      f"{bm['period_label']} against a year earlier. All major ports {_ptxt(bm['all_ports_ytd_growth_pct'])}; "
                      f"New Mangalore is {h['rank_by_tonnes']}th of 12 by tonnes. Overseas cargo {_ptxt(h['overseas_growth_pct'])} "
                      f"({'steepest fall of the 12' if h['rank_overseas_growth'] == 12 else 'rank ' + str(h['rank_overseas_growth']) + ' of 12'}), "
                      f"coastal {_ptxt(h['coastal_growth_pct'])} "
                      f"({'fastest of the 12' if h['rank_coastal_growth'] == 1 else 'rank ' + str(h['rank_coastal_growth']) + ' of 12'}).")
                _ll = {"Deendayal": (23.03, 70.22), "Mumbai": (18.94, 72.70), "JNPA": (18.95, 73.15), "Mormugao": (15.41, 73.80),
                       "New Mangalore": (12.92, 74.81), "Cochin": (9.96, 76.27), "V.O.C.": (8.76, 78.20), "Chennai": (13.10, 80.40),
                       "Kamarajar": (13.40, 80.20), "Visakhapatnam": (17.69, 83.29), "Paradip": (20.26, 86.67), "SMP Kolkata": (22.55, 88.32)}
                _mp = [x for x in bm["ports"] if x["port"] in _ll]
                if _mp:
                    _gmax = max(abs(float(x["ytd_growth_pct"])) for x in _mp) or 1
                    _fmap = go.Figure(go.Scattergeo(
                        lat=[_ll[x["port"]][0] for x in _mp], lon=[_ll[x["port"]][1] for x in _mp],
                        text=[f'{x["port"]}<br>{x["ytd_tonnes"] / 1e6:.1f} MMT, {float(x["ytd_growth_pct"]):+.1f}%' for x in _mp],
                        hoverinfo="text", mode="markers+text",
                        textposition=[{"Mumbai": "middle left", "JNPA": "bottom right", "Chennai": "bottom right", "Kamarajar": "top right"}
                                      .get(x["port"], "middle right") for x in _mp],
                        textfont=dict(size=[13 if x["is_home"] else 10 for x in _mp], color=["#1C1917" if x["is_home"] else "#57534E" for x in _mp]),
                        marker=dict(size=[max(9, (x["ytd_tonnes"] / 1e6) ** 0.5 * 4.2) for x in _mp], color=[float(x["ytd_growth_pct"]) for x in _mp],
                                    colorscale=[[0, "#B91C1C"], [0.5, "#F5F5F4"], [1, "#0F766E"]], cmin=-_gmax, cmax=_gmax,
                                    line=dict(color=["#1C1917" if x["is_home"] else "white" for x in _mp], width=[3 if x["is_home"] else 1 for x in _mp]),
                                    colorbar=dict(title="Growth %", thickness=12, len=0.6))))
                    _fmap.update_geos(scope="asia", lataxis_range=[6, 26], lonaxis_range=[66, 95], showcountries=True, countrycolor="#D6D3D1",
                                      showland=True, landcolor="#FAFAF9", showocean=True, oceancolor="#EEF4FA", showcoastlines=True, coastlinecolor="#A8A29E")
                    _fmap.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="white")
                    st.markdown(f"**The 12 major ports, {bm['period_label']}** (bubble = cargo this year; colour = growth on a year earlier; "
                                "New Mangalore outlined)")
                    st.plotly_chart(_fmap, **_W_CHART, config={"displayModeBar": False, "topojsonURL": "/app/static/topojson/"},
                                    key="ti_chart_port_map")
                lo = min(x["ytd_growth_pct"] for x in ports); hi = max(x["ytd_growth_pct"] for x in ports)
                pad = (hi - min(lo, 0)) * 0.012
                fig = go.Figure(go.Bar(
                    x=[x["ytd_growth_pct"] for x in ports], y=[x["port"] for x in ports], orientation="h",
                    marker_color=[C_IN if x["is_home"] else C_PART for x in ports], hoverinfo="skip"))
                fig.add_scatter(   # labels drawn as text beside each bar: always horizontal, never inside or on top
                    x=[x["ytd_growth_pct"] + pad if x["ytd_growth_pct"] >= 0 else x["ytd_growth_pct"] - pad for x in ports],
                    y=[x["port"] for x in ports], mode="text",
                    text=[f"{_ptxt(x['ytd_growth_pct'])}  ({x['ytd_tonnes'] / 1e6:.1f} MMT)" for x in ports],
                    textposition=["middle right" if x["ytd_growth_pct"] >= 0 else "middle left" for x in ports],
                    textfont=dict(size=12, color=INK), hoverinfo="skip", cliponaxis=False)
                _layout(fig, 34 * len(ports) + 40, showlegend=False, hovermode=False)
                fig.update_xaxes(range=[min(lo, 0) - (hi - min(lo, 0)) * 0.42, hi * 1.5], zeroline=True, zerolinecolor="#A8A29E", showticklabels=False)
                fig.update_yaxes(showgrid=False, automargin=True)
                fig.add_vline(x=bm["all_ports_ytd_growth_pct"], line_dash="dot", line_color="#C8C2BC", layer="below",
                              annotation_text=f"all major ports {bm['all_ports_ytd_growth_pct']:+.1f}%",
                              annotation_font=dict(size=11, color=MUTED), annotation_position="bottom right")
                st.plotly_chart(fig, **_PLOT_KW)
                _src("Ministry of Ports, Shipping and Waterways, Cargo handled at Major Ports, Table-1 (advance estimates)")
                trd = (bm.get("trend") or {}).get("months") or []
                g_ = [r for r in trd if r["growth_pct"] is not None]
                if len(g_) >= 6:
                    below = sum(1 for r in g_[-6:] if r["growth_pct"] < r["all_ports_growth_pct"])
                    with st.expander("Month by month against all major ports"):
                        _head("Monthly growth against all major ports", insight=f"New Mangalore grew slower than the major-port average in {below} of the last 6 months.", sub=
                              "Growth on the same month a year earlier, New Mangalore against all 12 major ports. The label is "
                              "New Mangalore's rank for growth that month (1 = fastest of 12).")
                        fig = go.Figure()
                        xs = [_month(r["month"]) for r in g_]
                        fig.add_bar(x=xs, y=[r["growth_pct"] for r in g_], name="New Mangalore", marker_color=C_IN,
                                    text=[f"#{r['rank_by_growth']}" for r in g_], textposition="outside", cliponaxis=False,
                                    hovertemplate="%{x}: %{y:+.1f}%<extra></extra>")
                        fig.add_scatter(x=xs, y=[r["all_ports_growth_pct"] for r in g_], name="All major ports", mode="lines+markers",
                                        line=dict(color=C_OUT, width=2), marker=dict(size=5), hovertemplate="%{x}: %{y:+.1f}%<extra></extra>")
                        _layout(fig, 280, hovermode="closest", yaxis_title="% on a year earlier")
                        fig.update_yaxes(zeroline=True, zerolinecolor="#A8A29E")
                        st.plotly_chart(fig, **_PLOT_KW)
                    shares = [r["share_of_major_ports_pct"] for r in trd]
                    st.markdown(f'<div class="ti-s">Share of all major-port cargo: {min(shares):.1f}% to {max(shares):.1f}% a month since '
                                f'{_month(trd[0]["month"])}; rank by tonnes {trd[-1]["rank_by_tonnes"]} of 12 in {_month(trd[-1]["month"])}.</div>',
                                unsafe_allow_html=True)
                rg = bm.get("regional")
                if rg:
                    near = ", ".join(f"{r['state_board'].split(' (')[0]} {r['ytd_tonnes'] / 1e3:,.0f} thousand t" for r in rg["neighbours"])
                    st.markdown(f'<div class="ti-s">Nearby non-major ports are not a volume competitor yet: in {rg["period"].replace(" Apr-", ", April to ")} '
                                f'the state-run ports of {near} handled {rg["neighbours_total_tonnes"] / 1e6:.2f} MMT together, against '
                                + (f'{rg["home_same_period_tonnes"] / 1e6:.1f} MMT at New Mangalore over the same months.</div>'
                                   if rg.get("home_same_period_tonnes") else 'far more at New Mangalore.</div>'),
                                unsafe_allow_html=True)
                _src("Ministry monthly reports for major and non-major ports (data/major_ports_monthly.csv, data/non_major_ports_2026-07.csv)")

        # ══ CUSTOMERS ══════════════════════════════════════════════════════════
        with t_cust:
            if not cw_ok:
                st.error("Customer data did not load. Restart the backend from the project folder, then refresh this page.")
            else:
                per, conc, rows = cw["period"], cw["concentration"], cw["customers"]
                _kpis([
                    ("Named customers", f"{cw['totals']['customers']}", f'<div class="c">{cw["totals"]["calls"]:,} ship calls since {_month(per["from"])}</div>'),
                    (f"Largest: {conc['top3'][0]}", f"{conc['top1_pct']:.0f}%", '<div class="c">of traced cargo tonnes</div>'),
                    ("Top 3 customers", f"{conc['top3_pct']:.0f}%", f'<div class="c">{", ".join(conc["top3"])}</div>'),
                    ("Customers making 80%", f"{conc['customers_for_80pct']}", '<div class="c">of traced cargo tonnes</div>'),
                ])

                dsx_c = (api_get("/trade/data-status") or {}).get("daily_reports")
                if dsx_c:
                    st.markdown(f'<div class="ti-s">Built from {dsx_c["total"]} NMPA daily reports: the original PDF is held for '
                                f'{dsx_c["total"] - dsx_c["not_checked"]} days; for {dsx_c["not_checked"]} days the original has not been '
                                'obtained, so those records are not checked (see Data &amp; checks). Names NMPA has not confirmed '
                                '(e.g. ADANI, MCF) are shown as written, not merged.</div>', unsafe_allow_html=True)
                cnotes = api_get("/trade/customer-notes") or {"customers": {}, "follow_ups_due": []}
                if cnotes["follow_ups_due"]:
                    st.markdown('<div class="ti-insight">Follow-ups due: ' + "; ".join(
                        f"{html.escape(f['customer'])} ({_d(f['follow_up'])}{', ' + html.escape(f['owner']) if f['owner'] else ''})"
                        for f in cnotes["follow_ups_due"]) + "</div>", unsafe_allow_html=True)
                top = [r for r in rows if r["trend_basis"] == "tonnes"][:12]
                with st.expander("Chart: largest customers, recent 3 months against the 3 before"):
                    _head("Largest customers", insight=f"{conc['top3'][0]} brings {conc['top1_pct']:.0f}% of traced cargo; the top 3 bring {conc['top3_pct']:.0f}%.", sub=
                          f"Tonnes in {per['recent_label']} (coloured: green rising, red falling, blue steady) against "
                          f"{per['previous_label']} (grey). Complete months only.")
                    fig = go.Figure()
                    fig.add_bar(y=[r["customer"] for r in top], x=[r["previous_tonnes"] for r in top], orientation="h",
                                name=per["previous_label"], marker_color=C_PART, hovertemplate="%{y}: %{x:,.0f} t<extra></extra>")
                    fig.add_bar(y=[r["customer"] for r in top], x=[r["recent_tonnes"] for r in top], orientation="h",
                                name=per["recent_label"], marker_color=[STATUS_COL.get(r["status"], C_IN) for r in top],
                                hovertemplate="%{y}: %{x:,.0f} t<extra></extra>")
                    _layout(fig, 34 * len(top) + 80, barmode="group", hovermode="closest", xaxis_title="Tonnes")
                    fig.update_xaxes(type="linear", showgrid=True, gridcolor=GRID)
                    fig.update_yaxes(autorange="reversed", showgrid=False, automargin=True)
                    st.plotly_chart(fig, **_PLOT_KW)

                _head("Customer list", sub="Tick a customer to open their details below. Search or use the status buttons to narrow the list; "
                                          "click a column title to sort. Hover over a column title to see what it means.")
                f1, f2 = st.columns([2, 3])
                q = f1.text_input("Find a customer", placeholder="Type a name, e.g. KIOCL", key="ti_q", label_visibility="collapsed")
                status_pick = f2.segmented_control("Status", ["All", "Falling", "Gone quiet", "Rising", "New customer"],
                                                   default="All", key="ti_status", label_visibility="collapsed")
                df_cw = pd.DataFrame([{
                    "Customer": r["customer"], "Main cargo": r["main_cargo"], "Status": r["status"],
                    "Share": r["share_of_traced_tonnes_pct"], "Tonnes": r["tonnes"],
                    "Change (3 months)": _ptxt(r["change_pct"], 0), "Calls": r["calls"],
                    "Days since last ship": r["days_since_last_call"],
                    "Waiting, customer not ready (ship-days)": r["not_ready_ship_days"],
                    "Data note": ", ".join(x for x in (["joint entry"] if r["joint_entry"] else []) + (["agent name?"] if r["agent_name_warning"] else []))
                } for r in rows])
                for c_ in ("Share", "Tonnes", "Calls", "Days since last ship", "Waiting, customer not ready (ship-days)"):
                    df_cw[c_] = pd.to_numeric(df_cw[c_], errors="coerce").fillna(0)
                view = df_cw
                if q:
                    view = view[view["Customer"].str.contains(q.strip(), case=False, regex=False)]
                if status_pick and status_pick != "All":
                    view = view[view["Status"] == status_pick]
                ev_c = st.dataframe(view.rename(columns={"Change (3 months)": "Change", "Days since last ship": "Days since ship",
                                                  "Waiting, customer not ready (ship-days)": "Waiting: customer not ready (ship-days)"}),
                             hide_index=True, width="stretch", height=420, on_select="rerun", selection_mode="single-row",
                             key="ti_cust_table", column_config={
                    "Customer": st.column_config.TextColumn(width="medium"),
                    "Main cargo": st.column_config.TextColumn(width="medium"),
                    "Share": st.column_config.ProgressColumn("Share", format="%.1f%%", min_value=0, max_value=max(1.0, df_cw["Share"].max() or 1)),
                    "Tonnes": st.column_config.NumberColumn(format="localized"),
                    "Change": st.column_config.TextColumn(help=f"Tonnes in {per['recent_label']} against {per['previous_label']}"),
                    "Waiting: customer not ready (ship-days)": st.column_config.NumberColumn(
                        help="Days this customer's ships waited at anchor because the receiver, shipper or cargo was not ready, "
                             "as written by port staff in NMPA's daily reports. 1 ship-day = 1 ship waiting 1 day."),
                    "Status": st.column_config.TextColumn(help=f"Tonnes in {per['recent_label']} against {per['previous_label']}: "
                        "Rising / Falling = up or down 30% or more, or at least 5% when that is 100,000 t or more (large customers). "
                        "Steady = in between. Too few ships to judge = under 4 ship calls in "
                        "those 6 months. New customer = first ship in the last 90 days. Gone quiet = no ship for at least 30 days and 3 times "
                        "its usual gap."),
                    "Data note": st.column_config.TextColumn(width="medium", help="Warnings about the data, not the customer. "
                        "Joint entry: the daily report names several companies for one cargo (e.g. HP/IOC/BPC), so the tonnes cannot be split. "
                        "Agent name?: this name is mostly written as a shipping agent, so the cargo owner may be someone else."),
                })
                gaps_txt = "".join(f" No daily reports exist for {_d(g['from'])} to {_d(g['to'])}; those days are not counted as silence."
                                   for g in per.get("report_gaps", []))
                st.markdown(f'<div class="ti-s">Latest daily report: {_d(per["latest_report"])}.{gaps_txt} '
                            f'{len(view)} of {len(df_cw)} customers. Container lines count calls, not tonnes. '
                            '"Joint entry" means the daily sheet names several receivers for one cargo. '
                            '"Agent name?" means the name is mostly used for a shipping agent.</div>', unsafe_allow_html=True)

                _head("Customer detail")
                names_cw = [r["customer"] for r in rows]
                sel_rows = list(getattr(getattr(ev_c, "selection", None), "rows", []) or [])
                if sel_rows and sel_rows[0] < len(view):
                    chosen = view.iloc[sel_rows[0]]["Customer"]
                    if st.session_state.get("ti_cust_applied") != chosen:      # apply each new click once
                        st.session_state["ti_cust_applied"] = chosen
                        st.session_state["ti_customer"] = chosen
                if st.session_state.get("ti_customer") not in names_cw:
                    st.session_state["ti_customer"] = names_cw[0]
                pick_c = st.selectbox("Customer", names_cw, key="ti_customer", label_visibility="collapsed")
                cd = api_get("/trade/customer", {"name": pick_c}, timeout=30)
                if cd:
                    s_ = cd["summary"]
                    _kpis([
                        ("Ship calls", f"{s_['calls']}", f'<div class="c">{s_["recent_calls"]} in {per["recent_label"]}</div>'),
                        ("Tonnes, complete months", _t(s_["tonnes"]), _chg(s_["change_pct"], f"{per['recent_label']} vs {per['previous_label']}")),
                        ("Foreign / coastal calls", f"{s_['foreign_calls']} / {s_['coastal_calls']}", f'<div class="c">main cargo: {s_["main_cargo"].lower()}</div>'),
                        ("Time its ships waited before berthing", f"{s_['waiting_ship_days']:g} ship-days",
                         f'<div class="c">{s_["not_ready_ship_days"]:g} because the customer was not ready'
                         + (f', {s_["ship_not_ready_ship_days"]:g} because the ship was not ready' if s_.get("ship_not_ready_ship_days") else "")
                         + '</div><div class="c">1 ship-day = 1 ship waiting 1 day; reasons as written by port staff</div>'),
                    ])
                    acc = cnotes["customers"].get(cd["customer"], {})
                    a1, a2 = st.columns([0.78, 0.22], vertical_alignment="top")
                    with a1:
                        st.markdown('<div class="ti-s">For the Traffic team: who looks after this customer, when to follow up, '
                                    'and notes from conversations. Filled in by staff with Update account.</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="ti-s"><b>Account owner:</b> {html.escape(acc.get("owner") or "not set")} &nbsp;·&nbsp; '
                                    f'<b>Follow-up:</b> {_d(acc["follow_up"]) if acc.get("follow_up") else "none"}</div>', unsafe_allow_html=True)
                        if acc.get("stage") or acc.get("reason") or acc.get("action"):
                            st.markdown(f'<div class="ti-s"><b>Opportunity:</b> {html.escape(acc.get("stage") or "not set")} &nbsp;·&nbsp; '
                                        f'<b>Reason:</b> {html.escape(acc.get("reason") or "not recorded")} &nbsp;·&nbsp; '
                                        f'<b>Proposed action:</b> {html.escape(acc.get("action") or "not set")}</div>', unsafe_allow_html=True)
                        for n_ in (acc.get("notes") or [])[:4]:
                            st.markdown(f'<div class="ti-note" style="color:#44403C">{html.escape(n_["at"][:10])}'
                                        f'{" · " + html.escape(n_["by"]) if n_.get("by") else ""}: {html.escape(n_["text"])}</div>',
                                        unsafe_allow_html=True)
                        if len(acc.get("notes") or []) > 4:
                            st.markdown(f'<div class="ti-s">{len(acc["notes"]) - 4} older notes kept.</div>', unsafe_allow_html=True)
                    with a2.popover("Update account", **_POP_KW):
                        own = st.text_input("Account owner", value=acc.get("owner", ""), key=f"acc_owner_{cd['customer']}")
                        has_fu = st.checkbox("Set a follow-up date", value=bool(acc.get("follow_up")), key=f"acc_has_fu_{cd['customer']}")
                        fu_d = st.date_input("Follow-up date", value=pd.Timestamp(acc["follow_up"]).date() if acc.get("follow_up") else None,
                                             key=f"acc_fu_{cd['customer']}", disabled=not has_fu)
                        stages_ = cnotes.get("stages", [])
                        actions_ = cnotes.get("actions", [])
                        stg = st.selectbox("Opportunity stage", [""] + stages_, index=([""] + stages_).index(acc.get("stage", "")) if acc.get("stage", "") in stages_ else 0,
                                           key=f"acc_stage_{cd['customer']}", help="Statistical gap = from the figures only; confirmed = Traffic has "
                                           "confirmed it with the customer; committed = backed by an agreement.")
                        rsn = st.text_input("Reason for the change (if known)", value=acc.get("reason", ""), key=f"acc_reason_{cd['customer']}",
                                            placeholder="e.g. refinery maintenance; moved part of exports to another port")
                        act = st.selectbox("Proposed action", [""] + actions_, index=([""] + actions_).index(acc.get("action", "")) if acc.get("action", "") in actions_ else 0,
                                           key=f"acc_action_{cd['customer']}")
                        nt = st.text_area("Add a note", key=f"acc_note_{cd['customer']}", height=80, placeholder="e.g. Met on 12 Nov; 2 ships expected in December")
                        who = st.text_input("Your name or team", key=f"acc_by_{cd['customer']}")
                        if st.button("Save", key=f"acc_save_{cd['customer']}", type="primary"):
                            try:
                                requests.post(headers=_auth_headers(), url=f"{API}/trade/customer-notes", timeout=10, json={
                                    "customer": cd["customer"], "owner": own,
                                    "follow_up": (fu_d.isoformat() if (has_fu and fu_d) else ""), "note": nt, "by": who,
                                    "stage": stg, "reason": rsn, "action": act})
                            except requests.RequestException:
                                st.error("Could not save. Is the backend running?")
                            st.rerun()
                    df_m = pd.DataFrame(cd["monthly"])
                    fig = go.Figure()
                    fig.add_bar(x=[_month(m) for m in df_m["month"]], y=df_m["tonnes"], name="Tonnes",
                                marker_color=[C_IN if c else C_PART for c in df_m["complete"]],
                                hovertemplate="%{x}: %{y:,.0f} t<extra></extra>")
                    fig.add_scatter(x=[_month(m) for m in df_m["month"]], y=df_m["calls"], name="Ship calls", yaxis="y2",
                                    mode="lines+markers", line=dict(color=C_OUT, width=2), marker=dict(size=5))
                    _layout(fig, 300, yaxis_title="Tonnes")
                    fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="Calls", showgrid=False, rangemode="tozero",
                                                  dtick=max(1, round((df_m["calls"].max() or 5) / 5)), tickformat=",d",
                                                  tickfont=dict(color=MUTED)))
                    st.markdown(f'<div class="ti-s">Monthly tonnes and ship calls. The last bar is light when the month is not complete yet.</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig, **_PLOT_KW)

                    a = b = st.container()          # full width, one under the other, so no column is cut off
                    with a:
                        st.markdown("**Cargo mix**: what this customer moves, largest first")
                        _tdetail(pd.DataFrame(cd["cargo_mix"]).replace({"direction": {"unknown": "not stated", "both": "import + export"}}).rename(columns={
                            "cargo": "Cargo", "direction": "Direction", "calls": "Calls", "tonnes": "Tonnes",
                            "foreign_calls": "Foreign", "coastal_calls": "Coastal"}), hide_index=True, width="stretch",
                            column_config={"Tonnes": st.column_config.NumberColumn(format="localized")})
                        st.markdown("**Why its ships waited**: waiting time by the reason written by port staff")
                        if cd["waiting_by_reason"]:
                            _tdetail(pd.DataFrame(cd["waiting_by_reason"]).rename(columns={
                                "reason": "Reason", "events": "Ships", "ship_days": "Ship-days"}), hide_index=True, width="stretch")
                        else:
                            st.caption("None of its ships was recorded waiting.")
                    with b:
                        st.markdown(f"**Due or waiting now**: this customer's ships in NMPA's report of {_d(cd['in_latest_report']['report_date'])}")
                        if cd["in_latest_report"]["ships"]:
                            _tdetail(pd.DataFrame(cd["in_latest_report"]["ships"])[
                                ["status", "vessel", "cargo", "quantity_t", "eta_or_arrival", "reason"]].rename(columns={
                                "status": "Status", "vessel": "Ship", "cargo": "Cargo", "quantity_t": "Tonnes",
                                "eta_or_arrival": "ETA or arrived", "reason": "Note"}), hide_index=True, width="stretch")
                        else:
                            st.caption("No ship for this customer in the latest report.")
                        st.markdown("**Latest ships**: most recent first")
                        _tdetail(pd.DataFrame(cd["recent_calls"])[["vessel", "cargo_group", "last_seen", "run", "tonnes"]]
                            .assign(last_seen=lambda d_: [_d(x) for x in d_["last_seen"]],
                                    run=lambda d_: d_["run"].map({"F": "Foreign", "C": "Coastal"}).fillna("Not stated"))
                            .rename(columns={"vessel": "Ship", "cargo_group": "Cargo", "last_seen": "Last seen",
                                             "run": "Foreign / coastal", "tonnes": "Tonnes"}),
                            hide_index=True, width="stretch", height=220,
                            column_config={"Tonnes": st.column_config.NumberColumn(format="localized")})
                    st.markdown(f'<div class="ti-s">Written in the daily reports as: {html.escape(", ".join(cd["spellings_seen"]) or "—")}</div>',
                                unsafe_allow_html=True)
                _src("NMPA daily vessel positions, receiver and shipper columns, with spellings merged by data/customer_aliases.csv")

        # ══ DATA AND METHODS ═══════════════════════════════════════════════════
        with t_data:
            dsx = api_get("/trade/data-status")
            if dsx:
                dr = dsx["daily_reports"]
                _head("Status of each dataset",
                      insight=dsx["claim"],
                      sub="Statuses: Original obtained (source file saved) \u00b7 Extraction checked (values match the source) \u00b7 "
                          "Reconciled (totals and comparable reports agree, or differences documented) \u00b7 NMPA-confirmed \u00b7 "
                          "Estimated (stated assumptions) \u00b7 Unresolved (missing evidence or unexplained conflict).")
                _stc = {}
                for x_ in dsx["datasets"]:
                    for part_ in str(x_["status"]).split(";"):
                        k_ = part_.strip().split(" (")[0]
                        k_ = "Unresolved" if "Unresolved" in k_ else k_
                        _stc[k_] = _stc.get(k_, 0) + 1
                _order = ["NMPA-confirmed", "Reconciled", "Extraction checked", "Original obtained", "Estimated", "Unresolved"]
                _keys = [k for k in _order if k in _stc] + [k for k in _stc if k not in _order]
                _sc = {"NMPA-confirmed": "#0F766E", "Reconciled": "#0F766E", "Extraction checked": "#1D4E89", "Original obtained": "#94A3B8",
                       "Estimated": "#D97706", "Unresolved": "#B91C1C"}
                _fds = go.Figure(go.Bar(y=_keys, x=[_stc[k] for k in _keys], orientation="h", marker_color=[_sc.get(k, "#94A3B8") for k in _keys],
                                        text=[_stc[k] for k in _keys], textposition="outside", cliponaxis=False))
                _fds.update_layout(height=80 + 34 * len(_keys), plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"),
                                   margin=dict(l=10, r=40, t=20, b=30), showlegend=False, xaxis_title="Datasets (a dataset can have two statuses)")
                _fds.update_yaxes(autorange="reversed", automargin=True)
                st.plotly_chart(_fds, **_W_CHART, config={"displayModeBar": False}, key="ti_chart_data_status")
                _tdetail(pd.DataFrame(dsx["datasets"]).rename(columns={"dataset": "Dataset", "status": "Status",
                             "evidence": "Evidence", "used_in": "Used in"}), hide_index=True, width="stretch", column_config={
                                 "Dataset": st.column_config.TextColumn(width="medium"), "Evidence": st.column_config.TextColumn(width="large")})
                st.markdown('<div class="ti-s"><b>Daily vessel reports, one by one</b> (data/daily_reports_manifest.csv): '
                            + "; ".join(f"{v} {html.escape(k.lower())}" for k, v in dr["by_status"].items())
                            + f'. The {dr["not_checked"]} unchecked days are listed in data/daily_reports_missing_pdfs.csv.</div>',
                            unsafe_allow_html=True)
            try:
                _srcreg = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "source_register.csv")
                with st.expander(f"Source register: {len(_srcreg)} original documents (publisher, period, pages used, units, revision, check status)"):
                    st.dataframe(_srcreg.drop(columns=["md5"]).rename(columns={"file": "File", "publisher": "Publisher", "document": "Document",
                                 "period": "Period", "pages_or_tables_used": "Pages / tables used", "units": "Units",
                                 "revision_status": "Revision status", "used_for": "Used for", "check_status": "Check status"}),
                                 hide_index=True, width="stretch")
                    st.markdown('<div class="ti-s">Full list with MD5 checksums: data/source_register.csv (rebuilt by scripts/build_source_register.py).</div>',
                                unsafe_allow_html=True)
            except Exception:
                pass
            _head("Where every number comes from")
            for key, s_ in brief["sources"].items():
                if key in ("performance", "waiting", "forecast"):   # other modules: Vessel Intelligence, Cargo Forecasting
                    continue
                st.markdown(f"**{s_['title']}**  \n`{s_['data_file']}`  \n{s_['origin']}  \nCoverage: {s_['coverage']}  \nChecked: {s_['checked']}")

            _head("Checks against official figures")
            if cw_ok:
                cov = cw["coverage_vs_official"]
                st.markdown(cov["verdict"])
                _cm = cov["months"]
                if _cm:
                    _fcv = go.Figure()
                    _fcv.add_scatter(x=[_month(r["month"]) for r in _cm], y=[r["traced_pct"] for r in _cm], name="Official cargo traced in daily reports",
                                     mode="lines+markers", line=dict(color="#1D4E89", width=3))
                    _fcv.add_scatter(x=[_month(r["month"]) for r in _cm], y=[r["named_customer_pct"] for r in _cm], name="With a named customer",
                                     mode="lines+markers", line=dict(color="#0F766E", width=3))
                    _fcv.update_layout(height=300, plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"),
                                       margin=dict(l=10, r=20, t=30, b=30), yaxis=dict(title="% of official tonnes", range=[0, 110], automargin=True),
                                       legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
                    st.plotly_chart(_fcv, **_W_CHART, config={"displayModeBar": False}, key="ti_chart_coverage")
                _tdetail(pd.DataFrame(cov["months"]).assign(month=lambda d_: [_month(m) for m in d_["month"]]).rename(columns={
                    "month": "Month", "official_t": "Official tonnes (non-container)", "traced_t": "Traced in daily reports",
                    "traced_pct": "Traced", "named_customer_pct": "With a named customer", "report_days": "Daily reports"}),
                    hide_index=True, width="stretch", column_config={
                        "Official tonnes (non-container)": st.column_config.NumberColumn(format="localized"),
                        "Traced in daily reports": st.column_config.NumberColumn(format="localized"),
                        "Traced": st.column_config.NumberColumn(format="%.0f%%"),
                        "With a named customer": st.column_config.NumberColumn(format="%.0f%%")})
            if sp and sp.get("available"):
                st.markdown("**Foreign vs coastal estimate:** " + sp["validation_against_ministry"]["verdict"])
            dq = trade_sum["data_quality"]
            xc = dq["prior_year_crosscheck"]
            st.markdown(f"**Monthly statements:** {dq['months_with_data']} of {dq['months_in_span']} months from "
                        f"{_month(dq['first_month'])} to {_month(dq['latest_month'])} have data. Missing: "
                        f"{', '.join(_month(m) for m in dq['missing_months']) or 'none'} (shown as gaps, never as zero). "
                        f"{len(dq['reconstructed_months'])} months are rebuilt from the prior-year column of later reports; "
                        f"{xc['exact_match_pct']}% of the figures that could be cross-checked match the original exactly.")

            _head("How each part works, and its limits")
            parts = [("Cargo flows and alerts", dq["notes"], brief["limits"])]
            if fc:
                parts.append(("Forecast", fc["how_it_works"], fc["limits"]))
            if cw_ok:
                parts.append(("Customers", cw["how_it_works"], cw["limits"]))
            if wt and wt.get("available"):
                parts.append(("Ship waiting", wt["how_it_works"], wt["limits"]))
            if sp and sp.get("available"):
                parts.append(("Foreign vs coastal by cargo", sp["how_it_works"], sp["limits"]))
            for title, how, lim in parts:
                with st.expander(title):
                    st.markdown("\n".join(f"- {x}" for x in how))
                    st.markdown("**Limits**\n" + "\n".join(f"- {x}" for x in lim))
            if cw_ok:
                nr = cw["name_review"]
                try:
                    _csv = requests.get(f"{API}/trade/customer-names.csv", timeout=30)
                    if _csv.ok:
                        st.download_button("Customer names to confirm with NMPA (CSV)", _csv.content,
                                           file_name="nmpa_customer_names_to_confirm.csv", mime="text/csv", key="ti_names")
                except requests.RequestException:
                    pass
                with st.expander("Customer names that need confirming"):
                    st.markdown(f"{nr['alias_rows']} spellings are merged by `data/customer_aliases.csv`; "
                                f"{nr['names_used_as_written']} names are used exactly as written. {nr['note']}")
                    st.markdown(", ".join(nr["examples_used_as_written"]))

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Cargo Anomaly & Risk Intelligence</span>
      <span class="sec-tag">Module 4 — Risk & Anomaly Engine</span>
      <div class="sec-sub">Multi-algorithm detection of cargo volume surges, volume decline anomalies, commodity movement deviations, and operational disruptions.</div>
    </div>
    
    <!-- Severity Scale Indicator -->
    <div style="background: #FFFDF9; border: 1px solid #F3E8D6; border-radius: 10px; padding: 12px 18px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
      <div style="font-size: 13px; font-weight: 700; color: #1C1917;">Cargo Risk Severity Progression:</div>
      <div style="display: flex; gap: 12px; font-size: 12px; font-weight: 700; flex-wrap: wrap;">
        <span style="background: #F0FDF4; color: #059669; border: 1px solid #DCFCE7; padding: 4px 12px; border-radius: 12px;">● Normal Operation</span>
        <span style="background: #EFF6FF; color: #2563EB; border: 1px solid #DBEAFE; padding: 4px 12px; border-radius: 12px;">▲ Low / Medium Risk</span>
        <span style="background: #FFFBEB; color: #D97706; border: 1px solid #FEF3C7; padding: 4px 12px; border-radius: 12px;">▲ High Risk Warning</span>
        <span style="background: #FEF2F2; color: #DC2626; border: 1px solid #FEE2E2; padding: 4px 12px; border-radius: 12px;">⚡ Critical Anomaly</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    anom_data = api_get("/anomaly/events") or {"events": []}
    hist_data = api_get("/anomaly/history") or {"history": {}}
    anom_events = anom_data.get("events", [])
    anom_hist = hist_data.get("history", {})

    c1, c2, c3, c4 = st.columns(4)
    sev_counts = {}
    for e in anom_events:
        sev_counts[e["severity"]] = sev_counts.get(e["severity"], 0) + 1
    c1.metric("Critical Anomalies", sev_counts.get("Critical", 0))
    c2.metric("High Severity", sev_counts.get("High", 0))
    c3.metric("Medium Severity", sev_counts.get("Medium", 0))
    c4.metric("Low Severity", sev_counts.get("Low", 0))

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([2, 3])

    with col_l:
        st.markdown('<div class="panel"><div class="panel-title">Active Anomaly Events</div>', unsafe_allow_html=True)
        for ev in anom_events:
            sev = ev["severity"]
            css_cls = f"alert-{sev.lower()}"
            badge_cls = f"badge-{sev[:4].lower()}"
            ts_str = ev["timestamp"][:16].replace("T", "  ")
            st.markdown(f"""
            <div class="alert-card {css_cls}">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div class="alert-title">{ev['event_id']} — {ev['type']}</div>
                <span class="badge {badge_cls}">{sev}</span>
              </div>
              <div class="alert-desc">{ev['description']}</div>
              <div class="alert-meta">
                <span><b>Commodity:</b> {ev['commodity']}</span>
                <span><b>Algorithm:</b> {ev['algorithm']}</span>
                <span><b>Confidence:</b> {int(ev['confidence']*100)}%</span>
                <span><b>Time:</b> {ts_str}</span>
              </div>
              <div style="margin-top:8px;font-size:11px;color:#92400E;background:rgba(245,158,11,0.08);padding:6px 10px;border-radius:6px;">
                <b>Action:</b> {ev['recommended_action']}
              </div>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_r:
        if anom_hist:
            fig_hist = go.Figure()
            sev_order = ["Critical", "High", "Medium", "Low"]
            sev_colors_list = ["#DC2626", "#D97706", "#2563EB", "#059669"]
            dates = []
            for sev, color in zip(sev_order, sev_colors_list):
                if sev in anom_hist:
                    dates = anom_hist[sev]["dates"]
                    fig_hist.add_trace(go.Bar(
                        x=dates, y=anom_hist[sev]["counts"],
                        name=sev, marker_color=color, opacity=0.85
                    ))
            fig_hist.update_layout(**PLOTLY_THEME, height=300, barmode="stack",
                                    title="30-Day Anomaly Frequency by Severity",
                                    xaxis_title="Date", yaxis_title="Event Count",
                                    legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig_hist, **_W_CHART)

        # Algorithm Legend
        st.markdown("""
        <div class="panel">
          <div class="panel-title">Detection Algorithms</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:12px;">
              <div style="display:flex;justify-content:space-between;"><span style="font-weight:700;font-size:13px;color:#166534;">Isolation Forest</span><span style="font-size:9px;font-weight:800;color:#166534;background:#DCFCE7;padding:2px 6px;border-radius:8px;">ACTIVE — scikit-learn</span></div>
              <div style="font-size:11px;color:#78716C;margin-top:4px;">Trained live on data/port_cargo_monthly.csv — flags real outlier months per commodity, not simulated.</div>
            </div>
            <div style="background:#F5F5F4;border:1px solid #E7E5E4;border-radius:8px;padding:12px;">
              <div style="display:flex;justify-content:space-between;"><span style="font-weight:700;font-size:13px;color:#78716C;">LSTM Anomaly Detection</span><span style="font-size:9px;font-weight:800;color:#78716C;background:#E7E5E4;padding:2px 6px;border-radius:8px;">ROADMAP</span></div>
              <div style="font-size:11px;color:#A8A29E;margin-top:4px;">Not yet implemented — would need daily/hourly sequence data, not present in the monthly dataset.</div>
            </div>
            <div style="background:#F5F5F4;border:1px solid #E7E5E4;border-radius:8px;padding:12px;">
              <div style="display:flex;justify-content:space-between;"><span style="font-weight:700;font-size:13px;color:#78716C;">Autoencoder</span><span style="font-size:9px;font-weight:800;color:#78716C;background:#E7E5E4;padding:2px 6px;border-radius:8px;">ROADMAP</span></div>
              <div style="font-size:11px;color:#A8A29E;margin-top:4px;">Not yet implemented.</div>
            </div>
            <div style="background:#F5F5F4;border:1px solid #E7E5E4;border-radius:8px;padding:12px;">
              <div style="display:flex;justify-content:space-between;"><span style="font-weight:700;font-size:13px;color:#78716C;">Transformer Detector</span><span style="font-size:9px;font-weight:800;color:#78716C;background:#E7E5E4;padding:2px 6px;border-radius:8px;">ROADMAP</span></div>
              <div style="font-size:11px;color:#A8A29E;margin-top:4px;">Not yet implemented.</div>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

    # ── Congestion Risk Classifier (RandomForestClassifier, real ML) ──
    st.markdown("---")
    cong = api_get("/forecast/congestion") or {}
    if cong.get("engine"):
        st.markdown('<div class="panel"><div class="panel-title">Port Congestion Risk Classifier (ML)</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:12px;color:#78716C;margin-bottom:12px;'>{cong.get('model', '')} — "
            f"backtested accuracy <b>{cong.get('model_accuracy_pct', 0)}%</b> "
            f"(F1 {cong.get('model_f1_macro', 0)}) on held-out months from data/port_cargo_monthly.csv.</div>",
            unsafe_allow_html=True
        )
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Current Risk Level", cong.get("risk_level", "—").upper(), f"Score {cong.get('current_risk_score', 0)}/10")
        cc2.metric("Anomalies (last 3 real months)", cong.get("anomalies_detected", 0))
        cc3.metric("Peak Risk Month (forecast)", cong.get("peak_congestion_month", "—"), f"Score {cong.get('peak_congestion_score', 0)}/10")

        traj = cong.get("forecast_risk_trajectory", [])
        if traj:
            fig_cong = go.Figure(go.Bar(
                x=[t["month"] for t in traj], y=[t["risk_score"] for t in traj],
                marker_color=[{"HIGH": "#DC2626", "MODERATE": "#D97706", "LOW": "#059669"}.get(t["risk_tier"], "#78716C") for t in traj],
                text=[t["risk_tier"] for t in traj], textposition="outside",
            ))
            fig_cong.update_layout(**PLOTLY_THEME, height=260, title="Projected Congestion Risk (chained from cargo forecast)",
                                    xaxis_title="Month", yaxis_title="Risk Score (0-10)")
            fig_cong.update_xaxes(type="category")  # "2026-08" etc. are month labels, not a continuous date axis
            fig_cong.update_yaxes(range=[0, 11])
            st.plotly_chart(fig_cong, **_W_CHART)

        prs = cong.get("port_risk_scores", {})
        if prs:
            st.markdown("<div style='font-size:12px;color:#78716C;margin-top:4px;'><b>Per-facility risk (data-derived vessel percentile):</b> "
                        + " &nbsp;|&nbsp; ".join(f"{k.replace('_',' ')}: {v}/10" for k, v in prs.items())
                        + "</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6 — INCENTIVE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[5]:
    # Incentive Engine - evidence only: NMPA tonnes x NMPA Scale of Rates, measured before/after, plain arithmetic.
    # Reuses the section helpers and styles defined in the Trade Intelligence tab (_head, _kpis, _src, _layout, ...).
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    cr = lambda v: "\u2014" if v is None else (("\u2212" if v < 0 else "") + (f"\u20b9{abs(v) / 1e7:,.2f} cr" if abs(v) >= 1e6
                                                                           else f"\u20b9{abs(v) / 1e5:,.1f} lakh"))
    tn = lambda v: f"{v / 1e6:,.2f} MMT" if v >= 1e6 else f"{v / 1e3:,.0f} thousand t"

    # Product-style building blocks for this tab: the answer first, details on demand.
    st.markdown("<style>" + "".join([
        ".ie-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:8px 0 16px 0}",
        ".ie-card{background:#FFFFFF;border:1px solid #E7E5E4;border-radius:10px;padding:14px 16px;border-top:3px solid #CBD5E1}",
        ".ie-card.good{border-top-color:#0F766E}.ie-card.watch{border-top-color:#D97706}.ie-card.act{border-top-color:#B91C1C}",
        ".ie-card.info{border-top-color:#1D4E89}",
        ".ie-card .l{font-size:12.5px;color:#57534E}",
        ".ie-card .v{font-size:25px;font-weight:750;color:#1C1917;line-height:1.15;margin-top:4px;font-variant-numeric:tabular-nums}",
        ".ie-card .s{font-size:12.5px;color:#57534E;margin-top:4px;line-height:1.35}",
        ".ie-take{font-size:15px;color:#1C1917;margin:0 0 10px 0;line-height:1.45}",
        ".ie-chip{display:inline-block;font-size:11.5px;font-weight:650;padding:2px 9px;border-radius:999px;margin:0 6px 4px 0;",
        "background:#F1F5F9;color:#334155;white-space:nowrap}",
        ".ie-chip.act{background:#FEE2E2;color:#991B1B}.ie-chip.watch{background:#FEF3C7;color:#92400E}",
        ".ie-chip.good{background:#CCFBF1;color:#115E59}.ie-chip.info{background:#DBEAFE;color:#1E3A8A}",
        ".ie-acts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:8px 0 14px 0}",
        ".ie-act{background:#FFFFFF;border:1px solid #E7E5E4;border-radius:10px;padding:14px 16px}",
        ".ie-act .t{font-size:15px;font-weight:700;color:#1C1917;margin:6px 0 4px 0;line-height:1.3}",
        ".ie-act .w{font-size:13px;color:#44403C;line-height:1.45}",
        ".ie-act .g{font-size:12px;color:#78716C;margin-top:8px}",
        "details.ie-notes{margin:2px 0 18px 0}details.ie-notes summary{font-size:12.5px;color:#78716C;cursor:pointer}",
        "details.ie-notes .ti-s{margin:6px 0}details.ie-notes .src{font-size:12px;color:#A8A29E;margin-top:4px}",
        ".ie-data{font-size:12.5px;color:#57534E;margin:-6px 0 10px 0}",
        ".ie-tw{max-height:460px;overflow:auto;border:1px solid #E7E5E4;border-radius:10px;background:#FFFFFF;margin:4px 0 4px 0}",
        ".ie-tbl{border-collapse:collapse;width:100%;font-size:13px;color:#1C1917}",
        ".ie-tbl th{position:sticky;top:0;background:#F5F5F4;color:#57534E;font-weight:600;text-align:left;padding:8px 10px;",
        "border-bottom:1px solid #E7E5E4;white-space:normal;vertical-align:bottom}",
        ".ie-tbl td{padding:7px 10px;border-bottom:1px solid #F5F5F4;vertical-align:top;white-space:normal;word-break:normal;",
        "overflow-wrap:break-word;line-height:1.4}",
        ".ie-tbl td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}",
        ".ie-tbl tr:hover td{background:#FAFAF9}",
        ".ie-csv{font-size:12px;margin:2px 0 10px 0}.ie-csv a{color:#78716C;text-decoration:none}",
        "@media (max-width:900px){.ie-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.ie-acts{grid-template-columns:1fr}}",
    ]) + "</style>", unsafe_allow_html=True)
    _ie_notes = []
    _ie_last_src = [None]

    def _cards(items):
        """KPI cards: (label, value, sub-line, tone) with tone good / watch / act / info."""
        st.markdown('<div class="ie-cards">' + "".join(
            f'<div class="ie-card {t}"><div class="l">{html.escape(l)}</div><div class="v">{v}</div><div class="s">{s_}</div></div>'
            for l, v, s_, t in items) + "</div>", unsafe_allow_html=True)

    def _ie_txt(t):
        """Show the rupee sign and arrows on screen (the PDF brief uses 'Rs' and '->')."""
        return t.replace("Rs ", "\u20b9").replace(" -> ", " \u2192 ")

    def _htable(data, *a_, **k_):
        """Analysis table: shown inside a closed 'See the details' drop-down, so each section leads with its chart."""
        df_ = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        if df_.empty:
            return _htable_raw(df_, *a_, **k_)
        with st.expander(f"See the details ({len(df_)} row{'s' if len(df_) != 1 else ''})"):
            _htable_raw(df_, *a_, **k_)

    def _hlist(data, *a_, **k_):
        """Worklist: shown open, because officers act on it."""
        return _htable_raw(data, *a_, **k_)

    _NAVY, _GREEN, _AMBER, _RED, _GREY, _LIGHT = "#1D4E89", "#0F766E", "#D97706", "#B91C1C", "#94A3B8", "#D6D3D1"

    def _ie_fig(fig, height, xtitle=None, ytitle=None, legend=True):
        """The Incentive Engine chart style: white, small dark-grey type, no toolbar."""
        fig.update_layout(height=height, plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"),
                          margin=dict(l=10, r=40, t=30, b=30), showlegend=legend, bargap=0.25,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
        if xtitle: fig.update_xaxes(title=xtitle)
        if ytitle: fig.update_yaxes(title=ytitle)
        fig.update_xaxes(gridcolor="#EEEEEE", zerolinecolor="#CCCCCC", automargin=True)
        fig.update_yaxes(automargin=True)
        return fig

    def _short(t, n):
        t = " ".join(str(t).split())
        return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(" ,;(") + "\u2026"

    def _ie_show(fig, key):
        st.plotly_chart(fig, **_W_CHART, config={"displayModeBar": False}, key=key)

    st.markdown("<style>.ie-tile{border:1px solid #E7E5E4;border-radius:10px;padding:12px 14px 4px 14px;border-top:4px solid #94A3B8;background:#fff}"
                ".ie-tile.good{border-top-color:#0F766E}.ie-tile.watch{border-top-color:#D97706}.ie-tile.act{border-top-color:#B91C1C}"
                ".ie-tile.info{border-top-color:#1D4E89}.ie-tile .l{font-size:12.5px;color:#57534E}"
                ".ie-tile .v{font-size:28px;font-weight:750;color:#1C1917;line-height:1.15;margin-top:2px;font-variant-numeric:tabular-nums}"
                ".ie-tile .s{font-size:12.5px;color:#57534E;margin-top:2px;min-height:18px}</style>", unsafe_allow_html=True)

    def _kpi_tile(col, label, value, sub, tone, ys=None, key=None, color="#1D4E89"):
        """A KPI tile: big number, one line of context, and a sparkline of the recent trend when there is one."""
        with col:
            st.markdown(f'<div class="ie-tile {tone}"><div class="l">{html.escape(label)}</div><div class="v">{html.escape(value)}</div>'
                        f'<div class="s">{sub}</div></div>', unsafe_allow_html=True)
            if ys:
                f_ = go.Figure(go.Scatter(y=ys, mode="lines", line=dict(color=color, width=2), fill="tozeroy",
                                          fillcolor="rgba(29,78,137,0.08)", hoverinfo="y"))
                f_.add_scatter(x=[len(ys) - 1], y=[ys[-1]], mode="markers", marker=dict(color=color, size=7), hoverinfo="skip")
                lo, hi = min(ys), max(ys)
                f_.update_layout(height=62, margin=dict(l=0, r=0, t=2, b=0), showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
                                 xaxis=dict(visible=False), yaxis=dict(visible=False, range=[lo - (hi - lo) * 0.15, hi + (hi - lo) * 0.15]))
                st.plotly_chart(f_, **_W_CHART, config={"displayModeBar": False, "staticPlot": True}, key=key)

    def _htable_raw(data, hide_index=True, width=None, column_config=None, height=None, key=None, **_kw):
        """A table that wraps long text instead of cutting it, with a small CSV download link."""
        import base64 as _b64
        import numpy as _np
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        if df.empty:
            st.markdown('<div class="ti-s">Nothing to show.</div>', unsafe_allow_html=True)
            return

        def cell(col, v):
            if v is None or (isinstance(v, float) and _np.isnan(v)):
                return '<td>\u2014</td>'
            if isinstance(v, (bool, _np.bool_)):
                return f'<td>{"Yes" if v else "No"}</td>'
            if isinstance(v, (int, _np.integer)):
                return f'<td class="n">{int(v):,}</td>'
            if isinstance(v, (float, _np.floating)):
                txt = f"{v:.1f}%" if str(col).lower().startswith("share") else (f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}")
                return f'<td class="n">{txt}</td>'
            return f"<td>{html.escape(_ie_txt(str(v)))}</td>"
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
        body = "".join("<tr>" + "".join(cell(c, v) for c, v in zip(df.columns, row)) + "</tr>" for row in df.itertuples(index=False))
        csv_ = _b64.b64encode(df.to_csv(index=False).encode("utf-8")).decode()
        st.markdown(f'<div class="ie-tw"><table class="ie-tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
                    f'<div class="ie-csv"><a download="table.csv" href="data:text/csv;base64,{csv_}">\u2913 Download CSV</a></div>',
                    unsafe_allow_html=True)

    def _chip(text, tone=""):
        return f'<span class="ie-chip {tone}">{html.escape(text)}</span>'

    def _first_sentence(text):
        m = re.search(r"(?<=[a-z0-9\)%\]])\.\s+(?=[A-Z0-9])", text or "")
        return ((text[:m.start() + 1], text[m.end():]) if m else (text or "", ""))

    def _flush_notes(source=None):
        """Notes and sources of the section just shown, collapsed under one small 'Notes and sources' line."""
        notes = list(_ie_notes)
        _ie_notes.clear()
        if not notes and (not source or source == _ie_last_src[0]):
            return
        _ie_last_src[0] = source
        st.markdown('<details class="ie-notes"><summary>Notes and sources</summary>' + "".join(notes)
                    + (f'<div class="src">Source: {html.escape(source)}</div>' if source else "") + "</details>",
                    unsafe_allow_html=True)

    def _note_md(text, **_kw):
        _ie_notes.append(text)

    def _src(text):
        _flush_notes(text)

    def _head(title, sub=None, insight=None):
        """Section title, one short takeaway, and the method behind a 'How it works' button."""
        _flush_notes()
        insight = _ie_txt(insight) if insight else insight
        first, rest = _first_sentence(insight) if insight else ("", "")
        more = " ".join(x for x in (rest, sub) if x)
        st.markdown('<div style="height:22px"></div>', unsafe_allow_html=True)
        c1, c2 = st.columns([0.8, 0.2], vertical_alignment="center")
        c1.markdown(f'<div class="ti-h" style="margin:0">{title}</div>', unsafe_allow_html=True)
        if more:
            try:
                with c2.popover("\u24d8 How it works"):
                    st.markdown(more)
            except Exception:
                c2.markdown(f'<details class="ie-notes"><summary>How it works</summary><div class="ti-s">{more}</div></details>',
                            unsafe_allow_html=True)
        if first:
            st.markdown(f'<div class="ie-take">{first}</div>', unsafe_allow_html=True)
    rv = api_get("/incentive/revenue", timeout=30)
    st.markdown('<div class="ti-head"><h2>Incentive Engine</h2><p>What each cargo earns, who and what is at risk, and what a '
                'discount would cost, from NMPA\'s own data.</p></div>', unsafe_allow_html=True)
    if not (rv and rv.get("available")):
        st.error("The Incentive Engine data did not load. Start the backend from the project folder, then refresh this page.")
    else:
        dcur = api_get("/incentive/data-current") or {}
        if dcur:
            st.markdown(f'<div class="ie-data">Data to: {_chip("NMPA " + _m(dcur["nmpa_statements_through"]), "info")}'
                        f'{_chip("Ministry " + _m(dcur["ministry_reports_through"]), "info")}'
                        f'{_chip("Daily reports " + _d(dcur["daily_reports_through"]), "info")}'
                        f'{_chip("Estimates, not NMPA bills")}</div>', unsafe_allow_html=True)
        it0, it1, it2, it3, it4 = st.tabs(["Start here", "What we earn", "Customers & cargo", "Plan a discount", "Schemes"])
        with it0:
            # Start here: this week's actions, guide by role, glossary, one-page brief
            act = api_get("/incentive/actions", timeout=90)
            kc0 = api_get("/incentive/key-customers", timeout=60) or {}
            op0 = api_get("/incentive/opportunities", timeout=30) or {}
            nn0 = api_get("/incentive/nmpa-notices") or {}
            t0 = rv["total"]
            ch0 = (t0["revenue_rs"] / t0["revenue_prev_rs"] - 1) * 100 if t0["revenue_prev_rs"] else None
            stake0 = sum(o.get("wharfage_at_stake_rs") or 0 for o in op0.get("cargos", []))
            # KPI tiles: the four numbers to look at first, with their recent trend
            _fl0 = [r for r in (api_get("/trade/flows", {"months": 24}) or {}).get("series", []) if r.get("total_tonnes")]
            try:
                _pf0 = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "nmpa_performance_monthly.csv")
                _ta0 = (_pf0[(_pf0.metric == "turn_round_time_hrs") & (_pf0.period == "month") & (_pf0.category == "overall")
                             & (_pf0.year == "current") & (_pf0.basis == "pilot")].drop_duplicates("month").sort_values("month").tail(12))
            except Exception:
                _ta0 = pd.DataFrame()
            k1_, k2_, k3_, k4_ = st.columns(4)
            if _fl0:
                last_ = _fl0[-1]; ly_ = next((r for r in _fl0 if r["month"] == f'{int(last_["month"][:4]) - 1}{last_["month"][4:]}'), None)
                yo_ = (last_["total_tonnes"] / ly_["total_tonnes"] - 1) * 100 if ly_ and ly_["total_tonnes"] else None
                _kpi_tile(k1_, f'Cargo handled, {pd.Timestamp(last_["month"] + "-01"):%b %Y}', f'{last_["total_tonnes"] / 1e6:.2f} MMT',
                          (f'{yo_:+.1f}% on the same month last year' if yo_ is not None else "NMPA monthly statement"),
                          "good" if (yo_ or 0) >= 0 else "watch", [r["total_tonnes"] / 1e6 for r in _fl0[-18:]], "ie_tile_cargo")
            _kpi_tile(k2_, f'Estimated wharfage, {rv["period"]}', f'\u20b9{t0["revenue_rs"] / 1e7:,.0f} cr',
                      (f'{ch0:+.1f}% on {rv["previous_period"]}' if ch0 is not None else ""), "good" if (ch0 or 0) >= 0 else "watch")
            if not _ta0.empty:
                tl_ = float(_ta0["value"].iloc[-1])
                _kpi_tile(k3_, f'Ship turnaround, {pd.Timestamp(_ta0["month"].iloc[-1] + "-01"):%b %Y}', f"{tl_:.1f} h",
                          f'12-month average {_ta0["value"].mean():.1f} h \u00b7 lower is better', "good" if tl_ <= _ta0["value"].mean() else "watch",
                          [float(v) for v in _ta0["value"]], "ie_tile_turnaround", color="#D97706")
            _kpi_tile(k4_, "Key customers at risk", f'{kc0.get("at_risk_count", 0)} of {len(kc0.get("rows", []))}',
                      (f'wharfage down \u20b9{(kc0.get("at_risk_quarter_fall_rs") or 0) / 1e7:,.1f} cr last quarter' if kc0.get("at_risk_quarter_fall_rs")
                       else "customers making up most of NMPA's wharfage"), "act" if kc0.get("at_risk_count") else "good")
            infc0 = [x for x in nn0.get("notices", []) if x["status"] == "In force"]
            b1_, b2_ = st.columns([1, 3])
            if b1_.button("Prepare the brief (PDF)", key="ie_brief_go",
                          help="One page for the Chairman or a Board meeting: actions, customers at risk, schemes ending, claims, "
                               "other ports, busy berths. Made only when you press this; nothing is sent."):
                try:
                    r_ = requests.get(f"{API}/incentive/brief.pdf", headers=_auth_headers(), timeout=120)
                    r_.raise_for_status()
                    st.session_state["ie_brief_pdf"] = r_.content
                except requests.RequestException as e_:
                    st.error(f"Could not prepare the brief: {e_}")
            if st.session_state.get("ie_brief_pdf"):
                b2_.download_button("\u2913 Download the one-page brief", st.session_state["ie_brief_pdf"],
                                    file_name=f"NMPA_incentive_brief_{pd.Timestamp.now():%Y-%m-%d}.pdf", mime="application/pdf",
                                    key="ie_brief_dl")
            nc0 = api_get("/incentive/nmpa-circulars") or {}
            if nc0.get("open"):
                st.markdown(f'<div class="ie-take" style="font-size:14.5px"><b>NMPA circulars:</b> {nc0["open"]} to look at '
                            f'(Schemes tab).</div>', unsafe_allow_html=True)
            ex0 = api_get("/incentive/expiring") or {}
            cw0 = api_get("/incentive/competitor-watch") or {}
            if cw0.get("new"):
                st.info(f"{len(cw0['new'])} new incentive or tariff notice(s) at competitor ports ("
                        + ", ".join(sorted({r['port'] for r in cw0['new']})) + "). See Schemes \u2192 Competitor watch.")
            due0 = (ex0.get("review_now", 0) or 0) + (ex0.get("plan_review", 0) or 0)
            _cards([
                (f"Wharfage earned, {rv['period']}", cr(t0["revenue_rs"]),
                 (f"{ch0:+.1f}% on last year" if ch0 is not None else "") + " (estimate)", "good" if (ch0 or 0) >= 0 else "watch"),
                ("Key customers at risk", f"{kc0.get('at_risk_count', 0)} of {len(kc0.get('rows', []))}",
                 (f"{kc0.get('at_risk_falling_count', 0)} lost {cr(-kc0.get('at_risk_quarter_fall_rs', 0))} last quarter; "
                  f"{kc0.get('at_risk_waiting_count', 0)} had ships waiting") if kc0 else "", "act" if kc0.get("at_risk_count") else "good"),
                ("Cargo going to other ports", cr(stake0), f"wharfage at stake, {op0.get('period', '')}", "watch" if stake0 else "good"),
                ("NMPA schemes in force", str(len(infc0)),
                 (f"{due0} end within 6 months: plan their review (Schemes tab)" if due0 else "from NMPA's own trade notices; see the Schemes tab"),
                 "watch" if due0 else "info"),
            ])
            if act:
                b1, b2 = st.columns([0.72, 0.28], vertical_alignment="bottom")
                b1.markdown(f'<div class="ti-h" style="margin:10px 0 2px 0">This week\'s actions</div>'
                            f'<div class="ie-take">{len(act["actions"])} things to do, worked out from the latest data.</div>',
                            unsafe_allow_html=True)
                try:
                    _bp = requests.get(f"{API}/incentive/brief.pdf", timeout=90)
                    if _bp.ok:
                        b2.download_button("\u2913 One-page brief (PDF)", _bp.content, file_name="NMPA_incentive_brief.pdf",
                                           mime="application/pdf", key="ie_brief", **_fullw(st.download_button))
                except requests.RequestException:
                    pass
                tone = {1: ("act", "Do now"), 2: ("watch", "This week"), 3: ("info", "When possible")}
                st.markdown('<div class="ie-acts">' + "".join(
                    f'<div class="ie-act">{_chip(tone.get(x["priority"], ("", ""))[1], tone.get(x["priority"], ("", ""))[0])}'
                    f'{_chip(x["who"])}<div class="t">{html.escape(x["action"])}</div>'
                    f'<div class="w">{html.escape(_ie_txt(x["why"]))}</div>'
                    f'<div class="g">Where: {html.escape(x["where"])} &nbsp;\u2192&nbsp; {html.escape(x["next"])}</div></div>'
                    for x in act["actions"]) + "</div>", unsafe_allow_html=True)
                g1, g2 = st.columns(2)
                with g1.expander("How each team uses this tab"):
                    for g in act["role_guide"]:
                        st.markdown(f"**{g['role']}**: {g['use_for']}.  \n*Where:* {g['where']}.  \n*Records:* {g['records']}.")
                with g2.expander("Words used here, in plain language"):
                    for w, m_ in act["glossary"]:
                        st.markdown(f"**{w}**: {m_}")

            # 0. Baseline KPIs for this module
            kp = api_get("/incentive/kpis", timeout=60)
            if kp and kp.get("available"):
                with st.expander("Baseline KPIs for this module: what is measured, and what is pending NMPA data"):
                    _hlist(pd.DataFrame([{"Area": r["area"], "KPI": r["kpi"], "Current value": r["value"], "Status": r["status"],
                                                "Source / what is needed": r["source"]} for r in kp["rows"]]),
                                 hide_index=True, width="stretch", column_config={
                                     "KPI": st.column_config.TextColumn(width="large"),
                                     "Current value": st.column_config.TextColumn(width="medium"),
                                     "Source / what is needed": st.column_config.TextColumn(width="large")})
                    _note_md(f'<div class="ti-s">{html.escape(kp["note"])}</div>', unsafe_allow_html=True)

            _flush_notes()
        with it1:
            tot = rv["total"]
            top = rv["cargos"][0]
            chg = (tot["revenue_rs"] / tot["revenue_prev_rs"] - 1) * 100 if tot["revenue_prev_rs"] else None
            _cards([
                (f"Wharfage earned, {rv['period']}", cr(tot["revenue_rs"]),
                 (f"{chg:+.1f}% on {rv['previous_period']}" if chg is not None else "") + " (estimate)", "good" if (chg or 0) >= 0 else "watch"),
                ("Largest earner", top["cargo"], f'{cr(top["revenue_rs"])} on {top["tonnes"] / 1e6:.2f} MMT', "info"),
                ("Coastal concession given up", cr(tot["coastal_concession_rs"]), "coastal rates are lower than foreign", "info"),
                ("Cargos priced", f"{len(rv['cargos'])}", f'{tot["tonnes"] / 1e6:.1f} MMT; the rest is listed below', "info"),
            ])
            _note_md(f'<div class="ti-s">{html.escape(rv["tariff"])} Wharfage only; both periods priced at today\'s rates, so the change '
                        'reflects tonnes, not tariff revisions.</div>', unsafe_allow_html=True)

            # 1. What each cargo earns
            _head("Estimated wharfage attributable to each cargo",
                  insight=(f"{top['cargo']} brings the most wharfage ({cr(top['revenue_rs'])}). The coastal concession costs little on "
                           "wharfage at New Mangalore, because the Scale of Rates charges the same rate for coastal and foreign crude, "
                           "POL products and iron ore." if tot["coastal_concession_rs"] < 0.01 * tot["revenue_rs"] else None),
                  sub="Tonnes from NMPA's monthly statements x the wharfage rate in the Scale of Rates, split foreign/coastal using the F/C "
                      "flag in NMPA's daily reports. Sorted by estimated wharfage, largest first.")
            _cg = list(reversed(rv["cargos"]))
            _fa = go.Figure()
            _fa.add_bar(y=[c["cargo"] for c in _cg], x=[(c["revenue_prev_rs"] or 0) / 1e7 for c in _cg], orientation="h",
                        name=rv["previous_period"], marker_color="#D6D3D1")
            _fa.add_bar(y=[c["cargo"] for c in _cg], x=[c["revenue_rs"] / 1e7 for c in _cg], orientation="h", name=rv["period"],
                        marker_color="#1D4E89", text=[f"\u20b9{c['revenue_rs'] / 1e7:.1f} cr" for c in _cg], textposition="outside", cliponaxis=False)
            _fa.update_layout(barmode="group", height=60 + 42 * len(_cg), xaxis_title="\u20b9 crore (estimate)", plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=90, t=56, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
            _w1, _w2 = st.columns([1, 1])
            with _w1:
                st.markdown(f"**Where the wharfage comes from** ({rv['period']})")
                _ftm = go.Figure(go.Treemap(labels=[c["cargo"] for c in _cg], parents=[""] * len(_cg), values=[c["revenue_rs"] / 1e7 for c in _cg],
                                            texttemplate="<b>%{label}</b><br>\u20b9%{value:.1f} cr<br>%{percentRoot:.0%}", textfont=dict(size=13),
                                            marker=dict(colors=[c["revenue_rs"] for c in _cg], colorscale=[[0, "#DCE7F3"], [1, "#1D4E89"]], line=dict(color="white", width=2)),
                                            hovertemplate="%{label}: \u20b9%{value:.2f} cr<extra></extra>"))
                _ftm.update_traces(root_color="white", marker_pad=dict(t=2, l=2, r=2, b=2))
                _ftm.update_layout(height=380, margin=dict(l=0, r=0, t=4, b=0), paper_bgcolor="white")
                _ie_show(_ftm, "ie_chart_treemap")
            with _w2:
                _chg = sorted([c for c in _cg if c.get("revenue_prev_rs") is not None], key=lambda c: -abs(c["revenue_change_rs"] or 0))
                _top = _chg[:7]; _rest = sum((c["revenue_change_rs"] or 0) for c in _chg[7:])
                _xs = [rv["previous_period"]] + [c["cargo"] for c in _top] + (["Other cargo"] if _chg[7:] else []) + [rv["period"]]
                _vals = ([sum(c["revenue_prev_rs"] or 0 for c in _chg) / 1e7] + [(c["revenue_change_rs"] or 0) / 1e7 for c in _top]
                         + ([_rest / 1e7] if _chg[7:] else []) + [0])
                st.markdown("**What changed since last year**")
                _fwf = go.Figure(go.Waterfall(x=_xs, y=_vals, measure=["absolute"] + ["relative"] * (len(_xs) - 2) + ["total"],
                                              increasing=dict(marker=dict(color=_GREEN)), decreasing=dict(marker=dict(color=_RED)),
                                              totals=dict(marker=dict(color=_NAVY)), connector=dict(line=dict(color="#CCCCCC")),
                                              text=[f"{v:+.1f}" if 0 < k_ < len(_xs) - 1 else "" for k_, v in enumerate(_vals)], textposition="outside"))
                _ie_fig(_fwf, 380, ytitle="\u20b9 crore (estimate)", legend=False); _fwf.update_xaxes(tickangle=-35)
                _run = [_vals[0]]
                for v_ in _vals[1:-1]:
                    _run.append(_run[-1] + v_)
                _lo_, _hi_ = min(_run), max(_run)
                _pad = max(2.0, (_hi_ - _lo_) * 0.6)
                _fwf.update_yaxes(range=[max(0, _lo_ - _pad), _hi_ + _pad])
                st.caption("Axis starts above zero so the changes are visible; the end bars are the two totals.")
                _ie_show(_fwf, "ie_chart_waterfall")
            with st.expander("See the full table, and how each figure is calculated"):
                rdf = pd.DataFrame([{
                    "Cargo": c["cargo"], "Tonnes": c["tonnes"], "Coastal": f"{c['coastal_share_pct']:.0f}%",
                    "Rate foreign / coastal (\u20b9/t)": f"{c['rate_foreign']:.2f} / {c['rate_coastal']:.2f}",
                    f"Wharfage {rv['period']}": cr(c["revenue_rs"]), f"Same months last year": cr(c["revenue_prev_rs"]),
                    "Change": _ptxt((c["revenue_rs"] / c["revenue_prev_rs"] - 1) * 100 if c["revenue_prev_rs"] else None, 0),
                    "Coastal concession": cr(c["coastal_concession_rs"]),
                    "Evidence": "Estimate (full tariff); billed figure not yet provided",
                    "Scale of Rates line": (f"p.{c['sor_page']}: " if c.get("sor_page") else "") + c["sor_line"]
                        + (f" ({c['spm_share_pct']:.0f}% of crude at the SPM, rest at berths)" if c.get("spm_share_pct") is not None else "")
                        + (f" (excludes {c['excluded_customer']}, {c['excluded_share_pct']:.0f}% of this cargo)" if c["excluded_share_pct"] else ""),
                } for c in rv["cargos"]])
                _hlist(rdf, hide_index=True, width="stretch", column_config={
                    "Cargo": st.column_config.TextColumn(width="medium"),
                    "Tonnes": st.column_config.NumberColumn(format="localized"),
                    "Coastal": st.column_config.TextColumn(help="Share of this cargo's tonnes on coastal (C) runs in NMPA's daily reports"),
                    "Coastal concession": st.column_config.TextColumn(help="Coastal tonnes x (foreign rate - coastal rate): wharfage the coastal rate gives up"),
                    "Scale of Rates line": st.column_config.TextColumn(width="large")})
                calc_pick = st.selectbox("Show the calculation for", [c["cargo"] for c in rv["cargos"]], key="inc_calc",
                                         help="Every step from the source document to the rupee figure")
                cc_ = next(c for c in rv["cargos"] if c["cargo"] == calc_pick)
                st.markdown('<div class="ti-insight">' + "<br>".join(f"{i + 1}. {html.escape(_ie_txt(t))}" for i, t in enumerate(cc_["calculation"]))
                            + "</div>", unsafe_allow_html=True)
                _note_md(f'<div class="ti-s"><b>Estimated at full tariff:</b> {cr(cc_["estimate_full_tariff_rs"])} &nbsp;·&nbsp; '
                            f'<b>After known adjustments:</b> {html.escape(cc_["adjustments_status"]) if cc_["estimate_after_known_adjustments_rs"] is None else cr(cc_["estimate_after_known_adjustments_rs"])} '
                            f'&nbsp;·&nbsp; <b>Billed (NMPA Finance):</b> {html.escape(cc_["billed_status"]) if cc_["billed_rs"] is None else cr(cc_["billed_rs"])}</div>',
                            unsafe_allow_html=True)
            with st.expander("What is not estimated here, and why"):
                for n_ in rv["not_estimated"]:
                    st.markdown(f"- **{n_['item']}**: {n_['why']}")
            _src("NMPA monthly commodity statements; NMPA Scale of Rates (wharfage); NMPA daily vessel reports (F/C flag, customers)")

            # 1a. Check against NMPA's own accounts
            ac = api_get("/incentive/accounts-check", timeout=30)
            if ac and ac.get("available"):
                close = [r["cargo"] for r in ac["rows"] if r["difference_pct_vs_2023_24"] is not None and abs(r["difference_pct_vs_2023_24"]) <= 16]
                _head("Reconciliation with NMPA's published accounts",
                      insight=(f"The rates used here are within about 15% of the income per tonne in NMPA's published accounts for 2023-24 "
                               f"for {', '.join(close)}. The differences are shown, not hidden: tariff revisions since 2023-24 account for "
                               "part of them; the rest is not explained by the data held." if close else
                               "Compare the rates used here with the income per tonne in NMPA's published accounts."),
                      sub=ac["explain"])
                _ra = [r for r in ac["rows"] if r.get("implied_rate_2023_24")]
                if _ra:
                    _fr = go.Figure()
                    _fr.add_bar(x=[r["cargo"] for r in _ra], y=[r["implied_rate_2023_24"] for r in _ra], name="NMPA earned per tonne (2023-24 accounts)",
                                marker_color=_LIGHT)
                    _fr.add_bar(x=[r["cargo"] for r in _ra], y=[r["our_rate_today"] for r in _ra], name="Rate used here (today)", marker_color=_NAVY)
                    _ie_fig(_fr, 340, ytitle="\u20b9 per tonne"); _fr.update_layout(barmode="group")
                    _ie_show(_fr, "ie_chart_reconciliation")
                _htable(pd.DataFrame([{
                    "Cargo": r["cargo"],
                    "NMPA income 2022-23 (actual)": cr(r["income_2022_23_rs"]), "Tonnes 2022-23": r["tonnes_2022_23"],
                    "Earned per tonne 2022-23": f"\u20b9{r['implied_rate_2022_23']:.2f}" if r["implied_rate_2022_23"] else "\u2014",
                    "NMPA income 2023-24 (revised estimate)": cr(r["income_2023_24_rs"]),
                    "Earned per tonne 2023-24": f"\u20b9{r['implied_rate_2023_24']:.2f}" if r["implied_rate_2023_24"] else "\u2014",
                    "Rate used here (today)": f"\u20b9{r['our_rate_today']:.2f}",
                    "Difference vs 2023-24": _ptxt(r["difference_pct_vs_2023_24"], 0)} for r in ac["rows"]]),
                    hide_index=True, width="stretch", column_config={"Tonnes 2022-23": st.column_config.NumberColumn(format="localized")})
                pa = api_get("/incentive/published-accounts")
                if pa and pa.get("available"):
                    with st.expander("NMPA's actual income by activity, 2023-24 and 2024-25 (Administration Report)"):
                        _hlist(pd.DataFrame([{"Line": r["line"], "Head": r["head"], "2024-25 (Rs cr)": r["fy_2024_25_rs_cr"],
                                                    "2023-24 (Rs cr)": r["fy_2023_24_rs_cr"]} for r in pa["rows"]]),
                                     hide_index=True, width="stretch", column_config={"Head": st.column_config.TextColumn(width="large")})
                        _note_md(f'<div class="ti-s">{html.escape(pa["note"])}</div>', unsafe_allow_html=True)
                        _src(pa["source"])
                _src(ac["source"])

            # 1b. PPP berths: royalty, not wharfage
            pr = api_get("/incentive/ppp-royalty", timeout=30)
            if pr and pr.get("available"):
                ctn = pr["containers"]
                _head("Cargo at PPP berths: NMPA earns a royalty",
                      insight=(f"Containers (Berth 14, {ctn['operator']}): about {ctn['laden_teu']:,} laden TEU in {pr['period']}. "
                               + (f"At what NMPA actually earned per laden TEU in 2023-24 (\u20b9{ctn['implied_rs_per_laden_teu_2023_24']:,}), "
                                  f"that is about {cr(ctn['royalty_at_implied_rs'])} in royalty; at the \u20b9{ctn['royalty_rs_per_teu']:,.0f} "
                                  f"quoted in 2019, at least {cr(ctn['royalty_estimate_rs'])}."
                                  if ctn.get("implied_rs_per_laden_teu_2023_24") else
                                  f"At least {cr(ctn['royalty_estimate_rs'])} in royalty at \u20b9{ctn['royalty_rs_per_teu']:,.0f} per TEU.")),
                      sub=f"Coal other than UPCL is handled at {pr['coal_berth_16']['berth']}, operated by {pr['coal_berth_16']['operator']}, where NMPA "
                          f"earns {pr['coal_berth_16']['basis']}. {pr['coal_berth_16']['note']}")
                _note_md('<div class="ti-s">' + html.escape(ctn.get("implied_note", "")) + " " + html.escape(ctn["royalty_source"]) + " "
                            + " ".join(html.escape(x) for x in ctn["limits"]) + "</div>", unsafe_allow_html=True)

            if ac and ac.get("available") and ac.get("other_lines"):
                _ol = [o for o in ac["other_lines"] if any(o.get(k) for k in ("actual_2022_23_rs", "re_2023_24_rs", "be_2024_25_rs"))]
                if _ol:
                    _fo = go.Figure()
                    for k_, nm_, col_ in (("actual_2022_23_rs", "2022-23 actual", _LIGHT), ("re_2023_24_rs", "2023-24 revised", _GREY),
                                          ("be_2024_25_rs", "2024-25 budget", _NAVY)):
                        _fo.add_bar(y=[_short(o["line"], 40) for o in _ol], x=[(o.get(k_) or 0) / 1e7 for o in _ol], orientation="h",
                                    name=nm_, marker_color=col_)
                    _ie_fig(_fo, 110 + 50 * len(_ol), xtitle="\u20b9 crore (NMPA's accounts)"); _fo.update_layout(barmode="group")
                    _fo.update_yaxes(autorange="reversed")
                    st.markdown("**NMPA's income from PPP berths and own-arrangement cargo**")
                    _ie_show(_fo, "ie_chart_ppp_income")
            if ac and ac.get("available"):
                with st.expander("NMPA income from PPP berths and own-arrangement cargo (from its accounts)"):
                    _hlist(pd.DataFrame([{"Income line": o["line"], "2022-23 actual": cr(o["actual_2022_23_rs"]),
                                                "2023-24 revised estimate": cr(o["re_2023_24_rs"]), "2024-25 budget": cr(o["be_2024_25_rs"])}
                                               for o in ac["other_lines"]]), hide_index=True, width="stretch")
                    t_ = ac["totals_re_2023_24"]
                    _note_md(f'<div class="ti-s">For scale, 2023-24 (revised estimate): cargo handling and storage charges '
                                f'{cr(t_["TOTAL_CHSC"])}, port and dock charges {cr(t_["TOTAL_PDC"])}, total operating income '
                                f'{cr(t_["TOTAL_OPINC"])}.</div>', unsafe_allow_html=True)
                _src(ac["source"])

            # customer wharfage (shown in Protect key customers; used by the deal desk)
            cwf = api_get("/incentive/customer-wharfage", timeout=30)

            _flush_notes()
            # Finance check: our estimates against NMPA's bills
            fk_ = api_get("/incentive/finance-check") or {}
            _head("Check our estimates against NMPA's bills",
                  insight=(f"Our wharfage estimates match NMPA's bills to {fk_['accuracy_pct']:.1f}% "
                           f"({fk_['months']}, {len(fk_['rows'])} cargos)." if fk_.get("available") else
                           "Every money figure here is an estimate until it is checked against NMPA's bills. When Finance "
                           "uploads one year of billed wharfage by cargo, this section shows how close each estimate is, and why."),
                  sub=fk_.get("method") or "")
            if fk_.get("available"):
                _cards([
                    ("Accuracy of our estimates", f"{fk_['accuracy_pct']:.1f}%", f"{fk_['months']}", "good" if fk_["accuracy_pct"] >= 90 else "watch"),
                    ("Billed by NMPA", cr(fk_["billed_total_rs"]), "wharfage, cargos compared", "info"),
                    ("Our estimate", cr(fk_["estimate_total_rs"]), "same cargos and months", "info")])
                _htable(pd.DataFrame([{
                    "Cargo": r["cargo"], "Months": r["months"],
                    "Billed": cr(r["billed_rs"]), "Our estimate": cr(r["estimate_rs"]),
                    "Difference": f"{r['amount_difference_pct']:+.1f}%",
                    "Tonnes: statements vs billed": f"{r['tonnes_difference_pct']:+.1f}%" if r["tonnes_difference_pct"] is not None else "\u2014",
                    "Rate per tonne: ours vs billed": (f"\u20b9{r['estimate_rate']:,.2f} vs \u20b9{r['billed_rate']:,.2f}"
                                                        if r["estimate_rate"] and r["billed_rate"] else "\u2014"),
                    "Rates used": r["rate_basis"]} for r in fk_["rows"]]))
                if fk_.get("other_charges"):
                    st.caption("Also uploaded, not yet compared: " + "; ".join(f"{o['charge'].replace('_', ' ')} {cr(o['amount_rs'])}" for o in fk_["other_charges"]))
                if fk_.get("uploaded_by"):
                    st.caption(f"Uploaded by {fk_['uploaded_by']}. The file stays on this computer (not uploaded to GitHub).")
            with st.expander("Upload NMPA's billing (Finance)" if fk_.get("uploaded") else "How Finance can upload NMPA's billing", expanded=False):
                st.markdown("One row per **month, cargo and charge**: `month` (e.g. 2026-05), `cargo` (one of the names below), "
                            "`charge` (wharfage, port_dues, pilotage, berth_hire or other), `tonnes` billed and `amount_rs` billed.")
                st.download_button("\u2913 Template (CSV)", (fk_.get("template") or "month,cargo,charge,tonnes,amount_rs\n"),
                                   file_name="NMPA_billing_template.csv", mime="text/csv", key="fk_tpl")
                st.caption("Cargo names: " + "; ".join(fk_.get("cargos", [])))
                up_ = st.file_uploader("Billing file (CSV)", type=["csv"], key="fk_upload")
                if up_ is not None and st.button("Check and save", key="fk_save"):
                    try:
                        rr_ = requests.post(f"{API}/incentive/finance-billing",
                                            json={"csv_text": up_.getvalue().decode("utf-8-sig"), "by": ""},
                                            headers=_auth_headers(), timeout=120)
                        if rr_.ok:
                            st.success(f"Saved {rr_.json()['rows']} rows ({rr_.json()['months']}). Refresh the page to see the comparison.")
                        else:
                            det_ = rr_.json().get("detail", rr_.text)
                            st.error("Not saved:\n\n" + ("\n".join(f"- {x}" for x in det_) if isinstance(det_, list) else str(det_)))
                    except requests.RequestException as e_:
                        st.error(f"Could not reach the backend: {e_}")
            _src("NMPA Finance billing (uploaded); NMPA monthly commodity statements; NMPA Scale of Rates")

        with it2:
            # 1d. Protect key customers
            kc = api_get("/incentive/key-customers", timeout=60)
            if kc and kc.get("available") and kc["rows"]:
                _head("Protect key customers",
                      insight=(f"{kc['at_risk_count']} of the {len(kc['rows'])} key customers show a warning sign: "
                               f"{kc.get('at_risk_falling_count', 0)} lost {cr(-kc['at_risk_quarter_fall_rs'])} of wharfage in {kc['q2_label']} "
                               f"against {kc['q1_label']}, and {kc.get('at_risk_waiting_count', 0)} had ships waiting because the customer "
                               f"was not ready. "
                               f"These {len(kc['rows'])} customers make up {kc['key_share_pct']:.0f}% of the wharfage traced to customers. "
                               + (f"{kc['no_owner_count']} have no NMPA account owner recorded." if kc["no_owner_count"] else "")),
                      sub=kc["rules"] + " Keeping existing cargo comes before chasing new cargo.")
                _kr = list(reversed(kc["rows"]))
                _fb = go.Figure(go.Bar(y=[r["customer"] for r in _kr], x=[r["wharfage_rs"] / 1e7 for r in _kr], orientation="h",
                                       marker_color=[{"High": "#B91C1C", "Medium": "#D97706"}.get(r["risk"], "#0F766E") for r in _kr],
                                       text=[f"{r['risk'] if r['risk'] != 'None found' else 'OK'} \u00b7 {r['share_pct']:.0f}%" for r in _kr],
                                       textposition="outside", cliponaxis=False, hovertext=["; ".join(r["signals"]) or "No warning sign" for r in _kr]))
                _fb.update_layout(height=60 + 34 * len(_kr), xaxis_title=f"Wharfage \u20b9 crore, {kc['period']} (estimate)", plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=90, t=56, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
                _rk = [r for r in kc["rows"] if r.get("wharfage_q1_rs")]
                _fm = go.Figure()
                for risk_, col_ in (("High", _RED), ("Medium", _AMBER), ("None found", _GREEN)):
                    rr_ = [r for r in _rk if (r["risk"] if r["risk"] in ("High", "Medium") else "None found") == risk_]
                    if not rr_:
                        continue
                    _fm.add_scatter(x=[(r["change_q2_vs_q1_rs"] or 0) / r["wharfage_q1_rs"] * 100 for r in rr_], y=[r["wharfage_rs"] / 1e7 for r in rr_],
                                    mode="markers+text", text=[r["customer"] for r in rr_], textposition="top center", name=f"Risk: {risk_.lower()}",
                                    marker=dict(size=[max(12, min(60, r["share_pct"] * 1.6)) for r in rr_], color=col_, opacity=0.75,
                                                line=dict(color="white", width=1)),
                                    hovertext=[f'{r["customer"]}: {"; ".join(r["signals"]) or "no warning sign"}' for r in rr_], hoverinfo="text")
                _fm.add_vline(x=0, line_color="#CCCCCC")
                _ie_fig(_fm, 460, xtitle=f"Wharfage change, {kc['q2_label']} against {kc['q1_label']} (%)",
                        ytitle=f"Wharfage, {kc['period']} (\u20b9 crore, log scale)")
                _fm.update_yaxes(type="log", tickvals=[1, 2, 5, 10, 20, 50, 100, 200], ticktext=["1", "2", "5", "10", "20", "50", "100", "200"])
                _xv = [(r["change_q2_vs_q1_rs"] or 0) / r["wharfage_q1_rs"] * 100 for r in _rk]
                if _xv:
                    _fm.update_xaxes(range=[min(_xv) - 45, max(_xv) + 45])
                st.markdown("**Customer risk map**: right = growing, left = falling; higher = more wharfage; bubble = share; colour = risk")
                _ie_show(_fm, "ie_chart_keycust")
                st.markdown(_chip("High risk", "act") + _chip("Medium", "watch") + _chip("No warning sign", "good"), unsafe_allow_html=True)
                with st.expander("See the full table: warning signs, follow-up and next step"):
                    _hlist(pd.DataFrame([{
                        "Customer": r["customer"], "Risk": r["risk"], "Share": r["share_pct"], "Main cargo": r["main_cargo"],
                        f"Wharfage {kc['period']}": cr(r["wharfage_rs"]),
                        f"Wharfage {kc['q2_label']} vs {kc['q1_label']}": cr(r["change_q2_vs_q1_rs"]),
                        "Warning signs": "; ".join(r["signals"]) or "\u2014",
                        "Follow-up": r["engagement"] + (f"; follow-up {_d(r['follow_up'])}" if r["follow_up"] else "")
                                     + (" (due)" if r["follow_up_due"] else ""),
                        "Next step": r["next_step"]} for r in kc["rows"]]), hide_index=True, width="stretch",
                        column_config={"Share": st.column_config.ProgressColumn("Share of traced wharfage", format="%.1f%%", min_value=0, max_value=100),
                                       "Warning signs": st.column_config.TextColumn(width="large"),
                                       "Next step": st.column_config.TextColumn(width="large")})
                _note_md('<div class="ti-s">' + " ".join(html.escape(c) for c in kc["caveats"]) + "</div>", unsafe_allow_html=True)
                with st.expander("Record what you learned from a customer (owner, reason, follow-up)"):
                    cn_all = api_get("/trade/customer-notes") or {"customers": {}, "stages": []}
                    k1, k2 = st.columns(2)
                    kc_c = k1.selectbox("Customer", [r["customer"] for r in kc["rows"]], key="kc_rec_c")
                    cur_ = cn_all["customers"].get(kc_c, {})
                    kc_owner = k2.text_input("Account owner (NMPA)", value=cur_.get("owner", ""), key=f"kc_owner_{kc_c}")
                    k3, k4 = st.columns(2)
                    stg_list = [""] + cn_all.get("stages", [])
                    kc_stage = k3.selectbox("Opportunity stage", stg_list, key=f"kc_stage_{kc_c}",
                                            index=stg_list.index(cur_.get("stage", "")) if cur_.get("stage", "") in stg_list else 0)
                    kc_fu_on = k4.checkbox("Set a follow-up date", value=bool(cur_.get("follow_up")), key=f"kc_fuon_{kc_c}")
                    kc_fu = k4.date_input("Follow-up", value=(pd.Timestamp(cur_["follow_up"]).date() if cur_.get("follow_up")
                                                                else (pd.Timestamp.today() + pd.Timedelta(days=14)).date()),
                                          key=f"kc_fu_{kc_c}", disabled=not kc_fu_on)
                    kc_reason = st.text_input("Reason for the change (from the customer)", value=cur_.get("reason", ""), key=f"kc_reason_{kc_c}",
                                              placeholder="e.g. refinery maintenance in August; volumes back from October")
                    kc_note = st.text_area("Note", key=f"kc_note_{kc_c}", height=70)
                    kc_by = st.text_input("Your name or team", key=f"kc_by_{kc_c}")
                    if st.button("Save", key=f"kc_save_{kc_c}"):
                        try:
                            r_ = requests.post(headers=_auth_headers(), url=f"{API}/trade/customer-notes", timeout=15, json={
                                "customer": kc_c, "owner": kc_owner, "stage": kc_stage, "reason": kc_reason,
                                "follow_up": kc_fu.isoformat() if kc_fu_on else "", "note": kc_note, "by": kc_by})
                            if r_.ok:
                                st.success("Saved. It also shows in Trade Intelligence, Customers.")
                                st.rerun()
                            else:
                                st.error(r_.json().get("detail", "Could not save."))
                        except requests.RequestException:
                            st.error("Could not save. Is the backend running?")
                _src("NMPA daily vessel reports (customer tonnes, waiting); NMPA Scale of Rates; customer notes from Trade Intelligence")

            # Customer call sheet: one page for the officer before calling a customer (made on request; nothing is sent)
            if kc and kc.get("rows"):
                cs1, cs2, cs3 = st.columns([3, 1, 2])
                cust_cs = cs1.selectbox("Prepare a call sheet for", [r["customer"] for r in kc["rows"]], key="cs_cust",
                                        help="One page: cargo trend, waiting on their side, schemes they can use, names, follow-up so far, "
                                             "and suggested talking points. Made only when you press the button.")
                if cs2.button("Prepare", key="cs_go"):
                    try:
                        r_ = requests.get(f"{API}/incentive/customer-sheet.pdf", params={"customer": cust_cs},
                                          headers=_auth_headers(), timeout=120)
                        r_.raise_for_status()
                        st.session_state["cs_pdf"] = (cust_cs, r_.content)
                    except requests.RequestException as e_:
                        st.error(f"Could not prepare the call sheet: {e_}")
                if st.session_state.get("cs_pdf") and st.session_state["cs_pdf"][0] == cust_cs:
                    cs3.download_button(f"\u2913 Call sheet: {cust_cs}", st.session_state["cs_pdf"][1],
                                        file_name=f"call_sheet_{cust_cs.replace(' ', '_')}.pdf", mime="application/pdf", key="cs_dl")

            # 2. Cargo lost to other ports - a statistical gap that starts a commercial review, not a discount
            op = api_get("/incentive/opportunities", timeout=30)
            if op and op.get("available") and op["cargos"]:
                big = op["cargos"][0]
                _head("Cargo lost to other ports: investigate before any incentive",
                      insight=(f"{big['cargo']}: New Mangalore's share fell from {big['share_prev_pct']:.1f}% to {big['share_pct']:.1f}% of all "
                               f"major ports ({op['period']}). Keeping last year's share would have meant about {big['tonnes_not_won'] / 1e3:,.0f} "
                               f"thousand tonnes more, worth {cr(big['wharfage_at_stake_rs'])} in wharfage. First step: find out why."),
                      sub=op["explain"])
                _oc = list(reversed(op["cargos"]))
                _fc = go.Figure()
                _fc.add_bar(y=[o["cargo"] for o in _oc], x=[o["share_prev_pct"] for o in _oc], orientation="h", name="Share last year",
                            marker_color="#D6D3D1")
                _fc.add_bar(y=[o["cargo"] for o in _oc], x=[o["share_pct"] for o in _oc], orientation="h", name="Share this year",
                            marker_color="#B91C1C", text=[(cr(o["wharfage_at_stake_rs"]) + " at stake") if o.get("wharfage_at_stake_rs") else ""
                                                        for o in _oc], textposition="outside", cliponaxis=False)
                _fc.update_layout(barmode="group", height=60 + 52 * len(_oc), xaxis_title="New Mangalore's share of all major ports (%)", plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=90, t=56, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
                st.plotly_chart(_fc, **_W_CHART, config={"displayModeBar": False}, key="ie_chart_lost")
                with st.expander("See the numbers"):
                    _hlist(pd.DataFrame([{
                        "Cargo": o["cargo"], "Signal": o["signal"], "Share last year": f"{o['share_prev_pct']:.2f}%", "Share this year": f"{o['share_pct']:.2f}%",
                        "New Mangalore growth": _ptxt(o["nmpa_growth_pct"]), "Other major ports' growth": _ptxt(o["other_ports_growth_pct"]),
                        "Tonnes not won": o["tonnes_not_won"], "Wharfage at stake": cr(o["wharfage_at_stake_rs"])}
                        for o in op["cargos"]]), hide_index=True, width="stretch", column_config={
                            "Signal": st.column_config.TextColumn(width="medium", help="Statistical gap = from the figures only. It becomes a "
                                                                  "confirmed opportunity once Traffic confirms it with the customer, and committed "
                                                                  "volume once there is an agreement."),
                            "Tonnes not won": st.column_config.NumberColumn(format="localized",
                                help="Last year's share x this year's all-major-port tonnes, minus what New Mangalore handled")})
                for o in op["cargos"]:
                    with st.expander(f"{o['cargo']}: who to talk to, and what the data already says"):
                        if o["customers"]:
                            cn_ = (api_get("/trade/customer-notes") or {}).get("customers", {})
                            st.markdown("**Opportunity stage** (recorded in Trade Intelligence, Customer detail, Update account): " + "; ".join(
                                f"{c['customer']}: {cn_.get(c['customer'], {}).get('stage') or 'Statistical gap (from the figures only)'}"
                                + (f" ({cn_[c['customer']]['reason']})" if cn_.get(c['customer'], {}).get('reason') else "")
                                for c in o["customers"]))
                            st.markdown("**Main customers of this cargo** (daily reports): " + "; ".join(
                                f"{c['customer']} ({c['status'].lower()}, {_ptxt(c['change_pct'], 0)} over the last 3 months"
                                + (f", {c['not_ready_ship_days']:g} ship-days waiting because not ready" if c["not_ready_ship_days"] else "") + ")"
                                for c in o["customers"]))
                        if o["flags"]:
                            st.markdown("**Before considering a discount:**\n" + "\n".join(f"- {f}" for f in o["flags"]))
                        st.markdown(f"**Suggested next step:** {o['suggested_next_step']}")
                        fbk = f"incentive|{o['cargo']}"
                        fb_all = (api_get("/trade/alert-feedback") or {})
                        cur_fb = fb_all.get("items", {}).get(fbk, {})
                        sts = fb_all.get("statuses", ["Open", "Looking into it", "Explained", "Not relevant"])
                        r1, r2, r3 = st.columns([0.3, 0.5, 0.2], vertical_alignment="bottom")
                        new_st = r1.selectbox("Review status", sts, index=sts.index(cur_fb.get("status", "Open")) if cur_fb.get("status", "Open") in sts else 0,
                                              key=f"opp_st_{o['cargo']}")
                        new_nt = r2.text_input("Finding (reason, evidence)", value=cur_fb.get("note", ""), key=f"opp_nt_{o['cargo']}")
                        if r3.button("Save", key=f"opp_sv_{o['cargo']}"):
                            try:
                                requests.post(headers=_auth_headers(), url=f"{API}/trade/alert-feedback", json={"key": fbk, "status": new_st, "note": new_nt}, timeout=10)
                            except requests.RequestException:
                                st.error("Could not save. Is the backend running?")
                            st.rerun()
                sr = api_get("/incentive/schemes") or {}
                if sr.get("reason_actions"):
                    with st.expander("Which action fits which reason"):
                        _hlist(pd.DataFrame(sr["reason_actions"], columns=["Confirmed reason", "Suggested action"]),
                                     hide_index=True, width="stretch")
                        _note_md('<div class="ti-s">The reason is entered by Traffic after speaking to the customer; the tool does not '
                                    'guess it from tonnage.</div>', unsafe_allow_html=True)
                _src("Ministry of Ports Table-2 (all major ports) and NMPA statements; customers from NMPA daily vessel reports")

            # 2c. Seasonal windows: a benefit only in a cargo's regularly quiet months
            sw_head = st.container()
            sw_d = st.number_input("Discount to compare (%)", 1.0, 50.0, 10.0, 1.0, key="sw_disc")
            sw = api_get("/incentive/seasonal-windows", {"discount_pct": sw_d}, timeout=90)
            if not sw:
                with sw_head:
                    st.warning("Seasonal windows could not be loaded (the backend did not answer in time or reported an error). "
                               "Reload the page; if it persists, check the backend window for an error.")
            if sw and sw.get("available") and sw["rows"]:
                reg = [r for r in sw["rows"] if r["regular"] and r["quiet_months"] and r.get("occupancy_quiet_pct") is not None]
                spare = max(reg, key=lambda r: (r["occupancy_other_pct"] or 0) - (r["occupancy_quiet_pct"] or 0)) if reg else None
                with sw_head:
                  _head("Seasonal windows: a benefit only in quiet months",
                      insight=((
                          f"{spare['cargo']} is regularly quiet in {', '.join(spare['quiet_months'])}, when its berths "
                          f"({', '.join(spare['berths'])}) had a ship on {spare['occupancy_quiet_pct']}% of days against "
                          f"{spare['occupancy_other_pct']}% in other months; a {sw_d:g}% discount in those months only would cost "
                          f"{cr(spare['cost_quiet_months_rs'])} a year against {cr(spare['cost_all_year_rs'])} all year."
                          if spare and (spare["occupancy_other_pct"] or 0) > (spare["occupancy_quiet_pct"] or 0) else "")
                          + f" {sw['status']}."),
                      sub=f"Quiet month = at or below 90% of an average month, over the complete financial years held. Costs on the "
                          f"last 12 months' tonnes ({sw['last12']}) at today's rates. Berth occupancy = share of report days a berth had a ship.")
                _sr = [r for r in sw["rows"] if r.get("seasonal_index")]
                if _sr:
                    _months = list(_sr[0]["seasonal_index"].keys())
                    _fd = go.Figure(go.Heatmap(z=[[r["seasonal_index"][m] for m in _months] for r in _sr], x=_months,
                                               y=[r["cargo"] + ("" if r["regular"] else " (irregular)") for r in _sr],
                                               colorscale=[[0, "#B91C1C"], [0.4, "#FEF3C7"], [0.5, "#FFFFFF"], [1, "#0F766E"]], zmin=50, zmax=150,
                                               text=[[f"{r['seasonal_index'][m]:.0f}" if r["seasonal_index"][m] is not None else "" for m in _months] for r in _sr],
                                               texttemplate="%{text}", colorbar=dict(title="100 = average")))
                    _fd.update_layout(height=70 + 34 * len(_sr), title=dict(text="Monthly cargo against an average month (red = quiet)", font=dict(size=13)), plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=40, t=44, b=30), legend=dict(orientation="h", y=1.12, x=0))
                    st.plotly_chart(_fd, **_W_CHART, config={"displayModeBar": False}, key="ie_chart_season")
                with st.expander("See the full table: cost of the discount, berths and occupancy"):
                    _hlist(pd.DataFrame([{
                        "Cargo": r["cargo"], "Regular pattern": "Yes" if r["regular"] else "No",
                        "Quiet months": ", ".join(r["quiet_months"]) or "\u2014",
                        f"{sw_d:g}% all year": cr(r["cost_all_year_rs"]), f"{sw_d:g}% in quiet months only": cr(r["cost_quiet_months_rs"]),
                        "Berths used": ", ".join(r["berths"]) or "\u2014",
                        "Berth occupancy: quiet / other months": (f"{r['occupancy_quiet_pct']}% / {r['occupancy_other_pct']}%"
                                                                  if r.get("occupancy_quiet_pct") is not None else "\u2014"),
                        "Reading": r["verdict"]} for r in sw["rows"]]), hide_index=True, width="stretch",
                        column_config={"Reading": st.column_config.TextColumn(width="large")})
                _note_md('<div class="ti-s">' + "<br>".join("\u2022 " + html.escape(c) for c in sw["caveats"]) + "</div>",
                            unsafe_allow_html=True)
                _src("NMPA monthly commodity statements (seasonal pattern, tonnes); NMPA daily vessel reports (berth occupancy); NMPA Scale of Rates")

            # 2b. Published wharfage: NMPA vs Cochin
            tc = api_get("/incentive/tariff-comparison")
            if tc and tc.get("available"):
                _head("Published wharfage: New Mangalore and Cochin", insight=tc["conclusion"], sub=tc["scope"])
                _tr = [r for r in tc["rows"] if r.get("nmpa_foreign") is not None and r.get("cochin_foreign") is not None]
                _fe = go.Figure()
                _fe.add_bar(x=[r["cargo"] for r in _tr], y=[r["nmpa_foreign"] for r in _tr], name="New Mangalore", marker_color="#1D4E89",
                            text=[f"\u20b9{r['nmpa_foreign']:.0f}" for r in _tr], textposition="outside", cliponaxis=False)
                _fe.add_bar(x=[r["cargo"] for r in _tr], y=[r["cochin_foreign"] for r in _tr], name="Cochin", marker_color="#A8A29E",
                            text=[f"\u20b9{r['cochin_foreign']:.0f}" for r in _tr], textposition="outside", cliponaxis=False)
                _fe.update_layout(barmode="group", height=360, yaxis_title="Published wharfage, foreign cargo (\u20b9 per tonne)", plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=90, t=56, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
                st.plotly_chart(_fe, **_W_CHART, config={"displayModeBar": False}, key="ie_chart_cochin")
                with st.expander("See the full comparison table (with page numbers)"):
                    _hlist(pd.DataFrame([{
                        "Cargo": r["cargo"], "Comparability": r["comparability"],
                        "NMPA foreign / coastal (Rs/t)": (f"{r['nmpa_foreign']:.2f} / {r['nmpa_coastal']:.2f}" if r.get("nmpa_foreign") is not None else "\u2014"),
                        "Cochin foreign / coastal (Rs/t)": (f"{r['cochin_foreign']:.2f} / {r['cochin_coastal']:.2f}" if r.get("cochin_foreign") is not None else "\u2014"),
                        "NMPA vs Cochin (foreign)": _ptxt(r.get("nmpa_vs_cochin_foreign_pct")),
                        "Pages (PDF) NMPA / Cochin": (f"{int(r['nmpa_page'])} / {int(r['cochin_page'])}" if r.get("nmpa_page") else "\u2014"),
                        "Note": r.get("note") or ""} for r in tc["rows"]]), hide_index=True, width="stretch",
                        column_config={"Note": st.column_config.TextColumn(width="large"), "Comparability": st.column_config.TextColumn(width="medium")})
                _src(f"NMPA: {tc['sources']['nmpa']}. Cochin: {tc['sources']['cochin']}.")
            tv_ = api_get("/incentive/tariff-comparison-voc")
            if tv_ and tv_.get("available"):
                with st.expander(f"Published wharfage: New Mangalore and V.O. Chidambaranar (Tuticorin), {tv_['period']}"):
                    st.markdown(f'<div class="ti-insight">{html.escape(_ie_txt(tv_["conclusion"]))}</div>', unsafe_allow_html=True)
                    _hlist(pd.DataFrame([{
                        "Cargo": r["cargo"], "Comparability": r["comparability"],
                        "NMPA foreign / coastal": (f"{r['nmpa_foreign']:.2f} / {r['nmpa_coastal']:.2f}" if r.get("nmpa_foreign") is not None else "\u2014"),
                        "VOC Zone A foreign / coastal": (f"{r['voc_zone_a_foreign']:.2f} / {r['voc_zone_a_coastal']:.2f}" if r.get("voc_zone_a_foreign") is not None else "\u2014"),
                        "VOC Zone B foreign / coastal": (f"{r['voc_zone_b_foreign']:.2f} / {r['voc_zone_b_coastal']:.2f}" if r.get("voc_zone_b_foreign") is not None else "\u2014"),
                        "NMPA vs VOC A / B (foreign)": (f"{_ptxt(r['nmpa_vs_voc_a_foreign_pct'])} / {_ptxt(r['nmpa_vs_voc_b_foreign_pct'])}" if r.get("nmpa_vs_voc_a_foreign_pct") is not None else "\u2014"),
                        "Pages (PDF) NMPA / VOC": (f"{int(r['nmpa_page'])} / {int(r['voc_page'])}" if r.get("nmpa_page") else "\u2014"),
                        "Note": r.get("note") or ""} for r in tv_["rows"]]), hide_index=True, width="stretch",
                        column_config={"Note": st.column_config.TextColumn(width="large")})
                    _src(f"NMPA: {tv_['sources']['nmpa']}. VOC: {tv_['sources']['voc']}. Both w.e.f. 01.05.2025.")
            cs = api_get("/incentive/cochin-schemes")
            if cs and cs.get("available"):
                with st.expander("How another major port designs schemes: Cochin Port examples"):
                    _note_md(f'<div class="ti-s">{html.escape(cs["note"])}</div>', unsafe_allow_html=True)
                    for x in cs["schemes"]:
                        st.markdown(f"**{x['notice']}** ({_d(x['date'])}): {x['type']}  \n"
                                    f"*Who benefits:* {x['who_benefits']}  \n*Terms:* {x['terms']}  \n*Period:* {x['period']}  \n"
                                    f"*Design features worth noting:* {x['design_features']}")

            _flush_notes()
            # Confirm customer names (Traffic): one list, biggest cargo first; nothing changes until an officer applies
            nm_ = api_get("/incentive/customer-names") or {}
            if nm_.get("items"):
                _head("Confirm customer names",
                      insight=(f"{nm_['decided']} of {nm_['total']} checked. The list starts with the names behind the most cargo, so a "
                               f"few minutes cover most tonnes. Every customer figure depends on these names."),
                      sub=nm_.get("rule", ""))
                kinds_ = {"All": None, "Spelling merges": "spelling", "Company renames and mergers": "identity", "Possible matches": "candidate"}
                f1, f2, f3 = st.columns([2, 1, 1])
                kind_sel = f1.radio("Show", list(kinds_), horizontal=True, key="nm_kind")
                pend_only = f2.checkbox("Not yet checked only", value=True, key="nm_pending")
                who_nm = f3.text_input("Your name (demo mode only)", key="nm_by")
                shown_ = [it for it in nm_["items"] if (kinds_[kind_sel] in (None, it["kind"])) and not (pend_only and it["decision"])][:10]
                labels_ = {"same": "Same", "different": "Different", "not_sure": "Not sure"}
                for it in shown_:
                    e_ = it["evidence"]
                    names_nm = " \u00b7 ".join(it["names"])
                    ev_txt = (f"{e_.get('tonnes_12m', 0):,} t in the last 12 months \u00b7 {e_.get('ships', 0)} ship(s) \u00b7 "
                              f"{e_.get('cargo', '') or 'cargo not stated'} \u00b7 {e_.get('months', '')}")
                    if e_.get("other"):
                        o_ = e_["other"]
                        ev_txt += f"<br>Other name: {o_.get('tonnes_12m', 0):,} t \u00b7 {o_.get('ships', 0)} ship(s) \u00b7 {o_.get('cargo', '')}"
                    st.markdown(f'<div class="ie-take" style="font-size:14px"><b>{html.escape(it["question"])}</b><br>'
                                f'Names: {html.escape(names_nm)}<br>{ev_txt}<br>'
                                f'<span style="color:#6B7585">Basis: {html.escape(it["basis"])}'
                                + (" (applied in the figures now)" if it["applied_now"] else "") + '</span>'
                                + (f'<br><b>Recorded:</b> {labels_[it["decision"]["choice"]]} by {html.escape(it["decision"]["by"])}'
                                   f' on {it["decision"]["at"][:10]}' + (" (applied)" if it["decision"].get("applied") else "")
                                   if it["decision"] else "") + '</div>', unsafe_allow_html=True)
                    d1, d2, d3 = st.columns([3, 3, 1])
                    ch_nm = d1.radio("Decision", list(labels_), format_func=labels_.get, horizontal=True, key=f"nm_c_{it['id']}",
                                     label_visibility="collapsed")
                    keep_nm = (d2.selectbox("Count under", it["names"], index=len(it["names"]) - 1, key=f"nm_k_{it['id']}",
                                            label_visibility="collapsed") if it["kind"] != "spelling" and ch_nm == "same" else "")
                    if d3.button("Save", key=f"nm_s_{it['id']}"):
                        try:
                            r_ = requests.post(f"{API}/incentive/customer-names/decide", headers=_auth_headers(), timeout=60,
                                               json={"item_id": it["id"], "choice": ch_nm, "keep_name": keep_nm, "by": who_nm})
                            if r_.ok:
                                st.rerun()
                            else:
                                st.error(r_.json().get("detail", r_.text) if r_.status_code != 403 else "Only Traffic can confirm customer names.")
                        except requests.RequestException as e_:
                            st.error(f"Could not reach the backend: {e_}")
                if not shown_:
                    st.success("Nothing left to check in this view.")
                a1, a2 = st.columns(2)
                if nm_.get("to_apply"):
                    if a1.button(f"Apply {nm_['to_apply']} confirmed decision(s) to the figures", key="nm_apply", type="primary"):
                        try:
                            r_ = requests.post(f"{API}/incentive/customer-names/apply", headers=_auth_headers(), timeout=120,
                                               json={"by": who_nm})
                            if r_.ok:
                                st.success(r_.json().get("message", "Applied."))
                                st.rerun()
                            else:
                                st.error("Only Traffic can apply customer name decisions." if r_.status_code == 403 else r_.text)
                        except requests.RequestException as e_:
                            st.error(f"Could not reach the backend: {e_}")
                else:
                    a1.caption("No confirmed change waiting to be applied.")
                csv_nm = pd.DataFrame([{"item": it["id"], "question": it["question"], "names": " | ".join(it["names"]),
                                        "tonnes_last_12_months": it["evidence"].get("tonnes_12m", 0), "basis": it["basis"],
                                        "decision (same / different / not sure)": "", "count under (name)": "", "checked by": ""}
                                       for it in nm_["items"]]).to_csv(index=False)
                a2.download_button("\u2913 Full list for NMPA to fill in (CSV)", csv_nm, file_name="customer_names_to_confirm.csv",
                                   mime="text/csv", key="nm_csv")

        with it3:
            _head("Discount calculator",
                  insight="Compare a discount on all cargo with a rebate on extra cargo only.",
                  sub="A blanket discount lowers the rate on every tonne, including cargo that would come anyway. A rebate on extra "
                      "volume pays the discount only on tonnes above an agreed baseline, so existing cargo keeps the full rate. The extra "
                      "tonnes are inputs you choose, not predictions: the tool does not guess how customers will react. Rate: the "
                      "cargo's average wharfage per tonne from NMPA's Scale of Rates (foreign/coastal and SPM/berth mix from NMPA's daily "
                      "reports). Baseline: this year's tonnes from NMPA's monthly statements, scaled to a year.")
            L_, R_ = st.columns([0.34, 0.66], gap="large")
            with L_:
                cargos_ = [c["cargo"] for c in rv["cargos"]]
                pick_i = st.selectbox("Cargo", cargos_, key="inc_cargo")
                disc = st.slider("Discount (%)", 1, 30, 10, key="inc_disc")
                won = next((o for o in (op or {}).get("cargos", []) if pick_i.lower().startswith(o["cargo"].lower().split(" ")[0])), None)
                low_pct = st.number_input("If customers bring this much more cargo (%)", 0.0, 100.0, 2.0, 0.5, key="inc_low",
                                          help="A what-if, not a prediction")
                with st.expander("Optional: costs and a target"):
                    cref_ = api_get("/incentive/cost-reference") or {}
                    if cref_.get("available"):
                        st.caption(cref_["plain"])
                        if st.button(f"Use NMPA's published average (\u20b9{cref_['suggested_rs_per_t']:.2f} per tonne)", key="inc_cost_ref"):
                            st.session_state["inc_cost"] = float(cref_["suggested_rs_per_t"])
                            st.rerun()
                    st.session_state.setdefault("inc_cost", 0.0)
                    cost_t = st.number_input("Extra port cost per extra tonne (\u20b9)", min_value=0.0, max_value=1000.0, step=1.0, key="inc_cost",
                                             help="Leave 0 if not known; results are then wharfage receipts, not profit")
                    fixed = st.number_input("Fixed cost of running the scheme (\u20b9)", 0.0, 1e10, 0.0, 100000.0, key="inc_fixed")
                    tgt = st.number_input("Target: extra tonnes a year", 0.0, 1e8, 0.0, 10000.0, key="inc_target",
                                          help="E.g. a volume Traffic has confirmed with the customer. "
                                               + (f"For reference, {won['cargo']} cargo not won at other ports: {won['tonnes_not_won']:,.0f} t "
                                                  f"in {op['period']}." if won else ""))
            sc = api_get("/incentive/scenario", {"cargo": pick_i, "discount_pct": disc, "cost_per_t": cost_t, "fixed_cost": fixed,
                                                  "low_response_pct": low_pct, **({"target_t": tgt} if tgt else {})})
            if sc:
                lakh = lambda t: f"{t / 1e5:,.2f} lakh t"
                with R_:
                    _hist = " \u00b7 ".join(f"{k}: {lakh(v)}" for k, v in sc.get("history_tonnes", {}).items())
                    st.markdown(f'<div class="ie-take" style="font-size:13.5px;margin-bottom:4px"><b>Baseline: {lakh(sc["baseline_tonnes_per_year"])} of '
                                f'{html.escape(pick_i)} a year</b>, the {html.escape(sc.get("baseline_basis", ""))}. '
                                f'<span style="color:#57534E">Earlier years: {_hist}.</span></div>', unsafe_allow_html=True)
                    st.markdown('<div class="ie-cards" style="grid-template-columns:repeat(2,minmax(0,1fr))">' + "".join(
                        f'<div class="ie-card {t}"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s_}</div></div>' for l, v, s_, t in [
                            ("Rate per tonne", f"\u20b9{sc['rate_rs_per_t']:.2f} \u2192 \u20b9{sc['discounted_rate_rs_per_t']:.2f}",
                             "today \u2192 with the discount", "info"),
                            ("Discount on all cargo: cost", cr(sc["blanket_given_up_on_baseline_rs"]),
                             f"a year, on {sc['baseline_tonnes_per_year'] / 1e6:.2f} MMT of existing cargo", "act"),
                            ("Discount on all cargo: break-even", "never" if sc["never_breaks_even"] else tn(sc["break_even_extra_tonnes_blanket"]),
                             ("" if sc["never_breaks_even"] else f"{sc['break_even_extra_pct_blanket']:.1f}% more cargo needed"), "watch"),
                            ("Rebate on extra cargo only: break-even", "never" if sc["never_breaks_even"] else
                             ("first extra tonne" if not sc["break_even_extra_tonnes_rebate"] else tn(sc["break_even_extra_tonnes_rebate"])),
                             "existing cargo keeps the full rate", "good")]) + "</div>", unsafe_allow_html=True)
                    r_, d_, q0_ = sc["rate_rs_per_t"], disc / 100, sc["baseline_tonnes_per_year"]
                    be_ = sc["break_even_extra_tonnes_blanket"] or 0
                    xmax = max(be_ * 1.4, (tgt or 0) * 1.2, q0_ * low_pct / 100 * 1.5, q0_ * 0.05)
                    xs = [xmax * k / 40 for k in range(41)]
                    m_ = r_ * (1 - d_) - cost_t
                    yb = [(m_ * x - r_ * d_ * q0_ - fixed) / 1e7 for x in xs]
                    yr = [(m_ * x - fixed) / 1e7 for x in xs]
                    _ff = go.Figure()
                    _ff.add_scatter(x=[x / 1e6 for x in xs], y=yr, name="Rebate on extra cargo only", line=dict(color="#0F766E", width=3))
                    _ff.add_scatter(x=[x / 1e6 for x in xs], y=yb, name="Discount on all cargo", line=dict(color="#B91C1C", width=3))
                    _ff.add_hline(y=0, line=dict(color="#78716C", width=1))
                    if be_ and not sc["never_breaks_even"]:
                        _ff.add_vline(x=be_ / 1e6, line=dict(color="#B91C1C", width=1, dash="dot"),
                                      annotation_text=f"break-even {be_ / 1e6:.2f} MMT", annotation_position="top left")
                    if tgt:
                        _ff.add_vline(x=tgt / 1e6, line=dict(color="#1D4E89", width=1, dash="dash"), annotation_text="your target",
                                      annotation_position="bottom right")
                    _ff.update_layout(height=330, xaxis_title="Extra cargo a year (million tonnes)",
                                      yaxis_title="Change in wharfage a year (\u20b9 crore)", hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white", font=dict(size=12, color="#44403C"), margin=dict(l=10, r=20, t=56, b=30), legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
                    st.plotly_chart(_ff, **_W_CHART, config={"displayModeBar": False}, key="ie_chart_calc")
                    st.markdown(f'<div class="ie-take" style="font-size:13.5px">Above the line the port gains; below it the port loses. '
                                f'{html.escape(sc["measure"])}.</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="ti-h" style="margin:18px 0 2px 0;font-size:16px">What if…? Real situations, side by side</div>'
                            f'<div class="ie-take" style="font-size:13.5px">Each row is one situation. The last two money columns show how '
                            f'NMPA\'s yearly wharfage from {html.escape(pick_i)} would change, compared with today, with a {disc}% discount given '
                            f'either on all cargo or only on extra cargo. Minus means NMPA earns less.</div>', unsafe_allow_html=True)

                _htable(pd.DataFrame([{
                    "What if…": r["scenario"], "Extra cargo a year (t)": r["extra_tonnes"], "Where the figure comes from": r["source"],
                    "Discount on all cargo: NMPA's yearly wharfage changes by": cr(r["blanket_change_rs"]),
                    "Rebate on extra cargo only: changes by": cr(r["rebate_change_rs"])}
                    for r in sc["scenarios"]]))
                st.markdown(f'<div class="ie-take" style="font-size:13.5px">In every row, the rebate on extra cargo is '
                            f'<b>{cr(sc["blanket_given_up_on_baseline_rs"])} a year better</b> for NMPA: that is the discount a cut for all '
                            f'cargo gives away on the {sc["baseline_tonnes_per_year"] / 1e5:,.2f} lakh t that come anyway. A discount on all '
                            f'cargo only pays off above the break-even row.</div>', unsafe_allow_html=True)
                gc_ = api_get("/incentive/growth-check", {"cargo": pick_i, "discount_pct": disc}) or {}
                if gc_.get("available"):
                    tone_gc = "act" if gc_["share_pct"] < 20 else "watch" if gc_["share_pct"] < 50 else "good"
                    st.markdown('<div class="ie-cards" style="grid-template-columns:repeat(3,minmax(0,1fr))">' + "".join(
                        f'<div class="ie-card {t}"><div class="l">{l}</div><div class="v">{v}</div><div class="s">{s_}</div></div>' for l, v, s_, t in [
                            ("Growth needed to break even", f"{gc_['need_pct']:.1f}% a year", f"a {disc}% discount on all {pick_i}", "info"),
                            ("How often NMPA's cargo grew that much", f"{gc_['hits']} of {gc_['periods']}",
                             f"twelve-month periods ({gc_['share_pct']:.0f}%), without this discount", tone_gc),
                            ("Usual yearly change", f"{gc_['typical_low_pct']:+.0f}% to {gc_['typical_high_pct']:+.0f}%",
                             f"latest: {gc_['latest_pct']:+.1f}% ({gc_['latest_period']})", "info")]) + "</div>", unsafe_allow_html=True)
                    st.markdown(f'<div class="ie-take" style="font-size:13.5px">{html.escape(gc_["reading"])}</div>', unsafe_allow_html=True)
                    _note_md(gc_["method"])
                # Is there room at this cargo's berths for the extra cargo the discount needs?
                bc_ = api_get("/incentive/berth-check", {"cargo": pick_i, "extra_pct": round(disc / (100 - disc) * 100, 1)}) or {}
                if bc_.get("available"):
                    tone_bc = {"Room": "good", "Some room": "watch", "Busy": "act"}  # stricter of days-with-a-ship and NMPA capacity
                    st.markdown(f"**Is there room at the berths?** {bc_['verdict']} \u00b7 last 12 months, {bc_['months']}")
                    st.markdown('<div class="ie-cards" style="grid-template-columns:repeat(3,minmax(0,1fr))">' + "".join(
                        f'<div class="ie-card {tone_bc[r["verdict_after"]]}"><div class="l">Berth {html.escape(r["berth"])} '
                        f'({r["cargo_share_pct"]}% {html.escape(pick_i)})</div><div class="v">{r["busy_now_pct"]:.0f}% \u2192 {r["busy_after_pct"]:.0f}%</div>'
                        f'<div class="s">days with a ship, now \u2192 with the extra cargo \u00b7 busiest {r["peak_pct"]:.0f}% ({r["peak_month"]})'
                        + (f'<br>NMPA usable capacity: {r["capacity_used_pct"]:.0f}% \u2192 {r["capacity_used_after_pct"]:.0f}% used' if r.get("capacity_used_pct") is not None else "")
                        + f' \u00b7 <b>{r["verdict_after"]}</b></div></div>'
                        for r in bc_["rows"][:3]) + "</div>", unsafe_allow_html=True)
                    st.markdown(f'<div class="ie-take" style="font-size:13.5px">{html.escape(bc_["plain"])} Where a berth is nearly full in its '
                                f'busiest month, a discount works best in the quiet months.</div>', unsafe_allow_html=True)
                    _bb = [r for r in bc_["rows"][:4] if r.get("capacity_used_pct") is not None]
                    if _bb:
                        _fbb = go.Figure(); n_ = len(_bb); top_ = max(130, max(r["capacity_used_after_pct"] for r in _bb) * 1.1)
                        for k_, r in enumerate(_bb):
                            _fbb.add_trace(go.Indicator(mode="number+gauge+delta", value=r["capacity_used_after_pct"],
                                number=dict(suffix="%", font=dict(size=20)), delta=dict(reference=r["capacity_used_pct"], suffix=" pts",
                                increasing=dict(color=_RED), decreasing=dict(color=_GREEN)),
                                title=dict(text=f'Berth {r["berth"]}', font=dict(size=13)),
                                domain=dict(x=[0.12, 1], y=[1 - (k_ + 1) / n_ + 0.04, 1 - k_ / n_ - 0.04]),
                                gauge=dict(shape="bullet", axis=dict(range=[0, top_]), bar=dict(color=_NAVY, thickness=0.45),
                                           steps=[dict(range=[0, 80], color="#E7F3EF"), dict(range=[80, 100], color="#FDF0DD"),
                                                  dict(range=[100, top_], color="#F8E1E1")],
                                           threshold=dict(line=dict(color=_RED, width=3), thickness=0.9, value=100))))
                        _fbb.update_layout(height=70 + 70 * n_, margin=dict(l=10, r=30, t=10, b=10), paper_bgcolor="white")
                        st.markdown("**NMPA usable capacity used, with the extra cargo** (bar; red line = 100% of NMPA's usable capacity; "
                                    "the change is against today)")
                        _ie_show(_fbb, "ie_chart_berth_bullets")
                    _note_md(bc_["method"])
                # Compare scheme designs side by side (the officer chooses; nothing is decided here)
                st.markdown("**Compare scheme designs** for this cargo and discount")
                xp_ = st.slider("Extra cargo expected (% of the last 12 months)", 0, 30, 5, 1, key="cmp_extra",
                                help="One assumption for all designs. Try a few values: the order of the designs can change.")
                cd_ = api_get("/incentive/compare-designs", {"cargo": pick_i, "discount_pct": disc, "extra_pct": xp_}) or {}
                if cd_.get("rows"):
                    _fcd = go.Figure()
                    _fcd.add_bar(x=[x["design"] for x in cd_["rows"]], y=[x["cost_rs"] / 1e7 for x in cd_["rows"]], name="Cost to NMPA in a year",
                                 marker_color=_RED)
                    _fcd.add_bar(x=[x["design"] for x in cd_["rows"]], y=[x["net_rs"] / 1e7 for x in cd_["rows"]], name="Net for NMPA in a year",
                                 marker_color=[_GREEN if x["net_rs"] >= 0 else _AMBER for x in cd_["rows"]],
                                 text=[f'{x["net_rs"] / 1e7:+.2f} cr' for x in cd_["rows"]], textposition="outside", cliponaxis=False)
                    _ie_fig(_fcd, 360, ytitle="\u20b9 crore (estimates)"); _fcd.update_layout(barmode="group")
                    _ie_show(_fcd, "ie_chart_compare_designs")
                    _htable(pd.DataFrame([{"Design": x["design"], "Cost to NMPA in a year": cr(x["cost_rs"]),
                                           "Net for NMPA in a year": cr(x["net_rs"]), "Pays for itself": x["pays_when"],
                                           "Customers must": x["customers_must"], "Main risk": x["main_risk"]} for x in cd_["rows"]]))
                    st.caption(f"Extra cargo assumed: {cd_['extra_t']:,} t a year. " + cd_["note"])
                with st.expander("What research and other Indian ports show about discounts"):
                    st.markdown(
                        "- **Port charges are a small part of a shipper's total cost**, so overall demand for port services reacts little to "
                        "price; but one port can still win or lose cargo when a nearby port is a close substitute "
                        "([Port Economics, Management and Policy: port pricing](https://porteconomicsmanagement.org/port-pricing/); "
                        "[a review of port pricing studies](https://core.ac.uk/download/276636267.pdf)). This is why the tool asks first *why* "
                        "a customer moved: a discount helps only when price is the reason.\n"
                        "- **Coastal cargo already gets a national 40% concession** at Major Ports on vessel- and cargo-related charges, except "
                        "thermal coal and POL including crude ([DG Shipping coastal shipping committee report, Jan 2026]"
                        "(https://dgma.gov.in/download/1769691524_697b598415456_coastal-committee-report-final-jan2026.pdf)). NMPA's Scale of "
                        "Rates applies it: coastal rates are about 60% of foreign rates, and crude and POL have the same rate for both.\n"
                        "- **Mormugao** introduced *Harit Shrey* green-ship discounts in October 2023, the first major port to do so "
                        "([Ministry of Ports Annual Report 2024-25](https://shipmin.gov.in/sites/default/files/Annual%20Report%202024-25%20-%20English.pdf)); "
                        "NMPA followed in January 2025 for a trial period.\n"
                        "- **Deendayal (Kandla)** handled about 8.5 million tonnes more salt in 2024-25 after concessions based on ship parcel "
                        "size, a targeted scheme rather than a cut for everyone ([press report, India Seatrade News]"
                        "(https://indiaseatradenews.com/paradip-port-authority-retains-the-top-slot-in-cargo-handling-among-major-ports-in-fy25-by-a-whisker/)).\n"
                        "- **Cochin** designs its schemes with tiers, fixed periods, minimum service frequency and a review after three months "
                        "(see *Customers & cargo*, Cochin examples). NMPA's own schemes follow the same pattern: incremental volume, new cargo, "
                        "green cargo, and named vessel types.")
                with st.expander("Formulas and conditions for a rebate scheme"):
                    st.markdown(f"- Blanket discount: `{sc['formulas']['blanket']}`\n- Rebate on extra volume: `{sc['formulas']['rebate']}`\n"
                                "- r = wharfage per tonne today, d = discount, c = extra cost per tonne, F = fixed cost.")
                    st.markdown("\n".join(f"- {x}" for x in sc["conditions"]))

            # 3-dd. Deal desk: a draft proposal for one customer
            _head("Customer proposal (deal desk)",
                  sub="A draft for internal discussion, not an offer: the customer's evidence, a stated baseline, four options with "
                      "their arithmetic, the eligibility check, the data gaps and the approval route, as a one-page PDF.")
            cust_opts = [c["customer"] for c in (cwf or {}).get("customers", [])] if cwf else []
            if cust_opts:
                q1, q2 = st.columns(2)
                dd_c = q1.selectbox("Customer", cust_opts, key="dd_cust")
                dd_cargos = (api_get("/incentive/proposal/cargos", {"customer": dd_c}) or {}).get("cargos", [])
                dd_g = q2.selectbox("Cargo", [c["cargo"] for c in dd_cargos] or ["(none priced)"], key="dd_cargo")
                q3, q4, q5 = st.columns(3)
                dd_s = q3.date_input("Start", value=pd.Timestamp("2026-12-01").date(), key="dd_start")
                dd_e = q4.date_input("End", value=pd.Timestamp("2027-02-28").date(), key="dd_end")
                dd_bm = q5.selectbox("Baseline", ["same_months_last_year", "recent_run_rate", "contractual"], key="dd_bm",
                                     format_func={"same_months_last_year": "Same months last year", "recent_run_rate": "Recent run-rate",
                                                  "contractual": "Contractual commitment"}.get)
                q6, q7, q8, q9 = st.columns(4)
                dd_d = q6.number_input("Blanket discount %", 0.0, 50.0, 10.0, 1.0, key="dd_disc")
                dd_t1u = q7.number_input("Slab 1: up to % above baseline", 1.0, 100.0, 10.0, 1.0, key="dd_t1u")
                dd_t1 = q8.number_input("Slab 1 rebate %", 0.0, 50.0, 5.0, 0.5, key="dd_t1")
                dd_t2 = q9.number_input("Beyond slab 1: rebate %", 0.0, 50.0, 10.0, 0.5, key="dd_t2")
                q10, q11, q12, q13 = st.columns(4)
                dd_low = q10.number_input("Low response: extra %", 0.0, 100.0, 5.0, 1.0, key="dd_low")
                dd_tgt = q11.number_input("Commercial target: extra t", 0.0, 1e8, 0.0, 10000.0, key="dd_tgt")
                dd_cap = q12.number_input("Budget cap (\u20b9)", 0.0, 1e10, 0.0, 100000.0, key="dd_cap")
                dd_ct = q13.number_input("Committed t (contractual)", 0.0, 1e8, 0.0, 10000.0, key="dd_ct", disabled=dd_bm != "contractual")
                dd_params = {"customer": dd_c, "cargo": "" if dd_g.startswith("(") else dd_g, "start": dd_s.isoformat(), "end": dd_e.isoformat(),
                             "discount_pct": dd_d, "low_response_pct": dd_low, "target_extra_t": dd_tgt, "budget_cap_rs": dd_cap,
                             "baseline_method": dd_bm, "contractual_t": dd_ct, "tier1_upto": dd_t1u, "tier1_pct": dd_t1, "tier2_pct": dd_t2}
                dd = api_get("/incentive/proposal", dd_params, timeout=60)
                if dd:
                    ev, bl_ = dd["evidence"], dd["baseline"]
                    st.markdown(f'<div class="ti-insight"><b>{html.escape(_ie_txt(dd["status"]))}.</b> ' + (
                        f'{html.escape(dd["customer"])}: {html.escape(str(ev["trend"]))}'
                        + (f' ({ev["change_pct"]:+.0f}% on the previous 3 months)' if ev.get("change_pct") is not None else "")
                        + f'; {ev["not_ready_ship_days"] or 0:.0f} ship-days waiting because the customer was not ready. '
                        + (f'Baseline {bl_["tonnes"]:,} t ({html.escape(bl_["label"])}).' if bl_.get("tonnes") is not None
                           else f'Baseline cannot be set: {html.escape(str(bl_.get("blocked")))}')) + "</div>", unsafe_allow_html=True)
                    _hlist(pd.DataFrame([{"Option": o["option"], "Tariff change": o["tariff_change"],
                                                "Cost over the period": cr(o["cost_rs"]) if o.get("cost_rs") else "\u2014", "Notes": o["notes"]}
                                               for o in dd["options"]]), hide_index=True, width="stretch",
                                 column_config={"Notes": st.column_config.TextColumn(width="large")})
                    if dd["scenarios"]:
                        _hlist(pd.DataFrame([{"Scenario": x["scenario"], "Extra t": x["extra_tonnes"], "Extra wharfage": cr(x["extra_wharfage_rs"]),
                                                    "Rebate (slabs)": cr(x["rebate_rs"]) + (" (capped)" if x["rebate_capped"] else ""),
                                                    "Rebate option: net": cr(x["rebate_net_rs"]), "Blanket option: net": cr(x["blanket_net_rs"])}
                                                   for x in dd["scenarios"]]), hide_index=True, width="stretch",
                                     column_config={"Extra t": st.column_config.NumberColumn(format="localized")})
                    if dd["eligibility"]["blocks"]:
                        st.markdown('<div class="ti-insight"><b>Blocked:</b> ' + " | ".join(html.escape(_ie_txt(b)) for b in dd["eligibility"]["blocks"])
                                    + "</div>", unsafe_allow_html=True)
                    ig_ = dd.get("integrity") or {}
                    if ig_.get("checks"):
                        st.markdown(f'<div class="ti-insight"><b>Checks for gaming:</b> {html.escape(ig_["summary"])}</div>',
                                    unsafe_allow_html=True)
                        with st.expander("See each gaming check (a warning is a reason to look, not proof)"):
                            _hlist(pd.DataFrame([{"Check": c["check"], "Result": c["status"], "What we found": c["plain"]}
                                                  for c in ig_["checks"]]), hide_index=True, width="stretch",
                                    column_config={"What we found": st.column_config.TextColumn(width="large")})
                    _note_md('<div class="ti-s"><b>Data gaps:</b> ' + " ".join(html.escape(g) for g in dd["data_gaps"])
                                + "<br><b>Approval route:</b> " + " \u2192 ".join(html.escape(a) for a in dd["approval_route"]) + "</div>",
                                unsafe_allow_html=True)
                    if dd["baseline"].get("tonnes") and dd["scenarios"]:
                        with st.expander("Save this proposal as a draft scheme (goes to the scheme register for review)"):
                            s1_, s2_, s3_ = st.columns([0.4, 0.3, 0.3])
                            dd_opt = s1_.radio("Option to put forward", ["Rebate on extra volume", "Blanket discount"], key="dd_opt")
                            dd_by = s2_.text_input("Your name or team", key="dd_by")
                            dd_cond = s3_.text_input("Conditions", key="dd_cond", placeholder="e.g. settlement quarterly")
                            c1_, c2_ = st.columns(2)
                            dd_commit = c1_.number_input("Tonnes the customer commits to over the period (0 = none)", min_value=0.0,
                                                         value=0.0, step=1000.0, key="dd_commit")
                            dd_claw = c2_.selectbox("If the commitment is missed", ["proportional", "all_or_nothing"], key="dd_claw",
                                                    format_func=lambda x: {"proportional": "Reduce the rebate in proportion",
                                                                           "all_or_nothing": "No rebate at all"}[x])
                            if st.button("Save as draft scheme", key="dd_save", type="primary"):
                                tiers_dd = [{"up_to_pct_above_baseline": dd_t1u, "rebate_pct": dd_t1}, {"up_to_pct_above_baseline": None, "rebate_pct": dd_t2}]
                                try:
                                    r_ = requests.post(headers=_auth_headers(), url=f"{API}/incentive/schemes", timeout=30, json={
                                        "cargo": dd["cargo"], "scope": dd_opt, "discount_pct": dd_d if dd_opt == "Blanket discount" else dd_t2,
                                        "start": dd_s.isoformat(), "end": dd_e.isoformat(), "budget_cap_rs": dd_cap, "customers": "",
                                        "conditions": dd_cond, "by": dd_by, "tiers": tiers_dd if dd_opt != "Blanket discount" else None,
                                        "success_target_t": dd_tgt or None, "customer": dd["customer"],
                                        "baseline_tonnes": dd["baseline"]["tonnes"], "baseline_label": dd["baseline"]["label"],
                                        "baseline_detail": dd["baseline"].get("detail", ""),
                                        "commitment_t": dd_commit or None, "clawback_rule": dd_claw})
                                    if r_.ok:
                                        st.success(f"Saved as {r_.json()['id']} (draft). Find it in the scheme register below.")
                                    else:
                                        st.error(r_.json().get("detail", "Could not save."))
                                except requests.RequestException:
                                    st.error("Could not save. Is the backend running?")
                    try:
                        pdf_ = requests.get(f"{API}/incentive/proposal.pdf", params=dd_params, timeout=60)
                        if pdf_.ok:
                            st.download_button("Download the draft proposal (PDF)", pdf_.content,
                                               file_name=f"NMPA_draft_proposal_{dd_c.replace(' ', '_')[:30]}.pdf", mime="application/pdf",
                                               key="dd_pdf")
                    except requests.RequestException:
                        pass
                _src("NMPA daily vessel reports (customer tonnes, waiting); NMPA Scale of Rates; customer notes from Trade Intelligence")

            # 3b. Ship charges: what a ship pays NMPA, and what NMPA's ship-charge rebates cost
            _head("Ship charges: what a ship pays to enter and use the port",
                  insight="Most port discounts, including NMPA's container (35% / 50%) and Cape-size (30%) rebates, are on ship "
                          "charges, not on the cargo charge. Work out one ship's bill here.",
                  sub="Port dues (entry fee), pilotage (pilot and tugs, one move in and one out) and berth hire (rent per hour), "
                      "from NMPA's Scale of Rates in force from 7 May 2026. A foreign-going ship's charges are in US dollars and "
                      "converted at the RBI reference rate on the day it enters.")
            v1_, v2_, v3_, v4_, v5_ = st.columns(5)
            vg_ = v1_.number_input("Ship size (GRT)", min_value=100.0, value=30000.0, step=1000.0, key="vc_grt")
            vco_ = v2_.radio("Voyage", ["Foreign-going", "Coastal"], key="vc_run") == "Coastal"
            vk_ = v3_.radio("Ship type", ["dry", "liquid"], key="vc_kind",
                            format_func=lambda x: {"dry": "Dry / container / general", "liquid": "Tanker / liquid"}[x])
            vh_ = v4_.number_input("Hours at berth", min_value=1.0, value=36.0, step=1.0, key="vc_hours")
            vfx_ = v5_.number_input("USD to INR", min_value=1.0, value=88.0, step=0.1, key="vc_fx", disabled=vco_)
            vcall_ = api_get("/incentive/vessel-charges/call", {"grt": vg_, "coastal": vco_, "kind": vk_, "hours": vh_,
                                                                "usd_inr": None if vco_ else vfx_})
            if vcall_:
                st.markdown(f'<div class="ti-insight">{html.escape(vcall_["plain"])}</div>', unsafe_allow_html=True)
                _fv = go.Figure()
                for k_, nm_, col_ in (("port_dues_rs", "Port dues", _NAVY), ("pilotage_rs", "Pilotage", _AMBER), ("berth_hire_rs", "Berth hire", _GREEN)):
                    _fv.add_bar(y=["This ship"], x=[(vcall_.get(k_) or 0) / 1e5], orientation="h", name=nm_, marker_color=col_,
                                text=[f"{nm_}: \u20b9{(vcall_.get(k_) or 0) / 1e5:,.1f} lakh"], textposition="inside", insidetextanchor="middle",
                                textfont=dict(color="white"))
                _ie_fig(_fv, 170, xtitle=f"\u20b9 lakh (total \u20b9{(vcall_.get('total_rs') or 0) / 1e5:,.1f} lakh)")
                _fv.update_layout(barmode="stack", legend=dict(traceorder="normal", orientation="h", yanchor="bottom", y=1.02, x=0))
                _fv.update_yaxes(showticklabels=False)
                _ie_show(_fv, "ie_chart_ship_charges")
            vs_ = api_get("/incentive/vessel-charges", {"usd_inr": vfx_}, timeout=90)
            if vs_:
                with st.expander("NMPA's own ship-charge rebates: what they cost"):
                    for k_ in ("container_rebate", "capesize_rebate"):
                        st.markdown(f'<div class="ti-insight"><b>{html.escape(vs_[k_]["notice"])}</b>: {html.escape(vs_[k_]["plain"])}</div>',
                                    unsafe_allow_html=True)
                    inp_ = vs_["inputs"]
                    st.markdown(f'<div class="ti-s">Ship sizes held: {inp_["ships_with_official_grt"]} from NMPA records, '
                                f'{inp_["ships_with_public_grt"]} from a public register. To complete: '
                                + " ".join(html.escape(h) for h in vs_["how_to_complete"]) + "</div>", unsafe_allow_html=True)
            _src("NMPA Scale of Rates (Chapter II, vessel related charges); NMPA daily vessel reports (calls, hours at berth); "
                 "NMPA trade notices")

            # 3c. Gaming checks for any customer and cargo
            with st.expander("Check a customer for gaming before offering a discount"):
                g1_, g2_, g3_, g4_ = st.columns([0.3, 0.25, 0.22, 0.23])
                gk_ = api_get("/incentive/key-customers", timeout=60) or {}
                gcs_ = [c_["customer"] for c_ in gk_.get("customers", [])] or ["MRPL"]
                gc_ = g1_.selectbox("Customer", gcs_, key="ig_c")
                gcar_ = [x["cargo"] for x in (api_get("/incentive/proposal/cargos", {"customer": gc_}) or {}).get("cargos", [])]
                gca_ = g2_.selectbox("Cargo", gcar_ or ["(no priced cargo)"], key="ig_cargo")
                gs_ = g3_.date_input("From", value=pd.Timestamp("2026-05-01"), key="ig_s")
                ge_ = g4_.date_input("To", value=pd.Timestamp("2026-10-31"), key="ig_e")
                if gcar_:
                    igr_ = api_get("/incentive/integrity", {"cargo": gca_, "start": gs_.isoformat(), "end": ge_.isoformat(),
                                                            "customer": gc_}, timeout=90)
                    if igr_:
                        st.markdown(f'<div class="ti-insight">{html.escape(igr_["summary"])}</div>', unsafe_allow_html=True)
                        _hlist(pd.DataFrame([{"Check": c["check"], "Result": c["status"], "What we found": c["plain"]}
                                              for c in igr_["checks"]]), hide_index=True, width="stretch",
                                column_config={"What we found": st.column_config.TextColumn(width="large")})
                        _src(igr_["source"] + ". " + igr_["note"])

            # 3x. Performance condition from ship data: pay only when the customer is ready
            rc0 = api_get("/incentive/readiness-condition") or {}
            if rc0.get("available"):
                _head("Pay only when the customer is ready",
                      insight=(f"{rc0['qualifying_pct']:.0f}% of ship calls ({rc0['qualifying_calls']} of {rc0['calls']}, "
                               f"{rc0['window']}) had no waiting because the customer was not ready. "
                               "A rebate tied to this condition rewards customers who are ready when their ship arrives, "
                               "and pays nothing on calls where berth time was lost on the customer side."),
                      sub=rc0["how"] + " Learned from ports that tie rebates to performance, such as Singapore's limit on port stay.")
                r1, r2, r3 = st.columns(3)
                cust_rc = r1.selectbox("Customer", ["All customers"] + rc0["customers"], key="rc_customer")
                win_rc = r2.selectbox("Period", [3, 6, 12], index=1, format_func=lambda m: f"Last {m} complete months", key="rc_months")
                mw_rc = r3.number_input("Allowed customer-side waiting (days)", min_value=0.0, max_value=10.0, value=0.0, step=0.5, key="rc_wait",
                                        help="A call still qualifies if the ship waited up to this many days because the customer was not ready.")
                rc_ = api_get("/incentive/readiness-condition", params={
                    "customer": "" if cust_rc == "All customers" else cust_rc, "months": win_rc, "max_wait_days": mw_rc}) or {}
                if rc_.get("available"):
                    _cards([
                        ("Calls that would qualify", f"{rc_['qualifying_calls']} of {rc_['calls']}", f"{rc_['qualifying_pct']:.0f}% of calls \u00b7 {rc_['window']}", "good"),
                        ("Tonnes on qualifying calls", f"{rc_['qualifying_tonnes_pct'] or 0:.0f}%", f"{rc_['qualifying_tonnes']:,} t of {rc_['tonnes']:,} t (containers excluded)", "info"),
                        ("Ship-days lost, customer not ready", f"{rc_['ship_days_lost']:,.0f}", "the waiting this condition targets", "watch" if rc_["ship_days_lost"] else "good")])
                    if cust_rc == "All customers":
                        _bc = sorted(rc_["by_customer"], key=lambda b_: -b_["calls"])[:12]
                        if _bc:
                            _frc = go.Figure(go.Bar(y=[b_["customer"] for b_ in _bc], x=[b_["qualifying_pct"] for b_ in _bc], orientation="h",
                                                    marker_color=[_GREEN if b_["qualifying_pct"] >= 85 else _AMBER if b_["qualifying_pct"] >= 70 else _RED for b_ in _bc],
                                                    text=[f'{b_["qualifying_pct"]:.0f}% \u00b7 {b_["ship_days_lost"]:.0f} ship-days lost' for b_ in _bc],
                                                    textposition="outside", cliponaxis=False))
                            _ie_fig(_frc, 80 + 32 * len(_bc), xtitle="Calls where the customer was ready (%), largest customers", legend=False)
                            _frc.update_xaxes(range=[0, 125]); _frc.update_yaxes(autorange="reversed")
                            _ie_show(_frc, "ie_chart_readiness")
                        _htable(pd.DataFrame([{"Customer": b_["customer"], "Ship calls": int(b_["calls"]),
                                               "Would qualify": f"{int(b_['qualifying'])} ({b_['qualifying_pct']:.0f}%)",
                                               "Ship-days lost, not ready": b_["ship_days_lost"]} for b_ in rc_["by_customer"]]))
                    if rc_["calls_failing"]:
                        with st.expander("Calls that would not qualify"):
                            _hlist(pd.DataFrame([{"Vessel": c_["vessel"], "Customer": c_["customer"], "Month": c_["month"],
                                                   "Cargo": c_["cargo"], "Days waited, customer not ready": c_["not_ready_days"]}
                                                  for c_ in rc_["calls_failing"]]))
                else:
                    st.info(rc_.get("reason") or "No ship calls for this choice.")
                _src(rc0["source"])

            # Shared budget pool (Incheon model): a fixed amount shared among customers by their extra cargo
            _head("Share a fixed budget by extra cargo",
                  insight=("The Board fixes one amount; customers who grow share it in proportion to their extra tonnes. "
                           "The total paid can never exceed the amount approved, and what is not earned stays with NMPA."),
                  sub="Modelled on Incheon Port's incentive programmes, where each programme has a fixed budget shared by volume.")
            p1, p2, p3 = st.columns(3)
            cargo_pl = p1.selectbox("Cargo", cargos_, index=cargos_.index(pick_i) if pick_i in cargos_ else 0, key="pool_cargo")
            amt_pl = p2.number_input("Budget (\u20b9 crore)", min_value=0.1, max_value=100.0, value=2.0, step=0.5, key="pool_amt")
            cap_pl = p3.slider("Most per extra tonne (% of wharfage)", 10, 100, 50, 5, key="pool_cap",
                               help="No customer is paid more than this share of the wharfage rate for each extra tonne.")
            pl_ = api_get("/incentive/pool-simulation", {"cargo": cargo_pl, "pool_crore": amt_pl, "cap_pct": cap_pl}) or {}
            if pl_.get("available"):
                _cards([
                    ("Budget approved", cr(pl_["pool_rs"]), "the most NMPA can pay", "info"),
                    ("Would have been paid", cr(pl_["paid_rs"]), f"{pl_['customers_rewarded']} customer(s) that grew", "good"),
                    ("Stays with NMPA", cr(pl_["unspent_rs"]), "not earned by extra cargo", "info")])
                st.markdown(f"**If this pool had run in {pl_['period']}** (against {pl_['compared_with']}): extra {cargo_pl} "
                            f"{pl_['extra_total_t']:,} t; {pl_['customers_falling']} customer(s) handled less and get nothing.")
                rows_pl = [r for r in pl_["rows"] if r["extra_t"] > 0]
                if rows_pl:
                    _fpl = go.Figure(go.Bar(y=[r["customer"] for r in rows_pl], x=[r["pay_rs"] / 1e5 for r in rows_pl], orientation="h",
                                            marker_color=[_AMBER if r["capped"] else _NAVY for r in rows_pl],
                                            text=[f'{r["pay_rs"] / 1e5:,.1f} lakh' for r in rows_pl], textposition="outside", cliponaxis=False))
                    _ie_fig(_fpl, 80 + 34 * len(rows_pl), xtitle="Would receive (\u20b9 lakh; amber = at the per-tonne limit)", legend=False)
                    _fpl.update_yaxes(autorange="reversed")
                    _ie_show(_fpl, "ie_chart_pool")
                    _htable(pd.DataFrame([{"Customer": r["customer"], "A year earlier (t)": f"{r['prev_t']:,}", "This period (t)": f"{r['cur_t']:,}",
                                           "Extra (t)": f"{r['extra_t']:,}", "Share of extra": f"{r['share_pct']:.1f}%",
                                           "Would receive": cr(r["pay_rs"]), "Per extra tonne": f"\u20b9{r['pay_per_extra_t_rs']:,.2f}",
                                           "Note": "At the per-tonne limit" if r["capped"] else "\u2014"} for r in rows_pl]))
                st.caption("Customer names are as written in NMPA's daily reports; joint or variant entries (e.g. two companies on one "
                           "line) count separately until NMPA confirms the names. Two months only can be compared with a year earlier "
                           "so far, so this is an illustration; the same rule applies to any period.")
                _note_md(pl_["method"])
            else:
                st.info(pl_.get("reason") or "Not available for this cargo.")

            # 3a. Rules: tariff versions, who controls each charge, combination rule
            rl = api_get("/incentive/rules")
            if rl:
                with st.expander("Rules applied to every proposal: tariff version, who controls each charge, combining benefits"):
                    _hlist(pd.DataFrame([{"Tariff version": v["name"], "From": _d(v["from"]), "To": _d(v["to"]),
                                                "Original held": "Yes" if v["held"] else "No: proposals in these dates are blocked",
                                                "Note": v["note"]} for v in rl["tariff_versions"]]), hide_index=True, width="stretch")
                    _hlist(pd.DataFrame([{"Charge": k, "NMPA can offer a benefit": {True: "Yes", False: "No", None: "Finance to confirm"}[v["nmpa_controls"]],
                                                "Basis": v["basis"]} for k, v in rl["charge_control"].items()]), hide_index=True, width="stretch",
                                 column_config={"Basis": st.column_config.TextColumn(width="large")})
                    _note_md(f'<div class="ti-s"><b>Combining benefits:</b> {html.escape(rl["combination_rule"])} Benefits already granted: '
                                + "; ".join(f'{html.escape(b["name"])}, {_d(b["from"])} to {_d(b["to"])}' for b in rl["known_benefits"]) + ".</div>",
                                unsafe_allow_html=True)

            _flush_notes()
        with it4:
            # Schemes ending soon, with a review pack
            ex_ = api_get("/incentive/expiring") or {}
            due_ = [r for r in ex_.get("rows", []) if r["band"] != "Running"]
            if ex_.get("available") and ex_.get("rows"):
                _head("Schemes ending soon: review before they lapse",
                      insight=((f"{len(due_)} scheme(s) end within {ex_['thresholds']['plan_review_days']} days. " if due_ else
                                "No scheme ends within six months. ") +
                               "Each comes with how it is doing against the other major ports, its cost where it can be priced, "
                               "and a renew / change / stop recommendation."),
                      sub=(f"'Review now' = ends within {ex_['thresholds']['review_now_days']} days; 'Plan the review' = within "
                           f"{ex_['thresholds']['plan_review_days']} days. The recommendation follows the evidence: a broad check of a "
                           "whole cargo group never gives a firm stop, and a relief measure is judged on the disruption, not on extra cargo."))
                _xr = sorted(ex_["rows"], key=lambda r: r["days_left"])
                _bcol = {"Review now": _RED, "Plan the review": _AMBER, "Running": _GREEN}
                _fx = go.Figure(go.Bar(y=[f'{_short(r["what"], 30)} \u00b7 {_short(r["cargo"], 18)}' for r in _xr], x=[r["days_left"] for r in _xr],
                                       orientation="h", marker_color=[_bcol.get(r["band"], _GREY) for r in _xr],
                                       text=[f'{r["days_left"]} days \u00b7 {r["band"].lower()}' for r in _xr], textposition="outside", cliponaxis=False))
                _fx.add_vline(x=ex_["thresholds"]["plan_review_days"], line_dash="dot", line_color=_AMBER)
                _ie_fig(_fx, 90 + 40 * len(_xr), xtitle="Days until the scheme ends", legend=False); _fx.update_yaxes(autorange="reversed")
                _fx.update_xaxes(range=[0, max(r["days_left"] for r in _xr) * 1.35])
                _ie_show(_fx, "ie_chart_expiring")
                for r in ex_["rows"]:
                    if r["band"] == "Running":
                        continue
                    with st.expander(f"{r['band']}: {r['notice']} \u00b7 ends {pd.Timestamp(r['ends']):%d %b %Y} ({r['days_left']} days)",
                                     expanded=r["band"] == "Review now"):
                        st.markdown(f"**What it is:** {r['what']} ({r['cargo']})")
                        st.markdown(f"**How it is doing:** {r['result']}" + (f". {r['evidence']}" if r.get("evidence") else ""))
                        if r.get("cost"):
                            st.markdown(f"**Cost:** {r['cost']}")
                        st.markdown(f'<div class="ie-take" style="font-size:13.5px"><b>Recommendation:</b> {html.escape(r["recommendation"])}</div>',
                                    unsafe_allow_html=True)
                later_ = [r for r in ex_["rows"] if r["band"] == "Running"]
                if later_:
                    st.caption("Running beyond six months: " + "; ".join(f"{r['notice']} (to {pd.Timestamp(r['ends']):%d %b %Y})" for r in later_))
                _src(ex_["source"])

            # NMPA's own incentive schemes (from its trade notices)
            nn = api_get("/incentive/nmpa-notices") or {}
            if nn.get("notices"):
                infc = [x for x in nn["notices"] if x["status"] == "In force"]
                _head("NMPA's own incentive schemes",
                      insight=(f"NMPA runs {len(infc)} incentive schemes today, from its own trade notices. A new proposal that overlaps "
                               "one of them is blocked unless an approved combination rule is recorded."),
                      sub="Read from NMPA's trade notices and circulars held in the project (scanned notices read in full). Each card "
                          "shows the benefit, who qualifies and the period; the notice number is in the table below.")
                _tl = [x for x in nn["notices"] if x.get("valid_from") and x.get("valid_to")]
                if _tl:
                    _ft = go.Figure()
                    for x in sorted(_tl, key=lambda x: x["valid_from"]):
                        live = x["status"] == "In force"
                        lab = f'{_short(x["cargos"], 28)} \u00b7 {_short(x["type"], 30)}'
                        _ft.add_bar(y=[lab], x=[(pd.Timestamp(x["valid_to"]) - pd.Timestamp(x["valid_from"])).days * 86400000],
                                    base=[x["valid_from"]], orientation="h", marker_color=_GREEN if live else _LIGHT, showlegend=False,
                                    hovertext=f'{x["notice"]}: {x["benefit"]}', hoverinfo="text")
                    _ft.add_vline(x=pd.Timestamp.today().strftime("%Y-%m-%d"), line_dash="dot", line_color=_RED)
                    _ft.add_annotation(x=pd.Timestamp.today().strftime("%Y-%m-%d"), y=1.02, yref="paper", text="today", showarrow=False,
                                       font=dict(color=_RED, size=11))
                    _ie_fig(_ft, 90 + 30 * len(_tl), legend=False)
                    _ft.update_layout(barmode="overlay"); _ft.update_traces(width=0.6)
                    _ft.update_xaxes(type="date"); _ft.update_yaxes(autorange="reversed")
                    st.markdown("**NMPA's schemes over time** (green = in force, grey = ended)")
                    _ie_show(_ft, "ie_chart_scheme_timeline")
                st.markdown('<div class="ie-acts">' + "".join(
                    f'<div class="ie-act">{_chip("In force", "good")}{_chip("to " + _d(x["valid_to"]) if x["valid_to"] else "open-ended", "info")}'
                    f'<div class="t">{html.escape(x["type"])}</div>'
                    f'<div class="w"><b>{html.escape(x["benefit"])}</b></div>'
                    f'<div class="w" style="margin-top:4px">{html.escape(x["cargos"])}</div>'
                    f'<div class="g">Notice {html.escape(x["notice"])}, {_d(x["date"])}</div></div>'
                    for x in infc) + "</div>", unsafe_allow_html=True)
                with st.expander(f"All {len(nn['notices'])} notices, with who qualifies (in force and ended)"):
                    _hlist(pd.DataFrame([{"Status": x["status"], "Notice": x["notice"], "Date": _d(x["date"]) if x["date"] else "",
                                           "Type": x["type"], "Cargo / vessels": x["cargos"], "Benefit": x["benefit"],
                                           "Who qualifies": x["eligibility"],
                                           "Valid": (f"{_d(x['valid_from'])} to {_d(x['valid_to'])}" if x["valid_to"] else
                                                     (f"from {_d(x['valid_from'])}" if x["valid_from"] else "")),
                                           "Paid": x["settlement"] or ""} for x in nn["notices"]]))
                io_ = api_get("/incentive/iron-ore-rebate", timeout=60)
                if io_:
                    with st.expander("Iron ore export rebate (in force): what the public data shows so far"):
                        chg = (io_["fy2026_27_to_date_t"] / io_["same_months_2025_t"] - 1) * 100 if io_["same_months_2025_t"] else None
                        st.markdown(f'<div class="ti-insight">Iron ore exports {io_["months"]}: {io_["fy2026_27_to_date_t"] / 1e6:.2f} MMT against '
                                    f'{io_["same_months_2025_t"] / 1e6:.2f} MMT a year earlier ({_ptxt(chg)}); 2025-26 in all: '
                                    f'{io_["fy2025_26_total_t"] / 1e6:.2f} MMT. Since the scheme began (October 2026): {io_["since_scheme_t"]:,} t '
                                    f'against {io_["since_scheme_prev_t"]:,} t a year earlier. Each extra tonne earns NMPA '
                                    f'\u20b9{io_["rate_rs_per_t"] - io_["rebate_per_extra_t_rs"]:.2f} after the \u20b9{io_["rebate_per_extra_t_rs"]:.2f} rebate.</div>',
                                    unsafe_allow_html=True)
                        base_col = f"FY 2025-26 base, {io_.get('base_months', 'held months')} (t" + ("" if io_.get("base_complete") else ", partial") + ")"
                        rows_io = []
                        for e in io_["exporters"]:
                            r_io = {"Exporter (as written)": e["customer"], "2026-27 to date (t)": e["fy2026_27_to_date_t"],
                                    base_col: e.get("fy2025_26_base_t", e["sep2025_mar2026_t"])}
                            if io_.get("same_months_compared"):
                                r_io["Extra vs a year earlier (t)"] = e.get("extra_vs_same_months_t")
                                r_io["Rebate building (\u20b9)"] = e.get("rebate_building_rs")
                            r_io["Status"] = e["status"]
                            rows_io.append(r_io)
                        _hlist(pd.DataFrame(rows_io), hide_index=True, width="stretch",
                                     column_config={"Status": st.column_config.TextColumn(width="large"),
                                        "2026-27 to date (t)": st.column_config.NumberColumn(format="localized"),
                                                    base_col: st.column_config.NumberColumn(format="localized")})
                        _note_md('<div class="ti-s">' + " ".join(html.escape(x) for x in io_["limits"]) + "</div>", unsafe_allow_html=True)
                        _src(io_["source"])

            # 3. Discount scenarios: blanket discount vs rebate on extra volume only
            # 3b. Scheme register: draft -> Traffic review -> Finance review -> approved -> active -> completed
            sch = api_get("/incentive/schemes") or {"schemes": [], "next_status": {}}
            _head("Scheme register",
                  sub=(sch.get("note", "") + " Save a scenario as a draft; it keeps the exact inputs, rate and tariff version used. "
                       "Approval needs an order or file reference; approved terms change only by an amendment, which needs "
                       "re-approval. For active and completed schemes, the cargo actually handled (NMPA's monthly statements, or the "
                       "customer's own traced tonnes for a customer scheme) is compared with the baseline frozen at approval, with "
                       "the market as context."))
            if sch.get("schemes"):
                _rs = ["Draft", "Ready for review", "Approved", "Active", "Completed", "Withdrawn"]
                _fr2 = go.Figure(go.Bar(x=_rs, y=[sum(1 for x in sch["schemes"] if x.get("status") == r_) for r_ in _rs],
                                        marker_color=[_GREY, _AMBER, _NAVY, _GREEN, _LIGHT, _LIGHT]))
                _ie_fig(_fr2, 240, ytitle="Schemes", legend=False)
                _ie_show(_fr2, "ie_chart_register")
            _TPL = {
                "Start from scratch": {},
                "Rebate on extra cargo, like NMPA's iron ore scheme (NMPA/TM/IOF-Exp-Rebate/26-27)": {
                    "sch_scope": "Rebate on extra volume", "sch_blm": "previous_fy",
                    "sch_cond": "Rebate on wharfage only for tonnes above the baseline (previous financial year, pro rata). Paid once after "
                                "the period, after Traffic verifies each customer's tonnes. Not combined with other concessions.",
                    "sch_stop": "Review after 3 months; end early if extra tonnes are below 25% of the target"},
                "Discount only in quiet months (see Seasonal windows)": {
                    "sch_scope": "Blanket discount", "sch_blm": "same_months_last_year",
                    "sch_cond": "Applies only to vessels berthing in the cargo's quiet months. Marine / Operations to confirm the berths "
                                "are free in those months. Settled at billing.",
                    "sch_stop": "End if waiting time at the cargo's berths rises above last year's level"},
                "Volume slabs, like NMPA's Harit Cargo Concession Policy 2025": {
                    "sch_scope": "Rebate on extra volume", "sch_blm": "same_months_avg_years",
                    "sch_cond": "A higher rebate on each block of tonnes above the baseline (slab-wise, as in NMPA's Harit policy). "
                                "Base rate at billing; higher slabs after Traffic verifies the tonnes.",
                    "sch_stop": "Review every 3 months against the target"},
                "Shared budget pool (as at Incheon): a fixed amount shared by extra cargo": {
                    "sch_scope": "Rebate on extra volume", "sch_blm": "same_months_last_year",
                    "sch_cond": "A fixed budget, approved by the Board, is shared among customers in proportion to their extra tonnes "
                                "against the same months last year; no customer receives more than 50% of the wharfage rate per extra "
                                "tonne. What is not earned stays with NMPA, so the total can never exceed the budget. Settled after "
                                "the period, on verification.",
                    "sch_stop": "Review after 3 months: extra tonnes and the share of the budget earned"},
                "Rebate only when the customer is ready (performance condition)": {
                    "sch_scope": "Rebate on extra volume", "sch_blm": "previous_fy",
                    "sch_cond": "Paid only on ship calls where the ship did not wait at anchorage because the receiver, shipper "
                                "or cargo was not ready (NMPA daily vessel reports; waiting for a berth never counts against the "
                                "customer). Calls with customer-side waiting pay the full rate. Settled after verification.",
                    "sch_stop": "Review after 3 months: share of qualifying calls and ship-days lost, customer not ready"},
                "Larger ships only (parcel size), like NMPA's Cape-size rebate and Deendayal's salt scheme": {
                    "sch_scope": "Blanket discount", "sch_blm": "same_months_last_year",
                    "sch_cond": "Applies only to vessels carrying at least the parcel size agreed with Marine for the berth (tonnes per call). "
                                "Larger parcels use berth time better; smaller calls pay the full rate. Settled at billing.",
                    "sch_stop": "Review after 3 months: average parcel size and berth occupancy against last year"},
                "Customer commitment (volume agreed in writing)": {
                    "sch_scope": "Rebate on extra volume", "sch_blm": "contractual",
                    "sch_cond": "Rebate only on tonnes above the volume the customer commits to in writing; a shortfall cancels the "
                                "rebate for that period.",
                    "sch_stop": "End if the committed volume is missed in two quarters in a row"},
            }

            def _apply_tpl():
                for k_, v_ in _TPL.get(st.session_state.get("sch_tpl"), {}).items():
                    st.session_state[k_] = v_
            st.markdown(f'<div class="ie-data">Designs below use the cargo and discount chosen in <b>Plan a discount</b>: '
                        f'{_chip(pick_i, "info")}{_chip(str(disc) + "% discount", "info")}</div>', unsafe_allow_html=True)
            with st.expander("Design a scheme and save it as a draft", expanded=False):
                st.selectbox("Start from", list(_TPL), key="sch_tpl", on_change=_apply_tpl,
                             help="Fills the type, baseline, conditions and stop rule from NMPA's own scheme designs. Everything can be changed.")
                f1, f2, f3 = st.columns(3)
                scope_ = f1.selectbox("Scheme type", ["Blanket discount", "Rebate on extra volume"], key="sch_scope")
                d_start = f2.date_input("Start", value=pd.Timestamp("2026-12-01").date(), key="sch_start")
                d_end = f3.date_input("End", value=pd.Timestamp("2027-02-28").date(), key="sch_end")
                g1, g2, g3 = st.columns(3)
                cap_ = g1.number_input("Budget cap (\u20b9)", 0.0, 1e10, 0.0, 100_000.0, key="sch_cap",
                                       help="The most NMPA will give away under this scheme. See the expected cost below.")
                custs_ = g2.text_input("Eligible customers", key="sch_cust", placeholder="e.g. all POL exporters")
                by_ = g3.text_input("Your name or team", key="sch_by")
                cond_ = st.text_area("Conditions and exclusions", key="sch_cond", height=70,
                                     placeholder="e.g. existing contracts excluded; settlement quarterly")
                b1, b2, b3 = st.columns(3)
                bl_methods = (rl or {}).get("baseline_methods", {"same_months_last_year": "Same months last year"})
                bm_ = b1.selectbox("Baseline method", list(bl_methods.keys()), format_func=lambda k: bl_methods[k], key="sch_blm",
                                   help="Baseline = tonnes expected without the scheme. It is frozen when the scheme is approved.")
                by_years = b2.number_input("Years to average", 2, 4, 3, key="sch_bly", disabled=bm_ != "same_months_avg_years")
                ct_ = b3.number_input("Committed tonnes (contractual)", 0.0, 1e8, 0.0, 10000.0, key="sch_ct", disabled=bm_ != "contractual")
                blv = api_get("/incentive/baseline", {"cargo": pick_i, "start": d_start.isoformat(), "end": d_end.isoformat(), "method": bm_,
                                                      "years": by_years, **({"contractual_t": ct_} if ct_ else {})})
                if blv:
                    _note_md('<div class="ti-s">' + (f'<b>Baseline:</b> {blv["tonnes"]:,} t ({html.escape(blv["label"])}; '
                                f'{html.escape(blv.get("detail", ""))})' if blv.get("tonnes") is not None else
                                f'<b>Baseline cannot be set:</b> {html.escape(blv.get("blocked") or "")}') + "</div>", unsafe_allow_html=True)
                tiers_df = None
                if scope_ == "Rebate on extra volume":
                    _note_md('<div class="ti-s"><b>Marginal slabs</b>: each block of tonnes above the baseline gets its own rate. '
                                'Leave the last "up to" empty for no upper limit. Rates are entered by authorised users; they are not NMPA policy.</div>',
                                unsafe_allow_html=True)
                    tiers_df = st.data_editor(pd.DataFrame([{"up_to_pct_above_baseline": 10.0, "rebate_pct": float(disc) / 2},
                                                            {"up_to_pct_above_baseline": None, "rebate_pct": float(disc)}]),
                                              num_rows="dynamic", key="sch_tiers", width="stretch", column_config={
                                                  "up_to_pct_above_baseline": st.column_config.NumberColumn("Up to % above baseline"),
                                                  "rebate_pct": st.column_config.NumberColumn("Rebate % on this block")})
                t1, t2 = st.columns(2)
                tgt_ = t1.number_input("Success target: extra tonnes over the baseline", 0.0, 1e8, 0.0, 10000.0, key="sch_tgt",
                                       help="Fixed before approval; results are judged against it")
                stop_ = t2.text_input("Stop rule", key="sch_stop", placeholder="e.g. end after 3 months if extra tonnes < 25% of target")
                el = api_get("/incentive/eligibility", {"cargo": pick_i, "start": d_start.isoformat(), "end": d_end.isoformat(), "customers": custs_})
                if el:
                    if el["blocks"]:
                        st.markdown('<div class="ti-insight"><b>Blocked:</b><br>' + "<br>".join("\u2022 " + html.escape(_ie_txt(b)) for b in el["blocks"])
                                    + "<br>It can be saved as a draft, but cannot go to review until these are resolved.</div>", unsafe_allow_html=True)
                    _note_md('<div class="ti-s"><b>Not checked by this tool:</b> ' + " ".join(html.escape(w) for w in el["warnings"]) + "</div>",
                                unsafe_allow_html=True)
                _bt = (blv or {}).get("tonnes")
                _r, _dsc = (sc or {}).get("rate_rs_per_t") or 0, disc / 100
                if scope_ == "Blanket discount":
                    _cost = _r * _dsc * _bt if _bt else None
                    _cost_txt = (f"Expected cost: <b>{cr(_cost)}</b>, the discount on the baseline of {_bt:,} t (cargo that comes anyway)"
                                 if _cost else "Expected cost: needs a baseline")
                else:
                    _cost = _r * _dsc * tgt_ if tgt_ else None
                    _cost_txt = (f"Expected cost: <b>{cr(_cost)}</b> if the target of {tgt_:,.0f} extra tonnes is met; nothing is paid "
                                 "on the baseline" if _cost else "Expected cost: enter a success target to see it")
                _days = (d_end - d_start).days + 1
                _checks = [
                    ("Baseline set from NMPA's statements", bool(_bt)),
                    ("Budget cap entered" + (" and covers the expected cost" if _cost else ""), bool(cap_) and (not _cost or cap_ >= _cost)),
                    ("Eligible customers named", bool(custs_.strip())),
                    ("Period of 12 months or less", 0 < _days <= 366),
                    ("Success target set", bool(tgt_)),
                    ("Stop rule written", bool(stop_.strip())),
                    ("No overlap with NMPA's schemes in force", bool(el) and not el.get("blocks")),
                ]
                _ok = sum(1 for _, v in _checks if v)
                st.markdown(f'<div class="ie-take" style="font-size:13.5px;margin-top:6px">{_cost_txt}.</div>'
                            f'<div style="margin:2px 0 4px 0"><b>Ready for review: {_ok} of {len(_checks)}</b></div>'
                            + "".join(_chip(("\u2713 " if v else "\u2022 ") + t, "good" if v else "watch") for t, v in _checks),
                            unsafe_allow_html=True)
                if st.button("Save as draft", key="sch_save", type="primary"):
                    tiers_ = None
                    if tiers_df is not None:
                        tiers_ = [{"up_to_pct_above_baseline": (None if pd.isna(r.up_to_pct_above_baseline) else float(r.up_to_pct_above_baseline)),
                                   "rebate_pct": float(r.rebate_pct)} for r in tiers_df.itertuples() if pd.notna(r.rebate_pct)]
                    try:
                        r_ = requests.post(headers=_auth_headers(), url=f"{API}/incentive/schemes", timeout=20, json={
                            "cargo": pick_i, "scope": scope_, "discount_pct": disc, "start": d_start.isoformat(), "end": d_end.isoformat(),
                            "budget_cap_rs": cap_, "customers": custs_, "conditions": cond_, "by": by_, "baseline_method": bm_,
                            "baseline_years": int(by_years), "contractual_t": ct_ or None, "tiers": tiers_,
                            "success_target_t": tgt_ or None, "stop_rule": stop_})
                        if r_.ok:
                            st.success(f"Saved as {r_.json()['id']} (draft)." + ("" if r_.json()["eligibility"]["eligible"] else " Blocked items listed above."))
                        else:
                            st.error(r_.json().get("detail", "Could not save."))
                    except requests.RequestException:
                        st.error("Could not save. Is the backend running?")
            if sch["schemes"]:
                _htable(pd.DataFrame([{
                    "Scheme": x["id"], "Status": x["status"], "Cargo": x["cargo"], "Type": x["scope"], "Discount": f"{x['discount_pct']:g}%",
                    "Period": f"{_d(x['start'])} to {_d(x['end'])}", "Baseline (t)": x["baseline_tonnes"], "Budget cap": cr(x["budget_cap_rs"]),
                    "Approval ref.": x.get("approval_reference") or "\u2014",
                    "Observed (t)": _fmt_t((x.get("observed") or {}).get("actual_tonnes")),
                    "vs baseline (t)": _fmt_t((x.get("observed") or {}).get("extra_tonnes_vs_baseline"), True)} for x in sch["schemes"]]).astype({"Observed (t)": str, "vs baseline (t)": str}),
                    hide_index=True, width="stretch", column_config={
                        "Baseline (t)": st.column_config.NumberColumn(format="localized"),
    })
                pick_s = st.selectbox("Open a scheme", [x["id"] for x in sch["schemes"]], key="sch_pick")
                xs = next(x for x in sch["schemes"] if x["id"] == pick_s)
                w1_, w2_, w3_ = st.columns([0.3, 0.3, 0.4], vertical_alignment="bottom")
                for col_, path_, label_, fn_ in ((w1_, "board-note.docx", "\u2913 Board agenda note (Word, draft)", "Board_agenda_note"),
                                                 (w2_, "trade-notice.docx", "\u2913 Trade notice (Word, draft)", "Trade_notice")):
                    try:
                        _wd = requests.get(f"{API}/incentive/schemes/{pick_s}/{path_}", headers=_auth_headers(), timeout=60)
                        if _wd.ok:
                            col_.download_button(label_, _wd.content, file_name=f"{pick_s}_{fn_}_DRAFT.docx",
                                                 mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                 key=f"wd_{path_}_{pick_s}")
                    except requests.RequestException:
                        pass
                w3_.caption("Drafts built from this scheme's figures, for Traffic and Finance to check before the Board meeting.")
                nxt = sch["next_status"].get(xs["status"], [])
                h1, h2, h3, h4 = st.columns([0.25, 0.3, 0.3, 0.15], vertical_alignment="bottom")
                to_ = h1.selectbox("Move to", ["(no change)"] + nxt, key=f"sch_to_{pick_s}")
                ref_ = h2.text_input("Approval reference", value=xs.get("approval_reference", ""), key=f"sch_ref_{pick_s}",
                                     help="The Board resolution (Section 27(1), Major Port Authorities Act 2021) or delegated order, "
                                          "and the trade notice that publishes the scheme, e.g. 'B.R. No. xx dt. dd.mm.yyyy; NMPA/TM/...'")
                note_ = h3.text_input("Note / your name", key=f"sch_note_{pick_s}")
                if h4.button("Update", key=f"sch_upd_{pick_s}"):
                    try:
                        r_ = requests.post(headers=_auth_headers(), url=f"{API}/incentive/schemes/{pick_s}", timeout=15, json={
                            "status": None if to_ == "(no change)" else to_, "approval_reference": ref_, "note": note_, "by": note_})
                        if not r_.ok:
                            st.error(r_.json().get("detail", "Could not update."))
                        else:
                            st.rerun()
                    except requests.RequestException:
                        st.error("Could not update. Is the backend running?")
                if xs.get("data_changed"):
                    st.markdown('<div class="ti-insight"><b>Data has changed since this draft was saved:</b> '
                                + "; ".join(html.escape(c) for c in xs["data_changed"])
                                + ". Re-check the figures before it moves on.</div>", unsafe_allow_html=True)
                if xs.get("approved_on_data"):
                    _note_md(f'<div class="ti-s">Approved on data version {xs["approved_on_data"]["fingerprint"]} (NMPA statements to '
                                f'{_m(xs["approved_on_data"]["nmpa_statements_through"])}); its terms and baseline stay as approved.</div>',
                                unsafe_allow_html=True)
                mc_ = xs.get("market_context") or {}
                if mc_.get("available"):
                    _note_md(f'<div class="ti-s"><b>Market context</b> ({html.escape(mc_["commodity"])}, '
                                f'{", ".join(_m(m) for m in mc_["months_compared"])} against a year earlier): New Mangalore '
                                f'{_ptxt(mc_["nmpa_growth_pct"])}, the other 11 major ports {_ptxt(mc_["other_ports_growth_pct"])}. '
                                f'{html.escape(mc_["label"].split(": ", 1)[1])}'
                                + (f' Months without comparable figures, left out: {", ".join(_m(m) for m in mc_["months_missing"])}.'
                                   if mc_.get("months_missing") else "") + "</div>", unsafe_allow_html=True)
                elif mc_:
                    _note_md(f'<div class="ti-s"><b>Market context:</b> not comparable ({html.escape(mc_.get("reason", ""))})</div>',
                                unsafe_allow_html=True)
                if xs["status"] in ("Approved", "Active"):
                    with st.expander("Amend this scheme (old terms are kept; it returns to Traffic review for re-approval)"):
                        a1, a2, a3 = st.columns(3)
                        am_disc = a1.number_input("Discount / top rebate %", 0.0, 50.0, float(xs["discount_pct"]), 0.5, key=f"am_d_{pick_s}")
                        am_end = a2.date_input("End", value=pd.Timestamp(xs["end"]).date(), key=f"am_e_{pick_s}")
                        am_cap = a3.number_input("Budget cap (\u20b9)", 0.0, 1e10, float(xs["budget_cap_rs"] or 0), 100000.0, key=f"am_c_{pick_s}")
                        am_reason = st.text_input("Reason for the amendment", key=f"am_r_{pick_s}")
                        am_by = st.text_input("Your name or team", key=f"am_b_{pick_s}")
                        if st.button("Submit amendment", key=f"am_s_{pick_s}"):
                            chg = {k: v for k, v in (("discount_pct", am_disc), ("end", am_end.isoformat()), ("budget_cap_rs", am_cap))
                                   if v != xs.get(k)}
                            try:
                                r_ = requests.post(headers=_auth_headers(), url=f"{API}/incentive/schemes/{pick_s}/amend", timeout=20,
                                                   json={"changes": chg, "reason": am_reason, "by": am_by})
                                if r_.ok:
                                    st.rerun()
                                else:
                                    st.error(r_.json().get("detail", "Could not amend."))
                            except requests.RequestException:
                                st.error("Could not amend. Is the backend running?")
                if xs.get("amendments"):
                    st.markdown("**Amendments** (earlier terms kept)")
                    _htable(pd.DataFrame([{"When": a["at"].replace("T", " "), "Who": a["by"], "Reason": a["reason"],
                                                "Earlier terms": str(a["previous_terms"]), "New terms": str(a["new_terms"]),
                                                "Earlier approval": a.get("previous_approval_reference") or ""} for a in xs["amendments"]]),
                                 hide_index=True, width="stretch")
                if xs.get("observed"):
                    ob = xs["observed"]
                    st.markdown(f'<div class="ti-insight">{html.escape(ob["label"])} Months with NMPA data: {len(ob["months_held"])} of '
                                f'{ob["months_total"]}. Cargo handled: {ob["actual_tonnes"] or 0:,} t against a baseline of '
                                f'{ob["baseline_tonnes_for_months_held"] or 0:,} t'
                                + (f'; estimated discount cost {cr(ob["estimated_discount_cost_rs"])} '
                                   f'({ob["budget_used_pct"]}% of the budget cap).' if ob.get("estimated_discount_cost_rs") is not None else ".")
                                + "</div>", unsafe_allow_html=True)
                el_ = xs.get("eligibility") or {}
                if el_.get("blocks"):
                    st.markdown('<div class="ti-insight"><b>Blocked from review:</b><br>' + "<br>".join("\u2022 " + html.escape(_ie_txt(b)) for b in el_["blocks"])
                                + "</div>", unsafe_allow_html=True)
                if xs.get("baselines"):
                    st.markdown("**Baseline versions** (frozen at approval; earlier versions kept)")
                    _htable(pd.DataFrame([{"Version": b["version"], "When": b["at"].replace("T", " "), "Method": b["label"],
                                                "Tonnes": b.get("tonnes"), "Detail": b.get("detail") or b.get("blocked") or "",
                                                "Reason": b.get("reason", ""), "Frozen": "Yes" if b.get("frozen") else "No"} for b in xs["baselines"]]),
                                 hide_index=True, width="stretch", column_config={"Tonnes": st.column_config.NumberColumn(format="localized")})
                if xs.get("tiers"):
                    _note_md('<div class="ti-s"><b>Marginal slabs:</b> ' + "; ".join(
                        (f'up to {t["up_to_pct_above_baseline"]:g}% above baseline: {t["rebate_pct"]:g}%' if t.get("up_to_pct_above_baseline") is not None
                         else f'beyond that: {t["rebate_pct"]:g}%') for t in xs["tiers"]) + "</div>", unsafe_allow_html=True)
                if xs.get("success_target_t") or xs.get("stop_rule"):
                    _note_md(f'<div class="ti-s"><b>Success target:</b> {xs.get("success_target_t") or 0:,.0f} extra tonnes over the baseline. '
                                f'<b>Stop rule:</b> {html.escape(xs.get("stop_rule") or "none")}.</div>', unsafe_allow_html=True)
                if (xs.get("observed") or {}).get("slabs"):
                    sl = xs["observed"]["slabs"]
                    _note_md(f'<div class="ti-s"><b>Rebate at the observed volume:</b> {cr(sl["rebate_rs"])}'
                                + (f' (capped; {cr(sl["rebate_before_cap_rs"])} before the cap)' if sl["capped"] else "")
                                + f'. {html.escape(sl["status"])}.</div>', unsafe_allow_html=True)
                st.markdown("**Audit trail** (who changed what, when)")
                _htable(pd.DataFrame(xs["audit"]).assign(at=lambda d_: d_["at"].str.replace("T", " "))
                             .rename(columns={"at": "When", "by": "Who", "event": "Change", "detail": "Detail"}),
                             hide_index=True, width="stretch")
                _note_md(f'<div class="ti-s">Tariff version used: {html.escape(xs["tariff_version"])}; rate \u20b9{xs["rate_rs_per_t"]:.2f}/t. '
                            f'Conditions: {html.escape(xs.get("conditions") or "none recorded")}. Eligible customers: '
                            f'{html.escape(xs.get("customers") or "not specified")}.</div>', unsafe_allow_html=True)
            else:
                _note_md('<div class="ti-s">No schemes yet.</div>', unsafe_allow_html=True)

            # Rebate claims: submitted -> verified -> approved -> paid (or rejected), with an audit trail
            cl_ = api_get("/incentive/claims") or {}
            def _claim_post(path_, body_):
                try:
                    r_ = requests.post(f"{API}{path_}", headers=_auth_headers(), json=body_, timeout=30)
                    if r_.ok:
                        return r_.json(), None
                    det_ = r_.json().get("detail") if r_.headers.get("content-type", "").startswith("application/json") else r_.text
                    return None, det_ if isinstance(det_, str) else str(det_)
                except requests.RequestException as e_:
                    return None, f"Could not reach the backend: {e_}"
            cnt_ = cl_.get("count", {})
            _head("Rebate claims",
                  insight=(f"{cl_.get('waiting', 0)} claim(s) waiting; {cnt_.get('Paid', 0)} paid; {cnt_.get('Rejected', 0)} rejected. "
                           "Each claim goes Submitted \u2192 Verified \u2192 Approved \u2192 Paid, with who did each step and when."
                           if cl_.get("claims") else
                           "No claims yet. When a customer claims a rebate (for example the iron ore rebate after March 2027), it is "
                           "recorded here and followed to payment, so nothing is paid twice or missed."),
                  sub=cl_.get("rules", ""))
            if cl_.get("claims"):
                _sts = ["Submitted", "Verified", "Approved", "Paid", "Rejected"]
                _reach = {"Submitted": sum(cnt_.get(x, 0) for x in _sts), "Verified": sum(cnt_.get(x, 0) for x in ("Verified", "Approved", "Paid")),
                          "Approved": sum(cnt_.get(x, 0) for x in ("Approved", "Paid")), "Paid": cnt_.get("Paid", 0)}
                _fcs = go.Figure(go.Funnel(y=list(_reach), x=list(_reach.values()), textinfo="value+percent initial",
                                           marker=dict(color=[_AMBER, _NAVY, _NAVY, _GREEN])))
                _ie_fig(_fcs, 280, legend=False)
                if cnt_.get("Rejected"):
                    st.caption(f'{cnt_["Rejected"]} claim(s) rejected.')
                _ie_show(_fcs, "ie_chart_claims")
                paid_tot = sum(c.get("paid_rs") or 0 for c in cl_["claims"])
                _cards([("Waiting", str(cl_.get("waiting", 0)), "submitted, verified or approved", "watch" if cl_.get("waiting") else "good"),
                        ("Paid", cr(paid_tot), f"{cnt_.get('Paid', 0)} claim(s)", "info"),
                        ("Rejected", str(cnt_.get("Rejected", 0)), "with the reason recorded", "info")])
                _hlist(pd.DataFrame([{"Scheme": b["scheme_name"], "Reference": b["scheme_ref"], "Claims": b["claims"],
                                       "Claimed": cr(b["claimed_rs"]), "Approved": cr(b["approved_rs"]), "Paid": cr(b["paid_rs"]),
                                       "Budget left": cr(b["budget_left_rs"]) if b["budget_left_rs"] is not None else "No budget held"}
                                      for b in cl_["by_scheme"]]))
                _hlist(pd.DataFrame([{"Claim": c["id"], "Customer": c["customer"], "Scheme": c["scheme_ref"],
                                       "Period": f"{c['period_from']} to {c['period_to']}", "Claimed": cr(c["claimed_rs"]),
                                       "Verified": cr(c["verified_rs"]), "Approved": cr(c["approved_rs"]), "Paid": cr(c["paid_rs"]),
                                       "Status": c["status"], "Last step by": c["history"][-1]["by"],
                                       "Days in this step": ("\u2014" if c["status"] in ("Paid", "Rejected") else
                                                             (pd.Timestamp.now() - pd.Timestamp(c["history"][-1]["at"])).days)}
                                      for c in cl_["claims"]]))
                st.caption("For reference only: NMPA's Citizen's Charter sets 5 days from receipt of bills in Finance to e-payment for "
                           "suppliers and contractors. It sets no standard for rebate claims; NMPA can set one.")
            ar_ = api_get("/incentive/approval-route") or {}
            with st.expander("Who approves what (to be confirmed by NMPA)"):
                st.markdown(ar_.get("rule", ""))
                if ar_.get("rows"):
                    _hlist(pd.DataFrame([{"Decision": r["decision"], "Authority": r["authority"] or "Not set",
                                           "Up to (\u20b9)": r["up_to_rs"] or "\u2014",
                                           "Confirmed by NMPA": ("Yes, " + r["confirmed_on"]) if r["confirmed"] else "No: to confirm",
                                           "Basis": r["basis"], "Note": r["note"]} for r in ar_["rows"]]))
                if ar_.get("references"):
                    st.markdown("**Reference documents** (starting points only):")
                    for r_ in ar_["references"]:
                        st.markdown(f"- [{r_['title']}]({r_['url']}){' (' + r_['date'] + ')' if r_['date'] else ''}: {r_['covers']}. *{r_['status']}*")
                st.caption("NMPA fills in data/approval_matrix.csv (authority, limit, confirmed_by_nmpa = yes, confirmed_on). Until then, "
                           "the platform records who approved each claim but does not apply any limit.")
            pre_ = st.session_state.pop("clm_prefill", None)
            if pre_:
                for k_, v_ in pre_.items():
                    st.session_state[k_] = v_
            with st.expander("New claim (Traffic)", expanded=bool(pre_)):
                if pre_:
                    st.info("Prepared from the monthly settlement list. Check every field against the customer's claim letter and "
                            "NMPA's bill, correct anything that differs, then submit.")
                opts_ = cl_.get("schemes", [])
                if not opts_:
                    st.info("No scheme is open for claims.")
                else:
                    k1, k2 = st.columns(2)
                    refs_ = [o["ref"] for o in opts_]
                    if st.session_state.get("clm_scheme") not in refs_:
                        st.session_state.pop("clm_scheme", None)
                    sch_ref_ = k1.selectbox("Scheme", refs_, format_func=lambda r: f"{r}: {next(o['name'] for o in opts_ if o['ref'] == r)[:60]}",
                                            key="clm_scheme")
                    sch_ = next(o for o in opts_ if o["ref"] == sch_ref_)
                    cust_ = k2.text_input("Customer", key="clm_cust")
                    k3, k4 = st.columns(2)
                    pf_ = k3.date_input("Period from", key="clm_from")
                    pt_ = k4.date_input("Period to", key="clm_to")
                    k5, k6 = st.columns(2)
                    tn_ = k5.number_input("Extra tonnes claimed", min_value=0.0, step=1000.0, key="clm_t")
                    am_ = k6.number_input("Amount claimed (\u20b9)", min_value=0.0, step=10000.0, key="clm_rs")
                    nt_ = st.text_input("Note (e.g. the customer's letter reference)", key="clm_note")
                    by_ = st.text_input("Your name (demo mode only)", key="clm_by")
                    if st.button("Submit claim", key="clm_go", type="primary"):
                        res_, err_ = _claim_post("/incentive/claims", {"scheme_ref": sch_["ref"], "customer": cust_, "period_from": str(pf_),
                                                                       "period_to": str(pt_), "claimed_tonnes": tn_, "claimed_rs": am_,
                                                                       "note": nt_, "by": by_})
                        if err_:
                            st.error(err_)
                        else:
                            st.success(f"Claim {res_['id']} submitted.")
                            st.rerun()
            open_ = [c for c in cl_.get("claims", []) if cl_.get("next", {}).get(c["status"])]
            if open_:
                with st.expander("Move a claim to its next step"):
                    c_ = st.selectbox("Claim", open_, format_func=lambda c: f"{c['id']}: {c['customer']}, {c['status']}", key="mv_claim")
                    to_ = st.radio("Next step", cl_["next"][c_["status"]], horizontal=True, key="mv_to")
                    body_ = {"to": to_, "by": st.text_input("Your name (demo mode only)", key="mv_by")}
                    if to_ == "Verified":
                        v1, v2 = st.columns(2)
                        body_["tonnes"] = v1.number_input("Verified extra tonnes", min_value=0.0, value=float(c_["claimed_tonnes"]), key="mv_t")
                        body_["amount_rs"] = v2.number_input("Verified amount (\u20b9)", min_value=0.0, value=float(c_["claimed_rs"]), key="mv_rs")
                    elif to_ == "Approved":
                        body_["amount_rs"] = st.number_input("Approved amount (\u20b9)", min_value=0.0, value=float(c_["verified_rs"] or 0), key="mv_ap")
                        rt_ = (api_get("/incentive/approval-route", {"decision": "Rebate claim: approve payment",
                                                                      "amount_rs": body_["amount_rs"]}) or {}).get("answer", {})
                        st.caption(f"Approval authority: {rt_['authority']} (confirmed by NMPA {rt_.get('confirmed_on', '')})."
                                   if rt_.get("authority") else (rt_.get("message") or "") + " The approver's name and role are recorded.")
                    elif to_ == "Paid":
                        body_["payment_ref"] = st.text_input("Payment or credit note reference", key="mv_ref")
                    body_["note"] = st.text_input("Reason" if to_ == "Rejected" else "Note", key="mv_note")
                    if st.button(f"Mark {to_.lower()}", key="mv_go", type="primary"):
                        res_, err_ = _claim_post(f"/incentive/claims/{c_['id']}/move", body_)
                        if err_:
                            st.error(err_)
                        else:
                            if res_.get("warning"):
                                st.warning(res_["warning"])
                            st.success(f"{c_['id']} is now {to_.lower()}.")
                            st.rerun()

            # Monthly settlement list for Finance: which calls and exporters qualify for NMPA's rebates this month
            sl0 = api_get("/incentive/settlement-list") or {}
            if sl0.get("available"):
                mths_ = sl0["months"][::-1]
                mth_ = st.selectbox("Month", mths_, format_func=lambda m: pd.Timestamp(m + "-01").strftime("%B %Y"), key="sl_month")
                sl_ = api_get("/incentive/settlement-list", {"month": mth_}) or sl0
                ct_, cp_ = sl_["container"]["calls"], sl_["capesize"]["calls"]
                _head(f"Monthly settlement list: {sl_['month_label']}",
                      insight=(f"{len(ct_)} container call(s) qualify for the container rebate and {len(cp_)} Berth 16 call(s) are to be "
                               f"checked for the Cape-size rebate this month. Finance applies each rebate on the bill, which carries the "
                               f"ship's GRT; amounts are shown here where the GRT is already held."),
                      sub=sl_["method"] + f" Latest daily report: {sl_['latest_report']}.")
                _cards([("Container rebate", f"{len(ct_)} call(s)", "Berth 14 \u00b7 25% to 50%, by date", "info"),
                        ("Cape-size rebate", f"{len(cp_)} call(s)", "Berth 16 \u00b7 30%, only above 80,000 GRT", "info"),
                        ("Iron ore rebate", "builds up", "paid after 31 Mar 2027, on verification", "info")])
                ssum_ = (api_get("/incentive/settlement-summary") or {}).get("rows", [])
                if ssum_:
                    _fs = go.Figure()
                    _fs.add_bar(x=[pd.Timestamp(r["month"] + "-01").strftime("%b %y") for r in ssum_], y=[r["container_calls"] for r in ssum_],
                                name="Container rebate calls (Berth 14)", marker_color=_NAVY)
                    _fs.add_bar(x=[pd.Timestamp(r["month"] + "-01").strftime("%b %y") for r in ssum_], y=[r["capesize_calls"] for r in ssum_],
                                name="Berth 16 calls to check (Cape-size)", marker_color=_AMBER)
                    _ie_fig(_fs, 300, ytitle="Ship calls"); _fs.update_layout(barmode="group")
                    st.markdown("**Qualifying calls, month by month**")
                    _ie_show(_fs, "ie_chart_settlement_months")
                st.markdown(f"**Container rebate** ({sl_['container']['notice']}): {sl_['container']['rule']}")
                if ct_:
                    _hlist(pd.DataFrame([{"Vessel": x["vessel"], "Berthed": x["berthed"], "Last seen": x["last_report"],
                                           "Run": {"F": "Foreign", "C": "Coastal"}.get(x["run"][:1].upper(), x["run"] or "\u2014"),
                                           "Cargo": x["cargo"], "GRT": f"{x['grt']:,.0f}" if x["grt"] else "On the bill",
                                           "Notice": x["notice"], "Rule": x["rule"],
                                           "Rebate (feeder to mainline)": (f"{cr(x['rebate_low_rs'])} to {cr(x['rebate_high_rs'])}" if x["rebate_low_rs"] is not None else x["apply"])}
                                          for x in ct_]))
                else:
                    st.caption("No container call at Berth 14 qualifies in this month (the rebate runs from 3 Nov 2026).")
                st.markdown(f"**Cape-size rebate** ({sl_['capesize']['notice']}): {sl_['capesize']['rule']}")
                if cp_:
                    _hlist(pd.DataFrame([{"Vessel": x["vessel"], "Berthed": x["berthed"], "Last seen": x["last_report"],
                                           "Length (LOA, m)": x["loa"] or "\u2014", "Cargo": x["cargo"],
                                           "GRT": f"{x['grt']:,.0f}" if x["grt"] else "On the bill", "Status": x["status"],
                                           "Rebate": cr(x["rebate_rs"]) if x["rebate_rs"] else "\u2014"} for x in cp_]))
                    st.caption("Length is a quick hint: Cape-size ships are typically around 280 m or longer. The GRT on the bill decides.")
                else:
                    st.caption("No call at Berth 16 in this month.")
                io_ = sl_["iron_ore"]["monitor"]
                st.markdown(f"**Iron ore export rebate** ({sl_['iron_ore']['notice']}): {sl_['iron_ore']['rule']}")
                if io_:
                    _hlist(pd.DataFrame([{"Exporter": e["customer"], f"FY 2026-27 to date ({io_['months']})": f"{e['fy2026_27_to_date_t']:,.0f} t",
                                           f"FY 2025-26 base ({sl_['iron_ore']['monitor'].get('base_months', '')}"
                                           + ("" if sl_['iron_ore']['monitor'].get('base_complete') else ", partial") + ")":
                                               f"{e.get('fy2025_26_base_t', e['sep2025_mar2026_t']):,.0f} t",
                                           "Status": e["status"]} for e in io_["exporters"]]))
                    st.caption(f"Each extra tonne above an exporter's full FY 2025-26 quantity earns \u20b9{io_['rebate_per_extra_t_rs']:,.2f}. "
                               + ("The FY 2025-26 base is complete (all 12 months of daily reports held)." if io_.get("base_complete") else
                                  f"The FY 2025-26 base covers {io_.get('base_months_held', '?')} of 12 months; back-fill the older daily reports to complete it."))
                # Prepare a claim from a line of this list: fills the claim form above; the officer checks and submits
                import datetime as _dtm
                prep_ = []
                for x in ct_:
                    prep_.append((f"Container rebate ({x['notice']}) \u00b7 {x['vessel']} \u00b7 Berth {x['berth']} \u00b7 berthed {x['berthed']}", {
                        "clm_scheme": x["notice"], "clm_cust": x.get("agent") or "",
                        "clm_from": _dtm.date.fromisoformat(x["berthed"]), "clm_to": _dtm.date.fromisoformat(x["last_report"]),
                        "clm_t": 0.0, "clm_rs": float(x["rebate_low_rs"] or 0),
                        "clm_note": (f"Settlement list {sl_['month_label']}: {x['vessel']} at Berth {x['berth']}, berthed {x['berthed']}, "
                                     f"{ {'F': 'Foreign', 'C': 'Coastal'}.get(x['run'][:1].upper(), x['run'] or 'run not stated') }, {x['cargo']}. Rebate under {x['notice']}: {x['rule']}" + (f"; estimate {cr(x['rebate_low_rs'])} to {cr(x['rebate_high_rs'])}"
                                     if x["rebate_low_rs"] is not None else "; amount from NMPA's bill (GRT on the bill)") + ".")}))
                for x in cp_:
                    prep_.append((f"Cape-size rebate \u00b7 {x['vessel']} \u00b7 Berth 16 \u00b7 berthed {x['berthed']}", {
                        "clm_scheme": sl_["capesize"]["notice"], "clm_cust": x.get("agent") or "",
                        "clm_from": _dtm.date.fromisoformat(x["berthed"]), "clm_to": _dtm.date.fromisoformat(x["last_report"]),
                        "clm_t": 0.0, "clm_rs": float(x["rebate_rs"] or 0),
                        "clm_note": (f"Settlement list {sl_['month_label']}: {x['vessel']} at Berth 16, berthed {x['berthed']}, LOA "
                                     f"{x['loa'] or 'not stated'} m, {x['cargo']}. {x['status']}. 30% of port dues and pilotage, "
                                     f"only above 80,000 GRT: check the GRT on the bill.")}))
                for e in ((io_ or {}).get("exporters") or []):
                    if "KIOCL" in e["customer"].upper().split(" + "):
                        continue
                    prep_.append((f"Iron ore export rebate \u00b7 {e['customer']}", {
                        "clm_scheme": sl_["iron_ore"]["notice"], "clm_cust": e["customer"],
                        "clm_from": _dtm.date(2026, 9, 23), "clm_to": _dtm.date(2027, 3, 31),
                        "clm_t": float(max(0, e.get("extra_vs_same_months_t") or 0)), "clm_rs": float(e.get("rebate_building_rs") or 0),
                        "clm_note": (f"Iron ore export rebate: 20% of wharfage on tonnes above the exporter's FY 2025-26 quantity, paid "
                                     f"after 31 Mar 2027 on verification. FY 2026-27 to date {e['fy2026_27_to_date_t']:,} t; FY 2025-26 base "
                                     f"{e.get('fy2025_26_base_t', e['sep2025_mar2026_t']):,} t "
                                     + ("(complete)." if (io_ or {}).get("base_complete") else "(partial: confirm with NMPA's figures).")
                                     + f" Status: {e['status']}.")}))
                if prep_:
                    p1_, p2_ = st.columns([4, 1])
                    pick_p = p1_.selectbox("Prepare a claim from this list", range(len(prep_)), format_func=lambda i: prep_[i][0], key="sl_prep_pick")
                    if p2_.button("Prepare claim", key="sl_prep_go"):
                        st.session_state["clm_prefill"] = prep_[pick_p][1]
                        st.rerun()
                    st.caption("Fills the 'New claim' form in Rebate claims with this line's details. Nothing is submitted: the officer "
                               "checks the form against the customer's claim letter and NMPA's bill, then submits.")
                for n_ in sl_["not_listed"]:
                    st.caption(n_)
                rows_csv = ([{"scheme": sl_["container"]["notice"], "vessel": x["vessel"], "berth": x["berth"], "berthed": x["berthed"],
                              "last_seen": x["last_report"], "run": x["run"], "cargo": x["cargo"], "grt": x["grt"] or "",
                              "rebate_low_rs": x["rebate_low_rs"] if x["rebate_low_rs"] is not None else "",
                              "rebate_high_rs": x["rebate_high_rs"] if x["rebate_high_rs"] is not None else "", "apply": x["apply"]} for x in ct_] +
                            [{"scheme": sl_["capesize"]["notice"], "vessel": x["vessel"], "berth": x["berth"], "berthed": x["berthed"],
                              "last_seen": x["last_report"], "run": x["run"], "cargo": x["cargo"], "grt": x["grt"] or "",
                              "rebate_low_rs": x["rebate_rs"] if x["rebate_rs"] is not None else "", "rebate_high_rs": "",
                              "apply": x["status"]} for x in cp_])
                if rows_csv:
                    st.download_button("\u2913 Settlement list for Finance (CSV)", pd.DataFrame(rows_csv).to_csv(index=False),
                                       file_name=f"settlement_list_{mth_}.csv", mime="text/csv", key="sl_csv")
                _src(sl_["source"])

            # 4. What happened after past incentives
            ev = api_get("/incentive/evidence", timeout=30)
            if ev and ev.get("available"):
                _head("What happened after past incentives",
                      insight="Each past incentive, and what the cargo did around it. Market context, not proof of effect.",
                      sub="New Mangalore against the other 11 major ports, before and after each incentive. " + ev["caution"])
                _pc, _wc0 = [], api_get("/incentive/waiver-cost", timeout=60) or {}
                for c in ev["cases"]:
                    if not c.get("measurable"):
                        _pc.append((c["incentive"], "not measurable", html.escape(_ie_txt(c["result"]))[:140], ""))
                        _note_md(f'<div class="ti-s"><b>{html.escape(c["incentive"])}</b>: {html.escape(_ie_txt(c["result"]))}</div>')
                        continue
                    if c.get("comparison_only"):
                        _pc.append((c["incentive"], f"{_ptxt(c['nmpa_coastal_growth_pct'])}",
                                    f"New Mangalore's coastal cargo, against {_ptxt(c['other_ports_coastal_growth_pct'])} at the other 11 major "
                                    f"ports (Apr to Sep 2026 vs a year earlier)", "good" if (c["nmpa_coastal_growth_pct"] or 0) > 0 else "watch"))
                        _note_md(f'<div class="ti-s"><b>{html.escape(c["incentive"])}</b>: New Mangalore\'s overseas cargo '
                                 f'{_ptxt(c["nmpa_overseas_growth_pct"])}. The concession applies at every major port, so the gap is specific '
                                 f'to New Mangalore\'s customers, not the concession itself.</div>')
                        continue
                    if c.get("waiver_window"):
                        _pc.append((c["incentive"], f"{c['march_2026_t'] / 1e3:,.0f} thousand t",
                                    f"in March 2026: {_ptxt(c['vs_march_2025_pct'])} on March 2025, {_ptxt(c['vs_feb_pct'])} on February 2026",
                                    "watch" if (c["vs_march_2025_pct"] or 0) < 0 else "good"))
                        if c.get("group_share_march_2026") and c.get("group_share_dec_feb") and c.get("group_share_march_2025"):
                            _note_md(f'<div class="ti-s"><b>{html.escape(c["incentive"])}</b>: New Mangalore\'s share of crude, POL products and '
                                     f'LPG at all major ports was {c["group_share_march_2026"]:.1f}% in March 2026, against '
                                     f'{c["group_share_dec_feb"]:.1f}% in Dec 2025 to Feb 2026 and {c["group_share_march_2025"]:.1f}% in March 2025 '
                                     f'(the Ministry\'s March report gives these three cargos only together).</div>')
                        continue
                    gap = f" ({', '.join(c['months_without_data'])}: no separate figure in the Ministry report)" if c.get("months_without_data") else ""
                    _pc.append((c["incentive"], f"{_ptxt(c['nmpa_change_pct'])}",
                                f"New Mangalore against {_ptxt(c['other_ports_change_pct'])} at the other 11 major ports; share "
                                f"{c['share_before_pct']:.1f}% \u2192 {c['share_after_pct']:.1f}%", "good" if (c["share_change_points"] or 0) > 0 else "watch"))
                    _note_md(f'<div class="ti-s"><b>{html.escape(c["incentive"])}</b>: {c["before_label"]} \u2192 {c["after_label"]}{gap}.</div>')
                if _wc0.get("total_rs"):
                    _pc.append(("Cost of the March 2026 waiver", cr(_wc0["total_rs"]),
                                "wharfage given up, upper estimate at the 2025-26 rates in force then", "act"))
                st.markdown('<div class="ie-cards" style="grid-template-columns:repeat(2,minmax(0,1fr))">' + "".join(
                    f'<div class="ie-card {t}"><div class="l">{html.escape(l)}</div><div class="v">{v}</div><div class="s">{s_}</div></div>'
                    for l, v, s_, t in _pc) + "</div>", unsafe_allow_html=True)
                _src("NMPA Trade Circular NMPA/TM/2025-26/Gen.2 (14 Mar 2026); NMPA statements; Ministry of Ports Tables 1 and 2")

            wv = api_get("/incentive/waiver-coverage", timeout=60)
            if wv and wv.get("available"):
                with st.expander(f"Ships covered by the March 2026 waiver ({_d(wv['window']['from'])} to {_d(wv['window']['to'])})"):
                    st.markdown(f'<div class="ti-insight">{len(wv["ships"])} crude and LPG ship calls berthed in the waiver window: '
                                + ", ".join(f"{c} {t / 1e3:,.0f} thousand t" for c, t in wv["tonnes_by_cargo"].items())
                                + (f' (no quantity recorded for {", ".join(wv["ships_without_quantity"])})' if wv["ships_without_quantity"] else "")
                                + f'.</div>', unsafe_allow_html=True)
                    _hlist(pd.DataFrame([{"Ship": x["vessel"], "Cargo": x["cargo"], "Customer": x["customer"], "Berthed": _d(x["berthed"]),
                                                "Berth": x["berth"] or "\u2014", "Run": {"F": "Foreign", "C": "Coastal"}.get(x["run"], x["run"]),
                                                "Tonnes": f"{x['tonnes']:,}" if x["tonnes"] else "not recorded",
                                                "Daily report": x["report_status"]} for x in wv["ships"]]),
                                 hide_index=True, width="stretch", column_config={"Tonnes": st.column_config.NumberColumn(format="localized")})
                    wc = api_get("/incentive/waiver-cost", timeout=60)
                    if wc:
                        st.markdown(f'<div class="ti-insight"><b>Wharfage waived (upper estimate): {cr(wc["total_rs"])}</b>, at the 2025-26 rates in force '
                                    f'then. {html.escape(wc["basis"])}</div>', unsafe_allow_html=True)
                        _hlist(pd.DataFrame([{"Ship": x["vessel"], "Rate line (2025-26)": {"crude_spm": "Crude through SPM", "crude_berth": "Crude at berth",
                                                    "lpg": "LPG"}[x["rate_line"]], "Rate (Rs/t)": x["rate_rs_per_t"], "SOR page": x["sor_page"],
                                                    "Wharfage waived": cr(x["wharfage_waived_rs"]) if x["wharfage_waived_rs"] else "not priced (no quantity)"}
                                                   for x in wc["ships"]]), hide_index=True, width="stretch")
                    _note_md('<div class="ti-s">' + " ".join(html.escape(n) for n in wv["notes"])
                                + (f' Left out, already working on 14 Mar: {", ".join(wv["excluded_already_working"])}.' if wv["excluded_already_working"] else "")
                                + "</div>", unsafe_allow_html=True)
                    _src(wv["source"])
            with st.expander("Basis, sources and limits"):
                st.markdown("\n".join(f"- {b}" for b in rv["basis"]))
                st.markdown("- Tariff: NMPA Scale of Rates in force from 1 May 2026 (indexed by 0.65%; validity from 7 May 2026). "
                            "Every rate used is located in this document, with its page number, by the automated checks.")
            # All discounts together
            pf_ = api_get("/incentive/portfolio", timeout=90)
            if pf_:
                _head("All discounts together: one budget",
                      insight=pf_["plain"] + " " + pf_["uptake"]["plain"],
                      sub="Like a household budget: one total limit for every discount, so Finance always knows the total. "
                          "Spain caps its ports' discounts at 20% of fee income, and at 40% on one fee for one kind of cargo. "
                          "NMPA's Board sets its own limits (approver role).")
                if pf_["schemes"]:
                    _fpf = go.Figure()
                    for k_, nm_, col_ in (("cost_to_date_rs", "Cost so far", _NAVY), ("exposure_rs", "Could cost (whole period)", _AMBER),
                                          ("budget_cap_rs", "Budget cap", _LIGHT)):
                        _fpf.add_bar(y=[f'{r["id"]} \u00b7 {r["cargo"]}' for r in pf_["schemes"]], x=[(r.get(k_) or 0) / 1e7 for r in pf_["schemes"]],
                                     orientation="h", name=nm_, marker_color=col_)
                    _ie_fig(_fpf, 110 + 60 * len(pf_["schemes"]), xtitle="\u20b9 crore"); _fpf.update_layout(barmode="group")
                    _fpf.update_yaxes(autorange="reversed")
                    _ie_show(_fpf, "ie_chart_portfolio")
                if pf_["schemes"]:
                    _htable(pd.DataFrame([{"Scheme": r["id"], "Cargo": r["cargo"], "Customer": r["customer"], "Status": r["status"],
                                           "Discount %": r["discount_pct"], "Budget cap": cr(r["budget_cap_rs"]),
                                           "Cost so far": cr(r["cost_to_date_rs"]), "Could cost (whole period)": cr(r["exposure_rs"]),
                                           "Bringing extra cargo?": {True: "Yes", False: "Not yet", None: "Not started"}[r["used"]]}
                                          for r in pf_["schemes"]]), hide_index=True, width="stretch")
                with st.expander("Board policy: total cap, combining discounts, clawback"):
                    pol_ = pf_["policy"]
                    q1_, q2_, q3_ = st.columns(3)
                    cap_ = q1_.number_input("Total cap, % of wharfage (0 = none)", 0.0, 100.0,
                                            float(pol_.get("portfolio_cap_pct_of_wharfage") or 0), key="pol_cap")
                    comb_ = q2_.number_input("Combined ceiling on one cargo, % (0 = no combining)", 0.0, 100.0,
                                             float(pol_.get("max_combined_benefit_pct") or 0), key="pol_comb")
                    claw_ = q3_.selectbox("If a commitment is missed", ["proportional", "all_or_nothing"], key="pol_claw",
                                          index=0 if pol_.get("default_clawback_rule") != "all_or_nothing" else 1)
                    pref_ = st.text_input("Board approval reference", value=pol_.get("approval_reference", ""), key="pol_ref")
                    if st.button("Save policy (approver only)", key="pol_save"):
                        try:
                            r_ = requests.post(headers=_auth_headers(), url=f"{API}/incentive/policy", timeout=20, json={
                                "portfolio_cap_pct_of_wharfage": cap_ or None, "max_combined_benefit_pct": comb_ or None,
                                "allow_combination": bool(comb_), "default_clawback_rule": claw_, "approval_reference": pref_})
                            st.success("Policy saved.") if r_.ok else st.error(r_.json().get("detail", "Could not save."))
                        except requests.RequestException:
                            st.error("Could not save. Is the backend running?")
                _src(pf_["base_note"] + ". " + " ".join(pf_["limits"]))

            # Every NMPA scheme judged so far (full check where it covers the cargo; simple check for coal and containers)
            sr_ = api_get("/incentive/scheme-review") or {}
            if sr_.get("available"):
                rows_sr = sr_["rows"]
                judged_sr = [r for r in rows_sr if r.get("available")]
                _head("Every NMPA scheme, judged so far",
                      insight=(f"{len(judged_sr)} of {len(rows_sr)} NMPA schemes can be judged with published data so far. "
                               "Schemes still running update by themselves as the Ministry publishes new months; schemes whose "
                               "cargo the Ministry does not show separately are marked 'Cannot be measured', not guessed."),
                      sub=sr_["method"] + f" Ministry data are held to {pd.Timestamp(sr_['latest_month'] + '-01'):%b %Y}.")
                _jg = [r for r in rows_sr if r.get("available") and r.get("extra_pct") is not None]
                if _jg:
                    _col = lambda res: _GREEN if res.lower().startswith("better") else _RED if res.lower().startswith("worse") else _GREY
                    _fj = go.Figure(go.Bar(y=[r["short"] for r in _jg], x=[r["extra_pct"] for r in _jg], orientation="h",
                                           marker_color=[_col(r["result"]) for r in _jg],
                                           hovertext=[r["result"] for r in _jg], hoverinfo="text+x"))
                    _ie_fig(_fj, 80 + 46 * len(_jg), xtitle="Beyond the other major ports' trend (%, or points)", legend=False)
                    _fj.update_yaxes(autorange="reversed")
                    _ie_show(_fj, "ie_chart_scheme_judged")
                    st.caption("Green = better than the other major ports; red = worse; grey = not clear yet (too few months, or within "
                               "normal ups and downs). Point at a bar for its full result.")
                _nj = [r["short"] for r in rows_sr if not (r.get("available") and r.get("extra_pct") is not None)]
                if _nj:
                    st.caption("Not judged yet: " + "; ".join(_nj) + ".")
                _htable(pd.DataFrame([{
                    "Scheme": r["short"], "Notice": r["notice"], "Scheme period": r["scheme_period"],
                    "Check": r.get("check", "\u2014"),
                    "Beyond the other ports' trend": (f"{r['extra_pct']:+.1f}%" if r.get("check") == "Full check" else f"{r['extra_pct']:+.1f} points")
                                                     if r.get("available") and r.get("extra_pct") is not None else "\u2014",
                    "Result": r["result"], "In plain words": r.get("plain") or "\u2014",
                    "Notes": r.get("notes") or "\u2014"} for r in rows_sr]))
                _src(sr_["source"])

            # Did it pay for itself? Earned from extra cargo minus what each scheme gave up
            nb_ = api_get("/incentive/net-benefit") or {}
            if nb_.get("rows"):
                judged_nb = [r for r in nb_["rows"] if r["net_low_rs"] is not None]
                _head("Did each scheme pay for itself?",
                      insight=(f"{len(judged_nb)} of {len(nb_['rows'])} schemes can be costed so far. A scheme pays for itself when the "
                               "wharfage from cargo it really brought (above what the market explains) is more than what it gave up."),
                      sub=nb_["method"])
                tone_nb = {"Paid for itself (so far)": "\u2705 ", "Did not pay for itself (so far)": "\u26a0\ufe0f ", "Close to break-even": "",
                           "Indicative only": "", "Cost not priced": "", "Earnings not priced": "", "Not yet": ""}
                rng = lambda lo, hi: "\u2014" if lo is None else (cr(lo) if abs((hi or lo) - lo) < 1 else f"{cr(lo)} to {cr(hi)}")
                _pc = [r for r in nb_["rows"] if r["cost_rs"] is not None and r["earned_high_rs"] is not None]
                if _pc:
                    _fp = go.Figure()
                    _fp.add_bar(y=[r["short"] for r in _pc], x=[r["cost_rs"] / 1e7 for r in _pc], orientation="h", name="Gave up", marker_color=_RED)
                    _fp.add_bar(y=[r["short"] for r in _pc], x=[r["earned_high_rs"] / 1e7 for r in _pc], orientation="h",
                                name="Earned from extra cargo", marker_color=_GREEN)
                    _ie_fig(_fp, 110 + 60 * len(_pc), xtitle="\u20b9 crore (estimates)")
                    _fp.update_layout(barmode="group"); _fp.update_yaxes(autorange="reversed")
                    _ie_show(_fp, "ie_chart_scheme_paid")
                _np_ = [f'{r["short"]} ({r["verdict"].lower()})' for r in nb_["rows"] if not (r["cost_rs"] is not None and r["earned_high_rs"] is not None)]
                if _np_:
                    st.caption("Not costed yet: " + "; ".join(_np_) + ".")
                _htable(pd.DataFrame([{"Scheme": r["short"], "Verdict": tone_nb.get(r["verdict"], "") + r["verdict"],
                                       "What it gave up": "\u2014" if r["cost_rs"] is None else cr(r["cost_rs"]),
                                       "Earned from extra cargo": rng(r["earned_low_rs"], r["earned_high_rs"]),
                                       "Net": rng(r["net_low_rs"], r["net_high_rs"]), "Why": r["why"] or "\u2014"} for r in nb_["rows"]]))
                st.caption("Ranges: the lower figure counts NMPA's published average handling cost per extra tonne; the higher counts none. "
                           "Costs and earnings are estimates from published data, not billed figures; the bills (What we earn \u2192 Check "
                           "against NMPA's bills) and the Scale of Rates are the authority.")
                _src(nb_["source"])

            # Did it work? NMPA against the other major ports
            _head("Did a discount work? Compare with the other major ports",
                  insight="If NMPA's cargo rose 15% but the same cargo rose 12% at every other major port, only the 3% gap "
                          "can be credited to the discount.",
                  sub="Expected without the discount = NMPA's tonnes in the same months last year x the growth at the other "
                      "major ports. The same sum on earlier months shows NMPA's normal ups and downs: a gap inside that range "
                      "is not evidence the discount worked.")
            e1_, e2_, e3_ = st.columns([0.4, 0.3, 0.3])
            ecs_ = ["Crude oil", "LPG", "POL products (out)", "POL products (in)", "Iron ore exports", "Edible oil",
                    "Fertilizer (finished)", "Fertilizer raw materials (dry)", "Food grains"]
            ec_ = e1_.selectbox("Cargo", ecs_, key="ev_c")
            es_ = e2_.date_input("Discount from", value=pd.Timestamp("2026-03-14"), key="ev_s")
            ee_ = e3_.date_input("Discount to", value=pd.Timestamp("2026-03-31"), key="ev_e")
            evr_ = api_get("/incentive/evaluate", {"cargo": ec_, "start": es_.isoformat(), "end": ee_.isoformat()}, timeout=60)
            if evr_:
                st.markdown(f'<div class="ti-insight">{html.escape(evr_["plain_answer"])}</div>', unsafe_allow_html=True)
                if evr_.get("available"):
                    nr_ = evr_.get("normal_range")
                    _fe2 = go.Figure(go.Bar(x=["Expected without the discount", "NMPA actual"],
                                            y=[evr_["expected_without_scheme_t"] / 1e3, evr_["nmpa_actual_t"] / 1e3],
                                            marker_color=[_LIGHT, _GREEN if (evr_.get("extra_credited_t") or 0) >= 0 else _RED],
                                            text=[f'{evr_["expected_without_scheme_t"] / 1e3:,.0f}k t', f'{evr_["nmpa_actual_t"] / 1e3:,.0f}k t'],
                                            textposition="outside", cliponaxis=False))
                    _ie_fig(_fe2, 300, ytitle="Thousand tonnes", legend=False)
                    _ie_show(_fe2, "ie_chart_did_it_work")
                    _htable(pd.DataFrame([{"NMPA actual (t)": evr_["nmpa_actual_t"], "Expected without the discount (t)": evr_["expected_without_scheme_t"],
                                           "Difference (t)": evr_["extra_credited_t"], "Difference %": evr_["extra_credited_pct"],
                                           "NMPA's normal range %": f'{nr_["low_pct"]:+.0f} to {nr_["high_pct"]:+.0f}' if nr_ else "not enough history"}]),
                            hide_index=True, width="stretch")
                for w_ in evr_.get("warnings", []):
                    st.markdown(f'<div class="ti-s">\u26a0 {html.escape(w_)}</div>', unsafe_allow_html=True)
                _src(evr_["source"] + ". " + " ".join(evr_.get("limits", [])))

            # Settlement of one scheme
            sch2_ = (api_get("/incentive/schemes") or {}).get("schemes", [])
            live_ = [x["id"] for x in sch2_ if x.get("status") in ("Approved", "Active", "Completed")]
            if live_:
                with st.expander("Year-end settlement of a scheme (commitment, shortfall, clawback)"):
                    ps_ = st.selectbox("Scheme", live_, key="set_pick")
                    se_ = api_get(f"/incentive/schemes/{ps_}/settlement", timeout=60)
                    if se_:
                        st.markdown(f'<div class="ti-insight">{html.escape(se_["plain"])}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="ti-s">Rule: {html.escape(se_["clawback_rule_label"])}. Settled: '
                                    f'{html.escape(se_["settlement_mode"])}. {html.escape(se_["status_label"])}</div>', unsafe_allow_html=True)

            # Competitor watch: new incentive and tariff notices at Cochin, VOC Tuticorin and Mormugao
            # NMPA circulars and trade notices: officer-added now; read automatically only after NMPA's permission
            nc_ = api_get("/incentive/nmpa-circulars") or {}
            def _nc_post(path_, body_):
                try:
                    r_ = requests.post(f"{API}{path_}", headers=_auth_headers(), json=body_, timeout=30)
                    if r_.ok:
                        return r_.json(), None
                    if r_.status_code in (401, 403):
                        return None, "Your login does not allow this (Traffic adds circulars; the Approver records NMPA's permission)."
                    return None, str(r_.json().get("detail", r_.text))
                except requests.RequestException as e_:
                    return None, f"Could not reach the backend: {e_}"
            perm_ = nc_.get("permission", {})
            _head("NMPA circulars and trade notices",
                  insight=(f"{nc_.get('open', 0)} circular(s) to look at. Each one shows which part of the platform it affects and a "
                           "suggested next step." if nc_.get("rows") else
                           "No circulars listed yet. Add NMPA's new circulars here: each is sorted (incentive, tariff, rules, weather, "
                           "statistics, tenders) with the part of the platform it affects."),
                  sub=nc_.get("rule", "") + (f" Automatic reading: ON (NMPA's permission recorded by {perm_['by']} on {perm_['on'][:10]}: "
                                             f"{perm_['reference']})." if perm_.get("granted") else
                                             " Automatic reading: OFF until NMPA's permission is recorded."))
            if nc_.get("rows"):
                _cats = nc_.get("categories", [])
                _fnc = go.Figure()
                _fnc.add_bar(y=_cats, x=[sum(1 for r in nc_["rows"] if r["category"] == c and r["status"] == "Open") for c in _cats], orientation="h",
                             name="To look at", marker_color=_AMBER)
                _fnc.add_bar(y=_cats, x=[sum(1 for r in nc_["rows"] if r["category"] == c and r["status"] != "Open") for c in _cats], orientation="h",
                             name="Done", marker_color=_LIGHT)
                _ie_fig(_fnc, 80 + 30 * len(_cats), xtitle="Circulars"); _fnc.update_layout(barmode="stack"); _fnc.update_yaxes(autorange="reversed")
                _ie_show(_fnc, "ie_chart_circulars")
                show_nc = [r for r in nc_["rows"] if r["status"] == "Open"] or nc_["rows"][-10:]
                _hlist(pd.DataFrame([{"No.": r["id"], "Date": r["date"] or "\u2014", "Circular": r["title"], "Category": r["category"],
                                       "Affects": r["affects"], "Suggested next step": r["next_step"], "Status": r["status"],
                                       "Link": r["url"] or "\u2014"} for r in show_nc]))
            with st.expander("Add an NMPA circular"):
                n1, n2 = st.columns([3, 1])
                t_nc = n1.text_input("Title, as NMPA wrote it", key="nc_title")
                d_nc = n2.date_input("Date of the circular", key="nc_date")
                u_nc = st.text_input("Link to the circular (optional)", key="nc_url")
                cats_ = ["Sort it for me"] + nc_.get("categories", [])
                c_nc = st.selectbox("Category", cats_, key="nc_cat")
                by_nc = st.text_input("Your name (demo mode only)", key="nc_by")
                if st.button("Add circular", key="nc_add", type="primary"):
                    res_, err_ = _nc_post("/incentive/nmpa-circulars", {"title": t_nc, "date": str(d_nc), "url": u_nc, "by": by_nc,
                                                                        "category": None if c_nc == "Sort it for me" else c_nc})
                    if err_:
                        st.error(err_)
                    else:
                        st.success(f"Added {res_['id']} as '{res_['category']}': {res_['next_step']}")
                        st.rerun()
            open_nc = [r for r in nc_.get("rows", []) if r["status"] == "Open"]
            if open_nc:
                with st.expander("Mark a circular as looked at"):
                    pick_nc = st.selectbox("Circular", open_nc, format_func=lambda r: f"{r['id']}: {r['title'][:70]}", key="nc_pick")
                    note_nc = st.text_input("What was done (e.g. 'added to the scheme register')", key="nc_note")
                    if st.button("Mark done", key="nc_done"):
                        res_, err_ = _nc_post(f"/incentive/nmpa-circulars/{pick_nc['id']}/done", {"note": note_nc, "by": by_nc})
                        if err_:
                            st.error(err_)
                        else:
                            st.rerun()
            with st.expander("NMPA's permission for automatic reading (Approver)"):
                st.markdown("NMPA's website asks programs not to read it automatically. When NMPA agrees in writing, record it here; "
                            "from then on the weekly refresh reads NMPA's circulars page (one request a week) and lists new circulars.")
                g_nc = st.checkbox("NMPA has given written permission", value=bool(perm_.get("granted")), key="nc_perm")
                ref_nc = st.text_input("Reference (e.g. email of 20 Nov 2026 from the Traffic Manager)", value=perm_.get("reference", ""),
                                       key="nc_ref")
                if st.button("Save", key="nc_perm_save"):
                    res_, err_ = _nc_post("/incentive/nmpa-circulars/permission", {"granted": g_nc, "reference": ref_nc, "by": by_nc})
                    if err_:
                        st.error(err_)
                    else:
                        st.success("Saved.")
                        st.rerun()

            # How New Mangalore's ship turnaround compares with the other major ports (Ministry figures)
            tb_ = api_get("/incentive/turnaround-benchmark") or {}
            if tb_.get("available"):
                _head("Ship turnaround: New Mangalore against the other major ports",
                      insight=tb_["plain"] + " Faster turnaround is part of what wins cargo, alongside price.",
                      sub="Average turnaround time in hours (lower is better). A discount cannot make up for ships waiting longer.")
                ps_ = tb_["ports"]
                cols_tb = ["#E2600E" if p["port"] == "New Mangalore Port" else "#9AA1AD" for p in ps_]
                fig_tb = go.Figure(go.Bar(x=[p["hours"] for p in ps_], y=[p["port"].replace(" Port", "") for p in ps_], orientation="h",
                                          marker_color=cols_tb, text=[f"{p['hours']:.1f}" for p in ps_], textposition="outside"))
                if tb_.get("all_ports_avg"):
                    fig_tb.add_vline(x=tb_["all_ports_avg"], line_dash="dash", line_color="#2B4A6F",
                                     annotation_text=f"All major ports {tb_['all_ports_avg']:.1f}", annotation_position="top")
                if tb_.get("nmpa_ytd"):
                    fig_tb.add_vline(x=tb_["nmpa_ytd"]["hours"], line_dash="dot", line_color="#E2600E",
                                     annotation_text=f"New Mangalore this year {tb_['nmpa_ytd']['hours']:.1f}", annotation_position="bottom")
                fig_tb.update_layout(height=430, margin=dict(l=10, r=40, t=30, b=10), yaxis=dict(autorange="reversed"),
                                     xaxis_title=f"Hours, {tb_['year']}", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_tb, **_W_CHART)
                ch_ = api_get("/incentive/charter-standards") or {}
                if ch_.get("available"):
                    std_ = {r["service"]: r for r in ch_["standards"]}
                    out_std = std_.get("Cargo handling at wharves and oil jetties", {}).get("standard")
                    act = ch_.get("actual_output_per_berth_day_t")
                    st.markdown(f'<div class="ie-take" style="font-size:13.5px"><b>NMPA\u2019s own service standards</b> (Citizen\u2019s Charter '
                                f'2024-25): berth allotment within {std_["Allotment of berths to vessels"]["standard"]} min of the vessel call, '
                                f'pilotage {std_["Pilotage"]["standard"]} min from pilot boarding to berthing, and {out_std:,.0f} t per ship '
                                f'berth-day.' + (f' Actual output was {act:,.0f} t per ship berth-day ({ch_["actual_through"]}, year to date): '
                                f'{"above" if act >= out_std else "below"} the standard, so ' + ("handling at the berth is not where time is "
                                "lost; waiting before berthing is." if act >= out_std else "berth productivity needs attention.") if act else "")
                                + '</div>', unsafe_allow_html=True)
                _src(tb_["source"] + "; NMPA Citizen's Charter 2024-25")

            cw_ = api_get("/incentive/competitor-watch") or {}
            n_new_cw = len(cw_.get("new", []))
            _head("Competitor watch: new schemes at Cochin, VOC Tuticorin and Mormugao",
                  insight=((f"{n_new_cw} new incentive or tariff notice(s) at competitor ports in the last {cw_['recent_days']} days."
                            if n_new_cw else f"No new incentive or tariff notices at competitor ports in the last {cw_['recent_days']} days.")
                           + f" Last checked: {pd.Timestamp(cw_['last_run']):%d %b %Y}." if cw_.get("available") else
                           "Not checked yet on this computer. It runs with the weekly refresh (scripts\\refresh_all.py)."),
                  sub=("Reads the competitor ports' public notice pages every week and keeps notices about rebates, concessions, "
                       "discounts, incentives, waivers, priority berthing or tariff changes. The first reading of a page is the "
                       "starting point, so only notices that appear after it are reported as new. The pages are listed in "
                       "data/competitor_sources.csv and can be changed there."))
            if cw_.get("available"):
                if n_new_cw:
                    _htable(pd.DataFrame([{"Port": r["port"], "Notice": r["title"], "Kind": r["kind"],
                                           "Date on the notice": r["date_on_page"] or "\u2014", "First seen": r["first_seen"],
                                           "Link": r["url"]} for r in cw_["new"]]))
                failed_cw = [p_ for p_ in cw_["pages"] if not p_["ok"]]
                if failed_cw:
                    st.warning("Could not be read last time: " + "; ".join(f"{p_['port']} ({p_['page']})" for p_ in failed_cw)
                               + ". Check the address in data/competitor_sources.csv.")
                empty_cw = [p_ for p_ in cw_["pages"] if p_["ok"] and not p_["found"]]
                if empty_cw:
                    st.caption("Read, but no incentive or tariff notices found (the page may load its list with JavaScript): "
                               + "; ".join(f"{p_['port']} ({p_['page']})" for p_ in empty_cw))
                with st.expander(f"All {len(cw_['all'])} incentive and tariff notices recorded at competitor ports"):
                    _hlist(pd.DataFrame([{"Port": r["port"], "Notice": r["title"], "Kind": r["kind"],
                                           "Date on the notice": r["date_on_page"] or "\u2014", "First seen": r["first_seen"]}
                                          for r in cw_["all"]]))
            _src(cw_.get("source") or "Public notice pages of the competitor ports")

            op_ = api_get("/incentive/other-ports") or {}
            if op_.get("available"):
                _head("How other major ports design schemes",
                      insight=(f"Indian major ports use {op_['kinds']} kinds of scheme; NMPA's own notices show {op_['nmpa_used']} of them. "
                               f"Not found among NMPA's notices: {', '.join(x.lower() for x in op_['not_at_nmpa'])}."),
                      sub=op_["legal_basis"] + " Other ports are shown for their design ideas only: their rates suit their own cargo, "
                          "customers and costs, so no other port's figure is used in any NMPA calculation. "
                          "NMPA's use is taken only from the notices held in this project. Each example at "
                          "another port carries its source; titles taken from a port association's list are marked as such.")
                _pt = sorted(op_["patterns"], key=lambda r: -len(r["other_ports"]))
                _fop = go.Figure(go.Bar(y=[r["pattern"] for r in _pt], x=[len(r["other_ports"]) for r in _pt], orientation="h",
                                        marker_color=[_GREEN if r["used_by_nmpa"] else _GREY for r in _pt],
                                        text=["used at NMPA" if r["used_by_nmpa"] else "not at NMPA" for r in _pt], textposition="outside", cliponaxis=False))
                _ie_fig(_fop, 90 + 30 * len(_pt), xtitle="Other major ports using this kind of scheme", legend=False)
                _fop.update_yaxes(autorange="reversed"); _fop.update_xaxes(dtick=1)
                _ie_show(_fop, "ie_chart_other_ports")
                _htable(pd.DataFrame([{
                    "Kind of scheme": r["pattern"],
                    "At NMPA (from its notices)": ("\u2713 " + r["nmpa"]) if r["used_by_nmpa"] else "Not found among NMPA's notices",
                    "Other ports": ", ".join(r["other_ports"]) or "\u2014",
                    "What it suggests for NMPA": r["idea"]} for r in op_["patterns"]]))
                with st.expander(f"All {len(op_['schemes'])} schemes recorded at other ports, with sources"):
                    for port_ in sorted({x["port"] for x in op_["schemes"]}):
                        st.markdown(f"**{port_}**")
                        st.markdown("\n".join(
                            f"- {x['scheme']}: {x['benefit']} ({x['period']}). [{x['source_title']}]({x['source_url']}) \u00b7 *{x['source_type']}*"
                            for x in op_["schemes"] if x["port"] == port_))
                _src(op_["source"])

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7 — DIGITAL TWIN
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Digital Twin Simulator</span>
      <span class="sec-tag">Module 6</span>
      <div class="sec-sub">Virtual port environment — what-if scenarios for cargo, vessels, weather, and policy changes</div>
    </div>""", unsafe_allow_html=True)
    st.caption("⚠ Scenario stress-test outcomes (workforce delta, risk classification, KPI shifts) are simulated illustrations, not calibrated against real incident data. The berth utilization **baseline** in the comparison chart below is real (data/berths.csv + latest cargo tonnage); only the 'Simulated' bars layer a hypothetical stress delta on top of it.")

    scenario_map = {
        "Cargo Surge +20%": "cargo_surge",
        "Vessel Delay Increase": "vessel_delay",
        "Trade Incentive Policy": "incentive_change",
        "Weather Disruption (Cyclone)": "weather_disruption",
    }
    sel_label = st.selectbox("Select Scenario", list(scenario_map.keys()))
    sel_key = scenario_map[sel_label]

    twin_data = api_get(f"/twin/scenario/{sel_key}") or {}
    result = twin_data.get("result", {})
    mc_data = twin_data.get("monte_carlo", {})

    if result:
        risk = result.get("risk_level", "Medium")
        risk_color = {"Low": "#059669", "Medium": "#D97706", "High": "#DC2626", "Critical": "#7C3AED"}.get(risk, "#78716C")

        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#FFFBEB,#FEF3C7);border:1px solid #FDE68A;border-radius:12px;padding:18px 22px;margin-bottom:20px;display:flex;align-items:center;gap:16px;">
          <div style="font-family:system-ui,sans-serif;font-size:18px;font-weight:800;color:#1C1917;">{result.get('name','Scenario')}</div>
          <div style="font-size:13px;color:#78716C;">{result.get('description','')}</div>
          <div style="margin-left:auto;background:{risk_color}15;border:1px solid {risk_color}40;color:{risk_color};padding:5px 14px;border-radius:16px;font-size:11px;font-weight:700;">Risk: {risk}</div>
        </div>""", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Congestion Index", f"{result.get('congestion_index',0):.2f}", result.get("congestion_delta", ""))
        c2.metric("Berth Utilization", f"{result.get('berth_utilization_pct',0):.1f}%", result.get("berth_delta", ""))
        c3.metric("Storage Utilization", f"{result.get('storage_utilization_pct',0):.1f}%", result.get("storage_delta", ""))
        c4.metric("Expected Revenue", f"₹{result.get('expected_revenue_cr',0):.1f} Cr", result.get("revenue_delta", ""))

        st.markdown("<br>", unsafe_allow_html=True)
        col_l, col_r = st.columns(2)

        with col_l:
            categories = ["Congestion", "Berth Util", "Storage Util", "Revenue"]
            baseline_vals = [0.63, 72.4, 65.0, 100.0]
            scenario_vals = [
                result.get("congestion_index", 0.63) * 100,
                result.get("berth_utilization_pct", 72.4),
                result.get("storage_utilization_pct", 65.0),
                result.get("expected_revenue_cr", 100.0) / 1.2,
            ]
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(r=baseline_vals, theta=categories, fill="toself",
                                                  name="Baseline", line_color="#78716C", fillcolor="rgba(120,113,108,0.1)"))
            fig_radar.add_trace(go.Scatterpolar(r=scenario_vals, theta=categories, fill="toself",
                                                  name=sel_label, line_color=GOLD, fillcolor="rgba(245,158,11,0.15)"))
            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 120])),
                                     paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"),
                                     height=320, showlegend=True, title="Scenario vs Baseline Comparison",
                                     legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig_radar, **_W_CHART)

        with col_r:
            add_cranes = result.get("additional_cranes_needed", 0)
            add_workforce = result.get("additional_workforce", 0)
            wf_color = "#DC2626" if add_workforce < 0 else "#059669"
            st.markdown(f"""
            <div class="panel">
              <div class="panel-title">Operational Impact Assessment</div>
              <div style="display:grid;gap:12px;">
                <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:14px;">
                  <div style="font-size:11px;color:#78716C;text-transform:uppercase;letter-spacing:0.6px;">Additional Cranes Required</div>
                  <div style="font-size:28px;font-weight:800;font-family:system-ui,sans-serif;color:#1C1917;">{add_cranes}</div>
                </div>
                <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:14px;">
                  <div style="font-size:11px;color:#78716C;text-transform:uppercase;letter-spacing:0.6px;">Workforce Delta</div>
                  <div style="font-size:28px;font-weight:800;font-family:system-ui,sans-serif;color:{wf_color};">{add_workforce:+d}</div>
                </div>
                <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:14px;">
                  <div style="font-size:11px;color:#78716C;text-transform:uppercase;letter-spacing:0.6px;">Risk Classification</div>
                  <div style="font-size:20px;font-weight:800;font-family:system-ui,sans-serif;color:{risk_color};">{risk}</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

        # Berth utilization comparison
        berths = api_get("/twin/berths") or {"berths": []}
        berths = berths.get("berths", [])
        if berths:
            df_b = pd.DataFrame(berths)
            import random as _rnd
            _rnd.seed(42)
            delta = float(result.get("berth_delta", "+0%").replace("%", ""))
            df_b["simulated_pct"] = df_b["utilization_pct"].apply(lambda x: min(100, x * (1 + delta / 100) + _rnd.gauss(0, 2)))
            fig_comp = go.Figure()
            fig_comp.add_trace(go.Bar(x=df_b["berth_id"], y=df_b["utilization_pct"],
                                       name="Baseline", marker_color="#D1D5DB"))
            fig_comp.add_trace(go.Bar(x=df_b["berth_id"], y=df_b["simulated_pct"],
                                       name=f"Simulated: {sel_label}", marker_color=GOLD, opacity=0.85))
            fig_comp.update_layout(**PLOTLY_THEME, barmode="group", height=280,
                                    title="Berth Utilization — Baseline vs Simulated")
            fig_comp.update_yaxes(range=[0, 110])
            st.plotly_chart(fig_comp, **_W_CHART)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8 — AI MARITIME COPILOT
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">AI Maritime Copilot</span>
      <span class="sec-tag">Module 7</span>
      <div class="sec-sub">LangGraph Cognitive Dispatcher — 3-tier fallback: LLM → SLM → Deterministic Zero-LLM</div>
    </div>""", unsafe_allow_html=True)
    st.caption("⚠ 'LangGraph' names the architecture pattern, not the library — `langgraph`/`langchain` are not dependencies of this project (see requirements.txt). Responses are templated from backend/app/services/synthetic_data.py, not generated by a real LLM call.")

    # Agent Roster
    agents = [
        ("Forecast Agent", "Cargo volume prediction queries"),
        ("Trade Agent", "Global trade lane & commodity analysis"),
        ("Policy Agent", "Incentive & regulation recommendations"),
        ("Simulation Agent", "Digital twin & what-if scenarios"),
        ("Reporting Agent", "Executive summary generation"),
    ]
    agent_cols = st.columns(5)
    for i, (name, role) in enumerate(agents):
        with agent_cols[i]:
            st.markdown(f"""
            <div style="background:#FFFFFF;border:1px solid #FDE68A;border-top:3px solid #F59E0B;border-radius:10px;padding:12px;text-align:center;">
              <div style="font-family:system-ui,sans-serif;font-size:12px;font-weight:700;color:#1C1917;">{name}</div>
              <div style="font-size:10px;color:#78716C;margin-top:4px;">{role}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Suggested queries
    sugg_data = api_get("/copilot/suggested-queries") or {"queries": []}
    suggestions = sugg_data.get("queries", [])
    if suggestions:
        st.markdown("**Suggested Queries:**")
        chip_html = "".join([f'<span class="query-chip">{q}</span>' for q in suggestions[:4]])
        st.markdown(chip_html, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns([2, 3])

    with col_l:
        query_input = st.text_area(
            "Ask the Maritime Copilot:",
            placeholder="e.g. Why is cargo forecast decreasing? What incentive should be applied?",
            height=120,
        )

        submit = st.button("Submit Query to Copilot")

        active_query = None
        if submit and query_input.strip():
            active_query = query_input

        # Quick query buttons
        st.markdown("**Or one-click submit a suggested query:**")
        qcols = st.columns(2)
        for i, q in enumerate(suggestions[:4]):
            with qcols[i % 2]:
                if st.button(q[:35] + "..." if len(q) > 35 else q, key=f"qbtn_{i}"):
                    active_query = q

        if active_query:
            with st.spinner("Dispatching through LangGraph..."):
                result = api_post("/copilot/query", {"query": active_query})
                if result:
                    st.session_state["last_copilot"] = result

    with col_r:
        if "last_copilot" in st.session_state:
            cop = st.session_state["last_copilot"]
            trace = cop.get("trace", {})
            response = cop.get("response", {})

            # Dispatch trace
            st.markdown('<div class="panel"><div class="panel-title">LangGraph Dispatch Trace</div>', unsafe_allow_html=True)
            tier_color = {"Tier 1: Heavy Synthesis (LLM)": "#DC2626",
                          "Tier 2: Fast Reasoning (SLM)": "#D97706",
                          "Tier 3: Deterministic Zero-LLM": "#059669"}.get(trace.get("tier", ""), GOLD)
            st.markdown(f"""
            <div style="display:flex;gap:20px;margin-bottom:14px;flex-wrap:wrap;">
              <span class="metric-pill">Complexity: {trace.get('complexity','')}</span>
              <span class="metric-pill" style="color:{tier_color};border-color:{tier_color}40;">Tier: {trace.get('tier','')}</span>
              <span class="metric-pill">Agent: {trace.get('agent','')}</span>
              <span class="metric-pill">Total: {trace.get('total_ms',0)}ms</span>
            </div>""", unsafe_allow_html=True)

            for step in trace.get("trace", []):
                st.markdown(f"""
                <div class="trace-step">
                  <div class="trace-num">{step['step']}</div>
                  <div style="flex:1;">
                    <div class="trace-component">{step['component']}</div>
                    <div class="trace-action">{step['action']}</div>
                    <div class="trace-detail">{step['detail']}</div>
                  </div>
                  <div class="trace-ms">{step['ms']}ms</div>
                </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # Response
            if response:
                confidence_pct = int(response.get("confidence", 0.85) * 100)
                st.markdown(f"""
                <div class="copilot-response">
                  <div style="font-size:11px;color:#78716C;margin-bottom:12px;display:flex;gap:12px;flex-wrap:wrap;">
                    <span><b>Confidence:</b> {confidence_pct}%</span>
                    <span><b>Data Sources:</b> {", ".join(response.get("data_refs", []))}</span>
                  </div>
                  {response.get("answer","").replace(chr(10), "<br>")}
                </div>""", unsafe_allow_html=True)

                followups = response.get("suggested_followups", [])
                if followups:
                    st.markdown("<br>**Follow-up Questions:**")
                    fu_html = "".join([f'<span class="query-chip">{q}</span>' for q in followups])
                    st.markdown(fu_html, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background:#FFFBEB;border:2px dashed #FDE68A;border-radius:12px;padding:40px;text-align:center;color:#78716C;">
              <div style="font-family:system-ui,sans-serif;font-size:18px;font-weight:700;color:#92400E;margin-bottom:8px;">LangGraph Copilot Ready</div>
              <div style="font-size:13px;">Type a query and click Submit to see the 3-tier dispatch trace and AI response.</div>
            </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9 — DATA PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[8]:
    st.markdown('<div class="ys-content">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sec-header">
      <span class="sec-title">Synthetic Data Pipeline & Architecture</span>
      <span class="sec-tag">Infrastructure</span>
      <div class="sec-sub">Kafka ingestion → Spark fusion → Data pools → AI readiness — real-time processing metrics</div>
    </div>""", unsafe_allow_html=True)

    pipe_data = api_get("/pipeline/status") or {}
    log_data = api_get("/pipeline/log") or {"events": []}
    kafka = pipe_data.get("kafka", {})
    spark = pipe_data.get("spark", {})
    airflow = pipe_data.get("airflow", {})
    pools = pipe_data.get("data_pools", {})

    # Pipeline flow stages
    stage_cols = st.columns(4)
    stages = [
        ("1. DATA INGESTION", "Internal Port Authority Data\nExternal AIS · Weather · Commodity APIs\nKafka Stream · Airflow Scheduler"),
        ("2. SPATIO-TEMPORAL FUSION", "Spark Streaming (temporal alignment)\nPyTorch Grid Matching (ship + weather)\nSLM Text Processor (PII masking)"),
        ("3. DATA POOLS", "PostgreSQL (master port data)\nTimescaleDB (AIS time-series)\nMilvus / Pinecone (vector embeddings)"),
        ("4. AI ORCHESTRATION", "LangGraph Cognitive Dispatcher\n3-Tier Execution & Fallback\n5 Specialized AI Agents"),
    ]
    for col, (title, desc) in zip(stage_cols, stages):
        with col:
            st.markdown(f"""
            <div class="pipeline-stage">
              <div class="pipeline-stage-title">{title}</div>
              <div class="pipeline-stage-sub">{desc.replace(chr(10), '<br>')}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # System Metrics
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Kafka msg/sec", f"{kafka.get('messages_per_sec',0):,}")
    m2.metric("Consumer Lag", str(kafka.get("consumer_lag", 0)))
    m3.metric("Spark rows/sec", f"{spark.get('rows_per_sec',0):,}")
    m4.metric("Airflow Success", f"{airflow.get('success_rate_pct',0)}%")
    m5.metric("Total Records", f"{pools.get('postgresql_records',0)/1e6:.2f}M")
    m6.metric("Storage (GB)", f"{pools.get('total_storage_gb',0):.1f}")

    st.markdown("<br>", unsafe_allow_html=True)
    col_log, col_pool = st.columns([3, 2])

    with col_log:
        st.markdown('<div class="panel"><div class="panel-title">Live Ingestion Event Log</div>', unsafe_allow_html=True)
        events = log_data.get("events", [])
        rows_html = ""
        for ev in events:
            lvl_class = "log-warn" if ev["level"] == "WARN" else "log-info"
            rows_html += f'<div class="log-row"><span class="log-ts">{ev["timestamp"]}</span><span class="log-src">[{ev["source"]}]</span><span class="{lvl_class}">{ev["message"]}</span></div>'
        st.markdown(f'<div class="log-container">{rows_html}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_pool:
        st.markdown('<div class="panel"><div class="panel-title">Data Pool Statistics</div>', unsafe_allow_html=True)
        pool_metrics = [
            ("PostgreSQL", "Relational master data", f"{pools.get('postgresql_records',0):,}", "records"),
            ("TimescaleDB", "AIS time-series", f"{pools.get('timescaledb_records',0)/1e6:.1f}M", "records"),
            ("Milvus Vectors", "Contextual RAG embeddings", f"{pools.get('milvus_vectors',0):,}", "vectors"),
        ]
        for name, desc, val, unit in pool_metrics:
            st.markdown(f"""
            <div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:14px;margin-bottom:10px;">
              <div style="font-weight:700;font-size:13px;color:#92400E;">{name}</div>
              <div style="font-size:11px;color:#78716C;margin-bottom:6px;">{desc}</div>
              <div style="font-family:system-ui,sans-serif;font-size:22px;font-weight:800;color:#1C1917;">{val} <span style="font-size:11px;color:#78716C;">{unit}</span></div>
            </div>""", unsafe_allow_html=True)

        uptime_data = [
            ("Kafka", kafka.get("uptime_pct", 99.97)),
            ("Spark", spark.get("uptime_pct", 99.91)),
            ("Airflow", airflow.get("uptime_pct", 99.84)),
        ]
        for svc, pct in uptime_data:
            color = "#059669" if pct >= 99.9 else "#D97706"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #FEF3C7;">
              <span style="font-size:12px;font-weight:600;color:#1C1917;">{svc} Uptime</span>
              <span style="font-size:12px;font-weight:700;color:{color};">{pct}%</span>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Architecture Diagrams
    st.markdown("---")
    st.markdown("""<div class="sec-header" style="margin-top:0">
      <span class="sec-title" style="font-size:18px">System Architecture Diagrams</span>
    </div>""", unsafe_allow_html=True)

    arch_tabs = st.tabs([
        "LangGraph Dispatcher (Diagram 1)",
        "Data Ingestion & Fusion (Diagram 2)",
        "Backend & Security (Diagram 3)",
        "End-to-End Flow (Diagram 4)",
    ])
    for i, atab in enumerate(arch_tabs):
        with atab:
            img_path = ARCH_DIR / "assets" / f"{i+1}.jpeg"
            if img_path.exists():
                st.image(str(img_path), **_W_IMG)
            else:
                st.info(f"Architecture diagram {i+1} not found at {img_path}")

    st.markdown('</div>', unsafe_allow_html=True)
