"""
Learning Loop — ARIA's feedback engine.

Records decisions, stores outcomes, adjusts scoring weights, and surfaces
what worked vs. what failed so future prioritizations improve over time.
This is reinforcement-learning-in-spirit: no full RL, but genuine weight updates
and explicit pattern memory.
"""

import json
from typing import Any, Dict, List, Optional

from src.memory_store import (
    get_decisions,
    get_learning_weights,
    get_outcome_summary,
    get_similar_past_decisions,
    get_weight_details,
    record_outcome,
    save_decision,
)


# ── Log a new PM decision ──────────────────────────────────────────────────────

def log_pm_decision(
    issue_title: str,
    priority: str,
    rationale: str,
    feature_name: str            = "",
    driver_welfare_score: float  = 0.0,
    rider_trust_score: float     = 0.0,
    mission_alignment: float     = 7.0,
    consultation_required: bool  = False,
    consultation_flags: Optional[List[str]] = None,
    assigned_team: str           = "",
    issue_type: str              = "",
    composite_score: Optional[float] = None,
) -> str:
    """Persist a PM decision and return its ID."""
    return save_decision({
        "issue_title":          issue_title,
        "issue_type":           issue_type,
        "priority":             priority,
        "rationale":            rationale,
        "feature_name":         feature_name,
        "driver_welfare_score": driver_welfare_score,
        "rider_trust_score":    rider_trust_score,
        "mission_alignment":    mission_alignment,
        "consultation_required": consultation_required,
        "consultation_flags":   consultation_flags or [],
        "assigned_team":        assigned_team,
        "composite_score":      composite_score,
        "status":               "OPEN",
    })


# ── Record an outcome ──────────────────────────────────────────────────────────

def log_outcome(
    decision_id: str,
    kpi_improved: bool,
    driver_impact_delta: float = 0.0,
    rider_impact_delta: float  = 0.0,
    hypothesis_held: bool      = False,
    notes: str                 = "",
    actual_vs_predicted: str   = "",
) -> Dict[str, Any]:
    """
    Record the outcome of a closed decision.
    Returns the updated learning weight snapshot and a learning note.
    """
    outcome = {
        "kpi_improved":          kpi_improved,
        "driver_impact_delta":   driver_impact_delta,
        "rider_impact_delta":    rider_impact_delta,
        "hypothesis_held":       hypothesis_held,
        "notes":                 notes,
        "actual_vs_predicted":   actual_vs_predicted,
    }
    record_outcome(decision_id, outcome)
    weights = get_learning_weights()

    changed = [f for f, w in weights.items() if w != 1.0]
    note = (
        f"Weights updated for {len(changed)} factors. "
        f"Future prioritization will reflect this outcome."
        if changed
        else "No weight changes triggered (no KPI or driver/rider delta provided)."
    )
    return {
        "decision_id":      decision_id,
        "outcome_recorded": True,
        "updated_weights":  weights,
        "learning_note":    note,
    }


# ── Learning state snapshot ────────────────────────────────────────────────────

def get_learning_state() -> Dict[str, Any]:
    """
    Full learning state: current weights, weight insights, outcome summary,
    recent decisions, and a health assessment.
    """
    weights  = get_learning_weights()
    details  = get_weight_details()
    summary  = get_outcome_summary()
    recent   = get_decisions(limit=5)

    weight_insights: List[str] = []
    for row in details:
        factor, w = row["factor"], row["weight"]
        sc, fc = row.get("success_count", 0), row.get("failure_count", 0)
        if w > 1.15:
            weight_insights.append(
                f"↑ {factor} (w={w:.2f}, {sc} successes) — consistently predictive of good outcomes"
            )
        elif w < 0.75:
            weight_insights.append(
                f"↓ {factor} (w={w:.2f}, {fc} failures) — less reliable; trust it less when scoring"
            )

    recent_display = [
        {
            "id":            d["id"],
            "issue":         (d["issue_title"] or "")[:60],
            "priority":      d["priority"],
            "status":        d["status"],
            "outcome_score": d.get("outcome_score"),
            "team":          d.get("assigned_team", ""),
        }
        for d in recent
    ]

    return {
        "current_weights":   weights,
        "weight_insights":   weight_insights or ["Weights at defaults — more outcomes needed to detect trends."],
        "outcome_summary":   summary,
        "recent_decisions":  recent_display,
        "learning_health":   _assess_health(summary),
    }


def _assess_health(summary: Dict) -> str:
    total = summary.get("total_decisions", 0)
    closed = summary.get("closed", 0)
    avg   = summary.get("avg_outcome_score", 0.0)

    if total == 0:
        return "COLD START — No decisions logged yet. System will begin learning after the first decision cycle."
    if closed == 0:
        return f"LEARNING PENDING — {total} decisions open, awaiting outcome data."
    if avg >= 0.7:
        return f"HEALTHY — avg outcome {avg:.2f}. System calibrating well."
    if avg >= 0.4:
        return f"IN PROGRESS — avg outcome {avg:.2f}. Accumulating more outcomes for calibration."
    return f"NEEDS REVIEW — avg outcome {avg:.2f}. Recent decisions may not be landing as expected."


# ── Contextual retrieval for new decisions ─────────────────────────────────────

def get_learning_context(issue_title: str) -> Dict[str, Any]:
    """
    Retrieve relevant past decisions before making a new one.
    Returns similar precedents, outcome-based guidance, and current weights.
    """
    similar  = get_similar_past_decisions(issue_title, limit=3)
    weights  = get_learning_weights()
    guidance: List[str] = []

    for d in similar:
        score = d.get("outcome_score")
        title = (d.get("issue_title") or "")[:50]
        pri   = d.get("priority", "?")
        if score is not None:
            if score >= 0.7:
                guidance.append(
                    f"✓ Similar issue '{title}' succeeded (score {score:.2f}, priority {pri}). "
                    "Consider same or adjacent approach."
                )
            elif score < 0.4:
                guidance.append(
                    f"✗ Similar issue '{title}' underperformed (score {score:.2f}, priority {pri}). "
                    "Review what failed before repeating approach."
                )

    if not guidance:
        guidance.append("No relevant past decisions found — proceeding with framework defaults.")

    return {
        "similar_past_decisions": [
            {
                "id":            d["id"],
                "issue":         (d.get("issue_title") or "")[:60],
                "priority":      d.get("priority"),
                "outcome_score": d.get("outcome_score"),
                "status":        d.get("status"),
            }
            for d in similar
        ],
        "learning_guidance":  guidance,
        "current_weights":    weights,
    }
