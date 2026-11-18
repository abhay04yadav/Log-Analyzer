import {
  ArrowRight, Bug, Check, Copy, Database, FileUp, KeyRound, Loader2, Play, PlugZap, Radio, ServerCrash, Square, Store,
  Terminal, Zap,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import LiveTail from "../components/LiveTail.jsx";
import UploadCard from "../components/UploadCard.jsx";
import { Help, PageHeader } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const ICONS = { db_pool_exhaustion: Database, inventory_null_pointer: Bug, cache_outage: ServerCrash, brute_force_login: KeyRound };
const STORE_SERVICES = ["api-gateway", "checkout-service", "payment-service", "order-service", "inventory-service", "cart-service", "auth-service"];

export default function Sources() {
  const { data, reload } = usePoll(() => api("/api/v1/simulator/scenarios"), 1500);
  const { data: project } = usePoll(() => api("/api/v1/project"), 0);
  const running = new Set((data?.status?.running || []).map((r) => r.scenario));
  const [started, setStarted] = useState({});
  const live = !!data?.status?.traffic;

  const run = async (id) => {
    await api("/api/v1/simulator/run", { method: "POST", body: { scenario: id } });
    setStarted((s) => ({ ...s, [id]: true }));
    reload();
  };
  const traffic = async (on) => { await api(`/api/v1/simulator/traffic/${on ? "start" : "stop"}`, { method: "POST" }); reload(); };

  return (
    <div className="space-y-6">
      <PageHeader title="Log sources"
        description="This is how logs get into the analyzer. Services send their logs automatically over the API; you can also upload a log file. Nothing else is needed: detection and analysis start as soon as logs arrive." />

      <div className="grid gap-4 md:grid-cols-3">
        {[
          { icon: PlugZap, title: "Automatic (API)", text: "Applications send each log line as it happens. This is the normal way in production." },
          { icon: FileUp, title: "Upload a file", text: "Have a log file from a server? Upload it and it is analysed the same way." },
          { icon: Zap, title: "Failure drills", text: "Trigger a realistic failure in the store to see detection and diagnosis end to end." },
        ].map((x) => (
          <div key={x.title} className="flex gap-3 rounded-2xl border border-dashed border-slate-300 bg-white/60 p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600"><x.icon size={18} /></div>
            <div>
              <div className="text-sm font-semibold text-slate-800">{x.title}</div>
              <div className="mt-0.5 text-sm text-slate-500">{x.text}</div>
            </div>
          </div>
        ))}
      </div>

      {/* connected application */}
      <div className="card">
        <div className="card-h flex-wrap">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-lg bg-slate-900 text-white"><Store size={20} /></div>
            <div>
              <div className="card-t">ShopFlow online store <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${live ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{live ? "● Streaming" : "Paused"}</span></div>
              <div className="card-d">Connected application · 7 services · sends logs over the API</div>
            </div>
          </div>
          {live
            ? <button className="btn-ghost" onClick={() => traffic(false)}><Square size={14} /> Pause traffic</button>
            : <button className="btn-primary" onClick={() => traffic(true)}><Play size={14} /> Start live traffic</button>}
        </div>
        <div className="space-y-3 p-5">
          <p className="text-sm text-slate-600">
            Live traffic is normal shopping activity (about 3 requests per second across all services, with the occasional harmless error).
            Start it first, so the analyzer learns what “normal” looks like before a problem happens.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {STORE_SERVICES.map((s) => <span key={s} className="mono rounded-md bg-slate-100 px-2 py-1 text-slate-600">{s}</span>)}
          </div>
        </div>
      </div>

      {/* failure drills */}
      <div>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Failure drills</h2>
            <p className="text-sm text-slate-500">Each drill makes the store fail in a realistic way for about 20 seconds. Watch the analyzer detect it, find where it started and suggest a fix.</p>
          </div>
          <Link to="/incidents" className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:underline">Go to incidents <ArrowRight size={14} /></Link>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {(data?.items || []).map((s) => {
            const Icon = ICONS[s.id] || Bug;
            const busy = running.has(s.id);
            return (
              <div key={s.id} className="card flex flex-col p-5">
                <div className="flex items-start gap-3">
                  <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${s.id === "brute_force_login" ? "bg-violet-50 text-violet-600" : "bg-rose-50 text-rose-600"}`}><Icon size={20} /></div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[15px] font-semibold text-slate-900">{s.title}</div>
                    <div className="mt-1 text-sm text-slate-600">{s.description}</div>
                  </div>
                </div>
                <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  <span className="font-semibold text-slate-700">The analyzer should find: </span><span className="mono">{s.expected_root_cause}</span>
                </div>
                <div className="mt-4 flex items-center justify-between gap-2">
                  <span className="text-xs text-slate-400">
                    {busy ? "Running. The incident appears within a few seconds." : started[s.id] ? <span className="inline-flex items-center gap-1 text-emerald-600"><Check size={13} /> Finished</span> : "Takes about 20 seconds"}
                  </span>
                  <div className="flex gap-2">
                    {(busy || started[s.id]) && <Link to="/incidents" className="btn-ghost btn-sm">View incidents</Link>}
                    <button className="btn-primary btn-sm" disabled={busy} onClick={() => run(s.id)}>
                      {busy ? <><Loader2 size={13} className="animate-spin" /> Running…</> : <><Play size={13} /> Start drill</>}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <UploadCard />
        <ApiCard project={project} />
      </div>
      <LiveTail />
    </div>
  );
}

function ApiCard({ project }) {
  const [copied, setCopied] = useState(null);
  const origin = window.location.origin;
  const key = project?.ingest_api_key || "…";
  const curl = `curl -X POST ${origin}/api/v1/ingest \\
  -H "X-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{"events": [
    {"level":"error","service":"billing","message":"Timeout calling ledger"},
    "2026-11-19 10:00:01 ERROR [billing] retry budget exhausted"
  ]}'`;
  const copy = async (what, text) => {
    try { await navigator.clipboard.writeText(text); setCopied(what); setTimeout(() => setCopied(null), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="card">
      <div className="card-h">
        <div>
          <div className="card-t"><Terminal size={16} /> Connect your own application</div>
          <div className="card-d">Send logs from any language or log shipper over HTTPS</div>
        </div>
      </div>
      <div className="space-y-4 p-5 text-sm">
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-600">Project API key <Help>Every request must include this key in the X-API-Key header. It identifies the project the logs belong to.</Help></div>
          <div className="flex items-center gap-2">
            <code className="mono flex-1 truncate rounded-lg bg-slate-100 px-3 py-2 text-slate-800">{key}</code>
            <button className="btn-ghost btn-sm" onClick={() => copy("key", key)}>{copied === "key" ? <Check size={13} /> : <Copy size={13} />} {copied === "key" ? "Copied" : "Copy"}</button>
          </div>
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-600">
            Example request
            <button className="flex items-center gap-1 font-medium text-brand-600 hover:underline" onClick={() => copy("curl", curl)}>{copied === "curl" ? <Check size={13} /> : <Copy size={13} />} {copied === "curl" ? "Copied" : "Copy"}</button>
          </div>
          <pre className="mono overflow-auto rounded-lg bg-slate-950 p-3 text-slate-100">{curl}</pre>
        </div>
        <ul className="space-y-1.5 text-xs text-slate-600">
          <li><span className="mono font-medium text-slate-800">POST /api/v1/ingest</span>: individual log lines (JSON, key=value or plain text, mixed is fine)</li>
          <li><span className="mono font-medium text-slate-800">POST /api/v1/ingest/text</span>: a whole log file in one request</li>
          <li><span className="mono font-medium text-slate-800">POST /api/v1/deployments</span>: tell the analyzer about a new release (helps find the cause)</li>
        </ul>
      </div>
    </div>
  );
}
