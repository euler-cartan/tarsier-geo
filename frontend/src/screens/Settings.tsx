import { Ico, Icon } from "../components/Icon";
import ChatChannels from "./ChatChannels";
import ConnectionSettings from "./ConnectionSettings";
import Appearance from "../shell/Appearance";
import { FormEvent, useEffect, useState } from "react";
import { getAbout, getAiSettings, getNotificationSettings, saveAiSettings, saveNotificationSettings, testAiSettings, testNotificationEmail } from "../api";
import { LoadingState } from "../components/States";
import type { AboutInfo } from "../api";

/** FSD §13 - settings sections currently being delivered incrementally. */
function Settings() {
  const [models, setModels] = useState<{id: string; name: string}[]>([]);
  const [modelsError, setModelsError] = useState("");
  const [modelsBusy, setModelsBusy] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [modelListOpen, setModelListOpen] = useState(false);
  const [activeModelOption, setActiveModelOption] = useState(0);
  const [refreshModels, setRefreshModels] = useState(0);
  const [allowExternalDiscovery, setAllowExternalDiscovery] = useState(false);
  const [provider, setProvider] = useState<"ollama" | "external">("ollama");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);
  const [defaultEndpoint, setDefaultEndpoint] = useState("http://127.0.0.1:11434/v1/chat/completions");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [about, setAbout] = useState<AboutInfo | null>(null);
  const [aboutError, setAboutError] = useState<string | null>(null);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpSecurity, setSmtpSecurity] = useState<"starttls" | "ssl" | "none">("starttls");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpUsernameSet, setSmtpUsernameSet] = useState(false);
  const [smtpSender, setSmtpSender] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpPasswordSet, setSmtpPasswordSet] = useState(false);
  const [clearSmtpCredentials, setClearSmtpCredentials] = useState(false);
  const [smtpTestRecipient, setSmtpTestRecipient] = useState("");
  const [notificationLoaded, setNotificationLoaded] = useState(false);
  const [notificationError, setNotificationError] = useState<string | null>(null);
  const [notificationStatus, setNotificationStatus] = useState<string | null>(null);
  const [notificationBusy, setNotificationBusy] = useState(false);
  const modelMatches = models.filter(item => `${item.id} ${item.name}`.toLowerCase().includes(modelSearch.toLowerCase())).slice(0, 60);

  useEffect(() => {
    getAiSettings()
      .then((settings) => {
        setDefaultEndpoint(settings.ollama_default_endpoint);
        if (settings.provider === "ollama" || settings.provider === "external") {
          setProvider(settings.provider);
        }
        setEndpointUrl(settings.endpoint_url ?? settings.ollama_default_endpoint);
        setModel(settings.model ?? "");
        setApiKeySet(settings.api_key_set);
        setLoaded(true);
      })
      .catch((err) => setError(err.message));
    getAbout()
      .then(setAbout)
      .catch((err) => setAboutError(err instanceof Error ? err.message : "Could not load About information."));
    getNotificationSettings()
      .then((settings) => {
        setSmtpHost(settings.host ?? "");
        setSmtpPort(settings.port ?? "587");
        if (settings.security === "starttls" || settings.security === "ssl" || settings.security === "none") setSmtpSecurity(settings.security);
        setSmtpUsername("");
        setSmtpUsernameSet(settings.username_set);
        setSmtpSender(settings.sender ?? "");
        setSmtpPasswordSet(settings.password_set);
      })
      .catch((err) => setNotificationError(err instanceof Error ? err.message : "Could not load notification settings."))
      .finally(() => setNotificationLoaded(true));
  }, []);

  useEffect(() => {
    if (!loaded) return;
    if (provider === "external" && !allowExternalDiscovery) return;
    const controller = new AbortController();
    setModels([]); setModelsError(""); setModelsBusy(true);
    const timer = setTimeout(() => {
      const endpoint = provider === "external" ? "https://openrouter.ai/api/v1/chat/completions" : endpointUrl;
      fetch(`/api/settings/ai/models?${new URLSearchParams({provider, endpoint_url: endpoint})}`, {signal: controller.signal})
        .then(async r => { const body = await r.json(); if (!r.ok) throw Error(body.detail); return body; })
        .then(body => setModels(body.models || []))
        .catch(e => { if (e.name !== "AbortError") setModelsError(e.message); })
        .finally(() => { if (!controller.signal.aborted) setModelsBusy(false); });
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [loaded, provider, endpointUrl, refreshModels, allowExternalDiscovery]);

  async function onSaveNotifications() {
    setNotificationError(null);
    setNotificationStatus(null);
    setNotificationBusy(true);
    try {
      const saved = await saveNotificationSettings({
        host: smtpHost,
        port: Number(smtpPort),
        security: smtpSecurity,
        username: smtpUsername,
        sender: smtpSender,
        password: smtpPassword || undefined,
        clear_credentials: clearSmtpCredentials,
      });
      setSmtpPassword("");
      setSmtpUsername("");
      setSmtpUsernameSet(saved.username_set);
      setSmtpPasswordSet(saved.password_set);
      setClearSmtpCredentials(false);
      setNotificationStatus("SMTP settings saved.");
    } catch (err) {
      setNotificationError(err instanceof Error ? err.message : "Could not save SMTP settings.");
    } finally {
      setNotificationBusy(false);
    }
  }

  async function onTestNotification() {
    setNotificationError(null);
    setNotificationStatus(null);
    setNotificationBusy(true);
    try {
      const saved = await saveNotificationSettings({
        host: smtpHost,
        port: Number(smtpPort),
        security: smtpSecurity,
        username: smtpUsername,
        sender: smtpSender,
        password: smtpPassword || undefined,
        clear_credentials: clearSmtpCredentials,
      });
      setSmtpPassword("");
      setSmtpUsername("");
      setSmtpUsernameSet(saved.username_set);
      setSmtpPasswordSet(saved.password_set);
      setClearSmtpCredentials(false);
      const result = await testNotificationEmail(smtpTestRecipient);
      setNotificationStatus(result.message);
    } catch (err) {
      setNotificationError(err instanceof Error ? err.message : "Test email could not be sent.");
    } finally {
      setNotificationBusy(false);
    }
  }

  function onProviderChange(next: "ollama" | "external") {
    setAllowExternalDiscovery(next === "external");
    setProvider(next);
    setEndpointUrl(next === "external" ? "https://openrouter.ai/api/v1/chat/completions" : defaultEndpoint);
    setModel(""); setApiKey(""); setStatus(null);
  }

  async function onTest() {
    setError(null);
    setStatus(null);
    setBusy(true);
    try {
      const result = await testAiSettings({
        provider,
        endpoint_url: provider === "external" ? "https://openrouter.ai/api/v1/chat/completions" : endpointUrl,
        model,
        api_key: apiKey || undefined,
      });
      setStatus(`Connected. Model ${result.model} replied.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setBusy(true);
    try {
      const saved = await saveAiSettings({
        provider,
        endpoint_url: provider === "external" ? "https://openrouter.ai/api/v1/chat/completions" : endpointUrl,
        model,
        api_key: apiKey || undefined,
      });
      setApiKey("");
      setApiKeySet(saved.api_key_set);
      setStatus("Saved. AI is ready to use.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (!loaded && !error) {
    return <LoadingState label="Loading settings" />;
  }

  return (
    <div className="settings-page">
      <p className="t-label" style={{ marginBottom: "var(--space-3)" }}>Preferences</p>
      <h1 className="t-display-xl">Settings</h1>
      <div style={{ display: "flex", gap: "var(--space-7)", marginTop: "var(--space-6)" }}>
        <nav aria-label="Settings sections" className="settings-nav">
          <a href="#ai" className="sidebar-link active"><Icon name="sparkle" />AI</a>
          <a href="#connections" className="sidebar-link"><Icon name="database" />Connections</a>
          <a href="#appearance" className="sidebar-link"><Icon name="sun" />Appearance</a>
          <a href="#notifications" className="sidebar-link"><Icon name="bell" />Notifications</a>
          <a href="#about" className="sidebar-link"><Icon name="info" />About</a>
        </nav>

        <div className="settings-content" style={{ flex: 1, minWidth: 0 }}>
        <form id="ai" className="settings-card" onSubmit={onSave}>
          <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
            AI configuration
          </h2>
          <p className="t-caption">Choose a downloaded Ollama model or OpenRouter. One setup powers every AI feature.</p>

          <fieldset style={{ border: "none", padding: 0, margin: "var(--space-5) 0" }}>
            <legend className="t-caption">Provider</legend>
            <label className="t-body-md" style={{ display: "block", marginTop: "var(--space-3)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider === "ollama"}
                onChange={() => onProviderChange("ollama")}
              />{" "}
              Ollama (local, private)
            </label>
            <label className="t-body-md" style={{ display: "block", marginTop: "var(--space-2)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider === "external"}
                onChange={() => onProviderChange("external")}
              />{" "}
              OpenRouter API (uses the internet)
            </label>
          </fieldset>

          {provider === "external" && (
            <p
              role="status"
              style={{
                color: "var(--status-warning)",
                background: "color-mix(in srgb, var(--status-warning) 12%, white)",
                border: "1px solid var(--status-warning)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-4)",
              }}
            >
              Using an external API may send parts of your data descriptions to that provider. Use Ollama
              for fully private AI.
            </p>
          )}

          <label className="t-caption" style={{ display: "block", marginTop: "var(--space-5)" }}>
            Endpoint URL
            <input
              className="text-input"
              style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }}
              readOnly={provider === "external"}
              value={provider === "external" ? "https://openrouter.ai/api/v1/chat/completions" : endpointUrl}
              onChange={(e) => setEndpointUrl(e.target.value)}
              placeholder={defaultEndpoint}
              required
            />
          </label>

          <div className="model-picker" onBlur={e => {if (!e.currentTarget.contains(e.relatedTarget as Node)) setModelListOpen(false);}}>
          <label className="t-caption" style={{ display: "block", marginTop: "var(--space-4)" }}>
            Model name
            <input
              className="text-input"
              style={{ display: "block", width: "100%", marginTop: "var(--space-2)", paddingRight: 44 }}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={modelListOpen}
              aria-controls="available-ai-models"
              aria-activedescendant={modelListOpen && modelMatches[activeModelOption] ? `model-option-${activeModelOption}` : undefined}
              autoComplete="off"
              value={model}
              onFocus={() => {setModelSearch(""); setActiveModelOption(0); setModelListOpen(true);}}
              onChange={(e) => {setModel(e.target.value); setModelSearch(e.target.value); setActiveModelOption(0); setModelListOpen(true);}}
              onKeyDown={e => {
                if (e.key === "Escape") {setModelListOpen(false); e.preventDefault();}
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {e.preventDefault(); setModelListOpen(true); setActiveModelOption(i => Math.max(0, Math.min(modelMatches.length - 1, i + (e.key === "ArrowDown" ? 1 : -1))));}
                if (e.key === "Enter" && modelListOpen && modelMatches[activeModelOption]) {e.preventDefault(); setModel(modelMatches[activeModelOption].id); setModelListOpen(false);}
              }}
              placeholder={provider === "ollama" ? "Select a downloaded model" : "Search OpenRouter models"}
              required
            />
          </label>
          <button type="button" className="model-picker-toggle" aria-label="Show available models" aria-expanded={modelListOpen} onClick={() => {setModelListOpen(v => !v); setModelSearch(""); setActiveModelOption(0);}}><Ico t="⌄" /></button>
          {modelListOpen && <div className="model-options" role="listbox" id="available-ai-models" aria-label="Available models">{modelMatches.map((m, i) => <button type="button" role="option" id={`model-option-${i}`} aria-selected={i === activeModelOption} tabIndex={-1} key={m.id} onMouseDown={e => e.preventDefault()} onClick={() => {setModel(m.id); setModelListOpen(false);}}><strong>{m.id}</strong>{m.name !== m.id && <span>{m.name}</span>}</button>)}{!modelMatches.length && <p className="t-caption">{modelsBusy ? "Loading models…" : modelsError || "No matching models. Refresh the list or enter a model ID."}</p>}</div>}
          </div>
          <div className="model-discovery"><p className="t-caption" role="status">{modelsBusy ? "Loading models…" : modelsError || (models.length ? `${models.length} models available. Type to filter or select a suggestion.` : provider === "external" && !allowExternalDiscovery ? "Select Refresh models to load OpenRouter models." : "No models found. Download a model in Ollama, then refresh.")}</p><button type="button" className="button-secondary-outline" onClick={() => {setAllowExternalDiscovery(true); setRefreshModels(v => v + 1);}} disabled={modelsBusy}><Ico t="Refresh models" /></button></div>
          {provider === "external" && <label className="t-caption" style={{ display: "block", marginTop: "var(--space-4)" }}>
            OpenRouter API key {apiKeySet ? "(saved  -  leave blank to keep)" : ""}
            <input
              className="text-input"
              type="password"
              autoComplete="off"
              style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={apiKeySet ? "Saved securely" : "sk-or-v1-…"}
            />
          </label>}
          {provider === "external" && <p className="t-caption">Stored in your credential vault. The key is never returned to the browser.</p>}

          {error && (
            <p style={{ color: "var(--status-danger)" }} role="alert">
              {error}
            </p>
          )}
          {status && <p style={{ color: "var(--status-good)" }}>{status}</p>}

          <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "var(--space-6)" }}>
            <button type="button" className="button-secondary-outline" onClick={onTest} disabled={busy}><Ico t="Test connection" /></button>
            <button type="submit" className="button-primary-dark" disabled={busy}><Ico t="Save" /></button>
          </div>

        </form>
          <ConnectionSettings />
          <section id="notifications" className="settings-card">
            <h2 className="t-heading-lg" style={{ marginTop: 0 }}>Notifications</h2>
            {!notificationLoaded ? <p className="t-caption">Loading notification settings.</p> : null}
            <p className="t-caption">Configure an SMTP server for email alerts and automation actions. Recipient addresses are entered on each alert or action. Webhook URLs are configured on their alert or action.</p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
              <label className="t-caption">SMTP host<input className="text-input" value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
              <label className="t-caption">Port<input className="text-input" type="number" min={1} max={65535} value={smtpPort} onChange={(e) => setSmtpPort(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
              <label className="t-caption">Encryption<select className="text-input" value={smtpSecurity} onChange={(e) => setSmtpSecurity(e.target.value as "starttls" | "ssl" | "none")} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">None</option></select></label>
              <label className="t-caption">SMTP username {smtpUsernameSet ? "(saved - leave blank to keep)" : "(optional)"}<input className="text-input" autoComplete="off" disabled={clearSmtpCredentials} value={smtpUsername} onChange={(e) => setSmtpUsername(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
              <label className="t-caption">Sender email address<input className="text-input" type="email" value={smtpSender} onChange={(e) => setSmtpSender(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
              <label className="t-caption">SMTP password {smtpPasswordSet ? "(saved - leave blank to keep)" : "(optional)"}<input className="text-input" type="password" autoComplete="new-password" disabled={clearSmtpCredentials} value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
            </div>
            {(smtpUsernameSet || smtpPasswordSet) && <label className="t-caption" style={{ display: "block", marginTop: "var(--space-3)" }}><input type="checkbox" checked={clearSmtpCredentials} onChange={(e) => setClearSmtpCredentials(e.target.checked)} /> Remove saved SMTP username and password on save</label>}
            {smtpSecurity === "none" && <p className="t-caption" style={{ color: "var(--status-warning)" }}>Email will be sent without transport encryption.</p>}
            {notificationError && <p role="alert" style={{ color: "var(--status-danger)" }}>{notificationError}</p>}
            {notificationStatus && <p role="status" style={{ color: "var(--status-good)" }}>{notificationStatus}</p>}
            <button type="button" className="button-primary-dark" onClick={onSaveNotifications} disabled={notificationBusy} style={{ marginTop: "var(--space-3)" }}><Ico t="Save SMTP settings" /></button>
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "end", marginTop: "var(--space-5)" }}>
              <label className="t-caption" style={{ flex: 1 }}>Test recipient<input className="text-input" type="email" value={smtpTestRecipient} onChange={(e) => setSmtpTestRecipient(e.target.value)} style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }} /></label>
              <button type="button" className="button-secondary-outline" onClick={onTestNotification} disabled={notificationBusy || !smtpTestRecipient}><Ico t="Send test email" /></button>
            </div>
            <ChatChannels />
          </section>

          <section id="appearance" className="settings-card">
            <h2 className="t-heading-lg" style={{ marginTop: 0 }}>Appearance</h2>
            <Appearance />
          </section>

          <section id="about" className="settings-card">
            <h2 className="t-heading-lg" style={{ marginTop: 0 }}>About Tarsier</h2>
            {aboutError && <p role="alert" style={{ color: "var(--status-danger)" }}>{aboutError}</p>}
            {about ? (
              <>
                <p className="t-body-md">Version {about.version}</p>
                <p className="t-body-md">License: {about.license}</p>
                <ul className="t-body-md" style={{ paddingLeft: "var(--space-5)" }}>
                  {about.links.map((link) => (
                    <li key={link.href}>
                      <a href={link.href} target="_blank" rel="noreferrer" style={{ color: "var(--primary)" }}>{link.label}</a>
                    </li>
                  ))}
                </ul>
              </>
            ) : !aboutError ? <p className="t-caption">Loading About information.</p> : null}
          </section>
        </div>
      </div>
    </div>
  );
}

export default Settings;
