"""
app.py — ARIA Streamlit UI for Namma Yatri AI Product Manager
Multi-tab: PM Copilot | Insights Dashboard | Decision Board | Learning Loop
"""

import os
import re
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

import streamlit as st

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="ARIA — Namma Yatri PM Agent",
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

    .aria-card {
        background: #1c2333; border: 1px solid #30363d;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
    }
    .aria-card h4 { color: #58a6ff; margin: 0 0 8px 0; }
    .aria-card p  { color: #c9d1d9; margin: 0; font-size: 0.9rem; }

    .answer-box {
        background: #1c2333; border-left: 4px solid #58a6ff;
        border-radius: 8px; padding: 20px 24px; margin-top: 12px;
        color: #e6edf3; line-height: 1.7;
    }

    .badge-critical { background:#3d0a0a; color:#ff4444; border:1px solid #ff4444; border-radius:12px; padding:2px 10px; font-size:0.8rem; font-weight:700; }
    .badge-high     { background:#3d1212; color:#f85149; border:1px solid #f85149; border-radius:12px; padding:2px 10px; font-size:0.8rem; font-weight:600; }
    .badge-medium   { background:#3d2b0a; color:#d29922; border:1px solid #d29922; border-radius:12px; padding:2px 10px; font-size:0.8rem; font-weight:600; }
    .badge-low      { background:#1a4a2e; color:#3fb950; border:1px solid #3fb950; border-radius:12px; padding:2px 10px; font-size:0.8rem; font-weight:600; }
    .badge-blocked  { background:#2d0a3d; color:#bc8cff; border:1px solid #bc8cff; border-radius:12px; padding:3px 12px; font-size:0.85rem; font-weight:700; }

    .stButton > button {
        width: 100%; background: #1c2333; border: 1px solid #30363d;
        color: #c9d1d9; border-radius: 8px; padding: 10px;
        text-align: left; transition: all 0.2s; margin-bottom: 4px;
    }
    .stButton > button:hover { background: #21262d; border-color: #58a6ff; color: #58a6ff; }

    .tool-pill {
        display: inline-block; background: #1f2d3d; color: #58a6ff;
        border: 1px solid #1f6feb; border-radius: 20px; padding: 2px 10px;
        font-size: 0.78rem; margin: 2px 4px 2px 0;
    }
    .src-pill {
        display: inline-block; background: #1a2d1e; color: #3fb950;
        border: 1px solid #3fb950; border-radius: 20px; padding: 2px 10px;
        font-size: 0.78rem; margin: 2px 4px 2px 0; word-break: break-all;
    }
    .consult-banner {
        background: #2d1f00; border: 2px solid #d29922; border-radius: 8px;
        padding: 12px 16px; margin: 8px 0; color: #d29922;
    }
    .block-banner {
        background: #2d0a0a; border: 2px solid #f85149; border-radius: 8px;
        padding: 12px 16px; margin: 8px 0; color: #f85149;
    }
    .kpi-card {
        background: #1c2333; border: 1px solid #30363d; border-radius: 10px;
        padding: 18px; text-align: center;
    }
    .kpi-label { color: #8b949e; font-size: 0.8rem; margin-bottom: 4px; }
    .kpi-value { color: #e6edf3; font-size: 1.8rem; font-weight: 700; }
    .kpi-breached { color: #f85149 !important; }
    .kpi-healthy  { color: #3fb950 !important; }
    .insight-card {
        background: #1c2333; border-left: 4px solid; border-radius: 8px;
        padding: 14px 18px; margin-bottom: 10px;
    }
    .insight-critical { border-color: #ff4444; }
    .insight-high     { border-color: #f85149; }
    .insight-medium   { border-color: #d29922; }
    .insight-low      { border-color: #3fb950; }
    .weight-bar-bg { background:#21262d; border-radius:6px; height:14px; width:100%; }
    .weight-bar-fill { background:#58a6ff; border-radius:6px; height:14px; }

    hr { border-color: #30363d; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Session state ──────────────────────────────────────────────────────────────
_defaults = {
    "messages":      [],
    "agent":         None,
    "pending_input": "",
    "run_workflow":  False,
    "active_tab":    0,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Cached helpers ─────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def load_agent(_llm_signature: str):
    from src.agent import build_agent
    return build_agent()


def _safe_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


def detect_confidence(text) -> str:
    if isinstance(text, list):
        normalized = " ".join(str(item) for item in text)
    elif isinstance(text, str):
        normalized = text
    else:
        normalized = str(text)

    tl = normalized.lower()
    if any(s in tl for s in ["high confidence", "multiple sources", "verified", "confirmed"]):
        return "High"
    if any(s in tl for s in ["low confidence", "uncertain", "unclear", "no data"]):
        return "Low"
    return "Medium"


def _extract_renderable_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]))
                elif "text" in item and item["text"]:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)

    if isinstance(content, dict):
        if content.get("type") == "text" and content.get("text"):
            return str(content["text"])
        if "text" in content and content["text"]:
            return str(content["text"])

    return str(content)


def get_data_status():
    data_dir = Path("data")
    if not data_dir.exists():
        return 0, []
    files = [f for f in data_dir.iterdir() if f.suffix in {".txt", ".md", ".pdf"}]
    return len(files), [f.name for f in files]


def _severity_color(sev: str) -> str:
    return {
        "CRITICAL": "#ff4444",
        "HIGH":     "#f85149",
        "MEDIUM":   "#d29922",
        "LOW":      "#3fb950",
    }.get(sev.upper(), "#58a6ff")


def _severity_badge(sev: str) -> str:
    cls = {"CRITICAL": "badge-critical", "HIGH": "badge-high",
           "MEDIUM": "badge-medium", "LOW": "badge-low"}.get(sev.upper(), "badge-low")
    return f'<span class="{cls}">{sev}</span>'


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-size:1.4rem;font-weight:700;color:#58a6ff;">🚌 ARIA</div>'
        '<div style="font-size:0.85rem;color:#8b949e;margin-bottom:20px;">Namma Yatri PM Agent</div>',
        unsafe_allow_html=True,
    )

    if st.button("▶️ Start Full PM Workflow", use_container_width=True, type="primary"):
        st.session_state.run_workflow = True
        st.session_state.active_tab  = 0
        st.rerun()

    st.markdown("---")
    st.markdown("**⚡ Quick Actions**")

    quick_actions = {
        "🔍 Find Pain Points": (
            "Search for the top pain points and complaints from Namma Yatri users and drivers. "
            "Analyze the data and give me a structured pain point report with confidence levels."
        ),
        "📊 Check KPIs + Insights": (
            "Check current KPI metrics for Namma Yatri, synthesize PM insights from the data, "
            "and run root cause analysis on the top breached KPI."
        ),
        "📝 Generate PRD": (
            "Generate a detailed PRD for a 'Scheduled Rides' feature for Namma Yatri. "
            "Problem: users miss Ola/Uber for advance bookings (e.g., 4am airport rides). "
            "Solution: allow booking up to 24 hours in advance. "
            "Success metric: 15%% of all rides become scheduled within 3 months."
        ),
        "📅 Q3 2026 Roadmap": (
            "Generate a product roadmap for Q3 2026 with theme: "
            "'Driver Retention & Earnings Optimization' for Namma Yatri."
        ),
        "🎫 Create Jira Stories": (
            "Create Jira user stories for a 'Scheduled Rides' feature: "
            "advance booking UI, driver acceptance flow, reminder notifications, "
            "cancellation policy, payment hold."
        ),
        "🔬 RCA: Cancellation Rate": (
            "Driver cancellation rate has breached 18%%. "
            "Run a root cause analysis, AI-prioritize the top issues, "
            "and recommend a prioritized fix plan."
        ),
        "📈 Learning State": (
            "Show me the current learning state: which factors are weighted higher or lower, "
            "what decisions have been logged, and what the overall learning health is."
        ),
    }

    for label, prompt in quick_actions.items():
        if st.button(label, key=f"qa_{label}"):
            st.session_state.pending_input = prompt
            st.session_state.active_tab    = 0
            st.rerun()

    st.markdown("---")
    n_files, file_names = get_data_status()
    st.markdown("**📁 Knowledge Base**")
    if n_files == 0:
        st.warning("No documents indexed.\nAdd files to `data/` and run:\n```\npython store_index.py\n```")
    else:
        st.success(f"{n_files} document(s) indexed")
        with st.expander("View files"):
            for fn in file_names:
                st.markdown(f"- `{fn}`")

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.markdown(
        '<div style="color:#8b949e;font-size:0.75rem;margin-top:16px;">'
        'Powered by Groq · LangGraph · Pinecone<br>Built for Namma Yatri</div>',
        unsafe_allow_html=True,
    )


# ── Render helper — defined before tabs so all tab blocks can call it ──────────
def _render_assistant_turn(data: dict, fallback_content: str):
    """Render a single assistant turn: tools, sources, consultation banners, answer."""
    tools_used = data.get("tools_used", [])
    sources    = data.get("sources", [])
    consult    = data.get("consult", [])
    raw_answer = data.get("answer", fallback_content) or fallback_content
    answer     = _extract_renderable_text(raw_answer)

    if tools_used:
        with st.expander(f"🔧 Tools Used ({len(tools_used)})", expanded=False):
            pills = "".join(
                f'<span class="tool-pill">{t.replace("_"," ")}</span>' for t in tools_used
            )
            st.markdown(pills, unsafe_allow_html=True)

    if sources:
        with st.expander(f"🌐 Sources ({len(sources)})", expanded=False):
            for s in sources:
                st.markdown(f'<span class="src-pill">🔗 {s}</span>', unsafe_allow_html=True)

    for flag_type, flag_reason in consult:
        if flag_type == "BLOCKED":
            st.markdown(
                f'<div class="block-banner">⛔ <strong>HARD BLOCK:</strong> {flag_reason}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="consult-banner">⚠️ <strong>Consultation Required:</strong> {flag_reason}</div>',
                unsafe_allow_html=True,
            )

    conf = detect_confidence(answer)
    badge_cls = {"High": "badge-low", "Medium": "badge-medium", "Low": "badge-high"}[conf]
    st.markdown(
        f'📊 Confidence: <span class="{badge_cls}">{conf}</span>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="answer-box">{answer}</div>',
        unsafe_allow_html=True,
    )


# ── Page header ────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="color:#58a6ff;margin-bottom:2px;">ARIA</h1>'
    '<p style="color:#8b949e;font-size:1rem;margin-top:0;">'
    'Namma Yatri — Autonomous Reasoning &amp; Intelligence Agent</p>',
    unsafe_allow_html=True,
)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_labels = ["💬 PM Copilot", "📊 Insights Dashboard", "📋 Decision Board", "📈 Learning Loop"]
tabs = st.tabs(tab_labels)
tab_copilot, tab_insights, tab_decisions, tab_learning = tabs


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PM COPILOT
# ══════════════════════════════════════════════════════════════════════════════
with tab_copilot:

    # Full PM Workflow run
    if st.session_state.get("run_workflow"):
        st.session_state.run_workflow = False
        st.markdown("## 🤖 Full PM Workflow Running...")

        workflow_steps = [
            "📋 Reading GitHub Issues",
            "🔍 Analyzing Pain Points",
            "📊 Checking KPI Metrics",
            "🧠 Synthesizing PM Insights",
            "🔬 Running Root Cause Analysis",
            "🎯 AI-Driven Prioritization",
            "🛡️ Consultation & Compliance Gate",
            "💡 Generating Solution",
            "📝 Writing PRD",
            "🎫 Creating Jira Stories",
            "🗺️ Generating Roadmap",
        ]
        placeholders = {}
        for i, name in enumerate(workflow_steps):
            placeholders[i + 1] = st.empty()
            placeholders[i + 1].markdown(
                f'<div style="background:#1c2333;border:1px solid #30363d;border-radius:8px;'
                f'padding:10px 14px;margin:3px 0;color:#8b949e;">⏳ Step {i+1}: {name}</div>',
                unsafe_allow_html=True,
            )

        workflow_results: dict = {}

        def _wf_step_done(step_num, step_name, result, wf_type=None):
            is_err = str(result).strip().startswith(("❌", "Error"))
            col = "#f85149" if is_err else "#3fb950"
            icon = "❌" if is_err else "✅"
            bg   = "#3d1212" if is_err else "#1a4a2e"
            placeholders[step_num].markdown(
                f'<div style="background:{bg};border:1px solid {col};border-radius:8px;'
                f'padding:10px 14px;margin:3px 0;color:{col};">'
                f'{icon} Step {step_num}: {step_name}</div>',
                unsafe_allow_html=True,
            )
            workflow_results[step_num] = result

        from src.agent import get_llm_config_signature
        llm_signature = get_llm_config_signature()
        if st.session_state.get("agent_llm_signature") != llm_signature:
            st.session_state.agent = None
            st.session_state.agent_llm_signature = llm_signature

        if st.session_state.agent is None:
            with st.spinner("Loading ARIA agent..."):
                try:
                    st.session_state.agent = load_agent(llm_signature)
                except Exception as e:
                    st.error(f"Failed to load agent: {e}")
                    st.stop()

        from src.agent import run_workflow as _run_wf
        wf_output = _run_wf(st.session_state.agent, step_callback=_wf_step_done)

        st.markdown("---")
        st.success("✅ Full PM Workflow Complete!")

        for tool_name, output in wf_output.items():
            if tool_name in ("workflow_type", "steps_planned"):
                continue
            with st.expander(f"🔧 {tool_name.replace('_', ' ').title()}", expanded=False):
                parsed = _safe_json(output)
                if parsed:
                    st.json(parsed)
                else:
                    st.markdown(output)

        st.session_state.messages.append({
            "role": "assistant",
            "content": "Full PM Workflow completed — 11 steps executed autonomously.",
            "data": {"tools_used": wf_output.get("steps_planned", []), "sources": [],
                     "raw": wf_output},
        })

    # Welcome card
    if not st.session_state.messages:
        st.markdown(
            """
            <div style="background:linear-gradient(135deg,#1c2333 0%,#161b22 100%);
                border:1px solid #21a1f1;border-radius:12px;padding:24px 28px;margin-bottom:24px;">
            <h2 style="color:#58a6ff;margin:0 0 8px 0;">👋 Hi, I'm ARIA</h2>
            <p style="color:#8b949e;margin:4px 0;font-size:0.9rem;">
                Your AI Product Manager for <strong style="color:#58a6ff;">Namma Yatri</strong>.
            </p><br/>
            <p style="color:#8b949e;margin:4px 0;font-size:0.9rem;">
                🧠 <strong>I synthesize</strong> KPI data into typed PM insights with severity scores<br/>
                🔬 <strong>I analyze</strong> root causes with multi-hypothesis reasoning<br/>
                🎯 <strong>I prioritize</strong> using AI scoring — not just ICE formula<br/>
                🛡️ <strong>I gate</strong> every artifact through consultation & compliance checks<br/>
                📈 <strong>I learn</strong> from outcome feedback and adjust my weights over time
            </p><br/>
            <p style="color:#8b949e;margin:0;font-size:0.85rem;">
                Use quick actions in the sidebar or type your question below ↓
            </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Chat history
    for turn in st.session_state.messages:
        if turn["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(turn["content"])
        else:
            with st.chat_message("assistant", avatar="🚌"):
                data = turn.get("data", {})
                _render_assistant_turn(data, turn["content"])

    # Chat input
    user_input = st.chat_input("Ask ARIA about Namma Yatri product strategy...")

    if st.session_state.pending_input and not user_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = ""

    if user_input:
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})

        from src.agent import get_llm_config_signature
        llm_signature = get_llm_config_signature()
        if st.session_state.get("agent_llm_signature") != llm_signature:
            st.session_state.agent = None
            st.session_state.agent_llm_signature = llm_signature

        if st.session_state.agent is None:
            with st.spinner("Loading ARIA agent..."):
                try:
                    st.session_state.agent = load_agent(llm_signature)
                except Exception as e:
                    st.error(f"Failed to load agent: {e}")
                    st.stop()

        with st.chat_message("assistant", avatar="🚌"):
            with st.spinner("ARIA is researching..."):
                try:
                    from src.agent import run_smart_workflow, detect_workflow_type, run_agent
                    wtype = detect_workflow_type(user_input)

                    if wtype in ("INCIDENT", "FEATURE", "EXPLORATION", "FULL_WORKFLOW", "LEARNING_QUERY"):
                        raw = run_smart_workflow(st.session_state.agent, user_input)
                        # Build readable answer from all step outputs
                        lines = [f"**Workflow:** `{raw.get('workflow_type')}` — "
                                 f"steps: {', '.join(raw.get('steps_planned', []))}\n"]
                        consultation_flags = []
                        for tool, out in raw.items():
                            if tool in ("workflow_type", "steps_planned"):
                                continue
                            parsed = _safe_json(out)
                            if tool == "check_consultation_gate" and parsed:
                                if parsed.get("blocks_output"):
                                    consultation_flags.append(("BLOCKED", parsed.get("block_reason", "")))
                                elif parsed.get("consultation_required"):
                                    consultation_flags.append(("REQUIRED", str(parsed.get("flags", []))))
                            lines.append(f"\n**{tool.replace('_',' ').title()}:**\n{out[:600]}")
                        answer = "\n".join(lines)
                        result = {
                            "answer":      answer,
                            "tools_used":  raw.get("steps_planned", []),
                            "sources":     [],
                            "consult":     consultation_flags,
                        }
                    else:
                        result = run_agent(st.session_state.agent, user_input)
                        result["consult"] = []
                except Exception as e:
                    result = {
                        "answer":     f"Error: {e}\n\nPlease check your API keys in .env",
                        "tools_used": [],
                        "sources":    [],
                        "consult":    [],
                    }

            _render_assistant_turn(result, result.get("answer", ""))

        st.session_state.messages.append({
            "role": "assistant",
            "content": result.get("answer", ""),
            "data":    result,
        })


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — INSIGHTS DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_insights:
    st.markdown("### 📊 Live KPI Metrics & Synthesized PM Insights")
    st.caption("Data is generated from the NammaYatri KPI simulation. Click Refresh to reload.")

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        refresh = st.button("🔄 Refresh", key="refresh_insights")

    if refresh or "kpi_data" not in st.session_state:
        with st.spinner("Fetching KPI metrics and synthesizing insights..."):
            try:
                from src.tools import check_kpi_metrics as _ckm
                kpi_raw = _ckm.func("") if hasattr(_ckm, "func") else _ckm("")
                kpi_parsed = _safe_json(kpi_raw) or {}
                st.session_state["kpi_data"] = kpi_parsed

                from src.insight_layer import synthesize_insights as _si
                metrics = kpi_parsed.get("metrics", {})
                insights = _si(metrics, [])
                st.session_state["insights"] = insights
            except Exception as e:
                st.error(f"Error loading KPI data: {e}")
                kpi_parsed = {}
                insights   = []
    else:
        kpi_parsed = st.session_state.get("kpi_data", {})
        insights   = st.session_state.get("insights", [])

    # KPI metric cards
    metrics = kpi_parsed.get("metrics", {})
    breached = kpi_parsed.get("breached_kpis", [])

    kpi_display = [
        ("driver_cancellation_rate", "Driver Cancellation",  "%%", True),
        ("avg_wait_time_minutes",    "Avg Wait Time",         "min", True),
        ("ride_completion_rate",     "Completion Rate",       "%%", False),
        ("driver_retention_rate",    "Driver Retention",      "%%", False),
        ("app_rating",               "App Rating",            "/5", False),
        ("active_drivers",           "Active Drivers",        "",   False),
    ]

    kpi_cols = st.columns(len(kpi_display))
    for col, (key, label, unit, higher_is_bad) in zip(kpi_cols, kpi_display):
        val = metrics.get(key, "—")
        is_breached = key in breached
        val_class = "kpi-breached" if is_breached else "kpi-healthy"
        val_str = f"{val}{unit}" if val != "—" else "—"
        warn = " ⚠️" if is_breached else ""
        col.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}{warn}</div>'
            f'<div class="kpi-value {val_class}">{val_str}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if breached:
        st.markdown(
            f'<div class="block-banner">⚠️ <strong>Breached KPIs:</strong> '
            f'{", ".join(breached)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("#### 🧠 Synthesized PM Insights")

    if not insights:
        st.info("No insights synthesized — KPI data may be within bounds or unavailable.")
    else:
        for ins in insights:
            sev  = ins.severity.value if hasattr(ins.severity, "value") else str(ins.severity)
            itype = ins.type.value if hasattr(ins.type, "value") else str(ins.type)
            color = _severity_color(sev)
            css_cls = f"insight-{sev.lower()}"

            consult_tag = ""
            if ins.requires_consultation:
                consult_tag = (
                    f'<span class="badge-medium" style="margin-left:8px;">Consultation Required</span>'
                )

            st.markdown(
                f'<div class="insight-card {css_cls}">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                f'{_severity_badge(sev)}'
                f'<strong style="color:#e6edf3;">{ins.title}</strong>'
                f'{consult_tag}'
                f'</div>'
                f'<p style="color:#8b949e;font-size:0.88rem;margin:0 0 6px 0;">{ins.description}</p>'
                f'<p style="color:#58a6ff;font-size:0.82rem;margin:0;">'
                f'Type: {itype} &nbsp;|&nbsp; Confidence: {ins.confidence:.0%}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if ins.recommended_pm_actions:
                with st.expander(f"📌 Recommended Actions — {ins.title}", expanded=False):
                    for action in ins.recommended_pm_actions:
                        st.markdown(f"- {action}")

            if ins.root_cause_hypotheses:
                with st.expander(f"🔬 Root Cause Hypotheses — {ins.title}", expanded=False):
                    for h in ins.root_cause_hypotheses:
                        st.markdown(f"- {h}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DECISION BOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_decisions:
    st.markdown("### 📋 Decision Board")
    st.caption("All PM decisions logged by ARIA. Log outcomes to feed the learning loop.")

    col_d1, col_d2 = st.columns([3, 2])

    with col_d1:
        st.markdown("#### Recent Decisions")
        try:
            from src.memory_store import get_decisions as _gd
            decisions = _gd(limit=30)
        except Exception as e:
            st.error(f"Could not load decisions: {e}")
            decisions = []

        if not decisions:
            st.info("No decisions logged yet. Run a PM workflow to generate and log decisions.")
        else:
            import pandas as pd
            rows = []
            for d in decisions:
                rows.append({
                    "ID":         d.get("id", "")[:8],
                    "Issue":      (d.get("issue_title") or "")[:50],
                    "Priority":   d.get("priority", ""),
                    "Status":     d.get("status", ""),
                    "Score":      d.get("composite_score", ""),
                    "Team":       d.get("assigned_team", ""),
                    "Outcome":    d.get("outcome_score", "—"),
                })
            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "Score": st.column_config.NumberColumn(format="%.2f"),
                    "Outcome": st.column_config.NumberColumn(format="%.2f"),
                },
            )

    with col_d2:
        st.markdown("#### Log an Outcome")
        with st.form("outcome_form"):
            decision_id     = st.text_input("Decision ID (full)", placeholder="e.g. abc123...")
            kpi_improved    = st.checkbox("KPI improved after this decision", value=False)
            hypothesis_held = st.checkbox("Primary hypothesis held", value=False)
            driver_delta    = st.slider("Driver impact delta", -1.0, 1.0, 0.0, 0.05)
            rider_delta     = st.slider("Rider impact delta",  -1.0, 1.0, 0.0, 0.05)
            notes           = st.text_area("Notes (optional)", height=80)
            submitted       = st.form_submit_button("💾 Log Outcome", use_container_width=True)

        if submitted:
            if not decision_id.strip():
                st.warning("Please enter a Decision ID.")
            else:
                try:
                    from src.learning_loop import log_outcome as _lo
                    outcome_result = _lo(
                        decision_id     = decision_id.strip(),
                        kpi_improved    = kpi_improved,
                        hypothesis_held = hypothesis_held,
                        driver_impact_delta = driver_delta,
                        rider_impact_delta  = rider_delta,
                        notes           = notes,
                    )
                    st.success(f"Outcome logged! Learning note: {outcome_result.get('learning_note', '')}")
                    updated = outcome_result.get("updated_weights", {})
                    if updated:
                        st.markdown("**Updated Weights:**")
                        for factor, weight in updated.items():
                            bar_pct = min(int((weight / 2.0) * 100), 100)
                            st.markdown(
                                f'<div style="margin:4px 0;">'
                                f'<span style="color:#8b949e;font-size:0.82rem;">{factor}</span>'
                                f'<div class="weight-bar-bg" style="margin-top:3px;">'
                                f'<div class="weight-bar-fill" style="width:{bar_pct}%"></div>'
                                f'</div>'
                                f'<span style="color:#58a6ff;font-size:0.78rem;">{weight:.3f}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                except Exception as e:
                    st.error(f"Error logging outcome: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — LEARNING LOOP
# ══════════════════════════════════════════════════════════════════════════════
with tab_learning:
    st.markdown("### 📈 Learning Loop")
    st.caption("ARIA adjusts its scoring weights based on outcome feedback over time.")

    col_lr, _ = st.columns([1, 5])
    with col_lr:
        reload = st.button("🔄 Reload", key="reload_learning")

    try:
        from src.learning_loop import get_learning_state as _gls
        ls = _gls()
    except Exception as e:
        st.error(f"Could not load learning state: {e}")
        ls = {}

    health = ls.get("learning_health", "COLD START — No data yet.")
    summary = ls.get("outcome_summary", {})
    weights = ls.get("current_weights", {})
    insights_text = ls.get("weight_insights", [])
    recent = ls.get("recent_decisions", [])

    # Health banner
    health_color = "#3fb950"
    if "COLD START" in health or "PENDING" in health:
        health_color = "#8b949e"
    elif "NEEDS REVIEW" in health:
        health_color = "#f85149"
    elif "IN PROGRESS" in health:
        health_color = "#d29922"

    st.markdown(
        f'<div style="background:#1c2333;border:2px solid {health_color};border-radius:10px;'
        f'padding:14px 18px;margin-bottom:16px;">'
        f'<span style="color:{health_color};font-weight:700;font-size:1rem;">🏥 System Health: {health}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_l1, col_l2 = st.columns(2)

    with col_l1:
        st.markdown("#### 🎛️ Current Scoring Weights")
        if not weights:
            st.info("No weight data — log some decisions and outcomes to begin calibration.")
        else:
            for factor, w in weights.items():
                pct = min(int((w / 2.0) * 100), 100)
                deviation = w - 1.0
                dev_str = (f"+{deviation:.3f}" if deviation >= 0 else f"{deviation:.3f}")
                dev_color = "#3fb950" if deviation > 0 else ("#f85149" if deviation < -0.05 else "#8b949e")
                st.markdown(
                    f'<div style="margin-bottom:10px;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
                    f'<span style="color:#c9d1d9;font-size:0.85rem;">{factor.replace("_"," ").title()}</span>'
                    f'<span style="color:{dev_color};font-size:0.82rem;font-weight:600;">'
                    f'{w:.3f} ({dev_str})</span>'
                    f'</div>'
                    f'<div class="weight-bar-bg">'
                    f'<div class="weight-bar-fill" style="width:{pct}%;'
                    f'background:{"#3fb950" if deviation > 0.1 else ("#f85149" if deviation < -0.05 else "#58a6ff")};"></div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with col_l2:
        st.markdown("#### 💡 Weight Insights")
        if insights_text:
            for note in insights_text:
                icon = "↑" if note.startswith("↑") else ("↓" if note.startswith("↓") else "•")
                color = "#3fb950" if icon == "↑" else ("#f85149" if icon == "↓" else "#8b949e")
                st.markdown(
                    f'<div style="background:#1c2333;border-left:3px solid {color};'
                    f'border-radius:6px;padding:8px 12px;margin-bottom:8px;'
                    f'color:#c9d1d9;font-size:0.85rem;">{note}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("#### 📊 Outcome Summary")
        if summary:
            cols_s = st.columns(3)
            cols_s[0].metric("Total Decisions", summary.get("total_decisions", 0))
            cols_s[1].metric("Closed",          summary.get("closed", 0))
            cols_s[2].metric("Avg Outcome",     f"{summary.get('avg_outcome_score', 0.0):.2f}")
        else:
            st.info("No outcome data yet.")

    st.markdown("---")
    st.markdown("#### 🕐 Recent Decisions")
    if recent:
        import pandas as pd
        st.dataframe(
            pd.DataFrame(recent),
            use_container_width=True,
            column_config={
                "outcome_score": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    else:
        st.info("No recent decisions to display.")
