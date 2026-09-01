-- This project was developed with assistance from AI tools.
-- Adds the mitigation_costs reference table and seeds planning-level cost ranges.
-- Safe to re-run (creates only if absent, seeds only when empty).

CREATE TABLE IF NOT EXISTS mitigation_costs (
    mitigation_type TEXT NOT NULL,
    kva_max         DOUBLE PRECISION,
    cost_low        INTEGER NOT NULL,
    cost_high       INTEGER NOT NULL
);

INSERT INTO mitigation_costs (mitigation_type, kva_max, cost_low, cost_high)
SELECT * FROM (VALUES
    ('transformer_upgrade',  500::double precision, 25000,  45000),
    ('transformer_upgrade',  1000,                  45000,  70000),
    ('transformer_upgrade',  NULL,                  70000,  120000),
    ('parallel_transformer', 500,                   50000,  80000),
    ('parallel_transformer', 1000,                  80000,  120000),
    ('parallel_transformer', NULL,                  120000, 180000),
    ('load_transfer',        NULL,                  10000,  30000)
) AS v(mitigation_type, kva_max, cost_low, cost_high)
WHERE NOT EXISTS (SELECT 1 FROM mitigation_costs);
