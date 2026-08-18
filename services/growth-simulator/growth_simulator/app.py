# This project was developed with assistance from AI tools.

"""Growth Simulator — FastAPI application for grid capacity prediction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
import structlog
from fastapi import FastAPI, HTTPException

from grid_common.logging import setup_logging
from growth_simulator.powerflow import PowerFlowPredictor
from growth_simulator.predictor import (
    GrowthPrediction,
    GrowthPredictor,
    GrowthScenario,
)
from growth_simulator.presets import PRESETS
from growth_simulator.settings import GrowthSimulatorSettings

logger = structlog.get_logger()
settings = GrowthSimulatorSettings()
predictor: GrowthPredictor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global predictor
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    predictor = PowerFlowPredictor(
        power_factor=settings.power_factor,
        residential_load_kw=settings.residential_load_kw,
        ev_charger_load_kw=settings.ev_charger_load_kw,
        ev_coincidence_factor=settings.ev_coincidence_factor,
        solar_capacity_factor=settings.solar_capacity_factor,
        planning_threshold_pct=settings.planning_threshold_pct,
        overload_threshold_pct=settings.overload_threshold_pct,
    )
    logger.info("growth_simulator_started")
    yield
    logger.info("growth_simulator_stopped")


app = FastAPI(title="Growth Simulator", lifespan=lifespan)


def _load_grid_data() -> dict[str, Any]:
    """Load current grid state from PostgreSQL."""
    with psycopg.connect(settings.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, substation_id, name, normal_capacity_mw, emergency_capacity_mw, "
                "current_load_mw, peak_load_mw FROM feeders"
            )
            cols = [d[0] for d in (cur.description or [])]
            feeders = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

            cur.execute(
                "SELECT id, asset_type, feeder_id, rated_kva, rated_voltage_kv, "
                "customers_downstream, lat, lon, vk_percent, vkr_percent, i0_percent, pfe_kw "
                "FROM assets WHERE asset_type = 'transformer' "
                "AND subtype = 'pad_mount' AND status = 'in_service'"
            )
            cols = [d[0] for d in (cur.description or [])]
            transformers = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

            cur.execute(
                "SELECT id, asset_type, subtype, feeder_id, rated_kva, rated_voltage_kv, "
                "customers_downstream, lat, lon, vk_percent, vkr_percent, i0_percent, pfe_kw "
                "FROM assets WHERE asset_type = 'transformer' "
                "AND subtype = 'power_transformer' AND status = 'in_service'"
            )
            cols = [d[0] for d in (cur.description or [])]
            substation_transformers = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

            cur.execute(
                "SELECT id, asset_type, feeder_id, customers_downstream, lat, lon "
                "FROM assets WHERE status = 'in_service'"
            )
            cols = [d[0] for d in (cur.description or [])]
            assets = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

            cur.execute(
                "SELECT id, feeder_id, from_asset_id, to_asset_id, conductor_type, "
                "length_m, ampacity_a FROM segments WHERE status = 'energized'"
            )
            cols = [d[0] for d in (cur.description or [])]
            segments = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

            cur.execute("SELECT name, r_ohm_per_km, x_ohm_per_km, c_nf_per_km, max_i_ka FROM conductor_types")
            cols = [d[0] for d in (cur.description or [])]
            conductor_rows = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
            conductor_types = {r["name"]: r for r in conductor_rows}

            # Optional table — guard so a not-yet-migrated DB doesn't 500 the endpoint.
            mitigation_costs: list[dict[str, Any]] = []
            cur.execute("SELECT to_regclass('public.mitigation_costs')")
            if (cur.fetchone() or [None])[0] is not None:
                cur.execute("SELECT mitigation_type, kva_max, cost_low, cost_high FROM mitigation_costs")
                cols = [d[0] for d in (cur.description or [])]
                mitigation_costs = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    return {
        "feeders": feeders,
        "transformers": transformers,
        "substation_transformers": substation_transformers,
        "all_assets": assets,
        "assets": assets,
        "segments": segments,
        "conductor_types": conductor_types,
        "mitigation_costs": mitigation_costs,
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if predictor is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    return {"status": "ready"}


@app.get("/growth/presets")
async def get_presets() -> list[GrowthScenario]:
    """Return available preset scenarios."""
    return PRESETS


@app.post("/growth/predict")
async def run_prediction(scenario: GrowthScenario) -> GrowthPrediction:
    """Run a growth prediction for the given scenario."""
    if predictor is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    try:
        grid_data = _load_grid_data()
    except Exception as e:
        logger.error("grid_data_load_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load grid data") from e

    result = predictor.predict(scenario, grid_data)
    logger.info(
        "prediction_complete",
        scenario=scenario.name,
        new_load_mw=result.total_new_load_mw,
        flagged_assets=len([a for a in result.at_risk_assets if a.status != "ok"]),
    )
    return result


@app.get("/growth/feeders")
async def get_feeders() -> list[dict[str, Any]]:
    """Return current feeder data."""
    try:
        grid_data = _load_grid_data()
    except Exception as e:
        logger.error("grid_data_load_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load grid data") from e
    return grid_data["feeders"]
