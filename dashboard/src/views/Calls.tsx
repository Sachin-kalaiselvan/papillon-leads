import { motion } from "framer-motion";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, Counter, ease, Page, rise, stagger } from "../components/ui";
import { label, when } from "../lib/format";
import { since } from "../lib/metrics";
import { useStore } from "../lib/store";

export default function Calls() {
  const { snap, prefs } = useStore();
  const nav = useNavigate();
  const days = prefs.range;
  const data = useMemo(() => {
    if (!snap) return null;
    const calls = snap.calls.filter((c) => new Date(c.started_at).getTime() >= since(days));
    const answered = calls.filter((c) => c.answered_at);
    const avg = answered.length ? answered.reduce((a, c) => a + (c.duration_sec || 0), 0) / answered.length : 0;
    const outcomes = Object.entries(calls.reduce<Record<string, number>>((a, c) => {
      const k = c.answered_at ? c.outcome || "completed" : c.status;
      return { ...a, [k]: (a[k] || 0) + 1 };
    }, {})).sort((a, b) => b[1] - a[1]);
    const hours = Array.from({ length: 10 }, (_, i) => i + 10).map((h) => {
      const hc = calls.filter((c) => Number(new Date(c.started_at).toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" })) === h);
      return { h, n: hc.length, rate: hc.length ? hc.filter((c) => c.answered_at).length / hc.length : 0 };
    });
    return { calls, answered, avg, outcomes, hours };
  }, [snap, days]);
  if (!snap || !data) return <Page title="Calls"><div className="skeleton" /></Page>;
  const leads = new Map(snap.leads.map((l) => [l.id, l]));

  return (
    <Page title="Calls" kicker={`Automated qualification calls · last ${days} days`}>
      <motion.div className="kpis wide" variants={stagger} initial="hidden" animate="show">
        {[
          ["Calls placed", data.calls.length, ""], ["Answered", data.answered.length, ""],
          ["Answer rate", data.calls.length ? Math.round((100 * data.answered.length) / data.calls.length) : 0, "%"],
          ["Avg conversation", Math.round(data.avg), "s"],
        ].map(([k, v, u]) => (
          <motion.div key={k as string} className="kpi" variants={rise}>
            <div className="kpi-k">{k}</div><div className="kpi-v"><Counter value={v as number} />{u}</div>
          </motion.div>
        ))}
      </motion.div>
      <div className="grid-2">
        <section className="card">
          <h3>How calls ended</h3>
          <div className="reasons">
            {data.outcomes.map(([k, n], i) => (
              <div className="reason" key={k}><span>{label(k)}</span><Bar value={n} max={data.outcomes[0][1]} tone={k === "completed" ? "sage" : "clay"} delay={i * 0.06} /><b>{n}</b></div>
            ))}
          </div>
        </section>
        <section className="card">
          <h3>Answer rate by hour (IST)</h3>
          <div className="heat">
            {data.hours.map((h, i) => (
              <motion.div key={h.h} className="heat-cell" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04, ease }}
                style={{ background: `rgba(180,136,74,${0.08 + h.rate * 0.85})` }} title={`${h.n} calls`}>
                <b>{h.n ? Math.round(h.rate * 100) + "%" : "—"}</b><span>{h.h > 12 ? h.h - 12 : h.h}{h.h >= 12 ? "pm" : "am"}</span>
              </motion.div>
            ))}
          </div>
          <p className="muted small">Use this to move the calling window in Rules.</p>
        </section>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>When</th><th>Lead</th><th>Attempt</th><th>Result</th><th>Length</th><th>Summary</th></tr></thead>
          <tbody>
            {data.calls.slice(0, 200).map((c, i) => {
              const l = leads.get(c.lead_id);
              return (
                <motion.tr key={c.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i, 20) * 0.02, ease }} onClick={() => l && nav(`/leads/${l.id}`)}>
                  <td className="muted">{when(c.started_at)}</td>
                  <td><b>{l?.name}</b><span className="sub">{l?.ref}</span></td>
                  <td>{c.attempt}</td>
                  <td><span className={`cstat c-${c.status}`}>{label(c.answered_at ? c.outcome || "completed" : c.status)}</span></td>
                  <td className="num">{c.duration_sec ? `${Math.floor(c.duration_sec / 60)}:${String(c.duration_sec % 60).padStart(2, "0")}` : "—"}</td>
                  <td className="clip">{c.summary ?? ""}</td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Page>
  );
}
