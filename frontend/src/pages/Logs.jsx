import { Search, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import EventModal from "../components/EventModal.jsx";
import { Empty, LevelBadge, PageHeader, Pill } from "../components/ui.jsx";
import { api, fmtDateTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

export default function Logs() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [eventId, setEventId] = useState(null);
  const service = params.get("service") || "";
  const level = params.get("level") || "";
  const trace = params.get("trace_id") || "";
  const qs = new URLSearchParams({ limit: "200", ...(params.get("q") && { q: params.get("q") }), ...(service && { service }), ...(level && { level }), ...(trace && { trace_id: trace }) });
  const { data } = usePoll(() => api(`/api/v1/events?${qs}`), 4000, [qs.toString()]);
  const { data: svc } = usePoll(() => api("/api/v1/services"), 10000);

  const set = (k, v) => {
    const p = new URLSearchParams(params);
    v ? p.set(k, v) : p.delete(k);
    setParams(p);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Log search"
        description="Search every log line from all services. Logs arrive in different formats (JSON, key=value, plain text) and are converted to one standard format. Click any line to see its full details." />
      <form className="card flex flex-wrap items-center gap-2 p-3" onSubmit={(e) => { e.preventDefault(); set("q", q); }}>
        <div className="relative min-w-[240px] flex-1">
          <Search size={16} className="absolute top-2.5 left-3 text-slate-400" />
          <input className="input w-full pl-9" placeholder="Search words in log messages, e.g. timeout, NullPointerException, 203.0.113.45" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input" value={service} onChange={(e) => set("service", e.target.value)}>
          <option value="">All services</option>
          {(svc?.items || []).map((s) => <option key={s.service}>{s.service}</option>)}
        </select>
        <select className="input" value={level} onChange={(e) => set("level", e.target.value)}>
          <option value="">All types</option>
          <option value="ERROR,CRITICAL">Errors only</option>
          <option value="WARN">Warnings only</option>
          <option value="INFO">Info only</option>
        </select>
        <button className="btn-primary">Search</button>
        {trace && <span className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 px-2.5 py-1.5 text-xs font-medium text-brand-700">Showing one request: <span className="mono">{trace.slice(0, 12)}</span><button type="button" className="text-brand-400 hover:text-brand-700" onClick={() => set("trace_id", "")} aria-label="Clear"><X size={14} /></button></span>}
      </form>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <tr><th className="px-4 py-2.5">Time</th><th className="px-3 py-2.5">Type</th><th className="px-3 py-2.5">Service</th><th className="px-3 py-2.5">Message</th><th className="px-3 py-2.5">Format</th><th className="px-3 py-2.5" title="Click a request ID to see every log line from that one user request, across all services">Request ID</th><th className="px-3 py-2.5">Incident</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(data?.items || []).map((e) => (
                <tr key={e.id} className={`cursor-pointer hover:bg-slate-50 ${e.is_error ? "bg-rose-50/30" : ""}`} onClick={() => setEventId(e.id)}>
                  <td className="mono whitespace-nowrap px-4 py-1.5 text-slate-500">{fmtDateTime(e.ts)}</td>
                  <td className="px-3 py-1.5"><LevelBadge level={e.level} /></td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-xs font-medium text-slate-700">{e.service}</td>
                  <td className="mono max-w-[560px] truncate px-3 py-1.5 text-slate-700" title={e.message}>{e.message}{e.has_stack && <Pill className="ml-2">stack trace</Pill>}</td>
                  <td className="px-3 py-1.5"><Pill>{e.format}</Pill></td>
                  <td className="mono px-3 py-1.5">
                    {e.trace_id && <button className="text-brand-600 hover:underline" onClick={(ev) => { ev.stopPropagation(); set("trace_id", e.trace_id); }}>{e.trace_id.slice(0, 8)}</button>}
                  </td>
                  <td className="px-3 py-1.5 text-xs">{e.incident_id && <Link onClick={(ev) => ev.stopPropagation()} to={`/incidents/${e.incident_id}`} className="font-medium text-brand-600 hover:underline">#{e.incident_id}</Link>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data?.items?.length === 0 && <Empty icon={Search} title="No matching logs">Try a different search word or clear the filters.</Empty>}
      </div>
      <EventModal id={eventId} onClose={() => setEventId(null)} />
    </div>
  );
}
