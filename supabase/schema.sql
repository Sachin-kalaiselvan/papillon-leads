-- Papillon Interiors — lead pipeline schema
-- Run once in Supabase: Dashboard → SQL Editor → paste → Run.
-- Safe to re-run: every object is created with IF NOT EXISTS / OR REPLACE.

create extension if not exists pgcrypto;

-- ─────────────────────────────────────────────────────────────
-- Settings (single row). Everything Papillon's brief makes a rule lives here,
-- so thresholds can change from the dashboard without a redeploy.
-- ─────────────────────────────────────────────────────────────
create table if not exists settings (
  id                     int primary key default 1 check (id = 1),
  -- where Papillon executes projects (property location, not where the buyer lives)
  service_areas          text[] not null default array[
    'bengaluru','bangalore','whitefield','sarjapur','electronic city','hebbal','yelahanka',
    'devanahalli','hoskote','kanakapura road','bannerghatta road','hennur','thanisandra',
    'jp nagar','jayanagar','koramangala','hsr layout','bellandur','marathahalli','kr puram',
    'rajajinagar','malleshwaram','indiranagar','old madras road','mysore road','tumkur road',
    'nelamangala','doddaballapura','bidadi','anekal','attibele','chandapura','begur','varthur'],
  accept_outstation      boolean not null default false,   -- projects outside service_areas
  outstation_min_budget  bigint  not null default 2500000,
  -- minimum indicative budget (₹) per scope — full home is ₹15 lakh per the brief
  min_budget_full_home   bigint  not null default 1500000,
  min_budget_kitchen     bigint  not null default 300000,
  min_budget_wardrobes   bigint  not null default 200000,
  min_budget_partial     bigint  not null default 500000,
  budget_tolerance       numeric not null default 0.85,    -- "reasonably aligned": within 85% of the minimum
  forward_temperatures   text[]  not null default array['hot','warm'],
  -- calling rules (IST)
  call_window_start      time    not null default '10:00',
  call_window_end        time    not null default '19:30',
  call_days              int[]   not null default array[1,2,3,4,5,6,7],  -- ISO weekday, 1 = Monday
  max_call_attempts      int     not null default 4,
  retry_minutes          int[]   not null default array[10, 120, 1440, 2880],
  max_parallel_calls     int     not null default 3,
  nurture_recheck_days   int     not null default 30,
  -- where qualified leads and reports go
  forward_whatsapp       text[]  not null default '{}',
  forward_emails         text[]  not null default '{}',
  report_emails          text[]  not null default '{}',
  updated_at             timestamptz not null default now()
);
insert into settings (id) values (1) on conflict do nothing;

-- ─────────────────────────────────────────────────────────────
-- Campaigns and spend (for weekly cost-per-qualified-lead)
-- ─────────────────────────────────────────────────────────────
create table if not exists campaigns (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  source       text not null check (source in ('meta','google','website','portal','referral','partner','import','manual','other')),
  external_id  text unique,            -- Meta campaign_id / Google campaign_id / utm_campaign
  audience     text,                   -- e.g. "NRI Gulf — Bengaluru handover projects"
  status       text not null default 'active' check (status in ('active','paused','ended')),
  started_on   date,
  notes        text,
  created_at   timestamptz not null default now()
);

create table if not exists campaign_spend (
  id           uuid primary key default gen_random_uuid(),
  campaign_id  uuid not null references campaigns(id) on delete cascade,
  spend_date   date not null,
  amount       numeric(12,2) not null default 0,
  impressions  int,
  clicks       int,
  unique (campaign_id, spend_date)
);

-- Projects in or near handover — leads from these get priority (brief point 2)
create table if not exists projects (
  id              uuid primary key default gen_random_uuid(),
  name            text not null,
  builder         text,
  locality        text,
  city            text not null default 'Bengaluru',
  possession_from date,
  possession_to   date,
  notes           text,
  created_at      timestamptz not null default now(),
  unique (name, builder)
);

-- ─────────────────────────────────────────────────────────────
-- Leads
-- ─────────────────────────────────────────────────────────────
create sequence if not exists lead_ref_seq start 1001;

create table if not exists leads (
  id                 uuid primary key default gen_random_uuid(),
  ref                text unique not null default ('PAP-' || nextval('lead_ref_seq')),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),

  -- contact
  name               text,
  phone              text not null unique,          -- E.164
  phone_country      text,                          -- ISO code from the number (IN, AE, US…)
  email              text,
  lives_in           text,                          -- where the buyer lives (can be anywhere)

  -- origin
  source             text not null default 'website',
  campaign_id        uuid references campaigns(id) on delete set null,
  external_lead_id   text,
  utm                jsonb not null default '{}',
  form_answers       jsonb not null default '{}',
  enquiry_count      int not null default 1,

  -- consent (needed before any automated call)
  consent_call       boolean not null default false,
  consent_text       text,
  consent_at         timestamptz,
  consent_ip         text,

  -- qualification (brief point 5 + 6)
  property_type      text check (property_type in ('apartment','villa','independent_house','row_house','penthouse','plot','commercial','other')),
  project_name       text,
  project_id         uuid references projects(id) on delete set null,
  locality           text,
  city               text,
  configuration      text,                          -- 2BHK, 3BHK, 4BHK…
  area_sqft          int,
  possession_status  text check (possession_status in ('received','within_3_months','3_to_6_months','6_to_12_months','over_12_months','unknown')),
  scope              text check (scope in ('full_home','turnkey','modular_kitchen','wardrobes','partial','renovation','other')),
  scope_detail       text,
  budget_min         bigint,
  budget_max         bigint,
  budget_said        text,                          -- what the person actually said
  timeline           text check (timeline in ('immediate','within_1_month','1_to_3_months','3_to_6_months','over_6_months','undecided')),
  ownership          text check (ownership in ('owner','co_owner','family_decision_maker','authorised_representative','tenant','broker','other','unknown')),
  decision_maker     boolean,
  other_designers    text,
  willing_consultation boolean,
  consult_mode       text check (consult_mode in ('site','studio','video','phone')),
  consult_slot       timestamptz,
  consult_slot_said  text,
  language           text,
  ai_summary         text,
  notes              text,

  -- pipeline state
  status             text not null default 'new' check (status in
                      ('new','queued','calling','qualifying','unreachable','qualified','nurture','out_of_area','disqualified','do_not_contact')),
  temperature        text check (temperature in ('hot','warm','cold')),
  score              int,
  score_reasons      jsonb not null default '[]',
  disqualify_reason  text,
  channel            text not null default 'voice' check (channel in ('voice','whatsapp')),
  call_attempts      int not null default 0,
  next_call_at       timestamptz,
  last_contact_at    timestamptz,
  qualified_at       timestamptz,

  -- Papillon's sales stages (brief point 12)
  stage              text not null default 'none' check (stage in
                      ('none','forwarded','contacted','consultation_booked','site_visit','quotation_sent','negotiation','won','lost')),
  forwarded_at       timestamptz,
  stage_updated_at   timestamptz,
  quote_value        bigint,
  won_value          bigint,
  lost_reason        text,
  assigned_to        uuid
);

create index if not exists leads_status_next_call on leads (status, next_call_at);
create index if not exists leads_created on leads (created_at desc);
create index if not exists leads_stage on leads (stage);

create table if not exists calls (
  id                uuid primary key default gen_random_uuid(),
  lead_id           uuid not null references leads(id) on delete cascade,
  provider          text not null default 'exotel',
  provider_call_id  text unique,
  attempt           int not null default 1,
  status            text not null default 'queued' check (status in ('queued','ringing','in_progress','completed','no_answer','busy','failed','cancelled')),
  outcome           text,         -- qualified / callback / not_interested / wrong_number / incomplete …
  started_at        timestamptz not null default now(),
  answered_at       timestamptz,
  ended_at          timestamptz,
  duration_sec      int,
  recording_url     text,
  transcript        jsonb not null default '[]',
  summary           text
);
create index if not exists calls_lead on calls (lead_id, started_at desc);

create table if not exists messages (
  id           uuid primary key default gen_random_uuid(),
  lead_id      uuid references leads(id) on delete cascade,
  channel      text not null check (channel in ('whatsapp','email')),
  direction    text not null check (direction in ('in','out')),
  recipient    text,
  body         text,
  provider_id  text,
  status       text,
  created_at   timestamptz not null default now()
);
create index if not exists messages_lead on messages (lead_id, created_at);

create table if not exists lead_events (
  id         bigserial primary key,
  lead_id    uuid references leads(id) on delete cascade,
  at         timestamptz not null default now(),
  kind       text not null,
  detail     jsonb not null default '{}',
  actor      text not null default 'system'
);
create index if not exists lead_events_lead on lead_events (lead_id, at desc);
create index if not exists lead_events_at on lead_events (at desc);

create table if not exists reports (
  id            uuid primary key default gen_random_uuid(),
  kind          text not null check (kind in ('daily','weekly')),
  period_start  date not null,
  period_end    date not null,
  data          jsonb not null,
  sent_to       text[] not null default '{}',
  created_at    timestamptz not null default now(),
  unique (kind, period_start)
);

-- Who can log in to the dashboard.
--   org = 'agency'   → you: sees every enquiry, calls, spend, settings
--   org = 'papillon' → Papillon's team: sees only forwarded (qualified) leads
create table if not exists team_members (
  user_id   uuid primary key,
  email     text unique not null,
  name      text,
  org       text not null check (org in ('agency','papillon')),
  role      text not null default 'sales' check (role in ('admin','sales','viewer')),
  created_at timestamptz not null default now()
);

create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists leads_touch on leads;
create trigger leads_touch before update on leads for each row execute function touch_updated_at();

-- ─────────────────────────────────────────────────────────────
-- Access rules (dashboard uses the anon key + login; backend uses the DB URL directly)
-- ─────────────────────────────────────────────────────────────
create or replace function my_org() returns text language sql stable security definer set search_path = public as $$
  select org from team_members where user_id = auth.uid()
$$;

alter table leads          enable row level security;
alter table calls          enable row level security;
alter table messages       enable row level security;
alter table lead_events    enable row level security;
alter table reports        enable row level security;
alter table campaigns      enable row level security;
alter table campaign_spend enable row level security;
alter table projects       enable row level security;
alter table settings       enable row level security;
alter table team_members   enable row level security;

drop policy if exists leads_read on leads;
create policy leads_read on leads for select to authenticated using (
  my_org() = 'agency' or (my_org() = 'papillon' and stage <> 'none')
);

drop policy if exists calls_read on calls;
create policy calls_read on calls for select to authenticated using (
  my_org() = 'agency' or (my_org() = 'papillon' and exists (select 1 from leads l where l.id = lead_id and l.stage <> 'none'))
);

drop policy if exists messages_read on messages;
create policy messages_read on messages for select to authenticated using (
  my_org() = 'agency' or (my_org() = 'papillon' and exists (select 1 from leads l where l.id = lead_id and l.stage <> 'none'))
);

drop policy if exists events_read on lead_events;
create policy events_read on lead_events for select to authenticated using (
  my_org() = 'agency' or (my_org() = 'papillon' and exists (select 1 from leads l where l.id = lead_id and l.stage <> 'none'))
);

drop policy if exists reports_read on reports;
create policy reports_read on reports for select to authenticated using (my_org() in ('agency','papillon'));

drop policy if exists campaigns_read on campaigns;
create policy campaigns_read on campaigns for select to authenticated using (my_org() in ('agency','papillon'));
drop policy if exists campaigns_write on campaigns;
create policy campaigns_write on campaigns for all to authenticated using (my_org() = 'agency') with check (my_org() = 'agency');

drop policy if exists spend_read on campaign_spend;
create policy spend_read on campaign_spend for select to authenticated using (my_org() in ('agency','papillon'));
drop policy if exists spend_write on campaign_spend;
create policy spend_write on campaign_spend for all to authenticated using (my_org() = 'agency') with check (my_org() = 'agency');

drop policy if exists projects_read on projects;
create policy projects_read on projects for select to authenticated using (my_org() in ('agency','papillon'));
drop policy if exists projects_write on projects;
create policy projects_write on projects for all to authenticated using (my_org() = 'agency') with check (my_org() = 'agency');

drop policy if exists settings_read on settings;
create policy settings_read on settings for select to authenticated using (my_org() in ('agency','papillon'));
drop policy if exists settings_write on settings;
create policy settings_write on settings for update to authenticated using (my_org() = 'agency') with check (my_org() = 'agency');

drop policy if exists team_self on team_members;
create policy team_self on team_members for select to authenticated using (user_id = auth.uid() or my_org() = 'agency');

-- Papillon's team moves leads through their stages through this one function,
-- so they can't edit qualification data or see unforwarded enquiries.
create or replace function update_lead_stage(
  p_lead uuid, p_stage text, p_quote bigint default null, p_won bigint default null,
  p_lost_reason text default null, p_note text default null
) returns leads language plpgsql security definer set search_path = public as $$
declare r leads; who text;
begin
  if my_org() is null then raise exception 'not allowed'; end if;
  if p_stage not in ('forwarded','contacted','consultation_booked','site_visit','quotation_sent','negotiation','won','lost') then
    raise exception 'bad stage %', p_stage;
  end if;
  select email into who from team_members where user_id = auth.uid();
  update leads set
    stage = p_stage,
    stage_updated_at = now(),
    quote_value = coalesce(p_quote, quote_value),
    won_value   = case when p_stage = 'won' then coalesce(p_won, quote_value, won_value) else won_value end,
    lost_reason = case when p_stage = 'lost' then coalesce(p_lost_reason, lost_reason) else lost_reason end,
    notes = case when p_note is not null and p_note <> '' then concat_ws(E'\n', notes, to_char(now() at time zone 'Asia/Kolkata','DD Mon HH24:MI') || ' — ' || p_note) else notes end
  where id = p_lead and stage <> 'none'
  returning * into r;
  if r.id is null then raise exception 'lead not found'; end if;
  insert into lead_events (lead_id, kind, detail, actor)
    values (p_lead, 'stage', jsonb_build_object('stage', p_stage, 'quote', p_quote, 'won', p_won, 'lost_reason', p_lost_reason, 'note', p_note), coalesce(who, 'dashboard'));
  return r;
end $$;

grant execute on function update_lead_stage(uuid, text, bigint, bigint, text, text) to authenticated;
grant execute on function my_org() to authenticated;

-- Live activity feed in the dashboard
do $$ begin
  begin alter publication supabase_realtime add table lead_events; exception when others then null; end;
  begin alter publication supabase_realtime add table leads; exception when others then null; end;
end $$;
