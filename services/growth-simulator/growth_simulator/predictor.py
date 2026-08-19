# This project was developed with assistance from AI tools.

"""Growth prediction models and computation."""

from __future__ import annotations

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


class MitigationOption(BaseModel):
    """One evaluated mitigation strategy for a constrained transformer."""

    type: str
    label: str
    description: str
    available: bool = True
    unavailable_reason: str | None = None
    cost_low: int | None = None
    cost_high: int | None = None
    capacity_added_kva: float | None = None
    load_transferred_kva: float | None = None
    resulting_utilization_pct: float | None = None
    resulting_status: str | None = None
    target_asset_id: str | None = None
    target_before_utilization_pct: float | None = None
    target_after_utilization_pct: float | None = None
    years_gained: int | None = None
    recommended: bool = False
    most_durable: bool = False
    note: str = ""


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
    mitigations: list[MitigationOption] = Field(default_factory=list)
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


