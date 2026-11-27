# Tarsier — Interactive Data Visualization Specification (DVS)

**Version:** 1.0 (v1 scope)
**Status:** Approved for build
**Date:** 2026-10-10
**Companion to:** PRD v1.0, TAD v1.0, FSD v1.0

---

## 0. How to use this document

### For Claude Code (the builder)
- This document is the **single source of truth for every chart, graph, and visualization** in Tarsier. Do not invent a chart type, color, or interaction not specified here.
- Every visualization follows the **update model in Section 1** — no exceptions, no separate polling/websocket logic needed.
- Use **MapLibre** for all map visualizations (locked in TAD). Use **one charting library for everything else** — see Section 2.
- Each chart section includes **states** (loading / empty / error / populated) — build all of them, not just the populated state.

### For the Manager (reviewer)
- Each chart has an **Acceptance check**. Verify against it once built.

---

## 1. The update model (applies to every chart in this document)

Tarsier's visualizations are **not** timer-based auto-refresh and **not** live-streaming (websockets). They are **run-triggered updates**:

> **When a check, query, or scheduled job finishes running — on this machine, right now, or earlier on a schedule — every visualization that depends on that result updates immediately, without a page reload.**

This applies whether the run was:
- Started manually by the user ("Run full check," "Run now," "Test run" in the automation builder), or
- Completed by a background scheduled job (APScheduler, per TAD Section 7.1) while the user is looking at the screen.

**How it works technically (for the builder):**
- Each chart subscribes to the **result of a specific job type** (e.g. "quality check results for layer X," "statistics for layer X," "change feed for database Y").
- When that job completes, the frontend receives the new result (via the existing API — a short poll **only** while a run is in progress is acceptable, not continuous) and the chart **re-renders with a smooth transition**, not a hard flash.
- If the user is on a screen whose data just updated from a **background scheduled job** (not one they triggered), show a small non-intrusive **"Updated just now"** badge near the chart, so they know it refreshed without assuming they'll notice silently.

**Acceptance check (applies globally):** triggering any run updates its dependent charts without a manual page reload; a chart never changes data outside of a completed run; a background-triggered update shows the "Updated just now" badge.

---

## 2. Charting approach

- **Charting library:** a single, open-source, React-friendly library used for **all** non-map charts, for visual consistency. Recommended: **Recharts** (or **Observable Plot** as an alternative) — both are lightweight, work fully offline (bundled, no external calls), and fit React cleanly. **Lock: Recharts.**
- **Maps:** MapLibre for everything spatial (previews, outlier highlighting, flowchart's map elements if any).
- **Color source:** all chart colors come from the **DVS palette in Section 3** — derived from the FSD's design tokens, never ad hoc.
- **Motion:** chart updates animate over ~300ms (value transitions, bar height changes) — confirms "it just updated" without being distracting. No animation longer than 500ms.

---

## 3. Visualization color palette

Reusing FSD tokens, applied consistently across all charts:

| Purpose | Token | Hex |
|---|---|---|
| Good / healthy / passed | `status-good` | `#0e3030` |
| Warning / nearing issue | `status-warning` | `#b8860b` |
| Danger / failed / critical | `status-danger` | `#b3261e` |
| Neutral data series (primary) | `primary` | `#1b1938` |
| Neutral data series (secondary) | `surface-teal-mid` | `#155555` |
| AI-related overlays | `surface-violet-soft` | `#c9b4fa` |
| Gridlines / axes | `hairline` | `#e8e4dd` |
| Muted / no-data | `ink-faint` | `#9a9794` |

**Rule:** status colors (good/warning/danger) are reserved **only** for meaning "this is good/warning/bad." Never used decoratively. Neutral series use `primary` and `surface-teal-mid` only.

---

## 4. Chart 1 — Health score (ring gauge)

**Where used:** Overview page headline stat (database-wide), layer list rows (small version), layer detail header (large version).

**Type:** **Circular ring gauge** (donut-style progress ring), 0–100.
- Ring color: `status-good` (score ≥ 80), `status-warning` (score 50–79), `status-danger` (score < 50).
- Center: the number itself at 30px / weight 600 (not `stat-xl`).
- Two sizes: **large** (Overview headline, detail header — 96px diameter) and **small** (layer list row — 28px diameter, number-only label beside it, no ring needed at that size — just a colored dot + number).

**Interaction:** hovering the large ring shows a tooltip breaking down the score's contributing factors (e.g. "Quality: 90, Freshness: 70, Completeness: 95").

**Health-score calculation (locked by the Manager):** combine the available 0–100 components with a weighted average: Quality **40%**, Freshness **30%**, Completeness **30%**. Exclude unavailable components and renormalize the remaining weights; if all three are unavailable, show the documented empty state instead of a number.

- **Quality:** percentage of completed, applicable quality checks with status `good`. `warning` and `danger` count as not good; `never_run` and `not_applicable` checks are excluded. This component includes the completeness check's pass/fail result.
- **Freshness:** score 100 at 30 days old or newer; decline linearly from 100 at day 30 to 0 at day 90; score 0 at 90 days or older. If no usable update timestamp is available, exclude this component.
- **Freshness timestamp:** use the source metadata `last_modified` timestamp first; if it is unavailable, use the latest recorded real change event. Never use scan time as a proxy. If neither timestamp exists, Freshness is unavailable.
- **Completeness:** for a supported sequence-style integer ID column, distinct observed IDs divided by the expected inclusive ID range from minimum to maximum, expressed as a percentage. This is the ID-sequence ratio only; it is not another quality-check pass rate. If no supported ID sequence is available, exclude this component.
- **Database-wide score:** arithmetic mean of the available per-layer composite scores. Layers with no composite score are excluded; if no layer has a score, show no database score.
- **Database tooltip:** show the arithmetic mean of each available component across layers that have that component, labeled as a component average. Show the small caption **“Component averages across layers”** beneath the database ring. These averages explain the data contributing across layers and may not recombine to the database-wide score when component availability differs; the ring score remains the mean of per-layer composite scores.

**Update behavior:** updates after any check that contributes to the score completes (quality check, freshness check).

**States:** loading = grey ring, pulsing. Empty (never checked) = grey ring with "–" in center and a "Run first check" micro-link below.

**Acceptance check:** ring color always matches the documented thresholds; hover tooltip shows the correct breakdown; updates immediately after a relevant run.

---

## 5. Chart 2 — Change-volume graph

**Where used:** global Changes screen (top), layer detail History tab.

**Type:** **Bar chart**, one bar per day (switchable to per-hour for a selected single day).
- X-axis: date/time, `caption` typography, gridlines in `hairline`.
- Y-axis: number of changes, start at 0, auto-scaled.
- Bar color: `primary` for normal volume.
- **Spike highlighting:** any bar that is a statistical outlier vs. the recent trend (e.g. more than 3× the 7-day average) is colored `status-danger` instead of `primary`, and gets a small marker dot above it.

**Interaction:**
- **Zoom:** click-drag to select a date range, zooms in; "Reset zoom" button appears when zoomed.
- **Hover:** tooltip shows exact count, date, and a one-line breakdown by change type (added/edited/deleted).
- **Click a bar:** jumps to the change feed (Section "Change feed" below) filtered to that day.
- **Range presets:** quick buttons — 7 days / 30 days / 90 days / custom.

**Update behavior:** redraws when the change-tracking job completes (trigger capture or polling cycle) or when the user runs "compare two dates."

**States:** loading = skeleton bars. Empty (no changes in range, or no tracking on this connection) = flat baseline with caption "No changes recorded in this range" (or "Change tracking not available for this connection type" where applicable, per FSD Section 15).

**Acceptance check:** spikes are correctly colored and marked; zoom and range presets work; clicking a bar filters the change feed correctly; empty/no-tracking states are distinct and correctly worded.

---

## 6. Chart 3 — Change feed (list, not a chart, but DVS-governed for consistency)

**Where used:** below the change-volume graph.

**Type:** reverse-chronological **list**, not a chart, but styled consistently: each row shows a small colored dot (added = `status-good`, edited = `primary`, deleted = `status-danger`), user, timestamp, layer, and a one-line before→after summary.

**Interaction:** filter bar above (user, layer, date range, change type); clicking a row opens the single-feature history timeline (Section 9).

**Update behavior:** new rows appear at the top immediately when a tracked change is captured or a polling cycle completes, with a brief highlight animation on new rows (fades after ~2 seconds).

**Acceptance check:** color-coding matches change type consistently with the bar chart above; new entries animate in in real time following a completed capture/poll.

---

## 7. Chart 4 — Per-column statistics (mini visualizations in the stats table)

**Where used:** Statistics tab, per-column row.

**Type:** compact **horizontal bar** inline in the table row showing: % empty (as a filled portion of a thin bar, `status-warning` if empty share is **20% or above**, else `ink-faint`), and a small **top-values bar list** (top 5 values, each as a thin horizontal bar sized by frequency, `primary` color) shown in an expandable row.

**Interaction:** clicking a column row expands it to show: full top-values bar list, a histogram (numeric columns) or value-frequency bars (text columns).

**Numeric column histogram:** standard **bar histogram**, **always 15 bins** (flat rule, not range-dependent), X-axis = value range, Y-axis = count. Min/max/average marked as thin vertical reference lines (`status-info` dashed).

**Update behavior:** updates when statistics are (re)computed for that layer (on-demand run or scheduled run), including when a sampled run is replaced by a full run (see Section 12).

**States:** loading = shimmer bar. Empty/no data = flat grey bar with "No values."

**Acceptance check:** histogram bins and reference lines are mathematically correct against the underlying data; expandable rows work; sampled vs full results are visually labeled (Section 12).

---

## 8. Chart 5 — Quality check results (per-check status + failing-feature breakdown)

**Where used:** Quality tab.

**Type:** **Horizontal stacked bar** per check type — one bar segmented into "passed" (`status-good`) and "failed" (`status-danger`) portions, with the failed-count as a label at the bar's end.

**Interaction:** clicking a check's bar expands the failing-features table (per FSD Section 9) below it, with a "show on map" action that highlights those features in a MapLibre preview panel (points/polygons styled in `status-danger` outline).

**Update behavior:** a check's bar updates the moment that specific check finishes running — checks can complete independently (e.g. topology finishes before completeness), so each bar updates on its own, not only when the whole suite finishes.

**States:** loading (bar still running) = animated indeterminate stripe in `ink-faint`. Not yet run = full `ink-faint` bar with "Not yet run" label and a "Run now" button.

**Acceptance check:** each check bar updates independently as its own run completes; map highlighting shows exactly the failing features; never-run state is visually distinct from a passing (all-good) state.

---

## 9. Chart 6 — Single-feature history (timeline)

**Where used:** opened from a map click, a change-feed row, or a table row.

**Type:** **Vertical timeline** — one entry per change to this specific feature, newest at top. Each entry: colored dot (same scheme as the change feed), timestamp, user, and an expandable before→after value diff (changed fields highlighted: old value struck through in `ink-faint`, new value in `ink`).

**Interaction:** expand/collapse each entry; "Compare to another version" lets the user pick two points on the timeline to diff directly.

**Update behavior:** a new entry animates onto the top of the timeline immediately if a new change to this exact feature is captured while the panel is open.

**Acceptance check:** diff correctly highlights only the fields that changed; compare-two-versions works for any two points on the timeline.

---

## 10. Chart 7 — Raster per-band histogram

**Where used:** Raster item detail page.

**Type:** **Bar histogram** of pixel values for the selected band. X-axis: pixel value range. Y-axis: pixel count (log scale toggle available, since raster histograms are often heavily skewed). Min/max/mean marked as dashed reference lines.

**Interaction:** a **band selector** (tabs or dropdown) switches which band's histogram is shown; switching re-renders the chart with the ~300ms transition.

**Update behavior:** updates when raster statistics are (re)computed for that item.

**States:** loading = shimmer. No bands / unreadable raster = clear error state, not a blank chart.

**Acceptance check:** histogram matches the band's true value distribution; log-scale toggle works; band switch updates correctly.

---

## 11. Chart 8 — Projection overview (Overview page)

**Where used:** Overview page, "Projection overview" card.

**Type:** **Horizontal grouped bar** — one bar per coordinate system found in the database, length = number of layers using it. The **expected/majority projection** is colored `primary`; any **minority/mismatched** projection is colored `status-warning`, with a small warning icon.

**Interaction:** clicking a bar filters the Overview's layer list table to just those layers.

**Update behavior:** updates when the overview/metadata scan completes (on connection refresh or scheduled scan).

**Acceptance check:** mismatched projections are visually flagged; clicking a bar correctly filters the layer list.

---

## 12. Sampled vs. full-run labeling (applies to Charts 4, 5, 7, and any stat-derived chart)

Per TAD Section 8 (performance), large layers may be summarized by **sample** rather than a full scan.

**Every chart whose data could come from a sample must:**
- Show a small `caption`-styled tag: **"Based on a sample (≈10% of rows)"** near the chart title, using `ink-mute` text with a `hairline` background pill.
- Offer a **"Run full check"** action next to the tag.
- When a full run completes, the tag disappears and the chart updates per the Section 1 model, with a brief **"Now showing full data"** confirmation that fades after a few seconds.

**Acceptance check:** every applicable chart shows the sample tag when relevant, removes it correctly after a full run, and the full-run action is always reachable from the chart itself.

---

## 13. Connection flowchart diagram (Feature 7.8 — graph visualization)

**Where used:** full-page Flowchart screen (FSD Section 12).

**Type:** **force-directed / hierarchical node-link graph** (not a traditional chart — a dedicated graph-layout render, pan/zoom canvas).
- Nodes: one per table/layer/raster/CSV, colored corner badge by type (vector = `primary`, raster = `surface-teal-mid`, tabular = `ink-mute`).
- Edges: solid = confirmed link, dashed = guessed link (with a "?" badge), solid + small user icon = user-added link.
- Node size can optionally scale slightly by row count (larger node = bigger dataset) — subtle, not dramatic, so the graph stays readable.

**Interaction:** pan/zoom, drag nodes to rearrange (layout persists per user session), click a node to open its detail page, click a dashed edge to confirm/reject, "Add connection" button to manually link two nodes.

**Update behavior:** updates when the connection-discovery scan completes (on-demand or scheduled) — new guessed links appear with a brief highlight animation; confirming/rejecting a link updates its edge style immediately (no scan needed for that action).

**States:** loading = skeleton nodes in fixed grid. Empty (nothing connected yet) = guidance message "No connections found yet — run a scan or add one manually."

**Acceptance check:** all three edge types render distinctly; confirm/reject and manual-add work without a full rescan; node click navigates correctly; layout persists during a session.

---

## 14. Automation builder canvas (Feature 7.6 — not a data chart, but a visualization surface)

**Where used:** Automation builder screen (FSD Section 11.2).

Governed here for visual consistency only (the interaction logic is in the FSD):
- **Canvas background:** `canvas-soft`, dotted grid pattern in `hairline` for alignment guidance.
- **Nodes:** rounded cards per FSD's `card-feature-row`, with a colored left accent bar by node type — trigger = `primary`, condition = `status-warning`, action = `status-good`.
- **Connecting lines:** curved bezier lines in `ink-faint`, becoming `primary` when hovered/selected.
- **Test-run visualization:** when "Test run" executes, the flow animates left-to-right — each node briefly highlights (`surface-violet-soft` glow, since it's an AI/automation-adjacent action) as the simulated run reaches it, finishing with a pass/fail badge on the final action node.

**Acceptance check:** node accent colors match type consistently; test-run animation visually traces the executed path in order; connecting lines highlight correctly on selection.

---

## 15. Empty, loading, and error states — global chart rules

Every chart in this document must implement, at minimum:

| State | Rule |
|---|---|
| **Loading** | Skeleton/shimmer shaped like the eventual chart — never a blank area or a generic spinner alone. |
| **Empty (no data yet)** | Plain-language message + a direct action to generate the data (e.g. "Run now"). Never an empty chart with no explanation. |
| **Not applicable (tiered feature)** | Clearly worded "Not available for this connection type" message, styled with `ink-faint`, not an error color — this is expected behavior, not a failure. |
| **Error** | Plain-language error message in `status-danger` text (no raw technical errors), with a retry action. |
| **Populated** | As specified per chart above, always following the Section 1 update model. |

**Acceptance check:** every chart in this document has all five states implemented and distinguishable from one another.

---

## 16. Open items for later documents

- Exact test scenarios proving each chart's correctness against known data → **FTL**.
- Dev/ops concerns (how chart-data jobs are scheduled, retried, logged) → **WFD**.

---

*End of DVS v1.0.*
