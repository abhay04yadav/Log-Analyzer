// Shared presentational components.
export const SIGNALS = [
  { key: "T", name: "Temporal", color: "var(--color-sig-t)" },
  { key: "D", name: "Dependency", color: "var(--color-sig-d)" },
  { key: "A", name: "Anomaly", color: "var(--color-sig-a)" },
  { key: "C", name: "Code & deploy", color: "var(--color-sig-c)" },
  { key: "H", name: "History", color: "var(--color-sig-h)" },
];

const LEVEL = {
  DEBUG: "bg-slate-100 text-slate-500",
  INFO: "bg-sky-50 text-sky-700",
  WARN: "bg-amber-50 text-amber-700",
  ERROR: "bg-rose-50 text-rose-700",
  CRITICAL: "bg-rose-600 text-white",
};
export function LevelBadge({ level }) {
  return <span className={`inline-block w-[64px] text-center rounded px-1.5 py-0.5 text-[11px] font-semibold ${LEVEL[level] || LEVEL.INFO}`}>{level}</span>;
}

const SEV = {
  low: "bg-slate-100 text-slate-600",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-rose-600 text-white",
};
export function SeverityBadge({ severity }) {
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${SEV[severity] || SEV.medium}`}>{severity}</span>;
}

export function StatusBadge({ status }) {
  const cls = status === "resolved" ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-rose-50 text-rose-700 ring-rose-200";
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${cls}`}>{status}</span>;
}

export function CategoryBadge({ category }) {
  return category === "security" ? (
    <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-semibold text-violet-800">security</span>
  ) : (
    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700">error</span>
  );
}

export function Pill({ children, className = "" }) {
  return <span className={`rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 ${className}`}>{children}</span>;
}

// Stacked bar: contribution of each signal (weight x value) to the score R.
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
    <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
      {SIGNALS.map((s) => (
        <span key={s.key} className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
          {s.key} · {s.name}
        </span>
      ))}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="px-4 py-10 text-center text-sm text-slate-400">{children}</div>;
}

export function Stat({ label, value, icon: Icon, tone = "slate", hint }) {
  const tones = {
    slate: "text-slate-600 bg-slate-100",
    rose: "text-rose-600 bg-rose-50",
    amber: "text-amber-600 bg-amber-50",
    emerald: "text-emerald-600 bg-emerald-50",
    brand: "text-brand-600 bg-brand-50",
    violet: "text-violet-600 bg-violet-50",
  };
  return (
    <div className="card flex items-center gap-3 p-4">
      <div className={`grid h-10 w-10 place-items-center rounded-lg ${tones[tone]}`}>{Icon && <Icon size={20} />}</div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold tabular-nums text-slate-900">{value ?? "—"}</div>
        <div className="truncate text-xs text-slate-500">{label}{hint && <span className="text-slate-400"> · {hint}</span>}</div>
      </div>
    </div>
  );
}
