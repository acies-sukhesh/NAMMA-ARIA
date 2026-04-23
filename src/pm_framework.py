"""
PM Decision Framework — structured evaluation of every issue before prioritization.

Evaluates: driver welfare, rider trust, mission alignment, compliance risk,
urgency, confidence, strategic importance, effort, and symptom vs root-cause status.

The composite score is the basis for AI-driven prioritization, not just ICE arithmetic.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PMEvaluation:
    issue_title: str

    # Impact: -2.0 (harmful) … +2.0 (very beneficial)
    driver_welfare_impact: float = 0.0
    rider_trust_impact:    float = 0.0

    # Scores: 0–10
    mission_alignment:    float = 7.0
    urgency:              float = 5.0
    confidence:           float = 5.0
    strategic_importance: float = 5.0
    effort_estimate:      float = 5.0   # Higher = harder (penalises composite score)

    # Risk: 0–10 (10 = maximum risk)
    compliance_risk:       float = 0.0
    zero_commission_risk:  float = 0.0
    consultation_cost:     float = 0.0

    # Qualitative flags
    is_symptom:                bool       = True
    symptom_or_root:           str        = "symptom"   # "symptom" | "root_cause" | "both"
    requires_consultation:     bool       = False
    consultation_flags:        List[str]  = field(default_factory=list)
    mission_filter_passed:     bool       = True
    mission_filter_reason:     str        = ""

    # Explainability
    rationale:               str       = ""
    alternatives_considered: List[str] = field(default_factory=list)

    def composite_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        Weighted composite on a 0–10 scale.
        Driver welfare and rider trust are first-tier; effort and risks are penalties.
        Zero-commission violations hard-zero the score.
        """
        w = weights or {
            "driver_earnings_impact": 1.0,
            "rider_trust_impact":     0.9,
            "urgency":                0.8,
            "strategic_importance":   0.7,
            "effort_inverse":         0.6,
            "compliance_risk_inverse": 0.7,
            "consultation_cost":      0.5,
        }

        # Normalise driver/rider impacts from [-2, +2] → [0, 10]
        driver_norm = (self.driver_welfare_impact + 2.0) * 2.5
        rider_norm  = (self.rider_trust_impact    + 2.0) * 2.5
        effort_inv   = 10.0 - self.effort_estimate
        compliance_inv = 10.0 - self.compliance_risk
        consult_inv  = 10.0 - self.consultation_cost

        raw = (
            w["driver_earnings_impact"]  * driver_norm   +
            w["rider_trust_impact"]      * rider_norm     +
            w["urgency"]                 * self.urgency   +
            w["strategic_importance"]    * self.strategic_importance +
            w["effort_inverse"]          * effort_inv     +
            w["compliance_risk_inverse"] * compliance_inv +
            w["consultation_cost"]       * consult_inv
        )
        total_w = sum(w.values())
        normalised = (raw / (total_w * 10.0)) * 10.0

        if self.zero_commission_risk > 7.0:
            return 0.0

        return round(min(max(normalised, 0.0), 10.0), 2)

    def to_dict(self) -> Dict:
        return asdict(self)


# ── Evaluation function ────────────────────────────────────────────────────────

def evaluate_issue(
    issue: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> PMEvaluation:
    """
    Score an issue through the NammaYatri PM decision framework.
    context may include: breached_kpis list, kpi_metrics dict.
    """
    context = context or {}
    title   = issue.get("title", "")
    tl      = title.lower()

    ev = PMEvaluation(issue_title=title)

    # ── Driver welfare ─────────────────────────────────────────────────────────
    if any(w in tl for w in ["driver", "earning", "subscription", "payment", "income", "salary"]):
        ev.driver_welfare_impact = 1.5
        ev.requires_consultation = True
        ev.consultation_flags.append("DRIVER_EARNINGS_MECHANIC — community input required")
        ev.consultation_cost = 4.0
    elif any(w in tl for w in ["cancel", "cancellation", "commitment score"]):
        ev.driver_welfare_impact = -0.5   # punitive if poorly designed
        ev.consultation_flags.append("CANCELLATION_MECHANIC — ensure no punitive revenue deduction")
        ev.consultation_cost = 2.0
    elif any(w in tl for w in ["wait", "eta", "positioning", "demand"]):
        ev.driver_welfare_impact = 0.5    # more rides → higher earnings
    else:
        ev.driver_welfare_impact = 0.0

    # ── Rider trust ────────────────────────────────────────────────────────────
    if any(w in tl for w in ["cancel", "wait", "eta", "safety", "booking", "track"]):
        ev.rider_trust_impact = 1.5
    elif any(w in tl for w in ["rating", "review", "support", "complaint"]):
        ev.rider_trust_impact = 1.0
    elif any(w in tl for w in ["rider", "user", "app"]):
        ev.rider_trust_impact = 0.8
    else:
        ev.rider_trust_impact = 0.5

    # ── Zero-commission / mission filter ──────────────────────────────────────
    commission_triggers = [
        "commission", "take rate", "percentage cut", "per-ride fee",
        "platform fee from driver", "cut from fare",
    ]
    if any(ct in tl for ct in commission_triggers):
        ev.zero_commission_risk    = 10.0
        ev.mission_filter_passed   = False
        ev.mission_filter_reason   = (
            "VIOLATES ZERO-COMMISSION PRINCIPLE — "
            "this feature would extract value from drivers in contravention of the platform promise"
        )
        ev.mission_alignment = 0.0
    elif any(w in tl for w in ["open source", "beckn", "ondc", "transparency", "community"]):
        ev.mission_alignment = 10.0
    elif any(w in tl for w in ["driver", "earning", "welfare"]):
        ev.mission_alignment = 8.5
    else:
        ev.mission_alignment = 6.0

    # ── Compliance risk ────────────────────────────────────────────────────────
    if any(w in tl for w in ["fare", "pricing", "surge", "dynamic pricing"]):
        ev.compliance_risk = 4.0
        ev.consultation_flags.append("PRICING_MECHANIC — verify Beckn protocol compliance")
        ev.requires_consultation = True
        ev.consultation_flags.append("PROTOCOL_REVIEW — Beckn/ONDC team must sign off")
    elif any(w in tl for w in ["allocation", "dispatch", "matching algorithm"]):
        ev.compliance_risk = 3.0
        ev.consultation_flags.append("ALLOCATION_CHANGE — indirect earnings effect, driver review advised")

    # ── Urgency (boosted by KPI breach) ───────────────────────────────────────
    breached = context.get("breached_kpis", [])
    if any(w in tl for w in ["cancel", "cancellation"]) and "driver_cancellation_rate" in breached:
        ev.urgency = 9.0
    elif any(w in tl for w in ["wait", "eta"]) and "avg_wait_time_minutes" in breached:
        ev.urgency = 8.0
    elif any(w in tl for w in ["completion", "complete"]) and "ride_completion_rate" in breached:
        ev.urgency = 9.0
    elif any(w in tl for w in ["retention", "churn"]) and "driver_retention_rate" in breached:
        ev.urgency = 7.5
    elif breached:
        ev.urgency = 6.0
    else:
        ev.urgency = 4.0

    # ── Effort estimate ────────────────────────────────────────────────────────
    if any(w in tl for w in ["pdf", "report", "notification", "alert", "analytics", "weekly"]):
        ev.effort_estimate = 2.0
    elif any(w in tl for w in ["ml", "model", "ai", "prediction", "recommendation engine"]):
        ev.effort_estimate = 8.0
    elif any(w in tl for w in ["advance booking", "schedule", "payment hold", "escrow"]):
        ev.effort_estimate = 6.0
    elif any(w in tl for w in ["heatmap", "dashboard", "visibility"]):
        ev.effort_estimate = 3.0
    else:
        ev.effort_estimate = 4.5

    # ── Strategic importance ───────────────────────────────────────────────────
    if any(w in tl for w in ["driver retention", "supply", "churn", "driver welfare"]):
        ev.strategic_importance = 9.0
    elif any(w in tl for w in ["completion rate", "trust", "safety"]):
        ev.strategic_importance = 8.5
    elif any(w in tl for w in ["expansion", "new city", "growth"]):
        ev.strategic_importance = 7.5
    elif any(w in tl for w in ["analytics", "dashboard", "visibility"]):
        ev.strategic_importance = 6.0
    else:
        ev.strategic_importance = 5.5

    # ── Symptom vs root cause ──────────────────────────────────────────────────
    if any(w in tl for w in ["rating", "churn", "completion"]):
        ev.is_symptom        = True
        ev.symptom_or_root   = "symptom"
    elif any(w in tl for w in ["cancel", "wait", "subscription pricing"]):
        ev.is_symptom        = False
        ev.symptom_or_root   = "root_cause"
    else:
        ev.symptom_or_root   = "both"

    # ── Build rationale ────────────────────────────────────────────────────────
    parts: List[str] = []
    if ev.driver_welfare_impact > 0:
        parts.append(f"driver welfare +{ev.driver_welfare_impact:.1f}")
    if ev.driver_welfare_impact < 0:
        parts.append(f"driver welfare {ev.driver_welfare_impact:.1f} — punitive risk")
    if ev.rider_trust_impact > 1:
        parts.append(f"rider trust +{ev.rider_trust_impact:.1f}")
    if ev.urgency >= 8:
        parts.append("KPI breach confirmed → high urgency")
    if not ev.mission_filter_passed:
        parts.append(f"BLOCKED: {ev.mission_filter_reason}")
    if ev.consultation_flags:
        parts.append(f"consultation flags: {'; '.join(ev.consultation_flags)}")
    if ev.symptom_or_root == "symptom":
        parts.append("note: symptom — fixing root cause preferred")

    ev.rationale = " | ".join(parts) if parts else "Standard framework evaluation"
    return ev


def evaluate_to_priority(
    ev: PMEvaluation,
    weights: Optional[Dict[str, float]] = None,
) -> str:
    if not ev.mission_filter_passed:
        return "BLOCKED"
    score = ev.composite_score(weights)
    if score >= 8.0:
        return "P0"
    elif score >= 6.0:
        return "P1"
    elif score >= 4.0:
        return "P2"
    else:
        return "P3"


def evaluation_to_json(ev: PMEvaluation) -> str:
    d = ev.to_dict()
    d["composite_score"] = ev.composite_score()
    d["priority"]        = evaluate_to_priority(ev)
    return json.dumps(d, indent=2)
