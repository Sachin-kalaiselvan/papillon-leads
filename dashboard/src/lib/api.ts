import { demoProspects, seed } from "./demo";
import type { Call, Campaign, CrawlState, Lead, LeadEvent, Message, Org, Project, Prospect, ProspectStatus, ReportRow, Settings, Spend, Stage } from "./types";

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
  prospects(): Promise<{ prospects: Prospect[]; state: CrawlState }>;
  updateProspect(id: string, u: { status?: ProspectStatus; notes?: string }): Promise<void>;
  prospectToProject(id: string, from: string, to: string): Promise<void>;
  crawlNow(feed: "projects" | "posts" | "partners"): Promise<number>;
  subscribe(onChange: () => void): () => void;
}

const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "");
const TOKEN_KEY = "papillon-token";

// ── Live: your own server (backend/papillon/api.py) ─────────────
function live(base: string): DataSource {
  const token = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
  const call = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const r = await fetch(base + path, {
      ...init,
      headers: { "content-type": "application/json", ...(token() ? { authorization: `Bearer ${token()}` } : {}), ...(init.headers || {}) },
    });
    if (r.status === 401) { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } }
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Server error ${r.status}`);
    return r.json();
  };
  const post = (path: string, body: unknown, method = "POST") => call(path, { method, body: JSON.stringify(body) });
  return {
    mode: "live",
    async session() {
      if (!token()) return null;
      try { return await call<{ email: string; org: Org }>("/api/me"); } catch { return null; }
    },
    async signIn(email, password) {
      const r = await call<{ token: string }>("/api/login", { method: "POST", body: JSON.stringify({ email, password }) });
      try { localStorage.setItem(TOKEN_KEY, r.token); } catch { /* ignore */ }
    },
    async signOut() { try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } },
    load: () => call<Snapshot>("/api/snapshot"),
    messages: (leadId) => call<Message[]>(`/api/leads/${leadId}/messages`),
    async updateStage(leadId, stage, u) { await post(`/api/leads/${leadId}/stage`, { stage, ...u }); },
    async saveSettings(s) { await post("/api/settings", s, "PUT"); },
    async addCampaign(c) { await post("/api/campaigns", c); },
    async addSpend(s) { await post("/api/spend", s); },
    async addProject(p) { await post("/api/projects", p); },
    async removeProject(id) { await call(`/api/projects/${id}`, { method: "DELETE" }); },
    prospects: () => call("/api/prospects"),
    async updateProspect(id, u) { await post(`/api/prospects/${id}`, u); },
    async prospectToProject(id, from, to) { await post(`/api/prospects/${id}/to-projects`, { possession_from: from, possession_to: to }); },
    async crawlNow(feed) { return (await call<{ new: number }>(`/api/crawl/${feed}`, { method: "POST" })).new; },
    subscribe(onChange) {
      // refresh every 20 s and whenever the tab comes back into view
      const t = window.setInterval(() => { if (!document.hidden) onChange(); }, 20000);
      const vis = () => { if (!document.hidden) onChange(); };
      document.addEventListener("visibilitychange", vis);
      return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); };
    },
  };
}

// ── Demo: sample data kept in this browser ─────────────────────
const DEMO_KEY = "papillon-demo-v1";
function demo(): DataSource {
  const read = (): Snapshot & { messagesBy: Record<string, Message[]>; org: Org; signedIn: boolean; prospects?: { prospects: Prospect[]; state: CrawlState } } => {
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
    async prospects() {
      if (!db.prospects) db.prospects = demoProspects();
      return db.prospects;
    },
    async updateProspect(pid, u) {
      const p = db.prospects?.prospects.find((x: Prospect) => x.id === pid);
      if (p) Object.assign(p, u);
      emit();
    },
    async prospectToProject(pid, from, to) {
      const p = db.prospects?.prospects.find((x: Prospect) => x.id === pid);
      if (!p) return;
      p.status = "added";
      db.projects.push({ id: pid, name: p.name ?? "", builder: null, locality: p.locality, possession_from: from || null, possession_to: to || null });
      emit();
    },
    async crawlNow() { return 0; },
    subscribe(f) { listeners.add(f); return () => { listeners.delete(f); }; },
  };
}

export const api: DataSource = API ? live(API) : demo();

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
