import { AlertTriangle, BookOpen, Bot, Cpu, RotateCcw, Scale, Trash2 } from "lucide-react";
import { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Help, Notice, PageHeader, Pill, SIGNALS } from "../components/ui.jsx";
import { api, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const CAT = { dependency: "Dependency", resource: "Resources", config: "Configuration", security: "Security" };

export default function Settings() {
  const { data: w, reload } = usePoll(() => api("/api/v1/settings/weights"), 5000);
  const { data: st } = usePoll(() => api("/api/v1/system/status"), 3000);
  const { data: pb } = usePoll(() => api("/api/v1/playbook"), 0);
  const [msg, setMsg] = useState(null);

  const resetWeights = async () => { await api("/api/v1/settings/weights/reset", { method: "POST" }); reload(); };
  const clearAll = async () => {
    if (!window.confirm("Delete all logs, incidents and learned weights? This cannot be undone.")) return;
    await api("/api/v1/admin/reset", { method: "POST" });
    reload();
    setMsg("All data has been cleared.");
    setTimeout(() => setMsg(null), 4000);
  };
  const history = [{ at: "default", weights: w?.default }, ...(w?.history || [])].filter((h) => h.weights)
    .map((h, i) => ({ i, label: h.at === "default" ? "start" : fmtTime(h.at), ...Object.fromEntries(SIGNALS.map((s) => [s.name, h.weights[s.key]])) }));

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="The AI assistant, how the analyzer learns from feedback, the library of known issues, and system status." />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-t"><Scale size={16} /> What the analyzer has learned</div>
              <div className="card-d">How much each clue counts when ranking root causes</div>
            </div>
            <button className="btn-ghost btn-sm" onClick={resetWeights}><RotateCcw size={13} /> Reset</button>
          </div>
          <div className="space-y-3 p-5">
            {SIGNALS.map((s) => {
              const v = w?.current?.[s.key] ?? 0, d0 = w?.default?.[s.key] ?? 0;
              return (
                <div key={s.key} className="flex items-center gap-3 text-sm">
                  <span className="flex w-52 items-center gap-1.5 text-slate-700">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.name}<Help>{s.help}</Help>
                  </span>
                  <div className="h-2 flex-1 rounded-full bg-slate-100"><div className="h-2 rounded-full" style={{ width: `${Math.min(100, v * 200)}%`, background: s.color }} /></div>
                  <span className="w-12 text-right font-semibold tabular-nums">{Math.round(v * 100)}%</span>
                  <span className={`w-14 text-right text-xs tabular-nums ${v > d0 ? "text-emerald-600" : v < d0 ? "text-rose-600" : "text-slate-400"}`}>{v - d0 >= 0 ? "+" : ""}{((v - d0) * 100).toFixed(1)}</span>
                </div>
              );
            })}
            <p className="pt-1 text-xs leading-relaxed text-slate-500">
              When an engineer confirms a root cause, the clues that pointed to it count a little more next time; when they reject one, those clues count a little less.
              The five weights always add up to 100%.
            </p>
          </div>
          {history.length > 1 && (
            <div className="h-48 border-t border-slate-100 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history} margin={{ left: -20, right: 10, top: 5 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis domain={[0, "auto"]} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v) => v.toFixed(3)} />
                  {SIGNALS.map((s) => <Line key={s.key} dataKey={s.name} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="card">
            <div className="card-h">
              <div>
                <div className="card-t"><Bot size={16} /> AI assistant</div>
                <div className="card-d">Writes the explanation and fix steps for each incident</div>
              </div>
              {st && (st.ai.enabled
                ? <Pill className="!bg-emerald-100 !text-emerald-700">Connected</Pill>
                : <Pill className="!bg-amber-100 !text-amber-800">Not configured</Pill>)}
            </div>
            <div className="space-y-2.5 p-5 text-sm">
              <Row k="Provider" v={st?.ai.provider === "gemini" ? "Google Gemini" : st?.ai.provider} />
              <Row k="Model" v={st?.ai.model} />
              <p className="pt-1 text-xs leading-relaxed text-slate-500">
                The AI only sees the evidence collected for the incident, with passwords and keys hidden. It must point to that evidence for every statement,
                and its answer is checked automatically before it is shown. Known issues are answered from the library without the AI.
                {st && !st.ai.enabled && " Without an AI key, automatic rules write the recommendation."}
              </p>
            </div>
          </div>
          <div className="card">
            <div className="card-h">
              <div>
                <div className="card-t"><Cpu size={16} /> System status</div>
                <div className="card-d">Processing pipeline health</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 p-5 text-sm">
              <Row k="Database" v={st?.database === "postgresql" ? "PostgreSQL" : st?.database === "sqlite" ? "SQLite" : st?.database} />
              <Row k="Message queue" v={st?.event_bus === "redis-streams" ? "Redis Streams" : st?.event_bus === "memory" ? "In-memory" : st?.event_bus} />
              <Row k="Waiting in queue" v={st?.bus_backlog} />
              <Row k="Log lines processed" v={st?.worker.processed_events?.toLocaleString()} />
              <Row k="Batches processed" v={st?.worker.processed_batches?.toLocaleString()} />
              <Row k="Processing errors" v={st?.worker.errors} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h">
          <div>
            <div className="card-t"><BookOpen size={16} /> Known issues library</div>
            <div className="card-d">Common problems with a ready-made fix. When an error matches one, its fix is used straight away.</div>
          </div>
          <span className="text-xs text-slate-400">{pb?.items?.length ?? 0} entries</span>
        </div>
        <div className="divide-y divide-slate-100">
          {(pb?.items || []).map((k) => (
            <div key={k.id} className="grid gap-3 px-5 py-4 text-sm md:grid-cols-[1fr_1.4fr]">
              <div>
                <div className="font-semibold text-slate-800">{k.name}</div>
                <div className="mt-1 flex gap-1"><Pill>{CAT[k.category] || k.category}</Pill><Pill className="capitalize">{k.severity}</Pill></div>
                <div className="mt-2 text-xs text-slate-500">{k.root_cause}</div>
                <details className="mt-1.5 text-xs text-slate-400">
                  <summary className="cursor-pointer hover:text-slate-600">Matching pattern</summary>
                  <div className="mono mt-1 break-all text-slate-500">{k.pattern}</div>
                </details>
              </div>
              <div>
                <div className="eyebrow mb-1.5">Fix steps</div>
                <ol className="list-decimal space-y-1 pl-4 text-sm text-slate-600">{k.fix_steps.map((s) => <li key={s}>{s}</li>)}</ol>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card border-rose-200">
        <div className="card-h border-rose-100">
          <div className="card-t text-rose-700"><AlertTriangle size={16} /> Danger zone</div>
        </div>
        <div className="flex flex-wrap items-center gap-4 p-5">
          <div className="flex-1 text-sm text-slate-600">
            <div className="font-medium text-slate-800">Clear all data</div>
            Deletes every log, incident, release record and learned weight. The project, API key and known issues library are kept.
          </div>
          <button className="btn-danger" onClick={clearAll}><Trash2 size={14} /> Clear all data</button>
        </div>
        {msg && <div className="px-5 pb-5"><Notice tone="ok">{msg}</Notice></div>}
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return <div className="flex items-center justify-between gap-3"><span className="text-slate-500">{k}</span><span className="font-medium text-slate-800">{v ?? "—"}</span></div>;
}
