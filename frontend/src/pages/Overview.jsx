import {
  Activity, AlertTriangle, ArrowRight, Boxes, CheckCircle2, FileSearch, Layers, PlugZap, ShieldAlert, Siren, Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import IncidentRow from "../components/IncidentRow.jsx";
import LiveTail from "../components/LiveTail.jsx";
import { Empty, Help, PageHeader, Stat } from "../components/ui.jsx";
import { api, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

export default function Overview() {
  const { data: ov } = usePoll(() => api("/api/v1/stats/overview"), 3000);
  const { data: ts } = usePoll(() => api("/api/v1/stats/timeseries?minutes=15"), 3000);
  const { data: inc } = usePoll(() => api("/api/v1/incidents?limit=6"), 3000);
  const { data: svc } = usePoll(() => api("/api/v1/services"), 5000);

  const noData = ov && !ov.events_15m && !(inc?.items?.length);

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" description="The health of your services right now: logs received, errors found and incidents that need attention.">
        <Link to="/guide" className="btn-ghost"><FileSearch size={16} /> How it works</Link>
        <Link to="/sources" className="btn-primary"><PlugZap size={16} /> Log sources</Link>
      </PageHeader>

      <HealthBanner ov={ov} top={inc?.items?.find((i) => i.status === "open")} />

      {noData && <GettingStarted />}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Logs received" hint="last 15 minutes" value={ov?.events_15m} icon={Activity} tone="brand"
          help="Every log line sent by your services is counted here." />
        <Stat label="Errors" hint="last 15 minutes" value={ov?.errors_15m} icon={AlertTriangle} tone="rose"
          help="Log lines with level Error or Critical." />
        <Stat label="Active incidents" hint="need attention" value={ov?.open_incidents} icon={Siren} tone="amber"
          help="An incident is a group of related errors that together describe one problem." />
        <Stat label="Security alerts" hint="e.g. password guessing" value={ov?.security_incidents} icon={ShieldAlert} tone="violet" />
        <Stat label="Resolved" hint="root cause confirmed" value={ov?.resolved_incidents} icon={CheckCircle2} tone="emerald" />
        <Stat label="Unique error types" hint="error signatures" value={ov?.fingerprints} icon={Layers} tone="slate"
          help="Errors that differ only in numbers, IDs or names are treated as the same error type (one 'signature')." />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="card-h">
            <div>
              <div className="card-t">Log activity</div>
              <div className="card-d">Number of log lines every 10 seconds, by type</div>
            </div>
            <div className="flex gap-3 text-xs text-slate-500">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-sky-300" /> Info</span>
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-amber-300" /> Warnings</span>
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-rose-400" /> Errors</span>
            </div>
          </div>
          <div className="h-64 p-3">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={ts?.items || []} margin={{ left: -18, right: 8, top: 8 }}>
                <CartesianGrid stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="t" tickFormatter={fmtTime} tick={{ fontSize: 11, fill: "#94a3b8" }} minTickGap={40} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#94a3b8" }} />
                <Tooltip labelFormatter={fmtTime} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Area type="monotone" dataKey="INFO" name="Info" stackId="1" stroke="#38bdf8" fill="#bae6fd" isAnimationActive={false} />
                <Area type="monotone" dataKey="WARN" name="Warnings" stackId="1" stroke="#f59e0b" fill="#fde68a" isAnimationActive={false} />
                <Area type="monotone" dataKey="ERROR" name="Errors" stackId="1" stroke="#e11d48" fill="#fda4af" isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-t"><Boxes size={16} /> Service health</div>
              <div className="card-d">Click a service to see its logs</div>
            </div>
            <Help>Green: no errors. Amber: a few errors. Red: more than 20% of its logs are errors.</Help>
          </div>
          <div className="divide-y divide-slate-100">
            {(svc?.items || []).length === 0 && <Empty icon={Boxes}>Services appear here as soon as they send logs.</Empty>}
            {(svc?.items || []).map((s) => {
              const rate = s.events ? s.errors / s.events : 0;
              const [dot, label] = rate > 0.2 ? ["bg-rose-500", "Failing"] : rate > 0 ? ["bg-amber-400", "Some errors"] : ["bg-emerald-500", "Healthy"];
              return (
                <Link key={s.service} to={`/logs?service=${encodeURIComponent(s.service)}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-slate-50">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dot}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-800">{s.service}</span>
                    <span className="block text-xs text-slate-400">{label}</span>
                  </span>
                  <span className="text-right text-xs tabular-nums text-slate-500">
                    {s.events} logs<br /><span className={s.errors ? "text-rose-600" : "text-slate-400"}>{s.errors} errors</span>
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-t"><Siren size={16} /> Latest incidents</div>
              <div className="card-d">Related errors grouped into one problem, with the likely cause</div>
            </div>
            <Link to="/incidents" className="flex items-center gap-1 text-xs font-semibold text-brand-600 hover:underline">View all <ArrowRight size={13} /></Link>
          </div>
          <div className="divide-y divide-slate-100">
            {inc?.items?.length === 0 && (
              <Empty icon={CheckCircle2} title="No incidents">When something goes wrong, the analyzer groups the errors into an incident and explains it here.</Empty>
            )}
            {(inc?.items || []).map((i) => <IncidentRow key={i.id} incident={i} compact />)}
          </div>
        </div>
        <LiveTail />
      </div>
    </div>
  );
}

function HealthBanner({ ov, top }) {
  if (!ov) return <div className="card h-[76px] animate-pulse" />;
  const n = ov.open_incidents;
  if (n > 0) {
    return (
      <div className="card flex flex-wrap items-center gap-4 border-rose-200 bg-gradient-to-r from-rose-50 to-white p-5">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-rose-100 text-rose-600"><Siren size={22} /></div>
        <div className="min-w-0 flex-1">
          <div className="text-base font-semibold text-slate-900">{n} active incident{n > 1 ? "s" : ""} need{n > 1 ? "" : "s"} attention</div>
          <div className="truncate text-sm text-slate-600">
            {top ? <>Most recent: {top.title}{top.top_candidate && <> · likely cause in <b>{top.top_candidate.service}</b></>}</> : "Open the incident to see the root cause and the suggested fix."}
          </div>
        </div>
        {top && <Link to={`/incidents/${top.id}`} className="btn-primary">See root cause <ArrowRight size={15} /></Link>}
      </div>
    );
  }
  return (
    <div className="card flex flex-wrap items-center gap-4 border-emerald-200 bg-gradient-to-r from-emerald-50 to-white p-5">
      <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-emerald-100 text-emerald-600"><CheckCircle2 size={22} /></div>
      <div className="flex-1">
        <div className="text-base font-semibold text-slate-900">All systems normal</div>
        <div className="text-sm text-slate-600">No active incidents. The analyzer is watching every incoming log and will raise an incident as soon as something goes wrong.</div>
      </div>
    </div>
  );
}

function GettingStarted() {
  const steps = [
    { icon: PlugZap, title: "1. Send logs", text: "Connect a service, start live traffic or upload a log file.", to: "/sources", cta: "Open Log sources" },
    { icon: Siren, title: "2. Problems are detected", text: "Error spikes, crashes and attacks are grouped into incidents automatically." },
    { icon: Sparkles, title: "3. Get root cause & fix", text: "Open an incident to see where the problem started and how to fix it." },
  ];
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-slate-100 bg-gradient-to-r from-brand-50 to-white px-5 py-4">
        <div className="text-base font-semibold text-slate-900">Get started</div>
        <div className="text-sm text-slate-600">No logs have arrived yet. Three steps to your first analysis:</div>
      </div>
      <div className="grid gap-px bg-slate-100 md:grid-cols-3">
        {steps.map((s) => (
          <div key={s.title} className="bg-white p-5">
            <div className="mb-3 grid h-10 w-10 place-items-center rounded-lg bg-brand-50 text-brand-600"><s.icon size={20} /></div>
            <div className="text-sm font-semibold text-slate-800">{s.title}</div>
            <div className="mt-1 text-sm text-slate-500">{s.text}</div>
            {s.to && <Link to={s.to} className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:underline">{s.cta} <ArrowRight size={14} /></Link>}
          </div>
        ))}
      </div>
    </div>
  );
}
