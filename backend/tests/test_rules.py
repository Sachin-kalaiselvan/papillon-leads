from datetime import datetime, time

from papillon.config import IST
from papillon.intake import _canonical, next_call_time, prefill_from_answers
from papillon.parsing import normalize_phone, parse_budget
from papillon.scoring import evaluate

S = {
    "service_areas": ["bengaluru", "bangalore", "whitefield", "sarjapur"], "accept_outstation": False,
    "outstation_min_budget": 2500000, "min_budget_full_home": 1500000, "min_budget_kitchen": 300000,
    "min_budget_wardrobes": 200000, "min_budget_partial": 500000, "budget_tolerance": 0.85,
    "forward_temperatures": ["hot", "warm"], "call_window_start": time(10), "call_window_end": time(19, 30),
    "call_days": [1, 2, 3, 4, 5, 6, 7],
}

GOOD = dict(city="Bengaluru", locality="Sarjapur Road", project_name="Prestige Lakeside", property_type="apartment",
            configuration="3BHK", area_sqft=1650, possession_status="received", scope="full_home",
            budget_min=1800000, budget_max=2200000, timeline="within_1_month", ownership="owner",
            willing_consultation=True)


def test_phone():
    assert normalize_phone("98450 12345") == ("+919845012345", "IN")
    assert normalize_phone("919845012345") == ("+919845012345", "IN")
    assert normalize_phone("+971 50 123 4567") == ("+971501234567", "AE")
    assert normalize_phone("12345") is None


def test_budget():
    assert parse_budget("15-20 lakhs") == (1500000, 2000000)
    assert parse_budget("₹18,00,000") == (1800000, 1800000)
    assert parse_budget("1.2 Cr") == (12000000, 12000000)
    assert parse_budget("above 25L") == (2500000, None)
    assert parse_budget("15 to 25") == (1500000, 2500000)
    assert parse_budget("under 10 lakhs") == (None, 1000000)


def test_hot():
    v = evaluate(GOOD, S)
    assert (v.status, v.temperature) == ("qualified", "hot")
    assert v.forwardable(S)


def test_warm_and_cold():
    assert evaluate({**GOOD, "timeline": "1_to_3_months"}, S).temperature == "warm"
    assert evaluate({**GOOD, "possession_status": "3_to_6_months"}, S).temperature == "warm"
    v = evaluate({**GOOD, "timeline": "3_to_6_months"}, S)
    assert (v.status, v.temperature) == ("qualified", "cold") and not v.forwardable(S)
    assert evaluate({**GOOD, "timeline": "undecided"}, S).status == "nurture"
    assert evaluate({**GOOD, "willing_consultation": False}, S).status == "nurture"


def test_budget_rules():
    assert evaluate({**GOOD, "budget_min": 1300000, "budget_max": 1300000}, S).temperature == "warm"   # within 85%
    assert evaluate({**GOOD, "budget_min": 1000000, "budget_max": 1000000}, S).status == "nurture"
    assert evaluate({**GOOD, "budget_min": 500000, "budget_max": 500000}, S).status == "disqualified"
    kitchen = {**GOOD, "scope": "modular_kitchen", "budget_min": 400000, "budget_max": 400000}
    assert evaluate(kitchen, S).status == "qualified"


def test_hard_stops():
    assert evaluate({**GOOD, "ownership": "tenant"}, S).status == "disqualified"
    assert evaluate({**GOOD, "property_type": "commercial"}, S).status == "disqualified"
    out = {**GOOD, "city": "Chennai", "locality": "OMR", "project_name": None}
    assert evaluate(out, S).status == "out_of_area"
    assert evaluate(out, {**S, "accept_outstation": True}).status == "qualified"


def test_nri_buyer_is_fine():
    # lives in Dubai, property in Bengaluru → qualifies normally
    assert evaluate({**GOOD, "lives_in": "Dubai"}, S).temperature == "hot"


def test_missing_details():
    v = evaluate({**GOOD, "budget_min": None, "budget_max": None, "ownership": None}, S)
    assert v.status == "qualifying" and "budget" in v.missing and "ownership / decision-maker" in v.missing


def test_call_window():
    late = datetime(2026, 11, 18, 21, 0, tzinfo=IST)
    nxt = next_call_time(late, S)
    assert (nxt.day, nxt.hour) == (19, 10)
    mid = datetime(2026, 11, 18, 12, 0, tzinfo=IST)
    assert next_call_time(mid, S) == mid


def test_form_keys():
    a = {"what_is_your_interior_budget?": "20-25 lakhs", "when_is_possession": "already received",
         "which_city_do_you_currently_live_in": "Dubai", "property_location": "Whitefield", "bhk": "3 BHK"}
    a = {k.replace("?", ""): v for k, v in a.items()}
    p = prefill_from_answers(a)
    assert p["budget_min"] == 2000000 and p["possession_status"] == "received"
    assert p["lives_in"] == "Dubai" and p["locality"] == "Whitefield" and p["configuration"] == "3BHK"
    assert _canonical({"city": "Bengaluru"}) == {"city": "Bengaluru"}
