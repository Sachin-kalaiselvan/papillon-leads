"""Turns collected answers into Papillon's lead classes.

Rules come straight from Papillon's brief:
  • residential only; owner or authorised decision-maker only
  • identifiable property (city + locality/project, type, configuration)
  • complete-home budget ₹15 lakh+ (other scopes have their own minimums in settings)
  • defined timeline; willing to discuss with the team
  • Hot / Warm / Cold; only the temperatures in settings.forward_temperatures are forwarded
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OWNER_OK = {"owner", "co_owner", "family_decision_maker", "authorised_representative"}
NEAR_POSSESSION = {"received", "within_3_months"}
FAST_TIMELINE = {"immediate", "within_1_month"}
SOON_TIMELINE = FAST_TIMELINE | {"1_to_3_months"}
DEFINED_TIMELINE = SOON_TIMELINE | {"3_to_6_months"}

# What must be known before a lead can be forwarded (brief point 5 + 6 + qualified-lead definition)
REQUIRED = [
    ("city", "property city"),
    ("_place", "locality or project name"),
    ("property_type", "property type"),
    ("configuration", "configuration"),
    ("possession_status", "possession status"),
    ("scope", "scope of work"),
    ("_budget", "budget"),
    ("timeline", "timeline"),
    ("_owner", "ownership / decision-maker"),
    ("willing_consultation", "willingness to meet the team"),
]


@dataclass
class Verdict:
    status: str                     # qualified | nurture | disqualified | out_of_area | qualifying
    temperature: str | None = None  # hot | warm | cold
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    disqualify_reason: str | None = None

    def forwardable(self, settings: dict) -> bool:
        return self.status == "qualified" and self.temperature in (settings.get("forward_temperatures") or ["hot", "warm"])


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def in_service_area(lead: dict, areas: list[str]) -> bool | None:
    """True/False when we know where the property is, None when we don't yet."""
    hay = " | ".join(_norm(lead.get(k)) for k in ("city", "locality", "project_name") if lead.get(k))
    if not hay:
        return None
    return any(_norm(a) and _norm(a) in hay for a in areas)


def min_budget_for(lead: dict, s: dict, outstation: bool) -> int:
    scope = lead.get("scope")
    if scope in ("full_home", "turnkey", "renovation", None):
        base = s["min_budget_full_home"]
    elif scope == "modular_kitchen":
        base = s["min_budget_kitchen"]
    elif scope == "wardrobes":
        base = s["min_budget_wardrobes"]
    else:
        base = s["min_budget_partial"]
    if outstation:
        base = max(base, s.get("outstation_min_budget") or base)
    return int(base)


def evaluate(lead: dict, s: dict, in_handover_list: bool = False) -> Verdict:
    reasons: list[str] = []

    # ── hard stops ──────────────────────────────────────────────
    if lead.get("property_type") == "commercial":
        return Verdict("disqualified", None, 0, ["− Commercial property"], [], "Not residential")
    if lead.get("ownership") in ("tenant", "broker"):
        return Verdict("disqualified", None, 0, [f"− Caller is a {lead['ownership']}"], [], "Not the owner or decision-maker")
    if lead.get("decision_maker") is False and lead.get("ownership") not in ("owner", "co_owner"):
        return Verdict("disqualified", None, 0, ["− Not the decision-maker"], [], "Not the owner or decision-maker")

    area = in_service_area(lead, s.get("service_areas") or [])
    outstation = area is False
    if outstation and not s.get("accept_outstation"):
        return Verdict("out_of_area", None, 0, [f"− Property outside service area ({lead.get('city') or lead.get('locality')})"], [],
                       "Property outside Papillon's service area")

    # ── completeness ────────────────────────────────────────────
    budget = lead.get("budget_max") or lead.get("budget_min")
    owner_known = lead.get("ownership") in OWNER_OK or lead.get("decision_maker") is True
    virtual = {
        "_place": lead.get("locality") or lead.get("project_name"),
        "_budget": budget,
        "_owner": True if owner_known else None,
    }
    missing = [label for key, label in REQUIRED
               if (virtual[key] if key.startswith("_") else lead.get(key)) in (None, "", "unknown")]

    # ── score (priority within a class) ─────────────────────────
    score = 0
    scope = lead.get("scope")
    score += {"full_home": 25, "turnkey": 25, "renovation": 18, "modular_kitchen": 14,
              "wardrobes": 10, "partial": 10}.get(scope, 0)
    if scope in ("full_home", "turnkey"):
        reasons.append("+ Complete-home / turnkey scope")

    min_b = min_budget_for(lead, s, outstation)
    tol = float(s.get("budget_tolerance") or 0.85)
    budget_ok = bool(budget) and budget >= min_b * tol
    budget_full = bool(budget) and budget >= min_b
    if budget:
        ratio = budget / min_b
        score += min(25, int(ratio * 15))
        lakh = lambda v: f"₹{v / 100000:.1f}L".replace(".0L", "L")
        reasons.append(("+ " if budget_ok else "− ") + f"Budget {lakh(budget)} vs minimum {lakh(min_b)}")

    timeline = lead.get("timeline")
    score += {"immediate": 20, "within_1_month": 18, "1_to_3_months": 12, "3_to_6_months": 6}.get(timeline, 0)
    if timeline:
        reasons.append(("+ " if timeline in SOON_TIMELINE else "− ") + "Timeline " + timeline.replace("_", " "))

    poss = lead.get("possession_status")
    score += {"received": 20, "within_3_months": 16, "3_to_6_months": 10, "6_to_12_months": 5}.get(poss, 0)
    if poss in NEAR_POSSESSION:
        reasons.append("+ Possession " + poss.replace("_", " "))
    elif poss in ("6_to_12_months", "over_12_months"):
        reasons.append("− Possession " + poss.replace("_", " "))

    if in_handover_list:
        score += 5
        reasons.append("+ Project is in the handover list")
    if lead.get("consult_slot") or lead.get("consult_slot_said"):
        score += 10
        reasons.append("+ Consultation slot agreed")
    if (lead.get("area_sqft") or 0) >= 1500:
        score += 5
    if lead.get("property_type") in ("villa", "independent_house", "penthouse"):
        score += 5
        reasons.append("+ " + lead["property_type"].replace("_", " ").title())
    if outstation:
        reasons.append("− Outstation project")
    score = max(0, min(100, score))

    if missing:
        return Verdict("qualifying", None, score, reasons, missing)

    # ── classification ──────────────────────────────────────────
    if budget and budget < min_b * 0.5:
        return Verdict("disqualified", None, score, reasons, [], "Budget far below Papillon's range")
    if lead.get("willing_consultation") is False:
        return Verdict("nurture", "cold", score, reasons + ["− Not ready to meet the team yet"], [])
    if timeline not in DEFINED_TIMELINE:
        return Verdict("nurture", "cold", score, reasons, [])
    if not budget_ok:
        return Verdict("nurture", "cold", score, reasons, [])

    if timeline in FAST_TIMELINE and poss in NEAR_POSSESSION and budget_full:
        return Verdict("qualified", "hot", score, reasons, [])
    if timeline in SOON_TIMELINE:
        return Verdict("qualified", "warm", score, reasons, [])
    return Verdict("qualified", "cold", score, reasons, [])  # 3–6 months: genuine, kept warm by nurture
