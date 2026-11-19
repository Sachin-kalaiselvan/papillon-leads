// Papillon website enquiry form → lead pipeline.
// Drop into the Papillon site and render <EnquiryForm /> on the consultation page / contact section.
// Set VITE_LEADS_API=https://leadsapi.papilloninteriors.in in the site's Vercel env vars.
import { useEffect, useState, type FormEvent } from "react";

const API = (import.meta as any).env?.VITE_LEADS_API ?? "https://leadsapi.papilloninteriors.in";
const CONSENT =
  "I agree that Papillon Interiors may message me on WhatsApp (including an automated assistant) and call me about my interiors enquiry.";

const SCOPES = ["Complete home interiors", "Turnkey project", "Modular kitchen", "Wardrobes", "A few rooms"];
const BUDGETS = ["Under ₹10 lakh", "₹10–15 lakh", "₹15–25 lakh", "₹25–40 lakh", "Above ₹40 lakh"];
const POSSESSION = ["Already received", "Within 3 months", "3–6 months", "6–12 months", "More than a year"];
const COUNTRIES = [["IN", "+91 India"], ["AE", "+971 UAE"], ["US", "+1 USA"], ["GB", "+44 UK"], ["SG", "+65 Singapore"],
  ["QA", "+974 Qatar"], ["SA", "+966 Saudi Arabia"], ["AU", "+61 Australia"], ["CA", "+1 Canada"]];
const BUDGET_VALUE: Record<string, string> = {
  "Under ₹10 lakh": "under 10 lakhs", "₹10–15 lakh": "10-15 lakhs", "₹15–25 lakh": "15-25 lakhs",
  "₹25–40 lakh": "25-40 lakhs", "Above ₹40 lakh": "above 40 lakhs",
};

export default function EnquiryForm() {
  const [f, setF] = useState({ name: "", phone: "", country: "IN", email: "", project: "", locality: "", configuration: "3 BHK",
    scope: SCOPES[0], budget: "", possession: "", company_website: "" });
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");
  const [utm, setUtm] = useState<Record<string, string>>({});

  useEffect(() => {
    const q = new URLSearchParams(location.search);
    const u: Record<string, string> = {};
    ["utm_source", "utm_medium", "utm_campaign", "utm_content", "gclid", "fbclid"].forEach((k) => { const v = q.get(k); if (v) u[k] = v; });
    setUtm(u);
  }, []);

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!consent) { setMsg("Please tick the box so our team can call you."); return; }
    setState("sending"); setMsg("");
    try {
      const r = await fetch(`${API}/intake/web`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...f, city: "Bengaluru", budget: BUDGET_VALUE[f.budget] ?? f.budget, consent: true,
                               consent_text: CONSENT, utm, page: location.pathname }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Something went wrong");
      setState("done");
    } catch (err) {
      setState("error"); setMsg((err as Error).message === "invalid phone number" ? "Please check the phone number." : "Couldn't send — please try again.");
    }
  }

  if (state === "done") {
    return (
      <div className="pap-enquiry pap-done">
        <h3>Thank you, {f.name.split(" ")[0] || "there"}.</h3>
        <p>We'll message you on WhatsApp shortly to understand your home, and a designer will follow up.</p>
      </div>
    );
  }

  return (
    <form className="pap-enquiry" onSubmit={submit} noValidate>
      <div className="pap-grid">
        <label>Your name<input required value={f.name} onChange={set("name")} autoComplete="name" /></label>
        <label>Mobile number
          <div className="pap-phone">
            <select value={f.country} onChange={set("country")} aria-label="Country code">
              {COUNTRIES.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
            <input required inputMode="tel" value={f.phone} onChange={set("phone")} autoComplete="tel-national" />
          </div>
        </label>
        <label>Email (optional)<input type="email" value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label>Project / society name<input value={f.project} onChange={set("project")} placeholder="e.g. your apartment project" /></label>
        <label>Locality in Bengaluru<input value={f.locality} onChange={set("locality")} placeholder="e.g. Sarjapur Road" /></label>
        <label>Home
          <select value={f.configuration} onChange={set("configuration")}>
            {["2 BHK", "3 BHK", "4 BHK", "Villa", "Independent house", "Penthouse"].map((x) => <option key={x}>{x}</option>)}
          </select>
        </label>
        <label>What do you need?
          <select value={f.scope} onChange={set("scope")}>{SCOPES.map((x) => <option key={x}>{x}</option>)}</select>
        </label>
        <label>Interior budget
          <select value={f.budget} onChange={set("budget")}><option value="">Choose a range</option>{BUDGETS.map((x) => <option key={x}>{x}</option>)}</select>
        </label>
        <label>Possession
          <select value={f.possession} onChange={set("possession")}><option value="">Choose</option>{POSSESSION.map((x) => <option key={x}>{x}</option>)}</select>
        </label>
        {/* honeypot: hidden from people, bots fill it */}
        <input className="pap-hp" tabIndex={-1} autoComplete="off" value={f.company_website} onChange={set("company_website")} aria-hidden />
      </div>
      <label className="pap-consent">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>{CONSENT}</span>
      </label>
      {msg && <p className="pap-msg">{msg}</p>}
      <button disabled={state === "sending"}>{state === "sending" ? "Sending…" : "Book a free design consultation"}</button>
      <style>{`
        .pap-enquiry{display:flex;flex-direction:column;gap:16px;max-width:720px}
        .pap-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
        .pap-enquiry label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:600}
        .pap-enquiry input,.pap-enquiry select{padding:12px 14px;border:1px solid #d9cfc1;border-radius:10px;font:inherit;background:#fff}
        .pap-phone{display:flex;gap:6px}.pap-phone select{width:130px}.pap-phone input{flex:1;min-width:0}
        .pap-consent{flex-direction:row!important;align-items:flex-start;gap:10px!important;font-weight:400!important;font-size:12px!important;line-height:1.5}
        .pap-consent input{margin-top:3px}
        .pap-hp{position:absolute;left:-9999px;opacity:0;height:0;width:0}
        .pap-msg{color:#b3402c;margin:0;font-size:13px}
        .pap-enquiry button{align-self:flex-start;padding:14px 26px;border:0;border-radius:999px;background:#1e1a22;color:#fbf8f3;font-weight:700;cursor:pointer}
        .pap-enquiry button:disabled{opacity:.6}
        .pap-done h3{margin:0;font-size:24px}
      `}</style>
    </form>
  );
}
