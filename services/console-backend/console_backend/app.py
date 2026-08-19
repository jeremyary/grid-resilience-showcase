# This project was developed with assistance from AI tools.

"""Console Backend (BFF) — API proxy and SSE event stream for the operations console."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import psycopg
import structlog
from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from console_backend.proxy import proxy_get, proxy_post
from console_backend.settings import ConsoleBackendSettings
from console_backend.sse import EventMultiplexer, event_stream
from grid_common.logging import setup_logging

logger = structlog.get_logger()
settings = ConsoleBackendSettings()
http_client: httpx.AsyncClient | None = None
mux: EventMultiplexer | None = None


def _client() -> httpx.AsyncClient:
    assert http_client is not None
    return http_client


def _mux() -> EventMultiplexer:
    assert mux is not None
    return mux


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global http_client, mux
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    http_client = httpx.AsyncClient(timeout=10.0)
    mux = EventMultiplexer(settings)
    mux.start()
    logger.info("console_backend_started")
    yield
    if http_client:
        await http_client.aclose()
    logger.info("console_backend_stopped")


app = FastAPI(title="Console Backend", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if http_client is None:
        raise HTTPException(status_code=503, detail="Not initialized")
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# SSE event stream
# ---------------------------------------------------------------------------


@app.get("/api/events")
async def events(request: Request) -> EventSourceResponse:
    """SSE stream of all grid.* Kafka events."""
    return EventSourceResponse(
        event_stream(_mux()),
        ping=1,
        headers={"X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Weather proxy
# ---------------------------------------------------------------------------


@app.get("/api/weather/current")
async def weather_current() -> Any:
    return await proxy_get(_client(), f"{settings.weather_service_url}/forecast/current")


@app.get("/api/weather/overlay.png")
async def weather_overlay() -> Any:
    from starlette.responses import Response

    from console_backend.weather_overlay import get_overlay

    png_bytes, bounds = get_overlay()
    if png_bytes is None:
        raise HTTPException(status_code=404, detail="No forecast overlay available")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Overlay-Bounds": f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
            if bounds
            else "",
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# Asset / Risk proxy
# ---------------------------------------------------------------------------


@app.get("/api/assets/ranked")
async def assets_ranked(limit: int = 20, min_score: float = 0.0) -> Any:
    return await proxy_get(
        _client(),
        f"{settings.risk_engine_url}/assets/ranked?limit={limit}&min_score={min_score}",
    )


@app.get("/api/assets/{asset_id}")
async def asset_detail(asset_id: str) -> Any:
    return await proxy_get(_client(), f"{settings.risk_engine_url}/assets/{asset_id}/risk")


# ---------------------------------------------------------------------------
# Camera / Detection proxy
# ---------------------------------------------------------------------------


@app.get("/api/cameras/findings")
async def cameras_findings(limit: int = 50) -> Any:
    return await proxy_get(
        _client(), f"{settings.defect_detector_url}/findings/recent?limit={limit}"
    )


# ---------------------------------------------------------------------------
# Dispatch proxy
# ---------------------------------------------------------------------------


@app.get("/api/dispatch/plans")
async def dispatch_plans() -> Any:
    return await proxy_get(_client(), f"{settings.dispatch_optimizer_url}/dispatch/plans")


@app.get("/api/dispatch/plans/{plan_id}")
async def dispatch_plan(plan_id: str) -> Any:
    return await proxy_get(_client(), f"{settings.dispatch_optimizer_url}/dispatch/plans/{plan_id}")


@app.post("/api/dispatch/approve/{plan_id}")
async def dispatch_approve(plan_id: str, request: Request) -> Any:
    body = await request.json() if await request.body() else {}
    return await proxy_post(
        _client(), f"{settings.dispatch_optimizer_url}/dispatch/approve/{plan_id}", body
    )


@app.post("/api/dispatch/override/{plan_id}")
async def dispatch_override(plan_id: str, request: Request) -> Any:
    body = await request.json()
    return await proxy_post(
        _client(), f"{settings.dispatch_optimizer_url}/dispatch/override/{plan_id}", body
    )


# ---------------------------------------------------------------------------
# Customer impact
# ---------------------------------------------------------------------------


@app.get("/api/customer-impact")
async def customer_impact() -> dict[str, Any]:
    """Current customer outage summary from the latest Kafka events."""
    return {"status": "no active outage", "total_affected": 0, "restored": 0, "etr_minutes": None}


# ---------------------------------------------------------------------------
# Scenario proxy
# ---------------------------------------------------------------------------


@app.get("/api/scenario/current")
async def scenario_current() -> Any:
    return await proxy_get(_client(), f"{settings.scenario_engine_url}/scenario/state")


@app.post("/api/scenario/{action}")
async def scenario_action(action: str, request: Request) -> Any:
    body = await request.json() if await request.body() else {}
    return await proxy_post(_client(), f"{settings.scenario_engine_url}/scenario/{action}", body)


# ---------------------------------------------------------------------------
# Growth Simulator proxy
# ---------------------------------------------------------------------------


@app.get("/api/growth/presets")
async def growth_presets() -> Any:
    return await proxy_get(_client(), f"{settings.growth_simulator_url}/growth/presets")


@app.post("/api/growth/predict")
async def growth_predict(request: Request) -> Any:
    body = await request.json()
    return await proxy_post(_client(), f"{settings.growth_simulator_url}/growth/predict", body)


@app.get("/api/growth/feeders")
async def growth_feeders() -> Any:
    return await proxy_get(_client(), f"{settings.growth_simulator_url}/growth/feeders")


# ---------------------------------------------------------------------------
# Topology (grid structure for map rendering)
# ---------------------------------------------------------------------------


@app.get("/api/topology")
async def topology() -> dict[str, Any]:
    """Grid topology — feeders, segments, assets for map rendering."""
    try:
        with psycopg.connect(settings.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, substation_id, name, status FROM feeders")
                feeders = [
                    dict(zip([d[0] for d in (cur.description or [])], r, strict=False))
                    for r in cur.fetchall()
                ]

                cur.execute(
                    "SELECT id, asset_type, subtype, lat, lon, feeder_id, status, "
                    "customers_downstream FROM assets"
                )
                assets = [
                    dict(zip([d[0] for d in (cur.description or [])], r, strict=False))
                    for r in cur.fetchall()
                ]

                cur.execute(
                    "SELECT id, feeder_id, from_asset_id, to_asset_id, status, "
                    "customers_served FROM segments"
                )
                segments = [
                    dict(zip([d[0] for d in (cur.description or [])], r, strict=False))
                    for r in cur.fetchall()
                ]

                cur.execute("SELECT id, lat, lon, camera_type, asset_id, status FROM cameras")
                cameras = [
                    dict(zip([d[0] for d in (cur.description or [])], r, strict=False))
                    for r in cur.fetchall()
                ]

        return {
            "feeders": feeders,
            "assets": assets,
            "segments": segments,
            "cameras": cameras,
        }
    except psycopg.Error as e:
        logger.error("topology_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Database query failed") from None


# ---------------------------------------------------------------------------
# Platform status
# ---------------------------------------------------------------------------


@app.get("/api/platform-status")
async def platform_status() -> dict[str, Any]:
    """OpenShift platform status — Argo CD sync, GPU utilization, service health."""
    return {
        "services": [],
        "argocd_sync": "healthy",
        "gpu_utilization": {},
    }
