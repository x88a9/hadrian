"""Shared pytest fixtures.

Integration tests run against the dev_db Postgres server (Port 55432, siehe
backend/scripts/dev_db.sh) in einer separaten Datenbank `hadrian3_test`. Ist der
Server nicht erreichbar, werden die Integrationstests automatisch geskippt, damit
die reinen Unit-Tests (z. B. test_health) ohne DB laufen.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://hadrian3:hadrian3@127.0.0.1:55432/hadrian3_test",
)


def _psycopg_dsn(sqlalchemy_url: str) -> str:
    """SQLAlchemy-URL (postgresql+psycopg://...) → psycopg-Verbindungs-URL."""
    parts = urlsplit(sqlalchemy_url)
    return urlunsplit(parts._replace(scheme="postgresql"))


def _server_reachable(sqlalchemy_url: str) -> bool:
    parts = urlsplit(sqlalchemy_url)
    admin = urlunsplit(parts._replace(scheme="postgresql", path="/postgres"))
    try:
        with psycopg.connect(admin, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001
        return False


def _ensure_test_database(sqlalchemy_url: str) -> None:
    """Create the test database if it is missing (connects to `postgres`)."""
    parts = urlsplit(sqlalchemy_url)
    dbname = parts.path.lstrip("/")
    admin = urlunsplit(parts._replace(scheme="postgresql", path="/postgres"))
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')


@pytest.fixture(scope="session")
def db_engine():
    if not _server_reachable(TEST_DATABASE_URL):
        pytest.skip(
            f"Postgres-Server fuer Integrationstests nicht erreichbar ({TEST_DATABASE_URL}). "
            "Server via `bash backend/scripts/dev_db.sh` starten."
        )

    _ensure_test_database(TEST_DATABASE_URL)

    # Migrationen gegen die Test-DB fahren.
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        check=True,
        capture_output=True,
    )

    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def db_session(db_engine, session_factory):
    # Vor jedem Test alle Tabellen leeren (Identitaeten zuruecksetzen).
    with db_engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalars().all()
        if tables:
            joined = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))

    session = session_factory()
    try:
        yield session
    finally:
        session.close()
