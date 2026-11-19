import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ease, Empty, Page, rise, stagger } from "../components/ui";
import { api } from "../lib/api";
import { ago, day } from "../lib/format";
import type { CrawlState, Prospect, ProspectKind, ProspectStatus } from "../lib/types";

const TABS: { k: ProspectKind; label: string; hint: string }[] = [
  { k: "post", label: "People asking", hint: "Public posts from people looking for an interior designer. Reply on the post itself." },
  { k: "partner", label: "Referral partners", hint: "Builders, agents, property managers and apartment associations — one tie-up can send many homeowners." },
  { k: "project", label: "Projects being built", hint: "Residential projects under construction. Add the ones nearing handover to target ads and prioritise their leads." },
];
const STATUS: { k: ProspectStatus; label: string }[] = [
  { k: "new", label: "New" }, { k: "contacted", label: "Contacted" }, { k: "interested", label: "Interested" },
  { k: "partner", label: "Partner" }, { k: "added", label: "Added" }, { k: "not_relevant", label: "Not relevant" },
];
const TAB_KEY = "papillon-prospect-tab";

function Radar({ state }: { state: CrawlState["partners"] }) {
  const max = state?.max_ring_km ?? 60;
  const rings = state?.rings ?? [];
  const done = new Set(rings.map((r) => r.km));
  const next = state?.next_ring_km ?? 5;
  const R = 110;
  return (
    <div className="radar">
      <svg viewBox="-125 -125 250 250" width="250" height="250">
        {Array.from({ length: max / 5 }, (_, i) => (i + 1) * 5).reverse().map((km, i) => (
          <motion.circle key={km} r={(km / max) * R} className={done.has(km) ? "rr done" : km === next ? "rr next" : "rr"}
            initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.03 * i, duration: 0.6, ease }} />
        ))}
        <g className="sweep-g"><line x1="0" y1="0" x2="0" y2={-R} className="sweep" /></g>
        <circle r="4" className="core" />
      </svg>
      <div className="radar-legend">
        <b>{Math.max(0, next - 5)} km</b> covered of {max} km · pass {state?.cycle ?? 1}
        <span>Next ring: {next} km{state?.last_run ? ` · last run ${ago(state.last_run)}` : ""}</span>
      </div>
    </div>
  );
}

function ProjectDialog({ p, onClose }: { p: Prospect; onClose: (saved: boolean) => void }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  return (
    <motion.div className="scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => onClose(false)}>
      <motion.form className="dialog" initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }} transition={{ ease }}
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => { e.preventDefault(); await api.prospectToProject(p.id, from, to); onClose(true); }}>
        <div className="kicker">Handover list</div>
        <h2>{p.name}</h2>
        <p className="muted small">Possession window, if you know it (builder site or RERA). Leave blank to fill later in Rules.</p>
        <div className="form-grid">
          <label>Possession from<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label>Possession to<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={() => onClose(false)}>Cancel</button>
          <button className="btn primary">Add to handover list</button>
        </div>
      </motion.form>
    </motion.div>
  );
}

export default function Prospects() {
  const [data, setData] = useState<{ prospects: Prospect[]; state: CrawlState } | null>(null);
  const [tab, setTab] = useState<ProspectKind>(() => { try { return (localStorage.getItem(TAB_KEY) as ProspectKind) || "post"; } catch { return "post"; } });
  const [status, setStatus] = useState<ProspectStatus | "all">("new");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Prospect | null>(null);
  const load = useCallback(() => api.prospects().then(setData).catch((e) => setMsg(e.message)), []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  useEffect(() => { try { localStorage.setItem(TAB_KEY, tab); } catch { /* ignore */ } }, [tab]);

  const counts = useMemo(() => Object.fromEntries(TABS.map((t) => [t.k, data?.prospects.filter((p) => p.kind === t.k && p.status === "new").length ?? 0])), [data]);
  const list = useMemo(() => (data?.prospects ?? [])
    .filter((p) => p.kind === tab && (status === "all" || p.status === status))
    .sort((a, b) => b.score - a.score), [data, tab, status]);
  const st = data?.state;
  const feed = tab === "post" ? "posts" : tab === "partner" ? "partners" : "projects";
  const feedState = st?.[feed as keyof CrawlState] as { last_run?: string; last_error?: string; errors?: string[] } | undefined;

  const setP = async (p: Prospect, s: ProspectStatus) => { await api.updateProspect(p.id, { status: s }); load(); };

  return (
    <Page title="Prospects" kicker="Found by the crawler"
      actions={<button className="btn primary" disabled={busy} onClick={async () => {
        setBusy(true); setMsg(null);
        try { const n = await api.crawlNow(feed); setMsg(`${n} new found`); await load(); } catch (e) { setMsg((e as Error).message); }
        setBusy(false);
      }}>{busy ? "Searching…" : "Search now"}</button>}>
      <div className="seg big">
        {TABS.map((t) => (
          <button key={t.k} className={tab === t.k ? "on" : ""} onClick={() => setTab(t.k)}>
            {tab === t.k && <motion.span layoutId="seg-pros" className="seg-on" />}
            <span>{t.label}{counts[t.k] ? <em className="seg-count">{counts[t.k]}</em> : null}</span>
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.p key={tab} className="hint" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          {TABS.find((t) => t.k === tab)?.hint}
          {feedState?.last_run && <> · last searched {ago(feedState.last_run)}</>}
          {msg && <b className="flash"> · {msg}</b>}
          {feedState?.last_error && <span className="err"> · last error: {feedState.last_error}</span>}
        </motion.p>
      </AnimatePresence>

      <div className={tab === "partner" ? "pros-grid with-radar" : "pros-grid"}>
        {tab === "partner" && <motion.aside className="card" initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }}><h3>Search area</h3><Radar state={st?.partners} /></motion.aside>}
        <div>
          <div className="chips">
            {[{ k: "all", label: "All" } as const, ...STATUS].map((s) => (
              <button key={s.k} className={`chip ${status === s.k ? "on" : ""}`} onClick={() => setStatus(s.k)}>
                {status === s.k && <motion.span layoutId="chip-pros" className="chip-on" />}
                <span>{s.label}</span><em>{data?.prospects.filter((p) => p.kind === tab && (s.k === "all" || p.status === s.k)).length ?? 0}</em>
              </button>
            ))}
          </div>
          {!data ? <div className="skeleton" /> : list.length === 0 ? <Empty>Nothing here yet — the crawler runs in the background.</Empty> : (
            <motion.div className="pros-list" variants={stagger} initial="hidden" animate="show" key={tab + status}>
              {list.slice(0, 200).map((p) => (
                <motion.article key={p.id} className={`pros pros-${p.kind}`} variants={rise} layout>
                  <div className="pros-score" style={{ ["--s" as string]: p.score }}><span>{p.score}</span></div>
                  <div className="pros-main">
                    <div className="pros-top">
                      <span className="src">{p.category}</span>
                      {p.locality && <span className="muted small">{p.locality}</span>}
                      {p.ring_km != null && <span className="muted small">{p.ring_km} km out</span>}
                      <span className="muted small">{p.posted_at ? `posted ${ago(p.posted_at)}` : `found ${day(p.found_at)}`}</span>
                    </div>
                    <h4>{p.name}</h4>
                    {p.body && <p className="pros-body">{p.body}</p>}
                    <div className="pros-links">
                      {p.phone && <a href={`tel:${p.phone.replace(/\s/g, "")}`}>{p.phone}</a>}
                      {p.phone && <a href={`https://wa.me/${p.phone.replace(/\D/g, "").replace(/^0/, "91")}`} target="_blank" rel="noreferrer">WhatsApp</a>}
                      {p.website && <a href={p.website} target="_blank" rel="noreferrer">Website</a>}
                      {p.url && <a href={p.url} target="_blank" rel="noreferrer">{p.kind === "post" ? "Open post" : "Map"}</a>}
                    </div>
                  </div>
                  <div className="pros-actions">
                    {p.kind === "project" && p.status !== "added" && <button className="btn primary sm" onClick={() => setDialog(p)}>Add to handover list</button>}
                    {p.kind === "post" && <button className="btn ghost sm" onClick={() => setP(p, "contacted")}>Replied</button>}
                    {p.kind === "partner" && <>
                      <button className="btn ghost sm" onClick={() => setP(p, "contacted")}>Contacted</button>
                      <button className="btn ghost sm" onClick={() => setP(p, "partner")}>Partner</button>
                    </>}
                    {p.kind !== "project" && <button className="btn ghost sm" onClick={() => setP(p, "interested")}>Interested</button>}
                    <button className="link" onClick={() => setP(p, "not_relevant")}>Not relevant</button>
                    <span className={`pstat ps-${p.status}`}>{STATUS.find((s) => s.k === p.status)?.label}</span>
                  </div>
                </motion.article>
              ))}
            </motion.div>
          )}
        </div>
      </div>
      <AnimatePresence>{dialog && <ProjectDialog p={dialog} onClose={(ok) => { setDialog(null); if (ok) load(); }} />}</AnimatePresence>
    </Page>
  );
}
