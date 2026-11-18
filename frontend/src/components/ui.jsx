// Shared presentational components.
import { Info } from "lucide-react";
import { useId } from "react";

// The five clues used to rank root-cause candidates (R = w1·T + w2·D + w3·A + w4·C + w5·H).
export const SIGNALS = [
  { key: "T", name: "Happened first", color: "var(--color-sig-t)",
    help: "The service whose errors started earliest is usually where the problem began." },
  { key: "D", name: "Position in call chain", color: "var(--color-sig-d)",
    help: "If a service fails but nothing it calls is failing, the problem most likely starts there." },
  { key: "A", name: "Unusual volume", color: "var(--color-sig-a)",
    help: "How much more often this error happens now compared with normal." },
  { key: "C", name: "Code & recent changes", color: "var(--color-sig-c)",
    help: "The error points to a line of code, and that service had a new release shortly before." },
  { key: "H", name: "Seen before", color: "var(--color-sig-h)",
    help: "The same or a similar problem was confirmed before, or it is in the known issues library." },
];

export function Logo({ size = 36 }) {
  const gid = useId();
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#6366f1" /><stop offset="1" stopColor="#4338ca" /></linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gid})`} />
      <path d="M8 10h16M8 16h10M8 22h8" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="22.5" cy="20.5" r="4" fill="none" stroke="#fbbf24" strokeWidth="2.4" />
      <path d="M25.4 23.4l2.2 2.2" stroke="#fbbf24" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

// Small (i) icon with an explanation on hover / focus.
export function Help({ children, className = "" }) {
  return (
    <span className={`group relative inline-flex align-middle ${className}`} tabIndex={0}>
      <Info size={14} className="cursor-help text-slate-400 group-hover:text-brand-600" />
      <span className="pointer-events-none hidden absolute bottom-full left-1/2 z-40 mb-2 w-64 -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs leading-relaxed font-normal normal-case tracking-normal text-slate-100 shadow-lg group-hover:block group-focus:block">
        {children}
      </span>
    </span>
  );
}

export function PageHeader({ title, description, children }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 text-sm leading-relaxed text-slate-500">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

const LEVEL = {
  DEBUG: ["Debug", "bg-slate-100 text-slate-500"],
  INFO: ["Info", "bg-sky-50 text-sky-700"],
  WARN: ["Warning", "bg-amber-50 text-amber-700"],
  ERROR: ["Error", "bg-rose-50 text-rose-700"],
  CRITICAL: ["Critical", "bg-rose-600 text-white"],
};
export function LevelBadge({ level }) {
  const [label, cls] = LEVEL[level] || LEVEL.INFO;
  return <span className={`inline-block w-[68px] shrink-0 rounded-md px-1.5 py-0.5 text-center text-[11px] font-semibold ${cls}`}>{label}</span>;
}

const SEV = {
  low: "bg-slate-100 text-slate-600 ring-slate-200",
  medium: "bg-amber-50 text-amber-700 ring-amber-200",
  high: "bg-orange-50 text-orange-700 ring-orange-200",
  critical: "bg-rose-600 text-white ring-rose-600",
};
export const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function SeverityBadge({ severity }) {
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${SEV[severity] || SEV.medium}`}>{cap(severity)} severity</span>;
}

export function StatusBadge({ status }) {
  return status === "resolved" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Resolved
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-700 ring-1 ring-rose-200">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-500" /> Active
    </span>
  );
}

export function CategoryBadge({ category }) {
  return category === "security" ? (
    <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700 ring-1 ring-violet-200">Security</span>
  ) : (
    <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">Application error</span>
  );
}

export function Pill({ children, className = "" }) {
  return <span className={`rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 ${className}`}>{children}</span>;
}

// Stacked bar: contribution of each clue (weight x value) to the score R.
export function ScoreBar({ signals, weights, height = 10 }) {
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-slate-100" style={{ height }}>
      {SIGNALS.map((s) => {
        const v = (weights?.[s.key] ?? 0) * (signals?.[s.key] ?? 0);
        return v > 0 ? <div key={s.key} title={`${s.name}: ${v.toFixed(3)}`} style={{ width: `${v * 100}%`, background: s.color }} /> : null;
      })}
    </div>
  );
}

export function SignalLegend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-500">
      {SIGNALS.map((s) => (
        <span key={s.key} className="flex items-center gap-1.5" title={s.help}>
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  );
}

export function Empty({ icon: Icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      {Icon && <div className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-slate-100 text-slate-400"><Icon size={20} /></div>}
      {title && <div className="text-sm font-semibold text-slate-700">{title}</div>}
      {children && <div className="mt-1 max-w-sm text-sm text-slate-500">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Stat({ label, value, icon: Icon, tone = "slate", hint, help }) {
  const tones = {
    slate: "text-slate-600 bg-slate-100",
    rose: "text-rose-600 bg-rose-50",
    amber: "text-amber-600 bg-amber-50",
    emerald: "text-emerald-600 bg-emerald-50",
    brand: "text-brand-600 bg-brand-50",
    violet: "text-violet-600 bg-violet-50",
  };
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">{label}{help && <Help>{help}</Help>}</div>
        <div className={`grid h-8 w-8 place-items-center rounded-lg ${tones[tone]}`}>{Icon && <Icon size={16} />}</div>
      </div>
      <div className="mt-2 text-[28px] leading-none font-semibold tracking-tight tabular-nums text-slate-900">{value ?? "—"}</div>
      {hint && <div className="mt-1.5 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }) {
  const cls = {
    info: "bg-brand-50 text-brand-900 ring-brand-100",
    ok: "bg-emerald-50 text-emerald-800 ring-emerald-100",
    warn: "bg-amber-50 text-amber-800 ring-amber-100",
    error: "bg-rose-50 text-rose-700 ring-rose-100",
  }[tone];
  return <div className={`rounded-lg px-3 py-2 text-sm ring-1 ${cls}`}>{children}</div>;
}
