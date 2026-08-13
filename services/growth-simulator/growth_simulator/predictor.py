# This project was developed with assistance from AI tools.

"""Growth prediction models and computation."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class GrowthScenario(BaseModel):
    """Input parameters for a growth prediction."""

    name: str
    description: str = ""
    feeder_ids: list[str] = Field(default_factory=list, description="Empty = all feeders")
    new_residential: int = Field(default=0, ge=0)
    ev_adoption_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    der_solar_kw: float = Field(default=0.0, ge=0.0)
    annual_growth_pct: float = Field(default=0.0, ge=0.0, le=20.0)
    horizon_years: int = Field(default=5, ge=1, le=30)


class FeederProjection(BaseModel):
    """Projected status for a feeder."""

    feeder_id: str
    feeder_name: str
    current_load_mw: float
    projected_load_mw: float
    normal_capacity_mw: float
    emergency_capacity_mw: float
    current_utilization_pct: float
    projected_utilization_pct: float
    status: str
    overload_year: int | None = None
    headroom_mw: float


class AssetProjection(BaseModel):
    """Projected status for a single transformer."""

    asset_id: str
    asset_type: str
    feeder_id: str
    rated_kva: float
    current_load_kva: float
    projected_load_kva: float
    current_utilization_pct: float
    projected_utilization_pct: float
    baseline_status: str
    status: str
    newly_at_risk: bool = False
    overload_year: int | None = None
    recommendation: str = ""
    lat: float
    lon: float


class YearlySnapshot(BaseModel):
    """Utilization snapshot for a single year across all assets and feeders."""

    year: int
    feeder_utilization_pct: dict[str, float] = Field(default_factory=dict)
    feeder_load_mw: dict[str, float] = Field(default_factory=dict)
    asset_utilization_pct: dict[str, float] = Field(default_factory=dict)


class GrowthPrediction(BaseModel):
    """Full prediction result."""

    scenario: GrowthScenario
    feeders: list[FeederProjection]
    at_risk_assets: list[AssetProjection]
    summary: str
    total_new_load_mw: float
    corridor_utilization_pct: float
    yearly_projections: list[YearlySnapshot] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

STANDARD_TRANSFORMER_SIZES_KVA = [167, 250, 500, 750, 1000, 1500, 2500]


class GrowthPredictor(ABC):
    """Abstract interface for growth prediction — swap in an ML model later."""

    @abstractmethod
    def predict(self, scenario: GrowthScenario, grid_data: dict[str, Any]) -> GrowthPrediction:
        """Run prediction given a scenario and current grid state."""


# ---------------------------------------------------------------------------
# Computational implementation
# ---------------------------------------------------------------------------


class ComputationalPredictor(GrowthPredictor):
    """Rule-based computational predictor (no GPU required)."""

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
        all_assets = grid_data.get("all_assets", [])

        target_feeders = [f for f in feeders if not scenario.feeder_ids or f["id"] in scenario.feeder_ids]

        feeder_projections: list[FeederProjection] = []
        asset_projections: list[AssetProjection] = []
        total_new_load_mw = 0.0

        for feeder in target_feeders:
            fid = feeder["id"]
            current_load = feeder["current_load_mw"]
            normal_cap = feeder["normal_capacity_mw"]
            emergency_cap = feeder.get("emergency_capacity_mw") or normal_cap * 1.2

            feeder_transformers = [t for t in transformers if t["feeder_id"] == fid]
            feeder_assets = [a for a in all_assets if a.get("feeder_id") == fid]
            total_feeder_customers = max(
                (a["customers_downstream"] for a in feeder_assets),
                default=sum(t["customers_downstream"] for t in feeder_transformers),
            )
            total_transformer_customers = sum(t["customers_downstream"] for t in feeder_transformers)

            new_load_mw = self._compute_feeder_new_load(scenario, feeder, total_feeder_customers)
            organic_factor = (1 + scenario.annual_growth_pct / 100) ** scenario.horizon_years
            projected_load = current_load * organic_factor + new_load_mw
            total_new_load_mw += projected_load - current_load

            overload_year = self._find_overload_year(
                current_load, new_load_mw, scenario.annual_growth_pct,
                normal_cap, scenario.horizon_years,
            )

            feeder_util = round(projected_load / normal_cap * 100, 1)
            feeder_projections.append(FeederProjection(
                feeder_id=fid,
                feeder_name=feeder["name"],
                current_load_mw=round(current_load, 2),
                projected_load_mw=round(projected_load, 2),
                normal_capacity_mw=normal_cap,
                emergency_capacity_mw=emergency_cap,
                current_utilization_pct=round(current_load / normal_cap * 100, 1),
                projected_utilization_pct=feeder_util,
                status=self._classify(feeder_util),
                overload_year=overload_year,
                headroom_mw=round(normal_cap - projected_load, 2),
            ))

            for t in feeder_transformers:
                proj = self._project_transformer(
                    t, feeder, scenario, total_feeder_customers,
                    total_transformer_customers, new_load_mw, organic_factor,
                )
                asset_projections.append(proj)

        asset_projections.sort(key=lambda a: a.projected_utilization_pct, reverse=True)

        corridor_load = sum(f["current_load_mw"] for f in feeders)
        corridor_cap = sum(f["normal_capacity_mw"] for f in feeders)
        corridor_new = corridor_load + total_new_load_mw
        corridor_util = corridor_new / corridor_cap * 100 if corridor_cap else 0

        overloaded_feeders = [f for f in feeder_projections if f.status == "overloaded"]
        at_risk_feeders = [f for f in feeder_projections if f.status == "at_risk"]
        overloaded_assets = [a for a in asset_projections if a.status == "overloaded"]
        at_risk_assets = [a for a in asset_projections if a.status == "at_risk"]

        summary = self._build_summary(
            scenario, overloaded_feeders, at_risk_feeders,
            overloaded_assets, at_risk_assets, total_new_load_mw,
        )

        return GrowthPrediction(
            scenario=scenario,
            feeders=feeder_projections,
            at_risk_assets=asset_projections,
            summary=summary,
            total_new_load_mw=round(total_new_load_mw, 2),
            corridor_utilization_pct=round(corridor_util, 1),
        )

    def _compute_feeder_new_load(
        self, scenario: GrowthScenario, feeder: dict[str, Any],
        total_feeder_customers: int,
    ) -> float:
        """Compute additional MW load on a feeder from the scenario (excluding organic growth)."""
        new_mw = 0.0

        if scenario.new_residential > 0 and total_feeder_customers > 0:
            feeder_share = 1.0 if len(scenario.feeder_ids) <= 1 else 1.0 / len(scenario.feeder_ids)
            homes = scenario.new_residential * feeder_share
            new_mw += homes * self.residential_load_kw / 1000

        if scenario.ev_adoption_pct > 0 and total_feeder_customers > 0:
            ev_customers = total_feeder_customers * scenario.ev_adoption_pct / 100
            new_mw += ev_customers * self.ev_charger_load_kw * self.ev_coincidence_factor / 1000

        if scenario.der_solar_kw > 0:
            feeder_share = 1.0 if len(scenario.feeder_ids) <= 1 else 1.0 / len(scenario.feeder_ids)
            solar_mw = scenario.der_solar_kw / 1000 * self.solar_capacity_factor * feeder_share
            new_mw -= solar_mw

        return max(new_mw, 0.0)

    def _project_transformer(
        self, t: dict[str, Any], feeder: dict[str, Any],
        scenario: GrowthScenario, total_feeder_customers: int,
        total_transformer_customers: int,
        feeder_new_load_mw: float, organic_factor: float,
    ) -> AssetProjection:
        """Project load on a single transformer."""
        rated_kva = t.get("rated_kva") or 500
        customers = t["customers_downstream"]
        feeder_load = feeder["current_load_mw"]

        # Current load: allocate feeder load by share of total feeder customers
        if total_feeder_customers > 0:
            load_share = customers / total_feeder_customers
        else:
            load_share = 0.0

        current_load_kw = feeder_load * 1000 * load_share
        current_load_kva = current_load_kw / self.power_factor

        # New load: distribute among transformers by share of transformer customers
        if total_transformer_customers > 0:
            new_load_share = customers / total_transformer_customers
        else:
            new_load_share = 0.0

        new_load_kw = feeder_new_load_mw * 1000 * new_load_share
        projected_load_kva = (current_load_kw * organic_factor + new_load_kw) / self.power_factor

        current_util = current_load_kva / rated_kva * 100 if rated_kva else 0
        projected_util = projected_load_kva / rated_kva * 100 if rated_kva else 0
        baseline_status = self._classify(current_util)
        status = self._classify(projected_util)
        newly_at_risk = baseline_status == "ok" and status != "ok"

        overload_year = None
        if status != "ok":
            threshold_kva = rated_kva * self.planning_threshold_pct / 100
            overload_year = self._find_transformer_overload_year(
                current_load_kva, new_load_kw / self.power_factor,
                scenario.annual_growth_pct, threshold_kva,
                scenario.horizon_years,
            )

        recommendation = ""
        if status != "ok":
            target_kva = projected_load_kva / (self.planning_threshold_pct / 100)
            recommendation = self._recommend_transformer_size(target_kva)

        return AssetProjection(
            asset_id=t["id"],
            asset_type="transformer",
            feeder_id=feeder["id"],
            rated_kva=rated_kva,
            current_load_kva=round(current_load_kva, 1),
            projected_load_kva=round(projected_load_kva, 1),
            current_utilization_pct=round(current_util, 1),
            projected_utilization_pct=round(projected_util, 1),
            baseline_status=baseline_status,
            status=status,
            newly_at_risk=newly_at_risk,
            overload_year=overload_year,
            recommendation=recommendation,
            lat=t["lat"],
            lon=t["lon"],
        )

    def _find_overload_year(
        self, current_load: float, new_load: float, growth_pct: float,
        capacity: float, horizon: int,
    ) -> int | None:
        """Find the first year where projected load exceeds capacity."""
        for year in range(1, horizon + 1):
            organic = current_load * (1 + growth_pct / 100) ** year
            projected = organic + new_load
            if projected > capacity:
                return year
        return None

    def _find_transformer_overload_year(
        self, current_kva: float, new_kva: float, growth_pct: float,
        threshold_kva: float, horizon: int,
    ) -> int | None:
        for year in range(1, horizon + 1):
            organic = current_kva * (1 + growth_pct / 100) ** year
            projected = organic + new_kva
            if projected > threshold_kva:
                return year
        return None

    def _recommend_transformer_size(self, target_kva: float) -> str:
        for size in STANDARD_TRANSFORMER_SIZES_KVA:
            if size >= target_kva:
                return f"Upgrade to {size} kVA transformer"
        return f"Upgrade to {math.ceil(target_kva / 100) * 100} kVA (non-standard, requires engineering review)"

    def _build_summary(
        self, scenario: GrowthScenario,
        overloaded_feeders: list[FeederProjection],
        at_risk_feeders: list[FeederProjection],
        overloaded_assets: list[AssetProjection],
        at_risk_assets: list[AssetProjection],
        total_new_load: float,
    ) -> str:
        parts = []
        period = f"within {scenario.horizon_years} year{'s' if scenario.horizon_years > 1 else ''}"

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
                     f"(load allocation estimated by customer count, PF={self.power_factor}).")

        return " ".join(parts)
