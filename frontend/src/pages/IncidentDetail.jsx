import {
  ArrowLeft, ArrowRight, BookOpen, Bot, Check, ChevronDown, ChevronRight, Clock, Code2, Crosshair, GitCommitHorizontal,
  History, Lightbulb, ListChecks, Loader2, MapPin, Network, RefreshCw, ScrollText, ShieldAlert, ShieldCheck, Sparkles,
  ThumbsDown, ThumbsUp, Wrench,
} from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import EventModal from "../components/EventModal.jsx";
import ServiceGraph from "../components/ServiceGraph.jsx";
import {
  CategoryBadge, Empty, Help, LevelBadge, Notice, Pill, ScoreBar, SeverityBadge, SignalLegend, SIGNALS, StatusBadge,
} from "../components/ui.jsx";
import { api, fmtDateTime, fmtTime } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const TABS = [
  { id: "cause", label: "Root cause", icon: Crosshair },
  { id: "fix", label: "Recommended fix", icon: Wrench },
  { id: "map", label: "Service map & code", icon: Network },
  { id: "timeline", label: "Timeline", icon: ScrollText },
  { id: "history", label: "History & feedback", icon: History },
];

export default function IncidentDetail() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "cause";
  const setTab = (t) => setParams({ tab: t }, { replace: true });
  const { data: d, error, reload } = usePoll(() => api(`/api/v1/incidents/${id}`), 3000, [id]);
  const [eventId, setEventId] = useState(null);
  const [busy, setBusy] = useState(null);

  if (error && !d) return <div className="card p-6 text-sm text-rose-600">{error}</div>;
  if (!d) return <div className="card h-64 animate-pulse" />;
  const top = d.candidates[0];
  const rec = d.recommendations[0];

  const sendFeedback = async (c, verdict) => {
    setBusy(c.id + verdict);
    try {
      await api(`/api/v1/incidents/${d.id}/feedback`, { method: "POST", body: { verdict, candidate_id: c.id } });
      await reload();
    } finally { setBusy(null); }
  };

  return (
    <div className="space-y-6">
      <div>
        <Link to="/incidents" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft size={15} /> All incidents</Link>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-slate-400">Incident #{d.id}</span>
          <StatusBadge status={d.status} /><SeverityBadge severity={d.severity} /><CategoryBadge category={d.category} />
        </div>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-900">{d.title}</h1>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-500">
          <span className="flex items-center gap-1.5"><Clock size={14} /> {fmtDateTime(d.window_start)} – {fmtTime(d.window_end)}</span>
          <span>{d.error_count} errors in {d.event_count} log lines</span>
          <span>Services involved: {d.services.join(", ")}</span>
        </div>
      </div>

      <Summary d={d} top={top} rec={rec} busy={busy} onFeedback={sendFeedback} onTab={setTab} />
      <AnalysisSteps d={d} />

      <div>
        <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`-mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition ${tab === t.id ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
              <t.icon size={16} /> {t.label}
              {t.id === "fix" && rec && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
              {t.id === "history" && d.similar?.length > 0 && <span className="rounded-full bg-brand-50 px-1.5 text-[11px] text-brand-700">{d.similar.length}</span>}
            </button>
          ))}
        </div>
        <div className="pt-6">
          {tab === "cause" && <Candidates d={d} busy={busy} onFeedback={sendFeedback} />}
          {tab === "fix" && <Recommendation d={d} rec={rec} onChanged={reload} onEvent={setEventId} />}
          {tab === "map" && <MapAndCode d={d} top={top} />}
          {tab === "timeline" && <Timeline d={d} onEvent={setEventId} />}
          {tab === "history" && <HistoryTab d={d} />}
        </div>
      </div>
      <EventModal id={eventId} onClose={() => setEventId(null)} />
    </div>
  );
}

// ------------------------------------------------------------------ plain-English summary
function strongest(c, w, n = 2) {
  if (!c) return [];
  return SIGNALS.map((s) => ({ ...s, v: (w[s.key] || 0) * (c.signals[s.key] || 0), reason: c.reasons[s.key] }))
    .filter((s) => s.v > 0.02).sort((a, b) => b.v - a.v).slice(0, n);
}

function Summary({ d, top, rec, busy, onFeedback, onTab }) {
  const why = strongest(top, d.weights, 3);
  const box = "flex flex-col bg-white p-5";
  const head = "mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider";
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-slate-100 px-5 py-3">
        <Sparkles size={16} className="text-brand-600" />
        <span className="text-[15px] font-semibold text-slate-800">Summary</span>
        <span className="text-xs text-slate-400">· the incident explained in four points</span>
      </div>
      <div className="grid gap-px bg-slate-100 md:grid-cols-2 xl:grid-cols-4">
        <div className={box}>
          <div className={`${head} text-rose-600`}><ShieldAlert size={14} /> What happened</div>
          <div className="space-y-1.5 text-sm text-slate-700">
            {d.detection.slice(0, 2).map((x) => <div key={x.label}>{x.label}</div>)}
            <div className="text-slate-500">{d.services.length} service{d.services.length > 1 ? "s" : ""} affected, {d.error_count} errors in total.</div>
          </div>
        </div>
        <div className={box}>
          <div className={`${head} text-brand-600`}><MapPin size={14} /> Where it started</div>
          {top ? (
            <>
              <div className="text-lg font-semibold text-slate-900">{top.service}</div>
              <div className="mono mt-0.5 truncate text-slate-500" title={top.message}>{top.error_type || top.message}</div>
              <div className="mt-2"><ConfidenceBadge c={top} /></div>
              <div className="mt-auto pt-3">
                {top.verdict === "confirmed" && <span className="inline-flex items-center gap-1 text-sm font-medium text-emerald-700"><Check size={15} /> Confirmed by an engineer</span>}
                {top.verdict === "rejected" && <span className="text-sm text-slate-500">Rejected by an engineer</span>}
                {!top.verdict && d.status !== "resolved" && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="mr-1 text-xs text-slate-500">Is this correct?</span>
                    <button className="btn-ok btn-sm" disabled={!!busy} onClick={() => onFeedback(top, "confirmed")}>
                      {busy === top.id + "confirmed" ? <Loader2 size={13} className="animate-spin" /> : <ThumbsUp size={13} />} Yes
                    </button>
                    <button className="btn-danger btn-sm" disabled={!!busy} onClick={() => onFeedback(top, "rejected")}><ThumbsDown size={13} /> No</button>
                  </div>
                )}
              </div>
            </>
          ) : <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 size={14} className="animate-spin" /> Analysing…</div>}
        </div>
        <div className={box}>
          <div className={`${head} text-amber-600`}><Lightbulb size={14} /> Why we think so</div>
          <ul className="space-y-2 text-sm text-slate-700">
            {why.map((s) => (
              <li key={s.key} className="flex gap-2">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-sm" style={{ background: s.color }} />
                <span><b className="font-medium text-slate-800">{s.name}:</b> {s.reason}</span>
              </li>
            ))}
            {!why.length && <li className="text-slate-500">Waiting for analysis…</li>}
          </ul>
          <button onClick={() => onTab("cause")} className="mt-auto inline-flex items-center gap-1 pt-3 text-sm font-semibold text-brand-600 hover:underline">Full explanation <ArrowRight size={14} /></button>
        </div>
        <div className={box}>
          <div className={`${head} text-emerald-600`}><Wrench size={14} /> How to fix it</div>
          {rec ? (
            <>
              <div className="text-sm font-medium text-slate-800">{rec.summary}</div>
              {rec.fix_steps[0] && <div className="mt-1.5 text-sm text-slate-600">First step: {stripRefs(rec.fix_steps[0])}</div>}
              <button onClick={() => onTab("fix")} className="mt-auto inline-flex items-center gap-1 pt-3 text-sm font-semibold text-brand-600 hover:underline">All {rec.fix_steps.length} steps <ArrowRight size={14} /></button>
            </>
          ) : (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              {d.recommendation_pending ? <><Loader2 size={14} className="animate-spin" /> Preparing a recommendation…</> : "No recommendation yet."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const stripRefs = (t) => String(t).replace(/\s*\[(E\d+(,\s*)?)+\]/g, "").replace(/\s*\(E\d+(,\s*E\d+)*\)/g, "");

// ------------------------------------------------------------------ the 8 analysis steps (IDF S1-S8)
function AnalysisSteps({ d }) {
  const rec = d.recommendations[0];
  const steps = [
    ["Collected", "Logs received from all services", true],
    ["Cleaned up", "Different log formats converted to one standard format", true],
    ["Grouped", "Similar errors given the same error signature", true],
    ["Linked", "Related errors joined into one incident", d.event_count > 0],
    ["Traced", "Followed requests from service to service", (d.graph?.nodes || []).length > 0],
    ["Ranked", "Suspects scored on five clues", d.candidates.length > 0],
    ["Fix suggested", "Recommendation prepared and checked against the evidence", !!rec],
    ["Learned", "Engineer feedback used to improve future rankings", d.feedback.length > 0],
  ];
  return (
    <div className="card flex flex-wrap items-center gap-x-1 gap-y-2 px-5 py-3">
      <span className="mr-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500">How this was analysed <Help>Every incident goes through the same eight steps. Green means the step is complete. Hover over a step for details.</Help></span>
      {steps.map(([name, help, ok], i) => (
        <span key={name} className="flex items-center gap-1" title={help}>
          <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${ok ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400"}`}>
            {ok ? <Check size={12} /> : <span className="text-[10px]">{i + 1}</span>} {name}
          </span>
          {i < steps.length - 1 && <ChevronRight size={13} className="text-slate-300" />}
        </span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ ranked candidates
function Candidates({ d, busy, onFeedback }) {
  const [open, setOpen] = useState(0);
  const w = d.weights;
  return (
    <div className="card">
      <div className="card-h flex-wrap">
        <div>
          <div className="card-t"><Crosshair size={16} /> Possible root causes, most likely first</div>
          <div className="card-d mt-0.5">Each suspect gets a score from 0 to 1 based on five clues. The longer the bar, the more likely it is where the problem started.</div>
        </div>
        <span className="mono flex items-center gap-1.5 text-[11px] text-slate-400">
          Score = {SIGNALS.map((s) => `${w[s.key].toFixed(2)}·${s.key}`).join(" + ")}
          <Help>The weights (numbers in front of each letter) are learned: they change when engineers confirm or reject a root cause. T, D, A, C and H are the five clues below.</Help>
        </span>
      </div>
      <div className="border-b border-slate-100 bg-slate-50/60 px-5 py-2.5"><SignalLegend /></div>
      {d.candidates.length === 0 && <Empty>Analysing…</Empty>}
      <div className="divide-y divide-slate-100">
        {d.candidates.map((c, i) => (
          <div key={c.id} className={i === 0 ? "bg-brand-50/30" : ""}>
            <button className="flex w-full items-center gap-4 px-5 py-4 text-left" onClick={() => setOpen(open === i ? -1 : i)}>
              <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold ${i === 0 ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500"}`}>{c.rank}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold text-slate-900">{c.service}</span>
                  {i === 0 && <span className="rounded-full bg-brand-600 px-2 py-0.5 text-[11px] font-semibold text-white">Most likely</span>}
                  <span className="mono truncate text-slate-500">{c.error_type || "error"}</span>
                  {c.verdict === "confirmed" && <Pill className="!bg-emerald-100 !text-emerald-700">✓ Confirmed</Pill>}
                  {c.verdict === "rejected" && <Pill className="!bg-slate-200">Rejected</Pill>}
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <ScoreBar signals={c.signals} weights={w} />
                  <span className="w-12 text-right text-sm font-semibold tabular-nums text-slate-800">{c.score.toFixed(2)}</span>
                  {i === 0 && <ConfidenceBadge c={c} />}
                </div>
              </div>
              {open === i ? <ChevronDown size={18} className="text-slate-400" /> : <ChevronRight size={18} className="text-slate-400" />}
            </button>
            {open === i && (
              <div className="space-y-4 px-5 pb-5 md:pl-[4.25rem]">
                <div>
                  <div className="eyebrow mb-1">Error message</div>
                  <div className="mono rounded-lg bg-white p-3 text-slate-700 ring-1 ring-slate-200">{c.message}</div>
                </div>
                <div>
                  <div className="eyebrow mb-2">The five clues</div>
                  <div className="divide-y divide-slate-100 rounded-lg ring-1 ring-slate-200">
                    {SIGNALS.map((s) => (
                      <div key={s.key} className="grid gap-2 bg-white px-3 py-2.5 text-sm md:grid-cols-[220px_140px_1fr] md:items-center">
                        <span className="flex items-center gap-2 font-medium text-slate-700">
                          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.name}
                          <span className="text-xs text-slate-400">({s.key})</span><Help>{s.help}</Help>
                        </span>
                        <span>
                          <span className="block h-1.5 w-full rounded-full bg-slate-100"><span className="block h-1.5 rounded-full" style={{ width: `${c.signals[s.key] * 100}%`, background: s.color }} /></span>
                          <span className="mt-0.5 block text-[11px] tabular-nums text-slate-400">value {c.signals[s.key].toFixed(2)} × weight {w[s.key].toFixed(2)}</span>
                        </span>
                        <span className="text-slate-600">{c.reasons[s.key]}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {c.confidence_detail && (
                  <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-600">
                    <b className="text-slate-800">Confidence {Math.round(c.confidence * 100)}% ({c.confidence_detail.label})</b> is based on three things:
                    the score itself ({c.confidence_detail.magnitude.toFixed(2)}), how many clues agree ({c.confidence_detail.agreement.toFixed(2)};
                    {" "}clues pointing here: {c.confidence_detail.supporting.map((k) => SIGNALS.find((s) => s.key === k)?.name || k).join(", ") || "none"})
                    {" "}and how far ahead it is of the next suspect ({c.confidence_detail.margin.toFixed(2)}).
                    <span className="mono ml-1 text-slate-400">= 0.5×score + 0.3×agreement + 0.2×lead</span>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-500">Seen {c.count} times · first at {fmtTime(c.first_seen)} · error signature <span className="mono">{c.fingerprint || "—"}</span></span>
                  <div className="flex-1" />
                  {d.status !== "resolved" && !c.verdict && <>
                    <button className="btn-ok btn-sm" disabled={!!busy} onClick={() => onFeedback(c, "confirmed")}>
                      {busy === c.id + "confirmed" ? <Loader2 size={13} className="animate-spin" /> : <ThumbsUp size={13} />} Yes, this is the root cause
                    </button>
                    <button className="btn-danger btn-sm" disabled={!!busy} onClick={() => onFeedback(c, "rejected")}>
                      <ThumbsDown size={13} /> Not the cause
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
  high: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  medium: "bg-amber-50 text-amber-700 ring-amber-200",
  low: "bg-slate-100 text-slate-600 ring-slate-200",
};
function ConfidenceBadge({ c }) {
  const d = c.confidence_detail;
  if (!d) return null;
  return (
    <span title="How sure the analyzer is: combines the score, how many clues agree, and the lead over the next suspect"
      className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${CONF[d.label]}`}>
      {d.label[0].toUpperCase() + d.label.slice(1)} confidence · {Math.round(c.confidence * 100)}%
    </span>
  );
}

// ------------------------------------------------------------------ map & code tab
function MapAndCode({ d, top }) {
  return (
    <div className="grid gap-6 xl:grid-cols-5">
      <div className="card xl:col-span-3">
        <div className="card-h">
          <div>
            <div className="card-t"><Network size={16} /> Service map</div>
            <div className="card-d">How requests flowed between services during this incident</div>
          </div>
        </div>
        <div className="p-4"><ServiceGraph graph={d.graph} highlight={top?.service} /></div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> No errors</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-rose-600" /> Has errors</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-5 rounded border-2 border-rose-600" /> Most likely root cause</span>
          <span className="flex items-center gap-1.5"><span className="w-5 border-t-2 border-dashed border-rose-600" /> Failed calls</span>
        </div>
      </div>
      <div className="space-y-6 xl:col-span-2">
        {top?.code_location ? <CodeContext loc={top.code_location} /> : (
          <div className="card"><Empty icon={Code2} title="No code location">This error did not include a stack trace that points to a line of code.</Empty></div>
        )}
        <div className="card">
          <div className="card-h">
            <div>
              <div className="card-t"><GitCommitHorizontal size={16} /> Recent releases</div>
              <div className="card-d">New versions deployed shortly before the incident</div>
            </div>
          </div>
          {d.deployments.length === 0 && <Empty>No releases in the hour before this incident.</Empty>}
          {d.deployments.map((x) => (
            <div key={x.id} className="space-y-1.5 border-b border-slate-50 px-5 py-3.5 text-sm last:border-0">
              <div className="flex flex-wrap items-center gap-2 font-medium text-slate-800">{x.service} <Pill className="!bg-brand-50 !text-brand-700">{x.version}</Pill> <span className="mono text-slate-400">{x.commit}</span></div>
              <div className="text-xs text-slate-500">{fmtDateTime(x.ts)} · by {x.author}</div>
              <div className="text-sm text-slate-600">{x.description}</div>
              {(x.changed_files || []).length > 0 && (
                <div className="flex flex-wrap items-center gap-1 text-xs text-slate-500">Files changed: {x.changed_files.map((f) => <Pill key={f} className="mono">{f}</Pill>)}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function CodeContext({ loc }) {
  return (
    <div className="card overflow-hidden">
      <div className="card-h">
        <div>
          <div className="card-t"><Code2 size={16} /> Where it failed in the code</div>
          <div className="card-d">Found by following the error's stack trace into the code repository</div>
        </div>
        {loc.changed_in_deployment && <Pill className="!bg-amber-100 !text-amber-800">changed in {loc.changed_in_deployment}</Pill>}
      </div>
      <div className="px-5 py-2.5 text-xs text-slate-600">
        <span className="mono font-medium text-slate-800">{loc.repo_path || loc.file}</span> · line {loc.line} · <span className="mono">{loc.function}</span>
        {!loc.resolved && <span className="ml-2 text-amber-600">(file not found in the repository)</span>}
      </div>
      {loc.snippet && (
        <pre className="mono overflow-auto bg-slate-950 py-3 text-slate-300">
          {loc.snippet.map((ln, i) => {
            const n = loc.start_line + i;
            const hit = n === loc.line;
            return (
              <div key={n} className={hit ? "bg-rose-500/25 text-white" : ""}>
                <span className={`inline-block w-12 select-none pr-3 text-right ${hit ? "text-rose-300" : "text-slate-600"}`}>{n}</span>{ln || " "}
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
  playbook: { label: "From the known issues library", icon: BookOpen, cls: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
  llm: { label: "AI assistant (Gemini)", icon: Bot, cls: "bg-brand-50 text-brand-700 ring-brand-200" },
  rules: { label: "Automatic rules", icon: ListChecks, cls: "bg-slate-100 text-slate-700 ring-slate-200" },
};
const KIND = { candidate: "Suspect", event: "Log line", deployment: "Release", code: "Code", history: "History", graph: "Service map" };

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
      <div className="card-h flex-wrap">
        <div>
          <div className="card-t">{d.category === "security" ? <ShieldAlert size={16} /> : <Wrench size={16} />} Recommended fix</div>
          <div className="card-d mt-0.5">What went wrong and the steps to fix it. Numbers like <span className="rounded bg-brand-50 px-1 font-semibold text-brand-700">E2</span> point to the evidence each statement is based on.</div>
        </div>
        <button className="btn-ghost btn-sm" onClick={ask} disabled={busy || !d.candidates.length}
          title={d.ai.enabled ? `Ask the AI assistant (${d.ai.model}) again using the collected evidence` : "AI assistant is not configured; automatic rules will be used"}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} {busy ? "Asking…" : d.ai.enabled ? "Ask AI again" : "Regenerate"}
        </button>
      </div>
      {err && <div className="mx-5 mt-4"><Notice tone="error">{err}</Notice></div>}
      {!rec && <Empty icon={Wrench} title={d.recommendation_pending ? "Preparing a recommendation" : "No recommendation yet"}>
        {d.recommendation_pending ? <span className="inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Waiting a few seconds for the incident to settle, then generating…</span> : "Click “Ask AI again” to generate one."}
      </Empty>}
      {rec && (
        <div className="space-y-5 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${src.cls}`}><src.icon size={13} /> {src.label}{rec.model ? ` · ${rec.model}` : ""}</span>
            <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${passed ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-amber-50 text-amber-800 ring-amber-200"}`}
              title="Every answer is checked automatically: the evidence it refers to must exist, fix steps must be present and no dangerous commands are allowed">
              <ShieldCheck size={13} /> {passed ? "Verified against evidence" : "Check needed"}
            </span>
            <span className="text-xs text-slate-500">confidence {(rec.confidence * 100).toFixed(0)}%{rec.latency_ms ? ` · generated in ${(rec.latency_ms / 1000).toFixed(1)} s` : ""}</span>
          </div>
          <div className="rounded-xl bg-slate-50 p-4">
            <div className="eyebrow mb-1">Root cause</div>
            <div className="text-base font-semibold text-slate-900">{rec.summary}</div>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-600"><Refs text={rec.root_cause} evidence={rec.evidence} /></p>
          </div>
          <div>
            <div className="eyebrow mb-2">Steps to fix</div>
            <ol className="space-y-2.5">
              {rec.fix_steps.map((s, i) => (
                <li key={i} className="flex gap-3 text-sm leading-relaxed text-slate-700">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">{i + 1}</span>
                  <span className="pt-0.5"><Refs text={s} evidence={rec.evidence} /></span>
                </li>
              ))}
            </ol>
          </div>
          {rec.validation.issues.length > 0 && (
            <ul className="space-y-1 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
              {rec.validation.issues.map((x) => <li key={x}>• {x}</li>)}
            </ul>
          )}
          <div className="border-t border-slate-100 pt-4">
            <button className="flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900" onClick={() => setShowEv((v) => !v)}>
              {showEv ? <ChevronDown size={15} /> : <ChevronRight size={15} />} Evidence used ({rec.evidence.length} items{rec.source === "llm" ? ", the only information given to the AI" : ""})
            </button>
            {showEv && (
              <div className="mt-3 space-y-1.5">
                {rec.evidence.map((e) => (
                  <div key={e.id} className="flex gap-2 rounded-lg bg-slate-50 p-2.5 text-xs">
                    <span className="h-fit rounded bg-brand-50 px-1 font-semibold text-brand-700">{e.id}</span>
                    <Pill className="h-fit">{KIND[e.kind] || e.kind}</Pill>
                    <pre className="mono min-w-0 flex-1 whitespace-pre-wrap break-words text-slate-600">{e.text.length > 600 ? e.text.slice(0, 600) + "…" : e.text}</pre>
                    {e.event_id && <button className="h-fit font-medium text-brand-600 hover:underline" onClick={() => onEvent(e.event_id)}>View log</button>}
                  </div>
                ))}
              </div>
            )}
          </div>
          {d.recommendations.length > 1 && <div className="text-xs text-slate-400">{d.recommendations.length - 1} earlier recommendation(s) are kept for the record.</div>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ history tab
function HistoryTab({ d }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card">
        <div className="card-h">
          <div>
            <div className="card-t"><History size={16} /> Similar past incidents</div>
            <div className="card-d">Earlier problems like this one whose root cause was confirmed</div>
          </div>
        </div>
        {!d.similar?.length && <Empty icon={History} title="Nothing similar yet">When an engineer confirms the root cause of an incident, similar future incidents will show it here, with the fix that worked.</Empty>}
        <div className="divide-y divide-slate-100">
          {(d.similar || []).map((s) => (
            <Link key={s.incident_id} to={`/incidents/${s.incident_id}`} className="block space-y-1 px-5 py-3.5 hover:bg-slate-50">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-slate-400">#{s.incident_id}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{s.title}</span>
                <Pill className="!bg-brand-50 !text-brand-700">{Math.round(s.similarity * 100)}% similar</Pill>
              </div>
              <div className="text-xs text-slate-500">Confirmed root cause: <b className="font-medium text-slate-700">{s.service}</b> · {s.error_type}</div>
              {s.fix && <div className="text-xs text-emerald-700">What fixed it: {s.fix}</div>}
            </Link>
          ))}
        </div>
      </div>
      <div className="card">
        <div className="card-h">
          <div>
            <div className="card-t"><ThumbsUp size={16} /> Engineer feedback</div>
            <div className="card-d">Each answer adjusts how much the five clues count in future</div>
          </div>
        </div>
        {d.feedback.length === 0 && <Empty icon={ThumbsUp} title="No feedback yet">Use “Yes / No” on the most likely root cause. The analyzer learns from every answer.</Empty>}
        <div className="divide-y divide-slate-100">
          {d.feedback.map((f) => (
            <div key={f.id} className="space-y-2 px-5 py-3.5 text-sm">
              <div className="flex items-center gap-2">
                {f.verdict === "confirmed" ? <Check size={15} className="text-emerald-600" /> : <ThumbsDown size={15} className="text-rose-600" />}
                <span className="font-medium capitalize text-slate-700">{f.user}</span>
                <span className="text-slate-600">{f.verdict === "confirmed" ? "confirmed" : "rejected"} suspect #{d.candidates.find((c) => c.id === f.candidate_id)?.rank ?? "?"}</span>
                <span className="text-xs text-slate-400">{fmtTime(f.created_at)}</span>
              </div>
              {f.weights_before && (
                <div className="flex flex-wrap gap-1.5">
                  {SIGNALS.map((s) => {
                    const a = f.weights_before[s.key], b = f.weights_after[s.key];
                    const diff = b - a;
                    return <Pill key={s.key}>{s.name} {a.toFixed(2)}→{b.toFixed(2)} <span className={diff > 0 ? "text-emerald-600" : diff < 0 ? "text-rose-600" : ""}>{diff > 0 ? "▲" : diff < 0 ? "▼" : ""}</span></Pill>;
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
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
      <div className="card-h flex-wrap">
        <div>
          <div className="card-t"><ScrollText size={16} /> Timeline <span className="font-normal text-slate-400">({d.timeline.length} log lines)</span></div>
          <div className="card-d">Every log line in this incident in time order. Highlighted lines belong to the most likely root cause. Click a line for details.</div>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} /> Errors only</label>
      </div>
      <div className="max-h-[560px] overflow-auto">
        {items.map((e) => (
          <button key={e.id} onClick={() => onEvent(e.id)} className={`flex w-full items-start gap-3 border-b border-slate-50 px-4 py-2 text-left hover:bg-slate-50 ${topIds.has(e.id) ? "bg-brand-50/60" : ""}`}>
            <span className="mono shrink-0 pt-0.5 text-slate-400">{fmtTime(e.ts)}.{String(new Date(e.ts).getMilliseconds()).padStart(3, "0")}</span>
            <LevelBadge level={e.level} />
            <span className="w-36 shrink-0 truncate pt-0.5 text-xs font-medium text-slate-600">{e.service}</span>
            <span className="mono min-w-0 flex-1 truncate pt-0.5 text-slate-700">{e.message}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
