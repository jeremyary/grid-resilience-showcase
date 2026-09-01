#!/usr/bin/env python3
# This project was developed with assistance from AI tools.
"""Apply schema.sql to PostgreSQL."""
import sys
from pathlib import Path
import psycopg

dsn = sys.argv[1] if len(sys.argv) > 1 else "postgresql://gridops:gridops@localhost:5432/gridops"
schema = Path(__file__).parent / "schema.sql"
conn = psycopg.connect(dsn)
conn.execute(schema.read_text())
conn.commit()
conn.close()
print("Schema applied.")
