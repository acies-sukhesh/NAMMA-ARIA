"""
Synthesized Insight Layer — converts raw KPI metrics and issues into typed PM insights.

No PM action should bypass this layer. Raw metric breaches alone are not insights;
an insight is a synthesized, actionable PM signal with evidence, affected personas,
hypotheses, and a consultation flag.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class InsightType(str, Enum):
    DRIVER_EARNINGS_RISK      = "DRIVER_EARNINGS_RISK"
    RIDER_TRUST_RISK          = "RIDER_TRUST_RISK"
    ETA_RELIABILITY_ISSUE     = "ETA_RELIABILITY_ISSUE"
    SUPPLY_DEMAND_IMBALANCE   = "SUPPLY_DEMAND_IMBALANCE"
    CONVERSION_FUNNEL_ISSUE   = "CONVERSION_FUNNEL_ISSUE"
    SUBSCRIPTION_HEALTH_ISSUE = "SUBSCRIPTION_HEALTH_ISSUE"
    CITY_OPS_ISSUE            = "CITY_OPS_ISSUE"
    COMPLIANCE_RISK           = "COMPLIANCE_RISK"
    PLATFORM_HEALTH_RISK      = "PLATFORM_HEALTH_RISK"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


@dataclass
class Insight:
    type: InsightType
    severity: Severity
    title: str
    description: str
    evidence: List[str]                = field(default_factory=list)
    affected_personas: List[str]       = field(default_factory=list)
    root_cause_hypotheses: List[str]   = field(default_factory=list)
    recommended_pm_actions: List[str]  = field(default_factory=list)
    requires_consultation: bool        = False
    consultation_reason: Optional[str] = None
    confidence: float                  = 0.7

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["type"]     = self.type.value
        d["severity"] = self.severity.value
        return d


# ── Core synthesis function ────────────────────────────────────────────────────

_THRESHOLDS: Dict[str, Dict] = {
    "driver_cancellation_rate": {"threshold": 10.0,  "direction": "above"},
    "avg_wait_time_minutes":    {"threshold": 7.0,   "direction": "above"},
    "ride_completion_rate":     {"threshold": 78.0,  "direction": "below"},
    "driver_retention_rate":    {"threshold": 65.0,  "direction": "below"},
    "app_rating":               {"threshold": 4.1,   "direction": "below"},
}


def _extract(raw: Any, key: str) -> tuple:
    """Return (value, threshold, is_breached, trend) from a raw metric entry.

    Accepts either:
    - a plain number (value only; threshold from _THRESHOLDS)
    - a dict with keys: value, threshold, status, trend
    """
    cfg = _THRESHOLDS.get(key, {"threshold": 0.0, "direction": "above"})
    if isinstance(raw, dict):
        val = float(raw.get("value", 0))
        thr = float(raw.get("threshold", cfg["threshold"]))
        breached = raw.get("status") == "BREACHED"
        trend = raw.get("trend", "stable")
    else:
        val = float(raw) if raw is not None else 0.0
        thr = cfg["threshold"]
        if cfg["direction"] == "above":
            breached = val > thr
        else:
            breached = val < thr
        trend = "unknown"
    return val, thr, breached, trend


def synthesize_insights(
    metrics: Dict[str, Any],
    issues: Optional[List[Dict]] = None,
    breached_kpis: Optional[List[str]] = None,
) -> List[Insight]:
    """
    Convert raw KPI metrics and optional issue list into typed, actionable insights.
    Always call this BEFORE prioritization or artifact generation.

    metrics may contain plain numeric values or structured dicts with
    {value, threshold, status, trend}.
    breached_kpis (optional list of keys) overrides breach detection.
    """
    insights: List[Insight] = []
    issues = issues or []
    breached_kpis = breached_kpis or []

    def _is_breached(key: str, raw: Any) -> bool:
        if breached_kpis and key in breached_kpis:
            return True
        _, _, breached, _ = _extract(raw, key)
        return breached

    # ── Driver retention ───────────────────────────────────────────────────────
    dr_raw = metrics.get("driver_retention_rate")
    if dr_raw is not None and _is_breached("driver_retention_rate", dr_raw):
        val, thr, _, _ = _extract(dr_raw, "driver_retention_rate")
        gap = thr - val
        _, _, _, trend_dr = _extract(dr_raw, "driver_retention_rate")
        sev = Severity.CRITICAL if gap > 15 else Severity.HIGH
        insights.append(Insight(
            type=InsightType.DRIVER_EARNINGS_RISK,
            severity=sev,
            title=f"Driver retention critically low — {val}% vs {thr}% target",
            description=(
                f"Driver D30 retention has fallen to {val}%, a {gap:.1f}pp gap from target. "
                "This is a leading indicator of supply collapse. Without intervention in 2–3 weeks "
                "expect the ride completion rate to fall further."
            ),
            evidence=[
                f"driver_retention_rate: {val}% (target {thr}%)",
                f"Trend: {trend_dr}",
            ],
            affected_personas=["driver", "platform"],
            root_cause_hypotheses=[
                "Earnings per hour declining relative to Ola/Uber on same corridors",
                "Low ride density in peripheral zones causing driver idle time",
                "Subscription perceived as unfair given low ride volume",
                "Drivers lack analytics visibility into their earnings trends",
                "Post-cancellation dispatch penalty creating vicious cycle",
            ],
            recommended_pm_actions=[
                "Launch weekly earnings PDF/WhatsApp report (zero backend cost)",
                "Zone-level heatmap showing predicted demand for next 2 hours",
                "Audit subscription tier pricing vs earnings ratio per city",
            ],
            requires_consultation=True,
            consultation_reason=(
                "Retention issues trace to earnings mechanics or subscription pricing — "
                "ARDU/driver community input required before any change"
            ),
            confidence=0.85,
        ))

    # ── Driver cancellation ────────────────────────────────────────────────────
    dc_raw = metrics.get("driver_cancellation_rate")
    if dc_raw is not None and _is_breached("driver_cancellation_rate", dc_raw):
        val, thr, _, trend_dc = _extract(dc_raw, "driver_cancellation_rate")
        insights.append(Insight(
            type=InsightType.SUPPLY_DEMAND_IMBALANCE,
            severity=Severity.CRITICAL,
            title=f"Driver cancellation at {val}% — far above {thr}% threshold",
            description=(
                "Post-acceptance cancellations destroy rider trust. At 18%, drivers are "
                "speculatively accepting rides to preserve dispatch priority, then cancelling. "
                "This is simultaneously a product design failure and a dispatch incentive failure."
            ),
            evidence=[
                f"driver_cancellation_rate: {val}% (target {thr}%)",
                "Correlated with low ride_completion_rate",
                f"Trend: {trend_dc}",
            ],
            affected_personas=["rider", "driver", "platform"],
            root_cause_hypotheses=[
                "Dispatch rewards acceptance rate but applies no cancellation cost",
                "Drivers in dense zones accept then cancel when a closer ride appears",
                "Optimistic ETA shown to rider → driver cancels on seeing true distance",
                "Pickup location GPS offset causes confusion → driver cancels",
                "No lightweight commitment signal in current booking flow",
            ],
            recommended_pm_actions=[
                "Smart Commitment Score — rank-deprioritize repeat cancellers (no revenue cut)",
                "Tighten dispatch radius — only match if driver can realistically commit",
                "In-app cancellation reason survey (5-second tap) for root-cause data",
            ],
            requires_consultation=False,
            confidence=0.9,
        ))

    # ── ETA / wait time ────────────────────────────────────────────────────────
    wt_raw = metrics.get("avg_wait_time_minutes")
    if wt_raw is not None and _is_breached("avg_wait_time_minutes", wt_raw):
        val, thr, _, trend_wt = _extract(wt_raw, "avg_wait_time_minutes")
        delta = val - thr
        insights.append(Insight(
            type=InsightType.ETA_RELIABILITY_ISSUE,
            severity=Severity.HIGH,
            title=f"Avg wait time {val} min — {delta:.1f} min above target",
            description=(
                f"Wait time exceeds target by {delta:.1f} min. At 8+ min, riders abandon to Ola/Uber. "
                "This is part supply-distribution problem, part ETA-accuracy problem: a 5-min ETA "
                "that becomes 8 min erodes trust faster than an honest 9-min ETA."
            ),
            evidence=[
                f"avg_wait_time_minutes: {val} (target {thr})",
                f"Trend: {trend_wt}",
            ],
            affected_personas=["rider"],
            root_cause_hypotheses=[
                "Driver supply geographically clustered, not distributed across demand zones",
                "ETA model using stale traffic assumptions (pre-2025 data)",
                "Low driver density during off-peak hours in peripheral areas",
                "Demand spikes (9–11pm, early morning) not proactively signalled to drivers",
            ],
            recommended_pm_actions=[
                "Zone-level push alerts to drivers 20 min before predicted demand surge",
                "Audit ETA model accuracy — if predicted 5 min, actual 8 min, show 8 min",
                "Demand heatmap for drivers showing next 2h prediction",
            ],
            confidence=0.8,
        ))

    # ── Ride completion ────────────────────────────────────────────────────────
    cr_raw = metrics.get("ride_completion_rate")
    if cr_raw is not None and _is_breached("ride_completion_rate", cr_raw):
        val, thr, _, _ = _extract(cr_raw, "ride_completion_rate")
        insights.append(Insight(
            type=InsightType.RIDER_TRUST_RISK,
            severity=Severity.CRITICAL,
            title=f"Ride completion rate {val}% — {thr - val}pp below target",
            description=(
                f"Completion at {val}% likely reflects post-match driver cancellations as primary cause, "
                "compounded by long waits driving rider abandonment. Every 1pp drop in completion "
                "means ~5K–10K failed rides/week at current scale — direct switching to competitors."
            ),
            evidence=[
                f"ride_completion_rate: {val}% (target {thr}%)",
                f"driver_cancellation_rate also BREACHED — correlated signal",
            ],
            affected_personas=["rider", "platform"],
            root_cause_hypotheses=[
                "Driver post-acceptance cancellation is primary driver (cancellation rate: 18%)",
                "Rider cancels after long wait post-match",
                "App funnel leakage at booking confirmation step",
                "No-match scenario in low-supply zones during peak",
            ],
            recommended_pm_actions=[
                "Decompose: cancellation-driven vs. no-match-driven completion loss",
                "Fix driver cancellation first (highest-confidence root cause)",
                "Track: rider drop-off at confirmed→matched→accepted→pickup funnel",
            ],
            confidence=0.75,
        ))

    # ── App rating ─────────────────────────────────────────────────────────────
    ar_raw = metrics.get("app_rating")
    if ar_raw is not None and _is_breached("app_rating", ar_raw):
        val, thr, _, trend_ar = _extract(ar_raw, "app_rating")
        insights.append(Insight(
            type=InsightType.PLATFORM_HEALTH_RISK,
            severity=Severity.MEDIUM,
            title=f"App rating {val}★ — below {thr}★ threshold",
            description=(
                f"Rating {val}★ is a lagging composite of unresolved cancellations, wait times, "
                "crashes, and support failures. Below 4.0★ we lose Play Store discoverability. "
                "This compounds organic install decay."
            ),
            evidence=[
                f"app_rating: {val}★ (target {thr}★)",
                f"Trend: {trend_ar}",
            ],
            affected_personas=["rider", "platform"],
            root_cause_hypotheses=[
                "Accumulated negative reviews from cancellation/wait frustrations",
                "App crashes on low-end Android (2GB RAM) driving 1★ reviews",
                "Poor support experience — unresolved complaints → rating drop",
                "Competitor promotions driving negative comparison reviews",
            ],
            recommended_pm_actions=[
                "Public review-reply strategy — resolved complaints visible to browsing users",
                "In-app rating prompt after successful ride completion (not randomly)",
                "Fix top 3 crash categories from Play Store ANR/crash reports",
            ],
            confidence=0.7,
        ))

    # ── Subscription signals from issues ──────────────────────────────────────
    sub_issues = [
        i for i in issues
        if any(kw in i.get("title", "").lower()
               for kw in ["subscription", "pricing", "plan", "tier", "weekly charge"])
    ]
    if sub_issues:
        insights.append(Insight(
            type=InsightType.SUBSCRIPTION_HEALTH_ISSUE,
            severity=Severity.MEDIUM,
            title="Subscription/pricing concerns surfaced in driver feedback",
            description=(
                "Driver-facing issues mention subscription or pricing. Given zero-commission "
                "sustainability depends entirely on subscription revenue, perceived unfairness "
                "directly threatens platform viability."
            ),
            evidence=[f"Issue: {i['title']}" for i in sub_issues[:3]],
            affected_personas=["driver"],
            root_cause_hypotheses=[
                "Subscription price unchanged while ride volume per driver declined",
                "Flat pricing across high-density and low-density zones — unfair to peripheral drivers",
                "Competitors offering lower or no subscription in specific corridors",
                "Value perception gap — drivers don't see explicit subscription ROI",
            ],
            recommended_pm_actions=[
                "Add 'What you paid vs. what you earned' breakdown to driver earnings view",
                "Audit subscription renewal rate vs. earnings-per-subscription by city",
                "Consider city/zone-based tiered pricing pilot (requires community consultation)",
            ],
            requires_consultation=True,
            consultation_reason=(
                "Subscription pricing is an earnings mechanic — "
                "ARDU/driver community consultation mandatory before any change"
            ),
            confidence=0.65,
        ))

    # Sort: CRITICAL > HIGH > MEDIUM > LOW
    _sev_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
    insights.sort(key=lambda x: _sev_order.get(x.severity, 4))
    return insights


# ── Serialisation helpers ──────────────────────────────────────────────────────

def insights_to_json(insights: List[Insight]) -> str:
    return json.dumps([i.to_dict() for i in insights], indent=2)


def get_insight_summary(insights: List[Insight]) -> str:
    critical = sum(1 for i in insights if i.severity == Severity.CRITICAL)
    high     = sum(1 for i in insights if i.severity == Severity.HIGH)
    consult  = sum(1 for i in insights if i.requires_consultation)
    parts = [f"{len(insights)} insights"]
    if critical: parts.append(f"{critical} CRITICAL")
    if high:     parts.append(f"{high} HIGH")
    if consult:  parts.append(f"{consult} need consultation")
    return " | ".join(parts)
