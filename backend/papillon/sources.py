"""Turns each lead source's payload into the common shape ingest() takes."""

from __future__ import annotations

import hashlib
import hmac
import re

import httpx

from .config import cfg

META_CONSENT = "Meta lead form — custom disclaimer: Papillon Interiors may call or WhatsApp me about my interiors enquiry."
GOOGLE_CONSENT = "Google lead form — Papillon Interiors may call or WhatsApp me about my interiors enquiry."


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def verify_meta_signature(raw: bytes, header: str | None) -> bool:
    if not cfg.meta_app_secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    mac = hmac.new(cfg.meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header[7:])


async def fetch_meta_lead(leadgen_id: str) -> dict:
    fields = "created_time,field_data,ad_id,ad_name,adset_name,campaign_id,campaign_name,form_id,platform,is_organic"
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(f"https://graph.facebook.com/{cfg.graph_version}/{leadgen_id}",
                           params={"access_token": cfg.meta_page_token, "fields": fields})
        r.raise_for_status()
        return r.json()


def from_meta(lead: dict) -> dict:
    answers = {_key(f["name"]): (f.get("values") or [""])[0] for f in lead.get("field_data", [])}
    name = answers.pop("full_name", None) or " ".join(x for x in [answers.pop("first_name", ""), answers.pop("last_name", "")] if x)
    return {
        "name": name, "phone": answers.pop("phone_number", None) or answers.pop("phone", None),
        "email": answers.pop("email", None), "source": "meta",
        "campaign_external_id": lead.get("campaign_id"), "campaign_name": lead.get("campaign_name"),
        "external_lead_id": lead.get("id"),
        "utm": {"ad": lead.get("ad_name"), "adset": lead.get("adset_name"), "form_id": lead.get("form_id"),
                "platform": lead.get("platform")},
        "form_answers": answers, "consent_call": True, "consent_text": META_CONSENT,
    }


def from_google(body: dict) -> dict:
    std = {"FULL_NAME", "FIRST_NAME", "LAST_NAME", "PHONE_NUMBER", "EMAIL", "CITY", "POSTAL_CODE", "COUNTRY", "REGION"}
    cols = {}
    for c in body.get("user_column_data", []):
        cid = c.get("column_id") or ""
        cols[_key(cid) if cid in std else _key(c.get("column_name") or cid)] = c.get("string_value")
    name = cols.pop("full_name", None) or " ".join(x for x in [cols.pop("first_name", ""), cols.pop("last_name", "")] if x)
    return {
        "name": name, "phone": cols.pop("phone_number", None), "email": cols.pop("email", None),
        "source": "google", "campaign_external_id": str(body.get("campaign_id") or "") or None,
        "campaign_name": f"Google {body.get('campaign_id')}" if body.get("campaign_id") else None,
        "external_lead_id": body.get("lead_id"),
        "utm": {"gclid": body.get("gcl_id"), "form_id": body.get("form_id"), "adgroup_id": body.get("adgroup_id")},
        "form_answers": cols, "consent_call": True, "consent_text": GOOGLE_CONSENT,
    }


def from_web(body: dict, ip: str | None) -> dict:
    utm = body.get("utm") or {}
    answers = {k: body.get(k) for k in ("city", "locality", "project", "property_type", "configuration", "area_sqft",
                                         "scope", "budget", "possession", "timeline", "ownership", "lives_in", "message")
               if body.get(k)}
    camp = utm.get("utm_campaign")
    return {
        "name": body.get("name"), "phone": body.get("phone"), "email": body.get("email"),
        "phone_region": body.get("country") or "IN",
        "source": "website", "campaign_external_id": f"web:{camp}" if camp else None,
        "campaign_name": camp, "utm": {**utm, "page": body.get("page")}, "form_answers": answers,
        "consent_call": bool(body.get("consent")), "consent_text": body.get("consent_text"), "consent_ip": ip,
    }
