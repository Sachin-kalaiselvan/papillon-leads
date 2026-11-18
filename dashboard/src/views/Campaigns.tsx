import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { ease, Page, rise, stagger } from "../components/ui";
import { api } from "../lib/api";
import { inr, istDate, label } from "../lib/format";
import { campaignTable } from "../lib/metrics";
import { useStore } from "../lib/store";

export default function Campaigns() {
  const { snap, reload } = useStore();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", source: "meta", audience: "" });
  const [spend, setSpend] = useState<Record<string, { date: string; amount: string }>>({});
  if (!snap) return <Page title="Campaigns"><div className="skeleton" /></Page>;
  const from = istDate(new Date(Date.now() - 29 * 86400000));
  const stats = new Map(campaignTable(snap, from, istDate()).map((r) => [r.id, r]));

  return (
    <Page title="Campaigns" kicker="Where enquiries come from · last 30 days"
      actions={<button className="btn primary" onClick={() => setAdding((a) => !a)}>{adding ? "Close" : "Add campaign"}</button>}>
      <AnimatePresence>
        {adding && (
          <motion.form className="card form-row" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ ease }}
            onSubmit={async (e) => {
              e.preventDefault();
              await api.addCampaign({ name: form.name, source: form.source, audience: form.audience || null, status: "active", started_on: istDate() });
              setForm({ name: "", source: "meta", audience: "" }); setAdding(false); await reload();
            }}>
            <label>Name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Meta · NRI Gulf" /></label>
            <label>Source<select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
              {["meta", "google", "website", "portal", "referral", "partner"].map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
            <label className="grow">Audience<input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} placeholder="Who it targets" /></label>
            <button className="btn primary">Save</button>
            <p className="muted small full">Meta and Google campaigns are also created automatically the first time a lead arrives from them — add spend here for cost-per-lead.</p>
          </motion.form>
        )}
      </AnimatePresence>
      <motion.div className="camps" variants={stagger} initial="hidden" animate="show">
        {snap.campaigns.map((c) => {
          const r = stats.get(c.id);
          const sp = spend[c.id] ?? { date: istDate(), amount: "" };
          return (
            <motion.section key={c.id} className="card camp" variants={rise} layout>
              <div className="camp-head"><span className={`src src-${c.source}`}>{label(c.source)}</span><h3>{c.name}</h3></div>
              {c.audience && <p className="muted">{c.audience}</p>}
              <div className="camp-nums">
                <div><b>{r?.enquiries ?? 0}</b><span>enquiries</span></div>
                <div><b>{(r?.hot ?? 0) + (r?.warm ?? 0)}</b><span>qualified</span></div>
                <div><b>{inr(r?.spend ?? 0)}</b><span>spend</span></div>
                <div><b>{r?.cpql ? inr(r.cpql) : "—"}</b><span>per qualified</span></div>
                <div><b>{r?.won ?? 0}</b><span>won</span></div>
              </div>
              <form className="spend" onSubmit={async (e) => {
                e.preventDefault();
                if (!sp.amount) return;
                await api.addSpend({ campaign_id: c.id, spend_date: sp.date, amount: Number(sp.amount), clicks: null });
                setSpend({ ...spend, [c.id]: { ...sp, amount: "" } }); await reload();
              }}>
                <input type="date" value={sp.date} onChange={(e) => setSpend({ ...spend, [c.id]: { ...sp, date: e.target.value } })} />
                <input inputMode="numeric" placeholder="Spend ₹" value={sp.amount} onChange={(e) => setSpend({ ...spend, [c.id]: { ...sp, amount: e.target.value } })} />
                <button className="btn ghost">Log spend</button>
              </form>
            </motion.section>
          );
        })}
      </motion.div>
    </Page>
  );
}
