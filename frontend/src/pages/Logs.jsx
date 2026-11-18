import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import EventModal from "../components/EventModal.jsx";
import { Empty, LevelBadge, Pill } from "../components/ui.jsx";
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
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Log explorer</h1>
        <p className="text-sm text-slate-500">Normalised events from all services and formats. Click an event to see its parsed fields, stack and raw input.</p>
      </div>
      <form className="card flex flex-wrap items-center gap-2 p-3" onSubmit={(e) => { e.preventDefault(); set("q", q); }}>
        <div className="relative min-w-[240px] flex-1">
          <Search size={15} className="absolute top-2.5 left-2.5 text-slate-400" />
          <input className="input w-full pl-8" placeholder="Full-text search, e.g. timeout, NullPointerException, 203.0.113.45" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input" value={service} onChange={(e) => set("service", e.target.value)}>
          <option value="">All services</option>
          {(svc?.items || []).map((s) => <option key={s.service}>{s.service}</option>)}
        </select>
        <select className="input" value={level} onChange={(e) => set("level", e.target.value)}>
          <option value="">All levels</option>
          <option value="ERROR,CRITICAL">Errors</option>
          <option value="WARN">Warnings</option>
          <option value="INFO">Info</option>
        </select>
        <button className="btn-primary">Search</button>
        {trace && <Pill className="mono">trace {trace.slice(0, 12)} <button type="button" className="ml-1 text-slate-400" onClick={() => set("trace_id", "")}>✕</button></Pill>}
      </form>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
              <tr><th className="px-3 py-2">Time</th><th className="px-3 py-2">Level</th><th className="px-3 py-2">Service</th><th className="px-3 py-2">Message</th><th className="px-3 py-2">Format</th><th className="px-3 py-2">Trace</th><th className="px-3 py-2">Incident</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(data?.items || []).map((e) => (
                <tr key={e.id} className={`cursor-pointer hover:bg-slate-50 ${e.is_error ? "bg-rose-50/30" : ""}`} onClick={() => setEventId(e.id)}>
                  <td className="mono whitespace-nowrap px-3 py-1.5 text-slate-500">{fmtDateTime(e.ts)}</td>
                  <td className="px-3 py-1.5"><LevelBadge level={e.level} /></td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-xs font-medium text-slate-700">{e.service}</td>
                  <td className="mono max-w-[560px] truncate px-3 py-1.5 text-slate-700" title={e.message}>{e.message}{e.has_stack && <Pill className="ml-2">stack</Pill>}</td>
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
        {data?.items?.length === 0 && <Empty>No matching events.</Empty>}
      </div>
      <EventModal id={eventId} onClose={() => setEventId(null)} />
    </div>
  );
}
