"""End-to-end against a real Postgres (TEST_DATABASE_URL). External APIs are stubbed."""

import asyncio
import os
from datetime import date, datetime, time, timedelta, timezone

import pytest

from papillon import db, dialer, forward, intake, notify, qualifier, reports, sources

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
SENT = []


async def _fake_wa(to, name, params, lead_id=None, log_text=None):
    SENT.append(("wa", to, name))


async def _fake_email(to, subject, html, text, lead_id=None):
    SENT.append(("email", tuple(to), subject))
    return True


async def _fake_exotel(phone, lead_id, call_id):
    return f"EXO-{call_id[:8]}"


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


async def _setup(monkeypatch):
    await db.open_pool(URL)
    await db.execute("truncate leads, calls, messages, lead_events, reports, campaigns, campaign_spend, projects, team_members cascade")
    await db.execute("""update settings set call_window_start='00:00', call_window_end='23:59',
                        forward_whatsapp='{+919900000001}', forward_emails='{sales@papillon.example}',
                        report_emails='{sachin@theingredientlist.co}'""")
    await db.execute("insert into projects (name, builder, locality, possession_from, possession_to) values "
                     "('Prestige Lakeside Habitat','Prestige','Varthur', current_date - 60, current_date + 30)")
    monkeypatch.setattr(notify, "wa_template", _fake_wa)
    monkeypatch.setattr(notify, "email", _fake_email)
    monkeypatch.setattr(dialer, "exotel_call", _fake_exotel)
    SENT.clear()


def test_full_journey(monkeypatch):
    async def go():
        await _setup(monkeypatch)
        # 1. website enquiry from an NRI with an Indian mobile
        web = sources.from_web({"name": "Ananya Rao", "phone": "98450 12345", "city": "Bengaluru",
                                "project": "Prestige Lakeside Habitat", "configuration": "3 BHK", "budget": "20-25 lakhs",
                                "consent": True, "consent_text": "I agree to be called", "utm": {"utm_campaign": "nri-gulf"}}, "1.2.3.4")
        lead, created = await intake.ingest(web)
        assert created and lead["status"] == "queued" and lead["budget_min"] == 2000000 and lead["project_id"]
        # duplicate enquiry merges, doesn't create a second lead
        again, created2 = await intake.ingest({**web, "source": "meta"})
        assert not created2 and again["id"] == lead["id"] and again["enquiry_count"] == 2

        # 2. dialer picks it up
        assert await dialer.dial_once() == 1
        call = await db.fetchone("select * from calls where lead_id = %s", [lead["id"]])
        assert call["provider_call_id"].startswith("EXO-")
        assert (await db.get_lead(lead["id"]))["status"] == "calling"

        # 3. the conversation (what the voice bot's tools do)
        await qualifier.apply_details(lead["id"], {
            "locality": "Varthur", "property_type": "apartment", "area_sqft": 1720, "possession_status": "received",
            "scope": "full_home", "timeline": "within_1_month", "ownership": "owner", "lives_in": "Dubai",
            "willing_consultation": True, "consult_mode": "video", "consult_slot_said": "Saturday 11 am",
            "budget_said": "around 22 lakhs", "consult_slot_iso": "2026-11-21T11:00:00+05:30"})
        done = await qualifier.finalize(lead["id"], "completed", "NRI in Dubai, 3BHK Prestige Lakeside, possession received.")
        assert done["status"] == "qualified" and done["temperature"] == "hot" and done["stage"] == "forwarded"
        assert ("wa", "+919900000001", "papillon_new_lead") in SENT
        assert any(x[0] == "email" and "[HOT]" in x[2] for x in SENT)

        # 4. Papillon moves it through their stages (dashboard RPC, run as superuser here)
        tm = "00000000-0000-0000-0000-000000000001"
        await db.execute("insert into team_members (user_id, email, org) values (%s, 'sales@papillon.example', 'papillon')", [tm])
        async with db.pool.connection() as conn:
            await conn.execute(f"set request.uid = '{tm}'")
            await conn.execute("select update_lead_stage(%s, 'consultation_booked', null, null, null, 'Video call booked')", [lead["id"]])
            await conn.execute("select update_lead_stage(%s, 'quotation_sent', 1950000)", [lead["id"]])
            await conn.execute("select update_lead_stage(%s, 'won')", [lead["id"]])
            await conn.execute("reset request.uid")
        won = await db.get_lead(lead["id"])
        assert won["stage"] == "won" and won["won_value"] == 1950000

        # 5. a second lead never answers → retries, WhatsApp after first miss, then unreachable
        l2, _ = await intake.ingest({"name": "Ravi", "phone": "+91 99001 23456", "consent_call": True, "source": "google"})
        for i in range(4):
            await db.execute("update leads set next_call_at = now() - interval '1 minute' where id = %s", [l2["id"]])
            await dialer.dial_once()
            c = await db.fetchone("select * from calls where lead_id = %s order by started_at desc limit 1", [l2["id"]])
            await dialer.handle_status({"CallSid": c["provider_call_id"], "Status": "no-answer", "CustomField": str(c["id"])})
        l2 = await db.get_lead(l2["id"])
        assert l2["status"] == "unreachable" and l2["call_attempts"] == 4
        assert ("wa", "+919900123456", "papillon_missed_call") in SENT

        # 6. overseas number goes WhatsApp-first; tenant gets disqualified; Chennai flat is out of area
        l3, _ = await intake.ingest({"name": "Kiran", "phone": "+1 415 555 0134", "consent_call": True})
        assert l3["channel"] == "whatsapp"
        await dialer.dial_once()
        assert (await db.get_lead(l3["id"]))["status"] == "qualifying"
        l4, _ = await intake.ingest({"name": "T", "phone": "+91 98860 11111", "consent_call": True})
        await qualifier.apply_details(l4["id"], {"ownership": "tenant"})
        assert (await qualifier.finalize(l4["id"], "completed"))["status"] == "disqualified"
        l5, _ = await intake.ingest({"name": "C", "phone": "+91 98860 22222", "consent_call": True})
        await qualifier.apply_details(l5["id"], {"city": "Chennai", "locality": "OMR"})
        assert (await qualifier.finalize(l5["id"], "completed"))["status"] == "out_of_area"

        # 7. lead without consent is stored but never called
        l6, _ = await intake.ingest({"name": "No consent", "phone": "+91 98860 33333", "consent_call": False})
        await db.execute("update leads set next_call_at = now() where id = %s", [l6["id"]])
        await dialer.dial_once()
        assert (await db.get_lead(l6["id"]))["status"] == "new"

        # 8. reports
        camp = await db.fetchone("select id from campaigns where external_id = 'web:nri-gulf'")
        today = datetime.now(timezone.utc).astimezone(intake.IST).date()
        await db.execute("insert into campaign_spend (campaign_id, spend_date, amount) values (%s, %s, 4200)", [camp["id"], today])
        d = await reports.run_and_send("daily", today)
        assert d["enquiries"] == 6 and d["hot"] == 1 and len(d["forwarded"]) == 1
        monday = today - timedelta(days=today.weekday())
        w = await reports.run_and_send("weekly", monday)
        nri = next(c for c in w["campaigns"] if c["name"] == "nri-gulf")
        assert nri["spend"] == 4200 and nri["hot"] == 1 and nri["won"] == 1 and nri["cpql"] == 4200
        subj, body, _ = reports.render_weekly(w)
        assert "Cost / qualified" in body
        await db.close_pool()

    run(go())
