import { animate, motion, useInView, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useRef, type ReactNode } from "react";
import type { Temperature } from "../lib/types";

export const ease = [0.22, 1, 0.36, 1] as const;

export function Page({ children, title, kicker, actions }: { children: ReactNode; title: string; kicker?: string; actions?: ReactNode }) {
  return (
    <motion.main
      className="page"
      initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      exit={{ opacity: 0, y: -10, filter: "blur(4px)" }}
      transition={{ duration: 0.45, ease }}
    >
      <header className="page-head">
        <div>
          {kicker && <motion.div className="kicker" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.08 }}>{kicker}</motion.div>}
          <h1>{title}</h1>
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </header>
      {children}
    </motion.main>
  );
}

export const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.08 } },
};
export const rise = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } },
};

export function Counter({ value, format = (n: number) => Math.round(n).toLocaleString("en-IN") }: { value: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (!inView) return;
    const c = animate(mv, value, { duration: 1.1, ease });
    return () => c.stop();
  }, [inView, value, mv]);
  return <motion.span ref={ref}>{text}</motion.span>;
}

export function Temp({ t, big }: { t: Temperature | null | undefined; big?: boolean }) {
  if (!t) return <span className="temp none">—</span>;
  return (
    <span className={`temp ${t} ${big ? "big" : ""}`}>
      <span className="dot" />
      {t}
    </span>
  );
}

export function Butterfly({ size = 34, draw = true }: { size?: number; draw?: boolean }) {
  const p = "M32 34 C26 16 10 6 5 14 C1 22 14 33 32 34 Z M32 34 C38 16 54 6 59 14 C63 22 50 33 32 34 Z M32 34 C26 40 16 52 11 47 C7 42 18 36 32 34 Z M32 34 C38 40 48 52 53 47 C57 42 46 36 32 34 Z";
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className="butterfly" aria-hidden>
      <motion.path d={p} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round"
        initial={draw ? { pathLength: 0, opacity: 0 } : false} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 1.8, ease }} />
      <motion.path d={p} fill="currentColor" initial={{ opacity: 0 }} animate={{ opacity: 0.16 }} transition={{ delay: 1.2, duration: 0.8 }} />
      <line x1="32" y1="22" x2="32" y2="48" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <motion.div className="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>{children}</motion.div>;
}

export function Bar({ value, max, tone = "brass", delay = 0 }: { value: number; max: number; tone?: string; delay?: number }) {
  return (
    <div className="bar">
      <motion.div className={`bar-fill ${tone}`} initial={{ width: 0 }} animate={{ width: `${max ? (100 * value) / max : 0}%` }}
        transition={{ duration: 0.9, delay, ease }} />
    </div>
  );
}
