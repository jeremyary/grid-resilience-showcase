# This project was developed with assistance from AI tools.

from __future__ import annotations

from grid_common.settings import ServiceSettings


class ConsoleBackendSettings(ServiceSettings):
    """Console Backend (BFF) configuration."""

    otel_service_name: str = "console-backend"
    kafka_consumer_group_id: str = "console-backend"
    weather_service_url: str = "http://localhost:8081"
    risk_engine_url: str = "http://localhost:8083"
    defect_detector_url: str = "http://localhost:8084"
    dispatch_optimizer_url: str = "http://localhost:8085"
    scenario_engine_url: str = "http://localhost:8080"
    growth_simulator_url: str = "http://localhost:8086"
    host: str = "0.0.0.0"
    port: int = 8090
