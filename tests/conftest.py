import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A fresh, initialised database in a temp folder; yields the app.db module."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from app import db as db_module

    db_module.init_db()
    return db_module
