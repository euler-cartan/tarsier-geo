import { Link, useLocation } from "react-router-dom";
import { useSelectedConnection } from "./ConnectionContext";
import BrandMark from "../components/BrandMark";
import { Icon, IconName } from "../components/Icon";

const NAV_ICONS: Record<string, IconName> = {
  overview: "home", statistics: "chart", snapshots: "camera", changes: "history",
  alerts: "bell", automations: "zap", flowchart: "graph",
};

/** FSD §3: sidebar navigation for the shipped and coming-soon screens. */
const NAV_ITEMS = [
  { label: "Overview", key: "overview", enabled: true },
  { label: "Statistics", key: "statistics", enabled: true },
  { label: "Snapshots", key: "snapshots", enabled: true },
  { label: "Changes", key: "changes", enabled: true },
  { label: "Alerts", key: "alerts", enabled: true },
  { label: "Automations", key: "automations", enabled: true },
  { label: "Flowchart", key: "flowchart", enabled: true },
];

function Sidebar() {
  const connectionId = useSelectedConnection();
  const location = useLocation();

  return (
    <nav
      aria-label="Main"
      style={{
        width: 248,
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        padding: "var(--space-6) var(--space-5)",
        flexShrink: 0,
        borderRight: "1px solid var(--hairline)",
        background: "var(--canvas)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "var(--space-3)", marginBottom: "var(--space-6)" }}>
        <BrandMark />
        <h1 className="t-display-sm" style={{ margin: 0, fontSize: 30, lineHeight: 1, letterSpacing: "-0.3px" }}>
          Tarsier
        </h1>
      </div>
      {NAV_ITEMS.map((item) => {
        const isActive =
          (item.key === "overview" && location.pathname.includes("/overview")) ||
          (item.key === "statistics" && location.pathname.includes("/statistics")) ||
          (item.key === "changes" && location.pathname.includes("/changes")) ||
          (item.key === "alerts" && location.pathname.includes("/alerts")) ||
          (item.key === "automations" && location.pathname.includes("/automations"));
        const active = (item.key === "snapshots" && location.pathname.includes("/snapshots")) || isActive || (item.key === "flowchart" && location.pathname.includes("/flowchart"));
        const content = (
          <div
            className={`sidebar-link${active ? " active" : ""}${item.enabled ? "" : " disabled"}`}
            style={{ cursor: item.enabled && connectionId ? "pointer" : "default" }}
          >
            <Icon name={NAV_ICONS[item.key]} />
            {item.label}
            {!item.enabled && <span className="badge-pill" style={{ marginLeft: "auto" }}>soon</span>}
          </div>
        );
        if (item.enabled && connectionId) {
          const href =
            item.key === "snapshots" ? `/connections/${connectionId}/snapshots` : item.key === "statistics"
              ? `/connections/${connectionId}/statistics`
              : item.key === "changes"
              ? `/connections/${connectionId}/changes`
              : item.key === "alerts"
                ? `/connections/${connectionId}/alerts`
                : item.key === "automations"
                  ? `/connections/${connectionId}/automations`
                : item.key === "flowchart"
                  ? `/connections/${connectionId}/flowchart`
                  : `/connections/${connectionId}/overview`;
          return (
            <Link key={item.key} to={href} style={{ textDecoration: "none" }}>
              {content}
            </Link>
          );
        }
        return <div key={item.key}>{content}</div>;
      })}
    </nav>
  );
}

export default Sidebar;
