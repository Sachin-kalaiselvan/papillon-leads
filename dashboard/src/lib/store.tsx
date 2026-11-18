import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Snapshot } from "./api";
import type { Org } from "./types";

interface Ctx {
  snap: Snapshot | null;
  error: string | null;
  session: { email: string; org: Org } | null;
  ready: boolean;
  reload: () => Promise<void>;
  setSession: (s: { email: string; org: Org } | null) => void;
  prefs: Prefs;
  setPref: <K extends keyof Prefs>(k: K, v: Prefs[K]) => void;
}

export interface Prefs {
  leadFilter: string;
  leadSource: string;
  leadSearch: string;
  range: 7 | 14 | 30;
}

const PREF_KEY = "papillon-prefs";
const defaults: Prefs = { leadFilter: "all", leadSource: "all", leadSearch: "", range: 7 };
const loadPrefs = (): Prefs => {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") }; } catch { return defaults; }
};

const C = createContext<Ctx>(null as unknown as Ctx);
export const useStore = () => useContext(C);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<{ email: string; org: Org } | null>(null);
  const [ready, setReady] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);

  const reload = useCallback(async () => {
    try {
      setSnap(await api.load());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    api.session()
      .then((s) => { setSession(s); if (s) return reload(); })
      .catch((e) => setError(e.message))
      .finally(() => setReady(true));
  }, [reload]);

  useEffect(() => (session ? api.subscribe(reload) : undefined), [session, reload]);

  const setPref = useCallback(<K extends keyof Prefs>(k: K, v: Prefs[K]) => {
    setPrefs((p) => {
      const n = { ...p, [k]: v };
      try { localStorage.setItem(PREF_KEY, JSON.stringify(n)); } catch { /* ignore */ }
      return n;
    });
  }, []);

  const value = useMemo(() => ({ snap, error, session, ready, reload, setSession, prefs, setPref }),
    [snap, error, session, ready, reload, prefs, setPref]);
  return <C.Provider value={value}>{children}</C.Provider>;
}
