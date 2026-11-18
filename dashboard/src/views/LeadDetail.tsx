import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ease, Page, rise, stagger, Temp } from "../components/ui";
import { api } from "../lib/api";
import { ago, budget, inr, label, place, when } from "../lib/format";
import { useStore } from "../lib/store";
import { STAGES, type Message, type Stage } from "../lib/types";
import { StageDialog } from "./Pipeline";

function ScoreRing({ score }: { score: number }) {
  const r = 30, c = 2 * Math.PI * r;
  return (
    <svg width="78" height="78" viewBox="0 0 78 78" className="ring">
      <circle cx="39" cy="39" r={r} className="ring-bg" />
      <motion.circle cx="39" cy="39" r={r} className="ring-fg" strokeDasharray={c}
        initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - score / 100) }} transition={{ duration: 1.2, ease }} />
      <text x="39" y="44" textAnchor="middle">{score}</text>
    </svg>
  );
}

export default function LeadDetail() {
  const { id } = useParams();
  const { snap, session } = useStore();
  const [tab, setTab] = useState<"calls" | "whatsapp" | "timeline">("calls");
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [pending, setPending] = useState<Stage | null>(null);
  const [openCall, setOpenCall] = useState<string | null>(null);
  const lead = snap?.leads.find((l) => l.id === id);
  useEffect(() => { if (id) api.messages(id).then(setMsgs).catch(() => setMsgs([])); }, [id, snap]);
  if (!snap) return <Page title="Lead"><div className="skeleton" /></Page>;
  if (!lead) return <Page title="Lead not found"><Link to="/leads">← Back to leads</Link></Page>;

  const calls = snap.calls.filter((c) => c.lead_id === lead.id);
  const events = snap.events.filter((e) => e.lead_id === lead.id);
  const firstOpen = openCall ?? calls.find((c) => c.transcript.length)?.id ?? null;
  const agency = session?.org === "agency";
  const stageIdx = STAGES.findIndex((s) => s.key === lead.stage);
  const fields: [string, string | null | undefined, boolean][] = [
    ["Property location", place(lead), !!(lead.locality || lead.project_name) && !!lead.city],
    ["Property type", label(lead.property_type), !!lead.property_type],
    ["Configuration", lead.configuration, !!lead.configuration],
    ["Area", lead.area_sqft ? `${lead.area_sqft.toLocaleString("en-IN")} sq ft` : null, !!lead.area_sqft],
    ["Possession", label(lead.possession_status), !!lead.possession_status && lead.possession_status !== "unknown"],
    ["Requirement", label(lead.scope) + (lead.scope_detail ? ` — ${lead.scope_detail}` : ""), !!lead.scope],
    ["Budget", budget(lead) + (lead.budget_said ? `  (“${lead.budget_said}”)` : ""), !!(lead.budget_min || lead.budget_max)],
    ["Timeline", label(lead.timeline), !!lead.timeline && lead.timeline !== "undecided"],
    ["Owner / decision-maker", label(lead.ownership), ["owner", "co_owner", "family_decision_maker", "authorised_representative"].includes(lead.ownership ?? "")],
    ["Consultation", lead.willing_consultation === false ? "Not yet" : [lead.consult_slot_said || when(lead.consult_slot), label(lead.consult_mode)].filter((x) => x && x !== "—").join(" · ") || null, !!lead.willing_consultation],
    ["Lives in", lead.lives_in, true],
    ["Other designers", lead.other_designers, true],
  ];

  return (
    <Page title={lead.name ?? lead.ref} kicker={`${lead.ref} · ${label(lead.source)} · arrived ${ago(lead.created_at)}`}
      actions={<div className="row">
        <a className="btn ghost" href={`tel:${lead.phone.replace(/\s/g, "")}`}>Call {lead.phone}</a>
        <a className="btn ghost" href={`https://wa.me/${lead.phone.replace(/\D/g, "")}`} target="_blank" rel="noreferrer">WhatsApp</a>
      </div>}>
      <motion.section className="lead-hero" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ ease }}>
        <div className="lh-left">
          <Temp t={lead.temperature} big />
          <div>
            <div className="lh-title">{lead.configuration}{lead.configuration?.toLowerCase().includes(label(lead.property_type).toLowerCase()) ? "" : ` ${label(lead.property_type).toLowerCase()}`} · {lead.project_name || lead.locality}</div>
            <div className="muted">{lead.status === "qualified" ? "Qualified" : label(lead.status)}{lead.disqualify_reason ? ` — ${lead.disqualify_reason}` : ""}
              {lead.qualified_at ? ` · qualified ${ago(lead.qualified_at)}` : ""}</div>
          </div>
        </div>
        {lead.score != null && <ScoreRing score={lead.score} />}
      </motion.section>

      {lead.stage !== "none" && (
        <motion.div className="stepper" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
          {STAGES.map((s, i) => (
            <button key={s.key} className={`step ${i <= stageIdx && lead.stage !== "lost" ? "done" : ""} ${lead.stage === s.key ? "cur" : ""} ${s.key}`}
              onClick={() => s.key !== lead.stage && setPending(s.key)}>
              {lead.stage === s.key && <motion.span layoutId="step-cur" className="step-cur" />}
              <span className="step-dot" /><span>{s.label}</span>
            </button>
          ))}
        </motion.div>
      )}
      {(lead.quote_value || lead.won_value || lead.lost_reason) && (
        <div className="money-line">
          {lead.quote_value && <span>Quotation <b>{inr(lead.quote_value)}</b></span>}
          {lead.won_value && <span>Won <b>{inr(lead.won_value)}</b></span>}
          {lead.lost_reason && <span>Lost — {lead.lost_reason}</span>}
        </div>
      )}

      <div className="detail-grid">
        <motion.div className="stack" variants={stagger} initial="hidden" animate="show">
          {lead.ai_summary && <motion.section className="card summary" variants={rise}><h3>In short</h3><p>{lead.ai_summary}</p></motion.section>}
          <motion.section className="card" variants={rise}>
            <h3>Requirement</h3>
            <dl className="facts">
              {fields.map(([k, v, ok]) => (
                <div key={k} className={ok ? "" : "missing"}>
                  <dt>{k}</dt><dd>{v && v !== "—" ? v : <i>not collected</i>}</dd>
                </div>
              ))}
            </dl>
          </motion.section>
          {lead.score_reasons.length > 0 && (
            <motion.section className="card" variants={rise}>
              <h3>Why it's {lead.temperature ?? "here"}</h3>
              <ul className="why">{lead.score_reasons.map((r) => <li key={r} className={r.startsWith("+") ? "plus" : "minus"}>{r.slice(2)}</li>)}</ul>
            </motion.section>
          )}
          {lead.notes && <motion.section className="card" variants={rise}><h3>Notes</h3><pre className="notes">{lead.notes}</pre></motion.section>}
          {agency && (
            <motion.section className="card meta" variants={rise}>
              <h3>Contact handling</h3>
              <p>Channel {lead.channel} · {lead.call_attempts} call attempt{lead.call_attempts === 1 ? "" : "s"}
                {lead.next_call_at ? ` · next try ${when(lead.next_call_at)}` : ""} · enquired {lead.enquiry_count}×</p>
            </motion.section>
          )}
        </motion.div>

        <motion.section className="card convo" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15, ease }}>
          <div className="tabs">
            {([["calls", `Calls (${calls.length})`], ["whatsapp", `WhatsApp (${msgs.filter((m) => m.channel === "whatsapp").length})`], ["timeline", "Timeline"]] as const).map(([k, t]) => (
              <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                {t}{tab === k && <motion.span layoutId="tab-line" className="tab-line" />}
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
              {tab === "calls" && (calls.length === 0 ? <p className="muted">No calls yet.</p> : calls.map((c) => (
                <div key={c.id} className="call">
                  <button className="call-head" onClick={() => setOpenCall(firstOpen === c.id ? "none" : c.id)}>
                    <span className={`cstat c-${c.status}`}>{label(c.status)}</span>
                    <span>Attempt {c.attempt} · {when(c.started_at)}</span>
                    <span>{c.duration_sec ? `${Math.floor(c.duration_sec / 60)}m ${c.duration_sec % 60}s` : ""}</span>
                  </button>
                  <AnimatePresence>
                    {firstOpen === c.id && (
                      <motion.div className="call-body" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ ease }}>
                        {c.recording_url && <audio controls src={c.recording_url} preload="none" />}
                        <div className="bubbles">
                          {c.transcript.map((t, i) => (
                            <motion.div key={i} className={`bubble ${t.role}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.025 }}>
                              {t.text}
                            </motion.div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )))}
              {tab === "whatsapp" && (msgs.filter((m) => m.channel === "whatsapp").length === 0 ? <p className="muted">No WhatsApp messages.</p> : (
                <div className="bubbles wa">
                  {msgs.filter((m) => m.channel === "whatsapp").map((m) => (
                    <div key={m.id} className={`bubble ${m.direction === "in" ? "user" : "assistant"}`}>{m.body}<time>{when(m.created_at)}</time></div>
                  ))}
                </div>
              ))}
              {tab === "timeline" && (
                <ol className="timeline">
                  {events.map((e) => (
                    <li key={e.id}><span className={`ev ev-${e.kind}`} /><div><b>{label(e.kind)}</b>
                      {e.kind === "stage" && <> → {label(String(e.detail.stage))}</>}
                      {e.detail.note ? <p>{String(e.detail.note)}</p> : null}
                      <span>{when(e.at)} · {e.actor}</span></div></li>
                  ))}
                </ol>
              )}
            </motion.div>
          </AnimatePresence>
        </motion.section>
      </div>
      <AnimatePresence>{pending && <StageDialog lead={lead} stage={pending} onClose={() => setPending(null)} />}</AnimatePresence>
    </Page>
  );
}
