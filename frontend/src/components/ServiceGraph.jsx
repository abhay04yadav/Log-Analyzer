// Service dependency graph rebuilt from spans, layered top -> bottom by call depth.
// Red = service with errors, outline = top-ranked root cause, "origin" = failing service with no failing dependency.
export default function ServiceGraph({ graph, highlight }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  if (!nodes.length) return <div className="py-8 text-center text-sm text-slate-400">No request tracing data in these logs.</div>;

  const W = 200, H = 50, GX = 24, GY = 46, PAD = 120;
  const rows = {};
  nodes.forEach((n) => { (rows[n.depth] ||= []).push(n); });
  const depths = Object.keys(rows).map(Number).sort((a, b) => a - b);
  const maxCols = Math.max(...depths.map((d) => rows[d].length));
  const width = 2 * PAD + maxCols * W + (maxCols - 1) * GX;
  const pos = {};
  depths.forEach((d, ri) => {
    const row = rows[d];
    const rowW = row.length * W + (row.length - 1) * GX;
    row.forEach((n, ci) => { pos[n.id] = { x: (width - rowW) / 2 + ci * (W + GX), y: 10 + ri * (H + GY) }; });
  });
  const height = 20 + depths.length * H + (depths.length - 1) * GY;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mx-auto block w-full" style={{ maxWidth: width * 1.15, maxHeight: 420 }} role="img" aria-label="Service dependency graph">
      <defs>
        {["#94a3b8", "#e11d48"].map((c, i) => (
          <marker key={c} id={`arr${i}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={c} />
          </marker>
        ))}
      </defs>
      {edges.map((e) => {
        const a = pos[e.source], b = pos[e.target];
        if (!a || !b) return null;
        const x1 = a.x + W / 2, y1 = a.y + H, x2 = b.x + W / 2, y2 = b.y - 2;
        const my = (y1 + y2) / 2;
        const bad = e.errors > 0;
        return (
          <g key={`${e.source}-${e.target}`}>
            <path d={`M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`} fill="none" stroke={bad ? "#e11d48" : "#cbd5e1"}
              strokeWidth={bad ? 2 : 1.5} strokeDasharray={bad ? "5 3" : undefined} markerEnd={`url(#arr${bad ? 1 : 0})`} />
            <text x={(x1 + x2) / 2 + 8} y={my + 4} fontSize="11" fill={bad ? "#e11d48" : "#94a3b8"}>
              {e.calls} calls{bad ? ` · ${e.errors} failed` : ""}
            </text>
          </g>
        );
      })}
      {nodes.map((n) => {
        const p = pos[n.id];
        const bad = n.errors > 0;
        return (
          <g key={n.id}>
            {n.id === highlight && <rect x={p.x - 4} y={p.y - 4} width={W + 8} height={H + 8} rx="12" fill="none" stroke="#e11d48" strokeWidth="2.5" />}
            <rect x={p.x} y={p.y} width={W} height={H} rx="9" fill={bad ? "#fff1f2" : "#f8fafc"} stroke={bad ? "#fda4af" : "#e2e8f0"} />
            <circle cx={p.x + 14} cy={p.y + 18} r="5" fill={bad ? "#e11d48" : "#10b981"} />
            <text x={p.x + 26} y={p.y + 22} fontSize="13" fontWeight="600" fill="#1e293b">{n.id.length > 18 ? n.id.slice(0, 17) + "…" : n.id}</text>
            <text x={p.x + 12} y={p.y + 40} fontSize="11" fill={bad ? "#be123c" : "#64748b"}>
              {n.errors ? `${n.errors} errors` : "healthy"} · {n.events} logs{n.origin && bad ? " · starts here" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
