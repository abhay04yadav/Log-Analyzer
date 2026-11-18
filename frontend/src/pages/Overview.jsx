import { AlertTriangle, Boxes, CheckCircle2, Fingerprint, Radio, ShieldAlert, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import IncidentRow from "../components/IncidentRow.jsx";
import LiveTail from "../components/LiveTail.jsx";
import { Empty, Stat } from "../components/ui.jsx";
import { api, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

export default function Overview() {
  const { data: ov } = usePoll(() => api("/api/v1/stats/overview"), 3000);
  const { data: ts } = usePoll(() => api("/api/v1/stats/timeseries?minutes=15"), 3000);
  const { data: inc } = usePoll(() => api("/api/v1/incidents?limit=6"), 3000);
  const { data: svc } = usePoll(() => api("/api/v1/services"), 5000);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Overview</h1>
          <p className="text-sm text-slate-500">Live view of ingested logs, detected incidents and services (last 15 minutes).</p>
        </div>
        <Link to="/simulator" className="btn-primary"><Zap size={16} /> Run a failure scenario</Link>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Events" hint="15 min" value={ov?.events_15m} icon={Radio} tone="brand" />
        <Stat label="Errors" hint="15 min" value={ov?.errors_15m} icon={AlertTriangle} tone="rose" />
        <Stat label="Open incidents" value={ov?.open_incidents} icon={Zap} tone="amber" />
        <Stat label="Security alerts" value={ov?.security_incidents} icon={ShieldAlert} tone="violet" />
        <Stat label="Resolved" value={ov?.resolved_incidents} icon={CheckCircle2} tone="emerald" />
        <Stat label="Error fingerprints" value={ov?.fingerprints} icon={Fingerprint} tone="slate" />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="card-h"><div className="card-t">Log volume by level</div><span className="text-[11px] text-slate-400">10 s buckets</span></div>
          <div className="h-64 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={ts?.items || []} margin={{ left: -18, right: 8, top: 8 }}>
                <CartesianGrid stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="t" tickFormatter={fmtTime} tick={{ fontSize: 11, fill: "#94a3b8" }} minTickGap={40} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip labelFormatter={fmtTime} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="INFO" stackId="1" stroke="#38bdf8" fill="#bae6fd" isAnimationActive={false} />
                <Area type="monotone" dataKey="WARN" stackId="1" stroke="#f59e0b" fill="#fde68a" isAnimationActive={false} />
                <Area type="monotone" dataKey="ERROR" stackId="1" stroke="#e11d48" fill="#fda4af" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-h"><div className="card-t"><Boxes size={16} /> Services</div></div>
          <div className="divide-y divide-slate-100">
            {(svc?.items || []).length === 0 && <Empty>No logs yet.</Empty>}
            {(svc?.items || []).map((s) => {
              const rate = s.events ? s.errors / s.events : 0;
              return (
                <Link key={s.service} to={`/logs?service=${encodeURIComponent(s.service)}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50">
                  <span className={`h-2.5 w-2.5 rounded-full ${rate > 0.2 ? "bg-rose-500" : rate > 0 ? "bg-amber-400" : "bg-emerald-500"}`} />
                  <span className="flex-1 truncate text-sm font-medium text-slate-700">{s.service}</span>
                  <span className="text-xs tabular-nums text-slate-500">{s.events} ev</span>
                  <span className={`w-14 text-right text-xs tabular-nums ${s.errors ? "text-rose-600" : "text-slate-400"}`}>{s.errors} err</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card-h">
            <div className="card-t"><AlertTriangle size={16} /> Recent incidents</div>
            <Link to="/incidents" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>
          </div>
          <div className="divide-y divide-slate-100">
            {inc?.items?.length === 0 && <Empty>No incidents detected yet. Start a scenario in the simulator.</Empty>}
            {(inc?.items || []).map((i) => <IncidentRow key={i.id} incident={i} compact />)}
          </div>
        </div>
        <LiveTail />
      </div>
    </div>
  );
}
