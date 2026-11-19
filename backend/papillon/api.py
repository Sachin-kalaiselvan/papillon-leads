"""Everything the dashboard reads and writes. Replaces Supabase's API.
org = 'agency'   → sees all enquiries, calls, spend and rules
org = 'papillon' → sees only leads forwarded to the studio, can move their stages"""

from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from . import db
from .auth import check_password, current_user, make_token

router = APIRouter(prefix="/api")
_tries: dict[str, list[float]] = {}

STAGES = ("forwarded", "contacted", "consultation_booked", "site_visit", "quotation_sent", "negotiation", "won", "lost")
VISIBLE = "stage <> 'none'"


def agency_only(user: dict = Depends(current_user)) -> dict:
    if user["org"] != "agency":
        raise HTTPException(403, "Not allowed")
    return user


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0]
    recent = [t for t in _tries.get(ip, []) if t > time.time() - 600]
    if len(recent) >= 10:
        raise HTTPException(429, "Too many attempts, try again in 10 minutes")
    user = await db.fetchone("select * from team_members where lower(email) = lower(%s) and active", [body.get("email", "")])
    if not user or not check_password(body.get("password", ""), user["password_hash"]):
        _tries[ip] = recent + [time.time()]
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(str(user["id"])), "email": user["email"], "org": user["org"]}


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return {"email": user["email"], "org": user["org"], "name": user["name"]}


@router.get("/snapshot")
async def snapshot(user: dict = Depends(current_user)):
    papillon = user["org"] == "papillon"
    lw = f"where {VISIBLE}" if papillon else ""
    sub = f"where lead_id in (select id from leads where {VISIBLE})" if papillon else ""
    data = {
        "leads": await db.fetchall(f"select * from leads {lw} order by created_at desc limit 5000"),
        "calls": await db.fetchall(f"select * from calls {sub} order by started_at desc limit 3000"),
        "events": await db.fetchall(f"select * from lead_events {sub} order by at desc limit 400"),
        "campaigns": await db.fetchall("select * from campaigns order by created_at desc"),
        "spend": await db.fetchall("select * from campaign_spend"),
        "projects": await db.fetchall("select * from projects order by possession_from nulls last"),
        "settings": await db.get_settings(),
        "reports": await db.fetchall("select * from reports order by period_start desc limit 120"),
    }
    return jsonable_encoder(data)


@router.get("/leads/{lead_id}/messages")
async def messages(lead_id: str, user: dict = Depends(current_user)):
    extra = f" and lead_id in (select id from leads where {VISIBLE})" if user["org"] == "papillon" else ""
    return jsonable_encoder(await db.fetchall(
        f"select * from messages where lead_id = %s{extra} order by created_at", [lead_id]))


async def update_stage(lead_id: str, stage: str, quote: int | None = None, won: int | None = None,
                       lost_reason: str | None = None, note: str | None = None, actor: str = "dashboard") -> dict:
    if stage not in STAGES:
        raise HTTPException(400, f"bad stage {stage}")
    lead = await db.fetchone(
        f"""update leads set
              stage = %(stage)s, stage_updated_at = now(),
              quote_value = coalesce(%(quote)s, quote_value),
              won_value = case when %(stage)s = 'won' then coalesce(%(won)s, quote_value, won_value) else won_value end,
              lost_reason = case when %(stage)s = 'lost' then coalesce(%(lost)s, lost_reason) else lost_reason end,
              notes = case when coalesce(%(note)s, '') <> ''
                           then concat_ws(E'\\n', notes, to_char(now() at time zone 'Asia/Kolkata', 'DD Mon HH24:MI') || ' — ' || %(note)s)
                           else notes end
            where id = %(id)s and {VISIBLE} returning *""",
        {"stage": stage, "quote": quote, "won": won, "lost": lost_reason, "note": note, "id": lead_id},
    )
    if not lead:
        raise HTTPException(404, "lead not found")
    await db.log_event(lead_id, "stage", {"stage": stage, "quote": quote, "won": won, "lost_reason": lost_reason, "note": note}, actor)
    return lead


@router.post("/leads/{lead_id}/stage")
async def stage(lead_id: str, request: Request, user: dict = Depends(current_user)):
    b = await request.json()
    lead = await update_stage(lead_id, b.get("stage"), b.get("quote"), b.get("won"), b.get("lostReason"), b.get("note"), user["email"])
    return jsonable_encoder(lead)


TEXT_ARRAYS = {"service_areas", "forward_temperatures", "forward_whatsapp", "forward_emails", "report_emails"}
TIMES = {"call_window_start", "call_window_end"}
NUMBERS = {"outstation_min_budget", "min_budget_full_home", "min_budget_kitchen", "min_budget_wardrobes",
           "min_budget_partial", "budget_tolerance", "max_call_attempts", "max_parallel_calls", "nurture_recheck_days"}
BOOLS = {"accept_outstation"}


@router.put("/settings")
async def save_settings(request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    sets, params = [], {}
    for k, v in b.items():
        if k in TEXT_ARRAYS:
            sets.append(f"{k} = array(select jsonb_array_elements_text(%({k})s))")
            params[k] = [str(x) for x in v]
        elif k in TIMES:
            sets.append(f"{k} = %({k})s::time")
            params[k] = str(v)[:5]
        elif k in NUMBERS or k in BOOLS:
            sets.append(f"{k} = %({k})s")
            params[k] = v
    if sets:
        await db.execute(f"update settings set {', '.join(sets)}, updated_at = now() where id = 1", params)
    return jsonable_encoder(await db.get_settings())


@router.post("/campaigns")
async def add_campaign(request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    row = await db.fetchone(
        "insert into campaigns (name, source, audience, status, started_on) values (%s,%s,%s,'active',%s) returning *",
        [b["name"], b.get("source", "other"), b.get("audience"), b.get("started_on") or date.today()])
    return jsonable_encoder(row)


@router.post("/spend")
async def add_spend(request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    await db.execute(
        """insert into campaign_spend (campaign_id, spend_date, amount, clicks) values (%s,%s,%s,%s)
           on conflict (campaign_id, spend_date) do update set amount = excluded.amount, clicks = excluded.clicks""",
        [b["campaign_id"], b["spend_date"], b["amount"], b.get("clicks")])
    return {"ok": True}


@router.post("/projects")
async def add_project(request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    row = await db.fetchone(
        """insert into projects (name, builder, locality, possession_from, possession_to) values (%s,%s,%s,%s,%s)
           on conflict (name, builder) do update set locality = excluded.locality,
             possession_from = excluded.possession_from, possession_to = excluded.possession_to returning *""",
        [b["name"], b.get("builder"), b.get("locality"), b.get("possession_from") or None, b.get("possession_to") or None])
    return jsonable_encoder(row)


@router.delete("/projects/{project_id}")
async def remove_project(project_id: str, user: dict = Depends(agency_only)):
    await db.execute("delete from projects where id = %s", [project_id])
    return {"ok": True}


# ── Prospects (crawler results) — agency only ───────────────────
PROSPECT_STATUSES = ("new", "contacted", "interested", "partner", "added", "not_relevant")


@router.get("/prospects")
async def prospects(user: dict = Depends(agency_only)):
    rows = await db.fetchall(
        """select * from prospects where status <> 'not_relevant' or updated_at > now() - interval '7 days'
           order by score desc, found_at desc limit 3000""")
    state = {r["key"]: r["value"] for r in await db.fetchall("select key, value from crawl_state")}
    return jsonable_encoder({"prospects": rows, "state": state})


@router.post("/prospects/{pid}")
async def update_prospect(pid: str, request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    if b.get("status") and b["status"] not in PROSPECT_STATUSES:
        raise HTTPException(400, "bad status")
    row = await db.fetchone(
        """update prospects set status = coalesce(%s, status), notes = coalesce(%s, notes), updated_at = now()
           where id = %s returning *""", [b.get("status"), b.get("notes"), pid])
    return jsonable_encoder(row)


@router.post("/prospects/{pid}/to-projects")
async def prospect_to_projects(pid: str, request: Request, user: dict = Depends(agency_only)):
    b = await request.json()
    p = await db.fetchone("select * from prospects where id = %s and kind = 'project'", [pid])
    if not p:
        raise HTTPException(404)
    await db.execute(
        """insert into projects (name, builder, locality, possession_from, possession_to) values (%s,%s,%s,%s,%s)
           on conflict (name, builder) do nothing""",
        [p["name"], b.get("builder") or (p["data"] or {}).get("developer") or "", p["locality"],
         b.get("possession_from") or None, b.get("possession_to") or None])
    await db.execute("update prospects set status = 'added', updated_at = now() where id = %s", [pid])
    return {"ok": True}


@router.post("/crawl/{feed}")
async def crawl_now(feed: str, user: dict = Depends(agency_only)):
    from . import crawler
    if feed not in crawler.SCHEDULE:
        raise HTTPException(400)
    return {"new": await crawler.run_feed(feed)}
