import { Bug, Database, KeyRound, Loader2, Play, Radio, ServerCrash, Square, Terminal, Trash2 } from "lucide-react";
import { useState } from "react";
import LiveTail from "../components/LiveTail.jsx";
import { api } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const ICONS = { db_pool_exhaustion: Database, inventory_null_pointer: Bug, cache_outage: ServerCrash, brute_force_login: KeyRound };

export default function Simulator() {
  const { data, reload } = usePoll(() => api("/api/v1/simulator/scenarios"), 1500);
  const [msg, setMsg] = useState(null);
  const running = new Set((data?.status?.running || []).map((r) => r.scenario));

  const run = async (id) => { await api("/api/v1/simulator/run", { method: "POST", body: { scenario: id } }); reload(); };
  const traffic = async (on) => { await api(`/api/v1/simulator/traffic/${on ? "start" : "stop"}`, { method: "POST" }); reload(); };
  const reset = async () => {
    if (!window.confirm("Delete all logs, incidents and learned weights?")) return;
    await api("/api/v1/admin/reset", { method: "POST" });
    setMsg("All demo data cleared.");
    setTimeout(() => setMsg(null), 3000);
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Failure simulator</h1>
        <p className="text-sm text-slate-500">
          Generates realistic logs for the <b>ShopFlow</b> demo system (gateway, checkout, payment, orders, Java inventory, cart, auth) in JSON, logfmt and plain-text formats,
          and sends them through the normal ingestion pipeline.
        </p>
      </div>

      <div className="card flex flex-wrap items-center gap-3 p-4">
        <Radio size={18} className={data?.status?.traffic ? "text-emerald-600" : "text-slate-400"} />
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-800">Background traffic</div>
          <div className="text-xs text-slate-500">Healthy requests across all services (about 3 per second), with an occasional harmless error.</div>
        </div>
        {data?.status?.traffic
          ? <button className="btn-ghost" onClick={() => traffic(false)}><Square size={14} /> Stop traffic</button>
          : <button className="btn-primary" onClick={() => traffic(true)}><Play size={14} /> Start traffic</button>}
        <button className="btn-danger" onClick={reset}><Trash2 size={14} /> Reset demo data</button>
      </div>
      {msg && <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{msg}</div>}

      <div className="grid gap-4 md:grid-cols-2">
        {(data?.items || []).map((s) => {
          const Icon = ICONS[s.id] || Bug;
          const busy = running.has(s.id);
          return (
            <div key={s.id} className="card flex flex-col p-4">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-rose-50 text-rose-600"><Icon size={20} /></div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-slate-800">{s.title}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{s.description}</div>
                  <div className="mt-2 text-[11px] text-slate-400">Expected root cause: <span className="text-slate-600">{s.expected_root_cause}</span></div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-end">
                <button className="btn-primary" disabled={busy} onClick={() => run(s.id)}>
                  {busy ? <><Loader2 size={14} className="animate-spin" /> Running (~20 s)…</> : <><Play size={14} /> Run scenario</>}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <LiveTail />
        <div className="card">
          <div className="card-h"><div className="card-t"><Terminal size={16} /> Send your own logs</div></div>
          <div className="space-y-2 p-4 text-xs text-slate-600">
            <p>Any application can push logs with the project API key:</p>
            <pre className="mono overflow-auto rounded-lg bg-slate-900 p-3 text-slate-100">{`curl -X POST http://localhost:8000/api/v1/ingest \\
  -H "X-API-Key: sla_demo_ingest_key" \\
  -H "Content-Type: application/json" \\
  -d '{"events": [
    {"level":"error","service":"billing","message":"Timeout calling ledger"},
    "2026-11-19 10:00:01 ERROR [billing] retry budget exhausted",
    "ts=2026-11-19T10:00:02Z level=warn service=billing msg=\\"slow query\\""
  ]}'`}</pre>
            <p>Or run the standalone simulator against the API: <span className="mono">python -m app.simulator.cli db_pool_exhaustion</span></p>
          </div>
        </div>
      </div>
    </div>
  );
}
