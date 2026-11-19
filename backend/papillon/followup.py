"""Starts the WhatsApp conversation for every new enquiry and nudges people who go quiet.
Messages only go out inside the contact window in Rules (default 10:00–19:30 IST)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger

from . import db, whatsapp
from .config import cfg
from .intake import in_window, next_call_time

NUDGE_AFTER_HOURS = 24


async def follow_up_once() -> int:
    s = await db.get_settings()
    now = datetime.now(timezone.utc)
    if not in_window(now, s):
        return 0
    due = await db.fetchall(
        """update leads set call_attempts = call_attempts + 1 where id in (
             select id from leads
             where consent_call and next_call_at is not null and next_call_at <= now()
               and (status in ('queued','qualifying','nurture') or (status = 'qualified' and stage = 'none'))
             order by (status = 'queued') desc, next_call_at
             limit 20 for update skip locked)
           returning *""")
    for lead in due:
        try:
            if lead["call_attempts"] > s["max_call_attempts"]:
                await db.update_lead(lead["id"], status="unreachable", next_call_at=None)
                await db.log_event(lead["id"], "unreachable", {"messages": lead["call_attempts"] - 1})
                continue
            if lead["status"] == "queued" or lead["call_attempts"] == 1:
                await whatsapp.send_intro(lead)
            else:
                await whatsapp.send_reminder(lead)
            await db.update_lead(lead["id"], status="qualifying",
                                 next_call_at=next_call_time(now + timedelta(hours=NUDGE_AFTER_HOURS), s))
        except Exception:  # noqa: BLE001
            logger.exception("follow-up failed for {}", lead["ref"])
    return len(due)


async def run_forever() -> None:
    while True:
        try:
            if cfg.dialer_enabled:
                await follow_up_once()
        except Exception:  # noqa: BLE001
            logger.exception("follow-up loop error")
        await asyncio.sleep(30)
