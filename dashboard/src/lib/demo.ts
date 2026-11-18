// Sample data so the dashboard can be previewed before Supabase is connected.
import type { Call, Campaign, Lead, LeadEvent, Message, Project, ReportRow, Settings, Spend, Stage, Status, Temperature } from "./types";

let s = 7;
const rnd = () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
const pick = <T,>(a: T[]) => a[Math.floor(rnd() * a.length)];
const iso = (minsAgo: number) => new Date(Date.now() - Math.max(minsAgo, 0) * 60000).toISOString();
const future = (mins: number) => new Date(Date.now() + mins * 60000).toISOString();

const FIRST = ["Ananya", "Rahul", "Divya", "Karthik", "Meghna", "Vikram", "Sneha", "Arjun", "Pooja", "Nikhil", "Lakshmi",
  "Rohan", "Kavya", "Siddharth", "Aditi", "Harish", "Priya", "Manoj", "Shalini", "Varun", "Deepa", "Abhishek", "Nandini", "Suresh"];
const LAST = ["Rao", "Iyer", "Reddy", "Nair", "Sharma", "Menon", "Gowda", "Shetty", "Kulkarni", "Pillai", "Hegde", "Bhat", "Krishnan", "Joshi"];
const PROJECTS: [string, string][] = [
  ["Amberwood Residences", "Sarjapur Road"], ["Lakeview Grande", "Varthur"], ["Silver Oak Enclave", "Hennur"],
  ["Cedar Heights", "Whitefield"], ["Banyan Greens", "Devanahalli"], ["Meridian Towers", "Hebbal"],
  ["Palm Court Villas", "Kanakapura Road"], ["Orchid Springs", "Thanisandra"], ["Riverstone Park", "Electronic City"],
  ["Monarch Bay", "Bellandur"]];
const LIVES = ["Bengaluru", "Bengaluru", "Bengaluru", "Bengaluru", "Dubai", "Pune", "Hyderabad", "Singapore", "San Jose", "Chennai", "Mumbai", "Abu Dhabi"];

export function seed() {
  s = 7;
  const campaigns: Campaign[] = [
    { id: "c1", name: "Meta · Handover projects Bengaluru", source: "meta", audience: "Homebuyers in 12 handover projects, 28–55", status: "active", started_on: "2026-11-01" },
    { id: "c2", name: "Meta · NRI Gulf & Singapore", source: "meta", audience: "Indians in UAE/SG/US with Bengaluru property interest", status: "active", started_on: "2026-11-03" },
    { id: "c3", name: "Google · Interior designers Bangalore", source: "google", audience: "Search: home interiors, 3BHK interiors, villa interiors", status: "active", started_on: "2026-11-01" },
    { id: "c4", name: "Website · Consultation page", source: "website", audience: "Organic + retargeting", status: "active", started_on: "2026-11-01" },
  ];
  const projects: Project[] = PROJECTS.slice(0, 7).map(([name, locality], i) => ({
    id: "p" + i, name, builder: null, locality,
    possession_from: new Date(Date.now() - (60 - i * 25) * 86400000).toISOString().slice(0, 10),
    possession_to: new Date(Date.now() + (30 + i * 20) * 86400000).toISOString().slice(0, 10),
  }));
  const leads: Lead[] = [];
  const calls: Call[] = [];
  const events: LeadEvent[] = [];
  const messagesBy: Record<string, Message[]> = {};

  for (let i = 0; i < 78; i++) {
    const age = Math.floor(rnd() * 14 * 1440 * (i < 10 ? 0.06 : 1));
    const camp = pick(campaigns);
    const [proj, loc] = pick(PROJECTS);
    const lives = camp.id === "c2" ? pick(["Dubai", "Singapore", "Abu Dhabi", "San Jose", "Doha"]) : pick(LIVES);
    const overseas = !["Bengaluru", "Pune", "Hyderabad", "Chennai", "Mumbai"].includes(lives) && rnd() > 0.4;
    const scope = pick(["full_home", "full_home", "full_home", "turnkey", "modular_kitchen", "wardrobes", "partial"]);
    const bhk = pick(["2BHK", "3BHK", "3BHK", "3BHK", "4BHK", "4BHK villa"]);
    const base = scope === "full_home" || scope === "turnkey" ? (bhk.startsWith("2") ? 9 : bhk.startsWith("3") ? 16 : 28) : scope === "modular_kitchen" ? 4 : 3;
    const bmin = Math.round((base * (0.6 + rnd() * 0.9))) * 100000;
    const poss = pick(["received", "received", "within_3_months", "within_3_months", "3_to_6_months", "6_to_12_months"]);
    const tl = pick(["immediate", "within_1_month", "within_1_month", "1_to_3_months", "1_to_3_months", "3_to_6_months", "undecided"]);
    const roll = rnd();
    let status: Status = "qualified";
    let temperature: Temperature | null = null;
    let reason: string | null = null;
    const fullOk = bmin >= (scope === "full_home" || scope === "turnkey" ? 1275000 : scope === "modular_kitchen" ? 255000 : 170000);
    if (age < 25) status = pick(["queued", "calling", "qualifying"]);
    else if (roll < 0.07) { status = "disqualified"; reason = pick(["Not the owner or decision-maker", "Wrong number", "Not interested"]); }
    else if (roll < 0.11) { status = "out_of_area"; reason = "Property outside Papillon's service area"; }
    else if (roll < 0.17) status = "unreachable";
    else if (roll < 0.21) status = "new";
    else if (!fullOk && bmin < 750000 && (scope === "full_home" || scope === "turnkey")) { status = "disqualified"; reason = "Budget far below Papillon's range"; }
    else if (!fullOk || tl === "undecided") { status = "nurture"; temperature = "cold"; }
    else if (tl === "3_to_6_months") temperature = "cold";
    else if ((tl === "immediate" || tl === "within_1_month") && (poss === "received" || poss === "within_3_months")) temperature = "hot";
    else temperature = "warm";

    const forwarded = status === "qualified" && temperature !== "cold";
    let stage: Stage = "none";
    if (forwarded) {
      const daysIn = age / 1440;
      const ladder: Stage[] = ["forwarded", "contacted", "consultation_booked", "site_visit", "quotation_sent", "negotiation", "won"];
      const reach = Math.min(ladder.length - 1, Math.floor(rnd() * Math.min(7, daysIn * 0.9 + 1)));
      stage = ladder[reach];
      if (reach >= 3 && rnd() < 0.18) stage = "lost";
    }
    const first = pick(FIRST);
    const id = `L${i.toString().padStart(3, "0")}`;
    const created = iso(age);
    const score = status === "qualified" ? Math.round(45 + rnd() * 50) : Math.round(rnd() * 45);
    const qv = ["quotation_sent", "negotiation", "won", "lost"].includes(stage) ? Math.round(bmin * (1 + rnd() * 0.3) / 10000) * 10000 : null;
    const lead: Lead = {
      id, ref: `PAP-${1001 + i}`, created_at: created, name: `${first} ${pick(LAST)}`,
      phone: overseas ? `+971 5${Math.floor(10000000 + rnd() * 89999999)}` : `+91 9${Math.floor(100000000 + rnd() * 899999999)}`,
      phone_country: overseas ? "AE" : "IN", email: `${first.toLowerCase()}@example.com`, lives_in: lives,
      source: camp.source, campaign_id: camp.id,
      property_type: bhk.includes("villa") ? "villa" : "apartment", project_name: status === "out_of_area" ? "Seaside Crest" : proj,
      locality: status === "out_of_area" ? "OMR" : loc, city: status === "out_of_area" ? "Chennai" : "Bengaluru",
      configuration: bhk, area_sqft: bhk.startsWith("2") ? 1180 + Math.round(rnd() * 200) : bhk.startsWith("3") ? 1500 + Math.round(rnd() * 400) : 2400 + Math.round(rnd() * 1200),
      possession_status: poss, scope, scope_detail: scope === "partial" ? "Living, dining and master bedroom" : null,
      budget_min: bmin, budget_max: rnd() > 0.5 ? Math.round(bmin * 1.25 / 100000) * 100000 : bmin, budget_said: `${bmin / 100000} lakhs`,
      timeline: tl, ownership: status === "disqualified" && reason?.startsWith("Not the owner") ? "tenant" : pick(["owner", "owner", "owner", "co_owner", "family_decision_maker"]),
      decision_maker: true, other_designers: rnd() > 0.6 ? "Has one other quote" : null,
      willing_consultation: status === "qualified" || status === "nurture" ? rnd() > 0.1 : null,
      consult_mode: overseas ? "video" : pick(["site", "studio", "video"]),
      consult_slot: null, consult_slot_said: forwarded ? pick(["Saturday 11 am", "Sunday afternoon", "Weekday evening after 6", "Next Friday 4 pm"]) : null,
      ai_summary: status === "qualified" || status === "nurture"
        ? `${bhk} in ${proj}, ${loc}. ${poss === "received" ? "Possession received" : "Possession " + poss.replace(/_/g, " ")}. Wants ${scope.replace(/_/g, " ")} with a budget around ${bmin / 100000} lakhs, starting ${tl.replace(/_/g, " ")}. ${lives !== "Bengaluru" ? "Lives in " + lives + ", prefers video consultation." : ""}`
        : null,
      notes: null, status, temperature, score,
      score_reasons: status === "qualified" || status === "nurture"
        ? [scope === "full_home" || scope === "turnkey" ? "+ Complete-home / turnkey scope" : `+ ${scope.replace(/_/g, " ")}`,
           (fullOk ? "+ " : "− ") + `Budget ₹${bmin / 100000}L vs minimum ₹${scope === "full_home" || scope === "turnkey" ? 15 : scope === "modular_kitchen" ? 3 : 2}L`,
           (tl === "undecided" || tl === "3_to_6_months" ? "− " : "+ ") + "Timeline " + tl.replace(/_/g, " "),
           ...(poss === "received" || poss === "within_3_months" ? ["+ Possession " + poss.replace(/_/g, " ")] : [])]
        : [],
      disqualify_reason: reason, channel: overseas ? "whatsapp" : "voice", call_attempts: status === "unreachable" ? 4 : 1,
      next_call_at: status === "queued" ? future(3) : status === "nurture" ? future(30 * 1440) : null,
      last_contact_at: status === "new" ? null : iso(age - 8),
      qualified_at: status === "qualified" ? iso(age - 12) : null, stage,
      forwarded_at: forwarded ? iso(age - 13) : null, stage_updated_at: forwarded ? iso(Math.max(0, age - 1440 * rnd() * 4)) : null,
      quote_value: qv, won_value: stage === "won" ? qv : null, lost_reason: stage === "lost" ? pick(["Went with a cheaper quote", "Postponed the project"]) : null,
      enquiry_count: rnd() > 0.9 ? 2 : 1,
    };
    leads.push(lead);

    events.push({ id: i * 10 + 1, lead_id: id, at: created, kind: "created", detail: { source: camp.source }, actor: camp.source });
    if (lead.channel === "voice" && status !== "new") {
      const answered = status !== "unreachable";
      const dur = answered ? 140 + Math.floor(rnd() * 200) : 0;
      calls.push({
        id: "call" + i, lead_id: id, attempt: 1, status: answered ? "completed" : "no_answer",
        outcome: answered ? (status === "disqualified" ? (reason === "Wrong number" ? "wrong_number" : "not_interested") : "completed") : null,
        started_at: iso(age - 2), answered_at: answered ? iso(age - 2) : null, duration_sec: dur, recording_url: null,
        summary: lead.ai_summary,
        transcript: answered ? [
          { role: "assistant", text: `Hello, am I speaking with ${first}? This is Meera, the virtual assistant from Papillon Interiors. You'd enquired about interiors for your home — is this a good time for two minutes?` },
          { role: "user", text: "Yes, tell me." },
          { role: "assistant", text: "Thank you! Which project is your home in, and is it in Bengaluru?" },
          { role: "user", text: `It's ${proj}, ${loc}. ${bhk}.` },
          { role: "assistant", text: "Lovely. Have you received possession already, or when are you expecting it?" },
          { role: "user", text: poss === "received" ? "We got the keys last month." : `Builder says ${poss.replace(/_/g, " ")}.` },
          { role: "assistant", text: "Are you looking at complete home interiors, or specific areas like the kitchen and wardrobes?" },
          { role: "user", text: scope === "full_home" || scope === "turnkey" ? "Full home, everything." : `Mainly the ${scope.replace(/_/g, " ")}.` },
          { role: "assistant", text: "To suggest the right design approach, what budget range do you have in mind for the interiors, roughly?" },
          { role: "user", text: `Around ${bmin / 100000} lakhs.` },
          { role: "assistant", text: "And when would you like the work to start?" },
          { role: "user", text: tl === "immediate" ? "As soon as possible." : `Probably ${tl.replace(/_/g, " ")}.` },
          { role: "assistant", text: "Is the home in your name, or are you planning it for family?" },
          { role: "user", text: "It's ours, I'm deciding." },
          { role: "assistant", text: "Would you like a free design consultation — at the site, at our studio, or on a video call?" },
          { role: "user", text: lead.consult_slot_said ? `Video is fine. ${lead.consult_slot_said} works.` : "Let me think and get back." },
          { role: "assistant", text: "Perfect, thank you. Our design team will get in touch with you shortly." },
        ] : [],
      });
      events.push({ id: i * 10 + 2, lead_id: id, at: iso(age - 2), kind: answered ? "call_answered" : "call_retry_scheduled", detail: {}, actor: "system" });
    }
    if (lead.channel === "whatsapp") {
      messagesBy[id] = [
        { id: id + "m1", lead_id: id, channel: "whatsapp", direction: "out", created_at: iso(age - 1), body: `Hi ${first}, this is Papillon Interiors about your home interiors enquiry. Could you reply here so we can understand your requirement?` },
        { id: id + "m2", lead_id: id, channel: "whatsapp", direction: "in", created_at: iso(age - 20), body: `Hi, yes. ${bhk} in ${proj}, possession ${poss === "received" ? "done" : "soon"}. I'm in ${lives}.` },
        { id: id + "m3", lead_id: id, channel: "whatsapp", direction: "out", created_at: iso(age - 21), body: "Thanks! Are you looking at complete home interiors, or specific areas?" },
        { id: id + "m4", lead_id: id, channel: "whatsapp", direction: "in", created_at: iso(age - 30), body: `${scope === "full_home" ? "Complete home" : scope.replace(/_/g, " ")}, budget around ${bmin / 100000}L.` },
      ];
    }
    if (status !== "new" && status !== "queued" && status !== "calling") {
      events.push({ id: i * 10 + 3, lead_id: id, at: iso(age - 11), kind: "scored", detail: { status, temperature, score }, actor: "system" });
    }
    if (forwarded) {
      events.push({ id: i * 10 + 4, lead_id: id, at: iso(age - 13), kind: "forwarded", detail: { temperature, exclusive_to: "Papillon Interiors" }, actor: "system" });
      if (stage !== "forwarded") events.push({ id: i * 10 + 5, lead_id: id, at: lead.stage_updated_at!, kind: "stage", detail: { stage }, actor: "papillon team" });
    }
  }
  events.sort((a, b) => b.at.localeCompare(a.at));

  const spend: Spend[] = [];
  for (let d = 0; d < 18; d++) {
    const date = new Date(Date.now() - d * 86400000).toISOString().slice(0, 10);
    for (const [cid, base] of [["c1", 2600], ["c2", 3400], ["c3", 3900]] as const) {
      spend.push({ id: `${cid}-${d}`, campaign_id: cid, spend_date: date, amount: Math.round(base * (0.8 + rnd() * 0.4)), clicks: Math.round(base / 18) });
    }
  }
  const settings: Settings = {
    service_areas: ["bengaluru", "bangalore", "whitefield", "sarjapur", "hebbal", "devanahalli", "hennur", "varthur", "electronic city", "kanakapura road", "bellandur", "thanisandra"],
    accept_outstation: false, outstation_min_budget: 2500000, min_budget_full_home: 1500000, min_budget_kitchen: 300000,
    min_budget_wardrobes: 200000, min_budget_partial: 500000, budget_tolerance: 0.85, forward_temperatures: ["hot", "warm"],
    call_window_start: "10:00", call_window_end: "19:30", max_call_attempts: 4, max_parallel_calls: 3, nurture_recheck_days: 30,
    forward_whatsapp: ["+91 98450 00000"], forward_emails: ["sales@papilloninteriors.example"], report_emails: ["sachin@theingredientlist.co"],
  };
  const reports: ReportRow[] = [];
  return { leads, calls, events, campaigns, spend, projects, settings, reports, messagesBy };
}
