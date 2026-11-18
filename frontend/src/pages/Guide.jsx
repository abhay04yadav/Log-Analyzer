import {
  ArrowRight, Bot, Crosshair, FileText, GitMerge, GraduationCap, Layers, Network, PlugZap, Radar, ShieldCheck, Siren,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader, SIGNALS } from "../components/ui.jsx";

const STEPS = [
  { icon: PlugZap, title: "Collect", text: "Every service sends its log lines to the analyzer as they happen, over a secure API. Files can also be uploaded." },
  { icon: FileText, title: "Clean up", text: "Logs come in different formats (JSON, key=value, plain text, Java and Python stack traces). They are converted to one standard format, and passwords and keys are hidden." },
  { icon: Layers, title: "Group", text: "Errors that differ only in numbers or IDs get the same error signature, so 500 copies of one error count as one error type." },
  { icon: Radar, title: "Detect", text: "A problem is raised when errors jump above their normal level, a critical or known error appears, or someone keeps failing to log in." },
  { icon: GitMerge, title: "Link", text: "Errors with the same signature, the same request ID or close in time are joined into one incident, so one problem means one alert." },
  { icon: Network, title: "Trace", text: "Requests are followed from service to service to build a map of who called whom, and where the calls failed." },
  { icon: Crosshair, title: "Rank", text: "Every failing service is a suspect. Each one is scored on five clues, and the highest score is the most likely root cause." },
  { icon: Wrench, title: "Recommend", text: "A fix is written from the known issues library or by the AI assistant, using only the collected evidence, and is checked before it is shown." },
  { icon: GraduationCap, title: "Learn", text: "When an engineer confirms or rejects a root cause, the importance of each clue is adjusted, so the next ranking is better." },
];

const TERMS = [
  ["Log", "A line of text an application writes about what it is doing, e.g. “payment failed: timeout”."],
  ["Service", "One part of the application, e.g. the payment service or the shopping-cart service."],
  ["Incident", "One problem. A group of related errors that should be handled together."],
  ["Root cause", "The service and error where the problem actually started. Other services often fail only because of it."],
  ["Error signature", "A short ID for a type of error. The same error with different numbers or names gets the same signature."],
  ["Request ID (trace)", "An ID that follows a single user request through every service it passes, so its path can be traced."],
  ["Confidence", "How sure the analyzer is about the most likely root cause: high, medium or low."],
  ["Evidence", "The log lines, code, releases and history used to explain an incident. Every statement in a fix points to it (E1, E2, …)."],
];

export default function Guide() {
  return (
    <div className="space-y-8">
      <PageHeader title="How it works"
        description="Smart Log Analyzer reads the logs of all your services, notices when something goes wrong, works out where the problem started and suggests how to fix it." />

      <div className="card overflow-hidden">
        <div className="grid gap-px bg-slate-100 md:grid-cols-3">
          {[
            ["The problem", "A modern application is made of many services. When one fails, the others start failing too, and engineers see thousands of errors from everywhere. Finding the one that started it takes a long time."],
            ["What we do", "The analyzer groups the errors into one incident, follows the requests between services, and ranks every suspect using five clear clues. It then explains the cause and the fix in plain language."],
            ["Why you can trust it", "Every conclusion shows its evidence: the clues and scores, the log lines, the code line and the release. The AI only writes the explanation, and its answer is checked against the evidence."],
          ].map(([t, x]) => (
            <div key={t} className="bg-white p-6">
              <div className="text-sm font-semibold text-brand-700">{t}</div>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{x}</p>
            </div>
          ))}
        </div>
      </div>

      <section>
        <h2 className="mb-1 text-lg font-semibold text-slate-900">From log line to fix in nine steps</h2>
        <p className="mb-4 text-sm text-slate-500">This happens automatically, within seconds of the logs arriving.</p>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={s.title} className="card flex gap-4 p-5">
              <div className="relative">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-600"><s.icon size={20} /></div>
                <span className="absolute -top-1.5 -right-1.5 grid h-5 w-5 place-items-center rounded-full bg-brand-600 text-[11px] font-bold text-white">{i + 1}</span>
              </div>
              <div>
                <div className="font-semibold text-slate-900">{s.title}</div>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <div>
            <div className="card-t"><Crosshair size={16} /> The five clues used to find the root cause</div>
            <div className="card-d">Each clue gives a value from 0 to 1. The score is a weighted sum: Score = w₁·T + w₂·D + w₃·A + w₄·C + w₅·H</div>
          </div>
        </div>
        <div className="divide-y divide-slate-100">
          {SIGNALS.map((s) => (
            <div key={s.key} className="flex items-start gap-4 px-5 py-4">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-sm font-bold text-white" style={{ background: s.color }}>{s.key}</span>
              <div>
                <div className="font-semibold text-slate-900">{s.name}</div>
                <p className="mt-0.5 text-sm text-slate-600">{s.help}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <div className="card-h"><div className="card-t"><Bot size={16} /> Where the AI fits in</div></div>
          <div className="space-y-3 p-5 text-sm leading-relaxed text-slate-600">
            <p><b className="text-slate-800">The AI does not find the root cause.</b> Detection, grouping, tracing and ranking are done by clear, testable rules, so every result can be explained.</p>
            <p>The AI (Google Gemini) receives the evidence for the top suspect and writes a readable explanation and fix steps. It must refer to the evidence (E1, E2, …) for every statement.</p>
            <p className="flex gap-2"><ShieldCheck size={18} className="shrink-0 text-emerald-600" /> Before it is shown, the answer is checked automatically: the evidence it refers to must exist, fix steps must be present and dangerous commands are rejected. If anything fails, the analyzer falls back to its own rules.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-h"><div className="card-t"><Siren size={16} /> Try it yourself</div></div>
          <ol className="space-y-3 p-5 text-sm text-slate-600">
            {[
              ["Open Log sources and click “Start live traffic”.", "/sources"],
              ["Start a failure drill, e.g. “Payment database overloaded after a new release”.", "/sources"],
              ["Within seconds a new incident appears. Open it from Incidents.", "/incidents"],
              ["Read the Summary: what happened, where it started, why, and how to fix it.", null],
              ["Click “Yes” to confirm the root cause; the analyzer learns from it.", null],
            ].map(([t, to], i) => (
              <li key={t} className="flex gap-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-slate-900 text-xs font-semibold text-white">{i + 1}</span>
                <span className="pt-0.5">{t} {to && <Link to={to} className="inline-flex items-center gap-0.5 font-semibold text-brand-600 hover:underline">Open <ArrowRight size={13} /></Link>}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="card">
        <div className="card-h"><div className="card-t">Glossary</div></div>
        <dl className="grid gap-px bg-slate-100 sm:grid-cols-2">
          {TERMS.map(([t, d]) => (
            <div key={t} className="bg-white px-5 py-3.5">
              <dt className="text-sm font-semibold text-slate-800">{t}</dt>
              <dd className="mt-0.5 text-sm text-slate-600">{d}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
