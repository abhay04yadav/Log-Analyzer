import { FileUp, Loader2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDateTime } from "../lib/api.js";

const SAMPLES = [
  { file: "shopflow-inventory-npe.log", label: "Inventory crash (Java)" },
  { file: "shopflow-cache-outage.log", label: "Cache server outage" },
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
      <div className="card-h">
        <div>
          <div className="card-t"><FileUp size={16} /> Upload a log file</div>
          <div className="card-d">Analyse a log file copied from a server</div>
        </div>
      </div>
      <div className="space-y-4 p-5 text-sm">
                <div
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}
          className="cursor-pointer rounded-xl border-2 border-dashed border-slate-200 px-4 py-7 text-center transition hover:border-brand-500 hover:bg-brand-50/40">
          <Upload size={22} className="mx-auto text-slate-400" />
          <div className="mt-1 text-sm text-slate-600">{file ? <><b>{file.name}</b> · {lines} lines</> : <><b className="text-brand-600">Choose a file</b> or drag it here</>}</div>
          <div className="mt-1 text-xs text-slate-400">.log, .txt or .jsonl · any format · up to 5 MB</div>
          <input ref={input} type="file" accept=".log,.txt,.jsonl,.json,text/plain" className="hidden" onChange={(e) => pick(e.target.files[0])} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          Or try a sample file:
          {SAMPLES.map((s) => <button key={s.file} type="button" className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700 hover:bg-slate-200" onClick={() => loadSample(s)}>{s.label}</button>)}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input className="input flex-1" placeholder="Service name, if the file does not include one (optional)" value={service} onChange={(e) => setService(e.target.value)} />
          <label className="flex items-center gap-1.5 text-xs text-slate-600" title="Moves the times in the file so it ends now. The file then appears in the live charts as if it just happened.">
            <input type="checkbox" checked={replay} onChange={(e) => setReplay(e.target.checked)} /> Treat as live
          </label>
          <button className="btn-primary" disabled={!file || busy} onClick={send}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {busy ? "Uploading…" : "Analyse file"}
          </button>
        </div>
        {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}
        {result && (
          <div className="rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
            <b>{result.accepted} log entries received</b> ({lines} lines, from {fmtDateTime(result.first_ts)} to {fmtDateTime(result.last_ts)}).
            {" "}Any problems found will appear under <Link to="/incidents" className="font-semibold underline">Incidents</Link> within a few seconds.
          </div>
        )}
      </div>
    </div>
  );
}
