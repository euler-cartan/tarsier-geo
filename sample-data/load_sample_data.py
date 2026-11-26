#!/usr/bin/env python
"""Load Tarsier's invented sample data into a PostGIS server you control.

Everything here is made up: there is no real person, address or organisation in
it. It builds three small databases so you can try every screen of Tarsier:

    <prefix>            vectors, tables, rasters, planted quality problems
    <prefix>_partner    a second source whose columns link to the first
    <prefix>_nospatial  plain PostgreSQL with no PostGIS at all

and two read-only roles, `<prefix>_ro` (reads everything) and `<prefix>_limited`
(cannot read one table, to show how Tarsier reports missing permission).

Use a throw-away PostGIS server, not one that holds real data. The administrator
you connect with must be a superuser (PostGIS is installed into each database).

    python sample-data/load_sample_data.py --port 55432 --admin-password ...

Add --add-to-tarsier to also create the four connections in a running Tarsier,
so there is nothing to type. Run it from a Python environment that has psycopg
installed (the Tarsier source install provides it).
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import os
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
from psycopg import sql

HERE = Path(__file__).resolve().parent
CX, CY = 182365.93036454797, 173064.94324167745  # centre of the invented city (EPSG:3968)

# database suffix, SQL file, schemas the read-only roles may see
DATABASES = (
    ("", "main", ("sample", "qa", "transit", "rasters", "public")),
    ("_partner", "partner", ("permits", "field_ops")),
    ("_nospatial", "nospatial", ("public",)),
)

ROADS_SQL = """
INSERT INTO sample.roads_300k
SELECT i, format('SRC-%s', i),
  CASE WHEN i%3=0 THEN 'LOCAL' WHEN i%3=1 THEN 'COLLECTOR' ELSE 'ARTERIAL' END,
  format('Demo Street %s', ((i-1)/2)::int),
  CASE WHEN i%2=1
    THEN ST_MakeLine(ST_MakePoint({cx}+(((i-1)/2/1000)::int-75)*10, {cy}+(((i-1)/2%1000)::int-500)*10),
                     ST_MakePoint({cx}+(((i-1)/2/1000)::int-75)*10+10, {cy}+(((i-1)/2%1000)::int-500)*10))
    ELSE ST_MakeLine(ST_MakePoint({cx}+(((i-2)/2%1000)::int-500)*10, {cy}+(((i-2)/2/1000)::int-75)*10),
                     ST_MakePoint({cx}+(((i-2)/2%1000)::int-500)*10+10, {cy}+(((i-2)/2/1000)::int-75)*10))
  END
FROM generate_series(1, 300000) i
"""

EXPECTED_ROWS = {
    "": {"sample.points_3k": 3000, "sample.roads_300k": 300000, "sample.parcels_25k": 25000,
         "sample.buildings_5k": 5000, "qa.property_sample": 20000, "qa.wide_records_5k": 5000,
         "rasters.landcover_tile": 1, "rasters.dem_missing_meta": 1},
    "_partner": {"permits.building_permits": 3061, "permits.permit_history": 1200,
                 "field_ops.stop_inspections": 300, "field_ops.utility_poles": 400},
    "_nospatial": {"public.sample_values": 250, "public.unicode_lookup": 8},
}


def connect(args, dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        host=args.host, port=args.port, dbname=dbname, user=args.admin_user,
        password=args.admin_password or None, connect_timeout=10, autocommit=True,
        application_name="tarsier-sample-loader",
    )


def create_roles(args, names: list[str]) -> str | None:
    """Create the two roles if they are missing. Returns the password used for new ones."""
    password = args.reader_password or os.environ.get("TARSIER_SAMPLE_PASSWORD") or secrets.token_urlsafe(18)
    created = False
    with connect(args, "postgres") as conn:
        for role in names:
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            if exists:
                print(f"  role {role} already exists; its password is unchanged")
                continue
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Identifier(role), sql.Literal(password)))
            created = True
            print(f"  created role {role}")
    return password if created else None


def create_database(args, name: str) -> None:
    with connect(args, "postgres") as conn:
        if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            if not args.recreate:
                sys.exit(f"Database {name!r} already exists. Use --recreate to replace it, or --prefix to pick other names.")
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))


def make_rasters(conn) -> bool:
    """The two small rasters are loaded from the same files you can add as a Files connection.

    Returns False (and loads nothing) on a server that does not allow PostGIS to read GeoTIFF files.
    """
    files = HERE / "files"
    try:
        # PostGIS ships with every GDAL format switched off. A superuser may switch GeoTIFF on for this session.
        conn.execute("SET postgis.gdal_enabled_drivers = 'GTiff'")
        conn.execute("SELECT ST_FromGDALRaster(%s)", ((files / "dem_invented_missing_metadata.tif").read_bytes(),))
    except psycopg.Error as exc:
        print(f"  skipped the two raster tables: this server will not let PostGIS read GeoTIFF files ({str(exc).splitlines()[0]})")
        return False
    # The dump carries the checks of the original, larger raster; drop them and let PostGIS describe the new one.
    conn.execute("""
        DO $$ DECLARE r record; BEGIN
          FOR r IN SELECT conrelid::regclass AS t, conname FROM pg_constraint
                   WHERE conrelid IN ('rasters.landcover_tile'::regclass, 'rasters.dem_missing_meta'::regclass)
                     AND conname LIKE 'enforce\\_%' LOOP
            EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.t, r.conname);
          END LOOP; END $$""")
    conn.execute("INSERT INTO rasters.landcover_tile VALUES (1, ST_FromGDALRaster(%s, 5070), 2021, 'invented')",
                 ((files / "landcover_invented.tif").read_bytes(),))
    conn.execute("INSERT INTO rasters.dem_missing_meta VALUES (1, ST_FromGDALRaster(%s, 26918), 'INVENTED-TILE-01')",
                 ((files / "dem_invented_missing_metadata.tif").read_bytes(),))
    # Deliberately no constraints on dem_missing_meta: it shows how Tarsier handles a raster that lacks metadata.
    conn.execute("SELECT AddRasterConstraints('rasters'::name, 'landcover_tile'::name, 'rast'::name)")
    return True


def grant(conn, db_name: str, schemas: tuple[str, ...], ro: str, limited: str, main: bool) -> None:
    for schema in schemas:
        conn.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
    for role in (ro, limited):
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db_name), sql.Identifier(role)))
        for schema in schemas:
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(role)))
    if main:  # the table the "limited" role must not read
        conn.execute(sql.SQL("REVOKE SELECT ON qa.permission_denied FROM {}").format(sql.Identifier(limited)))


def load_database(args, suffix: str, short: str, schemas: tuple[str, ...], ro: str, limited: str) -> dict[str, int]:
    name = args.prefix + suffix
    rasters_loaded = False
    print(f"\nLoading {name} ...")
    create_database(args, name)
    dump = gzip.open(HERE / "sql" / f"{short}.sql.gz", "rt", encoding="utf-8").read()
    with connect(args, name) as conn:
        try:
            conn.execute(dump)
        except psycopg.errors.InsufficientPrivilege as exc:
            sys.exit(f"The administrator account needs to be a PostgreSQL superuser to install PostGIS: {exc}")
        except psycopg.errors.FeatureNotSupported as exc:
            sys.exit(f"This server does not have PostGIS available. Install the PostGIS extension first: {exc}")
        # The dump empties the search path for its own statements; restore it for ours.
        conn.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
        if short == "main":
            print("  generating the 300,000-row road layer (this takes a little while) ...")
            conn.execute(ROADS_SQL.format(cx=CX, cy=CY))
            rasters_loaded = make_rasters(conn)
        grant(conn, name, schemas, ro, limited, main=short == "main")
        conn.execute("ANALYZE")
        counts = {}
        for key in EXPECTED_ROWS[suffix]:
            if key.startswith("rasters.") and not rasters_loaded:
                continue
            schema, table = key.split(".")
            counts[key] = conn.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(schema), sql.Identifier(table))).fetchone()[0]
    return counts


def add_to_tarsier(url: str, host: str, port: int, prefix: str, role: str, password: str) -> None:
    """Create the four sample connections in a running Tarsier through its local API."""
    base = url.rstrip("/") + "/api/connections"

    def call(method: str, body: dict | None = None):
        request = urllib.request.Request(
            base, method=method, data=json.dumps(body).encode() if body else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    try:
        existing = {c["name"] for c in call("GET")}
    except (urllib.error.URLError, OSError) as exc:
        sys.exit(f"Could not reach Tarsier at {url} ({exc}). Start it with `tarsier-geo start`, "
                 "or pass its address with --add-to-tarsier http://127.0.0.1:PORT")
    tag = "" if prefix == "tarsier_sample" else f" ({prefix})"
    wanted = [(f"Sample city{tag}", "postgis", {"host": host, "port": port, "database": prefix, "username": role}, password),
              (f"Sample partner{tag}", "postgis", {"host": host, "port": port, "database": prefix + "_partner", "username": role}, password),
              (f"Sample without PostGIS{tag}", "postgis", {"host": host, "port": port, "database": prefix + "_nospatial", "username": role}, password),
              ("Sample files", "files", {"folder": str(HERE / "files")}, None)]
    print()
    for name, kind, config, secret in wanted:
        if name in existing:
            print(f"  already in Tarsier: {name}")
            continue
        try:
            call("POST", {"name": name, "type": kind, "config": config, "password": secret})
            print(f"  added to Tarsier: {name}")
        except urllib.error.HTTPError as exc:
            detail = json.load(exc).get("detail", exc.reason) if exc.fp else exc.reason
            print(f"  could not add {name}: {detail}")


def print_details(args, host: str, port: int, password: str | None) -> None:
    print("\nAdd these connections in Tarsier (Add connection > PostGIS / PostgreSQL):\n")
    print(f"  host {host}   port {port}")
    for suffix, _short, _schemas in DATABASES:
        print(f"  database {args.prefix + suffix}")
    print(f"  user {args.prefix}_ro (reads everything)  or  {args.prefix}_limited (cannot read qa.permission_denied)")
    print(f"  password {password if password else '(the existing password of that role)'}")
    folder = "the sample-data/files folder of this repository" if os.environ.get("TARSIER_SAMPLE_IN_DOCKER") else HERE / "files"
    print(f"\n  Files connection (Add connection > Files in folders): {folder}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--admin-user", default="postgres", help="a PostgreSQL superuser (default: postgres)")
    parser.add_argument("--admin-password", default=os.environ.get("PGPASSWORD"),
                        help="its password (default: the PGPASSWORD variable, or you are asked)")
    parser.add_argument("--prefix", default="tarsier_sample", help="name prefix for the databases and roles")
    parser.add_argument("--reader-password", help="password for the new read-only roles (default: generated and shown)")
    parser.add_argument("--recreate", action="store_true", help="drop and rebuild databases that already exist")
    parser.add_argument("--add-to-tarsier", nargs="?", const="http://127.0.0.1:8731", metavar="URL",
                        help="also create the sample connections in a running Tarsier (default address %(const)s)")
    parser.add_argument("--skip-load", action="store_true",
                        help="the databases already exist (for example from Docker); only print details / add to Tarsier")
    parser.add_argument("--advertise-host", help="host to show in the connection details (default: --host)")
    parser.add_argument("--advertise-port", type=int, help="port to show in the connection details (default: --port)")
    args = parser.parse_args()
    shown_host, shown_port = args.advertise_host or args.host, args.advertise_port or args.port
    if args.skip_load:
        password = args.reader_password or os.environ.get("TARSIER_SAMPLE_PASSWORD")
        if not password:
            sys.exit("--skip-load needs --reader-password (or TARSIER_SAMPLE_PASSWORD): the password of the sample roles.")
        print_details(args, shown_host, shown_port, password)
        if args.add_to_tarsier:
            add_to_tarsier(args.add_to_tarsier, shown_host, shown_port, args.prefix, f"{args.prefix}_ro", password)
        return
    if args.admin_password is None and not os.environ.get("PGPASSFILE"):
        args.admin_password = getpass.getpass(f"Password for {args.admin_user}@{args.host}:{args.port}: ")

    ro, limited = f"{args.prefix}_ro", f"{args.prefix}_limited"
    print(f"Loading the Tarsier sample data into {args.host}:{args.port} (prefix {args.prefix!r})")
    try:
        password = create_roles(args, [ro, limited])
        results = {}
        for suffix, short, schemas in DATABASES:
            results[suffix] = load_database(args, suffix, short, schemas, ro, limited)
    except psycopg.OperationalError as exc:
        sys.exit(f"Could not connect to the PostgreSQL server: {exc}")

    bad = [f"{args.prefix}{s}.{k}: expected {EXPECTED_ROWS[s][k]}, found {n}"
           for s, counts in results.items() for k, n in counts.items() if n != EXPECTED_ROWS[s][k]]
    if bad:
        sys.exit("Row counts do not match:\n  " + "\n  ".join(bad))

    print("\nDone.")
    print_details(args, shown_host, shown_port, password)
    if args.add_to_tarsier:
        if password:
            add_to_tarsier(args.add_to_tarsier, shown_host, shown_port, args.prefix, ro, password)
        else:
            print("\nThe sample roles already existed, so their password is unknown here. "
                  "Re-run with --reader-password, or add the connections by hand.")


if __name__ == "__main__":
    main()
