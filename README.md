# Tarsier

A health record ("Kundali") for a geospatial database: one place to see statistics,
quality issues, and change history for vector, raster, and tabular data — without
writing SQL. **Read-only on user data in v1.**
The only write is the optional PostGIS change-tracking trigger, installed only with explicit permission.

## What it does

- Overview with a health score for every layer and table
- Statistics and quality checks (invalid geometry, overlaps, gaps, missing IDs, your own rules)
- Change history for PostGIS, alerts and automations
- Connection maps, raster details, local snapshots
- Optional AI help with a local Ollama model or OpenRouter: ask questions about a
  connection, with saved conversations. Small models can be wrong, so check what matters.

It connects to PostGIS / PostgreSQL, Oracle Spatial, SQL Server, folders of files
(shapefile, GeoPackage, GeoTIFF, CSV), ArcGIS Enterprise and GeoServer.

## Install

```bash
pip install tarsier-geo
tarsier-geo start
```

You need Python 3.11 or newer. The install check passed on Python 3.11 to 3.14 on Windows.

If pip cannot find a version, run `pip install --pre tarsier-geo`. This release candidate is
tested on Windows; Linux and macOS are not yet qualified.

A pip install from a Git link does not include the built web interface.

We recommend installing in a virtual environment. On Windows, run these first:

```powershell
py -m venv .venv
.venv\Scripts\activate
```

Your browser opens on `http://localhost:8731` (or the next free port;
`start --port 8050` picks one, `--no-browser` stops it opening). Stop Tarsier with
Ctrl+C, or from another terminal with `tarsier-geo stop`.

On Python 3.14 the Relationship Graph's path queries are unavailable and that screen
shows the connection flowchart instead.

## Install from source (for contributors)

You need [Git](https://git-scm.com/), [Python](https://www.python.org/downloads/)
3.11 (recommended) or 3.14, and [Node.js](https://nodejs.org/) 24 LTS. Windows is tested
for this release candidate; Linux and macOS are not yet qualified. Continuous integration (CI)
is planned.

```bash
git clone https://github.com/euler-cartan/tarsier-geo.git
cd tarsier-geo
```

**Windows (PowerShell).** For Python 3.14 change `3.11` and `py311` below.

```powershell
py -3.11 -m venv .venv
npm ci
npm run build --workspace=frontend
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-py311.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\tarsier-geo.exe start
```

**Linux or macOS** (not yet qualified). The lock files are for
Windows, so install without them:

```bash
python3.11 -m venv .venv
npm ci
npm run build --workspace=frontend
.venv/bin/python -m pip install -e .
.venv/bin/tarsier-geo start
```

Build the frontend before installing the Python package, because the package
includes it. On a bare Linux container image, install the system library `libexpat1` first.

## Try it on sample data

[`sample-data/`](https://github.com/euler-cartan/tarsier-geo/blob/main/sample-data/README.md) holds a small, invented set of databases and
files. With Docker it is two commands and four connections appear in Tarsier, so you
can try every screen without touching real data. The sample data is in the
[GitHub repository](https://github.com/euler-cartan/tarsier-geo), not in the pip package: download the repository to use it.

## Connect your own data

See [Connecting your own data](https://github.com/euler-cartan/tarsier-geo/blob/main/CONNECTING_YOUR_DATA.md): making a read-only account,
adding each type of connection, and what to expect on a large database.

## Working with large databases

Every read of your data is bounded, so Tarsier can sit next to a production
database without disturbing it. Layer extents come from the database's own
statistics (run `ANALYZE` on a table whose extent shows as "Not available"),
change history is pulled and shown in pages, and reads above a cap are
labelled as samples. The caps can be raised with environment variables set
before `tarsier-geo start`:

| Variable | Default | What it bounds |
| --- | --- | --- |
| `TARSIER_FULL_SCAN_MAX_ROWS` | 100,000 | Rows read by a full quality run |
| `TARSIER_SNAPSHOT_MAX_ROWS` | 250,000 | Largest table captured in a snapshot |
| `TARSIER_POLLING_MAX_ROWS` | 250,000 | Largest table tracked by polling |
| `TARSIER_POLLING_INTERVAL_MINUTES` | 15 | Minimum gap between polling passes |
| `TARSIER_CHANGE_SYNC_MAX_PER_RUN` | 50,000 | History-log rows pulled per sync |
| `TARSIER_EVENT_EVALUATION_WINDOW` | 20,000 | Newest changes an alert or automation pass reads |

Connect with a database role that has only `SELECT` (and `USAGE` on its
schemas). Polling-based change tracking covers small tables only; use the
history log for large ones.

## Backups

Stop Tarsier before running `tarsier-geo backup PATH.zip`. The archive contains
Tarsier's SQLite state and snapshots, excludes credentials, and pauses restored
alerts and automations. It does not back up the live source databases.

To restore, set `TARSIER_HOME` to an empty directory and run
`tarsier-geo restore PATH.zip`. Re-enter connection credentials, AI configuration,
and notification settings before resuming monitoring. Keep the archive private:
snapshots and cached results contain source data even though credentials are excluded.

## Known limits

v1.0.0-rc1 is a release candidate. Windows and PostGIS are the best-tested combination. Oracle, SQL Server, and GeoServer have had less testing; ArcGIS was tested only against a mock. Sample results are labelled and are not full checks.

Plain-English questions are answered by a model you configure; answer accuracy depends on that model. Review drafts before saving them.

Full statistics are available only for tables up to 20,000 rows in this release; larger tables show labelled sample statistics. Quality checks on very large tables can still take a long time.

Alerts to Microsoft Teams have not yet been tested against real Teams. "Layer not updated" (freshness) alerts send one message per layer. Schedules run in UTC. Scheduled checks need Tarsier to be running, and use samples on large tables: they are not the same as **Run full check**.

Do not use rc1 as the only safeguard for critical decisions; report problems through GitHub Issues, and security problems privately.

## Security

Tarsier has no login. It listens on `127.0.0.1` only and trusts the person at
that machine; it refuses requests addressed to any other host name and requests
made by other web sites open in the same browser. Do not put it behind a
reverse proxy or expose its port to a network. Passwords, tokens and API keys
are kept in the operating system's credential store (or encrypted on disk where
there is none), never in the settings database and never returned by the API.

See [`SECURITY.md`](https://github.com/euler-cartan/tarsier-geo/blob/main/SECURITY.md) for how to report a vulnerability.

## Contributors

- Neel Savalia ([@ineelsavalia](https://github.com/ineelsavalia))

## License

Apache-2.0 — see [`LICENSE`](https://github.com/euler-cartan/tarsier-geo/blob/main/LICENSE).
