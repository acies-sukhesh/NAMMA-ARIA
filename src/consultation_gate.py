"""
Consultation & Compliance Gate

Every PM artifact (solution, PRD, Jira, roadmap item) must pass through this gate.
It identifies whether community consultation, protocol review, or policy review is needed,
and hard-blocks any artifact that violates zero-commission or safety principles.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ConsultationFlag(str, Enum):
    DRIVER_COMMUNITY   = "requires_community_consultation"
    PROTOCOL_REVIEW    = "requires_protocol_review"
    POLICY_REVIEW      = "needs_policy_review"
    ZERO_COMMISSION    = "zero_commission_risk"
    EARNINGS_MECHANIC  = "earnings_mechanic_change"
    ALLOCATION_CHANGE  = "allocation_logic_change"
    SAFETY_CONDITIONS  = "safety_working_conditions"
    SUBSCRIPTION_PRICE = "subscription_pricing_change"


# Each rule has: flag, trigger keywords, explanation, and whether it hard-blocks
_RULES = [
    {
        "flag":         ConsultationFlag.ZERO_COMMISSION,
        "triggers":     ["commission", "take rate", "percentage cut", "per-ride fee",
                         "cut from fare", "platform fee from driver"],
        "reason":       (
            "HARD STOP: zero commission is a non-negotiable platform promise. "
            "Any mechanism that extracts a percentage of driver fares requires founder/board approval."
        ),
        "blocks": True,
    },
    {
        "flag":         ConsultationFlag.SUBSCRIPTION_PRICE,
        "triggers":     ["subscription price", "subscription pricing", "plan price", "tier price",
                         "weekly charge", "subscription cost", "change subscription"],
        "reason":       (
            "Subscription pricing changes directly affect driver economics. "
            "ARDU/driver community consultation is mandatory before any pricing change."
        ),
        "blocks": True,
    },
    {
        "flag":         ConsultationFlag.EARNINGS_MECHANIC,
        "triggers":     ["earnings", "income", "take-home", "driver pay", "per-ride pay",
                         "payment to driver", "driver revenue"],
        "reason":       (
            "Changes to how drivers earn require community input. "
            "Brief ARDU leadership and run a driver WhatsApp poll before proceeding."
        ),
        "blocks": False,
    },
    {
        "flag":         ConsultationFlag.ALLOCATION_CHANGE,
        "triggers":     ["dispatch algorithm", "allocation logic", "ride assignment",
                         "queue priority", "matching algorithm", "driver ranking"],
        "reason":       (
            "Allocation and dispatch changes affect driver income indirectly. "
            "Driver community review is advised before production rollout."
        ),
        "blocks": False,
    },
    {
        "flag":         ConsultationFlag.SAFETY_CONDITIONS,
        "triggers":     ["safety", "sos", "harassment", "assault", "working condition",
                         "hour limit", "rest time", "working hours"],
        "reason":       (
            "Driver safety or working condition changes require legal review "
            "and driver community consultation."
        ),
        "blocks": False,
    },
    {
        "flag":         ConsultationFlag.PROTOCOL_REVIEW,
        "triggers":     ["beckn", "ondc", "protocol", "api schema", "network layer",
                         "interoperability", "open network"],
        "reason":       (
            "Protocol-touching changes require ONDC team sign-off (2-week review window) "
            "to maintain Beckn network integrity."
        ),
        "blocks": False,
    },
    {
        "flag":         ConsultationFlag.POLICY_REVIEW,
        "triggers":     ["cancellation policy", "cancel policy", "penalty policy",
                         "surge pricing", "dynamic pricing", "incentive structure"],
        "reason":       (
            "User-visible policy changes require PM + legal + driver community review cycle."
        ),
        "blocks": False,
    },
]


@dataclass
class ConsultationResult:
    issue_title:                    str
    flags:                          List[Dict[str, Any]] = field(default_factory=list)
    blocks_output:                  bool                  = False
    consultation_required:          bool                  = False
    block_reason:                   str                   = ""
    recommended_consultation_steps: List[str]             = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def run_consultation_gate(
    issue_title: str = "",
    solution_text: str = "",
    prd_text: str = "",
) -> ConsultationResult:
    """
    Check issue title, solution description, and PRD text for consultation/compliance triggers.
    Returns a ConsultationResult with flags, block status, and recommended steps.
    """
    combined = f"{issue_title} {solution_text} {prd_text}".lower()
    result = ConsultationResult(issue_title=issue_title)

    triggered_flags = set()

    for rule in _RULES:
        if any(t in combined for t in rule["triggers"]):
            flag_val = rule["flag"].value
            if flag_val not in triggered_flags:
                triggered_flags.add(flag_val)
                result.flags.append({
                    "flag":         flag_val,
                    "reason":       rule["reason"],
                    "blocks_output": rule["blocks"],
                })
                result.consultation_required = True
                if rule["blocks"]:
                    result.blocks_output = True
                    result.block_reason  = rule["reason"]

    # ── Build recommended steps ────────────────────────────────────────────────
    has_earnings  = ConsultationFlag.EARNINGS_MECHANIC.value  in triggered_flags
    has_sub_price = ConsultationFlag.SUBSCRIPTION_PRICE.value in triggered_flags
    has_alloc     = ConsultationFlag.ALLOCATION_CHANGE.value  in triggered_flags
    has_zero_com  = ConsultationFlag.ZERO_COMMISSION.value    in triggered_flags
    has_protocol  = ConsultationFlag.PROTOCOL_REVIEW.value    in triggered_flags
    has_safety    = ConsultationFlag.SAFETY_CONDITIONS.value  in triggered_flags

    if has_zero_com:
        result.recommended_consultation_steps.insert(0,
            "⛔ ESCALATE IMMEDIATELY: Zero-commission risk requires founder/board sign-off. Do NOT proceed."
        )

    if has_earnings or has_sub_price or has_alloc:
        result.recommended_consultation_steps += [
            "1. Brief ARDU leadership on the proposed change and the rationale",
            "2. Run a WhatsApp poll in driver community groups (min 200 responses, 48-hour window)",
            "3. Host a driver AMA session (30–60 min live) before finalising the design",
        ]

    if has_sub_price:
        result.recommended_consultation_steps.append(
            "4. Present subscription ROI data alongside any pricing change proposal"
        )

    if has_protocol:
        result.recommended_consultation_steps.append(
            "5. Submit a Beckn protocol impact analysis to the ONDC team (allow 2-week review)"
        )

    if has_safety:
        result.recommended_consultation_steps.append(
            "6. Legal review for driver working-condition implications"
        )

    if not result.recommended_consultation_steps:
        result.recommended_consultation_steps.append(
            "No special consultation required — standard PM review process applies."
        )

    return result


def gate_to_json(gate: ConsultationResult) -> str:
    return json.dumps(gate.to_dict(), indent=2)
