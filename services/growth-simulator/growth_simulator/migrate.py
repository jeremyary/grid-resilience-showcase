# This project was developed with assistance from AI tools.

"""Apply pending SQL migrations. Each migration file is idempotent, so re-running is safe."""

from __future__ import annotations

from pathlib import Path

import psycopg
import structlog

from growth_simulator.settings import GrowthSimulatorSettings

logger = structlog.get_logger()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_FILES = ["migrate_powerflow.sql", "migrate_mitigation_costs.sql"]


def main() -> None:
    settings = GrowthSimulatorSettings()
    with psycopg.connect(settings.dsn) as conn:
        for filename in MIGRATION_FILES:
            sql = (MIGRATIONS_DIR / filename).read_text()
            logger.info("applying_migration", file=filename)
            with conn.cursor() as cur:
                cur.execute(sql)
    logger.info("migrations_complete")


if __name__ == "__main__":
    main()
