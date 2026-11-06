"""Seedar kallregistret ur DECLARED_SOURCES."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SourceRegistry
from ..sources import DECLARED_SOURCES

# Lagena ar kontrollerade med scripts/probe_sources.py detta datum.
PROBED_AT = dt.date(2026, 11, 6)

# robots.txt-utfall ur kontrollen. False betyder Disallow for var User-Agent.
ROBOTS_RESULT: dict[str, bool | None] = {
    "jobtech_live": None,  # ingen robots.txt (404)
    "jobtech_hist": None,
    "ted": None,
    "e_avrop": False,
    "a_society": False,
    "mercell": True,
    "tendsign": True,
    "kommers": True,
    "opic": True,
    "brainville": True,
    "ework": True,
    "poolia": True,
    "bemannia": True,
    "avropa": True,
}


def seed_sources(session: Session) -> int:
    """Skriv eller uppdatera kallregistret. Idempotent."""
    antal = 0
    for deklarerad in DECLARED_SOURCES:
        kalla = session.scalar(select(SourceRegistry).where(SourceRegistry.key == deklarerad.key))
        if kalla is None:
            kalla = SourceRegistry(key=deklarerad.key)
            session.add(kalla)
            antal += 1
        kalla.name = deklarerad.name
        kalla.access_mode = deklarerad.access
        kalla.base_url = deklarerad.base_url
        kalla.legal_note = deklarerad.legal_note
        kalla.schedule_cron = deklarerad.schedule_cron
        kalla.robots_allows = ROBOTS_RESULT.get(deklarerad.key)
        kalla.robots_checked_at = PROBED_AT if deklarerad.key in ROBOTS_RESULT else None
        # Statusen i deklarationen galler bara nar kallan ar ny. En kalla som
        # satts till FAILING av en misslyckad korning ska inte aterstallas av en
        # omseedning.
        if kalla.status is None or antal:
            kalla.status = deklarerad.status
    session.flush()
    return antal
