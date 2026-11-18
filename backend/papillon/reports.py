"""Daily lead report and weekly campaign report (brief points 11 + 12)."""

from __future__ import annotations

import asyncio
import html
from datetime import date, datetime, time, timedelta

from loguru import logger

from . import db, notify
from .config import IST, cfg
from .forward import budget_text

STAGES = ["forwarded", "contacted", "consultation_booked", "site_visit", "quotation_sent", "negotiation", "won"]


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, time.min, IST), datetime.combine(end + timedelta(days=1), time.min, IST))


async def build_daily(day: date) -> dict:
    a, b = _bounds(day, day)
    p = {"a": a, "b": b}
    new = await db.fetchall("select source, count(*) n from leads where created_at >= %(a)s and created_at < %(b)s group by source", p)
    calls = await db.fetchone(
        """select count(*) attempts,
                  count(*) filter (where answered_at is not null) connected,
                  coalesce(round(avg(duration_sec) filter (where answered_at is not null)), 0) avg_sec
           from calls where started_at >= %(a)s and started_at < %(b)s""", p)
    scored = await db.fetchall(
        """select distinct on (l.id) l.status, l.temperature, l.disqualify_reason
           from lead_events e join leads l on l.id = e.lead_id
           where e.kind = 'scored' and e.at >= %(a)s and e.at < %(b)s""", p)
    forwarded = await db.fetchall(
        """select ref, name, temperature, configuration, property_type, locality, city, scope, budget_min, budget_max,
                  timeline, possession_status, consult_slot_said, source, id
           from leads where forwarded_at >= %(a)s and forwarded_at < %(b)s order by temperature, score desc""", p)
    moves = await db.fetchall(
        """select e.detail->>'stage' stage, count(*) n from lead_events e
           where e.kind = 'stage' and e.at >= %(a)s and e.at < %(b)s group by 1""", p)
    reasons: dict[str, int] = {}
    for r in scored:
        if r["status"] in ("disqualified", "out_of_area"):
            reasons[r["disqualify_reason"] or r["status"]] = reasons.get(r["disqualify_reason"] or r["status"], 0) + 1
    return {
        "day": day.isoformat(),
        "enquiries": sum(r["n"] for r in new),
        "by_source": {r["source"]: r["n"] for r in new},
        "call_attempts": calls["attempts"], "calls_connected": calls["connected"], "avg_call_sec": int(calls["avg_sec"]),
        "hot": sum(1 for r in scored if r["status"] == "qualified" and r["temperature"] == "hot"),
        "warm": sum(1 for r in scored if r["status"] == "qualified" and r["temperature"] == "warm"),
        "cold": sum(1 for r in scored if r["temperature"] == "cold"),
        "disqualified": reasons,
        "forwarded": [{**{k: v for k, v in f.items() if k not in ("budget_min", "budget_max")},
                       "id": str(f["id"]), "budget": budget_text(f)} for f in forwarded],
        "stage_moves": {r["stage"]: r["n"] for r in moves},
    }


async def build_weekly(week_start: date) -> dict:
    end = week_start + timedelta(days=6)
    a, b = _bounds(week_start, end)
    p = {"a": a, "b": b, "da": week_start, "db": end}
    rows = await db.fetchall(
        """with c as (select id, name, source from campaigns
                      union all select null, 'No campaign', 'other'),
           spend as (select campaign_id, sum(amount) amount, sum(clicks) clicks from campaign_spend
                     where spend_date between %(da)s and %(db)s group by 1),
           l as (select * from leads where created_at >= %(a)s and created_at < %(b)s)
           select c.name, c.source, coalesce(s.amount, 0) spend, coalesce(s.clicks, 0) clicks,
                  count(l.id) enquiries,
                  count(l.id) filter (where l.last_contact_at is not null) contacted,
                  count(l.id) filter (where l.status = 'qualified' and l.temperature = 'hot') hot,
                  count(l.id) filter (where l.status = 'qualified' and l.temperature = 'warm') warm,
                  count(l.id) filter (where l.temperature = 'cold') cold,
                  count(l.id) filter (where l.stage <> 'none') forwarded,
                  count(l.id) filter (where l.stage in ('consultation_booked','site_visit','quotation_sent','negotiation','won')) consultations,
                  count(l.id) filter (where l.stage in ('site_visit','quotation_sent','negotiation','won')) site_visits,
                  count(l.id) filter (where l.stage in ('quotation_sent','negotiation','won')) quotations,
                  count(l.id) filter (where l.stage = 'won') won,
                  coalesce(sum(l.won_value) filter (where l.stage = 'won'), 0) won_value
           from c left join l on l.campaign_id is not distinct from c.id
           left join spend s on s.campaign_id = c.id
           group by c.id, c.name, c.source, s.amount, s.clicks
           having count(l.id) > 0 or coalesce(s.amount, 0) > 0
           order by count(l.id) desc""", p)
    camps = []
    for r in rows:
        q = r["hot"] + r["warm"]
        spend = float(r["spend"])
        camps.append({**{k: (float(v) if k in ("spend", "won_value") else v) for k, v in r.items()},
                      "cpl": round(spend / r["enquiries"]) if r["enquiries"] else None,
                      "cpql": round(spend / q) if q else None,
                      "qualified_rate": round(100 * q / r["enquiries"], 1) if r["enquiries"] else 0})
    keys = ["spend", "enquiries", "contacted", "hot", "warm", "cold", "forwarded", "consultations", "site_visits",
            "quotations", "won", "won_value"]
    tot = {k: sum(c[k] for c in camps) for k in keys}
    q = tot["hot"] + tot["warm"]
    tot.update(cpl=round(tot["spend"] / tot["enquiries"]) if tot["enquiries"] else None,
               cpql=round(tot["spend"] / q) if q else None,
               qualified_rate=round(100 * q / tot["enquiries"], 1) if tot["enquiries"] else 0)
    pipeline = await db.fetchall("select stage, count(*) n from leads where stage <> 'none' group by stage")
    return {"week_start": week_start.isoformat(), "week_end": end.isoformat(), "campaigns": camps, "totals": tot,
            "pipeline_now": {r["stage"]: r["n"] for r in pipeline}}


def _inr(v) -> str:
    return "—" if v in (None, "") else f"₹{int(v):,}"


def render_daily(d: dict) -> tuple[str, str, str]:
    subj = f"Papillon daily leads — {d['day']}: {d['enquiries']} enquiries, {d['hot']} hot, {d['warm']} warm"
    rows = "".join(
        f"<tr><td>{html.escape(f['ref'])}</td><td>{html.escape(f['name'] or '')}</td><td><b>{(f['temperature'] or '').upper()}</b></td>"
        f"<td>{html.escape(' '.join(x for x in [f['configuration'], f['locality'] or f['city']] if x))}</td>"
        f"<td>{html.escape(f['budget'])}</td><td>{html.escape((f['timeline'] or '').replace('_', ' '))}</td>"
        f"<td><a href='{cfg.dashboard_url}/leads/{f['id']}'>open</a></td></tr>" for f in d["forwarded"]
    ) or "<tr><td colspan=7>No leads forwarded today.</td></tr>"
    dq = ", ".join(f"{k}: {v}" for k, v in d["disqualified"].items()) or "none"
    src = ", ".join(f"{k} {v}" for k, v in d["by_source"].items()) or "—"
    body = f"""<div style="font-family:Arial;max-width:720px;margin:auto;color:#1f1a24">
<h2 style="font-family:Georgia">Daily lead report · {d['day']}</h2>
<p>Enquiries <b>{d['enquiries']}</b> ({html.escape(src)}) · Calls {d['call_attempts']} placed, {d['calls_connected']} connected (avg {d['avg_call_sec']}s)<br>
Qualified today: <b>{d['hot']} hot</b>, <b>{d['warm']} warm</b>, {d['cold']} cold (nurture) · Not qualified: {html.escape(dq)}</p>
<table cellpadding=6 style="border-collapse:collapse;font-size:13px" border=1 bordercolor="#e5dccf">
<tr style="background:#f6f1ea"><th>Ref</th><th>Name</th><th>Class</th><th>Property</th><th>Budget</th><th>Timeline</th><th></th></tr>{rows}</table>
<p style="font-size:12px;color:#7a6f66">Full detail, call recordings and transcripts: {cfg.dashboard_url}</p></div>"""
    text = f"{subj}\nCalls {d['call_attempts']} / connected {d['calls_connected']}\nNot qualified: {dq}\n" + "\n".join(
        f"{f['ref']} {f['name']} {f['temperature']} {f['budget']}" for f in d["forwarded"])
    return subj, body, text


def render_weekly(w: dict) -> tuple[str, str, str]:
    t = w["totals"]
    subj = (f"Papillon weekly campaign report — {w['week_start']} to {w['week_end']}: "
            f"{t['enquiries']} enquiries, {t['hot'] + t['warm']} qualified, {t['won']} won")
    head = ["Campaign", "Spend", "Enquiries", "CPL", "Hot", "Warm", "Cold", "Cost / qualified", "Consults", "Site visits", "Quotes", "Won"]
    tr = lambda c: "".join(f"<td>{v}</td>" for v in [
        html.escape(c.get("name", "Total")), _inr(c["spend"]), c["enquiries"], _inr(c["cpl"]), c["hot"], c["warm"], c["cold"],
        _inr(c["cpql"]), c["consultations"], c["site_visits"], c["quotations"], c["won"]])
    rows = "".join(f"<tr>{tr(c)}</tr>" for c in w["campaigns"]) + f"<tr style='font-weight:bold;background:#f6f1ea'>{tr({**t, 'name': 'Total'})}</tr>"
    body = f"""<div style="font-family:Arial;max-width:900px;margin:auto;color:#1f1a24">
<h2 style="font-family:Georgia">Weekly campaign report · {w['week_start']} – {w['week_end']}</h2>
<p>Qualified rate <b>{t['qualified_rate']}%</b> · Cost per qualified lead <b>{_inr(t['cpql'])}</b> · Won value {_inr(t['won_value'])}</p>
<table cellpadding=6 style="border-collapse:collapse;font-size:12px" border=1 bordercolor="#e5dccf">
<tr style="background:#1f1a24;color:#f6f1ea">{''.join(f'<th>{h}</th>' for h in head)}</tr>{rows}</table>
<p style="font-size:12px;color:#7a6f66">Leads counted by the week they arrived; stages are where they stand today. {cfg.dashboard_url}/reports</p></div>"""
    return subj, body, subj


async def run_and_send(kind: str, start: date) -> dict:
    s = await db.get_settings()
    if kind == "daily":
        data, end = await build_daily(start), start
        subj, body, text = render_daily(data)
    else:
        data, end = await build_weekly(start), start + timedelta(days=6)
        subj, body, text = render_weekly(data)
    to = list(dict.fromkeys((s.get("report_emails") or []) + (s.get("forward_emails") or [])))
    await notify.email(to, subj, body, text)
    await db.execute(
        """insert into reports (kind, period_start, period_end, data, sent_to) values (%s,%s,%s,%s, array(select jsonb_array_elements_text(%s)))
           on conflict (kind, period_start) do update set data = excluded.data, sent_to = excluded.sent_to, created_at = now()""",
        [kind, start, end, data, to],
    )
    return data


async def run_forever() -> None:
    """Daily at 20:00 IST; weekly every Monday 09:00 IST for the previous Mon–Sun."""
    while True:
        try:
            now = datetime.now(IST)
            today = now.date()
            if now.time() >= time(20, 0) and not await db.fetchone(
                    "select 1 from reports where kind='daily' and period_start=%s", [today]):
                await run_and_send("daily", today)
            last_monday = today - timedelta(days=today.weekday() + 7)
            if (today.weekday() > 0 or now.time() >= time(9, 0)) and not await db.fetchone(
                    "select 1 from reports where kind='weekly' and period_start=%s", [last_monday]):
                await run_and_send("weekly", last_monday)
        except Exception:  # noqa: BLE001
            logger.exception("report loop error")
        await asyncio.sleep(60)
