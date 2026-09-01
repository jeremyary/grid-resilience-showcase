# This project was developed with assistance from AI tools.

"""Pandapower-based growth predictor — replaces arithmetic load allocation."""

from __future__ import annotations

import math
from typing import Any

import pandapower as pp

from growth_simulator.predictor import (
    STANDARD_TRANSFORMER_SIZES_KVA,
    AssetProjection,
    FeederProjection,
    GrowthPrediction,
    GrowthPredictor,
    GrowthScenario,
    MitigationOption,
    YearlySnapshot,
)

_DIST_LV_KV = 0.24

# Preferred (soft) headroom target. Reaching this is "good headroom"; the planning threshold
# (80%) is the hard feasibility limit. A mitigation is sized to clear the limit, not to force a
# transformer-size jump just to hit the preferred target exactly.
HEADROOM_TARGET_PCT = 75.0


def _find_nearest_pole(transformer: dict[str, Any], poles: list[dict[str, Any]]) -> str:
    """Find the pole closest to a transformer by lat/lon."""
    def dist(p: dict[str, Any]) -> float:
        return math.hypot(p["lat"] - transformer["lat"], p["lon"] - transformer["lon"])
    return min(poles, key=dist)["id"]


def _build_feeder_network(
    feeder: dict[str, Any],
    transformers: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    power_factor: float,
    conductor_types: dict[str, dict[str, float]],
    substation_transformers: list[dict[str, Any]],
) -> tuple[pp.pandapowerNet, dict[str, int], float]:
    """Build a pandapower network for a single feeder.

    Returns the network, a mapping of transformer_id -> load index,
    and the MV bus voltage in kV.
    """
    fid = feeder["id"]
    sub_id = feeder["substation_id"]

    feeder_poles = [a for a in assets if a.get("feeder_id") == fid and a["asset_type"] == "pole"]
    feeder_segments = [s for s in segments if s["feeder_id"] == fid]
    feeder_xfmrs = [t for t in transformers if t["feeder_id"] == fid]
    xfmr_ids = {t["id"] for t in feeder_xfmrs}

    # Build transformer placement map from segments (pole -> transformer taps)
    xfmr_placement: dict[str, str] = {}
    line_segments: list[dict[str, Any]] = []
    for seg in feeder_segments:
        if seg["to_asset_id"] in xfmr_ids:
            xfmr_placement[seg["to_asset_id"]] = seg["from_asset_id"]
        elif seg["from_asset_id"] in xfmr_ids:
            xfmr_placement[seg["from_asset_id"]] = seg["to_asset_id"]
        else:
            line_segments.append(seg)

    total_customers = sum(t["customers_downstream"] for t in feeder_xfmrs)
    load_per_customer_kw = feeder["current_load_mw"] * 1000 / total_customers if total_customers else 0

    net = pp.create_empty_network(name=f"Feeder {fid}")
    bus_map: dict[str, int] = {}

    # Find substation transformer for this feeder's substation
    sub_xfmr = next(
        (st for st in substation_transformers if st["id"] == f"T-{sub_id}"),
        None,
    )
    sub_hv_kv = sub_xfmr["rated_voltage_kv"] if sub_xfmr else 115.0
    sub_lv_kv = feeder_xfmrs[0].get("rated_voltage_kv", 12.47) if feeder_xfmrs else 12.47
    sub_mva = (sub_xfmr["rated_kva"] / 1000.0) if sub_xfmr else 20.0

    # External grid + substation transformer
    hv_bus = pp.create_bus(net, vn_kv=sub_hv_kv, name=f"{sub_id}_HV")
    pp.create_ext_grid(net, bus=hv_bus, vm_pu=1.0, name="Grid")

    mv_bus = pp.create_bus(net, vn_kv=sub_lv_kv, name=f"{sub_id}_MV")
    bus_map[sub_id] = mv_bus

    pp.create_transformer_from_parameters(
        net, hv_bus=hv_bus, lv_bus=mv_bus,
        sn_mva=sub_mva, vn_hv_kv=sub_hv_kv, vn_lv_kv=sub_lv_kv,
        vk_percent=sub_xfmr["vk_percent"] if sub_xfmr else 8.0,
        vkr_percent=sub_xfmr["vkr_percent"] if sub_xfmr else 0.5,
        i0_percent=sub_xfmr["i0_percent"] if sub_xfmr else 0.3,
        pfe_kw=sub_xfmr["pfe_kw"] if sub_xfmr else 20.0,
        name=f"{sub_id}_XFMR",
    )

    # Pole buses
    for pole in feeder_poles:
        idx = pp.create_bus(net, vn_kv=sub_lv_kv, name=pole["id"])
        bus_map[pole["id"]] = idx

    # Pole-to-pole segments as lines (excludes transformer tap segments)
    for seg in line_segments:
        params = conductor_types.get(seg["conductor_type"])
        if not params:
            continue
        pp.create_line_from_parameters(
            net,
            from_bus=bus_map[seg["from_asset_id"]],
            to_bus=bus_map[seg["to_asset_id"]],
            length_km=seg["length_m"] / 1000.0,
            r_ohm_per_km=params["r_ohm_per_km"],
            x_ohm_per_km=params["x_ohm_per_km"],
            c_nf_per_km=params["c_nf_per_km"],
            max_i_ka=params["max_i_ka"],
            name=seg["id"],
        )

    # Distribution transformers + loads
    load_index_map: dict[str, int] = {}

    for t in feeder_xfmrs:
        tap_pole = xfmr_placement.get(t["id"]) or _find_nearest_pole(t, feeder_poles)
        hv_bus_t = bus_map[tap_pole]
        lv_bus_t = pp.create_bus(net, vn_kv=_DIST_LV_KV, name=f"{t['id']}_LV")

        rated_kva = t.get("rated_kva") or 500
        pp.create_transformer_from_parameters(
            net, hv_bus=hv_bus_t, lv_bus=lv_bus_t,
            sn_mva=rated_kva / 1000.0,
            vn_hv_kv=sub_lv_kv, vn_lv_kv=_DIST_LV_KV,
            vk_percent=t.get("vk_percent") or 5.75,
            vkr_percent=t.get("vkr_percent") or 1.0,
            i0_percent=t.get("i0_percent") or 0.5,
            pfe_kw=t.get("pfe_kw") or rated_kva * 0.003,
            name=t["id"],
        )

        load_kw = t["customers_downstream"] * load_per_customer_kw
        load_kvar = load_kw * math.tan(math.acos(power_factor))

        load_idx = pp.create_load(
            net, bus=lv_bus_t,
            p_mw=load_kw / 1000.0,
            q_mvar=load_kvar / 1000.0,
            name=f"Load_{t['id']}",
        )
        load_index_map[t["id"]] = load_idx

    return net, load_index_map, sub_lv_kv


class PowerFlowPredictor(GrowthPredictor):
    """Growth predictor backed by pandapower power-flow simulation."""

    def __init__(
        self,
        power_factor: float = 0.95,
        residential_load_kw: float = 4.0,
        ev_charger_load_kw: float = 7.2,
        ev_coincidence_factor: float = 0.35,
        solar_capacity_factor: float = 0.25,
        planning_threshold_pct: float = 80.0,
        overload_threshold_pct: float = 100.0,
    ) -> None:
        self.power_factor = power_factor
        self.residential_load_kw = residential_load_kw
        self.ev_charger_load_kw = ev_charger_load_kw
        self.ev_coincidence_factor = ev_coincidence_factor
        self.solar_capacity_factor = solar_capacity_factor
        self.planning_threshold_pct = planning_threshold_pct
        self.overload_threshold_pct = overload_threshold_pct

    def _classify(self, utilization_pct: float) -> str:
        if utilization_pct >= self.overload_threshold_pct:
            return "overloaded"
        if utilization_pct >= self.planning_threshold_pct:
            return "at_risk"
        return "ok"

    def predict(self, scenario: GrowthScenario, grid_data: dict[str, Any]) -> GrowthPrediction:
        feeders = grid_data["feeders"]
        transformers = grid_data["transformers"]
        segments = grid_data["segments"]
        assets = grid_data["assets"]
        conductor_types = grid_data.get("conductor_types", {})
        substation_transformers = grid_data.get("substation_transformers", [])
        mitigation_costs = grid_data.get("mitigation_costs", [])

        target_feeders = [f for f in feeders if not scenario.feeder_ids or f["id"] in scenario.feeder_ids]

        feeder_projections: list[FeederProjection] = []
        asset_projections: list[AssetProjection] = []
        total_new_load_mw = 0.0

        yearly_snapshots: dict[int, YearlySnapshot] = {}
        feeder_first_overload: dict[str, int | None] = {}
        asset_first_overload: dict[str, int | None] = {}

        for feeder in target_feeders:
            fid = feeder["id"]
            feeder_xfmrs = [t for t in transformers if t["feeder_id"] == fid]
            if not feeder_xfmrs:
                continue

            net, load_map, mv_kv = _build_feeder_network(
                feeder, transformers, segments, assets, self.power_factor,
                conductor_types, substation_transformers,
            )

            # Baseline power flow (year 0)
            pp.runpp(net, algorithm="nr", calculate_voltage_angles=True)
            baseline_import_mw = net.res_ext_grid.at[0, "p_mw"]
            baseline_xfmr_loading = self._get_transformer_loading(net, feeder_xfmrs)

            # Store baseline loads for year-by-year reset
            baseline_loads: dict[str, tuple[float, float]] = {}
            for t in feeder_xfmrs:
                tid = t["id"]
                if tid in load_map:
                    idx = load_map[tid]
                    baseline_loads[tid] = (net.load.at[idx, "p_mw"], net.load.at[idx, "q_mvar"])

            normal_cap = feeder["normal_capacity_mw"]
            emergency_cap = feeder.get("emergency_capacity_mw") or normal_cap * 1.2

            # Year-by-year power flow
            feeder_first_overload[fid] = None
            for t in feeder_xfmrs:
                asset_first_overload[t["id"]] = None

            end_year_import_mw = baseline_import_mw
            end_year_xfmr_loading = baseline_xfmr_loading

            for year in range(1, scenario.horizon_years + 1):
                self._apply_scenario_for_year(
                    net, scenario, feeder_xfmrs, load_map, baseline_loads, year,
                    num_target_feeders=len(target_feeders),
                )
                pp.runpp(net, algorithm="nr", calculate_voltage_angles=True)

                year_import_mw = net.res_ext_grid.at[0, "p_mw"]
                year_xfmr_loading = self._get_transformer_loading(net, feeder_xfmrs)

                # Capture yearly snapshot
                if year not in yearly_snapshots:
                    yearly_snapshots[year] = YearlySnapshot(
                        year=year,
                        feeder_utilization_pct={},
                        feeder_load_mw={},
                        asset_utilization_pct={},
                    )
                snap = yearly_snapshots[year]
                feeder_util_yr = round(year_import_mw / normal_cap * 100, 1)
                snap.feeder_utilization_pct[fid] = feeder_util_yr
                snap.feeder_load_mw[fid] = round(year_import_mw, 2)

                if feeder_first_overload[fid] is None and feeder_util_yr >= self.planning_threshold_pct:
                    feeder_first_overload[fid] = year

                for t in feeder_xfmrs:
                    tid = t["id"]
                    if tid in year_xfmr_loading:
                        loading = round(year_xfmr_loading[tid]["loading_pct"], 1)
                        snap.asset_utilization_pct[tid] = loading
                        if asset_first_overload[tid] is None and loading >= self.planning_threshold_pct:
                            asset_first_overload[tid] = year

                end_year_import_mw = year_import_mw
                end_year_xfmr_loading = year_xfmr_loading

            # Use final year results for projections
            scenario_import_mw = end_year_import_mw
            scenario_xfmr_loading = end_year_xfmr_loading
            new_load_mw = scenario_import_mw - baseline_import_mw
            total_new_load_mw += new_load_mw

            feeder_util = round(scenario_import_mw / normal_cap * 100, 1)

            feeder_projections.append(FeederProjection(
                feeder_id=fid,
                feeder_name=feeder["name"],
                current_load_mw=round(baseline_import_mw, 2),
                projected_load_mw=round(scenario_import_mw, 2),
                normal_capacity_mw=normal_cap,
                emergency_capacity_mw=emergency_cap,
                current_utilization_pct=round(baseline_import_mw / normal_cap * 100, 1),
                projected_utilization_pct=feeder_util,
                status=self._classify(feeder_util),
                overload_year=feeder_first_overload[fid],
                headroom_mw=round(normal_cap - scenario_import_mw, 2),
            ))

            # Per-transformer projected state for this feeder (load-transfer needs neighbors)
            feeder_state: dict[str, dict[str, float]] = {}
            for t in feeder_xfmrs:
                tid = t["id"]
                sc = scenario_xfmr_loading[tid]
                rated = t.get("rated_kva") or 500
                # Mitigation math must use the SAME apparent load that drives the displayed
                # utilization (pandapower loading_percent, S=√(P²+Q²)), not p_kw/PF — otherwise
                # transfer amounts and resulting-utilization figures won't reconcile with the
                # projected % shown to the planner.
                feeder_state[tid] = {
                    "rated_kva": rated,
                    "proj_load_kva": sc["loading_pct"] / 100.0 * rated,
                }

            for t in feeder_xfmrs:
                tid = t["id"]
                rated_kva = t.get("rated_kva") or 500
                bl = baseline_xfmr_loading[tid]
                sc = scenario_xfmr_loading[tid]

                baseline_status = self._classify(bl["loading_pct"])
                status = self._classify(sc["loading_pct"])
                newly_at_risk = baseline_status == "ok" and status != "ok"

                mitigations: list[MitigationOption] = []
                if status != "ok":
                    mitigations = self._generate_mitigations(
                        tid, fid, feeder_state, mitigation_costs, scenario,
                    )

                asset_projections.append(AssetProjection(
                    asset_id=tid,
                    asset_type="transformer",
                    feeder_id=fid,
                    rated_kva=rated_kva,
                    current_load_kva=round(bl["p_kw"] / self.power_factor, 1),
                    projected_load_kva=round(sc["p_kw"] / self.power_factor, 1),
                    current_utilization_pct=round(bl["loading_pct"], 1),
                    projected_utilization_pct=round(sc["loading_pct"], 1),
                    baseline_status=baseline_status,
                    status=status,
                    newly_at_risk=newly_at_risk,
                    overload_year=asset_first_overload.get(tid),
                    mitigations=mitigations,
                    lat=t["lat"],
                    lon=t["lon"],
                ))

        asset_projections.sort(key=lambda a: a.projected_utilization_pct, reverse=True)

        corridor_load = sum(f["current_load_mw"] for f in feeders)
        corridor_cap = sum(f["normal_capacity_mw"] for f in feeders)
        corridor_new = corridor_load + total_new_load_mw
        corridor_util = corridor_new / corridor_cap * 100 if corridor_cap else 0

        summary = self._build_summary(
            scenario, feeder_projections, asset_projections, total_new_load_mw,
        )

        sorted_snapshots = [yearly_snapshots[y] for y in sorted(yearly_snapshots)]

        return GrowthPrediction(
            scenario=scenario,
            feeders=feeder_projections,
            at_risk_assets=asset_projections,
            summary=summary,
            total_new_load_mw=round(total_new_load_mw, 2),
            corridor_utilization_pct=round(corridor_util, 1),
            yearly_projections=sorted_snapshots,
        )

    def _get_transformer_loading(
        self, net: pp.pandapowerNet, feeder_xfmrs: list[dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        """Extract transformer loading from pandapower results."""
        result: dict[str, dict[str, float]] = {}
        for t in feeder_xfmrs:
            tid = t["id"]
            trafo_idx = net.trafo[net.trafo.name == tid].index
            if len(trafo_idx) == 0:
                continue
            idx = trafo_idx[0]
            loading_pct = net.res_trafo.at[idx, "loading_percent"]
            p_hv_mw = net.res_trafo.at[idx, "p_hv_mw"]
            result[tid] = {
                "loading_pct": loading_pct,
                "p_kw": abs(p_hv_mw) * 1000,
            }
        return result

    def _apply_scenario_for_year(
        self,
        net: pp.pandapowerNet,
        scenario: GrowthScenario,
        feeder_xfmrs: list[dict[str, Any]],
        load_map: dict[str, int],
        baseline_loads: dict[str, tuple[float, float]],
        year: int,
        num_target_feeders: int = 1,
    ) -> None:
        """Set loads in the network for a specific year of the scenario."""
        total_customers = sum(t["customers_downstream"] for t in feeder_xfmrs)
        organic_factor = (1 + scenario.annual_growth_pct / 100) ** year

        feeder_share = 1.0 / max(num_target_feeders, 1)

        for t in feeder_xfmrs:
            tid = t["id"]
            if tid not in load_map:
                continue
            load_idx = load_map[tid]
            customers = t["customers_downstream"]
            base_p, base_q = baseline_loads[tid]

            new_p_mw = base_p * organic_factor
            new_q_mvar = base_q * organic_factor

            if scenario.new_residential > 0 and total_customers > 0:
                customer_share = customers / total_customers
                homes_this_xfmr = scenario.new_residential * feeder_share * customer_share
                residential_mw = homes_this_xfmr * self.residential_load_kw / 1000
                residential_mvar = residential_mw * math.tan(math.acos(self.power_factor))
                new_p_mw += residential_mw
                new_q_mvar += residential_mvar

            if scenario.ev_adoption_pct > 0:
                ev_customers = customers * scenario.ev_adoption_pct / 100
                ev_mw = ev_customers * self.ev_charger_load_kw * self.ev_coincidence_factor / 1000
                ev_mvar = ev_mw * math.tan(math.acos(self.power_factor))
                new_p_mw += ev_mw
                new_q_mvar += ev_mvar

            if scenario.der_solar_kw > 0 and total_customers > 0:
                customer_share = customers / total_customers
                solar_mw = scenario.der_solar_kw / 1000 * self.solar_capacity_factor * feeder_share * customer_share
                new_p_mw -= solar_mw

            new_p_mw = max(new_p_mw, 0.0)
            new_q_mvar = max(new_q_mvar, 0.0)

            net.load.at[load_idx, "p_mw"] = new_p_mw
            net.load.at[load_idx, "q_mvar"] = new_q_mvar

    def _generate_mitigations(
        self,
        asset_id: str,
        feeder_id: str,
        feeder_state: dict[str, dict[str, float]],
        cost_table: list[dict[str, Any]],
        scenario: GrowthScenario,
    ) -> list[MitigationOption]:
        """Build the three evaluated mitigation strategies for a constrained transformer."""
        state = feeder_state[asset_id]
        rated = state["rated_kva"]
        load_kva = state["proj_load_kva"]

        options = [
            self._upgrade_option(rated, load_kva, cost_table),
            self._parallel_option(rated, load_kva, cost_table),
            self._load_transfer_option(asset_id, feeder_id, feeder_state, cost_table),
        ]
        for o in options:
            o.years_gained = self._years_beyond_outlook(o, scenario)
        self._select_recommended(options)
        return options

    def _years_beyond_outlook(
        self, option: MitigationOption, scenario: GrowthScenario,
    ) -> int | None:
        """Extra years of headroom a fix absorbs past the horizon, at the scenario growth rate.

        Every feasible mitigation is sized against the horizon-year load, so all of them clear
        the full outlook by construction; the differentiator is how far past it the resulting
        headroom stretches. Reported as whole years beyond the horizon. Conservative — it assumes
        all load keeps compounding, though step loads (e.g. a data center) do not.
        """
        if not option.available or option.resulting_utilization_pct is None:
            return None
        years = self._headroom_years(option.resulting_utilization_pct, scenario)
        # A load transfer also fills a neighbor; that receiver runs out of headroom first, so
        # report whichever transformer crosses the threshold sooner.
        if option.type == "load_transfer" and option.target_after_utilization_pct is not None:
            recv = self._headroom_years(option.target_after_utilization_pct, scenario)
            if years is not None and recv is not None:
                years = min(years, recv)
        return years

    def _headroom_years(self, util: float, scenario: GrowthScenario) -> int | None:
        """Whole years for `util` to grow back to the planning threshold at the scenario rate."""
        g = scenario.annual_growth_pct
        if g <= 0 or util <= 0 or util >= self.planning_threshold_pct:
            return None
        years = math.log(self.planning_threshold_pct / util) / math.log(1 + g / 100)
        return int(min(years, 20.0))

    def _headroom_label(self, resulting: float) -> str:
        if resulting <= HEADROOM_TARGET_PCT:
            return "Good headroom"
        return (
            f"Adequate — above the {HEADROOM_TARGET_PCT:.0f}% preferred target, "
            f"below the {self.planning_threshold_pct:.0f}% limit"
        )

    def _upgrade_option(
        self, rated: float, load_kva: float, cost_table: list[dict[str, Any]],
    ) -> MitigationOption:
        # Smallest standard size that clears the planning threshold (80% is the hard limit;
        # 75% is only the preferred target, not a reason to jump an extra size).
        new_size = next(
            (s for s in STANDARD_TRANSFORMER_SIZES_KVA
             if s > rated and load_kva / s * 100 < self.planning_threshold_pct), None
        )
        max_std = STANDARD_TRANSFORMER_SIZES_KVA[-1]
        if new_size is None:
            return MitigationOption(
                type="transformer_upgrade",
                label="Transformer Upgrade",
                description="Not available as standard replacement",
                available=False,
                unavailable_reason=f"Required size exceeds standard {max_std:.0f} kVA unit.",
            )
        resulting = load_kva / new_size * 100
        status = self._classify(resulting)
        low, high = self._lookup_cost(cost_table, "transformer_upgrade", new_size)
        return MitigationOption(
            type="transformer_upgrade",
            label="Transformer Upgrade",
            description=f"{rated:.0f} → {new_size:.0f} kVA",
            cost_low=low, cost_high=high,
            capacity_added_kva=new_size - rated,
            resulting_utilization_pct=round(resulting, 1),
            resulting_status=status,
            note=self._headroom_label(resulting),
        )

    def _parallel_option(
        self, rated: float, load_kva: float, cost_table: list[dict[str, Any]],
    ) -> MitigationOption:
        # Paralleled units should match the existing transformer (impedance/ratio must match
        # for proper load sharing), so floor the added unit at the existing rating; grow it
        # only if a matched unit still can't clear the planning threshold.
        added_size = next(
            (s for s in STANDARD_TRANSFORMER_SIZES_KVA
             if s >= rated and load_kva / (rated + s) * 100 < self.planning_threshold_pct), None
        )
        max_std = STANDARD_TRANSFORMER_SIZES_KVA[-1]
        if added_size is None:
            return MitigationOption(
                type="parallel_transformer",
                label="Parallel Transformer",
                description="Not available as standard unit",
                available=False,
                unavailable_reason=f"Required added capacity exceeds standard {max_std:.0f} kVA unit.",
            )
        effective = rated + added_size
        resulting = load_kva / effective * 100
        status = self._classify(resulting)
        low, high = self._lookup_cost(cost_table, "parallel_transformer", added_size)
        return MitigationOption(
            type="parallel_transformer",
            label="Parallel Transformer",
            description=f"Add matching {added_size:.0f} kVA unit",
            cost_low=low, cost_high=high,
            capacity_added_kva=added_size,
            resulting_utilization_pct=round(resulting, 1),
            resulting_status=status,
            note=self._headroom_label(resulting),
        )

    def _load_transfer_option(
        self, asset_id: str, feeder_id: str,
        feeder_state: dict[str, dict[str, float]],
        cost_table: list[dict[str, Any]],
    ) -> MitigationOption:
        state = feeder_state[asset_id]
        rated = state["rated_kva"]
        load_kva = state["proj_load_kva"]
        # Aim to bring the overloaded unit to the preferred headroom target (75%), but a
        # receiving transformer may only be filled up to the planning threshold (80%).
        source_frac = HEADROOM_TARGET_PCT / 100.0
        receiver_frac = (self.planning_threshold_pct - 0.1) / 100.0
        # Move enough to reach the target — no more than necessary, since every transferred
        # customer is a real switching operation.
        required_transfer = load_kva - rated * source_frac

        # Candidate neighbor: same-feeder transformer with the most spare capacity below the
        # planning threshold. Reachability/switching feasibility is not validated here.
        best_id: str | None = None
        best_avail = 0.0
        for nid, ns in feeder_state.items():
            if nid == asset_id:
                continue
            avail = ns["rated_kva"] * receiver_frac - ns["proj_load_kva"]
            if avail > best_avail:
                best_avail = avail
                best_id = nid

        if best_id is None or best_avail <= 0 or required_transfer <= 0:
            return MitigationOption(
                type="load_transfer",
                label="Load Transfer",
                description="Not available",
                available=False,
                unavailable_reason=f"No transformer on {feeder_id} has spare planning headroom to receive load.",
            )

        # Cap the transfer at what the neighbor can absorb without crossing the threshold.
        actual_transfer = min(required_transfer, best_avail)
        src_after = (load_kva - actual_transfer) / rated * 100
        if src_after >= self.planning_threshold_pct:
            return MitigationOption(
                type="load_transfer",
                label="Load Transfer",
                description="Not available",
                available=False,
                unavailable_reason=(
                    f"No single transformer on {feeder_id} can absorb enough to bring "
                    f"{asset_id} below the {self.planning_threshold_pct:.0f}% planning threshold."
                ),
            )

        ns = feeder_state[best_id]
        n_rated = ns["rated_kva"]
        n_load = ns["proj_load_kva"]
        # Distinguish "reached the 75% target" from "receiver ran out of headroom first" so the
        # card explains why the source doesn't land exactly at 75%.
        if actual_transfer < required_transfer - 1e-6:
            note = (
                f"Limited by receiving transformer capacity — "
                f"target {HEADROOM_TARGET_PCT:.0f}%, achievable {src_after:.1f}%"
            )
        else:
            note = self._headroom_label(src_after)
        low, high = self._lookup_cost(cost_table, "load_transfer", 0.0)
        return MitigationOption(
            type="load_transfer",
            label="Load Transfer",
            description=f"{actual_transfer:.0f} kVA → {best_id}",
            cost_low=low, cost_high=high,
            load_transferred_kva=round(actual_transfer, 1),
            resulting_utilization_pct=round(src_after, 1),
            resulting_status=self._classify(src_after),
            target_asset_id=best_id,
            target_before_utilization_pct=round(n_load / n_rated * 100, 1),
            target_after_utilization_pct=round((n_load + actual_transfer) / n_rated * 100, 1),
            note=note,
        )

    def _select_recommended(self, options: list[MitigationOption]) -> None:
        """Flag the best-value fix, and the most durable one when they diverge (fix-now vs fix-right).

        All three strategies compete on cost-per-year-of-headroom (tie-broken by lower total cost,
        then more years); the winner is marked `recommended` (best value). A load transfer is cheap
        and can win when growth is slow enough that the few years it buys still beat a durable fix
        per dollar. When that happens the tool does not silently pick a deferral over a capacity
        add: it also flags the longest-lived capital fix as `most_durable`, so the planner sees both
        the fix-it-now and fix-it-right options and chooses. The card shows years, $/yr, and the
        switching-feasibility caveat.
        """
        def cost_mid(o: MitigationOption) -> float:
            if o.cost_low is None or o.cost_high is None:
                return float("inf")
            return (o.cost_low + o.cost_high) / 2

        def value_key(o: MitigationOption) -> tuple[float, float, int]:
            mid = cost_mid(o)
            years = o.years_gained or 0
            cost_per_year = mid / years if years > 0 else float("inf")
            return (cost_per_year, mid, -years)

        feasible = [
            o for o in options
            if o.available and o.resulting_utilization_pct is not None
            and o.resulting_utilization_pct < self.planning_threshold_pct
        ]
        if not feasible:
            return
        feasible.sort(key=value_key)
        best = feasible[0]
        best.recommended = True

        # If a stopgap won on value, surface the longest-lived capital fix as the durable
        # alternative so the fix-now/fix-right tradeoff stays the planner's call.
        if best.type == "load_transfer":
            capital = [o for o in feasible
                       if o.type in ("transformer_upgrade", "parallel_transformer")]
            if capital:
                capital.sort(key=lambda o: (-(o.years_gained or 0), cost_mid(o)))
                capital[0].most_durable = True

    def _lookup_cost(
        self, cost_table: list[dict[str, Any]], mtype: str, kva: float,
    ) -> tuple[int | None, int | None]:
        rows = [r for r in cost_table if r.get("mitigation_type") == mtype]
        rows.sort(key=lambda r: (r.get("kva_max") is None, r.get("kva_max") or 0))
        for r in rows:
            kmax = r.get("kva_max")
            if kmax is None or kva <= kmax:
                return int(r["cost_low"]), int(r["cost_high"])
        return None, None

    def _build_summary(
        self,
        scenario: GrowthScenario,
        feeder_projections: list[FeederProjection],
        asset_projections: list[AssetProjection],
        total_new_load: float,
    ) -> str:
        parts: list[str] = []
        period = f"within {scenario.horizon_years} year{'s' if scenario.horizon_years > 1 else ''}"

        overloaded_feeders = [f for f in feeder_projections if f.status == "overloaded"]
        at_risk_feeders = [f for f in feeder_projections if f.status == "at_risk"]
        overloaded_assets = [a for a in asset_projections if a.status == "overloaded"]
        at_risk_assets = [a for a in asset_projections if a.status == "at_risk"]

        if overloaded_feeders:
            ids = ", ".join(f.feeder_id for f in overloaded_feeders)
            parts.append(f"Feeder{'s' if len(overloaded_feeders) > 1 else ''} {ids} "
                         f"would exceed rated capacity {period}.")

        if at_risk_feeders:
            ids = ", ".join(f.feeder_id for f in at_risk_feeders)
            parts.append(f"Feeder{'s' if len(at_risk_feeders) > 1 else ''} {ids} "
                         f"would exceed {self.planning_threshold_pct:.0f}% planning threshold.")

        all_flagged = overloaded_assets + at_risk_assets
        newly = [a for a in all_flagged if a.newly_at_risk]
        baseline = [a for a in all_flagged if not a.newly_at_risk]

        if newly:
            parts.append(f"{len(newly)} transformer{'s' if len(newly) > 1 else ''} "
                         f"newly cross{'es' if len(newly) == 1 else ''} "
                         f"the planning threshold due to this scenario.")
        if baseline:
            parts.append(f"{len(baseline)} transformer{'s' if len(baseline) > 1 else ''} "
                         f"{'was' if len(baseline) == 1 else 'were'} already "
                         f"above the planning threshold at baseline.")

        has_solar = scenario.der_solar_kw > 0
        no_issues = not overloaded_feeders and not at_risk_feeders and not all_flagged

        if no_issues and has_solar:
            parts.append(f"Feeder net load reduced; no thermal capacity violations detected {period}. "
                         f"Segment-level reverse power flow and voltage rise not evaluated.")
        elif no_issues:
            parts.append(f"All feeders and transformers remain within planning thresholds {period}.")

        if scenario.ev_adoption_pct > 0:
            parts.append(f"EV load assumes {self.ev_coincidence_factor:.0%} simultaneous charging factor.")

        parts.append(f"Estimated total new demand: {total_new_load:.2f} MW "
                     f"(power-flow simulation, PF={self.power_factor}).")

        return " ".join(parts)
