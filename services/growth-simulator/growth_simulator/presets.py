# This project was developed with assistance from AI tools.

"""Preset growth scenarios for the demo."""

from __future__ import annotations

from growth_simulator.predictor import GrowthScenario

PRESETS: list[GrowthScenario] = [
    GrowthScenario(
        name="200 New Homes on F-12",
        description="Residential development adds 200 homes to the Burlington South feeder.",
        feeder_ids=["F-12"],
        new_residential=200,
        horizon_years=3,
    ),
    GrowthScenario(
        name="30% EV Adoption Corridor-Wide",
        description="30% of existing customers adopt Level 2 EV chargers across all feeders.",
        ev_adoption_pct=30.0,
        horizon_years=5,
    ),
    GrowthScenario(
        name="2 MW Solar Farm on F-13",
        description="Distributed solar generation reduces net load on the Mebane West feeder.",
        feeder_ids=["F-13"],
        der_solar_kw=2000,
        horizon_years=5,
    ),
    GrowthScenario(
        name="5-Year Organic Growth (2%/yr)",
        description="Baseline load growth at 2% annually across the corridor.",
        annual_growth_pct=2.0,
        horizon_years=5,
    ),
]
