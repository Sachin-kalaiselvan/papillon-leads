import { AnimatePresence, motion } from "framer-motion";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, Counter, ease, Page, rise, stagger, Temp } from "../components/ui";
import { ago, budget, day, label, lakh } from "../lib/format";
import { byDay, inRange, summary } from "../lib/metrics";
import { useStore } from "../lib/store";

const EVENT_TEXT: Record<string, string> = {
  created: "New enquiry", whatsapp_reminder: "WhatsApp reminder sent", scored: "Assessed",
  forwarded: "Sent to the studio", stage: "Stage moved", whatsapp_intro: "WhatsApp opened",
  whatsapp_missed_call: "Missed call — WhatsApp sent", unreachable: "Unreachable after retries",
  call_retry_scheduled: "Retry scheduled", repeat_enquiry: "Enquired again", details: "Details captured",
  conversation_end: "Conversation ended",
};

export default function Overview() {
  const { snap, prefs, setPref, session } = useStore();
  const nav = useNavigate();
  const agency = session?.org === "agency";
  const days = prefs.range;
  const m = useMemo(() => (snap ? summary(snap, days) : null), [snap, days]);
  const series = useMemo(() => (snap ? byDay(inRange(snap.leads, days), days) : []), [snap, days]);
  const leadsById = useMemo(() => new Map(snap?.leads.map((l) => [l.id, l]) ?? []), [snap]);
  if (!snap || !m) return <Page title="Overview"><div className="skeleton" /></Page>;

  const qualified = m.hot + m.warm;
  const waiting = snap.leads.filter((l) => l.stage === "forwarded")
    .sort((a, b) => (a.temperature === "hot" ? -1 : 1) - (b.temperature === "hot" ? -1 : 1) || (b.score ?? 0) - (a.score ?? 0)).slice(0, 6);
  const funnel = [
    { k: "Enquiries", v: m.enquiries },
    { k: "Messaged", v: m.contacted },
    { k: "Replied & assessed", v: m.assessed },
    { k: "Qualified", v: qualified },
    { k: "Consultations", v: m.consultations },
    { k: "Site visits", v: m.siteVisits },
    { k: "Quotations", v: m.quotes },
    { k: "Won", v: m.won },
  ];
  const reasons = Object.entries(inRange(snap.leads, days)
    .filter((l) => l.disqualify_reason)
    .reduce<Record<string, number>>((a, l) => ({ ...a, [l.disqualify_reason!]: (a[l.disqualify_reason!] || 0) + 1 }), {}))
    .sort((a, b) => b[1] - a[1]);
  const maxDay = Math.max(1, ...series.map((d) => d.total));

  return (
    <Page title="Overview" kicker={agency ? "Lead operations" : "Papillon studio"}
      actions={
        <div className="seg">
          {[7, 14, 30].map((d) => (
            <button key={d} className={days === d ? "on" : ""} onClick={() => setPref("range", d as 7 | 14 | 30)}>
              {days === d && <motion.span layoutId="seg" className="seg-on" />}<span>{d} days</span>
            </button>
          ))}
        </div>
      }>
      <motion.section className="hero" variants={stagger} initial="hidden" animate="show">
        <motion.div className="hero-main" variants={rise}>
          <div className="hero-num"><Counter value={qualified} /></div>
          <div className="hero-copy">
            <b>qualified homeowners</b> in the last {days} days
            <span>from {m.enquiries} enquiries · {m.enquiries ? Math.round((100 * qualified) / m.enquiries) : 0}% made the cut</span>
          </div>
          <svg className="hero-wave" viewBox="0 0 600 120" preserveAspectRatio="none">
            <motion.path d={wave(series.map((d) => d.qualified), 600, 120)} fill="none" stroke="currentColor" strokeWidth="2"
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, ease }} />
          </svg>
        </motion.div>
        <motion.div className="kpis" variants={stagger}>
          {[
            { k: "Hot", v: m.hot, cls: "hot" }, { k: "Warm", v: m.warm, cls: "warm" }, { k: "Cold · nurturing", v: m.cold, cls: "cold" },
            { k: "Assessed on WhatsApp", v: m.assessed, sub: `of ${m.contacted} messaged` }, { k: "Consultations", v: m.consultations },
            { k: "Won", v: m.wonValue, money: true, sub: `${m.won} projects` },
          ].map((c) => (
            <motion.div key={c.k} className={`kpi ${c.cls ?? ""}`} variants={rise} whileHover={{ y: -3 }}>
              <div className="kpi-k">{c.k}</div>
              <div className="kpi-v">{c.money ? <Counter value={c.v} format={(n) => lakh(Math.round(n / 10000) * 10000)} /> : <Counter value={c.v} />}</div>
              {c.sub && <div className="kpi-s">{c.sub}</div>}
            </motion.div>
          ))}
        </motion.div>
      </motion.section>

      <div className="grid-2">
        <motion.section className="card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, ease }}>
          <h3>From enquiry to project</h3>
          <div className="funnel">
            {funnel.map((f, i) => (
              <div className="funnel-row" key={f.k}>
                <span className="funnel-k">{f.k}</span>
                <Bar value={f.v} max={funnel[0].v} tone={i < 3 ? "ink" : i === 3 ? "brass" : "sage"} delay={0.3 + i * 0.07} />
                <span className="funnel-v">{f.v}</span>
                <span className="funnel-p">{i ? `${funnel[i - 1].v ? Math.round((100 * f.v) / funnel[i - 1].v) : 0}%` : ""}</span>
              </div>
            ))}
          </div>
        </motion.section>

        <motion.section className="card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.32, ease }}>
          <h3>Enquiries per day <span className="legend"><i className="lg-total" />all <i className="lg-q" />qualified</span></h3>
          <div className="cols">
            {series.map((d, i) => (
              <div className="col" key={d.date} title={`${day(d.date)}: ${d.total} enquiries, ${d.qualified} qualified`}>
                <div className="col-stack">
                  <motion.div className="col-total" initial={{ height: 0 }} animate={{ height: `${(100 * d.total) / maxDay}%` }} transition={{ delay: 0.3 + i * 0.03, duration: 0.7, ease }} />
                  <motion.div className="col-q" initial={{ height: 0 }} animate={{ height: `${(100 * d.qualified) / maxDay}%` }} transition={{ delay: 0.45 + i * 0.03, duration: 0.7, ease }} />
                </div>
                {(series.length <= 14 || i % 3 === 0) && <span>{day(d.date).split(" ")[0]}</span>}
              </div>
            ))}
          </div>
        </motion.section>
      </div>

      <div className="grid-2">
        <motion.section className="card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.38, ease }}>
          <h3>Waiting for the studio's first call <Link to="/pipeline" className="more">Pipeline →</Link></h3>
          {waiting.length === 0 && <p className="muted">Nothing waiting. Every qualified lead has been picked up.</p>}
          <motion.ul className="waitlist" variants={stagger} initial="hidden" animate="show">
            {waiting.map((l) => (
              <motion.li key={l.id} variants={rise} whileHover={{ x: 4 }} onClick={() => nav(`/leads/${l.id}`)}>
                <Temp t={l.temperature} />
                <div className="wl-main">
                  <b>{l.name}</b>
                  <span>{l.configuration} · {l.project_name || l.locality} · {label(l.scope)}</span>
                </div>
                <div className="wl-side"><b>{budget(l)}</b><span>{ago(l.forwarded_at)}</span></div>
              </motion.li>
            ))}
          </motion.ul>
        </motion.section>

        <motion.section className="card feed" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.44, ease }}>
          <h3>Live activity <span className="pulse" /></h3>
          <ul>
            <AnimatePresence initial={false}>
              {snap.events.slice(0, 11).map((e) => {
                const l = leadsById.get(e.lead_id);
                return (
                  <motion.li key={e.id} layout initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ ease }}
                    onClick={() => l && nav(`/leads/${l.id}`)}>
                    <span className={`ev ev-${e.kind}`} />
                    <div><b>{EVENT_TEXT[e.kind] ?? e.kind}</b>{e.kind === "stage" && ` → ${label(String(e.detail.stage))}`}
                      <span>{l?.name ?? "—"} · {l?.ref}</span></div>
                    <time>{ago(e.at)}</time>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
        </motion.section>
      </div>

      {agency && reasons.length > 0 && (
        <motion.section className="card" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5, ease }}>
          <h3>Why enquiries were held back</h3>
          <div className="reasons">
            {reasons.map(([r, n], i) => (
              <div key={r} className="reason"><span>{r}</span><Bar value={n} max={reasons[0][1]} tone="clay" delay={0.5 + i * 0.06} /><b>{n}</b></div>
            ))}
          </div>
        </motion.section>
      )}
    </Page>
  );
}

function wave(vals: number[], w: number, h: number) {
  if (vals.length < 2) return `M0 ${h} L${w} ${h}`;
  const max = Math.max(1, ...vals);
  const pts = vals.map((v, i) => [(i / (vals.length - 1)) * w, h - 12 - (v / max) * (h - 24)]);
  return pts.reduce((d, [x, y], i) => {
    if (!i) return `M${x} ${y}`;
    const [px, py] = pts[i - 1];
    const cx = (px + x) / 2;
    return `${d} C${cx} ${py} ${cx} ${y} ${x} ${y}`;
  }, "");
}
