"""SQLite access for CiviSort."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_code TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    photo_filename TEXT,
    after_photo_filename TEXT,
    evidence_status TEXT NOT NULL DEFAULT 'unverified',
    repair_status TEXT NOT NULL DEFAULT 'reported',
    severity INTEGER,
    exposure INTEGER,
    vulnerability REAL,
    school_access INTEGER NOT NULL DEFAULT 0,
    estimated_cost INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 1,
    primary_report_id INTEGER,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY (primary_report_id) REFERENCES reports(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES reports(id)
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget INTEGER NOT NULL,
    rain INTEGER NOT NULL,
    night INTEGER NOT NULL,
    school_hours INTEGER NOT NULL,
    selected_json TEXT NOT NULL,
    total_points REAL NOT NULL,
    actual_spend INTEGER NOT NULL,
    remaining INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_e=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Non-destructive migrations for databases created by earlier versions.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(plans)")}
    if "label" not in cols:
        conn.execute("ALTER TABLE plans ADD COLUMN label TEXT")
    if "is_synthetic" not in cols:
        conn.execute("ALTER TABLE plans ADD COLUMN is_synthetic INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def init_app_db(app) -> None:
    app.teardown_appcontext(close_db)

    # Create tables up front (idempotent) so seeding before the first request works.
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    boot = connect_path(app.config["DATABASE"])
    boot.close()

    @app.before_request
    def _ensure_schema():
        db = get_db()
        init_schema(db)


def connect_path(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
    return conn
