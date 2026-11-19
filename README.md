# Papillon Interiors — lead pipeline

Ads and forms bring in enquiries → each one gets an automatic call within minutes → the call collects the requirement → the system classifies it Hot / Warm / Cold → only qualified leads go to Papillon's team (WhatsApp + email) → the team moves them through consultation, site visit, quotation and won/lost on the dashboard → daily and weekly reports go out automatically.

```
papillon-leads/
├── database/schema.sql          PostgreSQL tables (runs on your VPS — no Supabase)
├── backend/                     runs on the VPS (Python)
│   ├── papillon/
│   │   ├── main.py              web endpoints (forms, Meta, Google, Exotel, WhatsApp, admin)
│   │   ├── api.py, auth.py      dashboard API + logins
│   │   ├── users.py             add / remove dashboard logins
│   │   ├── intake.py            every enquiry enters here: clean, dedupe, queue the call
│   │   ├── dialer.py            places calls, retries, call window, missed-call WhatsApp
│   │   ├── voice_bot.py         the phone conversation (Exotel → Deepgram → GPT → Sarvam voice)
│   │   ├── whatsapp.py          same questions over WhatsApp (NRI numbers, missed calls, gaps)
│   │   ├── qualifier.py         the script, what gets saved, what happens after a conversation
│   │   ├── scoring.py           Papillon's rules → Hot / Warm / Cold / not a fit
│   │   ├── forward.py           sends qualified leads to Papillon only
│   │   ├── reports.py           daily 8 pm + Monday 9 am reports
│   │   ├── sources.py, parsing.py, notify.py, db.py, config.py
│   ├── tests/                   rules + full end-to-end journey
│   ├── deploy/                  systemd service + nginx config
│   ├── requirements.txt, .env.example
├── dashboard/                   React app for you and Papillon (Vercel)
└── website/EnquiryForm.tsx      form for Papillon's own site
```

## How the brief maps to the build

| Brief | Where it's handled |
|---|---|
| 1–2 Homeowners, new purchases / handovers first | Ad audiences below; **Rules → Projects in handover** gives those leads priority |
| 3 Full home & turnkey first, then kitchen / wardrobes / partial | Score weights in `scoring.py`; each scope has its own minimum budget |
| 4 ₹15 L+ full-home budget | `min_budget_full_home` = ₹15 L; "reasonably aligned" = within 85% (editable) |
| 5 Location, configuration, area, possession, budget, timeline | Asked on the call / WhatsApp, saved field by field |
| 6 Owner or authorised decision-maker | Asked politely on every call; tenants and brokers are held back |
| 7 Contact and pre-qualify every prospect | Call within ~1 minute (inside 10:00–19:30 IST), 4 attempts, WhatsApp after the first miss |
| 8 Hot / Warm / Cold | Hot: starts within a month + possession received/≤3 months + full budget. Warm: starts within 3 months. Cold: 3–6 months out, budget short, or not ready to meet — kept and re-called after 30 days |
| 9 Forward only verified, relevant leads | Only Hot + Warm are forwarded (editable). Papillon's logins can't see anything else |
| 10 Exclusive to Papillon | Ads run under Papillon's brand, leads live in one database, forwarding goes only to Papillon's numbers/emails, every forward is logged with "exclusive_to" |
| 11 Daily + weekly reports | Emailed automatically and on the **Reports** page |
| 12 Consultations, site visits, quotations, conversions | Pipeline board + stage function; weekly report shows each by campaign with cost per qualified lead |

"Don't limit to Karnataka" is handled this way: **the buyer can be anywhere** — Dubai, the US, Pune, Hyderabad. Overseas numbers are qualified on WhatsApp first (no international calling cost). What's checked is where the **property** is. It defaults to Bengaluru areas; if Papillon takes outstation projects, switch on **Rules → Accept projects outside these areas** (with its own minimum budget, default ₹25 L) or add the cities to the service-area list.

---

## Setup

### 1. Database (PostgreSQL on the VPS — free)
```bash
sudo apt update && sudo apt install -y postgresql
sudo -u postgres psql -c "create user papillon with password 'CHOOSE-A-PASSWORD';"
sudo -u postgres psql -c "create database papillon owner papillon;"
sudo -u postgres psql -d papillon -c "create extension if not exists pgcrypto;"
```
`DATABASE_URL=postgresql://papillon:CHOOSE-A-PASSWORD@localhost:5432/papillon`
The tables are created in step 2 after the code is on the server.

### 2. Backend on the VPS
```bash
cd /home/sachin && git clone https://github.com/Sachin-kalaiselvan/papillon-leads.git
cd /home/sachin/papillon-leads/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env            # fill in keys
psql "postgresql://papillon:CHOOSE-A-PASSWORD@localhost:5432/papillon" -f ../database/schema.sql
.venv/bin/python -m papillon.users add sachin@theingredientlist.co "Sachin" agency
.venv/bin/python -m papillon.users add <papillon email> "Papillon Sales" papillon
sudo cp deploy/papillon-leads.service /etc/systemd/system/
sudo systemctl enable --now papillon-leads
sudo cp deploy/nginx-leads.conf /etc/nginx/sites-available/leads
sudo ln -s /etc/nginx/sites-available/leads /etc/nginx/sites-enabled/
sudo certbot --nginx -d leadsapi.papilloninteriors.in && sudo systemctl reload nginx
curl https://leadsapi.papilloninteriors.in/health      # → {"ok":true}
```
GoDaddy (papilloninteriors.in → DNS): add an A record `leadsapi` → the VPS IP. The dashboard goes on `leads.papilloninteriors.in` (step 6).

### 3. Calling (Exotel)
1. Exotel account with KYC, buy a Bengaluru ExoPhone (080…).
2. Ask Exotel support to enable **Connect Voice AI (AgentStream / Voicebot)** on the account.
3. Put API key, token, SID and the ExoPhone in `.env`. Nothing to set up in their flow builder — the backend gives Exotel the stream address per call.
4. Keys for speech: Deepgram (listening), Sarvam (Indian English voice, `priya`), OpenAI (conversation).

### 4. WhatsApp (Meta Cloud API)
Use a number branded Papillon Interiors. Create three templates (Utility category), then put their names in `.env`:

- `papillon_enquiry_intro` — *Hi {{1}}, this is Papillon Interiors about your home interiors enquiry. Could you reply here so we can understand your requirement? Reply STOP to opt out.*
- `papillon_missed_call` — *Hi {{1}}, we just tried calling you from Papillon Interiors about your interiors enquiry. Reply here to continue on WhatsApp, or tell us a good time to call.*
- `papillon_new_lead` (to the studio) — *New {{1}} lead {{2}}: {{3}}. {{4}} Open: {{5}}*

Webhook URL: `https://leadsapi.papilloninteriors.in/webhooks/whatsapp`, verify token = `WA_VERIFY_TOKEN`, subscribe to `messages`.

### 5. Lead sources
- **Meta Lead Ads** — form type *Higher intent*. Questions: full name, phone, email, plus custom questions *Project / society name*, *Locality*, *BHK*, *Possession status*, *Interior budget* (multiple choice: under 10 L / 10–15 L / 15–25 L / 25–40 L / 40 L+), *What do you need?*. Custom disclaimer: *"Papillon Interiors may call me (including an automated assistant) and WhatsApp me about my enquiry."* Webhook: `…/webhooks/meta` (field `leadgen`), page token in `.env`.
- **Google Ads lead form** — Webhook URL `…/webhooks/google`, key = `GOOGLE_LEAD_KEY`.
- **Website** — `website/EnquiryForm.tsx` → in the Papillon site repo put it at `src/components/EnquiryForm.tsx`, render `<EnquiryForm />` on the contact/consultation section, add `VITE_LEADS_API=https://leadsapi.papilloninteriors.in` in that project's Vercel env vars, and add the site URL to `ALLOWED_ORIGINS`.
- **CSV** (builder handover lists, referrals) — `POST /admin/import` with the admin token. Rows need a `consent` column = yes, otherwise they're stored but never auto-called.

### 6. Dashboard (Vercel)
Vercel → Add New → Project → papillon-leads → **Root Directory: `dashboard`** (click "Import single project" next to dashboard — the backend is not deployed on Vercel) → env var `VITE_API_URL=https://leadsapi.papilloninteriors.in` → deploy. Without that variable it runs in demo mode with sample data. Then Vercel project → Settings → Domains → add `leads.papilloninteriors.in` and put the CNAME it shows into GoDaddy DNS (name `leads`).

### 7. Nightly database backup
```bash
mkdir -p /home/sachin/backups
(crontab -l; echo '30 2 * * * pg_dump "postgresql://papillon:CHOOSE-A-PASSWORD@localhost:5432/papillon" | gzip > /home/sachin/backups/papillon-$(date +\%a).sql.gz') | crontab -
```
Keeps the last 7 days (one file per weekday).

---

## Where to find the right homeowners (beyond Karnataka)

| Audience | Channel | Targeting |
|---|---|---|
| Buyers in projects being handed over | Meta | Pin-radius (1–2 km) around each project in **Rules → Projects in handover**; age 28–55; interests home buying / interior design |
| NRIs who bought in Bengaluru | Meta | UAE, Qatar, Saudi, Oman, Kuwait, Singapore, US, UK, Australia; language English/Kannada/Tamil/Telugu/Malayalam; creatives that say "Video consultation · we manage the site while you're abroad" |
| People moving to Bengaluru | Meta | Hyderabad, Chennai, Pune, Mumbai, NCR + "recently moved"/"relocating" behaviours; creatives naming Bengaluru localities |
| High-intent search | Google | "home interiors bangalore", "3bhk interior cost bangalore", "villa interior designers bangalore", "<project name> interiors" — location: people *searching for* Bengaluru, anywhere in the world (Presence or interest) |

Ad copy should name Papillon and say a designer will call — never "get 3 free quotes", which brings shared, low-intent leads and breaks exclusivity.

## Day-to-day
- **You:** watch *Overview* and *Calls*, log ad spend in *Campaigns* (needed for cost per qualified lead), tune *Rules*.
- **Papillon:** open forwarded leads (WhatsApp/email link), read the call summary and transcript, call the customer, drag the card along the *Pipeline*. Quotation and Won ask for the value; Lost asks why.
- Admin actions (with `Authorization: Bearer <ADMIN_TOKEN>`): `POST /admin/leads/{id}/call-now`, `/rescore`, `/erase` (data-deletion request), `/admin/reports/daily?start=2026-11-18`.

## Tests
```bash
cd backend
pytest tests/test_rules.py                                   # rules only
TEST_DATABASE_URL=postgresql://… pytest tests/   # scratch DB with database/schema.sql loaded               # + full journey on a scratch database
```
