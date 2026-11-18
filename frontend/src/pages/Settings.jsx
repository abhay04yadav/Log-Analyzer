import { BookOpen, Bot, Cpu, RotateCcw, Scale } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Pill, SIGNALS } from "../components/ui.jsx";
import { api, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

export default function Settings() {
  const { data: w, reload } = usePoll(() => api("/api/v1/settings/weights"), 5000);
  const { data: st } = usePoll(() => api("/api/v1/system/status"), 3000);
  const { data: pb } = usePoll(() => api("/api/v1/playbook"), 0);

  const reset = async () => { await api("/api/v1/settings/weights/reset", { method: "POST" }); reload(); };
  const history = [{ at: "default", weights: w?.default }, ...(w?.history || [])].filter((h) => h.weights)
    .map((h, i) => ({ i, label: h.at === "default" ? "default" : fmtTime(h.at), ...h.weights }));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Model & settings</h1>
        <p className="text-sm text-slate-500">Ranking weights learned from engineer feedback, AI provider, pipeline status and the known-error playbook.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="card">
          <div className="card-h">
            <div className="card-t"><Scale size={16} /> Ranking weights: R = w₁T + w₂D + w₃A + w₄C + w₅H</div>
            <button className="btn-ghost !py-1 !text-xs" onClick={reset}><RotateCcw size={13} /> Reset</button>
          </div>
          <div className="space-y-2.5 p-4">
            {SIGNALS.map((s) => {
              const v = w?.current?.[s.key] ?? 0, d0 = w?.default?.[s.key] ?? 0;
              return (
                <div key={s.key} className="flex items-center gap-3 text-sm">
                  <span className="w-44 text-slate-600"><span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.key} · {w?.names?.[s.key]}</span>
                  <div className="h-2 flex-1 rounded-full bg-slate-100"><div className="h-2 rounded-full" style={{ width: `${v * 100 / 0.5}%`, maxWidth: "100%", background: s.color }} /></div>
                  <span className="w-12 text-right font-semibold tabular-nums">{v.toFixed(3)}</span>
                  <span className={`w-14 text-right text-xs tabular-nums ${v > d0 ? "text-emerald-600" : v < d0 ? "text-rose-600" : "text-slate-400"}`}>{v - d0 >= 0 ? "+" : ""}{(v - d0).toFixed(3)}</span>
                </div>
              );
            })}
            <p className="pt-1 text-xs text-slate-500">Confirming a root cause moves weight towards the signals that were strong for it; rejecting moves weight away (learning rate 0.1, minimum 0.05, always summing to 1).</p>
          </div>
          {history.length > 1 && (
            <div className="h-44 border-t border-slate-100 p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history} margin={{ left: -20, right: 10, top: 5 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <YAxis domain={[0, "auto"]} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  {SIGNALS.map((s) => <Line key={s.key} dataKey={s.key} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="space-y-5">
          <div className="card">
            <div className="card-h"><div className="card-t"><Bot size={16} /> AI provider</div></div>
            <div className="space-y-2 p-4 text-sm">
              <Row k="Provider" v={st?.ai.provider} />
              <Row k="Model" v={st?.ai.model} />
              <Row k="Status" v={st?.ai.enabled ? <Pill className="!bg-emerald-100 !text-emerald-700">enabled</Pill> : <Pill className="!bg-amber-100 !text-amber-800">no API key: playbook + rules only</Pill>} />
              <p className="text-xs text-slate-500">The AI receives only the masked evidence pack and must cite evidence ids. Its answer is checked by the validator (cited evidence exists, steps present, no unsafe operations) before it is shown.</p>
            </div>
          </div>
          <div className="card">
            <div className="card-h"><div className="card-t"><Cpu size={16} /> Pipeline</div></div>
            <div className="space-y-2 p-4 text-sm">
              <Row k="Database" v={st?.database} />
              <Row k="Event bus" v={st?.event_bus} />
              <Row k="Bus backlog" v={st?.bus_backlog} />
              <Row k="Events processed" v={st?.worker.processed_events} />
              <Row k="Batches processed" v={st?.worker.processed_batches} />
              <Row k="Worker errors" v={st?.worker.errors} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-h"><div className="card-t"><BookOpen size={16} /> Known-error playbook</div></div>
        <div className="divide-y divide-slate-100">
          {(pb?.items || []).map((k) => (
            <div key={k.id} className="grid gap-2 px-4 py-3 text-sm md:grid-cols-3">
              <div>
                <div className="font-medium text-slate-800">{k.name}</div>
                <div className="mt-1 flex gap-1"><Pill>{k.category}</Pill><Pill>{k.severity}</Pill></div>
              </div>
              <div className="mono break-all text-slate-500">{k.pattern}</div>
              <ol className="list-decimal space-y-0.5 pl-4 text-xs text-slate-600">{k.fix_steps.map((s) => <li key={s}>{s}</li>)}</ol>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return <div className="flex items-center justify-between gap-3"><span className="text-slate-500">{k}</span><span className="font-medium text-slate-800">{v ?? "—"}</span></div>;
}
