import { Ico, Icon } from "../components/Icon";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

type Entry = {label: string; url: string};

export default function CommandPalette() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  function open() {
    setQuery(""); setError(""); dialog.current?.showModal();
    fetch("/api/navigation").then(r => {if (!r.ok) throw Error(); return r.json();}).then(setEntries).catch(() => setError("Could not load items. Close and retry."));
  }
  useEffect(() => {
    function key(e: KeyboardEvent) { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); dialog.current?.open ? dialog.current.close() : open(); } }
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, []);
  const matches = entries.filter(e => e.label.toLowerCase().includes(query.toLowerCase())).slice(0, 40);
  function jump(entry: Entry) { dialog.current?.close(); navigate(entry.url); }
  return <><button type="button" className="button-secondary-outline" onClick={open}><Icon name="search" /><span className="sr-only">Search </span><kbd>Ctrl K</kbd></button>
    <dialog ref={dialog} aria-label="Jump to a screen or layer" className="command-dialog">
      <div style={{display: "flex", gap: 12}}><input autoFocus className="text-input" placeholder="Find a screen, layer, or table…" aria-label="Search navigation" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => {if (e.key === "Enter" && matches[0]) { e.preventDefault(); jump(matches[0]); }}} /><button className="button-secondary-outline" onClick={() => dialog.current?.close()}><Ico t="Close" /></button></div>
      {error && <p role="alert">{error}</p>}
      <div className="command-results">{matches.map(e => <button className="command-result" key={e.url} onClick={() => jump(e)}>{e.label}<span aria-hidden>↗</span></button>)}{!matches.length && <p>No matching destinations.</p>}</div>
      <p className="t-caption">Navigation only · Tab to select · Enter to open · Esc to close</p>
    </dialog></>;
}
