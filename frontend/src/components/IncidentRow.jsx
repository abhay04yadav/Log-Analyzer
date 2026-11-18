import { ChevronRight, ShieldAlert, Siren, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ago } from "../lib/api.js";
import { SeverityBadge, StatusBadge } from "./ui.jsx";

const CONF = { high: "text-emerald-700", medium: "text-amber-700", low: "text-slate-500" };

export default function IncidentRow({ incident: i, compact = false }) {
  const Icon = i.category === "security" ? ShieldAlert : Siren;
  const open = i.status !== "resolved";
  return (
    <Link to={`/incidents/${i.id}`} className="group flex items-center gap-4 px-5 py-3.5 transition hover:bg-slate-50">
      <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${!open ? "bg-emerald-50 text-emerald-600" : i.category === "security" ? "bg-violet-50 text-violet-600" : "bg-rose-50 text-rose-600"}`}>
        <Icon size={18} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-400">#{i.id}</span>
          <span className="truncate text-sm font-semibold text-slate-800 group-hover:text-brand-700">{i.title}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
          <StatusBadge status={i.status} />
          {!compact && <SeverityBadge severity={i.severity} />}
          {i.top_candidate && (
            <span>Likely cause: <b className="font-semibold text-slate-700">{i.top_candidate.service}</b>
              {i.top_candidate.confidence_label && <span className={CONF[i.top_candidate.confidence_label]}> ({i.top_candidate.confidence_label} confidence)</span>}
            </span>
          )}
          <span className="text-slate-300">•</span>
          <span>{i.services.length} service{i.services.length === 1 ? "" : "s"} affected</span>
          {i.has_recommendation && <span className="inline-flex items-center gap-1 font-medium text-brand-600"><Sparkles size={12} /> Fix ready</span>}
        </div>
      </div>
      <div className="hidden shrink-0 text-right text-xs text-slate-400 sm:block">{ago(i.created_at)}</div>
      <ChevronRight size={16} className="shrink-0 text-slate-300 group-hover:text-slate-500" />
    </Link>
  );
}
