import { Ico } from "./components/Icon";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ConnectionTypeInfo,
  createConnection,
  getConnectionTypes,
  installChangeTriggers,
} from "./api";
import { ErrorState, LoadingState } from "./components/States";

/**
 * Minimal, deliberately unstyled Add Connection flow (PRD Phase 1.1–1.3).
 * Proves the tier-notice requirement (TRS-007) and that every connection
 * type can actually connect, ahead of Phase 2, which replaces this with
 * the real FSD §4/§5 screens and design system.
 */
function AddConnection() {
  const [types, setTypes] = useState<ConnectionTypeInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ConnectionTypeInfo | null>(null);

  function loadTypes() {
    setLoadError(null);
    getConnectionTypes()
      .then(setTypes)
      .catch((err) => setLoadError(err.message));
  }

  useEffect(loadTypes, []);

  if (loadError) {
    return <ErrorState message={`Could not load connection types: ${loadError}`} onRetry={loadTypes} />;
  }

  if (!types) {
    return <LoadingState label="Loading connection types" rows={2} />;
  }

  return (
    <div>
      <p className="t-label" style={{ marginBottom: "var(--space-3)" }}>New connection</p>
      <h1 className="t-display-lg" style={{ marginBottom: "var(--space-3)" }}>Add a connection</h1>
      <p className="t-body-md" style={{ color: "var(--ink-body)", maxWidth: 560, marginBottom: "var(--space-7)" }}>
        Choose where your data lives. Tarsier reads your data; optional PostGIS change tracking installs a history log only if you choose Enable.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-4)", marginBottom: "var(--space-7)" }}>
        {types.map((type) => (
          <button
            key={type.id}
            type="button"
            className="card"
            aria-pressed={selected?.id === type.id}
            onClick={() => setSelected(type)}
            style={{
              padding: "var(--space-5) var(--space-6)",
              fontSize: 16,
              fontWeight: 500,
              color: "var(--ink)",
              borderColor: selected?.id === type.id ? "var(--ink)" : undefined,
              boxShadow: selected?.id === type.id ? "0 0 0 1px var(--ink)" : undefined,
            }}
          >
            {type.label}
          </button>
        ))}
      </div>

      {selected && <ConnectionNotice type={selected} />}
      {selected && <ConnectionForm key={selected.id} type={selected} />}
    </div>
  );
}

function ConnectionNotice({ type }: { type: ConnectionTypeInfo }) {
  if (!type.notice) {
    return (
      <p
        style={{
          color: "var(--ink)",
          padding: "var(--space-5) var(--space-6)",
          background: "color-mix(in srgb, var(--gradient-mint) 38%, var(--card))",
          border: "1px solid color-mix(in srgb, var(--gradient-mint) 70%, var(--hairline))",
          borderRadius: "var(--radius-xl)",
        }}
      >
        All features are fully supported for {type.label} connections.
      </p>
    );
  }
  return (
    <p
      role="alert"
      style={{
        color: "var(--ink)",
        background: "color-mix(in srgb, var(--gradient-peach) 38%, var(--card))",
        border: "1px solid color-mix(in srgb, var(--gradient-peach) 75%, var(--hairline))",
        borderRadius: "var(--radius-xl)",
        padding: "var(--space-5) var(--space-6)",
        marginBottom: "var(--space-5)",
      }}
    >
      {type.notice}
    </p>
  );
}

interface FieldSpec {
  key: string;
  label: string;
  defaultValue?: string;
  required?: boolean;
}

const FORM_FIELDS: Record<string, FieldSpec[]> = {
  postgis: [
    { key: "host", label: "Host", required: true },
    { key: "port", label: "Port", defaultValue: "5432", required: true },
    { key: "database", label: "Database", required: true },
    { key: "username", label: "Username", required: true },
  ],
  oracle: [
    { key: "host", label: "Host", required: true },
    { key: "port", label: "Port", defaultValue: "1521", required: true },
    { key: "service_name", label: "Service name", defaultValue: "XEPDB1", required: true },
    { key: "username", label: "Username", required: true },
  ],
  sqlserver: [
    { key: "host", label: "Host", required: true },
    { key: "port", label: "Port", defaultValue: "1433", required: true },
    { key: "database", label: "Database", required: true },
    { key: "username", label: "Username", defaultValue: "sa", required: true },
  ],
  files: [{ key: "folder", label: "Folder path", required: true }],
  arcgis: [{ key: "base_url", label: "Services URL (e.g. https://server/arcgis/rest/services)", required: true }],
  geoserver: [
    { key: "base_url", label: "Base URL (e.g. http://server/geoserver)", required: true },
    { key: "username", label: "Username", defaultValue: "admin", required: true },
  ],
};

const PASSWORD_LABEL: Record<string, string> = {
  arcgis: "Token (optional, leave blank for a public service)",
};

/** A visible caption above a field; the input itself keeps its own accessible name. */
function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-2)" }}>
      <span className="t-label" aria-hidden="true">{label}</span>
      {children}
    </div>
  );
}

function ConnectionForm({ type }: { type: ConnectionTypeInfo }) {
  const fields = FORM_FIELDS[type.id] ?? [];
  const showsPassword = type.id !== "files";

  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((f) => [f.key, f.defaultValue ?? ""]))
  );
  const [password, setPassword] = useState("");
  const [changeTracking, setChangeTracking] = useState<"enable" | "skip" | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setStatus("saving");
    setError(null);
    let createdId: string | null = null;
    try {
      const config: Record<string, unknown> = { ...values };
      if ("port" in config) config.port = Number(config.port);
      const saved = await createConnection({
        name,
        type: type.id,
        config,
        password: showsPassword ? password : undefined,
      });
      createdId = saved.id;
      setSavedId(saved.id);
      if (type.id === "postgis" && changeTracking === "enable") {
        await installChangeTriggers(saved.id);
      }
      setStatus("saved");
      navigate(`/connections/${saved.id}/overview`);
    } catch (err) {
      setStatus("error");
      const message = err instanceof Error ? err.message : "Could not create the connection.";
      setError(createdId ? `Connection saved, but the history log could not be installed: ${message}` : message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card" style={{ display: "grid", gap: "var(--space-5)", maxWidth: 560, padding: "var(--space-7)" }}>
      <h2 className="t-display-sm">Connection details</h2>
      <FormField label="Connection name">
        <input className="text-input" aria-label="Connection name" placeholder="e.g. City utilities" value={name} onChange={(e) => setName(e.target.value)} required />
      </FormField>
      {fields.map((field) => (
        <FormField key={field.key} label={field.label}>
          <input
            className="text-input"
            aria-label={field.label}
            placeholder={field.label}
            value={values[field.key]}
            onChange={(e) => setValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
            required={field.required}
          />
        </FormField>
      ))}
      {showsPassword && (
        <FormField label={PASSWORD_LABEL[type.id] ?? "Password"}>
          <input
            className="text-input"
            aria-label={PASSWORD_LABEL[type.id] ?? "Password"}
            placeholder={PASSWORD_LABEL[type.id] ?? "Password"}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormField>
      )}
      {type.id === "postgis" && (
        <div className="t-caption" style={{ color: "var(--ink-body)" }}>
          <p>Enable full change tracking? Tarsier can install a one-time history log in your database (needs write permission). You can skip this and add it later.</p>
          <div style={{ display: "flex", gap: "var(--space-3)" }}>
            <button type="button" className={changeTracking === "enable" ? "button-primary-dark" : "button-secondary-outline"} aria-pressed={changeTracking === "enable"} onClick={() => setChangeTracking("enable")}><Ico t="Enable" /></button>
            <button type="button" className={changeTracking === "skip" ? "button-primary-dark" : "button-secondary-outline"} aria-pressed={changeTracking === "skip"} onClick={() => setChangeTracking("skip")}><Ico t="Skip for now" /></button>
          </div>
        </div>
      )}
      <div>
        <button type="submit" className="button-primary-dark" disabled={status === "saving" || savedId !== null || (type.id === "postgis" && changeTracking === null)}><Ico t={status === "saving" ? "Testing connection…" : "Test & save"} /></button>
      </div>
      {status === "saved" && <p style={{ color: "var(--status-good-ink)", margin: 0 }}>Connection saved.</p>}
      {status === "error" && (
        <p role="alert" style={{ color: "var(--status-danger)", margin: 0 }}>
          {error}
          {savedId && <a href={`/connections/${savedId}/changes`}>Open Changes to retry Install/Upgrade.</a>}
        </p>
      )}
    </form>
  );
}

export default AddConnection;
