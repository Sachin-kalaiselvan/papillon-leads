import type { Lead } from "./types";

export const lakh = (v: number | null | undefined) =>
  v ? `₹${(v / 100000).toFixed(v % 100000 === 0 ? 0 : 1)}L` : "—";

export const inr = (v: number | null | undefined) =>
  v == null ? "—" : "₹" + Math.round(v).toLocaleString("en-IN");

export const budget = (l: Pick<Lead, "budget_min" | "budget_max">) => {
  const { budget_min: lo, budget_max: hi } = l;
  if (lo && hi && lo !== hi) return `${lakh(lo)}–${lakh(hi).slice(1)}`;
  if (lo && !hi) return `${lakh(lo)}+`;
  return lakh(hi || lo);
};

const LABELS: Record<string, string> = {
  full_home: "Complete home", turnkey: "Turnkey", modular_kitchen: "Modular kitchen", wardrobes: "Wardrobes",
  partial: "Partial", renovation: "Renovation", other: "Other",
  received: "Possession received", within_3_months: "Within 3 months", "3_to_6_months": "3–6 months",
  "6_to_12_months": "6–12 months", over_12_months: "12+ months", unknown: "Unknown",
  immediate: "Immediately", within_1_month: "Within a month", "1_to_3_months": "1–3 months",
  over_6_months: "6+ months", undecided: "Undecided",
  owner: "Owner", co_owner: "Co-owner", family_decision_maker: "Family decision-maker",
  authorised_representative: "Authorised representative", tenant: "Tenant", broker: "Broker",
  apartment: "Apartment", villa: "Villa", independent_house: "Independent house", row_house: "Row house",
  penthouse: "Penthouse", plot: "Plot", commercial: "Commercial",
  new: "Awaiting consent", queued: "Queued to call", calling: "On a call", qualifying: "Collecting details",
  unreachable: "Unreachable", qualified: "Qualified", nurture: "Nurture", out_of_area: "Out of area",
  disqualified: "Not a fit", do_not_contact: "Do not contact",
  site: "At site", studio: "At studio", video: "Video call", phone: "Phone",
  meta: "Meta ads", google: "Google ads", website: "Website", portal: "Portal", referral: "Referral",
  partner: "Partner", import: "Import", manual: "Manual",
};
export const label = (k: string | null | undefined) => (k ? LABELS[k] ?? k.replace(/_/g, " ") : "—");

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 0) {
    const f = -s;
    if (f < 3600) return `in ${Math.round(f / 60)}m`;
    if (f < 86400) return `in ${Math.round(f / 3600)}h`;
    return `in ${Math.round(f / 86400)}d`;
  }
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

export const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }) : "—";

export const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" });

export const place = (l: Lead) => [l.project_name, l.locality, l.city].filter(Boolean).join(", ") || "—";

export const istDate = (d = new Date()) => d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
