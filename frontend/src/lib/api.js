// Small fetch wrapper: adds the bearer token, parses JSON, signals logout on 401.
const KEY = "sla_token";

// Backend address. Empty in development (Vite proxies /api to localhost:8000);
// set VITE_API_URL (e.g. https://smart-log-analyzer-api.onrender.com) when the
// frontend is hosted separately, such as on Vercel.
export const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/+$/, "");

export function getToken() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(API_BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401 && !path.endsWith("/auth/login")) {
    setToken(null);
    window.dispatchEvent(new Event("sla-logout"));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText);
  return data;
}

export const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour12: false }) : "—");
export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString([], { hour12: false, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
export const ago = (iso) => {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};
