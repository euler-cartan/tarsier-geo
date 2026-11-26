import { useEffect } from "react";
import { applyTheme } from "./Appearance";
import { Outlet } from "react-router-dom";
import { AiProvider } from "./AiContext";
import AiPanel from "./AiPanel";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { ConnectionProvider } from "./ConnectionContext";

/** FSD §3: the app shell, used on every screen. */
function Layout() {
  useEffect(() => { fetch("/api/settings/appearance").then(r => r.json()).then(s => applyTheme(s.theme)).catch(() => {}); }, []);
  return (
    <ConnectionProvider><AiProvider>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <div className="app-shell">
        <Sidebar />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          <TopBar />
          <main id="main-content" tabIndex={-1} className="app-main">
            <div className="page">
              <Outlet />
            </div>
          </main>
        </div>
        <AiPanel />
      </div>
    </AiProvider></ConnectionProvider>
  );
}

export default Layout;
