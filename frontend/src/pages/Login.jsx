import { Activity, Lock } from "lucide-react";
import { useState } from "react";
import { api, setToken } from "../lib/api.js";

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
    <div className="grid min-h-full place-items-center bg-gradient-to-br from-slate-900 via-slate-800 to-brand-700 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-white">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600"><Activity size={22} /></div>
          <div>
            <div className="text-lg font-semibold leading-tight">Smart Log Analyzer</div>
            <div className="text-xs text-slate-300">Evidence-first incident diagnosis</div>
          </div>
        </div>
        <form onSubmit={submit} className="card space-y-4 p-6">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Lock size={16} /> Sign in</div>
          <label className="block text-xs font-medium text-slate-500">
            Username
            <input className="input mt-1 w-full" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label className="block text-xs font-medium text-slate-500">
            Password
            <input className="input mt-1 w-full" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus />
          </label>
          {error && <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>}
          <button className="btn-primary w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
      </div>
    </div>
  );
}
