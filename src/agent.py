"""
agent.py — ARIA workflow orchestration.

Two execution paths:
  1. run_direct_pipeline()  — calls all tool functions as pure Python (zero LLM tokens).
                              This is the primary path. Use it for all PM workflows.
  2. run_agent()            — single-turn LangGraph ReAct agent for conversational Q&A only.

All intelligence tools (KPI check, insight synthesis, RCA, prioritization, consultation gate,
artifact generation) are pure Python and don't need the LLM. The LLM is only needed for
open-ended Q&A via the copilot chat.

LLM alternatives (set LLM_PROVIDER in .env):
  groq     — Groq + llama-3.1-8b-instant (default, free but 6K TPM limit)
  ollama   — local Ollama (free, unlimited, requires ollama installed)
  gemini   — Google Gemini 3 Flash Preview (configurable via GEMINI_MODEL)
  openai   — OpenAI GPT-4o-mini (cheap)
"""

import os
import json
import re
from dotenv import load_dotenv
from typing import TypedDict, Optional
from src.prompt import ARIA_SYSTEM_PROMPT

load_dotenv(override=True)


# ── LLM builder — supports Groq / Ollama / Gemini / OpenAI ────────────────────

def _get_provider() -> str:
    """Read the selected LLM provider from the environment."""
    return os.environ.get("LLM_PROVIDER", "groq").strip().lower()


def _require_env(name: str, provider: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(
            f"Missing required environment variable `{name}` for "
            f"`LLM_PROVIDER={provider}`."
        )
    return value


def get_llm_config_signature() -> str:
    """Return the current provider/model selection for cache invalidation."""
    provider = _get_provider()
    if provider == "ollama":
        model = os.environ.get("OLLAMA_MODEL", "llama3.2").strip()
    elif provider == "gemini":
        model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview").strip()
    elif provider == "openai":
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    elif provider == "groq":
        model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    else:
        model = "unknown"
    return f"{provider}:{model}"


def build_llm():
    """Build the LLM from the selected provider."""
    provider = _get_provider()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        model = os.environ.get("OLLAMA_MODEL", "llama3.2").strip()
        return ChatOllama(model=model, temperature=0.3)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview").strip(),
            temperature=0.3,
            google_api_key=_require_env("GOOGLE_API_KEY", provider),
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
            temperature=0.3,
            api_key=_require_env("OPENAI_API_KEY", provider),
        )

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant").strip(),
            temperature=0.3,
            api_key=_require_env("GROQ_API_KEY", provider),
        )

    raise ValueError(
        "Unsupported `LLM_PROVIDER`. Expected one of: "
        "`groq`, `gemini`, `ollama`, `openai`."
    )


def build_agent():
    """Build the LangGraph ReAct agent (used only for copilot Q&A)."""
    from langgraph.prebuilt import create_react_agent
    from src.tools import ALL_TOOLS

    # Shorten the prompt for the agent to stay within token limits
    short_prompt = _SHORT_AGENT_PROMPT
    llm = build_llm()
    return create_react_agent(model=llm, tools=ALL_TOOLS, prompt=short_prompt)


# Short prompt for the ReAct agent (keeps token usage low for Q&A calls)
_SHORT_AGENT_PROMPT = """You are ARIA, an AI Product Manager for Namma Yatri.
Zero commission is sacred — never suggest revenue extraction from drivers.
Always check: driver impact, rider impact, mission alignment.
Use the available tools to answer the user's question. Be concise and structured."""


# ── Workflow state ─────────────────────────────────────────────────────────────

class WorkflowState(TypedDict):
    user_input: str
    kpi_metrics: Optional[dict]
    insights: Optional[dict]
    rca: Optional[dict]
    prioritized_issues: Optional[dict]
    consultation: Optional[dict]
    solution: Optional[dict]
    prd: Optional[dict]
    jira_stories: Optional[dict]
    roadmap: Optional[dict]
    completed: bool
    step_logs: list


# ── Workflow type detection ────────────────────────────────────────────────────

def detect_workflow_type(user_message: str) -> str:
    msg = user_message.lower()
    if any(kw in msg for kw in ["start pm workflow", "full workflow", "run all steps", "autonomous pm"]):
        return "FULL_WORKFLOW"
    if any(kw in msg for kw in ["learning", "outcome", "what worked", "explain decision", "log outcome", "learning state"]):
        return "LEARNING_QUERY"
    if any(kw in msg for kw in ["dropped", "breach", "declining", "rate fell", "kpi", "cancellation rate", "wait time", "completion rate", "driver churn", "app rating"]):
        return "INCIDENT"
    if any(kw in msg for kw in ["build", "prd", "feature", "advance booking", "design", "implement", "new feature", "scheduled ride"]):
        return "FEATURE"
    if any(kw in msg for kw in ["compare", "competitor", "market", "trend", "research"]):
        return "EXPLORATION"
    return "GENERAL"


def get_workflow_steps(workflow_type: str) -> list:
    workflows = {
        "FULL_WORKFLOW": [
            ("check_kpi_metrics",       "📊 Checking KPI Metrics"),
            ("synthesize_pm_insights",  "🧠 Synthesizing PM Insights"),
            ("run_root_cause_analysis", "🔬 Running Root Cause Analysis"),
            ("ai_prioritize_issues",    "🎯 AI-Driven Prioritization"),
            ("check_consultation_gate", "🛡️ Consultation & Compliance Gate"),
            ("generate_solution",       "💡 Generating Solution"),
            ("generate_prd",            "📝 Writing PRD"),
            ("create_jira_stories",     "🎫 Creating Jira Stories"),
            ("generate_roadmap",        "🗺️ Generating Roadmap"),
        ],
        "INCIDENT": [
            ("check_kpi_metrics",       "📊 Checking KPI Metrics"),
            ("synthesize_pm_insights",  "🧠 Synthesizing PM Insights"),
            ("run_root_cause_analysis", "🔬 Running Root Cause Analysis"),
            ("ai_prioritize_issues",    "🎯 AI-Driven Prioritization"),
            ("check_consultation_gate", "🛡️ Consultation & Compliance Gate"),
            ("generate_solution",       "💡 Generating Solution"),
            ("generate_prd",            "📝 Writing PRD"),
            ("create_jira_stories",     "🎫 Creating Jira Stories"),
        ],
        "FEATURE": [
            ("analyze_pain_points",     "📊 Validating Problem"),
            ("evaluate_pm_decision",    "⚖️ PM Framework Evaluation"),
            ("check_consultation_gate", "🛡️ Consultation & Compliance Gate"),
            ("generate_prd",            "📝 Writing PRD"),
            ("create_jira_stories",     "🎫 Creating Jira Stories"),
            ("generate_roadmap",        "🗺️ Adding to Roadmap"),
        ],
        "EXPLORATION": [
            ("search_competitor_data", "🔍 Competitor Analysis"),
            ("search_market_trends",   "📊 Market Trends"),
        ],
        "LEARNING_QUERY": [
            ("get_learning_state_tool", "📈 Fetching Learning State"),
        ],
        "GENERAL": [
            ("search_namma_yatri_reviews", "🔍 Searching NammaYatri Knowledge Base"),
        ],
    }
    return workflows.get(workflow_type, workflows["GENERAL"])


# ── Direct pipeline — NO LLM, pure Python tool execution ──────────────────────

def run_direct_pipeline(user_message: str, step_callback=None) -> dict:
    """
    Execute the PM workflow by calling tool Python functions directly.
    Zero LLM tokens consumed. All analysis and artifact tools are pure Python.

    This is the primary execution path. Use run_agent() only for conversational Q&A.
    step_callback(step_number, step_name, output, workflow_type) is called after each step.
    """
    import src.tools as T

    workflow_type = detect_workflow_type(user_message)
    steps = get_workflow_steps(workflow_type)

    results: dict = {
        "workflow_type":  workflow_type,
        "steps_planned":  [s[0] for s in steps],
    }
    ctx: dict = {}   # cumulative context dict passed between steps

    for i, (tool_name, step_name) in enumerate(steps):
        try:
            output = _call_tool_direct(tool_name, ctx, T)
            results[tool_name] = output

            # Merge parsed output into cumulative context
            parsed = _try_parse(output)
            if isinstance(parsed, dict):
                ctx.update(parsed)
            else:
                ctx[tool_name] = str(output)[:400]

            if step_callback:
                step_callback(i + 1, step_name, output, workflow_type)

        except Exception as e:
            err = f"Error in {tool_name}: {e}"
            results[tool_name] = err
            if step_callback:
                step_callback(i + 1, step_name, f"❌ {err}", workflow_type)

    return results


def _call_tool_direct(tool_name: str, ctx: dict, T) -> str:
    """Dispatch a single tool call using the accumulated context dict."""

    # ── Analysis tools (pure Python, no LLM) ──────────────────────────────────

    if tool_name == "check_kpi_metrics":
        return T.check_kpi_metrics.func("")

    if tool_name == "synthesize_pm_insights":
        # Pass the full KPI JSON
        kpi_src = ctx.get("check_kpi_metrics") or json.dumps({"metrics": ctx.get("metrics", {}), "breached_kpis": ctx.get("breached_kpis", [])})
        return T.synthesize_pm_insights.func(kpi_src)

    if tool_name == "run_root_cause_analysis":
        title = _top_issue_title(ctx)
        context_json = json.dumps({
            "breached_kpis": ctx.get("breached_kpis", []),
            "metrics":       ctx.get("metrics", {}),
        })
        return T.run_root_cause_analysis.func(title, context_json)

    if tool_name == "ai_prioritize_issues":
        pain_points = ctx.get("pain_points") or _build_pain_points_from_ctx(ctx)
        payload = json.dumps({
            "pain_points":  pain_points,
            "breached_kpis": ctx.get("breached_kpis", []),
        })
        return T.ai_prioritize_issues.func(payload)

    if tool_name == "evaluate_pm_decision":
        issue_json   = json.dumps({"title": _top_issue_title(ctx)})
        context_json = json.dumps({"breached_kpis": ctx.get("breached_kpis", [])})
        return T.evaluate_pm_decision.func(issue_json, context_json)

    if tool_name == "check_consultation_gate":
        top  = _top_issue(ctx)
        title   = top.get("title", _top_issue_title(ctx))
        solution = ctx.get("solution", ctx.get("feature_name", ""))
        return T.check_consultation_gate.func(title, str(solution), "")

    if tool_name == "get_learning_state_tool":
        return T.get_learning_state_tool.func("")

    # ── Artifact tools (pure Python templates) ────────────────────────────────

    if tool_name == "generate_solution":
        payload = json.dumps({
            "top_priority_issue":  _top_issue(ctx),
            "prioritized":         ctx.get("prioritized", []),
            "breached_kpis":       ctx.get("breached_kpis", []),
        })
        return T.generate_solution.func(payload)

    if tool_name == "generate_prd":
        payload = json.dumps({
            "feature_name":       ctx.get("feature_name", ""),
            "problem":            ctx.get("problem", ""),
            "solution":           ctx.get("solution", ""),
            "top_priority_issue": _top_issue(ctx),
            "consultation_required": ctx.get("consultation_required", False),
            "consultation_flags": ctx.get("consultation_flags", []),
        })
        return T.generate_prd.func(payload)

    if tool_name == "create_jira_stories":
        payload = json.dumps({
            "feature_name":       ctx.get("feature_name", ""),
            "prd_summary":        ctx.get("prd_summary", ctx.get("problem", "")),
            "solution":           ctx.get("solution", ""),
            "consultation_required": ctx.get("consultation_required", False),
        })
        return T.create_jira_stories.func(payload)

    if tool_name == "generate_roadmap":
        payload = json.dumps({
            "feature_name": ctx.get("feature_name", ""),
            "solution":     ctx.get("solution", ""),
            "priority":     _top_issue(ctx).get("priority", "P1"),
        })
        return T.generate_roadmap.func(payload)

    if tool_name == "analyze_pain_points":
        return T.analyze_pain_points.func(json.dumps(ctx)[:600])

    if tool_name == "search_namma_yatri_reviews":
        return T.search_namma_yatri_reviews.func("NammaYatri user feedback pain points")

    if tool_name == "search_competitor_data":
        return T.search_competitor_data.func("NammaYatri vs Ola Uber Rapido comparison 2025")

    if tool_name == "search_market_trends":
        return T.search_market_trends.func("India mobility ride hailing market trends 2025 2026")

    return f"No direct handler for tool: {tool_name}"


# ── Context extraction helpers ─────────────────────────────────────────────────

def _top_issue(ctx: dict) -> dict:
    """Extract the top priority issue dict from cumulative context."""
    top = ctx.get("top_priority_issue")
    if isinstance(top, dict):
        return top
    prioritized = ctx.get("prioritized", [])
    if prioritized and isinstance(prioritized, list):
        return prioritized[0]
    return {"title": "High driver cancellation rate after ride acceptance", "priority": "P0"}


def _top_issue_title(ctx: dict) -> str:
    return _top_issue(ctx).get("title", "Driver cancellation rate breach")


def _build_pain_points_from_ctx(ctx: dict) -> list:
    """Build a pain_points list from KPI breaches when no explicit list exists."""
    breached = ctx.get("breached_kpis", [])
    title_map = {
        "driver_cancellation_rate": "High driver cancellation rate after ride acceptance",
        "avg_wait_time_minutes":    "Average wait time too high — riders switching to competitors",
        "ride_completion_rate":     "Ride completion rate declining — drivers cancelling post-match",
        "driver_retention_rate":    "Driver retention falling — supply collapse risk",
        "app_rating":               "App rating below threshold — negative Play Store visibility",
    }
    return [
        {"id": f"PP-{i+1:03}", "title": title_map.get(k, k), "frequency": "high"}
        for i, k in enumerate(breached)
        if k in title_map
    ] or [{"id": "PP-001", "title": "High driver cancellation rate after ride acceptance", "frequency": "high"}]


def _try_parse(text: str) -> any:
    try:
        return json.loads(text)
    except Exception:
        return None


# ── Smart workflow — uses direct pipeline as primary path ──────────────────────

def run_smart_workflow(agent, user_message: str, step_callback=None) -> dict:
    """
    Primary entry point for all PM workflows.
    Runs the direct pipeline (no LLM) for analysis/artifact steps.
    The 'agent' parameter is kept for API compatibility but is not used for the pipeline.
    """
    return run_direct_pipeline(user_message, step_callback)


def run_workflow(agent, step_callback=None) -> dict:
    """Full 11-step autonomous PM pipeline (direct execution)."""
    return run_direct_pipeline("start pm workflow full pipeline", step_callback)


# ── Single-turn copilot Q&A ────────────────────────────────────────────────────

def run_agent(agent, user_message: str) -> dict:
    """
    Single-turn ReAct agent for conversational Q&A.
    Uses the LLM only here — with a short prompt to stay within token limits.
    Falls back to direct tool calls if the LLM errors.
    """
    try:
        result = agent.invoke({"messages": [("human", user_message)]})
        messages = result.get("messages", [])
        answer = ""
        tools_used = []
        sources = []

        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "AIMessage":
                if msg.content:
                    answer = msg.content
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = tc.get("name", "unknown")
                        if name not in tools_used:
                            tools_used.append(name)
            elif msg_type == "ToolMessage":
                content = getattr(msg, "content", "") or ""
                found = re.findall(r"\[SOURCE:\s*(https?://[^\]]+)\]", content)
                for s in found:
                    if s not in sources:
                        sources.append(s)

        return {"answer": answer, "tools_used": tools_used, "sources": sources, "consult": []}

    except Exception as e:
        # LLM unavailable — give a helpful direct answer
        return {
            "answer": (
                f"LLM unavailable: `{e}`\n\n"
                "For PM analysis (KPI breach, RCA, prioritization, PRD) use the "
                "**PM Workflow** button or quick actions — these run without the LLM.\n\n"
                "For conversational Q&A, check your `.env` API key or set "
                "`LLM_PROVIDER=ollama` to use a local model."
            ),
            "tools_used": [],
            "sources":    [],
            "consult":    [],
        }


# ── Direct autonomous execution (no agent object needed) ──────────────────────

def run_autonomous_pm_execution(user_message: str) -> dict:
    """Direct execution path — no agent object required, no LLM tokens used."""
    raw = run_direct_pipeline(user_message)
    top = _top_issue(raw)
    return {
        "problem":  top.get("title", ""),
        "solution": raw.get("generate_solution", ""),
        "prd":      raw.get("generate_prd", ""),
        "jira":     raw.get("create_jira_stories", ""),
        "roadmap":  raw.get("generate_roadmap", ""),
        "status":   "executed",
        "raw":      raw,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _merge_json_outputs(results: dict) -> str:
    merged: dict = {}
    for tool_name, output in results.items():
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                merged.update(parsed)
            else:
                merged[tool_name] = parsed
        except (json.JSONDecodeError, TypeError):
            merged[tool_name] = str(output)[:400]
    try:
        return json.dumps(merged, indent=2)
    except Exception:
        return str(merged)[:2000]


def _summarize_output(output: str, max_chars: int = 800) -> str:
    try:
        data = json.loads(output)
        if isinstance(data, dict):
            for key in ("summary", "problem", "solution", "title", "feature_name"):
                if key in data:
                    return str(data[key])[:max_chars]
            return json.dumps(data)[:max_chars]
        return str(data)[:max_chars]
    except Exception:
        return str(output)[:max_chars]
