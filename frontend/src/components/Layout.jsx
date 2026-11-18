import { Activity, AlertTriangle, FlaskConical, LayoutDashboard, LogOut, ScrollText, SlidersHorizontal } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { api, setToken } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle },
  { to: "/logs", label: "Log explorer", icon: ScrollText },
  { to: "/simulator", label: "Simulator", icon: FlaskConical },
  { to: "/settings", label: "Model & settings", icon: SlidersHorizontal },
];

function Dot({ ok }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-amber-400"}`} />;
}

export default function Layout({ onLogout }) {
  const { data: st } = usePoll(() => api("/api/v1/system/status"), 5000);
  const { data: ov } = usePoll(() => api("/api/v1/stats/overview"), 5000);

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-slate-900 text-slate-300 md:flex">
        <div className="flex items-center gap-2 px-5 py-5 text-white">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600"><Activity size={20} /></div>
          <div>
            <div className="text-sm font-semibold leading-tight">Smart Log Analyzer</div>
            <div className="text-[11px] text-slate-400">ShopFlow (demo)</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${isActive ? "bg-slate-800 text-white" : "hover:bg-slate-800/60 hover:text-white"}`}>
              <Icon size={17} />
              <span className="flex-1">{label}</span>
              {to === "/incidents" && ov?.open_incidents > 0 && (
                <span className="rounded-full bg-rose-500 px-1.5 text-[11px] font-semibold text-white">{ov.open_incidents}</span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-1.5 border-t border-slate-800 px-5 py-4 text-[11px] text-slate-400">
          <div className="flex items-center gap-2"><Dot ok={!!st} /> API {st ? "online" : "connecting…"}</div>
          {st && <>
            <div className="flex items-center gap-2"><Dot ok={st.database === "postgresql"} /> DB: {st.database}</div>
            <div className="flex items-center gap-2"><Dot ok={st.event_bus === "redis-streams"} /> Bus: {st.event_bus}</div>
            <div className="flex items-center gap-2"><Dot ok={st.ai.enabled} /> AI: {st.ai.enabled ? st.ai.model : "rules + playbook"}</div>
          </>}
          <button onClick={() => { setToken(null); onLogout(); }} className="mt-2 flex items-center gap-1.5 text-slate-400 hover:text-white">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <div className="sticky top-0 z-10 flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 py-2 md:hidden">
          {NAV.map(({ to, label, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `whitespace-nowrap rounded-md px-2.5 py-1 text-xs ${isActive ? "bg-slate-900 text-white" : "text-slate-600"}`}>{label}</NavLink>
          ))}
        </div>
        <div className="mx-auto max-w-[1400px] p-4 md:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
