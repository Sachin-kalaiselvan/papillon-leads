import type { Snapshot } from "./api";
import type { Lead, Stage } from "./types";

const ORDER: Stage[] = ["forwarded", "contacted", "consultation_booked", "site_visit", "quotation_sent", "negotiation", "won"];
export const reached = (l: Lead, s: Stage) =>
  l.stage === s || (l.stage !== "lost" && l.stage !== "none" && ORDER.indexOf(l.stage) >= ORDER.indexOf(s)) ||
  (l.stage === "lost" && ORDER.indexOf(s) <= ORDER.indexOf("site_visit")); // lost deals got at least to site visit

export const since = (days: number) => Date.now() - days * 86400000;

export function inRange(leads: Lead[], days: number) {
  const t = since(days);
  return leads.filter((l) => new Date(l.created_at).getTime() >= t);
}

export function summary(snap: Snapshot, days: number) {
  const leads = inRange(snap.leads, days);
  const t = since(days);
  const calls = snap.calls.filter((c) => new Date(c.started_at).getTime() >= t);
  const q = leads.filter((l) => l.status === "qualified");
  return {
    enquiries: leads.length,
    contacted: leads.filter((l) => l.last_contact_at).length,
    calls: calls.length,
    connected: calls.filter((c) => c.answered_at).length,
    hot: q.filter((l) => l.temperature === "hot").length,
    warm: q.filter((l) => l.temperature === "warm").length,
    cold: leads.filter((l) => l.temperature === "cold").length,
    notFit: leads.filter((l) => ["disqualified", "out_of_area", "do_not_contact"].includes(l.status)).length,
    forwarded: leads.filter((l) => l.stage !== "none").length,
    consultations: leads.filter((l) => reached(l, "consultation_booked")).length,
    siteVisits: leads.filter((l) => reached(l, "site_visit")).length,
    quotes: leads.filter((l) => reached(l, "quotation_sent")).length,
    won: leads.filter((l) => l.stage === "won").length,
    wonValue: leads.filter((l) => l.stage === "won").reduce((a, l) => a + (l.won_value || 0), 0),
    pipelineValue: leads.filter((l) => ["quotation_sent", "negotiation"].includes(l.stage)).reduce((a, l) => a + (l.quote_value || 0), 0),
  };
}

export function byDay(leads: Lead[], days: number) {
  const out: { date: string; total: number; qualified: number }[] = [];
  for (let d = days - 1; d >= 0; d--) {
    const date = new Date(Date.now() - d * 86400000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
    const dl = leads.filter((l) => new Date(l.created_at).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }) === date);
    out.push({ date, total: dl.length, qualified: dl.filter((l) => l.status === "qualified" && l.temperature !== "cold").length });
  }
  return out;
}

export function campaignTable(snap: Snapshot, fromISO: string, toISO: string) {
  const a = new Date(fromISO + "T00:00:00+05:30").getTime();
  const b = new Date(toISO + "T23:59:59+05:30").getTime();
  const leads = snap.leads.filter((l) => { const t = new Date(l.created_at).getTime(); return t >= a && t <= b; });
  const rows = [...snap.campaigns, { id: "__none", name: "No campaign", source: "other", audience: null, status: "", started_on: null }].map((c) => {
    const ls = leads.filter((l) => (l.campaign_id ?? "__none") === c.id);
    const spend = snap.spend.filter((s) => s.campaign_id === c.id && s.spend_date >= fromISO && s.spend_date <= toISO)
      .reduce((x, s) => x + Number(s.amount), 0);
    const hot = ls.filter((l) => l.status === "qualified" && l.temperature === "hot").length;
    const warm = ls.filter((l) => l.status === "qualified" && l.temperature === "warm").length;
    const q = hot + warm;
    return {
      id: c.id, name: c.name, source: c.source, spend, enquiries: ls.length, hot, warm,
      cold: ls.filter((l) => l.temperature === "cold").length,
      consultations: ls.filter((l) => reached(l, "consultation_booked")).length,
      siteVisits: ls.filter((l) => reached(l, "site_visit")).length,
      quotes: ls.filter((l) => reached(l, "quotation_sent")).length,
      won: ls.filter((l) => l.stage === "won").length,
      wonValue: ls.filter((l) => l.stage === "won").reduce((x, l) => x + (l.won_value || 0), 0),
      cpl: ls.length ? spend / ls.length : null, cpql: q ? spend / q : null,
      qRate: ls.length ? (100 * q) / ls.length : 0,
    };
  }).filter((r) => r.enquiries || r.spend);
  return rows;
}
