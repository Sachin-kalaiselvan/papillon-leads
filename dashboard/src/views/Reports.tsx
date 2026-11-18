import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { ease, Page } from "../components/ui";
import { day, inr, istDate } from "../lib/format";
import { campaignTable, reached } from "../lib/metrics";
import { useStore } from "../lib/store";

const monday = (d: Date) => { const x = new Date(d); const w = (x.getDay() + 6) % 7; x.setDate(x.getDate() - w); return istDate(x); };
const addDays = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00+05:30"); d.setDate(d.getDate() + n); return istDate(d); };

export default function Reports() {
  const { snap } = useStore();
  const [week, setWeek] = useState(monday(new Date()));
  const [tab, setTab] = useState<"weekly" | "daily" | "sent">("weekly");
  const end = addDays(week, 6);
  const rows = useMemo(() => (snap ? campaignTable(snap, week, end) : []), [snap, week, end]);
  const daily = useMemo(() => {
    if (!snap) return [];
    return Array.from({ length: 7 }, (_, i) => addDays(istDate(), -i)).map((d) => {
      const ls = snap.leads.filter((l) => istDate(new Date(l.created_at)) === d);
      const fw = snap.leads.filter((l) => l.forwarded_at && istDate(new Date(l.forwarded_at)) === d);
      return { d, enquiries: ls.length, hot: fw.filter((l) => l.temperature === "hot").length, warm: fw.filter((l) => l.temperature === "warm").length,
               cold: ls.filter((l) => l.temperature === "cold").length,
               held: ls.filter((l) => ["disqualified", "out_of_area"].includes(l.status)).length,
               consultations: snap.leads.filter((l) => reached(l, "consultation_booked") && l.stage_updated_at && istDate(new Date(l.stage_updated_at)) === d).length, fw };
    });
  }, [snap]);
  if (!snap) return <Page title="Reports"><div className="skeleton" /></Page>;
  const tot = rows.reduce((a, r) => ({ spend: a.spend + r.spend, enquiries: a.enquiries + r.enquiries, hot: a.hot + r.hot, warm: a.warm + r.warm,
    cold: a.cold + r.cold, consultations: a.consultations + r.consultations, siteVisits: a.siteVisits + r.siteVisits, quotes: a.quotes + r.quotes,
    won: a.won + r.won, wonValue: a.wonValue + r.wonValue }), { spend: 0, enquiries: 0, hot: 0, warm: 0, cold: 0, consultations: 0, siteVisits: 0, quotes: 0, won: 0, wonValue: 0 });
  const q = tot.hot + tot.warm;

  return (
    <Page title="Reports" kicker="Daily leads · weekly campaign performance"
      actions={<div className="seg">{(["weekly", "daily", "sent"] as const).map((t) => (
        <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
          {tab === t && <motion.span layoutId="seg-r" className="seg-on" />}<span>{t === "sent" ? "Sent reports" : t[0].toUpperCase() + t.slice(1)}</span>
        </button>))}</div>}>
      {tab === "weekly" && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ ease }}>
          <div className="weekbar">
            <button className="btn ghost" onClick={() => setWeek(addDays(week, -7))}>←</button>
            <b>{day(week)} – {day(end)}</b>
            <button className="btn ghost" onClick={() => setWeek(addDays(week, 7))} disabled={week >= monday(new Date())}>→</button>
            <div className="weekstats">
              <span>Cost per qualified lead <b>{q ? inr(tot.spend / q) : "—"}</b></span>
              <span>Qualified rate <b>{tot.enquiries ? Math.round((100 * q) / tot.enquiries) : 0}%</b></span>
              <span>Won <b>{inr(tot.wonValue)}</b></span>
            </div>
          </div>
          <div className="table-wrap">
            <table className="table report">
              <thead><tr><th>Campaign</th><th>Spend</th><th>Enquiries</th><th>Cost / enquiry</th><th>Hot</th><th>Warm</th><th>Cold</th>
                <th>Cost / qualified</th><th>Consults</th><th>Site visits</th><th>Quotes</th><th>Won</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <motion.tr key={r.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05, ease }}>
                    <td><b>{r.name}</b></td><td className="num">{inr(r.spend)}</td><td className="num">{r.enquiries}</td>
                    <td className="num">{r.cpl ? inr(r.cpl) : "—"}</td><td className="num hotc">{r.hot}</td><td className="num warmc">{r.warm}</td>
                    <td className="num coldc">{r.cold}</td><td className="num"><b>{r.cpql ? inr(r.cpql) : "—"}</b></td>
                    <td className="num">{r.consultations}</td><td className="num">{r.siteVisits}</td><td className="num">{r.quotes}</td>
                    <td className="num">{r.won}{r.wonValue ? <span className="sub">{inr(r.wonValue)}</span> : null}</td>
                  </motion.tr>
                ))}
                <tr className="total"><td>Total</td><td className="num">{inr(tot.spend)}</td><td className="num">{tot.enquiries}</td>
                  <td className="num">{tot.enquiries ? inr(tot.spend / tot.enquiries) : "—"}</td><td className="num">{tot.hot}</td><td className="num">{tot.warm}</td>
                  <td className="num">{tot.cold}</td><td className="num">{q ? inr(tot.spend / q) : "—"}</td><td className="num">{tot.consultations}</td>
                  <td className="num">{tot.siteVisits}</td><td className="num">{tot.quotes}</td><td className="num">{tot.won}</td></tr>
              </tbody>
            </table>
          </div>
          <p className="muted small">Leads are counted in the week they arrived; stages show where each one stands today. The same report is emailed every Monday at 9 am.</p>
        </motion.div>
      )}
      {tab === "daily" && (
        <div className="days">
          {daily.map((d, i) => (
            <motion.section key={d.d} className="card day" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, ease }}>
              <div className="day-head"><h3>{day(d.d)}</h3>
                <div className="day-nums"><span>{d.enquiries} enquiries</span><span className="hotc">{d.hot} hot</span><span className="warmc">{d.warm} warm</span>
                  <span className="coldc">{d.cold} cold</span><span>{d.held} held back</span><span>{d.consultations} consultations</span></div></div>
              {d.fw.length > 0 && <ul className="day-list">{d.fw.map((l) => <li key={l.id}><b>{l.ref}</b> {l.name} — {l.configuration}, {l.project_name || l.locality} · {l.temperature}</li>)}</ul>}
            </motion.section>
          ))}
        </div>
      )}
      {tab === "sent" && (
        snap.reports.length === 0 ? <p className="muted">Reports appear here once the server sends its first daily report (8 pm IST).</p> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Report</th><th>Period</th><th>Headline</th><th>Sent to</th></tr></thead>
            <tbody>{snap.reports.map((r) => (
              <tr key={r.id}><td><b>{r.kind === "daily" ? "Daily" : "Weekly"}</b></td><td>{day(r.period_start)}{r.kind === "weekly" ? ` – ${day(r.period_end)}` : ""}</td>
                <td>{r.kind === "daily" ? `${r.data.enquiries} enquiries · ${r.data.hot} hot · ${r.data.warm} warm` : `${r.data.totals?.enquiries} enquiries · ${(r.data.totals?.hot ?? 0) + (r.data.totals?.warm ?? 0)} qualified · ${r.data.totals?.won} won`}</td>
                <td className="muted">{r.sent_to.join(", ")}</td></tr>))}</tbody>
          </table></div>
        )
      )}
    </Page>
  );
}
