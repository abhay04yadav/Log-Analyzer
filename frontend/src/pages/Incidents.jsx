import { useState } from "react";
import IncidentRow from "../components/IncidentRow.jsx";
import { Empty } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const FILTERS = [
  { label: "All", q: "" },
  { label: "Open", q: "status=open" },
  { label: "Resolved", q: "status=resolved" },
  { label: "Security", q: "category=security" },
];

export default function Incidents() {
  const [f, setF] = useState(FILTERS[0]);
  const { data } = usePoll(() => api(`/api/v1/incidents?limit=100&${f.q}`), 3000, [f.q]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Incidents</h1>
        <p className="text-sm text-slate-500">Related errors grouped by fingerprint, trace and time, with the top-ranked root cause.</p>
      </div>
      <div className="flex gap-1.5">
        {FILTERS.map((x) => (
          <button key={x.label} onClick={() => setF(x)} className={x.label === f.label ? "btn-primary !py-1" : "btn-ghost !py-1"}>{x.label}</button>
        ))}
      </div>
      <div className="card divide-y divide-slate-100">
        {data?.items?.length === 0 && <Empty>No incidents.</Empty>}
        {(data?.items || []).map((i) => <IncidentRow key={i.id} incident={i} />)}
      </div>
    </div>
  );
}
