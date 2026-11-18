import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { seed } from "./demo";
import type { Call, Campaign, Lead, LeadEvent, Message, Org, Project, ReportRow, Settings, Spend, Stage } from "./types";

export interface Snapshot {
  leads: Lead[];
  calls: Call[];
  events: LeadEvent[];
  campaigns: Campaign[];
  spend: Spend[];
  projects: Project[];
  settings: Settings | null;
  reports: ReportRow[];
}

export interface StageUpdate { quote?: number | null; won?: number | null; lostReason?: string | null; note?: string | null }

export interface DataSource {
  mode: "live" | "demo";
  session(): Promise<{ email: string; org: Org } | null>;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  load(): Promise<Snapshot>;
  messages(leadId: string): Promise<Message[]>;
  updateStage(leadId: string, stage: Stage, u: StageUpdate): Promise<void>;
  saveSettings(s: Partial<Settings>): Promise<void>;
  addCampaign(c: Omit<Campaign, "id">): Promise<void>;
  addSpend(s: Omit<Spend, "id">): Promise<void>;
  addProject(p: Omit<Project, "id">): Promise<void>;
  removeProject(id: string): Promise<void>;
  subscribe(onChange: () => void): () => void;
}

const URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

// ── Live: Supabase ──────────────────────────────────────────────
function live(sb: SupabaseClient): DataSource {
  const must = <T,>(r: { data: T | null; error: any }) => {
    if (r.error) throw new Error(r.error.message);
    return r.data as T;
  };
  return {
    mode: "live",
    async session() {
      const { data } = await sb.auth.getSession();
      const u = data.session?.user;
      if (!u) return null;
      const tm = await sb.from("team_members").select("org").eq("user_id", u.id).maybeSingle();
      if (!tm.data) throw new Error("This login isn't on the team list yet. Ask the admin to add you.");
      return { email: u.email ?? "", org: tm.data.org as Org };
    },
    async signIn(email, password) {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
    },
    async signOut() { await sb.auth.signOut(); },
    async load() {
      const [leads, calls, events, campaigns, spend, projects, settings, reports] = await Promise.all([
        sb.from("leads").select("*").order("created_at", { ascending: false }).limit(5000),
        sb.from("calls").select("*").order("started_at", { ascending: false }).limit(3000),
        sb.from("lead_events").select("*").order("at", { ascending: false }).limit(400),
        sb.from("campaigns").select("*").order("created_at", { ascending: false }),
        sb.from("campaign_spend").select("*"),
        sb.from("projects").select("*").order("possession_from"),
        sb.from("settings").select("*").eq("id", 1).maybeSingle(),
        sb.from("reports").select("*").order("period_start", { ascending: false }).limit(120),
      ]);
      return {
        leads: must(leads), calls: must(calls), events: must(events), campaigns: must(campaigns),
        spend: must(spend), projects: must(projects), settings: must(settings), reports: must(reports),
      };
    },
    async messages(leadId) {
      return must(await sb.from("messages").select("*").eq("lead_id", leadId).order("created_at"));
    },
    async updateStage(leadId, stage, u) {
      must(await sb.rpc("update_lead_stage", {
        p_lead: leadId, p_stage: stage, p_quote: u.quote ?? null, p_won: u.won ?? null,
        p_lost_reason: u.lostReason ?? null, p_note: u.note ?? null,
      }));
    },
    async saveSettings(s) { must(await sb.from("settings").update({ ...s, updated_at: new Date().toISOString() }).eq("id", 1)); },
    async addCampaign(c) { must(await sb.from("campaigns").insert(c)); },
    async addSpend(s) { must(await sb.from("campaign_spend").upsert(s, { onConflict: "campaign_id,spend_date" })); },
    async addProject(p) { must(await sb.from("projects").insert(p)); },
    async removeProject(id) { must(await sb.from("projects").delete().eq("id", id)); },
    subscribe(onChange) {
      let t: number | undefined;
      const bump = () => { clearTimeout(t); t = window.setTimeout(onChange, 400); };
      const ch = sb.channel("pipeline")
        .on("postgres_changes", { event: "*", schema: "public", table: "leads" }, bump)
        .on("postgres_changes", { event: "INSERT", schema: "public", table: "lead_events" }, bump)
        .subscribe();
      return () => { sb.removeChannel(ch); };
    },
  };
}

// ── Demo: sample data kept in this browser ─────────────────────
const DEMO_KEY = "papillon-demo-v1";
function demo(): DataSource {
  const read = (): Snapshot & { messagesBy: Record<string, Message[]>; org: Org; signedIn: boolean } => {
    try {
      const raw = localStorage.getItem(DEMO_KEY);
      if (raw) return JSON.parse(raw);
    } catch { /* storage unavailable */ }
    return { ...seed(), org: "agency", signedIn: true };
  };
  let db = read();
  const save = () => { try { localStorage.setItem(DEMO_KEY, JSON.stringify(db)); } catch { /* ignore */ } };
  const listeners = new Set<() => void>();
  const emit = () => { save(); listeners.forEach((f) => f()); };
  const id = () => Math.random().toString(36).slice(2, 10);
  return {
    mode: "demo",
    async session() { return db.signedIn ? { email: db.org === "agency" ? "sachin@theingredientlist.co" : "sales@papillon", org: db.org } : null; },
    async signIn(email) { db.signedIn = true; db.org = /papillon/i.test(email) ? "papillon" : "agency"; emit(); },
    async signOut() { db.signedIn = false; emit(); },
    async load() {
      const { leads, calls, events, campaigns, spend, projects, settings, reports } = db;
      const visible = db.org === "papillon" ? leads.filter((l) => l.stage !== "none") : leads;
      const ids = new Set(visible.map((l) => l.id));
      return { leads: visible, calls: calls.filter((c) => ids.has(c.lead_id)), events: events.filter((e) => ids.has(e.lead_id)),
               campaigns, spend, projects, settings, reports };
    },
    async messages(leadId) { return db.messagesBy[leadId] ?? []; },
    async updateStage(leadId, stage, u) {
      const l = db.leads.find((x) => x.id === leadId);
      if (!l) return;
      l.stage = stage;
      l.stage_updated_at = new Date().toISOString();
      if (u.quote) l.quote_value = u.quote;
      if (stage === "won") l.won_value = u.won ?? l.quote_value;
      if (stage === "lost" && u.lostReason) l.lost_reason = u.lostReason;
      if (u.note) l.notes = [l.notes, u.note].filter(Boolean).join("\n");
      db.events.unshift({ id: Date.now(), lead_id: leadId, at: new Date().toISOString(), kind: "stage",
                          detail: { stage, note: u.note, quote: u.quote }, actor: db.org === "agency" ? "sachin" : "papillon team" });
      emit();
    },
    async saveSettings(s) { db.settings = { ...(db.settings as Settings), ...s }; emit(); },
    async addCampaign(c) { db.campaigns.unshift({ ...c, id: id() }); emit(); },
    async addSpend(s) {
      db.spend = db.spend.filter((x) => !(x.campaign_id === s.campaign_id && x.spend_date === s.spend_date));
      db.spend.push({ ...s, id: id() }); emit();
    },
    async addProject(p) { db.projects.push({ ...p, id: id() }); emit(); },
    async removeProject(pid) { db.projects = db.projects.filter((p) => p.id !== pid); emit(); },
    subscribe(f) { listeners.add(f); return () => { listeners.delete(f); }; },
  };
}

export const api: DataSource = URL && KEY ? live(createClient(URL, KEY)) : demo();

export function resetDemo() {
  try { localStorage.removeItem(DEMO_KEY); } catch { /* ignore */ }
  location.reload();
}

export function switchDemoOrg(org: Org) {
  try {
    const raw = localStorage.getItem(DEMO_KEY);
    const db = raw ? JSON.parse(raw) : { ...seed(), signedIn: true };
    db.org = org;
    localStorage.setItem(DEMO_KEY, JSON.stringify(db));
  } catch { /* ignore */ }
  location.reload();
}
