import { Ico } from "../components/Icon";
import CommandPalette from "./CommandPalette";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getConnections, SavedConnection } from "../api";
import { useAi } from "./AiContext";
import { useSelectedConnection } from "./ConnectionContext";

/** FSD §3 top bar: connection switcher, AI drawer, Settings. */
function TopBar() {
  // TopBar renders in Layout, above the parameterized child route. useParams
  // there only sees the parent route's params, so match the current URL here.
  const connectionId = useSelectedConnection();
  const navigate = useNavigate();
  const ai = useAi();
  const [connections, setConnections] = useState<SavedConnection[]>([]);

  useEffect(() => {
    getConnections().then(setConnections).catch(() => setConnections([]));
  }, [connectionId]);

  return (
    <header
      style={{
        height: 64,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 var(--space-8)",
        background: "var(--canvas)",
        borderBottom: "1px solid var(--hairline)",
        flexShrink: 0,
      }}
    >
      <select
        className="text-input"
        value={connectionId ?? ""}
        onChange={(e) => {
          if (e.target.value === "__add__") navigate("/connections/new");
          else navigate(`/connections/${e.target.value}/overview`);
        }}
        style={{ minWidth: 260, borderRadius: "var(--radius-pill)", paddingInline: "var(--space-6)" }}
      >
        <option value="" disabled>
          {connections.length ? "Switch connection…" : "No connections yet"}
        </option>
        {connections.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.type})
          </option>
        ))}
        <option value="__add__">+ Add connection</option>
      </select>

      <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
        <CommandPalette />
        <button
          type="button"
          className="button-secondary-outline"
          aria-label="Open AI assistant"
          onClick={() => ai.show({ job: "explain-changes" })}
        ><Ico t="AI" /></button>
        <Link to="/settings" className="button-secondary-outline" aria-label="Settings"><Ico t="Settings" /></Link>
      </div>
    </header>
  );
}

export default TopBar;
