# This project was developed with assistance from AI tools.

"""Side-by-side comparison: ComputationalPredictor vs PowerFlowPredictor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "growth-simulator"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "grid-common"))

from growth_simulator.powerflow import PowerFlowPredictor
from growth_simulator.predictor import ComputationalPredictor, GrowthScenario

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def load_grid_data() -> dict:
    assets_raw = json.loads((SEED_DIR / "assets.json").read_text())
    segments_raw = json.loads((SEED_DIR / "segments.json").read_text())
    feeders_raw = json.loads((SEED_DIR / "feeders.json").read_text())
    conductor_types_raw = json.loads((SEED_DIR / "conductor_types.json").read_text())

    transformers = [a for a in assets_raw if a["asset_type"] == "transformer" and a.get("subtype") == "pad_mount"]
    substation_transformers = [a for a in assets_raw if a["asset_type"] == "transformer" and a.get("subtype") == "power_transformer"]

    return {
        "feeders": feeders_raw,
        "transformers": transformers,
        "substation_transformers": substation_transformers,
        "all_assets": assets_raw,
        "assets": assets_raw,
        "segments": segments_raw,
        "conductor_types": {r["name"]: r for r in conductor_types_raw},
    }


def compare(scenario: GrowthScenario, grid_data: dict) -> None:
    arith = ComputationalPredictor()
    pflow = PowerFlowPredictor()

    r_a = arith.predict(scenario, grid_data)
    r_p = pflow.predict(scenario, grid_data)

    print(f"\n{'=' * 70}")
    print(f"SCENARIO: {scenario.name}")
    print(f"{'=' * 70}")

    print(f"\n{'Metric':<35s} {'Arithmetic':>12s} {'PowerFlow':>12s} {'Delta':>10s}")
    print("-" * 72)
    print(f"{'Total new load (MW)':<35s} {r_a.total_new_load_mw:>12.2f} {r_p.total_new_load_mw:>12.2f} {r_p.total_new_load_mw - r_a.total_new_load_mw:>+10.2f}")
    print(f"{'Corridor utilization (%)':<35s} {r_a.corridor_utilization_pct:>12.1f} {r_p.corridor_utilization_pct:>12.1f} {r_p.corridor_utilization_pct - r_a.corridor_utilization_pct:>+10.1f}")

    print(f"\n--- Feeder comparison ---")
    print(f"{'Feeder':<8s} {'Arith load':>11s} {'PFlow load':>11s} {'Arith util%':>12s} {'PFlow util%':>12s}")
    print("-" * 58)
    for fa in r_a.feeders:
        fp = next((f for f in r_p.feeders if f.feeder_id == fa.feeder_id), None)
        if not fp:
            continue
        print(f"{fa.feeder_id:<8s} {fa.projected_load_mw:>11.2f} {fp.projected_load_mw:>11.2f} {fa.projected_utilization_pct:>12.1f} {fp.projected_utilization_pct:>12.1f}")

    print(f"\n--- Transformer comparison (top 10 by PowerFlow utilization) ---")
    print(f"{'ID':<8s} {'kVA':>6s} {'Arith%':>8s} {'PFlow%':>8s} {'A-status':>10s} {'P-status':>10s}")
    print("-" * 54)

    pflow_sorted = sorted(r_p.at_risk_assets, key=lambda a: a.projected_utilization_pct, reverse=True)
    for ap in pflow_sorted[:10]:
        aa = next((a for a in r_a.at_risk_assets if a.asset_id == ap.asset_id), None)
        if not aa:
            continue
        print(f"{ap.asset_id:<8s} {ap.rated_kva:>6.0f} {aa.projected_utilization_pct:>8.1f} {ap.projected_utilization_pct:>8.1f} {aa.status:>10s} {ap.status:>10s}")


def main() -> None:
    grid_data = load_grid_data()

    compare(GrowthScenario(name="Baseline", description="No growth"), grid_data)

    compare(GrowthScenario(
        name="200 Homes on F-12",
        feeder_ids=["F-12"],
        new_residential=200,
        horizon_years=5,
    ), grid_data)

    compare(GrowthScenario(
        name="30% EV adoption",
        ev_adoption_pct=30.0,
        horizon_years=5,
    ), grid_data)


if __name__ == "__main__":
    main()
