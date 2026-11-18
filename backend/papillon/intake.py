"""Every enquiry — website, Meta, Google, CSV, manual — goes through ingest()."""

from __future__ import annotations

import re

from datetime import datetime, time, timedelta, timezone

from . import db
from .config import IST
from .parsing import (map_configuration, map_ownership, map_possession, map_property_type, map_scope,
                      map_timeline, normalize_phone, parse_area, parse_budget)


def next_call_time(after: datetime, s: dict) -> datetime:
    """First moment at or after `after` that falls inside the calling window (IST)."""
    start: time = s["call_window_start"]
    end: time = s["call_window_end"]
    days = set(s["call_days"] or [1, 2, 3, 4, 5, 6, 7])
    t = after.astimezone(IST)
    for _ in range(14):
        if t.isoweekday() in days:
            if t.time() < start:
                return t.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
            if t.time() < end:
                return t
        t = (t + timedelta(days=1)).replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    return t


def in_window(now: datetime, s: dict) -> bool:
    return next_call_time(now, s) <= now + timedelta(seconds=1)


async def match_project(name: str | None) -> tuple[str | None, bool]:
    """Find the project in the handover list. Returns (project_id, possession is within ±6 months)."""
    if not name or len(name.strip()) < 3:
        return None, False
    row = await db.fetchone(
        """select id, possession_from, possession_to from projects
           where %(n)s ilike '%%' || name || '%%' or name ilike '%%' || %(n)s || '%%'
           order by length(name) desc limit 1""",
        {"n": name.strip()},
    )
    if not row:
        return None, False
    today = datetime.now(IST).date()
    lo, hi = row["possession_from"], row["possession_to"] or row["possession_from"]
    near = bool(lo and hi and lo - timedelta(days=183) <= today <= hi + timedelta(days=183))
    return str(row["id"]), near


async def upsert_campaign(source: str, external_id: str | None, name: str | None) -> str | None:
    if not external_id and not name:
        return None
    key = external_id or f"{source}:{name}"
    row = await db.fetchone(
        """insert into campaigns (name, source, external_id, started_on)
           values (%s, %s, %s, current_date)
           on conflict (external_id) do update set name = coalesce(campaigns.name, excluded.name)
           returning id""",
        [name or key, source if source in ("meta", "google", "website", "portal", "referral", "partner", "import", "manual") else "other", key],
    )
    return str(row["id"])


# Custom form questions arrive with keys like "what_is_your_interior_budget" — map them by keyword
_KEY_HINTS = [
    (r"(where|which).*(live|stay|reside)|current_city|your_city|lives", "lives_in"),
    (r"budget", "budget"), (r"possession|handover|hand_over", "possession"),
    (r"bhk|configuration", "configuration"), (r"sq_?ft|carpet|area_of|size", "area_sqft"),
    (r"own(er|ership)|in_your_name", "ownership"), (r"when|timeline|start", "timeline"),
    (r"property_type|type_of_property|kind_of_property", "property_type"),
    (r"project|society|apartment_name|builder", "project"),
    (r"locality|location|area$", "locality"), (r"city", "city"),
    (r"requirement|scope|need|looking_for|interested_in", "scope"),
]


def _canonical(a: dict) -> dict:
    out = {}
    for k, v in a.items():
        key = k
        for pat, canon in _KEY_HINTS:
            if re.search(pat, k):
                key = canon
                break
        out.setdefault(key, v)
    return out


def prefill_from_answers(a: dict) -> dict:
    """Map whatever the form asked into lead columns. The call confirms all of it anyway."""
    a = _canonical(a)
    g = lambda *keys: next((a[k] for k in keys if a.get(k) not in (None, "")), None)
    out = {}
    if v := g("city", "property_city"):
        out["city"] = str(v)[:80]
    if v := g("locality", "area", "location", "property_location"):
        out["locality"] = str(v)[:120]
    if v := g("project", "project_name", "society", "apartment_name"):
        out["project_name"] = str(v)[:120]
    if v := g("property_type", "type"):
        out["property_type"] = map_property_type(v)
    if v := g("configuration", "bhk", "config"):
        out["configuration"] = map_configuration(v)
    if v := g("area_sqft", "carpet_area", "size", "sqft"):
        out["area_sqft"] = parse_area(v)
    if v := g("scope", "requirement", "interior_requirement", "what_do_you_need"):
        out["scope"] = map_scope(v)
        out["scope_detail"] = str(v)[:200]
    if v := g("budget", "interior_budget"):
        out["budget_said"] = str(v)[:80]
        out["budget_min"], out["budget_max"] = parse_budget(v)
    if v := g("possession", "possession_status", "handover"):
        out["possession_status"] = map_possession(v)
    if v := g("timeline", "when", "start_time"):
        out["timeline"] = map_timeline(v)
    if v := g("ownership", "are_you_the_owner"):
        out["ownership"] = map_ownership(v)
    if v := g("lives_in", "current_city", "your_city"):
        out["lives_in"] = str(v)[:80]
    return {k: v for k, v in out.items() if v is not None}


async def ingest(lead_in: dict, actor: str = "system") -> tuple[dict, bool]:
    """Create or merge a lead. Returns (lead, created)."""
    norm = normalize_phone(lead_in.get("phone"), lead_in.get("phone_region") or "IN")
    if not norm:
        raise ValueError("invalid phone number")
    phone, country = norm
    s = await db.get_settings()
    now = datetime.now(timezone.utc)
    source = lead_in.get("source") or "website"
    campaign_id = await upsert_campaign(source, lead_in.get("campaign_external_id"), lead_in.get("campaign_name"))
    answers = lead_in.get("form_answers") or {}
    pre = prefill_from_answers(answers)
    consent = bool(lead_in.get("consent_call"))

    existing = await db.fetchone("select * from leads where phone = %s", [phone])
    if existing:
        merged = {k: v for k, v in pre.items() if existing.get(k) in (None, "")}
        requeue = existing["status"] in ("unreachable", "nurture", "new") and consent
        await db.execute(
            "update leads set enquiry_count = enquiry_count + 1, form_answers = form_answers || %s where id = %s",
            [answers, existing["id"]],
        )
        if requeue:
            merged.update(status="queued", call_attempts=0, next_call_at=next_call_time(now, s))
        lead = await db.update_lead(existing["id"], **merged) if merged else await db.get_lead(existing["id"])
        await db.log_event(existing["id"], "repeat_enquiry", {"source": source, "requeued": requeue}, actor)
        return lead, False

    project_id, _ = await match_project(pre.get("project_name"))
    # Indian mobiles get a call; overseas numbers (NRI buyers) are qualified on WhatsApp first
    channel = "voice" if country == "IN" else "whatsapp"
    status = "queued" if consent else "new"
    lead = await db.fetchone(
        """insert into leads (name, phone, phone_country, email, lives_in, source, campaign_id, external_lead_id,
                              utm, form_answers, consent_call, consent_text, consent_at, consent_ip,
                              city, locality, project_name, project_id, property_type, configuration, area_sqft,
                              scope, scope_detail, budget_said, budget_min, budget_max, possession_status, timeline,
                              ownership, status, channel, next_call_at)
           values (%(name)s, %(phone)s, %(country)s, %(email)s, %(lives_in)s, %(source)s, %(campaign_id)s, %(ext)s,
                   %(utm)s, %(answers)s, %(consent)s, %(consent_text)s, %(consent_at)s, %(consent_ip)s,
                   %(city)s, %(locality)s, %(project_name)s, %(project_id)s, %(property_type)s, %(configuration)s, %(area_sqft)s,
                   %(scope)s, %(scope_detail)s, %(budget_said)s, %(budget_min)s, %(budget_max)s, %(possession_status)s, %(timeline)s,
                   %(ownership)s, %(status)s, %(channel)s, %(next_call_at)s)
           returning *""",
        {
            "name": (lead_in.get("name") or "").strip()[:120] or None,
            "phone": phone, "country": country,
            "email": (lead_in.get("email") or "").strip()[:160] or None,
            "lives_in": pre.get("lives_in") or lead_in.get("lives_in"),
            "source": source, "campaign_id": campaign_id, "ext": lead_in.get("external_lead_id"),
            "utm": lead_in.get("utm") or {}, "answers": answers,
            "consent": consent, "consent_text": lead_in.get("consent_text"),
            "consent_at": now if consent else None, "consent_ip": lead_in.get("consent_ip"),
            "project_id": project_id,
            **{k: pre.get(k) for k in ("city", "locality", "project_name", "property_type", "configuration", "area_sqft",
                                        "scope", "scope_detail", "budget_said", "budget_min", "budget_max",
                                        "possession_status", "timeline", "ownership")},
            "status": status, "channel": channel,
            "next_call_at": next_call_time(now, s) if consent else None,
        },
    )
    await db.log_event(lead["id"], "created", {"source": source, "channel": channel, "consent": consent}, actor)
    return lead, True
