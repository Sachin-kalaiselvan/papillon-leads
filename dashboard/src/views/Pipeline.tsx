import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ease, Page, Temp } from "../components/ui";
import { api } from "../lib/api";
import { ago, budget, lakh } from "../lib/format";
import { useStore } from "../lib/store";
import { STAGES, type Lead, type Stage } from "../lib/types";

export function StageDialog({ lead, stage, onClose }: { lead: Lead; stage: Stage; onClose: (done: boolean) => void }) {
  const { reload } = useStore();
  const [value, setValue] = useState(String(lead.quote_value ?? ""));
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const needsValue = stage === "quotation_sent" || stage === "won";
  const title = STAGES.find((s) => s.key === stage)?.label;
  return (
    <motion.div className="scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => onClose(false)}>
      <motion.form className="dialog" initial={{ y: 30, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 20, opacity: 0 }}
        transition={{ ease, duration: 0.35 }} onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault(); setBusy(true);
          const n = Number(value.replace(/[^\d.]/g, ""));
          const v = n ? Math.round(n < 1000 ? n * 100000 : n) : null;
          await api.updateStage(lead.id, stage, { quote: stage === "quotation_sent" ? v : null, won: stage === "won" ? v : null,
                                                  lostReason: stage === "lost" ? reason : null, note });
          await reload(); setBusy(false); onClose(true);
        }}>
        <div className="kicker">{lead.ref} · {lead.name}</div>
        <h2>Move to {title}</h2>
        {needsValue && <label>{stage === "won" ? "Final project value" : "Quotation value"} (₹ or lakhs)
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="e.g. 18.5 or 1850000" autoFocus /></label>}
        {stage === "lost" && <label>Why was it lost?
          <select value={reason} onChange={(e) => setReason(e.target.value)} required>
            <option value="">Choose…</option>
            {["Went with another designer", "Price / budget mismatch", "Postponed the project", "Not responding", "Doing it themselves", "Other"].map((r) => <option key={r}>{r}</option>)}
          </select></label>}
        <label>Note (optional)<textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="What happened?" /></label>
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={() => onClose(false)}>Cancel</button>
          <button className="btn primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </motion.form>
    </motion.div>
  );
}

export default function Pipeline() {
  const { snap, reload } = useStore();
  const nav = useNavigate();
  const [filter, setFilter] = useState<"all" | "hot" | "warm">("all");
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const [pending, setPending] = useState<{ lead: Lead; stage: Stage } | null>(null);
  if (!snap) return <Page title="Pipeline"><div className="skeleton" /></Page>;
  const leads = snap.leads.filter((l) => l.stage !== "none" && (filter === "all" || l.temperature === filter));

  const drop = async (stage: Stage) => {
    const lead = leads.find((l) => l.id === drag);
    setDrag(null); setOver(null);
    if (!lead || lead.stage === stage) return;
    if (["quotation_sent", "won", "lost"].includes(stage)) { setPending({ lead, stage }); return; }
    await api.updateStage(lead.id, stage, {});
    await reload();
  };

  return (
    <Page title="Pipeline" kicker="Qualified leads with the studio"
      actions={<div className="seg">{(["all", "hot", "warm"] as const).map((f) => (
        <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
          {filter === f && <motion.span layoutId="seg-p" className="seg-on" />}<span>{f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)}</span>
        </button>))}</div>}>
      <p className="hint">Drag a card to move it. Every move is logged and counts in the weekly report.</p>
      <LayoutGroup>
        <div className="board">
          {STAGES.map((s, ci) => {
            const col = leads.filter((l) => l.stage === s.key).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
            const value = col.reduce((a, l) => a + (l.won_value || l.quote_value || 0), 0);
            return (
              <motion.div key={s.key} className={`lane ${over === s.key ? "over" : ""} lane-${s.key}`}
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: ci * 0.05, ease }}
                onDragOver={(e) => { e.preventDefault(); setOver(s.key); }} onDragLeave={() => setOver(null)} onDrop={() => drop(s.key)}>
                <div className="lane-head">
                  <span>{s.label}</span><b>{col.length}</b>
                  {value > 0 && <em>{lakh(value)}</em>}
                </div>
                <div className="lane-body">
                  <AnimatePresence>
                    {col.map((l) => (
                      <motion.article key={l.id} layout layoutId={`card-${l.id}`} className={`deal ${drag === l.id ? "dragging" : ""}`}
                        initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
                        transition={{ type: "spring", stiffness: 380, damping: 32 }} whileHover={{ y: -2 }}
                        draggable onDragStart={() => setDrag(l.id)} onDragEnd={() => { setDrag(null); setOver(null); }}
                        onClick={() => nav(`/leads/${l.id}`)}>
                        <div className="deal-top"><Temp t={l.temperature} /><span className="ref">{l.ref}</span></div>
                        <b>{l.name}</b>
                        <span className="deal-line">{l.configuration} · {l.project_name || l.locality}</span>
                        <div className="deal-foot">
                          <span>{l.won_value ? lakh(l.won_value) : l.quote_value ? `Quote ${lakh(l.quote_value)}` : budget(l)}</span>
                          <span>{ago(l.stage_updated_at || l.forwarded_at)}</span>
                        </div>
                        {l.lives_in && l.lives_in !== "Bengaluru" && <span className="tag">Lives in {l.lives_in}</span>}
                      </motion.article>
                    ))}
                  </AnimatePresence>
                  {col.length === 0 && <div className="lane-empty">—</div>}
                </div>
              </motion.div>
            );
          })}
        </div>
      </LayoutGroup>
      <AnimatePresence>{pending && <StageDialog {...pending} onClose={() => setPending(null)} />}</AnimatePresence>
    </Page>
  );
}
