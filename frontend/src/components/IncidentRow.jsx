import { ChevronRight, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { ago } from "../lib/api.js";
import { CategoryBadge, SeverityBadge, StatusBadge } from "./ui.jsx";

export default function IncidentRow({ incident: i, compact = false }) {
  return (
    <Link to={`/incidents/${i.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50">
      <div className="w-10 shrink-0 text-xs font-semibold text-slate-400">#{i.id}</div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={i.severity} />
          <CategoryBadge category={i.category} />
          <StatusBadge status={i.status} />
          {i.has_recommendation && <span className="flex items-center gap-1 text-[11px] text-brand-600"><Sparkles size={12} /> fix ready</span>}
        </div>
        <div className="mt-1 truncate text-sm font-medium text-slate-800">{i.title}</div>
        <div className="mt-0.5 truncate text-xs text-slate-500">
          {i.top_candidate && <>Root cause: <b className="font-medium text-slate-700">{i.top_candidate.service}</b> · score {i.top_candidate.score.toFixed(2)} · </>}
          {i.services.length} service{i.services.length === 1 ? "" : "s"} · {i.event_count} events{!compact && <> · {i.services.join(", ")}</>}
        </div>
      </div>
      <div className="shrink-0 text-right text-xs text-slate-400">{ago(i.created_at)}</div>
      <ChevronRight size={16} className="shrink-0 text-slate-300" />
    </Link>
  );
}
