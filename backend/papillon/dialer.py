"""Places the qualification calls: speed-to-lead on new enquiries, retries, callbacks and nurture re-checks."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from loguru import logger

from . import db, whatsapp
from .config import cfg
from .intake import in_window, next_call_time


def sign(lead_id: str, call_id: str) -> str:
    return hmac.new(cfg.signing_secret.encode(), f"{lead_id}:{call_id}".encode(), hashlib.sha256).hexdigest()[:32]


def verify(lead_id: str, call_id: str, sig: str) -> bool:
    return bool(sig) and hmac.compare_digest(sign(lead_id, call_id), sig)


async def exotel_call(phone: str, lead_id: str, call_id: str) -> str:
    """Exotel Connect Voice AI API: rings the customer, then streams the call to our bot."""
    ws = cfg.public_base_url.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws}/voice/exotel?" + urlencode({"lead": lead_id, "call": call_id, "sig": sign(lead_id, call_id)})
    data = {
        "From": phone,
        "CallerId": cfg.exotel_caller_id,
        "StreamUrl": stream_url,
        "StreamType": "bidirectional",
        "Record": "true" if cfg.exotel_record else "false",
        "RecordingChannels": "dual",
        "TimeLimit": "900",
        "CustomField": call_id,
        "StatusCallback": f"{cfg.public_base_url}/webhooks/exotel/status",
        "StatusCallbackEvents[]": ["answered", "terminal"],
        "StatusCallbackContentType": "application/json",
    }
    url = f"{cfg.exotel_base_url}/v1/Accounts/{cfg.exotel_account_sid}/Calls/connect.json"
    async with httpx.AsyncClient(timeout=20, auth=(cfg.exotel_api_key, cfg.exotel_api_token)) as http:
        r = await http.post(url, data=data)
    if r.status_code >= 300:
        raise RuntimeError(f"Exotel {r.status_code}: {r.text[:300]}")
    j = r.json()
    return (j.get("Call") or j).get("Sid")


async def place_call(lead: dict) -> None:
    attempt = (lead.get("call_attempts") or 0) + 1
    row = await db.fetchone(
        "insert into calls (lead_id, attempt, status) values (%s, %s, 'queued') returning id", [lead["id"], attempt]
    )
    call_id = str(row["id"])
    await db.update_lead(lead["id"], call_attempts=attempt, last_contact_at=datetime.now(timezone.utc))
    try:
        sid = await exotel_call(lead["phone"], str(lead["id"]), call_id)
        await db.execute("update calls set provider_call_id = %s, status = 'ringing' where id = %s", [sid, call_id])
        await db.log_event(lead["id"], "call_started", {"attempt": attempt, "call_id": call_id})
    except Exception as e:  # noqa: BLE001
        logger.error("Call to {} failed to start: {}", lead["ref"], e)
        await db.execute("update calls set status = 'failed', ended_at = now(), outcome = %s where id = %s", [str(e)[:200], call_id])
        await after_unanswered(lead["id"], "failed")


async def after_unanswered(lead_id, status: str) -> None:
    """No answer / busy / failed: retry on the configured schedule, WhatsApp after the first miss."""
    s = await db.get_settings()
    lead = await db.get_lead(lead_id)
    attempts = lead["call_attempts"] or 0
    now = datetime.now(timezone.utc)
    if attempts == 1 and status in ("no_answer", "busy"):
        await whatsapp.send_missed_call(lead)
    if attempts >= s["max_call_attempts"]:
        await db.update_lead(lead_id, status="unreachable", next_call_at=None)
        await db.log_event(lead_id, "unreachable", {"attempts": attempts})
        return
    gaps = s["retry_minutes"] or [10, 120, 1440]
    gap = gaps[min(attempts - 1, len(gaps) - 1)]
    back_to = "qualifying" if lead.get("ai_summary") else "queued"
    await db.update_lead(lead_id, status=back_to, next_call_at=next_call_time(now + timedelta(minutes=gap), s))
    await db.log_event(lead_id, "call_retry_scheduled", {"attempts": attempts, "in_minutes": gap, "reason": status})


EXOTEL_STATUS = {"completed": "completed", "no-answer": "no_answer", "busy": "busy", "failed": "failed",
                 "canceled": "cancelled", "cancelled": "cancelled", "in-progress": "in_progress", "ringing": "ringing"}


async def handle_status(payload: dict) -> None:
    """Exotel StatusCallback (JSON)."""
    sid = payload.get("CallSid") or payload.get("Sid")
    call_id = payload.get("CustomField")
    raw = (payload.get("Status") or payload.get("CallStatus") or payload.get("EventType") or "").lower()
    status = EXOTEL_STATUS.get(raw, raw or "completed")
    call = await db.fetchone("select * from calls where provider_call_id = %s or id::text = %s limit 1", [sid, call_id or ""])
    if not call:
        logger.warning("Status for unknown call {}", sid)
        return
    if raw == "answered" or payload.get("EventType") == "answered":
        await db.execute("update calls set status = 'in_progress', answered_at = coalesce(answered_at, now()) where id = %s", [call["id"]])
        return
    dur = payload.get("ConversationDuration") or payload.get("Duration")
    await db.execute(
        """update calls set status = case when status = 'completed' then status else %s end,
                            ended_at = coalesce(ended_at, now()), duration_sec = coalesce(%s, duration_sec),
                            recording_url = coalesce(%s, recording_url) where id = %s""",
        [status, int(dur) if str(dur or "").isdigit() else None, payload.get("RecordingUrl"), call["id"]],
    )
    if status in ("no_answer", "busy", "failed", "cancelled"):
        await after_unanswered(call["lead_id"], status)
    else:
        # answered — the bot finalises the lead; if it didn't (crash, early hang-up), recover in 45s
        asyncio.create_task(_recover_if_stuck(call["lead_id"]))


async def _recover_if_stuck(lead_id) -> None:
    await asyncio.sleep(45)
    lead = await db.get_lead(lead_id)
    if lead and lead["status"] == "calling":
        from .qualifier import finalize
        await finalize(lead_id, "incomplete")


async def dial_once() -> int:
    s = await db.get_settings()
    now = datetime.now(timezone.utc)

    # overseas numbers and WhatsApp-channel leads: start on WhatsApp (any hour is fine for a template)
    for lead in await db.fetchall(
        """update leads set status = 'qualifying' where id in (
             select id from leads where channel = 'whatsapp' and status = 'queued' and next_call_at <= now()
             order by created_at limit 20 for update skip locked) returning *"""):
        await whatsapp.send_intro(lead)

    if not in_window(now, s):
        return 0
    # stale "calling" rows (no status callback in 20 min) → treat as failed
    for lead in await db.fetchall(
        """select l.* from leads l where l.status = 'calling' and not exists (
             select 1 from calls c where c.lead_id = l.id and c.started_at > now() - interval '20 minutes')"""):
        await after_unanswered(lead["id"], "failed")

    active = (await db.fetchone(
        "select count(*) n from calls where status in ('queued','ringing','in_progress') and started_at > now() - interval '20 minutes'"))["n"]
    room = max(0, int(s["max_parallel_calls"]) - active)
    if not room:
        return 0
    due = await db.fetchall(
        """update leads set status = 'calling' where id in (
             select id from leads
             where channel = 'voice' and consent_call and phone_country = 'IN'
               and next_call_at is not null and next_call_at <= now()
               and (status in ('queued','qualifying','nurture') or (status = 'qualified' and stage = 'none'))
               and call_attempts < %s
             order by (status = 'queued') desc, next_call_at
             limit %s for update skip locked)
           returning *""",
        [s["max_call_attempts"], room],
    )
    for lead in due:
        await place_call(lead)
    return len(due)


async def run_forever() -> None:
    while True:
        try:
            if cfg.dialer_enabled:
                await dial_once()
        except Exception:  # noqa: BLE001
            logger.exception("dialer loop error")
        await asyncio.sleep(20)
