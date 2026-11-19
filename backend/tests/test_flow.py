"""End-to-end against a real Postgres (TEST_DATABASE_URL). External APIs are stubbed."""

import asyncio
import os
from datetime import date, datetime, time, timedelta, timezone

import pytest

from papillon import api, auth, db, followup, forward, intake, notify, qualifier, reports, sources

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
SENT = []


async def _fake_wa(to, name, params, lead_id=None, log_text=None):
    SENT.append(("wa", to, name))


async def _fake_email(to, subject, html, text, lead_id=None):
    SENT.append(("email", tuple(to), subject))
    return True


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

        # 2. follow-up opens the WhatsApp conversation
        assert await followup.follow_up_once() == 1
        assert ("wa", "+919845012345", "papillon_enquiry_intro") in SENT
        assert (await db.get_lead(lead["id"]))["status"] == "qualifying"

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

        # 4. Papillon logs in and moves it through their stages
        await db.execute("insert into team_members (email, org, password_hash) values ('sales@papillon.example', 'papillon', %s)",
                         [auth.hash_password("studio-pass-1")])
        tm = await db.fetchone("select * from team_members where email = 'sales@papillon.example'")
        assert auth.check_password("studio-pass-1", tm["password_hash"]) and not auth.check_password("nope", tm["password_hash"])
        user = await auth.current_user(f"Bearer {auth.make_token(str(tm['id']))}")
        assert user["org"] == "papillon"
        await api.update_stage(lead["id"], "consultation_booked", note="Video call booked", actor=user["email"])
        await api.update_stage(lead["id"], "quotation_sent", quote=1950000)
        await api.update_stage(lead["id"], "won")
        won = await db.get_lead(lead["id"])
        assert won["stage"] == "won" and won["won_value"] == 1950000

        # 5. a second lead never replies → reminders, then unreachable
        l2, _ = await intake.ingest({"name": "Ravi", "phone": "+91 99001 23456", "consent_call": True, "source": "google"})
        for _ in range(5):
            await db.execute("update leads set next_call_at = now() - interval '1 minute' where id = %s", [l2["id"]])
            await followup.follow_up_once()
        l2 = await db.get_lead(l2["id"])
        assert l2["status"] == "unreachable"
        assert ("wa", "+919900123456", "papillon_enquiry_reminder") in SENT

        # 6. overseas buyer is handled the same way; tenant disqualified; Chennai flat out of area
        l3, _ = await intake.ingest({"name": "Kiran", "phone": "+1 415 555 0134", "consent_call": True})
        assert l3["channel"] == "whatsapp"
        await followup.follow_up_once()
        assert (await db.get_lead(l3["id"]))["status"] == "qualifying"
        l4, _ = await intake.ingest({"name": "T", "phone": "+91 98860 11111", "consent_call": True})
        await qualifier.apply_details(l4["id"], {"ownership": "tenant"})
        assert (await qualifier.finalize(l4["id"], "completed"))["status"] == "disqualified"
        l5, _ = await intake.ingest({"name": "C", "phone": "+91 98860 22222", "consent_call": True})
        await qualifier.apply_details(l5["id"], {"city": "Chennai", "locality": "OMR"})
        assert (await qualifier.finalize(l5["id"], "completed"))["status"] == "out_of_area"

        # 7. lead without consent is stored but never messaged
        l6, _ = await intake.ingest({"name": "No consent", "phone": "+91 98860 33333", "consent_call": False})
        await db.execute("update leads set next_call_at = now() where id = %s", [l6["id"]])
        await followup.follow_up_once()
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
        snap = await api.snapshot(user)
        assert len(snap["leads"]) == 1 and snap["leads"][0]["ref"] == lead["ref"]
        await db.close_pool()

    run(go())


def test_whatsapp_conversation(monkeypatch):
    """A lead replies on WhatsApp; the assistant saves answers and qualifies them."""
    from papillon import whatsapp
    replies = []

    async def fake_text(to, text, lead_id=None):
        replies.append(text)

    turns = iter([
        {"content": None, "tool_calls": [{"id": "1", "function": {"name": "save_details", "arguments":
            '{"city":"Bengaluru","locality":"Whitefield","property_type":"apartment","configuration":"3BHK",'
            '"possession_status":"received","scope":"full_home","budget_min_inr":2000000,"budget_max_inr":2500000,'
            '"timeline":"within_1_month","ownership":"owner","willing_consultation":true}'}}]},
        {"content": "Thank you! Our design team will call you today.", "tool_calls": [{"id": "2", "function": {
            "name": "end_conversation", "arguments": '{"outcome":"completed","summary":"3BHK Whitefield, 20-25L, keys received."}'}}]},
    ])

    async def fake_llm(messages):
        return next(turns)

    async def go():
        await _setup(monkeypatch)
        monkeypatch.setattr(notify, "wa_text", fake_text)
        monkeypatch.setattr(whatsapp, "_llm", fake_llm)
        lead, _ = await intake.ingest({"name": "Asha", "phone": "+91 98451 77777", "consent_call": True})
        await followup.follow_up_once()
        await whatsapp.handle_webhook({"entry": [{"changes": [{"value": {"messages": [
            {"from": "919845177777", "id": "w1", "type": "text", "text": {"body": "Hi, 3BHK in Whitefield"}}]}}]}]})
        done = await db.get_lead(lead["id"])
        assert done["status"] == "qualified" and done["temperature"] == "hot" and done["stage"] == "forwarded"
        assert replies and "design team" in replies[-1]
        await db.close_pool()

    run(go())
