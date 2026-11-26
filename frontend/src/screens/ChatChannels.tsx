import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
export default function ChatChannels() {
  const [configured, setConfigured] = useState<Record<string, boolean>>({});
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  useEffect(() => {fetch("/api/settings/chat-channels").then(r => r.json()).then(setConfigured).catch(() => setMessage("Could not load chat channels."));}, []);
  async function save(channel: string, clear = false) {
    try {const response = await fetch(`/api/settings/chat-channels/${channel}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({url: urls[channel] || "", clear})}); const body = await response.json(); if (!response.ok) throw Error(body.detail); setConfigured(body); setUrls({...urls, [channel]: ""}); setMessage(`${channel} settings saved.`);} catch(e) {setMessage(e instanceof Error ? e.message : "Could not save channel.");}
  }
  return <div style={{marginTop: 24}}><h3 className="t-heading-lg">Chat notifications</h3><p className="t-caption">Use Slack or Teams incoming webhooks that accept a JSON text message. URLs are stored in the credential vault and never displayed back.</p>{["slack", "teams"].map(channel => <div key={channel} style={{display: "flex", gap: 12, marginTop: 20, alignItems: "end", flexWrap: "wrap"}}><label className="channel-field" style={{flex: 1, minWidth: 180}}>{channel === "slack" ? "Slack" : "Teams"} {configured[channel] ? "(configured)" : "(not configured)"}<input className="text-input" type="password" autoComplete="new-password" style={{width: "100%", display: "block", marginTop: 8}} value={urls[channel] || ""} onChange={e => setUrls({...urls, [channel]: e.target.value})} placeholder="HTTPS incoming webhook URL" /></label><button type="button" className="button-secondary-outline" onClick={() => save(channel)} disabled={!urls[channel]}><Ico t="Save channel" /></button>{configured[channel] && <button type="button" className="button-secondary-outline" onClick={() => save(channel, true)}><Ico t="Remove" /></button>}</div>)}{message && <p role="status">{message}</p>}</div>;
}
