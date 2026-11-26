-- Minimal seed for TRS-001: one vector layer, one plain table.
-- Loaded into the disposable `tarsier-test-postgis` container (see README "Testing").

CREATE TABLE water_mains (
    id SERIAL PRIMARY KEY,
    material TEXT,
    diameter_mm INTEGER,
    geom geometry(LineString, 4326)
);
INSERT INTO water_mains (material, diameter_mm, geom) VALUES
    ('PVC', 150, ST_GeomFromText('LINESTRING(-0.1 51.5, -0.11 51.51)', 4326)),
    ('Cast Iron', 200, ST_GeomFromText('LINESTRING(-0.12 51.52, -0.13 51.53)', 4326));

CREATE TABLE inspection_log (
    id SERIAL PRIMARY KEY,
    inspector TEXT,
    inspected_at TIMESTAMP,
    notes TEXT
);
INSERT INTO inspection_log (inspector, inspected_at, notes) VALUES
    ('A. Patel', '2026-01-10 09:00', 'Routine check, no issues'),
    ('B. Khan', '2026-02-02 14:30', 'Minor corrosion noted');

-- Without this, pg_class.reltuples stays at -1 ("never analyzed") until
-- autovacuum gets around to it, which describe_item() correctly reports
-- as "no estimate available" rather than guessing — but that makes the
-- row_count test flaky depending on timing. Analyze explicitly instead.
ANALYZE water_mains;
ANALYZE inspection_log;
