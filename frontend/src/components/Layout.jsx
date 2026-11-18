import {
  BookOpenText, ChevronRight, LayoutDashboard, LogOut, PlugZap, Search, Settings as SettingsIcon, Siren, UserCircle2,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api, setToken } from "../lib/api.js";
import { usePoll } from "../lib/usePoll.js";
import { Logo } from "./ui.jsx";

const GROUPS = [
  {
    title: "Monitor",
    items: [
      { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
      { to: "/incidents", label: "Incidents", icon: Siren, badge: true },
      { to: "/logs", label: "Log search", icon: Search },
    ],
  },
  {
    title: "Configure",
    items: [
      { to: "/sources", label: "Log sources", icon: PlugZap },
      { to: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
  {
    title: "Help",
    items: [{ to: "/guide", label: "How it works", icon: BookOpenText }],
  },
];
const ALL = GROUPS.flatMap((g) => g.items);

function crumb(pathname) {
  if (pathname.startsWith("/incidents/")) return ["Incidents", `Incident #${pathname.split("/")[2]}`];
  const item = ALL.find((i) => (i.end ? pathname === i.to : pathname.startsWith(i.to)));
  return [item?.label || "Overview"];
}

export default function Layout({ onLogout }) {
  const { data: st, error: stErr } = usePoll(() => api("/api/v1/system/status"), 5000);
  const { data: ov } = usePoll(() => api("/api/v1/stats/overview"), 5000);
  const { data: me } = usePoll(() => api("/api/v1/auth/me"), 0);
  const { data: project } = usePoll(() => api("/api/v1/project"), 0);
  const { pathname } = useLocation();
  const parts = crumb(pathname);
  const online = !!st && !stErr;
  const receiving = (ov?.events_15m || 0) > 0;
  const signOut = () => { setToken(null); onLogout(); };

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-slate-950 text-slate-300 lg:flex">
        <Link to="/" className="flex items-center gap-3 px-5 pt-6 pb-5">
          <Logo />
          <div>
            <div className="text-[15px] font-semibold leading-tight text-white">Smart Log Analyzer</div>
            <div className="text-[11px] text-slate-400">AI root-cause analysis</div>
          </div>
        </Link>

        <div className="mx-3 mb-4 rounded-xl bg-slate-900 px-3 py-2.5 ring-1 ring-white/5">
          <div className="text-[10px] font-semibold tracking-wider text-slate-500 uppercase">Project</div>
          <div className="mt-0.5 truncate text-sm font-medium text-slate-100">{project?.name || "…"}</div>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-3">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <div className="px-3 pb-1.5 text-[10px] font-semibold tracking-wider text-slate-500 uppercase">{g.title}</div>
              <div className="space-y-0.5">
                {g.items.map(({ to, label, icon: Icon, end, badge }) => (
                  <NavLink key={to} to={to} end={end}
                    className={({ isActive }) => `group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${isActive ? "bg-brand-600 text-white shadow-sm" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}>
                    <Icon size={18} />
                    <span className="flex-1">{label}</span>
                    {badge && ov?.open_incidents > 0 && (
                      <span className="rounded-full bg-rose-500 px-1.5 py-px text-[11px] font-semibold text-white">{ov.open_incidents}</span>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="space-y-2 border-t border-white/5 px-5 py-4 text-xs">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${online ? "bg-emerald-400" : "bg-amber-400"}`} />
            <span className="text-slate-300">{online ? "All systems operational" : "Connecting…"}</span>
          </div>
          {st && (
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${st.ai.enabled ? "bg-emerald-400" : "bg-slate-500"}`} />
              <span className="text-slate-400">AI assistant {st.ai.enabled ? "on" : "off (rules only)"}</span>
            </div>
          )}
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur">
          <div className="flex h-14 items-center gap-3 px-4 md:px-8">
            <Link to="/" className="lg:hidden"><Logo size={28} /></Link>
            <div className="flex min-w-0 items-center gap-1.5 text-sm">
              <span className="hidden text-slate-400 sm:inline">{project?.name || "Project"}</span>
              {parts.map((p, i) => (
                <span key={p} className="flex min-w-0 items-center gap-1.5">
                  <ChevronRight size={14} className="hidden shrink-0 text-slate-300 sm:inline" />
                  {i === 0 && parts.length > 1
                    ? <Link to="/incidents" className="text-slate-500 hover:text-slate-900">{p}</Link>
                    : <span className="truncate font-medium text-slate-900">{p}</span>}
                </span>
              ))}
            </div>
            <div className="flex-1" />
            <span className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium sm:inline-flex ${receiving ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${receiving ? "animate-pulse bg-emerald-500" : "bg-slate-400"}`} />
              {receiving ? "Receiving logs" : "No logs in the last 15 min"}
            </span>
            <div className="flex items-center gap-2 border-l border-slate-200 pl-3 text-sm text-slate-600">
              <UserCircle2 size={20} className="text-slate-400" />
              <span className="hidden capitalize md:inline">{me?.user || "…"}</span>
              <button onClick={signOut} title="Sign out" className="ml-1 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Sign out">
                <LogOut size={16} />
              </button>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto border-t border-slate-100 px-3 py-2 lg:hidden">
            {ALL.map(({ to, label, end, icon: Icon }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium ${isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
                <Icon size={14} /> {label}
              </NavLink>
            ))}
          </nav>
        </header>
        <div className="mx-auto w-full max-w-[1400px] flex-1 p-4 md:p-8">
          <Outlet />
        </div>
        <footer className="border-t border-slate-200 px-4 py-4 text-center text-xs text-slate-400 md:px-8">
          Smart Log Analyzer · Logs in, root cause and fix out
        </footer>
      </main>
    </div>
  );
}
