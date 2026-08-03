-- This project was developed with assistance from AI tools.
-- PostgreSQL schema for the Grid Resilience Operations Center.
-- Matches Section 9.1 of the implementation plan.

CREATE TABLE IF NOT EXISTS feeders (
    id                  TEXT PRIMARY KEY,
    substation_id       TEXT,
    name                TEXT,
    normal_capacity_mw  DOUBLE PRECISION,
    emergency_capacity_mw DOUBLE PRECISION,
    current_load_mw     DOUBLE PRECISION,
    peak_load_mw        DOUBLE PRECISION,
    status              TEXT DEFAULT 'energized'
);

CREATE TABLE IF NOT EXISTS assets (
    id                      TEXT PRIMARY KEY,
    asset_type              TEXT NOT NULL,
    subtype                 TEXT,
    lat                     DOUBLE PRECISION NOT NULL,
    lon                     DOUBLE PRECISION NOT NULL,
    install_year            INTEGER,
    expected_lifespan_years INTEGER,
    feeder_id               TEXT REFERENCES feeders(id),
    is_end_of_line          BOOLEAN DEFAULT FALSE,
    vegetation_clearance_m  DOUBLE PRECISION,
    last_inspection_date    DATE,
    status                  TEXT DEFAULT 'in_service',
    rated_voltage_kv        DOUBLE PRECISION,
    phase_config            TEXT,
    circuit_name            TEXT,
    protection_zone         TEXT,
    customers_downstream    INTEGER DEFAULT 0,
    rated_kva               DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS segments (
    id              TEXT PRIMARY KEY,
    feeder_id       TEXT REFERENCES feeders(id),
    from_asset_id   TEXT REFERENCES assets(id),
    to_asset_id     TEXT REFERENCES assets(id),
    conductor_type  TEXT,
    length_m        DOUBLE PRECISION,
    customers_served INTEGER DEFAULT 0,
    ampacity_a      DOUBLE PRECISION,
    status          TEXT DEFAULT 'energized'
);

CREATE TABLE IF NOT EXISTS switches (
    id                   TEXT PRIMARY KEY,
    location_asset_id    TEXT REFERENCES assets(id),
    from_feeder_id       TEXT REFERENCES feeders(id),
    to_feeder_id         TEXT REFERENCES feeders(id),
    state                TEXT DEFAULT 'open',
    transfer_capacity_mw DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS cameras (
    id                         TEXT PRIMARY KEY,
    camera_type                TEXT NOT NULL,
    asset_id                   TEXT REFERENCES assets(id),
    lat                        DOUBLE PRECISION NOT NULL,
    lon                        DOUBLE PRECISION NOT NULL,
    field_of_view              TEXT,
    status                     TEXT DEFAULT 'active',
    baseline_interval_seconds  INTEGER DEFAULT 3600,
    escalated_interval_seconds INTEGER DEFAULT 30
);

CREATE TABLE IF NOT EXISTS crews (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    skills          TEXT[],
    certifications  TEXT[],
    shift_start     TIME,
    shift_end       TIME,
    home_base_lat   DOUBLE PRECISION,
    home_base_lon   DOUBLE PRECISION,
    current_lat     DOUBLE PRECISION,
    current_lon     DOUBLE PRECISION,
    status          TEXT DEFAULT 'available'
);

-- Add columns for growth prediction (safe to re-run)
ALTER TABLE feeders ADD COLUMN IF NOT EXISTS emergency_capacity_mw DOUBLE PRECISION;
ALTER TABLE feeders ADD COLUMN IF NOT EXISTS peak_load_mw DOUBLE PRECISION;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS rated_kva DOUBLE PRECISION;
ALTER TABLE segments ADD COLUMN IF NOT EXISTS ampacity_a DOUBLE PRECISION;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_assets_feeder ON assets(feeder_id);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_segments_feeder ON segments(feeder_id);
CREATE INDEX IF NOT EXISTS idx_cameras_asset ON cameras(asset_id);
