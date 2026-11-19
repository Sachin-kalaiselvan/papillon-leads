"""WhatsApp qualification — the assistant asks Papillon's questions in a chat and scores the answers."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
from loguru import logger

from . import db, notify
from .config import cfg
from .qualifier import END_PROPS, SAVE_PROPS, apply_details, finalize, system_prompt

TOOLS = [
    {"type": "function", "function": {"name": "save_details", "description": "Save details learned about the enquiry.",
                                      "parameters": {"type": "object", "properties": SAVE_PROPS}}},
    {"type": "function", "function": {"name": "end_conversation", "description": "Finish once you have everything or they want to stop.",
                                      "parameters": {"type": "object", "properties": END_PROPS, "required": ["outcome", "summary"]}}},
]

STOP_WORDS = {"stop", "unsubscribe", "don't message", "dont message", "not interested"}


def verify_signature(raw: bytes, header: str | None) -> bool:
    if not cfg.wa_app_secret:
        return True
    if not header or not header.startswith("sha256="):
        return False
    mac = hmac.new(cfg.wa_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header[7:])


def _first(lead: dict) -> str:
    return (lead.get("name") or "there").split(" ")[0]


async def send_intro(lead: dict) -> None:
    """Start the conversation (a template is required to message someone first)."""
    await notify.wa_template(lead["phone"], cfg.wa_tpl_intro, [_first(lead)], lead["id"],
                             f"Hi {_first(lead)}, this is {cfg.brand_name} about your home interiors enquiry. "
                             "Could you reply here so we can understand your requirement?")
    await db.update_lead(lead["id"], status="qualifying", last_contact_at=datetime.now(timezone.utc))
    await db.log_event(lead["id"], "whatsapp_intro", {})


async def send_reminder(lead: dict) -> None:
    await notify.wa_template(lead["phone"], cfg.wa_tpl_reminder, [_first(lead)], lead["id"],
                             f"Hi {_first(lead)}, following up from {cfg.brand_name} on your interiors enquiry. "
                             "Reply here whenever it suits you and we'll take it from there.")
    await db.log_event(lead["id"], "whatsapp_reminder", {"number": lead["call_attempts"]})


async def _history(lead_id) -> list[dict]:
    rows = await db.fetchall(
        "select direction, body from messages where lead_id = %s and channel = 'whatsapp' order by created_at desc limit 30",
        [lead_id],
    )
    out = []
    for r in reversed(rows):
        body = (r["body"] or "").removeprefix("[template] ")
        out.append({"role": "user" if r["direction"] == "in" else "assistant", "content": body})
    return out


async def _llm(messages: list[dict]) -> dict:
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(cfg.llm_api_url,
                            headers={"Authorization": f"Bearer {cfg.llm_api_key}"},
                            json={"model": cfg.llm_model, "messages": messages, "tools": TOOLS, "temperature": 0.4})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]


async def handle_inbound(from_number: str, text: str, wa_id: str | None) -> None:
    phone = "+" + from_number.lstrip("+")
    lead = await db.fetchone("select * from leads where phone = %s", [phone])
    if not lead:
        logger.info("WhatsApp from unknown number {}", phone)
        return
    await db.execute(
        "insert into messages (lead_id, channel, direction, recipient, body, provider_id, status) values (%s,'whatsapp','in',%s,%s,%s,'received')",
        [lead["id"], phone, text, wa_id],
    )
    await db.update_lead(lead["id"], last_contact_at=datetime.now(timezone.utc), call_attempts=0,
                         next_call_at=datetime.now(timezone.utc) + timedelta(hours=24)
                         if lead["status"] in ("queued", "qualifying") else lead["next_call_at"])

    if text.strip().lower() in STOP_WORDS:
        await finalize(lead["id"], "do_not_call", "Opted out on WhatsApp", channel="whatsapp")
        await notify.wa_text(phone, "Understood — we won't message you again. Thank you.", lead["id"])
        return
    # Once a lead is with Papillon's team (or closed), the assistant stays out of the chat
    if lead["stage"] != "none" or lead["status"] in ("disqualified", "do_not_contact", "out_of_area"):
        await db.log_event(lead["id"], "whatsapp_reply_for_team", {"text": text[:300]})
        return

    msgs = [{"role": "system", "content": system_prompt(lead, "whatsapp")}] + await _history(lead["id"])
    for _ in range(4):
        m = await _llm(msgs)
        calls = m.get("tool_calls") or []
        if not calls:
            if m.get("content"):
                await notify.wa_text(phone, m["content"], lead["id"])
            return
        msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": calls})
        ended = None
        for c in calls:
            args = json.loads(c["function"]["arguments"] or "{}")
            if c["function"]["name"] == "save_details":
                await apply_details(lead["id"], args)
                result = {"saved": True}
            else:
                ended = args
                result = {"ok": True}
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})
        if ended:
            if m.get("content"):
                await notify.wa_text(phone, m["content"], lead["id"])
            else:
                await notify.wa_text(phone, "Thank you! Our design team will get in touch with you shortly.", lead["id"])
            await finalize(lead["id"], ended.get("outcome", "completed"), ended.get("summary"), ended.get("callback_iso"),
                           channel="whatsapp")
            return


async def handle_webhook(body: dict) -> None:
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                t = msg.get("type")
                text = (msg.get("text", {}).get("body") if t == "text"
                        else msg.get("button", {}).get("text") if t == "button"
                        else (msg.get("interactive", {}).get("button_reply") or msg.get("interactive", {}).get("list_reply") or {}).get("title")
                        if t == "interactive" else None)
                if text:
                    try:
                        await handle_inbound(msg["from"], text, msg.get("id"))
                    except Exception:  # noqa: BLE001
                        logger.exception("WhatsApp handling failed")
