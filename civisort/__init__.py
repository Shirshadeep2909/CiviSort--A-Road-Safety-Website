"""CiviSort local Flask application factory."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
# CIVISORT_DATA_DIR lets you point the app at a separate data folder (e.g. for verification).
if os.environ.get("CIVISORT_DATA_DIR"):
    DATA_DIR = Path(os.environ["CIVISORT_DATA_DIR"]).resolve()
    UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "civisort.sqlite3"


def create_app(test_config: dict | None = None) -> Flask:
    from civisort.db import init_app_db
    from civisort.web import register_routes

    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config.update(
        SECRET_KEY="civisort-local-demo",
        DATABASE=str(DATABASE_PATH),
        UPLOAD_DIR=str(UPLOAD_DIR),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    init_app_db(app)
    register_routes(app)
    return app
