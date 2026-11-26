import { useEffect, useState } from "react";

export function applyTheme(theme: string) {
  document.documentElement.dataset.theme = theme === "dark" ? "dark" : "light";
}

export default function Appearance() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || "light");
  const [error, setError] = useState("");
  useEffect(() => { fetch("/api/settings/appearance").then(r => r.json()).then(s => { setTheme(s.theme); applyTheme(s.theme); }).catch(() => setError("Could not load appearance.")); }, []);
  async function change(value: string) {
    const response = await fetch("/api/settings/appearance", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({theme: value})});
    if (!response.ok) { setError("Could not save appearance."); return; }
    setTheme(value); applyTheme(value); setError("");
  }
  return <fieldset><legend className="t-caption">Choose your workspace theme. Your preference is saved automatically.</legend><div className="theme-options">{["light", "dark"].map(value => <label key={value} className="theme-choice"><span aria-hidden="true" className={`theme-preview ${value}`}><i /><b /></span><input type="radio" name="appearance" checked={theme === value} onChange={() => void change(value).catch(() => setError("Could not save appearance."))} /> {value === "light" ? "Light" : "Dark"}</label>)}</div>{error && <p role="alert">{error}</p>}</fieldset>;
}
