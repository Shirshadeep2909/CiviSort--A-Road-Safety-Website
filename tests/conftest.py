from __future__ import annotations

import pytest

from civisort import create_app
from civisort.db import get_db, init_schema


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "civisort.sqlite3"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        }
    )
    with app.app_context():
        init_schema(get_db())
    return app


@pytest.fixture
def client(app):
    return app.test_client()
