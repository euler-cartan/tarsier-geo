# Tarsier sample data

A small, invented set of databases and files for trying every part of Tarsier
without pointing it at real data. Nothing here describes a real place, person or
organisation; every name, address and value was generated. About 3 MB in the
repository; the large tables are generated when you load it.

Run the commands below from the Tarsier folder. Where they say `python`, use the
Python that Tarsier was installed into: `.\.venv\Scripts\python.exe` on Windows,
`.venv/bin/python` on Linux or macOS.

## Easiest: Docker and two commands

You need [Docker](https://www.docker.com/) and a running Tarsier (`tarsier-geo start`).

```bash
docker compose -f sample-data/docker-compose.yml up -d
```

This downloads a throw-away PostGIS server and loads the data into it (about a
minute the first time). It listens only on your own computer. When
`docker compose -f sample-data/docker-compose.yml logs loader` ends with `Done.`,
add everything to Tarsier in one go:

```bash
python sample-data/load_sample_data.py --skip-load --port 55432 --reader-password tarsier-sample --add-to-tarsier
```

Four connections appear in Tarsier: **Sample city**, **Sample partner**, **Sample
without PostGIS** and **Sample files**. If Tarsier is not on its default address
(`http://127.0.0.1:8731`), give its address: `--add-to-tarsier http://127.0.0.1:8732`.
Run the same command again at any time; it never adds duplicates.

To remove the sample server and its data: `docker compose -f sample-data/docker-compose.yml down -v`.
(If port 55432 is taken, set `TARSIER_SAMPLE_PORT` first and use that port above.)

## Without Docker: use a PostGIS server you already have

You need a PostgreSQL server with PostGIS that **holds nothing you care about**,
and an administrator account that is a superuser. From a Tarsier source install:

```bash
python sample-data/load_sample_data.py --host 127.0.0.1 --port 5432 --admin-user postgres --add-to-tarsier
```

It asks for the administrator password (or reads `PGPASSWORD`), builds the data in
about 15 seconds, and creates the four connections in the running Tarsier. Leave
out `--add-to-tarsier` to just print the details and type them in yourself
(Add connection, then PostGIS / PostgreSQL). `--prefix NAME` changes the database
and role names, `--recreate` rebuilds ones that already exist, and
`--reader-password` sets the password of the new roles (otherwise a random one is
shown once).

## What you get

| Database | What it is |
| --- | --- |
| `tarsier_sample` | The main source: vector layers, tables, two rasters and a set of planted problems |
| `tarsier_sample_partner` | A second source whose columns match the first, for the cross-connection graph |
| `tarsier_sample_nospatial` | Plain PostgreSQL without PostGIS, to see how Tarsier behaves there |

Two roles are created for each: `tarsier_sample_ro` reads everything, and
`tarsier_sample_limited` cannot read `qa.permission_denied`, so you can see how
Tarsier reports a table you lack permission for. (With Docker the password of both
is `tarsier-sample`.)

The `files/` folder holds a shapefile, a GeoPackage, a GeoJSON, a CSV and two
small GeoTIFFs. It is the **Sample files** connection.

## Things to try

- **Overview and health:** open Sample city and run the full check. Layers
  use four projections (EPSG 3968, 4326, 5070 and 26918), so the projection
  check has something to say. `sample.roads_300k` has 300,000 rows, so its
  statistics are clearly labelled as sample-based.
- **Quality checks:** the `qa` schema holds layers made to fail a check:
  `duplicate_polygons`, `gap_polygons`, `dangle_lines`, `natural_invalid_case`
  (an invalid geometry), `empty_geometries`, `sequence_ids` (seven missing IDs),
  `stale_assets` (old data) and `inspections_empty` (an empty table).
- **Statistics:** `qa.category_variants` has inconsistent spellings,
  `qa.property_sample` has missing and duplicated values, and
  `qa.unicode_names` has non-English text.
- **Custom rules:** try a rule on `qa.custom_rule_rows`.
- **Relationships:** with Sample partner added too, scan for links. Its permit
  PINs match `qa.property_sample`.
- **Permissions:** connect once as `tarsier_sample_limited`.
- **No PostGIS:** open Sample without PostGIS.
- **Rasters:** open `rasters.landcover_tile`, and `rasters.dem_missing_meta`,
  which is deliberately missing its metadata.
- **Change tracking:** on a connection whose role may create a schema, install the
  history log, edit a few rows in `psql`, then watch the Changes screen. The
  read-only roles cannot install it.
- **Snapshots and AI:** take a snapshot, or set up a local model in Settings and
  ask a question in plain English about `sample.buildings_5k`.

When you are done exploring, connect your own data: see
[Connecting your own data](../CONNECTING_YOUR_DATA.md).

## Files

| Path | Contents |
| --- | --- |
| `docker-compose.yml` | The one-command PostGIS server |
| `load_sample_data.py` | The loader, and the "add to Tarsier" helper |
| `sql/` | The three databases as compressed SQL (no data from any real source) |
| `files/` | Demo vector, table and raster files |
