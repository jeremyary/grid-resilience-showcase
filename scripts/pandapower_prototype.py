# This project was developed with assistance from AI tools.

"""Pandapower prototype — Feeder F-12, baseline power flow.

APPENG-5931: Build F-12's network in pandapower, run a power-flow solve,
validate that baseline loading roughly matches the arithmetic predictor.

Usage:
    pip install pandapower
    python scripts/pandapower_prototype.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandapower as pp

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"

# ---------------------------------------------------------------------------
# ACSR conductor impedance values (published engineering reference)
# ---------------------------------------------------------------------------
# ACSR 4/0 (Penguin): typical distribution backbone
#   R = 0.592 Ω/mi = 0.368 Ω/km, X = 0.391 Ω/mi = 0.243 Ω/km
# ACSR 1/0 (Raven): typical distribution lateral
#   R = 1.12 Ω/mi = 0.696 Ω/km, X = 0.441 Ω/mi = 0.274 Ω/km
# Capacitance: ~10 nF/km for overhead lines (small effect at distribution voltage)

CONDUCTOR_PARAMS = {
    "ACSR_4/0": {"r_ohm_per_km": 0.368, "x_ohm_per_km": 0.243, "c_nf_per_km": 10.0, "max_i_ka": 0.340},
    "ACSR_1/0": {"r_ohm_per_km": 0.696, "x_ohm_per_km": 0.274, "c_nf_per_km": 10.0, "max_i_ka": 0.230},
}

# Feeder F-12 current load from seed data
F12_CURRENT_LOAD_MW = 7.2
F12_FEEDER_ID = "F-12"

# Substation transformer parameters (115kV → 12.47kV)
SUB_XFMR_MVA = 20.0
SUB_HV_KV = 115.0
SUB_LV_KV = 12.47
SUB_VK_PERCENT = 8.0
SUB_VKR_PERCENT = 0.5
SUB_I0_PERCENT = 0.3
SUB_PFE_KW = 20.0


def load_seed_data() -> tuple[list[dict], list[dict], list[dict]]:
    """Load assets, segments, feeders from seed JSON."""
    assets = json.loads((SEED_DIR / "assets.json").read_text())
    segments = json.loads((SEED_DIR / "segments.json").read_text())
    feeders = json.loads((SEED_DIR / "feeders.json").read_text())
    return assets, segments, feeders


def filter_f12(
    assets: list[dict], segments: list[dict],
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Extract F-12 poles, transformers, segments, and SUB-A."""
    poles = [a for a in assets if a["feeder_id"] == F12_FEEDER_ID and a["asset_type"] == "pole"]
    transformers = [a for a in assets if a["feeder_id"] == F12_FEEDER_ID and a["asset_type"] == "transformer"]
    f12_segments = [s for s in segments if s["feeder_id"] == F12_FEEDER_ID]
    sub_a = next(a for a in assets if a["id"] == "SUB-A")
    return poles, transformers, f12_segments, sub_a


def find_nearest_pole(transformer: dict, poles: list[dict]) -> str:
    """Find the pole closest to a transformer by lat/lon."""
    def dist(p: dict) -> float:
        return math.hypot(p["lat"] - transformer["lat"], p["lon"] - transformer["lon"])
    return min(poles, key=dist)["id"]


def build_network(
    poles: list[dict],
    transformers: list[dict],
    f12_segments: list[dict],
    sub_a: dict,
) -> pp.pandapowerNet:
    """Build a pandapower network for Feeder F-12."""
    net = pp.create_empty_network(name="Feeder F-12 Prototype")

    # --- Bus index mapping: asset_id -> pandapower bus index ---
    bus_map: dict[str, int] = {}

    # External grid bus (115kV transmission)
    hv_bus = pp.create_bus(net, vn_kv=SUB_HV_KV, name="SUB-A_HV")
    pp.create_ext_grid(net, bus=hv_bus, vm_pu=1.0, name="Grid")

    # Substation MV bus (12.47kV)
    mv_bus = pp.create_bus(net, vn_kv=SUB_LV_KV, name="SUB-A_MV")
    bus_map["SUB-A"] = mv_bus

    # Substation transformer (115kV -> 12.47kV)
    pp.create_transformer_from_parameters(
        net,
        hv_bus=hv_bus,
        lv_bus=mv_bus,
        sn_mva=SUB_XFMR_MVA,
        vn_hv_kv=SUB_HV_KV,
        vn_lv_kv=SUB_LV_KV,
        vk_percent=SUB_VK_PERCENT,
        vkr_percent=SUB_VKR_PERCENT,
        i0_percent=SUB_I0_PERCENT,
        pfe_kw=SUB_PFE_KW,
        name="SUB-A_XFMR",
    )

    # Pole buses (all at 12.47kV)
    for pole in poles:
        idx = pp.create_bus(net, vn_kv=SUB_LV_KV, name=pole["id"])
        bus_map[pole["id"]] = idx

    # Feeder segments as lines (skip transformer tap segments)
    xfmr_ids = {t["id"] for t in transformers}
    for seg in f12_segments:
        if seg["from_asset_id"] in xfmr_ids or seg["to_asset_id"] in xfmr_ids:
            continue
        from_bus = bus_map[seg["from_asset_id"]]
        to_bus = bus_map[seg["to_asset_id"]]
        params = CONDUCTOR_PARAMS[seg["conductor_type"]]
        length_km = seg["length_m"] / 1000.0

        pp.create_line_from_parameters(
            net,
            from_bus=from_bus,
            to_bus=to_bus,
            length_km=length_km,
            r_ohm_per_km=params["r_ohm_per_km"],
            x_ohm_per_km=params["x_ohm_per_km"],
            c_nf_per_km=params["c_nf_per_km"],
            max_i_ka=params["max_i_ka"],
            name=seg["id"],
        )

    # Distribution transformers: tap into nearest pole
    total_customers = sum(t["customers_downstream"] for t in transformers)
    load_per_customer_kw = F12_CURRENT_LOAD_MW * 1000 / total_customers

    print(f"\n--- Transformer-to-pole mapping ---")
    print(f"Total F-12 customers (transformers): {total_customers}")
    print(f"Load per customer: {load_per_customer_kw:.2f} kW")
    print()

    for t in transformers:
        nearest_pole = find_nearest_pole(t, poles)
        hv_bus_t = bus_map[nearest_pole]

        # LV bus for this transformer (0.24 kV secondary)
        lv_bus_t = pp.create_bus(net, vn_kv=0.24, name=f"{t['id']}_LV")

        rated_kva = t["rated_kva"]
        rated_mva = rated_kva / 1000.0

        # Distribution transformer parameters (typical values by size)
        pp.create_transformer_from_parameters(
            net,
            hv_bus=hv_bus_t,
            lv_bus=lv_bus_t,
            sn_mva=rated_mva,
            vn_hv_kv=SUB_LV_KV,
            vn_lv_kv=0.24,
            vk_percent=5.75,
            vkr_percent=1.0,
            i0_percent=0.5,
            pfe_kw=rated_kva * 0.003,
            name=t["id"],
        )

        # Load on LV side
        load_kw = t["customers_downstream"] * load_per_customer_kw
        load_kvar = load_kw * math.tan(math.acos(0.95))  # PF = 0.95

        pp.create_load(
            net,
            bus=lv_bus_t,
            p_mw=load_kw / 1000.0,
            q_mvar=load_kvar / 1000.0,
            name=f"Load_{t['id']}",
        )

        utilization_pct = load_kw / 0.95 / rated_kva * 100  # kW -> kVA -> % of rated
        print(f"  {t['id']:6s} ({rated_kva:5.0f} kVA, {t['customers_downstream']:3d} cust) "
              f"-> {nearest_pole:5s}  load={load_kw:.0f} kW  util={utilization_pct:.1f}%")

    return net


def run_and_print(net: pp.pandapowerNet) -> None:
    """Run power flow and print key results."""
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True)

    print("\n" + "=" * 70)
    print("POWER FLOW RESULTS — Feeder F-12 Baseline")
    print("=" * 70)

    # --- Bus voltages (12.47kV buses only) ---
    print("\n--- Bus Voltages (12.47 kV buses) ---")
    print(f"{'Bus':<12s} {'V (pu)':>8s} {'V (kV)':>8s} {'Angle (°)':>10s}")
    print("-" * 42)
    mv_buses = net.bus[net.bus.vn_kv == SUB_LV_KV]
    for idx in mv_buses.index:
        name = net.bus.at[idx, "name"]
        vm = net.res_bus.at[idx, "vm_pu"]
        va = net.res_bus.at[idx, "va_degree"]
        print(f"{name:<12s} {vm:>8.4f} {vm * SUB_LV_KV:>8.3f} {va:>10.3f}")

    # --- Line loading ---
    print("\n--- Line Loading (top 10 most loaded) ---")
    print(f"{'Segment':<10s} {'Loading %':>10s} {'I (kA)':>8s} {'P (MW)':>8s}")
    print("-" * 40)
    line_loading = net.res_line.copy()
    line_loading["name"] = net.line["name"].values
    line_loading = line_loading.sort_values("loading_percent", ascending=False)
    for _, row in line_loading.head(10).iterrows():
        print(f"{row['name']:<10s} {row['loading_percent']:>10.1f} "
              f"{row['i_ka']:>8.4f} {row['p_from_mw']:>8.3f}")

    # --- Transformer loading ---
    print("\n--- Transformer Loading ---")
    print(f"{'Transformer':<14s} {'Loading %':>10s} {'P (MW)':>8s} {'Q (Mvar)':>8s}")
    print("-" * 44)
    for idx in net.trafo.index:
        name = net.trafo.at[idx, "name"]
        loading = net.res_trafo.at[idx, "loading_percent"]
        p = net.res_trafo.at[idx, "p_hv_mw"]
        q = net.res_trafo.at[idx, "q_hv_mvar"]
        print(f"{name:<14s} {loading:>10.1f} {p:>8.3f} {q:>8.3f}")

    # --- Total grid import ---
    print("\n--- Grid Import ---")
    for idx in net.ext_grid.index:
        p = net.res_ext_grid.at[idx, "p_mw"]
        q = net.res_ext_grid.at[idx, "q_mvar"]
        print(f"P = {p:.3f} MW, Q = {q:.3f} Mvar")

    # --- Voltage range ---
    mv_vm = net.res_bus.loc[mv_buses.index, "vm_pu"]
    print(f"\nVoltage range (MV buses): {mv_vm.min():.4f} - {mv_vm.max():.4f} pu")
    if mv_vm.min() < 0.95:
        print("  WARNING: Voltage below 0.95 pu (ANSI C84.1 Range A)")

    # --- Comparison with arithmetic predictor ---
    print("\n" + "=" * 70)
    print("COMPARISON WITH ARITHMETIC PREDICTOR")
    print("=" * 70)
    grid_p = net.res_ext_grid.at[0, "p_mw"]
    print(f"  Arithmetic predictor: F-12 current load = {F12_CURRENT_LOAD_MW:.1f} MW")
    print(f"  Pandapower total import:                 = {grid_p:.3f} MW")
    print(f"  Difference:                              = {grid_p - F12_CURRENT_LOAD_MW:.3f} MW "
          f"({(grid_p - F12_CURRENT_LOAD_MW) / F12_CURRENT_LOAD_MW * 100:.1f}%)")
    print(f"  (Difference is line losses + transformer losses)")


def main() -> None:
    assets, segments, feeders = load_seed_data()
    poles, transformers, f12_segments, sub_a = filter_f12(assets, segments)

    print(f"F-12 network: {len(poles)} poles, {len(transformers)} transformers, "
          f"{len(f12_segments)} segments")

    net = build_network(poles, transformers, f12_segments, sub_a)
    run_and_print(net)


if __name__ == "__main__":
    main()
