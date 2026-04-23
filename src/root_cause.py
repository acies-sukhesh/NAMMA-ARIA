"""
Root Cause Analysis — NammaYatri-specific, issue-type-aware multi-hypothesis reasoning.

Each hypothesis carries: category, confidence, driver/rider impact, and a concrete
investigation action so teams know exactly what data to pull next.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RCACategory(str, Enum):
    SUPPLY   = "SUPPLY"
    DEMAND   = "DEMAND"
    PRODUCT  = "PRODUCT"
    OPS      = "OPS"
    DATA     = "DATA"
    TRUST    = "TRUST"
    EXTERNAL = "EXTERNAL"


@dataclass
class Hypothesis:
    id: str
    category: RCACategory
    statement: str
    evidence_for: List[str]     = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    confidence: float           = 0.5
    investigation_action: str   = ""
    driver_impact: str          = "neutral"   # "positive" | "negative" | "neutral"
    rider_impact: str           = "neutral"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d


@dataclass
class RCAResult:
    issue_title: str
    issue_type: str
    hypotheses: List[Hypothesis]              = field(default_factory=list)
    top_hypothesis: Optional[Hypothesis]      = None
    recommended_investigation: List[str]      = field(default_factory=list)
    is_symptom: bool                          = True
    root_issue: Optional[str]                 = None
    cross_functional_scope: List[str]         = field(default_factory=list)
    immediate_data_pulls: List[str]           = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "issue_title":                self.issue_title,
            "issue_type":                 self.issue_type,
            "hypotheses":                 [h.to_dict() for h in self.hypotheses],
            "top_hypothesis":             self.top_hypothesis.to_dict() if self.top_hypothesis else None,
            "recommended_investigation":  self.recommended_investigation,
            "is_symptom":                 self.is_symptom,
            "root_issue":                 self.root_issue,
            "cross_functional_scope":     self.cross_functional_scope,
            "immediate_data_pulls":       self.immediate_data_pulls,
        }


# ── Issue-type hypothesis bank ─────────────────────────────────────────────────

_CANCELLATION = [
    Hypothesis(
        id="CAN-H1",
        category=RCACategory.SUPPLY,
        statement=(
            "Dispatch rewards acceptance rate but applies no cost to cancellation — "
            "drivers accept to maintain dispatch priority, then cancel freely"
        ),
        evidence_for=["No visible cancellation consequence in driver app", "High acceptance + high cancellation correlation"],
        evidence_against=["Some drivers maintain low cancellation despite high acceptance"],
        confidence=0.85,
        investigation_action="Segment: cancellation_rate by driver_acceptance_rate cohort",
        driver_impact="negative", rider_impact="negative",
    ),
    Hypothesis(
        id="CAN-H2",
        category=RCACategory.SUPPLY,
        statement=(
            "Drivers in high-density zones speculatively accept then cancel "
            "when a geographically closer ride appears"
        ),
        evidence_for=["Cancellation rate higher in CBD/high-density zones"],
        evidence_against=["Cancellation is also elevated in low-density zones"],
        confidence=0.75,
        investigation_action="Segment: cancellation_rate by zone_density (CBD vs suburban vs peripheral)",
        driver_impact="neutral", rider_impact="negative",
    ),
    Hypothesis(
        id="CAN-H3",
        category=RCACategory.DATA,
        statement=(
            "ETA shown to rider is systematically optimistic — when driver sees actual "
            "distance is too far, they cancel rather than face a long dead-mile"
        ),
        evidence_for=["wait_time KPI also breached", "ETA mismatch in reviews"],
        evidence_against=["Would expect ETA complaints to dominate if this were primary"],
        confidence=0.65,
        investigation_action="Compare predicted_ETA vs actual_pickup_time for CANCELLED rides specifically",
        driver_impact="neutral", rider_impact="negative",
    ),
    Hypothesis(
        id="CAN-H4",
        category=RCACategory.OPS,
        statement=(
            "GPS offset between rider's map pin and physical location causes "
            "driver confusion at destination — driver cancels rather than call"
        ),
        evidence_for=["'Driver at wrong location' complaints in reviews"],
        evidence_against=["Cancellations happen quickly (< 30s) suggesting pre-trip decision"],
        confidence=0.45,
        investigation_action="Analyse time-to-cancel after match — if > 60s it may be GPS; < 30s is pre-trip",
        driver_impact="neutral", rider_impact="negative",
    ),
]

_WAIT_TIME = [
    Hypothesis(
        id="WAIT-H1",
        category=RCACategory.SUPPLY,
        statement=(
            "Driver supply is geographically clustered near high-activity zones "
            "(malls, railway stations) rather than distributed across demand distribution"
        ),
        evidence_for=["Zone heat maps show driver clustering", "Long waits in peripheral areas"],
        evidence_against=["Wait times are high even in dense zones during peak"],
        confidence=0.80,
        investigation_action="Overlay: driver_idle_locations vs. ride_request_origins — compute supply-demand gap by zone",
        driver_impact="neutral", rider_impact="negative",
    ),
    Hypothesis(
        id="WAIT-H2",
        category=RCACategory.DATA,
        statement=(
            "ETA prediction model has drifted — trained on pre-2024 traffic patterns, "
            "now systematically underestimates travel time in Bengaluru/Hyderabad"
        ),
        evidence_for=["Bengaluru traffic up 30%+ post-COVID per NITI data"],
        evidence_against=["Would affect all platforms equally; Namma Yatri-specific signal needed"],
        confidence=0.60,
        investigation_action="Compute predicted_ETA vs actual_trip_start_time drift over last 90 days",
        driver_impact="neutral", rider_impact="negative",
    ),
    Hypothesis(
        id="WAIT-H3",
        category=RCACategory.OPS,
        statement=(
            "Off-peak demand spikes (9–11 pm, early morning 5–7 am) not proactively "
            "signalled to drivers — drivers go offline, demand spikes, wait time explodes"
        ),
        evidence_for=["wait_time trend=stable suggests periodic rather than continuous elevation"],
        evidence_against=["Need hour-of-day breakdown to confirm"],
        confidence=0.70,
        investigation_action="Break avg_wait_time by hour_of_day and day_of_week — identify spike windows",
        driver_impact="neutral", rider_impact="negative",
    ),
]

_COMPLETION = [
    Hypothesis(
        id="COMP-H1",
        category=RCACategory.SUPPLY,
        statement=(
            "Completion rate decline is primarily driven by post-acceptance driver cancellation "
            "(both KPIs breach in the same direction — strong co-movement)"
        ),
        evidence_for=["driver_cancellation_rate: 18% and ride_completion_rate: 71% both breached", "Causal direction: cancel → incomplete"],
        evidence_against=["Some completion loss is rider-side — need decomposition"],
        confidence=0.90,
        investigation_action="Decompose completion loss by type: driver_cancel, rider_cancel, no_match, timeout, app_crash",
        driver_impact="negative", rider_impact="negative",
    ),
    Hypothesis(
        id="COMP-H2",
        category=RCACategory.PRODUCT,
        statement=(
            "App funnel leakage — riders abort at booking confirmation due to UX friction "
            "or app crash on low-end devices before the ride is even matched"
        ),
        evidence_for=["App rating declining — often reflects UX frustration", "Low-end Android crash complaints"],
        evidence_against=["Completion rate is post-match metric; pre-match drop-offs tracked separately"],
        confidence=0.45,
        investigation_action="Track funnel step drop-off: search→select→confirm→matched→accepted→pickup",
        driver_impact="neutral", rider_impact="negative",
    ),
]

_SUBSCRIPTION = [
    Hypothesis(
        id="SUB-H1",
        category=RCACategory.TRUST,
        statement=(
            "Value perception gap — drivers don't clearly see subscription ROI "
            "relative to their actual weekly earnings through Namma Yatri"
        ),
        evidence_for=["No explicit earnings-vs-subscription breakdown in driver app"],
        evidence_against=["Renewal rate data needed to confirm actual churn"],
        confidence=0.75,
        investigation_action="WhatsApp poll: 'Is your Namma Yatri subscription worth what you pay?' (target 200 responses)",
        driver_impact="negative", rider_impact="neutral",
    ),
    Hypothesis(
        id="SUB-H2",
        category=RCACategory.EXTERNAL,
        statement=(
            "Competitors offering zero-subscription or lower-subscription models "
            "in specific corridors, making Namma Yatri subscription feel expensive"
        ),
        evidence_for=["Rapido expanding bike taxi at lower/no subscription"],
        evidence_against=["Zero commission still a strong differentiator — net earnings likely still higher"],
        confidence=0.60,
        investigation_action="Competitive audit: Ola/Uber/Rapido subscription pricing in Bengaluru, Hyderabad, Chennai",
        driver_impact="negative", rider_impact="neutral",
    ),
    Hypothesis(
        id="SUB-H3",
        category=RCACategory.PRODUCT,
        statement=(
            "Flat subscription pricing across high-density and low-density zones is "
            "unfair — peripheral-zone drivers pay same fee but get fewer rides"
        ),
        evidence_for=["Subscription price is uniform; ride density is highly non-uniform by zone"],
        evidence_against=["City-level average earnings may still justify current price"],
        confidence=0.65,
        investigation_action="Segment: subscription_renewal_rate by zone_density quintile and city",
        driver_impact="negative", rider_impact="neutral",
    ),
]

_RATINGS = [
    Hypothesis(
        id="RAT-H1",
        category=RCACategory.TRUST,
        statement=(
            "App rating is a lagging composite of cancellation frustration, "
            "wait time frustration, and poor support resolution"
        ),
        evidence_for=["Rating declined in same quarter as cancellation and wait time breaches"],
        evidence_against=["Rating may also reflect technical issues unrelated to ops KPIs"],
        confidence=0.85,
        investigation_action="Cluster Play Store reviews by topic: cancellation / wait / crash / support / competitor",
        driver_impact="neutral", rider_impact="negative",
    ),
    Hypothesis(
        id="RAT-H2",
        category=RCACategory.PRODUCT,
        statement=(
            "App crashes on low-end Android devices (2GB RAM) driving a disproportionate "
            "volume of 1-star reviews from target demographic"
        ),
        evidence_for=["'App crashes' in 1-star review text", "Target users are budget Android users"],
        evidence_against=["Crash rate data needed from Play Console to quantify volume"],
        confidence=0.70,
        investigation_action="Pull Play Console ANR and crash report by device RAM tier",
        driver_impact="neutral", rider_impact="negative",
    ),
]

_RCA_MAP: Dict[str, Dict] = {
    "cancellation": {
        "hypotheses": _CANCELLATION,
        "is_symptom": False,
        "root_issue": None,
        "recommended_investigation": [
            "Segment cancellation by driver_tenure (new < 30 days vs experienced)",
            "Plot time-to-cancel after accept (histogram) — reveals intent vs. GPS confusion",
            "Correlate cancellation_rate with zone_density to test H2",
            "WhatsApp pulse poll: 'Why did you cancel your last accepted ride?' (5 choices)",
        ],
        "cross_functional_scope": ["Product", "Data Science", "Driver Ops"],
        "immediate_data_pulls": [
            "cancellation_rate GROUP BY driver_tenure_bucket",
            "AVG(seconds_between_accept_and_cancel) by cancel_reason",
            "cancellation_rate GROUP BY zone_density_tier",
        ],
    },
    "wait_time": {
        "hypotheses": _WAIT_TIME,
        "is_symptom": True,
        "root_issue": "Supply distribution inefficiency + ETA model drift",
        "recommended_investigation": [
            "Time-of-day breakdown of avg_wait_time (hour-by-hour)",
            "Zone-level supply-demand gap map — overlay driver idle vs. ride origins",
            "ETA model accuracy audit over last 90 days",
        ],
        "cross_functional_scope": ["Product", "Data Science", "City Ops"],
        "immediate_data_pulls": [
            "avg_wait_time GROUP BY hour_of_day, day_of_week",
            "driver_idle_zone vs. request_origin_zone heatmap diff",
            "AVG(predicted_eta - actual_pickup_delay) for completed rides",
        ],
    },
    "completion": {
        "hypotheses": _COMPLETION,
        "is_symptom": True,
        "root_issue": "Primarily driven by driver post-acceptance cancellations",
        "recommended_investigation": [
            "Decompose completion_loss by failure_type (driver_cancel, rider_cancel, no_match, timeout)",
            "Fix driver cancellation first (H1 confidence: 90%)",
            "Secondary: audit booking funnel drop-off rates for H2",
        ],
        "cross_functional_scope": ["Product", "Engineering", "Data Science"],
        "immediate_data_pulls": [
            "COUNT(*) GROUP BY ride_failure_type",
            "funnel_step_exit_rate: search→confirm→matched→accepted→started",
        ],
    },
    "subscription": {
        "hypotheses": _SUBSCRIPTION,
        "is_symptom": False,
        "root_issue": None,
        "recommended_investigation": [
            "subscription_renewal_rate by city and driver tier",
            "Correlation: churn_rate vs earnings_per_week_per_driver",
            "Competitive pricing audit in Bengaluru, Hyderabad, Chennai",
        ],
        "cross_functional_scope": ["Product", "Driver Ops", "Finance"],
        "immediate_data_pulls": [
            "subscription_renewal_rate GROUP BY city, zone_density_tier",
            "AVG(weekly_rides * fare) / subscription_price_paid GROUP BY driver_id",
        ],
    },
    "ratings": {
        "hypotheses": _RATINGS,
        "is_symptom": True,
        "root_issue": "Lagging composite of cancellation, wait, crash, support failures",
        "recommended_investigation": [
            "Cluster Play Store reviews by topic (NLP or manual sample of 200)",
            "Pull ANR/crash rate by device RAM tier from Play Console",
            "Fix top 3 crash categories first (fastest rating win)",
        ],
        "cross_functional_scope": ["Product", "Engineering", "Support"],
        "immediate_data_pulls": [
            "Play Console: ANR rate and crash rate by device_memory_bucket",
            "1-star review text cluster analysis",
        ],
    },
}


def analyze_root_cause(issue_title: str, context: Dict[str, Any] = None) -> RCAResult:
    """
    Produce issue-type-aware root cause hypotheses, ranked by confidence.
    """
    tl = issue_title.lower()
    context = context or {}

    if any(w in tl for w in ["cancel", "cancellation", "cancelled"]):
        key = "cancellation"
    elif any(w in tl for w in ["wait", "eta", "pickup time"]):
        key = "wait_time"
    elif any(w in tl for w in ["completion", "complete", "finish", "completion rate"]):
        key = "completion"
    elif any(w in tl for w in ["subscription", "pricing", "plan", "tier", "weekly charge"]):
        key = "subscription"
    elif any(w in tl for w in ["rating", "review", "star", "app store"]):
        key = "ratings"
    else:
        # Generic fallback
        return RCAResult(
            issue_title=issue_title,
            issue_type="general",
            hypotheses=[
                Hypothesis(
                    id="GEN-H1",
                    category=RCACategory.PRODUCT,
                    statement=f"Product-level friction causing: {issue_title[:80]}",
                    confidence=0.4,
                    investigation_action="Gather more specific metrics on the affected flow",
                    driver_impact="unknown", rider_impact="unknown",
                )
            ],
            recommended_investigation=["Collect more specific data before forming hypotheses"],
            cross_functional_scope=["Product"],
        )

    data  = _RCA_MAP[key]
    hyps  = sorted(data["hypotheses"], key=lambda h: h.confidence, reverse=True)

    return RCAResult(
        issue_title=issue_title,
        issue_type=key,
        hypotheses=hyps,
        top_hypothesis=hyps[0] if hyps else None,
        recommended_investigation=data["recommended_investigation"],
        is_symptom=data["is_symptom"],
        root_issue=data.get("root_issue"),
        cross_functional_scope=data["cross_functional_scope"],
        immediate_data_pulls=data.get("immediate_data_pulls", []),
    )


def rca_to_json(rca: RCAResult) -> str:
    return json.dumps(rca.to_dict(), indent=2)
