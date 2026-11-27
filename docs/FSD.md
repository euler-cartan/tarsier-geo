# Tarsier — Frontend Specification Document (FSD)

**Version:** 1.0 (v1 scope)
**Status:** Approved for build
**Date:** 2026-10-10
**Companion to:** PRD v1.0, TAD v1.0
**Platform:** Desktop web app only (no mobile layout in v1)
**Brand base:** The v2 design tokens in Section 2 (adopted 2026-10-13), re-purposed for a data-dense working dashboard rather than a marketing site. Supersedes the earlier direction below (Section 1 kept for history; Section 2 is the current source of truth for tokens).

---

## 0. How to use this document

### For Claude Code (the builder)
- This document defines **every screen**, its **layout**, its **states** (loading / empty / error / populated), and the **components** used.
- Build using the **React + TypeScript + MapLibre** stack locked in the TAD.
- Use the **design tokens in Section 2** for all colors, type, spacing, and components. Do not invent new colors or font weights outside this system.
- Each screen maps to a PRD feature (A–E, automation builder, flowchart, AI assistant) — build screens in the same phase order as the PRD Build Order.
- If a screen needs a layout decision not covered here, **ask before inventing one.**

### For the Manager (reviewer)
- Each screen section lists what must be present. Use it to check built screens against spec.

---

## 1. Design direction — superseded 2026-10-13, kept for history

Everything in this Section 1 (the old indigo/white/teal direction) is **replaced** by Section 2 below, which holds the v2 design tokens. This section is left in place only so anyone reading the history understands why some earlier screen descriptions (written before 2026-10-13) mention indigo, teal, or rounded-rectangle-only buttons — those mentions are now superseded by Section 2's tokens wherever they conflict. No screen's *layout* changes (what's on the page, what the tabs are, what a table shows) — only the colors, type, and button/card shapes change.

---

## 2. Design tokens (v2, both light and dark mode)

**Source:** the tokens in this section, adopted 2026-10-13 (Manager + project owner decision). Tarsier ships with **both a light mode and a dark mode**, not light-only; the person can switch, and the toggle lives in Settings → Appearance (FSD §13).

**Fonts:** **Inter** for body and interface text, and **Newsreader** for display headings, both bundled with the app. Code uses the system's monospace font.

**Buttons are pill-shaped for primary actions** (matches v2's signature look) — this is a visible change from the old rounded-rectangle-only rule. Secondary/tertiary actions use a small 5px-radius "ghost" style, not a pill, so the UI doesn't turn into a wall of pills — see Section 14's updated component table.

### 2.1 Colors

**Shared across both modes** (same hex in light and dark — these are Tarsier's "constant" brand accents):
```
accent-interactive:    #0052ef  (electric blue — universal hover/active state on every interactive element: links, buttons, focus rings, active nav/tab)
accent-cta:            #f36458  (coral-red — primary button fill in both modes; never combine with accent-interactive on the same element, only as its hover target)
status-good:           #19d600  (green — health score good, check passed, change is normal)
status-warning:         #b8860b  (warm amber — health score medium, minor quality issue, nearing a threshold; kept from the earlier palette, v2 doesn't name one)
status-danger:          #dd0000  (pure red — health score poor, check failed, mass-delete alert, critical issue)
status-info:            #0052ef  (electric blue, reused — informational badges, neutral counts)
status-neutral:         #797979  (medium gray — disabled, "no data," stale)
ai-accent:              #e600ff  (vivid magenta — AI assistant icon, AI-suggested items, AI chat bubble, the Staged Review Card's accent border; sRGB fallback for v2's wide-gamut magenta)
```

**Light mode** (default):
```
canvas:                #ffffff  (page background)
canvas-soft:            #ededed (alternating rows, subtle panels, elevated surfaces)
ink:                    #0b0b0b  (default text — near-black, not pure black)
ink-mute:                #353535  (secondary text)
ink-faint:                #797979  (tertiary / disabled text)
hairline:                #e0e0e0  (borders, light)
on-accent:                #ffffff  (text on filled buttons/badges)

sidebar-bg:             #0b0b0b  (dark sidebar — the one dark surface, for wayfinding contrast, same in both modes)
sidebar-text:           #ffffff
sidebar-text-mute:      #b9b9b9
sidebar-active-bg:      #212121
```

**Dark mode:**
```
canvas:                #0b0b0b  (near-black canvas — not a "mode," the natural working surface per v2's direction)
canvas-soft:            #212121 (elevated cards, panels, alternating rows)
ink:                    #ffffff  (default text)
ink-mute:                #b9b9b9  (secondary text)
ink-faint:                #797979  (tertiary / disabled text)
hairline:                #212121  (subtle borders) / #353535 (more visible borders, dividers)
on-accent:                #ffffff  (text on filled buttons/badges)

sidebar-bg:             #0b0b0b  (unchanged — already dark)
sidebar-text:           #ffffff
sidebar-text-mute:      #b9b9b9
sidebar-active-bg:      #212121
```

**Depth in both modes** is mostly **color-based, not shadow-based** (per v2's own "Do" rule): `canvas` → `canvas-soft` → a slightly more visible border for emphasis, rather than drop shadows. A focus ring (2px solid `accent-interactive`) is the one place a ring-shadow is used, for accessibility.

### 2.2 Typography

Fonts by token: `display-*` and `stat-xl` use **Newsreader**; `heading-*`, `body-*`, `button-md`, `caption`, `micro` and `label` use **Inter**; `code` uses the system's monospace font.

| Token | Size | Weight | Letter-spacing | Use in Tarsier |
|---|---|---|---|---|
| `display-mega` | 64px | 300 | -1.92px | Welcome headline on first run |
| `display-xl` | 48px (36px on Settings) | 300 | -0.96px | Overview and item-page titles, "Your connections", Settings |
| `display-lg` | 36px | 300 | -0.36px | Other page titles (e.g. "Alerts," "Changes") |
| `display-md` | 32px | 300 | -0.32px | Review dialog titles and other large section titles |
| `display-sm` | 24px | 300 | 0.16px | Section titles, empty-state headings, connection names |
| `heading-lg` | 20px | 500 | 0 | Card titles, panel headers |
| `body-lg` | 18px | 500 | 0.18px | Welcome intro text (set to 400 there), emphasized notes |
| `body-md` | 16px | 400 | 0.16px | Default UI text, form fields (data tables use 15px) |
| `body-strong` | 16px | 500 | 0.16px | Defined, not used by any screen yet |
| `button-md` | 15px | 500 | 0 | Button labels (13px on Settings) |
| `caption` | 14px | 400 | 0 | Helper text, timestamps |
| `micro` | 12px | 500 | 0.2px | Fine print, small notes |
| `label` | 12px | 600 | 0.96px, uppercase | Small eyebrow labels above titles and groups |
| `code` | browser default | 400 | normal | Preformatted blocks (no dedicated type style) |

**Large numeric style:**
| `stat-xl` | 48px / 300, tabular numbers, -0.96px tracking | Headline stats on Overview (total layers, total size) |

Some components set their own sizes outside these tokens (e.g. data tables 15px, table headers 12px/600 uppercase, status badges 11px/600 uppercase, the health-ring number 30px/600).

**Don't** use weights above 600 anywhere (v2's own rule) — this replaces the old `body-strong` 700-weight token. Exception: the Flowchart icon letter uses weight 700.

### 2.3 Spacing, radius, elevation

**Spacing:** unchanged — 2/4/8/12/16/24/32/64px scale.

**Radius (updated for v2):**
```
radius-xs:    3px    (inputs, textareas)
radius-sm:    5px    (secondary/ghost buttons, small tags)
radius-md:    6px    (standard cards, containers — Tarsier's default card radius, down from 12px)
radius-lg:    12px   (large cards, modals, the Staged Review Card)
radius-pill:  9999px (primary buttons only)
```

**Elevation:** flat, color-based depth as described in 2.1 above — no offset drop shadows; a 1px border is the primary separator between surfaces in both modes.

---

## 3. App shell (used on every screen)

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar: [Connection switcher ▾]      [AI quick-ask] [⚙ Settings] │
├───────────┬─────────────────────────────────────────────────┤
│           │                                                 │
│ Sidebar   │   Main content area                             │
│ (dark,    │   (light canvas, scrollable)                    │
│ indigo)   │                                                 │
│           │                                                 │
│ Overview  │                                                 │
│ Layers    │                                                 │
│ Statistics│                                                 │
│ Quality   │                                                 │
│ Changes   │                                                 │
│ Alerts    │                                                 │
│ Automations│                                                │
│ Flowchart │                                                 │
│ AI Chat   │                                                 │
│           │                                                 │
└───────────┴─────────────────────────────────────────────────┘
```

- **Sidebar** — dark indigo (`sidebar-bg`), fixed width 240px, always visible. Active item has `sidebar-active-bg` background + left accent bar. Icons + labels.
- **Top bar** — white, height 64px, border-bottom `hairline`. Left: connection switcher (shows current database name + type icon; dropdown lists all connections + "Add connection"). Right: AI quick-ask icon (opens AI side panel, Section 11) and Settings gear.
- **Main content** — `canvas` background, 32px page padding, max content width 1400px centered on very wide screens.

**Acceptance check:** sidebar and top bar persist across every screen; switching connections updates all screens to that database's data; active sidebar item always matches the current screen.

---

## 4. Screen: Connection list / Welcome

**When shown:** app start, or "Add connection" from the switcher.

**If no connections exist (first run):**
- Centered single-column welcome panel on `canvas`.
- `display-mega` headline: "Connect your first database."
- Short `body-lg` description of what Tarsier does (one sentence).
- A set of connection-type cards (one per type: PostGIS, Oracle, SQL Server, Files, ArcGIS Enterprise, Geoserver) using `card-feature` styling — icon, type name, one-line description.
- Clicking a card opens the **Add Connection flow** (Section 5).

**If connections exist:**
- A table/grid of connection cards: name, type icon, status (connected/error), last-checked time, health score badge.
- "Add connection" button (`button-primary-pill`) top-right.
- Clicking a card opens that database's **Overview** (Section 6).

**Acceptance check:** empty state and populated state both render correctly; every connection type is represented as its own clearly labeled option.

---

## 5. Screen: Add / Edit Connection

**Layout:** modal or full-page step form (step form recommended for clarity, given per-type fields differ).

**Steps:**
1. **Pick type** — the 6 connection-type cards from Section 4.
2. **Enter details** — fields vary by type (host/port/credentials for databases; folder path for files; URL for ArcGIS/Geoserver). Use `text-input` styling throughout.
3. **Feature notice** — before saving, show a clear panel (using `status-warning` color accents, not an error) listing what is **not available** for this connection type, per the PRD's tier table. Example copy: *"Files connections don't support change tracking — you'll still get statistics and quality checks."*
4. **(PostGIS only) Optional trigger permission** — a clearly separated, skippable step: *"Enable full change tracking? Tarsier can install a one-time history log in your database (needs write permission). You can skip this and add it later."* Two buttons: "Enable" (`button-primary-pill`) and "Skip for now" (`button-secondary-ghost`).
5. **Test & save** — "Test connection" button runs a live check before allowing save; shows success/error inline.

**Acceptance check:** every connection type has correct fields; the tier-notice step always appears before save; the trigger-permission step only appears for PostGIS and is skippable; a failed test blocks saving with a clear error message.

A PostgreSQL database without PostGIS remains usable for non-spatial tables. Show this exact notice: "PostGIS is not installed in this database. Spatial features are unavailable; non-spatial tables are still available."

---

## 6. Screen: Overview

Every sample-derived result must be labelled wherever shown. Zero findings in a sample display 'none found in sample, not a full check' in a neutral state. Aggregate health carries a sample label when sampled quality contributes. Sample-first mode remains backend-only in rc2.

**Purpose:** PRD Feature A — the landing page for a connected database.

**Layout (top to bottom):**
1. **Header row** — database name (`display-xl`), connection type badge, "last checked" caption, a "Run full check" button (`button-secondary-ghost`).
2. **Headline stats row** — 4 stat cards: Overall health score (color-coded ring: good/warning/danger; ring number 30px / weight 600), total layers and total size (`stat-xl` numbers), last change detected.
3. **Layer list table** — sortable/filterable table. Columns: name, type icon (vector/raster/tabular), row/feature count, size, last changed, projection, index present (✓/✗), quality score (colored badge), health score (colored badge). Clicking a row opens the **Detail page** (Section 7).
   - **Stale layers** and **heavy layers** are flagged with a small `micro` badge in the row (e.g. "Stale — 94 days").
4. **Relationships summary card** — small preview diagram + "Open full flowchart →" link to Section 12.
5. **Projection overview card** — small chart/list grouping layers by coordinate system, flags mismatches in `status-warning`.

**States:** loading (skeleton rows), empty (no layers found — rare, show guidance), populated (above), error (connection lost — banner at top, `status-danger`). Tables the role cannot read remain in the list with the exact state "no permission"; show a count as "1 table shown with no permission." or "N tables shown with no permission."

**Acceptance check:** every item in PRD 7.1 is present and reads from live/cached data; clicking any layer row navigates to its detail page; stale/heavy flags appear correctly.

---

## 7. Screen: Layer / Table / Raster detail page

**Purpose:** PRD Feature 7.9 — the dedicated page for one item, type-aware.

**Layout (shared header, then type-specific tabs):**
1. **Header** — item name (`display-xl`), type badge, health score badge, "Run checks now" button.
2. **Tabs** (only the tabs relevant to this item's type are shown):
   - **Overview** — always shown: size, last changed, schema/column list, map preview (vector/raster) or sample rows (tabular).
   - **Statistics** — PRD Feature B (see Section 8). Hidden if not applicable. **Hidden entirely for raster items** — raster per-band numbers and histograms belong on the raster Overview tab (this section), not Feature B's column-stats tab.
   - **Quality** — PRD Feature C (see Section 9). Hidden if not applicable. **Hidden for raster** (raster quality is the Overview fields in PRD §8). Tabular items show only completeness + custom rules (no geometry/topology/boundary).
   - **History** — PRD Feature D (see Section 10). Hidden entirely for files and raster (no tracking); shown with a "limited" note for partial-tracking sources.
   - **Connections** — this item's links from the flowchart (Section 12), shown inline.

**Type-specific overview content:**
- **Vector:** map preview (MapLibre), geometry type, feature count, attribute table schema.
- **Raster:** all fields from PRD Section 8 (pixel size, bands, projection, footprint, per-band histogram, nodata %, bit depth, overviews present, cloud cover if available). Missing metadata shown as "Not available" in `ink-faint`, never as an error.
- **Tabular:** sample rows table, column schema, row count.

**Acceptance check:** tabs shown match what's valid for the item's type (PRD 6.1–6.3); raster never shows a History tab; files never show a working History tab (shows "not available for file connections" instead of being hidden, so the user understands why).

---

## 8. Screen/panel: Statistics (Feature B)

Lives inside the layer detail page's **Statistics tab**. A **global Statistics section** in the sidebar for cross-layer queries is specified in outline only — **not in Phase 3**; leave the sidebar item disabled until that screen is fully specified.

**Per-column statistics table:** column name, type, min, max, average, empty count, unique count, top values (small inline bar or list). Sortable.

**Flags row (above the table):** badges for messy categories, out-of-range values, duplicates, map outliers, null geometry — each clickable. A click must show the **actual matching sample rows** (not just counts). For map outliers and null geometry, also plot those specific points on the map.

**RC1 full-statistics guard:** For tables above 20,000 estimated rows, replace the table's full-statistics action with "Full statistics are not available for tables this large in this release. Sample statistics are shown and labelled." The Overview full check refreshes their sample statistics and shows each table as "skipped: too large for full check; sample used". For eligible tables, show "Checking all rows; the current sample remains visible while this runs." during the full run.

**AI query box** — persistent input at the top of the Statistics section: *"Ask about this data…"* placeholder. Below it: a results table/map that updates based on the AI's interpreted **structured filter** (TAD §7.2 — schema only in, filter out, Tarsier applies it read-only), plus a small caption showing that filter for transparency (e.g. "Showing: year < 2010 AND material IS NULL"). If AI is not configured: show a `status-warning` **"Set up AI first"** prompt with a link to Settings instead of running a query. If an external API is configured: show the TAD §7.2 privacy warning.

**Acceptance check:** every statistic from PRD 7.2 is shown; flags are clickable and filter correctly; the AI query box shows both the result and the underlying query it ran.

---

## 9. Screen/panel: Quality checks (Feature C)

Lives inside the layer detail page's **Quality tab**.

**Layout:**
- A **checklist panel** — one row per check (geometry validity; topology gaps / overlaps / slivers / dangles as four rows so each can finish on its own per DVS §8; completeness; custom attribute rules; projection; boundary). Each row has a status badge (good/warning/danger) and a count of failing features. Consistency is **not** a separate row — it is a custom-rule kind (when field X = Y, geometry type must be Z), per TAD Phase 4.
- Clicking a check row expands a **results table** listing the specific failing features, with a "show on map" action (highlights them in a MapLibre preview).
- **Custom rules manager** — a simple form list: attribute rules (field, operator, value) and geometry-type rules (when field = value, geometry must be type). Create / edit / delete, `text-input` and `button-secondary-ghost`. **If a rule was AI-authored** (drafted via "Explain this with AI" or the AI panel), it does not save directly from this form — it routes through the **Staged Review Card** (Section 18) first. A manually-typed rule saves immediately as today; only AI-drafted rules get the extra review step.
- **Boundary picker** — choose another vector layer on this connection as the expected area.
- "Explain this with AI" is **Phase 7** (PRD build order), not shown on this tab in Phase 4.

Extend the existing custom-rule form with the three families. For column
comparison, show a picker of cached columns from the same table and the selected
comparison operator. Reject incompatible types on the server. Label a pattern
input “Regular expression.” Hide the value control for IS UNIQUE and save no value.
Reuse existing forms, rule lists, edit/delete controls, errors and sampled-result
labels. Display “N rows skipped, value empty” and explain that null, empty-string
and whitespace-only operands are skipped, including either operand for column
comparison. Label uniqueness as sample-limited when appropriate. Keep the existing
Staged Review Card and approval flow for AI drafts. Add no screen or navigation.

Keep IS UNIQUE out of alert choices and reject saved/API attempts with “IS UNIQUE
is available only for quality rules, not alerts.” Explain the opposite direction
with these examples: quality total_value >= land_value flags a lower total, while an alert total_value < land_value fires; quality ZIP MATCHES ^[0-9]{5}$ flags a malformed ZIP, while an alert DOES NOT MATCH fires. Keep IS UNIQUE available to
quality rules. Do not introduce an implicit duplicate-alert operator.


**Acceptance check:** every Phase 4 check appears; failing features are listed and can be shown on the map; custom rules can be created, edited, deleted; an AI-drafted rule cannot be saved without passing through the Staged Review Card.

---

## 10. Screen/panel: Change tracking (Feature D)

Lives inside the layer detail page's **History tab**, plus a **global Changes section** in the sidebar for database-wide change activity.

**Global Changes screen:**
- **Change-volume graph** at the top (line/bar chart over time) — sudden spikes visually stand out (colored `status-danger` points).
- **Change feed** below — a reverse-chronological list: who, what, when, which layer, before→after summary. Filterable by user, layer, date range.
- **Compare two dates** — a date-range picker that produces a before/after diff view.
- **Auto change report** — a card showing the latest scheduled summary (daily/weekly), with "view full report" and "configure schedule" (links to Automations, Section 11).

On the Changes screen and the item's Changes tab, render one existing warning-style
banner above the change controls when tracking_health reports a nonzero failure
counter, an outdated logger or missing triggers. Reuse existing spacing, typography
and warning colors. Do not add a screen, modal, navigation item or settings form.
Use these exact messages, combining applicable messages within the same banner:

"Some changes may be missing from this history."

"Change tracking needs an update. Contact the connection owner."

"Change tracking is incomplete because one or more tracking triggers are missing."

When health cannot be verified, show: "Tracking health could not be verified. This history may be incomplete."

A single button "Mark as reviewed" inside the banner calls the dedicated acknowledgement endpoint. After it is used, the banner changes to a calmer informational style reading "Reviewed on {date}. Earlier possible gaps were acknowledged; this does not mean the missing changes were recovered." A new failure after that date shows the warning style again. No new screen, modal, navigation item or settings form.

**Single-feature history (inside a layer):**
- Clicking any single feature (from the map or a table row) opens a **feature history panel** — a vertical timeline of that one feature's changes.

**Acceptance check:** all items from PRD 7.4 are present; mass-change events are visually flagged; compare-two-dates produces an accurate diff; single-feature history opens from both map and table.

---

## 11. Screen: Alerts (Feature E) + Automation builder + AI panel

### 11.1 Alerts list
- Table of configured alerts: type, target (layer/database), condition summary, status (active/paused), last triggered.
- "New alert" button opens a simple form: pick alert type (from the PRD 7.5 list) → pick target → set condition → pick notification method (reuses the automation action list below).

### 11.2 Automation builder
**Visual, node-based workflow builder**, built with a drag-and-drop canvas:
- **Trigger node** (left) → **Condition node(s)** (middle, optional) → **Action node(s)** (right). Connected with lines.
- A **node palette** sidebar-within-the-canvas lists available triggers/conditions/actions (per PRD 7.6), dragged onto the canvas.
- **Templates gallery** — a starting screen before the blank canvas, showing ready-made recipes as cards (e.g. "Notify me on mass delete") that open pre-built into the canvas for editing.
- Each node is a small rounded card (`card-feature-row` styling) with its config inline (e.g. the action node for "send email" shows an address field directly on the node).
- "Test run" button simulates the automation against recent data before saving.
- **When the graph was drafted by AI** (the "help build an automation" job, PRD §7.7 job 4), clicking **Save** does not save directly — it opens the **Staged Review Card** (Section 18) first. A graph built by hand on the canvas saves immediately as today; only an AI-drafted graph gets the extra review step.

### 11.3 AI panel
A **slide-out panel from the right** (triggered by the top bar's AI icon, or contextually from Quality/Changes screens), using the `ai-accent` (magenta) AI accent:
- Chat-style interface: user message bubbles in `canvas-soft`, AI message bubbles with a thin `ai-accent` left border and a small AI icon.
- Shows which of the 4 jobs is active (query / explain-changes / explain-quality / build-automation) as a small tag on the AI's reply.
- If AI isn't configured: the panel shows a `status-warning` styled prompt — "Set up AI in Settings" with a direct link — instead of a chat box.
- If external API is selected in Settings, every AI panel session shows a persistent, dismissible-once-per-session banner: the Section 1 privacy warning text, styled with `status-warning`.
- Answering a plain question (job 1, "explain today's changes," "explain a quality problem") is **not** gated by the Staged Review Card — nothing is being saved, so the answer shows directly in the chat. Only the two jobs that produce something savable (a custom rule, an automation) route through Section 18.

**Acceptance check:** alerts list and creation form work for every alert type; the automation builder supports building and testing a multi-step chain and starting from a template; the AI panel correctly reflects configured/unconfigured state and shows the privacy warning when using an external API.

---

## 12. Screen: Connection flowchart (Feature 7.8)

**Layout:** full-page interactive diagram canvas (pan/zoom), built with a graph-layout library rendering nodes for each table/layer/raster/CSV, connected by lines for relationships.

- **Confirmed links** (official foreign keys) — solid line.
- **Guessed links** — dashed line, with a small "?" badge; clicking it opens a confirm/reject prompt.
- **User-added links** — solid line with a small "user" icon; added via a "Connect items" button that lets the user pick two items and a joining column.
- Nodes are colored by type (vector / raster / tabular) using small corner badges, not full node recoloring (keeps the diagram readable at scale).
- Clicking any node navigates to that item's detail page (Section 7).

**Acceptance check:** all three link kinds render with correct visual distinction; guessed links can be confirmed or rejected; user can manually add a link; clicking a node navigates correctly.

---

## 12.1 Screen: Relationship Graph (PRD §14.1 — Spatial Knowledge Graph Engine)

**Added 2026-10-13, Manager + user decision.** Supersedes the earlier interim design (a small "Also related, through other items" list on an item's Connections tab) — that list is removed once this screen ships. Built on Kuzu (TAD §3.1); reuses Cytoscape.js (already locked, Section 12) for the graph canvas rather than introducing a second graph-rendering library.

**Entry points:** a "Relationship Graph" button on the Connection flowchart screen (Section 12) top bar, and a "View in Relationship Graph" link from any item's detail page.

**Layout:** full-page canvas, similar framing to the flowchart screen, plus a left-hand panel:
- **Left panel:**
  - A search/select box to pick a starting item (defaults to whatever item the user arrived from).
  - **"Reachable within"** control — a small stepper for N links (default 2).
  - **"Confirmed links only"** toggle — when on, unconfirmed guessed links are excluded from every calculation on this screen, not just hidden visually.
  - **Shortest path finder** — pick a second item; the panel shows the chain between them, listing the matching column on each link in the chain.
  - **Connected groups** — a list of the graph's connected clusters, each labeled with its item count; a cluster spanning more than one database connection is marked "crosses connections."
- **Canvas (right):** the selected item's neighborhood (within the chosen N), confirmed links solid, guessed links dashed (same visual language as Section 12). The active shortest path, if one is being shown, is highlighted along its edges. Most-connected items are shown with a slightly larger node.
- Clicking any node navigates to that item's detail page, same as the flowchart screen.

**States:** if the graph is unavailable (e.g. running on a Python version Kuzu doesn't support — TAD §3.1), the screen shows a plain message explaining why, with a link back to the regular Connection flowchart (which still works normally) — not an error.

**Acceptance check:** neighborhood, shortest-path, and connected-groups views all match the underlying graph; the "confirmed only" toggle changes the actual results, not just the drawing; the unavailable state shows a plain explanation rather than an error; clicking a node navigates correctly.

---

## 13. Screen: Settings

Simple sectioned settings page (left mini-nav within the page, or accordion):
- **AI configuration** — choose Ollama or external API; fields are **endpoint URL**, **model name**, and **API key** (key required for external, optional for Ollama); "test connection" button; privacy warning shown when external API is selected (TAD §7.2 locked wording). **Phase 3 ships this section only.**
- **Connections management** — list/edit/delete existing connections (links back to Section 5's flow for editing). Later phase.
- **Notification channels** — email/Slack/Teams/webhook setup used by alerts and automations. Later phase.
- **Appearance** — light mode (default) / dark mode toggle (if built; otherwise marked "coming soon"). Later phase.
- **About** — version, license (Apache-2.0), links. Later phase.

The AI **chat drawer** (Section 11.3) is Phase 7; Phase 3 only needs Settings AI config plus the Statistics-tab query box states (unconfigured / privacy warning / configured).

**Acceptance check:** every setting persists (saved to Tarsier's own SQLite storage, per TAD Section 5) and is reflected immediately where used (e.g. a saved AI config enables the AI panel without a restart).

---

## 14. Shared components reference

| Component | Token base | Used in |
|---|---|---|
| `button-primary-pill` | v2 — `accent-cta` fill, `radius-pill`, hover → `accent-interactive` | Primary actions everywhere (replaces the old rounded-rectangle primary button) |
| `button-secondary-ghost` | v2 — transparent/outline fill, `radius-sm` (5px), hover → `accent-interactive` border/text | Secondary actions |
| `text-input` | v2 — `radius-xs` (3px), `hairline` border, focus ring in `accent-interactive` | All forms |
| `card-feature` | v2 — `canvas-soft` fill, `radius-lg` (12px), no drop shadow (color-based depth only) | Welcome cards, connection-type cards |
| `card-feature-row` | v2 — `canvas-soft` fill, `radius-md` (6px) | Automation nodes, alert rows |
| Status badge (new) | Uses `status-good/warning/danger/info/neutral` | Health scores, check results, alert status |
| Stat card (new) | `stat-xl` numeral + `caption` label | Overview headline stats |
| Data table (new) | `body-md` cells, `caption` headers, `canvas-soft` alternating rows, `hairline` borders | Layer lists, statistics, change feeds |
| Map preview (new) | MapLibre, `radius-md` container, `hairline` border | Overview thumbnails, layer detail, quality "show on map" |
| AI chat bubble (new) | `ai-accent` (magenta) accent border | AI panel |
| Flowchart node (new) | `card-feature-row` base + type corner badge | Connection flowchart |
| Staged Review Card (new) | `ai-accent` (magenta) accent border (AI-sourced), modal overlay, `radius-lg` | Section 18 — AI-drafted custom rules and automations before save |

**Note (2026-10-13):** the AI-related accent moved from the old violet (`surface-violet-soft`) to `ai-accent` (magenta), to match the v2 palette. Every component above that was "AI-sourced" uses `ai-accent` now, in both light and dark mode.

**Acceptance check:** no component outside this list is introduced without being added here first; colors used always trace back to Section 2's token list.

---

## 15. States every screen must handle

Every data-bearing screen (Overview, Detail, Statistics, Quality, Changes, Alerts, Automations, Flowchart) must explicitly design for:
- **Loading** — skeleton placeholders, not blank screens or spinners alone.
- **Empty** — clear explanation + next action (e.g. "No quality checks run yet — Run now").
- **Error** — plain-language error (no raw stack traces), with a retry action where applicable.
- **Populated** — the normal designed state (described above per screen).
- **Partial/degraded** — specifically for tiered features (e.g. a file connection's History tab shows "Not available for this connection type," not an empty table).

**Acceptance check:** each screen has all applicable states implemented and reviewable, not just the happy path.

---

## 16. Accessibility & responsiveness

- Desktop only (no mobile layout in v1, per PRD).
- Minimum supported width: 1280px. Below that, horizontal scroll is acceptable for dense tables; the app is not optimized narrower.
- Buttons and interactive elements meet a minimum 40×40px hit target.
- Color is never the only signal for status — every status badge includes a text label, not just a color.
- Keyboard navigation for forms and the automation builder's node palette (drag-and-drop must have a keyboard-accessible alternative, e.g. "Add node" menu).

**Acceptance check:** app is usable and legible at 1280px width; every status indicator has a text label; core flows (add connection, build automation, run a check) are completable via keyboard.

---

## 17. Open items for later documents

- Exact chart types/specs for statistics, histograms, change-volume graphs → **DVS**.
- Feature-to-test mapping for these screens → **FTL**.
- Dark mode is **in v1** now (Section 2, both modes specified) — no longer a later item.

---

## 18. Staged Review Card (AI review-gate)

**Added:** 2026-10-13, Manager + user decision, post-v1.0 addition. **Purpose:** before anything AI drafts gets permanently saved and able to run on its own later (a custom quality rule, an automation), the user must see exactly what it will do and explicitly approve it. This does **not** apply to one-off AI answers that don't get saved (see Section 11.3) — only to the two things AI can produce that persist and act without the user watching: a custom rule (Section 9) and an automation (Section 11.2).

**Trigger:** the "help build an automation" AI job (PRD §7.7 job 4) finishes, or the AI panel drafts a custom quality rule. Instead of saving directly, Tarsier opens this card.

**Layout:** a modal, centered, `ai-accent` (magenta) accent border, `radius-lg` (marks it as AI-sourced, consistent with the AI panel's visual language):
1. **Header** — "Review before saving" (`display-md`), with a small AI icon and a one-line note: "Tarsier never saves or runs anything from AI without your approval."
2. **Plain-English summary** — one or two sentences describing what this will do, in the AI's own words (e.g. "This automation checks every morning at 7am, and if more than 50 rows were deleted overnight, emails the team.").
3. **The actual thing, shown plainly:**
   - For a custom rule: the same field/operator/value form from Section 9's rules manager, pre-filled and editable — the user can tweak it right here before saving.
   - For an automation: the same trigger → condition → action node layout from Section 11.2, pre-built and editable on a small embedded canvas.
4. **Three actions:** **"Approve & save"** (`button-primary-pill`), **"Edit first"** (opens the full rules form or automation canvas with this draft loaded, no save yet), **"Discard"** (`button-secondary-ghost`, closes without saving).

**States:** loading (while AI drafts — skeleton card), populated (above), error (AI failed to produce a valid draft — plain message, "Try again" button, nothing saved).

**Acceptance check:** an AI-drafted custom rule or automation never reaches saved/active state without this card being approved; "Edit first" hands off to the normal manual editor with the draft pre-loaded; "Discard" leaves no trace (nothing partially saved); a manually-authored rule or automation (not AI-drafted) never shows this card — it saves exactly as it did before this section existed.

---

*End of FSD v1.0.*
