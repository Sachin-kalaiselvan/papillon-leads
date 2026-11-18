"""Normalising messy form answers: phone numbers, rupee amounts, and free-text choices."""

from __future__ import annotations

import re

import phonenumbers


def normalize_phone(raw: str | None, default_region: str = "IN") -> tuple[str, str] | None:
    """Return (E.164, ISO country) or None if it isn't a real, dialable number."""
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    digits = re.sub(r"\D", "", raw)
    if not raw.startswith("+") and len(digits) == 12 and digits.startswith("91"):
        raw = "+" + digits
    try:
        num = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164), phonenumbers.region_code_for_number(num)


_UNIT = {
    "crore": 10_000_000, "cr": 10_000_000, "crores": 10_000_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "l": 100_000, "lk": 100_000,
    "k": 1_000, "thousand": 1_000,
}


def parse_budget(text: str | None) -> tuple[int | None, int | None]:
    """'15-20 lakhs' → (1500000, 2000000); '1.2 Cr' → (12000000, 12000000); '₹18,00,000' → (1800000, 1800000).
    'above 25L' → (2500000, None)…  handled as min only."""
    if not text:
        return None, None
    t = str(text).lower().replace("₹", " ").replace("rs.", " ").replace("rs", " ").replace("inr", " ")
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    t = t.replace("to", "-").replace("–", "-").replace("—", "-")
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|lk|l|k|thousand)?\b", t)
    values: list[int] = []
    trailing_unit = None
    for _, unit in reversed(nums):
        if unit:
            trailing_unit = unit
            break
    for n, unit in nums:
        mult = _UNIT.get(unit or "", None)
        if mult is None:
            v = float(n)
            # bare "15" or "15-20" in an interiors budget question means lakhs
            mult = _UNIT[trailing_unit] if trailing_unit else (1 if v >= 10_000 else 100_000)
        values.append(int(float(n) * mult))
    values = [v for v in values if v >= 10_000]
    if not values:
        return None, None
    if re.search(r"\b(above|over|more than|min|minimum|\+)", t) or t.strip().endswith("+"):
        return min(values), None
    if re.search(r"\b(below|under|less than|upto|up -|max|within)\b", t):
        return None, max(values)
    return min(values), max(values)


def _pick(text: str | None, table: list[tuple[str, str]]) -> str | None:
    t = (text or "").lower()
    if not t:
        return None
    for needle, value in table:
        if re.search(needle, t):
            return value
    return None


def map_property_type(t):
    return _pick(t, [(r"commercial|office|shop|retail|showroom", "commercial"), (r"villa", "villa"),
                     (r"row ?house|town ?house", "row_house"), (r"penthouse", "penthouse"),
                     (r"independent|bungalow|house|duplex", "independent_house"),
                     (r"apartment|flat|condo|bhk|gated", "apartment"), (r"plot|land", "plot")])


def map_scope(t):
    return _pick(t, [(r"turnkey|end to end|end-to-end", "turnkey"), (r"full|complete|entire|whole", "full_home"),
                     (r"kitchen", "modular_kitchen"), (r"wardrobe|closet", "wardrobes"),
                     (r"renovat|remodel", "renovation"), (r"partial|few rooms|living|bedroom", "partial")])


def map_possession(t):
    return _pick(t, [(r"received|got|ready|handed|moved|done|completed|already", "received"),
                     (r"(within|next|in)\s*(1|2|3|one|two|three)\s*month|0-3|0 - 3|this month|next month", "within_3_months"),
                     (r"3\s*-\s*6|3 to 6|three to six|4 months|5 months|6 months", "3_to_6_months"),
                     (r"6\s*-\s*12|6 to 12|this year|within a year|12 months", "6_to_12_months"),
                     (r"more than|over a year|1\+|2026|2027|2028|under construction", "over_12_months")])


def map_timeline(t):
    return _pick(t, [(r"immediate|asap|right away|now|urgent", "immediate"),
                     (r"(within|in|next)\s*(a|1|one|2|two|3|four|4)?\s*week|this month|within (a|1|one) month|1 month", "within_1_month"),
                     (r"1\s*-\s*3|1 to 3|2 months|3 months|two months|three months|couple of months", "1_to_3_months"),
                     (r"3\s*-\s*6|3 to 6|4 months|5 months|6 months|six months", "3_to_6_months"),
                     (r"later|next year|more than 6|over 6|6\+|not sure|undecided|just exploring|planning", "undecided")])


def map_ownership(t):
    return _pick(t, [(r"tenant|rent", "tenant"), (r"broker|agent|channel partner", "broker"),
                     (r"co.?owner|joint|spouse|wife|husband", "co_owner"),
                     (r"family|father|mother|parents|son|daughter|brother|sister", "family_decision_maker"),
                     (r"authori[sz]ed|representative|power of attorney|poa|manager", "authorised_representative"),
                     (r"owner|own|bought|purchased|mine|yes", "owner")])


def map_configuration(t):
    if not t:
        return None
    m = re.search(r"(\d(?:\.5)?)\s*-?\s*bhk", str(t).lower())
    if m:
        return f"{m.group(1)}BHK"
    if re.search(r"villa|independent|duplex", str(t).lower()):
        return str(t).strip()[:40]
    m = re.search(r"\b(\d)\b", str(t))
    return f"{m.group(1)}BHK" if m else str(t).strip()[:40]


def parse_area(t) -> int | None:
    if t is None:
        return None
    m = re.search(r"(\d[\d,]{2,})", str(t))
    if not m:
        return None
    v = int(m.group(1).replace(",", ""))
    if "sq m" in str(t).lower() or "sqm" in str(t).lower():
        v = int(v * 10.764)
    return v if 200 <= v <= 30000 else None
