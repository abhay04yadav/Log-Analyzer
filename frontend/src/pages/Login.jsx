import { Crosshair, Lock, Radar, Wrench } from "lucide-react";
import { useState } from "react";
import { Logo } from "../components/ui.jsx";
import { api, setToken } from "../lib/api.js";

const POINTS = [
  { icon: Radar, title: "Detects problems automatically", text: "Watches every log line from every service, around the clock." },
  { icon: Crosshair, title: "Finds where it started", text: "Ranks every suspect with five clear, explainable clues." },
  { icon: Wrench, title: "Explains the fix", text: "Step-by-step fixes, each backed by evidence from your logs." },
];

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api("/api/v1/auth/login", { method: "POST", body: { username, password } });
      setToken(r.access_token);
      onLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col">
        <div className="absolute -top-40 -right-40 h-[500px] w-[500px] rounded-full bg-brand-600/30 blur-3xl" />
        <div className="absolute -bottom-40 -left-20 h-[400px] w-[400px] rounded-full bg-sky-500/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <Logo size={40} />
          <div className="text-lg font-semibold">Smart Log Analyzer</div>
        </div>
        <div className="relative mt-auto max-w-md">
          <h1 className="text-4xl leading-tight font-semibold tracking-tight">From thousands of errors to one root cause, in seconds.</h1>
          <p className="mt-4 text-slate-400">AI-assisted incident analysis for applications built from many services.</p>
          <div className="mt-10 space-y-5">
            {POINTS.map((p) => (
              <div key={p.title} className="flex gap-4">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/10 text-brand-200"><p.icon size={19} /></div>
                <div>
                  <div className="font-medium">{p.title}</div>
                  <div className="text-sm text-slate-400">{p.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative mt-auto pt-10 text-xs text-slate-500">© 2026 Smart Log Analyzer</div>
      </div>

      <div className="flex items-center justify-center bg-white px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <Logo size={36} />
            <div className="text-lg font-semibold text-slate-900">Smart Log Analyzer</div>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Welcome back. Enter your details to open the dashboard.</p>
          <form onSubmit={submit} className="mt-8 space-y-5">
            <label className="block text-sm font-medium text-slate-700">
              Username
              <input className="input mt-1.5 w-full !py-2.5" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Password
              <input className="input mt-1.5 w-full !py-2.5" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus />
            </label>
            {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
            <button className="btn-primary w-full !py-2.5" disabled={busy}><Lock size={15} /> {busy ? "Signing in…" : "Sign in"}</button>
          </form>
        </div>
      </div>
    </div>
  );
}
