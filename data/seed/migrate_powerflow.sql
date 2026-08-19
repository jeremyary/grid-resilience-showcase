-- This project was developed with assistance from AI tools.
-- Migration: add powerflow columns and conductor_types table.
-- Safe to re-run (IF NOT EXISTS / idempotent UPSERTs).

-- Transformer electrical parameters
ALTER TABLE assets ADD COLUMN IF NOT EXISTS vk_percent DOUBLE PRECISION;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS vkr_percent DOUBLE PRECISION;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS i0_percent DOUBLE PRECISION;
ALTER TABLE assets ADD COLUMN IF NOT EXISTS pfe_kw DOUBLE PRECISION;

-- Conductor types reference table
CREATE TABLE IF NOT EXISTS conductor_types (
    name        TEXT PRIMARY KEY,
    r_ohm_per_km    DOUBLE PRECISION NOT NULL,
    x_ohm_per_km    DOUBLE PRECISION NOT NULL,
    c_nf_per_km     DOUBLE PRECISION NOT NULL,
    max_i_ka        DOUBLE PRECISION NOT NULL
);

INSERT INTO conductor_types (name, r_ohm_per_km, x_ohm_per_km, c_nf_per_km, max_i_ka)
VALUES ('ACSR_4/0', 0.368, 0.243, 10.0, 0.340),
       ('ACSR_1/0', 0.696, 0.274, 10.0, 0.230)
ON CONFLICT (name) DO NOTHING;

-- Set electrical params on existing pad-mount distribution transformers
UPDATE assets SET vk_percent = 5.75, vkr_percent = 1.0, i0_percent = 0.5,
    pfe_kw = ROUND((rated_kva * 0.003)::numeric, 2)
WHERE asset_type = 'transformer' AND subtype = 'pad_mount' AND vk_percent IS NULL;

-- Substation power transformers (insert if missing)
INSERT INTO assets (id, asset_type, subtype, lat, lon, install_year, expected_lifespan_years,
    feeder_id, is_end_of_line, status, rated_voltage_kv, phase_config, circuit_name,
    protection_zone, customers_downstream, rated_kva, vk_percent, vkr_percent, i0_percent, pfe_kw)
VALUES
    ('T-SUB-A', 'transformer', 'power_transformer', 36.0958, -79.438, 1978, 45,
     NULL, FALSE, 'in_service', 115.0, '3P', 'Burlington Sub A', 'ZA-1', 6200, 20000,
     8.0, 0.5, 0.3, 20.0),
    ('T-SUB-B', 'transformer', 'power_transformer', 36.098, -79.502, 1982, 45,
     NULL, FALSE, 'in_service', 115.0, '3P', 'Mebane Sub B', 'ZB-1', 5800, 20000,
     8.0, 0.5, 0.3, 20.0)
ON CONFLICT (id) DO NOTHING;

-- Transformer-to-pole tap segments (insert if missing)
INSERT INTO segments (id, feeder_id, from_asset_id, to_asset_id, conductor_type, length_m, customers_served, ampacity_a, status)
VALUES
    ('SEG-081', 'F-11', 'P-004', 'T-001', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-082', 'F-11', 'P-010', 'T-002', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-083', 'F-11', 'P-001', 'T-008', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-084', 'F-11', 'P-006', 'T-011', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-085', 'F-11', 'P-010', 'T-012', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-086', 'F-11', 'P-005', 'T-013', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-087', 'F-12', 'P-028', 'T-003', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-088', 'F-12', 'P-040', 'T-004', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-089', 'F-12', 'P-050', 'T-005', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-090', 'F-12', 'P-033', 'T-014', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-091', 'F-12', 'P-037', 'T-015', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-092', 'F-12', 'P-043', 'T-016', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-093', 'F-12', 'P-047', 'T-017', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-094', 'F-12', 'P-052', 'T-018', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-095', 'F-13', 'P-060', 'T-006', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-096', 'F-13', 'P-066', 'T-007', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-097', 'F-13', 'P-062', 'T-019', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-098', 'F-13', 'P-065', 'T-020', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-099', 'F-13', 'P-058', 'T-021', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-100', 'F-13', 'P-067', 'T-022', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-101', 'F-14', 'P-071', 'T-009', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-102', 'F-14', 'P-077', 'T-010', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-103', 'F-14', 'P-073', 'T-023', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-104', 'F-14', 'P-076', 'T-024', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-105', 'F-14', 'P-079', 'T-025', 'ACSR_1/0', 10, 0, 230, 'energized'),
    ('SEG-106', 'F-14', 'P-080', 'T-026', 'ACSR_1/0', 10, 0, 230, 'energized')
ON CONFLICT (id) DO NOTHING;
