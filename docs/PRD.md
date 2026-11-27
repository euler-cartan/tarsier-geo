# Tarsier — Product Requirements Document (PRD)

**Version:** 1.0 (v1 scope)
**Status:** Approved for build
**Date:** 2026-10-10
**Package / repo name:** `tarsier-geo`
**License:** Apache-2.0
**Platform:** Desktop web app, on-premise (runs on the user's own server/computer)

---

## 0. How to use this document

**This is the source of truth for what Tarsier v1 must do.** Read it fully before building.

### For Claude Code (the builder)
- Build **step by step**, in the order given in **Section 10 (Build Order)**. Do not skip ahead.
- Finish one step fully, including its **"Done when"** check, before starting the next.
- **Do not assume the tech stack** (language, framework, libraries, how Tarsier stores its own data). Those decisions live in the **Technical Architecture Document (TAD)**, which comes after this PRD. If the TAD is not yet available, **stop and ask** before choosing a stack.
- After each step, report: what was built, how it meets the "Done when" check, and what is next.
- If anything in this PRD is unclear or seems to conflict, **ask before building** — do not guess.

### For the Manager (reviewer)
- Each feature in Sections 6–9 has **Acceptance checks**. Use them to verify shipped work matches the plan.
- Use Section 10's checkpoints to confirm each phase is truly complete before the next begins.

### Related documents (to be written after this PRD)
- **WFD** — Development & Operations Workflow
- **FSD** — Frontend Specification Document
- **TAD** — Technical Architecture Document (decides the stack)
- **FTL** — Feature Traceability List
- **DVS** — Interactive Data Visualization Specification

---

## 1. What Tarsier is

Tarsier is a tool that **watches geospatial databases and shows their full health, history, and quality on dashboards.** Think of it as a **health record for a database** — one place to see everything about the data: statistics, quality problems, and what changed, by whom, and when.

**Core promise:** a team can open Tarsier and instantly understand the state of their geospatial data — without writing code or SQL, and without being blind to silent changes or hidden errors.

**v1 is read-only.** Tarsier only watches and reports. It never changes the user's data. (Editing/fixing data is planned for a future version.)

---

## 2. Why we are building it (the problem)

Geospatial teams today face three main pains:

1. **Change blindness** — Data changes and nobody knows. Real example: at a utility company, someone deleted an entire area's features and the team had no idea who did it or when.
2. **Hidden quality errors** — Errors that normal GIS tools don't surface: broken shapes, topology problems, missing attribute/topology rules, out-of-range values, wrong projections.
3. **Statistics are hard to get** — To see basic numbers about the data, people must write custom scripts or SQL, or pull it into tools like PowerBI.

**What exists today:** Pieces of this exist separately — Esri's ArcGIS Data Reviewer (quality dashboards, Esri-only, paid), and raw PostGIS audit triggers (change tracking, but no friendly dashboard). **No single open-source tool combines change tracking + quality + easy statistics + AI, across vector, raster, and tabular data.** That gap is Tarsier's opportunity.

---

## 3. Who it is for

- **Users:** GIS, remote sensing, and geomatics teams in **government** and **large private companies**.
- **Serves both** the people managing the database (admins) and the people using the data (analysts).
- **One user role in v1.** No separate admin/viewer permissions yet. (Role separation may come later.)

---

## 4. Scope

### In scope (v1)
- Read-only monitoring dashboards for geospatial databases.
- Vector, raster, and tabular data.
- Features A–E, the automation builder, the connection flowchart, and the AI assistant (all detailed below).
- Desktop web app, running on-premise.

### Out of scope (v1 — explicitly NOT building now)
- **Editing or fixing data** (planned for a future version).
- **Change tracking for loose files** in folders (no snapshots — see Section 5).
- **Mobile / phone layout** (desktop only).
- **Multiple user roles / permissions.**

---

## 5. Connection types (tiered features)

Users connect Tarsier to wherever their data lives. **Different connection types support different features.** When a user picks a connection type, Tarsier must **clearly tell them upfront which features are not available for that choice** (e.g. "Change tracking is not available for file connections").

| Connection type | Change tracking (who/when) | Quality checks | Statistics |
|---|---|---|---|
| **PostGIS / PostgreSQL** | **Full** (Tarsier can set up tracking) | Yes | Yes |
| **Oracle Spatial** | Partial — depends on their setup | Yes | Yes |
| **SQL Server** | Partial — depends on their setup | Yes | Yes |
| **Files in folders** (shapefile, GeoPackage, GeoTIFF, CSV) | **None** (no snapshots) | Yes | Yes |
| **ArcGIS Enterprise** | Depends on what it exposes | Partial | Yes |
| **Geoserver** | Depends on what it exposes | Partial | Yes |

**Acceptance check (connections):**
- User can create a connection for each type above.
- Before/at connection time, unavailable features for that type are shown clearly.
- No feature silently fails — if it can't work for a connection, the UI says so.

---

## 6. Data types

Tarsier handles three kinds of data. Each shows different things.

### 6.1 Vector (points, lines, polygons)
Full treatment: overview, statistics, quality (including geometry/topology/projection), and change tracking (where the connection supports it). Attribute tables attached to vector layers are treated **as part of the vector layer** (not as separate tabular data).

### 6.2 Tabular (plain tables, no shapes)
- **Standalone tables in a database** and **loose CSV files**.
- Shows statistics and quality (minus anything geometry-related).
- Change tracking only when the table lives in a database (never for loose CSVs).
- CSVs may act as sources that connect to vector data (shown in the connection flowchart — see 7.8).

### 6.3 Raster (image grids — satellite, elevation, GeoTIFF)
- Full detail **only when the raster lives inside a database**.
- Shows overview + statistics + quality for remote sensing engineers.
- **No change tracking for raster** (rasters are replaced whole, not edited piece by piece).

**Acceptance check (data types):** Each layer/table/raster opens a detail page (see Section 8) appropriate to its type, showing only the sections that apply to it.

---

## 7. Features (all v1)

Every feature below is in v1. (During build, phases may be grouped — see Section 10 — but all are required for v1 to be "done.")

### 7.1 Feature A — Overview page
The main landing view for a whole database.

Must show:
- **Health score** — a single 0–100 number (red/yellow/green) for each layer and for the whole database.
- **Layer list** — for each layer: row/feature count, size, last changed, projection, whether it has an index, quality score.
- **Stale layers** — layers not touched in a long time (possibly abandoned).
- **Heavy layers** — the biggest / slowest layers.
- **Relationships** — which layers link to which (summary; full view in the flowchart, 7.8).
- **Projection overview** — which layers use which coordinate system (to spot mismatches).
- **Map preview / thumbnail** per layer.

**Acceptance check:** Opening a connected database shows all the above, accurate against the real data, with no SQL needed from the user.

### 7.2 Feature B — Statistics (engineer-level) + AI query
Per-column and per-layer numbers that reveal real problems.

Must show:
- Per column: minimum, maximum, average, count of empty values, count of unique values, most common values.
- **Messy categories** — values that are the same thing written differently ("Road", "road", "ROAD", "rd").
- **Out-of-range values** — e.g. negative pipe diameter, year = 9999.
- **Duplicates** — the same feature/row stored more than once.
- **Map outliers** — features located where they shouldn't be (a point in the ocean).
- **Null geometry** — rows that should have a shape but don't.
- **AI query box** — the user types a request in plain English ("show items with low stock") and the AI turns it into the correct query. **The user never writes SQL.**

**Acceptance check:** For a sample dataset, every statistic above is correct; the AI query box returns correct results for at least a set of private test questions (see the internal exam, Section 11).

### 7.3 Feature C — Quality checks (advanced)
Catches problems normal GIS tools miss.

Must check:
- **Geometry validity** — self-crossing polygons, broken shapes.
- **Topology** — gaps, overlaps, slivers (tiny leftover shapes), dangles (lines that don't connect).
- **Completeness** — missing features, missing attribute values.
- **Custom attribute rules** — rules the user defines (e.g. "diameter must be positive").
- **Projection check** — layer in the wrong coordinate system.
- **Boundary check** — features outside the area they should be in.
- **Consistency** — attribute value doesn't match the shape (label says "park" but shape is a road).

**Acceptance check:** Each check runs on demand, lists the specific features that failed, and the results match a known test dataset with planted errors.

### 7.4 Feature D — Change tracking
(Where the connection type supports it — see Section 5.)

Must provide:
- **Who / when / what** — every change recorded with user, time, and before → after values.
- **Single-feature history** — the full timeline of one feature.
- **Schema changes** — columns added or removed.
- **Mass-change detection** — large deletes or edits flagged (the utility-company case).
- **Compare two dates** — "what changed between Monday and Friday."
- **Auto change report** — a daily/weekly summary of changes.
- **Change-volume graph** — a trend line; sudden spikes stand out as suspicious.

**Acceptance check:** On a PostGIS test database, making a change (edit, delete, schema change) is captured with correct who/when/what; mass delete triggers the mass-change flag; compare-two-dates shows the correct differences.

### 7.5 Feature E — Alerts
Notify users when something important happens.

Must support alerts for:
- Mass delete / mass edit.
- Row count dropped suddenly.
- Schema changed.
- Layer not updated when expected (freshness).
- Quality score dropped.
- A specific user did something.
- New layer added / layer dropped.
- Size grew abnormally.
- A banned value appeared (e.g. negative number, bad projection).

**Acceptance check:** Each alert type can be set up and fires correctly when its condition is met, in a test scenario.

### 7.6 Automation builder ("when → if → do")
A simple visual, node-based workflow builder that lets users create their own rules without coding.

Pattern: **When [trigger] → if [condition] → do [action].**

- **Triggers:** on any change, on a schedule (e.g. every morning), on a threshold crossed, on a specific user's action, on a quality-check failure, on a new feature.
- **Conditions:** if user = X, if count drops more than Y%, if layer = Z, if value out of range.
- **Actions:** send email, send a message (Teams/Slack), call a webhook (ping another system), write to a log, run a quality check, ask the AI to summarize and send it.
- **Multi-step chains:** e.g. change happens → run quality check → if it fails → notify + log.
- **Templates:** ready-made recipes so users don't start from scratch.
- **AI action:** e.g. "every evening, summarize today's changes in plain English and email the team."

**Acceptance check:** A user can build a working automation from scratch and from a template; a multi-step chain runs end to end; the AI action produces and sends a plain-English summary.

### 7.7 AI assistant
Connects to **Ollama (local)** or **any API key** (user's choice). In v1 it does exactly four jobs:
1. **Plain-English → query** (powers the Feature B query box).
2. **Explain what changed today** in plain words.
3. **Explain a quality problem and suggest a fix.**
4. **Help build an automation** ("notify me when...").

**Acceptance check:** The assistant can be pointed at either Ollama or an API key; all four jobs work on test data; it never performs write actions on user data (read-only rule holds).

### 7.8 Connection flowchart
One interactive diagram of the whole database showing **what connects to what** (tables, vector layers, rasters, CSVs).

How connections are found — **Option D (mix):**
- **Official links** — connections the database formally declares (foreign keys). Shown as confirmed.
- **Smart guesses** — Tarsier compares columns (same name, same values, like "parcel_id" in two tables) and suggests likely connections, **clearly marked "guessed — please confirm."**
- **User-added** — the user can manually declare a connection (e.g. "this CSV joins this layer on this column").

**Cross-connection guessing (added 2026-10-13, Manager + user decision):** smart guesses are no longer limited to tables/layers within one connection — Tarsier also compares columns **across different connections** (e.g. a table in your PostGIS connection and a layer in your ArcGIS Enterprise connection), using the exact same name + value-overlap method already used within one connection (TAD's locked Connection-guess methodology). No geographic/location-based matching is used for this — only column names and value overlap, same as today. Cross-connection guesses are shown and confirmed/rejected the same way as any other guessed link.

**Acceptance check:** The flowchart renders all three kinds of links, visually distinguishes confirmed vs guessed, and lets the user confirm a guess or add their own. Guessed links are found both within a single connection and across different connections, using the same method either way.

### 7.9 Layer / table / raster detail page
Clicking the name of any layer, table, or raster opens a **dedicated detail page** for just that item, showing the sections relevant to its type (overview, statistics, quality, history where applicable).

**Acceptance check:** Every item has a working detail page; irrelevant sections are hidden (e.g. no topology section on a plain CSV; no change-tracking on a raster).

---

## 8. Raster detail (remote sensing)

When a raster lives in a database, its detail page shows:
- Pixel size (resolution / ground distance), width × height, number of bands, band names.
- Projection, area covered (footprint), acquisition date, sensor name (if stored).
- Per band: minimum, maximum, average, spread, histogram.
- Nodata (empty) value and how much of the image is empty.
- Bit depth / data type; whether overviews (fast previews) exist.
- Cloud cover % (if stored in metadata).

**Acceptance check:** For a test raster in a database, all available fields above display correctly; missing metadata is shown as "not available," not as an error.

---

## 9. Success criteria (validation)

Tarsier v1 is validated in **two stages:**

1. **Stage 1 — Internal exam.** We build our own test suite ("exam") with known datasets and planted errors. Tarsier must pass it — every feature's acceptance check must hold.
2. **Stage 2 — Real-user stress test.** GIS domain experts use Tarsier on real data and try to break it. Feedback is collected and addressed.

v1 is **not** considered shipped until Stage 1 fully passes.

---

## 10. Build order (step by step)

Build in this order. **Each step must pass its "Done when" check before the next step starts.** The exact stack is defined in the TAD — confirm the TAD exists before Phase 0.

### Phase 0 — Foundations
- **0.1 Confirm the stack** from the TAD. *Done when:* stack is chosen and written down; no assumptions made.
- **0.2 Project skeleton + repo** (Apache-2.0 license file, README, contribution + security rules). *Done when:* repo runs an empty app locally on-premise.

### Phase 1 — Connect and read (read-only core)
- **1.1 PostGIS / PostgreSQL connection.** *Done when:* Tarsier connects and lists layers/tables, read-only.
- **1.2 Tiered-feature notices** — show what's unavailable per connection type. *Done when:* picking a file connection clearly warns "no change tracking."
- **1.3 Other connections** — files, Oracle, SQL Server, ArcGIS Enterprise, Geoserver. *Done when:* each connects and lists its contents, with correct tier notices.

### Phase 2 — Overview + detail pages (Feature A + 7.9)
- **2.1 Database overview page** (health score, layer list, stale/heavy, projections, previews).
- **2.2 Detail page** per layer/table/raster, type-aware.
- *Done when:* a real database shows an accurate overview and every item opens a correct detail page.

### Phase 3 — Statistics + AI query (Feature B + AI job 1)
- **3.1 Statistics engine** (all stats in 7.2).
- **3.2 AI assistant wiring** (Ollama + API key).
- **3.3 Plain-English query box.**
- *Done when:* stats are correct on test data and the query box answers test questions correctly.

### Phase 4 — Quality checks (Feature C)
- Build each check in 7.3; list failing features.
- *Done when:* all checks match a planted-error test dataset.

### Phase 5 — Change tracking (Feature D)
- **5.1 PostGIS change capture** (who/when/what).
- **5.2 Single-feature history, schema-change detection, mass-change detection.**
- **5.3 Compare-two-dates + auto change report + change-volume graph.**
- *Done when:* all change-tracking acceptance checks pass on a PostGIS test DB.

### Phase 6 — Alerts (Feature E)
- Build each alert type in 7.5.
- *Done when:* each alert fires correctly in a test scenario.

### Phase 7 — Automation builder (7.6) + remaining AI jobs (7.7 jobs 2–4)
- **7.1 "When → if → do" builder** with triggers, conditions, actions, chains, templates.
- **7.2 AI actions** — explain today's changes, explain a quality problem + fix, help build an automation.
- *Done when:* a user can build and run an automation (from scratch and template), and all four AI jobs work.

### Phase 8 — Connection flowchart (7.8)
- Official links + guessed links (marked) + user-added links, interactive.
- *Done when:* all three link kinds render and the user can confirm/add links.

### Phase 9 — Validation
- **9.1 Run the internal exam (Stage 1).** Fix until it fully passes.
- **9.2 Real-user stress test (Stage 2).** Collect and address feedback.
- *Done when:* Stage 1 passes completely; Stage 2 feedback is logged.

**Manager checkpoints:** After every phase, the manager verifies the phase's "Done when" checks and the relevant Acceptance checks from Sections 6–9 before approving the next phase.

---

## 11. The internal exam (Stage 1 detail)

Before real users, Tarsier must pass an internal test suite we build. It should include, at minimum:
- Test datasets for vector, raster (in DB), tabular (DB table + CSV).
- A dataset with **planted errors** (bad geometry, topology gaps/overlaps/slivers, nulls, out-of-range values, wrong projection, duplicates) to test Feature C.
- A **PostGIS test database** where we make edits, deletes, mass deletes, and schema changes to test Feature D.
- A set of **plain-English questions** with known correct answers to test the AI query box. For TRS-025, the assistant answers a set of known test questions correctly against planted data. The exact exam questions are kept private.
- Alert and automation **scenarios** with known expected outcomes.

Each feature's Acceptance check (Sections 6–9) maps to exam items. (The full mapping lives in the FTL.)

---

## 12. License, security & contribution

- **License:** Apache-2.0 — wide adoption, plus patent and brand protection for the company. No plans to monetize in v1; paid services remain possible later without changing the license.
- **Open-source project:** Tarsier is community-built on GitHub.
- **Security & contribution rules** (to be detailed in the WFD): because v1 is read-only and runs on sensitive government/corporate data, contributors must follow clear cybersecurity and coding standards. No contribution may add write-access to user data in v1.

---

## 13. Open decisions (to resolve in later documents)

These are intentionally **not** decided here. Do not assume them.
- Full tech stack (language, framework, how Tarsier stores its own metadata, how it talks to each database) → **TAD**.
- Exact screen layouts and visual design → **FSD**.
- Chart/visualization specifications → **DVS**.
- Dev/ops process, CI, release, security rules → **WFD**.
- Feature-to-test mapping → **FTL**.

---

## 14. Approved post-v1.0 additions (2026-10-13)

These features were decided by the Manager and the project owner on 2026-10-13, after v1.0 build was already underway (all of Phases 0–8 had code written, Phase 9 validation had not yet started). They are **approved to build now, alongside finishing Phase 9**, not held back for a separate release. Each was decided through a plain-language trade-off discussion; the stack choices are also recorded in TAD.md, and the AI review screen is also recorded in FSD.md §18.

- **14.1 Spatial Knowledge Graph Engine** — a richer model of how layers/tables/sources relate to each other, beyond the existing flowchart's simple links. Built on **Kuzu** (TAD §3), embedded, no separate program, no Docker. Kuzu's maintainers archived the project on 2025-10-10 (no further upstream updates) — this risk was explicitly discussed and accepted; version is pinned (TAD §3).
- **14.2 Hybrid Spatial-Semantic AI Search / Analytics Accelerator** — faster number-crunching and smarter search, built on **DuckDB** (TAD §3), embedded, no separate program, no Docker. Runs against GeoParquet snapshots (14.3), never against the user's live source database.
- **14.3 GeoParquet Snapshot Versioning** — Tarsier takes a snapshot of each database's data **every 2 days**, keeps snapshots for **90 days** then auto-deletes older ones, and stores them in Tarsier's normal data folder (same place as everything else — no separate drive setup). Used for date-to-date comparison without querying the live source database, and as the data DuckDB (14.2) reads from.
- **14.4 Automated Spatial Schema-Drift & CDC Monitoring** — strengthens the existing schema-change detection (Feature D) and projection check (Feature C); not a new capability, an enhancement to ones already in v1.0 scope.
- **14.5 Zero-Trust Local Execution Guardrails** — reaffirms existing v1.0 rules (read-only on user data, AI never gets a live connection, no telemetry); not new, a restatement already covered by TAD §9.
- **14.6 "Show me what ran" transparency** — already covered by the existing AI query box design (FSD §8, TAD §7.2); not new.
- **14.7 Review-gated AI workflows ("Staged Review Card")** — AI-drafted custom quality rules and AI-drafted automations must be reviewed and explicitly approved by a human before they are saved and able to run on their own; full design in FSD §18. Does **not** apply to simple AI answers that aren't saved (e.g. the plain-English query box, "explain today's changes").
- **14.8 Command palette** — a keyboard-triggered quick-jump search for navigating between screens and finding a specific layer/table/raster by name. **Navigation only in v1** — it does not run actions (e.g. it will not "run a quality check" or "create an alert" from the palette itself).
- **14.9 Encrypted credential vault & backup/restore CLI** — new `tarsier backup PATH` and `tarsier restore PATH` commands. Secrets (database passwords, AI keys) are stored securely already (TAD §9, `keyring` + Fernet fallback); backups **leave secrets out by default** — restoring from a backup requires re-entering database passwords and AI keys. (Matches the `--include-key`-style opt-in pattern other local-first tools use, but the opt-in version is not yet scoped — out of scope for now, can be added later if asked for.)
- **14.10 Cross-connection relationship guessing** — extends 7.8's "smart guesses" to also compare across different connections, not just within one. Full detail in 7.8 above.

**Not approved / explicitly deferred:** a full, separately-running graph database program (as opposed to Kuzu's embedded approach) was discussed and intentionally **not** chosen, specifically because Tarsier's government users often cannot get approval for new always-running background software, Docker or not. If real usage later proves Kuzu's embedded approach isn't enough, revisit this as a clearly separate future decision — do not add it quietly.

---

*End of PRD v1.0.*
