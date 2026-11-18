import { FileUp, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, fmtDateTime } from "../lib/api.js";

const SAMPLES = [
  { file: "shopflow-inventory-npe.log", label: "Java NullPointerException (mixed formats)" },
  { file: "shopflow-cache-outage.log", label: "Redis cache outage" },
];
const MAX = 5 * 1024 * 1024;

// Upload a log file (any mix of JSON lines, logfmt and plain text with multi-line stack traces).
export default function UploadCard() {
  const input = useRef(null);
  const [file, setFile] = useState(null);       // { name, content }
  const [service, setService] = useState("");
  const [replay, setReplay] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const pick = async (f) => {
    setResult(null); setError(null);
    if (!f) return;
    if (f.size > MAX) { setError("File is larger than 5 MB."); return; }
    setFile({ name: f.name, content: await f.text() });
  };
  const loadSample = async (s) => {
    setResult(null); setError(null);
    const r = await fetch(`/samples/${s.file}`);
    setFile({ name: s.file, content: await r.text() });
  };
  const send = async () => {
    setBusy(true); setError(null);
    try {
      setResult(await api("/api/v1/upload", { method: "POST", body: { content: file.content, filename: file.name, service: service || null, replay } }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const lines = file ? file.content.split("\n").filter((l) => l.trim()).length : 0;
  return (
    <div className="card">
      <div className="card-h"><div className="card-t"><FileUp size={16} /> Upload a log file</div></div>
      <div className="space-y-3 p-4 text-sm">
        <p className="text-xs text-slate-500">JSON lines, logfmt or plain text. Multi-line stack traces are kept with their log line. Up to 5 MB.</p>
        <div
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}
          className="cursor-pointer rounded-lg border-2 border-dashed border-slate-200 px-4 py-5 text-center hover:border-brand-500 hover:bg-brand-50/40">
          <Upload size={20} className="mx-auto text-slate-400" />
          <div className="mt-1 text-sm text-slate-600">{file ? <><b>{file.name}</b> · {lines} lines</> : "Drop a .log / .txt / .jsonl file or click to choose"}</div>
          <input ref={input} type="file" accept=".log,.txt,.jsonl,.json,text/plain" className="hidden" onChange={(e) => pick(e.target.files[0])} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          Samples:
          {SAMPLES.map((s) => <button key={s.file} type="button" className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700 hover:bg-slate-200" onClick={() => loadSample(s)}>{s.label}</button>)}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input className="input flex-1" placeholder="Service name for lines without one (optional)" value={service} onChange={(e) => setService(e.target.value)} />
          <label className="flex items-center gap-1.5 text-xs text-slate-600" title="Shift timestamps so the file ends now, so it shows up as live traffic">
            <input type="checkbox" checked={replay} onChange={(e) => setReplay(e.target.checked)} /> Replay as live
          </label>
          <button className="btn-primary" disabled={!file || busy} onClick={send}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} Ingest
          </button>
        </div>
        {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}
        {result && (
          <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
            {result.accepted} log entries queued ({lines} lines) · original time range {fmtDateTime(result.first_ts)} – {fmtDateTime(result.last_ts)}
            {result.replay_offset_seconds !== 0 && " · replayed as live"}. Incidents appear within a few seconds.
          </div>
        )}
      </div>
    </div>
  );
}
