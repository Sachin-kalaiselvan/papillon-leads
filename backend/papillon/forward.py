"""Hands a qualified lead to Papillon's team — and only to them (brief point 10)."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from . import db, notify
from .config import IST, cfg

LABEL = {
    "full_home": "Complete home interiors", "turnkey": "Turnkey project", "modular_kitchen": "Modular kitchen",
    "wardrobes": "Wardrobes", "partial": "Partial interiors", "renovation": "Renovation", "other": "Other",
    "received": "Possession received", "within_3_months": "Possession within 3 months",
    "3_to_6_months": "Possession in 3–6 months", "6_to_12_months": "Possession in 6–12 months",
    "over_12_months": "Possession 12+ months away", "immediate": "Start immediately",
    "within_1_month": "Start within a month", "1_to_3_months": "Start in 1–3 months",
    "3_to_6_months_t": "Start in 3–6 months",
}


def lakh(v) -> str:
    if not v:
        return "—"
    return f"₹{v / 100000:.1f} L".replace(".0 L", " L")


def budget_text(lead: dict) -> str:
    lo, hi = lead.get("budget_min"), lead.get("budget_max")
    if lo and hi and lo != hi:
        return f"{lakh(lo)} – {lakh(hi)}"
    return lakh(hi or lo) + (" +" if lo and not hi else "")


def card_lines(lead: dict) -> list[tuple[str, str]]:
    place = ", ".join(x for x in [lead.get("project_name"), lead.get("locality"), lead.get("city")] if x)
    tl = lead.get("timeline") or ""
    return [
        ("Name", lead.get("name") or "—"),
        ("Phone", lead["phone"]),
        ("Property", f"{lead.get('configuration') or ''} {(lead.get('property_type') or '').replace('_', ' ')}".strip() or "—"),
        ("Location", place or "—"),
        ("Area", f"{lead['area_sqft']} sq ft" if lead.get("area_sqft") else "—"),
        ("Possession", LABEL.get(lead.get("possession_status"), "—")),
        ("Requirement", LABEL.get(lead.get("scope"), "—") + (f" — {lead['scope_detail']}" if lead.get("scope_detail") else "")),
        ("Budget", budget_text(lead)),
        ("Timeline", LABEL.get(tl if tl != "3_to_6_months" else "3_to_6_months_t", tl.replace("_", " ") or "—")),
        ("Owner / decision-maker", (lead.get("ownership") or "—").replace("_", " ")),
        ("Consultation", (lead.get("consult_slot_said") or (lead["consult_slot"].astimezone(IST).strftime("%a %d %b, %I:%M %p")
                          if lead.get("consult_slot") else "To be scheduled")) + (f" ({lead['consult_mode']})" if lead.get("consult_mode") else "")),
        ("Lives in", lead.get("lives_in") or "—"),
        ("Source", lead.get("source") or "—"),
    ]


async def forward_lead(lead: dict, s: dict) -> dict:
    now = datetime.now(timezone.utc)
    temp = (lead.get("temperature") or "").upper()
    link = f"{cfg.dashboard_url}/leads/{lead['id']}"
    summary = lead.get("ai_summary") or ""
    one_line = f"{lead.get('configuration') or ''} {lead.get('locality') or lead.get('city') or ''}, {budget_text(lead)}".strip()

    for num in s.get("forward_whatsapp") or []:
        await notify.wa_template(num, cfg.wa_tpl_forward,
                                 [temp, f"{lead['ref']} {lead.get('name') or ''}".strip(), one_line, summary[:300] or "—", link],
                                 lead["id"], f"Forwarded {lead['ref']} to {num}")

    rows = "".join(f"<tr><td style='padding:6px 14px 6px 0;color:#7a6f66'>{html.escape(k)}</td>"
                   f"<td style='padding:6px 0;color:#1f1a24'><b>{html.escape(str(v))}</b></td></tr>" for k, v in card_lines(lead))
    reasons = "".join(f"<li>{html.escape(r)}</li>" for r in lead.get("score_reasons") or [])
    body = f"""<div style="font-family:Georgia,serif;max-width:620px;margin:auto;background:#f6f1ea;padding:28px;border-radius:14px">
<div style="font:600 12px Arial;letter-spacing:.14em;color:#b08442">{html.escape(cfg.brand_name.upper())} · QUALIFIED LEAD</div>
<h2 style="margin:8px 0 4px;color:#1f1a24">{html.escape(temp)} · {html.escape(lead['ref'])}</h2>
<p style="color:#4a4048;font:15px/1.5 Arial">{html.escape(summary)}</p>
<table style="font:14px Arial;border-collapse:collapse;margin:14px 0">{rows}</table>
<div style="font:13px Arial;color:#4a4048"><b>Why it qualified</b><ul>{reasons}</ul></div>
<a href="{link}" style="display:inline-block;background:#1f1a24;color:#f6f1ea;padding:12px 20px;border-radius:999px;text-decoration:none;font:600 14px Arial">Open lead and WhatsApp chat</a>
<p style="font:11px Arial;color:#9a8f86;margin-top:22px">Exclusive to {html.escape(cfg.brand_name)}. This enquiry has not been shared with any other company.</p></div>"""
    text = "\n".join(f"{k}: {v}" for k, v in card_lines(lead)) + f"\n\n{summary}\n\n{link}"
    await notify.email(s.get("forward_emails") or [], f"[{temp}] New qualified lead {lead['ref']} — {one_line}", body, text, lead["id"])

    lead = await db.update_lead(lead["id"], stage="forwarded", forwarded_at=now, stage_updated_at=now)
    await db.log_event(lead["id"], "forwarded", {
        "to_whatsapp": s.get("forward_whatsapp") or [], "to_email": s.get("forward_emails") or [],
        "temperature": lead.get("temperature"), "exclusive_to": cfg.brand_name,
    })
    return lead
