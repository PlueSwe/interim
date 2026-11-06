"""Testuppsattning.

Varje test far en egen tom SQLite-databas. Att kora mot SQLite i stallet for
Postgres gor att testerna inte kraver nagon tjanst, och det ar varfor
models/base.py har en SQLite-variant for varje Postgres-specifik typ.

Vad som INTE tackas av det valet: check-villkor med Postgres-syntax och de
partiella indexen. De provas forst nar Alembic kor mot en riktig databas.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Maste sattas innan app.config laser miljon.
_tmp = Path(tempfile.mkdtemp(prefix="interim-radar-test-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "test-nyckel-som-inte-anvands-i-drift")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def session() -> Iterator:
    """Tom databas per test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    fil = Path(tempfile.mkdtemp(prefix="ir-db-")) / "t.db"
    motor = create_engine(f"sqlite:///{fil}", future=True)
    from app.models import Base

    Base.metadata.create_all(motor)
    Session = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        motor.dispose()


@pytest.fixture
def client() -> Iterator:
    """TestClient mot en tom databas, med en ADMIN inloggad."""
    from fastapi.testclient import TestClient

    from app import db as db_modul
    from app.main import app
    from app.models import Base, User, UserRole
    from app.security import hash_password

    fil = Path(tempfile.mkdtemp(prefix="ir-api-")) / "t.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    motor = create_engine(f"sqlite:///{fil}", future=True)
    Base.metadata.create_all(motor)
    Session = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)

    # Byt ut applikationens session mot testdatabasen.
    db_modul.engine = motor
    db_modul.SessionLocal = Session

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[db_modul.get_session] = override

    s = Session()
    s.add(
        User(
            email="admin@test.example.com",
            password_hash=hash_password("testlosenord-12345"),
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    s.commit()

    c = TestClient(app)
    svar = c.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.com", "password": "testlosenord-12345"},
    )
    assert svar.status_code == 200, svar.text

    c.test_session = s  # type: ignore[attr-defined]
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        s.close()
        motor.dispose()
