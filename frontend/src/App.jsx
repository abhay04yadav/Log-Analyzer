import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { getToken } from "./lib/api.js";
import IncidentDetail from "./pages/IncidentDetail.jsx";
import Incidents from "./pages/Incidents.jsx";
import Login from "./pages/Login.jsx";
import Logs from "./pages/Logs.jsx";
import Overview from "./pages/Overview.jsx";
import Settings from "./pages/Settings.jsx";
import Simulator from "./pages/Simulator.jsx";

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());

  useEffect(() => {
    const out = () => setAuthed(false);
    window.addEventListener("sla-logout", out);
    return () => window.removeEventListener("sla-logout", out);
  }, []);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;
  return (
    <Routes>
      <Route element={<Layout onLogout={() => setAuthed(false)} />}>
        <Route index element={<Overview />} />
        <Route path="incidents" element={<Incidents />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="logs" element={<Logs />} />
        <Route path="simulator" element={<Simulator />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
