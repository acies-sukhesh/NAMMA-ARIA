"""
app.py — ARIA v2 — NammaYatri Autonomous PM Workspace

5-tab PM intelligence workspace:
  📡 Signal Feed | 📈 Impact Quadrant | 🎯 RICE Score | 📝 Requirements | 📊 Success Metrics
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="ARIA v2 — NammaYatri PM Agent",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp { background-color: #0e1117; }
    section[data-testid="stSidebar"] { background-color: #161b22; }

    /* Cards */
    .aria-card {
        background: #1c2333; border: 1px solid #30363d;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
    }
    .aria-card h4 { color: #58a6ff; margin: 0 0 8px 0; }
    .aria-card p  { color: #c9d1d9; margin: 0; font-size: 0.9rem; }

    /* Answer box */
    .answer-box {
        background: #1c2333; border-left: 4px solid #58a6ff;
        border-radius: 8px; padding: 20px 24px; margin-top: 12px;
        color: #e6edf3; line-height: 1.7;
    }

    /* Priority / severity badges */
    .badge-critical { background:#3d0a0a; color:#ff4444; border:1px solid #ff4444; border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:700; }
    .badge-high     { background:#3d1212; color:#f85149; border:1px solid #f85149; border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:600; }
    .badge-medium   { background:#3d2b0a; color:#d29922; border:1px solid #d29922; border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:600; }
    .badge-low      { background:#1a4a2e; color:#3fb950; border:1px solid #3fb950; border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:600; }
    .badge-pass     { background:#0d2618; color:#3fb950; border:1px solid #3fb950; border-radius:12px; padding:2px 8px; font-size:0.75rem; font-weight:700; }
    .badge-fail     { background:#2d0a0a; color:#f85149; border:1px solid #f85149; border-radius:12px; padding:2px 8px; font-size:0.75rem; font-weight:700; }
    .badge-info     { background:#0d1f38; color:#58a6ff; border:1px solid #58a6ff; border-radius:12px; padding:2px 10px; font-size:0.78rem; }
    .badge-purple   { background:#1f0d38; color:#bc8cff; border:1px solid #bc8cff; border-radius:12px; padding:2px 10px; font-size:0.78rem; }
    .badge-orange   { background:#2d1a00; color:#e3a03e; border:1px solid #e3a03e; border-radius:12px; padding:2px 10px; font-size:0.78rem; }
    .badge-teal     { background:#002d2d; color:#3ecfcf; border:1px solid #3ecfcf; border-radius:12px; padding:2px 10px; font-size:0.78rem; }
    .badge-gold     { background:#2d2500; color:#d4a017; border:1px solid #d4a017; border-radius:12px; padding:2px 10px; font-size:0.78rem; }
    .badge-blocked  { background:#2d0a3d; color:#bc8cff; border:1px solid #bc8cff; border-radius:12px; padding:3px 12px; font-size:0.82rem; font-weight:700; }

    /* Tool / source pills */
    .tool-pill {
        display: inline-block; background: #1f2d3d; color: #58a6ff;
        border: 1px solid #1f6feb; border-radius: 20px; padding: 2px 10px;
        font-size: 0.75rem; margin: 2px 3px 2px 0;
    }
    .src-pill {
        display: inline-block; background: #1a2d1e; color: #3fb950;
        border: 1px solid #3fb950; border-radius: 20px; padding: 2px 10px;
        font-size: 0.75rem; margin: 2px 3px 2px 0; word-break: break-all;
    }

    /* Consultation banners */
    .consult-banner {
        background: #2d1f00; border: 2px solid #d29922; border-radius: 8px;
        padding: 12px 16px; margin: 8px 0; color: #d29922;
    }
    .block-banner {
        background: #2d0a0a; border: 2px solid #f85149; border-radius: 8px;
        padding: 12px 16px; margin: 8px 0; color: #f85149;
    }

    /* KPI cards */
    .kpi-card {
        background: #1c2333; border: 1px solid #30363d; border-radius: 10px;
        padding: 14px 10px; text-align: center; margin-bottom: 6px;
    }
    .kpi-label { color: #8b949e; font-size: 0.75rem; margin-bottom: 4px; }
    .kpi-value { color: #e6edf3; font-size: 1.5rem; font-weight: 700; }
    .kpi-breached { color: #f85149 !important; }
    .kpi-healthy  { color: #3fb950 !important; }

    /* Insight card */
    .insight-card {
        background: #1c2333; border-left: 4px solid; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 10px;
    }
    .insight-critical { border-color: #ff4444; }
    .insight-high     { border-color: #f85149; }
    .insight-medium   { border-color: #d29922; }
    .insight-low      { border-color: #3fb950; }

    /* Impact Quadrant grid */
    .quadrant-qw   { background:#0a1f0a; border:2px solid #3fb950; border-radius:12px; padding:16px; min-height:240px; }
    .quadrant-mb   { background:#0d1f38; border:2px solid #58a6ff; border-radius:12px; padding:16px; min-height:240px; }
    .quadrant-lhf  { background:#1f1a00; border:2px solid #d29922; border-radius:12px; padding:16px; min-height:240px; }
    .quadrant-dp   { background:#1a0a1a; border:2px solid #bc8cff; border-radius:12px; padding:16px; min-height:240px; }
    .quadrant-title { font-size:1rem; font-weight:700; margin-bottom:10px; }
    .feature-card {
        background:#21262d; border:1px solid #30363d; border-radius:8px;
        padding:10px 12px; margin-bottom:8px;
    }
    .feature-card-title { color:#e6edf3; font-size:0.88rem; font-weight:600; margin-bottom:4px; }
    .rice-score { color:#58a6ff; font-size:0.82rem; font-weight:700; }

    /* RICE table */
    .rice-row { display:flex; gap:8px; align-items:center; padding:8px 0; border-bottom:1px solid #21262d; }
    .rice-rank { color:#8b949e; font-size:0.82rem; width:30px; }
    .rice-title { color:#c9d1d9; font-size:0.85rem; flex:1; }

    /* Weight bars */
    .weight-bar-bg { background:#21262d; border-radius:6px; height:12px; width:100%; }
    .weight-bar-fill { background:#58a6ff; border-radius:6px; height:12px; }

    /* Sidebar metric row */
    .sb-metric { display:flex; justify-content:space-between; align-items:center;
                  padding:4px 0; border-bottom:1px solid #21262d; }
    .sb-metric-label { color:#8b949e; font-size:0.78rem; }
    .sb-metric-val   { font-size:0.82rem; font-weight:700; }

    /* Mission filter row */
    .mf-row { display:flex; align-items:center; gap:8px; padding:3px 0; }
    .mf-label { color:#8b949e; font-size:0.75rem; flex:1; }

    .stButton > button {
        width: 100%; background: #1c2333; border: 1px solid #30363d;
        color: #c9d1d9; border-radius: 8px; padding: 8px 12px;
        text-align: left; transition: all 0.2s; margin-bottom: 4px;
        font-size: 0.85rem;
    }
    .stButton > button:hover { background: #21262d; border-color: #58a6ff; color: #58a6ff; }
    hr { border-color: #30363d; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "messages":             [],
    "agent":                None,
    "agent_llm_signature":  "",
    "pending_input":        "",
    "auto_analysis_done":   False,
    # analysis cache
    "kpi_data":             {},
    "rice_data":            {},
    "quadrant_data":        {},
    "mission_filter_data":  {},
    "prd_data":             {},
    "jira_data":            {},
    "experiment_data":      {},
    "stakeholder_data":     {},
    # UI state
    "active_pm_core":       "—",
    "last_workflow_type":   "—",
    "last_mission_filter":  {},
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_json(text) -> dict | list | None:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except Exception:
        return None


def _extract_renderable_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return str(content.get("text") or content)
    return str(content)


def _sev_color(sev: str) -> str:
    return {"CRITICAL": "#ff4444", "HIGH": "#f85149",
            "MEDIUM": "#d29922", "LOW": "#3fb950"}.get(sev.upper(), "#58a6ff")


def _sev_badge(sev: str) -> str:
    cls = {"CRITICAL": "badge-critical", "HIGH": "badge-high",
           "MEDIUM": "badge-medium", "LOW": "badge-low"}.get(sev.upper(), "badge-info")
    return f'<span class="{cls}">{sev}</span>'


def _workflow_badge(wtype: str) -> str:
    badges = {
        "KPI_INCIDENT":      ("badge-critical",  "🚨 KPI INCIDENT"),
        "FEATURE_REQUEST":   ("badge-info",       "🔧 FEATURE REQUEST"),
        "IMPACT_ANALYSIS":   ("badge-purple",     "📈 IMPACT ANALYSIS"),
        "COMPETITOR_RESEARCH":("badge-teal",      "🏁 COMPETITOR RESEARCH"),
        "DRIVER_ISSUE":      ("badge-orange",     "🚗 DRIVER ISSUE"),
        "FULL_WORKFLOW":     ("badge-gold",       "⚡ FULL WORKFLOW"),
        "LEARNING_QUERY":    ("badge-medium",     "📚 LEARNING QUERY"),
        "GENERAL":           ("badge-low",        "💬 GENERAL Q&A"),
    }
    cls, label = badges.get(wtype, ("badge-info", wtype))
    return f'<span class="{cls}">{label}</span>'


def _pmcore_badge(core: str) -> str:
    return f'<span class="badge-purple">🎯 {core}</span>'


def _q_badge(q_label: str, status: str) -> str:
    cls = "badge-pass" if status == "PASS" else "badge-fail"
    icon = "✓" if status == "PASS" else "✗"
    return f'<span class="{cls}">{icon} {q_label}</span>'


def _get_data_status():
    data_dir = Path("data")
    if not data_dir.exists():
        return 0, []
    files = [f for f in data_dir.iterdir() if f.suffix in {".txt", ".md", ".pdf"}]
    return len(files), [f.name for f in files]


@st.cache_resource(show_spinner=False)
def _load_agent(sig: str):
    from src.agent import build_agent
    return build_agent()


# ── Auto-analysis on first load ────────────────────────────────────────────────

def _run_auto_analysis():
    """Run KPI check + RICE scoring on first page load and cache results."""
    if st.session_state.auto_analysis_done:
        return

    try:
        import src.tools as T

        # KPI metrics
        kpi_raw = T.check_kpi_metrics.func("")
        kpi_parsed = _safe_json(kpi_raw) or {}
        st.session_state["kpi_data"] = kpi_parsed

        # RICE scoring (uses default features)
        rice_raw = T.prioritize_with_rice.func(json.dumps({"pain_points": []}))
        rice_parsed = _safe_json(rice_raw) or {}
        st.session_state["rice_data"] = rice_parsed

        # Impact quadrant
        quad_raw = T.generate_impact_quadrant.func(rice_raw)
        st.session_state["quadrant_data"] = _safe_json(quad_raw) or {}

    except Exception:
        pass  # Silently fail — user can refresh manually

    st.session_state.auto_analysis_done = True


_run_auto_analysis()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-size:1.5rem;font-weight:800;color:#58a6ff;letter-spacing:-0.5px;">🚌 ARIA v2</div>'
        '<div style="font-size:0.8rem;color:#8b949e;margin-bottom:16px;">'
        'NammaYatri — Autonomous PM Agent</div>',
        unsafe_allow_html=True,
    )

    # ── Live Metrics Panel ───────────────────────────────────────────────────
    st.markdown('<div style="color:#c9d1d9;font-size:0.82rem;font-weight:600;margin-bottom:6px;">📊 Live KPIs</div>', unsafe_allow_html=True)
    kpi = st.session_state["kpi_data"].get("metrics", {})
    breached = st.session_state["kpi_data"].get("breached_kpis", [])

    _kpi_display = [
        ("ride_completion_rate",   "Completion Rate",   "%",   False),
        ("driver_cancellation_rate","Driver Cancel",   "%",    True),
        ("avg_wait_time_minutes",  "Avg Wait",         "m",    True),
        ("driver_retention_rate",  "Driver Retention", "%",    False),
        ("app_rating",             "App Rating",       "★",   False),
    ]
    for key, label, unit, higher_is_bad in _kpi_display:
        raw = kpi.get(key, {})
        val = raw.get("value", "—") if isinstance(raw, dict) else raw
        is_br = key in breached
        color = "#f85149" if is_br else "#3fb950"
        arrow = " ↑" if is_br and higher_is_bad else (" ↓" if is_br else "")
        st.markdown(
            f'<div class="sb-metric">'
            f'<span class="sb-metric-label">{label}</span>'
            f'<span class="sb-metric-val" style="color:{color};">{val}{unit}{arrow}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if breached:
        st.markdown(
            f'<div style="background:#2d0a0a;border:1px solid #f85149;border-radius:6px;'
            f'padding:6px 10px;margin:6px 0;color:#f85149;font-size:0.75rem;">'
            f'⚠️ {len(breached)} KPI(s) breached</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── PM Core routing indicator ────────────────────────────────────────────
    pm_core = st.session_state.get("active_pm_core", "—")
    wtype   = st.session_state.get("last_workflow_type", "—")
    st.markdown(
        f'<div style="font-size:0.78rem;color:#8b949e;margin-bottom:4px;">PM Core Active</div>'
        f'<div style="color:#bc8cff;font-weight:700;font-size:0.85rem;margin-bottom:10px;">'
        f'🎯 {pm_core}</div>',
        unsafe_allow_html=True,
    )

    # ── Mission filter status ────────────────────────────────────────────────
    mf = st.session_state.get("last_mission_filter", {})
    if mf:
        st.markdown('<div style="font-size:0.78rem;color:#8b949e;margin-bottom:6px;">Mission Filter</div>', unsafe_allow_html=True)
        mf_inner = mf.get("mission_filter", {})
        q_map = [
            ("Q1", "Q1_driver_welfare",   "Driver"),
            ("Q2", "Q2_rider_trust",      "Rider"),
            ("Q3", "Q3_beckn_compliance", "Beckn"),
            ("Q4", "Q4_zero_commission",  "Zero-₹"),
        ]
        mf_html = ""
        for qlabel, qkey, qshort in q_map:
            status = mf_inner.get(qkey, {}).get("status", "?")
            cls = "badge-pass" if status == "PASS" else "badge-fail"
            icon = "✓" if status == "PASS" else "✗"
            mf_html += f'<span class="{cls}" style="margin:1px 2px;font-size:0.7rem;">{icon} {qshort}</span>'
        st.markdown(mf_html, unsafe_allow_html=True)
        verdict = mf.get("overall_verdict", "")
        if "BLOCKED" in verdict:
            st.markdown('<span class="badge-fail" style="font-size:0.75rem;">⛔ BLOCKED</span>', unsafe_allow_html=True)
        elif verdict == "APPROVED":
            st.markdown('<span class="badge-pass" style="font-size:0.75rem;">✅ APPROVED</span>', unsafe_allow_html=True)
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Primary action ───────────────────────────────────────────────────────
    if st.button("▶️ Start Full PM Workflow", use_container_width=True, type="primary"):
        st.session_state.pending_input = "start pm workflow full pipeline autonomous"
        st.rerun()

    st.markdown("**⚡ Quick Actions**")

    _quick = {
        "🚨 Analyze KPI Incident":         "KPI breach detected — driver cancellation rate dropped. Run the KPI incident workflow.",
        "🔧 Generate PRD":                  "Build a PRD for a Scheduled Rides feature for NammaYatri — advance booking up to 24 hours.",
        "📈 Impact Analysis & RICE":        "Run an impact analysis and RICE prioritization for NammaYatri backlog. What should we build next?",
        "🏁 Competitor Research":           "Compare NammaYatri against Ola, Uber, and Rapido. What features are we missing?",
        "🚗 Driver Issue Investigation":    "Investigate driver earnings and ARDU sentiment. Subscription churn is rising.",
        "📚 Learning State":                "Show me the learning state — what decisions have been logged, what have we learned?",
    }
    for label, prompt in _quick.items():
        if st.button(label, key=f"qa_{label}"):
            st.session_state.pending_input = prompt
            st.rerun()

    st.markdown("---")

    n_files, _ = _get_data_status()
    label_color = "#3fb950" if n_files else "#d29922"
    label_text  = f"{n_files} docs indexed" if n_files else "No docs — run store_index.py"
    st.markdown(
        f'<div style="color:{label_color};font-size:0.78rem;margin-bottom:8px;">'
        f'📁 {label_text}</div>',
        unsafe_allow_html=True,
    )

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Refresh Analysis", use_container_width=True):
        st.session_state.auto_analysis_done = False
        _run_auto_analysis()
        st.rerun()

    st.markdown(
        '<div style="color:#8b949e;font-size:0.72rem;margin-top:12px;">'
        'ARIA v2 · Beckn / ONDC · Zero Commission<br>'
        'Built for NammaYatri</div>',
        unsafe_allow_html=True,
    )


# ── Page header ────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="color:#58a6ff;margin-bottom:0;font-size:2rem;">ARIA v2</h1>'
    '<p style="color:#8b949e;font-size:0.9rem;margin-top:2px;">'
    'NammaYatri — Autonomous Reasoning &amp; Intelligence Agent &nbsp;·&nbsp; '
    'Zero Commission &nbsp;·&nbsp; Driver-first &nbsp;·&nbsp; Beckn/ONDC</p>',
    unsafe_allow_html=True,
)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_signal, tab_quadrant, tab_rice, tab_reqs, tab_metrics = st.tabs([
    "📡 Signal Feed",
    "📈 Impact Quadrant",
    "🎯 RICE Score",
    "📝 Requirements",
    "📊 Success Metrics",
])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — response rendering
# ══════════════════════════════════════════════════════════════════════════════

def _render_turn(data: dict, fallback: str):
    """Render one assistant chat turn with all v2 metadata badges."""
    tools_used  = data.get("tools_used", [])
    sources     = data.get("sources", [])
    consult     = data.get("consult", [])
    wtype       = data.get("workflow_type", "")
    pm_core     = data.get("pm_core", "")
    mf          = data.get("mission_filter", {})
    rice_top    = data.get("rice_top_score")
    quadrant    = data.get("quadrant")
    raw_answer  = data.get("answer", fallback) or fallback
    answer      = _extract_renderable_text(raw_answer)

    # ── Badge row ────────────────────────────────────────────────────────────
    badge_html = ""
    if wtype:
        badge_html += _workflow_badge(wtype) + "&nbsp; "
    if pm_core:
        badge_html += _pmcore_badge(pm_core) + "&nbsp; "

    mf_inner = mf.get("mission_filter", {}) if isinstance(mf, dict) else {}
    if mf_inner:
        for qlabel, qkey in [("Q1", "Q1_driver_welfare"), ("Q2", "Q2_rider_trust"),
                               ("Q3", "Q3_beckn_compliance"), ("Q4", "Q4_zero_commission")]:
            status = mf_inner.get(qkey, {}).get("status", "?")
            badge_html += _q_badge(qlabel, status) + " "

    if mf.get("community_consult_required"):
        badge_html += '&nbsp;<span class="badge-medium">⚠️ ARDU Consult</span>'

    if badge_html:
        st.markdown(badge_html, unsafe_allow_html=True)

    # ── RICE + Quadrant inline ───────────────────────────────────────────────
    if rice_top or quadrant:
        meta_parts = []
        if rice_top:
            meta_parts.append(f'<span class="badge-info">RICE: {rice_top}</span>')
        if quadrant:
            meta_parts.append(f'<span class="badge-purple">📈 {quadrant}</span>')
        st.markdown(" &nbsp;".join(meta_parts), unsafe_allow_html=True)

    # ── Tools + Sources ──────────────────────────────────────────────────────
    if tools_used:
        pills = "".join(f'<span class="tool-pill">{t.replace("_", " ")}</span>' for t in tools_used)
        with st.expander(f"🔧 Tools ({len(tools_used)})", expanded=False):
            st.markdown(pills, unsafe_allow_html=True)

    if sources:
        src_pills = "".join(f'<span class="src-pill">🔗 {s}</span>' for s in sources[:6])
        with st.expander(f"🌐 Sources ({len(sources)})", expanded=False):
            st.markdown(src_pills, unsafe_allow_html=True)

    # ── Consultation / block banners ─────────────────────────────────────────
    for flag_type, flag_reason in consult:
        if flag_type == "BLOCKED":
            st.markdown(
                f'<div class="block-banner">⛔ <strong>HARD BLOCK:</strong> {flag_reason}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="consult-banner">⚠️ <strong>ARDU Consultation Required:</strong> {flag_reason}</div>',
                unsafe_allow_html=True,
            )

    # ── Answer ───────────────────────────────────────────────────────────────
    st.markdown(f'<div class="answer-box">{answer}</div>', unsafe_allow_html=True)


def _build_pipeline_summary(raw: dict) -> tuple[str, dict]:
    """Build a human-readable summary from direct pipeline output + extract metadata."""
    wtype     = raw.get("workflow_type", "")
    steps     = raw.get("steps_planned", [])
    mf_parsed = {}
    pm_core   = ""
    rice_top  = None
    quadrant  = None
    consult   = []

    lines = [
        f"**Workflow:** `{wtype}` — {len(steps)} steps: {', '.join(steps)}\n",
        f"**Status:** All steps executed via direct pipeline (zero LLM tokens)\n",
    ]

    for tool_name, out in raw.items():
        if tool_name in ("workflow_type", "steps_planned"):
            continue
        parsed = _safe_json(out) or {}

        # Extract mission filter data
        if tool_name == "run_mission_filter" and parsed:
            mf_parsed = parsed
            pm_core   = parsed.get("pm_core_routing", parsed.get("pm_core", ""))
            st.session_state["last_mission_filter"] = parsed
            st.session_state["active_pm_core"]      = pm_core

        # Extract RICE top score
        if tool_name == "prioritize_with_rice" and parsed:
            st.session_state["rice_data"] = parsed
            ranked = parsed.get("ranked_features", [])
            if ranked:
                top = ranked[0]
                rice_top = top.get("rice_score")
                quadrant = top.get("impact_quadrant")

        # Extract quadrant data
        if tool_name == "generate_impact_quadrant" and parsed:
            st.session_state["quadrant_data"] = parsed

        # Extract PRD / Jira / experiment
        if tool_name == "generate_prd" and parsed:
            st.session_state["prd_data"] = parsed
        if tool_name == "create_jira_stories" and parsed:
            st.session_state["jira_data"] = parsed
        if tool_name == "generate_experiment_brief" and parsed:
            st.session_state["experiment_data"] = parsed
        if tool_name == "generate_stakeholder_brief" and parsed:
            st.session_state["stakeholder_data"] = parsed

        # Check consultation gate
        if tool_name == "check_consultation_gate" and parsed:
            if parsed.get("blocks_output"):
                consult.append(("BLOCKED", parsed.get("block_reason", "Zero-commission violation")))
            elif parsed.get("consultation_required"):
                consult.append(("REQUIRED", str(parsed.get("flags", []))))

        if str(out).startswith("❌") or str(out).startswith("Error"):
            lines.append(f"\n⚠️ **{tool_name.replace('_', ' ').title()}:** {str(out)[:300]}")
        else:
            lines.append(f"\n✅ **{tool_name.replace('_', ' ').title()}:** Completed")

    st.session_state["last_workflow_type"] = wtype

    meta = {
        "workflow_type":  wtype,
        "tools_used":     steps,
        "sources":        [],
        "consult":        consult,
        "mission_filter": mf_parsed,
        "pm_core":        pm_core,
        "rice_top_score": rice_top,
        "quadrant":       quadrant,
    }
    return "\n".join(lines), meta


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — SIGNAL FEED
# ══════════════════════════════════════════════════════════════════════════════
with tab_signal:

    # ── Welcome card ────────────────────────────────────────────────────────
    if not st.session_state.messages:
        breached = st.session_state["kpi_data"].get("breached_kpis", [])
        breach_count = len(breached)

        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#1c2333 0%,#161b22 100%);
                border:1px solid #21a1f1;border-radius:12px;padding:24px 28px;margin-bottom:20px;">
            <h2 style="color:#58a6ff;margin:0 0 6px 0;">👋 ARIA is ready</h2>
            <p style="color:#8b949e;margin:4px 0;font-size:0.88rem;">
                Auto-analysis complete ·
                <strong style="color:{'#f85149' if breach_count else '#3fb950'}">
                {breach_count} KPI{'s' if breach_count != 1 else ''} breached
                </strong>
                · 8 features RICE-scored
            </p><br/>
            <p style="color:#c9d1d9;margin:4px 0;font-size:0.85rem;">
                🚨 <strong>Signal Feed</strong> — paste in a KPI alert, feature request, or driver issue<br/>
                📈 <strong>Impact Quadrant</strong> — auto-populated 2×2 matrix (see tab above)<br/>
                🎯 <strong>RICE Score</strong> — ranked feature table with R·I·C·E breakdown<br/>
                📝 <strong>Requirements</strong> — PRD and Jira stories after running a workflow<br/>
                📊 <strong>Success Metrics</strong> — experiment brief and guardrails
            </p><br/>
            <p style="color:#8b949e;margin:0;font-size:0.82rem;">
                Use quick actions in the sidebar ← or type a signal below ↓
            </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Auto-detected alert cards
        if breached:
            st.markdown("#### 🚨 Auto-Detected Alerts")
            kpi_meta = st.session_state["kpi_data"].get("metrics", {})
            for b in breached[:3]:
                mv = kpi_meta.get(b, {})
                val = mv.get("value", "—") if isinstance(mv, dict) else mv
                thr = mv.get("threshold", "—") if isinstance(mv, dict) else "—"
                trend = mv.get("trend", "") if isinstance(mv, dict) else ""
                trend_icon = "↓" if trend in ("declining", "worsening") else ("↑" if trend == "improving" else "→")
                st.markdown(
                    f'<div class="insight-card insight-critical">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                    f'{_sev_badge("CRITICAL")}'
                    f'<strong style="color:#e6edf3;font-size:0.88rem;">{b.replace("_"," ").title()}</strong>'
                    f'</div>'
                    f'<p style="color:#8b949e;font-size:0.82rem;margin:0;">'
                    f'Value: <strong style="color:#f85149;">{val}</strong> · '
                    f'Threshold: {thr} · Trend: {trend_icon} {trend}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Chat history ─────────────────────────────────────────────────────────
    for turn in st.session_state.messages:
        if turn["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(turn["content"])
        else:
            with st.chat_message("assistant", avatar="🚌"):
                _render_turn(turn.get("data", {}), turn["content"])

    # ── Chat input ────────────────────────────────────────────────────────────
    user_input = st.chat_input("Type a KPI alert, feature request, or question for ARIA...")

    if st.session_state.pending_input and not user_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = ""

    if user_input:
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})

        from src.agent import detect_workflow_type, get_workflow_steps

        wtype = detect_workflow_type(user_input)

        with st.chat_message("assistant", avatar="🚌"):

            if wtype == "GENERAL":
                # ── Conversational Q&A via LLM agent ─────────────────────────
                from src.agent import get_llm_config_signature, run_agent

                sig = get_llm_config_signature()
                if st.session_state.agent_llm_signature != sig:
                    st.session_state.agent = None
                    st.session_state.agent_llm_signature = sig

                if st.session_state.agent is None:
                    with st.spinner("Loading ARIA agent..."):
                        try:
                            st.session_state.agent = _load_agent(sig)
                        except Exception as e:
                            st.error(f"Failed to load agent: {e}")
                            st.stop()

                with st.spinner("ARIA is thinking..."):
                    try:
                        result = run_agent(st.session_state.agent, user_input)
                        result["consult"] = []
                        result["workflow_type"] = "GENERAL"
                    except Exception as e:
                        result = {
                            "answer":        f"LLM error: {e}",
                            "tools_used":    [],
                            "sources":       [],
                            "consult":       [],
                            "workflow_type": "GENERAL",
                        }

                _render_turn(result, result.get("answer", ""))

            else:
                # ── Direct pipeline — zero LLM ────────────────────────────────
                from src.agent import get_workflow_steps, run_direct_pipeline

                steps = get_workflow_steps(wtype)
                st.markdown(f'🔄 Running **{wtype}** — {len(steps)} steps (zero LLM)')

                placeholders = {}
                for i, (_, sname) in enumerate(steps, start=1):
                    placeholders[i] = st.empty()
                    placeholders[i].markdown(
                        f'<div style="background:#1c2333;border:1px solid #30363d;border-radius:6px;'
                        f'padding:8px 12px;margin:2px 0;color:#8b949e;font-size:0.82rem;">'
                        f'⏳ Step {i}: {sname}</div>',
                        unsafe_allow_html=True,
                    )

                def _step_done(num, name, output, wf_type=None):
                    is_err = str(output).strip().startswith(("❌", "Error", "No direct"))
                    col  = "#f85149" if is_err else "#3fb950"
                    icon = "❌" if is_err else "✅"
                    bg   = "#2d0a0a" if is_err else "#0a1f0a"
                    placeholders[num].markdown(
                        f'<div style="background:{bg};border:1px solid {col};border-radius:6px;'
                        f'padding:8px 12px;margin:2px 0;color:{col};font-size:0.82rem;">'
                        f'{icon} Step {num}: {name}</div>',
                        unsafe_allow_html=True,
                    )

                with st.spinner("Executing pipeline..."):
                    raw = run_direct_pipeline(user_input, step_callback=_step_done)

                answer, meta = _build_pipeline_summary(raw)
                meta["answer"] = answer

                st.markdown("---")
                _render_turn(meta, answer)
                result = meta

            st.session_state.messages.append({
                "role":    "assistant",
                "content": result.get("answer", ""),
                "data":    result,
            })


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — IMPACT QUADRANT
# ══════════════════════════════════════════════════════════════════════════════
with tab_quadrant:
    st.markdown("### 📈 Impact Quadrant")
    st.caption("2×2 matrix: Impact vs Effort. Auto-populated from RICE analysis.")

    rice_data = st.session_state.get("rice_data", {})
    iq = rice_data.get("impact_quadrant", {})

    quick_wins  = iq.get("quick_wins",        [])
    major_bets  = iq.get("major_bets",         [])
    low_hanging = iq.get("low_hanging_fruit",  [])
    deprio      = iq.get("deprioritise",        [])

    if not any([quick_wins, major_bets, low_hanging, deprio]):
        st.info("No quadrant data yet. Click **🔄 Refresh Analysis** in the sidebar or run a workflow.")
    else:
        def _feature_card(f: dict, priority_color: str) -> str:
            title      = f.get("title", "")
            rice       = f.get("rice_score", "—")
            prio       = f.get("nammayatri_priority", "")
            rice_cfg   = f.get("rice", {})
            r_val      = rice_cfg.get("reach", "?")
            i_val      = rice_cfg.get("impact", "?")
            c_val      = rice_cfg.get("confidence", "?")
            e_val      = rice_cfg.get("effort", "?")
            return (
                f'<div class="feature-card">'
                f'<div class="feature-card-title">{title}</div>'
                f'<div style="display:flex;gap:6px;align-items:center;">'
                f'<span class="rice-score">RICE: {rice}</span>'
                f'<span class="badge-info" style="font-size:0.7rem;">{prio}</span>'
                f'</div>'
                f'<div style="color:#8b949e;font-size:0.72rem;margin-top:4px;">'
                f'R:{r_val} · I:{i_val} · C:{c_val} · E:{e_val}</div>'
                f'</div>'
            )

        # Row 1: Quick Wins | Major Bets
        col_qw, col_mb = st.columns(2)

        with col_qw:
            st.markdown(
                '<div class="quadrant-qw">'
                '<div class="quadrant-title" style="color:#3fb950;">⚡ Quick Wins</div>'
                '<div style="color:#8b949e;font-size:0.75rem;margin-bottom:10px;">High Impact · Low Effort — Ship first</div>',
                unsafe_allow_html=True,
            )
            if quick_wins:
                for f in quick_wins[:4]:
                    st.markdown(_feature_card(f, "#3fb950"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#8b949e;font-size:0.82rem;">No features here</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_mb:
            st.markdown(
                '<div class="quadrant-mb">'
                '<div class="quadrant-title" style="color:#58a6ff;">🎯 Major Bets</div>'
                '<div style="color:#8b949e;font-size:0.75rem;margin-bottom:10px;">High Impact · High Effort — Plan carefully</div>',
                unsafe_allow_html=True,
            )
            if major_bets:
                for f in major_bets[:4]:
                    st.markdown(_feature_card(f, "#58a6ff"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#8b949e;font-size:0.82rem;">No features here</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)

        # Row 2: Low-hanging Fruit | Deprioritise
        col_lhf, col_dp = st.columns(2)

        with col_lhf:
            st.markdown(
                '<div class="quadrant-lhf">'
                '<div class="quadrant-title" style="color:#d29922;">🍋 Low-hanging Fruit</div>'
                '<div style="color:#8b949e;font-size:0.75rem;margin-bottom:10px;">Low Impact · Low Effort — Ship if bandwidth</div>',
                unsafe_allow_html=True,
            )
            if low_hanging:
                for f in low_hanging[:4]:
                    st.markdown(_feature_card(f, "#d29922"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#8b949e;font-size:0.82rem;">No features here</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_dp:
            st.markdown(
                '<div class="quadrant-dp">'
                '<div class="quadrant-title" style="color:#bc8cff;">🗑️ Deprioritise</div>'
                '<div style="color:#8b949e;font-size:0.75rem;margin-bottom:10px;">Low Impact · High Effort — Kill or defer</div>',
                unsafe_allow_html=True,
            )
            if deprio:
                for f in deprio[:4]:
                    st.markdown(_feature_card(f, "#bc8cff"), unsafe_allow_html=True)
            else:
                st.markdown('<p style="color:#8b949e;font-size:0.82rem;">No features here</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # Top 3 recommendations from quadrant analysis
        quad_analysis = st.session_state.get("quadrant_data", {})
        top3 = quad_analysis.get("top_3_recommendations", [])
        if top3:
            st.markdown("---")
            st.markdown("#### 🏆 Top 3 Recommendations")
            for rec in top3:
                rank    = rec.get("rank", "")
                feature = rec.get("feature", "")
                rice    = rec.get("rice", "")
                prio    = rec.get("priority", "")
                quad    = rec.get("quadrant", "")
                prio_cls = {"P0": "badge-critical", "P1": "badge-high",
                             "P2": "badge-medium", "P3": "badge-low"}.get(prio, "badge-info")
                st.markdown(
                    f'<div class="aria-card">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
                    f'<span style="color:#58a6ff;font-size:1rem;font-weight:800;">#{rank}</span>'
                    f'<strong style="color:#e6edf3;">{feature}</strong>'
                    f'</div>'
                    f'<div style="display:flex;gap:8px;">'
                    f'<span class="badge-info">RICE: {rice}</span>'
                    f'<span class="{prio_cls}">{prio}</span>'
                    f'<span class="badge-purple">{quad}</span>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — RICE SCORE
# ══════════════════════════════════════════════════════════════════════════════
with tab_rice:
    st.markdown("### 🎯 RICE Score")
    st.caption("Ranked features: RICE = (Reach × Impact × Confidence) / Effort")

    rice_data  = st.session_state.get("rice_data", {})
    ranked     = rice_data.get("ranked_features", [])
    top_rec    = rice_data.get("top_recommendation")

    if not ranked:
        st.info("No RICE data yet. Click **🔄 Refresh Analysis** or run an Impact Analysis workflow.")
    else:
        if top_rec:
            st.markdown(
                f'<div style="background:#0a1a0d;border:2px solid #3fb950;border-radius:10px;'
                f'padding:14px 18px;margin-bottom:16px;">'
                f'<span style="color:#3fb950;font-weight:700;">🏆 Top Recommendation: </span>'
                f'<span style="color:#e6edf3;">{top_rec.get("title", "")} </span>'
                f'<span class="badge-info" style="margin-left:6px;">RICE: {top_rec.get("rice_score", "")}</span>'
                f'<span class="badge-purple" style="margin-left:4px;">{top_rec.get("impact_quadrant", "")}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        import pandas as pd

        rows = []
        for i, f in enumerate(ranked, start=1):
            r_cfg = f.get("rice", {})
            rows.append({
                "Rank":       i,
                "Feature":    f.get("title", ""),
                "RICE":       f.get("rice_score", ""),
                "Priority":   f.get("nammayatri_priority", ""),
                "Quadrant":   f.get("impact_quadrant", ""),
                "Reach":      r_cfg.get("reach", ""),
                "Impact":     r_cfg.get("impact", ""),
                "Confidence": r_cfg.get("confidence", ""),
                "Effort":     r_cfg.get("effort", ""),
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "RICE":       st.column_config.NumberColumn(format="%.1f"),
                "Reach":      st.column_config.NumberColumn(format="%d"),
                "Impact":     st.column_config.NumberColumn(format="%d"),
                "Confidence": st.column_config.NumberColumn(format="%d"),
                "Effort":     st.column_config.NumberColumn(format="%d"),
            },
        )

        st.markdown(
            f'<div style="color:#8b949e;font-size:0.78rem;margin-top:8px;">'
            f'📐 {rice_data.get("rice_methodology", "RICE = (Reach × Impact × Confidence) / Effort · Scale 1–10")}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — REQUIREMENTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_reqs:
    st.markdown("### 📝 Requirements")
    st.caption("PRD and Jira stories from the last Feature Request or Full Workflow run.")

    prd_data  = st.session_state.get("prd_data", {})
    jira_data = st.session_state.get("jira_data", {})

    if not prd_data and not jira_data:
        st.info(
            "No requirements generated yet. Run a **Feature Request** workflow to populate this tab.\n\n"
            "Example: *'Build a PRD for Scheduled Rides feature'*"
        )
    else:
        col_prd, col_jira = st.columns(2)

        with col_prd:
            st.markdown("#### 📋 PRD")
            prd = prd_data.get("prd", prd_data)
            if prd:
                feature_name = prd.get("feature_name", "Feature")
                st.markdown(
                    f'<div style="background:#1c2333;border:1px solid #58a6ff;border-radius:8px;padding:14px 18px;">'
                    f'<h4 style="color:#58a6ff;margin:0 0 8px 0;">{feature_name}</h4>',
                    unsafe_allow_html=True,
                )
                _prd_fields = [
                    ("Problem Statement", "problem"),
                    ("Solution",          "solution"),
                    ("Priority",          "priority"),
                    ("Timeline",          "timeline"),
                ]
                for label, key in _prd_fields:
                    val = prd.get(key)
                    if val:
                        st.markdown(
                            f'<p style="color:#8b949e;font-size:0.78rem;margin:4px 0 0 0;">{label}</p>'
                            f'<p style="color:#c9d1d9;font-size:0.85rem;margin:2px 0 8px 0;">{val}</p>',
                            unsafe_allow_html=True,
                        )
                st.markdown('</div>', unsafe_allow_html=True)

                # Functional requirements
                func_reqs = prd.get("functional_requirements", [])
                if func_reqs:
                    with st.expander("📌 Functional Requirements", expanded=False):
                        for req in func_reqs:
                            st.markdown(f"- {req}")

                # Success metrics
                success_metrics = prd.get("success_metrics", {})
                if success_metrics:
                    with st.expander("📊 Success Metrics", expanded=False):
                        if isinstance(success_metrics, dict):
                            for label, val in success_metrics.items():
                                st.markdown(f"**{label.replace('_', ' ').title()}:** {val}")
                        elif isinstance(success_metrics, list):
                            for item in success_metrics:
                                st.markdown(f"- {item}")

                # Consultation flags
                if prd.get("consultation_required"):
                    flags = prd.get("consultation_flags", [])
                    st.markdown(
                        f'<div class="consult-banner">⚠️ <strong>ARDU Consultation Required</strong><br>'
                        f'{"<br>".join(str(f) for f in flags) if flags else "Driver community consultation needed"}</div>',
                        unsafe_allow_html=True,
                    )

                with st.expander("🔍 Full PRD JSON", expanded=False):
                    st.json(prd_data)

            else:
                st.info("No PRD data available.")

        with col_jira:
            st.markdown("#### 🎫 Jira Stories")
            if jira_data:
                epic     = jira_data.get("epic", "EPIC")
                stories  = jira_data.get("stories", [])
                total_sp = jira_data.get("total_story_points", 0)
                sprints  = jira_data.get("estimated_sprints", 0)

                st.markdown(
                    f'<div style="background:#1c2333;border:1px solid #30363d;border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:10px;">'
                    f'<strong style="color:#58a6ff;">{epic}</strong><br/>'
                    f'<span style="color:#8b949e;font-size:0.78rem;">'
                    f'{len(stories)} stories · {total_sp} SP · ~{sprints} sprints</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for story in stories:
                    sid   = story.get("id", "")
                    title = story.get("title", "")
                    sp    = story.get("story_points", "")
                    owner = story.get("owner", "")
                    prio  = story.get("priority", "")
                    prio_cls = {"P0": "badge-critical", "P1": "badge-high",
                                 "P2": "badge-medium", "P3": "badge-low"}.get(prio, "badge-info")
                    with st.expander(f"{sid} — {title[:55]}", expanded=False):
                        st.markdown(
                            f'<span class="{prio_cls}">{prio}</span>'
                            f'<span class="badge-info" style="margin-left:6px;">{sp} SP</span>'
                            f'<span style="color:#8b949e;font-size:0.78rem;margin-left:8px;">Owner: {owner}</span>',
                            unsafe_allow_html=True,
                        )
                        ac = story.get("acceptance_criteria", [])
                        if ac:
                            st.markdown("**Acceptance Criteria:**")
                            for c in ac:
                                st.markdown(f"- {c}")
                        labels = story.get("github_labels", [])
                        if labels:
                            label_pills = "".join(f'<span class="tool-pill">{l}</span>' for l in labels)
                            st.markdown(label_pills, unsafe_allow_html=True)

                with st.expander("🔍 Full Jira JSON", expanded=False):
                    st.json(jira_data)
            else:
                st.info("No Jira stories available.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — SUCCESS METRICS
# ══════════════════════════════════════════════════════════════════════════════
with tab_metrics:
    st.markdown("### 📊 Success Metrics")
    st.caption("Experiment brief, guardrails, and KPI targets from the last workflow.")

    exp_data         = st.session_state.get("experiment_data", {})
    stakeholder_data = st.session_state.get("stakeholder_data", {})

    if not exp_data and not stakeholder_data:
        st.info(
            "No experiment data yet. Run a **Full Workflow** or **Feature Request** workflow to populate this tab."
        )
    else:
        if exp_data:
            brief = exp_data.get("experiment_brief", exp_data)
            st.markdown("#### 🔬 Experiment Brief")

            feature = brief.get("feature", "Feature")
            hypo    = brief.get("hypothesis", "")

            st.markdown(
                f'<div style="background:#1c2333;border:1px solid #58a6ff;border-radius:8px;'
                f'padding:14px 18px;margin-bottom:14px;">'
                f'<h4 style="color:#58a6ff;margin:0 0 8px 0;">{feature}</h4>'
                f'<p style="color:#c9d1d9;font-size:0.85rem;margin:0;">{hypo}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            col_e1, col_e2 = st.columns(2)
            with col_e1:
                # Sample size
                sample = brief.get("sample_size", {})
                if sample:
                    st.markdown("**📏 Sample Size**")
                    for k, v in sample.items():
                        st.markdown(
                            f'<p style="color:#8b949e;font-size:0.78rem;margin:2px 0 0 0;">{k.replace("_", " ").title()}</p>'
                            f'<p style="color:#c9d1d9;font-size:0.83rem;margin:0 0 6px 0;">{v}</p>',
                            unsafe_allow_html=True,
                        )

                # Success metrics
                success = brief.get("success_metrics", {})
                if success:
                    st.markdown("**🎯 Success Metrics**")
                    primary = success.get("primary", "")
                    if primary:
                        st.markdown(
                            f'<div class="aria-card" style="border-color:#3fb950;">'
                            f'<p style="color:#3fb950;font-weight:700;margin:0;">PRIMARY: {primary}</p>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    secondary = success.get("secondary", [])
                    for s in secondary:
                        st.markdown(f"- {s}")

            with col_e2:
                # Guardrails
                guardrails = brief.get("guardrails", [])
                if guardrails:
                    st.markdown("**🛡️ Guardrails**")
                    for g in guardrails:
                        st.markdown(
                            f'<div style="background:#1c2333;border-left:3px solid #f85149;'
                            f'border-radius:4px;padding:6px 10px;margin-bottom:6px;'
                            f'color:#c9d1d9;font-size:0.82rem;">{g}</div>',
                            unsafe_allow_html=True,
                        )

                # Mission filter pre-check
                mf_check = brief.get("mission_filter_pre_check", {})
                if mf_check:
                    st.markdown("**✅ Mission Filter Pre-Check**")
                    for k, v in mf_check.items():
                        icon = "✅" if v is True else ("⚠️" if isinstance(v, str) else "❌")
                        label = k.replace("_", " ").title()
                        val_str = v if isinstance(v, str) else ("PASS" if v else "FAIL")
                        st.markdown(
                            f'<div style="display:flex;gap:6px;align-items:center;padding:3px 0;">'
                            f'<span>{icon}</span>'
                            f'<span style="color:#8b949e;font-size:0.8rem;">{label}:</span>'
                            f'<span style="color:#c9d1d9;font-size:0.8rem;">{val_str}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Rollback plan
                rollback = brief.get("rollback_plan", "")
                if rollback:
                    st.markdown(
                        f'<div class="consult-banner" style="margin-top:12px;">'
                        f'🔙 <strong>Rollback Plan:</strong> {rollback}</div>',
                        unsafe_allow_html=True,
                    )

            with st.expander("🔍 Full Experiment Brief JSON", expanded=False):
                st.json(exp_data)

        if stakeholder_data:
            st.markdown("---")
            st.markdown("#### 📋 Stakeholder Brief")
            brief_text = stakeholder_data.get("brief", stakeholder_data)
            if isinstance(brief_text, str):
                st.markdown(
                    f'<div class="answer-box">{brief_text}</div>',
                    unsafe_allow_html=True,
                )
            else:
                audience = stakeholder_data.get("audience", "")
                feature  = stakeholder_data.get("feature_name", "")
                if feature:
                    st.markdown(f"**Audience:** {audience} &nbsp;|&nbsp; **Feature:** {feature}")
                with st.expander("View Stakeholder Brief", expanded=True):
                    st.json(stakeholder_data)

    # ── KPI Targets (from roadmap if available) ───────────────────────────────
    st.markdown("---")
    st.markdown("#### 📌 KPI Targets vs Baseline")

    kpi_targets = [
        ("Ride Completion Rate",     "71%",    "80%",   "85%"),
        ("Driver Cancellation Rate", "18%",    "< 8%",  "< 5%"),
        ("Avg Wait Time",            "8.3 min","5 min", "4 min"),
        ("Driver Retention D30",     "58%",    "70%",   "75%"),
        ("App Store Rating",         "3.8★",   "4.2★",  "4.5★"),
    ]

    import pandas as pd
    df_kpi = pd.DataFrame(kpi_targets, columns=["Metric", "Baseline", "Target", "Stretch"])
    st.dataframe(df_kpi, use_container_width=True, hide_index=True)
