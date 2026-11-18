import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, fmtDateTime } from "../lib/api.js";
import { LevelBadge, Pill } from "./ui.jsx";

// Full event: normalised fields, parsed stack frames, original (masked) raw input.
export default function EventModal({ id, onClose }) {
  const [e, setE] = useState(null);
  useEffect(() => {
    if (!id) return;
    setE(null);
    api(`/api/v1/events/${id}`).then(setE).catch(() => setE({ error: true }));
  }, [id]);
  useEffect(() => {
    const esc = (ev) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  if (!id) return null;

  const fields = e && !e.error ? [
    ["Timestamp", fmtDateTime(e.ts)], ["Service", e.service], ["Logger", e.logger], ["Format", e.format],
    ["Trace", e.trace_id], ["Span", e.span_id], ["Parent span", e.parent_span_id], ["Error type", e.error_type],
    ["Fingerprint", e.fingerprint], ["Incident", e.incident_id && `#${e.incident_id}`],
  ].filter(([, v]) => v) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-slate-900/40 p-4 pt-16" onClick={onClose}>
      <div className="card w-full max-w-3xl" onClick={(ev) => ev.stopPropagation()}>
        <div className="card-h">
          <div className="card-t">Event #{id} {e?.level && <LevelBadge level={e.level} />}</div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close"><X size={18} /></button>
        </div>
        {!e && <div className="p-6 text-sm text-slate-400">Loading…</div>}
        {e && !e.error && (
          <div className="space-y-4 p-4">
            <div className="mono rounded-lg bg-slate-50 p-3 text-slate-800">{e.message}</div>
            <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
              {fields.map(([k, v]) => (
                <div key={k} className="flex gap-2"><span className="w-24 shrink-0 text-slate-400">{k}</span><span className="mono truncate text-slate-700">{v}</span></div>
              ))}
            </div>
            {e.stack?.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold text-slate-500">Parsed stack frames (innermost first)</div>
                <div className="space-y-1">
                  {e.stack.map((f, i) => (
                    <div key={i} className="mono flex flex-wrap gap-2 text-slate-600">
                      <Pill>{f.lang}</Pill><span className="text-slate-800">{f.function}</span><span className="text-slate-400">{f.module ? `${f.module} · ` : ""}{f.file}:{f.line}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {e.attrs && Object.keys(e.attrs).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold text-slate-500">Attributes</div>
                <div className="flex flex-wrap gap-1.5">{Object.entries(e.attrs).map(([k, v]) => <Pill key={k}>{k}={String(v)}</Pill>)}</div>
              </div>
            )}
            {e.stack_text && (
              <div>
                <div className="mb-1 text-xs font-semibold text-slate-500">Stack trace</div>
                <pre className="mono max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 whitespace-pre text-slate-100">{e.stack_text}</pre>
              </div>
            )}
            <div>
              <div className="mb-1 text-xs font-semibold text-slate-500">Original input ({e.format}, secrets masked)</div>
              <pre className="mono max-h-48 overflow-auto rounded-lg bg-slate-100 p-3 whitespace-pre-wrap break-all text-slate-700">{e.raw}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
