"""HTTP + WebSocket entry point. Run: uvicorn papillon.main:app --host 0.0.0.0 --port 8090"""

from __future__ import annotations

import asyncio
import csv
import io
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from loguru import logger

from . import db, dialer, reports, sources, whatsapp
from .config import cfg
from .intake import ingest

_bg: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(_app):
    await db.open_pool()
    _bg.append(asyncio.create_task(dialer.run_forever()))
    _bg.append(asyncio.create_task(reports.run_forever()))
    yield
    for t in _bg:
        t.cancel()
    await db.close_pool()


app = FastAPI(title="Papillon lead pipeline", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=cfg.allowed_origins or ["*"], allow_methods=["*"], allow_headers=["*"])


def admin(authorization: str = Header(default="")):
    if not cfg.admin_token or authorization != f"Bearer {cfg.admin_token}":
        raise HTTPException(401, "unauthorised")


@app.get("/health")
async def health():
    await db.fetchone("select 1")
    return {"ok": True}


# ── Website enquiry form ─────────────────────────────────────────
_hits: dict[str, list[float]] = {}


@app.post("/intake/web")
async def intake_web(request: Request):
    body = await request.json()
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0].strip()
    if body.get("company_website"):          # honeypot field, hidden from humans
        return {"ok": True}
    window = [t for t in _hits.get(ip, []) if t > time.time() - 600]
    if len(window) >= 5:
        raise HTTPException(429, "too many enquiries")
    _hits[ip] = window + [time.time()]
    if not body.get("consent"):
        raise HTTPException(400, "consent required")
    try:
        lead, created = await ingest(sources.from_web(body, ip), actor="website")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "ref": lead["ref"], "new": created}


# ── Meta (Facebook / Instagram) Lead Ads ─────────────────────────
@app.get("/webhooks/meta")
async def meta_verify(request: Request):
    q = request.query_params
    if q.get("hub.verify_token") == cfg.meta_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhooks/meta")
async def meta_webhook(request: Request):
    raw = await request.body()
    if not sources.verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403)
    body = await request.json()
    for entry in body.get("entry", []):
        for ch in entry.get("changes", []):
            if ch.get("field") != "leadgen":
                continue
            lid = ch["value"]["leadgen_id"]
            try:
                await ingest(sources.from_meta(await sources.fetch_meta_lead(lid)), actor="meta")
            except Exception:  # noqa: BLE001
                logger.exception("Meta lead {} failed", lid)
    return {"ok": True}


# ── Google Ads lead form extension ───────────────────────────────
@app.post("/webhooks/google")
async def google_webhook(request: Request):
    body = await request.json()
    if not cfg.google_lead_key or body.get("google_key") != cfg.google_lead_key:
        raise HTTPException(403)
    if body.get("is_test"):
        return {}
    try:
        await ingest(sources.from_google(body), actor="google")
    except ValueError as e:
        logger.warning("Google lead rejected: {}", e)
    return {}


# ── Calls ────────────────────────────────────────────────────────
@app.post("/webhooks/exotel/status")
async def exotel_status(request: Request):
    ctype = request.headers.get("content-type", "")
    payload = await request.json() if "json" in ctype else dict(await request.form())
    await dialer.handle_status(payload)
    return {"ok": True}


@app.websocket("/voice/exotel")
async def voice(websocket: WebSocket):
    from .voice_bot import run_call  # heavy imports only when a call comes in
    await run_call(websocket)


# ── WhatsApp ─────────────────────────────────────────────────────
@app.get("/webhooks/whatsapp")
async def wa_verify(request: Request):
    q = request.query_params
    if q.get("hub.verify_token") == cfg.wa_verify_token:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403)


@app.post("/webhooks/whatsapp")
async def wa_webhook(request: Request):
    raw = await request.body()
    if not whatsapp.verify_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403)
    asyncio.create_task(whatsapp.handle_webhook(await request.json()))
    return {"ok": True}


# ── Admin (you) ──────────────────────────────────────────────────
@app.post("/admin/leads", dependencies=[Depends(admin)])
async def add_lead(request: Request):
    body = await request.json()
    lead, created = await ingest({**body, "source": body.get("source") or "manual"}, actor="admin")
    return {"ref": lead["ref"], "id": str(lead["id"]), "new": created}


@app.post("/admin/import", dependencies=[Depends(admin)])
async def import_csv(file: UploadFile = File(...), source: str = "import"):
    """CSV columns: name, phone, email, consent (yes/no), and any of city, locality, project, configuration,
    budget, possession, timeline, scope. Rows without consent are stored but never auto-called."""
    text = (await file.read()).decode("utf-8-sig")
    added = merged = bad = 0
    for row in csv.DictReader(io.StringIO(text)):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            _, created = await ingest({
                "name": row.get("name"), "phone": row.get("phone"), "email": row.get("email"), "source": source,
                "form_answers": {k: v for k, v in row.items() if k not in ("name", "phone", "email", "consent") and v},
                "consent_call": row.get("consent", "").lower() in ("yes", "y", "true", "1"),
                "consent_text": f"CSV import ({source}) — consent column",
            }, actor="import")
            added += created
            merged += not created
        except ValueError:
            bad += 1
    return {"added": added, "merged": merged, "invalid": bad}


@app.post("/admin/leads/{lead_id}/call-now", dependencies=[Depends(admin)])
async def call_now(lead_id: str):
    lead = await db.update_lead(lead_id, status="queued", next_call_at=datetime.now(timezone.utc))
    return {"queued": lead["ref"]}


@app.post("/admin/leads/{lead_id}/rescore", dependencies=[Depends(admin)])
async def rescore(lead_id: str):
    from .qualifier import score_and_route
    lead = await score_and_route(await db.get_lead(lead_id), await db.get_settings(), channel="manual")
    return {"status": lead["status"], "temperature": lead["temperature"], "score": lead["score"]}


@app.post("/admin/leads/{lead_id}/erase", dependencies=[Depends(admin)])
async def erase(lead_id: str):
    """Data-deletion request (DPDP Act): removes the person's data, keeps an anonymous count."""
    await db.execute(
        """update leads set name = null, email = null, phone = 'erased-' || id::text, form_answers = '{}', utm = '{}',
                  notes = null, ai_summary = null, status = 'do_not_contact', next_call_at = null where id = %s""", [lead_id])
    await db.execute("update calls set transcript = '[]', recording_url = null, summary = null where lead_id = %s", [lead_id])
    await db.execute("delete from messages where lead_id = %s", [lead_id])
    await db.log_event(lead_id, "erased", {}, "admin")
    return {"erased": True}


@app.post("/admin/reports/{kind}", dependencies=[Depends(admin)])
async def report_now(kind: str, start: date):
    if kind not in ("daily", "weekly"):
        raise HTTPException(400)
    return await reports.run_and_send(kind, start)
