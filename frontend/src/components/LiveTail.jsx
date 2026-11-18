import { Pause, Play, ScrollText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../lib/api.js";
import { Empty, LevelBadge } from "./ui.jsx";

// Live tail: polls for events newer than the last one seen.
export default function LiveTail({ max = 60 }) {
  const [items, setItems] = useState([]);
  const [paused, setPaused] = useState(false);
  const last = useRef(0);

  useEffect(() => {
    if (paused) return undefined;
    let alive = true;
    const tick = async () => {
      try {
        const q = last.current ? `after_id=${last.current}&limit=200` : "limit=40";
        const r = await api(`/api/v1/events?${q}`);
        if (!alive || !r.items.length) return;
        last.current = Math.max(last.current, ...r.items.map((e) => e.id));
        setItems((prev) => [...r.items, ...prev].slice(0, max));
      } catch { /* shown elsewhere */ }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => { alive = false; clearInterval(id); };
  }, [paused, max]);

  return (
    <div className="card flex flex-col">
      <div className="card-h">
        <div className="card-t"><ScrollText size={16} /> Live log stream
          {!paused && <span className="ml-1 flex items-center gap-1 text-[11px] font-normal text-emerald-600"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" /> live</span>}
        </div>
        <button className="btn-ghost !py-1 !text-xs" onClick={() => setPaused((p) => !p)}>{paused ? <><Play size={13} /> Resume</> : <><Pause size={13} /> Pause</>}</button>
      </div>
      <div className="max-h-[360px] min-h-[200px] overflow-auto">
        {items.length === 0 && <Empty>Waiting for logs…</Empty>}
        {items.map((e) => (
          <div key={e.id} className={`flex items-start gap-2 border-b border-slate-50 px-3 py-1.5 ${e.is_error ? "bg-rose-50/40" : ""}`}>
            <span className="mono shrink-0 pt-0.5 text-slate-400">{fmtTime(e.ts)}</span>
            <LevelBadge level={e.level} />
            <span className="w-32 shrink-0 truncate pt-0.5 text-xs font-medium text-slate-600">{e.service}</span>
            <span className="mono min-w-0 flex-1 truncate pt-0.5 text-slate-700" title={e.message}>{e.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
