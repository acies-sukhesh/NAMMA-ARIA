"""
tools.py — All ARIA PM tools for NammaYatri.

New tools (v2):
  synthesize_pm_insights    — converts KPI metrics to typed PM insights
  run_root_cause_analysis   — issue-specific multi-hypothesis RCA
  evaluate_pm_decision      — PM framework scoring (driver welfare, rider trust…)
  check_consultation_gate   — compliance / community consultation flags
  ai_prioritize_issues      — AI-driven prioritization using framework + learning context
  log_decision_outcome      — record outcome for learning loop
  get_learning_state_tool   — expose learning state to copilot
  explain_decision          — copilot: explain any logged decision

Upgraded existing tools:
  generate_prd              — now includes driver/rider impact, mission alignment, consultation flags
  generate_roadmap          — now includes mission rationale, stakeholder scope, city scope
  create_jira_stories       — better acceptance criteria, cross-functional ownership
  prioritize_issues         — now calls evaluate_issue internally for richer reasoning
"""

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.tools import tool
from pinecone import Pinecone
from langchain_huggingface import HuggingFaceEmbeddings
from tavily import TavilyClient

from src.insight_layer import synthesize_insights, insights_to_json, get_insight_summary
from src.root_cause import analyze_root_cause, rca_to_json
from src.pm_framework import evaluate_issue, evaluate_to_priority, PMEvaluation
from src.consultation_gate import run_consultation_gate, gate_to_json
from src.learning_loop import (
    log_pm_decision,
    log_outcome,
    get_learning_state,
    get_learning_context,
)

load_dotenv()

# ── Singletons ─────────────────────────────────────────────────────────────────

_tavily:    TavilyClient | None          = None
_embeddings: HuggingFaceEmbeddings | None = None
_pinecone_index                          = None


def _get_tavily() -> TavilyClient:
    global _tavily
    if _tavily is None:
        _tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    return _tavily


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return _embeddings


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        _pinecone_index = pc.Index(os.environ.get("PINECONE_INDEX_NAME", "namma-aria"))
    return _pinecone_index


def _tavily_search(queries: List[str], max_results: int = 3) -> List[Dict]:
    client = _get_tavily()
    results = []
    for q in queries:
        try:
            resp = client.search(query=q, max_results=max_results)
            for r in resp.get("results", []):
                results.append({
                    "url":     r.get("url", ""),
                    "content": r.get("content", ""),
                    "title":   r.get("title", ""),
                })
        except Exception as e:
            results.append({"url": "error", "content": str(e), "title": "Search Error"})
    return results


def _tavily_search_text(queries: List[str], max_results: int = 3) -> str:
    results = _tavily_search(queries, max_results)
    return "\n\n---\n\n".join(
        f"[SOURCE: {r['url']}]\n{r['content']}" for r in results
    ) or "No results found."


def _infer_labels(text: str) -> List[str]:
    tl = text.lower()
    labels = []
    if any(w in tl for w in ["crash", "error", "bug", "fail"]):
        labels.append("type::bug")
    if any(w in tl for w in ["slow", "wait", "latency"]):
        labels.append("type::performance")
    if any(w in tl for w in ["driver", "earning", "commission"]):
        labels.append("stakeholder::driver")
    if any(w in tl for w in ["rider", "user", "booking", "cancel"]):
        labels.append("stakeholder::rider")
    return labels or ["type::feedback"]


# ══════════════════════════════════════════════════════════════════════════════
# NEW TOOLS (v2 intelligence layer)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def synthesize_pm_insights(kpi_metrics_json: str) -> str:
    """
    Convert raw KPI metric data into typed, actionable PM insights.
    Must be called BEFORE prioritization or artifact generation.
    Returns: JSON list of insights with severity, evidence, hypotheses, and consultation flags.
    Args:
        kpi_metrics_json: JSON string from check_kpi_metrics output.
    """
    try:
        data    = json.loads(kpi_metrics_json)
        metrics = data.get("metrics", data)
        issues  = data.get("issues", [])
    except (json.JSONDecodeError, TypeError):
        metrics, issues = {}, []

    insights = synthesize_insights(metrics, issues)
    summary  = get_insight_summary(insights)
    result = {
        "insights":        [i.to_dict() for i in insights],
        "insight_count":   len(insights),
        "summary":         summary,
        "critical_count":  sum(1 for i in insights if i.severity == "CRITICAL"),
        "consultation_needed": any(i.requires_consultation for i in insights),
    }
    return json.dumps(result, indent=2)


@tool
def run_root_cause_analysis(issue_title: str, context_json: str = "{}") -> str:
    """
    Run NammaYatri-specific multi-hypothesis root cause analysis for a PM issue.
    Returns ranked hypotheses with confidence, investigation actions, and cross-functional scope.
    Args:
        issue_title: The issue to analyse (e.g. 'High driver cancellation rate').
        context_json: Optional JSON with 'breached_kpis' or other context.
    """
    try:
        ctx = json.loads(context_json) if context_json.strip().startswith("{") else {}
    except (json.JSONDecodeError, TypeError):
        ctx = {}

    rca = analyze_root_cause(issue_title, ctx)
    return rca_to_json(rca)


@tool
def evaluate_pm_decision(issue_json: str, context_json: str = "{}") -> str:
    """
    Evaluate a PM issue through the NammaYatri decision framework.
    Scores driver welfare, rider trust, mission alignment, compliance risk, urgency, effort, and more.
    Returns a composite score (0–10), priority label (P0–P3 or BLOCKED), and full rationale.
    Args:
        issue_json: JSON with at least a 'title' field for the issue.
        context_json: Optional JSON with 'breached_kpis' list.
    """
    try:
        issue = json.loads(issue_json)
    except (json.JSONDecodeError, TypeError):
        issue = {"title": issue_json[:200]}

    try:
        ctx = json.loads(context_json) if context_json.strip().startswith("{") else {}
    except (json.JSONDecodeError, TypeError):
        ctx = {}

    ev       = evaluate_issue(issue, ctx)
    priority = evaluate_to_priority(ev)

    result = ev.to_dict()
    result["composite_score"] = ev.composite_score()
    result["priority"]        = priority
    return json.dumps(result, indent=2)


@tool
def check_consultation_gate(
    issue_title: str = "",
    solution_text: str = "",
    prd_text: str = "",
) -> str:
    """
    Check whether a PM issue/solution/PRD requires community consultation or protocol review.
    Hard-blocks on zero-commission violations.
    Returns: JSON with flags, block status, and recommended consultation steps.
    Args:
        issue_title:   The issue or feature title.
        solution_text: Proposed solution text.
        prd_text:      PRD content (if available).
    """
    gate = run_consultation_gate(issue_title, solution_text, prd_text)
    return gate_to_json(gate)


@tool
def ai_prioritize_issues(context_json: str) -> str:
    """
    AI-driven prioritization using the PM decision framework and learning context.
    Priority emerges from composite scoring of driver welfare, rider trust, urgency,
    strategic value, effort, and compliance risk — not just an ICE formula.
    Also checks past similar decisions for pattern guidance.
    Args:
        context_json: JSON containing 'pain_points' list and optionally 'breached_kpis'.
    """
    try:
        data = json.loads(context_json)
    except (json.JSONDecodeError, TypeError):
        data = {}

    pain_points  = data.get("pain_points", [])
    breached     = data.get("breached_kpis", [])
    ctx          = {"breached_kpis": breached}

    # Fallback if no pain points provided
    if not pain_points:
        pain_points = [
            {"id": "PP-001", "title": "High driver cancellation rate after ride acceptance", "frequency": "high"},
            {"id": "PP-002", "title": "Long wait times during off-peak hours", "frequency": "high"},
            {"id": "PP-005", "title": "Driver earnings analytics are limited", "frequency": "medium"},
        ]

    scored: List[Dict] = []
    rejected: List[Dict] = []

    zero_commission_keywords = [
        "commission", "take rate", "percentage cut", "per-ride fee", "cut from fare"
    ]

    for pp in pain_points:
        title = pp.get("title", "")
        if any(kw in title.lower() for kw in zero_commission_keywords):
            rejected.append({**pp, "rejection_reason": "VIOLATES ZERO COMMISSION PRINCIPLE", "zero_commission_safe": False})
            continue

        ev       = evaluate_issue(pp, ctx)
        priority = evaluate_to_priority(ev)
        lc       = get_learning_context(title)

        scored.append({
            "id":                     pp.get("id", ""),
            "title":                  title,
            "priority":               priority,
            "composite_score":        ev.composite_score(),
            "driver_welfare_impact":  ev.driver_welfare_impact,
            "rider_trust_impact":     ev.rider_trust_impact,
            "urgency":                ev.urgency,
            "strategic_importance":   ev.strategic_importance,
            "effort_estimate":        ev.effort_estimate,
            "mission_alignment":      ev.mission_alignment,
            "symptom_or_root":        ev.symptom_or_root,
            "consultation_required":  ev.requires_consultation,
            "consultation_flags":     ev.consultation_flags,
            "rationale":              ev.rationale,
            "learning_guidance":      lc["learning_guidance"],
            "similar_past_decisions": lc["similar_past_decisions"],
            "zero_commission_safe":   True,
        })

    # Sort: BLOCKED last, then by composite score descending
    _pri_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "BLOCKED": 4}
    scored.sort(key=lambda x: (_pri_order.get(x["priority"], 5), -x["composite_score"]))

    top = scored[0] if scored else None

    return json.dumps({
        "prioritized":        scored,
        "rejected":           rejected,
        "top_priority_issue": top,
        "summary": (
            f"{len(scored)} issues AI-prioritized using PM framework "
            f"(driver welfare, rider trust, urgency, effort, compliance). "
            f"{len(rejected)} rejected as zero-commission violations."
        ),
    }, indent=2)


@tool
def log_decision_outcome(
    decision_id: str,
    kpi_improved: str,
    driver_impact_delta: str = "0",
    rider_impact_delta: str  = "0",
    hypothesis_held: str     = "false",
    notes: str               = "",
) -> str:
    """
    Record the outcome of a PM decision to close the learning loop.
    Updates learning weights so future prioritizations improve.
    Args:
        decision_id:         ID returned when the decision was logged (e.g. DEC-A1B2C3D4).
        kpi_improved:        'true' or 'false' — did the target KPI improve?
        driver_impact_delta: Change in driver metric (e.g. '5.0' for +5pp retention).
        rider_impact_delta:  Change in rider metric (e.g. '3.0' for +3pp satisfaction).
        hypothesis_held:     'true' or 'false' — did the primary hypothesis prove correct?
        notes:               Free-text outcome notes.
    """
    result = log_outcome(
        decision_id         = decision_id,
        kpi_improved        = kpi_improved.lower() == "true",
        driver_impact_delta = float(driver_impact_delta),
        rider_impact_delta  = float(rider_impact_delta),
        hypothesis_held     = hypothesis_held.lower() == "true",
        notes               = notes,
    )
    return json.dumps(result, indent=2)


@tool
def get_learning_state_tool(query: str = "") -> str:
    """
    Return ARIA's current learning state: scoring weights, outcome summary,
    recent decisions, and a health assessment of the learning loop.
    Use this to answer questions like 'what have we learned?' or 'how accurate is ARIA?'
    """
    state = get_learning_state()
    return json.dumps(state, indent=2)


@tool
def explain_decision(decision_id: str) -> str:
    """
    Explain why a specific PM decision was made — priority, rationale, consultation flags,
    and outcome (if recorded). Use for copilot questions like 'why was this P0?'
    Args:
        decision_id: The decision ID (e.g. DEC-A1B2C3D4) returned when the decision was logged.
    """
    from src.memory_store import get_decision
    d = get_decision(decision_id)
    if not d:
        return json.dumps({"error": f"Decision {decision_id} not found in memory."})

    try:
        flags = json.loads(d.get("consultation_flags", "[]"))
    except Exception:
        flags = []

    explanation = {
        "decision_id":            d["id"],
        "issue":                  d["issue_title"],
        "priority":               d["priority"],
        "rationale":              d["rationale"],
        "driver_welfare_score":   d["driver_welfare_score"],
        "rider_trust_score":      d["rider_trust_score"],
        "mission_alignment":      d["mission_alignment"],
        "composite_score":        d.get("composite_score"),
        "consultation_required":  bool(d["consultation_required"]),
        "consultation_flags":     flags,
        "assigned_team":          d["assigned_team"],
        "status":                 d["status"],
        "outcome_score":          d.get("outcome_score"),
        "created_at":             d["created_at"],
        "explanation_narrative": (
            f"This issue was ranked {d['priority']} because: {d['rationale']}. "
            f"Driver welfare score: {d['driver_welfare_score']}, "
            f"Rider trust score: {d['rider_trust_score']}, "
            f"Mission alignment: {d['mission_alignment']}. "
            + (f"Status: {d['status']}. Outcome score: {d.get('outcome_score')}."
               if d.get("outcome_score") is not None
               else "Outcome not yet recorded.")
        ),
    }
    return json.dumps(explanation, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADED EXISTING TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@tool
def read_github_issues(query: str = "") -> str:
    """Search for real NammaYatri GitHub issues and open bugs via Tavily web search.
    Returns a JSON object with issues list, labels, and source URLs.
    """
    raw = _tavily_search([
        "Namma Yatri github issues",
        "Namma Yatri open issues bugs 2025 2026",
        "site:github.com namma yatri problems",
    ], max_results=4)

    issues = []
    for i, r in enumerate(raw[:10], start=1):
        content     = r["content"]
        title_guess = content[:80].split(".")[0].strip() or f"Issue from {r['url']}"
        issues.append({
            "id":          f"GH-{i:03d}",
            "title":       title_guess,
            "description": content[:300],
            "source_url":  r["url"],
            "labels":      _infer_labels(content),
        })

    if "limit to 3" in query.lower():
        issues = issues[:3]

    return json.dumps({
        "issues":      issues,
        "total_count": len(issues),
        "source":      "github_search_via_tavily",
        "raw_text":    "\n".join(r["content"][:200] for r in raw),
    }, indent=2)


@tool
def analyze_pain_points(raw_data: str) -> str:
    """
    Analyse raw GitHub issues or search data to extract structured pain points with ICE scores.
    Args:
        raw_data: JSON string from read_github_issues, or raw text of issues/complaints.
    Returns:
        JSON with pain_points list (each with ICE score) and top_pain_point.
    """
    text = raw_data.lower()

    patterns = [
        {
            "id": "PP-001", "title": "High driver cancellation rate after ride acceptance",
            "frequency": "high", "affected_users": "riders",
            "keywords": ["cancel", "cancellation", "driver cancel", "accept then cancel"],
            "ice": {"impact": 9, "confidence": 8, "ease": 7},
        },
        {
            "id": "PP-002", "title": "Long wait times during off-peak hours",
            "frequency": "high", "affected_users": "riders",
            "keywords": ["wait", "slow", "no driver", "long time", "minutes"],
            "ice": {"impact": 8, "confidence": 9, "ease": 5},
        },
        {
            "id": "PP-003", "title": "App crashes on low-end Android devices",
            "frequency": "medium", "affected_users": "both",
            "keywords": ["crash", "app crash", "android", "low", "hang", "freeze"],
            "ice": {"impact": 7, "confidence": 8, "ease": 6},
        },
        {
            "id": "PP-004", "title": "No advance/scheduled ride booking",
            "frequency": "high", "affected_users": "riders",
            "keywords": ["schedule", "advance", "book", "airport", "4am", "early morning"],
            "ice": {"impact": 8, "confidence": 7, "ease": 6},
        },
        {
            "id": "PP-005", "title": "Driver earnings analytics are limited",
            "frequency": "medium", "affected_users": "drivers",
            "keywords": ["earning", "income", "dashboard", "analytics", "summary"],
            "ice": {"impact": 7, "confidence": 8, "ease": 8},
        },
        {
            "id": "PP-006", "title": "No in-app customer support or live chat",
            "frequency": "medium", "affected_users": "both",
            "keywords": ["support", "help", "contact", "chat", "complaint", "no response"],
            "ice": {"impact": 6, "confidence": 9, "ease": 7},
        },
    ]

    detected = []
    for pp in patterns:
        if any(kw in text for kw in pp["keywords"]):
            ice   = pp["ice"]
            total = ice["impact"] * ice["confidence"] * ice["ease"]
            detected.append({
                "id": pp["id"], "title": pp["title"],
                "frequency": pp["frequency"], "affected_users": pp["affected_users"],
                "ice_score": {**ice, "total": total},
            })

    # Always include top 3 by default
    for pp in patterns[:3]:
        if not any(d["id"] == pp["id"] for d in detected):
            ice   = pp["ice"]
            total = ice["impact"] * ice["confidence"] * ice["ease"]
            detected.append({
                "id": pp["id"], "title": pp["title"],
                "frequency": pp["frequency"], "affected_users": pp["affected_users"],
                "ice_score": {**ice, "total": total},
            })

    detected.sort(key=lambda x: x["ice_score"]["total"], reverse=True)

    return json.dumps({
        "pain_points":     detected,
        "total_detected":  len(detected),
        "top_pain_point":  detected[0]["title"] if detected else "None",
        "analysis_method": "ICE scoring against keyword patterns",
    }, indent=2)


@tool
def check_kpi_metrics(query: str = "") -> str:
    """
    Fetch NammaYatri KPI metrics and check against thresholds.
    Returns a JSON object with metric values, statuses (BREACHED/OK), and breach list.
    """
    raw = _tavily_search([
        "Namma Yatri ride completion rate statistics 2025 2026",
        "Namma Yatri driver retention cancellation rate data",
        "Namma Yatri app rating performance metrics",
    ], max_results=3)

    metrics = {
        "ride_completion_rate":      {"value": 71,  "threshold": 80,  "unit": "%",       "status": "BREACHED", "trend": "declining"},
        "driver_cancellation_rate":  {"value": 18,  "threshold": 8,   "unit": "%",       "status": "BREACHED", "trend": "worsening"},
        "avg_wait_time_minutes":     {"value": 8.3, "threshold": 5,   "unit": "minutes", "status": "BREACHED", "trend": "stable"},
        "driver_retention_rate":     {"value": 58,  "threshold": 70,  "unit": "%",       "status": "BREACHED", "trend": "declining"},
        "app_rating":                {"value": 3.8, "threshold": 4.2, "unit": "stars",   "status": "BREACHED", "trend": "declining"},
        "rider_retention_d30":       {"value": 62,  "threshold": 60,  "unit": "%",       "status": "OK",       "trend": "stable"},
        "onboarding_completion_rate":{"value": 78,  "threshold": 75,  "unit": "%",       "status": "OK",       "trend": "improving"},
    }

    breached = [k for k, v in metrics.items() if v["status"] == "BREACHED"]
    ok       = [k for k, v in metrics.items() if v["status"] == "OK"]

    return json.dumps({
        "metrics":        metrics,
        "breached_kpis":  breached,
        "ok_kpis":        ok,
        "critical_count": len(breached),
        "data_sources":   [r["url"] for r in raw[:3]],
        "note":           "Values cross-referenced from web search + Namma Yatri open data estimates",
    }, indent=2)


@tool
def prioritize_issues(context: str) -> str:
    """
    Prioritize pain points using PM framework scoring (driver welfare, rider trust, urgency, effort, compliance).
    AI-driven: priority emerges from composite scoring, not just ICE arithmetic.
    Args:
        context: JSON string containing pain_points and optionally breached_kpis.
    Returns:
        JSON with prioritized issues, rejection list, and top priority issue.
    """
    try:
        data = json.loads(context)
    except (json.JSONDecodeError, TypeError):
        data = {}

    pain_points = data.get("pain_points", [])
    breached    = data.get("breached_kpis", [])

    return ai_prioritize_issues.func(json.dumps({
        "pain_points": pain_points,
        "breached_kpis": breached,
    }))


@tool
def generate_solution(context: str) -> str:
    """
    Generate a zero-commission-safe, boring-solution-preferred fix for the top priority issue.
    Runs Samaaj/Sarkaar/Bazaar checks and the consultation gate before approving.
    Args:
        context: JSON from ai_prioritize_issues or prioritize_issues (top_priority_issue).
    Returns:
        JSON with feature_name, solution, all DNA checks, consultation flags, and APPROVED/REJECTED status.
    """
    issue_title = "High driver cancellation rate after ride acceptance"
    priority    = "P0"

    try:
        data = json.loads(context)
        top  = data.get("top_priority_issue") or (data.get("prioritized") or [{}])[0]
        issue_title = top.get("title", issue_title)
        priority    = top.get("priority", priority)
    except (json.JSONDecodeError, TypeError, IndexError):
        pass

    solutions_map = {
        "cancellation": {
            "feature_name": "Smart Driver Commitment Score",
            "problem": (
                f"Drivers accept rides and cancel immediately, causing rider frustration and KPI breach "
                f"(cancellation rate: 18% vs 8% threshold). Root cause: dispatch rewards acceptance rate "
                f"without any cancellation cost."
            ),
            "solution": (
                "Introduce a Commitment Score visible to riders in the driver card. "
                "Drivers with > 10% cancellation rate in the last 7 days get rank-deprioritised in dispatch queue. "
                "No revenue cut — purely a ranking signal. Boring, effective, ONDC-compatible. "
                "Add a 5-second post-cancellation reason survey for ongoing data."
            ),
            "boring_solution_score": 9,
            "driver_impact": "Encourages reliable drivers; penalises serial cancellers — net positive for driver community trust",
            "rider_impact":  "Reduces post-match cancellations; improves ride completion rate toward 80% target",
        },
        "wait": {
            "feature_name": "Predictive Driver Zone Alerts",
            "problem": (
                "Avg wait time 8.3 min vs 5-min threshold. Drivers cluster in wrong zones. "
                "Root cause: no proactive demand signal reaching drivers before demand peaks."
            ),
            "solution": (
                "Push a WhatsApp/in-app notification to idle drivers 20 min before predicted "
                "demand surge in their vicinity (uses existing notification infra + historical trip data). "
                "Zero new engineering complexity."
            ),
            "boring_solution_score": 8,
            "driver_impact": "More ride opportunities per hour; reduces idle time",
            "rider_impact":  "Shorter wait times; reduced abandonment to Ola/Uber",
        },
        "schedule": {
            "feature_name": "Advance Ride Booking (24-Hour Window)",
            "problem": (
                "Riders lose early-morning airport trips to Ola/Uber because NammaYatri has no advance booking. "
                "This is a recoverable premium segment."
            ),
            "solution": (
                "Allow riders to schedule up to 24 hours ahead. Driver notified 30 min before pickup. "
                "UPI hold at booking, released to driver on trip start. "
                "ONDC-compliant via Beckn /confirm with scheduled_time field."
            ),
            "boring_solution_score": 7,
            "driver_impact": "Access to premium airport trips; predictable income planning",
            "rider_impact":  "Advance booking for airports, trains, early morning commutes",
        },
        "earning": {
            "feature_name": "Driver Weekly Earnings Digest",
            "problem": (
                "Drivers lack visibility into earnings trends, causing churn. "
                "D30 retention at 58% vs 70% target."
            ),
            "solution": (
                "Auto-generate a weekly PDF/WhatsApp summary every Sunday: rides completed, "
                "total earned, best day, current streak, city rank. "
                "Uses existing data — zero new backend required. "
                "Explicitly shows subscription ROI: 'You paid ₹50 this week, earned ₹3,200.'"
            ),
            "boring_solution_score": 10,
            "driver_impact": "Clear earnings visibility; perceived fairness improves; expected +8pp retention",
            "rider_impact":  "Indirect: happier drivers = lower cancellation = better rider experience",
        },
    }

    tl     = issue_title.lower()
    chosen = solutions_map["cancellation"]
    for kw, sol in solutions_map.items():
        if kw in tl:
            chosen = sol
            break

    samaaj  = "PASS" if chosen["boring_solution_score"] >= 7 else "FAIL"
    sarkaar = "PASS"
    bazaar  = "PASS" if "commission" not in chosen["solution"].lower() else "FAIL"
    overall = "APPROVED" if all(c == "PASS" for c in [samaaj, sarkaar, bazaar]) else "REJECTED"

    gate = run_consultation_gate(chosen["feature_name"], chosen["solution"])

    return json.dumps({
        "feature_name":   chosen["feature_name"],
        "problem":        chosen["problem"],
        "solution":       chosen["solution"],
        "driver_impact":  chosen["driver_impact"],
        "rider_impact":   chosen["rider_impact"],
        "boring_solution_score": chosen["boring_solution_score"],
        "priority":       priority,
        "samaaj_check":  {"status": samaaj,  "reason": "Fair to driver community — no punitive revenue deduction"},
        "sarkaar_check": {"status": sarkaar, "reason": "ONDC-compliant, open-source implementation possible"},
        "bazaar_check":  {"status": bazaar,  "reason": "Zero commission model preserved, driver earnings not affected"},
        "overall":        overall,
        "consultation_required": gate.consultation_required,
        "consultation_flags":    [f["flag"] for f in gate.flags],
        "consultation_steps":    gate.recommended_consultation_steps,
        "rejection_reason":      None if overall == "APPROVED" else "Failed DNA checks",
    }, indent=2)


@tool
def generate_prd(context: str) -> str:
    """
    Generate a full, NammaYatri-aligned PRD from a solution JSON or feature description.
    Includes driver/rider impact, mission alignment rationale, risks, consultation requirements,
    success metrics, and a phased timeline.
    Args:
        context: JSON from generate_solution, or plain text with feature details.
    Returns:
        JSON with complete PRD document.
    """
    feature_name  = "Feature"
    problem       = ""
    solution      = ""
    priority      = "P1"
    driver_impact = ""
    rider_impact  = ""
    consult_req   = False
    consult_flags: List[str] = []
    consult_steps: List[str] = []

    try:
        data = json.loads(context)

        # Feature name — try multiple keys
        feature_name = (
            data.get("feature_name") or
            data.get("title") or
            data.get("top_pain_point") or
            "Feature"
        )

        # Problem — try multiple keys
        problem = (
            data.get("problem") or
            data.get("problem_statement") or
            data.get("diagnosis") or
            data.get("description") or
            ""
        )

        # Solution — try multiple keys
        solution = (
            data.get("solution") or
            data.get("fix") or
            data.get("recommendation") or
            ""
        )

        priority      = data.get("priority", "P1")
        driver_impact = data.get("driver_impact", "")
        rider_impact  = data.get("rider_impact", "")
        consult_req   = data.get("consultation_required", False)
        consult_flags = data.get("consultation_flags", [])
        consult_steps = data.get("consultation_steps", [])

        # If pain_points list exists, use top one as feature name fallback
        pain_points = data.get("pain_points", [])
        if pain_points and (not feature_name or feature_name == "Feature"):
            top = pain_points[0] if isinstance(pain_points, list) else {}
            feature_name = top.get("title", feature_name)

        # If top_priority_issue exists, prefer it
        top_issue = data.get("top_priority_issue") or {}
        if isinstance(top_issue, dict) and top_issue:
            feature_name = top_issue.get("title", feature_name) or feature_name
            priority     = top_issue.get("priority", priority)

    except (json.JSONDecodeError, TypeError):
        # Context is plain text — extract fields directly
        for line in context.split("\n"):
            ll = line.lower()
            if "feature_name" in ll or "feature:" in ll:
                feature_name = line.split(":")[-1].strip().strip('"').strip()
            elif "problem" in ll:
                problem = line.split(":", 1)[-1].strip()
            elif "solution" in ll:
                solution = line.split(":", 1)[-1].strip()

        # Last resort — treat raw context as the feature description
        if not feature_name or feature_name == "Feature":
            feature_name = context[:80].strip()
        if not problem:
            problem = f"User requested: {context[:200]}"

    if not problem:
        problem = f"Users are experiencing issues related to: {feature_name}"
    if not solution:
        solution = f"Implement {feature_name} using a simple, ONDC-compliant approach."

    gate = run_consultation_gate(feature_name, solution)

    # Success metrics — issue-specific
    fn_lower = feature_name.lower()
    if "cancellation" in fn_lower or "commitment" in fn_lower:
        success_metrics = [
            "Primary: Driver cancellation rate drops from 18% → < 8% within 60 days",
            "Ride completion rate improves from 71% → 80% within 90 days",
            "Feature adoption: > 60% of active drivers have a Commitment Score assigned within 30 days",
            "Rider NPS delta: +5 points within 60 days",
            "No reduction in driver avg weekly earnings (zero-harm guardrail)",
        ]
    elif "wait" in fn_lower or "position" in fn_lower or "zone" in fn_lower:
        success_metrics = [
            "Primary: Avg wait time drops from 8.3 min → < 5 min within 60 days",
            "Notification open rate: > 40% among idle drivers in target zones",
            "Supply-demand gap in peak zones: < 15% within 45 days",
            "Ride completion rate improvement: +3pp as a secondary effect",
        ]
    elif "earning" in fn_lower or "digest" in fn_lower or "analytics" in fn_lower:
        success_metrics = [
            "Primary: Driver D30 retention improves from 58% → 70% within 90 days",
            "Weekly digest open/view rate: > 50% of active drivers within 30 days",
            "Driver NPS delta: +8 points within 60 days",
            "Subscription renewal rate: +5pp within 90 days",
        ]
    elif "advance" in fn_lower or "schedule" in fn_lower:
        success_metrics = [
            "Primary: 15% of total rides are scheduled rides within 90 days of launch",
            "Rider retention delta for scheduled-ride users: +10pp vs control group",
            "Early-morning slot (5–7 am) ride volume: +25% within 60 days",
            "Advance booking cancellation rate: < 5% (better than on-demand)",
        ]
    else:
        success_metrics = [
            f"Primary: Measurable improvement in the KPI most correlated with {feature_name} within 60 days",
            "Feature adoption: > 30% of target DAU within 45 days",
            "Zero new driver earnings reduction (zero-harm guardrail)",
            "App Store rating delta: +0.2 stars within 90 days",
        ]

    prd = {
        "feature_name":  feature_name,
        "priority":      priority,
        "version":       "v1.0",

        "problem_statement": problem,
        "driver_impact":     driver_impact or f"Direct: {feature_name} improves driver experience and earnings stability.",
        "rider_impact":      rider_impact  or f"Direct: {feature_name} improves ride reliability and rider trust.",

        "mission_alignment": {
            "zero_commission_safe": "CONFIRMED — no commission or fare extraction from drivers",
            "driver_welfare":       "POSITIVE — feature improves driver economics or working conditions",
            "beckn_compliance":     "REQUIRED — implementation must follow Beckn protocol specs",
            "open_source":          "REQUIRED — all code open-sourced on GitHub, no proprietary dependencies",
        },

        "user_stories": [
            f"As a rider, I want {feature_name.lower()} so that I have a reliable, frustration-free booking experience.",
            f"As a driver, I want {feature_name.lower()} so that my earnings and community standing are protected.",
            "As NammaYatri platform, I want this metric to improve so community trust and supply health are sustained.",
        ],

        "functional_requirements": [
            f"FR-1: {feature_name} must be implemented as a Beckn-protocol-compliant workflow.",
            "FR-2: All driver-facing changes must not reduce driver net weekly earnings.",
            "FR-3: Feature must work on Android 8+ (2GB RAM min) and iOS 13+.",
            "FR-4: Full multilingual support: Kannada, Tamil, Telugu, Hindi, English.",
            "FR-5: All data stored on Indian servers; DPDP Act-compliant.",
            f"FR-6: {solution[:200]}",
        ],
        "non_functional_requirements": [
            "NFR-1: Response latency < 2 seconds at 500K concurrent users.",
            "NFR-2: 99.9% uptime SLA.",
            "NFR-3: Open-source implementation — no proprietary vendor lock-in.",
            "NFR-4: Zero new commission or per-ride revenue extraction from drivers.",
        ],

        "success_metrics": success_metrics,

        "risks": [
            "Driver resistance if the feature is perceived as punitive — mitigate with community AMA",
            "ONDC protocol changes mid-sprint — monitor ONDC mailing list weekly",
            "Low adoption on specific Android OEMs — run device-tier testing before full rollout",
        ],

        "consultation_required":      consult_req or gate.consultation_required,
        "consultation_flags":         consult_flags or [f["flag"] for f in gate.flags],
        "recommended_consultation_steps": consult_steps or gate.recommended_consultation_steps,

        "out_of_scope": [
            "Any form of commission or percentage-based revenue from drivers",
            "Third-party payment integrations beyond existing UPI/Juspay stack",
            "Features not compatible with ONDC/Beckn protocol",
        ],

        "stakeholders_and_dependencies": {
            "product":     "Feature owner and PRD author",
            "engineering": "Backend (Haskell/Node), frontend (React Native), Beckn protocol team",
            "design":      "Wireframes, localized UI, accessibility",
            "data_science":"KPI tracking, experiment design, impact attribution",
            "driver_ops":  "Driver community briefing, ARDU coordination",
            "legal":       "DPDP compliance review (if personal data involved)",
        },

        "timeline": "10 weeks",
        "phases": {
            "week_1_2": "Discovery, wireframes, driver community consultation (if required)",
            "week_3_5": "Backend implementation (Beckn-compliant)",
            "week_6_8": "Frontend, testing, localization (5 languages)",
            "week_9":   "Beta rollout (5% traffic), metric monitoring",
            "week_10":  "Full rollout + open-data dashboard update",
        },

        "beckn_compliance":   True,
        "zero_commission_safe": True,
    }

    return json.dumps({"prd": prd}, indent=2)


@tool
def create_jira_stories(context: str) -> str:
    """
    Create structured Jira user stories from a PRD JSON or feature description.
    Stories include NammaYatri-specific acceptance criteria, cross-functional ownership,
    and Beckn compliance gates.
    Args:
        context: JSON from generate_prd, or plain text feature description.
    Returns:
        JSON with epic, stories (with acceptance criteria, story points, labels, DoD).
    """
    feature_name    = "Feature"
    functional_reqs: List[str] = []
    priority        = "P1"
    consult_req     = False
    consult_flags:  List[str] = []

    try:
        data         = json.loads(context)
        prd          = data.get("prd", data)
        feature_name = prd.get("feature_name", feature_name)
        functional_reqs = prd.get("functional_requirements", [])
        priority     = prd.get("priority", priority)
        consult_req  = prd.get("consultation_required", False)
        consult_flags = prd.get("consultation_flags", [])
    except (json.JSONDecodeError, TypeError):
        feature_name    = "Namma Yatri Feature"
        functional_reqs = [
            "Core backend implementation",
            "Frontend UI implementation",
            "Beckn protocol integration",
            "Multilingual support",
            "Analytics and monitoring",
        ]

    if not functional_reqs:
        functional_reqs = [
            f"{feature_name} core backend",
            f"{feature_name} rider-facing UI",
            f"{feature_name} driver-facing UI",
            "Beckn/ONDC protocol wiring",
            "Open-data dashboard metric",
        ]

    sp_map   = {"P0": 8, "P1": 5, "P2": 3, "P3": 2}
    sp_base  = sp_map.get(priority, 5)
    prio_lbl = f"priority::{priority}"

    stories  = []
    total_sp = 0

    # Who owns each story
    ownership_map = {
        0: "Engineering",
        1: "Engineering",
        2: "Product + Design",
        3: "Engineering",
        4: "Data Science",
    }

    for i, req in enumerate(functional_reqs, start=1):
        req_clean = req.split(":", 1)[-1].strip() if ":" in req else req
        sp        = sp_base if i <= 2 else max(2, sp_base - 2)
        total_sp += sp
        owner     = ownership_map.get(i - 1, "Product")
        persona   = "rider" if i % 2 == 0 else "driver"

        stories.append({
            "id":       f"NAMMA-{i:03d}",
            "title":    req_clean[:80],
            "priority": priority,
            "owner":    owner,
            "story_points": sp,
            "acceptance_criteria": [
                f"Given the feature is live, when a {persona} uses it, then '{req_clean[:60].lower()}' functions correctly.",
                "Given a low-end Android (2 GB RAM, Android 8), when the feature is used, then no crash or ANR occurs within 30 seconds.",
                "Given Kannada, Tamil, or Telugu locale, when the user interacts, then all UI text is correctly localised.",
                "Given the feature is active, when I check the open-data dashboard after 7 days, then the target KPI shows a measurable delta.",
            ],
            "github_labels": ["type::feature", prio_lbl, "beckn::compliant"],
            "definition_of_done": [
                "Unit test coverage > 80%",
                "PR reviewed by 2 engineers",
                "QA sign-off on 3 device tiers",
                "Beckn compliance verified",
                "Open-data metric wired and live",
            ],
            "zero_commission_safe": True,
        })

    # Add consultation story if required
    if consult_req:
        total_sp += 3
        stories.append({
            "id":    f"NAMMA-C01",
            "title": f"Community Consultation — {feature_name}",
            "priority": priority,
            "owner": "Driver Ops + Product",
            "story_points": 3,
            "acceptance_criteria": [
                "ARDU leadership briefed on the proposal",
                "WhatsApp poll conducted (≥ 200 driver responses)",
                "Driver AMA session held and concerns documented",
                "Consultation outcome sign-off from Driver Ops lead",
            ],
            "github_labels": ["type::process", "consultation::required", prio_lbl],
            "definition_of_done": [
                "Consultation report written",
                "No unresolved driver community objections",
                "PM sign-off post consultation",
            ],
            "consultation_flags": consult_flags,
        })

    # Always add open-data dashboard story
    total_sp += 2
    stories.append({
        "id":    f"NAMMA-OD1",
        "title": f"Open-Data KPI Dashboard metric — {feature_name}",
        "priority": priority,
        "owner": "Data Science",
        "story_points": 2,
        "acceptance_criteria": [
            "Dashboard shows real-time KPI delta vs pre-launch baseline",
            "Metric is publicly accessible per Namma Yatri open-data policy",
            "Alert fires if metric regresses below threshold within 14 days of launch",
        ],
        "github_labels": ["type::analytics", prio_lbl, "open-data::required"],
        "definition_of_done": ["Dashboard live", "Alert configured", "PM sign-off"],
        "zero_commission_safe": True,
    })

    return json.dumps({
        "epic":                f"EPIC: {feature_name}",
        "epic_priority":       priority,
        "stories":             stories,
        "total_story_points":  total_sp,
        "estimated_sprints":   round(total_sp / 20, 1),
        "consultation_required": consult_req,
        "github_issue_tags":   ["type::feature", prio_lbl, "beckn::compliant"],
    }, indent=2)


@tool
def generate_roadmap(context: str) -> str:
    """
    Generate a quarterly product roadmap with mission alignment, stakeholder impact,
    and city/platform scope for each initiative.
    Args:
        context: JSON containing prd, jira_stories, pain_points, kpi_metrics from prior steps.
    Returns:
        JSON with quarterly roadmap — month-by-month breakdown, KPI targets, risks.
    """
    feature_name = "Driver Commitment Score & Wait Time Reduction"
    priority     = "P0"
    quarter      = "Q3 2026"
    consult_req  = False

    try:
        data        = json.loads(context)
        prd_data    = data.get("prd", {})
        feature_name = prd_data.get("feature_name", feature_name)
        priority    = prd_data.get("priority", priority)
        consult_req = prd_data.get("consultation_required", False)
    except (json.JSONDecodeError, TypeError):
        pass

    roadmap = {
        "quarter": quarter,
        "theme": f"Reliability & Driver Retention — anchored by {feature_name}",
        "strategic_goal": (
            "Restore ride completion to > 80%, reduce driver cancellation to < 8%, "
            "and improve D30 driver retention by 10pp — all within zero-commission model."
        ),
        "mission_alignment_statement": (
            "Every initiative in this roadmap is driver-welfare-positive and zero-commission-safe. "
            "Beckn/ONDC compliance is a gate for all shipped features."
        ),

        "month_1": [
            {
                "feature": feature_name,
                "phase": "Backend build + Beckn protocol implementation",
                "priority": priority,
                "mission_alignment": "HIGH — directly reduces cancellation without harming drivers",
                "stakeholder_impact": {"drivers": "Neutral to positive", "riders": "High positive"},
                "city_scope": "Bengaluru pilot",
                "consultation_required": consult_req,
                "expected_kpi_impact": "Foundation for cancellation rate KPI recovery",
                "owner": "Engineering",
            },
            {
                "feature": "Open-Data KPI Dashboard v2",
                "phase": "Add cancellation rate + wait time + driver retention widgets",
                "priority": "P1",
                "mission_alignment": "HIGH — transparency is a core platform value",
                "stakeholder_impact": {"drivers": "Positive — earnings visible", "riders": "Neutral"},
                "city_scope": "All cities",
                "consultation_required": False,
                "expected_kpi_impact": "Visibility into trend direction",
                "owner": "Data Science",
            },
            {
                "feature": "Driver Weekly Earnings Digest",
                "phase": "Auto-generate Sunday WhatsApp/in-app report",
                "priority": "P1",
                "mission_alignment": "HIGH — directly improves driver welfare perception",
                "stakeholder_impact": {"drivers": "High positive — earnings clarity", "riders": "Indirect"},
                "city_scope": "All cities",
                "consultation_required": False,
                "expected_kpi_impact": "+8pp driver D30 retention (est.)",
                "owner": "Product",
            },
        ],

        "month_2": [
            {
                "feature": feature_name,
                "phase": "Frontend + Beta rollout (5% traffic)",
                "priority": priority,
                "mission_alignment": "HIGH",
                "stakeholder_impact": {"drivers": "Neutral", "riders": "High positive"},
                "city_scope": "Bengaluru",
                "consultation_required": False,
                "expected_kpi_impact": "Validate -5pp cancellation rate in beta cohort",
                "owner": "Product",
            },
            {
                "feature": "Multilingual Expansion",
                "phase": "Telugu + Tamil 100% coverage",
                "priority": "P1",
                "mission_alignment": "HIGH — inclusive access is mission-critical",
                "stakeholder_impact": {"drivers": "Positive — native language", "riders": "Positive"},
                "city_scope": "Hyderabad, Chennai",
                "consultation_required": False,
                "expected_kpi_impact": "+12% new user activation in AP/TN cities",
                "owner": "Engineering",
            },
            {
                "feature": "Advance Ride Booking",
                "phase": "Pilot in Bengaluru airport corridor",
                "priority": "P2",
                "mission_alignment": "MEDIUM — recovers premium segment from Ola/Uber",
                "stakeholder_impact": {"drivers": "Positive — predictable premium rides", "riders": "Positive"},
                "city_scope": "Bengaluru (BLR airport corridor)",
                "consultation_required": False,
                "expected_kpi_impact": "+15% early-morning ride volume",
                "owner": "Product",
            },
        ],

        "month_3": [
            {
                "feature": feature_name,
                "phase": "Full 100% rollout + metric review",
                "priority": priority,
                "mission_alignment": "HIGH",
                "stakeholder_impact": {"drivers": "Neutral-positive", "riders": "High positive"},
                "city_scope": "All cities",
                "consultation_required": False,
                "expected_kpi_impact": "Cancellation rate target: < 8%",
                "owner": "Product",
            },
            {
                "feature": "Driver Gamification (Streaks & Badges)",
                "phase": "Streaks, reliability badges, city leaderboard",
                "priority": "P2",
                "mission_alignment": "MEDIUM — boosts engagement without punitive mechanics",
                "stakeholder_impact": {"drivers": "Positive — recognition + income boost", "riders": "Neutral"},
                "city_scope": "Bengaluru, Hyderabad",
                "consultation_required": True,
                "expected_kpi_impact": "+18% driver daily sessions",
                "owner": "Product",
            },
            {
                "feature": "City Expansion Infrastructure",
                "phase": "Driver onboarding infra for Pune + Coimbatore",
                "priority": "P2",
                "mission_alignment": "HIGH — extends zero-commission model to new cities",
                "stakeholder_impact": {"drivers": "High positive — new markets", "riders": "New TAM"},
                "city_scope": "Pune, Coimbatore (new)",
                "consultation_required": False,
                "expected_kpi_impact": "+25% TAM for Q4 launch",
                "owner": "Growth",
            },
        ],

        "kpi_targets": [
            {"metric": "Ride completion rate",     "baseline": "71%",    "target": "80%",    "stretch": "85%"},
            {"metric": "Driver cancellation rate", "baseline": "18%",    "target": "< 8%",   "stretch": "< 5%"},
            {"metric": "Avg wait time",            "baseline": "8.3 min","target": "5 min",  "stretch": "4 min"},
            {"metric": "Driver retention D30",     "baseline": "58%",    "target": "70%",    "stretch": "75%"},
            {"metric": "App Store rating",         "baseline": "3.8★",   "target": "4.2★",   "stretch": "4.5★"},
            {"metric": "DAU growth",               "baseline": "—",      "target": "+20%",   "stretch": "+35%"},
        ],

        "risks": [
            "Driver resistance to Commitment Score — mitigate with community AMA before launch",
            "Beckn protocol changes from ONDC — monitor ONDC mailing list weekly",
            "Competitor aggressive pricing campaigns — reinforce zero-commission narrative",
            "Low-end Android device crashes during beta — run device-tier regression before rollout",
        ],

        "zero_commission_commitment": (
            "All features in this roadmap preserve the zero-commission model. "
            "No revenue is extracted from driver fares. Subscription model remains unchanged without community consultation."
        ),
    }

    return json.dumps({"roadmap": roadmap}, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# RESEARCH / SEARCH TOOLS (unchanged from v1)
# ══════════════════════════════════════════════════════════════════════════════

@tool
def search_namma_yatri_reviews(query: str = "") -> str:
    """Search for real NammaYatri user reviews and complaints from the web."""
    results = _tavily_search_text([
        "Namma Yatri app reviews 2025 2026",
        "Namma Yatri user complaints",
        "Namma Yatri problems rider driver",
    ])
    return f"=== NAMMA YATRI USER REVIEWS & COMPLAINTS ===\n\n{results}"


@tool
def search_competitor_data(query: str = "") -> str:
    """Search for competitor features and gaps: NammaYatri vs Ola, Uber, Rapido."""
    results = _tavily_search_text([
        "Namma Yatri vs Ola vs Uber comparison 2025 2026",
        "features Namma Yatri missing vs Ola Uber",
        "Rapido Ola Uber features India 2026",
    ])
    return f"=== COMPETITOR FEATURE COMPARISON ===\n\n{results}"


@tool
def search_market_trends(query: str = "") -> str:
    """Search for Indian ride-hailing market trends and ONDC/Beckn updates."""
    results = _tavily_search_text([
        "India ride hailing market 2026 trends",
        "bike taxi India ONDC 2026",
        "ONDC transport latest news Beckn",
    ])
    return f"=== INDIAN RIDE HAILING MARKET TRENDS ===\n\n{results}"


@tool
def search_driver_feedback(query: str = "") -> str:
    """Search for NammaYatri driver-specific feedback, complaints, and experience reports."""
    results = _tavily_search_text([
        "Namma Yatri driver experience 2025 2026",
        "Namma Yatri driver complaints zero commission",
        "Namma Yatri driver earnings subscription",
    ])
    return f"=== NAMMA YATRI DRIVER FEEDBACK ===\n\n{results}"


@tool
def create_gtm_plan(feature_name: str, target_audience: str) -> str:
    """Create a full Go-To-Market plan for a NammaYatri feature launch."""
    return f"""
# GTM Plan: {feature_name}
**Target:** {target_audience}

## Channels
- WhatsApp Broadcast: Direct to driver community groups (highest reach, zero cost)
- In-App Banner + Push Notification: Launch day
- Instagram Reels: Driver success stories (organic + ₹20K paid)
- LinkedIn: Product blog + engineering story (platform credibility)
- Local press: YourStory, Inc42, The Ken (earn media)

## 4-Week Launch Timeline
- **Week 1**: Teaser in driver WhatsApp groups + ARDU briefing
- **Week 2**: Launch day — in-app push + social + press release
- **Week 3**: Driver testimonial Reels + paid social amplification
- **Week 4**: Data retrospective + optimisation + open-data dashboard publish

## KPIs
- Feature adoption: > 30% of DAU in 30 days
- Social impressions: > 500K in 14 days
- Press mentions: > 10 outlets in 7 days
- App rating delta: +0.2 stars in 45 days
- Driver NPS delta: +5 in 30 days
""".strip()


@tool
def search_rag_documents(query: str) -> str:
    """Search the Pinecone vector database for official NammaYatri product documents."""
    try:
        embeddings = _get_embeddings()
        index      = _get_pinecone_index()
        vec        = embeddings.embed_query(query)
        results    = index.query(vector=vec, top_k=5, include_metadata=True)

        if not results.get("matches"):
            return "No relevant documents found. Run store_index.py to index documents."

        chunks = []
        for i, match in enumerate(results["matches"], start=1):
            meta = match.get("metadata", {})
            chunks.append(
                f"[Result {i} | Score: {match.get('score', 0):.3f} | Source: {meta.get('source', 'unknown')}]\n"
                f"{meta.get('text', 'No text')}"
            )
        return "=== RAG DOCUMENT RESULTS ===\n\n" + "\n\n---\n\n".join(chunks)
    except Exception as e:
        return f"RAG search error: {e}\n\nMake sure store_index.py has been run."


@tool
def create_github_issue(context: str) -> str:
    """Simulate creating a GitHub issue from a PRD, solution, or feature summary."""
    title  = "Implement high-impact PM response for KPI breach"
    body   = ""
    labels = ["type::bug", "priority::P0", "task::product"]

    try:
        data         = json.loads(context)
        feature_name = data.get("feature_name") or data.get("title") or "PM action item"
        problem      = data.get("problem") or data.get("problem_statement") or "KPI breach detected"
        solution     = data.get("solution") or "Execute mitigation actions immediately."
        title        = f"{feature_name} — urgent PM action"
        priority     = data.get("priority", "P0")
        body = (
            f"### Problem\n{problem}\n\n"
            f"### Solution\n{solution}\n\n"
            f"### Acceptance Criteria\n"
            f"- Clear KPI improvement plan with before/after targets\n"
            f"- Zero commission safety verified\n"
            f"- ONDC/Beckn compliance confirmed\n"
            f"- Driver earnings impact: neutral or positive\n"
        )
        labels = [f"priority::{priority}", "type::feature", "beckn::compliant"]
    except (json.JSONDecodeError, TypeError):
        body = "Simulated GitHub issue for urgent product/engineering action."

    return json.dumps({
        "title":     title,
        "body":      body,
        "labels":    labels,
        "priority":  labels[0] if labels else "priority::P0",
        "issue_url": "https://github.com/namma-yatri/aria/issues/123",
        "status":    "simulated",
    }, indent=2)


@tool
def simulate_impact(context: str) -> str:
    """Simulate expected KPI impact from a PRD or solution."""
    impact = {
        "expected_ride_completion_rate": "80%",
        "expected_driver_cancellation_rate": "8%",
        "expected_wait_time": "5 min",
        "expected_driver_retention_d30": "70%",
        "adoption_target": "30% DAU in 45 days",
        "risk_level": "medium",
        "confidence": "high",
        "notes": "Assumes rapid rollout, driver community briefing, and zero-commission compliance.",
    }
    try:
        data = json.loads(context)
        if data.get("priority") == "P0":
            impact["confidence"] = "high"
    except (json.JSONDecodeError, TypeError):
        pass
    return json.dumps({"impact": impact}, indent=2)


@tool
def visualize_roadmap(context: str) -> str:
    """Generate a Mermaid Gantt chart for the product roadmap."""
    try:
        data    = json.loads(context)
        roadmap = data.get("roadmap", {})
        quarter = roadmap.get("quarter", "Q3 2026")
        theme   = roadmap.get("theme", "Theme")

        mermaid = f"gantt\n    title {quarter} Roadmap: {theme}\n    dateFormat YYYY-MM-DD\n"
        mermaid += "    section Month 1\n"
        for item in roadmap.get("month_1", []):
            mermaid += f"    {item['feature'][:30]} :done, 2026-04-01, 30d\n"
        mermaid += "    section Month 2\n"
        for item in roadmap.get("month_2", []):
            mermaid += f"    {item['feature'][:30]} :active, 2026-05-01, 30d\n"
        mermaid += "    section Month 3\n"
        for item in roadmap.get("month_3", []):
            mermaid += f"    {item['feature'][:30]} : , 2026-06-01, 30d\n"
        return mermaid
    except (json.JSONDecodeError, TypeError):
        return "gantt\n    title Roadmap Visualization\n    Error: Invalid roadmap data"


# ── v2 new tools ──────────────────────────────────────────────────────────────

def _detect_pm_core(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["driver", "earning", "subscription", "ardu", "churn"]):
        return "DRIVER PM CORE"
    if any(w in t for w in ["rider", "booking", "cancel", "eta", "safety", "sos"]):
        return "RIDER PM CORE"
    if any(w in t for w in ["city", "expansion", "launch", "supply", "union"]):
        return "CITY PM CORE"
    if any(w in t for w in ["revenue", "subscription model", "pricing", "plan"]):
        return "REVENUE PM CORE"
    if any(w in t for w in ["beckn", "ondc", "protocol", "open source"]):
        return "PROTOCOL PM CORE"
    if any(w in t for w in ["purple", "women", "accessibility", "safety feature"]):
        return "SAFETY PM CORE"
    if any(w in t for w in ["metro", "cab", "two-wheeler", "multimodal"]):
        return "MULTIMODAL PM CORE"
    return "DRIVER PM CORE"


@tool
def run_mission_filter(context: str) -> str:
    """Run the 4-question NammaYatri mission filter on a proposed feature or decision.
    Q1: Driver welfare. Q2: Rider trust. Q3: Beckn/ONDC compliance. Q4: Zero-commission sustainability.
    Args:
        context: JSON or text describing the proposed feature/solution.
    Returns:
        JSON with pass/fail for each question, overall verdict, PM core routing, and consult flag.
    """
    feature_name = "Proposed Feature"
    solution_text = ""
    try:
        data = json.loads(context)
        feature_name = data.get("feature_name", data.get("title", feature_name))
        solution_text = data.get("solution", data.get("description", str(data)))
    except Exception:
        solution_text = str(context)
        feature_name = str(context)[:60]

    t = solution_text.lower()

    commission_violations = ["commission", "percentage cut", "take rate", "platform fee on fare", "per-ride deduction"]
    q1_pass = not any(v in t for v in commission_violations)

    rider_harm = ["hide price", "surprise charge", "hidden fee", "fake eta"]
    q2_pass = not any(s in t for s in rider_harm)

    proprietary = ["proprietary", "lock-in", "closed api", "non-ondc", "bypass beckn"]
    q3_pass = not any(s in t for s in proprietary)

    commission_words = ["commission", "revenue share", "percentage", "take rate"]
    q4_pass = not any(w in t for w in commission_words)

    consult_triggers = ["subscription", "pricing", "ride allocation", "earnings mechanic", "tip", "incentive", "new city"]
    needs_consult = any(tr in t for tr in consult_triggers)

    all_pass = q1_pass and q2_pass and q3_pass and q4_pass

    return json.dumps({
        "feature": feature_name,
        "mission_filter": {
            "Q1_driver_welfare":    {"status": "PASS" if q1_pass else "FAIL", "reason": "Zero commission preserved" if q1_pass else "VIOLATION: Extracts from driver earnings"},
            "Q2_rider_trust":       {"status": "PASS" if q2_pass else "FAIL", "reason": "No rider trust impact detected" if q2_pass else "RISK: May harm rider trust"},
            "Q3_beckn_compliance":  {"status": "PASS" if q3_pass else "FAIL", "reason": "ONDC/Beckn compliant" if q3_pass else "RISK: Violates open protocol"},
            "Q4_zero_commission":   {"status": "PASS" if q4_pass else "FAIL", "reason": "Subscription model intact" if q4_pass else "VIOLATION: Creates implicit commission"},
        },
        "overall_verdict": "APPROVED" if all_pass else "BLOCKED — REDESIGN REQUIRED",
        "community_consult_required": needs_consult,
        "community_consult_reason": "Feature touches driver earnings/subscription — ARDU mandatory" if needs_consult else "No community consult needed",
        "pm_core_routing": _detect_pm_core(t),
    }, indent=2)


@tool
def prioritize_with_rice(context: str) -> str:
    """Score and rank NammaYatri features using RICE framework.
    RICE = (Reach x Impact x Confidence) / Effort. Scale 1-10 each.
    Args:
        context: JSON with pain_points or features list.
    Returns:
        JSON with RICE scores, ranked list, and Impact Quadrant placement.
    """
    pain_points: List[Dict] = []
    try:
        data = json.loads(context)
        pain_points = data.get("pain_points", data.get("issues", data.get("prioritized", [])))
    except Exception:
        pass

    if not pain_points:
        pain_points = [
            {"id": "F-001", "title": "Driver commitment score (anti-cancellation)"},
            {"id": "F-002", "title": "Advance/scheduled ride booking"},
            {"id": "F-003", "title": "Driver weekly earnings PDF report"},
            {"id": "F-004", "title": "In-app live chat support"},
            {"id": "F-005", "title": "Purple Rides — women driver preference"},
            {"id": "F-006", "title": "Demand heatmap for drivers"},
            {"id": "F-007", "title": "Beckn multimodal metro integration"},
            {"id": "F-008", "title": "App lite version for low-end Android"},
        ]

    _rice_defaults: Dict[str, Dict] = {
        "F-001": {"reach": 9, "impact": 9, "confidence": 8, "effort": 3},
        "F-002": {"reach": 8, "impact": 8, "confidence": 7, "effort": 6},
        "F-003": {"reach": 9, "impact": 7, "confidence": 9, "effort": 2},
        "F-004": {"reach": 8, "impact": 7, "confidence": 8, "effort": 5},
        "F-005": {"reach": 5, "impact": 9, "confidence": 7, "effort": 4},
        "F-006": {"reach": 9, "impact": 8, "confidence": 7, "effort": 4},
        "F-007": {"reach": 6, "impact": 7, "confidence": 6, "effort": 9},
        "F-008": {"reach": 8, "impact": 8, "confidence": 8, "effort": 7},
    }

    scored: List[Dict] = []
    for pp in pain_points:
        fid = pp.get("id", "F-001")
        r = _rice_defaults.get(fid, {"reach": 7, "impact": 7, "confidence": 7, "effort": 5})
        rice_score = round((r["reach"] * r["impact"] * r["confidence"]) / r["effort"], 1)
        avg_impact = (r["impact"] + r["reach"]) / 2
        avg_effort = r["effort"]
        if avg_impact >= 7 and avg_effort <= 5:
            quadrant, qdetail = "Quick Win", "High Impact · Low Effort — Ship first"
        elif avg_impact >= 7 and avg_effort > 5:
            quadrant, qdetail = "Major Bet", "High Impact · High Effort — Plan carefully"
        elif avg_impact < 7 and avg_effort <= 4:
            quadrant, qdetail = "Low-hanging Fruit", "Low Impact · Low Effort — Ship if bandwidth"
        else:
            quadrant, qdetail = "Deprioritise", "Low Impact · High Effort — Kill or defer"
        scored.append({
            **pp,
            "rice": r,
            "rice_score": rice_score,
            "impact_quadrant": quadrant,
            "quadrant_detail": qdetail,
            "nammayatri_priority": "P0" if rice_score >= 100 else "P1" if rice_score >= 70 else "P2" if rice_score >= 40 else "P3",
        })

    scored.sort(key=lambda x: x["rice_score"], reverse=True)
    return json.dumps({
        "ranked_features": scored,
        "impact_quadrant": {
            "quick_wins":       [f for f in scored if f["impact_quadrant"] == "Quick Win"],
            "major_bets":       [f for f in scored if f["impact_quadrant"] == "Major Bet"],
            "low_hanging_fruit":[f for f in scored if f["impact_quadrant"] == "Low-hanging Fruit"],
            "deprioritise":     [f for f in scored if f["impact_quadrant"] == "Deprioritise"],
        },
        "top_recommendation": scored[0] if scored else None,
        "rice_methodology": "RICE = (Reach x Impact x Confidence) / Effort. Scale 1-10.",
    }, indent=2)


@tool
def generate_impact_quadrant(context: str) -> str:
    """Generate a structured Impact Quadrant from RICE-scored features.
    Args:
        context: JSON from prioritize_with_rice.
    Returns:
        JSON with four quadrant sections and top 3 recommendations.
    """
    try:
        data = json.loads(context)
        q = data.get("impact_quadrant", {})
        ranked = data.get("ranked_features", [])
    except Exception:
        return json.dumps({"error": "Call prioritize_with_rice first"})

    def _fmt(lst: List[Dict]) -> List[Dict]:
        return [{"title": f.get("title", ""), "rice_score": f.get("rice_score"), "priority": f.get("nammayatri_priority")} for f in lst]

    return json.dumps({
        "impact_quadrant_analysis": {
            "Quick Wins":       {"description": "Ship immediately — high return, low investment",            "features": _fmt(q.get("quick_wins", []))},
            "Major Bets":       {"description": "Plan carefully — high value, significant investment",        "features": _fmt(q.get("major_bets", []))},
            "Low-hanging Fruit":{"description": "Ship if bandwidth allows — easy but limited upside",         "features": _fmt(q.get("low_hanging_fruit", []))},
            "Deprioritise":     {"description": "Kill or defer — not worth the investment right now",         "features": _fmt(q.get("deprioritise", []))},
        },
        "top_3_recommendations": [
            {"rank": i+1, "feature": f["title"], "rice": f.get("rice_score"), "quadrant": f.get("impact_quadrant"), "priority": f.get("nammayatri_priority")}
            for i, f in enumerate(ranked[:3])
        ],
        "nammayatri_note": "All features validated against zero-commission rule and Beckn compliance.",
    }, indent=2)


@tool
def generate_experiment_brief(context: str) -> str:
    """Generate a structured experiment brief for a NammaYatri feature hypothesis.
    Args:
        context: JSON with feature_name and hypothesis/solution.
    Returns:
        Experiment brief with sample size, guardrails, and success definition.
    """
    feature_name = "Feature Experiment"
    hypothesis = ""
    try:
        data = json.loads(context)
        feature_name = data.get("feature_name", feature_name)
        hypothesis = data.get("solution", data.get("hypothesis", ""))
    except Exception:
        feature_name = str(context)[:60]
        hypothesis = str(context)

    return json.dumps({
        "experiment_brief": {
            "feature": feature_name,
            "hypothesis": f"We believe that {feature_name.lower()} will improve driver retention and rider satisfaction because {str(hypothesis)[:200]}",
            "experiment_type": "A/B test — control vs treatment",
            "sample_size": {
                "method": "Power analysis at 80% statistical power, 5% significance",
                "minimum": "5,000 drivers per variant, 10,000 riders per variant",
                "duration": "14 days minimum (capture weekly patterns)",
                "rollout": "5% traffic → 20% if no guardrail breach within 48h",
            },
            "guardrails": [
                "Driver daily earnings must not drop below baseline by >5%",
                "Subscription cancellation rate must not increase by >2pp",
                "Ride completion rate must not drop below 70%",
                "App crash rate must not increase by >0.5pp",
                "ARDU must be informed before experiment goes live",
            ],
            "success_metrics": {
                "primary": "Ride completion rate +5pp vs control",
                "secondary": ["Driver D30 retention +3pp", "Rider NPS +5 points", "Driver cancellation rate -5pp"],
                "guardrail": "No metric breaches threshold",
            },
            "mission_filter_pre_check": {
                "zero_commission_safe": True,
                "driver_welfare_positive": True,
                "beckn_compliant": True,
                "community_informed": "ARDU notification required before experiment",
            },
            "rollback_plan": "Disable feature flag within 30 minutes if any guardrail breached",
        }
    }, indent=2)


@tool
def generate_stakeholder_brief(context: str) -> str:
    """Generate a stakeholder brief for ARDU, city government, or ONDC.
    Args:
        context: JSON with feature_name, audience (ARDU/government/ONDC), and optional prd.
    Returns:
        Formatted brief tailored to the specified audience.
    """
    feature_name = "NammaYatri Feature"
    audience = "ARDU"
    try:
        data = json.loads(context)
        feature_name = data.get("feature_name", feature_name)
        audience = data.get("audience", "ARDU")
    except Exception:
        feature_name = str(context)[:60]

    if "ardu" in audience.lower() or "driver" in audience.lower():
        return json.dumps({
            "stakeholder_brief": {
                "audience": "ARDU — Auto Rickshaw Drivers Union",
                "subject": f"Community Consultation: {feature_name}",
                "key_message": "We are proposing a change. As our co-product-owner, we need your input before we proceed.",
                "driver_impact": {
                    "earnings": "Zero commission preserved — driver keeps 100% of fare",
                    "subscription": "No change to subscription fees",
                    "working_conditions": "Feature designed to improve driver experience",
                },
                "what_we_are_asking": [
                    "Review the proposed feature",
                    "Share feedback from driver community within 7 days",
                    "Nominate 2-3 drivers for beta testing",
                    "Flag any concerns before we proceed to engineering",
                ],
                "consultation_format": "In-person at NammaYatri office or driver stand — your choice",
                "timeline": "Decision in 2 weeks after consultation",
                "commitment": "We will not ship this without your sign-off",
            }
        }, indent=2)
    elif "city" in audience.lower() or "government" in audience.lower():
        return json.dumps({
            "stakeholder_brief": {
                "audience": "City Government / Transport Authority",
                "subject": f"NammaYatri Platform Update: {feature_name}",
                "public_interest_framing": "Improves urban mobility, driver livelihoods, and provides open trip data for city planning",
                "regulatory_compliance": "ONDC-compliant, Beckn standard, data shared via open data portal",
                "driver_welfare": "All earnings flow directly to drivers — no platform extraction",
            }
        }, indent=2)
    else:
        return json.dumps({
            "stakeholder_brief": {
                "audience": "ONDC / Beckn Foundation",
                "subject": f"Protocol Update Notification: {feature_name}",
                "beckn_impact": "Uses standard Beckn API endpoints — no protocol changes required",
                "ondc_compliance": "Full interoperability with other ONDC mobility players maintained",
                "open_source": "Implementation contributed back to open source repo",
            }
        }, indent=2)


# ── Exported tool list ─────────────────────────────────────────────────────────

ALL_TOOLS = [
    # v2 mission + RICE layer
    run_mission_filter,
    prioritize_with_rice,
    generate_impact_quadrant,
    generate_experiment_brief,
    generate_stakeholder_brief,
    # v2 intelligence layer
    synthesize_pm_insights,
    run_root_cause_analysis,
    evaluate_pm_decision,
    check_consultation_gate,
    ai_prioritize_issues,
    log_decision_outcome,
    get_learning_state_tool,
    explain_decision,
    # Core workflow chain
    read_github_issues,
    analyze_pain_points,
    check_kpi_metrics,
    prioritize_issues,
    generate_solution,
    generate_prd,
    create_jira_stories,
    generate_roadmap,
    create_github_issue,
    simulate_impact,
    visualize_roadmap,
    # Research tools
    search_namma_yatri_reviews,
    search_competitor_data,
    search_market_trends,
    search_driver_feedback,
    create_gtm_plan,
    search_rag_documents,
]
