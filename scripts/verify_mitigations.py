# This project was developed with assistance from AI tools.

"""Verify mitigation math against the seed data, independently of the predictor.

Recomputes each mitigation option's cost, capacity, and resulting utilization
from first principles and asserts the predictor agrees. No database required.

Usage:
    python3 scripts/verify_mitigations.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "growth-simulator"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services" / "grid-common"))

from growth_simulator.powerflow import PowerFlowPredictor
from growth_simulator.predictor import STANDARD_TRANSFORMER_SIZES_KVA, GrowthScenario

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
PLANNING_THRESHOLD = 80.0
HEADROOM_TARGET = 75.0
HEADROOM_FRAC = HEADROOM_TARGET / 100.0            # every option aims for this headroom target
RECEIVER_FRAC = (PLANNING_THRESHOLD - 0.1) / 100.0  # a receiving unit may fill only to the limit
# The predictor works from full-precision loading_percent; we recompute from the rounded
# projected utilization (0.1%), so allow one rounding step.
UTIL_TOL = 0.11


def apparent_load(a) -> float:
    """Apparent load (kVA) implied by the displayed utilization — the mitigation basis."""
    return a.projected_utilization_pct / 100.0 * a.rated_kva

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def load_grid_data() -> dict:
    assets_raw = json.loads((SEED_DIR / "assets.json").read_text())
    return {
        "feeders": json.loads((SEED_DIR / "feeders.json").read_text()),
        "transformers": [
            a for a in assets_raw
            if a["asset_type"] == "transformer" and a.get("subtype") == "pad_mount"
        ],
        "substation_transformers": [
            a for a in assets_raw
            if a["asset_type"] == "transformer" and a.get("subtype") == "power_transformer"
        ],
        "all_assets": assets_raw,
        "assets": assets_raw,
        "segments": json.loads((SEED_DIR / "segments.json").read_text()),
        "conductor_types": {
            r["name"]: r for r in json.loads((SEED_DIR / "conductor_types.json").read_text())
        },
        "mitigation_costs": json.loads((SEED_DIR / "mitigation_costs.json").read_text()),
    }


def expected_cost(cost_table: list[dict], mtype: str, kva: float) -> tuple[int | None, int | None]:
    rows = [r for r in cost_table if r["mitigation_type"] == mtype]
    rows.sort(key=lambda r: (r.get("kva_max") is None, r.get("kva_max") or 0))
    for r in rows:
        kmax = r.get("kva_max")
        if kmax is None or kva <= kmax:
            return int(r["cost_low"]), int(r["cost_high"])
    return None, None


def expected_headroom_years(util: float | None, growth_pct: float) -> int | None:
    """Whole years for `util` to grow back to the threshold — recomputed from first principles."""
    if util is None or growth_pct <= 0 or util <= 0 or util >= PLANNING_THRESHOLD:
        return None
    return int(min(math.log(PLANNING_THRESHOLD / util) / math.log(1 + growth_pct / 100), 20.0))


def verify_asset(
    a, cost_table: list[dict], feeder_state: dict[str, tuple[float, float]], growth_pct: float,
) -> None:
    aid = a.asset_id
    rated = a.rated_kva
    load = apparent_load(a)
    by_type = {m.type: m for m in a.mitigations}

    check(len(a.mitigations) == 3, f"{aid}: expected 3 mitigations, got {len(a.mitigations)}")
    check(set(by_type) == {"transformer_upgrade", "parallel_transformer", "load_transfer"},
          f"{aid}: unexpected mitigation types {set(by_type)}")

    # --- Transformer upgrade (smallest standard size that clears the 80% limit) ---
    up = by_type["transformer_upgrade"]
    exp_size = next((s for s in STANDARD_TRANSFORMER_SIZES_KVA
                     if s > rated and load / s * 100 < PLANNING_THRESHOLD), None)
    if exp_size is None:
        check(not up.available, f"{aid}: upgrade should be unavailable (need >{rated})")
    else:
        exp_util = round(load / exp_size * 100, 1)
        check(up.available, f"{aid}: upgrade should be available")
        check(abs(up.resulting_utilization_pct - exp_util) < UTIL_TOL,
              f"{aid}: upgrade util {up.resulting_utilization_pct} != {exp_util}")
        check(up.capacity_added_kva == exp_size - rated,
              f"{aid}: upgrade added {up.capacity_added_kva} != {exp_size - rated}")
        check((up.cost_low, up.cost_high) == expected_cost(cost_table, "transformer_upgrade", exp_size),
              f"{aid}: upgrade cost mismatch")

    # --- Parallel transformer (matched unit, floored at existing rating) ---
    par = by_type["parallel_transformer"]
    exp_add = next((s for s in STANDARD_TRANSFORMER_SIZES_KVA
                    if s >= rated and load / (rated + s) * 100 < PLANNING_THRESHOLD), None)
    if exp_add is None:
        check(not par.available, f"{aid}: parallel should be unavailable")
    else:
        exp_util = round(load / (rated + exp_add) * 100, 1)
        check(par.available, f"{aid}: parallel should be available")
        check(abs(par.resulting_utilization_pct - exp_util) < UTIL_TOL,
              f"{aid}: parallel util {par.resulting_utilization_pct} != {exp_util}")
        check(par.capacity_added_kva == exp_add,
              f"{aid}: parallel added {par.capacity_added_kva} != {exp_add}")
        check((par.cost_low, par.cost_high) == expected_cost(cost_table, "parallel_transformer", exp_add),
              f"{aid}: parallel cost mismatch")

    # --- Load transfer (target the headroom level, cap at what a neighbor can absorb) ---
    lt = by_type["load_transfer"]
    required = load - rated * HEADROOM_FRAC
    best_id, best_avail = None, 0.0
    for nid, (n_rated, n_load) in feeder_state.items():
        if nid == aid:
            continue
        avail = n_rated * RECEIVER_FRAC - n_load
        if avail > best_avail:
            best_avail, best_id = avail, nid
    actual = min(required, best_avail) if best_id is not None else 0.0
    src_after = (load - actual) / rated * 100 if best_id is not None else 100.0
    if best_id is None or best_avail <= 0 or required <= 0 or src_after >= PLANNING_THRESHOLD:
        check(not lt.available, f"{aid}: load transfer should be unavailable")
    else:
        check(lt.available, f"{aid}: load transfer should be available")
        check(lt.target_asset_id == best_id,
              f"{aid}: load transfer target {lt.target_asset_id} != {best_id}")
        exp_src = round(src_after, 1)
        check(abs(lt.resulting_utilization_pct - exp_src) < UTIL_TOL,
              f"{aid}: load transfer source util {lt.resulting_utilization_pct} != {exp_src}")
        n_rated, n_load = feeder_state[best_id]
        exp_after = round((n_load + actual) / n_rated * 100, 1)
        check(abs(lt.target_after_utilization_pct - exp_after) < UTIL_TOL,
              f"{aid}: load transfer target after {lt.target_after_utilization_pct} != {exp_after}")

    # --- Recommendation invariants ---
    # All three compete on cost per year of headroom; lowest wins (best value). When a load
    # transfer wins, the longest-lived capital fix is also flagged most durable.
    def value_key(m):
        mid = (m.cost_low + m.cost_high) / 2
        years = m.years_gained or 0
        return (mid / years if years > 0 else float("inf"), mid, -years)

    recommended = [m for m in a.mitigations if m.recommended]
    durable = [m for m in a.mitigations if m.most_durable]
    check(len(recommended) <= 1, f"{aid}: {len(recommended)} options marked recommended")
    check(len(durable) <= 1, f"{aid}: {len(durable)} options marked most_durable")
    feasible = [m for m in a.mitigations
                if m.available and m.resulting_utilization_pct is not None
                and m.resulting_utilization_pct < PLANNING_THRESHOLD]
    if feasible:
        check(len(recommended) == 1, f"{aid}: feasible options exist but none recommended")
        rec = recommended[0]
        best_key = min(value_key(m) for m in feasible)
        check(value_key(rec) <= best_key,
              f"{aid}: recommended {rec.label} is not the best cost-per-year")
        # most_durable appears only when the value winner is a load transfer, and points to the
        # longest-lived capital fix.
        capital = [m for m in feasible if m.type in ("transformer_upgrade", "parallel_transformer")]
        if rec.type == "load_transfer" and capital:
            check(len(durable) == 1, f"{aid}: load transfer won but no durable capital fix flagged")
            dkey = min((-(m.years_gained or 0), (m.cost_low + m.cost_high) / 2) for m in capital)
            d = durable[0]
            check(d.type in ("transformer_upgrade", "parallel_transformer"),
                  f"{aid}: most_durable {d.label} is not a capital fix")
            check((-(d.years_gained or 0), (d.cost_low + d.cost_high) / 2) <= dkey,
                  f"{aid}: most_durable {d.label} is not the longest-lived capital fix")
        else:
            check(not durable, f"{aid}: most_durable flagged when value winner is not a load transfer")
    else:
        check(not recommended, f"{aid}: no feasible option but one was recommended")
        check(not durable, f"{aid}: no feasible option but one was flagged most_durable")
    # Every equipment (capital) option must clear the planning threshold when available.
    for m in [by_type["transformer_upgrade"], by_type["parallel_transformer"]]:
        if m.available:
            check(m.resulting_utilization_pct < PLANNING_THRESHOLD,
                  f"{aid}: {m.label} lands at {m.resulting_utilization_pct}% (>= threshold)")

    # --- Years-of-headroom beyond the outlook (from resulting utilization) ---
    for m in a.mitigations:
        if not m.available:
            check(m.years_gained is None, f"{aid}: {m.label} unavailable but has years_gained")
            continue
        exp = expected_headroom_years(m.resulting_utilization_pct, growth_pct)
        # A load transfer also fills a neighbor; the receiver crosses the threshold first.
        if m.type == "load_transfer":
            recv = expected_headroom_years(m.target_after_utilization_pct, growth_pct)
            if exp is not None and recv is not None:
                exp = min(exp, recv)
        check(m.years_gained == exp,
              f"{aid}: {m.label} years_gained {m.years_gained} != {exp}")


def main() -> None:
    grid_data = load_grid_data()
    cost_table = grid_data["mitigation_costs"]
    predictor = PowerFlowPredictor()

    scenario = GrowthScenario(
        name="EV stress",
        description="30% EV + 2% organic growth, 10-year horizon",
        ev_adoption_pct=30.0,
        annual_growth_pct=2.0,
        horizon_years=10,
    )
    result = predictor.predict(scenario, grid_data)

    # Build per-feeder projected state (rated, projected load) for load-transfer checks.
    feeder_states: dict[str, dict[str, tuple[float, float]]] = {}
    for a in result.at_risk_assets:
        feeder_states.setdefault(a.feeder_id, {})[a.asset_id] = (a.rated_kva, apparent_load(a))

    constrained = [a for a in result.at_risk_assets if a.status != "ok"]
    print(f"Checking {len(constrained)} constrained transformers...")
    for a in constrained:
        verify_asset(a, cost_table, feeder_states[a.feeder_id], scenario.annual_growth_pct)

    # Unconstrained transformers must carry no mitigations.
    for a in result.at_risk_assets:
        if a.status == "ok":
            check(not a.mitigations, f"{a.asset_id}: ok transformer has mitigations")

    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    print(f"\nAll checks passed ({len(constrained)} constrained transformers verified).")


if __name__ == "__main__":
    main()
