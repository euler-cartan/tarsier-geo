# Tarsier — Feature Traceability List (FTL)

**Version:** 1.0 (v1 scope)
**Status:** Approved for use
**Date:** 2026-10-10
**Companion to:** PRD v1.0, TAD v1.0, FSD v1.0, DVS v1.0

---

## 0. How to use this document

### For Claude Code (the builder)
- Every row is one **testable unit of behavior**. When you build a feature, also build (or note as needed) the test referenced in its row.
- Use the **ID** (e.g. `TRS-014`) in commit messages, test file names, and PR descriptions when relevant, so work can be traced back to this table.
- Update the **Status** column as you go (see Section 1 for the status values). Do not mark `Passed` yourself — mark `Built` when done; the Manager or the exam run confirms `Passed`.

### For the Manager (reviewer)
- This table **is** the internal exam structure referenced in PRD Section 11. Running every `Not Started`/`Built` row to `Passed` = Stage 1 complete.
- Group by section to review one feature area at a time, matching the PRD Build Order phases.

---

## 1. Status values

| Status | Meaning |
|---|---|
| `Not Started` | Not yet built |
| `Built` | Code complete, not yet verified against its test |
| `Tested` | Test has been run at least once |
| `Passed` | Test passed, confirmed by Manager or exam run |
| `Failed` | Test run and failed — needs fix, do not ship |

All rows start at `Not Started`. This document ships with that default; status is updated during the build, not rewritten here.

---

## 2. ID scheme

`TRS-###` — sequential, stable once assigned. Never reuse or renumber an ID, even if a feature is later removed (mark it `Dropped` in Status instead, keep the row for history).

Test type key: **U** = unit test (pytest/Vitest), **I** = integration test (real connection/data), **M** = manual exam item (checked by a person against the internal exam, PRD Section 11), **V** = visual/UX check against FSD/DVS spec.

---

## 3. Connections (PRD Section 5 / TAD Section 6)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-001 | Connect to PostGIS/PostgreSQL | PRD §5, TAD §6.1 | Create a connection with valid credentials; layers/tables list correctly | I | Tested |
| TRS-002 | Connect to Oracle Spatial | PRD §5 | Same as above, Oracle test instance | I | Built |
| TRS-003 | Connect to SQL Server | PRD §5 | Same as above, SQL Server test instance | I | Tested |
| TRS-004 | Connect to files in a folder | PRD §5 | Point at a folder with shapefile/GeoPackage/GeoTIFF/CSV; contents list correctly | I | Tested |
| TRS-005 | Connect to ArcGIS Enterprise | PRD §5 | Connect to a test ArcGIS Enterprise instance; contents list correctly | I | Built |
| TRS-006 | Connect to Geoserver | PRD §5 | Connect to a test Geoserver instance; contents list correctly | I | Tested |
| TRS-007 | Tier notice shown before save | PRD §5, FSD §5 | For each connection type, the correct "unavailable features" list is shown before saving | V | Tested |
| TRS-008 | Failed connection test blocks save | FSD §5, TAD §8 | Invalid credentials/path show inline error and prevent saving; a slow PostGIS connection check times out with a clear error | I | Built |
| TRS-009 | All connections are read-only | PRD §1, TAD §9 | Confirm no write operation occurs against user data through any connector, except TRS-010 | I | Tested |
| TRS-010 | Optional PostGIS trigger install, skippable | PRD §6.2, FSD §5, TAD §8 | User can skip trigger install and still use Tarsier; if enabled, a busy table fails promptly with a clear error | I | Built |

---

## 4. Feature A — Overview (PRD §7.1, FSD §6, DVS §4/§11)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-011 | Health score - database & per layer | PRD §7.1, DVS §4 | Per-layer and database scores match the locked weighted formula; unavailable components are excluded and remaining weights renormalized; ring color and tooltip breakdown match DVS §4 | U+V | Built |
| TRS-012 | Layer list table — all columns correct | PRD §7.1 | Row/feature count, size, last changed, projection, index flag, quality score all match ground truth | I | Tested |
| TRS-013 | Stale layer flag | PRD §7.1 | A layer untouched beyond the threshold is flagged "Stale" | U | Tested |
| TRS-014 | Heavy layer flag | PRD §7.1 | Largest/slowest layers are correctly identified and flagged | U | Tested |
| TRS-015 | Relationships summary + link to flowchart | PRD §7.1, FSD §6 | Summary card shows correct count; link opens full flowchart | V | Built |
| TRS-016 | Projection overview chart | PRD §7.1, DVS §11 | Bar chart groups layers by CRS correctly; mismatches flagged `status-warning`; clicking a bar filters layer list | I+V | Tested |
| TRS-017 | Map preview/thumbnail per layer | PRD §7.1 | Thumbnail renders and roughly matches the layer's extent | V | Tested |
| TRS-018 | Overview loading/empty/error states | FSD §15 | All four states render correctly (disconnect test DB mid-load for error state) | V | Tested |

---

## 5. Feature B — Statistics + AI query (PRD §7.2, FSD §8, DVS §7)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-019 | Per-column stats (min/max/avg/empty/unique/top values) | PRD §7.2 | Computed values match a hand-calculated reference on a known test table | U | Tested |
| TRS-020 | Messy-category detection | PRD §7.2 | "Road"/"road"/"ROAD"/"rd" correctly grouped as a flagged inconsistency | U | Tested |
| TRS-021 | Out-of-range value detection | PRD §7.2 | Planted negative diameter / year=9999 correctly flagged | U | Tested |
| TRS-022 | Duplicate detection | PRD §7.2 | Planted duplicate row/feature is correctly identified | U | Tested |
| TRS-023 | Map outlier detection | PRD §7.2 | A point planted in an impossible location (e.g. ocean) is flagged | U | Tested |
| TRS-024 | Null geometry detection | PRD §7.2 | Rows missing geometry are correctly listed | U | Tested |
| TRS-025 | AI plain-English query — correct results | PRD §7.2, §7.7 | The assistant answers a set of known test questions correctly against planted data | M | Tested |
| TRS-026 | AI query box shows generated query | FSD §8 | The interpreted query is visibly shown alongside results, for transparency | V | Tested |
| TRS-027 | Histogram correctness (numeric columns) | DVS §7 | Bin counts and min/max/avg reference lines match the underlying data | U+V | Tested |
| TRS-028 | Flags are clickable and filter correctly | FSD §8 | Clicking a flag (e.g. "duplicates") filters the stats table/map to just those rows | V | Tested |

---

## 6. Feature C — Quality checks (PRD §7.3, FSD §9, DVS §8)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-029 | Geometry validity check | PRD §7.3 | Planted self-crossing polygon correctly flagged | U | Tested |
| TRS-030 | Topology — gaps | PRD §7.3 | Planted gap between polygons correctly flagged | U | Tested |
| TRS-031 | Topology — overlaps | PRD §7.3 | Planted overlap correctly flagged | U | Tested |
| TRS-032 | Topology — slivers | PRD §7.3 | Planted sliver polygon correctly flagged | U | Tested |
| TRS-033 | Topology — dangles | PRD §7.3 | Planted unconnected line end correctly flagged | U | Tested |
| TRS-034 | Completeness check | PRD §7.3 | Planted missing integer ID in an OBJECTID-style sequence is flagged; no sequence column reports not applicable | U | Tested |
| TRS-035 | Custom attribute rule — create/edit/delete | PRD §7.3, FSD §9 | User-defined rule (e.g. "diameter must be positive") can be created, edited, deleted, and runs correctly | I+V | Tested |
| TRS-036 | Projection check | PRD §7.3 | Layer in an unexpected CRS is correctly flagged | U | Tested |
| TRS-037 | Boundary check | PRD §7.3 | Planted feature outside the expected area is correctly flagged | U | Tested |
| TRS-038 | Consistency check | PRD §7.3 | Custom geometry-type rule (e.g. category = Road → geometry must be LineString) flags a planted mismatch | U | Tested |
| TRS-039 | Quality results bar — independent per-check update | DVS §8 | Each check's bar updates on its own completion, not only when the full suite finishes | I+V | Tested |
| TRS-040 | "Show on map" for failing features | FSD §9, DVS §8 | Clicking a failed check highlights exactly the correct features on the map | I+V | Tested |
| TRS-041 | "Explain with AI" on a failed check | PRD §7.7, FSD §9 | AI gives a plain-English explanation and a suggested fix (read-only, no auto-fix applied) | M | Tested |

---

## 7. Feature D — Change tracking (PRD §7.4, FSD §10, DVS §5/§6/§9)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-042 | Who/when/what capture (edit) | PRD §7.4, TAD §6.2 | As a non-owner role with edit permission only on the source table, perform an edit on the PostGIS test database and verify the correct session user, time and before/after values are captured; also verify owner edits still work. | I | Tested |
| TRS-043 | Who/when/what capture (delete) | PRD §7.4 | As a non-owner role with DELETE permission on the source table, perform a delete and verify correct user, time and before-image capture, including the founding utility-company scenario replica. | I | Tested |
| TRS-044 | Single-feature history | PRD §7.4, DVS §9 | Timeline for one feature shows all its changes in correct order; diff highlights only changed fields | I+V | Tested |
| TRS-045 | Schema-change detection | PRD §7.4 | As a non-owner role relative to the tracking schema and logger, with the required ownership/authority on its source table, add and remove a column and verify both schema events are captured and shown with the correct session user. | I | Tested |
| TRS-046 | Mass-change detection | PRD §7.4 | As a non-owner role with the required source-table DML permissions, perform a mass delete/edit and verify the correct actor, event count and mass-change flag at the locked thresholds. | I | Tested |
| TRS-047 | Compare two dates | PRD §7.4 | Selecting two dates produces an accurate diff of what changed between them | I | Tested |
| TRS-048 | Auto change report | PRD §7.4 | Scheduled daily/weekly report generates correctly and is viewable | I | Tested |
| TRS-049 | Change-volume graph + spike detection | PRD §7.4, DVS §5 | Graph reflects true change volume; a planted spike (mass change) is colored/marked as an outlier | I+V | Tested |
| TRS-050 | Change feed — filtering | DVS §6 | Filtering by user/layer/date range returns correct results | I | Tested |
| TRS-051 | Polling fallback (no trigger permission) | TAD §6.2 | With trigger permission declined, establish a polling snapshot, perform edits/deletes as a non-owner role with source-table DML permissions, then poll again. Verify exact primary-key-based actions and unknown-polling attribution, without granting tracking-schema access. | I | Tested |
| TRS-052 | No change tracking for files | PRD §5 | File connections show "not available" messaging, not an error or empty table | V | Tested |

---

## 8. Feature E — Alerts (PRD §7.5, FSD §11.1)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-053 | Mass delete/edit alert | PRD §7.5 | Fires correctly when triggered in test scenario | I | Tested |
| TRS-054 | Row count drop alert | PRD §7.5 | Fires when count drops beyond threshold | I | Tested |
| TRS-055 | Schema change alert | PRD §7.5 | Fires on column add/remove | I | Tested |
| TRS-056 | Freshness alert | PRD §7.5 | Fires when a layer isn't updated within the expected window | I | Tested |
| TRS-057 | Quality score drop alert | PRD §7.5 | Fires when a layer's quality score drops beyond threshold | I | Tested |
| TRS-058 | Specific-user alert | PRD §7.5 | Fires only for the specified user's actions | I | Tested |
| TRS-059 | New/dropped layer alert | PRD §7.5 | Fires when a layer is added or removed | I | Tested |
| TRS-060 | Size spike alert | PRD §7.5 | Fires when size grows abnormally | I | Tested |
| TRS-061 | Banned value alert | PRD §7.5 | Fires when a defined banned value appears | I | Tested |
| TRS-062 | Alert creation form — all types | FSD §11.1 | Every alert type can be created, edited, paused, deleted via the UI | V | Tested |

---

## 9. Automation builder (PRD §7.6, FSD §11.2, DVS §14)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-063 | Build a simple when→if→do automation | PRD §7.6 | User builds trigger→condition→action from scratch; saves and runs correctly | I+V | Tested |
| TRS-064 | Multi-step chain | PRD §7.6 | Change→quality check→conditional notify+log chain runs end to end correctly | I | Tested |
| TRS-065 | Start from a template | PRD §7.6, FSD §11.2 | A template opens pre-built into the canvas and can be edited and saved | V | Tested |
| TRS-066 | All trigger types available | PRD §7.6 | Any change, schedule, threshold, specific user, quality failure, new feature — all selectable and functional | I | Tested |
| TRS-067 | All condition types available | PRD §7.6 | User=X, count drop %, layer=Z, value out of range — all selectable and functional | I | Tested |
| TRS-068 | All action types available | PRD §7.6 | Email, chat message, webhook, log, run quality check, AI summarize+send — all functional | I | Tested |
| TRS-069 | AI action — automation | PRD §7.7 | "Every evening summarize today's changes and email the team" works end to end | M | Tested |
| TRS-070 | Test run before save | FSD §11.2, DVS §14 | Test run simulates against recent data and animates the correct executed path | I+V | Tested |
| TRS-071 | Multiple custom schedules | TAD §7.1 | User can create several automations with different custom times/intervals; each fires correctly | I | Tested |

---

## 10. AI assistant (PRD §7.7, TAD §7.2, FSD §11.3)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-072 | Ollama connection works | TAD §7.2 | AI jobs function correctly when configured with a local Ollama model | I | Tested |
| TRS-073 | External API connection works | TAD §7.2 | AI jobs function correctly when configured with an external API key | I | Tested |
| TRS-074 | Privacy warning shown for external API | TAD §7.2, FSD §11.3 | Warning text appears per spec when external API is active | V | Tested |
| TRS-075 | API key stored securely | TAD §9 | Key is never found in plain text on disk or in logs; never displayed back in full | I | Tested |
| TRS-076 | Graceful "set up AI first" state | PRD §7.7, FSD §11.3 | AI features show the configuration prompt, not an error, when unconfigured | V | Tested |
| TRS-077 | AI never writes to user data | PRD §1, TAD §7.2 | Confirm no AI action results in a write to any connected data source | I | Tested |
| TRS-078 | AI job — explain today's changes | PRD §7.7 | Produces an accurate plain-English summary against known test changes | M | Tested |

---

## 11. Raster (PRD §6.3, §8, FSD §7, DVS §10)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-079 | Raster overview fields | PRD §8 | Pixel size, dimensions, bands, projection, footprint, acquisition date, sensor (if present) all correct | I | Built |
| TRS-080 | Raster per-band statistics | PRD §8 | Min/max/avg/spread correct per band on a known test raster | U | Built |
| TRS-081 | Raster per-band histogram | DVS §10 | Histogram matches true distribution; band selector switches correctly; log-scale toggle works | U+V | Built |
| TRS-082 | Nodata % calculation | PRD §8 | Correct percentage reported on a test raster with known nodata coverage | U | Built |
| TRS-083 | Missing metadata shown gracefully | PRD §8, FSD §7 | Absent fields (e.g. no cloud cover data) show "Not available," not an error | V | Built |
| TRS-084 | No change tracking shown for raster | PRD §6.3 | History tab absent/not-applicable for raster items | V | Tested |

---

## 12. Tabular (PRD §6.2, FSD §7)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-085 | Standalone DB table — stats & quality | PRD §6.2 | Same checks as vector (minus geometry) run correctly on a plain DB table | I | Built |
| TRS-086 | Loose CSV — stats & quality | PRD §6.2 | Same checks run correctly on a CSV file; no change tracking offered | I | Built |
| TRS-087 | DB table change tracking | PRD §6.2 | Change tracking works for a standalone table in a tracked database | I | Built |
| TRS-088 | Attribute tables stay under vector | PRD §6.2 | A vector layer's attribute table is not duplicated as a separate tabular item | V | Built |

---

## 13. Connection flowchart (PRD §7.8, FSD §12, DVS §13)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-089 | Official (foreign-key) links detected | PRD §7.8 | Formally declared FKs appear as confirmed solid-line edges | I | Built |
| TRS-090 | Smart-guessed links detected | PRD §7.8, TAD §3 | Matching eligible columns after approved prefix stripping (at least 5 distinct values on each side and ≥80% overlap) produce a dashed guessed edge; excluded internal/page columns never produce guesses | I | Built |
| TRS-091 | Confirm/reject a guessed link | FSD §12 | User can confirm or reject a guess; edge style updates immediately | V | Built |
| TRS-092 | User-added link | PRD §7.8 | User can manually declare a connection between two items on a chosen column | I+V | Built |
| TRS-093 | Node click navigates to detail page | FSD §12 | Clicking any node opens the correct layer/table/raster detail page | V | Built |
| TRS-094 | Flowchart pan/zoom/drag | FSD §12, DVS §13 | Canvas supports pan, zoom, and node dragging; layout persists in session | V | Built |
| TRS-116 | Item detail "Connections" tab | FSD §7, §12 | Every item type shows a Connections tab listing that item's flowchart links inline (connected item, both columns, official/guessed/added); each entry opens the other item; items with no links show an empty state | I+V | Built |
| TRS-117 | Spatial Knowledge Graph Engine — backend (PRD §14.1) | PRD §14.1, TAD §3.1 | Kuzu-backed graph, derived from SQLite, answers reachability/shortest-path/connected-groups correctly; rebuilds automatically after a scan/flowchart change/connection delete; "confirmed only" mode excludes unconfirmed guesses from results | U+I | Built. Merged to local `main` (`a70db42`). WFD §6 security checklist reported and passed (all 6 items, one note on the archived-dependency risk already accepted in TAD §3.1). Backend covered; the dedicated screen is tracked separately as TRS-119. |
| TRS-118 | Cross-connection relationship guessing (PRD §14.10/§7.8) | PRD §14.10, TAD §3.1 | Same matching rule as TRS-090, now also run across different connections via shared `guess_between` function; confirmed test shows no location-based matching; confirm/reject works from either side and survives rescan; includes a visual check (dashed edge to dashed-box node for the other connection) | I+V | Built. Merged to local `main` (`a70db42`) with TRS-117, same security checklist result. |
| TRS-119 | Relationship Graph screen (PRD §14.1, FSD §12.1) | PRD §14.1, FSD §12.1 | Dedicated screen renders neighborhood/shortest-path/connected-groups views correctly; "confirmed only" toggle re-queries the backend (changes actual results, not just the drawing); unavailable state (e.g. Python 3.14, no Kuzu) shows a plain message, not an error; node click navigates correctly; interim "Also related" list is removed | V | Built. Merged to local `main` (`a70db42`). Not yet browser-reviewed — part of the batch visual review still pending. |

---

## 14. App shell, settings, and global behavior (FSD §3, §13)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-095 | Sidebar + top bar persist across screens | FSD §3 | Navigation remains consistent and functional on every screen | V | Tested |
| TRS-096 | Connection switcher updates all screens | FSD §3 | The switcher shows the current database name; switching connections updates Overview, Statistics, Quality, etc. to that database | I+V | Built |
| TRS-097 | Settings persist | FSD §13, TAD §5 | AI config, connections, notification channels, appearance all save to SQLite and persist across restarts | I | Built |
| TRS-098 | Loading/empty/error/partial states — global | FSD §15, DVS §15 | Every data-bearing screen implements all required states, not just the happy path; simultaneous first requests after startup must not produce a transient local-store initialization error | V | Built |
| TRS-099 | Desktop-only layout usable at 1280px | FSD §16 | App is usable and legible at the minimum supported width | V | Built |
| TRS-100 | Keyboard accessibility for core flows | FSD §16 | Add connection, build automation, run a check are completable via keyboard | V | Built |

---

## 15. Performance, security & packaging (TAD §8, §9, §2)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-101 | Cached results load instantly | TAD §8 | Reopening a dashboard loads from SQLite cache without re-querying the source | I | Built |
| TRS-102 | Sampling on huge layers, labeled | TAD §8, DVS §12 | Large test layer is summarized by sample, clearly labeled; full run available and correctly replaces the sample result | I+V | Built |
| TRS-103 | Monitoring doesn't block user's database | TAD §8 | Confirm no long-locking queries are issued against the source database during normal monitoring | I | Built |
| TRS-104 | `pip install tarsier-geo` works cross-platform | TAD §2 | Fresh install succeeds on Linux, Windows, and macOS with no extra software | I | Built |
| TRS-105 | Port auto-detection + override | TAD §2 | With the default port busy, app starts on a free port, prints the URL, opens the browser; `--port` override works | I | Tested |
| TRS-106 | No secrets in plain text or logs | TAD §9 | Full scan of disk and logs after normal use finds no plain-text credentials | I | Built |
| TRS-107 | No unconfigured outbound traffic | TAD §9, WFD §6 | Network monitoring confirms no telemetry/phone-home traffic and permits only user-configured AI, SMTP, or webhook destinations when triggered | I | Built |
| TRS-108 | Appearance section - light mode only | FSD §2.1, §13 | Settings shows light mode as active and a disabled dark-mode option marked "Coming soon" | V | Built — **note (2026-10-13): superseded.** Both light and dark mode are now required for v1 (Manager + user decision, FSD §2 rewritten for the v2 design system). This row's "light mode only, dark disabled" test no longer matches FSD and needs rebuilding as a dual-mode toggle, not a "coming soon" badge. |
| TRS-109 | About information and in-repo links | FSD §13, TAD §4 | About shows the running version and Apache-2.0 license; LICENSE and all six project documents open from the local bundle | I+V | Built |
| TRS-110 | ArcGIS FeatureServer statistics | PRD §5, §7.2; TAD §3 | FeatureServer vector and table queries return sample-based statistics; unsupported service types show a clear unavailable message | I+V | Built |
| TRS-111 | GeoServer WFS statistics | PRD §5, §7.2; TAD §3 | WFS JSON sampling returns vector statistics; raster coverages show a clear unavailable message | I+V | Built |
| TRS-112 | Notification channel settings | FSD §13, TAD §9 | SMTP settings persist; credentials remain masked; a saved Slack or Teams webhook address is never shown again; test email provides a clear result | I+V | Built |
| TRS-113 | SMTP alert and automation email delivery | PRD §7.5-§7.6, TAD §7.5-§7.6 | A fired email alert and automation send the expected message to recipients entered on that rule/action; delivery errors are visible and secrets are not exposed | I | Built |
| TRS-114 | Webhook and chat delivery states | PRD §7.5-§7.6, TAD §7.5-§7.6 | Alerts and automations POST to configured webhook URLs; alerts and automations send to the saved Slack or Teams incoming webhook (Slack: plain text; Teams: Adaptive Card) | I+V | Built |
| TRS-115 | Global Statistics summary | PRD §7.2, FSD §8.1 | Each connection layer shows cached flag counts, and each count opens the matching layer Statistics flag; cross-layer AI query is absent | I+V | Built |

---

## 16. Validation rollup (maps to PRD §9/§11)

- **Stage 1 (internal exam) = complete** when every row in Sections 3–15 is `Passed`.
- **Stage 2 (real-user stress test)** begins only after Stage 1 is fully `Passed`. Any issue found in Stage 2 gets a new row appended here (next available ID) rather than editing an existing row, to preserve history.

**Current totals:** 118 traceable test items across 13 feature areas (115 confirmed on `main` 2026-10-13, plus TRS-117–119 for the Spatial Knowledge Graph Engine, cross-connection guessing, and its dedicated screen). 0 `Passed` — batch visual/browser review still pending. TRS-108 is flagged above as needing a rebuild now that dual light/dark mode is required.

---

## 17. Local build additions (2026-10-16)

These entries supplement the historical rollup above; none implies Stage 1 is complete.
TRS-108 now has a working saved
light/dark toggle. TRS-112/114 now support configured Slack/Teams incoming webhooks;
their historical log-only descriptions are superseded. Live delivery remains unverified.

| ID | Feature | Source | Verification | Status |
|---|---|---|---|---|
| TRS-120 | Snapshot capture, retention, comparison, schema drift | PRD §14.3–14.4 | Local frame/GeoParquet fixtures and retention tests; live DB capture and raster support remain open | Built |
| TRS-121 | Snapshot DuckDB analytics and bounding-box search | PRD §14.2, §14.6 | Parameterized filters, local geometry search, displayed query; no embedding index | Built |
| TRS-122 | Review-gated AI rules and automations | PRD §14.7, FSD §18 | API rejection before approval, UI review gate, preview without saving/delivery | Tested |
| TRS-123 | Command palette | PRD §14.8 | Cached navigation tests and browser Enter navigation/close check | Tested |
| TRS-124 | Credentials-excluded backup/restore | PRD §14.9 | Round trip, secret exclusion, paused rules, restored vault isolation | Tested |
| TRS-125 | Local request guard | PRD §14.5 | Reject foreign Origin/Host, permit same-origin local API requests | Tested |
| TRS-126 | Fail-open history logging and tracking health | TAD §6.2, FSD §10 | As a non-owner role with source-table DML only, break the history write and verify the source edit commits, a server WARNING is emitted and the existing changes API flags possible gaps. Restore logging and verify exactly one correctly attributed event for a normal edit. Verify direct log access remains denied, cancellation/deadlock/serialization errors propagate, and outdated loggers and missing row triggers produce degraded health. | I | Built |

Final local suite: 203 backend passes, 67 skips; 93 frontend passes. Windows wheel
fresh-install smoke test passed. No rows are promoted to `Passed` without the full
acceptance process.

## 18. Approved custom operators (Round 9)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-127 | Same-table custom column comparisons | PRD §7.3; TAD quality/alert methodology; FSD §9 | Verify all six compatible-column comparisons, catalog/type rejection, null/empty-string/whitespace skips on either side, persisted union-of-skips counts and sampled labels. The planted total_value/land_value flagged and skipped counts must equal independent SQL. Show the opposite-direction alert example and verify other column alert predicates still work on aligned rows. Existing operators remain unchanged; reads remain read-only within existing timeouts. | U+I | Built |
| TRS-128 | Custom text-pattern rules | PRD §7.3; TAD quality/alert methodology; FSD §9 | Verify MATCHES and DOES NOT MATCH use Python re.search and skip/count each empty form in quality results. Compare the planted ZIP flagged and skipped counts with independent SQL. Verify clear invalid-regex errors, bounded pathological evaluation, persisted counts and sampled labels. Show the quality MATCHES versus alert DOES NOT MATCH example and retain other alert semantics. | U+I | Built |
| TRS-129 | Custom IS UNIQUE constraint | PRD §7.3; TAD quality/alert methodology; FSD §9 | Verify a valueless quality rule flags every non-empty duplicate occurrence including the original; duplicate counts agree with independent SQL. Repeated null, empty-string and whitespace-only values must be skipped and never duplicate each other. Verify persisted skipped counts, mixed-rule counting and sample-limited labels. IS UNIQUE must be absent from alert choices and rejected clearly on alert create, edit, preview and engine evaluation, while remaining available for quality rules. | U+I | Built |

## 19. RC1 event replay and result provenance (Round 12)

| ID | Feature | Source | Test description | Type | Status |
|---|---|---|---|---|---|
| TRS-130 | Alert and automation event replay protection | TAD §7.1 | Repeated and concurrent evaluation makes at most one delivery attempt per rule/event pair; upgrade retains prior fire/run history and does not replay cached events. | U+I | Built |
| TRS-131 | Creation checkpoint for event rules | TAD §7.1 | A new alert or automation on a large cached history fires zero times before a later captured event, then once; reimporting the old log does not fire. No backfill exists. | U+I | Built |
| TRS-132 | Sample result labelling | FSD §6, §9 | Every sample-derived number, score, percentage, ring, quality status and alert message is labelled; zero findings in a sample use the neutral exact wording, including aggregate health. | U+V | Built |
| TRS-133 | No-PostGIS notice | FSD §5 | A database without PostGIS shows the exact spatial-features-unavailable notice and still lists readable non-spatial tables. | I+V | Built |
| TRS-134 | No-permission table state | FSD §6 | A SELECT-only role sees unreadable tables marked "no permission" instead of hidden, with an accurate count. | I+V | Built |
| TRS-135 | RC1 full-statistics guard | FSD §8, TAD §8 | Tables above 20,000 estimated rows use labelled sample statistics in the table and Overview full-check flows; per-table skips are visible, eligible runs keep the sample visible, and cached statistics stay under 64 MiB. | U+I+V | Built |

*End of FTL v1.0.*
