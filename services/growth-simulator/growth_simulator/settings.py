# This project was developed with assistance from AI tools.

from __future__ import annotations

from grid_common.settings import ServiceSettings


class GrowthSimulatorSettings(ServiceSettings):
    """Growth Simulator configuration."""

    otel_service_name: str = "growth-simulator"
    kafka_consumer_group_id: str = "growth-simulator"
    power_factor: float = 0.95
    residential_load_kw: float = 4.0
    ev_charger_load_kw: float = 7.2
    ev_coincidence_factor: float = 0.35
    solar_capacity_factor: float = 0.25
    planning_threshold_pct: float = 80.0
    overload_threshold_pct: float = 100.0
    host: str = "0.0.0.0"
    port: int = 8080
