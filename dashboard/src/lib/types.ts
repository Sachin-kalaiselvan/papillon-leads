export type Temperature = "hot" | "warm" | "cold";
export type Status =
  | "new" | "queued" | "calling" | "qualifying" | "unreachable" | "qualified"
  | "nurture" | "out_of_area" | "disqualified" | "do_not_contact";
export type Stage =
  | "none" | "forwarded" | "contacted" | "consultation_booked" | "site_visit"
  | "quotation_sent" | "negotiation" | "won" | "lost";

export interface Lead {
  id: string;
  ref: string;
  created_at: string;
  name: string | null;
  phone: string;
  phone_country: string | null;
  email: string | null;
  lives_in: string | null;
  source: string;
  campaign_id: string | null;
  property_type: string | null;
  project_name: string | null;
  locality: string | null;
  city: string | null;
  configuration: string | null;
  area_sqft: number | null;
  possession_status: string | null;
  scope: string | null;
  scope_detail: string | null;
  budget_min: number | null;
  budget_max: number | null;
  budget_said: string | null;
  timeline: string | null;
  ownership: string | null;
  decision_maker: boolean | null;
  other_designers: string | null;
  willing_consultation: boolean | null;
  consult_mode: string | null;
  consult_slot: string | null;
  consult_slot_said: string | null;
  ai_summary: string | null;
  notes: string | null;
  status: Status;
  temperature: Temperature | null;
  score: number | null;
  score_reasons: string[];
  disqualify_reason: string | null;
  channel: "voice" | "whatsapp";
  call_attempts: number;
  next_call_at: string | null;
  last_contact_at: string | null;
  qualified_at: string | null;
  stage: Stage;
  forwarded_at: string | null;
  stage_updated_at: string | null;
  quote_value: number | null;
  won_value: number | null;
  lost_reason: string | null;
  enquiry_count: number;
}

export interface Call {
  id: string;
  lead_id: string;
  attempt: number;
  status: string;
  outcome: string | null;
  started_at: string;
  answered_at: string | null;
  duration_sec: number | null;
  recording_url: string | null;
  transcript: { role: "user" | "assistant"; text: string }[];
  summary: string | null;
}

export interface LeadEvent {
  id: number;
  lead_id: string;
  at: string;
  kind: string;
  detail: Record<string, unknown>;
  actor: string;
}

export interface Message {
  id: string;
  lead_id: string;
  channel: "whatsapp" | "email";
  direction: "in" | "out";
  body: string;
  created_at: string;
}

export interface Campaign {
  id: string;
  name: string;
  source: string;
  audience: string | null;
  status: string;
  started_on: string | null;
}

export interface Spend {
  id: string;
  campaign_id: string;
  spend_date: string;
  amount: number;
  clicks: number | null;
}

export interface Project {
  id: string;
  name: string;
  builder: string | null;
  locality: string | null;
  possession_from: string | null;
  possession_to: string | null;
}

export interface Settings {
  service_areas: string[];
  accept_outstation: boolean;
  outstation_min_budget: number;
  min_budget_full_home: number;
  min_budget_kitchen: number;
  min_budget_wardrobes: number;
  min_budget_partial: number;
  budget_tolerance: number;
  forward_temperatures: string[];
  call_window_start: string;
  call_window_end: string;
  max_call_attempts: number;
  max_parallel_calls: number;
  nurture_recheck_days: number;
  forward_whatsapp: string[];
  forward_emails: string[];
  report_emails: string[];
}

export interface ReportRow {
  id: string;
  kind: "daily" | "weekly";
  period_start: string;
  period_end: string;
  data: Record<string, any>;
  sent_to: string[];
  created_at: string;
}

export type Org = "agency" | "papillon";

export const STAGES: { key: Stage; label: string }[] = [
  { key: "forwarded", label: "New for team" },
  { key: "contacted", label: "Contacted" },
  { key: "consultation_booked", label: "Consultation" },
  { key: "site_visit", label: "Site visit" },
  { key: "quotation_sent", label: "Quotation" },
  { key: "negotiation", label: "Negotiation" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
];

export type ProspectKind = "project" | "post" | "partner";
export type ProspectStatus = "new" | "contacted" | "interested" | "partner" | "added" | "not_relevant";

export interface Prospect {
  id: string;
  kind: ProspectKind;
  source: string;
  name: string | null;
  category: string | null;
  locality: string | null;
  city: string | null;
  lat: number | null;
  lon: number | null;
  phone: string | null;
  website: string | null;
  email: string | null;
  url: string | null;
  body: string | null;
  posted_at: string | null;
  score: number;
  ring_km: number | null;
  status: ProspectStatus;
  notes: string | null;
  data: Record<string, any>;
  found_at: string;
}

export interface CrawlState {
  projects?: { last_run?: string; found?: number; new?: number; last_error?: string };
  posts?: { last_run?: string; found?: number; new?: number; errors?: string[]; last_error?: string };
  partners?: { last_run?: string; next_ring_km?: number; max_ring_km?: number; cycle?: number;
               rings?: { km: number; found: number; new: number; at: string }[]; last_error?: string };
}
