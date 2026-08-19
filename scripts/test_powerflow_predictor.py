# This project was developed with assistance from AI tools.

"""Test the PowerFlowPredictor against seed data (no database required).

Validates that the integrated predictor produces results consistent
with the prototype and the arithmetic predictor.

Usage:
    python3 scripts/test_powerflow_predictor.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add service to path so we can import it directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "growth-simulator"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "grid-common"))

from growth_simulator.powerflow import PowerFlowPredictor
from growth_simulator.predictor import GrowthScenario

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def load_grid_data() -> dict:
    """Load seed data to match app.py's _load_grid_data() shape."""
    assets_raw = json.loads((SEED_DIR / "assets.json").read_text())
    segments_raw = json.loads((SEED_DIR / "segments.json").read_text())
    feeders_raw = json.loads((SEED_DIR / "feeders.json").read_text())
    conductor_types_raw = json.loads((SEED_DIR / "conductor_types.json").read_text())
    mitigation_costs = json.loads((SEED_DIR / "mitigation_costs.json").read_text())

    transformers = [
        a for a in assets_raw
        if a["asset_type"] == "transformer" and a.get("subtype") == "pad_mount"
    ]
    substation_transformers = [
        a for a in assets_raw
        if a["asset_type"] == "transformer" and a.get("subtype") == "power_transformer"
    ]
    conductor_types = {r["name"]: r for r in conductor_types_raw}

    return {
        "feeders": feeders_raw,
        "transformers": transformers,
        "substation_transformers": substation_transformers,
        "all_assets": assets_raw,
        "assets": assets_raw,
        "segments": segments_raw,
        "conductor_types": conductor_types,
        "mitigation_costs": mitigation_costs,
    }


def main() -> None:
    grid_data = load_grid_data()
    predictor = PowerFlowPredictor()

    # --- Test 1: Baseline (no growth) ---
    print("=" * 60)
    print("TEST 1: Baseline — zero-growth scenario on all feeders")
    print("=" * 60)
    baseline = GrowthScenario(name="Baseline", description="No growth")
    result = predictor.predict(baseline, grid_data)

    print(f"\nCorridor utilization: {result.corridor_utilization_pct}%")
    print(f"Total new load: {result.total_new_load_mw} MW")
    print(f"\nFeeder results:")
    for f in result.feeders:
        print(f"  {f.feeder_id} ({f.feeder_name}): "
              f"{f.current_load_mw} MW -> {f.projected_load_mw} MW "
              f"({f.projected_utilization_pct}%) [{f.status}]")

    print(f"\nTransformer results (top 5 by utilization):")
    for a in result.at_risk_assets[:5]:
        rec = next((m.label for m in a.mitigations if m.recommended), "none")
        print(f"  {a.asset_id}: {a.current_utilization_pct}% -> {a.projected_utilization_pct}% "
              f"[{a.status}] recommended: {rec}")

    print(f"\nSummary: {result.summary}")

    # --- Test 2: 200 new homes on F-12 ---
    print("\n" + "=" * 60)
    print("TEST 2: 200 new homes on F-12")
    print("=" * 60)
    scenario_200 = GrowthScenario(
        name="200 Homes",
        description="200 new homes on Burlington South",
        feeder_ids=["F-12"],
        new_residential=200,
        horizon_years=5,
    )
    result = predictor.predict(scenario_200, grid_data)

    print(f"\nTotal new load: {result.total_new_load_mw} MW")
    for f in result.feeders:
        print(f"  {f.feeder_id}: {f.current_load_mw} -> {f.projected_load_mw} MW "
              f"({f.projected_utilization_pct}%) [{f.status}]")

    newly_at_risk = [a for a in result.at_risk_assets if a.newly_at_risk]
    print(f"\nNewly at risk: {len(newly_at_risk)} transformers")
    for a in newly_at_risk:
        rec = next((m.label for m in a.mitigations if m.recommended), "none")
        print(f"  {a.asset_id}: {a.current_utilization_pct}% -> {a.projected_utilization_pct}% "
              f"| recommended: {rec}")

    print(f"\nSummary: {result.summary}")

    # --- Test 3: 30% EV + 2% organic growth, 10-year horizon ---
    print("\n" + "=" * 60)
    print("TEST 3: 30% EV + 2% organic growth, 10-year horizon")
    print("=" * 60)
    scenario_ev = GrowthScenario(
        name="EV 30% + Growth",
        description="30% EV adoption with 2% annual organic growth",
        ev_adoption_pct=30.0,
        annual_growth_pct=2.0,
        horizon_years=10,
    )
    result = predictor.predict(scenario_ev, grid_data)

    print(f"\nTotal new load: {result.total_new_load_mw} MW")
    for f in result.feeders:
        print(f"  {f.feeder_id}: {f.current_load_mw} -> {f.projected_load_mw} MW "
              f"({f.projected_utilization_pct}%) [{f.status}] "
              f"first constraint year: {f.overload_year or 'none'}")

    overloaded = [a for a in result.at_risk_assets if a.status != "ok"]
    print(f"\nConstrained transformers: {len(overloaded)}")
    for a in overloaded[:10]:
        print(f"  {a.asset_id} ({a.rated_kva:.0f} kVA): {a.projected_utilization_pct}% "
              f"[{a.status}] first constraint year: {a.overload_year or 'none'}")

    # Show mitigation options for the most-constrained transformer
    if overloaded:
        a = overloaded[0]
        print(f"\n--- Mitigation options for {a.asset_id} "
              f"({a.rated_kva:.0f} kVA @ {a.projected_utilization_pct}%) ---")
        for m in a.mitigations:
            star = " *RECOMMENDED*" if m.recommended else ""
            if not m.available:
                print(f"  [{m.label}] unavailable — {m.unavailable_reason}{star}")
                continue
            cost = (f"${m.cost_low:,}–${m.cost_high:,}"
                    if m.cost_low is not None else "n/a")
            print(f"  [{m.label}] {m.description} | {cost} | "
                  f"-> {m.resulting_utilization_pct}% [{m.resulting_status}]{star}")
            if m.target_asset_id:
                print(f"      target {m.target_asset_id}: "
                      f"{m.target_before_utilization_pct}% -> {m.target_after_utilization_pct}%")

    # Year-by-year constraint timeline
    print(f"\n--- Year-by-year timeline (F-12 feeder + its transformers) ---")
    print(f"{'Year':<6s}", end="")
    print(f"{'F-12 %':>8s}", end="")
    f12_xfmrs = [a.asset_id for a in result.at_risk_assets if a.feeder_id == "F-12"][:5]
    for tid in f12_xfmrs:
        print(f"{tid:>8s}", end="")
    print()
    print("-" * (6 + 8 + 8 * len(f12_xfmrs)))

    for snap in result.yearly_projections:
        print(f"{snap.year:<6d}", end="")
        print(f"{snap.feeder_utilization_pct.get('F-12', 0):>8.1f}", end="")
        for tid in f12_xfmrs:
            print(f"{snap.asset_utilization_pct.get(tid, 0):>8.1f}", end="")
        print()

    print(f"\nSummary: {result.summary}")


if __name__ == "__main__":
    main()
