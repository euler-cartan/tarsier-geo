# Tarsier — Technical Architecture Document (TAD)

**Version:** 1.0 (v1 scope)
**Status:** Approved for build
**Date:** 2026-10-10
**Companion to:** PRD v1.0
**Package / repo name:** `tarsier-geo`
**License:** Apache-2.0

---

## 0. How to use this document

**This document decides HOW Tarsier is built.** The PRD decides *what* and *in what order*; this TAD decides the stack, structure, and technical rules. Read both before building.

### For Claude Code (the builder)
- Follow the **PRD's Build Order (Section 10 of the PRD)** for *sequence*. Use **this TAD** for *how* to build each part.
- Use **only** the technologies locked in this document. If something needed is not covered here, **stop and ask** — do not pick a tool on your own.
- Respect every rule in **Section 9 (Security)** and **Section 8 (Performance)** — these are not optional.
- Tarsier is **read-only on user data** in v1. The only exception is the one-time, optional change-tracking trigger install (Section 6), which requires explicit user permission.
- After each build step, report: what was built, which TAD section it follows, and how it meets the PRD "Done when" check.

### For the Manager (reviewer)
- Each section has **Acceptance checks**. Use them to confirm the build matches this architecture.

---

## 1. Architecture at a glance

Tarsier is a **single-machine, on-premise web application**, installed with `pip` and used in a browser.

```
  ┌───────────────────────────────────────────────┐
  │                 User's machine                 │
  │                                                │
  │   Browser  ──►  Tarsier local web server       │
  │   (React UI)      (FastAPI, Python)            │
  │                      │                         │
  │        ┌─────────────┼───────────────┐         │
  │        ▼             ▼               ▼         │
  │   Tarsier's own   Background      Connectors    │
  │   storage         scheduler       to data       │
  │   (SQLite)        (APScheduler)   sources        │
  │                                      │           │
  └──────────────────────────────────────┼──────────┘
                                          ▼
                 User's data: PostGIS / Postgres / Oracle /
                 SQL Server / files / ArcGIS Enterprise / Geoserver
                 (read-only)              │
                                          ▼
                 AI: Ollama (local, offline) OR external API (internet)
```

- The **React UI is pre-built and bundled inside the Python package**, so one `pip install` delivers everything and the app works offline.
- The server reads the user's data sources **read-only** and stores its *own* results, logs, rules, and settings in a local **SQLite** file.
- Background jobs (alerts, scheduled checks, polling, automations) run inside the app via **APScheduler**.
- AI is optional and user-configured (local Ollama or an external API).

**Acceptance check:** A fresh `pip install tarsier-geo` on Linux, Windows, and macOS produces a working app with no extra software to install (no Docker, no separate frontend build, no separate database server).

---

## 2. Install, start, and stop

### 2.1 Install
- Published on **PyPI** as `tarsier-geo`.
- **Minimum Python: 3.11.**
- Installed with `pip install tarsier-geo`. No Docker. Works on **Linux, Windows, macOS**.
- Intended installer: a **technical user** (GIS admin or developer) comfortable with Python and the terminal.

### 2.2 Start
- Command: `tarsier-geo start`.
- On start, Tarsier:
  1. Tries its **default port**.
  2. If that port is busy, **automatically finds the next free port**.
  3. **Prints the real URL** in the terminal (e.g. `Tarsier is running at http://localhost:8731`).
  4. **Automatically opens the browser** to that URL.
- Power users may force a port: `tarsier-geo start --port 8050`.

### 2.3 Stop
- Command: `tarsier-geo stop` (or closing the terminal process).

**Acceptance check:** With the default port occupied, `tarsier-geo start` still launches on a free port, prints the correct URL, and opens the browser. `--port` override works. `tarsier-geo stop` shuts it down cleanly.

---

## 3. Technology stack (locked)

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.11+** | Backend + CLI |
| Backend framework | **FastAPI** | Serves API + the bundled UI |
| Frontend | **React + TypeScript** | Pre-built, bundled in the package |
| Maps | **MapLibre** | Previews, outliers, flowchart map elements |
| Charts (non-map) | **Recharts** | Locked in DVS §2 |
| Tarsier's own storage | **SQLite** | Single file, zero setup, offline |
| Background jobs | **APScheduler** | In-process scheduler |
| Parquet snapshot serialization | **PyArrow** (`pyarrow>=20`) | Apache-2.0 licensed; supports complete Parquet/GeoParquet snapshots (PRD §14.3); complements DuckDB analytics |
| Backend tests | **pytest** | |
| Frontend tests | **Vitest + React Testing Library** | |
| Python packaging backend | **Hatchling** | Confirmed with Manager during Phase 0 (TAD didn't lock a backend) |
| Frontend build tool | **Vite** | Confirmed with Manager during Phase 0 (TAD didn't lock a build tool) |
| Secrets storage | **`keyring`** (primary) + **`cryptography`** (Fernet, encrypt-at-rest fallback for headless/no-OS-keystore environments) | Fills the Section 9 requirement ("OS secure storage where available, otherwise encrypt at rest"); chosen during Phase 1.1 since the TAD named the requirement but not a library |
| Frontend routing | **React Router** | Chosen Phase 2 — TAD didn't lock a router; the overwhelming standard for a React SPA, no real competing choice at this project's scale |
| Connection flowchart | **Cytoscape.js** | MIT-licensed graph visualization and layout library; bundled with the React frontend and used from a React effect. Its built-in layouts, pan/zoom, draggable nodes, and edge styling cover DVS §13 without runtime network calls or extra software installed by the user. Chosen for Phase 8 after comparing the requirements against React Flow: Cytoscape.js includes graph layouts, while React Flow would require a separate layout engine. |
| Analytics / search accelerator | **DuckDB** | Approved post-v1.0 addition (Manager + user decision, 2026-10-13) for the Spatial-Semantic AI Search and Analytics Accelerator features. Embedded — runs inside the Tarsier process, no separate server, no Docker. Used for fast read-only number-crunching and search against GeoParquet snapshots, never against the user's live source database directly. |
| Relationship / knowledge-graph storage | **Kuzu** (`pip install kuzu`, pin to **v0.11.3**) | Approved post-v1.0 addition (Manager + user decision, 2026-10-13) for the Spatial Knowledge Graph Engine feature. Embedded — runs inside the Tarsier process, no separate server, no Docker; this was the deciding factor over a full standalone graph database, because Tarsier's government customers often cannot get separately-running background software approved. MIT licensed — compatible with Tarsier's Apache-2.0 license (confirmed). **Known risk, accepted knowingly:** Kuzu was archived by its maintainers on 2025-10-10 and receives no further updates; v0.11.3 is the final release. Pin this exact version. If a bug surfaces in it later, Tarsier's own team must patch it (fork), since there is no upstream to report it to. Kuzu's optional extension-download server is also gone; do not rely on any Kuzu extension that fetches itself from Kuzu's own servers — only use what ships inside the pinned package. **Python-version policy (locked 2026-10-13):** Kuzu 0.11.3 has no wheel for Python 3.14 and never will (archived, no future release to add one). Tarsier's own requirement stays **Python 3.11+, uninterrupted** — it is pinned in the dependency file as `kuzu==0.11.3; python_version < "3.14"`. On Python 3.14+, Tarsier installs and runs normally; only the Spatial Knowledge Graph Engine reports itself unavailable (plain message in the UI, not an error) until Kuzu (or a replacement graph library) supports that Python version. This was chosen over capping Tarsier's whole Python requirement at ≤3.13, because excluding newer-Python users from the entire app is a bigger cost than one feature being unavailable to a subset of users. |

**Do not substitute** any of these without asking.

**Two infrastructure bugs found building Phase 2's screens, fixed at the framework level (not per-screen), so every future screen inherits the fix:**
- FastAPI's static-file mount only serves `index.html` for `/` and directory-style requests — a hard navigation or refresh on any client-side route (e.g. `/connections/{id}/overview`) returned a bare 404. `tarsier/web/serve.py` now falls back to `index.html` for any non-asset path that isn't a real file, the standard SPA-hosting pattern.
- MapLibre's own web worker isn't picked up by Vite's static analysis and silently never lands in the build output, so every map failed at runtime with "Worker failed to load." `frontend/scripts/copy-maplibre-worker.mjs` copies it from `node_modules` into `public/` before every dev/build run (not committed — always copied fresh from whatever `maplibre-gl` version is actually installed), and `main.tsx` points MapLibre at it via `setWorkerUrl()`.

### Data-reading libraries (locked)
| Purpose | Library |
|---|---|
| Files (shapefile, GeoPackage, GeoTIFF, many formats) | **GDAL/OGR** |
| Vector data + geometry operations/checks | **GeoPandas / Shapely** | Quality checks (PRD §7.3) use Shapely; formulas locked in the Quality-check methodology note after §5 |
| Raster data | **Rasterio** |
| PostGIS / PostgreSQL | **SQLAlchemy + psycopg** |
| Oracle Spatial | **SQLAlchemy + `python-oracledb`** (thin mode — no separate Oracle Instant Client install, per §2.1's "no extra software") — decided Phase 1.3 |
| SQL Server | **SQLAlchemy + `pymssql`** (bundles its own driver — no separate Microsoft ODBC driver install, per §2.1) — decided Phase 1.3 |
| ArcGIS Enterprise | **`requests`** against ArcGIS's own REST Services Directory (JSON) — not Esri's official `arcgis` SDK, which is far heavier than listing services needs — decided Phase 1.3 |
| Geoserver | **`requests`** against Geoserver's own REST Admin API (JSON) — not `owslib`, which adds a general OGC-client dependency for no benefit over Geoserver's own clean JSON API — decided Phase 1.3 |

**Acceptance check:** Only the locked libraries appear in the dependency list; each is used for its stated purpose.

**Known gap (Phase 1.3):** the Oracle connector is verified against a real Oracle Database Free instance, but that edition has no Oracle Spatial (MDSYS) installed — true of many real non-Enterprise Oracle installs too, and the connector now degrades gracefully instead of failing when that's the case (see `tarsier/connectors/oracle.py`). The actual `ALL_SDO_GEOM_METADATA` query is verified against a substitute table shaped like the real catalog, not genuine Oracle Spatial — TRS-002 stays at `Built`, not `Tested`, until validated against a licensed Spatial-enabled instance. Similarly, the ArcGIS Enterprise connector is verified against a mock server reproducing the documented REST contract, not a genuine ArcGIS Enterprise instance (no feasible way to stand one up for local testing) — TRS-005 stays at `Built`, not `Tested`, until a real instance is available.

**GDAL/PROJ hardening (found Phase 1.3):** `rasterio` and `pyogrio` each bundle their own copy of GDAL/PROJ. Many real Tarsier users — GIS admins — will have other geospatial software installed (QGIS, ArcGIS, a separate PostGIS) that sets `PROJ_LIB`/`PROJ_DATA`/`GDAL_DATA` system-wide, pointing at a *different* PROJ/GDAL version than the one bundled with Tarsier's pinned dependencies. Found exactly this on the dev machine: a local PostGIS install's `PROJ_LIB` silently hijacked CRS resolution, breaking an ordinary EPSG-coded GeoTIFF. `tarsier/__init__.py` now strips `PROJ_LIB`, `PROJ_DATA`, and `GDAL_DATA` from the environment on import, so Tarsier always uses the GDAL/PROJ data bundled with its own dependencies regardless of what else is installed.

### 3.1 Spatial Knowledge Graph Engine & cross-connection guessing — design (added 2026-10-13)

Built for PRD §14.1 (TRS-117) and §14.10/§7.8 (TRS-118), on branch `feature/TRS-117-knowledge-graph`.

**Storage split:** SQLite stays the single source of truth for connections, items, and the user's confirm/reject decisions (Section 5) — nothing changes there. The Kuzu graph is a **derived copy**, rebuilt from SQLite. It rebuilds automatically after a scan, a flowchart change, or a connection delete. Deleting the Kuzu graph file loses nothing — it regenerates from SQLite with no data loss. This keeps Kuzu disposable, which matters given its archived status above.

**What the graph holds:** sources, items, and the links between them (including links that cross connections). **What it can answer:** which items are reachable within N links; the shortest chain between two items (with the matching column shown on each link); connected groups of items, flagged when a group spans more than one connection, plus which items are most-connected; a "confirmed links only" mode that ignores unconfirmed guesses.

**API surface:** `/api/graph/status`, `/rebuild`, `/overview`, `/neighbors`, `/path`.

**No Kuzu extensions used** (per the archived-package caution above) — grouping/connected-components logic runs in Python instead of a Kuzu graph-algorithm extension, specifically to avoid depending on Kuzu's extension-download mechanism, which no longer works.

**Approved Option A (Round 9):** Read complete non-null distinct sets for columns with at most 1,000 distinct values. Above that limit, select up to 1,000 distinct values from the estimated smaller-distinct side (usable pg_stats n_distinct first, otherwise a bounded observed estimate) and probe the other full column with a parameterized read-only lookup under a five-second statement timeout. Preserve the minimum-five and 80% overlap rules. A timeout is unknown: record and surface "could not verify" in the scan/API count; it never means "no link". Text versus whole-number matching accepts only trimmed ASCII digit text and non-negative whole numbers; preserve leading zeros, reject fractions, signs and non-ASCII digits, and retain exact large integers. Suppress guesses for declared official links in either direction. No background-job or UI redesign is implied.

**Cross-connection guessing (TRS-118):** the existing within-connection column-matching rule (name match after prefix-stripping, internal columns excluded, ≥5 distinct values, ≥80% value overlap of the smaller set — unchanged from the original flowchart design) was moved into one shared function, `guess_between`, called by both the within-connection scan and the new cross-connection scan. **Matching follows approved Option A above; no location/geography-based matching** — confirmed by a test that two layers sharing identical coordinates but no matching column produce no guess. Storage: one new nullable column, `peer_connection_id`, on the existing links table. Confirm/reject works from either connection's side and survives a rescan.

**Screen:** v1 of this shipped as a small "Also related, through other items" list on the item's Connections tab (visible only when the graph is available) — superseded by the dedicated screen specified in FSD (added 2026-10-13, per Manager + user decision) once that's built; this note stays as the backend design record either way.

**Attribution:** recorded in the repo's `NOTICE` file — Kuzu's own tests/demo code (not its source) were used as a reference for API usage.

---

## 4. Frontend delivery

- The React/TypeScript app is **built once (static files)** and **bundled inside the Python package**.
- FastAPI **serves these static files** directly; there is no separate frontend server and no internet needed to load the UI.
- The browser talks to the backend through a local API (same machine).

**Acceptance check:** After `pip install`, the full dashboard loads in the browser with no network connection and no extra build step.

---

## 5. Tarsier's own storage (SQLite)

Tarsier keeps **its own data** separate from the user's data. Stored in a local SQLite file:
- Connection definitions (how to reach each data source; secrets handled per Section 9).
- **Cached results** — computed statistics and quality-check results (so dashboards load instantly).
- **Change logs** read/collected from sources (and polling snapshots where used).
- **Alert rules** and their history.
- **Automations** (the "when → if → do" definitions) and run history.
- **Settings**, including AI configuration (key stored securely — Section 9).
- **Confirmed/guessed/user-added connections** for the flowchart (PRD 7.8).

This is distinct from the user's monitored databases, which Tarsier only reads.

**Acceptance check:** All Tarsier state lives in its own SQLite store; nothing Tarsier needs to function is written into the user's data sources (except the optional trigger install in Section 6).

**Schema migrations (added Phase 2):** `Base.metadata.create_all()` only creates missing *tables* — it never alters an existing one, so a column added to a model later (e.g. the `last_scanned_at` this phase added) silently doesn't appear in a database created by an earlier version. Found by hitting this with real local data from an earlier phase, not in a test. `tarsier/storage/db.py` now runs a minimal migration on every startup: it diffs each model's columns against the real table (via SQLAlchemy reflection) and issues `ALTER TABLE ... ADD COLUMN` for anything missing. This covers every migration this project needs for now (adding nullable columns); it does not handle renames or drops — a real migration tool (e.g. Alembic) would be needed if that's ever required, not decided here.

---

**Statistics engine methodology (PRD §7.2, decided Phase 3):** the PRD names "messy categories," "out-of-range values," and "map outliers" by example only, not formula — each needed a concrete, generalizable rule rather than a guess:
- **Out-of-range values** (numeric columns): IQR outliers — outside [Q1 − 1.5×IQR, Q3 + 1.5×IQR], the standard domain-agnostic definition. User-defined rules (e.g. "diameter must be positive") are a distinct, later feature (PRD §7.3's Custom attribute rules, Phase 4), not this.
- **Messy categories** (text columns): case/whitespace variants of the same normalized value, plus a small fixed dictionary of common address/road-type abbreviations (Rd/Road, St/Street, Ave/Avenue, etc. — found necessary because the PRD's own example, "rd" vs "Road", isn't a string-prefix match, so no generic prefix heuristic can catch it).
- **Map outliers** ("a point in the ocean"): there's no land/water reference dataset anywhere in the locked stack, so this is a statistical spatial outlier — a feature whose centroid is far from the rest of its own layer (median + median-absolute-deviation, not mean/std — a single far-away point drags a mean/std toward itself and can mask the very outlier it's meant to catch on a small sample, found via our own test). Not literal ocean detection.
- **Flag matching rows (locked Phase 3):** Feature B flags (messy categories, out-of-range, duplicates, map outliers, null geometry) store **which specific sample rows/features matched**, not only aggregate counts, so a flag click can list those rows and (for map outliers / null geometry) plot those points.
- **Sampling** (TAD §8): every connector's `sample_rows()` fetches `limit + 1` rows to detect truncation without a separate COUNT query, per "read gently."
- **Per-connector spatial support in `sample_rows()`**: Postgres (`ST_Centroid`) and Files (GeoPandas) support every geometry type. SQL Server's `.STCentroid()` returns NULL for anything but a polygon (a real SQL Server limitation, confirmed directly against the seeded LineString fixture) — uses `.STEnvelope().STCentroid()` (bounding-box center) instead, which works for any geometry type. Oracle has no spatial-outlier support at all — Oracle Spatial still isn't available to test against (§3's existing known gap).
- **Known gap (Phase 3):** ArcGIS Enterprise and Geoserver still have no `sample_rows()` path. PRD §5 lists Statistics as available for both, but those connectors only list contents today. The Statistics tab must say so clearly — this was not silently implemented and not silently skipped in the UI.

**Quality-check methodology (PRD §7.3, decided Phase 4):** the PRD names each check by example, not formula. Locked rules:

- **Geometry validity:** Shapely `is_valid` (TAD §3). Self-crossing / broken shapes fail. Null geometry is Feature B, not this check.
- **Overlap:** two polygons in the same layer whose intersection has **positive area** (shared edges only do not count).
- **Sliver:** a polygon that is **both** (a) thin — compactness `4π × area / perimeter²` **below 0.05** — **and** (b) small — area **below 1% of the layer’s median polygon area**. Both required so ordinary small-but-compact polygons are not flagged.
- **Gap:** dissolve the layer’s polygons to one union; any **interior hole** in that union whose area is below the same small-area threshold as slivers (1% of median polygon area) is a gap.
- **Dangle:** a line endpoint with no *other* line’s endpoint or vertex within **0.1% of the layer bounding-box diagonal** (scale-adaptive; works regardless of CRS/units).
- **Completeness (“missing features”):** not a second reference layer. If the layer has a monotonic integer ID/OBJECTID-style column (`id`, `objectid`, `fid`, `ogc_fid`, `gid`, case-insensitive), flag missing numbers in `min…max`. If no such column exists, the check is **not applicable**. Empty attributes stay in Statistics — not duplicated here. This check reads the ID column in **full** (a sample cannot find sequence gaps).
- **Projection:** same majority-CRS rule as the Overview projection chart (DVS §11). The CRS used by most layers on the connection is expected; any other CRS on this layer is flagged. No per-layer expected-CRS setting.
- **Boundary:** the user picks **another vector layer on the same connection** (layer picker only — no file upload). Features not covered by that layer’s union fail (Shapely `covers`).
- **Consistency** ("label says park, shape is a road"): **not** automatic land-use inference (no reference dataset, same constraint as map outliers). Folded into **custom attribute rules**: a rule may require "when field X = Y, geometry type must be Z."
- **Explain with AI (TRS-041):** Phase 7, not Phase 4 (PRD build order 7.2).

- **Sampling:** geometry-based checks use the same sample-or-full-run pattern as statistics (`sample_geometries()`, `limit+1`). ArcGIS/Geoserver have no geometry sample path yet (same known gap as statistics). Oracle Spatial still unavailable — Oracle geometry quality checks degrade with a clear message.

Custom attribute rules are validity constraints. In addition to existing literal
comparisons and empty/not-empty predicates, support three additional families:

- Same-table column comparisons: >, >=, <, <=, = and != between compatible scalar columns.
- MATCHES TEXT PATTERN and DOES NOT MATCH TEXT PATTERN: Python regular expressions evaluated with re.search; use anchors for whole-value formats.
- IS UNIQUE: no value; flag every occurrence of a duplicated non-empty value, including the original.

All three quality-rule families skip null, empty-string and whitespace-only
operands, matching the existing empty-value check. Column comparison skips when
either operand is empty. Patterns and uniqueness skip when the tested value is
empty. Exclude empties before comparison, regex evaluation and duplicate grouping;
blanks never duplicate one another. Count skipped rows separately and display
“N rows skipped, value empty.” With several rules, count the union of skipped rows
once; a row skipped by one rule may still fail another rule with non-empty operands.

Validate fields and comparison-column names against the table catalog before
saving and running. Reject incompatible scalar types. Store the comparison-column
name or regex in the existing nullable value field; IS UNIQUE stores no value.
Accept no user-written SQL. Keep connector reads read-only and within their existing
timeouts. Default checks follow §8; other connectors retain their existing sample policy. Explicit full extended-rule
requests read at most 1,000,000 rows plus lookahead, and remain labelled sampled if
more rows exist. Sample uniqueness is not proof of table-wide uniqueness. Bound
regex evaluation in an isolated worker to five minutes and return clear errors for
invalid or over-limit patterns.

Quality rules report violations; banned-value alerts fire when their selected
condition is true. A quality rule total_value >= land_value flags total_value 80
with land_value 100; an alert total_value < land_value fires for that row. A quality
ZIP MATCHES ^[0-9]{5}$ rule flags “12X45”; a ZIP DOES NOT MATCH ^[0-9]{5}$ alert fires
for that value. IS UNIQUE flags both occurrences of a repeated key in quality
results. It is not available for alerts: interpreting it as an alert predicate
would fire for unique values, the opposite of a duplicate-quality violation.
The UI omits it, and alert API validation and engine evaluation reject it with a
clear quality-only message. Other existing and extended alert operators retain
their matching semantics, including their existing empty-value behavior. The
quality skipped count is not an alert count. Extended alerts use aligned current
rows from the selected table, preserve sample labelling and never combine unrelated
columns or treat historical after-images as separate current rows.


**Connection-guess methodology (PRD §7.8, decided Phase 8):**
- **Column names:** lowercase, trim surrounding whitespace, and convert internal spaces to underscores while preserving underscores. Before comparing, strip one leading known prefix (`from_`, `to_`, `new_`, `old_`, or `feature_`) from either name. Also strip compact `new`/`old` prefixes (`newreachcode` matches `reachcode`) because the source schema uses that spelling. After prefix removal, names must match exactly (`parcel_id` matches `Parcel_ID` and `parcel id`, but not `parcelid`); no fuzzy or partial matching.
- **Non-join column exclusion:** after name normalization, never guess links for `objectid`, `oid`, `fid`, `gid`, bare `id`, or `pagenumber`, regardless of value overlap. The ID names are treated as generated row identifiers; `pagenumber` is a positional page index, not a join key.
- **Minimum values:** each side must have at least 5 non-null distinct values in its sample. A matching name with fewer values on either side is not a guess candidate.
- **Sample values:** use the approved Option A in §3.1: complete distinct sets through 1,000, otherwise bounded distinct probes against the full lookup column. A guess qualifies at 80% overlap; timeouts remain unknown.
- Mark a qualifying guess as sample-based if either column was sampled rather than scanned in full. Show no confidence score; use the binary guessed treatment from PRD §7.8 (dashed edge and "?" badge).

---

## 6. Connecting to data & change tracking

### 6.1 Connections (read-only)
- Supported: **PostGIS/PostgreSQL, Oracle Spatial, SQL Server, files in folders, ArcGIS Enterprise, Geoserver.**
- All connections are **read-only** for user data.
- **Tiered features** per the PRD (Section 5): when a user sets up a connection, Tarsier clearly states which features are unavailable for that type (e.g. files → no change tracking).

### 6.2 Change tracking — method
- **Primary (A): database triggers.** For PostGIS, Tarsier can install small triggers inside the user's database that record every change (who / when / before → after) into a history table. This catches changes made by **any** tool or user.
  - Installing triggers needs **one-time write/admin permission** on that database.
  - This is **optional and skippable**, and clearly explained to the user:
    > *"Tarsier is read-only on your data. To enable full change tracking on PostGIS, it needs one-time permission to install a history log. This is optional — you can skip it."*
- **Fallback (B): polling / comparing.** Where triggers aren't available or permission is declined, Tarsier periodically reads and compares to detect **what** changed. This **cannot reliably tell who** made the change and may miss fast changes between checks.

History logger privilege boundary, fail-open behavior and upgrades: The row and DDL
history logger functions are zero-argument SECURITY DEFINER functions owned by the
role that accepts installation or upgrade. They pin search_path to pg_catalog,
tarsier_changes, use fully qualified catalog functions/types and history relations,
and accept no caller-supplied SQL or identifiers. They record session_user as the
actor. PUBLIC has no USAGE or CREATE on schema tarsier_changes and no privileges on
the history table, its sequence or the private tracking-failure sequence. Direct
log-read grants are limited to the installing role and Tarsier's configured
connection role; the latter receives schema USAGE and log SELECT only when it is
a separate role. Ordinary editors cannot read or write the log directly. PostgreSQL
administrator/superuser powers remain outside this application-grant restriction.
No source-table privileges are granted or changed. Existing installations are
upgraded only through the same explicit optional Allow flow, replacing logger
definitions and history ACLs without rewriting source rows or reinstalling table
triggers.

The user's edit must succeed when only history logging fails. A handler scoped to
the private logging block catches SQLSTATE classes 22, 23, 53 and 54 and codes
3F000, 42501, 42P01, 42703, 42704, 42804, 42809, 55000, 55P03, 58030 and P0001;
it emits a server WARNING and attempts to increment a private nontransactional
failure counter. Query cancellation 57014, deadlock 40P01, serialization failure
40001, other unlisted errors and errors from the user's own statement propagate
normally. The existing changes API exposes tracking health from logger-version
checks, log/counter reachability, trigger coverage and the sticky failure counter.
A nonzero counter means possible history gaps, including attempts later rolled
back; it is not an exact lost-change count. If the marker cannot be saved, a second
WARNING reports unknown completeness. Unreachable health objects mean completeness
is unverified; loss and restoration of both log and marker cannot prove historical
completeness.

The dedicated POST /api/connections/{id}/changes/acknowledge endpoint accepts an acknowledge_failures_up_to integer observed by the caller. Tarsier records that counter value and the acknowledgement time in its own connection metadata and returns them in tracking_health. It never resets the PostgreSQL sequence or claims the missing history was recovered. Failures beyond the acknowledged value remain unacknowledged; the raw total remains visible. Acknowledgement records review, not restored completeness. No new screen is required.

Optional row tracking excludes PostgreSQL system relations and PostGIS extension-owned metadata relations; user tables using PostGIS types remain eligible.

### 6.3 Tier reality (from PRD)
- PostGIS/Postgres → full (triggers possible).
- Oracle / SQL Server → partial, depends on their setup.
- Files → none (no snapshots, per PRD decision).
- ArcGIS Enterprise / Geoserver → depends on what they expose.

**Change-tracking methodology (PRD §7.4, decided Phase 5):**

- **Where events live:** with permission, Tarsier creates schema `tarsier_changes` in the user's PostGIS database (the TAD §6.2 optional write). Row triggers log every INSERT/UPDATE/DELETE into `tarsier_changes.change_log` (who = `session_user`, when = `clock_timestamp()`, before/after = `to_jsonb(OLD/NEW)`, feature id = primary key, else `id`/`objectid`/`gid`/`fid`). A DDL event trigger logs ALTER TABLE add/drop column as `action=schema`. Tarsier **syncs** that log into its own SQLite (`change_events`) so dashboards never query the user database on page load (TAD §8).
- **Polling fallback:** if trigger install is skipped or fails, Tarsier compares each table's primary-key → `md5(row::text)` fingerprint to the last snapshot. That yields what changed, not who (`db_user` is null, labeled "unknown — polling"). Fast in-between changes can be missed.
- **Mass-change flag:** events that share one database transaction (`txid`) on one table are a batch. The batch is mass if it covers **≥ 50 rows**, or **≥ 25% of the table** with a floor of **10 rows** — domain-agnostic stand-in for the PRD's "deleted an entire area" case (no area column is assumed).
- **Change-volume spike (DVS §5):** a day's bar is a spike when its count is **more than 3× the mean of the previous 7 days**. If that mean is 0, a day with ≥ 10 changes is a spike.
- **Compare two dates:** every captured event with `occurred_at` in `[start, end]` (inclusive calendar dates, UTC).
- **Auto change report:** a daily or weekly summary stored in SQLite (counts by action, mass-change batches, schema events). Generated on demand and when due. Configure-schedule in v1 lives on the Changes screen (Automations Phase 7 can link here later).
- **Not in Phase 5:** Oracle/SQL Server/ArcGIS/Geoserver capture (still "partial — depends on their setup"); files and rasters stay none. Explain-today's-changes AI is Phase 7.

**Acceptance check:** On a PostGIS test database, with permission granted, triggers capture correct who/when/what for edits, deletes, mass deletes, and schema changes. With permission declined, polling reports what-changed without "who." Files show no change tracking and say so.

---

## 7. Background jobs & AI

### 7.1 Scheduler (APScheduler)
- Runs **inside** the app — no extra software, works offline.
- Handles: scheduled quality checks, polling, alert evaluation, and automations.
- **Users define their own schedules** — any number of jobs, at the times and repeat intervals they choose.

**Alert methodology (PRD §7.5, decided Phase 6):** each type is a stored rule (SQLite) evaluated after an Overview scan, a quality-check run, or a change-log sync — never on page load. First evaluation only snapshots the current state (no flood of "new layer" fires). Defaults reuse earlier locked numbers so users aren't asked for a guess:

- **Mass delete/edit:** fires on a change event already flagged mass (TAD Phase 5: ≥ 50 rows or ≥ 25% of the table, floor 10).
- **Row count drop:** current cached `row_count` is **≥ 25%** below the previous snapshot (same share as mass-change).
- **Schema change:** any captured `action=schema` event on the target.
- **Freshness:** layer `last_modified` (else last change event, else last scan) is older than **90 days** — the Overview stale window.
- **Quality score drop:** score is `100 × (good checks / checks that have been run)` from the Quality cache. Fires if the score falls **10 points** or more versus the previous snapshot.
- **Specific user:** any captured change whose `db_user` matches the rule (case-insensitive).
- **New/dropped layer:** item keys in the Overview cache vs the previous snapshot.
- **Size spike:** `size_bytes` grew **≥ 50%** versus the previous snapshot.
- **Banned value:** user-set field + operator + value (same operators as custom quality rules) on a sample of the target layer, or on `after` JSON of recent edits.
- **Notify:** every fire is written to Tarsier's alert log. `webhook` also POSTs JSON. Email / Slack / Teams are accepted on the form but only logged until notification-channel Settings exist (FSD §13 — later).

**Automation methodology (PRD §7.6, decided Phase 7):** a saved graph in SQLite — trigger node(s) → optional condition node(s) → action node(s), edges in that order. No extra canvas library; the UI is three columns of cards plus SVG connectors, with a palette **Add** control so the builder is usable from the keyboard (FSD §16). Evaluated after Overview scan, quality-check run, change-log sync, or a scheduler tick — never on page load. First run of a threshold-style automation only snapshots (same idea as alerts). Defaults reuse locked numbers:

- **Triggers:** `any_change` (optional `mass_only`); `schedule` (daily UTC `hour`/`minute`, or `every_minutes`); `threshold` (row-count drop 25%, size spike 50%, or quality drop 10 points); `specific_user`; `quality_failure` (any cached check `danger`); `new_feature` (captured `insert` events).
- **Conditions:** `user_eq`; `count_drop` (25% unless the node sets percent); `layer_eq`; `value_out_of_range` (same operators as quality/banned-value).
- **Actions:** `log`; `webhook` POST; `email` / `chat` (Slack/Teams) logged until notification-channel Settings exist; `run_quality` (read-only quality scan); `ai_summarize` (job 2 on today's change counts, then deliver like notify).
- **Test run:** walks the graph against recent cache/events, records a trace for the canvas animation, and **does not** POST webhooks or run quality scans.
- **Templates:** Notify on mass delete; Evening change summary; Quality failure → log.

**Alert and automation event checkpoints:** New event-based rules record a creation checkpoint and consider only events captured after creation. No backfill is offered. Existing upgraded rules keep their current behavior: cached history does not replay, and prior fire or run history remains. Delivery semantics: at most one delivery attempt per rule/event pair; a crash between claiming an event and sending can lose one notification but never repeats it.

**AI jobs 2–4 (PRD §7.7, decided Phase 7):** the common chat-completions path from Phase 3. The model never gets a live database connection and never writes to user data.

- **Explain today's changes:** counts by action/layer/user for the current UTC day (plus mass/schema flags). No `OLD`/`NEW` cell values.
- **Explain a quality problem + fix:** check id, status, finding counts, layer name — not geometries or row payloads. Suggestion is text only; Tarsier does not apply a fix.
- **Help build an automation:** user sentence in, graph JSON out (same node kinds as the builder). The UI can save that graph; the model does not execute it.

**Acceptance check:** A user can create multiple schedules at custom times/intervals; each fires at the right time and runs its job.

### 7.2 AI assistant
- **Settings page** lets the user choose **Ollama (local)** or **API key (external)**.
- **Config shape (locked Phase 3.2):** one generic config for both choices — **endpoint URL**, **model name**, and **API key** (key required for external; optional for local Ollama). No named-provider list. The endpoint URL is the full chat-completions URL (e.g. `http://127.0.0.1:11434/v1/chat/completions` or `https://api.openai.com/v1/chat/completions`).
- **Wire protocol (locked Phase 3.2):** OpenAI-compatible `POST` chat-completions JSON. Ollama speaks this format too, so **one common internal path** handles both; the rest of the app never branches on provider.
- **Offline rule:** Ollama → fully offline. External API → that feature uses the internet, **clearly labeled**.
- **Privacy warning (locked):** when an external API is chosen, Tarsier warns:
  > *"Using an external API may send parts of your data descriptions to that provider. Use Ollama for fully private AI."*
- If AI is not configured, AI features show a friendly **"set up AI first"** message; **the rest of Tarsier works without AI.**
- AI does exactly the **four v1 jobs** (PRD 7.7): plain-English → query, explain today's changes, explain a quality problem + fix, help build an automation. Phase 3 wired the common path and job 1; Phase 7 adds jobs 2–4 and the FSD §11.3 drawer.
- **AI never writes to user data** (read-only rule holds). The AI is never given a live database connection.

**AI query architecture (locked Phase 3.2, PRD §7.2 / job 1):**
- The model receives **schema only** (column names and types) — never raw row values, never a live DB connection.
- It returns a **structured filter** in the same spirit as the FSD §8 caption (e.g. `year < 2010 AND material IS NULL`) — **not SQL**, and nothing the model executes itself.
- Tarsier applies that filter through its own existing **safe, read-only** data path (the same `sample_rows()` mechanism the statistics engine already uses). The AI never touches the user's database.

**Acceptance check:** Both Ollama and API-key modes work for all four jobs on test data; the privacy warning appears for external API; the app functions with AI unconfigured.

---

## 8. Performance at scale

Target scale: databases in the **terabytes**, layers with **millions of rows**.

Rules:
- **Do not recompute everything constantly.** Compute statistics and quality **on demand** (user clicks "run") and/or **on schedule**, then **cache the results in SQLite** so dashboards load instantly.
- **Sampling for huge layers** — Tarsier may check a representative sample for speed, **clearly labeled "based on a sample,"** and always allow a **full run** when the user wants it.
- **Read gently** — background reads must not block or strain the user's database.
- **Bound connection and lock waits** - PostGIS connection checks use a 5-second connect timeout and 5-second statement timeout. Optional trigger installation uses a 5-second lock timeout and 15-second statement timeout so a busy table cannot leave Test & Save waiting indefinitely.

- **PostGIS guarded sampling (Round 9):** Use finite positive reltuples, otherwise finite positive n_live_tup. At an estimated 3,000 rows or fewer, read the complete table and label it complete; never impose a five-percent cap on small tables. Above 3,000, combined percentage = min(50, 100 × 1500 / estimate). Use ten fixed SYSTEM seeds 719–728, each at one tenth of that percentage, combined and deduplicated by row identity. Keep the existing sample label. Record method, seed vector and actual retained row count in result details. A seeded physical sample repeats only while data/layout are unchanged; it does not prove population extrema or uniqueness.
- **Missing-estimate guard:** Never turn an unknown/negative/zero estimate into SYSTEM(100). When neither estimate is usable, use a fixed-budget spread-out physical-address fallback: at most 40 heap pages, 10,000 tuple addresses and 2,000 returned rows, with a verified direct TID access plan. Never fall back to a sequential scan or a full-table hash sort. Retain stable selected keys and a versioned cached sample to meet logical-data repeatability across storage maintenance. This round implements physical-layout repeatability; durable key/version caching remains a later qualification.
- **Completeness full-ID exception:** Retain the full-ID completeness exception for up to 1,000,000 estimated rows under a five-second statement timeout; larger or unknown sizes require an explicit full-ID request, and no sample proves sequence completeness.

**RC1 full-statistics guard:** The full-statistics exception to the general full-run rule is limited to tables with a known estimated row count of at most 20,000; a serialized statistics result may not exceed 64 MiB. Larger or unknown tables use labelled sample statistics. The Overview full check skips their full statistics, refreshes the sample, and records a per-table skip message; previously cached oversized results are excluded from dashboard reads.
- **Run timing persistence:** Persist run/build/source identifiers, UTC start/end, monotonic elapsed, item/check, row/byte counts, separate fetch/compute/cache-write/alert/graph durations, and timeout/cancel outcomes in Tarsier's own SQLite; no row values, SQL parameter values or secrets.

**Acceptance check:** Dashboards load from cached results without re-querying the source each time; a huge layer can be summarized by sample (labeled) and by full run; monitoring does not lock the user's database.

---

## 9. Security

Because Tarsier runs on sensitive government/corporate data, these rules are mandatory:

- **Read-only on user data** in v1. The only write is the optional change-tracking trigger install (Section 6), which requires explicit user permission.
  - **Enforcement varies by connector** (found during Phase 1.3): Postgres (`default_transaction_read_only`) and Oracle (`SET TRANSACTION READ ONLY`) reject writes at the server itself. SQL Server has no T-SQL equivalent — read-only there is application discipline only (Tarsier's code issues nothing but SELECT); a read-only SQL Server login is recommended for a server-enforced guarantee. Files, ArcGIS, and Geoserver connectors are read-only by construction (they never call a write operation at all).
- **Secrets (API keys, database passwords) stored securely:**
  - Use the **operating system's secure storage** where available; otherwise **encrypt at rest**.
  - Implementation (locked Phase 1.1): **`keyring`** for OS-secure-storage, with a **`cryptography`**-based Fernet encrypt-at-rest fallback for headless environments without an OS keystore.
  - **Never store secrets in plain text, never write them to logs, never display them back in full** (show masked).
- **Local-only by default** — the server listens on the local machine; it is not exposed to the public internet by Tarsier itself.
- **No unapproved telemetry / no phoning home.** Tarsier does not send usage data anywhere. The only outbound internet uses are ones the user deliberately configures: an external AI API (Section 7.2), and — for Alerts (PRD §7.5) and Automations (PRD §7.6) — a notification sent to an email address, Slack, Teams, or a webhook URL the user sets up. Nothing else leaves the machine.
- **Contributions must not add write-access to user data in v1** (enforced in review — rules detailed in the WFD).

**Acceptance check:** Secrets are never found in plain text on disk or in logs; the app does not make outbound connections except to a user-configured external AI or a user-configured notification channel (email/Slack/Teams/webhook); a security review confirms read-only behavior on user data.

---

## 10. Project structure (suggested, confirm in build)

A clear layout so contributors can navigate. (Exact names may be refined in Phase 0 of the build.)

```
tarsier-geo/
├── LICENSE                 # Apache-2.0
├── README.md
├── SECURITY.md             # security + contribution rules (see WFD)
├── pyproject.toml          # packaging, deps, entry point `tarsier-geo`
├── package.json            # root npm workspaces file — hoists node_modules so
│                           # tests/frontend/ (outside frontend/) can resolve
│                           # frontend/'s dependencies. Added Phase 0; not a
│                           # stack change, just module-resolution plumbing.
├── tarsier/                # Python backend
│   ├── cli/                # start/stop, port handling
│   ├── api/                # FastAPI routes
│   ├── connectors/         # postgis, oracle, sqlserver, files, arcgis, geoserver
│   ├── stats/              # statistics engine
│   ├── quality/            # quality checks
│   ├── changes/            # triggers + polling
│   ├── alerts/             # alert rules + evaluation
│   ├── automation/         # "when → if → do" engine
│   ├── ai/                 # Ollama + API common path
│   ├── scheduler/          # APScheduler jobs
│   ├── storage/            # SQLite models + cache
│   └── web/                # serves the bundled React build
├── frontend/               # React + TypeScript source (Vite-built)
│   └── (built output bundled into the package)
└── tests/
    ├── backend/            # pytest
    ├── frontend/            # Vitest / RTL
    └── datasets/           # planted-error test data for the internal exam
```

**Acceptance check:** The repo matches a clear, documented structure; a new contributor can find each feature's code from the folder names.

---

## 11. Build notes mapped to PRD phases

Use this alongside the PRD Build Order:
- **PRD Phase 0** → set up repo per Section 10, confirm this stack, add Apache-2.0 + security files.
- **PRD Phase 1** → `connectors/` + tier notices (Section 6).
- **PRD Phase 2** → `api/` + `web/` + React overview and detail pages (Sections 3–4).
- **PRD Phase 3** → `stats/` + `ai/` (jobs 1) (Sections 3, 7.2).
- **PRD Phase 4** → `quality/` (Section 3).
- **PRD Phase 5** → `changes/` triggers + polling (Section 6).
- **PRD Phase 6** → `alerts/` + `scheduler/` (Section 7.1).
- **PRD Phase 7** → `automation/` + remaining AI jobs (Section 7.2).
- **PRD Phase 8** → flowchart (frontend + stored links in Section 5).
- **PRD Phase 9** → run internal exam from `tests/datasets/`, then real-user test.

---

## 12. Decisions still owned by other documents

- Exact screen layouts & UI design → **FSD**.
- Chart / visualization specifications → **DVS**.
- Dev/ops process, CI, release steps, full security & contribution rules → **WFD**.
- Feature-to-test mapping → **FTL**.

---

*End of TAD v1.0.*
