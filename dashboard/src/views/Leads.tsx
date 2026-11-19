import { motion } from "framer-motion";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ease, Empty, Page, Temp } from "../components/ui";
import { ago, budget, label } from "../lib/format";
import { useStore } from "../lib/store";
import type { Lead } from "../lib/types";

const FILTERS: { k: string; label: string; test: (l: Lead) => boolean; agency?: boolean }[] = [
  { k: "all", label: "All", test: () => true },
  { k: "hot", label: "Hot", test: (l) => l.status === "qualified" && l.temperature === "hot" },
  { k: "warm", label: "Warm", test: (l) => l.status === "qualified" && l.temperature === "warm" },
  { k: "cold", label: "Cold", test: (l) => l.temperature === "cold", agency: true },
  { k: "working", label: "In conversation", test: (l) => ["new", "queued", "calling", "qualifying"].includes(l.status), agency: true },
  { k: "unreachable", label: "Unreachable", test: (l) => l.status === "unreachable", agency: true },
  { k: "held", label: "Not a fit", test: (l) => ["disqualified", "out_of_area", "do_not_contact"].includes(l.status), agency: true },
];

export default function Leads() {
  const { snap, prefs, setPref, session } = useStore();
  const nav = useNavigate();
  const agency = session?.org === "agency";
  const filters = FILTERS.filter((f) => agency || !f.agency);
  const counts = useMemo(() => Object.fromEntries(filters.map((f) => [f.k, snap?.leads.filter(f.test).length ?? 0])), [snap, filters]);
  const rows = useMemo(() => {
    if (!snap) return [];
    const f = filters.find((x) => x.k === prefs.leadFilter) ?? filters[0];
    const q = prefs.leadSearch.trim().toLowerCase();
    return snap.leads.filter(f.test)
      .filter((l) => prefs.leadSource === "all" || l.source === prefs.leadSource)
      .filter((l) => !q || [l.name, l.phone, l.ref, l.project_name, l.locality, l.city, l.lives_in].some((x) => x?.toLowerCase().includes(q)));
  }, [snap, prefs, filters]);
  if (!snap) return <Page title="Leads"><div className="skeleton" /></Page>;
  const sources = [...new Set(snap.leads.map((l) => l.source))];

  return (
    <Page title="Leads" kicker={`${snap.leads.length} on record`}
      actions={<input className="search" placeholder="Search name, phone, project…" value={prefs.leadSearch} onChange={(e) => setPref("leadSearch", e.target.value)} />}>
      <div className="chips">
        {filters.map((f) => (
          <button key={f.k} className={`chip ${prefs.leadFilter === f.k ? "on" : ""}`} onClick={() => setPref("leadFilter", f.k)}>
            {prefs.leadFilter === f.k && <motion.span layoutId="chip" className="chip-on" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
            <span>{f.label}</span><em>{counts[f.k]}</em>
          </button>
        ))}
        <select className="chip-select" value={prefs.leadSource} onChange={(e) => setPref("leadSource", e.target.value)}>
          <option value="all">All sources</option>
          {sources.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
      </div>
      {rows.length === 0 ? <Empty>No leads match this view.</Empty> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Lead</th><th>Class</th><th>Property</th><th>Need</th><th>Budget</th><th>Timeline</th><th>Status</th><th>Arrived</th></tr></thead>
            <tbody>
              {rows.slice(0, 300).map((l, i) => (
                <motion.tr key={l.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 20) * 0.02, ease }}
                  onClick={() => nav(`/leads/${l.id}`)}>
                  <td><b>{l.name ?? "—"}</b><span className="sub">{l.ref} · {l.lives_in && l.lives_in !== l.city ? `lives in ${l.lives_in}` : l.phone}</span></td>
                  <td><Temp t={l.status === "qualified" || l.status === "nurture" ? l.temperature : null} /></td>
                  <td>{l.configuration ?? "—"}<span className="sub">{l.project_name || l.locality || "—"}{l.city && l.city !== "Bengaluru" ? `, ${l.city}` : ""}</span></td>
                  <td>{label(l.scope)}</td>
                  <td className="num">{budget(l)}</td>
                  <td>{label(l.timeline)}</td>
                  <td><span className={`status s-${l.status}`}>{l.stage !== "none" ? label(l.stage === "forwarded" ? "With studio" : l.stage) : label(l.status)}</span>
                    {l.disqualify_reason && <span className="sub">{l.disqualify_reason}</span>}</td>
                  <td className="muted">{ago(l.created_at)}<span className="sub">{label(l.source)}</span></td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Page>
  );
}
