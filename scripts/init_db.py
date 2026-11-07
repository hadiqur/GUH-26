"""Create (or upgrade) the database:  python scripts/init_db.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import db_path, get_conn, init_db  # noqa: E402

init_db()
print(f"Database: {db_path()}")
with get_conn() as conn:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
print(f"Schema version: {version}")
print("Tables: " + ", ".join(tables))
