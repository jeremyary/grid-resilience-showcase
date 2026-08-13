#!/usr/bin/env python3
# This project was developed with assistance from AI tools.

"""Load seed JSON data into PostgreSQL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

SEED_DIR = Path(__file__).parent
DB_DSN = "postgresql://gridops:gridops@localhost:5432/gridops"


def _load_json(filename: str) -> list[dict]:
    path = SEED_DIR / filename
    if not path.exists():
        print(f"Skipping {filename} — file not found")
        return []
    with open(path) as f:
        return json.load(f)


def _insert_feeders(cur: psycopg.Cursor) -> int:
    rows = _load_json("feeders.json")
    for r in rows:
        cur.execute(
            """INSERT INTO feeders (id, substation_id, name, normal_capacity_mw,
               emergency_capacity_mw, current_load_mw, peak_load_mw, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                r["id"],
                r["substation_id"],
                r["name"],
                r["normal_capacity_mw"],
                r.get("emergency_capacity_mw"),
                r["current_load_mw"],
                r.get("peak_load_mw"),
                r["status"],
            ),
        )
    return len(rows)


def _insert_assets(cur: psycopg.Cursor) -> int:
    rows = _load_json("assets.json")
    for r in rows:
        cur.execute(
            """INSERT INTO assets (id, asset_type, subtype, lat, lon, install_year,
               expected_lifespan_years, feeder_id, is_end_of_line,
               vegetation_clearance_m, last_inspection_date, status,
               rated_voltage_kv, phase_config, circuit_name, protection_zone,
               customers_downstream, rated_kva,
               vk_percent, vkr_percent, i0_percent, pfe_kw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (
                r["id"],
                r["asset_type"],
                r.get("subtype"),
                r["lat"],
                r["lon"],
                r.get("install_year"),
                r.get("expected_lifespan_years"),
                r.get("feeder_id"),
                r.get("is_end_of_line", False),
                r.get("vegetation_clearance_m"),
                r.get("last_inspection_date"),
                r.get("status", "in_service"),
                r.get("rated_voltage_kv"),
                r.get("phase_config"),
                r.get("circuit_name"),
                r.get("protection_zone"),
                r.get("customers_downstream", 0),
                r.get("rated_kva"),
                r.get("vk_percent"),
                r.get("vkr_percent"),
                r.get("i0_percent"),
                r.get("pfe_kw"),
            ),
        )
    return len(rows)


def _insert_segments(cur: psycopg.Cursor) -> int:
    rows = _load_json("segments.json")
    for r in rows:
        cur.execute(
            """INSERT INTO segments (id, feeder_id, from_asset_id, to_asset_id,
               conductor_type, length_m, customers_served, ampacity_a, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (
                r["id"],
                r["feeder_id"],
                r["from_asset_id"],
                r["to_asset_id"],
                r.get("conductor_type"),
                r.get("length_m"),
                r.get("customers_served", 0),
                r.get("ampacity_a"),
                r.get("status", "energized"),
            ),
        )
    return len(rows)


def _insert_switches(cur: psycopg.Cursor) -> int:
    rows = _load_json("switches.json")
    for r in rows:
        cur.execute(
            """INSERT INTO switches (id, location_asset_id, from_feeder_id,
               to_feeder_id, state, transfer_capacity_mw)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (
                r["id"],
                r.get("location_asset_id"),
                r["from_feeder_id"],
                r["to_feeder_id"],
                r.get("state", "open"),
                r.get("transfer_capacity_mw"),
            ),
        )
    return len(rows)


def _insert_cameras(cur: psycopg.Cursor) -> int:
    rows = _load_json("cameras.json")
    for r in rows:
        cur.execute(
            """INSERT INTO cameras (id, camera_type, asset_id, lat, lon,
               field_of_view, status, baseline_interval_seconds,
               escalated_interval_seconds)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (
                r["id"],
                r["camera_type"],
                r.get("asset_id"),
                r["lat"],
                r["lon"],
                r.get("field_of_view"),
                r.get("status", "active"),
                r.get("baseline_interval_seconds", 3600),
                r.get("escalated_interval_seconds", 30),
            ),
        )
    return len(rows)


def _insert_crews(cur: psycopg.Cursor) -> int:
    rows = _load_json("crews.json")
    for r in rows:
        cur.execute(
            """INSERT INTO crews (id, name, skills, certifications,
               shift_start, shift_end, home_base_lat, home_base_lon,
               current_lat, current_lon, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
               skills = EXCLUDED.skills,
               certifications = EXCLUDED.certifications,
               home_base_lat = EXCLUDED.home_base_lat,
               home_base_lon = EXCLUDED.home_base_lon,
               current_lat = EXCLUDED.current_lat,
               current_lon = EXCLUDED.current_lon""",
            (
                r["id"],
                r["name"],
                r.get("skills", []),
                r.get("certifications", []),
                r.get("shift_start"),
                r.get("shift_end"),
                r.get("home_base_lat"),
                r.get("home_base_lon"),
                r.get("current_lat"),
                r.get("current_lon"),
                r.get("status", "available"),
            ),
        )
    return len(rows)


def _insert_conductor_types(cur: psycopg.Cursor) -> int:
    rows = _load_json("conductor_types.json")
    for r in rows:
        cur.execute(
            """INSERT INTO conductor_types (name, r_ohm_per_km, x_ohm_per_km,
               c_nf_per_km, max_i_ka)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (name) DO NOTHING""",
            (
                r["name"],
                r["r_ohm_per_km"],
                r["x_ohm_per_km"],
                r["c_nf_per_km"],
                r["max_i_ka"],
            ),
        )
    return len(rows)


def main() -> None:
    dsn = sys.argv[1] if len(sys.argv) > 1 else DB_DSN
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            print(f"Feeders:         {_insert_feeders(cur)}")
            print(f"Assets:          {_insert_assets(cur)}")
            print(f"Segments:        {_insert_segments(cur)}")
            print(f"Switches:        {_insert_switches(cur)}")
            print(f"Cameras:         {_insert_cameras(cur)}")
            print(f"Crews:           {_insert_crews(cur)}")
            print(f"Conductor types: {_insert_conductor_types(cur)}")
        conn.commit()
    print("Seed data loaded.")


if __name__ == "__main__":
    main()
