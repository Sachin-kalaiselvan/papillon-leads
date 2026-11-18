"""What the assistant asks, how answers are saved, and what happens when a conversation ends.
Shared by the phone call (voice_bot.py) and WhatsApp (whatsapp.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db
from .config import IST, cfg
from .intake import match_project, next_call_time
from .parsing import parse_budget
from .scoring import evaluate

ENUMS = {
    "property_type": ["apartment", "villa", "independent_house", "row_house", "penthouse", "plot", "commercial", "other"],
    "possession_status": ["received", "within_3_months", "3_to_6_months", "6_to_12_months", "over_12_months", "unknown"],
    "scope": ["full_home", "turnkey", "modular_kitchen", "wardrobes", "partial", "renovation", "other"],
    "timeline": ["immediate", "within_1_month", "1_to_3_months", "3_to_6_months", "over_6_months", "undecided"],
    "ownership": ["owner", "co_owner", "family_decision_maker", "authorised_representative", "tenant", "broker", "other", "unknown"],
    "consult_mode": ["site", "studio", "video", "phone"],
}

SAVE_PROPS = {
    "name": {"type": "string", "description": "Person's name as they say it"},
    "property_type": {"type": "string", "enum": ENUMS["property_type"]},
    "project_name": {"type": "string", "description": "Apartment project / society / layout name, with builder if said"},
    "locality": {"type": "string", "description": "Area or locality of the PROPERTY, e.g. Sarjapur Road, Whitefield"},
    "city": {"type": "string", "description": "City of the PROPERTY (not where the person lives)"},
    "lives_in": {"type": "string", "description": "Where the person currently lives, if different (e.g. Dubai, Pune)"},
    "configuration": {"type": "string", "description": "e.g. 2BHK, 3BHK, 4BHK, 3BHK villa"},
    "area_sqft": {"type": "integer", "description": "Carpet or super built-up area in sq ft"},
    "possession_status": {"type": "string", "enum": ENUMS["possession_status"]},
    "scope": {"type": "string", "enum": ENUMS["scope"], "description": "full_home = complete home interiors"},
    "scope_detail": {"type": "string", "description": "Rooms / items they mentioned"},
    "budget_min_inr": {"type": "integer", "description": "Lower end of interior budget in rupees (15 lakh = 1500000)"},
    "budget_max_inr": {"type": "integer", "description": "Upper end of interior budget in rupees"},
    "budget_said": {"type": "string", "description": "Budget exactly as they said it"},
    "timeline": {"type": "string", "enum": ENUMS["timeline"], "description": "When they want interior work to START"},
    "ownership": {"type": "string", "enum": ENUMS["ownership"]},
    "decision_maker": {"type": "boolean", "description": "Are they the one who decides on the interiors"},
    "other_designers": {"type": "string", "description": "Whether they're talking to other designers / have quotes"},
    "willing_consultation": {"type": "boolean", "description": "Open to a free consultation with Papillon's designer"},
    "consult_mode": {"type": "string", "enum": ENUMS["consult_mode"]},
    "consult_slot_iso": {"type": "string", "description": "Agreed consultation date-time, ISO 8601 with +05:30"},
    "consult_slot_said": {"type": "string", "description": "Consultation time as they said it"},
    "language": {"type": "string", "description": "Language they're most comfortable in"},
    "notes": {"type": "string", "description": "Anything else useful for the designer (style, family, pets, vastu…)"},
}

END_PROPS = {
    "outcome": {"type": "string", "enum": ["completed", "callback", "not_interested", "wrong_number", "do_not_call",
                                           "language_barrier", "incomplete"]},
    "summary": {"type": "string", "description": "2–3 line summary for Papillon's designer"},
    "callback_iso": {"type": "string", "description": "If outcome=callback: when to call back, ISO 8601 with +05:30"},
}


def _known(lead: dict) -> str:
    lines = []
    for k, label in [("name", "Name"), ("city", "City"), ("locality", "Locality"), ("project_name", "Project"),
                     ("property_type", "Property type"), ("configuration", "Configuration"), ("area_sqft", "Area sq ft"),
                     ("possession_status", "Possession"), ("scope", "Scope"), ("budget_said", "Budget"),
                     ("timeline", "Timeline"), ("ownership", "Ownership")]:
        if lead.get(k) not in (None, ""):
            lines.append(f"- {label}: {lead[k]}")
    return "\n".join(lines) or "- nothing yet"


def system_prompt(lead: dict, channel: str) -> str:
    now = datetime.now(IST)
    voice = channel == "voice"
    style = (
        "You are on a PHONE CALL. Speak in short, warm, natural Indian-English sentences — one question at a time, "
        "never more than two sentences per turn. No lists, no emojis, no markdown. Say amounts the Indian way "
        "(\"fifteen lakhs\"). If they interrupt, stop and listen."
        if voice else
        "You are chatting on WHATSAPP. Keep each message short (1–3 lines), one question at a time, friendly and "
        "businesslike. No long paragraphs. Simple emojis are fine but rare."
    )
    return f"""You are {cfg.brand_agent_name}, the virtual assistant for {cfg.brand_name}, a residential interior design studio in Bengaluru.
The person enquired about home interiors. Your job: understand their requirement properly so the right designer can follow up. You are not a salesperson and you never pressure anyone.

{style}

Current time: {now:%A %d %B %Y, %I:%M %p} IST.
What we already know from their enquiry (confirm it, don't re-ask from scratch):
{_known(lead)}

Find out, in a natural order:
1. Where the property is — project/society name, locality and city. (The person may live anywhere — Dubai, the US, Pune — that's fine; we need where the PROPERTY is.)
2. Property type and configuration (apartment/villa/independent house; 2/3/4 BHK) and the approximate area in sq ft.
3. Possession status — already received, or expected when.
4. What they need — complete home interiors / turnkey, modular kitchen, wardrobes, or a few rooms.
5. Indicative interior budget. Ask: "To suggest the right design approach, what budget range do you have in mind for the interiors, roughly?" If they hesitate, offer ranges: under 10 lakhs, 10 to 15, 15 to 25, 25 to 40, above 40 lakhs.
6. When they'd like work to start.
7. Whether the home is in their name or whether they're deciding for family — ask politely, e.g. "Is the home in your name, or are you planning it for family?"
8. Whether they'd like a free design consultation — at the site, at our studio, or on a video call — and which day and time suits them.

Rules:
- Call save_details as soon as you learn anything new (several fields at once is fine). Convert budgets to rupees (15 lakh = 1500000, 1.2 crore = 12000000).
- Never quote prices, packages or timelines for the work. If asked about cost: "It really depends on the design and materials — the designer will give you a detailed quote after understanding your home."
- Never promise discounts. Never mention other interior companies.
- If they're busy, ask when to call back, then call end_conversation with outcome "callback" and callback_iso.
- If it's a wrong number, they're not interested, or they ask not to be contacted, apologise briefly, then end_conversation with the matching outcome.
- If they aren't comfortable in English, say a team member who speaks their language will reach out, save the language, and end with outcome "language_barrier".
- If you are asked whether you're a person, say you're Papillon's virtual assistant and a designer from the team will follow up.
- When you have everything (or they want to stop), thank them, say "our design team will get in touch", then call end_conversation with outcome "completed" (or "incomplete" if key details are missing) and a short summary for the designer.
"""


def greeting(lead: dict) -> str:
    first = (lead.get("name") or "").split(" ")[0]
    hello = f"Hello, am I speaking with {first}?" if first else "Hello!"
    return (f"{hello} This is {cfg.brand_agent_name}, the virtual assistant from {cfg.brand_name}. "
            f"You'd enquired about interiors for your home — is this a good time for two minutes?")


def _parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=IST)
    except ValueError:
        return None


async def apply_details(lead_id, args: dict) -> dict:
    """Save whatever the assistant extracted. Ignores invalid enum values instead of failing the call."""
    upd: dict = {}
    for k, v in args.items():
        if v in (None, ""):
            continue
        if k in ENUMS and v not in ENUMS[k]:
            continue
        if k == "budget_min_inr":
            upd["budget_min"] = int(v)
        elif k == "budget_max_inr":
            upd["budget_max"] = int(v)
        elif k == "consult_slot_iso":
            if d := _parse_iso(v):
                upd["consult_slot"] = d
        elif k == "area_sqft":
            try:
                iv = int(v)
                if 200 <= iv <= 30000:
                    upd["area_sqft"] = iv
            except (TypeError, ValueError):
                pass
        elif k in SAVE_PROPS:
            upd[k] = v
    if "budget_said" in upd and "budget_min" not in upd and "budget_max" not in upd:
        upd["budget_min"], upd["budget_max"] = parse_budget(upd["budget_said"])
    if "project_name" in upd:
        pid, _ = await match_project(upd["project_name"])
        if pid:
            upd["project_id"] = pid
    upd = {k: v for k, v in upd.items() if v is not None}
    lead = await db.update_lead(lead_id, **upd) if upd else await db.get_lead(lead_id)
    if upd:
        await db.log_event(lead_id, "details", {k: str(v) for k, v in upd.items()}, "assistant")
    return lead


async def finalize(lead_id, outcome: str, summary: str | None = None, callback_iso: str | None = None,
                   channel: str = "voice") -> dict:
    """Decide what happens to the lead after a conversation ends."""
    s = await db.get_settings()
    lead = await db.get_lead(lead_id)
    now = datetime.now(timezone.utc)
    base = {"last_contact_at": now}
    if summary:
        base["ai_summary"] = summary

    if outcome == "wrong_number":
        lead = await db.update_lead(lead_id, status="disqualified", disqualify_reason="Wrong number", **base)
    elif outcome == "do_not_call":
        lead = await db.update_lead(lead_id, status="do_not_contact", disqualify_reason="Asked not to be contacted",
                                    next_call_at=None, **base)
    elif outcome == "not_interested":
        lead = await db.update_lead(lead_id, status="disqualified", disqualify_reason="Not interested", next_call_at=None, **base)
    elif outcome == "callback":
        when = _parse_iso(callback_iso) or (now + timedelta(hours=3))
        lead = await db.update_lead(lead_id, status="queued", next_call_at=next_call_time(when, s), **base)
    elif outcome == "language_barrier":
        lead = await db.update_lead(lead_id, status="qualifying", next_call_at=None,
                                    notes=((lead.get("notes") or "") + f"\nNeeds a call in {lead.get('language') or 'another language'}").strip(),
                                    **base)
    else:
        lead = await db.update_lead(lead_id, **base)
        lead = await score_and_route(lead, s, outcome=outcome, channel=channel)
        await db.log_event(lead_id, "conversation_end", {"outcome": outcome, "channel": channel})
        return lead

    await db.log_event(lead_id, "conversation_end", {"outcome": outcome, "channel": channel})
    return lead


async def score_and_route(lead: dict, s: dict, outcome: str = "completed", channel: str = "voice") -> dict:
    from . import forward, whatsapp

    near = False
    if lead.get("project_id"):
        _, near = await match_project(lead.get("project_name"))
    v = evaluate(lead, s, in_handover_list=near)
    now = datetime.now(timezone.utc)
    upd = {"score": v.score, "score_reasons": v.reasons, "temperature": v.temperature,
           "disqualify_reason": v.disqualify_reason}

    if v.status == "qualifying":
        # details still missing → ask the rest on WhatsApp; if they don't reply, another call later
        upd.update(status="qualifying", next_call_at=next_call_time(now + timedelta(hours=4), s))
        lead = await db.update_lead(lead["id"], **upd)
        if channel == "voice" and cfg.wa_token:
            await whatsapp.ask_missing(lead, v.missing)
    elif v.status == "qualified":
        upd.update(status="qualified", qualified_at=lead.get("qualified_at") or now)
        if v.forwardable(s):
            upd["next_call_at"] = None
            lead = await db.update_lead(lead["id"], **upd)
            if lead["stage"] == "none":
                lead = await forward.forward_lead(lead, s)
        else:
            upd.update(next_call_at=now + timedelta(days=int(s["nurture_recheck_days"])), call_attempts=0)
            lead = await db.update_lead(lead["id"], **upd)
    elif v.status == "nurture":
        upd.update(status="nurture", next_call_at=now + timedelta(days=int(s["nurture_recheck_days"])), call_attempts=0)
        lead = await db.update_lead(lead["id"], **upd)
    else:  # disqualified / out_of_area
        upd.update(status=v.status, next_call_at=None)
        lead = await db.update_lead(lead["id"], **upd)

    await db.log_event(lead["id"], "scored", {"status": lead["status"], "temperature": lead.get("temperature"),
                                              "score": v.score, "missing": v.missing})
    return lead
