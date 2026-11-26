# Connecting your own data

Tarsier watches a database and shows its health, statistics, quality and change
history. This guide takes you from "installed" to "my own data on screen". If you
have not yet seen Tarsier work, start with the [sample data](sample-data/README.md).

## What Tarsier does to your data

- **It only reads.** PostGIS sessions are opened read-only by the database itself.
  The one optional exception is the PostGIS *history log* (see the end of this guide),
  which you must ask for.
- **It reads gently.** Row counts and sizes come from the database's own
  statistics and quality checks read a sample (1,000 rows by default),
  and reads from PostgreSQL have a time limit. Results from a sample are labelled as such.
- **It keeps its own copy of the results** in a local file, so the screens open
  instantly and your source is not queried each time. Those results can include
  sample rows, so protect the folder as you would the data.
- **Passwords never go in that file.** They are kept in your operating system's
  credential store (or encrypted on disk where there is none), and are never shown
  again.
- **Nothing is sent anywhere** except to the AI service you choose to set up, and
  to e-mail or webhook addresses you configure for alerts.
- **The AI features are given metadata:** layer and column names, row counts, health
  scores, quality-check and change counts (some summaries include database user
  names), plus what you type. With OpenRouter that
  leaves your computer; with a local Ollama model it does not. Conversations are
  saved in the same local file (and in backups) until you delete them.

## 1. Use a read-only account

Do not connect with an administrator account. Make one that can only read.

**PostgreSQL / PostGIS** (run as the database owner):

```sql
CREATE ROLE tarsier_reader LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE mydb TO tarsier_reader;
GRANT USAGE ON SCHEMA public TO tarsier_reader;                 -- PostGIS keeps its catalog here
GRANT USAGE ON SCHEMA myschema TO tarsier_reader;               -- repeat for each schema
GRANT SELECT ON ALL TABLES IN SCHEMA myschema TO tarsier_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA myschema GRANT SELECT ON TABLES TO tarsier_reader;  -- future tables
```

Tarsier lists every table in every non-system schema that the account can see.
A table it can see but not read is shown as "no permission" instead of failing.

**Oracle:** `GRANT CREATE SESSION TO tarsier_reader;` and `GRANT SELECT` on the
tables to watch. Tarsier reads the tables owned by the account it logs in as, so
connect as the schema owner's name, or a read-only account that owns views or
synonyms of what you want to see.

**SQL Server:** add a login as a user of the database, then
`ALTER ROLE db_datareader ADD MEMBER tarsier_reader;` and
`GRANT VIEW DATABASE STATE TO tarsier_reader;` (for sizes and row counts). SQL
Server has no read-only session switch, so the account's permissions are your
safeguard.

**ArcGIS Enterprise / GeoServer:** use an account (or ArcGIS token) that can only
view the services. GeoServer's REST interface must be available to it.

## 2. Add the connection

Open Tarsier, click **Add connection**, choose the type, and fill in the form.
Tarsier tests the connection before saving it.

| Type | What to enter |
| --- | --- |
| **PostGIS / PostgreSQL** | Host, port (usually 5432), database, username, password |
| **Oracle Spatial** | Host, port (usually 1521), service name, username, password |
| **SQL Server** | Host, port (usually 1433), database, username, password |
| **Files in folders** | The folder path. Tarsier looks inside it (and below) for shapefiles, GeoPackages, GeoTIFFs and CSV files. Files are only read, never changed, and have no change tracking |
| **ArcGIS Enterprise** | The REST services address, normally ending `/arcgis/rest/services`. The password box is an optional token |
| **GeoServer** | The base address, for example `http://server:8080/geoserver`, plus username and password |

Use the address the database server answers on from **this** computer. A database
on another machine must accept connections from here (firewall, and for PostgreSQL
`listen_addresses` and `pg_hba.conf`).

## 3. Run the first check

Open the connection's **Overview** and choose **Run full check**. On a big database
this takes a while; you can leave the page and come back, and the result is kept.

- Numbers marked `~` are the database's estimates. If a table shows none, run
  `ANALYZE` on it (PostgreSQL) so the database has statistics to give.
- A layer or check labelled **sample-based** was computed from a sample, not every
  row. Very large tables are always sampled; the limits can be raised, see
  [Working with large databases](README.md#working-with-large-databases).
- A table you cannot read is listed as "no permission".

## 4. Watch for changes (optional)

Tarsier can record who changed what, on PostGIS only. Open **Changes** and pick one:

- **Install the history log.** Adds a small `tarsier_changes` schema and triggers to
  your tables. This is the only time Tarsier writes to your database, it needs an
  account that may create a schema and triggers, and it happens only when you press
  the button. Use a database account other than your read-only one.
- **Use polling.** Compares snapshots of small tables on a schedule. It needs no
  changes to the database, but can miss changes between checks and skips large tables.

## If something goes wrong

| What you see | What it usually means |
| --- | --- |
| "the username or password … was rejected" | Wrong credentials, or the account may not log in from this computer |
| "the database did not respond within the time limit" | The host or port is wrong, a firewall is in the way, or the database is very busy |
| "doesn't have permission to read this data" | The account lacks `SELECT` on that table; ask for it, or ignore the table |
| "the port must be a number" | The port field contains something other than digits |
| "did not answer as an ArcGIS REST services directory" (or GeoServer) | The address is wrong; open it in a browser and check you see the service list |
| "Tarsier accepts local requests only" | Open Tarsier at `localhost` or `127.0.0.1`, not at a network name |
| A connection no longer works after a restore | Backups leave passwords out on purpose; edit the connection in Settings and enter the password again |

To stop monitoring a database, open **Settings**, find it under **Connections** and
choose **Remove**. That removes Tarsier's saved results and the stored password; it
does not touch your database. If you installed the history log, remove it from the
database yourself, as its owner:

```sql
DROP EVENT TRIGGER IF EXISTS tarsier_ddl_logger;
DROP SCHEMA tarsier_changes CASCADE;
```
