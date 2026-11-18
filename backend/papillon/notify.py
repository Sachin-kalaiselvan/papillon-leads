"""Outgoing WhatsApp (Meta Cloud API) and email (SMTP)."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

import httpx
from loguru import logger

from . import db
from .config import cfg


async def wa_send(payload: dict, lead_id=None, body_for_log: str | None = None) -> str | None:
    if not (cfg.wa_token and cfg.wa_phone_number_id):
        logger.warning("WhatsApp not configured; skipped message to {}", payload.get("to"))
        return None
    url = f"https://graph.facebook.com/{cfg.graph_version}/{cfg.wa_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.post(url, json={"messaging_product": "whatsapp", **payload},
                            headers={"Authorization": f"Bearer {cfg.wa_token}"})
    ok = r.status_code < 300
    msg_id = r.json().get("messages", [{}])[0].get("id") if ok else None
    if not ok:
        logger.error("WhatsApp send failed {}: {}", r.status_code, r.text[:300])
    await db.execute(
        "insert into messages (lead_id, channel, direction, recipient, body, provider_id, status) values (%s,'whatsapp','out',%s,%s,%s,%s)",
        [lead_id, payload.get("to"), body_for_log or str(payload)[:500], msg_id, "sent" if ok else f"error {r.status_code}"],
    )
    return msg_id


async def wa_text(to: str, text: str, lead_id=None):
    return await wa_send({"to": to.lstrip("+"), "type": "text", "text": {"body": text[:4000]}}, lead_id, text)


async def wa_template(to: str, name: str, params: list[str], lead_id=None, log_text: str | None = None):
    comps = [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:900]} for p in params]}] if params else []
    return await wa_send(
        {"to": to.lstrip("+"), "type": "template",
         "template": {"name": name, "language": {"code": cfg.wa_tpl_lang}, "components": comps}},
        lead_id, log_text or f"[template {name}] " + " | ".join(map(str, params)),
    )


def _send_mail_sync(to: list[str], subject: str, html: str, text: str):
    msg = EmailMessage()
    msg["From"] = cfg.mail_from or cfg.smtp_user
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as s:
        s.starttls()
        if cfg.smtp_user:
            s.login(cfg.smtp_user, cfg.smtp_password)
        s.send_message(msg)


async def email(to: list[str], subject: str, html: str, text: str, lead_id=None) -> bool:
    to = [t for t in to if t]
    if not to:
        return False
    if not cfg.smtp_host:
        logger.warning("SMTP not configured; skipped email '{}'", subject)
        return False
    try:
        await asyncio.to_thread(_send_mail_sync, to, subject, html, text)
        ok = True
    except Exception as e:  # noqa: BLE001
        logger.error("Email failed: {}", e)
        ok = False
    await db.execute(
        "insert into messages (lead_id, channel, direction, recipient, body, status) values (%s,'email','out',%s,%s,%s)",
        [lead_id, ", ".join(to), subject, "sent" if ok else "error"],
    )
    return ok
