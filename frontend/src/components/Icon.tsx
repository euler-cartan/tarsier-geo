/** Line icons drawn inline (no icon library), plus the icon-only button label. */
const PATHS = {
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  close: "M18 6 6 18M6 6l12 12",
  check: "M20 6 9 17l-5-5",
  trash: "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z",
  save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2ZM17 21v-8H7v8M7 3v5h8",
  play: "M7 4v16l13-8Z",
  pause: "M8 5v14M16 5v14",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6",
  back: "M19 12H5M12 19l-7-7 7-7",
  skip: "M5 4l10 8-10 8ZM19 5v14",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM21 21l-4.3-4.3",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9ZM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8Z",
  settings: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4",
  map: "M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3ZM9 3v15M15 6v15",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  eyeOff: "M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 3.8M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.6 9.6 0 0 0 4.4-1M9.9 9.9a3 3 0 0 0 4.2 4.2",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4Z",
  external: "M7 17 17 7M7 7h10v10",
  graph: "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM9 6h6M8 8.5l8 7",
  compare: "M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4",
  sync: "M17 2l4 4-4 4M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4M21 13v1a4 4 0 0 1-4 4H3",
  camera: "M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2ZM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
  fit: "M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5",
  grid: "M3 3h7v7H3ZM14 3h7v7h-7ZM14 14h7v7h-7ZM3 14h7v7H3Z",
  link: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  filterOff: "M13 13v6l-4 2v-8L3 4h12M17 4l4 4M21 4l-4 4",
  download: "M12 3v12M7 10l5 5 5-5M5 21h14",
  mail: "M4 4h16v16H4ZM4 7l8 6 8-6",
  zap: "M13 2 3 14h9l-1 8 10-12h-9Z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  diff: "M12 3v14M5 10h14M5 21h14",
  chevronDown: "M6 9l6 6 6-6",
  home: "M3 11 12 3l9 8M5 10v11h14V10",
  chart: "M3 3v18h18M8 17v-5M13 17V8M18 17v-8",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l4 2",
  database: "M12 8c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3ZM4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM12 16v-4M12 8h.01",
  expand: "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
  shrink: "M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7",
  copy: "M9 9h12v12H9ZM5 15H3V3h12v2",
  newChat: "M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4Z",
  arrowUp: "M12 19V5M5 12l7-7 7 7",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}

// First match wins, so the more specific phrases come first.
const RULES: [RegExp, IconName][] = [
  [/^−$/, "minus"], [/^fit/i, "fit"], [/^\+$/, "plus"], [/^×$/, "close"], [/^⌄$/, "chevronDown"],
  [/^back/i, "back"], [/^skip/i, "skip"], [/^(cancel|close|discard|reject)/i, "close"],
  [/^(delete|remove|clear history)/i, "trash"], [/^clear/i, "filterOff"],
  [/^(edit)/i, "edit"], [/^(save|test & save|approve|create alert)/i, "save"],
  [/^(confirm|mark as reviewed|enable)/i, "check"], [/^(add|connect|\+)/i, "plus"],
  [/^pause/i, "pause"], [/^(resume|run|test run|read raster|evaluate)/i, "play"],
  [/^(retry|refresh)/i, "refresh"], [/^sync/i, "sync"], [/^(draft|explain|ask|generate)/i, "sparkle"],
  [/^hide diff/i, "diff"], [/^show diff/i, "diff"], [/^hide/i, "eyeOff"], [/^show on map/i, "map"],
  [/^(preview|review|explore|show)/i, "eye"], [/^(scan|search)/i, "search"],
  [/graph|flowchart/i, "graph"], [/^compare/i, "compare"], [/^capture/i, "camera"],
  [/^fit/i, "fit"], [/^arrange/i, "grid"], [/^(open|view|go to)/i, "external"],
  [/^send test email/i, "mail"], [/^test/i, "zap"], [/^load/i, "download"],
  [/^install/i, "download"], [/^settings$/i, "settings"], [/^ai$/i, "sparkle"],
];

/** A button's label shown as an icon: the words stay available to screen readers and as a tooltip. */
export function Ico({ t }: { t: string }) {
  const busy = t.endsWith("…");
  const name = RULES.find(([rule]) => rule.test(t))?.[1];
  if (!busy && !name) return <>{t}</>;
  return (
    <span className="ico" title={t}>
      {busy ? <span className="ico-spin" aria-hidden="true" /> : <Icon name={name as IconName} />}
      <span className="sr-only">{t}</span>
    </span>
  );
}
