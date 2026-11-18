import {
  ArrowLeft, Bot, BookOpen, Check, ChevronDown, ChevronRight, Code2, GitCommitHorizontal, History, ListChecks,
  Loader2, Network, RefreshCw, ShieldCheck, ShieldAlert, Target, ThumbsDown, ThumbsUp, Workflow,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import EventModal from "../components/EventModal.jsx";
import ServiceGraph from "../components/ServiceGraph.jsx";
import {
  CategoryBadge, Empty, LevelBadge, Pill, ScoreBar, SeverityBadge, SignalLegend, SIGNALS, StatusBadge,
} from "../components/ui.jsx";
import { api, fmtDateTime, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

export default function IncidentDetail() {
  const { id } = useParams();
  const { data: d, error, reload } = usePoll(() => api(`/api/v1/incidents/${id}`), 3000, [id]);
  const [eventId, setEventId] = useState(null);

  if (error && !d) return <div className="card p-6 text-sm text-rose-600">{error}</div>;
  if (!d) return <div className="p-6 text-sm text-slate-400">Loading incident…</div>;
  const top = d.candidates[0];
  const rec = d.recommendations[0];

  return (
    <div className="space-y-5">
      <div>
        <Link to="/incidents" className="mb-2 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"><ArrowLeft size={14} /> Incidents</Link>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-400">#{d.id}</span>
          <SeverityBadge severity={d.severity} /><CategoryBadge category={d.category} /><StatusBadge status={d.status} />
        </div>
        <h1 className="mt-1 text-xl font-semibold text-slate-900">{d.title}</h1>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>{fmtDateTime(d.window_start)} → {fmtTime(d.window_end)}</span>
          <span>{d.event_count} events · {d.error_count} errors</span>
          <span>Services: {d.services.join(", ")}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {d.detection.map((x) => <Pill key={x.label} className="!bg-amber-50 !text-amber-800">⚡ {x.label}</Pill>)}
        </div>
      </div>

      <PipelineStrip d={d} />

      <div className="grid gap-5 xl:grid-cols-5">
        <div className="space-y-5 xl:col-span-3">
          <Candidates d={d} onChanged={reload} />
          <Recommendation d={d} rec={rec} onChanged={reload} onEvent={setEventId} />
        </div>
        <div className="space-y-5 xl:col-span-2">
          <div className="card">
            <div className="card-h"><div className="card-t"><Network size={16} /> Service graph & traceback</div></div>
            <div className="p-3"><ServiceGraph graph={d.graph} highlight={top?.service} /></div>
            <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">Built from spans in the logs. Red edges carry errors; the outlined node is the top-ranked root cause.</div>
          </div>
          {d.similar?.length > 0 && <SimilarIncidents items={d.similar} />}
          {top?.code_location && <CodeContext loc={top.code_location} />}
          {d.deployments.length > 0 && (
            <div className="card">
              <div className="card-h"><div className="card-t"><GitCommitHorizontal size={16} /> Deployment evidence</div></div>
              {d.deployments.map((x) => (
                <div key={x.id} className="space-y-1 px-4 py-3 text-sm">
                  <div className="font-medium text-slate-800">{x.service} <Pill>{x.version}</Pill> <span className="mono text-slate-400">{x.commit}</span></div>
                  <div className="text-xs text-slate-500">{fmtDateTime(x.ts)} · {x.author}</div>
                  <div className="text-xs text-slate-600">{x.description}</div>
                  <div className="flex flex-wrap gap-1">{(x.changed_files || []).map((f) => <Pill key={f} className="mono">{f}</Pill>)}</div>
                </div>
              ))}
            </div>
          )}
          {d.feedback.length > 0 && <FeedbackLog d={d} />}
        </div>
      </div>

      <Timeline d={d} onEvent={setEventId} />
      <EventModal id={eventId} onClose={() => setEventId(null)} />
    </div>
  );
}

// ------------------------------------------------------------------ pipeline status strip
function PipelineStrip({ d }) {
  const rec = d.recommendations[0];
  const steps = [
    ["S1 Ingest", true], ["S2 Normalise", true], ["S3 Fingerprint", true], ["S4 Correlate", d.event_count > 0],
    ["S5 Traceback", (d.graph?.nodes || []).length > 0], ["S6 Diagnose", d.candidates.length > 0],
    ["S7 Recommend", !!rec], ["S8 Learn", d.feedback.length > 0],
  ];
  return (
    <div className="card flex flex-wrap items-center gap-1 px-3 py-2">
      <Workflow size={15} className="mr-1 text-slate-400" />
      {steps.map(([s, ok], i) => (
        <span key={s} className="flex items-center gap-1">
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${ok ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400"}`}>{ok ? "✓ " : ""}{s}</span>
          {i < steps.length - 1 && <ChevronRight size={12} className="text-slate-300" />}
        </span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ ranked candidates
function Candidates({ d, onChanged }) {
  const [open, setOpen] = useState(0);
  const [busy, setBusy] = useState(null);
  const send = async (c, verdict) => {
    setBusy(c.id + verdict);
    try {
      await api(`/api/v1/incidents/${d.id}/feedback`, { method: "POST", body: { verdict, candidate_id: c.id } });
      await onChanged();
    } finally { setBusy(null); }
  };
  const w = d.weights;
  return (
    <div className="card">
      <div className="card-h">
        <div className="card-t"><Target size={16} /> Root-cause candidates</div>
        <span className="mono text-[11px] text-slate-500">R = {SIGNALS.map((s) => `${w[s.key].toFixed(2)}·${s.key}`).join(" + ")}</span>
      </div>
      <div className="border-b border-slate-100 px-4 py-2"><SignalLegend /></div>
      {d.candidates.length === 0 && <Empty>Analysing…</Empty>}
      <div className="divide-y divide-slate-100">
        {d.candidates.map((c, i) => (
          <div key={c.id} className={i === 0 ? "bg-rose-50/30" : ""}>
            <button className="flex w-full items-center gap-3 px-4 py-3 text-left" onClick={() => setOpen(open === i ? -1 : i)}>
              <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold ${i === 0 ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-500"}`}>{c.rank}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-800">{c.service}</span>
                  <span className="mono truncate text-slate-500">{c.error_type || "error"}</span>
                  {c.verdict === "confirmed" && <Pill className="!bg-emerald-100 !text-emerald-700">confirmed</Pill>}
                  {c.verdict === "rejected" && <Pill className="!bg-slate-200">rejected</Pill>}
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <ScoreBar signals={c.signals} weights={w} />
                  <span className="w-10 text-right text-sm font-semibold tabular-nums text-slate-800">{c.score.toFixed(2)}</span>
                  {i === 0 && <ConfidenceBadge c={c} />}
                </div>
              </div>
              {open === i ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
            </button>
            {open === i && (
              <div className="space-y-3 px-4 pb-4 pl-14">
                <div className="mono rounded-lg bg-white p-2 text-slate-700 ring-1 ring-slate-100">{c.message}</div>
                <table className="w-full text-xs">
                  <tbody>
                    {SIGNALS.map((s) => (
                      <tr key={s.key} className="align-top">
                        <td className="w-36 py-1 pr-2 font-medium text-slate-600"><span className="mr-1.5 inline-block h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.key} · {d.signal_names[s.key]}</td>
                        <td className="w-24 py-1 pr-2">
                          <div className="h-1.5 w-full rounded-full bg-slate-100"><div className="h-1.5 rounded-full" style={{ width: `${c.signals[s.key] * 100}%`, background: s.color }} /></div>
                          <div className="mt-0.5 tabular-nums text-slate-400">{c.signals[s.key].toFixed(2)} × {w[s.key].toFixed(2)}</div>
                        </td>
                        <td className="py-1 text-slate-600">{c.reasons[s.key]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {c.confidence_detail && (
                  <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    <b className="text-slate-700">Confidence {c.confidence.toFixed(2)} ({c.confidence_detail.label})</b>
                    {" = 0.5 × R "}{c.confidence_detail.magnitude.toFixed(2)}
                    {" + 0.3 × agreement "}{c.confidence_detail.agreement.toFixed(2)}
                    {" + 0.2 × lead over next "}{c.confidence_detail.margin.toFixed(2)}
                    <span className="text-slate-400"> · signals pointing here: {c.confidence_detail.supporting.join(", ") || "none"}</span>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-500">{c.count} occurrences · first {fmtTime(c.first_seen)} · fingerprint <span className="mono">{c.fingerprint || "—"}</span></span>
                  <div className="flex-1" />
                  {d.status !== "resolved" && !c.verdict && <>
                    <button className="btn-ok !py-1 !text-xs" disabled={!!busy} onClick={() => send(c, "confirmed")}>
                      {busy === c.id + "confirmed" ? <Loader2 size={13} className="animate-spin" /> : <ThumbsUp size={13} />} Confirm root cause
                    </button>
                    <button className="btn-danger !py-1 !text-xs" disabled={!!busy} onClick={() => send(c, "rejected")}>
                      <ThumbsDown size={13} /> Reject
                    </button>
                  </>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const CONF = {
  high: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-200 text-slate-700",
};
function ConfidenceBadge({ c }) {
  const d = c.confidence_detail;
  if (!d) return null;
  return (
    <span title={`Magnitude of R ${d.magnitude}, signal agreement ${d.agreement}, lead over next candidate ${d.margin}`}
      className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${CONF[d.label]}`}>
      {d.label} confidence
    </span>
  );
}

// ------------------------------------------------------------------ similar past incidents
function SimilarIncidents({ items }) {
  return (
    <div className="card">
      <div className="card-h"><div className="card-t"><History size={16} /> Similar past incidents</div></div>
      <div className="divide-y divide-slate-100">
        {items.map((s) => (
          <Link key={s.incident_id} to={`/incidents/${s.incident_id}`} className="block space-y-1 px-4 py-3 hover:bg-slate-50">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-400">#{s.incident_id}</span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{s.title}</span>
              <Pill className="!bg-brand-50 !text-brand-700">{Math.round(s.similarity * 100)}% similar</Pill>
            </div>
            <div className="text-xs text-slate-500">Root cause confirmed: <b className="font-medium text-slate-700">{s.service}</b> · {s.error_type}</div>
            {s.fix && <div className="text-xs text-emerald-700">Fixed by: {s.fix}</div>}
          </Link>
        ))}
      </div>
      <div className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">Earlier incidents with an engineer-confirmed root cause that match this failure. They raise the H (history) signal and are given to the AI as evidence.</div>
    </div>
  );
}

// ------------------------------------------------------------------ code context
function CodeContext({ loc }) {
  return (
    <div className="card overflow-hidden">
      <div className="card-h">
        <div className="card-t"><Code2 size={16} /> Code location</div>
        {loc.changed_in_deployment && <Pill className="!bg-amber-100 !text-amber-800">changed in {loc.changed_in_deployment}</Pill>}
      </div>
      <div className="px-4 py-2 text-xs text-slate-600">
        <span className="mono font-medium text-slate-800">{loc.repo_path || loc.file}</span>:{loc.line} · <span className="mono">{loc.function}</span>
        {!loc.resolved && <span className="ml-2 text-amber-600">(not found in repository snapshot)</span>}
      </div>
      {loc.snippet && (
        <pre className="mono overflow-auto bg-slate-900 py-2 text-slate-300">
          {loc.snippet.map((ln, i) => {
            const n = loc.start_line + i;
            const hit = n === loc.line;
            return (
              <div key={n} className={hit ? "bg-rose-500/25 text-white" : ""}>
                <span className={`inline-block w-12 select-none pr-3 text-right ${hit ? "text-rose-300" : "text-slate-500"}`}>{n}</span>{ln || " "}
              </div>
            );
          })}
        </pre>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ recommendation
function Refs({ text, evidence }) {
  // turns "... [E2, E5]" into hoverable evidence chips
  const parts = String(text).split(/(E\d+)/g);
  return parts.map((p, i) => {
    const ev = /^E\d+$/.test(p) && evidence.find((e) => e.id === p);
    return ev ? <span key={i} title={ev.text} className="mx-0.5 cursor-help rounded bg-brand-50 px-1 text-[11px] font-semibold text-brand-700 ring-1 ring-brand-100">{p}</span> : <span key={i}>{p}</span>;
  });
}

const SOURCE = {
  playbook: { label: "Known-error playbook", icon: BookOpen, cls: "bg-emerald-50 text-emerald-700" },
  llm: { label: "AI (Gemini)", icon: Bot, cls: "bg-brand-50 text-brand-700" },
  rules: { label: "Rule-based", icon: ListChecks, cls: "bg-slate-100 text-slate-700" },
};

function Recommendation({ d, rec, onChanged, onEvent }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [showEv, setShowEv] = useState(false);
  const ask = async () => {
    setBusy(true); setErr(null);
    try { await api(`/api/v1/incidents/${d.id}/recommend`, { method: "POST" }); await onChanged(); }
    catch (e) { setErr(e.message); } finally { setBusy(false); }
  };
  const src = rec ? SOURCE[rec.source] || SOURCE.rules : null;
  const passed = rec?.validation?.status === "passed";
  return (
    <div className="card">
      <div className="card-h">
        <div className="card-t">{d.category === "security" ? <ShieldAlert size={16} /> : <ListChecks size={16} />} Recommended fix</div>
        <button className="btn-ghost !py-1 !text-xs" onClick={ask} disabled={busy || !d.candidates.length}
          title={d.ai.enabled ? `Ask ${d.ai.model} using the evidence pack` : "No GEMINI_API_KEY configured - rules will be used"}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} {d.ai.enabled ? "Ask Gemini" : "Regenerate"}
        </button>
      </div>
      {err && <div className="mx-4 mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{err}</div>}
      {!rec && <Empty>{d.recommendation_pending ? <span className="inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Waiting for the incident to settle, then generating…</span> : "No recommendation yet."}</Empty>}
      {rec && (
        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${src.cls}`}><src.icon size={12} /> {src.label}{rec.model ? ` · ${rec.model}` : ""}</span>
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${passed ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
              <ShieldCheck size={12} /> validator: {rec.validation.status}
            </span>
            <span className="text-[11px] text-slate-500">confidence {(rec.confidence * 100).toFixed(0)}%{rec.latency_ms ? ` · ${(rec.latency_ms / 1000).toFixed(1)} s` : ""}</span>
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-800">{rec.summary}</div>
            <p className="mt-1 text-sm leading-relaxed text-slate-600"><Refs text={rec.root_cause} evidence={rec.evidence} /></p>
          </div>
          <ol className="space-y-2">
            {rec.fix_steps.map((s, i) => (
              <li key={i} className="flex gap-2.5 text-sm text-slate-700">
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-slate-900 text-[11px] font-semibold text-white">{i + 1}</span>
                <span><Refs text={s} evidence={rec.evidence} /></span>
              </li>
            ))}
          </ol>
          {rec.validation.issues.length > 0 && (
            <ul className="space-y-1 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800">
              {rec.validation.issues.map((x) => <li key={x}>• {x}</li>)}
            </ul>
          )}
          <div>
            <button className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800" onClick={() => setShowEv((v) => !v)}>
              {showEv ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Evidence pack ({rec.evidence.length} items{rec.source === "llm" ? " sent to the AI" : ""})
            </button>
            {showEv && (
              <div className="mt-2 space-y-1.5">
                {rec.evidence.map((e) => (
                  <div key={e.id} className="flex gap-2 rounded-lg bg-slate-50 p-2 text-xs">
                    <span className="h-fit rounded bg-brand-50 px-1 font-semibold text-brand-700">{e.id}</span>
                    <Pill className="h-fit">{e.kind}</Pill>
                    <pre className="mono min-w-0 flex-1 whitespace-pre-wrap break-words text-slate-600">{e.text.length > 600 ? e.text.slice(0, 600) + "…" : e.text}</pre>
                    {e.event_id && <button className="h-fit text-brand-600 hover:underline" onClick={() => onEvent(e.event_id)}>open</button>}
                  </div>
                ))}
              </div>
            )}
          </div>
          {d.recommendations.length > 1 && <div className="text-[11px] text-slate-400">{d.recommendations.length - 1} earlier recommendation(s) kept for audit.</div>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ feedback history (S8)
function FeedbackLog({ d }) {
  return (
    <div className="card">
      <div className="card-h"><div className="card-t"><History size={16} /> Engineer feedback (S8)</div></div>
      <div className="divide-y divide-slate-100">
        {d.feedback.map((f) => (
          <div key={f.id} className="space-y-1.5 px-4 py-3 text-xs">
            <div className="flex items-center gap-2">
              {f.verdict === "confirmed" ? <Check size={14} className="text-emerald-600" /> : <ThumbsDown size={14} className="text-rose-600" />}
              <span className="font-medium text-slate-700">{f.user} {f.verdict} candidate #{d.candidates.find((c) => c.id === f.candidate_id)?.rank ?? "?"}</span>
              <span className="text-slate-400">{fmtTime(f.created_at)}</span>
            </div>
            {f.weights_before && (
              <div className="flex flex-wrap gap-1.5">
                {SIGNALS.map((s) => {
                  const a = f.weights_before[s.key], b = f.weights_after[s.key];
                  const diff = b - a;
                  return <Pill key={s.key}>{s.key} {a.toFixed(2)}→{b.toFixed(2)} <span className={diff > 0 ? "text-emerald-600" : diff < 0 ? "text-rose-600" : ""}>{diff > 0 ? "▲" : diff < 0 ? "▼" : ""}</span></Pill>;
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ timeline
function Timeline({ d, onEvent }) {
  const [errorsOnly, setErrorsOnly] = useState(false);
  const top = d.candidates[0];
  const topIds = new Set(top?.event_ids || []);
  const items = d.timeline.filter((e) => !errorsOnly || e.is_error);
  return (
    <div className="card">
      <div className="card-h">
        <div className="card-t">Incident timeline <span className="font-normal text-slate-400">({d.timeline.length} events)</span></div>
        <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} /> errors only</label>
      </div>
      <div className="max-h-[440px] overflow-auto">
        {items.map((e) => (
          <button key={e.id} onClick={() => onEvent(e.id)} className={`flex w-full items-start gap-2 border-b border-slate-50 px-3 py-1.5 text-left hover:bg-slate-50 ${topIds.has(e.id) ? "bg-rose-50/60" : ""}`}>
            <span className="mono shrink-0 pt-0.5 text-slate-400">{fmtTime(e.ts)}.{String(new Date(e.ts).getMilliseconds()).padStart(3, "0")}</span>
            <LevelBadge level={e.level} />
            <span className="w-32 shrink-0 truncate pt-0.5 text-xs font-medium text-slate-600">{e.service}</span>
            <span className="mono min-w-0 flex-1 truncate pt-0.5 text-slate-700">{e.message}</span>
            {e.trace_id && <span className="mono hidden shrink-0 pt-0.5 text-slate-300 lg:inline">{e.trace_id.slice(0, 8)}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
