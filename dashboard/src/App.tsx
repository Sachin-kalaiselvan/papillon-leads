import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Butterfly, ease } from "./components/ui";
import { api, resetDemo, switchDemoOrg } from "./lib/api";
import { useStore } from "./lib/store";
import threxaLogo from "./assets/threxa-logo.png";
import Campaigns from "./views/Campaigns";
import LeadDetail from "./views/LeadDetail";
import Leads from "./views/Leads";
import Overview from "./views/Overview";
import Pipeline from "./views/Pipeline";
import Reports from "./views/Reports";
import SettingsView from "./views/Settings";

const NAV = [
  { to: "/", label: "Overview", icon: "M4 13h6V4H4zm10 7h6V4h-6zM4 20h6v-4H4z", agency: false },
  { to: "/pipeline", label: "Pipeline", icon: "M4 5h4v14H4zm6 0h4v9h-4zm6 0h4v6h-4z", agency: false },
  { to: "/leads", label: "Leads", icon: "M5 6h14M5 12h14M5 18h9", agency: false },
  { to: "/reports", label: "Reports", icon: "M5 20V10m7 10V4m7 16v-7", agency: false },
  { to: "/campaigns", label: "Campaigns", icon: "M4 10v4l12 5V5zM16 9h4v6h-4", agency: true },
  { to: "/settings", label: "Rules", icon: "M12 8a4 4 0 100 8 4 4 0 000-8zm8 4l2-1-2-4-2 1-2-2V4h-4v2l-2 2-2-1-2 4 2 1v2l-2 1 2 4 2-1 2 2v2h4v-2l2-2 2 1 2-4-2-1z", agency: true },
];

function Login() {
  const { setSession, reload } = useStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="login">
      <motion.div className="login-art" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }}>
        <img src={threxaLogo} alt="Threxa" className="login-threxa" />
        <div className="login-for"><span>for</span></div>
        <Butterfly size={120} />
        <p>Every Papillon enquiry, called and understood — before it reaches the studio.</p>
      </motion.div>
      <motion.form className="login-card" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ ease, duration: 0.6, delay: 0.2 }}
        onSubmit={async (e) => {
          e.preventDefault(); setBusy(true); setErr(null);
          try { await api.signIn(email, password); const s = await api.session(); setSession(s); await reload(); }
          catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
        }}>
        <div className="kicker">Threxa for Papillon Interiors</div>
        <h1>Papillon Leads</h1>
        <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required autoFocus /></label>
        <label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required /></label>
        {err && <div className="error">{err}</div>}
        <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        {api.mode === "demo" && <p className="muted small">Demo mode — any email signs in. Use one with “papillon” in it to see the studio's view.</p>}
      </motion.form>
    </div>
  );
}

export default function App() {
  const { session, ready, snap, error } = useStore();
  const loc = useLocation();
  if (!ready) return <div className="splash"><Butterfly size={72} /></div>;
  if (!session) return <Login />;
  const agency = session.org === "agency";
  const hot = snap?.leads.filter((l) => l.stage === "forwarded" && l.temperature === "hot").length ?? 0;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand-block">
          <motion.img src={threxaLogo} alt="Threxa" className="threxa-logo"
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease }} />
          <motion.div className="built-for" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }}>
            <span>for</span>
          </motion.div>
          <div className="brand">
            <Butterfly size={34} />
            <div>
              <div className="brand-name">Papillon</div>
              <div className="brand-sub">Interiors · Leads</div>
            </div>
          </div>
        </div>
        <nav>
          {NAV.filter((n) => agency || !n.agency).map((n, i) => (
            <motion.div key={n.to} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 * i + 0.2, ease }}>
              <NavLink to={n.to} end={n.to === "/"} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-glow" className="nav-glow" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
                    <svg viewBox="0 0 24 24" width="18" height="18"><path d={n.icon} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    <span>{n.label}</span>
                    {n.to === "/pipeline" && hot > 0 && <span className="badge">{hot}</span>}
                  </>
                )}
              </NavLink>
            </motion.div>
          ))}
        </nav>
        <div className="side-foot">
          <div className="who">
            <div className="avatar">{session.email[0]?.toUpperCase()}</div>
            <div>
              <div className="who-mail">{session.email}</div>
              <div className="who-org">{agency ? "Lead operations" : "Papillon studio"}</div>
            </div>
          </div>
          {api.mode === "demo" && (
            <div className="demo-box">
              <span>Demo data</span>
              <button onClick={() => switchDemoOrg(agency ? "papillon" : "agency")}>View as {agency ? "studio" : "operations"}</button>
              <button onClick={resetDemo}>Reset</button>
            </div>
          )}
          <button className="link" onClick={async () => { await api.signOut(); location.reload(); }}>Sign out</button>
        </div>
      </aside>
      <div className="stage">
        {error && <div className="banner">{error}</div>}
        <AnimatePresence mode="wait">
          <Routes location={loc} key={loc.pathname.split("/")[1] + (loc.pathname.split("/")[2] ? "/d" : "")}>
            <Route path="/" element={<Overview />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/leads/:id" element={<LeadDetail />} />
            <Route path="/reports" element={<Reports />} />
            {agency && <Route path="/campaigns" element={<Campaigns />} />}
            {agency && <Route path="/settings" element={<SettingsView />} />}
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </AnimatePresence>
      </div>
    </div>
  );
}
