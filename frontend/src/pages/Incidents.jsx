import { CheckCircle2, Siren } from "lucide-react";
import { useState } from "react";
import IncidentRow from "../components/IncidentRow.jsx";
import { Empty, PageHeader } from "../components/ui.jsx";
import { api } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const FILTERS = [
  { label: "All incidents", q: "" },
  { label: "Active", q: "status=open" },
  { label: "Resolved", q: "status=resolved" },
  { label: "Security", q: "category=security" },
];

export default function Incidents() {
  const [f, setF] = useState(FILTERS[0]);
  const { data } = usePoll(() => api(`/api/v1/incidents?limit=100&${f.q}`), 3000, [f.q]);

  return (
    <div className="space-y-6">
      <PageHeader title="Incidents"
        description="An incident is one problem. When several errors are connected (same error, same request or same time), they are grouped together, and the analyzer works out which service the problem started in." />
      <div className="card overflow-hidden">
        <div className="flex gap-1 overflow-x-auto border-b border-slate-100 px-3 pt-2">
          {FILTERS.map((x) => (
            <button key={x.label} onClick={() => setF(x)}
              className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition ${x.label === f.label ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
              {x.label}
            </button>
          ))}
        </div>
        <div className="divide-y divide-slate-100">
          {data?.items?.length === 0 && (
            f.q === "status=open"
              ? <Empty icon={CheckCircle2} title="No active incidents">Everything is running normally.</Empty>
              : <Empty icon={Siren} title="No incidents yet">Incidents appear here automatically when the analyzer finds a problem in the incoming logs.</Empty>
          )}
          {(data?.items || []).map((i) => <IncidentRow key={i.id} incident={i} />)}
        </div>
      </div>
    </div>
  );
}
