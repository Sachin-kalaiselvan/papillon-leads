import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { ease, Page } from "../components/ui";
import { api } from "../lib/api";
import { day } from "../lib/format";
import { useStore } from "../lib/store";
import type { Settings } from "../lib/types";

const L = (v: number) => String(v / 100000);

function Tags({ value, onChange, placeholder, cap }: { value: string[]; onChange: (v: string[]) => void; placeholder: string; cap?: boolean }) {
  const [t, setT] = useState("");
  return (
    <div className={`tags ${cap ? "cap" : ""}`}>
      <AnimatePresence>
        {value.map((v) => (
          <motion.span key={v} className="tagx" layout initial={{ scale: 0.7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.7, opacity: 0 }}>
            {v}<button type="button" onClick={() => onChange(value.filter((x) => x !== v))}>×</button>
          </motion.span>
        ))}
      </AnimatePresence>
      <input value={t} placeholder={placeholder} onChange={(e) => setT(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && t.trim()) { e.preventDefault(); onChange([...new Set([...value, t.trim()])]); setT(""); } }} />
    </div>
  );
}

export default function SettingsView() {
  const { snap, reload } = useStore();
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const [proj, setProj] = useState({ name: "", locality: "", from: "", to: "" });
  useEffect(() => { if (snap?.settings) setS(snap.settings); }, [snap?.settings]);
  if (!snap || !s) return <Page title="Rules"><div className="skeleton" /></Page>;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setS({ ...s, [k]: v });
  const money = (k: keyof Settings, lbl: string) => (
    <label>{lbl}<div className="unit"><span>₹</span><input inputMode="decimal" value={L(s[k] as number)}
      onChange={(e) => set(k, Math.round(Number(e.target.value || 0) * 100000) as never)} /><span>lakh</span></div></label>
  );

  return (
    <Page title="Rules" kicker="What counts as a qualified lead"
      actions={<button className="btn primary" onClick={async () => { await api.saveSettings(s); await reload(); setSaved(true); setTimeout(() => setSaved(false), 1800); }}>
        <AnimatePresence mode="wait"><motion.span key={String(saved)} initial={{ y: 8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -8, opacity: 0 }}>{saved ? "Saved ✓" : "Save rules"}</motion.span></AnimatePresence>
      </button>}>
      <div className="settings">
        <motion.section className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ease }}>
          <h3>Minimum indicative budget</h3>
          <div className="form-grid">
            {money("min_budget_full_home", "Complete home / turnkey")}
            {money("min_budget_kitchen", "Modular kitchen only")}
            {money("min_budget_wardrobes", "Wardrobes only")}
            {money("min_budget_partial", "Partial interiors")}
            <label>“Reasonably aligned” allowance<div className="unit"><input inputMode="numeric" value={Math.round(s.budget_tolerance * 100)}
              onChange={(e) => set("budget_tolerance", Number(e.target.value) / 100)} /><span>% of minimum</span></div></label>
          </div>
        </motion.section>

        <motion.section className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05, ease }}>
          <h3>Where Papillon takes projects</h3>
          <p className="muted small">Matched against the property's city, locality and project. Buyers can live anywhere — only the property location is checked.</p>
          <Tags cap value={s.service_areas} onChange={(v) => set("service_areas", v.map((x) => x.toLowerCase()))} placeholder="Add a city or locality, press Enter" />
          <label className="switch"><input type="checkbox" checked={s.accept_outstation} onChange={(e) => set("accept_outstation", e.target.checked)} />
            <span className="track"><motion.span className="knob" layout /></span> Accept projects outside these areas</label>
          {s.accept_outstation && money("outstation_min_budget", "Minimum budget for outstation projects")}
        </motion.section>

        <motion.section className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, ease }}>
          <h3>Forwarding</h3>
          <div className="checks">
            {(["hot", "warm", "cold"] as const).map((t) => (
              <label key={t} className={`check ${t}`}><input type="checkbox" checked={s.forward_temperatures.includes(t)}
                onChange={(e) => set("forward_temperatures", e.target.checked ? [...s.forward_temperatures, t] : s.forward_temperatures.filter((x) => x !== t))} />Forward {t}</label>
            ))}
          </div>
          <label>Studio WhatsApp numbers<Tags value={s.forward_whatsapp} onChange={(v) => set("forward_whatsapp", v)} placeholder="+91…" /></label>
          <label>Studio emails<Tags value={s.forward_emails} onChange={(v) => set("forward_emails", v)} placeholder="name@papillon…" /></label>
          <label>Report emails<Tags value={s.report_emails} onChange={(v) => set("report_emails", v)} placeholder="Daily + weekly reports" /></label>
        </motion.section>

        <motion.section className="card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, ease }}>
          <h3>Calling</h3>
          <div className="form-grid">
            <label>Calls from<input type="time" value={s.call_window_start.slice(0, 5)} onChange={(e) => set("call_window_start", e.target.value)} /></label>
            <label>Calls until<input type="time" value={s.call_window_end.slice(0, 5)} onChange={(e) => set("call_window_end", e.target.value)} /></label>
            <label>Attempts before “unreachable”<input type="number" min={1} max={8} value={s.max_call_attempts} onChange={(e) => set("max_call_attempts", Number(e.target.value))} /></label>
            <label>Calls at the same time<input type="number" min={1} max={20} value={s.max_parallel_calls} onChange={(e) => set("max_parallel_calls", Number(e.target.value))} /></label>
            <label>Re-check cold leads after (days)<input type="number" min={7} value={s.nurture_recheck_days} onChange={(e) => set("nurture_recheck_days", Number(e.target.value))} /></label>
          </div>
        </motion.section>

        <motion.section className="card wide" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, ease }}>
          <h3>Projects in handover</h3>
          <p className="muted small">Leads from these projects get priority, and these are the projects to point ads at.</p>
          <table className="table compact"><thead><tr><th>Project</th><th>Locality</th><th>Possession window</th><th /></tr></thead>
            <tbody>
              {snap.projects.map((p) => (
                <tr key={p.id}><td><b>{p.name}</b></td><td>{p.locality}</td>
                  <td>{p.possession_from ? day(p.possession_from) : "—"} – {p.possession_to ? day(p.possession_to) : "—"}</td>
                  <td><button className="link" onClick={async () => { await api.removeProject(p.id); await reload(); }}>Remove</button></td></tr>
              ))}
            </tbody></table>
          <form className="form-row" onSubmit={async (e) => {
            e.preventDefault();
            await api.addProject({ name: proj.name, builder: null, locality: proj.locality || null, possession_from: proj.from || null, possession_to: proj.to || null });
            setProj({ name: "", locality: "", from: "", to: "" }); await reload();
          }}>
            <input required placeholder="Project name" value={proj.name} onChange={(e) => setProj({ ...proj, name: e.target.value })} />
            <input placeholder="Locality" value={proj.locality} onChange={(e) => setProj({ ...proj, locality: e.target.value })} />
            <input type="date" value={proj.from} onChange={(e) => setProj({ ...proj, from: e.target.value })} />
            <input type="date" value={proj.to} onChange={(e) => setProj({ ...proj, to: e.target.value })} />
            <button className="btn ghost">Add</button>
          </form>
        </motion.section>
      </div>
    </Page>
  );
}
